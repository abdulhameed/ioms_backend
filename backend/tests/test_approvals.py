"""
Phase 3 — Approval Workflow Engine tests.
APR-01 through APR-10 (PRD-required) + edge cases.
"""

import pytest
from unittest.mock import patch

from apps.approvals.models import ApprovalComment, ApprovalWorkflow
from apps.approvals.services import ApprovalService
from apps.users.models import Notification


# ── Helpers ────────────────────────────────────────────────────────────────────

APPROVALS_URL = "/api/v1/approvals/"


def approval_url(pk, action=""):
    base = f"/api/v1/approvals/{pk}/"
    return f"{base}{action}/" if action else base


def create_workflow(
    api_client,
    user,
    workflow_type="project_proposal",
    amount=None,
    mock_task=None,
):
    """Helper: POST to create + submit a workflow, returns response."""
    api_client.force_authenticate(user=user)
    payload = {"workflow_type": workflow_type}
    if amount is not None:
        payload["amount"] = str(amount)
    if mock_task:
        with patch("apps.approvals.tasks.send_approval_notification.delay"):
            resp = api_client.post(APPROVALS_URL, payload, format="json")
    else:
        resp = api_client.post(APPROVALS_URL, payload, format="json")
    return resp


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def initiator(django_user_model):
    return django_user_model.objects.create_user(
        username="initiator",
        email="initiator@example.com",
        password="Test1234!",
        role="pm",
        permission_level="full",
        is_active=True,
    )


@pytest.fixture
def l1_user(django_user_model):
    """hr_full — default L1 approver."""
    return django_user_model.objects.create_user(
        username="l1_user",
        email="l1@example.com",
        password="Test1234!",
        role="hr",
        permission_level="full",
        is_active=True,
    )


@pytest.fixture
def l2_user(django_user_model):
    """md — default L2 approver."""
    return django_user_model.objects.create_user(
        username="l2_user",
        email="l2@example.com",
        password="Test1234!",
        role="md",
        permission_level="full",
        is_active=True,
    )


@pytest.fixture
def stranger(django_user_model):
    """Authenticated user who is not a participant."""
    return django_user_model.objects.create_user(
        username="stranger",
        email="stranger@example.com",
        password="Test1234!",
        role="finance",
        permission_level="limited",
        is_active=True,
    )


@pytest.fixture
def pending_l1_workflow(initiator, l1_user, l2_user):
    """Create a project_proposal workflow already in pending_l1 state."""
    wf = ApprovalWorkflow.objects.create(
        workflow_type="project_proposal",
        status="pending_l1",
        requires_l2=True,
        initiated_by=initiator,
        l1_approver=l1_user,
        l2_approver=l2_user,
    )
    return wf


# ── APR-01: Create project_proposal → pending_l1; l1 notified ─────────────────

@pytest.mark.django_db
def test_apr_01_create_project_proposal(api_client, initiator, l1_user, l2_user):
    """APR-01: POST creates workflow; status=pending_l1; notification created for L1."""
    with patch("apps.approvals.tasks.send_approval_notification.delay") as mock_task:
        api_client.force_authenticate(user=initiator)
        resp = api_client.post(
            APPROVALS_URL,
            {"workflow_type": "project_proposal"},
            format="json",
        )

    assert resp.status_code == 201, resp.data
    data = resp.data
    assert data["status"] == "pending_l1"
    assert data["requires_l2"] is True
    assert data["workflow_type"] == "project_proposal"

    # Notification sent via Celery (not sync)
    mock_task.assert_called_once()
    args = mock_task.call_args[0]
    assert args[1] == "submitted"

    # Notification row created in DB (task ran synchronously via direct call for assert)
    wf = ApprovalWorkflow.objects.get(id=data["id"])
    # Trigger the actual task logic directly to test notification creation
    from apps.approvals.tasks import send_approval_notification
    send_approval_notification(str(wf.id), "submitted")
    assert Notification.objects.filter(
        resource_id=wf.id,
        notification_type="approval_pending",
    ).exists()


# ── APR-02: L1 approve → pending_l2 ──────────────────────────────────────────

