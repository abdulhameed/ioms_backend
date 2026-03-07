"""
Shortlets service layer — Phase 5.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone


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


def generate_client_code():
    return _generate_code("shortlets_client_code_seq", "CLT-", year_fmt=False, width=4)


def generate_booking_code():
    return _generate_code("shortlets_booking_code_seq", "BKG-", year_fmt=True, width=4)


def generate_receipt_number():
    return _generate_code("shortlets_receipt_code_seq", "RCP-", year_fmt=True, width=4)


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
        Create a booking with double-booking prevention (SELECT FOR UPDATE).
        Auto-creates CautionDeposit and queues receipt PDF generation.
        """
        from apps.shortlets.models import Booking, CautionDeposit, ShortletProperty
        from apps.shortlets.tasks import generate_receipt_pdf

        prop = validated_data["property"]
        check_in = validated_data["check_in_date"]
        check_out = validated_data["check_out_date"]
        rate_type = validated_data["rate_type"]

        with transaction.atomic():
            # Lock property row to prevent concurrent double-booking
            prop = ShortletProperty.objects.select_for_update().get(pk=prop.pk)

            conflicts = Booking.objects.filter(
                property=prop,
                status__in=["confirmed", "checked_in"],
                check_in_date__lt=check_out,
                check_out_date__gt=check_in,
            )
            if conflicts.exists():
                raise BookingConflictError(
                    "Property is booked for these dates."
                )

            base_amount = Booking.calculate_base_amount(prop, check_in, check_out, rate_type)
            caution = prop.caution_deposit_amount
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

        booking.property.status = "occupied"
        booking.property.save(update_fields=["status", "updated_at"])

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

        booking.property.status = "available"
        booking.property.save(update_fields=["status", "updated_at"])

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
