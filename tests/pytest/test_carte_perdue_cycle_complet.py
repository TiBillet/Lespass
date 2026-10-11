"""
Carte perdue : le cycle complet, avec le vrai Fedow de dev.
/ Lost card: the full cycle, with the real dev Fedow.

LOCALISATION : tests/pytest/test_carte_perdue_cycle_complet.py

POURQUOI / WHY :
Le lien carte <-> porteur est note a DEUX endroits :
- chez Fedow (`Card.user`), lu par la caisse V1 et « Mon compte » ;
- dans Lespass (`CarteCashless.user`, table partagee par tous les lieux), lu EN PREMIER par
  la caisse V2 (`laboutik.views._obtenir_ou_creer_wallet`), sans demander a Fedow.
Si une perte n'efface le lien que chez Fedow, la caisse V2 continue d'ouvrir le
portefeuille de l'ancien porteur : qui trouve la carte depense l'argent de qui l'a perdue.
Et le porteur ne peut plus lier de nouvelle carte cote Lespass (`UserADejaCarte`).
La fonction testee : `BaseBillet.views.declarer_la_carte_perdue`, appelee par les deux
boutons « carte perdue » (espace de l'usager et fiche admin).
/ The card <-> holder link lives in two places; the V2 POS reads the Lespass one first.

LE CYCLE TESTE (une variante par facon de declarer la perte) :
1. Un adherent lie la carte A (comme le parcours /qr : Fedow puis Lespass).
2. Son portefeuille est credite : monnaie locale chez Fedow + jetons locaux V2.
3. La carte A est declaree perdue.
4. A est anonyme chez Fedow ET dans Lespass ; la caisse V2 n'ouvre plus son portefeuille.
5. Il lie une carte B : elle est a lui des deux cotes, et ses deux soldes sont intacts.

LES VARIANTES :
- `mon_compte` : l'usager clique « carte perdue » dans /my_account/ ;
- `admin` : un admin du lieu clique « carte perdue » sur la fiche de l'usager ;
- `autre_client_fedow` : la carte est detachee chez Fedow par un autre client que Lespass
  (appel Fedow direct). Lespass n'en sait rien : la carte reste liee dans sa base. Cette
  variante est en xfail STRICT : elle prouve le trou, et devient ROUGE le jour ou il est
  bouche (on retire alors le xfail). Une vue Lespass ne peut pas la corriger : il faut une
  piste de fond (verification Fedow au scan en caisse V2, webhook Fedow, ou reconciliation).
  ATTENTION : elle ne reproduit PAS la methode « VV » de la caisse V1, qui REMBOURSE d'abord
  au lieu les jetons du lieu et le FED, puis detache. Seul le detachement est simule.
/ The `autre_client_fedow` variant is a strict xfail: it proves the gap and turns red once fixed.

DONNEES LAISSEES CHEZ FEDOW : chaque passage cree chez le Fedow de dev des cartes, des
wallets et des recharges de test (Fedow n'a pas d'API de suppression). Cote Lespass, tout
est annule par le rollback de `django_db` : on ne supprime RIEN a la main (piege 13.24).
/ Each run leaves test cards, wallets and refills on the dev Fedow (no delete API).

PREREQUIS : Fedow de dev joignable (conteneur fedow_django) ; le tenant 'lespass' a une
monnaie locale fiduciaire chez Fedow (AssetFedowPublic categorie TLF) ; un autre lieu
existe en base (pour le test « admin d'un autre lieu »).

Lancement / Run :
    docker exec lespass_django poetry run pytest tests/pytest/test_carte_perdue_cycle_complet.py -v
"""
import logging
import secrets
import uuid as uuid_module

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages import constants as niveaux_de_message
from django.test import Client as DjangoClient
from django.test import override_settings
from django_tenants.utils import tenant_context


pytestmark = [pytest.mark.django_db, pytest.mark.integration]

HOTE_DU_LIEU = "lespass.tibillet.localhost"
REFERER_DE_L_ADMIN = f"https://{HOTE_DU_LIEU}/admin/"
CREDIT_FEDOW_CENTIMES = 2000
CREDIT_LOCAL_V2_CENTIMES = 1500

# override_settings(DEBUG=True) autour de chaque appel Fedow : pytest-django force
# DEBUG=False, ce qui active la verification SSL de fedow_api ; le certificat Traefik de
# dev est auto-signe.
# / override_settings(DEBUG=True) around each Fedow call: the dev certificate is self-signed.


