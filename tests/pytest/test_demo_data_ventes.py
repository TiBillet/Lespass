"""
Tests pytest pour le seed de demo des ventes comptables.
/ Pytest tests for the accounting sales demo seed.

LOCALISATION : tests/pytest/test_demo_data_ventes.py

Couvre le module Administration/management/commands/_demo_data_v2_ventes.py :
6 tests sur l'integrite des donnees generees + la cohérence du rapport
comptable produit par RapportComptableService.

Strategie : reutilise la DB dev (meme pattern qu'admin tests + onboard).
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context


# ---------------------------------------------------------------------------
# Override : reutiliser la DB dev au lieu d'une test DB temporaire.
# / Override: reuse the dev DB instead of a temporary test DB.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def django_db_setup():
    """Pas de creation de test DB — on utilise la DB dev existante."""
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    """Desactive le bloqueur d'acces DB de pytest-django pour la session."""
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixture : seed sur tenant lespass + cleanup automatique
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_lespass():
    """
    Lance le seed sur le tenant lespass avec reset=True (etat propre).
    Yield (stats, debut, fin) ou debut/fin couvrent la periode generee.
    Cleanup : suppression des donnees demo a la fin.
    / Run the seed on 'lespass' tenant with reset=True. Cleanup after.
    """
    from Customers.models import Client
    from Administration.management.commands._demo_data_v2_ventes import (
        seed_ventes_demo, _reset_ventes_demo,
    )

    tenant = Client.objects.get(schema_name="lespass")

    # Fenetre : aujourd'hui debut → demain debut. Couvre largement le datetime
    # backdate "hier 14h" du seed.
    # / Window: today start -> tomorrow start. Wide enough for the backdated time.
    now_local = timezone.localtime()
    debut = (now_local - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    fin = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)

    with tenant_context(tenant):
        stats = seed_ventes_demo(reset=True)

    yield stats, debut, fin, tenant

    # Cleanup
    with tenant_context(tenant):
        _reset_ventes_demo()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_seed_cree_au_moins_15_lignes_distinctes(seed_lespass):
    """
    Le seed cree au moins 15 LigneArticle : 5 billets + 12 adhesions
    (8 SF + 4 unitaires) + 3 QR/NFC + 1 avoir + 1 remboursement = 22 lignes.
    / Seed creates at least 15 LigneArticle (typical: 22).
    """
    stats, _, _, _ = seed_lespass
    assert stats["nb_lignes_creees"] >= 15, (
        f"Attendu >= 15 lignes, obtenu {stats['nb_lignes_creees']}"
    )


def test_seed_idempotent_avec_reset(seed_lespass):
    """
    Re-lancer le seed avec reset=True produit le meme nombre de lignes.
    / Re-running with reset=True produces the same count.
    """
    from Administration.management.commands._demo_data_v2_ventes import (
        seed_ventes_demo,
    )

    stats_premier, _, _, tenant = seed_lespass

    # 2e seed avec reset (fixture deja faite : on en relance un)
    # / Second seed with reset (fixture already ran one)
    with tenant_context(tenant):
        stats_second = seed_ventes_demo(reset=True)

    assert stats_second["nb_lignes_creees"] == stats_premier["nb_lignes_creees"]
    assert stats_second["total_ttc_centimes"] == stats_premier["total_ttc_centimes"]


def test_seed_total_ttc_correspond_aux_lignes_demo(seed_lespass):
    """
    La somme(amount * qty) des LigneArticle [DEMO] (status V/P/F/N) correspond
    au stats['total_ttc_centimes']. On filtre par prefixe pour ne pas etre
    pollue par d'autres tests qui auraient laisse des LigneArticle dans la
    meme fenetre de temps (DB dev partagee).
    / Sum of demo LigneArticle matches stats. We filter by prefix to avoid
    / pollution from other tests sharing the dev DB.
    """
    from django.db.models import Sum, F
    from django.db.models.functions import Coalesce
    from decimal import Decimal
    from BaseBillet.models import LigneArticle, SaleOrigin

    stats, _, _, tenant = seed_lespass

    with tenant_context(tenant):
        # On reproduit exactement le filtre du _base_queryset mais en se
        # restreignant aux produits prefixes par '[DEMO] '.
        # / Same filter as _base_queryset, restricted to [DEMO] products.
        total = LigneArticle.objects.filter(
            pricesold__productsold__product__name__startswith="[DEMO] ",
            status__in=[
                LigneArticle.VALID,
                LigneArticle.PAID,
                LigneArticle.FREERES,
                LigneArticle.CREDIT_NOTE,
            ],
        ).exclude(sale_origin=SaleOrigin.LABOUTIK).aggregate(
            t=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")),
        )["t"]

    assert int(total) == stats["total_ttc_centimes"], (
        f"Somme demo={int(total)} cts, stats={stats['total_ttc_centimes']} cts"
    )


