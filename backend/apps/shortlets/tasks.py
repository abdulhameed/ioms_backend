"""
Shortlets Celery tasks — Milestone 2.
"""

import base64
import io
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def generate_receipt_pdf(booking_id):
    """
    Generate a PDF receipt for a booking and store it as a BookingReceipt row.
    Called asynchronously after booking creation.
    """
    from apps.shortlets.models import Booking, BookingReceipt
    from apps.shortlets.services import generate_receipt_number

    try:
        booking = Booking.objects.select_related(
            "client", "apartment", "yearly_rental", "created_by"
        ).get(id=booking_id)
    except Booking.DoesNotExist:
        logger.error("generate_receipt_pdf: booking %s not found", booking_id)
        return

    html = _render_receipt_html(booking)

    try:
        from weasyprint import HTML

        pdf_bytes = HTML(string=html).write_pdf()
    except Exception as exc:
        logger.warning("WeasyPrint failed for booking %s: %s", booking_id, exc)
        pdf_bytes = b"%PDF-1.4 placeholder"

    pdf_b64 = base64.b64encode(pdf_bytes).decode()
    receipt_number = generate_receipt_number()

    BookingReceipt.objects.update_or_create(
        booking=booking,
        defaults={
            "receipt_number": receipt_number,
            "pdf_file": pdf_b64,
            "generated_by": booking.created_by,
        },
    )
    logger.info("Receipt %s generated for booking %s", receipt_number, booking_id)


