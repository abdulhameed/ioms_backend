"""
Maintenance app models — Phase 6.

Models:
  MaintenanceRequest      — Issue ticket with SLA deadline, status state machine
  MaintenancePhoto        — File attachments (max 10, 20 MB total)
  MaintenanceStatusUpdate — Append-only status transition log
"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

SLA_HOURS = {
    "critical": 4,
    "high": 24,
    "medium": 72,
    "low": 168,  # 7 days
}


class MaintenanceRequest(models.Model):
    ISSUE_TYPE_CHOICES = [
        ("electrical", "Electrical"),
        ("plumbing", "Plumbing"),
        ("hvac", "HVAC / Air Conditioning"),
        ("structural", "Structural"),
        ("appliance", "Appliance"),
        ("cleaning", "Cleaning"),
        ("security", "Security"),
        ("it", "IT / Network"),
        ("other", "Other"),
    ]
    LOCATION_TYPE_CHOICES = [
        ("property", "Shortlet Property"),
        ("project_site", "Project Site"),
        ("office", "Office"),
    ]
    PRIORITY_CHOICES = [
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]
    STATUS_CHOICES = [
        ("open", "Open"),
        ("assigned", "Assigned"),
        ("in_progress", "In Progress"),
        ("pending_parts", "Pending Parts"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_code = models.CharField(max_length=20, unique=True, null=True, blank=True)

    issue_type = models.CharField(max_length=20, choices=ISSUE_TYPE_CHOICES)
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPE_CHOICES)
    property = models.ForeignKey(
        "shortlets.ShortletApartment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_requests",
    )
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_requests",
    )
    location_details = models.CharField(max_length=300, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="medium")
    description = models.CharField(max_length=1000)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")

    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reported_maintenance",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_maintenance",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_assigned_by",
    )
    assignment_notes = models.TextField(blank=True)
    expected_resolution_at = models.DateTimeField(null=True, blank=True)

    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="closed_maintenance",
    )
    resolution_notes = models.TextField(blank=True)
    labor_hours = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    parts_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    # SLA tracking
    sla_deadline = models.DateTimeField(null=True, blank=True)
    is_overdue = models.BooleanField(default=False)

    reported_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "maintenance_request"
        ordering = ["-reported_at"]

    def __str__(self):
        return f"{self.request_code or '?'} [{self.priority}] {self.issue_type}"

    def set_sla_deadline(self):
        hours = SLA_HOURS.get(self.priority, 72)
        self.sla_deadline = self.reported_at + timedelta(hours=hours)


class MaintenancePhoto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        MaintenanceRequest, on_delete=models.CASCADE, related_name="photos"
    )
    file = models.CharField(max_length=500)  # S3 key
    caption = models.CharField(max_length=100, blank=True)
    file_size_bytes = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "maintenance_photo"

    def __str__(self):
        return f"Photo for {self.request_id}"


class MaintenanceStatusUpdate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        MaintenanceRequest, on_delete=models.CASCADE, related_name="status_updates"
    )
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="maintenance_status_updates",
    )
    notes = models.TextField(blank=True)
    parts_needed = models.JSONField(default=list)
    parts_vendor = models.CharField(max_length=200, blank=True)
    parts_estimated_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    parts_expected_delivery = models.DateField(null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "maintenance_status_update"
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.request_id}: {self.from_status} → {self.to_status}"