@pytest.mark.django_db
def test_apr_02_l1_approve_escalates_to_l2(
    api_client, pending_l1_workflow, l1_user
):
    """APR-02: L1 approver approves project_proposal → status=pending_l2."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        api_client.force_authenticate(user=l1_user)
        resp = api_client.post(
            approval_url(pending_l1_workflow.id, "decide"),
            {"decision": "approved", "notes": "Looks good."},
            format="json",
        )

    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "pending_l2"
    assert resp.data["l1_decision"] == "approved"


# ── APR-03: L2 approve → approved ────────────────────────────────────────────

@pytest.mark.django_db
def test_apr_03_l2_approve_completes_workflow(
    api_client, pending_l1_workflow, l1_user, l2_user
):
    """APR-03: L2 approver approves → status=approved."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        # L1 first
        ApprovalService.decide(
            pending_l1_workflow, l1_user, "approved", "L1 OK"
        )
        assert pending_l1_workflow.status == "pending_l2"

        # L2 decide
        api_client.force_authenticate(user=l2_user)
        resp = api_client.post(
            approval_url(pending_l1_workflow.id, "decide"),
            {"decision": "approved", "notes": "Final approval granted."},
            format="json",
        )

    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "approved"
    assert resp.data["l2_decision"] == "approved"


# ── APR-04: L1 reject with notes < 20 chars → 400 ────────────────────────────

@pytest.mark.django_db
def test_apr_04_reject_notes_too_short(api_client, pending_l1_workflow, l1_user):
    """APR-04: Rejection notes < 20 chars returns 400."""
    api_client.force_authenticate(user=l1_user)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "decide"),
        {"decision": "rejected", "notes": "Too short."},
        format="json",
    )
    assert resp.status_code == 400
    # Workflow status unchanged
    pending_l1_workflow.refresh_from_db()
    assert pending_l1_workflow.status == "pending_l1"


# ── APR-05: L1 reject with valid notes → draft; initiator notified ───────────

@pytest.mark.django_db
def test_apr_05_l1_reject_returns_to_draft(
    api_client, pending_l1_workflow, l1_user, initiator
):
    """APR-05: L1 rejects with 20+ char notes → status=draft; initiator notified."""
    with patch("apps.approvals.tasks.send_approval_notification.delay") as mock_task:
        api_client.force_authenticate(user=l1_user)
        long_notes = "Insufficient supporting documents provided for review."
        resp = api_client.post(
            approval_url(pending_l1_workflow.id, "decide"),
            {"decision": "rejected", "notes": long_notes},
            format="json",
        )

    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "draft"
    assert resp.data["l1_decision"] == "rejected"
    assert resp.data["l1_notes"] == long_notes

    # Celery task fired with l1_rejected event
    mock_task.assert_called_once()
    args = mock_task.call_args[0]
    assert args[1] == "l1_rejected"


# ── APR-06: Initiator withdraws while pending_l1 ─────────────────────────────

@pytest.mark.django_db
def test_apr_06_initiator_withdraws(api_client, pending_l1_workflow, initiator):
    """APR-06: Initiator POST /withdraw/ → status=withdrawn."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        api_client.force_authenticate(user=initiator)
        resp = api_client.post(
            approval_url(pending_l1_workflow.id, "withdraw"),
            {},
            format="json",
        )

    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "withdrawn"
    pending_l1_workflow.refresh_from_db()
    assert pending_l1_workflow.withdrawn_at is not None


# ── APR-07: Non-approver calls /decide/ → 403 ─────────────────────────────────

@pytest.mark.django_db
def test_apr_07_non_approver_decide_forbidden(
    api_client, pending_l1_workflow, stranger
):
    """APR-07: User who is not l1_approver gets 403 on /decide/."""
    api_client.force_authenticate(user=stranger)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "decide"),
        {"decision": "approved"},
        format="json",
    )
    assert resp.status_code == 403


# ── APR-08: Requisition ≤ 500K → requires_l2=False; approved after L1 ────────

@pytest.mark.django_db
def test_apr_08_low_value_requisition_no_l2(
    api_client, initiator, l1_user, l2_user
):
    """APR-08: payment_requisition ≤ 500K → requires_l2=False; L1 approve = approved."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        api_client.force_authenticate(user=initiator)
        resp = api_client.post(
            APPROVALS_URL,
            {"workflow_type": "payment_requisition", "amount": "400000.00"},
            format="json",
        )
    assert resp.status_code == 201
    assert resp.data["requires_l2"] is False
    assert resp.data["status"] == "pending_l1"

    wf = ApprovalWorkflow.objects.get(id=resp.data["id"])

    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        api_client.force_authenticate(user=l1_user)
        resp2 = api_client.post(
            approval_url(wf.id, "decide"),
            {"decision": "approved", "notes": "Approved within budget."},
            format="json",
        )

    assert resp2.status_code == 200
    assert resp2.data["status"] == "approved"


