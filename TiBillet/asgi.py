"""
Configuration ASGI — HTTP + WebSocket
/ ASGI configuration — HTTP + WebSocket

LOCALISATION : TiBillet/asgi.py

FLUX des connexions WebSocket :
1. AllowedHostsOriginValidator — verifie que l'origine est autorisee
2. WebSocketTenantMiddleware — resout le tenant depuis le hostname, set connection.tenant
3. AuthMiddlewareStack — resout la session Django (scope["user"])
4. URLRouter — route vers le consumer (wsocket/routing.py)

FLUX des connexions HTTP :
1. django_asgi_app — traite par le middleware WSGI classique (TenantMainMiddleware inclus)
"""
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

from wsocket.middlewares import WebSocketTenantMiddleware
from wsocket.routing import websocket_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TiBillet.settings")

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            WebSocketTenantMiddleware(
                AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
            )
        ),
    }
)
