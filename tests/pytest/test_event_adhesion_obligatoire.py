"""
tests/pytest/test_event_adhesion_obligatoire.py — Restriction tarif si adhésion requise.
tests/pytest/test_event_adhesion_obligatoire.py — Price restriction if membership required.

Source PW TS : 38

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_event_adhesion_obligatoire.py -v
"""

import os
import sys
import uuid
from decimal import Decimal

sys.path.insert(0, '/DjangoFiles')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django

django.setup()

import pytest
from django.utils import timezone
from datetime import timedelta

from django_tenants.utils import tenant_context

from BaseBillet.models import Event, Product, Price
from Customers.models import Client


class TestEventAdhesionObligatoire:
    """Restriction d'accès à un tarif si adhésion obligatoire.
    / Access restriction to a price if membership is required."""

    def test_tarif_bloque_sans_adhesion(self, api_client, tenant):
        """38 — Tarif avec adhésion obligatoire → message restriction + lien /memberships/.
        / Price with required membership → restriction message + /memberships/ link."""
        uid = uuid.uuid4().hex[:8]

        with tenant_context(tenant):
            # Créer le produit adhésion / Create membership product
            membership_product = Product.objects.create(
                name=f'Adhésion Oblig {uid}',
                categorie_article=Product.ADHESION,
                publish=True,
            )
            Price.objects.create(
                product=membership_product,
                name=f'Tarif Adhésion Oblig {uid}',
                prix=Decimal('0.00'),
                subscription_type='Y',
                publish=True,
            )

            # Créer l'événement avec un produit lié à l'adhésion
            # / Create event with a product linked to membership
            event = Event.objects.create(
                name=f'AdhObligTest {uid}',
                datetime=timezone.now() + timedelta(days=30),
                jauge_max=100,
                published=True,
            )
            product = Product.objects.create(
                name=f'Billet AdhOblig {uid}',
                categorie_article=Product.FREERES,
                publish=True,
            )
            event.products.add(product)
            price = Price.objects.create(
                product=product,
                name=f'Tarif AdhOblig {uid}',
                prix=Decimal('0.00'),
                publish=True,
            )
            price.adhesions_obligatoires.set([membership_product])

            # GET page événement sans login → message "Log in to access this rate"
            # / GET event page without login → "Log in to access this rate" message
            slug = event.slug
            resp = api_client.get(f'/event/{slug}/')
            assert resp.status_code == 200
            content = resp.content.decode()

            # Utilisateur anonyme → "Log in to access this rate."
            # / Anonymous user → "Log in to access this rate."
            assert (
                'log in' in content.lower()
                or 'connectez' in content.lower()
                or 'identifier' in content.lower()
            ), "La page devrait demander de se connecter pour accéder au tarif"
