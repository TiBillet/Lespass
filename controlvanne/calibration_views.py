from decimal import Decimal, InvalidOperation
from datetime import datetime

from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

# La calibration modifie le facteur du débitmètre (impact direct sur la facturation).
# On la réserve aux superusers uniquement — un simple staff pourrait calibrer
# n'importe quelle tireuse, même celles qu'il ne gère pas.
superuser_required = user_passes_test(
    lambda u: u.is_active and u.is_superuser,
    login_url="/admin/login/",
)

from .models import Debimetre, RfidSession, TireuseBec


# ---------------------------------------------------------------------------
# Calculs (fonctions pures, facile à lire et à tester)
# ---------------------------------------------------------------------------

def _calculer_facteur_corrige(facteur_actuel, volume_mesure_ml, volume_reel_ml):
    """
    Calcule le facteur de calibration corrigé pour UNE mesure.

    Formule :  nouveau_facteur = facteur_actuel × (volume_mesuré_django / volume_réel)

    Exemple :
      Django a mesuré 450 ml, verre gradué = 500 ml → facteur trop élevé
      nouveau = facteur × (450 / 500) = facteur × 0.9  (on réduit)
    """
    if not volume_reel_ml or volume_reel_ml <= 0:
        return facteur_actuel
    return facteur_actuel * (float(volume_mesure_ml) / float(volume_reel_ml))


def _construire_mesures_recap(tireuse, sessions_calibrees):
    """
    Construit la liste des mesures calibrées enrichies (facteur calculé, écart %).
    Retourne aussi le facteur moyen arrondi à 4 décimales.
    """
    if not tireuse.debimetre:
        return [], None

    facteur_actuel = tireuse.debimetre.flow_calibration_factor
    mesures = []
    facteurs = []

    for session in sessions_calibrees:
        if not session.volume_reel_ml or session.volume_delta_ml <= 0:
            continue

        facteur_calcule = _calculer_facteur_corrige(
            facteur_actuel,
            session.volume_delta_ml,
            session.volume_reel_ml,
        )
        ecart_pct = (
            (float(session.volume_delta_ml) - float(session.volume_reel_ml))
            / float(session.volume_reel_ml)
            * 100
        )
        mesures.append({
            "session": session,
            "facteur_calcule": round(facteur_calcule, 4),
            "ecart_pct": round(ecart_pct, 1),
        })
        facteurs.append(facteur_calcule)

    facteur_moyen = round(sum(facteurs) / len(facteurs), 4) if facteurs else None
    return mesures, facteur_moyen


# ---------------------------------------------------------------------------
# Vues
# ---------------------------------------------------------------------------

@superuser_required
def calibration_page(request, uuid):
    """
    Page principale du wizard de calibration pour une tireuse.
    Affiche les sessions maintenance en attente de saisie + le récap des mesures.
    """
    tireuse = get_object_or_404(TireuseBec, uuid=uuid)

    # Optionnel : ?depuis=<ISO timestamp> passé par le lien "nouvelle série"
    # Si présent, on n'affiche que les sessions postérieures à ce moment
    depuis = None
    depuis_str = request.GET.get("depuis")
    if depuis_str:
        try:
            depuis = datetime.fromisoformat(depuis_str)
            if timezone.is_naive(depuis):
                depuis = timezone.make_aware(depuis)
        except (ValueError, TypeError):
            depuis = None

    # Filtre de base : sessions maintenance terminées avec du liquide versé
    filtre_base = dict(
        tireuse_bec=tireuse,
        is_maintenance=True,
        ended_at__isnull=False,
        volume_delta_ml__gt=0,
    )
    if depuis:
        filtre_base["started_at__gte"] = depuis

    sessions_terminees = list(
        RfidSession.objects.filter(**filtre_base).order_by("-started_at")[:20]
    )

    # Séparer : en attente de saisie vs déjà calibrées
    sessions_en_attente = [s for s in sessions_terminees if s.volume_reel_ml is None]
    sessions_calibrees  = [s for s in sessions_terminees if s.volume_reel_ml is not None]

    mesures_recap, facteur_moyen = _construire_mesures_recap(tireuse, sessions_calibrees)

    return render(request, "calibration/page.html", {
        "tireuse": tireuse,
        "sessions_en_attente": sessions_en_attente,
        "mesures_recap": mesures_recap,
        "facteur_moyen": facteur_moyen,
    })


