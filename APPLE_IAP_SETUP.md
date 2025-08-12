# Apple In-App Purchase (IAP) Integration Guide

This guide explains how to set up and use Apple In-App Purchase as an alternative payment gateway in your Django API.

## Overview

The Apple IAP integration provides a complete solution for processing in-app purchases through Apple's App Store. The system includes:

1. **Receipt Verification**: Server-side verification of Apple receipts
2. **Product Management**: API endpoints for managing IAP products
3. **Purchase Processing**: Automatic enrollment and subscription management
4. **Webhook Support**: Handling Apple's server-to-server notifications

## API Endpoints

### 1. Verify Apple IAP Receipt

**POST** `/api/apple-iap/verify-receipt/`

Verifies an Apple In-App Purchase receipt and processes the purchase.

#### Request Body

```json
{
  "receipt_data": "base64_encoded_receipt_data",
  "course_id": 123,
  "plan_type": "ONE_MONTH"
}
```

#### Response

**Success (200 OK):**

```json
{
  "success": true,
  "message": "Purchase processed successfully",
  "purchase_id": 456,
  "enrollment_id": 789,
  "transaction_id": "1000000123456789",
  "expiry_date": "2024-02-15T10:30:00Z"
}
```

**Error (400 Bad Request):**

```json
{
  "error": "Invalid receipt data format"
}
```

### 2. Manage Apple IAP Products

**GET** `/api/apple-iap/products/`

Lists all Apple IAP products.

**Query Parameters:**

- `course_id` (optional): Filter products by course ID

**Response:**

```json
[
  {
    "id": 1,
    "product_id": "com.yourapp.course1_monthly",
    "course": 123,
    "course_title": "Advanced Python Programming",
    "plan_type": "ONE_MONTH",
    "plan_name": "One Month",
    "price_usd": "9.99",
    "is_active": true,
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:30:00Z"
  }
]
```

**POST** `/api/apple-iap/products/`

Creates a new Apple IAP product.

**Request Body:**

```json
{
  "product_id": "com.yourapp.course1_monthly",
  "course_id": 123,
  "plan_type": "ONE_MONTH",
  "price_usd": "9.99"
}
```

### 3. Product Management

**GET** `/api/apple-iap/products/{product_id}/`

Retrieves details of a specific product.

**PUT** `/api/apple-iap/products/{product_id}/`

Updates an existing product.

**DELETE** `/api/apple-iap/products/{product_id}/`

Deactivates a product.

### 4. Webhook Handler

**POST** `/api/apple-iap/webhook/`

Handles Apple's server-to-server notifications.

## Database Models

### AppleIAPProduct

Stores Apple IAP product configurations:

```python
class AppleIAPProduct(models.Model):
    product_id = models.CharField(max_length=100, unique=True)
    course = models.ForeignKey(Course, related_name='apple_products')
    plan_type = models.CharField(max_length=20, choices=CoursePlanType.choices)
    price_usd = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### AppleIAPReceipt

Stores receipt verification records:

```python
class AppleIAPReceipt(models.Model):
    purchase = models.OneToOneField(Purchase, related_name='apple_receipt')
    receipt_data = models.TextField()
    verification_response = models.JSONField(default=dict)
    verification_date = models.DateTimeField(auto_now_add=True)
    is_valid = models.BooleanField(default=False)
    environment = models.CharField(max_length=20, choices=[('Production', 'Production'), ('Sandbox', 'Sandbox')])
```

### Updated Purchase Model

The existing Purchase model has been extended with Apple IAP fields:

```python
class Purchase(models.Model):
    # ... existing fields ...

    # Apple IAP fields
    apple_transaction_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    apple_product_id = models.CharField(max_length=100, blank=True, null=True)
    apple_receipt_data = models.TextField(blank=True, null=True)
    apple_verification_status = models.CharField(max_length=20, default='PENDING')
    payment_gateway = models.CharField(max_length=20, default='RAZORPAY')
