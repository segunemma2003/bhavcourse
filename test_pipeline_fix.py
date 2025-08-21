#!/usr/bin/env python3
"""
Test script to verify pipeline fix is working
Run this to test if the MySQL client and migrations are working correctly
"""

import os
import sys
import django

def test_mysql_client():
    """Test if MySQL client is working"""
    try:
        import MySQLdb
        print("✅ MySQL client imported successfully")
        return True
    except ImportError as e:
        print(f"❌ MySQL client import failed: {e}")
        return False

def test_django_setup():
    """Test Django setup"""
    try:
        # Set up Django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
        django.setup()
        print("✅ Django setup successful")
        return True
    except Exception as e:
        print(f"❌ Django setup failed: {e}")
        return False

def test_database_connection():
    """Test database connection"""
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            if result[0] == 1:
                print("✅ Database connection successful")
                return True
            else:
                print("❌ Database connection test failed")
                return False
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def test_payment_link_service():
    """Test payment link service"""
    try:
        from core.payment_link_service import PaymentLinkService
        service = PaymentLinkService()
        print("✅ Payment link service imported successfully")
        return True
    except Exception as e:
        print(f"❌ Payment link service test failed: {e}")
        return False

def test_models():
    """Test model imports"""
    try:
        from core.models import User, Course, PaymentOrder, PaymentLinkRequest
        print("✅ All models imported successfully")
        return True
    except Exception as e:
        print(f"❌ Model import failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Running pipeline fix verification tests...\n")
    
    tests = [
        ("MySQL Client", test_mysql_client),
        ("Django Setup", test_django_setup),
        ("Database Connection", test_database_connection),
        ("Payment Link Service", test_payment_link_service),
        ("Models", test_models),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"Testing {test_name}...")
        if test_func():
            passed += 1
        print()
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Pipeline fix is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 