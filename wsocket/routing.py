"""
Routes WebSocket pour LaBoutik
/ WebSocket routes for LaBoutik

LOCALISATION : wsocket/routing.py

Deux routes :
- ws/laboutik/{pv_uuid}/ — interface caisse (navigateur HTMX)
- ws/printer/{printer_uuid}/ — imprimante Sunmi Inner (app Android)
"""
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        r"ws/laboutik/(?P<pv_uuid>[0-9a-f-]+)/$",
        consumers.LaboutikConsumer.as_asgi(),
    ),
    re_path(
        r"ws/printer/(?P<printer_uuid>[0-9a-f-]+)/$",
        consumers.PrinterConsumer.as_asgi(),
    ),
]
