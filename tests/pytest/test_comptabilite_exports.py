"""
Tests pour les exports comptables (CSV, Excel, PDF, FEC).
/ Tests for accounting exports (CSV, Excel, PDF, FEC).

LOCALISATION : tests/pytest/test_comptabilite_exports.py

Meme pattern que test_comptabilite_admin.py : live dev DB.
/ Same pattern as test_comptabilite_admin.py: live dev DB.
"""
from datetime import timedelta

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context


@pytest.fixture(scope="session")
def django_db_setup():
    """Use the existing dev DB."""
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client_avec_cloture():
    """
    Cree un admin client + 1 cloture J sur une periode passee (eviter
    les collisions avec d'autres tests). Retourne (client, domain, tenant,
    cloture_uuid).
    / Build admin client + 1 daily closure on a distant past period.
    """
    from django.test import Client as DjangoClient
    from Customers.models import Client as TenantClient
    from AuthBillet.models import TibilletUser
    from comptabilite.models import ClotureCaisse
    from comptabilite.tasks import generer_cloture_pour_tenant

    # Tenant EXPLICITE : .exclude(public).first() est non deterministe et peut
    # renvoyer un tenant 'waiting_config' (categorie W, cree par les tests E2E
    # d'onboarding) qui n'a AUCUN domaine → AttributeError au setup.
    # / EXPLICIT tenant: .exclude(public).first() is non-deterministic and may
    # return a 'waiting_config' tenant (W category, created by onboarding E2E
    # tests) which has NO domain → AttributeError at setup.
    tenant = TenantClient.objects.get(schema_name="lespass")
    domain = tenant.domains.first()

    with tenant_context(tenant):
        admin_user, _ = TibilletUser.objects.get_or_create(
            email="admin@admin.com",
            defaults={"is_staff": True, "is_superuser": True, "is_active": True},
        )
        if not admin_user.is_staff:
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.is_active = True
            admin_user.save()

        fin = timezone.now() - timedelta(days=200)
        debut = fin - timedelta(days=1)
        ClotureCaisse.objects.filter(datetime_debut=debut, datetime_fin=fin).delete()
        cloture_uuid = generer_cloture_pour_tenant(
            schema_name=tenant.schema_name,
            niveau="J",
            datetime_debut_iso=debut.isoformat(),
            datetime_fin_iso=fin.isoformat(),
        )

    client = DjangoClient(HTTP_HOST=domain.domain)
    client.force_login(admin_user)
    return client, domain, tenant, cloture_uuid


def test_export_csv_retourne_fichier(admin_client_avec_cloture):
    """
    GET .../exporter-csv/ retourne un fichier CSV.
    / GET .../exporter-csv/ returns a CSV file.
    """
    client, _, tenant, cloture_uuid = admin_client_avec_cloture
    url = f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/exporter-csv/"
    response = client.get(url)

    assert response.status_code == 200, (
        f"Status {response.status_code} — content: {response.content[:300]}"
    )
    assert "text/csv" in response["Content-Type"]
    assert "attachment" in response["Content-Disposition"]
    assert ".csv" in response["Content-Disposition"]
    contenu = response.content.decode("utf-8-sig")  # decode UTF-8 BOM
    # En-tete attendue (FR)
    assert "Rapport" in contenu or "cloture" in contenu.lower()

    # Cleanup
    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()


def test_export_excel_retourne_fichier(admin_client_avec_cloture):
    """
    GET .../exporter-excel/ retourne un fichier .xlsx valide.
    / GET .../exporter-excel/ returns a valid .xlsx file.
    """
    client, _, tenant, cloture_uuid = admin_client_avec_cloture
    url = f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/exporter-excel/"
    response = client.get(url)

    assert response.status_code == 200, (
        f"Status {response.status_code} — content: {response.content[:300]}"
    )
    assert "spreadsheetml" in response["Content-Type"]
    assert "attachment" in response["Content-Disposition"]
    assert ".xlsx" in response["Content-Disposition"]
    # Taille minimale d'un .xlsx valide (zip + xml internes) : > 4 KB
    assert len(response.content) > 4000
    # Signature d'un fichier zip (xlsx = zip) : 'PK' au debut
    assert response.content[:2] == b"PK"

    # Cleanup
    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()


