"""
tests/pytest/test_membership_manual_validation.py — manual_validation sur un tarif adhésion.
tests/pytest/test_membership_manual_validation.py — manual_validation on a membership price.

Source PW TS : 07-fix-solidaire-manual-validation

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_membership_manual_validation.py -v
"""
import uuid
from decimal import Decimal

import pytest


@pytest.mark.integration
def test_manual_validation_on_price():
    """07 — Créer un tarif solidaire avec manual_validation=True, full_clean() passe.
    / Create a solidarity price with manual_validation=True, full_clean() passes."""
    from django_tenants.utils import schema_context
    from BaseBillet.models import Product, Price

    uid = uuid.uuid4().hex[:8]

    with schema_context('lespass'):
        product = Product.objects.create(
            name=f'Adhésion Solidaire ManVal {uid}',
            categorie_article=Product.ADHESION,
            publish=True,
        )
        price = Price.objects.create(
            product=product,
            name=f'Solidaire ManVal {uid}',
            prix=Decimal('2.00'),
            subscription_type='Y',
            publish=True,
        )

        # Activer manual_validation et valider
        # / Enable manual_validation and validate
        price.manual_validation = True
        price.full_clean()
        price.save()

        # Recharger et vérifier
        # / Reload and verify
        price.refresh_from_db()
        assert price.manual_validation is True, (
            "manual_validation should be True after save"
        )
