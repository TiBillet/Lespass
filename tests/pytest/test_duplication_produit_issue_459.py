"""
Dupliquer un produit ne doit pas ajouter de tarif gratuit en trop.
/ Duplicating a product must not add an extra free price.

LOCALISATION : tests/pytest/test_duplication_produit_issue_459.py

Code testé / Tested code : Administration/admin/products.py, ProductAdmin._duplicate_product

Issue GitHub #459 : pour un produit « réservation gratuite », l'enregistrement du nouveau
produit crée automatiquement un tarif gratuit (signal post_save_Product). Les tarifs du
produit source étaient ensuite copiés par-dessus : la copie avait un tarif gratuit en trop.
/ GitHub issue #459: the auto-created free price came on top of the copied prices.

Chaque test est marqué `django_db` : pytest-django l'exécute dans une transaction annulée
à la fin. Les objets créés par les fabriques ne restent pas en base de dev.
/ Every test runs in a rolled-back transaction.

Lancer / Run : make test ARGS="tests/pytest/test_duplication_produit_issue_459.py"
"""

from types import SimpleNamespace

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import (
    ajouter_un_tarif,
    catalogue_stripe_simule,
    creer_evenement_avec_tarif,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, avec Stripe (catalogue) et Celery simulés pendant tout le test.
    / The `lespass` venue, with the Stripe catalogue and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule() as catalogue_stripe:
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    catalogue_stripe=catalogue_stripe,
                    taches_demandees=taches_demandees,
                )


def dupliquer(produit):
    """Duplique un produit comme le fait le bouton « Dupliquer » de l'admin.
    / Duplicates a product like the admin "Duplicate" button does."""
    from Administration.admin.site import staff_admin_site
    from BaseBillet.models import Product

    admin_des_produits = staff_admin_site._registry[Product]
    return admin_des_produits._duplicate_product(produit)


def tarifs_tries(produit):
    """Les tarifs d'un produit sous la forme (nom, prix), triés.
    / A product's prices as sorted (name, amount) pairs."""
    tarifs = []
    for tarif in produit.prices.all():
        tarifs.append((tarif.name, tarif.prix))
    tarifs.sort()
    return tarifs


def test_dupliquer_une_reservation_gratuite_ne_cree_pas_de_tarif_en_trop(lieu):
    """Réservation gratuite à un tarif : la copie a un seul tarif.
    / Free booking with one price: the copy has a single price."""
    from BaseBillet.models import Product

    reservation_gratuite = creer_evenement_avec_tarif(prix="0.00", categorie=Product.FREERES)

    copie = dupliquer(reservation_gratuite.produit)

    assert copie.prices.count() == 1


def test_dupliquer_une_reservation_gratuite_copie_les_memes_tarifs(lieu):
    """Réservation gratuite à deux tarifs : la copie a exactement les mêmes tarifs.
    / Free booking with two prices: the copy has exactly the same prices."""
    from BaseBillet.models import Product

    reservation_gratuite = creer_evenement_avec_tarif(prix="0.00", categorie=Product.FREERES)
    ajouter_un_tarif(reservation_gratuite.produit, prix="5.00")

    copie = dupliquer(reservation_gratuite.produit)

    assert tarifs_tries(copie) == tarifs_tries(reservation_gratuite.produit)


def test_dupliquer_un_billet_payant_copie_les_memes_tarifs(lieu):
    """Billet payant : la copie a exactement les mêmes tarifs (pas de régression).
    / Paid ticket: the copy has exactly the same prices (no regression)."""
    concert = creer_evenement_avec_tarif(prix="10.00")

    copie = dupliquer(concert.produit)

    assert tarifs_tries(copie) == tarifs_tries(concert.produit)
