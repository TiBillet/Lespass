"""
Tests de la step « Votre lieu » (STEP_VENUE) + adresse optionnelle.
/ Tests for the "Your venue" step (STEP_VENUE) + optional address.

LOCALISATION: onboard/tests/test_step_venue.py

On vérifie :
  1. GET /onboard/venue/ (brouillon confirmé) -> 200 + formulaire.
  2. POST valide -> brouillon mis à jour (nom/slug/dns) + current_step=place
     + redirect /onboard/place/.
  3. Nom déjà pris -> 422 ; domaine déjà pris -> 422 (check déplacé ici).
  4. Adresse Tiers-Lieux choisie gardée en session pour l'étape Adresse.
  5. Étape Adresse : bouton « passer » -> avance sans adresse.

PIEGE : `WaitingConfiguration` vit dans le schema `meta` -> `schema_context("meta")`.
/ PITFALL: `WaitingConfiguration` lives in the `meta` schema.
"""

import time

import pytest
from django.test import Client, override_settings
from django_tenants.utils import schema_context

from MetaBillet.models import WaitingConfiguration


pytestmark = pytest.mark.onboard

DEV_HOST = "tibillet.localhost"


def _create_wc_at(step, client, cleanup=None, organisation="Venue Test"):
    """
    Crée un WaitingConfiguration confirmé (email_confirmed=True) positionné sur
    `step`, fixe la session du client de test et connecte l'utilisateur.
    / Create a confirmed WaitingConfiguration at `step`, pin the test client's
    session and log the user in.
    """
    unique_email = f"venue-{int(time.time() * 1000000)}@example.com"
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation=organisation,
            email=unique_email,
            dns_choice="tibillet.coop",
            email_confirmed=True,
            current_step=step,
            phone="",
        )
    if cleanup is not None:
        cleanup(wc)

    session = client.session
    session["onboard_wc_uuid"] = str(wc.uuid)
    session.save()

    from onboard.tests.helpers import login_test_user_for_email
    login_test_user_for_email(client, unique_email)
    return wc


def test_venue_get_renders_form(cleanup_waiting_configs):
    """GET /onboard/venue/ (brouillon confirmé) -> 200 + formulaire « Votre lieu »."""
    client = Client(HTTP_HOST=DEV_HOST)
    _create_wc_at(WaitingConfiguration.STEP_VENUE, client, cleanup=cleanup_waiting_configs)
    resp = client.get("/onboard/venue/")
    assert resp.status_code == 200
    assert b"onboard-venue-form" in resp.content


def test_venue_post_valid_updates_draft_and_advances(cleanup_waiting_configs):
    """POST valide -> brouillon (nom/slug/dns) mis à jour + redirect place."""
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_wc_at(WaitingConfiguration.STEP_VENUE, client, cleanup=cleanup_waiting_configs)
    suffixe = int(time.time() * 1000)
    nom = f"Lieu Test {suffixe}"
    resp = client.post("/onboard/venue/", data={
        "name": nom,
        "slug": f"lieu-test-{suffixe}",
        "dns_choice": "tibillet.coop",
    })
    assert resp.status_code in (302, 303)
    assert resp["Location"] == "/onboard/place/"
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.organisation == nom
    assert wc.slug == f"lieu-test-{suffixe}"
    assert wc.current_step == WaitingConfiguration.STEP_PLACE


def test_venue_post_existing_name_returns_422(cleanup_waiting_configs):
    """Nom déjà pris par un tenant existant (LESPASS) -> 422 sur `name`."""
    client = Client(HTTP_HOST=DEV_HOST)
    _create_wc_at(WaitingConfiguration.STEP_VENUE, client, cleanup=cleanup_waiting_configs)
    resp = client.post("/onboard/venue/", data={
        "name": "LESPASS",  # casse différente du tenant `lespass`
        "slug": f"lespass-x-{int(time.time() * 1000)}",
        "dns_choice": "tibillet.coop",
    })
    assert resp.status_code == 422
    assert b"name" in resp.content


def test_venue_serializer_rejects_existing_domain():
    """
    Domaine déjà pris -> 422 sur `slug`. En DEBUG (dev), le suffixe bascule sur
    'tibillet.localhost' (comme au Lancement) : le slug 'lespass' donne le
    domaine existant 'lespass.tibillet.localhost'. On force DEBUG=True pour un
    test déterministe quel que soit le réglage d'environnement.
    / Existing domain -> 422 on `slug`. In DEBUG the suffix becomes
    'tibillet.localhost' (like at Launch): slug 'lespass' yields the existing
    'lespass.tibillet.localhost'. We force DEBUG=True for determinism.
    """
    from onboard.serializers import OnboardVenueSerializer

    with override_settings(DEBUG=True):
        serializer = OnboardVenueSerializer(data={
            "name": f"Nom Unique {int(time.time() * 1000)}",  # nom libre -> on isole le check slug
            "slug": "lespass",
            "dns_choice": "tibillet.coop",
        })
        assert not serializer.is_valid()
        assert "slug" in serializer.errors


