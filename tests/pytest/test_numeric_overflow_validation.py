"""
tests/pytest/test_numeric_overflow_validation.py — Validation overflow sur Price.prix.
tests/pytest/test_numeric_overflow_validation.py — Overflow validation on Price.prix.

Verifie que les montants excessifs sont rejetes par Django (max_digits=6, decimal_places=2).
Verifies that excessive amounts are rejected by Django (max_digits=6, decimal_places=2).

Converti depuis : tests/playwright/tests/admin/28-numeric-overflow-validation.spec.ts
Converted from: tests/playwright/tests/admin/28-numeric-overflow-validation.spec.ts

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_numeric_overflow_validation.py -v
"""

import os
import sys

sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import pytest

from decimal import Decimal

from django.core.exceptions import ValidationError
from django_tenants.utils import schema_context

from BaseBillet.models import Price, Product


TENANT_SCHEMA = 'lespass'


class TestNumericOverflowValidation:
    """Tests de validation du champ Price.prix (DecimalField max_digits=6).
    / Validation tests for Price.prix field (DecimalField max_digits=6)."""

    def _build_price(self, amount):
        """Construit un objet Price non sauvegarde avec le montant donne.
        / Builds an unsaved Price object with the given amount."""
        with schema_context(TENANT_SCHEMA):
            product = Product.objects.first()
            assert product, "Au moins un Product doit exister en base"
            return Price(
                product=product,
                name="Test overflow",
                prix=Decimal(str(amount)),
            )

    def test_price_overflow_rejected(self):
        """Montant excessif (1000000.00) → ValidationError (depasse max_digits=6).
        / Excessive amount (1000000.00) → ValidationError (exceeds max_digits=6)."""
        with schema_context(TENANT_SCHEMA):
            price = self._build_price('1000000.00')
            with pytest.raises(ValidationError):
                price.full_clean()

    def test_valid_price_accepted(self):
        """Montant valide (15.00) → pas d'erreur.
        / Valid amount (15.00) → no error."""
        with schema_context(TENANT_SCHEMA):
            price = self._build_price('15.00')
            # full_clean ne doit pas lever d'exception
            # / full_clean must not raise an exception
            price.full_clean()
