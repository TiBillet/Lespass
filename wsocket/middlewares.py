from channels.db import database_sync_to_async
from django.db import connection
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken, TokenError

User = get_user_model()

import logging

logger = logging.getLogger(__name__)

@database_sync_to_async
def get_user(user_id):
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

@database_sync_to_async
def _get_tenant_from_hostname(hostname):
    """
    Cherche le tenant (Client) à partir du hostname de la requête WebSocket.
    Reproduit la logique de TenantMainMiddleware.get_tenant().
    """
    from Customers.models import Domain

    # Se placer sur le schema public pour lire les metadonnees tenant
    connection.set_schema_to_public()

    try:
        domain = Domain.objects.select_related("tenant").get(domain=hostname)
        return domain.tenant
    except Domain.DoesNotExist:
        return None

class WebSocketTenantMiddleware:
    """
    Middleware ASGI qui résout le tenant depuis le hostname de la connexion WebSocket
    et configure connection.tenant + connection.schema_name.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        headers = dict(scope.get("headers", []))
        host_header = headers.get(b"host", b"").decode("utf-8")

        # Retirer le port et le www
        hostname = host_header.split(":")[0]
        if hostname.startswith("www."):
            hostname = hostname[4:]

        tenant = await _get_tenant_from_hostname(hostname)

        if tenant is not None:
            scope["tenant"] = tenant
            await database_sync_to_async(connection.set_tenant)(tenant)
            logger.debug(f"[WS Tenant] {hostname} → schema '{tenant.schema_name}'")
        else:
            scope["tenant"] = None
            logger.warning(f"[WS Tenant] Aucun tenant pour le hostname '{hostname}'")

        return await self.app(scope, receive, send)

class WebSocketJWTAuthMiddleware:

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope["user"] = AnonymousUser()
        token = None
        headers = dict(scope.get('headers'))
        if headers:
            token = headers.get(b'authorization')
        if token :
            token = token.decode("utf-8").replace('Bearer ','')
            try:
                access_token = AccessToken(token)
                scope["user"] = await get_user(access_token["user_id"])
            except TokenError:
                logger.info('WebSocketJWTAuthMiddleware BAD TOKEN')

        return await self.app(scope, receive, send)
