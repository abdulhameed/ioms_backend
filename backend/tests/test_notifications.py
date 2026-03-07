"""
Phase 7 — Notification API & Celery Beat tests.
Test IDs: NFY-01 through NFY-07.
See docs/milestone_1_PRD_v2.md section 7.3 for full specifications.
"""

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.models import CustomUser, Notification

NOTIFICATIONS_URL = "/api/v1/notifications/"
UNREAD_COUNT_URL = "/api/v1/notifications/unread-count/"
READ_ALL_URL = "/api/v1/notifications/read-all/"


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_user(django_user_model, role, perm="full", email=None):
    from django.contrib.auth.models import Group

    email = email or f"{role}_{perm}@nfy.test"
    user = django_user_model.objects.create_user(
        username=email.split("@")[0],
        email=email,
        password="Test1234!",
        role=role,
        permission_level=perm,
        is_active=True,
    )
    # Ensure group exists and assign
    group_name = f"{role}_{perm}" if role not in ("md", "front_desk") else role
    group, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(group)
    return user


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_a(django_user_model):
    return _make_user(django_user_model, "hr", "full", "user_a@nfy.test")


@pytest.fixture
def user_b(django_user_model):
    return _make_user(django_user_model, "hr", "limited", "user_b@nfy.test")


@pytest.fixture
def admin_user(django_user_model):
    return _make_user(django_user_model, "admin", "full", "admin@nfy.test")


@pytest.fixture
def md_user(django_user_model):
    return _make_user(django_user_model, "md", "full", "md@nfy.test")


def _make_notification(user, is_read=False, ntype="system"):
    return Notification.objects.create(
        recipient=user,
        notification_type=ntype,
        title="Test notification",
        body="This is a test.",
        channel="in_app",
        is_read=is_read,
    )


# ── NFY-01: unread-count returns correct number ───────────────────────────────

@pytest.mark.django_db
def test_nfy_01_unread_count(api_client, user_a):
    """GET /notifications/unread-count/ returns correct count for the authenticated user."""
    _make_notification(user_a)
    _make_notification(user_a)
    _make_notification(user_a, is_read=True)  # already read — not counted

    api_client.force_authenticate(user=user_a)
    resp = api_client.get(UNREAD_COUNT_URL)
    assert resp.status_code == 200
    assert resp.data["count"] == 2


# ── NFY-02: mark single notification read → count decrements ─────────────────

@pytest.mark.django_db
def test_nfy_02_mark_single_read(api_client, user_a):
    """POST /notifications/{id}/read/ → is_read=True, read_at set, count decrements."""
    n1 = _make_notification(user_a)
    n2 = _make_notification(user_a)

    api_client.force_authenticate(user=user_a)
    resp = api_client.post(f"{NOTIFICATIONS_URL}{n1.id}/read/")
    assert resp.status_code == 200
    assert resp.data["is_read"] is True
    assert resp.data["read_at"] is not None

    # Unread count decremented from 2 → 1
    count_resp = api_client.get(UNREAD_COUNT_URL)
    assert count_resp.data["count"] == 1


# ── NFY-03: mark-all-read → all marked read, count = 0 ───────────────────────

@pytest.mark.django_db
def test_nfy_03_mark_all_read(api_client, user_a):
    """POST /notifications/read-all/ marks all unread as read; count becomes 0."""
    _make_notification(user_a)
    _make_notification(user_a)
    _make_notification(user_a)

    api_client.force_authenticate(user=user_a)
    resp = api_client.post(READ_ALL_URL)
    assert resp.status_code == 200
    assert resp.data["marked_read"] == 3

    count_resp = api_client.get(UNREAD_COUNT_URL)
    assert count_resp.data["count"] == 0

    # Verify all are truly read in DB
    assert Notification.objects.filter(recipient=user_a, is_read=False).count() == 0


# ── NFY-04: recipient isolation — user A cannot see user B's notifications ────

@pytest.mark.django_db
def test_nfy_04_recipient_isolation(api_client, user_a, user_b):
    """GET /notifications/ returns only the authenticated user's notifications."""
    _make_notification(user_a)
    _make_notification(user_a)
    _make_notification(user_b)  # belongs to user_b

    api_client.force_authenticate(user=user_a)
    resp = api_client.get(NOTIFICATIONS_URL)
    assert resp.status_code == 200

    # Paginated response
    results = resp.data["results"]
    assert len(results) == 2
    recipient_user_b_id = str(user_b.id)
    # None of user_a's results should be user_b's notifications
    notif_ids = {str(r["id"]) for r in results}
    user_b_notif_id = str(Notification.objects.filter(recipient=user_b).first().id)
    assert user_b_notif_id not in notif_ids


