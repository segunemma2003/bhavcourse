#!/usr/bin/env python3
"""
Test script to verify email queuing functionality
"""

import os
import sys
import django
import time

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

def test_email_queuing():
    """Test if email queuing works"""
    print("🔍 Testing email queuing functionality...")
    
    try:
        from core.models import PaymentOrder, Course, CoursePlanType
        from core.payment_link_service import PaymentLinkService
        from core.tasks import send_payment_link_email_async
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        user = User.objects.first()
        course = Course.objects.first()
        
        if not user or not course:
            print("❌ No user or course found")
            return False
        
        print(f"✅ Found user: {user.email}")
        print(f"✅ Found course: {course.title}")
        
        # Test 1: Direct task execution
        print("\n📧 Test 1: Testing direct task execution...")
        try:
            result = send_payment_link_email_async.delay(
                user_id=user.id,
                course_id=course.id,
                plan_type=CoursePlanType.ONE_MONTH,
                amount=100.00,
                payment_link="https://test-payment-link.com",
                reference_id="test_ref_123"
            )
            print(f"✅ Task queued successfully: {result.id}")
            print(f"✅ Task status: {result.status}")
        except Exception as e:
            print(f"❌ Task queuing failed: {str(e)}")
            return False
        
        # Test 2: Payment link service with queued email
        print("\n📧 Test 2: Testing payment link service with queued email...")
        try:
            service = PaymentLinkService()
            
            # Create a test payment link request
            result = service.create_payment_link_request(
                user=user,
                course=course,
                plan_type=CoursePlanType.ONE_MONTH,
                amount=100.00
            )
            
            print(f"✅ Payment link creation result: {result}")
            
            if result.get('success'):
                print("✅ Payment link created successfully")
                print(f"✅ Email queued: {result.get('email_sent')}")
                return True
            else:
                print(f"❌ Payment link creation failed: {result.get('error')}")
                return False
                
        except Exception as e:
            print(f"❌ Payment link service test failed: {str(e)}")
            return False
            
    except Exception as e:
        print(f"❌ Test setup failed: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 Starting Email Queue Test")
    print("=" * 50)
    
    success = test_email_queuing()
    
    print("=" * 50)
    if success:
        print("🎉 Email queuing test completed successfully!")
        print("✅ Emails are now being queued asynchronously")
        print("✅ Payment link generation should be faster")
    else:
        print("💥 Email queuing test failed!")
        print("❌ There are issues with the email queuing setup") 