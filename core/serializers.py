from datetime import timezone
import os
from rest_framework import serializers
from django.contrib.auth import get_user_model
from allauth.account.adapter import get_adapter
from allauth.account.utils import setup_user_email
from dj_rest_auth.registration.serializers import RegisterSerializer

from core.s3_utils import generate_presigned_url, is_s3_url
from .models import (Category, ContentPage, Course, CourseObjective, CoursePlanType, CourseRequirement, CourseCurriculum, Enrollment, FCMDevice, GeneralSettings, Notification, PaymentOrder, 
                     SubscriptionPlan, PlanFeature, UserSubscription, 
                    Wishlist, PaymentCard, Purchase
                    )
from django.db import transaction
from django.contrib.auth import authenticate
from dj_rest_auth.serializers import LoginSerializer as BaseLoginSerializer
import json
import logging

logger = logging.getLogger(__name__)

User = get_user_model()



class AdminAddStudentSerializer(serializers.Serializer):
    """Serializer for admin adding student to subscription plan"""
    user_id = serializers.IntegerField(help_text="ID of the user to enroll")
    course_id = serializers.IntegerField(help_text="ID of the course to enroll in")
    plan_type = serializers.ChoiceField(
        choices=CoursePlanType.choices,
        help_text="Subscription plan type"
    )
    amount_paid = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        required=False,
        help_text="Amount paid (optional - will use course price if not provided)"
    )
    payment_card_id = serializers.IntegerField(
        required=False, 
        allow_null=True,
        help_text="Payment card ID (optional)"
    )
    notes = serializers.CharField(
        max_length=500, 
        required=False, 
        allow_blank=True,
        help_text="Admin notes about this enrollment"
    )
    
    class Meta:
        ref_name = "AdminAddStudentSerializer"
        
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
        
        
class UserDetailsSerializer(serializers.ModelSerializer):
    profile_picture_url = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'phone_number', 'date_of_birth', 'profile_picture_url']
        read_only_fields = ['id', 'email']
    
    def get_profile_picture_url(self, obj):
        """
        Get the profile picture URL with presigned URL for S3
        """
        return obj.get_profile_picture_url()



class CustomLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(style={'input_type': 'password'})
    
    def authenticate(self, **kwargs):
        return authenticate(self.context['request'], **kwargs)
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        # For debugging
        print(f"Login attempt with email: {email} {password}")
        
        if email and password:
            # First try with email parameter
            user = self.authenticate(email=email, password=password)
            
            # If that fails, try with username parameter (for compatibility)
            if user is None:
                user = self.authenticate(username=email, password=password)
            
            # If still no user, authentication failed
            if user is None:
                msg = 'Unable to log in with provided credentials.'
                raise serializers.ValidationError(msg, code='authorization')
            
            # If user is not active, authentication should fail
            if not user.is_active:
                msg = 'User account is disabled.'
                raise serializers.ValidationError(msg, code='authorization')
        else:
            msg = 'Must include "email" and "password".'
            raise serializers.ValidationError(msg, code='authorization')
        
        attrs['user'] = user
        return attrs
    
class CustomRegisterSerializer(serializers.Serializer):
    # Define all fields needed for registration
    email = serializers.EmailField(required=True)
    full_name = serializers.CharField(required=True)
    phone_number = serializers.CharField(required=True)
    password1 = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)
    
    def validate_email(self, email):
        print(f"Validating email: {email}")
        email = get_adapter().clean_email(email)
        print(f"Cleaned email: {email}")
        
        # Debug: list all existing emails in the database
        all_emails = User.objects.values_list('email', flat=True)
        print(f"All emails in DB: {list(all_emails)}")
        
        existing = User.objects.filter(email__iexact=email).exists()
        print(f"Existing user with this email? {existing}")
        
        if existing:
            raise serializers.ValidationError("A user is already registered with this email address.")
        return email
    
    def validate_password1(self, password):
        return get_adapter().clean_password(password)
    
    def validate(self, data):
        if data['password1'] != data['password2']:
            raise serializers.ValidationError(
                {"password2": "The two password fields didn't match."})
        return data
    
    def get_cleaned_data(self):
        return {
            'email': self.validated_data.get('email', ''),
            'password1': self.validated_data.get('password1', ''),
            'full_name': self.validated_data.get('full_name', ''),
            'phone_number': self.validated_data.get('phone_number', ''),
        }
    
    def save(self, request):
        print("save method called")
        adapter = get_adapter()
        user = adapter.new_user(request)
        self.cleaned_data = self.get_cleaned_data()
        
        # Set user fields
        user.email = self.cleaned_data.get('email')
        user.full_name = self.cleaned_data.get('full_name')
        user.phone_number = self.cleaned_data.get('phone_number')
        
        # Set password
        raw_password = self.cleaned_data.get('password1')
        print(f"Setting password from raw_password (length: {len(raw_password)})")
        user.set_password(raw_password)
        print(f"Password after set_password: {user.password[:10]}...")
        
        # Save user
        user.save()
        print(f"User saved with ID: {user.id}, email: {user.email}")
        
        # Setup email
        setup_user_email(request, user, [])
        
        return user
    
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'phone_number', 'date_of_birth']
        read_only_fields = ['id', 'email']
        
        
