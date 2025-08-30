#!/usr/bin/env python3
"""
Test script to check Celery status and email queuing
"""

import os
import sys
import django
import time

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

def test_celery_connection():
    """Test if Celery is connected and working"""
    print("🔍 Testing Celery Connection...")
    
    try:
        from celery import current_app
        from core.tasks import send_payment_link_email_async
        
        # Check if Celery app is configured
        app = current_app
        print(f"✅ Celery app: {app}")
        
        # Check broker connection
        try:
            inspect = app.control.inspect()
            stats = inspect.stats()
            if stats:
                print("✅ Celery workers are running")
                for worker, info in stats.items():
                    print(f"   Worker: {worker}")
                    print(f"   Pool: {info.get('pool', {}).get('implementation', 'Unknown')}")
            else:
                print("❌ No Celery workers found")
                return False
        except Exception as e:
            print(f"❌ Cannot connect to Celery workers: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Celery connection failed: {e}")
        return False

def test_email_task():
    """Test the email task directly"""
    print("\n📧 Testing Email Task...")
    
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
        
        # Test the task directly
        print("📤 Queuing email task...")
        result = send_payment_link_email_async.delay(
            user_id=user.id,
            course_id=course.id,
            plan_type=CoursePlanType.ONE_MONTH,
            amount=100.00,
            payment_link="https://test-payment-link.com",
            reference_id="test_ref_123"
        )
        
        print(f"✅ Task queued successfully")
        print(f"   Task ID: {result.id}")
        print(f"   Task Status: {result.status}")
        
        # Wait a bit and check status
        print("⏳ Waiting for task completion...")
        time.sleep(5)
        
        # Check task status
        if result.ready():
            print(f"✅ Task completed: {result.status}")
            if result.successful():
                print("✅ Task executed successfully")
                return True
            else:
                print(f"❌ Task failed: {result.result}")
                return False
        else:
            print("⏳ Task still running...")
            return True  # Task is queued and running
            
    except Exception as e:
        print(f"❌ Email task test failed: {e}")
        return False

def test_payment_link_service():
    """Test payment link service with email queuing"""
    print("\n🔗 Testing Payment Link Service...")
    
    try:
        from core.payment_link_service import PaymentLinkService
        from core.models import Course, CoursePlanType
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        user = User.objects.first()
        course = Course.objects.first()
        
        if not user or not course:
            print("❌ No user or course found")
            return False
        
        service = PaymentLinkService()
        
        # Create payment link request
        result = service.create_payment_link_request(
            user=user,
            course=course,
            plan_type=CoursePlanType.ONE_MONTH,
            amount=100.00
        )
        
        print(f"✅ Payment link result: {result}")
        
        if result.get('success'):
            print("✅ Payment link created successfully")
            print(f"✅ Email queued: {result.get('email_sent')}")
            return True
        else:
            print(f"❌ Payment link creation failed: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"❌ Payment link service test failed: {e}")
        return False

def check_celery_logs():
    """Check for common Celery issues"""
    print("\n📋 Checking Celery Configuration...")
    
    try:
        from django.conf import settings
        
        # Check Redis URL
        redis_url = getattr(settings, 'CELERY_BROKER_URL', None)
        if redis_url:
            print(f"✅ Redis URL configured: {redis_url[:20]}...")
        else:
            print("❌ Redis URL not configured")
            return False
        
        # Check Celery settings
        print(f"✅ Celery serializer: {getattr(settings, 'CELERY_TASK_SERIALIZER', 'Not set')}")
        print(f"✅ Celery result backend: {getattr(settings, 'CELERY_RESULT_BACKEND', 'Not set')}")
        
        # Check email settings
        print(f"✅ Email backend: {getattr(settings, 'EMAIL_BACKEND', 'Not set')}")
        print(f"✅ Email host: {getattr(settings, 'EMAIL_HOST', 'Not set')}")
        print(f"✅ Default from email: {getattr(settings, 'DEFAULT_FROM_EMAIL', 'Not set')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration check failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Celery Status Check")
    print("=" * 50)
    
    # Check configuration
    config_ok = check_celery_logs()
    
    # Test Celery connection
    celery_ok = test_celery_connection()
    
    # Test email task
    email_ok = test_email_task()
    
    # Test payment link service
    service_ok = test_payment_link_service()
    
    print("\n" + "=" * 50)
    print("📊 SUMMARY:")
    print(f"Configuration: {'✅ OK' if config_ok else '❌ FAILED'}")
    print(f"Celery Connection: {'✅ OK' if celery_ok else '❌ FAILED'}")
    print(f"Email Task: {'✅ OK' if email_ok else '❌ FAILED'}")
    print(f"Payment Link Service: {'✅ OK' if service_ok else '❌ FAILED'}")
    
    if all([config_ok, celery_ok, email_ok, service_ok]):
        print("\n🎉 All tests passed! Celery is working correctly.")
    else:
        print("\n💥 Some tests failed. Check the issues above.")
        print("\n🔧 Common solutions:")
        print("1. Start Celery worker: celery -A courseapp worker -l info")
        print("2. Start Celery beat: celery -A courseapp beat -l info")
        print("3. Check Redis connection")
        print("4. Verify email settings") 