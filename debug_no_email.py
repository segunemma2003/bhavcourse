#!/usr/bin/env python3
"""
Debug script that tests payment link creation without email sending.
"""

import os
import sys
import django
import time
import uuid

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

def test_without_email():
    """Test payment link creation without email"""
    print("🔍 Testing payment link creation without email...")
    
    try:
        from core.models import PaymentOrder, Course, CoursePlanType
        from core.services import RazorpayService
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        user = User.objects.first()
        course = Course.objects.first()
        
        if not user or not course:
            print("❌ No user or course found")
            return False
        
        razorpay_service = RazorpayService()
        
        # Generate reference ID
        reference_id = f"link_{str(uuid.uuid4())[:8]}"
        print(f"Reference ID: {reference_id}")
        
        # Create payment order
        temp_order_id = f"plink_{uuid.uuid4().hex[:16]}"
        payment_order = PaymentOrder.objects.create(
            user=user,
            course=course,
            plan_type=CoursePlanType.ONE_MONTH,
            amount=100.00,
            status='LINK_REQUESTED',
            reference_id=reference_id,
            payment_method='PAYMENT_LINK',
            razorpay_order_id=temp_order_id
        )
        print(f"Payment order created: {payment_order.id}")
        
        # Prepare payment link data
        payment_link_data = {
            'amount': int(float(100.00) * 100),
            'currency': 'INR',
            'reference_id': reference_id,
            'description': f'Payment for {course.title} - {dict(CoursePlanType.choices)[CoursePlanType.ONE_MONTH]}',
            'callback_url': 'https://api.pixelcraftsbybhavani.com/api/payment-links/callback/',
            'callback_method': 'get',
            'notes': {
                'user_id': str(user.id),
                'course_id': str(course.id),
                'plan_type': CoursePlanType.ONE_MONTH,
                'email': user.email,
                'course_title': course.title,
                'plan_name': dict(CoursePlanType.choices)[CoursePlanType.ONE_MONTH],
                'payment_type': 'link'
            }
        }
        
        # Create payment link
        print("Creating payment link...")
        start_time = time.time()
        
        razorpay_response = razorpay_service.create_payment_link(payment_link_data)
        
        end_time = time.time()
        print(f"✅ Payment link created in {end_time - start_time:.2f} seconds")
        print(f"Response: {razorpay_response}")
        
        # Update payment order
        payment_link_id = razorpay_response.get('id')
        if payment_link_id:
            payment_order.razorpay_order_id = payment_link_id
            payment_order.save()
            print(f"Payment order updated with ID: {payment_link_id}")
        
        # Return result (without email)
        result = {
            'success': True,
            'message': 'Payment link created successfully.',
            'reference_id': reference_id,
            'payment_order_id': payment_order.id,
            'email_sent': False,
            'payment_link': razorpay_response.get('short_url')
        }
        
        print(f"✅ Result: {result}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Testing without email...")
    success = test_without_email()
    
    if success:
        print("\n🎉 Payment link creation works without email!")
    else:
        print("\n❌ Payment link creation failed.") 