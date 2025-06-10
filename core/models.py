from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
import random
import string
from datetime import timedelta
from django.conf import settings

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
        ]

class Category(models.Model):
    name = models.CharField(max_length=100)
    image_url = models.URLField(max_length=500)
    description = models.TextField()
    
    def __str__(self):
        return self.name
    
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
    title = models.CharField(max_length=100)
    video_url = models.URLField(max_length=500, blank=True, null=True)
    course = models.ForeignKey('Course', related_name='curriculum', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    class Meta:
        ordering = ['order']

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
        ]

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
        from django.core.cache import cache
        cache_patterns = [
            f"enrollments_v6_{self.user_id}_true",
            f"enrollments_v6_{self.user_id}_false",
            f"enrollment_status_{self.user_id}_{self.course_id}",
            f"enrollment_detail_{self.user_id}_{self.id}"
        ]
        for pattern in cache_patterns:
            cache.delete(pattern)

    
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
    
    def __str__(self):
        course_title = self.course.title if self.course else "Unknown Course"
        return f"{self.user.email if self.user else 'Unknown User'} - {course_title}"
    
    class Meta:
        ordering = ['-purchase_date']
        indexes = [
            models.Index(fields=['user', 'payment_status']),
            models.Index(fields=['purchase_date']),
            models.Index(fields=['transaction_id']),
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
            ('REFUNDED', 'Refunded')
        )
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.email} - {self.razorpay_order_id}"
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['razorpay_order_id']),
            models.Index(fields=['created_at']),
        ]