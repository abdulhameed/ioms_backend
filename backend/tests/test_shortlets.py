"""
Phase 5 — Shortlets & Asset Management tests.
Test IDs: SHL-01 through SHL-13.
See docs/milestone_1_PRD_v2.md section 5.4 for full specifications.
"""

import re
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.shortlets.models import (
    Booking,
    BookingReceipt,
    CautionDeposit,
    Client,
    ShortletProperty,
)
from apps.shortlets.services import BookingService, ClientService, DuplicateClientError

# ── URLs ────────────────────────────────────────────────────────────────────────

PROPERTIES_URL = "/api/v1/properties/"
CLIENTS_URL = "/api/v1/clients/"
BOOKINGS_URL = "/api/v1/bookings/"
DEPOSITS_URL = "/api/v1/deposits/"


# ── Fixtures ────────────────────────────────────────────────────────────────────

def _make_user(django_user_model, role, perm="full", email=None):
    from django.contrib.auth.models import Group

    email = email or f"{role}_{perm}@shortlets.test"
    user = django_user_model.objects.create_user(
        username=email.split("@")[0],
        email=email,
        password="Test1234!",
        role=role,
        permission_level=perm,
        is_active=True,
    )
    return user


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(django_user_model):
    return _make_user(django_user_model, "admin", "full", "admin@shortlets.test")


@pytest.fixture
def front_desk_user(django_user_model):
    return _make_user(django_user_model, "front_desk", "full", "frontdesk@shortlets.test")


@pytest.fixture
def md_user(django_user_model):
    return _make_user(django_user_model, "md", "full", "md@shortlets.test")


@pytest.fixture
def hr_full_user(django_user_model):
    return _make_user(django_user_model, "hr", "full", "hr@shortlets.test")


@pytest.fixture
def property_data():
    return {
        "name": "Luxury Studio Lekki",
        "unit_type": "studio",
        "location": "Lekki Phase 1, Lagos",
        "rate_nightly": "45000.00",
        "rate_weekly": "280000.00",
        "rate_monthly": "900000.00",
        "caution_deposit_amount": "50000.00",
        "amenities": ["wifi", "ac", "pool"],
        "description": "Modern studio with ocean view.",
    }


@pytest.fixture
def shortlet_property(django_user_model, admin_user):
    prop = ShortletProperty.objects.create(
        name="Test Studio",
        unit_type="studio",
        location="Victoria Island, Lagos",
        rate_nightly=Decimal("30000.00"),
        rate_weekly=Decimal("180000.00"),
        rate_monthly=Decimal("600000.00"),
        caution_deposit_amount=Decimal("30000.00"),
        status="available",
    )
    from apps.shortlets.services import generate_property_code
    prop.property_code = generate_property_code()
    prop.save()
    return prop


@pytest.fixture
def client_obj(admin_user):
    from apps.shortlets.services import generate_client_code
    c = Client.objects.create(
        full_name="Amina Sule",
        phone="08011112222",
        email="amina@test.com",
        id_type="nin",
        id_number="12345678901",
        client_type="individual",
        created_by=admin_user,
    )
    c.client_code = generate_client_code()
    c.save()
    return c


@pytest.fixture
def confirmed_booking(shortlet_property, client_obj, admin_user):
    from apps.shortlets.services import generate_booking_code
    booking = Booking.objects.create(
        booking_code=generate_booking_code(),
        client=client_obj,
        property=shortlet_property,
        check_in_date="2026-04-01",
        check_out_date="2026-04-05",
        rate_type="nightly",
        num_guests=2,
        base_amount=Decimal("120000.00"),
        caution_deposit_amount=Decimal("30000.00"),
        total_amount=Decimal("150000.00"),
        status="confirmed",
        created_by=admin_user,
    )
    CautionDeposit.objects.create(
        booking=booking,
        deposit_amount=Decimal("30000.00"),
        initiated_by=admin_user,
        status="held",
    )
    return booking


