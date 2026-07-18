"""
Tests unitaires pour les helpers AGGREGATE_POINTS (seo/services.py)
/ Unit tests for the AGGREGATE_POINTS helpers.

LOCALISATION : tests/pytest/test_seo_aggregate_points.py
Voir SESSIONS/SEO/CHANTIER-05-explorer-markers-per-pa.md.

Strategie : tests unitaires avec mocks. Les tests d'integration plus
realistes sont en Task 5 (smoke test refresh_seo_cache) et Task 10 (E2E).
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch


def test_get_postal_addresses_for_tenants_renvoie_dict_vide_pour_liste_vide():
    """Liste vide -> dict vide, pas d'appel DB."""
    from seo.services import get_postal_addresses_for_tenants
    assert get_postal_addresses_for_tenants([]) == {}


def test_get_postal_addresses_for_tenants_ignore_tenant_introuvable():
    """Client.DoesNotExist -> skip silencieusement."""
    from seo.services import get_postal_addresses_for_tenants
    from Customers.models import Client
    with patch.object(Client.objects, "get", side_effect=Client.DoesNotExist):
        result = get_postal_addresses_for_tenants([("uuid-introuvable", "schema-introuvable")])
    assert result == {}


def test_get_postal_addresses_for_tenants_construit_dict_correct():
    """Pour un tenant trouve, construit le dict avec tous les champs attendus."""
    from seo.services import get_postal_addresses_for_tenants

    fake_pa = MagicMock()
    fake_pa.pk = 42
    fake_pa.latitude = Decimal("48.8566")
    fake_pa.longitude = Decimal("2.3522")
    fake_pa.name = "Lieu test"
    fake_pa.street_address = "1 rue X"
    fake_pa.postal_code = "75001"
    fake_pa.address_locality = "Paris"
    fake_pa.address_country = "France"

    # Le mock rejoue la chaine du queryset : .exclude().exclude().order_by().
    # order_by("pk") est INDISPENSABLE cote code : sans tri explicite, PostgreSQL
    # rend les adresses dans un ordre arbitraire, et la carte vise alors une adresse
    # differente d'un rebuild du cache a l'autre.
    # / The mock replays the queryset chain, including the mandatory order_by("pk").
    fake_qs = MagicMock()
    fake_qs.exclude.return_value = fake_qs
    fake_qs.order_by.return_value = fake_qs
    fake_qs.__iter__ = lambda self: iter([fake_pa])

    fake_tenant = MagicMock()
    fake_tenant.schema_name = "fake_schema"

    with patch("Customers.models.Client.objects.get", return_value=fake_tenant), \
         patch("django_tenants.utils.tenant_context"), \
         patch("BaseBillet.models.PostalAddress.objects") as mock_objects:
        mock_objects.exclude.return_value = fake_qs
        result = get_postal_addresses_for_tenants([("uuid-A", "fake_schema")])

    assert "uuid-A" in result
    assert len(result["uuid-A"]) == 1
    pa_dict = result["uuid-A"][0]
    assert pa_dict["pa_id"] == 42
    assert pa_dict["latitude"] == 48.8566
    assert pa_dict["longitude"] == 2.3522
    assert pa_dict["name"] == "Lieu test"
    assert pa_dict["street_address"] == "1 rue X"
    assert pa_dict["postal_code"] == "75001"
    assert pa_dict["address_locality"] == "Paris"
    assert pa_dict["address_country"] == "France"


def test_build_aggregate_points_skip_tenants_pas_dans_configs():
    """
    Un tenant absent de configs_by_tenant est considere mort -> skip.
    / A tenant not in configs_by_tenant is dead -> skipped.
    """
    from seo.services import build_aggregate_points
    result = build_aggregate_points(
        [("uuid-mort", "schema-mort")],
        configs_by_tenant={},
        events_by_tenant={},
    )
    assert result == {"points": []}


