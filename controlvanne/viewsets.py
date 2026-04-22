"""
ViewSet DRF pour le module tireuse connectée (controlvanne).
/ DRF ViewSet for the connected tap module (controlvanne).

LOCALISATION : controlvanne/viewsets.py

Endpoints du Raspberry Pi :
- ping      → test de connectivité + config tireuse
- authorize → badge NFC → autorisation de service
- event     → mise à jour volume/statut en temps réel

Auth kiosk :
- AuthKioskView → POST token API → cookie session Django (pour le navigateur kiosk)

Conformité djc : ViewSet (pas ModelViewSet), serializers DRF, pas de @csrf_exempt.
/ djc compliance: ViewSet (not ModelViewSet), DRF serializers, no @csrf_exempt.
"""

import logging
from decimal import Decimal

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from controlvanne.models import (
    CarteMaintenance,
    RfidSession,
    TireuseBec,
)
from controlvanne.permissions import HasTireuseAccess
from controlvanne.serializers import (
    AuthorizeSerializer,
    EventSerializer,
    PingSerializer,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Helper WS — push temps réel vers le kiosk
# / WS helper — real-time push to kiosk
# ──────────────────────────────────────────────────────────────────────


def _push_ws_kiosk(tireuse, payload):
    """
    Envoie un payload JSON au kiosk via WebSocket (Channels).
    Pousse vers le groupe spécifique de la tireuse ET le groupe global.
    / Sends a JSON payload to the kiosk via WebSocket (Channels).
    Pushes to the tap-specific group AND the global group.

    LOCALISATION : controlvanne/viewsets.py

    Appelé par authorize() et event() pour informer le kiosk en temps réel.
    Le signal post_save de TireuseBec ne couvre que les changements de réservoir.
    Les changements de session NFC (badge, volume, fin) nécessitent ce push explicite.
    / Called by authorize() and event() to inform the kiosk in real time.
    The TireuseBec post_save signal only covers reservoir changes.
    NFC session changes (badge, volume, end) require this explicit push.

    :param tireuse: TireuseBec — la tireuse concernée
    :param payload: dict — données à envoyer au kiosk (format ws_payloads)
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    # Canal spécifique à cette tireuse (kiosk detail)
    # / Channel specific to this tap (kiosk detail)
    async_to_sync(channel_layer.group_send)(
        f"rfid_state.{tireuse.uuid}",
        {"type": "state_update", "payload": payload},
    )

    # Canal global (kiosk list / dashboard admin)
    # / Global channel (kiosk list / admin dashboard)
    async_to_sync(channel_layer.group_send)(
        "rfid_state.all",
        {"type": "state_update", "payload": payload},
    )


def _construire_payload_session(tireuse, session, **extras):
    """
    Construit le payload WebSocket pour un événement de session NFC.
    / Builds the WebSocket payload for an NFC session event.

    LOCALISATION : controlvanne/viewsets.py

    :param tireuse: TireuseBec
    :param session: RfidSession (ou None)
    :param extras: champs supplémentaires à fusionner (vanne_ouverte, session_done, etc.)
    :return: dict payload
    """
    payload = {
        "tireuse_bec": tireuse.nom_tireuse,
        "tireuse_bec_uuid": str(tireuse.uuid),
        "liquid_label": tireuse.liquid_label,
        "reservoir_ml": float(tireuse.reservoir_ml),
        "reservoir_max_ml": tireuse.reservoir_max_ml,
        "prix_litre": str(tireuse.prix_litre),
        "present": bool(session and session.ended_at is None),
        "authorized": bool(session and session.authorized),
        "vanne_ouverte": False,
        "volume_ml": float(session.dernier_volume_ml if session else 0),
        "uid": session.uid if session else None,
        "message": "",
    }
    # Carte maintenance → flag maintenance
    # / Maintenance card → maintenance flag
    if session and session.is_maintenance:
        payload["maintenance"] = True

    # Fusionner les champs supplémentaires (vanne_ouverte, balance, message, etc.)
    # / Merge extra fields (vanne_ouverte, balance, message, etc.)
    payload.update(extras)
    return payload


class TireuseViewSet(viewsets.ViewSet):
    """
    API du Raspberry Pi pour les tireuses connectées.
    / Raspberry Pi API for connected taps.

    - ping()      → test connexion + config tireuse / connectivity test + tap config
    - authorize() → badge NFC → autorisation / NFC badge → authorization
    - event()     → volume/statut temps réel / real-time volume/status
    """

    permission_classes = [HasTireuseAccess]

    # ─── ping ─────────────────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="ping", url_name="ping")
    def ping(self, request):
        """
        POST /controlvanne/api/tireuse/ping/
        Test de connectivité. Renvoie le statut et la config de la tireuse si UUID fourni.
        / Connectivity test. Returns status and tap config if UUID provided.
        """
        serializer = PingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tireuse_uuid = serializer.validated_data.get("tireuse_uuid")
        if not tireuse_uuid:
            return Response({"status": "pong", "message": "Server online"})

        # Chercher la tireuse sur ce tenant / Find the tap on this tenant
        try:
            tireuse = TireuseBec.objects.get(uuid=tireuse_uuid)
        except TireuseBec.DoesNotExist:
            return Response(
                {"status": "error", "message": "Tap not found on this tenant."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "status": "pong",
                "tireuse": {
                    "uuid": str(tireuse.uuid),
                    "nom": tireuse.nom_tireuse,
                    "enabled": tireuse.enabled,
                    "liquid_label": tireuse.liquid_label,
                    "prix_litre": str(tireuse.prix_litre),
                    "reservoir_ml": float(tireuse.reservoir_ml),
                    "reservoir_max_ml": tireuse.reservoir_max_ml,
                    "calibration_factor": (
                        tireuse.debimetre.flow_calibration_factor
                        if tireuse.debimetre
                        else None
                    ),
                },
            }
        )

    # ─── authorize ────────────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="authorize", url_name="authorize")
    def authorize(self, request):
        """
        POST /controlvanne/api/tireuse/authorize/
        Badge NFC posé sur la tireuse. Vérifie la carte et autorise le service.
        / NFC badge placed on the tap. Checks the card and authorizes pouring.

        - Carte maintenance → mode rinçage, pas de facturation
        - Carte normale → vérification solde wallet, calcul volume max autorisé
        / - Maintenance card → rinse mode, no billing
        / - Normal card → wallet balance check, compute max allowed volume
        """
        serializer = AuthorizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tireuse_uuid = serializer.validated_data["tireuse_uuid"]
        uid = serializer.validated_data["uid"]

        # Chercher la tireuse / Find the tap
        try:
            tireuse = TireuseBec.objects.get(uuid=tireuse_uuid)
        except TireuseBec.DoesNotExist:
            return Response(
                {"authorized": False, "message": "Tap not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Chercher la carte NFC / Find the NFC card
        from QrcodeCashless.models import CarteCashless

        carte = CarteCashless.objects.filter(tag_id=uid).first()
        if not carte:
            return Response({"authorized": False, "message": "Unknown card."})

        # Vérifier si c'est une carte de maintenance / Check if it's a maintenance card
        # On identifie le type de carte AVANT d'appliquer les regles d'acces :
        # la carte maintenance doit pouvoir fonctionner quand la tireuse est hors service,
        # tandis que les cartes normales sont bloquees.
        # / Identify the card type BEFORE applying access rules:
        # maintenance cards must work when the tap is out of service,
        # while normal cards are blocked.
        carte_maintenance = None
        is_maintenance = False
        try:
            carte_maintenance = carte.carte_maintenance
            is_maintenance = True
        except CarteMaintenance.DoesNotExist:
            pass

        # Carte normale + tireuse hors service → refus
        # / Normal card + tap out of service → refuse
        if not tireuse.enabled and not is_maintenance:
            return Response({"authorized": False, "message": "Tap is disabled."})

        # --- Maintenance : uniquement si la tireuse est hors service (enabled=False) ---
        # Une carte maintenance ne peut rincer que quand la tireuse est déclarée
        # hors service dans l'admin — sinon elle serait utilisable comme carte gratuite.
        # / Maintenance: only allowed when the tap is out of service (enabled=False).
        # A maintenance card must not work during normal service — it would bypass billing.
        if is_maintenance and tireuse.enabled:
            return Response(
                {
                    "authorized": False,
                    "message": "Maintenance card refused: tap is in service.",
                }
            )

        if is_maintenance:
            session = RfidSession.objects.create(
                uid=uid,
                carte=carte,
                tireuse_bec=tireuse,
                label_snapshot=str(carte),
                liquid_label_snapshot=tireuse.liquid_label,
                is_maintenance=True,
                carte_maintenance=carte_maintenance,
                produit_maintenance_snapshot=carte_maintenance.produit
                if carte_maintenance
                else "",
                authorized=True,
                allowed_ml_session=tireuse.reservoir_ml,
                volume_start_ml=Decimal("0.00"),
            )

            # Push WS : maintenance autorisée, vanne ouverte
            # / WS push: maintenance authorized, valve open
            _push_ws_kiosk(
                tireuse,
                _construire_payload_session(
                    tireuse,
                    session,
                    vanne_ouverte=True,
                    message="Rinçage autorisé",
                ),
            )

            return Response(
                {
                    "authorized": True,
                    "session_id": session.pk,
                    "is_maintenance": True,
                    "allowed_ml": float(session.allowed_ml_session),
                    "liquid_label": tireuse.liquid_label,
                    "message": "Maintenance mode",
                }
            )

        # --- Service normal : vérifier le solde wallet ---
        # / Normal service: check wallet balance
        from controlvanne.billing import (
            obtenir_contexte_cashless,
            calculer_solde_total_cascade,
            calculer_volume_autorise_ml,
        )

        contexte = obtenir_contexte_cashless(carte)
        if not contexte:
            _push_ws_kiosk(
                tireuse,
                {
                    **_construire_payload_session(tireuse, None),
                    "authorized": False,
                    "present": True,
                    "uid": uid,
                    "message": "Cashless non configuré pour ce lieu.",
                },
            )
            return Response(
                {
                    "authorized": False,
                    "message": "No cashless asset configured for this venue.",
                }
            )

        # Solde total cascade TNF → TLF → FED (identique à LaBoutik)
        # / Total cascade balance TNF → TLF → FED (same as LaBoutik)
        solde_centimes = calculer_solde_total_cascade(
            contexte["wallet_client"], contexte["cascade_assets"]
        )

        prix_litre = tireuse.prix_litre
        if prix_litre <= 0:
            _push_ws_kiosk(
                tireuse,
                {
                    **_construire_payload_session(tireuse, None),
                    "authorized": False,
                    "present": True,
                    "uid": uid,
                    "message": "Prix non configuré pour ce fût.",
                },
            )
            return Response(
                {
                    "authorized": False,
                    "message": "No price configured for the active keg.",
                }
            )

        # Volume disponible dans le reservoir
        # / Available volume in reservoir
        reservoir_disponible = float(tireuse.reservoir_ml)

        if reservoir_disponible <= 0:
            _push_ws_kiosk(
                tireuse,
                {
                    **_construire_payload_session(tireuse, None),
                    "authorized": False,
                    "present": True,
                    "uid": uid,
                    "message": "Fût vide.",
                },
            )
            return Response(
                {
                    "authorized": False,
                    "message": "Empty keg.",
                }
            )

        allowed_ml = calculer_volume_autorise_ml(
            solde_centimes, prix_litre, reservoir_disponible
        )

        if allowed_ml <= 0:
            _push_ws_kiosk(
                tireuse,
                {
                    **_construire_payload_session(tireuse, None),
                    "authorized": False,
                    "present": True,
                    "uid": uid,
                    "message": "Solde insuffisant.",
                    "balance": f"{solde_centimes / 100:.2f}",
                },
            )
            return Response(
                {
                    "authorized": False,
                    "message": "Insufficient funds.",
                    "solde_centimes": solde_centimes,
                }
            )

        session = RfidSession.objects.create(
            uid=uid,
            carte=carte,
            tireuse_bec=tireuse,
            label_snapshot=str(carte),
            liquid_label_snapshot=tireuse.liquid_label,
            is_maintenance=False,
            authorized=True,
            allowed_ml_session=allowed_ml,
            volume_start_ml=Decimal("0.00"),
        )

        logger.info(
            f"Authorize: carte={uid} tireuse={tireuse.nom_tireuse} "
            f"solde={solde_centimes}cts allowed={float(allowed_ml):.0f}ml"
        )

        # Informer le kiosk : carte posee, autorisee, vanne ouverte.
        # Sur le vrai Pi, valve.open() est appelé immédiatement après authorize.
        # Le pour_start est envoyé APRÈS l'ouverture — la vanne est déjà ouverte ici.
        # / Inform kiosk: card placed, authorized, valve open.
        # On the real Pi, valve.open() is called immediately after authorize.
        # pour_start is sent AFTER opening — the valve is already open here.
        _push_ws_kiosk(
            tireuse,
            _construire_payload_session(
                tireuse,
                session,
                vanne_ouverte=True,
                balance=f"{solde_centimes / 100:.2f}",
                message=f"Carte {uid} — service autorisé",
            ),
        )

        return Response(
            {
                "authorized": True,
                "session_id": session.pk,
                "is_maintenance": False,
                "allowed_ml": float(allowed_ml),
                "liquid_label": tireuse.liquid_label,
                "solde_centimes": solde_centimes,
                "message": "OK",
            }
        )

    # ─── event ────────────────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="event", url_name="event")
    def event(self, request):
        """
        POST /controlvanne/api/tireuse/event/
        Événement temps réel pendant un service (volume, fin de service, retrait carte).
        / Real-time event during a pour (volume, pour end, card removed).

        Met à jour la session + le réservoir + push WebSocket.
        Au pour_end : facturation via fedow_core (Transaction + LigneArticle + Stock).
        / Updates session + reservoir + WebSocket push.
        At pour_end: billing via fedow_core (Transaction + LigneArticle + Stock).
        """
        serializer = EventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tireuse_uuid = serializer.validated_data["tireuse_uuid"]
        uid = serializer.validated_data["uid"]
        event_type = serializer.validated_data["event_type"]
        volume_ml = serializer.validated_data.get("volume_ml", Decimal("0"))

        # Chercher la tireuse / Find the tap
        try:
            tireuse = TireuseBec.objects.get(uuid=tireuse_uuid)
        except TireuseBec.DoesNotExist:
            return Response(
                {"status": "error", "message": "Tap not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Chercher la session ouverte pour cette carte sur cette tireuse
        # / Find the open session for this card on this tap
        session = (
            RfidSession.objects.filter(
                tireuse_bec=tireuse, uid=uid, ended_at__isnull=True
            )
            .order_by("-started_at")
            .first()
        )
        if not session:
            # card_removed sans session = carte refusée retirée OU session déjà fermée
            # par pour_end (cas maintenance : le Pi envoie pour_end puis card_removed).
            # / card_removed without session = refused card removed OR session already
            # closed by pour_end (maintenance case: Pi sends pour_end then card_removed).
            if event_type == "card_removed":
                reset_payload = _construire_payload_session(tireuse, None)
                # Si la tireuse est hors service, le kiosk doit rester en mode maintenance
                # et non revenir à l'état "En attente" standard.
                # / If the tap is out of service, the kiosk must stay in maintenance mode
                # rather than returning to the standard "Waiting" state.
                if not tireuse.enabled:
                    reset_payload["maintenance"] = True
                    reset_payload["message"] = "En Maintenance"
                logger.info(
                    f"WS_PUSH card_removed sans session (reset kiosk): uid={uid} "
                    f"maintenance={not tireuse.enabled}"
                )
                _push_ws_kiosk(tireuse, reset_payload)
                return Response({"status": "ok", "message": "No session — kiosk reset."})
            return Response(
                {"status": "error", "message": "No open session for this card."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Variable pour la facturation (uniquement remplie par pour_end)
        # / Variable for billing (only set by pour_end)
        resultat_facturation = None

        # Traiter selon le type d'événement / Process by event type
        if event_type == "pour_update":
            session.volume_end_ml = volume_ml
            session.volume_delta_ml = volume_ml
            session.dernier_volume_ml = volume_ml
            session.save(
                update_fields=[
                    "volume_end_ml",
                    "volume_delta_ml",
                    "dernier_volume_ml",
                ]
            )

        elif event_type == "pour_start":
            session.volume_start_ml = volume_ml
            session.save(update_fields=["volume_start_ml"])

        elif event_type in ("pour_end", "card_removed"):
            session.close_with_volume(float(volume_ml))

            # Décrémenter le réservoir / Decrement reservoir
            if volume_ml > 0:
                tireuse.reservoir_ml = max(
                    Decimal("0"),
                    tireuse.reservoir_ml - Decimal(str(float(volume_ml))),
                )
                tireuse.save(update_fields=["reservoir_ml"])

            # --- Facturation (sauf maintenance) ---
            # / Billing (except maintenance)
            if not session.is_maintenance and volume_ml > 0 and tireuse.fut_actif:
                from controlvanne.billing import (
                    obtenir_contexte_cashless,
                    facturer_tirage,
                )
                from fedow_core.exceptions import SoldeInsuffisant

                contexte = obtenir_contexte_cashless(session.carte)
                if contexte:
                    try:
                        resultat_facturation = facturer_tirage(
                            session=session,
                            tireuse=tireuse,
                            carte=session.carte,
                            volume_ml=volume_ml,
                            contexte_cashless=contexte,
                            ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                        )
                    except SoldeInsuffisant:
                        # Le solde a changé entre authorize et pour_end (race condition).
                        # La bière est déjà servie — on log l'erreur mais on ne bloque pas.
                        # / Balance changed between authorize and pour_end (race condition).
                        # Beer is already served — log the error but don't block.
                        logger.error(
                            f"SoldeInsuffisant au pour_end: carte={uid} "
                            f"tireuse={tireuse.nom_tireuse} volume={volume_ml}ml"
                        )

            logger.info(
                f"Event {event_type}: carte={uid} tireuse={tireuse.nom_tireuse} "
                f"volume={volume_ml}ml session={session.pk} "
                f"facture={'oui' if resultat_facturation else 'non'}"
            )

        # Push WebSocket vers le kiosk selon le type d'événement
        # / WebSocket push to kiosk based on event type
        if event_type == "pour_start":
            _push_ws_kiosk(
                tireuse,
                _construire_payload_session(
                    tireuse,
                    session,
                    vanne_ouverte=True,
                    message="Tirage en cours",
                ),
            )
        elif event_type == "pour_update":
            # Estimer le solde restant : solde_cascade_total - coût_du_volume_déjà_servi
            # Le débit réel se fait au pour_end — ici on affiche une estimation visuelle.
            # / Estimate remaining balance: total_cascade_balance - cost_of_volume_served
            # The actual debit happens at pour_end — here we show a visual estimate.
            balance_estimee = None
            if not session.is_maintenance and tireuse.prix_litre > 0:
                from controlvanne.billing import (
                    obtenir_contexte_cashless as _ctx,
                    calculer_solde_total_cascade,
                )
                ctx = _ctx(session.carte)
                if ctx:
                    solde_db = calculer_solde_total_cascade(
                        ctx["wallet_client"], ctx["cascade_assets"]
                    )
                    cout_volume = Decimal(str(volume_ml)) / 1000 * tireuse.prix_litre * 100
                    solde_estime = max(Decimal("0"), Decimal(str(solde_db)) - cout_volume)
                    balance_estimee = f"{float(solde_estime) / 100:.2f}"
            extras_update = {"vanne_ouverte": True, "message": "Tirage en cours"}
            if balance_estimee is not None:
                extras_update["balance"] = balance_estimee
            _push_ws_kiosk(
                tireuse,
                _construire_payload_session(tireuse, session, **extras_update),
            )
        elif event_type in ("pour_end", "card_removed"):
            # Calculer le solde restant apres facturation (si disponible)
            # / Compute remaining balance after billing (if available)
            solde_apres = None
            if resultat_facturation:
                from controlvanne.billing import (
                    obtenir_contexte_cashless as _ctx,
                    calculer_solde_total_cascade,
                )

                ctx = _ctx(session.carte)
                if ctx:
                    solde_apres = calculer_solde_total_cascade(
                        ctx["wallet_client"], ctx["cascade_assets"]
                    )

            extras_fin = {
                "session_done": True,
                "message": f"Fin de service — {float(volume_ml):.0f} ml",
            }
            if solde_apres is not None:
                extras_fin["balance"] = f"{solde_apres / 100:.2f}"

            payload_fin = _construire_payload_session(tireuse, session, **extras_fin)
            logger.info(
                f"WS_PUSH pour_end/card_removed: event={event_type} "
                f"present={payload_fin.get('present')} "
                f"session_done={payload_fin.get('session_done')} "
                f"ended_at={session.ended_at} "
                f"volume_ml={payload_fin.get('volume_ml')} "
                f"uid={uid}"
            )
            _push_ws_kiosk(tireuse, payload_fin)

        response_data = {
            "status": "ok",
            "event_type": event_type,
            "session_id": session.pk,
            "volume_ml": float(volume_ml),
        }
        if resultat_facturation:
            response_data["montant_centimes"] = resultat_facturation["montant_centimes"]
            response_data["transaction_id"] = resultat_facturation["transaction"].id

        return Response(response_data)


# ──────────────────────────────────────────────────────────────────────
# AuthKioskView — POST token API → cookie session Django
# ──────────────────────────────────────────────────────────────────────


class AuthKioskView(APIView):
    """
    POST /controlvanne/auth-kiosk/
    Le Pi envoie sa clé API dans le header Authorization.
    Django vérifie la clé, crée une session, renvoie Set-Cookie.
    Le Pi récupère le cookie et lance Chromium avec ce cookie.
    / The Pi sends its API key in the Authorization header.
    Django verifies the key, creates a session, returns Set-Cookie.
    The Pi retrieves the cookie and launches Chromium with it.

    LOCALISATION : controlvanne/viewsets.py

    Le token ne doit pas fuiter en query string (logs, referer, historique navigateur).
    / The token must not leak in query string (logs, referer, browser history).
    """

    permission_classes = [HasTireuseAccess]

    def post(self, request):
        # La permission HasTireuseAccess a déjà vérifié la clé API
        # Si on arrive ici, l'accès est autorisé (clé valide ou admin session)
        # / HasTireuseAccess already verified the API key
        # If we reach here, access is authorized (valid key or admin session)

        # Créer une session Django anonyme (pas de User associé)
        # Le Pi utilise cette session pour le WebSocket et le kiosk
        # / Create an anonymous Django session (no User attached)
        # The Pi uses this session for WebSocket and kiosk
        if not request.session.session_key:
            request.session.create()

        # Marquer la session comme authentifiée pour le kiosk
        # / Mark the session as authenticated for the kiosk
        request.session["controlvanne_authenticated"] = True
        request.session.save()

        # Générer un token à usage unique pour l'auth kiosk sans injection de cookie
        # Le Pi lance Chromium sur l'URL /controlvanne/kiosk-token/<token>/
        # Django valide le token, pose le cookie de session via HTTP, redirige vers le kiosk
        # / Generate a one-time token for kiosk auth without cookie injection
        # The Pi opens Chromium on /controlvanne/kiosk-token/<token>/
        # Django validates the token, sets session cookie via HTTP, redirects to kiosk
        import uuid as uuid_module
        from django.core.cache import cache

        kiosk_token = str(uuid_module.uuid4())
        # Stocker le token dans le cache comme autorisation valide (TTL 5 minutes)
        # La valeur True indique simplement que le token est valide.
        # Chromium navigue vers /kiosk-token/<token>/ → Django valide, marque la session, redirige.
        # / Store the token in cache as a valid authorization (TTL 5 minutes)
        # The True value simply indicates the token is valid.
        # Chromium navigates to /kiosk-token/<token>/ → Django validates, marks session, redirects.
        cache.set(f"kiosk_token:{kiosk_token}", True, timeout=300)

        return Response(
            {
                "status": "ok",
                "message": "Session created. Use the sessionid cookie for kiosk.",
                "session_key": request.session.session_key,
                "kiosk_token": kiosk_token,
            }
        )


# ──────────────────────────────────────────────────────────────────────
# KioskTokenView — échange token à usage unique → cookie session HTTP
# / KioskTokenView — exchange one-time token → HTTP session cookie
# ──────────────────────────────────────────────────────────────────────


class KioskTokenView(APIView):
    """
    GET /controlvanne/kiosk-token/<token>/?next=<kiosk_url>
    Échange un token à usage unique contre un cookie de session Django.
    Django pose le cookie via Set-Cookie dans la réponse HTTP → Chromium le stocke nativement.
    Redirige ensuite vers l'URL kiosk réelle.
    / Exchanges a one-time token for a Django session cookie.
    Django sets the cookie via Set-Cookie in the HTTP response → Chromium stores it natively.
    Then redirects to the actual kiosk URL.

    LOCALISATION : controlvanne/viewsets.py

    Pas de permission DRF — le token est la preuve d'authenticité.
    / No DRF permission — the token is the proof of authenticity.
    """

    permission_classes = []
    authentication_classes = []

    def get(self, request, token):
        from django.core.cache import cache
        from django.http import HttpResponseRedirect, HttpResponseForbidden

        # Valider et consommer le token (usage unique)
        # / Validate and consume the token (one-time use)
        cache_key = f"kiosk_token:{token}"
        token_valide = cache.get(cache_key)

        if not token_valide:
            return HttpResponseForbidden("Token invalide ou expiré. / Invalid or expired token.")

        # Consommer le token immédiatement (usage unique)
        # / Consume the token immediately (one-time use)
        cache.delete(cache_key)

        # Marquer la session de CE navigateur (Chromium) comme authentifiée pour le kiosk
        # Django's SessionMiddleware enverra Set-Cookie: sessionid=... dans la réponse HTTP
        # Chromium stocke ce cookie nativement — plus besoin d'injection SQLite
        # / Mark THIS browser's (Chromium's) session as authenticated for kiosk
        # Django's SessionMiddleware will send Set-Cookie: sessionid=... in the HTTP response
        # Chromium stores this cookie natively — no more SQLite injection needed
        request.session["controlvanne_authenticated"] = True
        request.session.save()

        # Retourner une page HTML avec meta-refresh plutôt qu'un 302
        # Avec un 302, certaines versions de Chromium ne transmettent pas le Set-Cookie
        # dans la requête suivante. Avec un 200 + meta-refresh, le cookie est d'abord
        # stocké, puis la navigation vers next_url l'envoie correctement.
        # / Return an HTML page with meta-refresh instead of a 302
        # With a 302, some Chromium versions don't transmit the Set-Cookie
        # in the next request. With 200 + meta-refresh, the cookie is stored first,
        # then the navigation to next_url sends it correctly.
        from django.http import HttpResponse

        next_url = request.GET.get("next", "/controlvanne/kiosk/")
        html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url={next_url}">
  <title>Authentification kiosk…</title>
</head>
<body>
  <script>window.location.replace('{next_url}');</script>
  <p>Redirection en cours… <a href="{next_url}">Cliquez ici si la page ne se charge pas.</a></p>
</body>
</html>"""
        return HttpResponse(html, content_type="text/html")


# ──────────────────────────────────────────────────────────────────────
# KioskViewSet — pages kiosk temps réel pour les écrans Pi
# / KioskViewSet — real-time kiosk pages for Pi screens
# ──────────────────────────────────────────────────────────────────────


def _verifier_authentification_kiosk(request):
    """
    Vérifie que l'utilisateur est authentifié pour le kiosk.
    Trois moyens d'accès :
      1. session kiosk (cookie sessionid déjà posé)
      2. token à usage unique dans ?kiosk_token=<token> (premier lancement Pi)
      3. admin du tenant connecté
    / Checks that the user is authenticated for the kiosk.
    Three access methods:
      1. kiosk session (sessionid cookie already set)
      2. one-time token in ?kiosk_token=<token> (first Pi launch)
      3. logged-in tenant admin

    LOCALISATION : controlvanne/viewsets.py

    :param request: HttpRequest
    :return: True si autorisé, False sinon
    """
    from django.db import connection

    # Moyen 1 : session kiosk (cookie sessionid déjà présent dans le navigateur)
    # / Method 1: kiosk session (sessionid cookie already present in browser)
    est_kiosk = request.session.get("controlvanne_authenticated")
    if est_kiosk:
        return True

    # Moyen 2 : token à usage unique dans le query string (premier lancement Chromium)
    # Le Pi construit l'URL kiosk avec ?kiosk_token=<uuid> — Django valide, consomme le token,
    # marque la session. Django's SessionMiddleware pose Set-Cookie dans la réponse kiosk.
    # Les rechargements suivants de Chromium utilisent le cookie sessionid.
    # / Method 2: one-time token in query string (first Chromium launch)
    # Pi builds kiosk URL with ?kiosk_token=<uuid> — Django validates, consumes token,
    # marks session. Django's SessionMiddleware sets Set-Cookie in the kiosk response.
    # Subsequent Chromium reloads use the sessionid cookie.
    kiosk_token = request.GET.get("kiosk_token")
    if kiosk_token:
        from django.core.cache import cache
        cache_key = f"kiosk_token:{kiosk_token}"
        token_valide = cache.get(cache_key)
        if token_valide:
            cache.delete(cache_key)
            request.session["controlvanne_authenticated"] = True
            request.session.save()
            return True

    # Moyen 3 : admin du tenant connecté
    # / Method 3: logged-in tenant admin
    utilisateur = request.user
    if utilisateur and utilisateur.is_authenticated:
        est_admin = utilisateur.is_tenant_admin(connection.tenant)
        if est_admin:
            return True

    return False


class KioskViewSet(viewsets.ViewSet):
    """
    Pages kiosk pour les écrans des tireuses connectées.
    / Kiosk pages for connected tap screens.

    LOCALISATION : controlvanne/viewsets.py

    Deux vues :
    - list()     → GET /controlvanne/kiosk/
                   Grille de toutes les tireuses actives.
                   WebSocket : /ws/rfid/all/ (toutes les mises à jour).
    - retrieve() → GET /controlvanne/kiosk/<uuid>/
                   Écran dédié à une seule tireuse.
                   WebSocket : /ws/rfid/<uuid>/ (mises à jour ciblées).
                   Inclut le panneau simulateur Pi en mode DEMO.

    Auth : session kiosk (POST /controlvanne/auth-kiosk/) ou admin tenant.
    / Auth: kiosk session (POST /controlvanne/auth-kiosk/) or tenant admin.
    """

    # Pas de permission DRF — on vérifie manuellement via _verifier_authentification_kiosk
    # car le kiosk n'utilise pas d'API key, mais un cookie de session.
    # / No DRF permission — manual check via _verifier_authentification_kiosk
    # because the kiosk uses a session cookie, not an API key.
    permission_classes = []

    def list(self, request):
        """
        GET /controlvanne/kiosk/
        Grille de toutes les tireuses actives.
        Le WebSocket se connecte à /ws/rfid/all/ pour recevoir les mises à jour.
        / Grid of all active taps.
        WebSocket connects to /ws/rfid/all/ to receive updates.

        LOCALISATION : controlvanne/viewsets.py
        """
        from django.shortcuts import render
        from django.http import HttpResponseForbidden
        from BaseBillet.models import Configuration

        if not _verifier_authentification_kiosk(request):
            return HttpResponseForbidden("Not authenticated for kiosk.")

        toutes_les_tireuses_actives = TireuseBec.objects.filter(
            enabled=True,
        ).order_by("nom_tireuse")

        config = Configuration.get_solo()

        context = {
            "becs": toutes_les_tireuses_actives,
            "config": config,
            "slug_focus": "all",
        }

        return render(request, "controlvanne/kiosk_list.html", context)

    def retrieve(self, request, pk=None):
        """
        GET /controlvanne/kiosk/<uuid>/
        Écran dédié à une seule tireuse avec jauge, prix, et état temps réel.
        Le WebSocket se connecte à /ws/rfid/<uuid>/ pour les mises à jour ciblées.
        En mode DEMO, affiche le panneau simulateur Pi (boutons carte + slider débit).
        / Screen dedicated to a single tap with gauge, prices, and real-time state.
        WebSocket connects to /ws/rfid/<uuid>/ for targeted updates.
        In DEMO mode, shows the Pi simulator panel (card buttons + flow slider).

        LOCALISATION : controlvanne/viewsets.py
        """
        from django.conf import settings
        from django.shortcuts import render, get_object_or_404
        from django.http import HttpResponseForbidden
        from django.utils.translation import gettext_lazy as _
        from BaseBillet.models import Configuration

        if not _verifier_authentification_kiosk(request):
            return HttpResponseForbidden("Not authenticated for kiosk.")

        tireuse = get_object_or_404(TireuseBec, uuid=pk)
        config = Configuration.get_solo()

        context = {
            "tireuse": tireuse,
            "config": config,
            "slug_focus": str(pk),
        }

        # Mode demo : injecter les tags NFC simulés pour le panneau debug
        # / Demo mode: inject simulated NFC tags for the debug panel
        if getattr(settings, "DEMO", False):
            context["demo_tags"] = [
                {"tag_id": settings.DEMO_TAGID_CLIENT1, "name": _("Carte client 1")},
                {"tag_id": settings.DEMO_TAGID_CLIENT2, "name": _("Carte client 2")},
                {"tag_id": settings.DEMO_TAGID_CLIENT3, "name": _("Carte client 3")},
                {"tag_id": settings.DEMO_TAGID_CLIENT4, "name": _("Carte inconnue")},
            ]

        return render(request, "controlvanne/kiosk_detail.html", context)
