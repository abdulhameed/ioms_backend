"""
Maintenance views — Phase 6.
"""

import logging
from decimal import Decimal

from django.db.models import Avg, Count, F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maintenance.models import MaintenancePhoto, MaintenanceRequest
from apps.maintenance.permissions import (
    CanCreateRequest,
    CanManageRequest,
    CanViewMetrics,
    IsParticipantOrAdmin,
)
from apps.maintenance.serializers import (
    AcceptSerializer,
    AssignSerializer,
    CloseSerializer,
    MaintenanceRequestCreateSerializer,
    MaintenanceRequestDetailSerializer,
    MaintenanceRequestListSerializer,
    MaintenanceRequestUpdateSerializer,
    PhotoUploadSerializer,
    UpdateStatusSerializer,
)
from apps.maintenance.services import MaintenanceService

logger = logging.getLogger(__name__)


class MaintenanceListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [CanCreateRequest()]
        return [IsAuthenticated()]

    def get(self, request):
        qs = MaintenanceRequest.objects.select_related(
            "reported_by", "assigned_to"
        )
        status_f = request.query_params.get("status")
        priority = request.query_params.get("priority")
        issue_type = request.query_params.get("type")
        assignee = request.query_params.get("assignee")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        if status_f:
            qs = qs.filter(status=status_f)
        if priority:
            qs = qs.filter(priority=priority)
        if issue_type:
            qs = qs.filter(issue_type=issue_type)
        if assignee:
            qs = qs.filter(assigned_to_id=assignee)
        if date_from:
            qs = qs.filter(reported_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(reported_at__date__lte=date_to)

        return Response(MaintenanceRequestListSerializer(qs, many=True).data)

    def post(self, request):
        ser = MaintenanceRequestCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        req = MaintenanceService.create_request(ser.validated_data, actor=request.user)
        return Response(
            MaintenanceRequestDetailSerializer(req).data,
            status=status.HTTP_201_CREATED,
        )


class MaintenanceDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "PUT":
            return [CanManageRequest()]
        return [IsAuthenticated()]

    def _get_request(self, pk, user):
        req = get_object_or_404(
            MaintenanceRequest.objects.prefetch_related("photos", "status_updates"),
            pk=pk,
        )
        if self.request.method == "GET":
            perm = IsParticipantOrAdmin()
            if not perm.has_object_permission(self.request, self, req):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied()
        return req

    def get(self, request, pk):
        req = self._get_request(pk, request.user)
        return Response(MaintenanceRequestDetailSerializer(req).data)

    def put(self, request, pk):
        req = get_object_or_404(MaintenanceRequest, pk=pk)
        if req.status != "open":
            return Response(
                {"error": "Can only edit open requests."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = MaintenanceRequestUpdateSerializer(req, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(MaintenanceRequestDetailSerializer(req).data)


class MaintenanceAssignView(APIView):
    permission_classes = [CanManageRequest]

    def post(self, request, pk):
        req = get_object_or_404(MaintenanceRequest, pk=pk)
        ser = AssignSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        from apps.users.models import CustomUser

        try:
            assignee = CustomUser.objects.get(pk=ser.validated_data["assigned_to"])
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "Assigned user not found."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            MaintenanceService.assign(
                req,
                assigned_to=assignee,
                assigned_by=request.user,
                notes=ser.validated_data.get("notes", ""),
                expected_resolution_at=ser.validated_data.get("expected_resolution_at"),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(MaintenanceRequestDetailSerializer(req).data)


class MaintenanceAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        req = get_object_or_404(MaintenanceRequest, pk=pk)
        ser = AcceptSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            MaintenanceService.accept(
                req,
                actor=request.user,
                accepted=ser.validated_data["accepted"],
                decline_reason=ser.validated_data.get("decline_reason", ""),
            )
        except (ValueError, PermissionError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(MaintenanceRequestDetailSerializer(req).data)


class MaintenanceUpdateStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        req = get_object_or_404(MaintenanceRequest, pk=pk)

        # Only assignee or admin can update status
        is_admin = request.user.groups.filter(name__in=["admin_full", "md"]).exists()
        if req.assigned_to_id != request.user.id and not is_admin:
            return Response(
                {"error": "Only the assignee or admin can update status."},
                status=status.HTTP_403_FORBIDDEN,
            )

        ser = UpdateStatusSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        parts_data = {
            "parts_needed": ser.validated_data.get("parts_needed", []),
            "parts_vendor": ser.validated_data.get("parts_vendor", ""),
            "parts_estimated_cost": ser.validated_data.get("parts_estimated_cost"),
            "parts_expected_delivery": ser.validated_data.get("parts_expected_delivery"),
        }

        try:
            MaintenanceService.update_status(
                req,
                actor=request.user,
                new_status=ser.validated_data["status"],
                notes=ser.validated_data.get("notes", ""),
                parts_data=parts_data,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(MaintenanceRequestDetailSerializer(req).data)


class MaintenanceCloseView(APIView):
    permission_classes = [CanManageRequest]

    def post(self, request, pk):
        req = get_object_or_404(MaintenanceRequest, pk=pk)
        ser = CloseSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            MaintenanceService.close(
                req,
                actor=request.user,
                resolution_notes=ser.validated_data.get("resolution_notes", ""),
                labor_hours=ser.validated_data.get("labor_hours"),
                parts_cost=ser.validated_data.get("parts_cost"),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(MaintenanceRequestDetailSerializer(req).data)


class MaintenancePhotoView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        req = get_object_or_404(MaintenanceRequest, pk=pk)

        ser = PhotoUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        existing_count = req.photos.count()
        new_photos = ser.validated_data["photos"]

        if existing_count + len(new_photos) > 10:
            return Response(
                {
                    "error": "photo_limit_exceeded",
                    "message": f"Request already has {existing_count} photo(s). Maximum is 10.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        for p in new_photos:
            photo = MaintenancePhoto.objects.create(
                request=req,
                file=p.get("file", ""),
                caption=p.get("caption", ""),
                file_size_bytes=int(p.get("file_size_bytes", 0)),
            )
            created.append(photo)

        from apps.maintenance.serializers import MaintenancePhotoSerializer

        return Response(
            MaintenancePhotoSerializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )


class MaintenanceMetricsView(APIView):
    permission_classes = [CanViewMetrics]

    def get(self, request):
        from django.db.models import DurationField, ExpressionWrapper
        from django.db.models.functions import Now

        closed_qs = MaintenanceRequest.objects.filter(status="closed")

        # Average resolution time (closed_at - reported_at) per priority
        by_priority = {}
        for priority in ["critical", "high", "medium", "low"]:
            subset = closed_qs.filter(priority=priority)
            total_seconds = 0
            count = 0
            for r in subset:
                if r.closed_at and r.reported_at:
                    total_seconds += (r.closed_at - r.reported_at).total_seconds()
                    count += 1
            avg_hours = round(total_seconds / 3600 / count, 2) if count else None
            by_priority[priority] = {"count": count, "avg_resolution_hours": avg_hours}

        # SLA breach rate
        total = MaintenanceRequest.objects.count()
        overdue = MaintenanceRequest.objects.filter(is_overdue=True).count()
        sla_breach_rate = round(overdue / total * 100, 2) if total else 0

        # Open by status
        status_counts = {}
        for s in ["open", "assigned", "in_progress", "pending_parts", "resolved", "closed"]:
            status_counts[s] = MaintenanceRequest.objects.filter(status=s).count()

        return Response(
            {
                "by_priority": by_priority,
                "sla_breach_rate_pct": sla_breach_rate,
                "by_status": status_counts,
                "total": total,
            }
        )
