import hashlib
from rest_framework.response import Response
from django.contrib.auth import get_user_model, authenticate
from rest_framework import viewsets, permissions, filters, status, generics, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.decorators import action
from django.db.models import Count
from django.utils import timezone
from django.core.mail import send_mail
from core.s3_utils import generate_presigned_url, is_s3_url
from django.core.cache import cache
from django.conf import settings
from django.db.models import Q, Prefetch
# Add or modify the following in core/views.py
from rest_framework import viewsets, status, parsers
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import action
from django.db import transaction
from .models import Course, CourseObjective, CourseRequirement, CourseCurriculum, Category
from .serializers import CourseCreateUpdateSerializer, CourseDetailSerializer, CourseListSerializer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from core.func import performance_monitor
from core.permissions import IsEnrolledOrAdmin
from core.s3_utils import is_s3_url
from .services import RazorpayService,  process_course_purchase
from .tasks import send_push_notification
from django.db import transaction
import csv
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from PIL import Image
from django.db import models
import io
import uuid
from .models import (
    Course, CoursePlanType, Enrollment, Category, FCMDevice, Notification,
    SubscriptionPlan, UserSubscription, Wishlist, 
    PaymentCard, Purchase, User
)
from .serializers import (
    CourseCurriculumSerializer, CourseListSerializer, CourseDetailSerializer, CategorySerializer,
    CourseCreateUpdateSerializer, CourseObjectiveSerializer, CourseRequirementSerializer, CreateOrderSerializer, EnrollmentListSerializer, EnrollmentSerializer, FCMDeviceSerializer, LightweightEnrollmentSerializer, 
    NotificationSerializer, PurchaseCourseSerializer, SubscriptionPlanSerializer, SubscriptionPlanCreateUpdateSerializer, UserDetailsSerializer, UserProfilePictureSerializer, UserProfilePictureUploadSerializer,
    UserSubscriptionSerializer, VerifyPaymentSerializer, WishlistSerializer, 
    PaymentCardSerializer, PurchaseSerializer, UserSerializer,
    ForgotPasswordSerializer, VerifyOTPSerializer
)
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from io import BytesIO
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

# Add LogoutSerializer
class LogoutSerializer(serializers.Serializer):
    """Serializer for logout view."""
    pass

class CategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing course categories.
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAdminUser]
    
    @swagger_auto_schema(
        operation_summary="List all categories",
        operation_description="Returns a list of all available course categories."
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Retrieve a category",
        operation_description="Returns the details of a specific category by ID along with related courses."
    )
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        # Get courses for this category
        courses = Course.objects.filter(category=instance)
        course_serializer = CourseListSerializer(
            courses, 
            many=True, 
            context={'request': request}
        )
        
        # Combine data
        data = serializer.data
        data['courses'] = course_serializer.data
        
        return Response(data)
    
    @swagger_auto_schema(
        operation_summary="Create a category",
        operation_description="Creates a new category (admin only)."
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Update a category",
        operation_description="Updates an existing category (admin only)."
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Partially update a category",
        operation_description="Partially updates an existing category (admin only)."
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Delete a category",
        operation_description="Deletes a category (admin only)."
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return super().get_permissions()



class CourseViewSet(viewsets.ModelViewSet):
    """
    API endpoints for course management.
    """
    queryset = Course.objects.all()
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CourseCreateUpdateSerializer
        elif self.action == 'retrieve':
            return CourseDetailSerializer
        return CourseListSerializer  # Use CourseListSerializer for list view too
    
    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsAuthenticated, IsAdminUser]
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        """
        Optionally restricts the returned courses by filtering against query parameters.
        OPTIMIZED: Includes prefetch_related for related objects to reduce database queries.
        """
        # Base queryset with optimized joins
        queryset = Course.objects.select_related(
            'category'  # Join category table
        ).prefetch_related(
            # Prefetch objectives
            models.Prefetch(
                'objectives',
                queryset=CourseObjective.objects.all()
            ),
            # Prefetch requirements
            models.Prefetch(
                'requirements', 
                queryset=CourseRequirement.objects.all()
            ),
            # Prefetch curriculum ordered by order field
            models.Prefetch(
                'curriculum',
                queryset=CourseCurriculum.objects.order_by('order')
            ),
            # Prefetch enrollments for enrollment checking
            models.Prefetch(
                'enrollments',
                queryset=Enrollment.objects.select_related('user')
            ),
            # Prefetch wishlist entries
            models.Prefetch(
                'wishlisted_by',
                queryset=Wishlist.objects.select_related('user')
            )
        )
        
        # Apply filters
        # Filter by category
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        # Filter featured courses
        is_featured = self.request.query_params.get('featured')
        if is_featured and is_featured.lower() == 'true':
            queryset = queryset.filter(is_featured=True)
        
        # Search by title or description
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(small_desc__icontains=search)
            )
        
        # Filter by location
        location = self.request.query_params.get('location')
        if location:
            queryset = queryset.filter(location__icontains=location)
        
        return queryset
    
    @swagger_auto_schema(
        operation_summary="List all courses",
        operation_description="Returns a list of all courses with complete information including enrollment status",
        manual_parameters=[
            openapi.Parameter('category', openapi.IN_QUERY, description="Filter by category ID", type=openapi.TYPE_INTEGER),
            openapi.Parameter('featured', openapi.IN_QUERY, description="Filter featured courses (true/false)", type=openapi.TYPE_BOOLEAN),
            openapi.Parameter('search', openapi.IN_QUERY, description="Search by title or description", type=openapi.TYPE_STRING),
            openapi.Parameter('location', openapi.IN_QUERY, description="Filter by location", type=openapi.TYPE_STRING),
        ],
        responses={
            status.HTTP_200_OK: CourseListSerializer(many=True)
        }
    )
    def list(self, request, *args, **kwargs):
        """
        List all courses with complete information including enrollment status.
        Uses CourseListSerializer which now includes all the detailed information.
        """
        return super().list(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Retrieve a course",
        operation_description="Returns detailed information about a specific course",
        responses={
            status.HTTP_200_OK: CourseDetailSerializer(),
            status.HTTP_404_NOT_FOUND: "Course not found"
        }
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    
    @swagger_auto_schema(
        operation_summary="Create a new course",
        operation_description="Creates a new course with all related information (objectives, requirements, curriculum)",
        request_body=CourseCreateUpdateSerializer,
        responses={
            status.HTTP_201_CREATED: CourseDetailSerializer(),
            status.HTTP_400_BAD_REQUEST: "Invalid request data"
        }
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = serializer.save()
        
        # Return full course details
        return Response(
            CourseDetailSerializer(course, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED
        )
    
    @swagger_auto_schema(
        operation_summary="Update a course",
        operation_description="Updates a course and its related information (objectives, requirements, curriculum)",
        request_body=CourseCreateUpdateSerializer,
        responses={
            status.HTTP_200_OK: CourseDetailSerializer(),
            status.HTTP_400_BAD_REQUEST: "Invalid request data",
            status.HTTP_404_NOT_FOUND: "Course not found"
        }
    )
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        course = serializer.save()
        
        # Return full course details
        return Response(
            CourseDetailSerializer(course, context=self.get_serializer_context()).data
        )

    @swagger_auto_schema(
        operation_summary="Partially update a course",
        operation_description="Partially updates a course and its related information",
        request_body=CourseCreateUpdateSerializer,
        responses={
            status.HTTP_200_OK: CourseDetailSerializer(),
            status.HTTP_400_BAD_REQUEST: "Invalid request data",
            status.HTTP_404_NOT_FOUND: "Course not found"
        }
    )
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Debug output for partial update
        print(f"Partial update for course {instance.id}")
        print(f"Request data: {request.data}")
        
        # Handle the case where only form data is sent without JSON for related fields
        data = request.data.copy()
        
        # Check if objectives, requirements, curriculum are present in the request
        # but as empty strings (which can happen with form data)
        for field in ['objectives', 'requirements', 'curriculum']:
            if field in data and data[field] == '':
                # Remove the field so it's not processed by the serializer
                data.pop(field)
                print(f"Removed empty {field} field from request data")
        
        serializer = self.get_serializer(
            instance, 
            data=data, 
            partial=True
        )
        
        serializer.is_valid(raise_exception=True)
        
        # Debug output for what will be updated
        print(f"Valid data for update: {serializer.validated_data}")
        
        course = serializer.save()
        
        # Return full course details
        return Response(
            CourseDetailSerializer(course, context=self.get_serializer_context()).data
        )
    
    @swagger_auto_schema(
        operation_summary="Delete a course",
        operation_description="Deletes a course and all its related information",
        responses={
            status.HTTP_204_NO_CONTENT: "Course deleted successfully",
            status.HTTP_404_NOT_FOUND: "Course not found"
        }
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
    
    @swagger_auto_schema(
        method='get',
        operation_summary="Get featured courses",
        operation_description="Returns a list of featured courses",
        responses={
            status.HTTP_200_OK: CourseListSerializer(many=True)
        }
    )
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """
        List all featured courses.
        """
        featured_courses = Course.objects.filter(is_featured=True)
        page = self.paginate_queryset(featured_courses)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(featured_courses, many=True)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        method='get',
        operation_summary="Get top courses",
        operation_description="Returns a list of top courses based on enrollment count. If no courses have enrollments, returns the 5 most recent courses.",
        manual_parameters=[
            openapi.Parameter('limit', openapi.IN_QUERY, 
                            description="Number of courses to return (default: 10)", 
                            type=openapi.TYPE_INTEGER)
        ],
        responses={
            status.HTTP_200_OK: CourseListSerializer(many=True)
        }
    )
    @action(detail=False, methods=['get'])
    def top(self, request):
        """
        List top courses based on enrollment count.
        If no courses have enrollments, returns the 5 most recent courses.
        """
        # Get the limit parameter with a default of 10
        limit = request.query_params.get('limit', 10)
        try:
            limit = int(limit)
        except ValueError:
            limit = 10
        
        # Get courses ordered by enrollment count with a different annotation name
        top_courses = Course.objects.annotate(
            enrollment_count=Count('enrollments')
        ).order_by('-enrollment_count', '-date_uploaded')[:limit]
        
        # Check if there are courses and if any have enrollments
        if not top_courses.exists() or top_courses.aggregate(max_enrollments=models.Max('enrollment_count'))['max_enrollments'] == 0:
            top_courses = Course.objects.order_by('-date_uploaded')[:5]
        
        page = self.paginate_queryset(top_courses)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(top_courses, many=True)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        method='get',
        operation_summary="Get courses by category",
        operation_description="Returns a list of courses in a specific category",
        manual_parameters=[
            openapi.Parameter('category_id', openapi.IN_PATH, description="Category ID", type=openapi.TYPE_INTEGER, required=True),
        ],
        responses={
            status.HTTP_200_OK: CourseListSerializer(many=True),
            status.HTTP_404_NOT_FOUND: "Category not found"
        }
    )
    @action(detail=False, methods=['get'], url_path='category/(?P<category_id>\d+)')
    def by_category(self, request, category_id=None):
        """
        List all courses in a specific category.
        """
        try:
            Category.objects.get(pk=category_id)
        except Category.DoesNotExist:
            return Response(
                {"error": "Category not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        courses = Course.objects.filter(category_id=category_id)
        page = self.paginate_queryset(courses)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(courses, many=True)
        return Response(serializer.data)
    
    @swagger_auto_schema(
    method='post',
    operation_summary="Bulk create courses",
    operation_description="Creates multiple courses at once from JSON data",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'courses': openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'title': openapi.Schema(type=openapi.TYPE_STRING),
                        'small_desc': openapi.Schema(type=openapi.TYPE_STRING),
                        'category': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'is_featured': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'location': openapi.Schema(type=openapi.TYPE_STRING),
                        'objectives': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'description': openapi.Schema(type=openapi.TYPE_STRING)
                                }
                            )
                        ),
                        'requirements': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'description': openapi.Schema(type=openapi.TYPE_STRING)
                                }
                            )
                        ),
                        'curriculum': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'title': openapi.Schema(type=openapi.TYPE_STRING),
                                    'video_url': openapi.Schema(type=openapi.TYPE_STRING),
                                    'order': openapi.Schema(type=openapi.TYPE_INTEGER)
                                }
                            )
                        )
                    }
                )
            )
        },
        required=['courses']
    ),
    responses={
        status.HTTP_201_CREATED: openapi.Response(
            description="Courses created successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'success_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'failure_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'failed_entries': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'index': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'errors': openapi.Schema(type=openapi.TYPE_OBJECT)
                            }
                        )
                    )
                }
            )
        ),
        status.HTTP_400_BAD_REQUEST: "Invalid request data"
    }
)
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    def bulk_create(self, request):
        """
        Create multiple courses at once from JSON data.
        """
        if 'courses' not in request.data or not isinstance(request.data['courses'], list):
            return Response(
                {"error": "The request must include a 'courses' array"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        courses_data = request.data['courses']
        success_count = 0
        failure_count = 0
        failed_entries = []
        
        for idx, course_data in enumerate(courses_data):
            serializer = CourseCreateUpdateSerializer(data=course_data)
            try:
                if serializer.is_valid():
                    with transaction.atomic():
                        serializer.save()
                    success_count += 1
                else:
                    failure_count += 1
                    failed_entries.append({
                        'index': idx,
                        'errors': serializer.errors
                    })
            except Exception as e:
                failure_count += 1
                failed_entries.append({
                    'index': idx,
                    'errors': {'non_field_errors': [str(e)]}
                })
        
        return Response({
            'success_count': success_count,
            'failure_count': failure_count,
            'failed_entries': failed_entries
        }, status=status.HTTP_201_CREATED if success_count > 0 else status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='post',
        operation_summary="Import courses from CSV",
        operation_description="Imports courses from a CSV file with a specific format",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'csv_file': openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="CSV file with course data"
                )
            },
            required=['csv_file']
        ),
        responses={
            status.HTTP_201_CREATED: openapi.Response(
                description="Courses imported successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'success_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'failure_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'failed_entries': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'row': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'errors': openapi.Schema(type=openapi.TYPE_OBJECT)
                                }
                            )
                        )
                    }
                )
            ),
            status.HTTP_400_BAD_REQUEST: "Invalid CSV file"
        }
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    def import_csv(self, request):
        """
        Import courses from a CSV file.
        
        Expected CSV format:
        title,small_desc,category_id,is_featured,location,objectives,requirements,curriculum
        
        The objectives, requirements, and curriculum columns should contain JSON strings.
        """
        if 'csv_file' not in request.FILES:
            return Response(
                {"error": "No CSV file provided"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        csv_file = request.FILES['csv_file']
        if not csv_file.name.endswith('.csv'):
            return Response(
                {"error": "File is not a CSV"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Process the CSV file
        decoded_file = csv_file.read().decode('utf-8')
        io_string = io.StringIO(decoded_file)
        reader = csv.DictReader(io_string)
        
        success_count = 0
        failure_count = 0
        failed_entries = []
        
        for row_idx, row in enumerate(reader, start=1):
            try:
                # Process the JSON fields
                if 'objectives' in row:
                    row['objectives'] = json.loads(row['objectives'])
                else:
                    row['objectives'] = []
                    
                if 'requirements' in row:
                    row['requirements'] = json.loads(row['requirements'])
                else:
                    row['requirements'] = []
                    
                if 'curriculum' in row:
                    row['curriculum'] = json.loads(row['curriculum'])
                else:
                    row['curriculum'] = []
                
                # Convert 'is_featured' to boolean
                if 'is_featured' in row:
                    row['is_featured'] = row['is_featured'].lower() in ('true', 'yes', '1')
                else:
                    row['is_featured'] = False
                
                # Create the course
                serializer = CourseCreateUpdateSerializer(data=row)
                if serializer.is_valid():
                    with transaction.atomic():
                        serializer.save()
                    success_count += 1
                else:
                    failure_count += 1
                    failed_entries.append({
                        'row': row_idx,
                        'errors': serializer.errors
                    })
            except Exception as e:
                failure_count += 1
                failed_entries.append({
                    'row': row_idx,
                    'errors': {'non_field_errors': [str(e)]}
                })
        
        return Response({
            'success_count': success_count,
            'failure_count': failure_count,
            'failed_entries': failed_entries
        }, status=status.HTTP_201_CREATED if success_count > 0 else status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='post',
        operation_summary="Duplicate a course",
        operation_description="Creates a duplicate of an existing course with an optional new title",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'new_title': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="New title for the duplicated course (optional)"
                )
            }
        ),
        responses={
            status.HTTP_201_CREATED: CourseDetailSerializer(),
            status.HTTP_400_BAD_REQUEST: "Invalid request data",
            status.HTTP_404_NOT_FOUND: "Course not found"
        }
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    def duplicate(self, request, pk=None):
        """
        Create a duplicate of an existing course.
        """
        try:
            # Get the course to duplicate
            course = self.get_object()
            
            # Get the new title if provided, otherwise use the original title with "(Copy)" appended
            new_title = request.data.get('new_title', f"{course.title} (Copy)")
            
            # Create a new course with the same data
            new_course = Course.objects.create(
                title=new_title,
                image=course.image,
                small_desc=course.small_desc,
                category=course.category,
                is_featured=course.is_featured,
                location=course.location
            )
            
            # Duplicate objectives
            for objective in course.objectives.all():
                CourseObjective.objects.create(
                    course=new_course,
                    description=objective.description
                )
            
            # Duplicate requirements
            for requirement in course.requirements.all():
                CourseRequirement.objects.create(
                    course=new_course,
                    description=requirement.description
                )
            
            # Duplicate curriculum
            for curriculum_item in course.curriculum.all():
                CourseCurriculum.objects.create(
                    course=new_course,
                    title=curriculum_item.title,
                    video_url= curriculum_item.video_url,
                    order=curriculum_item.order
                )
            
            # Return the duplicated course details
            serializer = CourseDetailSerializer(new_course, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @swagger_auto_schema(
        method='post',
        operation_summary="Export course template",
        operation_description="Generates a CSV template for course import with example data",
        responses={
            status.HTTP_200_OK: "CSV template file",
            status.HTTP_500_INTERNAL_SERVER_ERROR: "Server error"
        }
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    def export_template(self, request):
        """
        Generate a CSV template for course import with example data.
        """
        try:
            # Create a CSV string
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write the header row
            header = ['title', 'small_desc', 'category_id', 'is_featured', 'location', 'objectives', 'requirements', 'curriculum']
            writer.writerow(header)
            
            # Write an example row
            example_objectives = json.dumps([
                {"description": "Understand basic concepts"},
                {"description": "Apply knowledge to real-world examples"}
            ])
            
            example_requirements = json.dumps([
                {"description": "Basic knowledge of the subject"},
                {"description": "Access to a computer"}
            ])
            
            example_curriculum = json.dumps([
                {"title": "Introduction", "video_url": "https://example.com/video1.mp4", "order": 1},
                {"title": "Basic Concepts", "video_url": "https://example.com/video2.mp4", "order": 2}
            ])
            
            example_row = [
                'Example Course Title',
                'This is a short description of the example course.',
                '1',  # Category ID (update with an actual category ID)
                'false',
                'Online',
                example_objectives,
                example_requirements,
                example_curriculum
            ]
            writer.writerow(example_row)
            
            # Create the response
            response = Response(output.getvalue(), content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="course_import_template.csv"'
            return response
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    @swagger_auto_schema(
    method='get',
    operation_summary="Get complete course details with enrollments",
    operation_description="Retrieves detailed information about a course including enrollment statistics",
    responses={
        status.HTTP_200_OK: CourseDetailSerializer(),
        status.HTTP_404_NOT_FOUND: "Course not found"
    }
)
    @action(detail=True, methods=['get'])
    def complete_details(self, request, pk=None):
        """
        Get complete details of a course including enrollment statistics.
        """
        try:
            course = self.get_object()
            
            # Get additional statistics
            enrollment_count = course.enrollments.count()
            recent_enrollments = course.enrollments.order_by('-date_enrolled')[:5]
            recent_students = [enrollment.user for enrollment in recent_enrollments]
            
            # Get base course details
            serializer = CourseDetailSerializer(course, context={'request': request})
            course_data = serializer.data
            
            # Add additional statistics
            course_data['statistics'] = {
                'total_enrollments': enrollment_count,
                'recent_enrollments': [
                    {
                        'student_id': student.id,
                        'student_name': student.full_name,
                        'student_email': student.email,
                        'date_enrolled': enrollment.date_enrolled
                    }
                    for enrollment, student in zip(recent_enrollments, recent_students)
                ],
                'curriculum_items_count': course.curriculum.count(),
                'total_rating': 4.5,  # Placeholder - implement actual rating calculation
                'review_count': 10,   # Placeholder - implement actual review count
            }
            
            return Response(course_data)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found"},
                status=status.HTTP_404_NOT_FOUND
            )

class EnrollmentViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing course enrollments - UPDATED WITH DURATION EXTRACTION
    """
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Enrollment.objects.none()  # Dummy queryset for swagger
    
    def get_serializer_class(self):
        """Use lightweight serializer for list views"""
        if self.action == 'list':
            return LightweightEnrollmentSerializer
        return EnrollmentSerializer
    
    def get_queryset(self):
        """OPTIMIZED: Different queries for different actions with curriculum count annotation"""
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        
        # ACTION-SPECIFIC OPTIMIZATION
        if self.action == 'list':
            # MINIMAL QUERY FOR LIST - with curriculum count annotation
            return Enrollment.objects.filter(
                user=self.request.user,
                is_active=True  # Only show active enrollments
            ).select_related(
                'course',           # Join course table
                'course__category'  # Join category table  
            ).annotate(
                # Add curriculum count for fast access
                curriculum_count=Count('course__curriculum')
            ).prefetch_related(
                # Prefetch curriculum for duration calculation
                Prefetch(
                    'course__curriculum',
                    queryset=CourseCurriculum.objects.only(
                        'id', 'title', 'video_url', 'order', 'course_id'
                    ).order_by('order')
                )
            ).only(
                # Only fetch essential fields - reduces data transfer
                'id', 'date_enrolled', 'plan_type', 'expiry_date', 
                'amount_paid', 'is_active',
                'course__id', 'course__title', 'course__image', 
                'course__small_desc', 'course__category__name'
            ).order_by('-date_enrolled')[:25]  # Limit to 25 most recent
            
        else:
            # FULL QUERY FOR DETAIL VIEW
            return Enrollment.objects.filter(
                user=self.request.user
            ).select_related(
                'course',
                'course__category'
            ).annotate(
                curriculum_count=Count('course__curriculum')
            ).prefetch_related(
                models.Prefetch(
                    'course__objectives',
                    queryset=CourseObjective.objects.only('id', 'description')
                ),
                models.Prefetch(
                    'course__requirements',
                    queryset=CourseRequirement.objects.only('id', 'description')
                ),
                models.Prefetch(
                    'course__curriculum',
                    queryset=CourseCurriculum.objects.only(
                        'id', 'title', 'video_url', 'order'
                    ).order_by('order')
                )
            ).order_by('-date_enrolled')
    
    def _get_cache_key(self, request):
        """Generate cache key for enrollment list"""
        show_all = request.query_params.get('show_all', 'false')
        key_data = f"enrollments_v6_{request.user.id}_{show_all}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _clear_user_cache(self, user_id):
        """Clear all enrollment caches for a user"""
        Enrollment.clear_user_enrollment_caches(user_id)
        
    def list(self, request, *args, **kwargs):
        """HEAVILY CACHED list with smart cache keys"""
        try:
            # STEP 1: Check cache first
            cache_key = self._get_cache_key(request)
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info(f"Cache HIT for user {request.user.id}")
                return Response(cached_data)
            
            logger.info(f"Cache MISS for user {request.user.id} - fetching from DB")
            
            # STEP 2: Get optimized queryset
            queryset = self.get_queryset()
            
            # STEP 3: Early return if no data
            if not queryset.exists():
                empty_result = []
                cache.set(cache_key, empty_result, 1800)
                return Response(empty_result)
            
            # STEP 4: Use lightweight serializer with duration extraction
            serializer = self.get_serializer(queryset, many=True, context={'request': request})
            response_data = serializer.data
            
            # STEP 5: Cache for 1 hour
            cache.set(cache_key, response_data, 3600)
            logger.info(f"Cached enrollment data for user {request.user.id}")
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Enrollment list error for user {request.user.id}: {str(e)}")
            return Response(
                {"error": "Failed to fetch enrollments", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Keep all your existing methods but add cache clearing:
    def create(self, request, *args, **kwargs):
        try:
            self._clear_user_cache(request.user.id)
            from .payment_views import CreateOrderView
            return CreateOrderView.as_view()(request)
        except Exception as e:
            logger.error(f"Error in enrollment create: {str(e)}")
            return Response(
                {"error": "Failed to create enrollment", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def destroy(self, request, *args, **kwargs):
        try:
            self._clear_user_cache(request.user.id)
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error in enrollment destroy: {str(e)}")
            return Response(
                {"error": "Failed to delete enrollment", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def retrieve(self, request, *args, **kwargs):
        """Retrieve with GUARANTEED fresh presigned URLs"""
        try:
            enrollment_id = kwargs.get('pk')
            
            # Get enrollment
            enrollment = self.get_queryset().filter(id=enrollment_id).first()
            if not enrollment:
                return Response(
                    {"error": "Enrollment not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # FORCE FRESH URLS by modifying the video URLs directly
            course = enrollment.course
            
            # Get all curriculum items and force fresh presigned URLs
            for curriculum_item in course.curriculum.all():
                if curriculum_item.video_url and is_s3_url(curriculum_item.video_url):
                    # Generate fresh presigned URL directly
                    fresh_url = generate_presigned_url(
                        curriculum_item.video_url, 
                        expiration=43200,  # 12 hours
                       
                    )
                    # Temporarily store the fresh URL (don't save to DB)
                    curriculum_item._fresh_video_url = fresh_url
            
            # Use modified serializer
            class FreshEnrollmentSerializer(EnrollmentSerializer):
                class FreshCourseDetailSerializer(CourseDetailSerializer):
                    class FreshCourseCurriculumSerializer(CourseCurriculumSerializer):
                        def get_video_url(self, obj):
                            # Use the fresh URL we generated above
                            if hasattr(obj, '_fresh_video_url'):
                                return obj._fresh_video_url
                            return super().get_video_url(obj)
                    
                    curriculum = FreshCourseCurriculumSerializer(many=True, read_only=True)
                
                course = FreshCourseDetailSerializer(read_only=True)
            
            serializer = FreshEnrollmentSerializer(enrollment, context={'request': request})
            
            logger.info(f"Retrieved enrollment {enrollment_id} with FORCED fresh URLs")
            
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error in enrollment retrieve: {str(e)}")
            return Response(
                {"error": "Failed to fetch enrollment details", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get_fresh_serializer(self, enrollment, context=None):
        """Get serializer that generates fresh presigned URLs"""
        
        class FreshEnrollmentSerializer(EnrollmentSerializer):
            """Enrollment serializer that forces fresh presigned URLs"""
            
            class FreshCourseDetailSerializer(CourseDetailSerializer):
                """Course serializer with fresh curriculum URLs"""
                
                class FreshCourseCurriculumSerializer(CourseCurriculumSerializer):
                    """Curriculum serializer that always generates fresh presigned URLs"""
                    
                    def get_video_url(self, obj):
                        """Generate fresh presigned URL for S3 videos - NO CACHING"""
                        url = obj.video_url
                        
                        from core.s3_utils import generate_presigned_url
                        # Generate fresh URL with long expiration
                        fresh_url = generate_presigned_url(url, expiration=43200)  # 12 hours
                        logger.debug(f"Generated fresh presigned URL for curriculum {obj.id}")
                        return fresh_url
                        # return url
                
                # Override curriculum field to use fresh serializer
                curriculum = FreshCourseCurriculumSerializer(many=True, read_only=True)
            
            # Override course field to use fresh serializer
            course = FreshCourseDetailSerializer(read_only=True)
        
        return FreshEnrollmentSerializer(enrollment, context=context)
    
    @action(detail=False, methods=['post'])
    def verify_payment(self, request):
        try:
            self._clear_user_cache(request.user.id)
            from .payment_views import VerifyPaymentView
            return VerifyPaymentView.as_view()(request)
        except Exception as e:
            logger.error(f"Error in verify_payment: {str(e)}")
            return Response(
                {"error": "Failed to verify payment", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def check_status(self, request):
        try:
            course_id = request.query_params.get('course_id')
            if not course_id:
                return Response(
                    {"error": "course_id parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # OPTIMIZED: Add caching for enrollment status checks
            cache_key = f"enrollment_status_{request.user.id}_{course_id}"
            cached_result = cache.get(cache_key)
            if cached_result:
                return Response(cached_result)
            
            # OPTIMIZED: Use select_related for efficient database query
            is_enrolled = Enrollment.objects.select_related('course').filter(
                user=request.user, 
                course_id=course_id
            ).exists()
            
            # Get subscription details if enrolled
            subscription_details = None
            if is_enrolled:
                subscription = UserSubscription.objects.select_related('plan').filter(
                    user=request.user,
                    is_active=True,
                    end_date__gt=timezone.now()
                ).first()
                
                if subscription:
                    subscription_details = {
                        'plan_name': subscription.plan.name,
                        'end_date': subscription.end_date,
                        'is_active': subscription.is_active
                    }
            
            result = {
                'is_enrolled': is_enrolled,
                'subscription_details': subscription_details
            }
            
            # Cache for 2 minutes
            cache.set(cache_key, result, 120)
            
            return Response(result)
            
        except Exception as e:
            logger.error(f"Error in check_status: {str(e)}")
            return Response(
                {"error": "Failed to check enrollment status", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Fast summary endpoint with aggregated data including total curriculum and duration"""
        cache_key = f"enrollment_summary_v3_{request.user.id}"
        cached_summary = cache.get(cache_key)
        
        if cached_summary:
            return Response(cached_summary)
        
        # Use database aggregation for speed
        from django.db.models import Count, Q, Sum
        
        summary = Enrollment.objects.filter(user=request.user).aggregate(
            total_enrollments=Count('id'),
            active_enrollments=Count('id', filter=Q(is_active=True)),
            expired_enrollments=Count('id', filter=Q(is_active=True, expiry_date__lt=timezone.now())),
            # Add total curriculum count across all enrollments
            total_curriculum_items=Sum('course__curriculum__id', distinct=True)
        )
        
        # Calculate total estimated duration
        active_enrollments = Enrollment.objects.filter(
            user=request.user, 
            is_active=True
        ).prefetch_related('course__curriculum')
        
        total_duration = 0
        total_curriculum = 0
        
        for enrollment in active_enrollments:
            curriculum_items = enrollment.course.curriculum.all()
            total_curriculum += len(curriculum_items)
            
            # Extract duration from video URLs (cached per course)
            course_duration = self._get_course_duration(enrollment.course.id, curriculum_items)
            total_duration += course_duration
        
        summary.update({
            'total_curriculum_items': total_curriculum,
            'total_estimated_duration_minutes': total_duration,
            'total_estimated_duration_hours': round(total_duration / 60, 1)
        })
        
        # Cache summary for 30 minutes
        cache.set(cache_key, summary, 1800)
        return Response(summary)
    
    def _get_course_duration(self, course_id, curriculum_items):
        """Get total duration for a course with caching"""
        cache_key = f"course_duration_{course_id}"
        cached_duration = cache.get(cache_key)
        
        if cached_duration is not None:
            return cached_duration
        
        total_duration = 0
        
        for item in curriculum_items:
            if item.video_url:
                # Extract duration from video URL
                duration = self._extract_video_duration(item.video_url)
                total_duration += duration
            else:
                # Default duration if no video URL
                total_duration += 10  # 10 minutes default
        
        # Cache course duration for 24 hours
        cache.set(cache_key, total_duration, 86400)
        return total_duration
    
    def _extract_video_duration(self, video_url):
        """Extract video duration from AWS S3 URL or video metadata"""
        cache_key = f"video_duration_{hashlib.md5(video_url.encode()).hexdigest()}"
        cached_duration = cache.get(cache_key)
        
        if cached_duration is not None:
            return cached_duration
        
        duration = 10  # Default 10 minutes
        
        try:
            # Method 1: Try to extract from S3 metadata
            duration = self._get_s3_video_duration(video_url)
            
            if duration == 10:  # If S3 method failed, try other methods
                # Method 2: Extract from URL patterns (if duration is in filename)
                duration = self._extract_duration_from_filename(video_url)
                
                if duration == 10:  # If filename method failed
                    # Method 3: Use video processing library (slower but accurate)
                    duration = self._get_video_duration_from_file(video_url)
        
        except Exception as e:
            logger.warning(f"Failed to extract duration from {video_url}: {str(e)}")
            duration = 10  # Fallback to default
        
        # Cache duration for 7 days
        cache.set(cache_key, duration, 604800)
        return duration
    
    def _get_s3_video_duration(self, video_url):
        """Extract video duration from S3 object metadata"""
        try:
            from core.s3_utils import get_s3_key_and_bucket, is_s3_url
            import boto3
            
            if not is_s3_url(video_url):
                return 10
            
            bucket_name, object_key = get_s3_key_and_bucket(video_url)
            if not bucket_name or not object_key:
                return 10
            
            # Create S3 client
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
            
            # Get object metadata
            response = s3_client.head_object(Bucket=bucket_name, Key=object_key)
            metadata = response.get('Metadata', {})
            
            # Check for duration in metadata
            if 'duration' in metadata:
                return int(float(metadata['duration']))
            elif 'duration-seconds' in metadata:
                return int(float(metadata['duration-seconds']) / 60)
            elif 'video-duration' in metadata:
                return int(float(metadata['video-duration']))
            
            # Check content length for rough estimation (very rough!)
            content_length = response.get('ContentLength', 0)
            if content_length > 0:
                # Very rough estimation: 1MB per minute of video (varies greatly)
                estimated_minutes = max(5, content_length // (1024 * 1024))
                return min(estimated_minutes, 120)  # Cap at 2 hours
            
        except Exception as e:
            logger.debug(f"S3 duration extraction failed: {str(e)}")
        
        return 10
    
    def _extract_duration_from_filename(self, video_url):
        """Try to extract duration from filename patterns"""
        try:
            import re
            
            # Common patterns in filenames
            patterns = [
                r'_(\d+)min_',           # _15min_
                r'_(\d+)m_',             # _15m_
                r'-(\d+)min-',           # -15min-
                r'-(\d+)m-',             # -15m-
                r'(\d+)minutes',         # 15minutes
                r'duration-(\d+)',       # duration-15
                r'(\d+)-minutes',        # 15-minutes
            ]
            
            for pattern in patterns:
                match = re.search(pattern, video_url, re.IGNORECASE)
                if match:
                    duration = int(match.group(1))
                    if 1 <= duration <= 300:  # Reasonable range: 1-300 minutes
                        return duration
            
        except Exception as e:
            logger.debug(f"Filename duration extraction failed: {str(e)}")
        
        return 10
    
    def _get_video_duration_from_file(self, video_url):
        """Get actual video duration using video processing (slower but accurate)"""
        try:
            # This method requires downloading the video file
            # Only use for critical cases or with small video files
            
            # Option 1: Use ffprobe if available
            duration = self._get_duration_with_ffprobe(video_url)
            if duration > 0:
                return duration
            
            # Option 2: Use moviepy (requires installation)
            # from moviepy.editor import VideoFileClip
            # clip = VideoFileClip(video_url)
            # duration = int(clip.duration / 60)
            # clip.close()
            # return duration
            
        except Exception as e:
            logger.debug(f"Video file duration extraction failed: {str(e)}")
        
        return 10
    
    def _get_duration_with_ffprobe(self, video_url):
        """Use ffprobe to get video duration (requires ffmpeg installation)"""
        try:
            import subprocess
            import json
            
            # Only try this for smaller files or in development
            if 'development' not in settings.DEBUG:
                return 10
            
            # Generate presigned URL for ffprobe
          
            presigned_url = generate_presigned_url(video_url, 3600)
            
            # Run ffprobe
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', presigned_url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                duration_seconds = float(data['format']['duration'])
                return int(duration_seconds / 60)
            
        except Exception as e:
            logger.debug(f"ffprobe duration extraction failed: {str(e)}")
        
        return 10
            
class SimpleEnrollmentViewSet(viewsets.ModelViewSet):
    """
    Simple fallback enrollment viewset without optimizations
    Use this if the optimized version is causing issues
    """
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    
    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action == 'list':
            return EnrollmentListSerializer  # Fast for lists
        return EnrollmentSerializer  # Detailed for individual items
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Enrollment.objects.none()
        
        # Optimize based on action
        if self.action == 'list':
            # Minimal query for list view
            return Enrollment.objects.filter(
                user=self.request.user,
                is_active=True
            ).select_related(
                'course', 'course__category'
            ).only(
                'id', 'date_enrolled', 'plan_type', 'expiry_date', 
                'amount_paid', 'is_active',
                'course__id', 'course__title', 'course__image', 
                'course__category__name'
            ).order_by('-date_enrolled')[:50]
        else:
            # Full query for detail view
            return Enrollment.objects.filter(
                user=self.request.user
            ).select_related(
                'course', 'course__category'
            ).prefetch_related(
                models.Prefetch('course__objectives', queryset=CourseObjective.objects.all()),
                models.Prefetch('course__requirements', queryset=CourseRequirement.objects.all()),
                models.Prefetch('course__curriculum', queryset=CourseCurriculum.objects.order_by('order'))
            ).order_by('-date_enrolled')
    
    def list(self, request, *args, **kwargs):
        """Optimized list with caching"""
        cache_key = self._get_cache_key(request)
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        response_data = serializer.data
        
        cache.set(cache_key, response_data, 3600)
        return Response(response_data)

class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing subscription plans.
    """
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer  # Default serializer for swagger
    
    def get_serializer_class(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.serializer_class
        
        if self.action in ['create', 'update', 'partial_update']:
            return SubscriptionPlanCreateUpdateSerializer
        return SubscriptionPlanSerializer
    
    @swagger_auto_schema(
        operation_summary="List all subscription plans",
        operation_description="Returns a list of all available subscription plans."
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Retrieve a subscription plan",
        operation_description="Returns the details of a specific subscription plan by ID."
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Create a subscription plan",
        operation_description="Creates a new subscription plan (admin only)."
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Update a subscription plan",
        operation_description="Updates an existing subscription plan (admin only)."
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Partially update a subscription plan",
        operation_description="Partially updates an existing subscription plan (admin only)."
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Delete a subscription plan",
        operation_description="Deletes a subscription plan (admin only)."
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]

class UserSubscriptionViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing user subscriptions.
    """
    serializer_class = UserSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = UserSubscription.objects.none()  # Dummy queryset for swagger
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return UserSubscription.objects.filter(user=self.request.user)
    
    @swagger_auto_schema(
        operation_summary="List user subscriptions",
        operation_description="Returns a list of the user's subscriptions."
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Retrieve subscription details",
        operation_description="Returns the details of a specific user subscription."
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Subscribe to a plan",
        operation_description="Subscribes the user to a plan.",
        request_body=UserSubscriptionSerializer
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        # Check if user already has an active subscription
        active_subscription = UserSubscription.objects.filter(
            user=self.request.user, 
            is_active=True, 
            end_date__gt=timezone.now()
        ).first()
        
        if active_subscription:
            active_subscription.is_active = False
            active_subscription.save()
        
        # Create new subscription with end_date = start_date + 30 days
        subscription = serializer.save(
            user=self.request.user,
            end_date=timezone.now() + timezone.timedelta(days=30)
        )
        
        # Schedule expiration notification
        self.schedule_expiration_notification(subscription)
    
    @swagger_auto_schema(
        operation_summary="Update subscription",
        operation_description="Updates a user's subscription."
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Cancel subscription",
        operation_description="Cancels a user's subscription."
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
    
    def schedule_expiration_notification(self, subscription):
        # Send email notification
        subject = 'Your subscription is about to expire'
        message = f'Your {subscription.plan.name} subscription will expire on {subscription.end_date.strftime("%Y-%m-%d")}. Please renew to continue enjoying your benefits.'
        send_mail(subject, message, settings.EMAIL_HOST_USER, [subscription.user.email])
        
        # Send push notification
        send_push_notification.delay(
            subscription.user.id, 
            "Subscription Active",
            f"Your {subscription.plan.name} subscription is now active until {subscription.end_date.strftime('%Y-%m-%d')}"
        )

class WishlistViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing user wishlist.
    """
    serializer_class = WishlistSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Wishlist.objects.none()  # Dummy queryset for swagger
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return Wishlist.objects.filter(user=self.request.user)
    
    @swagger_auto_schema(
        operation_summary="List wishlist items",
        operation_description="Returns a list of courses in the user's wishlist."
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Retrieve wishlist item",
        operation_description="Returns the details of a specific wishlist item."
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Add to wishlist",
        operation_description="Adds a course to the user's wishlist.",
        request_body=WishlistSerializer
    )
    def create(self, request, *args, **kwargs):
        # Check if already in wishlist
        course_id = request.data.get('course')
        if Wishlist.objects.filter(user=request.user, course_id=course_id).exists():
            return Response(
                {'error': 'This course is already in your wishlist'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().create(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @swagger_auto_schema(
        operation_summary="Remove from wishlist",
        operation_description="Removes a course from the user's wishlist."
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

class PaymentCardViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing payment cards.
    """
    serializer_class = PaymentCardSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = PaymentCard.objects.none()  # Dummy queryset for swagger
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return PaymentCard.objects.filter(user=self.request.user)
    
    @swagger_auto_schema(
        operation_summary="List payment cards",
        operation_description="Returns a list of the user's payment cards."
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Retrieve card details",
        operation_description="Returns the details of a specific payment card."
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Add payment card",
        operation_description="Adds a new payment card.",
        request_body=PaymentCardSerializer
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        # If this is the first card or is_default is True, make it the default
        is_default = serializer.validated_data.get('is_default', False)
        if is_default or not PaymentCard.objects.filter(user=self.request.user).exists():
            PaymentCard.objects.filter(user=self.request.user).update(is_default=False)
        
        serializer.save(user=self.request.user)
    
    @swagger_auto_schema(
        operation_summary="Update payment card",
        operation_description="Updates an existing payment card."
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
    
    def perform_update(self, serializer):
        # If setting this card as default, update all other cards
        is_default = serializer.validated_data.get('is_default', False)
        if is_default:
            PaymentCard.objects.filter(user=self.request.user).exclude(
                id=serializer.instance.id
            ).update(is_default=False)
        
        serializer.save()
    
    @swagger_auto_schema(
        operation_summary="Delete payment card",
        operation_description="Deletes a payment card."
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

class PurchaseViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing course purchases.
    """
    serializer_class = PurchaseSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Purchase.objects.none()  # Dummy queryset for swagger
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return Purchase.objects.filter(user=self.request.user).order_by('-purchase_date')
    
    @swagger_auto_schema(
        operation_summary="List purchase history",
        operation_description="Returns a list of the user's course purchases."
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Retrieve purchase details",
        operation_description="Returns the details of a specific purchase."
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    # Remove the old create method since purchase is now handled by CoursePurchaseView
    def create(self, request, *args, **kwargs):
        return Response(
            {
                'error': 'Direct purchase creation is not allowed. Use /courses/purchase/ endpoint instead.'
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

class UpdateProfileView(generics.UpdateAPIView):
    """
    API endpoint for updating user profile.
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = User.objects.none()  # Dummy queryset for swagger
    
    def get_object(self):
        if getattr(self, 'swagger_fake_view', False):
            return None
        return self.request.user
    
    @swagger_auto_schema(
        operation_summary="Update user profile",
        operation_description="Updates the user's profile information.",
        request_body=UserSerializer
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Partially update user profile",
        operation_description="Partially updates the user's profile information.",
        request_body=UserSerializer
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

class LogoutView(generics.GenericAPIView):
    """
    API endpoint for user logout.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LogoutSerializer  # Add serializer class for swagger
    
    @swagger_auto_schema(
        operation_summary="Logout",
        operation_description="Logs out the current user by invalidating their token.",
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Successfully logged out",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            )
        }
    )
    def post(self, request):
        # Delete the token to logout
        request.auth.delete()
        return Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)

class DeleteAccountView(generics.DestroyAPIView):
    """
    API endpoint for deleting user account.
    """
    permission_classes = [permissions.IsAuthenticated]
    queryset = User.objects.none()  # Dummy queryset for swagger
    serializer_class = UserSerializer  # Add serializer class for swagger
    
    def get_object(self):
        if getattr(self, 'swagger_fake_view', False):
            return None
        return self.request.user
    
    @swagger_auto_schema(
        operation_summary="Delete account",
        operation_description="Permanently deletes the user's account.",
        responses={
            status.HTTP_204_NO_CONTENT: openapi.Response(
                description="Account deleted successfully"
            )
        }
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)

class NotificationViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing user notifications.
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Notification.objects.none()  # Dummy queryset for swagger
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
            
        # Filter by is_seen if provided
        is_seen = self.request.query_params.get('is_seen')
        queryset = Notification.objects.filter(user=self.request.user)
        
        if is_seen is not None:
            is_seen_bool = is_seen.lower() == 'true'
            queryset = queryset.filter(is_seen=is_seen_bool)
            
        return queryset
    
    @swagger_auto_schema(
        operation_summary="List notifications",
        operation_description="Returns a list of the user's notifications. Can be filtered by 'is_seen' parameter.",
        manual_parameters=[
            openapi.Parameter(
                'is_seen', 
                openapi.IN_QUERY, 
                description="Filter by seen status (true/false)", 
                type=openapi.TYPE_BOOLEAN
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Retrieve notification",
        operation_description="Returns the details of a specific notification."
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @swagger_auto_schema(
        operation_summary="Mark all notifications as seen",
        operation_description="Marks all user notifications as seen.",
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="All notifications marked as seen",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            )
        }
    )
    @action(detail=False, methods=['post'])
    def mark_all_as_seen(self, request):
        Notification.objects.filter(
            user=request.user,
            is_seen=False
        ).update(is_seen=True)
        
        return Response({'message': 'All notifications marked as seen'})
    
    @swagger_auto_schema(
        operation_summary="Mark notification as seen",
        operation_description="Marks a specific notification as seen.",
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Notification marked as seen",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            )
        }
    )
    @action(detail=True, methods=['post'])
    def mark_as_seen(self, request, pk=None):
        notification = self.get_object()
        notification.is_seen = True
        notification.save()
        
        return Response({'message': 'Notification marked as seen'})

class FCMDeviceViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing FCM device registrations for push notifications.
    """
    serializer_class = FCMDeviceSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = FCMDevice.objects.none()  # Dummy queryset for swagger
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return FCMDevice.objects.filter(user=self.request.user)
    
    @swagger_auto_schema(
        operation_summary="List registered devices",
        operation_description="Returns a list of the user's registered devices for push notifications."
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Retrieve device details",
        operation_description="Returns the details of a specific registered device."
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Register device",
        operation_description="Registers a device for push notifications.",
        request_body=FCMDeviceSerializer
    )
    def create(self, request, *args, **kwargs):
        # Check if device already exists for this user
        device_id = request.data.get('device_id')
        try:
            device = FCMDevice.objects.get(device_id=device_id)
            if device.user != request.user:
                # Device exists but belongs to another user
                device.user = request.user
                device.registration_id = request.data.get('registration_id')
                device.active = True
                device.save()
                return Response(FCMDeviceSerializer(device).data)
            else:
                # Device exists and belongs to this user, update registration ID
                device.registration_id = request.data.get('registration_id')
                device.active = True
                device.save()
                return Response(FCMDeviceSerializer(device).data)
        except FCMDevice.DoesNotExist:
            # Device doesn't exist, create new
            return super().create(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @swagger_auto_schema(
        operation_summary="Update device registration",
        operation_description="Updates an existing device registration."
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Delete device registration",
        operation_description="Deletes a device registration."
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
    
    

@csrf_exempt
def debug_login(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            email = data.get('email')
            password = data.get('password')
            
            # Check if user exists
            try:
                user = User.objects.get(email__iexact=email)
                user_exists = True
                has_password = bool(user.password)
            except User.DoesNotExist:
                user_exists = False
                has_password = False
            
            # Try both authentication methods
            auth_with_email = authenticate(request=request, email=email, password=password)
            auth_with_username = authenticate(request=request, username=email, password=password)
            
            return JsonResponse({
                'user_exists': user_exists,
                'has_password': has_password,
                'auth_with_email': bool(auth_with_email),
                'auth_with_username': bool(auth_with_username),
                'debug_info': {
                    'email': email,
                    'password_length': len(password) if password else 0
                }
            })
        except Exception as e:
            return JsonResponse({'error': str(e)})
    
    return JsonResponse({'error': 'Invalid request method'})



class PublicCourseDetailView(generics.RetrieveAPIView):
    """
    API endpoint for retrieving public course details.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CourseDetailSerializer
    queryset = Course.objects.all()
    lookup_field = 'id'
    
    @swagger_auto_schema(
        operation_summary="Get public course details",
        operation_description="Retrieves detailed information about a course for public viewing",
        responses={
            status.HTTP_200_OK: CourseDetailSerializer(),
            status.HTTP_404_NOT_FOUND: "Course not found"
        }
    )
    def get(self, request, *args, **kwargs):
        try:
            course = self.get_object()
            serializer = self.get_serializer(course)
            
            # Get related courses from the same category
            related_courses = Course.objects.filter(
                category=course.category
            ).exclude(
                id=course.id
            ).order_by('-is_featured', '-date_uploaded')[:4]
            
            related_serializer = CourseDetailSerializer(
                related_courses, 
                many=True, 
                context={'request': request}
            )
            
            # Get category details
            category_serializer = CategorySerializer(course.category)
            
            # Combine data
            data = serializer.data
            data['category_details'] = category_serializer.data
            data['related_courses'] = related_serializer.data
            
            return Response(data)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found"},
                status=status.HTTP_404_NOT_FOUND
            )
class CourseObjectiveViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing course objectives.
    """
    serializer_class = CourseObjectiveSerializer
    permission_classes = []
    
    def get_queryset(self):
        """
        Filter objectives by course.
        """
        course_pk = self.kwargs.get('course_pk')
        if course_pk:
            return CourseObjective.objects.filter(course_id=course_pk)
        return CourseObjective.objects.none()
    
    def list(self, request, course_pk=None, *args, **kwargs):
        # Check if course exists
        try:
            course = Course.objects.get(pk=course_pk)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def create(self, request, course_pk=None, *args, **kwargs):
        # Check if course exists
        try:
            course = Course.objects.get(pk=course_pk)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        # Create serializer with data
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Set the course for the new objective
        objective = serializer.save(course=course)
        
        return Response(
            self.get_serializer(objective).data,
            status=status.HTTP_201_CREATED
        )
    
    def retrieve(self, request, course_pk=None, pk=None, *args, **kwargs):
        try:
            objective = CourseObjective.objects.get(course_id=course_pk, pk=pk)
        except CourseObjective.DoesNotExist:
            return Response(
                {"error": "Objective not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        serializer = self.get_serializer(objective)
        return Response(serializer.data)
    
    def update(self, request, course_pk=None, pk=None, *args, **kwargs):
        try:
            objective = CourseObjective.objects.get(course_id=course_pk, pk=pk)
        except CourseObjective.DoesNotExist:
            return Response(
                {"error": "Objective not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        serializer = self.get_serializer(objective, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)
    
    def partial_update(self, request, course_pk=None, pk=None, *args, **kwargs):
        try:
            objective = CourseObjective.objects.get(course_id=course_pk, pk=pk)
        except CourseObjective.DoesNotExist:
            return Response(
                {"error": "Objective not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        serializer = self.get_serializer(objective, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)
    
    def destroy(self, request, course_pk=None, pk=None, *args, **kwargs):
        try:
            objective = CourseObjective.objects.get(course_id=course_pk, pk=pk)
        except CourseObjective.DoesNotExist:
            return Response(
                {"error": "Objective not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        objective.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class CourseRequirementViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing course requirements.
    """
    serializer_class = CourseRequirementSerializer
    permission_classes = []
    
    def get_queryset(self):
        """
        Filter requirements by course.
        """
        course_pk = self.kwargs.get('course_pk')
        if course_pk:
            return CourseRequirement.objects.filter(course_id=course_pk)
        return CourseRequirement.objects.none()
    
    def list(self, request, course_pk=None, *args, **kwargs):
        # Check if course exists
        try:
            course = Course.objects.get(pk=course_pk)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def create(self, request, course_pk=None, *args, **kwargs):
        # Check if course exists
        try:
            course = Course.objects.get(pk=course_pk)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        # Create serializer with data
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Set the course for the new requirement
        requirement = serializer.save(course=course)
        
        return Response(
            self.get_serializer(requirement).data,
            status=status.HTTP_201_CREATED
        )
    
    def retrieve(self, request, course_pk=None, pk=None, *args, **kwargs):
        try:
            requirement = CourseRequirement.objects.get(course_id=course_pk, pk=pk)
        except CourseRequirement.DoesNotExist:
            return Response(
                {"error": "Requirement not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        serializer = self.get_serializer(requirement)
        return Response(serializer.data)
    
    def update(self, request, course_pk=None, pk=None, *args, **kwargs):
        try:
            requirement = CourseRequirement.objects.get(course_id=course_pk, pk=pk)
        except CourseRequirement.DoesNotExist:
            return Response(
                {"error": "Requirement not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        serializer = self.get_serializer(requirement, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)
    
    def partial_update(self, request, course_pk=None, pk=None, *args, **kwargs):
        try:
            requirement = CourseRequirement.objects.get(course_id=course_pk, pk=pk)
        except CourseRequirement.DoesNotExist:
            return Response(
                {"error": "Requirement not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        serializer = self.get_serializer(requirement, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)
    
    def destroy(self, request, course_pk=None, pk=None, *args, **kwargs):
        try:
            requirement = CourseRequirement.objects.get(course_id=course_pk, pk=pk)
        except CourseRequirement.DoesNotExist:
            return Response(
                {"error": "Requirement not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        requirement.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class CourseCurriculumViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing course curriculum items.
    """
    serializer_class = CourseCurriculumSerializer
    permission_classes = [permissions.AllowAny]
    
    # def get_permissions(self):
    #     """
    #     Allow enrolled users to view, require admin for write operations
    #     """
    #     if self.action in ['list', 'retrieve']:
    #         return [IsEnrolledOrAdmin()]
    #     return [permissions.IsAuthenticated(), permissions.IsAdminUser()]
    
    
    def get_queryset(self):
        """
        Filter curriculum items by course.
        """
        course_pk = self.kwargs.get('course_pk')
        if course_pk:
            return CourseCurriculum.objects.filter(course_id=course_pk).order_by('order')
        return CourseCurriculum.objects.none()
    
    def list(self, request, course_pk=None, *args, **kwargs):
        # Check if course exists
        try:
            course = Course.objects.get(pk=course_pk)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def create(self, request, course_pk=None, *args, **kwargs):
        # Check if course exists
        try:
            course = Course.objects.get(pk=course_pk)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        # Add course to data
        data = request.data.copy() if hasattr(request.data, 'copy') else request.data.copy()
        
        # Set order if not provided
        if 'order' not in data:
            # Get the next order value
            next_order = CourseCurriculum.objects.filter(course_id=course_pk).count() + 1
            data['order'] = next_order
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        
        # Set the course for the new curriculum item
        item = serializer.save(course=course)
        
        return Response(
            self.get_serializer(item).data,
            status=status.HTTP_201_CREATED
        )
    
    def retrieve(self, request, course_pk=None, pk=None, *args, **kwargs):
        try:
            item = CourseCurriculum.objects.get(course_id=course_pk, pk=pk)
        except CourseCurriculum.DoesNotExist:
            return Response(
                {"error": "Curriculum item not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        serializer = self.get_serializer(item)
        return Response(serializer.data)
    
    def update(self, request, course_pk=None, pk=None, *args, **kwargs):
        try:
            item = CourseCurriculum.objects.get(course_id=course_pk, pk=pk)
        except CourseCurriculum.DoesNotExist:
            return Response(
                {"error": "Curriculum item not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        serializer = self.get_serializer(item, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)
    
    def partial_update(self, request, course_pk=None, pk=None, *args, **kwargs):
        try:
            item = CourseCurriculum.objects.get(course_id=course_pk, pk=pk)
        except CourseCurriculum.DoesNotExist:
            return Response(
                {"error": "Curriculum item not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        serializer = self.get_serializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)
    
    def destroy(self, request, course_pk=None, pk=None, *args, **kwargs):
        try:
            item = CourseCurriculum.objects.get(course_id=course_pk, pk=pk)
        except CourseCurriculum.DoesNotExist:
            return Response(
                {"error": "Curriculum item not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        # Get the order of the deleted item
        order = item.order
        
        # Delete the item
        item.delete()
        
        # Update the order of remaining items
        with transaction.atomic():
            remaining_items = CourseCurriculum.objects.filter(
                course_id=course_pk, 
                order__gt=order
            ).order_by('order')
            
            for remaining_item in remaining_items:
                remaining_item.order -= 1
                remaining_item.save()
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    def reorder(self, request, course_pk=None, *args, **kwargs):
        # Check if course exists
        try:
            course = Course.objects.get(pk=course_pk)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get items to reorder
        items_data = request.data.get('items', [])
        if not items_data:
            return Response(
                {"error": "No items provided for reordering"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update order
        with transaction.atomic():
            for item_data in items_data:
                item_id = item_data.get('id')
                new_order = item_data.get('order')
                
                if not item_id or new_order is None:
                    return Response(
                        {"error": "Each item must have 'id' and 'order' fields"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                try:
                    item = CourseCurriculum.objects.get(pk=item_id, course_id=course_pk)
                    item.order = new_order
                    item.save()
                except CourseCurriculum.DoesNotExist:
                    return Response(
                        {"error": f"Curriculum item with ID {item_id} not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
        
        # Return the updated items
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    
class CoursePurchaseView(generics.CreateAPIView):
    """
    API endpoint for purchasing courses with Razorpay payment verification.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    class InputSerializer(serializers.Serializer):
        course_id = serializers.IntegerField()
        plan_type = serializers.ChoiceField(choices=CoursePlanType.choices)
        razorpay_payment_id = serializers.CharField()
        razorpay_order_id = serializers.CharField()
        razorpay_signature = serializers.CharField()
        payment_card_id = serializers.IntegerField(required=False, allow_null=True)
        
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
        operation_summary="Purchase a course",
        operation_description="""
        Purchase a course with Razorpay payment verification.
        
        This endpoint:
        1. Verifies the Razorpay payment signature
        2. Creates a Purchase record with COMPLETED status
        3. Creates/updates Enrollment for the course with selected plan
        4. Updates PaymentOrder status or creates new one
        5. Creates notifications for purchase and enrollment
        6. Schedules enrollment expiry reminder (3 days before) for non-lifetime plans
        
        Payment flow:
        1. Create order using /payments/create-order/
        2. Process payment on frontend with Razorpay
        3. Call this endpoint with payment details to complete purchase
        """,
        request_body=InputSerializer,
        responses={
            status.HTTP_201_CREATED: openapi.Response(
                description="Course purchased successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'message': openapi.Schema(type=openapi.TYPE_STRING),
                                'purchase': openapi.Schema(type=openapi.TYPE_OBJECT),
                                'enrollment': openapi.Schema(type=openapi.TYPE_OBJECT),
                                'payment_order_id': openapi.Schema(type=openapi.TYPE_INTEGER)
                            }
                        )
                    }
                )
            ),
            status.HTTP_400_BAD_REQUEST: "Invalid request data or payment verification failed"
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Extract validated data
        course_id = serializer.validated_data['course_id']
        plan_type = serializer.validated_data['plan_type']
        payment_card_id = serializer.validated_data.get('payment_card_id')  # Use .get() to handle None
        razorpay_payment_id = serializer.validated_data['razorpay_payment_id']
        razorpay_order_id = serializer.validated_data['razorpay_order_id']
        razorpay_signature = serializer.validated_data['razorpay_signature']
        
        
        
        
        try:
            # Get objects
            # Get objects
            course = Course.objects.get(pk=course_id)
            
            # Only try to get payment card if an ID was provided
            payment_card = None
            if payment_card_id:
                try:
                    payment_card = PaymentCard.objects.get(pk=payment_card_id)
                    # Verify payment card belongs to user if provided
                    if payment_card.user != request.user:
                        return Response(
                            {'error': 'Payment card does not belong to you'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                except PaymentCard.DoesNotExist:
                    return Response(
                        {'error': 'Payment card not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            
            with transaction.atomic():
                result = process_course_purchase(
                    user=request.user,
                    course=course,
                    plan_type=plan_type,
                    razorpay_payment_id=razorpay_payment_id,
                    razorpay_order_id=razorpay_order_id,
                    razorpay_signature=razorpay_signature,
                    payment_card=payment_card
                )
            
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
                'payment_order_id': result['payment_order'].id
            }
            
            
            return Response({"success": True, "data": response_data}, status=status.HTTP_201_CREATED)
            
        except Course.DoesNotExist:
            return Response(
                {'error': 'Course not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except PaymentCard.DoesNotExist:
            return Response(
                {'error': 'Payment card not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as ve:
            # Payment verification failed
            return Response(
                {'error': str(ve)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Course purchase failed: {str(e)}")
            return Response(
                {'error': 'Purchase failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
class ProfilePictureUploadView(generics.UpdateAPIView):
    """
    API endpoint for uploading user profile picture.
    Backend handles all file processing, validation, and storage.
    """
    serializer_class = UserProfilePictureUploadSerializer
    parser_classes = [MultiPartParser, FormParser]  # Handles file uploads
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    def process_uploaded_image(self, uploaded_file):
        """
        Backend processing of uploaded image:
        1. Validates file
        2. Resizes image if needed
        3. Converts to optimized format
        4. Generates unique filename
        5. Saves to storage (S3 or local)
        """
        try:
            # Open image using PIL
            image = Image.open(uploaded_file)
            
            # Convert to RGB if necessary (handles RGBA, P mode images)
            if image.mode in ('RGBA', 'P'):
                # Create white background
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            
            # Resize image if too large (maintain aspect ratio)
            max_size = (800, 800)  # Max 800x800 pixels
            if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Generate unique filename
            unique_id = uuid.uuid4().hex
            filename = f"profile_pictures/{unique_id}.jpg"
            
            # Save processed image to BytesIO
            output = BytesIO()
            image.save(output, format='JPEG', quality=90, optimize=True)
            output.seek(0)
            
            # Create ContentFile for Django storage
            content_file = ContentFile(output.read(), name=filename)
            
            logger.info(f"Processed image for user {self.request.user.id}: {filename}")
            return content_file, filename
            
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            raise serializers.ValidationError(f"Error processing image: {str(e)}")
    
    def patch(self, request, *args, **kwargs):
        """
        Backend handles the entire upload process:
        1. Receives multipart file
        2. Validates file
        3. Processes and optimizes image
        4. Deletes old profile picture
        5. Saves new file to storage
        6. Updates user record
        7. Returns secure URL
        """
        user = self.get_object()
        
        # Check if file was uploaded
        if 'profile_picture' not in request.FILES:
            return Response(
                {'error': 'No file uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        uploaded_file = request.FILES['profile_picture']
        
        # Backend validation
        try:
            # Process the uploaded image
            processed_file, filename = self.process_uploaded_image(uploaded_file)
            
            # Delete old profile picture if exists
            if user.profile_picture:
                old_file_path = user.profile_picture.name
                if default_storage.exists(old_file_path):
                    default_storage.delete(old_file_path)
                    logger.info(f"Deleted old profile picture: {old_file_path}")
            
            # Save new processed file
            saved_path = default_storage.save(filename, processed_file)
            
            # Update user profile picture field
            user.profile_picture = saved_path
            user.save()
            
            logger.info(f"Profile picture saved for user {user.id}: {saved_path}")
            
            # Generate secure URL for response
            profile_picture_url = user.get_profile_picture_url()
            
            return Response({
                'message': 'Profile picture uploaded and processed successfully',
                'profile_picture_url': profile_picture_url,
                'file_size': default_storage.size(saved_path),
                'file_path': saved_path
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Upload failed for user {user.id}: {str(e)}")
            return Response(
                {'error': f'Upload failed: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

class ProfilePictureRetrieveView(generics.RetrieveAPIView):
    """
    API endpoint for retrieving user profile picture.
    """
    serializer_class = UserProfilePictureSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    @swagger_auto_schema(
        operation_summary="Get profile picture",
        operation_description="Retrieve the authenticated user's profile picture URL.",
        responses={
            status.HTTP_200_OK: UserProfilePictureSerializer(),
            status.HTTP_404_NOT_FOUND: "Profile picture not found"
        }
    )
    def get(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(user)
        return Response(serializer.data)

class ProfilePictureDeleteView(generics.DestroyAPIView):
    """
    API endpoint for deleting user profile picture.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    @swagger_auto_schema(
        operation_summary="Delete profile picture",
        operation_description="Delete the authenticated user's profile picture.",
        responses={
            status.HTTP_204_NO_CONTENT: "Profile picture deleted successfully",
            status.HTTP_404_NOT_FOUND: "Profile picture not found"
        }
    )
    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        
        if user.profile_picture:
            # Delete the file
            user.profile_picture.delete(save=True)
            return Response(
                {'message': 'Profile picture deleted successfully'}, 
                status=status.HTTP_204_NO_CONTENT
            )
        else:
            return Response(
                {'error': 'No profile picture found'}, 
                status=status.HTTP_404_NOT_FOUND
            )

class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    API endpoint for retrieving and updating user profile with profile picture.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def get_object(self):
        return self.request.user
    
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return UserDetailsSerializer
        return UserProfilePictureUploadSerializer
    
    @swagger_auto_schema(
        operation_summary="Get user profile",
        operation_description="Retrieve complete user profile including profile picture.",
        responses={
            status.HTTP_200_OK: UserDetailsSerializer()
        }
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_summary="Update user profile with picture",
        operation_description="Update user profile including profile picture upload.",
        manual_parameters=[
            openapi.Parameter(
                'profile_picture', 
                openapi.IN_FORM, 
                description="Profile picture file (optional)", 
                type=openapi.TYPE_FILE,
                required=False
            )
        ],
        responses={
            status.HTTP_200_OK: UserDetailsSerializer(),
            status.HTTP_400_BAD_REQUEST: "Invalid data"
        }
    )
    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        
        # Handle profile picture upload if provided
        if 'profile_picture' in request.data:
            pic_serializer = UserProfilePictureUploadSerializer(
                user, 
                data={'profile_picture': request.data['profile_picture']}, 
                partial=True
            )
            pic_serializer.is_valid(raise_exception=True)
            pic_serializer.save()
        
        # Handle other profile fields
        other_data = {k: v for k, v in request.data.items() if k != 'profile_picture'}
        if other_data:
            profile_serializer = UserDetailsSerializer(user, data=other_data, partial=True)
            profile_serializer.is_valid(raise_exception=True)
            profile_serializer.save()
        
        # Return updated profile
        return Response(
            UserDetailsSerializer(user).data,
            status=status.HTTP_200_OK
        )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def debug_enrollments(request):
    try:
        enrollments = Enrollment.objects.filter(user=request.user)
        return Response({
            "count": enrollments.count(),
            "user_id": request.user.id,
            "status": "success"
        })
    except Exception as e:
        return Response({
            "error": str(e),
            "error_type": type(e).__name__,
            "user_id": request.user.id
        })