```

## Setup Instructions

### 1. Apple Developer Account Setup

1. **Create App Store Connect App**:

   - Go to App Store Connect
   - Create a new app
   - Configure in-app purchases

2. **Create In-App Purchase Products**:

   - Add products for each course/plan combination
   - Set product IDs (e.g., `com.yourapp.course1_monthly`)
   - Configure pricing

3. **Generate App-Specific Shared Secret**:
   - Go to App Store Connect → Users and Access → Keys
   - Generate a new key
   - Save the shared secret

### 2. Django Configuration

Add Apple IAP settings to your `settings.py`:

```python
# Apple IAP Configuration
APPLE_IAP_SHARED_SECRET = os.environ.get('APPLE_IAP_SHARED_SECRET', '')
APPLE_IAP_BUNDLE_ID = os.environ.get('APPLE_IAP_BUNDLE_ID', 'com.yourapp')
APPLE_IAP_ENVIRONMENT = os.environ.get('APPLE_IAP_ENVIRONMENT', 'Production')  # or 'Sandbox'
```

### 3. Create Database Migration

Run the migration to create the new models:

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. Configure Products

Create Apple IAP products for your courses:

```python
from core.models import AppleIAPProduct, Course, CoursePlanType

# Example: Create products for a course
course = Course.objects.get(id=1)

AppleIAPProduct.objects.create(
    product_id="com.yourapp.course1_monthly",
    course=course,
    plan_type=CoursePlanType.ONE_MONTH,
    price_usd=9.99
)

AppleIAPProduct.objects.create(
    product_id="com.yourapp.course1_lifetime",
    course=course,
    plan_type=CoursePlanType.LIFETIME,
    price_usd=49.99
)
```

## Client-Side Implementation

### iOS (Swift)

```swift
import StoreKit

class IAPManager: NSObject, SKProductsRequestDelegate, SKPaymentTransactionObserver {

    static let shared = IAPManager()
    private var products: [SKProduct] = []

    func fetchProducts() {
        let productIdentifiers = Set([
            "com.yourapp.course1_monthly",
            "com.yourapp.course1_lifetime"
        ])

        let request = SKProductsRequest(productIdentifiers: productIdentifiers)
        request.delegate = self
        request.start()
    }

    func purchase(product: SKProduct) {
        let payment = SKPayment(product: product)
        SKPaymentQueue.default().add(payment)
    }

    // SKProductsRequestDelegate
    func productsRequest(_ request: SKProductsRequest, didReceive response: SKProductsResponse) {
        self.products = response.products
        // Update UI with products
    }

    // SKPaymentTransactionObserver
    func paymentQueue(_ queue: SKPaymentQueue, updatedTransactions transactions: [SKPaymentTransaction]) {
        for transaction in transactions {
            switch transaction.transactionState {
            case .purchased:
                // Send receipt to Django API
                sendReceiptToAPI(transaction: transaction)
                queue.finishTransaction(transaction)

            case .failed:
                queue.finishTransaction(transaction)

            case .restored:
                // Handle restored purchases
                queue.finishTransaction(transaction)

            default:
                break
            }
        }
    }

    func sendReceiptToAPI(transaction: SKPaymentTransaction) {
        guard let receiptURL = Bundle.main.appStoreReceiptURL,
              let receiptData = try? Data(contentsOf: receiptURL) else {
            return
        }

        let receiptString = receiptData.base64EncodedString()

        let url = URL(string: "https://your-api.com/api/apple-iap/verify-receipt/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Token YOUR_DJANGO_TOKEN", forHTTPHeaderField: "Authorization")

        let body = [
            "receipt_data": receiptString
        ]

        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        URLSession.shared.dataTask(with: request) { data, response, error in
            if let data = data {
                let response = try? JSONSerialization.jsonObject(with: data)
                print("Django API response: \(response)")
            }
        }.resume()
    }
}
```

### Android (Kotlin)

```kotlin
import com.android.billingclient.api.*

class IAPManager(private val activity: Activity) {

    private lateinit var billingClient: BillingClient

