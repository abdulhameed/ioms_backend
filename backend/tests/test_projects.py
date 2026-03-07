"""
Phase 4 — Project & Site Management tests.
PROJ-01 through PROJ-15 (PRD-required) + edge cases.
"""

import re
import pytest
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache

from apps.approvals.models import ApprovalWorkflow
from apps.approvals.services import ApprovalService
from apps.projects.models import (
    Project,
    ProjectBudgetLine,
    ProjectDocument,
    ProjectMilestone,
    Requisition,
    RequisitionLineItem,
    SiteReport,
    SiteReportMaterial,
)
from apps.projects.services import ProjectService, RequisitionService
from apps.projects.tasks import check_budget_alerts
from apps.users.models import Notification

PROJECTS_URL = "/api/v1/projects/"
DASHBOARD_URL = "/api/v1/projects/dashboard/"


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def pm_user(django_user_model):
    return django_user_model.objects.create_user(
        username="pm_user",
        email="pm@proj.com",
        password="Test1234!",
        role="pm",
        permission_level="full",
        is_active=True,
    )


@pytest.fixture
def pm_limited_user(django_user_model):
    return django_user_model.objects.create_user(
        username="pm_limited",
        email="pm_limited@proj.com",
        password="Test1234!",
        role="pm",
        permission_level="limited",
        is_active=True,
    )


@pytest.fixture
def md_user(django_user_model):
    return django_user_model.objects.create_user(
        username="md_user",
        email="md@proj.com",
        password="Test1234!",
        role="md",
        permission_level="full",
        is_active=True,
    )


@pytest.fixture
def l1_user(django_user_model):
    """hr_full — L1 approver for workflows."""
    return django_user_model.objects.create_user(
        username="l1_proj",
        email="l1_proj@proj.com",
        password="Test1234!",
        role="hr",
        permission_level="full",
        is_active=True,
    )


@pytest.fixture
def draft_project(pm_user):
    return Project.objects.create(
        name="Test Project Alpha",
        project_type="commercial",
        location_text="Lagos, Nigeria",
        start_date="2026-04-01",
        expected_end_date="2026-12-31",
        budget_total=Decimal("2000000.00"),
        scope="Full commercial build.",
        project_manager=pm_user,
        created_by=pm_user,
    )


@pytest.fixture
def budget_line(draft_project):
    return ProjectBudgetLine.objects.create(
        project=draft_project,
        category="materials",
        allocated_amount=Decimal("1000000.00"),
    )


# ── PROJ-01: PM creates project → status=draft; project_code=null ─────────────

