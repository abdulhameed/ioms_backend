"""
Custom DRF permission classes for the users app.
"""

from rest_framework.permissions import BasePermission


def _has_group(user, *group_names):
    return user.groups.filter(name__in=group_names).exists()


class CanCreateUser(BasePermission):
    """md, hr_full, admin_full may create user accounts."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return _has_group(request.user, "md", "hr_full", "admin_full")


class CanManageUsers(BasePermission):
    """md, hr_full may list/view/update any user."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return _has_group(request.user, "md", "hr_full")


class CanViewAuditLog(BasePermission):
    """Only md and hr_full may access the audit log."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return _has_group(request.user, "md", "hr_full")


class IsManagerSameDept(BasePermission):
    """
    The acting user must have a 'full' permission_level and be in the same
    department as the target user (resolved in has_object_permission).
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.permission_level == "full"

    def has_object_permission(self, request, view, obj):
        # obj is the target CustomUser
        if request.user.role == "md":
            return True
        return request.user.department == obj.department