    fun setupBilling() {
        billingClient = BillingClient.newBuilder(activity)
            .setListener { billingResult, purchases ->
                if (billingResult.responseCode == BillingClient.BillingResponseCode.OK && purchases != null) {
                    for (purchase in purchases) {
                        handlePurchase(purchase)
                    }
                }
            }
            .enablePendingPurchases()
            .build()

        billingClient.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(billingResult: BillingResult) {
                if (billingResult.responseCode == BillingClient.BillingResponseCode.OK) {
                    // Billing client is ready
                    queryProducts()
                }
            }

            override fun onBillingServiceDisconnected() {
                // Retry connection
            }
        })
    }

    private fun queryProducts() {
        val productList = listOf(
            QueryProductDetailsParams.Product.newBuilder()
                .setProductId("com.yourapp.course1_monthly")
                .setProductType(BillingClient.ProductType.INAPP)
                .build()
        )

        val params = QueryProductDetailsParams.newBuilder()
            .setProductList(productList)
            .build()

        billingClient.queryProductDetailsAsync(params) { billingResult, productDetailsList ->
            // Handle product details
        }
    }

    private fun handlePurchase(purchase: Purchase) {
        if (purchase.purchaseState == Purchase.PurchaseState.PURCHASED) {
            // Send purchase token to Django API
            sendPurchaseToAPI(purchase)
        }
    }

    private fun sendPurchaseToAPI(purchase: Purchase) {
        val url = URL("https://your-api.com/api/apple-iap/verify-receipt/")
        val connection = url.openConnection() as HttpURLConnection

        connection.requestMethod = "POST"
        connection.setRequestProperty("Content-Type", "application/json")
        connection.setRequestProperty("Authorization", "Token YOUR_DJANGO_TOKEN")
        connection.doOutput = true

        val body = JSONObject().apply {
            put("receipt_data", purchase.purchaseToken)
        }

        connection.outputStream.use { os ->
            os.write(body.toString().toByteArray())
        }

        val response = connection.inputStream.bufferedReader().use { it.readText() }
        println("Django API response: $response")
    }
}
```

## Security Considerations

### 1. Receipt Verification

- All receipts are verified server-side with Apple's servers
- Supports both production and sandbox environments
- Handles receipt validation errors gracefully

### 2. Transaction Deduplication

- Prevents duplicate processing of the same transaction
- Uses Apple's transaction ID for uniqueness
- Maintains data integrity

### 3. Environment Handling

- Automatically detects production vs sandbox receipts
- Supports testing with sandbox accounts
- Proper error handling for environment mismatches

### 4. Webhook Security

- JWT signature verification (to be implemented)
- Secure handling of server-to-server notifications
- Rate limiting and error handling

## Testing

### 1. Sandbox Testing

1. Create sandbox test accounts in App Store Connect
2. Use sandbox environment for testing
3. Test with various product types and scenarios

### 2. Receipt Validation Testing

```bash
# Test receipt verification
curl -X POST https://your-api.com/api/apple-iap/verify-receipt/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token YOUR_TOKEN" \
  -d '{
    "receipt_data": "base64_encoded_receipt"
  }'
```

### 3. Product Management Testing

```bash
# Create a product
curl -X POST https://your-api.com/api/apple-iap/products/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token YOUR_TOKEN" \
  -d '{
    "product_id": "com.yourapp.test_product",
    "course_id": 1,
    "plan_type": "ONE_MONTH",
    "price_usd": "9.99"
  }'
```

## Error Handling

### Common Apple Status Codes

- **0**: Valid receipt
- **21000**: Invalid JSON
- **21002**: Malformed receipt data
- **21003**: Receipt could not be authenticated
- **21004**: Shared secret mismatch
- **21005**: Receipt server unavailable
- **21006**: Receipt valid but subscription expired
- **21007**: Test receipt sent to production
- **21008**: Production receipt sent to test

### Error Response Format

```json
{
  "success": false,
  "error": "Receipt could not be authenticated",
  "status_code": 21003
}
```

## Monitoring and Logging

### 1. Logging

The system includes comprehensive logging:

- Receipt verification attempts
- Purchase processing results
- Error details and stack traces
- Webhook processing events

### 2. Monitoring

Monitor these key metrics:

- Receipt verification success rate
- Purchase processing time
- Error rates by status code
- Webhook processing success

### 3. Alerts

Set up alerts for:

- High error rates
- Failed webhook processing
- Receipt verification failures
- Database transaction failures

## Migration from Razorpay

### 1. Gradual Migration

You can run both payment systems simultaneously:

```python
# In your purchase processing
if payment_gateway == 'RAZORPAY':
    # Process with Razorpay
    razorpay_service.process_payment(...)
elif payment_gateway == 'APPLE_IAP':
    # Process with Apple IAP
    apple_iap_service.process_receipt(...)
```

### 2. User Experience

- Allow users to choose payment method
- Maintain consistent API responses
- Handle both payment types in UI

### 3. Data Migration

- Existing purchases remain unchanged
- New purchases use the selected gateway
- Analytics can track both payment methods

## Best Practices

### 1. Receipt Handling

- Always verify receipts server-side
- Store receipt data for audit purposes
- Handle receipt refresh scenarios

### 2. Product Management

- Use consistent product ID naming
- Keep product configurations up to date
- Test products in sandbox first

### 3. Error Handling

- Implement retry logic for network failures
- Provide clear error messages to users
- Log all errors for debugging

### 4. Security

- Never store shared secrets in client code
- Validate all input data
- Use HTTPS for all API communications

This completes the Apple In-App Purchase integration setup!
