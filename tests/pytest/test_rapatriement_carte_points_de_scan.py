"""
Rapatriement des cartes de l'ancien Fedow : les points de scan (caisse, borne, tireuse).
/ Fetching cards from the old Fedow: the scan points (register, kiosk, tap).

LOCALISATION : tests/pytest/test_rapatriement_carte_points_de_scan.py

Spec : TECH_DOC/SESSIONS/QRCODECASHLESS/CHANTIER-02-rapatriement-cartes-fedow.md (§ 8.4).
Les numéros des tests (« test 32 ») renvoient à la matrice du § 8.4 de la spec. Le
service lui-même est testé dans test_rapatriement_carte_fedow.py (tests 1 à 28), et
l'écran de la carte primaire dans test_caisse_ouverture_ancien_fedow.py (29 et 30).
/ Test numbers refer to the § 8.4 matrix of the spec.

CE QUI EST TESTÉ
Pour chaque point de scan branché sur `trouver_ou_rapatrier_la_carte` (§ 4.3) :
(a) une carte connue SEULEMENT de l'ancien Fedow (absente en local, émise par le lieu
    courant) est rapatriée, et le parcours aboutit ;
(b) une carte d'un lieu encore sur l'ancien moteur (legacy) est refusée : l'écran le dit
    (`CarteDUnLieuNonMigre`), rien n'est créé ;
(c) l'ancien Fedow en panne : l'écran dit « Fedow injoignable » (`FedowInjoignable`), et
    la borne dit « La carte n'a pas pu être lue ».
Puis : 41 les sites non branchés n'interrogent jamais l'ancien Fedow ; 42 aucun site
n'appelle le service dans un bloc atomic de la vue ; 43 un tag inconnu partout donne
« Carte inconnue » sans erreur 500 ; 44 la démo ne crée plus la carte « inconnue ».
/ For each scan point: (a) fetched and the flow succeeds, (b) legacy refusal shown,
(c) outage shown. Then 41 to 44.

L'ANCIEN FEDOW EST SIMULÉ, JAMAIS APPELÉ
- Une garde (fixture automatique) fait échouer tout envoi réseau du client Fedow
  (`fedow_connect.fedow_api._get` / `_post`) ; la liste des envois tentés doit être vide
  à la fin de chaque test.
- La lecture d'une carte par le service est simulée par
  `patch.object(NFCcardFedow, "retrieve")` : c'est la cible unique du service (§ 8.1).
  `FedowAPI().NFCcard` est une instance de `NFCcardFedow` : la borne, qui lit la carte
  par `kiosk.carte.FedowAPI`, passe par la même simulation. La lecture du FED d'une
  carte par la caisse et la tireuse (`lire_depensable_fed_frais`, par la fiche de la
  carte) aussi : `tags_demandes` compte donc le rapatriement ET ces lectures.
- La lecture du portefeuille de la carte (`NFCcardFedow.card_tag_id_retrieve`, appelée
  par `obtenir_wallet_carte_depuis_fedow` au premier paiement) est simulée de même : elle
  rend le portefeuille « miroir » de la fiche, créé par le test avec son solde.
- Les refus (b) et (c) sont simulés par la réponse de l'ancien Fedow, pas en patchant le
  service : fiche d'un autre lieu passé en legacy (`lespass_domain`), ou panne réseau.
/ The old Fedow is faked at the `NFCcardFedow` class level; a guard forbids real calls.

PIÈGES (tests/PIEGES.md)
- CarteCashless est en SHARED_APPS : pas de FastTenantTestCase (9.30).
- Le service lit connection.tenant : tenant_context (vrai Client), jamais schema_context
  (9.1).
- tag_id et number sont uniques en base : valeurs hexadécimales neuves à chaque test
  (11.10). Tout est annulé par la transaction `django_db` (base de dev partagée).
- Les vues activent une langue sans la remettre : fixture autouse (10.5).
- Sous `django_db`, chaque test tourne déjà dans un atomic : le test 42 compare la
  profondeur des savepoints au moment de l'appel avec celle du début du test (§ 8.1).

Lancer / Run :
    make test ARGS="tests/pytest/test_rapatriement_carte_points_de_scan.py -q"
"""

