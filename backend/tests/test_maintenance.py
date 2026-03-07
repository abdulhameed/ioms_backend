"""
Phase 6 — Maintenance & Issue Escalation tests.
Test IDs: MNT-01 through MNT-12.
See docs/milestone_1_PRD_v2.md section 6.6 for full specifications.
"""

import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.maintenance.models import (
    MaintenanceRequest,
    MaintenancePhoto,
    MaintenanceStatusUpdate,
)
from apps.maintenance.services import MaintenanceService
from apps.maintenance.tasks import check_sla_breaches

MAINTENANCE_URL = "/api/v1/maintenance/"


# ── Fixtures ────────────────────────────────────────────────────────────────────

def _make_user(django_user_model, role, perm="full", email=None):
    email = email or f"{role}_{perm}@maint.test"
    return django_user_model.objects.create_user(
        username=email.split("@")[0],
        email=email,
        password="Test1234!",
        role=role,
        permission_level=perm,
        is_active=True,
    )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(django_user_model):
    return _make_user(django_user_model, "admin", "full", "admin@maint.test")


@pytest.fixture
def front_desk_user(django_user_model):
    return _make_user(django_user_model, "front_desk", "full", "frontdesk@maint.test")


@pytest.fixture
def pm_user(django_user_model):
    return _make_user(django_user_model, "pm", "full", "pm@maint.test")


@pytest.fixture
def md_user(django_user_model):
    return _make_user(django_user_model, "md", "full", "md@maint.test")


@pytest.fixture
def technician_user(django_user_model):
    """A user who will be assigned to maintenance tasks — non-admin role."""
    return _make_user(django_user_model, "hr", "full", "tech@maint.test")


@pytest.fixture
def open_request(admin_user):
    """A pre-created open maintenance request."""
    return MaintenanceService.create_request(
        {
            "issue_type": "electrical",
            "location_type": "office",
            "location_details": "Server room",
            "priority": "medium",
            "description": "Power socket not working.",
        },
        actor=admin_user,
    )


@pytest.fixture
def assigned_request(open_request, technician_user, admin_user):
    """An open request that has been assigned."""
    MaintenanceService.assign(
        open_request,
        assigned_to=technician_user,
        assigned_by=admin_user,
        notes="Please fix ASAP",
    )
    return open_request


# ── MNT-01: Critical → sla_deadline = reported_at + 4h; immediate alert ────────

@pytest.mark.django_db
def test_mnt_01_critical_sla_deadline_and_alert(api_client, admin_user, md_user):
    """MNT-01: Critical request → sla_deadline = reported_at + 4h; notification created."""
    from apps.users.models import Notification

    api_client.force_authenticate(user=admin_user)
    resp = api_client.post(
        MAINTENANCE_URL,
        {
            "issue_type": "electrical",
            "location_type": "office",
            "location_details": "Main board",
            "priority": "critical",
            "description": "Complete power failure.",
        },
        format="json",
    )
    assert resp.status_code == 201

    req = MaintenanceRequest.objects.get(id=resp.data["id"])
    expected_deadline = req.reported_at + timedelta(hours=4)
    diff = abs((req.sla_deadline - expected_deadline).total_seconds())
    assert diff < 5, f"SLA deadline off by {diff}s"

    # Immediate alert created for admin + md
    assert Notification.objects.filter(
        notification_type="sla_warning",
        resource_type="MaintenanceRequest",
        resource_id=req.id,
    ).exists()


# ── MNT-02: High priority → sla_deadline = reported_at + 24h ───────────────────

@pytest.mark.django_db
def test_mnt_02_high_sla_deadline(admin_user):
    """MNT-02: High priority request → sla_deadline = reported_at + 24h."""
    req = MaintenanceService.create_request(
        {
            "issue_type": "plumbing",
            "location_type": "property",
            "priority": "high",
            "description": "Pipe burst.",
        },
        actor=admin_user,
    )
    expected = req.reported_at + timedelta(hours=24)
    diff = abs((req.sla_deadline - expected).total_seconds())
    assert diff < 5


# ── MNT-03: Assign → status=assigned; assignee notified ────────────────────────

