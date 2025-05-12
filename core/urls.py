from django.urls import path, include
from rest_framework.routers import DefaultRouter

from core.admin_views import AdminMetricsView, ContentPageViewSet, EnrolledStudentsListView, GeneralSettingsView, PublicContentPageView, UserListView
from core.payment_views import CreateOrderView, VerifyPaymentView, cancel_subscription, razorpay_webhook, renew_subscription
from .views import (
    CategoryViewSet, CourseCurriculumViewSet, CourseObjectiveViewSet, CourseRequirementViewSet, CourseViewSet, EnrollmentViewSet, NotificationViewSet, PublicCourseDetailView,
    SubscriptionPlanViewSet, UserSubscriptionViewSet, WishlistViewSet,
    PaymentCardViewSet, PurchaseViewSet, UpdateProfileView,
    LogoutView, DeleteAccountView, FCMDeviceViewSet, debug_login
)
from .auth_views import CustomLoginView, CustomRegisterView, ForgotPasswordView, VerifyOTPView, GoogleLoginView



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
    path('auth/registration/', CustomRegisterView.as_view(), name='rest_register'),
    path('auth/login/', CustomLoginView.as_view(), name='rest_login'),
    path('auth/forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('auth/verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('auth/google/', GoogleLoginView.as_view(), name='google-login'),
    path('profile/update/', UpdateProfileView.as_view(), name='update-profile'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('account/delete/', DeleteAccountView.as_view(), name='delete-account'),
    path('auth/debug-login/', debug_login, name='debug-login'),
    path('admin/metrics/', AdminMetricsView.as_view(), name='admin-metrics'),
    path('settings/', GeneralSettingsView.as_view(), name='general-settings'),
    path('content/', PublicContentPageView.as_view(), name='public-content'),
    path('admin/users/', UserListView.as_view(), name='admin-users-list'),
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
    
    # Requirements
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
    
    # Curriculum
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
    path('admin/enrolled-students/', EnrolledStudentsListView.as_view(), name='admin-enrolled-students-list'),
    path('public/courses/<int:id>/', PublicCourseDetailView.as_view(), name='public-course-detail'),
    
    # Add a shortcut for complete course details
    path('courses/<int:pk>/complete/', CourseViewSet.as_view({'get': 'complete_details'}), name='course-complete-details'),
     path('payments/create-order/', CreateOrderView.as_view(), name='create-order'),
    path('payments/verify-payment/', VerifyPaymentView.as_view(), name='verify-payment'),
    path('payments/cancel-subscription/<int:subscription_id>/', cancel_subscription, name='cancel-subscription'),
    path('payments/renew-subscription/<int:subscription_id>/', renew_subscription, name='renew-subscription'),
    path('payments/webhook/', razorpay_webhook, name='razorpay-webhook'),
    
    # Add this to the existing EnrollmentViewSet
    path('enrollments/verify-payment/', EnrollmentViewSet.as_view({'post': 'verify_payment'}), name='enrollment-verify-payment'),
    path('enrollments/check-status/', EnrollmentViewSet.as_view({'get': 'check_status'}), name='enrollment-check-status'),
    
    
]