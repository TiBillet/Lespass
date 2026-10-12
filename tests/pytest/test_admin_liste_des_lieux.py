"""
Admin des lieux (Customers > Client) : quels lieux sont proposes.
/ Venues admin: which venues are listed.

LOCALISATION : tests/pytest/test_admin_liste_des_lieux.py

ROOT et les emplacements en attente de configuration ne sont jamais proposes.
META n'apparait que dans la liste d'un superuser.
/ ROOT and waiting slots never listed; META only in a superuser's list.
"""

from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from Administration.admin.site import staff_admin_site
from Customers.models import Client

pytestmark = pytest.mark.django_db


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
    # Precondition : la base dev contient des lieux de chaque categorie.
    # / Precondition: the dev database has venues of each category.
    for categorie in (Client.ROOT, Client.WAITING_CONFIG, Client.META):
        assert Client.objects.filter(categorie=categorie).exists(), categorie

    categories = _categories_proposees(chemin, est_superuser)

    assert Client.SALLE_SPECTACLE in categories
    assert Client.ROOT not in categories
    assert Client.WAITING_CONFIG not in categories
    assert (Client.META in categories) == meta_attendu
