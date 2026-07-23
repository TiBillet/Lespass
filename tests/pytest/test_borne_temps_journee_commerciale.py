"""
tests/pytest/test_borne_temps_journee_commerciale.py
Bornes de la journee commerciale (4h -> 4h) et changements d'heure.
/ Business day bounds (4am -> 4am) and daylight saving transitions.

LOCALISATION : tests/pytest/test_borne_temps_journee_commerciale.py

`ApiBillet.views.borne_temps_4h()` delimite la journee commerciale : elle ne
commence pas a minuit mais a 4h du matin. En festival ou en soiree culturelle,
l'activite se termine souvent vers 4h — le ticket Z automatique se declenche a
ce moment-la, et les ventes de fin de nuit doivent etre rattachees a la journee
qui vient de s'ecouler, pas a la suivante.

CE QUI EST VERIFIE / WHAT IS CHECKED
------------------------------------
La borne de debut vaut 4h A L'HEURE DU LIEU, y compris les deux jours de
l'annee ou le fuseau bascule. C'est le cas limite qui compte : la journee
commerciale (minuit + 4h) TRAVERSE le changement d'heure, qui a lieu vers 2h/3h
du matin. Si l'offset est fige avant l'addition, la borne derive d'une heure et
le rapport Z couvre la mauvaise plage.

/ The start bound must be 4am IN VENUE TIME, including on the two days a year
when the timezone shifts. The business day (midnight + 4h) crosses the DST
transition, which happens around 2-3am. Freezing the offset before the addition
makes the bound drift by one hour.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_borne_temps_journee_commerciale.py -v
"""

import datetime
import zoneinfo
from unittest.mock import patch

import pytest
from django_tenants.utils import tenant_context

from ApiBillet.views import borne_temps_4h
from BaseBillet.models import Configuration
from Customers.models import Client as TenantClient


# Dates 2026 des bascules en Europe/Paris.
# 29 mars : on passe de 2h a 3h (l'offset gagne 1h entre minuit et midi).
# 25 octobre : on passe de 3h a 2h (l'offset perd 1h).
# / 2026 DST transition dates for Europe/Paris.
JOUR_ENTREE_HEURE_ETE = datetime.date(2026, 3, 29)
JOUR_SORTIE_HEURE_ETE = datetime.date(2026, 10, 25)
JOUR_ORDINAIRE = datetime.date(2026, 7, 15)


@pytest.fixture
def tenant():
    """Le tenant de developpement. / The development tenant."""
    return TenantClient.objects.get(schema_name="lespass")


def _fuseau_de_reference(tenant):
    """Construit le fuseau du lieu avec zoneinfo, a partir de son NOM.

    On ne passe deliberement PAS par `Configuration.get_tzinfo()` : c'est
    l'implementation que ce chantier fait evoluer, et un test qui mesure avec
    l'instrument qu'il verifie ne prouve rien. On repart donc du nom stocke en
    base et on construit une reference independante.
    / Deliberately NOT using `Configuration.get_tzinfo()`: that is the very
    implementation under change, and a test measuring with the instrument it
    checks proves nothing. We rebuild an independent reference from the stored
    timezone name.
    """
    with tenant_context(tenant):
        nom_du_fuseau = Configuration.get_solo().fuseau_horaire
    return zoneinfo.ZoneInfo(nom_du_fuseau)


def _heure_locale_de_debut_de_journee(tenant, jour):
    """Renvoie l'heure locale ('HH:MM') de la borne de debut, pour un jour donne.

    On fige `timezone.now()` a midi (heure du lieu) le jour demande : midi est
    toujours apres 4h, donc `borne_temps_4h` renvoie bien les bornes du jour
    courant et non celles de la veille.
    / Freezes now() at local noon on the given day: noon is always past 4am, so
    the function returns the current day's bounds, not the previous day's.
    """
    fuseau_du_lieu = _fuseau_de_reference(tenant)
    midi_local = datetime.datetime.combine(jour, datetime.time(12, 0)).replace(
        tzinfo=fuseau_du_lieu
    )

    with tenant_context(tenant):
        with patch("ApiBillet.views.timezone.now", return_value=midi_local):
            debut_de_journee, _fin_de_journee = borne_temps_4h()

    return debut_de_journee.astimezone(fuseau_du_lieu).strftime("%H:%M")


