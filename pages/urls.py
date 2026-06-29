"""
URLs publiques de l'app pages.
/ Public URLs of the pages app.

LOCALISATION : pages/urls.py

La route /<slug>/ est un "attrape-tout" : elle doit etre incluse APRES les routes
de BaseBillet dans urls_tenants.py, pour que les routes specifiques existantes
(/event/, /my_account/, etc.) gagnent. La validation des slugs reserves (cf.
pages/models.py) empeche de creer une page dont le slug entrerait en collision.
/ The /<slug>/ route is a catch-all: it must be included AFTER BaseBillet's routes
in urls_tenants.py, so existing specific routes (/event/, /my_account/, etc.) win.
Reserved-slug validation (see pages/models.py) prevents creating a page whose slug
would collide.
"""

from django.urls import path

from pages import views

app_name = "pages"

urlpatterns = [
    path("<slug:slug>/", views.page_publique, name="page_publique"),
]
