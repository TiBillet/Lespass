"""
Routes WebSocket pour LaBoutik
/ WebSocket routes for LaBoutik

LOCALISATION : wsocket/routing.py

Une seule route : ws/laboutik/{pv_uuid}/
Le pv_uuid est l'UUID du PointDeVente (format UUID standard avec tirets).
"""
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        r"ws/laboutik/(?P<pv_uuid>[0-9a-f-]+)/$",
        consumers.LaboutikConsumer.as_asgi(),
    ),
]
