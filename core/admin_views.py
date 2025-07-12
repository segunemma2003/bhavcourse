
import hashlib
from rest_framework import generics, viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.db.models import Count, Sum
from django.utils import timezone
from django.db import transaction
from datetime import timedelta, datetime
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth

from core.admin_cache_manager import EnhancedAdminCacheMixin
from .models import Course, CoursePlanType, FCMDevice, Notification, PaymentCard, PaymentOrder, User, Purchase, ContentPage, GeneralSettings, UserSubscription, Wishlist
from .serializers import (
    AdminMetricsSerializer, ContentPageSerializer, 
    GeneralSettingsSerializer, CourseListSerializer, StudentEnrollmentDetailSerializer
)
from django.core.cache import cache
from rest_framework import serializers
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models import Count, Q,  Prefetch
from .serializers import UserDetailsSerializer
from django.contrib.auth import get_user_model
from .models import Enrollment
from rest_framework.permissions import IsAdminUser
import uuid
from decimal import Decimal
import logging

from .cache_manager import CacheManager, AdminCacheMixin

logger = logging.getLogger(__name__)
User = get_user_model()





class AdminDeleteUserAccountView(EnhancedAdminCacheMixin, generics.DestroyAPIView):
    """
    Admin API endpoint for deleting any user account by ID.
    This permanently deletes the user and all associated data.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    @swagger_auto_schema(
        operation_summary="Admin: Delete user account",
        operation_description="""
        Admin-only endpoint to permanently delete any user account by ID.
        Now with comprehensive cache clearing to ensure UI updates immediately.
        """
    )
    def delete(self, request, user_id, *args, **kwargs):
        try:
            # Get the user to delete
            user_to_delete = User.objects.get(pk=user_id)
            
            # Prevent deletion of admin users
            if user_to_delete.is_staff or user_to_delete.is_superuser:
                return Response(
                    {
                        'error': 'Cannot delete admin user',
                        'details': 'Admin users cannot be deleted through this endpoint'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Prevent admin from deleting themselves
            if user_to_delete.id == request.user.id:
                return Response(
                    {
                        'error': 'Cannot delete own account',
                        'details': 'Admins cannot delete their own account through this endpoint'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Store user info before deletion
            user_info = {
                'id': user_to_delete.id,
                'email': user_to_delete.email,
                'full_name': user_to_delete.full_name,
                'date_joined': user_to_delete.date_joined
            }
            
            # Perform cleanup and get summary
            with transaction.atomic():
                cleanup_summary = self._cleanup_user_data(user_to_delete)
                
                # Create audit log before deletion
                self._create_audit_log(request.user, user_to_delete, cleanup_summary)
                
                # CLEAR CACHES BEFORE DELETION
                self.clear_relevant_caches('user_delete', user_id=user_id)
                
                # Delete the user (this will cascade to related objects)
                user_to_delete.delete()
            
            # ADDITIONAL cache clearing after deletion
            CacheManager.clear_admin_cache()
            CacheManager.clear_course_cache()  # In case user was in course lists
            self.clear_caches_after_operation(
                    operation_type='user_delete',
                    user_id=user_id
                )
            # Prepare response
            response_data = {
                'message': f'User account for {user_info["email"]} deleted successfully',
                'deleted_user': user_info,
                'cleanup_summary': cleanup_summary,
                'deleted_by': request.user.email,
                'deletion_timestamp': timezone.now(),
                'cache_cleared': True  # Indicate caches were cleared
            }
            
            return Response({"success": True, "data": response_data}, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response(
                {
                    'error': 'User not found',
                    'details': f'No user found with ID {user_id}'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Admin user deletion failed for user {user_id}: {str(e)}")
            return Response(
                {
                    'error': 'Deletion failed',
                    'details': str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def _cleanup_user_data(self, user):
        """Clean up all user-related data and return summary"""
        cleanup_summary = {
            'enrollments_deactivated': 0,
            'purchases_cancelled': 0,
            'payment_cards_removed': 0,
            'notifications_deleted': 0,
            'wishlist_items_removed': 0,
            'fcm_devices_removed': 0
        }
        
        try:
            # 1. Deactivate enrollments instead of deleting (for audit purposes)
            enrollments = Enrollment.objects.filter(user=user)
            enrollments_count = enrollments.count()
            enrollments.update(is_active=False)
            cleanup_summary['enrollments_deactivated'] = enrollments_count
            
            # 2. Mark purchases as cancelled
            purchases = Purchase.objects.filter(user=user)
            purchases_count = purchases.count()
            purchases.update(payment_status='CANCELLED')
            cleanup_summary['purchases_cancelled'] = purchases_count
            
            # 3. Remove payment cards
            payment_cards = PaymentCard.objects.filter(user=user)
            cleanup_summary['payment_cards_removed'] = payment_cards.count()
            payment_cards.delete()
            
            # 4. Delete notifications
            notifications = Notification.objects.filter(user=user)
            cleanup_summary['notifications_deleted'] = notifications.count()
            notifications.delete()
            
            # 5. Remove wishlist items
            wishlist_items = Wishlist.objects.filter(user=user)
            cleanup_summary['wishlist_items_removed'] = wishlist_items.count()
            wishlist_items.delete()
            
            # 6. Remove FCM devices
            fcm_devices = FCMDevice.objects.filter(user=user)
            cleanup_summary['fcm_devices_removed'] = fcm_devices.count()
            fcm_devices.delete()
            
            # 7. Mark payment orders as cancelled
            payment_orders = PaymentOrder.objects.filter(user=user)
            payment_orders.update(status='CANCELLED')
            
            # 8. Deactivate user subscriptions
            user_subscriptions = UserSubscription.objects.filter(user=user)
            user_subscriptions.update(is_active=False)
            
        except Exception as e:
            logger.error(f"Error during user data cleanup: {str(e)}")
            raise
        
        return cleanup_summary
    
    def _create_audit_log(self, admin_user, deleted_user, cleanup_summary):
        """Create audit log entry for account deletion"""
        try:
            # Create a notification for the admin as audit trail
            Notification.objects.create(
                user=admin_user,
                title="User Account Deleted",
                message=f"Admin {admin_user.email} deleted user account: {deleted_user.email} (ID: {deleted_user.id}). "
                       f"Cleanup: {cleanup_summary['enrollments_deactivated']} enrollments deactivated, "
                       f"{cleanup_summary['purchases_cancelled']} purchases cancelled.",
                notification_type='SYSTEM'
            )
            
            # Log the action
            logger.info(f"User account deleted - Admin: {admin_user.email}, "
                       f"Deleted User: {deleted_user.email} (ID: {deleted_user.id}), "
                       f"Cleanup Summary: {cleanup_summary}")
            
        except Exception as e:
            logger.error(f"Failed to create audit log: {str(e)}")


# Also create a bulk delete endpoint for multiple users
class AdminBulkDeleteUsersView(AdminCacheMixin, generics.CreateAPIView):
    """
    Admin API endpoint for bulk deletion of multiple user accounts.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    class InputSerializer(serializers.Serializer):
        user_ids = serializers.ListField(
            child=serializers.IntegerField(),
            min_length=1,
            max_length=50,  # Limit to prevent abuse
            help_text="List of user IDs to delete"
        )
        confirm_deletion = serializers.BooleanField(
            default=False,
            help_text="Must be set to true to confirm bulk deletion"
        )
        
        class Meta:
            ref_name = "AdminBulkDeleteUsersInputSerializer"
        
        def validate_confirm_deletion(self, value):
            if not value:
                raise serializers.ValidationError("Must confirm deletion by setting this to true")
            return value
    
    def get_serializer_class(self):
        return self.InputSerializer
    
    @swagger_auto_schema(
        operation_summary="Admin: Bulk delete user accounts",
        operation_description="""
        Admin-only endpoint for bulk deletion of multiple user accounts.
        Now includes comprehensive cache clearing.
        """
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user_ids = serializer.validated_data['user_ids']
        
        # CLEAR CACHES BEFORE BULK OPERATION
        self.clear_relevant_caches('bulk_operation', user_ids=user_ids)
        
        results = []
        successfully_deleted = 0
        failed_deletions = 0
        
        for user_id in user_ids:
            try:
                user_to_delete = User.objects.get(pk=user_id)
                
                # Skip admin users
                if user_to_delete.is_staff or user_to_delete.is_superuser:
                    results.append({
                        'user_id': user_id,
                        'status': 'skipped',
                        'email': user_to_delete.email,
                        'message': 'Admin user - skipped for safety'
                    })
                    failed_deletions += 1
                    continue
                
                # Skip if trying to delete self
                if user_to_delete.id == request.user.id:
                    results.append({
                        'user_id': user_id,
                        'status': 'skipped',
                        'email': user_to_delete.email,
                        'message': 'Cannot delete own account'
                    })
                    failed_deletions += 1
                    continue
                
                # Perform deletion
                with transaction.atomic():
                    email = user_to_delete.email
                    cleanup_summary = self._cleanup_user_data(user_to_delete)
                    user_to_delete.delete()
                
                results.append({
                    'user_id': user_id,
                    'status': 'success',
                    'email': email,
                    'message': 'User deleted successfully',
                    'cleanup_summary': cleanup_summary
                })
                successfully_deleted += 1
                
            except User.DoesNotExist:
                results.append({
                    'user_id': user_id,
                    'status': 'error',
                    'message': 'User not found'
                })
                failed_deletions += 1
                
            except Exception as e:
                results.append({
                    'user_id': user_id,
                    'status': 'error',
                    'message': str(e)
                })
                failed_deletions += 1
        
        # CLEAR ALL CACHES AFTER BULK OPERATION
        CacheManager.clear_admin_cache()
        CacheManager.clear_course_cache()
        
        return Response({
            "success": True,
            "data": {
                'total_requested': len(user_ids),
                'successfully_deleted': successfully_deleted,
                'failed_deletions': failed_deletions,
                'results': results,
                'cache_cleared': True
            }
        }, status=status.HTTP_200_OK)
    
    def _cleanup_user_data(self, user):
        """Same cleanup logic as single deletion"""
        admin_delete_view = AdminDeleteUserAccountView()
        return admin_delete_view._cleanup_user_data(user)
    
class AdminAllStudentsView(EnhancedAdminCacheMixin, generics.ListAPIView):
    """
    Admin API endpoint for retrieving ALL students (both enrolled and not enrolled) with their enrollment information.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
        
    @swagger_auto_schema(
        operation_summary="Admin: Get all students with enrollment status",
        operation_description="""
        Admin-only endpoint to get a comprehensive list of ALL students (both enrolled and not enrolled).
        
        **Returns detailed information including:**
        - Student basic information (email, name, phone, etc.)
        - Enrollment statistics for each student
        - Registration date and activity status
        - Total amount spent per student
        - Last enrollment date if applicable
        - Quick enrollment status overview
        
        **Use Cases:**
        - View all students in the system
        - Identify students who haven't enrolled yet
        - Monitor student activity and spending
        - Bulk enrollment operations
        - Marketing and outreach to non-enrolled students
        """,
        manual_parameters=[
            openapi.Parameter(
                'search', 
                openapi.IN_QUERY, 
                description="Search students by email, name, or phone", 
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'enrollment_status', 
                openapi.IN_QUERY, 
                description="Filter by enrollment status (enrolled, not_enrolled, active_enrolled, expired_enrolled)", 
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'is_active', 
                openapi.IN_QUERY, 
                description="Filter by account active status (true/false)", 
                type=openapi.TYPE_BOOLEAN
            ),
            openapi.Parameter(
                'date_joined_after', 
                openapi.IN_QUERY, 
                description="Filter students who joined after this date (YYYY-MM-DD)", 
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE
            ),
            openapi.Parameter(
                'date_joined_before', 
                openapi.IN_QUERY, 
                description="Filter students who joined before this date (YYYY-MM-DD)", 
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE
            ),
            openapi.Parameter(
                'min_spent', 
                openapi.IN_QUERY, 
                description="Filter students who spent minimum amount", 
                type=openapi.TYPE_NUMBER
            ),
            openapi.Parameter(
                'ordering', 
                openapi.IN_QUERY, 
                description="Order by field (date_joined, total_spent, enrollment_count, -date_joined, -total_spent, -enrollment_count)", 
                type=openapi.TYPE_STRING
            ),
        ],
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Students list with enrollment information",
                examples={
                    "application/json": {
                        "count": 150,
                        "next": "http://example.com/api/admin/all-students/?page=2",
                        "previous": None,
                        "results": [
                            {
                                "student": {
                                    "id": 123,
                                    "email": "student1@example.com",
                                    "full_name": "John Doe",
                                    "phone_number": "+1234567890",
                                    "date_of_birth": "1995-01-15",
                                    "is_active": True,
                                    "date_joined": "2024-12-01T10:30:00Z",
                                    "profile_picture_url": "https://example.com/profile.jpg"
                                },
                                "enrollment_info": {
                                    "is_enrolled": True,
                                    "total_enrollments": 3,
                                    "active_enrollments": 2,
                                    "expired_enrollments": 1,
                                    "total_spent": "599.00",
                                    "last_enrollment_date": "2025-01-15T10:30:00Z",
                                    "enrollment_status": "active_enrolled",
                                    "status_message": "Has 2 active enrollments"
                                },
                                "quick_stats": {
                                    "days_since_joined": 40,
                                    "days_since_last_enrollment": 5,
                                    "average_spent_per_course": "199.67",
                                    "is_recent_student": True
                                }
                            },
                            {
                                "student": {
                                    "id": 124,
                                    "email": "newstudent@example.com",
                                    "full_name": "Jane Smith",
                                    "phone_number": "+1234567891",
                                    "date_of_birth": "1998-03-20",
                                    "is_active": True,
                                    "date_joined": "2025-01-10T14:20:00Z",
                                    "profile_picture_url": None
                                },
                                "enrollment_info": {
                                    "is_enrolled": False,
                                    "total_enrollments": 0,
                                    "active_enrollments": 0,
                                    "expired_enrollments": 0,
                                    "total_spent": "0.00",
                                    "last_enrollment_date": None,
                                    "enrollment_status": "not_enrolled",
                                    "status_message": "No enrollments yet"
                                },
                                "quick_stats": {
                                    "days_since_joined": 10,
                                    "days_since_last_enrollment": None,
                                    "average_spent_per_course": "0.00",
                                    "is_recent_student": True
                                }
                            }
                        ]
                    }
                },
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'next': openapi.Schema(type=openapi.TYPE_STRING),
                        'previous': openapi.Schema(type=openapi.TYPE_STRING),
                        'results': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'student': openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'email': openapi.Schema(type=openapi.TYPE_STRING),
                                            'full_name': openapi.Schema(type=openapi.TYPE_STRING),
                                            'phone_number': openapi.Schema(type=openapi.TYPE_STRING),
                                            'date_of_birth': openapi.Schema(type=openapi.TYPE_STRING),
                                            'is_active': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                            'date_joined': openapi.Schema(type=openapi.TYPE_STRING),
                                            'profile_picture_url': openapi.Schema(type=openapi.TYPE_STRING)
                                        }
                                    ),
                                    'enrollment_info': openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'is_enrolled': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                            'total_enrollments': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'active_enrollments': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'expired_enrollments': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'total_spent': openapi.Schema(type=openapi.TYPE_STRING),
                                            'last_enrollment_date': openapi.Schema(type=openapi.TYPE_STRING),
                                            'enrollment_status': openapi.Schema(type=openapi.TYPE_STRING),
                                            'status_message': openapi.Schema(type=openapi.TYPE_STRING)
                                        }
                                    ),
                                    'quick_stats': openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'days_since_joined': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'days_since_last_enrollment': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'average_spent_per_course': openapi.Schema(type=openapi.TYPE_STRING),
                                            'is_recent_student': openapi.Schema(type=openapi.TYPE_BOOLEAN)
                                        }
                                    )
                                }
                            )
                        )
                    }
                )
            ),
            status.HTTP_403_FORBIDDEN: openapi.Response(
                description="Admin access required",
                examples={
                    "application/json": {
                        "detail": "You do not have permission to perform this action."
                    }
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        # Add caching for admin requests
        search = request.query_params.get('search', '')
        enrollment_status = request.query_params.get('enrollment_status', '')
        page = request.query_params.get('page', '1')
        
        # Generate cache key for admin queries
        cache_key_data = f"admin_all_students_v8_{search}_{enrollment_status}_{page}"
        cache_key = hashlib.md5(cache_key_data.encode()).hexdigest()
        
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        
        # OPTIMIZED query with minimal data loading
        students_query = User.objects.filter(
            is_staff=False,
            is_superuser=False
        ).select_related().only(
            'id', 'email', 'full_name', 'phone_number', 'date_of_birth', 
            'is_active', 'date_joined'
        )
        
        # Apply search filter efficiently
        if search:
            students_query = students_query.filter(
                Q(email__icontains=search) |
                Q(full_name__icontains=search) |
                Q(phone_number__icontains=search)
            )
        
        # Apply other filters...
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            is_active_bool = is_active.lower() == 'true'
            students_query = students_query.filter(is_active=is_active_bool)
        
        # OPTIMIZED: Add enrollment annotations directly in query
        students_query = students_query.annotate(
            total_enrollments=Count('enrollments'),
            active_enrollments=Count('enrollments', filter=Q(enrollments__is_active=True)),
            total_spent=Sum('enrollments__amount_paid', filter=Q(enrollments__is_active=True))
        )
        
        # Apply enrollment filters using annotations
        if enrollment_status:
            if enrollment_status == 'enrolled':
                students_query = students_query.filter(total_enrollments__gt=0)
            elif enrollment_status == 'not_enrolled':
                students_query = students_query.filter(total_enrollments=0)
            elif enrollment_status == 'active_enrolled':
                students_query = students_query.filter(active_enrollments__gt=0)
        
        min_spent = request.query_params.get('min_spent')
        if min_spent:
            try:
                min_spent_float = float(min_spent)
                students_query = students_query.filter(total_spent__gte=min_spent_float)
            except ValueError:
                pass
        
        # Optimize ordering
        ordering = request.query_params.get('ordering', '-date_joined')
        if ordering.lstrip('-') in ['total_spent', 'total_enrollments', 'date_joined']:
            students_query = students_query.order_by(ordering)
        
        # PAGINATION with limit
        students_query = students_query[:1000]  # Hard limit for admin queries
        
        # Build response efficiently
        students_data = []
        for student in students_query:
            student_data = {
                'student': {
                    'id': student.id,
                    'email': student.email,
                    'full_name': student.full_name,
                    'phone_number': student.phone_number,
                    'date_of_birth': student.date_of_birth,
                    'is_active': student.is_active,
                    'date_joined': student.date_joined,
                    'profile_picture_url': student.get_profile_picture_url()
                },
                'enrollment_info': {
                    'is_enrolled': student.total_enrollments > 0,
                    'total_enrollments': student.total_enrollments or 0,
                    'active_enrollments': student.active_enrollments or 0,
                    'expired_enrollments': (student.total_enrollments or 0) - (student.active_enrollments or 0),
                    'total_spent': f"{student.total_spent or 0:.2f}",
                    'enrollment_status': 'active_enrolled' if student.active_enrollments else ('enrolled' if student.total_enrollments else 'not_enrolled'),
                    'status_message': f"Has {student.active_enrollments or 0} active enrollments" if student.active_enrollments else ("No enrollments yet" if not student.total_enrollments else "All enrollments expired")
                }
            }
            students_data.append(student_data)
        
        # Manual pagination
        from django.core.paginator import Paginator
        paginator = Paginator(students_data, 25)
        page_number = request.query_params.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        response_data = {
            'count': paginator.count,
            'next': None,
            'previous': None,
            'results': page_obj.object_list,
            'cache_info': {
                'cached': False,
                'timestamp': timezone.now().isoformat()
            }
        }
        
        # Add pagination URLs
        if page_obj.has_next():
            response_data['next'] = f"{request.build_absolute_uri()}?page={page_obj.next_page_number()}"
        if page_obj.has_previous():
            response_data['previous'] = f"{request.build_absolute_uri()}?page={page_obj.previous_page_number()}"
        
        # Cache for 5 minutes (admin data changes less frequently)
        cache.set(cache_key, response_data, 300)
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    def _calculate_enrollment_info(self, student):
        """Calculate enrollment information for a student"""
        enrollments = list(student.enrollments.all())
        
        total_enrollments = len(enrollments)
        active_enrollments = 0
        expired_enrollments = 0
        total_spent = 0
        last_enrollment_date = None
        
        for enrollment in enrollments:
            total_spent += float(enrollment.amount_paid)
            
            if enrollment.is_active and not enrollment.is_expired:
                active_enrollments += 1
            else:
                expired_enrollments += 1
            
            if last_enrollment_date is None or enrollment.date_enrolled > last_enrollment_date:
                last_enrollment_date = enrollment.date_enrolled
        
        # Determine enrollment status
        if total_enrollments == 0:
            enrollment_status = 'not_enrolled'
            status_message = 'No enrollments yet'
        elif active_enrollments > 0:
            enrollment_status = 'active_enrolled'
            status_message = f'Has {active_enrollments} active enrollment{"s" if active_enrollments > 1 else ""}'
        elif expired_enrollments > 0:
            enrollment_status = 'expired_enrolled'
            status_message = f'All {expired_enrollments} enrollment{"s" if expired_enrollments > 1 else ""} expired'
        else:
            enrollment_status = 'inactive_enrolled'
            status_message = 'Has inactive enrollments'
        
        return {
            'is_enrolled': total_enrollments > 0,
            'total_enrollments': total_enrollments,
            'active_enrollments': active_enrollments,
            'expired_enrollments': expired_enrollments,
            'total_spent': f"{total_spent:.2f}",
            'last_enrollment_date': last_enrollment_date,
            'enrollment_status': enrollment_status,
            'status_message': status_message
        }
    
    def _calculate_quick_stats(self, student, enrollment_info):
        """Calculate quick statistics for a student"""
        from django.utils import timezone
        
        now = timezone.now()
        days_since_joined = (now - student.date_joined).days
        
        days_since_last_enrollment = None
        if enrollment_info['last_enrollment_date']:
            days_since_last_enrollment = (now - enrollment_info['last_enrollment_date']).days
        
        # Calculate average spent per course
        total_spent = float(enrollment_info['total_spent'])
        total_enrollments = enrollment_info['total_enrollments']
        average_spent_per_course = total_spent / total_enrollments if total_enrollments > 0 else 0
        
        # Determine if student is recent (joined within last 30 days)
        is_recent_student = days_since_joined <= 30
        
        return {
            'days_since_joined': days_since_joined,
            'days_since_last_enrollment': days_since_last_enrollment,
            'average_spent_per_course': f"{average_spent_per_course:.2f}",
            'is_recent_student': is_recent_student
        }
class AdminMetricsView(generics.GenericAPIView):
    """
    API endpoint for retrieving admin dashboard metrics.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminMetricsSerializer
    
    @swagger_auto_schema(
        operation_summary="Get admin dashboard metrics",
        operation_description="Retrieves key metrics for the admin dashboard including total courses, students, and revenue",
        manual_parameters=[
            openapi.Parameter(
                'time_period', 
                openapi.IN_QUERY, 
                description="Time period for graph data (week, month, year)", 
                type=openapi.TYPE_STRING,
                default='month'
            ),
        ],
        responses={
            status.HTTP_200_OK: AdminMetricsSerializer,
            status.HTTP_401_UNAUTHORIZED: 'Unauthorized access',
            status.HTTP_403_FORBIDDEN: 'Permission denied',
        }
    )
    def get(self, request):
        # Get time period from query parameters (default to month)
        time_period = request.query_params.get('time_period', 'month')
        
        # Basic metrics
        total_courses = Course.objects.count()
        total_students = User.objects.filter(is_staff=False, is_superuser=False).count()
        total_revenue = Purchase.objects.aggregate(total=Sum('amount'))['total'] or 0
        
        # Prepare data for student registration graph
        now = timezone.now()
        
        # Set the date range based on time_period
        if time_period == 'week':
            start_date = now - timedelta(days=7)
            date_trunc = TruncDate('date_joined')
            date_format = '%Y-%m-%d'
        elif time_period == 'year':
            start_date = now - timedelta(days=365)
            date_trunc = TruncMonth('date_joined')
            date_format = '%Y-%m'
        else:  # Default to month
            start_date = now - timedelta(days=30)
            date_trunc = TruncDate('date_joined')
            date_format = '%Y-%m-%d'
        
        # Query for new registrations
        registrations = User.objects.filter(
            date_joined__gte=start_date,
            is_staff=False,
            is_superuser=False
        ).annotate(
            date=date_trunc
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        # Format for the graph
        registration_data = {
            'labels': [],
            'data': []
        }
        
        # Create a dictionary for quick lookup
        reg_dict = {reg['date'].strftime(date_format): reg['count'] for reg in registrations}
        
        # Fill in all dates in the range
        current_date = start_date
        while current_date <= now:
            date_str = current_date.strftime(date_format)
            registration_data['labels'].append(date_str)
            registration_data['data'].append(reg_dict.get(date_str, 0))
            
            if time_period == 'year':
                current_date += timedelta(days=30)  # Approximate for month
            else:
                current_date += timedelta(days=1)
        
        # Course popularity data
        course_popularity = Course.objects.annotate(
            student_count=Count('enrollments')
        ).order_by('-student_count')[:10]
        
        course_popularity_data = CourseListSerializer(
            course_popularity, 
            many=True, 
            context={'request': request}
        ).data
        
        # Prepare the response
        response_data = {
            'total_courses': total_courses,
            'total_students': total_students,
            'total_revenue': total_revenue,
            'student_registration_data': registration_data,
            'course_popularity': course_popularity_data
        }
        
        # serializer = self.get_serializer(data=response_data)
        # serializer.is_valid()  # Always valid as we're setting read-only fields
        
        return Response(response_data, status=status.HTTP_200_OK)

class ContentPageViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing privacy policy and terms & conditions.
    """
    queryset = ContentPage.objects.all()
    serializer_class = ContentPageSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_default_content(self, page_type):
        """
        Get default content for a content page type
        """
        if page_type == 'PRIVACY':
            return """
# Privacy Policy

## Introduction
Welcome to our Privacy Policy. This document explains how we collect, use, and protect your personal information.

## Information We Collect
- Personal information such as name, email address, and phone number
- Usage data such as course progress and login times
- Payment information when you make a purchase

## How We Use Your Information
- To provide and maintain our service
- To notify you about changes to our service
- To provide customer support
- To gather analysis or valuable information so that we can improve our service

## Data Security
We implement appropriate security measures to protect your personal information.

## Your Rights
You have the right to access, update, or delete your personal information.

## Changes to This Privacy Policy
We may update our Privacy Policy from time to time. We will notify you of any changes by posting the new Privacy Policy on this page.

## Contact Us
If you have any questions about this Privacy Policy, please contact us.
            """
        elif page_type == 'TERMS':
            return """
# Terms and Conditions

## Introduction
These Terms and Conditions govern your use of our service and website.

## Acceptance of Terms
By accessing or using our service, you agree to be bound by these Terms.

## User Accounts
- You are responsible for maintaining the security of your account
- You are responsible for all activities that occur under your account
- You must notify us immediately of any breach of security or unauthorized use of your account

## Course Content
- All content provided on our platform is for educational purposes only
- You may not reproduce, distribute, or create derivative works from our content
- We reserve the right to modify or discontinue any course without notice

## Payment Terms
- All fees are non-refundable unless stated otherwise
- We reserve the right to change our fees at any time

## Limitation of Liability
We will not be liable for any indirect, incidental, special, or consequential damages.

## Governing Law
These Terms shall be governed and construed in accordance with the laws of [Your Country].

## Changes to Terms
We reserve the right to modify or replace these Terms at any time.

## Contact Us
If you have any questions about these Terms, please contact us.
            """
        else:
            return ""
    
    @swagger_auto_schema(
        operation_summary="Get privacy policy or terms & conditions",
        operation_description="Retrieves the privacy policy or terms & conditions content",
        manual_parameters=[
            openapi.Parameter(
                'page_type', 
                openapi.IN_QUERY, 
                description="Page type (PRIVACY, TERMS)", 
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            status.HTTP_200_OK: ContentPageSerializer,
            status.HTTP_404_NOT_FOUND: 'Content not found',
        }
    )
    def retrieve(self, request, pk=None):
        page_type = request.query_params.get('page_type')
        if not page_type:
            return Response(
                {"error": "page_type query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to get existing content or create one with default content
        try:
            content_page = ContentPage.objects.get(page_type=page_type)
        except ContentPage.DoesNotExist:
            # Only create default content for admins
            if request.user.is_staff:
                content_page = ContentPage.objects.create(
                    page_type=page_type,
                    content=self.get_default_content(page_type)
                )
            else:
                return Response(
                    {"error": f"Content for {page_type} not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        serializer = self.get_serializer(content_page)
        return Response(serializer.data)
    
    
class GeneralSettingsView(generics.RetrieveUpdateAPIView):
    """
    API endpoint for retrieving and updating general settings.
    """
    serializer_class = GeneralSettingsSerializer
    
    def get_object(self):
        # Get the settings object or create a default one if it doesn't exist
        return GeneralSettings.get_settings()
    
    def get_permissions(self):
        """
        Allow anyone to retrieve settings, but only admin users can update.
        """
        if self.request.method in ['PUT', 'PATCH']:
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]
    
    @swagger_auto_schema(
        operation_summary="Get general settings",
        operation_description="Retrieves the general settings for the application",
        responses={
            status.HTTP_200_OK: GeneralSettingsSerializer,
        }
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Update general settings",
        operation_description="Updates the general settings for the application",
        request_body=GeneralSettingsSerializer,
        responses={
            status.HTTP_200_OK: GeneralSettingsSerializer,
            status.HTTP_400_BAD_REQUEST: 'Invalid data',
            status.HTTP_401_UNAUTHORIZED: 'Unauthorized access',
            status.HTTP_403_FORBIDDEN: 'Permission denied',
        }
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Partially update general settings",
        operation_description="Partially updates the general settings for the application",
        request_body=GeneralSettingsSerializer,
        responses={
            status.HTTP_200_OK: GeneralSettingsSerializer,
            status.HTTP_400_BAD_REQUEST: 'Invalid data',
            status.HTTP_401_UNAUTHORIZED: 'Unauthorized access',
            status.HTTP_403_FORBIDDEN: 'Permission denied',
        }
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

# Public version of ContentPageView for retrieving content
class PublicContentPageView(generics.RetrieveAPIView):
    """
    API endpoint for retrieving privacy policy and terms & conditions (public).
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = ContentPageSerializer
    
    def get_default_content(self, page_type):
        """
        Get default content for a content page type
        """
        if page_type == 'PRIVACY':
            return """
# Privacy Policy

## Introduction
Welcome to our Privacy Policy. This document explains how we collect, use, and protect your personal information.

## Information We Collect
- Personal information such as name, email address, and phone number
- Usage data such as course progress and login times
- Payment information when you make a purchase

## How We Use Your Information
- To provide and maintain our service
- To notify you about changes to our service
- To provide customer support
- To gather analysis or valuable information so that we can improve our service

## Data Security
We implement appropriate security measures to protect your personal information.

## Your Rights
You have the right to access, update, or delete your personal information.

## Changes to This Privacy Policy
We may update our Privacy Policy from time to time. We will notify you of any changes by posting the new Privacy Policy on this page.

## Contact Us
If you have any questions about this Privacy Policy, please contact us.
            """
        elif page_type == 'TERMS':
            return """
# Terms and Conditions

## Introduction
These Terms and Conditions govern your use of our service and website.

## Acceptance of Terms
By accessing or using our service, you agree to be bound by these Terms.

## User Accounts
- You are responsible for maintaining the security of your account
- You are responsible for all activities that occur under your account
- You must notify us immediately of any breach of security or unauthorized use of your account

## Course Content
- All content provided on our platform is for educational purposes only
- You may not reproduce, distribute, or create derivative works from our content
- We reserve the right to modify or discontinue any course without notice

## Payment Terms
- All fees are non-refundable unless stated otherwise
- We reserve the right to change our fees at any time

## Limitation of Liability
We will not be liable for any indirect, incidental, special, or consequential damages.

## Governing Law
These Terms shall be governed and construed in accordance with the laws of [Your Country].

## Changes to Terms
We reserve the right to modify or replace these Terms at any time.

## Contact Us
If you have any questions about these Terms, please contact us.
            """
        else:
            return ""
    
    @swagger_auto_schema(
        operation_summary="Get privacy policy or terms & conditions",
        operation_description="Retrieves the privacy policy or terms & conditions content (public access)",
        manual_parameters=[
            openapi.Parameter(
                'page_type', 
                openapi.IN_QUERY, 
                description="Page type (PRIVACY, TERMS)", 
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            status.HTTP_200_OK: ContentPageSerializer,
            status.HTTP_404_NOT_FOUND: 'Content not found',
        }
    )
    def get(self, request):
        page_type = request.query_params.get('page_type')
        if not page_type:
            return Response(
                {"error": "page_type query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            content_page = ContentPage.objects.get(page_type=page_type)
        except ContentPage.DoesNotExist:
            # Create content page with default content if it doesn't exist
            content_page = ContentPage.objects.create(
                page_type=page_type,
                content=self.get_default_content(page_type)
            )
        
        serializer = self.get_serializer(content_page)
        return Response(serializer.data)
            
class UserListView(generics.ListAPIView):
    """
    API endpoint for retrieving all users.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = UserDetailsSerializer
    queryset = User.objects.all()
    
    @swagger_auto_schema(
        operation_summary="Get all users",
        operation_description="Retrieves a list of all users registered in the system",
        manual_parameters=[
            openapi.Parameter(
                'search', 
                openapi.IN_QUERY, 
                description="Search users by email, full name, or phone number", 
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'is_staff', 
                openapi.IN_QUERY, 
                description="Filter by staff status (true/false)", 
                type=openapi.TYPE_BOOLEAN
            ),
            openapi.Parameter(
                'is_active', 
                openapi.IN_QUERY, 
                description="Filter by active status (true/false)", 
                type=openapi.TYPE_BOOLEAN
            ),
        ],
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="List of users",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'email': openapi.Schema(type=openapi.TYPE_STRING),
                            'full_name': openapi.Schema(type=openapi.TYPE_STRING),
                            'phone_number': openapi.Schema(type=openapi.TYPE_STRING),
                            'date_of_birth': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
                        }
                    )
                )
            ),
        }
    )
    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Apply filters based on query parameters
        search = request.query_params.get('search', None)
        is_staff = request.query_params.get('is_staff', None)
        is_active = request.query_params.get('is_active', None)
        
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search) | 
                Q(full_name__icontains=search) | 
                Q(phone_number__icontains=search)
            )
            
        if is_staff is not None:
            is_staff_bool = is_staff.lower() == 'true'
            queryset = queryset.filter(is_staff=is_staff_bool)
            
        if is_active is not None:
            is_active_bool = is_active.lower() == 'true'
            queryset = queryset.filter(is_active=is_active_bool)
        
        # Order by most recent first
        queryset = queryset.order_by('-date_joined')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class EnrolledStudentsListView(generics.ListAPIView):
    """
    API endpoint for retrieving all enrolled students.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = UserDetailsSerializer
    
    @swagger_auto_schema(
        operation_summary="Get all enrolled students",
        operation_description="Retrieves a list of all students who have enrolled in at least one course",
        manual_parameters=[
            openapi.Parameter(
                'search', 
                openapi.IN_QUERY, 
                description="Search students by email, full name, or phone number", 
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'course_id', 
                openapi.IN_QUERY, 
                description="Filter by specific course ID", 
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'min_courses', 
                openapi.IN_QUERY, 
                description="Filter by minimum number of enrolled courses", 
                type=openapi.TYPE_INTEGER
            ),
        ],
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="List of enrolled students",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'email': openapi.Schema(type=openapi.TYPE_STRING),
                            'full_name': openapi.Schema(type=openapi.TYPE_STRING),
                            'phone_number': openapi.Schema(type=openapi.TYPE_STRING),
                            'date_of_birth': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
                            'enrolled_courses_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                        }
                    )
                )
            ),
        }
    )
    def get(self, request, *args, **kwargs):
        # Get all students (non-staff users) who have enrolled in at least one course
        # Annotate with the count of enrolled courses
        queryset = User.objects.filter(
            is_staff=False, 
            is_superuser=False,
            enrollments__isnull=False
        ).distinct().annotate(
            enrolled_courses_count=Count('enrollments')
        )
        
        # Apply filters based on query parameters
        search = request.query_params.get('search', None)
        course_id = request.query_params.get('course_id', None)
        min_courses = request.query_params.get('min_courses', None)
        
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search) | 
                Q(full_name__icontains=search) | 
                Q(phone_number__icontains=search)
            )
            
        if course_id:
            queryset = queryset.filter(enrollments__course_id=course_id)
            
        if min_courses:
            try:
                min_courses_int = int(min_courses)
                queryset = queryset.filter(enrolled_courses_count__gte=min_courses_int)
            except ValueError:
                pass
        
        # Order by most active students first (most enrolled courses)
        queryset = queryset.order_by('-enrolled_courses_count', 'full_name')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            # Add the enrolled_courses_count to each user in the response
            for user_data, user_obj in zip(serializer.data, page):
                user_data['enrolled_courses_count'] = user_obj.enrolled_courses_count
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        # Add the enrolled_courses_count to each user in the response
        for user_data, user_obj in zip(serializer.data, queryset):
            user_data['enrolled_courses_count'] = user_obj.enrolled_courses_count
        
        return Response(serializer.data)


