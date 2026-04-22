"""
URLs du module tireuse connectee (controlvanne).
/ URLs for the connected tap module (controlvanne).

LOCALISATION : controlvanne/urls.py

Routes API (Raspberry Pi) :
- /controlvanne/api/tireuse/ping/       → TireuseViewSet.ping
- /controlvanne/api/tireuse/authorize/  → TireuseViewSet.authorize
- /controlvanne/api/tireuse/event/      → TireuseViewSet.event

Route auth kiosk :
- /controlvanne/auth-kiosk/             → AuthKioskView

Routes kiosk (ecrans Pi) :
- /controlvanne/kiosk/                  → KioskViewSet.list
- /controlvanne/kiosk/<uuid>/           → KioskViewSet.retrieve

Routes calibration (admin staff) :
- /controlvanne/calibration/<uuid>/              → calibration_page
- /controlvanne/calibration/<uuid>/sessions/     → calibration_sessions_partial (polling HTMX)
- /controlvanne/calibration/<uuid>/serie/        → calibration_serie (POST : soumettre toute la serie)
"""

from django.urls import path, include
from rest_framework import routers

from controlvanne.viewsets import TireuseViewSet, AuthKioskView, KioskViewSet, KioskTokenView
from controlvanne.calibration_views import (
    calibration_page,
    calibration_sessions_partial,
    calibration_serie,
)

router = routers.DefaultRouter()
router.register(r"api/tireuse", TireuseViewSet, basename="controlvanne-tireuse")

urlpatterns = [
    # Auth kiosk
    path("auth-kiosk/", AuthKioskView.as_view(), name="controlvanne-auth-kiosk"),
    path("kiosk-token/<str:token>/", KioskTokenView.as_view(), name="controlvanne-kiosk-token"),

    # Kiosk
    path("kiosk/", KioskViewSet.as_view({"get": "list"}), name="controlvanne-kiosk-list"),
    path("kiosk/<uuid:pk>/", KioskViewSet.as_view({"get": "retrieve"}), name="controlvanne-kiosk-detail"),

    # Calibration debitmetre (staff uniquement)
    path("calibration/<uuid:uuid>/", calibration_page, name="calibration_page"),
    path("calibration/<uuid:uuid>/sessions/", calibration_sessions_partial, name="calibration_sessions_partial"),
    path("calibration/<uuid:uuid>/serie/", calibration_serie, name="calibration_serie"),

    # ViewSet DRF : ping, authorize, event
    path("", include(router.urls)),
]
