from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from .serializers import CustomLoginSerializer, CustomRegisterSerializer, ForgotPasswordSerializer, UserDetailsSerializer, VerifyOTPSerializer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from dj_rest_auth.registration.views import RegisterView
from dj_rest_auth.views import LoginView
from rest_framework.authtoken.models import Token
from django.db import IntegrityError 
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

User = get_user_model()

class ForgotPasswordView(generics.GenericAPIView):
    """
    API endpoint for initiating password reset.
    """
    permission_classes = [AllowAny]
    serializer_class = ForgotPasswordSerializer
    
    @swagger_auto_schema(
        operation_summary="Request password reset OTP",
        operation_description="Sends a one-time password (OTP) to the user's email for password reset.",
        request_body=ForgotPasswordSerializer,
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="OTP sent successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            ),
            status.HTTP_404_NOT_FOUND: openapi.Response(
                description="User not found",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'error': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            )
        }
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        
        try:
            user = User.objects.get(email=email)
            otp = user.generate_otp()
            
            # Send OTP via email
            subject = 'Password Reset OTP'
            message = f'Your OTP for password reset is: {otp}. This OTP is valid for 10 minutes.'
            send_mail(subject, message, settings.EMAIL_HOST_USER, [email])
            
            return Response({'message': 'OTP sent to your email'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'User with this email does not exist'}, status=status.HTTP_404_NOT_FOUND)

# VerifyOTPView
class VerifyOTPView(generics.GenericAPIView):
    """
    API endpoint for verifying OTP and resetting password.
    """
    permission_classes = [AllowAny]
    serializer_class = VerifyOTPSerializer
    
    @swagger_auto_schema(
        operation_summary="Verify OTP and reset password",
        operation_description="Verifies the OTP sent to the user's email and resets the password.",
        request_body=VerifyOTPSerializer,
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Password reset successful",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Invalid or expired OTP",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'error': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            ),
            status.HTTP_404_NOT_FOUND: openapi.Response(
                description="User not found",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'error': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            )
        }
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']
        new_password = serializer.validated_data['new_password']
        
        try:
            user = User.objects.get(email=email)
            if user.verify_otp(otp):
                user.set_password(new_password)
                user.save()
                return Response({'message': 'Password reset successful'}, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({'error': 'User with this email does not exist'}, status=status.HTTP_404_NOT_FOUND)
        
class GoogleLoginView(SocialLoginView):
    """
    API endpoint for Google OAuth authentication.
    """
    adapter_class = GoogleOAuth2Adapter
    callback_url = 'YOUR_CALLBACK_URL'  # Can also be set to 'postmessage' for mobile/web apps
    client_class = OAuth2Client
    
    @swagger_auto_schema(
        operation_summary="Login with Google",
        operation_description="Authenticates a user using Google OAuth2 credentials.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['access_token'],
            properties={
                'access_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Google OAuth2 access token'
                ),
                'id_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Google OAuth2 ID token (optional)'
                ),
            }
        ),
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Successfully authenticated",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'key': openapi.Schema(type=openapi.TYPE_STRING, description='Authentication token'),
                        'user': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'email': openapi.Schema(type=openapi.TYPE_STRING),
                                'full_name': openapi.Schema(type=openapi.TYPE_STRING),
                                'phone_number': openapi.Schema(type=openapi.TYPE_STRING)
                            }
                        )
                    }
                )
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Invalid token",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'error': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            )
        }
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
    
class CustomRegisterView(RegisterView):
    serializer_class = CustomRegisterSerializer  # Explicitly set serializer class
    
    def get_serializer(self, *args, **kwargs):
        logger.info("Using CustomRegisterSerializer in get_serializer")
        return super().get_serializer(*args, **kwargs)
    
    def create(self, request, *args, **kwargs):
        # Log the request data for debugging
        email = request.data.get('email', '')
        logger.info(f"Registration attempt with email: {email}")
        
        # Check if user exists first with explicit logging
        existing_user = User.objects.filter(email__iexact=email).exists()
        logger.info(f"User exists check (view level): {existing_user}")
        
        serializer = self.get_serializer(data=request.data)
        logger.info(f"Serializer class: {serializer.__class__.__name__}")
        
        # Let the serializer handle validation
        try:
            serializer.is_valid(raise_exception=True)
            logger.info("Serializer validation passed")
        except Exception as e:
            logger.error(f"Validation error: {str(e)}")
            raise
        
        # Create the user
        try:
            user = self.perform_create(serializer)
            logger.info(f"User created successfully: {user.email}")
            
            # Create token
            token, created = Token.objects.get_or_create(user=user)
            
            # Create response
            data = {'key': token.key}
            user_data = UserDetailsSerializer(user).data
            data['user'] = user_data
            
            return Response(data, status=status.HTTP_201_CREATED)
            
        except IntegrityError as e:
            logger.error(f"IntegrityError during user creation: {str(e)}")
            return Response(
                {"email": ["A user with this email already exists."]},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error during user creation: {str(e)}")
            return Response(
                {"non_field_errors": ["An error occurred during registration."]},
                status=status.HTTP_400_BAD_REQUEST
            )
    
class CustomLoginView(LoginView):
    serializer_class = CustomLoginSerializer
    
    def get_response(self):
        response = super().get_response()
        # Add user details to the response
        user = self.user
        user_data = UserDetailsSerializer(user).data
        response.data['user'] = user_data
        return response