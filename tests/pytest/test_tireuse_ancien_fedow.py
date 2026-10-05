"""
Tests de la tireuse avec l'ancien Fedow : un tirage se paie comme au cashless de la
caisse, avec les monnaies locales d'abord, puis le reste sur l'ancien Fedow.
/ Tap tests with the old Fedow: a pour is paid like the register's cashless, local
currencies first, then the remainder on the old Fedow.

LOCALISATION : tests/pytest/test_tireuse_ancien_fedow.py

RÈGLE MÉTIER TESTÉE
1. Ordre : les monnaies locales d'abord (jetons cadeau TNF, puis monnaie locale TLF),
   puis le reste sur l'ancien Fedow (`_debiter_legacy` : il débite lui-même les TLF
   fédérés puis le FED, et rend le moyen : FED → `SF`, TLF → `LE`).
2. L'ancien Fedow n'est appelé que si la carte a un utilisateur ET que le lieu est
   relié. Carte anonyme ou lieu non relié : monnaies locales seules, aucun appel.
3. Au badge (`authorize`) : solde = monnaies locales + solde de l'ancien Fedow lu frais.
   Ancien Fedow injoignable : on continue avec les monnaies locales, sans refus.
   L'écran (`_lire_le_solde_de_la_carte`) dit le même solde que l'autorisation.
4. À la fin du service : lecture des soldes locaux, relecture du solde de l'ancien
   Fedow, répartition (locales d'abord, le reste sur l'ancien Fedow, plafonné à son
   solde lu). Le débit de l'ancien Fedow est un appel réseau : il se fait AVANT tout
   débit local (qui verrouille les jetons du client et du lieu), et donc avant
   `ouvrir_vente` et `encaisser_vente` (le verrou du lieu n'attend jamais le réseau).
   Ancien Fedow en échec ou solde lu insuffisant : on facture ce qui a été réellement
   débité, et UN SEUL avertissement dit le montant non facturé. L'échec du débit
   distant est journalisé en ERROR avec sa cause (il peut suivre un débit côté serveur).
5. La vente : UNE ligne (litres au prix du litre, D15) et un règlement par
   transaction débitée ; ce qui manque devient un article d'écart « reçu en moins ».
   Règlement local :
   `fedow_transaction_uuid`. Règlement de l'ancien Fedow : `reference_externe` = uuid
   de la transaction distante, `asset` = uuid de la monnaie distante.
/ Locals first, then the remainder on the old Fedow; old Fedow only for a card with a
user in a linked venue; authorize counts the old Fedow balance; remote debit before any
local debit, and before the sale is opened and settled; failure or short balance: bill
what was really debited, one warning, the failure logged as ERROR; one line and one
payment per debited transaction.

COMMENT CHAQUE TEST RETROUVE SA VENTE
La base est partagée avec le serveur de dev. Chaque test crée SA carte : il retrouve sa
vente par cette carte (`Vente.carte`). Chaque test qui lit une vente finit par
`verifier_egalites(vente)` (tests/pytest/fabriques_vente.py).
/ Each test creates ITS card and finds its sale through it; it ends with
verifier_egalites(vente).

SIMULATIONS
Les tests passent par les vraies routes de la tireuse (`authorize` puis `event`
`pour_end`), avec la clé API du terminal de la tireuse. Tout est marqué `django_db` :
la transaction est annulée à la fin (tests/PIEGES.md 13.1), rien ne reste en base de dev.
L'ancien Fedow (serveur distant) est TOUJOURS simulé : le lieu `lespass` y est relié en
dev, un vrai appel débiterait de vraies cartes.
- La lecture du solde (`lire_depensable_fed_frais`) et le débit (`_debiter_legacy`) sont
  simulés dans `laboutik.views`, leur module d'origine : la tireuse les importe au
  moment de l'appel, comme le reste des briques de la caisse.
- Garde réseau (fixture automatique) : les envois HTTP du client de l'ancien Fedow
  (`_get`, `_post`) échouent, et la liste des envois tentés doit être vide à la fin.
/ Real tap routes, rolled back. The old Fedow is ALWAYS faked (balance read and debit
faked in laboutik.views, where the tap imports them at call time); network guard.

CODE PARCOURU / CODE EXERCISED
- controlvanne/viewsets.py — TireuseViewSet.authorize, TireuseViewSet.event,
  _lire_le_solde_de_la_carte, _cloturer_session_et_facturer ;
- controlvanne/billing.py — facturer_tirage ;
- laboutik/views.py — lire_depensable_fed_frais, _debiter_legacy (réutilisés) ;
- BaseBillet/services_vente.py — le service de vente.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-C-tireuse-qr.md (§1 bis).

Lancer / Run : make test ARGS="tests/pytest/test_tireuse_ancien_fedow.py"
"""

import json
import logging
import uuid
from decimal import Decimal
from unittest import mock

import pytest
from django.test import Client as ClientHttpDjango
from django_tenants.utils import tenant_context

from fabriques_controlvanne import cle_api_de_la_tireuse
from fabriques_vente import verifier_egalites

# Nom de domaine du lieu de test partagé (le lieu « lespass » de la base de dev).
# / Domain of the shared test venue (the "lespass" venue of the dev database).
DOMAINE_DU_LIEU_PARTAGE = "lespass.tibillet.localhost"

# Code de devise d'une monnaie créée par le test, selon sa catégorie.
# / Currency code of a currency created by the test, by category.
CODE_DEVISE_PAR_CATEGORIE = {
    "TNF": "EUR",
    "TLF": "EUR",
}


# ---------------------------------------------------------------------------
# Garde réseau : aucun envoi réel vers l'ancien Fedow
# / Network guard: no real call to the old Fedow
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def aucun_envoi_reel_vers_l_ancien_fedow():
    """
    Pendant chaque test, les envois HTTP du client de l'ancien Fedow (`_get`, `_post`)
    échouent, et la liste des envois tentés doit être vide à la fin du test. Un test
    qui oublie de simuler l'ancien Fedow tombe donc au lieu de débiter une vraie carte.
    / During each test, the old Fedow client's HTTP calls fail, and no call may have
    been attempted at the end of the test.
    """
    envois_reseau_tentes = []

    def envoi_reseau_interdit(*arguments, **arguments_nommes):
        envois_reseau_tentes.append((arguments, arguments_nommes))
        raise AssertionError(
            "Appel réseau réel vers l'ancien Fedow interdit dans un test pytest."
        )

    with mock.patch("fedow_connect.fedow_api._post", side_effect=envoi_reseau_interdit):
        with mock.patch(
            "fedow_connect.fedow_api._get", side_effect=envoi_reseau_interdit
        ):
            yield

    assert envois_reseau_tentes == [], (
        f"Envois réseau réels tentés vers l'ancien Fedow : {envois_reseau_tentes}"
    )


