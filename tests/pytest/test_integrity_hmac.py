"""
Tests du chainage HMAC-SHA256 pour la conformite LNE (exigence 8).
/ HMAC-SHA256 chaining tests for LNE compliance (requirement 8).

LOCALISATION : tests/pytest/test_integrity_hmac.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')
django.setup()

import pytest
from django_tenants.utils import tenant_context
from Customers.models import Client


TENANT_SCHEMA = 'lespass'


def _get_tenant():
    """Recupere le tenant de test. / Gets the test tenant."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


class TestCleHMAC:
    """Tests de la cle HMAC par tenant. / HMAC key per tenant tests."""

    @pytest.mark.django_db
    def test_cle_generee_automatiquement(self):
        """
        get_or_create_hmac_key() genere une cle de 64 caracteres hex au premier appel.
        / Generates a 64-char hex key on first call.
        """
        tenant = _get_tenant()
        with tenant_context(tenant):
            from laboutik.models import LaboutikConfiguration
            config = LaboutikConfiguration.get_solo()
            config.hmac_key = None
            # Pas de update_fields sur un singleton django-solo : si le
            # singleton n'existe pas encore (count=0), get_solo() retourne
            # un objet en memoire et save(update_fields=[...]) leve
            # DatabaseError "Save with update_fields did not affect any rows".
            # Cf. tests/PIEGES.md piege 9.86.
            # / No update_fields on a django-solo singleton: if the singleton
            # doesn't exist yet, get_solo() returns an in-memory object and
            # save(update_fields=[...]) raises DatabaseError. See PIEGES.md 9.86.
            config.save()

            cle = config.get_or_create_hmac_key()

            assert cle is not None
            assert len(cle) == 64

    @pytest.mark.django_db
    def test_cle_stable_entre_appels(self):
        """
        Deux appels a get_or_create_hmac_key() retournent la meme cle.
        / Two calls return the same key.
        """
        tenant = _get_tenant()
        with tenant_context(tenant):
            from laboutik.models import LaboutikConfiguration
            config = LaboutikConfiguration.get_solo()
            config.hmac_key = None
            # Cf. tests/PIEGES.md piege 9.86 — pas de update_fields sur singleton.
            config.save()

            cle_1 = config.get_or_create_hmac_key()
            cle_2 = config.get_or_create_hmac_key()

            assert cle_1 == cle_2


from decimal import Decimal
from BaseBillet.models import SaleOrigin, PaymentMethod


def _creer_ligne_article_test(tenant, amount=1200, vat=Decimal('20.00'),
                               payment_method=PaymentMethod.CASH,
                               sale_origin=SaleOrigin.LABOUTIK):
    """
    Cree une LigneArticle de test avec les champs minimaux.
    / Creates a test LigneArticle with minimal fields.
    """
    with tenant_context(tenant):
        from BaseBillet.models import LigneArticle, Product, Price, PriceSold, ProductSold

        # Recuperer un produit et prix existants (crees par create_test_pos_data)
        # / Get existing product and price (created by create_test_pos_data)
        product = Product.objects.filter(
            categorie_pos__isnull=False
        ).first()
        if not product:
            pytest.skip("Pas de produit POS disponible (lancer create_test_pos_data)")

        price = Price.objects.filter(product=product).first()
        if not price:
            pytest.skip("Pas de prix disponible")

        product_sold, _ = ProductSold.objects.get_or_create(
            product=product,
            defaults={'product_name': product.name},
        )
        price_sold, _ = PriceSold.objects.get_or_create(
            productsold=product_sold,
            prix=price.prix,
            defaults={'price_name': str(price)},
        )

        ligne = LigneArticle.objects.create(
            pricesold=price_sold,
            qty=1,
            amount=amount,
            vat=vat,
            payment_method=payment_method,
            sale_origin=sale_origin,
            status=LigneArticle.VALID,
        )
        return ligne


class TestTotalHT:
    """Tests du calcul HT. / HT calculation tests."""

    def test_total_ht_tva_20(self):
        amount_ttc = 1200
        taux_tva = 20.0
        from laboutik.integrity import calculer_total_ht
        total_ht = calculer_total_ht(amount_ttc, taux_tva)
        assert total_ht == 1000

    def test_total_ht_tva_zero(self):
        from laboutik.integrity import calculer_total_ht
        total_ht = calculer_total_ht(500, 0.0)
        assert total_ht == 500

    def test_total_ht_tva_5_5(self):
        from laboutik.integrity import calculer_total_ht
        total_ht = calculer_total_ht(528, 5.5)
        assert total_ht == 500


