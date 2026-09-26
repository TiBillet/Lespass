"""
tests/pytest/test_paiement_idempotence.py — Double envoi de payer() : un seul encaissement.
/ Double submit of payer(): charged only once.

LOCALISATION : tests/pytest/test_paiement_idempotence.py

Le serveur pose une cle d'idempotence (cle_idempotence_paiement) quand il affiche
les moyens de paiement. Un double appui sur « Valider » renvoie la MEME cle :
payer() ne doit creer les LigneArticle qu'une seule fois.
Voir _executer_avec_cle_idempotence dans laboutik/views.py.
/ The server puts an idempotency key in the form. A double tap sends the same
key: payer() must create the LigneArticle records only once.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_paiement_idempotence.py -v
"""

import sys

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import re  # noqa: E402
import uuid  # noqa: E402
from decimal import Decimal  # noqa: E402

from django.db import connection  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import CategorieProduct, LigneArticle, Price, Product  # noqa: E402
from laboutik.models import PointDeVente  # noqa: E402


class TestPaiementIdempotence(FastTenantTestCase):
    """Un meme paiement envoye deux fois n'est encaisse qu'une fois.
    / The same payment sent twice is charged once."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_paiement_idempotence"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-paiement-idempotence.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test Paiement Idempotence"

    def setUp(self):
        connection.set_tenant(self.tenant)

        # Active la caisse V2 (le garde HasLaBoutikTerminalAccess l'exige).
        # / Enable V2 POS (required by the HasLaBoutikTerminalAccess guard).
        from BaseBillet.models import Configuration

        config = Configuration.get_solo()
        config.module_monnaie_locale = True
        config.module_caisse = True
        config.save()

        self.categorie = CategorieProduct.objects.create(name="Boissons idempotence")
        self.produit = Product.objects.create(
            name="Biere idempotence",
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
        )
        self.prix = Price.objects.create(
            product=self.produit,
            name="Pinte",
            prix=Decimal("5.00"),
            publish=True,
        )
        self.pv = PointDeVente.objects.create(
            name="Bar idempotence",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.pv.products.add(self.produit)

        self.admin, _created = TibilletUser.objects.get_or_create(
            email="admin-idempotence@tibillet.localhost",
            defaults={
                "username": "admin-idempotence@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        self.admin.client_admin.add(self.tenant)

        self.client_http = TenantClient(self.tenant)
        self.client_http.force_login(self.admin)

    def _poster_paiement_especes(self, cle_idempotence):
        """
        POST payer() : 1 biere a 5 € en especes, compte juste.
        cle_idempotence=None → champ absent (ancien client).
        / POST payer(): 1 beer at 5 € in cash. None → field missing.
        """
        donnees = {
            "uuid_pv": str(self.pv.uuid),
            "moyen_paiement": "espece",
            "total": "500",
            "given_sum": "0",
            f"repid-{self.produit.uuid}--{self.prix.uuid}": "1",
        }
        if cle_idempotence is not None:
            donnees["cle_idempotence_paiement"] = str(cle_idempotence)
        return self.client_http.post("/laboutik/paiement/payer/", data=donnees)

    def _nombre_de_lignes_du_produit(self):
        return LigneArticle.objects.filter(pricesold__price=self.prix).count()

    def test_deux_envois_avec_la_meme_cle_n_encaissent_qu_une_fois(self):
        cle_idempotence = uuid.uuid4()

        premiere_reponse = self._poster_paiement_especes(cle_idempotence)
        assert premiere_reponse.status_code == 200
        nombre_apres_le_premier_envoi = self._nombre_de_lignes_du_produit()
        assert nombre_apres_le_premier_envoi == 1

        deuxieme_reponse = self._poster_paiement_especes(cle_idempotence)
        assert deuxieme_reponse.status_code == 200
        assert self._nombre_de_lignes_du_produit() == nombre_apres_le_premier_envoi

    def test_la_cle_devient_l_uuid_transaction_des_lignes(self):
        cle_idempotence = uuid.uuid4()

        self._poster_paiement_especes(cle_idempotence)

        assert (
            LigneArticle.objects.filter(uuid_transaction=cle_idempotence).count() == 1
        )

    def test_deux_cles_differentes_font_deux_ventes(self):
        self._poster_paiement_especes(uuid.uuid4())
        self._poster_paiement_especes(uuid.uuid4())

        assert self._nombre_de_lignes_du_produit() == 2

    def test_sans_cle_le_paiement_marche_comme_avant(self):
        reponse = self._poster_paiement_especes(None)

        assert reponse.status_code == 200
        assert self._nombre_de_lignes_du_produit() == 1

    def test_une_cle_mal_formee_est_ignoree(self):
        """
        Une cle qui n'est pas un UUID : on paie comme sans cle, sans erreur 500.
        / A non-UUID key: pay as without a key, no 500.
        """
        reponse = self._poster_paiement_especes("pas-un-uuid")

        assert reponse.status_code == 200
        assert self._nombre_de_lignes_du_produit() == 1

    def test_moyens_paiement_pose_une_cle_hors_bande_dans_le_formulaire(self):
        """
        L'ecran des moyens de paiement contient le champ hors bande
        #addition-cle-idempotence avec un UUID.
        / The payment methods screen carries the out-of-band key field.
        """
        donnees = {
            "uuid_pv": str(self.pv.uuid),
            f"repid-{self.produit.uuid}--{self.prix.uuid}": "1",
        }
        reponse = self.client_http.post(
            "/laboutik/paiement/moyens_paiement/", data=donnees
        )
        contenu = reponse.content.decode()

        assert reponse.status_code == 200
        champ_hors_bande = re.search(
            r'id="addition-cle-idempotence"\s+name="cle_idempotence_paiement"\s+'
            r'value="([0-9a-f-]{36})"\s+hx-swap-oob="true"',
            contenu,
        )
        assert champ_hors_bande is not None
