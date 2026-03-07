"""
Shortlets app models — Phase 5.

Models:
  ShortletProperty  — Rental unit with nightly/weekly/monthly rates
  Client            — Guest/tenant record with duplicate-detection support
  Booking           — Reservation with double-booking prevention via SELECT FOR UPDATE
  BookingReceipt    — Pre-generated PDF receipt (OneToOne with Booking)
  CautionDeposit    — Security deposit lifecycle (held → pending_refund → approved_for_refund)
"""

import uuid
from decimal import Decimal
from math import ceil

from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedCharField


class ShortletProperty(models.Model):
    UNIT_TYPE_CHOICES = [
        ("studio", "Studio"),
        ("1_bedroom", "1 Bedroom"),
        ("2_bedroom", "2 Bedroom"),
        ("3_bedroom", "3 Bedroom"),
        ("penthouse", "Penthouse"),
        ("duplex", "Duplex"),
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shortlets_property"
        ordering = ["name"]

    def __str__(self):
        return f"{self.property_code or 'UNPUBLISHED'} — {self.name}"


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
    property = models.ForeignKey(
        ShortletProperty, on_delete=models.PROTECT, related_name="bookings"
    )
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
