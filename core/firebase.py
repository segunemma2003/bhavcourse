# core/firebase.py
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
import os

# Initialize Firebase Admin SDK if not already initialized
if not firebase_admin._apps:
    try:
        # Use environment variable or settings to get your Firebase credentials
        cred_path = settings.FIREBASE_CREDENTIALS_PATH
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"Firebase initialization error: {e}")

def send_firebase_message(registration_token, title, message, data=None):
    """
    Send notification using Firebase Admin SDK
    
    Args:
        registration_token (str): FCM token
        title (str): Notification title
        message (str): Notification body
        data (dict): Additional data payload
        
    Returns:
        bool: Success status
    """
    try:
        message_obj = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=message,
            ),
            data=data or {},
            token=registration_token,
        )
        
        response = messaging.send(message_obj)
        return True
    except Exception as e:
        print(f"Firebase messaging error: {e}")
        return False