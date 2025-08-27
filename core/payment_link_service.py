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
            
            # Validate amount
            if not amount or amount <= 0:
                return {
                    'success': False,
                    'error': 'Invalid amount for this course and plan'
                }
            
            # Generate unique reference ID
            reference_id = f"link_{str(uuid.uuid4())[:8]}"
            
            # Get base URL for callback
            base_url = getattr(settings, 'BASE_URL', 'https://api.pixelcraftsbybhavani.com')
            callback_url = f"{base_url}/api/payment-links/callback/"
            
            # Create payment order record with a temporary ID first
            temp_order_id = f"plink_{uuid.uuid4().hex[:16]}"
            payment_order = PaymentOrder.objects.create(
                user=user,
                course=course,
                plan_type=plan_type,
                amount=amount,
                status='LINK_REQUESTED',
                reference_id=reference_id,
                payment_method='PAYMENT_LINK',
                razorpay_order_id=temp_order_id  # Temporary ID, will be updated after payment link creation
            )
            
            # Generate payment link using Razorpay
            payment_link_data = {
                'amount': int(float(amount) * 100),  # Convert to paise and ensure integer
                'currency': 'INR',
                'reference_id': reference_id,
                'description': f'Payment for {course.title} - {dict(CoursePlanType.choices)[plan_type]}',
                'callback_url': callback_url,
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
            
            # Create Razorpay payment link with timeout
            try:
                import signal
                
                def timeout_handler(signum, frame):
                    raise TimeoutError("Payment link creation timed out")
                
                # Set timeout for payment link creation (30 seconds)
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)
                
                razorpay_response = self.razorpay_service.create_payment_link(payment_link_data)
                
                # Cancel the alarm
                signal.alarm(0)
                
            except TimeoutError:
                logger.error("Payment link creation timed out")
                # Mark order as failed
                payment_order.status = 'FAILED'
                payment_order.save()
                return {
                    'success': False,
                    'error': 'Payment link creation timed out. Please try again.'
                }
            except Exception as e:
                logger.error(f"Payment link creation failed: {str(e)}")
                # Mark order as failed
                payment_order.status = 'FAILED'
                payment_order.save()
                return {
                    'success': False,
                    'error': f'Payment link creation failed: {str(e)}'
                }
            
            if not razorpay_response.get('success'):
                # Mark order as failed
                payment_order.status = 'FAILED'
                payment_order.save()
                
                logger.error(f"Razorpay payment link creation failed: {razorpay_response.get('error')}")
                return {
                    'success': False,
                    'error': f"Failed to generate payment link: {razorpay_response.get('error', 'Unknown error')}"
                }
            
            # Update payment order with the payment link ID
            payment_link_id = razorpay_response.get('id')
            if payment_link_id:
                payment_order.razorpay_order_id = payment_link_id
                payment_order.save()
                logger.info(f"Created payment link: {payment_link_id}")
            else:
                logger.warning("No payment link ID received from Razorpay")
            
            # Send email to user (optional - don't fail if email fails)
            email_sent = False
            try:
                email_sent = self._send_payment_link_email(
                    user=user,
                    course=course,
                    plan_type=plan_type,
                    amount=amount,
                    payment_link=razorpay_response.get('short_url'),
                    reference_id=reference_id
                )
            except Exception as email_error:
                logger.error(f"Failed to send payment link email: {str(email_error)}")
                # Don't fail the entire request if email fails
            
            # Create notification with timeout
            try:
                import signal
                
                def notification_timeout_handler(signum, frame):
                    raise TimeoutError("Notification creation timed out")
                
                # Set timeout for notification creation (5 seconds)
                signal.signal(signal.SIGALRM, notification_timeout_handler)
                signal.alarm(5)
                
                Notification.objects.create(
                    user=user,
                    title="Payment Link Generated",
                    message=f"Payment link for {course.title} has been sent to your email.",
                    notification_type='PAYMENT',
                    is_seen=False
                )
                
                # Cancel the alarm
                signal.alarm(0)
                
            except TimeoutError:
                logger.error("Notification creation timed out")
            except Exception as notification_error:
                logger.error(f"Failed to create notification: {str(notification_error)}")
            
            return {
                'success': True,
                'message': 'Payment link request initiated successfully. Check your email for the payment link.',
                'reference_id': reference_id,
                'payment_order_id': payment_order.id,
                'email_sent': email_sent,
                'payment_link': razorpay_response.get('short_url')  # Return link in response for immediate use
            }
            
        except Exception as e:
            logger.error(f"Payment link creation failed: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to create payment link request: {str(e)}'
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
            # Check if email settings are configured
            if not getattr(settings, 'EMAIL_HOST_USER', None):
                logger.warning("Email settings not configured. Skipping email send.")
                return False
            
            subject = f"Payment Link for {course.title} - {dict(CoursePlanType.choices)[plan_type]}"
            
            # Email context
            context = {
                'user_name': user.full_name or user.email.split('@')[0],
                'course_title': course.title,
                'course_description': course.small_desc or course.description[:100] + '...' if course.description else 'Course description',
                'plan_type': dict(CoursePlanType.choices)[plan_type],
                'amount': amount,
                'payment_link': payment_link,
                'reference_id': reference_id,
                'expiry_date': (timezone.now() + timedelta(days=7)).strftime('%B %d, %Y'),
                'support_email': getattr(settings, 'SUPPORT_EMAIL', 'support@yourapp.com')
            }
            
            # Render email template
            try:
                html_message = render_to_string('emails/payment_link.html', context)
                plain_message = render_to_string('emails/payment_link.txt', context)
            except Exception as template_error:
                logger.error(f"Failed to render email templates: {str(template_error)}")
                # Fallback to simple text email
                plain_message = f"""
Payment Link for {course.title}

Hello {context['user_name']},

Your payment link for the course has been generated successfully.

Course: {course.title}
Plan: {context['plan_type']}
Amount: ₹{amount}
Reference ID: {reference_id}

Payment Link: {payment_link}

This link will expire on {context['expiry_date']}.

Thank you!
                """
                html_message = None
            
            # Send email with timeout
            try:
                import signal
                
                def email_timeout_handler(signum, frame):
                    raise TimeoutError("Email sending timed out")
                
                # Set timeout for email sending (10 seconds)
                signal.signal(signal.SIGALRM, email_timeout_handler)
                signal.alarm(10)
                
                send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@yourapp.com'),
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=True  # Changed to True to prevent hanging
                )
                
                # Cancel the alarm
                signal.alarm(0)
                
            except TimeoutError:
                logger.error("Email sending timed out")
                return False
            except Exception as email_send_error:
                logger.error(f"Email sending failed: {str(email_send_error)}")
                return False
            
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
            
            # Verify payment with Razorpay using order-based verification
            # Since we now have a proper Razorpay order, we can use signature verification
            try:
                # For payment links, we'll use payment ID verification since we don't have signature
                payment_verified = self.razorpay_service.verify_payment(payment_id)
                
                if not payment_verified:
                    return {
                        'success': False,
                        'error': 'Payment verification failed'
                    }
            except Exception as verify_error:
                logger.error(f"Payment verification error: {str(verify_error)}")
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
                razorpay_order_id=payment_order.razorpay_order_id,  # This is now the actual Razorpay order ID
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