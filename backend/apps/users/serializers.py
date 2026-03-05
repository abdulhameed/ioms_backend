"""
Users app serializers — Phase 2.
"""

import pyotp
from django.contrib.auth import authenticate
from django.contrib.auth.models import Permission
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import (
    AuditLog,
    CustomUser,
    EmailVerificationToken,
    Notification,
    PermissionGrant,
)


class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "full_name",
            "phone",
            "role",
            "department",
            "permission_level",
            "is_active",
            "mfa_enabled",
            "date_joined",
        ]
        read_only_fields = ["id", "date_joined"]


class UserDetailSerializer(serializers.ModelSerializer):
    """Used for GET /users/{id}/ and GET /users/me/."""

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "full_name",
            "phone",
            "username",
            "role",
            "department",
            "permission_level",
            "is_active",
            "mfa_enabled",
            "last_login_ip",
            "date_joined",
            "created_by",
        ]
        read_only_fields = ["id", "email", "date_joined", "last_login_ip", "created_by"]


class UserUpdateSerializer(serializers.ModelSerializer):
    """PUT /users/{id}/ — manager can change role/dept/level; self can change name/phone."""

    class Meta:
        model = CustomUser
        fields = [
            "full_name",
            "phone",
            "role",
            "department",
            "permission_level",
            "is_active",
        ]

    def validate_phone(self, value):
        if value:
            qs = CustomUser.objects.filter(phone=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "A user with this phone number already exists."
                )
        return value


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    role = serializers.ChoiceField(
        choices=CustomUser.ROLE_CHOICES, required=False, allow_blank=True
    )
    department = serializers.CharField(max_length=100, required=False, allow_blank=True)
    permission_level = serializers.ChoiceField(
        choices=CustomUser.PERMISSION_LEVEL_CHOICES, default="limited"
    )

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def validate_phone(self, value):
        if value and CustomUser.objects.filter(phone=value).exists():
            raise serializers.ValidationError(
                "A user with this phone number already exists."
            )
        return value


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128)

    def validate_token(self, value):
        try:
            obj = EmailVerificationToken.objects.select_related("user").get(token=value)
        except EmailVerificationToken.DoesNotExist:
            raise serializers.ValidationError("Invalid token.")
        if not obj.is_valid:
            raise serializers.ValidationError("Token has expired or already been used.")
        self._token_obj = obj
        return value

    def save(self):
        obj = self._token_obj
        obj.consume()
        user = obj.user
        user.is_active = True
        user.save(update_fields=["is_active"])
        return user


class SetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128)
    password = serializers.CharField(min_length=8, write_only=True)

    def validate_token(self, value):
        try:
            obj = EmailVerificationToken.objects.select_related("user").get(token=value)
        except EmailVerificationToken.DoesNotExist:
            raise serializers.ValidationError("Invalid token.")
        if not obj.is_valid:
            raise serializers.ValidationError("Token has expired or already been used.")
        self._token_obj = obj
        return value

    def save(self):
        obj = self._token_obj
        obj.consume()
        user = obj.user
        user.set_password(self.validated_data["password"])
        user.is_active = True
        user.save(update_fields=["password", "is_active"])
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data["email"].lower()
        password = data["password"]

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError({"email": "Invalid credentials."})

        if not user.is_active:
            raise serializers.ValidationError({"email": "Account is not yet activated."})

        if user.is_locked:
            raise serializers.ValidationError(
                {"non_field_errors": "account_locked"},
            )

        authenticated = authenticate(username=email, password=password)
        if not authenticated:
            user.record_failed_login()
            if user.is_locked:
                # Queue unlock email; 423 is returned on the *next* attempt
                # when is_locked is checked at the top of validate().
                from apps.users.tasks import send_account_unlock_email

                send_account_unlock_email.delay(str(user.id))
            raise serializers.ValidationError({"password": "Invalid credentials."})

        if not authenticated.is_active:
            raise serializers.ValidationError(
                {"email": "Account is not yet activated."}
            )

        authenticated.reset_login_attempts()
        data["user"] = authenticated
        return data


class MFASetupSerializer(serializers.Serializer):
    def save(self, user):
        secret = pyotp.random_base32()
        user.mfa_secret = secret
        user.save(update_fields=["mfa_secret"])
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name="IOMS")
        return {"provisioning_uri": provisioning_uri, "secret": secret}


class MFAVerifySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6)

    def validate_code(self, value):
        user = self.context["request"].user
        if not user.mfa_secret:
            raise serializers.ValidationError("MFA not set up for this account.")
        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(value, valid_window=1):
            raise serializers.ValidationError("Invalid or expired MFA code.")
        return value

    def save(self, user):
        user.mfa_enabled = True
        user.save(update_fields=["mfa_enabled"])
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }


class GrantPermissionSerializer(serializers.Serializer):
    permission_codename = serializers.CharField()

    def validate_permission_codename(self, value):
        try:
            perm = Permission.objects.get(codename=value)
        except Permission.DoesNotExist:
            raise serializers.ValidationError(f"Permission '{value}' does not exist.")
        self._permission = perm
        return value

    def save(self, user, granted_by):
        perm = self._permission
        # Re-activate if already exists
        grant, created = PermissionGrant.objects.get_or_create(
            user=user,
            permission=perm,
            defaults={"granted_by": granted_by},
        )
        if not created and not grant.is_active:
            grant.is_active = True
            grant.granted_by = granted_by
            grant.revoked_by = None
            grant.revoked_at = None
            grant.save()
        user.user_permissions.add(perm)
        return grant


class RevokePermissionSerializer(serializers.Serializer):
    permission_codename = serializers.CharField()

    def validate_permission_codename(self, value):
        try:
            perm = Permission.objects.get(codename=value)
        except Permission.DoesNotExist:
            raise serializers.ValidationError(f"Permission '{value}' does not exist.")
        self._permission = perm
        return value

    def save(self, user, revoked_by):
        perm = self._permission
        PermissionGrant.objects.filter(
            user=user, permission=perm, is_active=True
        ).update(
            is_active=False,
            revoked_by=revoked_by,
            revoked_at=timezone.now(),
        )
        user.user_permissions.remove(perm)


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "user",
            "user_email",
            "role_snapshot",
            "action",
            "resource_type",
            "resource_id",
            "description",
            "metadata",
            "ip_address",
            "timestamp",
        ]
        read_only_fields = fields

    def get_user_email(self, obj):
        return obj.user.email if obj.user else None


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "title",
            "body",
            "resource_type",
            "resource_id",
            "channel",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields
