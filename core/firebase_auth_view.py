from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model
from firebase_admin import auth as firebase_auth
import firebase_admin
from firebase_admin import credentials
from django.conf import settings
import os
import logging
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from .serializers import FirebaseAppleAuthSerializer

logger = logging.getLogger(__name__)

User = get_user_model()

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    try:
        # Use environment variable or settings to get Firebase credentials
        cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
        
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized successfully")
        else:
            logger.warning("Firebase credentials path not found or not set")
    except Exception as e:
        logger.error(f"Firebase initialization error: {e}")

class FirebaseGoogleAuthView(APIView):
    permission_classes = []
    """
    API endpoint for Firebase Google authentication.
    """
    @swagger_auto_schema(
        operation_summary="Firebase Google Authentication",
        operation_description="Authenticates a user using Firebase ID token from Google Authentication.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['id_token'],
            properties={
                'id_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Firebase ID token from Google Authentication'
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
            status.HTTP_400_BAD_REQUEST: "Invalid or missing ID token",
            status.HTTP_401_UNAUTHORIZED: "Firebase authentication failed"
        }
    )
    
    
    
    
    def post(self, request):
        id_token = request.data.get('id_token')
        
        if not id_token:
            return Response(
                {'error': 'ID token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Verify the Firebase token
            decoded_token = firebase_auth.verify_id_token(id_token)
            
            # Extract user info from token
            uid = decoded_token.get('uid')
            email = decoded_token.get('email')
            
            if not email:
                return Response(
                    {'error': 'Email is required for authentication'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get additional user data
            full_name = decoded_token.get('name', '')
            # You might want to extract phone number if available
            phone_number = None
            
            # Check if user exists
            try:
                user = User.objects.get(email__iexact=email)
                
                # Update user info if needed
                if full_name and not user.full_name:
                    user.full_name = full_name
                    user.save()
                
            except User.DoesNotExist:
                # Create a new user
                user = User.objects.create_user(
                    email=email,
                    full_name=full_name or email.split('@')[0],
                    phone_number=phone_number,
                    password=None  # No password for social auth users
                )
                logger.info(f"Created new user via Firebase: {email}")
            
            # Create or get authentication token
            token, created = Token.objects.get_or_create(user=user)
            
            # Get user data to return
            user_data = {
                'id': user.id,
                'email': user.email,
                'full_name': user.full_name,
                'phone_number': user.phone_number,
                # Add any other user fields you need
            }
            
            # Return the response similar to your existing login endpoint
            return Response({
                'key': token.key,
                'user': user_data
            })
            
        except firebase_admin.exceptions.FirebaseError as e:
            logger.error(f"Firebase token verification error: {e}")
            return Response(
                {'error': f'Firebase authentication failed: {str(e)}'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            logger.error(f"Firebase authentication unexpected error: {e}")
            return Response(
                {'error': f'Authentication failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FirebaseAppleAuthView(APIView):
    permission_classes = []
    """
    API endpoint for Firebase Apple authentication.
    """
    @swagger_auto_schema(
        operation_summary="Firebase Apple Authentication",
        operation_description="Authenticates a user using Firebase ID token from Apple Authentication.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['id_token'],
            properties={
                'id_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Firebase ID token from Apple Authentication'
                ),
                'nonce': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Nonce used for Apple authentication (optional)'
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
            status.HTTP_400_BAD_REQUEST: "Invalid or missing ID token",
            status.HTTP_401_UNAUTHORIZED: "Firebase authentication failed"
        }
    )
    
    def post(self, request):
        serializer = FirebaseAppleAuthSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        id_token = serializer.validated_data['id_token']
        nonce = serializer.validated_data.get('nonce')  # Optional nonce for Apple auth
        
        try:
            # Verify the Firebase token
            decoded_token = firebase_auth.verify_id_token(id_token)
            
            # Extract user info from token
            uid = decoded_token.get('uid')
            email = decoded_token.get('email')
            
            # For Apple auth, email might be in a different field or might be None initially
            # Apple provides email in 'firebase.identities' or directly in 'email'
            if not email:
                # Try to get email from firebase identities
                firebase_identities = decoded_token.get('firebase', {}).get('identities', {})
                apple_identities = firebase_identities.get('apple.com', [])
                if apple_identities:
                    email = apple_identities[0]
            
            # If still no email, check if user exists by UID
            if not email:
                # Try to find existing user by UID or create a placeholder
                try:
                    # Since User model doesn't have username field, we'll use a custom field
                    # or create a placeholder email based on UID
                    placeholder_email = f"{uid}@apple.placeholder"
                    user = User.objects.get(email=placeholder_email)
                    logger.info(f"Found existing Apple user with UID: {uid}")
                except User.DoesNotExist:
                    # Create user with UID-based placeholder email
                    user = User.objects.create_user(
                        email=placeholder_email,
                        full_name=decoded_token.get('name', 'Apple User'),
                        password=None
                    )
                    logger.info(f"Created new Apple user with UID: {uid}")
            else:
                # Check if user exists by email
                try:
                    user = User.objects.get(email__iexact=email)
                    
                    # Update user info if needed
                    full_name = decoded_token.get('name', '')
                    if full_name and not user.full_name:
                        user.full_name = full_name
                        user.save()
                        logger.info(f"Updated Apple user profile: {email}")
                    
                except User.DoesNotExist:
                    # Create a new user
                    user = User.objects.create_user(
                        email=email,
                        full_name=decoded_token.get('name', email.split('@')[0]),
                        password=None  # No password for social auth users
                    )
                    logger.info(f"Created new Apple user: {email}")
            
            # Create or get authentication token
            token, created = Token.objects.get_or_create(user=user)
            
            # Get user data to return
            user_data = {
                'id': user.id,
                'email': user.email,
                'full_name': user.full_name,
                'phone_number': user.phone_number,
                'auth_provider': 'apple',
                'is_new_user': created,
                # Add any other user fields you need
            }
            
            # Return the response similar to your existing login endpoint
            return Response({
                'key': token.key,
                'user': user_data,
                'message': 'Apple authentication successful'
            })
            
        except firebase_admin.exceptions.FirebaseError as e:
            logger.error(f"Firebase Apple token verification error: {e}")
            return Response(
                {'error': f'Firebase Apple authentication failed: {str(e)}'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            logger.error(f"Firebase Apple authentication unexpected error: {e}")
            return Response(
                {'error': f'Apple authentication failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )