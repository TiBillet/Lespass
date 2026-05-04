"""
Tests pour l'enrichissement des assets dans le cache SEO.
/ Tests for asset enrichment in SEO cache.
"""

import pytest
from Customers.models import Client


@pytest.mark.django_db(transaction=True)
def test_get_all_assets_returns_origin_and_accepting_tenants():
    """
    Vérifie que get_all_assets() retourne tenant_origin_id/name et accepting_tenant_ids.
    """
    from seo.services import get_all_assets

    assets = get_all_assets()
    assert len(assets) > 0, "La fixture doit contenir des assets"

    for asset in assets:
        assert "uuid" in asset
        assert "name" in asset
        assert "category" in asset
        assert "tenant_origin_id" in asset
        assert "tenant_origin_name" in asset
        assert "accepting_tenant_ids" in asset
        assert "accepting_count" in asset
        assert "is_federation_primary" in asset
        assert isinstance(asset["accepting_tenant_ids"], list)
        assert isinstance(asset["accepting_count"], int)
        assert isinstance(asset["is_federation_primary"], bool)


@pytest.mark.django_db(transaction=True)
def test_asset_fed_is_federation_primary():
    """
    Les assets de catégorie FED sont marqués is_federation_primary=True.
    """
    from seo.services import get_all_assets

    assets = get_all_assets()
    fed_assets = [a for a in assets if a["category"] == "FED"]
    for asset in fed_assets:
        assert asset["is_federation_primary"] is True


@pytest.mark.django_db(transaction=True)
def test_asset_origin_is_always_in_accepting_tenants():
    """
    Si un asset a un tenant_origin, il doit apparaitre dans accepting_tenant_ids
    et accepting_count doit etre >= 1.
    / If an asset has a tenant_origin, it must be in accepting_tenant_ids
    and accepting_count must be >= 1.
    """
    from seo.services import get_all_assets

    assets = get_all_assets()
    for asset in assets:
        if asset["tenant_origin_id"]:
            assert asset["tenant_origin_id"] in asset["accepting_tenant_ids"], (
                f"tenant_origin {asset['tenant_origin_id']} absent de accepting_tenant_ids "
                f"pour l'asset {asset['name']}"
            )
            assert asset["accepting_count"] >= 1


@pytest.mark.django_db(transaction=True)
def test_tenant_config_includes_accepted_assets():
    """
    Chaque tenant config doit inclure la liste des assets acceptes (uuid).
    / Each tenant config must include the list of accepted assets (uuid).
    """
    from seo.services import build_tenant_config_data

    tenant = Client.objects.exclude(schema_name="public").first()
    assert tenant is not None, "Fixture must have at least one tenant"

    data = build_tenant_config_data(tenant)
    assert "accepted_asset_ids" in data
    assert isinstance(data["accepted_asset_ids"], list)


@pytest.mark.django_db(transaction=True)
def test_build_explorer_data_assets_have_federation_fields():
    """
    Les assets dans build_explorer_data() exposent les champs de federation.
    / Assets in build_explorer_data() expose federation fields.
    """
    from seo.services import build_explorer_data
    from django.core.management import call_command

    call_command("refresh_seo_cache")

    data = build_explorer_data()
    assert "assets" in data
    assert len(data["assets"]) > 0

    for asset in data["assets"]:
        assert "tenant_origin_id" in asset
        assert "tenant_origin_name" in asset
        assert "accepting_tenant_ids" in asset
        assert "accepting_count" in asset
        assert "is_federation_primary" in asset


@pytest.mark.django_db(transaction=True)
def test_build_explorer_data_lieux_have_accepted_assets():
    """
    Les lieux dans build_explorer_data() exposent accepted_asset_ids.
    / Lieux in build_explorer_data() expose accepted_asset_ids.
    """
    from seo.services import build_explorer_data
    from django.core.management import call_command

    call_command("refresh_seo_cache")

    data = build_explorer_data()
    assert "lieux" in data
    for lieu in data["lieux"]:
        assert "accepted_asset_ids" in lieu
        assert isinstance(lieu["accepted_asset_ids"], list)
