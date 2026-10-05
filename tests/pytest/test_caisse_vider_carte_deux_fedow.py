"""
Tests de la caisse : vider la carte d'un client sur les DEUX Fedow (le Fedow local et
l'ancien Fedow), et écrire la vente du vidage.
/ Register tests: emptying a customer card on BOTH Fedow servers (the local Fedow and
the old Fedow), and writing the card-emptying sale.

LOCALISATION : tests/pytest/test_caisse_vider_carte_deux_fedow.py

RÈGLE MÉTIER TESTÉE (fiche B §5, validée par le mainteneur)
Le système est hybride : la carte d'un client peut porter de l'argent sur le Fedow
local (`fedow_core`, en base) et sur l'ancien Fedow (serveur distant). Vider la carte
à la caisse les vide TOUS LES DEUX, en un seul geste :
1. l'ancien Fedow d'abord (`POST card/refund`), hors de la transaction de base ;
   « vider et délier » envoie `VOID`, sinon `REFUND` ; la carte primaire envoyée est
   celle du caissier, la même que pour le Fedow local ;
2. l'ancien Fedow échoue : rien n'est fait, la caisse affiche une erreur claire ;
   l'ancien Fedow réussit puis le vidage local échoue : la caisse journalise un
   INCIDENT (montant, carte, uuid des transactions distantes) et affiche une erreur ;
3. les espèces rendues = la monnaie locale du lieu + la monnaie fédérée (FED), sur les
   deux Fedow ; les jetons cadeau sont repris sur les deux Fedow, sans argent rendu ;
4. une vente `VIDAGE_CARTE` : un règlement POSITIF par transaction de remboursement
   d'argent (monnaie locale `LE`, monnaie fédérée `SF` ; transaction locale →
   `fedow_transaction_uuid`, transaction distante → `reference_externe`), puis un
   règlement ESPÈCES de moins le total. Des jetons perdus annulent la dette du lieu
   (D8 bis) : par transaction de jetons repris, un règlement « jetons » (LG) positif
   (mêmes champs) et un article « Jetons cadeau repris au vidage » du même montant,
   hors chiffre d'affaires, TVA 0, sans carte. Une carte qui n'a que des jetons écrit
   aussi sa vente ;
5. carte inconnue de l'ancien Fedow, ou lieu non relié à l'ancien Fedow : vidage local
   seul, comme aujourd'hui ;
6. aucune ligne « Refund » sans vente n'est écrite : la vente `VIDAGE_CARTE` les
   remplace (D12) ;
7. l'aperçu, l'écran de succès et le reçu imprimé sont SÉPARÉS par Fedow et détaillés
   (une partie « Fedow local », une partie « ancien Fedow », une ligne par monnaie, les
   jetons cadeau affichés « repris, sans argent »), puis le total rendu en espèces.
   L'aperçu lit le solde de l'ancien Fedow sans rien débiter. Le reçu ne croit jamais
   les montants postés par le navigateur : il relit chaque transaction.
/ One gesture empties both Fedow servers: the old one first, then the local one. Cash
given back = local currency + FED on both; gift tokens taken back with no money. One
`VIDAGE_CARTE` sale: one positive payment per money refund, then minus the total in
cash; gift tokens write an LG payment and a "taken back" item (D8 bis). Unknown card or
venue not linked: local only.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-B-caisse.md (§5, « Vider une
carte sur les DEUX Fedow » et « Décisions du mainteneur »).

L'ANCIEN FEDOW EST SIMULÉ, JAMAIS APPELÉ
Aucun test n'appelle le vrai serveur : une garde (fixture automatique) fait échouer tout
envoi réseau par le client Fedow (`fedow_connect.fedow_api._post` / `_get`).
Deux niveaux de simulation :
- la vue de la caisse reçoit un faux client `FedowAPI` (même méthode que les tests du
  paiement en monnaie du réseau, test_caisse_ecrit_la_vente.py). Ce faux client répond
  comme le client de LaBoutik V1 (../LaBoutik/fedow_connect/fedow_api.py, `refund`) :
  * `NFCcard.retrieve(tag_id)` : la carte connue de l'ancien Fedow, ou
    `CarteInconnueDeFedow` (réponse 404) ; `NFCcard.card_tag_id_retrieve` suit ;
  * `NFCcard.refund(user_card_firstTagId=…, primary_card_fisrtTagId=…, void=…)` :
    un dict `serialized_card`, `before_refund_serialized_wallet` (les jetons avant le
    vidage, avec leur catégorie), `serialized_transactions` (une transaction REFUND
    par jeton repris, sans fiche de monnaie, comme le vrai serveur) ;
  * `asset.retrieve(uuid)` : la fiche d'une monnaie distante, avec sa catégorie
    (« TLF » monnaie locale du lieu, « TNF » jetons cadeau, « FED » monnaie fédérée) ;
- le client lui-même (`NFCcardFedow.refund`) est testé contre un faux envoi réseau
  (`_post` simulé) : la route `card/refund`, l'action `VID` ou `RFD`, la réponse 205.
/ The old Fedow is faked, never called: a guard fails any real network call.

COMMENT CHAQUE TEST RETROUVE SA VENTE
La base est partagée avec le serveur de dev : chaque test crée sa propre carte client, et
retrouve la vente du vidage par cette carte (`Vente.carte`, fiche B §1 : « `carte` quand
elle est connue »). Chaque test finit par `verifier_egalites(vente)` quand il lit une vente.
/ Each test creates its own customer card and finds the sale through it.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin (tests/PIEGES.md
13.1). La caisse est activée par `configuration_modifiee()`, jamais enregistrée
(tests/PIEGES.md 13.22). Celery est simulé (tests/PIEGES.md 13.4). Le lieu est dit
« relié » ou « non relié » à l'ancien Fedow par `FedowConfig.can_fedow`, simulé.

Lancer / Run : make test ARGS="tests/pytest/test_caisse_vider_carte_deux_fedow.py"
"""

import inspect
import logging
import uuid
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.test import override_settings
from django.utils import timezone
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from BaseBillet.models import LigneArticle, PaymentMethod
from BaseBillet.models_vente import Vente
from BaseBillet.services_vente import (
    NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE,
    EgaliteDeVenteRompue,
)
from BaseBillet.templatetags.billet_filters import cents_to_euros
from fabriques_panier import (
    configuration_modifiee,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_vente import verifier_egalites
from fedow_connect import fedow_api
from fedow_connect.fedow_api import CarteInconnueDeFedow, NFCcardFedow
from fedow_connect.models import FedowConfig
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import WalletService
from laboutik.models import CartePrimaire
from laboutik.printing.escpos_builder import build_escpos_from_ticket_data
from laboutik.printing.sunmi_inner import ticket_data_to_json_commands
from QrcodeCashless.models import CarteCashless
from test_caracterisation_caisse import creer_un_point_de_vente
from test_caracterisation_en_ligne import creer_un_administrateur_du_lieu

pytestmark = pytest.mark.django_db

# Adresse du vidage de carte à la caisse (laboutik/urls.py, PaiementViewSet.vider_carte).
# / Card-emptying address at the register.
URL_DU_VIDAGE_DE_CARTE = "/laboutik/paiement/vider_carte/"

# Début du nom de tout ce que ces tests créent.
# / Prefix of everything these tests create.
PREFIXE_DES_TESTS = "TEST_vider_carte_deux_fedow"

# La signature de l'envoi réseau du client Fedow, lue AVANT toute simulation : elle sert
# à relire les arguments d'un envoi simulé (chemin, données), qu'ils soient passés par
# position ou par nom.
# / The Fedow client's network-send signature, read BEFORE any fake: used to read back
# the arguments of a faked send, whether passed by position or by name.
SIGNATURE_DE_L_ENVOI_A_FEDOW = inspect.signature(fedow_api._post)


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture(autouse=True)
def aucun_appel_reseau_vers_l_ancien_fedow():
    """
    Garde : aucun test de ce fichier n'appelle le vrai ancien Fedow.
    Tout envoi réseau du client Fedow (`_post`, `_get`) échoue ici, et la liste des
    envois tentés doit être vide à la fin du test. Un test qui simule lui-même `_post`
    (le test du client) remplace cette garde le temps de son bloc `with`.
    / Guard: no test calls the real old Fedow. Any network send fails, and the list of
    attempted sends must be empty at the end.
    """
    envois_reseau_tentes = []

    def envoi_reseau_interdit(*arguments, **arguments_nommes):
        envois_reseau_tentes.append((arguments, arguments_nommes))
        raise AssertionError(
            "Appel réseau réel vers l'ancien Fedow interdit dans un test pytest."
        )

    with patch("fedow_connect.fedow_api._post", side_effect=envoi_reseau_interdit):
        with patch("fedow_connect.fedow_api._get", side_effect=envoi_reseau_interdit):
            yield

    assert envois_reseau_tentes == [], (
        f"Envois réseau réels tentés vers l'ancien Fedow : {envois_reseau_tentes}"
    )


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, caisse activée, avec Celery simulé pendant tout le test.
    / The `lespass` venue, register switched on, with Celery faked for the whole test.

    La caisse n'est accessible que si le module caisse (et donc le module monnaie
    locale) est actif. On l'active EN MÉMOIRE : `configuration_modifiee()` ne sauve
    jamais la `Configuration`, dont le cache est partagé avec le serveur live.
    / The register needs its module on. It is switched on in memory only.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    taches_demandees=taches_demandees,
                )


# --------------------------------------------------------------------------
# Ce qu'il faut pour vider une carte : un point de vente, le caissier, la carte
# / What emptying a card needs: a point of sale, the cashier, the card
# --------------------------------------------------------------------------


def preparer_la_caisse(lieu):
    """
    Un point de vente, la carte primaire du caissier (autorisée sur ce point de vente)
    et le client HTTP d'un administrateur du lieu connecté.
    La vue du vidage exige une carte primaire autorisée sur le point de vente : c'est
    elle qui signe les remboursements, sur le Fedow local et sur l'ancien Fedow.
    `tag_id` et `number` font 8 caractères au plus (tests/PIEGES.md 9.31).
    / A point of sale, the cashier's primary card (allowed on it) and a logged-in venue
    admin client.
    """
    point_de_vente = creer_un_point_de_vente([])
    identifiant_de_la_carte_primaire = identifiant_unique().upper()
    carte_du_caissier = CarteCashless.objects.create(
        tag_id=identifiant_de_la_carte_primaire,
        number=identifiant_de_la_carte_primaire,
        uuid=uuid.uuid4(),
    )
    carte_primaire = CartePrimaire.objects.create(
        carte=carte_du_caissier,
        edit_mode=False,
    )
    carte_primaire.points_de_vente.add(point_de_vente)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    return SimpleNamespace(
        point_de_vente=point_de_vente,
        carte_du_caissier=carte_du_caissier,
        client_du_caissier=client_du_caissier,
    )


def creer_une_carte_client_sans_solde(lieu):
    """
    ÉTAT DE DÉPART : la carte NFC anonyme d'un client, avec son portefeuille, sans
    aucun solde. Le test pose ensuite ses soldes, monnaie par monnaie.
    / STARTING STATE: an anonymous customer card, with its wallet, without balance.
    """
    portefeuille_de_la_carte = Wallet.objects.create(
        name=f"{PREFIXE_DES_TESTS} carte {identifiant_unique()}",
        origin=lieu.tenant,
    )
    identifiant_de_la_carte = identifiant_unique().upper()
    return CarteCashless.objects.create(
        tag_id=identifiant_de_la_carte,
        number=identifiant_de_la_carte,
        uuid=uuid.uuid4(),
        wallet_ephemere=portefeuille_de_la_carte,
    )


def poser_un_solde_sur_la_carte(carte, monnaie, montant_en_centimes):
    """
    Pose un solde de `montant_en_centimes` dans `monnaie`, sur le portefeuille de la
    carte (Fedow local).
    / Puts a balance in `monnaie` on the card's wallet (local Fedow).
    """
    Token.objects.create(
        wallet=carte.wallet_ephemere,
        asset=monnaie,
        value=montant_en_centimes,
    )


def solde_de_la_carte(carte, monnaie):
    """Le solde de la carte dans cette monnaie, relu en base (centimes).
    / The card's balance in this currency, read back (cents)."""
    return WalletService.obtenir_solde(wallet=carte.wallet_ephemere, asset=monnaie)


def monnaie_locale_propre_au_lieu(lieu):
    """
    Une monnaie locale (TLF) créée par le lieu lui-même : c'est la seule monnaie locale
    que le vidage rend en espèces (une monnaie locale d'un autre lieu n'est pas rendue).
    / A local currency (TLF) created by the venue itself: the only local currency the
    emptying gives back in cash.
    """
    monnaie_locale = (
        Asset.objects.filter(category=Asset.TLF, tenant_origin=lieu.tenant)
        .order_by("name")
        .first()
    )
    assert monnaie_locale is not None, "Le lieu n'a aucune monnaie locale (TLF)."
    return monnaie_locale


def monnaie_cadeau_propre_au_lieu(lieu):
    """
    Une monnaie cadeau (TNF, jetons cadeau) créée par le lieu lui-même.
    / A gift currency (TNF, gift tokens) created by the venue itself.
    """
    monnaie_cadeau = (
        Asset.objects.filter(category=Asset.TNF, tenant_origin=lieu.tenant)
        .order_by("name")
        .first()
    )
    assert monnaie_cadeau is not None, "Le lieu n'a aucune monnaie cadeau (TNF)."
    return monnaie_cadeau


def monnaie_federee_locale(lieu):
    """
    La monnaie fédérée (FED) côté Fedow local.
    `Asset.save()` interdit aujourd'hui un FED local (`AssetFedLocalInterdit`) : la
    monnaie fédérée vit sur l'ancien Fedow. Le vidage local sait pourtant la rendre
    (fedow_core/services.py, `rembourser_en_especes`). On lève la garde le temps de
    fabriquer la monnaie, et seulement pour ça. Un seul FED existe dans tout le
    système (contrainte `unique_fed_asset`) : on reprend celui qui existerait déjà.
    Le rollback du test efface la monnaie créée.
    / The federated currency on the local Fedow. A local FED is forbidden today: the
    guard is lifted only to build it. Only one FED exists system-wide.
    """
    monnaie_federee_existante = Asset.objects.filter(category=Asset.FED).first()
    if monnaie_federee_existante is not None:
        return monnaie_federee_existante

    portefeuille_du_lieu = WalletService.get_or_create_wallet_tenant(lieu.tenant)
    with override_settings(FEDOW_AUTORISER_ASSET_FED_LOCAL=True):
        return Asset.objects.create(
            name=f"{PREFIXE_DES_TESTS} monnaie federee {identifiant_unique()}",
            category=Asset.FED,
            currency_code="EUR",
            wallet_origin=portefeuille_du_lieu,
            tenant_origin=lieu.tenant,
        )


# --------------------------------------------------------------------------
# L'ancien Fedow, simulé
# / The old Fedow, faked
# --------------------------------------------------------------------------


def fiche_de_carte_de_l_ancien_fedow(carte):
    """
    La carte telle que l'ancien Fedow la décrit (champs de `CardValidator`, données
    déjà validées).
    / The card as the old Fedow describes it (validated `CardValidator` fields).
    """
    uuid_du_portefeuille_distant = uuid.uuid4()
    return {
        "uuid": uuid.uuid4(),
        "qrcode_uuid": uuid.uuid4(),
        "first_tag_id": carte.tag_id,
        "number_printed": carte.number,
        "is_wallet_ephemere": True,
        "wallet": {
            "uuid": uuid_du_portefeuille_distant,
            "tokens": [],
            "get_name": "Portefeuille de la carte",
            "has_user_card": True,
        },
        "origin": {
            "place": {
                "uuid": uuid.uuid4(),
                "name": "Lieu",
                "wallet": uuid.uuid4(),
            },
            "generation": 1,
        },
    }


