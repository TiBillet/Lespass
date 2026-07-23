"""
tests/pytest/test_fedow_solde_depensable.py
Le calcul du solde depensable dans un lieu (Fedow legacy).
/ The spendable-balance computation for a venue (legacy Fedow).

LOCALISATION : tests/pytest/test_fedow_solde_depensable.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
`WalletFedow.get_total_fiducial_and_all_federated_token`
(fedow_connect/fedow_api.py) repond a la question « combien cette personne
peut-elle depenser ICI ? ». Elle additionne trois choses, et une seule
d'entre elles est evidente :

1. le FED du reseau, depensable partout ;
2. la monnaie locale dont CE lieu est a l'origine ;
3. la monnaie locale d'un AUTRE lieu, mais que ce lieu a acceptee — la
   federation, materialisee par `AssetFedowPublic.federated_with`.

Ce que la fonction ne doit surtout PAS compter : la monnaie d'un autre
collectif qui n'a pas ete federee ici. C'est la frontiere economique entre
collectifs ; l'effacer laisserait un adherent depenser chez A l'argent qu'il a
verse a B.

/ This function answers "how much can this person spend HERE?". It sums the
network FED, this venue's own local currency, and another venue's currency when
federated here. It must never count a non-federated currency: that is the
economic boundary between collectives.

Les monnaies non fiduciaires (cadeau, temps, fidelite) n'entrent jamais dans ce
total : elles ne sont pas adossees a l'euro.
/ Non-fiduciary currencies never enter this total.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_fedow_solde_depensable.py -v
"""

import uuid as uuid_module
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from Customers.models import Client as TenantClient
from fedow_connect.fedow_api import WalletFedow
from fedow_public.models import AssetFedowPublic

pytestmark = pytest.mark.django_db

# Prefixe pour reconnaitre et nettoyer les donnees de ce fichier.
# La base de dev est partagee et sans rollback.
# / Prefix to recognize and clean this file's data. Shared dev DB, no rollback.
PREFIXE_DE_TEST = 'TEST_depensable'

# L'identifiant du lieu courant, tel que le Fedow distant le connait. La
# fonction compare `token['asset']['place_origin']['uuid']` a cette valeur pour
# savoir si la monnaie vient d'ici.
# / The current venue's id as the remote Fedow knows it.
UUID_DU_LIEU_COURANT = uuid_module.uuid4()


# ---------------------------------------------------------------------------
# Fixtures et utilitaires
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant():
    """Le tenant de developpement. / The development tenant."""
    return TenantClient.objects.get(schema_name="lespass")


@pytest.fixture
def portefeuille_fedow():
    """Le client Fedow, avec une configuration reduite a ce qu'il lit.

    `WalletFedow.__init__` ne fait que stocker sa configuration, et la fonction
    testee n'en lit qu'un seul champ : `fedow_place_uuid`. Un objet simple
    suffit donc, et evite de dependre de la FedowConfig du tenant — que les
    autres tests de la suite lisent.
    / WalletFedow.__init__ only stores its config, and the function under test
    reads a single field. A plain object avoids depending on the tenant's real
    FedowConfig, which other tests read.
    """
    return WalletFedow(
        fedow_config=SimpleNamespace(fedow_place_uuid=UUID_DU_LIEU_COURANT),
    )


@pytest.fixture
def wallet_origine(tenant):
    """Un wallet createur jetable pour les assets miroirs.
    / A throwaway origin wallet for the mirrored assets."""
    wallet = Wallet.objects.create(name=f'{PREFIXE_DE_TEST} origine')
    yield wallet
    with tenant_context(tenant):
        try:
            wallet.delete()
        except Exception:
            # Un asset peut proteger le wallet (FK PROTECT) : best effort.
            # / An asset may protect the wallet: best effort.
            pass


@pytest.fixture(autouse=True)
def _nettoyage_des_assets_miroirs(tenant):
    """Supprime les AssetFedowPublic fabriques par ce fichier.
    / Deletes the AssetFedowPublic rows built by this file.

    Le `tenant_context` est indispensable : `BaseBillet` porte des cles
    etrangeres vers `AssetFedowPublic` (`Configuration.fedow_reward_asset`,
    entre autres). Ces tables sont des TENANT_APPS, absentes du schema public,
    et le DELETE y leve `ProgrammingError` — ce qui laisse la connexion en
    transaction cassee et fait tomber tous les tests suivants de la suite, pas
    seulement ce teardown.
    / tenant_context is required: BaseBillet holds foreign keys to
    AssetFedowPublic, in TENANT_APPS tables missing from the public schema.
    A failing DELETE would break the connection for the rest of the suite.

    Voir tests/PIEGES.md 11.9 et 9.95.
    """
    yield
    with tenant_context(tenant):
        AssetFedowPublic.objects.filter(name__startswith=PREFIXE_DE_TEST).delete()


def _asset_miroir_federe_ici(tenant, wallet_origine, libelle):
    """Cree un asset miroir d'un AUTRE lieu, accepte par le tenant courant.

    C'est la situation d'une caisse sociale alimentaire portee par un
    collectif A, que le collectif B a accepte de prendre chez lui. Le lien est
    le M2M `federated_with`.
    / A currency owned by venue A that venue B accepted, linked by federated_with.
    """
    asset = AssetFedowPublic.objects.create(
        uuid=uuid_module.uuid4(),
        name=f'{PREFIXE_DE_TEST} {libelle}',
        currency_code='EUR',
        category=AssetFedowPublic.TOKEN_LOCAL_FIAT,
        origin=tenant,
        wallet_origin=wallet_origine,
    )
    asset.federated_with.add(tenant)
    return asset


def _token(valeur, categorie, asset_uuid=None, uuid_du_lieu_d_origine=None):
    """Fabrique un token tel que `WalletValidator` le renvoie apres validation.

    Le champ `uuid` est un OBJET UUID, pas une chaine : `AssetValidator.uuid`
    est un `UUIDField`, donc `validated_data` porte des UUID desérialisés. La
    fonction testee compare `token['asset']['uuid']` a des `asset.uuid` venus de
    la base — la comparaison ne marche qu'entre objets UUID. Un test qui
    passerait des chaines ne verrait jamais la federation fonctionner.
    / The uuid field is a UUID OBJECT, not a string: AssetValidator.uuid is a
    UUIDField, so validated_data carries deserialized UUIDs. The function
    compares them to asset.uuid from the DB, which only matches between UUID
    objects.

    On fabrique le dictionnaire A LA MAIN plutot que de faire passer un payload
    dans `WalletValidator` : son `validate()` CREE des lignes en base
    (`AssetFedowPublic`, `Wallet`) quand les uuid lui sont inconnus.
    / Built BY HAND: WalletValidator.validate() CREATES rows for unknown uuids.
    """
    return {
        "value": valeur,
        "asset_category": categorie,
        "asset": {
            "uuid": asset_uuid or uuid_module.uuid4(),
            "place_origin": (
                {"uuid": uuid_du_lieu_d_origine} if uuid_du_lieu_d_origine else None
            ),
        },
    }


def _reponse_du_fedow(tokens):
    """Enveloppe une liste de tokens comme le fait le serializer de wallet.
    / Wraps a token list the way the wallet serializer does."""
    reponse = MagicMock()
    reponse.validated_data = {"tokens": tokens}
    return reponse


