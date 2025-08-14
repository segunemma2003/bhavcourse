# Payment Link Integration Guide

This guide explains how to set up and use payment links as an alternative payment method in your Django API.

## Overview

The Payment Link integration provides a complete solution for generating payment links and sending them via email. Users can click the link to complete their payment using Razorpay's hosted payment page.

## Features

1. **Payment Link Generation**: Create Razorpay payment links
2. **Email Notifications**: Send payment links to users via email
3. **Payment Verification**: Verify payments made through links
4. **Status Tracking**: Track payment link status
5. **Automatic Enrollment**: Process enrollments after successful payment

## API Endpoints

### 1. Create Payment Link Request

**POST** `/api/payment-links/create/`

Creates a payment link request and sends email to user.

#### Request Body

```json
{
  "course_id": 123,
  "plan_type": "ONE_MONTH",
  "amount": 999.0
}
```

#### Response

**Success (201 Created):**

```json
{
  "success": true,
  "message": "Payment link request initiated successfully. Check your email for the payment link.",
  "reference_id": "link_a1b2c3d4",
  "payment_order_id": 456,
  "email_sent": true
}
```

**Error (400 Bad Request):**

```json
{
  "error": "Course not found"
}
```

### 2. Check Payment Link Status

**GET** `/api/payment-links/status/?reference_id=link_a1b2c3d4`

Check the status of a payment link request.

#### Response

**Success (200 OK):**

```json
{
  "reference_id": "link_a1b2c3d4",
  "status": "LINK_REQUESTED",
  "course_title": "Advanced Python Programming",
  "plan_type": "One Month",
  "amount": 999.0,
  "created_at": "2024-01-15T10:30:00Z",
  "paid_at": null
}
```

### 3. Verify Payment Link Payment

**POST** `/api/payment-links/verify/?payment_id=pay_123456&reference_id=link_a1b2c3d4`

Verify payment made through payment link.

#### Response

**Success (200 OK):**

```json
{
  "success": true,
  "message": "Payment verified and enrollment completed",
  "enrollment_id": 789,
  "purchase_id": 101
}
```

### 4. Payment Link Callback

**GET** `/api/payment-links/callback/?razorpay_payment_id=pay_123456&razorpay_payment_link_id=plink_123456&razorpay_payment_link_reference_id=link_a1b2c3d4`

Callback URL for Razorpay payment link payments.

## Database Models

### Updated PaymentOrder Model

The PaymentOrder model has been extended with payment link fields:

```python
class PaymentOrder(models.Model):
    # ... existing fields ...

    # Payment link fields
    reference_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    payment_method = models.CharField(max_length=20, default='RAZORPAY',
        choices=(
            ('RAZORPAY', 'Razorpay'),
            ('PAYMENT_LINK', 'Payment Link')
        )
    )
    plan_type = models.CharField(max_length=20, choices=CoursePlanType.choices, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    # Updated status choices
    status = models.CharField(max_length=20, default='CREATED',
        choices=(
            ('CREATED', 'Created'),
            ('PAID', 'Paid'),
            ('FAILED', 'Failed'),
            ('REFUNDED', 'Refunded'),
            ('LINK_REQUESTED', 'Link Requested'),
            ('LINK_EXPIRED', 'Link Expired')
        )
    )
```

## Setup Instructions

### 1. Run Database Migration

```bash
python manage.py makemigrations
python manage.py migrate
```

### 2. Configure Email Settings

Add email configuration to your `settings.py`:

```python
# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'  # or your SMTP server
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'
DEFAULT_FROM_EMAIL = 'your-email@gmail.com'

# Support email for payment links
SUPPORT_EMAIL = 'support@yourapp.com'

# Frontend URL for redirects
FRONTEND_URL = 'https://yourapp.com'
```

### 3. Configure Razorpay Settings

Ensure your Razorpay settings are configured:

```python
# Razorpay Configuration
RAZORPAY_KEY_ID = 'your-razorpay-key-id'
RAZORPAY_KEY_SECRET = 'your-razorpay-key-secret'
RAZORPAY_CURRENCY = 'INR'
BASE_URL = 'https://yourapi.com'
```

## Usage Examples

### 1. Create Payment Link Request

```python
import requests

# Create payment link request
response = requests.post(
    'https://yourapi.com/api/payment-links/create/',
    headers={
        'Authorization': 'Token YOUR_TOKEN',
        'Content-Type': 'application/json'
    },
    json={
        'course_id': 123,
        'plan_type': 'ONE_MONTH',
        'amount': 999.00
    }
)

if response.status_code == 201:
    data = response.json()
    print(f"Payment link created: {data['reference_id']}")
    print(f"Email sent: {data['email_sent']}")
```

