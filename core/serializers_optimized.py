# core/serializers_optimized.py
from rest_framework import serializers
from django.core.cache import cache
from django.utils import timezone
from .models import Course, CourseCurriculum, Enrollment, Category
import hashlib
import logging

logger = logging.getLogger(__name__)

class OptimizedCourseCurriculumSerializer(serializers.ModelSerializer):
    """
    Curriculum serializer that returns presigned URLs without generation
    """
    video_url = serializers.SerializerMethodField()
    video_status = serializers.SerializerMethodField()
    
    class Meta:
        model = CourseCurriculum
        fields = ['id', 'title', 'video_url', 'video_status', 'order']
    
    def get_video_url(self, obj):
        """
        Return presigned URL if ready, None if not ready (NO GENERATION)
        """
        if obj.url_generation_status == 'not_needed':
            return obj.video_url  # Return original URL for non-S3 files
        
        if obj.is_url_ready:
            return obj.presigned_url
        
        return None  # Don't return anything if not ready
    
    def get_video_status(self, obj):
        """
        Return status information for frontend handling
        """
        if obj.url_generation_status == 'not_needed':
            return {
                'status': 'ready',
                'message': 'Video ready'
            }
        
        status_messages = {
            'pending': 'Video URL is being prepared...',
            'ready': 'Video ready',
            'failed': 'Video temporarily unavailable',
            'expired': 'Video URL is being refreshed...'
        }
        
        return {
            'status': obj.url_generation_status,
            'message': status_messages.get(obj.url_generation_status, 'Unknown status'),
            'retry_after': 30 if obj.url_generation_status in ['pending', 'expired'] else None
        }

class MinimalCurriculumSerializer(serializers.ModelSerializer):
    """
    Minimal curriculum for list views - no video URLs
    """
    class Meta:
        model = CourseCurriculum
        fields = ['id', 'title', 'order']

class OptimizedCourseListSerializer(serializers.ModelSerializer):
    """
    Optimized course serializer for list views
    """
    category_name = serializers.CharField(source='category.name', read_only=True)
    enrolled_students = serializers.SerializerMethodField()
    is_enrolled = serializers.SerializerMethodField()
    is_wishlisted = serializers.SerializerMethodField()
    curriculum_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'image', 'small_desc', 'category', 
            'category_name', 'is_featured', 'date_uploaded', 
            'location', 'enrolled_students', 'is_enrolled', 'is_wishlisted',
            'price_one_month', 'price_three_months', 'price_lifetime',
            'curriculum_count'
        ]
    
    def get_enrolled_students(self, obj):
        """Use annotated value if available, fallback to property"""
        if hasattr(obj, 'enrollment_count'):
            return obj.enrollment_count
        return getattr(obj, '_enrolled_count', 0)
    
    def get_is_enrolled(self, obj):
        """Optimized enrollment check with caching"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        
        # Use prefetched data if available
        if hasattr(obj, '_user_enrollment_status'):
            return obj._user_enrollment_status
        
        # Check cache
        cache_key = f"user_enrolled_{request.user.id}_{obj.id}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Fallback to database query
        is_enrolled = obj.enrollments.filter(
            user=request.user,
            is_active=True
        ).exists()
        
        cache.set(cache_key, is_enrolled, 300)  # Cache for 5 minutes
        return is_enrolled
    
    def get_is_wishlisted(self, obj):
        """Check wishlist status with caching"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        
        cache_key = f"user_wishlist_{request.user.id}_{obj.id}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
        
        is_wishlisted = obj.wishlisted_by.filter(user=request.user).exists()
        cache.set(cache_key, is_wishlisted, 600)  # Cache for 10 minutes
        return is_wishlisted
    
    def get_curriculum_count(self, obj):
        """Get curriculum count efficiently"""
        if hasattr(obj, 'curriculum_count'):
            return obj.curriculum_count
        return obj.curriculum.count()

class OptimizedCourseDetailSerializer(OptimizedCourseListSerializer):
    """
    Full course details with optimized curriculum
    """
    objectives = serializers.StringRelatedField(many=True, read_only=True)
    requirements = serializers.StringRelatedField(many=True, read_only=True)
    curriculum = OptimizedCourseCurriculumSerializer(many=True, read_only=True)
    enrollment_status = serializers.SerializerMethodField()
    
    class Meta(OptimizedCourseListSerializer.Meta):
        fields = OptimizedCourseListSerializer.Meta.fields + [
            'description', 'objectives', 'requirements', 'curriculum', 'enrollment_status'
        ]
    
    def get_enrollment_status(self, obj):
        """Get detailed enrollment status"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return {'status': 'unauthenticated', 'message': 'Please log in'}
        
        # Use cached data if available
        cache_key = f"enrollment_status_{request.user.id}_{obj.id}"
        cached_status = cache.get(cache_key)
        if cached_status:
            return cached_status
        
        try:
            enrollment = obj.enrollments.filter(user=request.user).first()
            if not enrollment:
                status = {'status': 'not_enrolled', 'message': 'Not enrolled'}
            elif not enrollment.is_active:
                status = {'status': 'inactive', 'message': 'Enrollment inactive'}
            elif enrollment.is_expired:
                status = {'status': 'expired', 'message': 'Enrollment expired'}
            else:
                status = {
                    'status': 'active',
                    'message': 'Active enrollment',
                    'plan_type': enrollment.plan_type,
                    'expires_on': enrollment.expiry_date
                }
            
            cache.set(cache_key, status, 300)  # Cache for 5 minutes
            return status
            
        except Exception as e:
            logger.error(f"Error getting enrollment status: {e}")
            return {'status': 'error', 'message': 'Unable to check status'}

class PaginatedEnrollmentSerializer(serializers.ModelSerializer):
    """
    Lightweight enrollment serializer for paginated lists
    """
    course = OptimizedCourseListSerializer(read_only=True)
    plan_name = serializers.CharField(source='get_plan_type_display', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    days_remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = Enrollment
        fields = [
            'id', 'course', 'date_enrolled', 'plan_type', 'plan_name',
            'expiry_date', 'amount_paid', 'is_active', 'is_expired', 'days_remaining'
        ]
    
    def get_days_remaining(self, obj):
        """Calculate days remaining"""
        if obj.plan_type == 'LIFETIME':
            return None
        if not obj.expiry_date or obj.is_expired:
            return 0
        delta = obj.expiry_date - timezone.now()
        return max(0, delta.days)

class FullEnrollmentSerializer(PaginatedEnrollmentSerializer):
    """
    Full enrollment details with curriculum
    """
    course = OptimizedCourseDetailSerializer(read_only=True)
    
    class Meta(PaginatedEnrollmentSerializer.Meta):
        pass  # Inherits all fields but uses detailed course serializer