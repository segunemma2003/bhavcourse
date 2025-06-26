# core/views_optimized.py
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q, Exists, OuterRef
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Course, Enrollment, CourseCurriculum, Category
from .serializers_optimized import (
    OptimizedCourseListSerializer, OptimizedCourseDetailSerializer,
    PaginatedEnrollmentSerializer, FullEnrollmentSerializer,
    MinimalCurriculumSerializer
)
import hashlib
import time
import logging

logger = logging.getLogger(__name__)

class HighPerformanceMixin:
    """
    Mixin for high-performance views with intelligent caching
    """
    
    def get_cache_key(self, prefix, *args, **kwargs):
        """Generate cache key from arguments"""
        key_parts = [prefix] + [str(arg) for arg in args]
        if kwargs:
            sorted_kwargs = sorted(kwargs.items())
            key_parts.extend([f"{k}:{v}" for k, v in sorted_kwargs])
        
        key_string = "_".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get_cached_response(self, cache_key, timeout=3600):
        """Get cached response if available"""
        return cache.get(cache_key)
    
    def set_cached_response(self, cache_key, data, timeout=3600):
        """Cache response data"""
        cache.set(cache_key, data, timeout)
    
    def get_paginated_cache_key(self, base_key, page, page_size):
        """Generate cache key for paginated data"""
        return f"{base_key}_page_{page}_size_{page_size}"

class OptimizedCourseViewSet(HighPerformanceMixin, viewsets.ModelViewSet):
    """
    Ultra-optimized course viewset for 1M+ users
    """
    permission_classes = [permissions.AllowAny]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return OptimizedCourseListSerializer
        elif self.action == 'retrieve':
            return OptimizedCourseDetailSerializer
        return OptimizedCourseListSerializer
    
    def get_queryset(self):
        """Optimized queryset with minimal database hits"""
        if getattr(self, 'swagger_fake_view', False):
            return Course.objects.none()
        
        # Base queryset with essential joins
        queryset = Course.objects.select_related('category')
        
        # Add annotations for computed fields
        queryset = queryset.annotate(
            enrollment_count=Count('enrollments', filter=Q(enrollments__is_active=True)),
            curriculum_count=Count('curriculum')
        )
        
        # Add user-specific annotations if authenticated
        if hasattr(self.request, 'user') and self.request.user.is_authenticated:
            user_enrollment = Enrollment.objects.filter(
                course=OuterRef('pk'),
                user=self.request.user,
                is_active=True
            )
            
            queryset = queryset.annotate(
                _user_enrollment_status=Exists(user_enrollment)
            )
        
        # Apply filters
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        is_featured = self.request.query_params.get('featured')
        if is_featured and is_featured.lower() == 'true':
            queryset = queryset.filter(is_featured=True)
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(small_desc__icontains=search)
            )
        
        location = self.request.query_params.get('location')
        if location:
            queryset = queryset.filter(location__icontains=location)
        
        return queryset.order_by('-is_featured', '-date_uploaded')
    
    def list(self, request, *args, **kwargs):
        """Cached and paginated course list"""
        start_time = time.time()
        
        # Generate cache key based on query parameters and user
        user_id = request.user.id if request.user.is_authenticated else 'anonymous'
        cache_params = {
           'category': request.query_params.get('category', ''),
           'featured': request.query_params.get('featured', ''),
           'search': request.query_params.get('search', ''),
           'location': request.query_params.get('location', ''),
           'user_id': user_id
       }
       
       page = int(request.query_params.get('page', 1))
       page_size = min(int(request.query_params.get('page_size', 20)), 50)  # Max 50 items
       
       base_cache_key = self.get_cache_key('course_list_v4', **cache_params)
       cache_key = self.get_paginated_cache_key(base_cache_key, page, page_size)
       
       # Try cache first
       cached_data = self.get_cached_response(cache_key, timeout=1800)  # 30 minutes
       if cached_data:
           logger.info(f"Course list cache HIT - {time.time() - start_time:.3f}s")
           return Response(cached_data)
       
       # Get queryset and paginate
       queryset = self.get_queryset()
       paginator = Paginator(queryset, page_size)
       page_obj = paginator.get_page(page)
       
       # Serialize data
       serializer = self.get_serializer(page_obj, many=True)
       
       # Prepare response
       response_data = {
           'count': paginator.count,
           'next': page_obj.next_page_number() if page_obj.has_next() else None,
           'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
           'results': serializer.data
       }
       
       # Cache the response
       self.set_cached_response(cache_key, response_data, timeout=1800)
       
       elapsed = time.time() - start_time
       logger.info(f"Course list completed in {elapsed:.3f}s (page {page}, {len(page_obj)} items)")
       
       return Response(response_data)
   
   def retrieve(self, request, *args, **kwargs):
       """Cached course detail"""
       start_time = time.time()
       course_id = kwargs.get('pk')
       user_id = request.user.id if request.user.is_authenticated else 'anonymous'
       
       cache_key = self.get_cache_key('course_detail_v4', course_id, user_id)
       cached_data = self.get_cached_response(cache_key, timeout=1800)
       
       if cached_data:
           logger.info(f"Course detail cache HIT - {time.time() - start_time:.3f}s")
           return Response(cached_data)
       
       # Get course with optimized query
       try:
           course = self.get_queryset().prefetch_related(
               'objectives',
               'requirements',
               Prefetch(
                   'curriculum',
                   queryset=CourseCurriculum.objects.order_by('order')
               )
           ).get(pk=course_id)
       except Course.DoesNotExist:
           return Response({'error': 'Course not found'}, status=404)
       
       serializer = self.get_serializer(course)
       response_data = serializer.data
       
       # Cache the response
       self.set_cached_response(cache_key, response_data, timeout=1800)
       
       elapsed = time.time() - start_time
       logger.info(f"Course detail completed in {elapsed:.3f}s for course {course_id}")
       
       return Response(response_data)

