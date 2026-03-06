"""
Projects service layer — Phase 4.

ProjectService   — project submission and post-approval logic
RequisitionService — requisition submission and post-approval logic
"""

import logging
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)


def _next_sequence(seq_name: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT nextval('{seq_name}')")
        return cursor.fetchone()[0]


def generate_project_code() -> str:
    year = timezone.now().year
    seq = _next_sequence("projects_project_code_seq")
    return f"PROJ-{year}-{seq:03d}"


def generate_req_code() -> str:
    year = timezone.now().year
    seq = _next_sequence("projects_req_code_seq")
    return f"REQ-{year}-{seq:04d}"


class ProjectService:

    @staticmethod
    def submit(project, actor):
        """
        Draft → pending_l1.
        Creates an ApprovalWorkflow for the project proposal and sets project.status.
        Raises ValueError if project is not in draft status.
        """
        from apps.approvals.models import ApprovalWorkflow
        from apps.approvals.services import ApprovalService

        if project.status != "draft":
            raise ValueError(
                f"Only draft projects can be submitted (current: {project.status})."
            )

        content_type = ContentType.objects.get_for_model(project)
        workflow = ApprovalWorkflow(
            workflow_type="project_proposal",
            content_type=content_type,
            object_id=project.id,
            amount=project.budget_total,
            initiated_by=actor,
            requires_l2=True,  # project_proposal always requires L2
        )
        ApprovalService.submit(workflow)

        project.status = "pending_l1"
        project.save(update_fields=["status"])
        return workflow

    @staticmethod
    def on_workflow_approved(workflow):
        """
        Called (via signal) when an ApprovalWorkflow for a project_proposal is approved.
        Assigns project_code and sets project.status = 'planning'.
        """
        from apps.projects.models import Project

        try:
            project = Project.objects.get(id=workflow.object_id)
        except Project.DoesNotExist:
            logger.warning(
                "on_workflow_approved: project %s not found", workflow.object_id
            )
            return

        if not project.project_code:
            project.project_code = generate_project_code()
        project.status = "planning"
        project.save(update_fields=["status", "project_code"])

    @staticmethod
    def on_workflow_rejected(workflow):
        """Called when a project_proposal workflow is rejected (back to draft)."""
        from apps.projects.models import Project

        try:
            project = Project.objects.get(id=workflow.object_id)
        except Project.DoesNotExist:
            return
        project.status = "draft"
        project.save(update_fields=["status"])

    @staticmethod
    def on_workflow_l1_approved(workflow):
        """Called when L1 approves; advances project to pending_l2."""
        from apps.projects.models import Project

        try:
            project = Project.objects.get(id=workflow.object_id)
        except Project.DoesNotExist:
            return
        project.status = "pending_l2"
        project.save(update_fields=["status"])

    @staticmethod
    def on_workflow_withdrawn(workflow):
        """Called when a project workflow is withdrawn; returns project to draft."""
        from apps.projects.models import Project

        try:
            project = Project.objects.get(id=workflow.object_id)
        except Project.DoesNotExist:
            return
        project.status = "draft"
        project.save(update_fields=["status"])


class RequisitionService:

    @staticmethod
    def submit(requisition, actor):
        """
        Draft → pending_approval.
        Creates an ApprovalWorkflow for the requisition and determines requires_l2.
        """
        from apps.approvals.models import ApprovalWorkflow
        from apps.approvals.services import ApprovalService

        if requisition.status != "draft":
            raise ValueError(
                f"Only draft requisitions can be submitted (current: {requisition.status})."
            )

        content_type = ContentType.objects.get_for_model(requisition)
        requires_l2 = ApprovalService.evaluate_requires_l2(
            "payment_requisition",
            amount=requisition.total_amount,
            project=requisition.project,
        )
        workflow = ApprovalWorkflow(
            workflow_type="payment_requisition",
            content_type=content_type,
            object_id=requisition.id,
            amount=requisition.total_amount,
            initiated_by=actor,
            requires_l2=requires_l2,
        )
        ApprovalService.submit(workflow)

        if not requisition.req_code:
            requisition.req_code = generate_req_code()
        requisition.status = "pending_approval"
        requisition.save(update_fields=["status", "req_code"])
        return workflow

    @staticmethod
    def on_workflow_approved(workflow):
        """
        Called when a payment_requisition workflow is approved.
        Sets requisition.status='approved' and atomically increments committed_amount.
        """
        from apps.projects.models import Requisition

        try:
            requisition = Requisition.objects.select_related("budget_line").get(
                id=workflow.object_id
            )
        except Requisition.DoesNotExist:
            logger.warning(
                "on_workflow_approved: requisition %s not found", workflow.object_id
            )
            return

        requisition.status = "approved"
        requisition.save(update_fields=["status"])

        if requisition.budget_line:
            from apps.projects.models import ProjectBudgetLine

            ProjectBudgetLine.objects.filter(id=requisition.budget_line_id).update(
                committed_amount=F("committed_amount") + requisition.total_amount
            )

    @staticmethod
    def on_workflow_rejected(workflow):
        """Called when a requisition workflow is rejected."""
        from apps.projects.models import Requisition

        try:
            requisition = Requisition.objects.get(id=workflow.object_id)
        except Requisition.DoesNotExist:
            return
        requisition.status = "rejected"
        requisition.save(update_fields=["status"])
