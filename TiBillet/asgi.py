import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TiBillet.settings")

# IMPORTANT : get_asgi_application() DOIT être appelé AVANT les imports
# applicatifs (wsocket, controlvanne) — il initialise le registre d'apps
# Django. Sous runserver le bug est invisible (Django déjà initialisé),
# mais un serveur ASGI standalone (daphne TiBillet.asgi:application, cf.
# supervisor/conf.d/daphne.conf) crashe en AppRegistryNotReady sinon.
# / IMPORTANT: get_asgi_application() MUST be called BEFORE app imports
# (wsocket, controlvanne) — it initializes the Django app registry.
# Invisible under runserver, but a standalone ASGI server (daphne)
# crashes with AppRegistryNotReady otherwise.
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

from wsocket.middlewares import WebSocketTenantMiddleware
from wsocket.routing import websocket_urlpatterns
from controlvanne.routing import websocket_urlpatterns as controlvanne_ws_urlpatterns

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            WebSocketTenantMiddleware(
                AuthMiddlewareStack(
                    URLRouter(websocket_urlpatterns + controlvanne_ws_urlpatterns)
                )
            )
        ),
    }
)

# EX TiBillet Test
# application = ProtocolTypeRouter({
#
#     "http": get_asgi_application(),
#
#     "websocket": AllowedHostsOriginValidator(
#         WebSocketJWTAuthMiddleware(
#             URLRouter(
#                 wsocket.routing.websocket_urlpatterns
#             )
#         ),
#     ),
# })