def ancien_fedow_simule(carte_du_client, monnaies_reprises):
    """
    Le client de l'ancien Fedow (`FedowAPI`), simulé : il connaît la carte, et son
    vidage (`card/refund`) reprend les monnaies données.
    / The old Fedow client, faked: it knows the card, and its refund takes back the
    given currencies.

    `monnaies_reprises` : une liste de paires (catégorie, montant en centimes).
    Catégories de l'ancien Fedow : « TLF » (monnaie locale du lieu), « TNF » (jetons
    cadeau du lieu), « FED » (monnaie fédérée).
    Les transactions rendues ressemblent à celles du vrai serveur
    (../Fedow/fedow_core/views.py, `CardAPI.refund`) : une transaction REFUND par jeton
    repris, SANS fiche de monnaie (le vrai `TransactionSerializer` ne l'envoie pas). La
    catégorie se lit dans la fiche de la monnaie (`asset.retrieve`) ou dans le
    portefeuille d'avant le vidage (`before_refund_serialized_wallet`).

    :return: (le faux client, la liste des transactions rendues, dans l'ordre donné)
    """
    transactions_rendues = []
    jetons_avant_le_vidage = []
    categorie_par_monnaie = {}
    for categorie, montant_en_centimes in monnaies_reprises:
        uuid_de_la_monnaie = uuid.uuid4()
        categorie_par_monnaie[str(uuid_de_la_monnaie)] = categorie
        transactions_rendues.append(
            {
                "uuid": uuid.uuid4(),
                "hash": uuid.uuid4().hex + uuid.uuid4().hex,
                "datetime": timezone.now(),
                "sender": uuid.uuid4(),
                "receiver": uuid.uuid4(),
                "asset": uuid_de_la_monnaie,
                "amount": montant_en_centimes,
                "previous_transaction": uuid.uuid4(),
                "action": "RFD",
                "get_action_display": "Refund",
                "verify_hash": True,
            }
        )
        jetons_avant_le_vidage.append(
            {
                "uuid": uuid.uuid4(),
                "name": f"Jeton {categorie}",
                "value": montant_en_centimes,
                "asset_uuid": uuid_de_la_monnaie,
                "asset_name": f"Monnaie {categorie}",
                "asset_category": categorie,
                "is_primary_stripe_token": categorie == "FED",
            }
        )

    def fiche_de_la_monnaie(*arguments, **arguments_nommes):
        # La fiche d'une monnaie distante, avec sa catégorie. L'uuid arrive par
        # position ou par son nom `uuid` (fedow_connect/fedow_api.py, AssetFedow).
        # / A remote currency's record, with its category. The uuid comes by position
        # or by its name `uuid`.
        if arguments:
            uuid_de_la_monnaie = arguments[0]
        else:
            uuid_de_la_monnaie = arguments_nommes["uuid"]
        return {
            "uuid": uuid.UUID(str(uuid_de_la_monnaie)),
            "name": "Monnaie de l'ancien Fedow",
            "currency_code": "EUR",
            "category": categorie_par_monnaie[str(uuid_de_la_monnaie)],
        }

    fiche_de_la_carte = fiche_de_carte_de_l_ancien_fedow(carte_du_client)
    faux_fedow = MagicMock()
    faux_fedow.NFCcard.retrieve.return_value = fiche_de_la_carte
    faux_fedow.NFCcard.card_tag_id_retrieve.return_value = {
        "wallet_uuid": fiche_de_la_carte["wallet"]["uuid"],
        "is_wallet_ephemere": True,
        "origin": fiche_de_la_carte["origin"],
    }
    faux_fedow.NFCcard.refund.return_value = {
        "serialized_card": fiche_de_la_carte,
        "before_refund_serialized_wallet": {
            "uuid": fiche_de_la_carte["wallet"]["uuid"],
            "tokens": jetons_avant_le_vidage,
            "get_name": "Portefeuille de la carte",
            "has_user_card": True,
        },
        "serialized_transactions": transactions_rendues,
    }
    faux_fedow.asset.retrieve.side_effect = fiche_de_la_monnaie
    faux_fedow.asset.cached_retrieve.side_effect = fiche_de_la_monnaie
    return faux_fedow, transactions_rendues


def ancien_fedow_qui_ne_connait_pas_la_carte():
    """
    Le client de l'ancien Fedow, simulé : la carte lui est inconnue (réponse 404 du
    serveur, `CarteInconnueDeFedow` dans le client).
    / The old Fedow client, faked: the card is unknown to it (404).
    """
    faux_fedow = MagicMock()
    faux_fedow.NFCcard.retrieve.side_effect = CarteInconnueDeFedow(
        "Carte inconnue de Fedow (simulé par le test)."
    )
    faux_fedow.NFCcard.card_tag_id_retrieve.return_value = None
    faux_fedow.NFCcard.refund.side_effect = CarteInconnueDeFedow(
        "Carte inconnue de Fedow (simulé par le test)."
    )
    return faux_fedow


def ancien_fedow_en_echec(carte_du_client, ou_l_echec_arrive):
    """
    Le client de l'ancien Fedow, simulé : il échoue.
    / The old Fedow client, faked: it fails.

    `ou_l_echec_arrive` :
    - « au_vidage » : la carte est connue, mais `card/refund` est refusé (réponse 400
      du serveur, par exemple « Primary card must be in place primary cards ») ;
    - « serveur_injoignable » : le serveur ne répond pas du tout (erreur réseau), dès
      la première question. Ce n'est PAS une carte inconnue.
    """
    faux_fedow, _transactions_rendues = ancien_fedow_simule(
        carte_du_client, [("TLF", 400)]
    )
    if ou_l_echec_arrive == "au_vidage":
        faux_fedow.NFCcard.refund.side_effect = Exception(
            "Fedow a répondu 400 : Primary card must be in place primary cards "
            "(simulé par le test)."
        )
    elif ou_l_echec_arrive == "serveur_injoignable":
        erreur_reseau = requests.ConnectionError(
            "Ancien Fedow injoignable (simulé par le test)."
        )
        faux_fedow.NFCcard.retrieve.side_effect = erreur_reseau
        faux_fedow.NFCcard.card_tag_id_retrieve.side_effect = erreur_reseau
        faux_fedow.NFCcard.refund.side_effect = erreur_reseau
    else:
        raise ValueError(f"Échec inconnu : {ou_l_echec_arrive}")
    return faux_fedow


def vider_la_carte_a_la_caisse(
    caisse, carte_du_client, faux_ancien_fedow, lieu_relie, vider_et_delier=False
):
    """
    Le caissier vide la carte du client : la vraie route de la caisse, avec la carte
    primaire du caissier. L'ancien Fedow est simulé (`faux_ancien_fedow`), et le lieu
    est relié ou non à l'ancien Fedow (`FedowConfig.can_fedow`, simulé).
    `vider_et_delier` : la case « vider et délier la carte » de l'écran.
    / The cashier empties the customer card through the real register route.

    :return: (la réponse HTTP, la fausse classe `FedowAPI`, pour savoir si elle a été
        instanciée)
    """
    if vider_et_delier:
        case_vider_et_delier = "true"
    else:
        case_vider_et_delier = "false"
    donnees_du_formulaire = {
        "tag_id": carte_du_client.tag_id,
        "tag_id_cm": caisse.carte_du_caissier.tag_id,
        "uuid_pv": str(caisse.point_de_vente.uuid),
        "vider_carte": case_vider_et_delier,
    }
    with patch.object(FedowConfig, "can_fedow", return_value=lieu_relie):
        with patch(
            "laboutik.views.FedowAPI", return_value=faux_ancien_fedow
        ) as classe_fedow_api_simulee:
            reponse = caisse.client_du_caissier.post(
                URL_DU_VIDAGE_DE_CARTE, donnees_du_formulaire
            )
    return reponse, classe_fedow_api_simulee


# --------------------------------------------------------------------------
# Assistants de lecture
# / Reading helpers
# --------------------------------------------------------------------------


def retrouver_la_vente_de_vidage(carte_du_client):
    """
    La vente `VIDAGE_CARTE` de cette carte. Il en faut exactement une : zéro veut dire
    que la caisse n'a pas écrit de vente, deux qu'elle en a écrit une de trop.
    / The card's `VIDAGE_CARTE` sale. Exactly one is expected.
    """
    ventes_de_vidage = list(
        Vente.objects.filter(
            nature=Vente.Nature.VIDAGE_CARTE,
            carte=carte_du_client,
        )
    )
    assert len(ventes_de_vidage) == 1, (
        f"Attendu : une vente de vidage pour la carte {carte_du_client.tag_id}, "
        f"trouvé : {len(ventes_de_vidage)}."
    )
    return ventes_de_vidage[0]


def reglements_de_la_vidange(vente):
    """
    Les règlements de la vente, relus en base : une liste triée de tuples
    (moyen, montant, uuid de la transaction locale ou None, référence externe).
    / The sale's payments, read back: sorted (method, amount, local uuid, external ref).
    """
    reglements_lus = []
    for reglement in vente.reglements.all():
        uuid_de_la_transaction_locale = None
        if reglement.fedow_transaction_uuid is not None:
            uuid_de_la_transaction_locale = str(reglement.fedow_transaction_uuid)
        reglements_lus.append(
            (
                reglement.moyen,
                reglement.montant,
                uuid_de_la_transaction_locale,
                reglement.reference_externe,
            )
        )
    return sorted(reglements_lus, key=str)


def remboursement_local_de_la_monnaie(carte_du_client, monnaie):
    """
    L'unique transaction de remboursement (REFUND) du Fedow local, pour cette carte et
    cette monnaie.
    / The only local REFUND transaction for this card and currency.
    """
    remboursements = list(
        Transaction.objects.filter(
            card=carte_du_client,
            asset=monnaie,
            action=Transaction.REFUND,
        )
    )
    assert len(remboursements) == 1, (
        f"Attendu : un remboursement local en {monnaie.name}, "
        f"trouvé : {len(remboursements)}."
    )
    return remboursements[0]


def lignes_refund_de_la_carte(carte_du_client):
    """
    Les lignes de la carte sans vente (les anciennes lignes « Refund »), relues en
    base : une liste triée de paires (moyen de paiement, montant en centimes). Le
    vidage n'en écrit plus (D12) : elle doit rester vide.
    / The card's lines without a sale (old "Refund" lines): must stay empty (D12).
    """
    lignes_lues = []
    for ligne in LigneArticle.objects.filter(carte=carte_du_client, vente__isnull=True):
        lignes_lues.append((ligne.payment_method, ligne.amount))
    return sorted(lignes_lues)


def verifier_l_ecran_d_erreur(reponse):
    """
    L'écran d'erreur de la caisse : pas une erreur du serveur, pas l'écran de succès.
    / The register's error screen: not a server error, not the success screen.
    """
    assert reponse.status_code < 500
    contenu_de_la_reponse = reponse.content.decode()
    assert 'data-testid="alerte-messages"' in contenu_de_la_reponse
    assert 'data-testid="vider-carte-success"' not in contenu_de_la_reponse


def verifier_que_rien_n_est_ecrit_en_local(carte_du_client, soldes_attendus):
    """
    Rien n'est écrit en local : les soldes de la carte sont intacts, aucune transaction
    de remboursement, aucune vente de vidage, aucune ligne.
    / Nothing written locally: balances intact, no refund, no sale, no line.

    :param soldes_attendus: liste de paires (monnaie, solde attendu en centimes)
    """
    for monnaie, solde_attendu in soldes_attendus:
        assert solde_de_la_carte(carte_du_client, monnaie) == solde_attendu
    assert not Transaction.objects.filter(
        card=carte_du_client, action=Transaction.REFUND
    ).exists()
    assert not Vente.objects.filter(
        nature=Vente.Nature.VIDAGE_CARTE, carte=carte_du_client
    ).exists()
    assert not LigneArticle.objects.filter(carte=carte_du_client).exists()


def messages_d_incident(caplog):
    """Les messages d'erreur journalisés qui contiennent « INCIDENT ».
    / The logged error messages containing "INCIDENT"."""
    messages_trouves = []
    for enregistrement in caplog.records:
        message_journalise = enregistrement.getMessage()
        est_une_erreur = enregistrement.levelno >= logging.ERROR
        if est_une_erreur and "INCIDENT" in message_journalise:
            messages_trouves.append(message_journalise)
    return messages_trouves


# --------------------------------------------------------------------------
# 20 — Fedow local seul : monnaie locale et monnaie fédérée, deux règlements
# / 20 — Local Fedow only: local and federated currency, two payments
# --------------------------------------------------------------------------


def test_vider_carte_tlf_et_fed_deux_reglements(lieu):
    """
    Le lieu n'est pas relié à l'ancien Fedow. La carte porte 5,00 € de monnaie locale
    du lieu et 3,00 € de monnaie fédérée, sur le Fedow local. Le caissier la vide.
    La vente `VIDAGE_CARTE` n'a aucun article. Elle a un règlement positif par
    remboursement d'argent : monnaie locale (LE) +500 et monnaie fédérée (SF) +300,
    chacun avec l'uuid de SA transaction locale ; puis un règlement espèces −800 (ce
    qui sort du tiroir). La somme des règlements vaut 0.
    / Venue not linked to the old Fedow. Local 5.00 + FED 3.00, emptied. One sale
    without item: LE +500, SF +300 (each with its local transaction uuid), cash −800.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    monnaie_federee = monnaie_federee_locale(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_federee, 300)

    reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse, carte_du_client, MagicMock(), lieu_relie=False
    )

    assert reponse.status_code == 200
    assert solde_de_la_carte(carte_du_client, monnaie_locale) == 0
    assert solde_de_la_carte(carte_du_client, monnaie_federee) == 0
    remboursement_en_monnaie_locale = remboursement_local_de_la_monnaie(
        carte_du_client, monnaie_locale
    )
    remboursement_en_monnaie_federee = remboursement_local_de_la_monnaie(
        carte_du_client, monnaie_federee
    )

    vente = retrouver_la_vente_de_vidage(carte_du_client)
    assert vente.statut == Vente.Statut.REGLEE
    assert vente.point_de_vente_id == caisse.point_de_vente.pk
    assert vente.articles.count() == 0
    assert reglements_de_la_vidange(vente) == sorted(
        [
            (
                PaymentMethod.LOCAL_EURO,
                500,
                str(remboursement_en_monnaie_locale.uuid),
                "",
            ),
            (
                PaymentMethod.STRIPE_FED,
                300,
                str(remboursement_en_monnaie_federee.uuid),
                "",
            ),
            (PaymentMethod.CASH, -800, None, ""),
        ],
        key=str,
    )
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 20b — Les jetons cadeau locaux sont repris, sans argent rendu, réglés « jetons »
# / 20b — Local gift tokens are taken back, no money given back, LG payment
# --------------------------------------------------------------------------


def test_vider_carte_jetons_cadeau_locaux_repris_sans_argent_reglement_lg(lieu):
    """
    Le lieu n'est pas relié à l'ancien Fedow. La carte porte 5,00 € de monnaie locale
    et 2,00 € de jetons cadeau du lieu, sur le Fedow local. Le caissier la vide.
    Les jetons cadeau disparaissent aussi (décision du mainteneur) : leur solde passe à
    0, par une transaction de remboursement vers le lieu. Le tiroir ne rend que 5,00 €
    (règlement espèces −500 ; aucune ligne « Refund », D12). La dette des jetons perdus est
    annulée (D8 bis) : un règlement « jetons » (LG) +200, avec l'uuid de sa transaction
    locale, et l'article « Jetons cadeau repris au vidage » de 200.
    / Local 5.00 + gift 2.00. Gift tokens go to 0 through a REFUND transaction; cash
    −500 only; the tokens write an LG +200 payment and a 200 "taken back" item.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    monnaie_cadeau = monnaie_cadeau_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_cadeau, 200)

    reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse, carte_du_client, MagicMock(), lieu_relie=False
    )

    assert reponse.status_code == 200

    # Les jetons cadeau sont repris : solde à 0, une transaction de remboursement.
    # / Gift tokens are taken back: balance 0, one refund transaction.
    assert solde_de_la_carte(carte_du_client, monnaie_cadeau) == 0
    remboursement_des_jetons_cadeau = remboursement_local_de_la_monnaie(
        carte_du_client, monnaie_cadeau
    )
    assert remboursement_des_jetons_cadeau.amount == 200

    # Aucun argent rendu pour les jetons cadeau : leur règlement est « jetons ».
    # / No money given back for gift tokens: their payment is LG.
    remboursement_en_monnaie_locale = remboursement_local_de_la_monnaie(
        carte_du_client, monnaie_locale
    )
    vente = retrouver_la_vente_de_vidage(carte_du_client)
    assert reglements_de_la_vidange(vente) == sorted(
        [
            (
                PaymentMethod.LOCAL_EURO,
                500,
                str(remboursement_en_monnaie_locale.uuid),
                "",
            ),
            (
                PaymentMethod.LOCAL_GIFT,
                200,
                str(remboursement_des_jetons_cadeau.uuid),
                "",
            ),
            (PaymentMethod.CASH, -500, None, ""),
        ],
        key=str,
    )
    verifier_les_articles_des_jetons_repris(vente, montants_attendus=[200])
    assert lignes_refund_de_la_carte(carte_du_client) == []
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 20b bis — Les jetons repris au vidage sont écrits : article et règlement LG (D8 bis)
# / 20b bis — Tokens taken back at emptying are written: item and LG payment (D8 bis)
# --------------------------------------------------------------------------


def verifier_les_articles_des_jetons_repris(vente, montants_attendus):
    """
    Vérifie les articles « Jetons cadeau repris au vidage » de la vente : un article
    par transaction de jetons repris, quantité 1, prix = montant de la transaction,
    hors chiffre d'affaires, TVA 0, rien d'offert (net = total catalogue), sans moyen
    (le règlement LG le porte, Q-H2), sans carte ni monnaie.
    / Checks the "gift tokens taken back" items: one per token transaction, qty 1,
    price = its amount, off revenue, VAT 0, nothing offered, no method, no card, no
    currency.

    Le nom du produit système est une constante du service de vente : le plan
    comptable le reconnaît par ce nom (623400).
    / The system product's name is a sale service constant (623400 by name).

    :param montants_attendus: les montants des transactions de jetons (centimes)
    """
    montants_des_articles = []
    for article in vente.articles.all():
        produit_de_l_article = article.pricesold.productsold.product
        assert produit_de_l_article.name == NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE
        assert article.qty == 1
        assert article.amount == article.total_catalogue
        assert article.hors_chiffre_affaires is True
        assert article.vat == 0
        assert article.part_offerte == 0
        assert article.total_ttc == article.total_catalogue
        assert article.total_ht == article.total_catalogue
        assert article.total_tva == 0
        assert article.payment_method is None
        assert article.carte_id is None
        assert article.asset is None
        montants_des_articles.append(article.total_catalogue)
    assert sorted(montants_des_articles) == sorted(montants_attendus)


