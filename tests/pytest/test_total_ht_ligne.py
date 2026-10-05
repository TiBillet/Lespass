"""
tests/pytest/test_total_ht_ligne.py
Le HT stocke sur chaque ligne de vente de la caisse porte sur la LIGNE entiere.
/ The HT stored on each register sale line covers the WHOLE line.

LOCALISATION : tests/pytest/test_total_ht_ligne.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
La certification LNE (exigence 3) demande de stocker le HT de chaque ligne de
vente (`LigneArticle.total_ht`). Ce HT est scelle dans l'empreinte HMAC de la
ligne et exporte dans l'archive fiscale, avec la TVA stockee de la ligne.

Une ligne vaut `amount x qty` (prix unitaire x quantite). Le HT doit donc etre
calcule sur ce total, pas sur le prix d'un seul article :
3 bieres a 5,00 € TTC, TVA 20 % -> HT 12,50 € (et non 4,17 €).

Les ventes passent par la vraie route de paiement de la caisse, dans un schema de
test dedie : le HT est pose par le code de production, pas par le test.
/ Sales go through the real payment route, in a dedicated test schema.

Lancement / Run:
    make test ARGS="tests/pytest/test_total_ht_ligne.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import csv  # noqa: E402
from datetime import timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest import mock  # noqa: E402

from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

from AuthBillet.models import TibilletUser, Wallet  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    CategorieProduct,
    Configuration,
    LigneArticle,
    Price,
    Product,
    Tva,
)
from QrcodeCashless.models import CarteCashless  # noqa: E402
from fedow_core.models import Asset, Token  # noqa: E402
from fedow_core.services import AssetService  # noqa: E402
from laboutik.models import LaboutikConfiguration, PointDeVente  # noqa: E402

TAUX_TVA_POURCENT = 20


class TestTotalHtDeLaLigne(FastTenantTestCase):
    """Le HT stocke d'une ligne de caisse = HT de amount x qty.
    / The stored HT of a register line = HT of amount x qty."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_total_ht"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-total-ht.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test total HT"

    def setUp(self):
        """Un point de vente, deux articles a TVA 20 %, deux monnaies, une carte.
        / One point of sale, two 20 % VAT items, two currencies, one card."""
        # Le rollback du test precedent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.save()

        # Le singleton de la caisse doit exister en base (PIEGES 9.86).
        # / The register singleton must exist in the database.
        LaboutikConfiguration.get_solo().save()

        # Le taux d'une ligne vient de Product.tva (PIEGES 9.66).
        # / A line's rate comes from Product.tva.
        tva_a_vingt, _cree = Tva.objects.get_or_create(
            tva_rate=Decimal(TAUX_TVA_POURCENT)
        )
        categorie = CategorieProduct.objects.create(name="Boissons total HT")

        self.biere = Product.objects.create(
            name="Biere total HT",
            methode_caisse=Product.VENTE,
            categorie_pos=categorie,
            tva=tva_a_vingt,
        )
        Price.objects.create(product=self.biere, name="Pinte", prix=Decimal("5.00"))

        self.vin = Product.objects.create(
            name="Vin total HT",
            methode_caisse=Product.VENTE,
            categorie_pos=categorie,
            tva=tva_a_vingt,
        )
        Price.objects.create(product=self.vin, name="Bouteille", prix=Decimal("10.00"))

        self.point_de_vente = PointDeVente.objects.create(
            name="Comptoir total HT",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.point_de_vente.products.add(self.biere, self.vin)

        # Deux monnaies : cadeau (TNF, debitee en premier) et locale (TLF).
        # / Two currencies: gift (TNF, debited first) and local (TLF).
        wallet_du_lieu = Wallet.objects.create(
            origin=self.tenant, name="Wallet lieu total HT"
        )
        self.asset_cadeau = AssetService.creer_asset(
            tenant=self.tenant,
            name="Cadeau total HT",
            category=Asset.TNF,
            currency_code="EUR",
            wallet_origin=wallet_du_lieu,
        )
        self.asset_local = AssetService.creer_asset(
            tenant=self.tenant,
            name="Monnaie locale total HT",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=wallet_du_lieu,
        )

        client_de_la_carte = TibilletUser.objects.create(
            email="client-total-ht@tibillet.localhost",
            username="client-total-ht@tibillet.localhost",
        )
        wallet_du_client = Wallet.objects.create(
            origin=self.tenant, name="Wallet client total HT"
        )
        client_de_la_carte.wallet = wallet_du_client
        client_de_la_carte.save()
        self.carte = CarteCashless.objects.create(
            tag_id="THT1AAAA", number="THT1AAAA", user=client_de_la_carte
        )
        Token.objects.create(
            wallet=wallet_du_client, asset=self.asset_cadeau, value=600
        )
        Token.objects.create(
            wallet=wallet_du_client, asset=self.asset_local, value=1000
        )

        # Caissier : admin du lieu, session navigateur.
        # / Cashier: venue admin, browser session.
        caissier, _cree = TibilletUser.objects.get_or_create(
            email="caissier-total-ht@tibillet.localhost",
            defaults={
                "username": "caissier-total-ht@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        caissier.client_admin.add(self.tenant)
        self.navigateur = TenantClient(self.tenant)
        self.navigateur.force_login(caissier)

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _encaisser(
        self, moyen_de_paiement, produit, prix_centimes, quantite, tag_id=None
    ):
        """Encaisse par la VRAIE route de paiement de la caisse.
        / Collects through the REAL register payment route."""
        donnees = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "moyen_paiement": moyen_de_paiement,
            "total": str(prix_centimes * quantite),
            "given_sum": "0",
            f"repid-{produit.uuid}": str(quantite),
        }
        if tag_id is not None:
            donnees["tag_id"] = tag_id

        # Le reseau federe (Fedow distant) est coupe : la cascade reste locale.
        # / The federated network is off: the cascade stays local.
        with (
            mock.patch("laboutik.views.FedowConfig") as configuration_fedow,
            mock.patch("laboutik.views.FedowAPI"),
        ):
            configuration_fedow.get_solo.return_value.can_fedow.return_value = False
            reponse = self.navigateur.post("/laboutik/paiement/payer/", data=donnees)

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        return reponse

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_le_ht_d_une_ligne_porte_sur_toute_la_quantite(self):
        """3 bieres a 5,00 € TTC, TVA 20 % : HT de la ligne = 12,50 €.
        / 3 beers at 5.00 € incl. VAT, 20 %: line HT = 12.50 €."""
        self._encaisser("espece", self.biere, prix_centimes=500, quantite=3)

        ligne = LigneArticle.objects.get(pricesold__productsold__product=self.biere)
        assert ligne.amount == 500
        assert ligne.qty == 3
        assert ligne.total_ht == 1250, f"HT stocke {ligne.total_ht}, attendu 1250"

    def test_le_ht_d_un_paiement_en_cascade(self):
        """Vin a 10,00 € paye 6,00 € cadeau + 4,00 € monnaie locale, TVA 20 %.

        UNE ligne au prix unitaire 1000, quantite 1, part payee en jetons 600. Le champ
        `total_ht` porte le HT du NET vendu. La part payee en jetons cadeau est une
        vente ordinaire a TVA 0 (D8 bis) : HT = 600 + arrondi(400 / 1,2 = 333,33) = 933.
        / ONE line at unit price 1000, token part 600: HT = 600 + 333 = 933.
        """
        self._encaisser(
            "nfc", self.vin, prix_centimes=1000, quantite=1, tag_id=self.carte.tag_id
        )

        lignes = LigneArticle.objects.filter(pricesold__productsold__product=self.vin)
        assert lignes.count() == 1
        ligne_du_vin = lignes.first()
        assert ligne_du_vin.part_en_jetons == 600
        assert ligne_du_vin.total_ht == 933

    def test_l_archive_fiscale_exporte_le_ht_et_la_tva_stockes_de_la_ligne(self):
        """L'archive exporte le HT et la TVA stockés sur l'article : 3 bières à
        5,00 € (TTC 1500) → HT 1250, TVA 1500 − 1250 = 250.
        / The archive exports the item's stored HT and VAT: HT 1250, VAT 250."""
        from laboutik.archivage import generer_fichiers_archive

        maintenant = timezone.now()
        self._encaisser("espece", self.biere, prix_centimes=500, quantite=3)
        ligne = LigneArticle.objects.get(pricesold__productsold__product=self.biere)

        fichiers_de_l_archive = generer_fichiers_archive(
            schema=self.tenant.schema_name,
            debut=maintenant - timedelta(minutes=5),
            fin=maintenant + timedelta(minutes=5),
        )
        texte_des_articles = fichiers_de_l_archive["articles.csv"].decode("utf-8-sig")
        articles_exportes = list(
            csv.DictReader(texte_des_articles.splitlines(), delimiter=";")
        )
        article_de_la_ligne = []
        for article_exporte in articles_exportes:
            if article_exporte["uuid"] == str(ligne.uuid):
                article_de_la_ligne.append(article_exporte)
        assert len(article_de_la_ligne) == 1, articles_exportes
        assert article_de_la_ligne[0]["total_ht"] == "1250"
        assert article_de_la_ligne[0]["total_tva"] == "250"

    def test_la_chaine_hmac_reste_valide(self):
        """Le HT scelle reste coherent avec l'empreinte : la chaine des ventes est
        valide (`verifier_chaine_ventes` ne trouve aucune anomalie).
        / The sealed HT stays consistent with the fingerprint: the sales chain is
        valid."""
        from laboutik.integrity import verifier_chaine_ventes

        self._encaisser("espece", self.biere, prix_centimes=500, quantite=3)
        self._encaisser(
            "nfc", self.vin, prix_centimes=1000, quantite=1, tag_id=self.carte.tag_id
        )

        cle_hmac = LaboutikConfiguration.get_solo().get_or_create_hmac_key()
        anomalies = verifier_chaine_ventes(cle_hmac)
        assert anomalies == [], f"Chaine invalide : {anomalies}"