class ContentPageMixin:
    """
    Mixin to provide default content for content pages
    """
    def get_default_content(self, page_type):
        """
        Get default content for a content page type
        """
        if page_type == 'PRIVACY':
            return """
# Privacy Policy

## Introduction
Welcome to our Privacy Policy. This document explains how we collect, use, and protect your personal information.

## Information We Collect
- Personal information such as name, email address, and phone number
- Usage data such as course progress and login times
- Payment information when you make a purchase

## How We Use Your Information
- To provide and maintain our service
- To notify you about changes to our service
- To provide customer support
- To gather analysis or valuable information so that we can improve our service

## Data Security
We implement appropriate security measures to protect your personal information.

## Your Rights
You have the right to access, update, or delete your personal information.

## Changes to This Privacy Policy
We may update our Privacy Policy from time to time. We will notify you of any changes by posting the new Privacy Policy on this page.

## Contact Us
If you have any questions about this Privacy Policy, please contact us.
            """
        elif page_type == 'TERMS':
            return """
# Terms and Conditions

## Introduction
These Terms and Conditions govern your use of our service and website.

## Acceptance of Terms
By accessing or using our service, you agree to be bound by these Terms.

## User Accounts
- You are responsible for maintaining the security of your account
- You are responsible for all activities that occur under your account
- You must notify us immediately of any breach of security or unauthorized use of your account

## Course Content
- All content provided on our platform is for educational purposes only
- You may not reproduce, distribute, or create derivative works from our content
- We reserve the right to modify or discontinue any course without notice

## Payment Terms
- All fees are non-refundable unless stated otherwise
- We reserve the right to change our fees at any time

## Limitation of Liability
We will not be liable for any indirect, incidental, special, or consequential damages.

## Governing Law
These Terms shall be governed and construed in accordance with the laws of [Your Country].

## Changes to Terms
We reserve the right to modify or replace these Terms at any time.

## Contact Us
If you have any questions about these Terms, please contact us.
            """
        else:
            return ""

    def get_or_create_content_page(self, page_type, create_if_missing=True):
        """
        Get content page or create with default content if it doesn't exist
        """
        from .models import ContentPage
        
        try:
            content_page = ContentPage.objects.get(page_type=page_type)
            return content_page, False
        except ContentPage.DoesNotExist:
            if create_if_missing:
                content_page = ContentPage.objects.create(
                    page_type=page_type,
                    content=self.get_default_content(page_type)
                )
                return content_page, True
            return None, False

