"""
Projects Celery tasks — Phase 4.

Tasks:
  check_budget_alerts — scans ProjectBudgetLines and fires notifications at
                        80% and 95% utilization thresholds (no duplicates).
                        Registered in CELERY_BEAT_SCHEDULE in Phase 7.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def check_budget_alerts():
    """
    Runs hourly (registered in beat schedule by Phase 7).
    For each active ProjectBudgetLine:
      - First crossing of 80% → Notification to PM + MD
      - First crossing of 95% → CRITICAL Notification to MD
    Uses alerts_sent JSONField to prevent duplicate alerts.
    """
    from apps.projects.models import Project, ProjectBudgetLine
    from apps.users.models import AuditLog, CustomUser, Notification

    active_statuses = ["planning", "in_progress", "on_hold"]
    lines = ProjectBudgetLine.objects.filter(
        project__status__in=active_statuses
    ).select_related("project", "project__project_manager")

    notifications_created = 0

    for line in lines:
        utilization = line.utilization_pct
        alerts_sent = line.alerts_sent or {}
        changed = False

        # 95% threshold (CRITICAL)
        if utilization >= 95 and not alerts_sent.get("95pct"):
            md_users = CustomUser.objects.filter(role="md", is_active=True)
            for md in md_users:
                Notification.objects.create(
                    recipient=md,
                    notification_type="budget_alert",
                    title="CRITICAL: Budget line nearly exhausted",
                    body=(
                        f"Budget line '{line.category}' for project "
                        f"'{line.project.name}' has reached "
                        f"{utilization:.1f}% utilization (CRITICAL threshold)."
                    ),
                    resource_type="ProjectBudgetLine",
                    resource_id=line.id,
                    channel="email",
                )
                notifications_created += 1
            AuditLog.log(
                action="budget.critical_alert",
                resource_type="ProjectBudgetLine",
                resource_id=line.id,
                description=(
                    f"Budget line '{line.category}' for '{line.project.name}' "
                    f"reached {utilization:.1f}% utilization."
                ),
            )
            alerts_sent["95pct"] = True
            changed = True

        # 80% threshold (WARNING) — only if 95% not already triggered
        elif utilization >= 80 and not alerts_sent.get("80pct"):
            recipients = list(CustomUser.objects.filter(role="md", is_active=True))
            if line.project.project_manager:
                recipients.append(line.project.project_manager)
            for user in recipients:
                Notification.objects.create(
                    recipient=user,
                    notification_type="budget_alert",
                    title="Budget line utilization warning (80%)",
                    body=(
                        f"Budget line '{line.category}' for project "
                        f"'{line.project.name}' has reached "
                        f"{utilization:.1f}% utilization."
                    ),
                    resource_type="ProjectBudgetLine",
                    resource_id=line.id,
                    channel="in_app",
                )
                notifications_created += 1
            AuditLog.log(
                action="budget.warning_alert",
                resource_type="ProjectBudgetLine",
                resource_id=line.id,
                description=(
                    f"Budget line '{line.category}' for '{line.project.name}' "
                    f"reached {utilization:.1f}% utilization."
                ),
            )
            alerts_sent["80pct"] = True
            changed = True

        if changed:
            line.alerts_sent = alerts_sent
            line.save(update_fields=["alerts_sent"])

    logger.info("check_budget_alerts: created %d notifications", notifications_created)
    return notifications_created
