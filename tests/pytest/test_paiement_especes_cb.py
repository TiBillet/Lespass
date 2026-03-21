"""
tests/pytest/test_paiement_especes_cb.py — Tests Phase 2 etape 2 : paiement especes/CB.
tests/pytest/test_paiement_especes_cb.py — Tests Phase 2 step 2: cash/credit card payment.

Couvre : _creer_lignes_articles, ProductSold, PriceSold, LigneArticle,
         payer() especes/CB, panier vide, NFC desactive.
Covers: _creer_lignes_articles, ProductSold, PriceSold, LigneArticle,
        payer() cash/CC, empty cart, NFC disabled.

Utilise FastTenantTestCase (django-tenants) : schema isole, rollback entre tests.
Uses FastTenantTestCase (django-tenants): isolated schema, rollback between tests.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py -v
"""

import os
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django

django.setup()

from decimal import Decimal

from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    CategorieProduct, LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod,
)
from laboutik.models import PointDeVente


class TestPaiementEspecesCB(FastTenantTestCase):
    """1 classe FastTenantTestCase = 1 schema cree en setUpClass.
    Chaque methode est isolee par rollback (TestCase._fixture_teardown).
    / 1 FastTenantTestCase class = 1 schema created in setUpClass.
    Each method is isolated by rollback (TestCase._fixture_teardown)."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_paiement'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-paiement.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = 'Test Paiement'

    def setUp(self):
        """Cree les donnees minimales pour chaque test (rollback apres chaque test).
        / Creates minimal data for each test (rolled back after each test)."""
        # Re-setter le search_path apres le rollback du test precedent.
        # / Re-set search_path after previous test's rollback.
        connection.set_tenant(self.tenant)

        # Categorie POS / POS category
        self.categorie = CategorieProduct.objects.create(
            name='Boissons Test',
        )

        # Produit POS / POS product
        self.produit = Product.objects.create(
            name='Biere Test',
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
        )

        # Prix EUR (5.50 €) / EUR price (5.50 €)
        self.prix = Price.objects.create(
            product=self.produit,
            name='Pinte',
            prix=Decimal('5.50'),
            publish=True,
        )

        # Point de vente / Point of sale
        self.pv = PointDeVente.objects.create(
            name='Bar Test',
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.pv.products.add(self.produit)

        # Utilisateur admin (public schema — SHARED_APPS)
        # / Admin user (public schema — SHARED_APPS)
        self.admin, _created = TibilletUser.objects.get_or_create(
            email='admin-test-fast@tibillet.localhost',
            defaults={
                'username': 'admin-test-fast@tibillet.localhost',
                'is_staff': True,
                'is_active': True,
            },
        )
        self.admin.client_admin.add(self.tenant)

        # Client HTTP avec session admin / HTTP client with admin session
        self.c = TenantClient(self.tenant)
        self.c.force_login(self.admin)

    # ----------------------------------------------------------------------- #
    #  Helper
    # ----------------------------------------------------------------------- #

    def _post_paiement(self, moyen_paiement, quantite=1, extra_data=None):
        """POST /laboutik/paiement/payer/ avec le produit setUp.
        / POST /laboutik/paiement/payer/ with the setUp product."""
        prix_centimes = int(round(self.prix.prix * 100))
        data = {
            'uuid_pv': str(self.pv.uuid),
            'moyen_paiement': moyen_paiement,
            'total': str(prix_centimes * quantite),
            'given_sum': '0',
            f'repid-{self.produit.uuid}': str(quantite),
        }
        if extra_data:
            data.update(extra_data)
        return self.c.post('/laboutik/paiement/payer/', data=data)

    # ----------------------------------------------------------------------- #
    #  Tests (7 methodes, meme couverture que l'ancien fichier)
    # ----------------------------------------------------------------------- #

    def test_paiement_especes_cree_ligne_article(self):
        """Payer en especes cree une LigneArticle avec payment_method='CA'.
        / Cash payment creates a LigneArticle with payment_method='CA'."""
        response = self._post_paiement('espece')
        assert response.status_code == 200

        derniere_ligne = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
        ).order_by('-datetime').first()
        assert derniere_ligne is not None
        assert derniere_ligne.payment_method == PaymentMethod.CASH
        assert derniere_ligne.status == LigneArticle.VALID

    def test_paiement_cb_cree_ligne_article(self):
        """Payer par CB cree une LigneArticle avec payment_method='CC'.
        / CC payment creates a LigneArticle with payment_method='CC'."""
        response = self._post_paiement('carte_bancaire')
        assert response.status_code == 200

        derniere_ligne = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            payment_method=PaymentMethod.CC,
        ).order_by('-datetime').first()
        assert derniere_ligne is not None

    def test_total_centimes_correct(self):
        """Le montant dans LigneArticle == int(round(prix * 100)).
        / The amount in LigneArticle == int(round(price * 100))."""
        response = self._post_paiement('espece', quantite=2)
        assert response.status_code == 200

        derniere_ligne = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
        ).order_by('-datetime').first()
        prix_centimes_attendu = int(round(self.prix.prix * 100))
        assert derniere_ligne.amount == prix_centimes_attendu
        assert int(derniere_ligne.qty) == 2

    def test_pricesold_et_productsold_crees(self):
        """Un paiement cree ProductSold et PriceSold intermediaires.
        / A payment creates intermediate ProductSold and PriceSold."""
        response = self._post_paiement('espece')
        assert response.status_code == 200

        assert ProductSold.objects.filter(
            product=self.produit, event=None,
        ).exists()

        product_sold = ProductSold.objects.get(
            product=self.produit, event=None,
        )
        assert PriceSold.objects.filter(
            productsold=product_sold, price=self.prix,
        ).exists()

    def test_panier_vide_pas_de_ligne(self):
        """POST sans articles → pas de LigneArticle creee, reponse 200 (succes vide).
        / POST without articles → no LigneArticle created, 200 response (empty success)."""
        data = {
            'uuid_pv': str(self.pv.uuid),
            'moyen_paiement': 'espece',
            'total': '0',
            'given_sum': '0',
            # Pas de repid-* → panier vide / No repid-* → empty cart
        }
        response = self.c.post('/laboutik/paiement/payer/', data=data)
        assert response.status_code == 200

        assert LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
        ).count() == 0

    def test_paiement_nfc_carte_inconnue(self):
        """POST moyen_paiement=nfc + tag_id invalide → message "Carte inconnue".
        / POST moyen_paiement=nfc + invalid tag_id → "Carte inconnue" message."""
        response = self._post_paiement('nfc', extra_data={'tag_id': 'FAKE_TAG'})
        assert response.status_code == 200
        contenu = response.content.decode()
        assert "Carte inconnue" in contenu

    def test_product_uuid_inexistant_pas_de_ligne(self):
        """UUID produit inexistant dans le PV → ignore, pas de ligne creee.
        / Non-existent product UUID in PV → ignored, no line created."""
        data = {
            'uuid_pv': str(self.pv.uuid),
            'moyen_paiement': 'espece',
            'total': '100',
            'given_sum': '0',
            'repid-00000000-0000-0000-0000-000000000000': '1',
        }
        response = self.c.post('/laboutik/paiement/payer/', data=data)
        assert response.status_code == 200

        assert LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
        ).count() == 0
