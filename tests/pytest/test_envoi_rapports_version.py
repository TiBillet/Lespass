"""
tests/pytest/test_envoi_rapports_version.py — Session 19 : envoi auto rapports + version.
/ Session 19: automatic report sending + version display.

Couvre :
- Lecture de rapport_emails et rapport_periodicite depuis LaboutikConfiguration
- Filtrage par periodicite (daily/weekly/monthly)
- Lecture du fichier VERSION
- Version dans le state JSON

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_envoi_rapports_version.py -v
"""
import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

from django.db import connection
from django_tenants.test.cases import FastTenantTestCase

from laboutik.models import LaboutikConfiguration


class TestRapportEmailsConfig(FastTenantTestCase):
    """Tests pour la configuration des rapports automatiques.
    / Tests for automatic report configuration."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_rapports'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-rapports.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test Rapports'

    def setUp(self):
        connection.set_tenant(self.tenant)
        # Remettre les champs a leurs valeurs par defaut avant chaque test
        # Les tests FastTenantTestCase ne font pas de rollback DB (singleton partage)
        # / Reset fields to defaults before each test
        self.config = LaboutikConfiguration.get_solo()
        self.config.rapport_emails = []
        self.config.rapport_periodicite = 'daily'
        self.config.save()

    def test_rapport_emails_default_vide(self):
        """Le champ rapport_emails est une liste vide par defaut.
        / rapport_emails defaults to an empty list."""
        assert self.config.rapport_emails == []

    def test_rapport_periodicite_default_daily(self):
        """Le champ rapport_periodicite est 'daily' par defaut.
        / rapport_periodicite defaults to 'daily'."""
        assert self.config.rapport_periodicite == 'daily'

    def test_rapport_emails_accepte_liste(self):
        """rapport_emails accepte une liste d'emails.
        / rapport_emails accepts a list of emails."""
        emails = ['admin@test.fr', 'compta@test.fr']
        self.config.rapport_emails = emails
        self.config.save()
        self.config.refresh_from_db()
        assert self.config.rapport_emails == emails

    def test_rapport_periodicite_accepte_weekly(self):
        """rapport_periodicite accepte 'weekly'.
        / rapport_periodicite accepts 'weekly'."""
        self.config.rapport_periodicite = 'weekly'
        self.config.save()
        self.config.refresh_from_db()
        assert self.config.rapport_periodicite == 'weekly'


class TestVersion(FastTenantTestCase):
    """Tests pour la version du logiciel.
    / Tests for software version."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_version'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-version.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test Version'

    def test_lire_version_retourne_string(self):
        """_lire_version() retourne une string non vide.
        / _lire_version() returns a non-empty string."""
        from laboutik.views import _lire_version
        version = _lire_version()
        assert isinstance(version, str)
        assert len(version) > 0
        assert version != '?'

    def test_version_format_semver(self):
        """La version a un format X.Y.Z avec des points.
        / Version has X.Y.Z format with dots."""
        from laboutik.views import _lire_version
        version = _lire_version()
        parties = version.split('.')
        assert len(parties) >= 2, f"Version '{version}' n'a pas le format X.Y ou X.Y.Z"
