"""
Approval service layer — Phase 3.

All state transitions go through this module. Never mutate ApprovalWorkflow
status directly in views or serializers.
"""

from decimal import Decimal

from django.utils import timezone


class ApprovalService:
    """Handles all ApprovalWorkflow state transitions."""

    @staticmethod
    def evaluate_requires_l2(workflow_type, amount=None, project=None):
        """
        Returns True if this workflow requires L2 (md) sign-off.

        Rules:
          project_proposal  → always True
          caution_refund    → always True
          payment_requisition → True if amount > 500,000
                               OR amount > 20% of project remaining budget
        """
        if workflow_type in ("project_proposal", "caution_refund"):
            return True

        if workflow_type == "payment_requisition":
            if amount is not None and amount > Decimal("500000"):
                return True
            # Phase 4 will add project-budget check here when Project model exists
            if project is not None and amount is not None:
                try:
                    remaining = project.budget_total - project.budget_spent
                    if remaining > 0 and amount > (remaining * Decimal("0.20")):
                        return True
                except AttributeError:
                    pass

        return False

    @staticmethod
    def _assign_approvers(workflow):
        """
        Assigns l1_approver (hr_full) and, when requires_l2=True, l2_approver (md).
        Picks the first active user with the required role/level.
        """
        from apps.users.models import CustomUser

        l1 = (
            CustomUser.objects.filter(
                role="hr", permission_level="full", is_active=True
            )
            .exclude(id=workflow.initiated_by_id)
            .first()
        )
        workflow.l1_approver = l1

        if workflow.requires_l2:
            l2 = CustomUser.objects.filter(role="md", is_active=True).first()
            workflow.l2_approver = l2

    @staticmethod
    def submit(workflow):
        """
        Transition: draft → pending_l1.
        Assigns approvers and fires the submitted notification.
        """
        from apps.approvals.tasks import send_approval_notification

        if workflow.status != "draft":
            raise ValueError("Only draft workflows can be submitted.")

        ApprovalService._assign_approvers(workflow)
        workflow.status = "pending_l1"
        workflow.save()

        send_approval_notification.delay(str(workflow.id), "submitted")
        return workflow

    @staticmethod
    def decide(workflow, actor, decision, notes):
        """
        Handle an L1 or L2 decision (approved | rejected | more_info).
        Raises ValueError for invalid transitions, PermissionError for wrong actor.
        """
        from apps.approvals.tasks import send_approval_notification

        now = timezone.now()

        if workflow.status == "pending_l1":
            if actor.id != workflow.l1_approver_id:
                raise PermissionError("You are not the assigned L1 approver.")
            workflow.l1_decision = decision
            workflow.l1_decided_at = now
            workflow.l1_notes = notes

            if decision == "approved":
                if workflow.requires_l2:
                    workflow.status = "pending_l2"
                    send_approval_notification.delay(str(workflow.id), "l1_approved")
                else:
                    workflow.status = "approved"
                    send_approval_notification.delay(str(workflow.id), "approved")
            elif decision == "rejected":
                workflow.status = "draft"
                send_approval_notification.delay(str(workflow.id), "l1_rejected")
            elif decision == "more_info":
                # Status stays pending_l1; initiator notified to provide info
                send_approval_notification.delay(str(workflow.id), "more_info")

        elif workflow.status == "pending_l2":
            if actor.id != workflow.l2_approver_id:
                raise PermissionError("You are not the assigned L2 approver.")
            workflow.l2_decision = decision
            workflow.l2_decided_at = now
            workflow.l2_notes = notes

            if decision == "approved":
                workflow.status = "approved"
                send_approval_notification.delay(str(workflow.id), "approved")
            elif decision == "rejected":
                workflow.status = "draft"
                send_approval_notification.delay(str(workflow.id), "l2_rejected")
            elif decision == "more_info":
                send_approval_notification.delay(str(workflow.id), "more_info")

        else:
            raise ValueError(
                f"Cannot decide on a workflow with status '{workflow.status}'."
            )

        workflow.save()
        return workflow

    @staticmethod
    def withdraw(workflow, actor):
        """
        Transition: pending_l1 | pending_l2 → withdrawn.
        Only the initiator can withdraw.
        """
        from apps.approvals.tasks import send_approval_notification

        if actor.id != workflow.initiated_by_id:
            raise PermissionError("Only the workflow initiator can withdraw.")
        if workflow.status not in ("pending_l1", "pending_l2"):
            raise ValueError(
                f"Cannot withdraw a workflow with status '{workflow.status}'."
            )

        workflow.status = "withdrawn"
        workflow.withdrawn_at = timezone.now()
        workflow.save()

        send_approval_notification.delay(str(workflow.id), "withdrawn")
        return workflow
