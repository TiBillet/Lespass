# laboutik/urls.py
# Routage DRF pour l'interface de caisse LaBoutik.
# DRF routing for the LaBoutik cash register interface.
#
# Inclus depuis TiBillet/urls_tenants.py : path('laboutik/', include('laboutik.urls'))
# Included from TiBillet/urls_tenants.py: path('laboutik/', include('laboutik.urls'))
#
# URLs générées / Generated URLs :
#   /laboutik/caisse/                     → CaisseViewSet.list (page d'attente carte primaire)
#   /laboutik/caisse/carte_primaire/      → CaisseViewSet.carte_primaire (validation carte NFC)
#   /laboutik/caisse/point_de_vente/      → CaisseViewSet.point_de_vente (interface POS)
#   /laboutik/paiement/moyens_paiement/   → PaiementViewSet.moyens_paiement (boutons paiement)
#   /laboutik/paiement/confirmer/         → PaiementViewSet.confirmer (confirmation)
#   /laboutik/paiement/payer/             → PaiementViewSet.payer (exécution paiement)
#   /laboutik/paiement/lire_nfc/          → PaiementViewSet.lire_nfc (attente lecture NFC)
#   /laboutik/paiement/verifier_carte/    → PaiementViewSet.verifier_carte (check carte)
#   /laboutik/paiement/retour_carte/      → PaiementViewSet.retour_carte (feedback carte)
#   /laboutik/article-panel/<uuid>/panel/ → ArticlePanelViewSet.panel (menu contextuel)
#   /laboutik/article-panel/<uuid>/stock/ → ArticlePanelViewSet.stock_detail (vue stock)
#   /laboutik/article-panel/<uuid>/stock/<action>/ → ArticlePanelViewSet.stock_action (POST)

from django.urls import path
from rest_framework import routers

from laboutik.views import (
    ArticlePanelViewSet,
    CaisseViewSet,
    CommandeViewSet,
    PaiementViewSet,
)

router = routers.DefaultRouter()
router.register(r"caisse", CaisseViewSet, basename="laboutik-caisse")
router.register(r"paiement", PaiementViewSet, basename="laboutik-paiement")
router.register(r"commande", CommandeViewSet, basename="laboutik-commande")

# Panel contextuel article — hors router DRF (URLs manuelles)
# / Article context panel — outside DRF router (manual URLs)
_panel = ArticlePanelViewSet.as_view({"get": "panel"})
_stock_detail = ArticlePanelViewSet.as_view({"get": "stock_detail"})
_stock_action = ArticlePanelViewSet.as_view({"post": "stock_action"})
_toggle_bloquant = ArticlePanelViewSet.as_view({"post": "toggle_bloquant"})

urlpatterns = [
    path(
        "article-panel/<uuid:product_uuid>/panel/",
        _panel,
        name="article-panel",
    ),
    path(
        "article-panel/<uuid:product_uuid>/stock/",
        _stock_detail,
        name="article-panel-stock",
    ),
    path(
        "article-panel/<uuid:product_uuid>/stock/toggle-bloquant/",
        _toggle_bloquant,
        name="article-panel-stock-toggle-bloquant",
    ),
    path(
        "article-panel/<uuid:product_uuid>/stock/<str:action>/",
        _stock_action,
        name="article-panel-stock-action",
    ),
] + router.urls
