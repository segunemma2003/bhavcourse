import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
import os
import logging

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK if not already initialized
if not firebase_admin._apps:
    try:
        # Use environment variable or settings to get your Firebase credentials
        cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
        
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized successfully")
        else:
            logger.warning("Firebase credentials path not found or not set")
    except Exception as e:
        logger.error(f"Firebase initialization error: {e}")

def send_firebase_message(registration_token, title, body, data=None):
    """
    Send notification using Firebase Admin SDK
    
    Args:
        registration_token (str): FCM token
        title (str): Notification title
        body (str): Notification body
        data (dict): Additional data payload
        
    Returns:
        bool: Success status
    """
    try:
        # Validate inputs
        if not registration_token:
            logger.error("No registration token provided")
            return False
            
        if not firebase_admin._apps:
            logger.error("Firebase not initialized")
            return False
        
        # Create message object
        message_obj = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=registration_token,
        )
        
        # Send message
        response = messaging.send(message_obj)
        logger.info(f"Successfully sent message: {response}")
        return True
        
    except messaging.UnregisteredError:
        logger.warning(f"Token is unregistered: {registration_token}")
        # You might want to remove this token from your database
        return False
    except messaging.InvalidTokenError:
        logger.warning(f"Invalid token: {registration_token}")
        # You might want to remove this token from your database
        return False
    except Exception as e:
        logger.error(f"Firebase messaging error: {e}")
        return False

def send_bulk_notifications(tokens, title, body, data=None):
    """
    Send notifications to multiple devices
    
    Args:
        tokens (list): List of FCM tokens
        title (str): Notification title
        body (str): Notification body
        data (dict): Additional data payload
        
    Returns:
        dict: Success and failure counts
    """
    success_count = 0
    failure_count = 0
    
    for token in tokens:
        if send_firebase_message(token, title, body, data):
            success_count += 1
        else:
            failure_count += 1
    
    return {
        'success_count': success_count,
        'failure_count': failure_count,
        'total_sent': success_count + failure_count
    }