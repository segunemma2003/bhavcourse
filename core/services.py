import razorpay
from django.conf import settings
import logging
import uuid
from .models import Purchase, Enrollment, UserSubscription, Notification
from django.utils import timezone
from datetime import timedelta
from .tasks import send_push_notification  # Import the task function

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
    
    def process_course_purchase(self, user, course, plan, razorpay_payment_id, razorpay_order_id, razorpay_signature, payment_card=None):
        """
        Process a successful course purchase with payment verification
        
        Args:
            user: User object
            course: Course object
            plan: SubscriptionPlan object
            razorpay_payment_id: Razorpay Payment ID
            razorpay_order_id: Razorpay Order ID
            razorpay_signature: Razorpay Signature
            payment_card: PaymentCard object (optional)
            
        Returns:
            dict: Dictionary containing created objects and status
        """
        try:
            # Verify payment signature first
            # if not self.verify_payment_signature(razorpay_payment_id, razorpay_order_id, razorpay_signature):
            #     raise ValueError("Payment signature verification failed")
            
            # Generate transaction ID
            transaction_id = str(uuid.uuid4())
            
            # Create Purchase record
            purchase = Purchase.objects.create(
                user=user,
                course=course,
                plan=plan,
                payment_card=payment_card,
                amount=plan.amount,
                transaction_id=transaction_id,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_order_id=razorpay_order_id,
                payment_status='COMPLETED'
            )
            
            # Update or create subscription
            # First, deactivate any existing active subscription
            UserSubscription.objects.filter(
                user=user,
                is_active=True,
                end_date__gt=timezone.now()
            ).update(is_active=False)
            
            # Create new subscription
            subscription = UserSubscription.objects.create(
                user=user,
                plan=plan,
                start_date=timezone.now(),
                end_date=timezone.now() + timedelta(days=30),
                is_active=True
            )
            
            # Create enrollment
            enrollment, created = Enrollment.objects.get_or_create(
                user=user,
                course=course
            )
            
            # Update payment order status if exists
            from .models import PaymentOrder
            payment_order = PaymentOrder.objects.filter(
                razorpay_order_id=razorpay_order_id
            ).first()
            
            if payment_order:
                payment_order.status = 'PAID'
                payment_order.razorpay_payment_id = razorpay_payment_id
                payment_order.razorpay_signature = razorpay_signature
                payment_order.save()
            else:
                # Create payment order if it doesn't exist
                payment_order = PaymentOrder.objects.create(
                    user=user,
                    course=course,
                    plan=plan,
                    amount=plan.amount,
                    razorpay_order_id=razorpay_order_id,
                    razorpay_payment_id=razorpay_payment_id,
                    razorpay_signature=razorpay_signature,
                    status='PAID'
                )
            
            # Create notifications
            Notification.objects.create(
                user=user,
                title="Course Purchase Successful",
                message=f"You have successfully purchased and enrolled in {course.title}",
                notification_type='PAYMENT',
                is_seen=False
            )
            
            Notification.objects.create(
                user=user,
                title="Course Enrollment Successful",
                message=f"You have been enrolled in {course.title}. Your subscription is active until {subscription.end_date.strftime('%Y-%m-%d')}",
                notification_type='COURSE',
                is_seen=False
            )
            
            # Send push notifications
            send_push_notification.delay(
                user.id,
                "Course Purchase Successful",
                f"You have successfully purchased {course.title}",
                {
                    'type': 'purchase_success',
                    'course_id': course.id,
                    'purchase_id': purchase.id
                }
            )
            
            # Schedule subscription expiry reminder (using Celery)
            from .tasks import send_subscription_expiry_reminder
            # Schedule the task to run 3 days before expiry
            reminder_date = subscription.end_date - timedelta(days=3)
            if reminder_date > timezone.now():
                send_subscription_expiry_reminder.apply_async(
                    eta=reminder_date, 
                    args=[subscription.id]
                )
                logger.info(f"Scheduled expiry reminder for subscription {subscription.id} at {reminder_date}")
            
            return {
                'purchase': purchase,
                'subscription': subscription,
                'enrollment': enrollment,
                'payment_order': payment_order,
                'message': 'Course purchased successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to process course purchase: {str(e)}")
            raise
        
        
def process_course_purchase(user, course, plan, razorpay_payment_id, razorpay_order_id, razorpay_signature, payment_card=None):
        """
        Process a successful course purchase with payment verification
        
        Args:
            user: User object
            course: Course object
            plan: SubscriptionPlan object
            razorpay_payment_id: Razorpay Payment ID
            razorpay_order_id: Razorpay Order ID
            razorpay_signature: Razorpay Signature
            payment_card: PaymentCard object (optional)
            
        Returns:
            dict: Dictionary containing created objects and status
        """
        try:
            # Verify payment signature first
            # if not self.verify_payment_signature(razorpay_payment_id, razorpay_order_id, razorpay_signature):
            #     raise ValueError("Payment signature verification failed")
            
            # Generate transaction ID
            transaction_id = str(uuid.uuid4())
            
            # Create Purchase record
            purchase = Purchase.objects.create(
                user=user,
                course=course,
                plan=plan,
                payment_card=payment_card,
                amount=plan.amount,
                transaction_id=transaction_id,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_order_id=razorpay_order_id,
                payment_status='COMPLETED'
            )
            
            # Update or create subscription
            # First, deactivate any existing active subscription
            UserSubscription.objects.filter(
                user=user,
                is_active=True,
                end_date__gt=timezone.now()
            ).update(is_active=False)
            
            # Create new subscription
            subscription = UserSubscription.objects.create(
                user=user,
                plan=plan,
                start_date=timezone.now(),
                end_date=timezone.now() + timedelta(days=30),
                is_active=True
            )
            
            # Create enrollment
            enrollment, created = Enrollment.objects.get_or_create(
                user=user,
                course=course
            )
            
            # Update payment order status if exists
            from .models import PaymentOrder
            payment_order = PaymentOrder.objects.filter(
                razorpay_order_id=razorpay_order_id
            ).first()
            
            if payment_order:
                payment_order.status = 'PAID'
                payment_order.razorpay_payment_id = razorpay_payment_id
                payment_order.razorpay_signature = razorpay_signature
                payment_order.save()
            else:
                # Create payment order if it doesn't exist
                payment_order = PaymentOrder.objects.create(
                    user=user,
                    course=course,
                    plan=plan,
                    amount=plan.amount,
                    razorpay_order_id=razorpay_order_id,
                    razorpay_payment_id=razorpay_payment_id,
                    razorpay_signature=razorpay_signature,
                    status='PAID'
                )
            
            # Create notifications
            Notification.objects.create(
                user=user,
                title="Course Purchase Successful",
                message=f"You have successfully purchased and enrolled in {course.title}",
                notification_type='PAYMENT',
                is_seen=False
            )
            
            Notification.objects.create(
                user=user,
                title="Course Enrollment Successful",
                message=f"You have been enrolled in {course.title}. Your subscription is active until {subscription.end_date.strftime('%Y-%m-%d')}",
                notification_type='COURSE',
                is_seen=False
            )
            
            # Send push notifications
            send_push_notification.delay(
                user.id,
                "Course Purchase Successful",
                f"You have successfully purchased {course.title}",
                {
                    'type': 'purchase_success',
                    'course_id': course.id,
                    'purchase_id': purchase.id
                }
            )
            
            # Schedule subscription expiry reminder (using Celery)
            from .tasks import send_subscription_expiry_reminder
            # Schedule the task to run 3 days before expiry
            reminder_date = subscription.end_date - timedelta(days=3)
            if reminder_date > timezone.now():
                send_subscription_expiry_reminder.apply_async(
                    eta=reminder_date, 
                    args=[subscription.id]
                )
                logger.info(f"Scheduled expiry reminder for subscription {subscription.id} at {reminder_date}")
            
            return {
                'purchase': purchase,
                'subscription': subscription,
                'enrollment': enrollment,
                'payment_order': payment_order,
                'message': 'Course purchased successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to process course purchase: {str(e)}")
            raise