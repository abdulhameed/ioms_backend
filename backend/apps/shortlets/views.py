"""
Shortlets views — Milestone 2.
"""

import csv
import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.shortlets.models import (
    Booking,
    BookingReceipt,
    CautionDeposit,
    Client,
    NairaBnBBookingRequest,
    OfficeItem,
    ShortletApartment,
    YearlyRentalApartment,
)
from apps.shortlets.permissions import (
    CanExportClients,
    CanManageBooking,
    CanManageClient,
    CanManageDeposit,
    CanManageProperty,
    CanViewBooking,
    CanViewDeposit,
)
from apps.shortlets.serializers import (
    BookingCreateSerializer,
    BookingDetailSerializer,
    BookingListSerializer,
    BookingRequestDeclineSerializer,
    CautionDepositDisputeSerializer,
    CautionDepositSerializer,
    CautionDepositUpdateSerializer,
    CheckOutSerializer,
    ClientCreateSerializer,
    ClientDetailSerializer,
    ClientListSerializer,
    ClientUpdateSerializer,
    CompleteCheckoutSerializer,
    InventoryItemSerializer,
    InventoryVerificationSerializer,
    NairaBnBBookingRequestSerializer,
    OfficeItemCreateSerializer,
    OfficeItemSerializer,
    PropertyCreateSerializer,
    PropertyDetailSerializer,
    PropertyListSerializer,
    PropertyUpdateSerializer,
    YearlyRentalApartmentSerializer,
    YearlyRentalCreateSerializer,
)
from apps.shortlets.services import (
    BookingConflictError,
    BookingService,
    ClientService,
    DuplicateClientError,
    accept_booking_request,
    complete_checkout,
    generate_checkout_pdf,
    generate_office_item_code,
    generate_property_code,
    generate_yearly_rental_code,
    validate_nairabNb_signature,
)

logger = logging.getLogger(__name__)


# ── ShortletApartment ───────────────────────────────────────────────────────────


class PropertyListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [CanManageProperty()]
        return [IsAuthenticated()]

    def get(self, request):
        qs = ShortletApartment.objects.all()
        unit_type = request.query_params.get("unit_type")
        status_filter = request.query_params.get("status")
        price_min = request.query_params.get("price_min")
        price_max = request.query_params.get("price_max")

        if unit_type:
            qs = qs.filter(unit_type=unit_type)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if price_min:
            qs = qs.filter(rate_nightly__gte=price_min)
        if price_max:
            qs = qs.filter(rate_nightly__lte=price_max)

        return Response(PropertyListSerializer(qs, many=True).data)

    def post(self, request):
        ser = PropertyCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        prop = ser.save()
        prop.property_code = generate_property_code()
        prop.save(update_fields=["property_code"])
        return Response(
            PropertyDetailSerializer(prop).data, status=status.HTTP_201_CREATED
        )


class PropertyDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "PUT":
            return [CanManageProperty()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        prop = get_object_or_404(ShortletApartment, pk=pk)
        return Response(PropertyDetailSerializer(prop).data)

    def put(self, request, pk):
        prop = get_object_or_404(ShortletApartment, pk=pk)
        ser = PropertyUpdateSerializer(prop, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(PropertyDetailSerializer(prop).data)


class PropertyAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        prop = get_object_or_404(ShortletApartment, pk=pk)
        bookings = Booking.objects.filter(
            apartment=prop, status__in=["confirmed", "checked_in"]
        ).values("check_in_date", "check_out_date", "booking_code")
        blocked = [
            {
                "check_in": b["check_in_date"],
                "check_out": b["check_out_date"],
                "booking_code": b["booking_code"],
            }
            for b in bookings
        ]
        return Response({"property_id": str(pk), "blocked_ranges": blocked})


class PropertyCalendarView(APIView):
    """Return blocked date ranges for confirmed/checked-in bookings (calendar view)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        prop = get_object_or_404(ShortletApartment, pk=pk)
        bookings = Booking.objects.filter(
            apartment=prop, status__in=["confirmed", "checked_in"]
        ).values("check_in_date", "check_out_date", "booking_code", "status")
        blocked = [
            {
                "check_in": b["check_in_date"],
                "check_out": b["check_out_date"],
                "booking_code": b["booking_code"],
                "status": b["status"],
            }
            for b in bookings
        ]
        return Response({"apartment_id": str(pk), "blocked_ranges": blocked})


# ── YearlyRentalApartment ───────────────────────────────────────────────────────


class YearlyRentalListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [CanManageProperty()]
        return [IsAuthenticated()]

    def get(self, request):
        qs = YearlyRentalApartment.objects.all()
        lease_status = request.query_params.get("lease_status")
        if lease_status:
            qs = qs.filter(lease_status=lease_status)
        return Response(YearlyRentalApartmentSerializer(qs, many=True).data)

    def post(self, request):
        ser = YearlyRentalCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        yr = ser.save()
        yr.property_code = generate_yearly_rental_code()
        yr.save(update_fields=["property_code"])
        return Response(
            YearlyRentalApartmentSerializer(yr).data, status=status.HTTP_201_CREATED
        )


class YearlyRentalDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "PUT":
            return [CanManageProperty()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        yr = get_object_or_404(YearlyRentalApartment, pk=pk)
        return Response(YearlyRentalApartmentSerializer(yr).data)

    def put(self, request, pk):
        yr = get_object_or_404(YearlyRentalApartment, pk=pk)
        ser = YearlyRentalCreateSerializer(yr, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(YearlyRentalApartmentSerializer(yr).data)


# ── OfficeItem ──────────────────────────────────────────────────────────────────


class OfficeItemListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [CanManageProperty()]
        return [IsAuthenticated()]

    def get(self, request):
        qs = OfficeItem.objects.all()
        category = request.query_params.get("category")
        condition = request.query_params.get("condition")
        if category:
            qs = qs.filter(item_category=category)
        if condition:
            qs = qs.filter(condition=condition)
        return Response(OfficeItemSerializer(qs, many=True).data)

    def post(self, request):
        ser = OfficeItemCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        item = ser.save()
        item.item_code = generate_office_item_code()
        item.save(update_fields=["item_code"])
        return Response(OfficeItemSerializer(item).data, status=status.HTTP_201_CREATED)


class OfficeItemDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "PUT":
            return [CanManageProperty()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        item = get_object_or_404(OfficeItem, pk=pk)
        return Response(OfficeItemSerializer(item).data)

    def put(self, request, pk):
        item = get_object_or_404(OfficeItem, pk=pk)
        ser = OfficeItemCreateSerializer(item, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(OfficeItemSerializer(item).data)


# ── Client ─────────────────────────────────────────────────────────────────────


class ClientListCreateView(APIView):
    permission_classes = [CanManageClient]

    def get(self, request):
        qs = Client.objects.all()
        search = request.query_params.get("search")
        if search:
            from django.db.models import Q

            qs = qs.filter(
                Q(full_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
            )
        return Response(ClientListSerializer(qs, many=True).data)

    def post(self, request):
        force = request.query_params.get("force", "").lower() == "true"
        ser = ClientCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            client = ClientService.create_client(
                ser.validated_data, actor=request.user, force=force
            )
        except DuplicateClientError as exc:
            return Response(
                {
                    "error": "duplicate_client",
                    "message": "A client with this email or phone already exists.",
                    "existing_id": str(exc.existing_client.id),
                    "existing_code": exc.existing_client.client_code,
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            ClientDetailSerializer(client).data, status=status.HTTP_201_CREATED
        )


class ClientDetailView(APIView):
    permission_classes = [CanManageClient]

    def get(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        return Response(ClientDetailSerializer(client).data)

    def put(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        ser = ClientUpdateSerializer(client, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ClientDetailSerializer(client).data)


class ClientExportView(APIView):
    permission_classes = [CanExportClients]

    def get(self, request):
        clients = Client.objects.all().order_by("full_name")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="clients.csv"'
        writer = csv.writer(response)
        # id_number intentionally excluded (privacy)
        writer.writerow(
            [
                "client_code",
                "full_name",
                "email",
                "phone",
                "id_type",
                "client_type",
                "is_vip",
                "created_at",
            ]
        )
        for c in clients:
            writer.writerow(
                [
                    c.client_code,
                    c.full_name,
                    c.email or "",
                    c.phone,
                    c.id_type,
                    c.client_type,
                    c.is_vip,
                    c.created_at.strftime("%Y-%m-%d"),
                ]
            )
        return response


# ── Booking ────────────────────────────────────────────────────────────────────


class BookingListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [CanManageBooking()]
        return [CanViewBooking()]

    def get(self, request):
        qs = Booking.objects.select_related("client", "apartment", "yearly_rental")
        status_filter = request.query_params.get("status")
        apartment_id = request.query_params.get("apartment")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        if status_filter:
            qs = qs.filter(status=status_filter)
        if apartment_id:
            qs = qs.filter(apartment_id=apartment_id)
        if date_from:
            qs = qs.filter(check_in_date__gte=date_from)
        if date_to:
            qs = qs.filter(check_out_date__lte=date_to)

        return Response(BookingListSerializer(qs, many=True).data)

    def post(self, request):
        ser = BookingCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            booking = BookingService.create_booking(ser.validated_data, actor=request.user)
        except BookingConflictError as exc:
            return Response(
                {"error": "property_unavailable", "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            BookingDetailSerializer(booking).data, status=status.HTTP_201_CREATED
        )


class BookingDetailView(APIView):
    def get_permissions(self):
        return [CanViewBooking()]

    def get(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        return Response(BookingDetailSerializer(booking).data)


class BookingCheckInView(APIView):
    permission_classes = [CanManageBooking]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        try:
            BookingService.check_in(booking, actor=request.user)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingDetailSerializer(booking).data)


class BookingCheckOutView(APIView):
    permission_classes = [CanManageBooking]

    def post(self, request, pk):
        booking = get_object_or_404(Booking.objects.select_related("caution_deposit"), pk=pk)
        ser = CheckOutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            BookingService.check_out(
                booking,
                actor=request.user,
                condition=ser.validated_data.get("condition", ""),
                deduction_amount=ser.validated_data.get("deduction_amount", 0),
                notes=ser.validated_data.get("notes", ""),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BookingDetailSerializer(booking).data)


class BookingReceiptView(APIView):
    permission_classes = [CanManageBooking]

    def get(self, request, pk):
        import base64

        booking = get_object_or_404(Booking, pk=pk)
        receipt = get_object_or_404(BookingReceipt, booking=booking)

        if not receipt.pdf_file:
            return Response(
                {"error": "receipt_not_ready", "message": "Receipt PDF not yet generated."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            pdf_bytes = base64.b64decode(receipt.pdf_file)
        except Exception:
            pdf_bytes = receipt.pdf_file.encode()

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="receipt-{receipt.receipt_number}.pdf"'
        )
        return response


class BookingInventoryChecklistView(APIView):
    """GET — return inventory items for the booking's apartment."""

    permission_classes = [CanManageBooking]

    def get(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        if booking.apartment_id:
            items = booking.apartment.inventory_items.all()
        elif booking.yearly_rental_id:
            items = booking.yearly_rental.inventory_items.all()
        else:
            items = []
        return Response({"items": InventoryItemSerializer(items, many=True).data})


class BookingCompleteCheckoutView(APIView):
    """POST — create InventoryVerification; flag damaged/missing items → MaintenanceRequest."""

    permission_classes = [CanManageBooking]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        ser = CompleteCheckoutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            verification = complete_checkout(booking, ser.validated_data, request.user)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            InventoryVerificationSerializer(verification).data,
            status=status.HTTP_201_CREATED,
        )


class BookingCheckoutReportView(APIView):
    """GET — return checkout PDF report."""

    permission_classes = [CanManageBooking]

    def get(self, request, pk):
        booking = get_object_or_404(
            Booking.objects.prefetch_related(
                "inventory_verifications__items__inventory_item"
            ),
            pk=pk,
        )
        pdf_bytes = generate_checkout_pdf(booking)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="checkout-{booking.booking_code or str(booking.id)}.pdf"'
        )
        return response


# ── CautionDeposit ─────────────────────────────────────────────────────────────


class DepositListView(APIView):
    permission_classes = [CanViewDeposit]

    def get(self, request):
        qs = CautionDeposit.objects.select_related("booking__client")
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(CautionDepositSerializer(qs, many=True).data)


class DepositDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "PUT":
            return [CanManageDeposit()]
        return [CanViewDeposit()]

    def get(self, request, pk):
        deposit = get_object_or_404(CautionDeposit, pk=pk)
        return Response(CautionDepositSerializer(deposit).data)

    def put(self, request, pk):
        deposit = get_object_or_404(CautionDeposit, pk=pk)
        ser = CautionDepositUpdateSerializer(deposit, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(CautionDepositSerializer(deposit).data)


class DepositDisputeView(APIView):
    """POST — flag a deposit as disputed with a reason."""

    permission_classes = [CanManageBooking]

    def post(self, request, pk):
        deposit = get_object_or_404(CautionDeposit, pk=pk)
        ser = CautionDepositDisputeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        deposit.status = "disputed"
        deposit.dispute_reason = ser.validated_data["dispute_reason"]
        deposit.save(update_fields=["status", "dispute_reason", "updated_at"])
        return Response(CautionDepositSerializer(deposit).data)


# ── NairaBnB Webhook ───────────────────────────────────────────────────────────


class NairaBnBWebhookView(APIView):
    """
    POST — receive inbound booking requests from NairaBnB channel.
    Validates HMAC-SHA256 signature; creates NairaBnBBookingRequest on success.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        if not validate_nairabNb_signature(request):
            return Response(
                {"error": "invalid_signature"},
                status=status.HTTP_403_FORBIDDEN,
            )

        ser = NairaBnBBookingRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        booking_request = ser.save()
        return Response(
            NairaBnBBookingRequestSerializer(booking_request).data,
            status=status.HTTP_201_CREATED,
        )


# ── BookingRequest ─────────────────────────────────────────────────────────────


class BookingRequestListView(APIView):
    permission_classes = [CanManageBooking]

    def get(self, request):
        qs = NairaBnBBookingRequest.objects.select_related("apartment")
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(NairaBnBBookingRequestSerializer(qs, many=True).data)


class BookingRequestAcceptView(APIView):
    permission_classes = [CanManageBooking]

    def post(self, request, pk):
        booking_request = get_object_or_404(NairaBnBBookingRequest, pk=pk)
        try:
            booking = accept_booking_request(booking_request.id, accepted_by=request.user)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingDetailSerializer(booking).data, status=status.HTTP_201_CREATED)


class BookingRequestDeclineView(APIView):
    permission_classes = [CanManageBooking]

    def post(self, request, pk):
        booking_request = get_object_or_404(NairaBnBBookingRequest, pk=pk)
        if booking_request.status != "pending_review":
            return Response(
                {"error": f"Cannot decline a request with status '{booking_request.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = BookingRequestDeclineSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        booking_request.status = "declined"
        booking_request.declined_reason = ser.validated_data.get("declined_reason", "")
        booking_request.save(update_fields=["status", "declined_reason", "updated_at"])
        return Response(NairaBnBBookingRequestSerializer(booking_request).data)
