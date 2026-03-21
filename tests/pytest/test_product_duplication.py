"""
tests/pytest/test_product_duplication.py — Duplication de produit admin.
tests/pytest/test_product_duplication.py — Admin product duplication.

Source PW TS : 25

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_product_duplication.py -v
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
from django_tenants.utils import schema_context

from BaseBillet.models import Product, Price, ProductFormField

TENANT_SCHEMA = 'lespass'


class TestProductDuplication:
    """Duplication de produit via l'action admin.
    / Product duplication via admin action."""

    def test_duplication_cree_copie_independante(self, admin_client):
        """25 — Dupliquer un produit → copie avec [DUPLICATA], tarifs et form fields copiés.
        / Duplicate product → copy with [DUPLICATA], prices and form fields copied."""
        uid = uuid.uuid4().hex[:8]

        with schema_context(TENANT_SCHEMA):
            # Créer un produit avec 3 tarifs + 1 champ formulaire
            # / Create product with 3 prices + 1 form field
            product = Product.objects.create(
                name=f'ProdDup {uid}',
                categorie_article=Product.FREERES,
                publish=True,
            )
            price_names = []
            for i in range(3):
                pname = f'Tarif {i} {uid}'
                price_names.append(pname)
                Price.objects.create(
                    product=product,
                    name=pname,
                    prix=Decimal(f'{(i + 1) * 5}.00'),
                    publish=True,
                )

            ProductFormField.objects.create(
                product=product,
                label=f'Question {uid}',
                field_type=ProductFormField.FieldType.SHORT_TEXT,
            )

            original_pk = product.pk
            original_price_count = product.prices.count()
            original_field_count = product.form_fields.count()

            # Le produit a au moins 3 tarifs (peut en avoir plus si un signal en crée)
            # / Product has at least 3 prices (may have more if signal creates one)
            assert original_price_count >= 3, (
                f"Le produit devrait avoir au moins 3 tarifs, trouvé {original_price_count}"
            )
            assert original_field_count == 1

            # Appel de l'action admin de duplication
            # / Call admin duplication action
            resp = admin_client.get(
                f'/admin/BaseBillet/product/{original_pk}/duplicate_product/',
                HTTP_REFERER='/admin/BaseBillet/product/',
            )
            # Redirige vers la liste des produits
            # / Redirects to product list
            assert resp.status_code in (301, 302), f"Status inattendu : {resp.status_code}"

            # Vérifier que le duplicata existe
            # / Verify the duplicate exists
            expected_name = f'ProdDup {uid} [DUPLICATA]'
            duplicata = Product.objects.filter(name=expected_name).first()
            assert duplicata is not None, f"Le produit '{expected_name}' devrait exister"

            # Le duplicata a un PK différent
            # / Duplicate has a different PK
            assert duplicata.pk != original_pk

            # Non publié par défaut / Not published by default
            assert duplicata.publish is False

            # Les tarifs créés manuellement sont copiés
            # (un signal peut ajouter des tarifs auto — on vérifie seulement nos 3)
            # / Manually created prices are copied
            # (a signal may add auto prices — we only verify our 3)
            dup_prices = list(duplicata.prices.values_list('name', flat=True))
            assert len(dup_prices) >= 3, f"Le duplicata devrait avoir au moins 3 tarifs, trouvé {len(dup_prices)}"
            for pname in price_names:
                assert pname in dup_prices, f"Le tarif '{pname}' devrait être copié"

            # Champs formulaire copiés / Form fields copied
            dup_fields = duplicata.form_fields.count()
            assert dup_fields == 1, f"Le duplicata devrait avoir 1 champ formulaire, trouvé {dup_fields}"

            # Indépendance : modifier le duplicata ne change pas l'original
            # / Independence: modifying duplicate doesn't change original
            duplicata.name = f'ProdDup Modifié {uid}'
            duplicata.save()
            original = Product.objects.get(pk=original_pk)
            assert original.name == f'ProdDup {uid}', "L'original ne devrait pas être modifié"

            # Les tarifs sont indépendants (PKs différents)
            # / Prices are independent (different PKs)
            original_price_pks = set(product.prices.values_list('pk', flat=True))
            dup_price_pks = set(duplicata.prices.values_list('pk', flat=True))
            assert original_price_pks.isdisjoint(dup_price_pks), (
                "Les PKs des tarifs doivent être différents (copies indépendantes)"
            )
