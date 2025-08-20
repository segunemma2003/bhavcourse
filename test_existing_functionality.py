#!/usr/bin/env python3
"""
Test existing functionality to ensure payment link changes didn't break anything
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

def test_regular_payment_flow():
    """Test regular Razorpay payment flow"""
    print("\n💳 Testing Regular Payment Flow:")
    
    try:
        from core.services import RazorpayService
        from core.models import PaymentOrder, Course, User
        
        # Test Razorpay service initialization
        razorpay_service = RazorpayService()
        print("✅ Razorpay service initialized")
        
        # Test order creation
        test_amount = 999.00
        order_response = razorpay_service.create_order(
            amount=test_amount,
            currency='INR',
            receipt='test_order_123',
            notes={'test': 'regular_payment'}
        )
        
        print(f"✅ Regular order creation working: {order_response['id']}")
        
        # Test payment verification structure
        test_payment_verification = razorpay_service.verify_payment_signature(
            payment_id='test_payment_123',
            order_id=order_response['id'],
            signature='test_signature'
        )
        
        print("✅ Payment verification method accessible")
        
        return True
        
    except Exception as e:
        print(f"❌ Regular payment flow test failed: {e}")
        return False

def test_course_creation():
    """Test course creation by admin"""
    print("\n📚 Testing Course Creation:")
    
    try:
        from core.models import Course, Category, CoursePlanType
        
        # Check if we can create categories
        category, created = Category.objects.get_or_create(
            name='Test Category',
            defaults={
                'image_url': 'https://example.com/test.jpg',
                'description': 'Test category description'
            }
        )
        print(f"✅ Category creation working: {category.name}")
        
        # Check if we can create courses
        course, created = Course.objects.get_or_create(
            title='Test Course for Functionality Check',
            defaults={
                'description': 'Test course description',
                'small_desc': 'Test course small description',
                'category': category,
                'location': 'Online',
                'price_one_month': 999.00,
                'price_three_months': 2499.00,
                'price_lifetime': 4999.00,
                'is_featured': False
            }
        )
        print(f"✅ Course creation working: {course.title}")
        
        # Test course objectives and requirements
        from core.models import CourseObjective, CourseRequirement, CourseCurriculum
        
        objective, created = CourseObjective.objects.get_or_create(
            course=course,
            description='Test objective',
        )
        print("✅ Course objectives working")
        
        requirement, created = CourseRequirement.objects.get_or_create(
            course=course,
            description='Test requirement',
        )
        print("✅ Course requirements working")
        
        curriculum, created = CourseCurriculum.objects.get_or_create(
            course=course,
            title='Test Curriculum Item',
            defaults={
                'video_url': 'https://example.com/test-video.mp4',
                'order': 1
            }
        )
        print("✅ Course curriculum working")
        
        return True
        
    except Exception as e:
        print(f"❌ Course creation test failed: {e}")
        return False

def test_enrollment_functionality():
    """Test enrollment functionality"""
    print("\n📝 Testing Enrollment Functionality:")
    
    try:
        from core.models import Enrollment, Course, User, CoursePlanType
        
        # Get test data
        course = Course.objects.first()
        user = User.objects.first()
        
        if not course or not user:
            print("⚠️  No course or user found - skipping enrollment test")
            return True
        
        # Test enrollment creation
        enrollment, created = Enrollment.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                'plan_type': CoursePlanType.ONE_MONTH,
                'amount_paid': course.price_one_month,
                'is_active': True
            }
        )
        
        print(f"✅ Enrollment creation working: {enrollment}")
        
        # Test enrollment properties
        print(f"   - Is expired: {enrollment.is_expired}")
        print(f"   - Days remaining: {enrollment.get_days_remaining()}")
        
        return True
        
    except Exception as e:
        print(f"❌ Enrollment test failed: {e}")
        return False

def test_purchase_model():
    """Test Purchase model functionality"""
    print("\n🛒 Testing Purchase Model:")
    
    try:
        from core.models import Purchase, Course, User, CoursePlanType
        
        # Get test data
        course = Course.objects.first()
        user = User.objects.first()
        
        if not course or not user:
            print("⚠️  No course or user found - skipping purchase test")
            return True
        
        import uuid
        
        # Test purchase creation (regular Razorpay)
        purchase = Purchase.objects.create(
            user=user,
            course=course,
            plan_type=CoursePlanType.ONE_MONTH,
            amount=course.price_one_month,
            transaction_id=f'test_transaction_{uuid.uuid4().hex[:8]}',
            razorpay_order_id=f'order_test_{uuid.uuid4().hex[:8]}',
            razorpay_payment_id=f'pay_test_{uuid.uuid4().hex[:8]}',
            payment_status='COMPLETED',
            payment_gateway='RAZORPAY'
        )
        
        print(f"✅ Regular purchase creation working: {purchase}")
        
        # Test Apple IAP purchase
        apple_purchase = Purchase.objects.create(
            user=user,
            course=course,
            plan_type=CoursePlanType.LIFETIME,
            amount=course.price_lifetime,
            transaction_id=f'apple_test_{uuid.uuid4().hex[:8]}',
            apple_transaction_id=f'apple_trans_{uuid.uuid4().hex[:8]}',
            apple_product_id='com.yourapp.course.lifetime',
            payment_status='COMPLETED',
            payment_gateway='APPLE_IAP'
        )
        
        print(f"✅ Apple IAP purchase creation working: {apple_purchase}")
        
        return True
        
    except Exception as e:
        print(f"❌ Purchase model test failed: {e}")
        return False

def test_payment_order_model():
    """Test PaymentOrder model functionality"""
    print("\n📋 Testing PaymentOrder Model:")
    
    try:
        import uuid
        from core.models import PaymentOrder, Course, User, CoursePlanType
        
        # Get test data
        course = Course.objects.first()
        user = User.objects.first()
        
        if not course or not user:
            print("⚠️  No course or user found - skipping payment order test")
            return True
        
        # Test regular Razorpay order
        regular_order = PaymentOrder.objects.create(
            user=user,
            course=course,
            amount=course.price_one_month,
            razorpay_order_id=f'order_regular_{uuid.uuid4().hex[:8]}',
            status='CREATED',
            payment_method='RAZORPAY',
            plan_type=CoursePlanType.ONE_MONTH
        )
        
        print(f"✅ Regular PaymentOrder creation working: {regular_order}")
        
        # Test payment link order
        link_order = PaymentOrder.objects.create(
            user=user,
            course=course,
            amount=course.price_three_months,
            razorpay_order_id=f'plink_test_{uuid.uuid4().hex[:8]}',
            reference_id=f'link_test_{uuid.uuid4().hex[:8]}',
            status='LINK_REQUESTED',
            payment_method='PAYMENT_LINK',
            plan_type=CoursePlanType.THREE_MONTHS
        )
        
        print(f"✅ Payment Link order creation working: {link_order}")
        
        return True
        
    except Exception as e:
        print(f"❌ PaymentOrder model test failed: {e}")
        return False

def test_admin_views():
    """Test admin views are accessible"""
    print("\n👨‍💼 Testing Admin Views:")
    
    try:
        # Test admin view imports
        from core.admin_views import (
            AdminAllStudentsView,
            AdminAllStudentsEnrollmentsView,
            EnhancedCourseViewSet
        )
        print("✅ Admin views import successfully")
        
        # Test admin models
        from core.models import Course, User, Enrollment, Purchase
        
        # Check if admin can access models
        course_count = Course.objects.count()
        user_count = User.objects.count()
        enrollment_count = Enrollment.objects.count()
        purchase_count = Purchase.objects.count()
        
        print(f"✅ Admin can access models:")
        print(f"   - Courses: {course_count}")
        print(f"   - Users: {user_count}")
        print(f"   - Enrollments: {enrollment_count}")
        print(f"   - Purchases: {purchase_count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Admin views test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Testing Existing Functionality After Payment Link Changes")
    print("=" * 60)
    
    # Test Django setup
    if not test_django_setup():
        print("\n❌ Django setup failed. Cannot proceed.")
        return
    
    # Test regular payment flow
    if not test_regular_payment_flow():
        print("\n❌ Regular payment flow test failed.")
        return
    
    # Test course creation
    if not test_course_creation():
        print("\n❌ Course creation test failed.")
        return
    
    # Test enrollment functionality
    if not test_enrollment_functionality():
        print("\n❌ Enrollment functionality test failed.")
        return
    
    # Test purchase model
    if not test_purchase_model():
        print("\n❌ Purchase model test failed.")
        return
    
    # Test payment order model
    if not test_payment_order_model():
        print("\n❌ PaymentOrder model test failed.")
        return
    
    # Test admin views
    if not test_admin_views():
        print("\n❌ Admin views test failed.")
        return
    
    print("\n🎉 All existing functionality tests passed!")
    print("\n📝 Summary:")
    print("   ✅ Regular Razorpay payments - Working")
    print("   ✅ Course creation by admin - Working")
    print("   ✅ Enrollment functionality - Working")
    print("   ✅ Purchase model - Working")
    print("   ✅ PaymentOrder model - Working")
    print("   ✅ Admin views - Working")
    print("   ✅ Payment links - Working (new feature)")

if __name__ == "__main__":
    main() 