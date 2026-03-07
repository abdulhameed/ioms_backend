"""
Approvals Celery tasks — Phase 3.

Tasks:
  send_approval_notification — fires on every workflow state change
  send_pending_reminder      — checks for approvals > 24h; registered in beat in Phase 7
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_approval_notification(self, workflow_id: str, event_type: str):
    """
    Create in-app Notification rows and send emails for approval events.

    event_type values:
      submitted   — L1 approver notified
      l1_approved — L2 approver + initiator notified
      l1_rejected — initiator notified
      approved    — initiator (+ PM if project) notified
      l2_rejected — initiator + L1 approver notified
      more_info   — initiator notified
      withdrawn   — current pending approver notified
    """
    from apps.approvals.models import ApprovalWorkflow
    from apps.users.models import Notification

    try:
        workflow = ApprovalWorkflow.objects.select_related(
            "initiated_by", "l1_approver", "l2_approver"
        ).get(id=workflow_id)
    except ApprovalWorkflow.DoesNotExist:
        logger.warning("send_approval_notification: workflow %s not found", workflow_id)
        return

    recipients = []  # list of (user, channel)

    EVENT_TITLES = {
        "submitted": "Approval request pending your review",
        "l1_approved": "Approval advanced to L2",
        "l1_rejected": "Approval request rejected",
        "approved": "Approval request approved",
        "l2_rejected": "Approval request rejected at L2",
        "more_info": "More information requested on approval",
        "withdrawn": "Approval request withdrawn",
    }

    title = EVENT_TITLES.get(event_type, "Approval update")
    body = (
        f"Workflow '{workflow.workflow_type}' (ID: {workflow_id}) — {event_type}."
    )

    if event_type == "submitted":
        if workflow.l1_approver:
            recipients.append((workflow.l1_approver, "email"))
            recipients.append((workflow.l1_approver, "in_app"))

    elif event_type == "l1_approved":
        if workflow.l2_approver:
            recipients.append((workflow.l2_approver, "email"))
            recipients.append((workflow.l2_approver, "in_app"))
        recipients.append((workflow.initiated_by, "email"))
        recipients.append((workflow.initiated_by, "in_app"))

    elif event_type in ("l1_rejected", "more_info"):
        recipients.append((workflow.initiated_by, "email"))
        recipients.append((workflow.initiated_by, "in_app"))

    elif event_type == "approved":
        recipients.append((workflow.initiated_by, "email"))
        recipients.append((workflow.initiated_by, "in_app"))

    elif event_type == "l2_rejected":
        recipients.append((workflow.initiated_by, "email"))
        recipients.append((workflow.initiated_by, "in_app"))
        if workflow.l1_approver:
            recipients.append((workflow.l1_approver, "email"))
            recipients.append((workflow.l1_approver, "in_app"))

    elif event_type == "withdrawn":
        approver = workflow.l1_approver if workflow.l1_approver else workflow.l2_approver
        if approver:
            recipients.append((approver, "in_app"))

    import uuid as _uuid
    from django.conf import settings
    from django.core.mail import send_mail

    # Decide notification_type: decision events use approval_decided, others approval_pending
    DECIDED_EVENTS = {"approved", "l1_rejected", "l2_rejected", "withdrawn"}
    nfy_type = "approval_decided" if event_type in DECIDED_EVENTS else "approval_pending"

    for user, channel in recipients:
        Notification.objects.create(
            recipient=user,
            notification_type=nfy_type,
            title=title,
            body=body,
            resource_type="ApprovalWorkflow",
            resource_id=_uuid.UUID(str(workflow_id)),
            channel=channel,
        )
        if channel == "email":
            try:
                send_mail(
                    subject=f"[IOMS] {title}",
                    message=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except Exception:
                pass

    logger.info(
        "send_approval_notification: %s notifications for workflow %s event=%s",
        len(recipients),
        workflow_id,
        event_type,
    )


@shared_task
def send_pending_reminder():
    """
    Find approval workflows pending for > 24 hours and email the current approver.
    Defined here in Phase 3; registered in CELERY_BEAT_SCHEDULE in Phase 7.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.approvals.models import ApprovalWorkflow
    from apps.users.models import Notification

    threshold = timezone.now() - timedelta(hours=24)
    pending = ApprovalWorkflow.objects.filter(
        status__in=["pending_l1", "pending_l2"],
        updated_at__lte=threshold,
    ).select_related("l1_approver", "l2_approver")

    count = 0
    for workflow in pending:
        approver = workflow.current_approver
        if not approver:
            continue
        Notification.objects.create(
            recipient=approver,
            notification_type="approval_pending",
            title="Pending approval reminder",
            body=(
                f"Workflow '{workflow.workflow_type}' has been pending your approval "
                f"for more than 24 hours."
            ),
            resource_type="ApprovalWorkflow",
            resource_id=workflow.id,
            channel="email",
        )
        count += 1

    logger.info("send_pending_reminder: sent %d reminders", count)
    return count
