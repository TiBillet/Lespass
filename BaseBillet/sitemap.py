from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.db import connection
from BaseBillet.models import Event, Product

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

class ProductSitemap(TenantSitemap):
    """
    Sitemap for membership products.
    Includes all published membership/subscription products.
    Access at: https://yourdomain.com/sitemap.xml?section=products
    """
    changefreq = "weekly"  # Membership products change less frequently
    priority = 0.6  # Medium-high priority for search engines

    def items(self):
        # Only include published membership products
        return Product.objects.filter(publish=True, categorie_article=Product.ADHESION)

    def location(self, obj):
        # URL for each membership product - returns absolute path without protocol or domain
        # This follows Django's sitemap documentation requirements
        return reverse('membership_mvt-detail', kwargs={'pk': obj.uuid})

class StaticViewSitemap(TenantSitemap):
    """
    Sitemap for static pages.
    Includes the home page, events list page, and memberships list page.
    Access at: https://yourdomain.com/sitemap.xml?section=static
    """
    priority = 0.5  # Medium priority for search engines
    changefreq = "weekly"  # Static pages change infrequently

    def items(self):
        # List of static pages to include
        return ['index', 'event-list', 'membership_mvt-list']

    def location(self, item):
        # Generate URLs for each static page - returns absolute path without protocol or domain
        # This follows Django's sitemap documentation requirements
        if item == 'index':
            # Home page
            return reverse(item)
        elif item == 'event-list':
            # Events list page
            return reverse('event-list')
        elif item == 'membership_mvt-list':
            # Memberships list page
            return reverse('membership_mvt-list')
