"""
tests/pytest/test_carte_liee_chez_fedow_fed_en_caisse.py

Le FED de l'ancien Fedow doit se voir et se dépenser à la caisse V2, que la carte
soit liée à une personne ou anonyme.
/ The old Fedow's FED must be visible and spendable at the V2 register, whether the
card is linked to a person or anonymous.

LOCALISATION : tests/pytest/test_carte_liee_chez_fedow_fed_en_caisse.py

CE QUI EST TESTÉ / WHAT IS TESTED
---------------------------------
Un lieu V2 dont les cartes n'existent que chez l'ancien Fedow. Sa carte devient
locale de deux façons :
- au premier scan NFC (caisse, borne, tireuse), par le rapatriement
  (`QrcodeCashless/services.py`, `trouver_ou_rapatrier_la_carte`) ;
- quand la personne lie sa carte par QR code (`BaseBillet/views.py`,
  `ScanQrCode.link`).
Dans les deux cas, la carte locale doit porter sa propriétaire si l'ancien Fedow la
dit liée. Sinon, la caisse la prend pour une carte anonyme.

La caisse lit et débite le FED PAR LA CARTE, qu'elle soit liée à une personne ou
anonyme (portefeuille éphémère : ancienne borne avec TPE, LaBoutik V1) :
- lecture : la fiche de la carte (`NFCcard.retrieve`, `GET card/{tag}/`), qui porte
  le portefeuille de la personne ou le portefeuille éphémère ;
- débit : la carte et la carte primaire du caissier, comme LaBoutik V1
  (`POST transaction/`, méthode `TransactionFedow.to_place`).
La signature de la personne n'est jamais utilisée.
/ The card must carry its owner when the old Fedow says it is linked. The FED is read
and debited THROUGH THE CARD, linked or anonymous, with the cashier's primary card.

Dans un lieu V2, le seul jeton legacy dépensable est le FED : un lieu V2 n'émet ni
n'accepte de monnaie locale legacy (raisons 3 et 5 de `Customers/bascule_vers_v2.py`).
Le débit par la carte est donc UNE transaction, sur le FED.
/ In a V2 venue the only spendable legacy token is FED: one transaction.

L'ANCIEN FEDOW EST SIMULÉ, JAMAIS APPELÉ
-----------------------------------------
- Une garde (fixture automatique) fait échouer tout envoi réseau du client Fedow
  (`fedow_connect.fedow_api._get` / `_post`).
- `NFCcardFedow.retrieve` (le rapatriement) et le client `FedowAPI` des vues sont
  simulés par `ancien_fedow_simule`, qui rend les VRAIES formes de réponse : une
  carte liée dit `is_wallet_ephemere: False`, une carte anonyme `True`.
/ The old Fedow is faked, with the real response shapes.

PIÈGES (tests/PIEGES.md)
- CarteCashless est en SHARED_APPS : pas de FastTenantTestCase (9.30).
- tenant_context, jamais schema_context (9.1).
- tag_id et number : 8 hexadécimaux neufs à chaque test (9.31, 11.10).
- Les vues activent une langue sans la remettre : fixture autouse (10.5).
- Tout est annulé par la transaction `django_db` (base de dev partagée).

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        tests/pytest/test_carte_liee_chez_fedow_fed_en_caisse.py -v
"""

