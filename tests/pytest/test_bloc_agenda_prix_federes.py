"""
Test : le bloc LISTE / EVENEMENTS garde le prix pose par le filtre federe.
/ Test: the LISTE / EVENEMENTS block keeps the price set by the federated filter.

LOCALISATION : tests/pytest/test_bloc_agenda_prix_federes.py

Code teste : pages/templatetags/pages_tags.py:agenda_a_venir_du_bloc.

EventMVT.federated_events_filter pose `price_min` DANS le tenant_context de
chaque evenement (ses tarifs vivent dans son schema). Un evenement d'un lieu
federe n'a donc un prix juste QUE si personne ne le recalcule apres, hors de ce
contexte : il sortirait « Entré libre » a chaque fois.

Le filtre est remplace par un faux (mock) : pas de base, pas de federation a
monter. Seul le comportement du tag est verifie.
/ The filter is mocked: no database, no federation setup. Only the tag's
behaviour is checked.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from pages.templatetags.pages_tags import agenda_a_venir_du_bloc


def _faux_resultat_du_filtre_federe():
    """
    Imite le retour de federated_events_filter : evenements ranges par jour,
    chacun avec un price_min deja pose dans son propre lieu.
    / Mimics the filter's return: events grouped by day, price_min already set.
    """
    demain = datetime(2030, 1, 2, 20, 0)
    apres_demain = demain + timedelta(days=1)
    evenement_d_un_lieu_federe = SimpleNamespace(
        name="Concert federe",
        datetime=apres_demain,
        price_min="A partir de 12.00 €",
    )
    evenement_du_lieu = SimpleNamespace(
        name="Atelier du lieu",
        datetime=demain,
        price_min="Prix libre",
    )
    evenements_par_jour = {
        apres_demain.date(): [evenement_d_un_lieu_federe],
        demain.date(): [evenement_du_lieu],
    }
    return evenements_par_jour, {}, [], [], []


def test_le_bloc_garde_le_prix_pose_par_le_filtre_federe():
    with mock.patch(
        "BaseBillet.views.EventMVT.federated_events_filter",
        return_value=_faux_resultat_du_filtre_federe(),
    ):
        agenda = agenda_a_venir_du_bloc(6)

    prix_par_nom = {
        evenement.name: evenement.price_min for evenement in agenda["evenements"]
    }
    assert prix_par_nom["Concert federe"] == "A partir de 12.00 €"
    assert prix_par_nom["Atelier du lieu"] == "Prix libre"


def test_le_bloc_trie_par_date_et_compte_tous_les_evenements():
    with mock.patch(
        "BaseBillet.views.EventMVT.federated_events_filter",
        return_value=_faux_resultat_du_filtre_federe(),
    ):
        agenda = agenda_a_venir_du_bloc(1)

    # Une seule carte demandee : la plus proche dans le temps.
    # Le compteur, lui, annonce tous les evenements a venir.
    # / One card requested: the soonest. The counter announces all of them.
    assert [evenement.name for evenement in agenda["evenements"]] == ["Atelier du lieu"]
    assert agenda["total"] == 2
    assert agenda["nombre_de_cartes"] == 1
