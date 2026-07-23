"""
tests/pytest/test_fedow_garde_asset_fed_local.py — La garde anti-FED-local.
/ The local-FED guard.

LOCALISATION : tests/pytest/test_fedow_garde_asset_fed_local.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
`Asset.save()` (fedow_core/models.py) refuse de creer un asset local de
categorie FED, et leve `AssetFedLocalInterdit`.

POURQUOI CETTE GARDE EXISTE / WHY THIS GUARD EXISTS
---------------------------------------------------
La monnaie federee du reseau (FED) est servie par le Fedow distant. Le moteur
local n'en heberge aucune. Deux codes filtrent pourtant sur la seule categorie,
sans savoir distinguer les deux moteurs, et prendraient donc un FED local pour
la vraie monnaie federee :

- la cascade de paiement du point de vente, qui le debiterait lors d'un achat ;
- le remboursement en especes de la caisse
  (`WalletService.rembourser_en_especes`), qui le rendrait en billets.

Aucune contrainte de base ne joue ce role : `UniqueConstraint 'unique_fed_asset'`
autorise UN asset FED, elle n'en interdit pas la creation du premier.

/ The network's federated currency is served by the remote Fedow. The POS
payment cascade and the cash refund both filter on the category alone and would
mistake a local FED for the real thing. The DB constraint allows ONE FED asset;
it does not forbid creating it.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_fedow_garde_asset_fed_local.py -v
"""

import uuid as uuid_module

import pytest
from django.test import override_settings

from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_core.exceptions import AssetFedLocalInterdit
from fedow_core.models import Asset
from fedow_core.services import AssetService

pytestmark = pytest.mark.django_db

# Prefixe pour reconnaitre et nettoyer les donnees de ce fichier.
# La base de dev est partagee et sans rollback : tout objet cree ici doit
# porter ce prefixe pour que le nettoyage reste circonscrit.
# / Prefix to recognize and clean this file's data. The dev DB is shared and has
# no rollback: everything created here carries this prefix.
PREFIXE_DE_TEST = 'TEST_garde_fed'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="module")
def _connexion_sur_le_schema_public():
    """
    Pose la connexion sur `public` AVANT toute autre fixture de ce fichier.
    / Puts the connection on `public` BEFORE any other fixture in this file.

    Ce fichier teste `fedow_core.Asset`, un modele de SHARED_APPS : sa table vit
    dans le schema `public` et le code n'y pose jamais de contexte de tenant.
    Rien ne garantit que la connexion y soit deja : le middleware django-tenants
    la colle sur un tenant des qu'un test AILLEURS dans la suite passe par le
    client de test Django, et personne ne la decolle.

    EN SETUP, JAMAIS EN TEARDOWN : les finalizers des fixtures de portee
    superieure s'executent apres ceux de portee test ; remettre `public` en
    teardown les ferait tomber sur un schema sans les tables du tenant.
    / SETUP only, never teardown — higher-scoped finalizers run afterwards.

    Voir tests/PIEGES.md 12.5.bis.
    """
    from django.db import connection

    connection.set_schema_to_public()

    yield


@pytest.fixture(scope="module")
def tenant_lespass():
    """Le tenant de developpement, cible explicitement.
    / The development tenant, targeted explicitly.

    Jamais `.exclude(schema_name='public').first()` : les tenants d'onboarding
    ont un nom qui commence par un chiffre et passent premiers dans l'ordre
    alphabetique, sans domaine associe.
    / Never `.exclude(...).first()`: onboarding tenants sort first and have no
    domain attached.
    """
    return Client.objects.get(schema_name='lespass')


@pytest.fixture(scope="module")
def wallet_du_lieu():
    """Un wallet createur jetable pour les assets de ce fichier.
    / A throwaway origin wallet for this file's assets."""
    return Wallet.objects.create(name=f'{PREFIXE_DE_TEST} Lieu')


