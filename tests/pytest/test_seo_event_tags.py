"""
Tests unitaires pour get_event_tags_for_tenants (seo/services.py)
/ Unit tests for get_event_tags_for_tenants.

LOCALISATION : tests/pytest/test_seo_event_tags.py
Voir SESSIONS/SEO/CHANTIER-06-explorer-ux-pills-tags.md §4.1.
"""

from unittest.mock import MagicMock, patch


def test_get_event_tags_for_tenants_renvoie_dict_vide_pour_liste_vide():
    """Liste vide -> dict vide, pas d'appel DB."""
    from seo.services import get_event_tags_for_tenants
    assert get_event_tags_for_tenants([]) == {}


def test_get_event_tags_for_tenants_construit_dict_par_event_uuid():
    """
    Pour chaque event_id du JOIN, le dict contient une liste de tags.
    / For each event_id in the JOIN, the dict has a list of tags.
    """
    from seo.services import get_event_tags_for_tenants

    fake_rows = [
        ("event-uuid-A", "jazz", "Jazz", "#0dcaf0"),
        ("event-uuid-A", "concert", "Concert", "#ff5722"),
        ("event-uuid-B", "festival", "Festival", "#4caf50"),
    ]
    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = fake_rows
    fake_cursor.__enter__.return_value = fake_cursor
    fake_cursor.__exit__.return_value = False

    with patch("seo.services.connection") as mock_conn:
        mock_conn.cursor.return_value = fake_cursor
        result = get_event_tags_for_tenants([("uuid-A", "schema_a")])

    assert "event-uuid-A" in result
    assert "event-uuid-B" in result
    assert len(result["event-uuid-A"]) == 2
    assert len(result["event-uuid-B"]) == 1
    tag_slugs_a = {t["slug"] for t in result["event-uuid-A"]}
    assert tag_slugs_a == {"jazz", "concert"}
    assert result["event-uuid-B"][0]["color"] == "#4caf50"


def test_get_event_tags_for_tenants_event_sans_tag_pas_dans_dict():
    """
    Un event sans tag n'apparait pas dans le dict (JOIN strict).
    / An event without tag is absent from dict (strict JOIN).
    """
    from seo.services import get_event_tags_for_tenants

    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = []
    fake_cursor.__enter__.return_value = fake_cursor
    fake_cursor.__exit__.return_value = False

    with patch("seo.services.connection") as mock_conn:
        mock_conn.cursor.return_value = fake_cursor
        result = get_event_tags_for_tenants([("uuid-A", "schema_a")])

    assert result == {}
