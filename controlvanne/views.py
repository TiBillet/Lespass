import json, re, time
from smtplib import quoteaddr
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone
from asgiref.sync import async_to_sync
from .models import Card, CarteMaintenance, Configuration, RfidSession, TireuseBec
from .ws_payloads import WsPayload
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.db.models import F
from channels.layers import get_channel_layer


def _dec(x, d="0.00"):  # helper
    try:
        return Decimal(str(x))
    except:
        return Decimal(d)


def index(request):
    return render(request, "controlvanne/index.html")


def panel_multi(request):
    tireuse_bec = request.GET.get("tireuse_bec")
    print(f"DEBUG: tireuse_bec = '{tireuse_bec}'")
    if tireuse_bec:
        becs = None
        try:
            from uuid import UUID

            UUID(tireuse_bec)
            becs = TireuseBec.objects.filter(uuid=tireuse_bec)
            print(f"DEBUG: cherche par UUID, trouvé: {becs.count()}")
        except (ValueError, TypeError):
            print(f"DEBUG: pas un UUID, chercher par nom")
            becs = TireuseBec.objects.filter(nom_tireuse__iexact=tireuse_bec)
            print(f"DEBUG: trouvé par nom: {becs.count()}")
        if not becs:
            becs = TireuseBec.objects.all()
            print(f"DEBUG: fallback all, trouvé: {becs.count()}")
    else:
        becs = TireuseBec.objects.all()
    print(f"DEBUG: becs total: {becs.count()}")

    # Déterminer le slug_focus pour le WebSocket
    slug_focus = tireuse_bec if tireuse_bec else "all"

    return render(
        request,
        "controlvanne/panel_bootstrap.html",
        {
            "becs": becs,
            "slug_focus": slug_focus,
        },
    )


def _check_key(request):
    key = request.headers.get("X-API-Key") or request.GET.get("key")
    want = getattr(settings, "AGENT_SHARED_KEY", None)
    return (not want) or (key == want)


def _norm_uid(uid: str) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", uid or "").upper()


SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe(name: str) -> str:
    return (name or "").strip().lower()[:80] or "all"


