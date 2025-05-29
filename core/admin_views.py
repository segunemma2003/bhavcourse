
import hashlib
from rest_framework import generics, viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.db.models import Count, Sum
from django.utils import timezone
from datetime import timedelta, datetime
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from .models import Course, CoursePlanType, Notification, PaymentCard, PaymentOrder, User, Purchase, ContentPage, GeneralSettings
from .serializers import (
    AdminMetricsSerializer, ContentPageSerializer, 
    GeneralSettingsSerializer, CourseListSerializer
)
from django.core.cache import cache
from rest_framework import serializers
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models import Count, Q
from .serializers import UserDetailsSerializer
from django.contrib.auth import get_user_model
from .models import Enrollment
from rest_framework.permissions import IsAdminUser
import uuid
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)
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
        
        # serializer = self.get_serializer(data=response_data)
        # serializer.is_valid()  # Always valid as we're setting read-only fields
        
        return Response(response_data, status=status.HTTP_200_OK)

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
    
    
class AdminAddStudentToPlanView(generics.CreateAPIView):
    """
    Admin API endpoint for manually adding a student to a subscription plan without payment verification.
    This simulates the same flow as course purchase but bypasses payment processing.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    class InputSerializer(serializers.Serializer):
        user_id = serializers.IntegerField()
        course_id = serializers.IntegerField()
        plan_type = serializers.ChoiceField(choices=CoursePlanType.choices)
        amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
        payment_card_id = serializers.IntegerField(required=False, allow_null=True)
        notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
        
        class Meta:
            ref_name = "AdminAddStudentInputSerializer"
        
        def validate_user_id(self, value):
            try:
                User.objects.get(pk=value)
                return value
            except User.DoesNotExist:
                raise serializers.ValidationError("User does not exist")
        
        def validate_course_id(self, value):
            try:
                Course.objects.get(pk=value)
                return value
            except Course.DoesNotExist:
                raise serializers.ValidationError("Course does not exist")
        
        def validate_payment_card_id(self, value):
            if value is None:
                return None
            try:
                PaymentCard.objects.get(pk=value)
                return value
            except PaymentCard.DoesNotExist:
                raise serializers.ValidationError("Payment card does not exist")
    
    def get_serializer_class(self):
        return self.InputSerializer
    
    @swagger_auto_schema(
        operation_summary="Admin: Add student to subscription plan",
        operation_description="""
        Admin-only endpoint to manually add a student to a course subscription plan without payment verification.
        
        This endpoint simulates the complete purchase flow:
        1. Creates a Purchase record with COMPLETED status
        2. Creates/updates Enrollment for the course with selected plan
        3. Creates a mock PaymentOrder record
        4. Creates notifications for purchase and enrollment
        5. All without requiring actual payment processing
        
        **Admin Use Cases:**
        - Manually enroll students for promotional purposes
        - Handle offline payments
        - Resolve payment issues
        - Grant free access to courses
        """,
        request_body=InputSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response(
                description="Student added to plan successfully",
                examples={
                    "application/json": {
                        "success": True,
                        "data": {
                            "message": "Successfully enrolled user@example.com in Course Title (Lifetime)",
                            "purchase": {
                                "id": 123,
                                "transaction_id": "ADMIN_A1B2C3D4E5F6",
                                "amount": "299.00",
                                "payment_status": "COMPLETED"
                            },
                            "enrollment": {
                                "id": 456,
                                "plan_type": "LIFETIME",
                                "plan_name": "Lifetime",
                                "expiry_date": None,
                                "is_active": True
                            },
                            "payment_order_id": 789,
                            "admin_action": True,
                            "added_by": "admin@example.com"
                        }
                    }
                },
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'message': openapi.Schema(type=openapi.TYPE_STRING),
                                'purchase': openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                        'transaction_id': openapi.Schema(type=openapi.TYPE_STRING),
                                        'amount': openapi.Schema(type=openapi.TYPE_STRING),
                                        'payment_status': openapi.Schema(type=openapi.TYPE_STRING)
                                    }
                                ),
                                'enrollment': openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                        'plan_type': openapi.Schema(type=openapi.TYPE_STRING),
                                        'plan_name': openapi.Schema(type=openapi.TYPE_STRING),
                                        'expiry_date': openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),
                                        'is_active': openapi.Schema(type=openapi.TYPE_BOOLEAN)
                                    }
                                ),
                                'payment_order_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'admin_action': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                'added_by': openapi.Schema(type=openapi.TYPE_STRING)
                            }
                        )
                    }
                )
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Invalid request data",
                examples={
                    "application/json": {
                        "error": "Invalid request data",
                        "details": "User does not exist"
                    }
                }
            ),
            status.HTTP_403_FORBIDDEN: openapi.Response(
                description="Admin access required",
                examples={
                    "application/json": {
                        "detail": "You do not have permission to perform this action."
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Extract validated data
        user_id = serializer.validated_data['user_id']
        course_id = serializer.validated_data['course_id']
        plan_type = serializer.validated_data['plan_type']
        payment_card_id = serializer.validated_data.get('payment_card_id')
        notes = serializer.validated_data.get('notes', '')
        
        try:
            # Get objects
            user = User.objects.get(pk=user_id)
            course = Course.objects.get(pk=course_id)
            
            # Get payment card if provided
            payment_card = None
            if payment_card_id:
                try:
                    payment_card = PaymentCard.objects.get(pk=payment_card_id)
                    # Verify payment card belongs to user if provided
                    if payment_card.user != user:
                        return Response(
                            {'error': 'Payment card does not belong to the specified user'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                except PaymentCard.DoesNotExist:
                    return Response(
                        {'error': 'Payment card not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            # Calculate amount based on plan type if not provided
            amount_paid = serializer.validated_data.get('amount_paid')
            if not amount_paid:
                if plan_type == CoursePlanType.ONE_MONTH:
                    amount_paid = course.price_one_month
                elif plan_type == CoursePlanType.THREE_MONTHS:
                    amount_paid = course.price_three_months
                elif plan_type == CoursePlanType.LIFETIME:
                    amount_paid = course.price_lifetime
                else:
                    amount_paid = Decimal('0.00')
            
            with transaction.atomic():
                result = self._process_admin_enrollment(
                    admin_user=request.user,
                    user=user,
                    course=course,
                    plan_type=plan_type,
                    amount_paid=amount_paid,
                    payment_card=payment_card,
                    notes=notes
                )
            
            # Clear user's enrollment cache since we added new enrollment
            self._clear_user_cache(user.id)
            
            # Prepare response data
            response_data = {
                'message': result['message'],
                'purchase': {
                    'id': result['purchase'].id,
                    'transaction_id': result['purchase'].transaction_id,
                    'amount': result['purchase'].amount,
                    'payment_status': result['purchase'].payment_status
                },
                'enrollment': {
                    'id': result['enrollment'].id,
                    'plan_type': result['enrollment'].plan_type,
                    'plan_name': result['enrollment'].get_plan_type_display(),
                    'expiry_date': result['enrollment'].expiry_date,
                    'is_active': result['enrollment'].is_active
                },
                'payment_order_id': result['payment_order'].id,
                'admin_action': True,
                'added_by': request.user.email
            }
            
            return Response({"success": True, "data": response_data}, status=status.HTTP_201_CREATED)
            
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Course.DoesNotExist:
            return Response(
                {'error': 'Course not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Admin enrollment failed: {str(e)}")
            return Response(
                {'error': 'Enrollment failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def _process_admin_enrollment(self, admin_user, user, course, plan_type, amount_paid, payment_card=None, notes=''):
        """
        Process admin enrollment - simulates the same flow as course purchase but without payment verification
        """
        # Generate mock transaction ID
        transaction_id = f"ADMIN_{uuid.uuid4().hex[:12].upper()}"
        
        # Generate mock Razorpay IDs
        mock_order_id = f"order_admin_{uuid.uuid4().hex[:10]}"
        mock_payment_id = f"pay_admin_{uuid.uuid4().hex[:10]}"
        
        # 1. Create or update PaymentOrder (mock)
        payment_order, created = PaymentOrder.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                'amount': amount_paid,
                'razorpay_order_id': mock_order_id,
                'razorpay_payment_id': mock_payment_id,
                'razorpay_signature': f"admin_signature_{uuid.uuid4().hex[:16]}",
                'status': 'PAID'
            }
        )
        
        if not created:
            # Update existing order
            payment_order.razorpay_payment_id = mock_payment_id
            payment_order.razorpay_signature = f"admin_signature_{uuid.uuid4().hex[:16]}"
            payment_order.status = 'PAID'
            payment_order.save()
        
        # 2. Create Purchase record
        purchase = Purchase.objects.create(
            user=user,
            course=course,
            plan_type=plan_type,
            amount=amount_paid,
            transaction_id=transaction_id,
            razorpay_order_id=mock_order_id,
            razorpay_payment_id=mock_payment_id,
            payment_status='COMPLETED',
            payment_card=payment_card
        )
        
        # 3. Create or update Enrollment
        enrollment, enrollment_created = Enrollment.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                'plan_type': plan_type,
                'amount_paid': amount_paid,
                'is_active': True
            }
        )
        
        if not enrollment_created:
            # Update existing enrollment
            enrollment.plan_type = plan_type
            enrollment.amount_paid = amount_paid
            enrollment.is_active = True
            enrollment.save()
        
        # Calculate expiry date
        if plan_type == CoursePlanType.ONE_MONTH:
            enrollment.expiry_date = timezone.now() + timezone.timedelta(days=30)
        elif plan_type == CoursePlanType.THREE_MONTHS:
            enrollment.expiry_date = timezone.now() + timezone.timedelta(days=90)
        elif plan_type == CoursePlanType.LIFETIME:
            enrollment.expiry_date = None  # No expiry for lifetime
        
        enrollment.save()
        
        # 4. Create Notifications
        # Purchase notification
        Notification.objects.create(
            user=user,
            title="Course Access Granted",
            message=f"You have been enrolled in '{course.title}' ({enrollment.get_plan_type_display()} plan) by admin.",
            notification_type='COURSE'
        )
        
        # Enrollment notification
        Notification.objects.create(
            user=user,
            title="Enrollment Successful",
            message=f"Your enrollment in '{course.title}' is now active. Enjoy learning!",
            notification_type='COURSE'
        )
        
        # Admin notification (optional)
        admin_notes = f"Admin enrollment by {admin_user.email}. Notes: {notes}" if notes else f"Admin enrollment by {admin_user.email}"
        Notification.objects.create(
            user=admin_user,
            title="Student Enrolled",
            message=f"Successfully enrolled {user.email} in '{course.title}' ({enrollment.get_plan_type_display()}). {admin_notes}",
            notification_type='SYSTEM'
        )
        
        # 5. Send push notification (if FCM device exists)
        try:
            from .tasks import send_push_notification
            send_push_notification.delay(
                user.id,
                "Course Access Granted",
                f"You now have access to '{course.title}' - {enrollment.get_plan_type_display()} plan"
            )
        except Exception as e:
            logger.warning(f"Failed to send push notification: {e}")
        
        return {
            'message': f"Successfully enrolled {user.email} in {course.title} ({enrollment.get_plan_type_display()})",
            'purchase': purchase,
            'enrollment': enrollment,
            'payment_order': payment_order
        }
    
    def _clear_user_cache(self, user_id):
        """Clear enrollment cache for the enrolled user"""
        try:
            # Clear common cache patterns
            for page in range(1, 6):  # Clear first 5 pages
                for page_size in [10, 20, 50]:
                    key_string = f"enrollments_{user_id}_{page}_{page_size}"
                    cache_key = hashlib.md5(key_string.encode()).hexdigest()
                    cache.delete(cache_key)
        except Exception:
            pass
        
class AdminRemoveStudentFromPlanView(generics.DestroyAPIView):
    """
    Admin API endpoint for removing a student from a course subscription plan.
    This deactivates enrollment and updates related records.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    class InputSerializer(serializers.Serializer):
        user_id = serializers.IntegerField()
        course_id = serializers.IntegerField()
        reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
        refund_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
        
        class Meta:
            ref_name = "AdminRemoveStudentInputSerializer"
        
        def validate_user_id(self, value):
            try:
                User.objects.get(pk=value)
                return value
            except User.DoesNotExist:
                raise serializers.ValidationError("User does not exist")
        
        def validate_course_id(self, value):
            try:
                Course.objects.get(pk=value)
                return value
            except Course.DoesNotExist:
                raise serializers.ValidationError("Course does not exist")
    
    def get_serializer_class(self):
        return self.InputSerializer
    
    @swagger_auto_schema(
        operation_summary="Admin: Remove student from subscription plan",
        operation_description="""
        Admin-only endpoint to remove a student from a course subscription plan.
        
        This endpoint:
        1. Deactivates the user's enrollment for the specified course
        2. Updates purchase status to REFUNDED if refund_amount is provided
        3. Creates notifications for user and admin
        4. Logs the action for audit trail
        5. Clears relevant caches
        
        **Admin Use Cases:**
        - Handle refund requests
        - Remove access due to policy violations
        - Resolve billing issues
        - Cancel enrollments upon request
        """,
        request_body=InputSerializer,
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Student removed from plan successfully",
                examples={
                    "application/json": {
                        "success": True,
                        "data": {
                            "message": "Successfully removed user@example.com from Course Title",
                            "enrollment_id": 456,
                            "deactivated_at": "2025-01-20T10:30:00Z",
                            "refund_processed": True,
                            "refund_amount": "99.00",
                            "admin_action": True,
                            "removed_by": "admin@example.com",
                            "reason": "User requested refund"
                        }
                    }
                },
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'message': openapi.Schema(type=openapi.TYPE_STRING),
                                'enrollment_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'deactivated_at': openapi.Schema(type=openapi.TYPE_STRING),
                                'refund_processed': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                'refund_amount': openapi.Schema(type=openapi.TYPE_STRING),
                                'admin_action': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                'removed_by': openapi.Schema(type=openapi.TYPE_STRING),
                                'reason': openapi.Schema(type=openapi.TYPE_STRING)
                            }
                        )
                    }
                )
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Invalid request data",
                examples={
                    "application/json": {
                        "error": "Invalid request data",
                        "details": "User does not exist"
                    }
                }
            ),
            status.HTTP_404_NOT_FOUND: openapi.Response(
                description="Enrollment not found",
                examples={
                    "application/json": {
                        "error": "No active enrollment found for this user and course"
                    }
                }
            ),
            status.HTTP_403_FORBIDDEN: openapi.Response(
                description="Admin access required",
                examples={
                    "application/json": {
                        "detail": "You do not have permission to perform this action."
                    }
                }
            )
        }
    )
    def delete(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Extract validated data
        user_id = serializer.validated_data['user_id']
        course_id = serializer.validated_data['course_id']
        reason = serializer.validated_data.get('reason', '')
        refund_amount = serializer.validated_data.get('refund_amount')
        
        try:
            # Get objects
            user = User.objects.get(pk=user_id)
            course = Course.objects.get(pk=course_id)
            
            # Find the enrollment
            try:
                enrollment = Enrollment.objects.get(user=user, course=course, is_active=True)
            except Enrollment.DoesNotExist:
                return Response(
                    {'error': 'No active enrollment found for this user and course'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            with transaction.atomic():
                result = self._process_admin_removal(
                    admin_user=request.user,
                    user=user,
                    course=course,
                    enrollment=enrollment,
                    reason=reason,
                    refund_amount=refund_amount
                )
            
            # Clear user's enrollment cache
            self._clear_user_cache(user.id)
            
            # Prepare response data
            response_data = {
                'message': result['message'],
                'enrollment_id': enrollment.id,
                'deactivated_at': timezone.now().isoformat(),
                'refund_processed': refund_amount is not None,
                'refund_amount': str(refund_amount) if refund_amount else None,
                'admin_action': True,
                'removed_by': request.user.email,
                'reason': reason
            }
            
            return Response({"success": True, "data": response_data}, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Course.DoesNotExist:
            return Response(
                {'error': 'Course not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Admin removal failed: {str(e)}")
            return Response(
                {'error': 'Removal failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def _process_admin_removal(self, admin_user, user, course, enrollment, reason='', refund_amount=None):
        """
        Process admin removal - deactivates enrollment and updates related records
        """
        # 1. Deactivate the enrollment
        enrollment.is_active = False
        enrollment.save()
        
        # 2. Update purchase records if refund is processed
        refund_processed = False
        if refund_amount is not None:
            # Find related purchase records
            purchases = Purchase.objects.filter(
                user=user,
                course=course,
                payment_status='COMPLETED'
            )
            
            for purchase in purchases:
                purchase.payment_status = 'REFUNDED'
                purchase.save()
                refund_processed = True
        
        # 3. Update payment orders if they exist
        payment_orders = PaymentOrder.objects.filter(
            user=user,
            course=course,
            status='PAID'
        )
        
        for payment_order in payment_orders:
            if refund_amount is not None:
                payment_order.status = 'REFUNDED'
            else:
                payment_order.status = 'CANCELLED'
            payment_order.save()
        
        # 4. Create Notifications
        # User notification
        refund_message = f" A refund of ${refund_amount} has been processed." if refund_amount else ""
        reason_message = f" Reason: {reason}" if reason else ""
        
        Notification.objects.create(
            user=user,
            title="Course Access Removed",
            message=f"Your access to '{course.title}' has been removed by admin.{refund_message}{reason_message}",
            notification_type='COURSE'
        )
        
        # Admin notification
        Notification.objects.create(
            user=admin_user,
            title="Student Removed from Course",
            message=f"Successfully removed {user.email} from '{course.title}'. Refund: ${refund_amount or 'N/A'}. Reason: {reason or 'Not specified'}",
            notification_type='SYSTEM'
        )
        
        # 5. Send push notification (if FCM device exists)
        try:
            from .tasks import send_push_notification
            send_push_notification.delay(
                user.id,
                "Course Access Removed",
                f"Your access to '{course.title}' has been removed.{refund_message}"
            )
        except Exception as e:
            logger.warning(f"Failed to send push notification: {e}")
        
        return {
            'message': f"Successfully removed {user.email} from {course.title}",
            'refund_processed': refund_processed
        }
    
    def _clear_user_cache(self, user_id):
        """Clear enrollment cache for the user"""
        try:
            # Clear common cache patterns
            for page in range(1, 6):  # Clear first 5 pages
                for page_size in [10, 20, 50]:
                    key_string = f"enrollments_{user_id}_{page}_{page_size}"
                    cache_key = hashlib.md5(key_string.encode()).hexdigest()
                    cache.delete(cache_key)
        except Exception:
            pass  # Don't break functionality if cache clearing fails

# ADD BULK OPERATIONS API
# =======================

class AdminBulkEnrollmentOperationsView(generics.CreateAPIView):
    """
    Admin API for bulk enrollment operations (add/remove multiple students)
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    class InputSerializer(serializers.Serializer):
        operation = serializers.ChoiceField(choices=['add', 'remove'])
        enrollments = serializers.ListField(
            child=serializers.DictField(),
            min_length=1,
            max_length=100  # Limit to prevent abuse
        )
        
        class Meta:
            ref_name = "AdminBulkEnrollmentInputSerializer"
        
        def validate_enrollments(self, value):
            """Validate each enrollment entry"""
            for enrollment in value:
                if 'user_id' not in enrollment or 'course_id' not in enrollment:
                    raise serializers.ValidationError("Each enrollment must have user_id and course_id")
                
                # For add operations, plan_type is required
                if self.initial_data.get('operation') == 'add' and 'plan_type' not in enrollment:
                    raise serializers.ValidationError("plan_type is required for add operations")
            
            return value
    
    def get_serializer_class(self):
        return self.InputSerializer
    
    @swagger_auto_schema(
        operation_summary="Admin: Bulk enrollment operations",
        operation_description="""
        Admin-only endpoint for bulk enrollment operations.
        
        **Add Operation:**
        - Adds multiple students to courses
        - Each entry needs: user_id, course_id, plan_type
        - Optional: amount_paid, notes
        
        **Remove Operation:**
        - Removes multiple students from courses
        - Each entry needs: user_id, course_id
        - Optional: reason, refund_amount
        """,
        request_body=InputSerializer,
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Bulk operation completed",
                examples={
                    "application/json": {
                        "success": True,
                        "data": {
                            "operation": "add",
                            "total_processed": 3,
                            "successful": 2,
                            "failed": 1,
                            "results": [
                                {
                                    "index": 0,
                                    "status": "success",
                                    "message": "Added user1@example.com to Course Title",
                                    "data": {
                                        "enrollment_id": 123,
                                        "user_id": 1,
                                        "course_id": 10
                                    }
                                },
                                {
                                    "index": 1,
                                    "status": "success", 
                                    "message": "Added user2@example.com to Course Title",
                                    "data": {
                                        "enrollment_id": 124,
                                        "user_id": 2,
                                        "course_id": 10
                                    }
                                },
                                {
                                    "index": 2,
                                    "status": "error",
                                    "message": "User does not exist",
                                    "data": {
                                        "user_id": 999,
                                        "course_id": 10
                                    }
                                }
                            ]
                        }
                    }
                },
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'operation': openapi.Schema(type=openapi.TYPE_STRING),
                                'total_processed': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'successful': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'failed': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'results': openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'index': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'status': openapi.Schema(type=openapi.TYPE_STRING),
                                            'message': openapi.Schema(type=openapi.TYPE_STRING),
                                            'data': openapi.Schema(type=openapi.TYPE_OBJECT)
                                        }
                                    )
                                )
                            }
                        )
                    }
                )
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Invalid request data",
                examples={
                    "application/json": {
                        "error": "Invalid operation type",
                        "details": "Operation must be 'add' or 'remove'"
                    }
                }
            ),
            status.HTTP_403_FORBIDDEN: openapi.Response(
                description="Admin access required",
                examples={
                    "application/json": {
                        "detail": "You do not have permission to perform this action."
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        operation = serializer.validated_data['operation']
        enrollments = serializer.validated_data['enrollments']
        
        results = []
        successful = 0
        failed = 0
        
        for idx, enrollment_data in enumerate(enrollments):
            try:
                if operation == 'add':
                    result = self._bulk_add_student(request.user, enrollment_data)
                else:  # remove
                    result = self._bulk_remove_student(request.user, enrollment_data)
                
                results.append({
                    'index': idx,
                    'status': 'success',
                    'message': result['message'],
                    'data': result
                })
                successful += 1
                
            except Exception as e:
                results.append({
                    'index': idx,
                    'status': 'error',
                    'message': str(e),
                    'data': enrollment_data
                })
                failed += 1
        
        return Response({
            "success": True,
            "data": {
                'operation': operation,
                'total_processed': len(enrollments),
                'successful': successful,
                'failed': failed,
                'results': results
            }
        }, status=status.HTTP_200_OK)
    
    def _bulk_add_student(self, admin_user, data):
        """Add single student in bulk operation"""
        user = User.objects.get(pk=data['user_id'])
        course = Course.objects.get(pk=data['course_id'])
        plan_type = data['plan_type']
        amount_paid = data.get('amount_paid')
        notes = data.get('notes', '')
        
        # Use the same logic as AdminAddStudentToPlanView
        if not amount_paid:
            if plan_type == CoursePlanType.ONE_MONTH:
                amount_paid = course.price_one_month
            elif plan_type == CoursePlanType.THREE_MONTHS:
                amount_paid = course.price_three_months
            elif plan_type == CoursePlanType.LIFETIME:
                amount_paid = course.price_lifetime
            else:
                amount_paid = Decimal('0.00')
        
        # Process enrollment (simplified version)
        enrollment, created = Enrollment.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                'plan_type': plan_type,
                'amount_paid': amount_paid,
                'is_active': True
            }
        )
        
        if not created:
            enrollment.plan_type = plan_type
            enrollment.amount_paid = amount_paid
            enrollment.is_active = True
            enrollment.save()
        
        # Set expiry date
        if plan_type == CoursePlanType.ONE_MONTH:
            enrollment.expiry_date = timezone.now() + timezone.timedelta(days=30)
        elif plan_type == CoursePlanType.THREE_MONTHS:
            enrollment.expiry_date = timezone.now() + timezone.timedelta(days=90)
        elif plan_type == CoursePlanType.LIFETIME:
            enrollment.expiry_date = None
        
        enrollment.save()
        
        return {
            'message': f"Added {user.email} to {course.title}",
            'enrollment_id': enrollment.id,
            'user_id': user.id,
            'course_id': course.id
        }
    
    def _bulk_remove_student(self, admin_user, data):
        """Remove single student in bulk operation"""
        user = User.objects.get(pk=data['user_id'])
        course = Course.objects.get(pk=data['course_id'])
        reason = data.get('reason', '')
        
        enrollment = Enrollment.objects.get(user=user, course=course, is_active=True)
        enrollment.is_active = False
        enrollment.save()
        
        return {
            'message': f"Removed {user.email} from {course.title}",
            'enrollment_id': enrollment.id,
            'user_id': user.id,
            'course_id': course.id,
            'reason': reason
        }

# ADD THESE SERIALIZERS TO serializers.py
# ========================================

class AdminRemoveStudentSerializer(serializers.Serializer):
    """Serializer for admin removing student from subscription plan"""
    user_id = serializers.IntegerField(help_text="ID of the user to remove")
    course_id = serializers.IntegerField(help_text="ID of the course to remove from")
    reason = serializers.CharField(
        max_length=500, 
        required=False, 
        allow_blank=True,
        help_text="Reason for removal"
    )
    refund_amount = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        required=False,
        allow_null=True,
        help_text="Refund amount (optional)"
    )
    
    class Meta:
        ref_name = "AdminRemoveStudentSerializer"

class AdminBulkEnrollmentSerializer(serializers.Serializer):
    """Serializer for bulk enrollment operations"""
    operation = serializers.ChoiceField(
        choices=['add', 'remove'],
        help_text="Operation type: add or remove"
    )
    enrollments = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of enrollment operations"
    )
    
    class Meta:
        ref_name = "AdminBulkEnrollmentSerializer"