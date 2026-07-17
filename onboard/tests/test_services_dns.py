"""
Tests unitaires de `dns_suffixes_disponibles` : la source unique des suffixes de
domaine proposes a la creation d'un tenant, derivee de l'environnement.
/ Unit tests for `dns_suffixes_disponibles`: the single source of DNS suffixes
offered at tenant creation, derived from the environment.

LOCALISATION: onboard/tests/test_services_dns.py

Ces tests n'ont PAS besoin de la base : ils patchent seulement os.environ.
/ These tests need NO database: they only patch os.environ.
"""

import pytest

from onboard.services import dns_suffixes_disponibles


pytestmark = pytest.mark.onboard


def test_domain_seul_donne_un_choix(monkeypatch):
    """`DOMAIN` sans `ADDITIONAL_DOMAINS` -> un seul suffixe."""
    monkeypatch.setenv("DOMAIN", "example.org")
    monkeypatch.delenv("ADDITIONAL_DOMAINS", raising=False)
    assert dns_suffixes_disponibles() == ["example.org"]


def test_domain_puis_additional_dans_l_ordre(monkeypatch):
    """`DOMAIN` en premier, puis chaque `ADDITIONAL_DOMAINS` dans l'ordre saisi."""
    monkeypatch.setenv("DOMAIN", "example.org")
    monkeypatch.setenv("ADDITIONAL_DOMAINS", "a.org,b.org")
    assert dns_suffixes_disponibles() == ["example.org", "a.org", "b.org"]


def test_doublons_retires(monkeypatch):
    """Un domaine present dans DOMAIN et ADDITIONAL_DOMAINS n'apparait qu'une fois."""
    monkeypatch.setenv("DOMAIN", "example.org")
    monkeypatch.setenv("ADDITIONAL_DOMAINS", "example.org,b.org")
    assert dns_suffixes_disponibles() == ["example.org", "b.org"]


def test_espaces_ignores(monkeypatch):
    """Les espaces autour des virgules sont nettoyes."""
    monkeypatch.setenv("DOMAIN", "example.org")
    monkeypatch.setenv("ADDITIONAL_DOMAINS", " a.org , b.org ")
    assert dns_suffixes_disponibles() == ["example.org", "a.org", "b.org"]


def test_coop_remonte_en_tete_meme_dans_additional(monkeypatch):
    """
    Feedback mainteneur 2026-07-17 : `tibillet.coop` doit etre le choix par
    defaut (1er de la liste) meme s'il est declare dans ADDITIONAL_DOMAINS et
    non dans DOMAIN.
    / `tibillet.coop` must be the default choice even when declared in
    ADDITIONAL_DOMAINS rather than DOMAIN.
    """
    monkeypatch.setenv("DOMAIN", "tibillet.re")
    monkeypatch.setenv("ADDITIONAL_DOMAINS", "tibillet.coop,domainbis.org")
    suffixes = dns_suffixes_disponibles()
    assert suffixes[0] == "tibillet.coop"
    assert suffixes == ["tibillet.coop", "tibillet.re", "domainbis.org"]


def test_priorite_coop_avant_localhost(monkeypatch):
    """Si coop ET localhost sont presents, coop passe avant localhost."""
    monkeypatch.setenv("DOMAIN", "tibillet.localhost")
    monkeypatch.setenv("ADDITIONAL_DOMAINS", "tibillet.coop")
    suffixes = dns_suffixes_disponibles()
    assert suffixes[0] == "tibillet.coop"
    assert suffixes[1] == "tibillet.localhost"


def test_repli_si_env_vide(monkeypatch):
    """Environnement vide -> repli minimal non vide sur 'tibillet.localhost'."""
    monkeypatch.delenv("DOMAIN", raising=False)
    monkeypatch.delenv("ADDITIONAL_DOMAINS", raising=False)
    assert dns_suffixes_disponibles() == ["tibillet.localhost"]
