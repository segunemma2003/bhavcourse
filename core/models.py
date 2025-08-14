import hashlib
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.utils import timezone
import random
import string
from datetime import timedelta
from django.core.cache import cache
from django.conf import settings
import logging
from .cache_manager import CacheManager

logger = logging.getLogger(__name__)

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    razorpay_customer_id = models.CharField(max_length=255, blank=True, null=True)
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    date_of_birth = models.DateField(null=True, blank=True)
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_expiry = models.DateTimeField(blank=True, null=True)
    
    # These fields are required for Django admin
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    
    # Remove duplicate profile_picture field - you had it twice
    profile_picture = models.ImageField(
        upload_to='profile_pictures/', 
        blank=True, 
        null=True,
        help_text="User's profile picture"
    )
    
    objects = CustomUserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name', 'phone_number']
    
    def generate_otp(self):
        otp = ''.join(random.choices(string.digits, k=4))
        self.otp = otp
        self.otp_expiry = timezone.now() + timezone.timedelta(minutes=10)
        self.save()
        return otp
    
    def clear_otp(self):
        """Clear OTP after successful password reset"""
        self.otp = None
        self.otp_expiry = None
        self.save()
    
    def get_profile_picture_url(self):
        """
        Generate a URL for the profile picture.
        If you're using S3, this will generate a presigned URL.
        If using local storage, returns the regular URL.
        """
        if self.profile_picture:
            # If you have S3 integration, uncomment these lines:
            # try:
            #     from core.s3_utils import generate_presigned_url, is_s3_url
            #     url = self.profile_picture.url
            #     if is_s3_url(url):
            #         return generate_presigned_url(url)
            #     return url
            # except ImportError:
            #     # Fallback if S3 utils not available
            #     return self.profile_picture.url
            
            # For now, return the regular URL
            return self.profile_picture.url
        return None
        
    def verify_otp(self, otp):
        if self.otp == otp and timezone.now() <= self.otp_expiry:
            self.otp = None
            self.otp_expiry = None
            self.save()
            return True
        return False
    
    class Meta:
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['is_active']),
            # Add these performance indexes
            models.Index(fields=['is_staff', 'is_superuser']),
            models.Index(fields=['date_joined']),
            models.Index(fields=['is_active', 'date_joined']),
        ]
        
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Clear user-related caches if profile updated - v8
        if not is_new:
            self._clear_user_caches()
            CacheManager.clear_user_cache(self.id)
    
    def delete(self, *args, **kwargs):
        user_id = self.id
        result = super().delete(*args, **kwargs)
        self._clear_user_caches_on_delete(user_id)
        CacheManager.clear_user_cache(user_id)
        CacheManager.clear_admin_cache()
        return result
    
    def _clear_user_caches(self):
        """Clear user-related caches - UPDATED TO v8"""
        try:
            cache_patterns = [
                f"enrollments_v8_{self.id}_list_true",
                f"enrollments_v8_{self.id}_list_false",
                f"enrollment_summary_v8_{self.id}",
                f"wishlist_v8_{self.id}",
                f"notifications_v8_{self.id}_all",
                f"notifications_v8_{self.id}_true",
                f"notifications_v8_{self.id}_false",
            ]
            
            # Clear admin caches that might include this user
            cache_patterns.extend([
                "admin_all_students_v8",  # Admin student lists
                f"admin_student_enrollments_v8_{self.id}",  # Admin enrollment details
            ])
            
            hashed_keys = [hashlib.md5(pattern.encode()).hexdigest() for pattern in cache_patterns]
            cache.delete_many(hashed_keys)
            
        except Exception as e:
            logger.warning(f"User cache clearing failed: {e}")
    
    @staticmethod
    def _clear_user_caches_on_delete(user_id):
        """Clear caches after user deletion - UPDATED TO v8"""
        cache_patterns = [
            f"enrollments_v8_{user_id}_list_true",
            f"enrollments_v8_{user_id}_list_false",
            f"enrollment_summary_v8_{user_id}",
            f"wishlist_v8_{user_id}",
            f"notifications_v8_{user_id}_all",
            f"notifications_v8_{user_id}_true",
            f"notifications_v8_{user_id}_false",
            f"admin_student_enrollments_v8_{user_id}",
             "admin_all_students_v8",
        ]
        
        hashed_keys = [hashlib.md5(pattern.encode()).hexdigest() for pattern in cache_patterns]
        cache.delete_many(hashed_keys)