# ---------------------------------------------------------------------------
# L'ancien Fedow simulé
# / The faked old Fedow
# ---------------------------------------------------------------------------


def transaction_distante(moyen, montant_en_centimes):
    """
    Une transaction de l'ancien Fedow, telle que `_debiter_legacy` la rend :
    (uuid de la monnaie distante, montant, moyen déjà résolu, uuid de la transaction).
    Les uuid sont des textes, comme dans la réponse JSON du serveur.
    / A remote transaction as returned by _debiter_legacy (uuids as text, like JSON).

    :param moyen: `PaymentMethod.LOCAL_EURO` (TLF fédérés) ou `PaymentMethod.STRIPE_FED`
    :param montant_en_centimes: int
    :return: tuple
    """
    uuid_de_la_monnaie_distante = str(uuid.uuid4())
    uuid_de_la_transaction_distante = str(uuid.uuid4())
    return (
        uuid_de_la_monnaie_distante,
        montant_en_centimes,
        moyen,
        uuid_de_la_transaction_distante,
    )


class AncienFedowSimule:
    """
    L'ancien Fedow, simulé : un solde dépensable, et le débit qu'il fait.
    / The old Fedow, faked: a spendable balance, and the debit it makes.

    - `lire_depensable_fed_frais(user)` rend `(solde, True)` : le lieu est relié et le
      serveur répond. Chaque lecture est notée dans `lectures`.
    - `debiter_legacy(user, montant, uuid_transaction)` : noté dans `debits`, puis
      - `erreur_au_debit` donnée : cette erreur est levée (réseau coupé) ;
      - montant demandé > solde : refus, comme le vrai serveur (aucun débit partiel) ;
      - sinon : le solde baisse, et les `transactions_rendues` sont rendues.
    - `journal_des_appels` : liste partagée où le débit note « débit ancien Fedow »
      (pour vérifier l'ordre des appels).
    / Faked old Fedow: balance read (noted), debit (noted; raises the given error,
    refuses over the balance like the real server, else returns the given transactions).
    """

    def __init__(
        self,
        solde_en_centimes,
        transactions_rendues=None,
        erreur_au_debit=None,
        journal_des_appels=None,
    ):
        self.solde_en_centimes = solde_en_centimes
        self.transactions_rendues = transactions_rendues or []
        self.erreur_au_debit = erreur_au_debit
        self.journal_des_appels = journal_des_appels
        self.lectures = []
        self.debits = []

    def lire_depensable_fed_frais(self, user):
        self.lectures.append(user)
        return self.solde_en_centimes, True

    def debiter_legacy(self, user, montant_centimes, uuid_transaction):
        self.debits.append((user, montant_centimes, uuid_transaction))
        if self.journal_des_appels is not None:
            self.journal_des_appels.append("débit ancien Fedow")
        if self.erreur_au_debit is not None:
            raise self.erreur_au_debit
        if montant_centimes > self.solde_en_centimes:
            raise Exception(
                "Ancien Fedow simulé : solde insuffisant, aucun débit partiel."
            )
        self.solde_en_centimes -= montant_centimes
        return self.transactions_rendues


def simuler_l_ancien_fedow(ancien_fedow_simule):
    """
    Branche l'ancien Fedow simulé là où la tireuse va le chercher : dans
    `laboutik.views`, au moment de l'appel.
    / Plugs the faked old Fedow where the tap looks for it: laboutik.views, at call time.

    :return: deux gestionnaires `mock.patch` à ouvrir ensemble (`with a, b:`)
    """
    lecture_simulee = mock.patch(
        "laboutik.views.lire_depensable_fed_frais",
        side_effect=ancien_fedow_simule.lire_depensable_fed_frais,
    )
    debit_simule = mock.patch(
        "laboutik.views._debiter_legacy",
        side_effect=ancien_fedow_simule.debiter_legacy,
    )
    return lecture_simulee, debit_simule


# ---------------------------------------------------------------------------
# Fabriques du test (recopiées de test_tireuse_ecrit_la_vente.py)
# / Test factories (copied from test_tireuse_ecrit_la_vente.py)
# ---------------------------------------------------------------------------


def _monnaie_du_lieu(lieu, categorie):
    """
    La monnaie de cette catégorie que la tireuse du lieu utilise.
    / The currency of this category that the venue's tap uses.

    On lit la monnaie avec LA MÊME requête que la tireuse
    (`AssetService.obtenir_assets_accessibles`, puis la première de la catégorie) : un
    solde posé sur une autre monnaie de la même catégorie serait invisible pour la
    tireuse (tests/PIEGES.md 9.97). Si le lieu n'en a aucune, le test en crée une : elle
    disparaît au rollback.
    / Same query as the tap (PIEGES 9.97); created if missing (rolled back).

    :param lieu: le `Client` (lieu) du test
    :param categorie: `Asset.TNF` ou `Asset.TLF`
    :return: l'`Asset`
    """
    from fedow_core.services import AssetService, WalletService

    with tenant_context(lieu):
        monnaie_vue_par_la_tireuse = (
            AssetService.obtenir_assets_accessibles(lieu)
            .filter(category=categorie)
            .first()
        )
        if monnaie_vue_par_la_tireuse is not None:
            return monnaie_vue_par_la_tireuse

        portefeuille_du_lieu = WalletService.get_or_create_wallet_tenant(lieu)
        monnaie_creee = AssetService.creer_asset(
            tenant=lieu,
            name=f"TEST monnaie tireuse ancien Fedow {categorie}",
            category=categorie,
            currency_code=CODE_DEVISE_PAR_CATEGORIE[categorie],
            wallet_origin=portefeuille_du_lieu,
        )
        return monnaie_creee


