"""
Consumer WebSocket pour la caisse LaBoutik
/ WebSocket consumer for the LaBoutik POS

LOCALISATION : wsocket/consumers.py

Ce consumer gere la connexion WebSocket entre le serveur Django
et l'interface caisse (navigateur). Il est utilise pour :
- Repondre aux pings du navigateur (mesure de latence)
- Pousser des mises a jour de jauge billetterie (jauge_update)
- Pousser des mises a jour de badges stock (stock_update)
- Envoyer des notifications aux caisses connectees (notification)

FLUX :
1. Le navigateur ouvre une connexion WebSocket via HTMX ws extension
2. WebSocketTenantMiddleware resout le tenant depuis le hostname
3. Le consumer rejoint le group Redis `laboutik-pv-{pv_uuid}`
4. Les vues Django envoient des messages au group via broadcast.py
5. Le consumer transmet le HTML au navigateur
6. Le navigateur peut envoyer un ping, le consumer repond avec un pong

DEPENDENCIES :
- Django Channels (channels_redis pour le channel layer)
- HTMX ws extension (cote navigateur)
- WebSocketTenantMiddleware (wsocket/middlewares.py) pour le contexte tenant
"""

import json
import logging
import time

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class LaboutikConsumer(AsyncWebsocketConsumer):
    """
    Consumer WebSocket pour un point de vente LaBoutik.
    / WebSocket consumer for a LaBoutik point of sale.

    Chaque PV a son propre group Redis (`laboutik-pv-{pv_uuid}`).
    Le tenant est disponible dans self.scope["tenant"] grace au middleware.
    """

    async def connect(self):
        """
        Connexion WebSocket : rejoint le group du PV et le group jauges du tenant.
        / WebSocket connection: joins the PV group and the tenant gauges group.
        """
        self.pv_uuid = self.scope["url_route"]["kwargs"]["pv_uuid"]
        self.pv_group_name = f"laboutik-pv-{self.pv_uuid}"

        # Rejoindre le group Redis du point de vente
        # / Join the Redis group for this point of sale
        await self.channel_layer.group_add(self.pv_group_name, self.channel_name)

        # Rejoindre le group global jauges du tenant
        # Toutes les caisses du tenant recoivent les mises a jour de jauge
        # (OOB swap ignore silencieusement les events non affiches par ce PV)
        # / Join the tenant-wide gauges group
        # All POS terminals in the tenant receive gauge updates
        # (OOB swap silently ignores events not displayed by this PV)
        tenant = self.scope.get("tenant")
        tenant_schema = tenant.schema_name if tenant else "public"
        self.jauges_group_name = f"laboutik-jauges-{tenant_schema}"
        await self.channel_layer.group_add(self.jauges_group_name, self.channel_name)

        await self.accept()
        logger.info(
            f"[WS] Caisse connectee au PV {self.pv_uuid} (tenant: {tenant_schema})"
        )

    async def disconnect(self, close_code):
        """
        Deconnexion : quitte le group du PV et le group jauges.
        / Disconnection: leaves the PV group and the gauges group.
        """
        await self.channel_layer.group_discard(self.pv_group_name, self.channel_name)
        # Quitter le group jauges si il a ete rejoint
        # / Leave the gauges group if it was joined
        if hasattr(self, "jauges_group_name"):
            await self.channel_layer.group_discard(
                self.jauges_group_name, self.channel_name
            )
        logger.info(f"[WS] Caisse deconnectee du PV {self.pv_uuid}")

    async def receive(self, text_data):
        """
        Reception de messages du navigateur.
        / Receives messages from browser.

        Seul message accepte : ping.
        Le consumer repond avec un pong contenant le timestamp serveur
        pour que le navigateur calcule la latence aller-retour.
        / Only accepted message: ping.
        The consumer responds with a pong containing the server timestamp
        so the browser can calculate round-trip latency.
        """
        try:
            message = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            return

        type_message = message.get("type")
        if type_message == "ping":
            # Renvoyer le timestamp client + le timestamp serveur
            # / Send back the client timestamp + the server timestamp
            reponse_pong = json.dumps(
                {
                    "type": "pong",
                    "client_ts": message.get("client_ts", 0),
                    "server_ts": time.time() * 1000,
                }
            )
            await self.send(text_data=reponse_pong)

    async def jauge_update(self, event):
        """
        Recoit une mise a jour de jauge depuis le group Redis
        et la pousse au navigateur.
        / Receives a gauge update from the Redis group and pushes it to the browser.

        Le HTML est pre-rendu par broadcast.py (render_to_string cote serveur).
        """
        await self.send(text_data=event["html"])

    async def notification(self, event):
        """
        Recoit une notification depuis le group Redis
        et la pousse au navigateur.
        / Receives a notification from the Redis group and pushes it to the browser.
        """
        await self.send(text_data=event["html"])

    async def stock_update(self, event):
        """
        Reçoit une mise à jour de stock depuis le group Redis
        et la pousse au navigateur (OOB swap des badges stock).
        / Receives a stock update from the Redis group and pushes it to the browser.
        """
        await self.send(text_data=event["html"])


