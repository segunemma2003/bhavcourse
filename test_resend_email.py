#!/usr/bin/env python3
"""
Test Resend SMTP email configuration locally
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def test_resend_smtp():
    """Test Resend SMTP connection and email sending"""
    
    # Your Resend SMTP settings
    smtp_server = "smtp.resend.com"
    smtp_port = 587
    username = "resend"
    password = "re_d5kVwwa4_BhSSMaXANzu5LRBZciHWr5bq"
    
    # Test email details
    sender_email = "onboarding@resend.dev"  # Use Resend's default sender for testing
    receiver_email = "segunemma2003@gmail.com"  # Your actual email for testing
    
    print("🔍 Testing Resend SMTP configuration...")
    print(f"SMTP Server: {smtp_server}")
    print(f"SMTP Port: {smtp_port}")
    print(f"Username: {username}")
    print(f"From Email: {sender_email}")
    print(f"To Email: {receiver_email}")
    print("-" * 50)
    
    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = "Test Email from Resend SMTP"
        message["From"] = sender_email
        message["To"] = receiver_email
        
        # Create the plain-text and HTML version of your message
        text = """\
        Hi,
        
        This is a test email sent using Resend SMTP.
        
        If you receive this, the SMTP configuration is working correctly!
        
        Best regards,
        Your App
        """
        
        html = """\
        <html>
          <body>
            <p>Hi,<br>
               This is a <b>test email</b> sent using Resend SMTP.<br>
               If you receive this, the SMTP configuration is working correctly!
            </p>
            <p>Best regards,<br>
               Your App
            </p>
          </body>
        </html>
        """
        
        # Turn these into plain/html MIMEText objects
        part1 = MIMEText(text, "plain")
        part2 = MIMEText(html, "html")
        
        # Add HTML/plain-text parts to MIMEMultipart message
        message.attach(part1)
        message.attach(part2)
        
        # Create secure connection with server and send email
        print("📧 Attempting to connect to SMTP server...")
        
        # Create SMTP session
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Secure the connection
        
        print("🔐 TLS connection established")
        
        # Login to the server
        print("🔑 Attempting to login...")
        server.login(username, password)
        print("✅ Login successful")
        
        # Send email
        print("📤 Sending email...")
        server.sendmail(sender_email, receiver_email, message.as_string())
        print("✅ Email sent successfully!")
        
        # Close connection
        server.quit()
        print("🔒 Connection closed")
        
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ Authentication failed: {e}")
        return False
    except smtplib.SMTPRecipientsRefused as e:
        print(f"❌ Recipient refused: {e}")
        return False
    except smtplib.SMTPSenderRefused as e:
        print(f"❌ Sender refused: {e}")
        return False
    except smtplib.SMTPDataError as e:
        print(f"❌ Data error: {e}")
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
        return False

if __name__ == "__main__":
    print("🚀 Starting Resend SMTP Test")
    print("=" * 50)
    
    success = test_resend_smtp()
    
    print("=" * 50)
    if success:
        print("🎉 SMTP test completed successfully!")
        print("✅ Your Resend SMTP configuration appears to be working")
    else:
        print("💥 SMTP test failed!")
        print("❌ There are issues with your Resend SMTP configuration")
        print("\nCommon issues:")
        print("1. API key might be invalid or expired")
        print("2. Sender domain might not be verified in Resend")
        print("3. Network connectivity issues")
        print("4. Firewall blocking SMTP connections") 