class OptimizedEnrollmentViewSet(HighPerformanceMixin, viewsets.ModelViewSet):
   """
   Ultra-optimized enrollment viewset for 1M+ users
   """
   permission_classes = [permissions.IsAuthenticated]
   
   def get_serializer_class(self):
       if self.action == 'list':
           return PaginatedEnrollmentSerializer
       return FullEnrollmentSerializer
   
   def get_queryset(self):
       """Optimized enrollment queryset"""
       if getattr(self, 'swagger_fake_view', False):
           return Enrollment.objects.none()
       
       if self.action == 'list':
           # Lightweight query for list view
           return Enrollment.objects.filter(
               user=self.request.user,
               is_active=True
           ).select_related(
               'course',
               'course__category'
           ).annotate(
               curriculum_count=Count('course__curriculum')
           ).order_by('-date_enrolled')
       else:
           # Full query for detail view
           return Enrollment.objects.filter(
               user=self.request.user
           ).select_related(
               'course',
               'course__category'
           ).prefetch_related(
               'course__objectives',
               'course__requirements',
               Prefetch(
                   'course__curriculum',
                   queryset=CourseCurriculum.objects.order_by('order')
               )
           ).order_by('-date_enrolled')
   
   def list(self, request, *args, **kwargs):
       """Paginated enrollment list with caching"""
       start_time = time.time()
       user_id = request.user.id
       
       page = int(request.query_params.get('page', 1))
       page_size = min(int(request.query_params.get('page_size', 10)), 25)  # Max 25 enrollments
       show_all = request.query_params.get('show_all', 'false').lower() == 'true'
       
       cache_key = self.get_cache_key(
           'enrollment_list_v5', 
           user_id, 
           page, 
           page_size, 
           show_all
       )
       
       # Try cache first
       cached_data = self.get_cached_response(cache_key, timeout=3600)  # 1 hour
       if cached_data:
           logger.info(f"Enrollment list cache HIT - {time.time() - start_time:.3f}s")
           return Response(cached_data)
       
       # Get queryset
       queryset = self.get_queryset()
       if not show_all:
           # Only active, non-expired enrollments by default
           queryset = queryset.filter(
               Q(expiry_date__isnull=True) | Q(expiry_date__gt=timezone.now())
           )
       
       # Paginate
       paginator = Paginator(queryset, page_size)
       page_obj = paginator.get_page(page)
       
       if not page_obj:
           response_data = {
               'count': 0,
               'next': None,
               'previous': None,
               'results': []
           }
       else:
           serializer = self.get_serializer(page_obj, many=True)
           response_data = {
               'count': paginator.count,
               'next': page_obj.next_page_number() if page_obj.has_next() else None,
               'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
               'results': serializer.data
           }
       
       # Cache the response
       self.set_cached_response(cache_key, response_data, timeout=3600)
       
       elapsed = time.time() - start_time
       logger.info(f"Enrollment list completed in {elapsed:.3f}s (user {user_id}, page {page})")
       
       return Response(response_data)
   
   def retrieve(self, request, *args, **kwargs):
       """Single enrollment with full course details"""
       start_time = time.time()
       enrollment_id = kwargs.get('pk')
       user_id = request.user.id
       
       cache_key = self.get_cache_key('enrollment_detail_v3', enrollment_id, user_id)
       cached_data = self.get_cached_response(cache_key, timeout=1800)
       
       if cached_data:
           logger.info(f"Enrollment detail cache HIT - {time.time() - start_time:.3f}s")
           return Response(cached_data)
       
       try:
           enrollment = self.get_queryset().get(pk=enrollment_id)
       except Enrollment.DoesNotExist:
           return Response({'error': 'Enrollment not found'}, status=404)
       
       serializer = self.get_serializer(enrollment)
       response_data = serializer.data
       
       # Cache the response
       self.set_cached_response(cache_key, response_data, timeout=1800)
       
       elapsed = time.time() - start_time
       logger.info(f"Enrollment detail completed in {elapsed:.3f}s for enrollment {enrollment_id}")
       
       return Response(response_data)
   
   @action(detail=False, methods=['get'])
   def summary(self, request):
       """Fast enrollment summary with caching"""
       user_id = request.user.id
       cache_key = self.get_cache_key('enrollment_summary_v4', user_id)
       
       cached_data = self.get_cached_response(cache_key, timeout=1800)
       if cached_data:
           return Response(cached_data)
       
       # Use database aggregation for speed
       summary = Enrollment.objects.filter(user=request.user).aggregate(
           total_enrollments=Count('id'),
           active_enrollments=Count('id', filter=Q(is_active=True)),
           expired_enrollments=Count(
               'id', 
               filter=Q(is_active=True, expiry_date__lt=timezone.now())
           )
       )
       
       # Add curriculum count
       total_curriculum = CourseCurriculum.objects.filter(
           course__enrollments__user=request.user,
           course__enrollments__is_active=True
       ).count()
       
       summary['total_curriculum_items'] = total_curriculum
       
       # Cache for 30 minutes
       self.set_cached_response(cache_key, summary, timeout=1800)
       return Response(summary)

