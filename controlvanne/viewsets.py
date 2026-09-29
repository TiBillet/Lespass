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

from django.db import connection
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle

from controlvanne.acces import peut_voir_les_kiosks
from controlvanne.groupes_ws import pousser_aux_kiosks, uuid_du_lieu_courant
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

# gettext (et pas gettext_lazy) : les messages partent en JSON sur le WebSocket,
# et un texte « lazy » ne se sérialise pas en JSON.
# / gettext (not gettext_lazy): messages are sent as JSON over the WebSocket.
from django.utils.translation import gettext  # noqa: E402

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

    Les groupes sont nommés par lieu (controlvanne/groupes_ws.py) : un message
    ne sort jamais du lieu de la requête.
    / Groups are named per venue: a message never leaves the request's venue.

    :param tireuse: TireuseBec — la tireuse concernée
    :param payload: dict — données à envoyer au kiosk (format ws_payloads)
    """
    pousser_aux_kiosks(tireuse.uuid, payload, uuid_du_lieu_courant())

def _push_refus(tireuse, message, solde_centimes=None):
    """
    Pousse un message de refus minimal vers le kiosk via WebSocket.
    / Pushes a minimal refusal message to the kiosk via WebSocket.

    LOCALISATION : controlvanne/viewsets.py

    Utilisé pour tous les cas où authorize() refuse une carte.
    present=True + authorized=False : ecran_tireuse.js affiche l'écran « Carte
    refusée », tant que la carte est posée (retour en veille au retrait).
    Message minimal : le kiosk a déjà l'état complet de la tireuse (pas d'appel
    à _construire_payload_session, pas de requête SQL en plus).
    / present=True + authorized=False: the kiosk shows the refusal screen while
    the card is present. Minimal message, no extra SQL query.

    :param tireuse: TireuseBec — la tireuse concernée
    :param message: str — message lisible par le client (déjà traduit)
    :param solde_centimes: int ou None — solde de la carte, affiché s'il est connu
    """
    payload = {
        "tireuse_bec_uuid": str(tireuse.uuid),
        "authorized": False,
        "vanne_ouverte": False,
        "present": True,
        "message": message,
    }
    if solde_centimes is not None:
        payload.update(_champs_du_solde(solde_centimes, tireuse.prix_litre))
    _push_ws_kiosk(tireuse, payload)


def _champs_du_solde(solde_centimes, prix_litre):
    """
    Champs « solde » du message WebSocket, calculés et formatés par le serveur.
    / "Balance" fields of the WebSocket message, computed and formatted server-side.

    LOCALISATION : controlvanne/viewsets.py

    - balance       : solde en euros, texte « 14.10 » (gardé pour compatibilité)
    - solde_affiche : solde prêt à afficher, « 14,10 € » (langue active)
    - nombre_verres : verres de 25 cl que le solde permet (None si pas de prix)
    Le JS du kiosk écrit ces valeurs telles quelles (audit 2026-09-26, point 2.3).
    / The kiosk JS writes these values as they are.

    :param solde_centimes: int
    :param prix_litre: Decimal
    :return: dict
    """
    from controlvanne.billing import calculer_nombre_de_verres, formater_euros

    return {
        "balance": f"{int(solde_centimes) / 100:.2f}",
        "solde_affiche": formater_euros(solde_centimes),
        "nombre_verres": calculer_nombre_de_verres(solde_centimes, prix_litre),
    }


def _cle_de_cache_du_solde(session):
    """
    Clé de cache du solde lu à l'authorize, pour une session.
    Le lieu fait partie de la clé (règle multi-tenant).
    / Cache key of the balance read at authorize; includes the venue.
    """
    return f"controlvanne:solde_authorize:{connection.tenant.pk}:{session.pk}"


def _lire_le_solde_de_la_carte(carte):
    """
    Solde total de la carte (cascade TNF → TLF → FED), en centimes.
    / Card total balance (TNF → TLF → FED cascade), in cents.

    :param carte: CarteCashless
    :return: int, ou None si la carte n'a pas de contexte cashless
    """
    from controlvanne.billing import calculer_solde_total_cascade, obtenir_contexte_cashless

    contexte = obtenir_contexte_cashless(carte)
    if not contexte:
        return None
    return calculer_solde_total_cascade(
        contexte["wallet_client"], contexte["cascade_assets"]
    )


# Durée de vie du solde gardé en cache : largement plus qu'un service
# / Lifetime of the cached balance: far longer than one pour
DUREE_CACHE_SOLDE_SECONDES = 60 * 60 * 6


def _construire_payload_session(
    tireuse,
    session,
    prix_litre=None,
    solde_centimes=None,
    montant_servi_centimes=None,
    **extras,
):
    """
    Construit le payload WebSocket pour un événement de session NFC.
    / Builds the WebSocket payload for an NFC session event.

    LOCALISATION : controlvanne/viewsets.py

    Les montants d'argent sont calculés ICI, avec les mêmes fonctions que la
    facture (controlvanne/billing.py) : l'écran ne calcule plus rien.
    - prix_servi_centimes / prix_servi_affiche : prix du volume servi ;
    - balance / solde_affiche / nombre_verres : si solde_centimes est donné.
    / Money amounts are computed HERE with the bill's functions.

    :param tireuse: TireuseBec
    :param session: RfidSession (ou None)
    :param prix_litre: Decimal — passé par l'appelant s'il l'a déjà lu (évite
                       deux requêtes SQL de plus), sinon lu sur la tireuse
    :param solde_centimes: int ou None — solde de la carte à afficher
    :param montant_servi_centimes: int ou None — montant réellement facturé
                       (fin de service) ; sinon calculé depuis le volume
    :param extras: champs supplémentaires à fusionner (vanne_ouverte, session_done, etc.)
    :return: dict payload
    """
    from controlvanne.billing import calculer_montant_centimes, formater_euros

    if prix_litre is None:
        prix_litre = tireuse.prix_litre

    # Prénom du client si la carte est liée à un compte. Carte anonyme → chaîne vide.
    # Affiché sur l'écran de la tireuse : « Bonjour Camille », « Merci Camille ! ».
    # / Customer first name if the card is linked to an account. Anonymous card → empty string.
    prenom_du_client = ""
    carte_de_la_session = session.carte if session else None
    if carte_de_la_session and carte_de_la_session.user and carte_de_la_session.user.first_name:
        prenom_du_client = carte_de_la_session.user.first_name

    payload = {
        "tireuse_bec": tireuse.nom_tireuse,
        "tireuse_bec_uuid": str(tireuse.uuid),
        "liquid_label": tireuse.liquid_label,
        "reservoir_ml": float(tireuse.reservoir_ml),
        "reservoir_max_ml": tireuse.reservoir_max_ml,
        "prix_litre": str(prix_litre),
        "present": bool(session and session.ended_at is None),
        "authorized": bool(session and session.authorized),
        "vanne_ouverte": False,
        "volume_ml": float(session.dernier_volume_ml if session else 0),
        "uid": session.uid if session else None,
        "prenom": prenom_du_client,
        "message": "",
    }
    # Carte maintenance → flag maintenance
    # / Maintenance card → maintenance flag
    if session and session.is_maintenance:
        payload["maintenance"] = True

    # Prix du volume servi (pas pour un rinçage de maintenance)
    # / Price of the served volume (not for a maintenance rinse)
    if session and not session.is_maintenance:
        if montant_servi_centimes is None:
            montant_servi_centimes = calculer_montant_centimes(
                payload["volume_ml"], prix_litre
            )
        payload["prix_servi_centimes"] = montant_servi_centimes
        payload["prix_servi_affiche"] = formater_euros(montant_servi_centimes)

    # Solde de la carte, s'il est connu / Card balance, if known
    if solde_centimes is not None:
        payload.update(_champs_du_solde(solde_centimes, prix_litre))

    # Fusionner les champs supplémentaires (vanne_ouverte, balance, message, etc.)
    # / Merge extra fields (vanne_ouverte, balance, message, etc.)
    payload.update(extras)
    return payload


def _cloturer_session_et_facturer(tireuse, session, volume_ml, ip="0.0.0.0"):
    """
    Ferme une session NFC et facture le volume servi.
    / Closes an NFC session and bills the served volume.

    LOCALISATION : controlvanne/viewsets.py

    Utilisée par :
    - event() au pour_end / card_removed (fin normale d'un service) ;
    - authorize() pour les sessions orphelines : une session restée ouverte
      parce que card_removed n'est jamais arrivé (Pi redémarré, coupure
      réseau, page du simulateur rechargée).
    / Used by event() at pour_end / card_removed, and by authorize() for
    orphan sessions left open because card_removed never arrived.

    ÉTAPES (dans une seule transaction) :
    1. Verrouille la session et vérifie qu'elle est encore ouverte.
    2. La ferme avec le volume servi.
    3. Retire ce volume du réservoir de la tireuse.
    4. Facture le tirage (sauf maintenance, volume nul ou pas de fût).

    :param tireuse: TireuseBec
    :param session: RfidSession — la session à fermer
    :param volume_ml: Decimal — volume total servi pendant la session
    :param ip: str — adresse IP pour la trace de facturation
    :return: (session fermée, résultat de facturation ou None).
             (None, None) si un événement concurrent l'avait déjà fermée.
    """
    resultat_facturation = None

    # Verrou anti-double-facturation (fix review 2026-07-06, C1) :
    # deux événements concurrents (pour_end rejoué par le Pi sur
    # timeout réseau, ou pour_end + card_removed chevauchés)
    # lisaient la même session ouverte et facturaient DEUX FOIS le
    # même tirage. On verrouille la ligne de session et on
    # re-vérifie qu'elle est toujours ouverte : l'appel concurrent
    # sort proprement sans re-facturer. Fermeture, réservoir et
    # facturation partagent désormais la même transaction (fix I1).
    # / Anti-double-billing lock (2026-07-06 review, C1): two
    # concurrent events (pour_end retried by the Pi on network
    # timeout, or overlapping pour_end + card_removed) both read
    # the same open session and billed the SAME pour TWICE. Lock
    # the session row and re-check it is still open: the concurrent
    # call exits cleanly without billing again. Close, reservoir
    # and billing now share one transaction (I1 fix).
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        session_verrouillee = (
            RfidSession.objects.select_for_update()
            .filter(pk=session.pk, ended_at__isnull=True)
            .first()
        )
        if session_verrouillee is None:
            # Un événement concurrent a déjà fermé (et facturé) la
            # session : on ne refait rien.
            # / A concurrent event already closed (and billed) the
            # session: do nothing again.
            return None, None
        session = session_verrouillee

        session.close_with_volume(float(volume_ml))

        # Décrémenter le réservoir, directement en SQL :
        #   reservoir_ml = GREATEST(reservoir_ml - volume, 0)
        # La soustraction se fait dans la base, sur la valeur À JOUR. Avant, on
        # lisait tireuse.reservoir_ml (sans verrou) puis on réécrivait le
        # résultat : deux fermetures simultanées (session orpheline + pour_end)
        # perdaient une décrémentation (audit 2026-09-26, point 2.2).
        # update() ne déclenche pas post_save : on envoie donc l'état de la
        # tireuse aux kiosks nous-mêmes (à la fin de la transaction).
        # / Decrement the reservoir in SQL, on the CURRENT value (no stale read).
        # update() skips post_save: push the tap state ourselves (on commit).
        if volume_ml > 0 and not session.is_maintenance:
            from django.db.models import DecimalField, F, Value
            from django.db.models.functions import Greatest

            from controlvanne.signals import pousser_etat_de_la_tireuse

            volume_a_retirer_ml = Decimal(str(float(volume_ml)))
            zero_ml = Value(
                Decimal("0.00"),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
            TireuseBec.objects.filter(pk=tireuse.pk).update(
                reservoir_ml=Greatest(F("reservoir_ml") - volume_a_retirer_ml, zero_ml)
            )
            tireuse.refresh_from_db(fields=["reservoir_ml"])
            pousser_etat_de_la_tireuse(tireuse)

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
                        ip=ip,
                    )
                except SoldeInsuffisant:
                    # Le solde a changé entre authorize et pour_end (race
                    # condition). La bière est déjà servie — on log sans
                    # bloquer. L'atomic interne de facturer_tirage
                    # (savepoint) a annulé la facturation ; la fermeture
                    # de session et le réservoir sont conservés (réalité
                    # physique).
                    # / Balance changed between authorize and pour_end.
                    # Beer already served — log without blocking. The
                    # inner atomic of facturer_tirage (savepoint) rolled
                    # back the billing; session close and reservoir are
                    # kept (physical reality).
                    logger.error(
                        f"SoldeInsuffisant à la clôture: carte={session.uid} "
                        f"tireuse={tireuse.nom_tireuse} volume={volume_ml}ml"
                    )

    return session, resultat_facturation


def _cloturer_sessions_orphelines(tireuse, ip="0.0.0.0"):
    """
    Ferme et facture les sessions restées ouvertes sur une tireuse.
    / Closes and bills the sessions left open on a tap.

    LOCALISATION : controlvanne/viewsets.py

    Appelée par authorize(), AVANT d'ouvrir une nouvelle session.
    Un nouveau badge sur une tireuse veut dire que la carte précédente
    n'est plus là : sa session aurait dû être fermée par card_removed.
    Ce message peut manquer : Pi redémarré ou coupure réseau pendant un
    service, page du simulateur rechargée avec une carte posée.
    / Called by authorize() BEFORE opening a new session. A new badge means
    the previous card is gone; its card_removed may never have arrived.

    Sans cette fermeture :
    - le kiosk s'ouvre sur l'écran de service, comme si une carte était posée
      (le consumer envoie present=true tant qu'une session est ouverte) ;
    - le volume déjà versé n'est jamais facturé (facturation au pour_end).

    On facture le dernier volume connu (dernier_volume_ml, reçu au dernier
    pour_update). Le volume versé après ce dernier message est perdu.
    / We bill the last known volume (last pour_update).

    :param tireuse: TireuseBec
    :param ip: str — adresse IP pour la trace de facturation
    :return: int — nombre de sessions fermées
    """
    sessions_restees_ouvertes = RfidSession.objects.filter(
        tireuse_bec=tireuse,
        ended_at__isnull=True,
    ).select_related("carte")

    nombre_de_sessions_fermees = 0
    for session_orpheline in sessions_restees_ouvertes:
        volume_du_dernier_message_ml = session_orpheline.dernier_volume_ml or Decimal("0")
        session_fermee, resultat_facturation = _cloturer_session_et_facturer(
            tireuse,
            session_orpheline,
            volume_du_dernier_message_ml,
            ip=ip,
        )
        if session_fermee is None:
            # Fermée entre-temps par un autre appel : rien à faire
            # / Closed meanwhile by another call: nothing to do
            continue
        nombre_de_sessions_fermees += 1
        logger.warning(
            f"Session orpheline fermée au badge suivant : session={session_fermee.pk} "
            f"tireuse={tireuse.nom_tireuse} carte={session_fermee.uid} "
            f"volume={float(volume_du_dernier_message_ml):.0f}ml "
            f"facture={'oui' if resultat_facturation else 'non'}"
        )
    return nombre_de_sessions_fermees


def _la_cle_appartient_a_la_tireuse(request, tireuse):
    """
    Vérifie que la clé API de la requête est celle du terminal de CETTE tireuse.
    / Checks that the request's API key is THIS tap's terminal key.

    LOCALISATION : controlvanne/viewsets.py

    Sans ce contrôle, n'importe quelle clé de tireuse du lieu pouvait agir sur
    n'importe quelle tireuse, en envoyant un autre tireuse_uuid (audit
    2026-09-26, point 1.4).
    / Without it, any tap key of the venue could act on any tap.

    - Admin du lieu connecté (simulateur DEMO, debug) : pas de clé, accès permis
      (HasTireuseAccess a déjà vérifié qu'il est admin du lieu).
    - Clé API : son compte doit être le compte du terminal de la tireuse
      (Terminal.term_user, posé par l'appairage dans discovery/views.py).
    / Logged-in admin: allowed. API key: its account must be the tap terminal's.

    :param request: Request DRF (request.tireuse_api_key posé par HasTireuseAccess)
    :param tireuse: TireuseBec
    :return: bool
    """
    cle_de_la_requete = getattr(request, "tireuse_api_key", None)
    if cle_de_la_requete is None:
        return True

    terminal_de_la_tireuse = tireuse.terminal
    if terminal_de_la_tireuse is None or terminal_de_la_tireuse.term_user_id is None:
        return False
    return terminal_de_la_tireuse.term_user_id == cle_de_la_requete.user_id


def _refus_cle_d_une_autre_tireuse(tireuse):
    """
    Réponse 403 quand la clé n'est pas celle de la tireuse visée.
    / 403 response when the key is not the target tap's key.
    """
    logger.warning(
        f"Clé API refusée : elle n'appartient pas au terminal de la tireuse "
        f"{tireuse.nom_tireuse} ({tireuse.uuid})"
    )
    return Response(
        {"authorized": False, "message": "This API key does not belong to this tap."},
        status=status.HTTP_403_FORBIDDEN,
    )


class AuthorizeTireuseThrottle(SimpleRateThrottle):
    """
    Limite les appels à authorize : 30 par minute et par clé API.
    / Limits authorize calls: 30 per minute per API key.

    LOCALISATION : controlvanne/viewsets.py

    Pourquoi : authorize renvoie le solde d'une carte. Sans limite, une clé
    volée permettrait d'essayer des UID de carte en masse (audit 2026-09-26,
    point 1.6). Une vraie tireuse ne voit jamais 30 badges par minute.
    / authorize returns a card balance: without a limit, a stolen key could
    try card UIDs in bulk. A real tap never sees 30 badges per minute.

    Compté PAR CLÉ (et pas par IP) : dans un bar, tous les Pi sortent souvent
    par la même IP. Admin connecté (simulateur) : compté par compte. Sinon par IP.
    Le lieu fait partie de la clé de cache (règle multi-tenant).
    / Counted per key (not per IP: Pis often share the venue IP).
    The venue is part of the cache key (multi-tenant rule).
    """

    scope = "controlvanne_authorize"
    rate = "30/min"

    def get_cache_key(self, request, view):
        cle_de_la_requete = getattr(request, "tireuse_api_key", None)
        if cle_de_la_requete is not None:
            identifiant = f"cle-{cle_de_la_requete.prefix}"
        elif request.user and request.user.is_authenticated:
            identifiant = f"compte-{request.user.pk}"
        else:
            identifiant = f"ip-{self.get_ident(request)}"
        identifiant_du_lieu = connection.tenant.pk
        return self.cache_format % {
            "scope": self.scope,
            "ident": f"{identifiant_du_lieu}-{identifiant}",
        }


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
            tireuse = TireuseBec.objects.select_related("terminal").get(uuid=tireuse_uuid)
        except TireuseBec.DoesNotExist:
            return Response(
                {"status": "error", "message": "Tap not found on this tenant."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # La clé doit être celle de cette tireuse / The key must be this tap's key
        if not _la_cle_appartient_a_la_tireuse(request, tireuse):
            return _refus_cle_d_une_autre_tireuse(tireuse)

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

    @action(
        detail=False,
        methods=["post"],
        url_path="authorize",
        url_name="authorize",
        # Limite anti-devinette des UID de carte (voir AuthorizeTireuseThrottle)
        # / Anti card-UID guessing limit
        throttle_classes=[AuthorizeTireuseThrottle],
    )
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
            tireuse = TireuseBec.objects.select_related("terminal", "fut_actif").get(
                uuid=tireuse_uuid
            )
        except TireuseBec.DoesNotExist:
            return Response(
                {"authorized": False, "message": "Tap not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # La clé doit être celle de cette tireuse (avant toute action : les
        # sessions orphelines ne doivent pas être fermées par une autre clé)
        # / The key must be this tap's key (before anything else)
        if not _la_cle_appartient_a_la_tireuse(request, tireuse):
            return _refus_cle_d_une_autre_tireuse(tireuse)

        # Fermer (et facturer) les sessions restées ouvertes sur cette tireuse.
        # Un nouveau badge = la carte précédente n'est plus là. Fait avant tout
        # refus : même une carte refusée prouve que l'ancienne est partie.
        # / Close (and bill) sessions left open on this tap. A new badge means
        # the previous card is gone. Done before any refusal.
        _cloturer_sessions_orphelines(
            tireuse,
            ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
        )

        # Chercher la carte NFC / Find the NFC card
        from QrcodeCashless.models import CarteCashless

        # select_related("user") : le prénom du titulaire est envoyé au kiosk
        # (voir _construire_payload_session), sans requête en plus.
        # / select_related("user"): the holder's first name is sent to the kiosk.
        carte = CarteCashless.objects.select_related("user").filter(tag_id=uid).first()
        if not carte:
            _push_refus(tireuse, gettext("Carte non reconnue."))
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

        # Carte normale + tireuse hors service → refus, AFFICHÉ sur le kiosk.
        # Avant, seul le Pi recevait le refus : l'écran ne montrait rien
        # (audit 2026-09-26, point 2.6).
        # / Normal card + tap out of service → refusal, SHOWN on the kiosk.
        if not tireuse.enabled and not is_maintenance:
            _push_refus(tireuse, gettext("Tireuse hors service."))
            return Response({"authorized": False, "message": "Tap is disabled."})

        # Carte maintenance limitée à certaines tireuses (CarteMaintenance.tireuses,
        # « vide = toutes les tireuses »). Ce réglage de l'admin n'était jamais
        # vérifié (audit 2026-09-26, point 2.5).
        # / Maintenance card limited to some taps (empty = all taps).
        if is_maintenance:
            tireuses_autorisees = carte_maintenance.tireuses.all()
            carte_limitee_a_certaines_tireuses = tireuses_autorisees.exists()
            cette_tireuse_est_autorisee = tireuses_autorisees.filter(pk=tireuse.pk).exists()
            if carte_limitee_a_certaines_tireuses and not cette_tireuse_est_autorisee:
                _push_refus(
                    tireuse,
                    gettext("Carte maintenance non autorisée sur cette tireuse."),
                )
                return Response(
                    {
                        "authorized": False,
                        "message": "Maintenance card not allowed on this tap.",
                    }
                )

        # --- Maintenance : uniquement si la tireuse est hors service (enabled=False) ---
        # Une carte maintenance ne peut rincer que quand la tireuse est déclarée
        # hors service dans l'admin — sinon elle serait utilisable comme carte gratuite.
        # / Maintenance: only allowed when the tap is out of service (enabled=False).
        # A maintenance card must not work during normal service — it would bypass billing.
        if is_maintenance and tireuse.enabled:
            _push_refus(tireuse, gettext("Carte maintenance refusée : tireuse en service."))
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
                    message=gettext("Rinçage autorisé"),
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
            _push_refus(tireuse, gettext("Cashless non configuré pour ce lieu."))
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
            _push_refus(tireuse, gettext("Prix non configuré pour ce fût."))
            return Response(
                {
                    "authorized": False,
                    "message": "No price configured for the active keg.",
                }
            )

        # Volume disponible dans le reservoir.
        # Si illimité, on passe une valeur arbitrairement grande pour que
        # calculer_volume_autorise_ml ne plafonne pas sur le réservoir.
        # / Available reservoir volume.
        # If unlimited, pass an arbitrarily large value so
        # calculer_volume_autorise_ml doesn't cap on the reservoir.
        if tireuse.reservoir_illimite:
            reservoir_disponible = 9_999_000.0
        else:
            reservoir_disponible = float(tireuse.reservoir_ml)

        if not tireuse.reservoir_illimite and reservoir_disponible <= 0:
            _push_refus(tireuse, gettext("Fût vide."))
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
            _push_refus(tireuse, gettext("Solde insuffisant."), solde_centimes=solde_centimes)
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

        # Garder le solde lu ici pour les pour_update : ils l'utilisent pour
        # estimer le solde restant sans relire la cascade à chaque seconde
        # (audit 2026-09-26, point 2.4). Rien n'est débité avant le pour_end.
        # / Keep this balance for pour_update: no cascade re-read every second.
        from django.core.cache import cache

        cache.set(
            _cle_de_cache_du_solde(session),
            solde_centimes,
            timeout=DUREE_CACHE_SOLDE_SECONDES,
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
                prix_litre=prix_litre,
                solde_centimes=solde_centimes,
                vanne_ouverte=True,
                message=gettext("Carte %(uid)s — service autorisé") % {"uid": uid},
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

        # Chercher la tireuse, avec son terminal et son fût en une requête
        # (event arrive environ une fois par seconde pendant un tirage)
        # / Find the tap with its terminal and keg in one query
        try:
            tireuse = TireuseBec.objects.select_related("terminal", "fut_actif").get(
                uuid=tireuse_uuid
            )
        except TireuseBec.DoesNotExist:
            return Response(
                {"status": "error", "message": "Tap not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # La clé doit être celle de cette tireuse / The key must be this tap's key
        if not _la_cle_appartient_a_la_tireuse(request, tireuse):
            return _refus_cle_d_une_autre_tireuse(tireuse)

        # Chercher la session ouverte pour cette carte sur cette tireuse
        # / Find the open session for this card on this tap
        # carte + titulaire chargés avec la session (prénom affiché sur l'écran)
        # / card + holder loaded with the session (first name on screen)
        session = (
            RfidSession.objects.filter(
                tireuse_bec=tireuse, uid=uid, ended_at__isnull=True
            )
            .select_related("carte__user")
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
                    reset_payload["message"] = gettext("En maintenance")
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
            session_fermee, resultat_facturation = _cloturer_session_et_facturer(
                tireuse,
                session,
                volume_ml,
                ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
            )
            if session_fermee is None:
                # Un événement concurrent a déjà fermé (et facturé) la
                # session : on répond OK sans rien refaire.
                # / A concurrent event already closed (and billed) the
                # session: answer OK without redoing anything.
                logger.info(
                    f"Event {event_type} ignoré : session {session.pk} "
                    f"déjà fermée par un événement concurrent (uid={uid})"
                )
                return Response(
                    {
                        "status": "ok",
                        "message": "Session already closed by a concurrent event.",
                    }
                )
            session = session_fermee

            logger.info(
                f"Event {event_type}: carte={uid} tireuse={tireuse.nom_tireuse} "
                f"volume={volume_ml}ml session={session.pk} "
                f"facture={'oui' if resultat_facturation else 'non'}"
            )

        # Push WebSocket vers le kiosk selon le type d'événement
        # / WebSocket push to kiosk based on event type
        # Prix au litre lu UNE fois pour tout le message (propriété qui fait une
        # requête à chaque lecture) / Price per liter read ONCE (the property queries)
        prix_litre = tireuse.prix_litre

        if event_type == "pour_start":
            _push_ws_kiosk(
                tireuse,
                _construire_payload_session(
                    tireuse,
                    session,
                    prix_litre=prix_litre,
                    vanne_ouverte=True,
                    message=gettext("Tirage en cours"),
                ),
            )
        elif event_type == "pour_update":
            # Solde restant ESTIMÉ = solde lu à l'authorize − prix du volume déjà
            # servi. Le vrai débit se fait au pour_end. Le solde de l'authorize
            # vient du cache : pas de relecture de la cascade à chaque seconde
            # (audit 2026-09-26, point 2.4). Cache vide (redémarrage…) : on relit.
            # / Estimated balance = authorize balance − price of volume served.
            solde_estime_centimes = None
            if not session.is_maintenance and prix_litre > 0:
                from django.core.cache import cache

                from controlvanne.billing import calculer_montant_centimes

                solde_a_l_authorize = cache.get(_cle_de_cache_du_solde(session))
                if solde_a_l_authorize is None:
                    solde_a_l_authorize = _lire_le_solde_de_la_carte(session.carte)
                if solde_a_l_authorize is not None:
                    prix_deja_servi = calculer_montant_centimes(volume_ml, prix_litre)
                    solde_estime_centimes = max(0, solde_a_l_authorize - prix_deja_servi)
            _push_ws_kiosk(
                tireuse,
                _construire_payload_session(
                    tireuse,
                    session,
                    prix_litre=prix_litre,
                    solde_centimes=solde_estime_centimes,
                    vanne_ouverte=True,
                    message=gettext("Tirage en cours"),
                ),
            )
        elif event_type in ("pour_end", "card_removed"):
            # Solde restant après facturation, et montant RÉELLEMENT facturé
            # (il peut être inférieur au prix du volume si le solde manquait)
            # / Balance after billing, and the amount ACTUALLY billed
            solde_apres = None
            montant_facture_centimes = None
            if resultat_facturation:
                solde_apres = _lire_le_solde_de_la_carte(session.carte)
                montant_facture_centimes = resultat_facturation["montant_centimes"]

            # Le solde gardé pour les pour_update ne sert plus
            # / The balance kept for pour_update is no longer needed
            from django.core.cache import cache

            cache.delete(_cle_de_cache_du_solde(session))

            payload_fin = _construire_payload_session(
                tireuse,
                session,
                prix_litre=prix_litre,
                solde_centimes=solde_apres,
                montant_servi_centimes=montant_facture_centimes,
                session_done=True,
                message=gettext("Fin de service — %(volume)s ml")
                % {"volume": f"{float(volume_ml):.0f}"},
            )
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

class KioskBridgeThrottle(AnonRateThrottle):
    """Anti-brute-force sur le kiosk auth : 10 req/min par IP. / Brute-force protection on kiosk auth: 10 req/min per IP."""
    rate = "10/min"
    scope = "controlvanne_kiosk_bridge"

class AuthKioskView(APIView):
    """
    POST /controlvanne/auth-kiosk/
    Le Pi envoie sa clé API dans le header Authorization. Django renvoie un
    jeton à usage unique (kiosk_token), valable 5 minutes.
    / The Pi sends its API key in the Authorization header. Django returns a
    one-time token (kiosk_token), valid for 5 minutes.

    LOCALISATION : controlvanne/viewsets.py

    FLUX RÉEL (controlvanne/Pi/main.py) :
    1. Le Pi appelle cette vue et reçoit kiosk_token.
    2. Il écrit l'URL kiosk/<uuid>/?kiosk_token=<jeton> dans
       /tmp/tibeer_kiosk_url ; config/xinitrc.bash ouvre Chromium dessus.
    3. La page du kiosk consomme le jeton (_verifier_authentification_kiosk) :
       elle le supprime du cache et marque la session de CHROMIUM comme kiosk.
       Les rechargements suivants utilisent le cookie de session.
    / REAL FLOW: the Pi gets kiosk_token, Chromium opens
    kiosk/<uuid>/?kiosk_token=<token>, the kiosk page consumes it.

    Le jeton passe donc en query string. Le risque est limité : il ne sert
    qu'une fois (supprimé dès la première lecture) et expire en 5 minutes.
    / The token travels in the query string: single use, 5-minute lifetime.

    La session créée ici appartient au client HTTP du Pi (requests), pas à
    Chromium : le Pi ne s'en sert pas (session_key est renvoyé mais ignoré).
    / The session created here belongs to the Pi's HTTP client, not Chromium.
    """

    permission_classes = [HasTireuseAccess]
    throttle_classes = [KioskBridgeThrottle]

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
            request.session.set_expiry(60 * 60 * 12)   # 12h — aligné avec laboutik

        # Marquer la session comme authentifiée pour le kiosk
        # / Mark the session as authenticated for the kiosk
        request.session["controlvanne_authenticated"] = True
        request.session.save()

        # Générer un jeton à usage unique pour l'auth kiosk, sans injection de cookie.
        # Le Pi ouvre Chromium sur kiosk/<uuid>/?kiosk_token=<jeton> (Pi/main.py) ;
        # la page du kiosk valide le jeton et pose le cookie de session via HTTP.
        # / Generate a one-time token for kiosk auth, without cookie injection.
        # The Pi opens Chromium on kiosk/<uuid>/?kiosk_token=<token> (Pi/main.py);
        # the kiosk page validates it and sets the session cookie over HTTP.
        import uuid as uuid_module
        from django.core.cache import cache

        kiosk_token = str(uuid_module.uuid4())
        # Stocker le jeton dans le cache comme autorisation valide (TTL 5 minutes).
        # La valeur True indique simplement que le jeton est valide.
        # Il est consommé par _verifier_authentification_kiosk, quand Chromium
        # ouvre la page kiosk avec ?kiosk_token=<jeton> (Pi/main.py).
        # / Store the token in cache as a valid authorization (TTL 5 minutes).
        # The True value simply indicates the token is valid.
        # It is consumed by _verifier_authentification_kiosk, when Chromium opens
        # the kiosk page with ?kiosk_token=<token> (Pi/main.py).
        #
        # IMPORTANT : ce cache doit être partagé entre tous les workers (Redis ou PgCache).
        # Avec LocMemCache (default Django sans config), le token créé par un worker
        # ne sera pas trouvé par un autre worker — résultat : 403 silencieux en prod multi-worker.
        # Vérifier que CACHES["default"] pointe sur Redis dans les settings de prod.
        # / IMPORTANT: this cache must be shared across all workers (Redis or PgCache).
        # With LocMemCache (Django default without config), a token created by worker A
        # will not be found by worker B — silent 403 in multi-worker prod.
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

    Les moyens 1 et 3 sont la règle commune avec le WebSocket
    (peut_voir_les_kiosks, controlvanne/acces.py) : la page et son WebSocket
    laissent passer les mêmes personnes. Le moyen 2 (jeton) n'existe qu'en HTTP.
    / Methods 1 and 3 are the rule shared with the WebSocket. Method 2 is HTTP only.

    :param request: HttpRequest
    :return: True si autorisé, False sinon
    """
    # Moyens 1 et 3 : session kiosk ou admin du lieu (règle commune)
    # / Methods 1 and 3: kiosk session or venue admin (shared rule)
    if peut_voir_les_kiosks(request.session, request.user, connection.tenant):
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

        # fut_actif et ses tags sont affichés sur chaque vignette :
        # on les charge en une fois pour éviter une requête par tireuse.
        # / fut_actif and its tags are shown on each thumbnail: load them at once.
        toutes_les_tireuses_actives = (
            TireuseBec.objects.filter(enabled=True)
            .select_related("fut_actif")
            .prefetch_related("fut_actif__tag")
            .order_by("nom_tireuse")
        )

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
        Écran du Pi posé sur une seule tireuse (fiche bière, service, bilan).
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

        tireuse = get_object_or_404(
            TireuseBec.objects.select_related("fut_actif").prefetch_related("fut_actif__tag"),
            uuid=pk,
        )
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
