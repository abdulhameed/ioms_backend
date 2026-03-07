"""
Notifications app Celery tasks — Phase 7.

Tasks:
  booking_checkin_reminder  — Daily 8 AM: notify Front Desk of tomorrow's check-ins
  project_deadline_alert    — Daily 9 AM: notify PM + MD of projects due within 7 days

Both tasks are registered in CELERY_BEAT_SCHEDULE in config/settings/base.py (Phase 7).
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def booking_checkin_reminder():
    """
    Runs daily at 8:00 AM (registered in beat schedule by Phase 7).
    Finds confirmed bookings with check_in_date = tomorrow and notifies
    all active Front Desk users.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.shortlets.models import Booking
    from apps.users.models import CustomUser, Notification

    tomorrow = (timezone.now() + timedelta(days=1)).date()
    bookings = Booking.objects.filter(
        check_in_date=tomorrow,
        status="confirmed",
    ).select_related("client", "apartment", "yearly_rental")

    if not bookings.exists():
        logger.info("booking_checkin_reminder: no check-ins tomorrow (%s)", tomorrow)
        return 0

    front_desk_users = CustomUser.objects.filter(
        groups__name="front_desk", is_active=True
    ).distinct()

    count = 0
    booking_count = bookings.count()
    for user in front_desk_users:
        body_lines = [f"Tomorrow's check-ins ({tomorrow}):"]
        for b in bookings:
            body_lines.append(
                f"  - {b.client.full_name} @ {b.property.name} (Ref: {b.booking_code})"
            )
        Notification.objects.create(
            recipient=user,
            notification_type="booking_reminder",
            title=f"{booking_count} check-in(s) scheduled for tomorrow ({tomorrow})",
            body="\n".join(body_lines),
            channel="in_app",
        )
        count += 1

    logger.info(
        "booking_checkin_reminder: notified %d front-desk user(s) about %d check-in(s)",
        count,
        booking_count,
    )
    return count


@shared_task
def project_deadline_alert():
    """
    Runs daily at 9:00 AM (registered in beat schedule by Phase 7).
    Finds active projects whose expected_end_date is within the next 7 days
    and notifies the project manager + all MD users.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.projects.models import Project
    from apps.users.models import CustomUser, Notification

    today = timezone.now().date()
    cutoff = today + timedelta(days=7)

    projects = Project.objects.filter(
        status__in=["planning", "in_progress", "on_hold"],
        expected_end_date__lte=cutoff,
        expected_end_date__gte=today,
    ).select_related("project_manager")

    md_users = list(CustomUser.objects.filter(role="md", is_active=True))
    count = 0

    for project in projects:
        days_left = (project.expected_end_date - today).days
        body = (
            f"Project '{project.name}' "
            f"({project.project_code or 'code pending'}) "
            f"is due in {days_left} day(s) on {project.expected_end_date}. "
            f"Current status: {project.status}."
        )

        recipients = set()
        if project.project_manager:
            recipients.add(project.project_manager)
        for md in md_users:
            recipients.add(md)

        for user in recipients:
            Notification.objects.create(
                recipient=user,
                notification_type="system",
                title=f"Project deadline approaching: {project.name}",
                body=body,
                resource_type="Project",
                resource_id=project.id,
                channel="in_app",
            )
            count += 1

    logger.info("project_deadline_alert: created %d notifications", count)
    return count