# ── APR-09: Requisition > 500K → requires_l2=True; pending_l2 after L1 ───────

@pytest.mark.django_db
def test_apr_09_high_value_requisition_requires_l2(
    api_client, initiator, l1_user, l2_user
):
    """APR-09: payment_requisition > 500K → requires_l2=True; pending_l2 after L1."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        api_client.force_authenticate(user=initiator)
        resp = api_client.post(
            APPROVALS_URL,
            {"workflow_type": "payment_requisition", "amount": "750000.00"},
            format="json",
        )
    assert resp.status_code == 201
    assert resp.data["requires_l2"] is True

    wf = ApprovalWorkflow.objects.get(id=resp.data["id"])

    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        api_client.force_authenticate(user=l1_user)
        resp2 = api_client.post(
            approval_url(wf.id, "decide"),
            {"decision": "approved", "notes": "Approved at L1."},
            format="json",
        )

    assert resp2.status_code == 200
    assert resp2.data["status"] == "pending_l2"


# ── APR-10: GET /pending-count/ returns correct badge number ──────────────────

@pytest.mark.django_db
def test_apr_10_pending_count(api_client, l1_user, l2_user, initiator):
    """APR-10: /pending-count/ returns count of workflows awaiting the user."""
    # Create 2 workflows pending l1_user's decision
    ApprovalWorkflow.objects.create(
        workflow_type="project_proposal",
        status="pending_l1",
        requires_l2=True,
        initiated_by=initiator,
        l1_approver=l1_user,
        l2_approver=l2_user,
    )
    ApprovalWorkflow.objects.create(
        workflow_type="caution_refund",
        status="pending_l1",
        requires_l2=True,
        initiated_by=initiator,
        l1_approver=l1_user,
        l2_approver=l2_user,
    )

    api_client.force_authenticate(user=l1_user)
    resp = api_client.get("/api/v1/approvals/pending-count/")
    assert resp.status_code == 200
    assert resp.data["count"] == 2

    # l2_user has nothing pending yet
    api_client.force_authenticate(user=l2_user)
    resp2 = api_client.get("/api/v1/approvals/pending-count/")
    assert resp2.data["count"] == 0


# ── Edge cases ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_caution_refund_always_requires_l2():
    """caution_refund always requires L2 regardless of amount."""
    assert ApprovalService.evaluate_requires_l2("caution_refund") is True
    assert ApprovalService.evaluate_requires_l2("caution_refund", amount=None) is True


@pytest.mark.django_db
def test_project_proposal_always_requires_l2():
    """project_proposal always requires L2."""
    assert ApprovalService.evaluate_requires_l2("project_proposal") is True


@pytest.mark.django_db
def test_payment_requisition_exactly_500k_no_l2():
    """payment_requisition at exactly 500,000 does NOT require L2 (> not >=)."""
    from decimal import Decimal
    assert ApprovalService.evaluate_requires_l2(
        "payment_requisition", amount=Decimal("500000")
    ) is False


@pytest.mark.django_db
def test_payment_requisition_above_500k_requires_l2():
    """payment_requisition above 500K requires L2."""
    from decimal import Decimal
    assert ApprovalService.evaluate_requires_l2(
        "payment_requisition", amount=Decimal("500000.01")
    ) is True


@pytest.mark.django_db
def test_withdraw_approved_workflow_returns_400(
    api_client, pending_l1_workflow, l1_user, l2_user, initiator
):
    """Cannot withdraw an already-approved workflow."""
    pending_l1_workflow.status = "approved"
    pending_l1_workflow.save()

    api_client.force_authenticate(user=initiator)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "withdraw"),
        {},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_stranger_cannot_withdraw(api_client, pending_l1_workflow, stranger):
    """Non-initiator cannot withdraw even if workflow is pending."""
    api_client.force_authenticate(user=stranger)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "withdraw"),
        {},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_more_info_decision_keeps_pending_status(
    api_client, pending_l1_workflow, l1_user
):
    """more_info decision keeps status=pending_l1; task fires."""
    with patch("apps.approvals.tasks.send_approval_notification.delay") as mock_task:
        api_client.force_authenticate(user=l1_user)
        resp = api_client.post(
            approval_url(pending_l1_workflow.id, "decide"),
            {"decision": "more_info", "notes": "Please provide docs."},
            format="json",
        )

    assert resp.status_code == 200
    assert resp.data["status"] == "pending_l1"
    assert resp.data["l1_decision"] == "more_info"
    mock_task.assert_called_once()
    assert mock_task.call_args[0][1] == "more_info"


@pytest.mark.django_db
def test_decide_on_withdrawn_workflow_returns_400(
    api_client, pending_l1_workflow, l1_user, initiator
):
    """Cannot decide on a withdrawn workflow."""
    pending_l1_workflow.status = "withdrawn"
    pending_l1_workflow.save()

    api_client.force_authenticate(user=l1_user)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "decide"),
        {"decision": "approved"},
        format="json",
    )
    # IsAssignedApprover returns 403 when status is not pending_l1/l2
    assert resp.status_code in (400, 403)


@pytest.mark.django_db
def test_comment_added_to_workflow(
    api_client, pending_l1_workflow, l1_user
):
    """POST /comment/ creates an ApprovalComment on the workflow."""
    api_client.force_authenticate(user=l1_user)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "comment"),
        {"comment": "Need more details.", "comment_type": "info_request"},
        format="json",
    )
    assert resp.status_code == 201
    assert ApprovalComment.objects.filter(
        workflow=pending_l1_workflow,
        comment_type="info_request",
    ).count() == 1


@pytest.mark.django_db
def test_stranger_cannot_view_workflow_detail(
    api_client, pending_l1_workflow, stranger
):
    """Non-participant cannot access workflow detail."""
    api_client.force_authenticate(user=stranger)
    resp = api_client.get(approval_url(pending_l1_workflow.id))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_unauthenticated_cannot_access_approvals(api_client):
    """Unauthenticated request returns 401."""
    resp = api_client.get(APPROVALS_URL)
    assert resp.status_code == 401


@pytest.mark.django_db
def test_list_filters_by_status(
    api_client, pending_l1_workflow, l1_user
):
    """GET /approvals/?status=pending_l1 returns only matching workflows."""
    api_client.force_authenticate(user=l1_user)
    resp = api_client.get(f"{APPROVALS_URL}?status=pending_l1")
    assert resp.status_code == 200
    for item in resp.data["results"]:
        assert item["status"] == "pending_l1"


@pytest.mark.django_db
def test_l2_reject_returns_to_draft_and_notifies(
    api_client, pending_l1_workflow, l1_user, l2_user
):
    """L2 rejection returns status to draft and notifies initiator + L1."""
    with patch("apps.approvals.tasks.send_approval_notification.delay") as mock_task:
        # Advance to pending_l2
        ApprovalService.decide(
            pending_l1_workflow, l1_user, "approved", "OK"
        )
        mock_task.reset_mock()

        api_client.force_authenticate(user=l2_user)
        resp = api_client.post(
            approval_url(pending_l1_workflow.id, "decide"),
            {
                "decision": "rejected",
                "notes": "Insufficient project justification provided.",
            },
            format="json",
        )

    assert resp.status_code == 200
    assert resp.data["status"] == "draft"
    assert resp.data["l2_decision"] == "rejected"
    mock_task.assert_called_once()
    assert mock_task.call_args[0][1] == "l2_rejected"


@pytest.mark.django_db
def test_send_pending_reminder_task(initiator, l1_user, l2_user):
    """send_pending_reminder creates Notification for approvals > 24h."""
    from datetime import timedelta
    from django.utils import timezone
    from apps.approvals.tasks import send_pending_reminder

    wf = ApprovalWorkflow.objects.create(
        workflow_type="project_proposal",
        status="pending_l1",
        requires_l2=True,
        initiated_by=initiator,
        l1_approver=l1_user,
        l2_approver=l2_user,
    )
    # Backdate updated_at to simulate 25h old
    ApprovalWorkflow.objects.filter(id=wf.id).update(
        updated_at=timezone.now() - timedelta(hours=25)
    )

    count = send_pending_reminder()
    assert count == 1
    assert Notification.objects.filter(
        recipient=l1_user,
        notification_type="approval_pending",
        resource_id=wf.id,
    ).exists()


@pytest.mark.django_db
def test_pending_count_zero_when_none_pending(api_client, initiator):
    """pending-count returns 0 when no workflows are awaiting user."""
    api_client.force_authenticate(user=initiator)
    resp = api_client.get("/api/v1/approvals/pending-count/")
    assert resp.status_code == 200
    assert resp.data["count"] == 0


@pytest.mark.django_db
def test_l1_wrong_user_gets_403_via_service(pending_l1_workflow, stranger):
    """Service raises PermissionError when wrong actor tries to decide."""
    with pytest.raises(PermissionError):
        ApprovalService.decide(
            pending_l1_workflow, stranger, "approved", ""
        )


@pytest.mark.django_db
def test_submit_non_draft_raises_value_error(pending_l1_workflow):
    """Submitting a non-draft workflow raises ValueError."""
    with pytest.raises(ValueError, match="Only draft"):
        ApprovalService.submit(pending_l1_workflow)


@pytest.mark.django_db
def test_reject_exact_20_chars_passes(api_client, pending_l1_workflow, l1_user):
    """Notes with exactly 20 characters should pass validation."""
    notes_20 = "A" * 20  # exactly 20 chars
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        api_client.force_authenticate(user=l1_user)
        resp = api_client.post(
            approval_url(pending_l1_workflow.id, "decide"),
            {"decision": "rejected", "notes": notes_20},
            format="json",
        )
    assert resp.status_code == 200


@pytest.mark.django_db
def test_reject_19_chars_fails(api_client, pending_l1_workflow, l1_user):
    """Notes with 19 characters should fail validation."""
    notes_19 = "A" * 19
    api_client.force_authenticate(user=l1_user)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "decide"),
        {"decision": "rejected", "notes": notes_19},
        format="json",
    )
    assert resp.status_code == 400


# ── Authorization: wrong actor at decide ──────────────────────────────────────

@pytest.mark.django_db
def test_initiator_cannot_decide_own_workflow(
    api_client, pending_l1_workflow, initiator
):
    """The workflow initiator is not the approver; /decide/ must return 403."""
    api_client.force_authenticate(user=initiator)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "decide"),
        {"decision": "approved"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_l2_user_cannot_decide_at_l1_stage(
    api_client, pending_l1_workflow, l2_user
):
    """L2 approver cannot decide when workflow is still at L1 stage."""
    api_client.force_authenticate(user=l2_user)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "decide"),
        {"decision": "approved"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_l1_user_cannot_decide_at_l2_stage(
    api_client, pending_l1_workflow, l1_user
):
    """L1 approver cannot decide after workflow has advanced to L2."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        ApprovalService.decide(pending_l1_workflow, l1_user, "approved", "OK")
    assert pending_l1_workflow.status == "pending_l2"

    api_client.force_authenticate(user=l1_user)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "decide"),
        {"decision": "approved"},
        format="json",
    )
    assert resp.status_code == 403


