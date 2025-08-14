from rest_framework import status, views, permissions, serializers
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import logging

from .models import Course, CoursePlanType, PaymentOrder
from .payment_link_service import PaymentLinkService

logger = logging.getLogger(__name__)

# Initialize payment link service
payment_link_service = PaymentLinkService()


class CreatePaymentLinkView(views.APIView):
    """
    API endpoint for creating payment link requests
    """
    permission_classes = [permissions.IsAuthenticated]
    
    class CreatePaymentLinkSerializer(serializers.Serializer):
        course_id = serializers.IntegerField(help_text="Course ID to purchase")
        plan_type = serializers.ChoiceField(
            choices=CoursePlanType.choices,
            help_text="Subscription plan type"
        )
        amount = serializers.DecimalField(
            max_digits=10,
            decimal_places=2,
            required=False,
            help_text="Optional amount override"
        )
        
        def validate_course_id(self, value):
            try:
                Course.objects.get(pk=value)
                return value
            except Course.DoesNotExist:
                raise serializers.ValidationError("Course does not exist")
    
    @swagger_auto_schema(
        operation_summary="Create payment link request",
        operation_description="Creates a payment link request and sends email to user with payment link.",
        request_body=CreatePaymentLinkSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response(
                description="Payment link request created successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'reference_id': openapi.Schema(type=openapi.TYPE_STRING),
                        'payment_order_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'email_sent': openapi.Schema(type=openapi.TYPE_BOOLEAN)
                    }
                )
            ),
            status.HTTP_400_BAD_REQUEST: "Invalid request data",
            status.HTTP_500_INTERNAL_SERVER_ERROR: "Failed to create payment link"
        }
    )
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = self.CreatePaymentLinkSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        course_id = serializer.validated_data['course_id']
        plan_type = serializer.validated_data['plan_type']
        amount = serializer.validated_data.get('amount')
        
        try:
            # Create payment link request
            result = payment_link_service.create_payment_link_request(
                user=request.user,
                course_id=course_id,
                plan_type=plan_type,
                amount=amount
            )
            
            if result['success']:
                return Response(result, status=status.HTTP_201_CREATED)
            else:
                return Response(
                    {'error': result['error']},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Payment link creation failed: {str(e)}")
            return Response(
                {'error': 'Failed to create payment link request'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PaymentLinkStatusView(views.APIView):
    """
    API endpoint for checking payment link status
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_summary="Check payment link status",
        operation_description="Checks the status of a payment link request.",
        manual_parameters=[
            openapi.Parameter(
                'reference_id',
                openapi.IN_QUERY,
                description="Payment link reference ID",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Payment link status",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'reference_id': openapi.Schema(type=openapi.TYPE_STRING),
                        'status': openapi.Schema(type=openapi.TYPE_STRING),
                        'course_title': openapi.Schema(type=openapi.TYPE_STRING),
                        'plan_type': openapi.Schema(type=openapi.TYPE_STRING),
                        'amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'created_at': openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),
                        'paid_at': openapi.Schema(type=openapi.TYPE_STRING, format='date-time')
                    }
                )
            ),
            status.HTTP_404_NOT_FOUND: "Payment link not found"
        }
    )
    def get(self, request, *args, **kwargs):
        reference_id = request.query_params.get('reference_id')
        
        if not reference_id:
            return Response(
                {'error': 'Reference ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            payment_order = get_object_or_404(
                PaymentOrder,
                reference_id=reference_id,
                user=request.user,
                payment_method='PAYMENT_LINK'
            )
            
            return Response({
                'reference_id': payment_order.reference_id,
                'status': payment_order.status,
                'course_title': payment_order.course.title,
                'plan_type': dict(CoursePlanType.choices)[payment_order.plan_type],
                'amount': float(payment_order.amount),
                'created_at': payment_order.created_at.isoformat(),
                'paid_at': payment_order.paid_at.isoformat() if payment_order.paid_at else None
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Payment link status check failed: {str(e)}")
            return Response(
                {'error': 'Payment link not found'},
                status=status.HTTP_404_NOT_FOUND
            )


@swagger_auto_schema(
    method='post',
    operation_summary="Verify payment link payment",
    operation_description="Verifies payment made through payment link and processes enrollment.",
    manual_parameters=[
        openapi.Parameter(
            'payment_id',
            openapi.IN_QUERY,
            description="Razorpay payment ID",
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'reference_id',
            openapi.IN_QUERY,
            description="Payment link reference ID",
            type=openapi.TYPE_STRING,
            required=True
        )
    ],
    responses={
        status.HTTP_200_OK: openapi.Response(
            description="Payment verified successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'enrollment_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'purchase_id': openapi.Schema(type=openapi.TYPE_INTEGER)
                }
            )
        ),
        status.HTTP_400_BAD_REQUEST: "Invalid payment or reference ID",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Payment verification failed"
    }
)
@api_view(['POST'])
def verify_payment_link_payment(request):
    """
    Verify payment made through payment link
    """
    payment_id = request.query_params.get('payment_id')
    reference_id = request.query_params.get('reference_id')
    
    if not payment_id or not reference_id:
        return Response(
            {'error': 'Payment ID and Reference ID are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Verify payment
        result = payment_link_service.verify_payment_link_payment(
            payment_id=payment_id,
            reference_id=reference_id
        )
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['error']},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Payment link verification failed: {str(e)}")
        return Response(
            {'error': 'Payment verification failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(
    method='get',
    operation_summary="Payment link callback",
    operation_description="Callback URL for Razorpay payment link payments.",
    manual_parameters=[
        openapi.Parameter(
            'razorpay_payment_id',
            openapi.IN_QUERY,
            description="Razorpay payment ID",
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'razorpay_payment_link_id',
            openapi.IN_QUERY,
            description="Razorpay payment link ID",
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'razorpay_payment_link_reference_id',
            openapi.IN_QUERY,
            description="Payment link reference ID",
            type=openapi.TYPE_STRING,
            required=True
        )
    ],
    responses={
        status.HTTP_200_OK: "Payment processed successfully",
        status.HTTP_400_BAD_REQUEST: "Invalid payment data",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Payment processing failed"
    }
)
@api_view(['GET'])
def payment_link_callback(request):
    """
    Callback URL for Razorpay payment link payments
    """
    payment_id = request.query_params.get('razorpay_payment_id')
    payment_link_id = request.query_params.get('razorpay_payment_link_id')
    reference_id = request.query_params.get('razorpay_payment_link_reference_id')
    
    if not all([payment_id, payment_link_id, reference_id]):
        return Response(
            {'error': 'Missing required parameters'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Verify payment
        result = payment_link_service.verify_payment_link_payment(
            payment_id=payment_id,
            reference_id=reference_id
        )
        
        if result['success']:
            # Redirect to success page or return success response
            return Response({
                'success': True,
                'message': 'Payment completed successfully',
                'redirect_url': f"{settings.FRONTEND_URL}/payment-success?reference_id={reference_id}"
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'error': result['error'],
                'redirect_url': f"{settings.FRONTEND_URL}/payment-failed?reference_id={reference_id}"
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"Payment link callback processing failed: {str(e)}")
        return Response({
            'success': False,
            'error': 'Payment processing failed',
            'redirect_url': f"{settings.FRONTEND_URL}/payment-failed?reference_id={reference_id}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 