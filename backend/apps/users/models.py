"""
Users app models.

Phase 1: Minimal CustomUser with UUID pk and email as USERNAME_FIELD.
         Required so AUTH_USER_MODEL is set from day one (Django best practice).

Phase 2: Adds full_name, phone, role, department, permission_level,
         mfa_enabled, mfa_secret (encrypted), created_by, last_login_ip,
         EmailVerificationToken, PermissionGrant, AuditLog, Notification.
"""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    # username is still required by AbstractUser; kept for admin compatibility.
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users_customuser"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.email