def test_vider_carte_jetons_ecrits_article_et_reglement_lg(lieu):
    """
    Le lieu est relié à l'ancien Fedow. La carte porte, sur le Fedow local, 5,00 € de
    monnaie locale et 2,00 € de jetons cadeau ; sur l'ancien Fedow, 0,50 € de jetons
    cadeau. Le caissier la vide.
    Des jetons perdus annulent la dette du lieu (D8 bis) : le vidage écrit leur montant.
    Pour chaque transaction de jetons repris :
    - un règlement « jetons » (LG) POSITIF du montant, avec la monnaie et la carte, et
      comme les autres règlements du vidage : l'uuid de la transaction locale dans
      `fedow_transaction_uuid`, ou l'uuid de la transaction de l'ancien Fedow dans
      `reference_externe` ;
    - un article « Jetons cadeau repris au vidage » du même montant, hors chiffre
      d'affaires, TVA 0, sans carte ni monnaie.
    L'argent rendu ne change pas : monnaie locale (LE) +500, espèces −500.
    Les deux égalités tiennent.
    / Local 5.00 + local tokens 2.00, remote tokens 0.50. Each token transaction writes
    a positive LG payment (currency, card, local uuid or remote reference) and an
    off-revenue, 0-VAT item of the same amount. Cash unchanged: LE +500, cash −500.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    monnaie_cadeau = monnaie_cadeau_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_cadeau, 200)
    faux_ancien_fedow, transactions_distantes = ancien_fedow_simule(
        carte_du_client, [("TNF", 50)]
    )
    transaction_distante_des_jetons = transactions_distantes[0]

    reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_vidage(carte_du_client)
    assert vente.statut == Vente.Statut.REGLEE
    remboursement_en_monnaie_locale = remboursement_local_de_la_monnaie(
        carte_du_client, monnaie_locale
    )
    remboursement_des_jetons_locaux = remboursement_local_de_la_monnaie(
        carte_du_client, monnaie_cadeau
    )

    assert reglements_de_la_vidange(vente) == sorted(
        [
            (
                PaymentMethod.LOCAL_EURO,
                500,
                str(remboursement_en_monnaie_locale.uuid),
                "",
            ),
            (
                PaymentMethod.LOCAL_GIFT,
                200,
                str(remboursement_des_jetons_locaux.uuid),
                "",
            ),
            (
                PaymentMethod.LOCAL_GIFT,
                50,
                None,
                str(transaction_distante_des_jetons["uuid"]),
            ),
            (PaymentMethod.CASH, -500, None, ""),
        ],
        key=str,
    )

    # Chaque règlement « jetons » porte la monnaie reprise et la carte.
    # / Each token payment carries the currency taken back and the card.
    monnaie_par_montant_des_jetons = {}
    for reglement_des_jetons in vente.reglements.filter(
        moyen=PaymentMethod.LOCAL_GIFT
    ):
        assert reglement_des_jetons.carte_id == carte_du_client.pk
        monnaie_par_montant_des_jetons[reglement_des_jetons.montant] = str(
            reglement_des_jetons.asset
        )
    assert monnaie_par_montant_des_jetons == {
        200: str(monnaie_cadeau.uuid),
        50: str(transaction_distante_des_jetons["asset"]),
    }

    verifier_les_articles_des_jetons_repris(vente, montants_attendus=[200, 50])
    assert vente.total_catalogue == 250
    assert vente.total_offert == 0
    assert vente.total_ttc == 250
    assert vente.total_tva == 0
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 20c — L'ancien Fedow et le Fedow local, dans la même vente
# / 20c — The old Fedow and the local Fedow, in the same sale
# --------------------------------------------------------------------------


def test_vider_carte_ancien_fedow_et_local(lieu):
    """
    Le lieu est relié à l'ancien Fedow, qui connaît la carte. Sur l'ancien Fedow, la
    carte porte 4,00 € de monnaie locale du lieu, 1,00 € de monnaie fédérée et 0,50 €
    de jetons cadeau ; sur le Fedow local, 5,00 € de monnaie locale.
    L'ancien Fedow est vidé EN PREMIER (`card/refund`, action REFUND) : au moment de
    son appel, rien n'est encore remboursé en local. Puis le Fedow local est vidé.
    La vente a un règlement par remboursement d'argent : LE +500 (transaction locale,
    `fedow_transaction_uuid`), LE +400 et SF +100 (transactions distantes, uuid dans
    `reference_externe`), puis espèces −1000. Les jetons cadeau (sans argent rendu)
    ont leur règlement « jetons » (LG) +50, uuid distant dans `reference_externe`, et
    leur article « Jetons cadeau repris au vidage » de 50 (D8 bis).
    Aucun FED n'existe en local (comme en production) : la monnaie fédérée ne vient
    que de l'ancien Fedow.
    / Old Fedow: local 4.00 + FED 1.00 + gift 0.50; local Fedow: local 5.00. Old Fedow
    emptied FIRST. Payments LE +500 (local), LE +400 and SF +100 (remote, in
    `reference_externe`), cash −1000; the gift tokens: LG +50 (remote) and a 50 item.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    faux_ancien_fedow, transactions_distantes = ancien_fedow_simule(
        carte_du_client, [("TLF", 400), ("FED", 100), ("TNF", 50)]
    )
    transaction_distante_monnaie_locale = transactions_distantes[0]
    transaction_distante_monnaie_federee = transactions_distantes[1]
    transaction_distante_des_jetons = transactions_distantes[2]

    # Ce que le Fedow local contient au moment où l'ancien Fedow est vidé : l'ordre de
    # la règle veut que rien ne soit encore remboursé en local.
    # / What the local Fedow holds when the old Fedow is emptied: nothing refunded yet.
    etat_local_au_moment_du_vidage_distant = []
    reponse_du_vidage_distant = faux_ancien_fedow.NFCcard.refund.return_value

    def vider_la_carte_sur_l_ancien_fedow(*_arguments, **_arguments_nommes):
        etat_local_au_moment_du_vidage_distant.append(
            (
                Transaction.objects.filter(
                    card=carte_du_client, action=Transaction.REFUND
                ).count(),
                solde_de_la_carte(carte_du_client, monnaie_locale),
            )
        )
        return reponse_du_vidage_distant

    faux_ancien_fedow.NFCcard.refund.side_effect = vider_la_carte_sur_l_ancien_fedow

    reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )

    assert reponse.status_code == 200
    assert faux_ancien_fedow.NFCcard.refund.call_count == 1
    assert etat_local_au_moment_du_vidage_distant == [(0, 500)]
    assert solde_de_la_carte(carte_du_client, monnaie_locale) == 0
    remboursement_en_monnaie_locale = remboursement_local_de_la_monnaie(
        carte_du_client, monnaie_locale
    )

    vente = retrouver_la_vente_de_vidage(carte_du_client)
    assert vente.statut == Vente.Statut.REGLEE
    verifier_les_articles_des_jetons_repris(vente, montants_attendus=[50])
    assert reglements_de_la_vidange(vente) == sorted(
        [
            (
                PaymentMethod.LOCAL_EURO,
                500,
                str(remboursement_en_monnaie_locale.uuid),
                "",
            ),
            (
                PaymentMethod.LOCAL_EURO,
                400,
                None,
                str(transaction_distante_monnaie_locale["uuid"]),
            ),
            (
                PaymentMethod.STRIPE_FED,
                100,
                None,
                str(transaction_distante_monnaie_federee["uuid"]),
            ),
            (
                PaymentMethod.LOCAL_GIFT,
                50,
                None,
                str(transaction_distante_des_jetons["uuid"]),
            ),
            (PaymentMethod.CASH, -1000, None, ""),
        ],
        key=str,
    )

    # Chaque règlement distant porte la monnaie débitée sur l'ancien Fedow.
    # / Each remote payment carries the currency taken back on the old Fedow.
    monnaie_par_reference_externe = {}
    for reglement in vente.reglements.exclude(reference_externe=""):
        monnaie_par_reference_externe[reglement.reference_externe] = str(
            reglement.asset
        )
    assert monnaie_par_reference_externe == {
        str(transaction_distante_monnaie_locale["uuid"]): str(
            transaction_distante_monnaie_locale["asset"]
        ),
        str(transaction_distante_monnaie_federee["uuid"]): str(
            transaction_distante_monnaie_federee["asset"]
        ),
        str(transaction_distante_des_jetons["uuid"]): str(
            transaction_distante_des_jetons["asset"]
        ),
    }
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 20d — L'ancien Fedow échoue : rien n'est fait
# / 20d — The old Fedow fails: nothing is done
# --------------------------------------------------------------------------


@pytest.mark.parametrize("ou_l_echec_arrive", ["au_vidage", "serveur_injoignable"])
def test_vider_carte_ancien_fedow_en_echec_rien_n_est_fait(lieu, ou_l_echec_arrive):
    """
    Le lieu est relié à l'ancien Fedow. La carte porte 5,00 € de monnaie locale sur le
    Fedow local. L'ancien Fedow échoue : soit il refuse le vidage (`card/refund` en
    erreur), soit il ne répond pas du tout (erreur réseau, ce qui n'est PAS une carte
    inconnue).
    Rien n'est fait : la caisse affiche son écran d'erreur (jamais une erreur 500), les
    jetons locaux sont intacts, aucune transaction de remboursement, aucune vente,
    aucune ligne.
    / The old Fedow fails (refund refused, or unreachable). Nothing is done: error
    screen (never a 500), local balance intact, no refund, no sale, no line.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    faux_ancien_fedow = ancien_fedow_en_echec(carte_du_client, ou_l_echec_arrive)

    reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )

    verifier_l_ecran_d_erreur(reponse)
    verifier_que_rien_n_est_ecrit_en_local(
        carte_du_client, soldes_attendus=[(monnaie_locale, 500)]
    )


# --------------------------------------------------------------------------
# 20e — L'ancien Fedow est vidé, puis le vidage local échoue : INCIDENT
# / 20e — The old Fedow is emptied, then the local emptying fails: INCIDENT
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ou_l_echec_local_arrive", ["au_vidage_local", "a_l_encaissement_de_la_vente"]
)
def test_vider_carte_local_en_echec_apres_ancien_fedow_incident_journalise(
    lieu, caplog, ou_l_echec_local_arrive
):
    """
    Le lieu est relié à l'ancien Fedow. Sur l'ancien Fedow, la carte porte 4,00 € de
    monnaie locale du lieu et 1,00 € de monnaie fédérée ; sur le Fedow local, 5,00 € de
    monnaie locale. L'ancien Fedow est vidé (il ne s'annule pas), puis le vidage local
    échoue : soit le remboursement local lui-même, soit l'encaissement de la vente
    (égalités rompues, simulées), après les remboursements locaux.
    La caisse journalise UN INCIDENT, avec le montant vidé sur l'ancien Fedow (500),
    la carte, et l'uuid de chaque transaction distante : sans eux, personne ne peut
    rendre à la main l'argent repris. Elle affiche son écran d'erreur (jamais une
    erreur 500). Rien n'est écrit en local : soldes intacts, aucune transaction de
    remboursement, aucune vente, aucune ligne.
    / Old Fedow emptied (4.00 + FED 1.00), then the local emptying fails. One INCIDENT
    logged (amount 500, card, remote uuids), error screen, nothing written locally.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    faux_ancien_fedow, transactions_distantes = ancien_fedow_simule(
        carte_du_client, [("TLF", 400), ("FED", 100)]
    )

    if ou_l_echec_local_arrive == "au_vidage_local":
        simulation_de_l_echec_local = patch.object(
            WalletService,
            "rembourser_en_especes",
            side_effect=RuntimeError("Vidage local en échec (simulé par le test)."),
        )
    else:
        simulation_de_l_echec_local = patch(
            "laboutik.views.encaisser_vente",
            side_effect=EgaliteDeVenteRompue(
                "Égalité simulée par le test : règlements 0, articles 1."
            ),
        )

    with caplog.at_level(logging.ERROR, logger="laboutik.views"):
        with simulation_de_l_echec_local:
            reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
                caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
            )

    # L'ancien Fedow a bien été vidé : c'est ce qui rend l'incident nécessaire.
    # / The old Fedow was emptied: that is why the incident is needed.
    assert faux_ancien_fedow.NFCcard.refund.call_count == 1

    verifier_l_ecran_d_erreur(reponse)

    incidents = messages_d_incident(caplog)
    assert len(incidents) == 1, (
        f"Attendu : un incident journalisé, trouvé : {incidents}"
    )
    assert "500" in incidents[0]
    assert carte_du_client.tag_id in incidents[0]
    for transaction_distante in transactions_distantes:
        assert str(transaction_distante["uuid"]) in incidents[0]

    verifier_que_rien_n_est_ecrit_en_local(
        carte_du_client, soldes_attendus=[(monnaie_locale, 500)]
    )


# --------------------------------------------------------------------------
# 20e bis — L'ancien Fedow est vidé, puis sa réponse est illisible : l'écran dit
# la vérité
# / 20e bis — The old Fedow is emptied, then its answer is unreadable: the screen
# tells the truth
# --------------------------------------------------------------------------

# Le message qui dit la vérité après un vidage réussi sur l'ancien Fedow (fiche B §5,
# point 2). Les écrans sont demandés en français : une traduction anglaise le changerait.
# / The truthful message after a successful old-Fedow emptying. Screens are requested
# in French.
MESSAGE_ANCIEN_FEDOW_VIDE_PAS_LE_LOCAL = (
    "La carte est vidée sur l'ancien Fedow, mais pas en local. "
    "Incident enregistré : prévenez un responsable."
)


def test_vider_carte_ancien_fedow_vide_puis_categories_illisibles_ecran_dit_la_verite(
    lieu, caplog
):
    """
    Le lieu est relié à l'ancien Fedow. Sur l'ancien Fedow, la carte porte 4,00 € de
    monnaie locale du lieu ; sur le Fedow local, 5,00 € de monnaie locale.
    `card/refund` RÉUSSIT (la carte est vidée là-bas, ça ne s'annule pas), puis la
    caisse ne sait pas lire la catégorie de la monnaie reprise : absente du
    portefeuille d'avant le vidage, et sa fiche (`asset.retrieve`) ne répond pas.
    L'écran dit la vérité : « La carte est vidée sur l'ancien Fedow, mais pas en
    local. Incident enregistré : prévenez un responsable. » — jamais « Rien n'a été
    fait : réessayez », qui est faux (un nouvel essai ne rendrait jamais cet argent).
    UN INCIDENT est journalisé (la carte, l'uuid de la transaction distante). Rien
    n'est écrit en local : soldes intacts, aucune transaction de remboursement, aucune
    vente, aucune ligne.
    / card/refund succeeds on the old Fedow, then the taken-back currency's category is
    unreadable. The screen tells the truth (emptied there, not locally, incident
    logged), never "nothing was done: retry". One INCIDENT, nothing written locally.
    """
    caisse = preparer_la_caisse(lieu)
    demander_les_ecrans_en_francais(caisse)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    faux_ancien_fedow, transactions_distantes = ancien_fedow_simule(
        carte_du_client, [("TLF", 400)]
    )
    # La monnaie reprise n'est pas dans le portefeuille d'avant le vidage : la caisse
    # demande sa fiche, et l'ancien Fedow ne répond plus.
    # / The currency is missing from the before-refund wallet: the register asks for
    # its record, and the old Fedow no longer answers.
    reponse_du_vidage_distant = faux_ancien_fedow.NFCcard.refund.return_value
    reponse_du_vidage_distant["before_refund_serialized_wallet"]["tokens"] = []
    faux_ancien_fedow.asset.retrieve.side_effect = requests.ConnectionError(
        "Ancien Fedow injoignable après le vidage (simulé par le test)."
    )

    with caplog.at_level(logging.ERROR, logger="laboutik.views"):
        reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
            caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
        )

    # L'ancien Fedow a bien été vidé : c'est ce qui rend « réessayez » faux.
    # / The old Fedow was emptied: that is why "retry" would be false.
    assert faux_ancien_fedow.NFCcard.refund.call_count == 1

    verifier_l_ecran_d_erreur(reponse)
    texte_du_message = texte_de_l_element(
        lire_l_ecran(reponse), "alerte-messages-texte"
    )
    assert texte_du_message == MESSAGE_ANCIEN_FEDOW_VIDE_PAS_LE_LOCAL, (
        f"Message affiché : {texte_du_message!r}"
    )

    incidents = messages_d_incident(caplog)
    assert len(incidents) == 1, (
        f"Attendu : un incident journalisé, trouvé : {incidents}"
    )
    assert carte_du_client.tag_id in incidents[0]
    for transaction_distante in transactions_distantes:
        assert str(transaction_distante["uuid"]) in incidents[0]

    verifier_que_rien_n_est_ecrit_en_local(
        carte_du_client, soldes_attendus=[(monnaie_locale, 500)]
    )


# --------------------------------------------------------------------------
# 20f — Carte inconnue de l'ancien Fedow, ou lieu non relié : vidage local seul
# / 20f — Card unknown to the old Fedow, or venue not linked: local emptying only
# --------------------------------------------------------------------------


