"""
Liste des événements de l'API v2 (`GET /api/v2/events/`) : son coût ne dépend pas du nombre
d'événements.
/ API v2 event list: its cost does not depend on the number of events.

LOCALISATION : tests/pytest/test_api_v2_liste_des_evenements.py

Code testé / Tested code : api_v2/views.py (EventViewSet.list), api_v2/serializers.py
(EventSchemaSerializer).

La liste renvoie tous les événements publiés. Si chaque événement déclenche ses propres
requêtes SQL (adresse, tags, options, domaine du lieu), la liste ralentit à mesure que le lieu
accumule des événements, jusqu'à dépasser le délai des clients de l'API.
/ The list returns every published event: per-event SQL queries would slow it down as events
pile up.

Chaque test est marqué `django_db` : transaction annulée à la fin, rien ne reste en base.
Lancer / Run : make test ARGS="tests/pytest/test_api_v2_liste_des_evenements.py"
"""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import identifiant_unique, taches_celery_enregistrees

pytestmark = pytest.mark.django_db


def nombre_de_requetes_de_la_liste(api_client, auth_headers):
    """Appelle la liste des événements et renvoie le nombre de requêtes SQL qu'elle a faites.
    / Calls the event list and returns how many SQL queries it made."""
    with CaptureQueriesContext(connection) as requetes:
        reponse = api_client.get("/api/v2/events/", **auth_headers)
    assert reponse.status_code == 200
    return len(requetes.captured_queries)


def creer_un_evenement_publie_avec_tag_et_options():
    """Un événement publié, avec un tag, une option « radio » et une option « case à cocher ».
    Son adresse est celle de la configuration du lieu (posée par Event.save()).
    / A published event with a tag and two options; its address comes from Event.save()."""
    from BaseBillet.models import Event, OptionGenerale, Tag

    suffixe = identifiant_unique()
    evenement = Event.objects.create(
        name=f"TEST_liste_api {suffixe}",
        datetime=timezone.now() + timedelta(days=10),
        published=True,
    )
    evenement.tag.add(
        Tag.objects.create(name=f"TEST {suffixe}", slug=f"test-{suffixe}")
    )
    evenement.options_radio.add(OptionGenerale.objects.create(name=f"R {suffixe}"))
    evenement.options_checkbox.add(OptionGenerale.objects.create(name=f"C {suffixe}"))
    return evenement


def test_la_liste_des_evenements_ne_fait_pas_plus_de_requetes_avec_plus_d_evenements(
    tenant, api_client, auth_headers
):
    """
    Cinq événements publiés de plus (avec adresse, tag et options) : la liste fait le même
    nombre de requêtes SQL qu'avant. Adresse, tags, options et domaine du lieu sont chargés
    en une fois pour toute la liste, pas événement par événement.
    / Five more published events: the list makes the same number of SQL queries.
    """
    with tenant_context(tenant), taches_celery_enregistrees():
        # Premier appel : réchauffe les caches (configuration, images). On mesure au second.
        # / First call warms caches up; measure on the second one.
        nombre_de_requetes_de_la_liste(api_client, auth_headers)
        requetes_avant = nombre_de_requetes_de_la_liste(api_client, auth_headers)
        for _numero in range(5):
            creer_un_evenement_publie_avec_tag_et_options()
        nombre_de_requetes_de_la_liste(api_client, auth_headers)
        requetes_apres = nombre_de_requetes_de_la_liste(api_client, auth_headers)

    assert requetes_apres == requetes_avant


def test_la_liste_des_evenements_ne_fait_pas_plus_de_requetes_avec_des_sous_evenements(
    tenant, api_client, auth_headers
):
    """
    Cinq sous-événements de plus, rattachés à un événement parent : la liste fait le même
    nombre de requêtes SQL. Le champ `superEvent` du sérialiseur lit `instance.parent` : sans
    préchargement, chaque sous-événement ajoute sa requête, et un festival n'est presque fait
    que de sous-événements.
    / Five more sub-events attached to a parent: the list makes the same number of SQL queries.
    """
    from BaseBillet.models import Event

    with tenant_context(tenant), taches_celery_enregistrees():
        nombre_de_requetes_de_la_liste(api_client, auth_headers)
        requetes_avant = nombre_de_requetes_de_la_liste(api_client, auth_headers)

        festival = creer_un_evenement_publie_avec_tag_et_options()
        for _numero in range(5):
            sous_evenement = creer_un_evenement_publie_avec_tag_et_options()
            # update() : pas de signal post_save (il vide des caches et relit la configuration).
            # / update(): no post_save signal (it clears caches and reads the configuration).
            Event.objects.filter(pk=sous_evenement.pk).update(parent=festival)

        nombre_de_requetes_de_la_liste(api_client, auth_headers)
        requetes_apres = nombre_de_requetes_de_la_liste(api_client, auth_headers)

    assert requetes_apres == requetes_avant