import re
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client as ClientHttpDjango
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from BaseBillet.models import PaymentMethod
from fabriques_panier import (
    configuration_modifiee,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fedow_connect.fedow_api import CarteInconnueDeFedow, NFCcardFedow
from fedow_connect.models import FedowConfig
from laboutik.models import CartePrimaire
from QrcodeCashless.models import CarteCashless
from QrcodeCashless.services import trouver_ou_rapatrier_la_carte
from test_caisse_ecrit_la_vente import (
    cle_de_panier,
    creer_un_article_de_caisse,
    nouvelle_cle_d_idempotence,
    payer_un_panier_compose_a_la_caisse,
    retrouver_la_vente_de_la_cle,
)
from test_caracterisation_caisse import creer_un_point_de_vente
from test_caracterisation_en_ligne import creer_un_administrateur_du_lieu

pytestmark = pytest.mark.django_db

# Adresses des vues (laboutik/urls.py, BaseBillet/urls.py).
# / View addresses.
URL_DU_RETOUR_CARTE = "/laboutik/paiement/retour_carte/"
URL_DE_LA_LIAISON_PAR_QRCODE = "/qr/link/"

# Le domaine du lieu `lespass` de la base de dev. / The dev `lespass` venue domain.
DOMAINE_DU_LIEU = "lespass.tibillet.localhost"

# Le prix du café, en centimes et en texte. / The coffee price.
PRIX_DU_CAFE_EN_CENTIMES = 200
PRIX_DU_CAFE_EN_EUROS = "2.00"


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
    du client Fedow échoue, et la liste des envois tentés doit être vide à la fin.
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
    Le lieu `lespass`, caisse activée EN MÉMOIRE (`configuration_modifiee` ne sauve
    jamais la Configuration, tests/PIEGES.md 13.22), Celery simulé.
    / The `lespass` venue, register switched on in memory, Celery faked.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with taches_celery_enregistrees():
                yield SimpleNamespace(tenant=tenant)


# --------------------------------------------------------------------------
# L'ancien Fedow, simulé avec ses vraies formes de réponse
# / The old Fedow, faked with its real response shapes
# --------------------------------------------------------------------------


def tag_neuf():
    """Un tag NFC neuf : 8 hexadécimaux majuscules. / A fresh NFC tag."""
    return uuid.uuid4().hex[:8].upper()


def uuid_de_la_place_fedow_du_lieu():
    """
    L'uuid de la place Fedow du lieu courant, lu dans sa vraie configuration. Le
    rapatriement reconnaît une carte « du lieu courant » à cet uuid.
    / The current venue's Fedow place uuid, from its real configuration.
    """
    uuid_de_la_place = FedowConfig.get_solo().fedow_place_uuid
    if uuid_de_la_place is None:
        pytest.fail(
            "Le lieu lespass n'a pas de place Fedow (FedowConfig.fedow_place_uuid) "
            "dans la base de dev : ces tests supposent un lieu relié."
        )
    return uuid_de_la_place


def jeton_de_l_ancien_fedow(categorie, valeur_en_centimes, uuid_de_la_monnaie=None):
    """
    Un jeton du portefeuille d'une carte, tel que `GET card/{tag}/` le rend après
    `TokenValidator` (fedow_connect/validators.py). `categorie` : « FED » (monnaie
    fédérée) ou « TLF » (monnaie locale d'un lieu).
    / A card wallet token, as `GET card/{tag}/` returns it after TokenValidator.
    """
    uuid_de_la_monnaie = uuid_de_la_monnaie or uuid.uuid4()
    nom_de_la_monnaie = (
        "Euro fédéré" if categorie == "FED" else "Monnaie d'un autre lieu"
    )
    return {
        "uuid": uuid.uuid4(),
        "name": nom_de_la_monnaie,
        "value": valeur_en_centimes,
        "asset": {
            "uuid": uuid_de_la_monnaie,
            "name": nom_de_la_monnaie,
            "currency_code": "FED" if categorie == "FED" else "TLF",
            "category": categorie,
            "place_origin": None,
        },
        "asset_uuid": uuid_de_la_monnaie,
        "asset_name": nom_de_la_monnaie,
        "asset_category": categorie,
        "is_primary_stripe_token": categorie == "FED",
    }


def fiche_de_carte(tag_id, uuid_du_portefeuille, est_anonyme, jetons=()):
    """
    La carte telle que l'ancien Fedow la décrit (`GET card/{tag}/`, données validées
    par `CardValidator`), émise par le lieu courant.
    `est_anonyme` : True pour un portefeuille éphémère (carte sans personne), False
    pour une carte liée à une personne (son portefeuille EST celui de la personne).
    / The card as the old Fedow describes it, issued by the current venue.
    """
    return {
        "uuid": uuid.uuid4(),
        "qrcode_uuid": uuid.uuid4(),
        "first_tag_id": tag_id,
        "number_printed": tag_neuf(),
        "is_wallet_ephemere": est_anonyme,
        "is_primary": False,
        "wallet": {
            "uuid": uuid_du_portefeuille,
            "tokens": list(jetons),
            "get_name": "",
            "has_user_card": not est_anonyme,
        },
        "origin": {
            "place": {
                "uuid": uuid_de_la_place_fedow_du_lieu(),
                "name": "Lieu d'origine",
                "wallet": uuid.uuid4(),
                "lespass_domain": DOMAINE_DU_LIEU,
            },
            "generation": 1,
        },
    }


def proprietaire_avec_son_portefeuille():
    """
    Une personne connue de Lespass, avec son portefeuille local. Comme en production
    (`get_or_create_wallet`), le portefeuille local porte l'uuid de son portefeuille
    chez l'ancien Fedow.
    / A person known to Lespass, with a local wallet carrying the Fedow uuid.
    """
    proprietaire = creer_utilisateur(prenom="Proprietaire", nom="Carte")
    proprietaire.wallet = Wallet.objects.create(
        uuid=uuid.uuid4(),
        name=f"TEST_carte_liee portefeuille {proprietaire.email}",
    )
    proprietaire.save()
    return proprietaire


def carte_liee_chez_fedow_seulement(proprietaire, jetons=()):
    """
    Une carte chargée chez l'ancien Fedow, ABSENTE en local, que l'ancien Fedow dit
    liée à `proprietaire` : la situation d'une personne qui a lié sa carte par QR
    code avant tout scan en caisse. `jetons` : ceux du portefeuille de la personne.
    / A card only on the old Fedow, linked there to `proprietaire`, missing locally.
    """
    tag_id = tag_neuf()
    fiche = fiche_de_carte(
        tag_id,
        uuid_du_portefeuille=proprietaire.wallet.uuid,
        est_anonyme=False,
        jetons=jetons,
    )
    assert not CarteCashless.objects.filter(tag_id=tag_id).exists()
    return SimpleNamespace(tag_id=tag_id, fiche=fiche, proprietaire=proprietaire)


def carte_anonyme_chez_fedow_seulement(jetons):
    """
    Une carte anonyme chargée chez l'ancien Fedow, ABSENTE en local, dont le
    portefeuille éphémère porte `jetons` : le cas d'une carte rechargée à l'ancienne
    borne avec TPE, ou par LaBoutik V1. Le portefeuille miroir local existe déjà, comme
    après la lecture par le `CardValidator`.
    / An anonymous card only on the old Fedow, whose ephemeral wallet holds `jetons`.
    """
    tag_id = tag_neuf()
    portefeuille_ephemere = Wallet.objects.create(
        uuid=uuid.uuid4(), name=f"TEST_carte_anonyme portefeuille {tag_id}"
    )
    fiche = fiche_de_carte(
        tag_id,
        uuid_du_portefeuille=portefeuille_ephemere.uuid,
        est_anonyme=True,
        jetons=jetons,
    )
    return SimpleNamespace(
        tag_id=tag_id, fiche=fiche, portefeuille_ephemere=portefeuille_ephemere
    )


@contextmanager
def ancien_fedow_simule(fiches=(), debit_par_la_carte=None):
    """
    L'ancien Fedow, simulé à deux endroits :
    - `NFCcardFedow.retrieve` au niveau de la classe (le rapatriement l'appelle par
      `NFCcardFedow(config).retrieve`) ;
    - le client `FedowAPI` de la caisse (`laboutik.views.FedowAPI`).
    Le lieu est dit relié (`can_fedow`).
    / The old Fedow, faked at the class level and as the register's FedowAPI client.

    :param fiches: les cartes que l'ancien Fedow connaît (forme `fiche_de_carte`).
    :param debit_par_la_carte: la transaction que rend un débit par la carte
        (`transaction.to_place`), ou None.
    :return: SimpleNamespace(client_de_la_caisse) — le faux `FedowAPI()`, pour
        vérifier les appels.
    """
    fiche_par_tag = {}
    for fiche in fiches:
        fiche_par_tag[fiche["first_tag_id"]] = fiche

    def lire_la_fiche(tag_id):
        fiche_connue = fiche_par_tag.get(tag_id)
        if fiche_connue is None:
            raise CarteInconnueDeFedow(f"Carte inconnue de Fedow : {tag_id}")
        return fiche_connue

    def faux_retrieve_de_la_classe(self, tag_id):
        return lire_la_fiche(tag_id)

    def faux_card_tag_id_retrieve(tag_id):
        fiche_connue = fiche_par_tag.get(tag_id)
        if fiche_connue is None:
            return None
        return {
            "wallet_uuid": fiche_connue["wallet"]["uuid"],
            "is_wallet_ephemere": fiche_connue["is_wallet_ephemere"],
            "origin": fiche_connue["origin"],
        }

    def lecture_par_signature_interdite(user, use_cache=True):
        raise AssertionError(
            f"Le FED se lit par la carte, jamais par la signature de {user}."
        )

    def debit_par_signature_interdit(*arguments, **arguments_nommes):
        raise AssertionError("Le FED se débite par la carte, jamais par la signature.")

    client_de_la_caisse = MagicMock()
    client_de_la_caisse.NFCcard.retrieve.side_effect = lire_la_fiche
    client_de_la_caisse.NFCcard.card_tag_id_retrieve.side_effect = (
        faux_card_tag_id_retrieve
    )
    client_de_la_caisse.wallet.get_total_fiducial_and_all_federated_token.side_effect = (
        lecture_par_signature_interdite
    )
    client_de_la_caisse.transaction.to_place_from_qrcode.side_effect = (
        debit_par_signature_interdit
    )
    if debit_par_la_carte is not None:
        client_de_la_caisse.transaction.to_place.return_value = debit_par_la_carte

    with patch.object(FedowConfig, "can_fedow", return_value=True):
        with patch.object(NFCcardFedow, "retrieve", new=faux_retrieve_de_la_classe):
            with patch("laboutik.views.FedowAPI", return_value=client_de_la_caisse):
                yield SimpleNamespace(client_de_la_caisse=client_de_la_caisse)


def transaction_de_l_ancien_fedow(uuid_de_la_monnaie, montant_en_centimes):
    """
    Une transaction FED telle que l'ancien Fedow la rend après un débit par la carte
    (`POST transaction/`), réduite aux champs que la caisse lit.
    / A FED transaction as the old Fedow returns it, reduced to the fields read.
    """
    return {
        "uuid": str(uuid.uuid4()),
        "asset": str(uuid_de_la_monnaie),
        "amount": montant_en_centimes,
    }


# --------------------------------------------------------------------------
# La caisse
# / The register
# --------------------------------------------------------------------------


def preparer_la_caisse_et_le_cafe(lieu):
    """
    Un café à 2 € sur un point de vente, la carte primaire du caissier (autorisée sur
    ce point de vente) et le caissier connecté, qui demande les écrans en français.
    / A 2 € coffee at a point of sale, the cashier's primary card, the cashier.
    """
    cafe = creer_un_article_de_caisse(
        "cafe", prix_en_euros=PRIX_DU_CAFE_EN_EUROS, taux_tva="10.00"
    )
    point_de_vente = creer_un_point_de_vente([cafe.produit])
    tag_de_la_carte_primaire = identifiant_unique().upper()[:8]
    carte_du_caissier = CarteCashless.objects.create(
        tag_id=tag_de_la_carte_primaire,
        number=tag_de_la_carte_primaire,
        uuid=uuid.uuid4(),
    )
    carte_primaire = CartePrimaire.objects.create(
        carte=carte_du_caissier, edit_mode=False
    )
    carte_primaire.points_de_vente.add(point_de_vente)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    client_du_caissier.defaults["HTTP_ACCEPT_LANGUAGE"] = "fr"
    return SimpleNamespace(
        cafe=cafe,
        point_de_vente=point_de_vente,
        carte_du_caissier=carte_du_caissier,
        client_du_caissier=client_du_caissier,
    )


def payer_le_cafe_avec_la_carte(caisse, tag_id, cle_d_idempotence):
    """Le client paie le café en posant sa carte. / The customer taps to pay."""
    return payer_un_panier_compose_a_la_caisse(
        caisse.client_du_caissier,
        caisse.point_de_vente,
        {f"repid-{cle_de_panier(caisse.cafe)}": "1"},
        moyen_de_paiement="nfc",
        cle_d_idempotence=cle_d_idempotence,
        autres_champs={
            "tag_id": tag_id,
            "tag_id_cm": caisse.carte_du_caissier.tag_id,
        },
    )


def check_carte(caisse, tag_id):
    """Le client pose sa carte sur « check carte ». / The customer taps on card check."""
    return caisse.client_du_caissier.post(
        URL_DU_RETOUR_CARTE,
        {"tag_id": tag_id, "tag_id_cm": caisse.carte_du_caissier.tag_id},
    )


def reglements_de_la_vente(vente):
    """Les règlements d'une vente : (moyen, montant, référence externe).
    / A sale's payments: (method, amount, external reference)."""
    reglements = []
    for reglement in vente.reglements.all():
        reglements.append(
            (reglement.moyen, reglement.montant, reglement.reference_externe)
        )
    return reglements


# ==========================================================================
# 1 — Le rapatriement pose la propriétaire d'une carte liée chez Fedow
# / 1 — Fetching sets the owner of a card linked on Fedow
# ==========================================================================


def test_rapatriement_d_une_carte_liee_chez_fedow_pose_sa_proprietaire(lieu):
    """
    L'ancien Fedow dit la carte liée (`is_wallet_ephemere: False`), et son portefeuille
    est celui d'une personne connue ici : la carte rapatriée porte cette personne.
    / The old Fedow says the card is linked to a known person: the fetched card
    carries that person.
    """
    proprietaire = proprietaire_avec_son_portefeuille()
    carte_fedow = carte_liee_chez_fedow_seulement(proprietaire)

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]):
        carte_rapatriee = trouver_ou_rapatrier_la_carte(carte_fedow.tag_id)

    carte_relue = CarteCashless.objects.get(pk=carte_rapatriee.pk)
    assert carte_relue.user_id == proprietaire.pk, (
        "L'ancien Fedow dit la carte liée à cette personne, mais la carte locale n'a "
        "pas de propriétaire : la caisse la prendra pour une carte anonyme et ne "
        "lira pas son FED."
    )