@pytest.mark.parametrize("pourquoi_local_seul", ["carte_inconnue", "lieu_non_relie"])
def test_vider_carte_inconnue_de_l_ancien_fedow_vidange_locale_seule(
    lieu, pourquoi_local_seul
):
    """
    La carte porte 5,00 € de monnaie locale du lieu sur le Fedow local. L'ancien Fedow
    ne la vide pas :
    - « carte_inconnue » : le lieu est relié, mais l'ancien Fedow ne connaît pas la
      carte (réponse 404) ;
    - « lieu_non_relie » : le lieu n'est pas relié à l'ancien Fedow. Le client Fedow
      n'est alors même pas créé (le créer sans lieu relié lancerait une création de
      lieu sur le serveur, laboutik/views.py `obtenir_wallet_carte_depuis_fedow`).
    `card/refund` n'est jamais appelé. Le vidage local se fait comme aujourd'hui, et la
    vente du vidage est écrite : LE +500, espèces −500.
    / Card unknown to the old Fedow, or venue not linked: `card/refund` never called,
    local emptying as today, sale LE +500 and cash −500.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    faux_ancien_fedow = ancien_fedow_qui_ne_connait_pas_la_carte()
    lieu_relie = pourquoi_local_seul == "carte_inconnue"

    reponse, classe_fedow_api_simulee = vider_la_carte_a_la_caisse(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=lieu_relie
    )

    assert faux_ancien_fedow.NFCcard.refund.call_count == 0
    if not lieu_relie:
        assert classe_fedow_api_simulee.call_count == 0

    assert reponse.status_code == 200
    assert solde_de_la_carte(carte_du_client, monnaie_locale) == 0
    remboursement_en_monnaie_locale = remboursement_local_de_la_monnaie(
        carte_du_client, monnaie_locale
    )
    vente = retrouver_la_vente_de_vidage(carte_du_client)
    assert reglements_de_la_vidange(vente) == sorted(
        [
            (
                PaymentMethod.LOCAL_EURO,
                500,
                str(remboursement_en_monnaie_locale.uuid),
                "",
            ),
            (PaymentMethod.CASH, -500, None, ""),
        ],
        key=str,
    )
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 20g — « Vider et délier » envoie VOID, sinon REFUND ; même carte primaire
# / 20g — "Empty and unlink" sends VOID, otherwise REFUND; same primary card
# --------------------------------------------------------------------------


@pytest.mark.parametrize("vider_et_delier", [True, False])
def test_vider_et_delier_envoie_void_a_l_ancien_fedow(lieu, vider_et_delier):
    """
    Le lieu est relié à l'ancien Fedow, qui connaît la carte (4,00 € de monnaie locale
    du lieu là-bas, 5,00 € en local). La case « vider et délier la carte » est cochée,
    ou non.
    Le client de l'ancien Fedow reçoit : le tag de la carte du client, le tag de la
    carte primaire du CAISSIER (la même carte primaire pour les deux Fedow, décision du
    mainteneur, comme LaBoutik V1), et `void=True` si la case est cochée (action VOID :
    l'ancien Fedow délie aussi la carte), `void=False` sinon (action REFUND).
    Les arguments sont relus sur la signature du client de LaBoutik V1
    (`refund(user_card_firstTagId, primary_card_fisrtTagId, void=False)`), qu'ils soient
    passés par position ou par nom.
    / The old Fedow client receives the customer card tag, the CASHIER's primary card
    tag (same primary card for both Fedow), and void=True when the box is ticked.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    faux_ancien_fedow, _transactions_distantes = ancien_fedow_simule(
        carte_du_client, [("TLF", 400)]
    )

    reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse,
        carte_du_client,
        faux_ancien_fedow,
        lieu_relie=True,
        vider_et_delier=vider_et_delier,
    )

    assert reponse.status_code == 200
    assert faux_ancien_fedow.NFCcard.refund.call_count == 1

    def signature_du_client_v1(
        user_card_firstTagId=None, primary_card_fisrtTagId=None, void=False
    ):
        # Signature de `NFCcard.refund` dans LaBoutik V1 : sert seulement à relire
        # l'appel. / V1 `NFCcard.refund` signature: only used to read the call back.
        pass

    appel_du_vidage_distant = faux_ancien_fedow.NFCcard.refund.call_args
    arguments_du_vidage_distant = inspect.signature(signature_du_client_v1).bind(
        *appel_du_vidage_distant.args, **appel_du_vidage_distant.kwargs
    )
    arguments_du_vidage_distant.apply_defaults()
    arguments_lus = arguments_du_vidage_distant.arguments
    assert str(arguments_lus["user_card_firstTagId"]).upper() == carte_du_client.tag_id
    assert (
        str(arguments_lus["primary_card_fisrtTagId"]).upper()
        == caisse.carte_du_caissier.tag_id
    )
    assert arguments_lus["void"] is vider_et_delier


# --------------------------------------------------------------------------
# 20g bis — Le client de l'ancien Fedow : route card/refund, action VID ou RFD
# / 20g bis — The old Fedow client: card/refund route, VID or RFD action
# --------------------------------------------------------------------------


def reponse_de_l_ancien_fedow_au_vidage(tag_de_la_carte, montants_repris):
    """
    Le corps JSON que le vrai serveur rend à `card/refund` (réponse 205), tel qu'il
    arrive sur le réseau : textes, pas encore validés. Une transaction REFUND par
    montant repris.
    / The JSON body the real server returns to card/refund (205), as it arrives.
    """
    uuid_du_portefeuille = str(uuid.uuid4())
    fiche_de_la_carte = {
        "wallet": {
            "uuid": uuid_du_portefeuille,
            "tokens": [],
            "get_name": "Portefeuille de la carte",
            "has_user_card": True,
        },
        "origin": {
            "place": {
                "uuid": str(uuid.uuid4()),
                "name": "Lieu",
                "wallet": str(uuid.uuid4()),
            },
            "generation": 1,
        },
        "uuid": str(uuid.uuid4()),
        "qrcode_uuid": str(uuid.uuid4()),
        "first_tag_id": tag_de_la_carte,
        "number_printed": tag_de_la_carte,
        "is_wallet_ephemere": False,
    }
    transactions_json = []
    for montant_repris in montants_repris:
        transactions_json.append(
            {
                "uuid": str(uuid.uuid4()),
                "action": "RFD",
                "get_action_display": "Refund",
                "hash": uuid.uuid4().hex + uuid.uuid4().hex,
                "datetime": timezone.now().isoformat(),
                "sender": uuid_du_portefeuille,
                "receiver": str(uuid.uuid4()),
                "asset": str(uuid.uuid4()),
                "amount": montant_repris,
                "comment": None,
                "metadata": None,
                "card": None,
                "primary_card": str(uuid.uuid4()),
                "previous_transaction": str(uuid.uuid4()),
                "verify_hash": True,
            }
        )
    return {
        "serialized_card": fiche_de_la_carte,
        "before_refund_serialized_wallet": {
            "uuid": uuid_du_portefeuille,
            "tokens": [],
            "get_name": "Portefeuille de la carte",
            "has_user_card": True,
        },
        "serialized_transactions": transactions_json,
    }


def fausse_reponse_http(code_de_statut, corps_json):
    """Une réponse HTTP simulée (`requests.Response`) : un code et un corps JSON.
    / A faked HTTP response: a status code and a JSON body."""
    reponse = MagicMock()
    reponse.status_code = code_de_statut
    reponse.json.return_value = corps_json
    return reponse


@pytest.mark.parametrize(
    "vider_et_delier, action_attendue", [(True, "VID"), (False, "RFD")]
)
def test_client_card_refund_envoie_void_ou_refund_a_l_ancien_fedow(
    lieu, vider_et_delier, action_attendue
):
    """
    Le client de l'ancien Fedow (`NFCcardFedow.refund`), repris de LaBoutik V1 : il
    envoie `POST card/refund` avec le tag de la carte du client et celui de la carte
    primaire (en majuscules), et l'action `VID` (vider et délier) ou `RFD` (vider).
    Le serveur répond 205 ; le client rend les transactions de remboursement validées
    (`TransactionValidator`), dans `serialized_transactions`.
    L'envoi réseau (`_post`) est simulé : aucun appel réel.
    / The old Fedow client posts card/refund with both tags (upper case) and the VID or
    RFD action. The server answers 205; the client returns the validated transactions.
    """
    corps_de_la_reponse = reponse_de_l_ancien_fedow_au_vidage(
        tag_de_la_carte="ABCD1234", montants_repris=[400, 100]
    )

    with patch(
        "fedow_connect.fedow_api._post",
        return_value=fausse_reponse_http(205, corps_de_la_reponse),
    ) as envoi_simule:
        resultat = NFCcardFedow(fedow_config=MagicMock()).refund(
            user_card_firstTagId="abcd1234",
            primary_card_fisrtTagId="dcba4321",
            void=vider_et_delier,
        )

    assert envoi_simule.call_count == 1
    arguments_de_l_envoi = SIGNATURE_DE_L_ENVOI_A_FEDOW.bind(
        *envoi_simule.call_args.args, **envoi_simule.call_args.kwargs
    ).arguments
    assert arguments_de_l_envoi["path"].strip("/") == "card/refund"
    donnees_envoyees = arguments_de_l_envoi["data"]
    assert donnees_envoyees["user_card_firstTagId"] == "ABCD1234"
    assert donnees_envoyees["primary_card_fisrtTagId"] == "DCBA4321"
    assert donnees_envoyees["action"] == action_attendue

    montants_rendus = []
    uuids_rendus = []
    for transaction_rendue in resultat["serialized_transactions"]:
        montants_rendus.append(transaction_rendue["amount"])
        uuids_rendus.append(str(transaction_rendue["uuid"]))
    uuids_attendus = []
    for transaction_json in corps_de_la_reponse["serialized_transactions"]:
        uuids_attendus.append(transaction_json["uuid"])
    assert montants_rendus == [400, 100]
    assert uuids_rendus == uuids_attendus


@pytest.mark.parametrize(
    "code_de_statut, corps_de_la_reponse",
    [
        # 400 : le validateur de l'ancien Fedow (`CardRefundOrVoidValidator`) refuse.
        # DRF rend ses erreurs en JSON : `non_field_errors` pour une erreur de
        # `validate()`, le nom du champ pour une carte que le serveur ne trouve pas.
        # / 400: the old Fedow validator refuses; DRF returns its errors as JSON.
        (400, {"non_field_errors": ["Primary card must be in place primary cards"]}),
        (
            400,
            {
                "user_card_firstTagId": [
                    "Object with first_tag_id=ABCD1234 does not exist."
                ]
            },
        ),
        # 404 : route introuvable. / 404: route not found.
        (404, {"detail": "Not found."}),
        # 500 : erreur du serveur, corps HTML (pas de JSON lisible).
        # / 500: server error, HTML body (no readable JSON).
        (500, None),
    ],
)
def test_client_card_refund_reponse_en_erreur_leve_une_exception(
    lieu, code_de_statut, corps_de_la_reponse
):
    """
    L'ancien Fedow ne vide pas la carte : il répond 400 (son validateur refuse, par
    exemple une carte primaire inconnue de lui, ou une carte client introuvable), 404
    ou 500. Le client lève une exception dès le code de la réponse, et le message dit
    ce code : il ne rend JAMAIS un résultat vide en silence (le client de LaBoutik V1
    rendait `None`), sinon la caisse croirait la carte vidée là-bas et viderait le
    Fedow local seul.
    Le code dans le message prouve que le refus vient du code de la réponse, et pas
    d'une erreur plus loin (corps sans transactions lisibles).
    / The old Fedow does not empty the card (400, 404, 500). The client raises right
    on the status code, and the message carries that code: never a silent empty result.
    """
    reponse_refusee = MagicMock()
    reponse_refusee.status_code = code_de_statut
    reponse_refusee.content = b"<html>Server Error</html>"
    if corps_de_la_reponse is None:
        reponse_refusee.json.side_effect = ValueError("Le corps n'est pas du JSON.")
    else:
        reponse_refusee.json.return_value = corps_de_la_reponse

    with patch(
        "fedow_connect.fedow_api._post", return_value=reponse_refusee
    ) as envoi_simule:
        with pytest.raises(Exception) as erreur_levee:
            NFCcardFedow(fedow_config=MagicMock()).refund(
                user_card_firstTagId="ABCD1234",
                primary_card_fisrtTagId="DCBA4321",
                void=False,
            )

    # L'exception vient bien de la réponse du serveur, pas d'une méthode absente.
    # / The exception comes from the server response, not from a missing method.
    assert envoi_simule.call_count == 1
    assert str(code_de_statut) in str(erreur_levee.value)


# --------------------------------------------------------------------------
# 20h — Les deux Fedow vidés : la vente seulement, aucune ligne « Refund »
# / 20h — Both Fedow emptied: the sale only, no "Refund" line
# --------------------------------------------------------------------------


def test_vider_carte_deux_fedow_aucune_ligne_refund(lieu):
    """
    Le lieu est relié à l'ancien Fedow. Sur le Fedow local, la carte porte 5,00 € de
    monnaie locale et 3,00 € de monnaie fédérée ; sur l'ancien Fedow, 4,00 € de
    monnaie locale du lieu, 1,00 € de monnaie fédérée et 0,50 € de jetons cadeau.
    La vente `VIDAGE_CARTE` dit tout (D12) : son règlement espèces vaut −1300 (tout
    l'argent rendu : 500 + 300 + 400 + 100). Aucune ligne « Refund » sans vente n'est
    écrite sur la carte.
    / Local: 5.00 + FED 3.00; old Fedow: 4.00 + FED 1.00 + gift 0.50. The sale's cash
    payment is −1300; no "Refund" line without a sale.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    monnaie_federee = monnaie_federee_locale(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_federee, 300)
    faux_ancien_fedow, _transactions_distantes = ancien_fedow_simule(
        carte_du_client, [("TLF", 400), ("FED", 100), ("TNF", 50)]
    )

    reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_vidage(carte_du_client)
    reglements_especes = []
    for reglement in vente.reglements.filter(moyen=PaymentMethod.CASH):
        reglements_especes.append(reglement.montant)
    assert reglements_especes == [-1300]
    assert lignes_refund_de_la_carte(carte_du_client) == []
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 20i — Carte vide en local, mais avec un solde sur l'ancien Fedow
# / 20i — Card empty locally, but holding a balance on the old Fedow
# --------------------------------------------------------------------------


def test_vider_carte_vide_en_local_avec_solde_ancien_fedow(lieu):
    """
    Le lieu est relié à l'ancien Fedow. La carte n'a RIEN sur le Fedow local, mais
    porte 4,00 € de monnaie locale du lieu et 1,00 € de monnaie fédérée sur l'ancien
    Fedow. La vidange se fait dès qu'un des deux Fedow a quelque chose à reprendre
    (décision du mainteneur) : seul l'ancien Fedow est vidé.
    La vente a les deux règlements distants (LE +400, SF +100, uuid dans
    `reference_externe`) et espèces −500. Aucune transaction locale.
    / Nothing locally, 4.00 + FED 1.00 on the old Fedow: only the old Fedow is emptied.
    Sale: LE +400, SF +100 (remote), cash −500. No local transaction.
    """
    caisse = preparer_la_caisse(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    faux_ancien_fedow, transactions_distantes = ancien_fedow_simule(
        carte_du_client, [("TLF", 400), ("FED", 100)]
    )
    transaction_distante_monnaie_locale = transactions_distantes[0]
    transaction_distante_monnaie_federee = transactions_distantes[1]

    reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )

    assert reponse.status_code == 200
    assert 'data-testid="vider-carte-success"' in reponse.content.decode()
    assert faux_ancien_fedow.NFCcard.refund.call_count == 1
    assert not Transaction.objects.filter(
        card=carte_du_client, action=Transaction.REFUND
    ).exists()

    vente = retrouver_la_vente_de_vidage(carte_du_client)
    assert vente.statut == Vente.Statut.REGLEE
    assert reglements_de_la_vidange(vente) == sorted(
        [
            (
                PaymentMethod.LOCAL_EURO,
                400,
                None,
                str(transaction_distante_monnaie_locale["uuid"]),
            ),
            (
                PaymentMethod.STRIPE_FED,
                100,
                None,
                str(transaction_distante_monnaie_federee["uuid"]),
            ),
            (PaymentMethod.CASH, -500, None, ""),
        ],
        key=str,
    )
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 20j — Seulement des jetons cadeau : repris sur les deux Fedow, une vente (D8 bis)
# / 20j — Only gift tokens: taken back on both Fedow servers, one sale (D8 bis)
# --------------------------------------------------------------------------


def test_vider_carte_seulement_jetons_ecrit_une_vente(lieu):
    """
    Le lieu est relié à l'ancien Fedow. La carte ne porte que des jetons cadeau :
    2,00 € sur le Fedow local, 0,50 € sur l'ancien Fedow. Aucun argent n'est rendu.
    Les jetons sont repris sur les deux Fedow (le local par une transaction de
    remboursement vers le lieu). Des jetons perdus annulent la dette du lieu (D8 bis) :
    une vente `VIDAGE_CARTE` est écrite et encaissée, même sans argent. Elle a, par
    transaction de jetons repris, un article « Jetons cadeau repris au vidage » et un
    règlement « jetons » (LG) du même montant ; aucun règlement espèces. Aucune ligne
    « Refund » (anciens lecteurs) : l'article ne porte pas la carte.
    / Only gift tokens (2.00 local, 0.50 remote): taken back on both; a settled
    `VIDAGE_CARTE` sale is written, one item and one LG payment per token transaction,
    no cash payment, no Refund line.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_cadeau = monnaie_cadeau_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_cadeau, 200)
    faux_ancien_fedow, transactions_distantes = ancien_fedow_simule(
        carte_du_client, [("TNF", 50)]
    )
    transaction_distante_des_jetons = transactions_distantes[0]

    reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )

    assert reponse.status_code == 200
    assert 'data-testid="vider-carte-success"' in reponse.content.decode()
    assert faux_ancien_fedow.NFCcard.refund.call_count == 1
    assert solde_de_la_carte(carte_du_client, monnaie_cadeau) == 0
    remboursement_des_jetons_cadeau = remboursement_local_de_la_monnaie(
        carte_du_client, monnaie_cadeau
    )
    assert remboursement_des_jetons_cadeau.amount == 200

    vente = retrouver_la_vente_de_vidage(carte_du_client)
    assert vente.statut == Vente.Statut.REGLEE
    assert vente.numero is not None
    assert reglements_de_la_vidange(vente) == sorted(
        [
            (
                PaymentMethod.LOCAL_GIFT,
                200,
                str(remboursement_des_jetons_cadeau.uuid),
                "",
            ),
            (
                PaymentMethod.LOCAL_GIFT,
                50,
                None,
                str(transaction_distante_des_jetons["uuid"]),
            ),
        ],
        key=str,
    )
    verifier_les_articles_des_jetons_repris(vente, montants_attendus=[200, 50])
    assert not LigneArticle.objects.filter(carte=carte_du_client).exists()
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 20k — FED seulement sur l'ancien Fedow : le règlement SF porte la transaction distante
# / 20k — FED only on the old Fedow: the SF payment carries the remote transaction
# --------------------------------------------------------------------------


