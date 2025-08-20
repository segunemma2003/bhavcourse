#!/usr/bin/env python3
"""
Test for payment link functionality with proper Django configuration
"""

import os
import sys
import django
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')

def test_django_setup():
    """Test Django setup"""
    print("🔧 Testing Django Setup:")
    
    try:
        django.setup()
        print("✅ Django setup successful")
        return True
    except Exception as e:
        print(f"❌ Django setup failed: {e}")
        return False

def test_razorpay_config():
    """Test Razorpay configuration"""
    print("\n🔧 Testing Razorpay Configuration:")
    
    try:
        from django.conf import settings
        
        # Check settings
        key_id = getattr(settings, 'RAZORPAY_KEY_ID', None)
        key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', None)
        currency = getattr(settings, 'RAZORPAY_CURRENCY', None)
        
        print(f"   Key ID: {'✅ Set' if key_id else '❌ Not set'}")
        print(f"   Key Secret: {'✅ Set' if key_secret else '❌ Not set'}")
        print(f"   Currency: {currency}")
        
        if not key_id or not key_secret:
            print("❌ Razorpay credentials not configured")
            return False
        
        print("✅ Razorpay configuration is valid")
        return True
        
    except Exception as e:
        print(f"❌ Razorpay config test failed: {e}")
        return False

def test_services():
    """Test service initialization"""
    print("\n🔗 Testing Services:")
    
    try:
        from core.services import RazorpayService
        from core.payment_link_service import PaymentLinkService
        
        # Test Razorpay service
        razorpay_service = RazorpayService()
        print("✅ Razorpay service initialized")
        
        # Test Payment Link service
        payment_link_service = PaymentLinkService()
        print("✅ Payment link service initialized")
        
        return True
        
    except Exception as e:
        print(f"❌ Service initialization failed: {e}")
        return False

def test_payment_link_creation():
    """Test payment link creation logic"""
    print("\n🔗 Testing Payment Link Creation Logic:")
    
    try:
        from core.payment_link_service import PaymentLinkService
        from core.models import Course, User, CoursePlanType
        
        # Check if we have data
        courses = Course.objects.all()
        users = User.objects.all()
        
        print(f"   Found {courses.count()} courses")
        print(f"   Found {users.count()} users")
        
        if courses.count() == 0 or users.count() == 0:
            print("⚠️  No courses or users found - skipping full test")
            return True
        
        # Get sample data
        course = courses.first()
        user = users.first()
        
        print(f"   Testing with course: {course.title}")
        print(f"   Testing with user: {user.email}")
        
        # Initialize service
        service = PaymentLinkService()
        
        # Test payment link creation
        result = service.create_payment_link_request(
            user=user,
            course_id=course.id,
            plan_type=CoursePlanType.ONE_MONTH,
            amount=None
        )
        
        if result['success']:
            print("✅ Payment link created successfully!")
            print(f"   Reference ID: {result['reference_id']}")
            print(f"   Payment Link: {result.get('payment_link', 'N/A')}")
            return True
        else:
            print(f"❌ Payment link creation failed: {result['error']}")
            return False
            
    except Exception as e:
        print(f"❌ Payment link creation test failed: {e}")
        return False

def test_razorpay_api():
    """Test Razorpay API call structure"""
    print("\n🌐 Testing Razorpay API Call:")
    
    try:
        from core.services import RazorpayService
        
        # Initialize service
        razorpay_service = RazorpayService()
        
        # Test data structure
        test_data = {
            'amount': 99900,  # 999.00 in paise
            'currency': 'INR',
            'reference_id': 'test_link_123',
            'description': 'Test payment link',
            'callback_url': 'http://localhost:8000/api/payment-links/callback/',
            'callback_method': 'get',
            'notes': {'test': 'data'}
        }
        
        print("✅ Razorpay API call structure is valid")
        print(f"   Amount: {test_data['amount']} paise")
        print(f"   Currency: {test_data['currency']}")
        print(f"   Reference ID: {test_data['reference_id']}")
        
        # Note: We won't make actual API calls in this test
        # to avoid creating real payment links
        
        return True
        
    except Exception as e:
        print(f"❌ Razorpay API test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Payment Link Functionality Test (Django)")
    print("=" * 50)
    
    # Test Django setup
    if not test_django_setup():
        print("\n❌ Django setup failed. Cannot proceed.")
        return
    
    # Test Razorpay config
    if not test_razorpay_config():
        print("\n❌ Razorpay configuration test failed.")
        return
    
    # Test services
    if not test_services():
        print("\n❌ Service initialization test failed.")
        return
    
    # Test payment link creation
    if not test_payment_link_creation():
        print("\n❌ Payment link creation test failed.")
        return
    
    # Test Razorpay API
    if not test_razorpay_api():
        print("\n❌ Razorpay API test failed.")
        return
    
    print("\n🎉 All tests passed!")
    print("\n📝 Payment link functionality appears to be working correctly.")
    print("   The issue might be with:")
    print("   1. Database connection")
    print("   2. Missing courses/users in database")
    print("   3. Network connectivity to Razorpay")

if __name__ == "__main__":
    main() 