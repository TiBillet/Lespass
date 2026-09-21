"""
Fabriques de ventes de billets pour les tests : avec ou sans panier, en ligne ou en admin.
/ Ticket sale factories for tests: with or without cart, online or admin.

LOCALISATION : tests/pytest/fabriques_reservation.py

Ce module n'est pas un fichier de tests (pas de préfixe test_) : pytest ne le collecte pas.
Les fichiers de tests l'importent : `from fabriques_reservation import ...`.
/ Not a test file (no test_ prefix): pytest does not collect it. Test files import it.

Deux façons de vendre en ligne :
- SANS panier : réservation directe par l'API v2 — le paiement pointe vers la réservation ;
- AVEC panier : PanierSession + CommandeService.materialiser() — le paiement est porté par
  la Commande (paiement.reservation reste vide).
/ Two ways to sell online: WITHOUT cart (API v2) and WITH cart (materialiser()).

Le paiement est simulé par défaut. Avec `compte_stripe_reel`, un VRAI paiement est fait chez
Stripe en mode test (voir tests/stripe_reel.py et tests/PIEGES.md, piège 12.18).
/ Payment is simulated by default. With `compte_stripe_reel`, a REAL test-mode payment is made.

Utilisé par / Used by : tests/pytest/test_stripe_refund.py, tests/pytest/test_stripe_reel_remboursement.py
"""

import json
import random
import string
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


