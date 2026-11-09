"""
Les groupes de ressources se gèrent depuis le formulaire d'une ressource.
/ Resource groups are managed from the resource form.

LOCALISATION : tests/pytest/test_admin_groupe_de_ressources.py

Code testé :
- Administration/admin/dashboard.py : le module Réservations n'a plus d'entrée
  « Groupe de ressources ».
- Administration/admin/resources.py : ResourceGroupAdmin reste enregistré (menu
  « ⋮ » du champ Groupe), et ResourceInline n'ajoute jamais de ressource.

Une ressource exige un produit. L'inline du groupe ne montre pas ce champ : une
ressource ajoutée depuis le groupe partait en base sans produit, et la page
plantait (IntegrityError sur booking_resource.product_id).
/ A resource needs a product; the group inline does not show it.
"""
import uuid

import pytest
from django.test import RequestFactory
from django.urls import reverse
from django_tenants.utils import tenant_context

PREFIXE_DU_GROUPE = "[test_admin_groupe_de_ressources]"


@pytest.mark.django_db
def test_le_module_reservations_n_a_plus_d_entree_groupe_de_ressources(tenant):
    """
    Les pages du module Réservations listent les ressources, pas leurs groupes.
    / The booking module pages list resources, not their groups.
    """
    from Administration.admin.dashboard import MODULE_FIELDS, _construire_sections_modules

    with tenant_context(tenant):
        sections = _construire_sections_modules(RequestFactory().get("/admin/"))
        slug_du_module = MODULE_FIELDS["module_booking"]["slug"]
        section_reservations = None
        for section in sections:
            if section.get("_slug") == slug_du_module:
                section_reservations = section
        assert section_reservations is not None, "Le module Réservations est introuvable."

        liens_du_module = []
        for entree in section_reservations["items"]:
            liens_du_module.append(str(entree["link"]))

    assert "/admin/booking/resource/" in liens_du_module
    for lien in liens_du_module:
        assert "resourcegroup" not in lien


@pytest.mark.django_db
def test_le_formulaire_d_une_ressource_propose_d_ajouter_un_groupe(tenant, admin_client):
    """
    Le champ Groupe est une liste déroulante, avec un lien pour créer un groupe.
    / The Group field is a dropdown, with a link to create a group.
    """
    with tenant_context(tenant):
        page_d_ajout = admin_client.get(reverse("staff_admin:booking_resource_add"))

    assert page_d_ajout.status_code == 200
    contenu = page_d_ajout.content.decode()
    assert '<select name="group"' in contenu
    assert "/admin/booking/resourcegroup/add/" in contenu


@pytest.mark.django_db
def test_la_fiche_d_un_groupe_ne_cree_pas_de_ressource(tenant, admin_client):
    """
    Une ligne de ressource postée avec le groupe est ignorée : le groupe est créé,
    la page ne plante pas, aucune ressource n'est créée.
    / A resource row posted with the group is ignored: no crash, no resource.
    """
    from booking.models import Resource, ResourceGroup
    from booking.tests.test_booking_engine import (
        TEST_PREFIX,
        _cleanup,
        _make_calendar,
        _make_weekly_opening,
    )

    nom_du_groupe = f"{PREFIXE_DU_GROUPE} {uuid.uuid4().hex[:8]}"
    nom_de_la_ressource = f"{TEST_PREFIX} inline {uuid.uuid4().hex[:8]}"

    with tenant_context(tenant):
        try:
            calendrier = _make_calendar("groupe_inline")
            ouverture = _make_weekly_opening("groupe_inline")

            donnees_du_formulaire = {
                "name": nom_du_groupe,
                "description": "",
                "resources-TOTAL_FORMS": "1",
                "resources-INITIAL_FORMS": "0",
                "resources-MIN_NUM_FORMS": "0",
                "resources-MAX_NUM_FORMS": "1000",
                "resources-0-name": nom_de_la_ressource,
                "resources-0-capacity": "10",
                "resources-0-weekly_opening": str(ouverture.pk),
                "resources-0-calendar": str(calendrier.pk),
            }
            reponse = admin_client.post(
                reverse("staff_admin:booking_resourcegroup_add"),
                donnees_du_formulaire,
            )

            assert reponse.status_code == 302, reponse.content[:800]
            assert ResourceGroup.objects.filter(name=nom_du_groupe).exists()
            assert not Resource.objects.filter(name=nom_de_la_ressource).exists()
        finally:
            ResourceGroup.objects.filter(name__startswith=PREFIXE_DU_GROUPE).delete()
            _cleanup()
