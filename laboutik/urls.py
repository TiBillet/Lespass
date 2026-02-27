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

from rest_framework import routers

from laboutik.views import CaisseViewSet, PaiementViewSet

router = routers.DefaultRouter()
router.register(r'caisse', CaisseViewSet, basename='laboutik-caisse')
router.register(r'paiement', PaiementViewSet, basename='laboutik-paiement')

urlpatterns = router.urls
