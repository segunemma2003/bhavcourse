#!/usr/bin/env python3
"""
Detailed debug script to identify exactly where create_payment_link_request hangs.
"""

import os
import sys
import django
import time
import uuid

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

def debug_payment_link_request():
    """Debug the create_payment_link_request method step by step"""
    print("🔍 Debugging create_payment_link_request step by step...")
    
    try:
        from core.models import PaymentOrder, Course, CoursePlanType
        from core.payment_link_service import PaymentLinkService
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        user = User.objects.first()
        course = Course.objects.first()
        
        if not user or not course:
            print("❌ No user or course found")
            return False
        
        service = PaymentLinkService()
        
        # Step 1: Generate reference ID
        print("1. Generating reference ID...")
        reference_id = f"link_{str(uuid.uuid4())[:8]}"
        print(f"   ✅ Reference ID: {reference_id}")
        
        # Step 2: Get base URL
        print("2. Getting base URL...")
        from django.conf import settings
        base_url = getattr(settings, 'BASE_URL', 'https://api.pixelcraftsbybhavani.com')
        callback_url = f"{base_url}/api/payment-links/callback/"
        print(f"   ✅ Base URL: {base_url}")
        print(f"   ✅ Callback URL: {callback_url}")
        
        # Step 3: Create payment order
        print("3. Creating payment order...")
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
        print(f"   ✅ Payment order created: {payment_order.id}")
        
        # Step 4: Prepare payment link data
        print("4. Preparing payment link data...")
        payment_link_data = {
            'amount': int(float(100.00) * 100),
            'currency': 'INR',
            'reference_id': reference_id,
            'description': f'Payment for {course.title} - {dict(CoursePlanType.choices)[CoursePlanType.ONE_MONTH]}',
            'callback_url': callback_url,
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
        print(f"   ✅ Payment link data prepared")
        print(f"   Amount: {payment_link_data['amount']} paise")
        print(f"   Description: {payment_link_data['description']}")
        
        # Step 5: Create payment link via Razorpay
        print("5. Creating payment link via Razorpay...")
        start_time = time.time()
        
        razorpay_response = service.razorpay_service.create_payment_link(payment_link_data)
        
        end_time = time.time()
        print(f"   ✅ Razorpay call completed in {end_time - start_time:.2f} seconds")
        print(f"   Response: {razorpay_response}")
        
        # Step 6: Update payment order
        print("6. Updating payment order...")
        payment_link_id = razorpay_response.get('id')
        if payment_link_id:
            payment_order.razorpay_order_id = payment_link_id
            payment_order.save()
            print(f"   ✅ Payment order updated with ID: {payment_link_id}")
        else:
            print(f"   ⚠️  No payment link ID received")
        
        # Step 7: Send email (this might be where it hangs)
        print("7. Sending email...")
        try:
            email_sent = service._send_payment_link_email(
                user=user,
                course=course,
                plan_type=CoursePlanType.ONE_MONTH,
                amount=100.00,
                payment_link=razorpay_response.get('short_url'),
                reference_id=reference_id
            )
            print(f"   ✅ Email sent: {email_sent}")
        except Exception as e:
            print(f"   ❌ Email error: {str(e)}")
        
        # Step 8: Create notification
        print("8. Creating notification...")
        try:
            from core.models import Notification
            Notification.objects.create(
                user=user,
                title="Payment Link Generated",
                message=f"Payment link for {course.title} has been sent to your email.",
                notification_type='PAYMENT',
                is_seen=False
            )
            print(f"   ✅ Notification created")
        except Exception as e:
            print(f"   ❌ Notification error: {str(e)}")
        
        # Step 9: Return result
        print("9. Preparing result...")
        result = {
            'success': True,
            'message': 'Payment link request initiated successfully. Check your email for the payment link.',
            'reference_id': reference_id,
            'payment_order_id': payment_order.id,
            'email_sent': email_sent if 'email_sent' in locals() else False,
            'payment_link': razorpay_response.get('short_url')
        }
        print(f"   ✅ Result prepared: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting detailed debug...")
    success = debug_payment_link_request()
    
    if success:
        print("\n🎉 Payment link creation works!")
    else:
        print("\n❌ Payment link creation failed.") 