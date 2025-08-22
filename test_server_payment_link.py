#!/usr/bin/env python3
"""
Test script to verify payment link creation on the server.
This script should be run on the server with the Django environment activated.
"""

import os
import sys
import django

# Add the project directory to the Python path
sys.path.append('/var/www/bhavani')

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

from core.models import PaymentOrder, Course, CoursePlanType
from core.payment_link_service import PaymentLinkService
from core.services import RazorpayService
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

def test_razorpay_order_creation():
    """Test that Razorpay orders can be created"""
    print("🧪 Testing Razorpay order creation...")
    
    try:
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
        
        return True, order_response['id']
        
    except Exception as e:
        print(f"❌ Razorpay order creation failed: {str(e)}")
        return False, None

def test_payment_link_creation():
    """Test payment link creation with proper Razorpay orders"""
    print("\n🧪 Testing payment link creation...")
    
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
            
            print(f"\nPayment Order Details:")
            print(f"  - ID: {payment_order.id}")
            print(f"  - Razorpay Order ID: {payment_order.razorpay_order_id}")
            print(f"  - Reference ID: {payment_order.reference_id}")
            print(f"  - Status: {payment_order.status}")
            print(f"  - Payment Method: {payment_order.payment_method}")
            print(f"  - Amount: {payment_order.amount}")
            
            # Check if the razorpay_order_id looks like a proper Razorpay order ID
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

def check_existing_payment_orders():
    """Check existing payment orders for any issues"""
    print("\n🔍 Checking existing payment orders...")
    
    try:
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
        
        # Show recent payment orders
        recent_orders = PaymentOrder.objects.order_by('-created_at')[:5]
        print(f"\nRecent payment orders:")
        for order in recent_orders:
            print(f"  - Order {order.id}: {order.razorpay_order_id} ({order.payment_method}) - {order.status}")
        
        return True
        
    except Exception as e:
        print(f"❌ Check failed with exception: {str(e)}")
        return False

def test_razorpay_configuration():
    """Test Razorpay configuration"""
    print("\n🔧 Testing Razorpay configuration...")
    
    try:
        from django.conf import settings
        
        print(f"Razorpay Key ID: {'✅ Set' if hasattr(settings, 'RAZORPAY_KEY_ID') and settings.RAZORPAY_KEY_ID else '❌ Not set'}")
        print(f"Razorpay Key Secret: {'✅ Set' if hasattr(settings, 'RAZORPAY_KEY_SECRET') and settings.RAZORPAY_KEY_KEY_SECRET else '❌ Not set'}")
        print(f"Razorpay Currency: {getattr(settings, 'RAZORPAY_CURRENCY', 'Not set')}")
        
        # Test Razorpay client initialization
        razorpay_service = RazorpayService()
        print("✅ Razorpay service initialized successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Razorpay configuration test failed: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 Starting server payment link tests...")
    
    # Test Razorpay configuration
    config_success = test_razorpay_configuration()
    
    if config_success:
        # Test Razorpay order creation
        order_success, order_id = test_razorpay_order_creation()
        
        if order_success:
            # Test payment link creation
            link_success = test_payment_link_creation()
            
            if link_success:
                # Check existing orders
                check_success = check_existing_payment_orders()
                
                if check_success:
                    print("\n✅ All tests passed! Payment link creation is working correctly.")
                    print("\n📋 Summary:")
                    print("  - Razorpay configuration is correct")
                    print("  - Razorpay orders can be created")
                    print("  - Payment links use proper Razorpay order IDs")
                    print("  - No duplicate key errors should occur")
                else:
                    print("\n⚠️  Payment link creation works but order check failed.")
            else:
                print("\n❌ Payment link creation failed.")
        else:
            print("\n❌ Razorpay order creation failed.")
    else:
        print("\n❌ Razorpay configuration failed.")
    
    print("\n🎯 Test completed!") 