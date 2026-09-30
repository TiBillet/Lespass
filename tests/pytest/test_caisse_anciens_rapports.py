"""
tests/pytest/test_caisse_anciens_rapports.py
L'ancien rapport de caisse donne les mêmes totaux, alors que la caisse écrit aussi la
Vente et ses règlements.
/ The old register report gives the same totals, while the register also writes the
sale and its payments.

LOCALISATION : tests/pytest/test_caisse_anciens_rapports.py

RÈGLE MÉTIER TESTÉE
Pendant la transition (chantier 05, tronc §5), la caisse écrit ses lignes de vente
comme avant (même prix unitaire `amount`, même quantité `qty`, même taux `vat`, même
moyen de paiement), ET la Vente avec ses règlements. L'ancien rapport de caisse
(`laboutik/reports.py`, `RapportComptableService`) ne lit que les lignes : il doit donc
donner exactement les mêmes totaux. Ce sont eux que lit le ticket Z (clôture).
/ During the transition the register writes its lines as before AND the sale. The old
report only reads the lines: its totals must not move.

Trois ventes, par la vraie route de paiement de la caisse :
1. trois jus à 3,50 € en espèces ;
2. trois jus : 5,00 € en monnaie locale sur la carte du client, le reste (5,50 €) en CB ;
3. une bière à 5,00 € : 3,00 € en jetons cadeau sur la carte, le reste (2,00 €) en CB.
Pour chacune, on relit les six calculs de l'ancien rapport que lit le ticket Z :
totaux par moyen, détail des ventes, TVA, solde de caisse, offerts, recharges.

D'OÙ VIENNENT LES VALEURS ATTENDUES
Elles sont calculées à la main avec les formules de `laboutik/reports.py` et les
champs que la caisse écrivait sur ses lignes avant le chantier. Le calcul est écrit en
commentaire au-dessus de chaque valeur. Les formules utilisées :
- montant d'un groupe de lignes = ROUND(Σ amount × qty), arrondi au centime par
  PostgreSQL (`montant_ttc_centimes`) ;
- HT = int(round(TTC / (1 + taux / 100))) et TVA = TTC − HT (`calculer_tva`,
  `calculer_detail_ventes`) ;
- coût = prix d'achat unitaire × int(quantité totale), bénéfice = HT − coût ;
- les jetons cadeau (LG) comptent dans « cashless » et dans les quantités offertes du
  détail des ventes ; seuls FREE et NON_MONETAIRE sortent des calculs d'argent.
Une part payée par la carte garde le prix unitaire (`amount`) et une quantité
partielle : quantité = argent de la part / prix unitaire, arrondie à 6 décimales ; la
dernière part prend le reste (`laboutik/views.py`, `_calculer_qty_partielles`).
/ Expected values are computed by hand from the report's formulas and the fields the
register wrote on its lines before the work. The computation is written above each
value.

SCHÉMA DÉDIÉ
L'ancien rapport lit TOUTES les lignes de caisse du lieu sur la période, sans filtre de
point de vente : il faut un lieu qui ne contient que la vente du test
(`FastTenantTestCase`, tronc §8.5). Chaque test annule sa transaction à la fin. Le
singleton `LaboutikConfiguration` est créé en base (tests/PIEGES.md 9.86) : sans lui,
la clé de l'empreinte de la vente échoue.
Les cartes NFC sont dans le schéma `public` (tests/PIEGES.md 9.30) : elles sont créées
dans la transaction du test, donc annulées avec elle.
Le réseau Fedow distant est coupé (`can_fedow` faux) : la cascade de la carte reste
locale, aucun appel réseau.
/ Dedicated schema: the old report reads every register line of the venue in the
period. Each test rolls back. The remote Fedow network is off.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-B-caisse.md (§6, test 23)
et CHANTIER-05-montants-entiers.md (§5, §8).

Lancer / Run : make test ARGS="tests/pytest/test_caisse_anciens_rapports.py"
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
from QrcodeCashless.models import CarteCashless  # noqa: E402
from fabriques_vente import verifier_egalites  # noqa: E402
from fedow_core.models import Asset, Token  # noqa: E402
from fedow_core.services import AssetService  # noqa: E402
from laboutik.models import LaboutikConfiguration, PointDeVente  # noqa: E402
from laboutik.reports import RapportComptableService  # noqa: E402

# Adresses de la caisse (laboutik/urls.py).
# / Cash register addresses.
URL_DU_PAIEMENT_CAISSE = "/laboutik/paiement/payer/"
URL_DU_PAIEMENT_COMPLEMENTAIRE = "/laboutik/paiement/payer_complementaire/"

# Noms lus tels quels dans le rapport (catégorie, produits, monnaies).
# / Names read as they are in the report.
NOM_DE_LA_CATEGORIE = "Boissons anciens rapports"
NOM_DU_JUS = "Jus anciens rapports"
NOM_DE_LA_BIERE = "Biere anciens rapports"
NOM_DE_LA_MONNAIE_LOCALE = "Monnaie locale anciens rapports"
NOM_DES_JETONS_CADEAU = "Jetons cadeau anciens rapports"

# Prix d'achat des deux produits, en centimes : 1,00 €. Il fait vivre le coût et le
# bénéfice du détail des ventes.
# / Purchase price of both products, in cents: it drives cost and profit.
PRIX_D_ACHAT_EN_CENTIMES = 100

# Ce que l'ancien rapport rend quand la période n'a ni offert ni recharge.
# / What the old report returns when the period has no gift and no top-up.
AUCUN_OFFERT = {"par_produit": [], "qty_totale": 0.0, "valeur_totale": 0}
AUCUNE_RECHARGE = {"detail": {}, "total": 0, "cadeau_emis": 0}


class TestAnciensRapportsDeCaisseInchanges(FastTenantTestCase):
    """
    L'ancien rapport de caisse donne les mêmes totaux (fiche B §6, test 23).
    / The old register report gives the same totals (sheet B §6, test 23).
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_anciens_rapports"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-anciens-rapports.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test anciens rapports"

    def setUp(self):
        """
        Un comptoir, un jus à 3,50 € et une bière à 5,00 € (TVA 20 %), la monnaie
        locale et les jetons cadeau du lieu, un caissier connecté.
        / A counter, a juice and a beer (20 % VAT), the venue currencies, a cashier.
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
        # Son fond de caisse vaut 0 (défaut du champ).
        # / The register singleton must exist in the database. Cash float: 0.
        LaboutikConfiguration.get_solo().save()

        # Le taux d'une ligne vient de `Product.tva`.
        # / A line's rate comes from Product.tva.
        tva_a_vingt_pour_cent, _tva_creee = Tva.objects.get_or_create(
            tva_rate=Decimal("20")
        )
        categorie = CategorieProduct.objects.create(name=NOM_DE_LA_CATEGORIE)

        self.jus = Product.objects.create(
            name=NOM_DU_JUS,
            methode_caisse=Product.VENTE,
            categorie_pos=categorie,
            tva=tva_a_vingt_pour_cent,
            prix_achat=PRIX_D_ACHAT_EN_CENTIMES,
        )
        self.tarif_du_jus = Price.objects.create(
            product=self.jus, name="Verre", prix=Decimal("3.50"), publish=True
        )
        self.biere = Product.objects.create(
            name=NOM_DE_LA_BIERE,
            methode_caisse=Product.VENTE,
            categorie_pos=categorie,
            tva=tva_a_vingt_pour_cent,
            prix_achat=PRIX_D_ACHAT_EN_CENTIMES,
        )
        self.tarif_de_la_biere = Price.objects.create(
            product=self.biere, name="Pinte", prix=Decimal("5.00"), publish=True
        )

        self.point_de_vente = PointDeVente.objects.create(
            name="Comptoir anciens rapports",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.point_de_vente.products.add(self.jus, self.biere)

        # Les deux monnaies du lieu : locale (TLF) et jetons cadeau (TNF).
        # / The venue's two currencies: local (TLF) and gift tokens (TNF).
        portefeuille_du_lieu = Wallet.objects.create(
            origin=self.tenant, name="Wallet lieu anciens rapports"
        )
        self.monnaie_locale = AssetService.creer_asset(
            tenant=self.tenant,
            name=NOM_DE_LA_MONNAIE_LOCALE,
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=portefeuille_du_lieu,
        )
        self.jetons_cadeau = AssetService.creer_asset(
            tenant=self.tenant,
            name=NOM_DES_JETONS_CADEAU,
            category=Asset.TNF,
            currency_code="EUR",
            wallet_origin=portefeuille_du_lieu,
        )

        # Le caissier : un administrateur du lieu, connecté (sans carte primaire).
        # / The cashier: a logged-in venue admin (no primary card).
        caissier, _caissier_cree = TibilletUser.objects.get_or_create(
            email="caissier-anciens-rapports@tibillet.localhost",
            defaults={
                "username": "caissier-anciens-rapports@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        caissier.client_admin.add(self.tenant)
        self.navigateur_du_caissier = TenantClient(self.tenant)
        self.navigateur_du_caissier.force_login(caissier)

        # La période du rapport, large des deux côtés : l'heure de la machine ne
        # change rien au résultat.
        # / The report period, wide on both sides.
        self.debut_de_la_periode = timezone.now() - timedelta(hours=1)
        self.fin_de_la_periode = timezone.now() + timedelta(hours=1)

    # ------------------------------------------------------------------
    # Gestes du caissier
    # / Cashier actions
    # ------------------------------------------------------------------

    def _carte_du_client(self, identifiant_de_la_carte, soldes_par_monnaie):
        """
        Une carte NFC anonyme, dont le portefeuille porte les soldes donnés.
        / An anonymous NFC card whose wallet holds the given balances.

        :param identifiant_de_la_carte: `tag_id` et `number`, 8 caractères au plus
            (tests/PIEGES.md 9.31)
        :param soldes_par_monnaie: liste de paires (monnaie, solde en centimes)
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
        for monnaie, solde_en_centimes in soldes_par_monnaie:
            Token.objects.create(
                wallet=portefeuille_de_la_carte,
                asset=monnaie,
                value=solde_en_centimes,
            )
        return carte

    def _envoyer_sans_le_reseau_fedow(self, adresse, donnees_du_formulaire):
        """
        Poste le formulaire de la caisse, le réseau Fedow distant coupé : la cascade
        de la carte reste locale.
        / Posts the register form with the remote Fedow network off.
        """
        with (
            mock.patch("laboutik.views.FedowConfig") as configuration_fedow,
            mock.patch("laboutik.views.FedowAPI"),
        ):
            configuration_fedow.get_solo.return_value.can_fedow.return_value = False
            reponse = self.navigateur_du_caissier.post(adresse, donnees_du_formulaire)

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        return reponse

    def _payer_en_especes(self, produit, tarif, quantite, cle_d_idempotence):
        """
        Le caissier encaisse un panier d'un article en espèces, compte juste.
        / The cashier collects a one-article cart in cash, exact amount.
        """
        donnees_du_formulaire = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "moyen_paiement": "espece",
            "total": "0",
            "given_sum": "0",
            "cle_idempotence_paiement": cle_d_idempotence,
            f"repid-{produit.uuid}--{tarif.uuid}": str(quantite),
        }
        return self._envoyer_sans_le_reseau_fedow(
            URL_DU_PAIEMENT_CAISSE, donnees_du_formulaire
        )

    def _payer_par_la_carte_puis_le_reste_en_cb(
        self, carte, produit, tarif, quantite, cle_d_idempotence
    ):
        """
        La carte ne suffit pas : elle paie ce qu'elle peut, le reste est réglé en CB,
        par la route du paiement complémentaire (écran « reste à payer »). Le serveur
        refait lui-même la cascade de la carte.
        / The card is not enough: it pays what it can, the rest by bank card.
        """
        donnees_du_formulaire = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "cle_idempotence_paiement": cle_d_idempotence,
            "tag_id_carte1": carte.tag_id,
            "moyen_complement": "carte_bancaire",
            "given_sum": "",
            f"repid-{produit.uuid}--{tarif.uuid}": str(quantite),
        }
        return self._envoyer_sans_le_reseau_fedow(
            URL_DU_PAIEMENT_COMPLEMENTAIRE, donnees_du_formulaire
        )

    # ------------------------------------------------------------------
    # Lecture
    # / Reading
    # ------------------------------------------------------------------

    def _ancien_rapport(self):
        """L'ancien rapport de caisse sur la période.
        / The old register report over the period."""
        return RapportComptableService(
            self.point_de_vente, self.debut_de_la_periode, self.fin_de_la_periode
        )

    def _totaux_par_moyen_sans_la_devise(self, rapport):
        """
        Les totaux par moyen de paiement, sans le code devise (lu dans la
        configuration, ce n'est pas un montant).
        / Totals per payment method, without the currency code.
        """
        totaux_par_moyen = rapport.calculer_totaux_par_moyen()
        del totaux_par_moyen["currency_code"]
        return totaux_par_moyen

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
    # Scénario 1 — trois jus à 3,50 € en espèces
    # / Scenario 1 — three 3.50 € juices in cash
    # ------------------------------------------------------------------

    def test_anciens_rapports_inchanges_trois_jus_en_especes(self):
        """
        Trois jus à 3,50 € (TVA 20 %) en espèces : une ligne, prix unitaire 350,
        quantité 3, moyen espèces (CA), taux 20.
        / Three juices in cash: one line, unit price 350, quantity 3, cash, 20 %.
        """
        cle_d_idempotence = str(uuid.uuid4())
        self._payer_en_especes(
            self.jus, self.tarif_du_jus, quantite=3, cle_d_idempotence=cle_d_idempotence
        )

        self._verifier_la_vente_de_la_cle(cle_d_idempotence)
        rapport = self._ancien_rapport()

        # Espèces = ROUND(350 × 3) = 1050. Aucun autre moyen. Total = 1050.
        # / Cash = ROUND(350 × 3) = 1050. Total 1050.
        assert self._totaux_par_moyen_sans_la_devise(rapport) == {
            "especes": 1050,
            "carte_bancaire": 0,
            "cashless": 0,
            "cashless_detail": [],
            "cheque": 0,
            "federe": 0,
            "total": 1050,
        }

        # Une ligne vendue (CA n'est pas un moyen cadeau) : quantité 3, TTC 1050.
        # HT = int(round(1050 / 1,2)) = 875 ; TVA = 1050 − 875 = 175.
        # Coût = 100 × int(3.0) = 300 ; bénéfice = 875 − 300 = 575.
        # / One sold line: qty 3, TTC 1050, HT 875, VAT 175, cost 300, profit 575.
        assert rapport.calculer_detail_ventes() == {
            NOM_DE_LA_CATEGORIE: {
                "articles": [
                    {
                        "nom": NOM_DU_JUS,
                        "qty_vendus": 3.0,
                        "qty_offerts": 0.0,
                        "qty_total": 3.0,
                        "total_ttc": 1050,
                        "total_ht": 875,
                        "total_tva": 175,
                        "taux_tva": 20.0,
                        "prix_achat_unit": 100,
                        "cout_total": 300,
                        "benefice": 575,
                        "poids_total": None,
                        "unite_poids": None,
                    }
                ],
                "total_ttc": 1050,
            }
        }

        # Taux 20 : TTC = ROUND(350 × 3) = 1050 ; HT = int(round(1050 / 1,2)) = 875 ;
        # TVA = 175.
        # / 20 % rate: TTC 1050, HT 875, VAT 175.
        assert rapport.calculer_tva() == {
            "20.00%": {
                "taux": 20.0,
                "total_ttc": 1050,
                "total_ht": 875,
                "total_tva": 175,
            }
        }

        # Solde = fond de caisse 0 + entrées espèces 1050 − sorties 0 = 1050.
        # / Balance = float 0 + cash in 1050 − cash out 0.
        assert rapport.calculer_solde_caisse() == {
            "fond_de_caisse": 0,
            "entrees_especes": 1050,
            "sorties_especes": 0,
            "solde": 1050,
        }

        # Aucune ligne FREE, aucun produit de recharge.
        # / No FREE line, no top-up product.
        assert rapport.calculer_offerts() == AUCUN_OFFERT
        assert rapport.calculer_recharges() == AUCUNE_RECHARGE

    # ------------------------------------------------------------------
    # Scénario 9 — trois jus : 5,00 € en monnaie locale + 5,50 € en CB
    # / Scenario 9 — three juices: 5.00 € local currency + 5.50 € bank card
    # ------------------------------------------------------------------

    def test_anciens_rapports_inchanges_monnaie_locale_puis_cb(self):
        """
        Trois jus à 3,50 € (10,50 €). La carte porte 5,00 € de monnaie locale : elle
        paie 5,00 €, le reste (5,50 €) est réglé en CB.
        Deux parts, prix unitaire 350, taux 20 :
        - monnaie locale (LE) : quantité = 500 / 350 = 1,428571 (6 décimales) ;
        - CB (CC), dernière part : quantité = 3 − 1,428571 = 1,571429.
        / Two parts at unit price 350: LE qty 1.428571, CB qty 1.571429.
        """
        carte = self._carte_du_client("ANR9AAAA", [(self.monnaie_locale, 500)])
        cle_d_idempotence = str(uuid.uuid4())
        self._payer_par_la_carte_puis_le_reste_en_cb(
            carte,
            self.jus,
            self.tarif_du_jus,
            quantite=3,
            cle_d_idempotence=cle_d_idempotence,
        )

        self._verifier_la_vente_de_la_cle(cle_d_idempotence)
        rapport = self._ancien_rapport()

        # CB = ROUND(350 × 1,571429) = ROUND(550,00015) = 550.
        # Cashless (LE + LG) = ROUND(350 × 1,428571) = ROUND(499,99985) = 500, tout en
        # monnaie locale. Total = 550 + 500 = 1050.
        # / CB 550, cashless 500 (all local currency), total 1050.
        assert self._totaux_par_moyen_sans_la_devise(rapport) == {
            "especes": 0,
            "carte_bancaire": 550,
            "cashless": 500,
            "cashless_detail": [
                {"nom": NOM_DE_LA_MONNAIE_LOCALE, "code": "EUR", "montant": 500}
            ],
            "cheque": 0,
            "federe": 0,
            "total": 1050,
        }

        # Deux groupes (LE, CC), tous deux « vendus » (aucun n'est LG) :
        # quantité vendue = 1,428571 + 1,571429 = 3,0 ; TTC = 500 + 550 = 1050.
        # HT = int(round(1050 / 1,2)) = 875 ; TVA = 175.
        # Coût = 100 × int(3.0) = 300 ; bénéfice = 875 − 300 = 575.
        # / Two sold groups: qty 3.0, TTC 1050, HT 875, VAT 175, cost 300, profit 575.
        assert rapport.calculer_detail_ventes() == {
            NOM_DE_LA_CATEGORIE: {
                "articles": [
                    {
                        "nom": NOM_DU_JUS,
                        "qty_vendus": 3.0,
                        "qty_offerts": 0.0,
                        "qty_total": 3.0,
                        "total_ttc": 1050,
                        "total_ht": 875,
                        "total_tva": 175,
                        "taux_tva": 20.0,
                        "prix_achat_unit": 100,
                        "cout_total": 300,
                        "benefice": 575,
                        "poids_total": None,
                        "unite_poids": None,
                    }
                ],
                "total_ttc": 1050,
            }
        }

        # Les deux parts sont au taux 20 : TTC = ROUND(350 × 1,428571 + 350 × 1,571429)
        # = ROUND(1050,00000) = 1050 ; HT = 875 ; TVA = 175.
        # / Both parts at 20 %: TTC 1050, HT 875, VAT 175.
        assert rapport.calculer_tva() == {
            "20.00%": {
                "taux": 20.0,
                "total_ttc": 1050,
                "total_ht": 875,
                "total_tva": 175,
            }
        }

        # Aucune espèce : solde = 0 + 0 − 0 = 0.
        # / No cash: balance 0.
        assert rapport.calculer_solde_caisse() == {
            "fond_de_caisse": 0,
            "entrees_especes": 0,
            "sorties_especes": 0,
            "solde": 0,
        }

        assert rapport.calculer_offerts() == AUCUN_OFFERT
        assert rapport.calculer_recharges() == AUCUNE_RECHARGE

    # ------------------------------------------------------------------
    # Scénario 12 — une bière à 5,00 € : 3,00 € en jetons cadeau + 2,00 € en CB
    # / Scenario 12 — a 5.00 € beer: 3.00 € gift tokens + 2.00 € bank card
    # ------------------------------------------------------------------

    def test_anciens_rapports_inchanges_jetons_cadeau_puis_cb(self):
        """
        Une bière à 5,00 € (TVA 20 %). La carte porte 3,00 € de jetons cadeau et
        aucune monnaie locale : les jetons paient 3,00 €, le reste (2,00 €) en CB.
        Deux parts, prix unitaire 500, taux 20 (le taux du produit : LG n'est ni FREE
        ni NON_MONETAIRE) :
        - jetons (LG) : quantité = 300 / 500 = 0,6 ;
        - CB (CC), dernière part : quantité = 1 − 0,6 = 0,4.
        La Vente, elle, traite les jetons comme un cadeau (net 200) : l'ancien rapport
        ne la lit pas et garde ses totaux d'avant.
        / Two parts at unit price 500, 20 %: LG qty 0.6, CB qty 0.4. The old report
        keeps its former totals.
        """
        carte = self._carte_du_client(
            "ANR12AAA", [(self.monnaie_locale, 0), (self.jetons_cadeau, 300)]
        )
        cle_d_idempotence = str(uuid.uuid4())
        self._payer_par_la_carte_puis_le_reste_en_cb(
            carte,
            self.biere,
            self.tarif_de_la_biere,
            quantite=1,
            cle_d_idempotence=cle_d_idempotence,
        )

        self._verifier_la_vente_de_la_cle(cle_d_idempotence)
        rapport = self._ancien_rapport()

        # CB = ROUND(500 × 0,4) = 200.
        # Cashless (LE + LG) = ROUND(500 × 0,6) = 300, tout en jetons cadeau.
        # Total = 200 + 300 = 500.
        # / CB 200, cashless 300 (all gift tokens), total 500.
        assert self._totaux_par_moyen_sans_la_devise(rapport) == {
            "especes": 0,
            "carte_bancaire": 200,
            "cashless": 300,
            "cashless_detail": [
                {"nom": NOM_DES_JETONS_CADEAU, "code": "EUR", "montant": 300}
            ],
            "cheque": 0,
            "federe": 0,
            "total": 500,
        }

        # Groupe LG (moyen cadeau) : offerts, quantité 0,6, TTC 300.
        # Groupe CC : vendus, quantité 0,4, TTC 200.
        # Quantité totale = 0,4 + 0,6 = 1,0 ; TTC = 200 + 300 = 500.
        # HT = int(round(500 / 1,2)) = int(round(416,67)) = 417 ; TVA = 500 − 417 = 83.
        # Coût = 100 × int(1.0) = 100 ; bénéfice = 417 − 100 = 317.
        # / LG group gifted (0.6, 300), CC group sold (0.4, 200): TTC 500, HT 417,
        #   VAT 83, cost 100, profit 317.
        assert rapport.calculer_detail_ventes() == {
            NOM_DE_LA_CATEGORIE: {
                "articles": [
                    {
                        "nom": NOM_DE_LA_BIERE,
                        "qty_vendus": 0.4,
                        "qty_offerts": 0.6,
                        "qty_total": 1.0,
                        "total_ttc": 500,
                        "total_ht": 417,
                        "total_tva": 83,
                        "taux_tva": 20.0,
                        "prix_achat_unit": 100,
                        "cout_total": 100,
                        "benefice": 317,
                        "poids_total": None,
                        "unite_poids": None,
                    }
                ],
                "total_ttc": 500,
            }
        }

        # Les deux parts sont au taux 20 et comptent dans la TVA (seuls FREE et
        # NON_MONETAIRE en sortent) : TTC = ROUND(500 × 0,6 + 500 × 0,4) = 500 ;
        # HT = 417 ; TVA = 83.
        # / Both parts at 20 % count in the VAT: TTC 500, HT 417, VAT 83.
        assert rapport.calculer_tva() == {
            "20.00%": {
                "taux": 20.0,
                "total_ttc": 500,
                "total_ht": 417,
                "total_tva": 83,
            }
        }

        assert rapport.calculer_solde_caisse() == {
            "fond_de_caisse": 0,
            "entrees_especes": 0,
            "sorties_especes": 0,
            "solde": 0,
        }

        # Les jetons (LG) ne sont pas FREE : la section « offerts » reste vide.
        # / Tokens (LG) are not FREE: the gifts section stays empty.
        assert rapport.calculer_offerts() == AUCUN_OFFERT
        assert rapport.calculer_recharges() == AUCUNE_RECHARGE