# Then update your view classes to use this mixin:

class ContentPageViewSet(ContentPageMixin, viewsets.ModelViewSet):
    """
    API endpoints for managing privacy policy and terms & conditions.
    """
    queryset = ContentPage.objects.all()
    serializer_class = ContentPageSerializer
    permission_classes = [permissions.IsAdminUser]
    
    @swagger_auto_schema(
        operation_summary="Get privacy policy or terms & conditions",
        operation_description="Retrieves the privacy policy or terms & conditions content",
        manual_parameters=[
            openapi.Parameter(
                'page_type', 
                openapi.IN_QUERY, 
                description="Page type (PRIVACY, TERMS)", 
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            status.HTTP_200_OK: ContentPageSerializer,
            status.HTTP_404_NOT_FOUND: 'Content not found',
        }
    )
    def retrieve(self, request, pk=None):
        page_type = request.query_params.get('page_type')
        if not page_type:
            return Response(
                {"error": "page_type query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to get existing content or create one with default content if user is admin
        content_page, created = self.get_or_create_content_page(
            page_type, 
            create_if_missing=request.user.is_staff
        )
        
        if not content_page:
            return Response(
                {"error": f"Content for {page_type} not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.get_serializer(content_page)
        return Response(serializer.data)

class PublicContentPageView(ContentPageMixin, generics.RetrieveAPIView):
    """
    API endpoint for retrieving privacy policy and terms & conditions (public).
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = ContentPageSerializer
    
    @swagger_auto_schema(
        operation_summary="Get privacy policy or terms & conditions",
        operation_description="Retrieves the privacy policy or terms & conditions content (public access)",
        manual_parameters=[
            openapi.Parameter(
                'page_type', 
                openapi.IN_QUERY, 
                description="Page type (PRIVACY, TERMS)", 
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            status.HTTP_200_OK: ContentPageSerializer,
            status.HTTP_404_NOT_FOUND: 'Content not found',
        }
    )
    def get(self, request):
        page_type = request.query_params.get('page_type')
        if not page_type:
            return Response(
                {"error": "page_type query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to get existing content or create one with default content
        content_page, created = self.get_or_create_content_page(page_type)
        
        serializer = self.get_serializer(content_page)
        return Response(serializer.data)
    
    
class AdminAddStudentToPlanView(EnhancedAdminCacheMixin, generics.CreateAPIView):
    """
    Admin API endpoint for manually adding a student to a subscription plan.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    class InputSerializer(serializers.Serializer):
        user_id = serializers.IntegerField()
        course_id = serializers.IntegerField()
        plan_type = serializers.ChoiceField(choices=CoursePlanType.choices)
        amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
        payment_card_id = serializers.IntegerField(required=False, allow_null=True)
        notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
        
        class Meta:
            ref_name = "AdminAddStudentInputSerializer"
        
        def validate_user_id(self, value):
            try:
                User.objects.get(pk=value)
                return value
            except User.DoesNotExist:
                raise serializers.ValidationError("User does not exist")
        
        def validate_course_id(self, value):
            try:
                Course.objects.get(pk=value)
                return value
            except Course.DoesNotExist:
                raise serializers.ValidationError("Course does not exist")
    
    def get_serializer_class(self):
        return self.InputSerializer
    
    @swagger_auto_schema(
        operation_summary="Admin: Add student to subscription plan",
        operation_description="""
        Admin-only endpoint to manually add a student to a course subscription plan.
        Includes comprehensive cache clearing for immediate UI updates.
        """
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Extract validated data
        user_id = serializer.validated_data['user_id']
        course_id = serializer.validated_data['course_id']
        plan_type = serializer.validated_data['plan_type']
        payment_card_id = serializer.validated_data.get('payment_card_id')
        notes = serializer.validated_data.get('notes', '')
        
        try:
            # Get objects
            user = User.objects.get(pk=user_id)
            course = Course.objects.get(pk=course_id)
            
            # Get payment card if provided
            payment_card = None
            if payment_card_id:
                try:
                    payment_card = PaymentCard.objects.get(pk=payment_card_id)
                    if payment_card.user != user:
                        return Response(
                            {'error': 'Payment card does not belong to the specified user'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                except PaymentCard.DoesNotExist:
                    return Response(
                        {'error': 'Payment card not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            # Calculate amount based on plan type if not provided
            amount_paid = serializer.validated_data.get('amount_paid')
            if not amount_paid:
                if plan_type == CoursePlanType.ONE_MONTH:
                    amount_paid = course.price_one_month
                elif plan_type == CoursePlanType.THREE_MONTHS:
                    amount_paid = course.price_three_months
                elif plan_type == CoursePlanType.LIFETIME:
                    amount_paid = course.price_lifetime
                else:
                    amount_paid = Decimal('0.00')
            
            with transaction.atomic():
                result = self._process_admin_enrollment(
                    admin_user=request.user,
                    user=user,
                    course=course,
                    plan_type=plan_type,
                    amount_paid=amount_paid,
                    payment_card=payment_card,
                    notes=notes
                )
                self.clear_caches_after_operation(
                    operation_type='user_enrollment',
                    user_id=user_id,
                    course_id=course_id,
                    action='add'
                )
                # CLEAR CACHES IMMEDIATELY AFTER ENROLLMENT
                self.clear_relevant_caches('user_enroll', user_id=user_id, course_id=course_id)
            
            # Prepare response data
            response_data = {
                'message': result['message'],
                'purchase': {
                    'id': result['purchase'].id,
                    'transaction_id': result['purchase'].transaction_id,
                    'amount': result['purchase'].amount,
                    'payment_status': result['purchase'].payment_status
                },
                'enrollment': {
                    'id': result['enrollment'].id,
                    'plan_type': result['enrollment'].plan_type,
                    'plan_name': result['enrollment'].get_plan_type_display(),
                    'expiry_date': result['enrollment'].expiry_date,
                    'is_active': result['enrollment'].is_active
                },
                'payment_order_id': result['payment_order'].id,
                'admin_action': True,
                'added_by': request.user.email,
                'cache_cleared': True
            }
            
            return Response({"success": True, "data": response_data}, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Admin enrollment failed: {str(e)}")
            return Response(
                {'error': 'Enrollment failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def _process_admin_enrollment(self, admin_user, user, course, plan_type, amount_paid, payment_card=None, notes=''):
        """Process admin enrollment with comprehensive data creation"""
        # Generate mock transaction ID
        transaction_id = f"ADMIN_{uuid.uuid4().hex[:12].upper()}"
        mock_order_id = f"order_admin_{uuid.uuid4().hex[:10]}"
        mock_payment_id = f"pay_admin_{uuid.uuid4().hex[:10]}"
        
        # Create or update PaymentOrder
        payment_order, created = PaymentOrder.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                'amount': amount_paid,
                'razorpay_order_id': mock_order_id,
                'razorpay_payment_id': mock_payment_id,
                'razorpay_signature': f"admin_signature_{uuid.uuid4().hex[:16]}",
                'status': 'PAID'
            }
        )
        
        if not created:
            payment_order.razorpay_payment_id = mock_payment_id
            payment_order.status = 'PAID'
            payment_order.save()
        
        # Create Purchase record
        purchase = Purchase.objects.create(
            user=user,
            course=course,
            plan_type=plan_type,
            amount=amount_paid,
            transaction_id=transaction_id,
            razorpay_order_id=mock_order_id,
            razorpay_payment_id=mock_payment_id,
            payment_status='COMPLETED',
            payment_card=payment_card
        )
        
        # Create or update Enrollment
        enrollment, enrollment_created = Enrollment.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                'plan_type': plan_type,
                'amount_paid': amount_paid,
                'is_active': True
            }
        )
        
        if not enrollment_created:
            enrollment.plan_type = plan_type
            enrollment.amount_paid = amount_paid
            enrollment.is_active = True
            enrollment.save()
        
        # Set expiry date
        if plan_type == CoursePlanType.ONE_MONTH:
            enrollment.expiry_date = timezone.now() + timezone.timedelta(days=30)
        elif plan_type == CoursePlanType.THREE_MONTHS:
            enrollment.expiry_date = timezone.now() + timezone.timedelta(days=90)
        elif plan_type == CoursePlanType.LIFETIME:
            enrollment.expiry_date = None
        
        enrollment.save()
        
        # Create notifications
        Notification.objects.create(
            user=user,
            title="Course Access Granted",
            message=f"You have been enrolled in '{course.title}' ({enrollment.get_plan_type_display()} plan) by admin.",
            notification_type='COURSE'
        )
        
        Notification.objects.create(
            user=admin_user,
            title="Student Enrolled",
            message=f"Successfully enrolled {user.email} in '{course.title}' ({enrollment.get_plan_type_display()}). Notes: {notes}",
            notification_type='SYSTEM'
        )
        
        return {
            'message': f"Successfully enrolled {user.email} in {course.title} ({enrollment.get_plan_type_display()})",
            'purchase': purchase,
            'enrollment': enrollment,
            'payment_order': payment_order
        }
class AdminRemoveStudentFromPlanView(AdminCacheMixin, generics.DestroyAPIView):
    """Admin API endpoint for removing a student from a course subscription plan."""
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    class InputSerializer(serializers.Serializer):
        user_id = serializers.IntegerField()
        course_id = serializers.IntegerField()
        reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
        refund_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
        
        class Meta:
            ref_name = "AdminRemoveStudentInputSerializer"
    
    def get_serializer_class(self):
        return self.InputSerializer
    
    @swagger_auto_schema(
        operation_summary="Admin: Remove student from subscription plan",
        operation_description="Remove student from course with immediate cache clearing."
    )
    def delete(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user_id = serializer.validated_data['user_id']
        course_id = serializer.validated_data['course_id']
        reason = serializer.validated_data.get('reason', '')
        refund_amount = serializer.validated_data.get('refund_amount')
        
        try:
            user = User.objects.get(pk=user_id)
            course = Course.objects.get(pk=course_id)
            
            try:
                enrollment = Enrollment.objects.get(user=user, course=course, is_active=True)
            except Enrollment.DoesNotExist:
                return Response(
                    {'error': 'No active enrollment found for this user and course'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            with transaction.atomic():
                result = self._process_admin_removal(
                    admin_user=request.user,
                    user=user,
                    course=course,
                    enrollment=enrollment,
                    reason=reason,
                    refund_amount=refund_amount
                )
                
                # CLEAR CACHES IMMEDIATELY
                self.clear_relevant_caches('user_enroll', user_id=user_id, course_id=course_id)
            
            response_data = {
                'message': result['message'],
                'enrollment_id': enrollment.id,
                'deactivated_at': timezone.now().isoformat(),
                'refund_processed': refund_amount is not None,
                'refund_amount': str(refund_amount) if refund_amount else None,
                'admin_action': True,
                'removed_by': request.user.email,
                'reason': reason,
                'cache_cleared': True
            }
            
            return Response({"success": True, "data": response_data}, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Admin removal failed: {str(e)}")
            return Response(
                {'error': 'Removal failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def _process_admin_removal(self, admin_user, user, course, enrollment, reason='', refund_amount=None):
        """Process admin removal with proper record updates"""
        # Deactivate the enrollment
        enrollment.is_active = False
        enrollment.save()
        
        # Update purchase records if refund is processed
        if refund_amount is not None:
            purchases = Purchase.objects.filter(user=user, course=course, payment_status='COMPLETED')
            for purchase in purchases:
                purchase.payment_status = 'REFUNDED'
                purchase.save()
        
        # Create notifications
        refund_message = f" A refund of ${refund_amount} has been processed." if refund_amount else ""
        reason_message = f" Reason: {reason}" if reason else ""
        
        Notification.objects.create(
            user=user,
            title="Course Access Removed",
            message=f"Your access to '{course.title}' has been removed by admin.{refund_message}{reason_message}",
            notification_type='COURSE'
        )
        
        return {'message': f"Successfully removed {user.email} from {course.title}"}


# Update your CourseViewSet as well
class EnhancedCourseViewSet(AdminCacheMixin, viewsets.ModelViewSet):
    """Enhanced CourseViewSet with proper cache clearing"""
    
    def create(self, request, *args, **kwargs):
        """Clear caches after course creation"""
        result = super().create(request, *args, **kwargs)
        
        # Clear relevant caches
        self.clear_relevant_caches('course_create')
        
        return result
    
    def update(self, request, *args, **kwargs):
        """Clear caches after course update"""
        course_id = kwargs.get('pk')
        result = super().update(request, *args, **kwargs)
        
        # Clear relevant caches
        self.clear_relevant_caches('course_update', course_id=course_id)
        
        return result
    
    def destroy(self, request, *args, **kwargs):
        """Clear caches after course deletion"""
        course_id = kwargs.get('pk')
        result = super().destroy(request, *args, **kwargs)
        
        # Clear relevant caches
        self.clear_relevant_caches('course_delete', course_id=course_id)
        
        return result

class AdminBulkEnrollmentOperationsView(generics.CreateAPIView):
    """
    Admin API for bulk enrollment operations (add/remove multiple students)
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    class InputSerializer(serializers.Serializer):
        operation = serializers.ChoiceField(choices=['add', 'remove'])
        enrollments = serializers.ListField(
            child=serializers.DictField(),
            min_length=1,
            max_length=100  # Limit to prevent abuse
        )
        
        class Meta:
            ref_name = "AdminBulkEnrollmentInputSerializer"
        
        def validate_enrollments(self, value):
            """Validate each enrollment entry"""
            for enrollment in value:
                if 'user_id' not in enrollment or 'course_id' not in enrollment:
                    raise serializers.ValidationError("Each enrollment must have user_id and course_id")
                
                # For add operations, plan_type is required
                if self.initial_data.get('operation') == 'add' and 'plan_type' not in enrollment:
                    raise serializers.ValidationError("plan_type is required for add operations")
            
            return value
    
    def get_serializer_class(self):
        return self.InputSerializer
    
    @swagger_auto_schema(
        operation_summary="Admin: Bulk enrollment operations",
        operation_description="""
        Admin-only endpoint for bulk enrollment operations.
        
        **Add Operation:**
        - Adds multiple students to courses
        - Each entry needs: user_id, course_id, plan_type
        - Optional: amount_paid, notes
        
        **Remove Operation:**
        - Removes multiple students from courses
        - Each entry needs: user_id, course_id
        - Optional: reason, refund_amount
        """,
        request_body=InputSerializer,
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Bulk operation completed",
                examples={
                    "application/json": {
                        "success": True,
                        "data": {
                            "operation": "add",
                            "total_processed": 3,
                            "successful": 2,
                            "failed": 1,
                            "results": [
                                {
                                    "index": 0,
                                    "status": "success",
                                    "message": "Added user1@example.com to Course Title",
                                    "data": {
                                        "enrollment_id": 123,
                                        "user_id": 1,
                                        "course_id": 10
                                    }
                                },
                                {
                                    "index": 1,
                                    "status": "success", 
                                    "message": "Added user2@example.com to Course Title",
                                    "data": {
                                        "enrollment_id": 124,
                                        "user_id": 2,
                                        "course_id": 10
                                    }
                                },
                                {
                                    "index": 2,
                                    "status": "error",
                                    "message": "User does not exist",
                                    "data": {
                                        "user_id": 999,
                                        "course_id": 10
                                    }
                                }
                            ]
                        }
                    }
                },
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'operation': openapi.Schema(type=openapi.TYPE_STRING),
                                'total_processed': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'successful': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'failed': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'results': openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'index': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'status': openapi.Schema(type=openapi.TYPE_STRING),
                                            'message': openapi.Schema(type=openapi.TYPE_STRING),
                                            'data': openapi.Schema(type=openapi.TYPE_OBJECT)
                                        }
                                    )
                                )
                            }
                        )
                    }
                )
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Invalid request data",
                examples={
                    "application/json": {
                        "error": "Invalid operation type",
                        "details": "Operation must be 'add' or 'remove'"
                    }
                }
            ),
            status.HTTP_403_FORBIDDEN: openapi.Response(
                description="Admin access required",
                examples={
                    "application/json": {
                        "detail": "You do not have permission to perform this action."
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        operation = serializer.validated_data['operation']
        enrollments = serializer.validated_data['enrollments']
        
        results = []
        successful = 0
        failed = 0
        
        for idx, enrollment_data in enumerate(enrollments):
            try:
                if operation == 'add':
                    result = self._bulk_add_student(request.user, enrollment_data)
                else:  # remove
                    result = self._bulk_remove_student(request.user, enrollment_data)
                
                results.append({
                    'index': idx,
                    'status': 'success',
                    'message': result['message'],
                    'data': result
                })
                successful += 1
                
            except Exception as e:
                results.append({
                    'index': idx,
                    'status': 'error',
                    'message': str(e),
                    'data': enrollment_data
                })
                failed += 1
        
        return Response({
            "success": True,
            "data": {
                'operation': operation,
                'total_processed': len(enrollments),
                'successful': successful,
                'failed': failed,
                'results': results
            }
        }, status=status.HTTP_200_OK)
    
    def _bulk_add_student(self, admin_user, data):
        """Add single student in bulk operation"""
        user = User.objects.get(pk=data['user_id'])
        course = Course.objects.get(pk=data['course_id'])
        plan_type = data['plan_type']
        amount_paid = data.get('amount_paid')
        notes = data.get('notes', '')
        
        # Use the same logic as AdminAddStudentToPlanView
        if not amount_paid:
            if plan_type == CoursePlanType.ONE_MONTH:
                amount_paid = course.price_one_month
            elif plan_type == CoursePlanType.THREE_MONTHS:
                amount_paid = course.price_three_months
            elif plan_type == CoursePlanType.LIFETIME:
                amount_paid = course.price_lifetime
            else:
                amount_paid = Decimal('0.00')
        
        # Process enrollment (simplified version)
        enrollment, created = Enrollment.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                'plan_type': plan_type,
                'amount_paid': amount_paid,
                'is_active': True,
                'date_enrolled': timezone.now()  # Set date_enrolled explicitly
            }
        )
        
        if not created:
            enrollment.plan_type = plan_type
            enrollment.amount_paid = amount_paid
            enrollment.is_active = True
            enrollment.date_enrolled = timezone.now()  # Update date_enrolled
            enrollment.save()
        
        # Set expiry date using current time
        current_time = timezone.now()
        if plan_type == CoursePlanType.ONE_MONTH:
            enrollment.expiry_date = current_time + timezone.timedelta(days=30)
        elif plan_type == CoursePlanType.THREE_MONTHS:
            enrollment.expiry_date = current_time + timezone.timedelta(days=90)
        elif plan_type == CoursePlanType.LIFETIME:
            enrollment.expiry_date = None
        
        enrollment.save()
        
        return {
            'message': f"Added {user.email} to {course.title}",
            'enrollment_id': enrollment.id,
            'user_id': user.id,
            'course_id': course.id
        }
    
    def _bulk_remove_student(self, admin_user, data):
        """Remove single student in bulk operation"""
        user = User.objects.get(pk=data['user_id'])
        course = Course.objects.get(pk=data['course_id'])
        reason = data.get('reason', '')
        
        enrollment = Enrollment.objects.get(user=user, course=course, is_active=True)
        enrollment.is_active = False
        enrollment.save()
        
        return {
            'message': f"Removed {user.email} from {course.title}",
            'enrollment_id': enrollment.id,
            'user_id': user.id,
            'course_id': course.id,
            'reason': reason
        }
        
class AdminStudentEnrollmentsView(generics.RetrieveAPIView):
    """
    Admin API endpoint for viewing a specific student's enrollment details.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    @swagger_auto_schema(
        operation_summary="Admin: Get student enrollment details",
        operation_description="""
        Admin-only endpoint to view detailed enrollment information for a specific student.
        
        **Returns comprehensive enrollment data including:**
        - Student basic information (email, name, phone, etc.)
        - All enrolled courses with detailed information
        - Enrollment status (active, expired, expiring soon, etc.)
        - Days remaining for each enrollment
        - Plan types and expiration dates
        - Payment amounts for each enrollment
        - Course categories and locations
        
        **Use Cases:**
        - Check student's current enrollment status
        - Monitor expiring enrollments
        - Review payment history per course
        - Provide customer support
        - Audit enrollment data
        """,
        manual_parameters=[
            openapi.Parameter(
                'user_id', 
                openapi.IN_PATH, 
                description="ID of the student to retrieve enrollment details for", 
                type=openapi.TYPE_INTEGER,
                required=True
            ),
            openapi.Parameter(
                'include_inactive', 
                openapi.IN_QUERY, 
                description="Include inactive enrollments (default: false)", 
                type=openapi.TYPE_BOOLEAN,
                default=False
            ),
            openapi.Parameter(
                'plan_type', 
                openapi.IN_QUERY, 
                description="Filter by plan type (ONE_MONTH, THREE_MONTHS, LIFETIME)", 
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'status', 
                openapi.IN_QUERY, 
                description="Filter by status (active, expired, expiring_soon)", 
                type=openapi.TYPE_STRING
            ),
        ],
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Student enrollment details retrieved successfully",
                examples={
                    "application/json": {
                        "success": True,
                        "data": {
                            "student": {
                                "id": 123,
                                "email": "student@example.com",
                                "full_name": "John Doe",
                                "phone_number": "+1234567890",
                                "date_of_birth": "1995-01-15",
                                "profile_picture_url": "https://example.com/profile.jpg"
                            },
                            "enrollment_summary": {
                                "total_enrollments": 5,
                                "active_enrollments": 3,
                                "expired_enrollments": 1,
                                "expiring_soon": 1,
                                "lifetime_enrollments": 2,
                                "total_amount_paid": "1299.00"
                            },
                            "enrollments": [
                                {
                                    "id": 456,
                                    "course": 101,
                                    "course_title": "Advanced Python Programming",
                                    "course_category": "Programming",
                                    "course_location": "Online",
                                    "date_enrolled": "2024-12-01T10:30:00Z",
                                    "plan_type": "LIFETIME",
                                    "plan_name": "Lifetime",
                                    "expiry_date": None,
                                    "amount_paid": "299.00",
                                    "is_active": True,
                                    "is_expired": False,
                                    "days_remaining": None,
                                    "enrollment_status": {
                                        "status": "active_lifetime",
                                        "message": "Lifetime access",
                                        "color": "green"
                                    }
                                },
                                {
                                    "id": 457,
                                    "course": 102,
                                    "course_title": "Data Science Fundamentals",
                                    "course_category": "Data Science",
                                    "course_location": "Hybrid",
                                    "date_enrolled": "2025-01-15T14:20:00Z",
                                    "plan_type": "THREE_MONTHS",
                                    "plan_name": "Three Months",
                                    "expiry_date": "2025-04-15T14:20:00Z",
                                    "amount_paid": "199.00",
                                    "is_active": True,
                                    "is_expired": False,
                                    "days_remaining": 73,
                                    "enrollment_status": {
                                        "status": "active",
                                        "message": "Active - 73 days remaining",
                                        "color": "green"
                                    }
                                }
                            ]
                        }
                    }
                },
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'student': openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                        'email': openapi.Schema(type=openapi.TYPE_STRING),
                                        'full_name': openapi.Schema(type=openapi.TYPE_STRING),
                                        'phone_number': openapi.Schema(type=openapi.TYPE_STRING),
                                        'date_of_birth': openapi.Schema(type=openapi.TYPE_STRING),
                                        'profile_picture_url': openapi.Schema(type=openapi.TYPE_STRING)
                                    }
                                ),
                                'enrollment_summary': openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        'total_enrollments': openapi.Schema(type=openapi.TYPE_INTEGER),
                                        'active_enrollments': openapi.Schema(type=openapi.TYPE_INTEGER),
                                        'expired_enrollments': openapi.Schema(type=openapi.TYPE_INTEGER),
                                        'expiring_soon': openapi.Schema(type=openapi.TYPE_INTEGER),
                                        'lifetime_enrollments': openapi.Schema(type=openapi.TYPE_INTEGER),
                                        'total_amount_paid': openapi.Schema(type=openapi.TYPE_STRING)
                                    }
                                ),
                                'enrollments': openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'course': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'course_title': openapi.Schema(type=openapi.TYPE_STRING),
                                            'course_category': openapi.Schema(type=openapi.TYPE_STRING),
                                            'course_location': openapi.Schema(type=openapi.TYPE_STRING),
                                            'date_enrolled': openapi.Schema(type=openapi.TYPE_STRING),
                                            'plan_type': openapi.Schema(type=openapi.TYPE_STRING),
                                            'plan_name': openapi.Schema(type=openapi.TYPE_STRING),
                                            'expiry_date': openapi.Schema(type=openapi.TYPE_STRING),
                                            'amount_paid': openapi.Schema(type=openapi.TYPE_STRING),
                                            'is_active': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                            'is_expired': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                            'days_remaining': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'enrollment_status': openapi.Schema(
                                                type=openapi.TYPE_OBJECT,
                                                properties={
                                                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                                                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                                                    'color': openapi.Schema(type=openapi.TYPE_STRING)
                                                }
                                            )
                                        }
                                    )
                                )
                            }
                        )
                    }
                )
            ),
            status.HTTP_404_NOT_FOUND: openapi.Response(
                description="Student not found",
                examples={
                    "application/json": {
                        "error": "Student not found"
                    }
                }
            ),
            status.HTTP_403_FORBIDDEN: openapi.Response(
                description="Admin access required",
                examples={
                    "application/json": {
                        "detail": "You do not have permission to perform this action."
                    }
                }
            )
        }
    )
    def get(self, request, user_id, *args, **kwargs):
        # Add caching for admin enrollment details
        cache_key = f"admin_student_enrollments_v8_{user_id}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return Response(cached_data)
        
        try:
            # OPTIMIZED query with minimal data loading
            student = User.objects.select_related().only(
                'id', 'email', 'full_name', 'phone_number', 'date_of_birth'
            ).get(pk=user_id, is_staff=False, is_superuser=False)
        except User.DoesNotExist:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get filters
        include_inactive = request.query_params.get('include_inactive', 'false').lower() == 'true'
        plan_type_filter = request.query_params.get('plan_type')
        status_filter = request.query_params.get('status')
        
        # OPTIMIZED enrollment query
        enrollment_query = Enrollment.objects.filter(user=student).select_related(
            'course', 'course__category'
        ).only(
            'id', 'date_enrolled', 'plan_type', 'expiry_date', 'amount_paid', 'is_active',
            'course__id', 'course__title', 'course__image', 'course__category__name', 'course__location'
        )
        
        if not include_inactive:
            enrollment_query = enrollment_query.filter(is_active=True)
        
        if plan_type_filter:
            enrollment_query = enrollment_query.filter(plan_type=plan_type_filter)
        
        enrollments = list(enrollment_query.order_by('-date_enrolled'))
        
        # Build response data efficiently
        enrollment_data = []
        for enrollment in enrollments:
            enrollment_item = {
                'id': enrollment.id,
                'course': enrollment.course.id,
                'course_title': enrollment.course.title,
                'course_image': enrollment.course.image.url if enrollment.course.image else None,
                'course_category': enrollment.course.category.name if enrollment.course.category else None,
                'course_location': enrollment.course.location,
                'date_enrolled': enrollment.date_enrolled,
                'plan_type': enrollment.plan_type,
                'plan_name': enrollment.get_plan_type_display(),
                'expiry_date': enrollment.expiry_date,
                'amount_paid': str(enrollment.amount_paid),
                'is_active': enrollment.is_active,
                'is_expired': enrollment.is_expired,
                'days_remaining': enrollment.get_days_remaining(),
                'enrollment_status': self._get_enrollment_status_fast(enrollment)
            }
            enrollment_data.append(enrollment_item)
        
        # Apply status filter
        if status_filter:
            filtered_enrollments = []
            for item in enrollment_data:
                if (status_filter == 'active' and item['enrollment_status']['status'] in ['active', 'active_lifetime'] or
                    status_filter == 'expired' and item['enrollment_status']['status'] == 'expired' or
                    status_filter == 'expiring_soon' and item['enrollment_status']['status'] == 'expiring_soon'):
                    filtered_enrollments.append(item)
            enrollment_data = filtered_enrollments
        
        # Calculate summary
        summary = self._calculate_enrollment_summary_fast(enrollment_data)
        
        response_data = {
            'student': {
                'id': student.id,
                'email': student.email,
                'full_name': student.full_name,
                'phone_number': student.phone_number,
                'date_of_birth': student.date_of_birth,
                'profile_picture_url': student.get_profile_picture_url()
            },
            'enrollment_summary': summary,
            'enrollments': enrollment_data
        }
        
        # Cache for 10 minutes
        cache.set(cache_key, response_data, 600)
        
        return Response({"success": True, "data": response_data}, status=status.HTTP_200_OK)
    
    def _get_enrollment_status_fast(self, enrollment):
        """Fast enrollment status without DB queries"""
        if not enrollment.is_active:
            return {'status': 'inactive', 'message': 'Enrollment is inactive', 'color': 'red'}
        
        if enrollment.is_expired:
            return {'status': 'expired', 'message': 'Enrollment has expired', 'color': 'red'}
        
        if enrollment.plan_type == 'LIFETIME':
            return {'status': 'active_lifetime', 'message': 'Lifetime access', 'color': 'green'}
        
        days_remaining = enrollment.get_days_remaining()
        if days_remaining is None:
            return {'status': 'active', 'message': 'Active enrollment', 'color': 'green'}
        
        if days_remaining <= 7:
            return {'status': 'expiring_soon', 'message': f'Expires in {days_remaining} days', 'color': 'orange'}
        
        return {'status': 'active', 'message': f'Active - {days_remaining} days remaining', 'color': 'green'}
    
    def _calculate_enrollment_summary_fast(self, enrollments):
        """Fast summary calculation"""
        total = len(enrollments)
        active = sum(1 for e in enrollments if e['enrollment_status']['status'] in ['active', 'active_lifetime'])
        expired = sum(1 for e in enrollments if e['enrollment_status']['status'] == 'expired')
        expiring_soon = sum(1 for e in enrollments if e['enrollment_status']['status'] == 'expiring_soon')
        lifetime = sum(1 for e in enrollments if e['plan_type'] == 'LIFETIME')
        total_paid = sum(float(e['amount_paid']) for e in enrollments)
        
        return {
            'total_enrollments': total,
            'active_enrollments': active,
            'expired_enrollments': expired,
            'expiring_soon': expiring_soon,
            'lifetime_enrollments': lifetime,
            'total_amount_paid': f"{total_paid:.2f}"
        }

class AdminAllStudentsEnrollmentsView(generics.ListAPIView):
    """
    Admin API endpoint for viewing enrollment overview of all students.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    @swagger_auto_schema(
        operation_summary="Admin: Get all students enrollment overview",
        operation_description="""
        Admin-only endpoint to get an overview of enrollments for all students.
        
        **Returns a paginated list with:**
        - Student basic information
        - Enrollment count per student
        - Total amount paid per student
        - Most recent enrollment date
        - Active/expired enrollment counts
        """,
        manual_parameters=[
            openapi.Parameter(
                'search', 
                openapi.IN_QUERY, 
                description="Search students by email, name, or phone", 
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'has_active_enrollments', 
                openapi.IN_QUERY, 
                description="Filter students with active enrollments only", 
                type=openapi.TYPE_BOOLEAN
            ),
            openapi.Parameter(
                'min_enrollments', 
                openapi.IN_QUERY, 
                description="Minimum number of enrollments", 
                type=openapi.TYPE_INTEGER
            ),
        ],
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Students enrollment overview",
                examples={
                    "application/json": {
                        "count": 50,
                        "next": "http://example.com/api/admin/students-enrollments/?page=2",
                        "previous": None,
                        "results": [
                            {
                                "student": {
                                    "id": 123,
                                    "email": "student1@example.com",
                                    "full_name": "John Doe",
                                    "phone_number": "+1234567890"
                                },
                                "enrollment_stats": {
                                    "total_enrollments": 5,
                                    "active_enrollments": 3,
                                    "expired_enrollments": 2,
                                    "total_amount_paid": "899.00",
                                    "last_enrollment_date": "2025-01-15T10:30:00Z"
                                }
                            }
                        ]
                    }
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        # Get query parameters
        search = request.query_params.get('search')
        has_active_enrollments = request.query_params.get('has_active_enrollments')
        min_enrollments = request.query_params.get('min_enrollments')
        
        # Base query for students with enrollments
        students_query = User.objects.filter(
            is_staff=False,
            is_superuser=False,
            enrollments__isnull=False
        ).distinct()
        
        # Apply search filter
        if search:
            students_query = students_query.filter(
                Q(email__icontains=search) |
                Q(full_name__icontains=search) |
                Q(phone_number__icontains=search)
            )
        
        # Apply active enrollments filter
        if has_active_enrollments and has_active_enrollments.lower() == 'true':
            students_query = students_query.filter(
                enrollments__is_active=True
            ).distinct()
        
        # Prefetch enrollments for efficient querying
        students_query = students_query.prefetch_related(
            Prefetch(
                'enrollments',
                queryset=Enrollment.objects.select_related('course')
            )
        )
        
        # Get students
        students = list(students_query.order_by('-date_joined'))
        
        # Calculate stats and apply min_enrollments filter
        students_with_stats = []
        for student in students:
            stats = self._calculate_student_stats(student)
            
            # Apply minimum enrollments filter
            if min_enrollments:
                try:
                    min_count = int(min_enrollments)
                    if stats['total_enrollments'] < min_count:
                        continue
                except ValueError:
                    pass
            
            students_with_stats.append({
                'student': UserDetailsSerializer(student).data,
                'enrollment_stats': stats
            })
        
        # Manual pagination
        from django.core.paginator import Paginator
        paginator = Paginator(students_with_stats, 20)  # 20 students per page
        page_number = request.query_params.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        # Build response with pagination
        response_data = {
            'count': paginator.count,
            'next': None,
            'previous': None,
            'results': page_obj.object_list
        }
        
        # Add pagination URLs if needed
        if page_obj.has_next():
            response_data['next'] = f"{request.build_absolute_uri()}?page={page_obj.next_page_number()}"
        if page_obj.has_previous():
            response_data['previous'] = f"{request.build_absolute_uri()}?page={page_obj.previous_page_number()}"
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    def _calculate_student_stats(self, student):
        """Calculate enrollment statistics for a student"""
        enrollments = list(student.enrollments.all())
        
        total_enrollments = len(enrollments)
        active_enrollments = sum(1 for e in enrollments if e.is_active and not e.is_expired)
        expired_enrollments = sum(1 for e in enrollments if e.is_expired or not e.is_active)
        total_amount_paid = sum(float(e.amount_paid) for e in enrollments)
        
        last_enrollment_date = None
        if enrollments:
            last_enrollment_date = max(e.date_enrolled for e in enrollments)
        
        return {
            'total_enrollments': total_enrollments,
            'active_enrollments': active_enrollments,
            'expired_enrollments': expired_enrollments,
            'total_amount_paid': f"{total_amount_paid:.2f}",
            'last_enrollment_date': last_enrollment_date
        }