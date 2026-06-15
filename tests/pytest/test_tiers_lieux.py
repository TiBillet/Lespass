"""
Tests du client API Tiers-Lieux (CHANTIER-04).
/ Tests for the Tiers-Lieux API client.

LOCALISATION : tests/pytest/test_tiers_lieux.py

On mocke `requests.get` : aucun appel réseau réel, aucun accès DB.
Voir SESSIONS/EVENT_WIZARD/CHANTIER-04-integration-tiers-lieux.md.
"""

import uuid as uuidlib
from unittest.mock import MagicMock, patch

import pytest
import requests

from BaseBillet.services.tiers_lieux import (
    _construire_rue,
    _normaliser_fiche,
    rechercher_tiers_lieux,
    valider_coordonnees,
)


def test_valider_coordonnees_tolere_la_virgule_et_rejette_le_garbage():
    """Régression : un float localisé FR (« 44,05 ») doit être accepté et
    converti, sinon le pré-remplissage GPS de la carte casse. Le texte arbitraire
    (POST forgé), None et les coordonnées hors bornes sont rejetés -> (None, None)."""
    # Virgule décimale (rendu localisé) tolérée -> floats normalisés au point.
    assert valider_coordonnees("44,053909", "3,986721") == (44.053909, 3.986721)
    # Point décimal (format machine) accepté.
    assert valider_coordonnees("44.05", "3.98") == (44.05, 3.98)
    # Floats déjà typés acceptés.
    assert valider_coordonnees(-21.0096, 55.2705) == (-21.0096, 55.2705)
    # Mauvais inputs -> (None, None), jamais d'exception.
    assert valider_coordonnees("<script>alert(1)</script>", "x") == (None, None)
    assert valider_coordonnees(None, None) == (None, None)
    assert valider_coordonnees("", "") == (None, None)
    # Hors bornes terrestres -> rejeté.
    assert valider_coordonnees("200", "0") == (None, None)
    assert valider_coordonnees("0", "-181") == (None, None)


# ----------------------------------------------------------------------------
# Fixtures DB (réutilise la base de dev, comme les autres tests wizard).
# / DB fixtures (reuse dev DB, like the other wizard tests).
# ----------------------------------------------------------------------------

@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse dev DB (no test DB creation).
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()


# Fiche brute type, calquée sur l'exemple de la doc API (La Raffinerie).
# / Sample raw record, modeled on the API doc (La Raffinerie).
FICHE_BRUTE_RAFFINERIE = {
    "id": 3692,
    "Identifiant_national": "15ecb291-e759-4cfe-b9b0-55dbf2923640",
    "nom_tiers_lieu": "La Raffinerie",
    "adresse_nationale": "Avenue de Bourbon 97434 Saint-Paul",
    "adresse_nationale_cp": "97434",
    "adresse_nationale_ville": "Saint-Paul",
    "adresse_nationale_region": "La Reunion",
    "adresse_nationale_lat": -21.065862,
    "adresse_nationale_lon": 55.222177,
}


def _fausse_reponse(payload, status=200):
    """Construit une fausse réponse requests. / Build a fake requests response."""
    reponse = MagicMock()
    reponse.json.return_value = payload
    reponse.raise_for_status.return_value = None
    reponse.status_code = status
    return reponse


def test_construire_rue_retire_cp_et_ville():
    """La rue déduite ne contient ni le code postal ni la ville."""
    rue = _construire_rue("Avenue de Bourbon 97434 Saint-Paul", "97434", "Saint-Paul")
    assert rue == "Avenue de Bourbon"


def test_normaliser_fiche_mappe_les_champs_postal_address():
    """La fiche brute est traduite vers nos champs PostalAddress."""
    fiche = _normaliser_fiche(FICHE_BRUTE_RAFFINERIE)
    assert fiche["name"] == "La Raffinerie"
    assert fiche["postal_code"] == "97434"
    assert fiche["locality"] == "Saint-Paul"
    assert fiche["street_address"] == "Avenue de Bourbon"
    assert fiche["latitude"] == -21.065862
    assert fiche["longitude"] == 55.222177
    assert fiche["country"] == "France"
    assert fiche["identifiant_national"] == "15ecb291-e759-4cfe-b9b0-55dbf2923640"


def test_rechercher_terme_vide_ne_fait_aucun_appel():
    """Un terme vide -> liste vide, sans appel réseau."""
    with patch("BaseBillet.services.tiers_lieux.requests.get") as faux_get:
        assert rechercher_tiers_lieux("") == []
        assert rechercher_tiers_lieux("   ") == []
        faux_get.assert_not_called()


def test_rechercher_succes_renvoie_fiches_normalisees():
    """Réponse OK -> liste de fiches normalisées."""
    terme = f"raffinerie-{uuidlib.uuid4().hex[:8]}"  # terme unique -> pas de cache partagé
    payload = {"hits": [FICHE_BRUTE_RAFFINERIE]}
    with patch("BaseBillet.services.tiers_lieux.requests.get",
               return_value=_fausse_reponse(payload)) as faux_get:
        resultats = rechercher_tiers_lieux(terme)
        faux_get.assert_called_once()
        assert len(resultats) == 1
        assert resultats[0]["name"] == "La Raffinerie"