def test_rapatriement_d_une_carte_liee_a_un_portefeuille_inconnu_ici_reste_sans_proprietaire(
    lieu,
):
    """
    TÉMOIN. L'ancien Fedow dit la carte liée, mais aucune personne de Lespass ne porte
    ce portefeuille : la carte est rapatriée sans propriétaire, sans erreur. Le scan
    ne doit jamais casser pour ça.
    / WITNESS. Linked on Fedow to a wallet unknown here: fetched without owner, no error.
    """
    tag_id = tag_neuf()
    fiche = fiche_de_carte(tag_id, uuid_du_portefeuille=uuid.uuid4(), est_anonyme=False)

    with ancien_fedow_simule(fiches=[fiche]):
        carte_rapatriee = trouver_ou_rapatrier_la_carte(tag_id)

    assert CarteCashless.objects.get(pk=carte_rapatriee.pk).user_id is None


# ==========================================================================
# 2 — La liaison par QR code crée la carte locale avec sa propriétaire
# / 2 — Linking by QR code creates the local card with its owner
# ==========================================================================


def test_liaison_par_qrcode_d_une_carte_absente_en_local_la_cree_avec_sa_proprietaire(
    lieu,
):
    """
    La personne scanne le QR de sa carte et donne son email AVANT tout scan en caisse :
    la carte n'existe que chez l'ancien Fedow. L'ancien Fedow lie la carte et rend sa
    fiche complète. La carte locale doit alors exister, avec cette personne.
    / The person links the card by QR code BEFORE any register scan: the local card
    must then exist, with that person.
    """
    proprietaire = proprietaire_avec_son_portefeuille()
    carte_fedow = carte_liee_chez_fedow_seulement(proprietaire)
    uuid_du_qrcode = carte_fedow.fiche["qrcode_uuid"]

    client_de_la_liaison = MagicMock()
    client_de_la_liaison.wallet.get_or_create_wallet.return_value = (
        proprietaire.wallet,
        True,
    )
    client_de_la_liaison.NFCcard.linkwallet_cardqrcode.return_value = carte_fedow.fiche

    navigateur = ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU)
    with patch.object(FedowConfig, "can_fedow", return_value=True):
        with patch("BaseBillet.views.FedowAPI", return_value=client_de_la_liaison):
            with patch(
                "BaseBillet.views.get_or_create_user", return_value=proprietaire
            ):
                reponse = navigateur.post(
                    URL_DE_LA_LIAISON_PAR_QRCODE,
                    {
                        "email": proprietaire.email,
                        "emailConfirmation": proprietaire.email,
                        "cgu": True,
                        "qrcode_uuid": str(uuid_du_qrcode),
                    },
                )

    assert reponse.status_code in (200, 204, 302), reponse.status_code
    assert client_de_la_liaison.NFCcard.linkwallet_cardqrcode.called
    carte_locale = CarteCashless.objects.filter(uuid=uuid_du_qrcode).first()
    assert carte_locale is not None, (
        "La carte est liée chez l'ancien Fedow, mais aucune carte locale n'a été "
        "créée : au premier scan, la caisse la rapatriera sans propriétaire."
    )
    assert carte_locale.tag_id == carte_fedow.tag_id
    assert carte_locale.user_id == proprietaire.pk
    assert carte_locale.detail.origine_id == lieu.tenant.pk