def test_seed_ventilation_tva_par_taux(seed_lespass):
    """
    3 taux de TVA non nuls presents : 5.5%, 10%, 20% (et 0% pour les adhesions).
    Les montants correspondent aux chiffres ronds prevus, calcules en filtrant
    sur les lignes [DEMO] uniquement (DB dev partagee).
    / 3 non-zero VAT rates present. Filter on [DEMO] to avoid pollution.
    """
    from django.db.models import Sum, F
    from django.db.models.functions import Coalesce
    from decimal import Decimal
    from BaseBillet.models import LigneArticle, SaleOrigin

    _, _, _, tenant = seed_lespass

    with tenant_context(tenant):
        rows = (
            LigneArticle.objects.filter(
                pricesold__productsold__product__name__startswith="[DEMO] ",
                status__in=[
                    LigneArticle.VALID,
                    LigneArticle.PAID,
                    LigneArticle.FREERES,
                    LigneArticle.CREDIT_NOTE,
                ],
            ).exclude(sale_origin=SaleOrigin.LABOUTIK)
            .values("vat")
            .annotate(ttc=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")))
        )
        par_taux = {str(r["vat"]): int(r["ttc"]) for r in rows}

    # 3 taux non-nuls attendus / 3 non-zero rates expected
    assert "5.50" in par_taux, f"TVA 5.5% absente. Trouves: {list(par_taux)}"
    assert "10.00" in par_taux, f"TVA 10% absente. Trouves: {list(par_taux)}"
    assert "20.00" in par_taux, f"TVA 20% absente. Trouves: {list(par_taux)}"

    # Biere : 20×5€ = 100€ TTC à 20% / Beer
    assert par_taux["20.00"] == 10000
    # Billets : 200+80+120+20 = 420 - 20 (avoir) = 400€ TTC à 10% / Tickets
    assert par_taux["10.00"] == 40000
    # Food : 40 + 60 = 100€ TTC à 5.5% / Food
    assert par_taux["5.50"] == 10000


def test_seed_avoir_et_remboursement_distincts(seed_lespass):
    """
    La section remboursements distingue credit_notes (inclus dans total)
    et refunded (hors total). Montants attendus pour les lignes [DEMO] :
    -20€ et -16€.
    / Refund section distinguishes credit_notes (in total) from refunded (out).
    """
    from django.db.models import Sum, F, Count
    from django.db.models.functions import Coalesce
    from decimal import Decimal
    from BaseBillet.models import LigneArticle, SaleOrigin

    _, _, _, tenant = seed_lespass

    with tenant_context(tenant):
        cn = LigneArticle.objects.filter(
            pricesold__productsold__product__name__startswith="[DEMO] ",
            status=LigneArticle.CREDIT_NOTE,
        ).exclude(sale_origin=SaleOrigin.LABOUTIK).aggregate(
            t=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")),
            n=Count("pk"),
        )
        rf = LigneArticle.objects.filter(
            pricesold__productsold__product__name__startswith="[DEMO] ",
            status=LigneArticle.REFUNDED,
        ).exclude(sale_origin=SaleOrigin.LABOUTIK).aggregate(
            t=Coalesce(Sum(F("amount") * F("qty")), Decimal("0")),
            n=Count("pk"),
        )

    # Avoir : -20€ x 1 ligne / Credit note
    assert int(cn["t"]) == -2000, f"Avoir attendu -2000 cts, obtenu {int(cn['t'])}"
    assert cn["n"] == 1

    # Remboursement : -16€ x 1 ligne / Refund
    assert int(rf["t"]) == -1600, f"Refund attendu -1600 cts, obtenu {int(rf['t'])}"
    assert rf["n"] == 1


def test_seed_tous_payment_methods_couverts(seed_lespass):
    """
    Tous les payment_method TiBillet sont couverts : SF, SN, SP, SR, CC, CA,
    CH, TR, QR, LE, LG, NA. Exception : UK (Unknown) qui n'est jamais cree
    intentionnellement.
    / All TiBillet payment methods are covered (except UK which is never
    intentionally created).
    """
    from comptabilite.services import RapportComptableService

    _, debut, fin, tenant = seed_lespass

    with tenant_context(tenant):
        totaux = RapportComptableService(debut, fin).calculer_totaux_par_moyen()

    codes_attendus = {"SF", "SN", "SP", "SR", "CC", "CA", "CH", "TR", "QR", "LE", "LG", "NA"}
    codes_presents = set(totaux.keys()) - {"total", "currency_code"}

    manquants = codes_attendus - codes_presents
    assert not manquants, f"PaymentMethod manquants : {manquants}"
