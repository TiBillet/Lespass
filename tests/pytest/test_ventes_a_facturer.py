"""
tests/pytest/test_ventes_a_facturer.py
Une vente TiBillet découpée pour un logiciel de facturation (Dolibarr) : lignes de
facture, paiements de la facture, virements internes, paiements divers.
/ A TiBillet sale split for an invoicing software.

LOCALISATION : tests/pytest/test_ventes_a_facturer.py

RÈGLES MÉTIER TESTÉES (spec TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-06-connecteurs-
comptables/CHANTIER-06-D-ventes.md, D4, D7-D15, Q2, Q5, Q6, Q11)
- Lignes de la facture : les articles du chiffre d'affaires, au tarif vendu, avec le
  compte et la TVA de TiBillet ; la part payée en jetons sur une ligne à part (707900,
  TVA 0) ; un retour de consigne au premier tarif en euros du gobelet.
- Paiements de la facture : par compte de trésorerie (règlements nets, corrections
  comprises).
- Recharge et vidage : virements internes entre la banque de la monnaie et celle du
  moyen. Recharge offerte, jetons repris, écart d'encaissement : paiements divers.
- L'acheteur est `Vente.client`, jamais la carte lue après coup.
- Une vente sans montant ne donne rien (None).
/ Business rules tested: invoice lines, invoice payments, transfers, various payments,
buyer, empty sales.

Schéma dédié (`FastTenantTestCase`) : chaque test annule sa transaction à la fin. Les
ventes sont écrites par le service de vente (`fabriques_vente.py`). Valeurs attendues
calculées à la main : HT = arrondi_demi_haut(net × 100 / (100 + taux)), TVA = net − HT.
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from datetime import time  # noqa: E402
from decimal import Decimal  # noqa: E402

from django.db import connection  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402

from AuthBillet.models import Wallet  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    CategorieProduct,
    Configuration,
    PaymentMethod,
    Price,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Vente  # noqa: E402
from BaseBillet.services_vente import (  # noqa: E402
    NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE,
    ajouter_reglement,
    encaisser_vente,
    ouvrir_vente,
    tarif_vendu_d_un_produit_systeme,
)
from comptabilite.ventes_a_facturer import (  # noqa: E402
    RepartitionImpossible,
    vente_a_facturer,
)
from fabriques_panier import creer_utilisateur, identifiant_unique  # noqa: E402
from fabriques_vente import (  # noqa: E402
    NOM_DE_LA_CATEGORIE_DE_CAISSE_DE_TEST,
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from fedow_core.models import Asset  # noqa: E402
from laboutik.models import CompteComptable, LaboutikConfiguration  # noqa: E402
from laboutik.plan_comptable import (  # noqa: E402
    CompteComptableManquant,
    compte_pour_produit,
    comptes_du_plan_par_defaut_du_lieu,
)
from QrcodeCashless.models import CarteCashless  # noqa: E402


class TestVentesAFacturer(FastTenantTestCase):
    """
    La découpe d'une vente pour un logiciel de facturation (fiche 06-D).
    / A sale split for an invoicing software.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_ventes_a_facturer"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-ventes-a-facturer.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test ventes a facturer"

    def setUp(self):
        """
        Le lieu de test, une catégorie de caisse « Boissons » reliée au 707000 et une
        bière à 5,00 € (TVA 20 %) rangée dedans.
        / The test venue, a "Drinks" POS category (707000) and a 5.00 € beer.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse doit exister en base (tests/PIEGES.md 9.86).
        # / The register singleton must exist in the database.
        LaboutikConfiguration.get_solo().save()

        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.heure_de_fermeture = time(2, 0)
        configuration.save()

        self.categorie_des_boissons = CategorieProduct.objects.create(
            name=f"Boissons {identifiant_unique()}",
            compte_comptable=CompteComptable.objects.get(numero_de_compte="707000"),
        )
        self.tarif_de_la_biere = self._tarif_d_une_boisson("Biere", "5.00")

    # ------------------------------------------------------------------
    # Outils du test
    # / Test helpers
    # ------------------------------------------------------------------

    def _tarif_d_une_boisson(self, nom, prix_en_euros):
        """
        Le tarif vendu d'une boisson à 20 %, dans la catégorie « Boissons » (707000).
        / The sold price of a 20 % drink, in the "Drinks" category.
        """
        tarif_vendu = creer_tarif_vendu(
            nom=nom,
            prix_en_euros=prix_en_euros,
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )
        produit = tarif_vendu.productsold.product
        produit.categorie_pos = self.categorie_des_boissons
        produit.save()
        return tarif_vendu

    def _monnaie(self, nom, categorie):
        """
        Une monnaie du moteur fedow_core, créée par le lieu de test.
        / A fedow_core currency created by the test venue.
        """
        portefeuille_d_origine = Wallet.objects.create(
            name=f"Portefeuille {identifiant_unique()}"
        )
        return Asset.objects.create(
            name=f"{nom} {identifiant_unique()}",
            currency_code="EUR",
            category=categorie,
            tenant_origin=self.tenant,
            wallet_origin=portefeuille_d_origine,
        )

    def _tarif_de_recharge(self, prix_en_euros="10.00"):
        """Le tarif vendu d'une recharge en euros. / A euro top-up's sold price."""
        return creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros=prix_en_euros,
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )

    def _biere(self, quantite="1", prix_unitaire=500, **en_plus):
        """Un article « bière » pour `fabriquer_vente_encaissee`. / A beer item."""
        article = {
            "pricesold": self.tarif_de_la_biere,
            "quantite": Decimal(quantite),
            "prix_unitaire": prix_unitaire,
            "taux_tva": Decimal("20"),
        }
        article.update(en_plus)
        return article

    def _vendre(self, articles, reglements, **en_plus):
        """Une vente de caisse encaissée et vérifiée. / A settled register sale."""
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=articles,
            reglements=reglements,
            **en_plus,
        )
        verifier_egalites(vente)
        return vente

    def _decouper(self, vente):
        """
        La vente découpée, les comptes lus ici. La vente est relue en base, comme le
        fait la route.
        / The split sale, with accounts read here.
        """
        vente_relue = Vente.objects.get(pk=vente.pk)
        return vente_a_facturer(
            vente_relue, comptes_du_plan_par_defaut_du_lieu(), {}, {}
        )

    def _comptes_et_montants(self, elements, cle_du_compte):
        """
        [(numéro du compte, montant)] d'une liste de paiements.
        / [(account number, amount)] of a payment list.
        """
        resultat = []
        for element in elements:
            resultat.append(
                (element[cle_du_compte].numero_de_compte, element["montant"])
            )
        return resultat

    def _virements(self, decoupe):
        """[(depuis, vers, montant)] des virements. / Transfers as tuples."""
        resultat = []
        for virement in decoupe["virements"]:
            resultat.append(
                (
                    virement["depuis"].numero_de_compte,
                    virement["vers"].numero_de_compte,
                    virement["montant"],
                )
            )
        return resultat

    def _paiements_divers(self, decoupe):
        """[(trésorerie, montant, contrepartie)] des paiements divers. / As tuples."""
        resultat = []
        for paiement_divers in decoupe["paiements_divers"]:
            resultat.append(
                (
                    paiement_divers["compte_de_tresorerie"].numero_de_compte,
                    paiement_divers["montant"],
                    paiement_divers["contrepartie"].numero_de_compte,
                )
            )
        return resultat

    # ------------------------------------------------------------------
    # Les lignes de la facture / Invoice lines
    # ------------------------------------------------------------------

    def test_biere_en_especes_une_ligne_un_paiement(self):
        """
        Une bière à 5,00 € en espèces : une ligne au tarif vendu (HT 417, TVA 83, au
        707000 et au 445711), un paiement de 500 au 530000, rien d'autre.
        / A cash beer: one line, one payment, nothing else.
        """
        vente = self._vendre(
            [self._biere()], [{"moyen": PaymentMethod.CASH, "montant": 500}]
        )

        decoupe = self._decouper(vente)

        assert decoupe["nature"] == "sale"
        assert decoupe["client"] is None
        assert len(decoupe["lignes_de_la_facture"]) == 1
        ligne = decoupe["lignes_de_la_facture"][0]
        assert ligne["tarif"] == self.tarif_de_la_biere.price
        assert (ligne["total_ttc"], ligne["total_ht"], ligne["total_tva"]) == (
            500,
            417,
            83,
        )
        assert ligne["quantite"] == Decimal("1")
        assert ligne["prix_unitaire_ttc"] == 500
        assert ligne["compte"].numero_de_compte == "707000"
        assert ligne["compte_de_tva"].numero_de_compte == "445711"
        assert self._comptes_et_montants(
            decoupe["paiements_de_la_facture"], "compte"
        ) == [("530000", 500)]
        assert decoupe["virements"] == []
        assert decoupe["paiements_divers"] == []

    def test_part_payee_en_jetons_sur_une_ligne_a_part_707900(self):
        """
        Une bière à 5,00 € dont 3,00 € en jetons cadeau : une ligne « jetons » de 300
        au 707900, TVA 0, et une ligne du reste (200 : HT 167, TVA 33) au 707000.
        / A beer partly paid in gift tokens: a separate 707900 line, then the rest.
        """
        jetons_cadeau = self._monnaie("Jetons", Asset.TNF)
        vente = self._vendre(
            [self._biere(part_en_jetons=300)],
            [
                {
                    "moyen": PaymentMethod.LOCAL_GIFT,
                    "montant": 300,
                    "asset": jetons_cadeau.uuid,
                },
                {"moyen": PaymentMethod.CASH, "montant": 200},
            ],
        )

        lignes = self._decouper(vente)["lignes_de_la_facture"]

        assert len(lignes) == 2
        ligne_des_jetons, ligne_du_reste = lignes
        assert ligne_des_jetons["tarif"] is None
        assert ligne_des_jetons["compte"].numero_de_compte == "707900"
        assert ligne_des_jetons["compte_de_tva"] is None
        assert (
            ligne_des_jetons["total_ttc"],
            ligne_des_jetons["total_ht"],
            ligne_des_jetons["total_tva"],
        ) == (300, 300, 0)
        assert (
            ligne_du_reste["total_ttc"],
            ligne_du_reste["total_ht"],
            ligne_du_reste["total_tva"],
        ) == (200, 167, 33)
        assert ligne_du_reste["compte"].numero_de_compte == "707000"

    def test_retour_de_consigne_au_premier_tarif_du_gobelet(self):
        """
        Un retour de gobelet (vente AVOIR, −1,00 €) : la ligne porte le premier tarif
        en euros du gobelet, au compte de la consigne (707000), montants négatifs.
        / A cup return: the cup's first euro price, the deposit's account.
        """
        tarif_du_gobelet = self._tarif_d_une_boisson("Gobelet", "1.00")
        gobelet = tarif_du_gobelet.productsold.product
        Price.objects.create(
            product=gobelet, name="Second tarif", prix=Decimal("2.00"), order=200
        )
        tarif_du_retour = creer_tarif_vendu(
            nom="Retour gobelet",
            prix_en_euros="-1.00",
            taux_tva="20.00",
            methode_caisse=Product.RETOUR_CONSIGNE,
        )
        produit_de_retour = tarif_du_retour.productsold.product
        produit_de_retour.consigne_remboursee = gobelet
        produit_de_retour.save()
        vente_du_retour = self._vendre(
            [
                {
                    "pricesold": tarif_du_retour,
                    "quantite": Decimal("1"),
                    "prix_unitaire": -100,
                    "taux_tva": Decimal("20"),
                }
            ],
            [{"moyen": PaymentMethod.CASH, "montant": -100}],
            nature=Vente.Nature.AVOIR,
        )

        decoupe = self._decouper(vente_du_retour)

        assert decoupe["nature"] == "refund"
        ligne = decoupe["lignes_de_la_facture"][0]
        assert ligne["tarif"] == tarif_du_gobelet.price
        assert ligne["compte"].numero_de_compte == "707000"
        assert (ligne["total_ttc"], ligne["total_ht"], ligne["total_tva"]) == (
            -100,
            -83,
            -17,
        )
        assert self._comptes_et_montants(
            decoupe["paiements_de_la_facture"], "compte"
        ) == [("530000", -100)]

    def test_retour_de_consigne_sans_gobelet_leve_la_phrase_du_compte(self):
        """
        Un retour de consigne dont le gobelet n'est pas relié : la règle du compte lève
        sa phrase (`CompteComptableManquant`), comme pour le FEC : la route répond 409,
        jamais 500.
        / A deposit return without its cup: the account rule's sentence, not a crash.
        """
        tarif_du_retour = creer_tarif_vendu(
            nom="Retour orphelin",
            prix_en_euros="-1.00",
            taux_tva="20.00",
            methode_caisse=Product.RETOUR_CONSIGNE,
            avec_compte=False,
        )
        vente_du_retour = self._vendre(
            [
                {
                    "pricesold": tarif_du_retour,
                    "quantite": Decimal("1"),
                    "prix_unitaire": -100,
                    "taux_tva": Decimal("20"),
                }
            ],
            [{"moyen": PaymentMethod.CASH, "montant": -100}],
            nature=Vente.Nature.AVOIR,
        )

        try:
            self._decouper(vente_du_retour)
            assert False, "CompteComptableManquant attendue"
        except CompteComptableManquant as erreur:
            assert "retour de consigne" in str(erreur)

    # ------------------------------------------------------------------
    # Paiements, recharges, virements / Payments, top-ups, transfers
    # ------------------------------------------------------------------

    def test_biere_et_recharge_payees_en_cb_facture_plus_virement(self):
        """
        Une bière à 5,00 € et une recharge de 10,00 €, un seul règlement CB de
        15,00 € : la facture vaut la bière (payée 500 en CB), et la recharge est un
        virement de 1000 de la banque des recharges (419100) vers la CB (512100).
        / A beer and a top-up paid by card: invoice = the beer, plus one transfer.
        """
        vente = self._vendre(
            [
                self._biere(),
                {
                    "pricesold": self._tarif_de_recharge(),
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("0"),
                },
            ],
            [{"moyen": PaymentMethod.CC, "montant": 1500}],
        )

        decoupe = self._decouper(vente)

        assert len(decoupe["lignes_de_la_facture"]) == 1
        assert self._comptes_et_montants(
            decoupe["paiements_de_la_facture"], "compte"
        ) == [("512100", 500)]
        assert self._virements(decoupe) == [("419100", "512100", 1000)]
        assert decoupe["paiements_divers"] == []

    def test_recharge_seule_sans_ligne_de_facture(self):
        """
        Une recharge seule de 10,00 € en espèces : aucune ligne de facture, aucun
        paiement de facture, un virement 419100 → 530000.
        / A top-up alone: no invoice, one transfer.
        """
        vente = self._vendre(
            [
                {
                    "pricesold": self._tarif_de_recharge(),
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("0"),
                }
            ],
            [{"moyen": PaymentMethod.CASH, "montant": 1000}],
        )

        decoupe = self._decouper(vente)

        assert decoupe["lignes_de_la_facture"] == []
        assert decoupe["paiements_de_la_facture"] == []
        assert self._virements(decoupe) == [("419100", "530000", 1000)]

    def test_biere_payee_en_monnaie_locale(self):
        """
        Une bière payée en monnaie locale : le paiement de la facture va au compte de
        la monnaie (419100 sans correspondance propre), aucun virement.
        / A beer paid in local currency: the invoice payment goes to its account.
        """
        monnaie_locale = self._monnaie("Monnaie locale", Asset.TLF)
        vente = self._vendre(
            [self._biere()],
            [
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 500,
                    "asset": monnaie_locale.uuid,
                }
            ],
        )

        decoupe = self._decouper(vente)

        assert self._comptes_et_montants(
            decoupe["paiements_de_la_facture"], "compte"
        ) == [("419100", 500)]
        assert decoupe["virements"] == []

    def test_recharge_offerte_paiement_divers_623400(self):
        """
        Une recharge cadeau de 10,00 € entièrement offerte : pas de facture, pas de
        virement, un paiement divers de −1000 sur la banque des recharges (419100),
        contrepartie 623400.
        / A fully offered top-up: one various payment, 623400.
        """
        tarif_de_la_recharge_cadeau = creer_tarif_vendu(
            nom="Recharge cadeau",
            prix_en_euros="10.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_CADEAU,
        )
        vente = self._vendre(
            [
                {
                    "pricesold": tarif_de_la_recharge_cadeau,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("0"),
                    "offert_en_totalite": True,
                }
            ],
            None,
        )

        decoupe = self._decouper(vente)

        assert decoupe["lignes_de_la_facture"] == []
        assert decoupe["virements"] == []
        assert self._paiements_divers(decoupe) == [("419100", -1000, "623400")]

    def test_vidage_jetons_repris_et_argent_rendu(self):
        """
        Une carte vidée : 7,00 € de monnaie locale rendus en espèces et 2,00 € de jetons
        cadeau repris. Un paiement divers de +200 sur la banque des jetons (419100),
        contrepartie 623400 ; un virement de 700 de la caisse (530000) vers la banque
        de la monnaie (419100).
        / An emptied card: tokens taken back, cash given back.
        """
        monnaie_locale = self._monnaie("Monnaie locale", Asset.TLF)
        jetons_cadeau = self._monnaie("Jetons", Asset.TNF)
        vente = self._vendre(
            [
                {
                    "pricesold": tarif_vendu_d_un_produit_systeme(
                        NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE
                    ),
                    "quantite": Decimal("1"),
                    "prix_unitaire": 200,
                    "taux_tva": Decimal("0"),
                    "hors_chiffre_affaires": True,
                }
            ],
            [
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 700,
                    "asset": monnaie_locale.uuid,
                },
                {
                    "moyen": PaymentMethod.LOCAL_GIFT,
                    "montant": 200,
                    "asset": jetons_cadeau.uuid,
                },
                {"moyen": PaymentMethod.CASH, "montant": -700},
            ],
            nature=Vente.Nature.VIDAGE_CARTE,
        )

        decoupe = self._decouper(vente)

        assert decoupe["nature"] == "card_emptying"
        assert decoupe["lignes_de_la_facture"] == []
        assert self._paiements_divers(decoupe) == [("419100", 200, "623400")]
        assert self._virements(decoupe) == [("530000", "419100", 700)]

    def test_ecart_stripe_en_moins_paiement_divers_658000(self):
        """
        Un billet de 10,00 € payé par Stripe, qui encaisse 9,98 € : la facture vaut
        1000, payée 1000 sur Stripe (517100), et l'écart est un paiement divers de −2
        sur Stripe, contrepartie 658000.
        / A Stripe ticket with a −2 gap: invoice 1000, one various payment.
        """
        from BaseBillet.services_vente import (
            ajouter_article,
            ajouter_l_article_d_ecart_d_encaissement,
        )

        tarif_du_billet = creer_tarif_vendu(
            nom="Billet",
            prix_en_euros="10.00",
            taux_tva="5.50",
            categorie_article=Product.BILLET,
        )
        vente = ouvrir_vente(origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE)
        ajouter_article(
            vente,
            pricesold=tarif_du_billet,
            quantite=Decimal("1"),
            prix_unitaire=1000,
            taux_tva=Decimal("5.5"),
        )
        ajouter_l_article_d_ecart_d_encaissement(vente, -2)
        ajouter_reglement(vente, moyen=PaymentMethod.STRIPE_NOFED, montant=998)
        vente = encaisser_vente(vente)
        verifier_egalites(vente)

        decoupe = self._decouper(vente)

        assert self._comptes_et_montants(
            decoupe["paiements_de_la_facture"], "compte"
        ) == [("517100", 1000)]
        assert self._paiements_divers(decoupe) == [("517100", -2, "658000")]
        assert decoupe["virements"] == []

    def test_correction_especes_vers_cb_un_seul_paiement_cb(self):
        """
        Une bière payée en espèces, corrigée en CB : la vente corrigée a un seul
        paiement, 500 en CB. La vente CORRECTION elle-même n'est pas à facturer.
        / A cash beer corrected to card: one card payment.
        """
        vente = self._vendre(
            [self._biere()], [{"moyen": PaymentMethod.CASH, "montant": 500}]
        )
        vente_de_correction = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.CORRECTION,
            vente_liee=vente,
        )
        ajouter_reglement(vente_de_correction, moyen=PaymentMethod.CASH, montant=-500)
        ajouter_reglement(vente_de_correction, moyen=PaymentMethod.CC, montant=500)
        encaisser_vente(vente_de_correction)

        decoupe = self._decouper(vente)

        paiements = self._comptes_et_montants(
            decoupe["paiements_de_la_facture"], "compte"
        )
        assert paiements == [("512100", 500)]
        assert decoupe["virements"] == []

    # ------------------------------------------------------------------
    # L'acheteur, les ventes vides, les refus / Buyer, empty sales, refusals
    # ------------------------------------------------------------------

    def test_client_de_la_vente(self):
        """
        Une vente avec un client : `client` est ce user.
        / A sale with a customer: `client` is that user.
        """
        acheteuse = creer_utilisateur()
        vente = self._vendre(
            [self._biere()],
            [{"moyen": PaymentMethod.CASH, "montant": 500}],
            client=acheteuse,
        )

        assert self._decouper(vente)["client"] == acheteuse

    def test_carte_liee_apres_la_vente_reste_client_de_passage(self):
        """
        Une vente anonyme payée avec une carte qui n'avait pas de titulaire ; la carte
        est liée à un user APRÈS : la vente reste au client de passage (D4).
        / An anonymous sale whose card is linked to a user later stays anonymous.
        """
        identifiant_de_la_carte = identifiant_unique()[:8].upper()
        carte = CarteCashless.objects.create(
            tag_id=identifiant_de_la_carte, number=identifiant_de_la_carte
        )
        vente = self._vendre(
            [self._biere()],
            [{"moyen": PaymentMethod.CASH, "montant": 500}],
            carte=carte,
        )
        carte.user = creer_utilisateur()
        carte.save()

        assert self._decouper(vente)["client"] is None

    def test_vente_sans_montant_rend_none(self):
        """
        Une bière offerte par le bouton OFFRIR : rien à écrire, None.
        / A beer gifted with the GIFT button: None.
        """
        vente = self._vendre([self._biere(offert_en_totalite=True)], None)

        assert self._decouper(vente) is None

    def test_reglements_qui_ne_couvrent_pas_les_articles_leve_une_erreur(self):
        """
        Une bière de 5,00 € dont le seul règlement est en points (sans compte) :
        `RepartitionImpossible`, avec le numéro de la vente.
        / A beer paid only in points: RepartitionImpossible naming the sale.
        """
        points = self._monnaie("Points", Asset.FID)
        vente = self._vendre(
            [self._biere()],
            [
                {
                    "moyen": PaymentMethod.NON_MONETAIRE,
                    "montant": 500,
                    "asset": points.uuid,
                }
            ],
        )

        try:
            self._decouper(vente)
            assert False, "RepartitionImpossible attendue"
        except RepartitionImpossible as erreur:
            assert f"n° {vente.numero}" in str(erreur)

    # ------------------------------------------------------------------
    # La fabrique des tests donne un compte à ses produits
    # / The test factory gives its products an account
    # ------------------------------------------------------------------

    def test_fabrique_donne_un_compte_au_produit_sans_compte(self):
        """
        Un article de caisse créé par `creer_tarif_vendu` sans catégorie a quand même un
        compte : la fabrique le range dans la catégorie de caisse de test (707000). Une
        vente de test restée dans la base de dev ne bloque ainsi jamais l'export de la
        vraie journée.
        / A test product gets the test POS category (707000) when it has no account.
        """
        produit = creer_tarif_vendu(nom="Jus", methode_caisse=Product.VENTE).productsold.product

        assert produit.categorie_pos.name == NOM_DE_LA_CATEGORIE_DE_CAISSE_DE_TEST
        assert compte_pour_produit(produit).numero_de_compte == "707000"

    def test_fabrique_ne_touche_pas_un_produit_qui_a_deja_un_compte(self):
        """
        Un billet a son compte par son type (706000) : la fabrique ne lui pose pas de
        catégorie de caisse.
        / A ticket has its account by type: no POS category added.
        """
        billet = creer_tarif_vendu(
            nom="Billet", categorie_article=Product.BILLET
        ).productsold.product

        assert billet.categorie_pos is None
        assert compte_pour_produit(billet).numero_de_compte == "706000"

    def test_fabrique_sans_compte_sur_demande(self):
        """
        `avec_compte=False` : le produit reste sans compte, pour les tests du refus.
        / avec_compte=False keeps the product without account.
        """
        planche = creer_tarif_vendu(
            nom="Planche", methode_caisse=Product.VENTE, avec_compte=False
        ).productsold.product

        assert planche.categorie_pos is None
        try:
            compte_pour_produit(planche)
            assert False, "CompteComptableManquant attendue"
        except CompteComptableManquant:
            pass
