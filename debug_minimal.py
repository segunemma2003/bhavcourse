#!/usr/bin/env python3
"""
Minimal debug script to identify the exact issue.
"""

import os
import sys
import django
import time

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

def test_step_by_step():
    """Test each step individually"""
    print("🔍 Step-by-step debugging...")
    
    # Step 1: Basic imports
    print("1. Testing imports...")
    try:
        from core.models import PaymentOrder, Course, CoursePlanType
        from core.payment_link_service import PaymentLinkService
        from django.contrib.auth import get_user_model
        print("   ✅ Imports successful")
    except Exception as e:
        print(f"   ❌ Import error: {str(e)}")
        return False
    
    # Step 2: Get test data
    print("2. Getting test data...")
    try:
        User = get_user_model()
        user = User.objects.first()
        course = Course.objects.first()
        
        if not user or not course:
            print("   ❌ No user or course found")
            return False
            
        print(f"   ✅ User: {user.email}")
        print(f"   ✅ Course: {course.title}")
    except Exception as e:
        print(f"   ❌ Data error: {str(e)}")
        return False
    
    # Step 3: Test service initialization
    print("3. Testing service initialization...")
    try:
        service = PaymentLinkService()
        print("   ✅ Service initialized")
    except Exception as e:
        print(f"   ❌ Service error: {str(e)}")
        return False
    
    # Step 4: Test Razorpay service
    print("4. Testing Razorpay service...")
    try:
        from core.services import RazorpayService
        razorpay_service = RazorpayService()
        print("   ✅ Razorpay service initialized")
    except Exception as e:
        print(f"   ❌ Razorpay error: {str(e)}")
        return False
    
    # Step 5: Test simple Razorpay call
    print("5. Testing simple Razorpay call...")
    try:
        import uuid
        test_data = {
            'amount': 10000,
            'currency': 'INR',
            'reference_id': f'test_{uuid.uuid4().hex[:8]}',
            'description': 'Test payment link',
            'callback_url': 'https://api.pixelcraftsbybhavani.com/api/payment-links/callback/',
            'callback_method': 'get',
            'notes': {'test': True}
        }
        
        print("   📞 Making Razorpay API call...")
        start_time = time.time()
        
        response = razorpay_service.create_payment_link(test_data)
        
        end_time = time.time()
        print(f"   ✅ Razorpay call completed in {end_time - start_time:.2f} seconds")
        print(f"   Response: {response}")
        
    except Exception as e:
        print(f"   ❌ Razorpay call error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 6: Test full payment link creation
    print("6. Testing full payment link creation...")
    try:
        print("   📞 Creating payment link...")
        start_time = time.time()
        
        result = service.create_payment_link_request(
            user=user,
            course_id=course.id,
            plan_type=CoursePlanType.ONE_MONTH,
            amount=100.00
        )
        
        end_time = time.time()
        print(f"   ✅ Payment link creation completed in {end_time - start_time:.2f} seconds")
        print(f"   Result: {result}")
        
        return result.get('success', False)
        
    except Exception as e:
        print(f"   ❌ Payment link creation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting minimal debug...")
    success = test_step_by_step()
    
    if success:
        print("\n🎉 Payment link creation works!")
    else:
        print("\n❌ Payment link creation failed.") 