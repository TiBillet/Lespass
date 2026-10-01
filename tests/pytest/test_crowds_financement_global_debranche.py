"""
Tests pytest : le financement global des crowds est debranche.
/ Pytest tests: crowds global funding is disconnected.

LOCALISATION : tests/pytest/test_crowds_financement_global_debranche.py

Le modele GlobalFunding et ses donnees restent en base. Seuls la route, la vue et le
bouton disparaissent.
/ The GlobalFunding model and its data stay in the database. Only the route, the view
and the button are removed.
"""

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse

URLCONF_TENANT = "TiBillet.urls_tenants"


@pytest.mark.parametrize(
    "nom_de_route",
    [
        "crowds-global-funding-list",
        "crowds-global-funding-allocate",
        "crowds-global-funding-funded-total",
    ],
)
def test_les_routes_du_financement_global_n_existent_plus(nom_de_route):
    """Aucune route du financement global n'est declaree.
    / No global funding route is declared.
    """
    with pytest.raises(NoReverseMatch):
        reverse(nom_de_route, urlconf=URLCONF_TENANT)


def test_le_resume_crowds_n_affiche_plus_le_bouton_meme_si_le_reglage_est_actif():
    """Avec global_funding_button=True, la page d'accueil des crowds ne montre aucun
    bouton de financement global.
    / With global_funding_button=True, the crowds home page shows no global funding button.
    """
    configuration_crowds_factice = SimpleNamespace(
        global_funding_button=True,
        global_funding_button_text="Je finance",
    )
    contexte_du_resume = {
        "crowd_config": configuration_crowds_factice,
        "user": AnonymousUser(),
    }

    html_du_resume = render_to_string("crowds/partial/summary.html", contexte_du_resume)

    assert "crowds-summary-global-funding-button" not in html_du_resume
    assert "crowdsOpenGlobalFunding" not in html_du_resume
