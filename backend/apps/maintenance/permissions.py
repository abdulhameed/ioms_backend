"""
Maintenance permissions — Phase 6.
"""

from rest_framework.permissions import BasePermission


def _in_groups(user, *names):
    return user.groups.filter(name__in=names).exists()


class CanCreateRequest(BasePermission):
    """admin_full, front_desk, pm_full, pm_limited."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _in_groups(
            request.user, "admin_full", "front_desk", "pm_full", "pm_limited"
        )


class CanManageRequest(BasePermission):
    """admin_full only — assign, close, edit."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _in_groups(request.user, "admin_full")


class CanViewMetrics(BasePermission):
    """admin_full or md."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _in_groups(
            request.user, "admin_full", "md"
        )


class IsAssignee(BasePermission):
    """The currently assigned user on the request object."""

    def has_object_permission(self, request, view, obj):
        return obj.assigned_to_id == request.user.id


class IsParticipantOrAdmin(BasePermission):
    """reporter, assignee, admin_full, or md can view detail."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if _in_groups(user, "admin_full", "md"):
            return True
        return obj.reported_by_id == user.id or obj.assigned_to_id == user.id
