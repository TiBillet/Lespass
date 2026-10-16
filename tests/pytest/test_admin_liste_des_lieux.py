"""
Admin des lieux (Customers > Client) : quels lieux sont proposes.
/ Venues admin: which venues are listed.

LOCALISATION : tests/pytest/test_admin_liste_des_lieux.py

ROOT et les emplacements en attente de configuration ne sont jamais proposes.
META n'apparait que dans la liste d'un superuser.
/ ROOT and waiting slots never listed; META only in a superuser's list.
"""

import uuid
from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from Administration.admin.site import staff_admin_site
from Customers.models import Client

pytestmark = pytest.mark.django_db


def _fabriquer_un_lieu_de_chaque_categorie():
    """
    Un lieu de chaque categorie utile au test : ROOT, emplacement en attente, META,
    et un lieu ordinaire. Le test ne depend donc pas des lieux de la base de dev
    (les emplacements en attente y sont consommes par l'onboarding).
    `bulk_create` n'appelle pas `save()` : aucun schema n'est cree. Tout est annule
    par la transaction `django_db`.
    / One venue per category, so the test does not depend on the dev database.
    bulk_create skips save(): no schema is created. Rolled back by django_db.
    """
    suffixe = uuid.uuid4().hex[:8]
    lieux_fabriques = []
    for categorie in (
        Client.ROOT,
        Client.WAITING_CONFIG,
        Client.META,
        Client.SALLE_SPECTACLE,
    ):
        lieux_fabriques.append(
            Client(
                schema_name=f"test_liste_{categorie.lower()}_{suffixe}",
                name=f"Test liste des lieux {categorie} {suffixe}",
                categorie=categorie,
            )
        )
    Client.objects.bulk_create(lieux_fabriques)


def _categories_proposees(chemin, est_superuser):
    admin_des_lieux = staff_admin_site._registry[Client]
    requete = RequestFactory().get(chemin)
    requete.user = SimpleNamespace(is_superuser=est_superuser)
    lieux = admin_des_lieux.get_queryset(requete)
    return set(lieux.values_list("categorie", flat=True))


@pytest.mark.parametrize(
    "chemin, est_superuser, meta_attendu",
    [
        ("/admin/Customers/client/", True, True),
        ("/admin/autocomplete/", True, False),
        ("/admin/Customers/client/", False, False),
    ],
    ids=["liste-superuser", "autocompletion-superuser", "liste-gestionnaire"],
)
def test_les_lieux_techniques_proposes(chemin, est_superuser, meta_attendu):
    _fabriquer_un_lieu_de_chaque_categorie()

    categories = _categories_proposees(chemin, est_superuser)

    assert Client.SALLE_SPECTACLE in categories
    assert Client.ROOT not in categories
    assert Client.WAITING_CONFIG not in categories
    assert (Client.META in categories) == meta_attendu