def _ws_push(tireuse_bec, data: WsPayload):
    """
    Envoie un message WebSocket à un groupe spécifique ET au groupe 'all'.
    Le type du paramètre data est documenté dans controlvanne/ws_payloads.py.
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    # Nom du groupe avec UUID (accepte soit un objet TireuseBec soit un UUID string)
    if hasattr(tireuse_bec, "uuid"):
        group_uuid = str(tireuse_bec.uuid)
    else:
        group_uuid = str(tireuse_bec)

    group_name = f"rfid_state.{group_uuid}"

    # Structure du message pour le consumer Django Channels
    # "type": "state_update" appelle la méthode state_update du consumer
    message_structure = {"type": "state_update", "payload": data}

    print(f"📡 WS PUSH vers {group_name} : {data.get('message')}")

    # 1. Envoi au canal spécifique
    async_to_sync(channel_layer.group_send)(group_name, message_structure)

    # 2. Envoi au canal général (rfid_state.all) pour le dashboard admin
    # if safe_name != "all":
    async_to_sync(channel_layer.group_send)("rfid_state.all", message_structure)


@csrf_exempt
def ping(request):
    """Répond au test de connexion du Raspberry Pi"""
    return JsonResponse({"status": "pong", "message": "Server online"})


@csrf_exempt
def api_rfid_authorize(request):
    """Vérifie si une carte est autorisée et crée une session."""
    # 1. Parsing des données reçues
    try:
        data = json.loads(request.body)
        uid_raw = data.get("uid")
        # On récupère l'ID de la tireuse (envoyé par le Pi) pour savoir où afficher l'erreur
        target_uuid = data.get("tireuse_bec") or "all"
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "JSON invalide"}, status=400)

    # Debug Log
    print(f"🔍 AUTH REQUEST: UID={uid_raw} sur BEC={target_uuid}")

    # 2. Vérification Clé API
    if not _check_key(request):
        return JsonResponse({"error": "Clé API invalide"}, status=403)

    if not uid_raw:
        return JsonResponse({"error": "UID manquant"}, status=400)

    uid = _norm_uid(uid_raw)

    # 3. Recherche de la tireuse EN PREMIER (avant la carte)
    tireuse_bec = TireuseBec.objects.filter(uuid=target_uuid).first()
    if not tireuse_bec:
        tireuse_bec = TireuseBec.objects.filter(enabled=True).first()
    if not tireuse_bec:
        return JsonResponse({"authorized": False, "error": "Aucun bec dispo"}, status=500)

    # --- CAS MAINTENANCE : tireuse hors service ---
    if not tireuse_bec.enabled:
        # Carte maintenance → ouvrir la vanne, session sans facturation
        maint_card = CarteMaintenance.objects.filter(uid__iexact=uid, is_active=True).first()
        if maint_card:
            produit = maint_card.produit or "Nettoyage"
            open_session = RfidSession.objects.create(
                tireuse_bec=tireuse_bec,
                uid=uid,
                authorized=True,
                is_maintenance=True,
                carte_maintenance=maint_card,
                produit_maintenance_snapshot=maint_card.produit,
                label_snapshot=maint_card.label,
                liquid_label_snapshot=produit,
                unit_ml_snapshot=Decimal("0.00"),
            )
            flow_factor = (
                tireuse_bec.debimetre.flow_calibration_factor
                if tireuse_bec.debimetre else 6.5
            )
            _ws_push(tireuse_bec, {
                "tireuse_bec": tireuse_bec.nom_tireuse,
                "tireuse_bec_uuid": str(tireuse_bec.uuid),
                "maintenance": True,
                "present": True,
                "authorized": True,
                "vanne_ouverte": True,
                "uid": uid,
                "volume_ml": 0.0,
                "message": f"Nettoyage — {produit}",
            })
            return JsonResponse({
                "authorized": True,
                "session_id": open_session.id,
                "maintenance": True,
                "liquid_label": produit,
                "unit_ml": "0",
                "unit_label": "",
                "flow_calibration_factor": flow_factor,
            })

        # Carte normale sur tireuse en maintenance → refus avec solde affiché
        any_card = Card.objects.filter(uid__iexact=uid).first()
        balance_display = str(any_card.balance) if any_card else "—"
        _ws_push(tireuse_bec, {
            "tireuse_bec": tireuse_bec.nom_tireuse,
            "tireuse_bec_uuid": str(tireuse_bec.uuid),
            "maintenance": True,
            "present": True,
            "authorized": False,
            "vanne_ouverte": False,
            "uid": uid,
            "balance": balance_display,
            "message": "En Maintenance",
        })
        return JsonResponse({"authorized": False, "error": "Tireuse en maintenance"}, status=403)

    # 4a. Pas de fût assigné → vanne bloquée même avec une carte valide
    if not tireuse_bec.fut_actif:
        msg = "Aucun fût assigné"
        print(f"⛔ REFUS {uid} : {msg} sur {tireuse_bec.nom_tireuse}")
        _ws_push(tireuse_bec, {
            "tireuse_bec": tireuse_bec.nom_tireuse,
            "tireuse_bec_uuid": str(tireuse_bec.uuid),
            "present": True,
            "authorized": False,
            "vanne_ouverte": False,
            "uid": uid,
            "message": msg,
        })
        return JsonResponse({"authorized": False, "error": msg}, status=403)

    # 4b. Vérification Carte (seulement si tireuse en service et fût présent)
    card = Card.objects.filter(uid__iexact=uid, is_active=True).first()

    # --- CAS ERREUR : CARTE INCONNUE / EXPIRÉE ---
    if not card or not card.is_valid_now():
        msg = "Carte inconnue ou expirée"
        print(f"⛔ REFUS {uid} : {msg}")

        # affichage Rouge :
        _ws_push(
            tireuse_bec,
            {
                "tireuse_bec": tireuse_bec.nom_tireuse,
                "tireuse_bec_uuid": str(tireuse_bec.uuid),
                "present": True,
                "authorized": False,  # Rouge
                "vanne_ouverte": False,
                "uid": uid,
                "message": msg,
            },
        )
        return JsonResponse({"authorized": False, "error": msg}, status=403)

    # --- CAS ERREUR : SOLDE INSUFFISANT ---
    # Service gratuit (unit_ml == 0) : on ne vérifie pas le solde
    if card.balance <= 0 and tireuse_bec.unit_ml > 0:
        msg = f"Solde insuffisant ({card.balance}€)"
        print(f"⛔ REFUS {uid} : {msg}")

        _ws_push(
            tireuse_bec,
            {
                "tireuse_bec": tireuse_bec.nom_tireuse,
                "tireuse_bec_uuid": str(tireuse_bec.uuid),
                "present": True,
                "authorized": False,  # Rouge
                "vanne_ouverte": False,
                "uid": uid,
                "balance": str(card.balance),
                "message": msg,
            },
        )
        return JsonResponse({"authorized": False, "error": msg}, status=403)

    # 5. Gestion de la Session (Succès)
    # Fermer toute session orpheline (pour_end non reçu suite à une erreur réseau).
    # Cela garantit que unit_ml_snapshot reflète toujours le prix courant de la tireuse.
    open_session = RfidSession.objects.filter(card=card, ended_at__isnull=True).first()
    if open_session:
        open_session.ended_at = timezone.now()
        open_session.last_message = "Session fermée automatiquement (nouvelle présentation de carte)"
        open_session.save(update_fields=["ended_at", "last_message"])
        open_session = None

    if not open_session:

        # Calcul du volume max autorisé
        # Service gratuit (unit_ml == 0) : volume limité par le stock, pas par le solde
        if tireuse_bec.unit_ml == 0:
            max_volume_ml = float(tireuse_bec.reservoir_ml)
        else:
            max_volume_ml = float(card.balance) * float(tireuse_bec.unit_ml)

        # Plafonnement par le stock disponible (réserve)
        # Si appliquer_reserve est activé, on ne peut pas servir plus que
        # (reservoir_ml - seuil_mini_ml) pour préserver la réserve de fond de fût.
        if tireuse_bec.appliquer_reserve and tireuse_bec.seuil_mini_ml > 0:
            stock_disponible_ml = float(
                tireuse_bec.reservoir_ml - tireuse_bec.seuil_mini_ml
            )
            if stock_disponible_ml <= 0:
                # Stock épuisé sous le seuil : refus de service
                return JsonResponse(
                    {
                        "authorized": False,
                        "error": "Stock insuffisant (réserve atteinte)",
                    },
                    status=403,
                )
            max_volume_ml = min(max_volume_ml, stock_disponible_ml)

        # Création session
        open_session = RfidSession.objects.create(
            tireuse_bec=tireuse_bec,
            uid=uid,
            card=card,
            started_at=timezone.now(),
            volume_start_ml=0.0,
            authorized=True,
            liquid_label_snapshot=tireuse_bec.liquid_label,
            label_snapshot=card.label,
            unit_label_snapshot=tireuse_bec.monnaie,
            unit_ml_snapshot=tireuse_bec.unit_ml,
            allowed_ml_session=max_volume_ml,
        )

    # 5. SUCCÈS : Notification Écran (VERT)
    payload_ws = {
        "tireuse_bec": tireuse_bec.nom_tireuse,
        "tireuse_bec_uuid": str(tireuse_bec.uuid),
        "present": True,
        "authorized": True,  # Vert
        "vanne_ouverte": True,  # Vert
        "uid": uid,
        "liquid_label": tireuse_bec.liquid_label,
        "balance": str(card.balance),
        "reservoir_ml": float(tireuse_bec.reservoir_ml),
        "reservoir_max_ml": tireuse_bec.reservoir_max_ml,
        "prix_litre": str(tireuse_bec.prix_litre),
        "monnaie": tireuse_bec.monnaie,
        "message": f"Badge accepté. Solde: {card.balance} €",
    }

    print(f"✅ SUCCÈS {uid} sur {tireuse_bec.nom_tireuse}")

    # On utilise la _ws_push
    _ws_push(tireuse_bec, payload_ws)

    # 6. Réponse HTTP au Pi
    flow_factor = (
        tireuse_bec.debimetre.flow_calibration_factor
        if tireuse_bec.debimetre
        else 6.5
    )
    return JsonResponse(
        {
            "authorized": True,
            "session_id": open_session.id,
            "balance": str(card.balance),
            "liquid_label": tireuse_bec.liquid_label,
            "unit_label": tireuse_bec.monnaie,
            "unit_ml": str(tireuse_bec.unit_ml),
            "flow_calibration_factor": flow_factor,
        }
    )


@csrf_exempt
def api_rfid_event(request):
    """
    Reçoit les événements du Pi Python (start, update, end, auth_fail, card_removed)
    """
    # Debug optionnel
    # print(f"DATA: {request.body}")

    try:
        data = json.loads(request.body or b"{}")
    except Exception:
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    # 1. Extraction des données
    event_type = data.get("event_type")

    # Gestion UID (parfois brut, parfois nettoyé, on sécurise)
    raw_uid = data.get("uid", "")
    uid = _norm_uid(raw_uid)

    event_data = data.get("data", {})
    session_id = event_data.get("session_id")

    # Calcul Volume : On convertit le float reçu en Decimal
    volume_float = float(event_data.get("volume_ml", 0.0))
    current_vol = Decimal(f"{volume_float}").quantize(Decimal("0.01"))

    # Débit instantané transmis par le Pi (cl/min)
    debit_cl_min = float(event_data.get("debit_cl_min", 0.0))

    # Initialisation des variables
    target_uuid_raw = data.get("tireuse_bec")
    tireuse_bec = None
    session = None
    solde_epuise = False  # Variable pour suivre si le solde est épuisé

    # 1. ESSAYER DE TROUVER LA SESSION (Cas start, update, end)
    if session_id:
        try:
            session = RfidSession.objects.get(pk=session_id)
            tireuse_bec = session.tireuse_bec
        except RfidSession.DoesNotExist:
            pass

    # 2. SI PAS DE SESSION ID (Cas card_removed ou auth_fail)
    if not tireuse_bec and target_uuid_raw:
        tireuse_bec = TireuseBec.objects.filter(uuid=target_uuid_raw).first()
        if not tireuse_bec:
            tireuse_bec = TireuseBec.objects.filter(
                nom_tireuse__iexact=target_uuid_raw
            ).first()

    # 3. DERNIER RECOURS
    if not tireuse_bec:
        tireuse_bec = TireuseBec.objects.first()

    if not tireuse_bec:
        return JsonResponse(
            {"status": "error", "message": "Aucun bec trouvé"}, status=500
        )
    # =========================================================================
    # LOGIQUE EVENEMENTS
    # =========================================================================

    # --- CAS 1 : IDENTIFIANT REFUSÉ / CARTE REMIS EN ROUGE ---
    # NOTE: Le WebSocket est déjà envoyé par api_rfid_authorize avec le bon message
    # On ne fait rien ici pour éviter le doublon "Carte inconnue" puis "Non autorisé"
    if event_type == "auth_fail":
        print(f"🔴 AUTH_FAIL reçu mais ignoré (déjà géré par api_rfid_authorize)")
        return JsonResponse({"status": "ok"})

    # --- CAS 2 : RETRAIT CARTE (RESET ECRAN) ---
    if event_type == "card_removed" and not tireuse_bec.enabled:
        _ws_push(tireuse_bec, {
            "tireuse_bec": tireuse_bec.nom_tireuse,
            "tireuse_bec_uuid": str(tireuse_bec.uuid),
            "maintenance": True,
            "present": False,
            "authorized": False,
            "vanne_ouverte": False,
            "message": "En Maintenance",
        })
        return JsonResponse({"status": "ok"})

    if event_type == "card_removed":
        # Récupérer la dernière session pour avoir le volume servi et le solde
        last_session = (
            RfidSession.objects.filter(uid=uid, tireuse_bec=tireuse_bec)
            .order_by("-started_at")
            .first()
        )

        # Calculer le volume servi et le solde restant
        volume_served = 0.0
        remaining_balance = None
        if last_session:
            volume_served = float(last_session.volume_delta_ml or 0)
            if last_session.card:
                # Calculer le solde restant (après facturation si terminé)
                if last_session.ended_at:
                    remaining_balance = str(last_session.card.balance)
                else:
                    # Session non terminée, calculer solde estimé
                    unit_ml = last_session.unit_ml_snapshot if last_session.unit_ml_snapshot is not None else Decimal("100.0")
                    if unit_ml > 0 and volume_served > 0:
                        units_consumed = (
                            Decimal(str(volume_served)) / unit_ml
                        ).quantize(Decimal("0.01"))
                        remaining = last_session.card.balance - units_consumed
                        if remaining < 0:
                            remaining = Decimal("0.00")
                        remaining_balance = str(remaining)
                    else:
                        remaining_balance = str(last_session.card.balance)

        print(
            f"🍺 ENVOI CARD_REMOVED - Volume: {volume_served}ml, Solde: {remaining_balance}"
        )
        _ws_push(
            tireuse_bec,
            {
                "tireuse_bec": tireuse_bec.nom_tireuse,
                "tireuse_bec_uuid": str(tireuse_bec.uuid),
                "present": False,
                "uid": "",
                "message": f"Terminé - Reste: {remaining_balance or '0.00'}€"
                if volume_served > 0
                else "En attente...",
                "authorized": False,
                "volume_ml": volume_served,
                "balance": remaining_balance or "0.00",
            },
        )
        return JsonResponse({"status": "ok"})

    # --- CAS 3 : FLUX (START, UPDATE, END) ---
    # Nécessite une session valide
    if not session_id:
        return JsonResponse({"status": "error", "message": "No session ID"}, status=400)

    try:
        session = RfidSession.objects.get(pk=session_id)
    except RfidSession.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "Session not found"}, status=404
        )

    # A. Début de versage
    if event_type == "pour_start":
        # Session maintenance : payload maintenance cohérent dès le début
        if session.is_maintenance:
            produit = session.produit_maintenance_snapshot or "Nettoyage"
            _ws_push(tireuse_bec, {
                "tireuse_bec": tireuse_bec.nom_tireuse,
                "tireuse_bec_uuid": str(tireuse_bec.uuid),
                "maintenance": True,
                "present": True,
                "authorized": True,
                "vanne_ouverte": True,
                "session_done": False,
                "uid": uid,
                "volume_ml": 0.0,
                "message": f"Nettoyage — {produit}",
            })
        else:
            # Session normale : vanne_ouverte: True dès le pour_start (évite le flash rouge)
            start_balance = str(session.card.balance) if session.card else "0.00"
            _ws_push(tireuse_bec, {
                "tireuse_bec": tireuse_bec.nom_tireuse,
                "tireuse_bec_uuid": str(tireuse_bec.uuid),
                "present": True,
                "authorized": True,
                "vanne_ouverte": True,
                "uid": uid,
                "liquid_label": session.liquid_label_snapshot,
                "balance": start_balance,
                "volume_ml": 0.0,
                "reservoir_ml": float(tireuse_bec.reservoir_ml),
                "reservoir_max_ml": tireuse_bec.reservoir_max_ml,
                "prix_litre": str(tireuse_bec.prix_litre),
                "monnaie": tireuse_bec.monnaie,
                "message": f"Servez-vous ! Solde: {start_balance}€",
            })

    # B. Mise à jour ou Fin
    elif event_type in ["pour_update", "pour_end"]:
        with transaction.atomic():
            # 1. Calculer combien on a versé DEPUIS LA DERNIERE FOIS pour le Stock
            val_prev = session.volume_delta_ml
            previous_vol = Decimal(str(val_prev)) if val_prev is not None else Decimal("0.00")
            delta_stock = current_vol - previous_vol

            # Mise à jour Stock Tireuse (liquide vendu uniquement, pas maintenance)
            if delta_stock > 0 and not session.is_maintenance:
                tb = TireuseBec.objects.select_for_update().get(pk=tireuse_bec.pk)
                tb.reservoir_ml = tb.reservoir_ml - delta_stock
                if tb.reservoir_ml < 0:
                    tb.reservoir_ml = Decimal("0.00")
                tb.save()
                tireuse_bec.reservoir_ml = tb.reservoir_ml

            # 2. Mise à jour Session
            session.volume_delta_ml = current_vol
            session.last_message = f"Volume: {current_vol} ml"

            # Vérification solde épuisé (jamais pour maintenance)
            solde_epuise = False
            if not session.is_maintenance and session.card and session.allowed_ml_session:
                if current_vol >= float(session.allowed_ml_session):
                    solde_epuise = True
                    session.last_message = "Solde épuisé - Vanne fermée"
                    print(
                        f"⚠️ SOLDE ÉPUISÉ pour {uid} - Volume: {current_vol}ml, Max: {session.allowed_ml_session}ml"
                    )

            # 3. Calcul du solde estimé restant pendant le service
            # (avant la facturation finale)
            estimated_balance = str(session.card.balance) if session.card else "0.00"
            if session.card and current_vol > 0:
                unit_ml = session.unit_ml_snapshot if session.unit_ml_snapshot is not None else Decimal("100.0")
                if unit_ml > 0:
                    units_consumed = (current_vol / unit_ml).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    remaining = session.card.balance - units_consumed
                    if remaining < 0:
                        remaining = Decimal("0.00")
                    estimated_balance = str(remaining)

            # 4. Fin de session (FACTURATION)
            session_done = False
            charged_display = "0.00"
            balance_display = (
                estimated_balance  # Utiliser le solde estimé pour l'affichage
            )

            if event_type == "pour_end":
                session.ended_at = timezone.now()
                session_done = True

                if session.is_maintenance:
                    # Nettoyage : aucune facturation, juste enregistrer le volume
                    produit = session.produit_maintenance_snapshot or "Nettoyage"
                    session.last_message = f"Nettoyage terminé — {current_vol:.0f} ml ({produit})"
                elif session.card:
                    card = Card.objects.select_for_update().get(pk=session.card.pk)
                    unit_ml = session.unit_ml_snapshot if session.unit_ml_snapshot is not None else Decimal("100.0")

                    session.balance_avant = card.balance

                    if current_vol > 0 and unit_ml > 0:
                        units = (current_vol / unit_ml).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                        if units > card.balance:
                            units = card.balance
                        card.balance -= units
                        card.save()
                        session.charged_units = units
                        charged_display = str(units)
                        balance_display = str(card.balance)

                    session.balance_apres = card.balance

            session.save()

            # 1. On récupère le channel layer
            channel_layer = get_channel_layer()

            # 2. On construit le nom du groupe EXACTEMENT comme dans consumers.py
            group_name = f"rfid_state.{tireuse_bec.uuid}"

            # 3. On prépare les données
            # Si solde épuisé, on force la fermeture de la vanne
            vanne_ouverte = True
            force_close = False
            if solde_epuise:
                vanne_ouverte = False
                force_close = True

            if session.is_maintenance:
                data_to_send = {
                    "tireuse_bec": tireuse_bec.nom_tireuse,
                    "tireuse_bec_uuid": str(tireuse_bec.uuid),
                    "maintenance": True,
                    "present": not session_done,
                    "authorized": True,
                    "vanne_ouverte": vanne_ouverte,
                    "session_done": session_done,
                    "uid": uid,
                    "volume_ml": float(current_vol),
                    "message": session.last_message,
                }
            else:
                data_to_send = {
                    "tireuse_bec": tireuse_bec.nom_tireuse,
                    "tireuse_bec_uuid": str(tireuse_bec.uuid),
                    "present": True if not session_done else False,
                    "authorized": True,
                    "vanne_ouverte": vanne_ouverte,
                    "force_close": force_close,
                    "session_done": session_done or solde_epuise,
                    "uid": uid,
                    "liquid_label": session.liquid_label_snapshot or "Bière",
                    "volume_ml": float(current_vol),
                    "debit_cl_min": debit_cl_min,
                    "charged": charged_display,
                    "balance": balance_display,
                    "reservoir_ml": float(tireuse_bec.reservoir_ml),
                    "reservoir_max_ml": tireuse_bec.reservoir_max_ml,
                    "prix_litre": str(tireuse_bec.prix_litre),
                    "monnaie": tireuse_bec.monnaie,
                    "message": f"Terminé : {current_vol:.0f} ml"
                    if session_done
                    else ("Solde épuisé !" if solde_epuise else "Service en cours..."),
                }

            # 4. On envoie.
            # - "type" doit correspondre au nom de la méthode dans Consumer (`async def state_update`)
            # - Le consumer attend les données dans une clé "payload"
            print(f"🚀 ENVOI WS vers '{tireuse_bec.nom_tireuse}' ET vers 'ALL'")

            # 1. Envoi au canal SPÉCIFIQUE (pour l'écran du Pi)

            async_to_sync(channel_layer.group_send)(
                f"rfid_state.{tireuse_bec.uuid}",
                {"type": "state_update", "payload": data_to_send},
            )

            # 2. Envoi au canal GÉNÉRAL (pour le Dashboard PC)
            async_to_sync(channel_layer.group_send)(
                "rfid_state.all", {"type": "state_update", "payload": data_to_send}
            )

    # Réponse au Pi avec indication si fermeture forcée nécessaire
    response_data = {"status": "ok"}
    if solde_epuise:
        response_data["force_close"] = True
        response_data["message"] = "Solde epuise - Fermeture vanne requise"

    return JsonResponse(response_data)


@csrf_exempt
def api_rfid_register(request):
    """
    Auto-enregistrement d'un Pi dans la base Django.
    Le Pi envoie son UUID (dérivé du MAC), son nom et son hostname.
    Django crée la TireuseBec si elle n'existe pas encore (enabled=False).

    Sécurité :
    - Clé API partagée obligatoire (header X-API-Key)
    - Enregistrement autorisé uniquement si Configuration.allow_self_register=True
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST requis"}, status=405)

    # 1. Vérification de la clé API partagée
    if not _check_key(request):
        return JsonResponse({"error": "Clé API invalide"}, status=401)

    # 2. Vérification du mode d'enregistrement ouvert
    config = Configuration.get()
    if not config.allow_self_register:
        return JsonResponse(
            {
                "error": (
                    "Auto-enregistrement désactivé. "
                    "Activez 'Autoriser l'auto-enregistrement des Pi' "
                    "dans Configuration serveur de l'admin Django."
                )
            },
            status=403,
        )

    # 3. Parsing du body JSON
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Corps JSON invalide"}, status=400)

    uuid_str = body.get("uuid")
    nom_tireuse = (body.get("nom_tireuse") or "Nouvelle tireuse").strip()[:50]
    hostname = (body.get("hostname") or "").strip()[:100]

    if not uuid_str:
        return JsonResponse({"error": "Champ 'uuid' requis"}, status=400)

    # 4. Validation du format UUID
    try:
        from uuid import UUID as UUIDType
        uuid_obj = UUIDType(str(uuid_str))
    except (ValueError, AttributeError):
        return JsonResponse({"error": "Format UUID invalide"}, status=400)

    # 5. Création ou récupération de la tireuse
    # L'UUID est dérivé de l'adresse MAC, donc stable à chaque réinstall.
    note = f"Auto-enregistrée depuis {hostname}" if hostname else "Auto-enregistrée"
    tireuse, created = TireuseBec.objects.get_or_create(
        uuid=uuid_obj,
        defaults={
            "nom_tireuse": nom_tireuse,
            # Désactivée par défaut : l'admin doit assigner un fût et un débitmètre
            "enabled": False,
            "notes": note,
            # None = pas d'override : le prix du fût sera utilisé
            "prix_litre_override": None,
        },
    )
    if not created:
        # Même UUID/MAC : redémarrage normal ou réinstall avec nouveau nom.
        # On distingue les deux cas par le nom :
        # - nom identique → simple redémarrage, on ne touche à rien (évite de désactiver la tireuse à chaque reboot)
        # - nom différent → réinstall délibérée → on remet à zéro les états physiques
        #   (l'admin doit re-valider le fût et ré-activer la tireuse)
        if tireuse.nom_tireuse != nom_tireuse:
            tireuse.nom_tireuse = nom_tireuse
            tireuse.notes = note
            tireuse.enabled = False
            tireuse.fut_actif = None
            tireuse.save(update_fields=["nom_tireuse", "notes", "enabled", "fut_actif"])

    return JsonResponse(
        {
            "status": "created" if created else "already_exists",
            "uuid": str(tireuse.uuid),
            "nom_tireuse": tireuse.nom_tireuse,
            "enabled": tireuse.enabled,
        }
    )
