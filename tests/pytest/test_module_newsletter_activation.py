"""
Activation du module Newsletter : ouverte a tous les gestionnaires.
/ Newsletter module activation: open to every manager.

LOCALISATION : tests/pytest/test_module_newsletter_activation.py

CE QUE CES TESTS PROTEGENT
--------------------------
Le module Newsletter pilote une instance **Ghost** auto-hebergee. Il s'active comme les
autres modules : n'importe quel gestionnaire (admin du tenant) peut le faire depuis le
dashboard. La contrainte « il faut un serveur Ghost » n'est pas un verrou technique : elle
est simplement rappelee dans la description du module et sur la page de configuration, avec
une invitation a contacter l'equipe TiBillet (qui peut heberger l'instance).

Regles :
1. Le module est **desactive par defaut**.
2. Tout gestionnaire du tenant peut l'activer (modale de confirmation normale + POST accepte).
3. L'entree « Newsletter » de la sidebar n'apparait que module actif, et la config Ghost
   est atteignable depuis ce module (elle a demenage hors de « Outils externes »).

   Depuis le passage aux domaines, la sidebar affiche UN lien par module : « Newsletter »
   est donc un lien du domaine « Lespass », et non plus un groupe. Ses pages (Serveur
   Ghost, Brevo) sont devenues les onglets du module, construits par get_tabs().
   / Since the move to domains, the sidebar shows one link per module: "Newsletter" is a
     link inside the "Lespass" domain, and its pages are the module's tabs.

Tests d'integration sur la base de DEV. Ils remettent le module dans son etat initial a la
fin de chaque test (fixture `remettre_le_module_comme_avant`).
/ Integration tests on the DEV database; each test restores the module's initial state.
"""

import pytest
from django.test import Client as HttpClient
from django.utils.translation import gettext as _
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import Configuration
from Customers.models import Client

URL_DE_LA_MODALE = "/admin/BaseBillet/configuration/module-toggle-modal/module_newsletter/"
URL_DE_LA_BASCULE = "/admin/BaseBillet/configuration/module-toggle/module_newsletter/"


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()


@pytest.fixture
def tenant():
    t = Client.objects.filter(schema_name="lespass").first()
    if not t:
        pytest.fail("Seed demo_data_v2 absent : pas de tenant 'lespass'.")
    return t


@pytest.fixture
def remettre_le_module_comme_avant(tenant):
    """
    Ces tests tournent sur la base de DEV : on restaure l'etat initial du module apres
    chaque test, pour ne pas laisser la config du mainteneur modifiee.
    / Restore the module's initial state: these tests run on the DEV database.
    """
    with tenant_context(tenant):
        etat_initial = Configuration.get_solo().module_newsletter
    yield
    with tenant_context(tenant):
        configuration = Configuration.get_solo()
        configuration.module_newsletter = etat_initial
        configuration.save()


@pytest.fixture
def gestionnaire_ordinaire(tenant):
    """
    Un ADMIN DU TENANT qui n'est PAS superadmin — le profil type du gestionnaire d'un lieu.

    Il faut le CREER : la base de dev n'en contient aucun. Etre admin du tenant, ce n'est
    pas `is_staff` : c'est appartenir au M2M `client_admin` du tenant
    (cf. TibilletUser.is_tenant_admin et ApiBillet.permissions.TenantAdminPermissionWithRequest).
    Sans ce M2M, l'admin Django repond 302 vers /admin/login/ — un echec trompeur, qui
    ressemble a un refus de permission alors que l'utilisateur n'a simplement pas d'acces.

    L'utilisateur est SUPPRIME a la fin du test : ces tests tournent sur la base de DEV.
    / A TENANT ADMIN who is NOT a superadmin. It must be CREATED: the dev DB has none.
    Being a tenant admin is not `is_staff` — it is membership of the tenant's `client_admin`
    M2M. The user is DELETED at teardown; these tests run on the DEV database.
    """
    with tenant_context(tenant):
        utilisateur, _cree = TibilletUser.objects.get_or_create(
            email="test-gestionnaire-newsletter@example.org",
            defaults={
                "is_staff": True,
                "is_superuser": False,
                "is_active": True,
                "espece": TibilletUser.TYPE_HUM,
            },
        )
        utilisateur.client_admin.add(tenant)

    yield utilisateur

    with tenant_context(tenant):
        utilisateur.delete()


