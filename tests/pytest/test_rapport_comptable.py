"""
Tests du RapportComptableService.
/ RapportComptableService tests.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_rapport_comptable.py -v --api-key dummy

LOCALISATION : tests/pytest/test_rapport_comptable.py
"""
import os
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django
django.setup()

import pytest
from django.utils import timezone
from datetime import timedelta
from django_tenants.utils import tenant_context
from Customers.models import Client

TENANT_SCHEMA = 'lespass'


def _get_tenant():
    """Recupere le tenant de test. / Get the test tenant."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture
def tenant():
    return _get_tenant()


@pytest.fixture
def service(tenant):
    """
    Cree un RapportComptableService sur une large periode.
    / Create a RapportComptableService over a wide period.
    """
    with tenant_context(tenant):
        from laboutik.reports import RapportComptableService
        from laboutik.models import PointDeVente

        # Prendre le premier point de vente disponible, ou None si aucun
        # / Take the first available POS, or None if none
        pv = PointDeVente.objects.first()

        maintenant = timezone.now()
        debut = maintenant - timedelta(days=365)
        fin = maintenant + timedelta(hours=1)

        return RapportComptableService(
            point_de_vente=pv,
            datetime_debut=debut,
            datetime_fin=fin,
        )


@pytest.fixture
def service_vide(tenant):
    """
    Service sur une periode future sans donnees.
    / Service over a future period with no data.
    """
    with tenant_context(tenant):
        from laboutik.reports import RapportComptableService
        from laboutik.models import PointDeVente

        pv = PointDeVente.objects.first()

        # Periode dans le futur lointain — aucune ligne ne peut exister
        # / Far future period — no line can exist
        debut = timezone.now() + timedelta(days=3650)
        fin = debut + timedelta(hours=1)

        return RapportComptableService(
            point_de_vente=pv,
            datetime_debut=debut,
            datetime_fin=fin,
        )


class TestRapportComplet:
    """Tests sur generer_rapport_complet(). / Tests on generer_rapport_complet()."""

    def test_rapport_complet_13_cles(self, tenant, service):
        """
        generer_rapport_complet() retourne un dict avec exactement 13 cles.
        / generer_rapport_complet() returns a dict with exactly 13 keys.
        """
        with tenant_context(tenant):
            rapport = service.generer_rapport_complet()

            cles_attendues = {
                'totaux_par_moyen',
                'detail_ventes',
                'tva',
                'solde_caisse',
                'recharges',
                'adhesions',
                'remboursements',
                'habitus',
                'billets',
                'synthese_operations',
                'operateurs',
                'ventilation_par_pv',
                'infos_legales',
            }
            assert set(rapport.keys()) == cles_attendues
            assert len(rapport) == 13


class TestTotauxParMoyen:
    """Tests sur calculer_totaux_par_moyen(). / Tests on calculer_totaux_par_moyen()."""

    def test_totaux_par_moyen_structure(self, tenant, service):
        """
        Le dict contient especes, carte_bancaire, cashless, total.
        Le total est la somme des parties.
        / Dict contains cash, card, cashless, total. Total is the sum.
        """
        with tenant_context(tenant):
            totaux = service.calculer_totaux_par_moyen()

            assert 'especes' in totaux
            assert 'carte_bancaire' in totaux
            assert 'cashless' in totaux
            assert 'total' in totaux

            # Le total doit etre la somme des moyens
            # / Total must be the sum of methods
            somme = totaux['especes'] + totaux['carte_bancaire'] + totaux['cashless'] + totaux['cheque']
            assert totaux['total'] == somme

    def test_totaux_tous_entiers(self, tenant, service):
        """
        Les montants numeriques sont des entiers (centimes).
        Les cles non-numeriques (cashless_detail, currency_code) sont ignorees.
        / Numeric amounts are integers (cents).
        Non-numeric keys (cashless_detail, currency_code) are skipped.
        """
        # Cles non-numeriques ajoutees par l'enrichissement
        # / Non-numeric keys added by enrichment
        CLES_NON_NUMERIQUES = {'cashless_detail', 'currency_code'}

        with tenant_context(tenant):
            totaux = service.calculer_totaux_par_moyen()
            for cle, valeur in totaux.items():
                if cle in CLES_NON_NUMERIQUES:
                    continue
                assert isinstance(valeur, int), f"{cle} n'est pas un int: {type(valeur)}"


class TestTVA:
    """Tests sur calculer_tva(). / Tests on calculer_tva()."""

    def test_tva_coherence(self, tenant, service):
        """
        Pour chaque taux, total_ht + total_tva == total_ttc.
        / For each rate, total_ht + total_tva == total_ttc.
        """
        with tenant_context(tenant):
            tva = service.calculer_tva()

            for cle, detail in tva.items():
                assert detail['total_ht'] + detail['total_tva'] == detail['total_ttc'], (
                    f"Incoherence TVA pour {cle}: "
                    f"HT({detail['total_ht']}) + TVA({detail['total_tva']}) "
                    f"!= TTC({detail['total_ttc']})"
                )


class TestPeriodeVide:
    """Tests sur une periode sans ventes. / Tests on an empty period."""

    def test_rapport_periode_vide(self, tenant, service_vide):
        """
        Une periode sans vente retourne des totaux a 0.
        / A period with no sales returns totals at 0.
        """
        with tenant_context(tenant):
            rapport = service_vide.generer_rapport_complet()

            # Totaux par moyen : tout a 0
            # / Payment method totals: all 0
            totaux = rapport['totaux_par_moyen']
            assert totaux['total'] == 0
            assert totaux['especes'] == 0
            assert totaux['carte_bancaire'] == 0
            assert totaux['cashless'] == 0

            # TVA : dict vide (aucune ligne)
            # / VAT: empty dict (no lines)
            assert rapport['tva'] == {}

            # Detail ventes : dict vide
            # / Sales detail: empty dict
            assert rapport['detail_ventes'] == {}

            # Remboursements a 0
            # / Refunds at 0
            assert rapport['remboursements']['total'] == 0
            assert rapport['remboursements']['nb'] == 0

            # Habitus a 0
            assert rapport['habitus']['nb_cartes'] == 0
            assert rapport['habitus']['total'] == 0

            # Billets a 0
            assert rapport['billets']['nb'] == 0

            # Solde caisse : fond_de_caisse sans entrees
            # / Cash balance: float with no income
            solde = rapport['solde_caisse']
            assert solde['entrees_especes'] == 0
            assert solde['solde'] == solde['fond_de_caisse']


class TestHashLignes:
    """Tests sur calculer_hash_lignes(). / Tests on calculer_hash_lignes()."""

    def test_hash_lignes_deterministe(self, tenant, service):
        """
        Deux appels sur la meme periode retournent le meme hash.
        / Two calls on the same period return the same hash.
        """
        with tenant_context(tenant):
            hash1 = service.calculer_hash_lignes()
            hash2 = service.calculer_hash_lignes()
            assert hash1 == hash2
            # Le hash est une chaine hexadecimale de 64 caracteres (SHA-256)
            # / Hash is a 64-char hex string (SHA-256)
            assert len(hash1) == 64

    def test_hash_periode_vide(self, tenant, service_vide):
        """
        Le hash d'une periode vide est quand meme un SHA-256 valide.
        / Hash of empty period is still a valid SHA-256.
        """
        with tenant_context(tenant):
            h = service_vide.calculer_hash_lignes()
            assert len(h) == 64