@pytest.mark.django_db
def test_proj_01_create_project(api_client, pm_user):
    """PROJ-01: PM creates project → status=draft, project_code=null."""
    api_client.force_authenticate(user=pm_user)
    resp = api_client.post(
        PROJECTS_URL,
        {
            "name": "New Commercial Tower",
            "project_type": "commercial",
            "location_text": "Abuja",
            "start_date": "2026-05-01",
            "expected_end_date": "2027-05-01",
            "budget_total": "5000000.00",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == "draft"
    assert resp.data["project_code"] is None


# ── PROJ-02: Submit project → ApprovalWorkflow created, status=pending_l1 ─────

@pytest.mark.django_db
def test_proj_02_submit_project(api_client, draft_project, pm_user, l1_user, md_user):
    """PROJ-02: POST /submit/ creates an ApprovalWorkflow and sets status=pending_l1."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        api_client.force_authenticate(user=pm_user)
        resp = api_client.post(f"/api/v1/projects/{draft_project.id}/submit/")

    assert resp.status_code == 200, resp.data
    draft_project.refresh_from_db()
    assert draft_project.status == "pending_l1"

    workflow = ApprovalWorkflow.objects.filter(
        workflow_type="project_proposal",
        object_id=draft_project.id,
    ).first()
    assert workflow is not None
    assert workflow.status == "pending_l1"
    assert workflow.requires_l2 is True


# ── PROJ-03: Full L1+L2 approval → project_code assigned, status=planning ─────

@pytest.mark.django_db
def test_proj_03_full_approval_assigns_code(
    api_client, draft_project, pm_user, l1_user, md_user
):
    """PROJ-03: After L1+L2 approval, project_code=PROJ-YYYY-NNN, status=planning."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        ProjectService.submit(draft_project, pm_user)
        workflow = ApprovalWorkflow.objects.get(
            workflow_type="project_proposal", object_id=draft_project.id
        )
        # L1 approve
        ApprovalService.decide(workflow, workflow.l1_approver, "approved", "Good.")
        # L2 approve
        ApprovalService.decide(workflow, workflow.l2_approver, "approved", "Approved.")

    draft_project.refresh_from_db()
    assert draft_project.status == "planning"
    assert draft_project.project_code is not None
    assert re.match(r"^PROJ-\d{4}-\d{3}$", draft_project.project_code)


# ── PROJ-04: Edit project after submission → 400 ──────────────────────────────

@pytest.mark.django_db
def test_proj_04_edit_after_submission_blocked(
    api_client, draft_project, pm_user, l1_user, md_user
):
    """PROJ-04: PUT on a submitted project returns 400."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        ProjectService.submit(draft_project, pm_user)

    api_client.force_authenticate(user=pm_user)
    resp = api_client.put(
        f"/api/v1/projects/{draft_project.id}/",
        {"name": "New Name Attempt"},
        format="json",
    )
    assert resp.status_code == 400


# ── PROJ-05: Milestone completed → progress_pct auto-updated ──────────────────

@pytest.mark.django_db
def test_proj_05_milestone_completion_updates_progress(draft_project, pm_user):
    """PROJ-05: Completing milestone triggers progress_pct recalculation."""
    m1 = ProjectMilestone.objects.create(
        project=draft_project, title="Foundation", target_date="2026-05-01"
    )
    ProjectMilestone.objects.create(
        project=draft_project, title="Structure", target_date="2026-06-01"
    )
    draft_project.refresh_from_db()
    assert draft_project.progress_pct == 0

    m1.status = "completed"
    m1.save()

    draft_project.refresh_from_db()
    assert draft_project.progress_pct == Decimal("50.00")


# ── PROJ-06: Manual override → milestone change does NOT update progress ───────

@pytest.mark.django_db
def test_proj_06_manual_override_blocks_progress_recalc(draft_project):
    """PROJ-06: progress_manual_override=True means milestones don't change pct."""
    draft_project.progress_pct = Decimal("75.00")
    draft_project.progress_manual_override = True
    draft_project.save()

    m = ProjectMilestone.objects.create(
        project=draft_project, title="Phase X", target_date="2026-05-01"
    )
    m.status = "completed"
    m.save()

    draft_project.refresh_from_db()
    assert draft_project.progress_pct == Decimal("75.00")


# ── PROJ-07: Site report with quantity_used > available → 400 ─────────────────

@pytest.mark.django_db
def test_proj_07_material_quantity_exceeds_available(api_client, draft_project, pm_user):
    """PROJ-07: quantity_used > opening + deliveries returns 400."""
    api_client.force_authenticate(user=pm_user)
    resp = api_client.post(
        f"/api/v1/projects/{draft_project.id}/site-reports/",
        {
            "report_date": "2026-04-01",
            "report_type": "daily",
            "task_description": "Foundation pouring",
            "progress_summary": "Completed 30% of foundation.",
            "completion_pct_added": "10",
            "weather_condition": "sunny",
            "materials": [
                {
                    "material_name": "Cement",
                    "opening_balance": "50",
                    "new_deliveries": "10",
                    "quantity_used": "70",  # > 50 + 10 = 60
                    "wastage": "0",
                    "unit": "bags",
                }
            ],
        },
        format="json",
    )
    assert resp.status_code == 400


# ── PROJ-08: Site report locked on creation ───────────────────────────────────

@pytest.mark.django_db
def test_proj_08_site_report_locked(draft_project, pm_user):
    """PROJ-08: Site report is_locked=True on creation."""
    report = SiteReport.objects.create(
        project=draft_project,
        report_date="2026-04-01",
        report_type="daily",
        task_description="First day on site",
        progress_summary="Initial assessment completed.",
        weather_condition="sunny",
        created_by=pm_user,
    )
    assert report.is_locked is True


# ── PROJ-09: Requisition ≤ 500K → requires_l2=False ─────────────────────────

@pytest.mark.django_db
def test_proj_09_low_value_requisition_no_l2(
    draft_project, pm_user, budget_line, l1_user, md_user
):
    """PROJ-09: payment_requisition ≤ 500K → requires_l2=False."""
    req = Requisition.objects.create(
        project=draft_project,
        budget_line=budget_line,
        category="materials",
        description="Purchase cement for foundation work",
        total_amount=Decimal("400000.00"),
        created_by=pm_user,
    )
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        workflow = RequisitionService.submit(req, pm_user)

    assert workflow.requires_l2 is False
    req.refresh_from_db()
    assert req.status == "pending_approval"


# ── PROJ-10: Requisition > 500K → requires_l2=True ──────────────────────────

@pytest.mark.django_db
def test_proj_10_high_value_requisition_requires_l2(
    draft_project, pm_user, budget_line, l1_user, md_user
):
    """PROJ-10: payment_requisition > 500K → requires_l2=True."""
    req = Requisition.objects.create(
        project=draft_project,
        budget_line=budget_line,
        category="materials",
        description="Purchase steel reinforcement for main structure",
        total_amount=Decimal("750000.00"),
        created_by=pm_user,
    )
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        workflow = RequisitionService.submit(req, pm_user)

    assert workflow.requires_l2 is True


# ── PROJ-11: Approved requisition → committed_amount incremented atomically ───

@pytest.mark.django_db
def test_proj_11_approved_requisition_increments_committed(
    draft_project, pm_user, budget_line, l1_user, md_user
):
    """PROJ-11: On approval, budget_line.committed_amount += req.total_amount (F())."""
    req = Requisition.objects.create(
        project=draft_project,
        budget_line=budget_line,
        category="materials",
        description="Purchase aggregate stones for drainage",
        total_amount=Decimal("200000.00"),
        created_by=pm_user,
    )
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        workflow = RequisitionService.submit(req, pm_user)
        ApprovalService.decide(workflow, workflow.l1_approver, "approved", "OK.")

    budget_line.refresh_from_db()
    assert budget_line.committed_amount == Decimal("200000.00")

    req.refresh_from_db()
    assert req.status == "approved"


# ── PROJ-12: Budget > 80% → notification for PM + MD ─────────────────────────

@pytest.mark.django_db
def test_proj_12_budget_80_pct_alert(draft_project, pm_user, budget_line, md_user):
    """PROJ-12: 80% utilization triggers notifications for PM and MD."""
    draft_project.status = "planning"
    draft_project.save()

    # 85% utilization (850k of 1000k)
    budget_line.committed_amount = Decimal("850000.00")
    budget_line.save()

    result = check_budget_alerts()
    assert result >= 2

    assert Notification.objects.filter(
        recipient=md_user, notification_type="budget_alert"
    ).exists()
    assert Notification.objects.filter(
        recipient=pm_user, notification_type="budget_alert"
    ).exists()

    budget_line.refresh_from_db()
    assert budget_line.alerts_sent.get("80pct") is True


# ── PROJ-13: Dashboard cached; second call from cache ─────────────────────────

@pytest.mark.django_db
def test_proj_13_dashboard_cached(api_client, md_user):
    """PROJ-13: Dashboard is cached; second call returns same data from Redis."""
    api_client.force_authenticate(user=md_user)

    assert cache.get("projects_dashboard") is None

    resp1 = api_client.get(DASHBOARD_URL)
    assert resp1.status_code == 200

    assert cache.get("projects_dashboard") is not None

    resp2 = api_client.get(DASHBOARD_URL)
    assert resp2.data == resp1.data


# ── PROJ-14: PDF for site report returns valid PDF bytes ──────────────────────

@pytest.mark.django_db
def test_proj_14_site_report_pdf(api_client, draft_project, pm_user):
    """PROJ-14: GET /site-reports/{id}/pdf/ returns application/pdf."""
    report = SiteReport.objects.create(
        project=draft_project,
        report_date="2026-04-01",
        report_type="daily",
        task_description="Foundation work started",
        progress_summary="Completed initial setup.",
        weather_condition="sunny",
        created_by=pm_user,
    )
    SiteReportMaterial.objects.create(
        report=report,
        material_name="Cement",
        opening_balance=Decimal("100"),
        new_deliveries=Decimal("50"),
        quantity_used=Decimal("80"),
        wastage=Decimal("5"),
        unit="bags",
        work_area="Block A",
    )

    api_client.force_authenticate(user=pm_user)
    resp = api_client.get(
        f"/api/v1/projects/{draft_project.id}/site-reports/{report.id}/pdf/"
    )
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


# ── PROJ-15: pm_limited cannot create project; can create site report ──────────

@pytest.mark.django_db
def test_proj_15_pm_limited_permissions(
    api_client, pm_limited_user, draft_project
):
    """PROJ-15: pm_limited cannot create project (403); can create site report on assigned project."""
    draft_project.project_manager = pm_limited_user
    draft_project.save()

    api_client.force_authenticate(user=pm_limited_user)

    # Cannot create a project
    resp = api_client.post(
        PROJECTS_URL,
        {
            "name": "Unauthorized Project",
            "project_type": "commercial",
            "start_date": "2026-05-01",
            "expected_end_date": "2026-12-31",
            "budget_total": "1000000.00",
        },
        format="json",
    )
    assert resp.status_code == 403

    # Can create a site report on a project where they are PM
    resp2 = api_client.post(
        f"/api/v1/projects/{draft_project.id}/site-reports/",
        {
            "report_date": "2026-03-01",
            "report_type": "daily",
            "task_description": "Daily inspection",
            "progress_summary": "All work on schedule.",
            "weather_condition": "sunny",
        },
        format="json",
    )
    assert resp2.status_code == 201


# ── Edge cases ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_project_end_before_start_returns_400(api_client, pm_user):
    """end_date before start_date returns 400."""
    api_client.force_authenticate(user=pm_user)
    resp = api_client.post(
        PROJECTS_URL,
        {
            "name": "Bad Date Project",
            "project_type": "commercial",
            "start_date": "2026-06-01",
            "expected_end_date": "2026-05-01",
            "budget_total": "500000.00",
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_submit_already_submitted_raises(draft_project, pm_user, l1_user, md_user):
    """Submitting a non-draft project raises ValueError."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        ProjectService.submit(draft_project, pm_user)

    with pytest.raises(ValueError, match="Only draft"):
        ProjectService.submit(draft_project, pm_user)


@pytest.mark.django_db
def test_project_code_unique_across_projects(
    draft_project, pm_user, l1_user, md_user, django_user_model
):
    """Two consecutive approvals generate distinct project_code values."""
    project2 = Project.objects.create(
        name="Second Project",
        project_type="residential",
        start_date="2026-05-01",
        expected_end_date="2027-05-01",
        budget_total=Decimal("1000000.00"),
        created_by=pm_user,
    )

    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        wf1 = ProjectService.submit(draft_project, pm_user)
        wf2 = ProjectService.submit(project2, pm_user)
        ApprovalService.decide(wf1, wf1.l1_approver, "approved", "OK")
        ApprovalService.decide(wf1, wf1.l2_approver, "approved", "Final OK")
        ApprovalService.decide(wf2, wf2.l1_approver, "approved", "OK")
        ApprovalService.decide(wf2, wf2.l2_approver, "approved", "Final OK")

    draft_project.refresh_from_db()
    project2.refresh_from_db()
    assert draft_project.project_code != project2.project_code


@pytest.mark.django_db
def test_l1_rejection_returns_project_to_draft(
    draft_project, pm_user, l1_user, md_user
):
    """L1 rejection moves project back to draft status."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        wf = ProjectService.submit(draft_project, pm_user)
        ApprovalService.decide(
            wf, wf.l1_approver, "rejected", "Budget figures need revision."
        )

    draft_project.refresh_from_db()
    assert draft_project.status == "draft"
    assert draft_project.project_code is None


@pytest.mark.django_db
def test_l2_rejection_returns_project_to_draft(
    draft_project, pm_user, l1_user, md_user
):
    """L2 rejection moves project back to draft status."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        wf = ProjectService.submit(draft_project, pm_user)
        ApprovalService.decide(wf, wf.l1_approver, "approved", "Looks good.")
        ApprovalService.decide(
            wf, wf.l2_approver, "rejected", "Requires board level sign off first."
        )

    draft_project.refresh_from_db()
    assert draft_project.status == "draft"


@pytest.mark.django_db
def test_pending_l2_intermediate_project_status(
    draft_project, pm_user, l1_user, md_user
):
    """After L1 approval, project.status advances to pending_l2."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        wf = ProjectService.submit(draft_project, pm_user)
        ApprovalService.decide(wf, wf.l1_approver, "approved", "L1 OK")

    draft_project.refresh_from_db()
    assert draft_project.status == "pending_l2"


@pytest.mark.django_db
def test_milestone_progress_all_complete(draft_project):
    """All milestones completed → progress_pct = 100."""
    for i in range(3):
        ProjectMilestone.objects.create(
            project=draft_project,
            title=f"Milestone {i}",
            target_date="2026-05-01",
            status="completed",
        )
    draft_project.refresh_from_db()
    assert draft_project.progress_pct == Decimal("100.00")


@pytest.mark.django_db
def test_milestone_progress_none_complete(draft_project):
    """No milestones completed → progress_pct = 0."""
    ProjectMilestone.objects.create(
        project=draft_project, title="Not done", target_date="2026-05-01"
    )
    draft_project.refresh_from_db()
    assert draft_project.progress_pct == Decimal("0")


@pytest.mark.django_db
def test_site_report_closing_balance_computed(draft_project, pm_user):
    """closing_balance auto-computed: opening + deliveries - used."""
    report = SiteReport.objects.create(
        project=draft_project,
        report_date="2026-04-01",
        report_type="daily",
        task_description="Test",
        progress_summary="Test summary.",
        weather_condition="sunny",
        created_by=pm_user,
    )
    mat = SiteReportMaterial.objects.create(
        report=report,
        material_name="Sand",
        opening_balance=Decimal("100"),
        new_deliveries=Decimal("50"),
        quantity_used=Decimal("30"),
        wastage=Decimal("0"),
        unit="m3",
    )
    assert mat.closing_balance == Decimal("120")  # 100 + 50 - 30


@pytest.mark.django_db
def test_requisition_line_item_total_cost_auto(draft_project, pm_user, budget_line):
    """RequisitionLineItem.total_cost = quantity * unit_cost."""
    req = Requisition.objects.create(
        project=draft_project,
        budget_line=budget_line,
        category="materials",
        description="Test requisition",
        total_amount=Decimal("10000.00"),
        created_by=pm_user,
    )
    item = RequisitionLineItem.objects.create(
        requisition=req,
        description="Bags of cement",
        quantity=Decimal("100"),
        unit_of_measure="bags",
        unit_cost=Decimal("50.00"),
    )
    assert item.total_cost == Decimal("5000.00")


@pytest.mark.django_db
def test_budget_80pct_alert_no_duplicate(draft_project, pm_user, budget_line, md_user):
    """Budget alert not sent twice for the same threshold crossing."""
    draft_project.status = "planning"
    draft_project.save()

    budget_line.committed_amount = Decimal("850000.00")
    budget_line.save()

    check_budget_alerts()
    first_count = Notification.objects.filter(notification_type="budget_alert").count()

    check_budget_alerts()
    second_count = Notification.objects.filter(notification_type="budget_alert").count()

    assert first_count == second_count


@pytest.mark.django_db
def test_budget_95pct_critical_alert(draft_project, pm_user, budget_line, md_user):
    """95% utilization triggers CRITICAL notification for MD."""
    draft_project.status = "planning"
    draft_project.save()

    budget_line.committed_amount = Decimal("960000.00")  # 96%
    budget_line.save()

    result = check_budget_alerts()
    assert result >= 1

    assert Notification.objects.filter(
        recipient=md_user,
        notification_type="budget_alert",
        title__icontains="CRITICAL",
    ).exists()

    budget_line.refresh_from_db()
    assert budget_line.alerts_sent.get("95pct") is True


@pytest.mark.django_db
def test_project_list_filter_by_status(api_client, draft_project, md_user):
    """GET /projects/?status=draft returns only draft projects."""
    api_client.force_authenticate(user=md_user)
    resp = api_client.get(f"{PROJECTS_URL}?status=draft")
    assert resp.status_code == 200
    for item in resp.data["results"]:
        assert item["status"] == "draft"


@pytest.mark.django_db
def test_unauthenticated_cannot_access_projects(api_client):
    """Unauthenticated request returns 401."""
    resp = api_client.get(PROJECTS_URL)
    assert resp.status_code == 401


@pytest.mark.django_db
def test_budget_line_remaining_and_utilization(budget_line):
    """BudgetLine.remaining and utilization_pct computed correctly."""
    budget_line.committed_amount = Decimal("400000.00")
    budget_line.spent_amount = Decimal("100000.00")
    budget_line.save()

    assert budget_line.remaining == Decimal("500000.00")
    assert round(budget_line.utilization_pct, 1) == 50.0


@pytest.mark.django_db
def test_non_creator_cannot_submit_project(api_client, draft_project, md_user):
    """A user who didn't create the project cannot submit it."""
    api_client.force_authenticate(user=md_user)
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        resp = api_client.post(f"/api/v1/projects/{draft_project.id}/submit/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_add_document_to_project(api_client, draft_project, pm_user):
    """PM can upload document to draft project."""
    api_client.force_authenticate(user=pm_user)
    resp = api_client.post(
        f"/api/v1/projects/{draft_project.id}/documents/",
        {
            "file": "s3://bucket/documents/plan.pdf",
            "original_filename": "site_plan.pdf",
            "file_size_bytes": 204800,
        },
        format="json",
    )
    assert resp.status_code == 201
    assert ProjectDocument.objects.filter(project=draft_project).count() == 1


@pytest.mark.django_db
def test_project_budget_view(api_client, draft_project, pm_user, budget_line):
    """GET /projects/{id}/budget/ returns budget breakdown."""
    api_client.force_authenticate(user=pm_user)
    resp = api_client.get(f"/api/v1/projects/{draft_project.id}/budget/")
    assert resp.status_code == 200
    assert "lines" in resp.data
    assert len(resp.data["lines"]) == 1
    assert resp.data["lines"][0]["category"] == "materials"


@pytest.mark.django_db
def test_dashboard_cache_invalidated_on_project_create(api_client, pm_user, md_user):
    """Creating a project invalidates the dashboard cache."""
    api_client.force_authenticate(user=md_user)
    api_client.get(DASHBOARD_URL)
    assert cache.get("projects_dashboard") is not None

    api_client.force_authenticate(user=pm_user)
    api_client.post(
        PROJECTS_URL,
        {
            "name": "Cache Bust Project",
            "project_type": "commercial",
            "start_date": "2026-05-01",
            "expected_end_date": "2027-05-01",
            "budget_total": "1000000.00",
        },
        format="json",
    )
    assert cache.get("projects_dashboard") is None


@pytest.mark.django_db
def test_req_code_format_after_submit(
    draft_project, pm_user, budget_line, l1_user, md_user
):
    """req_code assigned on submission matches REQ-YYYY-NNNN format."""
    req = Requisition.objects.create(
        project=draft_project,
        budget_line=budget_line,
        category="materials",
        description="Procurement of tiles",
        total_amount=Decimal("100000.00"),
        created_by=pm_user,
    )
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        RequisitionService.submit(req, pm_user)
    req.refresh_from_db()
    assert re.match(r"^REQ-\d{4}-\d{4}$", req.req_code)


@pytest.mark.django_db
def test_site_report_future_date_rejected(api_client, draft_project, pm_user):
    """Site report with a future date returns 400."""
    api_client.force_authenticate(user=pm_user)
    resp = api_client.post(
        f"/api/v1/projects/{draft_project.id}/site-reports/",
        {
            "report_date": "2030-01-01",
            "report_type": "daily",
            "task_description": "Future report",
            "progress_summary": "Not real.",
            "weather_condition": "sunny",
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_non_pm_cannot_create_milestone(
    api_client, draft_project, pm_limited_user
):
    """User who is not the project PM cannot create a milestone."""
    api_client.force_authenticate(user=pm_limited_user)
    resp = api_client.post(
        f"/api/v1/projects/{draft_project.id}/milestones/",
        {"title": "Unauthorized milestone", "target_date": "2026-06-01"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_milestone_update_auto_sets_completion_date(
    api_client, draft_project, pm_user
):
    """Setting milestone status to completed auto-sets actual_completion_date."""
    milestone = ProjectMilestone.objects.create(
        project=draft_project,
        title="Foundation",
        target_date="2026-05-01",
    )
    api_client.force_authenticate(user=pm_user)
    resp = api_client.put(
        f"/api/v1/projects/{draft_project.id}/milestones/{milestone.id}/",
        {"status": "completed"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["actual_completion_date"] is not None


@pytest.mark.django_db
def test_budget_alert_not_triggered_for_inactive_project(
    draft_project, pm_user, budget_line, md_user
):
    """Budget alerts only fire for active projects (planning/in_progress/on_hold)."""
    # Project is in 'draft' status → should NOT trigger alert
    assert draft_project.status == "draft"
    budget_line.committed_amount = Decimal("850000.00")
    budget_line.save()

    result = check_budget_alerts()
    assert result == 0


# ── Edge cases: withdrawal, requisition without budget line, negative quantity ──

@pytest.mark.django_db
def test_project_withdrawal_returns_to_draft(draft_project, pm_user, l1_user, md_user):
    """Withdrawing a pending_l1 project workflow returns project status to draft."""
    from unittest.mock import patch

    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        workflow = ProjectService.submit(draft_project, actor=pm_user)
    assert draft_project.status == "pending_l1"

    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        ApprovalService.withdraw(workflow, actor=pm_user)
    draft_project.refresh_from_db()
    assert draft_project.status == "draft"


@pytest.mark.django_db
def test_requisition_no_budget_line_approves_cleanly(
    draft_project, pm_user, l1_user, md_user
):
    """Approving a requisition with no budget_line does not crash committed_amount update."""
    from unittest.mock import patch

    # Create requisition without a budget_line
    req = Requisition.objects.create(
        project=draft_project,
        description="Misc expense",
        total_amount=Decimal("10000.00"),
        created_by=pm_user,
        # budget_line intentionally omitted (null)
    )

    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        workflow = RequisitionService.submit(req, actor=pm_user)

    # L1 approve
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        ApprovalService.decide(workflow, l1_user, "approved", "")

    req.refresh_from_db()
    assert req.status == "approved"


@pytest.mark.django_db
def test_site_report_negative_quantity_rejected(
    api_client, draft_project, pm_user
):
    """quantity_used < 0 in a site report material → 400."""
    api_client.force_authenticate(user=pm_user)
    resp = api_client.post(
        f"/api/v1/projects/{draft_project.id}/site-reports/",
        {
            "report_date": "2026-03-01",
            "report_type": "daily",
            "task_description": "Laying foundation",
            "progress_summary": "50% done",
            "weather_condition": "sunny",
            "materials": [
                {
                    "material_name": "Cement",
                    "opening_balance": "100",
                    "new_deliveries": "0",
                    "quantity_used": "-5",
                    "wastage": "0",
                    "unit": "bags",
                    "work_area": "Foundation",
                }
            ],
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_site_report_negative_wastage_rejected(
    api_client, draft_project, pm_user
):
    """wastage < 0 in a site report material → 400."""
    api_client.force_authenticate(user=pm_user)
    resp = api_client.post(
        f"/api/v1/projects/{draft_project.id}/site-reports/",
        {
            "report_date": "2026-03-01",
            "report_type": "daily",
            "task_description": "Laying foundation",
            "progress_summary": "50% done",
            "weather_condition": "sunny",
            "materials": [
                {
                    "material_name": "Cement",
                    "opening_balance": "100",
                    "new_deliveries": "0",
                    "quantity_used": "10",
                    "wastage": "-2",
                    "unit": "bags",
                    "work_area": "Foundation",
                }
            ],
        },
        format="json",
    )
    assert resp.status_code == 400
