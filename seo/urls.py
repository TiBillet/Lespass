"""
URLs ROOT pour le site public TiBillet (schema public).
/ ROOT URLs for the TiBillet public site (public schema).

LOCALISATION: seo/urls.py

Version V1 allegee : pas de /adhesions/. La navigation pointe vers
/explorer/ qui offre une carte interactive lieux + events.
/ V1 lightweight version: no /adhesions/. Navigation points to
/explorer/ which offers an interactive venues + events map.
"""

from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView

from seo import views
from seo.views_common import humans_txt, robots_txt

app_name = "seo"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("lieux/", views.lieux, name="lieux"),
    path("evenements/", views.evenements, name="evenements"),
    path("recherche/", views.recherche, name="recherche"),
    path("explorer/", views.explorer, name="explorer"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("humans.txt", humans_txt, name="humans_txt"),
    path("sitemap.xml", views.sitemap_index_view, name="sitemap_index"),
    # /favicon.ico est demande automatiquement par les navigateurs sur toutes
    # les pages, y compris non-HTML (sitemap.xml, robots.txt). On evite le 404
    # en redirigeant vers le SVG vendore.
    # / Browsers auto-request /favicon.ico on all pages including non-HTML.
    # Redirect to the vendored SVG to avoid 404s.
    path(
        "favicon.ico",
        RedirectView.as_view(url=static("seo/favicon.svg"), permanent=True),
        name="favicon_ico",
    ),
]
