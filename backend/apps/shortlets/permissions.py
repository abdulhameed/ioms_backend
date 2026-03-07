"""
Shortlets permissions — Phase 5.
"""

from rest_framework.permissions import BasePermission


def _in_groups(user, *group_names):
    return user.groups.filter(name__in=group_names).exists()


class CanManageProperty(BasePermission):
    """Create/edit properties — admin_full or front_desk."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _in_groups(
            request.user, "admin_full", "front_desk"
        )


class CanManageBooking(BasePermission):
    """Create/update bookings — admin_full or front_desk."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _in_groups(
            request.user, "admin_full", "front_desk"
        )


class CanViewBooking(BasePermission):
    """View bookings — admin_full, front_desk, md, hr_full."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _in_groups(
            request.user, "admin_full", "front_desk", "md", "hr_full"
        )


class CanManageClient(BasePermission):
    """Create/edit clients — admin_full or front_desk."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _in_groups(
            request.user, "admin_full", "front_desk"
        )


class CanExportClients(BasePermission):
    """Export client CSV — md or admin_full only."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _in_groups(
            request.user, "md", "admin_full"
        )


class CanManageDeposit(BasePermission):
    """Update deposit refund details — admin_full only."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _in_groups(request.user, "admin_full")


class CanViewDeposit(BasePermission):
    """View deposits — admin_full, hr_full, md."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _in_groups(
            request.user, "admin_full", "hr_full", "md"
        )
