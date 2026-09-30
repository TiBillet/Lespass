"""
Un produit archivé ne bloque pas son nom.
/ An archived product does not reserve its name.

LOCALISATION : tests/pytest/test_product_nom_unique_si_non_archive.py

Code testé / Tested code :
- BaseBillet/models.py : contrainte `unique_product_non_archive_par_categorie_et_nom`
- Administration/admin/products.py : un_autre_produit_non_archive_porte_ce_nom (action `desarchive`)

Avant : le couple (catégorie, nom) était unique pour tous les produits. Impossible de créer
un produit portant le nom d'un produit archivé.
Maintenant : l'unicité ne concerne que les produits NON archivés.
/ Uniqueness of (category, name) now only applies to NON-archived products.

Chaque test est marqué `django_db` : pytest-django l'exécute dans une transaction annulée
à la fin. Les objets créés ne restent pas en base de dev.
/ Every test runs in a rolled-back transaction.

Lancer / Run : make test ARGS="tests/pytest/test_product_nom_unique_si_non_archive.py"
"""

from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    identifiant_unique,
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


def creer_un_billet(nom, archive=False):
    """Crée un produit billet. / Creates a ticket product."""
    from BaseBillet.models import Product

    return Product.objects.create(
        name=nom, categorie_article=Product.BILLET, archive=archive
    )


def test_on_peut_creer_un_produit_du_meme_nom_qu_un_produit_archive(lieu):
    """Un produit archivé ne bloque pas son nom.
    / An archived product does not block its name."""
    from BaseBillet.models import Product

    nom = f"Concert {identifiant_unique()}"
    creer_un_billet(nom, archive=True)

    creer_un_billet(nom)

    assert Product.objects.filter(name=nom).count() == 2


def test_plusieurs_produits_archives_peuvent_porter_le_meme_nom(lieu):
    """Deux produits archivés de même nom : autorisé.
    / Two archived products with the same name: allowed."""
    from BaseBillet.models import Product

    nom = f"Concert {identifiant_unique()}"
    creer_un_billet(nom, archive=True)

    creer_un_billet(nom, archive=True)

    assert Product.objects.filter(name=nom, archive=True).count() == 2


def test_deux_produits_non_archives_ne_peuvent_pas_porter_le_meme_nom(lieu):
    """Deux produits actifs de même nom et même catégorie : toujours refusé.
    / Two active products with the same name and category: still refused."""
    nom = f"Concert {identifiant_unique()}"
    creer_un_billet(nom)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            creer_un_billet(nom)


def test_le_formulaire_refuse_proprement_un_nom_deja_pris_par_un_produit_actif(lieu):
    """full_clean() lève une erreur de validation, pas une erreur de base de données.
    / full_clean() raises a validation error, not a database error."""
    from django.core.exceptions import ValidationError

    from BaseBillet.models import Product

    nom = f"Concert {identifiant_unique()}"
    creer_un_billet(nom)
    produit_en_double = Product(name=nom, categorie_article=Product.BILLET)

    with pytest.raises(ValidationError):
        produit_en_double.validate_constraints()


def test_desarchiver_est_bloque_si_un_produit_actif_porte_le_meme_nom(lieu):
    """Le contrôle de l'action admin « Désarchiver » détecte le produit actif du même nom.
    / The admin "Unarchive" check detects the active product with the same name."""
    from Administration.admin.products import un_autre_produit_non_archive_porte_ce_nom

    nom = f"Concert {identifiant_unique()}"
    ancien_produit = creer_un_billet(nom, archive=True)
    creer_un_billet(nom)

    assert un_autre_produit_non_archive_porte_ce_nom(ancien_produit) is True


def test_desarchiver_est_possible_si_le_nom_est_libre(lieu):
    """Le contrôle de l'action admin « Désarchiver » laisse passer un nom libre.
    / The admin "Unarchive" check lets a free name through."""
    from Administration.admin.products import un_autre_produit_non_archive_porte_ce_nom

    nom = f"Concert {identifiant_unique()}"
    ancien_produit = creer_un_billet(nom, archive=True)

    assert un_autre_produit_non_archive_porte_ce_nom(ancien_produit) is False
