from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User  # Import your custom User model

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('email', 'full_name', 'phone_number')  # Remove username reference

class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = ('email', 'full_name', 'phone_number', 'is_active', 'is_staff', 'is_superuser')  # Remove username reference

class CustomUserAdmin(UserAdmin):
    # The forms to add and change user instances
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm

    # The fields to be used in displaying the User model.
    list_display = ('email', 'full_name', 'phone_number', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    
    # These override the default UserAdmin fields which assume username exists
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('full_name', 'phone_number', 'date_of_birth')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'phone_number', 'password1', 'password2'),
        }),
    )
    
    search_fields = ('email', 'full_name', 'phone_number')
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions',)

# Register the new UserAdmin
admin.site.register(User, CustomUserAdmin)