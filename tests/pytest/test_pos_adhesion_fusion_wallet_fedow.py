"""
tests/pytest/test_pos_adhesion_fusion_wallet_fedow.py — Adhesion au POS V2 avec une carte
NFC anonyme : la carte doit etre liee au membre DES DEUX COTES (Lespass ET Fedow).
/ POS V2 membership with an anonymous NFC card: the card must be linked to the member on
BOTH sides (Lespass AND Fedow).

LOCALISATION : tests/pytest/test_pos_adhesion_fusion_wallet_fedow.py

POURQUOI CE FICHIER / WHY THIS FILE :
Depuis toujours, TiBillet ne lie JAMAIS une carte chargee d'un seul cote. Le parcours web
`/qr/link/` fait les trois etapes dans l'ordre (`BaseBillet/views.py`) :
   1. `get_or_create_wallet(user)`      — Fedow cree le wallet du user AVEC sa cle publique
   2. `linkwallet_card_number(...)`     — Fedow absorbe le wallet ephemere de la carte
   3. fusion locale des Tokens          — Lespass deplace le solde local
Le POS V2 ne fait que l'etape 3. Sur un lieu branche a Fedow, cela produit deux degats :
 - le FED que portait la carte reste sur un wallet ephemere que plus personne ne reference,
   donc invisible au comptoir ;
 - le user recoit un Wallet LOCAL a uuid aleatoire, inconnu de Fedow. Or Fedow authentifie
   chaque requete via l'en-tete `Wallet: <uuid>` : cet usager ne peut plus rien signer, et
   le prochain `get_or_create_wallet` levera « Wallet and member mismatch », a vie.

C'EST DE L'ARGENT REEL. Ces tests sont la preuve, pas la decoration.

MOCK STRICT, ET CE N'EST PAS UN DETAIL : la frontiere reseau (`FedowAPI`) est mockee avec
`create_autospec`, jamais avec un `MagicMock` nu. Un MagicMock nu accepte N'IMPORTE QUEL
attribut : `api.NFCcard.linkwallet_card_number` y « existe » meme si la vraie methode vit
sur une autre classe. Le test resterait vert pendant que le code casse en production.
/ STRICT MOCK: a bare MagicMock accepts ANY attribute and would validate a call on the wrong
  class. autospec raises AttributeError instead.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_pos_adhesion_fusion_wallet_fedow.py -v
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import uuid as uuid_module
from decimal import Decimal
from unittest import mock

from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import (
    CategorieProduct,
    Configuration,
    Membership,
    Price,
    Product,
)
from QrcodeCashless.models import CarteCashless
from fedow_connect.models import FedowConfig
from fedow_core.models import Asset, Token
from fedow_core.services import AssetService
from laboutik.models import PointDeVente


# Solde porte par la carte anonyme, en centimes : 66,00 €.
# Meme montant que le test de reference LaBoutik V1 (APIcashless/tests.py:2226), pour que
# les deux suites parlent du meme scenario.
# / Balance held by the anonymous card, in cents. Same amount as the LaBoutik V1 reference.
SOLDE_CARTE_ANONYME_CENTIMES = 6600

# Prix de l'adhesion vendue au comptoir, en euros.
# / Price of the membership sold at the counter, in euros.
PRIX_ADHESION_EUROS = Decimal("20.00")


def _fabriquer_fedow_api_mock(wallet_fedow_du_user):
    """
    Construit un faux `FedowAPI` qui imite le contrat du vrai.
    / Builds a fake FedowAPI mimicking the real contract.

    LOCALISATION : tests/pytest/test_pos_adhesion_fusion_wallet_fedow.py

    Le VRAI `get_or_create_wallet` POSE `user.wallet` et le sauve
    (`fedow_connect/fedow_api.py`). Le mock doit faire pareil : sinon la fonction testee
    travaille sur un user sans wallet et le test ne prouve rien.
    / The real get_or_create_wallet SETS and saves user.wallet; the mock must do the same.

    Le mock parent est un `MagicMock` : il sert UNIQUEMENT a enregistrer l'ORDRE des appels
    de ses deux enfants (`api.mock_calls`). Les enfants, eux, sont des `create_autospec`
    stricts — c'est la que se joue la verification du contrat.
    / The parent MagicMock only records call ORDER; the children are strict autospecs.

    :param wallet_fedow_du_user: Wallet local qui joue le role du miroir du wallet Fedow.
    :return: le faux FedowAPI, deja instancie.
    """
    from fedow_connect.fedow_api import NFCcardFedow, WalletFedow

    def poser_le_wallet_du_user(user_appele):
        """Imite le vrai client : il pose le wallet sur le user et le sauve.
        / Mimics the real client: sets the wallet on the user and saves it."""
        user_appele.wallet = wallet_fedow_du_user
        user_appele.save(update_fields=["wallet"])
        return wallet_fedow_du_user, True

    api = mock.MagicMock()
    api.wallet = mock.create_autospec(WalletFedow, instance=True)
    api.NFCcard = mock.create_autospec(NFCcardFedow, instance=True)
    api.wallet.get_or_create_wallet.side_effect = poser_le_wallet_du_user
    api.NFCcard.linkwallet_card_number.return_value = {"first_tag_id": "MOCKTAG1"}
    return api


class TestPosAdhesionFusionWalletFedow(FastTenantTestCase):
    """
    Une classe FastTenantTestCase = un schema cree en setUpClass.
    Chaque methode est isolee par rollback (TestCase._fixture_teardown), y compris les
    ecritures dans le schema public : `CarteCashless`, `Wallet`, `Asset` et `Token` vivent
    en SHARED_APPS, mais la connexion est la meme, donc le rollback les couvre.
    / One FastTenantTestCase class = one schema. Each method is rolled back, including
      SHARED_APPS writes (same connection).
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_pos_adhesion_fusion"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-pos-adhesion-fusion.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = "Test POS Adhesion Fusion"

    def setUp(self):
        # Re-poser le search_path apres le rollback du test precedent.
        # / Re-set search_path after the previous test's rollback.
        connection.set_tenant(self.tenant)

        # --- Le lieu : caisse V2 active ---
        # module_caisse exige module_monnaie_locale : on active les deux.
        # / V2 POS enabled (module_caisse requires module_monnaie_locale).
        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.save()

        # --- Le lieu est branche a Fedow ---
        # `can_fedow()` est vrai des que les trois champs sont remplis
        # (`fedow_connect/models.py`). FedowAPI etant mocke, la cle n'est jamais dechiffree.
        # / The venue is Fedow-connected: can_fedow() is true once the three fields are set.
        config_fedow = FedowConfig.get_solo()
        config_fedow.fedow_place_uuid = uuid_module.uuid4()
        config_fedow.fedow_place_admin_apikey = "cle-de-test-jamais-dechiffree"
        config_fedow.fedow_place_wallet_uuid = uuid_module.uuid4()
        config_fedow.save()
        assert config_fedow.can_fedow(), (
            "Le lieu de test doit etre branche a Fedow, sinon le scenario n'existe pas."
        )

        # --- La monnaie locale du lieu ---
        # / The venue's local currency.
        self.wallet_lieu = Wallet.objects.create(
            origin=self.tenant, name="Wallet lieu test adhesion"
        )
        self.asset_tlf = AssetService.creer_asset(
            tenant=self.tenant,
            name="Monnaie locale test adhesion",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=self.wallet_lieu,
        )

        # --- Le produit adhesion vendu au comptoir ---
        # La creation d'un Product ADHESION declenche
        # `BaseBillet.signals.send_membership_and_badge_product_to_fedow`, qui appelle le
        # VRAI Fedow. On le neutralise : ce test ne parle pas de l'asset d'adhesion, et un
        # appel reseau reel polluerait la base Fedow de dev.
        # / Creating an ADHESION Product fires a signal that calls the REAL Fedow. Neutralize
        #   it: this test is not about the membership asset, and a real call would pollute.
        self.categorie = CategorieProduct.objects.create(name="Adhesions test")
        with mock.patch("BaseBillet.signals.AssetFedow"):
            self.produit_adhesion = Product.objects.create(
                name="Adhesion test POS",
                categorie_article=Product.ADHESION,
                categorie_pos=self.categorie,
                publish=True,
            )
        self.prix_adhesion = Price.objects.create(
            product=self.produit_adhesion,
            name="Tarif plein",
            prix=PRIX_ADHESION_EUROS,
            subscription_type=Price.YEAR,
            publish=True,
        )

        # --- Le point de vente ---
        # / The point of sale.
        self.point_de_vente = PointDeVente.objects.create(
            name="Comptoir adhesions",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.point_de_vente.products.add(self.produit_adhesion)

        # --- La carte NFC ANONYME, chargee ---
        # Aucun user : c'est tout le sujet. Son solde vit sur un wallet ephemere.
        # / The ANONYMOUS loaded NFC card. No user: that is the whole point.
        self.wallet_ephemere = Wallet.objects.create(
            origin=self.tenant, name="Wallet ephemere carte test"
        )
        # `uuid` est l'identifiant du QR code, et c'est par lui que `CarteService` retrouve
        # la carte. Il est nullable en base : une carte de test sans uuid ferait chercher
        # `uuid=None`, qui matche toutes les autres cartes sans uuid. On le pose donc,
        # comme le fait toute carte reellement provisionnee.
        # / `uuid` is the QR code id and CarteService looks the card up by it. It is nullable
        #   in DB, and uuid=None would match every other uuid-less card. Set it, as any
        #   really provisioned card has one.
        self.carte_anonyme = CarteCashless.objects.create(
            tag_id="ADHTEST1",
            number="ADHTEST1",
            uuid=uuid_module.uuid4(),
            wallet_ephemere=self.wallet_ephemere,
        )
        Token.objects.create(
            wallet=self.wallet_ephemere,
            asset=self.asset_tlf,
            value=SOLDE_CARTE_ANONYME_CENTIMES,
        )

        # --- Le caissier ---
        # Admin du tenant, session navigateur (contourne la carte primaire).
        # / The cashier: tenant admin with a browser session.
        self.caissier, _cree = TibilletUser.objects.get_or_create(
            email="caissier-adhesion-fusion@tibillet.localhost",
            defaults={
                "username": "caissier-adhesion-fusion@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        self.caissier.client_admin.add(self.tenant)
        self.client_http = TenantClient(self.tenant)
        self.client_http.force_login(self.caissier)

        # L'email du membre identifie au comptoir. Il n'existe pas encore en base :
        # c'est le cas nominal, celui d'un nouvel adherent.
        # / The member's email, typed at the counter. Brand new user: the nominal case.
        self.email_adherent = "nouvel-adherent-fusion@tibillet.localhost"

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _poster_adhesion_avec_carte(self, tag_id=None, email=None):
        """
        Joue le geste du caissier : une adhesion au panier, la carte scannee, l'email saisi.
        / Plays the cashier's gesture: one membership in the cart, card scanned, email typed.

        :return: la reponse HTTP du POS.
        """
        prix_en_centimes = int(round(self.prix_adhesion.prix * 100))
        donnees_du_formulaire = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "moyen_paiement": "espece",
            "total": str(prix_en_centimes),
            "given_sum": str(prix_en_centimes),
            f"repid-{self.produit_adhesion.uuid}--{self.prix_adhesion.uuid}": "1",
            "tag_id": self.carte_anonyme.tag_id if tag_id is None else tag_id,
            "email_adhesion": self.email_adherent if email is None else email,
            "prenom_adhesion": "Alice",
            "nom_adhesion": "Testeuse",
        }
        return self.client_http.post(
            "/laboutik/paiement/payer/", data=donnees_du_formulaire
        )

    def _patcher_fedow(self, api_mockee):
        """
        Remplace `FedowAPI` PARTOUT ou il est importe sur ce chemin, en rendant la MEME
        instance. Deux points d'import existent : `laboutik.views` (import en tete de
        module) et `fedow_connect.fedow_api` (la source). Patcher un seul des deux laisserait
        passer un appel reel, et l'assertion d'ordre ne voudrait plus rien dire.
        / Patch FedowAPI at BOTH import points, returning the SAME instance.

        :return: un context manager a utiliser en `with`.
        """
        import contextlib

        @contextlib.contextmanager
        def _patch_double():
            with mock.patch("laboutik.views.FedowAPI", return_value=api_mockee), \
                 mock.patch(
                     "fedow_connect.fedow_api.FedowAPI", return_value=api_mockee
                 ):
                yield

        return _patch_double()

    # ------------------------------------------------------------------ #
    #  T1 — LE test du bug
    # ------------------------------------------------------------------ #

    def test_adhesion_carte_anonyme_declare_le_user_et_lie_la_carte_chez_fedow(self):
        """
        Un adherent est identifie au comptoir avec une carte NFC ANONYME qui porte 66 €.
        La carte doit finir liee a ce membre DES DEUX COTES.
        / A member is identified at the counter with an ANONYMOUS card holding €66.
          The card must end up linked to that member on BOTH sides.

        Ce que le test exige, dans l'ordre :
          1. Le user est DECLARE a Fedow (`get_or_create_wallet`) — seul appel qui transmet
             sa cle publique. Sans lui, son wallet est inauthentifiable.
          2. La carte est LIEE chez Fedow (`linkwallet_card_number`), pour que Fedow absorbe
             le wallet ephemere dans celui du user.
          3. Ces deux appels sont faits HORS du bloc atomic de la vente : un appel reseau
             dans une transaction tient un verrou DB pendant toute la latence, et un rollback
             ferait disparaitre un user dont Fedow garde deja la cle RSA.
          4. Le wallet du user est celui de Fedow, PAS un uuid local tire au hasard.
          5. Le solde a suivi, et la carte n'est plus anonyme cote Lespass.
        """
        wallet_fedow_du_user = Wallet.objects.create(
            uuid=uuid_module.uuid4(),
            origin=self.tenant,
            name="Wallet Fedow adherent test",
        )
        api_fedow = _fabriquer_fedow_api_mock(wallet_fedow_du_user)

        # Profondeur de savepoints AVANT la requete. `FastTenantTestCase` enveloppe deja le
        # test dans une transaction : on mesure donc une reference, on ne suppose pas zero.
        # Le bloc atomic de la vente ajoutera un savepoint ; un appel Fedow fait a
        # l'interieur se verra a sa profondeur.
        # / Savepoint depth BEFORE the request. The test is already wrapped in a transaction,
        #   so we measure a baseline rather than assume zero.
        profondeur_hors_atomic = len(connection.savepoint_ids)
        profondeurs_pendant_les_appels_fedow = []

        declarer_le_wallet = api_fedow.wallet.get_or_create_wallet.side_effect

        def declarer_en_notant_la_profondeur(user_appele):
            profondeurs_pendant_les_appels_fedow.append(len(connection.savepoint_ids))
            return declarer_le_wallet(user_appele)

        def lier_en_notant_la_profondeur(user=None, card_number=None):
            profondeurs_pendant_les_appels_fedow.append(len(connection.savepoint_ids))
            return {"first_tag_id": "MOCKTAG1"}

        api_fedow.wallet.get_or_create_wallet.side_effect = (
            declarer_en_notant_la_profondeur
        )
        api_fedow.NFCcard.linkwallet_card_number.side_effect = (
            lier_en_notant_la_profondeur
        )

        with self._patcher_fedow(api_fedow):
            reponse = self._poster_adhesion_avec_carte()

        assert reponse.status_code == 200, (
            f"Le paiement doit aboutir (recu {reponse.status_code})."
        )

        # --- 1. Le user a ete DECLARE a Fedow, avec sa cle publique ---
        # / The user was DECLARED to Fedow, carrying their public key.
        assert api_fedow.wallet.get_or_create_wallet.called, (
            "Le membre n'a PAS ete declare a Fedow. Son wallet n'aura pas de cle publique : "
            "il ne pourra plus rien signer, son FED devient invisible au comptoir, et le "
            "prochain get_or_create_wallet levera « Wallet and member mismatch », a vie."
        )
        user_declare = api_fedow.wallet.get_or_create_wallet.call_args.args[0]
        assert user_declare.email == self.email_adherent

        # --- 2. La carte a ete LIEE chez Fedow ---
        # / The card was LINKED on Fedow's side.
        assert api_fedow.NFCcard.linkwallet_card_number.called, (
            "La carte n'a PAS ete liee chez Fedow. Le FED qu'elle portait reste sur un "
            "wallet ephemere que plus personne ne reference : argent inaccessible au POS."
        )
        appel_de_liaison = api_fedow.NFCcard.linkwallet_card_number.call_args
        assert appel_de_liaison.kwargs["user"].email == self.email_adherent
        assert appel_de_liaison.kwargs["card_number"] == self.carte_anonyme.number

        # --- 3. Dans cet ordre : declarer AVANT de lier ---
        # Fedow ne peut pas lier une carte a un wallet qu'il ne connait pas encore.
        # L'ordre se lit sur le mock parent, qui enregistre les appels des deux enfants.
        # / Declare BEFORE linking; order is read on the parent mock.
        noms_des_appels = [appel[0] for appel in api_fedow.mock_calls]
        rang_declaration = next(
            i for i, nom in enumerate(noms_des_appels)
            if nom.endswith("get_or_create_wallet")
        )
        rang_liaison = next(
            i for i, nom in enumerate(noms_des_appels)
            if nom.endswith("linkwallet_card_number")
        )
        assert rang_declaration < rang_liaison, (
            "get_or_create_wallet doit preceder linkwallet_card_number."
        )

        # --- 4. Les appels reseau sont HORS du bloc atomic ---
        # / The network calls happen OUTSIDE the atomic block.
        assert profondeurs_pendant_les_appels_fedow, "Aucun appel Fedow n'a ete observe."
        assert all(
            profondeur == profondeur_hors_atomic
            for profondeur in profondeurs_pendant_les_appels_fedow
        ), (
            f"Un appel Fedow a ete fait DANS le bloc atomic "
            f"(profondeurs observees {profondeurs_pendant_les_appels_fedow}, "
            f"attendu {profondeur_hors_atomic}). Un appel reseau dans une transaction tient "
            f"un verrou DB pendant toute la latence, et un rollback ferait disparaitre un "
            f"user dont Fedow garde deja la cle RSA : cet email deviendrait indeclarable."
        )

        # --- 5. Le wallet du membre est celui de Fedow, pas un uuid local ---
        # / The member's wallet is Fedow's, not a random local uuid.
        adherent = TibilletUser.objects.get(email=self.email_adherent)
        assert adherent.wallet is not None
        assert adherent.wallet.uuid == wallet_fedow_du_user.uuid, (
            f"Le membre porte un wallet LOCAL ({adherent.wallet.uuid}) que Fedow ne connait "
            f"pas, au lieu du wallet Fedow ({wallet_fedow_du_user.uuid})."
        )

        # --- 6. Le solde a suivi, et la carte n'est plus anonyme ---
        # / The balance followed, and the card is no longer anonymous.
        self.carte_anonyme.refresh_from_db()
        assert self.carte_anonyme.user == adherent
        assert self.carte_anonyme.wallet_ephemere is None

        token_du_membre = Token.objects.filter(
            wallet=adherent.wallet, asset=self.asset_tlf
        ).first()
        assert token_du_membre is not None, "Le solde n'a pas suivi le membre."
        assert token_du_membre.value == SOLDE_CARTE_ANONYME_CENTIMES

        # --- 7. L'adhesion existe bien ---
        # / The membership does exist.
        assert Membership.objects.filter(
            user=adherent, price=self.prix_adhesion
        ).exists()

    # ------------------------------------------------------------------ #
    #  T2 — Le reseau refuse VRAIMENT la carte
    # ------------------------------------------------------------------ #

    def test_si_le_reseau_refuse_la_carte_rien_ne_bouge_mais_l_adhesion_existe(self):
        """
        Le reseau refuse de rattacher la carte (elle appartient a quelqu'un d'autre).
        / The network refuses to link the card (it belongs to someone else).

        Alors : on ne fusionne RIEN en local. Sinon Lespass dirait une chose et le reseau
        une autre, et le solde de la carte partirait chez le mauvais usager.
        Mais l'adhesion reste due : elle est creee. Une Membership n'a pas besoin de
        portefeuille, et refuser la vente pour un probleme de carte punirait l'adherent.
        / Merge NOTHING locally, otherwise Lespass and the network would disagree and the
          balance would move to the wrong person. But the membership is still owed.
        """
        wallet_fedow_du_user = Wallet.objects.create(
            uuid=uuid_module.uuid4(), origin=self.tenant, name="Wallet Fedow refus"
        )
        api_fedow = _fabriquer_fedow_api_mock(wallet_fedow_du_user)

        # Le reseau refuse la liaison...
        # / The network refuses the link...
        api_fedow.NFCcard.linkwallet_card_number.side_effect = Exception(
            "linkwallet_card_number : 400 {'card_number': ['Objet invalide']}"
        )
        # ...et confirme que la carte appartient a un wallet ETRANGER. C'est ce qui separe
        # un vrai refus d'une reponse perdue (cf. T3).
        # / ...and confirms the card belongs to a FOREIGN wallet. This is what separates a
        #   real refusal from a lost response (see T3).
        api_fedow.NFCcard.card_tag_id_retrieve.return_value = {
            "wallet_uuid": str(uuid_module.uuid4()),
            "is_wallet_ephemere": False,
        }

        with self._patcher_fedow(api_fedow):
            reponse = self._poster_adhesion_avec_carte()

        assert reponse.status_code == 200, (
            "Un refus de carte ne doit pas faire echouer la vente : l'adhesion est due."
        )

        adherent = TibilletUser.objects.get(email=self.email_adherent)

        # --- Rien n'a bouge cote carte ---
        # / Nothing moved on the card side.
        self.carte_anonyme.refresh_from_db()
        assert self.carte_anonyme.user is None, (
            "La carte a ete rattachee en local alors que le reseau l'a refusee : "
            "Lespass et le reseau divergent sur son proprietaire."
        )
        assert self.carte_anonyme.wallet_ephemere is not None, (
            "Le wallet ephemere a ete detache : le solde de la carte devient introuvable."
        )

        # --- Le solde est reste sur la carte, au centime pres ---
        # / The balance stayed on the card, to the cent.
        token_de_la_carte = Token.objects.get(
            wallet=self.wallet_ephemere, asset=self.asset_tlf
        )
        assert token_de_la_carte.value == SOLDE_CARTE_ANONYME_CENTIMES
        assert not Token.objects.filter(
            wallet=adherent.wallet, asset=self.asset_tlf
        ).exists()

        # --- Mais l'adhesion existe ---
        # / But the membership exists.
        assert Membership.objects.filter(
            user=adherent, price=self.prix_adhesion
        ).exists(), "L'adhesion doit etre creee meme si la carte n'a pas pu etre liee."
        # --- Le caissier est PREVENU a l'ecran ---
        # Construire un avertissement sans l'afficher ne sert a rien : le comptoir doit
        # savoir que la carte n'a pas suivi.
        # / The cashier IS warned on screen: building a warning without showing it is
        #   useless — the counter must know the card did not follow.
        assert "alerte-adhesion-carte" in reponse.content.decode(), (
            "Aucun avertissement affiche : le caissier croit que la carte a ete rattachee."
        )

    # ------------------------------------------------------------------ #
    #  T3 — Le refus est un FAUX NEGATIF (reponse perdue, ou 2e caisse)
    # ------------------------------------------------------------------ #

    def test_si_le_reseau_avait_deja_lie_la_carte_la_fusion_locale_a_bien_lieu(self):
        """
        Le reseau refuse la liaison PARCE QU'IL L'A DEJA FAITE pour ce membre.
        / The network refuses the link BECAUSE IT ALREADY DID IT for this member.

        C'est le piege le plus dangereux du chemin. Le reseau n'accepte de lier qu'une carte
        LIBRE : des qu'elle est liee — meme a CE membre — il repond 400. Or ce cas arrive
        pour de bon : la reponse se perd apres traitement (timeout), une seconde caisse
        arrive apres la premiere, ou le bloc atomic local a echoue apres coup.
        Si on prenait ce 400 pour un refus, on ne fusionnerait jamais : le reseau dirait
        carte→membre et Lespass dirait carte anonyme, pour toujours, sans aucun moyen de
        rattrapage — le parcours web refuse lui aussi une carte deja liee.
        / The network only links FREE cards: once linked, even to THIS member, it answers
          400. Taking that for a refusal would leave both sides permanently disagreeing,
          with no recovery: the web path refuses an already-linked card too.
        """
        wallet_fedow_du_user = Wallet.objects.create(
            uuid=uuid_module.uuid4(), origin=self.tenant, name="Wallet Fedow faux negatif"
        )
        api_fedow = _fabriquer_fedow_api_mock(wallet_fedow_du_user)

        api_fedow.NFCcard.linkwallet_card_number.side_effect = Exception(
            "linkwallet_card_number : 400 {'card_number': ['Objet invalide']}"
        )
        # Le reseau rattache DEJA cette carte au wallet de ce membre.
        # / The network ALREADY attaches this card to this member's wallet.
        api_fedow.NFCcard.card_tag_id_retrieve.return_value = {
            "wallet_uuid": str(wallet_fedow_du_user.uuid),
            "is_wallet_ephemere": False,
        }

        with self._patcher_fedow(api_fedow):
            reponse = self._poster_adhesion_avec_carte()

        assert reponse.status_code == 200

        adherent = TibilletUser.objects.get(email=self.email_adherent)

        # On a bien VERIFIE aupres du reseau avant de conclure.
        # / We DID ask the network before concluding.
        assert api_fedow.NFCcard.card_tag_id_retrieve.called, (
            "Sur echec de liaison, il faut demander au reseau a qui est la carte. Sans "
            "cette verification, une reponse perdue fige la divergence pour toujours."
        )

        # La fusion locale a bien eu lieu : les deux cotes disent la meme chose.
        # / The local merge happened: both sides now agree.
        self.carte_anonyme.refresh_from_db()
        assert self.carte_anonyme.user == adherent, (
            "Le reseau rattache deja la carte a ce membre, mais Lespass l'a laissee "
            "anonyme : les deux cotes divergent, et plus rien ne peut les reconcilier."
        )
        assert self.carte_anonyme.wallet_ephemere is None

        token_du_membre = Token.objects.get(
            wallet=adherent.wallet, asset=self.asset_tlf
        )
        assert token_du_membre.value == SOLDE_CARTE_ANONYME_CENTIMES

    # ------------------------------------------------------------------ #
    #  T4 — Le membre declare survit a un rollback du bloc atomic
    # ------------------------------------------------------------------ #

    def test_le_membre_declare_au_reseau_survit_a_un_rollback_du_bloc_atomic(self):
        """
        Une panne DANS le bloc atomic annule la vente, mais PAS la declaration du membre.
        / A failure INSIDE the atomic rolls back the sale, but NOT the member's declaration.

        C'est le test qui interdit de remettre la resolution dans la transaction. Si elle y
        etait, le rollback effacerait le user local pendant que le reseau garde deja sa cle
        RSA. Au retry, Lespass regenererait une cle differente, le reseau la refuserait, et
        cet email deviendrait indeclarable A VIE — sans reparation manuelle.
        / If the resolution were inside the transaction, the rollback would erase the local
          user while the network keeps their RSA key. On retry a new key would be refused,
          making that email undeclarable FOREVER.
        """
        wallet_fedow_du_user = Wallet.objects.create(
            uuid=uuid_module.uuid4(), origin=self.tenant, name="Wallet Fedow rollback"
        )
        api_fedow = _fabriquer_fedow_api_mock(wallet_fedow_du_user)

        # Le test client re-leve par defaut les exceptions de la vue : on veut ici observer
        # l'etat de la base APRES le rollback, pas remonter l'exception.
        # / The test client re-raises view exceptions by default; here we want to inspect the
        #   DB state AFTER the rollback instead.
        self.client_http.raise_request_exception = False

        # La panne : elle survient dans le bloc atomic, APRES la creation des adhesions.
        # / The failure happens inside the atomic, AFTER the memberships are created.
        with self._patcher_fedow(api_fedow), mock.patch(
            "laboutik.views._creer_billets_depuis_panier",
            side_effect=Exception("panne simulee dans le bloc atomic"),
        ):
            self._poster_adhesion_avec_carte()

        # --- Le membre existe toujours, avec le wallet que le reseau lui connait ---
        # / The member still exists, holding the wallet the network knows.
        adherent = TibilletUser.objects.filter(email=self.email_adherent).first()
        assert adherent is not None, (
            "Le membre a disparu avec le rollback alors que le reseau garde deja sa cle "
            "RSA : au retry, sa nouvelle cle sera refusee et cet email sera indeclarable."
        )
        assert adherent.wallet is not None
        assert adherent.wallet.uuid == wallet_fedow_du_user.uuid

        # --- Mais la vente, elle, a bien ete annulee ---
        # / But the sale itself was rolled back.
        assert not Membership.objects.filter(user=adherent).exists()

    # ------------------------------------------------------------------ #
    #  T6 — Anti-vol : un membre ne collectionne pas les cartes
    # ------------------------------------------------------------------ #

    def test_membre_possedant_deja_une_carte_le_reseau_n_est_pas_sollicite(self):
        """
        Le membre a deja une carte : on ne rattache pas la seconde, et surtout on NE
        PREVIENT PAS le reseau.
        / The member already has a card: do not link the second one, and above all do NOT
          tell the network.

        POURQUOI LE CONTROLE EST LOCAL, ET AVANT L'APPEL : le reseau ne bloque une seconde
        carte que si le wallet cible porte deja des jetons. Un membre au wallet vide y
        passerait, pendant que Lespass le refuserait ici — le reseau dirait carte→membre et
        Lespass dirait carte anonyme. On tranche donc avant d'avoir rien envoye.
        / The network only blocks a second card when the target wallet already holds tokens.
          A member with an empty wallet would pass there while Lespass refuses here, leaving
          both sides disagreeing. So we decide before sending anything.
        """
        # Le membre existe deja et possede une autre carte.
        # / The member already exists and owns another card.
        membre_existant = TibilletUser.objects.create(
            email=self.email_adherent, username=self.email_adherent
        )
        CarteCashless.objects.create(
            tag_id="ADHDEJA1", number="ADHDEJA1", uuid=uuid_module.uuid4(),
            user=membre_existant,
        )

        wallet_fedow_du_user = Wallet.objects.create(
            uuid=uuid_module.uuid4(), origin=self.tenant, name="Wallet Fedow antivol"
        )
        api_fedow = _fabriquer_fedow_api_mock(wallet_fedow_du_user)

        with self._patcher_fedow(api_fedow):
            reponse = self._poster_adhesion_avec_carte()

        assert reponse.status_code == 200

        # --- Le reseau n'a PAS ete sollicite pour la liaison ---
        # / The network was NOT asked to link.
        assert not api_fedow.NFCcard.linkwallet_card_number.called, (
            "Le reseau a ete sollicite alors qu'on savait deja localement qu'on refuserait "
            "la liaison. S'il avait accepte, les deux cotes divergeraient."
        )

        # --- La carte scannee reste anonyme, son solde intact ---
        # / The scanned card stays anonymous, its balance untouched.
        self.carte_anonyme.refresh_from_db()
        assert self.carte_anonyme.user is None
        assert self.carte_anonyme.wallet_ephemere is not None
        token_de_la_carte = Token.objects.get(
            wallet=self.wallet_ephemere, asset=self.asset_tlf
        )
        assert token_de_la_carte.value == SOLDE_CARTE_ANONYME_CENTIMES

        # --- Mais l'adhesion est bien enregistree ---
        # / But the membership is properly recorded.
        assert Membership.objects.filter(
            user=membre_existant, price=self.prix_adhesion
        ).exists()
        # --- Le caissier est PREVENU a l'ecran ---
        # Construire un avertissement sans l'afficher ne sert a rien : le comptoir doit
        # savoir que la carte n'a pas suivi.
        # / The cashier IS warned on screen: building a warning without showing it is
        #   useless — the counter must know the card did not follow.
        assert "alerte-adhesion-carte" in reponse.content.decode(), (
            "Aucun avertissement affiche : le caissier croit que la carte a ete rattachee."
        )

    # ------------------------------------------------------------------ #
    #  T7 — Reparation d'un wallet local divergent
    # ------------------------------------------------------------------ #

    def test_un_membre_au_wallet_local_divergent_est_realigne_avec_son_solde(self):
        """
        Un membre porte un wallet LOCAL a uuid aleatoire, herite d'avant cette regle.
        Il doit etre realigne sur son wallet reseau, solde compris.
        / A member holds a random-uuid LOCAL wallet inherited from before this rule. They
          must be realigned onto their network wallet, balance included.

        Le realignement deplace la valeur par des Transaction(FUSION), et ne SUPPRIME rien :
        `Token` porte une contrainte d'unicite (wallet, asset), et toutes les cles etrangeres
        vers `Wallet` sont en PROTECT — dont `LigneArticle.wallet`, qui vit dans le schema du
        lieu. Un deplacement en masse suivi d'une suppression pourrait echouer a mi-chemin,
        apres avoir repointe le membre, et laisser son solde orphelin.
        / Realignment moves value through FUSION transactions and DELETES nothing: Token has
          a unique (wallet, asset) constraint and every Wallet FK is PROTECT.
        """
        from fedow_core.models import Transaction

        # Le membre existe, avec un wallet local garni de 12,00 €.
        # / The member exists, holding a local wallet credited with €12.00.
        membre_existant = TibilletUser.objects.create(
            email=self.email_adherent, username=self.email_adherent
        )
        wallet_local_divergent = Wallet.objects.create(
            origin=self.tenant, name="Wallet local herite"
        )
        membre_existant.wallet = wallet_local_divergent
        membre_existant.save(update_fields=["wallet"])
        Token.objects.create(
            wallet=wallet_local_divergent, asset=self.asset_tlf, value=1200
        )

        wallet_fedow_du_user = Wallet.objects.create(
            uuid=uuid_module.uuid4(), origin=self.tenant, name="Wallet Fedow realigne"
        )
        api_fedow = _fabriquer_fedow_api_mock(wallet_fedow_du_user)

        # Le vrai client compare l'uuid rendu par le reseau a celui du membre et leve quand
        # ils different. On reproduit ce contrat : premier appel → refus, second appel (le
        # membre ayant ete detache en memoire) → succes.
        # / The real client raises on a diverging uuid. Reproduce that contract: first call
        #   refuses, second (after the in-memory detach) succeeds.
        appels_de_declaration = {"nombre": 0}

        def declarer_comme_le_vrai_client(user_appele):
            appels_de_declaration["nombre"] += 1
            if user_appele.wallet is not None:
                raise Exception("Wallet and member mismatch")
            user_appele.wallet = wallet_fedow_du_user
            user_appele.save(update_fields=["wallet"])
            return wallet_fedow_du_user, False

        api_fedow.wallet.get_or_create_wallet.side_effect = (
            declarer_comme_le_vrai_client
        )

        with self._patcher_fedow(api_fedow):
            reponse = self._poster_adhesion_avec_carte()

        assert reponse.status_code == 200
        assert appels_de_declaration["nombre"] == 2, (
            "Le realignement doit redemander le wallet au reseau apres avoir detache le "
            "wallet local divergent."
        )

        membre_existant.refresh_from_db()
        assert membre_existant.wallet.uuid == wallet_fedow_du_user.uuid

        # --- Le solde a suivi : 12,00 € herites + 66,00 € de la carte ---
        # / The balance followed: €12.00 inherited + €66.00 from the card.
        token_du_membre = Token.objects.get(
            wallet=wallet_fedow_du_user, asset=self.asset_tlf
        )
        assert token_du_membre.value == 1200 + SOLDE_CARTE_ANONYME_CENTIMES, (
            "Le solde du wallet local n'a pas suivi le membre : il dort sur un wallet que "
            "plus personne ne reference."
        )

        # --- L'ancien wallet est vide, mais TOUJOURS EN BASE (piste d'audit) ---
        # / The old wallet is empty but STILL IN DB (audit trail).
        assert Wallet.objects.filter(pk=wallet_local_divergent.pk).exists(), (
            "Le wallet d'origine a ete supprime : on perd la piste d'audit, et la "
            "suppression peut echouer sur des lignes vivant dans un autre schema."
        )
        assert Transaction.objects.filter(
            sender=wallet_local_divergent, receiver=wallet_fedow_du_user
        ).exists(), "Le deplacement du solde doit laisser une Transaction de fusion."

    # ------------------------------------------------------------------ #
    #  T8 — Adhesion ET recharge dans le meme panier
    # ------------------------------------------------------------------ #

    def test_adhesion_et_recharge_dans_le_meme_panier_le_solde_recharge_suit_le_membre(
        self,
    ):
        """
        Le client prend une adhesion ET recharge sa carte, en une seule vente.
        Les deux montants doivent finir sur le portefeuille du membre.
        / The customer takes a membership AND tops up their card in one sale. Both amounts
          must end up on the member's wallet.

        L'ORDRE DANS LA TRANSACTION EST CE QUE CE TEST PROTEGE. La recharge est creditee sur
        le portefeuille resolu au debut de la vente — pour une carte anonyme, son
        portefeuille ephemere. Or la fusion d'adhesion DETACHE ce portefeuille de la carte.
        Si la recharge passait apres, elle crediterait un portefeuille que plus rien ne
        reference : l'argent serait verse, encaisse, et introuvable. En rechargeant d'abord,
        la fusion ramasse le solde tout juste credite.
        / ORDER INSIDE THE TRANSACTION IS WHAT THIS TEST PROTECTS: the membership merge
          DETACHES the ephemeral wallet, so a top-up running after would credit a wallet
          nothing references — money taken and unreachable.
        """
        # Le produit de recharge est cree automatiquement avec l'Asset, avec ses tarifs
        # par defaut (1, 5, 10, Libre). / The top-up product is auto-created with the asset.
        produit_recharge = Product.objects.get(asset=self.asset_tlf)
        tarif_dix_euros = produit_recharge.prices.get(prix=Decimal("10.00"))
        self.point_de_vente.products.add(produit_recharge)

        wallet_fedow_du_user = Wallet.objects.create(
            uuid=uuid_module.uuid4(), origin=self.tenant, name="Wallet Fedow recharge"
        )
        api_fedow = _fabriquer_fedow_api_mock(wallet_fedow_du_user)

        prix_adhesion_centimes = int(round(self.prix_adhesion.prix * 100))
        montant_recharge_centimes = 1000
        donnees_du_formulaire = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "moyen_paiement": "espece",
            "total": str(prix_adhesion_centimes + montant_recharge_centimes),
            "given_sum": str(prix_adhesion_centimes + montant_recharge_centimes),
            f"repid-{self.produit_adhesion.uuid}--{self.prix_adhesion.uuid}": "1",
            f"repid-{produit_recharge.uuid}--{tarif_dix_euros.uuid}": "1",
            "tag_id": self.carte_anonyme.tag_id,
            "email_adhesion": self.email_adherent,
            "prenom_adhesion": "Alice",
            "nom_adhesion": "Testeuse",
        }

        with self._patcher_fedow(api_fedow):
            reponse = self.client_http.post(
                "/laboutik/paiement/payer/", data=donnees_du_formulaire
            )

        assert reponse.status_code == 200

        adherent = TibilletUser.objects.get(email=self.email_adherent)

        # --- Les DEUX montants sont sur le portefeuille du membre ---
        # / BOTH amounts are on the member's wallet.
        token_du_membre = Token.objects.get(
            wallet=adherent.wallet, asset=self.asset_tlf
        )
        assert token_du_membre.value == (
            SOLDE_CARTE_ANONYME_CENTIMES + montant_recharge_centimes
        ), (
            f"Le membre porte {token_du_membre.value} centimes au lieu de "
            f"{SOLDE_CARTE_ANONYME_CENTIMES + montant_recharge_centimes} : la recharge a "
            f"ete creditee sur le portefeuille ephemere APRES que la fusion l'a detache. "
            f"Le client a paye une recharge que personne ne peut plus depenser."
        )

        # --- Le portefeuille ephemere, detache, ne retient rien ---
        # / The detached ephemeral wallet holds nothing back.
        token_ephemere = Token.objects.filter(
            wallet=self.wallet_ephemere, asset=self.asset_tlf
        ).first()
        assert token_ephemere is None or token_ephemere.value == 0

    # ------------------------------------------------------------------ #
    #  T9 — Le paiement par CB suit le meme chemin
    # ------------------------------------------------------------------ #

    def test_adhesion_payee_par_carte_bancaire_declare_aussi_le_membre(self):
        """
        Le paiement par CB doit se comporter comme le paiement en especes.
        / Card payment must behave like cash payment.

        POURQUOI CE TEST EXISTE : les deux moyens de paiement sont servis par DEUX blocs de
        code distincts (`_payer_par_carte_ou_cheque` et `_payer_en_especes`), qui repetent la
        meme sequence. Une correction appliquee a un seul des deux passerait inapercue —
        c'est exactement le genre d'oubli que ce test attrape.
        / The two payment methods are served by TWO distinct code blocks repeating the same
          sequence. A fix applied to only one of them would go unnoticed.
        """
        wallet_fedow_du_user = Wallet.objects.create(
            uuid=uuid_module.uuid4(), origin=self.tenant, name="Wallet Fedow CB"
        )
        api_fedow = _fabriquer_fedow_api_mock(wallet_fedow_du_user)

        prix_en_centimes = int(round(self.prix_adhesion.prix * 100))
        donnees_du_formulaire = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "moyen_paiement": "carte_bancaire",
            "total": str(prix_en_centimes),
            "given_sum": "0",
            f"repid-{self.produit_adhesion.uuid}--{self.prix_adhesion.uuid}": "1",
            "tag_id": self.carte_anonyme.tag_id,
            "email_adhesion": self.email_adherent,
            "prenom_adhesion": "Alice",
            "nom_adhesion": "Testeuse",
        }

        with self._patcher_fedow(api_fedow):
            reponse = self.client_http.post(
                "/laboutik/paiement/payer/", data=donnees_du_formulaire
            )

        assert reponse.status_code == 200

        assert api_fedow.wallet.get_or_create_wallet.called, (
            "Le membre n'est pas declare au reseau sur le chemin CB : la correction n'a ete "
            "appliquee qu'au paiement en especes."
        )
        assert api_fedow.NFCcard.linkwallet_card_number.called

        adherent = TibilletUser.objects.get(email=self.email_adherent)
        assert adherent.wallet.uuid == wallet_fedow_du_user.uuid

        self.carte_anonyme.refresh_from_db()
        assert self.carte_anonyme.user == adherent
        assert self.carte_anonyme.wallet_ephemere is None
        token_du_membre = Token.objects.get(
            wallet=adherent.wallet, asset=self.asset_tlf
        )
        assert token_du_membre.value == SOLDE_CARTE_ANONYME_CENTIMES

    # ------------------------------------------------------------------ #
    #  T10 — Paiement NFC : plus d'adhesion fantome
    # ------------------------------------------------------------------ #

    def _poster_adhesion_payee_par_nfc(self, avec_identification=True):
        """POST d'une adhesion reglee AVEC LA CARTE elle-meme (moyen_paiement=nfc).
        / POSTs a membership paid WITH THE CARD itself."""
        prix_en_centimes = int(round(self.prix_adhesion.prix * 100))
        donnees_du_formulaire = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "moyen_paiement": "nfc",
            "total": str(prix_en_centimes),
            "given_sum": "0",
            f"repid-{self.produit_adhesion.uuid}--{self.prix_adhesion.uuid}": "1",
            "tag_id": self.carte_anonyme.tag_id,
        }
        if avec_identification:
            donnees_du_formulaire.update({
                "email_adhesion": self.email_adherent,
                "prenom_adhesion": "Alice",
                "nom_adhesion": "Testeuse",
            })
        return self.client_http.post(
            "/laboutik/paiement/payer/", data=donnees_du_formulaire
        )

    def test_adhesion_payee_par_nfc_sans_identification_est_refusee_sans_debit(self):
        """
        Une adhesion reglee par NFC sans identification est REFUSEE, avant tout debit.
        / An NFC-paid membership without identification is REFUSED, before any debit.

        C'EST LE PIRE DES CAS DE CE CHEMIN. La carte anonyme payait : le portefeuille etait
        debite, la ligne de vente creee, et l'adhesion... jamais enregistree, parce que
        `carte.user` valait None. Le client repartait avec 20 € de moins et aucune adhesion,
        sans le moindre message. On refuse desormais AVANT de toucher au solde.
        / THE WORST CASE OF THIS PATH: the wallet was debited, the sale line created, and the
          membership never recorded, because carte.user was None. The customer left €20
          poorer with nothing, silently. We now refuse BEFORE touching the balance.
        """
        wallet_fedow_du_user = Wallet.objects.create(
            uuid=uuid_module.uuid4(), origin=self.tenant, name="Wallet Fedow nfc refus"
        )
        api_fedow = _fabriquer_fedow_api_mock(wallet_fedow_du_user)

        with self._patcher_fedow(api_fedow):
            reponse = self._poster_adhesion_payee_par_nfc(avec_identification=False)

        assert reponse.status_code == 400, (
            "Une adhesion sans identification doit etre refusee, pas encaissee."
        )

        # --- Le solde de la carte n'a pas bouge d'un centime ---
        # / The card's balance did not move by a single cent.
        token_de_la_carte = Token.objects.get(
            wallet=self.wallet_ephemere, asset=self.asset_tlf
        )
        assert token_de_la_carte.value == SOLDE_CARTE_ANONYME_CENTIMES, (
            f"Le portefeuille a ete debite ({token_de_la_carte.value} au lieu de "
            f"{SOLDE_CARTE_ANONYME_CENTIMES}) alors qu'aucune adhesion ne pouvait etre "
            f"enregistree : le client paie pour rien."
        )

        # --- Aucune ligne de vente, aucune adhesion ---
        # / No sale line, no membership.
        from BaseBillet.models import LigneArticle, SaleOrigin

        assert not LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            pricesold__price=self.prix_adhesion,
        ).exists()
        assert not Membership.objects.filter(price=self.prix_adhesion).exists()

    def test_adhesion_payee_par_nfc_avec_identification_est_bien_enregistree(self):
        """
        Reglee par NFC AVEC identification : l'adhesion existe, le membre est declare au
        reseau, et la carte lui est rattachee.
        / Paid by NFC WITH identification: the membership exists, the member is declared to
          the network, and the card is attached to them.

        L'ORDRE EST CE QUE CE TEST PROTEGE : le debit s'appuie sur le portefeuille ephemere
        de la carte, et la fusion le DETACHE. Fusionner avant de debiter reviendrait a
        debiter un portefeuille qui n'est plus celui de la carte.
        / ORDER IS WHAT THIS TEST PROTECTS: the debit relies on the card's ephemeral wallet,
          and the merge DETACHES it.
        """
        wallet_fedow_du_user = Wallet.objects.create(
            uuid=uuid_module.uuid4(), origin=self.tenant, name="Wallet Fedow nfc ok"
        )
        api_fedow = _fabriquer_fedow_api_mock(wallet_fedow_du_user)

        with self._patcher_fedow(api_fedow):
            reponse = self._poster_adhesion_payee_par_nfc()

        assert reponse.status_code == 200, reponse.content.decode()[:400]

        adherent = TibilletUser.objects.get(email=self.email_adherent)

        # --- L'adhesion existe : c'est la reparation du bug ---
        # / The membership exists: that is the fix.
        assert Membership.objects.filter(
            user=adherent, price=self.prix_adhesion
        ).exists(), (
            "Le client a paye par carte et aucune adhesion n'a ete enregistree."
        )

        # --- Le membre est declare au reseau et la carte lui est rattachee ---
        # / The member is declared to the network and the card attached to them.
        assert api_fedow.wallet.get_or_create_wallet.called
        assert api_fedow.NFCcard.linkwallet_card_number.called
        assert adherent.wallet.uuid == wallet_fedow_du_user.uuid

        self.carte_anonyme.refresh_from_db()
        assert self.carte_anonyme.user == adherent
        assert self.carte_anonyme.wallet_ephemere is None

        # --- Le solde restant a suivi le membre : 66,00 € - 20,00 € = 46,00 € ---
        # Si la fusion etait passee AVANT le debit, le debit aurait porte sur un
        # portefeuille detache et ce montant serait faux.
        # / The remaining balance followed the member: €66.00 - €20.00 = €46.00.
        prix_en_centimes = int(round(self.prix_adhesion.prix * 100))
        token_du_membre = Token.objects.get(
            wallet=adherent.wallet, asset=self.asset_tlf
        )
        assert token_du_membre.value == (
            SOLDE_CARTE_ANONYME_CENTIMES - prix_en_centimes
        ), (
            f"Le membre porte {token_du_membre.value} centimes au lieu de "
            f"{SOLDE_CARTE_ANONYME_CENTIMES - prix_en_centimes} : le debit et la fusion se "
            f"sont marches dessus."
        )
