"""
Sitemap des pages publiques de l'app pages.
/ Sitemap of the public pages of the pages app.

LOCALISATION : pages/sitemap.py

S'ajoute au sitemap.xml du tenant (cf. TiBillet/urls_tenants.py), aux côtés des
events/products/static. Réutilise TenantSitemap (domaine du tenant + https).
/ Plugs into the tenant sitemap.xml (see urls_tenants.py), next to events/products
/static. Reuses TenantSitemap (tenant domain + https).
"""

from BaseBillet.sitemap import TenantSitemap
from pages.models import Page


class PageSitemap(TenantSitemap):
    """
    Sitemap des Pages publiées (hors brouillons et pages noindex).
    Accès : https://<tenant>/sitemap.xml?section=pages
    / Sitemap of published Pages (excluding drafts and noindex pages).
    """

    changefreq = "weekly"
    priority = 0.6

    def items(self):
        # Pages publiées, non exclues des moteurs, et HORS page d'accueil :
        # la racine "/" est déjà listée par StaticViewSitemap ('index'), on évite
        # ainsi un doublon. / Published, non-noindex pages, EXCLUDING the home page:
        # root "/" is already listed by StaticViewSitemap ('index'), avoiding a dup.
        return Page.objects.filter(publie=True, noindex=False, est_accueil=False)

    def lastmod(self, obj):
        # Dernière modification de la page.
        # / Last modification of the page.
        return obj.updated_at

    def location(self, obj):
        # Chemin absolu SANS protocole ni domaine (cf. doc Django).
        # L'adresse vient de la page elle-meme : voir Page.get_absolute_url().
        # / Absolute path WITHOUT protocol or domain (see Django docs).
        # The address comes from the page itself: see Page.get_absolute_url().
        return obj.get_absolute_url()
