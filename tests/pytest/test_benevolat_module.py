"""
Le module « Bénévolat » de l'admin : sa carte, son bloc dans la barre latérale.
/ The admin "Volunteering" module: its dashboard card and sidebar block.

LOCALISATION : tests/pytest/test_benevolat_module.py

Code testé / Tested code : BaseBillet/models.py (Configuration.module_benevolat),
Administration/admin/dashboard.py (MODULE_FIELDS, _construire_sections_modules)

La configuration n'est jamais écrite en base : on travaille sur une copie, rendue par
un get_solo simulé (même parade que tests/pytest/test_admin_sidebar_kiosk_tireuses.py).
/ The stored configuration is never written: a patched get_solo returns a copy.

Lancer / Run : make test ARGS="tests/pytest/test_benevolat_module.py"
"""

import copy
from unittest import mock

import pytest
from django.test import RequestFactory
from django_tenants.utils import tenant_context

from BaseBillet.models import Configuration

PAGES_DU_BENEVOLAT = [
    "/admin/booking/planningbenevole/",
    "/admin/booking/besoinbenevole/",
    "/admin/booking/tachebenevole/",
    "/admin/booking/inscriptionbenevole/",
]


def sections_de_la_barre_laterale(module_benevolat, module_booking=True):
    """Les sections de modules, avec ces deux modules allumés ou non. A appeler dans un tenant_context."""
    from Administration.admin import dashboard

    configuration_modifiee = copy.copy(Configuration.get_solo())
    configuration_modifiee.module_benevolat = module_benevolat
    configuration_modifiee.module_booking = module_booking

    requete = RequestFactory().get("/admin/")
    with mock.patch.object(dashboard.Configuration, "get_solo", return_value=configuration_modifiee):
        return dashboard._construire_sections_modules(requete)


def liens_de_toutes_les_sections(sections):
    liens = []
    for section in sections:
        for page in section.get("items", []):
            liens.append(str(page["link"]))
    return liens


def test_module_benevolat_existe_et_defaut_false():
    """
    On lit le DÉFAUT DU CHAMP, jamais get_solo() : la Configuration du lieu porte la
    valeur réelle, qu'un gestionnaire peut allumer depuis l'admin.
    / Read the field's default, never get_solo().
    """
    assert Configuration._meta.get_field("module_benevolat").default is False


def test_le_module_a_sa_carte_dans_le_tableau_de_bord():
    from Administration.admin.dashboard import MODULE_FIELDS

    assert MODULE_FIELDS["module_benevolat"]["slug"] == "benevolat"
    assert MODULE_FIELDS["module_benevolat"]["domaine"] == "lespass"


@pytest.mark.django_db
def test_module_allume_le_bloc_benevolat_porte_ses_quatre_pages(tenant):
    with tenant_context(tenant):
        sections = sections_de_la_barre_laterale(module_benevolat=True)

    section_benevolat = [section for section in sections if section.get("_slug") == "benevolat"]
    assert len(section_benevolat) == 1
    liens = [str(page["link"]) for page in section_benevolat[0]["items"]]
    assert liens == PAGES_DU_BENEVOLAT


@pytest.mark.django_db
def test_module_eteint_aucune_page_du_benevolat_dans_la_barre(tenant):
    """Éteint, le bénévolat n'apparaît nulle part, même dans « Réservation de ressources »."""
    with tenant_context(tenant):
        sections = sections_de_la_barre_laterale(module_benevolat=False, module_booking=True)

    liens = liens_de_toutes_les_sections(sections)
    for page in PAGES_DU_BENEVOLAT:
        assert page not in liens


# ---------------------------------------------------------------------------
# Menu du site public (place_header) et page /booking/benevolat/
# / Public site menu and the /booking/benevolat/ page
# ---------------------------------------------------------------------------

def entrees_du_menu_public(module_benevolat):
    """
    Les entrées du menu du site (main_nav de get_context), module allumé ou non,
    sans écrire la configuration. A appeler dans un tenant_context.
    / The public menu entries, module on or off, without writing the configuration.
    """
    from django.contrib.auth.models import AnonymousUser

    from BaseBillet import views as vues_basebillet

    configuration_modifiee = copy.copy(Configuration.get_solo())
    configuration_modifiee.module_benevolat = module_benevolat
    requete = RequestFactory().get("/")
    requete.user = AnonymousUser()
    requete.htmx = False
    with mock.patch.object(vues_basebillet.Configuration, "get_solo", return_value=configuration_modifiee):
        contexte = vues_basebillet.get_context(requete)
    return [entree["url"] for entree in contexte["main_nav"]]


@pytest.mark.django_db
def test_le_menu_du_site_porte_benevolat_seulement_module_allume(tenant):
    with tenant_context(tenant):
        assert "/booking/benevolat/" in entrees_du_menu_public(module_benevolat=True)
        assert "/booking/benevolat/" not in entrees_du_menu_public(module_benevolat=False)


@pytest.mark.django_db
def test_la_page_liste_montre_les_plannings_a_venir(tenant):
    import datetime
    import uuid

    from django.test import Client
    from django.utils import timezone

    from booking.models import BesoinBenevole, PlanningBenevole, TacheBenevole

    with tenant_context(tenant):
        identifiant = uuid.uuid4().hex[:8]
        planning = PlanningBenevole.objects.create(
            name=f"TEST_benevolat liste {identifiant}", slug=f"test-liste-{identifiant}", published=True,
        )
        brouillon = PlanningBenevole.objects.create(
            name=f"TEST_benevolat brouillon {identifiant}", slug=f"test-brouillon-{identifiant}", published=False,
        )
        tache = TacheBenevole.objects.create(name=f"TEST_benevolat tache {identifiant}")
        dans_trois_jours = timezone.now().date() + datetime.timedelta(days=3)
        for un_planning in [planning, brouillon]:
            BesoinBenevole.objects.create(planning=un_planning, tache=tache, date=dans_trois_jours)

        reponse = Client(HTTP_HOST="lespass.tibillet.localhost", HTTP_ACCEPT_LANGUAGE="fr").get("/booking/benevolat/")

    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert 'data-testid="benevolat-liste"' in html
    assert planning.name in html
    assert brouillon.name not in html
    assert f"/booking/benevolat/{planning.slug}/" in html
