"""
Tests unitaires pour le helper TiBillet/seo_indexing.py
/ Unit tests for the TiBillet/seo_indexing.py helper.

LOCALISATION : tests/pytest/test_seo_indexing.py

Voir SESSIONS/SEO/CHANTIER-01-noindex-dev.md pour la regle metier complete.

On teste les 3 flags d'environnement (DEBUG, TEST, DEMO), le cas "tous
les flags a 0 -> indexable", et le cas STRIPE_TEST qui ne desindexe pas.

/ We test the 3 env flags, the "all flags off -> indexable" case, and
that STRIPE_TEST does not de-index.
"""

import pytest

from TiBillet.seo_indexing import should_noindex


@pytest.fixture
def env_clean(monkeypatch):
    """
    Force les 4 flags a "0" pour isoler le cas teste.
    / Force the 4 flags to "0" to isolate the test case.
    """
    monkeypatch.setenv("DEBUG", "0")
    monkeypatch.setenv("TEST", "0")
    monkeypatch.setenv("DEMO", "0")
    monkeypatch.setenv("STRIPE_TEST", "0")


@pytest.mark.parametrize(
    "flag_a_activer",
    ["DEBUG", "TEST", "DEMO"],
)
def test_should_noindex_quand_un_flag_est_a_1(env_clean, monkeypatch, flag_a_activer):
    """
    Chaque flag pris isolement (les autres a "0") doit declencher
    le noindex. Parametrise pour ne pas dupliquer le meme test.
    / Each flag in isolation (the others at "0") must trigger noindex.
    """
    monkeypatch.setenv(flag_a_activer, "1")

    assert should_noindex() is True


def test_stripe_test_ne_desindexe_pas(env_clean, monkeypatch):
    """
    `STRIPE_TEST=1` seul ne desindexe pas : le mode de paiement ne dit
    rien de l'environnement.
    / `STRIPE_TEST=1` alone must not de-index.
    """
    monkeypatch.setenv("STRIPE_TEST", "1")

    assert should_noindex() is False


def test_should_indexer_quand_tous_les_flags_sont_a_zero(env_clean):
    """Tous les flags a "0" -> indexable (cas instance prod)."""
    assert should_noindex() is False
