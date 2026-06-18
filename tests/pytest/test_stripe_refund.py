"""
Tests pytest : remboursement Stripe d'une réservation payée (mock).
/ Pytest tests: Stripe refund of a paid reservation (mocked).

Couvre le chemin Reservation.cancel_and_refund_resa() qui n'était testé nulle
part : appel réel de stripe.Refund.create, passage du paiement en REFUNDED,
création d'une ligne d'avoir négative REFUNDED, annulation de la réservation et
des billets.
/ Covers Reservation.cancel_and_refund_resa(), previously untested: real
stripe.Refund.create call, payment moved to REFUNDED, negative REFUNDED credit
line created, reservation and tickets cancelled.

Stripe est mocké : Session.retrieve via la fixture mock_stripe, Refund.create
patché dans le test.
/ Stripe is mocked: Session.retrieve via the mock_stripe fixture, Refund.create
patched in the test.
"""

import json
import random
import string
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _create_event_and_paid_product(api_client, auth_headers, rid, price_amount="10.00"):
    """Crée un événement + un produit billetterie payant via l'API v2.
    / Creates an event + a paid ticketing product via API v2.

    Retourne (event_uuid, price_uuid).
    """
    start_date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    resp_event = api_client.post(
        "/api/v2/events/",
        data=json.dumps({
            "@context": "https://schema.org",
            "@type": "Event",
            "name": f"Refund Event {rid}",
            "startDate": start_date,
        }),
        content_type="application/json",
        **auth_headers,
    )
    assert resp_event.status_code in (200, 201), (
        f"Création événement échouée ({resp_event.status_code}): {resp_event.content[:300]}"
    )
    event_uuid = resp_event.json()["identifier"]

    resp_product = api_client.post(
        "/api/v2/products/",
        data=json.dumps({
            "@context": "https://schema.org",
            "@type": "Product",
            "name": f"Billets Refund {rid}",
            "description": "Test remboursement Stripe",
            "category": "Ticket booking",
            "isRelatedTo": {"@type": "Event", "identifier": event_uuid},
            "offers": [{
                "@type": "Offer",
                "name": "Plein tarif",
                "price": price_amount,
                "priceCurrency": "EUR",
            }],
        }),
        content_type="application/json",
        **auth_headers,
    )
    assert resp_product.status_code in (200, 201), (
        f"Création produit échouée ({resp_product.status_code}): {resp_product.content[:300]}"
    )
    price_uuid = resp_product.json()["offers"][0]["identifier"]
    return event_uuid, price_uuid


def _create_reservation(api_client, auth_headers, event_uuid, price_uuid, email, qty=1):
    """Crée une réservation payante via l'API v2.
    / Creates a paid reservation via API v2.
    """
    return api_client.post(
        "/api/v2/reservations/",
        data=json.dumps({
            "@context": "https://schema.org",
            "@type": "Reservation",
            "reservationFor": {"@type": "Event", "identifier": event_uuid},
            "underName": {"@type": "Person", "email": email},
            "reservedTicket": [{
                "@type": "Ticket",
                "identifier": price_uuid,
                "ticketQuantity": qty,
            }],
        }),
        content_type="application/json",
        **auth_headers,
    )


