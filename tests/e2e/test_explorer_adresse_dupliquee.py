"""
Tests E2E Playwright : carte explorer — deux lieux a la MEME adresse.
/ E2E Playwright tests: explorer map — two venues at the SAME address.

LOCALISATION : tests/e2e/test_explorer_adresse_dupliquee.py

Le bug corrige ici : quand deux lieux du reseau ont exactement les memes
coordonnees, Leaflet.markercluster garde leurs deux markers dans un cluster,
a TOUS les niveaux de zoom (le zoom ne peut pas separer deux points confondus).
Or `marker.openPopup()` ne fait RIEN sur un marker enferme dans un cluster :
il n'est pas sur la carte. Resultat : cliquer sur le lieu dans la liste
n'ouvrait aucun popup, et ses evenements semblaient avoir disparu.
La correction utilise `markerCluster.zoomToShowLayer()`, qui fait le spiderfy
puis rend la main (cf. explorer.js, montrerLeMarkerPuisOuvrirLePopup).
/ Fixed bug: two venues with identical coordinates stay clustered at every zoom
level, and openPopup() is a no-op on a clustered marker. Clicking the venue card
opened nothing. The fix uses zoomToShowLayer(), which spiderfies then calls back.

Ce test ne peut PAS etre un test pytest : il verifie du JavaScript (Leaflet,
markercluster, spiderfy). Il faut un vrai navigateur.
/ This cannot be a pytest test: it verifies JavaScript. A real browser is required.

PREREQUIS : le serveur tourne (byobu) et est joignable via Traefik.
"""

import json
import os
import shutil
import subprocess

import pytest
from playwright.sync_api import expect

# Domaine APEX (nu) : l'explorer ROOT vit sur l'apex, pas sur un sous-domaine tenant.
# / Bare (apex) domain: the ROOT explorer lives on the apex, not on a tenant subdomain.
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
EXPLORER_URL = f"https://{DOMAIN}/explorer/"

# Nom de l'adresse en double, cree puis supprime par la fixture.
# / Name of the duplicate address, created then removed by the fixture.
NOM_ADRESSE_DUPLIQUEE = "E2E — adresse dupliquee"

pytestmark = pytest.mark.e2e


def _lancer_dans_django(code_python):
    """
    Execute du code Python dans le conteneur Django, sur le schema public.
    / Run Python code inside the Django container, on the public schema.

    Meme pattern que tests/e2e/test_explorer_markers_per_pa.py : le test tourne
    soit depuis l'hote (docker exec), soit deja dans le conteneur.
    / Same pattern as test_explorer_markers_per_pa.py: the test runs either from
    the host (docker exec) or already inside the container.
    """
    on_est_dans_le_conteneur = shutil.which("docker") is None

    if on_est_dans_le_conteneur:
        cmd = [
            "python", "/DjangoFiles/manage.py",
            "tenant_command", "shell", "-s", "public", "-c", code_python,
        ]
        env = {**os.environ, "TEST": "1", "PYTHONPATH": "/DjangoFiles"}
        cwd = "/DjangoFiles"
    else:
        cmd = [
            "docker", "exec", "-e", "TEST=1", "lespass_django",
            "poetry", "run", "python", "manage.py",
            "tenant_command", "shell", "-s", "public", "-c", code_python,
        ]
        env = None
        cwd = None

    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=120, env=env, cwd=cwd,
    )


@pytest.fixture(scope="module")
def deux_lieux_a_la_meme_adresse():
    """
    Donne au tenant 'lespass' une adresse aux coordonnees EXACTES de l'adresse
    principale de 'festival', puis reconstruit le cache SEO.
    / Give the 'lespass' tenant an address with the EXACT coordinates of
    'festival' main address, then rebuild the SEO cache.

    Rend le nom du lieu federe et le nom d'un de ses evenements : le test verifie
    que ce nom apparait bien dans le popup, malgre les coordonnees confondues.
    / Yields the federated venue name and one of its event names.

    Nettoyage : l'adresse est supprimee et le cache reconstruit, pour ne pas
    laisser de donnee de test dans la base de dev.
    / Cleanup: the address is removed and the cache rebuilt.
    """
    code_de_preparation = f"""
import json
from Customers.models import Client
from django_tenants.utils import tenant_context
from BaseBillet.models import PostalAddress, Configuration, Event
from django.utils import timezone
from seo.tasks import refresh_seo_cache

lieu_federe = Client.objects.get(schema_name="festival")
lieu_de_la_carte = Client.objects.get(schema_name="lespass")

with tenant_context(lieu_federe):
    config = Configuration.get_solo()
    adresse_principale = config.postal_address
    nom_du_lieu_federe = config.organisation
    premier_event = (
        Event.objects.filter(
            published=True, archived=False, private=False,
            datetime__gte=timezone.now(),
            postal_address=adresse_principale,
        )
        .order_by("datetime")
        .first()
    )
    latitude = adresse_principale.latitude
    longitude = adresse_principale.longitude
    nom_du_premier_event = premier_event.name if premier_event else ""

with tenant_context(lieu_de_la_carte):
    PostalAddress.objects.get_or_create(
        name="{NOM_ADRESSE_DUPLIQUEE}",
        defaults=dict(
            street_address="", postal_code="", address_locality="",
            address_country="", latitude=latitude, longitude=longitude,
        ),
    )

refresh_seo_cache()
print("RESULTAT_JSON=" + json.dumps({{
    "nom_du_lieu_federe": nom_du_lieu_federe,
    "nom_du_premier_event": nom_du_premier_event,
}}))
"""
    resultat = _lancer_dans_django(code_de_preparation)
    if resultat.returncode != 0:
        pytest.fail(
            "Preparation impossible : le conteneur Django n'a pas repondu. "
            "Un environnement casse doit rendre le test ROUGE, pas le faire "
            "disparaitre du rapport.\n"
            f"Stderr : {resultat.stderr[:300]}"
        )

    ligne_resultat = [
        ligne for ligne in resultat.stdout.splitlines()
        if ligne.startswith("RESULTAT_JSON=")
    ]
    if not ligne_resultat:
        pytest.fail(
            "Preparation : le conteneur n'a renvoye aucun RESULTAT_JSON. "
            f"Sortie brute : {resultat.stdout[-300:]}"
        )

    donnees = json.loads(ligne_resultat[0].removeprefix("RESULTAT_JSON="))
    if not donnees["nom_du_premier_event"]:
        pytest.fail(
            "Le lieu federe 'festival' n'a aucun evenement futur a son adresse "
            "principale : le popup n'a rien a afficher, le test ne prouve rien. "
            "Reseeder : docker exec lespass_django poetry run python "
            "manage.py demo_data_v2"
        )

    yield donnees

    code_de_nettoyage = f"""
from Customers.models import Client
from django_tenants.utils import tenant_context
from BaseBillet.models import PostalAddress
from seo.tasks import refresh_seo_cache

with tenant_context(Client.objects.get(schema_name="lespass")):
    PostalAddress.objects.filter(name="{NOM_ADRESSE_DUPLIQUEE}").delete()
refresh_seo_cache()
"""
    _lancer_dans_django(code_de_nettoyage)


