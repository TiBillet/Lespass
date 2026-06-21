# WebSocket routes : chat (V1) + laboutik/printer (POS V2, portage S6)
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<room_name>\\w+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r"ws/laboutik/(?P<pv_uuid>[0-9a-f-]+)/$", consumers.LaboutikConsumer.as_asgi()),
    re_path(r"ws/printer/(?P<printer_uuid>[0-9a-f-]+)/$", consumers.PrinterConsumer.as_asgi()),
]