# ==========================================================================
# 3 — Caisse : une carte liée seulement chez Fedow montre et dépense son FED
# / 3 — Register: a card linked only on Fedow shows and spends its FED
# ==========================================================================


def test_check_carte_d_une_carte_liee_chez_fedow_seulement_affiche_son_fed(lieu):
    """
    LE BUG DE PRODUCTION. La personne a lié sa carte par QR code et rechargé 12 € de
    FED en ligne ; la carte n'a jamais été scannée en caisse. Au premier « check
    carte », la carte est rapatriée : la fiche doit montrer la personne et ses 12 €.
    / THE PRODUCTION BUG. First card check after a QR link and an online FED top-up.
    """
    caisse = preparer_la_caisse_et_le_cafe(lieu)
    proprietaire = proprietaire_avec_son_portefeuille()
    carte_fedow = carte_liee_chez_fedow_seulement(
        proprietaire, jetons=[jeton_de_l_ancien_fedow("FED", 1200)]
    )

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]):
        reponse = check_carte(caisse, carte_fedow.tag_id)

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="retour-carte-anonyme"' not in contenu, (
        "La carte est liée chez l'ancien Fedow, mais la caisse l'affiche anonyme."
    )
    assert 'data-testid="retour-carte-solde-fed"' in contenu, (
        "Le FED de la personne n'est pas affiché au check carte."
    )
    assert "12,00" in contenu or "12.00" in contenu


