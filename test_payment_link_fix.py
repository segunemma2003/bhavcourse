#!/usr/bin/env python3
"""
Test script to verify payment link creation works without duplicate key errors.
"""

import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

from core.models import PaymentOrder, Course, CoursePlanType
from core.payment_link_service import PaymentLinkService
from django.contrib.auth import get_user_model

User = get_user_model()

def test_payment_link_creation():
    """Test payment link creation to ensure no duplicate key errors"""
    print("🧪 Testing payment link creation...")
    
    try:
        # Get a test user and course
        user = User.objects.first()
        course = Course.objects.first()
        
        if not user or not course:
            print("❌ No user or course found for testing")
            return False
        
        print(f"Using user: {user.email}")
        print(f"Using course: {course.title}")
        
        # Initialize payment link service
        payment_service = PaymentLinkService()
        
        # Test payment link creation
        result = payment_service.create_payment_link_request(
            user=user,
            course_id=course.id,
            plan_type=CoursePlanType.ONE_MONTH,
            amount=100.00
        )
        
        if result['success']:
            print("✅ Payment link creation successful!")
            print(f"Reference ID: {result.get('reference_id')}")
            print(f"Payment Order ID: {result.get('payment_order_id')}")
            
            # Verify the payment order was created with a valid razorpay_order_id
            payment_order = PaymentOrder.objects.get(id=result['payment_order_id'])
            if payment_order.razorpay_order_id and payment_order.razorpay_order_id.strip():
                print(f"✅ Payment order has valid razorpay_order_id: {payment_order.razorpay_order_id}")
            else:
                print("❌ Payment order has empty razorpay_order_id")
                return False
            
            return True
        else:
            print(f"❌ Payment link creation failed: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with exception: {str(e)}")
        return False

def check_payment_orders():
    """Check for any problematic payment orders"""
    print("\n🔍 Checking payment orders...")
    
    # Check for empty razorpay_order_id
    empty_orders = PaymentOrder.objects.filter(razorpay_order_id='')
    print(f"Orders with empty razorpay_order_id: {empty_orders.count()}")
    
    # Check for null razorpay_order_id
    null_orders = PaymentOrder.objects.filter(razorpay_order_id__isnull=True)
    print(f"Orders with null razorpay_order_id: {null_orders.count()}")
    
    # Check for duplicate razorpay_order_id
    from django.db.models import Count
    duplicates = PaymentOrder.objects.values('razorpay_order_id').annotate(
        count=Count('razorpay_order_id')
    ).filter(count__gt=1, razorpay_order_id__isnull=False)
    
    print(f"Duplicate razorpay_order_id values: {duplicates.count()}")
    
    if duplicates.exists():
        for dup in duplicates:
            print(f"  - {dup['razorpay_order_id']}: {dup['count']} occurrences")

if __name__ == "__main__":
    print("🚀 Starting payment link fix verification...")
    
    # Check current state
    check_payment_orders()
    
    # Test payment link creation
    success = test_payment_link_creation()
    
    if success:
        print("\n✅ All tests passed! Payment link creation should work correctly.")
    else:
        print("\n❌ Tests failed. There may still be issues to resolve.")
        sys.exit(1) 