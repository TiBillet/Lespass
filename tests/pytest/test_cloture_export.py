"""
tests/pytest/test_cloture_export.py — Tests export PDF/CSV/Email de la cloture.
tests/pytest/test_cloture_export.py — Tests for closure PDF/CSV/Email export.

Couvre : generer_pdf_cloture, generer_csv_cloture, endpoints PDF/CSV, task email.
Covers: generer_pdf_cloture, generer_csv_cloture, PDF/CSV endpoints, email task.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_cloture_export.py -v --api-key dummy
"""

import os
import sys
import uuid

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import pytest

from django.utils import timezone
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod,
)
from Customers.models import Client
from laboutik.models import PointDeVente, ClotureCaisse


# Schema tenant utilise pour les tests.
# / Tenant schema used for tests.
TENANT_SCHEMA = 'lespass'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass' (doit exister dans la base).
    / The 'lespass' tenant (must exist in DB)."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def test_data(tenant):
    """Lance create_test_pos_data pour s'assurer que les donnees existent.
    / Runs create_test_pos_data to ensure test data exists."""
    from django.core.management import call_command
    call_command('create_test_pos_data')
    return True


@pytest.fixture(scope="module")
def admin_user(tenant):
    """Un utilisateur admin du tenant.
    / A tenant admin user."""
    with schema_context(TENANT_SCHEMA):
        email = 'admin-test-export@tibillet.localhost'
        user, created = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'is_staff': True,
                'is_active': True,
            },
        )
        user.client_admin.add(tenant)
        return user


@pytest.fixture(scope="module")
def premier_pv(test_data):
    """Le premier point de vente (Bar).
    / The first point of sale (Bar)."""
    with schema_context(TENANT_SCHEMA):
        return PointDeVente.objects.filter(hidden=False).order_by('poid_liste').first()


@pytest.fixture(scope="module")
def cloture_avec_donnees(admin_user, tenant, premier_pv):
    """
    Cree une ClotureCaisse avec des donnees realistes dans rapport_json.
    Creates a ClotureCaisse with realistic data in rapport_json.
    """
    with schema_context(TENANT_SCHEMA):
        rapport_json = {
            "par_produit": {
                "Bière pression": {"total": 1500, "qty": 3},
                "Coca-Cola": {"total": 500, "qty": 2},
            },
            "par_categorie": {
                "Boissons": 2000,
            },
            "par_moyen_paiement": {
                "especes": 500,
                "cb": 1000,
                "nfc": 500,
            },
            "par_tva": {
                "20.00%": {
                    "taux": 20.0,
                    "total_ttc": 2000,
                    "total_ht": 1667,
                    "total_tva": 333,
                },
            },
            "commandes": {
                "total": 5,
                "annulees": 1,
            },
        }
        cloture = ClotureCaisse.objects.create(
            point_de_vente=premier_pv,
            responsable=admin_user,
            datetime_ouverture=timezone.now() - timezone.timedelta(hours=8),
            total_especes=500,
            total_carte_bancaire=1000,
            total_cashless=500,
            total_general=2000,
            nombre_transactions=5,
            rapport_json=rapport_json,
        )
        return cloture


# ---------------------------------------------------------------------------
# Tests PDF
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestGenerationPDF:
    """Tests de la generation PDF.
    / PDF generation tests."""

    def test_generer_pdf_retourne_bytes(self, cloture_avec_donnees):
        """Le PDF genere commence par %PDF (signature PDF valide).
        / Generated PDF starts with %PDF (valid PDF signature)."""
        with schema_context(TENANT_SCHEMA):
            from laboutik.pdf import generer_pdf_cloture
            pdf_bytes = generer_pdf_cloture(cloture_avec_donnees)

            assert isinstance(pdf_bytes, bytes)
            assert pdf_bytes[:5] == b'%PDF-'
            assert len(pdf_bytes) > 100


# ---------------------------------------------------------------------------
# Tests CSV
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestGenerationCSV:
    """Tests de la generation CSV.
    / CSV generation tests."""

    def test_generer_csv_contient_produits(self, cloture_avec_donnees):
        """Le CSV contient les noms de produits du rapport.
        / CSV contains product names from the report."""
        with schema_context(TENANT_SCHEMA):
            from laboutik.csv_export import generer_csv_cloture
            csv_string = generer_csv_cloture(cloture_avec_donnees)

            assert isinstance(csv_string, str)
            assert "Bière pression" in csv_string or "Bi" in csv_string
            assert "Coca-Cola" in csv_string

    def test_generer_csv_contient_tva(self, cloture_avec_donnees):
        """Le CSV contient la section TVA.
        / CSV contains the VAT section."""
        with schema_context(TENANT_SCHEMA):
            from laboutik.csv_export import generer_csv_cloture
            csv_string = generer_csv_cloture(cloture_avec_donnees)

            assert "20.00%" in csv_string


# ---------------------------------------------------------------------------
# Tests endpoints
# ---------------------------------------------------------------------------