def _creer_une_tireuse(lieu, prix_du_litre_en_euros):
    """
    Une tireuse neuve, son fût (TVA 20 %) et la clé API de son terminal.
    / A fresh tap, its keg (20 % VAT) and its terminal's API key.

    La création de la tireuse fabrique aussi son point de vente et son terminal
    (signal `post_save`, controlvanne/signals.py). Le point de vente est caché, comme
    tout point de vente de test (tests/PIEGES.md 9.41).
    / Creating the tap also creates its POS and terminal (post_save signal).

    :param lieu: le `Client` (lieu) du test
    :param prix_du_litre_en_euros: texte, ex. "8.00"
    :return: (la `TireuseBec` relue en base, les en-têtes HTTP de sa clé API)
    """
    from BaseBillet.models import Price, Product, Tva
    from controlvanne.models import TireuseBec
    from laboutik.models import PointDeVente

    identifiant = uuid.uuid4().hex[:8]
    with tenant_context(lieu):
        # Le taux est unique en base : on réutilise celui qui existe déjà.
        # / The rate is unique in the database: reuse the existing one.
        tva_de_la_biere, _tva_creee = Tva.objects.get_or_create(
            tva_rate=Decimal("20.00")
        )
        fut = Product.objects.create(
            name=f"TEST fût tireuse ancien Fedow {identifiant}",
            categorie_article=Product.FUT,
            tva=tva_de_la_biere,
        )
        Price.objects.create(
            product=fut,
            name="Litre",
            prix=Decimal(prix_du_litre_en_euros),
            poids_mesure=True,
        )
        tireuse = TireuseBec.objects.create(
            nom_tireuse=f"TEST tireuse ancien Fedow {identifiant}",
            enabled=True,
            fut_actif=fut,
            reservoir_illimite=True,
        )
        tireuse.refresh_from_db()
        PointDeVente.objects.filter(pk=tireuse.point_de_vente_id).update(hidden=True)

    cle_api = cle_api_de_la_tireuse(lieu, tireuse)
    entetes_http = {"HTTP_AUTHORIZATION": f"Api-Key {cle_api}"}
    return tireuse, entetes_http


def _creer_une_carte(lieu, soldes_par_monnaie, avec_un_utilisateur):
    """
    Une carte NFC neuve, son portefeuille, et un solde par monnaie locale.
    / A fresh NFC card, its wallet, and one balance per local currency.

    Sans utilisateur, le portefeuille est celui de la carte (`wallet_ephemere`). Avec un
    utilisateur, c'est celui de l'utilisateur : la tireuse le prend en premier.
    / Without user: the card's own wallet. With a user: the user's wallet.

    :param lieu: le `Client` (lieu) du test
    :param soldes_par_monnaie: liste de couples (Asset, solde en centimes)
    :param avec_un_utilisateur: True pour relier la carte à un utilisateur
    :return: (la `CarteCashless`, son `Wallet`)
    """
    from AuthBillet.models import TibilletUser, Wallet
    from fedow_core.models import Token
    from QrcodeCashless.models import CarteCashless

    identifiant = uuid.uuid4().hex[:8].upper()
    with tenant_context(lieu):
        portefeuille = Wallet.objects.create(
            origin=lieu, name=f"TEST portefeuille tireuse ancien Fedow {identifiant}"
        )

        if avec_un_utilisateur:
            email = f"test+tireuseancienfedow{identifiant.lower()}@mock.test"
            utilisateur = TibilletUser.objects.create(
                email=email,
                username=email,
                first_name="Camille",
            )
            utilisateur.wallet = portefeuille
            utilisateur.save()
            carte = CarteCashless.objects.create(
                tag_id=identifiant,
                number=uuid.uuid4().hex[:8].upper(),
                user=utilisateur,
            )
        else:
            carte = CarteCashless.objects.create(
                tag_id=identifiant,
                number=uuid.uuid4().hex[:8].upper(),
                wallet_ephemere=portefeuille,
            )

        for monnaie, solde_en_centimes in soldes_par_monnaie:
            Token.objects.create(
                wallet=portefeuille, asset=monnaie, value=solde_en_centimes
            )

    return carte, portefeuille


def _poster(client_http, entetes_http, route, donnees):
    """
    POST JSON sur une route de la tireuse. / JSON POST to a tap route.
    """
    return client_http.post(
        f"/controlvanne/api/tireuse/{route}/",
        data=json.dumps(donnees),
        content_type="application/json",
        **entetes_http,
    )


def _badger(client_http, entetes_http, tireuse, carte):
    """
    Le badge de la carte sur la tireuse (`authorize`), comme le Raspberry Pi.
    / The card badge on the tap, like the Raspberry Pi.

    :return: la réponse de `authorize`
    """
    donnees_de_la_carte = {"tireuse_uuid": str(tireuse.uuid), "uid": carte.tag_id}
    reponse_du_badge = _poster(
        client_http, entetes_http, "authorize", donnees_de_la_carte
    )
    assert reponse_du_badge.status_code == 200, reponse_du_badge.content
    return reponse_du_badge


def _finir_le_service(client_http, entetes_http, tireuse, carte, volume_en_ml):
    """
    La fin de service (`event` `pour_end`) avec le volume servi.
    / The pour end with the served volume.

    :param volume_en_ml: texte, ex. "500.00"
    :return: la réponse du `pour_end`
    """
    donnees_de_la_carte = {"tireuse_uuid": str(tireuse.uuid), "uid": carte.tag_id}
    reponse_de_fin = _poster(
        client_http,
        entetes_http,
        "event",
        {**donnees_de_la_carte, "event_type": "pour_end", "volume_ml": volume_en_ml},
    )
    assert reponse_de_fin.status_code == 200, reponse_de_fin.content
    return reponse_de_fin


def _servir_un_tirage(client_http, entetes_http, tireuse, carte, volume_en_ml):
    """
    Un service complet, comme le Raspberry Pi : badge (`authorize`, qui doit
    autoriser), puis fin de service (`event` `pour_end`) avec le volume servi.
    / A full pour, like the Raspberry Pi: badge (must be authorized), then pour end.

    :param volume_en_ml: texte, ex. "500.00"
    :return: la réponse du `pour_end`
    """
    reponse_du_badge = _badger(client_http, entetes_http, tireuse, carte)
    assert reponse_du_badge.json()["authorized"] is True, reponse_du_badge.json()
    return _finir_le_service(client_http, entetes_http, tireuse, carte, volume_en_ml)


def _la_vente_du_tirage(carte):
    """
    LA vente de tireuse écrite pour cette carte : il doit y en avoir une et une seule.
    À appeler dans le lieu du test.
    / THE tap sale written for this card: exactly one. Call inside the test venue.
    """
    from BaseBillet.models import SaleOrigin
    from BaseBillet.models_vente import Vente

    ventes_de_la_carte = list(
        Vente.objects.filter(carte=carte, origine=SaleOrigin.TIREUSE)
    )
    assert len(ventes_de_la_carte) == 1, (
        f"Un tirage écrit une vente et une seule : {len(ventes_de_la_carte)} "
        f"trouvée(s) pour la carte {carte.tag_id}."
    )
    return ventes_de_la_carte[0]