class Category(models.Model):
    name = models.CharField(max_length=100)
    image_url = models.URLField(max_length=500)
    description = models.TextField()
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        # Clear category-related caches
        cache_patterns = [
            "categories_list_{}",
            f"category_detail_{self.id}",
        ]
        
        CacheManager.clear_cache_patterns(cache_patterns, "")
        
        # Also clear course caches since categories affect course listings
        CacheManager.clear_course_cache()
    
    def delete(self, *args, **kwargs):
        category_id = self.id
        result = super().delete(*args, **kwargs)
        
        # Clear all category and course caches
        cache_patterns = [
            "categories_list_{}",
            f"category_detail_{category_id}",
        ]
        
        CacheManager.clear_cache_patterns(cache_patterns, "")
        CacheManager.clear_course_cache()
        
        return result
    
    class Meta:
        verbose_name_plural = "Categories"

# Move CoursePlanType to the top so it can be referenced by other models
class CoursePlanType(models.TextChoices):
    ONE_MONTH = 'ONE_MONTH', 'One Month'
    THREE_MONTHS = 'THREE_MONTHS', 'Three Months'
    LIFETIME = 'LIFETIME', 'Lifetime'

class CourseObjective(models.Model):
    description = models.CharField(max_length=255)
    course = models.ForeignKey('Course', related_name='objectives', on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.course.title} - {self.description[:30]}"

class CourseRequirement(models.Model):
    description = models.CharField(max_length=255)
    course = models.ForeignKey('Course', related_name='requirements', on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.course.title} - {self.description[:30]}"

class CourseCurriculum(models.Model):
    title = models.CharField(max_length=500)
    video_url = models.TextField(blank=True, null=True)
    course = models.ForeignKey('Course', related_name='curriculum', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    
    # New fields for presigned URL management
    presigned_url = models.TextField(blank=True, help_text='Pre-generated presigned URL')
    presigned_expires_at = models.DateTimeField(null=True, blank=True, help_text='When presigned URL expires')
    url_generation_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('ready', 'Ready'),
            ('failed', 'Failed'),
            ('expired', 'Expired'),
            ('not_needed', 'Not Needed')  # For non-S3 URLs
        ],
        default='pending',
        help_text='Status of presigned URL generation'
    )
    generation_attempts = models.PositiveIntegerField(default=0)
    last_generation_attempt = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    
    def delete(self, *args, **kwargs):
        course_id = self.course_id
        result = super().delete(*args, **kwargs)
        
        # Clear course-related caches
        CacheManager.clear_course_cache(course_id)
        
        return result
    
    def save(self, *args, **kwargs):
        # Set status based on video_url
        if self.video_url:
            from core.s3_utils import is_s3_url
            if is_s3_url(self.video_url):
                if self.url_generation_status == 'pending':
                    # Keep pending status for new S3 URLs
                    pass
            else:
                # Non-S3 URLs don't need presigned generation
                self.url_generation_status = 'not_needed'
        else:
            self.url_generation_status = 'not_needed'
        
        super().save(*args, **kwargs)
        
        # Clear related caches
        
        self._clear_related_caches()
        CacheManager.clear_course_cache(self.course_id)
    
    def _clear_related_caches(self):
        """Clear caches related to this curriculum item - UPDATED TO v8"""
        try:
            # Clear course detail cache - v8
            cache.delete(f"course_detail_v8_{self.course_id}")
            
            # Clear course duration cache - v8
            cache.delete(f"course_duration_v8_{self.course_id}")
            
            # Clear enrollment caches for users enrolled in this course - v8
            enrollment_user_ids = Enrollment.objects.filter(
                course_id=self.course_id,
                is_active=True
            ).values_list('user_id', flat=True)[:100]  # Limit to prevent memory issues
            
            enrollment_cache_keys = []
            for user_id in enrollment_user_ids:
                enrollment_cache_keys.extend([
                    f"enrollments_v8_{user_id}_list_true",
                    f"enrollments_v8_{user_id}_list_false",
                    f"enrollment_summary_v8_{user_id}"
                ])
            
            # Hash and delete cache keys
            hashed_keys = [hashlib.md5(key.encode()).hexdigest() for key in enrollment_cache_keys]
            cache.delete_many(hashed_keys)
            
        except Exception as e:
            logger.warning(f"Cache clearing failed: {e}")
    
    @property
    def is_url_ready(self):
        """Check if presigned URL is ready and not expired"""
        return (
            self.url_generation_status == 'ready' and
            self.presigned_url and
            self.presigned_expires_at and
            self.presigned_expires_at > timezone.now()
        )
    
    class Meta:
        ordering = ['order']
        indexes = [
            models.Index(fields=['course', 'order']),
            models.Index(fields=['url_generation_status', 'presigned_expires_at']),
            models.Index(fields=['course', 'url_generation_status']),
            models.Index(fields=['presigned_expires_at']),
            models.Index(fields=['generation_attempts', 'url_generation_status']),
        ]
        
