from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import CoursePlanType, Enrollment, UserSubscription, Notification, FCMDevice
from django.contrib.auth import get_user_model
from .firebase import send_firebase_message, send_bulk_notifications
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

@shared_task
def send_push_notification(user_id, title, message, data=None):
    """
    Send push notification to all active devices of a user
    
    Args:
        user_id (int): User ID
        title (str): Notification title
        message (str): Notification body
        data (dict): Additional data payload
        
    Returns:
        dict: Result summary
    """
    try:
        user = User.objects.get(id=user_id)
        
        # Create notification in database first
        Notification.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type='SYSTEM',
            is_seen=False
        )
        
        # Get all active devices for the user
        devices = FCMDevice.objects.filter(user_id=user_id, active=True)
        
        if not devices.exists():
            logger.info(f"No active devices found for user {user_id}")
            return {
                'status': 'success',
                'message': f'No active devices for user {user_id}',
                'devices_count': 0,
                'success_count': 0,
                'failure_count': 0
            }
        
        # Extract registration tokens
        tokens = [device.registration_id for device in devices]
        
        # Send notifications using Firebase
        results = send_bulk_notifications(tokens, title, message, data or {})
        
        # Log invalid/unregistered tokens and deactivate them
        for device in devices:
            try:
                # Try sending to individual device to identify invalid tokens
                success = send_firebase_message(device.registration_id, title, message, data)
                if not success:
                    # Deactivate device if token is invalid
                    device.active = False
                    device.save()
                    logger.warning(f"Deactivated invalid device token for user {user_id}")
            except Exception as e:
                logger.error(f"Error processing device {device.id}: {e}")
        
        return {
            'status': 'success',
            'message': f'Push notification sent to user {user_id}',
            'devices_count': len(tokens),
            'success_count': results['success_count'],
            'failure_count': results['failure_count']
        }
        
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return {
            'status': 'error',
            'message': f'User {user_id} not found'
        }
    except Exception as e:
        logger.error(f"Error sending push notification to user {user_id}: {e}")
        return {
            'status': 'error',
            'message': f'Failed to send push notification: {str(e)}'
        }

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



