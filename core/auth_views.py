from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from .serializers import CustomLoginSerializer, CustomRegisterSerializer, ForgotPasswordSerializer, ResetPasswordSerializer, UserDetailsSerializer, VerifyOTPSerializer
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
    API endpoint for requesting password reset OTP.
    Step 1: Send OTP to email
    """
    permission_classes = [AllowAny]
    serializer_class = ForgotPasswordSerializer
    
    @swagger_auto_schema(
        operation_summary="Request password reset OTP",
        operation_description="Sends a one-time password (OTP) to the user's email for password reset. The OTP is valid for 10 minutes.",
        request_body=ForgotPasswordSerializer,
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="OTP sent successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'otp_expires_in': openapi.Schema(type=openapi.TYPE_STRING)
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
            ),
            status.HTTP_400_BAD_REQUEST: "Invalid email format"
        },
        tags=['Authentication']
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        
        try:
            user = User.objects.get(email__iexact=email)
            otp = user.generate_otp()
            
            # Send OTP via email
            subject = 'Password Reset OTP'
            message = f'''
            Hello {user.full_name},
            
            You requested a password reset for your account.
            
            Your OTP for password reset is: {otp}
            
            This OTP is valid for 10 minutes.
            
            If you didn't request this, please ignore this email.
            
            Best regards,
            The Course App Team
            '''
            
            send_mail(subject, message, settings.EMAIL_HOST_USER, [email])
            logger.info(f"Password reset OTP sent to {email}")
            
            return Response({
                'message': 'OTP sent to your email successfully',
                'otp_expires_in': '10 minutes'
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            logger.warning(f"Password reset attempted for non-existent email: {email}")
            return Response(
                {'error': 'User with this email does not exist'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error sending OTP to {email}: {str(e)}")
            return Response(
                {'error': 'Failed to send OTP. Please try again later.'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
# VerifyOTPView
class VerifyOTPView(generics.GenericAPIView):
    """
    API endpoint for verifying OTP.
    Step 2: Verify the OTP sent to email
    """
    permission_classes = [AllowAny]
    serializer_class = VerifyOTPSerializer
    
    @swagger_auto_schema(
        operation_summary="Verify password reset OTP",
        operation_description="Verifies the OTP sent to the user's email. Call this before attempting to reset the password.",
        request_body=VerifyOTPSerializer,
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="OTP verified successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'otp_verified': openapi.Schema(type=openapi.TYPE_BOOLEAN)
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
        },
        tags=['Authentication']
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']
        
        try:
            user = User.objects.get(email__iexact=email)
            
            if user.verify_otp(otp):
                logger.info(f"OTP verified successfully for {email}")
                return Response({
                    'message': 'OTP verified successfully',
                    'otp_verified': True
                }, status=status.HTTP_200_OK)
            else:
                logger.warning(f"Invalid or expired OTP for {email}")
                return Response(
                    {'error': 'Invalid or expired OTP'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except User.DoesNotExist:
            logger.warning(f"OTP verification attempted for non-existent email: {email}")
            return Response(
                {'error': 'User with this email does not exist'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error verifying OTP for {email}: {str(e)}")
            return Response(
                {'error': 'An error occurred while verifying OTP'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ResetPasswordView(generics.GenericAPIView):
    """
    API endpoint for resetting password with verified OTP.
    Step 3: Reset password using email, verified OTP, and new password
    """
    permission_classes = [AllowAny]
    serializer_class = ResetPasswordSerializer
    
    @swagger_auto_schema(
        operation_summary="Reset password with verified OTP",
        operation_description="Resets the user's password using the verified OTP. The OTP must be verified before calling this endpoint.",
        request_body=ResetPasswordSerializer,
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Password reset successful",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'password_reset': openapi.Schema(type=openapi.TYPE_BOOLEAN)
                    }
                )
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Invalid data or OTP not verified",
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
        },
        tags=['Authentication']
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']
        new_password = serializer.validated_data['new_password']
        
        try:
            user = User.objects.get(email__iexact=email)
            
            # Check if the provided OTP matches and is verified
            if not user.otp_verified:
                logger.warning(f"Attempt to reset password with unverified OTP for {email}")
                return Response(
                    {'error': 'OTP not verified. Please verify OTP first.'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Double-check the OTP matches (security measure)
            if user.otp != otp:
                logger.warning(f"OTP mismatch during password reset for {email}")
                return Response(
                    {'error': 'Invalid OTP'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if OTP hasn't expired
            if user.otp_expiry and timezone.now() > user.otp_expiry:
                logger.warning(f"Expired OTP used for password reset for {email}")
                user.clear_otp()  # Clear expired OTP
                return Response(
                    {'error': 'OTP has expired. Please request a new one.'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Reset the password
            user.set_password(new_password)
            user.clear_otp()  # Clear OTP after successful password reset
            
            # Send confirmation email
            subject = 'Password Reset Successful'
            message = f'''
            Hello {user.full_name},
            
            Your password has been successfully reset.
            
            If you didn't make this change, please contact us immediately.
            
            Best regards,
            The Course App Team
            '''
            
            try:
                send_mail(subject, message, settings.EMAIL_HOST_USER, [email])
            except Exception as email_error:
                logger.error(f"Failed to send confirmation email to {email}: {str(email_error)}")
                # Don't fail the password reset if email sending fails
            
            logger.info(f"Password reset successful for {email}")
            return Response({
                'message': 'Password reset successful',
                'password_reset': True
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            logger.warning(f"Password reset attempted for non-existent email: {email}")
            return Response(
                {'error': 'User with this email does not exist'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error resetting password for {email}: {str(e)}")
            return Response(
                {'error': 'An error occurred while resetting password'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
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