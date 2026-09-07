"""
tests/pytest/test_pos_paiement_cheque.py — Encaisser un chèque au point de vente V2.
/ Collecting a check at the V2 point of sale.

LOCALISATION : tests/pytest/test_pos_paiement_cheque.py

POURQUOI CE FICHIER / WHY THIS FILE :
Le chèque est un moyen de paiement vivant du comptoir : `PointDeVente.accepte_cheque`
l'active, le bouton s'affiche, et `_payer_par_carte_ou_cheque` l'encaisse. Il n'avait
pourtant aucun test — ni sur l'encaissement, ni sur son affichage.

Ce fichier couvre l'encaissement. Sa suite comptable — la clôture, les exports et
l'archive fiscale — est dans `test_rapports_cheque.py`, parce que c'est là qu'un chèque
encaissé se perdait.

Le code du moyen de paiement est `"CH"` côté formulaire, et `PaymentMethod.CHEQUE`
(`"CH"` également) en base : la correspondance est faite par `MAPPING_CODES_PAIEMENT`.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_pos_paiement_cheque.py -v
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
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
    Configuration,
    LigneArticle,
    PaymentMethod,
    Price,
    Product,
)
from laboutik.models import PointDeVente


# Le prix de l'article vendu, en euros.
# / Price of the sold article, in euros.
PRIX_ARTICLE_EUROS = Decimal("12.00")


class TestPosPaiementCheque(FastTenantTestCase):
    """
    L'encaissement par chèque au comptoir.
    / Check collection at the counter.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_pos_paiement_cheque"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-pos-paiement-cheque.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = "Test POS Paiement Cheque"

    def setUp(self):
        # Re-poser le search_path apres le rollback du test precedent.
        # / Re-set search_path after the previous test's rollback.
        connection.set_tenant(self.tenant)

        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.save()

        self.categorie = CategorieProduct.objects.create(name="Boissons test cheque POS")
        self.produit = Product.objects.create(
            name="Repas test cheque",
            categorie_article=Product.VENTE,
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
            publish=True,
        )
        self.prix = Price.objects.create(
            product=self.produit,
            name="Menu",
            prix=PRIX_ARTICLE_EUROS,
            publish=True,
        )
        self.point_de_vente = PointDeVente.objects.create(
            name="Comptoir test cheque POS",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            accepte_cheque=True,
        )
        self.point_de_vente.products.add(self.produit)

        self.caissier, _cree = TibilletUser.objects.get_or_create(
            email="caissier-cheque-pos@tibillet.localhost",
            defaults={
                "username": "caissier-cheque-pos@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        self.caissier.client_admin.add(self.tenant)
        self.client_http = TenantClient(self.tenant)
        self.client_http.force_login(self.caissier)

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _donnees_du_panier(self, moyen_paiement):
        """Un article au panier, réglé par le moyen demandé.
        / One article in the cart, paid by the requested method."""
        prix_en_centimes = int(round(self.prix.prix * 100))
        return {
            "uuid_pv": str(self.point_de_vente.uuid),
            "moyen_paiement": moyen_paiement,
            "total": str(prix_en_centimes),
            "given_sum": "",
            f"repid-{self.produit.uuid}--{self.prix.uuid}": "1",
        }

    # ------------------------------------------------------------------ #
    #  T1 — L'encaissement
    # ------------------------------------------------------------------ #

    def test_une_vente_payee_par_cheque_est_encaissee_comme_telle(self):
        """
        Un chèque encaissé doit être reconnaissable en base comme un chèque.

        C'est la condition de tout le reste : le rapport, la clôture et l'archive
        fiscale filtrent sur `payment_method`. Une vente enregistrée sous un autre
        moyen serait comptée dans la mauvaise colonne, sans que rien ne le signale.
        / Everything downstream filters on payment_method: a check recorded under
          another method would be counted in the wrong column, silently.
        """
        reponse = self.client_http.post(
            "/laboutik/paiement/payer/", data=self._donnees_du_panier("CH")
        )

        self.assertEqual(reponse.status_code, 200)

        ligne = LigneArticle.objects.get()
        self.assertEqual(ligne.payment_method, PaymentMethod.CHEQUE)
        self.assertEqual(ligne.amount, int(round(PRIX_ARTICLE_EUROS * 100)))

    # ------------------------------------------------------------------ #
    #  T2 — L'affichage du bouton
    # ------------------------------------------------------------------ #

    def test_le_cheque_est_propose_quand_le_comptoir_laccepte(self):
        """
        Le bouton suit la configuration du point de vente.
        / The button follows the POS configuration.
        """
        reponse = self.client_http.post(
            "/laboutik/paiement/moyens_paiement/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                "total": str(int(round(self.prix.prix * 100))),
                f"repid-{self.produit.uuid}--{self.prix.uuid}": "1",
            },
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertIn("CH", reponse.context["moyens_paiement"])

    def test_le_cheque_disparait_quand_le_comptoir_le_refuse(self):
        """
        Le pendant du test précédent : sans lui, le premier serait vert même si le
        bouton s'affichait toujours, quelle que soit la configuration.
        / Without this counterpart, the previous test would pass even if the button
          were always shown.
        """
        self.point_de_vente.accepte_cheque = False
        self.point_de_vente.save()

        reponse = self.client_http.post(
            "/laboutik/paiement/moyens_paiement/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                "total": str(int(round(self.prix.prix * 100))),
                f"repid-{self.produit.uuid}--{self.prix.uuid}": "1",
            },
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn("CH", reponse.context["moyens_paiement"])
