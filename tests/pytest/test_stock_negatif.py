"""
tests/pytest/test_stock_negatif.py — Tests bug 8 : stock vrac negatif et blocage hors stock.
/ Tests for bug 8: vrac negative stock and out-of-stock blocking.

Couvre :
- _valider_stock_panier : 3 cas (autorise / interdit + ok / interdit + insuffisant)
- _formater_erreurs_stock : le message lisible pour le caissier
- _creer_lignes_articles : retourne (lignes, produits_stock_negatif)
- Flow paiement especes :
    - vente hors stock autorisee + insuffisant → 200 + alerte stock_negatif
    - vente hors stock interdite + insuffisant → 400 + aucune LigneArticle creee

Covers:
- _valider_stock_panier: 3 cases (allowed / blocked + ok / blocked + insufficient)
- _formater_erreurs_stock: readable message for the cashier
- _creer_lignes_articles: returns (lignes, produits_stock_negatif)
- Cash payment flow:
    - allow out-of-stock + insufficient → 200 + stock_negatif alert
    - block out-of-stock + insufficient → 400 + no LigneArticle created

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_stock_negatif.py -v

LOCALISATION : tests/pytest/test_stock_negatif.py
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")


import django

django.setup()

from decimal import Decimal

from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    CategorieProduct,
    LigneArticle,
    Price,
    Product,
)
from inventaire.models import Stock, UniteStock
from laboutik.models import PointDeVente


class TestValiderStockPanier(FastTenantTestCase):
    """Tests unitaires pour _valider_stock_panier.
    / Unit tests for _valider_stock_panier."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_stock_negatif"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-stock-negatif.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test Stock Negatif"

    def setUp(self):
        # Re-setter le search_path apres le rollback du test precedent.
        # / Re-set search_path after previous test's rollback.
        connection.set_tenant(self.tenant)

        self.categorie = CategorieProduct.objects.create(name="Vrac Test")
        self.produit_cacahuetes = Product.objects.create(
            name="Cacahuetes en vrac",
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
        )
        self.prix_cacahuetes = Price.objects.create(
            product=self.produit_cacahuetes,
            name="Prix au kilo",
            prix=Decimal("12.00"),
            poids_mesure=True,
            publish=True,
        )

    def _construire_article_panier(self, weight_amount=None, quantite=1):
        """Helper : construit un dict article comme _extraire_articles_du_panier()."""
        return {
            "product": self.produit_cacahuetes,
            "price": self.prix_cacahuetes,
            "quantite": quantite,
            "prix_centimes": 1200,
            "weight_amount": weight_amount,
        }

    def test_aucun_stock_lie_retourne_vide(self):
        """Produit sans Stock lie : pas de blocage possible.
        / Product without linked Stock: no possible blocking."""
        from laboutik.views import _valider_stock_panier

        articles = [self._construire_article_panier(weight_amount=50000)]
        erreurs = _valider_stock_panier(articles)

        assert erreurs == []

    def test_vente_hors_stock_autorisee_retourne_vide(self):
        """autoriser_vente_hors_stock=True : aucun blocage en amont.
        / autoriser_vente_hors_stock=True: no upstream blocking."""
        from laboutik.views import _valider_stock_panier

        Stock.objects.create(
            product=self.produit_cacahuetes,
            quantite=200,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=True,  # par defaut, mais on est explicite
        )

        # On demande 50000g sur un stock de 200g
        # / We request 50000g on a 200g stock
        articles = [self._construire_article_panier(weight_amount=50000)]
        erreurs = _valider_stock_panier(articles)

        assert erreurs == []

    def test_vente_hors_stock_interdite_stock_ok(self):
        """autoriser_vente_hors_stock=False + stock suffisant : pas d'erreur.
        / Out-of-stock blocked + sufficient stock: no error."""
        from laboutik.views import _valider_stock_panier

        Stock.objects.create(
            product=self.produit_cacahuetes,
            quantite=1000,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=False,
        )

        # On demande 200g sur un stock de 1000g
        # / We request 200g on a 1000g stock
        articles = [self._construire_article_panier(weight_amount=200)]
        erreurs = _valider_stock_panier(articles)

        assert erreurs == []

    def test_vente_hors_stock_interdite_insuffisant(self):
        """autoriser_vente_hors_stock=False + stock insuffisant : erreur retournee.
        / Out-of-stock blocked + insufficient stock: error returned."""
        from laboutik.views import _valider_stock_panier

        Stock.objects.create(
            product=self.produit_cacahuetes,
            quantite=200,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=False,
        )

        # On demande 50000g sur un stock de 200g
        # / We request 50000g on a 200g stock
        articles = [self._construire_article_panier(weight_amount=50000)]
        erreurs = _valider_stock_panier(articles)

        assert len(erreurs) == 1
        erreur = erreurs[0]
        assert erreur["name"] == "Cacahuetes en vrac"
        assert erreur["demande"] == 50000
        assert erreur["disponible"] == 200
        assert erreur["unite"] == UniteStock.GR

    def test_format_erreurs_stock_message_lisible(self):
        """_formater_erreurs_stock produit un message contenant nom + quantites.
        / _formater_erreurs_stock produces a message with name + quantities."""
        from laboutik.views import _formater_erreurs_stock

        erreurs = [
            {
                "name": "Cacahuetes en vrac",
                "demande": 50000,
                "disponible": 200,
                "unite": "GR",
            }
        ]
        message = _formater_erreurs_stock(erreurs)

        assert "Cacahuetes en vrac" in message
        assert "50000" in message
        assert "200" in message
        # Le mot "insuffisant" ou la phrase signal doit apparaitre
        # / The word "insuffisant" or signal phrase must appear
        assert "insuffisant" in message.lower() or "refusée" in message.lower()


