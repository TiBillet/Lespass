"""
Tests — API v2 « recharge cadeau » (gift token wallet refill).
/ Tests — API v2 gift token wallet refill.

LOCALISATION : tests/pytest/test_api_v2_wallet_refill.py

Route testee : POST /api/v2/wallet-refills/
- Authentifie par cle API (ExternalApiKey) restreinte a un asset cadeau (TNF)
  via le champ gift_asset.
- Credite des tokens cadeau sur la tirelire d'un user (delegue a Fedow).

NOTE TECHNIQUE : ces tests reutilisent la base de donnees dev existante
(pattern V2 onboard). django-tenants exige un schema tenant reel pour les
modeles TENANT_APPS. On cree les objets dans tenant_context(lespass) puis on
appelle la vue via APIClient avec SERVER_NAME pour que le middleware tenant
resolve le schema 'lespass'. Fedow est mocke (imports locaux dans la vue ->
on patch a la source : fedow_connect.* et AuthBillet.utils).
/ TECHNICAL NOTE: reuse dev DB; create objects in tenant_context then call the
view through APIClient with SERVER_NAME so the tenant middleware resolves
'lespass'. Fedow is mocked at source.
"""

import uuid as uuidlib
from unittest import mock

import pytest
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient


# ---------------------------------------------------------------------------
# Reutiliser la DB dev au lieu d'une test DB temporaire (pattern onboard V2).
# / Reuse the dev DB instead of a temporary test DB.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def django_db_setup():
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db

PATH = "/api/v2/wallet-refills/"
HOST = "lespass.tibillet.localhost"


def _suffix():
    """Suffixe court unique pour eviter les collisions de noms.
    / Short unique suffix to avoid name collisions."""
    return uuidlib.uuid4().hex[:6]


@pytest.fixture
def gift_setup():
    """
    Cree dans le tenant 'lespass' : un wallet d'origine, deux assets cadeau
    (TNF), un asset monnaie temps (TIM), un asset fiduciaire (TLF), et trois
    cles API (une liee a l'asset cadeau, une liee a l'asset temps, une sans).
    Nettoie tout en fin de test.
    / Create a wallet, two gift assets (TNF), one time-currency asset (TIM),
    one fiat asset (TLF), and three API keys (gift-bound, time-bound, none).
    Cleans everything afterwards.
    """
    from Customers.models import Client
    from AuthBillet.models import Wallet
    from fedow_public.models import AssetFedowPublic
    from BaseBillet.models import ExternalApiKey
    from rest_framework_api_key.models import APIKey

    tenant = Client.objects.get(schema_name="lespass")

    with tenant_context(tenant):
        wallet = Wallet.objects.create(origin=tenant)

        asset_gift = AssetFedowPublic.objects.create(
            name=f"Test Cadeau {_suffix()}",
            currency_code="TGC",
            wallet_origin=wallet,
            origin=tenant,
            category=AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT,
        )
        asset_gift_other = AssetFedowPublic.objects.create(
            name=f"Autre Cadeau {_suffix()}",
            currency_code="TGO",
            wallet_origin=wallet,
            origin=tenant,
            category=AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT,
        )
        asset_time = AssetFedowPublic.objects.create(
            name=f"Test Temps {_suffix()}",
            currency_code="TTM",
            wallet_origin=wallet,
            origin=tenant,
            category=AssetFedowPublic.TIME,
        )
        asset_fiat = AssetFedowPublic.objects.create(
            name=f"Test Fiat {_suffix()}",
            currency_code="TFI",
            wallet_origin=wallet,
            origin=tenant,
            category=AssetFedowPublic.TOKEN_LOCAL_FIAT,
        )

        api_obj, key_str = APIKey.objects.create_key(name=f"giftkey-{_suffix()}")
        ext_key = ExternalApiKey.objects.create(
            name=f"giftkey-{_suffix()}",
            key=api_obj,
            gift_asset=asset_gift,
        )

        api_obj_time, key_str_time = APIKey.objects.create_key(
            name=f"timekey-{_suffix()}"
        )
        ext_key_time = ExternalApiKey.objects.create(
            name=f"timekey-{_suffix()}",
            key=api_obj_time,
            gift_asset=asset_time,
        )

        api_obj_no, key_str_no = APIKey.objects.create_key(name=f"nokey-{_suffix()}")
        ext_key_no = ExternalApiKey.objects.create(
            name=f"nokey-{_suffix()}",
            key=api_obj_no,
        )

    data = {
        "tenant": tenant,
        "asset_gift": asset_gift,
        "asset_gift_other": asset_gift_other,
        "asset_time": asset_time,
        "asset_fiat": asset_fiat,
        "key": key_str,
        "key_time": key_str_time,
        "key_no": key_str_no,
    }
    yield data

    # Nettoyage / Cleanup
    with tenant_context(tenant):
        ext_key.delete()
        ext_key_time.delete()
        ext_key_no.delete()
        api_obj.delete()
        api_obj_time.delete()
        api_obj_no.delete()
        asset_gift.delete()
        asset_gift_other.delete()
        asset_time.delete()
        asset_fiat.delete()
        wallet.delete()