class CustomTokenSerializer(serializers.Serializer):
    key = serializers.CharField()
    user = UserSerializer()

class ForgotPasswordSerializer(serializers.Serializer):
    """Serializer for requesting password reset OTP"""
    email = serializers.EmailField()
    
    def validate_email(self, value):
        """Validate that the email exists"""
        if not User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("User with this email does not exist.")
        return value
    
class VerifyOTPSerializer(serializers.Serializer):
    """Serializer for verifying OTP only"""
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=4)
    
    def validate_email(self, value):
        """Validate that the email exists"""
        if not User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("User with this email does not exist.")
        return value
    
    
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'image_url', 'description']
        
class CourseObjectiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseObjective
        fields = ['id', 'description']
        extra_kwargs = {
            'id': {'read_only': True}
        }

class CourseRequirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseRequirement
        fields = ['id', 'description']
        extra_kwargs = {
            'id': {'read_only': True}
        }

class CourseCurriculumSerializer(serializers.ModelSerializer):
    video_url = serializers.SerializerMethodField()
    
    class Meta:
        model = CourseCurriculum
        fields = ['id', 'title', 'video_url', 'order']
        extra_kwargs = {
            'id': {'read_only': True}
        }
    
    def get_video_url(self, obj):
        """
        Generate a presigned URL for S3 videos - ALWAYS FRESH
        """
        url = obj.video_url
        if url and is_s3_url(url):
            # Use direct presigned URL generation (no caching)
            from core.s3_utils import generate_presigned_url
            return generate_presigned_url(url, expiration=43200)  # 12 hour expiration
        return url
    
    def to_representation(self, instance):
        """
        Override to_representation to ensure video_url is properly handled
        """
        ret = super().to_representation(instance)
        # Ensure video_url is properly returned even for write operations
        if 'video_url' in ret and ret['video_url'] is None:
            # If the URL is None in the database, return None
            ret['video_url'] = None
        return ret

    def to_internal_value(self, data):
        """
        Keep the original URL when saving to database
        """
        # Store the original URL in internal value - don't try to save presigned URL
        return super().to_internal_value(data)

class CourseListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    enrolled_students = serializers.SerializerMethodField()
    is_enrolled = serializers.SerializerMethodField()
    is_wishlisted = serializers.SerializerMethodField()
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'image', 'small_desc', 'description', 'category', 
            'category_name', 'is_featured', 'date_uploaded', 
            'location', 'enrolled_students', 'is_enrolled', 'is_wishlisted',
            'price_one_month', 'price_three_months', 'price_lifetime'
        ]
    
    def get_enrolled_students(self, obj):
        """Get total number of enrolled students"""
        try:
            # Use prefetched enrollments if available for performance
            if hasattr(obj, 'prefetched_objects_cache') and 'enrollments' in obj.prefetched_objects_cache:
                return len([e for e in obj.prefetched_objects_cache['enrollments'] if e.is_active])
            
            # Fallback to database query
            return obj.enrollments.filter(is_active=True).count()
        except Exception as e:
            logger.error(f"Error getting enrolled students count: {str(e)}")
            return 0
    
    def get_is_enrolled(self, obj):
        """
        FIXED: Check if user has an active, non-expired enrollment
        This is the same logic that works in featured/top courses
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
            
        try:
            # Use prefetched enrollments if available
            if hasattr(obj, 'prefetched_objects_cache') and 'enrollments' in obj.prefetched_objects_cache:
                enrollments = obj.prefetched_objects_cache['enrollments']
                for enrollment in enrollments:
                    if (enrollment.user_id == request.user.id and 
                        enrollment.is_active and 
                        not enrollment.is_expired):
                        return True
                return False
            
            # Fallback to database query - THIS IS THE CORRECT LOGIC
            enrollment = obj.enrollments.filter(
                user=request.user,
                is_active=True
            ).first()
            
            if not enrollment:
                return False
                
            # CRITICAL: Check if enrollment is expired
            return not enrollment.is_expired
            
        except Exception as e:
            logger.error(f"Error checking enrollment status: {str(e)}")
            return False
    
    def get_is_wishlisted(self, obj):
        """Check if course is in user's wishlist"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
            
        try:
            # Use prefetched wishlist if available
            if hasattr(obj, 'prefetched_objects_cache') and 'wishlisted_by' in obj.prefetched_objects_cache:
                wishlisted_by = obj.prefetched_objects_cache['wishlisted_by']
                return any(w.user_id == request.user.id for w in wishlisted_by)
            
            # Fallback to database query
            return obj.wishlisted_by.filter(user=request.user).exists()
        except Exception as e:
            logger.error(f"Error checking wishlist status: {str(e)}")
            return False


class CourseDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    enrolled_students = serializers.SerializerMethodField()
    objectives = CourseObjectiveSerializer(many=True, read_only=True)
    requirements = CourseRequirementSerializer(many=True, read_only=True)
    curriculum = CourseCurriculumSerializer(many=True, read_only=True)
    is_enrolled = serializers.SerializerMethodField()
    is_wishlisted = serializers.SerializerMethodField()
    user_enrollment = serializers.SerializerMethodField()
    enrollment_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'image', 'small_desc', 'description', 'category', 
            'category_name', 'is_featured', 'date_uploaded', 
            'location', 'enrolled_students', 'objectives',
            'requirements', 'curriculum', 'is_enrolled', 'is_wishlisted',
            'price_one_month', 'price_three_months', 'price_lifetime',
            'user_enrollment', 'enrollment_status'
        ]
    
    def get_enrolled_students(self, obj):
        """Get total number of enrolled students"""
        # Use prefetched enrollments if available for performance
        if hasattr(obj, 'prefetched_objects_cache') and 'enrollments' in obj.prefetched_objects_cache:
            return len([e for e in obj.prefetched_objects_cache['enrollments'] if e.is_active])
        
        # Fallback to database query
        return obj.enrollments.filter(is_active=True).count()
    
    def get_is_enrolled(self, obj):
        """Check if user has an active, non-expired enrollment"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
            
        try:
            # Use prefetched enrollments if available
            if hasattr(obj, 'prefetched_objects_cache') and 'enrollments' in obj.prefetched_objects_cache:
                enrollments = obj.prefetched_objects_cache['enrollments']
                for enrollment in enrollments:
                    if (enrollment.user_id == request.user.id and 
                        enrollment.is_active and 
                        not enrollment.is_expired):
                        return True
                return False
            
            # Fallback to database query
            enrollment = obj.enrollments.filter(
                user=request.user,
                is_active=True
            ).first()
            
            if not enrollment:
                return False
                
            return not enrollment.is_expired
            
        except Exception as e:
            logger.error(f"Error checking enrollment status: {str(e)}")
            return False
    
    def get_is_wishlisted(self, obj):
        """Check if course is in user's wishlist"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
            
        return obj.wishlisted_by.filter(user=request.user).exists()
    
    def get_user_enrollment(self, obj):
        """Get user's enrollment details if enrolled"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
            
        try:
            # Use prefetched enrollments if available
            if hasattr(obj, 'prefetched_objects_cache') and 'enrollments' in obj.prefetched_objects_cache:
                enrollments = obj.prefetched_objects_cache['enrollments']
                for enrollment in enrollments:
                    if enrollment.user_id == request.user.id:
                        return {
                            'id': enrollment.id,
                            'plan_type': enrollment.plan_type,
                            'plan_name': enrollment.get_plan_type_display(),
                            'expiry_date': enrollment.expiry_date,
                            'date_enrolled': enrollment.date_enrolled,
                            'amount_paid': enrollment.amount_paid,
                            'is_active': enrollment.is_active,
                            'is_expired': enrollment.is_expired
                        }
                return None
            
            # Fallback to database query
            enrollment = obj.enrollments.filter(user=request.user).first()
            if not enrollment:
                return None
                
            return {
                'id': enrollment.id,
                'plan_type': enrollment.plan_type,
                'plan_name': enrollment.get_plan_type_display(),
                'expiry_date': enrollment.expiry_date,
                'date_enrolled': enrollment.date_enrolled,
                'amount_paid': enrollment.amount_paid,
                'is_active': enrollment.is_active,
                'is_expired': enrollment.is_expired
            }
            
        except Exception as e:
            logger.error(f"Error getting user enrollment: {str(e)}")
            return None
    
    def get_enrollment_status(self, obj):
        """Get detailed enrollment status for authenticated users"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return {
                'status': 'unauthenticated',
                'message': 'User not authenticated'
            }
        
        try:
            # Get the user enrollment data
            enrollment_data = self.get_user_enrollment(obj)
            
            if not enrollment_data:
                return {
                    'status': 'not_enrolled',
                    'message': 'User is not enrolled in this course'
                }
            
            if not enrollment_data['is_active']:
                return {
                    'status': 'inactive',
                    'message': 'Enrollment is inactive'
                }
            
            if enrollment_data['is_expired']:
                return {
                    'status': 'expired',
                    'message': 'Enrollment has expired',
                    'expired_on': enrollment_data['expiry_date']
                }
            
            # Active and not expired
            return {
                'status': 'active',
                'message': 'User has active access to this course',
                'plan_type': enrollment_data['plan_type'],
                'plan_name': enrollment_data['plan_name'],
                'expires_on': enrollment_data['expiry_date'] if enrollment_data['plan_type'] != CoursePlanType.LIFETIME else None,
                'is_lifetime': enrollment_data['plan_type'] == CoursePlanType.LIFETIME
            }
            
        except Exception as e:
            logger.error(f"Error getting enrollment status: {str(e)}")
            return {
                'status': 'error',
                'message': 'Error checking enrollment status'
            }
