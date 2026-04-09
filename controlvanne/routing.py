"""
Routes WebSocket du module tireuse connectée (controlvanne).
/ WebSocket routes for the connected tap module (controlvanne).

LOCALISATION : controlvanne/routing.py

Deux routes :
- /ws/rfid/all/    → PanelConsumer, groupe rfid_state.all (toutes les tireuses)
- /ws/rfid/<uuid>/ → PanelConsumer, groupe rfid_state.<uuid> (une seule tireuse)
/ Two routes:
- /ws/rfid/all/    → PanelConsumer, group rfid_state.all (all taps)
- /ws/rfid/<uuid>/ → PanelConsumer, group rfid_state.<uuid> (a single tap)

Câblé dans TiBillet/asgi.py via URLRouter.
/ Wired in TiBillet/asgi.py via URLRouter.
"""

from django.urls import path

from controlvanne.consumers import PanelConsumer

websocket_urlpatterns = [
    # Route globale : toutes les tireuses (kiosk_list.html)
    # / Global route: all taps (kiosk_list.html)
    path("ws/rfid/all/", PanelConsumer.as_asgi()),
    # Route spécifique : une seule tireuse (kiosk_detail.html)
    # / Specific route: a single tap (kiosk_detail.html)
    path("ws/rfid/<str:slug>/", PanelConsumer.as_asgi()),
]
