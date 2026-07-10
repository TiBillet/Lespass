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

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.template.loader import get_template

from AuthBillet.models import TibilletUser

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


# --- TerminalConsumer (kiosk, CHANTIER-02 Task 02B) ---
class TerminalConsumer(AsyncWebsocketConsumer):
    """
    Consumer WebSocket pour le suivi d'un paiement TPE Stripe depuis le kiosk.
    / WebSocket consumer tracking a Stripe terminal payment from the kiosk.

    Copie rebranchee de LaBoutik htmxview/consumers.py (TerminalConsumer).
    Le room_name est le `payment_intent_stripe_id` (voir kiosk/routing.py et
    kiosk/templates/kiosk/waiting_credit_card_terminal.html).
    / Rebranched copy of LaBoutik htmxview/consumers.py (TerminalConsumer).
    room_name is the `payment_intent_stripe_id` (see kiosk/routing.py and
    kiosk/templates/kiosk/waiting_credit_card_terminal.html).

    Garde d'acces : LaBoutik verifie `hasattr(self.user, 'appareil')`
    (modele Appareil, absent cote Lespass). Ici on verifie le role terminal
    du user (TibilletUser.ROLE_KIOSQUE), pose par l'auth de session du kiosk.
    / Access guard: LaBoutik checks `hasattr(self.user, 'appareil')`
    (Appareil model, absent on Lespass side). Here we check the user's
    terminal role (TibilletUser.ROLE_KIOSQUE), set by the kiosk's session auth.
    """

    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.user = self.scope["user"]

        # Deux gardes, dans cet ordre :
        #   1. le user est bien une borne Kiosque (role KI) ;
        #   2. le paiement ecoute appartient bien a CETTE borne.
        # Sans la seconde, une borne KI pourrait suivre le paiement d'une autre
        # borne, y compris d'un autre tenant : le nom du group Redis est
        # l'identifiant Stripe du paiement, partage par tous les schemas.
        # / Two guards: the user is a Kiosk terminal (KI), and the payment being
        # watched belongs to THIS device. Without the second one, a KI device
        # could follow another device's payment, even across tenants: the Redis
        # group name is the Stripe payment id, shared by all schemas.
        if not settings.DEBUG:
            if not self.user.is_authenticated or getattr(self.user, "terminal_role", None) != TibilletUser.ROLE_KIOSQUE:
                logger.error(f"{self.room_name} {self.user} ERROR NOT AUTHENTICATED OR NOT KIOSK TERMINAL")
                await self.close()
                return

            paiement_appartient_a_la_borne = await self.payment_intent_belongs_to_user()
            if not paiement_appartient_a_la_borne:
                logger.error(f"{self.room_name} {self.user} ERROR PAYMENT INTENT DOES NOT BELONG TO THIS TERMINAL")
                await self.close()
                return

        logger.info(f"{self.room_name} {self.user} connected")

        # Join room group
        await self.channel_layer.group_add(self.room_name, self.channel_name)

        await self.accept()

        # REJEU D'ETAT A LA (RE)CONNEXION
        # / State replay on (re)connect
        #
        # Le resultat final du paiement (succes/annule) est pousse une seule fois
        # par la tache Celery `poll_payment_intent_status`.
        # Si le reseau de la borne coupe juste a cet instant, ou si le paiement
        # reussit avant meme que ce websocket soit connecte, le message est perdu :
        # l'ecran reste bloque sur le spinner alors que Stripe a deja valide.
        #
        # Pour eviter ca : des qu'un client (re)connecte, on relit l'etat reel du
        # paiement en base. S'il est deja termine, on lui renvoie tout de suite le
        # bon ecran. La tache Celery met l'etat a jour en base meme quand la borne
        # est deconnectee, donc l'etat lu ici est fiable.
        #
        # / The final payment result is pushed only once by the Celery task and can
        # be lost on a flaky network. On reconnect we re-read the real status from
        # the database and replay the correct screen.
        await self.replay_payment_state_if_finished()

    @database_sync_to_async
    def payment_intent_belongs_to_user(self):
        """
        Le paiement ecoute appartient-il bien a la borne connectee ?
        / Does the watched payment belong to the connected device?

        Le lien est : PaymentsIntent -> Terminal (TPE) -> term_user (la borne).
        Un paiement inconnu est refuse : la vue cree toujours le PaymentsIntent
        AVANT de rendre le template qui ouvre le websocket.
        / The chain is PaymentsIntent -> Terminal -> term_user. An unknown payment
        is refused: the view always creates the PaymentsIntent before rendering
        the template that opens the websocket.

        room_name == payment_intent_stripe_id
        """
        from kiosk.models import PaymentsIntent

        try:
            payment_intent = PaymentsIntent.objects.select_related("terminal").get(
                payment_intent_stripe_id=self.room_name,
            )
        except PaymentsIntent.DoesNotExist:
            return False

        # Un TPE non appaire (term_user=None) n'appartient a aucune borne.
        # / An unpaired terminal (term_user=None) belongs to no device.
        return payment_intent.terminal.term_user_id == self.user.id

    @database_sync_to_async
    def get_finished_template_name(self):
        """
        Lit le statut reel du paiement en base et renvoie le nom du template final
        si le paiement est termine, sinon None.
        / Reads the real payment status from DB; returns the final template name
        if the payment is finished, else None.

        room_name == payment_intent_stripe_id
        (voir kiosk/routing.py et kiosk/templates/kiosk/waiting_credit_card_terminal.html)
        """
        from kiosk.models import PaymentsIntent
        try:
            payment_intent = PaymentsIntent.objects.get(payment_intent_stripe_id=self.room_name)
        except PaymentsIntent.DoesNotExist:
            return None

        if payment_intent.status == PaymentsIntent.SUCCEEDED:
            return "success.html"
        if payment_intent.status == PaymentsIntent.CANCELED:
            return "cancel.html"
        # Paiement encore en cours : le polling enverra la suite.
        # / Still in progress: polling will send the rest.
        return None

    async def replay_payment_state_if_finished(self):
        """
        Renvoie immediatement l'ecran final (succes/annule) si le paiement est
        deja termine au moment ou ce client (re)connecte. Sinon ne fait rien.
        / Immediately replays the final screen if the payment is already finished.
        """
        template_name = await self.get_finished_template_name()
        if not template_name:
            return
        logger.info(f"Rejeu d'etat WS pour {self.room_name} -> kiosk/{template_name}")
        # Meme rendu que la methode `template()` : le HTML porte un hx-swap-oob
        # qui remplace #tb-kiosque cote borne.
        # / Same render as `template()`: the HTML carries an hx-swap-oob.
        html = get_template(f"kiosk/{template_name}").render(context={})
        await self.send(text_data=html)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_name, self.channel_name)

    async def receive(self, text_data):
        """Non utilise cote kiosk : le serveur pousse, la borne ne parle pas.
        / Not used on the kiosk side: server pushes, the kiosk does not talk back."""
        pass

    # Recoit un message du group Redis. Doit avoir le meme nom que le type du
    # message envoye par `group_send` (ex : depuis kiosk/tasks.py).
    # / Receives a message from the Redis group. Must have the same name as the
    # `type` sent by `group_send` (e.g. from kiosk/tasks.py).
    async def template(self, event):
        logger.info(f"template event: {event}")
        template_name = event["template"]
        html = get_template(f"kiosk/{template_name}").render(context={"event": event})
        await self.send(text_data=html)

    async def message(self, event):
        """
        Message de progression du polling (kiosk/tasks.py envoie type='message'
        a chaque tick, avant l'evenement final type='template'). Le front kiosk
        garde la zone #message masquee (voir waiting_credit_card_terminal.html) :
        on logge simplement l'evenement. Sans ce handler, group_send lève une
        exception (pas de handler pour ce type) qui ferme le websocket a chaque tick.
        / Polling progress message (kiosk/tasks.py sends type='message' on every
        tick, before the final type='template' event). The kiosk front keeps the
        #message zone hidden: we just log the event. Without this handler,
        group_send raises (no handler for this type), closing the websocket on
        every tick.
        """
        logger.info(f"message event: {event}")


# --- ChatConsumer (chat wsocket V1, conserve lors du portage laboutik) ---
class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = f"chat_{self.room_name}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]
        await self.channel_layer.group_send(
            self.room_group_name, {"type": "chat.message", "message": message}
        )

    async def chat_message(self, event):
        message = event["message"]
        await self.send(text_data=json.dumps({"message": message}))
