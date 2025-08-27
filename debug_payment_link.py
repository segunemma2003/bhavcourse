#!/usr/bin/env python3
"""
Debug script to test payment link creation and identify issues.
"""

import os
import sys
import django

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

from core.models import PaymentOrder, Course, CoursePlanType
from core.payment_link_service import PaymentLinkService
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()

def debug_payment_link():
    """Debug payment link creation"""
    print("🔍 Debugging payment link creation...")
    
    try:
        # Check environment
        print("1. Checking environment...")
        print(f"   DEBUG: {getattr(settings, 'DEBUG', 'Not set')}")
        print(f"   RAZORPAY_KEY_ID: {'Set' if hasattr(settings, 'RAZORPAY_KEY_ID') and settings.RAZORPAY_KEY_ID else 'Not set'}")
        print(f"   RAZORPAY_KEY_SECRET: {'Set' if hasattr(settings, 'RAZORPAY_KEY_SECRET') and settings.RAZORPAY_KEY_SECRET else 'Not set'}")
        
        # Check database
        print("\n2. Checking database...")
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            print("   Database connection: ✅ OK")
        
        # Check models
        print("\n3. Checking models...")
        user = User.objects.first()
        course = Course.objects.first()
        
        if not user:
            print("   ❌ No users found")
            return False
        if not course:
            print("   ❌ No courses found")
            return False
            
        print(f"   User: {user.email}")
        print(f"   Course: {course.title}")
        
        # Test payment link service
        print("\n4. Testing payment link service...")
        service = PaymentLinkService()
        
        # Test Razorpay service
        print("   Testing Razorpay service...")
        from core.services import RazorpayService
        razorpay_service = RazorpayService()
        print("   Razorpay service: ✅ OK")
        
        # Create payment link
        print("\n5. Creating payment link...")
        result = service.create_payment_link_request(
            user=user,
            course_id=course.id,
            plan_type=CoursePlanType.ONE_MONTH,
            amount=100.00
        )
        
        print(f"   Result: {result}")
        
        if result['success']:
            print("   ✅ Payment link created successfully!")
            return True
        else:
            print(f"   ❌ Failed: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"   ❌ Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting payment link debug...")
    success = debug_payment_link()
    
    if success:
        print("\n🎉 Payment link creation works!")
    else:
        print("\n❌ Payment link creation failed.") 