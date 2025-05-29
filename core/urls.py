# Updated URLs for the new purchase endpoint

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.admin_views import AdminAddStudentToPlanView, AdminBulkEnrollmentOperationsView, AdminMetricsView, AdminRemoveStudentFromPlanView, ContentPageViewSet, EnrolledStudentsListView, GeneralSettingsView, PublicContentPageView, UserListView
from core.firebase_auth_view import FirebaseGoogleAuthView
from core.payment_views import CreateOrderView, VerifyPaymentView, cancel_subscription, razorpay_webhook, renew_subscription
from core.views_presign import GeneratePresignedURLView, S3DebugView
from .views import (
    CategoryViewSet, CourseCurriculumViewSet, CourseObjectiveViewSet, CourseRequirementViewSet, CourseViewSet, 
    EnrollmentViewSet, NotificationViewSet, ProfilePictureDeleteView, ProfilePictureRetrieveView, ProfilePictureUploadView, PublicCourseDetailView, SubscriptionPlanViewSet, UserProfileView, UserSubscriptionViewSet, 
    WishlistViewSet, PaymentCardViewSet, PurchaseViewSet, UpdateProfileView, LogoutView, DeleteAccountView, 
    FCMDeviceViewSet, debug_login, CoursePurchaseView  # Added the new view
)
from .auth_views import CustomLoginView, CustomRegisterView, ForgotPasswordView, ResetPasswordView, VerifyOTPView, GoogleLoginView

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'courses', CourseViewSet)
router.register(r'enrollments', EnrollmentViewSet, basename='enrollment')
router.register(r'subscription-plans', SubscriptionPlanViewSet)
router.register(r'my-subscriptions', UserSubscriptionViewSet, basename='user-subscription')
router.register(r'wishlist', WishlistViewSet, basename='wishlist')
router.register(r'payment-cards', PaymentCardViewSet, basename='payment-card')
router.register(r'purchase-history', PurchaseViewSet, basename='purchase')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'devices', FCMDeviceViewSet, basename='device')
router.register(r'content-pages', ContentPageViewSet, basename='content-page')

urlpatterns = [
    path('', include(router.urls)),
    
    # Auth endpoints
    path('auth/registration/', CustomRegisterView.as_view(), name='rest_register'),
    path('auth/login/', CustomLoginView.as_view(), name='rest_login'),
   path('auth/forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('auth/verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('auth/reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('auth/google/', GoogleLoginView.as_view(), name='google-login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/debug-login/', debug_login, name='debug-login'),
    
    # User profile
    path('profile/update/', UpdateProfileView.as_view(), name='update-profile'),
    path('account/delete/', DeleteAccountView.as_view(), name='delete-account'),
    
    # Admin endpoints
    path('admin/metrics/', AdminMetricsView.as_view(), name='admin-metrics'),
    path('admin/users/', UserListView.as_view(), name='admin-users-list'),
    path('admin/enrolled-students/', EnrolledStudentsListView.as_view(), name='admin-enrolled-students-list'),
    
    # Settings and content
    path('settings/', GeneralSettingsView.as_view(), name='general-settings'),
    path('content/', PublicContentPageView.as_view(), name='public-content'),
    
    # Course management endpoints
    path('courses/<int:course_pk>/objectives/', CourseObjectiveViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='course-objectives-list'),
    path('courses/<int:course_pk>/objectives/<int:pk>/', CourseObjectiveViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='course-objectives-detail'),
    
    path('courses/<int:course_pk>/requirements/', CourseRequirementViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='course-requirements-list'),
    path('courses/<int:course_pk>/requirements/<int:pk>/', CourseRequirementViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='course-requirements-detail'),
    
    path('courses/<int:course_pk>/curriculum/', CourseCurriculumViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='course-curriculum-list'),
    path('courses/<int:course_pk>/curriculum/<int:pk>/', CourseCurriculumViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='course-curriculum-detail'),
    path('courses/<int:course_pk>/curriculum/reorder/', CourseCurriculumViewSet.as_view({
        'post': 'reorder'
    }), name='course-curriculum-reorder'),
    
    # Public course details
    path('public/courses/<int:id>/', PublicCourseDetailView.as_view(), name='public-course-detail'),
    path('courses/<int:pk>/complete/', CourseViewSet.as_view({'get': 'complete_details'}), name='course-complete-details'),
    
    # Payment endpoints
    path('payments/create-order/', CreateOrderView.as_view(), name='create-order'),
    path('payments/verify-payment/', VerifyPaymentView.as_view(), name='verify-payment'),
    path('payments/cancel-subscription/<int:subscription_id>/', cancel_subscription, name='cancel-subscription'),
    path('payments/renew-subscription/<int:subscription_id>/', renew_subscription, name='renew-subscription'),
    path('payments/webhook/', razorpay_webhook, name='razorpay-webhook'),
 path('debug/s3/', S3DebugView.as_view(), name='s3-debug'),
    path('generate-presigned-url/', GeneratePresignedURLView.as_view(), name='generate-presigned-url'),

    path('payments/purchase-course/', CoursePurchaseView.as_view(), name='purchase-course'),
    # NEW: Course purchase endpoint
    path('courses/purchase/', CoursePurchaseView.as_view(), name='course-purchase'),
    
    # Enrollment endpoints (updated to work with new purchase flow)
    path('enrollments/verify-payment/', EnrollmentViewSet.as_view({'post': 'verify_payment'}), name='enrollment-verify-payment'),
    path('enrollments/check-status/', EnrollmentViewSet.as_view({'get': 'check_status'}), name='enrollment-check-status'),
    path('profile/picture/upload/', ProfilePictureUploadView.as_view(), name='profile-picture-upload'),
    path('profile/picture/', ProfilePictureRetrieveView.as_view(), name='profile-picture-get'),
    path('profile/picture/delete/', ProfilePictureDeleteView.as_view(), name='profile-picture-delete'),
    path('profile/', UserProfileView.as_view(), name='user-profile'),
     path('auth/firebase-google/', FirebaseGoogleAuthView.as_view(), name='firebase-google'),
      path('admin/add-student-to-plan/', AdminAddStudentToPlanView.as_view(), name='admin-add-student-to-plan'),
      path('admin/remove-student-from-plan/', AdminRemoveStudentFromPlanView.as_view(), name='admin-remove-student-from-plan'),
    path('admin/bulk-enrollment-operations/', AdminBulkEnrollmentOperationsView.as_view(), name='admin-bulk-enrollment-operations'),
 
    
]
