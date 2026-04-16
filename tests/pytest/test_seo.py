import pytest
from django.test import Client as DjangoTestClient
from Customers.models import Client


@pytest.mark.django_db
class TestSEOCacheModel:
    """Tests pour le modele SEOCache / Tests for SEOCache model"""

    def test_create_seo_cache_entry(self):
        """Creer une entree SEOCache avec tenant / Create SEOCache entry with tenant"""
        from seo.models import SEOCache

        client = Client.objects.filter(categorie=Client.ROOT).first()
        entry = SEOCache.objects.create(
            cache_type="tenant_summary",
            tenant=client,
            data={"name": "Test", "event_count": 5},
        )
        assert entry.pk is not None
        assert entry.data["event_count"] == 5
        assert entry.updated_at is not None

    def test_unique_together_constraint(self):
        """Pas de doublon (cache_type, tenant) / No duplicate (cache_type, tenant)"""
        from seo.models import SEOCache
        from django.db import IntegrityError, transaction

        client = Client.objects.filter(categorie=Client.ROOT).first()
        SEOCache.objects.create(cache_type="tenant_summary", tenant=client, data={})
        # IntegrityError doit etre dans un savepoint atomic sinon la transaction
        # courante devient "broken" et contamine TOUS les tests suivants avec
        # "current transaction is aborted" (PostgreSQL).
        # / IntegrityError must be inside an atomic savepoint, otherwise the
        # current transaction becomes "broken" and contaminates ALL following
        # tests with "current transaction is aborted" (PostgreSQL).
        with pytest.raises(IntegrityError), transaction.atomic():
            SEOCache.objects.create(cache_type="tenant_summary", tenant=client, data={})

    def test_global_cache_tenant_null(self):
        """Agregats globaux ont tenant=null / Global aggregates have tenant=null"""
        from seo.models import SEOCache

        entry = SEOCache.objects.create(
            cache_type="aggregate_events",
            tenant=None,
            data={"events": []},
        )
        assert entry.tenant is None

    def test_update_or_create_idempotent(self):
        """update_or_create ecrase sans doublon / update_or_create overwrites without duplicating"""
        from seo.models import SEOCache

        SEOCache.objects.update_or_create(
            cache_type="sitemap_index",
            tenant=None,
            defaults={"data": {"tenants": []}},
        )
        SEOCache.objects.update_or_create(
            cache_type="sitemap_index",
            tenant=None,
            defaults={"data": {"tenants": [{"domain": "test.com"}]}},
        )
        assert (
            SEOCache.objects.filter(cache_type="sitemap_index", tenant=None).count()
            == 1
        )
        entry = SEOCache.objects.get(cache_type="sitemap_index", tenant=None)
        assert len(entry.data["tenants"]) == 1


@pytest.mark.django_db
class TestRefreshSEOCache:
    """Tests pour le Celery task refresh_seo_cache / Tests for the refresh_seo_cache Celery task"""

    def test_refresh_seo_cache_creates_entries(self):
        """Le task cree des entrees SEOCache pour les tenants actifs
        / The task creates SEOCache entries for active tenants"""
        from seo.tasks import refresh_seo_cache
        from seo.models import SEOCache

        refresh_seo_cache()
        assert SEOCache.objects.filter(
            cache_type=SEOCache.AGGREGATE_EVENTS, tenant=None
        ).exists()
        assert SEOCache.objects.filter(
            cache_type=SEOCache.AGGREGATE_LIEUX, tenant=None
        ).exists()
        assert SEOCache.objects.filter(
            cache_type=SEOCache.SITEMAP_INDEX, tenant=None
        ).exists()

    def test_refresh_seo_cache_idempotent(self):
        """Deux executions consecutives, meme resultat
        / Two consecutive runs produce same result"""
        from seo.tasks import refresh_seo_cache
        from seo.models import SEOCache

        refresh_seo_cache()
        count_1 = SEOCache.objects.count()
        refresh_seo_cache()
        count_2 = SEOCache.objects.count()
        assert count_1 == count_2

    def test_cross_schema_query_returns_counts(self):
        """La requete SQL cross-schema retourne des counts corrects
        / The cross-schema SQL query returns correct counts"""
        from seo.services import get_active_tenants_with_counts

        results = get_active_tenants_with_counts()
        assert isinstance(results, list)
        for row in results:
            assert "tenant_id" in row
            assert "event_count" in row
            assert "membership_count" in row
            assert row["event_count"] >= 0
            assert row["membership_count"] >= 0


@pytest.mark.django_db
class TestSEOHelpers:
    """Tests pour les helpers SEO / Tests for SEO helpers"""

    def test_get_seo_cache_with_fallback(self):
        """Lecture L1 miss -> fallback L2 (DB)"""
        from seo.models import SEOCache
        from seo.views_common import get_seo_cache
        from django.core.cache import cache

        data = {"events": [{"name": "Test Event"}]}
        SEOCache.objects.update_or_create(
            cache_type=SEOCache.AGGREGATE_EVENTS,
            tenant=None,
            defaults={"data": data},
        )
        cache.delete("seo:aggregate_events:global")
        result = get_seo_cache(SEOCache.AGGREGATE_EVENTS)
        assert result is not None
        assert result["events"][0]["name"] == "Test Event"

    def test_build_json_ld_organization(self):
        """JSON-LD Organization bien forme"""
        from seo.views_common import build_json_ld_organization

        result = build_json_ld_organization(
            name="Test Org",
            url="https://test.com",
            logo_url="https://test.com/logo.png",
            description="A test org",
            same_as=["https://facebook.com/test"],
        )
        assert result["@context"] == "https://schema.org"
        assert result["@type"] == "Organization"
        assert result["name"] == "Test Org"
        assert result["sameAs"] == ["https://facebook.com/test"]

    def test_build_json_ld_product(self):
        """JSON-LD Product bien forme"""
        from seo.views_common import build_json_ld_product

        result = build_json_ld_product(
            name="Adhesion annuelle",
            description="Test",
            price="15.00",
            currency="EUR",
            url="https://test.com/memberships/123/",
        )
        assert result["@type"] == "Product"
        assert result["offers"]["price"] == "15.00"


