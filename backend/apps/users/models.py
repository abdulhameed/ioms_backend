"""
Users app models — Phase 2.

Models:
  CustomUser           — Extended auth user with role/dept/MFA/encryption
  EmailVerificationToken — Single-use token for email verification + password setup
  PermissionGrant      — Audit trail of individual permission overrides
  AuditLog             — Append-only event log (no update/delete at app layer)
  Notification         — In-app / email / SMS notification record
"""

import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.core.fields import EncryptedCharField


class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ("md", "Managing Director"),
        ("hr", "Human Resources"),
        ("finance", "Finance"),
        ("admin", "Administration"),
        ("pm", "Project Management"),
        ("front_desk", "Front Desk"),
        ("social_media", "Social Media"),
        ("content_creator", "Content Creator"),
    ]
    PERMISSION_LEVEL_CHOICES = [
        ("full", "Full"),
        ("limited", "Limited"),
    ]

    # ── Core identity ──────────────────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)

    # ── Role / RBAC ────────────────────────────────────────────────────────
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, blank=True)
    department = models.CharField(max_length=100, blank=True)
    permission_level = models.CharField(
        max_length=10, choices=PERMISSION_LEVEL_CHOICES, default="limited"
    )

    # ── MFA ────────────────────────────────────────────────────────────────
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = EncryptedCharField(blank=True)  # TOTP secret, stored encrypted

    # ── Provenance / audit ─────────────────────────────────────────────────
    created_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_users",
    )
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    # ── Login security ─────────────────────────────────────────────────────
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    # username kept for AbstractUser/admin compatibility; auto-generated on save.
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users_customuser"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.email

    # ── Helpers ────────────────────────────────────────────────────────────

    def get_role_key(self):
        """Return the Django Group name that maps to this user's role."""
        single_level_roles = {"md", "front_desk", "content_creator"}
        if self.role in single_level_roles:
            return self.role
        return f"{self.role}_{self.permission_level}"

    @property
    def is_locked(self):
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False

    def record_failed_login(self):
        self.failed_login_count += 1
        if self.failed_login_count >= 5:
            self.locked_until = timezone.now() + timedelta(minutes=30)
        self.save(update_fields=["failed_login_count", "locked_until"])

    def reset_login_attempts(self):
        if self.failed_login_count or self.locked_until:
            self.failed_login_count = 0
            self.locked_until = None
            self.save(update_fields=["failed_login_count", "locked_until"])


class EmailVerificationToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="verification_tokens"
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users_emailverificationtoken"

    @classmethod
    def create_for_user(cls, user, hours=72):
        return cls.objects.create(
            user=user,
            token=secrets.token_urlsafe(48),  # 64-char URL-safe token
            expires_at=timezone.now() + timedelta(hours=hours),
        )

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()

    def consume(self):
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])

    def __str__(self):
        return f"Token for {self.user.email}"


class PermissionGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="granted_permissions"
    )
    permission = models.ForeignKey("auth.Permission", on_delete=models.CASCADE)
    granted_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="permissions_granted",
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    revoked_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="permissions_revoked",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "users_permissiongrant"

    def __str__(self):
        return f"{self.user.email} — {self.permission.codename}"


class AuditLog(models.Model):
    """
    Append-only audit trail. No update or delete at the application layer.
    Use AuditLog.log() to create entries.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    role_snapshot = models.CharField(max_length=100, blank=True)
    action = models.CharField(max_length=100, db_index=True)
    resource_type = models.CharField(max_length=100, blank=True)
    resource_id = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "users_auditlog"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.action} by {self.user_id} at {self.timestamp}"

    @classmethod
    def log(
        cls,
        action,
        user=None,
        resource_type="",
        resource_id="",
        description="",
        metadata=None,
        ip_address=None,
    ):
        return cls.objects.create(
            user=user,
            role_snapshot=user.get_role_key() if user and user.role else "",
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else "",
            description=description,
            metadata=metadata or {},
            ip_address=ip_address,
        )


class Notification(models.Model):
    NOTIFICATION_TYPE_CHOICES = [
        ("approval_pending", "Approval Pending"),
        ("approval_decided", "Approval Decided"),
        ("assignment", "Assignment"),
        ("sla_warning", "SLA Warning"),
        ("budget_alert", "Budget Alert"),
        ("booking_reminder", "Booking Reminder"),
        ("system", "System"),
    ]
    CHANNEL_CHOICES = [
        ("in_app", "In-App"),
        ("email", "Email"),
        ("sms", "SMS"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(
        max_length=30, choices=NOTIFICATION_TYPE_CHOICES
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    resource_type = models.CharField(max_length=50, blank=True)
    resource_id = models.UUIDField(null=True, blank=True)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default="in_app")
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users_notification"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notification_type} → {self.recipient.email}"
