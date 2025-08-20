from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.core.cache import cache

# from core.views_optimized import CacheWarmingService
from .models import Course, CoursePlanType, Enrollment, UserSubscription, Notification, FCMDevice, CourseCurriculum
from django.contrib.auth import get_user_model
from .firebase import send_firebase_message, send_bulk_notifications
from .s3_utils import generate_presigned_url, is_s3_url
from datetime import timedelta
import logging
import hashlib

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task
def pre_warm_duration_caches():
    """
    Pre-calculate and cache video durations during low-traffic periods
    """
    try:
        # Get all unique course IDs that have recent enrollments
        recent_course_ids = Enrollment.objects.filter(
            date_enrolled__gte=timezone.now() - timedelta(days=30),
            is_active=True
        ).values_list('course_id', flat=True).distinct()
        
        for course_id in recent_course_ids:
            cache_key = f"course_duration_v8_{course_id}"
            
            # Only calculate if not cached
            if not cache.get(cache_key):
                try:
                    course = Course.objects.prefetch_related('curriculum').get(id=course_id)
                    total_duration = sum(
                        _estimate_video_duration_simple(item.video_url)
                        for item in course.curriculum.all()
                    )
                    cache.set(cache_key, total_duration, 86400)
                    
                except Course.DoesNotExist:
                    continue
        
        return f"Pre-warmed {len(recent_course_ids)} course duration caches"
        
    except Exception as e:
        logger.error(f"Cache pre-warming failed: {str(e)}")
        return f"Failed: {str(e)}"

def _estimate_video_duration_simple(video_url):
    """Simple, fast duration estimation"""
    if not video_url:
        return 10
    
    # Very basic estimation without expensive operations
    if any(keyword in video_url.lower() for keyword in ['intro', 'overview']):
        return 8
    elif any(keyword in video_url.lower() for keyword in ['detail', 'deep', 'advanced']):
        return 20
    else:
        return 12  # Average

@shared_task
def send_push_notification(user_id, title, message, data=None):
    """
    Optimized push notification sending
    """
    try:
        # Use select_related to avoid extra query
        user = User.objects.select_related().get(id=user_id)
        
        # Create notification in database first
        Notification.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type='SYSTEM',
            is_seen=False
        )
        
        # Get active devices with single query
        devices = FCMDevice.objects.filter(user_id=user_id, active=True).only('registration_id')
        
        if not devices.exists():
            return {
                'status': 'success',
                'message': f'No active devices for user {user_id}',
                'devices_count': 0
            }
        
        # Extract tokens efficiently
        tokens = [device.registration_id for device in devices]
        
        # Send bulk notifications
        results = send_bulk_notifications(tokens, title, message, data or {})
        
        return {
            'status': 'success',
            'message': f'Push notification sent to user {user_id}',
            'devices_count': len(tokens),
            'success_count': results.get('success_count', 0),
            'failure_count': results.get('failure_count', 0)
        }
        
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return {'status': 'error', 'message': f'User {user_id} not found'}
    except Exception as e:
        logger.error(f"Error sending push notification to user {user_id}: {e}")
        return {'status': 'error', 'message': f'Failed to send push notification: {str(e)}'}

