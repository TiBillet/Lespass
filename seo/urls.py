"""
URLs ROOT pour le site public TiBillet (schema public).
/ ROOT URLs for the TiBillet public site (public schema).

LOCALISATION: seo/urls.py
"""

from django.urls import path

from seo import views
from seo.views_common import robots_txt

app_name = "seo"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("lieux/", views.lieux, name="lieux"),
    path("evenements/", views.evenements, name="evenements"),
    path("adhesions/", views.adhesions, name="adhesions"),
    path("recherche/", views.recherche, name="recherche"),
    path("explorer/", views.explorer, name="explorer"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("sitemap.xml", views.sitemap_index_view, name="sitemap_index"),
]