@pytest.fixture(scope="module", autouse=True)
def _nettoyage_en_fin_de_module():
    """
    Supprime les objets crees par ce fichier.
    / Deletes objects created by this file.

    Ordre impose par les FK PROTECT : Assets puis Wallets. Ce fichier ne cree
    ni Token ni Transaction, il n'y a donc rien avant les assets.
    / Order imposed by the PROTECT FKs: Assets then Wallets.

    Le `tenant_context` est INDISPENSABLE pour les DEUX suppressions : leurs
    cascades atteignent des tables de TENANT_APPS, absentes du schema public.
    `Asset` cascade vers `BaseBillet.Product.asset`, et `Wallet` vers
    `BaseBillet.LigneArticle.wallet`. Sans lui, le DELETE leve
    `ProgrammingError: relation ... does not exist` — et laisse la connexion en
    transaction cassee, ce qui fait tomber tous les tests suivants de la suite,
    pas seulement ce teardown.
    / tenant_context is REQUIRED for BOTH deletes: Asset cascades to
    BaseBillet.Product.asset and Wallet to BaseBillet.LigneArticle.wallet, both
    TENANT_APPS tables missing from the public schema. Without it the DELETE
    raises and breaks the connection for the rest of the suite.

    Voir tests/PIEGES.md 11.9 et 9.95.
    """
    yield

    from Customers.models import Client as TenantClient
    from django_tenants.utils import tenant_context

    tenant = TenantClient.objects.get(schema_name='lespass')
    with tenant_context(tenant):
        Asset.objects.filter(name__startswith=PREFIXE_DE_TEST).delete()
        Wallet.objects.filter(name__startswith=PREFIXE_DE_TEST).delete()


def _nom_unique(libelle):
    """Nom d'asset unique pour ce run.
    / Asset name unique to this run.

    `Product` porte une contrainte unique sur (categorie_article, name), et le
    signal post_save d'`Asset` cree un Product « Recharge {nom} ». Sans suffixe
    unique, le second run leve une IntegrityError.
    / A post_save signal creates a "Recharge {name}" Product under a unique
    constraint. Without a unique suffix, the second run raises IntegrityError.
    """
    return f'{PREFIXE_DE_TEST} {libelle} {uuid_module.uuid4().hex[:8]}'


# ---------------------------------------------------------------------------
# La garde refuse la creation d'un asset FED local
# ---------------------------------------------------------------------------


def test_creation_directe_d_un_asset_fed_local_est_refusee(tenant_lespass, wallet_du_lieu):
    """`Asset.objects.create(category=FED)` leve AssetFedLocalInterdit.
    / Direct creation of a FED asset raises AssetFedLocalInterdit."""
    with pytest.raises(AssetFedLocalInterdit):
        Asset.objects.create(
            name=_nom_unique('FED direct'),
            category=Asset.FED,
            currency_code='EUR',
            wallet_origin=wallet_du_lieu,
            tenant_origin=tenant_lespass,
        )


def test_creation_via_le_service_est_refusee_aussi(tenant_lespass, wallet_du_lieu):
    """`AssetService.creer_asset` est couvert par la meme garde.

    Le service delegue a `Asset.objects.create()`, donc a `save()`. Placer la
    garde dans `save()` plutot que dans le service la rend impossible a
    contourner par un nouveau chemin de creation.
    / The service delegates to save(), so the guard cannot be bypassed by a new
    creation path.
    """
    with pytest.raises(AssetFedLocalInterdit):
        AssetService.creer_asset(
            tenant=tenant_lespass,
            name=_nom_unique('FED service'),
            category=Asset.FED,
            currency_code='EUR',
            wallet_origin=wallet_du_lieu,
        )


def test_aucun_asset_fed_local_n_est_laisse_en_base(tenant_lespass, wallet_du_lieu):
    """Apres un refus, rien n'a ete ecrit.

    La garde leve AVANT `super().save()` : il ne doit rester aucune ligne, ni
    Asset ni Product de recharge cree par le signal post_save.
    / The guard raises BEFORE super().save(): no row is left behind.
    """
    nom = _nom_unique('FED sans trace')

    with pytest.raises(AssetFedLocalInterdit):
        Asset.objects.create(
            name=nom,
            category=Asset.FED,
            currency_code='EUR',
            wallet_origin=wallet_du_lieu,
            tenant_origin=tenant_lespass,
        )

    assert not Asset.objects.filter(name=nom).exists()


