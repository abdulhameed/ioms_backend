# Milestone 2 migration: rename ShortletProperty → ShortletApartment,
# rename Booking.property → Booking.apartment, add new models and fields.

import uuid
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("shortlets", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── 1. Rename ShortletProperty → ShortletApartment (keeps db_table) ────
        migrations.RenameModel(
            old_name="ShortletProperty",
            new_name="ShortletApartment",
        ),
        # ── 2. Add villa choice + nairabNb_listing_id to ShortletApartment ──────
        migrations.AlterField(
            model_name="shortletapartment",
            name="unit_type",
            field=models.CharField(
                choices=[
                    ("studio", "Studio"),
                    ("1_bedroom", "1 Bedroom"),
                    ("2_bedroom", "2 Bedroom"),
                    ("3_bedroom", "3 Bedroom"),
                    ("penthouse", "Penthouse"),
                    ("duplex", "Duplex"),
                    ("villa", "Villa"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="shortletapartment",
            name="nairabNb_listing_id",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        # ── 3. Rename Booking.property → Booking.apartment ────────────────────
        migrations.RenameField(
            model_name="booking",
            old_name="property",
            new_name="apartment",
        ),
        # Make apartment nullable (yearly_rental bookings won't have it set)
        migrations.AlterField(
            model_name="booking",
            name="apartment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="bookings",
                to="shortlets.shortletapartment",
            ),
        ),
        # ── 4. Add nairabNb_reference to Booking ──────────────────────────────
        migrations.AddField(
            model_name="booking",
            name="nairabNb_reference",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        # ── 5. Add dispute_reason to CautionDeposit and update status choices ──
        migrations.AddField(
            model_name="cautiondeposit",
            name="dispute_reason",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="cautiondeposit",
            name="status",
            field=models.CharField(
                choices=[
                    ("held", "Held"),
                    ("pending_refund", "Pending Refund"),
                    ("approved_for_refund", "Approved for Refund"),
                    ("refunded", "Refunded"),
                    ("forfeited", "Forfeited"),
                    ("disputed", "Disputed"),
                ],
                default="held",
                max_length=30,
            ),
        ),
        # ── 6. Create YearlyRentalApartment ────────────────────────────────────
        migrations.CreateModel(
            name="YearlyRentalApartment",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "property_code",
                    models.CharField(blank=True, max_length=20, null=True, unique=True),
                ),
                ("name", models.CharField(max_length=200)),
                (
                    "unit_type",
                    models.CharField(
                        choices=[
                            ("studio", "Studio"),
                            ("1_bedroom", "1 Bedroom"),
                            ("2_bedroom", "2 Bedroom"),
                            ("3_bedroom", "3 Bedroom"),
                            ("penthouse", "Penthouse"),
                            ("duplex", "Duplex"),
                            ("villa", "Villa"),
                        ],
                        max_length=20,
                    ),
                ),
                ("location", models.CharField(max_length=300)),
                ("rate_yearly", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "deposit_amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=12
                    ),
                ),
                (
                    "lease_status",
                    models.CharField(
                        choices=[
                            ("available", "Available"),
                            ("leased", "Leased"),
                            ("maintenance", "Under Maintenance"),
                            ("inactive", "Inactive"),
                        ],
                        default="available",
                        max_length=20,
                    ),
                ),
                ("rent_due_date", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "current_tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rented_apartments",
                        to="shortlets.client",
                    ),
                ),
            ],
            options={
                "db_table": "shortlets_yearly_rental",
                "ordering": ["name"],
            },
        ),
        # ── 7. Add yearly_rental FK to Booking ────────────────────────────────
        migrations.AddField(
            model_name="booking",
            name="yearly_rental",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="bookings",
                to="shortlets.yearlyrentalapartment",
            ),
        ),
        # ── 8. Create OfficeItem ───────────────────────────────────────────────
        migrations.CreateModel(
            name="OfficeItem",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "item_code",
                    models.CharField(blank=True, max_length=20, null=True, unique=True),
                ),
                ("item_name", models.CharField(max_length=200)),
                (
                    "item_category",
                    models.CharField(
                        choices=[
                            ("furniture", "Furniture"),
                            ("electronics", "Electronics"),
                            ("appliances", "Appliances"),
                            ("equipment", "Equipment"),
                            ("stationery", "Stationery"),
                        ],
                        max_length=20,
                    ),
                ),
                ("department", models.CharField(blank=True, max_length=100)),
                (
                    "condition",
                    models.CharField(
                        choices=[
                            ("good", "Good"),
                            ("fair", "Fair"),
                            ("poor", "Poor"),
                            ("damaged", "Damaged"),
                        ],
                        default="good",
                        max_length=10,
                    ),
                ),
                ("location_detail", models.CharField(blank=True, max_length=300)),
                ("acquired_date", models.DateField(blank=True, null=True)),
                (
                    "purchase_cost",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "shortlets_office_item",
                "ordering": ["item_name"],
            },
        ),
        # ── 9. Create InventoryTemplate ───────────────────────────────────────
        migrations.CreateModel(
            name="InventoryTemplate",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "unit_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("studio", "Studio"),
                            ("1_bedroom", "1 Bedroom"),
                            ("2_bedroom", "2 Bedroom"),
                            ("3_bedroom", "3 Bedroom"),
                            ("penthouse", "Penthouse"),
                            ("duplex", "Duplex"),
                            ("villa", "Villa"),
                        ],
                        max_length=20,
                    ),
                ),
                ("item_name", models.CharField(max_length=200)),
                ("category", models.CharField(blank=True, max_length=100)),
                ("quantity_expected", models.PositiveIntegerField(default=1)),
                ("is_consumable", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "apartment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inventory_templates",
                        to="shortlets.shortletapartment",
                    ),
                ),
                (
                    "yearly_rental",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inventory_templates",
                        to="shortlets.yearlyrentalapartment",
                    ),
                ),
            ],
            options={
                "db_table": "shortlets_inventory_template",
                "ordering": ["item_name"],
            },
        ),
        # ── 10. Create InventoryItem ──────────────────────────────────────────
        migrations.CreateModel(
            name="InventoryItem",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("item_name", models.CharField(max_length=200)),
                ("category", models.CharField(blank=True, max_length=100)),
                ("quantity_total", models.PositiveIntegerField(default=1)),
                ("quantity_good", models.PositiveIntegerField(default=1)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "apartment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inventory_items",
                        to="shortlets.shortletapartment",
                    ),
                ),
                (
                    "yearly_rental",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inventory_items",
                        to="shortlets.yearlyrentalapartment",
                    ),
                ),
            ],
            options={
                "db_table": "shortlets_inventory_item",
                "ordering": ["item_name"],
            },
        ),
        # ── 11. Create InventoryVerification ──────────────────────────────────
        migrations.CreateModel(
            name="InventoryVerification",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("verified_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "cleaning_fee",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=12
                    ),
                ),
                (
                    "additional_charges",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=12
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "booking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inventory_verifications",
                        to="shortlets.booking",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inventory_verifications_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "shortlets_inventory_verification",
                "ordering": ["-verified_at"],
            },
        ),
        # ── 12. Create InventoryVerificationItem ──────────────────────────────
        migrations.CreateModel(
            name="InventoryVerificationItem",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("present_good", "Present & Good"),
                            ("damaged", "Damaged"),
                            ("missing", "Missing"),
                            ("not_applicable", "Not Applicable"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "estimated_cost",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=12
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                (
                    "photo",
                    models.ImageField(
                        blank=True, null=True, upload_to="inventory_verification/"
                    ),
                ),
                (
                    "inventory_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="verification_items",
                        to="shortlets.inventoryitem",
                    ),
                ),
                (
                    "verification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="shortlets.inventoryverification",
                    ),
                ),
            ],
            options={
                "db_table": "shortlets_inventory_verification_item",
            },
        ),
        # ── 13. Create NairaBnBBookingRequest ─────────────────────────────────
        migrations.CreateModel(
            name="NairaBnBBookingRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("nairabNb_reference", models.CharField(max_length=100, unique=True)),
                ("client_name", models.CharField(max_length=200)),
                ("client_email", models.EmailField(blank=True)),
                ("client_phone", models.CharField(blank=True, max_length=20)),
                ("check_in_date", models.DateField()),
                ("check_out_date", models.DateField()),
                ("num_guests", models.PositiveSmallIntegerField(default=1)),
                (
                    "quoted_amount",
                    models.DecimalField(decimal_places=2, max_digits=12),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending_review", "Pending Review"),
                            ("accepted", "Accepted"),
                            ("declined", "Declined"),
                            ("expired", "Expired"),
                        ],
                        default="pending_review",
                        max_length=20,
                    ),
                ),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("declined_reason", models.TextField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "apartment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="nairabNb_requests",
                        to="shortlets.shortletapartment",
                    ),
                ),
            ],
            options={
                "db_table": "shortlets_nairabNb_request",
                "ordering": ["-created_at"],
            },
        ),
        # ── 14. Sequences for new code fields ──────────────────────────────────
        migrations.RunSQL(
            sql="CREATE SEQUENCE IF NOT EXISTS shortlets_yearly_rental_code_seq;",
            reverse_sql="DROP SEQUENCE IF EXISTS shortlets_yearly_rental_code_seq;",
        ),
        migrations.RunSQL(
            sql="CREATE SEQUENCE IF NOT EXISTS shortlets_office_item_code_seq;",
            reverse_sql="DROP SEQUENCE IF EXISTS shortlets_office_item_code_seq;",
        ),
    ]
