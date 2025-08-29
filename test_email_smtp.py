#!/usr/bin/env python3
"""
Simple SMTP email test script to check email configuration.
"""

import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

def test_smtp_connection():
    """Test SMTP connection and email sending"""
    print("🔍 Testing SMTP email configuration...")
    
    # Get email settings from environment variables
    email_host = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
    email_port = int(os.environ.get('EMAIL_PORT', 587))
    email_use_tls = os.environ.get('EMAIL_USE_TLS', 'True').lower() == 'true'
    email_host_user = os.environ.get('EMAIL_HOST_USER', '')
    email_host_password = os.environ.get('EMAIL_HOST_PASSWORD', '')
    default_from_email = os.environ.get('DEFAULT_FROM_EMAIL', email_host_user)
    
    print(f"📧 Email Configuration:")
    print(f"   Host: {email_host}")
    print(f"   Port: {email_port}")
    print(f"   TLS: {email_use_tls}")
    print(f"   User: {email_host_user}")
    print(f"   Password: {'Set' if email_host_password else 'Not set'}")
    print(f"   From Email: {default_from_email}")
    
    if not email_host_user or not email_host_password:
        print("❌ Email credentials not configured!")
        return False
    
    try:
        # Test SMTP connection
        print(f"\n🔗 Testing SMTP connection to {email_host}:{email_port}...")
        
        if email_use_tls:
            context = ssl.create_default_context()
            server = smtplib.SMTP(email_host, email_port, timeout=10)
            server.starttls(context=context)
        else:
            server = smtplib.SMTP(email_host, email_port, timeout=10)
        
        # Login
        print("🔐 Attempting login...")
        server.login(email_host_user, email_host_password)
        print("✅ SMTP login successful!")
        
        # Test email sending
        print("📤 Testing email sending...")
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = default_from_email
        msg['To'] = email_host_user  # Send to self for testing
        msg['Subject'] = "SMTP Test Email - Payment Link System"
        
        body = """
This is a test email from your payment link system.

If you receive this email, your SMTP configuration is working correctly.

Test Details:
- Timestamp: {timestamp}
- SMTP Host: {host}
- SMTP Port: {port}
- TLS Enabled: {tls}

This email was sent automatically to verify your email configuration.
        """.format(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            host=email_host,
            port=email_port,
            tls=email_use_tls
        )
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        text = msg.as_string()
        server.sendmail(default_from_email, email_host_user, text)
        
        print("✅ Test email sent successfully!")
        print(f"📧 Email sent to: {email_host_user}")
        
        # Close connection
        server.quit()
        print("✅ SMTP connection closed successfully!")
        
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP Authentication failed: {e}")
        print("💡 Common solutions:")
        print("   - Check if you're using an App Password for Gmail")
        print("   - Verify your email and password are correct")
        print("   - Enable 2-factor authentication and generate an App Password")
        return False
        
    except smtplib.SMTPConnectError as e:
        print(f"❌ SMTP Connection failed: {e}")
        print("💡 Common solutions:")
        print("   - Check if the SMTP host and port are correct")
        print("   - Verify your internet connection")
        print("   - Check if the SMTP server is accessible")
        return False
        
    except smtplib.SMTPException as e:
        print(f"❌ SMTP Error: {e}")
        return False
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def check_environment_variables():
    """Check if required environment variables are set"""
    print("🔍 Checking environment variables...")
    
    required_vars = [
        'EMAIL_HOST',
        'EMAIL_HOST_USER', 
        'EMAIL_HOST_PASSWORD'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.environ.get(var)
        if not value:
            missing_vars.append(var)
        else:
            print(f"✅ {var}: {'Set' if var == 'EMAIL_HOST_PASSWORD' else value}")
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("💡 Please set these environment variables:")
        for var in missing_vars:
            print(f"   export {var}=your_value")
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 Starting SMTP Email Test...\n")
    
    # Check environment variables
    if not check_environment_variables():
        print("\n❌ Environment variables not properly configured!")
        exit(1)
    
    print("\n" + "="*50)
    
    # Test SMTP connection
    success = test_smtp_connection()
    
    print("\n" + "="*50)
    
    if success:
        print("🎉 Email configuration is working correctly!")
        print("💡 Your payment link emails should now be delivered.")
    else:
        print("❌ Email configuration has issues!")
        print("💡 Please fix the SMTP configuration before generating payment links.") 