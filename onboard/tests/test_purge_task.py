"""
Tests de la task `purge_stale_onboard_drafts`.
/ Tests for the `purge_stale_onboard_drafts` Celery task.

LOCALISATION: onboard/tests/test_purge_task.py

Style : pytest pur (fonctions + fixtures), pattern V2 du conftest local
(reutilisation de la base dev, nettoyage explicite via `cleanup_waiting_configs`).
/ Style: pure pytest (functions + fixtures), V2 pattern from local conftest
(dev DB reuse, explicit cleanup via `cleanup_waiting_configs`).
"""

from datetime import timedelta

from django.utils import timezone
from django_tenants.utils import schema_context

from MetaBillet.models import WaitingConfiguration


def test_purge_removes_old_unfinalized_drafts(cleanup_waiting_configs):
    """
    Un WC non finalise (tenant=None) cree il y a plus de `ttl_days` jours
    doit etre supprime. Un WC recent doit etre conserve.
    / An unfinalized WC (tenant=None) older than `ttl_days` must be deleted.
    A recent WC must be kept.
    """
    from onboard.tasks import purge_stale_onboard_drafts

    # On cree deux brouillons dans le schema "meta".
    # / Create two drafts in the "meta" schema.
    with schema_context("meta"):
        old = WaitingConfiguration.objects.create(
            organisation="PurgeOldOrg",
            email="purge-old@example.com",
            dns_choice="tibillet.localhost",
            phone="0102030405",  # champ obligatoire / required field
        )
        cleanup_waiting_configs(old)  # garde-fou si la purge echoue

        # Le champ "date de creation" s'appelle `datetime` (auto_now_add=True)
        # dans WaitingConfiguration : on ne peut pas le passer en kwarg de
        # create(). On le force a 31 jours dans le passe via update().
        # / The "creation date" field is named `datetime` (auto_now_add=True)
        # on WaitingConfiguration: cannot pass in create(). Force it to 31
        # days in the past via update().
        WaitingConfiguration.objects.filter(uuid=old.uuid).update(
            datetime=timezone.now() - timedelta(days=31),
        )

        recent = WaitingConfiguration.objects.create(
            organisation="PurgeRecentOrg",
            email="purge-recent@example.com",
            dns_choice="tibillet.localhost",
            phone="0102030405",
        )
        cleanup_waiting_configs(recent)

        old_uuid = old.uuid
        recent_uuid = recent.uuid

    # Appel synchrone (pas .delay()) pour test deterministe.
    # / Synchronous call (no .delay()) for deterministic test.
    deleted = purge_stale_onboard_drafts()

    with schema_context("meta"):
        # Le vieux a ete supprime. / The old one was deleted.
        assert not WaitingConfiguration.objects.filter(uuid=old_uuid).exists(), (
            "Old draft should have been purged."
        )
        # Le recent reste. / The recent one stays.
        assert WaitingConfiguration.objects.filter(uuid=recent_uuid).exists(), (
            "Recent draft must NOT be purged."
        )

    # Le compteur retourne au moins le vieux qu'on a force a 31 jours.
    # Peut etre superieur si la DB dev contient d'autres vieux drafts.
    # / Counter returns at least the one we forced to 31 days old. May be
    # higher if dev DB contains other old drafts.
    assert deleted >= 1, f"Expected at least 1 deletion, got {deleted}."


def test_purge_keeps_finalized_drafts(cleanup_waiting_configs, lespass_tenant):
    """
    Un WC vieux MAIS finalise (tenant attache) ne doit PAS etre purge :
    on conserve la trace historique de l'onboarding.
    / An old BUT finalized WC (tenant attached) must NOT be purged: keep
    historical onboarding trace.
    """
    from onboard.tasks import purge_stale_onboard_drafts

    with schema_context("meta"):
        finalized = WaitingConfiguration.objects.create(
            organisation="PurgeFinalizedOrg",
            email="purge-finalized@example.com",
            dns_choice="tibillet.localhost",
            phone="0102030405",
            tenant=lespass_tenant,  # WC deja finalise / WC already finalized
        )
        cleanup_waiting_configs(finalized)

        # Force a 31 jours dans le passe pour qu'il MATCHE le filtre d'age
        # mais SOIT exclu par le filtre `tenant__isnull=True`.
        # / Force to 31 days old so it MATCHES the age filter but is excluded
        # by the `tenant__isnull=True` filter.
        WaitingConfiguration.objects.filter(uuid=finalized.uuid).update(
            datetime=timezone.now() - timedelta(days=31),
        )
        finalized_uuid = finalized.uuid

    # Purge avec ttl=30 jours. / Purge with ttl=30 days.
    purge_stale_onboard_drafts()

    with schema_context("meta"):
        assert WaitingConfiguration.objects.filter(uuid=finalized_uuid).exists(), (
            "Finalized draft (tenant set) must NEVER be purged."
        )
