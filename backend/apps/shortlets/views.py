"""
Shortlets views — Phase 5.
"""

import csv
import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.shortlets.models import (
    Booking,
    BookingReceipt,
    CautionDeposit,
    Client,
    ShortletProperty,
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
    CautionDepositSerializer,
    CautionDepositUpdateSerializer,
    CheckOutSerializer,
    ClientCreateSerializer,
    ClientDetailSerializer,
    ClientListSerializer,
    ClientUpdateSerializer,
    PropertyCreateSerializer,
    PropertyDetailSerializer,
    PropertyListSerializer,
    PropertyUpdateSerializer,
)
from apps.shortlets.services import (
    BookingConflictError,
    BookingService,
    ClientService,
    DuplicateClientError,
    generate_property_code,
)

logger = logging.getLogger(__name__)


# ── ShortletProperty ────────────────────────────────────────────────────────────


class PropertyListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [CanManageProperty()]
        return [IsAuthenticated()]

    def get(self, request):
        qs = ShortletProperty.objects.all()
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
        prop = get_object_or_404(ShortletProperty, pk=pk)
        return Response(PropertyDetailSerializer(prop).data)

    def put(self, request, pk):
        prop = get_object_or_404(ShortletProperty, pk=pk)
        ser = PropertyUpdateSerializer(prop, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(PropertyDetailSerializer(prop).data)


class PropertyAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        prop = get_object_or_404(ShortletProperty, pk=pk)
        bookings = Booking.objects.filter(
            property=prop, status__in=["confirmed", "checked_in"]
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
        qs = Booking.objects.select_related("client", "property")
        status_filter = request.query_params.get("status")
        property_id = request.query_params.get("property")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        if status_filter:
            qs = qs.filter(status=status_filter)
        if property_id:
            qs = qs.filter(property_id=property_id)
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
