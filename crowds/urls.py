# crowd/urls.py
from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import InitiativeViewSet, GlobalFundingViewset, contribution_stripe_return

router = DefaultRouter()
router.register(r"", InitiativeViewSet, basename="crowds")
router.register(r"global-funding", GlobalFundingViewset, basename="crowds-global-funding")

urlpatterns = [
    # FR: Retour Stripe après paiement d'une contribution.
    #     L'URL contient l'UUID du paiement Stripe car CreationPaiementStripe l'insère automatiquement.
    #     Format : /crowd/<initiative>/<contributions>/<contribution>/<paiement_stripe>/stripe-return/
    # EN: Stripe return after contribution payment.
    #     URL contains Stripe payment UUID because CreationPaiementStripe inserts it automatically.
    path(
        "<uuid:initiative_uuid>/contributions/<uuid:contribution_uuid>/<uuid:paiement_uuid>/stripe-return/",
        contribution_stripe_return,
        name="contribution-stripe-return",
    ),
] + router.urls
