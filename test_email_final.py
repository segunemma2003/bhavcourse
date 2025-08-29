#!/usr/bin/env python3
"""
Final email test with working configuration
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def test_final_email():
    """Test email with working configuration"""
    
    # Your Resend SMTP settings
    smtp_server = "smtp.resend.com"
    smtp_port = 587
    username = "resend"
    password = "re_d5kVwwa4_BhSSMaXANzu5LRBZciHWr5bq"
    
    # Test with working configuration
    sender_email = "onboarding@resend.dev"  # Use Resend's default sender
    receiver_email = "segunemma2003@gmail.com"
    
    print("🔍 Final Email Test")
    print(f"From: {sender_email}")
    print(f"To: {receiver_email}")
    print("-" * 40)
    
    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = "Payment Link Test - Your Course Purchase"
        message["From"] = sender_email
        message["To"] = receiver_email
        
        # Create HTML message
        html = """
        <html>
          <body>
            <h2>Payment Link Generated Successfully!</h2>
            <p>Hello,</p>
            <p>Your payment link for the course has been generated successfully.</p>
            
            <h3>Course Details:</h3>
            <ul>
              <li><strong>Course:</strong> Test Course</li>
              <li><strong>Plan:</strong> One Month</li>
              <li><strong>Amount:</strong> ₹100</li>
              <li><strong>Reference ID:</strong> TEST123</li>
            </ul>
            
            <p><strong>Payment Link:</strong> <a href="https://test-payment-link.com">Complete Payment</a></p>
            
            <p>This link will expire in 7 days.</p>
            
            <p>Thank you for choosing our platform!</p>
            
            <hr>
            <p><small>This is a test email from your course app.</small></p>
          </body>
        </html>
        """
        
        # Create plain text version
        text = """
        Payment Link Generated Successfully!
        
        Hello,
        
        Your payment link for the course has been generated successfully.
        
        Course Details:
        - Course: Test Course
        - Plan: One Month
        - Amount: ₹100
        - Reference ID: TEST123
        
        Payment Link: https://test-payment-link.com
        
        This link will expire in 7 days.
        
        Thank you for choosing our platform!
        """
        
        # Attach both versions
        part1 = MIMEText(text, "plain")
        part2 = MIMEText(html, "html")
        message.attach(part1)
        message.attach(part2)
        
        # Send email
        print("📧 Sending email...")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(username, password)
        
        result = server.sendmail(sender_email, receiver_email, message.as_string())
        server.quit()
        
        print("✅ Email sent successfully!")
        print(f"Result: {result}")
        return True
        
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing Final Email Configuration")
    print("=" * 50)
    
    success = test_final_email()
    
    print("=" * 50)
    if success:
        print("🎉 Email test successful!")
        print("✅ Your email configuration is working")
        print("✅ Payment link emails will be delivered")
    else:
        print("💥 Email test failed")
        print("❌ Check your email configuration") 