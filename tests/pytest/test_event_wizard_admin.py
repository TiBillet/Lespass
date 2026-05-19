"""
Tests du wizard admin de creation d'evenement (S3).
/ Tests for the admin event creation wizard (S3).

LOCALISATION : tests/pytest/test_event_wizard_admin.py

On utilise la base de dev existante (cf. test_event_is_proposal_field.py).
/ Reuse the existing dev DB (cf. test_event_is_proposal_field.py).
"""

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


@pytest.fixture
def admin_user(tenant):
    """Retourne un user pouvant creer des evenements (superuser de preference).
    / Returns a user allowed to create events (preferring superuser).
    Cf. CanCreateEventPermission : super_user OR tenant_admin OR can_create_event."""
    from AuthBillet.models import TibilletUser
    with tenant_context(tenant):
        # Priorite : superuser HUM actif.
        # / Priority: active HUM superuser.
        user = TibilletUser.objects.filter(
            is_superuser=True, is_active=True,
            espece=TibilletUser.TYPE_HUM,
        ).first()
        if not user:
            # Fallback : un staff utilisateur.
            user = TibilletUser.objects.filter(
                is_staff=True, is_active=True,
                espece=TibilletUser.TYPE_HUM,
            ).first()
        assert user, "Pre-requis : au moins un superuser ou staff HUM existe."
        return user


@pytest.fixture
def cleanup_created_events(tenant):
    """Cleanup events crees pendant un test (par nom prefixe wizard).
    / Cleanup events created during a test (by wizard-prefixed name)."""
    yield
    from BaseBillet.models import Event, PostalAddress
    with tenant_context(tenant):
        Event.objects.filter(name__startswith="Wizard test ").delete()
        PostalAddress.objects.filter(name__startswith="Wizard test ").delete()


# ----------------------------------------------------------------------------
# Tests Step 1 — Access
# ----------------------------------------------------------------------------

@pytest.mark.django_db
class TestStep1PlaceAccess:
    def test_get_step1_redirige_anonyme(self, http_client):
        url = reverse("event-admin-wizard-place")
        resp = http_client.get(url)
        # Anonyme : redirect login OU 401/403.
        # / Anonymous: redirect login or 401/403.
        assert resp.status_code in (302, 401, 403)

    def test_get_step1_ok_pour_admin(self, http_client, admin_user, tenant):
        http_client.force_login(admin_user)
        with tenant_context(tenant):
            resp = http_client.get(reverse("event-admin-wizard-place"))
            assert resp.status_code == 200, resp.content[:500]
            assert b"wizard-place-form" in resp.content


# ----------------------------------------------------------------------------
# Tests Step 1 — Submit
# ----------------------------------------------------------------------------

@pytest.mark.django_db
class TestStep1PlaceSubmit:
    def test_post_avec_adresse_existante_redirige_step2(self, http_client, admin_user, tenant):
        from BaseBillet.models import PostalAddress
        with tenant_context(tenant):
            addr = PostalAddress.objects.first()
            assert addr, "Pre-requis : au moins une PostalAddress existe."
            http_client.force_login(admin_user)
            resp = http_client.post(reverse("event-admin-wizard-place"), {
                "postal_address": str(addr.pk),
            })
            assert resp.status_code == 302, resp.content[:500]
            assert resp.url == reverse("event-admin-wizard-event")
            assert http_client.session["event_wizard_admin_postal_address_pk"] == str(addr.pk)

    def test_post_avec_nouveau_lieu_cree_postal_address(
        self, http_client, admin_user, tenant, cleanup_created_events,
    ):
        from BaseBillet.models import PostalAddress
        with tenant_context(tenant):
            http_client.force_login(admin_user)
            count_before = PostalAddress.objects.count()
            resp = http_client.post(reverse("event-admin-wizard-place"), {
                "new_address_name": "Wizard test Salle des fetes",
                "street_address": "10 rue des Lilas",
                "postal_code": "97400",
                "address_locality": "Saint-Denis",
                "address_country": "France",
                "place_latitude": "-20.88",
                "place_longitude": "55.45",
                "place_adresse": "10 rue des Lilas, Saint-Denis",
            })
            assert resp.status_code == 302, resp.content[:500]
            assert PostalAddress.objects.count() == count_before + 1
            new_addr = PostalAddress.objects.filter(
                name="Wizard test Salle des fetes",
            ).order_by("-pk").first()
            assert new_addr is not None
            assert float(new_addr.latitude) == pytest.approx(-20.88)

    def test_post_sans_choix_renvoie_422(self, http_client, admin_user, tenant):
        with tenant_context(tenant):
            http_client.force_login(admin_user)
            resp = http_client.post(reverse("event-admin-wizard-place"), {})
            assert resp.status_code == 422

    def test_post_nouveau_lieu_sans_lat_lng_renvoie_422(self, http_client, admin_user, tenant):
        with tenant_context(tenant):
            http_client.force_login(admin_user)
            resp = http_client.post(reverse("event-admin-wizard-place"), {
                "new_address_name": "X",
                "street_address": "1 rue",
                "postal_code": "97400",
                "address_locality": "Saint-Denis",
            })
            assert resp.status_code == 422
            assert b"place_latitude" in resp.content or b"latitude" in resp.content


