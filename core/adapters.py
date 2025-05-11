# core/adapters.py
from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

class CustomAccountAdapter(DefaultAccountAdapter):
    def populate_username(self, request, user):
        # Don't populate username at all
        return user
    
    def save_user(self, request, user, form, commit=True):
        """
        Override to customize user saving behavior
        """
        # Get data from the form
        data = form.cleaned_data
        email = data.get('email')
        user.email = email
        
        # Set additional fields
        user.full_name = data.get('full_name', '')
        user.phone_number = data.get('phone_number', '')
        
        # Skip username completely
        
        # Save password if available
        if 'password1' in data:
            user.set_password(data["password1"])
        else:
            user.set_unusable_password()
            
        if commit:
            user.save()
            
        return user

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        # Set full_name from the social account data
        if 'name' in data:
            user.full_name = data.get('name')
        # Don't set username
        return user