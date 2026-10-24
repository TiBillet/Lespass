"""
Tests du repli serveur MapTiler -> OSM France HOT quand MapTiler refuse les tuiles.
/ Tests of the server-side MapTiler -> OSM France HOT fallback.

LOCALISATION : tests/pytest/test_maptiler_repli_quota.py

Quand le quota est epuise, MapTiler repond 403/429 AVEC une image PNG valide :
le navigateur l'affiche, le JS ne voit aucune erreur. C'est donc le serveur qui
sonde MapTiler (TiBillet/maptiler.py) et expose une cle vide pendant 24 h.
/ When the quota is used up, MapTiler answers 403/429 WITH a valid PNG image:
the browser shows it, the JS sees no error. The server probes MapTiler and
exposes an empty key for 24 h.

Aucun appel reseau : requests.get est remplace par un faux.
/ No network call: requests.get is replaced by a fake.
"""

from types import SimpleNamespace
from unittest import mock

import pytest
import requests
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django_tenants.utils import schema_context

from TiBillet import maptiler
from TiBillet.maptiler import (
    CLE_CACHE_ETAT_MAPTILER,
    DUREE_CACHE_MAPTILER_KO,
    DUREE_CACHE_MAPTILER_OK,
    cle_maptiler_a_exposer,
)

CLE_DE_TEST = "MAcleDeTest123"


def _lire_etat_global():
    """Lit l'etat MapTiler dans le cache global. / Reads the global state."""
    with schema_context("public"):
        return cache.get(CLE_CACHE_ETAT_MAPTILER)


@pytest.fixture(autouse=True)
def cache_maptiler_vide():
    """
    Vide l'etat MapTiler avant et apres chaque test.
    / Clears the MapTiler state before and after each test.

    Le memcached de test est celui du serveur de dev : un « ko » oublie ici
    couperait MapTiler sur le serveur de dev pendant 24 h.
    / The test memcached is the dev server's: a leftover "ko" would cut MapTiler
    on the dev server for 24 h.
    """
    with schema_context("public"):
        cache.delete(CLE_CACHE_ETAT_MAPTILER)
    yield
    with schema_context("public"):
        cache.delete(CLE_CACHE_ETAT_MAPTILER)


def _fausse_reponse(code_http):
    """Reponse requests minimale. / Minimal requests response."""
    return SimpleNamespace(status_code=code_http, ok=code_http < 400)


@override_settings(MAPTILER_KEY=CLE_DE_TEST)
@pytest.mark.parametrize("code_http", [403, 429])
def test_maptiler_refuse_les_tuiles_donne_une_cle_vide(code_http):
    """
    MapTiler repond 403 ou 429 : la cle exposee est vide (-> OSM cote JS).
    / MapTiler answers 403 or 429: the exposed key is empty.
    """
    with mock.patch.object(
        maptiler.requests, "get", return_value=_fausse_reponse(code_http)
    ):
        assert cle_maptiler_a_exposer() == ""


@override_settings(MAPTILER_KEY=CLE_DE_TEST)
def test_maptiler_refuse_les_tuiles_retient_ko_pendant_24_heures():
    """
    Un refus est retenu « ko » pendant 24 h dans le cache.
    / A refusal is kept as "ko" for 24 h in the cache.
    """
    with mock.patch.object(maptiler.requests, "get", return_value=_fausse_reponse(403)):
        with mock.patch.object(maptiler.cache, "set") as faux_set:
            cle_maptiler_a_exposer()
    faux_set.assert_called_once_with(
        CLE_CACHE_ETAT_MAPTILER, "ko", DUREE_CACHE_MAPTILER_KO
    )
    assert DUREE_CACHE_MAPTILER_KO == 60 * 60 * 24


@override_settings(MAPTILER_KEY=CLE_DE_TEST)
def test_maptiler_ok_donne_la_cle_et_retient_ok_pendant_une_heure():
    """
    MapTiler repond 200 : la cle est exposee, « ok » est retenu 1 h.
    / MapTiler answers 200: the key is exposed, "ok" is kept 1 h.
    """
    with mock.patch.object(maptiler.requests, "get", return_value=_fausse_reponse(200)):
        with mock.patch.object(maptiler.cache, "set") as faux_set:
            cle_exposee = cle_maptiler_a_exposer()
    assert cle_exposee == CLE_DE_TEST
    faux_set.assert_called_once_with(
        CLE_CACHE_ETAT_MAPTILER, "ok", DUREE_CACHE_MAPTILER_OK
    )


@override_settings(MAPTILER_KEY=CLE_DE_TEST)
def test_reseau_en_panne_garde_la_cle_et_ne_retient_rien():
    """
    La sonde n'a pas de reponse : on garde MapTiler, rien n'est mis en cache.
    / The probe gets no answer: MapTiler is kept, nothing is cached.
    """
    with mock.patch.object(
        maptiler.requests, "get", side_effect=requests.ConnectTimeout("lent")
    ):
        assert cle_maptiler_a_exposer() == CLE_DE_TEST
    assert _lire_etat_global() is None


@override_settings(MAPTILER_KEY=CLE_DE_TEST)
def test_etat_en_cache_evite_une_nouvelle_sonde():
    """
    Une fois « ko » retenu, les appels suivants ne sondent plus MapTiler.
    / Once "ko" is kept, later calls no longer probe MapTiler.
    """
    with mock.patch.object(
        maptiler.requests, "get", return_value=_fausse_reponse(403)
    ) as faux_get:
        cle_maptiler_a_exposer()
        cle_maptiler_a_exposer()
        cle_maptiler_a_exposer()
    assert faux_get.call_count == 1


@pytest.mark.django_db
@override_settings(MAPTILER_KEY=CLE_DE_TEST)
def test_etat_maptiler_est_global_et_pas_par_tenant(tenant):
    """
    Le « ko » retenu depuis un lieu vaut pour tous les lieux et le ROOT.
    / The "ko" kept from one venue applies to every venue and to ROOT.

    Le cache du projet prefixe les cles par schema (django-tenants) : sans
    schema_context("public"), chaque lieu sonderait MapTiler pour lui seul.
    / The project cache prefixes keys by schema: without schema_context("public")
    each venue would probe MapTiler on its own.
    """
    from django_tenants.utils import tenant_context

    with mock.patch.object(maptiler.requests, "get", return_value=_fausse_reponse(403)):
        with tenant_context(tenant):
            assert connection.schema_name != "public"
            cle_maptiler_a_exposer()

    assert _lire_etat_global() == "ko"


@override_settings(MAPTILER_KEY="")
def test_sans_cle_aucune_sonde():
    """
    Sans cle configuree : cle vide, et MapTiler n'est jamais sonde.
    / No key configured: empty key, MapTiler is never probed.
    """
    with mock.patch.object(maptiler.requests, "get") as faux_get:
        assert cle_maptiler_a_exposer() == ""
    faux_get.assert_not_called()
