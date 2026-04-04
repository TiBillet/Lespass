"""
Tests pour l'app inventaire (Stock + MouvementStock).
/ Tests for the inventaire app (Stock + MouvementStock).

LOCALISATION : tests/pytest/test_inventaire.py
"""

import time

import pytest
from django_tenants.test.cases import FastTenantTestCase

from Customers.models import Client


class TestStockModel(FastTenantTestCase):
    """Tests unitaires pour le modèle Stock / Unit tests for the Stock model."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_inventaire"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-inventaire.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.categorie = Client.SALLE_SPECTACLE
        tenant.save()

    def setUp(self):
        from django.db import connection

        connection.set_tenant(self.tenant)

        from BaseBillet.models import Product, Tva

        self.tva, _ = Tva.objects.get_or_create(tva_rate=20)
        self.product = Product.objects.create(
            name="Bière pression",
            methode_caisse="VT",
            tva=self.tva,
        )

    def test_creation_stock_basique(self):
        """Créer un Stock, vérifier les champs et __str__."""
        from inventaire.models import Stock, UniteStock

        stock = Stock.objects.create(
            product=self.product,
            quantite=50,
            unite=UniteStock.UN,
        )
        stock.refresh_from_db()

        assert stock.quantite == 50
        assert stock.unite == UniteStock.UN
        assert stock.seuil_alerte is None
        assert stock.autoriser_vente_hors_stock is True
        assert "Bière pression" in str(stock)
        assert "50" in str(stock)

    def test_stock_est_en_alerte(self):
        """Stock sous le seuil mais > 0 = en alerte."""
        from inventaire.models import Stock

        stock = Stock.objects.create(
            product=self.product,
            quantite=3,
            seuil_alerte=5,
        )
        assert stock.est_en_alerte() is True
        assert stock.est_en_rupture() is False

    def test_stock_pas_en_alerte_si_pas_de_seuil(self):
        """Pas de seuil défini = jamais en alerte."""
        from inventaire.models import Stock

        stock = Stock.objects.create(
            product=self.product,
            quantite=1,
            seuil_alerte=None,
        )
        assert stock.est_en_alerte() is False

    def test_stock_est_en_rupture(self):
        """Quantité <= 0 = en rupture."""
        from inventaire.models import Stock

        stock = Stock.objects.create(
            product=self.product,
            quantite=0,
        )
        assert stock.est_en_rupture() is True

    def test_stock_negatif_autorise(self):
        """La quantité peut être négative (ventes hors stock)."""
        from inventaire.models import Stock

        stock = Stock.objects.create(
            product=self.product,
            quantite=-5,
        )
        stock.refresh_from_db()
        assert stock.quantite == -5
        assert stock.est_en_rupture() is True

    def test_stock_unite_grammes(self):
        """L'unité GR (grammes) fonctionne."""
        from inventaire.models import Stock, UniteStock

        stock = Stock.objects.create(
            product=self.product,
            quantite=1500,
            unite=UniteStock.GR,
        )
        assert stock.unite == UniteStock.GR
        # Le label peut être FR ("Grammes") ou EN ("Grams") selon la locale active
        # / Label can be FR or EN depending on active locale
        stock_str = str(stock).lower()
        assert "gramm" in stock_str or "grams" in stock_str

    def test_contenance_sur_price(self):
        """Le champ contenance est disponible sur Price. / contenance field on Price."""
        from BaseBillet.models import Price

        prix_pinte = Price.objects.create(
            product=self.product,
            name="Pinte",
            prix=5.00,
            contenance=50,
        )
        prix_demi = Price.objects.create(
            product=self.product,
            name="Demi",
            prix=3.00,
            contenance=25,
        )
        assert prix_pinte.contenance == 50
        assert prix_demi.contenance == 25

    def test_contenance_null_par_defaut(self):
        """contenance=None signifie 1 unité par défaut. / None means 1 unit default."""
        from BaseBillet.models import Price

        prix = Price.objects.create(
            product=self.product,
            name="Verre",
            prix=2.00,
        )
        assert prix.contenance is None


