"""
Users app views — Phase 2.
"""

import logging

from django.contrib.auth.models import Permission
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import AuditLog, CustomUser, PermissionGrant
from apps.users.permissions import (
    CanCreateUser,
    CanManageUsers,
    CanViewAuditLog,
    IsManagerSameDept,
)
from apps.users.tasks import send_verification_email
from apps.users.serializers import (
    AuditLogSerializer,
    GrantPermissionSerializer,
    LoginSerializer,
    MFASetupSerializer,
    MFAVerifySerializer,
    RegisterSerializer,
    RevokePermissionSerializer,
    SetPasswordSerializer,
    UserDetailSerializer,
    UserListSerializer,
    UserUpdateSerializer,
    VerifyEmailSerializer,
)

logger = logging.getLogger(__name__)


def _get_client_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# ── Throttle ───────────────────────────────────────────────────────────────────


class LoginThrottle(AnonRateThrottle):
    scope = "login"
    # Set rate directly to bypass settings lookup in get_rate()
    rate = "10/placeholder"

    def parse_rate(self, rate):
        # 10 requests per 15-minute window regardless of rate string
        return (10, 15 * 60)


# ── Auth views ─────────────────────────────────────────────────────────────────


class RegisterView(APIView):
    permission_classes = [CanCreateUser]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Auto-generate username from email
        username_base = data["email"].split("@")[0]
        username = username_base
        counter = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{username_base}{counter}"
            counter += 1

        user = CustomUser.objects.create_user(
            username=username,
            email=data["email"],
            password=None,
            full_name=data.get("full_name", ""),
            phone=data.get("phone") or None,
            role=data.get("role", ""),
            department=data.get("department", ""),
            permission_level=data.get("permission_level", "limited"),
            is_active=False,
            created_by=request.user,
        )

        from apps.users.models import EmailVerificationToken

        token_obj = EmailVerificationToken.create_for_user(user)
        send_verification_email.delay(str(user.id), token_obj.token)

        AuditLog.log(
            action="user.created",
            user=request.user,
            resource_type="CustomUser",
            resource_id=user.id,
            description=f"Created user {user.email}",
            ip_address=_get_client_ip(request),
        )

        return Response(UserDetailSerializer(user).data, status=status.HTTP_201_CREATED)


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {"message": "Email verified. Account activated.", "user_id": str(user.id)},
            status=status.HTTP_200_OK,
        )


class SetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"message": "Password set successfully."},
            status=status.HTTP_200_OK,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        # Detect account-locked early (before DRF raises 400)
        if not serializer.is_valid():
            errors = serializer.errors
            non_field = errors.get("non_field_errors", [])
            msg = non_field[0] if non_field else ""
            if msg == "account_locked":
                return Response(
                    {
                        "error": "account_locked",
                        "message": "Account is locked. Try again later.",
                    },
                    status=status.HTTP_423_LOCKED,
                )
            return Response(errors, status=status.HTTP_401_UNAUTHORIZED)

        user = serializer.validated_data["user"]
        ip = _get_client_ip(request)

        # MFA enforcement for md and hr_full
        requires_mfa_roles = {"md", "hr_full"}
        if user.role in requires_mfa_roles and not user.mfa_enabled:
            return Response(
                {
                    "error": "mfa_required",
                    "message": "MFA must be configured before login for this role.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        AuditLog.log(
            action="auth.login",
            user=user,
            resource_type="CustomUser",
            resource_id=user.id,
            description="Successful login",
            metadata={
                "ip": ip,
                "device": request.META.get("HTTP_USER_AGENT", "")[:200],
            },
            ip_address=ip,
        )

        user.last_login_ip = ip
        user.save(update_fields=["last_login_ip"])

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": "missing_token", "message": "refresh token required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError as e:
            return Response(
                {"error": "invalid_token", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MFASetupView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MFASetupSerializer()
        result = serializer.save(user=request.user)
        return Response(result, status=status.HTTP_200_OK)


class MFAVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MFAVerifySerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        tokens = serializer.save(user=request.user)
        return Response(tokens, status=status.HTTP_200_OK)


# ── User ViewSet ───────────────────────────────────────────────────────────────


class UserViewSet(ModelViewSet):
    queryset = CustomUser.objects.select_related("created_by").order_by("-date_joined")
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "list":
            return UserListSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserDetailSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [CanManageUsers()]
        if self.action == "create":
            return [CanCreateUser()]
        if self.action in ("update", "partial_update"):
            return [CanManageUsers()]
        if self.action in ("grant_permission", "revoke_permission"):
            return [IsManagerSameDept()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        role = self.request.query_params.get("role")
        dept = self.request.query_params.get("department")
        is_active = self.request.query_params.get("is_active")
        if role:
            qs = qs.filter(role=role)
        if dept:
            qs = qs.filter(department=dept)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")
        return qs

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        old_role = instance.role
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        if user.role != old_role:
            AuditLog.log(
                action="user.role_changed",
                user=request.user,
                resource_type="CustomUser",
                resource_id=user.id,
                description=f"Role changed from {old_role} to {user.role}",
                ip_address=_get_client_ip(request),
            )

        return Response(UserDetailSerializer(user).data)

    @action(detail=False, methods=["get", "put"], url_path="me")
    def me(self, request):
        if request.method == "GET":
            return Response(UserDetailSerializer(request.user).data)
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        # Non-managers can only update own name/phone
        if not request.user.groups.filter(name__in=["md", "hr_full"]).exists():
            allowed = {"full_name", "phone"}
            for field in set(serializer.validated_data.keys()) - allowed:
                serializer.validated_data.pop(field, None)
        serializer.save()
        return Response(UserDetailSerializer(request.user).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="grant-permission",
        permission_classes=[IsManagerSameDept],
    )
    def grant_permission(self, request, pk=None):
        target = self.get_object()
        serializer = GrantPermissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        grant = serializer.save(user=target, granted_by=request.user)

        AuditLog.log(
            action="permission.granted",
            user=request.user,
            resource_type="PermissionGrant",
            resource_id=grant.id,
            description=f"Granted {grant.permission.codename} to {target.email}",
            ip_address=_get_client_ip(request),
        )
        return Response({"message": "Permission granted."}, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["post"],
        url_path="revoke-permission",
        permission_classes=[IsManagerSameDept],
    )
    def revoke_permission(self, request, pk=None):
        target = self.get_object()
        serializer = RevokePermissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=target, revoked_by=request.user)
        return Response({"message": "Permission revoked."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="permissions")
    def permissions_list(self, request, pk=None):
        target = self.get_object()
        if (
            request.user != target
            and not request.user.groups.filter(name__in=["md", "hr_full"]).exists()
        ):
            return Response(status=status.HTTP_403_FORBIDDEN)

        group_perms = list(
            Permission.objects.filter(group__user=target).values("codename", "name")
        )
        individual_grants = PermissionGrant.objects.filter(
            user=target, is_active=True
        ).select_related("permission")
        individual = [
            {"codename": g.permission.codename, "name": g.permission.name}
            for g in individual_grants
        ]
        return Response(
            {"group_permissions": group_perms, "individual_grants": individual}
        )


# ── AuditLog ViewSet ───────────────────────────────────────────────────────────


class AuditLogViewSet(ModelViewSet):
    """Read-only. No create/update/delete via API (append-only model)."""

    queryset = AuditLog.objects.select_related("user").order_by("-timestamp")
    serializer_class = AuditLogSerializer
    permission_classes = [CanViewAuditLog]
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        action_filter = self.request.query_params.get("action")
        resource = self.request.query_params.get("resource_type")
        if action_filter:
            qs = qs.filter(action=action_filter)
        if resource:
            qs = qs.filter(resource_type=resource)
        return qs

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        import csv
        from django.http import HttpResponse

        qs = self.get_queryset()
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="audit_log.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "timestamp",
                "user",
                "action",
                "resource_type",
                "resource_id",
                "description",
                "ip_address",
            ]
        )
        for log in qs.iterator():
            writer.writerow(
                [
                    log.timestamp.isoformat(),
                    log.user.email if log.user else "",
                    log.action,
                    log.resource_type,
                    log.resource_id,
                    log.description,
                    log.ip_address or "",
                ]
            )
        return response
