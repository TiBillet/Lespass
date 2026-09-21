"""
Tests de l'enrichissement explorer_data pour la page Reseau V2.
/ Tests for the explorer_data enrichment used by the V2 Network page.

LOCALISATION : tests/pytest/test_federation_enrichissement.py

Couvre les deux helpers de BaseBillet/views.py :
- _distance_km_haversine : distance a vol d'oiseau entre deux points GPS.
- _enrichir_explorer_data_avec_distance : ajoute la distance a chaque point
  de explorer_data. Le type de lieu (Client.categorie) n'est plus enrichi :
  ni le filtre ni le badge de type n'existent plus cote front.
"""
from types import SimpleNamespace

import pytest

from BaseBillet.views import (
    _distance_km_haversine,
    _enrichir_explorer_data_avec_distance,
)
from Customers.models import Client


# ----------------------------------------------------------------------------
# Fixtures : base de dev (meme pattern que test_federation_view_integration.py)
# / Fixtures: dev DB (same pattern as test_federation_view_integration.py)
# ----------------------------------------------------------------------------

@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse dev DB (no test DB creation).
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()


@pytest.fixture
def tenant():
    tenant_lespass = Client.objects.filter(schema_name="lespass").first()
    if not tenant_lespass:
        tenant_lespass = Client.objects.exclude(schema_name="public").first()
    return tenant_lespass


def _config_avec_adresse_geocodee():
    """Fausse Configuration : seule postal_address est lue par le helper."""
    return SimpleNamespace(
        postal_address=SimpleNamespace(latitude=45.7719, longitude=4.8902),
    )


# ----------------------------------------------------------------------------
# _distance_km_haversine
# / _distance_km_haversine
# ----------------------------------------------------------------------------

class TestDistanceKmHaversine:

    def test_distance_villeurbanne_paris_environ_392_km(self):
        # Villeurbanne (45.7719, 4.8902) -> Paris (48.8566, 2.3522) : la
        # distance reelle a vol d'oiseau est d'environ 392 km. On accepte une
        # marge de 5 km : on teste la formule, pas la geographie.
        # / Villeurbanne -> Paris: the real straight-line distance is about
        # 392 km. 5 km tolerance: we test the formula, not geography.
        distance = _distance_km_haversine(45.7719, 4.8902, 48.8566, 2.3522)
        assert 387 < distance < 397

    def test_distance_nulle_entre_deux_points_identiques(self):
        # / Zero distance between two identical points
        distance = _distance_km_haversine(45.7719, 4.8902, 45.7719, 4.8902)
        assert distance == 0


# ----------------------------------------------------------------------------
# _enrichir_explorer_data_avec_distance
# / _enrichir_explorer_data_avec_distance
# ----------------------------------------------------------------------------

@pytest.mark.django_db
class TestEnrichissementExplorerData:

    def test_ajoute_la_distance_quand_origine_geocodee(self, tenant):
        # Un point situe au tenant courant est a 0.0 km de l'origine.
        # / A point at the current tenant is 0.0 km away from the origin.
        uuid_du_tenant = str(tenant.uuid)
        explorer_data = {
            "tenants": [{"tenant_id": uuid_du_tenant, "name": "Lieu Test"}],
            "points": [{
                "pa_id": f"{uuid_du_tenant}:1",
                "tenant_id": uuid_du_tenant,
                "latitude": 45.7719,
                "longitude": 4.8902,
            }],
        }

        resultat = _enrichir_explorer_data_avec_distance(
            explorer_data, _config_avec_adresse_geocodee(),
        )

        assert resultat["points"][0]["distance_km"] == 0.0

    def test_point_sans_coordonnees_recoit_distance_null(self, tenant):
        # Un point sans lat/lng (lieu sans adresse fixe) recoit distance_km None.
        # / A point without lat/lng (no fixed venue) gets distance_km None.
        uuid_du_tenant = str(tenant.uuid)
        explorer_data = {
            "tenants": [],
            "points": [{
                "pa_id": f"addressless-{uuid_du_tenant}",
                "tenant_id": uuid_du_tenant,
                "latitude": None,
                "longitude": None,
            }],
        }

        resultat = _enrichir_explorer_data_avec_distance(
            explorer_data, _config_avec_adresse_geocodee(),
        )

        assert resultat["points"][0]["distance_km"] is None

    def test_sans_origine_geocodee_la_cle_distance_est_absente(self, tenant):
        # Si le tenant courant n'a pas d'adresse geocodee, la cle distance_km
        # ne doit PAS exister : sinon le JS afficherait "sans lieu fixe" sur
        # tous les lieux. / Without a geocoded origin, the distance_km key must
        # NOT exist: otherwise the JS would show "no fixed venue" everywhere.
        uuid_du_tenant = str(tenant.uuid)
        explorer_data = {
            "tenants": [],
            "points": [{
                "pa_id": f"{uuid_du_tenant}:1",
                "tenant_id": uuid_du_tenant,
                "latitude": 45.7719,
                "longitude": 4.8902,
            }],
        }
        config_sans_adresse = SimpleNamespace(postal_address=None)

        resultat = _enrichir_explorer_data_avec_distance(
            explorer_data, config_sans_adresse,
        )

        assert "distance_km" not in resultat["points"][0]

    def test_tenants_avec_uuid_invalides_ne_font_pas_echouer(self, tenant):
        # Des identifiants non-UUID dans les donnees de cache ne doivent pas
        # faire echouer le calcul : un point sans coordonnees recoit None.
        # / Non-UUID identifiers in cached data must not break the computation:
        # a point without coordinates gets None.
        explorer_data = {
            "tenants": [{"tenant_id": "uuid-sans-adresse", "name": "Lieu Fictif"}],
            "points": [{
                "pa_id": "addressless-uuid-sans-adresse",
                "tenant_id": "uuid-sans-adresse",
                "latitude": None,
                "longitude": None,
            }],
        }

        resultat = _enrichir_explorer_data_avec_distance(
            explorer_data, _config_avec_adresse_geocodee(),
        )

        assert resultat["points"][0]["distance_km"] is None
