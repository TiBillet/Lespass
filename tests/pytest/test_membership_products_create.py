"""
tests/pytest/test_membership_products_create.py — Création de produits adhésion + vérification page /memberships/.
tests/pytest/test_membership_products_create.py — Create membership products + verify on /memberships/ page.

Source PW TS : 03, 04, 05, 06, 08

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_membership_products_create.py -v
"""
import uuid
from decimal import Decimal

import pytest


@pytest.mark.integration
def test_create_adhesion_simple(admin_client):
    """03 — Adhésion simple : 1 produit + 2 tarifs (annuel 20€, mensuel 2€).
    / Simple membership: 1 product + 2 prices (annual €20, monthly €2)."""
    from django_tenants.utils import schema_context
    from BaseBillet.models import Product, Price

    uid = uuid.uuid4().hex[:8]
    product_name = f"Adhésion Simple {uid}"

    with schema_context('lespass'):
        product = Product.objects.create(
            name=product_name,
            categorie_article=Product.ADHESION,
            publish=True,
        )
        Price.objects.create(
            product=product, name=f'Annuel {uid}',
            prix=Decimal('20.00'), subscription_type='Y', publish=True,
        )
        Price.objects.create(
            product=product, name=f'Mensuel {uid}',
            prix=Decimal('2.00'), subscription_type='M', publish=True,
        )

    resp = admin_client.get('/memberships/')
    assert resp.status_code == 200, f"GET /memberships/ failed: {resp.status_code}"
    assert product_name in resp.content.decode(), (
        f"Product '{product_name}' not found on /memberships/"
    )


@pytest.mark.integration
def test_create_adhesion_recurrente(admin_client):
    """04 — Adhésion récurrente : tarif mensuel avec recurring_payment=True.
    / Recurring membership: monthly price with recurring_payment=True."""
    from django_tenants.utils import schema_context
    from BaseBillet.models import Product, Price

    uid = uuid.uuid4().hex[:8]
    product_name = f"Adhésion Récurrente {uid}"

    with schema_context('lespass'):
        product = Product.objects.create(
            name=product_name,
            categorie_article=Product.ADHESION,
            publish=True,
        )
        Price.objects.create(
            product=product, name=f'Mensuel Récurrent {uid}',
            prix=Decimal('10.00'), subscription_type='M',
            recurring_payment=True, publish=True,
        )

    resp = admin_client.get('/memberships/')
    assert resp.status_code == 200
    assert product_name in resp.content.decode()


@pytest.mark.integration
def test_create_adhesion_validation_selective(admin_client):
    """05 — Validation sélective : 2 tarifs (solidaire 2€, plein 30€).
    / Selective validation: 2 prices (solidarity €2, full €30)."""
    from django_tenants.utils import schema_context
    from BaseBillet.models import Product, Price

    uid = uuid.uuid4().hex[:8]
    product_name = f"Adhésion Validation Sélective {uid}"

    with schema_context('lespass'):
        product = Product.objects.create(
            name=product_name,
            categorie_article=Product.ADHESION,
            publish=True,
        )
        Price.objects.create(
            product=product, name=f'Solidaire {uid}',
            prix=Decimal('2.00'), subscription_type='Y', publish=True,
        )
        Price.objects.create(
            product=product, name=f'Plein tarif {uid}',
            prix=Decimal('30.00'), subscription_type='Y', publish=True,
        )

    resp = admin_client.get('/memberships/')
    assert resp.status_code == 200
    assert product_name in resp.content.decode()


@pytest.mark.integration
def test_create_panier_amap(admin_client):
    """06 — Panier AMAP : 2 tarifs (annuel 400€, mensuel 40€) + OptionGenerale.
    / AMAP basket: 2 prices (annual €400, monthly €40) + OptionGenerale."""
    from django_tenants.utils import schema_context
    from BaseBillet.models import Product, Price, OptionGenerale

    uid = uuid.uuid4().hex[:8]
    product_name = f"Panier AMAP {uid}"

    with schema_context('lespass'):
        product = Product.objects.create(
            name=product_name,
            categorie_article=Product.ADHESION,
            publish=True,
        )
        Price.objects.create(
            product=product, name=f'Annuel AMAP {uid}',
            prix=Decimal('400.00'), subscription_type='Y', publish=True,
        )
        Price.objects.create(
            product=product, name=f'Mensuel AMAP {uid}',
            prix=Decimal('40.00'), subscription_type='M', publish=True,
        )
        option = OptionGenerale.objects.create(name=f'Légumes {uid}')
        product.option_generale_checkbox.add(option)

    resp = admin_client.get('/memberships/')
    assert resp.status_code == 200
    assert product_name in resp.content.decode()


@pytest.mark.integration
def test_create_ssa_avec_formulaire(admin_client):
    """08 — SSA avec formulaire personnalisé : ProductFormField requis.
    / SSA with custom form: required ProductFormField."""
    from django_tenants.utils import schema_context
    from BaseBillet.models import Product, Price, ProductFormField

    uid = uuid.uuid4().hex[:8]
    product_name = f"SSA Formulaire {uid}"

    with schema_context('lespass'):
        product = Product.objects.create(
            name=product_name,
            categorie_article=Product.ADHESION,
            publish=True,
        )
        Price.objects.create(
            product=product, name=f'Tarif SSA {uid}',
            prix=Decimal('15.00'), subscription_type='Y', publish=True,
        )
        ProductFormField.objects.create(
            product=product,
            label='Pseudonyme',
            name=f'pseudonyme_{uid}',
            field_type='ST',
            required=True,
        )

    resp = admin_client.get('/memberships/')
    assert resp.status_code == 200
    assert product_name in resp.content.decode()
