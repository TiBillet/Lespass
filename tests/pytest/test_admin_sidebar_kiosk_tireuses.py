"""
Reorganisation de la sidebar : bornes dans le module Kiosk, historique unique
des tirages dans le module Tireuses.
/ Sidebar reorganisation: kiosks in the Kiosk module, one pour history in Taps.

LOCALISATION : tests/pytest/test_admin_sidebar_kiosk_tireuses.py

CE QUE CES TESTS PROTEGENT :

1. On cree une borne depuis le module Kiosk (kiosk.Borne, proxy de Terminal).
   Le role « Kiosk » est pose tout seul, et le code PIN est fabrique.
2. Le module Kiosk montre « Bornes » et « Paiements ». La page « Réglages des
   bornes » est devenue un bloc de la fiche de la borne.
3. Le module Tireuses n'a plus qu'UN historique de service. « Sessions » et
   « Historique cartes » (meme modele) ont quitte le menu.
4. Une session de tirage facturee ne se supprime depuis AUCUN historique.
   Avant, seul RfidSessionAdmin la protegeait.

Meme pattern que les autres tests d'admin : base de dev vivante (lieu lespass).
/ Same pattern as the other admin tests: live dev DB (lespass venue).

PIEGE MULTI-TENANT : tenant_context(), jamais schema_context() — la fabrication
du code PIN lit connection.tenant.
"""

import copy
import uuid
from types import SimpleNamespace
from unittest import mock

import pytest
from django.test import Client as HttpClient
from django.test import RequestFactory
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import Configuration
from Customers.models import Client


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse the dev database.
    pass


@pytest.fixture
def lieu_et_superadmin(db):
    """
    Rend le lieu `lespass`, son domaine et un superadmin.
    / Returns the `lespass` tenant, its domain and a superadmin.
    """
    tenant = Client.objects.get(schema_name="lespass")
    domaine = tenant.domains.first()
    with tenant_context(tenant):
        utilisateur = TibilletUser.objects.filter(is_superuser=True).first()
    if not domaine or not utilisateur:
        pytest.fail("Le lieu 'lespass' n'a pas de domaine ou de superadmin.")
    return tenant, domaine.domain, utilisateur


def _sections_avec_kiosk_et_tireuse_actifs():
    """
    Construit les sections de la sidebar avec les modules kiosk et tireuse
    allumes, SANS toucher a la configuration en base.
    / Builds sidebar sections with kiosk and tap modules on, without writing
    the stored configuration.

    A appeler dans un tenant_context.
    """
    from Administration.admin import dashboard

    configuration_modifiee = copy.copy(Configuration.get_solo())
    configuration_modifiee.module_kiosk = True
    configuration_modifiee.module_tireuse = True

    requete = RequestFactory().get("/admin/")
    with mock.patch.object(
        dashboard.Configuration, "get_solo", return_value=configuration_modifiee
    ):
        return dashboard._construire_sections_modules(requete)


def _liens_du_module(sections, slug):
    """Les liens (str) des pages d'un module. / A module's page links."""
    for section in sections:
        if section.get("_slug") == slug:
            return [str(page["link"]) for page in section["items"]]
    pytest.fail(f"Module {slug} absent de la sidebar.")


# --- Sidebar ---


@pytest.mark.django_db
def test_le_module_kiosk_liste_les_bornes_et_plus_les_reglages(lieu_et_superadmin):
    """
    Le module Kiosk mene aux bornes. Les reglages n'ont plus d'entree propre.
    / The Kiosk module links to kiosks; settings have no own entry anymore.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    with tenant_context(tenant):
        liens_kiosk = _liens_du_module(_sections_avec_kiosk_et_tireuse_actifs(), "kiosk")

    assert "/admin/kiosk/borne/" in liens_kiosk
    assert "/admin/kiosk/paymentsintent/" in liens_kiosk
    assert "/admin/kiosk/reglagesborne/" not in liens_kiosk


@pytest.mark.django_db
def test_le_module_tireuses_n_a_plus_qu_un_historique_de_service(lieu_et_superadmin):
    """
    « Sessions » et « Historique cartes » ont quitte le menu : ils montraient
    le meme modele que l'historique des tirages.
    / "Sessions" and "Card history" left the menu: same model as pour history.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    with tenant_context(tenant):
        liens_tireuses = _liens_du_module(
            _sections_avec_kiosk_et_tireuse_actifs(), "tireuses"
        )

    assert "/admin/controlvanne/historiquetireuse/" in liens_tireuses
    assert "/admin/controlvanne/rfidsession/" not in liens_tireuses
    assert "/admin/controlvanne/historiquecarte/" not in liens_tireuses
    # Maintenance et calibration restent / Maintenance and calibration stay
    assert "/admin/controlvanne/historiquemaintenance/" in liens_tireuses
    assert "/admin/controlvanne/sessioncalibration/" in liens_tireuses


# --- Bornes ---


@pytest.mark.django_db
def test_creer_une_borne_pose_le_role_kiosk_et_fabrique_un_code_pin(lieu_et_superadmin):
    """
    BorneAdmin.save_model() pose le role « Kiosk » et fabrique le code PIN.
    / BorneAdmin.save_model() sets the "Kiosk" role and issues the PIN.
    """
    from Administration.admin.site import staff_admin_site
    from discovery.models import PairingDevice
    from kiosk.admin import BorneAdmin
    from kiosk.models import Borne

    tenant, _domaine, utilisateur = lieu_et_superadmin
    with tenant_context(tenant):
        admin_des_bornes = BorneAdmin(Borne, staff_admin_site)
        requete = RequestFactory().post("/admin/kiosk/borne/add/")
        requete.user = utilisateur

        borne = Borne(name=f"Borne test {uuid.uuid4().hex[:6]}")
        admin_des_bornes.save_model(requete, borne, form=None, change=False)

        try:
            borne.refresh_from_db()
            assert borne.terminal_role == TibilletUser.ROLE_KIOSQUE
            assert PairingDevice.objects.filter(cible_uuid=borne.id).exists()
            # La borne apparait dans la liste du module Kiosk.
            # / The kiosk shows up in the Kiosk module list.
            assert Borne.objects.filter(pk=borne.pk).exists()
        finally:
            PairingDevice.objects.filter(cible_uuid=borne.id).delete()
            borne.delete()


