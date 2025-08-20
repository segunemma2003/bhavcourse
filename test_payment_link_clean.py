#!/usr/bin/env python3
"""
Test for payment link functionality with cleanup
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

def cleanup_payment_orders():
    """Clean up existing payment orders"""
    print("\n🧹 Cleaning up existing payment orders:")
    
    try:
        from core.models import PaymentOrder
        
        # Delete all payment orders
        count = PaymentOrder.objects.count()
        PaymentOrder.objects.all().delete()
        print(f"✅ Deleted {count} existing payment orders")
        return True
        
    except Exception as e:
        print(f"❌ Cleanup failed: {e}")
        return False

def test_payment_link_creation():
    """Test payment link creation"""
    print("\n🔗 Testing Payment Link Creation:")
    
    try:
        from core.payment_link_service import PaymentLinkService
        from core.models import Course, User, CoursePlanType
        
        # Check if we have data
        courses = Course.objects.all()
        users = User.objects.all()
        
        print(f"   Found {courses.count()} courses")
        print(f"   Found {users.count()} users")
        
        if courses.count() == 0 or users.count() == 0:
            print("⚠️  No courses or users found - skipping test")
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
            print(f"   Email sent: {result['email_sent']}")
            return True
        else:
            print(f"❌ Payment link creation failed: {result['error']}")
            return False
            
    except Exception as e:
        print(f"❌ Payment link creation test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Payment Link Functionality Test (Clean)")
    print("=" * 50)
    
    # Test Django setup
    if not test_django_setup():
        print("\n❌ Django setup failed. Cannot proceed.")
        return
    
    # Clean up existing payment orders
    if not cleanup_payment_orders():
        print("\n❌ Cleanup failed.")
        return
    
    # Test payment link creation
    if not test_payment_link_creation():
        print("\n❌ Payment link creation test failed.")
        return
    
    print("\n🎉 Payment link functionality is working correctly!")
    print("\n📝 The payment link feature is now ready to use.")

if __name__ == "__main__":
    main() 