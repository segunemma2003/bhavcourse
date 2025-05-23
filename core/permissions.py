# Add this custom permission class to your views.py or permissions.py

from rest_framework import permissions
from rest_framework import generics, viewsets, status, permissions
from core.serializers import CourseCurriculumSerializer
from .models import Enrollment

class IsEnrolledOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow enrolled users or admins to access course content.
    """
    
    def has_permission(self, request, view):
        # Allow admin users
        if request.user.is_authenticated and request.user.is_staff:
            return True
        
        # For read operations, check if user is enrolled
        if request.method in permissions.SAFE_METHODS:
            if not request.user.is_authenticated:
                return False
            
            # Get course ID from URL
            course_pk = view.kwargs.get('course_pk')
            if course_pk:
                # Check if user has active enrollment
                return Enrollment.objects.filter(
                    user=request.user,
                    course_id=course_pk,
                    is_active=True
                ).exists()
        
        return False

