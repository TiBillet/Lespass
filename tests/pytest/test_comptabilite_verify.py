"""
Tests pour la management command verify_clotures.
/ Tests for the verify_clotures management command.

LOCALISATION : tests/pytest/test_comptabilite_verify.py
"""
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
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


def test_verify_clotures_signale_hash_modifie():
    """
    Quand on modifie hash_lignes en DB (simulation tampering), la commande
    signale l'anomalie.
    / If we tamper with hash_lignes in DB, the command flags the anomaly.
    """
    from Customers.models import Client
    from comptabilite.models import ClotureCaisse
    from comptabilite.tasks import generer_cloture_pour_tenant

    tenant = Client.objects.exclude(schema_name="public").first()
    fin = timezone.now() - timedelta(days=250)
    debut = fin - timedelta(days=1)

    with tenant_context(tenant):
        ClotureCaisse.objects.filter(datetime_debut=debut, datetime_fin=fin).delete()
        cloture_uuid = generer_cloture_pour_tenant(
            schema_name=tenant.schema_name, niveau="J",
            datetime_debut_iso=debut.isoformat(),
            datetime_fin_iso=fin.isoformat(),
        )
        # On corrompt le hash sans toucher aux donnees pour simuler une
        # modification manuelle indue du champ.
        # / Tamper with hash_lignes to simulate manual tampering.
        ClotureCaisse.objects.filter(uuid=cloture_uuid).update(
            hash_lignes="0" * 64,
        )

    try:
        out = StringIO()
        call_command(
            "verify_clotures",
            f"--tenant={tenant.schema_name}",
            stdout=out,
        )
        output = out.getvalue()
        # La commande doit signaler 'hash' ET 'invalide' (ou 'mismatch') dans le rapport
        # / Command must mention 'hash' AND 'invalid' (or 'mismatch') in report
        assert "hash" in output.lower()
        assert (
            "invalide" in output.lower()
            or "mismatch" in output.lower()
            or "different" in output.lower()
            or "anomalie" in output.lower()
        ), f"Output:\n{output}"
    finally:
        with tenant_context(tenant):
            ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()


def test_verify_clotures_signale_trou_sequentiel():
    """
    Quand on supprime une cloture du milieu de la sequence, la commande
    signale le trou.
    / If we delete a middle closure, the command flags the gap.
    """
    from Customers.models import Client
    from comptabilite.models import ClotureCaisse
    from comptabilite.tasks import generer_cloture_pour_tenant

    tenant = Client.objects.exclude(schema_name="public").first()

    with tenant_context(tenant):
        # On regarde le max actuel pour anchorer les nouvelles clotures bien plus haut.
        # / Anchor our test clotures well above current max.
        max_actuel = ClotureCaisse.objects.order_by("-numero_sequentiel").first()
        base_num = (max_actuel.numero_sequentiel + 100) if max_actuel else 1

    # On cree 3 clotures avec des periodes passees distinctes
    # / Create 3 clotures with distinct distant past periods
    uuids = []
    with tenant_context(tenant):
        for i in range(3):
            fin = timezone.now() - timedelta(days=260 + i * 2)
            debut = fin - timedelta(days=1)
            ClotureCaisse.objects.filter(datetime_debut=debut, datetime_fin=fin).delete()
            u = generer_cloture_pour_tenant(
                schema_name=tenant.schema_name, niveau="J",
                datetime_debut_iso=debut.isoformat(),
                datetime_fin_iso=fin.isoformat(),
            )
            uuids.append(u)

        # On supprime la 2eme pour creer un trou dans la sequence
        # / Delete the middle one to create a gap
        ClotureCaisse.objects.filter(uuid=uuids[1]).delete()

    try:
        out = StringIO()
        call_command(
            "verify_clotures",
            f"--tenant={tenant.schema_name}",
            stdout=out,
        )
        output = out.getvalue()
        # Le rapport doit mentionner un trou / un gap manquant
        # / Report must mention a gap / missing number
        assert (
            "trou" in output.lower()
            or "gap" in output.lower()
            or "manquant" in output.lower()
            or "missing" in output.lower()
        ), f"Output:\n{output}"
    finally:
        with tenant_context(tenant):
            # Nettoyage : supprimer celles qui restent
            # / Cleanup remaining
            for u in uuids:
                ClotureCaisse.objects.filter(uuid=u).delete()