def _post(payload=None, key=None, idem=None):
    """Effectue le POST sur la route en resolvant le tenant via SERVER_NAME.
    / Perform the POST, resolving the tenant via SERVER_NAME."""
    client = APIClient()
    extra = {"SERVER_NAME": HOST}
    if key:
        extra["HTTP_AUTHORIZATION"] = f"Api-Key {key}"
    if idem:
        extra["HTTP_IDEMPOTENCY_KEY"] = idem
    return client.post(PATH, data=payload or {}, format="json", **extra)


# ---------------------------------------------------------------------------
# Tests d'autorisation (n'atteignent pas Fedow)
# / Authorization tests (do not reach Fedow)
# ---------------------------------------------------------------------------


def test_refill_sans_cle_est_refuse(gift_setup):
    """Sans header Authorization, la permission refuse.
    / Without Authorization header, permission is denied."""
    resp = _post(
        payload={
            "email": "user@example.org",
            "asset": str(gift_setup["asset_gift"].uuid),
            "amount": 100,
        }
    )
    assert resp.status_code in (401, 403)


def test_refill_cle_sans_gift_asset_est_refusee(gift_setup):
    """Une cle sans gift_asset n'a pas le droit walletrefill -> refuse.
    / A key without gift_asset lacks the walletrefill permission -> denied."""
    resp = _post(
        payload={
            "email": "user@example.org",
            "asset": str(gift_setup["asset_gift"].uuid),
            "amount": 100,
        },
        key=gift_setup["key_no"],
    )
    assert resp.status_code in (401, 403)


def test_refill_asset_non_autorise_pour_la_cle_403(gift_setup):
    """Demander un autre asset cadeau que celui de la cle -> 403.
    / Requesting a gift asset other than the key's one -> 403."""
    resp = _post(
        payload={
            "email": "user@example.org",
            "asset": str(gift_setup["asset_gift_other"].uuid),
            "amount": 100,
        },
        key=gift_setup["key"],
    )
    assert resp.status_code == 403


def test_refill_asset_fiduciaire_refuse_422(gift_setup):
    """Un asset fiduciaire (TLF, adosse a l'euro) n'est pas rechargeable -> 422.
    / A fiat asset (TLF, euro-backed) is not refillable -> 422.

    L'asset fiduciaire n'est pas celui de la cle, mais le controle de categorie
    rechargeable passe AVANT le controle d'appartenance, donc 422.
    / The fiat asset is not the key's asset, but the refillable-category check
    runs before the ownership check, hence 422.
    """
    resp = _post(
        payload={
            "email": "user@example.org",
            "asset": str(gift_setup["asset_fiat"].uuid),
            "amount": 100,
        },
        key=gift_setup["key"],
    )
    assert resp.status_code == 422


def test_refill_au_dessus_du_plafond_422(gift_setup):
    """amount > 10000 -> 422 (plafond).
    / amount above 10000 -> 422 (cap)."""
    resp = _post(
        payload={
            "email": "user@example.org",
            "asset": str(gift_setup["asset_gift"].uuid),
            "amount": 10001,
        },
        key=gift_setup["key"],
    )
    assert resp.status_code == 422


