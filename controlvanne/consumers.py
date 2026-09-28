"""
Consumer WebSocket pour le module tireuse connectée (controlvanne).
/ WebSocket consumer for the connected tap module (controlvanne).

LOCALISATION : controlvanne/consumers.py

Ce consumer gère la connexion WebSocket entre le serveur Django
et les écrans kiosk des tireuses (page web sur le Pi).
/ This consumer handles the WebSocket connection between the Django server
and the tap kiosk screens (web page on the Pi).

Deux groupes Channels, nommés PAR LIEU (controlvanne/groupes_ws.py) :
- rfid_state.<uuid lieu>.all            → toutes les tireuses du lieu (vue liste)
- rfid_state.<uuid lieu>.<uuid tireuse> → une seule tireuse (vue detail)
/ Two Channels groups, named PER VENUE:
- rfid_state.<venue uuid>.all           → all taps of the venue (list view)
- rfid_state.<venue uuid>.<tap uuid>    → a single tap (detail view)

ACCÈS (audit 2026-09-26, point 1.1) : même règle que la page du kiosk
(controlvanne/acces.py) — session kiosk ou admin du lieu. Sinon la connexion
est refusée avant d'être acceptée.
/ ACCESS: same rule as the kiosk page; otherwise refused before accept.

COMMUNICATION :
Reçoit : state_update depuis les signaux TireuseBec (signals.py)
Envoie : payload JSON vers le client JS (ecran_tireuse.js)
/ Receives: state_update from TireuseBec signals (signals.py)
Sends: JSON payload to JS client (ecran_tireuse.js)
"""

import logging
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db import connection
from django.utils.translation import gettext

from controlvanne.acces import peut_voir_les_kiosks
from controlvanne.groupes_ws import groupe_de_la_tireuse, groupe_de_tout_le_lieu
from controlvanne.models import RfidSession, TireuseBec

logger = logging.getLogger(__name__)


class PanelConsumer(AsyncJsonWebsocketConsumer):
    """
    Consumer WebSocket pour les écrans kiosk des tireuses.
    / WebSocket consumer for tap kiosk screens.

    LOCALISATION : controlvanne/consumers.py

    À la connexion, le client s'abonne à un groupe Channels de SON lieu :
    - /ws/rfid/all/    → rfid_state.<uuid lieu>.all (toutes les tireuses du lieu)
    - /ws/rfid/<uuid>/ → rfid_state.<uuid lieu>.<uuid> (une tireuse de ce lieu)
    / On connection, the client subscribes to a group of ITS venue.
    """

    # Pas encore abonné : disconnect() ne doit rien retirer si connect() a refusé
    # / Not subscribed yet: disconnect() must not discard if connect() refused
    group = None

    async def connect(self):
        """
        Connexion WebSocket : contrôle d'accès, abonnement, état initial.
        / WebSocket connection: access check, subscription, initial state.

        FLUX :
        1. Lieu connu ? (scope["tenant"], posé par WebSocketTenantMiddleware
           à partir du nom de domaine). Sinon refus.
        2. Accès permis ? Session kiosk ou admin du lieu (même règle que la
           page, controlvanne/acces.py). Sinon refus.
        3. Slug valide ? « all » ou l'UUID d'une tireuse DE CE LIEU. Sinon refus.
        4. Abonnement au groupe du lieu, acceptation, envoi de l'état initial.
        Refus = close() AVANT accept() : le navigateur reçoit un refus de
        connexion, et ecran_tireuse.js affiche le bandeau « connexion perdue ».
        / Refusal = close() BEFORE accept(): the handshake is rejected.
        """
        # Slug de l'URL (/ws/rfid/<slug>/) / URL slug
        slug = self.scope.get("url_route", {}).get("kwargs", {}).get("slug") or "all"
        slug = slug.lower()

        # 1. Lieu / Venue
        lieu = self.scope.get("tenant")
        if lieu is None:
            logger.warning(f"WS refusé : lieu inconnu (slug={slug})")
            await self.close(code=4003)
            return

        # 2 et 3. Accès et slug (requêtes en base : hors de la boucle async)
        # / 2 and 3. Access and slug (DB queries: outside the async loop)
        refus = await self._raison_du_refus(lieu, slug)
        if refus:
            logger.warning(f"WS refusé : {refus} (lieu={lieu.schema_name}, slug={slug})")
            await self.close(code=4003)
            return

        # 4. Groupe du lieu / Venue group
        if slug == "all":
            self.group = groupe_de_tout_le_lieu(lieu.uuid)
        else:
            self.group = groupe_de_la_tireuse(lieu.uuid, slug)
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
        Déconnexion WebSocket : quitte le groupe Channels (s'il y en a un :
        une connexion refusée n'a jamais été abonnée).
        / WebSocket disconnection: leave the group (if any).
        """
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    @database_sync_to_async
    def _raison_du_refus(self, lieu, slug):
        """
        Dit pourquoi refuser la connexion, ou None si elle est permise.
        / Says why the connection is refused, or None if allowed.

        LOCALISATION : controlvanne/consumers.py

        PIÈGE django-tenants : ce thread (database_sync_to_async) n'hérite pas
        du lieu. On le rétablit avant toute requête sur une TENANT_APP.
        / This worker thread does not inherit the venue: restore it first.

        Session kiosk acceptée : on l'enregistre pour prolonger sa durée de vie.
        Un kiosk reste des semaines sur la même page sans requête HTTP, et
        seul le HTTP prolongeait la session (SESSION_SAVE_EVERY_REQUEST) :
        sans cela, sa reconnexion WebSocket finirait par être refusée.
        / Kiosk session accepted: save it to extend its lifetime (only HTTP
        requests extended it before).

        :param lieu: Client — le lieu du WebSocket
        :param slug: str — « all » ou UUID de tireuse, en minuscules
        :return: str (raison du refus, pour les logs) ou None
        """
        connection.set_tenant(lieu)

        session = self.scope.get("session")
        utilisateur = self.scope.get("user")
        if not peut_voir_les_kiosks(session, utilisateur, lieu):
            return "ni session kiosk, ni admin du lieu"

        if slug != "all":
            # La route accepte n'importe quelle chaîne (<str:slug>) : on vérifie
            # d'abord que c'est un UUID, sinon la requête lèverait une erreur.
            # / The route accepts any string: check it is a UUID first.
            try:
                uuid_de_la_tireuse = uuid.UUID(slug)
            except ValueError:
                return "slug qui n'est pas un UUID"
            tireuse_du_lieu = TireuseBec.objects.filter(uuid=uuid_de_la_tireuse).exists()
            if not tireuse_du_lieu:
                return "tireuse inconnue dans ce lieu"

        session_kiosk = session is not None and session.get("controlvanne_authenticated")
        if session_kiosk:
            session.save()

        return None

    async def state_update(self, event):
        """
        Reçoit un event state_update depuis les signaux Django (signals.py).
        Transmet le payload JSON au client WebSocket (ecran_tireuse.js).
        / Receives a state_update event from Django signals (signals.py).
        Forwards the JSON payload to the WebSocket client (ecran_tireuse.js).
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
                "liquid_label": gettext("Liquide"),
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
                "message": gettext("En maintenance"),
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