# ---------------------------------------------------------------------------
# Fabriques / Factories
# ---------------------------------------------------------------------------


@pytest.fixture
def detail_des_cartes(tenant):
    """La generation de cartes a laquelle rattacher les cartes de test. / Card batch."""
    from QrcodeCashless.models import Detail

    with tenant_context(tenant):
        detail, _detail_cree = Detail.objects.get_or_create(
            slug="test-carte-perdue-cycle-complet",
            defaults={"base_url": "test-carte-perdue.localhost", "generation": 1, "origine": tenant},
        )
    return detail


@pytest.fixture
def navigateur_admin_du_lieu(admin_user):
    """
    Un client neuf, connecte comme admin du lieu, pour CE test (piege 13.10 : un
    `force_login` par test, jamais un client de session partage).
    / A fresh client logged in as venue admin, for THIS test only.
    """
    navigateur = DjangoClient(HTTP_HOST=HOTE_DU_LIEU, raise_request_exception=False)
    navigateur.force_login(admin_user)
    return navigateur


def _carte_connue_de_fedow_et_de_lespass(tenant, detail):
    """
    Une carte vierge, connue des DEUX registres avec les memes identifiants :
    chez Fedow (create_cards) et dans Lespass (CarteCashless). Le numero commence par
    « AB » : 8 caracteres hexadecimaux, toujours avec des lettres.
    / A blank card known to BOTH registries with the same identifiers.
    """
    from QrcodeCashless.models import CarteCashless
    from fedow_connect.fedow_api import FedowAPI

    numero_imprime = "AB" + secrets.token_hex(3).upper()
    tag_rfid = secrets.token_hex(4).upper()
    qrcode_uuid = uuid_module.uuid4()

    with override_settings(DEBUG=True), tenant_context(tenant):
        FedowAPI().NFCcard.create_cards([{
            "first_tag_id": tag_rfid,
            "complete_tag_id_uuid": str(uuid_module.uuid4()),
            "qrcode_uuid": str(qrcode_uuid),
            "number_printed": numero_imprime,
            "generation": 1,
            "is_primary": False,
        }])
        carte = CarteCashless.objects.create(
            tag_id=tag_rfid, number=numero_imprime, uuid=qrcode_uuid, detail=detail,
        )
    return carte


def _adherent_avec_wallet_fedow(tenant, prefixe):
    """Un usager actif, email valide, avec son wallet declare chez Fedow. / Member + wallet."""
    from AuthBillet.utils import get_or_create_user
    from fedow_connect.fedow_api import FedowAPI

    email = f"jturbeaux+{prefixe}{uuid_module.uuid4().hex[:8]}@pm.me"
    with override_settings(DEBUG=True), tenant_context(tenant):
        utilisateur = get_or_create_user(email, send_mail=False)
        utilisateur.is_active = True
        utilisateur.email_valid = True
        utilisateur.save()
        FedowAPI().wallet.get_or_create_wallet(utilisateur)
        utilisateur.refresh_from_db()
    return utilisateur


def _lier_la_carte_comme_le_parcours_qr(tenant, utilisateur, carte):
    """
    Lie la carte au porteur comme ScanQrCode.link : chez Fedow, puis dans Lespass.
    Leve l'exception de Lespass si la liaison locale est refusee (ex. UserADejaCarte).
    / Links the card like ScanQrCode.link: Fedow, then Lespass.
    """
    from fedow_connect.fedow_api import FedowAPI
    from fedow_core.services import CarteService

    with override_settings(DEBUG=True), tenant_context(tenant):
        carte_liee_chez_fedow = FedowAPI().NFCcard.linkwallet_cardqrcode(
            user=utilisateur, qrcode_uuid=carte.uuid,
        )
        assert carte_liee_chez_fedow, f"Fedow a refuse de lier la carte {carte.number}."
        CarteService.lier_a_user(qrcode_uuid=carte.uuid, user=utilisateur)


def _carte_liee_et_son_porteur(tenant, detail, prefixe="droits"):
    """Un porteur et sa carte, lies des deux cotes. / A holder and his card, linked both sides."""
    utilisateur = _adherent_avec_wallet_fedow(tenant, prefixe)
    carte = _carte_connue_de_fedow_et_de_lespass(tenant, detail)
    _lier_la_carte_comme_le_parcours_qr(tenant, utilisateur, carte)
    return utilisateur, carte