class CourseCreateUpdateSerializer(serializers.ModelSerializer):
    objectives = CourseObjectiveSerializer(many=True, required=False)  # Change this to required=False
    requirements = CourseRequirementSerializer(many=True, required=False)  # Change this to required=False
    curriculum = CourseCurriculumSerializer(many=True, required=False) 
    
    class Meta:
        model = Course
        fields = [
            'title', 'image', 'small_desc', 'description', 'category', 
            'is_featured', 'location', 'objectives',
            'requirements', 'curriculum',
            # Add the three price fields
            'price_one_month', 'price_three_months', 'price_lifetime'
        ]
        # Define extra kwargs to handle required fields differently for creation vs update
        extra_kwargs = {
            'title': {'required': False},
            'small_desc': {'required': False},
            'description': {'required': False},
            'category': {'required': False},
            'image': {'required': False},
            'price_one_month': {'required': False},
            'price_three_months': {'required': False},
            'price_lifetime': {'required': False},
        }
    
    def to_internal_value(self, data):
        """
        Override to handle string JSON fields from form data.
        """
        # Create a mutable copy of the QueryDict if needed
        if hasattr(data, 'copy'):
            data = data.copy()
        
        # Extract and pre-process the related fields
        objectives_data = None
        requirements_data = None
        curriculum_data = None
        
        # Handle parsing for each related field
        for field in ['objectives', 'requirements', 'curriculum']:
            if field in data and isinstance(data[field], str):
                try:
                    # Skip empty values
                    if not data[field].strip():
                        if field == 'objectives':
                            objectives_data = []
                        elif field == 'requirements':
                            requirements_data = []
                        elif field == 'curriculum':
                            curriculum_data = []
                        data.pop(field)  # Remove from data to avoid validation errors
                        continue
                    
                    # Try to parse as JSON
                    parsed_value = json.loads(data[field])
                    
                    # Check for None or non-list values
                    if parsed_value is None:
                        if field == 'objectives':
                            objectives_data = []
                        elif field == 'requirements':
                            requirements_data = []
                        elif field == 'curriculum':
                            curriculum_data = []
                        data.pop(field)  # Remove from data to avoid validation errors
                    elif not isinstance(parsed_value, list):
                        raise serializers.ValidationError({field: "Must be a JSON array"})
                    else:
                        # Check if we have a nested array [[{...}]] instead of [{...}]
                        if len(parsed_value) > 0 and isinstance(parsed_value[0], list):
                            parsed_value = parsed_value[0]  # Unwrap the nested array
                        
                        # Store the parsed value in the corresponding variable
                        if field == 'objectives':
                            objectives_data = parsed_value
                        elif field == 'requirements':
                            requirements_data = parsed_value
                        elif field == 'curriculum':
                            curriculum_data = parsed_value
                        
                        print(f"Successfully parsed {field} to list of {len(parsed_value)} items")
                        
                        # Remove from data to avoid validation errors
                        data.pop(field)
                except json.JSONDecodeError as e:
                    print(f"Error parsing {field} as JSON: {e}")
                    raise serializers.ValidationError({field: f"Invalid JSON format: {str(e)}"})
        
        # Call the parent implementation to handle the rest of the fields
        try:
            print(f"Data before parent to_internal_value: {data}")
            value = super().to_internal_value(data)
            
            # Add the parsed related fields back
            if objectives_data is not None:
                value['objectives'] = objectives_data
            if requirements_data is not None:
                value['requirements'] = requirements_data
            if curriculum_data is not None:
                value['curriculum'] = curriculum_data
                
            return value
        except Exception as e:
            print(f"Error in parent to_internal_value: {e}")
            raise
    
    def validate(self, data):
        """
        Custom validation that enforces required fields only for creation, not updates.
        """
        # Check if this is an update or create operation
        is_update = self.instance is not None
        
        # For creation, validate that required fields are present
        if not is_update:
            required_fields = ['title', 'small_desc', 'category', 'description', 
                            'price_one_month', 'price_three_months', 'price_lifetime']
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                raise serializers.ValidationError(
                    {field: ["This field is required."] for field in missing_fields}
                )
            
            # For creation, image is required unless it's already in the instance
            if 'image' not in data and (not self.instance or not self.instance.image):
                raise serializers.ValidationError({'image': ["This field is required."]})
                    
            # For creation, ensure related fields are present and not empty
            for field in ['objectives', 'requirements', 'curriculum']:
                if field not in data or not data[field]:
                    raise serializers.ValidationError({field: [f"At least one {field[:-1]} is required."]})
        
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        objectives_data = validated_data.pop('objectives', [])
        requirements_data = validated_data.pop('requirements', [])
        curriculum_data = validated_data.pop('curriculum', [])
        
        # Log what we're going to create
        print(f"Creating course with: {validated_data}")
        print(f"Creating {len(objectives_data)} objectives")
        print(f"Creating {len(requirements_data)} requirements")
        print(f"Creating {len(curriculum_data)} curriculum items")
        
        # Create the course
        course = Course.objects.create(**validated_data)
        
        # Create objectives
        for objective_data in objectives_data:
            CourseObjective.objects.create(course=course, **objective_data)
        
        # Create requirements
        for requirement_data in requirements_data:
            CourseRequirement.objects.create(course=course, **requirement_data)
        
        # Create curriculum items
        for idx, curriculum_item_data in enumerate(curriculum_data):
            # Set order if not provided
            if 'order' not in curriculum_item_data:
                curriculum_item_data['order'] = idx + 1
            CourseCurriculum.objects.create(course=course, **curriculum_item_data)
        
        # Log the final counts
        print(f"Successfully created course ID: {course.id}")
        print(f"Created objectives: {course.objectives.count()}")
        print(f"Created requirements: {course.requirements.count()}")
        print(f"Created curriculum items: {course.curriculum.count()}")
        
        return course
    
    @transaction.atomic
    def update(self, instance, validated_data):
        print(f"Updating course with: {validated_data}")
        objectives_data = validated_data.pop('objectives', None)
        requirements_data = validated_data.pop('requirements', None)
        curriculum_data = validated_data.pop('curriculum', None)
        
        # Update course fields only if provided
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update objectives only if explicitly provided in the request
        if objectives_data is not None:
            print(f"Updating objectives with: {objectives_data}")
            instance.objectives.all().delete()
            for objective_data in objectives_data:
                CourseObjective.objects.create(course=instance, **objective_data)
        
        # Update requirements only if explicitly provided in the request
        if requirements_data is not None:
            print(f"Updating requirements with: {requirements_data}")
            instance.requirements.all().delete()
            for requirement_data in requirements_data:
                CourseRequirement.objects.create(course=instance, **requirement_data)
        
        # Update curriculum only if explicitly provided in the request
        if curriculum_data is not None:
            print(f"Updating curriculum with: {curriculum_data}")
            instance.curriculum.all().delete()
            for idx, curriculum_item_data in enumerate(curriculum_data):
                # Set order if not provided
                if 'order' not in curriculum_item_data:
                    curriculum_item_data['order'] = idx + 1
                CourseCurriculum.objects.create(course=instance, **curriculum_item_data)
        
        # Log the final counts after update
        print(f"Update complete for course ID: {instance.id}")
        print(f"Updated objectives: {instance.objectives.count()}")
        print(f"Updated requirements: {instance.requirements.count()}")
        print(f"Updated curriculum items: {instance.curriculum.count()}")
        
        return instance
    
    def validate_category(self, value):
        """
        Check that the category exists.
        """
        if value is None:
            return value
            
        try:
            category = Category.objects.get(pk=value.id if hasattr(value, 'id') else value)
            return category
        except Category.DoesNotExist:
            raise serializers.ValidationError("Category does not exist.")