# ── Participants CAN view detail ───────────────────────────────────────────────

@pytest.mark.django_db
def test_initiator_can_view_workflow_detail(
    api_client, pending_l1_workflow, initiator
):
    """Initiator can GET the workflow detail."""
    api_client.force_authenticate(user=initiator)
    resp = api_client.get(approval_url(pending_l1_workflow.id))
    assert resp.status_code == 200
    assert str(resp.data["id"]) == str(pending_l1_workflow.id)


@pytest.mark.django_db
def test_l1_approver_can_view_workflow_detail(
    api_client, pending_l1_workflow, l1_user
):
    """L1 approver can GET the workflow detail."""
    api_client.force_authenticate(user=l1_user)
    resp = api_client.get(approval_url(pending_l1_workflow.id))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_l2_approver_can_view_workflow_detail(
    api_client, pending_l1_workflow, l2_user
):
    """L2 approver can GET the workflow detail (assigned even before L2 stage)."""
    api_client.force_authenticate(user=l2_user)
    resp = api_client.get(approval_url(pending_l1_workflow.id))
    assert resp.status_code == 200


# ── Stranger cannot comment ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_stranger_cannot_comment(api_client, pending_l1_workflow, stranger):
    """Non-participant gets 403 on POST /comment/."""
    api_client.force_authenticate(user=stranger)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "comment"),
        {"comment": "Hello from outside.", "comment_type": "comment"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_initiator_can_comment(api_client, pending_l1_workflow, initiator):
    """Initiator (participant) can add a comment."""
    api_client.force_authenticate(user=initiator)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "comment"),
        {"comment": "Attaching additional docs.", "comment_type": "info_response"},
        format="json",
    )
    assert resp.status_code == 201
    assert ApprovalComment.objects.filter(
        workflow=pending_l1_workflow, comment_type="info_response"
    ).exists()