class PrinterConsumer(AsyncWebsocketConsumer):
    """
    Consumer WebSocket dedie aux imprimantes Sunmi Inner.
    L'app Android de la tablette Sunmi se connecte a ce consumer
    et recoit des commandes JSON pour imprimer.
    / Dedicated WebSocket consumer for Sunmi Inner printers.
    The Sunmi tablet's Android app connects to this consumer
    and receives JSON commands to print.

    LOCALISATION : wsocket/consumers.py

    FLUX :
    1. L'app Android ouvre ws/printer/{printer_uuid}/
    2. Le consumer rejoint le group Redis `printer-{printer_uuid}`
    3. Le SunmiInnerBackend envoie des commandes via channel_layer.group_send
    4. Le consumer transmet les commandes JSON a l'app Android
    5. L'app Android interprete les commandes et imprime

    FORMAT DES COMMANDES :
    {"action": "print", "commands": [
        {"type": "text", "value": "...", "bold": true, "size": 2, "align": "center"},
        {"type": "qrcode", "value": "https://...", "size": 5},
        {"type": "cut"}
    ]}
    """

    async def connect(self):
        """
        Connexion : verifie l'authentification puis rejoint le group Redis.
        Les appareils POS sont loggues via session admin Django.
        AuthMiddlewareStack (dans asgi.py) resout la session et place
        l'utilisateur dans scope["user"]. On refuse la connexion si
        l'utilisateur n'est pas authentifie ou si le tenant n'est pas resolu.
        / Connection: checks authentication then joins the Redis group.
        POS devices are logged in via Django admin session.
        AuthMiddlewareStack resolves the session and places
        the user in scope["user"]. We reject if user is not authenticated
        or tenant is not resolved.
        """
        # Verifier que le tenant est resolu (WebSocketTenantMiddleware)
        # / Check that the tenant is resolved
        tenant = self.scope.get("tenant")
        if not tenant:
            logger.warning("[WS] Printer connexion refusee : pas de tenant")
            await self.close()
            return

        # Verifier que l'utilisateur est authentifie (session admin)
        # / Check that the user is authenticated (admin session)
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            logger.warning(
                f"[WS] Printer connexion refusee : utilisateur non authentifie "
                f"(tenant={tenant.schema_name})"
            )
            await self.close()
            return

        self.printer_uuid = self.scope["url_route"]["kwargs"]["printer_uuid"]
        self.group_name = f"printer-{self.printer_uuid}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info(
            f"[WS] Imprimante connectee : {self.printer_uuid} "
            f"(user={user.email}, tenant={tenant.schema_name})"
        )

    async def disconnect(self, close_code):
        """
        Deconnexion : quitte le group Redis si la connexion avait ete acceptee.
        / Disconnection: leaves the Redis group if connection was accepted.
        """
        # Si la connexion a ete refusee dans connect(), group_name n'existe pas
        # / If connection was rejected in connect(), group_name doesn't exist
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(f"[WS] Imprimante deconnectee : {self.printer_uuid}")

    async def receive(self, text_data):
        """
        Reception de messages de l'app Android (pas utilise pour l'instant).
        / Receives messages from the Android app (not used for now).
        """
        pass

    async def print_ticket(self, event):
        """
        Recoit une commande d'impression depuis le channel layer Redis
        et la transmet a l'app Android.
        Le type "print.ticket" dans group_send devient la methode "print_ticket"
        (Channels convertit les points en underscores).
        / Receives a print command from the Redis channel layer
        and forwards it to the Android app.
        """
        await self.send(
            text_data=json.dumps(
                {
                    "action": "print",
                    "commands": event["commands"],
                }
            )
        )
