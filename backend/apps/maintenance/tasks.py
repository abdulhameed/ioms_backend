"""
Maintenance Celery tasks — Phase 6.

check_sla_breaches: registered in CELERY_BEAT_SCHEDULE in Phase 7.
"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def check_sla_breaches():
    """
    Flag maintenance requests that have passed their SLA deadline.
    Sets is_overdue=True, creates Notification for admin + MD, writes AuditLog.
    Does NOT re-alert requests already marked is_overdue=True.
    """
    from apps.maintenance.models import MaintenanceRequest
    from apps.users.models import AuditLog, CustomUser, Notification

    now = timezone.now()
    breached = MaintenanceRequest.objects.filter(
        status__in=["open", "assigned", "in_progress", "pending_parts"],
        sla_deadline__lt=now,
        is_overdue=False,
    )

    recipients = list(
        CustomUser.objects.filter(
            groups__name__in=["admin_full", "md"], is_active=True
        ).distinct()
    )

    count = 0
    for request in breached:
        request.is_overdue = True
        request.save(update_fields=["is_overdue", "updated_at"])

        body = (
            f"Maintenance request {request.request_code} ({request.get_priority_display()}) "
            f"has breached its SLA deadline. "
            f"Deadline was {request.sla_deadline.strftime('%Y-%m-%d %H:%M')}. "
            f"Current status: {request.status}."
        )
        for user in recipients:
            Notification.objects.create(
                recipient=user,
                notification_type="sla_warning",
                title=f"SLA Breach: {request.request_code}",
                body=body,
                resource_type="MaintenanceRequest",
                resource_id=request.id,
            )

        AuditLog.log(
            action="sla_breach_detected",
            resource_type="MaintenanceRequest",
            resource_id=request.id,
            description=f"{request.request_code} marked overdue",
        )
        count += 1

    logger.info("check_sla_breaches: %d requests marked overdue", count)
    return count
