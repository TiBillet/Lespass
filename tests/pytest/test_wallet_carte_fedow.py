"""
Tests — résolution du wallet d'une carte NFC DEPUIS Fedow (source de vérité).
/ Tests — resolving a NFC card's wallet FROM Fedow (source of truth).

LOCALISATION : tests/pytest/test_wallet_carte_fedow.py

CE QUI EST TESTÉ / WHAT IS TESTED :
Depuis l'intégration Fedow, le wallet d'une carte n'est plus fabriqué localement à
uuid aléatoire : il est DEMANDÉ à Fedow (qui fait foi) puis MIROIR en local avec le
MÊME uuid. C'est la seule façon d'avoir un wallet capable de recevoir du FED.
On teste les deux fonctions de laboutik/views.py :
  - `obtenir_wallet_carte_depuis_fedow(carte)` : appelle Fedow, miroir local, rattache
    le wallet éphémère à une carte anonyme ;
  - `_obtenir_ou_creer_wallet(carte)` : priorité user.wallet > wallet_ephemere > Fedow,
    et LÈVE une Exception si Fedow ne connaît pas la carte (dépendance assumée, pas de
    fallback local).
/ Since the Fedow integration, a card's wallet is no longer locally built with a random
uuid: it is REQUESTED from Fedow (source of truth) then MIRRORED locally with the SAME
uuid — the only way to hold FED. We test both functions in laboutik/views.py.

Fedow est MOCKÉ (pas de réseau) : on patche `laboutik.views.FedowAPI`. Les wallets
locaux viennent de la vraie base AuthBillet (DB dev partagée — pas de rollback, donc
get_or_create + nettoyage explicite).
/ Fedow is MOCKED (no network): we patch `laboutik.views.FedowAPI`. Local wallets come
from the real AuthBillet DB (shared dev DB — no rollback, hence explicit cleanup).
"""

import uuid as uuidlib
from unittest import mock

import pytest
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db


def _suffix():
    """Suffixe court unique pour éviter les collisions de noms / tag_id.
    / Short unique suffix to avoid name / tag_id collisions."""
    return uuidlib.uuid4().hex[:6]


def _tag():
    """tag_id de carte de test : 8 caractères max (piège 9.31).
    / Test card tag_id: 8 chars max (pitfall 9.31)."""
    return f"WF{_suffix().upper()}"  # "WF" + 6 = 8 caractères


@pytest.fixture
def carte_anonyme(tenant):
    """Une CarteCashless anonyme (sans user). Nettoyée en fin de test, y compris le
    wallet éphémère que la résolution Fedow peut créer.
    / An anonymous CarteCashless (no user). Cleaned afterwards, including the ephemeral
    wallet the Fedow resolution may create.
    """
    from QrcodeCashless.models import CarteCashless

    with tenant_context(tenant):
        tag = _tag()
        carte = CarteCashless.objects.create(tag_id=tag, number=tag)

    yield {"tenant": tenant, "carte": carte}

    with tenant_context(tenant):
        from AuthBillet.models import Wallet
        from fedow_core.models import Token

        carte.refresh_from_db()
        wallet_eph = carte.wallet_ephemere
        carte.wallet_ephemere = None
        carte.save(update_fields=["wallet_ephemere"])
        carte.delete()
        if wallet_eph is not None:
            Token.objects.filter(wallet=wallet_eph).delete()
            try:
                wallet_eph.delete()
            except Exception:
                pass


@pytest.fixture
def carte_liee(tenant):
    """Une CarteCashless liée à un user qui a déjà un wallet local.
    Nettoyée en fin de test (DB dev partagée, pas de rollback).
    / A CarteCashless linked to a user who already has a local wallet. Cleaned afterwards.
    """
    from AuthBillet.models import Wallet
    from AuthBillet.utils import get_or_create_user
    from QrcodeCashless.models import CarteCashless

    with tenant_context(tenant):
        user = get_or_create_user(f"wf-lie-{_suffix()}@tibillet.test", send_mail=False)
        # On garantit un wallet local pour le user (sinon _obtenir_ou_creer_wallet
        # passerait à l'étape Fedow).
        # / Ensure a local wallet for the user (otherwise step 3 would hit Fedow).
        if not user.wallet:
            user.wallet = Wallet.objects.create(
                origin=tenant, name=f"WF wallet {_suffix()}"
            )
            user.save()
        tag = _tag()
        carte = CarteCashless.objects.create(tag_id=tag, number=tag, user=user)

    yield {"tenant": tenant, "user": user, "wallet": user.wallet, "carte": carte}

    with tenant_context(tenant):
        from fedow_core.models import Token

        Token.objects.filter(wallet=user.wallet).delete()
        carte.delete()
        try:
            user.wallet.delete()
        except Exception:
            pass  # un objet lié peut protéger le wallet — best effort
        try:
            user.delete()
        except Exception:
            pass


