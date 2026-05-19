"""
Tests du wizard public anonyme de proposition d'evenement (S4).
/ Tests for the public anonymous event proposal wizard.

LOCALISATION : tests/pytest/test_event_wizard_public.py

On reutilise la base de dev (cf. test_event_wizard_admin.py).
/ Reuse the existing dev DB.
"""

from unittest.mock import patch

import pytest
from django.test.client import Client as DjangoClient
from django.urls import reverse
from django_tenants.utils import tenant_context

from Customers.models import Client


# ----------------------------------------------------------------------------
# Fixtures globales : DB de dev + acces multi-tenant
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
    # On cherche en priorite "lespass" (tenant dev de reference).
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


# ----------------------------------------------------------------------------
# Step 0 — Email
# ----------------------------------------------------------------------------

@pytest.mark.django_db
class TestStep0Email:
    def test_get_accessible_anonyme(self, http_client, tenant):
        with tenant_context(tenant):
            resp = http_client.get(reverse("event-propose-email"))
            assert resp.status_code == 200
            assert b"propose-email-form" in resp.content

    def test_post_emails_non_concordants_422(self, http_client, tenant):
        with tenant_context(tenant):
            resp = http_client.post(reverse("event-propose-email"), {
                "email": "a@x.fr", "email_confirm": "b@x.fr",
            })
            assert resp.status_code == 422

    def test_post_honeypot_rempli_422(self, http_client, tenant):
        with tenant_context(tenant):
            resp = http_client.post(reverse("event-propose-email"), {
                "email": "a@x.fr", "email_confirm": "a@x.fr",
                "website": "https://spam.example",
            })
            assert resp.status_code == 422

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_post_succes_envoie_mail_et_redirige(self, mock_mail, http_client, tenant):
        with tenant_context(tenant):
            resp = http_client.post(reverse("event-propose-email"), {
                "email": "a@x.fr", "email_confirm": "a@x.fr",
            })
            assert resp.status_code == 302
            assert resp.url == reverse("event-propose-verify")
            assert mock_mail.called


# ----------------------------------------------------------------------------
# Step 0 — Verify
# ----------------------------------------------------------------------------

@pytest.mark.django_db
class TestStep0Verify:
    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_get_sans_email_redirige_email(self, _mock_mail, http_client, tenant):
        with tenant_context(tenant):
            resp = http_client.get(reverse("event-propose-verify"))
            assert resp.status_code == 302
            assert resp.url == reverse("event-propose-email")

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_code_correct_redirige_place(self, _mock_mail, http_client, tenant):
        from AuthBillet.otp_service import hash_code_otp
        with tenant_context(tenant):
            http_client.post(reverse("event-propose-email"), {
                "email": "a@x.fr", "email_confirm": "a@x.fr",
            })
            session = http_client.session
            session["event_proposal_otp_hash"] = hash_code_otp("000111")
            session.save()
            resp = http_client.post(reverse("event-propose-verify"), {"otp": "000111"})
            assert resp.status_code == 302
            assert resp.url == reverse("event-propose-place")

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_code_incorrect_422(self, _mock_mail, http_client, tenant):
        from AuthBillet.otp_service import hash_code_otp
        with tenant_context(tenant):
            http_client.post(reverse("event-propose-email"), {
                "email": "a@x.fr", "email_confirm": "a@x.fr",
            })
            session = http_client.session
            session["event_proposal_otp_hash"] = hash_code_otp("000111")
            session.save()
            resp = http_client.post(reverse("event-propose-verify"), {"otp": "999999"})
            assert resp.status_code == 422


# ----------------------------------------------------------------------------
# Bypass impossible : OTP non confirme -> redirect email
# ----------------------------------------------------------------------------

@pytest.mark.django_db
class TestBypassImpossible:
    def test_step1_place_sans_otp_redirige_email(self, http_client, tenant):
        with tenant_context(tenant):
            resp = http_client.get(reverse("event-propose-place"))
            assert resp.status_code == 302
            assert resp.url == reverse("event-propose-email")

    def test_step2_event_sans_otp_redirige_email(self, http_client, tenant):
        with tenant_context(tenant):
            resp = http_client.get(reverse("event-propose-event"))
            assert resp.status_code == 302
            assert resp.url == reverse("event-propose-email")


# ----------------------------------------------------------------------------
# Submission finale : creation event proposal
# ----------------------------------------------------------------------------

@pytest.mark.django_db
class TestSubmissionFinale:
    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_step2_cree_event_proposal(self, _mock_mail, http_client, tenant):
        from BaseBillet.models import Event, PostalAddress
        with tenant_context(tenant):
            addr = PostalAddress.objects.first()
            assert addr is not None, "Pre-requis : au moins une PostalAddress existe."
            session = http_client.session
            session["event_proposal_otp_confirmed"] = True
            session["event_proposal_otp_email"] = "a@x.fr"
            session["event_proposal_postal_address_pk"] = str(addr.pk)
            session.save()

            resp = http_client.post(reverse("event-propose-event"), {
                "name": "Proposition publique test",
                "datetime": "2026-12-31T20:00",
            })
            assert resp.status_code == 302
            assert resp.url == reverse("event-propose-done")
            event = Event.objects.filter(name="Proposition publique test").first()
            assert event is not None
            assert event.published is False
            assert event.is_proposal is True
            assert event.created_by is None

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_step2_succes_reset_session(self, _mock_mail, http_client, tenant):
        from BaseBillet.models import PostalAddress
        with tenant_context(tenant):
            addr = PostalAddress.objects.first()
            assert addr is not None
            session = http_client.session
            session["event_proposal_otp_confirmed"] = True
            session["event_proposal_otp_email"] = "a@x.fr"
            session["event_proposal_postal_address_pk"] = str(addr.pk)
            session.save()

            http_client.post(reverse("event-propose-event"), {
                "name": "Test reset",
                "datetime": "2026-12-31T20:00",
            })
            assert "event_proposal_postal_address_pk" not in http_client.session
            assert "event_proposal_otp_confirmed" not in http_client.session


# ----------------------------------------------------------------------------
# Page done : accessible sans garde (one-shot success)
# ----------------------------------------------------------------------------

@pytest.mark.django_db
class TestDone:
    def test_done_accessible_sans_garde(self, http_client, tenant):
        with tenant_context(tenant):
            resp = http_client.get(reverse("event-propose-done"))
            assert resp.status_code == 200
            assert b"propose-done" in resp.content