class TestCreerLignesArticlesRetourTuple(FastTenantTestCase):
    """Tests pour la nouvelle signature de _creer_lignes_articles.
    / Tests for the new signature of _creer_lignes_articles."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_stock_negatif_lignes"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-stock-negatif-lignes.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test Stock Negatif Lignes"

    def setUp(self):
        connection.set_tenant(self.tenant)

        self.categorie = CategorieProduct.objects.create(name="Vrac Test 2")
        self.produit = Product.objects.create(
            name="Cacahuetes test 2",
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
        )
        self.prix = Price.objects.create(
            product=self.produit,
            name="Prix au kilo",
            prix=Decimal("12.00"),
            poids_mesure=True,
            publish=True,
        )

    def test_retourne_tuple_lignes_et_produits_negatifs(self):
        """_creer_lignes_articles retourne (lignes, produits_stock_negatif).
        / _creer_lignes_articles returns (lignes, produits_stock_negatif)."""
        from django.db import transaction as db_transaction

        from laboutik.views import _creer_lignes_articles

        # Stock 200g, on vend 50000g — vente hors stock autorisee
        # / 200g stock, sell 50000g — out-of-stock allowed
        Stock.objects.create(
            product=self.produit,
            quantite=200,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=True,
        )

        articles_panier = [
            {
                "product": self.produit,
                "price": self.prix,
                "quantite": 1,
                "prix_centimes": 60000,  # 50000g a 12€/kg = 600€
                "weight_amount": 50000,
            }
        ]

        with db_transaction.atomic():
            resultat = _creer_lignes_articles(articles_panier, "espece")

        # Le retour est un tuple (list, list)
        # / Return is a tuple (list, list)
        assert isinstance(resultat, tuple)
        assert len(resultat) == 2

        lignes, produits_stock_negatif = resultat
        assert len(lignes) == 1
        assert isinstance(lignes[0], LigneArticle)

        # Le produit est passe en negatif (200 - 50000 = -49800)
        # / Product went negative (200 - 50000 = -49800)
        assert len(produits_stock_negatif) == 1
        assert produits_stock_negatif[0]["name"] == "Cacahuetes test 2"
        assert produits_stock_negatif[0]["quantite"] == -49800
        assert produits_stock_negatif[0]["unite"] == UniteStock.GR

    def test_retourne_liste_vide_si_stock_reste_positif(self):
        """Si le stock reste positif apres la vente, produits_stock_negatif est vide.
        / If stock stays positive after sale, produits_stock_negatif is empty."""
        from django.db import transaction as db_transaction

        from laboutik.views import _creer_lignes_articles

        # Stock 100kg, on vend 200g
        # / 100kg stock, sell 200g
        Stock.objects.create(
            product=self.produit,
            quantite=100000,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=True,
        )

        articles_panier = [
            {
                "product": self.produit,
                "price": self.prix,
                "quantite": 1,
                "prix_centimes": 240,  # 200g a 12€/kg = 2.40€
                "weight_amount": 200,
            }
        ]

        with db_transaction.atomic():
            lignes, produits_stock_negatif = _creer_lignes_articles(
                articles_panier, "espece"
            )

        assert len(lignes) == 1
        assert produits_stock_negatif == []


class TestFlowPaiementStock(FastTenantTestCase):
    """Tests du flow HTTP complet : blocage 400 et alerte 200.
    / Full HTTP flow tests: 400 blocking and 200 alert."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_stock_negatif_flow"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-stock-negatif-flow.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test Stock Negatif Flow"

    def setUp(self):
        connection.set_tenant(self.tenant)

        self.categorie = CategorieProduct.objects.create(name="Vrac Flow")
        self.produit = Product.objects.create(
            name="Cacahuetes flow",
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
        )
        self.prix = Price.objects.create(
            product=self.produit,
            name="Prix au kilo",
            prix=Decimal("12.00"),
            poids_mesure=True,
            publish=True,
        )
        self.pv = PointDeVente.objects.create(
            name="Bar Vrac",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.pv.products.add(self.produit)

        self.admin, _created = TibilletUser.objects.get_or_create(
            email="admin-stock-negatif@tibillet.localhost",
            defaults={
                "username": "admin-stock-negatif@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        self.admin.client_admin.add(self.tenant)

        self.c = TenantClient(self.tenant)
        self.c.force_login(self.admin)

    def _post_paiement_vrac(self, weight_amount):
        """POST paiement especes pour weight_amount grammes de cacahuetes.
        / POST cash payment for weight_amount grams of peanuts."""
        # Ligne panier au format suffixe variable (--N) attendu par le backend
        # pour les articles a montant variable (poids/mesure).
        # / Cart line with variable suffix (--N) expected by backend
        # for variable-amount articles (weight/measure).
        prix_centimes = int(weight_amount / 1000 * 1200)  # weight_amount g a 12€/kg
        line_id = f"{self.produit.uuid}--{self.prix.uuid}--1"
        data = {
            "uuid_pv": str(self.pv.uuid),
            "moyen_paiement": "espece",
            "total": str(prix_centimes),
            "given_sum": "0",
            f"repid-{line_id}": "1",
            f"weight-{line_id}": str(weight_amount),
            f"custom-{line_id}": str(prix_centimes),
        }
        return self.c.post("/laboutik/paiement/payer/", data=data)

    def test_paiement_bloque_400_si_hors_stock_interdit_et_insuffisant(self):
        """autoriser_vente_hors_stock=False + stock insuffisant : 400, aucune ligne creee.
        / Out-of-stock blocked + insufficient: 400, no LigneArticle created."""
        Stock.objects.create(
            product=self.produit,
            quantite=200,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=False,
        )

        nb_lignes_avant = LigneArticle.objects.count()

        response = self._post_paiement_vrac(weight_amount=50000)

        # Le serveur renvoie 400 et le partial d'erreur
        # / Server returns 400 and the error partial
        assert response.status_code == 400
        contenu = response.content.decode("utf-8")
        assert "Cacahuetes flow" in contenu

        # Aucune LigneArticle creee
        # / No LigneArticle created
        assert LigneArticle.objects.count() == nb_lignes_avant

        # Stock inchange
        # / Stock unchanged
        stock = self.produit.stock_inventaire
        stock.refresh_from_db()
        assert stock.quantite == 200

    def test_paiement_passe_200_avec_alerte_si_hors_stock_autorise_et_insuffisant(self):
        """autoriser_vente_hors_stock=True + insuffisant : 200, alerte produits_stock_negatif.
        / Out-of-stock allowed + insufficient: 200, produits_stock_negatif alert."""
        Stock.objects.create(
            product=self.produit,
            quantite=200,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=True,
        )

        response = self._post_paiement_vrac(weight_amount=50000)

        # Le paiement passe (200) et l'ecran de succes contient l'alerte
        # / Payment passes (200) and success screen contains the alert
        assert response.status_code == 200
        contenu = response.content.decode("utf-8")
        assert 'data-testid="alerte-stock-negatif"' in contenu
        assert "Cacahuetes flow" in contenu
        assert "-49800" in contenu  # 200 - 50000 = -49800
        assert "clic long" in contenu  # Le hint mainteneur

        # La LigneArticle est bien creee
        # / LigneArticle is created
        ligne = (
            LigneArticle.objects.filter(
                pricesold__price=self.prix,
            )
            .order_by("-datetime")
            .first()
        )
        assert ligne is not None
        assert ligne.weight_quantity == 50000

        # Stock passe en negatif
        # / Stock went negative
        stock = self.produit.stock_inventaire
        stock.refresh_from_db()
        assert stock.quantite == -49800
