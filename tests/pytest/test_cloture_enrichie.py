"""
tests/pytest/test_cloture_enrichie.py — Tests Session 13 : clotures enrichies.
tests/pytest/test_cloture_enrichie.py — Tests Session 13: enriched closures.

Couvre : niveau, numero_sequentiel, total_perpetuel, hash_lignes,
         datetime_ouverture auto, cloture M, garde correction post-cloture.
Covers: level, sequential number, perpetual total, lines hash,
        auto datetime_ouverture, monthly closure, post-closure correction guard.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_cloture_enrichie.py -v
"""
import sys
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
from laboutik.models import (
    PointDeVente, ClotureCaisse, LaboutikConfiguration,
)
from laboutik.integrity import ligne_couverte_par_cloture

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
        email = 'admin-test-cloture-enrichie@tibillet.localhost'
        user, created = TibilletUser.objects.get_or_create(
            email=email,
            defaults={'username': email, 'is_staff': True, 'is_active': True},
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
def premier_produit_et_prix(premier_pv):
    """Premier produit du PV avec son prix.
    / First product of the PV with its price."""
    with schema_context(TENANT_SCHEMA):
        produit = premier_pv.products.filter(methode_caisse__isnull=False).first()
        prix = Price.objects.filter(
            product=produit, publish=True, asset__isnull=True,
        ).order_by('order').first()
        return produit, prix


def _make_client(admin_user, tenant):
    """Cree un client DRF authentifie comme admin du tenant.
    / Creates a DRF client authenticated as tenant admin."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
    return client


def _creer_ligne_article_directe(produit, prix, montant_centimes, payment_method_code, dt=None, pv=None):
    """
    Cree une LigneArticle directement en base.
    Creates a LigneArticle directly in DB.
    """
    product_sold, _ = ProductSold.objects.get_or_create(
        product=produit, event=None,
        defaults={'categorie_article': produit.categorie_article},
    )
    price_sold, _ = PriceSold.objects.get_or_create(
        productsold=product_sold, price=prix,
        defaults={'prix': prix.prix},
    )
    ligne = LigneArticle.objects.create(
        pricesold=price_sold, qty=1, amount=montant_centimes,
        sale_origin=SaleOrigin.LABOUTIK, payment_method=payment_method_code,
        status=LigneArticle.VALID, point_de_vente=pv,
    )
    if dt is not None:
        LigneArticle.objects.filter(pk=ligne.pk).update(datetime=dt)
        ligne.refresh_from_db()
    return ligne


def _nettoyer_clotures_et_perpetuel(pv=None):
    """Nettoie TOUTES les clotures du tenant et remet le total perpetuel a 0.
    La cloture est globale au tenant, pas par PV.
    / Cleans ALL closures for the tenant and resets perpetual total to 0.
    Closure is global to the tenant, not per POS."""
    ClotureCaisse.objects.all().delete()
    config = LaboutikConfiguration.get_solo()
    config.total_perpetuel = 0
    # Pas de update_fields sur un singleton django-solo (piege 9.86) :
    # si le singleton n'existe pas encore, save(update_fields=[...]) leve
    # DatabaseError "Save with update_fields did not affect any rows".
    # / No update_fields on a django-solo singleton (trap 9.86).
    config.save()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestClotureNumeroSequentiel:
    """2 clotures J → numeros sequentiels 1 et 2.
    / 2 daily closures → sequential numbers 1 and 2."""

    def test_cloture_journal_numero_sequentiel(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            _nettoyer_clotures_et_perpetuel(premier_pv)

            # Cloture 1 / Closure 1
            _creer_ligne_article_directe(produit, prix, 500, PaymentMethod.CASH, pv=premier_pv)
            client = _make_client(admin_user, tenant)
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            cloture1 = ClotureCaisse.objects.filter(
                niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('-numero_sequentiel').first()
            assert cloture1.numero_sequentiel == 1
            assert cloture1.niveau == ClotureCaisse.JOURNALIERE

            # Cloture 2 / Closure 2
            _creer_ligne_article_directe(produit, prix, 300, PaymentMethod.CC, pv=premier_pv)
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            cloture2 = ClotureCaisse.objects.filter(
                niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('-numero_sequentiel').first()
            assert cloture2.numero_sequentiel == 2


@pytest.mark.usefixtures("test_data")
class TestClotureTotalPerpetuel:
    """cloture 5000 + cloture 3000 → perpetuel 8000.
    / closure 5000 + closure 3000 → perpetual 8000."""

    def test_cloture_journal_total_perpetuel(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Le total perpetuel est incremente du total de chaque cloture.
        On verifie le delta entre 2 clotures successives.
        / Perpetual total is incremented by each closure's total.
        We verify the delta between 2 successive closures.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix

            # Lire le total perpetuel actuel / Read current perpetual total
            config = LaboutikConfiguration.get_solo()
            perpetuel_avant = config.total_perpetuel

            # Cloturer tout ce qui traine / Close any pending sales
            client = _make_client(admin_user, tenant)
            client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            config.refresh_from_db()
            perpetuel_apres_nettoyage = config.total_perpetuel

            # Cloture avec 5000 centimes / Closure with 5000 cents
            _creer_ligne_article_directe(produit, prix, 5000, PaymentMethod.CASH, pv=premier_pv)
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            config.refresh_from_db()
            perpetuel_apres_cloture1 = config.total_perpetuel
            delta1 = perpetuel_apres_cloture1 - perpetuel_apres_nettoyage
            assert delta1 == 5000

            # Cloture avec 3000 centimes / Closure with 3000 cents
            _creer_ligne_article_directe(produit, prix, 3000, PaymentMethod.CC, pv=premier_pv)
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            config.refresh_from_db()
            perpetuel_apres_cloture2 = config.total_perpetuel
            delta2 = perpetuel_apres_cloture2 - perpetuel_apres_cloture1
            assert delta2 == 3000

            # Le total perpetuel a augmente de 8000 au total / Total increase is 8000
            delta_total = perpetuel_apres_cloture2 - perpetuel_apres_nettoyage
            assert delta_total == 8000

            # Le snapshot sur la cloture correspond au total config
            # / The snapshot on the closure matches the config total
            derniere_cloture = ClotureCaisse.objects.filter(
                niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('-numero_sequentiel').first()
            assert derniere_cloture.total_perpetuel == perpetuel_apres_cloture2


@pytest.mark.usefixtures("test_data")
class TestClotureMensuelle:
    """Cloture M agrege les J du mois.
    / Monthly closure aggregates daily closures."""

    def test_cloture_mensuelle(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        with schema_context(TENANT_SCHEMA):
            from laboutik.tasks import _generer_cloture_agregee
            from BaseBillet.models import Configuration
            from datetime import date

            produit, prix = premier_produit_et_prix

            # Activer module_caisse : _generer_cloture_agregee court-circuite
            # silencieusement si le module n'est pas actif sur le tenant.
            # / Enable module_caisse: _generer_cloture_agregee silently returns
            # if the module is not active on the tenant.
            config_base = Configuration.get_solo()
            if not config_base.module_caisse:
                config_base.module_caisse = True
                config_base.save()

            # Cloturer tout ce qui traine / Close any pending sales
            client = _make_client(admin_user, tenant)
            client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})

            # Supprimer les clotures M existantes pour ce PV
            # / Delete existing M closures for this POS
            ClotureCaisse.objects.filter(
                niveau=ClotureCaisse.MENSUELLE,
            ).delete()

            # Compter les clotures J existantes ce mois-ci
            # / Count existing daily closures this month
            aujourd_hui = date.today()
            nb_j_avant = ClotureCaisse.objects.filter(
                niveau=ClotureCaisse.JOURNALIERE,
            ).count()

            # Creer 2 clotures J supplementaires / Create 2 more daily closures
            _creer_ligne_article_directe(produit, prix, 2000, PaymentMethod.CASH, pv=premier_pv)
            client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})

            _creer_ligne_article_directe(produit, prix, 3000, PaymentMethod.CC, pv=premier_pv)
            client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})

            # Compter les J apres / Count daily closures after
            nb_j_apres = ClotureCaisse.objects.filter(
                niveau=ClotureCaisse.JOURNALIERE,
            ).count()
            assert nb_j_apres >= nb_j_avant + 2

            # Generer cloture M / Generate monthly closure
            _generer_cloture_agregee(
                niveau='M', niveau_source='J',
                date_debut=aujourd_hui.replace(day=1),
                date_fin=aujourd_hui,
            )

            # Verifier la cloture M / Verify monthly closure
            cloture_m = ClotureCaisse.objects.filter(
                niveau=ClotureCaisse.MENSUELLE,
            ).order_by('-numero_sequentiel').first()
            assert cloture_m is not None
            assert cloture_m.numero_sequentiel >= 1
            # Le total de la cloture M doit etre >= 5000 (les 2 nouvelles J)
            # / Monthly closure total must be >= 5000 (the 2 new daily closures)
            assert cloture_m.total_general >= 5000
            # Le nombre de transactions doit etre >= 2
            # / Transaction count must be >= 2
            assert cloture_m.nombre_transactions >= 2


@pytest.mark.usefixtures("test_data")
class TestDatetimeOuvertureAuto:
    """datetime_ouverture = datetime 1ere vente apres derniere cloture.
    / datetime_ouverture = datetime of 1st sale after last closure."""

    def test_datetime_ouverture_auto(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            _nettoyer_clotures_et_perpetuel(premier_pv)

            # Cloture 1 / Closure 1
            _creer_ligne_article_directe(produit, prix, 1000, PaymentMethod.CASH, pv=premier_pv)
            client = _make_client(admin_user, tenant)
            client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})

            premiere_cloture = ClotureCaisse.objects.filter(
                niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('numero_sequentiel').first()

            # Nouvelle vente apres cloture 1 / New sale after closure 1
            _creer_ligne_article_directe(produit, prix, 2000, PaymentMethod.CC, pv=premier_pv)

            # Cloture 2 / Closure 2
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            cloture2 = ClotureCaisse.objects.filter(
                niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('-numero_sequentiel').first()

            # datetime_ouverture de cloture2 doit etre apres datetime_cloture de cloture1
            # / datetime_ouverture of closure2 must be after datetime_cloture of closure1
            assert cloture2.datetime_ouverture > premiere_cloture.datetime_cloture


@pytest.mark.usefixtures("test_data")
class TestPasDeVentePasDeCloture:
    """Retourne 400 si aucune vente a cloturer.
    / Returns 400 if no sales to close."""

    def test_pas_de_vente_pas_de_cloture(
        self, admin_user, tenant, premier_pv,
    ):
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            # Cloturer tout ce qui traine / Close everything pending
            client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            # Re-cloturer : pas de vente → 400
            # / Re-close: no sales → 400
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 400


@pytest.mark.usefixtures("test_data")
class TestGardeCorrectionPostCloture:
    """ligne_couverte_par_cloture() retourne la cloture.
    / ligne_couverte_par_cloture() returns the closure."""

    def test_garde_correction_post_cloture(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            _nettoyer_clotures_et_perpetuel(premier_pv)

            ligne = _creer_ligne_article_directe(produit, prix, 1000, PaymentMethod.CASH, pv=premier_pv)

            # Pas encore de cloture → ligne NON couverte
            # / No closure yet → line NOT covered
            assert ligne_couverte_par_cloture(ligne) is None

            # Cloturer / Close
            client = _make_client(admin_user, tenant)
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            # Maintenant la ligne EST couverte / Now the line IS covered
            ligne.refresh_from_db()
            cloture_trouvee = ligne_couverte_par_cloture(ligne)
            assert cloture_trouvee is not None
            assert cloture_trouvee.point_de_vente == premier_pv


@pytest.mark.usefixtures("test_data")
class TestRapportJson13Cles:
    """Le rapport JSON a 13 sections.
    / The JSON report has 13 sections."""

    def test_rapport_json_13_cles(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            _nettoyer_clotures_et_perpetuel(premier_pv)

            _creer_ligne_article_directe(produit, prix, 1000, PaymentMethod.CASH, pv=premier_pv)
            client = _make_client(admin_user, tenant)
            response = client.post('/laboutik/caisse/cloturer/', {'uuid_pv': str(premier_pv.uuid)})
            assert response.status_code == 200

            cloture = ClotureCaisse.objects.filter(
                niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('-numero_sequentiel').first()
            rapport = cloture.rapport_json

            # 13 cles attendues du RapportComptableService
            # / 13 expected keys from RapportComptableService
            cles_attendues = [
                'totaux_par_moyen', 'detail_ventes', 'tva', 'solde_caisse',
                'recharges', 'adhesions', 'remboursements', 'habitus',
                'billets', 'synthese_operations', 'operateurs',
                'ventilation_par_pv', 'infos_legales',
            ]
            for cle in cles_attendues:
                assert cle in rapport, f"Cle manquante: {cle}"
            assert len(rapport) == 13
