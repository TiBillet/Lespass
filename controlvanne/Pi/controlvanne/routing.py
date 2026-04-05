from django.urls import path
from .consumers import PanelConsumer

# websocket_urlpatterns = [
#    path("ws/panel/", PanelConsumer.as_asgi()),
# ]
websocket_urlpatterns = [
    path("ws/rfid/ALL/", PanelConsumer.as_asgi(), {"group": "rfid_state.ALL"}),
    path("ws/rfid/<str:slug>/", PanelConsumer.as_asgi()),
]
