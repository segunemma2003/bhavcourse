import hashlib
import logging
from django.core.cache import cache
from django.conf import settings
from typing import List, Optional, Union

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Centralized cache management system for comprehensive cache clearing
    """
    
    # Current cache version - increment when cache structure changes
    CACHE_VERSION = "v9"
    
    # Cache key patterns organized by entity type
    CACHE_PATTERNS = {
        'courses': [
            'courses_list_{}',
            'course_detail_{}_{}',  # course_id, user_id
            'course_duration_{}',   # course_id
            'category_detail_{}',   # category_id
        ],
        'categories': [
            'categories_list_{}',
            'category_detail_{}',   # category_id
        ],
        'enrollments': [
            'enrollments_{}_list_{}',      # user_id, show_all
            'enrollments_{}_{}_{}_{}',     # user_id, page, page_size, filters
            'enrollment_detail_{}',        # enrollment_id
            'enrollment_summary_{}',       # user_id
            'enrollment_status_{}_{}',     # user_id, course_id
        ],
        'users': [
            'user_profile_{}',             # user_id
            'user_enrollments_{}',         # user_id
            'user_notifications_{}',       # user_id
            'user_wishlist_{}',           # user_id
        ],
        'admin': [
            'admin_all_students_{}_{}',        # filters_hash, page
            'admin_student_enrollments_{}',    # user_id
            'admin_metrics_{}',               # time_period
        ],
        'notifications': [
            'notifications_{}_{}',         # user_id, is_seen
        ],
        'wishlist': [
            'wishlist_{}',                 # user_id
        ],
        'global': [
            'courses_list_{}',
            'categories_list_{}',
            'admin_all_students_{}',
        ]
    }
    
    @classmethod
    def _get_cache_key(cls, pattern: str, *args) -> str:
        """Generate standardized cache key with version"""
        try:
            formatted_pattern = pattern.format(*args)
            cache_key_data = f"{formatted_pattern}_{cls.CACHE_VERSION}"
            return hashlib.md5(cache_key_data.encode()).hexdigest()
        except Exception as e:
            logger.warning(f"Cache key generation failed for pattern {pattern}: {e}")
            return f"fallback_{hashlib.md5(str(args).encode()).hexdigest()}"
    
    @classmethod
    def clear_cache_patterns(cls, patterns: List[str], *args) -> int:
        """Clear multiple cache patterns with given arguments"""
        cleared_count = 0
        cache_keys = []
        
        for pattern in patterns:
            try:
                cache_key = cls._get_cache_key(pattern, *args)
                cache_keys.append(cache_key)
            except Exception as e:
                logger.warning(f"Failed to generate cache key for pattern {pattern}: {e}")
        
        if cache_keys:
            try:
                cache.delete_many(cache_keys)
                cleared_count = len(cache_keys)
                logger.info(f"Cleared {cleared_count} cache keys")
            except Exception as e:
                logger.error(f"Cache deletion failed: {e}")
        
        return cleared_count
    
    @classmethod
    def clear_user_cache(cls, user_id: int) -> int:
        """Clear all user-related caches"""
        cleared_count = 0
        
        # Clear enrollment caches with various combinations
        enrollment_patterns = [
            'enrollments_{}_list_true',
            'enrollments_{}_list_false',
            'enrollment_summary_{}',
        ]
        
        for pattern in enrollment_patterns:
            cache_key = cls._get_cache_key(pattern, user_id)
            cache.delete(cache_key)
            cleared_count += 1
        
        # Clear enrollment status for all courses (range approach)
        for course_id in range(1, 1000):  # Adjust range based on your data
            cache_key = cls._get_cache_key('enrollment_status_{}_{}', user_id, course_id)
            cache.delete(cache_key)
            cleared_count += 1
        
        # Clear other user-related caches
        user_patterns = cls.CACHE_PATTERNS['users'] + cls.CACHE_PATTERNS['notifications'] + cls.CACHE_PATTERNS['wishlist']
        cleared_count += cls.clear_cache_patterns(user_patterns, user_id)
        
        # Clear admin caches that might include this user
        cls.clear_admin_cache()
        
        logger.info(f"Cleared {cleared_count} cache keys for user {user_id}")
        return cleared_count
    
    @classmethod
    def clear_course_cache(cls, course_id: Optional[int] = None) -> int:
        """Clear all course-related caches"""
        cleared_count = 0
        
        if course_id:
            # Clear specific course caches
            course_patterns = [
                'course_detail_{}_{}',    # Will clear for all users
                'course_duration_{}',
            ]
            
            # Clear course detail for all users (range approach)
            for user_id in range(1, 10000):  # Adjust range
                cache_key = cls._get_cache_key('course_detail_{}_{}', course_id, user_id)
                cache.delete(cache_key)
                cleared_count += 1
            
            # Clear course duration
            cache_key = cls._get_cache_key('course_duration_{}', course_id)
            cache.delete(cache_key)
            cleared_count += 1
        
        # Clear global course caches
        global_patterns = [
            'courses_list_{}',
            'categories_list_{}',
        ]
        
        # Clear course lists with various filter combinations
        common_filters = ['', 'featured', 'search', 'category']
        for filter_combo in common_filters:
            for page in range(1, 20):  # Clear first 20 pages
                cache_key = cls._get_cache_key('courses_list_{}_{}', filter_combo, page)
                cache.delete(cache_key)
                cleared_count += 1
        
        # Clear category caches
        for cat_id in range(1, 100):  # Adjust range
            cache_key = cls._get_cache_key('category_detail_{}', cat_id)
            cache.delete(cache_key)
            cleared_count += 1
        
        # Clear admin caches
        cls.clear_admin_cache()
        
        logger.info(f"Cleared {cleared_count} course-related cache keys")
        return cleared_count
    
    @classmethod
    def clear_admin_cache(cls) -> int:
        """Clear all admin-related caches"""
        cleared_count = 0
        
        # Clear admin student lists with various filters
        common_admin_filters = [
            '', 'enrolled', 'not_enrolled', 'active', 'inactive'
        ]
        
        for filter_combo in common_admin_filters:
            for page in range(1, 50):  # Admin might have many pages
                cache_key = cls._get_cache_key('admin_all_students_{}_{}', filter_combo, page)
                cache.delete(cache_key)
                cleared_count += 1
        
        # Clear admin student enrollment details
        for user_id in range(1, 10000):  # Adjust range
            cache_key = cls._get_cache_key('admin_student_enrollments_{}', user_id)
            cache.delete(cache_key)
            cleared_count += 1
        
        # Clear admin metrics
        for time_period in ['week', 'month', 'year']:
            cache_key = cls._get_cache_key('admin_metrics_{}', time_period)
            cache.delete(cache_key)
            cleared_count += 1
        
        logger.info(f"Cleared {cleared_count} admin cache keys")
        return cleared_count
    
    @classmethod
    def clear_enrollment_cache(cls, user_id: int, course_id: Optional[int] = None) -> int:
        """Clear enrollment-related caches"""
        cleared_count = 0
        
        # Clear user enrollment caches
        cleared_count += cls.clear_user_cache(user_id)
        
        # Clear course-related caches if course_id provided
        if course_id:
            cleared_count += cls.clear_course_cache(course_id)
        
        return cleared_count
    
    @classmethod
    def clear_all_cache(cls) -> int:
        """Nuclear option - clear all application caches"""
        try:
            cache.clear()
            logger.warning("Cleared ALL cache - nuclear option used")
            return 1
        except Exception as e:
            logger.error(f"Failed to clear all cache: {e}")
            return 0
    
    @classmethod
    def warm_critical_caches(cls):
        """Warm up critical caches after major operations"""
        try:
            # Import here to avoid circular imports
            from .models import Course, Category, User
            
            # Warm up category list
            categories = Category.objects.all()[:10]
            
            # Warm up featured courses
            featured_courses = Course.objects.filter(is_featured=True)[:5]
            
            logger.info("Critical caches warmed up")
        except Exception as e:
            logger.warning(f"Cache warming failed: {e}")

# Usage in your admin views:

class AdminCacheMixin:
    """Mixin for admin views to handle cache clearing"""
    
    def clear_relevant_caches(self, operation_type: str, **kwargs):
        """Clear caches based on operation type"""
        try:
            if operation_type == 'user_delete':
                user_id = kwargs.get('user_id')
                if user_id:
                    CacheManager.clear_user_cache(user_id)
                    CacheManager.clear_admin_cache()
            
            elif operation_type == 'user_enroll':
                user_id = kwargs.get('user_id')
                course_id = kwargs.get('course_id')
                if user_id:
                    CacheManager.clear_enrollment_cache(user_id, course_id)
                    CacheManager.clear_admin_cache()
            
            elif operation_type == 'course_create' or operation_type == 'course_update' or operation_type == 'course_delete':
                course_id = kwargs.get('course_id')
                CacheManager.clear_course_cache(course_id)
                CacheManager.clear_admin_cache()
            
            elif operation_type == 'bulk_operation':
                # For bulk operations, clear everything
                CacheManager.clear_admin_cache()
                CacheManager.clear_course_cache()
                # Clear user caches for affected users
                user_ids = kwargs.get('user_ids', [])
                for user_id in user_ids:
                    CacheManager.clear_user_cache(user_id)
            
            # Warm up critical caches after clearing
            CacheManager.warm_critical_caches()
            
        except Exception as e:
            logger.error(f"Cache clearing failed for {operation_type}: {e}")