@pytest.fixture(autouse=True)
def le_lieu_doit_avoir_un_changement_d_heure(tenant):
    """Refuse de valider silencieusement si le lieu n'a pas de changement d'heure.

    Sans bascule (La Reunion, par exemple), les tests DST passeraient sans rien
    prouver. On aime mieux un echec explicite qu'un faux vert.
    / Without a DST transition (Reunion, for instance) the DST tests would pass
    without proving anything. An explicit failure beats a false green.
    """
    fuseau_du_lieu = _fuseau_de_reference(tenant)

    minuit = datetime.datetime.combine(JOUR_ENTREE_HEURE_ETE, datetime.time.min)
    midi = datetime.datetime.combine(JOUR_ENTREE_HEURE_ETE, datetime.time(12, 0))
    offset_a_minuit = minuit.replace(tzinfo=fuseau_du_lieu).utcoffset()
    offset_a_midi = midi.replace(tzinfo=fuseau_du_lieu).utcoffset()

    if offset_a_minuit == offset_a_midi:
        pytest.skip(
            f"Le tenant de test est sur un fuseau sans changement d'heure "
            f"({fuseau_du_lieu}) : les cas DST de ce fichier ne prouveraient rien."
        )


@pytest.mark.django_db
def test_la_journee_commerciale_commence_a_4h_un_jour_ordinaire(tenant):
    """Cas nominal : hors bascule, la journee commerciale demarre a 4h locales.
    / Nominal case: outside DST transitions, the business day starts at 4am."""
    assert _heure_locale_de_debut_de_journee(tenant, JOUR_ORDINAIRE) == "04:00"


@pytest.mark.django_db
def test_la_journee_commerciale_commence_a_4h_le_jour_du_passage_a_l_heure_d_ete(
    tenant,
):
    """Entree dans l'heure d'ete : la borne reste a 4h locales.

    Cette nuit-la, 2h du matin devient 3h. Une borne calculee en figeant
    l'offset de minuit (heure d'hiver) puis en ajoutant 4h designerait un
    instant qui vaut 5h au mur : le rapport Z demarrerait une heure trop tard.
    / That night, 2am becomes 3am. A bound computed by freezing midnight's
    offset then adding 4h lands on 5am wall time: the Z report would start an
    hour late.
    """
    assert _heure_locale_de_debut_de_journee(tenant, JOUR_ENTREE_HEURE_ETE) == "04:00"


@pytest.mark.django_db
def test_la_journee_commerciale_commence_a_4h_le_jour_du_retour_a_l_heure_d_hiver(
    tenant,
):
    """Sortie de l'heure d'ete : la borne reste a 4h locales.

    Cette nuit-la, 3h du matin redevient 2h : la nuit dure 25 heures. La borne
    doit malgre tout designer 4h au mur.
    / That night, 3am becomes 2am again: the night lasts 25 hours. The bound
    must still point at 4am wall time.
    """
    assert _heure_locale_de_debut_de_journee(tenant, JOUR_SORTIE_HEURE_ETE) == "04:00"


@pytest.mark.django_db
def test_la_fenetre_va_bien_d_un_matin_a_l_autre(tenant):
    """La fenetre s'etend de 4h a ~4h le lendemain.

    On verifie les deux bouts en heure locale plutot que la duree absolue :
    les jours de bascule, la fenetre dure reellement 23h ou 25h, et c'est
    normal — c'est la meme journee commerciale vue par les gens du lieu.
    / We check both ends in local time rather than the absolute duration: on
    transition days the window really lasts 23 or 25 hours, which is correct.
    """
    fuseau_du_lieu = _fuseau_de_reference(tenant)
    midi_local = datetime.datetime.combine(
        JOUR_ORDINAIRE, datetime.time(12, 0)
    ).replace(tzinfo=fuseau_du_lieu)

    with tenant_context(tenant):
        with patch("ApiBillet.views.timezone.now", return_value=midi_local):
            debut_de_journee, fin_de_journee = borne_temps_4h()

    debut_local = debut_de_journee.astimezone(fuseau_du_lieu)
    fin_locale = fin_de_journee.astimezone(fuseau_du_lieu)

    assert debut_local.strftime("%H:%M") == "04:00"
    assert debut_local.date() == JOUR_ORDINAIRE
    # La fin tombe au petit matin du lendemain (23:59:59 + 4h -> 03:59:59).
    # / The end lands early next morning (23:59:59 + 4h -> 03:59:59).
    assert fin_locale.date() == JOUR_ORDINAIRE + datetime.timedelta(days=1)
    assert fin_locale.strftime("%H") == "03"