class EnrollmentSerializer(serializers.ModelSerializer):
    course = CourseDetailSerializer(read_only=True)
    plan_name = serializers.CharField(source='get_plan_type_display', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Enrollment
        fields = ['id', 'course', 'date_enrolled', 'plan_type', 'plan_name', 
                 'expiry_date', 'amount_paid', 'is_active', 'is_expired']
        read_only_fields = ['date_enrolled', 'expiry_date', 'is_expired']
        
    def to_representation(self, instance):
        """
        OPTIMIZED: This will now use the prefetched course data
        instead of making additional database queries
        """
        representation = super().to_representation(instance)
        
        # The CourseDetailSerializer will automatically use the prefetched data
        # from select_related() and prefetch_related() in the ViewSet
        # No additional database queries will be triggered here
        
        return representation
        

class PlanFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanFeature
        fields = ['id', 'description']

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    features = PlanFeatureSerializer(many=True, read_only=True)
    
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'is_pro', 'amount', 'features']

class SubscriptionPlanCreateUpdateSerializer(serializers.ModelSerializer):
    features = PlanFeatureSerializer(many=True, required=False)
    
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'is_pro', 'amount', 'features']
    
    def create(self, validated_data):
        features_data = validated_data.pop('features', [])
        plan = SubscriptionPlan.objects.create(**validated_data)
        
        for feature_data in features_data:
            PlanFeature.objects.create(plan=plan, **feature_data)
        
        return plan
    
    def update(self, instance, validated_data):
        features_data = validated_data.pop('features', None)
        instance = super().update(instance, validated_data)
        
        if features_data is not None:
            instance.features.all().delete()
            for feature_data in features_data:
                PlanFeature.objects.create(plan=instance, **feature_data)
        
        return instance

