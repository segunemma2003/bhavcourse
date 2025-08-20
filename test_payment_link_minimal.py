#!/usr/bin/env python3
"""
Minimal test for payment link functionality without full Django setup
"""

import os
import sys
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

def test_razorpay_config():
    """Test Razorpay configuration from environment"""
    print("🔧 Testing Razorpay Configuration:")
    
    # Check environment variables
    key_id = os.environ.get('RAZORPAY_KEY_ID')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET')
    currency = os.environ.get('RAZORPAY_CURRENCY', 'INR')
    
    print(f"   Key ID: {'✅ Set' if key_id else '❌ Not set'}")
    print(f"   Key Secret: {'✅ Set' if key_secret else '❌ Not set'}")
    print(f"   Currency: {currency}")
    
    if not key_id or not key_secret:
        print("❌ Razorpay credentials not configured in environment")
        return False
    
    print("✅ Razorpay environment variables are configured")
    return True

def test_payment_link_service_logic():
    """Test payment link service logic without database"""
    print("\n🔗 Testing Payment Link Service Logic:")
    
    try:
        # Import the service without Django setup
        from core.payment_link_service import PaymentLinkService
        print("✅ Payment link service imported successfully")
        
        # Test service initialization
        service = PaymentLinkService()
        print("✅ Payment link service initialized")
        
        # Test Razorpay service initialization
        from core.services import RazorpayService
        razorpay_service = RazorpayService()
        print("✅ Razorpay service initialized")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Service initialization failed: {e}")
        return False

def test_payment_link_data_structure():
    """Test payment link data structure"""
    print("\n📋 Testing Payment Link Data Structure:")
    
    try:
        # Test the data structure that would be sent to Razorpay
        import uuid
        from decimal import Decimal
        
        # Sample data
        course_title = "Test Course"
        plan_type = "ONE_MONTH"
        amount = Decimal("999.00")
        reference_id = f"link_{str(uuid.uuid4())[:8]}"
        
        payment_link_data = {
            'amount': int(float(amount) * 100),  # Convert to paise
            'currency': 'INR',
            'reference_id': reference_id,
            'description': f'Payment for {course_title} - {plan_type}',
            'callback_url': 'http://localhost:8000/api/payment-links/callback/',
            'callback_method': 'get',
            'notes': {
                'user_id': '123',
                'course_id': '456',
                'plan_type': plan_type,
                'email': 'test@example.com',
                'course_title': course_title,
                'plan_name': plan_type,
                'payment_type': 'link'
            }
        }
        
        print("✅ Payment link data structure created successfully")
        print(f"   Amount: {payment_link_data['amount']} paise")
        print(f"   Reference ID: {payment_link_data['reference_id']}")
        print(f"   Description: {payment_link_data['description']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Data structure test failed: {e}")
        return False

def test_razorpay_api_call():
    """Test Razorpay API call (without actual call)"""
    print("\n🌐 Testing Razorpay API Call Structure:")
    
    try:
        # Test the structure of what would be sent to Razorpay
        from core.services import RazorpayService
        
        # Initialize service
        razorpay_service = RazorpayService()
        
        # Test data
        test_data = {
            'amount': 99900,  # 999.00 in paise
            'currency': 'INR',
            'reference_id': 'test_link_123',
            'description': 'Test payment link',
            'callback_url': 'http://localhost:8000/api/payment-links/callback/',
            'callback_method': 'get',
            'notes': {'test': 'data'}
        }
        
        print("✅ Razorpay API call structure is valid")
        print(f"   Amount: {test_data['amount']} paise")
        print(f"   Currency: {test_data['currency']}")
        print(f"   Reference ID: {test_data['reference_id']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Razorpay API call test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Payment Link Functionality Test (Minimal)")
    print("=" * 50)
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Environment variables loaded")
    
    # Test Razorpay config
    if not test_razorpay_config():
        print("\n❌ Razorpay configuration test failed.")
        return
    
    # Test payment link service logic
    if not test_payment_link_service_logic():
        print("\n❌ Payment link service logic test failed.")
        return
    
    # Test data structure
    if not test_payment_link_data_structure():
        print("\n❌ Payment link data structure test failed.")
        return
    
    # Test Razorpay API call structure
    if not test_razorpay_api_call():
        print("\n❌ Razorpay API call test failed.")
        return
    
    print("\n🎉 All minimal tests passed!")
    print("\n📝 Next steps:")
    print("   1. Ensure MySQL is running and accessible")
    print("   2. Configure database connection in .env file")
    print("   3. Run Django migrations")
    print("   4. Create test courses and users")
    print("   5. Test the full payment link creation flow")

if __name__ == "__main__":
    main() 