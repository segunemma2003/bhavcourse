# core/tasks.py
from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import UserSubscription, Notification
from django.contrib.auth import get_user_model

User = get_user_model()

@shared_task
def send_subscription_expiry_reminder():
    """
    Send email notifications to users whose subscriptions are expiring in 3 days
    """
    # Find subscriptions expiring in the next 3 days
    expiry_threshold = timezone.now() + timezone.timedelta(days=3)
    expiring_subscriptions = UserSubscription.objects.filter(
        is_active=True,
        end_date__lt=expiry_threshold,
        end_date__gt=timezone.now()
    )
    
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
        
        # Send push notification to user's devices (handled by separate function)
        send_push_notification.delay(user.id, "Subscription Expiring Soon", 
                                  f"Your subscription expires on {expiry_date}")
    
    return f"Sent {expiring_subscriptions.count()} subscription expiry reminders"

@shared_task
def deactivate_expired_subscriptions():
    """
    Automatically deactivate expired subscriptions
    """
    now = timezone.now()
    expired_count = UserSubscription.objects.filter(
        is_active=True,
        end_date__lt=now
    ).update(is_active=False)
    
    return f"Deactivated {expired_count} expired subscriptions"

@shared_task
def send_push_notification(user_id, title, message, data=None):
    """
    Send push notification to all devices of a user
    """
    from .firebase import send_firebase_message
    from .models import FCMDevice

    user = User.objects.get(id=user_id)
    
    # Create notification in database
    Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type='SYSTEM',
        is_seen=False
    )
    
    # Get all active devices for the user
    devices = FCMDevice.objects.filter(user_id=user_id, active=True)
    
    results = []
    for device in devices:
        try:
            # This would call your Firebase integration
            # Implement according to your firebase.py module
            success = send_firebase_message(
                device.registration_id,
                title,
                message,
                data or {}
            )
            results.append((device.id, success))
        except Exception as e:
            results.append((device.id, f"Error: {str(e)}"))
    
    return f"Push notification sent to {len(results)} devices"


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
    ])
    
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
    {popular_courses_text if popular_courses else "No enrollments this week."}
    
    View the full dashboard at: http://yourdomain.com/admin/dashboard
    
    """
    
    # Get all admin users
    admin_users = User.objects.filter(is_staff=True)
    admin_emails = [user.email for user in admin_users]
    
    # Send email
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