def _crediter_chez_fedow_en_monnaie_locale(tenant, utilisateur, montant_centimes):
    """
    Credite le wallet du porteur chez Fedow, dans la monnaie locale fiduciaire du lieu.
    Meme contrat que l'API v2 de recharge : Fedow exige `ligne_article_uuid`.
    / Credits the holder's Fedow wallet in the venue's local fiat currency.
    """
    from BaseBillet.models import (
        LigneArticle, PaymentMethod, Price, PriceSold, Product, ProductSold, SaleOrigin,
    )
    from fedow_connect.fedow_api import FedowAPI
    from fedow_public.models import AssetFedowPublic

    with override_settings(DEBUG=True), tenant_context(tenant):
        monnaie_locale = AssetFedowPublic.objects.filter(
            origin=tenant, category=AssetFedowPublic.TOKEN_LOCAL_FIAT,
        ).first()
        assert monnaie_locale, (
            "Aucune monnaie locale fiduciaire chez Fedow pour ce lieu : le test ne peut "
            "pas crediter le portefeuille. Un tenant sans monnaie doit rendre le test ROUGE."
        )
        produit, _cree = Product.objects.get_or_create(
            name="Test recharge carte perdue", categorie_article=Product.RECHARGE_CASHLESS,
        )
        tarif, _cree = Price.objects.get_or_create(product=produit, name="Test", prix=0)
        produit_vendu, _cree = ProductSold.objects.get_or_create(product=produit)
        tarif_vendu, _cree = PriceSold.objects.get_or_create(
            productsold=produit_vendu, price=tarif, defaults={"prix": 0},
        )
        ligne = LigneArticle.objects.create(
            pricesold=tarif_vendu, qty=1, amount=montant_centimes,
            payment_method=PaymentMethod.FREE, status=LigneArticle.VALID,
            sale_origin=SaleOrigin.API, asset=monnaie_locale.uuid,
        )
        FedowAPI().transaction.refill_from_lespass_to_user_wallet(
            user=utilisateur, amount=montant_centimes, asset=monnaie_locale,
            metadata={
                "reason": "Test carte perdue cycle complet",
                "ligne_article_uuid": str(ligne.uuid),
                "rewarded_from_ticket_scanned": True,
            },
        )


def _crediter_en_jetons_locaux_v2(tenant, utilisateur, montant_centimes):
    """
    Pose des jetons du moteur local V2 (fedow_core) sur le wallet du porteur.
    / Puts local V2 engine tokens on the holder's wallet.
    """
    from AuthBillet.models import Wallet
    from fedow_core.models import Asset, Token

    with tenant_context(tenant):
        wallet_du_lieu = Wallet.objects.create(origin=tenant, name="Test carte perdue lieu")
        monnaie_v2 = Asset.objects.create(
            name=f"TLF carte perdue {uuid_module.uuid4().hex[:6]}",
            currency_code="EUR",
            category=Asset.TLF,
            wallet_origin=wallet_du_lieu,
            tenant_origin=tenant,
        )
        Token.objects.create(wallet=utilisateur.wallet, asset=monnaie_v2, value=montant_centimes)
    return monnaie_v2


def _solde_chez_fedow(tenant, utilisateur):
    """Le solde total du porteur chez Fedow, sans cache. / Holder's Fedow balance, no cache."""
    from fedow_connect.fedow_api import FedowAPI

    with override_settings(DEBUG=True), tenant_context(tenant):
        return FedowAPI().wallet.get_total_fiducial_and_all_federated_token(utilisateur, use_cache=False)


def _carte_chez_fedow(tenant, carte):
    """Ce que Fedow sait de la carte (wallet_uuid, is_wallet_ephemere). / Fedow's view."""
    from fedow_connect.fedow_api import FedowAPI

    with override_settings(DEBUG=True), tenant_context(tenant):
        return FedowAPI().NFCcard.card_number_retrieve(carte.number)


def _wallet_ouvert_par_la_caisse_v2(tenant, carte):
    """Le wallet que la caisse V2 ouvre quand on scanne cette carte. / Wallet the V2 POS opens."""
    from laboutik.views import _obtenir_ou_creer_wallet

    with override_settings(DEBUG=True), tenant_context(tenant):
        carte.refresh_from_db()
        return _obtenir_ou_creer_wallet(carte)


def _niveaux_des_messages(reponse):
    """Les niveaux des messages poses par la vue (SUCCESS, INFO, ERROR...). / Message levels."""
    return [message.level for message in get_messages(reponse.wsgi_request)]


