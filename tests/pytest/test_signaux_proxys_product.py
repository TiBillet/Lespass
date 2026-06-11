"""
Garde-fou : les proxys de Product doivent etre connectes aux signaux Product.

Les signaux Django sont emis avec la classe EXACTE utilisee au save() : un
Product sauve via un proxy admin (TicketProduct, MembershipProduct...) n'emet
PAS les signaux connectes a sender=Product. Bug constate : le tarif gratuit
FREERES n'etait plus auto-cree via le proxy billetterie (cf. CHANGELOG
2026-06-11). Les connexions vivent dans BaseBillet/models.py (PROXYS_PRODUCT)
et BaseBillet/signals.py.

/ Guard: Product proxies must be connected to the Product signals.
Django signals are sent with the EXACT class used at save(): a Product saved
through an admin proxy does NOT emit signals connected to sender=Product.
Observed bug: the FREERES free price was no longer auto-created through the
ticket proxy. Connections live in BaseBillet/models.py (PROXYS_PRODUCT) and
BaseBillet/signals.py.
"""

import uuid

import pytest
from django.db.models.signals import post_save, pre_save
from django_tenants.utils import tenant_context

from BaseBillet import signals as basebillet_signals
from BaseBillet.models import (
    PROXYS_PRODUCT,
    Product,
    TicketProduct,
    post_save_Product,
)
from Customers.models import Client

# ---------------------------------------------------------------------------
# Pattern "live dev DB" du projet (cf. test_comptabilite_service.py) :
# pas de creation de DB de test, on utilise la base de dev existante.
# / Project's "live dev DB" pattern: no test DB creation, use the dev DB.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def django_db_setup():
    """No test DB creation — use the existing dev DB."""
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    """Disable pytest-django's DB access blocker for the session."""
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db


def _receivers_vivants(signal, sender):
    """
    Renvoie les fonctions receveuses actives du signal pour ce sender.
    `_live_receivers` est une API privee Django mais stable : elle resout les
    weakrefs et applique le filtre par sender, exactement comme a l'envoi.
    / Returns the live receiver functions of the signal for this sender.
    `_live_receivers` is a private but stable Django API: it resolves weakrefs
    and applies the sender filter, exactly like at dispatch time.
    """
    receivers = signal._live_receivers(sender)
    # Django 5 renvoie un tuple (sync, async) ; Django 4.2 une liste simple.
    # / Django 5 returns a (sync, async) tuple; Django 4.2 a plain list.
    if isinstance(receivers, tuple):
        return list(receivers[0])
    return list(receivers)


def test_aucun_proxy_product_oublie_dans_proxys_product():
    """
    Si quelqu'un cree un nouveau proxy de Product sans l'ajouter a
    PROXYS_PRODUCT, ce test echoue — au lieu d'un bug silencieux en prod.
    / If someone creates a new Product proxy without adding it to
    PROXYS_PRODUCT, this test fails — instead of a silent production bug.
    """
    proxys_declares = set(PROXYS_PRODUCT)
    proxys_reels = {
        sous_classe
        for sous_classe in Product.__subclasses__()
        if sous_classe._meta.proxy
    }
    difference = proxys_reels.symmetric_difference(proxys_declares)
    assert proxys_reels == proxys_declares, (
        "Proxy de Product absent de PROXYS_PRODUCT (BaseBillet/models.py) "
        f"ou declare en trop : {difference}"
    )


def test_tous_les_proxys_sont_connectes_aux_quatre_receivers():
    """
    Chaque proxy doit declencher les 4 receivers du modele concret :
    post_save_Product (poids + tarif FREERES), send_membership_and_badge
    (asset Fedow), trigger_product_update (notification LaBoutik) et
    unpublish_if_archived (depublication a l'archivage).
    / Every proxy must trigger the concrete model's 4 receivers.
    """
    for proxy in PROXYS_PRODUCT:
        recepteurs_post_save = _receivers_vivants(post_save, proxy)
        assert post_save_Product in recepteurs_post_save, (
            f"{proxy.__name__} : post_save_Product non connecte"
        )
        assert (
            basebillet_signals.send_membership_and_badge_product_to_fedow
            in recepteurs_post_save
        ), f"{proxy.__name__} : send_membership_and_badge_product_to_fedow non connecte"
        assert basebillet_signals.trigger_product_update in recepteurs_post_save, (
            f"{proxy.__name__} : trigger_product_update non connecte"
        )

        recepteurs_pre_save = _receivers_vivants(pre_save, proxy)
        assert basebillet_signals.unpublish_if_archived in recepteurs_pre_save, (
            f"{proxy.__name__} : unpublish_if_archived non connecte"
        )


def test_tarif_gratuit_freeres_auto_cree_via_proxy_ticket():
    """
    Le bug d'origine, rejoue : creer un produit FREERES via le proxy
    TicketProduct doit auto-creer son tarif gratuit (prix=0), comme via
    le modele concret.
    / The original bug, replayed: creating a FREERES product through the
    TicketProduct proxy must auto-create its free price (prix=0), just like
    through the concrete model.
    """
    tenant_lespass = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant_lespass):
        produit = TicketProduct.objects.create(
            name=f"TestFreeresProxy_{uuid.uuid4().hex[:8]}",
            categorie_article=Product.FREERES,
        )
        try:
            assert produit.prices.filter(prix=0).exists(), (
                "Le tarif gratuit n'a pas ete auto-cree par post_save_Product "
                "via le proxy TicketProduct"
            )
        finally:
            # Nettoyage TOUJOURS execute (DB de dev partagee, pas de rollback).
            # / Cleanup ALWAYS runs (shared dev DB, no rollback).
            produit.prices.all().delete()
            produit.delete()
