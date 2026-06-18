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
from django.test import override_settings
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
        # Asset fédéré : un seul autorisé par schéma (contrainte unique_primary_asset
        # sur category='FED'). On réutilise donc celui qui existe déjà en dev plutôt
        # que d'en créer un (qui violerait la contrainte). Peut être None.
        # / Federated asset: only one allowed per schema (unique constraint on
        # category='FED'). Reuse the existing one instead of creating a second.
        asset_fed = AssetFedowPublic.objects.filter(
            category=AssetFedowPublic.STRIPE_FED_FIAT,
        ).first()

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

        # Un vrai user destinataire : la vue crée désormais une LigneArticle de
        # traçabilité qui exige un user réel (un MagicMock casse la sauvegarde du
        # JSONField metadata). On le réutilise via le mock de get_or_create_user.
        # / A real recipient user: the view now creates a tracing LigneArticle
        # that needs a real user (a MagicMock breaks the metadata JSONField save).
        from AuthBillet.utils import get_or_create_user
        user_refill = get_or_create_user(f"refilluser-{_suffix()}@example.org")

    data = {
        "tenant": tenant,
        "asset_gift": asset_gift,
        "asset_gift_other": asset_gift_other,
        "asset_time": asset_time,
        "asset_fiat": asset_fiat,
        "asset_fed": asset_fed,
        "key": key_str,
        "key_time": key_str_time,
        "key_no": key_str_no,
        "user": user_refill,
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
        # asset_fed n'est PAS supprimé : il préexistait, on l'a seulement réutilisé.
        # / asset_fed is NOT deleted: it pre-existed, we only reused it.
        try:
            user_refill.delete()
        except Exception:
            pass  # best-effort : un wallet/objet lié peut le protéger
        wallet.delete()


@pytest.fixture
def fedow_real_setup(tenant):
    """Assets RÉELS rechargeables, créés à la fois en base ET sur Fedow, avec une
    clé API liée pour chacun. Skip explicite si Fedow est indisponible.

    On reproduit ce que fait l'admin (AssetAdmin.save_model) : wallet_origin =
    wallet de la place + get_or_create_token_asset() pour matérialiser l'asset
    côté serveur Fedow. Un objects.create() seul ne crée l'asset qu'en local.
    / Real refillable assets, created both in DB AND on Fedow, each with a bound
    API key. Explicit skip if Fedow is unavailable. Mirrors AssetAdmin.save_model.
    """
    from django.db import connection
    from django.test import override_settings

    from fedow_connect.models import FedowConfig
    from fedow_connect.fedow_api import FedowAPI
    from fedow_public.models import AssetFedowPublic
    from BaseBillet.models import ExternalApiKey
    from rest_framework_api_key.models import APIKey

    with override_settings(DEBUG=True), tenant_context(tenant):
        if not FedowConfig.get_solo().can_fedow():
            pytest.skip("Fedow indisponible (can_fedow=False) — test d'intégration sauté.")

        fedow_config = FedowConfig.get_solo()
        api = FedowAPI(fedow_config=fedow_config)

        # Un asset par type rechargeable (cadeau, temps, fidélité), avec un NOM
        # UNIQUE par run : Fedow refuse un nom déjà présent (validate_name), et un
        # asset fraîchement créé conserve son uuid Lespass côté Fedow — donc la
        # recharge (qui envoie cet uuid) le retrouve bien.
        # / One asset per refillable category, with a UNIQUE name per run: Fedow
        # rejects a duplicate name, and a freshly created asset keeps its Lespass
        # uuid on Fedow, so the refill (sending that uuid) resolves it correctly.
        suffixe = _suffix()
        categories = {
            "cadeau": AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT,
            "temps": AssetFedowPublic.TIME,
            "fidelite": AssetFedowPublic.FIDELITY,
        }
        assets, keys, cles_creees, assets_crees = {}, {}, [], []
        for i, (nom, categorie) in enumerate(categories.items()):
            asset = AssetFedowPublic.objects.create(
                category=categorie,
                name=f"{nom} API {suffixe}",
                currency_code=(suffixe[:2] + str(i)).upper(),  # 3 car. ~uniques
                wallet_origin=fedow_config.wallet,
                origin=connection.tenant,
            )
            # Crée l'asset sur Fedow (avec l'uuid Lespass).
            # / Create the asset on Fedow (with the Lespass uuid).
            api.asset.get_or_create_token_asset(asset)
            assets[nom] = asset
            assets_crees.append(asset)

            api_obj, key_str = APIKey.objects.create_key(name=f"{nom}key-{suffixe}")
            ext_key = ExternalApiKey.objects.create(
                name=f"{nom}key-{suffixe}", key=api_obj, gift_asset=asset,
            )
            keys[nom] = key_str
            cles_creees.append((ext_key, api_obj))

    yield {"tenant": tenant, "assets": assets, "keys": keys}

    # Nettoyage : clés + assets locaux. Les assets côté Fedow restent (pas
    # d'endpoint de suppression simple) — pollution mineure de la base dev.
    # / Cleanup: keys + local assets. Fedow-side assets remain (minor dev noise).
    with tenant_context(tenant):
        for ext_key, api_obj in cles_creees:
            ext_key.delete()
            api_obj.delete()
        for asset in assets_crees:
            asset.delete()


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


def test_refill_asset_federe_refuse_422(gift_setup):
    """Un asset fédéré (FED, fiduciaire fédérée adossée à l'euro) n'est pas
    rechargeable -> 422.
    / A federated asset (FED, euro-backed) is not refillable -> 422.

    Comme le fiduciaire local (TLF), le fédéré (FED) est exclu de
    REFILLABLE_CATEGORIES. On ne doit jamais pouvoir créditer de l'argent réel
    (euro / euro fédéré) via cette route : uniquement cadeau, temps, fidélité.
    / Like local fiat (TLF), federated (FED) is excluded from REFILLABLE.
    Real money (euro / federated euro) must never be credited via this route.
    """
    if gift_setup["asset_fed"] is None:
        pytest.skip("Aucun asset fédéré (FED) en base dev pour ce test.")
    resp = _post(
        payload={
            "email": "user@example.org",
            "asset": str(gift_setup["asset_fed"].uuid),
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
            "AuthBillet.utils.get_or_create_user", return_value=gift_setup["user"]
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


def test_refill_fedow_echec_502_et_ligne_failed(gift_setup):
    """Si Fedow lève pendant le crédit (ex: l'erreur ligne_article_uuid d'origine),
    on renvoie un 502 propre et la LigneArticle créée passe en FAILED.
    / If Fedow raises during credit, return a clean 502 and the created
    LigneArticle is marked FAILED.

    C'est exactement le scénario du bug initial (500 brute) : on le rend propre
    et traçable. / This is the original bug scenario (raw 500), made clean.
    """
    from BaseBillet.models import LigneArticle

    with (
        mock.patch(
            "AuthBillet.utils.get_or_create_user", return_value=gift_setup["user"]
        ),
        mock.patch("fedow_connect.models.FedowConfig.can_fedow", return_value=True),
        mock.patch("fedow_connect.fedow_api.FedowAPI") as MockFedow,
    ):
        refill = MockFedow.return_value.transaction.refill_from_lespass_to_user_wallet
        refill.side_effect = Exception(
            {"metadata": ["No data in metadata for ligne_article_uuid"]}
        )
        resp = _post(
            payload={
                "email": "erreur@example.org",
                "asset": str(gift_setup["asset_gift"].uuid),
                "amount": 250,
            },
            key=gift_setup["key"],
        )
        # On récupère l'uuid de la ligne via le metadata passé à Fedow.
        # / Get the line uuid from the metadata passed to Fedow.
        _, kwargs = refill.call_args
        ligne_uuid = kwargs["metadata"]["ligne_article_uuid"]

    assert resp.status_code == 502, (
        f"Attendu 502 (erreur fournisseur), obtenu {resp.status_code}"
    )
    with tenant_context(gift_setup["tenant"]):
        ligne = LigneArticle.objects.get(uuid=ligne_uuid)
        assert ligne.status == LigneArticle.FAILED, (
            f"La ligne aurait dû passer FAILED, obtenu {ligne.status}"
        )


# ---------------------------------------------------------------------------
# Tests d'INTÉGRATION RÉELLE (Fedow réel, pas de mock) — crédit effectif vérifié
# / REAL INTEGRATION tests (real Fedow, no mock) — effective credit verified
# ---------------------------------------------------------------------------


def _solde_fedow(tenant, email, asset):
    """Lit le solde réel d'un asset sur le wallet Fedow de l'email donné.
    Retourne 0 si le wallet n'existe pas encore (user jamais crédité).
    / Reads the real balance of an asset on the user's Fedow wallet.
    Returns 0 if the wallet does not exist yet (user never credited)."""
    from django.test import override_settings
    from fedow_connect.fedow_api import FedowAPI
    from AuthBillet.utils import get_or_create_user

    with override_settings(DEBUG=True), tenant_context(tenant):
        user = get_or_create_user(email, send_mail=False)
        try:
            wallet = FedowAPI().wallet.retrieve_by_signature(user)
        except Exception:
            return 0  # pas encore de wallet Fedow -> solde nul
        return next(
            (tok["value"] for tok in wallet.validated_data.get("tokens", [])
             if str(tok["asset_uuid"]) == str(asset.uuid)),
            0,
        )


@override_settings(DEBUG=True)
@pytest.mark.parametrize("type_asset", ["cadeau", "temps", "fidelite"])
def test_refill_reel_credite_le_wallet(fedow_real_setup, type_asset):
    """INTÉGRATION RÉELLE (sans mock) : la recharge crédite vraiment le wallet sur
    Fedow, pour chaque type d'asset rechargeable (cadeau, temps, fidélité).
    / REAL INTEGRATION (no mock): the refill actually credits the wallet on Fedow,
    for each refillable asset type.

    C'est ce test qui aurait attrapé le bug d'origine (ligne_article_uuid /
    membership_uuid manquants) — le mock le cachait.
    / This is the test that would have caught the original bug — the mock hid it.
    """
    asset = fedow_real_setup["assets"][type_asset]
    key = fedow_real_setup["keys"][type_asset]
    email = f"realrefill-{_suffix()}@example.org"
    montant = 250

    solde_avant = _solde_fedow(fedow_real_setup["tenant"], email, asset)

    resp = _post(
        payload={"email": email, "asset": str(asset.uuid), "amount": montant},
        key=key,
    )
    assert resp.status_code == 201, (
        f"{type_asset} : recharge échouée ({resp.status_code}) {resp.content[:300]}"
    )
    data = resp.json()
    assert data["@type"] == "MoneyTransfer"
    assert data["amount"] == montant
    assert data["asset"] == str(asset.uuid)

    # Le crédit a bien eu lieu RÉELLEMENT sur Fedow.
    # / The credit actually happened on Fedow.
    solde_apres = _solde_fedow(fedow_real_setup["tenant"], email, asset)
    assert solde_apres == solde_avant + montant, (
        f"{type_asset} : solde Fedow {solde_apres} != {solde_avant}+{montant}"
    )


@override_settings(DEBUG=True)
def test_refill_reel_idempotent_ne_recredite_pas(fedow_real_setup):
    """INTÉGRATION RÉELLE : deux appels avec la même Idempotency-Key ne créditent
    le wallet qu'UNE seule fois (208 au rejeu).
    / REAL: two calls with the same Idempotency-Key credit the wallet only once.
    """
    from django.core.cache import cache
    from django.db import connection

    asset = fedow_real_setup["assets"]["cadeau"]
    key = fedow_real_setup["keys"]["cadeau"]
    email = f"realidem-{_suffix()}@example.org"
    montant = 150
    idem = uuidlib.uuid4().hex
    payload = {"email": email, "asset": str(asset.uuid), "amount": montant}

    solde_avant = _solde_fedow(fedow_real_setup["tenant"], email, asset)

    resp1 = _post(payload=payload, key=key, idem=idem)
    resp2 = _post(payload=payload, key=key, idem=idem)

    assert resp1.status_code == 201, f"1er appel : {resp1.status_code} {resp1.content[:200]}"
    assert resp2.status_code == 208, "le rejeu idempotent doit renvoyer 208"
    assert resp1.json()["identifier"] == resp2.json()["identifier"]

    # Le wallet n'a été crédité qu'UNE fois malgré les deux appels.
    # / The wallet was credited only once despite two calls.
    solde_apres = _solde_fedow(fedow_real_setup["tenant"], email, asset)
    assert solde_apres == solde_avant + montant, (
        f"Idempotence cassée : solde {solde_apres} != {solde_avant}+{montant} (double crédit ?)"
    )

    with tenant_context(fedow_real_setup["tenant"]):
        cache.delete(f"api:gift_refill:idem:{connection.tenant.pk}:{idem}")
