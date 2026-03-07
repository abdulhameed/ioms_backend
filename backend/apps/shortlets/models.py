"""
Shortlets app models — Milestone 2 (Phase 5 extended).

Models:
  ShortletApartment         — Renamed from ShortletProperty; nightly/weekly/monthly rental unit
  YearlyRentalApartment     — Long-term yearly rental unit
  OfficeItem                — Office/company asset inventory item
  Client                    — Guest/tenant record with duplicate-detection support
  Booking                   — Reservation for shortlet apartment or yearly rental
  BookingReceipt            — Pre-generated PDF receipt (OneToOne with Booking)
  CautionDeposit            — Security deposit lifecycle (held → pending_refund → approved_for_refund)
  InventoryTemplate         — Blueprint for inventory items per unit type
  InventoryItem             — Actual inventory item linked to an apartment/yearly rental
  InventoryVerification     — Immutable checkout verification record
  InventoryVerificationItem — Per-item status within a verification
  NairaBnBBookingRequest    — Inbound booking request from NairaBnB channel
"""

import uuid
from decimal import Decimal
from math import ceil

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.fields import EncryptedCharField


class ShortletApartment(models.Model):
    UNIT_TYPE_CHOICES = [
        ("studio", "Studio"),
        ("1_bedroom", "1 Bedroom"),
        ("2_bedroom", "2 Bedroom"),
        ("3_bedroom", "3 Bedroom"),
        ("penthouse", "Penthouse"),
        ("duplex", "Duplex"),
        ("villa", "Villa"),
    ]
    STATUS_CHOICES = [
        ("available", "Available"),
        ("occupied", "Occupied"),
        ("maintenance", "Under Maintenance"),
        ("inactive", "Inactive"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    name = models.CharField(max_length=200)
    unit_type = models.CharField(max_length=20, choices=UNIT_TYPE_CHOICES)
    location = models.CharField(max_length=300)
    rate_nightly = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    rate_weekly = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    rate_monthly = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    amenities = models.JSONField(default=list)
    description = models.CharField(max_length=1000, blank=True)
    caution_deposit_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="available"
    )
    nairabNb_listing_id = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shortlets_property"
        ordering = ["name"]

    def __str__(self):
        return f"{self.property_code or 'UNPUBLISHED'} — {self.name}"


# Backward-compat alias — used by legacy migration references only; do not use in new code
ShortletProperty = ShortletApartment


class YearlyRentalApartment(models.Model):
    UNIT_TYPE_CHOICES = ShortletApartment.UNIT_TYPE_CHOICES
    LEASE_STATUS_CHOICES = [
        ("available", "Available"),
        ("leased", "Leased"),
        ("maintenance", "Under Maintenance"),
        ("inactive", "Inactive"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    name = models.CharField(max_length=200)
    unit_type = models.CharField(max_length=20, choices=UNIT_TYPE_CHOICES)
    location = models.CharField(max_length=300)
    rate_yearly = models.DecimalField(max_digits=12, decimal_places=2)
    deposit_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    lease_status = models.CharField(
        max_length=20, choices=LEASE_STATUS_CHOICES, default="available"
    )
    current_tenant = models.ForeignKey(
        "Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rented_apartments",
    )
    rent_due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shortlets_yearly_rental"
        ordering = ["name"]

    def __str__(self):
        return f"{self.property_code or 'UNPUBLISHED'} — {self.name}"


class OfficeItem(models.Model):
    CATEGORY_CHOICES = [
        ("furniture", "Furniture"),
        ("electronics", "Electronics"),
        ("appliances", "Appliances"),
        ("equipment", "Equipment"),
        ("stationery", "Stationery"),
    ]
    CONDITION_CHOICES = [
        ("good", "Good"),
        ("fair", "Fair"),
        ("poor", "Poor"),
        ("damaged", "Damaged"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    item_name = models.CharField(max_length=200)
    item_category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    department = models.CharField(max_length=100, blank=True)
    condition = models.CharField(
        max_length=10, choices=CONDITION_CHOICES, default="good"
    )
    location_detail = models.CharField(max_length=300, blank=True)
    acquired_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shortlets_office_item"
        ordering = ["item_name"]

    def __str__(self):
        return f"{self.item_code or '?'} — {self.item_name}"


class Client(models.Model):
    ID_TYPE_CHOICES = [
        ("nin", "NIN"),
        ("passport", "Passport"),
        ("drivers_license", "Driver's License"),
        ("voters_card", "Voter's Card"),
    ]
    CLIENT_TYPE_CHOICES = [
        ("individual", "Individual"),
        ("corporate", "Corporate"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=200)
    email = models.EmailField(unique=True, null=True, blank=True)
    phone = models.CharField(max_length=20, unique=True)
    id_type = models.CharField(max_length=20, choices=ID_TYPE_CHOICES, blank=True)
    id_number = models.CharField(max_length=100, blank=True)
    client_type = models.CharField(
        max_length=20, choices=CLIENT_TYPE_CHOICES, default="individual"
    )
    is_vip = models.BooleanField(default=False)
    preferences_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clients_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shortlets_client"
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.client_code or '?'} — {self.full_name}"


class Booking(models.Model):
    RATE_TYPE_CHOICES = [
        ("nightly", "Nightly"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
    ]
    STATUS_CHOICES = [
        ("confirmed", "Confirmed"),
        ("checked_in", "Checked In"),
        ("checked_out", "Checked Out"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name="bookings"
    )
    apartment = models.ForeignKey(
        ShortletApartment,
        on_delete=models.PROTECT,
        related_name="bookings",
        null=True,
        blank=True,
    )
    yearly_rental = models.ForeignKey(
        YearlyRentalApartment,
        on_delete=models.PROTECT,
        related_name="bookings",
        null=True,
        blank=True,
    )
    nairabNb_reference = models.CharField(max_length=100, blank=True, null=True)
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    rate_type = models.CharField(max_length=10, choices=RATE_TYPE_CHOICES)
    num_guests = models.PositiveSmallIntegerField(default=1)
    base_amount = models.DecimalField(max_digits=12, decimal_places=2)
    caution_deposit_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="confirmed"
    )
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    checkout_condition = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shortlets_booking"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.booking_code or '?'} — {self.client_id}"

    def clean(self):
        has_apartment = bool(self.apartment_id)
        has_yearly = bool(self.yearly_rental_id)
        if not has_apartment and not has_yearly:
            raise ValidationError(
                "Either apartment or yearly_rental must be set on a Booking."
            )
        if has_apartment and has_yearly:
            raise ValidationError(
                "Only one of apartment or yearly_rental can be set on a Booking."
            )

    @property
    def booked_property(self):
        """Return whichever property FK is set."""
        return self.apartment or self.yearly_rental

    @staticmethod
    def calculate_base_amount(prop, check_in, check_out, rate_type):
        """Compute base_amount from dates and property rates."""
        import datetime

        if isinstance(check_in, str):
            check_in = datetime.date.fromisoformat(check_in)
        if isinstance(check_out, str):
            check_out = datetime.date.fromisoformat(check_out)
        days = (check_out - check_in).days
        if days <= 0:
            raise ValueError("check_out_date must be after check_in_date.")
        if rate_type == "nightly":
            if prop.rate_nightly is None:
                raise ValueError("Property has no nightly rate set.")
            return prop.rate_nightly * days
        if rate_type == "weekly":
            if prop.rate_weekly is None:
                raise ValueError("Property has no weekly rate set.")
            return prop.rate_weekly * Decimal(str(ceil(days / 7)))
        if rate_type == "monthly":
            if prop.rate_monthly is None:
                raise ValueError("Property has no monthly rate set.")
            months = max(1, round(days / 30))
            return prop.rate_monthly * Decimal(str(months))
        raise ValueError(f"Unknown rate_type: {rate_type}")


class BookingReceipt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField(
        Booking, on_delete=models.CASCADE, related_name="receipt"
    )
    receipt_number = models.CharField(max_length=20, unique=True)
    # PDF stored as base64-encoded string (S3 key path in production)
    pdf_file = models.TextField(blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipts_generated",
    )

    class Meta:
        db_table = "shortlets_receipt"

    def __str__(self):
        return self.receipt_number


class CautionDeposit(models.Model):
    REFUND_METHOD_CHOICES = [
        ("bank_transfer", "Bank Transfer"),
        ("cash", "Cash"),
        ("card_reversal", "Card Reversal"),
    ]
    STATUS_CHOICES = [
        ("held", "Held"),
        ("pending_refund", "Pending Refund"),
        ("approved_for_refund", "Approved for Refund"),
        ("refunded", "Refunded"),
        ("forfeited", "Forfeited"),
        ("disputed", "Disputed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField(
        Booking, on_delete=models.CASCADE, related_name="caution_deposit"
    )
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2)
    deduction_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    deduction_reason = models.TextField(blank=True)
    refund_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    refund_method = models.CharField(
        max_length=20, choices=REFUND_METHOD_CHOICES, blank=True
    )
    # Bank account number stored encrypted
    account_number = EncryptedCharField(blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="held")
    dispute_reason = models.TextField(blank=True)
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="caution_deposits_initiated",
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="caution_deposits_processed",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shortlets_cautiondeposit"

    def __str__(self):
        return f"Deposit for {self.booking_id} [{self.status}]"


class InventoryTemplate(models.Model):
    """Blueprint for inventory items associated with a unit type or specific apartment."""

    apartment = models.ForeignKey(
        ShortletApartment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inventory_templates",
    )
    yearly_rental = models.ForeignKey(
        YearlyRentalApartment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inventory_templates",
    )
    unit_type = models.CharField(
        max_length=20,
        choices=ShortletApartment.UNIT_TYPE_CHOICES,
        blank=True,
    )
    item_name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True)
    quantity_expected = models.PositiveIntegerField(default=1)
    is_consumable = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shortlets_inventory_template"
        ordering = ["item_name"]

    def __str__(self):
        return f"Template: {self.item_name} (qty {self.quantity_expected})"


class InventoryItem(models.Model):
    """Actual inventory item linked to a specific apartment or yearly rental."""

    apartment = models.ForeignKey(
        ShortletApartment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inventory_items",
    )
    yearly_rental = models.ForeignKey(
        YearlyRentalApartment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inventory_items",
    )
    item_name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True)
    quantity_total = models.PositiveIntegerField(default=1)
    quantity_good = models.PositiveIntegerField(default=1)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shortlets_inventory_item"
        ordering = ["item_name"]

    def __str__(self):
        return f"{self.item_name} (apt: {self.apartment_id or self.yearly_rental_id})"


class InventoryVerification(models.Model):
    """Immutable checkout verification record — cannot be updated after creation."""

    is_immutable = True  # class-level flag; enforced in save()

    booking = models.ForeignKey(
        Booking,
        on_delete=models.PROTECT,
        related_name="inventory_verifications",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inventory_verifications_created",
    )
    verified_at = models.DateTimeField(default=timezone.now)
    cleaning_fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    additional_charges = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shortlets_inventory_verification"
        ordering = ["-verified_at"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                "InventoryVerification records are immutable and cannot be updated."
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Verification for booking {self.booking_id} at {self.verified_at}"


class InventoryVerificationItem(models.Model):
    STATUS_CHOICES = [
        ("present_good", "Present & Good"),
        ("damaged", "Damaged"),
        ("missing", "Missing"),
        ("not_applicable", "Not Applicable"),
    ]

    verification = models.ForeignKey(
        InventoryVerification,
        on_delete=models.CASCADE,
        related_name="items",
    )
    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name="verification_items",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    estimated_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    notes = models.TextField(blank=True)
    photo = models.ImageField(upload_to="inventory_verification/", null=True, blank=True)

    class Meta:
        db_table = "shortlets_inventory_verification_item"

    def __str__(self):
        return f"{self.inventory_item.item_name} [{self.status}]"


class NairaBnBBookingRequest(models.Model):
    STATUS_CHOICES = [
        ("pending_review", "Pending Review"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
        ("expired", "Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nairabNb_reference = models.CharField(max_length=100, unique=True)
    apartment = models.ForeignKey(
        ShortletApartment,
        on_delete=models.PROTECT,
        related_name="nairabNb_requests",
    )
    client_name = models.CharField(max_length=200)
    client_email = models.EmailField(blank=True)
    client_phone = models.CharField(max_length=20, blank=True)
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    num_guests = models.PositiveSmallIntegerField(default=1)
    quoted_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending_review"
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    declined_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shortlets_nairabNb_request"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.pk and not self.expires_at:
            from datetime import timedelta
            self.expires_at = timezone.now() + timedelta(hours=24)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"NairaBnB {self.nairabNb_reference} [{self.status}]"
