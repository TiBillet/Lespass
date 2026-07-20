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

from seo import views, views_legal
from seo.views_common import humans_txt, robots_txt

app_name = "seo"

urlpatterns = [
    path("", views.landing, name="landing"),
    # Hub des fonctionnalites (page liste). Avant la route <slug> pour la lisibilite.
    # / Features hub (list page). Before the <slug> route for readability.
    path("features/", views.features_hub, name="features_hub"),
    # Page de detail d'une fonctionnalite (captures, descriptions, liens doc).
    # / Feature detail page (screenshots, descriptions, doc links).
    path("features/<slug:slug>/", views.feature_detail, name="feature_detail"),
    path("recherche/", views.recherche, name="recherche"),
    path("explorer/", views.explorer, name="explorer"),
    # Pages legales du site ROOT. Le texte vit dans des gabarits versionnes
    # (seo/templates/seo/legal/) et non en base : l'historique git permet de
    # prouver quel texte etait affiche a une date donnee.
    # / ROOT legal pages. Text lives in versioned templates, not in the DB:
    # git history proves which wording was live on a given date.
    path("mentions-legales/", views_legal.mentions_legales, name="mentions_legales"),
    path("cgu/", views_legal.cgu, name="cgu"),
    path("confidentialite/", views_legal.confidentialite, name="confidentialite"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("humans.txt", humans_txt, name="humans_txt"),
    path("sitemap.xml", views.sitemap_index_view, name="sitemap_index"),
    # Sitemap des pages ROOT (landing + fonctionnalites), reference dans l'index.
    # / ROOT pages sitemap (landing + features), referenced in the index.
    path("sitemap-root.xml", views.sitemap_root_view, name="sitemap_root"),
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
