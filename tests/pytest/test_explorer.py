"""
Tests pour les services explorer (GPS dans SEOCache).
/ Tests for explorer services (GPS in SEOCache).
"""

import pytest
from django.test import Client as DjangoTestClient
from Customers.models import Client


@pytest.mark.django_db
class TestExplorerServices:
    """Tests GPS dans build_tenant_config_data et aggregate_lieux.
    / Tests GPS in build_tenant_config_data and aggregate_lieux.
    """

    def test_build_tenant_config_data_includes_gps(self):
        """build_tenant_config_data retourne latitude et longitude.
        / build_tenant_config_data returns latitude and longitude.
        """
        from seo.services import build_tenant_config_data

        # Prendre un tenant actif (non-root, non-public)
        # / Pick an active tenant (non-root, non-public)
        client = (
            Client.objects.exclude(schema_name="public")
            .exclude(categorie=Client.ROOT)
            .first()
        )

        if client is None:
            pytest.skip("Aucun tenant actif disponible / No active tenant available")

        data = build_tenant_config_data(client)

        # Les cles GPS doivent etre presentes dans le dict
        # / GPS keys must be present in the dict
        assert "latitude" in data, "Cle 'latitude' manquante / Key 'latitude' missing"
        assert "longitude" in data, (
            "Cle 'longitude' manquante / Key 'longitude' missing"
        )

    def test_aggregate_lieux_contains_gps_fields(self):
        """Chaque lieu dans aggregate_lieux a latitude et longitude.
        / Each venue in aggregate_lieux has latitude and longitude.
        """
        from seo.models import SEOCache
        from seo.tasks import refresh_seo_cache
        from seo.views_common import get_seo_cache

        # Lancer le refresh pour peupler le cache
        # / Run refresh to populate the cache
        refresh_seo_cache()

        lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX) or {}
        lieux = lieux_data.get("lieux", [])

        # Il doit y avoir au moins un lieu pour que le test soit pertinent
        # / There must be at least one venue for the test to be meaningful
        if not lieux:
            pytest.skip("Aucun lieu dans le cache / No venue in cache")

        for lieu in lieux:
            assert "latitude" in lieu, (
                f"Cle 'latitude' manquante pour {lieu.get('name')} "
                f"/ Key 'latitude' missing for {lieu.get('name')}"
            )
            assert "longitude" in lieu, (
                f"Cle 'longitude' manquante pour {lieu.get('name')} "
                f"/ Key 'longitude' missing for {lieu.get('name')}"
            )

    def test_build_explorer_data_returns_three_keys(self):
        """build_explorer_data retourne lieux, events, memberships (tous des listes).
        / build_explorer_data returns lieux, events, memberships (all lists).
        """
        from seo.services import build_explorer_data
        from seo.tasks import refresh_seo_cache

        # Peupler le cache avant d'appeler build_explorer_data
        # / Populate cache before calling build_explorer_data
        refresh_seo_cache()

        data = build_explorer_data()

        assert "lieux" in data, "Cle 'lieux' manquante / Key 'lieux' missing"
        assert "events" in data, "Cle 'events' manquante / Key 'events' missing"
        assert "memberships" in data, (
            "Cle 'memberships' manquante / Key 'memberships' missing"
        )
        assert isinstance(data["lieux"], list), (
            "lieux doit etre une liste / lieux must be a list"
        )
        assert isinstance(data["events"], list), (
            "events doit etre une liste / events must be a list"
        )
        assert isinstance(data["memberships"], list), (
            "memberships doit etre une liste / memberships must be a list"
        )

    def test_build_explorer_data_excludes_lieux_without_coords(self):
        """Tous les lieux retournes ont latitude ET longitude non-None.
        / All returned lieux have non-None latitude AND longitude.
        """
        from seo.services import build_explorer_data
        from seo.tasks import refresh_seo_cache

        refresh_seo_cache()
        data = build_explorer_data()

        for lieu in data["lieux"]:
            assert lieu["latitude"] is not None, (
                f"latitude None pour {lieu.get('name')} / latitude None for {lieu.get('name')}"
            )
            assert lieu["longitude"] is not None, (
                f"longitude None pour {lieu.get('name')} / longitude None for {lieu.get('name')}"
            )

    def test_build_explorer_data_nests_events_under_lieux(self):
        """Chaque lieu a des cles events et memberships (listes).
        / Each lieu has events and memberships keys (lists).
        """
        from seo.services import build_explorer_data
        from seo.tasks import refresh_seo_cache

        refresh_seo_cache()
        data = build_explorer_data()

        for lieu in data["lieux"]:
            assert "events" in lieu, (
                f"Cle 'events' manquante dans lieu {lieu.get('name')} "
                f"/ Key 'events' missing in lieu {lieu.get('name')}"
            )
            assert "memberships" in lieu, (
                f"Cle 'memberships' manquante dans lieu {lieu.get('name')} "
                f"/ Key 'memberships' missing in lieu {lieu.get('name')}"
            )
            assert isinstance(lieu["events"], list), (
                "events du lieu doit etre une liste / lieu events must be a list"
            )
            assert isinstance(lieu["memberships"], list), (
                "memberships du lieu doit etre une liste / lieu memberships must be a list"
            )

    def test_build_explorer_data_events_have_lieu_id(self):
        """Chaque event dans la liste plate a lieu_id, lieu_name, lieu_domain.
        / Each event in the flat list has lieu_id, lieu_name, lieu_domain.
        """
        from seo.services import build_explorer_data
        from seo.tasks import refresh_seo_cache

        refresh_seo_cache()
        data = build_explorer_data()

        for event in data["events"]:
            assert "lieu_id" in event, (
                f"Cle 'lieu_id' manquante dans event {event.get('name')} "
                f"/ Key 'lieu_id' missing in event {event.get('name')}"
            )
            assert "lieu_name" in event, (
                f"Cle 'lieu_name' manquante dans event {event.get('name')} "
                f"/ Key 'lieu_name' missing in event {event.get('name')}"
            )
            assert "lieu_domain" in event, (
                f"Cle 'lieu_domain' manquante dans event {event.get('name')} "
                f"/ Key 'lieu_domain' missing in event {event.get('name')}"
            )


@pytest.mark.django_db
class TestExplorerView:
    """Tests pour la vue explorer / Tests for the explorer view"""

    @pytest.fixture(autouse=True)
    def _setup_cache_and_client(self):
        from seo.tasks import refresh_seo_cache

        refresh_seo_cache()
        self.root_client = DjangoTestClient(HTTP_HOST="www.tibillet.localhost")

    def test_explorer_view_returns_200(self):
        response = self.root_client.get("/explorer/")
        assert response.status_code == 200

    def test_explorer_template_contains_json_script(self):
        response = self.root_client.get("/explorer/")
        content = response.content.decode()
        assert 'id="explorer-data"' in content
        assert 'type="application/json"' in content

    def test_explorer_template_contains_leaflet(self):
        response = self.root_client.get("/explorer/")
        content = response.content.decode()
        assert "leaflet" in content.lower()

    def test_explorer_template_contains_search_bar(self):
        response = self.root_client.get("/explorer/")
        content = response.content.decode()
        assert "explorer-search" in content
