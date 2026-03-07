"""
Notifications app serializers — Phase 7.
"""

from rest_framework import serializers

from apps.users.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "title",
            "body",
            "resource_type",
            "resource_id",
            "channel",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields
