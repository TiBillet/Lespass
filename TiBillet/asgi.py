import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

from wsocket.routing import websocket_urlpatterns
# from wsocket.middlewares import WebSocketJWTAuthMiddleware

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

django_asgi_app = get_asgi_application()
application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
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
