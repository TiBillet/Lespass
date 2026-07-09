"""
URLs de l'app booking — réservation de ressources partagées.
/ booking app URLs — shared resource reservation.

LOCALISATION : booking/urls.py

L'URL de base est 'booking/' (définie dans TiBillet/urls_tenants.py).
/ Base URL is 'booking/' (defined in TiBillet/urls_tenants.py).
"""
from django.urls import path
from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import BookingViewSet

router = DefaultRouter()
router.register(r"", BookingViewSet, basename="booking") # Booking add from


urlpatterns = [

              ] + router.urls
