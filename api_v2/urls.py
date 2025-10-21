from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import EventViewSet

router = DefaultRouter()
# basename must be 'event' to align with ExternalApiKey.api_permissions()
router.register(r"events", EventViewSet, basename="event")

urlpatterns = [
    path("", include(router.urls)),
]
