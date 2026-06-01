"""
Tests d'intégration de FederationViewset.list (/federation/).
/ Integration tests for FederationViewset.list (/federation/).

LOCALISATION : tests/pytest/test_federation_view_integration.py
Voir SESSIONS/FEDERATION/04-federation-config-design.md.

On exerce la VUE réelle (routing django-tenants + rendu) sur le tenant 'lespass'
de la base de dev, en mockant les sources de données (config, cache fédération,
build_explorer_data) pour rester indépendant du seed et du contenu du cache.

Les options 1/2/tri sont aussi couvertes en unitaire dans test_federation_config.py
(fonction pure appliquer_options_federation). Ici on vérifie le CÂBLAGE de la vue :
- option "afficher_lieux_entrants" (logique propre à la vue),
- application effective des options sur le rendu,
- robustesse (200) selon la config.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test.client import Client as DjangoClient
from django.urls import reverse
from django_tenants.utils import tenant_context

from Customers.models import Client


# ----------------------------------------------------------------------------
# Fixtures : base de dev + acces multi-tenant (cf. test_event_wizard_public.py)
# / Fixtures: dev DB + multi-tenant access
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
    t = Client.objects.filter(schema_name="lespass").first()
    if not t:
        t = Client.objects.exclude(schema_name="public").first()
    return t


@pytest.fixture
def http_client(tenant):
    domain = tenant.domains.first()
    return DjangoClient(HTTP_HOST=domain.domain)


def _fake_config(**overrides):
    """Faux FederationConfiguration.get_solo() : SimpleNamespace avec les 5 champs."""
    valeurs = dict(
        afficher_lieux_entrants=True,
        afficher_seulement_lieux_avec_event=False,
        afficher_lieux_sans_adresse=True,
        tri_des_lieux="alpha",
        texte_introduction="",
    )
    valeurs.update(overrides)
    return SimpleNamespace(**valeurs)


# ----------------------------------------------------------------------------
# Option 3 : afficher_lieux_entrants (logique propre a la vue)
# ----------------------------------------------------------------------------


@pytest.mark.django_db
class TestOptionLieuxEntrants:

    def test_entrants_actives_inclut_le_voisin_entrant(self, http_client, tenant):
        """afficher_lieux_entrants=True -> l'uuid entrant est passe a l'explorer."""
        with tenant_context(tenant):
            current_uuid = str(tenant.uuid)
            fake_incoming = {"by_tenant": {current_uuid: ["uuid-entrant-fictif"]}}
            capture = MagicMock(return_value={"points": [], "tenants": []})
            with patch("BaseBillet.models.FederationConfiguration.get_solo",
                       return_value=_fake_config(afficher_lieux_entrants=True)), \
                 patch("seo.views_common.get_seo_cache", return_value=fake_incoming), \
                 patch("seo.services.build_explorer_data_for_tenants", capture):
                resp = http_client.get(reverse("federation-list"))

            assert resp.status_code == 200
            uuids_passes = capture.call_args[0][0]
            assert "uuid-entrant-fictif" in uuids_passes

    def test_entrants_desactives_exclut_le_voisin_entrant(self, http_client, tenant):
        """afficher_lieux_entrants=False -> l'uuid entrant n'est PAS passe."""
        with tenant_context(tenant):
            current_uuid = str(tenant.uuid)
            fake_incoming = {"by_tenant": {current_uuid: ["uuid-entrant-fictif"]}}
            capture = MagicMock(return_value={"points": [], "tenants": []})
            with patch("BaseBillet.models.FederationConfiguration.get_solo",
                       return_value=_fake_config(afficher_lieux_entrants=False)), \
                 patch("seo.views_common.get_seo_cache", return_value=fake_incoming), \
                 patch("seo.services.build_explorer_data_for_tenants", capture):
                resp = http_client.get(reverse("federation-list"))

            assert resp.status_code == 200
            uuids_passes = capture.call_args[0][0]
            assert "uuid-entrant-fictif" not in uuids_passes


# ----------------------------------------------------------------------------
# Application effective des options sur le rendu
# ----------------------------------------------------------------------------


@pytest.mark.django_db
class TestOptionsAppliqueesAuRendu:

    def test_lieu_sans_adresse_injecte_dans_le_rendu(self, http_client, tenant):
        """
        afficher_lieux_sans_adresse=True : un tenant present dans `tenants` mais
        sans point doit produire un point "addressless-<uuid>" dans le JSON rendu
        (json_script #explorer-data). Prouve que appliquer_options_federation est
        bien câblé dans la vue.
        """
        with tenant_context(tenant):
            explorer_data = {
                "points": [],
                "tenants": [
                    {"tenant_id": "uuid-sans-adresse", "name": "Lieu Sans Adresse",
                     "domain": "sansadresse.test", "logo_url": None, "event_count": 1},
                ],
            }
            with patch("BaseBillet.models.FederationConfiguration.get_solo",
                       return_value=_fake_config(afficher_lieux_sans_adresse=True)), \
                 patch("seo.views_common.get_seo_cache", return_value={"by_tenant": {}}), \
                 patch("seo.services.build_explorer_data_for_tenants",
                       return_value=explorer_data):
                resp = http_client.get(reverse("federation-list"))

            assert resp.status_code == 200
            assert b"addressless-uuid-sans-adresse" in resp.content

    def test_texte_introduction_present_dans_le_rendu(self, http_client, tenant):
        """Le texte d'introduction configuré apparait dans la page."""
        with tenant_context(tenant):
            marqueur = "Bienvenue-dans-notre-reseau-de-demo-12345"
            with patch("BaseBillet.models.FederationConfiguration.get_solo",
                       return_value=_fake_config(texte_introduction=f"<p>{marqueur}</p>")), \
                 patch("seo.views_common.get_seo_cache", return_value={"by_tenant": {}}), \
                 patch("seo.services.build_explorer_data_for_tenants",
                       return_value={"points": [], "tenants": []}):
                resp = http_client.get(reverse("federation-list"))

            assert resp.status_code == 200
            assert marqueur.encode() in resp.content
