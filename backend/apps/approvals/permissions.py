"""
Approvals app permissions — Phase 3.
"""

from rest_framework.permissions import BasePermission

MANAGER_ROLES = {"md", "hr_full"}


def _is_manager(user):
    return user.groups.filter(name__in=MANAGER_ROLES).exists()


class IsApprovalParticipant(BasePermission):
    """
    Allows access if request.user is the initiator, l1_approver, l2_approver,
    or is an md / hr_full manager.
    Used for: GET /approvals/{id}/
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if _is_manager(user):
            return True
        return user.id in (
            obj.initiated_by_id,
            obj.l1_approver_id,
            obj.l2_approver_id,
        )


class IsAssignedApprover(BasePermission):
    """
    Allows access only to the user who is currently responsible for deciding.
    L1 approver when status=pending_l1; L2 approver when status=pending_l2.
    Used for: POST /approvals/{id}/decide/
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if obj.status == "pending_l1":
            return user.id == obj.l1_approver_id
        if obj.status == "pending_l2":
            return user.id == obj.l2_approver_id
        return False


class IsWorkflowInitiator(BasePermission):
    """
    Allows access only to the workflow initiator.
    Used for: POST /approvals/{id}/withdraw/
    """

    def has_object_permission(self, request, view, obj):
        return request.user.id == obj.initiated_by_id
