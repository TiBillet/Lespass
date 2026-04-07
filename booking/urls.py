"""
URLs de l'app booking — réservation de ressources partagées
/ booking app URLs — shared resource reservation

LOCALISATION : booking/urls.py

Enregistre le BookingViewSet sur le router DRF.
L'URL de base est 'booking/' (définie dans TiBillet/urls_tenants.py).
/ Registers BookingViewSet on the DRF router.
Base URL is 'booking/' (defined in TiBillet/urls_tenants.py).
"""
from rest_framework.routers import DefaultRouter

from .views import BookingViewSet

router = DefaultRouter()
router.register(r'', BookingViewSet, basename='booking')

urlpatterns = router.urls