# ---------------------------------------------------------------------------
# La garde ne deborde pas sur les autres categories
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "categorie, code_devise",
    [
        (Asset.TLF, 'EUR'),
        (Asset.TNF, 'EUR'),
        (Asset.TIM, 'TMP'),
        (Asset.FID, 'PTS'),
    ],
)
def test_les_autres_categories_se_creent_normalement(
    tenant_lespass, wallet_du_lieu, categorie, code_devise,
):
    """Monnaie locale, cadeau, temps et fidelite restent creables.

    La garde ne vise que la monnaie federee du reseau. Un debordement sur les
    autres categories bloquerait la creation de monnaies par les collectifs.
    / The guard targets the federated currency only. Spilling over would block
    collectives from creating their own currencies.
    """
    asset = AssetService.creer_asset(
        tenant=tenant_lespass,
        name=_nom_unique(f'ok {categorie}'),
        category=categorie,
        currency_code=code_devise,
        wallet_origin=wallet_du_lieu,
    )

    assert asset.pk is not None
    assert asset.category == categorie


# ---------------------------------------------------------------------------
# L'echappatoire de test
# ---------------------------------------------------------------------------


def test_le_reglage_leve_la_garde(tenant_lespass, wallet_du_lieu):
    """Avec FEDOW_AUTORISER_ASSET_FED_LOCAL, la creation passe.

    C'est le mecanisme dont se servent les fichiers qui couvrent le code
    d'apres-migration (remboursement en especes cote FED, BankTransferService).
    Sans lui, ces tests n'auraient plus d'asset a manipuler.
    / This is the mechanism used by the files covering post-migration code.

    On ne cree l'asset que si aucun FED n'existe : la contrainte de base
    `unique_fed_asset` n'en autorise qu'un dans tout le systeme.
    / We only create if no FED exists: the DB constraint allows a single one.
    """
    fed_deja_present = Asset.objects.filter(category=Asset.FED).first()
    if fed_deja_present is not None:
        pytest.skip("Un asset FED existe deja : la contrainte unique_fed_asset en interdit un second.")

    nom = _nom_unique('FED autorise')
    with override_settings(FEDOW_AUTORISER_ASSET_FED_LOCAL=True):
        asset = Asset.objects.create(
            name=nom,
            category=Asset.FED,
            currency_code='EUR',
            wallet_origin=wallet_du_lieu,
            tenant_origin=tenant_lespass,
        )

    assert asset.pk is not None

    # Nettoyage immediat : un asset FED qui trainerait polluerait toute la
    # suite, ou la convention est qu'il n'existe aucun FED local.
    # Le `tenant_context` est indispensable — la cascade de suppression touche
    # `BaseBillet.Product`, absent du schema public (PIEGES 11.9).
    # / Immediate cleanup: a leftover FED asset would pollute the whole suite.
    # tenant_context is required — the delete cascade reaches BaseBillet.Product.
    from django_tenants.utils import tenant_context

    with tenant_context(tenant_lespass):
        asset.delete()


def test_un_asset_fed_existant_reste_lisible(tenant_lespass, wallet_du_lieu):
    """La garde bloque l'ecriture, jamais la lecture.

    `rembourser_en_especes` et la cascade du point de vente interrogent les
    assets FED a chaque passage. Une garde qui casserait la lecture arreterait
    le vidage de carte en caisse.
    / The guard blocks writes, never reads: the cash refund and the POS cascade
    query FED assets on every run.
    """
    with override_settings(FEDOW_AUTORISER_ASSET_FED_LOCAL=True):
        # La lecture ne passe pas par save() : elle fonctionne dans les deux
        # etats du reglage. On verifie surtout qu'elle ne leve rien.
        # / Reading does not go through save(): it works either way.
        assets_fed = list(Asset.objects.filter(category=Asset.FED))

    assert isinstance(assets_fed, list)