@pytest.mark.django_db
class TestSitemaps:
    """Tests pour les sitemaps enrichis / Tests for enriched sitemaps"""

    def test_sitemap_accessible(self, api_client):
        """Le sitemap principal est accessible"""
        response = api_client.get("/sitemap.xml")
        assert response.status_code == 200

    def test_sitemap_contains_xml(self, api_client):
        """Le sitemap retourne du XML valide"""
        response = api_client.get("/sitemap.xml")
        content = response.content.decode()
        assert "<?xml" in content


@pytest.mark.django_db
class TestRootViews:
    """Tests pour les vues ROOT (schema public) / Tests for ROOT views (public schema)"""

    @pytest.fixture(autouse=True)
    def _setup_cache_and_client(self):
        """
        Remplit le cache SEO et cree un client HTTP pointant vers le ROOT tenant.
        / Populate SEO cache and create an HTTP client targeting the ROOT tenant.
        """
        from seo.tasks import refresh_seo_cache

        refresh_seo_cache()

        # Le ROOT tenant utilise le domaine www.tibillet.localhost.
        # django-tenants resout ce host vers le schema public → urls_public.py.
        # / The ROOT tenant uses www.tibillet.localhost domain.
        # django-tenants resolves this host to the public schema → urls_public.py.
        self.root_client = DjangoTestClient(HTTP_HOST="www.tibillet.localhost")

    def test_landing_page_returns_200(self):
        """La page d'accueil ROOT retourne 200 / ROOT landing page returns 200"""
        response = self.root_client.get("/")
        assert response.status_code == 200

    def test_landing_page_contains_key_figures(self):
        """La landing contient les chiffres cles / Landing contains key figures"""
        response = self.root_client.get("/")
        content = response.content.decode()
        assert "Lieux" in content
        # Le template utilise "Événements" (avec accents). Accepter les 2
        # variantes pour robustesse i18n.
        # / The template uses "Événements" (with accents). Accept both
        # variants for i18n robustness.
        assert any(s in content for s in ("Événements", "Evenements", "événements", "evenements"))

    def test_lieux_page_returns_200(self):
        """La page lieux retourne 200 / Venues page returns 200"""
        response = self.root_client.get("/lieux/")
        assert response.status_code == 200

    def test_evenements_page_returns_200(self):
        """La page evenements retourne 200 / Events page returns 200"""
        response = self.root_client.get("/evenements/")
        assert response.status_code == 200

    def test_adhesions_page_returns_200(self):
        """La page adhesions retourne 200 / Memberships page returns 200"""
        response = self.root_client.get("/adhesions/")
        assert response.status_code == 200

    def test_recherche_empty_query_returns_200(self):
        """La recherche sans terme retourne 200 / Search with empty query returns 200"""
        response = self.root_client.get("/recherche/?q=")
        assert response.status_code == 200

    def test_recherche_with_query_returns_200(self):
        """La recherche avec un terme retourne 200 / Search with a query returns 200"""
        response = self.root_client.get("/recherche/?q=test")
        assert response.status_code == 200

    def test_landing_contains_json_ld(self):
        """La landing contient du JSON-LD Organization / Landing contains JSON-LD Organization"""
        response = self.root_client.get("/")
        content = response.content.decode()
        assert "application/ld+json" in content
        assert "schema.org" in content


@pytest.mark.django_db
class TestRobotsTxtAndSitemap:
    """Tests robots.txt et sitemap tenant / Tests for robots.txt and tenant sitemap"""

    def test_robots_txt_contains_sitemap(self, api_client):
        """robots.txt contient la reference au sitemap / robots.txt contains sitemap reference"""
        response = api_client.get("/robots.txt")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Sitemap:" in content
        assert "sitemap.xml" in content

    def test_robots_txt_content_type(self, api_client):
        """robots.txt est en text/plain / robots.txt is text/plain"""
        response = api_client.get("/robots.txt")
        assert "text/plain" in response["Content-Type"]


@pytest.mark.django_db
class TestTenantSEOImprovements:
    """Tests pour les ameliorations SEO par tenant / Tests for tenant SEO improvements"""

    def test_canonical_link_in_response(self, api_client):
        """La page d'accueil contient un lien canonical / Homepage contains a canonical link"""
        response = api_client.get("/")
        content = response.content.decode()
        assert 'rel="canonical"' in content

    def test_json_ld_organization_in_response(self, api_client):
        """La page d'accueil contient du JSON-LD Organization / Homepage contains JSON-LD Organization"""
        response = api_client.get("/")
        content = response.content.decode()
        assert (
            '"@type": "Organization"' in content or '"@type":"Organization"' in content
        )