class TestMouvementStockModel(FastTenantTestCase):
    """Tests unitaires pour le modèle MouvementStock / Unit tests for MouvementStock."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_inventaire"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-inventaire.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.categorie = Client.SALLE_SPECTACLE
        tenant.save()

    def setUp(self):
        from django.db import connection

        connection.set_tenant(self.tenant)

        from BaseBillet.models import Product, Tva
        from inventaire.models import Stock

        self.tva, _ = Tva.objects.get_or_create(tva_rate=20)
        self.product = Product.objects.create(
            name="Coca-Cola",
            methode_caisse="VT",
            tva=self.tva,
        )
        self.stock = Stock.objects.create(
            product=self.product,
            quantite=100,
        )

    def test_creation_mouvement_vente(self):
        """Créer un mouvement de type Vente (VE)."""
        from inventaire.models import MouvementStock, TypeMouvement

        mvt = MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.VE,
            quantite=-2,
            quantite_avant=100,
        )
        mvt.refresh_from_db()

        assert mvt.type_mouvement == TypeMouvement.VE
        assert mvt.quantite == -2
        assert mvt.quantite_avant == 100
        assert mvt.motif == ""
        assert mvt.ligne_article is None
        assert mvt.cloture is None
        assert mvt.cree_par is None

    def test_creation_mouvement_reception(self):
        """Créer un mouvement de type Réception (RE) avec motif."""
        from inventaire.models import MouvementStock, TypeMouvement

        mvt = MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.RE,
            quantite=50,
            quantite_avant=100,
            motif="Livraison fournisseur",
        )
        assert mvt.type_mouvement == TypeMouvement.RE
        assert mvt.quantite == 50
        assert mvt.motif == "Livraison fournisseur"

    def test_mouvement_ordering_par_date(self):
        """Les mouvements sont triés par -cree_le (plus récent en premier)."""
        from inventaire.models import MouvementStock, TypeMouvement

        mvt1 = MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.VE,
            quantite=-1,
            quantite_avant=100,
        )
        # Petit délai pour garantir un cree_le différent
        # / Small delay to ensure different cree_le
        time.sleep(0.05)
        mvt2 = MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.RE,
            quantite=10,
            quantite_avant=99,
        )

        mouvements = list(MouvementStock.objects.all())
        assert mouvements[0].pk == mvt2.pk
        assert mouvements[1].pk == mvt1.pk

    def test_str_mouvement(self):
        """__str__ contient le type, le delta signé et le nom du produit."""
        from inventaire.models import MouvementStock, TypeMouvement

        mvt = MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.VE,
            quantite=-3,
            quantite_avant=100,
        )
        texte = str(mvt)
        # Le delta signé doit apparaître / Signed delta must appear
        assert "-3" in texte
        # Le nom du produit / Product name
        assert "Coca-Cola" in texte


class TestStockService(FastTenantTestCase):
    """Tests pour StockService / Tests for StockService."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_inventaire"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-inventaire.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.categorie = Client.SALLE_SPECTACLE
        tenant.save()

    def setUp(self):
        from django.db import connection

        connection.set_tenant(self.tenant)

        from BaseBillet.models import Price, Product, Tva
        from inventaire.models import Stock, UniteStock

        self.tva, _ = Tva.objects.get_or_create(tva_rate=20)
        self.product = Product.objects.create(
            name="Bière pression service",
            methode_caisse="VT",
            tva=self.tva,
        )
        self.price_pinte = Price.objects.create(
            product=self.product,
            name="Pinte",
            prix=5.00,
            contenance=50,
        )
        self.stock = Stock.objects.create(
            product=self.product,
            quantite=3000,
            unite=UniteStock.CL,
            seuil_alerte=500,
        )

    def test_decrementer_stock_vente(self):
        """Vendre 2 pintes (contenance=50) décrémente de 100cl."""
        from inventaire.models import MouvementStock, TypeMouvement
        from inventaire.services import StockService

        StockService.decrementer_pour_vente(
            stock=self.stock,
            contenance=self.price_pinte.contenance,
            qty=2,
        )

        self.stock.refresh_from_db()
        assert self.stock.quantite == 2900

        mvt = MouvementStock.objects.filter(stock=self.stock).first()
        assert mvt.type_mouvement == TypeMouvement.VE
        assert mvt.quantite == -100
        assert mvt.quantite_avant == 3000

    def test_decrementer_stock_contenance_null(self):
        """contenance=None utilise 1 par défaut. / None defaults to 1."""
        from BaseBillet.models import Product
        from inventaire.models import MouvementStock, Stock, UniteStock
        from inventaire.services import StockService

        product_unite = Product.objects.create(
            name="Snack service",
            methode_caisse="VT",
            tva=self.tva,
        )
        stock_unite = Stock.objects.create(
            product=product_unite,
            quantite=20,
            unite=UniteStock.UN,
        )

        StockService.decrementer_pour_vente(
            stock=stock_unite,
            contenance=None,
            qty=3,
        )

        stock_unite.refresh_from_db()
        assert stock_unite.quantite == 17

        mvt = MouvementStock.objects.filter(stock=stock_unite).first()
        assert mvt.quantite == -3

    def test_decrementer_stock_non_bloquant_passe_en_negatif(self):
        """Stock non bloquant : la vente passe en négatif. / Non-blocking allows negative."""
        from inventaire.services import StockService

        self.stock.quantite = 30
        self.stock.save()

        StockService.decrementer_pour_vente(
            stock=self.stock,
            contenance=50,
            qty=1,
        )

        self.stock.refresh_from_db()
        assert self.stock.quantite == -20

    def test_decrementer_stock_bloquant_leve_exception(self):
        """Stock bloquant + insuffisant => StockInsuffisant. / Blocking + insufficient raises."""
        from inventaire.models import StockInsuffisant
        from inventaire.services import StockService

        self.stock.quantite = 30
        self.stock.autoriser_vente_hors_stock = False
        self.stock.save()

        with pytest.raises(StockInsuffisant):
            StockService.decrementer_pour_vente(
                stock=self.stock,
                contenance=50,
                qty=1,
            )

        # Le stock n'a pas bougé / Stock unchanged
        self.stock.refresh_from_db()
        assert self.stock.quantite == 30

    def test_creer_mouvement_reception(self):
        """Réception de 3000cl ajoute au stock. / Reception adds to stock."""
        from inventaire.models import MouvementStock, TypeMouvement
        from inventaire.services import StockService

        StockService.creer_mouvement(
            stock=self.stock,
            type_mouvement=TypeMouvement.RE,
            quantite=3000,
            motif="Livraison brasseur",
        )

        self.stock.refresh_from_db()
        assert self.stock.quantite == 6000

        mvt = MouvementStock.objects.filter(
            stock=self.stock, type_mouvement=TypeMouvement.RE
        ).first()
        assert mvt.quantite == 3000
        assert mvt.quantite_avant == 3000
        assert mvt.motif == "Livraison brasseur"

    def test_creer_mouvement_perte(self):
        """Perte de 200cl : delta automatiquement négatif. / Loss: delta auto-negative."""
        from inventaire.models import MouvementStock, TypeMouvement
        from inventaire.services import StockService

        StockService.creer_mouvement(
            stock=self.stock,
            type_mouvement=TypeMouvement.PE,
            quantite=200,
        )

        self.stock.refresh_from_db()
        assert self.stock.quantite == 2800

        mvt = MouvementStock.objects.filter(
            stock=self.stock, type_mouvement=TypeMouvement.PE
        ).first()
        assert mvt.quantite == -200

    def test_ajustement_inventaire(self):
        """Ajustement à 2500 : delta calculé automatiquement. / Adjustment computes delta."""
        from inventaire.models import MouvementStock, TypeMouvement
        from inventaire.services import StockService

        StockService.ajuster_inventaire(
            stock=self.stock,
            stock_reel=2500,
            motif="Inventaire mensuel",
        )

        self.stock.refresh_from_db()
        assert self.stock.quantite == 2500

        mvt = MouvementStock.objects.filter(
            stock=self.stock, type_mouvement=TypeMouvement.AJ
        ).first()
        assert mvt.quantite == -500
        assert mvt.quantite_avant == 3000


