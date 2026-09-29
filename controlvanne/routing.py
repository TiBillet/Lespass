"""
Routes WebSocket du module tireuse connectée (controlvanne).
/ WebSocket routes for the connected tap module (controlvanne).

LOCALISATION : controlvanne/routing.py

Deux routes (groupes nommés par lieu, voir controlvanne/groupes_ws.py) :
- /ws/rfid/all/    → PanelConsumer, groupe rfid_state.<uuid lieu>.all
                     (toutes les tireuses du lieu)
- /ws/rfid/<uuid>/ → PanelConsumer, groupe rfid_state.<uuid lieu>.<uuid>
                     (une seule tireuse du lieu)
Accès : session kiosk ou admin du lieu (controlvanne/acces.py), sinon refus.
/ Two routes (per-venue groups). Access: kiosk session or venue admin.

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