# ----------------------------------------------------------------------------
# Tests Step 2 — Access
# ----------------------------------------------------------------------------

@pytest.mark.django_db
class TestStep2EventAccess:
    def test_get_step2_sans_session_redirige_step1(self, http_client, admin_user, tenant):
        with tenant_context(tenant):
            http_client.force_login(admin_user)
            resp = http_client.get(reverse("event-admin-wizard-event"))
            assert resp.status_code == 302
            assert resp.url == reverse("event-admin-wizard-place")


# ----------------------------------------------------------------------------
# Tests Step 2 — Submit
# ----------------------------------------------------------------------------

@pytest.mark.django_db
class TestStep2EventSubmit:
    def _seed_session(self, http_client, tenant):
        from BaseBillet.models import PostalAddress
        with tenant_context(tenant):
            addr = PostalAddress.objects.first()
            assert addr, "Pre-requis : au moins une PostalAddress existe."
            session = http_client.session
            session["event_wizard_admin_postal_address_pk"] = str(addr.pk)
            session.save()
            return addr

    def test_post_minimum_cree_event_publie(
        self, http_client, admin_user, tenant, cleanup_created_events,
    ):
        from BaseBillet.models import Event
        addr = self._seed_session(http_client, tenant)
        http_client.force_login(admin_user)
        # Re-seed session apres force_login (qui peut renouveler la session).
        # / Re-seed session after force_login (which may rotate the session).
        session = http_client.session
        session["event_wizard_admin_postal_address_pk"] = str(addr.pk)
        session.save()
        with tenant_context(tenant):
            resp = http_client.post(reverse("event-admin-wizard-event"), {
                "name": "Wizard test Mon premier event",
                "datetime": "2026-12-31T20:00",
                "long_description": "Hello",
            })
            assert resp.status_code == 302, resp.content[:500]
            event = Event.objects.filter(name="Wizard test Mon premier event").first()
            assert event
            assert event.published is True
            assert event.is_proposal is False
            assert event.postal_address_id == addr.pk
            assert event.created_by == admin_user

    def test_post_avec_tags_cree_tags_inexistants(
        self, http_client, admin_user, tenant, cleanup_created_events,
    ):
        from BaseBillet.models import Event
        addr = self._seed_session(http_client, tenant)
        http_client.force_login(admin_user)
        session = http_client.session
        session["event_wizard_admin_postal_address_pk"] = str(addr.pk)
        session.save()
        with tenant_context(tenant):
            resp = http_client.post(reverse("event-admin-wizard-event"), {
                "name": "Wizard test Event with tags",
                "datetime": "2026-12-31T20:00",
                "tags": "Atelier, Gratuit, Nouveau-Tag-Wizard",
            })
            assert resp.status_code == 302, resp.content[:500]
            event = Event.objects.get(name="Wizard test Event with tags")
            tag_names = list(event.tag.values_list("name", flat=True))
            assert "Atelier" in tag_names
            assert "Nouveau-Tag-Wizard" in tag_names

    def test_post_succes_nettoie_session(
        self, http_client, admin_user, tenant, cleanup_created_events,
    ):
        addr = self._seed_session(http_client, tenant)
        http_client.force_login(admin_user)
        session = http_client.session
        session["event_wizard_admin_postal_address_pk"] = str(addr.pk)
        session.save()
        with tenant_context(tenant):
            http_client.post(reverse("event-admin-wizard-event"), {
                "name": "Wizard test Cleanup",
                "datetime": "2026-12-31T20:00",
            })
            assert "event_wizard_admin_postal_address_pk" not in http_client.session
