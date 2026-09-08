"""
La page d'accueil d'un module : onglets et liste des admins.
/ A module's landing page: category tabs and the list of its admin pages.

LOCALISATION : tests/pytest/test_admin_page_de_module.py

CE QUE CES TESTS PROTEGENT
--------------------------
La sidebar est rangee par domaine et n'affiche qu'UN lien par module. Ce lien
mene a une page qui liste les admins du module, rangees sous les onglets
Gerer / Configurer / Analyser.

Le risque numero un de cette architecture, c'est qu'une page d'admin devienne
INATTEIGNABLE : elle n'est plus dans la sidebar, donc si la page de module ne
la liste pas, plus personne ne peut y acceder. C'est ce que verifie le test
le plus important de ce fichier.
/ The main risk is an admin page becoming unreachable: it left the sidebar, so
  if the module page does not list it, nobody can reach it.

Meme pattern que les autres tests d'admin : base de dev vivante.
/ Same pattern as the other admin tests: live dev DB.
"""

import pytest
from django.test import Client as HttpClient
from django.urls import reverse
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
    Rend le premier lieu qui a un domaine ET un superadmin.
    / Returns the first tenant having both a domain and a superadmin.
    """
    for tenant in Client.objects.exclude(schema_name="public"):
        domaine = tenant.domains.first()
        if not domaine:
            continue
        with tenant_context(tenant):
            utilisateur = TibilletUser.objects.filter(is_superuser=True).first()
        if utilisateur:
            return tenant, domaine.domain, utilisateur
    pytest.skip("Aucun lieu avec un domaine et un superadmin.")


@pytest.fixture
def navigateur(lieu_et_superadmin):
    """Un client HTTP deja connecte sur le lieu. / A logged-in HTTP client."""
    _tenant, domaine, utilisateur = lieu_et_superadmin
    client = HttpClient(HTTP_HOST=domaine)
    client.force_login(utilisateur)
    return client


@pytest.mark.django_db
def test_la_page_de_module_repond(navigateur, lieu_et_superadmin):
    """La page d'un module actif s'affiche. / An active module's page loads."""
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    with tenant_context(tenant):
        module_actif = Configuration.get_solo().module_billetterie
    if not module_actif:
        pytest.skip("Le module billetterie n'est pas actif sur ce lieu.")

    reponse = navigateur.get(reverse("staff_admin:page_de_module", args=["agenda"]))
    assert reponse.status_code == 200


@pytest.mark.django_db
def test_un_module_inconnu_renvoie_404(navigateur):
    """
    Un identifiant inconnu ne doit pas faire planter l'admin.
    / An unknown slug must not crash the admin.
    """
    reponse = navigateur.get(
        reverse("staff_admin:page_de_module", args=["module-qui-nexiste-pas"])
    )
    assert reponse.status_code == 404


@pytest.mark.django_db
def test_l_onglet_demande_est_celui_qui_s_ouvre(navigateur, lieu_et_superadmin):
    """
    ?onglet=configurer ouvre bien « Configurer », et pas le premier onglet.
    / ?onglet=configurer opens "Configurer", not the first tab.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    with tenant_context(tenant):
        if not Configuration.get_solo().module_billetterie:
            pytest.skip("Le module billetterie n'est pas actif sur ce lieu.")

    adresse = reverse("staff_admin:page_de_module", args=["agenda"])
    contenu = navigateur.get(adresse + "?onglet=configurer").content.decode()

    # L'onglet actif porte la classe "active" ET son data-testid.
    # / The active tab carries both the class and its data-testid.
    assert 'data-testid="module-tab-configurer"' in contenu
    position_configurer = contenu.index('data-testid="module-tab-configurer"')
    debut_du_lien = contenu.rfind("<a", 0, position_configurer)
    assert 'class="active"' in contenu[debut_du_lien:position_configurer]


@pytest.mark.django_db
def test_un_onglet_inconnu_retombe_sur_le_premier(navigateur, lieu_et_superadmin):
    """
    Une valeur farfelue dans l'URL ne casse rien : on ouvre le premier onglet.
    / A bogus tab value falls back to the first tab instead of breaking.
    """
    tenant, _domaine, _utilisateur = lieu_et_superadmin
    with tenant_context(tenant):
        if not Configuration.get_solo().module_billetterie:
            pytest.skip("Le module billetterie n'est pas actif sur ce lieu.")

    adresse = reverse("staff_admin:page_de_module", args=["agenda"])
    reponse = navigateur.get(adresse + "?onglet=nimportequoi")
    assert reponse.status_code == 200
    assert 'data-testid="module-page-row"' in reponse.content.decode()


@pytest.mark.django_db
def test_aucune_page_d_admin_ne_devient_inatteignable(lieu_et_superadmin):
    """
    LE test important de ce fichier.

    Les pages d'un module ont quitte la sidebar. Chacune doit donc etre
    listee par la page de son module, sinon elle n'est plus accessible
    nulle part.
    / The critical test: every module page must be listed by its module's
      landing page, otherwise it is unreachable.
    """
    from django.test import RequestFactory

    from Administration.admin import dashboard

    tenant, _domaine, _utilisateur = lieu_et_superadmin
    requete = RequestFactory().get("/admin/")

    with tenant_context(tenant):
        sections = dashboard._construire_sections_modules(requete)
        navigation = dashboard.get_sidebar_navigation(requete)

    carte = dashboard._carte_des_liens_vers_modeles()

    pages_avant = {
        str(page.get("link"))
        for section in sections
        for page in (section.get("items") or [])
    }

    # Ce qu'on peut atteindre : les liens de la sidebar, plus toutes les
    # pages listees par les pages de module.
    # / Reachable: sidebar links plus every page listed by a module page.
    pages_atteignables = {
        str(item.get("link"))
        for groupe in navigation
        for item in groupe["items"]
    }
    for section in sections:
        if not section.get("_slug"):
            continue
        par_categorie = dashboard._categoriser_les_pages(section["items"], carte)
        for pages_de_la_categorie in par_categorie.values():
            pages_atteignables |= {
                str(page.get("link")) for page in pages_de_la_categorie
            }

    perdues = sorted(pages_avant - pages_atteignables)
    assert not perdues, f"Pages d'admin devenues inatteignables : {perdues}"


@pytest.mark.django_db
def test_chaque_page_est_rangee_dans_exactement_une_categorie(lieu_et_superadmin):
    """
    Une page ne doit ni disparaitre ni apparaitre deux fois.
    / A page must neither vanish nor appear twice.
    """
    from django.test import RequestFactory

    from Administration.admin import dashboard

    tenant, _domaine, _utilisateur = lieu_et_superadmin
    requete = RequestFactory().get("/admin/")
    with tenant_context(tenant):
        sections = dashboard._construire_sections_modules(requete)
    carte = dashboard._carte_des_liens_vers_modeles()

    for section in sections:
        if not section.get("_slug"):
            continue
        par_categorie = dashboard._categoriser_les_pages(section["items"], carte)
        nombre_range = sum(len(pages) for pages in par_categorie.values())
        assert nombre_range == len(section["items"]), (
            f"Module {section['_slug']} : {nombre_range} pages rangees "
            f"pour {len(section['items'])} pages reelles."
        )