def _debits_locaux_de_la_carte(carte):
    """
    Les transactions de vente `fedow_core` (Fedow local) de cette carte, dans l'ordre
    de création. / The local fedow_core sale transactions of this card, in order.
    """
    from fedow_core.models import Transaction

    return list(
        Transaction.objects.filter(card=carte, action=Transaction.SALE).order_by("id")
    )


def _avertissements_de_la_tireuse(caplog):
    """
    Les avertissements (niveau WARNING) écrits par le code de la tireuse
    (`controlvanne.*`). / The WARNING records written by the tap code.
    """
    avertissements = []
    for enregistrement in caplog.records:
        vient_de_la_tireuse = enregistrement.name.startswith("controlvanne")
        est_un_avertissement = enregistrement.levelno == logging.WARNING
        if vient_de_la_tireuse and est_un_avertissement:
            avertissements.append(enregistrement.getMessage())
    return avertissements


def _erreurs_de_la_tireuse(caplog):
    """
    Les erreurs (niveau ERROR) écrites par le code de la tireuse (`controlvanne.*`).
    / The ERROR records written by the tap code.
    """
    erreurs = []
    for enregistrement in caplog.records:
        vient_de_la_tireuse = enregistrement.name.startswith("controlvanne")
        est_une_erreur = enregistrement.levelno == logging.ERROR
        if vient_de_la_tireuse and est_une_erreur:
            erreurs.append(enregistrement.getMessage())
    return erreurs


# ---------------------------------------------------------------------------
# Tests sur la base partagée (transaction annulée à la fin de chaque test)
# / Tests on the shared database (transaction rolled back after each test)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tirage_locales_puis_ancien_fedow_une_vente(tenant):
    """
    50 cl à 8 €/L = 400, par une carte reliée à un utilisateur : 100 en jetons cadeau
    (TNF), 100 en monnaie locale (TLF), puis le reste (200) sur l'ancien Fedow, qui
    débite 150 en TLF fédérés et 50 en FED.
    - les monnaies locales passent d'abord (soldes à 0), puis `_debiter_legacy` est
      appelé UNE fois, avec l'utilisateur, 200, et l'identifiant de paiement du tirage ;
    - UNE vente : UNE ligne (0,500 L à 800, total 400, part en jetons 100), et
      4 règlements (un par transaction débitée) ;
    - règlements locaux : `fedow_transaction_uuid` de leur transaction `fedow_core` ;
    - règlements de l'ancien Fedow : `reference_externe` = uuid de la transaction
      distante, `asset` = uuid de la monnaie distante, moyens `LE` (TLF) et `SF` (FED),
      pas de `fedow_transaction_uuid` ;
    - la ligne ne porte ni moyen ni monnaie (Q-H2) : les règlements les portent.
    / 400 = 100 tokens + 100 local TLF + 200 old Fedow (150 federated TLF + 50 FED):
    locals first, one old Fedow debit of 200, one sale, one line, 4 payments.
    """
    from BaseBillet.models import PaymentMethod
    from fedow_core.models import Asset, Token

    jetons_cadeau = _monnaie_du_lieu(tenant, Asset.TNF)
    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, portefeuille = _creer_une_carte(
        tenant,
        [(jetons_cadeau, 100), (monnaie_locale, 100)],
        avec_un_utilisateur=True,
    )

    transaction_en_tlf_federes = transaction_distante(PaymentMethod.LOCAL_EURO, 150)
    transaction_en_fed = transaction_distante(PaymentMethod.STRIPE_FED, 50)
    ancien_fedow = AncienFedowSimule(
        solde_en_centimes=1000,
        transactions_rendues=[transaction_en_tlf_federes, transaction_en_fed],
    )
    lecture_simulee, debit_simule = simuler_l_ancien_fedow(ancien_fedow)
    with lecture_simulee, debit_simule:
        reponse = _servir_un_tirage(
            ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
            entetes_http,
            tireuse,
            carte,
            "500.00",
        )
    assert reponse.json()["montant_centimes"] == 400

    with tenant_context(tenant):
        # Les monnaies locales sont vidées d'abord.
        # / Local currencies are emptied first.
        assert Token.objects.get(wallet=portefeuille, asset=jetons_cadeau).value == 0
        assert Token.objects.get(wallet=portefeuille, asset=monnaie_locale).value == 0
        debits_locaux = _debits_locaux_de_la_carte(carte)
        assert len(debits_locaux) == 2

        vente = _la_vente_du_tirage(carte)

        # Puis UN débit sur l'ancien Fedow : le reste, 200, avec l'identifiant de
        # paiement du tirage (le même que sur la ligne).
        # / Then ONE old Fedow debit: the remainder, 200, with the pour's payment id.
        assert len(ancien_fedow.debits) == 1
        utilisateur_debite, montant_demande, uuid_de_paiement = ancien_fedow.debits[0]
        assert utilisateur_debite == carte.user
        assert montant_demande == 200
        assert vente.articles.get().uuid_transaction == uuid_de_paiement

        # La vente : 400 au catalogue, rien d'offert, net 400 (la part en jetons est
        # une vente ordinaire, D8 bis).
        # / The sale: 400 catalogue, nothing offered, net 400 (token part sold).
        assert vente.total_catalogue == 400
        assert vente.total_offert == 0
        assert vente.total_ttc == 400

        # 4 règlements : un par transaction débitée.
        # / 4 payments: one per debited transaction.
        reglements_lus = []
        for reglement in vente.reglements.all():
            reglements_lus.append(
                (
                    reglement.moyen,
                    reglement.montant,
                    str(reglement.asset),
                    reglement.fedow_transaction_uuid,
                    reglement.reference_externe or "",
                )
            )
        debit_en_jetons = debits_locaux[0]
        debit_en_monnaie_locale = debits_locaux[1]
        reglements_attendus = [
            (
                PaymentMethod.LOCAL_GIFT,
                100,
                str(jetons_cadeau.uuid),
                debit_en_jetons.uuid,
                "",
            ),
            (
                PaymentMethod.LOCAL_EURO,
                100,
                str(monnaie_locale.uuid),
                debit_en_monnaie_locale.uuid,
                "",
            ),
            (
                PaymentMethod.LOCAL_EURO,
                150,
                transaction_en_tlf_federes[0],
                None,
                transaction_en_tlf_federes[3],
            ),
            (
                PaymentMethod.STRIPE_FED,
                50,
                transaction_en_fed[0],
                None,
                transaction_en_fed[3],
            ),
        ]
        assert sorted(reglements_lus, key=str) == sorted(reglements_attendus, key=str)

        # UNE ligne : les litres servis au prix du litre, la part en jetons dedans.
        # / ONE line: litres served at the price per litre, token part included.
        ligne = vente.articles.get()
        assert ligne.qty == Decimal("0.500")
        assert ligne.amount == 800
        assert ligne.total_catalogue == 400
        assert ligne.part_en_jetons == 100
        assert ligne.payment_method is None
        assert ligne.asset is None

        verifier_egalites(vente)


