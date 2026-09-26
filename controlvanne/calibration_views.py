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
   En cas d'erreur (aucun volume, volume invalide, pas de débitmètre) :
   statut 422 + formulaire avec le message. La page accepte le 422 grâce
   au listener htmx:beforeSwap (calibration/page.html).

« Nouvelle série » : lien ?nouvelle_serie=1 → le serveur redirige vers
?depuis=<maintenant>. C'est l'heure du serveur qui compte, pas celle du PC.

Acces : staff uniquement (@staff_member_required).
TODO : restreindre aux admins du lieu (voir
CHANGELOG/a traiter/controlvanne-audit-securite-facturation.md, point 1.5).
"""

from decimal import Decimal
from datetime import timezone as dt_timezone, datetime

from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from rest_framework import serializers

from controlvanne.models import RfidSession, TireuseBec


class VolumeReelSerializer(serializers.Serializer):
    """
    Valide un volume lu sur le verre gradué, en millilitres.
    / Validates a volume read on the graduated glass, in milliliters.

    LOCALISATION : controlvanne/calibration_views.py
    """

    volume_reel_ml = serializers.DecimalField(
        max_digits=7,
        decimal_places=2,
        min_value=Decimal("1"),
        max_value=Decimal("2000"),
        error_messages={
            "invalid": _("Le volume doit être un nombre."),
            "min_value": _("Le volume doit être d'au moins 1 ml."),
            "max_value": _("Le volume ne peut pas dépasser 2000 ml."),
            "max_decimal_places": _("Deux décimales au maximum."),
            "max_digits": _("Le volume doit être un nombre."),
        },
    )


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


def _formulaire_avec_erreurs(request, tireuse, depuis_str, sessions_en_attente, erreurs):
    """
    Renvoie le formulaire de saisie avec les messages d'erreur, en statut 422.
    HX-Reswap: innerHTML garde #sessions-poll (et son polling) dans la page :
    sans cela, le prochain envoi ne trouverait plus sa cible.
    La page accepte le 422 grâce au listener htmx:beforeSwap (page.html).
    / Returns the form with error messages, status 422. HX-Reswap: innerHTML
    keeps #sessions-poll in the page. page.html accepts 422 via htmx:beforeSwap.
    """
    ctx = {
        "tireuse": tireuse,
        "depuis": depuis_str,
        "sessions_en_attente": sessions_en_attente,
        "erreurs": erreurs,
    }
    response = render(request, "calibration/partial_sessions.html", ctx, status=422)
    response["HX-Reswap"] = "innerHTML"
    return response


# ── Vues ──────────────────────────────────────────────────────────────


@staff_member_required
def calibration_page(request, uuid):
    """
    GET /controlvanne/calibration/<uuid>/
    Squelette de la page. Les sessions sont chargees par HTMX (polling toutes les 8s).
    Le parametre ?depuis=<timestamp> definit le debut de la serie en cours.
    ?nouvelle_serie=1 : redirige vers ?depuis=<heure du serveur>.
    / Page skeleton. Sessions are loaded by HTMX (polling every 8s).
    The ?depuis=<timestamp> parameter defines the start of the current series.
    ?nouvelle_serie=1 redirects to ?depuis=<server time>.
    """
    tireuse = get_object_or_404(TireuseBec, uuid=uuid)

    # Nouvelle série : l'heure de départ est celle du serveur (pas du PC)
    # / New series: the start time is the server's (not the PC's)
    demande_de_nouvelle_serie = request.GET.get("nouvelle_serie")
    if demande_de_nouvelle_serie:
        heure_de_depart = int(timezone.now().timestamp())
        adresse_de_la_page = reverse("calibration_page", kwargs={"uuid": uuid})
        return redirect(f"{adresse_de_la_page}?depuis={heure_de_depart}")

    depuis_str = request.GET.get("depuis", "")
    ctx = {
        "tireuse": tireuse,
        "depuis": depuis_str,
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
        "erreurs": [],
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

    # Aucun debitmetre → erreur immediate
    # / No flow meter → immediate error
    if not tireuse.debimetre:
        return _formulaire_avec_erreurs(
            request,
            tireuse,
            depuis_str,
            sessions_en_attente,
            [_("Aucun débitmètre associé à cette tireuse.")],
        )

    facteur_actuel = float(tireuse.debimetre.flow_calibration_factor)

    # 1. Lire et valider chaque volume saisi
    # / 1. Read and validate each entered volume
    volumes_valides_par_session = []
    erreurs = []
    for session in sessions_en_attente:
        # Case « ignorer » cochée → on ne compte pas ce versement
        # / "Ignore" box checked → this pour is not counted
        session_ignoree = request.POST.get(f"ignorer_{session.pk}")
        if session_ignoree:
            continue

        valeur_brute = request.POST.get(f"vol_{session.pk}", "").strip()
        # Champ vide → versement non mesuré, on le laisse de côté
        # / Blank field → pour not measured, left aside
        if not valeur_brute:
            continue

        validation = VolumeReelSerializer(
            data={"volume_reel_ml": valeur_brute.replace(",", ".")}
        )
        if not validation.is_valid():
            heure_du_versement = timezone.localtime(session.started_at).strftime("%d/%m %H:%M")
            for message in validation.errors["volume_reel_ml"]:
                erreurs.append(f"{heure_du_versement} : {message}")
            continue

        volumes_valides_par_session.append(
            (session, validation.validated_data["volume_reel_ml"])
        )

    if erreurs:
        return _formulaire_avec_erreurs(
            request, tireuse, depuis_str, sessions_en_attente, erreurs
        )

    # Aucun volume saisi → message d'erreur
    # / No volume entered → error message
    if not volumes_valides_par_session:
        return _formulaire_avec_erreurs(
            request,
            tireuse,
            depuis_str,
            sessions_en_attente,
            [_("Saisissez au moins un volume avant d'appliquer.")],
        )

    # 2. Enregistrer les volumes et le nouveau facteur, tout ou rien
    # / 2. Save the volumes and the new factor, all or nothing
    mesures = []
    facteurs = []
    with transaction.atomic():
        for session, volume_reel in volumes_valides_par_session:
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
                / float(volume_reel)
                * 100,
                1,
            )
            mesures.append(
                {
                    "session": session,
                    "facteur_corrige": facteur_corrige,
                    "ecart_pct": ecart_pct,
                }
            )
            facteurs.append(facteur_corrige)

        # Facteur moyen appliqué au débitmètre
        # / Average factor applied to the flow meter
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
    }
    return render(request, "calibration/partial_serie_result.html", ctx)
