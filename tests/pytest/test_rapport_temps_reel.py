"""
tests/pytest/test_rapport_temps_reel.py — Test de l'action rapport_temps_reel.
tests/pytest/test_rapport_temps_reel.py — Test for the rapport_temps_reel action.

Couvre : GET /laboutik/caisse/rapport-temps-reel/ (page standalone HTML).
Covers: GET /laboutik/caisse/rapport-temps-reel/ (standalone HTML page).

Utilise FastTenantTestCase (django-tenants) : schema isole, TenantClient pour le routage URL.
Uses FastTenantTestCase (django-tenants): isolated schema, TenantClient for URL routing.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_rapport_temps_reel.py -v
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser


class TestRapportTempsReel(FastTenantTestCase):
    """Verifie que l'endpoint rapport-temps-reel repond correctement.
    Utilise un tenant isole avec TenantClient pour le routage django-tenants.
    / Verify that the rapport-temps-reel endpoint responds correctly.
    Uses an isolated tenant with TenantClient for django-tenants routing."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_rapport'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-rapport.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = 'Test Rapport'

    def setUp(self):
        """Cree un utilisateur admin et le client HTTP authentifie.
        / Creates an admin user and authenticated HTTP client."""
        # Re-setter le search_path apres le rollback du test precedent.
        # / Re-set search_path after previous test's rollback.
        connection.set_tenant(self.tenant)

        # Utilisateur admin (public schema — SHARED_APPS)
        # / Admin user (public schema — SHARED_APPS)
        self.admin, _created = TibilletUser.objects.get_or_create(
            email='admin-test-rapport@tibillet.localhost',
            defaults={
                'username': 'admin-test-rapport@tibillet.localhost',
                'is_staff': True,
                'is_active': True,
            },
        )
        self.admin.client_admin.add(self.tenant)

        # Client HTTP avec session admin / HTTP client with admin session
        self.c = TenantClient(self.tenant)
        self.c.force_login(self.admin)

    def test_rapport_temps_reel_status_200(self):
        """
        GET /laboutik/caisse/rapport-temps-reel/ doit renvoyer 200
        avec une page HTML standalone (DOCTYPE).
        Sur un tenant vide (pas de ventes), le message "aucune vente" est affiche.
        / GET must return 200 with a standalone HTML page (DOCTYPE).
        On an empty tenant (no sales), the "no sales" message is displayed.
        """
        response = self.c.get('/laboutik/caisse/rapport-temps-reel/')

        # Statut 200 attendu / Expected status 200
        assert response.status_code == 200, (
            f"Attendu 200, recu {response.status_code}"
        )

        # Page HTML standalone (pas un partial HTMX)
        # / Standalone HTML page (not an HTMX partial)
        contenu = response.content.decode('utf-8')
        assert '<!DOCTYPE html>' in contenu, (
            "La reponse doit contenir <!DOCTYPE html> (page standalone)"
        )

        # Soit le rapport est present, soit le message "aucune vente"
        # / Either the report is present, or the "no sales" message
        rapport_present = 'section-totaux-par-moyen' in contenu
        aucune_vente = 'aucune-vente' in contenu
        assert rapport_present or aucune_vente, (
            "La reponse doit contenir soit 'section-totaux-par-moyen' "
            "(rapport avec ventes) soit 'aucune-vente' (pas de ventes)"
        )
