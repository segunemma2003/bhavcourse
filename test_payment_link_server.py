#!/usr/bin/env python3
"""
Simple test script to verify payment link creation on the server.
Run this on the server with: python test_payment_link_server.py
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

User = get_user_model()

def test_payment_link():
    """Test payment link creation"""
    print("🧪 Testing payment link creation...")
    
    try:
        # Get test data
        user = User.objects.first()
        course = Course.objects.first()
        
        if not user or not course:
            print("❌ No user or course found")
            return False
        
        print(f"User: {user.email}")
        print(f"Course: {course.title}")
        
        # Create payment link
        service = PaymentLinkService()
        result = service.create_payment_link_request(
            user=user,
            course_id=course.id,
            plan_type=CoursePlanType.ONE_MONTH,
            amount=100.00
        )
        
        if result['success']:
            print("✅ Payment link created successfully!")
            print(f"Reference ID: {result.get('reference_id')}")
            print(f"Payment Order ID: {result.get('payment_order_id')}")
            
            # Check the payment order
            payment_order = PaymentOrder.objects.get(id=result['payment_order_id'])
            print(f"Razorpay Order ID: {payment_order.razorpay_order_id}")
            print(f"Status: {payment_order.status}")
            
            return True
        else:
            print(f"❌ Failed: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 Testing payment link creation...")
    success = test_payment_link()
    
    if success:
        print("\n🎉 Payment link creation works correctly!")
    else:
        print("\n❌ Payment link creation failed.") 