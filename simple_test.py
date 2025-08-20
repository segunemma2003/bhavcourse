#!/usr/bin/env python3
"""
Simple test for payment link functionality
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

try:
    django.setup()
    print("✅ Django setup successful")
except Exception as e:
    print(f"❌ Django setup failed: {e}")
    sys.exit(1)

def test_database_connection():
    """Test database connection and basic data"""
    try:
        from core.models import Course, User, CoursePlanType
        
        # Check courses
        courses = Course.objects.all()
        print(f"📚 Found {courses.count()} courses")
        
        if courses.count() > 0:
            course = courses.first()
            print(f"   Sample course: {course.title}")
            print(f"   Prices: 1M={course.price_one_month}, 3M={course.price_three_months}, Lifetime={course.price_lifetime}")
        
        # Check users
        users = User.objects.all()
        print(f"👥 Found {users.count()} users")
        
        if users.count() > 0:
            user = users.first()
            print(f"   Sample user: {user.email}")
        
        return courses.count() > 0 and users.count() > 0
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

def test_razorpay_config():
    """Test Razorpay configuration"""
    try:
        from django.conf import settings
        
        print("\n🔧 Testing Razorpay Configuration:")
        
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
        
        # Test Razorpay client
        from core.services import RazorpayService
        razorpay_service = RazorpayService()
        print("✅ Razorpay service initialized")
        
        return True
        
    except Exception as e:
        print(f"❌ Razorpay config test failed: {e}")
        return False

def test_payment_link_service():
    """Test payment link service"""
    try:
        from core.payment_link_service import PaymentLinkService
        from core.models import Course, User, CoursePlanType
        
        print("\n🔗 Testing Payment Link Service:")
        
        # Get sample data
        course = Course.objects.first()
        user = User.objects.first()
        
        if not course or not user:
            print("❌ No course or user found for testing")
            return False
        
        # Initialize service
        service = PaymentLinkService()
        print("✅ Payment link service initialized")
        
        # Test payment link creation
        print(f"   Testing with course: {course.title}")
        print(f"   Testing with user: {user.email}")
        
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
            print(f"   Email sent: {result['email_sent']}")
            return True
        else:
            print(f"❌ Payment link creation failed: {result['error']}")
            return False
            
    except Exception as e:
        print(f"❌ Payment link service test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Payment Link Functionality Test")
    print("=" * 50)
    
    # Test database
    if not test_database_connection():
        print("\n❌ Database test failed. Please check your database setup.")
        return
    
    # Test Razorpay config
    if not test_razorpay_config():
        print("\n❌ Razorpay configuration test failed. Please check your .env file.")
        return
    
    # Test payment link service
    if test_payment_link_service():
        print("\n🎉 All tests passed! Payment link functionality is working.")
    else:
        print("\n❌ Payment link service test failed.")

if __name__ == "__main__":
    main() 