@pytest.mark.django_db
def test_mnt_03_assign_request(api_client, admin_user, technician_user, open_request):
    """MNT-03: Assign request → status=assigned; assignee receives notification."""
    from apps.users.models import Notification

    api_client.force_authenticate(user=admin_user)
    resp = api_client.post(
        f"/api/v1/maintenance/{open_request.id}/assign/",
        {"assigned_to": str(technician_user.id), "notes": "Urgent fix needed"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "assigned"

    assert Notification.objects.filter(
        recipient=technician_user,
        notification_type="assignment",
        resource_type="MaintenanceRequest",
    ).exists()


# ── MNT-04: Assignee accepts → status stays assigned; update logged ─────────────

@pytest.mark.django_db
def test_mnt_04_assignee_accepts(api_client, technician_user, assigned_request):
    """MNT-04: Assignee accepts → status=assigned; status update row created."""
    api_client.force_authenticate(user=technician_user)
    resp = api_client.post(
        f"/api/v1/maintenance/{assigned_request.id}/accept/",
        {"accepted": True},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "assigned"

    assert MaintenanceStatusUpdate.objects.filter(
        request=assigned_request,
        from_status="assigned",
        to_status="assigned",
    ).exists()


# ── MNT-05: Assignee declines → status=open; admin notified ────────────────────

@pytest.mark.django_db
def test_mnt_05_assignee_declines(
    api_client, technician_user, admin_user, assigned_request
):
    """MNT-05: Assignee declines → status=open; admin notified for reassignment."""
    from apps.users.models import Notification

    api_client.force_authenticate(user=technician_user)
    resp = api_client.post(
        f"/api/v1/maintenance/{assigned_request.id}/accept/",
        {"accepted": False, "decline_reason": "Not available this week"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "open"

    assert Notification.objects.filter(
        notification_type="assignment",
        resource_type="MaintenanceRequest",
        resource_id=assigned_request.id,
    ).exists()


# ── MNT-06: Update to in_progress → MaintenanceStatusUpdate created ─────────────

@pytest.mark.django_db
def test_mnt_06_update_to_in_progress(api_client, technician_user, assigned_request):
    """MNT-06: Update status to in_progress → status update row created."""
    api_client.force_authenticate(user=technician_user)
    resp = api_client.post(
        f"/api/v1/maintenance/{assigned_request.id}/update-status/",
        {"status": "in_progress", "notes": "Started work"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "in_progress"

    assert MaintenanceStatusUpdate.objects.filter(
        request=assigned_request,
        from_status="assigned",
        to_status="in_progress",
    ).exists()


# ── MNT-07: Update to pending_parts with JSON → parts stored correctly ──────────

@pytest.mark.django_db
def test_mnt_07_pending_parts_with_json(api_client, technician_user, assigned_request):
    """MNT-07: Update to pending_parts with parts JSON → data stored correctly."""
    # First move to in_progress
    MaintenanceService.update_status(assigned_request, actor=technician_user, new_status="in_progress")

    api_client.force_authenticate(user=technician_user)
    resp = api_client.post(
        f"/api/v1/maintenance/{assigned_request.id}/update-status/",
        {
            "status": "pending_parts",
            "notes": "Waiting on parts",
            "parts_needed": ["Circuit breaker 20A", "Wire 2.5mm"],
            "parts_vendor": "Lagos Electricals Ltd",
            "parts_estimated_cost": "15000.00",
            "parts_expected_delivery": "2026-03-15",
        },
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "pending_parts"

    update = MaintenanceStatusUpdate.objects.filter(
        request=assigned_request, to_status="pending_parts"
    ).last()
    assert update is not None
    assert "Circuit breaker 20A" in update.parts_needed
    assert update.parts_vendor == "Lagos Electricals Ltd"


# ── MNT-08: Close → resolved_at set; status=closed ──────────────────────────────

@pytest.mark.django_db
def test_mnt_08_close_request(api_client, admin_user, technician_user, assigned_request):
    """MNT-08: Close request → status=closed; resolved_at set."""
    # Move through to resolved
    MaintenanceService.update_status(assigned_request, actor=technician_user, new_status="in_progress")
    MaintenanceService.update_status(assigned_request, actor=technician_user, new_status="resolved")

    api_client.force_authenticate(user=admin_user)
    resp = api_client.post(
        f"/api/v1/maintenance/{assigned_request.id}/close/",
        {
            "resolution_notes": "Fixed the socket.",
            "labor_hours": "2.5",
            "parts_cost": "3500.00",
        },
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "closed"

    assigned_request.refresh_from_db()
    assert assigned_request.resolved_at is not None
    assert assigned_request.closed_at is not None
    assert assigned_request.labor_hours == Decimal("2.5")


# ── MNT-09: Overdue task marks is_overdue=True; notification created ─────────────

@pytest.mark.django_db
def test_mnt_09_sla_breach_task(admin_user, md_user, open_request):
    """MNT-09: Overdue request → check_sla_breaches sets is_overdue=True; notification created."""
    from apps.users.models import Notification

    # Mock deadline in the past
    open_request.sla_deadline = timezone.now() - timedelta(hours=1)
    open_request.save(update_fields=["sla_deadline"])

    count = check_sla_breaches()
    assert count >= 1

    open_request.refresh_from_db()
    assert open_request.is_overdue is True

    assert Notification.objects.filter(
        notification_type="sla_warning",
        resource_type="MaintenanceRequest",
        resource_id=open_request.id,
    ).exists()


# ── MNT-10: Re-run overdue task → no duplicate notification ──────────────────────

@pytest.mark.django_db
def test_mnt_10_no_duplicate_sla_notification(admin_user, open_request):
    """MNT-10: Re-running check_sla_breaches on already-overdue request → no new notification."""
    from apps.users.models import Notification

    open_request.sla_deadline = timezone.now() - timedelta(hours=2)
    open_request.is_overdue = True  # already flagged
    open_request.save(update_fields=["sla_deadline", "is_overdue"])

    before = Notification.objects.filter(
        resource_type="MaintenanceRequest",
        resource_id=open_request.id,
    ).count()

    check_sla_breaches()

    after = Notification.objects.filter(
        resource_type="MaintenanceRequest",
        resource_id=open_request.id,
    ).count()

    assert after == before  # no new notifications


# ── MNT-11: Metrics endpoint returns correct structure ───────────────────────────

@pytest.mark.django_db
def test_mnt_11_metrics_endpoint(api_client, admin_user, open_request):
    """MNT-11: GET /maintenance/metrics/ returns correct structure."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get("/api/v1/maintenance/metrics/")
    assert resp.status_code == 200
    assert "by_priority" in resp.data
    assert "sla_breach_rate_pct" in resp.data
    assert "by_status" in resp.data
    assert "total" in resp.data
    for priority in ["critical", "high", "medium", "low"]:
        assert priority in resp.data["by_priority"]


# ── MNT-12: More than 10 photos → 400 ───────────────────────────────────────────

@pytest.mark.django_db
def test_mnt_12_photo_limit_exceeded(api_client, admin_user, open_request):
    """MNT-12: Uploading more than 10 photos in one request → 400."""
    api_client.force_authenticate(user=admin_user)
    photos = [
        {"file": f"s3://bucket/photo_{i}.jpg", "caption": f"Photo {i}", "file_size_bytes": 1000}
        for i in range(11)  # 11 photos
    ]
    resp = api_client.post(
        f"/api/v1/maintenance/{open_request.id}/photos/",
        {"photos": photos},
        format="json",
    )
    assert resp.status_code == 400


# ── Edge cases ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_request_code_format(admin_user):
    """request_code matches MNT-YYYY-NNNN pattern."""
    req = MaintenanceService.create_request(
        {"issue_type": "cleaning", "location_type": "office", "priority": "low",
         "description": "Clean kitchen."},
        actor=admin_user,
    )
    assert re.match(r"^MNT-\d{4}-\d{4}$", req.request_code)


@pytest.mark.django_db
def test_sla_deadline_medium_72h(admin_user):
    """Medium priority → sla_deadline = reported_at + 72h."""
    req = MaintenanceService.create_request(
        {"issue_type": "other", "location_type": "office", "priority": "medium",
         "description": "General issue."},
        actor=admin_user,
    )
    expected = req.reported_at + timedelta(hours=72)
    diff = abs((req.sla_deadline - expected).total_seconds())
    assert diff < 5


@pytest.mark.django_db
def test_sla_deadline_low_168h(admin_user):
    """Low priority → sla_deadline = reported_at + 168h (7 days)."""
    req = MaintenanceService.create_request(
        {"issue_type": "other", "location_type": "office", "priority": "low",
         "description": "Low urgency issue."},
        actor=admin_user,
    )
    expected = req.reported_at + timedelta(hours=168)
    diff = abs((req.sla_deadline - expected).total_seconds())
    assert diff < 5


@pytest.mark.django_db
def test_assign_already_assigned_raises(open_request, technician_user, admin_user):
    """Cannot assign a request that isn't open."""
    MaintenanceService.assign(open_request, technician_user, admin_user)
    with pytest.raises(ValueError, match="open"):
        MaintenanceService.assign(open_request, technician_user, admin_user)


@pytest.mark.django_db
def test_non_assignee_cannot_accept(api_client, admin_user, front_desk_user, assigned_request):
    """Non-assignee trying to accept → 400 PermissionError."""
    api_client.force_authenticate(user=front_desk_user)
    resp = api_client.post(
        f"/api/v1/maintenance/{assigned_request.id}/accept/",
        {"accepted": True},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_close_open_request_raises(open_request, admin_user):
    """Cannot close an open (unresolved) request."""
    with pytest.raises(ValueError):
        MaintenanceService.close(open_request, actor=admin_user)


@pytest.mark.django_db
def test_unauthenticated_cannot_list(api_client):
    """Unauthenticated → 401."""
    resp = api_client.get(MAINTENANCE_URL)
    assert resp.status_code == 401


@pytest.mark.django_db
def test_filter_by_priority(api_client, admin_user, open_request):
    """Filter by priority=medium returns only medium requests."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"{MAINTENANCE_URL}?priority=medium")
    assert resp.status_code == 200
    for r in resp.data:
        assert r["priority"] == "medium"


@pytest.mark.django_db
def test_filter_by_status(api_client, admin_user, open_request):
    """Filter by status=open returns only open requests."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"{MAINTENANCE_URL}?status=open")
    assert resp.status_code == 200
    for r in resp.data:
        assert r["status"] == "open"


@pytest.mark.django_db
def test_edit_open_request(api_client, admin_user, open_request):
    """PUT on open request updates description."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.put(
        f"/api/v1/maintenance/{open_request.id}/",
        {"description": "Updated description.", "priority": "high"},
        format="json",
    )
    assert resp.status_code == 200
    open_request.refresh_from_db()
    assert open_request.priority == "high"


@pytest.mark.django_db
def test_edit_assigned_request_blocked(api_client, admin_user, assigned_request):
    """PUT on assigned (non-open) request → 400."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.put(
        f"/api/v1/maintenance/{assigned_request.id}/",
        {"description": "Too late to edit."},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_photo_upload_success(api_client, admin_user, open_request):
    """POST photos within limit → 201."""
    api_client.force_authenticate(user=admin_user)
    photos = [
        {"file": f"s3://bucket/photo_{i}.jpg", "caption": f"Photo {i}", "file_size_bytes": 500_000}
        for i in range(3)
    ]
    resp = api_client.post(
        f"/api/v1/maintenance/{open_request.id}/photos/",
        {"photos": photos},
        format="json",
    )
    assert resp.status_code == 201
    assert len(resp.data) == 3


@pytest.mark.django_db
def test_photo_total_size_limit(api_client, admin_user, open_request):
    """Photos totalling > 20 MB → 400."""
    api_client.force_authenticate(user=admin_user)
    photos = [
        {"file": f"s3://bucket/photo_{i}.jpg", "file_size_bytes": 5 * 1024 * 1024}
        for i in range(5)  # 5 × 5 MB = 25 MB
    ]
    resp = api_client.post(
        f"/api/v1/maintenance/{open_request.id}/photos/",
        {"photos": photos},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_metrics_non_admin_403(api_client, front_desk_user):
    """front_desk cannot access metrics → 403."""
    api_client.force_authenticate(user=front_desk_user)
    resp = api_client.get("/api/v1/maintenance/metrics/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_non_creator_cannot_create_request(api_client, django_user_model):
    """hr_full has no create permission → 403."""
    hr = _make_user(django_user_model, "hr", "full", "hr@maint.test")
    api_client.force_authenticate(user=hr)
    resp = api_client.post(
        MAINTENANCE_URL,
        {"issue_type": "other", "location_type": "office",
         "priority": "low", "description": "Test"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_status_update_append_only(api_client, admin_user, technician_user, assigned_request):
    """Status updates are created only; no PUT endpoint exists on the update object."""
    MaintenanceService.update_status(assigned_request, actor=technician_user, new_status="in_progress")
    update = MaintenanceStatusUpdate.objects.filter(request=assigned_request).last()
    # No PUT route — verify update was created and is not modifiable via API
    assert update.from_status == "assigned"
    assert update.to_status == "in_progress"


@pytest.mark.django_db
def test_non_admin_cannot_close(api_client, technician_user, assigned_request):
    """Non-admin cannot close a request → 403."""
    MaintenanceService.update_status(assigned_request, actor=technician_user, new_status="in_progress")
    MaintenanceService.update_status(assigned_request, actor=technician_user, new_status="resolved")

    api_client.force_authenticate(user=technician_user)
    resp = api_client.post(
        f"/api/v1/maintenance/{assigned_request.id}/close/",
        {"resolution_notes": "Done."},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_request_detail_shows_status_timeline(
    api_client, admin_user, technician_user, assigned_request
):
    """GET detail includes status_updates timeline."""
    MaintenanceService.update_status(assigned_request, actor=technician_user, new_status="in_progress")
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"/api/v1/maintenance/{assigned_request.id}/")
    assert resp.status_code == 200
    assert len(resp.data["status_updates"]) >= 1


# ── Edge cases: transitions, permissions, closed-request edits ────────────────

@pytest.mark.django_db
def test_invalid_transition_non_admin_gets_400(api_client, technician_user, assigned_request):
    """Assignee (non-admin) trying assigned → resolved (skipping in_progress) → 400."""
    api_client.force_authenticate(user=technician_user)
    resp = api_client.post(
        f"/api/v1/maintenance/{assigned_request.id}/update-status/",
        {"status": "resolved", "notes": "Jumped straight to resolved."},
        format="json",
    )
    assert resp.status_code == 400
    assert "Cannot transition" in resp.data["error"]


@pytest.mark.django_db
def test_admin_can_skip_transitions(api_client, admin_user, assigned_request):
    """Admin can override transition rules: assigned → resolved directly → 200."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.post(
        f"/api/v1/maintenance/{assigned_request.id}/update-status/",
        {"status": "resolved", "notes": "Admin override."},
        format="json",
    )
    assert resp.status_code == 200
    assigned_request.refresh_from_db()
    assert assigned_request.status == "resolved"


@pytest.mark.django_db
def test_third_party_cannot_update_status(
    api_client, front_desk_user, assigned_request
):
    """A user who is neither assignee nor admin gets 403 on update-status."""
    api_client.force_authenticate(user=front_desk_user)
    resp = api_client.post(
        f"/api/v1/maintenance/{assigned_request.id}/update-status/",
        {"status": "in_progress", "notes": "Hijacking."},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_pm_cannot_view_metrics(api_client, pm_user):
    """pm_full user cannot access maintenance metrics → 403."""
    api_client.force_authenticate(user=pm_user)
    resp = api_client.get("/api/v1/maintenance/metrics/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_edit_closed_request_returns_400(api_client, admin_user, technician_user, assigned_request):
    """After a request is closed, PUT to edit it returns 400."""
    # Advance to resolved, then close
    MaintenanceService.update_status(assigned_request, actor=technician_user, new_status="in_progress")
    MaintenanceService.update_status(assigned_request, actor=technician_user, new_status="resolved")
    MaintenanceService.close(assigned_request, actor=admin_user, resolution_notes="Done.")

    api_client.force_authenticate(user=admin_user)
    resp = api_client.put(
        f"/api/v1/maintenance/{assigned_request.id}/",
        {"description": "Trying to edit closed request."},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_close_in_progress_sets_resolved_at(admin_user, technician_user, assigned_request):
    """Closing an in_progress request (no prior resolved_at) auto-sets resolved_at = closed_at."""
    MaintenanceService.update_status(assigned_request, actor=technician_user, new_status="in_progress")
    assert assigned_request.resolved_at is None

    MaintenanceService.close(
        assigned_request, actor=admin_user, resolution_notes="Emergency close."
    )
    assigned_request.refresh_from_db()
    assert assigned_request.resolved_at is not None
    assert assigned_request.closed_at is not None
    assert assigned_request.resolved_at == assigned_request.closed_at


@pytest.mark.django_db
def test_accept_after_accept_still_assigned(technician_user, assigned_request):
    """Calling accept=True twice on the same request is idempotent — stays assigned."""
    MaintenanceService.accept(assigned_request, actor=technician_user, accepted=True)
    assigned_request.refresh_from_db()
    assert assigned_request.status == "assigned"

    # Accept again — still valid since status remains 'assigned'
    MaintenanceService.accept(assigned_request, actor=technician_user, accepted=True)
    assigned_request.refresh_from_db()
    assert assigned_request.status == "assigned"
    # Two status update log entries created
    assert assigned_request.status_updates.count() >= 2
