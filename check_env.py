#!/usr/bin/env python3
"""
Check environment variables and settings.
"""

import os
import sys
import django

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

from django.conf import settings

def check_environment():
    """Check environment variables"""
    print("🔍 Checking environment variables...")
    
    # Check .env file
    env_file = '/var/www/bhavani/.env'
    if os.path.exists(env_file):
        print(f"✅ .env file exists: {env_file}")
        with open(env_file, 'r') as f:
            content = f.read()
            if 'BASE_URL' in content:
                print("✅ BASE_URL found in .env")
            else:
                print("❌ BASE_URL not found in .env")
    else:
        print(f"❌ .env file not found: {env_file}")
    
    # Check Django settings
    print(f"\n📋 Django settings:")
    print(f"   DEBUG: {getattr(settings, 'DEBUG', 'Not set')}")
    print(f"   ALLOWED_HOSTS: {getattr(settings, 'ALLOWED_HOSTS', 'Not set')}")
    print(f"   BASE_URL: {getattr(settings, 'BASE_URL', 'Not set')}")
    print(f"   RAZORPAY_KEY_ID: {'Set' if hasattr(settings, 'RAZORPAY_KEY_ID') and settings.RAZORPAY_KEY_ID else 'Not set'}")
    print(f"   RAZORPAY_KEY_SECRET: {'Set' if hasattr(settings, 'RAZORPAY_KEY_SECRET') and settings.RAZORPAY_KEY_SECRET else 'Not set'}")
    
    # Test callback URL generation
    print(f"\n🔗 Callback URL test:")
    base_url = getattr(settings, 'BASE_URL', 'https://api.pixelcraftsbybhavani.com')
    callback_url = f"{base_url}/api/payment-links/callback/"
    print(f"   Base URL: {base_url}")
    print(f"   Callback URL: {callback_url}")

if __name__ == "__main__":
    check_environment() 