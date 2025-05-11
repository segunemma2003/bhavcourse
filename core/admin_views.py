# Add this to core/admin_views.py or include in core/views.py

from rest_framework import generics, viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.db.models import Count, Sum
from django.utils import timezone
from datetime import timedelta, datetime
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from .models import Course, User, Purchase, ContentPage, GeneralSettings
from .serializers import (
    AdminMetricsSerializer, ContentPageSerializer, 
    GeneralSettingsSerializer, CourseListSerializer
)
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models import Count, Q
from .serializers import UserDetailsSerializer
from django.contrib.auth import get_user_model
from .models import Enrollment

User = get_user_model()

class AdminMetricsView(generics.GenericAPIView):
    """
    API endpoint for retrieving admin dashboard metrics.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminMetricsSerializer
    
    @swagger_auto_schema(
        operation_summary="Get admin dashboard metrics",
        operation_description="Retrieves key metrics for the admin dashboard including total courses, students, and revenue",
        manual_parameters=[
            openapi.Parameter(
                'time_period', 
                openapi.IN_QUERY, 
                description="Time period for graph data (week, month, year)", 
                type=openapi.TYPE_STRING,
                default='month'
            ),
        ],
        responses={
            status.HTTP_200_OK: AdminMetricsSerializer,
            status.HTTP_401_UNAUTHORIZED: 'Unauthorized access',
            status.HTTP_403_FORBIDDEN: 'Permission denied',
        }
    )
    def get(self, request):
        # Get time period from query parameters (default to month)
        time_period = request.query_params.get('time_period', 'month')
        
        # Basic metrics
        total_courses = Course.objects.count()
        total_students = User.objects.filter(is_staff=False, is_superuser=False).count()
        total_revenue = Purchase.objects.aggregate(total=Sum('amount'))['total'] or 0
        
        # Prepare data for student registration graph
        now = timezone.now()
        
        # Set the date range based on time_period
        if time_period == 'week':
            start_date = now - timedelta(days=7)
            date_trunc = TruncDate('date_joined')
            date_format = '%Y-%m-%d'
        elif time_period == 'year':
            start_date = now - timedelta(days=365)
            date_trunc = TruncMonth('date_joined')
            date_format = '%Y-%m'
        else:  # Default to month
            start_date = now - timedelta(days=30)
            date_trunc = TruncDate('date_joined')
            date_format = '%Y-%m-%d'
        
        # Query for new registrations
        registrations = User.objects.filter(
            date_joined__gte=start_date,
            is_staff=False,
            is_superuser=False
        ).annotate(
            date=date_trunc
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        # Format for the graph
        registration_data = {
            'labels': [],
            'data': []
        }
        
        # Create a dictionary for quick lookup
        reg_dict = {reg['date'].strftime(date_format): reg['count'] for reg in registrations}
        
        # Fill in all dates in the range
        current_date = start_date
        while current_date <= now:
            date_str = current_date.strftime(date_format)
            registration_data['labels'].append(date_str)
            registration_data['data'].append(reg_dict.get(date_str, 0))
            
            if time_period == 'year':
                current_date += timedelta(days=30)  # Approximate for month
            else:
                current_date += timedelta(days=1)
        
        # Course popularity data
        course_popularity = Course.objects.annotate(
            student_count=Count('enrollments')
        ).order_by('-student_count')[:10]
        
        course_popularity_data = CourseListSerializer(
            course_popularity, 
            many=True, 
            context={'request': request}
        ).data
        
        # Prepare the response
        response_data = {
            'total_courses': total_courses,
            'total_students': total_students,
            'total_revenue': total_revenue,
            'student_registration_data': registration_data,
            'course_popularity': course_popularity_data
        }
        
        serializer = self.get_serializer(data=response_data)
        serializer.is_valid()  # Always valid as we're setting read-only fields
        
        return Response(serializer.data)

class ContentPageViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing privacy policy and terms & conditions.
    """
    queryset = ContentPage.objects.all()
    serializer_class = ContentPageSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_default_content(self, page_type):
        """
        Get default content for a content page type
        """
        if page_type == 'PRIVACY':
            return """
# Privacy Policy

## Introduction
Welcome to our Privacy Policy. This document explains how we collect, use, and protect your personal information.

## Information We Collect
- Personal information such as name, email address, and phone number
- Usage data such as course progress and login times
- Payment information when you make a purchase

## How We Use Your Information
- To provide and maintain our service
- To notify you about changes to our service
- To provide customer support
- To gather analysis or valuable information so that we can improve our service

## Data Security
We implement appropriate security measures to protect your personal information.

## Your Rights
You have the right to access, update, or delete your personal information.

## Changes to This Privacy Policy
We may update our Privacy Policy from time to time. We will notify you of any changes by posting the new Privacy Policy on this page.

## Contact Us
If you have any questions about this Privacy Policy, please contact us.
            """
        elif page_type == 'TERMS':
            return """
# Terms and Conditions

## Introduction
These Terms and Conditions govern your use of our service and website.

## Acceptance of Terms
By accessing or using our service, you agree to be bound by these Terms.

## User Accounts
- You are responsible for maintaining the security of your account
- You are responsible for all activities that occur under your account
- You must notify us immediately of any breach of security or unauthorized use of your account

## Course Content
- All content provided on our platform is for educational purposes only
- You may not reproduce, distribute, or create derivative works from our content
- We reserve the right to modify or discontinue any course without notice

## Payment Terms
- All fees are non-refundable unless stated otherwise
- We reserve the right to change our fees at any time

## Limitation of Liability
We will not be liable for any indirect, incidental, special, or consequential damages.

## Governing Law
These Terms shall be governed and construed in accordance with the laws of [Your Country].

## Changes to Terms
We reserve the right to modify or replace these Terms at any time.

## Contact Us
If you have any questions about these Terms, please contact us.
            """
        else:
            return ""
    
    @swagger_auto_schema(
        operation_summary="Get privacy policy or terms & conditions",
        operation_description="Retrieves the privacy policy or terms & conditions content",
        manual_parameters=[
            openapi.Parameter(
                'page_type', 
                openapi.IN_QUERY, 
                description="Page type (PRIVACY, TERMS)", 
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            status.HTTP_200_OK: ContentPageSerializer,
            status.HTTP_404_NOT_FOUND: 'Content not found',
        }
    )
    def retrieve(self, request, pk=None):
        page_type = request.query_params.get('page_type')
        if not page_type:
            return Response(
                {"error": "page_type query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to get existing content or create one with default content
        try:
            content_page = ContentPage.objects.get(page_type=page_type)
        except ContentPage.DoesNotExist:
            # Only create default content for admins
            if request.user.is_staff:
                content_page = ContentPage.objects.create(
                    page_type=page_type,
                    content=self.get_default_content(page_type)
                )
            else:
                return Response(
                    {"error": f"Content for {page_type} not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        serializer = self.get_serializer(content_page)
        return Response(serializer.data)
    
    
class GeneralSettingsView(generics.RetrieveUpdateAPIView):
    """
    API endpoint for retrieving and updating general settings.
    """
    serializer_class = GeneralSettingsSerializer
    
    def get_object(self):
        # Get the settings object or create a default one if it doesn't exist
        return GeneralSettings.get_settings()
    
    def get_permissions(self):
        """
        Allow anyone to retrieve settings, but only admin users can update.
        """
        if self.request.method in ['PUT', 'PATCH']:
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]
    
    @swagger_auto_schema(
        operation_summary="Get general settings",
        operation_description="Retrieves the general settings for the application",
        responses={
            status.HTTP_200_OK: GeneralSettingsSerializer,
        }
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Update general settings",
        operation_description="Updates the general settings for the application",
        request_body=GeneralSettingsSerializer,
        responses={
            status.HTTP_200_OK: GeneralSettingsSerializer,
            status.HTTP_400_BAD_REQUEST: 'Invalid data',
            status.HTTP_401_UNAUTHORIZED: 'Unauthorized access',
            status.HTTP_403_FORBIDDEN: 'Permission denied',
        }
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Partially update general settings",
        operation_description="Partially updates the general settings for the application",
        request_body=GeneralSettingsSerializer,
        responses={
            status.HTTP_200_OK: GeneralSettingsSerializer,
            status.HTTP_400_BAD_REQUEST: 'Invalid data',
            status.HTTP_401_UNAUTHORIZED: 'Unauthorized access',
            status.HTTP_403_FORBIDDEN: 'Permission denied',
        }
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

# Public version of ContentPageView for retrieving content
class PublicContentPageView(generics.RetrieveAPIView):
    """
    API endpoint for retrieving privacy policy and terms & conditions (public).
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = ContentPageSerializer
    
    def get_default_content(self, page_type):
        """
        Get default content for a content page type
        """
        if page_type == 'PRIVACY':
            return """
# Privacy Policy

## Introduction
Welcome to our Privacy Policy. This document explains how we collect, use, and protect your personal information.

## Information We Collect
- Personal information such as name, email address, and phone number
- Usage data such as course progress and login times
- Payment information when you make a purchase

## How We Use Your Information
- To provide and maintain our service
- To notify you about changes to our service
- To provide customer support
- To gather analysis or valuable information so that we can improve our service

## Data Security
We implement appropriate security measures to protect your personal information.

## Your Rights
You have the right to access, update, or delete your personal information.

## Changes to This Privacy Policy
We may update our Privacy Policy from time to time. We will notify you of any changes by posting the new Privacy Policy on this page.

## Contact Us
If you have any questions about this Privacy Policy, please contact us.
            """
        elif page_type == 'TERMS':
            return """
# Terms and Conditions

## Introduction
These Terms and Conditions govern your use of our service and website.

## Acceptance of Terms
By accessing or using our service, you agree to be bound by these Terms.

## User Accounts
- You are responsible for maintaining the security of your account
- You are responsible for all activities that occur under your account
- You must notify us immediately of any breach of security or unauthorized use of your account

## Course Content
- All content provided on our platform is for educational purposes only
- You may not reproduce, distribute, or create derivative works from our content
- We reserve the right to modify or discontinue any course without notice

## Payment Terms
- All fees are non-refundable unless stated otherwise
- We reserve the right to change our fees at any time

## Limitation of Liability
We will not be liable for any indirect, incidental, special, or consequential damages.

## Governing Law
These Terms shall be governed and construed in accordance with the laws of [Your Country].

## Changes to Terms
We reserve the right to modify or replace these Terms at any time.

## Contact Us
If you have any questions about these Terms, please contact us.
            """
        else:
            return ""
    
    @swagger_auto_schema(
        operation_summary="Get privacy policy or terms & conditions",
        operation_description="Retrieves the privacy policy or terms & conditions content (public access)",
        manual_parameters=[
            openapi.Parameter(
                'page_type', 
                openapi.IN_QUERY, 
                description="Page type (PRIVACY, TERMS)", 
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            status.HTTP_200_OK: ContentPageSerializer,
            status.HTTP_404_NOT_FOUND: 'Content not found',
        }
    )
    def get(self, request):
        page_type = request.query_params.get('page_type')
        if not page_type:
            return Response(
                {"error": "page_type query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            content_page = ContentPage.objects.get(page_type=page_type)
        except ContentPage.DoesNotExist:
            # Create content page with default content if it doesn't exist
            content_page = ContentPage.objects.create(
                page_type=page_type,
                content=self.get_default_content(page_type)
            )
        
        serializer = self.get_serializer(content_page)
        return Response(serializer.data)
            
class UserListView(generics.ListAPIView):
    """
    API endpoint for retrieving all users.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = UserDetailsSerializer
    queryset = User.objects.all()
    
    @swagger_auto_schema(
        operation_summary="Get all users",
        operation_description="Retrieves a list of all users registered in the system",
        manual_parameters=[
            openapi.Parameter(
                'search', 
                openapi.IN_QUERY, 
                description="Search users by email, full name, or phone number", 
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'is_staff', 
                openapi.IN_QUERY, 
                description="Filter by staff status (true/false)", 
                type=openapi.TYPE_BOOLEAN
            ),
            openapi.Parameter(
                'is_active', 
                openapi.IN_QUERY, 
                description="Filter by active status (true/false)", 
                type=openapi.TYPE_BOOLEAN
            ),
        ],
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="List of users",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'email': openapi.Schema(type=openapi.TYPE_STRING),
                            'full_name': openapi.Schema(type=openapi.TYPE_STRING),
                            'phone_number': openapi.Schema(type=openapi.TYPE_STRING),
                            'date_of_birth': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
                        }
                    )
                )
            ),
        }
    )
    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Apply filters based on query parameters
        search = request.query_params.get('search', None)
        is_staff = request.query_params.get('is_staff', None)
        is_active = request.query_params.get('is_active', None)
        
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search) | 
                Q(full_name__icontains=search) | 
                Q(phone_number__icontains=search)
            )
            
        if is_staff is not None:
            is_staff_bool = is_staff.lower() == 'true'
            queryset = queryset.filter(is_staff=is_staff_bool)
            
        if is_active is not None:
            is_active_bool = is_active.lower() == 'true'
            queryset = queryset.filter(is_active=is_active_bool)
        
        # Order by most recent first
        queryset = queryset.order_by('-date_joined')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class EnrolledStudentsListView(generics.ListAPIView):
    """
    API endpoint for retrieving all enrolled students.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = UserDetailsSerializer
    
    @swagger_auto_schema(
        operation_summary="Get all enrolled students",
        operation_description="Retrieves a list of all students who have enrolled in at least one course",
        manual_parameters=[
            openapi.Parameter(
                'search', 
                openapi.IN_QUERY, 
                description="Search students by email, full name, or phone number", 
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'course_id', 
                openapi.IN_QUERY, 
                description="Filter by specific course ID", 
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'min_courses', 
                openapi.IN_QUERY, 
                description="Filter by minimum number of enrolled courses", 
                type=openapi.TYPE_INTEGER
            ),
        ],
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="List of enrolled students",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'email': openapi.Schema(type=openapi.TYPE_STRING),
                            'full_name': openapi.Schema(type=openapi.TYPE_STRING),
                            'phone_number': openapi.Schema(type=openapi.TYPE_STRING),
                            'date_of_birth': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
                            'enrolled_courses_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                        }
                    )
                )
            ),
        }
    )
    def get(self, request, *args, **kwargs):
        # Get all students (non-staff users) who have enrolled in at least one course
        # Annotate with the count of enrolled courses
        queryset = User.objects.filter(
            is_staff=False, 
            is_superuser=False,
            enrollments__isnull=False
        ).distinct().annotate(
            enrolled_courses_count=Count('enrollments')
        )
        
        # Apply filters based on query parameters
        search = request.query_params.get('search', None)
        course_id = request.query_params.get('course_id', None)
        min_courses = request.query_params.get('min_courses', None)
        
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search) | 
                Q(full_name__icontains=search) | 
                Q(phone_number__icontains=search)
            )
            
        if course_id:
            queryset = queryset.filter(enrollments__course_id=course_id)
            
        if min_courses:
            try:
                min_courses_int = int(min_courses)
                queryset = queryset.filter(enrolled_courses_count__gte=min_courses_int)
            except ValueError:
                pass
        
        # Order by most active students first (most enrolled courses)
        queryset = queryset.order_by('-enrolled_courses_count', 'full_name')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            # Add the enrolled_courses_count to each user in the response
            for user_data, user_obj in zip(serializer.data, page):
                user_data['enrolled_courses_count'] = user_obj.enrolled_courses_count
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        # Add the enrolled_courses_count to each user in the response
        for user_data, user_obj in zip(serializer.data, queryset):
            user_data['enrolled_courses_count'] = user_obj.enrolled_courses_count
        
        return Response(serializer.data)


class ContentPageMixin:
    """
    Mixin to provide default content for content pages
    """
    def get_default_content(self, page_type):
        """
        Get default content for a content page type
        """
        if page_type == 'PRIVACY':
            return """