def test_cafe_paye_en_fed_avec_une_carte_liee_chez_fedow_seulement(lieu):
    """
    LE BUG DE PRODUCTION, au paiement. Même carte (liée par QR code, 12 € de FED, jamais
    scannée en caisse) : le café à 2 € est payé en FED, sans écran de complément. Le
    débit part par la carte et la carte primaire du caissier, depuis le portefeuille
    de la personne, et la vente a un règlement FED (SF) de 2 €.
    / THE PRODUCTION BUG, at payment: the coffee is paid in FED, no complement screen,
    debited through the card and the cashier's primary card.
    """
    caisse = preparer_la_caisse_et_le_cafe(lieu)
    proprietaire = proprietaire_avec_son_portefeuille()
    uuid_du_fed = uuid.uuid4()
    carte_fedow = carte_liee_chez_fedow_seulement(
        proprietaire,
        jetons=[jeton_de_l_ancien_fedow("FED", 1200, uuid_de_la_monnaie=uuid_du_fed)],
    )
    debit_du_fed = transaction_de_l_ancien_fedow(uuid_du_fed, PRIX_DU_CAFE_EN_CENTIMES)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    with ancien_fedow_simule(
        fiches=[carte_fedow.fiche], debit_par_la_carte=debit_du_fed
    ) as fedow:
        reponse = payer_le_cafe_avec_la_carte(
            caisse, carte_fedow.tag_id, cle_d_idempotence
        )

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="paiement-succes"' in contenu, (
        "Le café n'est pas payé en FED : la caisse a pris la carte pour une carte "
        "anonyme sans solde (écran de complément)."
    )
    debit = fedow.client_de_la_caisse.transaction.to_place
    assert debit.call_count == 1
    arguments_du_debit = debit.call_args.kwargs
    assert arguments_du_debit["amount"] == PRIX_DU_CAFE_EN_CENTIMES
    assert str(arguments_du_debit["asset"]) == str(uuid_du_fed)
    assert str(arguments_du_debit["wallet"]) == str(proprietaire.wallet.uuid)
    assert arguments_du_debit["user_card_firstTagId"] == carte_fedow.tag_id
    assert (
        arguments_du_debit["primary_card_fisrtTagId"] == caisse.carte_du_caissier.tag_id
    )
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert reglements_de_la_vente(vente) == [
        (PaymentMethod.STRIPE_FED, PRIX_DU_CAFE_EN_CENTIMES, debit_du_fed["uuid"])
    ]