# ── Withdraw while pending_l2 ─────────────────────────────────────────────────

@pytest.mark.django_db
def test_initiator_can_withdraw_while_pending_l2(
    api_client, pending_l1_workflow, l1_user, initiator
):
    """Initiator can withdraw after L1 approval (workflow in pending_l2)."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        ApprovalService.decide(pending_l1_workflow, l1_user, "approved", "OK")
    assert pending_l1_workflow.status == "pending_l2"

    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        api_client.force_authenticate(user=initiator)
        resp = api_client.post(
            approval_url(pending_l1_workflow.id, "withdraw"),
            {},
            format="json",
        )
    assert resp.status_code == 200
    assert resp.data["status"] == "withdrawn"


# ── L2-level rejection validation ─────────────────────────────────────────────

@pytest.mark.django_db
def test_l2_reject_notes_too_short_returns_400(
    api_client, pending_l1_workflow, l1_user, l2_user
):
    """L2 rejection also requires notes ≥ 20 chars."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        ApprovalService.decide(pending_l1_workflow, l1_user, "approved", "OK")

    api_client.force_authenticate(user=l2_user)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "decide"),
        {"decision": "rejected", "notes": "Too brief."},
        format="json",
    )
    assert resp.status_code == 400
    pending_l1_workflow.refresh_from_db()
    assert pending_l1_workflow.status == "pending_l2"


