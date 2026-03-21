"""
tests/pytest/test_reservation_limits.py — Limites de réservation : stock, max/user, adhésion.
tests/pytest/test_reservation_limits.py — Reservation limits: stock, max/user, membership.

Source PW TS : 19

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_reservation_limits.py -v
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
    Event, Product, Price, Reservation, Ticket, PriceSold, ProductSold,
)
from Customers.models import Client


class TestReservationLimits:
    """Limites d'affichage sur la page événement (stock, max/user, adhésion).
    / Event page display limits (stock, max/user, membership)."""

    def test_stock_epuise_affiche_message(self, api_client, admin_user, tenant):
        """19a — Stock épuisé → message 'no longer available' sur la page event.
        / Stock exhausted → 'no longer available' message on event page."""
        uid = uuid.uuid4().hex[:8]

        with tenant_context(tenant):
            # Créer un événement avec un produit à stock=1
            # / Create event with a product at stock=1
            event = Event.objects.create(
                name=f'StockTest {uid}',
                datetime=timezone.now() + timedelta(days=30),
                jauge_max=100,
                published=True,
            )
            product = Product.objects.create(
                name=f'Billet Stock {uid}',
                categorie_article=Product.FREERES,
                publish=True,
            )
            event.products.add(product)
            price = Price.objects.create(
                product=product,
                name=f'Tarif Stock {uid}',
                prix=Decimal('0.00'),
                stock=1,
                publish=True,
            )

            # Créer 1 réservation qui épuise le stock
            # / Create 1 reservation that exhausts the stock
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
            Ticket.objects.create(
                reservation=resa,
                pricesold=price_sold,
                status=Ticket.NOT_SCANNED,
            )

            # Vérifier que le stock est épuisé via le modèle
            # / Verify stock is exhausted via model
            assert price.out_of_stock(event=event), "Le stock devrait être épuisé"

            # GET page événement → contient le message de stock épuisé
            # / GET event page → contains out of stock message
            slug = event.slug
            resp = api_client.get(f'/event/{slug}/')
            assert resp.status_code == 200
            content = resp.content.decode()
            assert 'no longer available' in content.lower() or 'plus disponible' in content.lower(), (
                "La page devrait afficher un message de stock épuisé"
            )

    def test_max_par_utilisateur_affiche_message(self, api_client, admin_user, admin_client, tenant):
        """19b — Max par utilisateur atteint → message 'maximum' sur la page event.
        / Max per user reached → 'maximum' message on event page."""
        uid = uuid.uuid4().hex[:8]

        with tenant_context(tenant):
            event = Event.objects.create(
                name=f'MaxUserTest {uid}',
                datetime=timezone.now() + timedelta(days=30),
                jauge_max=100,
                published=True,
            )
            product = Product.objects.create(
                name=f'Billet MaxUser {uid}',
                categorie_article=Product.FREERES,
                publish=True,
            )
            event.products.add(product)
            price = Price.objects.create(
                product=product,
                name=f'Tarif MaxUser {uid}',
                prix=Decimal('0.00'),
                max_per_user=1,
                publish=True,
            )

            # Créer 1 ticket pour atteindre le max
            # / Create 1 ticket to reach the max
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
            Ticket.objects.create(
                reservation=resa,
                pricesold=price_sold,
                status=Ticket.NOT_SCANNED,
            )

            # Vérifier le max_per_user côté modèle
            # / Verify max_per_user via model
            assert price.max_per_user_reached(user=admin_user, event=event), (
                "Le max par utilisateur devrait être atteint"
            )

            # GET page event avec l'admin connecté → message max
            # / GET event page with admin logged in → max message
            slug = event.slug
            resp = admin_client.get(f'/event/{slug}/')
            assert resp.status_code == 200
            content = resp.content.decode()
            assert 'maximum' in content.lower(), (
                "La page devrait afficher un message de max par utilisateur"
            )

    def test_adhesion_requise_affiche_message(self, api_client, admin_user, admin_client, tenant):
        """19c — Adhésion requise sans adhésion → message + lien /memberships/.
        / Required membership without subscription → message + /memberships/ link."""
        uid = uuid.uuid4().hex[:8]

        with tenant_context(tenant):
            # Créer un produit d'adhésion
            # / Create a membership product
            membership_product = Product.objects.create(
                name=f'Adhésion Requise {uid}',
                categorie_article=Product.ADHESION,
                publish=True,
            )
            Price.objects.create(
                product=membership_product,
                name=f'Tarif Adhésion {uid}',
                prix=Decimal('10.00'),
                subscription_type='Y',
                publish=True,
            )

            # Créer un événement avec un produit qui exige l'adhésion
            # / Create event with product requiring membership
            event = Event.objects.create(
                name=f'AdhReqTest {uid}',
                datetime=timezone.now() + timedelta(days=30),
                jauge_max=100,
                published=True,
            )
            product = Product.objects.create(
                name=f'Billet AdhReq {uid}',
                categorie_article=Product.FREERES,
                publish=True,
            )
            event.products.add(product)
            price = Price.objects.create(
                product=product,
                name=f'Tarif AdhReq {uid}',
                prix=Decimal('0.00'),
                publish=True,
            )
            price.adhesions_obligatoires.set([membership_product])

            # GET page event avec admin_client (connecté mais sans adhésion)
            # / GET event page with admin_client (logged in but no membership)
            slug = event.slug
            resp = admin_client.get(f'/event/{slug}/')
            assert resp.status_code == 200
            content = resp.content.decode()

            # Le template affiche "You must have" + nom adhésion + lien /memberships/
            # / Template displays "You must have" + membership name + /memberships/ link
            assert '/memberships/' in content, (
                "La page devrait contenir un lien vers /memberships/"
            )
            assert membership_product.name in content, (
                "La page devrait afficher le nom de l'adhésion requise"
            )
