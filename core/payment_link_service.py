import uuid
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from datetime import timedelta
from .models import Course, CoursePlanType, PaymentOrder, Notification
from .services import RazorpayService

logger = logging.getLogger(__name__)

class PaymentLinkService:
    """
    Service for generating payment links and sending email notifications
    """
    
    def __init__(self):
        self.razorpay_service = RazorpayService()
    
    def create_payment_link_request(self, user, course_id, plan_type, amount=None):
        """
        Create a payment link request and send email to user
        
        Args:
            user: Django user object
            course_id (int): Course ID
            plan_type (str): Plan type (ONE_MONTH, THREE_MONTHS, LIFETIME)
            amount (Decimal): Optional amount override
            
        Returns:
            dict: Result with status and message
        """
        try:
            # Get course
            try:
                course = Course.objects.get(pk=course_id)
            except Course.DoesNotExist:
                return {
                    'success': False,
                    'error': 'Course not found'
                }
            
            # Get amount based on plan type if not provided
            if not amount:
                if plan_type == CoursePlanType.ONE_MONTH:
                    amount = course.price_one_month
                elif plan_type == CoursePlanType.THREE_MONTHS:
                    amount = course.price_three_months
                elif plan_type == CoursePlanType.LIFETIME:
                    amount = course.price_lifetime
                else:
                    return {
                        'success': False,
                        'error': 'Invalid plan type'
                    }
            
            # Generate unique reference ID
            reference_id = f"link_{str(uuid.uuid4())[:8]}"
            
            # Create payment order record
            payment_order = PaymentOrder.objects.create(
                user=user,
                course=course,
                plan_type=plan_type,
                amount=amount,
                status='LINK_REQUESTED',
                reference_id=reference_id,
                payment_method='PAYMENT_LINK'
            )
            
            # Generate payment link using Razorpay
            payment_link_data = {
                'amount': float(amount) * 100,  # Convert to paise
                'currency': 'INR',
                'reference_id': reference_id,
                'description': f'Payment for {course.title} - {dict(CoursePlanType.choices)[plan_type]}',
                'callback_url': f"{settings.BASE_URL}/api/payment-links/verify/",
                'callback_method': 'get',
                'notes': {
                    'user_id': str(user.id),
                    'course_id': str(course_id),
                    'plan_type': plan_type,
                    'email': user.email,
                    'course_title': course.title,
                    'plan_name': dict(CoursePlanType.choices)[plan_type],
                    'payment_type': 'link'
                }
            }
            
            # Create Razorpay payment link
            razorpay_response = self.razorpay_service.create_payment_link(payment_link_data)
            
            if not razorpay_response.get('success'):
                # Mark order as failed
                payment_order.status = 'FAILED'
                payment_order.save()
                
                return {
                    'success': False,
                    'error': 'Failed to generate payment link'
                }
            
            # Update payment order with Razorpay link ID
            payment_order.razorpay_order_id = razorpay_response.get('id')
            payment_order.save()
            
            # Send email to user
            email_sent = self._send_payment_link_email(
                user=user,
                course=course,
                plan_type=plan_type,
                amount=amount,
                payment_link=razorpay_response.get('short_url'),
                reference_id=reference_id
            )
            
            # Create notification
            Notification.objects.create(
                user=user,
                title="Payment Link Generated",
                message=f"Payment link for {course.title} has been sent to your email.",
                notification_type='PAYMENT',
                is_seen=False
            )
            
            return {
                'success': True,
                'message': 'Payment link request initiated successfully. Check your email for the payment link.',
                'reference_id': reference_id,
                'payment_order_id': payment_order.id,
                'email_sent': email_sent
            }
            
        except Exception as e:
            logger.error(f"Payment link creation failed: {str(e)}")
            return {
                'success': False,
                'error': 'Failed to create payment link request'
            }
    
    def _send_payment_link_email(self, user, course, plan_type, amount, payment_link, reference_id):
        """
        Send payment link email to user
        
        Args:
            user: Django user object
            course: Course object
            plan_type: Plan type
            amount: Amount
            payment_link: Razorpay payment link
            reference_id: Reference ID
            
        Returns:
            bool: True if email sent successfully
        """
        try:
            subject = f"Payment Link for {course.title} - {dict(CoursePlanType.choices)[plan_type]}"
            
            # Email context
            context = {
                'user_name': user.full_name,
                'course_title': course.title,
                'course_description': course.small_desc,
                'plan_type': dict(CoursePlanType.choices)[plan_type],
                'amount': amount,
                'payment_link': payment_link,
                'reference_id': reference_id,
                'expiry_date': (timezone.now() + timedelta(days=7)).strftime('%B %d, %Y'),
                'support_email': getattr(settings, 'SUPPORT_EMAIL', 'support@yourapp.com')
            }
            
            # Render email template
            html_message = render_to_string('emails/payment_link.html', context)
            plain_message = render_to_string('emails/payment_link.txt', context)
            
            # Send email
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False
            )
            
            logger.info(f"Payment link email sent to {user.email} for course {course.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send payment link email: {str(e)}")
            return False
    
    def verify_payment_link_payment(self, payment_id, reference_id):
        """
        Verify payment made through payment link
        
        Args:
            payment_id (str): Razorpay payment ID
            reference_id (str): Reference ID from payment link
            
        Returns:
            dict: Verification result
        """
        try:
            # Find payment order
            try:
                payment_order = PaymentOrder.objects.get(
                    reference_id=reference_id,
                    payment_method='PAYMENT_LINK'
                )
            except PaymentOrder.DoesNotExist:
                return {
                    'success': False,
                    'error': 'Payment order not found'
                }
            
            # Verify payment with Razorpay
            payment_verified = self.razorpay_service.verify_payment(payment_id)
            
            if not payment_verified:
                return {
                    'success': False,
                    'error': 'Payment verification failed'
                }
            
            # Update payment order
            payment_order.status = 'PAID'
            payment_order.razorpay_payment_id = payment_id
            payment_order.paid_at = timezone.now()
            payment_order.save()
            
            # Process enrollment
            enrollment_result = self._process_payment_link_enrollment(payment_order)
            
            if not enrollment_result['success']:
                return enrollment_result
            
            # Create notification
            Notification.objects.create(
                user=payment_order.user,
                title="Payment Successful",
                message=f"Your payment for {payment_order.course.title} has been completed successfully.",
                notification_type='PAYMENT',
                is_seen=False
            )
            
            return {
                'success': True,
                'message': 'Payment verified and enrollment completed',
                'enrollment_id': enrollment_result.get('enrollment_id'),
                'purchase_id': enrollment_result.get('purchase_id')
            }
            
        except Exception as e:
            logger.error(f"Payment link verification failed: {str(e)}")
            return {
                'success': False,
                'error': 'Payment verification failed'
            }
    
    def _process_payment_link_enrollment(self, payment_order):
        """
        Process enrollment after payment link payment
        
        Args:
            payment_order: PaymentOrder object
            
        Returns:
            dict: Enrollment result
        """
        try:
            from .models import Purchase, Enrollment
            
            # Create purchase record
            purchase = Purchase.objects.create(
                user=payment_order.user,
                course=payment_order.course,
                plan_type=payment_order.plan_type,
                amount=payment_order.amount,
                transaction_id=f"link_{payment_order.reference_id}",
                razorpay_order_id=payment_order.razorpay_order_id,
                razorpay_payment_id=payment_order.razorpay_payment_id,
                payment_status='COMPLETED',
                payment_gateway='RAZORPAY',
                purchase_date=timezone.now()
            )
            
            # Create or update enrollment
            enrollment, created = Enrollment.objects.get_or_create(
                user=payment_order.user,
                course=payment_order.course,
                defaults={
                    'plan_type': payment_order.plan_type,
                    'date_enrolled': timezone.now(),
                    'is_active': True,
                    'amount_paid': payment_order.amount
                }
            )
            
            if not created:
                # Update existing enrollment
                enrollment.plan_type = payment_order.plan_type
                enrollment.is_active = True
                enrollment.amount_paid = payment_order.amount
                enrollment.save()
            
            # Set expiry date for subscription plans
            if payment_order.plan_type in ['ONE_MONTH', 'THREE_MONTHS']:
                if payment_order.plan_type == 'ONE_MONTH':
                    expiry_days = 30
                else:
                    expiry_days = 90
                
                enrollment.expiry_date = timezone.now() + timedelta(days=expiry_days)
                enrollment.save()
            
            return {
                'success': True,
                'enrollment_id': enrollment.id,
                'purchase_id': purchase.id
            }
            
        except Exception as e:
            logger.error(f"Payment link enrollment processing failed: {str(e)}")
            return {
                'success': False,
                'error': 'Enrollment processing failed'
            } 