from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.db import connection
from BaseBillet.models import Event, Product


class TenantSitemap(Sitemap):
    """
    Sitemap de base tenant-aware. Utilise le domaine du tenant courant.
    / Tenant-aware base sitemap. Uses the current tenant's domain.
    LOCALISATION: seo/sitemap.py
    """

    protocol = "https"

    def get_domain(self, site=None):
        """
        Retourne le domaine du tenant courant.
        / Returns the current tenant's domain.
        """
        return connection.tenant.get_primary_domain().domain


class EventSitemap(TenantSitemap):
    """
    Sitemap evenements publies. / Published events sitemap.
    LOCALISATION: seo/sitemap.py
    """

    changefreq = "daily"
    priority = 0.7

    def items(self):
        return Event.objects.filter(published=True)

    def lastmod(self, obj):
        return obj.created

    def location(self, obj):
        return reverse("event-detail", kwargs={"pk": obj.slug})


class ProductSitemap(TenantSitemap):
    """
    Sitemap adhesions/produits. / Memberships/products sitemap.
    LOCALISATION: seo/sitemap.py
    """

    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return Product.objects.filter(publish=True, categorie_article=Product.ADHESION)

    def location(self, obj):
        return reverse("membership_mvt-detail", kwargs={"pk": obj.uuid})


class StaticViewSitemap(TenantSitemap):
    """
    Sitemap pages statiques. / Static pages sitemap.
    LOCALISATION: seo/sitemap.py
    """

    priority = 0.5
    changefreq = "weekly"

    def items(self):
        return ["index", "event-list", "membership_mvt-list"]

    def location(self, item):
        return reverse(item)
