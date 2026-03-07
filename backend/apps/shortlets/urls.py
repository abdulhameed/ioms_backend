"""
Shortlets app URL patterns — Phase 5.
"""

from django.urls import path

from apps.shortlets.views import (
    BookingCheckInView,
    BookingCheckOutView,
    BookingDetailView,
    BookingListCreateView,
    BookingReceiptView,
    ClientDetailView,
    ClientExportView,
    ClientListCreateView,
    DepositDetailView,
    DepositListView,
    PropertyAvailabilityView,
    PropertyDetailView,
    PropertyListCreateView,
)

urlpatterns = [
    # Properties — export must come before <uuid:pk>
    path("clients/export/", ClientExportView.as_view(), name="client-export"),

    path("properties/", PropertyListCreateView.as_view(), name="property-list"),
    path("properties/<uuid:pk>/", PropertyDetailView.as_view(), name="property-detail"),
    path(
        "properties/<uuid:pk>/availability/",
        PropertyAvailabilityView.as_view(),
        name="property-availability",
    ),

    path("clients/", ClientListCreateView.as_view(), name="client-list"),
    path("clients/<uuid:pk>/", ClientDetailView.as_view(), name="client-detail"),

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

    path("deposits/", DepositListView.as_view(), name="deposit-list"),
    path("deposits/<uuid:pk>/", DepositDetailView.as_view(), name="deposit-detail"),
]
