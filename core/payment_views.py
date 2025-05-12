# core/payment_views.py
from rest_framework import status, views, permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone

from .models import Course, PaymentCard, PaymentOrder, SubscriptionPlan, Purchase, Enrollment, UserSubscription, Notification
from .serializers import CreateOrderSerializer, PaymentOrderSerializer, VerifyPaymentSerializer, PurchaseSerializer
from .services import RazorpayService
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

import logging
import hmac
import hashlib
import uuid
import json

logger = logging.getLogger(__name__)

# Initialize the Razorpay service
razorpay_service = RazorpayService()

class CreateOrderView(views.APIView):
    """
    API endpoint for creating a Razorpay order for course subscription
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_summary="Create payment order",
        operation_description="Creates a Razorpay payment order for course subscription.",
        request_body=CreateOrderSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response(
                description="Order created successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'order_id': openapi.Schema(type=openapi.TYPE_STRING),
                        'amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'currency': openapi.Schema(type=openapi.TYPE_STRING),
                        'payment_order_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'key_id': openapi.Schema(type=openapi.TYPE_STRING),
                        'user_info': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'name': openapi.Schema(type=openapi.TYPE_STRING),
                                'email': openapi.Schema(type=openapi.TYPE_STRING),
                                'contact': openapi.Schema(type=openapi.TYPE_STRING)
                            }
                        ),
                        'notes': openapi.Schema(type=openapi.TYPE_OBJECT)
                    }
                )
            ),
            status.HTTP_400_BAD_REQUEST: "Invalid request data or already enrolled",
            status.HTTP_500_INTERNAL_SERVER_ERROR: "Failed to create payment order"
        }
    )
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = CreateOrderSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Get validated data
        course_id = serializer.validated_data.get('course_id')
        plan_id = serializer.validated_data.get('plan_id')
        payment_card_id = serializer.validated_data.get('payment_card_id')
        
        # Get course and plan objects
        course = get_object_or_404(Course, pk=course_id)
        plan = get_object_or_404(SubscriptionPlan, pk=plan_id)
        
        # Check if user already has an active subscription for this course
        existing_enrollment = Enrollment.objects.filter(
            user=request.user,
            course=course
        ).exists()
        
        if existing_enrollment:
            return Response(
                {"error": "You are already enrolled in this course"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate a unique receipt ID
        receipt_id = f"rcpt_{str(uuid.uuid4())[:8]}"
        
        # Create notes for Razorpay order
        notes = {
            'user_id': str(request.user.id),
            'course_id': str(course_id),
            'plan_id': str(plan_id),
            'email': request.user.email,
            'course_title': course.title,
            'plan_name': plan.name
        }
        
        # Create Razorpay order
        try:
            order_response = razorpay_service.create_order(
                amount=float(plan.amount),
                receipt=receipt_id,
                notes=notes
            )
            
            # Create payment order record in database
            payment_order = PaymentOrder.objects.create(
                user=request.user,
                course=course,
                plan=plan,
                amount=plan.amount,
                razorpay_order_id=order_response['id'],
                status='CREATED'
            )
            
            # Return order details to client
            response_data = {
                'order_id': order_response['id'],
                'amount': order_response['amount'] / 100,  # Convert paise to rupees
                'currency': order_response['currency'],
                'payment_order_id': payment_order.id,
                'key_id': settings.RAZORPAY_KEY_ID,
                'user_info': {
                    'name': request.user.full_name,
                    'email': request.user.email,
                    'contact': request.user.phone_number or ''
                },
                'notes': notes
            }
            
            return Response(response_data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Failed to create Razorpay order: {str(e)}")
            return Response(
                {"error": "Failed to create payment order. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class VerifyPaymentView(views.APIView):
    """
    API endpoint for verifying Razorpay payment and completing course enrollment
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_summary="Verify payment",
        operation_description="Verifies a Razorpay payment and completes the course enrollment process.",
        request_body=VerifyPaymentSerializer,
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Payment verified and enrollment completed",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'purchase': openapi.Schema(type=openapi.TYPE_OBJECT),
                        'enrollment_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'subscription_end_date': openapi.Schema(type=openapi.TYPE_STRING, format='date-time')
                    }
                )
            ),
            status.HTTP_400_BAD_REQUEST: "Invalid payment signature or request data",
            status.HTTP_500_INTERNAL_SERVER_ERROR: "Payment verification failed"
        }
    )
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = VerifyPaymentSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Get payment details
        razorpay_payment_id = serializer.validated_data.get('razorpay_payment_id')
        razorpay_order_id = serializer.validated_data.get('razorpay_order_id')
        razorpay_signature = serializer.validated_data.get('razorpay_signature')
        
        # Verify payment signature
        try:
            is_valid = razorpay_service.verify_payment_signature(
                razorpay_payment_id,
                razorpay_order_id,
                razorpay_signature
            )
            
            if not is_valid:
                logger.error(f"Invalid payment signature: {razorpay_payment_id}")
                return Response(
                    {"error": "Invalid payment signature"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get payment order
            payment_order = get_object_or_404(
                PaymentOrder, 
                razorpay_order_id=razorpay_order_id,
                user=request.user
            )
            
            # Update payment order
            payment_order.status = 'PAID'
            payment_order.razorpay_payment_id = razorpay_payment_id
            payment_order.razorpay_signature = razorpay_signature
            payment_order.save()
            
            # Get course and plan details
            course = payment_order.course
            plan = payment_order.plan
            
            # Get payment card if available
            payment_card = None
            card_id = request.data.get('payment_card_id')
            if card_id:
                try:
                    payment_card = PaymentCard.objects.get(pk=card_id, user=request.user)
                except PaymentCard.DoesNotExist:
                    pass
            
            # Process subscription payment
            subscription, purchase, enrollment = razorpay_service.process_subscription_payment(
                user=request.user,
                plan=plan,
                course=course,
                payment_id=razorpay_payment_id,
                order_id=razorpay_order_id,
                payment_card=payment_card
            )
            
            # Return success response
            return Response({
                "message": "Payment successful and course enrollment completed",
                "purchase": PurchaseSerializer(purchase).data,
                "enrollment_id": enrollment.id,
                "subscription_end_date": subscription.end_date
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Payment verification failed: {str(e)}")
            return Response(
                {"error": "Payment verification failed. Please contact support."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@swagger_auto_schema(
    method='post',
    operation_summary="Cancel subscription",
    operation_description="Cancels a user's active subscription.",
    responses={
        status.HTTP_200_OK: openapi.Response(
            description="Subscription canceled successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING)
                }
            )
        ),
        status.HTTP_404_NOT_FOUND: "Subscription not found",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Failed to cancel subscription"
    }
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cancel_subscription(request, subscription_id):
    """
    API endpoint for canceling a subscription
    """
    try:
        subscription = get_object_or_404(
            UserSubscription, 
            id=subscription_id,
            user=request.user
        )
        
        # Mark subscription as inactive
        subscription.is_active = False
        subscription.save()
        
        # Create notification
        Notification.objects.create(
            user=request.user,
            title="Subscription Canceled",
            message=f"Your subscription to {subscription.plan.name} has been canceled",
            notification_type='SUBSCRIPTION',
            is_seen=False
        )
        
        return Response({
            "message": "Subscription canceled successfully"
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Subscription cancellation failed: {str(e)}")
        return Response(
            {"error": "Failed to cancel subscription. Please try again."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@swagger_auto_schema(
    method='post',
    operation_summary="Renew subscription",
    operation_description="Creates a new payment order to renew an expired or inactive subscription.",
    responses={
        status.HTTP_201_CREATED: openapi.Response(
            description="Renewal order created successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'order_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                    'currency': openapi.Schema(type=openapi.TYPE_STRING),
                    'payment_order_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'key_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'user_info': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'name': openapi.Schema(type=openapi.TYPE_STRING),
                            'email': openapi.Schema(type=openapi.TYPE_STRING),
                            'contact': openapi.Schema(type=openapi.TYPE_STRING)
                        }
                    ),
                    'notes': openapi.Schema(type=openapi.TYPE_OBJECT)
                }
            )
        ),
        status.HTTP_400_BAD_REQUEST: "Subscription is still active",
        status.HTTP_404_NOT_FOUND: "Subscription not found",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Failed to create renewal order"
    }
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def renew_subscription(request, subscription_id):
    """
    API endpoint for renewing a subscription
    """
    try:
        subscription = get_object_or_404(
            UserSubscription, 
            id=subscription_id,
            user=request.user
        )
        
        # Check if user has an active subscription
        if subscription.is_active and subscription.end_date > timezone.now():
            return Response({
                "error": "Subscription is still active. Cannot renew yet."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create a new order for renewal
        plan = subscription.plan
        
        # Generate a unique receipt ID
        receipt_id = f"renew_{str(uuid.uuid4())[:8]}"
        
        # Create notes for Razorpay order
        notes = {
            'user_id': str(request.user.id),
            'subscription_id': str(subscription.id),
            'plan_id': str(plan.id),
            'email': request.user.email,
            'renewal': 'true',
            'plan_name': plan.name
        }
        
        # Create Razorpay order
        order_response = razorpay_service.create_order(
            amount=float(plan.amount),
            receipt=receipt_id,
            notes=notes
        )
        
        # Create payment order record
        payment_order = PaymentOrder.objects.create(
            user=request.user,
            plan=plan,
            amount=plan.amount,
            razorpay_order_id=order_response['id'],
            status='CREATED'
        )
        
        # Return order details
        response_data = {
            'order_id': order_response['id'],
            'amount': order_response['amount'] / 100,
            'currency': order_response['currency'],
            'payment_order_id': payment_order.id,
            'key_id': settings.RAZORPAY_KEY_ID,
            'user_info': {
                'name': request.user.full_name,
                'email': request.user.email,
                'contact': request.user.phone_number or ''
            },
            'notes': notes
        }
        
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Subscription renewal failed: {str(e)}")
        return Response(
            {"error": "Failed to create renewal order. Please try again."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        
        
@swagger_auto_schema(
    method='post',
    operation_summary="Razorpay webhook handler",
    operation_description="Handles webhook events from Razorpay for payment processing.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'event': openapi.Schema(type=openapi.TYPE_STRING),
            'payload': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'payment': openapi.Schema(type=openapi.TYPE_OBJECT),
                    'order': openapi.Schema(type=openapi.TYPE_OBJECT),
                    'refund': openapi.Schema(type=openapi.TYPE_OBJECT)
                }
            )
        }
    ),
    responses={
        200: "Event processed successfully",
        400: "Invalid signature or request data",
        500: "Server error"
    }
)
@api_view(['POST'])
@csrf_exempt
def razorpay_webhook(request):
    """
    Webhook handler for Razorpay events
    """
    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    
    try:
        # Verify webhook signature
        razorpay_signature = request.headers.get('X-Razorpay-Signature')
        if not razorpay_signature:
            logger.error("No Razorpay signature found in webhook request")
            return HttpResponse(status=400)
        
        # Get request body
        request_body = request.body.decode('utf-8')
        
        # Generate signature
        generated_signature = hmac.new(
            webhook_secret.encode(),
            request_body.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Verify signature
        if not hmac.compare_digest(generated_signature, razorpay_signature):
            logger.error("Invalid Razorpay webhook signature")
            return HttpResponse(status=400)
        
        # Process webhook payload
        payload = json.loads(request_body)
        event = payload.get('event')
        
        logger.info(f"Received Razorpay webhook: {event}")
        
        if event == 'payment.authorized':
            # Payment was authorized, update order and create subscription
            payment_data = payload.get('payload', {}).get('payment', {})
            order_id = payment_data.get('order_id')
            payment_id = payment_data.get('id')
            
            # Find the payment order
            try:
                payment_order = PaymentOrder.objects.get(razorpay_order_id=order_id)
                
                # Update payment order status
                payment_order.status = 'PAID'
                payment_order.razorpay_payment_id = payment_id
                payment_order.save()
                
                # Get user, course, and plan
                user = payment_order.user
                course = payment_order.course
                plan = payment_order.plan
                
                # Check if this is a renewal or new subscription
                notes = payment_data.get('notes', {})
                is_renewal = notes.get('renewal') == 'true'
                
                if is_renewal:
                    # Update existing subscription
                    subscription_id = notes.get('subscription_id')
                    subscription = UserSubscription.objects.get(id=subscription_id)
                    
                    # Extend subscription by 30 days
                    if subscription.end_date < timezone.now():
                        # If expired, start from now
                        subscription.start_date = timezone.now()
                        subscription.end_date = timezone.now() + timezone.timedelta(days=30)
                    else:
                        # If not expired, add 30 days to current end date
                        subscription.end_date += timezone.timedelta(days=30)
                    
                    subscription.is_active = True
                    subscription.save()
                    
                    # Create purchase record
                    transaction_id = str(uuid.uuid4())
                    Purchase.objects.create(
                        user=user,
                        course=course if course else None,
                        amount=payment_order.amount,
                        transaction_id=transaction_id,
                        razorpay_order_id=order_id,
                        razorpay_payment_id=payment_id,
                        payment_status='COMPLETED'
                    )
                    
                    # Create notification
                    Notification.objects.create(
                        user=user,
                        title="Subscription Renewed",
                        message=f"Your subscription to {plan.name} has been renewed successfully",
                        notification_type='SUBSCRIPTION',
                        is_seen=False
                    )
                    
                else:
                    # New subscription
                    # Create subscription
                    subscription = UserSubscription.objects.create(
                        user=user,
                        plan=plan,
                        start_date=timezone.now(),
                        end_date=timezone.now() + timezone.timedelta(days=30),
                        is_active=True
                    )
                    
                    # Create purchase record
                    transaction_id = str(uuid.uuid4())
                    Purchase.objects.create(
                        user=user,
                        course=course,
                        amount=payment_order.amount,
                        transaction_id=transaction_id,
                        razorpay_order_id=order_id,
                        razorpay_payment_id=payment_id,
                        payment_status='COMPLETED'
                    )
                    
                    # Create enrollment if not exists
                    if course:
                        Enrollment.objects.get_or_create(
                            user=user,
                            course=course
                        )
                    
                    # Create notification
                    Notification.objects.create(
                        user=user,
                        title="Subscription Successful",
                        message=f"Your subscription to {plan.name} has been activated successfully",
                        notification_type='SUBSCRIPTION',
                        is_seen=False
                    )
                
                logger.info(f"Successfully processed payment: {payment_id} for order: {order_id}")
                
            except PaymentOrder.DoesNotExist:
                logger.error(f"Payment order not found for order_id: {order_id}")
            
            except Exception as e:
                logger.error(f"Error processing payment.authorized webhook: {str(e)}")
        
        elif event == 'payment.failed':
            # Payment failed, update order status
            payment_data = payload.get('payload', {}).get('payment', {})
            order_id = payment_data.get('order_id')
            payment_id = payment_data.get('id')
            
            try:
                payment_order = PaymentOrder.objects.get(razorpay_order_id=order_id)
                
                # Update payment order status
                payment_order.status = 'FAILED'
                payment_order.razorpay_payment_id = payment_id
                payment_order.save()
                
                # Create notification
                Notification.objects.create(
                    user=payment_order.user,
                    title="Payment Failed",
                    message="Your payment has failed. Please try again.",
                    notification_type='PAYMENT',
                    is_seen=False
                )
                
                logger.info(f"Marked payment as failed: {payment_id} for order: {order_id}")
                
            except PaymentOrder.DoesNotExist:
                logger.error(f"Payment order not found for order_id: {order_id}")
            
            except Exception as e:
                logger.error(f"Error processing payment.failed webhook: {str(e)}")
        
        elif event == 'refund.created':
            # Refund created, update purchase record
            refund_data = payload.get('payload', {}).get('refund', {})
            payment_id = refund_data.get('payment_id')
            
            try:
                # Find the purchase record
                purchase = Purchase.objects.get(razorpay_payment_id=payment_id)
                
                # Update purchase status
                purchase.payment_status = 'REFUNDED'
                purchase.save()
                
                # Create notification
                Notification.objects.create(
                    user=purchase.user,
                    title="Refund Processed",
                    message=f"Your refund for {purchase.course.title if purchase.course else 'subscription'} has been processed.",
                    notification_type='PAYMENT',
                    is_seen=False
                )
                
                logger.info(f"Processed refund for payment_id: {payment_id}")
                
            except Purchase.DoesNotExist:
                logger.error(f"Purchase record not found for payment_id: {payment_id}")
            
            except Exception as e:
                logger.error(f"Error processing refund.created webhook: {str(e)}")
        
        return HttpResponse(status=200)
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return HttpResponse(status=500)