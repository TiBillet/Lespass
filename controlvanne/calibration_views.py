"""
Vues de calibration du debitmetre pour une tireuse.
/ Calibration views for the tap flow meter.

LOCALISATION : controlvanne/calibration_views.py

Flux :
1. calibration_page              GET  /controlvanne/calibration/<uuid>/
   Squelette de la page. Les sessions sont chargees par HTMX (polling).

2. calibration_sessions_partial  GET  /controlvanne/calibration/<uuid>/sessions/?depuis=<ts>
   Partial HTMX — retourne les sessions en attente de saisie.
   Appele toutes les 8s par le polling HTMX de la page.
   Contient le formulaire de saisie unique (un champ par session).

3. calibration_serie             POST /controlvanne/calibration/<uuid>/serie/
   Recoit tous les volumes en une seule requete (vol_<session_pk>=...).
   Valide, marque les sessions, calcule le facteur moyen, l'applique.
   Retourne partial_serie_result.html qui remplace #sessions-poll (outerHTML).
   Le remplacement outerHTML supprime le polling.

Acces : staff uniquement (@staff_member_required).
"""

from decimal import Decimal, InvalidOperation
from datetime import timezone as dt_timezone, datetime

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from controlvanne.models import RfidSession, TireuseBec


# ── Helpers ───────────────────────────────────────────────────────────


def _parse_depuis_str(valeur_brute):
    """
    Convertit un timestamp flottant (chaine) en datetime UTC.
    Retourne None si la valeur est absente ou invalide.
    / Converts a float timestamp (string) to a UTC datetime.
    Returns None if the value is missing or invalid.
    """
    try:
        ts = float(valeur_brute)
        return datetime.fromtimestamp(ts, tz=dt_timezone.utc)
    except (ValueError, TypeError):
        return None


def _sessions_en_attente(tireuse, depuis=None):
    """
    Sessions maintenance terminees, volume mesure par Django > 0,
    sans volume reel saisi par l'admin (volume_reel_ml IS NULL).
    / Finished maintenance sessions, Django-measured volume > 0,
    without real volume entered by admin (volume_reel_ml IS NULL).
    """
    qs = RfidSession.objects.filter(
        tireuse_bec=tireuse,
        is_maintenance=True,
        ended_at__isnull=False,
        volume_delta_ml__gt=0,
        volume_reel_ml__isnull=True,
    )
    if depuis:
        qs = qs.filter(started_at__gte=depuis)
    return qs.order_by("started_at")


def _calculer_facteur_corrige(facteur_actuel, volume_delta_ml, volume_reel_ml):
    """
    facteur_corrige = facteur_actuel x (volume_django / volume_reel)
    Exemple : facteur=6.5, django=500ml, reel=480ml → 6.5 x (500/480) = 6.77
    Si les volumes sont egaux, le facteur ne change pas.
    / If volumes are equal, the factor does not change.
    """
    if not volume_reel_ml or float(volume_reel_ml) <= 0:
        return float(facteur_actuel)
    return round(float(facteur_actuel) * (float(volume_delta_ml) / float(volume_reel_ml)), 4)


# ── Vues ──────────────────────────────────────────────────────────────


@staff_member_required
def calibration_page(request, uuid):
    """
    GET /controlvanne/calibration/<uuid>/
    Squelette de la page. Les sessions sont chargees par HTMX (polling toutes les 8s).
    Le parametre ?depuis=<timestamp> definit le debut de la serie en cours.
    / Page skeleton. Sessions are loaded by HTMX (polling every 8s).
    The ?depuis=<timestamp> parameter defines the start of the current series.
    """
    tireuse = get_object_or_404(TireuseBec, uuid=uuid)
    depuis_str = request.GET.get("depuis", "")
    ctx = {
        "tireuse": tireuse,
        "depuis": depuis_str,
        # maintenant : pour le lien "Nouvelle serie" (timestamp courant)
        # / maintenant: for the "New series" link (current timestamp)
        "maintenant": timezone.now().timestamp(),
    }
    return render(request, "calibration/page.html", ctx)


@staff_member_required
def calibration_sessions_partial(request, uuid):
    """
    GET /controlvanne/calibration/<uuid>/sessions/?depuis=<ts>
    Partial HTMX appele toutes les 8s par la page.
    Retourne le formulaire de saisie avec une ligne par session en attente.
    / HTMX partial called every 8s by the page.
    Returns the input form with one row per pending session.
    """
    tireuse = get_object_or_404(TireuseBec, uuid=uuid)
    depuis_str = request.GET.get("depuis", "")
    depuis = _parse_depuis_str(depuis_str)
    sessions_en_attente = list(_sessions_en_attente(tireuse, depuis))
    ctx = {
        "tireuse": tireuse,
        "depuis": depuis_str,
        "sessions_en_attente": sessions_en_attente,
        "erreur": None,
    }
    return render(request, "calibration/partial_sessions.html", ctx)


