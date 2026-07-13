import os
import subprocess
import pytest

try:
    import urllib3
except Exception:  # pragma: no cover - optional dependency for warnings
    urllib3 = None


def pytest_addoption(parser):
    """Add CLI options to inject API key and base URL into the test session.

    Usage examples:
      poetry run pytest -qs tests/pytest --api-key <KEY>
      poetry run pytest -qs tests/pytest --api-key <KEY> --api-base-url https://lespass.tibillet.localhost
    """
    parser.addoption(
        "--api-key",
        action="store",
        default=None,
        help="API key to use for Authorization header (sets env var API_KEY)",
    )
    parser.addoption(
        "--api-base-url",
        action="store",
        default=None,
        help="Override base URL for API tests (sets env var API_BASE_URL)",
    )


@pytest.fixture(autouse=True, scope="session")
def _inject_cli_env(request):
    """Autouse session fixture to export CLI options into environment vars.

    Tests already read API_KEY and API_BASE_URL from the environment, so
    this allows passing them via pytest CLI flags without editing tests.
    """

    api_key = request.config.getoption("--api-key") or os.getenv("API_KEY")

    if not api_key:
        # Essayer d'abord via docker exec (depuis la machine hote).
        # Si 'docker' n'existe pas (on est dans le conteneur), appeler manage.py directement.
        # / Try docker exec first (from host). If 'docker' not found (inside container),
        # call manage.py directly.
        try:
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-e",
                    "TEST=1",
                    "lespass_django",
                    "poetry",
                    "run",
                    "python",
                    "manage.py",
                    "test_api_key",
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                api_key = result.stdout.strip()
        except FileNotFoundError:
            # On est dans le conteneur — 'docker' n'existe pas ici.
            # / We're inside the container — 'docker' binary doesn't exist here.
            try:
                result = subprocess.run(
                    ["python", "manage.py", "test_api_key"],
                    capture_output=True,
                    text=True,
                    cwd="/DjangoFiles",
                    env={**os.environ, "TEST": "1"},
                )
                if result.returncode == 0:
                    api_key = result.stdout.strip()
            except Exception:
                pass

    if not api_key:
        pytest.fail(
            "API key is empty. Provide --api-key/ API_KEY env or ensure docker "
            "returns a key via manage.py test_api_key."
        )

    os.environ["API_KEY"] = api_key

    # Silence HTTPS warnings in test environment (self-signed certs on localhost)
    if urllib3 is not None:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    base = request.config.getoption("--api-base-url")
    if base:
        os.environ["API_BASE_URL"] = base.rstrip("/")


# Les 5 fichiers du flow API v2 Event doivent s'executer dans CET ordre : ils se
# partagent le meme evenement, cree par le premier et supprime par le dernier.
# Chacun ne contient qu'un seul test, ecrit sous forme de fonction.
# / The 5 files of the API v2 Event flow must run in THIS order: they share the same
# event, created by the first file and deleted by the last one.
ORDRE_DU_FLOW_API_V2_EVENT = {
    "test_event_create.py": 0,
    "test_events_list.py": 1,
    "test_event_retrieve.py": 2,
    "test_event_link_address.py": 3,
    "test_event_delete.py": 4,
}

# Rang de tous les autres tests : ils passent apres le flow, sans etre reordonnes.
# / Rank of every other test: they run after the flow, without being reordered.
RANG_DES_AUTRES_TESTS = 10


def pytest_collection_modifyitems(config, items):
    """
    Ordonne les 5 fichiers du flow API v2 Event. Ne touche a RIEN d'autre.
    / Orders the 5 files of the API v2 Event flow. Touches NOTHING else.

    LOCALISATION : tests/pytest/conftest.py

    REGLE : ne trier QUE des fichiers entiers. NE JAMAIS trier par nom de test.

    Trier par sous-chaine du nom d'un test (« create », « list »...) casse la suite :

    1. Les tests sont ecrits en francais, et le mot « liste » CONTIENT « list ». Un
       test nomme `test_retourne_liste_vide_...` part alors dans un autre groupe que
       ses tests freres.

    2. Sa classe se retrouve donc COUPEE EN DEUX BLOCS non contigus. pytest rejoue
       `setUpClass` ET `tearDownClass` a chaque bloc — et le `tearDownClass` d'un
       `FastTenantTestCase` remet la connexion sur `public`, ce qui casse l'etat
       attendu par le bloc suivant. Des dizaines d'erreurs en suite complete, alors
       que chaque fichier passe seul.

    La cle `(rang_du_fichier, chemin_du_fichier)` garantit que tous les tests d'un
    fichier partagent la meme cle : le tri de Python etant stable, aucune classe ne
    peut etre fragmentee.
    / RULE: only sort whole files, NEVER by test name. French test names contain the
    English keywords ("liste" contains "list"), which splits a class into two
    non-contiguous blocks and re-runs setUpClass/tearDownClass in the middle.
    """

    def sort_key(item):
        chemin_du_fichier = str(item.fspath)
        nom_du_fichier = os.path.basename(chemin_du_fichier)

        rang_du_fichier = ORDRE_DU_FLOW_API_V2_EVENT.get(
            nom_du_fichier,
            RANG_DES_AUTRES_TESTS,
        )

        # On renvoie le chemin en second : tous les tests d'un meme fichier gardent
        # la meme cle de tri. Le tri de Python etant stable, leur ordre de collecte
        # est preserve tel quel, et aucune classe n'est fragmentee.
        # / The path comes second: all tests of a file share the same sort key. Python's
        # sort being stable, their collection order is preserved and no class is split.
        return (rang_du_fichier, chemin_du_fichier)

    items.sort(key=sort_key)


