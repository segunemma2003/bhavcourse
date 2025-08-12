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

from .models import Course, AppleIAPProduct, Purchase, Enrollment, Notification
from .apple_iap_service import AppleIAPService
from .serializers import AppleIAPProductSerializer

logger = logging.getLogger(__name__)

# Initialize Apple IAP service
apple_iap_service = AppleIAPService()


class AppleIAPVerifyReceiptView(views.APIView):
    """
    API endpoint for verifying Apple In-App Purchase receipts
    """
    permission_classes = [permissions.IsAuthenticated]
    
    class VerifyReceiptSerializer(serializers.Serializer):
        receipt_data = serializers.CharField(required=True, help_text="Base64 encoded receipt data")
        course_id = serializers.IntegerField(required=False, help_text="Course ID (optional if product is configured)")
        plan_type = serializers.CharField(required=False, help_text="Plan type (optional if product is configured)")
        
        def validate_receipt_data(self, value):
            if not apple_iap_service.validate_receipt_format(value):
                raise serializers.ValidationError("Invalid receipt data format")
            return value
        
        def validate_course_id(self, value):
            try:
                Course.objects.get(pk=value)
                return value
            except Course.DoesNotExist:
                raise serializers.ValidationError("Course does not exist")
    
    @swagger_auto_schema(
        operation_summary="Verify Apple IAP receipt",
        operation_description="Verifies an Apple In-App Purchase receipt and processes the purchase.",
        request_body=VerifyReceiptSerializer,
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Receipt verified and purchase processed",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'purchase_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'enrollment_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'transaction_id': openapi.Schema(type=openapi.TYPE_STRING),
                        'expiry_date': openapi.Schema(type=openapi.TYPE_STRING, format='date-time')
                    }
                )
            ),
            status.HTTP_400_BAD_REQUEST: "Invalid receipt data or request",
            status.HTTP_500_INTERNAL_SERVER_ERROR: "Receipt verification failed"
        }
    )
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = self.VerifyReceiptSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        receipt_data = serializer.validated_data['receipt_data']
        course_id = serializer.validated_data.get('course_id')
        plan_type = serializer.validated_data.get('plan_type')
        
        try:
            # Process the receipt
            result = apple_iap_service.process_receipt(
                receipt_data=receipt_data,
                user=request.user,
                course_id=course_id,
                plan_type=plan_type
            )
            
            if result['success']:
                return Response(result, status=status.HTTP_200_OK)
            else:
                return Response(
                    {'error': result['error']},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Apple IAP receipt verification failed: {str(e)}")
            return Response(
                {'error': 'Receipt verification failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AppleIAPProductsView(views.APIView):
    """
    API endpoint for managing Apple IAP products
    """
    permission_classes = [permissions.IsAuthenticated]
    
    class CreateProductSerializer(serializers.Serializer):
        product_id = serializers.CharField(max_length=100, help_text="Apple Product ID")
        course_id = serializers.IntegerField()
        plan_type = serializers.ChoiceField(choices=Course.CoursePlanType.choices)
        price_usd = serializers.DecimalField(max_digits=10, decimal_places=2)
        
        def validate_course_id(self, value):
            try:
                Course.objects.get(pk=value)
                return value
            except Course.DoesNotExist:
                raise serializers.ValidationError("Course does not exist")
        
        def validate_product_id(self, value):
            if AppleIAPProduct.objects.filter(product_id=value).exists():
                raise serializers.ValidationError("Product ID already exists")
            return value
    
    @swagger_auto_schema(
        operation_summary="Create Apple IAP product",
        operation_description="Creates a new Apple IAP product configuration.",
        request_body=CreateProductSerializer,
        responses={
            status.HTTP_201_CREATED: AppleIAPProductSerializer,
            status.HTTP_400_BAD_REQUEST: "Invalid request data"
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.CreateProductSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            product = apple_iap_service.create_product(
                product_id=serializer.validated_data['product_id'],
                course_id=serializer.validated_data['course_id'],
                plan_type=serializer.validated_data['plan_type'],
                price_usd=serializer.validated_data['price_usd']
            )
            
            return Response(
                AppleIAPProductSerializer(product).data,
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            logger.error(f"Failed to create Apple IAP product: {str(e)}")
            return Response(
                {'error': 'Failed to create product'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @swagger_auto_schema(
        operation_summary="List Apple IAP products",
        operation_description="Lists all Apple IAP products for a course.",
        manual_parameters=[
            openapi.Parameter(
                'course_id',
                openapi.IN_QUERY,
                description="Course ID to filter products",
                type=openapi.TYPE_INTEGER,
                required=False
            )
        ],
        responses={
            status.HTTP_200_OK: AppleIAPProductSerializer(many=True)
        }
    )
    def get(self, request, *args, **kwargs):
        course_id = request.query_params.get('course_id')
        
        if course_id:
            products = apple_iap_service.get_products_for_course(course_id)
        else:
            products = AppleIAPProduct.objects.filter(is_active=True)
        
        return Response(
            AppleIAPProductSerializer(products, many=True).data,
            status=status.HTTP_200_OK
        )


class AppleIAPProductDetailView(views.APIView):
    """
    API endpoint for managing individual Apple IAP products
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_summary="Get Apple IAP product",
        operation_description="Retrieves details of a specific Apple IAP product.",
        responses={
            status.HTTP_200_OK: AppleIAPProductSerializer,
            status.HTTP_404_NOT_FOUND: "Product not found"
        }
    )
    def get(self, request, product_id, *args, **kwargs):
        try:
            product = get_object_or_404(AppleIAPProduct, product_id=product_id)
            return Response(
                AppleIAPProductSerializer(product).data,
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Failed to retrieve Apple IAP product: {str(e)}")
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @swagger_auto_schema(
        operation_summary="Update Apple IAP product",
        operation_description="Updates an existing Apple IAP product.",
        request_body=AppleIAPProductSerializer,
        responses={
            status.HTTP_200_OK: AppleIAPProductSerializer,
            status.HTTP_404_NOT_FOUND: "Product not found"
        }
    )
    def put(self, request, product_id, *args, **kwargs):
        try:
            product = get_object_or_404(AppleIAPProduct, product_id=product_id)
            serializer = AppleIAPProductSerializer(product, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Failed to update Apple IAP product: {str(e)}")
            return Response(
                {'error': 'Failed to update product'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @swagger_auto_schema(
        operation_summary="Delete Apple IAP product",
        operation_description="Deactivates an Apple IAP product.",
        responses={
            status.HTTP_200_OK: "Product deactivated successfully",
            status.HTTP_404_NOT_FOUND: "Product not found"
        }
    )
    def delete(self, request, product_id, *args, **kwargs):
        try:
            product = get_object_or_404(AppleIAPProduct, product_id=product_id)
            product.is_active = False
            product.save()
            
            return Response(
                {'message': 'Product deactivated successfully'},
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Failed to deactivate Apple IAP product: {str(e)}")
            return Response(
                {'error': 'Failed to deactivate product'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@swagger_auto_schema(
    method='post',
    operation_summary="Apple IAP webhook handler",
    operation_description="Handles webhook events from Apple for IAP processing.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'signedPayload': openapi.Schema(type=openapi.TYPE_STRING)
        }
    ),
    responses={
        200: "Event processed successfully",
        400: "Invalid request data",
        500: "Server error"
    }
)
@api_view(['POST'])
def apple_iap_webhook(request):
    """
    Webhook handler for Apple IAP events
    """
    try:
        # Extract signed payload
        signed_payload = request.data.get('signedPayload')
        
        if not signed_payload:
            logger.error("No signed payload in Apple IAP webhook")
            return Response({'error': 'No signed payload'}, status=400)
        
        # TODO: Implement JWT verification for signed payload
        # For now, we'll log the webhook and process it
        
        logger.info(f"Received Apple IAP webhook: {signed_payload}")
        
        # Process the webhook payload
        # This would typically involve:
        # 1. Verifying the JWT signature
        # 2. Extracting transaction information
        # 3. Processing the purchase
        
        return Response({'status': 'processed'}, status=200)
        
    except Exception as e:
        logger.error(f"Apple IAP webhook processing error: {str(e)}")
        return Response({'error': 'Webhook processing failed'}, status=500) 