"""
Tests de la task Celery `create_tenant_from_draft`.
/ Tests for the `create_tenant_from_draft` Celery task.

LOCALISATION: onboard/tests/test_create_tenant_task.py

NOTES (FR) :
  - Style **pytest pur** (pas de TestCase) — fixtures dans conftest.py.
  - On REUTILISE la base dev existante (cf. conftest.py local) au lieu de
    creer une test DB lourde. Pas de migrations rejouees a chaque run.
  - La vraie methode `WaitingConfiguration.create_tenant()` recategorise un
    Client du pool (WAITING_CONFIG -> SALLE_SPECTACLE) et applique TOUTES les
    migrations sur les TENANT_APPS du nouveau schema. C'est extremement lent
    (plusieurs minutes). On la **mocke** dans tous les tests qui devraient
    aboutir : le mock renvoie le tenant `lespass` deja en place et simule
    l'ecriture de `wc.tenant` + `wc.created`.
  - Pour le pool slot, on cree un Client temporaire avec
    `auto_create_schema=False` (sinon Postgres cree vraiment un schema, ce
    qui est lent et casse souvent la transaction courante).
  - Le test "federation" reste skippe : `fedow_core` n'est pas sur la
    branche `main-wizard` et la FK `OnboardInvitation.federation` est
    commentee (cf. onboard/models.py TODO).

/ NOTES (EN):
  - **Pure pytest** style (no TestCase). Fixtures live in conftest.py.
  - REUSE the existing dev DB (cf. local conftest.py) instead of building a
    test DB. No migrations replayed per run.
  - Real `WaitingConfiguration.create_tenant()` re-categorises a pool Client
    and runs migrations on the new schema. Very slow. We MOCK it in every
    test that should succeed; the mock returns the existing `lespass`
    tenant and simulates `wc.tenant` + `wc.created` persistence.
  - For the pool slot, we create a temporary Client with
    `auto_create_schema=False` (otherwise Postgres really creates a schema,
    which is slow and breaks the current transaction).
  - The "federation" test stays skipped: `fedow_core` is not on the
    `main-wizard` branch and the `OnboardInvitation.federation` FK is
    commented (cf. onboard/models.py TODO).
"""

import uuid
from unittest.mock import patch

import pytest
from django_tenants.utils import schema_context

from Customers.models import Client
from MetaBillet.models import WaitingConfiguration


# ---------------------------------------------------------------------------
# Helpers locaux : WC et pool slot temporaires.
# / Local helpers: temporary WC and pool slot.
# ---------------------------------------------------------------------------


def _make_wc(cleanup_waiting_configs):
    """
    Cree un WaitingConfiguration minimal dans le schema meta et le marque
    pour suppression en teardown.
    / Build a minimal WaitingConfiguration in the meta schema and tag it
    for teardown cleanup.
    """
    # Email unique par run pour eviter les collisions avec les vrais drafts.
    # / Unique email per run to avoid collisions with real drafts.
    suffix = uuid.uuid4().hex[:8]
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation=f"CreateTaskOrg-{suffix}",
            email=f"create-task-user-{suffix}@example.com",
            dns_choice="tibillet.localhost",
            phone="0102030405",  # champ obligatoire / required
            email_confirmed=True,
        )
    cleanup_waiting_configs(wc)
    return wc


def _make_pool_slot(cleanup_clients):
    """
    Cree un Client WAITING_CONFIG sans materialiser de schema Postgres
    (auto_create_schema=False) : juste une ligne en DB pour satisfaire le
    pool check de la task. Le client est supprime au teardown.

    / Create a Client WAITING_CONFIG without materialising a Postgres schema
    (auto_create_schema=False): just a DB row to satisfy the task's pool
    check. The client is removed at teardown.

    PIEGE : sans `auto_create_schema=False`, le save() declenche `CREATE
    SCHEMA <name>` qui peut etre lent (plusieurs secondes) et qui se met
    dans la transaction courante — toute erreur ulterieure abortera tout.
    / PITFALL: without `auto_create_schema=False`, save() triggers `CREATE
    SCHEMA <name>`, which is slow and runs inside the current transaction
    so any later error aborts everything.
    """
    suffix = uuid.uuid4().hex[:8]
    slot = Client(
        schema_name=f"onboard-test-pool-slot-{suffix}",
        name=f"Onboard Test Pool Slot {suffix}",
        categorie=Client.WAITING_CONFIG,
    )
    slot.auto_create_schema = False  # IMPORTANT: skip schema creation
    # django-tenants exige que Client.save() s'execute dans le schema
    # public. Si un test precedent a laisse le schema courant sur un
    # tenant (via le middleware HTTP_HOST=lespass.tibillet.localhost
    # par exemple), on force explicitement le retour pour eviter un
    # `Can't create tenant outside the public schema` au save().
    # / django-tenants requires Client.save() to run in the public
    # schema. Force return if a previous test (e.g. an HTTP-based one
    # using HTTP_HOST=<tenant>) left us on a tenant schema.
    with schema_context("public"):
        slot.save()
    cleanup_clients(slot)
    return slot


