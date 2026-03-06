"""
Projects app serializers — Phase 4.
"""

from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.projects.models import (
    BUDGET_CATEGORY_CHOICES,
    PROJECT_STATUS_CHOICES,
    PROJECT_TYPE_CHOICES,
    Project,
    ProjectBudgetLine,
    ProjectDocument,
    ProjectMilestone,
    Requisition,
    RequisitionLineItem,
    SiteReport,
    SiteReportMaterial,
)


# ── Project ────────────────────────────────────────────────────────────────────


class ProjectListSerializer(serializers.ModelSerializer):
    project_manager_email = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "project_code",
            "name",
            "project_type",
            "status",
            "health",
            "progress_pct",
            "project_manager",
            "project_manager_email",
            "start_date",
            "expected_end_date",
            "budget_total",
            "created_at",
        ]
        read_only_fields = fields

    def get_project_manager_email(self, obj):
        return obj.project_manager.email if obj.project_manager else None


class ProjectDetailSerializer(serializers.ModelSerializer):
    project_manager_email = serializers.SerializerMethodField()
    created_by_email = serializers.SerializerMethodField()
    milestone_count = serializers.SerializerMethodField()
    document_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "project_code",
            "name",
            "project_type",
            "location_text",
            "lat",
            "lng",
            "start_date",
            "expected_end_date",
            "budget_total",
            "scope",
            "status",
            "health",
            "progress_pct",
            "progress_manual_override",
            "project_manager",
            "project_manager_email",
            "created_by",
            "created_by_email",
            "milestone_count",
            "document_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "project_code",
            "created_by",
            "created_by_email",
            "milestone_count",
            "document_count",
            "created_at",
            "updated_at",
        ]

    def get_project_manager_email(self, obj):
        return obj.project_manager.email if obj.project_manager else None

    def get_created_by_email(self, obj):
        return obj.created_by.email

    def get_milestone_count(self, obj):
        return obj.milestones.count()

    def get_document_count(self, obj):
        return obj.documents.count()


class ProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = [
            "name",
            "project_type",
            "location_text",
            "lat",
            "lng",
            "start_date",
            "expected_end_date",
            "budget_total",
            "scope",
            "project_manager",
            "progress_manual_override",
        ]

    def validate(self, data):
        if data.get("start_date") and data.get("expected_end_date"):
            if data["expected_end_date"] <= data["start_date"]:
                raise serializers.ValidationError(
                    {"expected_end_date": "End date must be after start date."}
                )
        return data


class ProjectUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = [
            "name",
            "project_type",
            "location_text",
            "lat",
            "lng",
            "start_date",
            "expected_end_date",
            "budget_total",
            "scope",
            "project_manager",
            "progress_pct",
            "progress_manual_override",
            "health",
        ]


# ── Budget ─────────────────────────────────────────────────────────────────────


class BudgetLineSerializer(serializers.ModelSerializer):
    remaining = serializers.SerializerMethodField()
    utilization_pct = serializers.SerializerMethodField()

    class Meta:
        model = ProjectBudgetLine
        fields = [
            "id",
            "category",
            "allocated_amount",
            "committed_amount",
            "spent_amount",
            "remaining",
            "utilization_pct",
        ]
        read_only_fields = ["id", "committed_amount", "spent_amount"]

    def get_remaining(self, obj):
        return str(obj.remaining)

    def get_utilization_pct(self, obj):
        return round(obj.utilization_pct, 2)


class BudgetLineCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectBudgetLine
        fields = ["category", "allocated_amount"]


# ── Document ───────────────────────────────────────────────────────────────────


class DocumentSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.SerializerMethodField()

    class Meta:
        model = ProjectDocument
        fields = [
            "id",
            "file",
            "original_filename",
            "file_size_bytes",
            "uploaded_by",
            "uploaded_by_email",
            "uploaded_at",
        ]
        read_only_fields = ["id", "uploaded_by", "uploaded_by_email", "uploaded_at"]

    def get_uploaded_by_email(self, obj):
        return obj.uploaded_by.email


class DocumentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectDocument
        fields = ["file", "original_filename", "file_size_bytes"]


# ── Milestone ──────────────────────────────────────────────────────────────────


class MilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMilestone
        fields = [
            "id",
            "title",
            "target_date",
            "actual_completion_date",
            "status",
            "depends_on",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MilestoneCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMilestone
        fields = ["title", "target_date", "depends_on"]


class MilestoneUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMilestone
        fields = ["status", "actual_completion_date", "title", "target_date"]

    def validate(self, data):
        if data.get("status") == "completed" and not data.get("actual_completion_date"):
            data["actual_completion_date"] = timezone.now().date()
        return data


# ── Site Report ────────────────────────────────────────────────────────────────


class SiteReportMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteReportMaterial
        fields = [
            "id",
            "material_name",
            "opening_balance",
            "new_deliveries",
            "quantity_used",
            "closing_balance",
            "wastage",
            "unit",
            "work_area",
        ]
        read_only_fields = ["id", "closing_balance"]

    def validate(self, data):
        available = data.get("opening_balance", Decimal("0")) + data.get(
            "new_deliveries", Decimal("0")
        )
        if data.get("quantity_used", Decimal("0")) > available:
            raise serializers.ValidationError(
                {
                    "quantity_used": (
                        f"quantity_used ({data['quantity_used']}) exceeds "
                        f"available stock ({available})."
                    )
                }
            )
        return data


class SiteReportCreateSerializer(serializers.ModelSerializer):
    materials = SiteReportMaterialSerializer(many=True, required=False)

    class Meta:
        model = SiteReport
        fields = [
            "report_date",
            "report_type",
            "task_description",
            "progress_summary",
            "completion_pct_added",
            "external_labor_count",
            "weather_condition",
            "has_safety_incident",
            "incident_description",
            "materials",
        ]

    def validate_report_date(self, value):
        if value > timezone.now().date():
            raise serializers.ValidationError("Report date cannot be in the future.")
        return value

    def create(self, validated_data):
        materials_data = validated_data.pop("materials", [])
        report = SiteReport.objects.create(**validated_data)
        for mat in materials_data:
            SiteReportMaterial.objects.create(report=report, **mat)
        return report


class SiteReportDetailSerializer(serializers.ModelSerializer):
    materials = SiteReportMaterialSerializer(many=True, read_only=True)
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        model = SiteReport
        fields = [
            "id",
            "report_date",
            "report_type",
            "task_description",
            "progress_summary",
            "completion_pct_added",
            "external_labor_count",
            "weather_condition",
            "has_safety_incident",
            "incident_description",
            "is_locked",
            "created_by",
            "created_by_email",
            "created_at",
            "materials",
        ]
        read_only_fields = fields

    def get_created_by_email(self, obj):
        return obj.created_by.email


# ── Requisition ────────────────────────────────────────────────────────────────


class LineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequisitionLineItem
        fields = [
            "id",
            "description",
            "quantity",
            "unit_of_measure",
            "unit_cost",
            "total_cost",
        ]
        read_only_fields = ["id", "total_cost"]


class LineItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequisitionLineItem
        fields = ["description", "quantity", "unit_of_measure", "unit_cost"]


class RequisitionCreateSerializer(serializers.ModelSerializer):
    line_items = LineItemCreateSerializer(many=True, required=False)

    class Meta:
        model = Requisition
        fields = [
            "budget_line",
            "category",
            "urgency",
            "description",
            "total_amount",
            "payment_structure",
            "mobilization_pct",
            "mobilization_amount",
            "balance_terms",
            "vendor_name",
            "line_items",
        ]

    def create(self, validated_data):
        line_items_data = validated_data.pop("line_items", [])
        requisition = Requisition.objects.create(**validated_data)
        for item in line_items_data:
            RequisitionLineItem.objects.create(requisition=requisition, **item)
        # Auto-set total_amount from line items if provided
        if line_items_data:
            total = sum(
                item.quantity * item.unit_cost
                for item in requisition.line_items.all()
            )
            requisition.total_amount = total
            requisition.save(update_fields=["total_amount"])
        return requisition


class RequisitionDetailSerializer(serializers.ModelSerializer):
    line_items = LineItemSerializer(many=True, read_only=True)
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        model = Requisition
        fields = [
            "id",
            "req_code",
            "project",
            "budget_line",
            "category",
            "urgency",
            "description",
            "total_amount",
            "payment_structure",
            "mobilization_pct",
            "mobilization_amount",
            "balance_terms",
            "vendor_name",
            "status",
            "mobilization_status",
            "balance_status",
            "created_by",
            "created_by_email",
            "created_at",
            "updated_at",
            "line_items",
        ]
        read_only_fields = [
            "id",
            "req_code",
            "status",
            "mobilization_status",
            "balance_status",
            "created_by",
            "created_by_email",
            "created_at",
            "updated_at",
        ]

    def get_created_by_email(self, obj):
        return obj.created_by.email
