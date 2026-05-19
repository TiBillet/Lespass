"""
Tests pour les exports CSV comptables (profils Sage 50, EBP, Paheko).
/ Tests for accounting CSV exports (Sage 50, EBP, Paheko profiles).

LOCALISATION : tests/pytest/test_comptabilite_csv_comptable.py
"""
from datetime import timedelta

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


@pytest.fixture
def cloture_de_test():
    """Cree une cloture sur une periode passee distincte. Retourne (tenant, cloture_uuid)."""
    from Customers.models import Client
    from comptabilite.models import ClotureCaisse
    from comptabilite.tasks import generer_cloture_pour_tenant

    tenant = Client.objects.exclude(schema_name="public").first()
    fin = timezone.now() - timedelta(days=210)
    debut = fin - timedelta(days=1)
    with tenant_context(tenant):
        ClotureCaisse.objects.filter(datetime_debut=debut, datetime_fin=fin).delete()
        uuid = generer_cloture_pour_tenant(
            schema_name=tenant.schema_name,
            niveau="J",
            datetime_debut_iso=debut.isoformat(),
            datetime_fin_iso=fin.isoformat(),
        )
    yield tenant, uuid
    # Cleanup
    with tenant_context(tenant):
        ClotureCaisse.objects.filter(uuid=uuid).delete()


def test_profils_csv_disponibles():
    """Le module profils_csv expose 3 profils : sage_50, ebp, paheko."""
    from comptabilite.profils_csv import PROFILS
    assert "sage_50" in PROFILS
    assert "ebp" in PROFILS
    assert "paheko" in PROFILS


def test_generer_csv_comptable_sage_50(cloture_de_test):
    """Profil Sage 50 : separateur ';', UTF-8 BOM, mode DEBIT_CREDIT."""
    from comptabilite.models import ClotureCaisse
    from comptabilite.csv_comptable import generer_csv_comptable
    tenant, cloture_uuid = cloture_de_test
    with tenant_context(tenant):
        cloture = ClotureCaisse.objects.get(uuid=cloture_uuid)
        bytes_data, filename, content_type, avertissements = generer_csv_comptable(
            cloture, "sage_50"
        )
        assert filename.endswith(".csv")
        assert "text/csv" in content_type
        # UTF-8 with BOM
        contenu = bytes_data.decode("utf-8-sig")
        # Separateur ;
        premiere_ligne = contenu.split("\n")[0]
        assert ";" in premiere_ligne
        # Au moins une colonne attendue
        assert "JournalCode" in contenu or "CompteNum" in contenu


def test_generer_csv_comptable_ebp(cloture_de_test):
    """Profil EBP : separateur ',', encodage CP1252, mode MONTANT_SENS."""
    from comptabilite.models import ClotureCaisse
    from comptabilite.csv_comptable import generer_csv_comptable
    tenant, cloture_uuid = cloture_de_test
    with tenant_context(tenant):
        cloture = ClotureCaisse.objects.get(uuid=cloture_uuid)
        bytes_data, filename, content_type, avertissements = generer_csv_comptable(
            cloture, "ebp"
        )
        # CP1252 encoding
        contenu = bytes_data.decode("cp1252")
        # Separateur ,
        premiere_ligne = contenu.split("\n")[0]
        assert "," in premiere_ligne
        # Mode MONTANT_SENS : doit avoir colonne 'Sens'
        assert "Sens" in contenu


def test_generer_csv_comptable_paheko(cloture_de_test):
    """Profil Paheko : separateur ';', decimal ',', mode MONTANT_UNIQUE."""
    from comptabilite.models import ClotureCaisse
    from comptabilite.csv_comptable import generer_csv_comptable
    tenant, cloture_uuid = cloture_de_test
    with tenant_context(tenant):
        cloture = ClotureCaisse.objects.get(uuid=cloture_uuid)
        bytes_data, filename, content_type, avertissements = generer_csv_comptable(
            cloture, "paheko"
        )
        contenu = bytes_data.decode("utf-8")
        # Mode MONTANT_UNIQUE : compte_debit + compte_credit + montant
        assert "compte_debit" in contenu
        assert "compte_credit" in contenu


# ============================================================================
# S6 — 5 profils CSV supplementaires : Dolibarr, PennyLane, CIEL, ODOO, DOKO
# ============================================================================


