"""
Middlewares WebSocket pour LaBoutik
/ WebSocket middlewares for LaBoutik

LOCALISATION : wsocket/middlewares.py

Deux middlewares ASGI pour les connexions WebSocket :
1. WebSocketTenantMiddleware — resout le tenant depuis le hostname
2. WebSocketJWTAuthMiddleware — authentifie via JWT (existant, pas utilise pour l'instant)

FLUX (ordre dans asgi.py) :
AllowedHostsOriginValidator
  → WebSocketTenantMiddleware (resout le tenant, set connection.tenant)
    → AuthMiddlewareStack (resout la session Django)
      → URLRouter (route vers le consumer)

DEPENDENCIES :
- Customers.models.Domain (DomainMixin de django-tenants)
- django.db.connection (pour set_tenant / set_schema_to_public)
"""
import logging

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from rest_framework_simplejwt.tokens import AccessToken, TokenError

User = get_user_model()

logger = logging.getLogger(__name__)


# --- Resolution du tenant depuis le hostname ---
# / Tenant resolution from hostname

@database_sync_to_async
def _get_tenant_from_hostname(hostname):
    """
    Cherche le tenant (Client) a partir du hostname de la requete WebSocket.
    Reproduit la logique de TenantMainMiddleware.get_tenant().
    / Looks up the tenant (Client) from the WebSocket request hostname.
    Replicates the logic of TenantMainMiddleware.get_tenant().

    :param hostname: Nom de domaine sans port ni www (ex: "lespass.tibillet.localhost")
    :return: Instance Client (tenant) ou None si pas trouve
    """
    from Customers.models import Domain

    # Se placer sur le schema public pour lire les metadonnees tenant
    # (les Domain sont dans le schema public)
    # / Switch to public schema to read tenant metadata
    # (Domains are stored in the public schema)
    connection.set_schema_to_public()

    try:
        domain = Domain.objects.select_related("tenant").get(domain=hostname)
        return domain.tenant
    except Domain.DoesNotExist:
        return None


class WebSocketTenantMiddleware:
    """
    Middleware ASGI qui resout le tenant depuis le hostname de la connexion WebSocket
    et configure connection.tenant + connection.schema_name.
    / ASGI middleware that resolves the tenant from the WebSocket connection hostname
    and configures connection.tenant + connection.schema_name.

    Reproduit le comportement de django_tenants.middleware.TenantMainMiddleware
    mais pour les connexions WebSocket (ASGI) au lieu de HTTP (WSGI).

    Le tenant est aussi stocke dans scope["tenant"] pour que le consumer
    puisse y acceder si besoin.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Extraire le hostname depuis les headers de la requete WebSocket
        # Le header "host" contient le hostname:port (ex: "lespass.tibillet.localhost:8002")
        # / Extract hostname from WebSocket request headers
        # The "host" header contains hostname:port
        headers = dict(scope.get("headers", []))
        host_header = headers.get(b"host", b"").decode("utf-8")

        # Retirer le port et le www (comme TenantMainMiddleware.hostname_from_request)
        # / Remove port and www (like TenantMainMiddleware.hostname_from_request)
        hostname = host_header.split(":")[0]
        if hostname.startswith("www."):
            hostname = hostname[4:]

        # Chercher le tenant en base
        # / Look up the tenant in DB
        tenant = await _get_tenant_from_hostname(hostname)

        if tenant is not None:
            # Configurer le tenant sur la connexion DB (comme TenantMainMiddleware.process_request)
            # / Set tenant on the DB connection (like TenantMainMiddleware.process_request)
            scope["tenant"] = tenant
            await database_sync_to_async(connection.set_tenant)(tenant)
            logger.debug(
                f"[WS Tenant] {hostname} → schema '{tenant.schema_name}'"
            )
        else:
            # Pas de tenant trouve — rester sur le schema public
            # Le consumer decidera quoi faire (rejeter la connexion ou continuer)
            # / No tenant found — stay on public schema
            # The consumer will decide what to do (reject or continue)
            scope["tenant"] = None
            logger.warning(
                f"[WS Tenant] Aucun tenant pour le hostname '{hostname}'"
            )

        return await self.app(scope, receive, send)


# --- Authentification JWT (existant, pas utilise pour l'instant) ---
# / JWT authentication (existing, not used for now)

@database_sync_to_async
def _get_user(user_id):
    """
    Recupere un utilisateur par son ID, ou retourne AnonymousUser.
    / Gets a user by ID, or returns AnonymousUser.
    """
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()


class WebSocketJWTAuthMiddleware:
    """
    Middleware ASGI qui authentifie la connexion WebSocket via un token JWT
    dans le header Authorization.
    / ASGI middleware that authenticates the WebSocket connection via a JWT token
    in the Authorization header.

    Pas utilise pour l'instant (la caisse utilise l'auth session via AuthMiddlewareStack).
    Conserve pour un usage futur (ex: connexion depuis une app mobile).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope["user"] = AnonymousUser()
        token = None
        headers = dict(scope.get("headers", []))
        if headers:
            token = headers.get(b"authorization")
        if token:
            token = token.decode("utf-8").replace("Bearer ", "")
            try:
                access_token = AccessToken(token)
                scope["user"] = await _get_user(access_token["user_id"])
            except TokenError:
                logger.info("WebSocketJWTAuthMiddleware BAD TOKEN")

        return await self.app(scope, receive, send)
