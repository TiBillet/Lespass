"""
Exports CSV de l'admin : un BOM en tête pour qu'Excel lise bien les accents.
/ Admin CSV exports: a leading BOM so Excel reads accents correctly.

LOCALISATION : tests/pytest/test_export_csv_bom_excel.py

Code testé / Tested code :
- Administration/admin/mixins.py (ExportCsvLisibleParExcelMixin)
- Administration/admin_tenant.py (MembershipAdmin, LigneArticleAdmin, EventAdmin, TicketAdmin)

Issue GitHub #422 :
- sans BOM, Excel lit le CSV en Windows-1252 : « é » devient « Ã© ».
- le BOM ne doit PAS aller dans les exports JSON : JSON.parse() le refuse.

Chaque test est marqué `django_db` : pytest-django l'exécute dans une transaction annulée.
/ Every test runs in a rolled-back transaction.

Lancer / Run : make test ARGS="tests/pytest/test_export_csv_bom_excel.py"
"""

import codecs
from types import SimpleNamespace

import pytest
from django.test import RequestFactory
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    creer_adhesion,
    creer_utilisateur,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, avec Stripe (catalogue) et Celery simulés pendant tout le test.
    / The `lespass` venue, with the Stripe catalogue and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees():
                yield SimpleNamespace(tenant=tenant)


def admin_des_adhesions():
    """L'admin des adhésions, tel qu'enregistré sur le site d'admin du lieu.
    / The membership admin, as registered on the venue admin site."""
    from Administration.admin.site import staff_admin_site
    from BaseBillet.models import Membership

    return staff_admin_site._registry[Membership]


def exporter_une_adhesion_avec_accents(admin_user, format_d_export):
    """
    Crée une adhésion au nom accentué, puis l'exporte comme le bouton « Exporter » de l'admin.
    / Creates a membership with an accented name, then exports it like the admin button.

    :return: le contenu du fichier exporté (bytes)
    """
    from BaseBillet.models import Membership

    adhesion_produit = creer_adhesion(prix="15.00")
    membre = creer_utilisateur(prenom="Élodie", nom="Bérénice")
    adhesion = Membership.objects.create(
        user=membre,
        price=adhesion_produit.tarif,
        first_name="Élodie",
        last_name="Bérénice",
    )

    requete = RequestFactory().get("/")
    requete.user = admin_user

    reponse = admin_des_adhesions()._do_file_export(
        format_d_export,
        requete,
        Membership.objects.filter(pk=adhesion.pk),
    )
    return reponse.content


def test_les_quatre_admins_d_export_utilisent_le_mixin_avant_django_import_export():
    """
    Le mixin doit passer AVANT ExportMixin dans l'héritage : sinon sa méthode
    get_export_data n'est jamais appelée.
    / The mixin must come BEFORE ExportMixin in the MRO, otherwise it is never called.
    """
    from import_export.admin import ExportMixin

    from Administration.admin.mixins import ExportCsvLisibleParExcelMixin
    from Administration.admin.site import staff_admin_site
    from BaseBillet.models import Event, LigneArticle, Membership, Ticket

    for modele in [Membership, LigneArticle, Event, Ticket]:
        classe_admin = type(staff_admin_site._registry[modele])
        ordre_d_heritage = classe_admin.__mro__

        assert ExportCsvLisibleParExcelMixin in ordre_d_heritage, classe_admin.__name__
        position_du_mixin = ordre_d_heritage.index(ExportCsvLisibleParExcelMixin)
        position_d_import_export = ordre_d_heritage.index(ExportMixin)
        assert position_du_mixin < position_d_import_export, classe_admin.__name__


def test_l_export_csv_des_adhesions_commence_par_un_bom(lieu, admin_user):
    """Le fichier CSV commence par le BOM UTF-8 (EF BB BF).
    / The CSV file starts with the UTF-8 BOM."""
    from import_export.formats.base_formats import CSV

    contenu = exporter_une_adhesion_avec_accents(admin_user, CSV())

    assert contenu.startswith(codecs.BOM_UTF8)


def test_l_export_csv_des_adhesions_garde_les_accents(lieu, admin_user):
    """Une fois le BOM retiré, le texte est de l'UTF-8 avec les accents intacts.
    / Once the BOM is stripped, the text is UTF-8 with intact accents."""
    from import_export.formats.base_formats import CSV

    contenu = exporter_une_adhesion_avec_accents(admin_user, CSV())
    texte = contenu.decode("utf-8-sig")

    assert "Élodie" in texte
    assert "Ã©" not in texte


def test_l_export_json_des_adhesions_n_a_pas_de_bom(lieu, admin_user):
    """Un JSON ne doit pas commencer par un BOM : JSON.parse() le refuserait.
    / A JSON file must not start with a BOM."""
    from import_export.formats.base_formats import JSON

    contenu = exporter_une_adhesion_avec_accents(admin_user, JSON())

    assert not contenu.startswith(codecs.BOM_UTF8)
