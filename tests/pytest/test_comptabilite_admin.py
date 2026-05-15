"""
Tests smoke S1 — modele ClotureCaisse + admin Unfold.
/ Smoke tests S1 — ClotureCaisse model + Unfold admin.

LOCALISATION : tests/pytest/test_comptabilite_admin.py

S1 livre uniquement le squelette : modele, migration, admin liste vide,
entree sidebar. Ces tests verifient qu'on peut creer une cloture en base
et que la page admin se charge.
/ S1 only delivers the skeleton: model, migration, empty admin list,
sidebar entry. These tests verify we can create a closure and that
the admin page loads.

NOTE TECHNIQUE : ces tests reutilisent la base de donnees dev existante
(pattern V2 onboard — pas de test DB creee a chaque run). Obligatoire
car django-tenants necessite un schema tenant reel pour les modeles
TENANT_APPS.
/ TECHNICAL NOTE: these tests reuse the existing dev DB (onboard V2 pattern
— no test DB created per run). Required because django-tenants needs a real
tenant schema for TENANT_APPS models.
"""
import pytest
from django_tenants.utils import tenant_context


# ---------------------------------------------------------------------------
# Override : reutiliser la DB dev au lieu d'une test DB temporaire.
# / Override: reuse the dev DB instead of a temporary test DB.
# Meme pattern que onboard/tests/conftest.py.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def django_db_setup():
    """
    Pas de creation de test DB — on utilise la DB dev existante.
    / No test DB creation — we use the existing dev DB.
    """
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    """
    Desactive le bloqueur d'acces DB de pytest-django pour toute la session.
    / Disable pytest-django's DB access blocker for the whole session.
    """
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.django_db


def test_app_comptabilite_dans_installed_apps():
    """
    L'app comptabilite est bien chargee par Django (presente dans INSTALLED_APPS).
    / The comptabilite app is properly loaded by Django.
    """
    from django.apps import apps
    assert apps.is_installed("comptabilite"), (
        "L'app 'comptabilite' n'est pas dans INSTALLED_APPS"
    )


def test_modele_cloturecaisse_creation_minimale():
    """
    On peut creer une ClotureCaisse minimale dans un schema tenant.
    / We can create a minimal ClotureCaisse in a tenant schema.

    On utilise le tenant 'lespass' de la DB dev.
    / We use the 'lespass' tenant from the dev DB.
    """
    from Customers.models import Client
    tenant = Client.objects.exclude(schema_name="public").first()
    assert tenant is not None, "Aucun tenant non-public disponible pour le test"

    from django.utils import timezone
    from datetime import timedelta

    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse

        debut = timezone.now() - timedelta(days=1)
        fin = timezone.now()

        cloture = ClotureCaisse.objects.create(
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            numero_sequentiel=1,
            datetime_debut=debut,
            datetime_fin=fin,
        )

        assert cloture.pk is not None
        assert cloture.numero_sequentiel == 1
        assert cloture.niveau == "J"
        assert cloture.total_general == 0
        assert cloture.rapport_json == {}

        # Nettoyage pour ne pas polluer la DB dev.
        # / Cleanup to avoid polluting the dev DB.
        cloture.delete()


def test_modele_cloturecaisse_unique_numero_sequentiel():
    """
    Le numero sequentiel est unique globalement par tenant.
    / Sequential number is globally unique per tenant.
    """
    from Customers.models import Client
    tenant = Client.objects.exclude(schema_name="public").first()
    assert tenant is not None, "Aucun tenant non-public disponible pour le test"

    from django.utils import timezone
    from datetime import timedelta
    from django.db import IntegrityError

    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        from django.db import transaction

        debut = timezone.now() - timedelta(days=2)
        fin1 = timezone.now() - timedelta(days=1)

        cloture1 = ClotureCaisse.objects.create(
            niveau="J", numero_sequentiel=9999,
            datetime_debut=debut, datetime_fin=fin1,
        )

        # La violation de contrainte casse la transaction courante.
        # On utilise un savepoint pour isoler l'echec et pouvoir continuer.
        # / The constraint violation breaks the current transaction.
        # Use a savepoint to isolate the failure and allow cleanup.
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ClotureCaisse.objects.create(
                    niveau="H", numero_sequentiel=9999,  # meme numero / same number
                    datetime_debut=debut,
                    datetime_fin=timezone.now(),
                )

        # Nettoyage / Cleanup
        cloture1.delete()


# ============================================================================
# Tests admin Unfold
# ============================================================================

@pytest.fixture
def admin_client():
    """
    Client Django authentifie en tant qu'admin sur un tenant.
    / Django client logged in as admin on a tenant.

    Reutilise la DB dev — meme pattern que les autres tests de ce fichier.
    / Reuses the dev DB — same pattern as other tests in this file.
    """
    from django.test import Client as DjangoClient
    from Customers.models import Client as TenantClient
    from AuthBillet.models import TibilletUser

    tenant = TenantClient.objects.exclude(schema_name="public").first()
    assert tenant is not None, "Aucun tenant non-public disponible"
    domain = tenant.domains.first()
    assert domain is not None, f"Tenant {tenant.schema_name} n'a pas de Domain"

    with tenant_context(tenant):
        admin_user, _created = TibilletUser.objects.get_or_create(
            email="admin@admin.com",
            defaults={"is_staff": True, "is_superuser": True, "is_active": True},
        )
        if not admin_user.is_staff:
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.is_active = True
            admin_user.save()

    client = DjangoClient(HTTP_HOST=domain.domain)
    client.force_login(admin_user)
    return client, domain


def test_admin_changelist_se_charge(admin_client):
    """
    GET /admin/comptabilite/cloturecaisse/ retourne 200.
    / The admin changelist returns 200.
    """
    client, _ = admin_client
    response = client.get("/admin/comptabilite/cloturecaisse/")
    assert response.status_code == 200, (
        f"Status {response.status_code} — body: {response.content[:500]}"
    )


def test_admin_pas_de_bouton_add(admin_client):
    """
    Le bouton 'Add' n'est PAS present (modele immuable).
    / The 'Add' button is NOT present (immutable model).
    """
    client, _ = admin_client
    response = client.get("/admin/comptabilite/cloturecaisse/")
    contenu = response.content.decode("utf-8")
    # Unfold rend le bouton "add" avec href contenant '/add/'.
    # / Unfold renders the "add" button with href containing '/add/'.
    assert "/comptabilite/cloturecaisse/add/" not in contenu, (
        "Le bouton Add ne devrait pas etre present pour ClotureCaisse"
    )
