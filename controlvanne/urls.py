"""
URLs du module tireuse connectée (controlvanne).
/ URLs for the connected tap module (controlvanne).

LOCALISATION : controlvanne/urls.py

Routes API (Raspberry Pi) :
- /controlvanne/api/tireuse/ping/       → TireuseViewSet.ping
- /controlvanne/api/tireuse/authorize/  → TireuseViewSet.authorize
- /controlvanne/api/tireuse/event/      → TireuseViewSet.event

Route auth kiosk :
- /controlvanne/auth-kiosk/             → AuthKioskView (POST token → session cookie)

Routes kiosk (écrans Pi) :
- /controlvanne/kiosk/                  → KioskViewSet.list (toutes les tireuses)
- /controlvanne/kiosk/<uuid>/           → KioskViewSet.retrieve (une seule tireuse)
"""

from django.urls import path, include
from rest_framework import routers

from controlvanne.viewsets import TireuseViewSet, AuthKioskView, KioskViewSet

router = routers.DefaultRouter()
router.register(r"api/tireuse", TireuseViewSet, basename="controlvanne-tireuse")

urlpatterns = [
    # Auth kiosk : POST token API → cookie session Django
    # / Auth kiosk: POST API token → Django session cookie
    path("auth-kiosk/", AuthKioskView.as_view(), name="controlvanne-auth-kiosk"),
    # Kiosk : grille de toutes les tireuses actives
    # / Kiosk: grid of all active taps
    path(
        "kiosk/",
        KioskViewSet.as_view({"get": "list"}),
        name="controlvanne-kiosk-list",
    ),
    # Kiosk : écran dédié à une seule tireuse
    # / Kiosk: screen dedicated to a single tap
    path(
        "kiosk/<uuid:pk>/",
        KioskViewSet.as_view({"get": "retrieve"}),
        name="controlvanne-kiosk-detail",
    ),
    # ViewSet DRF : ping, authorize, event
    # / DRF ViewSet: ping, authorize, event
    path("", include(router.urls)),
]