# ==========================================================================
# 4 — Caisse : une carte anonyme montre et dépense le FED de son portefeuille
# / 4 — Register: an anonymous card shows and spends its wallet's FED
# ==========================================================================


def test_check_carte_d_une_carte_anonyme_affiche_le_fed_de_son_portefeuille(lieu):
    """
    Une carte anonyme rechargée à l'ancienne borne (TPE) porte 15 € de FED sur son
    portefeuille éphémère, et 7 € de la monnaie d'un AUTRE lieu, non fédérée ici. Le
    « check carte » lit la fiche de la carte (clé du lieu, sans signature de personne)
    et affiche 15 € de FED, sans les 7 € qui ne se dépensent pas ici.
    / An anonymous card with 15 € FED and 7 € of a non-federated currency: the card
    check shows 15 € of FED, not the 7 €.
    """
    caisse = preparer_la_caisse_et_le_cafe(lieu)
    carte_fedow = carte_anonyme_chez_fedow_seulement(
        jetons=[
            jeton_de_l_ancien_fedow("FED", 1500),
            jeton_de_l_ancien_fedow("TLF", 700),
        ]
    )

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = check_carte(caisse, carte_fedow.tag_id)

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="retour-carte-solde-fed"' in contenu, (
        "Le FED du portefeuille éphémère de la carte anonyme n'est pas affiché."
    )
    assert "15,00" in contenu or "15.00" in contenu
    assert "22,00" not in contenu and "22.00" not in contenu, (
        "La monnaie d'un autre lieu, non fédérée ici, est comptée dans le solde."
    )


