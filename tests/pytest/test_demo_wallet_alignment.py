"""
tests/pytest/test_demo_wallet_alignment.py — Declaration du wallet user aupres de Fedow (demo data).
tests/pytest/test_demo_wallet_alignment.py — Declaring the user wallet to Fedow (demo data).

POURQUOI / WHY :
`create_test_pos_data` cree, pour les cartes clientes liees a un user (CLIENT1/CLIENT2), un
Wallet LOCAL a uuid aleatoire. Fedow, lui, ne connait ni ce user ni sa cle publique : il n'a
qu'un WALLET EPHEMERE anonyme, fabrique a la volee des qu'on lit la carte.
`aligner_wallet_user_sur_fedow` doit DECLARER le user aupres de Fedow (avec sa cle publique),
puis faire absorber le wallet ephemere par le wallet du user.
/ create_test_pos_data creates a random-uuid LOCAL wallet, while Fedow only knows an anonymous
EPHEMERAL wallet. The function must DECLARE the user to Fedow, then have the user's wallet
absorb the ephemeral one.

LE SENS DE LA FUSION EST CE QUE CES TESTS PROTEGENT. Un wallet ephemere n'a pas de cle
publique cote Fedow. Attribuer son uuid au user donne un wallet inauthentifiable : toute
requete signee au nom de ce user casse sur `wallet.public_key()`, et la carte ne peut porter
aucun FED. Le test `test_aligner_declare_le_user_a_fedow` verifie que la declaration a bien
lieu — c'est lui qui echoue si quelqu'un remet la fusion a l'envers.
/ These tests guard the MERGE DIRECTION. An ephemeral wallet has no public key; giving its
uuid to the user yields an unauthenticatable wallet.

La frontiere reseau (FedowAPI) est mockee : c'est la seule dependance inevitable. La logique
locale (Token/Transaction/Wallet) et l'ORDRE des appels Fedow sont exerces POUR DE VRAI.
/ Only the network boundary (FedowAPI) is mocked; local logic and Fedow call ORDER run for real.

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

# Chemin de patch : FedowAPI et FedowConfig sont importes EN TETE du module de seed, donc
# c'est la reference du module de seed qu'il faut remplacer, pas celle de fedow_connect.
# / Patch path: both are imported at the top of the seed module, so patch the seed module's
#   reference, not fedow_connect's.
MODULE_SEED = "Administration.management.commands.demo_data_v2"


def _tag():
    return f"AL{uuid_module.uuid4().hex[:6].upper()}"  # "AL" + 6 = 8 chars


def _fabriquer_fedow_api_mock(tenant, user, wallet_a_rendre):
    """
    Construit un faux FedowAPI qui imite le contrat du vrai.
    / Builds a fake FedowAPI mimicking the real contract.

    `get_or_create_wallet` du vrai client POSE `user.wallet` et le sauve (cf.
    fedow_connect/fedow_api.py). Le mock doit faire pareil, sinon la fonction testee
    travaille sur un user sans wallet et le test ne prouve rien.
    / The real get_or_create_wallet SETS and saves user.wallet; the mock must do the same.

    :param wallet_a_rendre: le Wallet local qui joue le role du miroir du wallet Fedow.
    :return: (mock FedowAPI instancie, mock de la classe)
    """
    def poser_le_wallet_du_user(user_appele):
        # Le vrai client compare l'uuid renvoye par Fedow a `user.wallet.uuid` et leve
        # "Wallet and member mismatch" s'ils different. L'appelant DOIT donc avoir detache
        # le wallet local avant d'arriver ici. On le verifie, sinon supprimer ce
        # detachement passerait au travers de toute la suite.
        # / The real client raises "Wallet and member mismatch" on a differing uuid, so the
        #   caller MUST have detached the local wallet first. Assert it, otherwise removing
        #   that detach would slip past the whole suite.
        assert user_appele.wallet is None, (
            "get_or_create_wallet a ete appele avec un user portant encore son wallet "
            "local : le vrai client Fedow aurait leve 'Wallet and member mismatch'."
        )
        user_appele.wallet = wallet_a_rendre
        user_appele.save(update_fields=["wallet"])
        return wallet_a_rendre, True

    # MOCK STRICT (`create_autospec`), et ce n'est pas un detail : un `MagicMock` nu accepte
    # NIMPORTE QUEL attribut. `api.NFCcard.linkwallet_card_number` y « existe » alors que la
    # vraie methode vit sur `NFCcardFedow`. Un mock permissif valide donc joyeusement un appel
    # sur la mauvaise classe, et le test reste vert pendant que le code casse en production.
    # Avec autospec, un appel hors contrat leve `AttributeError` — le test le voit.
    # / STRICT MOCK: a bare MagicMock accepts ANY attribute, so it happily validates a call on
    #   the wrong class while the real code breaks. autospec raises AttributeError instead.
    from fedow_connect.fedow_api import WalletFedow, NFCcardFedow

    api = mock.MagicMock()
    api.wallet = mock.create_autospec(WalletFedow, instance=True)
    api.NFCcard = mock.create_autospec(NFCcardFedow, instance=True)
    api.wallet.get_or_create_wallet.side_effect = poser_le_wallet_du_user
    api.NFCcard.linkwallet_card_number.return_value = {"first_tag_id": "MOCK1234"}
    return api


@pytest.fixture
def carte_client_avec_wallet_local():
    """Reproduit l'etat post-create_test_pos_data : carte cliente liee a un user dont le
    wallet est LOCAL (uuid aleatoire), garni d'un solde (Token).
    / Reproduces the post-create_test_pos_data state: a user-linked client card whose wallet
    is LOCAL (random uuid), credited with a balance (Token).

    NON COUVERT ICI : la migration de `Transaction` et `LigneArticle` vers le wallet Fedow.
    `WalletService.crediter` ne cree qu'un Token ; ces deux `.update()` de la fonction testee
    n'ont donc pas de donnee a deplacer dans cette fixture.
    / NOT COVERED HERE: the Transaction and LigneArticle migration — crediter only creates a
    Token, so those two .update() calls have nothing to move in this fixture.

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

        detail, _detail_cree = Detail.objects.get_or_create(
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
        # Garnir le wallet local (cree un Token sur wallet_local).
        # / Credit the local wallet (creates a Token on wallet_local).
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
        wallet_courant = carte.user.wallet if carte.user_id else None
        carte.delete()
        user.refresh_from_db()
        user.wallet = None
        user.save(update_fields=["wallet"])
        user.delete()
        for uuid_wallet in {wallet_local.uuid, getattr(wallet_courant, "uuid", None)}:
            if uuid_wallet is None:
                continue
            Transaction.objects.filter(sender__uuid=uuid_wallet).delete()
            Transaction.objects.filter(receiver__uuid=uuid_wallet).delete()
            Token.objects.filter(wallet__uuid=uuid_wallet).delete()
            Wallet.objects.filter(uuid=uuid_wallet).delete()


@pytest.fixture
def fedow_configure():
    """Force `can_fedow()` a True, quel que soit l'etat de la base de dev.
    / Forces can_fedow() to True, whatever the dev database holds."""
    with mock.patch(f"{MODULE_SEED}.FedowConfig") as config_mock:
        config_mock.get_solo.return_value.can_fedow.return_value = True
        yield config_mock


def test_aligner_declare_le_user_a_fedow(carte_client_avec_wallet_local, fedow_configure):
    """LE test de non-regression du sens de fusion.
    / THE merge-direction regression test.

    L'alignement DOIT declarer le user aupres de Fedow via `get_or_create_wallet` — c'est le
    seul appel qui transmet la cle publique du user (`public_pem`). Sans lui, le user herite
    du wallet ephemere anonyme de la carte, que Fedow ne peut pas authentifier.
    Il DOIT ensuite lier la carte via `linkwallet_card_number`, dans cet ordre.
    / Alignment MUST declare the user through get_or_create_wallet (the only call carrying the
    user's public key), THEN link the card. Order matters.
    """
    from AuthBillet.models import Wallet
    from Administration.management.commands.demo_data_v2 import (
        aligner_wallet_user_sur_fedow,
    )

    tenant = carte_client_avec_wallet_local["tenant"]
    carte = carte_client_avec_wallet_local["carte"]
    user = carte_client_avec_wallet_local["user"]

    with tenant_context(tenant):
        wallet_du_user_chez_fedow = Wallet.objects.create(
            uuid=uuid_module.uuid4(), origin=tenant, name=f"{TEST_PREFIX} fedow"
        )
        api = _fabriquer_fedow_api_mock(tenant, user, wallet_du_user_chez_fedow)

        with mock.patch(f"{MODULE_SEED}.FedowAPI", return_value=api):
            aligner_wallet_user_sur_fedow(carte)

        # 1. Le user a bien ete declare aupres de Fedow (avec sa cle publique).
        # / The user was declared to Fedow (carrying their public key).
        assert api.wallet.get_or_create_wallet.called, (
            "Le user n'a PAS ete declare a Fedow : son wallet n'aura pas de cle publique, "
            "et toute requete signee en son nom cassera cote Fedow."
        )
        assert api.wallet.get_or_create_wallet.call_args.args[0].pk == user.pk

        # 2. La carte a ete liee a ce user cote Fedow.
        # / The card was linked to that user on Fedow's side.
        assert api.NFCcard.linkwallet_card_number.called
        appel_lien = api.NFCcard.linkwallet_card_number.call_args
        assert appel_lien.kwargs["user"].pk == user.pk
        assert appel_lien.kwargs["card_number"] == carte.number

        # 3. L'ordre : declarer AVANT de lier. Lier d'abord echouerait, Fedow ne connaissant
        #    pas encore le wallet du user.
        # / Order: declare BEFORE linking; the reverse fails, Fedow not knowing the wallet yet.
        # L'ordre se lit sur le mock parent, qui enregistre les appels des deux sous-objets.
        # / Order is read on the parent mock, which records both children's calls.
        noms_appeles = [appel[0] for appel in api.mock_calls]
        rang_declaration = next(i for i, n in enumerate(noms_appeles)
                                if n.endswith("get_or_create_wallet"))
        rang_liaison = next(i for i, n in enumerate(noms_appeles)
                            if n.endswith("linkwallet_card_number"))
        assert rang_declaration < rang_liaison, (
            "get_or_create_wallet doit preceder linkwallet_card_number : Fedow ne peut pas "
            "lier une carte a un wallet qu'il ne connait pas encore."
        )


def test_aligner_migre_solde_et_supprime_le_wallet_local(
    carte_client_avec_wallet_local, fedow_configure
):
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
    user = carte_client_avec_wallet_local["user"]
    wallet_local = carte_client_avec_wallet_local["wallet_local"]
    asset = carte_client_avec_wallet_local["asset"]

    with tenant_context(tenant):
        wallet_du_user_chez_fedow = Wallet.objects.create(
            uuid=uuid_module.uuid4(), origin=tenant, name=f"{TEST_PREFIX} fedow"
        )
        api = _fabriquer_fedow_api_mock(tenant, user, wallet_du_user_chez_fedow)

        with mock.patch(f"{MODULE_SEED}.FedowAPI", return_value=api):
            a_aligne = aligner_wallet_user_sur_fedow(carte)

        assert a_aligne is True

        carte.refresh_from_db()
        # 1. Le user pointe desormais le wallet declare a Fedow.
        assert str(carte.user.wallet.uuid) == str(wallet_du_user_chez_fedow.uuid)
        # 2. Le solde a suivi (1500 sur le wallet Fedow).
        assert WalletService.obtenir_solde(wallet_du_user_chez_fedow, asset) == 1500
        # 3. Plus aucun token sur le wallet local.
        assert not Token.objects.filter(wallet__uuid=wallet_local.uuid).exists()
        # 4. Le wallet local fantome a ete supprime (plus de doublon).
        assert not Wallet.objects.filter(uuid=wallet_local.uuid).exists()


def test_aligner_no_op_si_deja_aligne(carte_client_avec_wallet_local, fedow_configure):
    """Idempotence : si Fedow rend le wallet que le user porte deja, rien n'est migre.
    / Idempotence: if Fedow returns the wallet the user already holds, nothing is migrated."""
    from AuthBillet.models import Wallet
    from Administration.management.commands.demo_data_v2 import (
        aligner_wallet_user_sur_fedow,
    )

    tenant = carte_client_avec_wallet_local["tenant"]
    carte = carte_client_avec_wallet_local["carte"]
    user = carte_client_avec_wallet_local["user"]
    wallet_local = carte_client_avec_wallet_local["wallet_local"]

    with tenant_context(tenant):
        # Fedow rend le wallet DEJA porte par le user.
        # / Fedow returns the wallet the user ALREADY holds.
        api = _fabriquer_fedow_api_mock(tenant, user, wallet_local)

        with mock.patch(f"{MODULE_SEED}.FedowAPI", return_value=api):
            a_aligne = aligner_wallet_user_sur_fedow(carte)

        assert a_aligne is False
        # Le wallet local est intact : c'est le wallet du user, pas un fantome.
        # / The local wallet is intact: it IS the user's wallet, not a ghost.
        assert Wallet.objects.filter(uuid=wallet_local.uuid).exists()
        carte.refresh_from_db()
        assert str(carte.user.wallet.uuid) == str(wallet_local.uuid)


def test_aligner_rend_son_wallet_au_user_si_fedow_echoue(
    carte_client_avec_wallet_local, fedow_configure
):
    """Fedow injoignable : le user ne doit PAS rester sans wallet.
    / Fedow unreachable: the user must NOT be left without a wallet.

    L'alignement detache le wallet local avant d'appeler Fedow (sinon "Wallet and member
    mismatch"). Si l'appel echoue, ce detachement doit etre annule.
    / Alignment detaches the local wallet before calling Fedow; a failure must undo that.
    """
    from AuthBillet.models import Wallet
    from Administration.management.commands.demo_data_v2 import (
        aligner_wallet_user_sur_fedow,
    )

    tenant = carte_client_avec_wallet_local["tenant"]
    carte = carte_client_avec_wallet_local["carte"]
    user = carte_client_avec_wallet_local["user"]
    wallet_local = carte_client_avec_wallet_local["wallet_local"]

    with tenant_context(tenant):
        api = mock.MagicMock()
        api.wallet.get_or_create_wallet.side_effect = Exception("Fedow injoignable")

        with mock.patch(f"{MODULE_SEED}.FedowAPI", return_value=api):
            with pytest.raises(Exception, match="Fedow injoignable"):
                aligner_wallet_user_sur_fedow(carte)

        # Le user a retrouve son wallet local.
        # / The user got their local wallet back.
        user.refresh_from_db()
        assert user.wallet is not None, "Le user est reste SANS wallet apres l'echec Fedow."
        assert str(user.wallet.uuid) == str(wallet_local.uuid)
        assert Wallet.objects.filter(uuid=wallet_local.uuid).exists()


def test_aligner_no_op_si_fedow_absent(carte_client_avec_wallet_local):
    """Sans Fedow configure sur le lieu, on ne touche a rien (aucun appel reseau).
    / Without Fedow on the venue, nothing is touched (no network call)."""
    from AuthBillet.models import Wallet
    from Administration.management.commands.demo_data_v2 import (
        aligner_wallet_user_sur_fedow,
    )

    tenant = carte_client_avec_wallet_local["tenant"]
    carte = carte_client_avec_wallet_local["carte"]
    wallet_local = carte_client_avec_wallet_local["wallet_local"]

    with tenant_context(tenant):
        with mock.patch(f"{MODULE_SEED}.FedowConfig") as config_mock:
            config_mock.get_solo.return_value.can_fedow.return_value = False
            with mock.patch(f"{MODULE_SEED}.FedowAPI") as api_mock:
                a_aligne = aligner_wallet_user_sur_fedow(carte)

        assert a_aligne is False
        assert not api_mock.called, "FedowAPI ne doit pas etre instancie sans Fedow configure."
        carte.refresh_from_db()
        assert str(carte.user.wallet.uuid) == str(wallet_local.uuid)
        assert Wallet.objects.filter(uuid=wallet_local.uuid).exists()


def test_aligner_migre_le_solde_meme_si_la_liaison_de_carte_echoue(
    carte_client_avec_wallet_local, fedow_configure
):
    """Fedow refuse la liaison de la carte : le solde doit MIGRER quand meme.
    / Fedow refuses the card link: the balance must still migrate.

    Fedow n'accepte que des cartes libres (son serializer filtre sur `user__isnull=True`).
    Relancer le seed sur une carte deja liee renvoie donc 400 : c'est l'etat attendu au
    second passage, pas une anomalie. Si cet echec interrompait la fonction, le user
    pointerait son wallet Fedow pendant que son solde resterait sur le wallet local
    orphelin — soit zero au point de vente, sans le moindre message.
    / If that failure aborted the function, the user would point at their Fedow wallet while
    the balance stayed on the orphaned local one: zero at the POS, silently.
    """
    from AuthBillet.models import Wallet
    from fedow_core.models import Token
    from fedow_core.services import WalletService
    from Administration.management.commands.demo_data_v2 import (
        aligner_wallet_user_sur_fedow,
    )

    tenant = carte_client_avec_wallet_local["tenant"]
    carte = carte_client_avec_wallet_local["carte"]
    user = carte_client_avec_wallet_local["user"]
    wallet_local = carte_client_avec_wallet_local["wallet_local"]
    asset = carte_client_avec_wallet_local["asset"]

    with tenant_context(tenant):
        wallet_du_user_chez_fedow = Wallet.objects.create(
            uuid=uuid_module.uuid4(), origin=tenant, name=f"{TEST_PREFIX} fedow"
        )
        api = _fabriquer_fedow_api_mock(tenant, user, wallet_du_user_chez_fedow)
        # Fedow refuse la liaison, comme au second passage du seed.
        # / Fedow refuses the link, as on the seed's second pass.
        api.NFCcard.linkwallet_card_number.side_effect = Exception(
            "linkwallet_card_number : 400 {'card_number': ['Object does not exist']}"
        )

        with mock.patch(f"{MODULE_SEED}.FedowAPI", return_value=api):
            # La fonction ne doit PAS remonter l'echec : le seed ne s'arrete pas la.
            # / The function must NOT propagate the failure: the seed does not stop here.
            a_aligne = aligner_wallet_user_sur_fedow(carte)

        assert a_aligne is True

        # Le solde a bien migre malgre l'echec de liaison.
        # / The balance migrated despite the link failure.
        assert WalletService.obtenir_solde(wallet_du_user_chez_fedow, asset) == 1500
        assert not Token.objects.filter(wallet__uuid=wallet_local.uuid).exists()
        assert not Wallet.objects.filter(uuid=wallet_local.uuid).exists()
        carte.refresh_from_db()
        assert str(carte.user.wallet.uuid) == str(wallet_du_user_chez_fedow.uuid)