class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    plan_amount = serializers.DecimalField(source='plan.amount', max_digits=10, decimal_places=2, read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = UserSubscription
        fields = ['id', 'plan', 'plan_name', 'plan_amount', 'start_date', 'end_date', 'is_active', 'is_expired']
        read_only_fields = ['start_date', 'is_expired']

class WishlistSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_image = serializers.ImageField(source='course.image', read_only=True)
    
    class Meta:
        model = Wishlist
        fields = ['id', 'course', 'course_title', 'course_image', 'date_added']
        read_only_fields = ['date_added']

class PaymentCardSerializer(serializers.ModelSerializer):
    card_number = serializers.CharField(write_only=True, required=False)
    cvv = serializers.CharField(write_only=True, required=False)
    class Meta:
        model = PaymentCard
        fields = [
            'id', 'card_type', 'last_four', 'card_holder_name', 
            'expiry_month', 'expiry_year', 'is_default',
            'card_number', 'cvv'  # Write-only fields
        ]
        extra_kwargs = {
            'last_four': {'read_only': True}
        }
    
    def validate_card_number(self, value):
        # Basic validation - you might want to add more checks
        if value and not value.isdigit():
            raise serializers.ValidationError("Card number must contain only digits")
        
        if value and len(value) < 13 or len(value) > 19:
            raise serializers.ValidationError("Card number must be between 13 and 19 digits")
        
        return value
    
    def validate_cvv(self, value):
        if value and not value.isdigit():
            raise serializers.ValidationError("CVV must contain only digits")
        
        if value and len(value) < 3 or len(value) > 4:
            raise serializers.ValidationError("CVV must be 3 or 4 digits")
        
        return value
    
    def create(self, validated_data):
        # Extract and remove write-only fields
        card_number = validated_data.pop('card_number', None)
        cvv = validated_data.pop('cvv', None)
        
        # Set last_four from the card number
        if card_number:
            validated_data['last_four'] = card_number[-4:]
        
        # Create the payment card
        payment_card = super().create(validated_data)
        
        return payment_card

class PurchaseSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_image = serializers.ImageField(source='course.image', read_only=True)
    plan_name = serializers.CharField(source='get_plan_type_display', read_only=True)
    card_last_four = serializers.CharField(source='payment_card.last_four', read_only=True)
    
    class Meta:
        model = Purchase
        fields = [
            'id', 'course', 'course_title', 'course_image',
            'plan_type', 'plan_name', 
            'payment_card', 'card_last_four', 
            'amount', 'purchase_date', 'transaction_id', 'payment_status',
            'razorpay_order_id', 'razorpay_payment_id'
        ]
        read_only_fields = ['purchase_date', 'transaction_id', 'payment_status',
                          'razorpay_order_id', 'razorpay_payment_id']
        
# Update UserSerializer to include date_of_birth
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'phone_number', 'date_of_birth']
        read_only_fields = ['id', 'email']

