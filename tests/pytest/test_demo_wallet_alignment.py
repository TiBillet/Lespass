"""
tests/pytest/test_demo_wallet_alignment.py — Alignement du wallet user sur Fedow (demo data).
tests/pytest/test_demo_wallet_alignment.py — Aligning the user wallet on Fedow (demo data).

POURQUOI / WHY :
`create_test_pos_data` cree, pour les cartes clientes liees a un user (CLIENT1/CLIENT2),
un Wallet LOCAL a uuid aleatoire. Or Fedow est la source de verite du wallet de carte
(`obtenir_wallet_carte_depuis_fedow`). Resultat : la carte porte DEUX wallets (un local
fantome + le wallet Fedow orphelin), et le scan utilise le mauvais. `aligner_wallet_user_sur_fedow`
corrige le doublon : il migre le solde (Token) + l'historique (Transaction/LigneArticle) du
wallet local vers le wallet Fedow, reassigne user.wallet, et supprime le wallet local.
/ create_test_pos_data creates a random-uuid LOCAL wallet for user-linked client cards, but
Fedow is the source of truth. This leaves the card with TWO wallets. aligner_wallet_user_sur_fedow
migrates balance + history to the Fedow wallet, reassigns user.wallet, deletes the local wallet.

La frontiere Fedow (obtenir le wallet cible) est mockee : seule cette dependance reseau est
inevitable. La logique migree (Token/Transaction/Wallet) est exercee POUR DE VRAI.
/ Only the Fedow network boundary (getting the target wallet) is mocked; the migration logic runs for real.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_demo_wallet_alignment.py -q
"""

import uuid as uuid_module
from unittest import mock

import pytest
from django_tenants.utils import tenant_context

from Customers.models import Client


pytestmark = pytest.mark.django_db

TEST_PREFIX = "[test_demo_wallet_alignment]"


def _tag():
    return f"AL{uuid_module.uuid4().hex[:6].upper()}"  # "AL" + 6 = 8 chars


@pytest.fixture
def carte_client_avec_wallet_local():
    """Reproduit l'etat post-create_test_pos_data : carte cliente liee a un user dont le
    wallet est LOCAL (uuid aleatoire), garni d'un solde (Token + Transaction).
    / Reproduces the post-create_test_pos_data state: a user-linked client card whose wallet
    is LOCAL (random uuid), credited with a balance (Token + Transaction).

    DB dev partagee, pas de rollback : nettoyage manuel en teardown.
    """
    from AuthBillet.models import Wallet
    from AuthBillet.models import TibilletUser
    from QrcodeCashless.models import CarteCashless, Detail
    from fedow_core.models import Asset, Token, Transaction
    from fedow_core.services import WalletService

    tenant = Client.objects.get(schema_name="lespass")
    tag = _tag()

    with tenant_context(tenant):
        # Asset TLF du tenant (cree par le seed) pour porter un solde.
        # / Tenant TLF asset (seeded) to hold a balance.
        asset = Asset.objects.filter(
            tenant_origin=tenant, category=Asset.TLF, active=True
        ).first()
        assert asset is not None, "Asset TLF lespass requis (lancer le seed POS)."

        detail, _ = Detail.objects.get_or_create(
            slug="test-demo-wallet-alignment",
            defaults={"base_url": "test-align.localhost", "generation": 1, "origine": tenant},
        )
        wallet_local = Wallet.objects.create(origin=tenant, name=f"{TEST_PREFIX} local")
        user = TibilletUser.objects.create(
            email=f"align-{tag.lower()}@test.loc",
            username=f"align-{tag.lower()}@test.loc",
            espece=TibilletUser.TYPE_HUM,
            client_source=tenant,
            is_active=True,
            wallet=wallet_local,
        )
        carte = CarteCashless.objects.create(
            tag_id=tag, uuid=uuid_module.uuid4(), number=tag, detail=detail, user=user
        )
        # Garnir le wallet local (cree Token + Transaction sur wallet_local).
        # / Credit the local wallet (creates Token + Transaction on wallet_local).
        WalletService.crediter(wallet_local, asset, 1500)

    yield {
        "tenant": tenant,
        "carte": carte,
        "user": user,
        "wallet_local": wallet_local,
        "asset": asset,
    }

    # Nettoyage : on supprime tout ce qui peut subsister (selon que l'alignement a eu lieu).
    # / Cleanup: remove whatever may remain (depending on whether alignment happened).
    with tenant_context(tenant):
        carte.refresh_from_db()
        # Detacher le wallet du user puis supprimer carte/user.
        wallet_courant = carte.user.wallet if carte.user_id else None
        carte.delete()
        user.refresh_from_db()
        user.wallet = None
        user.save(update_fields=["wallet"])
        user.delete()
        # Supprimer tokens/transactions puis les wallets restants.
        for w in {wallet_local.uuid, getattr(wallet_courant, "uuid", None)}:
            if w is None:
                continue
            Transaction.objects.filter(sender__uuid=w).delete()
            Transaction.objects.filter(receiver__uuid=w).delete()
            Token.objects.filter(wallet__uuid=w).delete()
            Wallet.objects.filter(uuid=w).delete()


