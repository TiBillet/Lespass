# Routes WebSocket : caisse LaBoutik, imprimantes, TPE kiosque.
# / WebSocket routes: LaBoutik POS, printers, kiosk card terminal.
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/laboutik/(?P<pv_uuid>[0-9a-f-]+)/$", consumers.LaboutikConsumer.as_asgi()),
    re_path(r"ws/printer/(?P<printer_uuid>[0-9a-f-]+)/$", consumers.PrinterConsumer.as_asgi()),
    re_path(r"ws/terminal/(?P<room_name>[\w-]+)/$", consumers.TerminalConsumer.as_asgi()),
]
