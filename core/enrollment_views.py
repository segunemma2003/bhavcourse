from datetime import timezone
from django.db.models import Prefetch, Q
from django.core.cache import cache
from rest_framework.decorators import action
from rest_framework.response import Response
import hashlib
import json
from rest_framework import viewsets, permissions, filters, status, generics, serializers
from core.models import CourseCurriculum, CourseObjective, CourseRequirement, Enrollment
from core.serializers import EnrollmentSerializer, LightweightEnrollmentSerializer

import logging

logger = logging.getLogger(__name__)


class OptimizedEnrollmentViewSet(viewsets.ModelViewSet):
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None  # Disable pagination for better caching
    
    def get_queryset(self):
        """Ultra-optimized queryset with minimal database hits"""
        if getattr(self, 'swagger_fake_view', False):
            return Enrollment.objects.none()
        
        return Enrollment.objects.select_related(
            'course',
            'course__category'
        ).prefetch_related(
            # Only prefetch what we actually need
            Prefetch(
                'course__objectives',
                queryset=CourseObjective.objects.only('id', 'description', 'course_id')
            ),
            Prefetch(
                'course__requirements',
                queryset=CourseRequirement.objects.only('id', 'description', 'course_id')
            ),
            Prefetch(
                'course__curriculum',
                queryset=CourseCurriculum.objects.only(
                    'id', 'title', 'video_url', 'order', 'course_id'
                ).order_by('order')
            )
        ).filter(
            user=self.request.user
        ).only(
            # Only fetch fields we actually use
            'id', 'course_id', 'date_enrolled', 'plan_type', 
            'expiry_date', 'amount_paid', 'is_active',
            'course__id', 'course__title', 'course__image', 
            'course__small_desc', 'course__category_id',
            'course__category__name'
        ).order_by('-date_enrolled')
    
    def list(self, request, *args, **kwargs):
        """Heavily cached list with smart invalidation"""
        try:
            # Create cache key
            cache_key = self._get_cache_key(request)
            
            # Try cache first (extend to 1 hour)
            cached_data = cache.get(cache_key)
            if cached_data:
                return Response(cached_data)
            
            # Get optimized queryset
            queryset = self.get_queryset()
            
            # Use lightweight serializer
            serializer = LightweightEnrollmentSerializer(queryset, many=True, context={'request': request})
            response_data = serializer.data
            
            # Cache for 1 hour (enrollments don't change often)
            cache.set(cache_key, response_data, 3600)
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Enrollment list error for user {request.user.id}: {str(e)}")
            return Response(
                {"error": "Failed to fetch enrollments", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_cache_key(self, request):
        """Generate deterministic cache key"""
        user_id = request.user.id
        key_data = f"enrollments_v2_{user_id}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _clear_user_cache(self, user_id):
        """Clear cache when data changes"""
        key_data = f"enrollments_v2_{user_id}"
        cache_key = hashlib.md5(key_data.encode()).hexdigest()
        cache.delete(cache_key)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Fast summary endpoint with aggregated data"""
        cache_key = f"enrollment_summary_{request.user.id}"
        cached_summary = cache.get(cache_key)
        
        if cached_summary:
            return Response(cached_summary)
        
        # Use database aggregation for speed
        from django.db.models import Count, Q
        
        summary = Enrollment.objects.filter(user=request.user).aggregate(
            total_enrollments=Count('id'),
            active_enrollments=Count('id', filter=Q(is_active=True)),
            expired_enrollments=Count('id', filter=Q(is_active=True, expiry_date__lt=timezone.now()))
        )
        
        # Cache summary for 30 minutes
        cache.set(cache_key, summary, 1800)
        return Response(summary)