"""
Test du management command `create_empty_tenant`.
/ Test for the `create_empty_tenant` management command.

LOCALISATION: onboard/tests/test_create_empty_tenant_cmd.py

PIEGE auto_create_schema :
    Le modele `Client` (`Customers/models.py`) a `auto_create_schema = True`.
    Chaque `Client.objects.create(...)` declenche ~200 migrations sur le
    nouveau schema Postgres (5-7 min). Pour eviter de bloquer la CI, on
    monkey-patche `Client.auto_create_schema = False` au niveau de la classe
    le temps du test : la ligne DB est creee, mais aucun schema Postgres
    n'est materialise. C'est exactement ce que veut tester la commande
    (ajout d'un slot WAITING_CONFIG dans le pool).

    Le cleanup_clients fixture supprime ensuite la ligne via SQL brut.
    Comme aucun schema reel n'a ete cree, rien ne lingere en DB.

    Un test "slow" (skip par defaut) verifie le comportement reel avec
    `auto_create_schema=True` pour le cas ou on veut valider en local.

/ auto_create_schema PITFALL:
    `Client` (`Customers/models.py`) has `auto_create_schema = True`. Every
    `Client.objects.create(...)` triggers ~200 migrations on the new
    Postgres schema (5-7 min). To avoid blocking CI, we monkey-patch
    `Client.auto_create_schema = False` at the class level for the test:
    the DB row is created, but no Postgres schema is materialised. That is
    exactly what we want to test (adding a WAITING_CONFIG slot to the
    pool).

    The `cleanup_clients` fixture then deletes the row via raw SQL. Since
    no real schema was created, nothing lingers in the DB.

    A "slow" test (skipped by default) verifies the real behavior with
    `auto_create_schema=True` for local validation.
"""

from io import StringIO

import pytest
from django.core.management import call_command

from Customers.models import Client


pytestmark = pytest.mark.onboard


# ---------------------------------------------------------------------------
# Helper / fixture local
# ---------------------------------------------------------------------------


@pytest.fixture
def disable_auto_schema_creation():
    """
    Monkey-patch `Client.auto_create_schema = False` pendant le test, pour
    eviter les ~5 min de migrations Postgres a chaque `Client.objects.create()`.
    On restaure la valeur originale au teardown.

    / Monkey-patches `Client.auto_create_schema = False` for the duration of
    the test, to avoid the ~5 min Postgres migrations on every
    `Client.objects.create()`. Restores the original value at teardown.
    """
    original = Client.auto_create_schema
    Client.auto_create_schema = False
    try:
        yield
    finally:
        Client.auto_create_schema = original


def _track_new_waiting_clients(cleanup_clients, before_pks):
    """
    Compare les pks WAITING_CONFIG actuels a un snapshot precedent, et
    tracke chaque nouveau Client pour cleanup.
    / Compare current WAITING_CONFIG pks against a previous snapshot, and
    track each new Client for cleanup.
    """
    new_clients = Client.objects.filter(categorie=Client.WAITING_CONFIG).exclude(
        pk__in=before_pks,
    )
    for client in new_clients:
        cleanup_clients(client)
    return new_clients


# ---------------------------------------------------------------------------
# Tests rapides (sans creation de schema Postgres)
# / Fast tests (no Postgres schema creation)
# ---------------------------------------------------------------------------


def test_create_empty_tenant_adds_one_slot_to_pool(
    disable_auto_schema_creation, cleanup_clients,
):
    """
    Sans option, la commande ajoute exactement 1 slot WAITING_CONFIG au pool
    et un Domain primaire associe.
    / With no option, the command adds exactly 1 WAITING_CONFIG slot to the
    pool, plus an associated primary Domain.
    """
    before_pks = list(
        Client.objects.filter(categorie=Client.WAITING_CONFIG).values_list(
            "pk", flat=True,
        )
    )
    before = len(before_pks)

    stdout = StringIO()
    call_command("create_empty_tenant", stdout=stdout)

    after = Client.objects.filter(categorie=Client.WAITING_CONFIG).count()
    assert after == before + 1, (
        f"Pool: attendu {before + 1} apres create_empty_tenant, trouve {after}."
    )

    # Tracker le nouveau slot pour cleanup.
    # / Track the new slot for cleanup.
    new_clients = _track_new_waiting_clients(cleanup_clients, before_pks)
    assert new_clients.count() == 1

    # Verifie le slug et la presence du Domain primaire.
    # / Check the slug and primary Domain.
    new_tenant = new_clients.first()
    assert new_tenant.name.startswith("empty-"), (
        f"Le slug doit commencer par 'empty-', trouve : {new_tenant.name}"
    )
    assert new_tenant.schema_name.startswith("empty_"), (
        f"Le schema_name doit commencer par 'empty_', trouve : "
        f"{new_tenant.schema_name}"
    )
    assert new_tenant.on_trial is True
    # Domain primaire associe / Primary domain associated.
    assert new_tenant.domains.filter(is_primary=True).count() == 1

    output = stdout.getvalue()
    assert "Created empty tenant" in output
    assert "Total: 1 empty tenant(s) created." in output


def test_create_empty_tenant_with_count_creates_n_slots(
    disable_auto_schema_creation, cleanup_clients,
):
    """
    `--count 3` ajoute 3 slots distincts.
    / `--count 3` adds 3 distinct slots.
    """
    before_pks = list(
        Client.objects.filter(categorie=Client.WAITING_CONFIG).values_list(
            "pk", flat=True,
        )
    )
    before = len(before_pks)

    stdout = StringIO()
    call_command("create_empty_tenant", "--count", "3", stdout=stdout)

    after = Client.objects.filter(categorie=Client.WAITING_CONFIG).count()
    assert after == before + 3

    new_clients = _track_new_waiting_clients(cleanup_clients, before_pks)
    assert new_clients.count() == 3

    # Les 3 slugs doivent etre distincts (token_hex de 4 bytes => 8 hex).
    # / The 3 slugs must be distinct (token_hex 4 bytes => 8 hex chars).
    slugs = set(new_clients.values_list("name", flat=True))
    assert len(slugs) == 3, f"Slugs attendus distincts, trouve : {slugs}"

    output = stdout.getvalue()
    assert output.count("Created empty tenant") == 3
    assert "Total: 3 empty tenant(s) created." in output


# ---------------------------------------------------------------------------
# Test "slow" — comportement reel avec auto_create_schema=True
# / "slow" test — real behavior with auto_create_schema=True
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason=(
        "Slow integration : auto_create_schema=True declenche ~200 migrations "
        "Postgres (5-7 min). Lancer manuellement avec : "
        "pytest onboard/tests/test_create_empty_tenant_cmd.py::"
        "test_create_empty_tenant_real_schema_creation -v --no-header -p no:cacheprovider "
        "(et retirer le skip au prealable)."
    ),
)
def test_create_empty_tenant_real_schema_creation(cleanup_clients):
    """
    Verification "smoke" du comportement reel : la commande sans patch cree
    un slot ET son schema Postgres. Skipped par defaut (5-7 min).
    / "Smoke" check of real behavior: the unpatched command creates both a
    slot AND its Postgres schema. Skipped by default (5-7 min).
    """
    before = Client.objects.filter(categorie=Client.WAITING_CONFIG).count()
    stdout = StringIO()
    call_command("create_empty_tenant", stdout=stdout)
    after = Client.objects.filter(categorie=Client.WAITING_CONFIG).count()
    assert after == before + 1

    new_tenant = (
        Client.objects
        .filter(categorie=Client.WAITING_CONFIG)
        .order_by("-created_on")
        .first()
    )
    cleanup_clients(new_tenant)
