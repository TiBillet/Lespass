from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import EventViewSet, PostalAddressViewSet, SaleViewSet

router = DefaultRouter()
# basename must be 'event' to align with ExternalApiKey.api_permissions()
router.register(r"events", EventViewSet, basename="event")
# Postal address endpoints (use basename 'postaladdress' to map to ExternalApiKey.api_permissions)
router.register(r"postal-addresses", PostalAddressViewSet, basename="postaladdress")
# Route API des ventes (LigneArticle)
router.register(r'sales', SaleViewSet, basename='sale')
urlpatterns = [
    path("", include(router.urls)),
]
