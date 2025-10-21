from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import EventViewSet, PostalAddressViewSet

router = DefaultRouter()
# basename must be 'event' to align with ExternalApiKey.api_permissions()
router.register(r"events", EventViewSet, basename="event")
# Postal address endpoints (use basename 'postaladdress' to map to ExternalApiKey.api_permissions)
router.register(r"postal-addresses", PostalAddressViewSet, basename="postaladdress")

urlpatterns = [
    path("", include(router.urls)),
]
