"""
Shortlets app URL patterns — Milestone 2.
"""

from django.urls import path

from apps.shortlets.views import (
    BookingCheckInView,
    BookingCheckOutView,
    BookingCheckoutReportView,
    BookingCompleteCheckoutView,
    BookingDetailView,
    BookingInventoryChecklistView,
    BookingListCreateView,
    BookingReceiptView,
    BookingRequestAcceptView,
    BookingRequestDeclineView,
    BookingRequestListView,
    ClientDetailView,
    ClientExportView,
    ClientListCreateView,
    DepositDetailView,
    DepositDisputeView,
    DepositListView,
    NairaBnBWebhookView,
    OfficeItemDetailView,
    OfficeItemListCreateView,
    PropertyAvailabilityView,
    PropertyCalendarView,
    PropertyDetailView,
    PropertyListCreateView,
    YearlyRentalDetailView,
    YearlyRentalListCreateView,
)

urlpatterns = [
    # ── NairaBnB Webhook ───────────────────────────────────────────────────────
    path("webhooks/nairabNb/", NairaBnBWebhookView.as_view(), name="nairabNb-webhook"),

    # ── Booking Requests ───────────────────────────────────────────────────────
    path("booking-requests/", BookingRequestListView.as_view(), name="booking-request-list"),
    path(
        "booking-requests/<uuid:pk>/accept/",
        BookingRequestAcceptView.as_view(),
        name="booking-request-accept",
    ),
    path(
        "booking-requests/<uuid:pk>/decline/",
        BookingRequestDeclineView.as_view(),
        name="booking-request-decline",
    ),

    # ── Assets: Shortlet Apartments ───────────────────────────────────────────
    # /api/v1/assets/shortlets/ — new canonical URL
    path("assets/shortlets/", PropertyListCreateView.as_view(), name="apartment-list"),
    path(
        "assets/shortlets/<uuid:pk>/",
        PropertyDetailView.as_view(),
        name="apartment-detail",
    ),
    path(
        "assets/shortlets/<uuid:pk>/calendar/",
        PropertyCalendarView.as_view(),
        name="apartment-calendar",
    ),
    # /api/v1/properties/ — kept for backward compatibility
    path("properties/", PropertyListCreateView.as_view(), name="property-list"),
    path("properties/<uuid:pk>/", PropertyDetailView.as_view(), name="property-detail"),
    path(
        "properties/<uuid:pk>/availability/",
        PropertyAvailabilityView.as_view(),
        name="property-availability",
    ),

    # ── Assets: Yearly Rentals ────────────────────────────────────────────────
    path("assets/yearly-rentals/", YearlyRentalListCreateView.as_view(), name="yearly-rental-list"),
    path(
        "assets/yearly-rentals/<uuid:pk>/",
        YearlyRentalDetailView.as_view(),
        name="yearly-rental-detail",
    ),

    # ── Assets: Office Items ──────────────────────────────────────────────────
    path("assets/offices/", OfficeItemListCreateView.as_view(), name="office-item-list"),
    path(
        "assets/offices/<uuid:pk>/",
        OfficeItemDetailView.as_view(),
        name="office-item-detail",
    ),

    # ── Clients ───────────────────────────────────────────────────────────────
    path("clients/export/", ClientExportView.as_view(), name="client-export"),
    path("clients/", ClientListCreateView.as_view(), name="client-list"),
    path("clients/<uuid:pk>/", ClientDetailView.as_view(), name="client-detail"),

    # ── Bookings ──────────────────────────────────────────────────────────────
    path("bookings/", BookingListCreateView.as_view(), name="booking-list"),
    path("bookings/<uuid:pk>/", BookingDetailView.as_view(), name="booking-detail"),
    path(
        "bookings/<uuid:pk>/check-in/",
        BookingCheckInView.as_view(),
        name="booking-check-in",
    ),
    path(
        "bookings/<uuid:pk>/check-out/",
        BookingCheckOutView.as_view(),
        name="booking-check-out",
    ),
    path(
        "bookings/<uuid:pk>/receipt/",
        BookingReceiptView.as_view(),
        name="booking-receipt",
    ),
    path(
        "bookings/<uuid:pk>/inventory-checklist/",
        BookingInventoryChecklistView.as_view(),
        name="booking-inventory-checklist",
    ),
    path(
        "bookings/<uuid:pk>/complete-checkout/",
        BookingCompleteCheckoutView.as_view(),
        name="booking-complete-checkout",
    ),
    path(
        "bookings/<uuid:pk>/checkout-report/pdf/",
        BookingCheckoutReportView.as_view(),
        name="booking-checkout-report",
    ),

    # ── Deposits ──────────────────────────────────────────────────────────────
    path("deposits/", DepositListView.as_view(), name="deposit-list"),
    path("deposits/<uuid:pk>/", DepositDetailView.as_view(), name="deposit-detail"),
    path("deposits/<uuid:pk>/dispute/", DepositDisputeView.as_view(), name="deposit-dispute"),
]