def test_cafe_paye_en_fed_par_une_carte_anonyme_debite_par_la_carte_et_la_carte_primaire(
    lieu,
):
    """
    La même carte anonyme (15 € de FED sur son portefeuille éphémère) paie le café à
    2 €. Sans personne, pas de signature : la caisse débite comme LaBoutik V1, par la
    carte du client et la carte primaire du caissier (`transaction.to_place`, route
    `POST transaction/` de l'ancien Fedow). Une seule transaction, sur le FED, depuis
    le portefeuille de la carte. La vente a un règlement FED (SF) de 2 €.
    / The anonymous card pays the coffee: debited by card + primary card, like V1.
    """
    caisse = preparer_la_caisse_et_le_cafe(lieu)
    uuid_du_fed = uuid.uuid4()
    carte_fedow = carte_anonyme_chez_fedow_seulement(
        jetons=[jeton_de_l_ancien_fedow("FED", 1500, uuid_de_la_monnaie=uuid_du_fed)]
    )
    debit_du_fed = transaction_de_l_ancien_fedow(uuid_du_fed, PRIX_DU_CAFE_EN_CENTIMES)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    with ancien_fedow_simule(
        fiches=[carte_fedow.fiche], debit_par_la_carte=debit_du_fed
    ) as fedow:
        reponse = payer_le_cafe_avec_la_carte(
            caisse, carte_fedow.tag_id, cle_d_idempotence
        )

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="paiement-succes"' in contenu, (
        "Le café n'est pas payé avec le FED de la carte anonyme."
    )
    debit = fedow.client_de_la_caisse.transaction.to_place
    assert debit.call_count == 1, "Attendu : un seul débit par la carte, sur le FED."
    arguments_du_debit = debit.call_args.kwargs
    assert arguments_du_debit["amount"] == PRIX_DU_CAFE_EN_CENTIMES
    assert str(arguments_du_debit["asset"]) == str(uuid_du_fed)
    assert str(arguments_du_debit["wallet"]) == str(carte_fedow.fiche["wallet"]["uuid"])
    assert arguments_du_debit["user_card_firstTagId"] == carte_fedow.tag_id
    assert (
        arguments_du_debit["primary_card_fisrtTagId"] == caisse.carte_du_caissier.tag_id
    )
    # Traçabilité caisse ↔ ancien Fedow : l'uuid de la vente part avec le débit.
    # / Register ↔ old Fedow traceability: the sale uuid goes with the debit.
    assert "uuid_transaction" in arguments_du_debit["metadata"]
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert reglements_de_la_vente(vente) == [
        (PaymentMethod.STRIPE_FED, PRIX_DU_CAFE_EN_CENTIMES, debit_du_fed["uuid"])
    ]


