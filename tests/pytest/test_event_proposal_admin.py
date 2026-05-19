"""
Tests de la moderation admin pour les propositions publiques (S5).
/ Tests for admin moderation of public proposals (S5).

LOCALISATION : tests/pytest/test_event_proposal_admin.py

On reutilise la base de dev existante (cf. test_event_is_proposal_field.py)
et le tenant "lespass".
/ Reuse the existing dev DB and the "lespass" tenant.

Couvre :
- TestEventProposalsBadge : 3 tests du callback sidebar Unfold.
- TestActionBulkApprouver : 2 tests de l'action bulk approuver_propositions
  sur EventAdmin (changelist staff_admin).
/ Covers:
- TestEventProposalsBadge: 3 tests of the Unfold sidebar callback.
- TestActionBulkApprouver: 2 tests of the bulk action approuver_propositions
  on EventAdmin (staff_admin changelist).
"""

import uuid

import pytest
from django.test.client import Client as DjangoClient
from django.urls import reverse
from django.utils import timezone
from django_tenants.utils import tenant_context

from Customers.models import Client


# ----------------------------------------------------------------------------
# Fixtures globales : base de dev + acces multi-tenant
# / Global fixtures: dev DB + multi-tenant access
# ----------------------------------------------------------------------------

@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse dev DB (no test DB creation).
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()


@pytest.fixture
def tenant():
    # On cible "lespass" en priorite (tenant dev de reference).
    # / Prefer "lespass" tenant (dev reference).
    t = Client.objects.filter(schema_name="lespass").first()
    if not t:
        t = Client.objects.exclude(schema_name="public").first()
    return t


@pytest.fixture
def domain(tenant):
    return tenant.domains.first()


@pytest.fixture
def http_client(domain):
    # Le test client doit "viser" le domaine du tenant pour que
    # django-tenants resolve le bon schema.
    # / Test client must target the tenant domain so django-tenants resolves schema.
    return DjangoClient(HTTP_HOST=domain.domain)


@pytest.fixture
def admin_user(tenant):
    """Retourne un user pouvant administrer le tenant (superuser HUM).
    / Returns a tenant-admin user (HUM superuser)."""
    from AuthBillet.models import TibilletUser
    with tenant_context(tenant):
        user = TibilletUser.objects.filter(
            is_superuser=True, is_active=True,
            espece=TibilletUser.TYPE_HUM,
        ).first()
        if not user:
            user = TibilletUser.objects.filter(
                is_staff=True, is_active=True,
                espece=TibilletUser.TYPE_HUM,
            ).first()
        assert user, "Pre-requis : au moins un superuser ou staff HUM existe."
        return user


@pytest.fixture
def cleanup_proposals(tenant):
    """Cleanup des events crees pendant le test (par prefixe de nom).
    / Cleanup of events created during the test (by name prefix)."""
    yield
    from BaseBillet.models import Event
    with tenant_context(tenant):
        Event.objects.filter(name__startswith="ProposalTest ").delete()


# ----------------------------------------------------------------------------
# Tests : badge sidebar Unfold (event_proposals_badge_callback)
# / Tests: Unfold sidebar badge (event_proposals_badge_callback)
# ----------------------------------------------------------------------------

@pytest.mark.django_db
class TestEventProposalsBadge:
    def test_callback_compte_propositions_pending(self, tenant, cleanup_proposals):
        from BaseBillet.models import Event
        from Administration.admin.dashboard import event_proposals_badge_callback
        with tenant_context(tenant):
            # On purge les anciennes propositions pending pour fiabiliser le compte.
            # / Purge previous pending proposals to make the count reliable.
            Event.objects.filter(is_proposal=True, published=False).delete()
            for i in range(3):
                Event.objects.create(
                    name=f"ProposalTest pending {i} {uuid.uuid4().hex[:6]}",
                    datetime=timezone.now() + timezone.timedelta(days=1),
                    is_proposal=True,
                    published=False,
                )
            assert event_proposals_badge_callback(None) == "+ 3"

    def test_callback_retourne_none_si_zero(self, tenant, cleanup_proposals):
        from BaseBillet.models import Event
        from Administration.admin.dashboard import event_proposals_badge_callback
        with tenant_context(tenant):
            # Aucune proposition pending => callback retourne None.
            # / No pending proposal => callback returns None.
            Event.objects.filter(is_proposal=True, published=False).delete()
            assert event_proposals_badge_callback(None) is None

    def test_callback_ignore_events_publies(self, tenant, cleanup_proposals):
        from BaseBillet.models import Event
        from Administration.admin.dashboard import event_proposals_badge_callback
        with tenant_context(tenant):
            # On supprime tout proposition pending residuelle.
            # / Remove any residual pending proposal.
            Event.objects.filter(is_proposal=True, published=False).delete()
            # Une proposition deja approuvee (published=True) ne doit pas etre comptee.
            # / An already approved proposal (published=True) must NOT be counted.
            Event.objects.create(
                name=f"ProposalTest approuvee {uuid.uuid4().hex[:6]}",
                datetime=timezone.now() + timezone.timedelta(days=1),
                is_proposal=True,
                published=True,
            )
            assert event_proposals_badge_callback(None) is None


# ----------------------------------------------------------------------------
# Tests : action bulk "approuver_propositions" via le changelist staff_admin
# / Tests: bulk action "approuver_propositions" via the staff_admin changelist
# ----------------------------------------------------------------------------

@pytest.mark.django_db
class TestActionBulkApprouver:
    def test_action_approuver_set_published_true_et_is_proposal_false(
        self, http_client, admin_user, tenant, cleanup_proposals,
    ):
        from BaseBillet.models import Event
        with tenant_context(tenant):
            ev = Event.objects.create(
                name=f"ProposalTest a approuver {uuid.uuid4().hex[:6]}",
                datetime=timezone.now() + timezone.timedelta(days=1),
                is_proposal=True,
                published=False,
            )
        http_client.force_login(admin_user)
        url = reverse("staff_admin:BaseBillet_event_changelist")
        with tenant_context(tenant):
            resp = http_client.post(url, {
                "action": "approuver_propositions",
                "_selected_action": [str(ev.pk)],
            })
            # Django admin redirige (302) ou ressert la liste (200) selon le contexte.
            # / Django admin either redirects (302) or re-renders the list (200).
            assert resp.status_code in (200, 302), resp.content[:500]
            ev.refresh_from_db()
            assert ev.is_proposal is False
            assert ev.published is True

    def test_action_approuver_ignore_events_deja_publies(
        self, http_client, admin_user, tenant, cleanup_proposals,
    ):
        """Un event regulier (is_proposal=False) selectionne ne doit PAS etre touche.
        / A regular event (is_proposal=False) in the selection must NOT be flipped."""
        from BaseBillet.models import Event
        with tenant_context(tenant):
            ev_regulier = Event.objects.create(
                name=f"ProposalTest regulier {uuid.uuid4().hex[:6]}",
                datetime=timezone.now() + timezone.timedelta(days=1),
                is_proposal=False,
                published=False,
            )
        http_client.force_login(admin_user)
        url = reverse("staff_admin:BaseBillet_event_changelist")
        with tenant_context(tenant):
            resp = http_client.post(url, {
                "action": "approuver_propositions",
                "_selected_action": [str(ev_regulier.pk)],
            })
            assert resp.status_code in (200, 302), resp.content[:500]
            ev_regulier.refresh_from_db()
            # L'action filtre is_proposal=True : un event regulier reste intact.
            # / Action filters is_proposal=True: a regular event stays untouched.
            assert ev_regulier.is_proposal is False
            assert ev_regulier.published is False
