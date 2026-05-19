"""
Tests pour les modeles CompteComptable + MappingMoyenDePaiement.
/ Tests for CompteComptable + MappingMoyenDePaiement models.

LOCALISATION : tests/pytest/test_comptabilite_models.py
Pattern : live dev DB.
"""
import pytest
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


def test_modele_compte_comptable_creation():
    """On peut creer un CompteComptable et l'__str__ retourne 'numero — libelle'."""
    from Customers.models import Client
    tenant = Client.objects.exclude(schema_name="public").first()
    with tenant_context(tenant):
        from comptabilite.models import CompteComptable
        compte = CompteComptable.objects.create(
            numero="999999",
            libelle="Compte de test",
            type_compte=CompteComptable.TYPE_AUTRE,
        )
        assert "999999" in str(compte)
        assert "Compte de test" in str(compte)
        compte.delete()


def test_modele_mapping_creation():
    """On peut creer un MappingMoyenDePaiement lie a un compte."""
    from Customers.models import Client
    tenant = Client.objects.exclude(schema_name="public").first()
    with tenant_context(tenant):
        from comptabilite.models import CompteComptable, MappingMoyenDePaiement
        compte = CompteComptable.objects.create(
            numero="999998", libelle="Compte test mapping",
            type_compte=CompteComptable.TYPE_TRESORERIE,
        )
        # ZZ ne devrait jamais exister dans PaymentMethod, donc pas de collision
        mapping = MappingMoyenDePaiement.objects.create(
            payment_method="ZZ", compte=compte,
        )
        assert mapping.compte == compte
        mapping.delete()
        compte.delete()


def test_seed_pcg_francais_applique_dans_tenant():
    """
    La data migration 0002 cree les 9 comptes par defaut dans chaque tenant.
    / Data migration 0002 creates the 9 default accounts in each tenant.
    """
    from Customers.models import Client
    tenant = Client.objects.exclude(schema_name="public").first()
    with tenant_context(tenant):
        from comptabilite.models import CompteComptable
        # Verifier au moins 5 comptes du PCG francais standard
        for numero in ["411000", "512000", "530000", "706000", "756000"]:
            assert CompteComptable.objects.filter(numero=numero).exists(), (
                f"Compte {numero} manquant apres seed"
            )


def test_seed_mappings_paiement_appliques():
    """La data migration 0002 cree les mappings PaymentMethod -> CompteComptable."""
    from Customers.models import Client
    tenant = Client.objects.exclude(schema_name="public").first()
    with tenant_context(tenant):
        from comptabilite.models import MappingMoyenDePaiement
        # Au moins les 3 plus courants : CA (especes), CC (CB), CH (cheque)
        for code in ["CA", "CC", "CH"]:
            assert MappingMoyenDePaiement.objects.filter(payment_method=code).exists(), (
                f"Mapping {code} manquant apres seed"
            )
