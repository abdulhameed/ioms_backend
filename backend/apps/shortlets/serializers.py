"""
Shortlets serializers — Milestone 2.
"""

from rest_framework import serializers

from apps.shortlets.models import (
    Booking,
    BookingReceipt,
    CautionDeposit,
    Client,
    InventoryItem,
    InventoryTemplate,
    InventoryVerification,
    InventoryVerificationItem,
    NairaBnBBookingRequest,
    OfficeItem,
    ShortletApartment,
    YearlyRentalApartment,
)


# ── ShortletApartment ───────────────────────────────────────────────────────────


class PropertyListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortletApartment
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
            "nairabNb_listing_id",
        ]
        read_only_fields = ["id", "property_code"]


class PropertyDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortletApartment
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
            "nairabNb_listing_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "property_code", "created_at", "updated_at"]


class PropertyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortletApartment
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
            "nairabNb_listing_id",
        ]


class PropertyUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortletApartment
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
            "nairabNb_listing_id",
        ]


# ── YearlyRentalApartment ───────────────────────────────────────────────────────


class YearlyRentalApartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = YearlyRentalApartment
        fields = [
            "id",
            "property_code",
            "name",
            "unit_type",
            "location",
            "rate_yearly",
            "deposit_amount",
            "lease_status",
            "current_tenant",
            "rent_due_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "property_code", "created_at", "updated_at"]


class YearlyRentalCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = YearlyRentalApartment
        fields = [
            "name",
            "unit_type",
            "location",
            "rate_yearly",
            "deposit_amount",
            "lease_status",
            "current_tenant",
            "rent_due_date",
        ]


# ── OfficeItem ──────────────────────────────────────────────────────────────────


class OfficeItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfficeItem
        fields = [
            "id",
            "item_code",
            "item_name",
            "item_category",
            "department",
            "condition",
            "location_detail",
            "acquired_date",
            "purchase_cost",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "item_code", "created_at", "updated_at"]


class OfficeItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfficeItem
        fields = [
            "item_name",
            "item_category",
            "department",
            "condition",
            "location_detail",
            "acquired_date",
            "purchase_cost",
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
    apartment_name = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_code",
            "client",
            "client_name",
            "apartment",
            "apartment_name",
            "yearly_rental",
            "check_in_date",
            "check_out_date",
            "rate_type",
            "total_amount",
            "status",
            "created_at",
        ]
        read_only_fields = fields

    def get_apartment_name(self, obj):
        if obj.apartment_id:
            return obj.apartment.name
        if obj.yearly_rental_id:
            return obj.yearly_rental.name
        return None


class BookingDetailSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.full_name", read_only=True)
    apartment_name = serializers.SerializerMethodField()
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
            "apartment",
            "apartment_name",
            "yearly_rental",
            "nairabNb_reference",
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

    def get_apartment_name(self, obj):
        if obj.apartment_id:
            return obj.apartment.name
        if obj.yearly_rental_id:
            return obj.yearly_rental.name
        return None


class BookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = [
            "client",
            "apartment",
            "yearly_rental",
            "nairabNb_reference",
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
        apartment = data.get("apartment")
        yearly_rental = data.get("yearly_rental")
        if not apartment and not yearly_rental:
            raise serializers.ValidationError(
                "Either apartment or yearly_rental must be provided."
            )
        if apartment and yearly_rental:
            raise serializers.ValidationError(
                "Only one of apartment or yearly_rental can be set."
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
            "dispute_reason",
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


class CautionDepositDisputeSerializer(serializers.Serializer):
    dispute_reason = serializers.CharField()


# ── Inventory ──────────────────────────────────────────────────────────────────


class InventoryTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryTemplate
        fields = [
            "id",
            "apartment",
            "yearly_rental",
            "unit_type",
            "item_name",
            "category",
            "quantity_expected",
            "is_consumable",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class InventoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryItem
        fields = [
            "id",
            "apartment",
            "yearly_rental",
            "item_name",
            "category",
            "quantity_total",
            "quantity_good",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class InventoryVerificationItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(
        source="inventory_item.item_name", read_only=True
    )

    class Meta:
        model = InventoryVerificationItem
        fields = [
            "id",
            "inventory_item",
            "item_name",
            "status",
            "estimated_cost",
            "notes",
            "photo",
        ]


class InventoryVerificationSerializer(serializers.ModelSerializer):
    items = InventoryVerificationItemSerializer(many=True, read_only=True)
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True
    )

    class Meta:
        model = InventoryVerification
        fields = [
            "id",
            "booking",
            "created_by",
            "created_by_email",
            "verified_at",
            "cleaning_fee",
            "additional_charges",
            "notes",
            "items",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_by_email", "created_at"]


class CompleteCheckoutSerializer(serializers.Serializer):
    cleaning_fee = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=0
    )
    additional_charges = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=0
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    items = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )


# ── NairaBnBBookingRequest ─────────────────────────────────────────────────────


class NairaBnBBookingRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = NairaBnBBookingRequest
        fields = [
            "id",
            "nairabNb_reference",
            "apartment",
            "client_name",
            "client_email",
            "client_phone",
            "check_in_date",
            "check_out_date",
            "num_guests",
            "quoted_amount",
            "status",
            "expires_at",
            "declined_reason",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "expires_at",
            "created_at",
            "updated_at",
        ]


class BookingRequestDeclineSerializer(serializers.Serializer):
    declined_reason = serializers.CharField(required=False, allow_blank=True, default="")
