"""
Champs internes de l'événement : commentaire, comm' envoyée, ressource bloquée.
/ Event internal fields: comment, communication sent, blocked resource.

LOCALISATION : tests/pytest/test_event_champs_internes.py

Code testé :
- BaseBillet/models.py : Event.commentaire_interne, communication_envoyee, ressource_bloquee
- Administration/admin_tenant.py : EventForm.clean(), EventAdmin.get_fieldsets()
- api_v2/serializers.py, ApiBillet/serializers.py : les champs internes ne sortent jamais

Le blocage des créneaux lui-même est testé dans
booking/tests/test_ressource_bloquee_par_evenement.py.
"""
import datetime

import pytest
from django.test import RequestFactory
from django.utils import timezone
from django_tenants.utils import tenant_context

CHAMPS_INTERNES = ("commentaire_interne", "communication_envoyee", "ressource_bloquee")


def test_aucun_serializer_d_api_n_expose_les_champs_internes():
    """
    Les serializers d'événement des API v1 et v2 ne listent aucun champ interne.
    / Neither the v1 nor the v2 event serializer lists an internal field.
    """
    from ApiBillet.serializers import EventSerializer
    from api_v2.serializers import EventSchemaSerializer

    for classe_de_serializer in (EventSchemaSerializer, EventSerializer):
        champs_exposes = set(classe_de_serializer.Meta.fields)
        for nom_du_champ in CHAMPS_INTERNES:
            assert nom_du_champ not in champs_exposes, (
                f"{classe_de_serializer.__name__} expose {nom_du_champ}"
            )


@pytest.mark.django_db
def test_le_formulaire_admin_exige_une_date_de_fin_quand_une_ressource_est_bloquee(tenant):
    """
    Choisir une ressource bloquée sans date de fin : erreur sur la date de fin.
    Avec une date de fin : plus d'erreur sur ce champ.
    / Blocked resource without end date: error on the end date; with one: none.
    """
    from Administration.admin_tenant import EventForm
    from booking.tests.test_booking_engine import (
        _cleanup,
        _make_calendar,
        _make_resource,
        _make_weekly_opening,
    )

    with tenant_context(tenant):
        try:
            salle = _make_resource(
                "champs_internes_form",
                _make_calendar("champs_internes_form"),
                _make_weekly_opening("champs_internes_form"),
            )
            debut = timezone.localtime(timezone.now()) + datetime.timedelta(days=10)
            donnees_du_formulaire = {
                "name": "Concert dans la salle",
                "datetime": debut.strftime("%Y-%m-%d %H:%M:%S"),
                "jauge_max": 50,
                "ressource_bloquee": str(salle.pk),
            }

            formulaire_sans_fin = EventForm(data=donnees_du_formulaire)
            formulaire_sans_fin.is_valid()
            erreurs_sur_la_fin = formulaire_sans_fin.errors.get("end_datetime", [])
            assert "Une date de fin est obligatoire pour bloquer une ressource." in erreurs_sur_la_fin

            donnees_avec_fin = dict(donnees_du_formulaire)
            donnees_avec_fin["end_datetime"] = (debut + datetime.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
            formulaire_avec_fin = EventForm(data=donnees_avec_fin)
            formulaire_avec_fin.is_valid()
            assert "end_datetime" not in formulaire_avec_fin.errors
        finally:
            _cleanup()


@pytest.mark.django_db
def test_la_ressource_bloquee_n_apparait_dans_la_fiche_que_si_le_module_reservation_est_actif(tenant):
    """
    Module réservation éteint : le champ disparaît de la fiche. Allumé : il est là.
    Les deux autres champs internes sont toujours là.
    / Booking module off: the field is hidden; on: shown. The other two always are.
    """
    from Administration.admin_tenant import EventAdmin, staff_admin_site
    from BaseBillet.models import Configuration, Event

    def champs_de_la_fiche():
        admin_des_evenements = EventAdmin(Event, staff_admin_site)
        requete = RequestFactory().get("/admin/BaseBillet/event/add/")
        tous_les_champs = []
        for _titre, options_du_bloc in admin_des_evenements.get_fieldsets(requete):
            tous_les_champs.extend(options_du_bloc["fields"])
        return tous_les_champs

    with tenant_context(tenant):
        configuration = Configuration.get_solo()
        valeur_d_origine = configuration.module_booking
        try:
            configuration.module_booking = False
            configuration.save()
            champs_module_eteint = champs_de_la_fiche()
            assert "ressource_bloquee" not in champs_module_eteint
            assert "commentaire_interne" in champs_module_eteint
            assert "communication_envoyee" in champs_module_eteint

            configuration.module_booking = True
            configuration.save()
            assert "ressource_bloquee" in champs_de_la_fiche()
        finally:
            configuration.module_booking = valeur_d_origine
            configuration.save()
