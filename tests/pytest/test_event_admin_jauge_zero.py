"""
Admin des événements : un événement avec une jauge à zéro ne casse pas la liste.
/ Event admin: an event with a zero capacity does not break the list.

LOCALISATION : tests/pytest/test_event_admin_jauge_zero.py

Code testé : Administration/admin_tenant.py
- EventAdmin.get_queryset() : annotation `valid_tickets_percentage`
- EventAdmin.display_valid_tickets_percentage() : la colonne « Pourcentage »

Le pourcentage de billets valides divise par `jauge_max`. Un gestionnaire peut
saisir une jauge à 0. La division doit alors donner « pas de pourcentage », et
non une erreur SQL qui fait tomber toute la liste des événements du lieu.
/ The percentage divides by jauge_max. A zero capacity must give "no percentage",
  not an SQL error that breaks the whole event list.

Chaque test est marqué `django_db` : transaction annulée à la fin.
"""

import datetime

import pytest
from django.test import RequestFactory
from django.utils import timezone
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db


def creer_evenement_avec_une_jauge_a_zero():
    """
    Crée un événement racine (ni action, ni enfant) avec une jauge à 0.
    Il apparaît donc dans la liste de l'admin.
    / Creates a root event with a zero capacity: it shows up in the admin list.
    """
    from BaseBillet.models import Event

    return Event.objects.create(
        name="Test jauge à zéro",
        datetime=timezone.now() + datetime.timedelta(days=3650),
        jauge_max=0,
    )


def lire_l_evenement_comme_la_liste_de_l_admin(evenement):
    """
    Relit l'événement avec le queryset de la liste de l'admin.
    / Reads the event back through the admin changelist queryset.
    """
    from Administration.admin_tenant import EventAdmin, staff_admin_site
    from BaseBillet.models import Event

    requete = RequestFactory().get("/admin/BaseBillet/event/")
    admin_des_evenements = EventAdmin(Event, staff_admin_site)
    queryset_de_la_liste = admin_des_evenements.get_queryset(requete)
    return admin_des_evenements, queryset_de_la_liste.get(pk=evenement.pk)


def test_la_liste_se_charge_avec_une_jauge_a_zero(tenant):
    # Le `.get()` exécute la requête SQL : c'est lui qui levait la division par zéro.
    # / The .get() runs the SQL query: that is where the division by zero was raised.
    with tenant_context(tenant):
        evenement = creer_evenement_avec_une_jauge_a_zero()
        _admin, evenement_de_la_liste = lire_l_evenement_comme_la_liste_de_l_admin(
            evenement
        )

    assert evenement_de_la_liste.valid_tickets_percentage is None


def test_la_colonne_pourcentage_s_affiche_avec_une_jauge_a_zero(tenant):
    with tenant_context(tenant):
        evenement = creer_evenement_avec_une_jauge_a_zero()
        admin_des_evenements, evenement_de_la_liste = (
            lire_l_evenement_comme_la_liste_de_l_admin(evenement)
        )
        texte_de_la_colonne = admin_des_evenements.display_valid_tickets_percentage(
            evenement_de_la_liste
        )

    assert texte_de_la_colonne == "—"


def test_le_pourcentage_reste_calcule_avec_une_jauge_normale(tenant):
    # Témoin : sans billet, une jauge de 50 donne 0 %, pas « — ».
    # / Control: no ticket and a capacity of 50 gives 0%, not "—".
    from BaseBillet.models import Event

    with tenant_context(tenant):
        evenement = Event.objects.create(
            name="Test jauge normale",
            datetime=timezone.now() + datetime.timedelta(days=3650),
            jauge_max=50,
        )
        admin_des_evenements, evenement_de_la_liste = (
            lire_l_evenement_comme_la_liste_de_l_admin(evenement)
        )
        texte_de_la_colonne = admin_des_evenements.display_valid_tickets_percentage(
            evenement_de_la_liste
        )

    assert texte_de_la_colonne == "0.0%"


def test_la_fiche_de_l_evenement_s_ouvre_avec_une_jauge_a_zero(tenant):
    # La page de modification charge l'événement par get_object(), qui passe
    # aussi par get_queryset() et donc par le calcul du pourcentage.
    # / The change page loads the event through get_object(), which also uses
    #   get_queryset() and therefore the percentage computation.
    from Administration.admin_tenant import EventAdmin, staff_admin_site
    from BaseBillet.models import Event

    with tenant_context(tenant):
        evenement = creer_evenement_avec_une_jauge_a_zero()
        requete = RequestFactory().get(
            f"/admin/BaseBillet/event/{evenement.pk}/change/"
        )
        evenement_de_la_fiche = EventAdmin(Event, staff_admin_site).get_object(
            requete, str(evenement.pk)
        )

    assert evenement_de_la_fiche.pk == evenement.pk