@pytest.mark.django_db
def test_tirage_paye_entierement_par_l_ancien_fedow(tenant):
    """
    La carte (reliée à un utilisateur) n'a aucune monnaie locale. 50 cl à 8 €/L = 400,
    payés entièrement par l'ancien Fedow : 250 en TLF fédérés et 150 en FED.
    - le badge autorise le service sur le seul solde de l'ancien Fedow ;
    - aucun débit local ; `_debiter_legacy` appelé avec 400 ;
    - UNE vente de 400 : une ligne, et un règlement par transaction distante ;
    - la réponse du `pour_end` (statut 200) n'a PAS de clé `transaction_id` : elle ne
      porte que l'identifiant d'une transaction `fedow_core` locale, et il n'y en a
      aucune (le Raspberry Pi ne la lit que pour son journal).
    / No local currency: 400 paid entirely by the old Fedow (250 TLF + 150 FED); one
    line, one payment per remote transaction; no `transaction_id` in the response.
    """
    from BaseBillet.models import PaymentMethod

    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, _portefeuille = _creer_une_carte(tenant, [], avec_un_utilisateur=True)

    transaction_en_tlf_federes = transaction_distante(PaymentMethod.LOCAL_EURO, 250)
    transaction_en_fed = transaction_distante(PaymentMethod.STRIPE_FED, 150)
    ancien_fedow = AncienFedowSimule(
        solde_en_centimes=1000,
        transactions_rendues=[transaction_en_tlf_federes, transaction_en_fed],
    )
    lecture_simulee, debit_simule = simuler_l_ancien_fedow(ancien_fedow)
    with lecture_simulee, debit_simule:
        reponse = _servir_un_tirage(
            ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
            entetes_http,
            tireuse,
            carte,
            "500.00",
        )
    assert reponse.status_code == 200
    assert reponse.json()["montant_centimes"] == 400
    assert "transaction_id" not in reponse.json()

    with tenant_context(tenant):
        assert _debits_locaux_de_la_carte(carte) == []
        assert len(ancien_fedow.debits) == 1
        assert ancien_fedow.debits[0][1] == 400

        vente = _la_vente_du_tirage(carte)
        assert vente.total_catalogue == 400
        assert vente.total_offert == 0
        assert vente.total_ttc == 400

        reglements_lus = []
        for reglement in vente.reglements.all():
            reglements_lus.append(
                (
                    reglement.moyen,
                    reglement.montant,
                    str(reglement.asset),
                    reglement.fedow_transaction_uuid,
                    reglement.reference_externe,
                )
            )
        assert sorted(reglements_lus, key=str) == sorted(
            [
                (
                    PaymentMethod.LOCAL_EURO,
                    250,
                    transaction_en_tlf_federes[0],
                    None,
                    transaction_en_tlf_federes[3],
                ),
                (
                    PaymentMethod.STRIPE_FED,
                    150,
                    transaction_en_fed[0],
                    None,
                    transaction_en_fed[3],
                ),
            ],
            key=str,
        )

        ligne = vente.articles.get()
        assert ligne.total_catalogue == 400
        assert ligne.part_en_jetons == 0

        verifier_egalites(vente)


@pytest.mark.django_db
def test_carte_anonyme_n_appelle_jamais_l_ancien_fedow(tenant):
    """
    Témoin. Carte ANONYME (sans utilisateur), 300 en monnaie locale, et le Raspberry Pi
    annonce 50 cl à 8 €/L (400) : il reste 100 à payer. L'ancien Fedow ne débite que le
    portefeuille d'un utilisateur : ni lecture ni débit distants, ni au badge ni à la
    fin. On facture les monnaies locales seules (300).
    / Witness. Anonymous card: no remote read nor debit; locals only (300).
    """
    from BaseBillet.models import PaymentMethod
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, _portefeuille = _creer_une_carte(
        tenant, [(monnaie_locale, 300)], avec_un_utilisateur=False
    )

    ancien_fedow = AncienFedowSimule(
        solde_en_centimes=1000,
        transactions_rendues=[transaction_distante(PaymentMethod.STRIPE_FED, 100)],
    )
    lecture_simulee, debit_simule = simuler_l_ancien_fedow(ancien_fedow)
    with lecture_simulee, debit_simule:
        reponse = _servir_un_tirage(
            ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
            entetes_http,
            tireuse,
            carte,
            "500.00",
        )
    assert reponse.json()["montant_centimes"] == 300

    assert ancien_fedow.lectures == []
    assert ancien_fedow.debits == []

    with tenant_context(tenant):
        vente = _la_vente_du_tirage(carte)
        assert vente.total_catalogue == 300
        reglement = vente.reglements.get()
        assert reglement.moyen == PaymentMethod.LOCAL_EURO
        assert reglement.montant == 300
        assert not reglement.reference_externe

        verifier_egalites(vente)


@pytest.mark.django_db
def test_lieu_non_relie_n_appelle_jamais_l_ancien_fedow(tenant):
    """
    Témoin. Le lieu n'est pas relié à l'ancien Fedow (`can_fedow()` faux). Carte reliée
    à un utilisateur, 300 en monnaie locale, 50 cl à 8 €/L (400) : il reste 100 à payer.
    La vraie lecture (`lire_depensable_fed_frais`) répond « indisponible » sans créer de
    client Fedow ; aucun débit distant n'est demandé. On facture les locales seules.
    / Witness. Venue not linked: no Fedow client created, no remote debit; locals only.
    """
    from BaseBillet.models import PaymentMethod
    from fedow_connect.models import FedowConfig
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, _portefeuille = _creer_une_carte(
        tenant, [(monnaie_locale, 300)], avec_un_utilisateur=True
    )

    client_fedow_interdit = mock.MagicMock(
        side_effect=AssertionError("Aucun client de l'ancien Fedow ne doit être créé.")
    )
    debit_interdit = mock.MagicMock(
        side_effect=AssertionError("Aucun débit de l'ancien Fedow ne doit être demandé.")
    )
    with mock.patch.object(FedowConfig, "can_fedow", return_value=False):
        with mock.patch("laboutik.views.FedowAPI", new=client_fedow_interdit):
            with mock.patch("laboutik.views._debiter_legacy", new=debit_interdit):
                reponse = _servir_un_tirage(
                    ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
                    entetes_http,
                    tireuse,
                    carte,
                    "500.00",
                )
    assert reponse.json()["montant_centimes"] == 300

    assert client_fedow_interdit.called is False
    assert debit_interdit.called is False

    with tenant_context(tenant):
        vente = _la_vente_du_tirage(carte)
        assert vente.total_catalogue == 300
        reglement = vente.reglements.get()
        assert reglement.moyen == PaymentMethod.LOCAL_EURO
        assert reglement.montant == 300

        verifier_egalites(vente)


