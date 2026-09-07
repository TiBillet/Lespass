"""
tests/pytest/test_pos_retour_consigne.py — Le retour de consigne au point de vente V2.
/ Deposit return at the V2 point of sale.

LOCALISATION : tests/pytest/test_pos_retour_consigne.py

POURQUOI CE FICHIER / WHY THIS FILE :
Un retour de consigne rend de l'argent au client. C'est la seule operation du comptoir
qui va dans ce sens, et c'est ce qui la rend fragile : tout le reste du code de vente
suppose qu'un panier coute quelque chose.

Trois choses doivent etre vraies, et chacune a son test :
 1. La ligne comptable garde un montant NEGATIF. C'est ce signe, et rien d'autre, qui
    fait que le retour se soustrait du chiffre d'affaires et du tiroir-caisse dans tous
    les rapports (`reports.py` somme `amount x qty` sans valeur absolue).
 2. En cashless, un retour de consigne est une RECHARGE : on credite la carte du montant
    absolu. Un debit negatif ne veut rien dire pour la cascade multi-asset.
 3. On ne rembourse une consigne qu'en especes ou en cashless. Ni carte bancaire, ni
    cheque : on ne rend pas de la monnaie sur un terminal de paiement.

Le lieu de la verite est `Product.methode_caisse == Product.RETOUR_CONSIGNE`, comme en
V1 (`LaBoutik/webview/views.py`, `methode_CR`).

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_pos_retour_consigne.py -v
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import uuid as uuid_module
from decimal import Decimal

from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import (
    CategorieProduct,
    Configuration,
    LigneArticle,
    Price,
    Product,
)
from QrcodeCashless.models import CarteCashless
from fedow_connect.models import FedowConfig
from fedow_core.models import Asset, Token
from fedow_core.services import AssetService
from laboutik.models import PointDeVente


# Le prix d'un retour de consigne, en euros. NEGATIF : le lieu rend cet argent.
# Meme montant que l'article « Retour Consigne » de la V1
# (`LaBoutik/administration/management/commands/install.py`).
# / A deposit return price, in euros. NEGATIVE: the venue gives this money back.
PRIX_RETOUR_CONSIGNE_EUROS = Decimal("-1.00")

# Le prix de l'article de vente ordinaire, pour les paniers melanges.
# / Price of the ordinary sale article, used for mixed-cart tests.
PRIX_BIERE_EUROS = Decimal("3.00")


class TestPosRetourConsigne(FastTenantTestCase):
    """
    Une classe FastTenantTestCase = un schema cree en setUpClass.
    Chaque methode est isolee par rollback, y compris les ecritures dans le schema
    public (`Wallet`, `Asset`, `Token` vivent en SHARED_APPS mais partagent la
    connexion, donc le rollback les couvre).
    / One FastTenantTestCase class = one schema; each method is rolled back,
      SHARED_APPS writes included (same connection).
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_pos_retour_consigne"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-pos-retour-consigne.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = "Test POS Retour Consigne"

    def setUp(self):
        # Re-poser le search_path apres le rollback du test precedent.
        # / Re-set search_path after the previous test's rollback.
        connection.set_tenant(self.tenant)

        # --- Le lieu : caisse V2 active ---
        # `module_caisse` exige `module_monnaie_locale` : on active les deux.
        # / V2 POS enabled (module_caisse requires module_monnaie_locale).
        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.save()

        # --- Le lieu est branche a Fedow ---
        # `can_fedow()` est vrai des que les trois champs sont remplis
        # (`fedow_connect/models.py`).
        # / The venue is Fedow-connected: can_fedow() is true once the three fields are set.
        config_fedow = FedowConfig.get_solo()
        config_fedow.fedow_place_uuid = uuid_module.uuid4()
        config_fedow.fedow_place_admin_apikey = "cle-de-test-jamais-dechiffree"
        config_fedow.fedow_place_wallet_uuid = uuid_module.uuid4()
        config_fedow.save()

        # --- La monnaie locale du lieu ---
        # C'est elle qu'un retour de consigne credite quand le client presente sa carte.
        # / The venue's local currency: what a deposit return credits on the card.
        self.wallet_lieu = Wallet.objects.create(
            origin=self.tenant, name="Wallet lieu test consigne"
        )
        self.asset_tlf = AssetService.creer_asset(
            tenant=self.tenant,
            name="Monnaie locale test consigne",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=self.wallet_lieu,
        )

        self.categorie = CategorieProduct.objects.create(name="Consignes test")

        # --- L'article « Retour Consigne » ---
        # Prix NEGATIF et `methode_caisse=RETOUR_CONSIGNE` : les deux vont ensemble.
        # L'asset porte la monnaie a crediter en cashless — il se pose sur le PRODUIT,
        # jamais sur le prix : `_extraire_articles_du_panier` ne retient que les Price
        # dont l'asset est nul, un prix porteur d'asset serait ignore en silence.
        # / NEGATIVE price + methode_caisse=RETOUR_CONSIGNE. The asset (currency to
        #   credit) belongs to the PRODUCT: a Price carrying an asset is silently skipped.
        self.produit_retour_consigne = Product.objects.create(
            name="Retour Consigne",
            categorie_article=Product.VENTE,
            methode_caisse=Product.RETOUR_CONSIGNE,
            categorie_pos=self.categorie,
            asset=self.asset_tlf,
            publish=True,
        )
        self.prix_retour_consigne = Price.objects.create(
            product=self.produit_retour_consigne,
            name="Gobelet",
            prix=PRIX_RETOUR_CONSIGNE_EUROS,
            publish=True,
        )

        # --- Un article de vente ordinaire, pour les paniers melanges ---
        # / An ordinary sale article, for mixed-cart tests.
        self.produit_biere = Product.objects.create(
            name="Biere test consigne",
            categorie_article=Product.VENTE,
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
            publish=True,
        )
        self.prix_biere = Price.objects.create(
            product=self.produit_biere,
            name="Pinte",
            prix=PRIX_BIERE_EUROS,
            publish=True,
        )

        # --- Le point de vente, qui accepte TOUT ---
        # C'est volontaire : si le PV refusait deja la carte bancaire, le test du refus
        # ne prouverait rien. On veut que le refus vienne de la regle « consigne », pas
        # de la configuration du comptoir.
        # / The POS accepts EVERY method on purpose: otherwise the refusal tests would
        #   pass for the wrong reason.
        self.point_de_vente = PointDeVente.objects.create(
            name="Comptoir consignes",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            accepte_cheque=True,
        )
        self.point_de_vente.products.add(self.produit_retour_consigne)
        self.point_de_vente.products.add(self.produit_biere)

        # --- La carte NFC du client, anonyme et vide ---
        # Elle porte un wallet ephemere : `_obtenir_ou_creer_wallet` le rend directement,
        # sans jamais interroger Fedow. C'est ce qui permet a ces tests de se passer de
        # tout mock reseau — le credit lui-meme est une ecriture DB locale.
        # / The customer's anonymous NFC card, carrying an ephemeral wallet: the wallet
        #   resolver returns it without any Fedow call, so these tests need no network mock.
        self.wallet_carte = Wallet.objects.create(
            origin=self.tenant, name="Wallet carte test consigne"
        )
        self.carte_client = CarteCashless.objects.create(
            tag_id="CONSIGN1",
            number="CONSIGN1",
            uuid=uuid_module.uuid4(),
            wallet_ephemere=self.wallet_carte,
        )

        # --- Le caissier ---
        # Admin du tenant, session navigateur (contourne la carte primaire).
        # / The cashier: tenant admin with a browser session.
        self.caissier, _cree = TibilletUser.objects.get_or_create(
            email="caissier-retour-consigne@tibillet.localhost",
            defaults={
                "username": "caissier-retour-consigne@tibillet.localhost",
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

    def _cle_panier(self, produit, prix):
        """La cle de formulaire d'un article du panier.
        / The cart form key of one article."""
        return f"repid-{produit.uuid}--{prix.uuid}"

    def _donnees_de_base(self, moyen_paiement):
        """Le socle commun d'un POST de paiement.
        / The common base of a payment POST."""
        return {
            "uuid_pv": str(self.point_de_vente.uuid),
            "moyen_paiement": moyen_paiement,
            "given_sum": "",
        }

    def _poster_retour_consigne(self, moyen_paiement="espece", quantite=1):
        """
        Joue le geste du caissier : un retour de consigne au panier, et on paie.
        / Plays the cashier's gesture: one deposit return in the cart, then pay.
        """
        prix_en_centimes = int(round(self.prix_retour_consigne.prix * 100)) * quantite
        donnees = self._donnees_de_base(moyen_paiement)
        donnees["total"] = str(prix_en_centimes)
        donnees[self._cle_panier(self.produit_retour_consigne, self.prix_retour_consigne)] = str(quantite)
        return self.client_http.post("/laboutik/paiement/payer/", data=donnees)

    def _poster_retour_consigne_en_nfc(self, quantite=1):
        """
        Le client presente sa carte : le retour doit la CREDITER.
        / The customer taps their card: the return must CREDIT it.
        """
        prix_en_centimes = int(round(self.prix_retour_consigne.prix * 100)) * quantite
        donnees = self._donnees_de_base("nfc")
        donnees["total"] = str(prix_en_centimes)
        donnees["tag_id"] = self.carte_client.tag_id
        donnees[self._cle_panier(self.produit_retour_consigne, self.prix_retour_consigne)] = str(quantite)
        return self.client_http.post("/laboutik/paiement/payer/", data=donnees)

    def _solde_de_la_carte(self, asset=None):
        """
        Le solde porte par la carte pour un asset donne, en centimes.
        / The card's balance for a given asset, in cents.
        """
        asset_lu = asset or self.asset_tlf
        token = Token.objects.filter(wallet=self.wallet_carte, asset=asset_lu).first()
        return int(token.value) if token else 0

    def _poster_panier_melange(self, moyen_paiement="espece"):
        """
        Un panier qui melange une biere et un retour de consigne.
        / A cart mixing a beer and a deposit return.
        """
        total_centimes = int(round((self.prix_biere.prix + self.prix_retour_consigne.prix) * 100))
        donnees = self._donnees_de_base(moyen_paiement)
        donnees["total"] = str(total_centimes)
        donnees[self._cle_panier(self.produit_biere, self.prix_biere)] = "1"
        donnees[self._cle_panier(self.produit_retour_consigne, self.prix_retour_consigne)] = "1"
        return self.client_http.post("/laboutik/paiement/payer/", data=donnees)

    def _demander_les_moyens_de_paiement(self, avec_retour_consigne=True):
        """
        Joue l'ecran « comment payez-vous ? » et rend les moyens proposes.
        / Plays the "how do you pay?" screen and returns the offered methods.
        """
        donnees = {"uuid_pv": str(self.point_de_vente.uuid)}
        if avec_retour_consigne:
            donnees[self._cle_panier(self.produit_retour_consigne, self.prix_retour_consigne)] = "1"
            donnees["total"] = str(int(round(self.prix_retour_consigne.prix * 100)))
        else:
            donnees[self._cle_panier(self.produit_biere, self.prix_biere)] = "1"
            donnees["total"] = str(int(round(self.prix_biere.prix * 100)))
        reponse = self.client_http.post(
            "/laboutik/paiement/moyens_paiement/", data=donnees
        )
        return reponse

    # ------------------------------------------------------------------ #
    #  T1 — Les moyens proposes
    # ------------------------------------------------------------------ #

    def test_les_moyens_dun_retour_de_consigne_excluent_la_carte_et_le_cheque(self):
        """
        Au comptoir, on ne rembourse une consigne qu'en especes ou sur la carte.

        Le point de vente de ce test accepte pourtant la carte bancaire ET le cheque :
        si l'un des deux apparait, c'est que la regle « consigne » n'existe pas.
        / The POS accepts card and check: if either shows up, the deposit rule is absent.
        """
        reponse = self._demander_les_moyens_de_paiement(avec_retour_consigne=True)

        self.assertEqual(reponse.status_code, 200)
        moyens_proposes = reponse.context["moyens_paiement"]

        self.assertIn("espece", moyens_proposes, "Les especes doivent rester proposees.")
        self.assertIn("nfc", moyens_proposes, "Le cashless doit rester propose.")
        self.assertNotIn(
            "carte_bancaire",
            moyens_proposes,
            "On ne rembourse pas une consigne sur un terminal de paiement.",
        )
        self.assertNotIn(
            "CH",
            moyens_proposes,
            "On ne rembourse pas une consigne par cheque.",
        )

    def test_un_comptoir_sans_especes_naffiche_pas_le_bouton_especes(self):
        """
        Le bouton affiché doit suivre les moyens réellement disponibles.

        On teste ici le HTML rendu, pas seulement le contexte : en mode consigne le
        gabarit affichait le bouton ESPÈCE sans condition, alors qu'il conditionne
        bien le bouton CASHLESS. Un comptoir qui refuse les espèces montrait donc un
        bouton menant à un paiement que le serveur refuse.
        / We assert on the rendered HTML, not just the context: the deposit branch of
          the template showed the CASH button unconditionally.
        """
        self.point_de_vente.accepte_especes = False
        self.point_de_vente.save()

        reponse = self._demander_les_moyens_de_paiement(avec_retour_consigne=True)

        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn("espece", reponse.context["moyens_paiement"])
        self.assertNotContains(
            reponse,
            "deposit-btn-especes",
            msg_prefix=(
                "Le comptoir refuse les especes : le bouton ne doit pas etre affiche."
            ),
        )

    def test_le_cashless_nest_pas_propose_si_le_produit_na_pas_de_monnaie(self):
        """
        Un bouton qui mène à un refus certain ne doit pas s'afficher.

        Sans `Product.asset`, le crédit est impossible et `payer()` refuse. Proposer
        CASHLESS quand même fait scanner sa carte au client pour rien : le caissier
        découvre le problème après le geste, devant lui.
        / A button leading to a certain refusal must not be shown: without an asset the
          credit is impossible, and the customer taps their card for nothing.
        """
        self.produit_retour_consigne.asset = None
        self.produit_retour_consigne.save()

        reponse = self._demander_les_moyens_de_paiement(avec_retour_consigne=True)

        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn(
            "nfc",
            reponse.context["moyens_paiement"],
            "Sans monnaie a crediter, le cashless ne doit pas etre propose.",
        )
        self.assertNotContains(reponse, "deposit-btn-cashless")
        # Les especes restent possibles : elles ne dependent d'aucun asset.
        # / Cash stays available: it depends on no asset.
        self.assertIn("espece", reponse.context["moyens_paiement"])
        self.assertContains(reponse, "deposit-btn-especes")

    def test_le_cashless_nest_pas_propose_si_la_monnaie_est_un_cadeau(self):
        """
        Même règle pour un asset cadeau : le refus est certain, le bouton ment.
        / Same rule for a gift asset: the refusal is certain, so the button lies.
        """
        asset_cadeau = AssetService.creer_asset(
            tenant=self.tenant,
            name="Cadeau test moyens consigne",
            category=Asset.TNF,
            currency_code="EUR",
            wallet_origin=self.wallet_lieu,
        )
        self.produit_retour_consigne.asset = asset_cadeau
        self.produit_retour_consigne.save()

        reponse = self._demander_les_moyens_de_paiement(avec_retour_consigne=True)

        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn("nfc", reponse.context["moyens_paiement"])
        self.assertNotContains(reponse, "deposit-btn-cashless")

    def test_le_cashless_est_propose_quand_la_monnaie_est_correcte(self):
        """
        Le garde-fou des deux tests précédents : sans lui, ils passeraient même si le
        bouton CASHLESS avait disparu pour tout le monde.
        / Guard for the two previous tests: without it they would pass even if the
          CASHLESS button had vanished for everyone.
        """
        reponse = self._demander_les_moyens_de_paiement(avec_retour_consigne=True)

        self.assertEqual(reponse.status_code, 200)
        self.assertIn("nfc", reponse.context["moyens_paiement"])
        self.assertContains(reponse, "deposit-btn-cashless")

    def test_un_panier_melange_naffiche_pas_lecran_de_remboursement(self):
        """
        L'écran de paiement ne doit pas annoncer un remboursement quand le client doit payer.

        Le mode consigne passe le total en valeur absolue et bascule les libellés sur
        « Rembourser la consigne par : ». Sur un panier qui mélange une bière à 3 € et
        un retour à −1 €, le total vaut 2 € et l'écran annoncerait « rembourser 2 € »
        alors que le client **doit** 2 €. Le POST est déjà refusé, mais le caissier voit
        cet écran **avant** de poster : il n'a aucune raison de lire l'inverse de la
        vérité.
        / The payment screen must not announce a refund when the customer owes money.
          The POST is already refused, but the cashier sees this screen first.
        """
        donnees = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "total": str(int(round((self.prix_biere.prix + self.prix_retour_consigne.prix) * 100))),
            self._cle_panier(self.produit_biere, self.prix_biere): "1",
            self._cle_panier(self.produit_retour_consigne, self.prix_retour_consigne): "1",
        }
        reponse = self.client_http.post(
            "/laboutik/paiement/moyens_paiement/", data=donnees
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(
            reponse.context["deposit_is_present"],
            "Un panier melange n'est pas un remboursement de consigne.",
        )
        self.assertNotContains(reponse, "deposit-btn-especes")

    def test_un_panier_ordinaire_garde_tous_ses_moyens_de_paiement(self):
        """
        Le garde-fou du test precedent : sans retour de consigne, rien ne change.

        Sans ce test, une regression qui supprimerait la carte bancaire PARTOUT
        passerait inapercue — le test T1 serait vert pour la mauvaise raison.
        / Guard for the previous test: a regression removing card payment EVERYWHERE
          would otherwise make T1 pass for the wrong reason.
        """
        reponse = self._demander_les_moyens_de_paiement(avec_retour_consigne=False)

        self.assertEqual(reponse.status_code, 200)
        moyens_proposes = reponse.context["moyens_paiement"]

        self.assertIn("carte_bancaire", moyens_proposes)
        self.assertIn("CH", moyens_proposes)

    # ------------------------------------------------------------------ #
    #  T2 — Les refus cote serveur
    # ------------------------------------------------------------------ #

    def test_un_retour_de_consigne_paye_par_carte_bancaire_est_refuse(self):
        """
        Le filtrage des boutons est un confort d'affichage ; la garde est ici.

        `payer()` ne confronte jamais le moyen recu a la liste des moyens proposes :
        un POST forge passerait donc outre. On verifie le refus ET l'absence
        d'ecriture — un refus qui laisse une ligne en base ne serait pas un refus.
        / Button filtering is cosmetic; this is the real guard. We check both the
          refusal AND that nothing was written.
        """
        reponse = self._poster_retour_consigne(moyen_paiement="carte_bancaire")

        self.assertContains(reponse, "en espèces ou sur la carte", status_code=400)
        self.assertEqual(
            LigneArticle.objects.count(),
            0,
            "Un paiement refuse ne doit laisser aucune ligne comptable.",
        )

    def test_un_retour_de_consigne_paye_par_cheque_est_refuse(self):
        """
        Meme regle pour le cheque : on ne fait pas un cheque pour rendre 1 euro.
        / Same rule for checks.
        """
        reponse = self._poster_retour_consigne(moyen_paiement="CH")

        self.assertContains(reponse, "en espèces ou sur la carte", status_code=400)
        self.assertEqual(LigneArticle.objects.count(), 0)

    def test_un_panier_qui_melange_vente_et_retour_de_consigne_est_refuse(self):
        """
        Un panier melange rend l'ecran de paiement faux, pas seulement inelegant.

        `payer()` passe le total en valeur absolue des qu'une consigne est presente.
        Sur un panier a 3,00 - 1,00 = 2,00 euros, l'ecran afficherait « A rembourser :
        2,00 » alors que le client DOIT 2,00 euros. La valeur absolue n'a de sens que
        sur un panier entierement negatif : on refuse donc le melange.
        / A mixed cart makes the payment screen lie: abs() only makes sense on a
          wholly negative cart.
        """
        reponse = self._poster_panier_melange(moyen_paiement="espece")

        self.assertContains(reponse, "sans autre article", status_code=400)
        self.assertEqual(LigneArticle.objects.count(), 0)

    def test_un_retour_de_consigne_ne_peut_pas_se_regler_via_une_commande(self):
        """
        Le paiement d'une commande de table est un second chemin, et il doit refuser aussi.

        `payer_commande` construit son propre panier depuis la commande et appelle
        directement les flux de paiement : les gardes de `payer()` ne s'y appliquent
        pas. En NFC, la cascade de débit s'arrête sans rien écrire sur un montant
        négatif et affiche pourtant un succès ; en carte ou en chèque, elle écrirait une
        ligne négative sous un moyen par lequel on ne rembourse pas.
        / Paying a table order is a second path that bypasses payer()'s guards: in NFC
          the debit cascade writes nothing yet reports success.
        """
        from laboutik.models import ArticleCommandeSauvegarde, CommandeSauvegarde

        commande = CommandeSauvegarde.objects.create(
            statut=CommandeSauvegarde.OPEN,
            responsable=self.caissier,
        )
        ArticleCommandeSauvegarde.objects.create(
            commande=commande,
            product=self.produit_retour_consigne,
            price=self.prix_retour_consigne,
            qty=1,
            statut=ArticleCommandeSauvegarde.EN_ATTENTE,
        )

        reponse = self.client_http.post(
            f"/laboutik/commande/payer/{commande.uuid}/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                "moyen_paiement": "nfc",
                "tag_id": self.carte_client.tag_id,
                "given_sum": "",
            },
        )

        self.assertEqual(reponse.status_code, 400)
        self.assertContains(
            reponse,
            "au comptoir",
            status_code=400,
            msg_prefix="Le refus doit expliquer ou se regle un retour de consigne.",
        )
        self.assertEqual(LigneArticle.objects.count(), 0)
        self.assertEqual(self._solde_de_la_carte(), 0)

    # ------------------------------------------------------------------ #
    #  T3 — Les especes
    # ------------------------------------------------------------------ #

    def test_un_retour_de_consigne_en_especes_cree_une_ligne_negative(self):
        """
        Le signe du montant est le coeur du sujet.

        C'est lui, et rien d'autre, qui fait que le retour se soustrait du chiffre
        d'affaires et du tiroir-caisse : `reports.py` somme `amount x qty` sans valeur
        absolue. Une ligne positive ferait apparaitre le remboursement comme une
        recette.
        / The sign IS the subject: reports sum amount x qty with no abs().
        """
        reponse = self._poster_retour_consigne(moyen_paiement="espece")

        self.assertEqual(reponse.status_code, 200)

        lignes = LigneArticle.objects.all()
        self.assertEqual(lignes.count(), 1)

        ligne = lignes.first()
        self.assertEqual(
            ligne.amount,
            -100,
            "Le montant doit rester negatif : le lieu rend cet argent.",
        )
        self.assertEqual(ligne.payment_method, "CA")

    # ------------------------------------------------------------------ #
    #  T6 — L'inaltérabilité LNE tolère un montant négatif
    # ------------------------------------------------------------------ #

    def test_la_chaine_dintegrite_lne_accepte_une_ligne_negative(self):
        """
        La chaîne d'inaltérabilité doit valider une ligne de montant négatif.

        Le retour de consigne introduit dans la comptabilité quelque chose que la caisse
        ne produisait pas jusqu'ici : une `LigneArticle` à montant négatif. Le HMAC
        sérialise ce montant et `calculer_total_ht` le divise par le taux de TVA. Si
        l'un des deux traitait le signe de travers, la chaîne d'intégrité serait déclarée
        rompue — et une caisse dont la chaîne est rompue est une caisse non conforme.

        On ne le suppose pas : on chaîne une ligne de retour réelle et on demande à
        `verifier_chaine` de se prononcer.
        / Deposit returns introduce something new in the accounting chain: a negative
          LigneArticle. A broken chain means a non-compliant register, so we ask
          verifier_chaine rather than assume.
        """
        from laboutik.integrity import verifier_chaine
        from laboutik.models import LaboutikConfiguration

        self._poster_retour_consigne(moyen_paiement="espece")

        ligne = LigneArticle.objects.get()
        self.assertLess(ligne.amount, 0, "Le test n'a de sens que sur une ligne negative.")

        # On verifie la chaine TELLE QUE LE POS L'A PRODUITE. Recalculer nous-memes le
        # HMAC avant de le verifier comparerait `calculer_hmac` a elle-meme : le test
        # serait vert quel que soit le montant, et il effacerait au passage le chainage
        # reel pose par `_creer_lignes_articles`.
        # / We verify the chain AS THE POS PRODUCED IT: recomputing the HMAC here would
        #   compare calculer_hmac to itself and erase the real chaining.
        self.assertTrue(ligne.hmac_hash, "Le POS doit avoir chaine la ligne.")

        cle_hmac = LaboutikConfiguration.get_solo().get_or_create_hmac_key()
        est_valide, erreurs, _corrections = verifier_chaine(
            LigneArticle.objects.filter(pk=ligne.pk), cle_hmac
        )

        self.assertTrue(
            est_valide,
            f"La chaine LNE doit rester valide sur un montant negatif. Erreurs : {erreurs}",
        )
        self.assertEqual(erreurs, [])

        # Le total HT suit le signe du TTC : un remboursement est negatif de bout en
        # bout, sinon l'ecriture comptable derivee serait fausse.
        # / The HT total follows the TTC sign: a refund is negative all the way through.
        self.assertLess(
            ligne.total_ht,
            0,
            "Le total HT d'un remboursement doit rester negatif.",
        )

    def test_la_chaine_lne_reste_coherente_avec_une_tva_sur_le_retour(self):
        """
        Le même contrôle, mais avec un taux de TVA réel sur le produit.

        Sans taux, `calculer_total_ht` renvoie le montant tel quel et la division par
        `(1 + taux/100)` n'est jamais exercée. C'est pourtant là qu'une erreur de signe
        se logerait : sur un montant négatif, la division doit conserver le signe.
        / Without a rate, the division in calculer_total_ht is never exercised — yet
          that is exactly where a sign error would hide.
        """
        from laboutik.integrity import verifier_chaine
        from laboutik.models import LaboutikConfiguration
        from BaseBillet.models import Tva

        taux_vingt, _cree = Tva.objects.get_or_create(tva_rate=Decimal("20.00"))
        self.produit_retour_consigne.tva = taux_vingt
        self.produit_retour_consigne.save()

        self._poster_retour_consigne(moyen_paiement="espece")

        ligne = LigneArticle.objects.get()
        self.assertEqual(ligne.amount, -100)

        cle_hmac = LaboutikConfiguration.get_solo().get_or_create_hmac_key()
        est_valide, erreurs, _corrections = verifier_chaine(
            LigneArticle.objects.filter(pk=ligne.pk), cle_hmac
        )

        self.assertTrue(est_valide, f"Chaine LNE invalide : {erreurs}")
        # -100 TTC a 20 % => -83 HT (arrondi au centime).
        # / -100 TTC at 20% => -83 HT (rounded to the cent).
        self.assertEqual(ligne.total_ht, -83)

    # ------------------------------------------------------------------ #
    #  T5 — Le stock ne bouge pas
    # ------------------------------------------------------------------ #

    def test_un_retour_de_consigne_ne_decremente_pas_le_stock(self):
        """
        Le gobelet REVIENT : décrémenter le stock à ce moment-là serait à l'envers.

        `StockService.decrementer_pour_vente` le dit lui-même : « ici on décrémente
        toujours ». Sans exception pour les retours, rendre un gobelet retirerait un
        gobelet de l'inventaire — l'inverse de ce qui se passe sur le comptoir.
        / The cup COMES BACK: decrementing here would be backwards.
        """
        from inventaire.models import Stock

        stock = Stock.objects.create(
            product=self.produit_retour_consigne,
            quantite=10,
            autoriser_vente_hors_stock=True,
        )

        reponse = self._poster_retour_consigne(moyen_paiement="espece")

        self.assertEqual(reponse.status_code, 200)
        stock.refresh_from_db()
        self.assertEqual(
            stock.quantite,
            10,
            "Un gobelet rendu ne retire rien de l'inventaire.",
        )

    def test_une_vente_ordinaire_reste_bloquee_par_un_stock_insuffisant(self):
        """
        Le garde-fou de l'exclusion de stock : elle ne vaut QUE pour les retours.

        `_valider_stock_panier` et la décrémentation ignorent désormais les articles
        `RETOUR_CONSIGNE`. Si cette exclusion débordait sur les ventes ordinaires, on
        vendrait sans limite un stock épuisé — et personne ne s'en apercevrait avant
        l'inventaire.
        / Guard for the stock exclusion: it must apply ONLY to returns, never to
          ordinary sales, which must stay blocked when stock runs out.
        """
        from inventaire.models import Stock

        Stock.objects.create(
            product=self.produit_biere,
            quantite=0,
            autoriser_vente_hors_stock=False,
        )

        prix_en_centimes = int(round(self.prix_biere.prix * 100))
        donnees = self._donnees_de_base("espece")
        donnees["total"] = str(prix_en_centimes)
        donnees[self._cle_panier(self.produit_biere, self.prix_biere)] = "1"
        reponse = self.client_http.post("/laboutik/paiement/payer/", data=donnees)

        self.assertEqual(
            reponse.status_code,
            400,
            "Une vente ordinaire doit rester bloquee par un stock epuise.",
        )
        self.assertEqual(LigneArticle.objects.count(), 0)

    def test_une_vente_ordinaire_decremente_toujours_son_stock(self):
        """
        Le second garde-fou : la décrémentation normale ne doit pas avoir disparu.
        / Second guard: ordinary decrementing must still happen.
        """
        from inventaire.models import Stock

        stock = Stock.objects.create(
            product=self.produit_biere,
            quantite=10,
            autoriser_vente_hors_stock=True,
        )

        prix_en_centimes = int(round(self.prix_biere.prix * 100))
        donnees = self._donnees_de_base("espece")
        donnees["total"] = str(prix_en_centimes)
        donnees[self._cle_panier(self.produit_biere, self.prix_biere)] = "1"
        reponse = self.client_http.post("/laboutik/paiement/payer/", data=donnees)

        self.assertEqual(reponse.status_code, 200)
        stock.refresh_from_db()
        self.assertEqual(
            stock.quantite,
            9,
            "Une vente ordinaire doit toujours decrementer le stock.",
        )

    def test_un_retour_de_consigne_reste_possible_a_stock_zero(self):
        """
        Un stock épuisé ne doit pas empêcher un client de récupérer sa consigne.

        `_valider_stock_panier` bloque toute vente d'un produit à stock insuffisant
        quand la vente hors stock est interdite. Appliquée à un retour, cette règle
        garderait l'argent du client parce qu'il ne reste plus de gobelets — ce qui
        n'a aucun sens : il en RAPPORTE un.
        / An empty stock must not stop a customer from getting their deposit back:
          they are bringing a cup IN.
        """
        from inventaire.models import Stock

        Stock.objects.create(
            product=self.produit_retour_consigne,
            quantite=0,
            autoriser_vente_hors_stock=False,
        )

        reponse = self._poster_retour_consigne(moyen_paiement="espece")

        self.assertEqual(
            reponse.status_code,
            200,
            "Le client doit pouvoir recuperer sa consigne meme a stock zero.",
        )
        self.assertEqual(LigneArticle.objects.count(), 1)

    # ------------------------------------------------------------------ #
    #  T4 — Le cashless : un retour de consigne est une RECHARGE
    # ------------------------------------------------------------------ #

    def test_un_retour_de_consigne_en_nfc_credite_la_carte(self):
        """
        En cashless, rendre une consigne veut dire RECHARGER la carte.

        C'est le point le moins intuitif du chantier, et celui que la V1 avait déjà
        résolu ainsi (`methode_CR` : `refill_wallet(abs(total))`). Un « débit négatif »
        n'existe pas : la cascade de débit multi-asset cherche de quoi prélever, et sur
        un montant négatif elle s'arrête immédiatement sans rien écrire.

        Deux assertions, et les deux comptent :
          - la carte est créditée du montant ABSOLU (l'argent arrive vraiment) ;
          - la ligne comptable garde le montant NÉGATIF (le CA cashless baisse).
        / In cashless a deposit return is a TOP-UP: the card is credited the absolute
          amount, while the accounting line keeps the negative amount.
        """
        solde_avant = self._solde_de_la_carte()

        reponse = self._poster_retour_consigne_en_nfc()

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(
            self._solde_de_la_carte(),
            solde_avant + 100,
            "La carte doit etre creditee du montant rendu.",
        )

        ligne = LigneArticle.objects.get()
        self.assertEqual(
            ligne.amount,
            -100,
            "La ligne comptable reste negative : c'est elle qui fait baisser le CA.",
        )
        self.assertEqual(ligne.payment_method, "LE")
        self.assertEqual(ligne.carte, self.carte_client)
        self.assertEqual(ligne.wallet, self.wallet_carte)
        self.assertEqual(ligne.asset, self.asset_tlf.uuid)

    def test_un_retour_de_consigne_en_nfc_de_deux_gobelets_credite_deux_euros(self):
        """
        La quantité vaut aussi pour le crédit.
        / Quantity applies to the credit too.
        """
        reponse = self._poster_retour_consigne_en_nfc(quantite=2)

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(self._solde_de_la_carte(), 200)

    def test_un_retour_de_consigne_en_nfc_sans_asset_est_refuse(self):
        """
        Sans monnaie désignée, on ne devine pas : on refuse.

        `Product.asset` porte la monnaie à créditer. S'il manque, le seul choix serait
        d'inventer un asset — c'est-à-dire de créditer le client dans une monnaie que
        personne n'a choisie. On refuse, et surtout on n'écrit rien.
        / Without a designated currency we refuse rather than guess. And we write nothing.
        """
        self.produit_retour_consigne.asset = None
        self.produit_retour_consigne.save()

        reponse = self._poster_retour_consigne_en_nfc()

        self.assertContains(reponse, "monnaie associée", status_code=400)
        self.assertEqual(self._solde_de_la_carte(), 0, "Aucun credit ne doit avoir lieu.")
        self.assertEqual(LigneArticle.objects.count(), 0)

    def test_un_panier_de_retours_sur_deux_monnaies_differentes_est_refuse(self):
        """
        Deux consignes à rendre dans deux monnaies : on refuse plutôt que d'en choisir une.

        Le crédit se fait sur UN seul asset, pour le total du panier. Si le panier porte
        deux produits de retour rattachés à des monnaies différentes, créditer le tout
        sur la première reviendrait à rendre au client de la monnaie qu'il n'avait pas
        avancée, et à fausser le détail par monnaie dans les rapports.

        On refuse : c'est deux opérations, pas une.
        / The credit targets ONE asset for the whole cart total. Two returns on two
          currencies would credit money the customer never advanced.
        """
        autre_monnaie = AssetService.creer_asset(
            tenant=self.tenant,
            name="Seconde monnaie locale test consigne",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=self.wallet_lieu,
        )
        second_retour = Product.objects.create(
            name="Retour Consigne assiette",
            categorie_article=Product.VENTE,
            methode_caisse=Product.RETOUR_CONSIGNE,
            categorie_pos=self.categorie,
            asset=autre_monnaie,
            publish=True,
        )
        prix_second_retour = Price.objects.create(
            product=second_retour,
            name="Assiette",
            prix=Decimal("-2.00"),
            publish=True,
        )
        self.point_de_vente.products.add(second_retour)

        donnees = self._donnees_de_base("nfc")
        donnees["total"] = "-300"
        donnees["tag_id"] = self.carte_client.tag_id
        donnees[self._cle_panier(self.produit_retour_consigne, self.prix_retour_consigne)] = "1"
        donnees[self._cle_panier(second_retour, prix_second_retour)] = "1"
        reponse = self.client_http.post("/laboutik/paiement/payer/", data=donnees)

        self.assertContains(reponse, "monnaies différentes", status_code=400)
        self.assertEqual(
            self._solde_de_la_carte(),
            0,
            "Aucune monnaie ne doit etre creditee sur un panier ambigu.",
        )
        self.assertEqual(self._solde_de_la_carte(asset=autre_monnaie), 0)
        self.assertEqual(LigneArticle.objects.count(), 0)

    def test_un_retour_de_consigne_en_nfc_avec_un_asset_cadeau_est_refuse(self):
        """
        Une consigne se rend en monnaie locale, pas en cadeau.

        Un asset cadeau (TNF) créditerait le client d'une monnaie offerte par le lieu
        alors qu'il récupère une somme qu'il avait avancée. La ligne serait étiquetée
        `LOCAL_EURO` tandis que le crédit serait en cadeau : le total cashless resterait
        juste (LE et LG y sont confondus) mais le détail par monnaie mentirait.
        / A gift asset (TNF) would credit given money for money the customer advanced,
          and the per-currency detail would lie.
        """
        asset_cadeau = AssetService.creer_asset(
            tenant=self.tenant,
            name="Cadeau test consigne",
            category=Asset.TNF,
            currency_code="EUR",
            wallet_origin=self.wallet_lieu,
        )
        self.produit_retour_consigne.asset = asset_cadeau
        self.produit_retour_consigne.save()

        reponse = self._poster_retour_consigne_en_nfc()

        self.assertContains(reponse, "en monnaie locale", status_code=400)
        self.assertEqual(self._solde_de_la_carte(asset=asset_cadeau), 0)
        self.assertEqual(LigneArticle.objects.count(), 0)

    def test_un_retour_de_consigne_de_deux_gobelets_rend_deux_euros(self):
        """
        La quantite se multiplie, et le resultat reste negatif.
        / Quantity multiplies, and the result stays negative.
        """
        reponse = self._poster_retour_consigne(moyen_paiement="espece", quantite=2)

        self.assertEqual(reponse.status_code, 200)

        ligne = LigneArticle.objects.get()
        self.assertEqual(ligne.amount, -100)
        self.assertEqual(ligne.qty, 2)
        self.assertEqual(
            ligne.total(),
            -200,
            "Deux gobelets rendus valent deux euros rendus.",
        )
