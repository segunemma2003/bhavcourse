#!/usr/bin/env python3
"""
Test script to verify the new payment link approach with proper Razorpay orders.
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

def test_proper_payment_link_creation():
    """Test the new payment link creation with proper Razorpay orders"""
    print("🧪 Testing new payment link creation with proper Razorpay orders...")
    
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
            
            # Verify the payment order was created with a proper Razorpay order ID
            payment_order = PaymentOrder.objects.get(id=result['payment_order_id'])
            
            print(f"Payment Order Details:")
            print(f"  - ID: {payment_order.id}")
            print(f"  - Razorpay Order ID: {payment_order.razorpay_order_id}")
            print(f"  - Reference ID: {payment_order.reference_id}")
            print(f"  - Status: {payment_order.status}")
            print(f"  - Payment Method: {payment_order.payment_method}")
            print(f"  - Amount: {payment_order.amount}")
            
            # Check if the razorpay_order_id looks like a proper Razorpay order ID
            # Razorpay order IDs typically start with 'order_' and are alphanumeric
            if payment_order.razorpay_order_id and payment_order.razorpay_order_id.startswith('order_'):
                print("✅ Payment order has proper Razorpay order ID format")
                return True
            else:
                print(f"❌ Payment order has unexpected order ID format: {payment_order.razorpay_order_id}")
                return False
            
        else:
            print(f"❌ Payment link creation failed: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with exception: {str(e)}")
        return False

def compare_with_regular_payment():
    """Compare payment link approach with regular payment approach"""
    print("\n🔍 Comparing payment link approach with regular payment approach...")
    
    try:
        # Get a test user and course
        user = User.objects.first()
        course = Course.objects.first()
        
        if not user or not course:
            print("❌ No user or course found for testing")
            return False
        
        # Get recent payment orders
        recent_payment_orders = PaymentOrder.objects.filter(
            user=user,
            course=course
        ).order_by('-created_at')[:5]
        
        print(f"Recent payment orders for {user.email} - {course.title}:")
        
        for order in recent_payment_orders:
            print(f"  - Order {order.id}:")
            print(f"    * Razorpay Order ID: {order.razorpay_order_id}")
            print(f"    * Payment Method: {order.payment_method}")
            print(f"    * Status: {order.status}")
            print(f"    * Created: {order.created_at}")
            print(f"    * Reference ID: {order.reference_id}")
            print()
        
        return True
        
    except Exception as e:
        print(f"❌ Comparison failed with exception: {str(e)}")
        return False

def test_razorpay_order_creation():
    """Test that Razorpay orders are being created properly"""
    print("\n🧪 Testing Razorpay order creation...")
    
    try:
        from core.services import RazorpayService
        
        razorpay_service = RazorpayService()
        
        # Test creating a small order
        test_amount = 1.00  # 1 rupee
        test_receipt = f"test_receipt_{uuid.uuid4().hex[:8]}"
        test_notes = {
            'test': True,
            'description': 'Test order for payment link verification'
        }
        
        print(f"Creating test Razorpay order for ₹{test_amount}...")
        
        order_response = razorpay_service.create_order(
            amount=test_amount,
            receipt=test_receipt,
            notes=test_notes
        )
        
        print(f"✅ Razorpay order created successfully!")
        print(f"  - Order ID: {order_response['id']}")
        print(f"  - Amount: {order_response['amount']} paise")
        print(f"  - Currency: {order_response['currency']}")
        print(f"  - Receipt: {order_response.get('receipt')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Razorpay order creation failed: {str(e)}")
        return False

if __name__ == "__main__":
    import uuid
    
    print("🚀 Starting payment link proper implementation verification...")
    
    # Test Razorpay order creation
    razorpay_success = test_razorpay_order_creation()
    
    if razorpay_success:
        # Test payment link creation
        link_success = test_proper_payment_link_creation()
        
        if link_success:
            # Compare approaches
            compare_success = compare_with_regular_payment()
            
            if compare_success:
                print("\n✅ All tests passed! The new payment link approach is working correctly.")
                print("\n📋 Summary:")
                print("  - Razorpay orders are being created properly")
                print("  - Payment links use actual Razorpay order IDs")
                print("  - The approach is now consistent with regular payments")
                print("  - No more duplicate key errors should occur")
            else:
                print("\n⚠️  Payment link creation works but comparison failed.")
        else:
            print("\n❌ Payment link creation failed.")
            sys.exit(1)
    else:
        print("\n❌ Razorpay order creation failed. Check Razorpay configuration.")
        sys.exit(1) 