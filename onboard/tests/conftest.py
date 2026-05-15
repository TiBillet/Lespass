"""
Conftest pytest local pour les tests onboard.
/ Local pytest conftest for onboard tests.

LOCALISATION: onboard/tests/conftest.py

Strategie (pattern V2 de lespass-main) :
  - On REUTILISE la base de donnees dev existante (pas de "test DB" cree
    a chaque run, pas de migrations replay). C'est ce qui rend les tests
    rapides (~30s vs ~6min).
  - Les tests modifient donc la VRAIE base dev : chaque test doit nettoyer
    ce qu'il cree, ou utiliser des fixtures function-scoped avec teardown.
  - Pas de `Client.objects.create(auto_create_schema=True)` dans setUp :
    on consomme le tenant `lespass` deja en place + les slots du pool
    WAITING_CONFIG existants.

/ Strategy (V2 pattern from lespass-main):
  - REUSE the existing dev database (no "test DB" created every run, no
    migrations replayed). This makes tests fast (~30s vs ~6min).
  - Tests therefore modify the REAL dev DB: each test must clean up what
    it creates, or use function-scoped fixtures with teardown.
  - No `Client.objects.create(auto_create_schema=True)` in setUp: we
    consume the already-present `lespass` tenant + existing WAITING_CONFIG
    pool slots.

PIEGE : si tu lances les tests pendant que tu fais du dev a la main sur
le meme tenant lespass, tu peux avoir des collisions. Lance les tests
quand la DB dev est au repos.
/ PITFALL: if you run tests while doing manual dev on the same `lespass`
tenant, collisions may occur. Run tests with the dev DB at rest.
"""

import pytest


# ---------------------------------------------------------------------------
# Fixtures cles : reutiliser la DB dev au lieu de creer une test DB.
# / Key fixtures: reuse the dev DB instead of creating a test DB.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def django_db_setup():
    """
    Override la fixture pytest-django par defaut : on ne cree pas de test DB.
    On utilise la base de donnees dev existante.
    / Override pytest-django's default fixture: don't create a test DB.
    We use the existing dev database.
    """
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access_for_all(django_db_blocker):
    """
    Desactive le bloqueur d'acces DB de pytest-django pour toute la session.
    Sans ca, chaque test devrait porter `@pytest.mark.django_db`.
    / Disable pytest-django's DB access blocker for the whole session.
    Without this, each test would need `@pytest.mark.django_db`.
    """
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


# ---------------------------------------------------------------------------
# Fixtures utilitaires partagees par les tests onboard.
# / Utility fixtures shared by onboard tests.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def lespass_tenant():
    """
    Renvoie le tenant `lespass` existant en DB dev.
    / Returns the existing `lespass` tenant from the dev DB.
    """
    from Customers.models import Client
    return Client.objects.get(schema_name="lespass")


@pytest.fixture
def cleanup_waiting_configs():
    """
    Suit les UUIDs des WaitingConfiguration crees pendant le test et les
    supprime au teardown. Usage :

        def test_xxx(cleanup_waiting_configs):
            wc = WaitingConfiguration.objects.create(...)
            cleanup_waiting_configs(wc)
            ...

    / Tracks UUIDs of WaitingConfigurations created during the test and
    deletes them at teardown.
    """
    from django_tenants.utils import schema_context
    from MetaBillet.models import WaitingConfiguration

    tracked_uuids = []

    def _track(wc):
        tracked_uuids.append(wc.uuid)
        return wc

    yield _track

    if tracked_uuids:
        with schema_context("meta"):
            WaitingConfiguration.objects.filter(uuid__in=tracked_uuids).delete()


@pytest.fixture
def cleanup_clients():
    """
    Suit les schema_names des Client crees pendant le test et les supprime
    au teardown.
    Usage :

        def test_xxx(cleanup_clients):
            tenant = Client.objects.create(...)
            cleanup_clients(tenant)

    PIEGE : on n'utilise PAS `Client.objects.filter(...).delete()` car le
    collector Django essaie de cascader sur les M2M reverse (en particulier
    `BaseBillet_configuration_federated_with`), qui n'existent pas dans
    le schema public — l'ORM crashe alors avec
    `relation "BaseBillet_configuration_federated_with" does not exist`.
    On fait donc une suppression SQL brute des lignes dans
    `customers_client` + `customers_domain`. Pour les tenants sans schema
    Postgres reel (cree avec `auto_create_schema=False`), cela suffit ;
    pour les autres, le schema Postgres restera en base mais ce n'est pas
    bloquant pour des tests qui reutilisent la DB dev (on peut purger a la
    main si besoin).

    / Tracks schema_names of Clients created during the test and deletes
    them at teardown.

    PITFALL: do NOT use `Client.objects.filter(...).delete()` — Django's
    deletion collector cascades over reverse M2M tables (notably
    `BaseBillet_configuration_federated_with`) which don't exist in the
    public schema; the ORM crashes with
    `relation "..._federated_with" does not exist`. We therefore raw-SQL
    delete rows from `customers_client` + `customers_domain`. For tenants
    without a real Postgres schema (created with auto_create_schema=False),
    this is sufficient; for the others, the Postgres schema lingers but
    that's not blocking for dev-DB tests.
    """
    from django.db import connection

    tracked_schema_names = []

    def _track(client):
        tracked_schema_names.append(client.schema_name)
        return client

    yield _track

    if tracked_schema_names:
        # Suppression brute (sans cascade Django) dans le schema public.
        # / Raw delete (no Django cascade) inside the public schema.
        previous_schema = connection.schema_name
        connection.set_schema_to_public()
        try:
            with connection.cursor() as cur:
                # Noms de table avec majuscule -> guillemets obligatoires
                # (le projet n'a pas active le lowercase de Django).
                # / Mixed-case tables require quoting (project doesn't enforce
                # lowercase table names).
                # Domain d'abord (FK vers Client). / Domain first (FK to Client).
                # PK de Client = uuid (pas id). / Client PK is `uuid` (not id).
                cur.execute(
                    'DELETE FROM "Customers_domain" WHERE tenant_id IN ('
                    '  SELECT uuid FROM "Customers_client" WHERE schema_name = ANY(%s)'
                    ')',
                    [tracked_schema_names],
                )
                cur.execute(
                    'DELETE FROM "Customers_client" WHERE schema_name = ANY(%s)',
                    [tracked_schema_names],
                )
        finally:
            # Restaure le schema courant si modifie.
            # / Restore the previous schema if changed.
            if previous_schema and previous_schema != "public":
                connection.set_schema(previous_schema)


@pytest.fixture
def cleanup_invitations():
    """
    Suit les OnboardInvitation crees pendant le test et les supprime au
    teardown.
    / Tracks OnboardInvitations created during the test and deletes at
    teardown.
    """
    from onboard.models import OnboardInvitation

    tracked_ids = []

    def _track(inv):
        tracked_ids.append(inv.pk)
        return inv

    yield _track

    if tracked_ids:
        OnboardInvitation.objects.filter(pk__in=tracked_ids).delete()
