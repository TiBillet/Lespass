import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

import wsocket.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

application = ProtocolTypeRouter({

    "http": get_asgi_application(),

    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                wsocket.routing.websocket_urlpatterns
            )
        ),
    ),
})