def _make_client(admin_user, tenant):
    """Cree un client DRF authentifie comme admin du tenant.
    / Creates a DRF client authenticated as tenant admin."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
    return client


@pytest.mark.usefixtures("test_data")
class TestEndpoints:
    """Tests des endpoints HTTP.
    / HTTP endpoint tests."""

    def test_endpoint_pdf_200(self, admin_user, tenant, cloture_avec_donnees):
        """GET /laboutik/caisse/<uuid>/rapport_pdf/ retourne 200 + application/pdf.
        / Returns 200 + application/pdf."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            url = f"/laboutik/caisse/{cloture_avec_donnees.uuid}/rapport_pdf/"
            response = client.get(url)

            assert response.status_code == 200
            assert response["Content-Type"] == "application/pdf"
            assert response.content[:5] == b'%PDF-'

    def test_endpoint_csv_200(self, admin_user, tenant, cloture_avec_donnees):
        """GET /laboutik/caisse/<uuid>/rapport_csv/ retourne 200 + text/csv.
        / Returns 200 + text/csv."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            url = f"/laboutik/caisse/{cloture_avec_donnees.uuid}/rapport_csv/"
            response = client.get(url)

            assert response.status_code == 200
            assert "text/csv" in response["Content-Type"]
            assert len(response.content) > 0

    def test_endpoint_pdf_uuid_inconnu_404(self, admin_user, tenant):
        """GET avec UUID inexistant retourne 404.
        / GET with unknown UUID returns 404."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            fake_uuid = uuid.uuid4()
            url = f"/laboutik/caisse/{fake_uuid}/rapport_pdf/"
            response = client.get(url)

            assert response.status_code == 404

    def test_envoyer_rapport_declenche_task(
        self, admin_user, tenant, cloture_avec_donnees,
    ):
        """POST envoyer_rapport/ appelle la task Celery avec les bons args.
        / POST envoyer_rapport/ calls the Celery task with correct args."""
        from unittest.mock import patch, MagicMock

        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            url = f"/laboutik/caisse/{cloture_avec_donnees.uuid}/envoyer_rapport/"

            # Patch la task Celery la ou elle est importee (import inline dans la vue)
            # Patch the Celery task where it's imported (inline import in the view)
            with patch('laboutik.tasks.envoyer_rapport_cloture') as mock_task:
                mock_task.delay = MagicMock()
                response = client.post(url, data={})

                assert response.status_code == 200
                mock_task.delay.assert_called_once_with(
                    TENANT_SCHEMA,
                    str(cloture_avec_donnees.uuid),
                    None,  # pas d'email fourni / no email provided
                )


# ---------------------------------------------------------------------------
# Test envoi reel d'email (SMTP)
# / Real email sending test (SMTP)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestEnvoiReelEmail:
    """Envoie un vrai email avec PDF + CSV via SMTP.
    / Sends a real email with PDF + CSV via SMTP."""

    def test_envoyer_rapport_email_reel(self, cloture_avec_donnees):
        """
        Appelle la task Celery en synchrone (pas .delay) pour envoyer
        un vrai email a ADMIN_EMAIL avec les PJ PDF + CSV.
        Calls the Celery task synchronously (not .delay) to send
        a real email to ADMIN_EMAIL with PDF + CSV attachments.
        """
        with schema_context(TENANT_SCHEMA):
            from laboutik.tasks import envoyer_rapport_cloture

            admin_email = os.environ.get('ADMIN_EMAIL')
            assert admin_email, "ADMIN_EMAIL non defini dans l'environnement"

            # Appel synchrone (sans .delay) — envoie vraiment l'email
            # Synchronous call (no .delay) — actually sends the email
            result = envoyer_rapport_cloture(
                TENANT_SCHEMA,
                str(cloture_avec_donnees.uuid),
                admin_email,
            )

            assert result is True, "L'envoi de l'email a echoue"