def test_build_aggregate_points_limite_events_a_5_avec_count_total():
    """
    PA avec 12 events futurs -> popup contient 5, events_futurs_count_total=12.
    / PA with 12 future events -> popup has 5, count_total = 12.
    """
    from seo.services import build_aggregate_points

    fake_pa = {
        "pa_id": 42, "latitude": 48.85, "longitude": 2.35,
        "name": "PA test", "street_address": "1 rue X",
        "postal_code": "75001", "address_locality": "Paris",
        "address_country": "France",
    }
    # Champ "datetime" en entree (format get_events_for_tenants)
    # / Input field is "datetime" (get_events_for_tenants format)
    fake_events = [
        {"uuid": f"e{i}", "name": f"Event {i}",
         "datetime": f"2026-0{i % 9 + 1}-15T20:00:00+00:00",
         "postal_address_id": 42, "slug": f"event-{i}"}
        for i in range(1, 13)
    ]
    with patch("seo.services.get_postal_addresses_for_tenants",
               return_value={"uuid-A": [fake_pa]}):
        result = build_aggregate_points(
            [("uuid-A", "schema-A")],
            configs_by_tenant={"uuid-A": {"organisation": "Org A", "domain": "a.test"}},
            events_by_tenant={"uuid-A": fake_events},
        )
    assert len(result["points"]) == 1
    point = result["points"][0]
    assert len(point["events_futurs"]) == 5
    assert point["events_futurs_count_total"] == 12


def test_build_aggregate_points_is_main_address_flag():
    """
    Si pa_id == config.postal_address_id -> is_main_address True. Sinon False.
    / If pa_id matches config.postal_address_id -> is_main_address True.
    """
    from seo.services import build_aggregate_points

    fake_pa_main = {
        "pa_id": 10, "latitude": 1.0, "longitude": 1.0,
        "name": "Main", "street_address": "", "postal_code": "",
        "address_locality": "", "address_country": "",
    }
    fake_pa_sec = {
        "pa_id": 20, "latitude": 2.0, "longitude": 2.0,
        "name": "Sec", "street_address": "", "postal_code": "",
        "address_locality": "", "address_country": "",
    }
    with patch("seo.services.get_postal_addresses_for_tenants",
               return_value={"uuid-X": [fake_pa_main, fake_pa_sec]}):
        result = build_aggregate_points(
            [("uuid-X", "schema-X")],
            configs_by_tenant={"uuid-X": {
                "organisation": "Org X", "domain": "x.test",
                "postal_address_id": 10,
            }},
            events_by_tenant={},
        )
    points_par_id = {p["pa_id"]: p for p in result["points"]}
    # pa_id est prefixe par le tenant_uuid (unicite cross-tenant) : "uuid-X:10".
    # / pa_id is prefixed with the tenant_uuid (cross-tenant uniqueness).
    assert points_par_id["uuid-X:10"]["is_main_address"] is True
    assert points_par_id["uuid-X:20"]["is_main_address"] is False


def test_build_explorer_data_for_tenants_filtre_par_uuid():
    """
    build_explorer_data_for_tenants lit AGGREGATE_POINTS + AGGREGATE_LIEUX
    et filtre par tenant_uuids.
    / Filters AGGREGATE_POINTS + AGGREGATE_LIEUX by tenant_uuids.
    """
    from seo.services import build_explorer_data_for_tenants

    fake_points = {"points": [
        {"pa_id": 1, "tenant_id": "uuid-A", "pa_name": "PA1",
         "latitude": 1.0, "longitude": 1.0},
        {"pa_id": 2, "tenant_id": "uuid-A", "pa_name": "PA2",
         "latitude": 2.0, "longitude": 2.0},
        {"pa_id": 3, "tenant_id": "uuid-B", "pa_name": "PA3",
         "latitude": 3.0, "longitude": 3.0},
    ]}
    fake_lieux = {"lieux": [
        {"tenant_id": "uuid-A", "name": "Org A", "domain": "a.test"},
        {"tenant_id": "uuid-B", "name": "Org B", "domain": "b.test"},
    ]}

    # get_seo_cache appele 2x : 1 pour AGGREGATE_POINTS, 1 pour AGGREGATE_LIEUX
    # / get_seo_cache called 2x: once for POINTS, once for LIEUX
    def fake_get_cache(cache_type):
        from seo.models import SEOCache
        if cache_type == SEOCache.AGGREGATE_POINTS:
            return fake_points
        if cache_type == SEOCache.AGGREGATE_LIEUX:
            return fake_lieux
        return None

    with patch("seo.views_common.get_seo_cache", side_effect=fake_get_cache):
        result = build_explorer_data_for_tenants(["uuid-A"])
    assert len(result["points"]) == 2
    assert {p["pa_id"] for p in result["points"]} == {1, 2}
    assert len(result["tenants"]) == 1
    assert result["tenants"][0]["tenant_id"] == "uuid-A"


