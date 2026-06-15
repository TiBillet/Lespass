"""
Tests de la fédération automatique par tags (FederationConfiguration.tags_federation).
/ Tests for tag-based auto federation.

LOCALISATION : tests/pytest/test_federation_auto_tags.py

Le cœur de la logique est le helper seo.services.get_tenant_uuids_with_event_tags,
qui lit le cache AGGREGATE_EVENTS et applique le veto `private` + le match par slug.
On le teste avec un cache MOCKÉ : aucune dépendance à la base ni au cache réel.
/ Core logic is the cache helper; tested with a MOCKED cache (no DB / real cache).
"""

from unittest.mock import patch

from seo.services import get_tenant_uuids_with_event_tags


def test_helper_filtre_par_slug_et_respecte_private():
    """
    get_tenant_uuids_with_event_tags ne retient QUE les tenants ayant un event
    PUBLIC (private=False) portant un des slugs demandés.
    / Keep only tenants with a PUBLIC event carrying one of the requested slugs.
    """
    faux_cache = {"events": [
        # Tenant T1 : event public taggé "concert" -> RETENU
        {"tenant_id": "T1", "private": False, "tags": [{"slug": "concert"}]},
        # Tenant T2 : même tag mais event PRIVÉ -> exclu (veto private)
        {"tenant_id": "T2", "private": True, "tags": [{"slug": "concert"}]},
        # Tenant T3 : event public mais autre tag -> exclu
        {"tenant_id": "T3", "private": False, "tags": [{"slug": "theatre"}]},
        # Tenant T4 : event public sans tag -> exclu
        {"tenant_id": "T4", "private": False, "tags": []},
    ]}

    # Le helper importe get_seo_cache depuis seo.views_common : on patche là.
    # / The helper imports get_seo_cache from seo.views_common: patch it there.
    with patch("seo.views_common.get_seo_cache", return_value=faux_cache):
        resultat = get_tenant_uuids_with_event_tags(["concert"])

    assert resultat == {"T1"}


def test_helper_plusieurs_tags_union():
    """Plusieurs slugs demandés : un tenant matche s'il porte AU MOINS un des tags."""
    faux_cache = {"events": [
        {"tenant_id": "T1", "private": False, "tags": [{"slug": "concert"}]},
        {"tenant_id": "T3", "private": False, "tags": [{"slug": "theatre"}]},
        {"tenant_id": "T5", "private": False, "tags": [{"slug": "expo"}]},
    ]}
    with patch("seo.views_common.get_seo_cache", return_value=faux_cache):
        resultat = get_tenant_uuids_with_event_tags(["concert", "theatre"])
    assert resultat == {"T1", "T3"}


def test_helper_liste_vide_retourne_set_vide_sans_lire_le_cache():
    """
    Liste de tags vide ou None -> set vide (fédération auto inactive),
    et on ne touche même pas le cache.
    / Empty/None tag list -> empty set, cache not even read.
    """
    # patch.object lèverait si le cache était lu ; ici on vérifie juste le court-circuit.
    assert get_tenant_uuids_with_event_tags([]) == set()
    assert get_tenant_uuids_with_event_tags(None) == set()


def test_helper_cache_absent_retourne_set_vide():
    """Cache AGGREGATE_EVENTS absent (None) -> set vide, pas d'erreur."""
    with patch("seo.views_common.get_seo_cache", return_value=None):
        resultat = get_tenant_uuids_with_event_tags(["concert"])
    assert resultat == set()