# --- Fixtures partagees portees depuis la V2 (lespass-main) ---
# Avant : chaque fichier de test redeclarait django_db_setup et
# _enable_db_access localement. Ces fixtures centralisees les remplacent.
# Les declarations locales restantes priment sans conflit (meme comportement).
# / Shared fixtures ported from V2 (lespass-main).
# Before: each test file redeclared django_db_setup and _enable_db_access
# locally. These centralized fixtures replace them. Remaining local
# declarations take precedence without conflict (same behavior).


@pytest.fixture(scope="session")
def api_client(_inject_cli_env):
    """Client Django in-process — resout le tenant 'lespass' via HTTP_HOST.
    / In-process Django test client — resolves 'lespass' tenant via HTTP_HOST.
    """
    from django.test import Client
    return Client(HTTP_HOST='lespass.tibillet.localhost')


@pytest.fixture
def auth_headers(_inject_cli_env):
    """En-tetes d'auth pour le test client Django.
    Scope=function : verifie que l'APIKey stockee dans env pointe toujours
    vers une ligne existante en DB (lespass). Si elle a ete purgee par
    un test intermediaire, on en regenere une via `manage.py test_api_key`.
    / Function-scoped: verifies the APIKey stored in env still points to
    an existing DB row. If purged by a previous test, regenerate it.
    """
    from django_tenants.utils import tenant_context
    from rest_framework_api_key.models import APIKey
    from Customers.models import Client as TenantClient

    api_key = os.environ.get("API_KEY")
    needs_regen = not api_key
    if not needs_regen:
        try:
            tenant = TenantClient.objects.get(schema_name="lespass")
            with tenant_context(tenant):
                APIKey.objects.get_from_key(api_key)
        except Exception:
            needs_regen = True

    if needs_regen:
        import subprocess
        try:
            result = subprocess.run(
                ["python", "manage.py", "test_api_key"],
                capture_output=True, text=True, cwd="/DjangoFiles",
                env={**os.environ, "TEST": "1"},
            )
            if result.returncode == 0:
                api_key = result.stdout.strip()
                os.environ["API_KEY"] = api_key
        except Exception:
            pass

    return {"HTTP_AUTHORIZATION": f"Api-Key {api_key}"}


@pytest.fixture(scope="session")
def admin_user(_inject_cli_env):
    """Utilisateur admin du tenant lespass (doit exister dans la DB dev).
    / Admin user of the lespass tenant (must exist in dev DB)."""
    from django_tenants.utils import schema_context
    from AuthBillet.models import TibilletUser
    from Customers.models import Client
    tenant = Client.objects.get(schema_name='lespass')
    with schema_context('lespass'):
        email = os.environ.get('ADMIN_EMAIL', 'jturbeaux@pm.me')
        user = TibilletUser.objects.get(email=email)
        # Apres un flush DB, is_active peut etre False (signal pre_save).
        # / After a DB flush, is_active can be False (pre_save signal).
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])
        user.client_admin.add(tenant)
        return user


@pytest.fixture(scope="session")
def admin_client(admin_user):
    """Client Django authentifie comme admin pour l'admin Django.
    / Django client authenticated as admin for Django admin site."""
    from django.test import Client as DjangoClient
    client = DjangoClient(HTTP_HOST='lespass.tibillet.localhost')
    client.force_login(admin_user)
    return client


@pytest.fixture(scope="session")
def tenant():
    """Le tenant 'lespass'. / The 'lespass' tenant."""
    from Customers.models import Client
    return Client.objects.get(schema_name='lespass')


@pytest.fixture(scope="session")
def django_db_setup():
    """Pas de creation de test database — les tests utilisent la base dev existante.
    / Skip test database creation — tests use the existing dev database (django-tenants).
    """
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access_for_all(django_db_blocker):
    """Desactiver le bloqueur d'acces DB de pytest-django.
    Les tests existants accedent a la base dev directement (django-tenants).
    / Disable pytest-django's database blocker.
    Existing tests access the dev database directly (django-tenants).
    """
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


