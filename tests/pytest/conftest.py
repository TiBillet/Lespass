import os
import subprocess
import sys
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
                # sys.executable = l'interpreteur qui fait tourner pytest, donc
                # celui du virtualenv. `python` nu pointerait sur le Python
                # systeme du conteneur, qui n'a pas Django installe.
                # / sys.executable = the interpreter running pytest, i.e. the
                # virtualenv's. A bare `python` would resolve to the container's
                # system Python, which has no Django installed.
                result = subprocess.run(
                    [sys.executable, "manage.py", "test_api_key"],
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
        result = subprocess.run(
            ["python", "manage.py", "test_api_key"],
            capture_output=True, text=True, cwd="/DjangoFiles",
            env={**os.environ, "TEST": "1"},
        )
        # Une regeneration ratee echoue ICI : rendre l'ancienne cle ferait echouer le
        # test plus loin, en 403, sans lien apparent avec la vraie cause.
        # / A failed regeneration fails HERE, not later as an unrelated 403.
        if result.returncode != 0:
            pytest.fail(
                f"manage.py test_api_key a echoue (rc={result.returncode}) : {result.stderr[-500:]}"
            )
        api_key = result.stdout.strip()
        os.environ["API_KEY"] = api_key

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


@pytest.fixture(autouse=True)
def _archiver_les_evenements_crees():
    """Après chaque test, archive les événements créés par les tests Stripe
    (base de dev partagée, sans rollback ; les autres données restent en base).
    / After each test, archives the events created by the Stripe tests
    (shared dev DB, no rollback; the other data stays).
    """
    yield
    import fabriques_reservation

    if fabriques_reservation.EVENEMENTS_A_ARCHIVER:
        fabriques_reservation.archiver_evenements_crees()


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

    LES MONTANTS RENVOYES PAR STRIPE (centimes)
    - `session.amount_total` est calcule AU MOMENT OU ON LE LIT : c'est la somme des
      `total_catalogue` des articles de la vente d'origine du `Paiement_stripe` le plus
      recent qui porte l'id de la session simulee. Pas de paiement, ou pas de vente : 0.
    - `stripe.Invoice.retrieve(id)` renvoie `facture` : `status` = "paid", et
      `amount_paid` calcule de la meme facon, pour le paiement qui porte cet id de
      facture. La facture simulee n'a ni `lines` ni `parent` : un test qui cree le
      paiement d'une echeance (`new_entry_from_stripe_subscription_invoice`) patche sa
      propre facture.
    Le montant n'est donc jamais fixe : un montant fixe ferait apparaitre un ecart
    d'encaissement dans tous les tests, et 0 simulerait une facture payee par le solde
    du client. Un `MagicMock` ne convient pas non plus : `int(MagicMock())` vaut 1.
    / Stripe amounts (cents) are computed when read: sum of `total_catalogue` of the
    items of the original sale of the newest payment carrying the simulated session id
    (or invoice id). No payment or no sale: 0.

    IMPOSER UN MONTANT (test d'ecart d'encaissement) : une simple affectation.
        mock_stripe.session.amount_total = 2400
        mock_stripe.facture.amount_paid = 0
    La valeur imposee est rendue telle quelle jusqu'a la fin du test.
    / To impose an amount, just assign it; it is returned as is until the end of the test.
    """
    from unittest.mock import patch, MagicMock
    from types import SimpleNamespace

    def total_catalogue_de_la_vente_du_paiement_le_plus_recent(paiements_candidats):
        """
        Somme des `total_catalogue` des articles de la vente d'origine du paiement le
        plus recent parmi `paiements_candidats`. Pas de paiement, ou pas de vente : 0.
        Lu dans le schema courant : le test est deja dans le lieu quand Stripe est lu.
        / Sum of the catalogue totals of the newest payment's original sale; 0 otherwise.
        """
        from BaseBillet.models import LigneArticle

        paiement_le_plus_recent = paiements_candidats.order_by("-order_date").first()
        if paiement_le_plus_recent is None:
            return 0
        if paiement_le_plus_recent.vente_id is None:
            return 0

        total_catalogue_des_articles = 0
        for article in LigneArticle.objects.filter(
            vente_id=paiement_le_plus_recent.vente_id
        ):
            total_catalogue_des_articles += article.total_catalogue
        return total_catalogue_des_articles

    # Les montants imposes par le test, par nom d'attribut.
    # / Amounts imposed by the test, by attribute name.
    montants_imposes_par_le_test = {}

    def lire_amount_total(session):
        if "amount_total" in montants_imposes_par_le_test:
            return montants_imposes_par_le_test["amount_total"]
        from BaseBillet.models import Paiement_stripe

        paiements_de_la_session = Paiement_stripe.objects.filter(
            checkout_session_id_stripe=session.id
        )
        return total_catalogue_de_la_vente_du_paiement_le_plus_recent(
            paiements_de_la_session
        )

    def imposer_amount_total(session, montant_impose):
        montants_imposes_par_le_test["amount_total"] = montant_impose

    def lire_amount_paid(facture):
        if "amount_paid" in montants_imposes_par_le_test:
            return montants_imposes_par_le_test["amount_paid"]
        from BaseBillet.models import Paiement_stripe

        paiements_de_la_facture = Paiement_stripe.objects.filter(
            invoice_stripe=facture.id
        )
        return total_catalogue_de_la_vente_du_paiement_le_plus_recent(
            paiements_de_la_facture
        )

    def imposer_amount_paid(facture, montant_impose):
        montants_imposes_par_le_test["amount_paid"] = montant_impose

    fake_session = MagicMock()
    fake_session.id = "cs_test_mock_session"
    fake_session.url = "https://checkout.stripe.com/c/pay/fake_session"
    fake_session.payment_intent = "pi_test_mock_intent"
    fake_session.payment_status = "paid"
    fake_session.mode = "payment"
    fake_session.metadata = {}
    fake_session.subscription = None
    fake_session.status = "complete"
    # Chaque MagicMock a sa PROPRE classe : la propriete posee sur `type(...)` ne
    # concerne que cet objet (ni les autres mocks, ni ses attributs enfants).
    # / Each MagicMock has its OWN class: the property only affects this object.
    type(fake_session).amount_total = property(lire_amount_total, imposer_amount_total)

    fake_facture = MagicMock()
    fake_facture.id = None
    fake_facture.status = "paid"
    type(fake_facture).amount_paid = property(lire_amount_paid, imposer_amount_paid)

    def relire_la_facture_chez_stripe(identifiant_de_la_facture, **options_stripe):
        """`stripe.Invoice.retrieve` simule : la facture demandee, payee.
        / Simulated `stripe.Invoice.retrieve`: the requested invoice, paid."""
        fake_facture.id = identifiant_de_la_facture
        return fake_facture

    fake_pi = MagicMock()
    fake_pi.payment_method_types = ["card"]
    fake_pi.payment_method_options = {}

    with (
        patch("stripe.checkout.Session.create", return_value=fake_session) as mock_create,
        patch("stripe.checkout.Session.retrieve", return_value=fake_session) as mock_retrieve,
        patch("stripe.PaymentIntent.retrieve", return_value=fake_pi) as mock_pi,
        patch("stripe.Subscription.retrieve", return_value=MagicMock(id="sub_test_mock")) as mock_sub,
        patch("stripe.Subscription.modify", return_value=MagicMock()) as mock_sub_mod,
        patch(
            "stripe.Invoice.retrieve", side_effect=relire_la_facture_chez_stripe
        ) as mock_invoice,
    ):
        yield SimpleNamespace(
            session=fake_session,
            facture=fake_facture,
            pi=fake_pi,
            mock_create=mock_create,
            mock_retrieve=mock_retrieve,
            mock_pi=mock_pi,
            mock_invoice=mock_invoice,
        )
