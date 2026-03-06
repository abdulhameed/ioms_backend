"""
Projects app views — Phase 4.
"""

import logging

from django.core.cache import cache
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import (
    Project,
    ProjectBudgetLine,
    ProjectDocument,
    ProjectMilestone,
    Requisition,
    SiteReport,
)
from apps.projects.permissions import (
    CanCreateProject,
    IsProjectCreator,
    IsPMOnProject,
)
from apps.projects.serializers import (
    BudgetLineCreateSerializer,
    BudgetLineSerializer,
    DocumentCreateSerializer,
    DocumentSerializer,
    LineItemCreateSerializer,
    MilestoneCreateSerializer,
    MilestoneSerializer,
    MilestoneUpdateSerializer,
    ProjectCreateSerializer,
    ProjectDetailSerializer,
    ProjectListSerializer,
    ProjectUpdateSerializer,
    RequisitionCreateSerializer,
    RequisitionDetailSerializer,
    SiteReportCreateSerializer,
    SiteReportDetailSerializer,
)
from apps.projects.services import ProjectService, RequisitionService

logger = logging.getLogger(__name__)

DASHBOARD_CACHE_KEY = "projects_dashboard"
DASHBOARD_CACHE_TTL = 60  # seconds


# ── Project ────────────────────────────────────────────────────────────────────


class ProjectListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Project.objects.select_related(
            "project_manager", "created_by"
        ).order_by("-created_at")

        status_filter = request.query_params.get("status")
        type_filter = request.query_params.get("project_type")
        pm_filter = request.query_params.get("pm")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if type_filter:
            qs = qs.filter(project_type=type_filter)
        if pm_filter:
            qs = qs.filter(project_manager=pm_filter)

        serializer = ProjectListSerializer(qs, many=True)
        return Response({"count": len(serializer.data), "results": serializer.data})

    def post(self, request):
        if not CanCreateProject().has_permission(request, self):
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = ProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save(created_by=request.user)
        # Invalidate dashboard cache
        cache.delete(DASHBOARD_CACHE_KEY)
        return Response(
            ProjectDetailSerializer(project).data, status=status.HTTP_201_CREATED
        )


class ProjectDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_project(self, pk):
        return get_object_or_404(
            Project.objects.select_related("project_manager", "created_by"), pk=pk
        )

    def get(self, request, pk):
        return Response(ProjectDetailSerializer(self._get_project(pk)).data)

    def put(self, request, pk):
        project = self._get_project(pk)

        # Only creator can edit; only in draft
        if project.created_by_id != request.user.id:
            return Response(status=status.HTTP_403_FORBIDDEN)
        if project.status != "draft":
            return Response(
                {"error": "locked", "message": "Only draft projects can be edited."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ProjectUpdateSerializer(project, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        cache.delete(DASHBOARD_CACHE_KEY)
        return Response(ProjectDetailSerializer(project).data)


class ProjectSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)

        if project.created_by_id != request.user.id:
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            ProjectService.submit(project, request.user)
        except ValueError as e:
            return Response(
                {"error": "invalid_state", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cache.delete(DASHBOARD_CACHE_KEY)
        return Response(ProjectDetailSerializer(project).data)


class ProjectBudgetView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        lines = project.budget_lines.all()
        serializer = BudgetLineSerializer(lines, many=True)

        total_allocated = sum(l.allocated_amount for l in lines)
        total_committed = sum(l.committed_amount for l in lines)
        total_spent = sum(l.spent_amount for l in lines)
        total_remaining = total_allocated - (total_committed + total_spent)
        overall_pct = (
            float((total_committed + total_spent) / total_allocated * 100)
            if total_allocated
            else 0
        )

        return Response(
            {
                "budget_total": str(project.budget_total),
                "lines": serializer.data,
                "total_allocated": str(total_allocated),
                "total_committed": str(total_committed),
                "total_spent": str(total_spent),
                "total_remaining": str(total_remaining),
                "overall_utilization_pct": round(overall_pct, 2),
            }
        )

    def post(self, request, pk):
        """Add a budget line to the project."""
        project = get_object_or_404(Project, pk=pk)
        serializer = BudgetLineCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        line = serializer.save(project=project)
        return Response(BudgetLineSerializer(line).data, status=status.HTTP_201_CREATED)


class ProjectDashboardView(APIView):
    """GET /api/v1/projects/dashboard/ — cached 60s."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = cache.get(DASHBOARD_CACHE_KEY)
        if data is None:
            data = self._compute()
            cache.set(DASHBOARD_CACHE_KEY, data, DASHBOARD_CACHE_TTL)
        return Response(data)

    def _compute(self):
        from apps.approvals.models import ApprovalWorkflow

        projects = Project.objects.all()
        by_status = {}
        for p in projects:
            by_status[p.status] = by_status.get(p.status, 0) + 1

        agg = ProjectBudgetLine.objects.aggregate(
            total_budget=Sum("allocated_amount"),
            total_committed=Sum("committed_amount"),
        )

        pending_approvals = ApprovalWorkflow.objects.filter(
            workflow_type="project_proposal",
            status__in=["pending_l1", "pending_l2"],
        ).count()

        from django.utils import timezone

        overdue_milestones = ProjectMilestone.objects.filter(
            target_date__lt=timezone.now().date(),
            status__in=["pending", "in_progress"],
        ).count()

        return {
            "total_projects": projects.count(),
            "by_status": by_status,
            "total_budget": str(agg["total_budget"] or 0),
            "total_committed": str(agg["total_committed"] or 0),
            "pending_approvals": pending_approvals,
            "overdue_milestones": overdue_milestones,
        }


# ── Milestones ─────────────────────────────────────────────────────────────────


class MilestoneListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        milestones = project.milestones.select_related("depends_on").order_by(
            "target_date"
        )
        return Response(MilestoneSerializer(milestones, many=True).data)

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        perm = IsPMOnProject()
        if not perm.has_object_permission(request, self, project):
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = MilestoneCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        milestone = serializer.save(project=project)
        return Response(
            MilestoneSerializer(milestone).data, status=status.HTTP_201_CREATED
        )


class MilestoneDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, pk, mid):
        project = get_object_or_404(Project, pk=pk)
        milestone = get_object_or_404(ProjectMilestone, pk=mid, project=project)

        perm = IsPMOnProject()
        if not perm.has_object_permission(request, self, project):
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = MilestoneUpdateSerializer(
            milestone, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MilestoneSerializer(milestone).data)


# ── Documents ──────────────────────────────────────────────────────────────────


class DocumentListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        docs = project.documents.select_related("uploaded_by").order_by("-uploaded_at")
        return Response(DocumentSerializer(docs, many=True).data)

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)

        if project.status != "draft" and project.created_by_id != request.user.id:
            return Response(
                {"error": "locked", "message": "Documents can only be added to draft projects."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DocumentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc = serializer.save(project=project, uploaded_by=request.user)
        return Response(DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


# ── Site Reports ───────────────────────────────────────────────────────────────


class SiteReportListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        reports = project.site_reports.select_related("created_by").order_by(
            "-report_date"
        )
        return Response(SiteReportDetailSerializer(reports, many=True).data)

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)

        perm = IsPMOnProject()
        if not perm.has_object_permission(request, self, project):
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = SiteReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = serializer.save(project=project, created_by=request.user)
        return Response(
            SiteReportDetailSerializer(report).data, status=status.HTTP_201_CREATED
        )


class SiteReportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, rid):
        project = get_object_or_404(Project, pk=pk)
        report = get_object_or_404(SiteReport, pk=rid, project=project)
        return Response(SiteReportDetailSerializer(report).data)


class SiteReportPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, rid):
        project = get_object_or_404(Project, pk=pk)
        report = get_object_or_404(
            SiteReport.objects.prefetch_related("materials"), pk=rid, project=project
        )

        html = self._render_html(report)
        try:
            from weasyprint import HTML

            pdf_bytes = HTML(string=html).write_pdf()
        except Exception as exc:
            logger.warning("WeasyPrint failed: %s", exc)
            return Response(
                {"error": "pdf_error", "message": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="site-report-{report.id}.pdf"'
        )
        return response

    @staticmethod
    def _render_html(report):
        materials_rows = ""
        for mat in report.materials.all():
            materials_rows += (
                f"<tr><td>{mat.material_name}</td>"
                f"<td>{mat.opening_balance}</td>"
                f"<td>{mat.new_deliveries}</td>"
                f"<td>{mat.quantity_used}</td>"
                f"<td>{mat.closing_balance}</td>"
                f"<td>{mat.unit}</td></tr>"
            )

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; font-size: 12px; margin: 40px; }}
    h1 {{ color: #333; }} h2 {{ color: #555; font-size: 14px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
    th {{ background: #f0f0f0; }}
    .header {{ margin-bottom: 20px; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>Site Report</h1>
    <p><strong>Project:</strong> {report.project.name}
       ({report.project.project_code or "DRAFT"})</p>
    <p><strong>Report Date:</strong> {report.report_date}</p>
    <p><strong>Type:</strong> {report.get_report_type_display()}</p>
    <p><strong>Weather:</strong> {report.get_weather_condition_display()}</p>
    <p><strong>External Labour:</strong> {report.external_labor_count}</p>
  </div>

  <h2>Task Description</h2>
  <p>{report.task_description}</p>

  <h2>Progress Summary</h2>
  <p>{report.progress_summary}</p>
  <p><strong>Completion % Added:</strong> {report.completion_pct_added}%</p>

  {"<h2>Safety Incident</h2><p>" + report.incident_description + "</p>"
   if report.has_safety_incident else ""}

  <h2>Material Reconciliation</h2>
  <table>
    <thead>
      <tr>
        <th>Material</th><th>Opening</th><th>Deliveries</th>
        <th>Used</th><th>Closing</th><th>Unit</th>
      </tr>
    </thead>
    <tbody>{materials_rows or "<tr><td colspan='6'>No materials recorded</td></tr>"}</tbody>
  </table>
</body>
</html>"""


# ── Requisitions ───────────────────────────────────────────────────────────────


class RequisitionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        reqs = project.requisitions.select_related("created_by", "budget_line").order_by(
            "-created_at"
        )
        return Response(RequisitionDetailSerializer(reqs, many=True).data)

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)

        # pm_full and admin can create requisitions
        allowed = {"md", "pm_full", "admin_full"}
        if not request.user.groups.filter(name__in=allowed).exists():
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = RequisitionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = serializer.save(project=project, created_by=request.user)
        return Response(
            RequisitionDetailSerializer(req).data, status=status.HTTP_201_CREATED
        )


class RequisitionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, rid):
        project = get_object_or_404(Project, pk=pk)
        req = get_object_or_404(Requisition, pk=rid, project=project)
        return Response(RequisitionDetailSerializer(req).data)

    def put(self, request, pk, rid):
        project = get_object_or_404(Project, pk=pk)
        req = get_object_or_404(Requisition, pk=rid, project=project)

        if req.created_by_id != request.user.id:
            return Response(status=status.HTTP_403_FORBIDDEN)
        if req.status != "draft":
            return Response(
                {"error": "locked", "message": "Only draft requisitions can be edited."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RequisitionCreateSerializer(req, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(RequisitionDetailSerializer(req).data)


class RequisitionSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, rid):
        project = get_object_or_404(Project, pk=pk)
        req = get_object_or_404(Requisition, pk=rid, project=project)

        if req.created_by_id != request.user.id:
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            workflow = RequisitionService.submit(req, request.user)
        except ValueError as e:
            return Response(
                {"error": "invalid_state", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "message": "Requisition submitted for approval.",
                "requires_l2": workflow.requires_l2,
                "workflow_id": str(workflow.id),
                "requisition": RequisitionDetailSerializer(req).data,
            }
        )