# Privacy Policy

## Introduction
Welcome to our Privacy Policy. This document explains how we collect, use, and protect your personal information.

## Information We Collect
- Personal information such as name, email address, and phone number
- Usage data such as course progress and login times
- Payment information when you make a purchase

## How We Use Your Information
- To provide and maintain our service
- To notify you about changes to our service
- To provide customer support
- To gather analysis or valuable information so that we can improve our service

## Data Security
We implement appropriate security measures to protect your personal information.

## Your Rights
You have the right to access, update, or delete your personal information.

## Changes to This Privacy Policy
We may update our Privacy Policy from time to time. We will notify you of any changes by posting the new Privacy Policy on this page.

## Contact Us
If you have any questions about this Privacy Policy, please contact us.
            """
        elif page_type == 'TERMS':
            return """
# Terms and Conditions

## Introduction
These Terms and Conditions govern your use of our service and website.

## Acceptance of Terms
By accessing or using our service, you agree to be bound by these Terms.

## User Accounts
- You are responsible for maintaining the security of your account
- You are responsible for all activities that occur under your account
- You must notify us immediately of any breach of security or unauthorized use of your account

## Course Content
- All content provided on our platform is for educational purposes only
- You may not reproduce, distribute, or create derivative works from our content
- We reserve the right to modify or discontinue any course without notice