class TestStockViewSet(FastTenantTestCase):
    """Tests pour les endpoints StockViewSet (reception, perte, offert).
    / Tests for StockViewSet endpoints."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_inventaire"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-inventaire.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.categorie = Client.SALLE_SPECTACLE
        tenant.save()

    def setUp(self):
        from django.db import connection

        connection.set_tenant(self.tenant)

        from rest_framework.test import APIClient

        from AuthBillet.models import TibilletUser
        from BaseBillet.models import Product, Tva
        from inventaire.models import Stock, UniteStock

        self.tva, _ = Tva.objects.get_or_create(tva_rate=20)
        self.product = Product.objects.create(
            name="Biere stock view",
            methode_caisse="VT",
            tva=self.tva,
        )
        self.stock = Stock.objects.create(
            product=self.product,
            quantite=3000,
            unite=UniteStock.CL,
        )

        # Utilisateur admin pour l'authentification
        # / Admin user for authentication
        self.user = TibilletUser.objects.create_superuser(
            email="stock-view-test@test.local",
            password="testpass123",
        )
        self.user.client_admin.add(self.tenant)

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.defaults["HTTP_HOST"] = "test-inventaire.tibillet.localhost"

    def test_reception_stock(self):
        """POST reception ajoute au stock. / POST reception adds to stock."""
        url = f"/api/inventaire/stock/{self.stock.pk}/reception/"
        response = self.client.post(url, {"quantite": 3000}, format="json")

        assert response.status_code == 200
        assert response.data["stock_actuel"] == 6000

    def test_perte_stock(self):
        """POST perte retire du stock. / POST loss removes from stock."""
        url = f"/api/inventaire/stock/{self.stock.pk}/perte/"
        response = self.client.post(url, {"quantite": 200}, format="json")

        assert response.status_code == 200
        assert response.data["stock_actuel"] == 2800

    def test_offert_stock(self):
        """POST offert retire du stock. / POST offered removes from stock."""
        url = f"/api/inventaire/stock/{self.stock.pk}/offert/"
        response = self.client.post(url, {"quantite": 50}, format="json")

        assert response.status_code == 200
        assert response.data["stock_actuel"] == 2950

    def test_reception_quantite_invalide(self):
        """quantite=0 retourne 400. / quantite=0 returns 400."""
        url = f"/api/inventaire/stock/{self.stock.pk}/reception/"
        response = self.client.post(url, {"quantite": 0}, format="json")

        assert response.status_code == 400


class TestDebitMetreViewSet(FastTenantTestCase):
    """Tests pour l'endpoint DebitMetreViewSet (capteur debit metre).
    / Tests for DebitMetreViewSet endpoint (flow meter sensor)."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_inventaire"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-inventaire.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.categorie = Client.SALLE_SPECTACLE
        tenant.save()

    def setUp(self):
        from django.db import connection

        connection.set_tenant(self.tenant)

        from rest_framework.test import APIClient

        from AuthBillet.models import TibilletUser
        from BaseBillet.models import Product, Tva
        from inventaire.models import Stock, UniteStock

        self.tva, _ = Tva.objects.get_or_create(tva_rate=20)
        self.product = Product.objects.create(
            name="Biere debit metre",
            methode_caisse="VT",
            tva=self.tva,
        )
        self.stock = Stock.objects.create(
            product=self.product,
            quantite=5000,
            unite=UniteStock.CL,
        )

        self.user = TibilletUser.objects.create_superuser(
            email="debit-metre-test@test.local",
            password="testpass123",
        )
        self.user.client_admin.add(self.tenant)

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.defaults["HTTP_HOST"] = "test-inventaire.tibillet.localhost"

    def test_debit_metre_decremente(self):
        """POST debit-metre decremente en CL. / POST debit-metre decrements in CL."""
        from inventaire.models import MouvementStock, TypeMouvement

        url = "/api/inventaire/debit-metre/"
        response = self.client.post(
            url,
            {
                "product_uuid": str(self.product.uuid),
                "quantite_cl": 850,
                "capteur_id": "pi-tireuse-01",
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["stock_actuel"] == 4150
        assert response.data["product_uuid"] == str(self.product.uuid)

        # Verifier le mouvement cree / Check the created movement
        mvt = MouvementStock.objects.filter(
            stock=self.stock, type_mouvement=TypeMouvement.DM
        ).first()
        assert mvt is not None
        assert mvt.quantite == -850
        assert mvt.motif == "pi-tireuse-01"

    def test_debit_metre_produit_sans_stock_cl(self):
        """Produit avec stock en UN (pas CL) retourne 400.
        / Product with stock in UN (not CL) returns 400."""
        from BaseBillet.models import Product
        from inventaire.models import Stock, UniteStock

        product_un = Product.objects.create(
            name="Snack sans CL",
            methode_caisse="VT",
            tva=self.tva,
        )
        Stock.objects.create(
            product=product_un,
            quantite=100,
            unite=UniteStock.UN,
        )

        url = "/api/inventaire/debit-metre/"
        response = self.client.post(
            url,
            {
                "product_uuid": str(product_un.uuid),
                "quantite_cl": 500,
                "capteur_id": "pi-tireuse-02",
            },
            format="json",
        )

        assert response.status_code == 400


class TestResumeStockCloture(FastTenantTestCase):
    """Tests pour ResumeStockService (résumé stock dans clôture de caisse).
    / Tests for ResumeStockService (stock summary in cash closure)."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_inventaire"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-inventaire.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.categorie = Client.SALLE_SPECTACLE
        tenant.save()

    def setUp(self):
        from django.db import connection

        connection.set_tenant(self.tenant)

        from BaseBillet.models import Product, Tva
        from inventaire.models import MouvementStock, Stock, TypeMouvement, UniteStock

        self.tva, _ = Tva.objects.get_or_create(tva_rate=20)
        self.product = Product.objects.create(
            name="Bière résumé clôture",
            methode_caisse="VT",
            tva=self.tva,
        )
        self.stock = Stock.objects.create(
            product=self.product,
            quantite=3000,
            unite=UniteStock.CL,
            seuil_alerte=500,
        )

        # 3 mouvements sans clôture / 3 movements without closure
        MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.VE,
            quantite=-100,
            quantite_avant=3000,
        )
        MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.PE,
            quantite=-50,
            quantite_avant=2900,
            motif="Casse",
        )
        MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.OF,
            quantite=-25,
            quantite_avant=2850,
        )

    def test_generer_resume_cloture(self):
        """generer_resume agrège les mouvements par produit.
        / generer_resume aggregates movements by product."""
        from inventaire.models import MouvementStock
        from inventaire.services import ResumeStockService

        mouvements = MouvementStock.objects.filter(cloture__isnull=True)
        resume = ResumeStockService.generer_resume(mouvements)

        assert len(resume["par_produit"]) == 1

        produit = resume["par_produit"][0]
        assert produit["nom"] == "Bière résumé clôture"
        assert produit["ventes"] == -100
        assert produit["pertes"] == -50
        assert produit["offerts"] == -25
        assert produit["receptions"] == 0
        assert produit["debit_metre"] == 0
        assert produit["ajustements"] == 0

    def test_rattacher_mouvements_a_cloture(self):
        """rattacher_a_cloture lie les mouvements orphelins à la clôture.
        / rattacher_a_cloture links orphan movements to the closure."""
        from django.utils import timezone

        from inventaire.models import MouvementStock
        from inventaire.services import ResumeStockService
        from laboutik.models import ClotureCaisse

        cloture = ClotureCaisse.objects.create(
            datetime_ouverture=timezone.now(),
        )

        nombre = ResumeStockService.rattacher_a_cloture(cloture)
        assert nombre == 3

        # Tous les mouvements sont rattachés / All movements are linked
        orphelins = MouvementStock.objects.filter(cloture__isnull=True).count()
        assert orphelins == 0

        rattaches = MouvementStock.objects.filter(cloture=cloture).count()
        assert rattaches == 3