def _verifier_la_reponse_du_bouton(reponse, niveau_attendu):
    """
    Le bouton « carte perdue » repond 200 + en-tete HX-Redirect, avec UN message du niveau
    attendu. Le statut seul ne prouve rien : la vue repond aussi 200 quand elle echoue.
    / The button answers 200 + HX-Redirect with ONE message of the expected level.
    """
    assert reponse.status_code == 200, f"statut inattendu : {reponse.status_code}"
    assert reponse.headers.get("HX-Redirect"), "La vue n'a pas renvoye d'en-tete HX-Redirect."
    assert _niveaux_des_messages(reponse) == [niveau_attendu], (
        f"Messages poses : {_niveaux_des_messages(reponse)}, attendu [{niveau_attendu}]."
    )


# ---------------------------------------------------------------------------
# Les trois facons de declarer la carte perdue
# / The three ways to report the card lost
# ---------------------------------------------------------------------------


def _perte_declaree_dans_mon_compte(tenant, utilisateur, carte, admin_user):
    """L'usager clique « carte perdue » dans /my_account/. / Holder reports it."""
    navigateur = DjangoClient(HTTP_HOST=HOTE_DU_LIEU)
    navigateur.force_login(utilisateur)
    with override_settings(DEBUG=True):
        reponse = navigateur.get(f"/my_account/{carte.number}/lost_my_card/")
    _verifier_la_reponse_du_bouton(reponse, niveaux_de_message.SUCCESS)


def _perte_declaree_par_un_admin(tenant, utilisateur, carte, admin_user):
    """Un admin du lieu clique « carte perdue » sur la fiche. / Venue admin reports it."""
    navigateur = DjangoClient(HTTP_HOST=HOTE_DU_LIEU)
    navigateur.force_login(admin_user)
    with override_settings(DEBUG=True):
        reponse = navigateur.get(
            f"/my_account/{utilisateur.pk}:{carte.number}/admin_lost_my_card/",
            HTTP_REFERER=REFERER_DE_L_ADMIN,
        )
    _verifier_la_reponse_du_bouton(reponse, niveaux_de_message.SUCCESS)


def _perte_declaree_par_un_autre_client_fedow(tenant, utilisateur, carte, admin_user):
    """
    La carte est detachee chez Fedow sans passer par Lespass (autre client Fedow).
    / The card is detached on Fedow without going through Lespass.
    """
    from fedow_connect.fedow_api import FedowAPI

    with override_settings(DEBUG=True), tenant_context(tenant):
        FedowAPI().NFCcard.lost_my_card_by_signature(utilisateur, number_printed=carte.number)


FACONS_DE_DECLARER_LA_PERTE = {
    "mon_compte": _perte_declaree_dans_mon_compte,
    "admin": _perte_declaree_par_un_admin,
    "autre_client_fedow": _perte_declaree_par_un_autre_client_fedow,
}


