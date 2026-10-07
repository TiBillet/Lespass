"""
La liste des assets s'affiche sur un lieu qui n'est pas relie a Fedow.
/ The asset list renders on a venue that is not linked to Fedow.

LOCALISATION : tests/pytest/test_admin_asset_sans_fedow.py

LE BUG PROTEGE / THE BUG
------------------------
`AssetAdmin.get_queryset()` instanciait `FedowAPI()` a chaque affichage de la
liste. Sur un lieu sans place Fedow (`can_fedow()` faux), `PlaceFedow.__init__`
lance alors `create_place()`. Sur le lieu `meta` (agenda), aucun admin n'est
rattache au lieu : `admin.email` leve `AttributeError`, et la page repond 500.
/ On a venue without a Fedow place, instantiating FedowAPI() triggers
  create_place(); with no venue admin, `admin.email` raises and the page is a 500.

Le lieu `meta` de la base de dev est exactement ce cas : pas de place Fedow,
pas d'admin de lieu. Le test le prend tel quel, sans rien ecrire.
/ The dev `meta` venue is exactly this case. The test uses it read-only.

Lancement / Run:
    make test ARGS="tests/pytest/test_admin_asset_sans_fedow.py"
"""

import pytest
from django.test import Client as HttpClient
from django.urls import reverse
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from Customers.models import Client
from fedow_connect.models import FedowConfig


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse the dev database.
    pass


@pytest.mark.django_db
def test_la_liste_des_assets_repond_sur_un_lieu_sans_fedow():
    """Sur `meta` (sans place Fedow), la liste des assets repond 200, pas 500.
    / On `meta` (no Fedow place), the asset list answers 200, not 500."""
    lieu_meta = Client.objects.get(schema_name="meta")
    domaine = lieu_meta.domains.first()
    if domaine is None:
        pytest.fail("Le lieu 'meta' n'a aucun domaine : impossible d'ouvrir son admin.")

    with tenant_context(lieu_meta):
        # Le test ne prouve quelque chose que si le lieu n'est PAS relie a Fedow.
        # / The test only proves something if the venue is NOT linked to Fedow.
        if FedowConfig.get_solo().can_fedow():
            pytest.fail("Le lieu 'meta' est relie a Fedow : ce test ne prouverait rien.")
        superadmin = TibilletUser.objects.filter(is_superuser=True).first()

    if superadmin is None:
        pytest.fail("Aucun superadmin dans la base de dev.")

    navigateur = HttpClient(HTTP_HOST=domaine.domain)
    navigateur.force_login(superadmin)
    reponse = navigateur.get(reverse("staff_admin:fedow_public_assetfedowpublic_changelist"))

    assert reponse.status_code == 200


@pytest.mark.django_db
def test_l_admin_ne_cree_plus_d_asset_legacy():
    """Plus de creation d'asset legacy depuis l'admin (decision du 2026-10-06, en
    attendant H-2 / H-3) : la page d'ajout repond 403, meme au superadmin, et la liste
    n'a plus de lien d'ajout. Lecture seule sur `meta`.
    / No more legacy asset creation from the admin: add page 403, no add link."""
    lieu_meta = Client.objects.get(schema_name="meta")
    domaine = lieu_meta.domains.first()
    if domaine is None:
        pytest.fail("Le lieu 'meta' n'a aucun domaine : impossible d'ouvrir son admin.")
    superadmin = TibilletUser.objects.filter(is_superuser=True).first()
    if superadmin is None:
        pytest.fail("Aucun superadmin dans la base de dev.")

    navigateur = HttpClient(HTTP_HOST=domaine.domain)
    navigateur.force_login(superadmin)
    adresse_d_ajout = reverse("staff_admin:fedow_public_assetfedowpublic_add")

    reponse_ajout = navigateur.get(adresse_d_ajout)
    assert reponse_ajout.status_code == 403

    reponse_liste = navigateur.get(
        reverse("staff_admin:fedow_public_assetfedowpublic_changelist")
    )
    assert reponse_liste.status_code == 200
    assert adresse_d_ajout not in reponse_liste.content.decode()
