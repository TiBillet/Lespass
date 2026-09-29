"""
tests/pytest/test_hors_argent_offerts.py
Les lignes « offertes » (FREE) restent dans la cloture mais sortent de tout calcul
d'argent du ticket X / Z.
/ "Gifted" lines (FREE) stay in the closure but leave every money computation.

LOCALISATION : tests/pytest/test_hors_argent_offerts.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
A la caisse, une ligne offerte garde sa valeur (amount = prix unitaire) avec le
moyen de paiement FREE. Deux cas existent :
- un article offert (bouton OFFRIR du mode gerant) ;
- une recharge cadeau (le lieu credite de la monnaie cadeau sur une carte).

Ce n'est pas de l'argent encaisse. Le rapport de caisse (RapportComptableService)
les exclut donc du total, de la TVA, du detail des ventes, du CA par point de
vente, du panier moyen, du total des recharges et de l'ecriture comptable (FEC).
Il les montre a part : section « Offerts » et ligne « Cadeau emis (hors argent) ».

Les recharges et les ventes passent par la vraie route de paiement. Les articles
offerts sont crees par la fonction de la caisse qui ecrit les lignes
(`_creer_lignes_articles`, code "gift") : c'est elle qu'appelle le bouton OFFRIR.

Schema de test dedie : le rapport lit toutes les ventes du lieu dans la periode.
/ Dedicated test schema: the report reads every sale of the venue in the period.

Lancement / Run:
    make test ARGS="tests/pytest/test_hors_argent_offerts.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from datetime import timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest import mock  # noqa: E402

from django.core.management import call_command  # noqa: E402
from django.db import connection, transaction  # noqa: E402
from django.http import QueryDict  # noqa: E402
from django.utils import timezone  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

from AuthBillet.models import TibilletUser, Wallet  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    CategorieProduct,
    Configuration,
    LigneArticle,
    PaymentMethod,
    Price,
    Product,
    Tva,
)
from QrcodeCashless.models import CarteCashless  # noqa: E402
from fedow_core.models import Asset  # noqa: E402
from fedow_core.services import AssetService  # noqa: E402
from laboutik.models import (  # noqa: E402
    ClotureCaisse,
    CompteComptable,
    LaboutikConfiguration,
    PointDeVente,
)
from laboutik.reports import RapportComptableService  # noqa: E402

PRIX_VIN_CENTIMES = 500


class TestLignesHorsArgent(FastTenantTestCase):
    """Les lignes FREE sortent des calculs d'argent du rapport de caisse.
    / FREE lines leave the register report's money computations."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_hors_argent"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-hors-argent.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test hors argent"

    def setUp(self):
        """Un point de vente, un vin a TVA 20 %, deux monnaies, une carte.
        / One point of sale, a 20 % VAT wine, two currencies, one card."""
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

        # Plan comptable du lieu : comptes de vente, de TVA et de tresorerie,
        # necessaires a l'ecriture FEC.
        # / Venue chart of accounts, needed for the FEC entry.
        call_command(
            "charger_plan_comptable", schema=self.tenant.schema_name, jeu="bar_resto"
        )
        compte_de_vente = CompteComptable.objects.get(numero_de_compte="7072000")

        # Le taux d'une ligne vient de Product.tva (PIEGES 9.66).
        # / A line's rate comes from Product.tva.
        tva_a_vingt, _cree = Tva.objects.get_or_create(tva_rate=Decimal("20"))
        categorie = CategorieProduct.objects.create(
            name="Boissons hors argent", compte_comptable=compte_de_vente
        )
        self.vin = Product.objects.create(
            name="Vin hors argent",
            methode_caisse=Product.VENTE,
            categorie_pos=categorie,
            tva=tva_a_vingt,
            prix_achat=100,
        )
        Price.objects.create(product=self.vin, name="Verre", prix=Decimal("5.00"))

        self.point_de_vente = PointDeVente.objects.create(
            name="Comptoir hors argent",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.point_de_vente.products.add(self.vin)

        # Les monnaies du lieu. Leur creation cree aussi les produits de
        # recharge (signal fedow_core) : « Recharge cadeau » et « Recharge euros ».
        # / Creating the currencies also creates their top-up products.
        wallet_du_lieu = Wallet.objects.create(
            origin=self.tenant, name="Wallet lieu hors argent"
        )
        self.asset_cadeau = AssetService.creer_asset(
            tenant=self.tenant,
            name="Cadeau hors argent",
            category=Asset.TNF,
            currency_code="EUR",
            wallet_origin=wallet_du_lieu,
        )
        self.asset_local = AssetService.creer_asset(
            tenant=self.tenant,
            name="Monnaie hors argent",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=wallet_du_lieu,
        )
        self.recharge_cadeau = Product.objects.get(asset=self.asset_cadeau)
        self.recharge_euros = Product.objects.get(asset=self.asset_local)

        client_de_la_carte = TibilletUser.objects.create(
            email="client-hors-argent@tibillet.localhost",
            username="client-hors-argent@tibillet.localhost",
        )
        wallet_du_client = Wallet.objects.create(
            origin=self.tenant, name="Wallet client hors argent"
        )
        client_de_la_carte.wallet = wallet_du_client
        client_de_la_carte.save()
        self.carte = CarteCashless.objects.create(
            tag_id="HAR1AAAA", number="HAR1AAAA", user=client_de_la_carte
        )

        # Caissier : admin du lieu, session navigateur.
        # / Cashier: venue admin, browser session.
        self.caissier, _cree = TibilletUser.objects.get_or_create(
            email="caissier-hors-argent@tibillet.localhost",
            defaults={
                "username": "caissier-hors-argent@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        self.caissier.client_admin.add(self.tenant)
        self.navigateur = TenantClient(self.tenant)
        self.navigateur.force_login(self.caissier)

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _payer(self, moyen, cle_article, quantite, total_centimes, tag_id=None):
        """Encaisse par la VRAIE route de paiement, reseau federe coupe.
        / Collects through the REAL payment route, federated network off."""
        donnees = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "moyen_paiement": moyen,
            "total": str(total_centimes),
            "given_sum": "0",
            f"repid-{cle_article}": str(quantite),
        }
        if tag_id is not None:
            donnees["tag_id"] = tag_id
        with (
            mock.patch("laboutik.views.FedowConfig") as configuration_fedow,
            mock.patch("laboutik.views.FedowAPI"),
        ):
            configuration_fedow.get_solo.return_value.can_fedow.return_value = False
            reponse = self.navigateur.post("/laboutik/paiement/payer/", data=donnees)
        assert reponse.status_code == 200, reponse.content.decode()[:400]
        return reponse

    def _cle_du_tarif(self, produit, nom_du_tarif):
        """Cle de panier « produit--tarif » d'un article a plusieurs tarifs.
        / Cart key "product--price" of a multi-price item."""
        tarif = produit.prices.get(name=nom_du_tarif)
        return f"{produit.uuid}--{tarif.uuid}"

    def _offrir_des_vins(self, quantite):
        """Cree les lignes d'un panier offert, comme le bouton OFFRIR.
        / Creates the lines of a gifted cart, like the GIFT button."""
        from laboutik.views import _creer_lignes_articles, _extraire_articles_du_panier

        donnees = QueryDict(mutable=True)
        donnees[f"repid-{self.vin.uuid}"] = str(quantite)
        articles = _extraire_articles_du_panier(donnees, self.point_de_vente)
        with transaction.atomic():
            _creer_lignes_articles(articles, "gift", point_de_vente=self.point_de_vente)

    def _vendre_un_vin_en_especes(self):
        self._payer("espece", self.vin.uuid, 1, PRIX_VIN_CENTIMES)

    def _rapport(self):
        maintenant = timezone.now()
        return RapportComptableService(
            None, maintenant - timedelta(hours=1), maintenant + timedelta(hours=1)
        )

    # ------------------------------------------------------------------
    # Articles offerts / Gifted items
    # ------------------------------------------------------------------

    def test_une_ligne_offerte_est_creee_sans_tva(self):
        """Une ligne offerte n'est pas une vente en argent : TVA 0.
        / A gifted line is not a money sale: VAT 0."""
        self._offrir_des_vins(2)

        ligne = LigneArticle.objects.get(payment_method=PaymentMethod.FREE)
        assert ligne.amount == PRIX_VIN_CENTIMES
        assert ligne.vat == 0, f"TVA de la ligne offerte : {ligne.vat}"

    def test_un_article_offert_n_entre_pas_dans_la_tva(self):
        """2 vins offerts + 1 vendu : la TVA porte sur 5,00 € seulement.
        / 2 gifted + 1 sold: VAT covers 5.00 € only."""
        self._offrir_des_vins(2)
        self._vendre_un_vin_en_especes()

        tva = self._rapport().calculer_tva()

        total_ttc_des_taux = sum(taux["total_ttc"] for taux in tva.values())
        assert total_ttc_des_taux == PRIX_VIN_CENTIMES, tva

    def test_un_article_offert_sort_du_detail_des_ventes(self):
        """Le detail des ventes ne compte que le vin vendu.
        / The sales detail only counts the sold wine."""
        self._offrir_des_vins(2)
        self._vendre_un_vin_en_especes()

        detail = self._rapport().calculer_detail_ventes()

        article = detail["Boissons hors argent"]["articles"][0]
        assert article["qty_vendus"] == 1
        assert article["total_ttc"] == PRIX_VIN_CENTIMES

    def test_la_section_offerts_donne_quantite_et_valeur(self):
        """Section « Offerts » : 2 vins, valeur 10,00 €, cout 2,00 €.
        / "Gifted" section: 2 wines, value 10.00 €, cost 2.00 €."""
        self._offrir_des_vins(2)
        self._vendre_un_vin_en_especes()

        offerts = self._rapport().calculer_offerts()

        assert offerts["qty_totale"] == 2
        assert offerts["valeur_totale"] == 1000
        assert offerts["par_produit"] == [
            {"nom": "Vin hors argent", "qty": 2, "valeur": 1000, "cout_achat": 200}
        ]

    def test_le_total_du_rapport_ignore_les_offerts(self):
        """Le total encaisse reste 5,00 € (non-regression).
        / The collected total stays 5.00 € (non-regression)."""
        self._offrir_des_vins(2)
        self._vendre_un_vin_en_especes()

        assert self._rapport().calculer_totaux_par_moyen()["total"] == PRIX_VIN_CENTIMES

    def test_un_article_offert_ne_compte_pas_dans_le_ca_du_point_de_vente(self):
        """CA du point de vente : 5,00 €.
        / Point of sale revenue: 5.00 €."""
        self._offrir_des_vins(2)
        self._vendre_un_vin_en_especes()

        ventilation = self._rapport().calculer_ventilation_par_pv()

        assert ventilation == [
            {
                "nom": "Comptoir hors argent",
                "uuid": str(self.point_de_vente.uuid),
                "total_ttc": PRIX_VIN_CENTIMES,
            }
        ]

    def test_l_ecriture_comptable_reste_equilibree(self):
        """FEC d'une cloture avec des offerts : debits = credits, sans alerte.
        / FEC of a closure with gifted items: debits = credits, no warning."""
        from laboutik.ventilation import (
            charger_categories_par_nom,
            charger_comptes_tva,
            charger_mappings_paiement,
            ventiler_cloture,
        )

        self._offrir_des_vins(2)
        self._vendre_un_vin_en_especes()
        rapport = self._rapport().generer_rapport_complet()
        cloture = ClotureCaisse.objects.create(
            point_de_vente=self.point_de_vente,
            responsable=self.caissier,
            datetime_ouverture=timezone.now(),
            datetime_cloture=timezone.now(),
            total_especes=PRIX_VIN_CENTIMES,
            total_general=PRIX_VIN_CENTIMES,
            nombre_transactions=2,
            rapport_json=rapport,
        )

        lignes, avertissements = ventiler_cloture(
            cloture,
            charger_mappings_paiement(),
            charger_categories_par_nom(),
            charger_comptes_tva(),
        )

        total_debits = sum(
            ligne["montant_centimes"] for ligne in lignes if ligne["sens"] == "D"
        )
        total_credits = sum(
            ligne["montant_centimes"] for ligne in lignes if ligne["sens"] == "C"
        )
        assert total_debits == PRIX_VIN_CENTIMES
        assert total_debits == total_credits
        assert avertissements == []

    def test_le_ticket_x_affiche_les_offerts(self):
        """L'ecran Ventes (ticket X) montre la section « Offerts ».
        / The Sales screen (X ticket) shows the "Gifted" section."""
        self._offrir_des_vins(2)
        self._vendre_un_vin_en_especes()

        reponse = self.navigateur.get("/laboutik/caisse/recap-en-cours/")

        contenu = reponse.content.decode()
        assert reponse.status_code == 200
        assert 'data-testid="recap-offerts"' in contenu

    def _cloture_avec_des_offerts(self):
        """Une cloture dont le rapport contient 2 vins offerts et 1 vendu.
        / A closure whose report holds 2 gifted wines and 1 sold."""
        self._offrir_des_vins(2)
        self._vendre_un_vin_en_especes()
        return ClotureCaisse.objects.create(
            point_de_vente=self.point_de_vente,
            responsable=self.caissier,
            datetime_ouverture=timezone.now(),
            datetime_cloture=timezone.now(),
            total_especes=PRIX_VIN_CENTIMES,
            total_general=PRIX_VIN_CENTIMES,
            nombre_transactions=2,
            rapport_json=self._rapport().generer_rapport_complet(),
        )

    def test_le_ticket_z_imprime_mentionne_les_offerts(self):
        """Le ticket Z imprime porte « Offerts : 2 articles, valeur 10.00 EUR ».
        / The printed Z ticket mentions the gifted items."""
        from laboutik.printing.formatters import formatter_ticket_cloture

        ticket = formatter_ticket_cloture(self._cloture_avec_des_offerts())

        assert "Offerts: 2 articles, valeur 10.00 EUR" in ticket["footer"]
        assert ticket["total"]["amount"] == PRIX_VIN_CENTIMES

    def test_l_export_csv_de_la_cloture_liste_les_offerts(self):
        """L'export CSV de la cloture a une section « Offerts (hors argent) ».
        / The closure CSV export has a "Gifted" section."""
        from laboutik.csv_export import generer_csv_cloture

        contenu_csv = generer_csv_cloture(self._cloture_avec_des_offerts())

        assert "Offerts (hors argent)" in contenu_csv
        assert "Vin hors argent;2.0;10.00" in contenu_csv

    # ------------------------------------------------------------------
    # Recharges cadeau / Gift top-ups
    # ------------------------------------------------------------------

    def test_une_recharge_cadeau_sort_du_total_des_recharges(self):
        """Recharge cadeau 10 € + recharge euros 20 € : 20 € encaisses, 10 € emis.
        / Gift top-up 10 € + euro top-up 20 €: 20 € collected, 10 € issued."""
        self._payer(
            "nfc",
            self._cle_du_tarif(self.recharge_cadeau, "10"),
            1,
            1000,
            tag_id=self.carte.tag_id,
        )
        self._payer(
            "espece",
            self._cle_du_tarif(self.recharge_euros, "10"),
            2,
            2000,
            tag_id=self.carte.tag_id,
        )

        recharges = self._rapport().calculer_recharges()

        assert recharges["total"] == 2000
        assert recharges["cadeau_emis"] == 1000

    def test_une_recharge_cadeau_ne_gonfle_pas_le_panier_moyen(self):
        """Recharge cadeau 10 € puis achat de 5 € : panier moyen 5 €, aucune recharge payee.
        / Gift top-up then a 5 € purchase: average basket 5 €, no paid top-up."""
        self._payer(
            "nfc",
            self._cle_du_tarif(self.recharge_cadeau, "10"),
            1,
            1000,
            tag_id=self.carte.tag_id,
        )
        self._payer(
            "nfc", self.vin.uuid, 1, PRIX_VIN_CENTIMES, tag_id=self.carte.tag_id
        )

        habitus = self._rapport().calculer_habitus()

        assert habitus["panier_moyen"] == PRIX_VIN_CENTIMES
        assert habitus["recharge_mediane"] == 0

    # ------------------------------------------------------------------
    # Correction de moyen de paiement / Payment method correction
    # ------------------------------------------------------------------

    def test_une_ligne_offerte_ne_peut_pas_etre_corrigee_en_especes(self):
        """Corriger une recharge cadeau en especes ferait apparaitre de l'argent
        jamais encaisse : refuse.
        / Correcting a gift top-up into cash would create money: refused."""
        self._payer(
            "nfc",
            self._cle_du_tarif(self.recharge_cadeau, "10"),
            1,
            1000,
            tag_id=self.carte.tag_id,
        )
        ligne_offerte = LigneArticle.objects.get(payment_method=PaymentMethod.FREE)

        reponse = self.navigateur.post(
            "/laboutik/paiement/corriger_moyen_paiement/",
            data={
                "ligne_uuid": str(ligne_offerte.uuid),
                "nouveau_moyen": PaymentMethod.CASH,
                "raison": "test",
            },
        )

        assert reponse.status_code == 400
        ligne_offerte.refresh_from_db()
        assert ligne_offerte.payment_method == PaymentMethod.FREE

    def test_le_mapping_fec_de_l_admin_ne_propose_pas_offert(self):
        """Un moyen hors argent n'a pas de compte de tresorerie : absent du menu.
        / A non-money method has no cash account: not offered in the menu."""
        reponse = self.navigateur.get("/admin/laboutik/mappingmoyendepaiement/add/")

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        assert 'value="CA"' in contenu
        assert 'value="NA"' not in contenu

    # ------------------------------------------------------------------
    # Bouton OFFRIR en mode gerant / GIFT button in manager mode
    # ------------------------------------------------------------------

    def _carte_primaire(self, tag_id, mode_gerant):
        """Une carte primaire (carte du caissier) avec acces au point de vente.
        / A primary card (cashier card) with access to the point of sale."""
        from laboutik.models import CartePrimaire

        carte_du_caissier = CarteCashless.objects.create(tag_id=tag_id, number=tag_id)
        carte_primaire = CartePrimaire.objects.create(
            carte=carte_du_caissier, edit_mode=mode_gerant
        )
        carte_primaire.points_de_vente.add(self.point_de_vente)
        return carte_du_caissier

    def _demander_les_moyens_de_paiement(self, tag_id_cm, cle_article, quantite):
        return self.navigateur.post(
            "/laboutik/paiement/moyens_paiement/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                "tag_id_cm": tag_id_cm,
                f"repid-{cle_article}": str(quantite),
            },
        )

    def _offrir(self, tag_id_cm, cle_article, quantite, total_centimes, tag_id=None):
        donnees = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "moyen_paiement": "gift",
            "tag_id_cm": tag_id_cm,
            "total": str(total_centimes),
            "given_sum": "0",
            f"repid-{cle_article}": str(quantite),
        }
        if tag_id is not None:
            donnees["tag_id"] = tag_id
        return self.navigateur.post("/laboutik/paiement/payer/", data=donnees)

    def test_la_tuile_offrir_apparait_pour_une_carte_en_mode_gerant(self):
        """Carte primaire en mode gerant : la tuile OFFRIR est proposee, avec le
        total du panier pour l'ecran de confirmation.
        / Manager-mode primary card: the GIFT tile is offered, with the total."""
        carte_du_gerant = self._carte_primaire("GER1AAAA", mode_gerant=True)

        reponse = self._demander_les_moyens_de_paiement(
            carte_du_gerant.tag_id, self.vin.uuid, 2
        )

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        assert 'data-testid="paiement-btn-offrir"' in contenu
        assert (
            "method=gift&amp;total=10" in contenu or "method=gift&total=10" in contenu
        )

    def test_pas_de_tuile_offrir_sans_mode_gerant(self):
        """Carte primaire sans mode gerant : pas de tuile OFFRIR.
        / Primary card without manager mode: no GIFT tile."""
        carte_du_caissier = self._carte_primaire("CAI1AAAA", mode_gerant=False)

        reponse = self._demander_les_moyens_de_paiement(
            carte_du_caissier.tag_id, self.vin.uuid, 2
        )

        assert reponse.status_code == 200
        assert 'data-testid="paiement-btn-offrir"' not in reponse.content.decode()

    def test_le_gerant_offre_un_panier_payant(self):
        """2 vins offerts : une ligne FREE au prix du vin, quantite 2, sans TVA.
        / 2 wines gifted: one FREE line at the wine price, qty 2, no VAT."""
        carte_du_gerant = self._carte_primaire("GER2AAAA", mode_gerant=True)

        reponse = self._offrir(carte_du_gerant.tag_id, self.vin.uuid, 2, 1000)

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        ligne = LigneArticle.objects.get(payment_method=PaymentMethod.FREE)
        assert ligne.amount == PRIX_VIN_CENTIMES
        assert ligne.qty == 2
        assert ligne.vat == 0

    def test_offrir_est_refuse_sans_mode_gerant(self):
        """Un POST « gift » sur un panier payant, sans mode gerant : refuse.
        / A "gift" POST on a paying cart without manager mode: refused."""
        carte_du_caissier = self._carte_primaire("CAI2AAAA", mode_gerant=False)

        reponse = self._offrir(carte_du_caissier.tag_id, self.vin.uuid, 2, 1000)

        assert reponse.status_code == 400
        assert not LigneArticle.objects.filter(
            payment_method=PaymentMethod.FREE
        ).exists()

    def test_offrir_une_recharge_en_euros_est_refuse(self):
        """Offrir une recharge en euros creerait de la monnaie remboursable : refuse.
        / Gifting a euro top-up would create refundable money: refused."""
        carte_du_gerant = self._carte_primaire("GER3AAAA", mode_gerant=True)

        reponse = self._offrir(
            carte_du_gerant.tag_id,
            self._cle_du_tarif(self.recharge_euros, "10"),
            1,
            1000,
            tag_id=self.carte.tag_id,
        )

        assert reponse.status_code == 400
        assert not LigneArticle.objects.exists()

    def test_offrir_un_retour_de_consigne_est_refuse(self):
        """Offrir un retour de consigne n'a pas de sens (un remboursement) : refuse.
        / Gifting a deposit return makes no sense (it is a refund): refused."""
        carte_du_gerant = self._carte_primaire("GER4AAAA", mode_gerant=True)
        retour_consigne = Product.objects.create(
            name="Retour gobelet hors argent",
            methode_caisse=Product.RETOUR_CONSIGNE,
            asset=self.asset_local,
            publish=True,
        )
        Price.objects.create(
            product=retour_consigne, name="Gobelet", prix=Decimal("-1.00"), publish=True
        )
        self.point_de_vente.products.add(retour_consigne)

        reponse = self._offrir(carte_du_gerant.tag_id, retour_consigne.uuid, 1, -100)

        assert reponse.status_code == 400
        assert not LigneArticle.objects.exists()

    def test_la_tuile_offrir_apparait_pour_une_adhesion_identifiee(self):
        """Adhesion : apres l'identification du client, la tuile OFFRIR est proposee
        au gerant.
        / Membership: after client identification, the GIFT tile is offered."""
        carte_du_gerant = self._carte_primaire("GER5AAAA", mode_gerant=True)
        adhesion = Product.objects.create(
            name="Adhesion hors argent",
            categorie_article=Product.ADHESION,
            publish=True,
        )
        Price.objects.create(product=adhesion, name="Annuelle", prix=Decimal("10.00"))
        self.point_de_vente.products.add(adhesion)

        reponse = self.navigateur.post(
            "/laboutik/paiement/identifier_client/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                "tag_id_cm": carte_du_gerant.tag_id,
                "email_adhesion": "adherent-offert@tibillet.localhost",
                "prenom_adhesion": "Ada",
                "nom_adhesion": "Offerte",
                "panier_a_recharges": "False",
                "panier_a_adhesions": "True",
                "panier_a_billets": "False",
                "moyens_paiement": "espece,carte_bancaire",
                f"repid-{adhesion.uuid}": "1",
            },
        )

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        assert 'data-testid="paiement-btn-offrir"' in contenu

    def test_une_commande_de_table_ne_peut_pas_etre_offerte_par_un_post(self):
        """Le paiement d'une commande de table n'accepte que ses moyens de paiement :
        un POST « gift » est refuse.
        / Table-order payment only accepts its methods: a "gift" POST is refused."""
        from laboutik.models import ArticleCommandeSauvegarde, CommandeSauvegarde

        commande = CommandeSauvegarde.objects.create(
            statut=CommandeSauvegarde.OPEN,
            responsable=self.caissier,
        )
        ArticleCommandeSauvegarde.objects.create(
            commande=commande,
            product=self.vin,
            price=self.vin.prices.first(),
            qty=2,
            statut=ArticleCommandeSauvegarde.EN_ATTENTE,
        )

        reponse = self.navigateur.post(
            f"/laboutik/commande/payer/{commande.uuid}/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                "moyen_paiement": "gift",
                "given_sum": "",
            },
        )

        assert reponse.status_code == 400
        assert not LigneArticle.objects.exists()
