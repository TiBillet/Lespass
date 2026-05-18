"""
URLs de l'app PaiementStripe.
/ URLs for the PaiementStripe app.

LOCALISATION: PaiementStripe/urls.py

Routes :
  - `/stripe/onboard/from_config/` -> initie l'onboarding Stripe Connect
    pour un tenant existant (depuis l'admin Unfold).
  - `/stripe/onboard/return_from_config/<id_acc_connect>/` -> retour
    Stripe apres saisie KYC.

Historique : ces 2 routes vivaient initialement sous
`/tenant/onboard_stripe_*` (BaseBillet.views.Tenant) — flow legacy
melange avec la creation de tenant. Migrees ici le 2026-05-16
pour separer les responsabilites (cf.
`TECH_DOC/SESSIONS/MOYENS_PAIEMENT/01-stripe-migration-spec.md`).

/ Routes for Stripe Connect onboarding of an EXISTING tenant (from the
Unfold admin). Migrated from `BaseBillet.views.Tenant` on 2026-05-16.
"""

from django.urls import path

from PaiementStripe.views import StripeConnectOnboardingViewSet

stripe_onboard_from_config = StripeConnectOnboardingViewSet.as_view({
    "get": "onboard_from_config",
})
stripe_onboard_return_from_config = StripeConnectOnboardingViewSet.as_view({
    "get": "onboard_return_from_config",
})


urlpatterns = [
    path(
        "onboard/from_config/",
        stripe_onboard_from_config,
        name="stripe-onboard-from-config",
    ),
    path(
        "onboard/return_from_config/<str:id_acc_connect>/",
        stripe_onboard_return_from_config,
        name="stripe-onboard-return-from-config",
    ),
]