@superuser_required
@require_POST
def calibration_soumettre(request, uuid, session_id):
    """
    Reçoit le volume réel saisi par l'opérateur pour une session de maintenance.
    Marque la session comme calibration, calcule le facteur corrigé.
    Retourne deux fragments HTMX :
      - la ligne de la table mise à jour (target = #mesure-<id>)
      - le bloc récap mis à jour hors-bande (hx-swap-oob)
    """
    tireuse = get_object_or_404(TireuseBec, uuid=uuid)
    session = get_object_or_404(
        RfidSession, pk=session_id, tireuse_bec=tireuse, is_maintenance=True
    )

    # Lecture et validation du volume réel saisi
    erreur = None
    facteur_corrige = None
    ecart_pct = None

    try:
        volume_reel_ml = Decimal(
            request.POST.get("volume_reel_ml", "0").replace(",", ".")
        )
        if volume_reel_ml <= 0:
            raise ValueError("volume nul")
    except (InvalidOperation, ValueError):
        volume_reel_ml = None
        erreur = "Saisissez un volume supérieur à 0 ml."

    if not erreur:
        # Enregistrement
        session.volume_reel_ml = volume_reel_ml
        session.is_calibration = True
        session.save(update_fields=["volume_reel_ml", "is_calibration"])

        # Calcul du facteur pour cette mesure
        if tireuse.debimetre:
            facteur_corrige = _calculer_facteur_corrige(
                tireuse.debimetre.flow_calibration_factor,
                session.volume_delta_ml,
                volume_reel_ml,
            )
            facteur_corrige = round(facteur_corrige, 4)
            ecart_pct = round(
                (float(session.volume_delta_ml) - float(volume_reel_ml))
                / float(volume_reel_ml) * 100,
                1,
            )

    # Recalcul du récap complet pour la mise à jour hors-bande
    sessions_calibrees = list(
        RfidSession.objects.filter(
            tireuse_bec=tireuse,
            is_calibration=True,
            volume_reel_ml__isnull=False,
            ended_at__isnull=False,
        ).order_by("-started_at")[:20]
    )
    mesures_recap, facteur_moyen = _construire_mesures_recap(tireuse, sessions_calibrees)

    return render(request, "calibration/partial_mesure.html", {
        "session": session,
        "tireuse": tireuse,
        "erreur": erreur,
        "facteur_corrige": facteur_corrige,
        "ecart_pct": ecart_pct,
        "mesures_recap": mesures_recap,
        "facteur_moyen": facteur_moyen,
    })


@superuser_required
@require_POST
def calibration_supprimer(request, uuid, session_id):
    """
    Supprime une session de maintenance en attente de saisie.
    Seules les sessions sans volume_reel_ml peuvent être supprimées —
    les mesures déjà calibrées sont conservées pour l'historique.
    Retourne un fragment vide : HTMX remplace la ligne par rien.
    """
    tireuse = get_object_or_404(TireuseBec, uuid=uuid)
    session = get_object_or_404(
        RfidSession,
        pk=session_id,
        tireuse_bec=tireuse,
        is_maintenance=True,
        volume_reel_ml__isnull=True,  # Seulement les mesures non encore saisies
    )
    session.delete()
    return render(request, "calibration/partial_vide.html")


@superuser_required
@require_POST
def calibration_appliquer(request, uuid):
    """
    Applique le facteur moyen calculé au débitmètre associé à la tireuse.
    Retourne un fragment HTMX de confirmation.
    """
    tireuse = get_object_or_404(TireuseBec, uuid=uuid)

    erreur = None
    facteur_ancien = None
    facteur_applique = None

    try:
        facteur_applique = round(float(request.POST.get("facteur_moyen", "0").replace(",", ".")), 4)
        if facteur_applique <= 0:
            raise ValueError("facteur nul")
    except (ValueError, TypeError):
        facteur_applique = None
        erreur = "Facteur invalide."

    if not erreur and not tireuse.debimetre:
        erreur = "Aucun débitmètre associé à cette tireuse."

    if not erreur:
        facteur_ancien = tireuse.debimetre.flow_calibration_factor
        tireuse.debimetre.flow_calibration_factor = facteur_applique
        tireuse.debimetre.save(update_fields=["flow_calibration_factor"])

    return render(request, "calibration/partial_confirmation.html", {
        "tireuse": tireuse,
        "facteur_applique": facteur_applique,
        "facteur_ancien": facteur_ancien,
        "erreur": erreur,
        "maintenant": timezone.now().isoformat(),
    })