class TestStripeRefund:
    """Remboursement Stripe d'une réservation payée / Stripe refund of a paid reservation."""

    def test_cancel_and_refund_paid_reservation_calls_stripe_refund(
        self, api_client, auth_headers, mock_stripe, tenant
    ):
        """Annuler une réservation payée déclenche un vrai remboursement Stripe.
        / Cancelling a paid reservation triggers a real Stripe refund.

        Flux :
        1. Créer un événement + produit payant + réservation (Stripe mocké).
        2. Forcer l'état "payé" : paiement VALID, lignes VALID.
        3. Appeler cancel_and_refund_resa() avec Refund.create patché.
        4. Vérifier : Refund.create appelé (bon montant/payment_intent), paiement
           REFUNDED, ligne d'avoir négative REFUNDED, réservation + billets annulés.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import (
            Reservation, Paiement_stripe, LigneArticle, Ticket,
        )

        rid = _random_id()
        email = f"test+refund{rid}@mock.test"

        # 1. Événement + produit payant + réservation
        # / Event + paid product + reservation
        event_uuid, price_uuid = _create_event_and_paid_product(api_client, auth_headers, rid)
        resp = _create_reservation(api_client, auth_headers, event_uuid, price_uuid, email)
        assert resp.status_code in (200, 201), (
            f"Réservation échouée ({resp.status_code}): {resp.content[:300]}"
        )
        assert mock_stripe.mock_create.called, "Stripe Session.create devrait être appelé"

        with tenant_context(tenant):
            reservation = Reservation.objects.filter(
                user_commande__email=email,
            ).order_by("-datetime").first()
            assert reservation is not None, f"Réservation introuvable pour {email}"

            paiement = reservation.paiements.first()
            assert paiement is not None, "Paiement_stripe introuvable"

            # 2. Forcer l'état "payé" via .update() (pas de signal parasite) :
            #    paiement VALID + lignes VALID. Les billets sont CREATED (non scannés).
            # / Force the "paid" state via .update(): payment VALID + lines VALID.
            Paiement_stripe.objects.filter(pk=paiement.pk).update(
                status=Paiement_stripe.VALID,
                payment_intent_id="pi_refund_mock",
            )
            LigneArticle.objects.filter(paiement_stripe=paiement).update(
                status=LigneArticle.VALID,
            )

            # Montant de CETTE réservation = somme de ses lignes payées.
            # Aujourd'hui un paiement = une seule réservation, donc ce montant
            # coïncide avec l'amount_total du checkout.
            # ⚠️ PANIER (à venir) : cancel_and_refund_resa rembourse amount_total
            # (le PAIEMENT entier), PAS ce sous-total. Le jour où un paiement
            # portera plusieurs réservations/adhésions, ce test devra diverger
            # (et le code devra rembourser le sous-total de la réservation).
            # / Amount of THIS reservation = sum of its paid lines. Today a payment
            # holds a single reservation, so it equals the checkout amount_total.
            # WARNING (baskets): cancel_and_refund_resa refunds amount_total (the
            # whole payment), not this subtotal.
            montant_reservation = sum(
                int(ligne.amount * ligne.qty)
                for ligne in LigneArticle.objects.filter(
                    paiement_stripe=paiement, status=LigneArticle.VALID,
                )
            )
            assert montant_reservation > 0, "Le montant de la réservation doit être positif."

            mock_stripe.session.payment_intent = "pi_refund_mock"
            mock_stripe.session.amount_total = montant_reservation

            lignes_avant = LigneArticle.objects.filter(paiement_stripe=paiement).count()

            # 3. Annulation + remboursement, avec Refund.create patché.
            # / Cancellation + refund, with Refund.create patched.
            with patch(
                "stripe.Refund.create",
                return_value=MagicMock(status="succeeded"),
            ) as mock_refund:
                reservation.cancel_and_refund_resa()

            # 4. Vérifications / Assertions
            assert mock_refund.called, "stripe.Refund.create n'a pas été appelé"
            kwargs = mock_refund.call_args.kwargs
            assert kwargs.get("payment_intent") == "pi_refund_mock", (
                f"payment_intent inattendu : {kwargs.get('payment_intent')}"
            )

            # Aujourd'hui amount_total == montant de la réservation (1 paiement
            # = 1 réservation). Cette assertion vérifie donc bien le montant
            # remboursé de LA RÉSERVATION (et non un montant arbitraire).
            # / Today amount_total == reservation amount: this checks the amount
            # refunded for THE RESERVATION.
            assert kwargs.get("amount") == montant_reservation, (
                f"Le montant remboursé doit être celui de la réservation "
                f"({montant_reservation}), obtenu : {kwargs.get('amount')}"
            )

            paiement.refresh_from_db()
            assert paiement.status == Paiement_stripe.REFUNDED, (
                f"Paiement attendu REFUNDED, obtenu {paiement.status}"
            )

            reservation.refresh_from_db()
            assert reservation.status == Reservation.CANCELED, (
                f"Réservation attendue CANCELED, obtenu {reservation.status}"
            )

            # Une ligne d'avoir négative en REFUNDED a été créée.
            # / A negative REFUNDED credit line was created.
            lignes_apres = LigneArticle.objects.filter(paiement_stripe=paiement)
            assert lignes_apres.count() == lignes_avant + 1, (
                "Une ligne d'avoir aurait dû être créée."
            )
            avoirs = lignes_apres.filter(status=LigneArticle.REFUNDED)
            assert avoirs.exists(), "Aucune ligne REFUNDED créée."
            assert any(ligne.qty < 0 for ligne in avoirs), (
                "La ligne d'avoir doit avoir une quantité négative."
            )

            # Tous les billets sont annulés.
            # / All tickets are cancelled.
            assert all(t.status == Ticket.CANCELED for t in reservation.tickets.all()), (
                "Tous les billets doivent être annulés."
            )

            # Nettoyage : on retire les lignes comptables créées (vente + avoir)
            # pour ne pas polluer les calculs de comptabilité (DB dev partagée,
            # pas de rollback). / Cleanup: remove created accounting lines (sale +
            # credit note) to avoid polluting accounting tests (shared dev DB).
            LigneArticle.objects.filter(paiement_stripe=paiement).delete()

    def test_free_reservation_cancel_does_not_call_stripe_refund(
        self, api_client, auth_headers, mock_stripe, tenant
    ):
        """Annuler une réservation gratuite ne déclenche aucun remboursement Stripe.
        / Cancelling a free reservation triggers no Stripe refund.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Reservation, LigneArticle

        rid = _random_id()
        email = f"test+refundfree{rid}@mock.test"

        # Produit gratuit (0 €).
        # / Free product (0 €).
        event_uuid, price_uuid = _create_event_and_paid_product(
            api_client, auth_headers, rid, price_amount="0.00",
        )
        resp = _create_reservation(api_client, auth_headers, event_uuid, price_uuid, email)
        assert resp.status_code in (200, 201)

        with tenant_context(tenant):
            reservation = Reservation.objects.filter(
                user_commande__email=email,
            ).order_by("-datetime").first()
            assert reservation is not None

            with patch("stripe.Refund.create") as mock_refund:
                reservation.cancel_and_refund_resa()

            # total_paid() == 0 → pas de remboursement Stripe.
            # / total_paid() == 0 → no Stripe refund.
            assert not mock_refund.called, (
                "Aucun remboursement Stripe ne doit être créé pour une réservation gratuite."
            )
            reservation.refresh_from_db()
            assert reservation.status == Reservation.CANCELED

            # Nettoyage des lignes (l'annulation gratuite crée un avoir
            # CREDIT_NOTE) pour ne pas polluer la comptabilité.
            # / Cleanup lines (free cancel creates a CREDIT_NOTE) to avoid
            # polluting accounting.
            LigneArticle.objects.filter(reservation=reservation).delete()

    def test_partial_refund_one_ticket_out_of_four(
        self, api_client, auth_headers, mock_stripe, tenant
    ):
        """Rembourser 1 billet sur 4 ne rembourse que le prix d'UN billet.
        / Refunding 1 of 4 tickets only refunds one ticket's price.

        Vérifie le remboursement PARTIEL (cancel_and_refund_ticket) : le montant
        remboursé est celui d'un seul billet, pas du paiement entier ; un avoir
        qty=-1 est créé ; seul le billet visé est annulé ; le paiement reste VALID.
        / Checks the PARTIAL refund: one ticket's price (not the whole payment),
        a qty=-1 credit line, only the targeted ticket cancelled, payment stays VALID.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import (
            Reservation, Paiement_stripe, LigneArticle, Ticket,
        )

        rid = _random_id()
        email = f"test+partial{rid}@mock.test"

        event_uuid, price_uuid = _create_event_and_paid_product(
            api_client, auth_headers, rid, price_amount="10.00",
        )
        resp = _create_reservation(api_client, auth_headers, event_uuid, price_uuid, email, qty=4)
        assert resp.status_code in (200, 201), (
            f"Réservation échouée ({resp.status_code}): {resp.content[:300]}"
        )

        with tenant_context(tenant):
            reservation = Reservation.objects.filter(
                user_commande__email=email,
            ).order_by("-datetime").first()
            assert reservation is not None
            assert reservation.tickets.count() == 4, (
                f"4 billets attendus, obtenu {reservation.tickets.count()}"
            )

            paiement = reservation.paiements.first()
            assert paiement is not None

            # Forcer l'état "payé".
            # / Force the "paid" state.
            Paiement_stripe.objects.filter(pk=paiement.pk).update(
                status=Paiement_stripe.VALID,
                payment_intent_id="pi_partial_mock",
            )
            LigneArticle.objects.filter(paiement_stripe=paiement).update(
                status=LigneArticle.VALID,
            )

            ligne = LigneArticle.objects.filter(
                paiement_stripe=paiement, status=LigneArticle.VALID,
            ).first()
            prix_un_billet = ligne.amount  # montant unitaire (cancel_and_refund_ticket: ligne.amount * 1)

            # amount_total = le PAIEMENT entier (4 billets) — ne doit PAS être remboursé.
            # / amount_total = the whole payment (4 tickets) — must NOT be refunded.
            mock_stripe.session.payment_intent = "pi_partial_mock"
            mock_stripe.session.amount_total = int(prix_un_billet * 4)

            ticket_a_rembourser = reservation.tickets.first()

            with patch(
                "stripe.Refund.create",
                return_value=MagicMock(status="succeeded"),
            ) as mock_refund:
                reservation.cancel_and_refund_ticket(ticket_a_rembourser)

            # Le remboursement porte sur UN billet, pas sur le paiement entier.
            # / Refund is for ONE ticket, not the whole payment.
            assert mock_refund.called, "stripe.Refund.create n'a pas été appelé"
            kwargs = mock_refund.call_args.kwargs
            assert kwargs.get("amount") == prix_un_billet, (
                f"Refund partiel attendu {prix_un_billet} (1 billet), obtenu {kwargs.get('amount')}"
            )
            assert kwargs.get("amount") != int(prix_un_billet * 4), (
                "Le remboursement ne doit pas porter sur tout le panier."
            )

            # Seul le billet visé est annulé ; les 3 autres restent.
            # / Only the targeted ticket is cancelled; the other 3 remain.
            ticket_a_rembourser.refresh_from_db()
            assert ticket_a_rembourser.status == Ticket.CANCELED
            autres = reservation.tickets.exclude(pk=ticket_a_rembourser.pk)
            assert autres.count() == 3
            assert all(t.status != Ticket.CANCELED for t in autres), (
                "Les 3 autres billets ne doivent pas être annulés."
            )

            # Un avoir d'un billet (qty=-1) est créé.
            # / A one-ticket credit line (qty=-1) is created.
            avoir = LigneArticle.objects.filter(
                paiement_stripe=paiement, status=LigneArticle.REFUNDED, qty=-1,
            )
            assert avoir.exists(), "Un avoir d'un billet (qty=-1) doit être créé."

            # Le paiement reste VALID : remboursement partiel, pas annulation totale.
            # / Payment stays VALID: partial refund, not a full cancellation.
            paiement.refresh_from_db()
            assert paiement.status == Paiement_stripe.VALID, (
                f"Le paiement ne doit PAS passer REFUNDED sur un remboursement partiel "
                f"(obtenu {paiement.status})."
            )

            # Nettoyage des lignes comptables créées (cf. test ci-dessus).
            # / Cleanup created accounting lines (see test above).
            LigneArticle.objects.filter(paiement_stripe=paiement).delete()