@receiver(post_save, sender=CourseCurriculum)
def handle_curriculum_save(sender, instance, created, **kwargs):
    """Trigger presigned URL generation for new S3 videos"""
    if instance.video_url and instance.url_generation_status == 'pending':
        from core.s3_utils import is_s3_url
        if is_s3_url(instance.video_url):
            # Queue for background processing
            from core.tasks import generate_presigned_url_async
            generate_presigned_url_async.apply_async(
                args=[instance.id],
                countdown=5  # Start after 5 seconds to avoid overwhelming
            )

class Course(models.Model):
    title = models.CharField(max_length=200)
    image = models.ImageField(upload_to='courses/')
    description = models.TextField(default="description")
    small_desc = models.CharField(max_length=255, default="description")
    category = models.ForeignKey(Category, related_name='courses', on_delete=models.CASCADE)
    is_featured = models.BooleanField(default=False)
    date_uploaded = models.DateTimeField(auto_now_add=True)
    location = models.CharField(max_length=100)
    price_one_month = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_three_months = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_lifetime = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    def __str__(self):
        return self.title
    
    @property
    def enrolled_students(self):
        """Get count of active enrollments"""
        return self.enrollments.filter(is_active=True).count()
    
    # Remove the is_expired property from Course model - it doesn't make sense here
    # as expiry is an enrollment property, not a course property
    
    class Meta:
        ordering = ['-date_uploaded']
        indexes = [
            models.Index(fields=['category', 'is_featured']),
            models.Index(fields=['is_featured', 'date_uploaded']),
            models.Index(fields=['category']),
            models.Index(fields=['date_uploaded']),
            # Add these performance indexes
            models.Index(fields=['category', 'date_uploaded']),
            models.Index(fields=['is_featured', 'category']),
            models.Index(fields=['date_uploaded', 'is_featured']),
        ]
        
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Clear course-related caches - v8
        self._clear_course_caches(is_new)
        CacheManager.clear_course_cache(self.id)
        
        if is_new:
            # Clear additional caches for new courses
            CacheManager.clear_admin_cache()
    
    def delete(self, *args, **kwargs):
        course_id = self.id
        result = super().delete(*args, **kwargs)
        self._clear_course_caches_on_delete(course_id)
        CacheManager.clear_course_cache(course_id)
        CacheManager.clear_admin_cache()
        return result
    
    def _clear_course_caches(self, is_new=False):
        """Clear course-related caches - UPDATED TO v8"""
        try:
            # Clear course detail caches
            cache.delete(f"course_detail_v8_{self.id}")
            cache.delete(f"course_duration_v8_{self.id}")
            
            # Clear course list caches (pattern-based)
            cache_patterns = [
                "courses_list_v8",  # All course list variations
                f"category_detail_v8_{self.category_id}" if self.category_id else "",
            ]
            
            # Clear category list cache
            cache_patterns.append("categories_list_v8")
            
            # If new course, clear admin caches
            if is_new:
                cache_patterns.extend([
                    "admin_all_students_v8",  # Admin views might be affected
                ])
            
            # Clear enrollment caches for users enrolled in this course
            if not is_new:  # Only for existing courses
                enrolled_user_ids = Enrollment.objects.filter(
                    course_id=self.id,
                    is_active=True
                ).values_list('user_id', flat=True)[:100]
                
                for user_id in enrolled_user_ids:
                    cache_patterns.extend([
                        f"enrollments_v8_{user_id}_list_true",
                        f"enrollments_v8_{user_id}_list_false",
                        f"enrollment_summary_v8_{user_id}"
                    ])
            
            # Hash and delete
            valid_patterns = [p for p in cache_patterns if p]  # Remove empty strings
            hashed_keys = [hashlib.md5(pattern.encode()).hexdigest() for pattern in valid_patterns]
            cache.delete_many(hashed_keys)
            
        except Exception as e:
            logger.warning(f"Course cache clearing failed: {e}")
    
    def _clear_course_caches_on_delete(self, course_id):
        """Clear caches after course deletion - UPDATED TO v8"""
        cache_patterns = [
            f"course_detail_v8_{course_id}",
            f"course_duration_v8_{course_id}",
            "courses_list_v8",
            "categories_list_v8",
        ]
        
        hashed_keys = [hashlib.md5(pattern.encode()).hexdigest() for pattern in cache_patterns]
        cache.delete_many(hashed_keys)

