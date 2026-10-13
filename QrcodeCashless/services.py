"""
Services des cartes NFC : rapatriement depuis l'ancien Fedow.
/ NFC card services: fetching cards from the old Fedow.

LOCALISATION : QrcodeCashless/services.py

L'ancien Fedow (`../Fedow`) est la source de vérité des cartes. `CarteCashless` est
un miroir local. Une carte chargée chez Fedow (`import_cards`) n'existe pas encore
ici : elle est rapatriée au premier scan, carte par carte, comme dans LaBoutik V1.
Fedow n'a aucune route qui liste les cartes d'un lieu.

Spec : TECH_DOC/SESSIONS/QRCODECASHLESS/CHANTIER-02-rapatriement-cartes-fedow.md
"""

import logging
import re

from django.db import IntegrityError, connection, transaction
from django.utils.translation import gettext_lazy as _

from AuthBillet.models import Wallet
from Customers.models import Client, Domain
from QrcodeCashless.models import CarteCashless, Detail
from fedow_connect.fedow_api import CarteInconnueDeFedow, NFCcardFedow
from fedow_connect.models import FedowConfig

logger = logging.getLogger(__name__)

# Un tag NFC : exactement 8 caractères hexadécimaux, en majuscules.
# / An NFC tag: exactly 8 uppercase hexadecimal characters.
MOTIF_TAG_NFC = re.compile(r"^[0-9A-F]{8}$")


class FedowInjoignable(Exception):
    """
    L'ancien Fedow ne répond pas, ou répond une fiche de carte illisible.
    / The old Fedow does not answer, or answers an unreadable card record.

    LOCALISATION : QrcodeCashless/services.py

    À distinguer d'une carte inconnue : l'écran dit « Fedow injoignable », pas
    « Carte inconnue ». Les points de scan affichent `message_pour_l_ecran`.
    """

    message_pour_l_ecran = _(
        "Fedow injoignable : la carte n'a pas pu être vérifiée. Réessayez."
    )


class CarteDUnLieuNonMigre(Exception):
    """
    La carte vient d'un lieu encore sur l'ancien moteur (legacy), ou d'un lieu
    introuvable. Elle est refusée : aucune CarteCashless ni aucun Detail n'est créé.
    / The card comes from a venue still on the old engine, or an unknown venue.

    LOCALISATION : QrcodeCashless/services.py

    POURQUOI : créer le Detail d'un lieu legacy le retiendrait en legacy (raison 6
    de Customers/bascule_vers_v2.py, « Des cartes NFC sont rattachées à votre
    lieu »). Un scan fait ailleurs l'empêcherait de passer en V2.
    Les points de scan affichent `message_pour_l_ecran`.
    """

    message_pour_l_ecran = _(
        "Cette carte vient d'un lieu qui n'utilise pas encore le nouveau moteur TiBillet."
    )


