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
                    "seuil_mini_ml": float(tireuse.seuil_mini_ml),
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

        if not tireuse.enabled:
            return Response({"authorized": False, "message": "Tap is disabled."})

        # Chercher la carte NFC / Find the NFC card
        from QrcodeCashless.models import CarteCashless

        carte = CarteCashless.objects.filter(tag_id=uid).first()
        if not carte:
            return Response({"authorized": False, "message": "Unknown card."})

        # Vérifier si c'est une carte de maintenance / Check if it's a maintenance card
        carte_maintenance = None
        is_maintenance = False
        try:
            carte_maintenance = carte.carte_maintenance
            is_maintenance = True
        except CarteMaintenance.DoesNotExist:
            pass

        # --- Maintenance : pas de facturation ---
        # / Maintenance: no billing
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
            calculer_volume_autorise_ml,
        )
        from fedow_core.services import WalletService

        contexte = obtenir_contexte_cashless(carte)
        if not contexte:
            return Response(
                {
                    "authorized": False,
                    "message": "No cashless asset configured for this venue.",
                }
            )

        solde_centimes = WalletService.obtenir_solde(
            contexte["wallet_client"], contexte["asset_tlf"]
        )

        prix_litre = tireuse.prix_litre
        if prix_litre <= 0:
            return Response(
                {
                    "authorized": False,
                    "message": "No price configured for the active keg.",
                }
            )

        # Réservoir disponible (avec ou sans réserve)
        # / Available reservoir (with or without reserve)
        reservoir_disponible = float(tireuse.reservoir_ml)
        if tireuse.appliquer_reserve:
            reservoir_disponible = max(
                0, reservoir_disponible - float(tireuse.seuil_mini_ml)
            )

        allowed_ml = calculer_volume_autorise_ml(
            solde_centimes, prix_litre, reservoir_disponible
        )

        if allowed_ml <= 0:
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

        # Le push WebSocket est géré par le signal post_save de TireuseBec
        # / WebSocket push is handled by TireuseBec's post_save signal

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

        return Response(
            {
                "status": "ok",
                "message": "Session created. Use the sessionid cookie for kiosk.",
                "session_key": request.session.session_key,
            }
        )


# ──────────────────────────────────────────────────────────────────────
# KioskViewSet — pages kiosk temps réel pour les écrans Pi
# / KioskViewSet — real-time kiosk pages for Pi screens
# ──────────────────────────────────────────────────────────────────────


def _verifier_authentification_kiosk(request):
    """
    Vérifie que l'utilisateur est authentifié pour le kiosk.
    Deux moyens d'accès : session kiosk (POST /auth-kiosk/) ou admin tenant.
    / Checks that the user is authenticated for the kiosk.
    Two access methods: kiosk session (POST /auth-kiosk/) or tenant admin.

    LOCALISATION : controlvanne/viewsets.py

    :param request: HttpRequest
    :return: True si autorisé, False sinon
    """
    from django.db import connection

    # Moyen 1 : session kiosk (créée par POST /controlvanne/auth-kiosk/)
    # / Method 1: kiosk session (created by POST /controlvanne/auth-kiosk/)
    est_kiosk = request.session.get("controlvanne_authenticated")
    if est_kiosk:
        return True

    # Moyen 2 : admin du tenant connecté
    # / Method 2: logged-in tenant admin
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