class Enrollment(models.Model):
    user = models.ForeignKey(User, related_name='enrollments', on_delete=models.CASCADE)
    course = models.ForeignKey(Course, related_name='enrollments', on_delete=models.CASCADE)
    date_enrolled = models.DateTimeField(auto_now_add=True)
    plan_type = models.CharField(
        max_length=20, 
        choices=CoursePlanType.choices, 
        default=CoursePlanType.ONE_MONTH
    )
    expiry_date = models.DateTimeField(null=True, blank=True)  # Null for lifetime plan
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['user', 'course']
        ordering = ['-date_enrolled']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['user', 'date_enrolled']),
            models.Index(fields=['course', 'is_active']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['plan_type']),
            models.Index(fields=['is_active', 'date_enrolled']),
            # Add these performance indexes
            models.Index(fields=['user', 'is_active', 'date_enrolled']),
            models.Index(fields=['is_active', 'expiry_date']),
            models.Index(fields=['user', 'course', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.course.title} - {self.get_plan_type_display()}"
    
    @property
    def is_expired(self):
        """
        Check if enrollment has expired.
        Lifetime enrollments never expire.
        """
        # Lifetime plans never expire
        if self.plan_type == CoursePlanType.LIFETIME:
            return False
        
        # If no expiry date is set, consider it not expired
        if not self.expiry_date:
            return False
        
        # Check if current time is past expiry date
        return timezone.now() > self.expiry_date
    
    def save(self, *args, **kwargs):
        """
        Override save to set expiry_date based on plan_type if not already set.
        """
        # Set expiry date if not already set and not lifetime plan
        if not self.expiry_date and self.plan_type != CoursePlanType.LIFETIME:
            # Use current time as base date for new enrollments
            base_date = timezone.now()
            
            if self.plan_type == CoursePlanType.ONE_MONTH:
                self.expiry_date = base_date + timezone.timedelta(days=30)
            elif self.plan_type == CoursePlanType.THREE_MONTHS:
                self.expiry_date = base_date + timezone.timedelta(days=90)
        
        super().save(*args, **kwargs)
        self._clear_enrollment_caches()
        CacheManager.clear_enrollment_cache(self.user_id, self.course_id)
    
    def delete(self, *args, **kwargs):
        user_id = self.user_id  # Store before deletion
        result = super().delete(*args, **kwargs)
        self._clear_enrollment_caches_for_user(user_id)
        CacheManager.clear_enrollment_cache(user_id, self.course_id)
        return result
    
    def _clear_enrollment_caches(self):
        """Clear cache for this enrollment's user"""
        self._clear_enrollment_caches_for_user(self.user_id)
    
    @staticmethod
    def _clear_enrollment_caches_for_user(user_id):
        """Clear all enrollment cache variations for a user - UPDATED TO v8"""
        cache_patterns = [
            f"enrollments_v8_{user_id}_list_true",
            f"enrollments_v8_{user_id}_list_false", 
            f"enrollment_summary_v8_{user_id}",
            f"enrollment_status_v8_{user_id}",  # Base pattern
        ]
        
        # Clear enrollment detail caches (reasonable range)
        for enrollment_id in range(1, 1000):
            cache_patterns.append(f"enrollment_detail_v8_{enrollment_id}")
        
        # Clear course-related caches that might be affected
        try:
            # Get course IDs for this user's enrollments
            course_ids = Enrollment.objects.filter(
                user_id=user_id
            ).values_list('course_id', flat=True)[:50]  # Limit
            
            for course_id in course_ids:
                cache_patterns.extend([
                    f"course_detail_v8_{course_id}_{user_id}",
                    f"course_duration_v8_{course_id}",
                ])
        except Exception:
            pass  # Don't break if this fails
        
        # Hash keys and clear in batches
        batch_size = 100
        for i in range(0, len(cache_patterns), batch_size):
            batch = cache_patterns[i:i + batch_size]
            hashed_keys = [hashlib.md5(pattern.encode()).hexdigest() for pattern in batch]
            cache.delete_many(hashed_keys)
    
    @staticmethod
    def clear_user_enrollment_caches(user_id):
        """Public method for external cache clearing"""
        Enrollment._clear_enrollment_caches_for_user(user_id)
    
    def get_days_remaining(self):
        """
        Get number of days remaining until expiry.
        Returns None for lifetime plans.
        Returns 0 if already expired.
        """
        if self.plan_type == CoursePlanType.LIFETIME:
            return None
        
        if not self.expiry_date:
            return None
        
        if self.is_expired:
            return 0
        
        delta = self.expiry_date - timezone.now()
        return max(0, delta.days)
    
    def extend_enrollment(self, additional_days):
        """Extend the enrollment by additional days."""
        if self.plan_type == CoursePlanType.LIFETIME:
            return  # Cannot extend lifetime plans
        
        if not self.expiry_date:
            self.expiry_date = timezone.now()
        
        self.expiry_date += timezone.timedelta(days=additional_days)
        self.save()
    
    def deactivate(self):
        """Deactivate the enrollment."""
        self.is_active = False
        self.save()
    
    def reactivate(self):
        """Reactivate the enrollment."""
        self.is_active = True
        self.save()

class PlanFeature(models.Model):
    description = models.CharField(max_length=255)
    plan = models.ForeignKey('SubscriptionPlan', related_name='features', on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.plan.name} - {self.description}"

class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    is_pro = models.BooleanField(default=False)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return self.name

class UserSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='subscriptions', on_delete=models.CASCADE)
    plan = models.ForeignKey(SubscriptionPlan, related_name='subscribers', on_delete=models.CASCADE)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    
    def save(self, *args, **kwargs):
        if not self.end_date:
            self.end_date = self.start_date + timedelta(days=30)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.user.email} - {self.plan.name}"
    
    @property
    def is_expired(self):
        return timezone.now() >= self.end_date
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['end_date']),
        ]