class TestChainageHMAC:
    """Tests du chainage HMAC-SHA256. / HMAC-SHA256 chaining tests."""

    @pytest.mark.django_db
    def test_hmac_calcule_non_vide(self):
        """calculer_hmac() retourne 64 chars hex. / Returns 64-char hex."""
        tenant = _get_tenant()
        with tenant_context(tenant):
            from laboutik.integrity import calculer_hmac
            ligne = _creer_ligne_article_test(tenant)
            hmac_resultat = calculer_hmac(ligne, 'cle_secrete_test', '')
            assert len(hmac_resultat) == 64
            assert all(c in '0123456789abcdef' for c in hmac_resultat)

    @pytest.mark.django_db
    def test_hmac_chaine_3_lignes(self):
        """3 lignes chainees → verifier_chaine True. / 3 chained lines → True."""
        tenant = _get_tenant()
        with tenant_context(tenant):
            from laboutik.integrity import calculer_hmac, verifier_chaine, calculer_total_ht
            from laboutik.models import LaboutikConfiguration
            from BaseBillet.models import LigneArticle

            config = LaboutikConfiguration.get_solo()
            cle = config.get_or_create_hmac_key()

            # Utiliser un uuid_transaction unique pour isoler les lignes de ce test
            # / Use a unique uuid_transaction to isolate this test's lines
            import uuid as uuid_module
            test_uuid = uuid_module.uuid4()

            previous = ''
            for i in range(3):
                ligne = _creer_ligne_article_test(tenant, amount=1000 + i * 100)
                ligne.uuid_transaction = test_uuid
                ligne.total_ht = calculer_total_ht(ligne.amount, ligne.vat)
                ligne.previous_hmac = previous
                ligne.hmac_hash = calculer_hmac(ligne, cle, previous)
                ligne.save(update_fields=['uuid_transaction', 'total_ht', 'hmac_hash', 'previous_hmac'])
                previous = ligne.hmac_hash

            # Verifier uniquement les lignes de ce test (pas celles des autres tests)
            # / Verify only this test's lines (not from other tests)
            lignes_chainees = LigneArticle.objects.filter(
                uuid_transaction=test_uuid,
            )
            est_valide, erreurs, corrections = verifier_chaine(lignes_chainees, cle)
            assert est_valide is True
            assert len(erreurs) == 0

    @pytest.mark.django_db
    def test_hmac_detecte_modification(self):
        """Modifier amount casse la chaine. / Modifying amount breaks chain."""
        tenant = _get_tenant()
        with tenant_context(tenant):
            from laboutik.integrity import calculer_hmac, verifier_chaine, calculer_total_ht
            from laboutik.models import LaboutikConfiguration
            from BaseBillet.models import LigneArticle

            config = LaboutikConfiguration.get_solo()
            cle = config.get_or_create_hmac_key()

            # Isoler les lignes de ce test avec un uuid_transaction unique
            # / Isolate this test's lines with a unique uuid_transaction
            import uuid as uuid_module
            test_uuid = uuid_module.uuid4()

            previous = ''
            lignes = []
            for i in range(2):
                ligne = _creer_ligne_article_test(tenant, amount=1000)
                ligne.uuid_transaction = test_uuid
                ligne.total_ht = calculer_total_ht(ligne.amount, ligne.vat)
                ligne.previous_hmac = previous
                ligne.hmac_hash = calculer_hmac(ligne, cle, previous)
                ligne.save(update_fields=['uuid_transaction', 'total_ht', 'hmac_hash', 'previous_hmac'])
                previous = ligne.hmac_hash
                lignes.append(ligne)

            # Falsifier la premiere ligne (modification directe en DB)
            # / Tamper with first line (direct DB modification)
            lignes[0].amount = 9999
            lignes[0].save(update_fields=['amount'])

            # Verifier uniquement les lignes de ce test
            # / Verify only this test's lines
            lignes_chainees = LigneArticle.objects.filter(
                uuid_transaction=test_uuid,
            )
            est_valide, erreurs, corrections = verifier_chaine(lignes_chainees, cle)
            assert est_valide is False
            assert len(erreurs) >= 1
