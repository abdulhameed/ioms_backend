"""
Projects app signals — Phase 4.

Listens to ApprovalWorkflow post_save to keep Project and Requisition status
in sync with the approval state machine.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="approvals.ApprovalWorkflow")
def sync_on_workflow_change(sender, instance, **kwargs):
    """
    Dispatches to ProjectService or RequisitionService based on workflow_type
    and current workflow status.
    """
    if instance.object_id is None:
        return

    if instance.workflow_type == "project_proposal":
        _handle_project_workflow(instance)
    elif instance.workflow_type == "payment_requisition":
        _handle_requisition_workflow(instance)


def _handle_project_workflow(workflow):
    from apps.projects.services import ProjectService

    status = workflow.status

    if status == "approved":
        ProjectService.on_workflow_approved(workflow)
    elif status == "pending_l2":
        ProjectService.on_workflow_l1_approved(workflow)
    elif status == "withdrawn":
        ProjectService.on_workflow_withdrawn(workflow)
    elif status == "draft":
        # draft after rejection: check decision fields
        if workflow.l1_decision == "rejected" or workflow.l2_decision == "rejected":
            ProjectService.on_workflow_rejected(workflow)


def _handle_requisition_workflow(workflow):
    from apps.projects.services import RequisitionService

    status = workflow.status

    if status == "approved":
        RequisitionService.on_workflow_approved(workflow)
    elif status == "draft":
        if workflow.l1_decision == "rejected" or workflow.l2_decision == "rejected":
            RequisitionService.on_workflow_rejected(workflow)
