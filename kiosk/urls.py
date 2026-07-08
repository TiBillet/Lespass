# kiosk/urls.py
# Routage DRF pour le parcours de recharge kiosque.
# DRF routing for the kiosk refill flow.
#
# Inclus depuis TiBillet/urls_tenants.py : path('kiosk/', include('kiosk.urls'))
# Included from TiBillet/urls_tenants.py: path('kiosk/', include('kiosk.urls'))
#
# URLs generees / Generated URLs :
#   /kiosk/                          → KioskViewSet.list (page d'accueil)
#   /kiosk/check_request_card/       → KioskViewSet.check_request_card
#   /kiosk/refill_with_wisepos/      → KioskViewSet.refill_with_wisepos
#   /kiosk/{pk}/cancel/              → KioskViewSet.cancel

from rest_framework import routers

from kiosk.views import KioskViewSet

router = routers.DefaultRouter()
router.register(r"", KioskViewSet, basename="kiosk")

urlpatterns = router.urls