import html
import re
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.conf import settings
from django.db import connection
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from AuthBillet.models import TermUser, TibilletUser, Wallet
from BaseBillet.models import LigneArticle, Membership, Product
from BaseBillet.models_vente import Vente
from Customers.models import Client
from fabriques_controlvanne import donner_une_carte_primaire_au_lieu
from fabriques_panier import (
    configuration_modifiee,
    creer_adhesion,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fedow_connect.fedow_api import CarteInconnueDeFedow, NFCcardFedow
from fedow_connect.models import FedowConfig
from fedow_core.models import Token
from fedow_core.services import WalletService
from QrcodeCashless.models import CarteCashless
from QrcodeCashless.services import trouver_ou_rapatrier_la_carte
from test_caisse_ecrit_la_vente import (
    cle_de_panier,
    creer_un_article_de_caisse,
    monnaie_locale_du_lieu,
    nouvelle_cle_d_idempotence,
    payer_le_reste_avec_une_deuxieme_carte,
    retrouver_la_vente_de_la_cle,
)
from test_caisse_ouverture_ancien_fedow import (
    ouvrir_la_caisse,
)
from test_caisse_ouverture_ancien_fedow import (
    preparer_la_caisse as preparer_l_ouverture_de_la_caisse,
)
from test_caisse_vider_carte_deux_fedow import (
    URL_DE_L_APERCU_DU_VIDAGE,
    URL_DU_VIDAGE_DE_CARTE,
    ancien_fedow_simule_avec_ses_soldes,
    retrouver_la_vente_de_vidage,
)
from test_caisse_vider_carte_deux_fedow import (
    preparer_la_caisse as preparer_le_vidage_a_la_caisse,
)
from test_caracterisation_caisse import (
    creer_un_point_de_vente,
    creer_une_carte_nfc_chargee,
    payer_a_la_caisse,
)
from test_caracterisation_en_ligne import creer_un_administrateur_du_lieu
from test_qrcode_ecrit_la_vente import (
    _fiches_des_monnaies,
    _transaction_de_l_ancien_fedow,
)
from test_rapatriement_carte_fedow import fiche_de_l_ancien_fedow
from test_tireuse_ancien_fedow import _creer_une_carte as creer_une_carte_de_tireuse
from test_tireuse_ancien_fedow import _creer_une_tireuse, _poster

pytestmark = pytest.mark.django_db

# Adresses des vues (laboutik/urls.py, kiosk/urls.py, BaseBillet/urls.py).
# / View addresses.
URL_DU_PAIEMENT_CAISSE = "/laboutik/paiement/payer/"
URL_DE_L_IDENTIFICATION_DU_CLIENT = "/laboutik/paiement/identifier_client/"
URL_DU_RETOUR_CARTE = "/laboutik/paiement/retour_carte/"
URL_DE_LA_ZONE_RECHARGER = "/laboutik/paiement/recharge_carte/"
URL_DE_LA_LECTURE_DE_CARTE_PAR_LA_BORNE = "/kiosk/check_request_card/"
URL_DU_RECAPITULATIF_DE_LA_BORNE = "/kiosk/recapitulatif/"
URL_DE_LA_GENERATION_DU_QRCODE = "/qrcodescanpay/generate_qrcode/"
URL_DE_LA_LECTURE_DE_CARTE_DU_QRCODE = "/qrcodescanpay/process_with_nfc/"

# Les messages des points de scan (msgid en français, QrcodeCashless/services.py).
# / The scan points' messages (French msgid).
MESSAGE_LIEU_NON_MIGRE = (
    "Cette carte vient d'un lieu qui n'utilise pas encore le nouveau moteur TiBillet."
)
MESSAGE_FEDOW_INJOIGNABLE = (
    "Fedow injoignable : la carte n'a pas pu être vérifiée. Réessayez."
)
MESSAGE_BORNE_CARTE_ILLISIBLE = "La carte n'a pas pu être lue. Merci de réessayer."
MESSAGE_CARTE_INCONNUE = "Carte inconnue"

# Le domaine du lieu `lespass` de la base de dev. / The dev `lespass` venue domain.
DOMAINE_DU_LIEU = "lespass.tibillet.localhost"


# --------------------------------------------------------------------------
# Gardes et contexte
# / Guards and context
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les vues activent une langue sans la remettre (tests/PIEGES.md, 10.5).
    / Views activate a language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture(autouse=True)
def aucun_appel_reseau_vers_l_ancien_fedow():
    """
    Garde : aucun test de ce fichier n'appelle le vrai ancien Fedow. Tout envoi réseau
    du client Fedow (`_post`, `_get`) échoue, et la liste des envois tentés doit être
    vide à la fin du test.
    / Guard: no test calls the real old Fedow.
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
    Le lieu `lespass`, caisse activée, avec Celery simulé, connexion posée sur son
    schéma pendant tout le test. La caisse est activée EN MÉMOIRE :
    `configuration_modifiee()` ne sauve jamais la `Configuration` (tests/PIEGES.md 13.22).
    / The `lespass` venue, register switched on in memory, Celery faked.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    taches_demandees=taches_demandees,
                )


@pytest.fixture
def lieu_legacy(tenant):
    """
    Un autre lieu, qui a un domaine principal, passé sur l'ancien moteur (legacy). La
    transaction du test annule ce changement à la fin.
    / Another venue with a primary domain, switched to the legacy engine (rolled back).
    """
    for lieu_candidat in Client.objects.exclude(
        schema_name__in=["public", tenant.schema_name]
    ).order_by("schema_name"):
        if lieu_candidat.get_primary_domain() is not None:
            Client.objects.filter(pk=lieu_candidat.pk).update(
                moteur_monnaie=Client.MOTEUR_LEGACY
            )
            return lieu_candidat
    pytest.fail("Aucun autre lieu avec un domaine principal dans la base de dev.")


# --------------------------------------------------------------------------
# L'ancien Fedow, simulé
# / The old Fedow, faked
# --------------------------------------------------------------------------


def tag_neuf():
    """Un tag NFC neuf : 8 caractères hexadécimaux majuscules (PIEGES 11.10).
    / A fresh NFC tag: 8 uppercase hexadecimal characters."""
    return uuid.uuid4().hex[:8].upper()


def uuid_de_la_place_fedow_du_lieu():
    """
    L'uuid de la place Fedow du lieu courant, lu dans sa vraie configuration. Le
    service reconnaît une carte « du lieu courant » à cet uuid.
    / The current venue's Fedow place uuid, from its real configuration.
    """
    uuid_de_la_place = FedowConfig.get_solo().fedow_place_uuid
    if uuid_de_la_place is None:
        pytest.fail(
            "Le lieu lespass n'a pas de place Fedow (FedowConfig.fedow_place_uuid) "
            "dans la base de dev : ces tests supposent un lieu relié."
        )
    return uuid_de_la_place


def carte_connue_seulement_de_fedow(monnaie=None, solde_en_centimes=0):
    """
    Une carte chargée chez l'ancien Fedow (`import_cards`) et absente en local : sa
    fiche Fedow (émise par le lieu courant), et le portefeuille « miroir » que le
    `CardValidator` aurait écrit pendant la lecture (même uuid, sans origine).
    `monnaie` et `solde_en_centimes` : un solde posé sur ce portefeuille, en monnaie
    locale (fedow_core), pour les parcours qui débitent ou affichent la carte.
    / A card loaded on the old Fedow and missing locally: its record and its mirror
    wallet (same uuid, no origin), optionally with a local balance.
    """
    tag_id = tag_neuf()
    portefeuille_miroir = Wallet.objects.create(
        uuid=uuid.uuid4(),
        name=f"TEST_rapatriement portefeuille miroir {tag_id}",
    )
    if monnaie is not None and solde_en_centimes > 0:
        Token.objects.create(
            wallet=portefeuille_miroir,
            asset=monnaie,
            value=solde_en_centimes,
        )
    fiche = fiche_de_l_ancien_fedow(
        tag_id,
        uuid_de_la_place=uuid_de_la_place_fedow_du_lieu(),
        uuid_du_portefeuille=portefeuille_miroir.uuid,
    )
    return SimpleNamespace(
        tag_id=tag_id,
        fiche=fiche,
        portefeuille_miroir=portefeuille_miroir,
    )


def carte_d_un_lieu_legacy(lieu_legacy):
    """
    Une carte connue de l'ancien Fedow, émise par un lieu encore sur l'ancien moteur :
    sa fiche porte le domaine de ce lieu (`lespass_domain`), et une place Fedow qui
    n'est pas celle du lieu courant.
    / A card issued by a venue still on the legacy engine.
    """
    tag_id = tag_neuf()
    fiche = fiche_de_l_ancien_fedow(
        tag_id,
        uuid_de_la_place=uuid.uuid4(),
        lespass_domain=lieu_legacy.get_primary_domain().domain,
    )
    return SimpleNamespace(tag_id=tag_id, fiche=fiche)


def panne_de_l_ancien_fedow():
    """Une panne réseau de l'ancien Fedow. / An old Fedow network outage."""
    return requests.exceptions.ConnectionError(
        "Ancien Fedow injoignable (simulé par le test)."
    )


@contextmanager
def ancien_fedow_simule(fiches=(), panne=None):
    """
    L'ancien Fedow, simulé au niveau de la classe `NFCcardFedow` (le service ET
    `FedowAPI().NFCcard` passent par elle). Le lieu est dit relié (`can_fedow`).
    / The old Fedow, faked at the `NFCcardFedow` class level. The venue is linked.

    - `fiches` : les cartes que l'ancien Fedow connaît. `retrieve` rend leur fiche ;
      un autre tag répond `CarteInconnueDeFedow` (le 404 de Fedow) ;
    - `card_tag_id_retrieve` (lecture du portefeuille au premier paiement) rend le
      portefeuille de la fiche, carte anonyme ; un tag inconnu rend None ;
    - `panne` : une exception levée par les deux lectures, pour tous les tags.
    Rend `SimpleNamespace(tags_demandes)` : un tag par appel à `retrieve`, qu'il vienne
    du rapatriement ou de la lecture du FED de la carte (`lire_depensable_fed_frais`).
    """
    fiche_par_tag = {}
    for fiche in fiches:
        fiche_par_tag[fiche["first_tag_id"]] = fiche
    tags_demandes = []

    def faux_retrieve(self, tag_id):
        tags_demandes.append(tag_id)
        if panne is not None:
            raise panne
        fiche_connue = fiche_par_tag.get(tag_id)
        if fiche_connue is None:
            raise CarteInconnueDeFedow(f"Carte inconnue de Fedow : {tag_id}")
        return fiche_connue

    def faux_card_tag_id_retrieve(self, card_number):
        if panne is not None:
            raise panne
        fiche_connue = fiche_par_tag.get(card_number)
        if fiche_connue is None:
            return None
        return {
            "wallet_uuid": fiche_connue["wallet"]["uuid"],
            "is_wallet_ephemere": True,
        }

    with patch.object(FedowConfig, "can_fedow", return_value=True):
        with patch.object(NFCcardFedow, "retrieve", new=faux_retrieve):
            with patch.object(
                NFCcardFedow, "card_tag_id_retrieve", new=faux_card_tag_id_retrieve
            ):
                yield SimpleNamespace(tags_demandes=tags_demandes)


# --------------------------------------------------------------------------
# Assistants de lecture
# / Reading helpers
# --------------------------------------------------------------------------


def texte_de_l_element(reponse, testid):
    """
    Le texte d'un élément simple (`<p>`, `<strong>`…) repéré par son `data-testid`,
    entités HTML décodées, espaces normalisés. None si l'élément est absent.
    / The text of a simple element found by its data-testid, or None.
    """
    contenu = reponse.content.decode()
    trouve = re.search(rf'data-testid="{testid}"[^>]*>(.*?)</', contenu, re.DOTALL)
    if trouve is None:
        return None
    return " ".join(html.unescape(trouve.group(1)).split())


def message_de_la_caisse(reponse):
    """Le message d'alerte de la caisse (`hx_messages.html`).
    / The register's alert message."""
    return texte_de_l_element(reponse, "alerte-messages-texte")


def message_de_la_fiche_de_carte(reponse):
    """
    Le message d'erreur de la fiche de la carte (« check carte », `hx_card_feedback.html`).
    / The error message of the card check popup.
    """
    contenu = reponse.content.decode()
    assert 'data-testid="retour-carte-erreur"' in contenu, contenu[:600]
    trouve = re.search(r'id="card-solde-titre">(.*?)</strong>', contenu, re.DOTALL)
    assert trouve is not None, contenu[:600]
    return " ".join(html.unescape(trouve.group(1)).split())


def message_de_la_borne(reponse):
    """Le message d'erreur de la borne. / The kiosk error message."""
    return texte_de_l_element(reponse, "kiosk-error-message")


def la_carte_existe_en_local(tag_id):
    """Une CarteCashless porte-t-elle ce tag ? / Does a local card carry this tag?"""
    return CarteCashless.objects.filter(tag_id=tag_id).exists()


def verifier_la_carte_rapatriee(lieu, carte_fedow):
    """
    La carte est maintenant en local, avec les identifiants de sa fiche Fedow, et
    rattachée à une génération (`Detail`) du lieu courant.
    / The card is now local, with its Fedow identifiers, attached to the venue.
    """
    carte_locale = CarteCashless.objects.get(tag_id=carte_fedow.tag_id)
    assert carte_locale.number == carte_fedow.fiche["number_printed"]
    assert str(carte_locale.uuid) == str(carte_fedow.fiche["qrcode_uuid"])
    assert carte_locale.detail.origine_id == lieu.tenant.pk
    return carte_locale


def solde_du_portefeuille(portefeuille, monnaie):
    """Le solde du portefeuille dans cette monnaie (centimes), relu en base.
    / The wallet's balance in this currency (cents)."""
    return WalletService.obtenir_solde(wallet=portefeuille, asset=monnaie)


def client_du_caissier(lieu):
    """
    Le client HTTP d'un administrateur du lieu connecté, qui demande les écrans en
    français : sans carte primaire, la caisse accepte la session d'un administrateur.
    / A logged-in venue admin client asking for French screens.
    """
    client_http = creer_un_administrateur_du_lieu(lieu)
    client_http.defaults["HTTP_ACCEPT_LANGUAGE"] = "fr"
    return client_http


# --------------------------------------------------------------------------
# Les parcours de chaque point de scan : préparer, puis scanner
# / Each scan point's flow: prepare, then scan
# --------------------------------------------------------------------------
# Chaque point de scan a deux fonctions : `preparer_...(lieu)` fabrique ce qu'il faut
# pour arriver jusqu'au scan (point de vente, articles, client HTTP) ; `scanner_...`
# envoie la requête avec le tag lu. L'ancien Fedow est simulé par le test, autour du
# scan. Le test 42 rejoue les mêmes parcours avec un espion sur le service.
# / Each scan point has a `preparer_...` and a `scanner_...` function.


# --- 30 bis : CaisseViewSet._identifier_adherent (adhésion en espèces) ---


def preparer_une_adhesion_en_especes(lieu):
    """Une adhésion à 20 € au point de vente, et le caissier.
    / A 20 € membership at the point of sale, and the cashier."""
    adhesion = creer_adhesion(prix="20.00")
    return SimpleNamespace(
        lieu=lieu,
        adhesion=adhesion,
        point_de_vente=creer_un_point_de_vente([adhesion.produit]),
        client_http=client_du_caissier(lieu),
        email_de_l_adherente=f"test+rapatriement{identifiant_unique()}@mock.test",
        cartes_liees_chez_fedow=[],
    )


def scanner_une_adhesion_en_especes(preparation, tag_id):
    """
    Le caissier vend l'adhésion en espèces, sans recharge : l'adhérente donne son
    e-mail et pose sa carte. La déclaration du membre à Fedow est simulée (elle pose
    un portefeuille sur l'utilisatrice, comme le vrai client), la liaison de la carte
    chez Fedow (`linkwallet_card_number`) aussi : chaque appel est noté.
    / The cashier sells the membership in cash; the member gives her email and taps
    her card. Fedow declaration and card linking are faked and recorded.
    """

    def declarer_en_posant_un_portefeuille(utilisateur, tenant=None, ip=None):
        utilisateur.wallet = Wallet.objects.create(
            name=f"TEST_rapatriement portefeuille de {utilisateur.email}",
            origin=tenant,
        )
        utilisateur.save(update_fields=["wallet"])

    def lier_la_carte(self, user=None, card_number=None):
        preparation.cartes_liees_chez_fedow.append(card_number)
        return {"first_tag_id": card_number}

    with patch(
        "fedow_connect.services.declarer_wallet_user_a_fedow",
        side_effect=declarer_en_posant_un_portefeuille,
    ):
        with patch.object(NFCcardFedow, "linkwallet_card_number", new=lier_la_carte):
            return payer_a_la_caisse(
                preparation.client_http,
                preparation.point_de_vente,
                preparation.adhesion,
                quantite=1,
                moyen_de_paiement="espece",
                autres_champs={
                    "tag_id": tag_id,
                    "email_adhesion": preparation.email_de_l_adherente,
                    "prenom_adhesion": "Ada",
                    "nom_adhesion": "Lovelace",
                },
            )


def adhesion_enregistree(preparation):
    """L'adhésion vendue, au nom de l'adhérente (ou None).
    / The sold membership, in the member's name (or None)."""
    return Membership.objects.filter(
        user__email=preparation.email_de_l_adherente,
        price=preparation.adhesion.tarif,
    ).first()


# --- 31 : PaiementViewSet.identifier_client ---


def preparer_l_identification_du_client(lieu):
    """Une adhésion au panier : la caisse demande qui est le client.
    / A membership in the cart: the register asks who the customer is."""
    adhesion = creer_adhesion(prix="15.00")
    return SimpleNamespace(
        lieu=lieu,
        adhesion=adhesion,
        point_de_vente=creer_un_point_de_vente([adhesion.produit]),
        client_http=client_du_caissier(lieu),
    )


def scanner_pour_identifier_le_client(preparation, tag_id):
    """Le client pose sa carte sur l'écran « qui est le client ? ».
    / The customer taps the card on the "who is the customer?" screen."""
    adhesion = preparation.adhesion
    return preparation.client_http.post(
        URL_DE_L_IDENTIFICATION_DU_CLIENT,
        {
            "tag_id": tag_id,
            "uuid_pv": str(preparation.point_de_vente.uuid),
            f"repid-{adhesion.produit.uuid}--{adhesion.tarif.uuid}": "1",
            "panier_a_adhesions": "True",
            "moyens_paiement": "espece",
        },
    )


# --- 32 : PaiementViewSet._payer_par_nfc ---


def preparer_un_paiement_nfc(lieu):
    """Une bière à 5 € au point de vente, et le caissier.
    / A 5 € beer at the point of sale, and the cashier."""
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    return SimpleNamespace(
        lieu=lieu,
        biere=biere,
        point_de_vente=creer_un_point_de_vente([biere.produit]),
        client_http=client_du_caissier(lieu),
    )


def scanner_pour_payer_en_nfc(preparation, tag_id):
    """Le client paie la bière avec sa carte. / The customer pays with the card."""
    return payer_a_la_caisse(
        preparation.client_http,
        preparation.point_de_vente,
        preparation.biere,
        quantite=1,
        moyen_de_paiement="nfc",
        autres_champs={"tag_id": tag_id},
    )


# --- 33 et 34 : _payer_en_especes et _payer_par_carte_ou_cheque (recharge) ---


def preparer_une_recharge(lieu):
    """
    Une recharge de 10 € en monnaie locale du lieu (celle que la caisse lit), au point
    de vente, et le caissier.
    / A 10 € top-up in the venue's local currency, and the cashier.
    """
    monnaie_locale = monnaie_locale_du_lieu(lieu)
    recharge = creer_un_article_de_caisse(
        "recharge",
        prix_en_euros="10.00",
        taux_tva="0.00",
        methode_caisse=Product.RECHARGE_EUROS,
        asset=monnaie_locale,
    )
    return SimpleNamespace(
        lieu=lieu,
        monnaie_locale=monnaie_locale,
        recharge=recharge,
        point_de_vente=creer_un_point_de_vente([recharge.produit]),
        client_http=client_du_caissier(lieu),
    )


def scanner_pour_une_recharge_en_especes(preparation, tag_id):
    """Le client recharge sa carte, payée en espèces.
    / The customer tops up the card, paid in cash."""
    return payer_a_la_caisse(
        preparation.client_http,
        preparation.point_de_vente,
        preparation.recharge,
        quantite=1,
        moyen_de_paiement="espece",
        autres_champs={"tag_id": tag_id},
    )


def scanner_pour_une_recharge_par_cheque(preparation, tag_id):
    """Le client recharge sa carte, payée par chèque.
    / The customer tops up the card, paid by cheque."""
    return payer_a_la_caisse(
        preparation.client_http,
        preparation.point_de_vente,
        preparation.recharge,
        quantite=1,
        moyen_de_paiement="CH",
        autres_champs={"tag_id": tag_id},
    )


# --- 35 : PaiementViewSet._rembourser_consigne_par_nfc ---


def preparer_un_retour_de_consigne(lieu):
    """
    Un gobelet consigné à 1 €, et son retour de consigne relié (D11), crédité en
    monnaie locale du lieu.
    / A 1 € deposit cup and its linked deposit return, credited in local currency.
    """
    monnaie_locale = monnaie_locale_du_lieu(lieu)
    gobelet = creer_un_article_de_caisse(
        "gobelet", prix_en_euros="1.00", taux_tva="20.00"
    )
    retour_de_consigne = creer_un_article_de_caisse(
        "retour consigne",
        prix_en_euros="-1.00",
        taux_tva="20.00",
        methode_caisse=Product.RETOUR_CONSIGNE,
        asset=monnaie_locale,
    )
    Product.objects.filter(pk=retour_de_consigne.produit.pk).update(
        consigne_remboursee=gobelet.produit
    )
    return SimpleNamespace(
        lieu=lieu,
        monnaie_locale=monnaie_locale,
        retour_de_consigne=retour_de_consigne,
        point_de_vente=creer_un_point_de_vente([retour_de_consigne.produit]),
        client_http=client_du_caissier(lieu),
    )


def scanner_pour_rembourser_la_consigne(preparation, tag_id):
    """Le client rend son gobelet : la consigne est créditée sur sa carte.
    / The customer returns the cup: the deposit is credited on the card."""
    return payer_a_la_caisse(
        preparation.client_http,
        preparation.point_de_vente,
        preparation.retour_de_consigne,
        quantite=1,
        moyen_de_paiement="nfc",
        autres_champs={"tag_id": tag_id},
    )


# --- 36 : PaiementViewSet._executer_paiement_complementaire (seconde carte) ---


def preparer_un_paiement_a_deux_cartes(lieu):
    """
    Trois jus à 3,50 € (10,50 €). La carte 1, locale, porte 5,00 € : il reste 5,50 € à
    payer avec une seconde carte.
    / Three juices (10.50 €); card 1 holds 5.00 €; 5.50 € is left for a second card.
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    return SimpleNamespace(
        lieu=lieu,
        jus=jus,
        monnaie_locale=monnaie_locale_du_lieu(lieu),
        point_de_vente=creer_un_point_de_vente([jus.produit]),
        carte_1=creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500),
        client_http=client_du_caissier(lieu),
        cle_d_idempotence=nouvelle_cle_d_idempotence(),
    )


def scanner_la_seconde_carte(preparation, tag_id):
    """Le client pose une seconde carte pour payer le reste.
    / The customer taps a second card to pay the rest."""
    return payer_le_reste_avec_une_deuxieme_carte(
        preparation.client_http,
        preparation.point_de_vente,
        {f"repid-{cle_de_panier(preparation.jus)}": "3"},
        preparation.carte_1,
        SimpleNamespace(tag_id=tag_id),
        preparation.cle_d_idempotence,
    )


# --- 37 : PaiementViewSet.retour_carte (« check carte ») ---


def preparer_le_check_carte(lieu):
    """Le caissier ouvre « check carte ». / The cashier opens the card check."""
    return SimpleNamespace(
        lieu=lieu,
        monnaie_locale=monnaie_locale_du_lieu(lieu),
        client_http=client_du_caissier(lieu),
    )


def scanner_pour_le_check_carte(preparation, tag_id):
    """Le client pose sa carte sur « check carte ». / The customer taps on card check."""
    return preparation.client_http.post(URL_DU_RETOUR_CARTE, {"tag_id": tag_id})


# --- 38 : PaiementViewSet.vider_carte_preview et vider_carte ---


def preparer_le_vidage_de_carte(lieu):
    """
    Un point de vente, la carte primaire du caissier, et le caissier connecté
    (test_caisse_vider_carte_deux_fedow.py), qui demande les écrans en français.
    / A point of sale, the cashier's primary card, and the logged-in cashier.
    """
    caisse = preparer_le_vidage_a_la_caisse(lieu)
    caisse.client_du_caissier.defaults["HTTP_ACCEPT_LANGUAGE"] = "fr"
    caisse.lieu = lieu
    return caisse


def donnees_du_vidage(caisse, tag_id):
    """Les champs postés par l'écran du vidage. / The emptying screen's fields."""
    return {
        "tag_id": tag_id,
        "tag_id_cm": caisse.carte_du_caissier.tag_id,
        "uuid_pv": str(caisse.point_de_vente.uuid),
    }


def client_fedow_du_vidage(tag_id):
    """
    Le client `FedowAPI` de la caisse, simulé pour le vidage : l'ancien Fedow porte
    4,00 € de monnaie locale du lieu sur cette carte, et son vidage les reprend
    (test_caisse_vider_carte_deux_fedow.py). Le service, lui, lit la carte par la
    simulation de `NFCcardFedow` du test.
    / The register's `FedowAPI` client faked for the emptying: 4.00 € on the old Fedow.
    """
    faux_fedow, _transactions, _relues = ancien_fedow_simule_avec_ses_soldes(
        SimpleNamespace(tag_id=tag_id, number=tag_id), [("TLF", 400)]
    )
    return faux_fedow


def scanner_pour_l_apercu_du_vidage(caisse, tag_id):
    """Le caissier scanne la carte du client : l'aperçu du vidage.
    / The cashier scans the card: the emptying preview."""
    with patch("laboutik.views.FedowAPI", return_value=client_fedow_du_vidage(tag_id)):
        return caisse.client_du_caissier.post(
            URL_DE_L_APERCU_DU_VIDAGE,
            donnees_du_vidage(caisse, tag_id),
            HTTP_HX_REQUEST="true",
        )


def scanner_pour_vider_la_carte(caisse, tag_id):
    """Le caissier confirme le vidage de la carte. / The cashier empties the card."""
    donnees = donnees_du_vidage(caisse, tag_id)
    donnees["vider_carte"] = "false"
    with patch("laboutik.views.FedowAPI", return_value=client_fedow_du_vidage(tag_id)):
        return caisse.client_du_caissier.post(URL_DU_VIDAGE_DE_CARTE, donnees)


# --- 39 : la borne (kiosk/carte.py, lire_la_carte_pour_la_borne) ---


def preparer_la_borne(lieu):
    """
    Une borne appairée (compte terminal au rôle Kiosque, créé dans le lieu), et son
    client HTTP, qui demande les écrans en français.
    / A paired kiosk (Kiosk-role terminal account) and its HTTP client.
    """
    email_de_la_borne = f"test-rapatriement-borne-{identifiant_unique()}@terminals.test"
    compte_de_la_borne = TermUser.objects.create(
        email=email_de_la_borne,
        username=email_de_la_borne,
        terminal_role=TibilletUser.ROLE_KIOSQUE,
        is_active=True,
    )
    client_http = APIClient()
    client_http.force_authenticate(user=compte_de_la_borne)
    client_http.defaults["SERVER_NAME"] = DOMAINE_DU_LIEU
    client_http.defaults["HTTP_ACCEPT_LANGUAGE"] = "fr"
    return SimpleNamespace(
        lieu=lieu,
        monnaie_locale=monnaie_locale_du_lieu(lieu),
        client_http=client_http,
    )


def scanner_sur_la_borne(borne, tag_id):
    """Le client pose sa carte sur la borne (écran 1). / The customer taps on the kiosk."""
    return borne.client_http.post(
        URL_DE_LA_LECTURE_DE_CARTE_PAR_LA_BORNE, data={"tag_id": tag_id}
    )


def demander_le_recapitulatif_a_la_borne(borne, tag_id):
    """
    Le client choisit 20 € : le récapitulatif relit la carte par le validateur de la
    recharge (`RefillWisePoseValidator.validate_tag_id`, kiosk/validators.py).
    / The customer picks 20 €: the summary re-reads the card through the validator.
    """
    return borne.client_http.post(
        URL_DU_RECAPITULATIF_DE_LA_BORNE,
        data={"tag_id": tag_id, "totalAmount": "20.00"},
    )


# --- 40 : la tireuse (controlvanne/viewsets.py, authorize) ---


def preparer_la_tireuse(lieu):
    """
    Une tireuse neuve à 8 €/L, réservoir illimité, la clé API de son terminal
    (test_tireuse_ancien_fedow.py), et une carte primaire dans le lieu. Les messages
    poussés à l'écran de la tireuse sont notés dans `messages_a_l_ecran`.
    / A fresh tap, its terminal API key and a venue primary card. Screen messages are
    recorded.
    """
    tireuse, entetes_http = _creer_une_tireuse(
        lieu.tenant, prix_du_litre_en_euros="8.00"
    )
    # Sans carte primaire dans le lieu, la tireuse refuse de servir.
    # / Without a primary card in the venue, the tap refuses to pour.
    donner_une_carte_primaire_au_lieu(lieu.tenant)
    return SimpleNamespace(
        lieu=lieu,
        tireuse=tireuse,
        entetes_http=entetes_http,
        monnaie_locale=monnaie_locale_du_lieu(lieu),
        messages_a_l_ecran=[],
    )


def scanner_sur_la_tireuse(preparation, tag_id):
    """
    Le badge posé sur la tireuse (`authorize`), comme le Raspberry Pi. Les messages
    WebSocket vers l'écran de la tireuse sont capturés, pas envoyés.
    / The badge on the tap; WebSocket screen messages are captured.
    """

    def capturer_le_message(uuid_de_la_tireuse, message, uuid_du_lieu):
        preparation.messages_a_l_ecran.append(message)

    from django.test import Client as ClientHttpDjango

    with patch(
        "controlvanne.viewsets.pousser_aux_kiosks", side_effect=capturer_le_message
    ):
        return _poster(
            ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU),
            preparation.entetes_http,
            "authorize",
            {"tireuse_uuid": str(preparation.tireuse.uuid), "uid": tag_id},
        )


# ==========================================================================
# 30 bis — CaisseViewSet._identifier_adherent : adhésion en espèces, sans recharge
# / Membership paid in cash, without top-up
# ==========================================================================


def test_30_bis_a_adhesion_en_especes_rapatrie_la_carte_et_la_lie_a_l_adherente(lieu):
    """
    Adhésion payée en espèces, sans recharge : la carte posée n'est connue que de
    l'ancien Fedow. Elle est rapatriée pendant l'identification de l'adhérente, et
    l'adhésion la rattache à l'adhérente (chez Fedow, puis en local). Sans rapatriement,
    la carte serait ignorée (repli sur l'e-mail seul).
    / Card known only by the old Fedow: fetched during identification, then linked.
    """
    adhesion_au_comptoir = preparer_une_adhesion_en_especes(lieu)
    carte_fedow = carte_connue_seulement_de_fedow()

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = scanner_une_adhesion_en_especes(
            adhesion_au_comptoir, carte_fedow.tag_id
        )

    assert reponse.status_code == 200, reponse.content.decode()[:600]
    assert 'data-testid="paiement-succes"' in reponse.content.decode()
    assert fedow.tags_demandes == [carte_fedow.tag_id]
    carte_locale = verifier_la_carte_rapatriee(lieu, carte_fedow)
    adhesion_vendue = adhesion_enregistree(adhesion_au_comptoir)
    assert adhesion_vendue is not None
    assert adhesion_au_comptoir.cartes_liees_chez_fedow == [carte_locale.number]
    carte_locale.refresh_from_db()
    assert carte_locale.user_id == adhesion_vendue.user_id


def test_30_bis_b_adhesion_carte_d_un_lieu_legacy_repli_sur_l_email(lieu, lieu_legacy):
    """
    La carte posée vient d'un lieu legacy : elle est refusée (rien n'est créé), et
    l'adhérente est identifiée par son e-mail, comme avant le chantier. L'adhésion est
    enregistrée, aucune carte n'est liée chez Fedow.
    / Legacy card refused: fallback on the email, membership recorded, no card linked.
    """
    adhesion_au_comptoir = preparer_une_adhesion_en_especes(lieu)
    carte_legacy = carte_d_un_lieu_legacy(lieu_legacy)

    with ancien_fedow_simule(fiches=[carte_legacy.fiche]) as fedow:
        reponse = scanner_une_adhesion_en_especes(
            adhesion_au_comptoir, carte_legacy.tag_id
        )

    assert reponse.status_code == 200, reponse.content.decode()[:600]
    assert 'data-testid="paiement-succes"' in reponse.content.decode()
    assert fedow.tags_demandes == [carte_legacy.tag_id]
    assert not la_carte_existe_en_local(carte_legacy.tag_id)
    assert adhesion_enregistree(adhesion_au_comptoir) is not None
    assert adhesion_au_comptoir.cartes_liees_chez_fedow == []


def test_30_bis_c_adhesion_ancien_fedow_en_panne_repli_sur_l_email(lieu):
    """
    L'ancien Fedow est en panne pendant l'identification : la carte est ignorée,
    l'adhérente est identifiée par son e-mail, l'adhésion est enregistrée.
    / Old Fedow down: the card is ignored, fallback on the email.
    """
    adhesion_au_comptoir = preparer_une_adhesion_en_especes(lieu)
    tag_id = tag_neuf()

    with ancien_fedow_simule(panne=panne_de_l_ancien_fedow()) as fedow:
        reponse = scanner_une_adhesion_en_especes(adhesion_au_comptoir, tag_id)

    assert reponse.status_code == 200, reponse.content.decode()[:600]
    assert 'data-testid="paiement-succes"' in reponse.content.decode()
    assert fedow.tags_demandes == [tag_id]
    assert not la_carte_existe_en_local(tag_id)
    assert adhesion_enregistree(adhesion_au_comptoir) is not None
    assert adhesion_au_comptoir.cartes_liees_chez_fedow == []


# ==========================================================================
# 31 — PaiementViewSet.identifier_client
# ==========================================================================


def test_31_a_identifier_client_carte_seulement_chez_fedow_identifiee_anonyme(lieu):
    """
    Le client pose une carte connue seulement de l'ancien Fedow sur l'écran « qui est
    le client ? » : elle est rapatriée, reconnue comme carte anonyme, et la caisse
    demande l'e-mail (formulaire pré-rempli avec le tag).
    / Card known only by the old Fedow: fetched, anonymous, the email form is shown.
    """
    identification = preparer_l_identification_du_client(lieu)
    carte_fedow = carte_connue_seulement_de_fedow()

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = scanner_pour_identifier_le_client(identification, carte_fedow.tag_id)

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="client-form"' in contenu, contenu[:600]
    assert f"setHiddenInput('tag_id', '{carte_fedow.tag_id}')" in contenu
    assert message_de_la_caisse(reponse) is None
    assert fedow.tags_demandes == [carte_fedow.tag_id]
    verifier_la_carte_rapatriee(lieu, carte_fedow)


def test_31_b_identifier_client_carte_d_un_lieu_legacy_refusee(lieu, lieu_legacy):
    """Carte d'un lieu legacy : l'écran dit pourquoi, rien n'est créé.
    / Legacy card: the screen says why, nothing created."""
    identification = preparer_l_identification_du_client(lieu)
    carte_legacy = carte_d_un_lieu_legacy(lieu_legacy)

    with ancien_fedow_simule(fiches=[carte_legacy.fiche]):
        reponse = scanner_pour_identifier_le_client(identification, carte_legacy.tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_LIEU_NON_MIGRE
    assert not la_carte_existe_en_local(carte_legacy.tag_id)


def test_31_c_identifier_client_ancien_fedow_en_panne_dit_fedow_injoignable(lieu):
    """Ancien Fedow en panne : « Fedow injoignable », pas « Carte inconnue ».
    / Old Fedow down: "Fedow unreachable", not "Unknown card"."""
    identification = preparer_l_identification_du_client(lieu)
    tag_id = tag_neuf()

    with ancien_fedow_simule(panne=panne_de_l_ancien_fedow()):
        reponse = scanner_pour_identifier_le_client(identification, tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_FEDOW_INJOIGNABLE
    assert not la_carte_existe_en_local(tag_id)


# ==========================================================================
# 32 — PaiementViewSet._payer_par_nfc
# ==========================================================================


def test_32_a_paiement_nfc_carte_seulement_chez_fedow_rapatriee_et_debitee(lieu):
    """
    Une bière à 5 € payée avec une carte connue seulement de l'ancien Fedow, dont le
    portefeuille porte 20 € de monnaie locale : la carte est rapatriée, le paiement
    aboutit, le portefeuille passe à 15 €, la ligne de vente est validée.
    / Card known only by the old Fedow: fetched, paid, balance 20 → 15 €.
    """
    paiement = preparer_un_paiement_nfc(lieu)
    carte_fedow = carte_connue_seulement_de_fedow(
        monnaie=monnaie_locale_du_lieu(lieu), solde_en_centimes=2000
    )

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = scanner_pour_payer_en_nfc(paiement, carte_fedow.tag_id)

    assert reponse.status_code == 200
    assert 'data-testid="paiement-succes"' in reponse.content.decode(), (
        message_de_la_caisse(reponse)
    )
    assert fedow.tags_demandes == [carte_fedow.tag_id]
    verifier_la_carte_rapatriee(lieu, carte_fedow)
    monnaie_locale = monnaie_locale_du_lieu(lieu)
    assert (
        solde_du_portefeuille(carte_fedow.portefeuille_miroir, monnaie_locale) == 1500
    )
    assert list(
        LigneArticle.objects.filter(pricesold__price=paiement.biere.tarif).values_list(
            "status", flat=True
        )
    ) == [LigneArticle.VALID]


def test_32_b_paiement_nfc_carte_d_un_lieu_legacy_refusee(lieu, lieu_legacy):
    """Carte d'un lieu legacy : refus affiché, rien n'est vendu ni créé.
    / Legacy card: refusal shown, nothing sold nor created."""
    paiement = preparer_un_paiement_nfc(lieu)
    carte_legacy = carte_d_un_lieu_legacy(lieu_legacy)

    with ancien_fedow_simule(fiches=[carte_legacy.fiche]):
        reponse = scanner_pour_payer_en_nfc(paiement, carte_legacy.tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_LIEU_NON_MIGRE
    assert not la_carte_existe_en_local(carte_legacy.tag_id)
    assert not LigneArticle.objects.filter(
        pricesold__price=paiement.biere.tarif
    ).exists()


def test_32_c_paiement_nfc_ancien_fedow_en_panne_dit_fedow_injoignable(lieu):
    """Ancien Fedow en panne : « Fedow injoignable », rien n'est vendu.
    / Old Fedow down: "Fedow unreachable", nothing sold."""
    paiement = preparer_un_paiement_nfc(lieu)
    tag_id = tag_neuf()

    with ancien_fedow_simule(panne=panne_de_l_ancien_fedow()):
        reponse = scanner_pour_payer_en_nfc(paiement, tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_FEDOW_INJOIGNABLE
    assert not la_carte_existe_en_local(tag_id)
    assert not LigneArticle.objects.filter(
        pricesold__price=paiement.biere.tarif
    ).exists()


# ==========================================================================
# 33 — PaiementViewSet._payer_en_especes (recharge)
# ==========================================================================


def test_33_a_recharge_en_especes_carte_seulement_chez_fedow_rapatriee_et_creditee(
    lieu,
):
    """
    Recharge de 10 € payée en espèces sur une carte connue seulement de l'ancien
    Fedow : la carte est rapatriée, son portefeuille (miroir Fedow) reçoit 10 €.
    / Cash top-up on a card known only by the old Fedow: fetched, credited 10 €.
    """
    recharge = preparer_une_recharge(lieu)
    carte_fedow = carte_connue_seulement_de_fedow()

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = scanner_pour_une_recharge_en_especes(recharge, carte_fedow.tag_id)

    assert reponse.status_code == 200
    assert 'data-testid="paiement-succes"' in reponse.content.decode(), (
        message_de_la_caisse(reponse)
    )
    assert fedow.tags_demandes == [carte_fedow.tag_id]
    carte_locale = verifier_la_carte_rapatriee(lieu, carte_fedow)
    assert carte_locale.wallet_ephemere_id == carte_fedow.portefeuille_miroir.uuid
    assert (
        solde_du_portefeuille(carte_fedow.portefeuille_miroir, recharge.monnaie_locale)
        == 1000
    )


def test_33_b_recharge_en_especes_carte_d_un_lieu_legacy_refusee(lieu, lieu_legacy):
    """Carte d'un lieu legacy : refus affiché, rien n'est rechargé ni créé.
    / Legacy card: refusal shown, no top-up."""
    recharge = preparer_une_recharge(lieu)
    carte_legacy = carte_d_un_lieu_legacy(lieu_legacy)

    with ancien_fedow_simule(fiches=[carte_legacy.fiche]):
        reponse = scanner_pour_une_recharge_en_especes(recharge, carte_legacy.tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_LIEU_NON_MIGRE
    assert not la_carte_existe_en_local(carte_legacy.tag_id)
    assert not LigneArticle.objects.filter(
        pricesold__price=recharge.recharge.tarif
    ).exists()


def test_33_c_recharge_en_especes_ancien_fedow_en_panne_dit_fedow_injoignable(lieu):
    """Ancien Fedow en panne : « Fedow injoignable », rien n'est rechargé.
    / Old Fedow down: "Fedow unreachable", no top-up."""
    recharge = preparer_une_recharge(lieu)
    tag_id = tag_neuf()

    with ancien_fedow_simule(panne=panne_de_l_ancien_fedow()):
        reponse = scanner_pour_une_recharge_en_especes(recharge, tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_FEDOW_INJOIGNABLE
    assert not la_carte_existe_en_local(tag_id)


# ==========================================================================
# 34 — PaiementViewSet._payer_par_carte_ou_cheque (recharge)
# ==========================================================================


def test_34_a_recharge_par_cheque_carte_seulement_chez_fedow_rapatriee_et_creditee(
    lieu,
):
    """
    Recharge de 10 € payée par chèque sur une carte connue seulement de l'ancien
    Fedow : la carte est rapatriée, son portefeuille reçoit 10 €.
    / Cheque top-up on a card known only by the old Fedow: fetched, credited 10 €.
    """
    recharge = preparer_une_recharge(lieu)
    carte_fedow = carte_connue_seulement_de_fedow()

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = scanner_pour_une_recharge_par_cheque(recharge, carte_fedow.tag_id)

    assert reponse.status_code == 200
    assert 'data-testid="paiement-succes"' in reponse.content.decode(), (
        message_de_la_caisse(reponse)
    )
    assert fedow.tags_demandes == [carte_fedow.tag_id]
    verifier_la_carte_rapatriee(lieu, carte_fedow)
    assert (
        solde_du_portefeuille(carte_fedow.portefeuille_miroir, recharge.monnaie_locale)
        == 1000
    )


def test_34_b_recharge_par_cheque_carte_d_un_lieu_legacy_refusee(lieu, lieu_legacy):
    """Carte d'un lieu legacy : refus affiché, rien n'est rechargé ni créé.
    / Legacy card: refusal shown, no top-up."""
    recharge = preparer_une_recharge(lieu)
    carte_legacy = carte_d_un_lieu_legacy(lieu_legacy)

    with ancien_fedow_simule(fiches=[carte_legacy.fiche]):
        reponse = scanner_pour_une_recharge_par_cheque(recharge, carte_legacy.tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_LIEU_NON_MIGRE
    assert not la_carte_existe_en_local(carte_legacy.tag_id)
    assert not LigneArticle.objects.filter(
        pricesold__price=recharge.recharge.tarif
    ).exists()


def test_34_c_recharge_par_cheque_ancien_fedow_en_panne_dit_fedow_injoignable(lieu):
    """Ancien Fedow en panne : « Fedow injoignable », rien n'est rechargé.
    / Old Fedow down: "Fedow unreachable", no top-up."""
    recharge = preparer_une_recharge(lieu)
    tag_id = tag_neuf()

    with ancien_fedow_simule(panne=panne_de_l_ancien_fedow()):
        reponse = scanner_pour_une_recharge_par_cheque(recharge, tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_FEDOW_INJOIGNABLE
    assert not la_carte_existe_en_local(tag_id)


# ==========================================================================
# 35 — PaiementViewSet._rembourser_consigne_par_nfc
# ==========================================================================


def test_35_a_retour_de_consigne_carte_seulement_chez_fedow_rapatriee_et_creditee(lieu):
    """
    Un gobelet rendu, remboursé sur une carte connue seulement de l'ancien Fedow : la
    carte est rapatriée, son portefeuille reçoit 1 € de monnaie locale.
    / Deposit refunded on a card known only by the old Fedow: fetched, credited 1 €.
    """
    consigne = preparer_un_retour_de_consigne(lieu)
    carte_fedow = carte_connue_seulement_de_fedow()

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = scanner_pour_rembourser_la_consigne(consigne, carte_fedow.tag_id)

    assert reponse.status_code == 200, message_de_la_caisse(reponse)
    assert 'data-testid="paiement-succes"' in reponse.content.decode()
    assert fedow.tags_demandes == [carte_fedow.tag_id]
    verifier_la_carte_rapatriee(lieu, carte_fedow)
    assert (
        solde_du_portefeuille(carte_fedow.portefeuille_miroir, consigne.monnaie_locale)
        == 100
    )


def test_35_b_retour_de_consigne_carte_d_un_lieu_legacy_refusee(lieu, lieu_legacy):
    """Carte d'un lieu legacy : refus affiché (400), rien n'est remboursé ni créé.
    / Legacy card: refusal shown (400), nothing refunded."""
    consigne = preparer_un_retour_de_consigne(lieu)
    carte_legacy = carte_d_un_lieu_legacy(lieu_legacy)

    with ancien_fedow_simule(fiches=[carte_legacy.fiche]):
        reponse = scanner_pour_rembourser_la_consigne(consigne, carte_legacy.tag_id)

    assert reponse.status_code == 400
    assert message_de_la_caisse(reponse) == MESSAGE_LIEU_NON_MIGRE
    assert not la_carte_existe_en_local(carte_legacy.tag_id)
    assert not LigneArticle.objects.filter(
        pricesold__price=consigne.retour_de_consigne.tarif
    ).exists()


def test_35_c_retour_de_consigne_ancien_fedow_en_panne_dit_fedow_injoignable(lieu):
    """Ancien Fedow en panne : « Fedow injoignable » (400), rien n'est remboursé.
    / Old Fedow down: "Fedow unreachable" (400), nothing refunded."""
    consigne = preparer_un_retour_de_consigne(lieu)
    tag_id = tag_neuf()

    with ancien_fedow_simule(panne=panne_de_l_ancien_fedow()):
        reponse = scanner_pour_rembourser_la_consigne(consigne, tag_id)

    assert reponse.status_code == 400
    assert message_de_la_caisse(reponse) == MESSAGE_FEDOW_INJOIGNABLE
    assert not la_carte_existe_en_local(tag_id)


# ==========================================================================
# 36 — PaiementViewSet._executer_paiement_complementaire (seconde carte)
# ==========================================================================


def test_36_a_seconde_carte_seulement_chez_fedow_rapatriee_et_paie_le_reste(lieu):
    """
    La carte 1 (locale) paie 5,00 € ; la seconde carte, connue seulement de l'ancien
    Fedow et chargée de 6,00 €, est rapatriée et paie le reste, 5,50 €. Une seule vente,
    réglée ; il reste 0,50 € sur la seconde carte.
    L'ancien Fedow est interrogé deux fois : le rapatriement de la seconde carte, puis
    la lecture du FED de la carte 1, qui ne couvre pas tout (inconnue là-bas : 0).
    / Second card known only by the old Fedow: fetched, pays the 5.50 € left. The old
    Fedow is asked twice: fetching card 2, then reading card 1's FED.
    """
    deux_cartes = preparer_un_paiement_a_deux_cartes(lieu)
    seconde_carte = carte_connue_seulement_de_fedow(
        monnaie=deux_cartes.monnaie_locale, solde_en_centimes=600
    )

    with ancien_fedow_simule(fiches=[seconde_carte.fiche]) as fedow:
        reponse = scanner_la_seconde_carte(deux_cartes, seconde_carte.tag_id)

    assert reponse.status_code == 200
    assert 'data-testid="paiement-succes"' in reponse.content.decode(), (
        message_de_la_caisse(reponse)
    )
    assert fedow.tags_demandes == [seconde_carte.tag_id, deux_cartes.carte_1.tag_id]
    verifier_la_carte_rapatriee(lieu, seconde_carte)
    vente = retrouver_la_vente_de_la_cle(deux_cartes.cle_d_idempotence)
    assert vente.statut == Vente.Statut.REGLEE
    assert (
        solde_du_portefeuille(
            seconde_carte.portefeuille_miroir, deux_cartes.monnaie_locale
        )
        == 50
    )


def test_36_b_seconde_carte_d_un_lieu_legacy_refusee(lieu, lieu_legacy):
    """Seconde carte d'un lieu legacy : refus affiché, aucune vente, rien n'est créé.
    / Legacy second card: refusal shown, no sale."""
    deux_cartes = preparer_un_paiement_a_deux_cartes(lieu)
    carte_legacy = carte_d_un_lieu_legacy(lieu_legacy)

    with ancien_fedow_simule(fiches=[carte_legacy.fiche]):
        reponse = scanner_la_seconde_carte(deux_cartes, carte_legacy.tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_LIEU_NON_MIGRE
    assert not la_carte_existe_en_local(carte_legacy.tag_id)
    assert not Vente.objects.filter(
        idempotency_key=deux_cartes.cle_d_idempotence
    ).exists()


def test_36_c_seconde_carte_ancien_fedow_en_panne_dit_fedow_injoignable(lieu):
    """Ancien Fedow en panne : « Fedow injoignable », aucune vente.
    / Old Fedow down: "Fedow unreachable", no sale."""
    deux_cartes = preparer_un_paiement_a_deux_cartes(lieu)
    tag_id = tag_neuf()

    with ancien_fedow_simule(panne=panne_de_l_ancien_fedow()):
        reponse = scanner_la_seconde_carte(deux_cartes, tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_FEDOW_INJOIGNABLE
    assert not la_carte_existe_en_local(tag_id)
    assert not Vente.objects.filter(
        idempotency_key=deux_cartes.cle_d_idempotence
    ).exists()


# ==========================================================================
# 37 — PaiementViewSet.retour_carte (« check carte »)
# ==========================================================================


def test_37_a_check_carte_seulement_chez_fedow_affiche_la_fiche_de_la_carte(lieu):
    """
    « Check carte » sur une carte connue seulement de l'ancien Fedow, qui porte 7 € de
    monnaie locale : elle est rapatriée, la fiche s'affiche (carte anonyme, solde),
    sans message d'erreur. L'ancien Fedow est interrogé deux fois pour cette carte :
    le rapatriement, puis la lecture de son FED pour l'affichage.
    / Card check on a card known only by the old Fedow: fetched, its record shown. The
    old Fedow is asked twice: fetching, then reading its FED.
    """
    check_carte = preparer_le_check_carte(lieu)
    carte_fedow = carte_connue_seulement_de_fedow(
        monnaie=check_carte.monnaie_locale, solde_en_centimes=700
    )

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = scanner_pour_le_check_carte(check_carte, carte_fedow.tag_id)

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="retour-carte-erreur"' not in contenu
    assert 'data-testid="retour-carte-anonyme"' in contenu
    assert texte_de_l_element(reponse, "retour-carte-soldes").startswith("7")
    assert fedow.tags_demandes == [carte_fedow.tag_id, carte_fedow.tag_id]
    verifier_la_carte_rapatriee(lieu, carte_fedow)


def test_37_b_check_carte_d_un_lieu_legacy_affiche_le_refus(lieu, lieu_legacy):
    """Carte d'un lieu legacy : la fiche affiche le refus, rien n'est créé.
    / Legacy card: the popup shows the refusal."""
    check_carte = preparer_le_check_carte(lieu)
    carte_legacy = carte_d_un_lieu_legacy(lieu_legacy)

    with ancien_fedow_simule(fiches=[carte_legacy.fiche]):
        reponse = scanner_pour_le_check_carte(check_carte, carte_legacy.tag_id)

    assert reponse.status_code == 200
    assert message_de_la_fiche_de_carte(reponse) == MESSAGE_LIEU_NON_MIGRE
    assert not la_carte_existe_en_local(carte_legacy.tag_id)


def test_37_c_check_carte_ancien_fedow_en_panne_dit_fedow_injoignable(lieu):
    """Ancien Fedow en panne : la fiche dit « Fedow injoignable ».
    / Old Fedow down: the popup says "Fedow unreachable"."""
    check_carte = preparer_le_check_carte(lieu)
    tag_id = tag_neuf()

    with ancien_fedow_simule(panne=panne_de_l_ancien_fedow()):
        reponse = scanner_pour_le_check_carte(check_carte, tag_id)

    assert reponse.status_code == 200
    assert message_de_la_fiche_de_carte(reponse) == MESSAGE_FEDOW_INJOIGNABLE
    assert not la_carte_existe_en_local(tag_id)


# ==========================================================================
# 38 — PaiementViewSet.vider_carte_preview et vider_carte
# ==========================================================================


def test_38_a_apercu_du_vidage_carte_seulement_chez_fedow_rapatriee(lieu):
    """
    Aperçu du vidage d'une carte connue seulement de l'ancien Fedow, qui y porte 4 € :
    la carte est rapatriée, l'écran de confirmation s'affiche, rien n'est débité.
    / Emptying preview of a card known only by the old Fedow: fetched, confirm screen.
    """
    caisse = preparer_le_vidage_de_carte(lieu)
    carte_fedow = carte_connue_seulement_de_fedow()

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = scanner_pour_l_apercu_du_vidage(caisse, carte_fedow.tag_id)

    assert reponse.status_code == 200
    assert 'data-testid="vider-carte-confirm"' in reponse.content.decode(), (
        message_de_la_caisse(reponse)
    )
    assert fedow.tags_demandes == [carte_fedow.tag_id]
    verifier_la_carte_rapatriee(lieu, carte_fedow)


def test_38_a_vidage_carte_seulement_chez_fedow_rapatriee_et_videe(lieu):
    """
    Vidage d'une carte connue seulement de l'ancien Fedow, qui y porte 4 € : la carte
    est rapatriée, vidée sur l'ancien Fedow, et la vente du vidage est écrite.
    / Emptying a card known only by the old Fedow: fetched, emptied, sale written.
    """
    caisse = preparer_le_vidage_de_carte(lieu)
    carte_fedow = carte_connue_seulement_de_fedow()

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = scanner_pour_vider_la_carte(caisse, carte_fedow.tag_id)

    assert reponse.status_code == 200
    assert 'data-testid="vider-carte-success"' in reponse.content.decode(), (
        message_de_la_caisse(reponse)
    )
    assert fedow.tags_demandes == [carte_fedow.tag_id]
    carte_locale = verifier_la_carte_rapatriee(lieu, carte_fedow)
    vente_du_vidage = retrouver_la_vente_de_vidage(carte_locale)
    assert vente_du_vidage.statut == Vente.Statut.REGLEE


def test_38_b_apercu_du_vidage_carte_d_un_lieu_legacy_refusee(lieu, lieu_legacy):
    """Aperçu du vidage, carte d'un lieu legacy : refus affiché, rien n'est créé.
    / Preview, legacy card: refusal shown."""
    caisse = preparer_le_vidage_de_carte(lieu)
    carte_legacy = carte_d_un_lieu_legacy(lieu_legacy)

    with ancien_fedow_simule(fiches=[carte_legacy.fiche]):
        reponse = scanner_pour_l_apercu_du_vidage(caisse, carte_legacy.tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_LIEU_NON_MIGRE
    assert not la_carte_existe_en_local(carte_legacy.tag_id)


def test_38_b_vidage_carte_d_un_lieu_legacy_refusee(lieu, lieu_legacy):
    """Vidage, carte d'un lieu legacy : refus affiché, rien n'est vidé ni créé.
    / Emptying, legacy card: refusal shown, nothing emptied."""
    caisse = preparer_le_vidage_de_carte(lieu)
    carte_legacy = carte_d_un_lieu_legacy(lieu_legacy)

    with ancien_fedow_simule(fiches=[carte_legacy.fiche]):
        reponse = scanner_pour_vider_la_carte(caisse, carte_legacy.tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_LIEU_NON_MIGRE
    assert 'data-testid="vider-carte-success"' not in reponse.content.decode()
    assert not la_carte_existe_en_local(carte_legacy.tag_id)


def test_38_c_apercu_du_vidage_ancien_fedow_en_panne_dit_fedow_injoignable(lieu):
    """Aperçu du vidage, ancien Fedow en panne : « Fedow injoignable ».
    / Preview, old Fedow down: "Fedow unreachable"."""
    caisse = preparer_le_vidage_de_carte(lieu)
    tag_id = tag_neuf()

    with ancien_fedow_simule(panne=panne_de_l_ancien_fedow()):
        reponse = scanner_pour_l_apercu_du_vidage(caisse, tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_FEDOW_INJOIGNABLE
    assert not la_carte_existe_en_local(tag_id)


def test_38_c_vidage_ancien_fedow_en_panne_dit_fedow_injoignable(lieu):
    """Vidage, ancien Fedow en panne : « Fedow injoignable », rien n'est vidé.
    / Emptying, old Fedow down: "Fedow unreachable", nothing emptied."""
    caisse = preparer_le_vidage_de_carte(lieu)
    tag_id = tag_neuf()

    with ancien_fedow_simule(panne=panne_de_l_ancien_fedow()):
        reponse = scanner_pour_vider_la_carte(caisse, tag_id)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_FEDOW_INJOIGNABLE
    assert 'data-testid="vider-carte-success"' not in reponse.content.decode()
    assert not la_carte_existe_en_local(tag_id)


# ==========================================================================
# 39 — La borne : check_request_card (kiosk/views.py) et le validateur de la
#      recharge (kiosk/validators.py), via lire_la_carte_pour_la_borne
# ==========================================================================


def test_39_a_borne_carte_seulement_chez_fedow_rapatriee_et_solde_affiche(lieu):
    """
    La borne lit une carte connue seulement de l'ancien Fedow, qui porte 15 € de
    monnaie locale : la carte est rapatriée, le solde s'affiche. L'ancien Fedow est
    lu deux fois (la borne, puis le service) : c'est accepté (§ 4.3).
    / Kiosk reads a card known only by the old Fedow: fetched, balance shown.
    """
    borne = preparer_la_borne(lieu)
    carte_fedow = carte_connue_seulement_de_fedow(
        monnaie=borne.monnaie_locale, solde_en_centimes=1500
    )

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = scanner_sur_la_borne(borne, carte_fedow.tag_id)

    assert reponse.status_code == 200
    assert 'data-testid="kiosk-etape-solde"' in reponse.content.decode(), (
        message_de_la_borne(reponse)
    )
    # Le solde vient du portefeuille miroir (base locale) : 15,00 €.
    # / The balance comes from the mirror wallet (local database).
    assert texte_de_l_element(reponse, "kiosk-solde").startswith("15,00")
    assert fedow.tags_demandes == [carte_fedow.tag_id, carte_fedow.tag_id]
    verifier_la_carte_rapatriee(lieu, carte_fedow)


def test_39_a_validateur_de_la_recharge_carte_seulement_chez_fedow_rapatriee(lieu):
    """
    Le récapitulatif de la borne passe par le validateur de la recharge : une carte
    connue seulement de l'ancien Fedow est rapatriée, le récapitulatif s'affiche.
    / The kiosk summary goes through the refill validator: fetched, summary shown.
    """
    borne = preparer_la_borne(lieu)
    carte_fedow = carte_connue_seulement_de_fedow()

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = demander_le_recapitulatif_a_la_borne(borne, carte_fedow.tag_id)

    assert reponse.status_code == 200
    assert 'data-testid="kiosk-etape-recapitulatif"' in reponse.content.decode(), (
        message_de_la_borne(reponse)
    )
    assert carte_fedow.tag_id in fedow.tags_demandes
    verifier_la_carte_rapatriee(lieu, carte_fedow)


def test_39_b_borne_carte_d_un_lieu_legacy_affiche_le_refus(lieu, lieu_legacy):
    """
    Carte d'un lieu legacy sur la borne : retour à « posez votre carte », avec le
    message du refus (pas le message générique « La carte n'a pas pu être lue »).
    / Legacy card on the kiosk: back to step 1 with the refusal message.
    """
    borne = preparer_la_borne(lieu)
    carte_legacy = carte_d_un_lieu_legacy(lieu_legacy)

    with ancien_fedow_simule(fiches=[carte_legacy.fiche]):
        reponse = scanner_sur_la_borne(borne, carte_legacy.tag_id)

    assert reponse.status_code == 200
    assert 'data-testid="kiosk-etape-poser-carte"' in reponse.content.decode()
    assert message_de_la_borne(reponse) == MESSAGE_LIEU_NON_MIGRE
    assert not la_carte_existe_en_local(carte_legacy.tag_id)


def test_39_b_validateur_de_la_recharge_carte_d_un_lieu_legacy_affiche_le_refus(
    lieu, lieu_legacy
):
    """
    Carte d'un lieu legacy au récapitulatif : le validateur de la recharge rend le
    message du refus (pas le message générique).
    / Legacy card at the summary: the validator returns the refusal message.
    """
    borne = preparer_la_borne(lieu)
    carte_legacy = carte_d_un_lieu_legacy(lieu_legacy)

    with ancien_fedow_simule(fiches=[carte_legacy.fiche]):
        reponse = demander_le_recapitulatif_a_la_borne(borne, carte_legacy.tag_id)

    assert reponse.status_code == 200
    assert 'data-testid="kiosk-etape-erreur"' in reponse.content.decode()
    assert message_de_la_borne(reponse) == MESSAGE_LIEU_NON_MIGRE
    assert not la_carte_existe_en_local(carte_legacy.tag_id)


def test_39_c_borne_ancien_fedow_en_panne_dit_carte_illisible(lieu):
    """
    Ancien Fedow en panne : la borne dit « La carte n'a pas pu être lue. Merci de
    réessayer. » (sa première lecture, celle du solde, échoue déjà).
    / Old Fedow down: the kiosk says the card could not be read.
    """
    borne = preparer_la_borne(lieu)
    tag_id = tag_neuf()

    with ancien_fedow_simule(panne=panne_de_l_ancien_fedow()):
        reponse = scanner_sur_la_borne(borne, tag_id)

    assert reponse.status_code == 200
    assert 'data-testid="kiosk-etape-poser-carte"' in reponse.content.decode()
    assert message_de_la_borne(reponse) == MESSAGE_BORNE_CARTE_ILLISIBLE
    assert not la_carte_existe_en_local(tag_id)


def test_39_c_validateur_de_la_recharge_ancien_fedow_en_panne_dit_carte_illisible(lieu):
    """Ancien Fedow en panne au récapitulatif : « La carte n'a pas pu être lue ».
    / Old Fedow down at the summary: the card could not be read."""
    borne = preparer_la_borne(lieu)
    tag_id = tag_neuf()

    with ancien_fedow_simule(panne=panne_de_l_ancien_fedow()):
        reponse = demander_le_recapitulatif_a_la_borne(borne, tag_id)

    assert reponse.status_code == 200
    assert 'data-testid="kiosk-etape-erreur"' in reponse.content.decode()
    assert message_de_la_borne(reponse) == MESSAGE_BORNE_CARTE_ILLISIBLE
    assert not la_carte_existe_en_local(tag_id)


# ==========================================================================
# 40 — La tireuse : authorize (controlvanne/viewsets.py)
# ==========================================================================


def test_40_a_tireuse_carte_seulement_chez_fedow_rapatriee_et_service_autorise(lieu):
    """
    Badge d'une carte connue seulement de l'ancien Fedow, qui porte 10 € de monnaie
    locale, sur une tireuse à 8 €/L : la carte est rapatriée, le service est autorisé
    (1 250 ml), une session est ouverte pour cette carte. L'ancien Fedow est interrogé
    deux fois pour cette carte : le rapatriement, puis la lecture de son FED pour le
    solde de la tireuse.
    / Badge of a card known only by the old Fedow: fetched, pouring authorized. The old
    Fedow is asked twice: fetching, then reading its FED.
    """
    from controlvanne.models import RfidSession

    tireuse = preparer_la_tireuse(lieu)
    carte_fedow = carte_connue_seulement_de_fedow(
        monnaie=tireuse.monnaie_locale, solde_en_centimes=1000
    )

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = scanner_sur_la_tireuse(tireuse, carte_fedow.tag_id)

    reponse_lue = reponse.json()
    assert reponse.status_code == 200
    assert reponse_lue["authorized"] is True, reponse_lue
    assert reponse_lue["solde_centimes"] == 1000
    assert reponse_lue["allowed_ml"] == 1250.0
    assert fedow.tags_demandes == [carte_fedow.tag_id, carte_fedow.tag_id]
    carte_locale = verifier_la_carte_rapatriee(lieu, carte_fedow)
    assert RfidSession.objects.filter(
        carte=carte_locale, tireuse_bec=tireuse.tireuse, authorized=True
    ).exists()


def test_40_a_tireuse_envoie_toujours_le_prenom_du_titulaire(lieu):
    """
    Une carte déjà locale, liée à une utilisatrice (« Camille ») : le service la rend
    sans appel réseau, et la tireuse envoie toujours son prénom à l'écran (la carte est
    relue avec `select_related("user")`).
    / A local card linked to a user: the tap still sends the holder's first name.
    """
    tireuse = preparer_la_tireuse(lieu)
    carte_de_camille, _portefeuille = creer_une_carte_de_tireuse(
        lieu.tenant, [(tireuse.monnaie_locale, 1000)], avec_un_utilisateur=True
    )

    with ancien_fedow_simule() as fedow:
        with patch("laboutik.views.lire_depensable_fed_frais", return_value=(0, False)):
            reponse = scanner_sur_la_tireuse(tireuse, carte_de_camille.tag_id)

    assert reponse.json()["authorized"] is True, reponse.json()
    assert fedow.tags_demandes == []
    messages_autorises = [
        message
        for message in tireuse.messages_a_l_ecran
        if message.get("authorized") is True
    ]
    assert messages_autorises, tireuse.messages_a_l_ecran
    assert messages_autorises[-1]["prenom"] == "Camille"


def test_40_b_tireuse_carte_d_un_lieu_legacy_refusee_et_affichee(lieu, lieu_legacy):
    """
    Badge d'une carte d'un lieu legacy : service refusé, et le refus est poussé à
    l'écran de la tireuse avec son message. Rien n'est créé.
    / Legacy card on the tap: refused, the refusal is pushed to the tap screen.
    """
    tireuse = preparer_la_tireuse(lieu)
    carte_legacy = carte_d_un_lieu_legacy(lieu_legacy)

    with ancien_fedow_simule(fiches=[carte_legacy.fiche]):
        reponse = scanner_sur_la_tireuse(tireuse, carte_legacy.tag_id)

    assert reponse.json() == {"authorized": False, "message": "Card refused."}
    assert tireuse.messages_a_l_ecran[-1]["authorized"] is False
    assert tireuse.messages_a_l_ecran[-1]["message"] == MESSAGE_LIEU_NON_MIGRE
    assert not la_carte_existe_en_local(carte_legacy.tag_id)


def test_40_c_tireuse_ancien_fedow_en_panne_refus_fedow_injoignable(lieu):
    """Ancien Fedow en panne : service refusé, l'écran dit « Fedow injoignable ».
    / Old Fedow down: refused, the screen says "Fedow unreachable"."""
    tireuse = preparer_la_tireuse(lieu)
    tag_id = tag_neuf()

    with ancien_fedow_simule(panne=panne_de_l_ancien_fedow()):
        reponse = scanner_sur_la_tireuse(tireuse, tag_id)

    assert reponse.json() == {"authorized": False, "message": "Card refused."}
    assert tireuse.messages_a_l_ecran[-1]["message"] == MESSAGE_FEDOW_INJOIGNABLE
    assert not la_carte_existe_en_local(tag_id)


# ==========================================================================
# 41 — Les sites NON branchés n'interrogent jamais l'ancien Fedow
# / Non-wired sites never ask the old Fedow
# ==========================================================================


def generer_un_qrcode_de_paiement(client_de_l_encaisseur):
    """
    L'encaisseur génère un QR code de 12,50 €. Rend la demande (ligne « en attente »).
    / The collector generates a 12.50 € QR code; returns the pending request.
    """
    reponse = client_de_l_encaisseur.post(
        URL_DE_LA_GENERATION_DU_QRCODE, data={"amount": "12.5", "asset_type": "EUR"}
    )
    assert reponse.status_code == 200, reponse.content.decode()[:400]
    uuid_de_la_demande = reponse.context["ligne_article_uuid_hex"]
    return LigneArticle.objects.get(uuid=uuid.UUID(uuid_de_la_demande))


def test_41_paiement_qrcode_par_carte_n_interroge_jamais_la_fiche_fedow(lieu):
    """
    `QrCodeScanPay.process_with_nfc` n'est PAS branché (§ 4.3) : le débit se fait chez
    Fedow par le tag, la carte locale ne sert qu'à remplir la vente, et `None` y est
    accepté. Un tag inconnu en local paie le QR code (202), la vente n'a pas de carte,
    aucune carte n'est rapatriée, et `NFCcardFedow.retrieve` n'est jamais appelé.
    / The QR card payment is not wired: no retrieve, no fetched card, sale without card.
    """
    encaisseur = creer_utilisateur(prenom="Encaisseur", nom="QR")
    encaisseur.initiate_payment.add(lieu.tenant)
    client_de_l_encaisseur = client_du_caissier(lieu)
    client_de_l_encaisseur.force_login(encaisseur)
    demande = generer_un_qrcode_de_paiement(client_de_l_encaisseur)

    payeur = creer_utilisateur(prenom="Payeur", nom="QR")
    payeur.wallet = Wallet.objects.create(name=f"TEST_rapatriement {payeur.email}")
    payeur.save()
    uuid_de_la_monnaie = uuid.uuid4()
    faux_fedow_du_qrcode = MagicMock()
    faux_fedow_du_qrcode.NFCcard.card_tag_id_retrieve.return_value = {
        "wallet_uuid": str(payeur.wallet.uuid),
        "is_wallet_ephemere": False,
    }
    faux_fedow_du_qrcode.wallet.get_total_fiducial_and_all_federated_token.return_value = 99999
    faux_fedow_du_qrcode.transaction.to_place_from_qrcode.return_value = [
        _transaction_de_l_ancien_fedow(uuid_de_la_monnaie, demande.amount)
    ]
    faux_fedow_du_qrcode.asset.retrieve.side_effect = _fiches_des_monnaies(
        {uuid_de_la_monnaie: "TLF"}
    )
    tag_inconnu_en_local = tag_neuf()

    with ancien_fedow_simule() as fedow:
        with patch("BaseBillet.validators.FedowAPI", return_value=faux_fedow_du_qrcode):
            reponse = client_de_l_encaisseur.post(
                URL_DE_LA_LECTURE_DE_CARTE_DU_QRCODE,
                data={
                    "tagSerial": tag_inconnu_en_local,
                    "ligne_article_uuid_hex": demande.uuid.hex,
                },
            )

    assert reponse.status_code == 202, reponse.content.decode()[:400]
    assert fedow.tags_demandes == []
    assert not la_carte_existe_en_local(tag_inconnu_en_local)
    vente = Vente.objects.get(articles__uuid=demande.uuid)
    assert vente.carte_id is None


def test_41_zone_recharger_d_un_tag_inconnu_n_interroge_jamais_fedow(lieu):
    """
    `recharge_carte` n'est PAS branché (relecture après « check carte ») : un tag
    inconnu en local répond 404, sans lire l'ancien Fedow ni créer de carte.
    / `recharge_carte` is not wired: unknown tag gives 404, no retrieve.
    """
    client_http = client_du_caissier(lieu)
    tag_inconnu_en_local = tag_neuf()

    with ancien_fedow_simule() as fedow:
        reponse = client_http.get(
            URL_DE_LA_ZONE_RECHARGER, {"tag_id": tag_inconnu_en_local}
        )

    assert reponse.status_code == 404
    assert fedow.tags_demandes == []
    assert not la_carte_existe_en_local(tag_inconnu_en_local)


def test_41_carte_primaire_inconnue_au_vidage_n_interroge_jamais_fedow(lieu):
    """
    `_charger_carte_primaire` n'est PAS branché : il tourne DANS des blocs atomic.
    Au vidage, une carte primaire inconnue en local donne « Carte inconnue », sans lire
    l'ancien Fedow ni créer de carte (la carte du client, elle, est locale).
    / `_charger_carte_primaire` is not wired: unknown primary card, no retrieve.
    """
    caisse = preparer_le_vidage_de_carte(lieu)
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500)
    tag_de_la_carte_primaire_inconnue = tag_neuf()
    donnees = {
        "tag_id": carte_du_client.tag_id,
        "tag_id_cm": tag_de_la_carte_primaire_inconnue,
        "uuid_pv": str(caisse.point_de_vente.uuid),
        "vider_carte": "false",
    }

    with ancien_fedow_simule() as fedow:
        reponse = caisse.client_du_caissier.post(URL_DU_VIDAGE_DE_CARTE, donnees)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_CARTE_INCONNUE
    assert fedow.tags_demandes == []
    assert not la_carte_existe_en_local(tag_de_la_carte_primaire_inconnue)


# ==========================================================================
# 42 — Aucun site branché n'appelle le service dans un bloc atomic de la vue
# / No wired site calls the service inside a view atomic block
# ==========================================================================


def ouvrir_la_caisse_en_francais(lieu):
    """
    L'écran d'ouverture de la caisse (test_caisse_ouverture_ancien_fedow.py) : une
    carte primaire locale sur un point de vente, et le caissier.
    / The register opening screen: a local primary card and the cashier.
    """
    return preparer_l_ouverture_de_la_caisse(lieu)


# Un parcours par site branché : (nom du site, préparation, scan, module où le
# service est importé, monnaie à poser sur le portefeuille miroir ?).
# La tireuse importe le service au moment de l'appel, depuis son module d'origine.
# / One flow per wired site: where the service is imported, and whether the mirror
# wallet needs a balance.
PARCOURS_DES_SITES_BRANCHES = [
    (
        "carte_primaire",
        ouvrir_la_caisse_en_francais,
        ouvrir_la_caisse,
        "laboutik.views",
        False,
    ),
    (
        "_identifier_adherent",
        preparer_une_adhesion_en_especes,
        scanner_une_adhesion_en_especes,
        "laboutik.views",
        False,
    ),
    (
        "identifier_client",
        preparer_l_identification_du_client,
        scanner_pour_identifier_le_client,
        "laboutik.views",
        False,
    ),
    (
        "_payer_par_nfc",
        preparer_un_paiement_nfc,
        scanner_pour_payer_en_nfc,
        "laboutik.views",
        True,
    ),
    (
        "_payer_en_especes",
        preparer_une_recharge,
        scanner_pour_une_recharge_en_especes,
        "laboutik.views",
        False,
    ),
    (
        "_payer_par_carte_ou_cheque",
        preparer_une_recharge,
        scanner_pour_une_recharge_par_cheque,
        "laboutik.views",
        False,
    ),
    (
        "_rembourser_consigne_par_nfc",
        preparer_un_retour_de_consigne,
        scanner_pour_rembourser_la_consigne,
        "laboutik.views",
        False,
    ),
    (
        "_executer_paiement_complementaire",
        preparer_un_paiement_a_deux_cartes,
        scanner_la_seconde_carte,
        "laboutik.views",
        True,
    ),
    (
        "retour_carte",
        preparer_le_check_carte,
        scanner_pour_le_check_carte,
        "laboutik.views",
        False,
    ),
    (
        "vider_carte_preview",
        preparer_le_vidage_de_carte,
        scanner_pour_l_apercu_du_vidage,
        "laboutik.views",
        False,
    ),
    (
        "vider_carte",
        preparer_le_vidage_de_carte,
        scanner_pour_vider_la_carte,
        "laboutik.views",
        False,
    ),
    (
        "borne_check_request_card",
        preparer_la_borne,
        scanner_sur_la_borne,
        "kiosk.carte",
        False,
    ),
    (
        "borne_validateur_de_la_recharge",
        preparer_la_borne,
        demander_le_recapitulatif_a_la_borne,
        "kiosk.carte",
        False,
    ),
    (
        "tireuse_authorize",
        preparer_la_tireuse,
        scanner_sur_la_tireuse,
        "QrcodeCashless.services",
        True,
    ),
]


@pytest.mark.parametrize(
    "nom_du_site,preparer,scanner,module_du_service,avec_un_solde",
    PARCOURS_DES_SITES_BRANCHES,
    ids=[parcours[0] for parcours in PARCOURS_DES_SITES_BRANCHES],
)
def test_42_le_service_est_appele_hors_de_tout_bloc_atomic_de_la_vue(
    lieu, nom_du_site, preparer, scanner, module_du_service, avec_un_solde
):
    """
    Le service fait un appel réseau (jusqu'à 30 s si Fedow est en panne) : appelé dans
    un bloc atomic, il tiendrait un verrou de base pendant tout ce temps. Un espion
    remplace le service là où le site l'importe, note la profondeur des savepoints à
    chaque appel, puis appelle le vrai service. Le test tourne déjà dans un atomic
    (`django_db`) : la profondeur de chaque appel doit être celle du début du test.
    / The service makes a network call: it must never run inside a view atomic block.
    """
    preparation = preparer(lieu)
    monnaie = monnaie_locale_du_lieu(lieu) if avec_un_solde else None
    carte_fedow = carte_connue_seulement_de_fedow(
        monnaie=monnaie, solde_en_centimes=2000 if avec_un_solde else 0
    )
    profondeur_au_debut_du_test = len(connection.savepoint_ids)
    profondeurs_pendant_les_appels = []

    def espion_du_service(tag_id):
        profondeurs_pendant_les_appels.append(len(connection.savepoint_ids))
        return trouver_ou_rapatrier_la_carte(tag_id)

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]):
        with patch(
            f"{module_du_service}.trouver_ou_rapatrier_la_carte",
            side_effect=espion_du_service,
        ):
            reponse = scanner(preparation, carte_fedow.tag_id)

    assert reponse.status_code < 500
    assert profondeurs_pendant_les_appels, (
        f"{nom_du_site} : le service n'a jamais été appelé."
    )
    assert all(
        profondeur == profondeur_au_debut_du_test
        for profondeur in profondeurs_pendant_les_appels
    ), (
        f"{nom_du_site} : service appelé dans un bloc atomic "
        f"(profondeurs {profondeurs_pendant_les_appels}, "
        f"attendu {profondeur_au_debut_du_test})."
    )
    assert la_carte_existe_en_local(carte_fedow.tag_id)


# ==========================================================================
# 43 — Tag hexadécimal inconnu partout : « Carte inconnue », plus de 500
# / Hex tag unknown everywhere: "Unknown card", no more 500
# ==========================================================================


def test_43_recharge_en_especes_tag_inconnu_partout_dit_carte_inconnue(lieu):
    """
    `_payer_en_especes` n'avait pas d'`except` (500 sur un tag inconnu). Un tag
    hexadécimal inconnu en local ET chez l'ancien Fedow donne « Carte inconnue ».
    / Cash top-up, tag unknown everywhere: "Unknown card", no 500.
    """
    recharge = preparer_une_recharge(lieu)
    tag_inconnu_partout = tag_neuf()

    with ancien_fedow_simule() as fedow:
        reponse = scanner_pour_une_recharge_en_especes(recharge, tag_inconnu_partout)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_CARTE_INCONNUE
    assert fedow.tags_demandes == [tag_inconnu_partout]
    assert not la_carte_existe_en_local(tag_inconnu_partout)


def test_43_recharge_par_cheque_tag_inconnu_partout_dit_carte_inconnue(lieu):
    """
    `_payer_par_carte_ou_cheque` n'avait pas d'`except` (500 sur un tag inconnu). Un
    tag hexadécimal inconnu en local ET chez l'ancien Fedow donne « Carte inconnue ».
    / Cheque top-up, tag unknown everywhere: "Unknown card", no 500.
    """
    recharge = preparer_une_recharge(lieu)
    tag_inconnu_partout = tag_neuf()

    with ancien_fedow_simule() as fedow:
        reponse = scanner_pour_une_recharge_par_cheque(recharge, tag_inconnu_partout)

    assert reponse.status_code == 200
    assert message_de_la_caisse(reponse) == MESSAGE_CARTE_INCONNUE
    assert fedow.tags_demandes == [tag_inconnu_partout]
    assert not la_carte_existe_en_local(tag_inconnu_partout)


# ==========================================================================
# 44 — Démo D5 : la carte « inconnue » des simulateurs n'est plus créée chez Fedow
# / Demo D5: the simulators' "unknown" card is no longer created on Fedow
# ==========================================================================


def test_44_demo_ne_cree_plus_la_carte_inconnue_des_simulateurs_chez_fedow(tenant):
    """
    `demo_data_v2` crée les cartes des simulateurs chez l'ancien Fedow
    (`_seed_cartes_nfc_fedow`). `DEMO_TAGID_CLIENT4` est le bouton « Carte inconnue »
    des simulateurs (caisse, borne, tireuse) : créée chez Fedow, elle serait rapatriée
    au premier scan et cesserait d'être inconnue. Elle n'est donc plus envoyée ; les
    quatre autres le sont toujours.
    / The demo no longer sends DEMO_TAGID_CLIENT4 to Fedow; the four others still go.
    """
    from Administration.management.commands.demo_data_v2 import Command

    listes_envoyees_a_fedow = []

    def faux_create(self, cartes, generation=1):
        listes_envoyees_a_fedow.append(cartes)
        return True

    with patch.object(FedowConfig, "can_fedow", return_value=True):
        with patch.object(NFCcardFedow, "create", new=faux_create):
            Command()._seed_cartes_nfc_fedow({})

    assert len(listes_envoyees_a_fedow) == 1
    tags_envoyes = [carte["first_tag_id"] for carte in listes_envoyees_a_fedow[0]]
    assert settings.DEMO_TAGID_CLIENT4 not in tags_envoyes
    assert sorted(tags_envoyes) == sorted(
        [
            settings.DEMO_TAGID_CM,
            settings.DEMO_TAGID_CLIENT1,
            settings.DEMO_TAGID_CLIENT2,
            settings.DEMO_TAGID_CLIENT3,
        ]
    )