def _fake_create_tenant_factory(target_tenant):
    """
    Construit une fonction qui imite `WaitingConfiguration.create_tenant()` :
    elle ecrit `wc.tenant` + `wc.created` en base et retourne `target_tenant`.
    / Build a function that mimics `WaitingConfiguration.create_tenant()`:
    it writes `wc.tenant` + `wc.created` and returns `target_tenant`.
    """
    def _fake(self_wc):
        with schema_context("meta"):
            self_wc.tenant = target_tenant
            self_wc.created = True
            self_wc.save()
        return target_tenant

    return _fake


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.onboard
def test_create_tenant_from_draft_consumes_pool_slot(
    lespass_tenant, cleanup_waiting_configs, cleanup_clients,
):
    """
    Apres la task, `wc.tenant` est rempli (le mock simule la chaine reelle
    de `create_tenant()` qui ecrit wc.tenant en base).
    / After the task, `wc.tenant` is set (the mock simulates the real
    chain of `create_tenant()` which persists wc.tenant in DB).
    """
    from onboard.tasks import create_tenant_from_draft

    wc = _make_wc(cleanup_waiting_configs)
    _make_pool_slot(cleanup_clients)  # satisfait le pool check / pool check

    with patch.object(
        WaitingConfiguration, "create_tenant",
        autospec=True,
        side_effect=_fake_create_tenant_factory(lespass_tenant),
    ):
        create_tenant_from_draft(wc_uuid=str(wc.uuid))

    with schema_context("meta"):
        wc.refresh_from_db()
        assert wc.tenant is not None, "wc.tenant doit etre rempli apres la task."
        assert wc.tenant_id == lespass_tenant.pk
        assert wc.tenant.categorie != Client.WAITING_CONFIG, (
            "Le tenant final ne doit plus etre dans la categorie WAITING_CONFIG."
        )


@pytest.mark.onboard
def test_create_tenant_from_draft_is_idempotent(
    lespass_tenant, cleanup_waiting_configs, cleanup_clients,
):
    """
    Deux appels successifs n'invoquent qu'une seule fois `create_tenant()`.
    / Two successive calls invoke `create_tenant()` only once.
    """
    from onboard.tasks import create_tenant_from_draft

    wc = _make_wc(cleanup_waiting_configs)
    _make_pool_slot(cleanup_clients)

    with patch.object(
        WaitingConfiguration, "create_tenant",
        autospec=True,
        side_effect=_fake_create_tenant_factory(lespass_tenant),
    ) as mock_create:
        create_tenant_from_draft(wc_uuid=str(wc.uuid))
        # Deuxieme appel : doit retourner tot grace au check tenant_id.
        # / Second call: must early-return thanks to the tenant_id check.
        create_tenant_from_draft(wc_uuid=str(wc.uuid))

        assert mock_create.call_count == 1, (
            "create_tenant() ne doit etre appele qu'une seule fois (idempotence)."
        )

    with schema_context("meta"):
        wc.refresh_from_db()
        assert wc.tenant_id == lespass_tenant.pk