## Payment Terms
- All fees are non-refundable unless stated otherwise
- We reserve the right to change our fees at any time

## Limitation of Liability
We will not be liable for any indirect, incidental, special, or consequential damages.

## Governing Law
These Terms shall be governed and construed in accordance with the laws of [Your Country].

## Changes to Terms
We reserve the right to modify or replace these Terms at any time.

## Contact Us
If you have any questions about these Terms, please contact us.
            """
        else:
            return ""

    def get_or_create_content_page(self, page_type, create_if_missing=True):
        """
        Get content page or create with default content if it doesn't exist
        """
        from .models import ContentPage
        
        try:
            content_page = ContentPage.objects.get(page_type=page_type)
            return content_page, False
        except ContentPage.DoesNotExist:
            if create_if_missing:
                content_page = ContentPage.objects.create(
                    page_type=page_type,
                    content=self.get_default_content(page_type)
                )
                return content_page, True
            return None, False

# Then update your view classes to use this mixin:

class ContentPageViewSet(ContentPageMixin, viewsets.ModelViewSet):
    """
    API endpoints for managing privacy policy and terms & conditions.
    """
    queryset = ContentPage.objects.all()
    serializer_class = ContentPageSerializer
    permission_classes = [permissions.IsAdminUser]
    
    @swagger_auto_schema(
        operation_summary="Get privacy policy or terms & conditions",
        operation_description="Retrieves the privacy policy or terms & conditions content",
        manual_parameters=[
            openapi.Parameter(
                'page_type', 
                openapi.IN_QUERY, 
                description="Page type (PRIVACY, TERMS)", 
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            status.HTTP_200_OK: ContentPageSerializer,
            status.HTTP_404_NOT_FOUND: 'Content not found',
        }
    )
    def retrieve(self, request, pk=None):
        page_type = request.query_params.get('page_type')
        if not page_type:
            return Response(
                {"error": "page_type query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to get existing content or create one with default content if user is admin
        content_page, created = self.get_or_create_content_page(
            page_type, 
            create_if_missing=request.user.is_staff
        )
        
        if not content_page:
            return Response(
                {"error": f"Content for {page_type} not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.get_serializer(content_page)
        return Response(serializer.data)

class PublicContentPageView(ContentPageMixin, generics.RetrieveAPIView):
    """
    API endpoint for retrieving privacy policy and terms & conditions (public).
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = ContentPageSerializer
    
    @swagger_auto_schema(
        operation_summary="Get privacy policy or terms & conditions",
        operation_description="Retrieves the privacy policy or terms & conditions content (public access)",
        manual_parameters=[
            openapi.Parameter(
                'page_type', 
                openapi.IN_QUERY, 
                description="Page type (PRIVACY, TERMS)", 
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            status.HTTP_200_OK: ContentPageSerializer,
            status.HTTP_404_NOT_FOUND: 'Content not found',
        }
    )
    def get(self, request):
        page_type = request.query_params.get('page_type')
        if not page_type:
            return Response(
                {"error": "page_type query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to get existing content or create one with default content
        content_page, created = self.get_or_create_content_page(page_type)
        
        serializer = self.get_serializer(content_page)
        return Response(serializer.data)