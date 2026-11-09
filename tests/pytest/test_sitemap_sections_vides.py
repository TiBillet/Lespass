"""
Tests de `StaticViewSitemap` : une section vide ne va pas au sitemap.
/ Tests for `StaticViewSitemap`: an empty section stays out of the sitemap.

LOCALISATION : tests/pytest/test_sitemap_sections_vides.py

On teste les DEUX sens : exclure a tort coute plus cher que le probleme
corrige.

PIEGE : la base dev est partagee (cf. tests/README.md), on ne cree ni ne
supprime aucune donnee — les managers sont patches a la place.
/ Both directions tested. The dev DB is shared: we patch managers instead
of creating data.
"""

from unittest.mock import patch

import pytest
from django_tenants.utils import tenant_context

from Customers.models import Client

pytestmark = pytest.mark.django_db


def _items_du_sitemap(schema="lespass"):
    """Rend la liste des sections declarees par le sitemap statique."""
    from BaseBillet.sitemap import StaticViewSitemap

    tenant = Client.objects.filter(schema_name=schema).first()
    assert tenant is not None, f"Tenant {schema} absent de la DB dev."
    with tenant_context(tenant):
        return StaticViewSitemap().items()


class _FauxManager:
    """Manager minimal dont `filter(...).exists()` renvoie une valeur fixe."""

    def __init__(self, vide):
        self._vide = vide

    def filter(self, *a, **kw):
        return self

    def exclude(self, *a, **kw):
        return self

    def exists(self):
        return not self._vide

    def count(self):
        # Deux elements : une page liste n'est declaree qu'a partir de deux.
        # / Two items: a list page is declared from two on.
        return 0 if self._vide else 2


def test_la_home_est_toujours_declaree():
    """
    `index` ne depend d'aucun module : c'est la porte d'entree du site.
    / `index` never depends on a module.
    """
    assert "index" in _items_du_sitemap()


def test_les_sections_vides_sortent_du_sitemap():
    """
    Modules actifs mais AUCUN contenu -> seule la home reste.

    C'est le cas codecommun.coop : la billetterie est activee, mais le
    site n'a aucun evenement. Declarer /event/ revient a proposer a Google
    une page de filtres sans rien a filtrer.
    / Modules on but NO content -> only the home remains.
    """
    from BaseBillet import sitemap as module_sitemap

    with patch.object(module_sitemap.Event, "objects", _FauxManager(vide=True)), \
         patch("BaseBillet.models.Product.objects", _FauxManager(vide=True)), \
         patch("BaseBillet.models.FederatedPlace.objects", _FauxManager(vide=True)), \
         patch("booking.models.Resource.objects", _FauxManager(vide=True)), \
         patch("booking.benevolat.plannings_publies_avec_des_besoins_a_venir", return_value=[]), \
         patch("BaseBillet.models.FederationConfiguration.get_solo") as faux_fed:
        faux_fed.return_value.afficher_lieux_entrants = False
        items = _items_du_sitemap()

    assert items == ["index"], (
        f"Sections vides encore declarees au sitemap : {items}"
    )


def test_une_section_avec_du_contenu_reste_declaree():
    """
    Modules actifs ET contenu present -> les sections sont declarees.

    Le garde-fou du test precedent : le filtre ne doit pas devenir un
    aspirateur qui vide le sitemap des sites qui, eux, ont du contenu.
    / The counterpart: the filter must not empty the sitemap of sites
    that do have content.
    """
    from BaseBillet import sitemap as module_sitemap

    with patch.object(module_sitemap.Event, "objects", _FauxManager(vide=False)), \
         patch("BaseBillet.models.Product.objects", _FauxManager(vide=False)), \
         patch("BaseBillet.models.FederatedPlace.objects", _FauxManager(vide=False)):
        items = _items_du_sitemap()

    for section in ("index", "event-list", "membership_mvt-list", "federation-list"):
        assert section in items, f"{section} devrait etre declaree : {items}"


def test_les_lieux_entrants_suffisent_a_declarer_le_reseau_local():
    """
    Aucun FederatedPlace, mais un lieu entrant et l'option active -> declaree.

    Sans cette source, un tenant qui n'affiche QUE des lieux entrants
    verrait sa page disparaitre du sitemap alors qu'elle est pleine.
    / No FederatedPlace but one incoming place, option on -> still declared.
    """
    from BaseBillet import sitemap as module_sitemap

    tenant = Client.objects.get(schema_name="lespass")
    lieux_entrants = {"by_tenant": {str(tenant.uuid): ["uuid-d-un-voisin"]}}

    with patch.object(module_sitemap.Event, "objects", _FauxManager(vide=True)), \
         patch("BaseBillet.models.Product.objects", _FauxManager(vide=True)), \
         patch("BaseBillet.models.FederatedPlace.objects", _FauxManager(vide=True)), \
         patch("seo.views_common.get_seo_cache", return_value=lieux_entrants), \
         patch("BaseBillet.models.FederationConfiguration.get_solo") as faux_fed:
        faux_fed.return_value.afficher_lieux_entrants = True
        faux_fed.return_value.tags_federation.all.return_value = []
        items = _items_du_sitemap()

    assert "federation-list" in items


def test_les_adhesions_federees_suffisent_a_declarer_la_page():
    """
    Aucun produit d'adhesion local mais des lieux federes visibles -> declaree.

    La page liste les deux sources (cf. MembershipMVT.list) ; ne tester que
    les produits locaux excluait du sitemap une page pleine.
    / No local membership product but visible federated places -> declared.
    """
    from BaseBillet import sitemap as module_sitemap

    with patch.object(module_sitemap.Event, "objects", _FauxManager(vide=True)), \
         patch("BaseBillet.models.Product.objects", _FauxManager(vide=True)), \
         patch("BaseBillet.models.FederatedPlace.objects", _FauxManager(vide=False)), \
         patch("BaseBillet.models.FederationConfiguration.get_solo") as faux_fed:
        faux_fed.return_value.afficher_lieux_entrants = False
        items = _items_du_sitemap()

    assert "membership_mvt-list" in items