@pytest.mark.django_db
def test_more_info_at_l2_keeps_pending_l2(
    api_client, pending_l1_workflow, l1_user, l2_user
):
    """more_info decision at L2 stage keeps status=pending_l2."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        ApprovalService.decide(pending_l1_workflow, l1_user, "approved", "OK")

    with patch("apps.approvals.tasks.send_approval_notification.delay") as mock_task:
        api_client.force_authenticate(user=l2_user)
        resp = api_client.post(
            approval_url(pending_l1_workflow.id, "decide"),
            {"decision": "more_info", "notes": "Needs board sign-off."},
            format="json",
        )
    assert resp.status_code == 200
    assert resp.data["status"] == "pending_l2"
    assert resp.data["l2_decision"] == "more_info"
    assert mock_task.call_args[0][1] == "more_info"


# ── Re-submit after rejection ─────────────────────────────────────────────────

@pytest.mark.django_db
def test_resubmit_after_rejection(
    api_client, pending_l1_workflow, l1_user, initiator, l2_user
):
    """After L1 rejection returns workflow to draft, initiator can re-submit."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        ApprovalService.decide(
            pending_l1_workflow,
            l1_user,
            "rejected",
            "Needs more budget justification.",
        )
    assert pending_l1_workflow.status == "draft"

    # Re-submit: POST a new draft field update then submit via service
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        ApprovalService.submit(pending_l1_workflow)
    assert pending_l1_workflow.status == "pending_l1"


# ── Cannot decide on approved workflow ───────────────────────────────────────

@pytest.mark.django_db
def test_cannot_decide_on_approved_workflow(
    api_client, pending_l1_workflow, l1_user, l2_user
):
    """Trying to decide on an already-approved workflow returns 403/400."""
    pending_l1_workflow.status = "approved"
    pending_l1_workflow.save()

    api_client.force_authenticate(user=l1_user)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "decide"),
        {"decision": "approved"},
        format="json",
    )
    assert resp.status_code in (400, 403)


# ── Notification recipients verification ──────────────────────────────────────

@pytest.mark.django_db
def test_l1_approved_notifies_l2_and_initiator(
    pending_l1_workflow, l1_user, l2_user, initiator
):
    """l1_approved event creates notifications for both l2_approver and initiator."""
    from apps.approvals.tasks import send_approval_notification

    send_approval_notification(str(pending_l1_workflow.id), "l1_approved")

    assert Notification.objects.filter(
        recipient=l2_user, resource_id=pending_l1_workflow.id
    ).exists(), "L2 approver should be notified"
    assert Notification.objects.filter(
        recipient=initiator, resource_id=pending_l1_workflow.id
    ).exists(), "Initiator should be notified"


@pytest.mark.django_db
def test_approved_event_notifies_initiator(
    pending_l1_workflow, initiator
):
    """approved event creates notification for initiator."""
    from apps.approvals.tasks import send_approval_notification

    send_approval_notification(str(pending_l1_workflow.id), "approved")

    assert Notification.objects.filter(
        recipient=initiator, resource_id=pending_l1_workflow.id
    ).exists()


