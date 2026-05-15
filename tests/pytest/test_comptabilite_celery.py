"""
Tests pour les wrappers Celery + email auto de la cloture comptable.
/ Tests for Celery wrappers + automatic closure report email.

LOCALISATION : tests/pytest/test_comptabilite_celery.py
Pattern : live dev DB.
"""
from datetime import timedelta
from unittest.mock import patch, MagicMock

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context


@pytest.fixture(scope="session")
def django_db_setup():
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db


def test_cron_cloture_quotidienne_appelle_management_command():
    """
    Le wrapper @app.task cron_cloture_quotidienne appelle bien
    call_command('generer_cloture', '--niveau=J').
    / The wrapper calls the management command with niveau=J.
    """
    from TiBillet.celery import cron_cloture_quotidienne
    with patch("TiBillet.celery.call_command") as mock_call:
        cron_cloture_quotidienne()
        mock_call.assert_called_with("generer_cloture", "--niveau=J")


def test_cron_cloture_hebdomadaire_appelle_management_command():
    """Wrapper hebdomadaire -> --niveau=H."""
    from TiBillet.celery import cron_cloture_hebdomadaire
    with patch("TiBillet.celery.call_command") as mock_call:
        cron_cloture_hebdomadaire()
        mock_call.assert_called_with("generer_cloture", "--niveau=H")


def test_envoyer_email_cloture_skip_si_pas_de_config():
    """
    Si Configuration.rapport_emails est vide, l'email n'est PAS envoye.
    / If rapport_emails is empty, no email is sent.
    """
    from Customers.models import Client
    from comptabilite.models import ClotureCaisse
    from comptabilite.tasks import (
        envoyer_email_cloture, generer_cloture_pour_tenant,
    )
    from BaseBillet.models import Configuration

    tenant = Client.objects.exclude(schema_name="public").first()
    fin = timezone.now() - timedelta(days=220)
    debut = fin - timedelta(days=1)

    with tenant_context(tenant):
        ClotureCaisse.objects.filter(datetime_debut=debut, datetime_fin=fin).delete()
        cloture_uuid = generer_cloture_pour_tenant(
            schema_name=tenant.schema_name, niveau="J",
            datetime_debut_iso=debut.isoformat(),
            datetime_fin_iso=fin.isoformat(),
        )
        # On vide rapport_emails pour ce test
        # / Empty rapport_emails for this test
        config = Configuration.get_solo()
        old_emails = config.rapport_emails
        old_periodicite = config.rapport_periodicite
        config.rapport_emails = ""
        config.save()

    try:
        with patch("BaseBillet.tasks.CeleryMailerClass") as MockMailer:
            result = envoyer_email_cloture(tenant.schema_name, cloture_uuid)
            assert result is False
            MockMailer.assert_not_called()
    finally:
        # Cleanup
        with tenant_context(tenant):
            config = Configuration.get_solo()
            config.rapport_emails = old_emails
            config.rapport_periodicite = old_periodicite
            config.save()
            ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()


def test_envoyer_email_cloture_envoie_si_config_ok():
    """
    Si rapport_emails est configure ET rapport_periodicite matche le niveau,
    CeleryMailerClass est instancie avec le PDF en attachement.
    / If config matches, CeleryMailerClass is called with the PDF attachment.
    """
    from Customers.models import Client
    from comptabilite.models import ClotureCaisse
    from comptabilite.tasks import (
        envoyer_email_cloture, generer_cloture_pour_tenant,
    )
    from BaseBillet.models import Configuration

    tenant = Client.objects.exclude(schema_name="public").first()
    fin = timezone.now() - timedelta(days=230)
    debut = fin - timedelta(days=1)

    with tenant_context(tenant):
        ClotureCaisse.objects.filter(datetime_debut=debut, datetime_fin=fin).delete()
        cloture_uuid = generer_cloture_pour_tenant(
            schema_name=tenant.schema_name, niveau="J",
            datetime_debut_iso=debut.isoformat(),
            datetime_fin_iso=fin.isoformat(),
        )
        config = Configuration.get_solo()
        old_emails = config.rapport_emails
        old_periodicite = config.rapport_periodicite
        config.rapport_emails = "compta@example.com, tresorerie@example.com"
        config.rapport_periodicite = "J"
        config.save()

    try:
        # Mock CeleryMailerClass to capture the args
        # / Mock CeleryMailerClass to capture args
        with patch("comptabilite.tasks.CeleryMailerClass") as MockMailer:
            mock_instance = MagicMock()
            mock_instance.send.return_value = 1  # Django send() returns 1 on success
            MockMailer.return_value = mock_instance

            envoyer_email_cloture(tenant.schema_name, cloture_uuid)

            assert MockMailer.called, "CeleryMailerClass should be instantiated"
            kwargs = MockMailer.call_args.kwargs
            # 2 destinataires parses (split ",")
            # / 2 recipients parsed
            assert kwargs.get("email") == [
                "compta@example.com", "tresorerie@example.com",
            ]
            # 1 PDF en attachement
            # / 1 PDF attachment
            assert kwargs.get("attached_files") is not None
            assert len(kwargs["attached_files"]) == 1
            # Filename contient 'cloture-'
            filename = list(kwargs["attached_files"].keys())[0]
            assert filename.startswith("cloture-") and filename.endswith(".pdf")
            mock_instance.send.assert_called_once()
    finally:
        with tenant_context(tenant):
            config = Configuration.get_solo()
            config.rapport_emails = old_emails
            config.rapport_periodicite = old_periodicite
            config.save()
            ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()