@pytest.mark.onboard
def test_create_tenant_from_draft_writes_error_when_no_pool(
    cleanup_waiting_configs,
):
    """
    Si le pool WAITING_CONFIG est vide, la task ecrit `wc.error_message`
    et retourne proprement (pas de raise).
    / If WAITING_CONFIG pool is empty, the task writes `wc.error_message`
    and returns cleanly (no raise).

    PIEGE : NE PAS faire `Client.objects.filter(categorie=WAITING_CONFIG).delete()`
    ici — cela viderait le vrai pool de la DB dev partagee. A la place, on
    patche le manager Client.objects pour que la query count() renvoie 0.
    / PITFALL: do NOT delete WAITING_CONFIG clients here — that would purge
    the real pool from the shared dev DB. Instead, we patch Client.objects
    so the count() query returns 0.
    """
    from onboard.tasks import create_tenant_from_draft

    wc = _make_wc(cleanup_waiting_configs)

    # On patche `Client.objects` dans le module `onboard.tasks` pour que la
    # query `.filter(...).count()` renvoie 0, sans toucher la vraie DB.
    # / Patch `Client.objects` inside `onboard.tasks` so `.filter(...).count()`
    # returns 0, without touching the real DB.
    with patch("onboard.tasks.Client.objects") as mock_qs, \
         patch.object(WaitingConfiguration, "create_tenant", autospec=True) as mock_create:
        mock_qs.filter.return_value.count.return_value = 0

        # Aucune exception ne doit remonter. / no exception bubbles up.
        create_tenant_from_draft(wc_uuid=str(wc.uuid))

        # create_tenant ne doit jamais etre appele si le pool est vide.
        # / create_tenant must never be called when pool is empty.
        assert mock_create.call_count == 0, (
            "create_tenant() ne doit pas etre appele si le pool est vide."
        )

    with schema_context("meta"):
        wc.refresh_from_db()
        assert wc.tenant is None, (
            "wc.tenant doit rester vide si la task a abandonne."
        )
        error = (wc.error_message or "").lower()
        assert "pool" in error or "slot" in error, (
            f"error_message doit mentionner 'pool' ou 'slot', "
            f"recu : {wc.error_message!r}"
        )


@pytest.mark.onboard
def test_create_tenant_from_draft_calls_ready_mailer_on_success(
    lespass_tenant, cleanup_waiting_configs, cleanup_clients,
):
    """
    En cas de succes, la task enqueue `onboard_ready_mailer` avec wc_uuid.
    / On success, the task enqueues `onboard_ready_mailer` with wc_uuid.
    """
    from onboard.tasks import create_tenant_from_draft

    wc = _make_wc(cleanup_waiting_configs)
    _make_pool_slot(cleanup_clients)
    wc_uuid = str(wc.uuid)

    with patch.object(
        WaitingConfiguration, "create_tenant",
        autospec=True,
        side_effect=_fake_create_tenant_factory(lespass_tenant),
    ), patch("onboard.tasks.onboard_ready_mailer.delay") as mock_mailer:
        create_tenant_from_draft(wc_uuid=wc_uuid)

        mock_mailer.assert_called_once_with(wc_uuid=wc_uuid)