def test_build_explorer_data_for_tenants_liste_vide_renvoie_points_et_tenants_vides():
    """Liste vide -> {"points": [], "tenants": []} sans appel cache."""
    from seo.services import build_explorer_data_for_tenants
    assert build_explorer_data_for_tenants([]) == {"points": [], "tenants": []}


def test_build_aggregate_points_propage_tags_dans_events_pour_popup():
    """
    Le champ `tags` est present dans les events_pour_popup quand l'event d'entree
    en a. Forme : list[dict{slug, name, color}].
    / Field `tags` is propagated into events_pour_popup when input event has them.
    """
    from seo.services import build_aggregate_points

    fake_pa = {
        "pa_id": 1, "latitude": 1.0, "longitude": 1.0,
        "name": "PA", "street_address": "", "postal_code": "",
        "address_locality": "", "address_country": "",
    }
    fake_event_avec_tags = {
        "uuid": "ev-1",
        "name": "Soiree Jazz",
        "datetime": "2026-06-15T20:00:00+00:00",
        "postal_address_id": 1,
        "slug": "soiree-jazz",
        "tags": [{"slug": "jazz", "name": "Jazz", "color": "#0dcaf0"}],
    }
    with patch("seo.services.get_postal_addresses_for_tenants",
               return_value={"uuid-A": [fake_pa]}):
        result = build_aggregate_points(
            [("uuid-A", "schema-A")],
            configs_by_tenant={"uuid-A": {"organisation": "Org", "domain": "a.test"}},
            events_by_tenant={"uuid-A": [fake_event_avec_tags]},
        )
    point = result["points"][0]
    assert len(point["events_futurs"]) == 1
    event = point["events_futurs"][0]
    assert "tags" in event
    assert event["tags"] == [{"slug": "jazz", "name": "Jazz", "color": "#0dcaf0"}]


def test_build_aggregate_points_tags_vide_si_event_sans_tag():
    """
    Un event sans tags d'entree -> events_pour_popup[i].tags = [].
    / Event without tags -> events_pour_popup[i].tags = [].
    """
    from seo.services import build_aggregate_points

    fake_pa = {
        "pa_id": 1, "latitude": 1.0, "longitude": 1.0,
        "name": "PA", "street_address": "", "postal_code": "",
        "address_locality": "", "address_country": "",
    }
    fake_event_sans_tags = {
        "uuid": "ev-2",
        "name": "Atelier",
        "datetime": "2026-07-01T18:00:00+00:00",
        "postal_address_id": 1,
        "slug": "atelier",
        # Pas de cle "tags" du tout
    }
    with patch("seo.services.get_postal_addresses_for_tenants",
               return_value={"uuid-A": [fake_pa]}):
        result = build_aggregate_points(
            [("uuid-A", "schema-A")],
            configs_by_tenant={"uuid-A": {"organisation": "Org", "domain": "a.test"}},
            events_by_tenant={"uuid-A": [fake_event_sans_tags]},
        )
    event = result["points"][0]["events_futurs"][0]
    assert event["tags"] == []


def test_get_postal_addresses_for_tenants_trie_les_adresses_par_pk():
    """
    Les adresses sortent triees par pk croissant.
    / Addresses come out sorted by ascending pk.

    Sans order_by explicite, PostgreSQL rend les lignes dans un ordre arbitraire,
    qui bouge au fil des ecritures. Cet ordre se propage jusqu'aux markers de la
    carte : un lieu vise au clic changerait d'adresse d'un rebuild du cache a l'autre.
    / Without explicit ordering, PostgreSQL returns rows in an arbitrary, drifting
    order that propagates to the map markers.
    """
    from seo.services import get_postal_addresses_for_tenants

    fake_qs = MagicMock()
    fake_qs.exclude.return_value = fake_qs
    fake_qs.order_by.return_value = fake_qs
    fake_qs.__iter__ = lambda self: iter([])

    fake_tenant = MagicMock()
    fake_tenant.schema_name = "fake_schema"

    with patch("Customers.models.Client.objects.get", return_value=fake_tenant), \
         patch("django_tenants.utils.tenant_context"), \
         patch("BaseBillet.models.PostalAddress.objects") as mock_objects:
        mock_objects.exclude.return_value = fake_qs
        get_postal_addresses_for_tenants([("uuid-A", "fake_schema")])

    fake_qs.order_by.assert_called_once_with("pk")


