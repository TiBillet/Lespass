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


@pytest.fixture(scope="session")
def auth_headers(_inject_cli_env):
    """En-tetes d'auth pour le test client Django (**auth_headers dans chaque appel).
    / Auth headers for Django test client (**auth_headers in each call).
    """
    api_key = os.environ["API_KEY"]
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
        # S'assurer que l'utilisateur est admin du tenant
        # / Ensure the user is admin of the tenant
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
