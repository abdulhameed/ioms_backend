"""
Approvals app models — Phase 3.

Models:
  ApprovalWorkflow  — Generic FK state machine (draft → pending_l1 → pending_l2 → approved)
  ApprovalComment   — Threaded discussion / info requests on a workflow
"""

import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class ApprovalWorkflow(models.Model):
    WORKFLOW_TYPES = [
        ("project_proposal", "Project Proposal"),
        ("payment_requisition", "Payment Requisition"),
        ("caution_refund", "Caution Refund"),
    ]
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending_l1", "Pending L1"),
        ("pending_l2", "Pending L2"),
        ("approved", "Approved"),
        ("withdrawn", "Withdrawn"),
    ]
    DECISION_CHOICES = [
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("more_info", "More Info Requested"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_type = models.CharField(max_length=30, choices=WORKFLOW_TYPES)

    # ── Generic FK ─────────────────────────────────────────────────────────────
    content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    object_id = models.UUIDField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    # ── State ──────────────────────────────────────────────────────────────────
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    requires_l2 = models.BooleanField(default=False)
    # Amount stored for routing logic (L2 threshold on payment_requisition)
    amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # ── Participants ───────────────────────────────────────────────────────────
    initiated_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.PROTECT,
        related_name="initiated_workflows",
    )

    # L1 fields
    l1_approver = models.ForeignKey(
        "users.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="l1_workflows",
    )
    l1_decision = models.CharField(
        max_length=20, choices=DECISION_CHOICES, blank=True
    )
    l1_decided_at = models.DateTimeField(null=True, blank=True)
    l1_notes = models.TextField(blank=True)

    # L2 fields
    l2_approver = models.ForeignKey(
        "users.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="l2_workflows",
    )
    l2_decision = models.CharField(
        max_length=20, choices=DECISION_CHOICES, blank=True
    )
    l2_decided_at = models.DateTimeField(null=True, blank=True)
    l2_notes = models.TextField(blank=True)

    withdrawn_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "approvals_workflow"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.workflow_type} [{self.status}] by {self.initiated_by_id}"

    @property
    def current_approver(self):
        """Returns the user currently responsible for acting."""
        if self.status == "pending_l1":
            return self.l1_approver
        if self.status == "pending_l2":
            return self.l2_approver
        return None


class ApprovalComment(models.Model):
    COMMENT_TYPES = [
        ("comment", "Comment"),
        ("info_request", "Info Request"),
        ("info_response", "Info Response"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(
        ApprovalWorkflow, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.PROTECT,
        related_name="approval_comments",
    )
    comment = models.TextField()
    comment_type = models.CharField(
        max_length=20, choices=COMMENT_TYPES, default="comment"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "approvals_comment"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.comment_type} by {self.author_id} on {self.workflow_id}"
