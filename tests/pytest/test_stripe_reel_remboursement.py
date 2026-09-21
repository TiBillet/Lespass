"""
Tests pytest : remboursements avec un VRAI Stripe, en mode test.
/ Pytest tests: refunds with a REAL Stripe, in test mode.

LOCALISATION : tests/pytest/test_stripe_reel_remboursement.py

Ce qui passe VRAIMENT par Stripe :
- le paiement : un PaymentIntent du montant de la réservation, payé par la carte de test ;
- chaque remboursement : stripe.Refund.create n'est PAS mocké ;
- la vérification : les remboursements sont relus chez Stripe (Refund.list).
Seule la session Checkout reste simulée : on ne peut pas la payer sans navigateur
(tests/PIEGES.md, pièges 12.15 et 12.18). Elle renvoie le vrai payment_intent, comme une
session payée en production.
/ What REALLY goes through Stripe: the payment, every refund (Refund.create is NOT mocked),
and the check (refunds read back from Stripe). Only the Checkout session stays simulated.

Sur demande seulement : marqueur `stripe_reel`, lancé par `make test-stripe` (STRIPE_REEL=1).
Sans la variable, ces tests sont ignorés et nommés en rouge en fin de run.
/ On demand only: `stripe_reel` marker, run by `make test-stripe`.

Prérequis : réseau, clé racine Stripe de TEST (sk_test_…), compte Connect du lieu.
/ Requirements: network, Stripe TEST root key, the place's Connect account.

Lancer / Run :
    make test-stripe ARGS="tests/pytest/test_stripe_reel_remboursement.py -q"
"""

import pytest

from fabriques_reservation import (
    creer_evenement_et_produit,
    identifiant_aleatoire,
    nettoyer_paiement,
    reservation_payee,
)

pytestmark = pytest.mark.stripe_reel


@pytest.fixture
def compte_stripe_de_test(tenant):
    """Clé Stripe de test posée, et compte Connect du lieu. / Test key set, place's Connect account."""
    from django_tenants.utils import tenant_context
    from tests.stripe_reel import preparer_stripe_mode_test

    with tenant_context(tenant):
        return preparer_stripe_mode_test()


class TestRemboursementStripeReel:
    """Remboursements réels chez Stripe, avec et sans panier.
    / Real refunds at Stripe, with and without cart.
    """

    @pytest.mark.parametrize("parcours", ["sans_panier", "avec_panier"])
    def test_trois_billets_rembourses_un_par_un_chez_stripe(
        self,
        parcours,
        api_client,
        auth_headers,
        mock_stripe,
        tenant,
        compte_stripe_de_test,
    ):
        """3 billets à 10 € remboursés un par un : Stripe enregistre 3 remboursements de 10 €.
        / 3 tickets at 10 € refunded one by one: Stripe records 3 refunds of 10 €.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Paiement_stripe, Reservation
        from tests.stripe_reel import (
            etat_du_paiement_chez_stripe,
            montants_rembourses_chez_stripe,
        )

        event_uuid, price_uuid = creer_evenement_et_produit(
            api_client, auth_headers, identifiant_aleatoire()
        )
        reservation, paiement, prix_un_billet = reservation_payee(
            parcours,
            api_client,
            auth_headers,
            tenant,
            mock_stripe,
            event_uuid,
            price_uuid,
            qty=3,
            compte_stripe_reel=compte_stripe_de_test,
        )

        try:
            with tenant_context(tenant):
                for billet in reservation.tickets.order_by("pk"):
                    reservation.cancel_and_refund_ticket(billet)

                montants_chez_stripe = montants_rembourses_chez_stripe(
                    paiement.payment_intent_id,
                    compte_stripe_de_test,
                )
                assert montants_chez_stripe == [
                    prix_un_billet,
                    prix_un_billet,
                    prix_un_billet,
                ], (
                    f"Stripe doit avoir 3 remboursements de {prix_un_billet}, obtenu {montants_chez_stripe}"
                )

                # Le paiement lui-même, lu chez Stripe : 30 € encaissés, 30 € remboursés.
                # / The payment itself, read at Stripe: 30 € captured, 30 € refunded.
                etat_chez_stripe = etat_du_paiement_chez_stripe(
                    paiement.payment_intent_id,
                    compte_stripe_de_test,
                )
                assert etat_chez_stripe == {
                    "montant_encaisse": prix_un_billet * 3,
                    "montant_rembourse": prix_un_billet * 3,
                    "rembourse_en_totalite": True,
                }, f"Paiement inattendu chez Stripe : {etat_chez_stripe}"

                paiement.refresh_from_db()
                assert paiement.status == Paiement_stripe.REFUNDED
                reservation.refresh_from_db()
                assert reservation.status == Reservation.CANCELED
        finally:
            nettoyer_paiement(tenant, paiement)

    @pytest.mark.parametrize("parcours", ["sans_panier", "avec_panier"])
    def test_reservation_complete_remboursee_chez_stripe(
        self,
        parcours,
        api_client,
        auth_headers,
        mock_stripe,
        tenant,
        compte_stripe_de_test,
    ):
        """Réservation de 3 billets à 10 € annulée : Stripe enregistre un remboursement de 30 €.
        / 3-ticket reservation at 10 € cancelled: Stripe records one refund of 30 €.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Paiement_stripe, Reservation
        from tests.stripe_reel import (
            etat_du_paiement_chez_stripe,
            montants_rembourses_chez_stripe,
        )

        event_uuid, price_uuid = creer_evenement_et_produit(
            api_client, auth_headers, identifiant_aleatoire()
        )
        reservation, paiement, prix_un_billet = reservation_payee(
            parcours,
            api_client,
            auth_headers,
            tenant,
            mock_stripe,
            event_uuid,
            price_uuid,
            qty=3,
            compte_stripe_reel=compte_stripe_de_test,
        )

        try:
            with tenant_context(tenant):
                reservation.cancel_and_refund_resa()

                montants_chez_stripe = montants_rembourses_chez_stripe(
                    paiement.payment_intent_id,
                    compte_stripe_de_test,
                )
                assert montants_chez_stripe == [prix_un_billet * 3], (
                    f"Stripe doit avoir 1 remboursement de {prix_un_billet * 3}, obtenu {montants_chez_stripe}"
                )

                # Le paiement lui-même, lu chez Stripe : 30 € encaissés, 30 € remboursés.
                # / The payment itself, read at Stripe: 30 € captured, 30 € refunded.
                etat_chez_stripe = etat_du_paiement_chez_stripe(
                    paiement.payment_intent_id,
                    compte_stripe_de_test,
                )
                assert etat_chez_stripe == {
                    "montant_encaisse": prix_un_billet * 3,
                    "montant_rembourse": prix_un_billet * 3,
                    "rembourse_en_totalite": True,
                }, f"Paiement inattendu chez Stripe : {etat_chez_stripe}"

                paiement.refresh_from_db()
                assert paiement.status == Paiement_stripe.REFUNDED
                reservation.refresh_from_db()
                assert reservation.status == Reservation.CANCELED
        finally:
            nettoyer_paiement(tenant, paiement)
