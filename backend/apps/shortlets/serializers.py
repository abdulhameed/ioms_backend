"""
Shortlets serializers — Phase 5.
"""

from rest_framework import serializers

from apps.shortlets.models import (
    Booking,
    BookingReceipt,
    CautionDeposit,
    Client,
    ShortletProperty,
)


# ── ShortletProperty ────────────────────────────────────────────────────────────


class PropertyListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortletProperty
        fields = [
            "id",
            "property_code",
            "name",
            "unit_type",
            "location",
            "status",
            "rate_nightly",
            "rate_weekly",
            "rate_monthly",
            "caution_deposit_amount",
        ]
        read_only_fields = ["id", "property_code"]


class PropertyDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortletProperty
        fields = [
            "id",
            "property_code",
            "name",
            "unit_type",
            "location",
            "rate_nightly",
            "rate_weekly",
            "rate_monthly",
            "amenities",
            "description",
            "caution_deposit_amount",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "property_code", "created_at", "updated_at"]


class PropertyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortletProperty
        fields = [
            "name",
            "unit_type",
            "location",
            "rate_nightly",
            "rate_weekly",
            "rate_monthly",
            "amenities",
            "description",
            "caution_deposit_amount",
            "status",
        ]


class PropertyUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortletProperty
        fields = [
            "name",
            "unit_type",
            "location",
            "rate_nightly",
            "rate_weekly",
            "rate_monthly",
            "amenities",
            "description",
            "caution_deposit_amount",
            "status",
        ]


# ── Client ─────────────────────────────────────────────────────────────────────


class ClientListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = [
            "id",
            "client_code",
            "full_name",
            "email",
            "phone",
            "client_type",
            "is_vip",
            "created_at",
        ]
        read_only_fields = fields


class ClientDetailSerializer(serializers.ModelSerializer):
    booking_count = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id",
            "client_code",
            "full_name",
            "email",
            "phone",
            "id_type",
            "id_number",
            "client_type",
            "is_vip",
            "preferences_notes",
            "created_by",
            "booking_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "client_code",
            "created_by",
            "booking_count",
            "created_at",
            "updated_at",
        ]

    def get_booking_count(self, obj):
        return obj.bookings.count()


class ClientCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = [
            "full_name",
            "email",
            "phone",
            "id_type",
            "id_number",
            "client_type",
            "is_vip",
            "preferences_notes",
        ]
        # Disable auto-UniqueValidator so ClientService can return 409 for duplicates
        extra_kwargs = {
            "email": {"validators": []},
            "phone": {"validators": []},
        }


class ClientUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = [
            "full_name",
            "email",
            "phone",
            "id_type",
            "id_number",
            "client_type",
            "is_vip",
            "preferences_notes",
        ]
        extra_kwargs = {
            "email": {"validators": []},
            "phone": {"validators": []},
        }


# ── Booking ────────────────────────────────────────────────────────────────────


class BookingListSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.full_name", read_only=True)
    property_name = serializers.CharField(source="property.name", read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_code",
            "client",
            "client_name",
            "property",
            "property_name",
            "check_in_date",
            "check_out_date",
            "rate_type",
            "total_amount",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class BookingDetailSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.full_name", read_only=True)
    property_name = serializers.CharField(source="property.name", read_only=True)
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True
    )

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_code",
            "client",
            "client_name",
            "property",
            "property_name",
            "check_in_date",
            "check_out_date",
            "rate_type",
            "num_guests",
            "base_amount",
            "caution_deposit_amount",
            "total_amount",
            "payment_method",
            "payment_reference",
            "status",
            "checked_in_at",
            "checked_out_at",
            "checkout_condition",
            "created_by",
            "created_by_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "booking_code",
            "base_amount",
            "caution_deposit_amount",
            "total_amount",
            "status",
            "checked_in_at",
            "checked_out_at",
            "created_by",
            "created_by_email",
            "created_at",
            "updated_at",
        ]


class BookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = [
            "client",
            "property",
            "check_in_date",
            "check_out_date",
            "rate_type",
            "num_guests",
            "payment_method",
            "payment_reference",
        ]

    def validate(self, data):
        check_in = data.get("check_in_date")
        check_out = data.get("check_out_date")
        if check_in and check_out and check_out <= check_in:
            raise serializers.ValidationError(
                {"check_out_date": "Check-out date must be after check-in date."}
            )
        return data


class CheckOutSerializer(serializers.Serializer):
    condition = serializers.CharField(max_length=200, required=False, allow_blank=True)
    deduction_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=0
    )
    notes = serializers.CharField(required=False, allow_blank=True)


# ── CautionDeposit ─────────────────────────────────────────────────────────────


class CautionDepositSerializer(serializers.ModelSerializer):
    booking_code = serializers.CharField(
        source="booking.booking_code", read_only=True
    )

    class Meta:
        model = CautionDeposit
        fields = [
            "id",
            "booking",
            "booking_code",
            "deposit_amount",
            "deduction_amount",
            "deduction_reason",
            "refund_amount",
            "refund_method",
            "account_number",
            "status",
            "initiated_by",
            "processed_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "booking",
            "booking_code",
            "deposit_amount",
            "deduction_amount",
            "deduction_reason",
            "refund_amount",
            "status",
            "initiated_by",
            "created_at",
            "updated_at",
        ]


class CautionDepositUpdateSerializer(serializers.ModelSerializer):
    """Admin sets refund method + bank details; triggers ApprovalWorkflow."""

    class Meta:
        model = CautionDeposit
        fields = ["refund_method", "account_number"]