@pytest.mark.onboard
def test_create_tenant_from_draft_creates_events_from_drafts_with_iso_datetime(
    lespass_tenant, cleanup_waiting_configs, cleanup_clients,
):
    """
    Regression : `events_draft` est un JSONField -> les datetimes sont
    stockes en string ISO 8601 ("2026-06-15T19:00:00+02:00"). Avant fix,
    `Event.objects.create(datetime="...")` ne convertissait PAS la string,
    et `Event.save()` plantait silencieusement avec
    `'str' object has no attribute 'astimezone'` quand le post_save signal
    tentait de generer le slug. Le `try/except Exception` swallow l'erreur
    -> 0 events crees, sans trace evidente pour l'utilisateur.

    Le fix parse `datetime.fromisoformat()` avant create. Ce test verifie
    qu'un draft avec datetime ISO string aboutit bien a un Event en DB
    dans le schema du nouveau tenant.

    / Regression: `events_draft` JSONField stores datetimes as ISO 8601
    strings. Before the fix, `Event.objects.create(datetime="...")` did
    NOT convert, and the post_save signal crashed silently. The except
    swallowed the error -> 0 events created. Fix parses fromisoformat()
    before create.
    """
    from BaseBillet.models import Event
    from onboard.tasks import create_tenant_from_draft

    wc = _make_wc(cleanup_waiting_configs)
    _make_pool_slot(cleanup_clients)

    # Suffix unique pour ne pas hitter le `unique_together = ('name', 'datetime')`
    # de Event si plusieurs runs du test laissent des Events orphelins dans
    # le tenant `lespass` partage. / Unique suffix to avoid hitting the
    # `unique_together = ('name', 'datetime')` constraint on shared tenant.
    nom_event_unique = f"EventTest-{uuid.uuid4().hex[:8]}"

    # Un draft d'event avec datetime SOUS FORME DE STRING ISO (ce que
    # produit DRF/Django quand il serialise une DateTime -> JSON pour le
    # JSONField events_draft). / Draft with ISO string datetime (DRF/Django
    # output when serializing DateTime -> JSON for the events_draft field).
    iso_datetime_str = "2099-06-15T19:00:00+02:00"
    with schema_context("meta"):
        wc.events_draft = [{
            "name": nom_event_unique,
            "datetime": iso_datetime_str,
            "description": "Test regression datetime string",
        }]
        wc.save(update_fields=["events_draft"])

    with patch.object(
        WaitingConfiguration, "create_tenant",
        autospec=True,
        side_effect=_fake_create_tenant_factory(lespass_tenant),
    ):
        create_tenant_from_draft(wc_uuid=str(wc.uuid))

    # On verifie que l'event a bien ete cree dans le schema du tenant
    # (lespass_tenant ici, qui sert de tenant cible mock).
    # / Verify the event exists in the tenant schema (lespass_tenant
    # serves as the mock target tenant here).
    from django_tenants.utils import tenant_context
    with tenant_context(lespass_tenant):
        evt = Event.objects.filter(name=nom_event_unique).first()
        assert evt is not None, (
            "Event devrait avoir ete cree dans le tenant. "
            "Si None: bug datetime str / parse fromisoformat regressif."
        )
        # Cleanup explicit pour ne pas polluer le tenant lespass partage.
        # / Explicit cleanup to keep shared lespass tenant clean.
        evt_name = evt.name
        evt_dt = evt.datetime
        evt.delete()
        assert evt_dt.year == 2099, f"Annee attendue 2099, recu {evt_dt.year}"
        assert evt_name == nom_event_unique


@pytest.mark.onboard
def test_create_tenant_from_draft_accumulates_warnings_for_broken_drafts(
    lespass_tenant, cleanup_waiting_configs, cleanup_clients,
):
    """
    Quand un draft d'event est mal forme (datetime non parsable, image
    invalide, etc.), la task le skip ET accumule un warning lisible dans
    `wc.events_creation_warnings`. Le tenant est cree normalement, le
    drafts valides sont ajoutes — seul le draft cassé est ignore.

    L'utilisateur voit ces warnings sur `/onboard/launch/` (rendu par
    `status_done.html`) et peut recreer les events manuellement dans
    son admin.

    / When an event draft is malformed (unparseable datetime, broken
    image), the task skips it AND accumulates a readable warning in
    `wc.events_creation_warnings`. Tenant is created normally, valid
    drafts processed — only the broken one is ignored. The user sees
    the warnings on `/onboard/launch/` (status_done.html).
    """
    from BaseBillet.models import Event
    from onboard.tasks import create_tenant_from_draft

    wc = _make_wc(cleanup_waiting_configs)
    _make_pool_slot(cleanup_clients)

    # 2 drafts : 1 valide + 1 mal forme (datetime "not-a-date" -> raise
    # ValueError dans fromisoformat). Suffix unique pour eviter les
    # collisions sur unique_together (name, datetime) du tenant lespass
    # partage. / 2 drafts: 1 valid + 1 broken (datetime "not-a-date"
    # raises ValueError in fromisoformat). Unique suffix to avoid
    # collisions in shared lespass tenant.
    suffix = uuid.uuid4().hex[:8]
    nom_valide = f"EventValide-{suffix}"
    nom_casse = f"EventCasse-{suffix}"
    with schema_context("meta"):
        wc.events_draft = [
            {
                "name": nom_valide,
                "datetime": "2099-07-14T20:00:00+02:00",
                "description": "Draft valide, doit etre cree.",
            },
            {
                "name": nom_casse,
                "datetime": "not-a-date",  # invalide -> raise au parse
                "description": "Draft casse, doit etre skip + warning.",
            },
        ]
        wc.save(update_fields=["events_draft"])

    with patch.object(
        WaitingConfiguration, "create_tenant",
        autospec=True,
        side_effect=_fake_create_tenant_factory(lespass_tenant),
    ):
        create_tenant_from_draft(wc_uuid=str(wc.uuid))

    # Verif 1 : le draft valide est cree, le draft casse est skip.
    # / Check 1: valid draft created, broken draft skipped.
    from django_tenants.utils import tenant_context
    with tenant_context(lespass_tenant):
        evt_valide = Event.objects.filter(name=nom_valide).first()
        evt_casse = Event.objects.filter(name=nom_casse).first()
        assert evt_valide is not None, "Le draft valide doit etre cree."
        assert evt_casse is None, "Le draft casse doit etre skip."
        # Cleanup pour ne pas polluer le tenant lespass partage.
        # / Cleanup to keep shared lespass tenant clean.
        evt_valide.delete()

    # Verif 2 : le warning est accumule dans wc.events_creation_warnings,
    # mentionne le nom du draft casse + une trace lisible (classe d'exc).
    # / Check 2: warning is accumulated in wc.events_creation_warnings,
    # mentions the broken draft name + readable trace (exception class).
    with schema_context("meta"):
        wc.refresh_from_db()
        warnings_text = wc.events_creation_warnings
        assert warnings_text, (
            "events_creation_warnings doit etre non-vide quand un draft est skip."
        )
        assert nom_casse in warnings_text, (
            f"Le nom du draft casse '{nom_casse}' doit apparaitre dans les warnings, "
            f"recu: {warnings_text!r}"
        )
        # Le valide ne doit PAS apparaitre (puisqu'il a reussi).
        # / Valid one must NOT appear (it succeeded).
        assert nom_valide not in warnings_text, (
            "Le draft valide ne doit PAS apparaitre dans les warnings."
        )


