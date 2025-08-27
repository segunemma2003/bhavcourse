#!/usr/bin/env python3
"""
Detailed debug script to identify where payment link creation is hanging.
"""

import os
import sys
import django
import time

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

from core.models import PaymentOrder, Course, CoursePlanType
from core.payment_link_service import PaymentLinkService
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()

def debug_step_by_step():
    """Debug payment link creation step by step"""
    print("🔍 Debugging payment link creation step by step...")
    
    try:
        # Step 1: Check environment
        print("1. Checking environment...")
        print(f"   DEBUG: {getattr(settings, 'DEBUG', 'Not set')}")
        print(f"   RAZORPAY_KEY_ID: {'Set' if hasattr(settings, 'RAZORPAY_KEY_ID') and settings.RAZORPAY_KEY_ID else 'Not set'}")
        print(f"   RAZORPAY_KEY_SECRET: {'Set' if hasattr(settings, 'RAZORPAY_KEY_SECRET') and settings.RAZORPAY_KEY_SECRET else 'Not set'}")
        
        # Step 2: Check database
        print("\n2. Checking database...")
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            print("   Database connection: ✅ OK")
        
        # Step 3: Check models
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
        
        # Step 4: Test Razorpay service initialization
        print("\n4. Testing Razorpay service initialization...")
        try:
            from core.services import RazorpayService
            razorpay_service = RazorpayService()
            print("   Razorpay service: ✅ OK")
        except Exception as e:
            print(f"   ❌ Razorpay service error: {str(e)}")
            return False
        
        # Step 5: Test payment link service initialization
        print("\n5. Testing payment link service initialization...")
        try:
            service = PaymentLinkService()
            print("   Payment link service: ✅ OK")
        except Exception as e:
            print(f"   ❌ Payment link service error: {str(e)}")
            return False
        
        # Step 6: Test Razorpay order creation (this is likely where it hangs)
        print("\n6. Testing Razorpay order creation...")
        try:
            import uuid
            test_amount = 1.00
            test_receipt = f"test_receipt_{uuid.uuid4().hex[:8]}"
            test_notes = {'test': True}
            
            print("   Creating test Razorpay order...")
            start_time = time.time()
            
            order_response = razorpay_service.create_order(
                amount=test_amount,
                receipt=test_receipt,
                notes=test_notes
            )
            
            end_time = time.time()
            print(f"   Razorpay order created in {end_time - start_time:.2f} seconds")
            print(f"   Order ID: {order_response.get('id')}")
            print("   Razorpay order creation: ✅ OK")
            
        except Exception as e:
            print(f"   ❌ Razorpay order creation error: {str(e)}")
            return False
        
        # Step 7: Test payment link creation
        print("\n7. Testing payment link creation...")
        try:
            print("   Creating payment link...")
            start_time = time.time()
            
            result = service.create_payment_link_request(
                user=user,
                course_id=course.id,
                plan_type=CoursePlanType.ONE_MONTH,
                amount=100.00
            )
            
            end_time = time.time()
            print(f"   Payment link created in {end_time - start_time:.2f} seconds")
            print(f"   Result: {result}")
            
            if result['success']:
                print("   ✅ Payment link created successfully!")
                return True
            else:
                print(f"   ❌ Failed: {result.get('error')}")
                return False
                
        except Exception as e:
            print(f"   ❌ Payment link creation error: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
            
    except Exception as e:
        print(f"   ❌ General error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting detailed payment link debug...")
    success = debug_step_by_step()
    
    if success:
        print("\n🎉 Payment link creation works!")
    else:
        print("\n❌ Payment link creation failed.") 