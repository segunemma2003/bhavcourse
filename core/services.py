# core/services.py
import razorpay
from django.conf import settings
import logging
import uuid
from .models import Purchase, Enrollment, UserSubscription, Notification
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

class RazorpayService:
    def __init__(self):
        self.client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
        
    def create_order(self, amount, currency=None, receipt=None, notes=None):
        """
        Create a Razorpay order
        
        Args:
            amount: Amount in smallest currency unit (paise for INR)
            currency: Currency code (default: settings.RAZORPAY_CURRENCY)
            receipt: Receipt number for your reference
            notes: Additional notes as a dict
            
        Returns:
            order_id: Razorpay Order ID
        """
        try:
            data = {
                'amount': int(amount * 100),  # Convert to paise
                'currency': currency or settings.RAZORPAY_CURRENCY,
            }
            
            if receipt:
                data['receipt'] = receipt
                
            if notes:
                data['notes'] = notes
                
            order = self.client.order.create(data=data)
            return order
        except Exception as e:
            logger.error(f"Razorpay order creation failed: {str(e)}")
            raise
    
    def verify_payment_signature(self, payment_id, order_id, signature):
        """
        Verify Razorpay payment signature
        
        Args:
            payment_id: Razorpay Payment ID
            order_id: Razorpay Order ID
            signature: Razorpay Payment Signature
            
        Returns:
            bool: True if signature is valid
        """
        try:
            return self.client.utility.verify_payment_signature({
                'razorpay_payment_id': payment_id,
                'razorpay_order_id': order_id,
                'razorpay_signature': signature
            })
        except razorpay.errors.SignatureVerificationError:
            logger.error("Razorpay signature verification failed")
            return False
        except Exception as e:
            logger.error(f"Razorpay verification error: {str(e)}")
            return False
    
    def get_payment_details(self, payment_id):
        """
        Get payment details from Razorpay
        
        Args:
            payment_id: Razorpay Payment ID
            
        Returns:
            dict: Payment details
        """
        try:
            return self.client.payment.fetch(payment_id)
        except Exception as e:
            logger.error(f"Failed to fetch payment details: {str(e)}")
            raise
    
    def process_subscription_payment(self, user, plan, course, payment_id, order_id, payment_card=None):
        """
        Process a successful subscription payment
        
        Args:
            user: User object
            plan: SubscriptionPlan object
            course: Course object
            payment_id: Razorpay Payment ID
            order_id: Razorpay Order ID
            payment_card: PaymentCard object (optional)
            
        Returns:
            tuple: (UserSubscription, Purchase, Enrollment)
        """
        try:
            # Generate transaction ID
            transaction_id = str(uuid.uuid4())
            
            # Create subscription
            subscription = UserSubscription.objects.create(
                user=user,
                plan=plan,
                start_date=timezone.now(),
                end_date=timezone.now() + timedelta(days=30),
                is_active=True
            )
            
            # Create purchase record
            purchase = Purchase.objects.create(
                user=user,
                course=course,
                payment_card=payment_card,
                amount=plan.amount,
                transaction_id=transaction_id,
                # Add Razorpay specific fields
                razorpay_payment_id=payment_id,
                razorpay_order_id=order_id
            )
            
            # Create enrollment
            enrollment, created = Enrollment.objects.get_or_create(
                user=user,
                course=course
            )
            
            # Create notification
            Notification.objects.create(
                user=user,
                title="Course Enrollment Successful",
                message=f"You have successfully enrolled in {course.title}",
                notification_type='COURSE',
                is_seen=False
            )
            
            return subscription, purchase, enrollment
            
        except Exception as e:
            logger.error(f"Failed to process subscription payment: {str(e)}")
            raise