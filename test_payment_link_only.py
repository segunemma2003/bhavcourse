#!/usr/bin/env python3
"""
Test to isolate the payment link creation step.
"""

import os
import sys
import django
import time

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

from core.services import RazorpayService
from django.conf import settings

def test_payment_link_creation():
    """Test only the payment link creation step"""
    print("🔍 Testing payment link creation step...")
    
    try:
        # Initialize Razorpay service
        razorpay_service = RazorpayService()
        
        # Test data
        payment_link_data = {
            'amount': 10000,  # 100 rupees in paise
            'currency': 'INR',
            'reference_id': 'test_ref_123',
            'description': 'Test payment link',
            'callback_url': 'http://localhost:8000/api/payment-links/callback/',
            'callback_method': 'get',
            'notes': {
                'test': True,
                'description': 'Test payment link creation'
            }
        }
        
        print("📞 Creating payment link...")
        start_time = time.time()
        
        # This is where it's likely hanging
        razorpay_response = razorpay_service.create_payment_link(payment_link_data)
        
        end_time = time.time()
        print(f"✅ Payment link created in {end_time - start_time:.2f} seconds")
        print(f"Response: {razorpay_response}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Testing payment link creation...")
    success = test_payment_link_creation()
    
    if success:
        print("\n🎉 Payment link creation works!")
    else:
        print("\n❌ Payment link creation failed.") 