"""
Consumer WebSocket pour la caisse LaBoutik
/ WebSocket consumer for the LaBoutik POS

LOCALISATION : wsocket/consumers.py

Ce consumer gere la connexion WebSocket entre le serveur Django
et l'interface caisse (navigateur). Il est utilise pour :
- Repondre aux pings du navigateur (mesure de latence)
- Pousser des mises a jour de jauge billetterie (jauge_update)
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
        await self.channel_layer.group_add(
            self.pv_group_name, self.channel_name
        )

        # Rejoindre le group global jauges du tenant
        # Toutes les caisses du tenant recoivent les mises a jour de jauge
        # (OOB swap ignore silencieusement les events non affiches par ce PV)
        # / Join the tenant-wide gauges group
        # All POS terminals in the tenant receive gauge updates
        # (OOB swap silently ignores events not displayed by this PV)
        tenant = self.scope.get("tenant")
        tenant_schema = tenant.schema_name if tenant else "public"
        self.jauges_group_name = f"laboutik-jauges-{tenant_schema}"
        await self.channel_layer.group_add(
            self.jauges_group_name, self.channel_name
        )

        await self.accept()
        logger.info(
            f"[WS] Caisse connectee au PV {self.pv_uuid} "
            f"(tenant: {tenant_schema})"
        )

    async def disconnect(self, close_code):
        """
        Deconnexion : quitte le group du PV et le group jauges.
        / Disconnection: leaves the PV group and the gauges group.
        """
        await self.channel_layer.group_discard(
            self.pv_group_name, self.channel_name
        )
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
            reponse_pong = json.dumps({
                "type": "pong",
                "client_ts": message.get("client_ts", 0),
                "server_ts": time.time() * 1000,
            })
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