@pytest.mark.django_db
def test_la_liste_des_bornes_exclut_les_caisses(lieu_et_superadmin):
    """
    Borne.objects ne renvoie que les terminaux de role « Kiosk ».
    / Borne.objects only returns kiosk-role terminals.
    """
    from kiosk.models import Borne
    from laboutik.models import Terminal

    tenant, _domaine, _utilisateur = lieu_et_superadmin
    with tenant_context(tenant):
        caisse = Terminal.objects.create(
            name=f"Caisse test {uuid.uuid4().hex[:6]}",
            terminal_role=TibilletUser.ROLE_LABOUTIK,
        )
        try:
            assert not Borne.objects.filter(pk=caisse.pk).exists()
        finally:
            caisse.delete()


@pytest.mark.django_db
def test_la_fiche_d_ajout_d_une_borne_s_affiche_avec_ses_reglages(lieu_et_superadmin):
    """
    La page d'ajout repond, ne demande pas le role, et porte le bloc des reglages.
    / The add page loads, does not ask for the role, and holds the settings block.
    """
    _tenant, domaine, utilisateur = lieu_et_superadmin
    navigateur = HttpClient(HTTP_HOST=domaine)
    navigateur.force_login(utilisateur)

    reponse = navigateur.get("/admin/kiosk/borne/add/")
    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert 'name="terminal_role"' not in contenu
    assert 'name="reglages_borne-0-recharge_active"' in contenu


# --- Sessions facturees ---


@pytest.mark.django_db
def test_une_session_facturee_ne_se_supprime_depuis_aucun_historique(lieu_et_superadmin):
    """
    Les trois admins de RfidSession refusent de supprimer une session facturee.
    Avant, HistoriqueTireuse et HistoriqueCarte la laissaient supprimer.
    / The three RfidSession admins refuse to delete a billed session.
    """
    from Administration.admin.site import staff_admin_site
    from controlvanne.admin import (
        HistoriqueCarteAdmin,
        HistoriqueTireuseAdmin,
        RfidSessionAdmin,
    )
    from controlvanne.models import HistoriqueCarte, HistoriqueTireuse, RfidSession

    tenant, _domaine, utilisateur = lieu_et_superadmin
    requete = RequestFactory().get("/admin/")
    requete.user = utilisateur

    # Une fausse session suffit : seul ligne_article_id est lu.
    # / A fake session is enough: only ligne_article_id is read.
    session_facturee = SimpleNamespace(ligne_article_id=uuid.uuid4())
    session_non_facturee = SimpleNamespace(ligne_article_id=None)

    with tenant_context(tenant):
        for classe_admin, modele in (
            (RfidSessionAdmin, RfidSession),
            (HistoriqueTireuseAdmin, HistoriqueTireuse),
            (HistoriqueCarteAdmin, HistoriqueCarte),
        ):
            admin_des_sessions = classe_admin(modele, staff_admin_site)
            assert admin_des_sessions.has_delete_permission(requete, session_facturee) is False
            assert admin_des_sessions.has_delete_permission(requete, session_non_facturee)


@pytest.mark.django_db
def test_creer_une_borne_par_le_formulaire_enregistre_ses_reglages(lieu_et_superadmin):
    """
    Parcours complet : POST du formulaire d'ajout, bloc des reglages compris.
    La borne est creee avec le role « Kiosk » et ses reglages sont enregistres.
    / Full path: POST the add form with its settings block.
    """
    from discovery.models import PairingDevice
    from kiosk.models import Borne, ReglagesBorne

    tenant, domaine, utilisateur = lieu_et_superadmin
    navigateur = HttpClient(HTTP_HOST=domaine)
    navigateur.force_login(utilisateur)

    nom_de_la_borne = f"Borne formulaire {uuid.uuid4().hex[:6]}"
    reponse = navigateur.post(
        "/admin/kiosk/borne/add/",
        data={
            "name": nom_de_la_borne,
            "printer": "",
            "reglages_borne-TOTAL_FORMS": "1",
            "reglages_borne-INITIAL_FORMS": "0",
            "reglages_borne-MIN_NUM_FORMS": "0",
            "reglages_borne-MAX_NUM_FORMS": "1",
            # Case decochee : on veut voir la valeur arriver en base.
            # / Unchecked box: we want to see the value reach the DB.
            "reglages_borne-0-id": "",
            "reglages_borne-0-terminal": "",
        },
    )
    # Redirection = formulaire valide / Redirect = valid form
    assert reponse.status_code == 302, reponse.content.decode()[:2000]

    with tenant_context(tenant):
        borne = Borne.objects.get(name=nom_de_la_borne)
        try:
            assert borne.terminal_role == TibilletUser.ROLE_KIOSQUE
            reglages = ReglagesBorne.objects.get(terminal_id=borne.id)
            assert reglages.recharge_active is False
        finally:
            PairingDevice.objects.filter(cible_uuid=borne.id).delete()
            borne.delete()