def test_deux_lieux_a_la_meme_adresse_produisent_deux_points_distincts(
    page, deux_lieux_a_la_meme_adresse
):
    """
    Les deux adresses confondues restent DEUX points, chacun avec ses evenements.
    / The two identical addresses stay TWO points, each keeping its own events.

    C'est la question posee par le bug remonte : « la meme adresse existe dans les
    deux lieux, est-ce que ca ferait conflit ? ». Non : pa_id est prefixe par
    l'UUID du tenant, donc aucun ecrasement cote donnees.
    / No collision: pa_id is prefixed with the tenant UUID.
    """
    page.goto(EXPLORER_URL)
    page.wait_for_load_state("networkidle")

    donnees_de_la_carte = json.loads(page.locator("#explorer-data").text_content())
    points = donnees_de_la_carte["points"]

    # Regroupe les points par coordonnees pour trouver le couple confondu.
    # / Group points by coordinates to find the overlapping pair.
    points_par_coordonnees = {}
    for point in points:
        cle = (point["latitude"], point["longitude"])
        points_par_coordonnees.setdefault(cle, []).append(point)

    couples_confondus = [
        liste for liste in points_par_coordonnees.values() if len(liste) >= 2
    ]
    assert couples_confondus, (
        "Aucun couple de points aux memes coordonnees : la fixture n'a pas produit "
        "l'adresse dupliquee attendue."
    )

    # Les deux points ont bien des pa_id distincts (prefixes par tenant).
    # / The two points do have distinct pa_ids (tenant-prefixed).
    for liste_de_points in couples_confondus:
        identifiants = {point["pa_id"] for point in liste_de_points}
        assert len(identifiants) == len(liste_de_points), (
            f"Deux points partagent le meme pa_id : {identifiants}"
        )


def test_clic_sur_un_lieu_a_adresse_dupliquee_ouvre_son_popup_avec_ses_events(
    page, deux_lieux_a_la_meme_adresse
):
    """
    Cliquer sur la carte d'un lieu dont l'adresse est dupliquee ouvre SON popup,
    et ce popup liste SES evenements.
    / Clicking the card of a venue whose address is duplicated opens ITS popup,
    listing ITS events.

    Sans le correctif, le marker reste enferme dans le cluster, openPopup() ne fait
    rien, et aucun popup n'apparait : le test echoue sur le wait_for_selector.
    / Without the fix, the marker stays clustered, openPopup() is a no-op, and no
    popup ever appears.
    """
    nom_du_lieu_federe = deux_lieux_a_la_meme_adresse["nom_du_lieu_federe"]
    nom_du_premier_event = deux_lieux_a_la_meme_adresse["nom_du_premier_event"]

    page.goto(EXPLORER_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".leaflet-marker-icon, .leaflet-marker-cluster", timeout=8_000)

    # Clic sur la carte du lieu federe dans la liste (declenche focusOnLieu).
    # / Click the federated venue card in the list (triggers focusOnLieu).
    carte_du_lieu = page.locator(
        ".explorer-card--lieu", has_text=nom_du_lieu_federe
    ).first
    expect(carte_du_lieu).to_be_visible()
    carte_du_lieu.click()

    # Le popup doit s'ouvrir : c'est exactement ce qui ne se produisait plus.
    # / The popup must open: exactly what stopped happening.
    popup = page.locator(".leaflet-popup")
    expect(popup).to_be_visible(timeout=8_000)

    # Et il porte le bon lieu, avec ses evenements — pas ceux du lieu voisin.
    # / And it carries the right venue, with its own events.
    expect(popup).to_contain_text(nom_du_lieu_federe)
    expect(popup).to_contain_text(nom_du_premier_event)