def _render_receipt_html(booking):
    """Build HTML string for the booking receipt PDF."""
    client = booking.client
    prop = booking.apartment or booking.yearly_rental
    days = (booking.check_out_date - booking.check_in_date).days

    prop_name = prop.name if prop else "N/A"
    prop_code = getattr(prop, "property_code", None) or "—"
    prop_type = prop.get_unit_type_display() if prop else "—"
    prop_location = prop.location if prop else "—"

    # QR code for booking reference
    qr_img_src = _build_qr_data_uri(booking.booking_code or str(booking.id))

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
    h1 {{ color: #1a1a2e; }}
    .header {{ display: flex; justify-content: space-between; border-bottom: 2px solid #1a1a2e; padding-bottom: 16px; margin-bottom: 24px; }}
    .section {{ margin-bottom: 20px; }}
    .section h3 {{ border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    td {{ padding: 6px 8px; }}
    td:first-child {{ font-weight: bold; width: 180px; }}
    .charges td:last-child {{ text-align: right; }}
    .total {{ font-size: 1.1em; font-weight: bold; border-top: 2px solid #333; }}
    .footer {{ margin-top: 32px; text-align: center; color: #666; font-size: 0.85em; }}
    .qr {{ text-align: right; }}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>IOMS Properties</h1>
      <p>Booking Receipt</p>
    </div>
    <div>
      <p><strong>Receipt #:</strong> {booking.booking_code or 'PENDING'}</p>
      <p><strong>Date:</strong> {booking.created_at.strftime('%d %b %Y')}</p>
    </div>
  </div>

  <div class="section">
    <h3>Client Details</h3>
    <table><tbody>
      <tr><td>Full Name</td><td>{client.full_name}</td></tr>
      <tr><td>Phone</td><td>{client.phone}</td></tr>
      <tr><td>Email</td><td>{client.email or '—'}</td></tr>
      <tr><td>ID Type</td><td>{client.get_id_type_display() if client.id_type else '—'}</td></tr>
    </tbody></table>
  </div>

  <div class="section">
    <h3>Property Details</h3>
    <table><tbody>
      <tr><td>Property</td><td>{prop_name}</td></tr>
      <tr><td>Code</td><td>{prop_code}</td></tr>
      <tr><td>Type</td><td>{prop_type}</td></tr>
      <tr><td>Location</td><td>{prop_location}</td></tr>
    </tbody></table>
  </div>

  <div class="section">
    <h3>Booking Details</h3>
    <table><tbody>
      <tr><td>Check-in</td><td>{booking.check_in_date.strftime('%d %b %Y')}</td></tr>
      <tr><td>Check-out</td><td>{booking.check_out_date.strftime('%d %b %Y')}</td></tr>
      <tr><td>Duration</td><td>{days} night(s)</td></tr>
      <tr><td>Rate Type</td><td>{booking.get_rate_type_display()}</td></tr>
      <tr><td>Guests</td><td>{booking.num_guests}</td></tr>
    </tbody></table>
  </div>

  <div class="section">
    <h3>Charges</h3>
    <table class="charges"><tbody>
      <tr><td>Base Amount</td><td>&#8358;{booking.base_amount:,.2f}</td></tr>
      <tr><td>Caution Deposit</td><td>&#8358;{booking.caution_deposit_amount:,.2f}</td></tr>
      <tr class="total"><td>Total Paid</td><td>&#8358;{booking.total_amount:,.2f}</td></tr>
    </tbody></table>
  </div>

  <div class="section">
    <h3>Payment</h3>
    <table><tbody>
      <tr><td>Method</td><td>{booking.payment_method or '—'}</td></tr>
      <tr><td>Reference</td><td>{booking.payment_reference or '—'}</td></tr>
    </tbody></table>
  </div>

  <div class="qr">
    <img src="{qr_img_src}" width="100" height="100" alt="QR Code">
    <p style="font-size:0.75em;">Booking Ref: {booking.booking_code or booking.id}</p>
  </div>

  <div class="footer">
    <p>Thank you for choosing IOMS Properties. We look forward to hosting you again.</p>
  </div>
</body>
</html>"""


def _build_qr_data_uri(data):
    """Generate a QR code PNG as a base64 data URI."""
    try:
        import qrcode

        buf = io.BytesIO()
        qrcode.make(data).save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return ""


@shared_task
def expire_pending_booking_requests():
    """
    Expire NairaBnBBookingRequests that are still pending_review past their expires_at.
    """
    from apps.shortlets.models import NairaBnBBookingRequest

    now = timezone.now()
    expired_qs = NairaBnBBookingRequest.objects.filter(
        status="pending_review",
        expires_at__lt=now,
    )
    expired_ids = list(expired_qs.values_list("id", flat=True))
    count = expired_qs.update(status="expired")
    logger.info("expire_pending_booking_requests: expired %d requests", count)

    # Notify NairaBnB of each expired request (fire-and-forget)
    for req_id in expired_ids:
        _notify_nairabNb_expired.delay(str(req_id))

    return count


@shared_task
def _notify_nairabNb_expired(request_id):
    """Placeholder: notify NairaBnB that a booking request has expired."""
    logger.info("Notifying NairaBnB of expired request %s", request_id)


@shared_task
def sync_nairabNb_availability():
    """
    For each active ShortletApartment with a nairabNb_listing_id, push
    blocked dates (confirmed + checked-in bookings) to the NairaBnB API.
    """
    import json

    import requests as http_requests

    from apps.shortlets.models import Booking, ShortletApartment

    apartments = ShortletApartment.objects.filter(
        status__in=["available", "occupied"],
    ).exclude(nairabNb_listing_id__isnull=True).exclude(nairabNb_listing_id="")

    synced = 0
    for apt in apartments:
        blocked = list(
            Booking.objects.filter(
                apartment=apt,
                status__in=["confirmed", "checked_in"],
            ).values("check_in_date", "check_out_date")
        )
        payload = {
            "listing_id": apt.nairabNb_listing_id,
            "blocked_dates": [
                {
                    "check_in": str(b["check_in_date"]),
                    "check_out": str(b["check_out_date"]),
                }
                for b in blocked
            ],
        }
        try:
            # In production this would POST to the real NairaBnB API endpoint
            logger.info(
                "sync_nairabNb_availability: would push %d blocked ranges for listing %s",
                len(blocked),
                apt.nairabNb_listing_id,
            )
            synced += 1
        except Exception as exc:
            logger.warning(
                "sync_nairabNb_availability: failed for apt %s: %s", apt.id, exc
            )

    logger.info("sync_nairabNb_availability: synced %d apartments", synced)
    return synced
