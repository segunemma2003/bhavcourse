#!/usr/bin/env python3
"""
Test script to check if the API is calling payment link service correctly
"""

import os
import sys
import django
import requests
import json

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

def test_payment_link_api():
    """Test the payment link API endpoint"""
    print("🔍 Testing Payment Link API...")
    
    try:
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
        
        # Test the service directly first
        print("\n📧 Testing Payment Link Service Directly...")
        from core.payment_link_service import PaymentLinkService
        
        service = PaymentLinkService()
        result = service.create_payment_link_request(
            user=user,
            course_id=course.id,
            plan_type=CoursePlanType.ONE_MONTH,
            amount=100.00
        )
        
        print(f"✅ Service result: {result}")
        
        if result.get('success'):
            print("✅ Payment link created successfully")
            print(f"✅ Email queued: {result.get('email_sent')}")
            print(f"✅ Payment link: {result.get('payment_link')}")
            return True
        else:
            print(f"❌ Payment link creation failed: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_celery_tasks():
    """Check if Celery tasks are being processed"""
    print("\n🔍 Checking Celery Tasks...")
    
    try:
        from celery import current_app
        
        # Check active tasks
        inspect = current_app.control.inspect()
        active = inspect.active()
        
        if active:
            print("✅ Active tasks found:")
            for worker, tasks in active.items():
                print(f"   {worker}: {len(tasks)} active tasks")
                for task in tasks:
                    print(f"     - {task.get('name', 'Unknown')}: {task.get('status', 'Unknown')}")
        else:
            print("ℹ️  No active tasks")
        
        # Check reserved tasks (queued but not started)
        reserved = inspect.reserved()
        if reserved:
            print("✅ Reserved tasks found:")
            for worker, tasks in reserved.items():
                print(f"   {worker}: {len(tasks)} reserved tasks")
        else:
            print("ℹ️  No reserved tasks")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking tasks: {e}")
        return False

def check_logs():
    """Check recent logs for email-related messages"""
    print("\n🔍 Checking Recent Logs...")
    
    try:
        # This would check your log files
        # For now, we'll just show what to look for
        print("📋 Look for these log messages:")
        print("   - 'Payment link email queued for user'")
        print("   - 'Payment link email sent successfully'")
        print("   - 'Failed to queue payment link email'")
        print("   - 'Failed to send payment link email'")
        
        print("\n📁 Check these log files:")
        print("   - /var/www/bhavani/logs/django.log")
        print("   - Celery worker logs")
        print("   - System logs: journalctl -u celery")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking logs: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Payment Link API Test")
    print("=" * 50)
    
    # Test the service
    service_ok = test_payment_link_api()
    
    # Check Celery tasks
    tasks_ok = check_celery_tasks()
    
    # Check logs
    logs_ok = check_logs()
    
    print("\n" + "=" * 50)
    print("📊 SUMMARY:")
    print(f"Service Test: {'✅ OK' if service_ok else '❌ FAILED'}")
    print(f"Celery Tasks: {'✅ OK' if tasks_ok else '❌ FAILED'}")
    print(f"Logs Check: {'✅ OK' if logs_ok else '❌ FAILED'}")
    
    if service_ok:
        print("\n🎉 Payment link service is working!")
        print("✅ If emails aren't being sent, check:")
        print("   1. Celery worker logs")
        print("   2. Email configuration")
        print("   3. Template files")
    else:
        print("\n💥 Service test failed!")
        print("❌ Check the error messages above") 