class OptimizedCourseCurriculumViewSet(HighPerformanceMixin, viewsets.ModelViewSet):
   """
   Optimized curriculum viewset with presigned URL handling
   """
   permission_classes = [permissions.AllowAny]  # Adjust based on your needs
   
   def get_queryset(self):
       course_pk = self.kwargs.get('course_pk')
       if course_pk:
           return CourseCurriculum.objects.filter(
               course_id=course_pk
           ).order_by('order')
       return CourseCurriculum.objects.none()
   
   def list(self, request, course_pk=None, *args, **kwargs):
       """Cached curriculum list"""
       start_time = time.time()
       
       cache_key = self.get_cache_key('curriculum_list_v3', course_pk)
       cached_data = self.get_cached_response(cache_key, timeout=3600)  # 1 hour
       
       if cached_data:
           logger.info(f"Curriculum cache HIT - {time.time() - start_time:.3f}s")
           return Response(cached_data)
       
       try:
           course = Course.objects.get(pk=course_pk)
       except Course.DoesNotExist:
           return Response({'error': 'Course not found'}, status=404)
       
       queryset = self.get_queryset()
       from .serializers_optimized import OptimizedCourseCurriculumSerializer
       serializer = OptimizedCourseCurriculumSerializer(queryset, many=True)
       response_data = serializer.data
       
       # Cache the response
       self.set_cached_response(cache_key, response_data, timeout=3600)
       
       elapsed = time.time() - start_time
       logger.info(f"Curriculum list completed in {elapsed:.3f}s for course {course_pk}")
       
       return Response(response_data)

# Cache warming service for popular content
class CacheWarmingService:
   """
   Service to pre-warm caches for better performance
   """
   
   @staticmethod
   def warm_popular_courses(limit=50):
       """Pre-warm cache for popular courses"""
       try:
           popular_courses = Course.objects.annotate(
               enrollment_count=Count('enrollments')
           ).order_by('-enrollment_count')[:limit]
           
           # Warm course list cache
           for course in popular_courses:
               cache_key = f"course_detail_v4_{course.id}_anonymous"
               if not cache.get(cache_key):
                   # This would be called by a background task
                   pass
           
           logger.info(f"Cache warming queued for {len(popular_courses)} popular courses")
           
       except Exception as e:
           logger.error(f"Cache warming failed: {e}")
   
   @staticmethod
   def warm_user_enrollments(user_id):
       """Pre-warm cache for user's enrollments"""
       try:
           cache_key = f"enrollment_list_v5_{user_id}_1_10_false"
           if not cache.get(cache_key):
               # This would be called by a background task
               pass
           
           logger.info(f"Cache warming queued for user {user_id}")
           
       except Exception as e:
           logger.error(f"User cache warming failed: {e}")