import requests
import json
import base64
import logging
from django.conf import settings
from django.utils import timezone
from datetime import datetime, timedelta
from .models import AppleIAPProduct, AppleIAPReceipt, Purchase, Enrollment, UserSubscription, Notification

logger = logging.getLogger(__name__)

class AppleIAPService:
    """
    Service for handling Apple In-App Purchase verification and processing
    """
    
    # Apple's verification URLs
    PRODUCTION_URL = "https://buy.itunes.apple.com/verifyReceipt"
    SANDBOX_URL = "https://sandbox.itunes.apple.com/verifyReceipt"
    
    def __init__(self):
        self.production_url = self.PRODUCTION_URL
        self.sandbox_url = self.SANDBOX_URL
    
    def verify_receipt(self, receipt_data, password=None):
        """
        Verify Apple receipt with Apple's servers
        
        Args:
            receipt_data (str): Base64 encoded receipt data
            password (str): App-specific shared secret (optional)
            
        Returns:
            dict: Verification response from Apple
        """
        try:
            # Prepare request payload
            payload = {
                'receipt-data': receipt_data,
                'exclude-old-transactions': True
            }
            
            if password:
                payload['password'] = password
            
            # Try production first
            response = self._verify_with_apple(self.production_url, payload)
            
            # If production fails with 21007, try sandbox
            if response.get('status') == 21007:
                logger.info("Production verification failed, trying sandbox")
                response = self._verify_with_apple(self.sandbox_url, payload)
            
            return response
            
        except Exception as e:
            logger.error(f"Apple receipt verification failed: {str(e)}")
            return {
                'status': 9999,
                'error': str(e)
            }
    
    def _verify_with_apple(self, url, payload):
        """
        Make verification request to Apple's servers
        
        Args:
            url (str): Apple verification URL
            payload (dict): Request payload
            
        Returns:
            dict: Apple's response
        """
        try:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Apple verification request failed: {response.status_code}")
                return {
                    'status': 9999,
                    'error': f'HTTP {response.status_code}'
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request to Apple failed: {str(e)}")
            return {
                'status': 9999,
                'error': str(e)
            }
    
    def process_receipt(self, receipt_data, user, course_id=None, plan_type=None):
        """
        Process Apple receipt and create/update purchase records
        
        Args:
            receipt_data (str): Base64 encoded receipt data
            user: Django user object
            course_id (int): Course ID (optional, can be extracted from receipt)
            plan_type (str): Plan type (optional, can be extracted from receipt)
            
        Returns:
            dict: Processing result
        """
        try:
            # Verify receipt with Apple
            verification_response = self.verify_receipt(receipt_data)
            
            if verification_response.get('status') != 0:
                error_msg = self._get_error_message(verification_response.get('status'))
                logger.error(f"Apple receipt verification failed: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'status_code': verification_response.get('status')
                }
            
            # Extract receipt info
            receipt_info = verification_response.get('receipt', {})
            latest_receipt_info = verification_response.get('latest_receipt_info', [])
            
            # Use latest receipt info if available, otherwise use receipt info
            if latest_receipt_info:
                transaction_info = latest_receipt_info[0]
            else:
                transaction_info = receipt_info.get('in_app', [{}])[0] if receipt_info.get('in_app') else {}
            
            # Extract transaction details
            transaction_id = transaction_info.get('transaction_id')
            product_id = transaction_info.get('product_id')
            purchase_date_ms = transaction_info.get('purchase_date_ms')
            expires_date_ms = transaction_info.get('expires_date_ms')
            
            # Check if transaction already processed
            existing_purchase = Purchase.objects.filter(
                apple_transaction_id=transaction_id
            ).first()
            
            if existing_purchase:
                logger.info(f"Transaction {transaction_id} already processed")
                return {
                    'success': True,
                    'message': 'Transaction already processed',
                    'purchase_id': existing_purchase.id,
                    'is_duplicate': True
                }
            
            # Find or create Apple IAP product
            try:
                apple_product = AppleIAPProduct.objects.get(
                    product_id=product_id,
                    is_active=True
                )
                course = apple_product.course
                plan_type = apple_product.plan_type
            except AppleIAPProduct.DoesNotExist:
                # Fallback to provided course_id and plan_type
                if not course_id or not plan_type:
                    return {
                        'success': False,
                        'error': 'Product not configured and course_id/plan_type not provided'
                    }
                
                from .models import Course
                try:
                    course = Course.objects.get(id=course_id)
                except Course.DoesNotExist:
                    return {
                        'success': False,
                        'error': 'Course not found'
                    }
            
            # Convert purchase date
            purchase_date = None
            if purchase_date_ms:
                purchase_date = datetime.fromtimestamp(int(purchase_date_ms) / 1000)
            
            # Convert expiry date
            expiry_date = None
            if expires_date_ms:
                expiry_date = datetime.fromtimestamp(int(expires_date_ms) / 1000)
            
            # Create purchase record
            purchase = Purchase.objects.create(
                user=user,
                course=course,
                plan_type=plan_type,
                amount=apple_product.price_usd if apple_product else 0,
                transaction_id=f"apple_{transaction_id}",
                apple_transaction_id=transaction_id,
                apple_product_id=product_id,
                apple_receipt_data=receipt_data,
                apple_verification_status='VERIFIED',
                payment_status='COMPLETED',
                payment_gateway='APPLE_IAP',
                purchase_date=purchase_date or timezone.now()
            )
            
            # Create receipt record
            AppleIAPReceipt.objects.create(
                purchase=purchase,
                receipt_data=receipt_data,
                verification_response=verification_response,
                is_valid=True,
                environment='Production' if verification_response.get('environment') == 'Production' else 'Sandbox'
            )
            
            # Create enrollment
            enrollment, created = Enrollment.objects.get_or_create(
                user=user,
                course=course,
                defaults={
                    'plan_type': plan_type,
                    'date_enrolled': timezone.now(),
                    'is_active': True
                }
            )
            
            if not created:
                # Update existing enrollment
                enrollment.plan_type = plan_type
                enrollment.is_active = True
                enrollment.save()
            
            # Set expiry date for subscription plans
            if plan_type in ['ONE_MONTH', 'THREE_MONTHS'] and expiry_date:
                enrollment.expiry_date = expiry_date
                enrollment.save()
            
            # Create notification
            Notification.objects.create(
                user=user,
                title="Purchase Successful",
                message=f"Your purchase of {course.title} ({dict(CoursePlanType.choices)[plan_type]}) has been completed successfully.",
                notification_type='PAYMENT',
                is_seen=False
            )
            
            logger.info(f"Successfully processed Apple IAP transaction {transaction_id}")
            
            return {
                'success': True,
                'message': 'Purchase processed successfully',
                'purchase_id': purchase.id,
                'enrollment_id': enrollment.id,
                'transaction_id': transaction_id,
                'expiry_date': expiry_date.isoformat() if expiry_date else None
            }
            
        except Exception as e:
            logger.error(f"Apple IAP processing failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_error_message(self, status_code):
        """
        Get human-readable error message for Apple status codes
        
        Args:
            status_code (int): Apple status code
            
        Returns:
            str: Error message
        """
        error_messages = {
            0: "Valid receipt",
            21000: "The App Store could not read the JSON object you provided",
            21002: "The data in the receipt-data property was malformed",
            21003: "The receipt could not be authenticated",
            21004: "The shared secret you provided does not match the shared secret on file for your account",
            21005: "The receipt server is not currently available",
            21006: "This receipt is valid but the subscription has expired",
            21007: "This receipt is from the test environment, but it was sent to the production environment for verification",
            21008: "This receipt is from the production environment, but it was sent to the test environment for verification",
            21010: "This receipt could not be authorized",
            21099: "Internal data access error",
            21199: "Unknown error occurred"
        }
        
        return error_messages.get(status_code, f"Unknown error (status: {status_code})")
    
    def get_products_for_course(self, course_id):
        """
        Get Apple IAP products for a specific course
        
        Args:
            course_id (int): Course ID
            
        Returns:
            QuerySet: Apple IAP products
        """
        return AppleIAPProduct.objects.filter(
            course_id=course_id,
            is_active=True
        )
    
    def create_product(self, product_id, course_id, plan_type, price_usd):
        """
        Create a new Apple IAP product
        
        Args:
            product_id (str): Apple Product ID
            course_id (int): Course ID
            plan_type (str): Plan type
            price_usd (Decimal): Price in USD
            
        Returns:
            AppleIAPProduct: Created product
        """
        return AppleIAPProduct.objects.create(
            product_id=product_id,
            course_id=course_id,
            plan_type=plan_type,
            price_usd=price_usd
        )
    
    def validate_receipt_format(self, receipt_data):
        """
        Basic validation of receipt data format
        
        Args:
            receipt_data (str): Receipt data
            
        Returns:
            bool: True if valid format
        """
        try:
            # Check if it's base64 encoded
            base64.b64decode(receipt_data)
            return True
        except Exception:
            return False 