@pytest.mark.django_db
def test_authorize_compte_le_solde_de_l_ancien_fedow(tenant):
    """
    Carte reliée à un utilisateur : 100 en monnaie locale, 300 sur l'ancien Fedow. Au
    badge, le solde est 400 (les deux) ; le volume autorisé à 8 €/L est 500 ml ; l'écran
    de la tireuse affiche 4,00 € (2 verres de 25 cl). Le solde de l'ancien Fedow est lu
    pour l'utilisateur de la carte.
    / Badge: balance = 100 local + 300 old Fedow = 400; 500 ml allowed; screen 4.00.
    """
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, _portefeuille = _creer_une_carte(
        tenant, [(monnaie_locale, 100)], avec_un_utilisateur=True
    )

    messages_envoyes_a_l_ecran = []

    def capturer_le_message(uuid_de_la_tireuse, message, uuid_du_lieu):
        messages_envoyes_a_l_ecran.append(message)

    ancien_fedow = AncienFedowSimule(solde_en_centimes=300)
    lecture_simulee, debit_simule = simuler_l_ancien_fedow(ancien_fedow)
    with lecture_simulee, debit_simule:
        with mock.patch(
            "controlvanne.viewsets.pousser_aux_kiosks", side_effect=capturer_le_message
        ):
            reponse_du_badge = _badger(
                ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
                entetes_http,
                tireuse,
                carte,
            )

    reponse_lue = reponse_du_badge.json()
    assert reponse_lue["authorized"] is True, reponse_lue
    assert reponse_lue["solde_centimes"] == 400
    assert reponse_lue["allowed_ml"] == 500.0

    message_du_badge = messages_envoyes_a_l_ecran[-1]
    assert message_du_badge["balance"] == "4.00"
    assert message_du_badge["nombre_verres"] == 2

    with tenant_context(tenant):
        assert carte.user in ancien_fedow.lectures
    assert ancien_fedow.debits == []


@pytest.mark.django_db
def test_authorize_ancien_fedow_injoignable_continue_avec_les_locales(tenant):
    """
    Carte reliée à un utilisateur, 300 en monnaie locale ; le lieu est relié, mais
    l'ancien Fedow ne répond pas (création du client en erreur réseau). Au badge, la
    vraie lecture (`lire_depensable_fed_frais`) est tentée, dégrade en silence, et le
    service est autorisé sur les monnaies locales seules : solde 300, 375 ml à 8 €/L.
    Jamais de refus pour ça.
    / Old Fedow unreachable at badge: the read is attempted, degrades, and the pour is
    authorized on local currencies only (300, 375 ml). Never a refusal for that.
    """
    from fedow_connect.models import FedowConfig
    from fedow_core.models import Asset
    from laboutik.views import lire_depensable_fed_frais

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, _portefeuille = _creer_une_carte(
        tenant, [(monnaie_locale, 300)], avec_un_utilisateur=True
    )

    client_fedow_injoignable = mock.MagicMock(
        side_effect=ConnectionError("Ancien Fedow simulé : injoignable.")
    )
    debit_interdit = mock.MagicMock(
        side_effect=AssertionError("Aucun débit de l'ancien Fedow au badge.")
    )
    with mock.patch.object(FedowConfig, "can_fedow", return_value=True):
        with mock.patch("laboutik.views.FedowAPI", new=client_fedow_injoignable):
            with mock.patch(
                "laboutik.views.lire_depensable_fed_frais",
                wraps=lire_depensable_fed_frais,
            ) as lecture_espionnee:
                with mock.patch("laboutik.views._debiter_legacy", new=debit_interdit):
                    reponse_du_badge = _badger(
                        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
                        entetes_http,
                        tireuse,
                        carte,
                    )

    reponse_lue = reponse_du_badge.json()
    assert reponse_lue["authorized"] is True, reponse_lue
    assert reponse_lue["solde_centimes"] == 300
    assert reponse_lue["allowed_ml"] == 375.0

    # La lecture de l'ancien Fedow a bien été tentée, pour l'utilisateur de la carte.
    # / The old Fedow read was attempted, for the card's user.
    assert lecture_espionnee.called is True
    with tenant_context(tenant):
        utilisateurs_lus = []
        for appel in lecture_espionnee.call_args_list:
            if appel.args:
                utilisateurs_lus.append(appel.args[0])
            else:
                utilisateurs_lus.append(appel.kwargs.get("user"))
        assert carte.user in utilisateurs_lus
    assert debit_interdit.called is False


@pytest.mark.django_db
def test_fin_de_service_ancien_fedow_en_echec_facture_les_locales(tenant, caplog):
    """
    Carte reliée à un utilisateur : 100 en monnaie locale, 1000 sur l'ancien Fedow. Le
    badge autorise 50 cl à 8 €/L (400). À la fin du service, le débit distant (300) est
    tenté puis échoue (réseau coupé). La bière est servie : on encaisse ce qui a été
    réellement débité (les 100 locaux) ; la ligne garde son prix (400) et un article
    « Écart d'encaissement — reçu en moins » porte −300. La vente tient ses égalités ;
    UN SEUL avertissement de la tireuse dit le montant non facturé (300).
    / Remote debit fails at pour end: collect the 100 local, line 400 + gap −300, the
    sale holds, one warning with the unbilled amount (300).
    """
    from BaseBillet.models import PaymentMethod
    from fedow_core.models import Asset, Token

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, portefeuille = _creer_une_carte(
        tenant, [(monnaie_locale, 100)], avec_un_utilisateur=True
    )

    ancien_fedow = AncienFedowSimule(
        solde_en_centimes=1000,
        erreur_au_debit=ConnectionError("Ancien Fedow simulé : réseau coupé."),
    )
    lecture_simulee, debit_simule = simuler_l_ancien_fedow(ancien_fedow)
    with lecture_simulee, debit_simule:
        with caplog.at_level(logging.WARNING):
            reponse = _servir_un_tirage(
                ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
                entetes_http,
                tireuse,
                carte,
                "500.00",
            )
    assert reponse.json()["montant_centimes"] == 100

    # Le débit distant a été tenté pour le reste (300).
    # / The remote debit was attempted for the remainder (300).
    assert len(ancien_fedow.debits) == 1
    assert ancien_fedow.debits[0][1] == 300

    avertissements = _avertissements_de_la_tireuse(caplog)
    assert len(avertissements) == 1, avertissements
    assert "300" in avertissements[0]

    with tenant_context(tenant):
        assert Token.objects.get(wallet=portefeuille, asset=monnaie_locale).value == 0

        vente = _la_vente_du_tirage(carte)
        assert vente.total_catalogue == 100
        reglement = vente.reglements.get()
        assert reglement.moyen == PaymentMethod.LOCAL_EURO
        assert reglement.montant == 100
        assert not reglement.reference_externe
        totaux_des_articles = []
        for article in vente.articles.all():
            totaux_des_articles.append(article.total_ttc)
        assert sorted(totaux_des_articles) == [-300, 400]

        verifier_egalites(vente)