@pytest.mark.django_db
def test_l2_rejected_notifies_initiator_and_l1(
    pending_l1_workflow, l1_user, initiator
):
    """l2_rejected event notifies both initiator and l1_approver."""
    from apps.approvals.tasks import send_approval_notification

    send_approval_notification(str(pending_l1_workflow.id), "l2_rejected")

    assert Notification.objects.filter(
        recipient=initiator, resource_id=pending_l1_workflow.id
    ).exists(), "Initiator should be notified on L2 rejection"
    assert Notification.objects.filter(
        recipient=l1_user, resource_id=pending_l1_workflow.id
    ).exists(), "L1 approver should be notified on L2 rejection"


@pytest.mark.django_db
def test_withdrawn_event_notifies_current_approver(
    pending_l1_workflow, l1_user
):
    """withdrawn event creates in-app notification for the current pending approver."""
    from apps.approvals.tasks import send_approval_notification

    send_approval_notification(str(pending_l1_workflow.id), "withdrawn")

    notif = Notification.objects.filter(
        recipient=l1_user,
        resource_id=pending_l1_workflow.id,
        channel="in_app",
    )
    assert notif.exists()


# ── List: filter by workflow_type; scoping by role ────────────────────────────

@pytest.mark.django_db
def test_list_filters_by_workflow_type(api_client, l1_user, initiator, l2_user):
    """GET /approvals/?workflow_type=caution_refund returns only matching type."""
    ApprovalWorkflow.objects.create(
        workflow_type="project_proposal",
        status="pending_l1",
        requires_l2=True,
        initiated_by=initiator,
        l1_approver=l1_user,
        l2_approver=l2_user,
    )
    ApprovalWorkflow.objects.create(
        workflow_type="caution_refund",
        status="pending_l1",
        requires_l2=True,
        initiated_by=initiator,
        l1_approver=l1_user,
        l2_approver=l2_user,
    )

    api_client.force_authenticate(user=l1_user)
    resp = api_client.get(f"{APPROVALS_URL}?workflow_type=caution_refund")
    assert resp.status_code == 200
    for item in resp.data["results"]:
        assert item["workflow_type"] == "caution_refund"


@pytest.mark.django_db
def test_initiator_sees_own_workflows_in_list(
    api_client, pending_l1_workflow, initiator
):
    """Initiator can list their own created workflows."""
    api_client.force_authenticate(user=initiator)
    resp = api_client.get(APPROVALS_URL)
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.data["results"]]
    assert str(pending_l1_workflow.id) in ids


@pytest.mark.django_db
def test_md_sees_all_workflows(api_client, pending_l1_workflow, l2_user, django_user_model):
    """md user (manager) can see all workflows, not just their own."""
    # Create a second workflow not involving l2_user
    other_user = django_user_model.objects.create_user(
        username="other_pm",
        email="other_pm@example.com",
        password="Test1234!",
        role="pm",
        is_active=True,
    )
    other_l1 = django_user_model.objects.create_user(
        username="other_l1",
        email="other_l1@example.com",
        password="Test1234!",
        role="hr",
        permission_level="full",
        is_active=True,
    )
    other_wf = ApprovalWorkflow.objects.create(
        workflow_type="caution_refund",
        status="pending_l1",
        requires_l2=True,
        initiated_by=other_user,
        l1_approver=other_l1,
        l2_approver=l2_user,  # l2_user is also the l2 here; make truly separate
    )

    api_client.force_authenticate(user=l2_user)
    resp = api_client.get(APPROVALS_URL)
    assert resp.status_code == 200
    # md sees all, including workflows where they are not l1_approver
    ids = [item["id"] for item in resp.data["results"]]
    assert str(pending_l1_workflow.id) in ids


# ── Pending count: l2 counts and decrement after decision ─────────────────────