# ---------------------------------------------------------------------------
# Le cycle complet / The full cycle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("facon_de_declarer", [
    "mon_compte",
    "admin",
    pytest.param(
        "autre_client_fedow",
        marks=pytest.mark.xfail(
            strict=True,
            raises=AssertionError,
            reason=(
                "Trou connu : une carte detachee chez Fedow sans passer par Lespass reste "
                "liee dans CarteCashless.user. Piste de fond a choisir (verification Fedow "
                "au scan en caisse V2, webhook Fedow, ou reconciliation)."
            ),
        ),
    ),
])
def test_carte_perdue_puis_nouvelle_carte_le_solde_suit_le_porteur(
    tenant, detail_des_cartes, admin_user, facon_de_declarer,
):
    """
    Carte A liee et creditee, declaree perdue, carte B liee : A n'ouvre plus rien, B ouvre
    le portefeuille du porteur, et ses soldes (Fedow et local V2) sont intacts.
    / Card A linked and credited, reported lost, card B linked: A opens nothing, B opens the
    holder's wallet, balances intact.
    """
    from fedow_core.models import Token
    from QrcodeCashless.models import CarteCashless

    # --- 1. Un adherent lie la carte A / A member links card A ---
    utilisateur = _adherent_avec_wallet_fedow(tenant, f"perdue{facon_de_declarer[:6]}")
    carte_a = _carte_connue_de_fedow_et_de_lespass(tenant, detail_des_cartes)
    _lier_la_carte_comme_le_parcours_qr(tenant, utilisateur, carte_a)

    # --- 2. Son portefeuille est credite / The wallet is credited ---
    solde_fedow_avant_credit = _solde_chez_fedow(tenant, utilisateur)
    _crediter_chez_fedow_en_monnaie_locale(tenant, utilisateur, CREDIT_FEDOW_CENTIMES)
    monnaie_v2 = _crediter_en_jetons_locaux_v2(tenant, utilisateur, CREDIT_LOCAL_V2_CENTIMES)
    solde_fedow_avant_perte = _solde_chez_fedow(tenant, utilisateur)
    assert solde_fedow_avant_perte == solde_fedow_avant_credit + CREDIT_FEDOW_CENTIMES

    # Avant la perte, la caisse V2 ouvre bien son portefeuille avec la carte A.
    # / Before the loss, the V2 POS opens the holder's wallet with card A.
    assert _wallet_ouvert_par_la_caisse_v2(tenant, carte_a).uuid == utilisateur.wallet.uuid

    # --- 3. La carte A est declaree perdue / Card A is reported lost ---
    FACONS_DE_DECLARER_LA_PERTE[facon_de_declarer](tenant, utilisateur, carte_a, admin_user)

    # --- 4. A est anonyme chez Fedow ET dans Lespass / A is anonymous on both sides ---
    carte_a_chez_fedow = _carte_chez_fedow(tenant, carte_a)
    assert carte_a_chez_fedow.get("is_wallet_ephemere") is True, (
        f"Fedow rattache encore la carte perdue {carte_a.number} au porteur."
    )
    with tenant_context(tenant):
        carte_a.refresh_from_db()
        assert carte_a.user_id is None, (
            f"[{facon_de_declarer}] La carte perdue {carte_a.number} est detachee chez Fedow "
            "mais TOUJOURS liee au porteur dans Lespass : la caisse V2 ouvrira encore son "
            "portefeuille."
        )

    # La caisse V2 n'ouvre plus le portefeuille du porteur avec la carte perdue.
    # / The V2 POS no longer opens the holder's wallet with the lost card.
    wallet_ouvert_par_a = _wallet_ouvert_par_la_caisse_v2(tenant, carte_a)
    assert wallet_ouvert_par_a.uuid != utilisateur.wallet.uuid, (
        f"[{facon_de_declarer}] Qui trouve la carte perdue depense le portefeuille du porteur."
    )

    # --- 5. Il lie une carte B / The holder links card B ---
    carte_b = _carte_connue_de_fedow_et_de_lespass(tenant, detail_des_cartes)
    try:
        _lier_la_carte_comme_le_parcours_qr(tenant, utilisateur, carte_b)
    except Exception as erreur_liaison:
        pytest.fail(
            f"[{facon_de_declarer}] Impossible de lier la nouvelle carte {carte_b.number} : "
            f"{type(erreur_liaison).__name__} {erreur_liaison}"
        )

    # B est a lui, des deux cotes, et la caisse V2 ouvre son portefeuille.
    # / B is his on both sides, and the V2 POS opens his wallet.
    carte_b_chez_fedow = _carte_chez_fedow(tenant, carte_b)
    assert f"{carte_b_chez_fedow.get('wallet_uuid')}" == f"{utilisateur.wallet.uuid}"
    with tenant_context(tenant):
        assert CarteCashless.objects.get(pk=carte_b.pk).user_id == utilisateur.pk
    assert _wallet_ouvert_par_la_caisse_v2(tenant, carte_b).uuid == utilisateur.wallet.uuid

    # Les soldes sont intacts / Balances are intact.
    assert _solde_chez_fedow(tenant, utilisateur) == solde_fedow_avant_perte, (
        f"[{facon_de_declarer}] Le solde chez Fedow a change avec la perte de la carte."
    )
    with tenant_context(tenant):
        jetons_v2 = Token.objects.get(wallet=utilisateur.wallet, asset=monnaie_v2)
        assert jetons_v2.value == CREDIT_LOCAL_V2_CENTIMES, (
            f"[{facon_de_declarer}] Les jetons locaux V2 ont change avec la perte de la carte."
        )


# ---------------------------------------------------------------------------
# Les cas limites de la declaration / Edge cases
# ---------------------------------------------------------------------------