def test_refill_payload_invalide_400(gift_setup):
    """amount negatif / manquant -> 400 (serializer).
    / negative / missing amount -> 400 (serializer)."""
    resp = _post(
        payload={
            "email": "user@example.org",
            "asset": str(gift_setup["asset_gift"].uuid),
            "amount": -5,
        },
        key=gift_setup["key"],
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Tests atteignant Fedow (mocke)
# / Tests reaching Fedow (mocked)
# ---------------------------------------------------------------------------


def test_refill_fedow_indisponible_503(gift_setup):
    """Si can_fedow() est faux -> 503.
    / If can_fedow() is false -> 503."""
    with (
        mock.patch(
            "AuthBillet.utils.get_or_create_user", return_value=mock.MagicMock()
        ),
        mock.patch("fedow_connect.models.FedowConfig.can_fedow", return_value=False),
    ):
        resp = _post(
            payload={
                "email": "user@example.org",
                "asset": str(gift_setup["asset_gift"].uuid),
                "amount": 500,
            },
            key=gift_setup["key"],
        )
    assert resp.status_code == 503


def test_refill_nominal_201_appelle_fedow(gift_setup):
    """Cas nominal : 201, reponse MoneyTransfer, Fedow appele une fois.
    / Nominal: 201, MoneyTransfer response, Fedow called once."""
    tx_uuid = str(uuidlib.uuid4())
    with (
        mock.patch(
            "AuthBillet.utils.get_or_create_user", return_value=mock.MagicMock()
        ),
        mock.patch("fedow_connect.models.FedowConfig.can_fedow", return_value=True),
        mock.patch("fedow_connect.fedow_api.FedowAPI") as MockFedow,
    ):
        MockFedow.return_value.transaction.refill_from_lespass_to_user_wallet.return_value = {
            "uuid": tx_uuid,
            "hash": "deadbeef",
        }
        resp = _post(
            payload={
                "email": "alice@example.org",
                "asset": str(gift_setup["asset_gift"].uuid),
                "amount": 500,
            },
            key=gift_setup["key"],
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["@type"] == "MoneyTransfer"
    assert data["identifier"] == tx_uuid
    assert data["amount"] == 500
    assert data["asset"] == str(gift_setup["asset_gift"].uuid)
    assert data["recipient"]["email"] == "alice@example.org"

    refill = MockFedow.return_value.transaction.refill_from_lespass_to_user_wallet
    refill.assert_called_once()
    _, kwargs = refill.call_args
    assert kwargs["amount"] == 500
    assert kwargs["asset"].uuid == gift_setup["asset_gift"].uuid


def test_refill_monnaie_temps_201(gift_setup):
    """Un asset Monnaie temps (TIM) est rechargeable -> 201.
    / A time-currency (TIM) asset is refillable -> 201.

    Verifie l'elargissement des categories au-dela du seul cadeau (TNF).
    / Checks the category set was widened beyond gift (TNF) only.
    """
    tx_uuid = str(uuidlib.uuid4())
    with (
        mock.patch(
            "AuthBillet.utils.get_or_create_user", return_value=mock.MagicMock()
        ),
        mock.patch("fedow_connect.models.FedowConfig.can_fedow", return_value=True),
        mock.patch("fedow_connect.fedow_api.FedowAPI") as MockFedow,
    ):
        MockFedow.return_value.transaction.refill_from_lespass_to_user_wallet.return_value = {
            "uuid": tx_uuid,
        }
        resp = _post(
            payload={
                "email": "user@example.org",
                "asset": str(gift_setup["asset_time"].uuid),
                "amount": 300,
            },
            key=gift_setup["key_time"],
        )
    assert resp.status_code == 201
    assert resp.json()["identifier"] == tx_uuid
    assert resp.json()["asset"] == str(gift_setup["asset_time"].uuid)


def test_refill_cree_user_si_inconnu(gift_setup):
    """get_or_create_user est appele avec l'email fourni.
    / get_or_create_user is called with the provided email."""
    with (
        mock.patch(
            "AuthBillet.utils.get_or_create_user", return_value=mock.MagicMock()
        ) as mock_user,
        mock.patch("fedow_connect.models.FedowConfig.can_fedow", return_value=True),
        mock.patch("fedow_connect.fedow_api.FedowAPI") as MockFedow,
    ):
        MockFedow.return_value.transaction.refill_from_lespass_to_user_wallet.return_value = {
            "uuid": str(uuidlib.uuid4())
        }
        resp = _post(
            payload={
                "email": "bob@example.org",
                "asset": str(gift_setup["asset_gift"].uuid),
                "amount": 200,
            },
            key=gift_setup["key"],
        )
    assert resp.status_code == 201
    mock_user.assert_called_once_with("bob@example.org")


def test_refill_idempotent_ne_recredite_pas(gift_setup):
    """Deux appels avec la meme Idempotency-Key -> Fedow appele une seule fois.
    / Two calls with the same Idempotency-Key -> Fedow called once."""
    idem = uuidlib.uuid4().hex
    payload = {
        "email": "carol@example.org",
        "asset": str(gift_setup["asset_gift"].uuid),
        "amount": 300,
    }
    with (
        mock.patch(
            "AuthBillet.utils.get_or_create_user", return_value=mock.MagicMock()
        ),
        mock.patch("fedow_connect.models.FedowConfig.can_fedow", return_value=True),
        mock.patch("fedow_connect.fedow_api.FedowAPI") as MockFedow,
    ):
        MockFedow.return_value.transaction.refill_from_lespass_to_user_wallet.return_value = {
            "uuid": str(uuidlib.uuid4())
        }
        resp1 = _post(payload=payload, key=gift_setup["key"], idem=idem)
        resp2 = _post(payload=payload, key=gift_setup["key"], idem=idem)
        refill = MockFedow.return_value.transaction.refill_from_lespass_to_user_wallet
        assert refill.call_count == 1

    assert resp1.status_code == 201
    # Rejeu idempotent : 208 Already Reported (deja traite, pas de re-credit)
    # / Idempotent replay: 208 Already Reported (already processed, no re-credit)
    assert resp2.status_code == 208
    assert resp1.json()["identifier"] == resp2.json()["identifier"]

    # Nettoyage du cache d'idempotence / Idempotency cache cleanup
    from django.core.cache import cache
    from django.db import connection

    with tenant_context(gift_setup["tenant"]):
        cache.delete(f"api:gift_refill:idem:{connection.tenant.pk}:{idem}")
