"""
Approvals app serializers — Phase 3.
"""

from rest_framework import serializers

from apps.approvals.models import ApprovalComment, ApprovalWorkflow


class ApprovalCommentSerializer(serializers.ModelSerializer):
    author_email = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalComment
        fields = [
            "id",
            "author",
            "author_email",
            "comment",
            "comment_type",
            "created_at",
        ]
        read_only_fields = ["id", "author", "author_email", "created_at"]

    def get_author_email(self, obj):
        return obj.author.email


class ApprovalWorkflowListSerializer(serializers.ModelSerializer):
    initiated_by_email = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalWorkflow
        fields = [
            "id",
            "workflow_type",
            "status",
            "requires_l2",
            "amount",
            "initiated_by",
            "initiated_by_email",
            "l1_approver",
            "l2_approver",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_initiated_by_email(self, obj):
        return obj.initiated_by.email


class ApprovalWorkflowDetailSerializer(serializers.ModelSerializer):
    comments = ApprovalCommentSerializer(many=True, read_only=True)
    initiated_by_email = serializers.SerializerMethodField()
    l1_approver_email = serializers.SerializerMethodField()
    l2_approver_email = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalWorkflow
        fields = [
            "id",
            "workflow_type",
            "content_type",
            "object_id",
            "status",
            "requires_l2",
            "amount",
            "initiated_by",
            "initiated_by_email",
            "l1_approver",
            "l1_approver_email",
            "l1_decision",
            "l1_decided_at",
            "l1_notes",
            "l2_approver",
            "l2_approver_email",
            "l2_decision",
            "l2_decided_at",
            "l2_notes",
            "withdrawn_at",
            "created_at",
            "updated_at",
            "comments",
        ]
        read_only_fields = fields

    def get_initiated_by_email(self, obj):
        return obj.initiated_by.email

    def get_l1_approver_email(self, obj):
        return obj.l1_approver.email if obj.l1_approver else None

    def get_l2_approver_email(self, obj):
        return obj.l2_approver.email if obj.l2_approver else None


class ApprovalWorkflowCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalWorkflow
        fields = [
            "workflow_type",
            "content_type",
            "object_id",
            "amount",
        ]

    def validate_workflow_type(self, value):
        valid = {wt for wt, _ in ApprovalWorkflow.WORKFLOW_TYPES}
        if value not in valid:
            raise serializers.ValidationError(f"Invalid workflow_type '{value}'.")
        return value


class DecideSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=[c[0] for c in ApprovalWorkflow.DECISION_CHOICES]
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, data):
        if data["decision"] == "rejected":
            if len(data.get("notes", "").strip()) < 20:
                raise serializers.ValidationError(
                    {"notes": "Rejection notes must be at least 20 characters."}
                )
        return data


class WithdrawSerializer(serializers.Serializer):
    """No body required; validation is done in the service layer."""
    pass


class CommentSerializer(serializers.Serializer):
    comment = serializers.CharField()
    comment_type = serializers.ChoiceField(
        choices=[c[0] for c in ApprovalComment.COMMENT_TYPES],
        default="comment",
    )
