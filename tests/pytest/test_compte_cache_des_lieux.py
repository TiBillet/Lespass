"""
Cache des lieux Fedow de la page compte : nom et logo par identifiant Fedow.
/ Account page Fedow venues cache: name and logo by Fedow place uuid.

LOCALISATION : tests/pytest/test_compte_cache_des_lieux.py

Le cache est partage par toute l'instance (schema public). Sans cela, chaque
lieu avait sa copie, et un visiteur sur deux attendait le parcours de tous les
lieux (6 s en prod) en ouvrant /my_account/.

Le cache memcached n'est pas annule a la fin d'un test : chaque test remet la
cle dans l'etat ou il l'a trouvee.
/ Memcached is not rolled back: each test restores the key.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.template.loader import render_to_string
from django_tenants.utils import schema_context, tenant_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def cache_des_lieux():
    """
    Rend une fonction qui pose une valeur dans le cache des lieux, puis restaure.
    / Returns a function that sets the venues cache, then restores it.
    """
    from BaseBillet.views import CLE_CACHE_DES_LIEUX_FEDOW

    with schema_context("public"):
        valeur_d_origine = cache.get(CLE_CACHE_DES_LIEUX_FEDOW)

    def poser(valeur):
        with schema_context("public"):
            if valeur is None:
                cache.delete(CLE_CACHE_DES_LIEUX_FEDOW)
            else:
                cache.set(CLE_CACHE_DES_LIEUX_FEDOW, valeur, 60)

    yield poser

    with schema_context("public"):
        if valeur_d_origine is None:
            cache.delete(CLE_CACHE_DES_LIEUX_FEDOW)
        else:
            cache.set(CLE_CACHE_DES_LIEUX_FEDOW, valeur_d_origine, 60)


def test_le_cache_construit_est_partage_par_tous_les_lieux(tenant, cache_des_lieux):
    """
    Construit depuis un lieu, le cache se lit depuis un autre lieu. Il ne contient
    que des textes, avec des cles en str, et saute les lieux sans identifiant Fedow.
    / Built from one venue, readable from another. Plain strings, str keys.
    """
    from BaseBillet.views import (
        construire_le_cache_des_lieux_fedow,
        lire_le_cache_des_lieux_fedow,
    )
    from Customers.models import Client
    from fedow_connect.models import FedowConfig

    cache_des_lieux(None)
    with tenant_context(tenant):
        infos_construites = construire_le_cache_des_lieux_fedow()
        uuid_fedow_du_lieu = FedowConfig.get_solo().fedow_place_uuid

    autre_lieu = (
        Client.objects.filter(categorie=Client.SALLE_SPECTACLE)
        .exclude(pk=tenant.pk)
        .first()
    )
    with tenant_context(autre_lieu):
        infos_lues = lire_le_cache_des_lieux_fedow()

    assert infos_lues == infos_construites
    assert uuid_fedow_du_lieu is not None, "Le lieu dev doit etre relie a Fedow."
    assert str(uuid_fedow_du_lieu) in infos_lues
    assert "None" not in infos_lues
    for infos in infos_lues.values():
        assert set(infos) == {"organisation", "logo_url"}
        assert infos["logo_url"] is None or isinstance(infos["logo_url"], str)


def test_un_cache_chaud_ne_parcourt_aucun_lieu(tenant, cache_des_lieux):
    """
    La recherche accepte un UUID (ce que rend le validateur Fedow) comme une str.
    / Lookup accepts a UUID object as well as a str.
    """
    from BaseBillet.views import MyAccount

    uuid_du_lieu = uuid.uuid4()
    infos = {"organisation": "La Filature", "logo_url": "/media/logo.png"}
    cache_des_lieux({str(uuid_du_lieu): infos})

    with (
        tenant_context(tenant),
        patch(
            "BaseBillet.views.construire_le_cache_des_lieux_fedow",
            side_effect=AssertionError("parcours de tous les lieux"),
        ),
    ):
        assert MyAccount.get_place_cached_info(uuid_du_lieu) == infos
        assert MyAccount.get_place_cached_info(str(uuid_du_lieu)) == infos
        assert MyAccount.get_place_cached_info(uuid.uuid4()) is None


def test_un_cache_absent_est_reconstruit_une_seule_fois(tenant, cache_des_lieux):
    from BaseBillet.views import MyAccount, construire_le_cache_des_lieux_fedow

    cache_des_lieux(None)
    with (
        tenant_context(tenant),
        patch(
            "BaseBillet.views.construire_le_cache_des_lieux_fedow",
            wraps=construire_le_cache_des_lieux_fedow,
        ) as construction,
    ):
        MyAccount.get_place_cached_info(uuid.uuid4())
        MyAccount.get_place_cached_info(uuid.uuid4())

    assert construction.call_count == 1


def test_le_recalcul_seo_remplit_le_cache_des_lieux():
    """
    Le beat 4 h (refresh_seo_cache) remplit le cache : aucun visiteur n'attend.
    / The 4 h beat fills the cache: no visitor waits.
    """
    from seo.tasks import refresh_seo_cache

    with (
        patch("seo.services.set_memcached_l1"),
        patch("BaseBillet.views.construire_le_cache_des_lieux_fedow") as construction,
    ):
        refresh_seo_cache()

    construction.assert_called_once_with()


def test_les_jetons_recoivent_le_nom_et_le_logo_des_lieux(tenant, cache_des_lieux):
    from BaseBillet.models import Configuration
    from BaseBillet.views import get_distant_fedow_tokens

    uuid_origine = uuid.uuid4()
    uuid_federe = uuid.uuid4()
    cache_des_lieux(
        {
            str(uuid_origine): {"organisation": "Origine", "logo_url": "/media/o.png"},
            str(uuid_federe): {"organisation": "Voisin", "logo_url": None},
        }
    )
    jeton = {
        "asset_category": "TLF",
        "asset": {
            "place_origin": {"uuid": uuid_origine},
            "place_uuid_federated_with": [uuid_federe],
            "is_stripe_primary": False,
        },
    }
    faux_fedow = MagicMock()
    faux_fedow.wallet.cached_retrieve_by_signature.return_value.validated_data = {
        "tokens": [jeton]
    }

    with (
        tenant_context(tenant),
        patch("BaseBillet.views.FedowAPI", return_value=faux_fedow),
        patch("BaseBillet.views.lieu_en_moteur_legacy", return_value=True),
    ):
        jetons = get_distant_fedow_tokens(
            SimpleNamespace(user=MagicMock()), Configuration.get_solo()
        )

    assert jetons[0]["asset"]["logo_url"] == "/media/o.png"
    assert jetons[0]["asset"]["names_of_place_federated"] == ["Origine", "Voisin"]


@pytest.mark.parametrize("skin", ["V2", "classic"])
def test_la_table_des_jetons_affiche_le_logo_du_lieu(skin):
    jeton = {
        "name": "Monnaie locale",
        "value": 1000,
        "asset": {
            "logo_url": "/media/logo-du-lieu.png",
            "names_of_place_federated": ["La Filature"],
            "is_stripe_primary": False,
        },
    }
    html = render_to_string(
        f"pages/{skin}/vues/compte/partials/token_table.html",
        {"tokens": [jeton], "config": SimpleNamespace(organisation="La Filature")},
    )
    assert 'src="/media/logo-du-lieu.png"' in html


@pytest.mark.parametrize("skin", ["V2", "classic"])
def test_la_table_des_jetons_n_a_plus_de_colonne_derniere_transaction(skin):
    """
    Les monnaies locales n'ont pas de date de derniere transaction : la colonne
    affichait « None ». Elle est retiree.
    / Local currencies have no last-transaction date: the column is gone.
    """
    jeton_local = {
        "name": "Cadeau",
        "value": 500,
        "asset": {"names_of_place_federated": ["Lespass"], "is_stripe_primary": False},
        "is_local": True,
        "last_transaction_datetime": None,
    }
    html = render_to_string(
        f"pages/{skin}/vues/compte/partials/token_table.html",
        {"tokens": [jeton_local], "config": SimpleNamespace(organisation="Lespass")},
    )
    assert "Last transaction" not in html
    assert "Dernière transaction" not in html
    assert "None" not in html


def test_un_cache_vide_n_est_pas_un_cache_absent(tenant, cache_des_lieux):
    """
    Une instance sans lieu relie a Fedow donne un cache vide ({}). Il est valide :
    le reconstruire a chaque jeton referait le parcours de tous les lieux.
    / An empty cache ({}) is valid: rebuilding it per token would rescan all venues.
    """
    from BaseBillet.views import MyAccount

    cache_des_lieux({})
    with (
        tenant_context(tenant),
        patch(
            "BaseBillet.views.construire_le_cache_des_lieux_fedow",
            side_effect=AssertionError("parcours de tous les lieux"),
        ),
    ):
        assert MyAccount.get_place_cached_info(uuid.uuid4()) is None