class Wishlist(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='wishlist_items', on_delete=models.CASCADE)
    course = models.ForeignKey(Course, related_name='wishlisted_by', on_delete=models.CASCADE)
    date_added = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'course']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['course']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.course.title}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Clear wishlist cache for this user - v8
        cache.delete(f"wishlist_v8_{self.user_id}")
        cache_key = CacheManager._get_cache_key(f"wishlist_{self.user_id}")
        from django.core.cache import cache
        cache.delete(cache_key)
    
    def delete(self, *args, **kwargs):
        user_id = self.user_id
        result = super().delete(*args, **kwargs)
        cache.delete(f"wishlist_v8_{user_id}")
        cache_key = CacheManager._get_cache_key(f"wishlist_{user_id}")
        from django.core.cache import cache
        cache.delete(cache_key)
        return result

class PaymentCard(models.Model):
    CARD_TYPES = (
        ('VISA', 'Visa'),
        ('MASTERCARD', 'MasterCard'),
        ('AMERICAN EXPRESS', 'American Express'),
        ('DISCOVER', 'Discover'),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='payment_cards', on_delete=models.CASCADE)
    card_type = models.CharField(max_length=20, choices=CARD_TYPES)
    last_four = models.CharField(max_length=4)  # Only store last 4 digits for security
    card_holder_name = models.CharField(max_length=255)
    expiry_month = models.CharField(max_length=2)
    expiry_year = models.CharField(max_length=4)
    is_default = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.card_type} **** **** **** {self.last_four}"
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'is_default']),
        ]

