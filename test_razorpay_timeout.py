#!/usr/bin/env python3
"""
Simple test to check Razorpay API timeout.
"""

import os
import sys
import django
import time
import requests

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

from django.conf import settings

def test_razorpay_connection():
    """Test Razorpay API connection"""
    print("🔍 Testing Razorpay API connection...")
    
    try:
        # Check if credentials are set
        if not hasattr(settings, 'RAZORPAY_KEY_ID') or not settings.RAZORPAY_KEY_ID:
            print("❌ RAZORPAY_KEY_ID not set")
            return False
            
        if not hasattr(settings, 'RAZORPAY_KEY_SECRET') or not settings.RAZORPAY_KEY_SECRET:
            print("❌ RAZORPAY_KEY_SECRET not set")
            return False
        
        print(f"✅ Razorpay credentials found")
        
        # Test basic HTTP connection to Razorpay
        print("🌐 Testing HTTP connection to Razorpay...")
        start_time = time.time()
        
        try:
            response = requests.get('https://api.razorpay.com/v1/', timeout=10)
            end_time = time.time()
            print(f"✅ HTTP connection successful in {end_time - start_time:.2f} seconds")
            print(f"   Status code: {response.status_code}")
        except requests.exceptions.Timeout:
            print("❌ HTTP connection timed out")
            return False
        except requests.exceptions.RequestException as e:
            print(f"❌ HTTP connection failed: {str(e)}")
            return False
        
        # Test Razorpay client initialization
        print("🔧 Testing Razorpay client initialization...")
        try:
            import razorpay
            client = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
            )
            print("✅ Razorpay client initialized")
        except Exception as e:
            print(f"❌ Razorpay client error: {str(e)}")
            return False
        
        # Test a simple API call
        print("📞 Testing Razorpay API call...")
        try:
            start_time = time.time()
            # Try to get account details (this should work with valid credentials)
            account = client.account.fetch()
            end_time = time.time()
            print(f"✅ API call successful in {end_time - start_time:.2f} seconds")
            print(f"   Account ID: {account.get('id')}")
        except Exception as e:
            print(f"❌ API call failed: {str(e)}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ General error: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 Starting Razorpay connection test...")
    success = test_razorpay_connection()
    
    if success:
        print("\n🎉 Razorpay connection works!")
    else:
        print("\n❌ Razorpay connection failed.") 