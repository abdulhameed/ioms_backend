"""
Projects app models — Phase 4.

Models:
  Project               — Core project record with status state machine
  ProjectBudgetLine     — Budget categories with committed/spent tracking
  ProjectDocument       — Uploaded files (S3 keys) attached to a project
  ProjectMilestone      — Deliverable milestones; auto-updates progress_pct
  SiteReport            — Locked daily/weekly/incident site reports
  SiteReportMaterial    — Material reconciliation per report
  Requisition           — Payment request linked to budget line; triggers approval
  RequisitionLineItem   — Line items that sum to requisition.total_amount
"""

import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


# ── Choices ────────────────────────────────────────────────────────────────────

PROJECT_TYPE_CHOICES = [
    ("residential", "Residential"),
    ("commercial", "Commercial"),
    ("infrastructure", "Infrastructure"),
    ("renovation", "Renovation"),
    ("other", "Other"),
]

PROJECT_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("pending_l1", "Pending L1"),
    ("pending_l2", "Pending L2"),
    ("approved", "Approved"),
    ("planning", "Planning"),
    ("in_progress", "In Progress"),
    ("on_hold", "On Hold"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
]

PROJECT_HEALTH_CHOICES = [
    ("not_started", "Not Started"),
    ("on_track", "On Track"),
    ("at_risk", "At Risk"),
    ("delayed", "Delayed"),
    ("completed", "Completed"),
]

BUDGET_CATEGORY_CHOICES = [
    ("materials", "Materials"),
    ("labor", "Labor"),
    ("equipment", "Equipment"),
    ("professional_services", "Professional Services"),
    ("contingency", "Contingency"),
    ("utilities", "Utilities"),
    ("other", "Other"),
]

MILESTONE_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("in_progress", "In Progress"),
    ("completed", "Completed"),
    ("blocked", "Blocked"),
]

SITE_REPORT_TYPE_CHOICES = [
    ("daily", "Daily"),
    ("weekly", "Weekly"),
    ("incident", "Incident"),
]

WEATHER_CONDITION_CHOICES = [
    ("sunny", "Sunny"),
    ("cloudy", "Cloudy"),
    ("rainy", "Rainy"),
    ("stormy", "Stormy"),
    ("other", "Other"),
]

REQUISITION_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("pending_approval", "Pending Approval"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]

PAYMENT_STRUCTURE_CHOICES = [
    ("full", "Full Payment"),
    ("mobilization_balance", "Mobilization + Balance"),
]

URGENCY_CHOICES = [
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("critical", "Critical"),
]

PAYMENT_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("paid", "Paid"),
    ("not_applicable", "N/A"),
]


# ── Models ─────────────────────────────────────────────────────────────────────


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    name = models.CharField(max_length=200, unique=True)
    project_type = models.CharField(max_length=30, choices=PROJECT_TYPE_CHOICES)
    location_text = models.CharField(max_length=300, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    start_date = models.DateField()
    expected_end_date = models.DateField()
    budget_total = models.DecimalField(
        max_digits=15, decimal_places=2, validators=[MinValueValidator(0)]
    )
    scope = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=PROJECT_STATUS_CHOICES, default="draft", db_index=True
    )
    health = models.CharField(
        max_length=15, choices=PROJECT_HEALTH_CHOICES, default="not_started"
    )
    progress_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    progress_manual_override = models.BooleanField(default=False)
    project_manager = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.PROTECT,
        related_name="managed_projects",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.PROTECT,
        related_name="created_projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "projects_project"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.project_code or 'DRAFT'} — {self.name}"

    def recalculate_progress(self):
        """Auto-update progress_pct from completed milestones (unless overridden)."""
        if self.progress_manual_override:
            return
        total = self.milestones.count()
        if total == 0:
            return
        completed = self.milestones.filter(status="completed").count()
        self.progress_pct = (completed / total) * 100
        self.save(update_fields=["progress_pct"])


class ProjectBudgetLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="budget_lines"
    )
    category = models.CharField(max_length=30, choices=BUDGET_CATEGORY_CHOICES)
    allocated_amount = models.DecimalField(
        max_digits=15, decimal_places=2, validators=[MinValueValidator(0)]
    )
    committed_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    spent_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    # Tracks which thresholds (80pct, 95pct) have already triggered an alert
    alerts_sent = models.JSONField(default=dict)

    class Meta:
        db_table = "projects_budget_line"
        unique_together = [("project", "category")]

    def __str__(self):
        return f"{self.project.name} / {self.category}"

    @property
    def remaining(self):
        return self.allocated_amount - (self.committed_amount + self.spent_amount)

    @property
    def utilization_pct(self):
        if not self.allocated_amount:
            return 0
        return float(
            (self.committed_amount + self.spent_amount) / self.allocated_amount * 100
        )


class ProjectDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="documents"
    )
    file = models.CharField(max_length=500)  # S3 key / path
    original_filename = models.CharField(max_length=255)
    file_size_bytes = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.PROTECT,
        related_name="uploaded_documents",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "projects_document"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.project.name})"


class ProjectMilestone(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="milestones"
    )
    title = models.CharField(max_length=200)
    target_date = models.DateField()
    actual_completion_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=15, choices=MILESTONE_STATUS_CHOICES, default="pending"
    )
    depends_on = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dependents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "projects_milestone"
        ordering = ["target_date"]

    def __str__(self):
        return f"{self.title} ({self.project.name})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Recalculate progress after each milestone save (if not overridden)
        if not self.project.progress_manual_override:
            self.project.recalculate_progress()


class SiteReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="site_reports"
    )
    report_date = models.DateField()
    report_type = models.CharField(max_length=10, choices=SITE_REPORT_TYPE_CHOICES)
    task_description = models.CharField(max_length=200)
    progress_summary = models.TextField(max_length=1000)
    completion_pct_added = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    external_labor_count = models.PositiveIntegerField(default=0)
    weather_condition = models.CharField(max_length=10, choices=WEATHER_CONDITION_CHOICES)
    has_safety_incident = models.BooleanField(default=False)
    incident_description = models.TextField(blank=True)
    is_locked = models.BooleanField(default=True)  # always True; immutable after creation
    created_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.PROTECT,
        related_name="site_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "projects_site_report"
        ordering = ["-report_date", "-created_at"]

    def __str__(self):
        return f"{self.report_type} report — {self.project.name} on {self.report_date}"


class SiteReportMaterial(models.Model):
    UNIT_CHOICES = [
        ("kg", "Kilogram"),
        ("tonnes", "Tonnes"),
        ("litres", "Litres"),
        ("m2", "Square Metres"),
        ("m3", "Cubic Metres"),
        ("units", "Units"),
        ("bags", "Bags"),
        ("rolls", "Rolls"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(
        SiteReport, on_delete=models.CASCADE, related_name="materials"
    )
    material_name = models.CharField(max_length=200)
    opening_balance = models.DecimalField(
        max_digits=12, decimal_places=3, validators=[MinValueValidator(0)]
    )
    new_deliveries = models.DecimalField(
        max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(0)]
    )
    quantity_used = models.DecimalField(
        max_digits=12, decimal_places=3, validators=[MinValueValidator(0)]
    )
    closing_balance = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    wastage = models.DecimalField(
        max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(0)]
    )
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)
    work_area = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "projects_site_report_material"

    def save(self, *args, **kwargs):
        self.closing_balance = self.opening_balance + self.new_deliveries - self.quantity_used
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.material_name} — {self.report}"


class Requisition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    req_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requisitions",
    )
    budget_line = models.ForeignKey(
        ProjectBudgetLine,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requisitions",
    )
    category = models.CharField(max_length=30, choices=BUDGET_CATEGORY_CHOICES)
    urgency = models.CharField(max_length=10, choices=URGENCY_CHOICES, default="medium")
    description = models.TextField(max_length=500)
    total_amount = models.DecimalField(
        max_digits=15, decimal_places=2, validators=[MinValueValidator(0)]
    )
    payment_structure = models.CharField(
        max_length=25, choices=PAYMENT_STRUCTURE_CHOICES, default="full"
    )
    mobilization_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    mobilization_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    balance_terms = models.TextField(blank=True)
    vendor_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=20, choices=REQUISITION_STATUS_CHOICES, default="draft"
    )
    mobilization_status = models.CharField(
        max_length=15,
        choices=PAYMENT_STATUS_CHOICES,
        default="not_applicable",
    )
    balance_status = models.CharField(
        max_length=15,
        choices=PAYMENT_STATUS_CHOICES,
        default="not_applicable",
    )
    created_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.PROTECT,
        related_name="requisitions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "projects_requisition"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.req_code or 'DRAFT'} — {self.description[:50]}"


class RequisitionLineItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requisition = models.ForeignKey(
        Requisition, on_delete=models.CASCADE, related_name="line_items"
    )
    description = models.CharField(max_length=300)
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, validators=[MinValueValidator(0)]
    )
    unit_of_measure = models.CharField(max_length=50)
    unit_cost = models.DecimalField(
        max_digits=15, decimal_places=2, validators=[MinValueValidator(0)]
    )
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        db_table = "projects_requisition_line_item"

    def save(self, *args, **kwargs):
        self.total_cost = self.quantity * self.unit_cost
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} × {self.quantity} @ {self.unit_cost}"