def identifiant_aleatoire():
    """8 caractères pour rendre uniques les noms et les emails de test.
    / 8 characters to make test names and emails unique."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def creer_evenement_et_produit(
    api_client, auth_headers, rid, price_amount="10.00", category="Ticket booking"
):
    """Crée un événement + un produit billetterie via l'API v2.
    / Creates an event + a ticketing product via API v2.

    `category` : « Ticket booking » passe par un paiement Stripe, même à 0 €.
    Une vraie réservation gratuite exige « Free booking » (tests/PIEGES.md, piège 12.16).
    / "Ticket booking" goes through a Stripe payment, even at 0 €. A real free
    reservation needs "Free booking".

    Retourne (event_uuid, price_uuid).
    """
    start_date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    resp_event = api_client.post(
        "/api/v2/events/",
        data=json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "Event",
                "name": f"Refund Event {rid}",
                "startDate": start_date,
            }
        ),
        content_type="application/json",
        **auth_headers,
    )
    assert resp_event.status_code in (200, 201), (
        f"Création événement échouée ({resp_event.status_code}): {resp_event.content[:300]}"
    )
    event_uuid = resp_event.json()["identifier"]

    resp_product = api_client.post(
        "/api/v2/products/",
        data=json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": f"Billets Refund {rid}",
                "description": "Test remboursement Stripe",
                "category": category,
                "isRelatedTo": {"@type": "Event", "identifier": event_uuid},
                "offers": [
                    {
                        "@type": "Offer",
                        "name": "Plein tarif",
                        "price": price_amount,
                        "priceCurrency": "EUR",
                    }
                ],
            }
        ),
        content_type="application/json",
        **auth_headers,
    )
    assert resp_product.status_code in (200, 201), (
        f"Création produit échouée ({resp_product.status_code}): {resp_product.content[:300]}"
    )
    price_uuid = resp_product.json()["offers"][0]["identifier"]
    return event_uuid, price_uuid


def creer_reservation_api(
    api_client, auth_headers, event_uuid, price_uuid, email, qty=1
):
    """Crée une réservation via l'API v2 (parcours SANS panier).
    / Creates a reservation via API v2 (WITHOUT cart).
    """
    return api_client.post(
        "/api/v2/reservations/",
        data=json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "Reservation",
                "reservationFor": {"@type": "Event", "identifier": event_uuid},
                "underName": {"@type": "Person", "email": email},
                "reservedTicket": [
                    {
                        "@type": "Ticket",
                        "identifier": price_uuid,
                        "ticketQuantity": qty,
                    }
                ],
            }
        ),
        content_type="application/json",
        **auth_headers,
    )


def materialiser_panier(email, event_uuid, price_uuid, qty):
    """Passe par le vrai panier, comme la vue PanierMVT.checkout. Dans un tenant_context.
    / Goes through the real cart, like the PanierMVT.checkout view. Inside a tenant_context.

    Retourne la réservation créée (reservation.commande renseignée).
    / Returns the created reservation (reservation.commande is set).
    """
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory
    from AuthBillet.utils import get_or_create_user
    from BaseBillet.services_commande import CommandeService
    from BaseBillet.services_panier import PanierSession

    acheteur = get_or_create_user(email, send_mail=False)

    # Requête minimale avec session et user (tests/PIEGES.md, piège 10.2).
    # / Minimal request with session and user.
    request = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(request)
    request.user = acheteur

    panier = PanierSession(request)
    panier.add_ticket(event_uuid, price_uuid, qty)
    commande, succes = CommandeService.materialiser(
        panier,
        acheteur,
        first_name="Test",
        last_name="Panier",
        email=email,
    )
    assert succes, f"Matérialisation du panier échouée : {commande}"
    return commande.reservations.get()


def simuler_paiement_valide(reservation, paiement, payment_intent_id):
    """Met la réservation dans l'état « payée », sans passer par la session Checkout.
    / Puts the reservation in the "paid" state, without going through the Checkout session.

    Les .update() court-circuitent les signaux : on active donc les billets à la main,
    comme le fait le signal reservation_paid (tests/PIEGES.md, piège 12.17).
    / .update() bypasses signals: tickets are activated by hand, as reservation_paid does.

    La réservation passe VALID (payée, mail envoyé), comme en production : les
    transitions de la machine à états sont alors celles de la vraie vie.
    / The reservation goes VALID (paid, mail sent), as in production.
    """
    from BaseBillet.models import Paiement_stripe, LigneArticle, Reservation, Ticket

    Paiement_stripe.objects.filter(pk=paiement.pk).update(
        status=Paiement_stripe.VALID,
        payment_intent_id=payment_intent_id,
    )
    LigneArticle.objects.filter(paiement_stripe=paiement).update(
        status=LigneArticle.VALID,
    )
    reservation.tickets.update(status=Ticket.NOT_SCANNED)
    Reservation.objects.filter(pk=reservation.pk).update(status=Reservation.VALID)
    reservation.refresh_from_db()
    paiement.refresh_from_db()


def reservation_payee(
    parcours,
    api_client,
    auth_headers,
    tenant,
    mock_stripe,
    event_uuid,
    price_uuid,
    qty,
    compte_stripe_reel=None,
):
    """Crée une réservation payée, avec ou sans panier.
    / Creates a paid reservation, with or without cart.

    `parcours` : "sans_panier" ou "avec_panier".

    Sans `compte_stripe_reel`, le paiement est simulé (identifiant Stripe fictif).
    Avec, un VRAI paiement du montant de la réservation est fait chez Stripe, en mode test.
    Dans les deux cas, la session Checkout reste simulée (on ne peut pas la payer sans
    navigateur, piège 12.15) : elle renvoie le payment_intent, comme une session payée.
    / Without `compte_stripe_reel`, payment is simulated. With it, a REAL test-mode payment
    of the reservation amount is made at Stripe. The Checkout session stays simulated.

    Retourne (reservation, paiement, prix_un_billet) — prix en centimes.
    Le payment_intent est dans paiement.payment_intent_id.
    / Returns (reservation, paiement, prix_un_billet) — price in cents.
    """
    from django_tenants.utils import tenant_context
    from BaseBillet.models import LigneArticle, Reservation
    from tests.stripe_reel import payer_avec_la_carte_de_test

    rid = identifiant_aleatoire()
    email = f"test+refund{rid}@mock.test"

    if parcours == "sans_panier":
        resp = creer_reservation_api(
            api_client, auth_headers, event_uuid, price_uuid, email, qty=qty
        )
        assert resp.status_code in (200, 201), (
            f"Réservation échouée ({resp.status_code}): {resp.content[:300]}"
        )
        with tenant_context(tenant):
            reservation = (
                Reservation.objects.filter(
                    user_commande__email=email,
                )
                .order_by("-datetime")
                .first()
            )
            assert reservation.commande is None, (
                "Le parcours SANS panier ne crée pas de Commande."
            )
            paiement = reservation.paiements.first()
    else:
        with tenant_context(tenant):
            reservation = materialiser_panier(email, event_uuid, price_uuid, qty)
            assert reservation.paiements.count() == 0, (
                "Le paiement du panier est porté par la Commande."
            )
            paiement = reservation.commande.paiement_stripe

    # Garde vitale : filter(paiement_stripe=None).delete() viderait la compta du tenant.
    # / Vital guard: filter(paiement_stripe=None).delete() would wipe the tenant's accounting.
    assert paiement is not None, "Paiement_stripe introuvable"

    with tenant_context(tenant):
        lignes_du_paiement = LigneArticle.objects.filter(paiement_stripe=paiement)
        montant_de_la_reservation = 0
        for ligne in lignes_du_paiement:
            montant_de_la_reservation += int(ligne.amount * ligne.qty)
        prix_un_billet = lignes_du_paiement.get().amount

        if compte_stripe_reel:
            paiement_chez_stripe = payer_avec_la_carte_de_test(
                montant_de_la_reservation,
                compte_stripe_reel,
                description=f"Lespass test {rid}",
            )
            payment_intent_id = paiement_chez_stripe.id
        else:
            payment_intent_id = f"pi_{rid}"

        simuler_paiement_valide(reservation, paiement, payment_intent_id)

    mock_stripe.session.payment_intent = payment_intent_id
    return reservation, paiement, prix_un_billet


def nettoyer_paiement(tenant, paiement):
    """Retire les lignes comptables d'un paiement (vente + remboursements) : la base
    de dev est partagée et sans rollback.
    / Removes a payment's accounting lines (sale + refunds): the dev DB is shared, no rollback.
    """
    from django_tenants.utils import tenant_context
    from BaseBillet.models import LigneArticle

    with tenant_context(tenant):
        LigneArticle.objects.filter(paiement_stripe=paiement).delete()


def vente_admin_especes(tenant, event_uuid, price_uuid, qty, offert=False):
    """Crée une réservation par le vrai formulaire admin, payée en espèces (ou offerte).
    / Creates a reservation through the real admin form, paid in cash (or offered).

    Un tarif gratuit n'accepte que le moyen de paiement « Offert » (validation du formulaire).
    / A free price only accepts the "Offered" payment method (form validation).

    Retourne (reservation, ligne) : la ligne de vente hors Stripe de la réservation.
    / Returns (reservation, ligne): the reservation's non-Stripe sale line.
    """
    from django_tenants.utils import tenant_context
    from Administration.admin_tenant import ReservationAddAdmin
    from BaseBillet.models import LigneArticle, PaymentMethod

    if offert:
        moyen_de_paiement = PaymentMethod.FREE
    else:
        moyen_de_paiement = PaymentMethod.CASH

    form_data = {
        "email": f"test+admin{identifiant_aleatoire()}@mock.test",
        "price": f"{event_uuid}:{price_uuid}",
        "payment_method": moyen_de_paiement,
        "quantity": qty,
    }

    with tenant_context(tenant):
        form = ReservationAddAdmin(data=form_data)
        with (
            patch("Administration.admin_tenant.send_sale_to_laboutik.delay"),
            patch("Administration.admin_tenant.ticket_celery_mailer.delay"),
        ):
            assert form.is_valid(), form.errors
            reservation = form.save()
        ligne = LigneArticle.objects.get(reservation=reservation)
    return reservation, ligne


def nettoyer_vente_admin(tenant, ligne):
    """Retire une ligne admin et ses avoirs (d'abord les avoirs : credit_note_for est en PROTECT).
    / Removes an admin line and its credit notes (credit notes first: PROTECT FK).
    """
    from django_tenants.utils import tenant_context
    from BaseBillet.models import LigneArticle

    with tenant_context(tenant):
        LigneArticle.objects.filter(credit_note_for=ligne).delete()
        LigneArticle.objects.filter(pk=ligne.pk).delete()
