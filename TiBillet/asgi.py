"""
Configuration ASGI — HTTP + WebSocket
/ ASGI configuration — HTTP + WebSocket

LOCALISATION : TiBillet/asgi.py

FLUX des connexions WebSocket :
1. AllowedHostsOriginValidator — verifie que l'origine est autorisee
2. WebSocketTenantMiddleware — resout le tenant depuis le hostname, set connection.tenant
3. AuthMiddlewareStack — resout la session Django (scope["user"])
4. URLRouter — route vers le consumer (wsocket/routing.py + controlvanne/routing.py)

FLUX des connexions HTTP :
1. django_asgi_app — traite par le middleware WSGI classique (TenantMainMiddleware inclus)

IMPORTANT : os.environ.setdefault + get_asgi_application() AVANT tout import applicatif.
Les imports wsocket/controlvanne chargent des modèles Django — si le registre d'apps
n'est pas encore initialisé au moment de l'import, Django lève AppRegistryNotReady.
Ce bug se manifeste uniquement avec Daphne/Uvicorn (ASGI), pas avec runserver (WSGI).
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TiBillet.settings")
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from controlvanne.routing import websocket_urlpatterns as controlvanne_ws_urlpatterns  # noqa: E402
from wsocket.middlewares import WebSocketTenantMiddleware  # noqa: E402
from wsocket.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            WebSocketTenantMiddleware(
                AuthMiddlewareStack(URLRouter(websocket_urlpatterns + controlvanne_ws_urlpatterns))
            )
        ),
    }
)
