"""
tests/pytest/test_paiement_mixte.py — Paiement mixte a la caisse (especes / CB / cheque).
/ Split payment at the POS (cash / card / cheque).

Couvre :
- la tuile MIXTE dans l'ecran des moyens de paiement ;
- l'ecran de repartition (repartir) ;
- payer() avec moyen_paiement=mix : un reglement par moyen, et les refus.
/ Covers the MIXED tile, the split screen, and payer() with moyen_paiement=mix.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_paiement_mixte.py -v
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
    PaymentMethod,
    Price,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Vente
from laboutik.models import PointDeVente


class TestPaiementMixte(FastTenantTestCase):
    """1 classe FastTenantTestCase = 1 schema cree en setUpClass.
    Chaque methode est isolee par rollback.
    / 1 class = 1 schema. Each method is isolated by rollback."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_paiement_mixte"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-paiement-mixte.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = "Test Paiement Mixte"

    def setUp(self):
        """Une biere a 5,50 €, un bar qui accepte especes, CB et cheque.
        / A 5.50 € beer, a bar accepting cash, card and cheque."""
        connection.set_tenant(self.tenant)

        # Active la caisse V2 (le garde HasLaBoutikTerminalAccess l'exige).
        # / Enable the V2 POS (required by the HasLaBoutikTerminalAccess guard).
        from BaseBillet.models import Configuration

        config = Configuration.get_solo()
        config.module_monnaie_locale = True
        config.module_caisse = True
        config.save()

        self.categorie = CategorieProduct.objects.create(name="Boissons Mixte")
        self.produit = Product.objects.create(
            name="Biere Mixte",
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
        )
        self.prix = Price.objects.create(
            product=self.produit,
            name="Pinte",
            prix=Decimal("5.50"),
            publish=True,
        )

        self.pv = PointDeVente.objects.create(
            name="Bar Mixte",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            accepte_cheque=True,
        )
        self.pv.products.add(self.produit)

        self.admin, _created = TibilletUser.objects.get_or_create(
            email="admin-test-mixte@tibillet.localhost",
            defaults={
                "username": "admin-test-mixte@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        self.admin.client_admin.add(self.tenant)

        self.c = TenantClient(self.tenant)
        self.c.force_login(self.admin)

    # ----------------------------------------------------------------------- #
    #  Helpers
    # ----------------------------------------------------------------------- #

    def _post_paiement_mixte(self, repartition, quantite=2):
        """POST payer() en paiement mixte. repartition = {code: centimes}.
        / POST payer() as a split payment. repartition = {code: cents}."""
        data = {
            "uuid_pv": str(self.pv.uuid),
            "moyen_paiement": "mix",
            "total": "0",
            "given_sum": "",
            f"repid-{self.produit.uuid}": str(quantite),
        }
        for code_du_moyen, montant_en_centimes in repartition.items():
            data[f"repartition_{code_du_moyen}"] = str(montant_en_centimes)
        return self.c.post("/laboutik/paiement/payer/", data=data)

    def _nombre_de_ventes_de_caisse(self):
        return LigneArticle.objects.filter(sale_origin=SaleOrigin.LABOUTIK).count()

    # ----------------------------------------------------------------------- #
    #  payer() — cas nominal
    # ----------------------------------------------------------------------- #

    def test_paiement_mixte_especes_et_cb_cree_deux_reglements(self):
        """2 bieres (11 €) payees 4 € en especes et 7 € en CB : la vente est
        encaissee avec un reglement especes de 400 et un reglement CB de 700.
        / 11 € paid 4 € cash + 7 € card: two payments on the settled sale."""
        response = self._post_paiement_mixte({"espece": 400, "carte_bancaire": 700})
        assert response.status_code == 200

        ligne = (
            LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            )
            .order_by("-datetime")
            .first()
        )
        vente = ligne.vente
        assert vente.statut == Vente.Statut.REGLEE

        montants_par_moyen = {}
        for reglement in vente.reglements.all():
            montants_par_moyen[reglement.moyen] = reglement.montant
        assert montants_par_moyen == {
            PaymentMethod.CASH: 400,
            PaymentMethod.CC: 700,
        }

    def test_paiement_mixte_trois_moyens(self):
        """Especes + CB + cheque : trois reglements.
        / Cash + card + cheque: three payments."""
        response = self._post_paiement_mixte(
            {"espece": 100, "carte_bancaire": 500, "CH": 500}
        )
        assert response.status_code == 200

        ligne = (
            LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            )
            .order_by("-datetime")
            .first()
        )
        assert ligne.vente.reglements.count() == 3

    def test_ecran_de_succes_affiche_paiement_mixte(self):
        """L'ecran de succes indique « paiement mixte ».
        / The success screen says "paiement mixte"."""
        response = self._post_paiement_mixte({"espece": 400, "carte_bancaire": 700})
        assert "paiement mixte" in response.content.decode()

    # ----------------------------------------------------------------------- #
    #  payer() — refus (rien n'est ecrit)
    # ----------------------------------------------------------------------- #

    def test_somme_differente_du_total_est_refusee(self):
        """4 € + 5 € pour un panier de 11 € : refus, aucune vente ecrite.
        / Amounts that do not add up to the total: refused, nothing written."""
        response = self._post_paiement_mixte({"espece": 400, "carte_bancaire": 500})
        assert response.status_code == 400
        assert self._nombre_de_ventes_de_caisse() == 0

    def test_un_seul_moyen_est_refuse(self):
        """Tout en especes via le mix : refus (il faut au moins deux moyens).
        / A single method through the mix is refused."""
        response = self._post_paiement_mixte({"espece": 1100})
        assert response.status_code == 400
        assert self._nombre_de_ventes_de_caisse() == 0

    def test_moyen_non_accepte_par_le_point_de_vente_est_refuse(self):
        """Le bar n'accepte plus le cheque : un POST force avec du cheque est refuse.
        / The bar no longer accepts cheques: a forged cheque POST is refused."""
        self.pv.accepte_cheque = False
        self.pv.save()
        response = self._post_paiement_mixte({"espece": 600, "CH": 500})
        assert response.status_code == 400
        assert self._nombre_de_ventes_de_caisse() == 0

    def test_montant_negatif_est_refuse(self):
        """Un montant negatif est refuse par le serializer.
        / A negative amount is refused by the serializer."""
        response = self._post_paiement_mixte({"espece": 1200, "carte_bancaire": -100})
        assert response.status_code == 400
        assert self._nombre_de_ventes_de_caisse() == 0

    # ----------------------------------------------------------------------- #
    #  Tuile MIXTE et ecran de repartition
    # ----------------------------------------------------------------------- #

    def test_tuile_mixte_affichee_avec_plusieurs_moyens(self):
        """Le bar accepte especes, CB et cheque : la tuile MIXTE est affichee.
        / The bar accepts several methods: the MIXED tile shows."""
        response = self.c.post(
            "/laboutik/paiement/moyens_paiement/",
            data={
                "uuid_pv": str(self.pv.uuid),
                f"repid-{self.produit.uuid}": "1",
            },
        )
        assert response.status_code == 200
        assert 'data-testid="paiement-btn-mixte"' in response.content.decode()

    def test_tuile_mixte_absente_avec_un_seul_moyen(self):
        """Le bar n'accepte que les especes : pas de tuile MIXTE.
        / Cash only: no MIXED tile."""
        self.pv.accepte_carte_bancaire = False
        self.pv.accepte_cheque = False
        self.pv.save()
        response = self.c.post(
            "/laboutik/paiement/moyens_paiement/",
            data={
                "uuid_pv": str(self.pv.uuid),
                f"repid-{self.produit.uuid}": "1",
            },
        )
        assert response.status_code == 200
        assert "paiement-btn-mixte" not in response.content.decode()

    def test_ecran_de_repartition_affiche_une_ligne_par_moyen(self):
        """repartir() affiche une ligne par moyen recu, et ignore le cashless.
        / repartir() shows one row per method received, and ignores cashless."""
        response = self.c.get(
            "/laboutik/paiement/repartir/?total=11,00&moyens=espece,carte_bancaire,nfc"
        )
        assert response.status_code == 200
        contenu = response.content.decode()
        assert 'data-testid="mixte-ligne-espece"' in contenu
        assert 'data-testid="mixte-ligne-carte_bancaire"' in contenu
        assert "mixte-ligne-CH" not in contenu
        assert "mixte-ligne-nfc" not in contenu
        assert 'data-total-en-centimes="1100"' in contenu