def extraire_le_reste_a_payer(contenu_html):
    """
    Le « reste à payer » de l'écran de complément, en euros avec un point ('1.00'),
    ou None. Même lecture que tests/pytest/test_paiement_complementaire.py.
    / The complement screen's remaining amount ('1.00'), or None.
    """
    motif = re.compile(
        r"complement-reste-a-payer.*?<strong>\s*([0-9.,]+)\s*€", re.DOTALL
    )
    correspondance = motif.search(contenu_html)
    if correspondance is None:
        return None
    return correspondance.group(1).replace(",", ".")


def test_carte_anonyme_au_fed_insuffisant_ne_compte_que_son_fed_et_passe_au_complement(
    lieu,
):
    """
    La carte anonyme ne porte que 1 € de FED, et 7 € de la monnaie d'un autre lieu, qui
    ne se dépense pas ici. Le café à 2 € ne peut pas être payé par la carte seule :
    l'écran de complément s'affiche, avec 1 € pris sur le FED et 1 € de reste. Aucun
    débit n'est fait à ce stade : il part à la validation du complément.
    Une correction qui additionnerait tous les jetons de la carte (8 €) « paierait »
    le café : ce test la fait tomber.
    / The anonymous card holds 1 € of FED and 7 € of a non-spendable currency: the
    complement screen shows 1 € remaining. A fix summing every token would "pay".
    """
    caisse = preparer_la_caisse_et_le_cafe(lieu)
    carte_fedow = carte_anonyme_chez_fedow_seulement(
        jetons=[
            jeton_de_l_ancien_fedow("FED", 100),
            jeton_de_l_ancien_fedow("TLF", 700),
        ]
    )

    with ancien_fedow_simule(fiches=[carte_fedow.fiche]) as fedow:
        reponse = payer_le_cafe_avec_la_carte(
            caisse, carte_fedow.tag_id, nouvelle_cle_d_idempotence()
        )

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="paiement-succes"' not in contenu, (
        "Le café est payé alors que la carte n'a que 1 € de FED dépensable ici : "
        "la monnaie d'un autre lieu a été comptée."
    )
    assert 'data-testid="complement-paiement"' in contenu
    assert extraire_le_reste_a_payer(contenu) == "1.00", (
        "Le FED de la carte anonyme (1 €) n'est pas pris en compte dans le reste."
    )
    fedow.client_de_la_caisse.transaction.to_place.assert_not_called()
