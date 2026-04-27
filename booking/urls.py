"""
URLs de l'app booking — réservation de ressources partagées.
/ booking app URLs — shared resource reservation.

LOCALISATION : booking/urls.py

L'URL de base est 'booking/' (définie dans TiBillet/urls_tenants.py).
/ Base URL is 'booking/' (defined in TiBillet/urls_tenants.py).
"""
from django.urls import path

from .views import BookingViewSet

list_view            = BookingViewSet.as_view({'get': 'list'})
resource_view        = BookingViewSet.as_view({'get': 'resource_page'})
book_view            = BookingViewSet.as_view({'get': 'book', 'post': 'book'})
slot_unavailable_view = BookingViewSet.as_view({'get': 'slot_unavailable'})
my_bookings_view     = BookingViewSet.as_view({'get': 'my_bookings'})
cancel_view          = BookingViewSet.as_view({'get': 'cancel_confirm', 'post': 'cancel_confirm'})

urlpatterns = [
    path('',                           list_view,             name='booking-list'),
    path('resource/<int:pk>/',         resource_view,         name='booking-resource'),
    path('<int:pk>/book/',             book_view,             name='booking-book'),
    path('<int:pk>/slot-unavailable/', slot_unavailable_view, name='booking-slot-unavailable'),
    path('my-bookings/',               my_bookings_view,      name='booking-my-bookings'),
    path('cancel/<int:booking_pk>/',   cancel_view,           name='booking-cancel'),
]