def test_double_clic_le_second_ne_signale_pas_d_erreur(
    tenant, detail_des_cartes, navigateur_admin_du_lieu, admin_user, caplog,
):
    """
    Deux clics sur « carte perdue » : le premier detache, le second trouve la carte deja
    detachee chez Fedow (404). Le second affiche une INFO, sans erreur journalisee (pas
    d'alerte Sentry), et la carte reste detachee.
    / Double click: the second one finds the card already detached (404): INFO, no error log.
    """
    utilisateur, carte = _carte_liee_et_son_porteur(tenant, detail_des_cartes, "double")
    adresse = f"/my_account/{utilisateur.pk}:{carte.number}/admin_lost_my_card/"

    with override_settings(DEBUG=True):
        premier_clic = navigateur_admin_du_lieu.get(adresse, HTTP_REFERER=REFERER_DE_L_ADMIN)
    _verifier_la_reponse_du_bouton(premier_clic, niveaux_de_message.SUCCESS)

    # Second clic avec un client neuf : le client de test ne suit pas HX-Redirect, donc le
    # message du premier clic resterait en session (un vrai navigateur l'aurait affiche).
    # / Fresh client: the test client does not follow HX-Redirect, the first message would linger.
    second_navigateur = DjangoClient(HTTP_HOST=HOTE_DU_LIEU, raise_request_exception=False)
    second_navigateur.force_login(admin_user)
    with caplog.at_level(logging.WARNING), override_settings(DEBUG=True):
        second_clic = second_navigateur.get(adresse, HTTP_REFERER=REFERER_DE_L_ADMIN)
    _verifier_la_reponse_du_bouton(second_clic, niveaux_de_message.INFO)

    erreurs_journalisees = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not erreurs_journalisees, (
        f"Un double clic ne doit pas lever d'alerte : {[r.getMessage() for r in erreurs_journalisees]}"
    )
    with tenant_context(tenant):
        carte.refresh_from_db()
        assert carte.user_id is None


def test_le_bouton_repare_une_carte_deja_detachee_chez_fedow(
    tenant, detail_des_cartes, navigateur_admin_du_lieu,
):
    """
    La carte a ete detachee chez Fedow sans passer par Lespass (autre client Fedow) : elle
    reste liee dans Lespass. Le bouton « carte perdue » de l'admin doit aligner Lespass sur
    Fedow (Fedow repond 404 « plus a ce porteur ») : la carte est detachee en local, et le
    porteur peut lier une nouvelle carte.
    / The admin button repairs a card already detached on Fedow by another client.
    """
    from fedow_connect.fedow_api import FedowAPI

    utilisateur, carte_a = _carte_liee_et_son_porteur(tenant, detail_des_cartes, "repare")
    with override_settings(DEBUG=True), tenant_context(tenant):
        FedowAPI().NFCcard.lost_my_card_by_signature(utilisateur, number_printed=carte_a.number)
        carte_a.refresh_from_db()
        assert carte_a.user_id == utilisateur.pk, "Precondition : la carte est encore liee en local."

    with override_settings(DEBUG=True):
        reponse = navigateur_admin_du_lieu.get(
            f"/my_account/{utilisateur.pk}:{carte_a.number}/admin_lost_my_card/",
            HTTP_REFERER=REFERER_DE_L_ADMIN,
        )
    _verifier_la_reponse_du_bouton(reponse, niveaux_de_message.INFO)

    with tenant_context(tenant):
        carte_a.refresh_from_db()
        assert carte_a.user_id is None, "Le bouton n'a pas aligne Lespass sur Fedow."

    carte_b = _carte_connue_de_fedow_et_de_lespass(tenant, detail_des_cartes)
    _lier_la_carte_comme_le_parcours_qr(tenant, utilisateur, carte_b)


def test_carte_liee_localement_a_un_autre_usager_reste_a_lui_et_alerte(
    tenant, detail_des_cartes, caplog,
):
    """
    Divergence : Fedow dit que la carte est au porteur, Lespass dit qu'elle est a quelqu'un
    d'autre. La perte declaree par le porteur ne doit PAS detacher la carte de l'autre
    personne, et doit lever une alerte (logger.error), a traiter a la main.
    / Lespass links the card to someone else: do not touch it, raise an error log.
    """
    utilisateur, carte = _carte_liee_et_son_porteur(tenant, detail_des_cartes, "divergence")
    autre_usager = _adherent_avec_wallet_fedow(tenant, "autre")
    with tenant_context(tenant):
        carte.user = autre_usager
        carte.save(update_fields=["user"])

    navigateur = DjangoClient(HTTP_HOST=HOTE_DU_LIEU)
    navigateur.force_login(utilisateur)
    with caplog.at_level(logging.WARNING), override_settings(DEBUG=True):
        reponse = navigateur.get(f"/my_account/{carte.number}/lost_my_card/")
    _verifier_la_reponse_du_bouton(reponse, niveaux_de_message.SUCCESS)

    with tenant_context(tenant):
        carte.refresh_from_db()
        assert carte.user_id == autre_usager.pk, "La carte de l'autre usager a ete detachee."
    alertes = [
        r for r in caplog.records
        if r.levelno >= logging.ERROR and "AUTRE usager" in r.getMessage()
    ]
    assert alertes, "La divergence Fedow/Lespass doit lever une alerte (logger.error)."


