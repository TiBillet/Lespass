from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    EventViewSet,
    PostalAddressViewSet,
    ProductViewSet,
    SaleViewSet,
    ReservationViewSet,
    MembershipViewSet,
    WalletRefillViewSet,
    CrowdInitiativeViewSet,
    PageViewSet,
    BlocViewSet,
)

router = DefaultRouter()
# basename must be 'event' to align with ExternalApiKey.api_permissions()
router.register(r"events", EventViewSet, basename="event")
# Postal address endpoints (use basename 'postaladdress' to map to ExternalApiKey.api_permissions)
router.register(r"postal-addresses", PostalAddressViewSet, basename="postaladdress")
# Product endpoints (use basename 'product' to map to ExternalApiKey.api_permissions)
router.register(r"products", ProductViewSet, basename="product")
# Route API des ventes (LigneArticle)
router.register(r'sales', SaleViewSet, basename='sale')
# Reservation endpoints (use basename 'reservation' to map to ExternalApiKey.api_permissions)
router.register(r"reservations", ReservationViewSet, basename="reservation")
# Membership endpoints (use basename 'membership' to map to ExternalApiKey.api_permissions)
router.register(r"memberships", MembershipViewSet, basename="membership")
# Wallet gift-refill endpoint (basename 'walletrefill' -> ExternalApiKey.gift_asset)
router.register(r"wallet-refills", WalletRefillViewSet, basename="walletrefill")
router.register(r"initiatives", CrowdInitiativeViewSet, basename="crowd")
# basename = cle de api_permissions() (page / bloc)
router.register(r"pages", PageViewSet, basename="page")
router.register(r"blocs", BlocViewSet, basename="bloc")
urlpatterns = [
    path("", include(router.urls)),
]
