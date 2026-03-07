"""
Shortlets service layer — Milestone 2.
"""

import hashlib
import hmac
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class BookingConflictError(Exception):
    """Raised when a booking overlaps an existing confirmed/checked-in reservation."""


class DuplicateClientError(Exception):
    """Raised when a client with matching email or phone already exists."""

    def __init__(self, existing_client):
        self.existing_client = existing_client
        super().__init__(f"Duplicate client: {existing_client.id}")


def _generate_code(sequence_name, prefix, year_fmt=None, width=4):
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(f"SELECT nextval('{sequence_name}')")
        seq = cur.fetchone()[0]
    if year_fmt:
        year = timezone.now().year
        return f"{prefix}{year}-{seq:0{width}d}"
    return f"{prefix}{seq:0{width}d}"


def generate_property_code():
    return _generate_code("shortlets_property_code_seq", "PROP-SL-", year_fmt=False, width=3)


def generate_yearly_rental_code():
    return _generate_code("shortlets_yearly_rental_code_seq", "YR-", year_fmt=False, width=3)


def generate_office_item_code():
    return _generate_code("shortlets_office_item_code_seq", "OFF-", year_fmt=False, width=3)


def generate_client_code():
    return _generate_code("shortlets_client_code_seq", "CLT-", year_fmt=False, width=4)


def generate_booking_code():
    return _generate_code("shortlets_booking_code_seq", "BKG-", year_fmt=True, width=4)


def generate_receipt_number():
    return _generate_code("shortlets_receipt_code_seq", "RCP-", year_fmt=True, width=4)