# Update CourseListSerializer and CourseDetailSerializer to include enrollment and wishlist status

    

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'notification_type', 'is_seen', 'created_at']
        read_only_fields = ['title', 'message', 'notification_type', 'created_at']
        
class FCMDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = FCMDevice
        fields = ['id', 'registration_id', 'device_id', 'active']
        extra_kwargs = {
            'registration_id': {'write_only': True}
        }
        
class ContentPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentPage
        fields = ['id', 'page_type', 'content', 'last_updated']
        read_only_fields = ['last_updated']

class GeneralSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneralSettings
        fields = ['id', 'company_name', 'contact_email', 'contact_phone', 'address', 'last_updated']
        read_only_fields = ['id', 'last_updated']

class AdminMetricsSerializer(serializers.Serializer):
    total_courses = serializers.IntegerField(read_only=True)
    total_students = serializers.IntegerField(read_only=True)
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    # For the graphs
    student_registration_data = serializers.DictField(read_only=True)
    course_popularity = serializers.ListField(read_only=True)
    
    
class PaymentOrderSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    
    class Meta:
        model = PaymentOrder
        fields = [
            'id', 'course', 'course_title', 'plan', 'plan_name', 
            'amount', 'razorpay_order_id', 'razorpay_payment_id',
            'razorpay_signature', 'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['razorpay_order_id', 'status', 'created_at', 'updated_at']
        
class CreateOrderSerializer(serializers.Serializer):
    course_id = serializers.IntegerField()
    plan_type = serializers.ChoiceField(choices=CoursePlanType.choices)
    payment_card_id = serializers.IntegerField(required=False, allow_null=True)
    
    class Meta:
        # Adding a ref_name to avoid conflicts
        ref_name = "CreateOrderSerializer"
    
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

class VerifyPaymentSerializer(serializers.Serializer):
    razorpay_payment_id = serializers.CharField()
    razorpay_order_id = serializers.CharField()
    razorpay_signature = serializers.CharField()



class PurchaseCourseSerializer(serializers.Serializer):
    course_id = serializers.IntegerField()
    plan_id = serializers.IntegerField()
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
    
    def validate_plan_id(self, value):
        try:
            SubscriptionPlan.objects.get(pk=value)
            return value
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError("Subscription plan does not exist")
    
    # def validate_payment_card_id(self, value):
    #     if value is None:
    #         return None
    #     try:
    #         PaymentCard.objects.get(pk=value)
    #         return value
    #     except PaymentCard.DoesNotExist:
    #         raise serializers.ValidationError("Payment card does not exist")
    
    
    
class UserProfilePictureSerializer(serializers.ModelSerializer):
    profile_picture_url = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'profile_picture', 'profile_picture_url']
        extra_kwargs = {
            'profile_picture': {'write_only': True}
        }
    
    def get_profile_picture_url(self, obj):
        """
        Get the profile picture URL with presigned URL for S3
        """
        return obj.get_profile_picture_url()

class UserProfilePictureUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['profile_picture']
    
    def validate_profile_picture(self, value):
        """
        Backend validation of uploaded file
        """
        # File size validation (5MB limit)
        max_size = 5 * 1024 * 1024  # 5MB
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File size {value.size} bytes exceeds maximum allowed size of {max_size} bytes (5MB)"
            )
        
        # File type validation
        allowed_mime_types = [
            'image/jpeg', 
            'image/jpg', 
            'image/png', 
            'image/gif', 
            'image/webp'
        ]
        
        if value.content_type not in allowed_mime_types:
            raise serializers.ValidationError(
                f"Unsupported file type: {value.content_type}. "
                f"Allowed types: {', '.join(allowed_mime_types)}"
            )
        
        # Validate that it's actually an image
        try:
            from PIL import Image
            # Try to open the image to ensure it's valid
            img = Image.open(value)
            img.verify()  # Verify it's a valid image
            value.seek(0)  # Reset file pointer after verification
        except Exception as e:
            raise serializers.ValidationError(f"Invalid image file: {str(e)}")
        
        # File name validation
        if not value.name:
            raise serializers.ValidationError("File must have a name")
        
        # Check for potentially dangerous file extensions
        dangerous_extensions = ['.php', '.asp', '.jsp', '.exe', '.bat', '.sh']
        file_extension = os.path.splitext(value.name)[1].lower()
        if file_extension in dangerous_extensions:
            raise serializers.ValidationError(f"File extension {file_extension} not allowed")
        
        return value
    
class ResetPasswordSerializer(serializers.Serializer):
    """Serializer for resetting password with verified OTP"""
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=4)
    new_password = serializers.CharField(min_length=8)
    confirm_password = serializers.CharField(min_length=8)
    
    def validate_email(self, value):
        """Validate that the email exists"""
        if not User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("User with this email does not exist.")
        return value
    
    def validate(self, data):
        """Validate that passwords match"""
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data
    
    def validate_otp(self, value):
        """Basic OTP validation"""
        if not value.isdigit():
            raise serializers.ValidationError("OTP must contain only numbers.")
        return value
    
class FirebaseAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField(required=True)
    
    
class StudentEnrollmentDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for student enrollments with course info"""
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_image = serializers.ImageField(source='course.image', read_only=True)
    course_category = serializers.CharField(source='course.category.name', read_only=True)
    course_location = serializers.CharField(source='course.location', read_only=True)
    plan_name = serializers.CharField(source='get_plan_type_display', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    days_remaining = serializers.SerializerMethodField()
    enrollment_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Enrollment
        fields = [
            'id', 'course', 'course_title', 'course_image', 'course_category', 
            'course_location', 'date_enrolled', 'plan_type', 'plan_name', 
            'expiry_date', 'amount_paid', 'is_active', 'is_expired', 
            'days_remaining', 'enrollment_status'
        ]
    
    def get_days_remaining(self, obj):
        """Calculate days remaining until expiry"""
        if obj.plan_type == 'LIFETIME':
            return None  # Lifetime access
        
        if not obj.expiry_date:
            return None
        
        from django.utils import timezone
        now = timezone.now()
        
        if obj.expiry_date <= now:
            return 0  # Already expired
        
        delta = obj.expiry_date - now
        return delta.days
    
    def get_enrollment_status(self, obj):
        """Get detailed enrollment status"""
        if not obj.is_active:
            return {
                'status': 'inactive',
                'message': 'Enrollment is inactive',
                'color': 'red'
            }
        
        if obj.is_expired:
            return {
                'status': 'expired',
                'message': 'Enrollment has expired',
                'color': 'red'
            }
        
        if obj.plan_type == 'LIFETIME':
            return {
                'status': 'active_lifetime',
                'message': 'Lifetime access',
                'color': 'green'
            }
        
        days_remaining = self.get_days_remaining(obj)
        if days_remaining is None:
            return {
                'status': 'active',
                'message': 'Active enrollment',
                'color': 'green'
            }
        
        if days_remaining <= 7:
            return {
                'status': 'expiring_soon',
                'message': f'Expires in {days_remaining} days',
                'color': 'orange'
            }
        
        return {
            'status': 'active',
            'message': f'Active - {days_remaining} days remaining',
            'color': 'green'
        }
        
class LightweightCourseSerializer(serializers.ModelSerializer):
    """Minimal course data for enrollment lists"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'image', 'small_desc', 'category_name'
        ]

class LightweightEnrollmentSerializer(serializers.ModelSerializer):
    """Optimized enrollment serializer with minimal nested data"""
    course = LightweightCourseSerializer(read_only=True)
    plan_name = serializers.CharField(source='get_plan_type_display', read_only=True)
    is_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = Enrollment
        fields = [
            'id', 'course', 'date_enrolled', 'plan_type', 'plan_name',
            'expiry_date', 'amount_paid', 'is_active', 'is_expired'
        ]
    
    def get_is_expired(self, obj):
        """Compute expiry without additional queries"""
        if obj.plan_type == 'LIFETIME':
            return False
        if not obj.expiry_date:
            return False
        return obj.expiry_date <= timezone.now()