"""
Approvals app views — Phase 3.
"""

import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.approvals.models import ApprovalComment, ApprovalWorkflow
from apps.approvals.permissions import (
    IsApprovalParticipant,
    IsAssignedApprover,
    IsWorkflowInitiator,
)
from apps.approvals.serializers import (
    ApprovalWorkflowCreateSerializer,
    ApprovalWorkflowDetailSerializer,
    ApprovalWorkflowListSerializer,
    CommentSerializer,
    DecideSerializer,
    WithdrawSerializer,
)
from apps.approvals.services import ApprovalService

logger = logging.getLogger(__name__)


class ApprovalViewSet(ModelViewSet):
    """
    ApprovalWorkflow CRUD + actions.

    List/create: /api/v1/approvals/
    Detail/update: /api/v1/approvals/{id}/
    Actions: /decide/, /withdraw/, /comment/, /pending-count/
    """

    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        qs = (
            ApprovalWorkflow.objects.select_related(
                "initiated_by", "l1_approver", "l2_approver"
            )
            .prefetch_related("comments__author")
            .order_by("-created_at")
        )

        # pending-count and list: scope to user's workflows
        if self.action in ("list", "pending_count"):
            qs = qs.filter(
                initiated_by=user
            ) | ApprovalWorkflow.objects.filter(
                l1_approver=user
            ) | ApprovalWorkflow.objects.filter(
                l2_approver=user
            )
            qs = (
                qs.select_related("initiated_by", "l1_approver", "l2_approver")
                .prefetch_related("comments__author")
                .distinct()
                .order_by("-created_at")
            )

        # Managers (md / hr_full) see all
        if user.groups.filter(name__in=["md", "hr_full"]).exists():
            qs = (
                ApprovalWorkflow.objects.select_related(
                    "initiated_by", "l1_approver", "l2_approver"
                )
                .prefetch_related("comments__author")
                .order_by("-created_at")
            )

        # Apply query filters
        status_filter = self.request.query_params.get("status")
        type_filter = self.request.query_params.get("workflow_type")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if type_filter:
            qs = qs.filter(workflow_type=type_filter)

        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return ApprovalWorkflowCreateSerializer
        if self.action in ("retrieve", "decide", "withdraw", "comment"):
            return ApprovalWorkflowDetailSerializer
        return ApprovalWorkflowListSerializer

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated()]
        if self.action == "retrieve":
            return [IsAuthenticated(), IsApprovalParticipant()]
        if self.action == "decide":
            return [IsAuthenticated(), IsAssignedApprover()]
        if self.action == "withdraw":
            return [IsAuthenticated(), IsWorkflowInitiator()]
        if self.action == "comment":
            return [IsAuthenticated(), IsApprovalParticipant()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = ApprovalWorkflowCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        workflow = ApprovalWorkflow(
            workflow_type=data["workflow_type"],
            content_type=data.get("content_type"),
            object_id=data.get("object_id"),
            amount=data.get("amount"),
            initiated_by=request.user,
            requires_l2=ApprovalService.evaluate_requires_l2(
                data["workflow_type"], amount=data.get("amount")
            ),
        )
        ApprovalService.submit(workflow)

        return Response(
            ApprovalWorkflowDetailSerializer(workflow).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="decide")
    def decide(self, request, pk=None):
        workflow = self.get_object()
        serializer = DecideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            ApprovalService.decide(
                workflow=workflow,
                actor=request.user,
                decision=serializer.validated_data["decision"],
                notes=serializer.validated_data.get("notes", ""),
            )
        except PermissionError as e:
            return Response(
                {"error": "forbidden", "message": str(e)},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValueError as e:
            return Response(
                {"error": "invalid_transition", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(ApprovalWorkflowDetailSerializer(workflow).data)

    @action(detail=True, methods=["post"], url_path="withdraw")
    def withdraw(self, request, pk=None):
        workflow = self.get_object()
        serializer = WithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            ApprovalService.withdraw(workflow=workflow, actor=request.user)
        except PermissionError as e:
            return Response(
                {"error": "forbidden", "message": str(e)},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValueError as e:
            return Response(
                {"error": "invalid_transition", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(ApprovalWorkflowDetailSerializer(workflow).data)

    @action(detail=True, methods=["post"], url_path="comment")
    def comment(self, request, pk=None):
        workflow = self.get_object()
        serializer = CommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ApprovalComment.objects.create(
            workflow=workflow,
            author=request.user,
            comment=serializer.validated_data["comment"],
            comment_type=serializer.validated_data.get("comment_type", "comment"),
        )

        return Response(
            ApprovalWorkflowDetailSerializer(workflow).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="pending-count")
    def pending_count(self, request):
        from django.db.models import Q

        user = request.user
        count = ApprovalWorkflow.objects.filter(
            Q(status="pending_l1", l1_approver=user)
            | Q(status="pending_l2", l2_approver=user)
        ).count()
        return Response({"count": count})


def models_q(user):
    """Build Q filter: workflows where user is l1 or l2 approver."""
    from django.db.models import Q

    return Q(l1_approver=user) | Q(l2_approver=user)
