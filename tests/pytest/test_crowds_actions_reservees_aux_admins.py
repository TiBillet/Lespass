"""
Les actions de gestion d'un projet crowds sont réservées aux admins du lieu.
/ Crowds management actions are reserved to the venue admins.

LOCALISATION : tests/pytest/test_crowds_actions_reservees_aux_admins.py

Code testé : crowds/views.py, les actions `close`, `archive`, `mark-paid`,
`budget-items/<bid>/approve|reject`, `participations/<pid>/approve|validate`.
Elles partagent le même contrôle :
`request.user.is_superuser or request.user.is_current_tenant_admin()`.
/ Tested code: the crowds management actions and their shared admin check.

RÈGLE TESTÉE :
- admin du lieu OU superuser : rien d'autre ;
- `is_staff` ne donne aucun droit : ce drapeau est partagé par tous les lieux
  (schéma public). L'admin d'un autre lieu a `is_staff=True`, il ne doit rien
  pouvoir faire ici ;
- `is_current_tenant_admin` est une MÉTHODE : sans `()`, Python la voit comme
  vraie, et tout compte connecté passerait.
/ Venue admin OR superuser only. `is_staff` is shared by every venue and grants nothing.

Lancer / Run :
docker exec lespass_django bash -c "ulimit -v 8000000; timeout 600 poetry run pytest /DjangoFiles/tests/pytest/test_crowds_actions_reservees_aux_admins.py -v"
"""

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import client_connecte, creer_utilisateur, identifiant_unique

pytestmark = pytest.mark.django_db


def creer_une_initiative_ouverte():
    """Un projet crowds ouvert, au nom unique.
    / An open crowds project with a unique name."""
    from crowds.models import Initiative

    return Initiative.objects.create(name=f"Projet test {identifiant_unique()}")


def creer_une_proposition_de_budget(initiative, porteur):
    """Une ligne de budget en attente de validation.
    / A budget line waiting for approval."""
    from crowds.models import BudgetItem

    return BudgetItem.objects.create(
        initiative=initiative,
        contributor=porteur,
        description="Achat de matériel",
        amount=12000,
    )


def creer_l_admin_d_un_autre_lieu():
    """
    Un compte admin d'un AUTRE lieu : `is_staff=True`, mais absent du
    `client_admin` du lieu courant.
    / An admin of ANOTHER venue: is_staff=True, not in this venue's client_admin.
    """
    from Customers.models import Client

    admin_ailleurs = creer_utilisateur()
    admin_ailleurs.is_staff = True
    admin_ailleurs.save(update_fields=["is_staff"])

    autre_lieu = Client.objects.exclude(schema_name__in=["public", "lespass"]).first()
    if autre_lieu is not None:
        admin_ailleurs.client_admin.add(autre_lieu)
    return admin_ailleurs


def test_un_compte_connecte_non_admin_ne_peut_pas_cloturer_un_projet(tenant):
    with tenant_context(tenant):
        projet = creer_une_initiative_ouverte()

        reponse = client_connecte(creer_utilisateur()).post(f"/crowd/{projet.pk}/close/")

        projet.refresh_from_db()
        assert reponse.status_code == 403
        assert projet.closed is False


def test_l_admin_d_un_autre_lieu_ne_peut_pas_cloturer_un_projet_ici(tenant):
    with tenant_context(tenant):
        projet = creer_une_initiative_ouverte()

        reponse = client_connecte(creer_l_admin_d_un_autre_lieu()).post(f"/crowd/{projet.pk}/close/")

        projet.refresh_from_db()
        assert reponse.status_code == 403
        assert projet.closed is False


def test_un_compte_connecte_non_admin_ne_peut_pas_valider_un_budget(tenant):
    from crowds.models import BudgetItem

    with tenant_context(tenant):
        projet = creer_une_initiative_ouverte()
        porteur = creer_utilisateur()
        proposition = creer_une_proposition_de_budget(projet, porteur)

        reponse = client_connecte(porteur).post(
            f"/crowd/{projet.pk}/budget-items/{proposition.pk}/approve/"
        )

        proposition.refresh_from_db()
        assert reponse.status_code == 403
        assert proposition.state == BudgetItem.State.REQUESTED


def test_l_admin_du_lieu_peut_cloturer_un_projet(tenant):
    with tenant_context(tenant):
        projet = creer_une_initiative_ouverte()
        admin_du_lieu = creer_utilisateur()
        admin_du_lieu.client_admin.add(tenant)

        reponse = client_connecte(admin_du_lieu).post(f"/crowd/{projet.pk}/close/")

        projet.refresh_from_db()
        assert reponse.status_code == 302
        assert projet.closed is True
