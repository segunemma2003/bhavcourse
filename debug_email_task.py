#!/usr/bin/env python3
"""
Debug script to test email task directly
"""

import os
import sys
import django

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

def debug_email_task():
    """Debug the email task directly"""
    print("🔍 Debugging Email Task...")
    
    try:
        from core.tasks import send_payment_link_email_async
        from core.models import Course, CoursePlanType
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        user = User.objects.first()
        course = Course.objects.first()
        
        if not user or not course:
            print("❌ No user or course found")
            return False
        
        print(f"✅ Found user: {user.email}")
        print(f"✅ Found course: {course.title}")
        
        # Test the task directly without Celery
        print("📧 Testing task directly...")
        
        result = send_payment_link_email_async(
            user_id=user.id,
            course_id=course.id,
            plan_type=CoursePlanType.ONE_MONTH,
            amount=100.00,
            payment_link="https://test-payment-link.com",
            reference_id="test_ref_123"
        )
        
        print(f"✅ Task result: {result}")
        return result
        
    except Exception as e:
        print(f"❌ Task failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_email_templates():
    """Check if email templates exist"""
    print("\n🔍 Checking Email Templates...")
    
    try:
        from django.template.loader import render_to_string
        from django.conf import settings
        
        # Test template rendering
        context = {
            'user_name': 'Test User',
            'course_title': 'Test Course',
            'course_description': 'Test Description',
            'plan_type': 'One Month',
            'amount': 100.00,
            'payment_link': 'https://test.com',
            'reference_id': 'TEST123',
            'expiry_date': 'December 31, 2024',
            'support_email': 'support@test.com'
        }
        
        # Try to render templates
        try:
            html_message = render_to_string('emails/payment_link.html', context)
            print("✅ HTML template rendered successfully")
        except Exception as e:
            print(f"❌ HTML template failed: {e}")
        
        try:
            plain_message = render_to_string('emails/payment_link.txt', context)
            print("✅ Text template rendered successfully")
        except Exception as e:
            print(f"❌ Text template failed: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Template check failed: {e}")
        return False

def test_email_sending():
    """Test email sending directly"""
    print("\n🔍 Testing Email Sending...")
    
    try:
        from django.core.mail import send_mail
        from django.conf import settings
        
        subject = "Test Email"
        message = "This is a test email"
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bybhavani.com')
        recipient_list = ['segunemma2003@gmail.com']
        
        print(f"From: {from_email}")
        print(f"To: {recipient_list}")
        
        result = send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=False
        )
        
        print(f"✅ Email sent successfully: {result}")
        return True
        
    except Exception as e:
        print(f"❌ Email sending failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Email Task Debug")
    print("=" * 50)
    
    # Check templates
    templates_ok = check_email_templates()
    
    # Test email sending
    email_ok = test_email_sending()
    
    # Debug task
    task_ok = debug_email_task()
    
    print("\n" + "=" * 50)
    print("📊 SUMMARY:")
    print(f"Templates: {'✅ OK' if templates_ok else '❌ FAILED'}")
    print(f"Email Sending: {'✅ OK' if email_ok else '❌ FAILED'}")
    print(f"Task Execution: {'✅ OK' if task_ok else '❌ FAILED'}") 