@pytest.fixture(autouse=True, scope="class")
def _connexion_sur_le_schema_public_avant_chaque_classe(request):
    """
    Garantit que la connexion est sur `public` AVANT le `setUpClass` de chaque classe.
    / Ensures the connection sits on `public` BEFORE each class's `setUpClass`.

    LOCALISATION : tests/pytest/conftest.py

    POURQUOI :
    Deux choses « collent » la connexion sur un tenant, et personne ne la decolle :
    - le middleware django-tenants, des qu'un test fait une requete avec le client de
      test Django sur `lespass.tibillet.localhost` ;
    - les `setUp()` des `FastTenantTestCase` du projet, qui appellent
      `connection.set_tenant(...)` a chaque test.

    (`FastTenantTestCase.tearDownClass`, lui, remet bien `public` — mais seulement en fin
    de CLASSE. Il ne rattrape donc pas un test-fonction qui a colle `lespass` juste avant.)

    Or `FastTenantTestCase.setUpClass` doit CREER son tenant de test quand le schema
    n'existe pas encore, et django-tenants l'interdit hors du schema public :
        Exception: Can't create tenant outside the public schema. Current schema is lespass.

    Sans cette remise a zero, le premier test qui laisse la connexion sur `lespass` fait
    echouer tous les `FastTenantTestCase` dont le schema n'existe pas (~50 erreurs en
    suite complete, alors que chaque fichier passe seul).

    POURQUOI EN SETUP DE CLASSE, ET SURTOUT PAS EN TEARDOWN DE TEST :
    une premiere version remettait `public` apres CHAQUE test. Erreur : les finalizers
    des fixtures de portee superieure (class, module, session) s'executent APRES ceux de
    portee test. Ces finalizers, qui nettoient des objets du tenant, tombaient alors sur
    `public` et levaient :
        ProgrammingError: relation "BaseBillet_ticket" does not exist
    En agissant en SETUP de classe, on ne touche a aucun teardown.
    / Do NOT restore in test teardown: higher-scoped finalizers run afterwards and would
    hit `public` while cleaning up tenant objects.

    POURQUOI SEULEMENT POUR LES `FastTenantTestCase` :
    ces classes-la reposent le tenant elles-memes (leur `setUpClass` fait `set_tenant`),
    donc les mettre sur `public` juste avant est sans effet de bord. Les classes de test
    ORDINAIRES, elles, ne reposent aucun tenant : leur imposer `public` casserait leurs
    fixtures, dont le nettoyage tomberait sur un schema sans les tables du tenant.
    On ne change donc l'etat de la connexion QUE la ou c'est necessaire.
    / Only for FastTenantTestCase: they re-set the tenant themselves in setUpClass, so
    forcing `public` right before is harmless. Ordinary test classes set no tenant, and
    forcing `public` on them would break their fixtures' cleanup.

    Voir tests/PIEGES.md 12.5 et 12.5.bis.
    """
    from django.db import connection
    from django_tenants.test.cases import FastTenantTestCase

    classe_de_test = getattr(request, "cls", None)

    est_un_fast_tenant_test_case = (
        classe_de_test is not None
        and isinstance(classe_de_test, type)
        and issubclass(classe_de_test, FastTenantTestCase)
    )

    if est_un_fast_tenant_test_case:
        connection.set_schema_to_public()

    yield


@pytest.fixture
def mock_stripe():
    """Patche les appels Stripe pour eviter le reseau.
    Retourne un namespace avec les mocks pour inspection.
    / Patches Stripe API calls to avoid network.
    Returns a namespace with mocks for inspection.

    Usage :
        def test_something(mock_stripe, ...):
            # mock_stripe.session contient le mock Session
            # mock_stripe.session.id == "cs_test_mock_session"
    """
    from unittest.mock import patch, MagicMock
    from types import SimpleNamespace

    fake_session = MagicMock()
    fake_session.id = "cs_test_mock_session"
    fake_session.url = "https://checkout.stripe.com/c/pay/fake_session"
    fake_session.payment_intent = "pi_test_mock_intent"
    fake_session.payment_status = "paid"
    fake_session.mode = "payment"
    fake_session.metadata = {}
    fake_session.subscription = None
    fake_session.status = "complete"

    fake_pi = MagicMock()
    fake_pi.payment_method_types = ["card"]
    fake_pi.payment_method_options = {}

    with (
        patch("stripe.checkout.Session.create", return_value=fake_session) as mock_create,
        patch("stripe.checkout.Session.retrieve", return_value=fake_session) as mock_retrieve,
        patch("stripe.PaymentIntent.retrieve", return_value=fake_pi) as mock_pi,
        patch("stripe.Subscription.retrieve", return_value=MagicMock(id="sub_test_mock")) as mock_sub,
        patch("stripe.Subscription.modify", return_value=MagicMock()) as mock_sub_mod,
    ):
        yield SimpleNamespace(
            session=fake_session,
            pi=fake_pi,
            mock_create=mock_create,
            mock_retrieve=mock_retrieve,
            mock_pi=mock_pi,
        )