@pytest.mark.onboard
def test_create_tenant_from_draft_writes_error_when_name_taken_async(
    cleanup_waiting_configs, cleanup_clients,
):
    """
    Race condition : entre la validation step 1 (nom libre) et la creation
    async, un autre user prend le meme nom -> `TenantCreateValidator.
    create_tenant` raise `Exception("The name 'X' is already taken.")`.

    On verifie que la task :
      - capture l'exception et l'inscrit dans `wc.error_message`,
      - laisse `wc.tenant` a None (rien n'a abouti),
      - re-raise pour permettre l'autoretry Celery (catch via pytest.raises).

    L'utilisateur verra alors dans `/onboard/launch/` (rendu par
    `status_error.html`) le message d'erreur, avec le bouton "Reessayer"
    qui appellera retry mais aboutira au meme echec tant que le nom est
    pris -> il devra revenir step 1 changer de nom.

    / Race condition: between step-1 validation (name available) and async
    creation, another user grabs the same name -> create_tenant() raises.
    The task captures it in `wc.error_message`, leaves `wc.tenant=None`,
    and re-raises for Celery autoretry. The user sees the error on
    `/onboard/launch/` and must change the name in step 1.
    """
    from onboard.tasks import create_tenant_from_draft

    wc = _make_wc(cleanup_waiting_configs)
    _make_pool_slot(cleanup_clients)

    def _raise_name_taken(self_wc):
        raise Exception(f"The name '{self_wc.organisation}' is already taken.")

    with patch.object(
        WaitingConfiguration, "create_tenant",
        autospec=True,
        side_effect=_raise_name_taken,
    ):
        with pytest.raises(Exception, match="already taken"):
            create_tenant_from_draft(wc_uuid=str(wc.uuid))

    with schema_context("meta"):
        wc.refresh_from_db()
        assert wc.tenant is None, (
            "wc.tenant doit rester None quand create_tenant raise."
        )
        error = (wc.error_message or "").lower()
        assert "already taken" in error, (
            f"error_message doit mentionner 'already taken', "
            f"recu: {wc.error_message!r}"
        )


@pytest.mark.onboard
@pytest.mark.skip(
    reason="fedow_core not on main-wizard. The FK OnboardInvitation.federation "
           "is commented out (cf. onboard/models.py TODO). Re-enable when V2 "
           "monorepo merges. / fedow_core absent sur main-wizard."
)
def test_create_tenant_from_draft_attaches_to_invitation_federation():
    """
    Si `wc.invitation` est presente, le tenant rejoint directement
    `federation.tenants` (pas via pending_tenants) et `inv.used_at` est
    renseigne.
    / If `wc.invitation` is set, the tenant joins `federation.tenants`
    directly (skipping pending_tenants) and `inv.used_at` is filled.
    """
    # Code pret pour la fusion V2 — pour l'instant, ce test est skippe.
    # / Code ready for the V2 merge — currently skipped.
    raise AssertionError("Should be skipped above.")
