"""
Maintenance serializers — Phase 6.
"""

from rest_framework import serializers

from apps.maintenance.models import (
    MaintenancePhoto,
    MaintenanceRequest,
    MaintenanceStatusUpdate,
)

_MAX_PHOTOS = 10
_MAX_TOTAL_BYTES = 20 * 1024 * 1024  # 20 MB


class MaintenancePhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenancePhoto
        fields = ["id", "file", "caption", "file_size_bytes", "uploaded_at"]
        read_only_fields = ["id", "uploaded_at"]


class PhotoUploadSerializer(serializers.Serializer):
    """Validates a batch of photo uploads for a single request."""

    photos = serializers.ListField(
        child=serializers.DictField(), allow_empty=False
    )

    def validate_photos(self, value):
        if len(value) > _MAX_PHOTOS:
            raise serializers.ValidationError(
                f"Maximum {_MAX_PHOTOS} photos allowed per request."
            )
        total = sum(int(p.get("file_size_bytes", 0)) for p in value)
        if total > _MAX_TOTAL_BYTES:
            raise serializers.ValidationError(
                f"Total photo size exceeds 20 MB ({total} bytes)."
            )
        return value


class StatusUpdateSerializer(serializers.ModelSerializer):
    updated_by_email = serializers.EmailField(
        source="updated_by.email", read_only=True
    )

    class Meta:
        model = MaintenanceStatusUpdate
        fields = [
            "id",
            "from_status",
            "to_status",
            "updated_by",
            "updated_by_email",
            "notes",
            "parts_needed",
            "parts_vendor",
            "parts_estimated_cost",
            "parts_expected_delivery",
            "timestamp",
        ]
        read_only_fields = fields


class MaintenanceRequestListSerializer(serializers.ModelSerializer):
    reported_by_email = serializers.EmailField(
        source="reported_by.email", read_only=True
    )
    assigned_to_email = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceRequest
        fields = [
            "id",
            "request_code",
            "issue_type",
            "location_type",
            "priority",
            "status",
            "is_overdue",
            "sla_deadline",
            "reported_by",
            "reported_by_email",
            "assigned_to",
            "assigned_to_email",
            "reported_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_assigned_to_email(self, obj):
        return obj.assigned_to.email if obj.assigned_to else None


class MaintenanceRequestDetailSerializer(serializers.ModelSerializer):
    reported_by_email = serializers.EmailField(
        source="reported_by.email", read_only=True
    )
    assigned_to_email = serializers.SerializerMethodField()
    photos = MaintenancePhotoSerializer(many=True, read_only=True)
    status_updates = StatusUpdateSerializer(many=True, read_only=True)

    class Meta:
        model = MaintenanceRequest
        fields = [
            "id",
            "request_code",
            "issue_type",
            "location_type",
            "property",
            "project",
            "location_details",
            "priority",
            "description",
            "status",
            "is_overdue",
            "sla_deadline",
            "reported_by",
            "reported_by_email",
            "assigned_to",
            "assigned_to_email",
            "assigned_by",
            "assignment_notes",
            "expected_resolution_at",
            "resolved_at",
            "closed_at",
            "closed_by",
            "resolution_notes",
            "labor_hours",
            "parts_cost",
            "reported_at",
            "created_at",
            "updated_at",
            "photos",
            "status_updates",
        ]
        read_only_fields = [
            "id",
            "request_code",
            "sla_deadline",
            "is_overdue",
            "reported_by",
            "reported_by_email",
            "assigned_to",
            "assigned_to_email",
            "assigned_by",
            "resolved_at",
            "closed_at",
            "closed_by",
            "reported_at",
            "created_at",
            "updated_at",
            "photos",
            "status_updates",
        ]

    def get_assigned_to_email(self, obj):
        return obj.assigned_to.email if obj.assigned_to else None


class MaintenanceRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceRequest
        fields = [
            "issue_type",
            "location_type",
            "property",
            "project",
            "location_details",
            "priority",
            "description",
        ]


class MaintenanceRequestUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceRequest
        fields = ["issue_type", "location_type", "location_details", "priority", "description"]


class AssignSerializer(serializers.Serializer):
    assigned_to = serializers.UUIDField()
    notes = serializers.CharField(required=False, allow_blank=True)
    expected_resolution_at = serializers.DateTimeField(required=False, allow_null=True)


class AcceptSerializer(serializers.Serializer):
    accepted = serializers.BooleanField()
    decline_reason = serializers.CharField(required=False, allow_blank=True)


class UpdateStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["in_progress", "pending_parts", "resolved", "closed"]
    )
    notes = serializers.CharField(required=False, allow_blank=True)
    parts_needed = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    parts_vendor = serializers.CharField(required=False, allow_blank=True)
    parts_estimated_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    parts_expected_delivery = serializers.DateField(required=False, allow_null=True)


class CloseSerializer(serializers.Serializer):
    resolution_notes = serializers.CharField(required=False, allow_blank=True)
    labor_hours = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False, allow_null=True
    )
    parts_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
