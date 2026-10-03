"""
tests/pytest/test_ticket_client_imprime.py
Le ticket client imprime apres une vente de caisse : articles, total, TVA et
detail des moyens de paiement.
/ The customer receipt printed after a register sale.

LOCALISATION : tests/pytest/test_ticket_client_imprime.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
Un article paye avec plusieurs monnaies donne plusieurs lignes de vente, au meme
prix unitaire, avec des quantites partielles (total = amount x qty). Le ticket :
- regroupe ces parts : le client lit « Vin x3 15,00 », pas « x1,2 » puis « x1,8 » ;
- calcule chaque montant sur amount x qty (jamais une quantite tronquee) ;
- detaille ce qui a ete paye par chaque moyen (monnaies de carte par nom,
  especes, CB), et l'imprime quand au moins deux moyens ont servi.

Les ventes passent par la vraie route de paiement, dans un schema de test
dedie. Le formateur et les deux moteurs d'impression (ESC/POS et Sunmi interne)
sont ensuite appeles sur les lignes que la caisse a vraiment creees.
/ Sales go through the real payment route; the formatter and both print
engines then run on the lines the register actually created.

Lancement / Run:
    make test ARGS="tests/pytest/test_ticket_client_imprime.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import html  # noqa: E402
import re  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest import mock  # noqa: E402

from django.db import connection  # noqa: E402
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
from laboutik.printing.escpos_builder import build_escpos_from_ticket_data  # noqa: E402
from laboutik.printing.formatters import formatter_ticket_vente  # noqa: E402
from laboutik.printing.sunmi_inner import ticket_data_to_json_commands  # noqa: E402

NOM_MONNAIE_CADEAU = "Cadeau ticket"
NOM_MONNAIE_LOCALE = "Monnaie locale ticket"


def _extraire_champ_cache(contenu_html, nom_du_champ):
    """Valeur d'un <input type=hidden name=...> du HTML rendu.
    / Value of a hidden input in the rendered HTML."""
    motif = re.compile(r'name="' + re.escape(nom_du_champ) + r'"\s+value="([^"]*)"')
    correspondance = motif.search(contenu_html)
    if correspondance is None:
        return None
    return html.unescape(correspondance.group(1))


class TestTicketClientImprime(FastTenantTestCase):
    """Le ticket client suit la regle total = amount x qty.
    / The customer receipt follows total = amount x qty."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_ticket_client"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-ticket-client.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test ticket client"

    def setUp(self):
        """Un point de vente, deux articles a TVA 20 %, deux monnaies.
        / One point of sale, two 20 % VAT items, two currencies."""
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
        tva_a_vingt, _cree = Tva.objects.get_or_create(tva_rate=Decimal("20"))
        categorie = CategorieProduct.objects.create(name="Boissons ticket client")

        self.vin = Product.objects.create(
            name="Vin ticket",
            methode_caisse=Product.VENTE,
            categorie_pos=categorie,
            tva=tva_a_vingt,
        )
        Price.objects.create(product=self.vin, name="Verre", prix=Decimal("5.00"))

        self.bouteille = Product.objects.create(
            name="Bouteille ticket",
            methode_caisse=Product.VENTE,
            categorie_pos=categorie,
            tva=tva_a_vingt,
        )
        Price.objects.create(
            product=self.bouteille, name="Bouteille", prix=Decimal("10.00")
        )

        self.point_de_vente = PointDeVente.objects.create(
            name="Comptoir ticket client",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.point_de_vente.products.add(self.vin, self.bouteille)

        # Deux monnaies : cadeau (TNF, debitee en premier) et locale (TLF).
        # / Two currencies: gift (TNF, debited first) and local (TLF).
        wallet_du_lieu = Wallet.objects.create(
            origin=self.tenant, name="Wallet lieu ticket client"
        )
        self.asset_cadeau = AssetService.creer_asset(
            tenant=self.tenant,
            name=NOM_MONNAIE_CADEAU,
            category=Asset.TNF,
            currency_code="EUR",
            wallet_origin=wallet_du_lieu,
        )
        self.asset_local = AssetService.creer_asset(
            tenant=self.tenant,
            name=NOM_MONNAIE_LOCALE,
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=wallet_du_lieu,
        )

        # Caissier : admin du lieu, session navigateur.
        # / Cashier: venue admin, browser session.
        caissier, _cree = TibilletUser.objects.get_or_create(
            email="caissier-ticket-client@tibillet.localhost",
            defaults={
                "username": "caissier-ticket-client@tibillet.localhost",
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

    def _carte_avec_soldes(self, tag_id, solde_cadeau, solde_local):
        """Une carte liee a un client, avec ses soldes cadeau et locaux.
        / A card linked to a customer, with gift and local balances."""
        client = TibilletUser.objects.create(
            email=f"client-{tag_id.lower()}@tibillet.localhost",
            username=f"client-{tag_id.lower()}@tibillet.localhost",
        )
        wallet_du_client = Wallet.objects.create(
            origin=self.tenant, name=f"Wallet {tag_id}"
        )
        client.wallet = wallet_du_client
        client.save()
        carte = CarteCashless.objects.create(tag_id=tag_id, number=tag_id, user=client)
        Token.objects.create(
            wallet=wallet_du_client, asset=self.asset_cadeau, value=solde_cadeau
        )
        Token.objects.create(
            wallet=wallet_du_client, asset=self.asset_local, value=solde_local
        )
        return carte

    def _donnees_de_paiement(self, moyen, produit, quantite, prix_centimes):
        return {
            "uuid_pv": str(self.point_de_vente.uuid),
            "moyen_paiement": moyen,
            "total": str(prix_centimes * quantite),
            "given_sum": "0",
            f"repid-{produit.uuid}": str(quantite),
        }

    def _poster(self, chemin, donnees):
        """POST sur la caisse, reseau federe coupe (cascade locale).
        / POST to the register, federated network off (local cascade)."""
        with (
            mock.patch("laboutik.views.FedowConfig") as configuration_fedow,
            mock.patch("laboutik.views.FedowAPI"),
        ):
            configuration_fedow.get_solo.return_value.can_fedow.return_value = False
            return self.navigateur.post(chemin, data=donnees)

    def _payer_par_carte(self, carte, produit, quantite, prix_centimes):
        donnees = self._donnees_de_paiement("nfc", produit, quantite, prix_centimes)
        donnees["tag_id"] = carte.tag_id
        reponse = self._poster("/laboutik/paiement/payer/", donnees)
        assert reponse.status_code == 200, reponse.content.decode()[:400]
        return reponse

    def _lignes_du_paiement_de(self, carte):
        """Toutes les lignes du paiement (y compris un complement en especes).
        / All lines of the payment (including a cash complement)."""
        ligne_de_la_carte = LigneArticle.objects.filter(carte=carte).first()
        assert ligne_de_la_carte is not None, "Aucune ligne pour cette carte."
        return LigneArticle.objects.filter(
            uuid_transaction=ligne_de_la_carte.uuid_transaction
        ).select_related("pricesold__productsold")

    def _ticket(self, lignes):
        return formatter_ticket_vente(lignes, self.point_de_vente, None, "")

    def _detail_par_nom(self, ticket):
        return {entree["name"]: entree["total"] for entree in ticket["cascade_detail"]}

    def _payer_trois_vins_carte_puis_especes(self):
        """3 vins (15 €) : carte 6 € cadeau + 4 € locale, complement 5 € especes.
        / 3 wines: card 6 € gift + 4 € local, 5 € cash complement."""
        carte = self._carte_avec_soldes("TKC6AAAA", solde_cadeau=600, solde_local=400)
        premiere_reponse = self._payer_par_carte(
            carte, self.vin, quantite=3, prix_centimes=500
        )
        contenu = premiere_reponse.content.decode()
        reponse_complement = self._poster(
            "/laboutik/paiement/payer_complementaire/",
            {
                "uuid_pv": str(self.point_de_vente.uuid),
                "moyen_complement": "espece",
                "tag_id_carte1": carte.tag_id,
                "cascade_carte1": _extraire_champ_cache(contenu, "cascade_carte1"),
                "total_nfc_carte1": _extraire_champ_cache(contenu, "total_nfc_carte1"),
                "given_sum": "",
                f"repid-{self.vin.uuid}": "3",
            },
        )
        assert reponse_complement.status_code == 200, (
            reponse_complement.content.decode()[:400]
        )
        return carte

    # ------------------------------------------------------------------
    # Le formateur / The formatter
    # ------------------------------------------------------------------

    def test_les_parts_d_un_article_sont_regroupees_par_taux(self):
        """3 vins payes 6 € cadeau + 9 € locale. Les parts d'un article se regroupent
        quand elles ont le meme taux de TVA. La part en jetons est a TVA 0 (D8 bis), la
        part en monnaie locale a 20 % : deux lignes, « x1.20 6,00 » et « x1.80 9,00 ».
        Le total du ticket reste 15,00 €.
        / 3 wines paid 6 € gift + 9 € local: parts group by VAT rate; the token part is
        at 0 %, the local part at 20 %: two lines, total 15.00 €."""
        carte = self._carte_avec_soldes("TKC1AAAA", solde_cadeau=600, solde_local=900)
        self._payer_par_carte(carte, self.vin, quantite=3, prix_centimes=500)

        ticket = self._ticket(self._lignes_du_paiement_de(carte))

        assert len(ticket["articles"]) == 2, ticket["articles"]
        taux_quantites_et_totaux = []
        for article in ticket["articles"]:
            taux_quantites_et_totaux.append(
                (article["vat_rate"], article["qty"], article["total"])
            )
        assert sorted(taux_quantites_et_totaux) == [
            ("0.00", "1.20", 600),
            ("20.00", "1.80", 900),
        ]
        assert ticket["total"]["amount"] == 1500

    def test_une_part_inferieure_a_un_article_n_est_pas_perdue(self):
        """Une bouteille a 10 € payee 2 € cadeau + 8 € locale : deux lignes (TVA 0 pour
        les jetons, D8 bis), 2,00 € et 8,00 € ; le ticket affiche 10,00 €.
        / A 10 € bottle paid 2 € + 8 €: two lines (2.00 and 8.00), total 10.00 €."""
        carte = self._carte_avec_soldes("TKC2AAAA", solde_cadeau=200, solde_local=800)
        self._payer_par_carte(carte, self.bouteille, quantite=1, prix_centimes=1000)

        ticket = self._ticket(self._lignes_du_paiement_de(carte))

        totaux_des_lignes = []
        for article in ticket["articles"]:
            totaux_des_lignes.append(article["total"])
        assert sorted(totaux_des_lignes) == [200, 800]
        assert ticket["total"]["amount"] == 1000

    def test_le_detail_donne_le_montant_paye_par_chaque_monnaie(self):
        """3 vins payes 6 € cadeau + 9 € locale : detail 6,00 / 9,00.
        / Detail shows 6.00 / 9.00."""
        carte = self._carte_avec_soldes("TKC3AAAA", solde_cadeau=600, solde_local=900)
        self._payer_par_carte(carte, self.vin, quantite=3, prix_centimes=500)

        ticket = self._ticket(self._lignes_du_paiement_de(carte))

        assert self._detail_par_nom(ticket) == {
            NOM_MONNAIE_CADEAU: 600,
            NOM_MONNAIE_LOCALE: 900,
        }

    def test_un_paiement_en_especes_garde_sa_quantite(self):
        """2 vins en especes : x2, 10,00 €, un seul moyen dans le detail.
        / 2 wines in cash: x2, 10.00 €, one method in the detail."""
        donnees = self._donnees_de_paiement("espece", self.vin, 2, 500)
        reponse = self._poster("/laboutik/paiement/payer/", donnees)
        assert reponse.status_code == 200, reponse.content.decode()[:400]

        lignes = LigneArticle.objects.filter(
            pricesold__productsold__product=self.vin
        ).select_related("pricesold__productsold")
        ticket = self._ticket(lignes)

        assert ticket["articles"][0]["qty"] == 2
        assert ticket["articles"][0]["total"] == 1000
        assert len(ticket["cascade_detail"]) == 1, ticket["cascade_detail"]

    def test_la_tva_du_ticket_porte_sur_la_part_en_argent(self):
        """15 € TTC, dont 6 € payes en jetons (TVA 0, D8 bis) et 9 € en monnaie
        locale a 20 % : taux 0 HT 6,00 € ; taux 20 % HT 7,50 €, TVA 1,50 €.
        / 15 € incl. VAT: 6 € in tokens at 0 %, 9 € at 20 % (7.50 HT, 1.50 VAT)."""
        carte = self._carte_avec_soldes("TKC5AAAA", solde_cadeau=600, solde_local=900)
        self._payer_par_carte(carte, self.vin, quantite=3, prix_centimes=500)

        ticket = self._ticket(self._lignes_du_paiement_de(carte))

        tva_par_taux = {}
        for ligne_de_tva in ticket["tva_breakdown"]:
            tva_par_taux[ligne_de_tva["rate"]] = ligne_de_tva
        assert tva_par_taux == {
            "0.00": {"rate": "0.00", "ht": 600, "tva": 0, "ttc": 600},
            "20.00": {"rate": "20.00", "ht": 750, "tva": 150, "ttc": 900},
        }

    def test_le_detail_inclut_le_complement_en_especes(self):
        """Carte 6 € cadeau + 4 € locale, complement 5 € especes : trois moyens.
        / Card 6 € gift + 4 € local, 5 € cash complement: three methods."""
        carte = self._payer_trois_vins_carte_puis_especes()

        ticket = self._ticket(self._lignes_du_paiement_de(carte))

        assert self._detail_par_nom(ticket) == {
            NOM_MONNAIE_CADEAU: 600,
            NOM_MONNAIE_LOCALE: 400,
            "Espèces": 500,
        }
        assert ticket["total"]["amount"] == 1500

    def test_le_detail_suit_l_ordre_de_la_cascade(self):
        """Cadeau, puis monnaie locale (ordre du debit), puis especes.
        / Gift, then local currency (debit order), then cash."""
        carte = self._payer_trois_vins_carte_puis_especes()

        ticket = self._ticket(self._lignes_du_paiement_de(carte))

        noms_dans_l_ordre = [entree["name"] for entree in ticket["cascade_detail"]]
        assert noms_dans_l_ordre == [NOM_MONNAIE_CADEAU, NOM_MONNAIE_LOCALE, "Espèces"]

    def test_une_part_en_monnaie_federee_porte_un_libelle_francais(self):
        """Une part payee en monnaie federee s'imprime « Monnaie fédérée ».

        La monnaie federee n'existe pas comme asset local : son libelle vient du
        moyen de paiement (STRIPE_FED). Les lignes sont posees a la main : une
        vraie part federee demande le Fedow distant.
        / The federated currency is not a local asset: its label comes from the
        payment method. Lines are created by hand (a real share needs Fedow).
        """
        import uuid as uuid_module

        from BaseBillet.models import PaymentMethod, PriceSold, ProductSold, SaleOrigin

        tarif_vendu = PriceSold.objects.create(
            productsold=ProductSold.objects.create(product=self.bouteille),
            price=self.bouteille.prices.first(),
            prix=Decimal("10.00"),
        )
        paiement = uuid_module.uuid4()
        for moyen, qty in (
            (PaymentMethod.STRIPE_FED, Decimal("0.6")),
            (PaymentMethod.CASH, Decimal("0.4")),
        ):
            LigneArticle.objects.create(
                pricesold=tarif_vendu,
                qty=qty,
                amount=1000,
                payment_method=moyen,
                status=LigneArticle.VALID,
                sale_origin=SaleOrigin.LABOUTIK,
                uuid_transaction=paiement,
                asset=uuid_module.uuid4()
                if moyen == PaymentMethod.STRIPE_FED
                else None,
            )

        ticket = self._ticket(LigneArticle.objects.filter(uuid_transaction=paiement))

        assert self._detail_par_nom(ticket) == {"Monnaie fédérée": 600, "Espèces": 400}

    # ------------------------------------------------------------------
    # Les moteurs d'impression / The print engines
    # ------------------------------------------------------------------

    def test_l_imprimante_escpos_imprime_le_detail_des_moyens(self):
        """Paiement a trois moyens : chaque moyen est imprime avec son montant.
        / Three methods: each method is printed with its amount."""
        carte = self._payer_trois_vins_carte_puis_especes()
        ticket = self._ticket(self._lignes_du_paiement_de(carte))

        texte = build_escpos_from_ticket_data(576, ticket).decode(
            "utf-8", errors="ignore"
        )

        assert f"{NOM_MONNAIE_CADEAU}  6.00EUR" in texte
        assert f"{NOM_MONNAIE_LOCALE}  4.00EUR" in texte
        assert "Espèces  5.00EUR" in texte

    def test_l_imprimante_escpos_n_imprime_pas_le_detail_d_un_seul_moyen(self):
        """Un ticket paye d'un seul moyen n'imprime pas de bloc de detail.
        / A single-method receipt prints no detail block."""
        carte = self._payer_trois_vins_carte_puis_especes()
        ticket = self._ticket(self._lignes_du_paiement_de(carte))
        ticket["cascade_detail"] = ticket["cascade_detail"][:1]

        texte = build_escpos_from_ticket_data(576, ticket).decode(
            "utf-8", errors="ignore"
        )

        assert f"{NOM_MONNAIE_CADEAU}  6.00EUR" not in texte

    def test_l_imprimante_sunmi_interne_imprime_le_detail_des_moyens(self):
        """Meme regle pour l'imprimante interne Sunmi.
        / Same rule for the Sunmi built-in printer."""
        carte = self._payer_trois_vins_carte_puis_especes()
        ticket = self._ticket(self._lignes_du_paiement_de(carte))

        textes = [
            commande.get("value", "")
            for commande in ticket_data_to_json_commands(ticket)
        ]
        assert any("Espèces" in texte and "5.00" in texte for texte in textes), textes
        assert any(NOM_MONNAIE_CADEAU in texte for texte in textes), textes
