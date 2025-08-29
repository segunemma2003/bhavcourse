#!/usr/bin/env python3
"""
Detailed test script for Resend SMTP with better error handling
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def test_resend_detailed():
    """Test Resend SMTP with detailed error handling"""
    
    # Your Resend SMTP settings
    smtp_server = "smtp.resend.com"
    smtp_port = 587
    username = "resend"
    password = "re_d5kVwwa4_BhSSMaXANzu5LRBZciHWr5bq"
    
    # Test email details
    sender_email = "noreply@bybhavani.com"  # Your verified domain
    receiver_email = "segunemma2003@gmail.com"  # Your email for testing
    
    print("🔍 Detailed Resend SMTP Test")
    print(f"SMTP Server: {smtp_server}")
    print(f"SMTP Port: {smtp_port}")
    print(f"Username: {username}")
    print(f"From Email: {sender_email}")
    print(f"To Email: {receiver_email}")
    print("-" * 50)
    
    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = "Test Email from Resend SMTP - Local Test"
        message["From"] = sender_email
        message["To"] = receiver_email
        
        # Simple text message
        text = "This is a test email sent using Resend SMTP from your local machine."
        
        # Turn into MIMEText object
        part1 = MIMEText(text, "plain")
        message.attach(part1)
        
        print("📧 Attempting to connect to SMTP server...")
        
        # Create SMTP session with debug
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.set_debuglevel(1)  # Enable debug output
        
        print("🔐 Starting TLS...")
        server.starttls()
        print("✅ TLS connection established")
        
        # Login to the server
        print("🔑 Attempting to login...")
        server.login(username, password)
        print("✅ Login successful")
        
        # Send email
        print("📤 Sending email...")
        result = server.sendmail(sender_email, receiver_email, message.as_string())
        print(f"✅ Email sent successfully! Result: {result}")
        
        # Close connection
        server.quit()
        print("🔒 Connection closed")
        
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ Authentication failed: {e}")
        print(f"   Error code: {e.smtp_code}")
        print(f"   Error message: {e.smtp_error}")
        return False
    except smtplib.SMTPRecipientsRefused as e:
        print(f"❌ Recipient refused: {e}")
        return False
    except smtplib.SMTPSenderRefused as e:
        print(f"❌ Sender refused: {e}")
        return False
    except smtplib.SMTPDataError as e:
        print(f"❌ Data error: {e}")
        print(f"   Error code: {e.smtp_code}")
        print(f"   Error message: {e.smtp_error}")
        return False
    except smtplib.SMTPConnectError as e:
        print(f"❌ Connection error: {e}")
        return False
    except smtplib.SMTPHeloError as e:
        print(f"❌ HELO error: {e}")
        return False
    except smtplib.SMTPNotSupportedError as e:
        print(f"❌ Not supported error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        print(f"   Error type: {type(e)}")
        return False

def test_resend_api_alternative():
    """Test using Resend API as an alternative to SMTP"""
    print("\n🔄 Testing Resend API as alternative...")
    
    try:
        import requests
        
        api_key = "re_d5kVwwa4_BhSSMaXANzu5LRBZciHWr5bq"
        url = "https://api.resend.com/emails"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "from": "noreply@bybhavani.com",  # Your verified domain
            "to": ["segunemma2003@gmail.com"],  # Your email for testing
            "subject": "Test Email from Resend API",
            "html": "<p>This is a test email sent using Resend API.</p>"
        }
        
        print("📧 Sending via Resend API...")
        response = requests.post(url, headers=headers, json=data)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ API email sent successfully!")
            return True
        else:
            print(f"❌ API email failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ API test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting Detailed Resend Email Test")
    print("=" * 60)
    
    # Test SMTP
    smtp_success = test_resend_detailed()
    
    # Test API as alternative
    api_success = test_resend_api_alternative()
    
    print("=" * 60)
    if smtp_success:
        print("🎉 SMTP test completed successfully!")
    elif api_success:
        print("🎉 API test completed successfully!")
        print("💡 Consider using Resend API instead of SMTP")
    else:
        print("💥 Both tests failed!")
        print("\nPossible solutions:")
        print("1. Check if your Resend API key is valid")
        print("2. Verify your domain in Resend dashboard")
        print("3. Try using Resend API instead of SMTP")
        print("4. Check if your account has sending permissions") 