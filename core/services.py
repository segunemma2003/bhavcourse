import razorpay
from django.conf import settings
import logging
import uuid
from .models import CoursePlanType, Purchase, Enrollment, UserSubscription, Notification
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
    
    def verify_payment_by_id(self, payment_id, expected_amount=None):
        """
        Verify payment using payment ID only (no order required)
        
        Args:
            payment_id: Razorpay Payment ID
            expected_amount: Expected amount in rupees (optional verification)
            
        Returns:
            dict: Payment details if valid, raises exception if invalid
        """
        try:
            # Fetch payment details from Razorpay
            payment = self.client.payment.fetch(payment_id)
            logger.info(f"Payment details fetched: {payment['id']}, status: {payment['status']}")
            print(payment)
            # Verify payment status
            if payment['status'] != 'captured':
                raise ValueError(f"Payment not completed. Status: {payment['status']}")
            
           
            return payment
            
        except razorpay.errors.BadRequestError as e:
            logger.error(f"Invalid payment ID: {payment_id} {str(e)}")
            raise ValueError("Invalid payment ID")
        except Exception as e:
            logger.error(f"Payment verification failed: {str(e)}")
            raise
    
    # Keep your existing methods but modify verify_payment_signature
    def verify_payment_signature(self, payment_id, order_id=None, signature=None):
        """
        Verify payment - if no order_id, use payment ID verification only
        
        Args:
            payment_id: Razorpay Payment ID
            order_id: Razorpay Order ID (optional)
            signature: Razorpay Payment Signature (optional)
            
        Returns:
            bool: True if payment is valid
        """
        try:
            # If no order_id provided, use payment ID verification
            if not order_id:
                payment = self.verify_payment_by_id(payment_id)
                return payment['status'] == 'captured'
            
            # Original signature verification for order-based payments
            return self.client.utility.verify_payment_signature({
                'razorpay_payment_id': payment_id,
                'razorpay_order_id': order_id,
                'razorpay_signature': signature
            })
        except Exception as e:
            logger.error(f"Payment verification error: {str(e)}")
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
    
    def process_course_purchase(user, course, plan_type, razorpay_payment_id, razorpay_order_id, razorpay_signature, payment_card=None):
        """
        Process a successful course purchase with payment verification
        
        Args:
            user: User object
            course: Course object
            plan_type: Type of plan (ONE_MONTH, THREE_MONTHS, LIFETIME)
            razorpay_payment_id: Razorpay Payment ID
            razorpay_order_id: Razorpay Order ID
            razorpay_signature: Razorpay Signature
            payment_card: PaymentCard object (optional)
            
        Returns:
            dict: Dictionary containing created objects and status
        """
        try:
            # Get plan amount based on plan type
            if plan_type == CoursePlanType.ONE_MONTH:
                amount = course.price_one_month
            elif plan_type == CoursePlanType.THREE_MONTHS:
                amount = course.price_three_months
            elif plan_type == CoursePlanType.LIFETIME:
                amount = course.price_lifetime
            else:
                raise ValueError("Invalid plan type")
            
            # Generate transaction ID
            transaction_id = str(uuid.uuid4())
            
            # Create Purchase record
            purchase = Purchase.objects.create(
                user=user,
                course=course,
                payment_card=payment_card,
                amount=amount,
                transaction_id=transaction_id,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_order_id=razorpay_order_id,
                payment_status='COMPLETED'
            )
            
            # Create or update enrollment
            existing_enrollment = Enrollment.objects.filter(user=user, course=course).first()
            
            if existing_enrollment:
                # Update existing enrollment with new plan type
                existing_enrollment.plan_type = plan_type
                current_time = timezone.now()
                if plan_type == CoursePlanType.ONE_MONTH:
                    existing_enrollment.expiry_date = current_time + timezone.timedelta(days=30)
                elif plan_type == CoursePlanType.THREE_MONTHS:
                    existing_enrollment.expiry_date = current_time + timezone.timedelta(days=90)
                elif plan_type == CoursePlanType.LIFETIME:
                    existing_enrollment.expiry_date = None
                
                existing_enrollment.amount_paid = amount
                existing_enrollment.is_active = True
                existing_enrollment.save()
                enrollment = existing_enrollment
            else:
                # Create new enrollment
                enrollment = Enrollment.objects.create(
                    user=user,
                    course=course,
                    plan_type=plan_type,
                    amount_paid=amount,
                    is_active=True
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
                    amount=amount,
                    razorpay_order_id=razorpay_order_id,
                    razorpay_payment_id=razorpay_payment_id,
                    razorpay_signature=razorpay_signature,
                    status='PAID'
                )
            
            # Create notifications
            Notification.objects.create(
                user=user,
                title="Course Purchase Successful",
                message=f"You have successfully purchased and enrolled in {course.title} with a {enrollment.get_plan_type_display()} plan.",
                notification_type='PAYMENT',
                is_seen=False
            )
            
            if plan_type != CoursePlanType.LIFETIME:
                expiry_msg = f"Your access is valid until {enrollment.expiry_date.strftime('%Y-%m-%d')}"
            else:
                expiry_msg = "You have lifetime access to this course."
                
            Notification.objects.create(
                user=user,
                title="Course Enrollment Successful",
                message=f"You have been enrolled in {course.title}. {expiry_msg}",
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
            
            # Schedule expiry reminder for non-lifetime plans
            if plan_type != CoursePlanType.LIFETIME and enrollment.expiry_date:
                from .tasks import send_enrollment_expiry_reminder
                # Schedule the task to run 3 days before expiry
                reminder_date = enrollment.expiry_date - timezone.timedelta(days=3)
                if reminder_date > timezone.now():
                    send_enrollment_expiry_reminder.apply_async(
                        eta=reminder_date, 
                        args=[enrollment.id]
                    )
                    logger.info(f"Scheduled expiry reminder for enrollment {enrollment.id} at {reminder_date}")
            
            return {
                'purchase': purchase,
                'enrollment': enrollment,
                'payment_order': payment_order,
                'message': 'Course purchased successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to process course purchase: {str(e)}")
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

def process_course_purchase(user, course, plan_type, razorpay_payment_id, razorpay_order_id, razorpay_signature, payment_card=None):
    """
    Process a successful course purchase with payment verification
    
    Args:
        user: User object
        course: Course object
        plan_type: Type of plan (ONE_MONTH, THREE_MONTHS, LIFETIME)
        razorpay_payment_id: Razorpay Payment ID
        razorpay_order_id: Razorpay Order ID
        razorpay_signature: Razorpay Signature
        payment_card: PaymentCard object (optional)
        
    Returns:
        dict: Dictionary containing created objects and status
    """
    try:
        razorpay_service = RazorpayService()
        is_valid = razorpay_service.verify_payment_signature(
            razorpay_payment_id, 
            razorpay_order_id, 
            razorpay_signature
        )
        
        if not is_valid:
            logger.error(f"❌ Payment verification failed for order {razorpay_order_id}")
            raise ValueError("Payment verification failed. Invalid signature.")
        
        logger.info(f"✅ Payment verified successfully for order {razorpay_order_id}")
        
        # Get plan amount based on plan type
        if plan_type == CoursePlanType.ONE_MONTH:
            amount = course.price_one_month
        elif plan_type == CoursePlanType.THREE_MONTHS:
            amount = course.price_three_months
        elif plan_type == CoursePlanType.LIFETIME:
            amount = course.price_lifetime
        else:
            raise ValueError("Invalid plan type")
        
        # Generate transaction ID
        transaction_id = str(uuid.uuid4())
        
        # Create Purchase record
        purchase = Purchase.objects.create(
            user=user,
            course=course,
            payment_card=payment_card,
            plan_type=plan_type,
            amount=amount,
            transaction_id=transaction_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_order_id=razorpay_order_id,
            payment_status='COMPLETED'
        )
        
        # Create or update enrollment
        existing_enrollment = Enrollment.objects.filter(user=user, course=course).first()
        
        if existing_enrollment:
            # Update existing enrollment with new plan type
            current_time = timezone.now()
            
            existing_enrollment.plan_type = plan_type
            if plan_type == CoursePlanType.ONE_MONTH:
                existing_enrollment.expiry_date = current_time + timezone.timedelta(days=30)
            elif plan_type == CoursePlanType.THREE_MONTHS:
                existing_enrollment.expiry_date = current_time + timezone.timedelta(days=90)
            elif plan_type == CoursePlanType.LIFETIME:
                existing_enrollment.expiry_date = None
            
            existing_enrollment.amount_paid = amount
            existing_enrollment.is_active = True
            existing_enrollment.save()
            enrollment = existing_enrollment
        else:
            # Create new enrollment
            current_time = timezone.now()
            expiry_date = None
            
            if plan_type == CoursePlanType.ONE_MONTH:
                expiry_date = current_time + timezone.timedelta(days=30)
            elif plan_type == CoursePlanType.THREE_MONTHS:
                expiry_date = current_time + timezone.timedelta(days=90)
                
            enrollment = Enrollment.objects.create(
                user=user,
                course=course,
                plan_type=plan_type,
                amount_paid=amount,
                is_active=True,
                expiry_date=expiry_date
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
                amount=amount,
                razorpay_order_id=razorpay_order_id,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_signature=razorpay_signature,
                status='PAID'
            )
        
        # Create notifications
        Notification.objects.create(
            user=user,
            title="Course Purchase Successful",
            message=f"You have successfully purchased and enrolled in {course.title} with a {enrollment.get_plan_type_display()} plan.",
            notification_type='PAYMENT',
            is_seen=False
        )
        
        if plan_type != CoursePlanType.LIFETIME:
            expiry_msg = f"Your access is valid until {enrollment.expiry_date.strftime('%Y-%m-%d')}"
        else:
            expiry_msg = "You have lifetime access to this course."
            
        Notification.objects.create(
            user=user,
            title="Course Enrollment Successful",
            message=f"You have been enrolled in {course.title}. {expiry_msg}",
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
        
        # Schedule expiry reminder for non-lifetime plans
        if plan_type != CoursePlanType.LIFETIME and enrollment.expiry_date is not None:
            from .tasks import send_enrollment_expiry_reminder
            # Schedule the task to run 3 days before expiry
            reminder_date = enrollment.expiry_date - timezone.timedelta(days=3)
            if reminder_date > timezone.now():
                send_enrollment_expiry_reminder.apply_async(
                    eta=reminder_date, 
                    args=[enrollment.id]
                )
                logger.info(f"Scheduled expiry reminder for enrollment {enrollment.id} at {reminder_date}")
        
        return {
            'purchase': purchase,
            'enrollment': enrollment,
            'payment_order': payment_order,
            'message': 'Course purchased successfully'
        }
        
    except Exception as e:
        logger.error(f"Failed to process course purchase: {str(e)}")
        raise
            
def clear_enrollment_cache(user_id):
    """
    Utility function to clear all enrollment-related cache for a user - UPDATED TO v8
    """
    from django.core.cache import cache
    import hashlib
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"🧹 [Services] Clearing enrollment cache v8 for user {user_id}")
    
    # Clear main enrollment list cache (both show_all variants) - v8
    for show_all in ['true', 'false']:
        key_data = f"enrollments_v8_{user_id}_list_{show_all}"
        cache_key = hashlib.md5(key_data.encode()).hexdigest()
        cache.delete(cache_key)
        logger.debug(f"Cleared enrollment list cache v8: {cache_key}")
    
    # Clear enrollment summary cache - v8
    summary_cache_key = f"enrollment_summary_v8_{user_id}"
    cache.delete(summary_cache_key)
    logger.debug(f"Cleared enrollment summary cache v8: {summary_cache_key}")
    
    logger.info(f"✅ [Services] Cleared enrollment cache v8 for user {user_id}")
    
    
    