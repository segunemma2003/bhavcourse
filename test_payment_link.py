#!/usr/bin/env python3
"""
Test script for payment link functionality
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
django.setup()

from core.models import Course, User, CoursePlanType
from core.payment_link_service import PaymentLinkService
from core.services import RazorpayService

def test_payment_link_creation():
    """Test payment link creation functionality"""
    print("=== Testing Payment Link Creation ===")
    
    # Check if we have courses
    courses = Course.objects.all()
    print(f"Found {courses.count()} courses in database")
    
    if courses.count() == 0:
        print("❌ No courses found. Please create some courses first.")
        return False
    
    # Check if we have users
    users = User.objects.all()
    print(f"Found {users.count()} users in database")
    
    if users.count() == 0:
        print("❌ No users found. Please create some users first.")
        return False
    
    # Get first course and user for testing
    course = courses.first()
    user = users.first()
    
    print(f"Testing with course: {course.title}")
    print(f"Testing with user: {user.email}")
    print(f"Course prices - 1 month: {course.price_one_month}, 3 months: {course.price_three_months}, lifetime: {course.price_lifetime}")
    
    # Test Razorpay service initialization
    try:
        razorpay_service = RazorpayService()
        print("✅ Razorpay service initialized successfully")
    except Exception as e:
        print(f"❌ Razorpay service initialization failed: {e}")
        return False
    
    # Test payment link service
    try:
        payment_link_service = PaymentLinkService()
        print("✅ Payment link service initialized successfully")
    except Exception as e:
        print(f"❌ Payment link service initialization failed: {e}")
        return False
    
    # Test payment link creation
    try:
        result = payment_link_service.create_payment_link_request(
            user=user,
            course_id=course.id,
            plan_type=CoursePlanType.ONE_MONTH,
            amount=None
        )
        
        if result['success']:
            print("✅ Payment link created successfully!")
            print(f"Reference ID: {result['reference_id']}")
            print(f"Payment Link: {result.get('payment_link', 'N/A')}")
            print(f"Email sent: {result['email_sent']}")
            return True
        else:
            print(f"❌ Payment link creation failed: {result['error']}")
            return False
            
    except Exception as e:
        print(f"❌ Payment link creation failed with exception: {e}")
        return False

def test_razorpay_configuration():
    """Test Razorpay configuration"""
    print("\n=== Testing Razorpay Configuration ===")
    
    try:
        from django.conf import settings
        
        # Check required settings
        required_settings = [
            'RAZORPAY_KEY_ID',
            'RAZORPAY_KEY_SECRET',
            'RAZORPAY_CURRENCY'
        ]
        
        for setting in required_settings:
            if hasattr(settings, setting):
                value = getattr(settings, setting)
                if value:
                    print(f"✅ {setting}: {'*' * len(str(value))} (configured)")
                else:
                    print(f"❌ {setting}: Not set")
            else:
                print(f"❌ {setting}: Not found in settings")
        
        # Test Razorpay client creation
        razorpay_service = RazorpayService()
        print("✅ Razorpay client created successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Razorpay configuration test failed: {e}")
        return False

def main():
    """Main test function"""
    print("Payment Link Functionality Test")
    print("=" * 40)
    
    # Test Razorpay configuration first
    if not test_razorpay_configuration():
        print("\n❌ Razorpay configuration issues found. Please check your settings.")
        return
    
    # Test payment link creation
    if test_payment_link_creation():
        print("\n✅ All tests passed! Payment link functionality is working.")
    else:
        print("\n❌ Payment link creation failed. Check the errors above.")

if __name__ == "__main__":
    main() 