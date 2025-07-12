import hashlib
import time
from django.core.cache import cache
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

class AdminCacheManager:
    """Centralized admin cache management with pattern-based clearing"""
    
    # All admin cache patterns
    ADMIN_CACHE_PATTERNS = {
        'students': [
            'admin_all_students_v8_*',
            'admin_student_enrollments_v8_*',
            'admin_students_enrollments_overview_*'
        ],
        'courses': [
            'course_detail_v8_*',
            'courses_list_v8_*',
            'course_duration_v8_*'
        ],
        'enrollments': [
            'enrollments_v8_*',
            'enrollment_*'
        ],
        'metrics': [
            'admin_metrics_*',
        ]
    }
    
    @classmethod
    def clear_admin_caches_immediately(cls, operation_type=None, **context):
        """
        Immediately clear all admin-related caches after operations
        Use this RIGHT AFTER database operations
        """
        start_time = time.time()
        
        try:
            # Method 1: Pattern-based clearing (Redis only)
            if hasattr(cache, 'delete_pattern'):
                cls._clear_with_patterns()
            else:
                # Method 2: Fallback for non-Redis backends
                cls._clear_with_key_enumeration()
            
            # Method 3: Clear specific context-related caches
            if context:
                cls._clear_context_caches(operation_type, **context)
            
            duration = time.time() - start_time
            logger.info(f"Admin cache cleared in {duration:.3f}s for operation: {operation_type}")
            
        except Exception as e:
            logger.error(f"Admin cache clearing failed: {e}")
    
    @classmethod
    def _clear_with_patterns(cls):
        """Use Redis SCAN to find and delete matching patterns"""
        patterns_to_clear = []
        for category, patterns in cls.ADMIN_CACHE_PATTERNS.items():
            patterns_to_clear.extend(patterns)
        
        for pattern in patterns_to_clear:
            try:
                cache.delete_pattern(pattern)
                logger.debug(f"Cleared pattern: {pattern}")
            except Exception as e:
                logger.warning(f"Failed to clear pattern {pattern}: {e}")
    
    @classmethod  
    def _clear_with_key_enumeration(cls):
        """Fallback method for non-Redis backends"""
        # Generate likely cache keys and delete them
        keys_to_delete = []
        
        # Student list variations
        search_terms = ['', 'john', 'jane', 'test', 'admin']
        statuses = ['', 'enrolled', 'not_enrolled', 'active', 'inactive']
        
        for search in search_terms:
            for status in statuses:
                for page in range(1, 20):
                    cache_key_data = f"admin_all_students_v8_{search}_{status}_{page}"
                    hashed_key = hashlib.md5(cache_key_data.encode()).hexdigest()
                    keys_to_delete.append(hashed_key)
        
        # Student enrollment details (user IDs 1-10000)
        for user_id in range(1, 10001):
            cache_key_data = f"admin_student_enrollments_v8_{user_id}"
            hashed_key = hashlib.md5(cache_key_data.encode()).hexdigest()
            keys_to_delete.append(hashed_key)
        
        # Clear in batches
        batch_size = 1000
        for i in range(0, len(keys_to_delete), batch_size):
            batch = keys_to_delete[i:i + batch_size]
            cache.delete_many(batch)
    
    @classmethod
    def _clear_context_caches(cls, operation_type, **context):
        """Clear specific caches based on operation context"""
        if operation_type == 'user_enrollment':
            user_id = context.get('user_id')
            course_id = context.get('course_id') 
            
            if user_id:
                # Clear specific user caches
                user_cache_key = f"admin_student_enrollments_v8_{user_id}"
                hashed_key = hashlib.md5(user_cache_key.encode()).hexdigest()
                cache.delete(hashed_key)
                
                # Clear user's enrollment caches
                enrollment_patterns = [
                    f"enrollments_v8_{user_id}_*",
                    f"enrollment_summary_v8_{user_id}"
                ]
                for pattern in enrollment_patterns:
                    if hasattr(cache, 'delete_pattern'):
                        cache.delete_pattern(pattern)
            
            if course_id:
                # Clear course-related caches
                course_patterns = [
                    f"course_detail_v8_{course_id}_*",
                    f"course_duration_v8_{course_id}"
                ]
                for pattern in course_patterns:
                    if hasattr(cache, 'delete_pattern'):
                        cache.delete_pattern(pattern)

# Enhanced Mixin for Admin Views
class EnhancedAdminCacheMixin:
    """Enhanced mixin with immediate cache clearing"""
    
    def clear_caches_after_operation(self, operation_type, **context):
        """Call this immediately after successful database operations"""
        
        # Clear caches within the same database transaction
        transaction.on_commit(lambda: AdminCacheManager.clear_admin_caches_immediately(
            operation_type=operation_type, 
            **context
        ))
        
        # Also clear immediately for instant admin feedback
        AdminCacheManager.clear_admin_caches_immediately(
            operation_type=operation_type,
            **context
        )