def test_rechercher_timeout_renvoie_liste_vide():
    """Timeout réseau -> [] (jamais d'exception propagée)."""
    terme = f"timeout-{uuidlib.uuid4().hex[:8]}"
    with patch("BaseBillet.services.tiers_lieux.requests.get",
               side_effect=requests.Timeout("trop lent")):
        assert rechercher_tiers_lieux(terme) == []


def test_rechercher_erreur_reseau_renvoie_liste_vide():
    """Erreur réseau quelconque -> [] (jamais d'exception propagée)."""
    terme = f"erreur-{uuidlib.uuid4().hex[:8]}"
    with patch("BaseBillet.services.tiers_lieux.requests.get",
               side_effect=requests.ConnectionError("injoignable")):
        assert rechercher_tiers_lieux(terme) == []


def test_rechercher_met_en_cache_et_evite_un_second_appel():
    """Deux appels avec le même terme -> un seul appel réseau (cache)."""
    terme = f"cache-{uuidlib.uuid4().hex[:8]}"
    payload = {"hits": [FICHE_BRUTE_RAFFINERIE]}
    with patch("BaseBillet.services.tiers_lieux.requests.get",
               return_value=_fausse_reponse(payload)) as faux_get:
        premier = rechercher_tiers_lieux(terme)
        second = rechercher_tiers_lieux(terme)
        assert premier == second
        # Le deuxième appel a été servi par le cache : un seul appel réseau.
        # / The second call was served from cache: a single network call.
        faux_get.assert_called_once()


# ----------------------------------------------------------------------------
# Endpoints HTMX du wizard (check-instance, search-tierslieux).
# / Wizard HTMX endpoints.
# ----------------------------------------------------------------------------


def _http_client_lespass():
    """Client HTTP anonyme routé sur le tenant lespass. / Anonymous client on lespass."""
    from django.test.client import Client as DjangoClient
    from Customers.models import Client

    lespass = Client.objects.get(schema_name="lespass")
    domain = lespass.domains.first()
    return DjangoClient(HTTP_HOST=domain.domain), lespass


@pytest.mark.django_db
def test_check_instance_avec_instance_affiche_le_nom():
    """Un email administrant une instance -> encart avec le nom de l'instance."""
    from django.urls import reverse
    from django_tenants.utils import tenant_context
    from AuthBillet.models import TibilletUser

    http, lespass = _http_client_lespass()
    email = f"admin-tl-{uuidlib.uuid4().hex[:8]}@example.org"
    with tenant_context(lespass):
        user = TibilletUser.objects.create(email=email)
        user.client_admin.add(lespass)
    try:
        resp = http.get(reverse("event-wizard-check-instance"),
                        {"email_proposeur": email})
        assert resp.status_code == 200
        assert b"wizard-instance-found" in resp.content
        assert lespass.name.encode() in resp.content
    finally:
        with tenant_context(lespass):
            TibilletUser.objects.filter(email=email).delete()


@pytest.mark.django_db
def test_check_instance_email_inconnu_renvoie_vide():
    """Un email inconnu -> réponse vide (pas d'encart)."""
    from django.urls import reverse

    http, _ = _http_client_lespass()
    resp = http.get(reverse("event-wizard-check-instance"),
                    {"email_proposeur": f"inconnu-{uuidlib.uuid4().hex[:8]}@nulle-part.test"})
    assert resp.status_code == 200
    assert resp.content.strip() == b""


@pytest.mark.django_db
def test_search_tierslieux_terme_court_renvoie_vide():
    """Terme < 3 caractères -> réponse vide (pas d'appel API)."""
    from django.urls import reverse

    http, _ = _http_client_lespass()
    resp = http.get(reverse("event-wizard-search-tierslieux"), {"q": "ab"})
    assert resp.status_code == 200
    assert resp.content.strip() == b""


@pytest.mark.django_db
def test_search_tierslieux_rend_les_fiches(monkeypatch):
    """Terme valide -> le service est appelé et les fiches sont rendues."""
    from django.urls import reverse

    fiche = {
        "name": "La Raffinerie", "street_address": "Avenue de Bourbon",
        "postal_code": "97434", "locality": "Saint-Paul", "region": "La Reunion",
        "country": "France", "latitude": -21.06, "longitude": 55.22,
        "identifiant_national": "abc",
    }
    monkeypatch.setattr(
        "BaseBillet.services.tiers_lieux.rechercher_tiers_lieux",
        lambda terme, limite=5: [fiche],
    )
    http, _ = _http_client_lespass()
    resp = http.get(reverse("event-wizard-search-tierslieux"), {"q": "raffinerie"})
    assert resp.status_code == 200
    assert b"wizard-tierslieux-results" in resp.content
    assert b"La Raffinerie" in resp.content
