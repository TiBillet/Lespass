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

    def test_deux_lignes_du_meme_produit_sont_additionnees(self):
        """Stock 100g bloquant, panier 100g + 100g : refuse (200g demandes).
        Chaque ligne seule tient dans le stock, mais pas leur somme.
        / 100g blocking stock, cart 100g + 100g: refused (200g requested)."""
        from laboutik.views import _valider_stock_panier

        Stock.objects.create(
            product=self.produit_cacahuetes,
            quantite=100,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=False,
        )

        articles = [
            self._construire_article_panier(weight_amount=100),
            self._construire_article_panier(weight_amount=100),
        ]
        erreurs = _valider_stock_panier(articles)

        assert len(erreurs) == 1
        assert erreurs[0]["name"] == "Cacahuetes en vrac"
        assert erreurs[0]["demande"] == 200
        assert erreurs[0]["disponible"] == 100

    def test_deux_lignes_qui_tiennent_ensemble_dans_le_stock_passent(self):
        """Stock 100g bloquant, panier 40g + 60g : accepte (pile 100g).
        / 100g blocking stock, cart 40g + 60g: accepted (exactly 100g)."""
        from laboutik.views import _valider_stock_panier

        Stock.objects.create(
            product=self.produit_cacahuetes,
            quantite=100,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=False,
        )

        articles = [
            self._construire_article_panier(weight_amount=40),
            self._construire_article_panier(weight_amount=60),
        ]
        erreurs = _valider_stock_panier(articles)

        assert erreurs == []

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

        # Quantites lisibles, et "dans le panier" / "en stock" (pas "demande" / "reste")
        # / Readable quantities, "in the cart" / "in stock" wording
        assert "Cacahuetes en vrac : 50 kg dans le panier, 200 g en stock" in message
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

        # Active la caisse V2 (le garde HasLaBoutikTerminalAccess l'exige).
        # / Enable V2 POS (required by the HasLaBoutikTerminalAccess guard).
        from BaseBillet.models import Configuration
        config = Configuration.get_solo()
        config.module_monnaie_locale = True
        config.module_caisse = True
        config.save()

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

    def _post_moyens_paiement_vrac(self, weight_amount):
        """POST sur moyens_paiement (clic VALIDER) pour weight_amount grammes.
        / POST to moyens_paiement (VALIDER click) for weight_amount grams."""
        prix_centimes = int(weight_amount / 1000 * 1200)
        line_id = f"{self.produit.uuid}--{self.prix.uuid}--1"
        data = {
            "uuid_pv": str(self.pv.uuid),
            f"repid-{line_id}": "1",
            f"weight-{line_id}": str(weight_amount),
            f"custom-{line_id}": str(prix_centimes),
        }
        return self.c.post("/laboutik/paiement/moyens_paiement/", data=data)

    def test_valider_refuse_400_avant_choix_du_moyen_de_paiement(self):
        """Stock bloquant + insuffisant : le refus arrive au clic VALIDER,
        pas apres le choix especes / CB.
        / Blocking + insufficient stock: refused on VALIDER, before payment choice."""
        Stock.objects.create(
            product=self.produit,
            quantite=200,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=False,
        )

        response = self._post_moyens_paiement_vrac(weight_amount=50000)

        assert response.status_code == 400
        contenu = response.content.decode("utf-8")
        assert "Cacahuetes flow" in contenu

    def test_valider_passe_200_si_vente_hors_stock_autorisee(self):
        """Vente hors stock autorisee : VALIDER affiche les moyens de paiement.
        / Out-of-stock allowed: VALIDER shows payment methods."""
        Stock.objects.create(
            product=self.produit,
            quantite=200,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=True,
        )

        response = self._post_moyens_paiement_vrac(weight_amount=50000)

        assert response.status_code == 200

    def test_paiement_nfc_bloque_400_si_hors_stock_interdit_et_insuffisant(self):
        """Le paiement cashless (NFC) verifie aussi le stock.
        Avant, il vendait l'article epuise sans controle.
        La garde passe avant la recherche de la carte : un tag inconnu suffit.
        / NFC payment also checks stock. The guard runs before the card lookup."""
        Stock.objects.create(
            product=self.produit,
            quantite=200,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=False,
        )
        nb_lignes_avant = LigneArticle.objects.count()

        prix_centimes = int(50000 / 1000 * 1200)
        line_id = f"{self.produit.uuid}--{self.prix.uuid}--1"
        data = {
            "uuid_pv": str(self.pv.uuid),
            "moyen_paiement": "nfc",
            "tag_id": "AAAAAAAA",
            "total": str(prix_centimes),
            "given_sum": "0",
            f"repid-{line_id}": "1",
            f"weight-{line_id}": str(50000),
            f"custom-{line_id}": str(prix_centimes),
        }
        response = self.c.post("/laboutik/paiement/payer/", data=data)

        assert response.status_code == 400
        assert "Cacahuetes flow" in response.content.decode("utf-8")
        assert LigneArticle.objects.count() == nb_lignes_avant

    def test_paiement_refuse_si_deux_pesees_depassent_le_stock_ensemble(self):
        """Stock 100g bloquant, panier 100g + 100g (2 lignes) : 400, rien de vendu.
        / 100g blocking stock, cart 100g + 100g (2 lines): 400, nothing sold."""
        Stock.objects.create(
            product=self.produit,
            quantite=100,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=False,
        )
        nb_lignes_avant = LigneArticle.objects.count()

        # Deux pesees = deux lignes --1 et --2 (comme le pave de tarif.js)
        # / Two weighings = two lines --1 and --2 (like the tarif.js keypad)
        data = {
            "uuid_pv": str(self.pv.uuid),
            "moyen_paiement": "espece",
            "total": "240",
            "given_sum": "0",
        }
        for numero_de_pesee in (1, 2):
            line_id = f"{self.produit.uuid}--{self.prix.uuid}--{numero_de_pesee}"
            data[f"repid-{line_id}"] = "1"
            data[f"weight-{line_id}"] = "100"
            data[f"custom-{line_id}"] = "120"

        response = self.c.post("/laboutik/paiement/payer/", data=data)

        assert response.status_code == 400
        assert "Cacahuetes flow" in response.content.decode("utf-8")
        assert LigneArticle.objects.count() == nb_lignes_avant
        stock = self.produit.stock_inventaire
        stock.refresh_from_db()
        assert stock.quantite == 100


    # --- Popup de la garde au clic (GET stock_insuffisant) ---
    # / Click guard popup (GET stock_insuffisant)

    def _get_message_stock(self, quantite_au_panier, quantite_a_ajouter):
        return self.c.get(
            "/laboutik/paiement/stock_insuffisant/",
            {
                "product_uuid": str(self.produit.uuid),
                "quantite_au_panier": quantite_au_panier,
                "quantite_a_ajouter": quantite_a_ajouter,
            },
        )

    def test_message_stock_insuffisant_dit_panier_stock_et_reste(self):
        """Stock 100 g, 60 g au panier, on veut 50 g : popup warning claire.
        / 100 g stock, 60 g in cart, 50 g wanted: clear warning popup."""
        Stock.objects.create(
            product=self.produit,
            quantite=100,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=False,
        )

        response = self._get_message_stock(quantite_au_panier=60, quantite_a_ajouter=50)

        assert response.status_code == 200
        contenu = response.content.decode("utf-8")
        assert 'data-testid="alerte-messages"' in contenu
        assert "alerte-box--warning" in contenu
        assert "Cacahuetes flow : stock insuffisant." in contenu
        assert "Déjà dans le panier : 60 g" in contenu
        assert "En stock : 100 g" in contenu
        assert "Vous pouvez encore en ajouter : 40 g" in contenu

    def test_message_stock_insuffisant_quand_plus_rien_n_est_possible(self):
        """Stock 100 g, 100 g au panier : "Vous ne pouvez plus en ajouter."
        / 100 g stock, 100 g in cart: nothing more can be added."""
        Stock.objects.create(
            product=self.produit,
            quantite=100,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=False,
        )

        response = self._get_message_stock(quantite_au_panier=100, quantite_a_ajouter=1)

        contenu = response.content.decode("utf-8")
        assert "Vous ne pouvez plus en ajouter." in contenu

    def test_message_stock_change_si_le_stock_en_base_permet_l_ajout(self):
        """Le badge etait en retard : en base, l'ajout passe. Popup info "retouchez".
        / Stale badge: the DB stock allows it. Info popup "tap again"."""
        Stock.objects.create(
            product=self.produit,
            quantite=1000,
            unite=UniteStock.GR,
            autoriser_vente_hors_stock=False,
        )

        response = self._get_message_stock(quantite_au_panier=100, quantite_a_ajouter=50)

        contenu = response.content.decode("utf-8")
        assert "alerte-box--info" in contenu
        assert "Le stock vient de changer" in contenu