@pytest.mark.django_db
def test_fin_de_service_solde_distant_insuffisant_debite_ce_qu_il_a(tenant, caplog):
    """
    Carte reliée à un utilisateur : 100 en monnaie locale, 300 sur l'ancien Fedow au
    badge (400 autorisés). Entre le badge et la fin, le solde distant tombe à 120. À la
    fin (400) : 100 répartis sur la monnaie locale, relecture du solde distant (120) et
    débit distant de `min(120, 300)` = 120 (en FED), puis le débit local de 100. On
    facture 220 ; la vente tient ; UN SEUL avertissement dit le montant non facturé (180).
    / Remote balance drops to 120: debit 120 (not the whole 300), bill 220, one warning
    with the unbilled amount (180).
    """
    from BaseBillet.models import PaymentMethod
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, _portefeuille = _creer_une_carte(
        tenant, [(monnaie_locale, 100)], avec_un_utilisateur=True
    )

    transaction_en_fed = transaction_distante(PaymentMethod.STRIPE_FED, 120)
    ancien_fedow = AncienFedowSimule(
        solde_en_centimes=300,
        transactions_rendues=[transaction_en_fed],
    )
    client_http = ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE)
    lecture_simulee, debit_simule = simuler_l_ancien_fedow(ancien_fedow)
    with lecture_simulee, debit_simule:
        reponse_du_badge = _badger(client_http, entetes_http, tireuse, carte)
        assert reponse_du_badge.json()["authorized"] is True
        assert reponse_du_badge.json()["solde_centimes"] == 400

        # Le solde distant baisse entre le badge et la fin du service.
        # / The remote balance drops between the badge and the pour end.
        ancien_fedow.solde_en_centimes = 120

        with caplog.at_level(logging.WARNING):
            reponse = _finir_le_service(
                client_http, entetes_http, tireuse, carte, "500.00"
            )
    assert reponse.json()["montant_centimes"] == 220

    assert len(ancien_fedow.debits) == 1
    assert ancien_fedow.debits[0][1] == 120

    avertissements = _avertissements_de_la_tireuse(caplog)
    assert len(avertissements) == 1, avertissements
    assert "180" in avertissements[0]

    with tenant_context(tenant):
        vente = _la_vente_du_tirage(carte)
        assert vente.total_catalogue == 220

        reglement_distant = vente.reglements.get(moyen=PaymentMethod.STRIPE_FED)
        assert reglement_distant.montant == 120
        assert reglement_distant.reference_externe == transaction_en_fed[3]
        reglement_local = vente.reglements.get(moyen=PaymentMethod.LOCAL_EURO)
        assert reglement_local.montant == 100

        verifier_egalites(vente)


@pytest.mark.django_db
def test_ecran_et_authorize_meme_solde(tenant):
    """
    Carte reliée à un utilisateur : 100 en monnaie locale, 300 sur l'ancien Fedow. Le
    solde lu par l'écran de la tireuse quand le cache est vide
    (`_lire_le_solde_de_la_carte`) vaut le solde de l'autorisation : 400, ancien Fedow
    compris.
    / The screen balance (empty cache) equals the authorize balance: 400.
    """
    from controlvanne.viewsets import _lire_le_solde_de_la_carte
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, _portefeuille = _creer_une_carte(
        tenant, [(monnaie_locale, 100)], avec_un_utilisateur=True
    )

    ancien_fedow = AncienFedowSimule(solde_en_centimes=300)
    lecture_simulee, debit_simule = simuler_l_ancien_fedow(ancien_fedow)
    with lecture_simulee, debit_simule:
        reponse_du_badge = _badger(
            ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
            entetes_http,
            tireuse,
            carte,
        )
        solde_de_l_autorisation = reponse_du_badge.json()["solde_centimes"]

        with tenant_context(tenant):
            solde_de_l_ecran = _lire_le_solde_de_la_carte(carte)

    assert solde_de_l_autorisation == 400
    assert solde_de_l_ecran == solde_de_l_autorisation


@pytest.mark.django_db
def test_debit_distant_hors_du_verrou_du_lieu(tenant):
    """
    Carte reliée à un utilisateur : 100 en monnaie locale, 1000 sur l'ancien Fedow, 50 cl
    à 8 €/L (400). Le débit distant (300) est un appel réseau : il se fait AVANT
    l'ouverture de la vente (`ouvrir_vente`) et AVANT son encaissement
    (`encaisser_vente`, qui prend le verrou du lieu jusqu'à la fin de la transaction).
    On vérifie l'ordre des appels.
    `ouvrir_vente` et `encaisser_vente` sont espionnés à leur source
    (`BaseBillet.services_vente`) : la tireuse les importe au moment de l'appel.
    / The remote debit happens BEFORE the sale is opened and settled (venue lock).
    """
    from BaseBillet import services_vente
    from BaseBillet.models import PaymentMethod
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, _portefeuille = _creer_une_carte(
        tenant, [(monnaie_locale, 100)], avec_un_utilisateur=True
    )

    journal_des_appels = []
    vraie_ouverture = services_vente.ouvrir_vente
    vrai_encaissement = services_vente.encaisser_vente

    def ouverture_notee(*arguments, **arguments_nommes):
        journal_des_appels.append("ouvrir_vente")
        return vraie_ouverture(*arguments, **arguments_nommes)

    def encaissement_note(*arguments, **arguments_nommes):
        journal_des_appels.append("encaisser_vente")
        return vrai_encaissement(*arguments, **arguments_nommes)

    ancien_fedow = AncienFedowSimule(
        solde_en_centimes=1000,
        transactions_rendues=[transaction_distante(PaymentMethod.STRIPE_FED, 300)],
        journal_des_appels=journal_des_appels,
    )
    lecture_simulee, debit_simule = simuler_l_ancien_fedow(ancien_fedow)
    with lecture_simulee, debit_simule:
        with mock.patch(
            "BaseBillet.services_vente.ouvrir_vente", side_effect=ouverture_notee
        ):
            with mock.patch(
                "BaseBillet.services_vente.encaisser_vente",
                side_effect=encaissement_note,
            ):
                reponse = _servir_un_tirage(
                    ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
                    entetes_http,
                    tireuse,
                    carte,
                    "500.00",
                )
    assert reponse.json()["montant_centimes"] == 400

    assert journal_des_appels == [
        "débit ancien Fedow",
        "ouvrir_vente",
        "encaisser_vente",
    ], journal_des_appels

    with tenant_context(tenant):
        vente = _la_vente_du_tirage(carte)
        verifier_egalites(vente)