def test_venue_post_keeps_tl_address_in_session(cleanup_waiting_configs):
    """La fiche Tiers-Lieux choisie (GPS + adresse structurée) est gardée en
    session pour pré-remplir le widget carte de l'étape Adresse."""
    client = Client(HTTP_HOST=DEV_HOST)
    _create_wc_at(WaitingConfiguration.STEP_VENUE, client, cleanup=cleanup_waiting_configs)
    suffixe = int(time.time() * 1000)
    adresse = "La Raffinerie Avenue de Bourbon 97434 Saint-Paul"
    client.post("/onboard/venue/", data={
        "name": f"Lieu TL {suffixe}",
        "slug": f"lieu-tl-{suffixe}",
        "dns_choice": "tibillet.coop",
        "tl_adresse": adresse,
        "tl_lat": "-21.0096",
        "tl_lng": "55.2705",
        "tl_street": "Avenue de Bourbon",
        "tl_cp": "97434",
        "tl_ville": "Saint-Paul",
    })
    prefill = client.session.get("onboard_venue_prefill")
    assert prefill is not None
    assert prefill["adresse_recherche"] == adresse
    # Coordonnées validées et converties en float (cf. valider_coordonnees).
    # / Coordinates validated and converted to float.
    assert prefill["latitude"] == -21.0096
    assert prefill["longitude"] == 55.2705
    assert prefill["street_address"] == "Avenue de Bourbon"
    assert prefill["postal_code"] == "97434"
    assert prefill["address_locality"] == "Saint-Paul"


def test_venue_post_coordonnees_invalides_ignorees(cleanup_waiting_configs):
    """Mauvais input : des coordonnées non numériques (POST forgé) ne sont PAS
    stockées comme GPS. Le prefill garde l'adresse (repli Nominatim) avec
    latitude/longitude vides — pas de crash, pas de garbage en session."""
    client = Client(HTTP_HOST=DEV_HOST)
    _create_wc_at(WaitingConfiguration.STEP_VENUE, client, cleanup=cleanup_waiting_configs)
    suffixe = int(time.time() * 1000)
    resp = client.post("/onboard/venue/", data={
        "name": f"Lieu Bad {suffixe}",
        "slug": f"lieu-bad-{suffixe}",
        "dns_choice": "tibillet.coop",
        "tl_adresse": "Un lieu quelque part",
        "tl_lat": "<script>alert(1)</script>",
        "tl_lng": "pas-un-nombre",
    })
    assert resp.status_code in (302, 303)
    prefill = client.session.get("onboard_venue_prefill")
    assert prefill is not None
    assert prefill["latitude"] == ""
    assert prefill["longitude"] == ""
    assert prefill["adresse_recherche"] == "Un lieu quelque part"


def test_place_get_sans_prefill_se_rend_sans_erreur(cleanup_waiting_configs):
    """Régression : GET /onboard/place/ sans fiche Tiers-Lieux en session
    (lieu saisi à la main) doit renvoyer 200.

    Avant le fix, `03_place.html` levait `VariableDoesNotExist` : `prefill` était
    un dict vide et `valeur|default:prefill.latitude` ne tolère pas une clé
    absente quand elle est résolue comme ARGUMENT de filtre. La vue garantit
    désormais toutes les clés du prefill (vides → le widget bascule sur Nominatim)."""
    client = Client(HTTP_HOST=DEV_HOST)
    _create_wc_at(WaitingConfiguration.STEP_PLACE, client, cleanup=cleanup_waiting_configs)
    # Aucun onboard_venue_prefill en session (cas saisie manuelle).
    # / No onboard_venue_prefill in session (manual entry case).
    resp = client.get("/onboard/place/")
    assert resp.status_code == 200


def test_place_post_skip_advances_without_address(cleanup_waiting_configs):
    """Bouton « Je ne renseigne pas d'adresse » -> avance à descriptions sans adresse."""
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_wc_at(WaitingConfiguration.STEP_PLACE, client, cleanup=cleanup_waiting_configs)
    resp = client.post("/onboard/place/", data={"skip_address": "1"})
    assert resp.status_code in (302, 303)
    assert resp["Location"] == "/onboard/descriptions/"
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.current_step == WaitingConfiguration.STEP_DESCRIPTIONS