# ── NFY-05: check_sla_breaches creates Notification rows ─────────────────────

@pytest.mark.django_db
def test_nfy_05_sla_breach_creates_notification(admin_user, md_user):
    """check_sla_breaches task creates sla_warning Notification rows for admin + MD."""
    from apps.maintenance.models import MaintenanceRequest
    from apps.maintenance.services import MaintenanceService
    from apps.maintenance.tasks import check_sla_breaches

    req = MaintenanceService.create_request(
        {
            "issue_type": "plumbing",
            "location_type": "office",
            "location_details": "Ground floor",
            "priority": "high",
            "description": "Burst pipe.",
        },
        actor=admin_user,
    )
    # Force SLA deadline into the past
    MaintenanceRequest.objects.filter(id=req.id).update(
        sla_deadline=timezone.now() - timedelta(hours=1)
    )

    before_count = Notification.objects.filter(notification_type="sla_warning").count()
    check_sla_breaches()

    new_notifications = Notification.objects.filter(
        notification_type="sla_warning",
        resource_type="MaintenanceRequest",
        resource_id=req.id,
    )
    assert new_notifications.count() >= 1

    req.refresh_from_db()
    assert req.is_overdue is True


# ── NFY-06: check_budget_alerts creates budget_alert Notification ─────────────

@pytest.mark.django_db
def test_nfy_06_budget_alert_creates_notification(md_user):
    """check_budget_alerts task creates budget_alert Notification with correct resource_id."""
    from apps.projects.models import Project, ProjectBudgetLine
    from apps.projects.tasks import check_budget_alerts

    pm_user = CustomUser.objects.create_user(
        username="pm_nfy06",
        email="pm_nfy06@nfy.test",
        password="Test1234!",
        role="pm",
        permission_level="full",
        is_active=True,
    )
    project = Project.objects.create(
        name="NFY-06 Project",
        project_type="commercial",
        location_text="Lagos",
        start_date="2026-01-01",
        expected_end_date="2026-12-31",
        budget_total=Decimal("1000000.00"),
        scope="Test project.",
        project_manager=pm_user,
        created_by=pm_user,
        status="in_progress",
    )
    budget_line = ProjectBudgetLine.objects.create(
        project=project,
        category="materials",
        allocated_amount=Decimal("1000000.00"),
        committed_amount=Decimal("850000.00"),  # 85% — above 80% threshold
    )

    check_budget_alerts()

    notif = Notification.objects.filter(
        notification_type="budget_alert",
        resource_type="ProjectBudgetLine",
        resource_id=budget_line.id,
    )
    assert notif.exists()


# ── NFY-07: approval_decided email sent to console ───────────────────────────

@pytest.mark.django_db
def test_nfy_07_approval_decided_email(django_user_model):
    """
    When a workflow is approved, send_approval_notification fires an email
    for channel='email' recipients. Verify send_mail is called with correct args.
    """
    from apps.approvals.models import ApprovalWorkflow
    from apps.approvals.services import ApprovalService
    from apps.approvals.tasks import send_approval_notification

    initiator = _make_user(django_user_model, "pm", "full", "initiator_nfy07@nfy.test")
    l1_user = _make_user(django_user_model, "hr", "full", "l1_nfy07@nfy.test")
    md = _make_user(django_user_model, "md", "full", "md_nfy07@nfy.test")

    workflow = ApprovalWorkflow.objects.create(
        workflow_type="project_proposal",
        initiated_by=initiator,
        l1_approver=l1_user,
        l2_approver=md,
        requires_l2=True,
        status="pending_l2",
        l1_decision="approved",
    )

    with patch("django.core.mail.send_mail") as mock_send:
        send_approval_notification(str(workflow.id), "approved")

    # send_mail should have been called at least once (for email channel recipients)
    assert mock_send.called
    # The call should include the initiator's email as a recipient
    all_recipient_lists = [call.kwargs.get("recipient_list", call.args[3] if len(call.args) > 3 else [])
                           for call in mock_send.call_args_list]
    flat_recipients = [email for lst in all_recipient_lists for email in lst]
    assert initiator.email in flat_recipients

    # Notification rows created in DB with approval_decided type
    assert Notification.objects.filter(
        notification_type="approval_decided",
        resource_id=workflow.id,
    ).exists()


# ── Edge cases ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_unread_count_zero_for_new_user(api_client, user_a):
    """User with no notifications gets count = 0."""
    api_client.force_authenticate(user=user_a)
    resp = api_client.get(UNREAD_COUNT_URL)
    assert resp.status_code == 200
    assert resp.data["count"] == 0