def test_export_pdf_retourne_fichier(admin_client_avec_cloture):
    """
    GET .../exporter-pdf/ retourne un PDF A4 valide.
    / GET .../exporter-pdf/ returns a valid A4 PDF.
    """
    client, _, tenant, cloture_uuid = admin_client_avec_cloture
    url = f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/exporter-pdf/"
    response = client.get(url)

    assert response.status_code == 200, (
        f"Status {response.status_code} — content: {response.content[:300]}"
    )
    assert response["Content-Type"] == "application/pdf"
    assert "attachment" in response["Content-Disposition"]
    assert ".pdf" in response["Content-Disposition"]
    # Signature magic d'un PDF : commence par '%PDF-'
    # / Magic signature of a PDF
    assert response.content[:5] == b"%PDF-"
    # Taille minimale d'un PDF valide : > 1 KB
    assert len(response.content) > 1000

    # Cleanup
    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()


def test_export_fec_retourne_fichier(admin_client_avec_cloture):
    """
    GET .../exporter-fec/ retourne un fichier FEC tabule (18 colonnes).
    / GET .../exporter-fec/ returns a tab-separated FEC file (18 columns).
    """
    client, _, tenant, cloture_uuid = admin_client_avec_cloture
    url = f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/exporter-fec/"
    response = client.get(url)

    assert response.status_code == 200, (
        f"Status {response.status_code} — content: {response.content[:300]}"
    )
    assert "text/plain" in response["Content-Type"]
    assert "cp1252" in response["Content-Type"].lower() or "windows-1252" in response["Content-Type"].lower()
    assert "attachment" in response["Content-Disposition"]
    assert ".txt" in response["Content-Disposition"]
    # FEC commence par le nom du fichier 'FEC-'
    # / Filename starts with 'FEC-'
    assert "FEC-" in response["Content-Disposition"]

    # Decoder en CP1252 et verifier la structure
    # / Decode in CP1252 and check structure
    contenu = response.content.decode("cp1252")
    lignes = contenu.split("\r\n")
    assert len(lignes) >= 1, "Au moins l'en-tete doit etre presente"
    # 18 colonnes = 17 tabulations sur chaque ligne
    # / 18 columns = 17 tabs per line
    premiere_ligne = lignes[0]
    assert premiere_ligne.count("\t") == 17, (
        f"En-tete doit avoir 17 tabs (18 colonnes), trouve : {premiere_ligne.count(chr(9))}"
    )
    # En-tete contient les colonnes FEC obligatoires
    # / Header contains mandatory FEC columns
    assert "JournalCode" in premiere_ligne
    assert "EcritureNum" in premiere_ligne
    assert "CompteNum" in premiere_ligne

    # Cleanup
    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()


def test_export_csv_comptable_get_retourne_form(admin_client_avec_cloture):
    """
    GET .../exporter-csv-comptable/ retourne le form HTMX avec select profil.
    / GET returns the HTMX form with profile select.
    """
    client, _, tenant, cloture_uuid = admin_client_avec_cloture
    response = client.get(
        f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/exporter-csv-comptable/"
    )
    assert response.status_code == 200
    contenu = response.content.decode("utf-8")
    assert 'data-testid="comptabilite-form-csv-comptable"' in contenu
    assert 'data-testid="comptabilite-select-profil"' in contenu
    # Au moins un profil dans le select
    # / At least one profile in the select
    assert "Sage" in contenu or "EBP" in contenu or "Paheko" in contenu

    # Cleanup
    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()


def test_export_csv_comptable_post_telecharge(admin_client_avec_cloture):
    """
    POST .../exporter-csv-comptable/ avec profil=sage_50 telecharge un CSV.
    / POST with profil=sage_50 downloads a CSV file.
    """
    client, _, tenant, cloture_uuid = admin_client_avec_cloture
    response = client.post(
        f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/exporter-csv-comptable/",
        {"profil": "sage_50"},
    )
    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    assert "compta-sage_50-" in response["Content-Disposition"]

    # Cleanup
    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()
