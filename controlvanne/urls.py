"""
URLs du module tireuse connectée (controlvanne).
/ URLs for the connected tap module (controlvanne).

LOCALISATION : controlvanne/urls.py

Routes :
- /controlvanne/api/tireuse/ping/       → TireuseViewSet.ping
- /controlvanne/api/tireuse/authorize/  → TireuseViewSet.authorize
- /controlvanne/api/tireuse/event/      → TireuseViewSet.event
- /controlvanne/auth-kiosk/             → AuthKioskView (POST token → session cookie)
"""

from django.urls import path, include
from rest_framework import routers

from controlvanne.viewsets import TireuseViewSet, AuthKioskView, kiosk_view

router = routers.DefaultRouter()
router.register(r"api/tireuse", TireuseViewSet, basename="controlvanne-tireuse")

urlpatterns = [
    # Auth kiosk : POST token API → cookie session Django
    # / Auth kiosk: POST API token → Django session cookie
    path("auth-kiosk/", AuthKioskView.as_view(), name="controlvanne-auth-kiosk"),
    # Kiosk : page web temps réel pour l'écran du Pi
    # / Kiosk: real-time web page for the Pi screen
    path("kiosk/<uuid:uuid>/", kiosk_view, name="controlvanne-kiosk"),
    # ViewSet DRF : ping, authorize, event
    path("", include(router.urls)),
]
