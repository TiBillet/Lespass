from datetime import timedelta

from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.db import connection
from django.utils import timezone
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

# Un evenement passe reste en ligne, mais il sort du sitemap apres cette duree.
# On ne pousse plus vers Google des pages d'archive qui n'interessent personne.
# / A past event stays online, but leaves the sitemap after this delay.
DUREE_DES_EVENEMENTS_PASSES_DANS_LE_SITEMAP = timedelta(days=183)


def evenements_du_sitemap():
    """
    Les evenements declares a Google : les memes que l'agenda du lieu.
    / Events declared to Google: the same as the venue's agenda.

    LOCALISATION : BaseBillet/sitemap.py

    - publies et non archives (un event archive est retire de l'agenda) ;
    - sans les actions benevoles (elles s'affichent dans l'evenement parent) ;
    - passes depuis moins de 6 mois.
    Les evenements « non federables » (private=True) restent : ils ne sont caches
    que des agendas des AUTRES lieux, pas de celui du lieu.
    / Published, not archived, no volunteer actions, past for less than 6 months.
    Non-federable events stay: they are only hidden from other venues' agendas.
    """
    date_limite = timezone.now() - DUREE_DES_EVENEMENTS_PASSES_DANS_LE_SITEMAP
    return Event.objects.filter(
        published=True,
        archived=False,
        datetime__gte=date_limite,
    ).exclude(categorie=Event.ACTION)


class EventSitemap(TenantSitemap):
    """
    Sitemap for events.
    Includes the events of the venue's agenda (see evenements_du_sitemap).
    Access at: https://yourdomain.com/sitemap.xml?section=events
    """
    changefreq = "daily"  # Events change frequently
    priority = 0.7  # High priority for search engines

    # Pas de lastmod : l'evenement n'a pas de date de modification. Une date
    # fausse (la date de creation) fait ignorer tous les lastmod du site par Google.
    # / No lastmod: Event has no modification date, and a wrong one discredits them all.

    def items(self):
        return evenements_du_sitemap()

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
        pages = []

        # Racine "/" : une page d'accueil CMS publiee la remplit toujours.
        # Sinon c'est l'accueil par defaut, et on applique la meme regle que sa
        # balise robots (vues/accueil.html). L'accueil affiche aussi les
        # evenements des lieux federes : un lieu federe compte donc comme
        # « a des evenements » (en cas de doute on inclut).
        # / "/" : a published CMS home always fills it. Otherwise, same rule as
        # the default home's robots tag; a federated venue counts as having events.
        from TiBillet.seo_indexing import accueil_par_defaut_est_vide

        accueil_cms_publie = False
        if config.module_pages:
            from pages.models import Page
            accueil_cms_publie = Page.objects.filter(est_accueil=True, publie=True).exists()

        il_y_a_des_evenements = (
            Event.objects.filter(published=True, datetime__gte=timezone.now()).exists()
            or FederatedPlace.objects.exists()
        )
        if accueil_cms_publie or not accueil_par_defaut_est_vide(config, il_y_a_des_evenements):
            pages.append('index')

        # Meme filtre que EventSitemap, pour ne pas se contredire.
        # / Same filter as EventSitemap.
        if config.module_billetterie and evenements_du_sitemap().exists():
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

        # La page « Autour de nous » se nourrit de trois sources : les lieux
        # declares ici, les lieux qui nous declarent (si l'option est active),
        # et les lieux trouves par tags. Memes sources que FederationViewset.list
        # (BaseBillet/views.py) : sans aucun voisin, la page est vide.
        # / Same three sources as FederationViewset.list: no neighbour, empty page.
        if config.module_federation:
            from seo.models import SEOCache
            from seo.services import get_tenant_uuids_with_event_tags
            from seo.views_common import get_seo_cache

            config_federation = FederationConfiguration.get_solo()
            uuid_du_lieu_courant = str(connection.tenant.uuid)

            voisins_entrants_ou_par_tags = set()
            if config_federation.afficher_lieux_entrants:
                lieux_entrants = get_seo_cache(SEOCache.FEDERATION_INCOMING) or {}
                voisins_entrants_ou_par_tags |= set(
                    lieux_entrants.get("by_tenant", {}).get(uuid_du_lieu_courant, [])
                )
            slugs_des_tags = [tag.slug for tag in config_federation.tags_federation.all()]
            voisins_entrants_ou_par_tags |= get_tenant_uuids_with_event_tags(slugs_des_tags)
            voisins_entrants_ou_par_tags.discard(uuid_du_lieu_courant)

            if FederatedPlace.objects.exists() or voisins_entrants_ou_par_tags:
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
