"""
tests/pytest/test_vente_en_points.py
Vente en points ou en temps a la caisse : le moyen de paiement « non monetaire » (NM).
/ Selling in points or time at the register: the "non-monetary" payment method (NM).

LOCALISATION : tests/pytest/test_vente_en_points.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
Un lieu peut vendre un article en points de fidelite (monnaie FID) ou en heures
(monnaie temps TIM). Ce n'est pas de l'argent.

La vente est enregistree avec le moyen NM. La ligne garde le prix en unites de
la monnaie (centiemes : 300 points = 30000), et une TVA a 0.

Le rapport de caisse (RapportComptableService) exclut ces lignes de tout calcul
d'argent : total, TVA, section « Offerts ». Il les montre a part, dans la section
« Non monetaire », une ligne par nom de monnaie.

Dans l'admin, un tarif en points n'est accepte que sur un article de vente ou une
adhesion.

A la caisse, les tarifs en points sont proposes (apres les tarifs en euros). Un panier
ne contient qu'une seule monnaie, se paie uniquement par carte NFC, et le solde est
compare a la somme du panier. Les commandes de table et la tireuse refusent les
tarifs en points.

Les paiements passent par la VRAIE route de la caisse, reseau federe coupe.

Schema de test dedie : le rapport lit toutes les ventes du lieu dans la periode.
/ Dedicated test schema: the report reads every sale of the venue in the period.

Lancement / Run:
    make test ARGS="tests/pytest/test_vente_en_points.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import csv  # noqa: E402
import io  # noqa: E402
import re  # noqa: E402
import uuid as uuid_module  # noqa: E402
from datetime import timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest import mock  # noqa: E402

from django.core.management import call_command  # noqa: E402
from django.db import connection, transaction  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.utils import timezone  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

from Administration.admin.products import POSPriceInline  # noqa: E402
from Administration.admin.site import staff_admin_site  # noqa: E402
from AuthBillet.models import TibilletUser, Wallet  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    CategorieProduct,
    Configuration,
    LigneArticle,
    Membership,
    PaymentMethod,
    POSProduct,
    Price,
    PriceSold,
    Product,
    ProductSold,
    SaleOrigin,
    Tva,
)
from QrcodeCashless.models import CarteCashless  # noqa: E402
from BaseBillet.models_vente import Reglement, Vente  # noqa: E402
from BaseBillet.services_vente import (  # noqa: E402
    ajouter_article,
    ajouter_reglement,
    encaisser_vente,
    ouvrir_vente,
)
import comptabilite.tasks  # noqa: E402
from comptabilite.models import ClotureCaisse as ClotureCaisseUnique  # noqa: E402
from comptabilite.rapport import RapportDesVentes  # noqa: E402
from fedow_core.models import Asset  # noqa: E402
from fabriques_ecran import (  # noqa: E402
    texte_sans_espaces_en_trop,
    textes_des_elements,
)
from fedow_core.services import AssetService, WalletService  # noqa: E402
from laboutik.models import (  # noqa: E402
    ArticleCommandeSauvegarde,
    CartePrimaire,
    CommandeSauvegarde,
    CompteComptable,
    LaboutikConfiguration,
    PointDeVente,
)
from laboutik.reports import RapportComptableService  # noqa: E402

# 300 points coutent 30000 unites : la caisse compte les points en centiemes.
# / 300 points cost 30000 units: the register counts points in hundredths.
PRIX_PINS_EN_CENTIEMES_DE_POINTS = 30000
PRIX_VIN_CENTIMES = 500


class TestVenteEnPoints(FastTenantTestCase):
    """Les lignes NM : TVA 0, hors argent, section « Non monetaire ».
    / NM lines: VAT 0, not money, "Non-monetary" section."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_vente_en_points"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-vente-en-points.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test vente en points"

    def setUp(self):
        """Un Pin's et un vin a TVA 20 %, deux monnaies non monetaires, un admin.
        / A pin and a wine at 20 % VAT, two non-monetary currencies, an admin."""
        # Le rollback du test precedent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        # Aucun e-mail de rapport : une clôture journalière n'envoie rien.
        # / No report e-mail: a daily closure sends nothing.
        configuration.rapport_emails = ""
        configuration.save()

        # Le singleton de la caisse doit exister en base (PIEGES 9.86).
        # / The register singleton must exist in the database.
        LaboutikConfiguration.get_solo().save()

        # Plan comptable du lieu : necessaire a l'ecriture FEC.
        # / Venue chart of accounts, needed for the FEC entry.
        call_command("charger_plan_comptable", schema=self.tenant.schema_name)
        compte_de_vente = CompteComptable.objects.get(numero_de_compte="707000")
        categorie = CategorieProduct.objects.create(
            name="Boutique en points", compte_comptable=compte_de_vente
        )

        # Les monnaies du lieu. TLF (euros locaux) sert a verifier qu'une vente en
        # points ne debite jamais d'euros.
        # / The venue currencies. TLF checks that a points sale never debits euros.
        wallet_du_lieu = Wallet.objects.create(
            origin=self.tenant, name="Wallet lieu vente en points"
        )
        self.asset_euros = AssetService.creer_asset(
            tenant=self.tenant,
            name="Monnaie locale en points",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=wallet_du_lieu,
        )
        self.asset_points = AssetService.creer_asset(
            tenant=self.tenant,
            name="Points fidélité",
            category=Asset.FID,
            currency_code="PTS",
            wallet_origin=wallet_du_lieu,
        )
        self.asset_temps = AssetService.creer_asset(
            tenant=self.tenant,
            name="Temps",
            category=Asset.TIM,
            currency_code="TMP",
            wallet_origin=wallet_du_lieu,
        )

        # Le Pin's porte une TVA a 20 % : une ligne en points qui la reprendrait
        # aurait une TVA non nulle.
        # / The pin carries 20 % VAT: a points line that copied it would be non-zero.
        tva_a_vingt, _cree = Tva.objects.get_or_create(tva_rate=Decimal("20"))
        self.pins = self._creer_article(
            "Pin's en points", tva_a_vingt, categorie, "Points", "300.00",
            self.asset_points,
        )
        self.tarif_pins = self.pins.prices.get()
        self.medaille = self._creer_article(
            "Médaille en points", tva_a_vingt, categorie, "Points", "300.00",
            self.asset_points,
        )
        self.machine = self._creer_article(
            "Machine 3D en temps", tva_a_vingt, categorie, "Heure", "1.00",
            self.asset_temps,
        )
        self.vin = self._creer_article(
            "Vin en euros", tva_a_vingt, categorie, "Verre", "5.00", None
        )
        self.tarif_vin = self.vin.prices.get()

        # Biere a deux tarifs : 5 € et 1 heure de benevolat. Le tarif en temps a
        # un ordre PLUS PETIT : sans le tri « euros d'abord », il passerait devant.
        # / Beer with two prices; the time price has a SMALLER order on purpose.
        self.biere = self._creer_article(
            "Bière deux tarifs", tva_a_vingt, categorie, "Pinte", "5.00", None
        )
        self.tarif_biere_euros = self.biere.prices.get()
        self.tarif_biere_temps = Price.objects.create(
            product=self.biere,
            name="Bénévole",
            prix=Decimal("1.00"),
            non_fiduciaire=True,
            asset=self.asset_temps,
            order=50,
        )

        self.adhesion = Product.objects.create(
            name="Adhésion en points",
            categorie_article=Product.ADHESION,
            methode_caisse=Product.ADHESION_POS,
        )
        Price.objects.create(
            product=self.adhesion,
            name="Points",
            prix=Decimal("300.00"),
            non_fiduciaire=True,
            asset=self.asset_points,
        )

        self.point_de_vente = PointDeVente.objects.create(
            name="Comptoir en points",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.point_de_vente.products.add(
            self.pins, self.medaille, self.machine, self.vin, self.biere, self.adhesion
        )

        # La carte du client, avec son portefeuille.
        # / The customer's card, with its wallet.
        self.client_de_la_carte = TibilletUser.objects.create(
            email="client-en-points@tibillet.localhost",
            username="client-en-points@tibillet.localhost",
        )
        self.wallet_du_client = Wallet.objects.create(
            origin=self.tenant, name="Wallet client en points"
        )
        self.client_de_la_carte.wallet = self.wallet_du_client
        self.client_de_la_carte.save()
        self.carte = CarteCashless.objects.create(
            tag_id="PTS1AAAA", number="PTS1AAAA", user=self.client_de_la_carte
        )

        # Admin du lieu : il edite les tarifs et corrige les paiements.
        # / Venue admin: edits prices and corrects payments.
        self.admin_du_lieu, _cree = TibilletUser.objects.get_or_create(
            email="admin-vente-en-points@tibillet.localhost",
            defaults={
                "username": "admin-vente-en-points@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        self.admin_du_lieu.client_admin.add(self.tenant)
        self.navigateur = TenantClient(self.tenant)
        self.navigateur.force_login(self.admin_du_lieu)

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _creer_article(self, nom, tva, categorie, nom_du_tarif, prix, asset):
        """Un article de vente a un tarif, en euros (asset None) ou en points.
        / A sale item with one price, in euros (asset None) or in points."""
        article = Product.objects.create(
            name=nom, methode_caisse=Product.VENTE, tva=tva, categorie_pos=categorie
        )
        Price.objects.create(
            product=article,
            name=nom_du_tarif,
            prix=Decimal(prix),
            non_fiduciaire=asset is not None,
            asset=asset,
        )
        return article

    def _crediter_la_carte(self, asset, montant_en_centiemes):
        with transaction.atomic():
            WalletService.crediter(self.wallet_du_client, asset, montant_en_centiemes)

    def _solde(self, asset):
        return WalletService.obtenir_solde(wallet=self.wallet_du_client, asset=asset)

    def _payer(self, moyen, articles, donnees_en_plus=None):
        """Encaisse par la VRAIE route de paiement, reseau federe coupe.
        `articles` : {cle_du_panier: quantite}.
        / Collects through the REAL payment route, federated network off."""
        donnees = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "moyen_paiement": moyen,
            "total": "0",
            "given_sum": "0",
            "tag_id": self.carte.tag_id,
        }
        for cle_du_panier, quantite in articles.items():
            donnees[f"repid-{cle_du_panier}"] = str(quantite)
        if donnees_en_plus:
            donnees.update(donnees_en_plus)
        with (
            mock.patch("laboutik.views.FedowConfig") as configuration_fedow,
            mock.patch("laboutik.views.FedowAPI"),
        ):
            configuration_fedow.get_solo.return_value.can_fedow.return_value = False
            return self.navigateur.post("/laboutik/paiement/payer/", data=donnees)

    def _carte_primaire(self, tag_id, mode_gerant):
        """Une carte primaire (carte du caissier) avec acces au point de vente.
        / A primary card (cashier card) with access to the point of sale."""
        carte_du_caissier = CarteCashless.objects.create(tag_id=tag_id, number=tag_id)
        carte_primaire = CartePrimaire.objects.create(
            carte=carte_du_caissier, edit_mode=mode_gerant
        )
        carte_primaire.points_de_vente.add(self.point_de_vente)
        return carte_du_caissier

    def _creer_ligne_de_caisse(self, tarif, moyen, amount, qty, asset=None):
        """Ecrit une ligne de caisse validee, sans passer par la route de paiement.
        / Writes a validated register line, without the payment route."""
        produit_vendu = ProductSold.objects.create(product=tarif.product)
        tarif_vendu = PriceSold.objects.create(
            productsold=produit_vendu, price=tarif, prix=tarif.prix
        )
        return LigneArticle.objects.create(
            pricesold=tarif_vendu,
            qty=qty,
            amount=amount,
            payment_method=moyen,
            asset=asset.uuid if asset else None,
            status=LigneArticle.VALID,
            sale_origin=SaleOrigin.LABOUTIK,
        )

    def _vendre_un_pins_en_points(self):
        return self._creer_ligne_de_caisse(
            self.tarif_pins,
            PaymentMethod.NON_MONETAIRE,
            PRIX_PINS_EN_CENTIEMES_DE_POINTS,
            1,
            asset=self.asset_points,
        )

    def _vendre_un_vin_en_especes(self):
        return self._creer_ligne_de_caisse(
            self.tarif_vin, PaymentMethod.CASH, PRIX_VIN_CENTIMES, 1
        )

    def _rapport(self):
        maintenant = timezone.now()
        return RapportComptableService(
            None, maintenant - timedelta(hours=1), maintenant + timedelta(hours=1)
        )

    def _formset_des_tarifs(
        self, produit, prix="300.00", case_non_fiduciaire=True, asset="points",
        champs_en_plus=None,
    ):
        """Formset de l'inline des tarifs de caisse, tel que l'admin le construit.
        `asset` : "points" (monnaie FID du test), un Asset, ou None (champ vide).
        / POS price inline formset, as the admin builds it."""
        if asset == "points":
            asset = self.asset_points
        requete = RequestFactory().post("/")
        requete.user = self.admin_du_lieu
        inline_des_tarifs = POSPriceInline(POSProduct, staff_admin_site)
        ClasseDuFormset = inline_des_tarifs.get_formset(requete, produit)
        prefixe = ClasseDuFormset.get_default_prefix()

        donnees = {
            f"{prefixe}-TOTAL_FORMS": "1",
            f"{prefixe}-INITIAL_FORMS": "0",
            f"{prefixe}-MIN_NUM_FORMS": "0",
            f"{prefixe}-MAX_NUM_FORMS": "1000",
            f"{prefixe}-0-name": "Tarif en points",
            f"{prefixe}-0-prix": prix,
            f"{prefixe}-0-publish": "on",
            f"{prefixe}-0-order": "100",
        }
        if case_non_fiduciaire:
            donnees[f"{prefixe}-0-non_fiduciaire"] = "on"
        if asset is not None:
            donnees[f"{prefixe}-0-asset"] = str(asset.pk)
        for nom_du_champ, valeur in (champs_en_plus or {}).items():
            donnees[f"{prefixe}-0-{nom_du_champ}"] = valeur
        return ClasseDuFormset(data=donnees, instance=produit, prefix=prefixe)

    # ------------------------------------------------------------------
    # Moyen de paiement et TVA / Payment method and VAT
    # ------------------------------------------------------------------

    def test_les_points_et_le_temps_sont_enregistres_en_non_monetaire(self):
        """FID et TIM ne sont jamais enregistres en euros.
        / FID and TIM are never recorded as euros."""
        from laboutik.views import MAPPING_ASSET_CATEGORY_PAYMENT_METHOD

        assert MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[Asset.FID] == PaymentMethod.NON_MONETAIRE
        assert MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[Asset.TIM] == PaymentMethod.NON_MONETAIRE

    def test_une_ligne_en_points_est_creee_sans_tva(self):
        """Une vente en points n'est pas une vente en argent : TVA 0.
        / A points sale is not a money sale: VAT 0."""
        ligne = self._vendre_un_pins_en_points()

        ligne.refresh_from_db()
        assert ligne.vat == 0, f"TVA de la ligne en points : {ligne.vat}"

    # ------------------------------------------------------------------
    # Rapport de caisse / Register report
    # ------------------------------------------------------------------

    def test_le_total_du_rapport_ignore_les_points(self):
        """Un Pin's en points + un vin en especes : le total encaisse est 5,00 €.
        / A pin in points + a wine in cash: the collected total is 5.00 €."""
        self._vendre_un_pins_en_points()
        self._vendre_un_vin_en_especes()

        assert self._rapport().calculer_totaux_par_moyen()["total"] == PRIX_VIN_CENTIMES

    def test_la_tva_du_rapport_ignore_les_points(self):
        """La TVA ne porte que sur le vin vendu en especes.
        / VAT only covers the wine sold in cash."""
        self._vendre_un_pins_en_points()
        self._vendre_un_vin_en_especes()

        tva = self._rapport().calculer_tva()

        total_ttc_des_taux = sum(taux["total_ttc"] for taux in tva.values())
        assert total_ttc_des_taux == PRIX_VIN_CENTIMES, tva

    def test_une_vente_en_points_n_est_pas_un_article_offert(self):
        """La section « Offerts » ne montre que les articles offerts (FREE).
        / The "Gifted" section only shows gifted items (FREE)."""
        self._vendre_un_pins_en_points()

        offerts = self._rapport().calculer_offerts()

        assert offerts["par_produit"] == [], offerts
        assert offerts["valeur_totale"] == 0

    def test_la_section_non_monetaire_donne_une_ligne_par_monnaie(self):
        """3 Pin's en points (1 + 2) et 5 heures : deux lignes, par nom de monnaie.
        / 3 pins in points (1 + 2) and 5 hours: two lines, by currency name."""
        self._vendre_un_pins_en_points()
        self._creer_ligne_de_caisse(
            self.tarif_pins,
            PaymentMethod.NON_MONETAIRE,
            PRIX_PINS_EN_CENTIEMES_DE_POINTS,
            2,
            asset=self.asset_points,
        )
        self._creer_ligne_de_caisse(
            self.tarif_pins,
            PaymentMethod.NON_MONETAIRE,
            100,
            5,
            asset=self.asset_temps,
        )
        self._vendre_un_vin_en_especes()

        non_monetaire = self._rapport().calculer_non_monetaire()

        assert non_monetaire == {
            "par_monnaie": [
                {"nom": "Points fidélité", "qty_articles": 3.0, "unites": 90000},
                {"nom": "Temps", "qty_articles": 5.0, "unites": 500},
            ]
        }

    def test_le_rapport_complet_contient_la_section_non_monetaire(self):
        """La cloture stocke la section « Non monetaire ».
        / The closure stores the "Non-monetary" section."""
        self._vendre_un_pins_en_points()

        rapport = self._rapport().generer_rapport_complet()

        assert rapport["non_monetaire"]["par_monnaie"] == [
            {"nom": "Points fidélité", "qty_articles": 1.0, "unites": 30000}
        ]

    # ------------------------------------------------------------------
    # Correction du moyen de paiement / Payment method correction
    # ------------------------------------------------------------------

    def test_une_vente_en_points_ne_peut_pas_etre_corrigee_en_especes(self):
        """Corriger une vente en points en especes ferait apparaitre de l'argent
        jamais encaisse : refuse.
        / Correcting a points sale into cash would create money: refused."""
        ligne_en_points = self._vendre_un_pins_en_points()
        navigateur = TenantClient(self.tenant)
        navigateur.force_login(self.admin_du_lieu)

        reponse = navigateur.post(
            "/laboutik/paiement/corriger_moyen_paiement/",
            data={
                "ligne_uuid": str(ligne_en_points.uuid),
                "ancien_moyen": ligne_en_points.payment_method,
                "nouveau_moyen": PaymentMethod.CASH,
                "raison": "test",
            },
        )

        assert reponse.status_code == 400
        assert "en points ou en temps" in reponse.content.decode()
        ligne_en_points.refresh_from_db()
        assert ligne_en_points.payment_method == PaymentMethod.NON_MONETAIRE

    # ------------------------------------------------------------------
    # Admin : ou poser un tarif en points / Admin: where a points price fits
    # ------------------------------------------------------------------

    def test_un_tarif_en_points_est_refuse_sur_une_recharge(self):
        """Une recharge ne se vend pas en points : formulaire refuse.
        / A top-up is not sold in points: form refused."""
        recharge = Product.objects.create(
            name="Recharge en points", methode_caisse=Product.RECHARGE_EUROS
        )

        formset = self._formset_des_tarifs(recharge)

        assert not formset.is_valid()
        assert "non_fiduciaire" in formset.forms[0].errors, formset.errors

    def test_un_tarif_en_points_est_accepte_sur_un_article_de_vente(self):
        """Un article de vente accepte un tarif en points.
        / A sale item accepts a points price."""
        formset = self._formset_des_tarifs(self.pins)

        assert formset.is_valid(), formset.errors

    def test_un_tarif_en_points_est_accepte_sur_une_adhesion(self):
        """Une adhesion accepte un tarif en points.
        / A membership accepts a points price."""
        formset = self._formset_des_tarifs(self.adhesion)

        assert formset.is_valid(), formset.errors

    def test_un_tarif_en_euros_reste_accepte_sur_une_recharge(self):
        """La regle ne touche que les tarifs en points.
        / The rule only affects points prices."""
        recharge = Product.objects.create(
            name="Recharge en euros", methode_caisse=Product.RECHARGE_EUROS
        )

        formset = self._formset_des_tarifs(
            recharge, case_non_fiduciaire=False, asset=None
        )

        assert formset.is_valid(), formset.errors

    # ------------------------------------------------------------------
    # Tuiles et panier / Tiles and cart
    # ------------------------------------------------------------------

    def _article_de_la_tuile(self, produit):
        from laboutik.views import _construire_donnees_articles

        articles = _construire_donnees_articles(self.point_de_vente)
        for article in articles:
            if article["id"] == str(produit.uuid):
                return article
        return None

    def test_un_article_en_points_a_sa_tuile(self):
        """Le Pin's (300 points seulement) est propose a la caisse.
        / The points-only pin is offered at the register."""
        article = self._article_de_la_tuile(self.pins)

        assert article is not None, "Le Pin's en points n'a pas de tuile"
        assert article["prix"] == PRIX_PINS_EN_CENTIEMES_DE_POINTS

    def test_le_tarif_en_euros_passe_avant_le_tarif_en_temps(self):
        """La biere garde ses deux tarifs, les euros d'abord ; la tuile
        affiche 5 €.
        / Beer keeps both prices, euros first; the tile shows 5 €."""
        article = self._article_de_la_tuile(self.biere)

        assert article["prix"] == 500
        uuids_des_tarifs = [tarif["price_uuid"] for tarif in article["tarifs"]]
        assert uuids_des_tarifs == [
            str(self.tarif_biere_euros.uuid),
            str(self.tarif_biere_temps.uuid),
        ]

    def test_un_tarif_en_points_sur_une_consigne_n_a_pas_de_tuile(self):
        """Un tarif en points pose sur un produit qui n'est ni une vente ni une
        adhesion n'est pas vendable, meme s'il existe en base.
        / A points price on a non-sale, non-membership product is not sellable."""
        consigne = Product.objects.create(
            name="Consigne en points", methode_caisse=Product.RETOUR_CONSIGNE
        )
        Price.objects.create(
            product=consigne,
            name="Points",
            prix=Decimal("3.00"),
            non_fiduciaire=True,
            asset=self.asset_points,
        )
        self.point_de_vente.products.add(consigne)

        assert self._article_de_la_tuile(consigne) is None

    # ------------------------------------------------------------------
    # Paiement NFC en points / NFC payment in points
    # ------------------------------------------------------------------

    def test_un_pins_paye_en_points_cree_une_ligne_non_monetaire(self):
        """300 points debites : une ligne a 30000 unites, TVA 0, dans une vente en
        points reglee « points ou temps » (NM). Le moyen est sur le reglement, pas sur
        la ligne (Q-H2).
        / 300 points debited: one line at 30000 units, VAT 0, NM payment."""
        self._crediter_la_carte(self.asset_points, PRIX_PINS_EN_CENTIEMES_DE_POINTS)

        reponse = self._payer("nfc", {self.pins.uuid: 1})

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        ligne = LigneArticle.objects.get()
        assert ligne.payment_method is None
        moyens_de_la_vente = []
        for reglement in ligne.vente.reglements.all():
            moyens_de_la_vente.append(reglement.moyen)
        assert moyens_de_la_vente == [PaymentMethod.NON_MONETAIRE]
        assert ligne.amount == PRIX_PINS_EN_CENTIEMES_DE_POINTS
        assert ligne.qty == 1
        assert ligne.vat == 0
        assert self._solde(self.asset_points) == 0

    def test_une_adhesion_payee_en_points_ne_debite_pas_d_euros(self):
        """L'adhesion est creee, payee en points ; les euros de la carte
        restent intacts.
        / The membership is created, paid in points; card euros stay intact."""
        self._crediter_la_carte(self.asset_points, PRIX_PINS_EN_CENTIEMES_DE_POINTS)
        self._crediter_la_carte(self.asset_euros, 50000)
        adherent_declare = {
            "user": self.client_de_la_carte,
            "carte": self.carte,
            "fusion_locale_autorisee": False,
            "avertissements": [],
        }

        with mock.patch(
            "laboutik.views._declarer_adherent_au_reseau", return_value=adherent_declare
        ):
            reponse = self._payer("nfc", {self.adhesion.uuid: 1})

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        adhesion = Membership.objects.get(user=self.client_de_la_carte)
        ligne = LigneArticle.objects.get()
        assert ligne.vente.reglements.get().moyen == PaymentMethod.NON_MONETAIRE
        assert ligne.membership == adhesion
        # La fiche d'adhesion dit « payee en points » ; le montant est en points.
        # / The membership says "paid in points"; the amount is in points.
        assert adhesion.payment_method == PaymentMethod.NON_MONETAIRE
        assert adhesion.contribution_value == Decimal("300.00")
        assert self._solde(self.asset_points) == 0
        assert self._solde(self.asset_euros) == 50000

    def test_un_panier_points_et_euros_est_refuse(self):
        """Pin's + vin : refus, aucune ligne, aucun debit.
        / Pin + wine: refused, no line, no debit."""
        self._crediter_la_carte(self.asset_points, PRIX_PINS_EN_CENTIEMES_DE_POINTS)
        self._crediter_la_carte(self.asset_euros, 50000)

        reponse = self._payer("nfc", {self.pins.uuid: 1, self.vin.uuid: 1})

        assert reponse.status_code == 400
        assert "encaissez-les séparément" in reponse.content.decode()
        assert not LigneArticle.objects.exists()
        assert self._solde(self.asset_points) == PRIX_PINS_EN_CENTIEMES_DE_POINTS
        assert self._solde(self.asset_euros) == 50000

    def test_un_panier_points_et_temps_est_refuse(self):
        """Pin's + une heure de machine : refus, aucune ligne.
        / Pin + one machine hour: refused, no line."""
        self._crediter_la_carte(self.asset_points, PRIX_PINS_EN_CENTIEMES_DE_POINTS)
        self._crediter_la_carte(self.asset_temps, 100)

        reponse = self._payer("nfc", {self.pins.uuid: 1, self.machine.uuid: 1})

        assert reponse.status_code == 400
        assert "encaissez-les séparément" in reponse.content.decode()
        assert not LigneArticle.objects.exists()
        assert self._solde(self.asset_temps) == 100

    def test_un_panier_en_points_ne_se_paie_pas_en_especes(self):
        """Un POST force « especes » est refuse : aucune ligne.
        / A forged cash POST is refused: no line."""
        reponse = self._payer("espece", {self.pins.uuid: 1})

        assert reponse.status_code == 400
        assert "uniquement avec la carte du client" in reponse.content.decode()
        assert not LigneArticle.objects.exists()

    def test_un_panier_en_points_ne_peut_pas_etre_offert(self):
        """Un POST « gift » (OFFRIR, carte en mode gerant) sur un panier en points
        est refuse : ce panier se paie uniquement par carte NFC. La regle OFFRIR
        elle-meme est testee par
        test_offrir_est_refuse_pour_un_panier_en_points_meme_en_mode_gerant.
        / A "gift" POST on a points cart is refused: NFC card only."""
        carte_du_gerant = self._carte_primaire("GPT1AAAA", mode_gerant=True)

        reponse = self._payer(
            "gift", {self.pins.uuid: 1}, {"tag_id_cm": carte_du_gerant.tag_id}
        )

        assert reponse.status_code == 400
        assert "uniquement avec la carte du client" in reponse.content.decode()
        assert not LigneArticle.objects.exists()

    def test_un_panier_en_points_ne_propose_que_la_carte_nfc(self):
        """Seul CASHLESS est propose, pas d'OFFRIR meme en mode gerant.
        / Only CASHLESS is offered, no GIFT even in manager mode."""
        carte_du_gerant = self._carte_primaire("GPT2AAAA", mode_gerant=True)

        reponse = self.navigateur.post(
            "/laboutik/paiement/moyens_paiement/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                "tag_id_cm": carte_du_gerant.tag_id,
                f"repid-{self.pins.uuid}": "1",
            },
        )

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        assert 'data-testid="paiement-btn-cashless"' in contenu
        assert 'data-testid="paiement-btn-especes"' not in contenu
        assert 'data-testid="paiement-btn-cb"' not in contenu
        assert 'data-testid="paiement-btn-offrir"' not in contenu

    def test_les_moyens_de_paiement_refusent_un_panier_melange(self):
        """Des « VALIDER », un panier melange est refuse.
        / From VALIDATE on, a mixed cart is refused."""
        reponse = self.navigateur.post(
            "/laboutik/paiement/moyens_paiement/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                f"repid-{self.pins.uuid}": "1",
                f"repid-{self.vin.uuid}": "1",
            },
        )

        assert reponse.status_code == 400
        assert "encaissez-les séparément" in reponse.content.decode()

    def test_solde_de_points_insuffisant_popup_sans_deuxieme_carte(self):
        """100 points pour un Pin's a 300 : popup au nom de la monnaie, sans
        completement par 2e carte, aucune ligne.
        / 100 points for a 300 pin: popup with the currency name, no 2nd card."""
        self._crediter_la_carte(self.asset_points, 10000)

        reponse = self._payer("nfc", {self.pins.uuid: 1})

        contenu = reponse.content.decode()
        assert 'data-testid="paiement-nfc-insuffisant"' in contenu, contenu[:400]
        # Le manque (200 points) s'affiche dans la monnaie du panier, pas en €.
        # / The shortfall is shown in the cart currency, not in €.
        manque_affiche = re.search(
            r'id="test-manque-monnaie">([^<]*)</b>', contenu
        ).group(1)
        assert manque_affiche == "200,00 Points fidélité", manque_affiche
        assert 'data-testid="paiement-insuffisant-btn-cashless"' not in contenu
        assert not LigneArticle.objects.exists()
        assert self._solde(self.asset_points) == 10000

    def test_le_solde_est_compare_a_la_somme_du_panier(self):
        """Pin's + Medaille (600 points) avec 500 points : popup, aucun debit.
        / Pin + medal (600 points) with 500 points: popup, no debit."""
        self._crediter_la_carte(self.asset_points, 50000)

        reponse = self._payer("nfc", {self.pins.uuid: 1, self.medaille.uuid: 1})

        contenu = reponse.content.decode()
        assert 'data-testid="paiement-nfc-insuffisant"' in contenu, contenu[:400]
        # Refus AVANT le debit : le manque est calcule sur la somme (100 points).
        # / Refused BEFORE the debit: the shortfall is computed on the sum.
        manque_affiche = re.search(
            r'id="test-manque-monnaie">([^<]*)</b>', contenu
        ).group(1)
        assert manque_affiche == "100,00 Points fidélité", manque_affiche
        assert 'data-testid="paiement-insuffisant-btn-cashless"' not in contenu
        assert not LigneArticle.objects.exists()
        assert self._solde(self.asset_points) == 50000

    def test_une_monnaie_hors_mapping_est_refusee_avant_le_debit(self):
        """Une categorie de monnaie inconnue du mapping : refus a la
        classification, aucun debit, aucune ligne.
        / A currency category missing from the mapping: refused before any debit."""
        from laboutik.views import MAPPING_ASSET_CATEGORY_PAYMENT_METHOD

        self._crediter_la_carte(self.asset_points, PRIX_PINS_EN_CENTIEMES_DE_POINTS)
        mapping_sans_les_points = dict(MAPPING_ASSET_CATEGORY_PAYMENT_METHOD)
        del mapping_sans_les_points[Asset.FID]

        with mock.patch.dict(
            "laboutik.views.MAPPING_ASSET_CATEGORY_PAYMENT_METHOD",
            mapping_sans_les_points,
            clear=True,
        ):
            reponse = self._payer("nfc", {self.pins.uuid: 1})

        assert reponse.status_code == 400
        assert "pas acceptée à la caisse" in reponse.content.decode()
        assert not LigneArticle.objects.exists()
        assert self._solde(self.asset_points) == PRIX_PINS_EN_CENTIEMES_DE_POINTS

    def test_le_complement_de_paiement_refuse_un_panier_en_points(self):
        """Un POST direct du complement avec un panier en points : refus.
        / A direct complement POST with a points cart: refused."""
        self._crediter_la_carte(self.asset_points, 10000)

        reponse = self.navigateur.post(
            "/laboutik/paiement/payer_complementaire/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                f"repid-{self.pins.uuid}": "1",
                "tag_id_carte1": self.carte.tag_id,
                "moyen_complement": "espece",
                "given_sum": "0",
            },
        )

        assert reponse.status_code == 400
        assert "uniquement avec la carte du client" in reponse.content.decode()
        assert not LigneArticle.objects.exists()
        assert self._solde(self.asset_points) == 10000

    # ------------------------------------------------------------------
    # Rapport, FEC, archive / Report, FEC, archive
    # ------------------------------------------------------------------

    def _vendre_un_pins_en_points_et_un_vin_en_especes(self):
        self._crediter_la_carte(self.asset_points, PRIX_PINS_EN_CENTIEMES_DE_POINTS)
        reponse_points = self._payer("nfc", {self.pins.uuid: 1})
        assert reponse_points.status_code == 200, reponse_points.content.decode()[:400]
        reponse_especes = self._payer("espece", {self.vin.uuid: 1})
        assert reponse_especes.status_code == 200, reponse_especes.content.decode()[:400]

    # La clôture et le FEC de l'ancien moteur ne lisent plus une vente de la caisse
    # (moyen de la ligne vide, Q-H2) : les points y sont testés sur le rapport unique
    # (tests/pytest/test_rapport_unique.py, points par monnaie) et le FEC unique
    # (tests/pytest/test_fec_equilibre.py, vente en points sans écriture).
    # / The old engine's closure and FEC no longer read a register sale: points are
    # tested on the single report and the single FEC.

    def test_l_archive_fiscale_garde_la_vente_en_points_sans_tva(self):
        """L'article payé en points est dans l'archive (`articles.csv`), TVA 0,
        HT = TTC ; sa vente a un règlement NM (`reglements.csv`).
        / The points item is archived, VAT 0, excl. tax = incl. tax; its sale has an
        NM payment."""
        from laboutik.archivage import generer_fichiers_archive

        self._vendre_un_pins_en_points_et_un_vin_en_especes()
        ligne_en_points = LigneArticle.objects.get(
            vente__reglements__moyen=PaymentMethod.NON_MONETAIRE
        )

        fichiers = generer_fichiers_archive(schema=self.tenant.schema_name)

        contenu_des_articles = fichiers["articles.csv"].decode("utf-8-sig")
        articles_du_csv = list(
            csv.DictReader(io.StringIO(contenu_des_articles), delimiter=";")
        )
        article_archive = None
        for article_du_csv in articles_du_csv:
            if article_du_csv["uuid"] == str(ligne_en_points.uuid):
                article_archive = article_du_csv
        assert article_archive is not None
        assert article_archive["vente_uuid"] == str(ligne_en_points.vente_id)
        assert Decimal(article_archive["taux_tva"]) == Decimal("0")
        assert article_archive["total_ht"] == str(PRIX_PINS_EN_CENTIEMES_DE_POINTS)
        assert article_archive["total_tva"] == "0"

        contenu_des_reglements = fichiers["reglements.csv"].decode("utf-8-sig")
        reglements_du_csv = list(
            csv.DictReader(io.StringIO(contenu_des_reglements), delimiter=";")
        )
        moyens_de_la_vente_en_points = []
        for reglement_du_csv in reglements_du_csv:
            if reglement_du_csv["vente_uuid"] == str(ligne_en_points.vente_id):
                moyens_de_la_vente_en_points.append(reglement_du_csv["moyen"])
        assert moyens_de_la_vente_en_points == [PaymentMethod.NON_MONETAIRE]

    # ------------------------------------------------------------------
    # Commandes de table / Table orders
    # ------------------------------------------------------------------

    def test_ouvrir_une_commande_avec_un_tarif_en_points_est_refuse(self):
        """Ouvrir une commande avec le Pin's : refus, aucun article.
        / Opening an order with the pin: refused, no item."""
        reponse = self.navigateur.post(
            "/laboutik/commande/ouvrir/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                "articles": [
                    {
                        "product_uuid": str(self.pins.uuid),
                        "price_uuid": str(self.tarif_pins.uuid),
                        "qty": 1,
                    }
                ],
            },
            content_type="application/json",
        )

        assert reponse.status_code == 400
        assert "commande de table" in reponse.content.decode()
        assert not CommandeSauvegarde.objects.exists()
        assert not ArticleCommandeSauvegarde.objects.exists()

    def test_ajouter_un_tarif_en_points_a_une_commande_est_refuse(self):
        """Ajouter le Pin's a une commande ouverte : refus, aucun article.
        / Adding the pin to an open order: refused, no item."""
        commande = CommandeSauvegarde.objects.create(
            statut=CommandeSauvegarde.OPEN, responsable=self.admin_du_lieu
        )

        reponse = self.navigateur.post(
            f"/laboutik/commande/ajouter/{commande.uuid}/",
            data=[
                {
                    "product_uuid": str(self.pins.uuid),
                    "price_uuid": str(self.tarif_pins.uuid),
                    "qty": 1,
                }
            ],
            content_type="application/json",
        )

        assert reponse.status_code == 400
        assert "commande de table" in reponse.content.decode()
        assert not ArticleCommandeSauvegarde.objects.exists()

    def test_payer_une_commande_contenant_un_tarif_en_points_est_refuse(self):
        """Une commande qui contient deja un tarif en points ne se paie pas.
        / An order already holding a points price cannot be paid."""
        self._crediter_la_carte(self.asset_points, PRIX_PINS_EN_CENTIEMES_DE_POINTS)
        commande = CommandeSauvegarde.objects.create(
            statut=CommandeSauvegarde.OPEN, responsable=self.admin_du_lieu
        )
        ArticleCommandeSauvegarde.objects.create(
            commande=commande,
            product=self.pins,
            price=self.tarif_pins,
            qty=1,
            statut=ArticleCommandeSauvegarde.EN_ATTENTE,
        )

        with (
            mock.patch("laboutik.views.FedowConfig") as configuration_fedow,
            mock.patch("laboutik.views.FedowAPI"),
        ):
            configuration_fedow.get_solo.return_value.can_fedow.return_value = False
            reponse = self.navigateur.post(
                f"/laboutik/commande/payer/{commande.uuid}/",
                data={
                    "uuid_pv": str(self.point_de_vente.uuid),
                    "moyen_paiement": "nfc",
                    "tag_id": self.carte.tag_id,
                    "given_sum": "",
                },
            )

        assert reponse.status_code == 400
        assert "commande de table" in reponse.content.decode()
        assert not LigneArticle.objects.exists()
        assert self._solde(self.asset_points) == PRIX_PINS_EN_CENTIEMES_DE_POINTS

    # ------------------------------------------------------------------
    # Tireuse / Tap
    # ------------------------------------------------------------------

    def test_la_tireuse_facture_le_tarif_en_euros(self):
        """Un fut avec un tarif « au litre » en temps (ordre 1) et un en
        euros : la tireuse facture en euros.
        / A keg with a per-litre time price (order 1) and a euro one: billed in euros."""
        from controlvanne.billing import facturer_tirage, obtenir_contexte_cashless
        from controlvanne.models import RfidSession, TireuseBec

        fut = Product.objects.create(name="Fût en points", categorie_article=Product.FUT)
        Price.objects.create(
            product=fut,
            name="Litre bénévole",
            prix=Decimal("1.00"),
            poids_mesure=True,
            non_fiduciaire=True,
            asset=self.asset_temps,
            order=1,
        )
        tarif_au_litre_en_euros = Price.objects.create(
            product=fut, name="Litre", prix=Decimal("5.00"), poids_mesure=True
        )
        tireuse = TireuseBec.objects.create(
            nom_tireuse="Tireuse en points",
            enabled=True,
            fut_actif=fut,
            reservoir_ml=Decimal("30000.00"),
        )
        self._crediter_la_carte(self.asset_euros, 1000)
        # Le volume autorisé est posé au badge et plafonne le volume facturé (Q-H13).
        # / The authorised volume is set at the badge and caps the billed volume.
        session = RfidSession.objects.create(
            uid=self.carte.tag_id,
            carte=self.carte,
            tireuse_bec=tireuse,
            authorized=True,
            allowed_ml_session=Decimal("1000.00"),
        )

        facturer_tirage(
            session,
            tireuse,
            self.carte,
            Decimal("500"),
            obtenir_contexte_cashless(self.carte),
        )

        # 500 ml a 5 €/L = 2,50 €.
        ligne = LigneArticle.objects.get()
        assert ligne.pricesold.price == tarif_au_litre_en_euros
        assert ligne.amount * ligne.qty == 250
        assert self._solde(self.asset_euros) == 750

    # ------------------------------------------------------------------
    # Cas limites de la vente en points / Points sale edge cases
    # ------------------------------------------------------------------

    def test_deux_pins_en_points_une_ligne_quantite_deux(self):
        """2 Pin's : une ligne NM au prix unitaire, quantite 2 ; 600 points debites.
        / 2 pins: one NM line at unit price, qty 2; 600 points debited."""
        self._crediter_la_carte(self.asset_points, 2 * PRIX_PINS_EN_CENTIEMES_DE_POINTS)

        reponse = self._payer("nfc", {self.pins.uuid: 2})

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        ligne = LigneArticle.objects.get()
        assert ligne.amount == PRIX_PINS_EN_CENTIEMES_DE_POINTS
        assert ligne.qty == 2
        assert ligne.amount * ligne.qty == 2 * PRIX_PINS_EN_CENTIEMES_DE_POINTS
        assert self._solde(self.asset_points) == 0

    def test_une_biere_payee_en_temps(self):
        """Le tarif « Benevole » de la biere (1 heure) se paie en temps : la vente est
        dans l'unite du temps, reglee « points ou temps » (NM) dans cette monnaie.
        / The beer's time price is paid in time: NM payment in the time currency."""
        self._crediter_la_carte(self.asset_temps, 100)
        cle_du_tarif_en_temps = f"{self.biere.uuid}--{self.tarif_biere_temps.uuid}"

        reponse = self._payer("nfc", {cle_du_tarif_en_temps: 1})

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        ligne = LigneArticle.objects.get()
        assert ligne.amount == 100
        reglement_en_temps = ligne.vente.reglements.get()
        assert reglement_en_temps.moyen == PaymentMethod.NON_MONETAIRE
        assert reglement_en_temps.asset == self.asset_temps.uuid
        assert self._solde(self.asset_temps) == 0

    def test_deux_monnaies_de_points_dans_un_panier_sont_refusees(self):
        """Deux monnaies FID differentes : c'est un melange, refuse.
        / Two different FID currencies: a mix, refused."""
        wallet_du_partenaire = Wallet.objects.create(
            origin=self.tenant, name="Wallet partenaire en points"
        )
        points_partenaires = AssetService.creer_asset(
            tenant=self.tenant,
            name="Points partenaires",
            category=Asset.FID,
            currency_code="PPA",
            wallet_origin=wallet_du_partenaire,
        )
        goodies = self._creer_article(
            "Goodies partenaires", None, None, "Points", "100.00", points_partenaires
        )
        self.point_de_vente.products.add(goodies)
        self._crediter_la_carte(self.asset_points, PRIX_PINS_EN_CENTIEMES_DE_POINTS)
        self._crediter_la_carte(points_partenaires, 10000)

        reponse = self._payer("nfc", {self.pins.uuid: 1, goodies.uuid: 1})

        assert reponse.status_code == 400
        assert "encaissez-les séparément" in reponse.content.decode()
        assert not LigneArticle.objects.exists()

    def test_une_monnaie_archivee_ne_vend_plus_ses_tarifs(self):
        """Monnaie FID archivee : plus de tuile, un POST est ignore (aucune ligne).
        / Archived FID currency: no tile, a POST is ignored (no line)."""
        self._crediter_la_carte(self.asset_points, PRIX_PINS_EN_CENTIEMES_DE_POINTS)
        self.asset_points.archive = True
        self.asset_points.save()

        reponse = self._payer("nfc", {self.pins.uuid: 1})

        assert self._article_de_la_tuile(self.pins) is None
        assert not LigneArticle.objects.exists(), reponse.content.decode()[:400]
        assert self._solde(self.asset_points) == PRIX_PINS_EN_CENTIEMES_DE_POINTS

    def test_une_monnaie_inactive_ne_vend_plus_ses_tarifs(self):
        """Monnaie FID inactive : plus de tuile.
        / Inactive FID currency: no tile."""
        self.asset_points.active = False
        self.asset_points.save()

        assert self._article_de_la_tuile(self.pins) is None

    def test_un_tarif_en_points_non_publie_n_a_pas_de_tuile(self):
        """Tarif en points non publie : plus de tuile.
        / Unpublished points price: no tile."""
        self.tarif_pins.publish = False
        self.tarif_pins.save()

        assert self._article_de_la_tuile(self.pins) is None

    def test_le_tarif_en_points_d_une_consigne_est_ignore_dans_un_post(self):
        """Un POST force avec le tarif en points d'une consigne : l'article est ignore.
        / A forged POST with a deposit's points price: the item is ignored."""
        from django.http import QueryDict

        from laboutik.views import _extraire_articles_du_panier

        consigne = Product.objects.create(
            name="Consigne forcée en points", methode_caisse=Product.RETOUR_CONSIGNE
        )
        tarif_en_points = Price.objects.create(
            product=consigne,
            name="Points",
            prix=Decimal("3.00"),
            non_fiduciaire=True,
            asset=self.asset_points,
        )
        self.point_de_vente.products.add(consigne)
        donnees = QueryDict(mutable=True)
        donnees[f"repid-{consigne.uuid}--{tarif_en_points.uuid}"] = "1"

        articles = _extraire_articles_du_panier(donnees, self.point_de_vente)

        assert articles == []

    def test_offrir_est_refuse_pour_un_panier_en_points_meme_en_mode_gerant(self):
        """La regle OFFRIR elle-meme : un panier en points n'est jamais offrable.
        Controle : le vin, lui, l'est.
        / The GIFT rule itself: a points cart is never giftable (wine is)."""
        from django.http import QueryDict

        from laboutik.views import _extraire_articles_du_panier, _panier_peut_etre_offert

        carte_du_gerant = self._carte_primaire("GPT3AAAA", mode_gerant=True)
        panier_en_points = QueryDict(mutable=True)
        panier_en_points[f"repid-{self.pins.uuid}"] = "1"
        panier_en_euros = QueryDict(mutable=True)
        panier_en_euros[f"repid-{self.vin.uuid}"] = "1"

        articles_en_points = _extraire_articles_du_panier(
            panier_en_points, self.point_de_vente
        )
        articles_en_euros = _extraire_articles_du_panier(
            panier_en_euros, self.point_de_vente
        )

        assert not _panier_peut_etre_offert(articles_en_points, carte_du_gerant.tag_id)
        assert _panier_peut_etre_offert(articles_en_euros, carte_du_gerant.tag_id)

    def test_payer_en_especes_une_commande_contenant_un_tarif_en_points_est_refuse(self):
        """Meme refus en especes qu'en NFC.
        / Same refusal with cash as with NFC."""
        commande = CommandeSauvegarde.objects.create(
            statut=CommandeSauvegarde.OPEN, responsable=self.admin_du_lieu
        )
        ArticleCommandeSauvegarde.objects.create(
            commande=commande,
            product=self.pins,
            price=self.tarif_pins,
            qty=1,
            statut=ArticleCommandeSauvegarde.EN_ATTENTE,
        )

        reponse = self.navigateur.post(
            f"/laboutik/commande/payer/{commande.uuid}/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                "moyen_paiement": "espece",
                "given_sum": "",
            },
        )

        assert reponse.status_code == 400
        assert "commande de table" in reponse.content.decode()
        assert not LigneArticle.objects.exists()

    def test_les_tarifs_en_points_suivent_leur_ordre_d_affichage(self):
        """Euros d'abord, puis l'ordre d'affichage, meme entre deux monnaies.
        La monnaie qui a le plus petit uuid recoit le plus GRAND ordre : un tri
        par monnaie la ferait passer devant.
        / Euros first, then display order, even between two currencies."""
        monnaie_premiere_par_uuid, monnaie_seconde_par_uuid = sorted(
            [self.asset_points, self.asset_temps], key=lambda asset: str(asset.uuid)
        )
        affiche = self._creer_article(
            "Affiche trois tarifs", None, None, "Euros", "4.00", None
        )
        tarif_euros = affiche.prices.get()
        tarif_en_second = Price.objects.create(
            product=affiche, name="Second", prix=Decimal("2.00"),
            non_fiduciaire=True, asset=monnaie_premiere_par_uuid, order=20,
        )
        tarif_en_premier = Price.objects.create(
            product=affiche, name="Premier", prix=Decimal("1.00"),
            non_fiduciaire=True, asset=monnaie_seconde_par_uuid, order=10,
        )
        self.point_de_vente.products.add(affiche)

        article = self._article_de_la_tuile(affiche)

        uuids_des_tarifs = [tarif["price_uuid"] for tarif in article["tarifs"]]
        assert uuids_des_tarifs == [
            str(tarif_euros.uuid),
            str(tarif_en_premier.uuid),
            str(tarif_en_second.uuid),
        ]

    def test_solde_disparu_pendant_le_paiement_popup_en_points(self):
        """Le solde baisse entre la verification et le debit : le popup reste en
        points et ne propose aucun complement.
        / Balance drops between check and debit: popup stays in points."""
        from fedow_core.exceptions import SoldeInsuffisant

        self._crediter_la_carte(self.asset_points, PRIX_PINS_EN_CENTIEMES_DE_POINTS)

        with mock.patch(
            "laboutik.views.TransactionService.creer_vente",
            side_effect=SoldeInsuffisant(0, PRIX_PINS_EN_CENTIEMES_DE_POINTS),
        ):
            reponse = self._payer("nfc", {self.pins.uuid: 1})

        contenu = reponse.content.decode()
        assert 'data-testid="paiement-nfc-insuffisant"' in contenu, contenu[:400]
        manque_affiche = re.search(
            r'id="test-manque-monnaie">([^<]*)</b>', contenu
        ).group(1)
        assert manque_affiche == "300,00 Points fidélité", manque_affiche
        assert 'data-testid="paiement-insuffisant-btn-cashless"' not in contenu
        assert not LigneArticle.objects.exists()

    # ------------------------------------------------------------------
    # Un tarif « non fiduciaire » sans monnaie / A points price without currency
    # ------------------------------------------------------------------

    def _creer_un_tarif_non_fiduciaire_sans_monnaie(self):
        """Tarif coche « non fiduciaire » mais sans monnaie, ecrit en base.
        / Price marked non-fiduciary but without currency, written to the database."""
        gobelet = Product.objects.create(
            name="Gobelet sans monnaie", methode_caisse=Product.VENTE
        )
        tarif_sans_monnaie = Price.objects.create(
            product=gobelet, name="Points ?", prix=Decimal("300.00"),
            non_fiduciaire=True, asset=None,
        )
        self.point_de_vente.products.add(gobelet)
        return gobelet, tarif_sans_monnaie

    def test_un_tarif_non_fiduciaire_sans_monnaie_n_est_pas_vendu_en_euros(self):
        """Pas de tuile, et un POST « especes » ne cree aucune ligne.
        / No tile, and a cash POST creates no line."""
        gobelet, _tarif = self._creer_un_tarif_non_fiduciaire_sans_monnaie()

        reponse = self._payer("espece", {gobelet.uuid: 1})

        assert self._article_de_la_tuile(gobelet) is None
        assert not LigneArticle.objects.exists(), reponse.content.decode()[:400]

    def test_un_tarif_non_fiduciaire_sans_monnaie_n_entre_pas_en_commande(self):
        """Une commande de table refuse ce tarif.
        / A table order refuses this price."""
        gobelet, tarif_sans_monnaie = self._creer_un_tarif_non_fiduciaire_sans_monnaie()

        reponse = self.navigateur.post(
            "/laboutik/commande/ouvrir/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                "articles": [
                    {
                        "product_uuid": str(gobelet.uuid),
                        "price_uuid": str(tarif_sans_monnaie.uuid),
                        "qty": 1,
                    }
                ],
            },
            content_type="application/json",
        )

        assert reponse.status_code == 400
        assert "commande de table" in reponse.content.decode()
        assert not ArticleCommandeSauvegarde.objects.exists()

    # ------------------------------------------------------------------
    # Admin : regles d'un tarif en points / Admin: points price rules
    # ------------------------------------------------------------------

    def test_un_tarif_non_fiduciaire_sans_monnaie_est_refuse_par_l_admin(self):
        """Case cochee, monnaie vide : erreur sur la monnaie.
        / Box checked, empty currency: error on the currency."""
        formset = self._formset_des_tarifs(self.pins, asset=None)

        assert not formset.is_valid()
        assert "asset" in formset.forms[0].errors, formset.errors

    def test_decocher_non_fiduciaire_vide_la_monnaie(self):
        """Case decochee, monnaie encore envoyee (champ cache) : le tarif repasse en
        euros, sans monnaie.
        / Box unchecked, currency still sent (hidden field): back to euros."""
        formset = self._formset_des_tarifs(
            self.pins, prix="5.00", case_non_fiduciaire=False, asset=self.asset_points
        )

        assert formset.is_valid(), formset.errors
        assert formset.forms[0].cleaned_data["asset"] is None

    def test_un_tarif_d_une_demi_heure_est_accepte(self):
        """0,50 heure : accepte pour un tarif en temps.
        / 0.50 hour: accepted for a time price."""
        formset = self._formset_des_tarifs(
            self.machine, prix="0.50", asset=self.asset_temps
        )

        assert formset.is_valid(), formset.errors

    def test_un_tarif_en_euros_a_cinquante_centimes_reste_refuse(self):
        """0,50 € : toujours refuse pour un tarif en euros.
        / 0.50 €: still refused for a euro price."""
        formset = self._formset_des_tarifs(
            self.vin, prix="0.50", case_non_fiduciaire=False, asset=None
        )

        assert not formset.is_valid()
        assert "prix" in formset.forms[0].errors, formset.errors

    def test_un_tarif_en_points_a_prix_libre_est_refuse(self):
        """Un tarif en points n'est pas a prix libre.
        / A points price is not a free price."""
        formset = self._formset_des_tarifs(
            self.pins, champs_en_plus={"free_price": "on"}
        )

        assert not formset.is_valid()
        assert "free_price" in formset.forms[0].errors, formset.errors

    def test_un_tarif_en_points_au_poids_est_refuse(self):
        """Un tarif en points n'est pas au poids.
        / A points price is not sold by weight."""
        formset = self._formset_des_tarifs(
            self.pins, champs_en_plus={"poids_mesure": "on"}
        )

        assert not formset.is_valid()
        assert "poids_mesure" in formset.forms[0].errors, formset.errors

    # ------------------------------------------------------------------
    # Adhesion en points : a la caisse seulement / Points membership: POS only
    # ------------------------------------------------------------------

    def _adhesion_mixte(self):
        """Une adhesion publiee a deux tarifs : 10 € et 300 points.
        / A published membership with two prices: 10 € and 300 points."""
        adhesion_mixte = Product.objects.create(
            name="Adhésion mixte",
            categorie_article=Product.ADHESION,
            publish=True,
        )
        tarif_en_euros = Price.objects.create(
            product=adhesion_mixte, name="Tarif normal", prix=Decimal("10.00")
        )
        tarif_en_points = Price.objects.create(
            product=adhesion_mixte,
            name="Tarif bénévole en points",
            prix=Decimal("300.00"),
            non_fiduciaire=True,
            asset=self.asset_points,
        )
        return adhesion_mixte, tarif_en_euros, tarif_en_points

    def test_la_page_d_adhesion_ne_propose_pas_le_tarif_en_points(self):
        """Le site ne propose que le tarif en euros.
        / The website only offers the euro price."""
        adhesion_mixte, _tarif_en_euros, _tarif_en_points = self._adhesion_mixte()

        reponse = self.navigateur.get(f"/memberships/{adhesion_mixte.uuid}/")

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        assert "Tarif normal" in contenu
        assert "Tarif bénévole en points" not in contenu

    def test_le_formulaire_d_adhesion_refuse_un_tarif_en_points(self):
        """Le validateur de l'adhesion en ligne (site et API v2) refuse ce tarif.
        / The online membership validator (website and API v2) refuses it."""
        from types import SimpleNamespace

        from django.contrib.auth.models import AnonymousUser

        from BaseBillet.validators import MembershipValidator

        _adhesion, _tarif_en_euros, tarif_en_points = self._adhesion_mixte()
        donnees = {
            "email": "adherent-web@tibillet.localhost",
            "firstname": "Ada",
            "lastname": "Web",
            "price": str(tarif_en_points.uuid),
            "acknowledge": "1",
            "newsletter": "0",
        }
        requete = SimpleNamespace(user=AnonymousUser(), data=donnees)

        validateur = MembershipValidator(data=donnees, context={"request": requete})

        assert not validateur.is_valid()
        assert "price" in validateur.errors, validateur.errors

    def test_le_panier_en_ligne_refuse_un_tarif_en_points(self):
        """Le panier du site refuse une adhesion au tarif en points.
        / The website cart refuses a membership at the points price."""
        from BaseBillet.services_panier import InvalidItemError, PanierSession
        from fabriques_panier import requete_avec_session

        _adhesion, _tarif_en_euros, tarif_en_points = self._adhesion_mixte()
        panier = PanierSession(requete_avec_session())

        with self.assertRaises(InvalidItemError):
            panier.add_membership(tarif_en_points.uuid)

    def test_l_api_v2_annonce_la_monnaie_du_tarif_en_points(self):
        """L'offre schema.org d'un tarif en points porte le code de sa monnaie, pas EUR.
        / The schema.org offer of a points price carries its currency code."""
        from api_v2.serializers import ProductSchemaSerializer

        adhesion_mixte, tarif_en_euros, tarif_en_points = self._adhesion_mixte()

        representation = ProductSchemaSerializer().to_representation(adhesion_mixte)

        monnaie_par_tarif = {}
        for offre in representation["offers"]:
            monnaie_par_tarif[offre["identifier"]] = offre["priceCurrency"]
        assert monnaie_par_tarif[str(tarif_en_euros.uuid)] == "EUR"
        assert monnaie_par_tarif[str(tarif_en_points.uuid)] == "PTS"

    # ------------------------------------------------------------------
    # Affichage a la caisse : l'unite de la monnaie / POS display: currency unit
    # ------------------------------------------------------------------

    def test_le_filtre_ecrit_un_montant_dans_sa_monnaie(self):
        """Sans monnaie : euros. Avec : centiemes / 100 et le nom de la monnaie.
        / Without currency: euros. With: hundredths / 100 and the currency name."""
        from laboutik.templatetags.laboutik_filters import montant_dans_la_monnaie

        assert montant_dans_la_monnaie(30000, "Points fidélité") == "300,00 Points fidélité"
        assert montant_dans_la_monnaie(50, "Temps") == "0,50 Temps"
        assert montant_dans_la_monnaie(500, "") == "5,00 €"

    def test_la_tuile_du_pins_porte_le_nom_de_sa_monnaie(self):
        """La tuile d'un article en points porte l'unite « Points fidelite ».
        / A points item tile carries the "Points fidelite" unit."""
        article = self._article_de_la_tuile(self.pins)

        assert article["unite_label"] == "Points fidélité"
        assert article["unite_courte"] == "PF"

    def test_chaque_tarif_porte_son_unite(self):
        """Biere : « € » pour la pinte, « Temps » pour le benevole.
        / Beer: "€" for the pint, "Temps" for the volunteer price."""
        article = self._article_de_la_tuile(self.biere)

        unites_des_tarifs = [tarif["unite_label"] for tarif in article["tarifs"]]
        unites_courtes_des_tarifs = [tarif["unite_courte"] for tarif in article["tarifs"]]
        assert article["unite_label"] == "€"
        assert unites_des_tarifs == ["€", "Temps"]
        assert unites_courtes_des_tarifs == ["€", "T"]

    def test_la_page_de_caisse_affiche_le_pins_en_points(self):
        """La tuile rendue affiche « 300 Points fidélité » et le transmet au panier
        (data-currency).
        / The rendered tile shows the points and passes the unit to the cart."""
        from django.template.loader import render_to_string

        from laboutik.views import CURRENCY_DATA

        article = self._article_de_la_tuile(self.pins)
        contenu = render_to_string(
            "cotton/articles.html",
            {
                "currency_data": CURRENCY_DATA,
                # Le gabarit lit les tuiles dans pv.articles (contexte de la caisse)
                # / The template reads tiles from pv.articles (POS context)
                "pv": {"articles": [article], "afficher_les_prix": True},
            },
        )

        assert 'data-currency="Points fidélité"' in contenu, contenu[:600]
        # Sur la tuile : les initiales, le nom complet en infobulle
        # / On the tile: the initials, full name as tooltip
        assert '300 <abbr title="Points fidélité">PF</abbr>' in contenu

    def test_l_ecran_des_moyens_de_paiement_affiche_le_total_en_points(self):
        """Total du panier Pin's : « 300,00 Points fidélité », pas en €.
        / Pin cart total: in points, not in €."""
        reponse = self.navigateur.post(
            "/laboutik/paiement/moyens_paiement/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                f"repid-{self.pins.uuid}": "1",
            },
        )

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        total_affiche = re.search(
            r'class="payment-total-val">([^<]*)</span>', contenu
        ).group(1)
        assert total_affiche == "300,00 Points fidélité", total_affiche

    def test_l_ecran_de_succes_affiche_le_paiement_en_points(self):
        """Succes : total paye et solde de la carte en points, jamais en €.
        / Success: paid total and card balance in points, never in €."""
        self._crediter_la_carte(self.asset_points, 50000)

        # Le navigateur poste un total faux : l'ecran affiche le total recalcule
        # par le serveur.
        # / The browser posts a wrong total: the screen shows the server's total.
        reponse = self._payer("nfc", {self.pins.uuid: 1}, {"total": "1"})

        contenu = reponse.content.decode()
        assert 'data-testid="paiement-succes"' in contenu, contenu[:400]
        total_paye = re.search(
            r'test-return-total-achats">.*?<b>([^<]*)</b>', contenu, re.S
        ).group(1)
        assert total_paye == "300,00 Points fidélité", total_paye
        debite = re.search(
            r'data-testid="paiement-carte1-debite">(.*?)</b>', contenu, re.S
        ).group(1)
        assert "300,00 Points fidélité" in debite, debite
        solde_apres = re.search(
            r'data-testid="paiement-carte1-solde-apres">([^<]*)</b>', contenu
        ).group(1)
        assert solde_apres == "200,00 Points fidélité", solde_apres
        assert "300,00 €" not in contenu

    def test_la_liste_des_ventes_affiche_la_vente_en_points(self):
        """E18 : la vente du Pin's affiche 300,00 Points fidelite, pas 300,00 €.
        / The pin sale shows points, not €."""
        self._vendre_un_pins_en_points_et_un_vin_en_especes()

        reponse = self.navigateur.get("/laboutik/caisse/liste-ventes/")

        # Les montants s'ecrivent avec des espaces insecables : on les ramene a une
        # espace ordinaire avant de chercher le texte.
        # / Amounts use non-breaking spaces: collapsed before searching the text.
        contenu_brut = reponse.content.decode()
        contenu = texte_sans_espaces_en_trop(contenu_brut)
        assert reponse.status_code == 200, contenu[:400]
        assert "300,00 €" not in contenu
        # La plus recente d'abord : le vin (especes, temoin en euros), puis le Pin's.
        # / Most recent first: the wine (cash, euro control), then the pin.
        assert textes_des_elements(contenu_brut, "vente-total") == [
            "5,00 €",
            "300,00 Points fidélité",
        ]
        assert textes_des_elements(contenu_brut, "vente-moyens") == [
            "5,00 € Espèces",
            "300,00 Points fidélité",
        ]

    def test_la_liste_des_ventes_se_filtre_sur_les_points(self):
        """Filtre « Points ou temps » : la vente en points, pas celle en especes.
        / "Points or time" filter: the points sale, not the cash one."""
        self._vendre_un_pins_en_points_et_un_vin_en_especes()

        reponse = self.navigateur.get("/laboutik/caisse/liste-ventes/?moyen=NM")

        contenu = texte_sans_espaces_en_trop(reponse.content.decode())
        assert reponse.status_code == 200, contenu[:400]
        assert 'value="NM"' in contenu
        assert "300,00 Points fidélité" in contenu
        assert "5,00 €" not in contenu

    def test_le_detail_d_une_vente_en_points(self):
        """Detail : prix, total de la ligne et total en points ; pas de bouton
        « Corriger » (le serveur refuse de corriger une vente hors argent).
        / Detail: amounts in points; no "Correct" button."""
        self._crediter_la_carte(self.asset_points, PRIX_PINS_EN_CENTIEMES_DE_POINTS)
        self._payer("nfc", {self.pins.uuid: 1})
        ligne = LigneArticle.objects.get()

        reponse = self.navigateur.get(
            f"/laboutik/caisse/detail-vente/{ligne.vente_id}/"
        )

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        totaux_affiches = textes_des_elements(contenu, "detail-total-transaction")
        assert totaux_affiches == ["300,00 Points fidélité"], totaux_affiches
        assert "300,00 €" not in texte_sans_espaces_en_trop(contenu)
        assert 'data-testid="btn-corriger"' not in contenu

    def test_la_popup_client_identifie_affiche_l_adhesion_en_points(self):
        """Adhesion en points, client identifie par sa carte : total et solde de la
        carte en points (le caissier voit si la carte peut payer).
        / Points membership, identified client: total and card balance in points."""
        self._crediter_la_carte(self.asset_points, 25000)
        self._crediter_la_carte(self.asset_euros, 1000)

        reponse = self.navigateur.post(
            "/laboutik/paiement/identifier_client/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                "tag_id": self.carte.tag_id,
                "panier_a_adhesions": "True",
                "moyens_paiement": "nfc",
                f"repid-{self.adhesion.uuid}": "1",
            },
        )

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        total_affiche = re.search(
            r'class="payment-total-val">([^<]*)</span>', contenu
        ).group(1)
        assert total_affiche == "300,00 Points fidélité", total_affiche
        solde_affiche = re.search(r"Solde : ([^<]*)</b>", contenu).group(1)
        assert solde_affiche == "250,00 Points fidélité", solde_affiche

    # ------------------------------------------------------------------
    # Ticket X, ticket Z, exports : section « Non monetaire »
    # / X and Z tickets, exports: "Non-monetary" section
    # ------------------------------------------------------------------

    def test_l_ecran_du_ticket_x_montre_les_ventes_en_points(self):
        """Recapitulatif en cours : le tableau « Non monétaire (hors argent) », lu dans
        la section « Points » du rapport des ventes, montre « Points fidélité »
        300,00 Points fidélité.
        / Current recap: the "non-monetary" table shows 300.00 loyalty points."""
        self._vendre_un_pins_en_points_et_un_vin_en_especes()

        reponse = self.navigateur.get("/laboutik/caisse/recap-en-cours/")

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        debut_de_la_section = contenu.index('data-testid="recap-non-monetaire"')
        bloc_des_points = contenu[debut_de_la_section:]
        ligne_des_points = re.search(
            r"<td[^>]*>Points fidélité</td>\s*<td[^>]*>([^<]*)</td>",
            bloc_des_points,
        )
        assert ligne_des_points is not None, bloc_des_points[:800]
        assert ligne_des_points.group(1).strip() == "300,00\u00a0Points fidélité"

    def test_le_ticket_x_imprime_mentionne_les_ventes_en_points(self):
        """Ticket X imprime, lu dans le rapport X du rapport des ventes : la ligne des
        points (300.00), hors du TOTAL, qui reste le vin seul (500).
        / Printed X ticket from the single report's X: the points line, outside the
        TOTAL."""
        from laboutik.printing.formatters import formatter_ticket_x

        self._vendre_un_pins_en_points_et_un_vin_en_especes()
        maintenant = timezone.now()
        debut_du_service = maintenant - timedelta(hours=1)
        rapport_du_service = RapportDesVentes(
            debut_du_service, maintenant + timedelta(hours=1)
        ).rapport_x()

        ticket = formatter_ticket_x(rapport_du_service, debut_du_service)

        # « Points fidélité (hors argent): 300.00 » ferait 37 caractères : plus large
        # que le ticket (32), la mention « hors argent » est retirée.
        # / Wider than the 32-char ticket: the "hors argent" mention is dropped.
        assert "Points fidélité: 300.00" in ticket["footer"]
        assert ticket["total"]["amount"] == PRIX_VIN_CENTIMES

    def _cloture_unique_du_jour(self):
        """La cloture journaliere unique du lieu (J), creee par la tache de cloture.
        / The venue's single daily closure (J), created by the closure task."""
        uuid_de_la_j = comptabilite.tasks.generer_cloture_pour_tenant(
            schema_name=self.tenant.schema_name,
            niveau=ClotureCaisseUnique.NIVEAU_JOURNALIER,
        )
        return ClotureCaisseUnique.objects.get(uuid=uuid_de_la_j)

    def test_le_ticket_z_imprime_mentionne_les_ventes_en_points(self):
        """Ticket Z imprime (J unique) : la ligne des points (300,00 en centiemes
        30000), hors du TOTAL, qui reste le vin seul (5,00 €). Le rapport de la J ne
        garde pas le nombre d'articles par monnaie : la ligne ne le porte pas.
        / Printed Z ticket (single J): the points line, outside the TOTAL."""
        from laboutik.printing.formatters import formatter_ticket_cloture

        self._vendre_un_pins_en_points_et_un_vin_en_especes()
        ticket = formatter_ticket_cloture(self._cloture_unique_du_jour())

        # Plus large que le ticket avec « (hors argent) » : la mention est retirée.
        # / Wider than the ticket with "(hors argent)": the mention is dropped.
        assert "Points fidélité: 300.00" in ticket["footer"]
        assert ticket["total"]["amount"] == PRIX_VIN_CENTIMES

    def test_l_ecran_de_cloture_montre_les_ventes_en_points(self):
        """Ecran du Z, par la vraie route : les reglements de la J montrent les
        points par monnaie, « Points fidélité » 300,00.
        / Z screen, through the real route: the J's payments show points per
        currency."""
        self._vendre_un_pins_en_points_et_un_vin_en_especes()

        reponse = self.navigateur.post(
            "/laboutik/caisse/cloturer/", {"uuid_pv": str(self.point_de_vente.uuid)}
        )

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]

        debut_des_reglements = contenu.index('data-testid="cloture-reglements"')
        bloc_des_reglements = contenu[debut_des_reglements:]
        ligne_des_points = re.search(
            r"<td[^>]*>Points fidélité</td>\s*<td[^>]*>([^<]*)</td>",
            bloc_des_reglements,
        )
        assert ligne_des_points is not None, bloc_des_reglements[:800]
        assert ligne_des_points.group(1).strip() == "300,00"

    # La fiche d'une clôture, son PDF et le rapport temps réel de l'ancien moteur ne
    # sont plus joignables (tests/pytest/test_part_en_jetons.py, test 15), et l'ancien
    # moteur ne sait plus lire une vente de la caisse (moyen de la ligne vide, Q-H2).
    # Les points de ces écrans sont lus sur le rapport des ventes unique : l'écran du
    # Z (`test_l_ecran_de_cloture_montre_les_ventes_en_points`), le ticket Z et le
    # récapitulatif en cours (`test_l_ecran_du_ticket_x_montre_les_ventes_en_points`).
    # / The old engine's screens are unreachable and cannot read a register sale;
    # points are read on the single sales report (Z screen, Z ticket, current recap).

    # Les exports CSV et tableur d'une clôture sont ceux de la clôture unique : leur
    # section « Points » est testée dans tests/pytest/test_comptabilite_exports.py
    # (toutes les sections dans l'ordre, totaux égaux au rapport).
    # / Closure CSV and spreadsheet exports: test_comptabilite_exports.py.

    # ------------------------------------------------------------------
    # Ticket client imprime / Printed customer ticket
    # ------------------------------------------------------------------

    def _ticket_de_la_vente(self, moyen):
        """Ticket client de la vente reglee par `moyen` (code DB), retrouvee par son
        reglement (la ligne ne porte plus le moyen, Q-H2) : le ticket lit la vente.
        / Customer ticket of the sale paid with `moyen`, found through its payment."""
        from laboutik.printing.formatters import formatter_ticket_vente

        reglement_de_ce_moyen = Reglement.objects.filter(moyen=moyen).first()
        return formatter_ticket_vente(reglement_de_ce_moyen.vente, self.admin_du_lieu)

    def test_le_ticket_client_en_points_n_a_ni_euros_ni_tva(self):
        """Ticket d'un Pin's en points : unite « Points fidelite », pas de TVA.
        Controle : le ticket du vin reste en EUR, avec sa TVA.
        / Points ticket: points unit, no VAT. Control: the wine ticket keeps EUR."""
        self._vendre_un_pins_en_points_et_un_vin_en_especes()

        ticket_en_points = self._ticket_de_la_vente(PaymentMethod.NON_MONETAIRE)
        ticket_en_euros = self._ticket_de_la_vente(PaymentMethod.CASH)

        assert ticket_en_points["unite"] == "Points fidélité"
        assert ticket_en_points["tva_breakdown"] == []
        assert ticket_en_points["total_tva"] == 0
        assert ticket_en_euros["unite"] == "EUR"
        assert ticket_en_euros["tva_breakdown"] != []

    def test_l_imprimante_sunmi_imprime_les_points(self):
        """Sunmi (app integree) : TOTAL et article en points, jamais « EUR ».
        / Sunmi inner: TOTAL and item in points, never "EUR"."""
        from laboutik.printing.sunmi_inner import ticket_data_to_json_commands

        self._vendre_un_pins_en_points_et_un_vin_en_especes()
        ticket = self._ticket_de_la_vente(PaymentMethod.NON_MONETAIRE)

        commandes = ticket_data_to_json_commands(ticket)

        textes = [str(commande.get("value", "")) for commande in commandes]
        assert "TOTAL: 300.00 Points fidélité" in textes
        assert any(texte.endswith("300.00 Points fidélité") and " x1" in texte for texte in textes)
        assert not any("EUR" in texte for texte in textes), textes

    def test_l_imprimante_escpos_imprime_les_points_sans_tva(self):
        """ESC/POS (imprimante reseau) : TOTAL en points, pas de tableau de TVA.
        / ESC/POS: TOTAL in points, no VAT table."""
        from laboutik.printing.escpos_builder import build_escpos_from_ticket_data

        self._vendre_un_pins_en_points_et_un_vin_en_especes()
        ticket = self._ticket_de_la_vente(PaymentMethod.NON_MONETAIRE)

        octets = build_escpos_from_ticket_data(576, ticket)

        assert "TOTAL: 300.00 Points fidélité".encode("utf-8") in octets
        assert "300.00 Points fidélité\n".encode("utf-8") in octets
        assert b"TVA%" not in octets
        assert b"EUR" not in octets

    # ------------------------------------------------------------------
    # Adhesions, exports et tickets / Memberships, exports and tickets
    # ------------------------------------------------------------------

    def _vendre_une_adhesion_en_points(self):
        self._crediter_la_carte(self.asset_points, PRIX_PINS_EN_CENTIEMES_DE_POINTS)
        adherent_declare = {
            "user": self.client_de_la_carte,
            "carte": self.carte,
            "fusion_locale_autorisee": False,
            "avertissements": [],
        }
        with mock.patch(
            "laboutik.views._declarer_adherent_au_reseau", return_value=adherent_declare
        ):
            reponse = self._payer("nfc", {self.adhesion.uuid: 1})
        assert reponse.status_code == 200, reponse.content.decode()[:400]

    # La fiche et l'export CSV de l'ancienne clôture de la caisse ne sont plus
    # joignables. L'adhésion en points dans le rapport des ventes unique :
    # tests/pytest/test_rapport_unique.py
    # `test_adhesion_payee_en_points_ecrite_en_points_jamais_en_euros` ; dans son
    # export CSV : tests/pytest/test_comptabilite_exports.py
    # `test_csv_points_par_monnaie_et_adhesion_en_points_absente_des_euros` (les points
    # en total par monnaie, fiche F §8).
    # / The old closure page and CSV export are gone; the points membership is tested
    # on the single sales report and its CSV export.

    # Le PDF du Z envoyé par e-mail est celui de la clôture unique : sa section
    # « Points » est testée dans tests/pytest/test_comptabilite_exports.py.
    # / The e-mailed Z PDF is the single closure's: test_comptabilite_exports.py.

    def test_le_ticket_z_a_une_ligne_par_monnaie(self):
        """Points et temps vendus : deux lignes au pied du Z de la J unique
        (300,00 points, 1,00 heure).
        / Points and time sold: two lines at the bottom of the single J's Z."""
        from laboutik.printing.formatters import formatter_ticket_cloture

        self._crediter_la_carte(self.asset_points, PRIX_PINS_EN_CENTIEMES_DE_POINTS)
        self._crediter_la_carte(self.asset_temps, 100)
        self._payer("nfc", {self.pins.uuid: 1})
        self._payer("nfc", {self.machine.uuid: 1})

        ticket = formatter_ticket_cloture(self._cloture_unique_du_jour())

        # « Temps (hors argent): 1.00 » tient sur le ticket (25 caractères) ; la ligne
        # des points, trop large, perd la mention « hors argent ».
        # / The time line fits; the points line, too wide, drops the mention.
        assert "Points fidélité: 300.00" in ticket["footer"]
        assert "Temps (hors argent): 1.00" in ticket["footer"]

    def test_le_ticket_client_d_une_vente_en_temps(self):
        """Ticket d'une heure de machine : unite « Temps », pas de TVA.
        / Ticket of one machine hour: "Temps" unit, no VAT."""
        self._crediter_la_carte(self.asset_temps, 100)
        self._payer("nfc", {self.machine.uuid: 1})

        ticket = self._ticket_de_la_vente(PaymentMethod.NON_MONETAIRE)

        assert ticket["unite"] == "Temps"
        assert ticket["tva_breakdown"] == []

    # L'export CSV de l'ancienne clôture de la caisse n'est plus joignable. Les offerts
    # dans l'export CSV du rapport des ventes unique :
    # tests/pytest/test_comptabilite_exports.py
    # `test_csv_liste_les_offerts_avec_leurs_valeurs`.
    # / The old closure CSV export is gone; gifted items are tested on the single
    # sales report's CSV export.

    # Le PDF du Z envoyé par e-mail est celui de la clôture unique : sa section
    # « Offerts » est testée dans tests/pytest/test_comptabilite_exports.py.
    # / The e-mailed Z PDF is the single closure's: test_comptabilite_exports.py.

    def test_le_ticket_d_une_vente_en_points_sans_monnaie_connue(self):
        """Vente en points dont la monnaie est introuvable : « Points ou temps »,
        jamais EUR. Le ticket lit la vente : elle est ecrite par le service de vente,
        dans une unite (uuid) qu'aucune monnaie du lieu ne porte.
        / Points sale with an unknown currency: "Points ou temps", never EUR."""
        produit_vendu = ProductSold.objects.create(product=self.tarif_pins.product)
        tarif_vendu = PriceSold.objects.create(
            productsold=produit_vendu, price=self.tarif_pins, prix=self.tarif_pins.prix
        )
        vente = self._vente_reglee_au_comptoir(
            unite=str(uuid_module.uuid4()),
            articles=[{
                "pricesold": tarif_vendu,
                "quantite": Decimal("1"),
                "prix_unitaire": PRIX_PINS_EN_CENTIEMES_DE_POINTS,
                "taux_tva": Decimal("0"),
                "payment_method": PaymentMethod.NON_MONETAIRE,
                "status": LigneArticle.VALID,
                "point_de_vente": self.point_de_vente,
            }],
            reglements=[{
                "moyen": PaymentMethod.NON_MONETAIRE,
                "montant": PRIX_PINS_EN_CENTIEMES_DE_POINTS,
            }],
        )
        from laboutik.printing.formatters import formatter_ticket_vente

        ticket = formatter_ticket_vente(vente, self.admin_du_lieu)

        assert ticket["unite"] == "Points ou temps"
        assert ticket["tva_breakdown"] == []

    # ------------------------------------------------------------------
    # Cotisation d'une adhesion payee en points / Points membership contribution
    # ------------------------------------------------------------------

    def _adhesion_payee_en_points(self):
        self._vendre_une_adhesion_en_points()
        return Membership.objects.get(user=self.client_de_la_carte)

    def test_la_contribution_d_une_adhesion_en_points_a_son_unite(self):
        """300 points : unite « Points fidelite » ; une cotisation en especes : €.
        / 300 points: "Points fidelite" unit; a cash contribution: €."""
        adhesion_en_points = self._adhesion_payee_en_points()
        adhesion_en_euros = Membership.objects.create(
            user=self.admin_du_lieu,
            price=self.adhesion.prices.first(),
            contribution_value=Decimal("10.00"),
            payment_method=PaymentMethod.CASH,
        )

        assert adhesion_en_points.unite_de_la_contribution() == "Points fidélité"
        assert adhesion_en_euros.unite_de_la_contribution() == "€"

    def test_mon_compte_affiche_la_cotisation_en_points(self):
        """Carte d'adhesion de « Mon compte » : « 300,00 Points fidélité », pas €.
        / "My account" membership card: points, not €."""
        from django.template.loader import render_to_string

        adhesion = self._adhesion_payee_en_points()

        contenu = render_to_string(
            "pages/classic/vues/compte/membership/membership_card.html",
            {"membership": adhesion},
        )

        zone = contenu[contenu.find("Contribution"):][:200]
        assert "<strong>300,00</strong> Points fidélité" in contenu, zone

    def test_la_carte_v2_affiche_la_cotisation_en_points(self):
        """Carte d'adhesion (gabarit V2) : « 300,00 Points fidélité ».
        / V2 membership card: points."""
        from django.template.loader import render_to_string

        adhesion = self._adhesion_payee_en_points()

        contenu = render_to_string(
            "pages/V2/vues/compte/membership/membership_card.html",
            {"membership": adhesion},
        )

        zone = contenu[contenu.find("Contribution"):][:200]
        assert "<dd>300,00 Points fidélité</dd>" in contenu, zone

    def test_le_renouvellement_d_une_adhesion_en_points_ne_preremplit_pas_d_euros(self):
        """Renouveler depuis l'admin : cotisation affichee en points ; le formulaire
        n'est pre-rempli ni du tarif, ni du montant, ni du moyen.
        / Admin renewal: contribution shown in points; no pre-filled price/amount/method."""
        adhesion = self._adhesion_payee_en_points()

        reponse = self.navigateur.get(f"/memberships/{adhesion.pk}/renouveller/")

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        zone = contenu[contenu.find("Contribution actuelle"):][:200]
        assert "300,00 Points fidélité" in contenu, zone
        lien = re.search(r'href="([^"]*membership/add/[^"]*)"', contenu).group(1)
        assert "email=" in lien, lien
        assert "contribution=" not in lien, lien
        assert "price=" not in lien, lien
        assert "payment_method=" not in lien, lien

    def test_la_fiche_utilisateur_de_l_admin_affiche_la_cotisation_en_points(self):
        """Fiche utilisateur (admin) : « 300,00 Points fidélité ».
        / Admin user page: points."""
        self._adhesion_payee_en_points()
        # La fiche utilisateur ne montre que les clients du lieu (client_achat)
        # / The admin user page only shows the venue's customers
        self.client_de_la_carte.client_achat.add(self.tenant)

        reponse = self.navigateur.get(
            f"/admin/AuthBillet/humanuser/{self.client_de_la_carte.pk}/change/"
        )

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        assert "300,00&nbsp;Points fidélité" in contenu

    def test_un_tarif_a_zero_point_est_refuse(self):
        """Admin : un tarif en points a 0 est refuse.
        / Admin: a 0-point price is refused."""
        formset = self._formset_des_tarifs(self.pins, prix="0.00")

        assert not formset.is_valid()
        assert "prix" in formset.forms[0].errors, formset.errors

    def test_un_fut_sans_tarif_en_euros_n_est_pas_facture(self):
        """Tireuse : fut avec un seul tarif au litre, en temps : prix au litre nul,
        donc pas de facture (facturer_tirage s'arrete avant tout debit).
        / Tap: keg with only a time per-litre price: no bill."""
        from controlvanne.billing import facturer_tirage, obtenir_contexte_cashless
        from controlvanne.models import RfidSession, TireuseBec

        fut = Product.objects.create(name="Fût en temps seulement", categorie_article=Product.FUT)
        Price.objects.create(
            product=fut, name="Litre bénévole", prix=Decimal("1.00"),
            poids_mesure=True, non_fiduciaire=True, asset=self.asset_temps,
        )
        tireuse = TireuseBec.objects.create(
            nom_tireuse="Tireuse en temps", enabled=True, fut_actif=fut,
            reservoir_ml=Decimal("30000.00"),
        )
        self._crediter_la_carte(self.asset_euros, 1000)
        session = RfidSession.objects.create(
            uid=self.carte.tag_id, carte=self.carte, tireuse_bec=tireuse, authorized=True
        )

        resultat = facturer_tirage(
            session, tireuse, self.carte, Decimal("500"),
            obtenir_contexte_cashless(self.carte),
        )

        assert resultat is None
        assert not LigneArticle.objects.exists()
        assert self._solde(self.asset_euros) == 1000

    def test_la_liste_des_ventes_sans_monnaie_connue(self):
        """Vente NM dont la monnaie est introuvable : « Points ou temps », pas €.
        La ligne appartient a une vente reglee (le service en cours commence a la
        premiere ligne des ventes reglees) dont l'unite est une monnaie inconnue.
        / NM sale with an unknown currency: "Points ou temps", not €."""
        produit_vendu = ProductSold.objects.create(product=self.tarif_pins.product)
        tarif_vendu = PriceSold.objects.create(
            productsold=produit_vendu, price=self.tarif_pins, prix=self.tarif_pins.prix
        )
        self._vente_reglee_au_comptoir(
            unite=str(uuid_module.uuid4()),
            articles=[{
                "pricesold": tarif_vendu,
                "quantite": Decimal("1"),
                "prix_unitaire": PRIX_PINS_EN_CENTIEMES_DE_POINTS,
                "taux_tva": Decimal("0"),
                "payment_method": PaymentMethod.NON_MONETAIRE,
                "status": LigneArticle.VALID,
                "point_de_vente": self.point_de_vente,
            }],
            reglements=[{
                "moyen": PaymentMethod.NON_MONETAIRE,
                "montant": PRIX_PINS_EN_CENTIEMES_DE_POINTS,
            }],
        )

        reponse = self.navigateur.get("/laboutik/caisse/liste-ventes/")

        contenu_brut = reponse.content.decode()
        contenu = texte_sans_espaces_en_trop(contenu_brut)
        assert reponse.status_code == 200, contenu[:400]
        assert textes_des_elements(contenu_brut, "vente-total") == [
            "300,00 Points ou temps"
        ]
        assert "300,00 €" not in contenu

    # ------------------------------------------------------------------
    # Article reparti sur deux moyens : total arrondi, jamais tronque
    # / Item split over two methods: rounded total, never truncated
    # ------------------------------------------------------------------

    def _vente_reglee_au_comptoir(self, unite, articles, reglements):
        """
        Une vente de caisse reglee, ecrite par le service de vente, dans l'unite
        donnee (« EUR » ou l'uuid d'une monnaie de points). Rend la vente.
        / A settled register sale written by the sale service, in the given unit.
        """
        vente = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VENTE,
            unite=unite,
            point_de_vente=self.point_de_vente,
        )
        for article in articles:
            ajouter_article(vente, **article)
        for reglement in reglements:
            ajouter_reglement(vente, **reglement)
        return encaisser_vente(vente)

    def _trois_jus_repartis_carte_et_monnaie_locale(self):
        """3 jus a 3,50 € : 5,50 € par CB et 5,00 € en monnaie locale. Les deux
        lignes ont le meme prix unitaire et des quantites a 6 decimales :
        350 × 1,571429 = 550,00015 et 350 × 1,428571 = 499,99985. Elles appartiennent
        a une vente reglee (le service en cours commence a la premiere ligne des ventes
        reglees), chacune avec son argent reel (`total_catalogue_impose`).
        / 3 juices at 3.50 €, split 5.50 € card + 5.00 € local currency, in one
        settled sale."""
        uuid_de_la_vente = uuid_module.uuid4()
        articles = []
        for moyen, quantite, argent_reel in [
            (PaymentMethod.CC, Decimal("1.571429"), 550),
            (PaymentMethod.LOCAL_EURO, Decimal("1.428571"), 500),
        ]:
            produit_vendu = ProductSold.objects.create(product=self.tarif_vin.product)
            tarif_vendu = PriceSold.objects.create(
                productsold=produit_vendu, price=self.tarif_vin, prix=self.tarif_vin.prix
            )
            articles.append({
                "pricesold": tarif_vendu,
                "quantite": quantite,
                "prix_unitaire": 350,
                "taux_tva": Decimal("20"),
                "total_catalogue_impose": argent_reel,
                "payment_method": moyen,
                "status": LigneArticle.VALID,
                "uuid_transaction": uuid_de_la_vente,
                "point_de_vente": self.point_de_vente,
            })
        vente = self._vente_reglee_au_comptoir(
            unite="EUR",
            articles=articles,
            reglements=[
                {"moyen": PaymentMethod.CC, "montant": 550},
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 500,
                    "asset": self.asset_euros.uuid,
                },
            ],
        )
        lignes = []
        for moyen in (PaymentMethod.CC, PaymentMethod.LOCAL_EURO):
            lignes.append(LigneArticle.objects.get(vente=vente, payment_method=moyen))
        return uuid_de_la_vente, lignes

    def test_le_total_d_une_ligne_repartie_est_arrondi(self):
        """550,00015 → 550 et 499,99985 → 500 (et non 499).
        / Rounded, not truncated."""
        _uuid, (ligne_cb, ligne_locale) = self._trois_jus_repartis_carte_et_monnaie_locale()

        assert ligne_cb.total() == 550
        assert ligne_locale.total() == 500

    def test_le_detail_d_une_vente_repartie_tombe_juste(self):
        """Detail de la vente a la caisse : 10,50 €, et UN article de 10,50 € (les
        deux parts 500 + 550 forment un seul article).
        / Sale detail: 10.50 €, and ONE 10.50 € item (both parts form one item)."""
        _uuid_du_paiement, lignes = self._trois_jus_repartis_carte_et_monnaie_locale()
        uuid_de_la_vente = lignes[0].vente_id

        reponse = self.navigateur.get(f"/laboutik/caisse/detail-vente/{uuid_de_la_vente}/")

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        totaux_de_la_vente = textes_des_elements(contenu, "detail-total-transaction")
        assert totaux_de_la_vente == ["10,50 €"], totaux_de_la_vente
        totaux_des_lignes = textes_des_elements(contenu, "detail-total-ligne")
        assert totaux_des_lignes == ["10,50 €"], totaux_des_lignes

    def test_la_liste_des_ventes_filtree_sur_la_monnaie_locale_tombe_juste(self):
        """Liste des ventes filtree sur la monnaie locale : 5,00 € (et non 4,99 €).
        / Sales list filtered on local currency: 5.00 €, not 4.99 €."""
        self._trois_jus_repartis_carte_et_monnaie_locale()

        reponse = self.navigateur.get("/laboutik/caisse/liste-ventes/?moyen=LE")

        contenu_brut = reponse.content.decode()
        contenu = texte_sans_espaces_en_trop(contenu_brut)
        assert reponse.status_code == 200, contenu[:400]
        assert "4,99 €" not in contenu
        # Toute la vente (10,50 €), et sa part en monnaie locale (5,00 €, jamais
        # 4,99 €) dans les moyens en clair.
        # / The whole sale, and its local currency part (5.00 €, never 4.99 €).
        assert textes_des_elements(contenu_brut, "vente-total") == ["10,50 €"]
        assert textes_des_elements(contenu_brut, "vente-moyens") == [
            "5,50 € Carte bancaire + 5,00 € Monnaie locale en points"
        ]
