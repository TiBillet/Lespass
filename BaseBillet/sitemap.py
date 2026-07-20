from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.db import connection
from BaseBillet.models import Event

# This file defines the sitemaps for the TiBillet application.
# The sitemaps are accessible at:
# - Complete sitemap: https://yourdomain.com/sitemap.xml
# - Events sitemap: https://yourdomain.com/sitemap.xml?section=events
# - Products sitemap: https://yourdomain.com/sitemap.xml?section=products
# - Static pages sitemap: https://yourdomain.com/sitemap.xml?section=static
#
# IMPORTANT: According to Django's documentation, the location() method should return
# an absolute path WITHOUT protocol or domain. For example:
#   - Good: '/foo/bar/'
#   - Bad: 'example.com/foo/bar/'
#   - Bad: 'https://example.com/foo/bar/'
#
# This implementation follows these guidelines by using Django's reverse() function,
# which returns paths without protocol or domain. The TenantSitemap base class
# provides the protocol and domain information separately.

class TenantSitemap(Sitemap):
    """
    Base sitemap class that uses the tenant's domain instead of the default Site domain.

    Django's sitemap framework combines:
    1. The protocol (https)
    2. The domain (from get_domain())
    3. The path (from location())

    The location() method in child classes should return only the path part
    (e.g., '/events/my-event/') without protocol or domain, as per Django's documentation.
    Django will automatically combine this with the protocol and domain to create the full URL.
    """
    protocol = 'https'  # Use HTTPS for all URLs

    def get_domain(self, site=None):
        """
        Override the get_domain method to use the tenant's domain.
        This domain will be combined with the protocol and the path from location()
        to create the full URL in the sitemap.
        """
        return connection.tenant.get_primary_domain().domain

class EventSitemap(TenantSitemap):
    """
    Sitemap for events.
    Includes all published events with their URLs.
    Access at: https://yourdomain.com/sitemap.xml?section=events
    """
    changefreq = "daily"  # Events change frequently
    priority = 0.7  # High priority for search engines

    def items(self):
        # Only include published events
        return Event.objects.filter(published=True)

    def lastmod(self, obj):
        # Last modification date is the creation date
        return obj.created

    def location(self, obj):
        # URL for each event - returns absolute path without protocol or domain
        # This follows Django's sitemap documentation requirements
        return reverse('event-detail', kwargs={'pk': obj.slug})

# ProductSitemap SUPPRIMÉ (audit SEO 2026-07-05) : listait les fragments
# HTMX /memberships/<uuid>/ — retiré de urls_tenants.py en même temps.
# / ProductSitemap REMOVED: listed the /memberships/<uuid>/ HTMX fragments.


class StaticViewSitemap(TenantSitemap):
    """
    Sitemap for static pages.
    Includes the home page, events list page, and memberships list page.
    Access at: https://yourdomain.com/sitemap.xml?section=static
    """
    priority = 0.5  # Medium priority for search engines
    changefreq = "weekly"  # Static pages change infrequently

    def items(self):
        # Une section n'est declaree que si son module est actif ET qu'elle
        # a du contenu : une page vide au sitemap est un signal negatif.
        # Recalcule a chaque requete, donc une section reapparait seule des
        # qu'elle se remplit.
        # En cas de doute on INCLUT : exclure a tort coute du referencement.
        # / A section is declared only if its module is on AND it has
        # content. Recomputed per request. When unsure, include.

        # Import local : evite un import circulaire (module charge par urls).
        # / Local import: avoids a circular import.
        from BaseBillet.models import (
            Configuration,
            FederatedPlace,
            FederationConfiguration,
            Product,
        )

        config = Configuration.get_solo()
        pages = ['index']

        # Meme filtre que EventSitemap, pour ne pas se contredire.
        # / Same filter as EventSitemap.
        if config.module_billetterie and Event.objects.filter(published=True).exists():
            pages.append('event-list')

        # La page liste les adhesions locales ET celles des lieux federes
        # (cf. MembershipMVT.list) : tester les seules locales exclurait du
        # sitemap une page pleine.
        # / The page lists local memberships AND federated ones; testing only
        # local products would drop a full page from the sitemap.
        if config.module_adhesion and (
            Product.objects.filter(
                categorie_article=Product.ADHESION, publish=True,
            ).exists()
            or FederatedPlace.objects.filter(membership_visible=True).exists()
        ):
            pages.append('membership_mvt-list')

        # La page se nourrit de trois sources (lieux declares, entrants,
        # tags) ; on teste les deux moins couteuses.
        # / Three sources feed this page; we test the two cheapest.
        if config.module_federation:
            config_federation = FederationConfiguration.get_solo()
            if FederatedPlace.objects.exists() or config_federation.afficher_lieux_entrants:
                pages.append('federation-list')

        return pages

    def location(self, item):
        # Generate URLs for each static page - returns absolute path without protocol or domain
        # / Genere les URL pour chaque page statique — retourne le chemin absolu sans protocole/domaine
        if item == 'index':
            return reverse(item)
        elif item == 'event-list':
            return reverse('event-list')
        elif item == 'membership_mvt-list':
            return reverse('membership_mvt-list')
        elif item == 'federation-list':
            # Page "Reseau local" — explorer carte/liste des lieux federes
            # / "Local network" page — federated lieux explorer (map/list)
            return reverse('federation-list')
