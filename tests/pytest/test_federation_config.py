"""
Tests de la logique d'options de fédération
(seo.services.appliquer_options_federation).
/ Tests for the federation display-options logic.

LOCALISATION : tests/pytest/test_federation_config.py
Voir SESSIONS/FEDERATION/04-federation-config-design.md.
"""


def _explorer_data_exemple():
    """Jeu explorer minimal : 3 points (3 tenants), 3 tenants."""
    return {
        "points": [
            {"pa_id": 1, "tenant_id": "uuid-B", "tenant_organisation": "Beta",
             "events_futurs": [{"datetime_iso": "2026-07-01T20:00:00+00:00"}],
             "events_futurs_count_total": 1},
            {"pa_id": 2, "tenant_id": "uuid-A", "tenant_organisation": "Alpha",
             "events_futurs": [], "events_futurs_count_total": 0},
            {"pa_id": 3, "tenant_id": "uuid-C", "tenant_organisation": "Gamma",
             "events_futurs": [{"datetime_iso": "2026-06-15T20:00:00+00:00"}],
             "events_futurs_count_total": 3},
        ],
        "tenants": [
            {"tenant_id": "uuid-B", "name": "Beta", "event_count": 1},
            {"tenant_id": "uuid-A", "name": "Alpha", "event_count": 0},
            {"tenant_id": "uuid-C", "name": "Gamma", "event_count": 3},
        ],
    }


def test_filtre_event_only_retire_les_lieux_sans_event():
    from seo.services import appliquer_options_federation
    result = appliquer_options_federation(
        _explorer_data_exemple(),
        afficher_seulement_avec_event=True,
        tri_des_lieux="alpha",
    )
    assert {p["pa_id"] for p in result["points"]} == {1, 3}
    assert {t["tenant_id"] for t in result["tenants"]} == {"uuid-B", "uuid-C"}


def test_pas_de_filtre_event_garde_tout():
    from seo.services import appliquer_options_federation
    result = appliquer_options_federation(
        _explorer_data_exemple(),
        afficher_seulement_avec_event=False,
        tri_des_lieux="alpha",
    )
    assert len(result["points"]) == 3
    assert len(result["tenants"]) == 3


def test_tri_alphabetique_ordonne_par_organisation():
    from seo.services import appliquer_options_federation
    result = appliquer_options_federation(
        _explorer_data_exemple(),
        afficher_seulement_avec_event=False,
        tri_des_lieux="alpha",
    )
    assert [p["tenant_organisation"] for p in result["points"]] == ["Alpha", "Beta", "Gamma"]


def test_tri_par_prochain_event_les_sans_event_a_la_fin():
    from seo.services import appliquer_options_federation
    result = appliquer_options_federation(
        _explorer_data_exemple(),
        afficher_seulement_avec_event=False,
        tri_des_lieux="events",
    )
    # point 3 (15 juin) avant point 1 (1 juil) ; point 2 (sans event) en dernier
    assert [p["pa_id"] for p in result["points"]] == [3, 1, 2]


# --- Option 1 : lieux sans adresse (point sans coordonnees injecte) ---


def _explorer_data_avec_tenant_sans_point():
    """1 point reel (uuid-A) + 1 tenant sans point (uuid-D = lieu sans adresse)."""
    return {
        "points": [
            {"pa_id": 1, "tenant_id": "uuid-A", "tenant_organisation": "Alpha",
             "events_futurs": [], "events_futurs_count_total": 0},
        ],
        "tenants": [
            {"tenant_id": "uuid-A", "name": "Alpha", "event_count": 0},
            {"tenant_id": "uuid-D", "name": "Delta", "domain": "d.test",
             "logo_url": None, "event_count": 2},
        ],
    }


def test_lieux_sans_adresse_injecte_un_point_sans_coords():
    from seo.services import appliquer_options_federation
    result = appliquer_options_federation(
        _explorer_data_avec_tenant_sans_point(),
        afficher_seulement_avec_event=False,
        tri_des_lieux="alpha",
        afficher_lieux_sans_adresse=True,
    )
    points_par_id = {p["pa_id"]: p for p in result["points"]}
    assert "addressless-uuid-D" in points_par_id
    point_d = points_par_id["addressless-uuid-D"]
    assert point_d["latitude"] is None
    assert point_d["longitude"] is None
    assert point_d["is_addressless"] is True
    assert point_d["tenant_id"] == "uuid-D"
    assert point_d["tenant_organisation"] == "Delta"


def test_lieux_sans_adresse_desactive_n_injecte_rien():
    from seo.services import appliquer_options_federation
    result = appliquer_options_federation(
        _explorer_data_avec_tenant_sans_point(),
        afficher_seulement_avec_event=False,
        tri_des_lieux="alpha",
        afficher_lieux_sans_adresse=False,
    )
    assert [p["pa_id"] for p in result["points"]] == [1]  # aucun point injecte


def test_lieux_sans_adresse_respecte_le_filtre_event():
    """Un tenant sans point ET sans event futur ne doit pas apparaitre si filtre event."""
    from seo.services import appliquer_options_federation
    data = {
        "points": [],
        "tenants": [
            {"tenant_id": "uuid-E", "name": "Echo", "event_count": 0},
        ],
    }
    result = appliquer_options_federation(
        data,
        afficher_seulement_avec_event=True,
        tri_des_lieux="alpha",
        afficher_lieux_sans_adresse=True,
    )
    assert result["points"] == []