def _superadmin(tenant):
    with tenant_context(tenant):
        utilisateur = TibilletUser.objects.filter(is_superuser=True).first()
    if not utilisateur:
        pytest.fail("Aucun superadmin dans la base de dev.")
    return utilisateur


def _client_http(tenant, utilisateur):
    """
    PIEGE MULTI-TENANT : le `force_login` ET les requetes qui suivent doivent se faire
    DANS le tenant_context. Hors contexte, la session n'est pas retrouvee et l'admin
    repond 302 vers /admin/login/ — un echec trompeur, qui ressemble a un probleme de
    permission alors que c'est un probleme de schema.
    / MULTI-TENANT TRAP: force_login AND the following requests must run INSIDE the
    tenant_context, otherwise the session is not found and the admin answers 302.
    """
    client = HttpClient(HTTP_HOST=tenant.domains.first().domain)
    client.force_login(utilisateur)
    return client


def _poser_letat_du_module(valeur):
    """
    Force l'etat du module. A APPELER DANS UN tenant_context.
    / Force the module's state. CALL INSIDE a tenant_context.

    PIEGE : ne PAS utiliser `Configuration.objects.update(...)`. django-solo MET EN CACHE
    l'objet renvoye par get_solo() (SOLO_CACHE). Un `update()` ecrit en base mais laisse le
    cache intact : la vue lirait alors l'ANCIENNE valeur et basculerait dans le mauvais
    sens. Il faut passer par get_solo() + save(), qui invalide le cache.
    / TRAP: do NOT use `objects.update()`. django-solo CACHES the get_solo() object; an
    update() writes to the DB but leaves the cache stale, so the view would read the OLD
    value and toggle the wrong way. Use get_solo() + save(), which invalidates the cache.
    """
    configuration = Configuration.get_solo()
    configuration.module_newsletter = valeur
    configuration.save()


@pytest.mark.django_db
class TestValeurParDefaut:

    def test_le_module_newsletter_est_desactive_par_defaut(self):
        """
        On lit le DEFAUT DU CHAMP, jamais get_solo() : la Configuration d'un tenant porte
        la valeur reelle, qu'un gestionnaire peut activer. La lire ici rendrait le test
        dependant de l'etat de la base.
        / Read the FIELD DEFAULT, never get_solo(): the tenant's Configuration holds the
        real value, which a manager may have switched on.
        """
        champ = Configuration._meta.get_field("module_newsletter")
        assert champ.default is False


@pytest.mark.django_db
class TestActivationParTousLesGestionnaires:

    def test_le_gestionnaire_voit_la_modale_de_confirmation_normale(
        self, tenant, gestionnaire_ordinaire, remettre_le_module_comme_avant
    ):
        """
        Le module s'active comme les autres : un gestionnaire ordinaire recoit la modale de
        confirmation habituelle, avec son bouton de bascule.
        """
        with tenant_context(tenant):
            client = _client_http(tenant, gestionnaire_ordinaire)
            reponse = client.get(URL_DE_LA_MODALE)

        assert reponse.status_code == 200
        page = reponse.content.decode()

        # La modale de confirmation, avec son bouton de bascule.
        assert "module-toggle/module_newsletter" in page

    def test_le_gestionnaire_peut_activer_le_module(
        self, tenant, gestionnaire_ordinaire, remettre_le_module_comme_avant
    ):
        """
        Le POST de bascule est accepte pour un gestionnaire du tenant : le module s'active.
        """
        with tenant_context(tenant):
            client = _client_http(tenant, gestionnaire_ordinaire)
            _poser_letat_du_module(False)
            reponse = client.post(URL_DE_LA_BASCULE)

        assert reponse.status_code == 200
        with tenant_context(tenant):
            assert Configuration.get_solo().module_newsletter is True


