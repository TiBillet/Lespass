import os
import subprocess
import pytest


def pytest_addoption(parser):
    """Add CLI option to inject API key into the test session.

    Usage examples:
      poetry run pytest -qs tests/pytest --api-key <KEY>
    """
    parser.addoption(
        "--api-key",
        action="store",
        default=None,
        help="API key to use for Authorization header (sets env var API_KEY)",
    )


@pytest.fixture(autouse=True, scope="session")
def _inject_cli_env(request):
    """Autouse session fixture to export CLI options into environment vars.

    Tests already read API_KEY from the environment, so
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
    Chaque test obtient ainsi des en-tetes auth valides, independamment de
    ce que les tests precedents ont fait.

    / Function-scoped: verifies the APIKey stored in env still points to
    an existing DB row (lespass). If a previous test purged it, regenerate
    via `manage.py test_api_key`. Each test thus gets valid auth headers,
    independent of prior tests.
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
        except APIKey.DoesNotExist:
            needs_regen = True
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
        # S'assurer que l'utilisateur est admin du tenant et actif.
        # Apres un flush DB, is_active peut etre False (signal pre_save).
        # / Ensure the user is admin of the tenant and active.
        # After a DB flush, is_active can be False (pre_save signal).
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


@pytest.fixture
def terminal_client(tenant):
    """
    Client Django authentifie comme TermUser Laboutik (session posee).
    / Django Client authenticated as a Laboutik TermUser (session set).

    Remplace auth_headers (header Api-Key V1) pour les tests V2 qui utilisent
    les routes protegees par HasLaBoutikTerminalAccess.
    / Replaces auth_headers (V1 Api-Key header) for V2 tests using routes
    protected by HasLaBoutikTerminalAccess.

    Usage :
        def test_something(terminal_client):
            response = terminal_client.get('/laboutik/caisse/')
            assert response.status_code == 200
    """
    import uuid
    from django.test import Client
    from django_tenants.utils import tenant_context
    from AuthBillet.models import TermUser

    email = f'test-{uuid.uuid4()}@terminals.local'
    with tenant_context(tenant):
        term_user = TermUser.objects.create(
            email=email,
            username=email,
            terminal_role='LB',
            accept_newsletter=False,
        )
        # Backend explicite pour force_login (plusieurs backends peuvent etre configures).
        # / Explicit backend for force_login (multiple backends may be configured).
        term_user.backend = 'django.contrib.auth.backends.ModelBackend'

    client = Client(HTTP_HOST=f'{tenant.schema_name}.tibillet.localhost')
    client.force_login(term_user)

    yield client

    # Cleanup : supprimer le TermUser cree pour ce test.
    # / Cleanup: delete the TermUser created for this test.
    with tenant_context(tenant):
        term_user.delete()


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


def pytest_runtest_setup(item):
    """
    Avant chaque test qui herite de FastTenantTestCase, force
    connection.schema_name = 'public'. FastTenantTestCase.setUpClass exige
    le schema public pour creer le test tenant — si un test precedent a
    laisse connection dans un schema tenant via un tenant_context/schema_context
    mal restaure, setUpClass crashe avec :
      "Can't create tenant outside the public schema. Current schema is X"

    / Before each FastTenantTestCase, force connection.schema_name = 'public'.
    FastTenantTestCase.setUpClass requires public schema to create the test
    tenant. If a previous test leaked a tenant schema via an improperly
    restored tenant_context/schema_context, setUpClass crashes.
    """
    try:
        from django.db import connection
        from django_tenants.test.cases import FastTenantTestCase
        cls = getattr(item, "cls", None)
        if cls is not None and issubclass(cls, FastTenantTestCase):
            if connection.schema_name != "public":
                connection.set_schema_to_public()
    except Exception:
        pass


def pytest_collection_modifyitems(config, items):
    """
    Reorder tests to ensure the following sequence for API v2 Event flow:
    1) create
    2) list
    3) retrieve
    4) link (address linking)
    5) delete
    Other tests keep their relative order.
    """

    def sort_key(item):
        name = item.name.lower()
        path = str(item.fspath)
        # Priority by function/test name
        if "create" in name:
            return (0, path)
        if "list" in name:
            return (1, path)
        if "retrieve" in name:
            return (2, path)
        # ensure link-address tests run before delete cleanup
        if "link" in name:
            return (3, path)
        if "delete" in name:
            return (4, path)
        # Everything else afterwards
        return (10, path)

    items.sort(key=sort_key)