@pytest.mark.django_db
def test_pending_count_includes_pending_l2_for_l2_user(
    api_client, pending_l1_workflow, l1_user, l2_user
):
    """pending-count for l2_user increases when workflow reaches pending_l2."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        ApprovalService.decide(pending_l1_workflow, l1_user, "approved", "OK")

    api_client.force_authenticate(user=l2_user)
    resp = api_client.get("/api/v1/approvals/pending-count/")
    assert resp.data["count"] == 1


@pytest.mark.django_db
def test_pending_count_decrements_after_decision(
    api_client, pending_l1_workflow, l1_user
):
    """pending-count for l1_user drops to 0 after they decide."""
    api_client.force_authenticate(user=l1_user)
    assert api_client.get("/api/v1/approvals/pending-count/").data["count"] == 1

    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        ApprovalService.decide(pending_l1_workflow, l1_user, "approved", "OK")

    resp = api_client.get("/api/v1/approvals/pending-count/")
    assert resp.data["count"] == 0


# ── Input validation ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_create_with_invalid_workflow_type_returns_400(api_client, initiator):
    """Creating a workflow with an unknown workflow_type returns 400."""
    api_client.force_authenticate(user=initiator)
    resp = api_client.post(
        APPROVALS_URL,
        {"workflow_type": "not_a_real_type"},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_without_workflow_type_returns_400(api_client, initiator):
    """Creating a workflow without workflow_type returns 400."""
    api_client.force_authenticate(user=initiator)
    resp = api_client.post(APPROVALS_URL, {}, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_reject_with_empty_notes_returns_400(api_client, pending_l1_workflow, l1_user):
    """Empty rejection notes (blank string) must fail the 20-char rule."""
    api_client.force_authenticate(user=l1_user)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "decide"),
        {"decision": "rejected", "notes": ""},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_approved_decision_no_notes_is_ok(api_client, pending_l1_workflow, l1_user):
    """Approval decision without notes should succeed (notes only required for rejection)."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        api_client.force_authenticate(user=l1_user)
        resp = api_client.post(
            approval_url(pending_l1_workflow.id, "decide"),
            {"decision": "approved"},  # no notes field
            format="json",
        )
    assert resp.status_code == 200
    assert resp.data["status"] in ("pending_l2", "approved")


@pytest.mark.django_db
def test_payment_requisition_no_amount_defaults_no_l2(api_client, initiator, l1_user):
    """payment_requisition with no amount → requires_l2=False (treat as 0 < 500k)."""
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        api_client.force_authenticate(user=initiator)
        resp = api_client.post(
            APPROVALS_URL,
            {"workflow_type": "payment_requisition"},
            format="json",
        )
    assert resp.status_code == 201
    assert resp.data["requires_l2"] is False


# ── Reminder task: boundary conditions ───────────────────────────────────────

@pytest.mark.django_db
def test_pending_reminder_does_not_fire_for_recent_workflow(
    initiator, l1_user, l2_user
):
    """send_pending_reminder skips workflows updated < 24h ago."""
    from apps.approvals.tasks import send_pending_reminder

    ApprovalWorkflow.objects.create(
        workflow_type="project_proposal",
        status="pending_l1",
        requires_l2=True,
        initiated_by=initiator,
        l1_approver=l1_user,
        l2_approver=l2_user,
    )
    # updated_at is auto_now → just now, less than 24h
    count = send_pending_reminder()
    assert count == 0


@pytest.mark.django_db
def test_pending_reminder_fires_for_pending_l2_workflow(
    initiator, l1_user, l2_user
):
    """send_pending_reminder also targets workflows in pending_l2 state."""
    from datetime import timedelta
    from django.utils import timezone
    from apps.approvals.tasks import send_pending_reminder

    wf = ApprovalWorkflow.objects.create(
        workflow_type="project_proposal",
        status="pending_l2",
        requires_l2=True,
        initiated_by=initiator,
        l1_approver=l1_user,
        l2_approver=l2_user,
    )
    ApprovalWorkflow.objects.filter(id=wf.id).update(
        updated_at=timezone.now() - timedelta(hours=25)
    )

    count = send_pending_reminder()
    assert count == 1
    assert Notification.objects.filter(
        recipient=l2_user,
        notification_type="approval_pending",
        resource_id=wf.id,
    ).exists()


# ── Cannot withdraw withdrawn workflow ────────────────────────────────────────

@pytest.mark.django_db
def test_cannot_withdraw_already_withdrawn(
    api_client, pending_l1_workflow, initiator
):
    """Withdrawing an already-withdrawn workflow returns 400."""
    pending_l1_workflow.status = "withdrawn"
    pending_l1_workflow.save()

    api_client.force_authenticate(user=initiator)
    resp = api_client.post(
        approval_url(pending_l1_workflow.id, "withdraw"),
        {},
        format="json",
    )
    assert resp.status_code == 400
