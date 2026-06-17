"""
Tests pytest : lien de paiement d'adhésion à usage unique (protection SEPA).
/ Pytest tests: single-use membership payment link (SEPA duplicate protection).

Contexte métier : une adhésion à validation manuelle (caisse sociale alimentaire)
envoie un lien de paiement par email. Pour un prélèvement SEPA, le débit prend
3 à 14 jours. Sans protection, recliquer sur le lien pouvait recréer un checkout
et donc un 2e prélèvement.

Correctif testé ici :
- dès que le paiement est soumis, l'adhésion passe en statut PAYMENT_PENDING ;
- la vue get_checkout_for_membership ne recrée alors plus de checkout et affiche
  une page d'information claire (au lieu d'un 404 JSON brut).

/ Business context: a manually-validated membership emails a payment link.
For SEPA the debit takes 3-14 days. Without protection, re-clicking the link
could recreate a checkout, hence a 2nd debit. Fix: once submitted the membership
moves to PAYMENT_PENDING and the view stops creating new checkouts.

Stripe est mocké côté serveur (fixture mock_stripe) : pas d'aller-retour réseau.
/ Stripe is mocked server-side (mock_stripe fixture): no network round-trip.
"""

import json
import random
import string

import pytest


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _create_manual_membership(api_client, auth_headers, email):
    """Crée un produit adhésion à validation manuelle + une adhésion (statut AW).
    Retourne (price_uuid, email). L'adhésion est créée via l'API v2.
    / Creates a manual-validation membership product + a membership (AW status).
    """
    rid = _random_id()
    # 1. Produit adhésion annuel avec validation manuelle.
    # / Annual membership product with manual validation.
    product_payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": f"Adhesion SEPA lien {rid}",
        "description": "Test lien de paiement à usage unique",
        "category": "Membership",
        "offers": [{
            "@type": "Offer",
            "name": f"Annuel {rid}",
            "price": "20.00",
            "priceCurrency": "EUR",
            "additionalProperty": [{
                "@type": "PropertyValue",
                "name": "manualValidation",
                "value": True,
            }],
        }],
    }
    resp = api_client.post(
        "/api/v2/products/",
        data=json.dumps(product_payload),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code in (200, 201), (
        f"Création produit échouée ({resp.status_code}): {resp.content[:300]}"
    )
    price_uuid = resp.json()["offers"][0]["identifier"]

    # 2. Adhésion en attente de validation admin (statut AW).
    # / Membership awaiting admin validation (AW status).
    membership_payload = {
        "@context": "https://schema.org",
        "@type": "ProgramMembership",
        "member": {
            "@type": "Person",
            "email": email,
            "givenName": "SEPA",
            "familyName": "Lien",
        },
        "membershipPlan": {"@type": "Offer", "identifier": price_uuid},
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "paymentMode", "value": "STRIPE"},
            {"@type": "PropertyValue", "name": "status", "value": "AW"},
        ],
    }
    resp = api_client.post(
        "/api/v2/memberships/",
        data=json.dumps(membership_payload),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code in (200, 201), (
        f"Création adhésion échouée ({resp.status_code}): {resp.content[:300]}"
    )
    return price_uuid


def _force_status(tenant, email, new_status):
    """Force le statut d'une adhésion via .update() (n'enclenche aucun signal).
    Retourne l'objet Membership rafraîchi.
    / Forces a membership status via .update() (triggers no signal).
    """
    from django_tenants.utils import tenant_context
    from BaseBillet.models import Membership

    with tenant_context(tenant):
        membership = Membership.objects.filter(
            user__email=email,
        ).order_by("-date_added").first()
        assert membership is not None, f"Adhésion introuvable pour {email}"
        # .update() évite le post_save (pas de LigneArticle auto sur statut ONCE).
        # / .update() avoids post_save (no auto LigneArticle on ONCE status).
        Membership.objects.filter(pk=membership.pk).update(status=new_status)
        membership.refresh_from_db()
        return membership


class TestMembershipSepaPaymentLink:
    """Lien de paiement d'adhésion à usage unique / Single-use payment link."""

    def test_payment_pending_membership_shows_pending_page_without_new_checkout(
        self, api_client, auth_headers, mock_stripe, tenant
    ):
        """Adhésion en PAYMENT_PENDING : la vue affiche la page "paiement en
        cours" et NE crée PAS de nouveau checkout (anti double prélèvement).
        / PAYMENT_PENDING membership: view shows the "pending" page and does NOT
        create a new checkout.
        """
        from BaseBillet.models import Membership

        email = f"test+sepapp{_random_id()}@mock.test"
        _create_manual_membership(api_client, auth_headers, email)
        membership = _force_status(tenant, email, Membership.PAYMENT_PENDING)

        resp = api_client.get(
            f"/memberships/{membership.uuid}/get_checkout_for_membership/"
        )

        assert resp.status_code == 200, (
            f"Attendu 200 (page d'info), obtenu {resp.status_code}"
        )
        assert b"membership-payment-already-pending" in resp.content, (
            "La page 'paiement en cours' n'a pas été rendue."
        )
        # Aucun checkout Stripe ne doit avoir été créé.
        # / No Stripe checkout must have been created.
        assert not mock_stripe.mock_create.called, (
            "Un nouveau checkout Stripe a été créé alors que le paiement est en cours !"
        )

    def test_paid_membership_shows_already_done_page_without_new_checkout(
        self, api_client, auth_headers, mock_stripe, tenant
    ):
        """Adhésion déjà payée (ONCE) : la vue affiche "déjà active", pas de checkout.
        / Already paid (ONCE) membership: view shows "already active", no checkout.
        """
        from BaseBillet.models import Membership

        email = f"test+sepadone{_random_id()}@mock.test"
        _create_manual_membership(api_client, auth_headers, email)
        membership = _force_status(tenant, email, Membership.ONCE)

        resp = api_client.get(
            f"/memberships/{membership.uuid}/get_checkout_for_membership/"
        )

        assert resp.status_code == 200
        assert b"membership-payment-already-done" in resp.content, (
            "La page 'adhésion déjà active' n'a pas été rendue."
        )
        assert not mock_stripe.mock_create.called

    def test_admin_valid_membership_creates_checkout(
        self, api_client, auth_headers, mock_stripe, tenant
    ):
        """Adhésion ADMIN_VALID (non encore payée) : la vue crée bien un checkout
        et redirige vers Stripe (comportement nominal préservé).
        / ADMIN_VALID membership: the view creates a checkout and redirects to
        Stripe (nominal behaviour preserved).
        """
        from BaseBillet.models import Membership

        email = f"test+sepaav{_random_id()}@mock.test"
        _create_manual_membership(api_client, auth_headers, email)
        membership = _force_status(tenant, email, Membership.ADMIN_VALID)

        resp = api_client.get(
            f"/memberships/{membership.uuid}/get_checkout_for_membership/"
        )

        assert resp.status_code in (302, 303), (
            f"Attendu une redirection vers Stripe, obtenu {resp.status_code}"
        )
        assert mock_stripe.mock_create.called, (
            "Aucun checkout Stripe créé pour une adhésion validée non payée."
        )

    def test_submitted_payment_moves_membership_to_payment_pending(
        self, api_client, auth_headers, mock_stripe, tenant
    ):
        """Soumission du paiement (retour/webhook) : l'adhésion ADMIN_VALID passe
        en PAYMENT_PENDING quand le paiement reste "unpaid" (cas SEPA).
        / Payment submission (return/webhook): an ADMIN_VALID membership moves to
        PAYMENT_PENDING while the payment stays "unpaid" (SEPA case).
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Membership, Paiement_stripe
        from BaseBillet.validators import MembershipValidator

        email = f"test+sepamove{_random_id()}@mock.test"
        _create_manual_membership(api_client, auth_headers, email)
        membership = _force_status(tenant, email, Membership.ADMIN_VALID)

        with tenant_context(tenant):
            # Crée le checkout (LigneArticle + Paiement_stripe en PENDING).
            # / Create the checkout (LigneArticle + PENDING Paiement_stripe).
            MembershipValidator.get_checkout_stripe(membership)
            paiement = Paiement_stripe.objects.filter(
                checkout_session_id_stripe="cs_test_mock_session",
            ).order_by("-datetime").first()
            assert paiement is not None

            # Simule un paiement soumis mais non débité (SEPA en attente).
            # / Simulate a submitted-but-not-debited payment (SEPA pending).
            mock_stripe.session.payment_status = "unpaid"
            mock_stripe.session.expires_at = 9999999999  # session non expirée
            paiement.update_checkout_status()

            membership.refresh_from_db()
            assert membership.status == Membership.PAYMENT_PENDING, (
                f"Statut attendu PAYMENT_PENDING, obtenu {membership.status}"
            )
            # Le paiement reste en attente (pas encaissé).
            # / The payment stays pending (not captured).
            assert paiement.status == Paiement_stripe.PENDING
