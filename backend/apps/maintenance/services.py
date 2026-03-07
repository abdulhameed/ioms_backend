"""
Maintenance service layer — Phase 6.
"""

from django.db import connection
from django.utils import timezone


def generate_request_code():
    with connection.cursor() as cur:
        cur.execute("SELECT nextval('maintenance_request_code_seq')")
        seq = cur.fetchone()[0]
    year = timezone.now().year
    return f"MNT-{year}-{seq:04d}"


class MaintenanceService:

    @staticmethod
    def create_request(validated_data, actor):
        """
        Create a MaintenanceRequest.
        - Assigns request_code via sequence
        - Calculates sla_deadline from priority
        - Fires immediate notification for critical priority
        """
        from apps.maintenance.models import MaintenanceRequest
        from apps.users.models import AuditLog, Notification

        request = MaintenanceRequest(**validated_data)
        request.reported_by = actor
        request.request_code = generate_request_code()
        request.set_sla_deadline()
        request.save()

        # Immediate alert for critical priority
        if request.priority == "critical":
            _notify_admins_and_md(
                request,
                title=f"CRITICAL Maintenance: {request.get_issue_type_display()}",
                body=(
                    f"Critical issue reported at {request.location_details or request.location_type}. "
                    f"SLA deadline: {request.sla_deadline.strftime('%Y-%m-%d %H:%M')}. "
                    f"Ref: {request.request_code}"
                ),
            )

        AuditLog.log(
            action="maintenance_created",
            user=actor,
            resource_type="MaintenanceRequest",
            resource_id=request.id,
            description=f"{request.request_code} [{request.priority}] {request.issue_type}",
        )
        return request

    @staticmethod
    def assign(request, assigned_to, assigned_by, notes="", expected_resolution_at=None):
        """Assign request → status=assigned; notify assignee."""
        from apps.users.models import Notification

        if request.status != "open":
            raise ValueError(f"Can only assign an open request (current: {request.status}).")

        request.assigned_to = assigned_to
        request.assigned_by = assigned_by
        request.assignment_notes = notes
        request.expected_resolution_at = expected_resolution_at
        request.status = "assigned"
        request.save(
            update_fields=[
                "assigned_to",
                "assigned_by",
                "assignment_notes",
                "expected_resolution_at",
                "status",
                "updated_at",
            ]
        )

        Notification.objects.create(
            recipient=assigned_to,
            notification_type="assignment",
            title=f"Maintenance Assigned: {request.request_code}",
            body=(
                f"You have been assigned to maintenance request {request.request_code} "
                f"({request.get_priority_display()} priority). "
                f"Notes: {notes or 'None'}."
            ),
            resource_type="MaintenanceRequest",
            resource_id=request.id,
        )

    @staticmethod
    def accept(request, actor, accepted, decline_reason=""):
        """
        Assignee accepts or declines.
        - Accepted: status stays 'assigned'; log comment
        - Declined: status → 'open'; notify admin for reassignment
        """
        from apps.users.models import Notification

        if request.assigned_to_id != actor.id:
            raise PermissionError("Only the assigned user can accept or decline.")
        if request.status != "assigned":
            raise ValueError(f"Request is not in 'assigned' state (current: {request.status}).")

        if accepted:
            _log_status_update(request, "assigned", "assigned", actor, notes="Assignment accepted.")
        else:
            request.status = "open"
            request.assigned_to = None
            request.save(update_fields=["status", "assigned_to", "updated_at"])
            _log_status_update(
                request, "assigned", "open", actor, notes=f"Declined: {decline_reason}"
            )
            _notify_admins(
                request,
                title=f"Maintenance Declined: {request.request_code}",
                body=(
                    f"{actor.full_name or actor.email} declined assignment for "
                    f"{request.request_code}. Reason: {decline_reason or 'Not specified'}. "
                    f"Reassignment needed."
                ),
            )

    @staticmethod
    def update_status(request, actor, new_status, notes="", parts_data=None):
        """
        Create a MaintenanceStatusUpdate and advance the request status.
        Valid transitions checked loosely — admin can override.
        """
        VALID_TRANSITIONS = {
            "assigned": ["in_progress"],
            "in_progress": ["pending_parts", "resolved"],
            "pending_parts": ["in_progress", "resolved"],
            "resolved": ["closed"],
        }
        allowed = VALID_TRANSITIONS.get(request.status, [])
        is_admin = actor.groups.filter(name__in=["admin_full", "md"]).exists()

        if new_status not in allowed and not is_admin:
            raise ValueError(
                f"Cannot transition from '{request.status}' to '{new_status}'."
            )

        old_status = request.status
        parts_data = parts_data or {}
        _log_status_update(
            request,
            old_status,
            new_status,
            actor,
            notes=notes,
            parts_needed=parts_data.get("parts_needed", []),
            parts_vendor=parts_data.get("parts_vendor", ""),
            parts_estimated_cost=parts_data.get("parts_estimated_cost"),
            parts_expected_delivery=parts_data.get("parts_expected_delivery"),
        )

        request.status = new_status
        if new_status == "resolved":
            request.resolved_at = timezone.now()
        request.save(update_fields=["status", "resolved_at", "updated_at"])

    @staticmethod
    def close(request, actor, resolution_notes="", labor_hours=None, parts_cost=None):
        """Close a resolved request; record final resolution details."""
        if request.status not in ("resolved", "in_progress", "pending_parts"):
            raise ValueError(
                f"Cannot close a request with status '{request.status}'."
            )

        request.status = "closed"
        request.closed_at = timezone.now()
        request.closed_by = actor
        request.resolution_notes = resolution_notes
        if labor_hours is not None:
            request.labor_hours = labor_hours
        if parts_cost is not None:
            request.parts_cost = parts_cost
        if not request.resolved_at:
            request.resolved_at = request.closed_at
        request.save(
            update_fields=[
                "status",
                "closed_at",
                "closed_by",
                "resolution_notes",
                "labor_hours",
                "parts_cost",
                "resolved_at",
                "updated_at",
            ]
        )
        _log_status_update(request, "resolved", "closed", actor, notes=resolution_notes)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _log_status_update(
    request,
    from_status,
    to_status,
    actor,
    notes="",
    parts_needed=None,
    parts_vendor="",
    parts_estimated_cost=None,
    parts_expected_delivery=None,
):
    from apps.maintenance.models import MaintenanceStatusUpdate

    MaintenanceStatusUpdate.objects.create(
        request=request,
        from_status=from_status,
        to_status=to_status,
        updated_by=actor,
        notes=notes,
        parts_needed=parts_needed or [],
        parts_vendor=parts_vendor or "",
        parts_estimated_cost=parts_estimated_cost,
        parts_expected_delivery=parts_expected_delivery,
    )


def _notify_admins_and_md(request, title, body):
    from apps.users.models import CustomUser, Notification

    recipients = CustomUser.objects.filter(
        groups__name__in=["admin_full", "md"], is_active=True
    ).distinct()
    for user in recipients:
        Notification.objects.create(
            recipient=user,
            notification_type="sla_warning",
            title=title,
            body=body,
            resource_type="MaintenanceRequest",
            resource_id=request.id,
        )


def _notify_admins(request, title, body):
    from apps.users.models import CustomUser, Notification

    recipients = CustomUser.objects.filter(
        groups__name="admin_full", is_active=True
    ).distinct()
    for user in recipients:
        Notification.objects.create(
            recipient=user,
            notification_type="assignment",
            title=title,
            body=body,
            resource_type="MaintenanceRequest",
            resource_id=request.id,
        )