def test_vider_carte_fed_seulement_sur_l_ancien_fedow_reglement_sf_distant(
    lieu,
):
    """
    Le cas de la production : aucun FED n'existe sur le Fedow local (un FED local est
    interdit). La carte porte 5,00 € de monnaie locale en local, et 1,00 € de monnaie
    fédérée sur l'ancien Fedow. Le caissier la vide.
    La vente `VIDAGE_CARTE` a un règlement de monnaie fédérée (SF) de +100, avec l'uuid
    de la transaction distante dans `reference_externe`, et un règlement espèces de
    −600. Aucune ligne « Refund » (D12), pas d'erreur « aucun asset FED ».
    / Production case: no local FED. The sale has an SF +100 payment carrying the
    remote transaction, cash −600; no "Refund" line, no "no FED asset" error.
    """
    assert not Asset.objects.filter(category=Asset.FED).exists(), (
        "Ce test suppose qu'aucun FED n'existe sur le Fedow local (cas de la production)."
    )
    caisse = preparer_la_caisse(lieu)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    faux_ancien_fedow, transactions_distantes = ancien_fedow_simule(
        carte_du_client, [("FED", 100)]
    )
    transaction_distante_monnaie_federee = transactions_distantes[0]

    reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_vidage(carte_du_client)
    reglement_de_monnaie_federee = vente.reglements.get(moyen=PaymentMethod.STRIPE_FED)
    assert reglement_de_monnaie_federee.montant == 100
    assert reglement_de_monnaie_federee.reference_externe == str(
        transaction_distante_monnaie_federee["uuid"]
    )
    reglement_especes = vente.reglements.get(moyen=PaymentMethod.CASH)
    assert reglement_especes.montant == -600
    assert lignes_refund_de_la_carte(carte_du_client) == []
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 20l — « Vider et délier » une carte vide partout, mais connue de l'ancien Fedow
# / 20l — "Empty and unlink" a card empty everywhere, but known to the old Fedow
# --------------------------------------------------------------------------


def test_vider_et_delier_une_carte_vide_partout_la_delie_des_deux_cotes(lieu):
    """
    Le lieu est relié à l'ancien Fedow, qui connaît la carte d'un membre. La carte n'a
    rien, ni en local ni sur l'ancien Fedow. Le caissier coche « vider et délier ».
    La carte est déliée DES DEUX CÔTÉS (décision du mainteneur) : l'ancien Fedow
    reçoit `card/refund` en VOID, et la carte locale perd son membre et son
    portefeuille. Aucune vente n'est écrite (aucun argent), aucune ligne.
    / A card empty everywhere, known to the old Fedow, "empty and unlink": unlinked on
    BOTH sides (VOID sent, local card loses its member and wallet). No sale, no line.
    """
    caisse = preparer_la_caisse(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    membre = creer_utilisateur(prenom="Membre", nom="Vide")
    CarteCashless.objects.filter(pk=carte_du_client.pk).update(user=membre)
    carte_du_client.refresh_from_db()
    faux_ancien_fedow, _transactions_distantes = ancien_fedow_simule(
        carte_du_client, []
    )

    reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse,
        carte_du_client,
        faux_ancien_fedow,
        lieu_relie=True,
        vider_et_delier=True,
    )

    assert reponse.status_code == 200
    assert 'data-testid="vider-carte-success"' in reponse.content.decode()
    assert faux_ancien_fedow.NFCcard.refund.call_count == 1
    assert faux_ancien_fedow.NFCcard.refund.call_args.kwargs["void"] is True

    carte_du_client.refresh_from_db()
    assert carte_du_client.user is None
    assert carte_du_client.wallet_ephemere is None
    assert not Vente.objects.filter(
        nature=Vente.Nature.VIDAGE_CARTE, carte=carte_du_client
    ).exists()
    assert not LigneArticle.objects.filter(carte=carte_du_client).exists()


# ==========================================================================
# L'APERÇU, L'ÉCRAN DE SUCCÈS ET LE REÇU : SÉPARÉS PAR FEDOW, DÉTAILLÉS
# / THE PREVIEW, THE SUCCESS SCREEN AND THE RECEIPT: SPLIT BY FEDOW, DETAILED
# ==========================================================================
#
# Décision du mainteneur (fiche B §5, « B-3b », décision 3) : une partie « Fedow
# local », une partie « ancien Fedow », chacune avec une ligne par monnaie (jetons
# cadeau compris, affichés « repris, sans argent »), puis le total rendu en espèces.
#
# Ce que l'écran doit porter pour être lu par ces tests (et par Playwright) :
# - `data-testid="vider-carte-partie-fedow-local"` : la partie du Fedow local ;
# - `data-testid="vider-carte-partie-ancien-fedow"` : la partie de l'ancien Fedow ;
# - `data-testid="vider-carte-ligne"` : une ligne par monnaie, DANS sa partie ;
# - `data-testid="vider-carte-ancien-fedow-injoignable"` : l'aperçu dit que l'ancien
#   Fedow ne répond pas ;
# - le total reste dans `vider-carte-amount` (aperçu) et `vider-carte-success-amount`
#   (succès).
# / What the screen carries: one part per Fedow, one line per currency inside its part.

# Adresses de l'aperçu et de l'impression du reçu (laboutik/urls.py, PaiementViewSet).
# / Preview and receipt-printing addresses.
URL_DE_L_APERCU_DU_VIDAGE = "/laboutik/paiement/vider_carte/preview/"
URL_DE_L_IMPRESSION_DU_RECU = "/laboutik/paiement/vider_carte/imprimer_recu/"

# Les noms des monnaies de l'ancien Fedow, dans ces tests. Aucun ne contient le nom
# d'une monnaie du Fedow local (« Monnaie locale », « Cadeau ») : une ligne se
# retrouve par son nom sans confusion possible.
# / Old Fedow currency names in these tests; none contains a local currency name.
NOM_DE_LA_MONNAIE_DISTANTE = {
    "TLF": "Euro du lieu (ancien)",
    "FED": "Euro federe (ancien)",
    "TNF": "Bonus du lieu (ancien)",
}

# Le texte que le mainteneur veut lire sur une ligne de jetons cadeau.
# Les écrans et le reçu de ces tests sont demandés EN FRANÇAIS (en-tête
# `Accept-Language: fr`) : le client de test parle anglais par défaut
# (`client_connecte`), et une traduction anglaise changerait ce texte.
# / The wording the maintainer wants on a gift-token line. Screens and receipt are
# requested in French: the test client speaks English by default.
MENTION_DES_JETONS_CADEAU = "repris, sans argent"


def demander_les_ecrans_en_francais(caisse):
    """Toutes les requêtes suivantes du caissier demandent le français.
    / Every following cashier request asks for French."""
    caisse.client_du_caissier.defaults["HTTP_ACCEPT_LANGUAGE"] = "fr"


class LecteurDeLEcran(HTMLParser):
    """
    Lit le HTML rendu et garde, pour chaque élément qui porte un `data-testid` :
    son `data-testid`, ceux de ses parents, et son texte (espaces normalisés).
    / Reads the rendered HTML and keeps, for each element with a `data-testid`: its
    testid, its parents' testids, and its text.
    """

    # Les balises HTML sans fermeture : elles n'ouvrent aucun parent.
    # / Void HTML tags: they never open a parent.
    BALISES_SANS_FERMETURE = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements_ouverts = []
        self.elements_lus = []

    def handle_starttag(self, balise, attributs):
        if balise in self.BALISES_SANS_FERMETURE:
            return
        testid = dict(attributs).get("data-testid")
        self.elements_ouverts.append(
            {"balise": balise, "testid": testid, "morceaux_de_texte": []}
        )

    def handle_endtag(self, balise):
        # On ferme jusqu'à la dernière balise ouverte du même nom.
        # / Close up to the last open tag with the same name.
        position = len(self.elements_ouverts) - 1
        while position >= 0 and self.elements_ouverts[position]["balise"] != balise:
            position -= 1
        if position < 0:
            return
        while len(self.elements_ouverts) > position:
            element_ferme = self.elements_ouverts.pop()
            if element_ferme["testid"] is None:
                continue
            testids_des_parents = []
            for parent in self.elements_ouverts:
                if parent["testid"] is not None:
                    testids_des_parents.append(parent["testid"])
            self.elements_lus.append(
                SimpleNamespace(
                    testid=element_ferme["testid"],
                    testids_des_parents=testids_des_parents,
                    texte=texte_normalise(
                        "".join(element_ferme["morceaux_de_texte"])
                    ),
                )
            )

    def handle_data(self, texte):
        for element_ouvert in self.elements_ouverts:
            element_ouvert["morceaux_de_texte"].append(texte)


def texte_normalise(texte):
    """Le texte sans espaces multiples, les espaces insécables remplacées.
    / Text with collapsed spaces, non-breaking spaces replaced."""
    return " ".join(texte.replace(" ", " ").split())


def lire_l_ecran(reponse):
    """Les éléments à `data-testid` de la réponse HTML.
    / The response's elements carrying a `data-testid`."""
    lecteur = LecteurDeLEcran()
    lecteur.feed(reponse.content.decode())
    return lecteur.elements_lus


def texte_de_l_element(elements_lus, testid):
    """Le texte du premier élément qui porte ce `data-testid`, ou None.
    / Text of the first element with this testid, or None."""
    for element in elements_lus:
        if element.testid == testid:
            return element.texte
    return None


def lignes_de_la_partie(elements_lus, testid_de_la_partie):
    """Les textes des lignes (`vider-carte-ligne`) rangées DANS cette partie.
    / Texts of the lines inside this part."""
    textes_des_lignes = []
    for element in elements_lus:
        est_une_ligne = element.testid == "vider-carte-ligne"
        if est_une_ligne and testid_de_la_partie in element.testids_des_parents:
            textes_des_lignes.append(element.texte)
    return textes_des_lignes


def la_ligne_qui_nomme(textes_des_lignes, nom_de_la_monnaie):
    """L'unique ligne qui porte ce nom de monnaie.
    / The only line carrying this currency name."""
    lignes_trouvees = []
    for texte_de_la_ligne in textes_des_lignes:
        if nom_de_la_monnaie in texte_de_la_ligne:
            lignes_trouvees.append(texte_de_la_ligne)
    assert len(lignes_trouvees) == 1, (
        f"Attendu : une ligne « {nom_de_la_monnaie} », trouvé : {lignes_trouvees} "
        f"parmi {textes_des_lignes}."
    )
    return lignes_trouvees[0]


def montant_affiche(centimes):
    """Un montant comme l'écran l'affiche (filtre `cents_to_euros`), normalisé.
    / An amount as the screen shows it, normalised."""
    return texte_normalise(cents_to_euros(centimes))


def fiche_de_monnaie_distante(uuid_de_la_monnaie, categorie, du_lieu):
    """
    Une monnaie de l'ancien Fedow, comme `AssetValidator` la rend (données validées).
    `du_lieu` : la monnaie a été créée par CE lieu (son portefeuille d'origine est
    celui du lieu sur l'ancien Fedow). La monnaie fédérée vient de la coopérative,
    jamais du lieu.
    / A remote currency as `AssetValidator` returns it. `du_lieu`: created by THIS
    venue (origin wallet = the venue's wallet on the old Fedow).
    """
    configuration_fedow = FedowConfig.get_solo()
    if du_lieu:
        portefeuille_d_origine = configuration_fedow.fedow_place_wallet_uuid
        lieu_d_origine = {
            "uuid": configuration_fedow.fedow_place_uuid,
            "name": "Ce lieu",
            "wallet": configuration_fedow.fedow_place_wallet_uuid,
        }
        nom_de_la_monnaie = NOM_DE_LA_MONNAIE_DISTANTE[categorie]
    else:
        portefeuille_d_origine = uuid.uuid4()
        lieu_d_origine = {"uuid": uuid.uuid4(), "name": "Un autre lieu", "wallet": portefeuille_d_origine}
        nom_de_la_monnaie = f"Monnaie d'un autre lieu {categorie}"
    if categorie == "FED":
        lieu_d_origine = None
    return {
        "uuid": uuid_de_la_monnaie,
        "name": nom_de_la_monnaie,
        "currency_code": "EUR",
        "place_origin": lieu_d_origine,
        "wallet_origin": portefeuille_d_origine,
        "category": categorie,
        "get_category_display": categorie,
        "created_at": timezone.now(),
        "last_update": timezone.now(),
        "is_stripe_primary": categorie == "FED",
    }


def jeton_de_la_carte_distante(fiche_de_la_monnaie, montant_en_centimes):
    """Un jeton du portefeuille de la carte sur l'ancien Fedow (`TokenValidator`).
    / A token of the card's wallet on the old Fedow."""
    return {
        "uuid": uuid.uuid4(),
        "name": fiche_de_la_monnaie["name"],
        "value": montant_en_centimes,
        "asset": fiche_de_la_monnaie,
        "asset_uuid": fiche_de_la_monnaie["uuid"],
        "asset_name": fiche_de_la_monnaie["name"],
        "asset_category": fiche_de_la_monnaie["category"],
        "is_primary_stripe_token": fiche_de_la_monnaie["category"] == "FED",
        "last_transaction": None,
    }


def ancien_fedow_simule_avec_ses_soldes(
    carte_du_client, monnaies_reprises, monnaies_d_autres_lieux=()
):
    """
    L'ancien Fedow simulé (`ancien_fedow_simule`), complété pour l'aperçu et le reçu :
    / The faked old Fedow, completed for the preview and the receipt:

    - `NFCcard.retrieve(tag_id)` (lecture de la carte, sans débit) rend le portefeuille
      de la carte avec ses jetons : ceux que le vidage reprendra (`monnaies_reprises`)
      et ceux d'autres lieux (`monnaies_d_autres_lieux`), que le vidage ne reprend pas
      (../Fedow/fedow_core/serializers.py, `CardRefundOrVoidValidator` : jetons du lieu
      et monnaie fédérée seulement) ;
    - `asset.retrieve` / `asset.cached_retrieve` : la fiche de chaque monnaie, avec son
      nom (`NOM_DE_LA_MONNAIE_DISTANTE`) ;
    - `transaction.retrieve(uuid)` (relecture d'une transaction par son uuid) : la
      transaction REFUND telle que l'ancien Fedow l'a écrite, reçue par le portefeuille
      du lieu ; un uuid inconnu rend 404, comme `TransactionFedow.retrieve`.
    Les montants et les monnaies sont les mêmes dans les quatre réponses.

    Le portefeuille du lieu sur l'ancien Fedow est lu dans `FedowConfig` (base de dev :
    le lieu y est relié).

    :param monnaies_reprises: paires (catégorie, centimes) que le vidage reprend
    :param monnaies_d_autres_lieux: paires (catégorie, centimes) d'autres lieux
    :return: (le faux client, les transactions rendues par le vidage, le dict
        uuid → transaction relue, que le test peut compléter)
    """
    configuration_fedow = FedowConfig.get_solo()
    assert configuration_fedow.fedow_place_wallet_uuid is not None, (
        "Ce test suppose le lieu relié à l'ancien Fedow en base de dev "
        "(FedowConfig.fedow_place_wallet_uuid)."
    )
    faux_fedow, transactions_rendues = ancien_fedow_simule(
        carte_du_client, monnaies_reprises
    )

    fiche_par_monnaie = {}
    jetons_de_la_carte = []
    transaction_relue_par_uuid = {}
    for transaction_rendue in transactions_rendues:
        categorie = None
        for jeton_avant in faux_fedow.NFCcard.refund.return_value[
            "before_refund_serialized_wallet"
        ]["tokens"]:
            if str(jeton_avant["asset_uuid"]) == str(transaction_rendue["asset"]):
                categorie = jeton_avant["asset_category"]
                jeton_avant["asset_name"] = NOM_DE_LA_MONNAIE_DISTANTE[categorie]
                jeton_avant["name"] = NOM_DE_LA_MONNAIE_DISTANTE[categorie]
        fiche_de_la_monnaie = fiche_de_monnaie_distante(
            transaction_rendue["asset"], categorie, du_lieu=True
        )
        fiche_par_monnaie[str(transaction_rendue["asset"])] = fiche_de_la_monnaie
        jetons_de_la_carte.append(
            jeton_de_la_carte_distante(fiche_de_la_monnaie, transaction_rendue["amount"])
        )
        transaction_relue = dict(transaction_rendue)
        transaction_relue["receiver"] = configuration_fedow.fedow_place_wallet_uuid
        transaction_relue["card"] = None
        transaction_relue_par_uuid[str(transaction_rendue["uuid"])] = transaction_relue

    for categorie, montant_en_centimes in monnaies_d_autres_lieux:
        fiche_de_la_monnaie = fiche_de_monnaie_distante(
            uuid.uuid4(), categorie, du_lieu=False
        )
        fiche_par_monnaie[str(fiche_de_la_monnaie["uuid"])] = fiche_de_la_monnaie
        jetons_de_la_carte.append(
            jeton_de_la_carte_distante(fiche_de_la_monnaie, montant_en_centimes)
        )

    faux_fedow.NFCcard.retrieve.return_value["wallet"]["tokens"] = jetons_de_la_carte

    def fiche_de_la_monnaie_par_uuid(*arguments, **arguments_nommes):
        if arguments:
            uuid_demande = arguments[0]
        else:
            uuid_demande = arguments_nommes["uuid"]
        return fiche_par_monnaie[str(uuid_demande)]

    def transaction_par_uuid(*arguments, **arguments_nommes):
        if arguments:
            uuid_demande = arguments[0]
        else:
            uuid_demande = arguments_nommes["uuid"]
        return transaction_relue_par_uuid.get(str(uuid_demande), 404)

    faux_fedow.asset.retrieve.side_effect = fiche_de_la_monnaie_par_uuid
    faux_fedow.asset.cached_retrieve.side_effect = fiche_de_la_monnaie_par_uuid
    faux_fedow.transaction.retrieve.side_effect = transaction_par_uuid
    return faux_fedow, transactions_rendues, transaction_relue_par_uuid


