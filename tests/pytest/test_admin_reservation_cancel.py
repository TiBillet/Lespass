"""
tests/pytest/test_admin_reservation_cancel.py — Annulation de réservation + avoirs.
tests/pytest/test_admin_reservation_cancel.py — Reservation cancellation + credit notes.

Source PW TS : 35

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_admin_reservation_cancel.py -v
"""

import os
import sys
import uuid
from decimal import Decimal

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

import pytest
from django.utils import timezone
from datetime import timedelta

from django_tenants.utils import tenant_context

from BaseBillet.models import (
    Event, Product, Price, Reservation, Ticket,
    PriceSold, ProductSold, LigneArticle, SaleOrigin,
)
from Customers.models import Client

TENANT_SCHEMA = 'lespass'


def _get_tenant():
    return Client.objects.get(schema_name=TENANT_SCHEMA)


def _creer_reservation_gratuite(admin_user, uid, nb_tickets=2):
    """Crée un événement + produit FREERES + réservation avec N tickets.
    / Creates event + FREERES product + reservation with N tickets."""
    event = Event.objects.create(
        name=f'CancelTest {uid}',
        datetime=timezone.now() + timedelta(days=30),
        jauge_max=100,
        published=True,
    )
    product = Product.objects.create(
        name=f'Billet Cancel {uid}',
        categorie_article=Product.FREERES,
        publish=True,
    )
    event.products.add(product)
    price = Price.objects.create(
        product=product,
        name=f'Tarif Cancel {uid}',
        prix=Decimal('0.00'),
        publish=True,
    )

    product_sold = ProductSold.objects.create(
        product=product,
    )
    price_sold = PriceSold.objects.create(
        productsold=product_sold,
        price=price,
        prix=price.prix,
    )

    resa = Reservation.objects.create(
        user_commande=admin_user,
        event=event,
        status=Reservation.VALID,
    )

    # Créer les LigneArticle pour chaque ticket (comme le ferait le flow réel)
    # / Create LigneArticle for each ticket (as real flow would)
    for _ in range(nb_tickets):
        ticket = Ticket.objects.create(
            reservation=resa,
            pricesold=price_sold,
            status=Ticket.NOT_SCANNED,
        )
        ligne = LigneArticle.objects.create(
            pricesold=price_sold,
            qty=1,
            amount=0,
            reservation=resa,
            sale_origin=SaleOrigin.ADMIN,
            status=LigneArticle.VALID,
        )

    return resa


class TestAdminReservationCancel:
    """Annulation de réservation admin + avoirs (credit notes).
    / Admin reservation cancellation + credit notes."""

    def test_annuler_reservation_cree_avoirs(self, admin_user):
        """35a — Annuler réservation → status C, tickets C, avoirs créés.
        / Cancel reservation → status C, tickets C, credit notes created."""
        uid = uuid.uuid4().hex[:8]

        with tenant_context(_get_tenant()):
            resa = _creer_reservation_gratuite(admin_user, uid, nb_tickets=2)
            resa_pk = resa.pk

            # Vérifier l'état initial
            # / Verify initial state
            assert resa.status == Reservation.VALID
            assert resa.tickets.count() == 2
            lignes_avant = LigneArticle.objects.filter(reservation=resa).count()
            assert lignes_avant == 2, f"Devrait avoir 2 lignes avant annulation, trouvé {lignes_avant}"

            # Annuler la réservation (appel direct, pas via Stripe)
            # / Cancel reservation (direct call, not via Stripe)
            result = resa.cancel_and_refund_resa()

            # Vérifier le statut réservation
            # / Verify reservation status
            resa.refresh_from_db()
            assert resa.status == Reservation.CANCELED, (
                f"Le statut devrait être CANCELED, trouvé {resa.status}"
            )

            # Tous les tickets annulés / All tickets canceled
            for ticket in resa.tickets.all():
                assert ticket.status == Ticket.CANCELED, (
                    f"Le ticket {ticket.pk} devrait être CANCELED, trouvé {ticket.status}"
                )

            # Avoirs créés (LigneArticle avec credit_note_for non null)
            # / Credit notes created (LigneArticle with credit_note_for not null)
            avoirs = LigneArticle.objects.filter(
                credit_note_for__reservation=resa,
                status=LigneArticle.CREDIT_NOTE,
            )
            assert avoirs.count() > 0, "Des avoirs devraient avoir été créés"

    def test_double_annulation_pas_de_doublon(self, admin_user):
        """35b — Annuler une réservation déjà annulée → pas de doublon d'avoirs.
        / Cancel already cancelled reservation → no duplicate credit notes."""
        uid = uuid.uuid4().hex[:8]

        with tenant_context(_get_tenant()):
            resa = _creer_reservation_gratuite(admin_user, uid, nb_tickets=1)

            # Première annulation / First cancellation
            resa.cancel_and_refund_resa()
            resa.refresh_from_db()
            assert resa.status == Reservation.CANCELED

            avoirs_count_after_first = LigneArticle.objects.filter(
                credit_note_for__reservation=resa,
                status=LigneArticle.CREDIT_NOTE,
            ).count()

            # Deuxième annulation → devrait lever une exception ou être sans effet
            # / Second cancellation → should raise exception or have no effect
            try:
                resa.cancel_and_refund_resa()
            except Exception:
                pass  # Exception attendue (tickets déjà annulés)

            # Pas de nouveaux avoirs créés / No new credit notes
            avoirs_count_after_second = LigneArticle.objects.filter(
                credit_note_for__reservation=resa,
                status=LigneArticle.CREDIT_NOTE,
            ).count()
            assert avoirs_count_after_second == avoirs_count_after_first, (
                "La double annulation ne devrait pas créer de nouveaux avoirs"
            )