def test_carte_connue_de_fedow_miroir_meme_uuid_et_rattache_ephemere(carte_anonyme):
    """Carte connue de Fedow (wallet éphémère) : `obtenir_wallet_carte_depuis_fedow`
    crée un Wallet local AVEC LE MÊME uuid que Fedow et rattache `carte.wallet_ephemere`.
    / Card known to Fedow (ephemeral wallet): `obtenir_wallet_carte_depuis_fedow` creates
    a local Wallet WITH THE SAME uuid as Fedow and attaches `carte.wallet_ephemere`.
    """
    from laboutik.views import obtenir_wallet_carte_depuis_fedow

    wallet_uuid_fedow = uuidlib.uuid4()

    with mock.patch("laboutik.views.FedowAPI") as MockAPI:
        retrieve = MockAPI.return_value.NFCcard.card_tag_id_retrieve
        retrieve.return_value = {
            "wallet_uuid": str(wallet_uuid_fedow),
            "is_wallet_ephemere": True,
            "origin": {},
        }

        with tenant_context(carte_anonyme["tenant"]):
            wallet = obtenir_wallet_carte_depuis_fedow(carte_anonyme["carte"])

    # Fedow a bien été interrogé avec le tag_id physique de la carte.
    # / Fedow was queried with the card's physical tag_id.
    retrieve.assert_called_once_with(carte_anonyme["carte"].tag_id)

    # Le wallet local a le MÊME uuid que Fedow (Fedow fait foi).
    # Comparaison en str : get_or_create peut renvoyer l'uuid en str (valeur posée)
    # ou en UUID (recharge depuis la base) — str() normalise les deux.
    # / The local wallet has the SAME uuid as Fedow. Compare as str: get_or_create may
    # return the uuid as str (set value) or UUID (reloaded) — str() normalizes both.
    assert wallet is not None
    assert str(wallet.uuid) == str(wallet_uuid_fedow)

    # Le wallet éphémère est rattaché à la carte anonyme pour les prochains scans.
    # / The ephemeral wallet is attached to the anonymous card for next scans.
    with tenant_context(carte_anonyme["tenant"]):
        carte_anonyme["carte"].refresh_from_db()
        assert carte_anonyme["carte"].wallet_ephemere is not None
        assert str(carte_anonyme["carte"].wallet_ephemere.uuid) == str(wallet_uuid_fedow)


def test_carte_avec_user_retourne_wallet_user_sans_appeler_fedow(carte_liee):
    """Carte liée à un user qui a déjà un wallet : `_obtenir_ou_creer_wallet` retourne
    `user.wallet` à l'étape 1, SANS jamais instancier FedowAPI.
    / Card linked to a user with an existing wallet: `_obtenir_ou_creer_wallet` returns
    `user.wallet` at step 1, WITHOUT ever instantiating FedowAPI.
    """
    from laboutik.views import _obtenir_ou_creer_wallet

    with mock.patch("laboutik.views.FedowAPI") as MockAPI:
        with tenant_context(carte_liee["tenant"]):
            wallet = _obtenir_ou_creer_wallet(carte_liee["carte"])

    # On récupère bien le wallet du user, et Fedow n'a PAS été sollicité (étape 1).
    # / We get the user's wallet, and Fedow was NOT contacted (step 1).
    assert wallet == carte_liee["wallet"]
    MockAPI.assert_not_called()


def test_carte_inconnue_de_fedow_leve_exception(carte_anonyme):
    """Carte inconnue de Fedow (`card_tag_id_retrieve` → None) : `_obtenir_ou_creer_wallet`
    LÈVE une Exception (Fedow indispensable, pas de fallback local à uuid aléatoire).
    / Card unknown to Fedow (`card_tag_id_retrieve` → None): `_obtenir_ou_creer_wallet`
    RAISES an Exception (Fedow is mandatory, no random-uuid local fallback).
    """
    from laboutik.views import _obtenir_ou_creer_wallet

    with mock.patch("laboutik.views.FedowAPI") as MockAPI:
        # Fedow ne connaît pas la carte (404 → None côté card_tag_id_retrieve).
        # / Fedow doesn't know the card (404 → None from card_tag_id_retrieve).
        MockAPI.return_value.NFCcard.card_tag_id_retrieve.return_value = None

        with tenant_context(carte_anonyme["tenant"]):
            with pytest.raises(Exception) as exc_info:
                _obtenir_ou_creer_wallet(carte_anonyme["carte"])

    # Le message d'erreur mentionne le tag_id et l'absence dans Fedow.
    # / The error message mentions the tag_id and the Fedow absence.
    assert carte_anonyme["carte"].tag_id in str(exc_info.value)

    # Aucun wallet éphémère ne doit avoir été créé / rattaché.
    # / No ephemeral wallet must have been created / attached.
    with tenant_context(carte_anonyme["tenant"]):
        carte_anonyme["carte"].refresh_from_db()
        assert carte_anonyme["carte"].wallet_ephemere is None


def test_resolution_fedow_idempotente_un_seul_wallet(carte_anonyme):
    """Idempotence : deux appels successifs de `obtenir_wallet_carte_depuis_fedow` avec le
    même uuid Fedow → UN SEUL Wallet local (get_or_create, même uuid).
    / Idempotence: two successive `obtenir_wallet_carte_depuis_fedow` calls with the same
    Fedow uuid → ONLY ONE local Wallet (get_or_create, same uuid).
    """
    from laboutik.views import obtenir_wallet_carte_depuis_fedow
    from AuthBillet.models import Wallet

    wallet_uuid_fedow = uuidlib.uuid4()

    with mock.patch("laboutik.views.FedowAPI") as MockAPI:
        MockAPI.return_value.NFCcard.card_tag_id_retrieve.return_value = {
            "wallet_uuid": str(wallet_uuid_fedow),
            "is_wallet_ephemere": True,
            "origin": {},
        }

        with tenant_context(carte_anonyme["tenant"]):
            wallet_1 = obtenir_wallet_carte_depuis_fedow(carte_anonyme["carte"])
            wallet_2 = obtenir_wallet_carte_depuis_fedow(carte_anonyme["carte"])

    # Même uuid PK (comparé en str, cf. get_or_create), et un seul Wallet en base.
    # / Same uuid PK (compared as str, see get_or_create), and only one Wallet in DB.
    assert str(wallet_1.uuid) == str(wallet_2.uuid) == str(wallet_uuid_fedow)
    with tenant_context(carte_anonyme["tenant"]):
        assert Wallet.objects.filter(uuid=wallet_uuid_fedow).count() == 1