@pytest.mark.django_db
def test_mark_already_read_notification_is_idempotent(api_client, user_a):
    """Marking an already-read notification read again returns 200 without error."""
    n = _make_notification(user_a, is_read=True)

    api_client.force_authenticate(user=user_a)
    resp = api_client.post(f"{NOTIFICATIONS_URL}{n.id}/read/")
    assert resp.status_code == 200
    assert resp.data["is_read"] is True


@pytest.mark.django_db
def test_cannot_read_another_users_notification(api_client, user_a, user_b):
    """User A cannot mark User B's notification as read → 404."""
    n = _make_notification(user_b)
    api_client.force_authenticate(user=user_a)
    resp = api_client.post(f"{NOTIFICATIONS_URL}{n.id}/read/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_filter_by_is_read_false(api_client, user_a):
    """GET /notifications/?is_read=false returns only unread notifications."""
    _make_notification(user_a, is_read=False)
    _make_notification(user_a, is_read=True)
    _make_notification(user_a, is_read=False)

    api_client.force_authenticate(user=user_a)
    resp = api_client.get(f"{NOTIFICATIONS_URL}?is_read=false")
    assert resp.status_code == 200
    results = resp.data["results"]
    assert len(results) == 2
    for r in results:
        assert r["is_read"] is False


@pytest.mark.django_db
def test_filter_by_notification_type(api_client, user_a):
    """GET /notifications/?type=sla_warning returns only that type."""
    _make_notification(user_a, ntype="sla_warning")
    _make_notification(user_a, ntype="system")

    api_client.force_authenticate(user=user_a)
    resp = api_client.get(f"{NOTIFICATIONS_URL}?type=sla_warning")
    assert resp.status_code == 200
    results = resp.data["results"]
    assert len(results) == 1
    assert results[0]["notification_type"] == "sla_warning"


@pytest.mark.django_db
def test_unauthenticated_cannot_access_notifications(api_client):
    """Unauthenticated request → 401."""
    resp = api_client.get(NOTIFICATIONS_URL)
    assert resp.status_code == 401


@pytest.mark.django_db
def test_read_all_only_marks_own_notifications(api_client, user_a, user_b):
    """POST /notifications/read-all/ only affects current user's notifications."""
    _make_notification(user_a)
    n_b = _make_notification(user_b)

    api_client.force_authenticate(user=user_a)
    api_client.post(READ_ALL_URL)

    n_b.refresh_from_db()
    assert n_b.is_read is False  # user_b's notification untouched


@pytest.mark.django_db
def test_booking_checkin_reminder_no_checkins(django_user_model):
    """booking_checkin_reminder returns 0 when no bookings tomorrow."""
    from apps.notifications.tasks import booking_checkin_reminder

    result = booking_checkin_reminder()
    assert result == 0


@pytest.mark.django_db
def test_project_deadline_alert_no_deadlines(django_user_model):
    """project_deadline_alert returns 0 when no projects due within 7 days."""
    from apps.notifications.tasks import project_deadline_alert

    result = project_deadline_alert()
    assert result == 0


@pytest.mark.django_db
def test_dashboard_cache_refresh_sets_cache():
    """dashboard_cache_refresh sets 'projects_dashboard' key in Redis cache."""
    from django.core.cache import cache

    from apps.projects.tasks import dashboard_cache_refresh

    cache.delete("projects_dashboard")
    dashboard_cache_refresh()
    data = cache.get("projects_dashboard")
    assert data is not None
    assert "total" in data
    assert "by_status" in data


@pytest.mark.django_db
def test_audit_log_archive_removes_old_entries(admin_user):
    """audit_log_archive deletes AuditLog entries older than 7 years."""
    from apps.users.models import AuditLog
    from apps.users.tasks import audit_log_archive

    # Create an old log entry (8 years ago)
    old_entry = AuditLog.objects.create(
        action="test.old_event",
        user=admin_user,
        resource_type="Test",
        description="Old log",
    )
    AuditLog.objects.filter(id=old_entry.id).update(
        timestamp=timezone.now() - timedelta(days=365 * 8)
    )

    # Create a recent log entry (should not be deleted)
    recent_entry = AuditLog.objects.create(
        action="test.recent_event",
        user=admin_user,
        resource_type="Test",
        description="Recent log",
    )

    result = audit_log_archive()
    assert result >= 1
    assert not AuditLog.objects.filter(id=old_entry.id).exists()
    assert AuditLog.objects.filter(id=recent_entry.id).exists()