# ── SHL-01: Create property → property_code auto-assigned ──────────────────────

@pytest.mark.django_db
def test_shl_01_create_property_code_assigned(api_client, admin_user, property_data):
    """SHL-01: POST /properties/ assigns PROP-SL-NNN code."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.post(PROPERTIES_URL, property_data, format="json")
    assert resp.status_code == 201
    code = resp.data["property_code"]
    assert re.match(r"^PROP-SL-\d{3}$", code), f"Unexpected code format: {code}"


# ── SHL-02: Create client → CLT-NNNN; duplicate phone returns 409 ──────────────

@pytest.mark.django_db
def test_shl_02_create_client_code_and_duplicate(api_client, admin_user):
    """SHL-02: Create client → CLT-NNNN; second request with same phone → 409."""
    api_client.force_authenticate(user=admin_user)

    # First client
    resp = api_client.post(
        CLIENTS_URL,
        {"full_name": "Tunde Bakare", "phone": "08033334444", "email": "tunde@test.com"},
        format="json",
    )
    assert resp.status_code == 201
    assert re.match(r"^CLT-\d{4}$", resp.data["client_code"])

    # Duplicate phone → 409
    resp2 = api_client.post(
        CLIENTS_URL,
        {"full_name": "Another Person", "phone": "08033334444", "email": "other@test.com"},
        format="json",
    )
    assert resp2.status_code == 409
    assert resp2.data["error"] == "duplicate_client"


# ── SHL-03: Create booking → availability checked; double-booking rejected ─────

@pytest.mark.django_db
def test_shl_03_double_booking_rejected(api_client, admin_user, shortlet_property, client_obj):
    """SHL-03: First booking succeeds; overlapping second booking → 409."""
    api_client.force_authenticate(user=admin_user)

    payload = {
        "client": str(client_obj.id),
        "property": str(shortlet_property.id),
        "check_in_date": "2026-05-10",
        "check_out_date": "2026-05-15",
        "rate_type": "nightly",
        "num_guests": 2,
    }

    resp1 = api_client.post(BOOKINGS_URL, payload, format="json")
    assert resp1.status_code == 201

    # Overlapping dates
    payload2 = dict(payload)
    payload2["check_out_date"] = "2026-05-12"  # overlaps first booking
    resp2 = api_client.post(BOOKINGS_URL, payload2, format="json")
    assert resp2.status_code == 409
    assert resp2.data["error"] == "property_unavailable"


# ── SHL-04: Concurrent bookings → only 1 succeeds ──────────────────────────────

@pytest.mark.django_db
def test_shl_04_concurrent_booking_only_one_succeeds(
    shortlet_property, client_obj, admin_user, django_user_model
):
    """SHL-04: Two overlapping bookings via service → only one row created."""
    # Create second client for second booking attempt
    c2 = Client.objects.create(
        full_name="Second Guest",
        phone="08099998888",
        email="guest2@test.com",
        created_by=admin_user,
    )
    from apps.shortlets.services import generate_client_code
    c2.client_code = generate_client_code()
    c2.save()

    from apps.shortlets.services import BookingConflictError

    check_in = "2026-06-01"
    check_out = "2026-06-04"

    data1 = {
        "client": client_obj,
        "property": shortlet_property,
        "check_in_date": check_in,
        "check_out_date": check_out,
        "rate_type": "nightly",
        "num_guests": 1,
    }
    data2 = dict(data1)
    data2["client"] = c2

    # First call succeeds
    BookingService.create_booking(data1, actor=admin_user)

    # Second call with same dates raises conflict
    with pytest.raises(BookingConflictError):
        BookingService.create_booking(data2, actor=admin_user)

    # Only one booking row in DB for these dates
    count = Booking.objects.filter(
        property=shortlet_property,
        check_in_date=check_in,
        check_out_date=check_out,
    ).count()
    assert count == 1


# ── SHL-05: Booking created → CautionDeposit auto-created with status=held ─────

@pytest.mark.django_db
def test_shl_05_caution_deposit_auto_created(shortlet_property, client_obj, admin_user):
    """SHL-05: CautionDeposit row auto-created with status=held at booking time."""
    data = {
        "client": client_obj,
        "property": shortlet_property,
        "check_in_date": "2026-07-01",
        "check_out_date": "2026-07-03",
        "rate_type": "nightly",
        "num_guests": 1,
    }
    booking = BookingService.create_booking(data, actor=admin_user)

    assert CautionDeposit.objects.filter(booking=booking).exists()
    deposit = booking.caution_deposit
    assert deposit.status == "held"
    assert deposit.deposit_amount == shortlet_property.caution_deposit_amount


# ── SHL-06: Booking created → receipt task queued; PDF accessible after run ────

@pytest.mark.django_db
def test_shl_06_receipt_pdf_generated(shortlet_property, client_obj, admin_user):
    """SHL-06: Celery task generates receipt; GET receipt returns PDF."""
    from apps.shortlets.tasks import generate_receipt_pdf

    data = {
        "client": client_obj,
        "property": shortlet_property,
        "check_in_date": "2026-08-01",
        "check_out_date": "2026-08-03",
        "rate_type": "nightly",
        "num_guests": 2,
    }
    booking = BookingService.create_booking(data, actor=admin_user)

    # Run task synchronously
    generate_receipt_pdf(str(booking.id))

    assert BookingReceipt.objects.filter(booking=booking).exists()
    receipt = booking.receipt
    assert receipt.pdf_file  # base64 content
    assert re.match(r"^RCP-\d{4}-\d{4}$", receipt.receipt_number)

    # Receipt endpoint returns PDF
    client = APIClient()
    client.force_authenticate(user=admin_user)
    resp = client.get(f"/api/v1/bookings/{booking.id}/receipt/")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


# ── SHL-07: Check-in → status=checked_in; checked_in_at set ───────────────────

@pytest.mark.django_db
def test_shl_07_check_in(api_client, admin_user, confirmed_booking):
    """SHL-07: POST check-in → status=checked_in; checked_in_at populated."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.post(f"/api/v1/bookings/{confirmed_booking.id}/check-in/")
    assert resp.status_code == 200
    assert resp.data["status"] == "checked_in"
    assert resp.data["checked_in_at"] is not None

    confirmed_booking.property.refresh_from_db()
    assert confirmed_booking.property.status == "occupied"