def _calculer(portefeuille_fedow, tenant, tokens, use_cache=True):
    """Lance le calcul avec un Fedow distant simule.

    Le `tenant_context` est indispensable : la fonction lit `connection.tenant`
    pour savoir quelles monnaies d'autres lieux sont acceptees ici. Hors
    contexte, elle tomberait sur le schema public ou sur un FakeTenant.
    / tenant_context is required: the function reads connection.tenant to know
    which other venues' currencies are accepted here.
    """
    with (
        tenant_context(tenant),
        patch.object(
            WalletFedow, 'cached_retrieve_by_signature',
            return_value=_reponse_du_fedow(tokens),
        ),
        patch.object(
            WalletFedow, 'retrieve_by_signature',
            return_value=_reponse_du_fedow(tokens),
        ),
    ):
        return portefeuille_fedow.get_total_fiducial_and_all_federated_token(
            user=MagicMock(),
            use_cache=use_cache,
        )


# ---------------------------------------------------------------------------
# Ce qui est depensable ici
# ---------------------------------------------------------------------------


def test_le_fed_du_reseau_est_depensable_partout(portefeuille_fedow, tenant):
    """La monnaie federee compte, sans condition de lieu.
    / The federated currency counts, with no venue condition."""
    total = _calculer(portefeuille_fedow, tenant, [_token(1200, 'FED')])

    assert total == 1200


def test_la_monnaie_du_lieu_courant_est_depensable(portefeuille_fedow, tenant):
    """Une monnaie locale dont CE lieu est a l'origine compte.
    / A local currency originating from THIS venue counts."""
    tokens = [
        _token(5000, 'TLF', uuid_du_lieu_d_origine=UUID_DU_LIEU_COURANT),
    ]

    total = _calculer(portefeuille_fedow, tenant, tokens)

    assert total == 5000


def test_la_monnaie_d_un_autre_lieu_federee_ici_est_depensable(
    portefeuille_fedow, tenant, wallet_origine,
):
    """Une caisse sociale alimentaire d'ailleurs, acceptee ici, compte.

    C'est le cas d'usage de la federation : deux collectifs qui conviennent
    d'accepter la monnaie l'un de l'autre.
    / The federation use case: two collectives accepting each other's currency.
    """
    asset_federe = _asset_miroir_federe_ici(
        tenant, wallet_origine, 'Caisse sociale alimentaire',
    )
    tokens = [
        _token(
            3000, 'TLF',
            asset_uuid=asset_federe.uuid,
            uuid_du_lieu_d_origine=uuid_module.uuid4(),  # un autre lieu
        ),
    ]

    total = _calculer(portefeuille_fedow, tenant, tokens)

    assert total == 3000


def test_les_trois_sources_s_additionnent(
    portefeuille_fedow, tenant, wallet_origine,
):
    """FED, monnaie du lieu et monnaie federee se cumulent exactement.
    / FED, own currency and federated currency add up exactly."""
    asset_federe = _asset_miroir_federe_ici(
        tenant, wallet_origine, 'Caisse sociale cumul',
    )
    tokens = [
        _token(1200, 'FED'),
        _token(5000, 'TLF', uuid_du_lieu_d_origine=UUID_DU_LIEU_COURANT),
        _token(
            3000, 'TLF',
            asset_uuid=asset_federe.uuid,
            uuid_du_lieu_d_origine=uuid_module.uuid4(),
        ),
    ]

    total = _calculer(portefeuille_fedow, tenant, tokens)

    assert total == 9200


# ---------------------------------------------------------------------------
# Ce qui n'est PAS depensable ici
# ---------------------------------------------------------------------------


def test_la_monnaie_d_un_autre_lieu_non_federee_n_est_pas_depensable(
    portefeuille_fedow, tenant, wallet_origine,
):
    """La frontiere entre collectifs : sans federation, la monnaie ne compte pas.

    L'adherent la possede toujours, et elle s'affiche sur sa page de solde — mais
    grisee. La compter ici laisserait depenser chez un collectif l'argent verse
    a un autre.
    / The boundary between collectives: without federation the currency does not
    count. Counting it would let someone spend at venue A the money paid to B.
    """
    asset_non_federe = AssetFedowPublic.objects.create(
        uuid=uuid_module.uuid4(),
        name=f'{PREFIXE_DE_TEST} Monnaie non federee',
        currency_code='EUR',
        category=AssetFedowPublic.TOKEN_LOCAL_FIAT,
        origin=tenant,
        wallet_origin=wallet_origine,
    )
    # Volontairement : aucun appel a federated_with.add(tenant).
    # / Deliberately: no federated_with.add(tenant) call.
    tokens = [
        _token(
            3000, 'TLF',
            asset_uuid=asset_non_federe.uuid,
            uuid_du_lieu_d_origine=uuid_module.uuid4(),
        ),
    ]

    total = _calculer(portefeuille_fedow, tenant, tokens)

    assert total == 0


@pytest.mark.parametrize("categorie_non_fiduciaire", ['TNF', 'TIM', 'FID'])
def test_les_monnaies_non_fiduciaires_ne_sont_jamais_comptees(
    portefeuille_fedow, tenant, categorie_non_fiduciaire,
):
    """Cadeau, temps et fidelite n'entrent pas dans un solde en euros.

    Elles ne sont pas adossees a l'euro : les additionner a du fiduciaire
    donnerait un montant qui ne veut rien dire.
    / They are not euro-backed: summing them with fiduciary money would produce
    a meaningless amount.
    """
    tokens = [_token(9999, categorie_non_fiduciaire)]

    total = _calculer(portefeuille_fedow, tenant, tokens)

    assert total == 0


def test_un_portefeuille_vide_vaut_zero(portefeuille_fedow, tenant):
    """Aucun token : total nul, et surtout pas d'erreur.
    / No token: zero total, and above all no error."""
    total = _calculer(portefeuille_fedow, tenant, [])

    assert total == 0


# ---------------------------------------------------------------------------
# Lecture fraiche ou lecture en cache
# ---------------------------------------------------------------------------


def test_la_lecture_sans_cache_interroge_le_fedow_directement(
    portefeuille_fedow, tenant,
):
    """`use_cache=False` court-circuite le cache de dix secondes.

    Le solde affiche peut vieillir de quelques secondes sans dommage, mais
    celui qui va servir a payer doit etre frais : un cache de dix secondes
    suffirait a laisser passer une depense deja faite ailleurs.
    / A displayed balance may age a few seconds; one about to be spent must be
    fresh, or a ten-second cache could let a double spend through.
    """
    tokens = [_token(1200, 'FED')]

    with (
        tenant_context(tenant),
        patch.object(
            WalletFedow, 'cached_retrieve_by_signature',
            return_value=_reponse_du_fedow(tokens),
        ) as lecture_en_cache,
        patch.object(
            WalletFedow, 'retrieve_by_signature',
            return_value=_reponse_du_fedow(tokens),
        ) as lecture_fraiche,
    ):
        portefeuille_fedow.get_total_fiducial_and_all_federated_token(
            user=MagicMock(),
            use_cache=False,
        )

    lecture_fraiche.assert_called_once()
    lecture_en_cache.assert_not_called()


def test_la_lecture_par_defaut_passe_par_le_cache(portefeuille_fedow, tenant):
    """Sans precision, l'affichage courant se contente du cache.
    / By default the plain display is happy with the cache."""
    tokens = [_token(1200, 'FED')]

    with (
        tenant_context(tenant),
        patch.object(
            WalletFedow, 'cached_retrieve_by_signature',
            return_value=_reponse_du_fedow(tokens),
        ) as lecture_en_cache,
        patch.object(
            WalletFedow, 'retrieve_by_signature',
            return_value=_reponse_du_fedow(tokens),
        ) as lecture_fraiche,
    ):
        portefeuille_fedow.get_total_fiducial_and_all_federated_token(
            user=MagicMock(),
        )

    lecture_en_cache.assert_called_once()
    lecture_fraiche.assert_not_called()
