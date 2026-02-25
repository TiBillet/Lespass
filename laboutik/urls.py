# laboutik/urls.py — routage DRF pour la caisse LaBoutik
# parent: TiBillet/urls_tenants.py

from rest_framework import routers

from laboutik.views import CaisseViewSet, PaiementViewSet

router = routers.DefaultRouter()
router.register(r'caisse', CaisseViewSet, basename='laboutik-caisse')
router.register(r'paiement', PaiementViewSet, basename='laboutik-paiement')

urlpatterns = router.urls