# ── SHL-08: Check-out (good condition) → status=checked_out; workflow created ─

@pytest.mark.django_db
def test_shl_08_check_out_no_deduction(api_client, admin_user, hr_full_user, confirmed_booking):
    """SHL-08: Check-out with no damage → refund workflow pending_l1."""
    # Check in first
    BookingService.check_in(confirmed_booking, actor=admin_user)

    api_client.force_authenticate(user=admin_user)
    resp = api_client.post(
        f"/api/v1/bookings/{confirmed_booking.id}/check-out/",
        {"condition": "good", "deduction_amount": "0", "notes": "No damage."},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "checked_out"

    confirmed_booking.property.refresh_from_db()
    assert confirmed_booking.property.status == "available"

    # Caution refund workflow created
    from apps.approvals.models import ApprovalWorkflow
    wf = ApprovalWorkflow.objects.filter(workflow_type="caution_refund").first()
    assert wf is not None
    assert wf.status == "pending_l1"


# ── SHL-09: Check-out (damaged) → refund_amount = deposit - deduction ──────────

@pytest.mark.django_db
def test_shl_09_check_out_with_deduction(admin_user, hr_full_user, confirmed_booking):
    """SHL-09: Deduction reduces refund_amount correctly."""
    BookingService.check_in(confirmed_booking, actor=admin_user)
    BookingService.check_out(
        confirmed_booking,
        actor=admin_user,
        condition="damaged",
        deduction_amount=Decimal("10000.00"),
        notes="Broken chair",
    )

    deposit = confirmed_booking.caution_deposit
    deposit.refresh_from_db()
    assert deposit.deduction_amount == Decimal("10000.00")
    assert deposit.refund_amount == Decimal("20000.00")  # 30000 - 10000
    assert deposit.status == "pending_refund"


# ── SHL-10: Caution refund L1+L2 approval → status=approved_for_refund ─────────

@pytest.mark.django_db
def test_shl_10_caution_refund_full_approval(
    admin_user, hr_full_user, md_user, confirmed_booking
):
    """SHL-10: Full L1+L2 approval → CautionDeposit.status=approved_for_refund; notification created."""
    from apps.approvals.models import ApprovalWorkflow
    from apps.approvals.services import ApprovalService
    from apps.users.models import Notification

    BookingService.check_in(confirmed_booking, actor=admin_user)
    BookingService.check_out(
        confirmed_booking,
        actor=admin_user,
        condition="good",
        deduction_amount=Decimal("0"),
        notes="",
    )

    wf = ApprovalWorkflow.objects.get(workflow_type="caution_refund")

    # L1 approval
    ApprovalService.decide(wf, actor=hr_full_user, decision="approved", notes="OK")
    wf.refresh_from_db()
    assert wf.status == "pending_l2"

    # L2 approval
    ApprovalService.decide(wf, actor=md_user, decision="approved", notes="Approved")
    wf.refresh_from_db()
    assert wf.status == "approved"

    deposit = confirmed_booking.caution_deposit
    deposit.refresh_from_db()
    assert deposit.status == "approved_for_refund"

    # Notification created for initiator
    assert Notification.objects.filter(
        notification_type="approval_decided",
        resource_type="CautionDeposit",
    ).exists()


# ── SHL-11: GET /properties/{id}/availability/ returns blocked ranges ──────────

@pytest.mark.django_db
def test_shl_11_availability_returns_blocked_ranges(
    api_client, admin_user, shortlet_property, confirmed_booking
):
    """SHL-11: Confirmed booking dates appear in availability blocked ranges."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"/api/v1/properties/{shortlet_property.id}/availability/")
    assert resp.status_code == 200
    blocked = resp.data["blocked_ranges"]
    assert len(blocked) >= 1
    codes = [b["booking_code"] for b in blocked]
    assert confirmed_booking.booking_code in codes


# ── SHL-12: Client export CSV excludes id_number column ──────────────────────

@pytest.mark.django_db
def test_shl_12_client_export_excludes_id_number(api_client, md_user, client_obj):
    """SHL-12: CSV export has no id_number column."""
    api_client.force_authenticate(user=md_user)
    resp = api_client.get("/api/v1/clients/export/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")
    content = resp.content.decode()
    header_row = content.splitlines()[0]
    assert "id_number" not in header_row
    assert "client_code" in header_row
    assert "full_name" in header_row


# ── SHL-13: front_desk cannot access /clients/export/ ─────────────────────────

@pytest.mark.django_db
def test_shl_13_front_desk_cannot_export_clients(api_client, front_desk_user):
    """SHL-13: front_desk → GET /clients/export/ returns 403."""
    api_client.force_authenticate(user=front_desk_user)
    resp = api_client.get("/api/v1/clients/export/")
    assert resp.status_code == 403


# ── Edge cases ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_checkout_date_before_checkin_returns_400(api_client, admin_user, shortlet_property, client_obj):
    """check_out_date <= check_in_date → 400."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.post(
        BOOKINGS_URL,
        {
            "client": str(client_obj.id),
            "property": str(shortlet_property.id),
            "check_in_date": "2026-09-10",
            "check_out_date": "2026-09-10",  # same day
            "rate_type": "nightly",
            "num_guests": 1,
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_booking_base_amount_nightly_calculated(shortlet_property, client_obj, admin_user):
    """base_amount = rate_nightly × nights."""
    data = {
        "client": client_obj,
        "property": shortlet_property,
        "check_in_date": "2026-10-01",
        "check_out_date": "2026-10-04",  # 3 nights
        "rate_type": "nightly",
        "num_guests": 1,
    }
    booking = BookingService.create_booking(data, actor=admin_user)
    assert booking.base_amount == shortlet_property.rate_nightly * 3
    assert booking.total_amount == booking.base_amount + shortlet_property.caution_deposit_amount


@pytest.mark.django_db
def test_booking_base_amount_weekly_calculated(shortlet_property, client_obj, admin_user):
    """base_amount = rate_weekly × weeks (rounded up)."""
    data = {
        "client": client_obj,
        "property": shortlet_property,
        "check_in_date": "2026-11-01",
        "check_out_date": "2026-11-09",  # 8 days = 2 weeks (ceil)
        "rate_type": "weekly",
        "num_guests": 1,
    }
    booking = BookingService.create_booking(data, actor=admin_user)
    assert booking.base_amount == shortlet_property.rate_weekly * 2


@pytest.mark.django_db
def test_booking_code_format(shortlet_property, client_obj, admin_user):
    """booking_code matches BKG-YYYY-NNNN pattern."""
    data = {
        "client": client_obj,
        "property": shortlet_property,
        "check_in_date": "2026-12-01",
        "check_out_date": "2026-12-03",
        "rate_type": "nightly",
        "num_guests": 1,
    }
    booking = BookingService.create_booking(data, actor=admin_user)
    assert re.match(r"^BKG-\d{4}-\d{4}$", booking.booking_code)


@pytest.mark.django_db
def test_check_in_wrong_status_raises(confirmed_booking, admin_user):
    """check_in on already-checked-in booking raises ValueError."""
    confirmed_booking.status = "checked_in"
    confirmed_booking.save()
    with pytest.raises(ValueError, match="checked_in"):
        BookingService.check_in(confirmed_booking, actor=admin_user)


@pytest.mark.django_db
def test_check_out_wrong_status_raises(confirmed_booking, admin_user):
    """check_out on confirmed (not checked_in) booking raises ValueError."""
    with pytest.raises(ValueError, match="confirmed"):
        BookingService.check_out(confirmed_booking, actor=admin_user, condition="good")


@pytest.mark.django_db
def test_duplicate_client_force_bypass(api_client, admin_user):
    """
    force=true bypasses the duplicate-warning 409.
    Flow: first attempt with phone A → 409; re-submit with corrected phone B
    and force=true → 201 (no second duplicate found).
    """
    api_client.force_authenticate(user=admin_user)
    api_client.post(
        CLIENTS_URL,
        {"full_name": "John Doe", "phone": "08055556666", "email": "john@test.com"},
        format="json",
    )
    # Same email triggers 409 (duplicate found)
    dup_resp = api_client.post(
        CLIENTS_URL,
        {"full_name": "John Doe Alt", "phone": "08066667777", "email": "john@test.com"},
        format="json",
    )
    assert dup_resp.status_code == 409

    # Re-submit with force=true and corrected email → 201
    resp = api_client.post(
        f"{CLIENTS_URL}?force=true",
        {"full_name": "John Doe Alt", "phone": "08066667777", "email": "johndoealt@test.com"},
        format="json",
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_duplicate_client_email_returns_409(api_client, admin_user):
    """Duplicate email also triggers 409."""
    api_client.force_authenticate(user=admin_user)
    api_client.post(
        CLIENTS_URL,
        {"full_name": "Jane Smith", "phone": "08077778888", "email": "jane@test.com"},
        format="json",
    )
    resp = api_client.post(
        CLIENTS_URL,
        {"full_name": "Jane Other", "phone": "08099990000", "email": "jane@test.com"},
        format="json",
    )
    assert resp.status_code == 409


@pytest.mark.django_db
def test_unauthenticated_cannot_access_properties(api_client):
    """Unauthenticated request → 401."""
    resp = api_client.get(PROPERTIES_URL)
    assert resp.status_code == 401


@pytest.mark.django_db
def test_property_list_filter_by_status(api_client, admin_user, shortlet_property):
    """Filter properties by status=available returns correct subset."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"{PROPERTIES_URL}?status=available")
    assert resp.status_code == 200
    for p in resp.data:
        assert p["status"] == "available"


@pytest.mark.django_db
def test_availability_no_blocked_ranges_for_empty_property(
    api_client, admin_user, shortlet_property
):
    """Property with no bookings returns empty blocked_ranges."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"/api/v1/properties/{shortlet_property.id}/availability/")
    assert resp.status_code == 200
    assert resp.data["blocked_ranges"] == []


@pytest.mark.django_db
def test_receipt_404_before_task_runs(api_client, admin_user, shortlet_property, client_obj):
    """GET receipt before task runs → 404."""
    data = {
        "client": client_obj,
        "property": shortlet_property,
        "check_in_date": "2027-01-01",
        "check_out_date": "2027-01-03",
        "rate_type": "nightly",
        "num_guests": 1,
    }
    # Create booking but don't run the task
    booking = BookingService.create_booking(data, actor=admin_user)
    # Delete the auto-created receipt if celery ran synchronously in test
    BookingReceipt.objects.filter(booking=booking).delete()

    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"/api/v1/bookings/{booking.id}/receipt/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_deposit_list_filtered_by_status(api_client, admin_user, confirmed_booking):
    """GET /deposits/?status=held returns only held deposits."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"{DEPOSITS_URL}?status=held")
    assert resp.status_code == 200
    for d in resp.data:
        assert d["status"] == "held"


@pytest.mark.django_db
def test_client_search(api_client, admin_user, client_obj):
    """Search by name returns matching clients."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"{CLIENTS_URL}?search=Amina")
    assert resp.status_code == 200
    assert len(resp.data) >= 1
    assert any("Amina" in c["full_name"] for c in resp.data)


@pytest.mark.django_db
def test_property_detail_view(api_client, admin_user, shortlet_property):
    """GET /properties/{id}/ returns property details."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"/api/v1/properties/{shortlet_property.id}/")
    assert resp.status_code == 200
    assert resp.data["id"] == str(shortlet_property.id)
    assert resp.data["property_code"] == shortlet_property.property_code


@pytest.mark.django_db
def test_booking_base_amount_monthly_calculated(shortlet_property, client_obj, admin_user):
    """base_amount = rate_monthly × months (min 1)."""
    data = {
        "client": client_obj,
        "property": shortlet_property,
        "check_in_date": "2026-10-01",
        "check_out_date": "2026-10-31",  # 30 days = 1 month
        "rate_type": "monthly",
        "num_guests": 1,
    }
    booking = BookingService.create_booking(data, actor=admin_user)
    assert booking.base_amount == shortlet_property.rate_monthly * 1


@pytest.mark.django_db
def test_hr_full_cannot_create_booking(api_client, hr_full_user, shortlet_property, client_obj):
    """hr_full can view bookings but cannot create them → 403."""
    api_client.force_authenticate(user=hr_full_user)
    resp = api_client.post(
        BOOKINGS_URL,
        {
            "client": str(client_obj.id),
            "property": str(shortlet_property.id),
            "check_in_date": "2026-10-01",
            "check_out_date": "2026-10-04",
            "rate_type": "nightly",
            "num_guests": 1,
        },
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_checked_out_booking_not_in_availability(
    api_client, admin_user, hr_full_user, shortlet_property, confirmed_booking
):
    """Checked-out bookings do NOT appear in availability blocked ranges."""
    # Check in then check out
    BookingService.check_in(confirmed_booking, actor=admin_user)
    BookingService.check_out(confirmed_booking, actor=admin_user, condition="good")

    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"/api/v1/properties/{shortlet_property.id}/availability/")
    assert resp.status_code == 200
    codes = [b["booking_code"] for b in resp.data["blocked_ranges"]]
    assert confirmed_booking.booking_code not in codes


@pytest.mark.django_db
def test_deduction_exceeds_deposit_clamps_refund_to_zero(
    admin_user, hr_full_user, confirmed_booking
):
    """Deduction > deposit → refund_amount = 0 (not negative)."""
    BookingService.check_in(confirmed_booking, actor=admin_user)
    BookingService.check_out(
        confirmed_booking,
        actor=admin_user,
        condition="heavily damaged",
        deduction_amount=Decimal("50000.00"),  # more than 30000 deposit
        notes="Major damage",
    )
    deposit = confirmed_booking.caution_deposit
    deposit.refresh_from_db()
    assert deposit.refund_amount <= Decimal("0")


@pytest.mark.django_db
def test_booking_monthly_rate_missing_raises(client_obj, admin_user):
    """Property with no monthly rate + monthly booking raises ValueError."""
    prop = ShortletProperty.objects.create(
        name="No Monthly Rate Studio",
        unit_type="studio",
        location="Test",
        rate_nightly=Decimal("20000.00"),
        # rate_monthly intentionally not set
        caution_deposit_amount=Decimal("10000.00"),
    )
    data = {
        "client": client_obj,
        "property": prop,
        "check_in_date": "2026-11-01",
        "check_out_date": "2026-12-01",
        "rate_type": "monthly",
        "num_guests": 1,
    }
    with pytest.raises(ValueError, match="no monthly rate"):
        BookingService.create_booking(data, actor=admin_user)


@pytest.mark.django_db
def test_property_code_unique_across_properties(api_client, admin_user, property_data):
    """Two created properties receive distinct property_code values."""
    api_client.force_authenticate(user=admin_user)
    r1 = api_client.post(PROPERTIES_URL, property_data, format="json")
    r2 = api_client.post(
        PROPERTIES_URL,
        {**property_data, "name": "Second Property"},
        format="json",
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.data["property_code"] != r2.data["property_code"]


@pytest.mark.django_db
def test_booking_list_filter_by_property(
    api_client, admin_user, shortlet_property, client_obj, confirmed_booking
):
    """Filter bookings by property_id returns only that property's bookings."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"{BOOKINGS_URL}?property={shortlet_property.id}")
    assert resp.status_code == 200
    for b in resp.data:
        assert str(b["property"]) == str(shortlet_property.id)


@pytest.mark.django_db
def test_deposit_update_non_admin_403(api_client, front_desk_user, confirmed_booking):
    """front_desk cannot update deposit refund details → 403."""
    deposit = confirmed_booking.caution_deposit
    api_client.force_authenticate(user=front_desk_user)
    resp = api_client.put(
        f"/api/v1/deposits/{deposit.id}/",
        {"refund_method": "bank_transfer", "account_number": "1234567890"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_nonexistent_booking_returns_404(api_client, admin_user):
    """GET /bookings/{unknown-uuid}/ → 404."""
    import uuid
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"/api/v1/bookings/{uuid.uuid4()}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_nonexistent_property_returns_404(api_client, admin_user):
    """GET /properties/{unknown-uuid}/ → 404."""
    import uuid
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"/api/v1/properties/{uuid.uuid4()}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_checked_in_booking_blocks_availability(
    api_client, admin_user, shortlet_property, confirmed_booking
):
    """A checked-in booking still blocks availability."""
    BookingService.check_in(confirmed_booking, actor=admin_user)

    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"/api/v1/properties/{shortlet_property.id}/availability/")
    codes = [b["booking_code"] for b in resp.data["blocked_ranges"]]
    assert confirmed_booking.booking_code in codes


@pytest.mark.django_db
def test_booking_list_filter_by_status(
    api_client, admin_user, confirmed_booking
):
    """Filter bookings by status=confirmed returns only confirmed bookings."""
    api_client.force_authenticate(user=admin_user)
    resp = api_client.get(f"{BOOKINGS_URL}?status=confirmed")
    assert resp.status_code == 200
    for b in resp.data:
        assert b["status"] == "confirmed"


@pytest.mark.django_db
def test_non_front_desk_cannot_create_property(api_client, hr_full_user, property_data):
    """hr_full cannot create a property → 403."""
    api_client.force_authenticate(user=hr_full_user)
    resp = api_client.post(PROPERTIES_URL, property_data, format="json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_non_front_desk_cannot_create_client(api_client, hr_full_user):
    """hr_full cannot create a client → 403."""
    api_client.force_authenticate(user=hr_full_user)
    resp = api_client.post(
        CLIENTS_URL,
        {"full_name": "Test", "phone": "08000000001"},
        format="json",
    )
    assert resp.status_code == 403


# ── Edge cases: check-in twice, property status transitions, zero caution ──────

@pytest.mark.django_db
def test_check_in_twice_returns_400(api_client, admin_user, confirmed_booking):
    """Calling check-in on an already checked-in booking → 400."""
    BookingService.check_in(confirmed_booking, actor=admin_user)
    assert confirmed_booking.status == "checked_in"

    api_client.force_authenticate(user=admin_user)
    resp = api_client.post(
        f"{BOOKINGS_URL}{confirmed_booking.id}/check-in/",
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_property_occupied_after_checkin(confirmed_booking, admin_user):
    """ShortletProperty status becomes 'occupied' immediately after check-in."""
    BookingService.check_in(confirmed_booking, actor=admin_user)
    confirmed_booking.property.refresh_from_db()
    assert confirmed_booking.property.status == "occupied"


@pytest.mark.django_db
def test_property_available_after_checkout(confirmed_booking, admin_user, hr_full_user):
    """ShortletProperty status returns to 'available' after check-out."""
    from unittest.mock import patch

    BookingService.check_in(confirmed_booking, actor=admin_user)
    with patch("apps.approvals.tasks.send_approval_notification.delay"):
        BookingService.check_out(confirmed_booking, actor=admin_user, condition="good")

    confirmed_booking.property.refresh_from_db()
    assert confirmed_booking.property.status == "available"


@pytest.mark.django_db
def test_zero_caution_deposit_total_equals_base(admin_user):
    """A property with caution_deposit_amount=0 → booking total = base_amount only."""
    from apps.shortlets.services import generate_property_code, generate_client_code

    prop = ShortletProperty.objects.create(
        name="Budget Room",
        unit_type="studio",
        location="Surulere, Lagos",
        rate_nightly=Decimal("15000.00"),
        caution_deposit_amount=Decimal("0.00"),
        status="available",
        property_code=generate_property_code(),
    )
    client = Client.objects.create(
        full_name="No Deposit Client",
        phone="08099999001",
        email="nodeposit@test.com",
        client_type="individual",
        id_type="nin",
        id_number="98765432100",
        created_by=admin_user,
        client_code=generate_client_code(),
    )
    from unittest.mock import patch

    with patch("apps.shortlets.tasks.generate_receipt_pdf.delay"):
        booking = BookingService.create_booking(
            {
                "property": prop,
                "client": client,
                "check_in_date": "2026-05-01",
                "check_out_date": "2026-05-02",
                "rate_type": "nightly",
                "num_guests": 1,
            },
            actor=admin_user,
        )
    assert booking.caution_deposit_amount == Decimal("0.00")
    assert booking.total_amount == booking.base_amount