def trouver_ou_rapatrier_la_carte(tag_id):
    """
    Renvoie la CarteCashless locale du tag. Si elle manque et que le lieu est relié
    à l'ancien Fedow, la lit chez Fedow et fabrique le miroir local.
    / Returns the local CarteCashless of the tag. If missing and the venue is linked
    to the old Fedow, reads it there and builds the local mirror.

    LOCALISATION : QrcodeCashless/services.py

    À appeler dans un schéma tenant : lit FedowConfig (TENANT_APPS) et
    connection.tenant. JAMAIS dans un bloc transaction.atomic() : l'appel réseau
    tiendrait un verrou de base, jusqu'à 30 s si Fedow est en panne.

    FLUX :
    1. Tag nettoyé et mis en majuscules.
    2. Carte locale trouvée -> renvoyée, sans appel réseau. Sinon, tag contrôlé
       (8 hexadécimaux) avant tout appel réseau.
    3. Lieu non relié à l'ancien Fedow -> DoesNotExist, sans appel réseau.
    4. Lecture de la carte chez Fedow.
    5. Choix du lieu d'origine (refus si legacy ou introuvable), sans écriture.
    6. Création du Detail (si besoin) et de la carte, dans un savepoint.
    7. Origine posée sur le Wallet miroir, s'il n'en a pas.

    :param tag_id: tag NFC lu (str)
    :return: CarteCashless
    :raises CarteCashless.DoesNotExist: tag invalide, carte inconnue en local ET chez
        Fedow, lieu non relié à l'ancien Fedow, ou collision d'identifiant.
    :raises FedowInjoignable: Fedow ne répond pas, ou répond une fiche illisible.
    :raises CarteDUnLieuNonMigre: carte d'un lieu legacy ou introuvable. Les miroirs
        Wallet/Asset écrits par le CardValidator pendant la lecture restent : c'est
        l'effet de bord accepté de fedow_connect.
    """
    # 1. Tag nettoyé et mis en majuscules.
    # / Tag cleaned and uppercased.
    tag_id_propre = str(tag_id or "").strip().upper()

    # 2. Carte déjà connue ici : aucun appel réseau. La recherche locale passe AVANT
    #    le contrôle du format : une carte locale au tag non hexadécimal (données de
    #    test ou de démo) doit rester trouvée, comme avant ce service.
    # / Card already known here: no network call. Local lookup comes BEFORE the
    #   format check, so a local card with a non-hex tag is still found.
    carte_locale = CarteCashless.objects.filter(tag_id=tag_id_propre).first()
    if carte_locale is not None:
        return carte_locale

    # Contrôle du format AVANT tout appel réseau : sans lui, un tag vide partirait
    # en « GET card// ».
    # / Format check BEFORE any network call.
    tag_id_valide = MOTIF_TAG_NFC.match(tag_id_propre) is not None
    if not tag_id_valide:
        raise CarteCashless.DoesNotExist(f"Tag NFC invalide : {tag_id_propre!r}")

    # 3. Lieu non relié à l'ancien Fedow : rien à demander.
    # / Venue not linked to the old Fedow: nothing to ask.
    fedow_config = FedowConfig.get_solo()
    if not fedow_config.can_fedow():
        raise CarteCashless.DoesNotExist(
            f"Carte {tag_id_propre} inconnue, lieu non relié à Fedow"
        )

    # 4. Lecture chez l'ancien Fedow.
    # / Read on the old Fedow.
    try:
        fiche_fedow = NFCcardFedow(fedow_config).retrieve(tag_id_propre)
    except CarteInconnueDeFedow:
        raise CarteCashless.DoesNotExist(
            f"Carte {tag_id_propre} inconnue, ici et chez Fedow"
        )
    except Exception as erreur_de_fedow:
        logger.error(
            f"Rapatriement de la carte {tag_id_propre} : Fedow injoignable : {erreur_de_fedow}"
        )
        raise FedowInjoignable(str(erreur_de_fedow))

    # 5. Lieu d'origine de la carte. Peut refuser : aucune écriture avant ce point.
    # / Card's venue of origin. May refuse: no write before this point.
    lieu_d_origine = _trouver_le_lieu_d_origine(
        fiche_fedow, fedow_config, tag_id_propre
    )
    generation = fiche_fedow["origin"]["generation"]

    # 6. Création, dans un savepoint. Le except reste HORS du atomic : sinon la
    #    transaction englobante est cassée (« current transaction is aborted »).
    # / Creation inside a savepoint. The except stays OUTSIDE the atomic block.
    try:
        with transaction.atomic():
            detail = _obtenir_ou_creer_le_detail(lieu_d_origine, generation)
            carte_rapatriee = CarteCashless.objects.create(
                tag_id=fiche_fedow["first_tag_id"].upper(),
                number=fiche_fedow["number_printed"].upper(),
                uuid=fiche_fedow["qrcode_uuid"],
                detail=detail,
            )
    except IntegrityError:
        # Deux scans simultanés : l'autre a créé la carte. On la renvoie.
        # / Two simultaneous scans: the other one created the card.
        carte_creee_entre_temps = CarteCashless.objects.filter(
            tag_id=tag_id_propre
        ).first()
        if carte_creee_entre_temps is not None:
            return carte_creee_entre_temps

        # Le numéro ou l'uuid est déjà porté par une AUTRE carte locale. Unicité
        # globale à toutes les instances (CarteCashless est en SHARED_APPS).
        # / The number or uuid already belongs to ANOTHER local card.
        logger.error(
            f"Rapatriement impossible : collision d'identifiant pour la carte "
            f"tag={tag_id_propre} number={fiche_fedow['number_printed']} "
            f"uuid={fiche_fedow['qrcode_uuid']}"
        )
        raise CarteCashless.DoesNotExist(
            f"Carte {tag_id_propre} : collision d'identifiant en local"
        )

    # 7. Le Wallet miroir, créé sans origine par le CardValidator, reçoit celle du
    #    lieu. Une origine existante n'est jamais écrasée. Sinon,
    #    obtenir_wallet_carte_depuis_fedow (laboutik/views.py) trouverait ce Wallet
    #    et ne poserait jamais l'origine.
    # / The mirror Wallet gets the venue as origin, never overwriting one.
    uuid_du_portefeuille = fiche_fedow["wallet"]["uuid"]
    Wallet.objects.filter(uuid=uuid_du_portefeuille, origin__isnull=True).update(
        origin=connection.tenant,
    )

    # Fedow la dit primaire pour ce lieu : on ne crée pas de CartePrimaire (elle
    # n'aurait aucun point de vente). Le gestionnaire la déclare dans l'admin.
    # / Fedow says primary for this venue: no CartePrimaire is created.
    if fiche_fedow.get("is_primary"):
        logger.info(
            f"Carte {tag_id_propre} rapatriée : carte primaire chez Fedow, "
            f"à déclarer dans l'admin des cartes primaires."
        )

    logger.info(
        f"Carte {tag_id_propre} rapatriée depuis Fedow (lieu d'origine : {lieu_d_origine})."
    )
    return carte_rapatriee