@shared_task
def send_subscription_expiry_reminder(subscription_id=None):
    """
    Send email notifications to users whose subscriptions are expiring in 3 days.
    If subscription_id is provided, send reminder for that specific subscription.
    Otherwise, send reminders for all subscriptions expiring in 3 days.
    """
    if subscription_id:
        # Send reminder for specific subscription
        try:
            subscription = UserSubscription.objects.get(id=subscription_id, is_active=True)
            user = subscription.user
            expiry_date = subscription.end_date.strftime("%Y-%m-%d")
            
            # Check if it's within 3 days of expiry
            if subscription.end_date <= timezone.now() + timezone.timedelta(days=3):
                # Send email notification
                subject = 'Your subscription is about to expire'
                message = f'''
                Dear {user.full_name},
                
                Your {subscription.plan.name} subscription will expire on {expiry_date}.
                
                Please renew your subscription to continue enjoying all the benefits and access to our courses.
                
                Thank you for being a valued customer.
                
                Best regards,
                The Course App Team
                '''
                send_mail(subject, message, settings.EMAIL_HOST_USER, [user.email])
                
                # Create a notification record in the database
                Notification.objects.create(
                    user=user,
                    title="Subscription Expiring Soon",
                    message=f"Your {subscription.plan.name} subscription will expire on {expiry_date}. Renew now to maintain access.",
                    notification_type='SUBSCRIPTION'
                )
                
                # Send push notification
                push_result = send_push_notification.delay(
                    user.id, 
                    "Subscription Expiring Soon", 
                    f"Your subscription expires on {expiry_date}",
                    {'type': 'subscription_expiry', 'subscription_id': subscription_id}
                )
                
                logger.info(f"Sent expiry reminder for subscription {subscription_id}")
                return f"Sent expiry reminder for subscription {subscription_id}"
                
        except UserSubscription.DoesNotExist:
            logger.error(f"Subscription {subscription_id} not found")
            return f"Subscription {subscription_id} not found"
        except Exception as e:
            logger.error(f"Error sending reminder for subscription {subscription_id}: {e}")
            return f"Error: {str(e)}"
    else:
        # Find subscriptions expiring in the next 3 days
        expiry_threshold = timezone.now() + timezone.timedelta(days=3)
        expiring_subscriptions = UserSubscription.objects.filter(
            is_active=True,
            end_date__lt=expiry_threshold,
            end_date__gt=timezone.now()
        )
        
        count = 0
        for subscription in expiring_subscriptions:
            user = subscription.user
            expiry_date = subscription.end_date.strftime("%Y-%m-%d")
            
            # Send email notification
            subject = 'Your subscription is about to expire'
            message = f'''
            Dear {user.full_name},
            
            Your {subscription.plan.name} subscription will expire on {expiry_date}.
            
            Please renew your subscription to continue enjoying all the benefits and access to our courses.
            
            Thank you for being a valued customer.
            
            Best regards,
            The Course App Team
            '''
            send_mail(subject, message, settings.EMAIL_HOST_USER, [user.email])
            
            # Create a notification record in the database
            Notification.objects.create(
                user=user,
                title="Subscription Expiring Soon",
                message=f"Your {subscription.plan.name} subscription will expire on {expiry_date}. Renew now to maintain access.",
                notification_type='SUBSCRIPTION'
            )
            
            # Send push notification to user's devices
            send_push_notification.delay(
                user.id, 
                "Subscription Expiring Soon", 
                f"Your subscription expires on {expiry_date}",
                {'type': 'subscription_expiry', 'subscription_id': subscription.id}
            )
            count += 1
        
        return f"Sent {count} subscription expiry reminders"

@shared_task
def deactivate_expired_subscriptions():
    """
    Automatically deactivate expired subscriptions
    """
    now = timezone.now()
    expired_subscriptions = UserSubscription.objects.filter(
        is_active=True,
        end_date__lt=now
    )
    
    # Send notifications before deactivating
    for subscription in expired_subscriptions:
        user = subscription.user
        
        # Create notification
        Notification.objects.create(
            user=user,
            title="Subscription Expired",
            message=f"Your {subscription.plan.name} subscription has expired. Please renew to regain access to courses.",
            notification_type='SUBSCRIPTION'
        )
        
        # Send push notification
        send_push_notification.delay(
            user.id,
            "Subscription Expired",
            f"Your {subscription.plan.name} subscription has expired",
            {'type': 'subscription_expired', 'subscription_id': subscription.id}
        )
    
    # Deactivate expired subscriptions
    expired_count = expired_subscriptions.update(is_active=False)
    
    return f"Deactivated {expired_count} expired subscriptions"

