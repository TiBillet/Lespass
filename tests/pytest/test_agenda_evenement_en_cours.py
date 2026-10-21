"""
Agenda : un événement commencé mais pas terminé reste affiché.
/ Agenda: a started but unfinished event stays listed.

LOCALISATION : tests/pytest/test_agenda_evenement_en_cours.py

Code testé : BaseBillet/views.py, EventMVT.federated_events_filter()

Les tests passent TOUJOURS par une recherche sur un nom unique, même avec un filtre
par jour : un filtre combiné n'est jamais mis en cache. Sans elle, le résultat irait
dans le memcached partagé avec le serveur de dev, et un événement annulé par le
rollback s'afficherait sur l'agenda (tests/PIEGES.md 13.5). Seuls les événements du
test sortent (pas ceux de la démo).
Chaque test est marqué `django_db` : transaction annulée à la fin.
"""
import datetime
import uuid

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db


def noms_affiches_dans_l_agenda(recherche):
    """Les noms des événements que l'agenda affiche pour cette recherche. / Listed names."""
    from BaseBillet.views import EventMVT

    evenements_par_date = EventMVT.federated_events_filter(search=recherche)[0]
    noms = []
    for evenements_du_jour in evenements_par_date.values():
        for evenement in evenements_du_jour:
            noms.append(evenement.name)
    return noms


def creer_evenement(nom, debut, fin=None):
    from BaseBillet.models import Event

    return Event.objects.create(name=nom, datetime=debut, end_datetime=fin, published=True)


def test_un_evenement_en_cours_reste_dans_l_agenda_jusqu_a_sa_date_de_fin(tenant):
    # Une expo commencée il y a 10 jours, qui finit dans 10 jours.
    # / An exhibition that started 10 days ago and ends in 10 days.
    prefixe = f"TEST expo {uuid.uuid4().hex[:8]}"
    maintenant = timezone.now()
    with tenant_context(tenant):
        creer_evenement(
            f"{prefixe} en cours",
            debut=maintenant - datetime.timedelta(days=10),
            fin=maintenant + datetime.timedelta(days=10),
        )

        assert noms_affiches_dans_l_agenda(prefixe) == [f"{prefixe} en cours"]


def test_un_evenement_termine_ou_sans_date_de_fin_ne_revient_pas_dans_l_agenda(tenant):
    prefixe = f"TEST expo {uuid.uuid4().hex[:8]}"
    maintenant = timezone.now()
    with tenant_context(tenant):
        creer_evenement(
            f"{prefixe} terminée",
            debut=maintenant - datetime.timedelta(days=10),
            fin=maintenant - datetime.timedelta(days=2),
        )
        creer_evenement(
            f"{prefixe} sans fin",
            debut=maintenant - datetime.timedelta(days=10),
        )

        assert noms_affiches_dans_l_agenda(prefixe) == []


# ---------------------------------------------------------------------------
# Filtre par jour (menu « Trier par date ») / Day filter
# ---------------------------------------------------------------------------

def test_un_jour_choisi_montre_l_expo_en_cours_rangee_sous_ce_jour(tenant):
    from BaseBillet.views import EventMVT

    nom = f"TEST expo {uuid.uuid4().hex[:8]}"
    maintenant = timezone.now()
    jour_choisi = timezone.localdate() + datetime.timedelta(days=3)
    with tenant_context(tenant):
        creer_evenement(
            nom,
            debut=maintenant - datetime.timedelta(days=10),
            fin=maintenant + datetime.timedelta(days=10),
        )

        evenements_par_date = EventMVT.federated_events_filter(date_filter=jour_choisi, search=nom)[0]

        assert nom in [evenement.name for evenement in evenements_par_date.get(jour_choisi, [])]


def test_un_jour_apres_la_fin_de_l_expo_ne_la_montre_pas(tenant):
    from BaseBillet.views import EventMVT

    nom = f"TEST expo {uuid.uuid4().hex[:8]}"
    maintenant = timezone.now()
    jour_apres_la_fin = timezone.localdate() + datetime.timedelta(days=12)
    with tenant_context(tenant):
        creer_evenement(
            nom,
            debut=maintenant - datetime.timedelta(days=10),
            fin=maintenant + datetime.timedelta(days=10),
        )

        evenements_par_date = EventMVT.federated_events_filter(date_filter=jour_apres_la_fin, search=nom)[0]

        tous_les_noms = []
        for evenements_du_jour in evenements_par_date.values():
            for evenement in evenements_du_jour:
                tous_les_noms.append(evenement.name)
        assert nom not in tous_les_noms


def test_le_menu_des_jours_propose_aujourd_hui_pour_une_expo_en_cours_pas_son_jour_de_debut(tenant):
    from BaseBillet.views import EventMVT

    prefixe = f"TEST expo {uuid.uuid4().hex[:8]}"
    maintenant = timezone.now()
    with tenant_context(tenant):
        evenement = creer_evenement(
            prefixe,
            debut=maintenant - datetime.timedelta(days=10),
            fin=maintenant + datetime.timedelta(days=10),
        )

        jours_du_menu = EventMVT.federated_events_filter(search=prefixe)[2]

        assert jours_du_menu == [timezone.localdate()]
        assert timezone.localdate(evenement.datetime) not in jours_du_menu


# ---------------------------------------------------------------------------
# Carte et explorateur (cache SEO) / Map and explorer (SEO cache)
# Code testé : seo/services.py, get_events_for_tenants(), get_counts_for_tenant()
# ---------------------------------------------------------------------------

def test_la_carte_garde_l_expo_en_cours_et_oublie_l_evenement_termine(tenant):
    from seo.services import get_events_for_tenants

    prefixe = f"TEST expo {uuid.uuid4().hex[:8]}"
    maintenant = timezone.now()
    with tenant_context(tenant):
        creer_evenement(
            f"{prefixe} en cours",
            debut=maintenant - datetime.timedelta(days=10),
            fin=maintenant + datetime.timedelta(days=10),
        )
        creer_evenement(
            f"{prefixe} terminée",
            debut=maintenant - datetime.timedelta(days=10),
            fin=maintenant - datetime.timedelta(days=2),
        )

        evenements_de_la_carte = get_events_for_tenants([(tenant.uuid, tenant.schema_name)])

    noms_du_test = []
    for evenement_de_la_carte in evenements_de_la_carte:
        if evenement_de_la_carte["name"].startswith(prefixe):
            noms_du_test.append(evenement_de_la_carte["name"])
    assert noms_du_test == [f"{prefixe} en cours"]


def test_le_compteur_d_evenements_du_lieu_compte_l_expo_en_cours(tenant):
    from seo.services import get_counts_for_tenant

    maintenant = timezone.now()
    with tenant_context(tenant):
        compte_avant = get_counts_for_tenant(tenant.schema_name)["event_count"]
        creer_evenement(
            f"TEST expo {uuid.uuid4().hex[:8]}",
            debut=maintenant - datetime.timedelta(days=10),
            fin=maintenant + datetime.timedelta(days=10),
        )

        assert get_counts_for_tenant(tenant.schema_name)["event_count"] == compte_avant + 1
