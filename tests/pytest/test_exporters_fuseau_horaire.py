"""
tests/pytest/test_exporters_fuseau_horaire.py
Exports comptables : les dates sortent a l'heure du lieu.
/ Accounting exports: dates come out in venue time.

LOCALISATION : tests/pytest/test_exporters_fuseau_horaire.py

Les deux exporters (`LigneArticleExportResource`, `TicketExportResource`)
convertissent des datetimes stockees en UTC vers le fuseau du lieu avant de les
formater. C'est ce qui alimente l'export comptable, adosse a la certification
LNE : une vente doit apparaitre au jour et a l'heure ou elle a eu lieu POUR LE
LIEU, pas pour le serveur.

LE CAS QUI COMPTE / THE CASE THAT MATTERS
------------------------------------------
Une vente de fin de soiree : 22h30 UTC un 15 juillet, c'est 00h30 le 16 juillet
a Paris. La date exportee doit etre le **16**. Si la conversion tombe, la vente
part dans le rapport de la veille et la comptabilite ne tombe plus juste.
/ A late-night sale: 22:30 UTC on July 15th is 00:30 on July 16th in Paris. The
exported date must be the 16th, otherwise the sale lands in the previous day's
report.

Ces tests n'ecrivent RIEN en base : ils appellent les methodes `dehydrate_*`
avec des objets factices, seule la Configuration du tenant est lue.
/ These tests write NOTHING: they call the `dehydrate_*` methods with fake
objects; only the tenant Configuration is read.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_exporters_fuseau_horaire.py -v
"""

import datetime
import zoneinfo
from unittest.mock import MagicMock

import pytest
from django_tenants.utils import tenant_context

from Administration.importers.lignearticle_exporter import LigneArticleExportResource
from Administration.importers.ticket_exporter import TicketExportResource
from BaseBillet.models import Configuration
from Customers.models import Client as TenantClient


@pytest.fixture
def tenant():
    """Le tenant de developpement. / The development tenant."""
    return TenantClient.objects.get(schema_name="lespass")


@pytest.fixture
def fuseau_du_lieu(tenant):
    """Fuseau du lieu, reconstruit avec zoneinfo depuis le NOM stocke en base.

    On ne passe pas par `get_tzinfo()` : c'est l'implementation que les
    exporters utilisent, et un test qui mesure avec l'instrument qu'il verifie
    ne prouve rien.
    / Rebuilt from the stored name rather than through `get_tzinfo()`: a test
    measuring with the instrument it checks proves nothing.
    """
    with tenant_context(tenant):
        return zoneinfo.ZoneInfo(Configuration.get_solo().fuseau_horaire)


def _instant_utc(annee, mois, jour, heure, minute):
    """Un instant precis, exprime en UTC. / A precise instant, in UTC."""
    return datetime.datetime(
        annee, mois, jour, heure, minute, tzinfo=datetime.timezone.utc
    )


# ---------------------------------------------------------------------------
# Export des lignes d'articles (ventes) — la date comptable
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_une_vente_apres_minuit_est_datee_du_jour_local(tenant, fuseau_du_lieu):
    """Une vente a 00h30 locale appartient au jour local, pas au jour UTC.

    22h30 UTC le 15 juillet = 00h30 le 16 juillet a Paris (UTC+2 en ete).
    L'export doit annoncer le 16.
    / A sale at 00:30 local belongs to the local day, not the UTC day.
    """
    if fuseau_du_lieu.utcoffset(datetime.datetime(2026, 7, 15)) == datetime.timedelta(
        0
    ):
        pytest.skip(
            f"Le tenant de test est sur {fuseau_du_lieu} (offset nul en juillet) : "
            "ce test ne distinguerait pas l'heure locale de l'UTC."
        )

    exporter = LigneArticleExportResource()
    with tenant_context(tenant):
        exporter.before_export(queryset=None)

    ligne = MagicMock()
    ligne.datetime = _instant_utc(2026, 7, 15, 22, 30)

    date_exportee = exporter.dehydrate_date(ligne)

    jour_local_attendu = ligne.datetime.astimezone(fuseau_du_lieu).strftime("%Y-%m-%d")
    assert date_exportee == jour_local_attendu
    assert date_exportee == "2026-07-16"


@pytest.mark.django_db
def test_une_vente_en_journee_garde_sa_date(tenant):
    """Cas nominal : une vente en pleine journee sort au bon jour.
    / Nominal case: a daytime sale exports on the right day."""
    exporter = LigneArticleExportResource()
    with tenant_context(tenant):
        exporter.before_export(queryset=None)

    ligne = MagicMock()
    ligne.datetime = _instant_utc(2026, 7, 15, 12, 0)

    assert exporter.dehydrate_date(ligne) == "2026-07-15"


@pytest.mark.django_db
def test_une_ligne_sans_date_exporte_une_chaine_vide(tenant):
    """Pas de date en base : on exporte une cellule vide, pas une erreur.
    / No date: export an empty cell, not an error."""
    exporter = LigneArticleExportResource()
    with tenant_context(tenant):
        exporter.before_export(queryset=None)

    ligne = MagicMock()
    ligne.datetime = None

    assert exporter.dehydrate_date(ligne) == ""


# ---------------------------------------------------------------------------
# Export des billets — l'heure affichee sur le document
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_l_heure_de_l_evenement_est_celle_du_lieu(tenant, fuseau_du_lieu):
    """Un concert a 20h au bar s'exporte 20h, pas l'heure UTC.

    18h00 UTC = 20h00 a Paris en ete. C'est l'heure que le public a vue sur son
    billet qui doit figurer dans l'export.
    / A concert at 20:00 at the venue exports as 20:00, not the UTC time.
    """
    heure_utc = _instant_utc(2026, 7, 15, 18, 0)
    heure_locale_attendue = heure_utc.astimezone(fuseau_du_lieu).strftime(
        "%d/%m/%Y %H:%M"
    )

    ticket = MagicMock()
    ticket.reservation.event.datetime = heure_utc

    with tenant_context(tenant):
        resultat = TicketExportResource().dehydrate_event_datetime(ticket)

    assert resultat == heure_locale_attendue


@pytest.mark.django_db
def test_l_heure_de_reservation_est_celle_du_lieu(tenant, fuseau_du_lieu):
    """Meme regle pour l'horodatage de la reservation.
    / Same rule for the reservation timestamp."""
    heure_utc = _instant_utc(2026, 7, 15, 9, 15)
    heure_locale_attendue = heure_utc.astimezone(fuseau_du_lieu).strftime(
        "%d/%m/%Y %H:%M"
    )

    ticket = MagicMock()
    ticket.reservation.datetime = heure_utc

    with tenant_context(tenant):
        resultat = TicketExportResource().dehydrate_reservation_datetime(ticket)

    assert resultat == heure_locale_attendue


@pytest.mark.django_db
def test_un_billet_sans_evenement_exporte_une_chaine_vide(tenant):
    """Billet orphelin : cellule vide, pas d'exception qui casse tout l'export.
    / Orphan ticket: empty cell, no exception breaking the whole export."""
    ticket = MagicMock()
    ticket.reservation = None

    with tenant_context(tenant):
        resultat = TicketExportResource().dehydrate_event_datetime(ticket)

    assert resultat == ""