### 2. Check Payment Status

```python
# Check payment link status
response = requests.get(
    'https://yourapi.com/api/payment-links/status/',
    headers={'Authorization': 'Token YOUR_TOKEN'},
    params={'reference_id': 'link_a1b2c3d4'}
)

if response.status_code == 200:
    data = response.json()
    print(f"Status: {data['status']}")
    print(f"Amount: ₹{data['amount']}")
```

### 3. Verify Payment

```python
# Verify payment (usually called by Razorpay callback)
response = requests.post(
    'https://yourapi.com/api/payment-links/verify/',
    params={
        'payment_id': 'pay_123456',
        'reference_id': 'link_a1b2c3d4'
    }
)

if response.status_code == 200:
    data = response.json()
    print(f"Payment verified: {data['success']}")
    print(f"Enrollment ID: {data['enrollment_id']}")
```

## Email Templates

### HTML Template (`templates/emails/payment_link.html`)

The HTML template includes:

- Professional styling
- Course details
- Payment button
- Expiry warning
- Support contact information

### Text Template (`templates/emails/payment_link.txt`)

Plain text version for email clients that don't support HTML.

## Payment Flow

### 1. User Requests Payment Link

```
User → API → Payment Link Service → Razorpay → Email → User
```

### 2. User Completes Payment

```
User → Payment Link → Razorpay → Callback → API → Enrollment
```

### 3. Payment Verification

```
Razorpay → Callback URL → Payment Verification → Database Update
```

## Security Features

### 1. Reference ID Validation

- Unique reference IDs for each payment link
- Prevents duplicate processing
- Links payments to specific orders

### 2. Payment Verification

- Server-side verification with Razorpay
- Validates payment status
- Prevents fraud

### 3. Email Security

- Secure email delivery
- Expiry dates for payment links
- Support contact for issues

## Error Handling

### Common Error Scenarios

1. **Invalid Course ID**: Returns 400 with error message
2. **Email Send Failure**: Logs error but continues processing
3. **Payment Verification Failure**: Returns appropriate error
4. **Expired Payment Links**: Handled by status tracking

### Error Response Format

```json
{
  "error": "Error description",
  "success": false
}
```

## Monitoring and Logging

### 1. Logging

The system includes comprehensive logging:

- Payment link creation
- Email sending status
- Payment verification
- Error details

### 2. Status Tracking

Track payment link status:

- `LINK_REQUESTED`: Link created and email sent
- `PAID`: Payment completed
- `FAILED`: Payment failed
- `LINK_EXPIRED`: Link expired

## Testing

### 1. Test Payment Link Creation

```bash
curl -X POST https://yourapi.com/api/payment-links/create/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "course_id": 1,
    "plan_type": "ONE_MONTH",
    "amount": 999.00
  }'
```

### 2. Test Status Check

```bash
curl -X GET "https://yourapi.com/api/payment-links/status/?reference_id=link_a1b2c3d4" \
  -H "Authorization: Token YOUR_TOKEN"
```

### 3. Test Payment Verification

```bash
curl -X POST "https://yourapi.com/api/payment-links/verify/?payment_id=pay_123456&reference_id=link_a1b2c3d4"
```

## Benefits

### 1. User Experience

- No need to integrate payment gateway in app
- Professional email templates
- Secure payment processing
- Mobile-friendly payment links

### 2. Business Benefits

- Reduced app complexity
- Better conversion rates
- Automated payment processing
- Detailed tracking and analytics

### 3. Technical Benefits

- Scalable architecture
- Secure payment handling
- Easy integration
- Comprehensive error handling

## Best Practices

### 1. Email Configuration

- Use reliable SMTP service
- Set up proper email templates
- Test email delivery
- Monitor email bounce rates

### 2. Payment Link Management

- Set appropriate expiry dates
- Monitor payment link usage
- Clean up expired links
- Track conversion rates

### 3. Security

- Validate all inputs
- Use HTTPS for all communications
- Monitor for suspicious activity
- Regular security audits

## Troubleshooting

### Common Issues

1. **Email Not Sent**: Check SMTP configuration
2. **Payment Link Expired**: Generate new link
3. **Payment Verification Failed**: Check Razorpay credentials
4. **Callback Not Working**: Verify callback URL configuration

### Debug Steps

1. Check application logs
2. Verify Razorpay configuration
3. Test email delivery
4. Validate payment link generation

This completes the Payment Link integration setup!