def apercu_du_vidage(caisse, carte_du_client, faux_ancien_fedow, lieu_relie):
    """
    Le caissier scanne la carte : l'aperçu du vidage (vraie route de la caisse, requête
    HTMX). L'ancien Fedow est simulé, le lieu est relié ou non.
    / The cashier scans the card: the emptying preview (real route, HTMX request).

    :return: (la réponse HTTP, la fausse classe `FedowAPI`)
    """
    donnees_du_formulaire = {
        "tag_id": carte_du_client.tag_id,
        "tag_id_cm": caisse.carte_du_caissier.tag_id,
        "uuid_pv": str(caisse.point_de_vente.uuid),
    }
    with patch.object(FedowConfig, "can_fedow", return_value=lieu_relie):
        with patch(
            "laboutik.views.FedowAPI", return_value=faux_ancien_fedow
        ) as classe_fedow_api_simulee:
            reponse = caisse.client_du_caissier.post(
                URL_DE_L_APERCU_DU_VIDAGE,
                donnees_du_formulaire,
                HTTP_HX_REQUEST="true",
                HTTP_ACCEPT_LANGUAGE="fr",
            )
    return reponse, classe_fedow_api_simulee


class LecteurDuFormulaireDImpression(HTMLParser):
    """
    Lit les champs du formulaire « Imprimer le reçu » de l'écran de succès : ce que le
    navigateur posterait. Les noms des champs ne sont pas fixés par les tests.
    / Reads the fields of the success screen's "Print receipt" form.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.dans_le_formulaire = False
        self.champs = []

    def handle_starttag(self, balise, attributs):
        attributs_de_la_balise = dict(attributs)
        if balise == "form":
            adresse_postee = attributs_de_la_balise.get("hx-post") or ""
            self.dans_le_formulaire = "imprimer_recu" in adresse_postee
            return
        if balise == "input" and self.dans_le_formulaire:
            nom_du_champ = attributs_de_la_balise.get("name")
            if nom_du_champ:
                self.champs.append(
                    (nom_du_champ, attributs_de_la_balise.get("value") or "")
                )

    def handle_startendtag(self, balise, attributs):
        self.handle_starttag(balise, attributs)

    def handle_endtag(self, balise):
        if balise == "form":
            self.dans_le_formulaire = False


def champs_du_formulaire_d_impression(reponse_de_l_ecran_de_succes):
    """Les paires (nom, valeur) du formulaire d'impression du reçu.
    / The receipt print form's (name, value) pairs."""
    lecteur = LecteurDuFormulaireDImpression()
    lecteur.feed(reponse_de_l_ecran_de_succes.content.decode())
    assert lecteur.champs, "Aucun formulaire « Imprimer le reçu » sur l'écran de succès."
    return lecteur.champs


def poster_l_impression_du_recu(lieu, caisse, champs_postes, faux_ancien_fedow):
    """
    Le caissier touche « Imprimer le reçu » : la vraie route, avec les champs donnés.
    Le terminal a une imprimante (simulée) ; l'impression part en tâche Celery,
    interceptée par le lieu (`lieu.taches_demandees`). L'ancien Fedow est simulé.
    / The cashier taps "Print receipt": the real route. The printing Celery task is
    intercepted.

    :return: (la réponse HTTP, la liste des impressions demandées : les arguments de
        chaque tâche `imprimer_async`)
    """
    donnees_du_formulaire = {}
    for nom_du_champ, valeur_du_champ in champs_postes:
        donnees_du_formulaire.setdefault(nom_du_champ, []).append(valeur_du_champ)
    imprimante_du_terminal_simulee = SimpleNamespace(pk=uuid.uuid4())
    nombre_de_taches_avant = len(lieu.taches_demandees)
    with patch(
        "laboutik.views.imprimante_du_terminal",
        return_value=imprimante_du_terminal_simulee,
    ):
        with patch.object(FedowConfig, "can_fedow", return_value=True):
            with patch("laboutik.views.FedowAPI", return_value=faux_ancien_fedow):
                reponse = caisse.client_du_caissier.post(
                    URL_DE_L_IMPRESSION_DU_RECU,
                    donnees_du_formulaire,
                    HTTP_HX_REQUEST="true",
                    HTTP_ACCEPT_LANGUAGE="fr",
                )
    impressions_demandees = []
    for nom_de_la_tache, arguments in lieu.taches_demandees[nombre_de_taches_avant:]:
        if nom_de_la_tache == "imprimer_async":
            impressions_demandees.append(arguments)
    return reponse, impressions_demandees


def imprimer_le_recu(lieu, caisse, champs_postes, faux_ancien_fedow):
    """
    Le caissier imprime le reçu (`poster_l_impression_du_recu`) ; il faut exactement
    une impression demandée.
    / The cashier prints the receipt; exactly one print is expected.

    :return: (la réponse HTTP, le ticket envoyé à l'imprimante, un dict `ticket_data`)
    """
    reponse, impressions_demandees = poster_l_impression_du_recu(
        lieu, caisse, champs_postes, faux_ancien_fedow
    )
    assert len(impressions_demandees) == 1, (
        f"Attendu : une impression demandée, trouvé : {len(impressions_demandees)}. "
        f"Réponse : {reponse.content.decode()[:300]}"
    )
    ticket_envoye = impressions_demandees[0][1]
    return reponse, ticket_envoye


def texte_imprime(ticket_envoye):
    """
    Le texte que l'imprimante ESC/POS imprimerait pour ce ticket. On passe par le vrai
    constructeur (`build_escpos_from_ticket_data`) : une clé que l'imprimante ne lit
    pas ne s'imprime pas, et le test le voit.
    / The text an ESC/POS printer would print, through the real builder.
    """
    octets_imprimes = build_escpos_from_ticket_data(576, dict(ticket_envoye))
    return octets_imprimes.decode("utf-8", errors="ignore")


def parties_du_recu(texte_du_recu):
    """
    Le reçu coupé en trois : la partie « Fedow local », la partie « ancien Fedow »
    (jusqu'à la ligne du total), et la ligne « TOTAL ». La partie locale vient d'abord.
    / The receipt split in three: the local part, the old Fedow part, the TOTAL line.
    """
    texte_en_minuscules = texte_du_recu.lower()
    debut_de_la_partie_locale = texte_en_minuscules.find("fedow local")
    debut_de_la_partie_distante = texte_en_minuscules.find("ancien fedow")
    debut_du_total = texte_du_recu.find("TOTAL:")
    assert debut_du_total >= 0, f"Aucune ligne TOTAL sur le reçu :\n{texte_du_recu}"
    assert debut_de_la_partie_distante >= 0, (
        f"Aucune partie « ancien Fedow » sur le reçu :\n{texte_du_recu}"
    )
    partie_locale = ""
    if debut_de_la_partie_locale >= 0:
        assert debut_de_la_partie_locale < debut_de_la_partie_distante, (
            f"La partie « Fedow local » doit précéder l'ancien Fedow :\n{texte_du_recu}"
        )
        partie_locale = texte_du_recu[debut_de_la_partie_locale:debut_de_la_partie_distante]
    partie_distante = texte_du_recu[debut_de_la_partie_distante:debut_du_total]
    ligne_du_total = texte_du_recu[debut_du_total:].split("\n")[0]
    return partie_locale, partie_distante, ligne_du_total


def ligne_imprimee_qui_nomme(partie_du_recu, nom_de_la_monnaie):
    """L'unique ligne imprimée de cette partie qui porte ce nom de monnaie.
    / The only printed line of this part carrying this currency name."""
    lignes_trouvees = []
    for ligne_imprimee in partie_du_recu.split("\n"):
        if nom_de_la_monnaie in ligne_imprimee:
            lignes_trouvees.append(ligne_imprimee)
    assert len(lignes_trouvees) == 1, (
        f"Attendu : une ligne « {nom_de_la_monnaie} », trouvé : {lignes_trouvees} "
        f"dans :\n{partie_du_recu}"
    )
    return lignes_trouvees[0]


def vider_une_carte_sur_les_deux_fedow(lieu):
    """
    ÉTAT DE DÉPART commun à l'écran de succès et au reçu, puis le vidage à la caisse.
    Fedow local : 5,00 € de monnaie locale du lieu et 2,00 € de jetons cadeau.
    Ancien Fedow : 4,00 € de monnaie locale du lieu, 1,00 € de monnaie fédérée,
    0,50 € de jetons cadeau. Espèces rendues : 5,00 + 4,00 + 1,00 = 10,00 €.
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback).
    / Common starting state, then the emptying. Cash given back: 10.00.

    :return: SimpleNamespace(caisse, carte, monnaie_locale, monnaie_cadeau,
        faux_ancien_fedow, transactions_distantes, transaction_relue_par_uuid,
        reponse)
    """
    caisse = preparer_la_caisse(lieu)
    demander_les_ecrans_en_francais(caisse)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    monnaie_cadeau = monnaie_cadeau_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_cadeau, 200)
    faux_ancien_fedow, transactions_distantes, transaction_relue_par_uuid = (
        ancien_fedow_simule_avec_ses_soldes(
            carte_du_client, [("TLF", 400), ("FED", 100), ("TNF", 50)]
        )
    )
    reponse, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )
    assert reponse.status_code == 200
    return SimpleNamespace(
        caisse=caisse,
        carte=carte_du_client,
        monnaie_locale=monnaie_locale,
        monnaie_cadeau=monnaie_cadeau,
        faux_ancien_fedow=faux_ancien_fedow,
        transactions_distantes=transactions_distantes,
        transaction_relue_par_uuid=transaction_relue_par_uuid,
        reponse=reponse,
    )


# --------------------------------------------------------------------------
# 20m — L'aperçu est séparé par Fedow et détaillé, sans rien débiter
# / 20m — The preview is split by Fedow and detailed, debiting nothing
# --------------------------------------------------------------------------


def test_apercu_separe_fedow_local_et_ancien_fedow_sans_rien_debiter(lieu):
    """
    Le lieu est relié à l'ancien Fedow, qui connaît la carte.
    Fedow local : 5,00 € de monnaie locale du lieu, 2,00 € de jetons cadeau.
    Ancien Fedow : 4,00 € de monnaie locale du lieu, 1,00 € de monnaie fédérée,
    0,50 € de jetons cadeau du lieu, et 3,00 € de monnaie locale d'UN AUTRE lieu
    (que le vidage ne reprend pas).
    Le caissier scanne la carte. L'aperçu montre deux parties :
    - Fedow local : une ligne « Monnaie locale 5,00 € », une ligne « Cadeau …
      repris, sans argent » ;
    - ancien Fedow : trois lignes (4,00 €, 1,00 €, jetons cadeau « repris, sans
      argent ») ; la monnaie de l'autre lieu n'y est pas ;
    - « À rendre en espèces » : 10,00 €.
    L'aperçu ne débite rien : l'ancien Fedow n'est que lu (aucun `card/refund`), et en
    local aucun remboursement n'est écrit, les soldes sont intacts.
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback).
    / Preview split in two parts, one line per currency, gift tokens "taken back, no
    money", the other venue's currency absent, total 10.00. Nothing is debited.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    monnaie_cadeau = monnaie_cadeau_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_cadeau, 200)
    faux_ancien_fedow, _transactions, _relues = ancien_fedow_simule_avec_ses_soldes(
        carte_du_client,
        [("TLF", 400), ("FED", 100), ("TNF", 50)],
        monnaies_d_autres_lieux=[("TLF", 300)],
    )

    reponse, _classe_fedow_api = apercu_du_vidage(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )

    assert reponse.status_code == 200
    elements_lus = lire_l_ecran(reponse)
    assert texte_de_l_element(elements_lus, "vider-carte-confirm") is not None

    lignes_locales = lignes_de_la_partie(elements_lus, "vider-carte-partie-fedow-local")
    assert len(lignes_locales) == 2, lignes_locales
    assert montant_affiche(500) in la_ligne_qui_nomme(lignes_locales, monnaie_locale.name)
    assert MENTION_DES_JETONS_CADEAU in la_ligne_qui_nomme(
        lignes_locales, monnaie_cadeau.name
    )

    lignes_distantes = lignes_de_la_partie(
        elements_lus, "vider-carte-partie-ancien-fedow"
    )
    assert len(lignes_distantes) == 3, lignes_distantes
    assert montant_affiche(400) in la_ligne_qui_nomme(
        lignes_distantes, NOM_DE_LA_MONNAIE_DISTANTE["TLF"]
    )
    assert montant_affiche(100) in la_ligne_qui_nomme(
        lignes_distantes, NOM_DE_LA_MONNAIE_DISTANTE["FED"]
    )
    assert MENTION_DES_JETONS_CADEAU in la_ligne_qui_nomme(
        lignes_distantes, NOM_DE_LA_MONNAIE_DISTANTE["TNF"]
    )
    assert "Monnaie d'un autre lieu" not in reponse.content.decode()

    assert montant_affiche(1000) in texte_de_l_element(elements_lus, "vider-carte-amount")

    # Rien n'est débité, ni sur l'ancien Fedow, ni en local.
    # / Nothing is debited, on the old Fedow or locally.
    assert faux_ancien_fedow.NFCcard.refund.call_count == 0
    verifier_que_rien_n_est_ecrit_en_local(
        carte_du_client, [(monnaie_locale, 500), (monnaie_cadeau, 200)]
    )


# --------------------------------------------------------------------------
# 20n — Carte vide en local, solde sur l'ancien Fedow : l'aperçu l'accepte
# / 20n — Card empty locally, balance on the old Fedow: the preview accepts it
# --------------------------------------------------------------------------


def test_apercu_carte_vide_en_local_avec_solde_ancien_fedow_acceptee(lieu):
    """
    Le lieu est relié à l'ancien Fedow. La carte n'a RIEN sur le Fedow local, mais
    porte 4,00 € de monnaie locale du lieu sur l'ancien Fedow.
    Décision du mainteneur (a) : cette carte se vide. L'aperçu ne la refuse donc pas
    (pas de message « Aucun solde remboursable ») : il montre l'écran de confirmation,
    avec la partie « ancien Fedow » et 4,00 € à rendre en espèces.
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback).
    / Nothing locally, 4.00 on the old Fedow: the preview shows the confirmation
    screen, with the old Fedow part and 4.00 to give back.
    """
    caisse = preparer_la_caisse(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    faux_ancien_fedow, _transactions, _relues = ancien_fedow_simule_avec_ses_soldes(
        carte_du_client, [("TLF", 400)]
    )

    reponse, _classe_fedow_api = apercu_du_vidage(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )

    assert reponse.status_code == 200
    elements_lus = lire_l_ecran(reponse)
    assert texte_de_l_element(elements_lus, "alerte-messages") is None
    assert texte_de_l_element(elements_lus, "vider-carte-confirm") is not None
    lignes_distantes = lignes_de_la_partie(
        elements_lus, "vider-carte-partie-ancien-fedow"
    )
    assert montant_affiche(400) in la_ligne_qui_nomme(
        lignes_distantes, NOM_DE_LA_MONNAIE_DISTANTE["TLF"]
    )
    assert montant_affiche(400) in texte_de_l_element(elements_lus, "vider-carte-amount")
    assert faux_ancien_fedow.NFCcard.refund.call_count == 0


# --------------------------------------------------------------------------
# 20o — Lieu non relié ou carte inconnue : pas de partie « ancien Fedow »
# / 20o — Venue not linked or unknown card: no "old Fedow" part
# --------------------------------------------------------------------------


@pytest.mark.parametrize("pourquoi_local_seul", ["carte_inconnue", "lieu_non_relie"])
def test_apercu_sans_ancien_fedow_la_partie_distante_est_absente(
    lieu, pourquoi_local_seul
):
    """
    La carte porte 5,00 € de monnaie locale du lieu, sur le Fedow local.
    - « carte_inconnue » : le lieu est relié, mais l'ancien Fedow ne connaît pas la
      carte (réponse 404) ;
    - « lieu_non_relie » : le lieu n'est pas relié à l'ancien Fedow ; le client
      `FedowAPI` n'est même pas créé (sa création lancerait une création de place).
    L'aperçu montre la partie « Fedow local » (5,00 €) et AUCUNE partie « ancien
    Fedow » ; 5,00 € à rendre.
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback).
    / Local part only (5.00), no old Fedow part. Venue not linked: `FedowAPI` never
    built.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    lieu_relie = pourquoi_local_seul == "carte_inconnue"

    reponse, classe_fedow_api_simulee = apercu_du_vidage(
        caisse,
        carte_du_client,
        ancien_fedow_qui_ne_connait_pas_la_carte(),
        lieu_relie=lieu_relie,
    )

    assert reponse.status_code == 200
    elements_lus = lire_l_ecran(reponse)
    lignes_locales = lignes_de_la_partie(elements_lus, "vider-carte-partie-fedow-local")
    assert montant_affiche(500) in la_ligne_qui_nomme(lignes_locales, monnaie_locale.name)
    assert texte_de_l_element(elements_lus, "vider-carte-partie-ancien-fedow") is None
    assert montant_affiche(500) in texte_de_l_element(elements_lus, "vider-carte-amount")
    if not lieu_relie:
        assert classe_fedow_api_simulee.called is False


