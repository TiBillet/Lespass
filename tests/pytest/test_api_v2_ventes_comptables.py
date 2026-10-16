"""
tests/pytest/test_api_v2_ventes_comptables.py
Les ventes d'une clôture J pour un logiciel de facturation (Dolibarr) :
`GET /api/v2/closures/<uuid>/sales/`.
/ A J closure's sales for an invoicing software.

LOCALISATION : tests/pytest/test_api_v2_ventes_comptables.py

RÈGLES MÉTIER TESTÉES (spec TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-06-connecteurs-
comptables/CHANTIER-06-D-ventes.md, D2, D19, Q4, Q7 ; contrat : CHANTIER-06-D-PLAN.md,
tâche 4)
- Le droit : la clé doit avoir « comptabilité » ET « ventes » (la route publie l'e-mail
  des acheteurs).
- Mêmes refus que `entries` : 404 pour une J inconnue ou sans ventes.
- Une vente publiée : numéro, nature, client (uuid et e-mail SEULS), lignes au tarif
  (uuid du `Price` = `ref_ext` du produit Dolibarr), paiements, virements, paiements
  divers ; montants en centimes ; comptes par leur numéro.
- Pagination par `after_number` (numéro de vente) et `limit`, `nextAfterNumber`.
- Une vente sans montant n'est pas publiée ; des règlements qui ne couvrent pas les
  articles : 409, avec le numéro de la vente.
- Un nombre de requêtes qui ne grandit pas avec le nombre de ventes.
/ Business rules tested: key rights, refusals, published sale, pagination, empty
sales, mismatch, fixed query count.

Schéma dédié (`FastTenantTestCase`) : une clôture lit TOUTES les ventes du lieu.
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import uuid  # noqa: E402
from datetime import datetime, time  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.db import connection  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402
from rest_framework_api_key.models import APIKey  # noqa: E402

import comptabilite.tasks  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    CategorieProduct,
    Configuration,
    ExternalApiKey,
    PaymentMethod,
    Product,
    SaleOrigin,
)
from comptabilite.models import ClotureCaisse  # noqa: E402
from fabriques_panier import creer_utilisateur, identifiant_unique  # noqa: E402
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from fedow_core.models import Asset  # noqa: E402
from AuthBillet.models import Wallet  # noqa: E402
from laboutik.models import CompteComptable, LaboutikConfiguration  # noqa: E402

FUSEAU_DE_PARIS = ZoneInfo("Europe/Paris")

DOMAINE_DU_LIEU_DE_TEST = "test-api-ventes-comptables.tibillet.localhost"

MOMENT_DES_VENTES = datetime(2026, 3, 10, 20, 0, tzinfo=FUSEAU_DE_PARIS)
MOMENT_DU_Z = datetime(2026, 3, 10, 23, 0, tzinfo=FUSEAU_DE_PARIS)


class TestApiVentesComptables(FastTenantTestCase):
    """
    La route des ventes d'une J (fiche 06-D).
    / The route of a J's sales.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_api_ventes_comptables"

    @classmethod
    def get_test_tenant_domain(cls):
        return DOMAINE_DU_LIEU_DE_TEST

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test API ventes comptables"

    def setUp(self):
        """
        Le lieu de test (Paris, fermeture à 2 h), une bière à 5,00 € rangée dans une
        catégorie reliée au 707000, la clé de Dolibarr (comptabilité + ventes) et le
        client HTTP.
        / The test venue, a 5.00 € beer, Dolibarr's key and the HTTP client.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)
        LaboutikConfiguration.get_solo().save()

        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.heure_de_fermeture = time(2, 0)
        configuration.rapport_emails = ""
        configuration.rapport_periodicite = Configuration.PERIODICITE_NONE
        configuration.save()

        categorie_des_boissons = CategorieProduct.objects.create(
            name=f"Boissons {identifiant_unique()}",
            compte_comptable=CompteComptable.objects.get(numero_de_compte="707000"),
        )
        self.tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere",
            prix_en_euros="5.00",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )
        produit = self.tarif_de_la_biere.productsold.product
        produit.categorie_pos = categorie_des_boissons
        produit.save()

        self.cle_de_dolibarr = self._creer_une_cle_d_api(
            droit_comptabilite=True, droit_ventes=True
        )
        self.client = APIClient()
        self.client.defaults["HTTP_HOST"] = DOMAINE_DU_LIEU_DE_TEST

    # ------------------------------------------------------------------
    # Outils du test
    # / Test helpers
    # ------------------------------------------------------------------

    def _creer_une_cle_d_api(self, droit_comptabilite, droit_ventes):
        """Une clé du lieu avec ces droits ; rend son texte. / A key; returns its text."""
        nom_de_la_cle = f"ventes-{identifiant_unique()}"
        cle_technique, texte_de_la_cle = APIKey.objects.create_key(name=nom_de_la_cle)
        ExternalApiKey.objects.create(
            name=nom_de_la_cle,
            key=cle_technique,
            comptabilite=droit_comptabilite,
            sale=droit_ventes,
        )
        return texte_de_la_cle

    def _lire(self, adresse, cle=None):
        """Un GET avec la clé de Dolibarr (ou une autre). / A GET with a key."""
        cle_a_utiliser = cle if cle is not None else self.cle_de_dolibarr
        return self.client.get(adresse, HTTP_AUTHORIZATION=f"Api-Key {cle_a_utiliser}")

    def _heure_figee(self, moment):
        """Remplace l'heure de Django par `moment`. / Freezes Django's clock."""
        return patch("django.utils.timezone.now", return_value=moment)

    def _vendre_des_bieres(self, nombre_de_ventes, client=None, offert=False):
        """
        `nombre_de_ventes` ventes d'une bière en espèces, à 20 h. Rend la liste.
        / Several cash beer sales at 8 pm.
        """
        ventes = []
        with self._heure_figee(MOMENT_DES_VENTES):
            for _numero in range(nombre_de_ventes):
                article = {
                    "pricesold": self.tarif_de_la_biere,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                }
                reglements = [{"moyen": PaymentMethod.CASH, "montant": 500}]
                if offert:
                    article["offert_en_totalite"] = True
                    reglements = None
                vente = fabriquer_vente_encaissee(
                    origine=SaleOrigin.LABOUTIK,
                    articles=[article],
                    reglements=reglements,
                    client=client,
                )
                verifier_egalites(vente)
                ventes.append(vente)
        return ventes

    def _cloturer_la_journee(self):
        """La J à 23 h. / The J at 11 pm."""
        with self._heure_figee(MOMENT_DU_Z):
            uuid_de_la_cloture = comptabilite.tasks.generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            )
        return ClotureCaisse.objects.get(uuid=uuid_de_la_cloture)

    def _adresse(self, cloture, parametres=""):
        """L'adresse des ventes d'une J. / The route of a J's sales."""
        return f"/api/v2/closures/{cloture.uuid}/sales/{parametres}"

    # ------------------------------------------------------------------
    # Le droit et les refus / The right and refusals
    # ------------------------------------------------------------------

    def test_comptabilite_seule_refusee_avec_ventes_acceptee(self):
        """
        Une clé « comptabilité » seule : 403. Une clé « ventes » seule : 403. Les
        deux : 200.
        / Accounting alone or sales alone: 403; both: 200.
        """
        self._vendre_des_bieres(1)
        cloture = self._cloturer_la_journee()
        cle_comptable_seule = self._creer_une_cle_d_api(True, False)
        cle_ventes_seule = self._creer_une_cle_d_api(False, True)

        assert (
            self._lire(self._adresse(cloture), cle=cle_comptable_seule).status_code
            == 403
        )
        assert (
            self._lire(self._adresse(cloture), cle=cle_ventes_seule).status_code == 403
        )
        assert self._lire(self._adresse(cloture)).status_code == 200

    def test_j_inconnue_404(self):
        """
        Un uuid inconnu : 404 `not_exportable`, comme `entries`.
        / An unknown uuid: 404, like entries.
        """
        reponse = self._lire(f"/api/v2/closures/{uuid.uuid4()}/sales/")

        assert reponse.status_code == 404
        assert reponse.json()["code"] == "not_exportable"

    # ------------------------------------------------------------------
    # Une vente publiée / A published sale
    # ------------------------------------------------------------------

    def test_une_vente_en_especes_publiee(self):
        """
        Une bière en espèces : numéro, nature, client nul, une ligne au tarif vendu,
        un paiement de 500 au 530000, rien d'autre ; en-tête de la J.
        / A cash beer: number, nature, no customer, one line, one payment.
        """
        vente = self._vendre_des_bieres(1)[0]
        cloture = self._cloturer_la_journee()

        reponse = self._lire(self._adresse(cloture))

        assert reponse.status_code == 200, reponse.content
        donnees = reponse.json()
        assert donnees["closure"] == str(cloture.uuid)
        assert donnees["number"] == cloture.numero_sequentiel
        assert donnees["accountingDate"] == "2026-03-10"
        assert donnees["amountUnit"] == "cent"
        assert donnees["nextAfterNumber"] is None
        assert len(donnees["results"]) == 1
        vente_publiee = donnees["results"][0]
        assert vente_publiee["identifier"] == str(vente.uuid)
        assert vente_publiee["orderNumber"] == vente.numero
        assert vente_publiee["nature"] == "sale"
        assert vente_publiee["customer"] is None
        assert vente_publiee["relatedSale"] is None
        assert vente_publiee["orderedItem"] == [
            {
                "priceIdentifier": str(self.tarif_de_la_biere.price.uuid),
                "name": f"{self.tarif_de_la_biere.price.product.name} — {self.tarif_de_la_biere.price.name}",
                "quantity": "1.000000",
                "unitPrice": 500,
                "totalTTC": 500,
                "totalHT": 417,
                "totalVAT": 83,
                "vatRate": "20.00",
                "accountingAccount": "707000",
                "vatAccountingAccount": "445711",
            }
        ]
        assert vente_publiee["invoicePayments"] == [
            {
                "treasuryAccount": "530000",
                "method": "CA",
                "amount": 500,
            }
        ]
        assert vente_publiee["transfers"] == []
        assert vente_publiee["variousPayments"] == []

    def test_client_publie_par_son_email_seul(self):
        """
        Une vente avec une cliente : `customer` = son uuid et son e-mail, rien d'autre
        (spec Q4).
        / A sale with a customer: uuid and e-mail only.
        """
        acheteuse = creer_utilisateur()
        acheteuse.first_name = "Alice"
        acheteuse.last_name = "Martin"
        acheteuse.save()
        self._vendre_des_bieres(1, client=acheteuse)
        cloture = self._cloturer_la_journee()

        vente_publiee = self._lire(self._adresse(cloture)).json()["results"][0]

        assert vente_publiee["customer"] == {
            "identifier": str(acheteuse.pk),
            "email": acheteuse.email,
        }

    def test_recharge_publiee_en_virement(self):
        """
        Une recharge de 10,00 € en espèces : pas de ligne, un virement 419100 → 530000
        avec les libellés des comptes.
        / A cash top-up: no line, one transfer.
        """
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="10.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )
        with self._heure_figee(MOMENT_DES_VENTES):
            vente = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": tarif_de_la_recharge,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 1000,
                        "taux_tva": Decimal("0"),
                    }
                ],
                reglements=[{"moyen": PaymentMethod.CASH, "montant": 1000}],
            )
            verifier_egalites(vente)
        cloture = self._cloturer_la_journee()

        vente_publiee = self._lire(self._adresse(cloture)).json()["results"][0]

        assert vente_publiee["orderedItem"] == []
        assert vente_publiee["invoicePayments"] == []
        assert len(vente_publiee["transfers"]) == 1
        virement = vente_publiee["transfers"][0]
        assert (virement["fromAccount"], virement["toAccount"], virement["amount"]) == (
            "419100",
            "530000",
            1000,
        )
        assert virement["fromMethod"] is None
        assert virement["toMethod"] == "CA"
        assert virement["label"] == "Recharge cashless"

    # ------------------------------------------------------------------
    # Pagination, ventes vides, refus / Pagination, empty sales, refusals
    # ------------------------------------------------------------------

    def test_pagination_after_number_et_limit(self):
        """
        Trois ventes, `limit=2` : deux ventes et `nextAfterNumber` = numéro de la
        deuxième ; puis la troisième et `nextAfterNumber` nul.
        / Three sales, limit=2: two then one.
        """
        ventes = self._vendre_des_bieres(3)
        cloture = self._cloturer_la_journee()

        premiere_page = self._lire(self._adresse(cloture, "?limit=2")).json()
        numero_du_curseur = premiere_page["nextAfterNumber"]
        seconde_page = self._lire(
            self._adresse(cloture, f"?limit=2&after_number={numero_du_curseur}")
        ).json()

        assert [v["orderNumber"] for v in premiere_page["results"]] == [
            ventes[0].numero,
            ventes[1].numero,
        ]
        assert numero_du_curseur == ventes[1].numero
        assert [v["orderNumber"] for v in seconde_page["results"]] == [ventes[2].numero]
        assert seconde_page["nextAfterNumber"] is None

    def test_after_number_ou_limit_invalide_400(self):
        """
        `after_number=-1`, `limit=0` ou `limit=5000` : 400.
        / Invalid cursor or limit: 400.
        """
        self._vendre_des_bieres(1)
        cloture = self._cloturer_la_journee()

        for parametres in [
            "?after_number=-1",
            "?limit=0",
            "?limit=5000",
            "?limit=deux",
        ]:
            assert self._lire(self._adresse(cloture, parametres)).status_code == 400, (
                parametres
            )

    def test_vente_sans_montant_absente(self):
        """
        Une bière offerte (rien à écrire) puis une bière en espèces : seule la seconde
        est publiée.
        / A gifted beer is not published.
        """
        self._vendre_des_bieres(1, offert=True)
        vente_payee = self._vendre_des_bieres(1)[0]
        cloture = self._cloturer_la_journee()

        resultats = self._lire(self._adresse(cloture)).json()["results"]

        assert [v["orderNumber"] for v in resultats] == [vente_payee.numero]

    def test_reglements_qui_ne_couvrent_pas_les_articles_409(self):
        """
        Une bière payée en points (sans compte) : 409 `unbalanced_entry`, la phrase
        nomme la vente.
        / A beer paid in points: 409 naming the sale.
        """
        portefeuille = Wallet.objects.create(
            name=f"Portefeuille {identifiant_unique()}"
        )
        points = Asset.objects.create(
            name=f"Points {identifiant_unique()}",
            currency_code="EUR",
            category=Asset.FID,
            tenant_origin=self.tenant,
            wallet_origin=portefeuille,
        )
        with self._heure_figee(MOMENT_DES_VENTES):
            vente = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": self.tarif_de_la_biere,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 500,
                        "taux_tva": Decimal("20"),
                    }
                ],
                reglements=[
                    {
                        "moyen": PaymentMethod.NON_MONETAIRE,
                        "montant": 500,
                        "asset": points.uuid,
                    }
                ],
            )
        cloture = self._cloturer_la_journee()

        reponse = self._lire(self._adresse(cloture))

        assert reponse.status_code == 409
        assert reponse.json()["code"] == "unbalanced_entry"
        assert f"n° {vente.numero}" in reponse.json()["detail"]

    def test_nombre_de_requetes_fixe(self):
        """
        Une J d'une vente, puis une J de cinq ventes avec clients : le même nombre de
        requêtes.
        / One sale then five sales: the same query count.
        """
        self._vendre_des_bieres(1)
        premiere_j = self._cloturer_la_journee()
        self._lire(self._adresse(premiere_j))
        with CaptureQueriesContext(connection) as requetes_d_une_vente:
            self._lire(self._adresse(premiere_j))

        with self._heure_figee(datetime(2026, 3, 11, 20, 0, tzinfo=FUSEAU_DE_PARIS)):
            for _numero in range(5):
                fabriquer_vente_encaissee(
                    origine=SaleOrigin.LABOUTIK,
                    articles=[
                        {
                            "pricesold": self.tarif_de_la_biere,
                            "quantite": Decimal("1"),
                            "prix_unitaire": 500,
                            "taux_tva": Decimal("20"),
                        }
                    ],
                    reglements=[{"moyen": PaymentMethod.CASH, "montant": 500}],
                    client=creer_utilisateur(),
                )
        with self._heure_figee(datetime(2026, 3, 11, 23, 0, tzinfo=FUSEAU_DE_PARIS)):
            uuid_de_la_seconde = comptabilite.tasks.generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            )
        seconde_j = ClotureCaisse.objects.get(uuid=uuid_de_la_seconde)
        self._lire(self._adresse(seconde_j))
        with CaptureQueriesContext(connection) as requetes_de_cinq_ventes:
            reponse = self._lire(self._adresse(seconde_j))

        assert len(reponse.json()["results"]) == 5
        assert len(requetes_de_cinq_ventes) == len(requetes_d_une_vente), [
            requete["sql"][:100] for requete in requetes_de_cinq_ventes.captured_queries
        ]
