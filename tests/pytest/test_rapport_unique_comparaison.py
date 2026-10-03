"""
tests/pytest/test_rapport_unique_comparaison.py
Le nouveau rapport des ventes et l'ancien rapport de caisse donnent les mêmes totaux sur
les trois paiements que l'ancien calculait juste : espèces, CB, carte NFC d'une seule
monnaie.
/ The new sales report and the old register report give the same totals on the three
payments the old one computed right: cash, bank card, single-currency NFC card.

LOCALISATION : tests/pytest/test_rapport_unique_comparaison.py

RÈGLE MÉTIER TESTÉE (fiche F §5)
Le nouveau rapport (`comptabilite/rapport.py`, `RapportDesVentes`) remplace l'ancien
rapport de caisse (`laboutik/reports.py`, `RapportComptableService`). Sur une vente que
l'ancien calculait juste, les deux donnent :
- les mêmes totaux TTC, HT et TVA, au total et par taux ;
- les mêmes règlements par moyen : espèces, CB, chèque, cashless (monnaie locale et
  jetons cadeau, par nom de monnaie), fédéré.
Les ventes que l'ancien calculait faux (troncatures, recharges dans le chiffre
d'affaires, jetons comptés en argent…) ne sont pas comparées ici : les valeurs exactes
de `test_rapport_unique.py` tiennent ce rôle.
/ Same revenue totals (overall and by rate) and same payments by method in both engines.

Trois paiements, par la vraie route de paiement de la caisse :
1. trois jus à 3,50 € en espèces ;
2. trois jus à 3,50 € en CB ;
3. trois jus à 3,50 € payés par la carte du client, qui porte assez de monnaie locale.

CORRESPONDANCE DES DEUX RAPPORTS
    ancien `calculer_tva()`               nouveau `section_chiffre_affaires()`
        "20.00%" → total_ttc, total_ht,       par_taux["20.00"] → total_ttc_en_centimes,
                   total_tva                                      total_ht_en_centimes,
                                                                  total_tva_en_centimes
    ancien `calculer_totaux_par_moyen()`  nouveau `section_reglements()`
        especes                               argent.par_moyen["CA"]
        carte_bancaire                        argent.par_moyen["CC"]
        cheque                                argent.par_moyen["CH"]
        cashless (LE + LG)                    cashless.par_moyen["LE"] + ["LG"]
        cashless_detail [{nom, montant}]      cashless.par_moyen[…].par_monnaie {nom, total}
        federe                                cashless.par_moyen["SF"]
        total                                 argent.total + cashless.total
    ancien `calculer_solde_caisse()`      nouveau `section_caisse_especes()` (espèces)
        fond_de_caisse                        fond_de_caisse_en_centimes
        entrees_especes                       reçues + rendues + corrections
        sorties_especes, solde                sorties_en_centimes, solde_theorique_…
Un moyen absent vaut 0 dans les deux.

SCHÉMA DÉDIÉ
Les deux rapports lisent TOUTES les ventes du lieu sur la période : il faut un lieu qui
ne contient que la vente du test (`FastTenantTestCase`, tronc §8.5). Chaque test annule
sa transaction à la fin. Le singleton `LaboutikConfiguration` est créé en base
(tests/PIEGES.md 9.86) : sans lui, la clé de l'empreinte de la vente échoue. Les cartes
NFC sont dans le schéma `public` (tests/PIEGES.md 9.30) : elles sont créées dans la
transaction du test, donc annulées avec elle. Le réseau Fedow distant est coupé
(`can_fedow` faux) : la carte est débitée en local, aucun appel réseau.
/ Dedicated schema, rolled back after each test; the remote Fedow network is off.

Modèle : tests/pytest/test_caisse_anciens_rapports.py (même route, mêmes gestes).
Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-F-rapport-unique.md (§5).

Lancer / Run : make test ARGS="tests/pytest/test_rapport_unique_comparaison.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import uuid  # noqa: E402
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
    Price,
    Product,
    Tva,
)
from BaseBillet.models_vente import Vente  # noqa: E402
from comptabilite.rapport import RapportDesVentes  # noqa: E402
from fabriques_vente import verifier_egalites  # noqa: E402
from fedow_core.models import Asset, Token  # noqa: E402
from fedow_core.services import AssetService  # noqa: E402
from laboutik.models import LaboutikConfiguration, PointDeVente  # noqa: E402
from laboutik.reports import RapportComptableService  # noqa: E402
from QrcodeCashless.models import CarteCashless  # noqa: E402

# Adresse du paiement de la caisse (laboutik/urls.py).
# / Cash register payment address.
URL_DU_PAIEMENT_CAISSE = "/laboutik/paiement/payer/"

# Noms lus tels quels dans les rapports (catégorie, produit, monnaie).
# / Names read as they are in the reports.
NOM_DE_LA_CATEGORIE = "Boissons comparaison"
NOM_DU_JUS = "Jus comparaison"
NOM_DE_LA_MONNAIE_LOCALE = "Monnaie locale comparaison"

# Le taux du jus, tel que chaque rapport l'écrit dans sa clé.
# / The juice rate, as each report writes it in its key.
TAUX_DANS_L_ANCIEN_RAPPORT = "20.00%"
TAUX_DANS_LE_NOUVEAU_RAPPORT = "20.00"


class TestRapportUniqueComparaison(FastTenantTestCase):
    """
    Le nouveau rapport et l'ancien rapport de caisse donnent les mêmes totaux (fiche F
    §5).
    / The new report and the old register report give the same totals.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_rapport_unique_comparaison"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-rapport-unique-comparaison.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test rapport unique comparaison"

    def setUp(self):
        """
        Un comptoir, un jus à 3,50 € (TVA 20 %), la monnaie locale du lieu, un caissier
        connecté, la période des rapports.
        / A counter, a juice (20 % VAT), the venue currency, a cashier, the period.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Schéma dédié : on peut enregistrer la configuration de CE lieu de test.
        # / Dedicated schema: this test venue's configuration can be saved.
        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.save()

        # Le singleton de la caisse doit exister en base (tests/PIEGES.md 9.86).
        # / The register singleton must exist in the database.
        LaboutikConfiguration.get_solo().save()

        # Le taux d'une ligne de caisse vient de `Product.tva`.
        # / A register line's rate comes from Product.tva.
        tva_a_vingt_pour_cent, _tva_creee = Tva.objects.get_or_create(
            tva_rate=Decimal("20")
        )
        categorie = CategorieProduct.objects.create(name=NOM_DE_LA_CATEGORIE)
        self.jus = Product.objects.create(
            name=NOM_DU_JUS,
            methode_caisse=Product.VENTE,
            categorie_pos=categorie,
            tva=tva_a_vingt_pour_cent,
        )
        self.tarif_du_jus = Price.objects.create(
            product=self.jus, name="Verre", prix=Decimal("3.50"), publish=True
        )

        self.point_de_vente = PointDeVente.objects.create(
            name="Comptoir comparaison",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.point_de_vente.products.add(self.jus)

        portefeuille_du_lieu = Wallet.objects.create(
            origin=self.tenant, name="Wallet lieu comparaison"
        )
        self.monnaie_locale = AssetService.creer_asset(
            tenant=self.tenant,
            name=NOM_DE_LA_MONNAIE_LOCALE,
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=portefeuille_du_lieu,
        )

        # Le caissier : un administrateur du lieu, connecté (sans carte primaire).
        # / The cashier: a logged-in venue admin (no primary card).
        caissier, _caissier_cree = TibilletUser.objects.get_or_create(
            email="caissier-comparaison@tibillet.localhost",
            defaults={
                "username": "caissier-comparaison@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        caissier.client_admin.add(self.tenant)
        self.navigateur_du_caissier = TenantClient(self.tenant)
        self.navigateur_du_caissier.force_login(caissier)

        # La période des rapports, large des deux côtés : l'heure de la machine ne
        # change rien au résultat.
        # / The report period, wide on both sides.
        self.debut_de_la_periode = timezone.now() - timedelta(hours=1)
        self.fin_de_la_periode = timezone.now() + timedelta(hours=1)

    # ------------------------------------------------------------------
    # Gestes du caissier
    # / Cashier actions
    # ------------------------------------------------------------------

    def _carte_du_client(self, identifiant_de_la_carte, solde_en_monnaie_locale):
        """
        Une carte NFC anonyme dont le portefeuille porte un solde en monnaie locale.
        `tag_id` et `number` font 8 caractères au plus (tests/PIEGES.md 9.31).
        / An anonymous NFC card whose wallet holds a local currency balance.
        """
        portefeuille_de_la_carte = Wallet.objects.create(
            origin=self.tenant, name=f"Wallet carte {identifiant_de_la_carte}"
        )
        carte = CarteCashless.objects.create(
            tag_id=identifiant_de_la_carte,
            number=identifiant_de_la_carte,
            uuid=uuid.uuid4(),
            wallet_ephemere=portefeuille_de_la_carte,
        )
        Token.objects.create(
            wallet=portefeuille_de_la_carte,
            asset=self.monnaie_locale,
            value=solde_en_monnaie_locale,
        )
        return carte

    def _payer_trois_jus(self, moyen_de_paiement, carte=None):
        """
        Le caissier encaisse trois jus par la vraie route de paiement, le réseau Fedow
        distant coupé (la carte est débitée en local). Rend la clé d'idempotence du
        paiement.
        / The cashier collects three juices through the real payment route.

        :param moyen_de_paiement: code de la caisse : "espece", "carte_bancaire", "nfc"
        :param carte: la carte du client pour un paiement "nfc", sinon None
        """
        cle_d_idempotence = str(uuid.uuid4())
        donnees_du_formulaire = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "moyen_paiement": moyen_de_paiement,
            "total": "0",
            "given_sum": "0",
            "cle_idempotence_paiement": cle_d_idempotence,
            f"repid-{self.jus.uuid}--{self.tarif_du_jus.uuid}": "3",
        }
        if carte is not None:
            donnees_du_formulaire["tag_id"] = carte.tag_id

        with (
            mock.patch("laboutik.views.FedowConfig") as configuration_fedow,
            mock.patch("laboutik.views.FedowAPI"),
        ):
            configuration_fedow.get_solo.return_value.can_fedow.return_value = False
            reponse = self.navigateur_du_caissier.post(
                URL_DU_PAIEMENT_CAISSE, donnees_du_formulaire
            )

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        return cle_d_idempotence

    def _verifier_la_vente_de_la_cle(self, cle_d_idempotence):
        """
        La caisse a écrit UNE vente pour ce paiement, et ses deux égalités tiennent.
        / The register wrote ONE sale for this payment, and its equalities hold.
        """
        ventes_de_la_cle = list(Vente.objects.filter(idempotency_key=cle_d_idempotence))
        assert len(ventes_de_la_cle) == 1, (
            f"Attendu : une vente pour la clé {cle_d_idempotence}, "
            f"trouvé : {len(ventes_de_la_cle)}."
        )
        verifier_egalites(ventes_de_la_cle[0])

    # ------------------------------------------------------------------
    # Lecture et comparaison des deux rapports
    # / Reading and comparing both reports
    # ------------------------------------------------------------------

    def _chiffre_affaires_des_deux_rapports(self):
        """
        Le chiffre d'affaires de chaque rapport, ramené à la même forme : pour chaque
        taux, et au total, (TTC, HT, TVA) en centimes.
        / Each report's revenue in the same shape: (TTC, HT, VAT) per rate and in total.
        """
        ancien_rapport = RapportComptableService(
            self.point_de_vente, self.debut_de_la_periode, self.fin_de_la_periode
        )
        nouveau_rapport = RapportDesVentes(
            self.debut_de_la_periode, self.fin_de_la_periode
        )

        tva_de_l_ancien = ancien_rapport.calculer_tva()
        ancien_par_taux = {}
        ancien_total_ttc = 0
        ancien_total_ht = 0
        ancien_total_tva = 0
        for taux_de_l_ancien, ligne_du_taux in tva_de_l_ancien.items():
            ancien_par_taux[taux_de_l_ancien] = (
                ligne_du_taux["total_ttc"],
                ligne_du_taux["total_ht"],
                ligne_du_taux["total_tva"],
            )
            ancien_total_ttc += ligne_du_taux["total_ttc"]
            ancien_total_ht += ligne_du_taux["total_ht"]
            ancien_total_tva += ligne_du_taux["total_tva"]

        chiffre_affaires_du_nouveau = nouveau_rapport.section_chiffre_affaires()
        nouveau_par_taux = {}
        for taux_du_nouveau, ligne_du_taux in chiffre_affaires_du_nouveau[
            "par_taux"
        ].items():
            nouveau_par_taux[taux_du_nouveau] = (
                ligne_du_taux["total_ttc_en_centimes"],
                ligne_du_taux["total_ht_en_centimes"],
                ligne_du_taux["total_tva_en_centimes"],
            )
        nouveau_total = (
            chiffre_affaires_du_nouveau["total_ttc_en_centimes"],
            chiffre_affaires_du_nouveau["total_ht_en_centimes"],
            chiffre_affaires_du_nouveau["total_tva_en_centimes"],
        )
        return {
            "ancien_par_taux": ancien_par_taux,
            "ancien_total": (ancien_total_ttc, ancien_total_ht, ancien_total_tva),
            "nouveau_par_taux": nouveau_par_taux,
            "nouveau_total": nouveau_total,
        }

    def _reglements_des_deux_rapports(self):
        """
        Les règlements de chaque rapport, ramenés à la même forme (voir la
        correspondance en tête du fichier) : un montant par moyen, le total, et le
        cashless par nom de monnaie.
        / Each report's payments in the same shape: one amount per method, the total,
        and cashless by currency name.
        """
        ancien_rapport = RapportComptableService(
            self.point_de_vente, self.debut_de_la_periode, self.fin_de_la_periode
        )
        nouveau_rapport = RapportDesVentes(
            self.debut_de_la_periode, self.fin_de_la_periode
        )

        totaux_de_l_ancien = ancien_rapport.calculer_totaux_par_moyen()
        cashless_de_l_ancien_par_nom = {}
        for ligne_de_la_monnaie in totaux_de_l_ancien["cashless_detail"]:
            cashless_de_l_ancien_par_nom[ligne_de_la_monnaie["nom"]] = (
                ligne_de_la_monnaie["montant"]
            )
        reglements_de_l_ancien = {
            "especes": totaux_de_l_ancien["especes"],
            "carte_bancaire": totaux_de_l_ancien["carte_bancaire"],
            "cheque": totaux_de_l_ancien["cheque"],
            "cashless": totaux_de_l_ancien["cashless"],
            "cashless_par_nom": cashless_de_l_ancien_par_nom,
            "federe": totaux_de_l_ancien["federe"],
            "total": totaux_de_l_ancien["total"],
        }

        reglements_du_nouveau = nouveau_rapport.section_reglements()
        argent_par_moyen = reglements_du_nouveau["argent"]["par_moyen"]
        cashless_par_moyen = reglements_du_nouveau["cashless"]["par_moyen"]

        cashless_du_nouveau_par_nom = {}
        for code_du_moyen in ["LE", "LG"]:
            if code_du_moyen not in cashless_par_moyen:
                continue
            for ligne_de_la_monnaie in cashless_par_moyen[code_du_moyen][
                "par_monnaie"
            ].values():
                nom_de_la_monnaie = ligne_de_la_monnaie["nom"]
                if nom_de_la_monnaie not in cashless_du_nouveau_par_nom:
                    cashless_du_nouveau_par_nom[nom_de_la_monnaie] = 0
                cashless_du_nouveau_par_nom[nom_de_la_monnaie] += ligne_de_la_monnaie[
                    "total_en_centimes"
                ]

        reglements_du_nouveau_meme_forme = {
            "especes": self._montant_du_moyen(argent_par_moyen, "CA"),
            "carte_bancaire": self._montant_du_moyen(argent_par_moyen, "CC"),
            "cheque": self._montant_du_moyen(argent_par_moyen, "CH"),
            "cashless": self._montant_du_moyen(cashless_par_moyen, "LE")
            + self._montant_du_moyen(cashless_par_moyen, "LG"),
            "cashless_par_nom": cashless_du_nouveau_par_nom,
            "federe": self._montant_du_moyen(cashless_par_moyen, "SF"),
            "total": reglements_du_nouveau["argent"]["total_en_centimes"]
            + reglements_du_nouveau["cashless"]["total_en_centimes"],
        }
        return reglements_de_l_ancien, reglements_du_nouveau_meme_forme

    def _montant_du_moyen(self, lignes_par_moyen, code_du_moyen):
        """
        Le total d'un moyen dans un bloc du nouveau rapport, 0 s'il est absent (le
        nouveau rapport n'écrit pas un moyen sans règlement ; l'ancien l'écrit à 0).
        / A method's total in a block of the new report, 0 when absent.
        """
        if code_du_moyen not in lignes_par_moyen:
            return 0
        return lignes_par_moyen[code_du_moyen]["total_en_centimes"]

    # ------------------------------------------------------------------
    # Les trois paiements
    # / The three payments
    # ------------------------------------------------------------------

    def test_comparaison_trois_jus_en_especes(self):
        """
        Trois jus à 3,50 € en espèces. Les deux rapports : 1050 TTC, 875 HT, 175 TVA
        (taux 20) ; espèces 1050, rien d'autre ; même tiroir (fond 0, entrées 1050,
        sorties 0, solde 1050).
        / Three juices in cash: both reports give 1050 / 875 / 175, cash 1050, and the
        same cash drawer.
        """
        cle_d_idempotence = self._payer_trois_jus("espece")
        self._verifier_la_vente_de_la_cle(cle_d_idempotence)

        chiffres = self._chiffre_affaires_des_deux_rapports()
        reglements_de_l_ancien, reglements_du_nouveau = (
            self._reglements_des_deux_rapports()
        )

        # 350 × 3 = 1050 ; HT arrondi(1050 / 1,2) = 875 ; TVA 175.
        # / 350 × 3 = 1050; HT 875; VAT 175.
        assert chiffres["nouveau_total"] == chiffres["ancien_total"] == (1050, 875, 175)
        assert (
            chiffres["nouveau_par_taux"][TAUX_DANS_LE_NOUVEAU_RAPPORT]
            == chiffres["ancien_par_taux"][TAUX_DANS_L_ANCIEN_RAPPORT]
        )
        assert len(chiffres["nouveau_par_taux"]) == len(chiffres["ancien_par_taux"])

        assert reglements_du_nouveau == reglements_de_l_ancien
        assert reglements_du_nouveau["especes"] == 1050
        assert reglements_du_nouveau["total"] == 1050

        # Le tiroir : fond, espèces, sorties, solde. L'ancien moteur ne sépare pas
        # les espèces reçues, rendues et corrigées : ses « entrées espèces » sont la
        # somme nette des lignes payées en espèces. On compare donc à la somme des
        # trois lignes du nouveau.
        # / The drawer. The old engine does not split cash received, given back and
        # corrected: its "cash in" is compared with the sum of the three new lines.
        ancien_rapport = RapportComptableService(
            self.point_de_vente, self.debut_de_la_periode, self.fin_de_la_periode
        )
        solde_de_l_ancien = ancien_rapport.calculer_solde_caisse()
        caisse_du_nouveau = RapportDesVentes(
            self.debut_de_la_periode, self.fin_de_la_periode
        ).section_caisse_especes()
        entrees_especes_du_nouveau = (
            caisse_du_nouveau["especes_recues_en_centimes"]
            + caisse_du_nouveau["especes_rendues_en_centimes"]
            + caisse_du_nouveau["corrections_en_centimes"]
        )

        assert (
            caisse_du_nouveau["fond_de_caisse_en_centimes"]
            == solde_de_l_ancien["fond_de_caisse"]
        )
        assert (
            entrees_especes_du_nouveau == solde_de_l_ancien["entrees_especes"] == 1050
        )
        assert (
            caisse_du_nouveau["sorties_en_centimes"]
            == solde_de_l_ancien["sorties_especes"]
        )
        assert (
            caisse_du_nouveau["solde_theorique_en_centimes"]
            == solde_de_l_ancien["solde"]
            == 1050
        )

    def test_comparaison_trois_jus_en_cb(self):
        """
        Trois jus à 3,50 € en CB. Les deux rapports : 1050 TTC, 875 HT, 175 TVA
        (taux 20) ; CB 1050, rien d'autre.
        / Three juices by bank card: both reports give 1050 / 875 / 175 and card 1050.
        """
        cle_d_idempotence = self._payer_trois_jus("carte_bancaire")
        self._verifier_la_vente_de_la_cle(cle_d_idempotence)

        chiffres = self._chiffre_affaires_des_deux_rapports()
        reglements_de_l_ancien, reglements_du_nouveau = (
            self._reglements_des_deux_rapports()
        )

        assert chiffres["nouveau_total"] == chiffres["ancien_total"] == (1050, 875, 175)
        assert (
            chiffres["nouveau_par_taux"][TAUX_DANS_LE_NOUVEAU_RAPPORT]
            == chiffres["ancien_par_taux"][TAUX_DANS_L_ANCIEN_RAPPORT]
        )
        assert len(chiffres["nouveau_par_taux"]) == len(chiffres["ancien_par_taux"])

        assert reglements_du_nouveau == reglements_de_l_ancien
        assert reglements_du_nouveau["carte_bancaire"] == 1050
        assert reglements_du_nouveau["total"] == 1050

    def test_comparaison_trois_jus_par_la_carte_en_monnaie_locale(self):
        """
        Trois jus à 3,50 € payés par la carte du client, qui porte 20,00 € de monnaie
        locale : la carte paie tout, d'une seule monnaie. Les deux rapports : 1050 TTC,
        875 HT, 175 TVA (taux 20) ; cashless 1050, tout en monnaie locale (par son nom).
        / Three juices paid by the customer's card (one currency): both reports give
        1050 / 875 / 175 and cashless 1050 in local currency.
        """
        carte = self._carte_du_client("RUCNFCAA", 2000)
        cle_d_idempotence = self._payer_trois_jus("nfc", carte=carte)
        self._verifier_la_vente_de_la_cle(cle_d_idempotence)

        chiffres = self._chiffre_affaires_des_deux_rapports()
        reglements_de_l_ancien, reglements_du_nouveau = (
            self._reglements_des_deux_rapports()
        )

        assert chiffres["nouveau_total"] == chiffres["ancien_total"] == (1050, 875, 175)
        assert (
            chiffres["nouveau_par_taux"][TAUX_DANS_LE_NOUVEAU_RAPPORT]
            == chiffres["ancien_par_taux"][TAUX_DANS_L_ANCIEN_RAPPORT]
        )
        assert len(chiffres["nouveau_par_taux"]) == len(chiffres["ancien_par_taux"])

        assert reglements_du_nouveau == reglements_de_l_ancien
        assert reglements_du_nouveau["cashless"] == 1050
        assert reglements_du_nouveau["cashless_par_nom"] == {
            NOM_DE_LA_MONNAIE_LOCALE: 1050
        }
        assert reglements_du_nouveau["total"] == 1050