# --------------------------------------------------------------------------
# 20p — Ancien Fedow injoignable : l'aperçu le dit clairement
# / 20p — Old Fedow unreachable: the preview says so clearly
# --------------------------------------------------------------------------


def test_apercu_ancien_fedow_injoignable_le_dit_clairement(lieu):
    """
    Le lieu est relié à l'ancien Fedow, qui ne répond pas (erreur réseau). La carte
    porte 5,00 € de monnaie locale sur le Fedow local.
    L'aperçu ne plante pas (pas d'erreur 500) et le dit clairement : l'élément
    `vider-carte-ancien-fedow-injoignable` est affiché. (La vidange elle-même refusera :
    test 20d.)
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback).
    / Old Fedow unreachable: no server error, the preview shows the "unreachable"
    notice.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    faux_ancien_fedow = ancien_fedow_en_echec(carte_du_client, "serveur_injoignable")

    reponse, _classe_fedow_api = apercu_du_vidage(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )

    assert reponse.status_code < 500
    elements_lus = lire_l_ecran(reponse)
    assert (
        texte_de_l_element(elements_lus, "vider-carte-ancien-fedow-injoignable")
        is not None
    )
    assert faux_ancien_fedow.NFCcard.refund.call_count == 0


# --------------------------------------------------------------------------
# 20q — L'écran de succès est séparé par Fedow et détaillé
# / 20q — The success screen is split by Fedow and detailed
# --------------------------------------------------------------------------


def test_ecran_de_succes_separe_et_detaille(lieu):
    """
    La carte est vidée sur les deux Fedow (état de départ :
    `vider_une_carte_sur_les_deux_fedow`). L'écran de succès montre :
    - Fedow local : « Monnaie locale 5,00 € », « Cadeau … repris, sans argent » ;
    - ancien Fedow : 4,00 €, 1,00 €, jetons cadeau « repris, sans argent » ;
    - « Rendu en espèces » : 10,00 € (les jetons cadeau ne comptent pas).
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback).
    / Success screen: local part, old Fedow part, one line per currency, cash 10.00.
    """
    vidage = vider_une_carte_sur_les_deux_fedow(lieu)

    elements_lus = lire_l_ecran(vidage.reponse)
    assert texte_de_l_element(elements_lus, "vider-carte-success") is not None

    lignes_locales = lignes_de_la_partie(elements_lus, "vider-carte-partie-fedow-local")
    assert len(lignes_locales) == 2, lignes_locales
    assert montant_affiche(500) in la_ligne_qui_nomme(
        lignes_locales, vidage.monnaie_locale.name
    )
    assert MENTION_DES_JETONS_CADEAU in la_ligne_qui_nomme(
        lignes_locales, vidage.monnaie_cadeau.name
    )

    lignes_distantes = lignes_de_la_partie(
        elements_lus, "vider-carte-partie-ancien-fedow"
    )
    assert len(lignes_distantes) == 3, lignes_distantes
    assert montant_affiche(400) in la_ligne_qui_nomme(
        lignes_distantes, NOM_DE_LA_MONNAIE_DISTANTE["TLF"]
    )
    assert montant_affiche(100) in la_ligne_qui_nomme(
        lignes_distantes, NOM_DE_LA_MONNAIE_DISTANTE["FED"]
    )
    assert MENTION_DES_JETONS_CADEAU in la_ligne_qui_nomme(
        lignes_distantes, NOM_DE_LA_MONNAIE_DISTANTE["TNF"]
    )

    assert montant_affiche(1000) in texte_de_l_element(
        elements_lus, "vider-carte-success-amount"
    )


# --------------------------------------------------------------------------
# 20r — Le reçu imprimé est séparé par Fedow et détaillé
# / 20r — The printed receipt is split by Fedow and detailed
# --------------------------------------------------------------------------


def test_recu_imprime_separe_et_detaille(lieu):
    """
    La carte est vidée sur les deux Fedow (`vider_une_carte_sur_les_deux_fedow`), puis
    le caissier touche « Imprimer le reçu » : le navigateur poste le formulaire de
    l'écran de succès tel quel.
    Le reçu, lu tel que l'imprimante ESC/POS l'imprime, porte :
    - une partie « Fedow local » : « Monnaie locale » 5.00, « Cadeau » « repris, sans
      argent » ;
    - puis une partie « ancien Fedow » : 4.00, 1.00, jetons cadeau « repris, sans
      argent » ;
    - puis « TOTAL: 10.00 » : les espèces rendues (les jetons cadeau ne comptent pas).
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback ; l'impression est interceptée).
    / Receipt as printed: local part, then old Fedow part, then TOTAL 10.00.
    """
    vidage = vider_une_carte_sur_les_deux_fedow(lieu)
    champs_postes = champs_du_formulaire_d_impression(vidage.reponse)

    _reponse, ticket_envoye = imprimer_le_recu(
        lieu, vidage.caisse, champs_postes, vidage.faux_ancien_fedow
    )

    texte_du_recu = texte_imprime(ticket_envoye)
    partie_locale, partie_distante, ligne_du_total = parties_du_recu(texte_du_recu)

    assert "5.00" in ligne_imprimee_qui_nomme(partie_locale, vidage.monnaie_locale.name)
    assert MENTION_DES_JETONS_CADEAU in ligne_imprimee_qui_nomme(
        partie_locale, vidage.monnaie_cadeau.name
    ).lower()

    assert "4.00" in ligne_imprimee_qui_nomme(
        partie_distante, NOM_DE_LA_MONNAIE_DISTANTE["TLF"]
    )
    assert "1.00" in ligne_imprimee_qui_nomme(
        partie_distante, NOM_DE_LA_MONNAIE_DISTANTE["FED"]
    )
    assert MENTION_DES_JETONS_CADEAU in ligne_imprimee_qui_nomme(
        partie_distante, NOM_DE_LA_MONNAIE_DISTANTE["TNF"]
    ).lower()

    assert "10.00" in ligne_du_total


# --------------------------------------------------------------------------
# 20s — Le reçu ne croit pas les montants postés par le navigateur
# / 20s — The receipt does not trust amounts posted by the browser
# --------------------------------------------------------------------------


def test_recu_ne_croit_pas_les_montants_postes_par_le_navigateur(lieu):
    """
    La carte est vidée sur les deux Fedow (`vider_une_carte_sur_les_deux_fedow`). Le
    formulaire d'impression est falsifié avant d'être posté :
    - toute valeur de champ faite de chiffres devient « 99999 », et des champs
      « montant » et « total_centimes » à 99999 sont ajoutés ;
    - une transaction de l'ancien Fedow en plus est glissée à côté des vraies : elle
      existe là-bas (77,77 €), mais elle n'a pas été reçue par le portefeuille du lieu
      (ce n'est pas un remboursement de CE lieu).
    Le reçu relit chaque transaction : l'ancien Fedow par son uuid (montant, monnaie,
    destinataire), le Fedow local en base. Il imprime donc les vrais montants (4.00,
    1.00, TOTAL 10.00), jamais 999.99, et ignore la transaction glissée (pas de 77.77).
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback ; l'impression est interceptée).
    / The print form is tampered (amounts, an extra remote transaction of another
    wallet). The receipt re-reads every transaction and prints the real amounts only.
    """
    vidage = vider_une_carte_sur_les_deux_fedow(lieu)
    champs_du_formulaire = champs_du_formulaire_d_impression(vidage.reponse)

    # Une transaction qui existe sur l'ancien Fedow, mais reçue par un autre portefeuille.
    # / A transaction existing on the old Fedow, but received by another wallet.
    uuid_de_la_transaction_glissee = uuid.uuid4()
    transaction_glissee = dict(vidage.transactions_distantes[0])
    transaction_glissee["uuid"] = uuid_de_la_transaction_glissee
    transaction_glissee["amount"] = 7777
    transaction_glissee["receiver"] = uuid.uuid4()
    transaction_glissee["card"] = None
    vidage.transaction_relue_par_uuid[str(uuid_de_la_transaction_glissee)] = (
        transaction_glissee
    )

    uuids_des_transactions_distantes = set()
    for transaction_distante in vidage.transactions_distantes:
        uuids_des_transactions_distantes.add(str(transaction_distante["uuid"]))

    champs_falsifies = []
    noms_des_champs_des_transactions_distantes = set()
    for nom_du_champ, valeur_du_champ in champs_du_formulaire:
        if valeur_du_champ in uuids_des_transactions_distantes:
            noms_des_champs_des_transactions_distantes.add(nom_du_champ)
        if valeur_du_champ.lstrip("-").isdigit():
            valeur_du_champ = "99999"
        champs_falsifies.append((nom_du_champ, valeur_du_champ))
    assert noms_des_champs_des_transactions_distantes, (
        "Le formulaire d'impression doit porter l'uuid des transactions de l'ancien "
        "Fedow (source relue par le reçu)."
    )
    for nom_du_champ in noms_des_champs_des_transactions_distantes:
        champs_falsifies.append((nom_du_champ, str(uuid_de_la_transaction_glissee)))
    champs_falsifies.append(("montant", "99999"))
    champs_falsifies.append(("total_centimes", "99999"))

    _reponse, ticket_envoye = imprimer_le_recu(
        lieu, vidage.caisse, champs_falsifies, vidage.faux_ancien_fedow
    )

    texte_du_recu = texte_imprime(ticket_envoye)
    _partie_locale, partie_distante, ligne_du_total = parties_du_recu(texte_du_recu)
    assert "4.00" in ligne_imprimee_qui_nomme(
        partie_distante, NOM_DE_LA_MONNAIE_DISTANTE["TLF"]
    )
    assert "1.00" in ligne_imprimee_qui_nomme(
        partie_distante, NOM_DE_LA_MONNAIE_DISTANTE["FED"]
    )
    assert "10.00" in ligne_du_total
    assert "999.99" not in texte_du_recu
    assert "77.77" not in texte_du_recu


# --------------------------------------------------------------------------
# 20t — Carte vidée seulement sur l'ancien Fedow : le reçu s'imprime
# / 20t — Card emptied on the old Fedow only: the receipt prints
# --------------------------------------------------------------------------


def test_recu_d_une_carte_videe_seulement_sur_l_ancien_fedow(lieu):
    """
    Le lieu est relié à l'ancien Fedow. La carte n'a rien sur le Fedow local, et porte
    4,00 € de monnaie locale du lieu et 1,00 € de monnaie fédérée sur l'ancien Fedow.
    Elle est vidée (seul l'ancien Fedow a quelque chose à reprendre), puis le caissier
    imprime le reçu : il n'y a AUCUNE transaction locale, le reçu s'imprime quand même
    (pas de « Paramètres manquants »), avec la partie « ancien Fedow » (4.00, 1.00) et
    « TOTAL: 5.00 ».
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback ; l'impression est interceptée).
    / No local transaction: the receipt still prints, old Fedow part, TOTAL 5.00.
    """
    caisse = preparer_la_caisse(lieu)
    demander_les_ecrans_en_francais(caisse)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    faux_ancien_fedow, _transactions, _relues = ancien_fedow_simule_avec_ses_soldes(
        carte_du_client, [("TLF", 400), ("FED", 100)]
    )
    reponse_du_vidage, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )
    assert reponse_du_vidage.status_code == 200
    champs_postes = champs_du_formulaire_d_impression(reponse_du_vidage)

    _reponse, ticket_envoye = imprimer_le_recu(
        lieu, caisse, champs_postes, faux_ancien_fedow
    )

    texte_du_recu = texte_imprime(ticket_envoye)
    _partie_locale, partie_distante, ligne_du_total = parties_du_recu(texte_du_recu)
    assert "4.00" in ligne_imprimee_qui_nomme(
        partie_distante, NOM_DE_LA_MONNAIE_DISTANTE["TLF"]
    )
    assert "1.00" in ligne_imprimee_qui_nomme(
        partie_distante, NOM_DE_LA_MONNAIE_DISTANTE["FED"]
    )
    assert "5.00" in ligne_du_total


# --------------------------------------------------------------------------
# 20u — Ancien Fedow injoignable au moment d'imprimer : impression refusée
# / 20u — Old Fedow unreachable when printing: printing refused
# --------------------------------------------------------------------------


def test_recu_ancien_fedow_injoignable_a_l_impression_refuse_l_impression(lieu):
    """
    La carte est vidée sur les deux Fedow (`vider_une_carte_sur_les_deux_fedow`).
    Puis l'ancien Fedow cesse de répondre (erreur réseau), et le caissier touche
    « Imprimer le reçu ». Le reçu ne peut pas relire les transactions de l'ancien
    Fedow : l'impression est REFUSÉE (décision du mainteneur : jamais de reçu partiel).
    Aucune impression n'est demandée, la caisse affiche un message d'avertissement,
    pas d'erreur 500.
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback ; l'impression est interceptée).
    / Old Fedow unreachable at print time: no print requested, a warning, no 500.
    """
    vidage = vider_une_carte_sur_les_deux_fedow(lieu)
    champs_postes = champs_du_formulaire_d_impression(vidage.reponse)
    erreur_reseau = requests.ConnectionError(
        "Ancien Fedow injoignable (simulé par le test)."
    )
    vidage.faux_ancien_fedow.transaction.retrieve.side_effect = erreur_reseau
    vidage.faux_ancien_fedow.asset.retrieve.side_effect = erreur_reseau
    vidage.faux_ancien_fedow.asset.cached_retrieve.side_effect = erreur_reseau

    reponse, impressions_demandees = poster_l_impression_du_recu(
        lieu, vidage.caisse, champs_postes, vidage.faux_ancien_fedow
    )

    assert reponse.status_code < 500
    assert impressions_demandees == []
    elements_lus = lire_l_ecran(reponse)
    assert texte_de_l_element(elements_lus, "alerte-messages") is not None


# --------------------------------------------------------------------------
# 20v — Le reçu imprime le nom et l'adresse du lieu
# / 20v — The receipt prints the venue's name and address
# --------------------------------------------------------------------------


def test_recu_imprime_le_nom_et_l_adresse_du_lieu(lieu):
    """
    Le lieu s'appelle « Le Bar des Essais », au 12 rue des Essais, 97400 Saint-Denis
    (réglages changés en mémoire, jamais enregistrés : tests/PIEGES.md 13.22). La
    carte est vidée sur les deux Fedow, puis le reçu est imprimé.
    Le texte imprimé porte le nom du lieu et son adresse : ce sont des mentions
    légales du reçu.
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback ; l'impression est interceptée).
    / The printed receipt carries the venue's name and address.
    """
    with configuration_modifiee(
        organisation="Le Bar des Essais",
        adress="12 rue des Essais",
        postal_code=97400,
        city="Saint-Denis",
    ):
        vidage = vider_une_carte_sur_les_deux_fedow(lieu)
        champs_postes = champs_du_formulaire_d_impression(vidage.reponse)
        _reponse, ticket_envoye = imprimer_le_recu(
            lieu, vidage.caisse, champs_postes, vidage.faux_ancien_fedow
        )

    texte_du_recu = texte_imprime(ticket_envoye)
    assert "Le Bar des Essais" in texte_du_recu
    assert "12 rue des Essais 97400 Saint-Denis" in texte_du_recu


# --------------------------------------------------------------------------
# 20w — Seulement des jetons cadeau : l'aperçu accepte la carte
# / 20w — Only gift tokens: the preview accepts the card
# --------------------------------------------------------------------------


def test_apercu_carte_avec_seulement_des_jetons_cadeau_acceptee(lieu):
    """
    Le lieu est relié à l'ancien Fedow. La carte ne porte que des jetons cadeau :
    2,00 € sur le Fedow local, 0,50 € sur l'ancien Fedow. La vidange les reprend
    (décision du mainteneur, 5 ter) : l'aperçu accepte donc la carte (pas de message
    « Aucun solde remboursable »). Il montre les deux lignes « repris, sans argent »,
    une par Fedow, et 0,00 € à rendre en espèces.
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback).
    / Only gift tokens: the preview shows both "taken back, no money" lines and 0.00.
    """
    caisse = preparer_la_caisse(lieu)
    monnaie_cadeau = monnaie_cadeau_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_cadeau, 200)
    faux_ancien_fedow, _transactions, _relues = ancien_fedow_simule_avec_ses_soldes(
        carte_du_client, [("TNF", 50)]
    )

    reponse, _classe_fedow_api = apercu_du_vidage(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )

    assert reponse.status_code == 200
    elements_lus = lire_l_ecran(reponse)
    assert texte_de_l_element(elements_lus, "alerte-messages") is None
    lignes_locales = lignes_de_la_partie(elements_lus, "vider-carte-partie-fedow-local")
    assert MENTION_DES_JETONS_CADEAU in la_ligne_qui_nomme(
        lignes_locales, monnaie_cadeau.name
    )
    lignes_distantes = lignes_de_la_partie(
        elements_lus, "vider-carte-partie-ancien-fedow"
    )
    assert MENTION_DES_JETONS_CADEAU in la_ligne_qui_nomme(
        lignes_distantes, NOM_DE_LA_MONNAIE_DISTANTE["TNF"]
    )
    assert montant_affiche(0) in texte_de_l_element(elements_lus, "vider-carte-amount")
    assert faux_ancien_fedow.NFCcard.refund.call_count == 0


# --------------------------------------------------------------------------
# 20x — Carte vide partout, connue de l'ancien Fedow : l'aperçu propose de la délier
# / 20x — Card empty everywhere, known to the old Fedow: the preview offers to unlink it
# --------------------------------------------------------------------------


def test_apercu_carte_vide_partout_connue_de_l_ancien_fedow_propose_de_la_delier(lieu):
    """
    Le lieu est relié à l'ancien Fedow, qui connaît la carte d'un membre. La carte n'a
    rien, ni en local ni sur l'ancien Fedow. La vidange sait la délier des deux côtés
    (« vider et délier », test 20l) : l'aperçu accepte donc la carte (pas de message
    « Aucun solde remboursable ») et propose SEULEMENT de réinitialiser la carte
    (`vider-carte-btn-reinit`). Le bouton « garder le compte » n'est pas proposé : sans
    rien à reprendre, cette vidange échouerait.
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback).
    / Card empty everywhere, known to the old Fedow: the preview only offers to reset
    the card.
    """
    caisse = preparer_la_caisse(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    membre = creer_utilisateur(prenom="Membre", nom="Vide")
    CarteCashless.objects.filter(pk=carte_du_client.pk).update(user=membre)
    carte_du_client.refresh_from_db()
    faux_ancien_fedow, _transactions, _relues = ancien_fedow_simule_avec_ses_soldes(
        carte_du_client, []
    )

    reponse, _classe_fedow_api = apercu_du_vidage(
        caisse, carte_du_client, faux_ancien_fedow, lieu_relie=True
    )

    assert reponse.status_code == 200
    elements_lus = lire_l_ecran(reponse)
    assert texte_de_l_element(elements_lus, "alerte-messages") is None
    assert texte_de_l_element(elements_lus, "vider-carte-btn-reinit") is not None
    assert texte_de_l_element(elements_lus, "vider-carte-btn-keep-user") is None
    assert faux_ancien_fedow.NFCcard.refund.call_count == 0


# --------------------------------------------------------------------------
# 20y — Le reçu ignore une transaction du lieu qui n'est pas un remboursement
# / 20y — The receipt ignores a venue transaction that is not a refund
# --------------------------------------------------------------------------


def test_recu_ignore_une_transaction_du_lieu_qui_n_est_pas_un_remboursement(lieu):
    """
    La carte est vidée sur les deux Fedow (`vider_une_carte_sur_les_deux_fedow`). Une
    transaction de l'ancien Fedow est glissée dans le formulaire d'impression : elle
    est bien reçue par le portefeuille du lieu, mais c'est une VENTE (action « QRS »,
    paiement par QR code), de 33,33 €, pas un remboursement.
    Le reçu ne garde que les remboursements : pas de 33.33, TOTAL toujours 10.00.
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback ; l'impression est interceptée).
    / A venue transaction that is a sale (QRS), not a refund, is ignored by the receipt.
    """
    vidage = vider_une_carte_sur_les_deux_fedow(lieu)
    champs_du_formulaire = champs_du_formulaire_d_impression(vidage.reponse)

    uuid_de_la_vente_glissee = uuid.uuid4()
    vente_glissee = dict(
        vidage.transaction_relue_par_uuid[str(vidage.transactions_distantes[0]["uuid"])]
    )
    vente_glissee["uuid"] = uuid_de_la_vente_glissee
    vente_glissee["amount"] = 3333
    vente_glissee["action"] = "QRS"
    vente_glissee["get_action_display"] = "Qrcode sale"
    vidage.transaction_relue_par_uuid[str(uuid_de_la_vente_glissee)] = vente_glissee

    champs_postes = list(champs_du_formulaire)
    champs_postes.append(
        ("transaction_uuids_ancien_fedow", str(uuid_de_la_vente_glissee))
    )

    _reponse, ticket_envoye = imprimer_le_recu(
        lieu, vidage.caisse, champs_postes, vidage.faux_ancien_fedow
    )

    texte_du_recu = texte_imprime(ticket_envoye)
    _partie_locale, _partie_distante, ligne_du_total = parties_du_recu(texte_du_recu)
    assert "33.33" not in texte_du_recu
    assert "10.00" in ligne_du_total


# --------------------------------------------------------------------------
# 20z — Un uuid posté deux fois n'est imprimé qu'une fois
# / 20z — A uuid posted twice is printed once
# --------------------------------------------------------------------------


def test_recu_un_uuid_poste_deux_fois_n_est_imprime_qu_une_fois(lieu):
    """
    La carte est vidée sur les deux Fedow (`vider_une_carte_sur_les_deux_fedow`). Le
    formulaire d'impression est posté avec chaque uuid de l'ancien Fedow EN DOUBLE.
    Le reçu relit chaque transaction une seule fois : une seule ligne « Euro du lieu
    (ancien) » à 4.00, et le TOTAL reste 10.00 (pas 15.00).
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback ; l'impression est interceptée).
    / Each remote uuid posted twice: printed once, TOTAL stays 10.00.
    """
    vidage = vider_une_carte_sur_les_deux_fedow(lieu)
    champs_du_formulaire = champs_du_formulaire_d_impression(vidage.reponse)

    champs_postes = list(champs_du_formulaire)
    for transaction_distante in vidage.transactions_distantes:
        champs_postes.append(
            ("transaction_uuids_ancien_fedow", str(transaction_distante["uuid"]))
        )

    _reponse, ticket_envoye = imprimer_le_recu(
        lieu, vidage.caisse, champs_postes, vidage.faux_ancien_fedow
    )

    texte_du_recu = texte_imprime(ticket_envoye)
    _partie_locale, partie_distante, ligne_du_total = parties_du_recu(texte_du_recu)
    assert "4.00" in ligne_imprimee_qui_nomme(
        partie_distante, NOM_DE_LA_MONNAIE_DISTANTE["TLF"]
    )
    assert "10.00" in ligne_du_total


# --------------------------------------------------------------------------
# 20z bis — Titres de partie et lignes sans argent : sans « 1 x » sur le papier
# / 20z bis — Part titles and no-money lines: no "1 x" on paper
# --------------------------------------------------------------------------


def test_recu_titres_et_lignes_sans_argent_imprimes_sans_quantite(lieu):
    """
    La carte est vidée sur les deux Fedow (`vider_une_carte_sur_les_deux_fedow`), puis
    le reçu est imprimé. Les titres de partie (« FEDOW LOCAL », « ANCIEN FEDOW ») et
    les lignes de jetons cadeau (« repris, sans argent ») ne sont pas des articles :
    ils s'impriment SEULS, sans le préfixe de quantité « 1 x » d'un article sans prix.
    Contrôlé sur les deux imprimantes : ESC/POS (`build_escpos_from_ticket_data`,
    une ligne de texte par ligne imprimée) et Sunmi interne
    (`ticket_data_to_json_commands`, une commande texte par ligne).
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback ; l'impression est interceptée).
    / Part titles and gift-token lines print alone, without "1 x", on both printers.
    """
    vidage = vider_une_carte_sur_les_deux_fedow(lieu)
    champs_postes = champs_du_formulaire_d_impression(vidage.reponse)
    _reponse, ticket_envoye = imprimer_le_recu(
        lieu, vidage.caisse, champs_postes, vidage.faux_ancien_fedow
    )

    # Les lignes attendues seules : les deux titres, et les deux lignes de jetons
    # cadeau (une par Fedow), repérées par le nom de leur monnaie.
    # / The lines expected alone: both titles and both gift-token lines.
    debuts_des_lignes_seules = [
        "FEDOW LOCAL",
        "ANCIEN FEDOW",
        vidage.monnaie_cadeau.name,
        NOM_DE_LA_MONNAIE_DISTANTE["TNF"],
    ]

    # ESC/POS : une ligne de texte par ligne imprimée. Les codes de mise en page qui
    # précèdent parfois une ligne ne gênent pas : on cherche le préfixe « 1 x »
    # collé au texte attendu.
    # / ESC/POS: one text line per printed line; look for "1 x " glued to the text.
    lignes_imprimees = texte_imprime(ticket_envoye).split("\n")
    for debut_attendu in debuts_des_lignes_seules:
        lignes_trouvees = []
        for ligne_imprimee in lignes_imprimees:
            if debut_attendu in ligne_imprimee:
                lignes_trouvees.append(ligne_imprimee)
        assert len(lignes_trouvees) == 1, (debut_attendu, lignes_imprimees)
        assert f"1 x {debut_attendu}" not in lignes_trouvees[0], (
            f"ESC/POS : « {debut_attendu} » est imprimé comme un article : "
            f"{lignes_trouvees[0]!r}"
        )

    # Sunmi interne : une commande texte par ligne.
    # / Sunmi built-in: one text command per line.
    textes_des_commandes = []
    for commande in ticket_data_to_json_commands(dict(ticket_envoye)):
        if commande.get("type") == "text":
            textes_des_commandes.append(commande.get("value", ""))
    for debut_attendu in debuts_des_lignes_seules:
        commandes_trouvees = []
        for texte_de_la_commande in textes_des_commandes:
            if debut_attendu in texte_de_la_commande:
                commandes_trouvees.append(texte_de_la_commande)
        assert len(commandes_trouvees) == 1, (debut_attendu, textes_des_commandes)
        assert commandes_trouvees[0].startswith(debut_attendu), (
            f"Sunmi : « {debut_attendu} » n'est pas imprimé seul : {commandes_trouvees[0]!r}"
        )


# --------------------------------------------------------------------------
# 21 — Popup « retour carte » → « Vider » : le nouveau solde est le RÉEL
# / 21 — Card popup → "Vider": the new balance is the REAL one
# --------------------------------------------------------------------------


def vider_la_carte_depuis_la_popup_retour_carte(caisse, carte_du_client, faux_ancien_fedow):
    """
    Le caissier choisit « Vider » dans la popup retour carte (`action_carte=vider`) :
    la carte reste au client. Le lieu est relié à l'ancien Fedow (simulé).
    / The cashier picks "Vider" in the card popup: the card stays with the customer.
    """
    donnees_du_formulaire = {
        "tag_id": carte_du_client.tag_id,
        "tag_id_cm": caisse.carte_du_caissier.tag_id,
        "uuid_pv": str(caisse.point_de_vente.uuid),
        "vider_carte": "false",
        "action_carte": "vider",
    }
    with patch.object(FedowConfig, "can_fedow", return_value=True):
        with patch("laboutik.views.FedowAPI", return_value=faux_ancien_fedow):
            return caisse.client_du_caissier.post(
                URL_DU_VIDAGE_DE_CARTE, donnees_du_formulaire
            )


def lignes_du_nouveau_solde(elements_lus, testid_de_la_partie):
    """Les textes des lignes du nouveau solde (`vider-carte-nouveau-solde-ligne`)
    rangées DANS cette partie.
    / Texts of the new-balance lines inside this part."""
    textes_des_lignes = []
    for element in elements_lus:
        est_une_ligne = element.testid == "vider-carte-nouveau-solde-ligne"
        if est_une_ligne and testid_de_la_partie in element.testids_des_parents:
            textes_des_lignes.append(element.texte)
    return textes_des_lignes


def test_popup_vider_nouveau_solde_par_monnaie_relu_sur_l_ancien_fedow(lieu):
    """
    Fedow local : 5,00 € de monnaie locale du lieu (reprise). Ancien Fedow : 4,00 € de
    monnaie locale du lieu (reprise). APRÈS le vidage, la carte garde sur l'ancien
    Fedow 3,00 € d'une monnaie d'un autre lieu et 1,50 h de monnaie temps (relues sur
    le serveur), que le vidage ne reprend pas.
    L'écran final « vider » montre : rendu 9,00 € (les deux Fedow) ; un tableau
    Monnaie · Solde avec une partie « Ancien Fedow » de deux lignes (3,00 € et la
    monnaie temps dans son unité), jamais additionnées ; aucune partie « Fedow local »
    (tout y a été repris) ; pas de « Carte vide ».
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback).
    / Final "vider" screen: 9.00 given back; one "Ancien Fedow" part, one line per
    currency (3.00 € and the time currency), never added together.
    """
    caisse = preparer_la_caisse(lieu)
    demander_les_ecrans_en_francais(caisse)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    faux_ancien_fedow, _transactions_distantes = ancien_fedow_simule(
        carte_du_client, [("TLF", 400)]
    )

    # Première lecture (avant le vidage) : la fiche simulée. Seconde lecture (après le
    # vidage) : la carte garde deux monnaies non reprises.
    # / First read (before): the faked card. Second read (after): two currencies remain.
    fiche_avant_le_vidage = faux_ancien_fedow.NFCcard.retrieve.return_value
    fiche_apres_le_vidage = dict(fiche_avant_le_vidage)
    fiche_apres_le_vidage["wallet"] = dict(fiche_avant_le_vidage["wallet"])
    fiche_apres_le_vidage["wallet"]["tokens"] = [
        {
            "uuid": uuid.uuid4(),
            "name": "Jeton d'un autre lieu",
            "value": 300,
            "asset_uuid": uuid.uuid4(),
            "asset_name": "Monnaie d'un autre lieu",
            "asset_category": "TLF",
            "asset": {"currency_code": "EUR"},
            "is_primary_stripe_token": False,
        },
        {
            "uuid": uuid.uuid4(),
            "name": "Jeton temps",
            "value": 150,
            "asset_uuid": uuid.uuid4(),
            "asset_name": "Monnaie temps du test",
            "asset_category": "TIM",
            "asset": {"currency_code": "TMP"},
            "is_primary_stripe_token": False,
        },
    ]
    faux_ancien_fedow.NFCcard.retrieve.side_effect = [
        fiche_avant_le_vidage,
        fiche_apres_le_vidage,
    ]

    reponse = vider_la_carte_depuis_la_popup_retour_carte(
        caisse, carte_du_client, faux_ancien_fedow
    )

    assert reponse.status_code == 200
    assert faux_ancien_fedow.NFCcard.refund.call_count == 1
    assert faux_ancien_fedow.NFCcard.retrieve.call_count == 2
    elements_lus = lire_l_ecran(reponse)
    assert montant_affiche(900) in texte_de_l_element(
        elements_lus, "vider-carte-success-amount"
    )
    assert texte_de_l_element(elements_lus, "vider-carte-success-carte-vide") is None
    assert texte_de_l_element(elements_lus, "vider-carte-nouveau-solde-fedow-local") is None

    lignes_distantes = lignes_du_nouveau_solde(
        elements_lus, "vider-carte-nouveau-solde-ancien-fedow"
    )
    assert len(lignes_distantes) == 2, lignes_distantes
    assert montant_affiche(300) in la_ligne_qui_nomme(
        lignes_distantes, "Monnaie d'un autre lieu"
    )
    ligne_de_la_monnaie_temps = la_ligne_qui_nomme(lignes_distantes, "Monnaie temps du test")
    assert "TMP" in ligne_de_la_monnaie_temps, ligne_de_la_monnaie_temps
    assert "€" not in ligne_de_la_monnaie_temps, ligne_de_la_monnaie_temps
    # Jamais d'addition de deux monnaies : 3,00 + 1,50 n'apparaît nulle part.
    # / Two currencies are never added: 4.50 appears nowhere.
    assert montant_affiche(450) not in texte_normalise(reponse.content.decode())

    vente = retrouver_la_vente_de_vidage(carte_du_client)
    assert vente.statut == Vente.Statut.REGLEE
    verifier_egalites(vente)


def test_popup_vider_ancien_fedow_muet_apres_le_vidage_aucun_chiffre_invente(lieu):
    """
    Le vidage réussit sur les deux Fedow, puis l'ancien Fedow ne répond plus quand la
    caisse relit la carte. L'écran final « vider » : la partie « Ancien Fedow » du
    nouveau solde dit qu'il ne répond pas, sans aucun chiffre ni ligne ; pas de
    « Carte vide » (on ne le sait pas). La vente du vidage est bien écrite.
    CE QUE LE TEST LAISSE : rien (`django_db`, rollback).
    / Old Fedow silent after the emptying: its part says so, no figure, no "empty card".
    """
    caisse = preparer_la_caisse(lieu)
    demander_les_ecrans_en_francais(caisse)
    monnaie_locale = monnaie_locale_propre_au_lieu(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(carte_du_client, monnaie_locale, 500)
    faux_ancien_fedow, _transactions_distantes = ancien_fedow_simule(
        carte_du_client, [("TLF", 400)]
    )
    fiche_avant_le_vidage = faux_ancien_fedow.NFCcard.retrieve.return_value
    faux_ancien_fedow.NFCcard.retrieve.side_effect = [
        fiche_avant_le_vidage,
        requests.ConnectionError("Ancien Fedow injoignable (simulé par le test)."),
    ]

    reponse = vider_la_carte_depuis_la_popup_retour_carte(
        caisse, carte_du_client, faux_ancien_fedow
    )

    assert reponse.status_code == 200
    elements_lus = lire_l_ecran(reponse)
    assert montant_affiche(900) in texte_de_l_element(
        elements_lus, "vider-carte-success-amount"
    )
    texte_de_la_partie_distante = texte_de_l_element(
        elements_lus, "vider-carte-nouveau-solde-ancien-fedow"
    )
    assert texte_de_la_partie_distante is not None
    assert "ne répond pas" in texte_de_la_partie_distante
    assert "€" not in texte_de_la_partie_distante, texte_de_la_partie_distante
    assert lignes_du_nouveau_solde(
        elements_lus, "vider-carte-nouveau-solde-ancien-fedow"
    ) == []
    assert texte_de_l_element(elements_lus, "vider-carte-success-carte-vide") is None

    vente = retrouver_la_vente_de_vidage(carte_du_client)
    assert vente.statut == Vente.Statut.REGLEE
    verifier_egalites(vente)