def test_une_carte_primaire_de_caissier_perdue_n_ouvre_plus_la_caisse(
    tenant, detail_des_cartes, navigateur_admin_du_lieu,
):
    """
    Une carte de caissier (laboutik.CartePrimaire) declaree perdue est retiree des cartes
    primaires : elle ne doit plus ouvrir la caisse du lieu.
    / A lost cashier card is removed from the primary cards: it no longer opens the POS.
    """
    from laboutik.models import CartePrimaire

    utilisateur, carte = _carte_liee_et_son_porteur(tenant, detail_des_cartes, "caissier")
    with tenant_context(tenant):
        CartePrimaire.objects.create(carte=carte)

    with override_settings(DEBUG=True):
        reponse = navigateur_admin_du_lieu.get(
            f"/my_account/{utilisateur.pk}:{carte.number}/admin_lost_my_card/",
            HTTP_REFERER=REFERER_DE_L_ADMIN,
        )
    _verifier_la_reponse_du_bouton(reponse, niveaux_de_message.SUCCESS)

    with tenant_context(tenant):
        assert not CartePrimaire.objects.filter(carte=carte).exists(), (
            "La carte de caissier perdue ouvre encore la caisse du lieu."
        )


# ---------------------------------------------------------------------------
# admin_lost_my_card : qui a le droit / who is allowed
# ---------------------------------------------------------------------------


def test_un_superuser_peut_declarer_une_carte_perdue_depuis_l_admin(tenant, detail_des_cartes):
    """
    L'admin s'ouvre aux superusers (TenantAdminPermissionWithRequest) et leur montre le
    bouton « carte perdue ». Le bouton doit donc fonctionner pour eux : pas d'erreur 500,
    carte detachee des deux cotes.
    / Superusers see the admin and the button: it must work for them.
    """
    from AuthBillet.models import TibilletUser

    utilisateur, carte = _carte_liee_et_son_porteur(tenant, detail_des_cartes)
    with tenant_context(tenant):
        superuser = TibilletUser.objects.create(
            email=f"jturbeaux+super{uuid_module.uuid4().hex[:8]}@pm.me",
            username=f"super{uuid_module.uuid4().hex[:8]}",
            espece=TibilletUser.TYPE_HUM,
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )

    navigateur = DjangoClient(HTTP_HOST=HOTE_DU_LIEU, raise_request_exception=False)
    navigateur.force_login(superuser)
    with override_settings(DEBUG=True):
        reponse = navigateur.get(
            f"/my_account/{utilisateur.pk}:{carte.number}/admin_lost_my_card/",
            HTTP_REFERER=REFERER_DE_L_ADMIN,
        )

    _verifier_la_reponse_du_bouton(reponse, niveaux_de_message.SUCCESS)
    assert _carte_chez_fedow(tenant, carte).get("is_wallet_ephemere") is True
    with tenant_context(tenant):
        carte.refresh_from_db()
        assert carte.user_id is None


def test_un_usager_non_admin_ne_peut_pas_declarer_la_carte_d_un_autre(tenant, detail_des_cartes):
    """
    Un usager connecte, sans droit d'admin sur le lieu, appelle l'URL admin : refus propre
    (403), aucune erreur 500, et la carte reste liee des deux cotes.
    / A non-admin gets a clean 403, no 500, and the card stays linked on both sides.
    """
    utilisateur, carte = _carte_liee_et_son_porteur(tenant, detail_des_cartes)
    intrus = _adherent_avec_wallet_fedow(tenant, "intrus")

    navigateur = DjangoClient(HTTP_HOST=HOTE_DU_LIEU, raise_request_exception=False)
    navigateur.force_login(intrus)
    with override_settings(DEBUG=True):
        reponse = navigateur.get(
            f"/my_account/{utilisateur.pk}:{carte.number}/admin_lost_my_card/",
            HTTP_REFERER=REFERER_DE_L_ADMIN,
        )

    assert reponse.status_code == 403, (
        f"Un usager non admin obtient {reponse.status_code} au lieu d'un refus 403."
    )
    assert f"{_carte_chez_fedow(tenant, carte).get('wallet_uuid')}" == f"{utilisateur.wallet.uuid}", (
        "Un usager non admin a detache chez Fedow la carte d'un autre."
    )
    with tenant_context(tenant):
        carte.refresh_from_db()
        assert carte.user_id == utilisateur.pk


def test_un_admin_d_un_autre_lieu_ne_peut_pas_declarer_la_carte(tenant, detail_des_cartes):
    """
    Un admin d'un AUTRE lieu (pas superuser) appelle l'URL admin de ce lieu : refus 403,
    et la carte reste liee des deux cotes.
    / An admin of ANOTHER venue gets a 403 here, and the card stays linked.
    """
    from AuthBillet.models import TibilletUser
    from Customers.models import Client

    autre_lieu = Client.objects.exclude(schema_name__in=["public", tenant.schema_name]).exclude(
        categorie=Client.WAITING_CONFIG,
    ).exclude(schema_name__startswith="test").first()
    assert autre_lieu, "Il faut un second lieu en base de dev pour ce test."

    utilisateur, carte = _carte_liee_et_son_porteur(tenant, detail_des_cartes)
    with tenant_context(tenant):
        admin_d_ailleurs = TibilletUser.objects.create(
            email=f"jturbeaux+ailleurs{uuid_module.uuid4().hex[:8]}@pm.me",
            username=f"ailleurs{uuid_module.uuid4().hex[:8]}",
            espece=TibilletUser.TYPE_HUM,
            is_active=True,
            is_staff=True,
        )
        admin_d_ailleurs.client_admin.add(autre_lieu)

    navigateur = DjangoClient(HTTP_HOST=HOTE_DU_LIEU, raise_request_exception=False)
    navigateur.force_login(admin_d_ailleurs)
    with override_settings(DEBUG=True):
        reponse = navigateur.get(
            f"/my_account/{utilisateur.pk}:{carte.number}/admin_lost_my_card/",
            HTTP_REFERER=REFERER_DE_L_ADMIN,
        )

    assert reponse.status_code == 403, (
        f"Un admin d'un autre lieu obtient {reponse.status_code} au lieu d'un refus 403."
    )
    with tenant_context(tenant):
        carte.refresh_from_db()
        assert carte.user_id == utilisateur.pk


def test_admin_lost_my_card_avec_un_identifiant_mal_forme_repond_400(navigateur_admin_du_lieu):
    """
    L'URL attend « <uuid du porteur>:<numero de carte> ». Une valeur mal formee donne
    exactement 400, jamais une erreur 500 (et pas un 403 qui masquerait une perte de droits).
    / A malformed identifier gives exactly 400.
    """
    # Trois formes : pas de « : », pas d'uuid, un uuid valide sans numero de carte.
    # / Three shapes: no colon, no uuid, a valid uuid without a card number.
    identifiants_mal_formes = [
        "sans-deux-points",
        "pas-un-uuid:ABCDEF12",
        f"{uuid_module.uuid4()}",
    ]
    for identifiant_mal_forme in identifiants_mal_formes:
        with override_settings(DEBUG=True):
            reponse = navigateur_admin_du_lieu.get(
                f"/my_account/{identifiant_mal_forme}/admin_lost_my_card/",
                HTTP_REFERER=REFERER_DE_L_ADMIN,
            )
        assert reponse.status_code == 400, (
            f"« {identifiant_mal_forme} » donne {reponse.status_code} au lieu de 400."
        )


def test_admin_lost_my_card_avec_un_usager_inconnu_repond_404(navigateur_admin_du_lieu):
    """Un uuid bien forme mais inconnu donne 404. / A well-formed but unknown uuid gives 404."""
    with override_settings(DEBUG=True):
        reponse = navigateur_admin_du_lieu.get(
            f"/my_account/{uuid_module.uuid4()}:ABCDEF12/admin_lost_my_card/",
            HTTP_REFERER=REFERER_DE_L_ADMIN,
        )
    assert reponse.status_code == 404, f"Usager inconnu : {reponse.status_code} au lieu de 404."