@pytest.mark.django_db
def test_ancien_fedow_debite_avant_les_monnaies_locales(tenant):
    """
    50 cl à 8 €/L = 400, par une carte reliée à un utilisateur : 100 en jetons cadeau
    (TNF), 100 en monnaie locale (TLF), 200 sur l'ancien Fedow.
    Le débit de l'ancien Fedow (`_debiter_legacy`, appel réseau) passe AVANT tout débit
    local (`TransactionService.creer_vente`, qui verrouille les jetons du client et du
    lieu) : pendant l'appel réseau, aucun jeton n'est verrouillé, et les autres ventes
    cashless du lieu n'attendent pas. Les montants ne changent pas : 100 + 100 en local,
    200 sur l'ancien Fedow.
    `creer_vente` est espionné à sa source (`fedow_core.services.TransactionService`) :
    la tireuse l'importe au moment de l'appel. L'espion (`wraps`) note chaque débit
    local, puis appelle le vrai débit.
    / The old Fedow debit (network) happens BEFORE any local debit (which locks the
    client's and the venue's tokens). Same amounts: 100 + 100 local, 200 old Fedow.
    """
    from BaseBillet.models import PaymentMethod
    from fedow_core.models import Asset, Token
    from fedow_core.services import TransactionService

    jetons_cadeau = _monnaie_du_lieu(tenant, Asset.TNF)
    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, portefeuille = _creer_une_carte(
        tenant,
        [(jetons_cadeau, 100), (monnaie_locale, 100)],
        avec_un_utilisateur=True,
    )

    journal_des_appels = []
    vrai_debit_local = TransactionService.creer_vente

    def debit_local_note(*arguments, **arguments_nommes):
        journal_des_appels.append("débit local")
        return vrai_debit_local(*arguments, **arguments_nommes)

    ancien_fedow = AncienFedowSimule(
        solde_en_centimes=1000,
        transactions_rendues=[transaction_distante(PaymentMethod.STRIPE_FED, 200)],
        journal_des_appels=journal_des_appels,
    )
    lecture_simulee, debit_simule = simuler_l_ancien_fedow(ancien_fedow)
    with lecture_simulee, debit_simule:
        with mock.patch.object(
            TransactionService, "creer_vente", wraps=debit_local_note
        ) as espion_du_debit_local:
            reponse = _servir_un_tirage(
                ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
                entetes_http,
                tireuse,
                carte,
                "500.00",
            )
    assert reponse.json()["montant_centimes"] == 400

    # L'ordre : l'ancien Fedow d'abord, puis les deux débits locaux.
    # / The order: the old Fedow first, then the two local debits.
    assert journal_des_appels == [
        "débit ancien Fedow",
        "débit local",
        "débit local",
    ], journal_des_appels

    # Les montants : 200 demandés à l'ancien Fedow, 100 en jetons puis 100 en TLF.
    # / The amounts: 200 asked from the old Fedow, 100 tokens then 100 TLF.
    assert len(ancien_fedow.debits) == 1
    assert ancien_fedow.debits[0][1] == 200
    debits_locaux_demandes = []
    for appel in espion_du_debit_local.call_args_list:
        debits_locaux_demandes.append(
            (appel.kwargs["asset"], appel.kwargs["montant_en_centimes"])
        )
    assert debits_locaux_demandes == [(jetons_cadeau, 100), (monnaie_locale, 100)]

    with tenant_context(tenant):
        assert Token.objects.get(wallet=portefeuille, asset=jetons_cadeau).value == 0
        assert Token.objects.get(wallet=portefeuille, asset=monnaie_locale).value == 0

        # La part en jetons est une vente ordinaire (D8 bis) : rien d'offert.
        # / The token part is an ordinary sale: nothing offered.
        vente = _la_vente_du_tirage(carte)
        assert vente.total_catalogue == 400
        assert vente.total_offert == 0
        assert vente.total_ttc == 400
        assert vente.reglements.count() == 3

        verifier_egalites(vente)


@pytest.mark.django_db
def test_echec_de_l_ancien_fedow_journalise_en_erreur_avec_la_cause(tenant, caplog):
    """
    Carte reliée à un utilisateur : 100 en monnaie locale, 1000 sur l'ancien Fedow,
    50 cl à 8 €/L (400). Le débit distant (300) lève une erreur. Cette erreur peut
    arriver APRÈS un débit côté serveur (réponse perdue) : elle est journalisée en
    ERROR, avec sa cause, la carte et le montant demandé. L'avertissement « montant non
    facturé » reste le seul WARNING.
    / The remote debit (300) raises. It may come after a server-side debit: logged as
    ERROR with the cause, the card and the requested amount. The single WARNING stays.
    """
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, _portefeuille = _creer_une_carte(
        tenant, [(monnaie_locale, 100)], avec_un_utilisateur=True
    )

    cause_de_l_echec = "Ancien Fedow simulé : réponse perdue après le débit."
    ancien_fedow = AncienFedowSimule(
        solde_en_centimes=1000,
        erreur_au_debit=ConnectionError(cause_de_l_echec),
    )
    lecture_simulee, debit_simule = simuler_l_ancien_fedow(ancien_fedow)
    with lecture_simulee, debit_simule:
        with caplog.at_level(logging.INFO):
            reponse = _servir_un_tirage(
                ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
                entetes_http,
                tireuse,
                carte,
                "500.00",
            )
    assert reponse.json()["montant_centimes"] == 100

    erreurs = _erreurs_de_la_tireuse(caplog)
    assert len(erreurs) == 1, erreurs
    message_d_erreur = erreurs[0]
    assert cause_de_l_echec in message_d_erreur
    assert carte.tag_id in message_d_erreur
    assert "300" in message_d_erreur

    avertissements = _avertissements_de_la_tireuse(caplog)
    assert len(avertissements) == 1, avertissements