@shared_task
def generate_admin_metrics_report():
    """
    Generate a weekly admin metrics report and email it to administrators
    """
    from django.contrib.auth import get_user_model
    from .models import Course, Purchase, User, Enrollment
    from django.db.models import Sum, Count
    from django.utils import timezone
    from datetime import timedelta
    
    User = get_user_model()
    
    # Calculate basic metrics
    total_courses = Course.objects.count()
    total_students = User.objects.filter(is_staff=False, is_superuser=False).count()
    total_revenue = Purchase.objects.aggregate(total=Sum('amount'))['total'] or 0
    
    # New this week
    one_week_ago = timezone.now() - timedelta(days=7)
    new_courses = Course.objects.filter(date_uploaded__gte=one_week_ago).count()
    new_students = User.objects.filter(
        date_joined__gte=one_week_ago,
        is_staff=False, 
        is_superuser=False
    ).count()
    new_revenue = Purchase.objects.filter(
        purchase_date__gte=one_week_ago
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    # Most popular courses this week
    popular_courses = Course.objects.filter(
        enrollments__date_enrolled__gte=one_week_ago
    ).annotate(
        enrollment_count=Count('enrollments')
    ).order_by('-enrollment_count')[:5]
    
    popular_courses_text = "\n".join([
        f"- {course.title}: {course.enrollment_count} new enrollments"
        for course in popular_courses
    ]) if popular_courses else "No enrollments this week."
    
    # Build email content
    subject = 'Weekly Admin Metrics Report'
    message = f"""
    Weekly Admin Metrics Report ({one_week_ago.strftime('%Y-%m-%d')} to {timezone.now().strftime('%Y-%m-%d')})
    
    OVERALL METRICS:
    - Total courses: {total_courses}
    - Total students: {total_students}
    - Total revenue: ${total_revenue}
    
    THIS WEEK:
    - New courses: {new_courses}
    - New students: {new_students}
    - New revenue: ${new_revenue}
    
    MOST POPULAR COURSES THIS WEEK:
    {popular_courses_text}
    
    View the full dashboard at: http://yourdomain.com/admin/dashboard
    """
    
    # Get all admin users
    admin_users = User.objects.filter(is_staff=True)
    admin_emails = [user.email for user in admin_users]
    
    # Send email
    if admin_emails:
        send_mail(subject, message, settings.EMAIL_HOST_USER, admin_emails)
    
    return f"Admin metrics report sent to {len(admin_emails)} administrators"

@shared_task
def cleanup_expired_otps():
    """
    Clean up expired OTPs from the database
    """
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    
    User = get_user_model()
    
    # Find users with expired OTPs
    expired_otps = User.objects.filter(
        otp_expiry__lt=timezone.now(),
        otp__isnull=False
    ).update(otp=None, otp_expiry=None)
    
    return f"Cleaned up {expired_otps} expired OTPs"

@shared_task
def cleanup_inactive_fcm_tokens():
    """
    Clean up inactive FCM tokens periodically
    """
    # Remove devices that have been inactive for more than 30 days
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
    
    # First, try sending a test notification to all devices
    # If they fail, mark them as inactive
    inactive_devices = FCMDevice.objects.filter(
        date_created__lt=thirty_days_ago,
        active=True
    )
    
    deactivated_count = 0
    for device in inactive_devices:
        # Try sending a silent notification to check if token is still valid
        success = send_firebase_message(
            device.registration_id,
            "",
            "",
            {"silent": "true", "type": "token_check"}
        )
        
        if not success:
            device.active = False
            device.save()
            deactivated_count += 1
    
    return f"Cleaned up {deactivated_count} inactive FCM tokens"



@shared_task
def send_enrollment_expiry_reminder(enrollment_id=None):
    """
    Send email notifications to users whose enrollments are expiring in 3 days.
    If enrollment_id is provided, send reminder for that specific enrollment.
    Otherwise, send reminders for all enrollments expiring in 3 days.
    """
    if enrollment_id:
        # Send reminder for specific enrollment
        try:
            enrollment = Enrollment.objects.get(id=enrollment_id, is_active=True)
            
            # Skip lifetime enrollments
            if enrollment.plan_type == CoursePlanType.LIFETIME:
                return f"Enrollment {enrollment_id} is a lifetime plan, no expiry reminder needed"
            
            user = enrollment.user
            course = enrollment.course
            expiry_date = enrollment.expiry_date.strftime("%Y-%m-%d")
            
            # Check if it's within 3 days of expiry
            if enrollment.expiry_date <= timezone.now() + timezone.timedelta(days=3):
                # Send email notification
                subject = 'Your course enrollment is about to expire'
                message = f'''
                Dear {user.full_name},
                
                Your enrollment in {course.title} will expire on {expiry_date}.
                
                Renew your enrollment to continue enjoying access to the course content.
                
                Thank you for being a valued customer.
                
                Best regards,
                The Course App Team
                '''
                send_mail(subject, message, settings.EMAIL_HOST_USER, [user.email])
                
                # Create a notification record in the database
                Notification.objects.create(
                    user=user,
                    title="Enrollment Expiring Soon",
                    message=f"Your enrollment in {course.title} will expire on {expiry_date}. Renew now to maintain access.",
                    notification_type='COURSE'
                )
                
                # Send push notification
                push_result = send_push_notification.delay(
                    user.id, 
                    "Enrollment Expiring Soon", 
                    f"Your course access expires on {expiry_date}",
                    {'type': 'enrollment_expiry', 'enrollment_id': enrollment_id}
                )
                
                logger.info(f"Sent expiry reminder for enrollment {enrollment_id}")
                return f"Sent expiry reminder for enrollment {enrollment_id}"
                
        except Enrollment.DoesNotExist:
            logger.error(f"Enrollment {enrollment_id} not found")
            return f"Enrollment {enrollment_id} not found"
        except Exception as e:
            logger.error(f"Error sending reminder for enrollment {enrollment_id}: {e}")
            return f"Error: {str(e)}"
    else:
        # Find enrollments expiring in the next 3 days
        expiry_threshold = timezone.now() + timezone.timedelta(days=3)
        expiring_enrollments = Enrollment.objects.filter(
            is_active=True,
            plan_type__in=[CoursePlanType.ONE_MONTH, CoursePlanType.THREE_MONTHS],
            expiry_date__lt=expiry_threshold,
            expiry_date__gt=timezone.now()
        )
        
        count = 0
        for enrollment in expiring_enrollments:
            user = enrollment.user
            course = enrollment.course
            expiry_date = enrollment.expiry_date.strftime("%Y-%m-%d")
            
            # Send email notification
            subject = 'Your course enrollment is about to expire'
            message = f'''
            Dear {user.full_name},
            
            Your enrollment in {course.title} will expire on {expiry_date}.
            
            Renew your enrollment to continue enjoying access to the course content.
            
            Thank you for being a valued customer.
            
            Best regards,
            The Course App Team
            '''
            send_mail(subject, message, settings.EMAIL_HOST_USER, [user.email])
            
            # Create a notification record in the database
            Notification.objects.create(
                user=user,
                title="Enrollment Expiring Soon",
                message=f"Your enrollment in {course.title} will expire on {expiry_date}. Renew now to maintain access.",
                notification_type='COURSE'
            )
            
            # Send push notification to user's devices
            send_push_notification.delay(
                user.id, 
                "Enrollment Expiring Soon", 
                f"Your course access expires on {expiry_date}",
                {'type': 'enrollment_expiry', 'enrollment_id': enrollment.id}
            )
            count += 1
        
        return f"Sent {count} enrollment expiry reminders"


@shared_task
def deactivate_expired_enrollments():
    """
    Automatically deactivate expired enrollments
    """
    now = timezone.now()
    expired_enrollments = Enrollment.objects.filter(
        is_active=True,
        plan_type__in=[CoursePlanType.ONE_MONTH, CoursePlanType.THREE_MONTHS],
        expiry_date__lt=now
    )
    
    # Send notifications before deactivating
    for enrollment in expired_enrollments:
        user = enrollment.user
        course = enrollment.course
        
        # Create notification
        Notification.objects.create(
            user=user,
            title="Course Enrollment Expired",
            message=f"Your enrollment in {course.title} has expired. Please renew to regain access to the course.",
            notification_type='COURSE'
        )
        
        # Send push notification
        send_push_notification.delay(
            user.id,
            "Course Enrollment Expired",
            f"Your enrollment in {course.title} has expired",
            {'type': 'enrollment_expired', 'enrollment_id': enrollment.id}
        )
    
    # Deactivate expired enrollments
    expired_count = expired_enrollments.update(is_active=False)
    
    return f"Deactivated {expired_count} expired enrollments"



@shared_task(bind=True, max_retries=3)
def generate_presigned_url_async(self, curriculum_id):
    """
    Generate presigned URL for single curriculum item
    """
    try:
        item = CourseCurriculum.objects.get(id=curriculum_id)
        
        # Update status to processing
        item.url_generation_status = 'processing'
        item.generation_attempts += 1
        item.last_generation_attempt = timezone.now()
        item.save(update_fields=['url_generation_status', 'generation_attempts', 'last_generation_attempt'])
        
        if not item.video_url:
            item.url_generation_status = 'not_needed'
            item.save(update_fields=['url_generation_status'])
            return f"No video URL for curriculum {curriculum_id}"
        
        if not is_s3_url(item.video_url):
            item.url_generation_status = 'not_needed'
            item.save(update_fields=['url_generation_status'])
            return f"Non-S3 URL for curriculum {curriculum_id}"
        
        # Generate presigned URL with 25-hour expiration (slightly longer than daily refresh)
        presigned_url = generate_presigned_url(item.video_url, expiration=90000)  # 25 hours
        
        # Update item with generated URL
        item.presigned_url = presigned_url
        item.presigned_expires_at = timezone.now() + timedelta(hours=25)
        item.url_generation_status = 'ready'
        item.save(update_fields=['presigned_url', 'presigned_expires_at', 'url_generation_status'])
        
        # Clear any related caches
        cache.delete(f"course_detail_v8_{item.course_id}")
        cache.delete(f"course_curriculum_v8_{item.course_id}")
        cache.delete(f"course_duration_v8_{item.course_id}")  # Clear duration cache
        
        logger.info(f"Generated presigned URL for curriculum {curriculum_id}")
        return f"Generated presigned URL for curriculum {curriculum_id}"
        
    except CourseCurriculum.DoesNotExist:
        logger.error(f"Curriculum {curriculum_id} does not exist")
        return f"Curriculum {curriculum_id} does not exist"
        
    except Exception as e:
        logger.error(f"Failed to generate presigned URL for curriculum {curriculum_id}: {str(e)}")
        
        # Update status to failed
        try:
            item = CourseCurriculum.objects.get(id=curriculum_id)
            item.url_generation_status = 'failed'
            item.save(update_fields=['url_generation_status'])
        except:
            pass
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 60 * (2 ** self.request.retries)  # 60s, 120s, 240s
            raise self.retry(countdown=countdown)
        
        return f"Failed to generate presigned URL for curriculum {curriculum_id}: {str(e)}"



@shared_task
def regenerate_all_presigned_urls():
    """
    Daily task to regenerate all presigned URLs (runs at 11:50 PM)
    """
    try:
        # Get all curriculum items that need URL generation
        curriculum_items = CourseCurriculum.objects.filter(
            video_url__isnull=False
        ).exclude(
            video_url__exact=''
        ).values_list('id', flat=True)
        
        total_items = len(curriculum_items)
        logger.info(f"Starting daily regeneration of {total_items} presigned URLs")
        
        # Queue all items for regeneration with staggered execution
        for i, curriculum_id in enumerate(curriculum_items):
            # Stagger the execution to avoid overwhelming AWS API
            countdown = i * 2  # 2 seconds between each request
            generate_presigned_url_async.apply_async(
                args=[curriculum_id],
                countdown=countdown,
                queue='url_generation'
            )
        
        return f"Queued {total_items} items for presigned URL regeneration"
        
    except Exception as e:
        logger.error(f"Failed to queue presigned URL regeneration: {str(e)}")
        return f"Failed: {str(e)}"
    
    
@shared_task
def cleanup_expired_presigned_urls():
    """
    Clean up expired presigned URLs (runs every 6 hours)
    """
    try:
        expired_count = CourseCurriculum.objects.filter(
            presigned_expires_at__lt=timezone.now(),
            url_generation_status='ready'
        ).update(
            url_generation_status='expired',
            presigned_url='',
            presigned_expires_at=None
        )
        
        logger.info(f"Marked {expired_count} presigned URLs as expired")
        return f"Cleaned up {expired_count} expired URLs"
        
    except Exception as e:
        logger.error(f"Failed to cleanup expired URLs: {str(e)}")
        return f"Failed: {str(e)}"


@shared_task
def clear_stale_caches():
    """
    Clear stale caches periodically
    """
    try:
        # Clear old enrollment caches (pattern-based clearing would be better with Redis SCAN)
        # This is a simplified version - in production, use Redis SCAN for pattern deletion
        cache_keys_to_clear = []
        
        # Add specific cache keys that are commonly stale
        for user_id in range(1, 10000):  # Adjust range based on your user count
            for suffix in ['true', 'false']:
                key_data = f"enrollments_v7_{user_id}_{suffix}"
                cache_key = hashlib.md5(key_data.encode()).hexdigest()
                cache_keys_to_clear.append(cache_key)
                
                if len(cache_keys_to_clear) >= 1000:  # Process in batches
                    cache.delete_many(cache_keys_to_clear)
                    cache_keys_to_clear = []
        
        if cache_keys_to_clear:
            cache.delete_many(cache_keys_to_clear)
            
        return "Cleared stale caches"
        
    except Exception as e:
        logger.error(f"Failed to clear stale caches: {str(e)}")
        return f"Failed: {str(e)}"
    
    
@shared_task
def monitor_failed_url_generations():
    """
    Monitor and alert for failed URL generations
    """
    try:
        failed_items = CourseCurriculum.objects.filter(
            url_generation_status='failed',
            generation_attempts__gte=3,
            video_url__isnull=False
        ).exclude(video_url__exact='')
        
        if failed_items.exists():
            count = failed_items.count()
            logger.warning(f"Found {count} curriculum items with failed URL generation")
            
            # Send notification to admins
            admin_users = User.objects.filter(is_staff=True)
            for admin in admin_users:
                Notification.objects.create(
                    user=admin,
                    title=f"URL Generation Failures",
                    message=f"{count} videos failed URL generation after multiple attempts",
                    notification_type='SYSTEM'
                )
        
        return f"Monitored failed generations: {failed_items.count() if failed_items.exists() else 0} failures"
        
    except Exception as e:
        logger.error(f"Failed to monitor URL generations: {str(e)}")
        return f"Failed: {str(e)}"
    
    
@shared_task
def refresh_expiring_presigned_urls():
    """
    Daily task to refresh presigned URLs that are expiring soon
    """
    # Find URLs expiring in the next 2 hours
    expiring_soon = CourseCurriculum.objects.filter(
        url_generation_status='ready',
        presigned_expires_at__lt=timezone.now() + timedelta(hours=2),
        video_url__isnull=False
    ).exclude(video_url='')
    
    count = 0
    for curriculum in expiring_soon:
        # Mark as expired and queue for regeneration
        curriculum.url_generation_status = 'expired'
        curriculum.save()
        
        # Queue for regeneration with staggered timing to avoid overwhelming AWS
        generate_presigned_url_async.apply_async(
            args=[curriculum.id],
            countdown=count * 2  # 2 second intervals
        )
        count += 1
    
    logger.info(f"Queued {count} URLs for refresh")
    return f"Queued {count} URLs for refresh"

@shared_task
def bulk_generate_missing_urls():
    """
    Task to generate URLs for items that don't have them yet
    """
    missing_urls = CourseCurriculum.objects.filter(
        video_url__isnull=False,
        url_generation_status__in=['pending', 'failed']
    ).exclude(video_url='')[:100]  # Process 100 at a time
    
    count = 0
    for curriculum in missing_urls:
        if is_s3_url(curriculum.video_url):
            generate_presigned_url_async.apply_async(
                args=[curriculum.id],
                countdown=count * 1  # 1 second intervals
            )
            count += 1
    
    logger.info(f"Queued {count} missing URLs for generation")
    return f"Queued {count} missing URLs for generation"

@shared_task
def cleanup_failed_url_generations():
    """
    Retry failed URL generations periodically
    """
    failed_items = CourseCurriculum.objects.filter(
        url_generation_status='failed',
        video_url__isnull=False
    ).exclude(video_url='')[:50]  # Retry 50 at a time
    
    count = 0
    for curriculum in failed_items:
        if is_s3_url(curriculum.video_url):
            # Reset to pending and retry
            curriculum.url_generation_status = 'pending'
            curriculum.save()
            
            generate_presigned_url_async.apply_async(
                args=[curriculum.id],
                countdown=count * 5  # 5 second intervals for failed items
            )
            count += 1
    
    logger.info(f"Retrying {count} failed URL generations")
    return f"Retrying {count} failed URL generations"

# Add to your existing tasks
@shared_task
def warm_cache_for_popular_content():
    
    """
    Pre-warm cache for popular courses and recent enrollments
    """
    from django.db.models import Count

    
    # Warm popular courses
    CacheWarmingService.warm_popular_courses()
    
    # Warm recent user enrollments
    from core.models import Enrollment
    recent_users = Enrollment.objects.filter(
        date_enrolled__gte=timezone.now() - timedelta(days=7)
    ).values_list('user_id', flat=True).distinct()[:100]
    
    for user_id in recent_users:
        CacheWarmingService.warm_user_enrollments(user_id)
    
    return f"Cache warmed for popular content and {len(recent_users)} recent users"


@shared_task
def bulk_process_new_curriculum():
    """Process multiple curriculum items in batches"""
    pending_items = CourseCurriculum.objects.filter(
        url_generation_status='pending'
    )[:50]  # Process 50 at a time
    
    for item in pending_items:
        generate_presigned_url_async.apply_async(
            args=[item.id],
            countdown=random.randint(1, 10)  # Spread the load
        )