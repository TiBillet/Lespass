"""
tests/pytest/test_adhesions_obligatoires_m2m.py — M2M adhesions_obligatoires sur Price.
tests/pytest/test_adhesions_obligatoires_m2m.py — M2M adhesions_obligatoires on Price.

Source PW TS : 37

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_adhesions_obligatoires_m2m.py -v
"""
import uuid
from decimal import Decimal

import pytest


@pytest.mark.integration
def test_adhesions_obligatoires_set_and_remove():
    """37 — Gérer le M2M adhesions_obligatoires : set 2, vérifier, retirer 1, vérifier.
    / Manage adhesions_obligatoires M2M: set 2, verify, remove 1, verify."""
    from django_tenants.utils import schema_context
    from BaseBillet.models import Product, Price

    uid = uuid.uuid4().hex[:8]

    with schema_context('lespass'):
        # 2 produits adhésion / 2 membership products
        product_a = Product.objects.create(
            name=f'Adhésion A {uid}',
            categorie_article=Product.ADHESION,
            publish=True,
        )
        Price.objects.create(
            product=product_a, name=f'Tarif A {uid}',
            prix=Decimal('10.00'), subscription_type='Y', publish=True,
        )

        product_b = Product.objects.create(
            name=f'Adhésion B {uid}',
            categorie_article=Product.ADHESION,
            publish=True,
        )
        Price.objects.create(
            product=product_b, name=f'Tarif B {uid}',
            prix=Decimal('15.00'), subscription_type='Y', publish=True,
        )

        # 1 produit gratuit (réservation libre) / 1 free product (free booking)
        product_f = Product.objects.create(
            name=f'Resa Gratuite AdhTest {uid}',
            categorie_article=Product.FREERES,
            publish=True,
        )
        price_gratuit = Price.objects.create(
            product=product_f, name=f'Gratuit {uid}',
            prix=Decimal('0.00'), publish=True,
        )

        # Associer les 2 adhésions comme obligatoires
        # / Set both memberships as required
        price_gratuit.adhesions_obligatoires.set([product_a, product_b])
        price_gratuit.refresh_from_db()
        assert price_gratuit.adhesions_obligatoires.count() == 2, (
            "Should have 2 required memberships"
        )

        # Retirer 1, vérifier qu'il en reste 1
        # / Remove 1, verify 1 remains
        price_gratuit.adhesions_obligatoires.remove(product_a)
        price_gratuit.refresh_from_db()
        assert price_gratuit.adhesions_obligatoires.count() == 1, (
            "Should have 1 required membership after remove"
        )
        assert price_gratuit.adhesions_obligatoires.first() == product_b
