"""
Projects app permissions — Phase 4.
"""

from rest_framework.permissions import BasePermission

CREATE_PROJECT_GROUPS = {"md", "admin_full", "pm_full"}
MANAGE_PROJECT_GROUPS = {"md", "admin_full"}


class CanCreateProject(BasePermission):
    """Allowed for: md, admin_full, pm_full."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.groups.filter(
            name__in=CREATE_PROJECT_GROUPS
        ).exists()


class CanManageProject(BasePermission):
    """Allowed for: md, admin_full."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.groups.filter(
            name__in=MANAGE_PROJECT_GROUPS
        ).exists()


class IsProjectCreator(BasePermission):
    """Object-level: only the project creator can edit (and only in draft)."""

    def has_object_permission(self, request, view, obj):
        return request.user.id == obj.created_by_id


class IsPMOnProject(BasePermission):
    """
    Object-level: user is the project_manager or an md.
    Used for milestone creation, site report creation.
    `obj` is the Project instance.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.groups.filter(name="md").exists():
            return True
        return obj.project_manager_id == user.id