def test_aligner_migre_solde_et_supprime_le_wallet_local(carte_client_avec_wallet_local):
    """Apres alignement : user.wallet == wallet Fedow, le solde a migre, le wallet local a disparu.
    / After alignment: user.wallet == Fedow wallet, balance migrated, local wallet gone."""
    from AuthBillet.models import Wallet
    from fedow_core.models import Token
    from fedow_core.services import WalletService
    from Administration.management.commands.demo_data_v2 import (
        aligner_wallet_user_sur_fedow,
    )

    tenant = carte_client_avec_wallet_local["tenant"]
    carte = carte_client_avec_wallet_local["carte"]
    wallet_local = carte_client_avec_wallet_local["wallet_local"]
    asset = carte_client_avec_wallet_local["asset"]

    with tenant_context(tenant):
        # Le wallet Fedow miroir (meme role que get_or_create(uuid=fedow_uuid)).
        # / The Fedow mirror wallet (same role as get_or_create(uuid=fedow_uuid)).
        wallet_fedow = Wallet.objects.create(
            uuid=uuid_module.uuid4(), origin=tenant, name=f"{TEST_PREFIX} fedow"
        )

        # Mock de la frontiere Fedow : renvoie le wallet miroir pour cette carte.
        # / Mock the Fedow boundary: returns the mirror wallet for this card.
        with mock.patch(
            "laboutik.views.obtenir_wallet_carte_depuis_fedow",
            return_value=wallet_fedow,
        ):
            a_aligne = aligner_wallet_user_sur_fedow(carte)

        assert a_aligne is True

        carte.refresh_from_db()
        # 1. Le user pointe desormais le wallet Fedow.
        assert str(carte.user.wallet.uuid) == str(wallet_fedow.uuid)
        # 2. Le solde a suivi (1500 sur le wallet Fedow).
        assert WalletService.obtenir_solde(wallet_fedow, asset) == 1500
        # 3. Plus aucun token sur le wallet local.
        assert not Token.objects.filter(wallet__uuid=wallet_local.uuid).exists()
        # 4. Le wallet local fantome a ete supprime (plus de doublon).
        assert not Wallet.objects.filter(uuid=wallet_local.uuid).exists()


def test_aligner_no_op_si_deja_aligne(carte_client_avec_wallet_local):
    """Idempotence : si user.wallet est deja le wallet Fedow, l'alignement ne fait rien.
    / Idempotence: if user.wallet is already the Fedow wallet, alignment is a no-op."""
    from Administration.management.commands.demo_data_v2 import (
        aligner_wallet_user_sur_fedow,
    )

    tenant = carte_client_avec_wallet_local["tenant"]
    carte = carte_client_avec_wallet_local["carte"]
    wallet_local = carte_client_avec_wallet_local["wallet_local"]

    with tenant_context(tenant):
        # Fedow renvoie le wallet DEJA porte par le user → no-op.
        # / Fedow returns the wallet ALREADY held by the user → no-op.
        with mock.patch(
            "laboutik.views.obtenir_wallet_carte_depuis_fedow",
            return_value=wallet_local,
        ):
            a_aligne = aligner_wallet_user_sur_fedow(carte)

        assert a_aligne is False


def test_aligner_no_op_si_carte_inconnue_de_fedow(carte_client_avec_wallet_local):
    """Si Fedow ne connait pas la carte (None), on ne touche a rien (pas de doublon cree).
    / If Fedow doesn't know the card (None), nothing is touched (no duplicate created)."""
    from AuthBillet.models import Wallet
    from Administration.management.commands.demo_data_v2 import (
        aligner_wallet_user_sur_fedow,
    )

    tenant = carte_client_avec_wallet_local["tenant"]
    carte = carte_client_avec_wallet_local["carte"]
    wallet_local = carte_client_avec_wallet_local["wallet_local"]

    with tenant_context(tenant):
        with mock.patch(
            "laboutik.views.obtenir_wallet_carte_depuis_fedow", return_value=None
        ):
            a_aligne = aligner_wallet_user_sur_fedow(carte)

        assert a_aligne is False
        # Le wallet local est intact (toujours porte par le user).
        carte.refresh_from_db()
        assert str(carte.user.wallet.uuid) == str(wallet_local.uuid)
        assert Wallet.objects.filter(uuid=wallet_local.uuid).exists()
