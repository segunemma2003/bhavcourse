# core/auth_backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()

class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # Add debug prints
        print(f"EmailBackend.authenticate called with username={username}, kwargs={kwargs}")
        
        # Check if email is provided directly or through username
        email = kwargs.get('email', username)
        if not email:
            print("No email provided")
            return None
            
        try:
            # Find user by email (case-insensitive)
            user = User.objects.get(email__iexact=email)
            print(f"Found user: {user.email}")
            
            # Check password
            if user.check_password(password):
                print("Password check passed")
                return user
            else:
                print("Password check failed")
                return None
        except User.DoesNotExist:
            print(f"No user found with email {email}")
            return None
    
    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None