class Purchase(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='purchases', on_delete=models.SET_NULL, null=True, blank=True)
    course = models.ForeignKey(Course, related_name='purchases', on_delete=models.SET_NULL, null=True, blank=True)
    payment_card = models.ForeignKey(PaymentCard, related_name='purchases', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Plan type field for course purchases
    plan_type = models.CharField(max_length=20, choices=CoursePlanType.choices, null=True, blank=True)
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    purchase_date = models.DateTimeField(auto_now_add=True)
    transaction_id = models.CharField(max_length=100, unique=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    payment_status = models.CharField(max_length=20, default='PENDING', 
        choices=(
            ('PENDING', 'Pending'),
            ('COMPLETED', 'Completed'),
            ('FAILED', 'Failed'),
            ('REFUNDED', 'Refunded')
        )
    )
    
    # Apple IAP fields
    apple_transaction_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    apple_product_id = models.CharField(max_length=100, blank=True, null=True)
    apple_receipt_data = models.TextField(blank=True, null=True)
    apple_verification_status = models.CharField(max_length=20, default='PENDING',
        choices=(
            ('PENDING', 'Pending'),
            ('VERIFIED', 'Verified'),
            ('FAILED', 'Failed'),
            ('EXPIRED', 'Expired')
        )
    )
    payment_gateway = models.CharField(max_length=20, default='RAZORPAY',
        choices=(
            ('RAZORPAY', 'Razorpay'),
            ('APPLE_IAP', 'Apple In-App Purchase')
        )
    )
    
    def __str__(self):
        course_title = self.course.title if self.course else "Unknown Course"
        return f"{self.user.email if self.user else 'Unknown User'} - {course_title}"
    
    class Meta:
        ordering = ['-purchase_date']
        indexes = [
            models.Index(fields=['user', 'payment_status']),
            models.Index(fields=['purchase_date']),
            models.Index(fields=['transaction_id']),
            models.Index(fields=['apple_transaction_id']),
            models.Index(fields=['payment_gateway']),
        ]


class AppleIAPProduct(models.Model):
    """Apple IAP Product configuration"""
    product_id = models.CharField(max_length=100, unique=True, help_text="Apple Product ID (e.g., com.yourapp.course1_monthly)")
    course = models.ForeignKey(Course, related_name='apple_products', on_delete=models.CASCADE)
    plan_type = models.CharField(max_length=20, choices=CoursePlanType.choices)
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price in USD")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.product_id} - {self.course.title} ({self.get_plan_type_display()})"
    
    class Meta:
        indexes = [
            models.Index(fields=['product_id', 'is_active']),
            models.Index(fields=['course', 'plan_type']),
        ]


class AppleIAPReceipt(models.Model):
    """Apple IAP Receipt verification records"""
    purchase = models.OneToOneField(Purchase, related_name='apple_receipt', on_delete=models.CASCADE)
    receipt_data = models.TextField(help_text="Base64 encoded receipt data")
    verification_response = models.JSONField(default=dict, help_text="Apple's verification response")
    verification_date = models.DateTimeField(auto_now_add=True)
    is_valid = models.BooleanField(default=False)
    environment = models.CharField(max_length=20, default='Production',
        choices=(
            ('Production', 'Production'),
            ('Sandbox', 'Sandbox')
        )
    )
    
    def __str__(self):
        return f"Receipt for {self.purchase.transaction_id}"
    
    class Meta:
        indexes = [
            models.Index(fields=['verification_date']),
            models.Index(fields=['is_valid', 'environment']),
        ]


class PaymentLinkRequest(models.Model):
    """Payment link requests for course enrollment"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='payment_link_requests', on_delete=models.CASCADE)
    course = models.ForeignKey(Course, related_name='payment_link_requests', on_delete=models.CASCADE)
    plan_type = models.CharField(max_length=20, choices=CoursePlanType.choices)
    
    # Payment link details
    payment_link_id = models.CharField(max_length=100, unique=True, help_text="Unique identifier for the payment link")
    payment_link_url = models.URLField(blank=True, null=True, help_text="Generated payment link URL")
    
    # Request status
    status = models.CharField(max_length=20, default='PENDING',
        choices=(
            ('PENDING', 'Pending'),
            ('EMAIL_SENT', 'Email Sent'),
            ('PAYMENT_COMPLETED', 'Payment Completed'),
            ('ENROLLMENT_COMPLETED', 'Enrollment Completed'),
            ('EXPIRED', 'Expired'),
            ('CANCELLED', 'Cancelled')
        )
    )
    
    # Email tracking
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_sent_count = models.PositiveIntegerField(default=0)
    
    # Payment details (filled when payment is completed)
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    payment_date = models.DateTimeField(null=True, blank=True)
    
    # Admin contact
    admin_contacted = models.BooleanField(default=False)
    admin_notes = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(help_text="Link expiration date")
    
    def __str__(self):
        return f"Payment Link: {self.user.email} - {self.course.title} ({self.get_plan_type_display()})"
    
    @property
    def is_expired(self):
        """Check if the payment link has expired"""
        return timezone.now() > self.expires_at
    
    @property
    def days_until_expiry(self):
        """Get days remaining until expiry"""
        if self.is_expired:
            return 0
        delta = self.expires_at - timezone.now()
        return delta.days
    
    def get_payment_amount(self):
        """Get payment amount based on course and plan type"""
        if self.plan_type == CoursePlanType.ONE_MONTH:
            return self.course.price_one_month
        elif self.plan_type == CoursePlanType.THREE_MONTHS:
            return self.course.price_three_months
        elif self.plan_type == CoursePlanType.LIFETIME:
            return self.course.price_lifetime
        return 0
    
    class Meta:
        indexes = [
            models.Index(fields=['payment_link_id']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['expires_at']),
        ]

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('SUBSCRIPTION', 'Subscription'),
        ('COURSE', 'Course'),
        ('PAYMENT', 'Payment'),
        ('SYSTEM', 'System'),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='notifications', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    is_seen = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.email} - {self.title}"
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_seen']),
            models.Index(fields=['created_at']),
        ]
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Clear notification caches for this user - v8
        self._clear_notification_caches()
        cache_patterns = [
            f"notifications_{self.user_id}_all",
            f"notifications_{self.user_id}_true", 
            f"notifications_{self.user_id}_false"
        ]
        
        cache_keys = []
        for pattern in cache_patterns:
            cache_key = CacheManager._get_cache_key(pattern)
            cache_keys.append(cache_key)
        
        from django.core.cache import cache
        cache.delete_many(cache_keys)
    
    def delete(self, *args, **kwargs):
        user_id = self.user_id
        result = super().delete(*args, **kwargs)
        self._clear_notification_caches_for_user(user_id)
        cache_patterns = [
            f"notifications_{user_id}_all",
            f"notifications_{user_id}_true", 
            f"notifications_{user_id}_false"
        ]
        
        cache_keys = []
        for pattern in cache_patterns:
            cache_key = CacheManager._get_cache_key(pattern)
            cache_keys.append(cache_key)
        
        from django.core.cache import cache
        cache.delete_many(cache_keys)
        return result
    
    def _clear_notification_caches(self):
        """Clear notification caches for this user - UPDATED TO v8"""
        self._clear_notification_caches_for_user(self.user_id)
    
    @staticmethod
    def _clear_notification_caches_for_user(user_id):
        """Clear notification caches - UPDATED TO v8"""
        cache_patterns = [
            f"notifications_v8_{user_id}_all",
            f"notifications_v8_{user_id}_true",
            f"notifications_v8_{user_id}_false"
        ]
        
        hashed_keys = [hashlib.md5(pattern.encode()).hexdigest() for pattern in cache_patterns]
        cache.delete_many(hashed_keys)
        
class FCMDevice(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='fcm_devices', 
        on_delete=models.CASCADE
    )
    registration_id = models.TextField()  # The FCM token
    device_id = models.CharField(max_length=255, unique=True)  # Unique device identifier
    active = models.BooleanField(default=True)
    date_created = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.email} - {self.device_id}"
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'active']),
            models.Index(fields=['device_id']),
        ]
    
class ContentPage(models.Model):
    PAGE_TYPES = (
        ('PRIVACY', 'Privacy Policy'),
        ('TERMS', 'Terms and Conditions'),
    )
    
    page_type = models.CharField(max_length=20, choices=PAGE_TYPES, unique=True)
    content = models.TextField()
    last_updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.get_page_type_display()

class GeneralSettings(models.Model):
    company_name = models.CharField(max_length=255)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20)
    address = models.TextField()
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'General Settings'
        verbose_name_plural = 'General Settings'
    
    def __str__(self):
        return self.company_name
    
    @classmethod
    def get_settings(cls):
        """Get the settings object or create a default one if it doesn't exist"""
        settings, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'company_name': 'Course App',
                'contact_email': 'contact@example.com',
                'contact_phone': '+1234567890',
                'address': 'Default Address'
            }
        )
        return settings
    
class PaymentOrder(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='payment_orders', on_delete=models.SET_NULL, null=True, blank=True)
    course = models.ForeignKey(Course, related_name='payment_orders', on_delete=models.SET_NULL, null=True, blank=True)
    plan = models.ForeignKey('SubscriptionPlan', related_name='payment_orders', on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    razorpay_order_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, default='CREATED', 
        choices=(
            ('CREATED', 'Created'),
            ('PAID', 'Paid'),
            ('FAILED', 'Failed'),
            ('REFUNDED', 'Refunded'),
            ('LINK_REQUESTED', 'Link Requested'),
            ('LINK_EXPIRED', 'Link Expired')
        )
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Payment link fields
    reference_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    payment_method = models.CharField(max_length=20, default='RAZORPAY',
        choices=(
            ('RAZORPAY', 'Razorpay'),
            ('PAYMENT_LINK', 'Payment Link')
        )
    )
    plan_type = models.CharField(max_length=20, choices=CoursePlanType.choices, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.email} - {self.razorpay_order_id}"
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['razorpay_order_id']),
            models.Index(fields=['created_at']),
        ]