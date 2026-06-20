# inventaire/urls.py
# Routage DRF pour les endpoints de gestion de stock.
# / DRF routing for stock management endpoints.
#
# Inclus depuis TiBillet/urls_tenants.py : path('api/inventaire/', include('inventaire.urls'))
#
# URLs generees / Generated URLs :
#   /api/inventaire/stock/{pk}/reception/ → StockViewSet.reception
#   /api/inventaire/stock/{pk}/perte/     → StockViewSet.perte
#   /api/inventaire/stock/{pk}/offert/    → StockViewSet.offert
#   /api/inventaire/debit-metre/          → DebitMetreViewSet.create (POST)

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from inventaire.views import DebitMetreViewSet, StockViewSet

router = DefaultRouter()
router.register(r"stock", StockViewSet, basename="stock")
router.register(r"debit-metre", DebitMetreViewSet, basename="debit-metre")

urlpatterns = [
    path("", include(router.urls)),
]
