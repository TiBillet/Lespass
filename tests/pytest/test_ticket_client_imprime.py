"""
tests/pytest/test_ticket_client_imprime.py
Le ticket client imprime apres une vente de caisse : il lit la VENTE.
/ The customer receipt printed after a register sale: it reads the SALE.

LOCALISATION : tests/pytest/test_ticket_client_imprime.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
`formatter_ticket_vente(vente, operateur)` (laboutik/printing/formatters.py) lit la
vente (`Vente`, ses articles, ses reglements) :
- le NUMERO DE LA VENTE est imprime (« Vente n° 12 »), sur les deux imprimantes ;
- les articles sont regroupes comme dans le detail d'une vente a l'ecran : un
  article paye avec plusieurs moyens (plusieurs « parts ») reste UN article, avec sa
  quantite reelle et son total (somme des nets vendus figes sur les lignes) ;
- le TOTAL est le net vendu de la vente (`Vente.total_ttc`) : un article offert
  compte 0, et sa part offerte est montree a part ;
- la TVA par taux est la somme des HT et des TVA figes sur les lignes ;
- le detail des reglements reprend les libelles et l'ordre de la liste des ventes
  (un moyen d'argent par son nom, un reglement cashless par le nom de sa monnaie ; le
  comptoir d'abord, le cashless ensuite) ; il n'est imprime qu'avec au moins deux
  moyens ;
- chaque ligne du pied tient en 32 caracteres (papier 58 mm).
La re-impression passe par l'uuid de la vente (route `imprimer_ticket`) ; le
journal des impressions la compte par vente : la deuxieme impression de la meme
vente est un DUPLICATA (laboutik/printing/tasks.py).
/ The formatter reads the sale; reprint by sale uuid, DUPLICATE counted per sale.

DONNEES
Les ventes a la carte passent par la vraie route de paiement (cascade jetons cadeau,
puis monnaie locale, puis complement), dans un schema de test dedie. Les autres sont
ecrites par le service de vente (`fabriques_vente.py`). Chaque test annule sa
transaction.
/ Card sales through the real payment route; others through the sale service.

D'OU VIENNENT LES VALEURS ATTENDUES (calculees a la main)
- 3 vins a 5,00 € = 15,00 € (1500), payes 6,00 € en jetons cadeau (TVA 0, D8 bis)
  et 9,00 € en monnaie locale (TVA 20 %) : HT 900 × 100 / 120 = 750, TVA 150.
- Complement : carte 6,00 € cadeau + 4,00 € locale, 5,00 € en especes.
- Une bouteille a 10,00 € payee 2,00 € cadeau + 8,00 € locale.
- Un jus a 3,50 € paye en especes et une pinte a 5,00 € offerte : TOTAL 350, part
  offerte 500.
- Les libelles sont ceux de la caisse en francais (« Espèces ») ; un reglement
  cashless porte le nom de sa monnaie, creee par le test.

Specification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-G-lecteurs.md (§3, §5
test 10) ; CHANTIER-04-C-ticket-imprime.md (detail des moyens).

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
import json  # noqa: E402
import re  # noqa: E402
import uuid as uuid_module  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from datetime import timezone as dt_timezone  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest import mock  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

from AuthBillet.models import TibilletUser, Wallet  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    CategorieProduct,
    Configuration,
    Event,
    LigneArticle,
    PaymentMethod,
    Price,
    PriceSold,
    Product,
    ProductSold,
    SaleOrigin,
    Tva,
)
from BaseBillet.models_vente import Vente  # noqa: E402
from QrcodeCashless.models import CarteCashless  # noqa: E402
from fabriques_ecran import attributs_des_elements  # noqa: E402
from fabriques_panier import taches_celery_enregistrees  # noqa: E402
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from fedow_core.models import Asset, Token  # noqa: E402
from fedow_core.services import AssetService  # noqa: E402
from laboutik.models import (  # noqa: E402
    ImpressionLog,
    LaboutikConfiguration,
    PointDeVente,
    Printer,
)
from laboutik.printing.escpos_builder import build_escpos_from_ticket_data  # noqa: E402
from laboutik.printing.formatters import formatter_ticket_vente  # noqa: E402
from laboutik.printing.sunmi_inner import ticket_data_to_json_commands  # noqa: E402
from laboutik.printing.tasks import imprimer_async  # noqa: E402

NOM_MONNAIE_CADEAU = "Cadeau ticket"
NOM_MONNAIE_LOCALE = "Monnaie locale ticket"

# La largeur d'une ligne de ticket (papier 58 mm), ecrite a la main.
# / The width of a ticket line (58 mm paper), hand-written.
LARGEUR_D_UNE_LIGNE_DE_TICKET = 32

# Un pied de ticket plus large qu'une ligne : il doit etre replie.
# / A footer wider than one line: it must be folded.
PIED_DE_TICKET_TROP_LONG = (
    "Merci pour votre passage, a bientot au bar associatif du quartier !"
)

# Le fuseau du lieu : les dates du ticket s'y ecrivent (le serveur est en UTC).
# / The venue's time zone: receipt dates are written in it (server in UTC).
FUSEAU_DU_LIEU = "Europe/Paris"

URL_DE_L_IMPRESSION_DU_TICKET = "/laboutik/paiement/imprimer_ticket/"
DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE = "/laboutik/caisse/detail-vente/"


def _extraire_champ_cache(contenu_html, nom_du_champ):
    """Valeur d'un <input type=hidden name=...> du HTML rendu.
    / Value of a hidden input in the rendered HTML."""
    motif = re.compile(r'name="' + re.escape(nom_du_champ) + r'"\s+value="([^"]*)"')
    correspondance = motif.search(contenu_html)
    if correspondance is None:
        return None
    return html.unescape(correspondance.group(1))


def _textes_de_l_imprimante_sunmi(ticket):
    """Les textes envoyes a l'imprimante Sunmi interne.
    / The texts sent to the Sunmi built-in printer."""
    textes = []
    commandes = ticket_data_to_json_commands(ticket)
    for commande in commandes:
        textes.append(str(commande.get("value", "")))
    return textes


def _texte_de_l_imprimante_escpos(ticket):
    """Le texte envoye a l'imprimante ESC/POS (reseau, cloud).
    / The text sent to the ESC/POS printer."""
    return build_escpos_from_ticket_data(576, ticket).decode("utf-8", errors="ignore")


class ImprimanteSimulee:
    """
    Remplace l'envoi reel a l'imprimante : garde une copie de chaque ticket recu et
    repond que l'impression a reussi.
    / Replaces the real printer call: keeps a copy of each ticket, answers success.
    """

    def __init__(self):
        self.tickets_recus = []

    def imprimer(self, imprimante, donnees_du_ticket):
        self.tickets_recus.append(dict(donnees_du_ticket))
        return {"ok": True}


class TestTicketClientImprime(FastTenantTestCase):
    """Le ticket client lit la vente.
    / The customer receipt reads the sale."""

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
        """Un point de vente, deux articles a TVA 20 %, deux monnaies, un caissier.
        / One point of sale, two 20 % VAT items, two currencies, a cashier."""
        # Le rollback du test precedent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.rapport_emails = ""
        configuration.fuseau_horaire = FUSEAU_DU_LIEU
        configuration.save()

        # Le singleton de la caisse doit exister en base (PIEGES 9.86). Son pied de
        # ticket est remis a vide : le cache garde celui du test precedent.
        # / The register singleton must exist; its footer is reset (cache).
        configuration_de_la_caisse = LaboutikConfiguration.get_solo()
        configuration_de_la_caisse.pied_ticket = ""
        configuration_de_la_caisse.save()

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
        self.caissier, _cree = TibilletUser.objects.get_or_create(
            email="caissier-ticket-client@tibillet.localhost",
            defaults={
                "username": "caissier-ticket-client@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        self.caissier.client_admin.add(self.tenant)
        self.navigateur = TenantClient(self.tenant, HTTP_ACCEPT_LANGUAGE="fr")
        self.navigateur.force_login(self.caissier)

    # ------------------------------------------------------------------
    # Utilitaires : les ventes par la route de paiement
    # / Helpers: sales through the payment route
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

    def _vente_payee_par(self, carte):
        """La vente du paiement fait avec cette carte (complement compris), lue par sa
        carte (`Vente.carte`) : la ligne ne porte pas la carte, elle est sur la vente
        et ses règlements (Q-H2).
        / The sale of the payment made with this card, read through Vente.carte."""
        ventes_de_la_carte = list(Vente.objects.filter(carte=carte))
        assert len(ventes_de_la_carte) == 1, (
            f"Attendu : une vente pour cette carte, trouvé : {len(ventes_de_la_carte)}."
        )
        return ventes_de_la_carte[0]

    def _ticket(self, vente):
        return formatter_ticket_vente(vente, None)

    def _detail_par_nom(self, ticket):
        detail_par_nom = {}
        for entree in ticket["cascade_detail"]:
            detail_par_nom[entree["name"]] = entree["total"]
        return detail_par_nom

    def _payer_trois_vins_carte_puis_especes(self):
        """3 vins (15 €) : carte 6 € cadeau + 4 € locale, complement 5 € especes.
        Rend la vente.
        / 3 wines: card 6 € gift + 4 € local, 5 € cash complement. Returns the sale."""
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
        return self._vente_payee_par(carte)

    def _payer_deux_vins_en_especes(self):
        """2 vins (10 €) payes en especes, par la route. Rend la vente.
        / 2 wines paid in cash, through the route. Returns the sale."""
        donnees = self._donnees_de_paiement("espece", self.vin, 2, 500)
        reponse = self._poster("/laboutik/paiement/payer/", donnees)
        assert reponse.status_code == 200, reponse.content.decode()[:400]
        ligne_du_vin = LigneArticle.objects.filter(
            pricesold__productsold__product=self.vin
        ).first()
        return ligne_du_vin.vente

    # ------------------------------------------------------------------
    # Utilitaires : les ventes par le service de vente
    # / Helpers: sales through the sale service
    # ------------------------------------------------------------------

    def _vendre_un_jus_en_especes_et_offrir_une_pinte(self):
        """
        Un jus a 3,50 € paye en especes et une pinte a 5,00 € entierement offerte
        (bouton OFFRIR). Rend la vente.
        / A cash juice and a fully offered pint. Returns the sale.
        """
        tarif_du_jus = creer_tarif_vendu(nom="Jus", prix_en_euros="3.50")
        tarif_de_la_pinte = creer_tarif_vendu(nom="Pinte", prix_en_euros="5.00")
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            articles=[
                {
                    "pricesold": tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.CASH,
                    "status": LigneArticle.VALID,
                    "point_de_vente": self.point_de_vente,
                },
                {
                    "pricesold": tarif_de_la_pinte,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                    "offert_en_totalite": True,
                    "status": LigneArticle.VALID,
                    "point_de_vente": self.point_de_vente,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
        )
        verifier_egalites(vente)
        return vente

    def _vendre_une_biere_en_especes(self):
        """
        Une biere a 5,00 € payee en especes, au comptoir, ligne avec son
        identifiant de paiement comme la caisse l'ecrit. Rend la vente.
        / A cash beer at the counter. Returns the sale.
        """
        tarif_de_la_biere = creer_tarif_vendu(nom="Biere", prix_en_euros="5.00")
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            operateur=self.caissier,
            articles=[
                {
                    "pricesold": tarif_de_la_biere,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.CASH,
                    "status": LigneArticle.VALID,
                    "uuid_transaction": uuid_module.uuid4(),
                    "point_de_vente": self.point_de_vente,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 500}],
        )
        verifier_egalites(vente)
        return vente

    # ------------------------------------------------------------------
    # Le formateur : articles, total, TVA
    # / The formatter: items, total, VAT
    # ------------------------------------------------------------------

    def test_un_article_paye_par_deux_monnaies_est_un_seul_article(self):
        """3 vins payes 6 € en jetons cadeau (TVA 0) + 9 € en monnaie locale (TVA
        20 %) : UNE ligne, UN article sur le ticket, « x3 », total 15,00 €, comme dans
        le detail de la vente a l'ecran. Le total du ticket est 15,00 €.
        / ONE line, ONE item on the receipt: x3, 15.00 €."""
        carte = self._carte_avec_soldes("TKC1AAAA", solde_cadeau=600, solde_local=900)
        self._payer_par_carte(carte, self.vin, quantite=3, prix_centimes=500)

        ticket = self._ticket(self._vente_payee_par(carte))

        assert len(ticket["articles"]) == 1, ticket["articles"]
        assert ticket["articles"][0]["qty"] == 3
        assert ticket["articles"][0]["total"] == 1500
        assert ticket["total"]["amount"] == 1500

    def test_un_article_paye_en_partie_en_jetons_garde_sa_quantite(self):
        """Une bouteille a 10 € payee 2 € cadeau + 8 € locale : un article « x1 » a
        10,00 € ; le ticket affiche 10,00 €.
        / A 10 € bottle paid 2 € + 8 €: one item x1 at 10.00 €, total 10.00 €."""
        carte = self._carte_avec_soldes("TKC2AAAA", solde_cadeau=200, solde_local=800)
        self._payer_par_carte(carte, self.bouteille, quantite=1, prix_centimes=1000)

        ticket = self._ticket(self._vente_payee_par(carte))

        assert len(ticket["articles"]) == 1, ticket["articles"]
        assert ticket["articles"][0]["qty"] == 1
        assert ticket["articles"][0]["total"] == 1000
        assert ticket["total"]["amount"] == 1000

    def test_un_paiement_en_especes_garde_sa_quantite(self):
        """2 vins en especes : x2, 10,00 €.
        / 2 wines in cash: x2, 10.00 €."""
        vente = self._payer_deux_vins_en_especes()

        ticket = self._ticket(vente)

        assert ticket["articles"][0]["qty"] == 2
        assert ticket["articles"][0]["total"] == 1000
        assert ticket["total"]["amount"] == 1000

    def test_la_tva_du_ticket_est_celle_figee_sur_les_lignes(self):
        """15 € TTC, dont 6 € payes en jetons (TVA 0, D8 bis) et 9 € en monnaie
        locale a 20 % : taux 0 HT 6,00 € ; taux 20 % HT 7,50 €, TVA 1,50 €.
        / 15 € incl. VAT: 6 € in tokens at 0 %, 9 € at 20 % (7.50 HT, 1.50 VAT)."""
        carte = self._carte_avec_soldes("TKC5AAAA", solde_cadeau=600, solde_local=900)
        self._payer_par_carte(carte, self.vin, quantite=3, prix_centimes=500)

        ticket = self._ticket(self._vente_payee_par(carte))

        tva_par_taux = {}
        for ligne_de_tva in ticket["tva_breakdown"]:
            tva_par_taux[ligne_de_tva["rate"]] = ligne_de_tva
        assert tva_par_taux == {
            "0.00": {"rate": "0.00", "ht": 600, "tva": 0, "ttc": 600},
            "20.00": {"rate": "20.00", "ht": 750, "tva": 150, "ttc": 900},
        }

    def test_le_total_est_le_net_vendu_et_l_offert_est_montre_a_part(self):
        """Un jus a 3,50 € en especes et une pinte a 5,00 € offerte : TOTAL 3,50 €
        (le net vendu de la vente) ; l'article pinte vaut 0,00 € et porte sa part
        offerte de 5,00 €, imprimee sous l'article.
        / TOTAL is the net sold (3.50 €); the offered pint is 0.00 € with its 5.00 €
        offered part printed."""
        vente = self._vendre_un_jus_en_especes_et_offrir_une_pinte()

        ticket = self._ticket(vente)

        assert ticket["total"]["amount"] == 350
        totaux_et_offerts = []
        for article in ticket["articles"]:
            totaux_et_offerts.append((article["total"], article.get("offert", 0)))
        assert sorted(totaux_et_offerts) == [(0, 500), (350, 0)]
        lignes_imprimees = _texte_de_l_imprimante_escpos(ticket).splitlines()
        ligne_de_l_offert_imprimee = False
        for ligne_imprimee in lignes_imprimees:
            if "Offert" in ligne_imprimee and "5.00" in ligne_imprimee:
                ligne_de_l_offert_imprimee = True
        assert ligne_de_l_offert_imprimee, lignes_imprimees

    # ------------------------------------------------------------------
    # Le formateur : le numero de la vente et le pied
    # / The formatter: the sale number and the footer
    # ------------------------------------------------------------------

    def test_le_ticket_porte_le_numero_de_la_vente_sur_les_deux_imprimantes(self):
        """Le numero de la vente est imprime « Vente n° <numero> », sur l'imprimante
        ESC/POS et sur l'imprimante Sunmi interne.
        / The sale number is printed on both printers."""
        vente = self._vendre_une_biere_en_especes()
        numero_attendu = re.compile(rf"Vente n°\s*{vente.numero}\b")

        ticket = self._ticket(vente)

        assert numero_attendu.search(_texte_de_l_imprimante_escpos(ticket))
        textes_sunmi = _textes_de_l_imprimante_sunmi(ticket)
        numero_imprime_sur_sunmi = False
        for texte_sunmi in textes_sunmi:
            if numero_attendu.search(texte_sunmi):
                numero_imprime_sur_sunmi = True
        assert numero_imprime_sur_sunmi, textes_sunmi

    def test_le_pied_du_ticket_tient_en_32_caracteres(self):
        """Un pied de ticket de 67 caracteres : chaque ligne du pied tient en 32
        caracteres, et aucun mot n'est perdu.
        / A 67-character footer: each footer line fits 32 characters, no word lost."""
        configuration_de_la_caisse = LaboutikConfiguration.get_solo()
        configuration_de_la_caisse.pied_ticket = PIED_DE_TICKET_TROP_LONG
        configuration_de_la_caisse.save()
        vente = self._vendre_une_biere_en_especes()

        ticket = self._ticket(vente)

        for ligne_du_pied in ticket["footer"]:
            assert len(ligne_du_pied) <= LARGEUR_D_UNE_LIGNE_DE_TICKET, ligne_du_pied
        mots_du_pied = " ".join(ticket["footer"]).split()
        for mot_attendu in PIED_DE_TICKET_TROP_LONG.split():
            assert mot_attendu in mots_du_pied, ticket["footer"]

    # ------------------------------------------------------------------
    # Le formateur : le detail des reglements
    # / The formatter: the payments detail
    # ------------------------------------------------------------------

    def test_le_detail_donne_le_montant_de_chaque_reglement(self):
        """3 vins payes 6 € cadeau + 9 € locale : un reglement par monnaie, ecrit
        par le nom de sa monnaie : 6,00 / 9,00.
        / One payment per currency, written by its currency name: 6.00 / 9.00."""
        carte = self._carte_avec_soldes("TKC3AAAA", solde_cadeau=600, solde_local=900)
        self._payer_par_carte(carte, self.vin, quantite=3, prix_centimes=500)

        ticket = self._ticket(self._vente_payee_par(carte))

        assert self._detail_par_nom(ticket) == {
            NOM_MONNAIE_CADEAU: 600,
            NOM_MONNAIE_LOCALE: 900,
        }

    def test_le_detail_inclut_le_complement_en_especes(self):
        """Carte 6 € cadeau + 4 € locale, complement 5 € especes : trois reglements.
        / Card 6 € gift + 4 € local, 5 € cash complement: three payments."""
        vente = self._payer_trois_vins_carte_puis_especes()

        ticket = self._ticket(vente)

        assert self._detail_par_nom(ticket) == {
            NOM_MONNAIE_CADEAU: 600,
            NOM_MONNAIE_LOCALE: 400,
            "Espèces": 500,
        }
        assert ticket["total"]["amount"] == 1500

    def test_le_detail_suit_l_ordre_de_la_liste_des_ventes(self):
        """L'ordre de la liste des ventes : le comptoir d'abord (especes), puis le
        cashless par code de moyen (monnaie locale « LE », puis jetons cadeau « LG »).
        / The sales list order: counter first, then cashless by method code."""
        vente = self._payer_trois_vins_carte_puis_especes()

        ticket = self._ticket(vente)

        noms_dans_l_ordre = []
        for entree in ticket["cascade_detail"]:
            noms_dans_l_ordre.append(entree["name"])
        assert noms_dans_l_ordre == ["Espèces", NOM_MONNAIE_LOCALE, NOM_MONNAIE_CADEAU]

    def test_un_reglement_federe_sans_monnaie_connue_s_ecrit_monnaie_federee(self):
        """Une bouteille a 10 € payee 6 € en monnaie federee (monnaie inconnue du
        lieu) + 4 € en especes : le reglement federe s'ecrit « Monnaie fédérée »,
        comme dans la liste des ventes.
        / A federated payment without a known currency is written "Monnaie
        fédérée", like in the sales list."""
        tarif_de_la_bouteille = creer_tarif_vendu(
            nom="Bouteille federee", prix_en_euros="10.00"
        )
        monnaie_inconnue = uuid_module.uuid4()
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            articles=[
                {
                    "pricesold": tarif_de_la_bouteille,
                    "quantite": Decimal("0.6"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("20"),
                    "total_catalogue_impose": 600,
                    "payment_method": PaymentMethod.STRIPE_FED,
                    "asset": monnaie_inconnue,
                    "status": LigneArticle.VALID,
                },
                {
                    "pricesold": tarif_de_la_bouteille,
                    "quantite": Decimal("0.4"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("20"),
                    "total_catalogue_impose": 400,
                    "payment_method": PaymentMethod.CASH,
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.STRIPE_FED,
                    "montant": 600,
                    "asset": monnaie_inconnue,
                },
                {"moyen": PaymentMethod.CASH, "montant": 400},
            ],
        )
        verifier_egalites(vente)

        ticket = self._ticket(vente)

        assert self._detail_par_nom(ticket) == {
            "Espèces": 400,
            "Monnaie fédérée": 600,
        }

    # ------------------------------------------------------------------
    # La re-impression : par l'uuid de la vente, DUPLICATA par vente
    # / Reprint: by the sale uuid, DUPLICATE per sale
    # ------------------------------------------------------------------

    def test_ticket_vente_numero_et_duplicata(self):
        """
        Une biere vendue, puis son ticket demande deux fois par la route
        `imprimer_ticket` avec l'uuid de la VENTE, et imprime par la vraie tache.
        Le journal a deux impressions de la vente (`uuid_transaction` = uuid de la
        vente) : la premiere est l'original, la deuxieme un DUPLICATA. Le premier
        ticket porte le numero de la vente.
        / A beer sold, its receipt requested twice with the SALE uuid and printed by
        the real task: two log rows for the sale, the second a DUPLICATE; the first
        receipt carries the sale number.
        """
        vente = self._vendre_une_biere_en_especes()
        imprimante_du_terminal = Printer.objects.create(
            name="Imprimante ticket client", printer_type=Printer.MOCK
        )

        with mock.patch(
            "laboutik.views.imprimante_du_terminal",
            return_value=imprimante_du_terminal,
        ):
            with taches_celery_enregistrees() as taches_demandees:
                for _numero_de_la_demande in range(2):
                    reponse = self.navigateur.post(
                        URL_DE_L_IMPRESSION_DU_TICKET,
                        data={"uuid_vente": str(vente.uuid)},
                    )
                    assert reponse.status_code == 200, reponse.content.decode()[:400]

        impressions_demandees = []
        for nom_de_la_tache, arguments in taches_demandees:
            if nom_de_la_tache == "imprimer_async":
                impressions_demandees.append(arguments)
        assert len(impressions_demandees) == 2, taches_demandees

        imprimante_simulee = ImprimanteSimulee()
        with mock.patch(
            "laboutik.printing.imprimer", side_effect=imprimante_simulee.imprimer
        ):
            for cle_de_l_imprimante, donnees_du_ticket, nom_du_schema in (
                impressions_demandees
            ):
                imprimer_async(cle_de_l_imprimante, donnees_du_ticket, nom_du_schema)

        impressions_de_la_vente = list(
            ImpressionLog.objects.filter(
                type_justificatif=ImpressionLog.VENTE
            ).order_by("datetime")
        )
        assert len(impressions_de_la_vente) == 2
        assert impressions_de_la_vente[0].uuid_transaction == vente.uuid
        assert impressions_de_la_vente[1].uuid_transaction == vente.uuid
        assert impressions_de_la_vente[0].is_duplicata is False
        assert impressions_de_la_vente[1].is_duplicata is True

        assert len(imprimante_simulee.tickets_recus) == 2
        assert imprimante_simulee.tickets_recus[0]["is_duplicata"] is False
        assert imprimante_simulee.tickets_recus[1]["is_duplicata"] is True
        assert re.search(
            rf"Vente n°\s*{vente.numero}\b",
            _texte_de_l_imprimante_escpos(imprimante_simulee.tickets_recus[0]),
        )

    def test_le_bouton_reimprimer_du_detail_envoie_l_uuid_de_la_vente(self):
        """Le bouton « Ré-imprimer » du detail d'une vente envoie l'uuid de la vente
        a la route d'impression.
        / The detail's "Reprint" button sends the sale uuid to the print route."""
        vente = self._vendre_une_biere_en_especes()

        reponse = self.navigateur.get(
            f"{DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE}{vente.uuid}/"
        )

        contenu = reponse.content.decode()
        assert reponse.status_code == 200, contenu[:400]
        boutons_reimprimer = attributs_des_elements(contenu, "btn-reimprimer")
        assert len(boutons_reimprimer) == 1, contenu[:2000]
        valeurs_envoyees = json.loads(boutons_reimprimer[0]["hx-vals"])
        assert valeurs_envoyees.get("uuid_vente") == str(vente.uuid), valeurs_envoyees

    def _imprimer_par_la_tache(self, impressions_demandees):
        """
        Imprime par la vraie tache les impressions demandees (imprimante simulee).
        Rend l'imprimante simulee (ses tickets recus).
        / Prints the requested prints through the real task (simulated printer).
        """
        imprimante_simulee = ImprimanteSimulee()
        with mock.patch(
            "laboutik.printing.imprimer", side_effect=imprimante_simulee.imprimer
        ):
            for cle_de_l_imprimante, donnees_du_ticket, nom_du_schema in (
                impressions_demandees
            ):
                imprimer_async(cle_de_l_imprimante, donnees_du_ticket, nom_du_schema)
        return imprimante_simulee

    def test_paiement_puis_imprimer_compte_le_duplicata_sur_la_vente(self):
        """
        Le vrai chemin : 2 vins payes en especes par la route de paiement, puis le
        bouton « Imprimer » de l'ecran de fin de paiement, deux fois. Le bouton
        envoie l'uuid de la VENTE ; le journal a deux impressions de cette vente, la
        deuxieme est un DUPLICATA.
        / Real path: payment, then the success screen's Print button twice: it sends
        the SALE uuid; the second print is a DUPLICATE of that sale.
        """
        donnees = self._donnees_de_paiement("espece", self.vin, 2, 500)
        reponse_du_paiement = self._poster("/laboutik/paiement/payer/", donnees)
        contenu_du_paiement = reponse_du_paiement.content.decode()
        assert reponse_du_paiement.status_code == 200, contenu_du_paiement[:400]
        ligne_du_vin = LigneArticle.objects.filter(
            pricesold__productsold__product=self.vin
        ).first()
        vente = ligne_du_vin.vente
        boutons_imprimer = attributs_des_elements(
            contenu_du_paiement, "btn-imprimer-ticket"
        )
        assert len(boutons_imprimer) == 1, contenu_du_paiement[:2000]
        valeurs_du_bouton = json.loads(boutons_imprimer[0]["hx-vals"])
        assert valeurs_du_bouton == {"uuid_vente": str(vente.uuid)}
        imprimante_du_terminal = Printer.objects.create(
            name="Imprimante fin de paiement", printer_type=Printer.MOCK
        )

        with mock.patch(
            "laboutik.views.imprimante_du_terminal",
            return_value=imprimante_du_terminal,
        ):
            with taches_celery_enregistrees() as taches_demandees:
                for _numero_de_la_demande in range(2):
                    reponse = self.navigateur.post(
                        URL_DE_L_IMPRESSION_DU_TICKET, data=valeurs_du_bouton
                    )
                    assert reponse.status_code == 200, reponse.content.decode()[:400]
        impressions_demandees = []
        for nom_de_la_tache, arguments in taches_demandees:
            if nom_de_la_tache == "imprimer_async":
                impressions_demandees.append(arguments)
        self._imprimer_par_la_tache(impressions_demandees)

        impressions_de_la_vente = list(
            ImpressionLog.objects.filter(uuid_transaction=vente.uuid).order_by(
                "datetime"
            )
        )
        assert len(impressions_de_la_vente) == 2
        assert impressions_de_la_vente[0].is_duplicata is False
        assert impressions_de_la_vente[1].is_duplicata is True

    def test_une_vente_en_ligne_ne_s_imprime_pas_a_la_caisse(self):
        """
        Un billet vendu en ligne (aucun point de vente) : la route d'impression
        refuse (« Donnees manquantes pour l'impression ») et ne demande aucune
        impression.
        / An online sale (no point of sale) is not printed at the register.
        """
        tarif_du_billet = creer_tarif_vendu(nom="Billet en ligne", prix_en_euros="10.00")
        vente_en_ligne = fabriquer_vente_encaissee(
            origine=SaleOrigin.LESPASS,
            articles=[
                {
                    "pricesold": tarif_du_billet,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.STRIPE_NOFED,
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": PaymentMethod.STRIPE_NOFED, "montant": 1000}],
        )
        imprimante_du_terminal = Printer.objects.create(
            name="Imprimante vente en ligne", printer_type=Printer.MOCK
        )

        with mock.patch(
            "laboutik.views.imprimante_du_terminal",
            return_value=imprimante_du_terminal,
        ):
            with taches_celery_enregistrees() as taches_demandees:
                reponse = self.navigateur.post(
                    URL_DE_L_IMPRESSION_DU_TICKET,
                    data={"uuid_vente": str(vente_en_ligne.uuid)},
                )

        assert reponse.status_code == 200
        assert "Donnees manquantes pour l'impression" in html.unescape(
            reponse.content.decode()
        )
        assert taches_demandees == []

    # ------------------------------------------------------------------
    # Le ticket : dates, noms, avoir, offert, pied
    # / The receipt: dates, names, credit note, offered, footer
    # ------------------------------------------------------------------

    def test_la_date_du_ticket_est_l_encaissement_dans_le_fuseau_du_lieu(self):
        """
        La vente est encaissee le 10/03/2026 a 20:45 UTC (21:45 a Paris, heure
        d'hiver), le ticket est imprime le 11/03/2026 a 09:00 UTC (10:00 a Paris).
        La date de l'en-tete est celle de l'ENCAISSEMENT, a l'heure de Paris :
        « 10/03/2026 21:45 ». Un DUPLICATA imprime en plus « Imprimé le
        11/03/2026 10:00 » ; un original non.
        Les deux instants sont poses par `patch` de `django.utils.timezone.now` :
        ils different d'un jour, une date lue sur l'heure d'impression se voit.
        / Settled on 10/03/2026 20:45 UTC, printed on 11/03/2026 09:00 UTC: the
        header is the settlement in Paris time; a duplicate adds the print date.
        """
        instant_de_l_encaissement = datetime(2026, 3, 10, 20, 45, tzinfo=dt_timezone.utc)
        instant_de_l_impression = datetime(2026, 3, 11, 9, 0, tzinfo=dt_timezone.utc)
        with mock.patch(
            "django.utils.timezone.now", return_value=instant_de_l_encaissement
        ):
            vente = self._vendre_une_biere_en_especes()

        with mock.patch(
            "django.utils.timezone.now", return_value=instant_de_l_impression
        ):
            ticket = self._ticket(vente)
        ticket_duplicata = dict(ticket)
        ticket_duplicata["is_duplicata"] = True

        assert ticket["header"]["date"] == "10/03/2026 21:45"
        assert "Imprimé le" not in _texte_de_l_imprimante_escpos(ticket)
        ligne_d_impression = "Imprimé le 11/03/2026 10:00"
        assert ligne_d_impression in _texte_de_l_imprimante_escpos(ticket_duplicata)
        assert ligne_d_impression in _textes_de_l_imprimante_sunmi(ticket_duplicata)

    def test_le_ticket_nomme_le_tarif_quand_il_differe_du_produit(self):
        """
        Un produit « Biere » a deux tarifs, « Pinte » (5,00 €) et « Demi »
        (3,00 €), vendus ensemble : deux articles, « Biere … Pinte » et
        « Biere … Demi ».
        / Two prices of one product: each item is named with its price name.
        """
        biere = Product.objects.create(
            name=f"Biere {uuid_module.uuid4().hex[:6]}", methode_caisse=Product.VENTE
        )
        tarifs_vendus = []
        for nom_du_tarif, prix in (("Pinte", Decimal("5.00")), ("Demi", Decimal("3.00"))):
            tarif = Price.objects.create(product=biere, name=nom_du_tarif, prix=prix)
            produit_vendu = ProductSold.objects.create(product=biere)
            tarif_vendu = PriceSold.objects.create(
                productsold=produit_vendu, price=tarif, prix=prix
            )
            tarifs_vendus.append(tarif_vendu)
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            articles=[
                {
                    "pricesold": tarifs_vendus[0],
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.CASH,
                    "status": LigneArticle.VALID,
                },
                {
                    "pricesold": tarifs_vendus[1],
                    "quantite": Decimal("1"),
                    "prix_unitaire": 300,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.CASH,
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 800}],
        )
        verifier_egalites(vente)

        ticket = self._ticket(vente)

        noms_des_articles = []
        for article in ticket["articles"]:
            noms_des_articles.append(article["name"])
        assert sorted(noms_des_articles) == [f"{biere.name} Demi", f"{biere.name} Pinte"]

    def test_le_ticket_d_un_billet_porte_l_evenement_et_sa_date(self):
        """
        Un billet d'un evenement du 12/10 vendu a la caisse : le nom imprime porte
        le nom de l'evenement et sa date (jour/mois, heure de Paris).
        / A ticket's printed name carries the event name and date.
        """
        tarif_du_billet = creer_tarif_vendu(
            nom="Entree", prix_en_euros="10.00", categorie_article=Product.BILLET
        )
        debut_de_l_evenement = timezone.now() + timedelta(days=8)
        with taches_celery_enregistrees():
            evenement = Event.objects.create(
                name=f"Concert ticket {uuid_module.uuid4().hex[:6]}",
                datetime=debut_de_l_evenement,
                end_datetime=debut_de_l_evenement + timedelta(hours=2),
                jauge_max=100,
            )
        tarif_du_billet.productsold.event = evenement
        tarif_du_billet.productsold.save()
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            articles=[
                {
                    "pricesold": tarif_du_billet,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1000,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.CASH,
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 1000}],
        )
        verifier_egalites(vente)
        date_attendue = debut_de_l_evenement.astimezone(
            ZoneInfo(FUSEAU_DU_LIEU)
        ).strftime("%d/%m")

        ticket = self._ticket(vente)

        nom_imprime = ticket["articles"][0]["name"]
        assert evenement.name in nom_imprime
        assert nom_imprime.endswith(date_attendue), nom_imprime

    def test_le_ticket_d_un_avoir_porte_avoir_et_son_montant_negatif(self):
        """
        Un retour de consigne a 1,00 € (vente AVOIR, rendu en especes) : l'en-tete
        dit « Avoir n° <numero> » ; l'article est imprime avec son montant negatif
        sur les deux imprimantes (« -1.00 »), et le TOTAL est -1.00.
        / A deposit return: "Avoir n°" header; the negative item is printed with its
        sign on both printers.
        """
        tarif_de_la_consigne = creer_tarif_vendu(nom="Consigne", prix_en_euros="1.00")
        vente_d_avoir = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.AVOIR,
            point_de_vente=self.point_de_vente,
            articles=[
                {
                    "pricesold": tarif_de_la_consigne,
                    "quantite": Decimal("-1"),
                    "prix_unitaire": 100,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.CASH,
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": -100}],
        )
        verifier_egalites(vente_d_avoir)

        ticket = self._ticket(vente_d_avoir)

        assert ticket["header"]["numero"] == f"Avoir n° {vente_d_avoir.numero}"
        assert "x-1  -1.00EUR" in _texte_de_l_imprimante_escpos(ticket)
        assert "TOTAL: -1.00 EUR" in _texte_de_l_imprimante_escpos(ticket)
        textes_sunmi = _textes_de_l_imprimante_sunmi(ticket)
        ligne_negative_sur_sunmi = False
        for texte_sunmi in textes_sunmi:
            if texte_sunmi.endswith("x-1  -1.00EUR"):
                ligne_negative_sur_sunmi = True
        assert ligne_negative_sur_sunmi, textes_sunmi

    def test_une_ligne_de_prix_negatif_s_imprime_avec_son_montant(self):
        """
        Une ligne de prix negatif (un moyen dont les remboursements depassent les
        ventes, sur un ticket X ou Z : -4,00 €) s'imprime avec son montant et son
        signe, pas comme une ligne de commande cuisine.
        / A negative-price line prints its signed amount on both printers.
        """
        ticket = {
            "header": {"title": "", "subtitle": "", "date": ""},
            "articles": [
                {"name": "Especes", "qty": 1, "price": -400, "total": -400},
            ],
            "total": {"amount": -400, "label": ""},
            "qrcode": None,
            "footer": [],
        }

        assert "Especes x1  -4.00EUR" in _texte_de_l_imprimante_escpos(ticket)
        assert "Especes x1  -4.00EUR" in _textes_de_l_imprimante_sunmi(ticket)

    def test_la_sunmi_interne_imprime_duplicata_et_un_total_a_zero(self):
        """
        Une pinte entierement offerte (TOTAL 0), re-imprimee (DUPLICATA) : la Sunmi
        interne imprime « *** DUPLICATA *** » et « TOTAL: 0.00 EUR ».
        / Sunmi built-in printer: DUPLICATE mention and a zero TOTAL.
        """
        tarif_de_la_pinte = creer_tarif_vendu(nom="Pinte", prix_en_euros="5.00")
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            articles=[
                {
                    "pricesold": tarif_de_la_pinte,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                    "offert_en_totalite": True,
                    "status": LigneArticle.VALID,
                },
            ],
        )
        verifier_egalites(vente)
        ticket = self._ticket(vente)
        ticket["is_duplicata"] = True

        textes_sunmi = _textes_de_l_imprimante_sunmi(ticket)

        assert "*** DUPLICATA ***" in textes_sunmi
        assert "TOTAL: 0.00 EUR" in textes_sunmi

    def test_l_offert_n_entre_pas_dans_le_detail_des_reglements(self):
        """
        Un jus a 3,50 € paye en especes et une pinte a 5,00 € offerte : le detail
        des reglements est exactement [Espèces 350] (pas de règlement « Offert ») ;
        aucune ligne ESC/POS « Offert  <montant> » (forme du detail) ; la ligne
        d'article « Offert: 5.00EUR » est bien la.
        / The offered part never enters the payments detail; it is printed under
        the item.
        """
        vente = self._vendre_un_jus_en_especes_et_offrir_une_pinte()

        ticket = self._ticket(vente)

        assert ticket["cascade_detail"] == [{"name": "Espèces", "total": 350}]
        lignes_imprimees = _texte_de_l_imprimante_escpos(ticket).splitlines()
        ligne_d_article_offert_imprimee = False
        for ligne_imprimee in lignes_imprimees:
            assert "Offert  " not in ligne_imprimee, ligne_imprimee
            if ligne_imprimee.endswith("  Offert: 5.00EUR"):
                ligne_d_article_offert_imprimee = True
        assert ligne_d_article_offert_imprimee, lignes_imprimees

    def test_le_pied_garde_les_lignes_vides_du_lieu(self):
        """
        Un pied de ticket « Merci ! », ligne vide, « A bientot » : la ligne vide
        voulue par le lieu est gardee.
        / The venue's blank footer line is kept.
        """
        configuration_de_la_caisse = LaboutikConfiguration.get_solo()
        configuration_de_la_caisse.pied_ticket = "Merci !\n\nA bientot"
        configuration_de_la_caisse.save()
        vente = self._vendre_une_biere_en_especes()

        ticket = self._ticket(vente)

        assert ticket["footer"][:3] == ["Merci !", "", "A bientot"]

    # ------------------------------------------------------------------
    # Les moteurs d'impression / The print engines
    # ------------------------------------------------------------------

    def test_l_imprimante_escpos_imprime_le_detail_des_moyens(self):
        """Paiement a trois moyens : chaque moyen est imprime avec son montant.
        / Three methods: each method is printed with its amount."""
        vente = self._payer_trois_vins_carte_puis_especes()
        ticket = self._ticket(vente)

        texte = _texte_de_l_imprimante_escpos(ticket)

        assert f"{NOM_MONNAIE_CADEAU}  6.00EUR" in texte
        assert f"{NOM_MONNAIE_LOCALE}  4.00EUR" in texte
        assert "Espèces  5.00EUR" in texte

    def test_l_imprimante_escpos_n_imprime_pas_le_detail_d_un_seul_moyen(self):
        """2 vins payes en especes, un seul moyen : pas de bloc de detail.
        / A single-method receipt prints no detail block."""
        vente = self._payer_deux_vins_en_especes()
        ticket = self._ticket(vente)

        texte = _texte_de_l_imprimante_escpos(ticket)

        assert "Espèces" not in texte

    def test_l_imprimante_sunmi_interne_imprime_le_detail_des_moyens(self):
        """Meme regle pour l'imprimante interne Sunmi.
        / Same rule for the Sunmi built-in printer."""
        vente = self._payer_trois_vins_carte_puis_especes()
        ticket = self._ticket(vente)

        textes = _textes_de_l_imprimante_sunmi(ticket)

        especes_imprimees = False
        cadeau_imprime = False
        for texte in textes:
            if "Espèces" in texte and "5.00" in texte:
                especes_imprimees = True
            if NOM_MONNAIE_CADEAU in texte:
                cadeau_imprime = True
        assert especes_imprimees, textes
        assert cadeau_imprime, textes