@staff_member_required
@require_POST
def calibration_serie(request, uuid):
    """
    POST /controlvanne/calibration/<uuid>/serie/
    Recoit les volumes reels pour toutes les sessions de la serie.
    Format POST : vol_<session_pk>=<volume_ml> pour chaque session.
    Les champs laisses vides sont ignores (session ignoree dans le calcul).
    Calcule le facteur moyen et l'applique au debitmetre.
    Retourne partial_serie_result.html (remplace #sessions-poll en outerHTML).
    / Receives real volumes for all sessions in the series.
    POST format: vol_<session_pk>=<volume_ml> for each session.
    Blank fields are ignored (session excluded from calculation).
    Calculates the average factor and applies it to the flow meter.
    Returns partial_serie_result.html (replaces #sessions-poll as outerHTML).
    """
    tireuse = get_object_or_404(TireuseBec, uuid=uuid)
    depuis_str = request.POST.get("depuis", "")
    depuis = _parse_depuis_str(depuis_str)
    sessions_en_attente = list(_sessions_en_attente(tireuse, depuis))

    # Aucun debitmetre → erreur immediate (innerHTML pour garder #sessions-poll dans le DOM)
    # / No flow meter → immediate error (innerHTML to keep #sessions-poll in the DOM)
    if not tireuse.debimetre:
        ctx = {
            "tireuse": tireuse,
            "depuis": depuis_str,
            "sessions_en_attente": sessions_en_attente,
            "erreur": "Aucun débitmètre associé à cette tireuse.",
        }
        response = render(request, "calibration/partial_sessions.html", ctx)
        response["HX-Reswap"] = "innerHTML"
        return response

    facteur_actuel = float(tireuse.debimetre.flow_calibration_factor)

    # Collecter les volumes saisis et traiter chaque session
    # / Collect entered volumes and process each session
    mesures = []
    facteurs = []

    for session in sessions_en_attente:
        valeur_brute = request.POST.get(f"vol_{session.pk}", "").strip()

        # Champ laisse vide → on ignore cette session
        # / Blank field → skip this session
        if not valeur_brute:
            continue

        try:
            volume_reel = Decimal(valeur_brute.replace(",", "."))
            if volume_reel <= 0:
                raise ValueError("Volume nul ou negatif")
        except (InvalidOperation, ValueError):
            # Volume invalide → on ignore cette session mais on continue
            # / Invalid volume → skip this session but continue
            continue

        # Sauvegarder le volume reel dans la session
        # / Save the real volume in the session
        session.volume_reel_ml = volume_reel
        session.is_calibration = True
        session.save(update_fields=["volume_reel_ml", "is_calibration"])

        facteur_corrige = _calculer_facteur_corrige(
            facteur_actuel,
            session.volume_delta_ml,
            volume_reel,
        )
        ecart_pct = round(
            (float(session.volume_delta_ml) - float(volume_reel))
            / float(volume_reel) * 100,
            1,
        )
        mesures.append({
            "session": session,
            "facteur_corrige": facteur_corrige,
            "ecart_pct": ecart_pct,
        })
        facteurs.append(facteur_corrige)

    # Aucun volume valide saisi → retourner le formulaire avec message d'erreur.
    # HX-Reswap: innerHTML pour que #sessions-poll reste dans le DOM avec
    # ses attributs de polling — sans cela le prochain submit ne trouverait
    # plus la cible et ne ferait rien.
    # / No valid volume entered → return form with error message.
    # HX-Reswap: innerHTML so #sessions-poll stays in the DOM with its
    # polling attributes — without this the next submit can't find the target.
    if not mesures:
        ctx = {
            "tireuse": tireuse,
            "depuis": depuis_str,
            "sessions_en_attente": sessions_en_attente,
            "erreur": "Saisissez au moins un volume avant d'appliquer.",
        }
        response = render(request, "calibration/partial_sessions.html", ctx)
        response["HX-Reswap"] = "innerHTML"
        return response

    # Calculer et appliquer le facteur moyen
    # / Calculate and apply the average factor
    facteur_moyen = round(sum(facteurs) / len(facteurs), 4)
    facteur_ancien = tireuse.debimetre.flow_calibration_factor
    tireuse.debimetre.flow_calibration_factor = facteur_moyen
    tireuse.debimetre.save(update_fields=["flow_calibration_factor"])

    ctx = {
        "tireuse": tireuse,
        "depuis": depuis_str,
        "mesures": mesures,
        "facteur_ancien": facteur_ancien,
        "facteur_applique": facteur_moyen,
        # maintenant : timestamp pour le lien "Nouvelle serie de verification"
        # / maintenant: timestamp for the "New verification series" link
        "maintenant": timezone.now().timestamp(),
    }
    return render(request, "calibration/partial_serie_result.html", ctx)