class TestExportDepuisUnVraiRapport:
    """Les exports partent d'un rapport REELLEMENT produit par le service.

    Les tests voisins fabriquent un `rapport_json` a la main. C'est commode,
    mais ca rend le fichier aveugle a la seule chose qui compte ici : le PDF et
    le CSV lisent-ils les cles que le service produit VRAIMENT ? Un rapport
    invente repond toujours oui.

    Ces tests-ci construisent le rapport avec `RapportComptableService`, comme la
    cloture le fait en production.
    / The neighbouring tests hand-craft a rapport_json, which makes them blind to
    the only thing that matters: do the exports read the keys the service really
    produces? These build the report with RapportComptableService, as the real
    closure does.
    """

    @pytest.fixture
    def cloture_depuis_le_service(self, admin_user, tenant, premier_pv):
        """Une vente reelle, un rapport calcule, une cloture qui le porte.
        / A real sale, a computed report, a closure carrying it."""
        from datetime import timedelta

        from laboutik.reports import RapportComptableService

        nom_du_produit = f"Export test {uuid.uuid4().hex[:8]}"

        with schema_context(TENANT_SCHEMA):
            produit = Product.objects.create(
                name=nom_du_produit,
                categorie_article=Product.NONE,
            )
            tarif = Price.objects.create(product=produit, name="Unite", prix=10)
            produit_vendu = ProductSold.objects.create(product=produit)
            tarif_vendu = PriceSold.objects.create(
                productsold=produit_vendu, price=tarif, prix=10,
            )
            ligne = LigneArticle.objects.create(
                pricesold=tarif_vendu,
                qty=2,
                amount=1000,
                vat=20,
                payment_method=PaymentMethod.CASH,
                status=LigneArticle.VALID,
                sale_origin=SaleOrigin.LABOUTIK,
                point_de_vente=premier_pv,
            )

            maintenant = timezone.now()
            service = RapportComptableService(
                point_de_vente=premier_pv,
                datetime_debut=maintenant - timedelta(minutes=5),
                datetime_fin=maintenant + timedelta(minutes=5),
            )
            rapport = service.generer_rapport_complet()

            cloture = ClotureCaisse.objects.create(
                point_de_vente=premier_pv,
                responsable=admin_user,
                datetime_ouverture=maintenant - timedelta(minutes=5),
                total_especes=2000,
                total_carte_bancaire=0,
                total_cashless=0,
                total_general=2000,
                nombre_transactions=1,
                rapport_json=rapport,
            )

            yield {"cloture": cloture, "nom_du_produit": nom_du_produit}

            # Ordre impose par les FK : cloture, puis ligne, puis les objets de
            # catalogue. Le `.delete()` d'un `Product` sans image leve un
            # `TypeError` dans django-stdimage (son callback post_delete
            # travaille sur un chemin `None`) : on l'enveloppe pour ne pas faire
            # echouer le teardown sur une lib tierce (PIEGES 10.1).
            # / Order imposed by the FKs. Deleting a Product without an image
            # raises TypeError inside django-stdimage, so we wrap it.
            cloture.delete()
            ligne.delete()
            tarif_vendu.delete()
            produit_vendu.delete()
            tarif.delete()
            try:
                produit.delete()
            except TypeError:
                pass

    def test_le_csv_contient_le_detail_des_produits_vendus(
        self, cloture_depuis_le_service,
    ):
        """Le produit vendu apparait dans le CSV de cloture.

        C'est le test qui manquait : le CSV lisait des cles que le service ne
        produit plus, et rendait des sections vides sans lever d'erreur.
        / The missing test: the CSV read keys the service no longer produces and
        silently rendered empty sections.
        """
        with schema_context(TENANT_SCHEMA):
            from laboutik.csv_export import generer_csv_cloture

            contenu = generer_csv_cloture(cloture_depuis_le_service["cloture"])

        assert cloture_depuis_le_service["nom_du_produit"] in contenu
        assert "Ventilation TVA" in contenu or "VAT breakdown" in contenu

    def test_le_pdf_se_genere_depuis_un_vrai_rapport(
        self, cloture_depuis_le_service,
    ):
        """Le PDF se fabrique sans erreur a partir du rapport du service.
        / The PDF builds without error from the service's report."""
        with schema_context(TENANT_SCHEMA):
            from laboutik.pdf import generer_pdf_cloture

            pdf = generer_pdf_cloture(cloture_depuis_le_service["cloture"])

        assert isinstance(pdf, bytes)
        assert pdf.startswith(b"%PDF")

    def test_les_sections_de_detail_ne_sont_pas_vides(
        self, cloture_depuis_le_service,
    ):
        """La traduction du rapport vers les sections d'export produit du contenu.

        Un dictionnaire vide passerait tous les tests d'export precedents, qui se
        contentent de verifier qu'aucune exception n'est levee.
        / An empty dict would pass every previous export test, which only check
        that no exception is raised.
        """
        from laboutik.reports import sections_de_detail_pour_export

        sections = sections_de_detail_pour_export(
            cloture_depuis_le_service["cloture"].rapport_json,
        )

        assert sections["par_produit"], "Aucun produit dans les sections d'export"
        assert sections["par_categorie"], "Aucune categorie dans les sections d'export"
        assert sections["par_tva"], "Aucune ventilation TVA dans les sections d'export"

    def test_une_cloture_ancienne_reste_lisible(self, cloture_avec_donnees):
        """Les cloture archivees avant le changement de format s'exportent encore.

        Leur `rapport_json` porte deja les sections a plat. Les reconstruire
        depuis `detail_ventes`, absent chez elles, viderait leurs exports — une
        cloture archivee doit se reimprimer a l'identique des annees apres.
        / Closures archived before the format change already carry flat sections.
        An archived closure must reprint identically years later.
        """
        from laboutik.reports import sections_de_detail_pour_export

        sections = sections_de_detail_pour_export(cloture_avec_donnees.rapport_json)

        assert "Bière pression" in sections["par_produit"]
        assert sections["par_categorie"]["Boissons"] == 2000
        assert sections["par_tva"]["20.00%"]["total_ht"] == 1667
