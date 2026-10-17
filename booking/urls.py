"""
URLs de l'app booking — réservation de ressources partagées et planning des bénévoles.
/ booking app URLs — shared resource reservation and volunteer planning.

LOCALISATION : booking/urls.py

L'URL de base est 'booking/' (définie dans TiBillet/urls_tenants.py).
/ Base URL is 'booking/' (defined in TiBillet/urls_tenants.py).

Les routes du bénévolat passent AVANT router.urls : BookingViewSet est enregistré sur
le préfixe vide, ses routes « <pk>/resource/ », « <pk>/book/ »… avaleraient sinon un
planning dont le slug vaut « book ».
/ Volunteering routes come BEFORE router.urls: BookingViewSet sits on the empty prefix.
"""
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BookingViewSet
from .views_benevolat import BenevolatViewSet

router = DefaultRouter()
router.register(r"", BookingViewSet, basename="booking") # Booking add from


urlpatterns = [
    path(
        "benevolat/besoin/<uuid:pk>/inscrire/",
        BenevolatViewSet.as_view({"post": "inscrire"}),
        name="benevolat-inscrire",
    ),
    path(
        "benevolat/besoin/<uuid:pk>/retirer/",
        BenevolatViewSet.as_view({"post": "retirer"}),
        name="benevolat-retirer",
    ),
    path(
        "benevolat/besoin/<uuid:pk>/inscrire-une-personne/",
        BenevolatViewSet.as_view({"get": "inscrire_une_personne", "post": "inscrire_une_personne"}),
        name="benevolat-inscrire-une-personne",
    ),
    path(
        "benevolat/besoin/<uuid:pk>/chercher-une-personne/",
        BenevolatViewSet.as_view({"get": "chercher_une_personne"}),
        name="benevolat-chercher-une-personne",
    ),
    # La lettre passe AVANT le désistement : les deux routes ont le même nombre de
    # segments. Un jeton signé contient toujours « : », il ne vaut jamais « lettre » ;
    # et PlanningBenevole.clean() refuse le slug « desistement ».
    # / "lettre" BEFORE "desistement": same segment count.
    path(
        "benevolat/<slug:slug>/lettre/",
        BenevolatViewSet.as_view({"post": "lettre"}),
        name="benevolat-lettre",
    ),
    path(
        "benevolat/desistement/<str:jeton>/",
        BenevolatViewSet.as_view({"get": "desistement", "post": "desistement"}),
        name="benevolat-desistement",
    ),
    path(
        "benevolat/<slug:slug>/",
        BenevolatViewSet.as_view({"get": "retrieve"}),
        name="benevolat-planning",
    ),
    # La liste des plannings (entrée « Bénévolat » du menu du site).
    # / The plannings list (the site menu's "Bénévolat" entry).
    path(
        "benevolat/",
        BenevolatViewSet.as_view({"get": "list"}),
        name="benevolat-liste",
    ),
] + router.urls
