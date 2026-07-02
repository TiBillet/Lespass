import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

from wsocket.middlewares import WebSocketTenantMiddleware
from wsocket.routing import websocket_urlpatterns
# from controlvanne.routing import websocket_urlpatterns as controlvanne_ws_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TiBillet.settings")

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            WebSocketTenantMiddleware(
                AuthMiddlewareStack(
                    # URLRouter(websocket_urlpatterns + controlvanne_ws_urlpatterns)
                    URLRouter(websocket_urlpatterns)
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
