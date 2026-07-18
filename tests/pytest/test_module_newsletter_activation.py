"""
Activation du module Newsletter : reservee aux superadmins.
/ Newsletter module activation: superadmins only.

LOCALISATION : tests/pytest/test_module_newsletter_activation.py

CE QUE CES TESTS PROTEGENT
--------------------------
Le module Newsletter pilote une instance **Ghost** auto-hebergee. Celle-ci doit d'abord etre
installee et DIMENSIONNEE (la charge serveur depend du volume de mails envoyes). On ne peut
donc pas le laisser s'activer d'un clic.

Regles :
1. Le module est **desactive par defaut**.
2. Seul un **superadmin** peut l'activer.
3. Un gestionnaire ordinaire qui clique ne recoit PAS un refus sec : on lui affiche une
   invitation a contacter l'equipe TiBillet, avec les liens Matrix / Discord / email.
4. Le POST de bascule est protege LUI AUSSI — la modale n'est que de l'affichage, une requete
   forgee la contournerait. **On ne fait jamais confiance a l'interface pour appliquer une
   regle d'acces.**

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
        pytest.skip("Seed demo_data_v2 absent : pas de tenant 'lespass'.")
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


def _superadmin(tenant):
    with tenant_context(tenant):
        utilisateur = TibilletUser.objects.filter(is_superuser=True).first()
    if not utilisateur:
        pytest.skip("Aucun superadmin dans la base de dev.")
    return utilisateur


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
        la valeur reelle, qu'un superadmin peut activer. La lire ici rendrait le test
        dependant de l'etat de la base.
        / Read the FIELD DEFAULT, never get_solo(): the tenant's Configuration holds the
        real value, which a superadmin may have switched on.
        """
        champ = Configuration._meta.get_field("module_newsletter")
        assert champ.default is False


@pytest.mark.django_db
class TestGestionnaireOrdinaire:

    def test_il_voit_la_modale_de_contact_et_pas_le_bouton_dactivation(
        self, tenant, gestionnaire_ordinaire, remettre_le_module_comme_avant
    ):
        """
        Pas un mur, une porte : on lui explique pourquoi, et on lui donne les liens pour
        joindre l'equipe TiBillet.
        """
        with tenant_context(tenant):
            client = _client_http(tenant, gestionnaire_ordinaire)
            reponse = client.get(URL_DE_LA_MODALE)

        assert reponse.status_code == 200
        page = reponse.content.decode()

        # C'est bien la modale de CONTACT, pas celle de confirmation.
        assert 'data-testid="module-modal-contact"' in page
        assert "serveur de newsletter Ghost" in page

        # Les trois canaux de contact sont la.
        assert "contact@tibillet.re" in page
        assert "matrix.to" in page
        assert "discord.gg" in page

        # Et SURTOUT : aucun bouton de bascule.
        assert "module-toggle/module_newsletter" not in page

    def test_un_post_force_est_refuse_403(
        self, tenant, gestionnaire_ordinaire, remettre_le_module_comme_avant
    ):
        """
        SECURITE. La modale n'est que de l'affichage : une requete forgee la contourne.
        Le POST doit refuser tout seul — on ne fait JAMAIS confiance a l'interface pour
        appliquer une regle d'acces.
        """
        with tenant_context(tenant):
            client = _client_http(tenant, gestionnaire_ordinaire)
            _poser_letat_du_module(False)
            reponse = client.post(URL_DE_LA_BASCULE)

        assert reponse.status_code == 403

        with tenant_context(tenant):
            assert Configuration.get_solo().module_newsletter is False, (
                "Un gestionnaire ordinaire a reussi a activer le module par un POST force."
            )


@pytest.mark.django_db
class TestSuperadmin:

    def test_il_voit_la_modale_de_confirmation_normale(
        self, tenant, remettre_le_module_comme_avant
    ):
        with tenant_context(tenant):
            client = _client_http(tenant, _superadmin(tenant))
            reponse = client.get(URL_DE_LA_MODALE)

        assert reponse.status_code == 200
        page = reponse.content.decode()

        # La modale de confirmation, avec son bouton de bascule.
        assert "module-toggle/module_newsletter" in page
        # Et PAS la modale de contact.
        assert 'data-testid="module-modal-contact"' not in page

    def test_il_peut_activer_le_module(self, tenant, remettre_le_module_comme_avant):
        with tenant_context(tenant):
            client = _client_http(tenant, _superadmin(tenant))
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
        Le menu « Newsletter » (et donc « Serveur Ghost ») n'existe que module actif.
        """
        from Administration.admin.dashboard import get_sidebar_navigation

        client = _client_http(tenant, _superadmin(tenant))

        def _titres_de_la_sidebar():
            """Rend la sidebar via une vraie requete admin, et liste ses groupes."""
            requete = client.get("/admin/").wsgi_request
            with tenant_context(tenant):
                navigation = get_sidebar_navigation(requete)
            return [str(groupe["title"]) for groupe in navigation]

        # --- Module DESACTIVE : pas de groupe Newsletter ---
        with tenant_context(tenant):
            _poser_letat_du_module(False)
        assert "Newsletter" not in _titres_de_la_sidebar()

        # --- Module ACTIF : le groupe apparait ---
        with tenant_context(tenant):
            _poser_letat_du_module(True)
        assert "Newsletter" in _titres_de_la_sidebar()

    def test_ghost_a_bien_demenage_hors_de_outils_externes(
        self, tenant, remettre_le_module_comme_avant
    ):
        """
        La config Ghost etait perdue au milieu de « Outils externes », entre Webhook et
        Brevo. Elle vit maintenant dans le groupe « Newsletter ».
        """
        from Administration.admin.dashboard import get_sidebar_navigation

        client = _client_http(tenant, _superadmin(tenant))
        requete = client.get("/admin/").wsgi_request

        with tenant_context(tenant):
            _poser_letat_du_module(True)
            navigation = get_sidebar_navigation(requete)

        # Les titres de la sidebar sont TRADUITS ("External tools" -> "Outils externes") :
        # on ne peut pas les chercher par leur cle anglaise. On collecte donc TOUS les
        # libelles d'items, tous groupes confondus, et on verifie ou vit Ghost.
        # / Sidebar titles are TRANSLATED: collect every item label instead.
        tous_les_items = []
        for groupe in navigation:
            for item in groupe["items"]:
                tous_les_items.append((str(groupe["title"]), str(item["title"])))

        libelles = [libelle for _titre_du_groupe, libelle in tous_les_items]

        # L'ancienne entree "Ghost" de "Outils externes" a disparu...
        assert "Ghost" not in libelles
        # ...et "Serveur Ghost" existe, dans le groupe "Newsletter".
        groupe_de_ghost = [
            titre for titre, libelle in tous_les_items if libelle == "Serveur Ghost"
        ]
        assert groupe_de_ghost, "Serveur Ghost est introuvable dans la sidebar."
        assert groupe_de_ghost[0] == str(_("Newsletter"))
