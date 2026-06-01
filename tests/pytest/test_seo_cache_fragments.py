"""
Tests du cache SEO en fragments par tenant (CHANTIER-07).
/ Tests for the per-tenant SEO cache fragments.

LOCALISATION : tests/pytest/test_seo_cache_fragments.py
Voir SESSIONS/SEO/CHANTIER-07-cache-fragments.md.

Reutilise la base de dev (schema lespass), comme test_seo_aggregate_points / e2e_slugs.
"""

import pytest

from Customers.models import Client


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de base de test).
    # / Reuse dev DB (no test DB creation).
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()


@pytest.mark.django_db
def test_refresh_tenant_ecrit_les_3_fragments_du_tenant_seulement():
    """refresh_tenant_seo_cache(X) ecrit TENANT_SUMMARY/EVENTS/POINTS pour X."""
    from seo.tasks import refresh_tenant_seo_cache
    from seo.models import SEOCache

    lespass = Client.objects.get(schema_name="lespass")
    resultat = refresh_tenant_seo_cache(str(lespass.uuid))

    assert resultat["tenant"] == str(lespass.uuid)
    for cache_type in (SEOCache.TENANT_SUMMARY, SEOCache.TENANT_EVENTS, SEOCache.TENANT_POINTS):
        assert SEOCache.objects.filter(cache_type=cache_type, tenant=lespass).exists(), cache_type


@pytest.mark.django_db
def test_rebuild_aggregate_points_est_la_concat_des_fragments():
    """AGGREGATE_POINTS = somme des points de tous les fragments TENANT_POINTS."""
    from seo.tasks import refresh_seo_cache, rebuild_seo_aggregates
    from seo.models import SEOCache

    refresh_seo_cache()        # peuple tous les fragments + agregats
    rebuild_seo_aggregates()   # recombine (idempotent)

    total_fragments = 0
    for entry in SEOCache.objects.filter(cache_type=SEOCache.TENANT_POINTS):
        total_fragments += len(entry.data.get("points", []))

    agg = SEOCache.objects.get(cache_type=SEOCache.AGGREGATE_POINTS, tenant=None)
    assert len(agg.data.get("points", [])) == total_fragments


@pytest.mark.django_db
def test_pa_id_uniques_dans_agregat_apres_refactor():
    """Le pa_id reste unique cross-tenant apres recombinaison (bug 1 preserve)."""
    from seo.tasks import refresh_seo_cache
    from seo.models import SEOCache

    refresh_seo_cache()
    agg = SEOCache.objects.get(cache_type=SEOCache.AGGREGATE_POINTS, tenant=None)
    pa_ids = [p["pa_id"] for p in agg.data.get("points", [])]
    assert len(pa_ids) == len(set(pa_ids))  # zero collision


@pytest.mark.django_db
def test_rebuild_ne_touche_pas_federation_incoming():
    """rebuild_seo_aggregates ne recalcule PAS FEDERATION_INCOMING (reserve au beat)."""
    from seo.tasks import refresh_seo_cache, rebuild_seo_aggregates
    from seo.models import SEOCache

    refresh_seo_cache()  # calcule FEDERATION_INCOMING (au beat)
    avant = SEOCache.objects.get(cache_type=SEOCache.FEDERATION_INCOMING, tenant=None).updated_at

    rebuild_seo_aggregates()  # ne doit pas toucher FEDERATION_INCOMING
    apres = SEOCache.objects.get(cache_type=SEOCache.FEDERATION_INCOMING, tenant=None).updated_at

    assert avant == apres
