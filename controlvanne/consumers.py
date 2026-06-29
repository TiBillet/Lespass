"""
Consumer WebSocket pour le module tireuse connectée (controlvanne).
/ WebSocket consumer for the connected tap module (controlvanne).

LOCALISATION : controlvanne/consumers.py

Ce consumer gère la connexion WebSocket entre le serveur Django
et les écrans kiosk des tireuses (page web sur le Pi).
/ This consumer handles the WebSocket connection between the Django server
and the tap kiosk screens (web page on the Pi).

Deux groupes Channels :
- rfid_state.all    → toutes les tireuses (vue liste)
- rfid_state.<uuid> → une seule tireuse (vue detail)
/ Two Channels groups:
- rfid_state.all    → all taps (list view)
- rfid_state.<uuid> → a single tap (detail view)

COMMUNICATION :
Reçoit : state_update depuis les signaux TireuseBec (signals.py)
Envoie : payload JSON vers le client JS (panel_kiosk.js)
/ Receives: state_update from TireuseBec signals (signals.py)
Sends: JSON payload to JS client (panel_kiosk.js)
"""

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from controlvanne.models import RfidSession, TireuseBec

logger = logging.getLogger(__name__)


class PanelConsumer(AsyncJsonWebsocketConsumer):
    """
    Consumer WebSocket pour les écrans kiosk des tireuses.
    / WebSocket consumer for tap kiosk screens.

    LOCALISATION : controlvanne/consumers.py

    À la connexion, le client s'abonne à un groupe Channels :
    - /ws/rfid/all/    → groupe rfid_state.all (toutes les tireuses)
    - /ws/rfid/<uuid>/ → groupe rfid_state.<uuid> (une seule tireuse)
    / On connection, the client subscribes to a Channels group:
    - /ws/rfid/all/    → group rfid_state.all (all taps)
    - /ws/rfid/<uuid>/ → group rfid_state.<uuid> (a single tap)
    """

    async def connect(self):
        """
        Connexion WebSocket : détermine le groupe et envoie l'état initial.
        / WebSocket connection: determine group and send initial state.
        """
        # Récupérer le slug depuis l'URL (/ws/rfid/<slug>/)
        # / Get slug from URL (/ws/rfid/<slug>/)
        slug = self.scope.get("url_route", {}).get("kwargs", {}).get("slug")
        logger.debug(f"WS connexion — slug reçu : '{slug}'")

        # Déterminer le groupe Channels
        # Si pas de slug ou slug = "all" → groupe global
        # Sinon → groupe spécifique à la tireuse (slug = uuid)
        # / Determine Channels group
        # No slug or slug = "all" → global group
        # Otherwise → tap-specific group (slug = uuid)
        if slug and slug.lower() != "all":
            self.group = f"rfid_state.{slug.lower()}"
        else:
            self.group = "rfid_state.all"

        logger.debug(f"WS connexion — abonnement au groupe : '{self.group}'")

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

        # Envoyer l'état initial au client qui vient de se connecter
        # / Send initial state to the newly connected client
        payload_initial = await self._construire_payload_initial(slug)
        if payload_initial:
            await self.send_json(payload_initial)

    async def disconnect(self, code):
        """
        Déconnexion WebSocket : quitte le groupe Channels.
        / WebSocket disconnection: leave the Channels group.
        """
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def state_update(self, event):
        """
        Reçoit un event state_update depuis les signaux Django (signals.py).
        Transmet le payload JSON au client WebSocket (panel_kiosk.js).
        / Receives a state_update event from Django signals (signals.py).
        Forwards the JSON payload to the WebSocket client (panel_kiosk.js).
        """
        logger.debug(f"WS envoi au groupe {self.group}")
        await self.send_json(event["payload"])

    @database_sync_to_async
    def _construire_payload_initial(self, slug_tireuse):
        """
        Construit le payload initial envoyé à la connexion WebSocket.
        Pour le groupe "all", pas de payload initial (les signaux post_save suffisent).
        Pour une tireuse spécifique, envoie son état courant.
        / Builds the initial payload sent on WebSocket connection.
        For the "all" group, no initial payload (post_save signals are enough).
        For a specific tap, sends its current state.

        LOCALISATION : controlvanne/consumers.py

        PIÈGE django-tenants :
        database_sync_to_async crée un thread worker qui n'hérite pas
        de connection.tenant. Il faut rétablir le tenant depuis scope["tenant"]
        avant toute requête sur une TENANT_APP (TireuseBec, RfidSession).
        / django-tenants PITFALL:
        database_sync_to_async creates a worker thread that does not inherit
        connection.tenant. We must restore the tenant from scope["tenant"]
        before any query on a TENANT_APP (TireuseBec, RfidSession).

        :param slug_tireuse: str — UUID de la tireuse ou "all" ou None
        :return: dict payload ou None
        """
        # Pas de payload initial pour le groupe global
        # / No initial payload for the global group
        if not slug_tireuse or slug_tireuse.lower() == "all":
            return None

        # Rétablir le tenant sur ce thread worker (piège django-tenants + Channels)
        # / Restore tenant on this worker thread (django-tenants + Channels pitfall)
        tenant = self.scope.get("tenant")
        if tenant:
            from django.db import connection as db_connection

            db_connection.set_tenant(tenant)

        tireuse = TireuseBec.objects.filter(uuid=slug_tireuse).first()
        if not tireuse:
            return {
                "tireuse_bec": slug_tireuse,
                "liquid_label": "Liquide",
                "present": False,
                "authorized": False,
                "vanne_ouverte": False,
                "volume_ml": 0.0,
                "debit_l_min": 0.0,
                "message": "",
            }

        # Tireuse désactivée → mode maintenance
        # / Disabled tap → maintenance mode
        if not tireuse.enabled:
            return {
                "tireuse_bec": tireuse.nom_tireuse,
                "tireuse_bec_uuid": str(tireuse.uuid),
                "maintenance": True,
                "present": False,
                "authorized": False,
                "vanne_ouverte": False,
                "message": "En Maintenance",
            }

        # Session NFC ouverte la plus récente (ended_at=null → carte posée)
        # / Most recent open NFC session (ended_at=null → card present)
        session_ouverte = (
            RfidSession.objects.filter(
                tireuse_bec=tireuse,
                ended_at__isnull=True,
            )
            .order_by("-started_at")
            .first()
        )

        return {
            "tireuse_bec": tireuse.nom_tireuse,
            "tireuse_bec_uuid": str(tireuse.uuid),
            "liquid_label": tireuse.liquid_label,
            "present": bool(session_ouverte and session_ouverte.uid),
            "authorized": bool(session_ouverte.authorized)
            if session_ouverte
            else False,
            "vanne_ouverte": False,
            "volume_ml": float(
                session_ouverte.volume_end_ml if session_ouverte else 0.0
            ),
            "debit_cl_min": 0.0,
            "reservoir_ml": float(tireuse.reservoir_ml),
            "reservoir_max_ml": tireuse.reservoir_max_ml,
            "prix_litre": str(tireuse.prix_litre),
            "currency": "\u20ac",
            "message": session_ouverte.last_message if session_ouverte else "",
            "uid": session_ouverte.uid if session_ouverte else None,
        }