@pytest.mark.django_db
class TestSidebar:

    def test_le_menu_newsletter_napparait_que_si_le_module_est_actif(
        self, tenant, remettre_le_module_comme_avant
    ):
        """
        Inutile de montrer une config Ghost a un lieu qui n'a pas de serveur Ghost.
        Le lien « Newsletter » n'existe dans la sidebar que module actif.

        Depuis le passage aux domaines, « Newsletter » est un LIEN du domaine
        « Lespass », et non plus un groupe : on cherche donc parmi les libelles
        d'items, tous groupes confondus.
        / "Newsletter" is now a link inside the "Lespass" domain, not a group.
        """
        from Administration.admin.dashboard import get_sidebar_navigation

        client = _client_http(tenant, _superadmin(tenant))

        def _liens_de_la_sidebar():
            """Rend la sidebar via une vraie requete admin, et liste ses liens."""
            requete = client.get("/admin/").wsgi_request
            with tenant_context(tenant):
                navigation = get_sidebar_navigation(requete)
            return [
                str(item["title"])
                for groupe in navigation
                for item in groupe["items"]
            ]

        # --- Module DESACTIVE : pas de lien Newsletter ---
        with tenant_context(tenant):
            _poser_letat_du_module(False)
        assert str(_("Newsletter")) not in _liens_de_la_sidebar()

        # --- Module ACTIF : le lien apparait ---
        with tenant_context(tenant):
            _poser_letat_du_module(True)
        assert str(_("Newsletter")) in _liens_de_la_sidebar()

    def test_newsletter_est_rangee_dans_le_domaine_lespass(
        self, tenant, remettre_le_module_comme_avant
    ):
        """
        La sidebar est rangee par domaine. Newsletter parle au public : elle
        appartient donc a « Lespass », comme l'agenda et l'adhesion.
        / The sidebar is grouped by domain; Newsletter belongs to "Lespass".
        """
        from Administration.admin.dashboard import DOMAINES, get_sidebar_navigation

        client = _client_http(tenant, _superadmin(tenant))
        requete = client.get("/admin/").wsgi_request

        with tenant_context(tenant):
            _poser_letat_du_module(True)
            navigation = get_sidebar_navigation(requete)

        groupes_contenant_newsletter = [
            str(groupe["title"])
            for groupe in navigation
            for item in groupe["items"]
            if str(item["title"]) == str(_("Newsletter"))
        ]

        assert groupes_contenant_newsletter, "Le lien Newsletter est introuvable."
        assert groupes_contenant_newsletter[0] == str(DOMAINES["lespass"]["titre"])

    def test_ghost_a_bien_demenage_hors_de_outils_externes(
        self, tenant, remettre_le_module_comme_avant
    ):
        """
        La config Ghost etait perdue au milieu de « Outils externes », entre Webhook et
        Brevo. Elle vit maintenant dans le module « Newsletter ».

        Depuis le passage aux domaines, les pages d'un module ne sont plus dans la
        sidebar : elles sont listees par la PAGE DU MODULE, sous ses onglets. On
        verifie donc les deux choses qui comptent vraiment :
          1. plus aucune entree « Ghost » ne traine dans la sidebar ;
          2. « Serveur Ghost » reste atteignable, depuis la page du module.
        / A module's pages are now listed by its landing page: check Ghost left the
          sidebar and is still reachable from the module page.
        """
        from Administration.admin import dashboard

        client = _client_http(tenant, _superadmin(tenant))
        requete = client.get("/admin/").wsgi_request

        with tenant_context(tenant):
            _poser_letat_du_module(True)
            navigation = dashboard.get_sidebar_navigation(requete)
            sections = dashboard._construire_sections_modules(requete)

        # 1. L'ancienne entree "Ghost" de "Outils externes" a disparu.
        libelles_de_la_sidebar = [
            str(item["title"]) for groupe in navigation for item in groupe["items"]
        ]
        assert "Ghost" not in libelles_de_la_sidebar

        # 2. "Serveur Ghost" est listee par la page du module Newsletter.
        #    C'est le point critique : sans elle, la page serait perdue.
        #    / Critical: without the module page, this page would be unreachable.
        carte = dashboard._carte_des_liens_vers_modeles()
        section_newsletter = [
            section for section in sections if section.get("_slug") == "newsletter"
        ]
        assert section_newsletter, "Le module Newsletter est introuvable."

        par_categorie = dashboard._categoriser_les_pages(
            section_newsletter[0]["items"], carte
        )
        pages_listees = [
            str(page["title"])
            for pages in par_categorie.values()
            for page in pages
        ]
        assert str(_("Serveur Ghost")) in pages_listees, (
            "Serveur Ghost n'est atteignable ni par la sidebar ni par la page du module."
        )
