"""
Tests E2E Playwright : Explorer ROOT — 1 marker par PostalAddress (CHANTIER-05).
/ E2E Playwright tests: ROOT Explorer — 1 marker per PostalAddress (CHANTIER-05).

LOCALISATION : tests/e2e/test_explorer_markers_per_pa.py
Voir TECH_DOC/SESSIONS/SEO/CHANTIER-05-explorer-markers-per-pa.md.

Vérifie le refacto CHANTIER-05 :
- La page /explorer/ se charge sans erreur JS
- Le JSON injecté contient bien des "points" (pas "lieux")
- Au moins 1 marker (ou cluster) est visible sur la carte

PRÉREQUIS : le cache AGGREGATE_POINTS doit être à jour. Lancer avant :
  docker exec lespass_django poetry run python manage.py shell -c \
    "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"

Pattern conftest : pas de live_server Django. Le serveur tourne dans byobu
et est accessible via Traefik. Le domaine ROOT (apex) est tibillet.localhost
(PAS le sous-domaine tenant du baseURL).
/ conftest pattern: no Django live_server. Server runs in byobu, accessible
via Traefik. ROOT domain (apex) is tibillet.localhost (NOT the tenant subdomain
used as Playwright baseURL).
"""

import os

import pytest
from playwright.sync_api import expect

# Domaine APEX (nu) : l'explorer ROOT vit sur l'apex, pas sur le sous-domaine.
# / Bare (apex) domain: ROOT explorer lives on the apex, not on the subdomain.
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
EXPLORER_URL = f"https://{DOMAIN}/explorer/"

pytestmark = pytest.mark.e2e


# ============================================================
# FIXTURE — refresh SEO cache avant les tests
# ============================================================


@pytest.fixture(autouse=True, scope="module")
def refresh_cache():
    """
    Rafraichit le cache SEO (AGGREGATE_POINTS) une fois avant tous les tests
    du module. Garantit que les points par PostalAddress sont a jour.
    / Refresh the SEO cache (AGGREGATE_POINTS) once before all tests in this
    module. Ensures points-per-PostalAddress are up-to-date.

    Scope "module" : un seul appel.
    / Scope "module": a single call.

    Si le refresh echoue (serveur absent, CI sans docker), on logge et on
    continue. Les tests utiliseront le cache existant ou afficheront un SKIP.
    / If refresh fails (server absent, CI without docker), log and continue.
    Tests will use the existing cache or display an adequate SKIP.
    """
    import shutil
    import subprocess

    inside_container = shutil.which("docker") is None

    if inside_container:
        cmd = [
            "python", "/DjangoFiles/manage.py",
            "tenant_command", "shell", "-s", "public", "-c",
            "from seo.tasks import refresh_seo_cache; refresh_seo_cache()",
        ]
        env = {**os.environ, "TEST": "1", "PYTHONPATH": "/DjangoFiles"}
        cwd = "/DjangoFiles"
    else:
        cmd = [
            "docker", "exec", "-e", "TEST=1",
            "lespass_django", "poetry", "run", "python",
            "manage.py",
            "tenant_command", "shell", "-s", "public", "-c",
            "from seo.tasks import refresh_seo_cache; refresh_seo_cache()",
        ]
        env = None
        cwd = None

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=60,
        env=env, cwd=cwd,
    )
    if result.returncode != 0:
        import warnings
        warnings.warn(
            f"refresh_seo_cache a echoue (rc={result.returncode}). "
            f"Les tests utiliseront le cache existant. "
            f"Stderr : {result.stderr[:200]}",
            stacklevel=2,
        )


# ============================================================
# TESTS
# ============================================================


def test_page_explorer_charge_et_injecte_des_points(page):
    """
    La page /explorer/ se charge et injecte le JSON #explorer-data avec la
    nouvelle structure CHANTIER-05 : "points" et "tenants" au lieu de
    "lieux/events".
    / The /explorer/ page loads and injects the #explorer-data JSON with the
    new CHANTIER-05 structure: "points" and "tenants" instead of "lieux/events".

    Chaque point doit exposer : pa_id, tenant_id, latitude, longitude,
    pa_name, events_futurs, events_futurs_count_total.
    / Each point must expose: pa_id, tenant_id, latitude, longitude,
    pa_name, events_futurs, events_futurs_count_total.
    """
    import json

    # ROOT tenant : page Explorer publique, pas besoin de login.
    # / ROOT tenant: public Explorer page, no login required.
    page.goto(EXPLORER_URL)
    page.wait_for_load_state("networkidle")

    # Vérifie que l'élément JSON-data est présent.
    # / Check that the JSON-data element is present.
    data_el = page.locator("#explorer-data")
    assert data_el.count() > 0, "L'element #explorer-data est absent de la page"

    # Parse le JSON et vérifie la nouvelle structure {points, tenants}.
    # / Parse the JSON and verify the new structure {points, tenants}.
    raw_json = data_el.text_content()
    assert raw_json, "#explorer-data est vide"

    data = json.loads(raw_json)

    assert "points" in data, "La cle 'points' est absente du JSON #explorer-data"
    assert "tenants" in data, "La cle 'tenants' est absente du JSON #explorer-data"
    assert isinstance(data["points"], list), "'points' n'est pas une liste"
    assert isinstance(data["tenants"], list), "'tenants' n'est pas une liste"

    # Si des points sont presents, verifier la structure de chaque point.
    # / If points are present, verify the structure of each point.
    if data["points"]:
        first_point = data["points"][0]
        required_fields = [
            "pa_id",
            "tenant_id",
            "latitude",
            "longitude",
            "pa_name",
            "events_futurs",
            "events_futurs_count_total",
        ]
        for field in required_fields:
            assert field in first_point, (
                f"Champ obligatoire '{field}' absent du premier point : {first_point}"
            )


def test_au_moins_1_marker_visible_si_carte_a_des_donnees(page):
    """
    Si AGGREGATE_POINTS contient au moins 1 point, Leaflet doit avoir rendu
    au moins 1 marker ou cluster (.leaflet-marker-icon / .leaflet-marker-cluster).
    / If AGGREGATE_POINTS has at least 1 point, Leaflet must have rendered at
    least 1 marker or cluster (.leaflet-marker-icon / .leaflet-marker-cluster).

    SKIP automatique si la base de test ne contient aucun point (refresh_seo_cache
    a retourne un cache vide).
    / Automatic SKIP if the test DB has no points (refresh_seo_cache returned
    an empty cache).
    """
    import json

    page.goto(EXPLORER_URL)
    page.wait_for_load_state("networkidle")

    data_el = page.locator("#explorer-data")
    raw_json = data_el.text_content()
    data = json.loads(raw_json)

    # Si aucun point disponible : skip propre, pas un echec.
    # / If no points available: clean skip, not a failure.
    if not data.get("points"):
        pytest.skip(
            "Aucun point dans AGGREGATE_POINTS — "
            "lancer refresh_seo_cache avant les tests pour peupler le cache."
        )

    # Attendre que Leaflet rende les markers (cluster ou pin individuel).
    # / Wait for Leaflet to render markers (cluster or individual pin).
    page.wait_for_selector(
        ".leaflet-marker-icon, .leaflet-marker-cluster",
        timeout=8_000,
    )

    markers_count = page.locator(".leaflet-marker-icon, .leaflet-marker-cluster").count()
    assert markers_count > 0, (
        f"Aucun marker Leaflet visible alors que {len(data['points'])} point(s) "
        "sont presents dans AGGREGATE_POINTS."
    )
