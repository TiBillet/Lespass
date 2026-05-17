"""
Tests unitaires pour les helpers AGGREGATE_POINTS (seo/services.py)
/ Unit tests for the AGGREGATE_POINTS helpers.

LOCALISATION : tests/pytest/test_seo_aggregate_points.py
Voir SESSIONS/SEO/CHANTIER-05-explorer-markers-per-pa.md pour la spec.

NOTE : ces tests utilisent la DB de dev existante (pas une DB de test isolee).
Ils reposent sur le pattern etabli par onboard/tests/conftest.py :
  - django_db_setup est override pour ne pas creer de test DB
  - _enable_db_access_for_all desactive le bloqueur DB pour la session
Le conftest.py local (voir ci-dessous dans ce fichier) fournit ces fixtures.

/ NOTE: these tests use the existing dev DB (not an isolated test DB).
They follow the pattern established in onboard/tests/conftest.py:
  - django_db_setup is overridden to skip test DB creation
  - _enable_db_access_for_all disables the DB blocker for the session
The local conftest.py (see below in this file) provides these fixtures.
"""

from decimal import Decimal

import pytest
from django_tenants.utils import tenant_context

from Customers.models import Client


def test_get_postal_addresses_for_tenants_renvoie_pa_avec_coords_seulement():
    """
    Une PA sans coords ne doit pas remonter. Une PA avec lat/lng remonte.
    / PA without coords doesn't show up. PA with lat/lng does.
    """
    from seo.services import get_postal_addresses_for_tenants
    from BaseBillet.models import PostalAddress

    tenant = Client.objects.exclude(schema_name="public").first()
    if tenant is None:
        pytest.skip("Aucun tenant non-public disponible en DB — lancer contre la DB dev.")

    # Nettoyage des PA creees par ce test avant de commencer (idempotent)
    # / Cleanup any PA created by this test before starting (idempotent)
    with tenant_context(tenant):
        PostalAddress.objects.filter(name__in=["Sans coords", "Avec coords"]).delete()

    with tenant_context(tenant):
        pa_sans_coords = PostalAddress.objects.create(name="Sans coords")
        pa_avec_coords = PostalAddress.objects.create(
            name="Avec coords",
            latitude=Decimal("48.8566"),
            longitude=Decimal("2.3522"),
        )

    try:
        resultat = get_postal_addresses_for_tenants([(str(tenant.uuid), tenant.schema_name)])
        pa_ids = [pa["pa_id"] for pa in resultat.get(str(tenant.uuid), [])]
        assert pa_avec_coords.pk in pa_ids
        assert pa_sans_coords.pk not in pa_ids
    finally:
        # Nettoyage : on supprime les PA creees par ce test
        # / Cleanup: delete the PAs created by this test
        with tenant_context(tenant):
            PostalAddress.objects.filter(pk__in=[pa_sans_coords.pk, pa_avec_coords.pk]).delete()