def test_generer_csv_comptable_dolibarr(cloture_de_test):
    """Profil Dolibarr : separateur ',', UTF-8, mode DEBIT_CREDIT."""
    from comptabilite.models import ClotureCaisse
    from comptabilite.csv_comptable import generer_csv_comptable
    from comptabilite.profils_csv import PROFILS

    tenant, cloture_uuid = cloture_de_test
    assert "dolibarr" in PROFILS

    with tenant_context(tenant):
        cloture = ClotureCaisse.objects.get(uuid=cloture_uuid)
        bytes_data, filename, content_type, _ = generer_csv_comptable(cloture, "dolibarr")
        assert filename.endswith(".csv")
        contenu = bytes_data.decode("utf-8")
        premiere_ligne = contenu.split("\n")[0]
        assert "," in premiere_ligne
        assert "code_journal" in contenu or "compte" in contenu


def test_generer_csv_comptable_pennylane(cloture_de_test):
    """Profil PennyLane : separateur ';', UTF-8, mode DEBIT_CREDIT."""
    from comptabilite.models import ClotureCaisse
    from comptabilite.csv_comptable import generer_csv_comptable
    from comptabilite.profils_csv import PROFILS

    tenant, cloture_uuid = cloture_de_test
    assert "pennylane" in PROFILS

    with tenant_context(tenant):
        cloture = ClotureCaisse.objects.get(uuid=cloture_uuid)
        bytes_data, filename, content_type, _ = generer_csv_comptable(cloture, "pennylane")
        contenu = bytes_data.decode("utf-8")
        premiere_ligne = contenu.split("\n")[0]
        assert ";" in premiere_ligne
        assert "Compte" in contenu or "Journal" in contenu


def test_generer_csv_comptable_ciel(cloture_de_test):
    """Profil CIEL Compta : separateur '\\t' (tabulation), encodage CP1252."""
    from comptabilite.models import ClotureCaisse
    from comptabilite.csv_comptable import generer_csv_comptable
    from comptabilite.profils_csv import PROFILS

    tenant, cloture_uuid = cloture_de_test
    assert "ciel" in PROFILS

    with tenant_context(tenant):
        cloture = ClotureCaisse.objects.get(uuid=cloture_uuid)
        bytes_data, filename, content_type, _ = generer_csv_comptable(cloture, "ciel")
        assert filename.endswith(".txt")
        contenu = bytes_data.decode("cp1252")
        premiere_ligne = contenu.split("\n")[0]
        # Tabulation comme separateur
        assert "\t" in premiere_ligne


def test_generer_csv_comptable_odoo(cloture_de_test):
    """Profil Odoo : separateur ',', UTF-8, mode DEBIT_CREDIT."""
    from comptabilite.models import ClotureCaisse
    from comptabilite.csv_comptable import generer_csv_comptable
    from comptabilite.profils_csv import PROFILS

    tenant, cloture_uuid = cloture_de_test
    assert "odoo" in PROFILS

    with tenant_context(tenant):
        cloture = ClotureCaisse.objects.get(uuid=cloture_uuid)
        bytes_data, filename, content_type, _ = generer_csv_comptable(cloture, "odoo")
        contenu = bytes_data.decode("utf-8")
        premiere_ligne = contenu.split("\n")[0]
        assert "," in premiere_ligne
        assert "journal_id" in contenu or "account_id" in contenu


def test_generer_csv_comptable_doko(cloture_de_test):
    """Profil DOKO : separateur ';', UTF-8, mode DEBIT_CREDIT."""
    from comptabilite.models import ClotureCaisse
    from comptabilite.csv_comptable import generer_csv_comptable
    from comptabilite.profils_csv import PROFILS

    tenant, cloture_uuid = cloture_de_test
    assert "doko" in PROFILS

    with tenant_context(tenant):
        cloture = ClotureCaisse.objects.get(uuid=cloture_uuid)
        bytes_data, filename, content_type, _ = generer_csv_comptable(cloture, "doko")
        contenu = bytes_data.decode("utf-8")
        premiere_ligne = contenu.split("\n")[0]
        assert ";" in premiere_ligne
        assert "JournalCode" in contenu or "CompteNum" in contenu