def validate_nairabNb_signature(request):
    """Validate HMAC-SHA256 signature from NairaBnB webhook request."""
    secret = (settings.NAIRABND_WEBHOOK_SECRET or "").encode()
    sig = request.headers.get("X-NairaBnB-Signature", "")
    expected = hmac.new(secret, request.body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


class ClientService:
    @staticmethod
    def find_duplicate(email=None, phone=None):
        """Return an existing Client matching email or phone, or None."""
        from apps.shortlets.models import Client
        from django.db.models import Q

        if not email and not phone:
            return None
        q = Q()
        if email:
            q |= Q(email__iexact=email)
        if phone:
            q |= Q(phone=phone)
        return Client.objects.filter(q).first()

    @staticmethod
    def create_client(validated_data, actor, force=False):
        """
        Create a new client. Raises DuplicateClientError if duplicate found
        and force=False. Pass force=True to bypass duplicate check.
        """
        from apps.shortlets.models import Client

        email = validated_data.get("email")
        phone = validated_data.get("phone")

        if not force:
            existing = ClientService.find_duplicate(email=email, phone=phone)
            if existing:
                raise DuplicateClientError(existing)

        client_code = generate_client_code()
        return Client.objects.create(
            **validated_data, client_code=client_code, created_by=actor
        )


class BookingService:
    @staticmethod
    def create_booking(validated_data, actor):
        """
        Create a booking with double-booking prevention (SELECT FOR UPDATE) for
        shortlet apartments. Supports both apartment and yearly_rental bookings.
        Auto-creates CautionDeposit and queues receipt PDF generation.
        """
        from apps.shortlets.models import (
            Booking,
            CautionDeposit,
            ShortletApartment,
        )
        from apps.shortlets.tasks import generate_receipt_pdf

        apartment = validated_data.get("apartment")
        yearly_rental = validated_data.get("yearly_rental")
        check_in = validated_data["check_in_date"]
        check_out = validated_data["check_out_date"]
        rate_type = validated_data["rate_type"]

        with transaction.atomic():
            if apartment:
                # Lock apartment row to prevent concurrent double-booking
                apartment = ShortletApartment.objects.select_for_update().get(
                    pk=apartment.pk
                )
                validated_data["apartment"] = apartment

                conflicts = Booking.objects.filter(
                    apartment=apartment,
                    status__in=["confirmed", "checked_in"],
                    check_in_date__lt=check_out,
                    check_out_date__gt=check_in,
                )
                if conflicts.exists():
                    raise BookingConflictError("Property is booked for these dates.")

                prop = apartment
                caution = apartment.caution_deposit_amount
            else:
                prop = yearly_rental
                caution = yearly_rental.deposit_amount

            base_amount = Booking.calculate_base_amount(prop, check_in, check_out, rate_type)
            total = base_amount + caution
            booking_code = generate_booking_code()

            booking = Booking.objects.create(
                **validated_data,
                booking_code=booking_code,
                base_amount=base_amount,
                caution_deposit_amount=caution,
                total_amount=total,
                created_by=actor,
                status="confirmed",
            )

            CautionDeposit.objects.create(
                booking=booking,
                deposit_amount=caution,
                initiated_by=actor,
                status="held",
            )

        # Queue outside the transaction so the task can read the committed row
        generate_receipt_pdf.delay(str(booking.id))
        return booking

    @staticmethod
    def check_in(booking, actor):
        """Transition: confirmed → checked_in; mark property occupied."""
        if booking.status != "confirmed":
            raise ValueError(
                f"Cannot check in a booking with status '{booking.status}'."
            )
        booking.status = "checked_in"
        booking.checked_in_at = timezone.now()
        booking.save(update_fields=["status", "checked_in_at", "updated_at"])

        if booking.apartment_id:
            booking.apartment.status = "occupied"
            booking.apartment.save(update_fields=["status", "updated_at"])
        elif booking.yearly_rental_id:
            booking.yearly_rental.lease_status = "leased"
            booking.yearly_rental.save(update_fields=["lease_status", "updated_at"])

    @staticmethod
    def check_out(booking, actor, condition, deduction_amount=None, notes=""):
        """
        Transition: checked_in → checked_out.
        Updates CautionDeposit and creates caution_refund ApprovalWorkflow.
        """
        from apps.approvals.models import ApprovalWorkflow
        from apps.approvals.services import ApprovalService
        from django.contrib.contenttypes.models import ContentType

        from apps.shortlets.models import CautionDeposit

        if booking.status != "checked_in":
            raise ValueError(
                f"Cannot check out a booking with status '{booking.status}'."
            )

        booking.status = "checked_out"
        booking.checked_out_at = timezone.now()
        booking.checkout_condition = condition or ""
        booking.save(
            update_fields=["status", "checked_out_at", "checkout_condition", "updated_at"]
        )

        if booking.apartment_id:
            booking.apartment.status = "available"
            booking.apartment.save(update_fields=["status", "updated_at"])
        elif booking.yearly_rental_id:
            booking.yearly_rental.lease_status = "available"
            booking.yearly_rental.save(update_fields=["lease_status", "updated_at"])

        # Update caution deposit
        deposit = booking.caution_deposit  # CautionDeposit related object
        deduction = Decimal(str(deduction_amount)) if deduction_amount else Decimal("0")
        refund = deposit.deposit_amount - deduction
        deposit.deduction_amount = deduction
        deposit.deduction_reason = notes or ""
        deposit.refund_amount = refund
        deposit.status = "pending_refund"
        deposit.save(
            update_fields=[
                "deduction_amount",
                "deduction_reason",
                "refund_amount",
                "status",
                "updated_at",
            ]
        )

        # Create and submit caution refund workflow (always requires L2)
        ct = ContentType.objects.get_for_model(CautionDeposit)
        workflow = ApprovalWorkflow.objects.create(
            workflow_type="caution_refund",
            content_type=ct,
            object_id=deposit.id,
            initiated_by=actor,
            amount=refund,
            requires_l2=True,
        )
        ApprovalService.submit(workflow)
        return booking


def accept_booking_request(request_id, accepted_by):
    """
    Accept a NairaBnB booking request atomically.
    Creates Client (or reuses existing), Booking, and CautionDeposit.
    """
    from apps.shortlets.models import (
        Booking,
        CautionDeposit,
        Client,
        NairaBnBBookingRequest,
    )

    with transaction.atomic():
        req = NairaBnBBookingRequest.objects.select_for_update().get(id=request_id)
        if req.status != "pending_review":
            raise ValueError(
                f"Cannot accept a request with status '{req.status}'."
            )

        # Find or create client from request data
        client = None
        if req.client_email:
            client = Client.objects.filter(email__iexact=req.client_email).first()
        if client is None and req.client_phone:
            client = Client.objects.filter(phone=req.client_phone).first()
        if client is None:
            client_code = generate_client_code()
            client = Client.objects.create(
                full_name=req.client_name,
                email=req.client_email or None,
                phone=req.client_phone or f"NBNB-{req.nairabNb_reference[:10]}",
                client_type="individual",
                client_code=client_code,
                created_by=accepted_by,
            )

        booking_code = generate_booking_code()
        booking = Booking.objects.create(
            booking_code=booking_code,
            client=client,
            apartment=req.apartment,
            nairabNb_reference=req.nairabNb_reference,
            check_in_date=req.check_in_date,
            check_out_date=req.check_out_date,
            rate_type="nightly",
            num_guests=req.num_guests,
            base_amount=req.quoted_amount,
            caution_deposit_amount=req.apartment.caution_deposit_amount,
            total_amount=req.quoted_amount + req.apartment.caution_deposit_amount,
            created_by=accepted_by,
            status="confirmed",
        )

        CautionDeposit.objects.create(
            booking=booking,
            deposit_amount=req.apartment.caution_deposit_amount,
            initiated_by=accepted_by,
            status="held",
        )

        req.status = "accepted"
        req.save(update_fields=["status", "updated_at"])

    return booking


def complete_checkout(booking, verification_data, user):
    """
    Create an InventoryVerification + items. Auto-create MaintenanceRequests
    for damaged/missing items.
    """
    from apps.shortlets.models import (
        InventoryItem,
        InventoryVerification,
        InventoryVerificationItem,
    )

    with transaction.atomic():
        verification = InventoryVerification.objects.create(
            booking=booking,
            created_by=user,
            cleaning_fee=verification_data.get("cleaning_fee", Decimal("0")),
            additional_charges=verification_data.get("additional_charges", Decimal("0")),
            notes=verification_data.get("notes", ""),
        )

        damaged_items = []
        for item_data in verification_data.get("items", []):
            item_id = item_data.get("inventory_item")
            item_status = item_data.get("status", "present_good")
            try:
                inv_item = InventoryItem.objects.get(pk=item_id)
            except InventoryItem.DoesNotExist:
                continue

            InventoryVerificationItem.objects.create(
                verification=verification,
                inventory_item=inv_item,
                status=item_status,
                estimated_cost=item_data.get("estimated_cost", Decimal("0")),
                notes=item_data.get("notes", ""),
            )

            if item_status in ("damaged", "missing"):
                damaged_items.append((inv_item, item_status, item_data.get("estimated_cost", 0)))

        # Auto-create maintenance requests for damaged/missing items
        if damaged_items:
            _auto_create_maintenance_for_damaged(booking, damaged_items, user)

    return verification


def _auto_create_maintenance_for_damaged(booking, damaged_items, reporter):
    """Create MaintenanceRequest rows for items flagged as damaged/missing."""
    from apps.maintenance.models import MaintenanceRequest

    for inv_item, item_status, _ in damaged_items:
        MaintenanceRequest.objects.create(
            issue_type="appliance",
            location_type="property",
            property=booking.apartment,
            description=f"Checkout issue: {inv_item.item_name} — {item_status}",
            priority="medium",
            reported_by=reporter,
        )


def generate_checkout_pdf(booking):
    """Generate a checkout/verification PDF for the booking using WeasyPrint."""
    try:
        from weasyprint import HTML

        html = _render_checkout_html(booking)
        return HTML(string=html).write_pdf()
    except Exception as exc:
        logger.warning("WeasyPrint checkout PDF failed for booking %s: %s", booking.id, exc)
        return b"%PDF-1.4 placeholder"


def _render_checkout_html(booking):
    verifications = booking.inventory_verifications.prefetch_related("items__inventory_item").all()
    rows = ""
    for v in verifications:
        for item in v.items.all():
            rows += (
                f"<tr><td>{item.inventory_item.item_name}</td>"
                f"<td>{item.status}</td>"
                f"<td>₦{item.estimated_cost:,.2f}</td>"
                f"<td>{item.notes}</td></tr>"
            )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Checkout Report</title></head>
<body>
  <h1>Checkout Report — {booking.booking_code or booking.id}</h1>
  <p>Client: {booking.client.full_name}</p>
  <p>Check-out: {booking.checked_out_at or 'N/A'}</p>
  <table border="1" style="width:100%;border-collapse:collapse;">
    <thead><tr><th>Item</th><th>Status</th><th>Est. Cost</th><th>Notes</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""