def test_build_aggregate_points_deux_tenants_meme_adresse_gardent_leurs_events():
    """
    Deux lieux differents a la MEME adresse (memes coordonnees) restent deux points
    distincts, chacun avec ses propres evenements.
    / Two different venues at the SAME address stay two distinct points, each keeping
    its own events.

    C'est le scenario du bug remonte : le lieu qui affiche la carte du reseau possede
    une PostalAddress aux coordonnees exactes d'un lieu federe. Les pk de PostalAddress
    repartent a 1 dans chaque schema tenant : sans le prefixe tenant_uuid sur pa_id, les
    deux points s'ecraseraient cote JS et les evenements du lieu federe dispararaitraient.
    / Reported-bug scenario: PostalAddress pks restart at 1 in every tenant schema, so
    without the tenant_uuid prefix on pa_id the two points would collide.
    """
    from seo.services import build_aggregate_points

    # Meme pk (1) et memes coordonnees dans les deux schemas : le pire cas.
    # / Same pk (1) and same coordinates in both schemas: the worst case.
    adresse_partagee = {
        "pa_id": 1, "latitude": 45.766, "longitude": 4.873,
        "name": "La grange", "street_address": "", "postal_code": "69100",
        "address_locality": "Villeurbanne", "address_country": "FR",
    }
    event_du_lieu_federe = {
        "uuid": "ev-federe", "name": "Bal trad", "slug": "bal-trad",
        "datetime": "2026-10-27T20:00:00+00:00", "postal_address_id": 1,
    }

    with patch("seo.services.get_postal_addresses_for_tenants", return_value={
        "uuid-carte": [dict(adresse_partagee)],
        "uuid-federe": [dict(adresse_partagee)],
    }):
        result = build_aggregate_points(
            [("uuid-carte", "schema-carte"), ("uuid-federe", "schema-federe")],
            configs_by_tenant={
                "uuid-carte": {"organisation": "Lieu qui affiche la carte", "domain": "carte.test"},
                "uuid-federe": {"organisation": "Lieu federe", "domain": "federe.test"},
            },
            # Seul le lieu federe a un evenement a cette adresse.
            # / Only the federated venue has an event at this address.
            events_by_tenant={"uuid-federe": [event_du_lieu_federe]},
        )

    points_par_id = {p["pa_id"]: p for p in result["points"]}
    assert set(points_par_id) == {"uuid-carte:1", "uuid-federe:1"}

    # L'evenement reste sur le point du lieu federe, et n'est pas absorbe par l'autre.
    # / The event stays on the federated venue point, and is not absorbed by the other.
    assert points_par_id["uuid-federe:1"]["events_futurs_count_total"] == 1
    assert points_par_id["uuid-federe:1"]["events_futurs"][0]["name"] == "Bal trad"
    assert points_par_id["uuid-carte:1"]["events_futurs_count_total"] == 0


def test_build_tenant_config_data_expose_l_id_de_l_adresse_principale(tenant):
    """
    build_tenant_config_data expose postal_address_id = l'adresse de la Configuration.
    / build_tenant_config_data exposes postal_address_id = the Configuration address.

    C'est ce champ que build_aggregate_points compare pour poser is_main_address, donc
    c'est lui qui decide quel marker la carte vise au clic sur un lieu (explorer.js,
    focusOnLieu). S'il reste a None, aucun point n'est marque comme principal et la
    carte vise une adresse quelconque du lieu.
    / This field drives is_main_address, hence which marker the map focuses on click.
    """
    from django_tenants.utils import tenant_context

    from BaseBillet.models import Configuration
    from seo.services import build_tenant_config_data

    with tenant_context(tenant):
        config_du_tenant = Configuration.get_solo()
        id_adresse_principale_attendu = config_du_tenant.postal_address_id

    data = build_tenant_config_data(tenant)

    assert data["postal_address_id"] == id_adresse_principale_attendu
