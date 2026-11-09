"""
Sitemap des ressources réservables et des plannings de bénévoles.
/ Sitemap of the bookable resources and the volunteer plannings.

LOCALISATION : booking/sitemap.py

S'ajoute au sitemap.xml du tenant (cf. TiBillet/urls_tenants.py), aux côtés des
events/static/pages. Réutilise TenantSitemap (domaine du tenant + https).
Les pages liste (/booking/, /booking/benevolat/) sont dans StaticViewSitemap.
/ Plugs into the tenant sitemap.xml. List pages live in StaticViewSitemap.
"""

from django.urls import reverse

from BaseBillet.models import Configuration
from BaseBillet.sitemap import TenantSitemap
from booking.benevolat import plannings_publies_avec_des_besoins_a_venir
from booking.models import Resource


class RessourceSitemap(TenantSitemap):
    """
    Sitemap des ressources : toutes celles de la page /booking/, quand le module
    booking est actif. Une ressource n'a pas d'état « brouillon » : la page
    /booking/ les affiche toutes.
    Accès : https://<tenant>/sitemap.xml?section=ressources
    / All resources of the /booking/ page, when the booking module is on.
    """

    changefreq = "weekly"
    priority = 0.6

    def items(self):
        # Module éteint : le menu n'affiche plus la page, on ne la déclare pas.
        # / Module off: the menu hides the page, do not declare it.
        config = Configuration.get_solo()
        if not config.module_booking:
            return Resource.objects.none()
        return Resource.objects.order_by("name")

    def location(self, obj):
        # Chemin absolu SANS protocole ni domaine (cf. doc Django).
        # / Absolute path WITHOUT protocol or domain (see Django docs).
        return reverse("booking-resource", kwargs={"pk": obj.pk})


class PlanningSitemap(TenantSitemap):
    """
    Sitemap des plannings de bénévoles publiés qui ont un besoin à venir, quand le
    module bénévolat est actif. Ce sont ceux de la page liste.
    Pas déclarés : un planning non publié (404 pour le public) ; un planning sans
    besoin à venir (sa page ne dit que « Aucun besoin à venir »).
    Accès : https://<tenant>/sitemap.xml?section=plannings
    / Published plannings with an upcoming need, when the volunteering module is on.
    """

    changefreq = "daily"
    priority = 0.5

    def items(self):
        # Module éteint : le menu n'affiche plus la page, on ne la déclare pas.
        # / Module off: the menu hides the page, do not declare it.
        config = Configuration.get_solo()
        if not config.module_benevolat:
            return []
        return plannings_publies_avec_des_besoins_a_venir()

    def location(self, obj):
        # Chemin absolu SANS protocole ni domaine (cf. doc Django).
        # / Absolute path WITHOUT protocol or domain (see Django docs).
        return reverse("benevolat-planning", kwargs={"slug": obj.slug})