def _trouver_le_lieu_d_origine(fiche_fedow, fedow_config, tag_id):
    """
    Trouve le lieu (Client) qui a émis la carte, d'après la fiche Fedow.
    / Finds the venue (Client) that issued the card, from the Fedow record.

    LOCALISATION : QrcodeCashless/services.py

    - Le lieu courant : reconnu par l'uuid de sa place Fedow. Il est toujours v2 :
      caisse, borne et tireuse sont fermées aux lieux legacy.
    - Un autre lieu : retrouvé par `lespass_domain` -> Domain -> tenant. Accepté
      seulement s'il est v2.
    - Lieu legacy, ou introuvable : refus.

    LIMITE CONNUE : Fedow écrit `lespass_domain` une seule fois, à la création du
    lieu. Un lieu qui a changé de domaine sans garder l'ancien en Domain devient
    introuvable.

    :raises CarteDUnLieuNonMigre: lieu legacy ou introuvable
    """
    place_fedow = fiche_fedow["origin"]["place"]

    carte_du_lieu_courant = str(place_fedow["uuid"]) == str(
        fedow_config.fedow_place_uuid
    )
    if carte_du_lieu_courant:
        return connection.tenant

    lespass_domain = place_fedow.get("lespass_domain")
    domaine_du_lieu_d_origine = None
    if lespass_domain:
        domaine_du_lieu_d_origine = (
            Domain.objects.filter(domain=lespass_domain)
            .select_related("tenant")
            .first()
        )

    if domaine_du_lieu_d_origine is None:
        logger.info(
            f"Carte {tag_id} refusée : lieu d'origine introuvable "
            f"(place {place_fedow.get('name')}, domaine {lespass_domain!r})."
        )
        raise CarteDUnLieuNonMigre(f"Carte {tag_id} : lieu d'origine introuvable")

    lieu_d_origine = domaine_du_lieu_d_origine.tenant
    lieu_d_origine_en_v2 = lieu_d_origine.moteur_monnaie == Client.MOTEUR_V2
    if not lieu_d_origine_en_v2:
        logger.info(
            f"Carte {tag_id} refusée : son lieu d'origine {lieu_d_origine} est legacy."
        )
        raise CarteDUnLieuNonMigre(f"Carte {tag_id} : lieu d'origine legacy")

    return lieu_d_origine


def _obtenir_ou_creer_le_detail(lieu, generation):
    """
    Renvoie la génération de cartes (Detail) du lieu, créée si elle manque.
    / Returns the venue's card generation (Detail), created if missing.

    LOCALISATION : QrcodeCashless/services.py

    Pas de get_or_create : le couple (origine, generation) n'a aucune contrainte
    d'unicité, un lieu peut en porter plusieurs. On prend le premier par pk.
    Detail est en SHARED_APPS : écrire celui d'un autre lieu ne change pas de schéma.

    Le base_url reprend le calcul de _obtenir_la_generation_par_defaut_du_lieu
    (QrcodeCashless/admin.py). Ce module n'importe pas admin.py, qui tire
    Administration.
    """
    detail_existant = (
        Detail.objects.filter(origine=lieu, generation=generation)
        .order_by("pk")
        .first()
    )
    if detail_existant is not None:
        return detail_existant

    # base_url préfixe l'UUID dans le QR code imprimé. On ne le remplit que s'il
    # tient dans les 60 caractères du champ.
    # / base_url prefixes the printed QR code UUID; only set if it fits.
    base_url = None
    domaine_du_lieu = lieu.get_primary_domain()
    if domaine_du_lieu:
        adresse_des_qrcodes = f"https://{domaine_du_lieu.domain}/qr/"
        longueur_maximale = Detail._meta.get_field("base_url").max_length
        if len(adresse_des_qrcodes) <= longueur_maximale:
            base_url = adresse_des_qrcodes

    return Detail.objects.create(
        origine=lieu,
        generation=generation,
        base_url=base_url,
    )
