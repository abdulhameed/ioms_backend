from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users import views

router = DefaultRouter()
router.register(r"users", views.UserViewSet, basename="user")
router.register(r"audit-logs", views.AuditLogViewSet, basename="auditlog")

auth_urls = [
    path("register/", views.RegisterView.as_view(), name="auth-register"),
    path("verify-email/", views.VerifyEmailView.as_view(), name="auth-verify-email"),
    path("set-password/", views.SetPasswordView.as_view(), name="auth-set-password"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("mfa/setup/", views.MFASetupView.as_view(), name="auth-mfa-setup"),
    path("mfa/verify/", views.MFAVerifyView.as_view(), name="auth-mfa-verify"),
]

urlpatterns = [
    path("auth/", include(auth_urls)),
    path("", include(router.urls)),
]
