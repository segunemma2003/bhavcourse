#!/usr/bin/env python3
"""
Debug script with timeout to identify hanging issues.
"""

import os
import sys
import django
import time
import signal

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")

def test_with_timeout():
    """Test with timeout"""
    print("🔍 Testing with 10-second timeout...")
    
    try:
        from core.payment_link_service import PaymentLinkService
        from core.models import Course, CoursePlanType
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        user = User.objects.first()
        course = Course.objects.first()
        
        if not user or not course:
            print("❌ No user or course found")
            return False
        
        service = PaymentLinkService()
        
        # Set timeout for 10 seconds
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)
        
        print("📞 Creating payment link (10-second timeout)...")
        start_time = time.time()
        
        result = service.create_payment_link_request(
            user=user,
            course_id=course.id,
            plan_type=CoursePlanType.ONE_MONTH,
            amount=100.00
        )
        
        # Cancel the alarm
        signal.alarm(0)
        
        end_time = time.time()
        print(f"✅ Completed in {end_time - start_time:.2f} seconds")
        print(f"Result: {result}")
        
        return result.get('success', False)
        
    except TimeoutError:
        print("❌ Operation timed out after 10 seconds")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 Testing with timeout...")
    success = test_with_timeout()
    
    if success:
        print("\n🎉 Payment link creation works!")
    else:
        print("\n❌ Payment link creation failed or timed out.") 