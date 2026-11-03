"""
Tests E2E Playwright : bloc de page « Carte figée » (lieux et événements importés en JSON).
/ E2E Playwright tests: "frozen map" page block (venues and events imported as JSON).

LOCALISATION : tests/e2e/test_bloc_carte_figee.py
Voir TECH_DOC/SESSIONS/PAGES/CHANTIER-08-carte-figee.md.

Le bloc réutilise l'outil de carte de la page « Autour de nous »
(seo/static/seo/explorer.js). Ces tests vérifient, dans un vrai navigateur :
- la liste des lieux et le compteur ;
- l'accordéon des événements d'un lieu, avec les liens venus du fichier ;
- la vue « Événements » ;
- la popup d'un marqueur, avec le libellé « Événements : ».
/ The block reuses the network map tool. These tests check, in a real browser,
the venue list, the events accordion with file links, the events view and the
marker popup.

Pattern conftest : pas de live_server. Le serveur tourne dans byobu, derrière
Traefik. La page et le bloc sont créés par django_shell, puis supprimés.
/ No live_server: the server runs behind Traefik. Page and block are created
with django_shell, then deleted.
"""

import json
import os

import pytest
from playwright.sync_api import expect

DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
SLUG_DE_LA_PAGE = "e2e-carte-figee"
URL_DE_LA_PAGE = f"https://lespass.{DOMAIN}/{SLUG_DE_LA_PAGE}/"

pytestmark = [pytest.mark.e2e, pytest.mark.explorer]

# Deux lieux : un avec deux événements et des liens, un sans rien.
# / Two venues: one with two events and links, one with nothing.
LIEUX_DU_FICHIER = [
    {
        "nom": "La Cité du Faire E2E",
        "latitude": 45.7578,
        "longitude": 4.8320,
        "adresse": "12 rue de l'Exemple, 69003 Lyon",
        "url": "https://lacitedufaire.example.org/",
        "evenements": [
            {
                "nom": "Visite guidée E2E",
                "date": "2026-10-02T14:00",
                "url": "https://lacitedufaire.example.org/visite/",
                "tags": ["JPTO"],
            },
            {"nom": "Atelier ouvert E2E", "date": "2026-10-03", "tags": ["JPTO"]},
        ],
    },
    {"nom": "Tiers-lieu sans lien E2E", "latitude": 48.5734, "longitude": 7.7521},
]


@pytest.fixture
def page_avec_carte_figee(django_shell):
    """
    Crée une page publiée avec un bloc CARTE_FIGEE, puis la supprime.
    / Creates a published page with a CARTE_FIGEE block, then deletes it.

    Le bloc passe par full_clean() : les données sont vérifiées comme à
    l'import dans l'admin. / The block goes through full_clean().
    """
    code_de_creation = f"""
import json
from pages.models import Bloc, Page
Page.objects.filter(slug="{SLUG_DE_LA_PAGE}").delete()
page = Page.objects.create(titre="E2E carte figée", slug="{SLUG_DE_LA_PAGE}", publie=True, affichage_nav="")
bloc = Bloc(page=page, type_bloc=Bloc.CARTE_FIGEE, titre="Bilan E2E",
            donnees_carte_figee=json.loads({json.dumps(json.dumps(LIEUX_DU_FICHIER))}))
bloc.full_clean(exclude=["uuid"])
bloc.save()
print(page.pk)
"""
    django_shell(code_de_creation)
    yield URL_DE_LA_PAGE
    django_shell(
        f'from pages.models import Page; Page.objects.filter(slug="{SLUG_DE_LA_PAGE}").delete()'
    )


def test_la_liste_montre_les_lieux_du_fichier(page, page_avec_carte_figee):
    page.goto(page_avec_carte_figee)

    bloc = page.locator('[data-testid="bloc-carte-figee"]')
    expect(bloc).to_be_visible()
    expect(page.locator(".explorer-card--lieu")).to_have_count(2)
    expect(page.locator("#explorer-counter")).to_contain_text("2 lieux")
    # La ligne « 📍 » de la carte de la liste porte l'adresse du fichier.
    # / The list card's "📍" line carries the file address.
    expect(page.locator(".explorer-card--lieu").first).to_contain_text("69003 Lyon")


def test_l_accordeon_d_un_lieu_montre_ses_evenements_avec_leurs_liens(
    page, page_avec_carte_figee
):
    page.goto(page_avec_carte_figee)

    carte_du_lieu = page.locator(
        ".explorer-card--lieu", has_text="La Cité du Faire E2E"
    )
    carte_du_lieu.locator(".explorer-accordion-toggle").click()

    lien_de_la_visite = carte_du_lieu.locator(
        ".explorer-accordion-item", has_text="Visite guidée E2E"
    )
    expect(lien_de_la_visite).to_have_attribute(
        "href", "https://lacitedufaire.example.org/visite/"
    )
    expect(carte_du_lieu.locator(".explorer-card-link")).to_have_attribute(
        "href", "https://lacitedufaire.example.org/"
    )


def test_un_lieu_sans_url_n_a_pas_de_bouton_visiter(page, page_avec_carte_figee):
    page.goto(page_avec_carte_figee)

    carte_sans_lien = page.locator(
        ".explorer-card--lieu", has_text="Tiers-lieu sans lien E2E"
    )
    expect(carte_sans_lien).to_be_visible()
    expect(carte_sans_lien.locator(".explorer-card-link")).to_have_count(0)


def test_la_vue_evenements_liste_les_evenements_du_fichier(page, page_avec_carte_figee):
    page.goto(page_avec_carte_figee)

    page.locator('[data-testid="explorer-pill-event"]').click()

    expect(page.locator(".explorer-card--event")).to_have_count(2)
    titre_de_la_visite = page.locator(
        ".explorer-card--event h3 a", has_text="Visite guidée E2E"
    )
    expect(titre_de_la_visite).to_have_attribute(
        "href", "https://lacitedufaire.example.org/visite/"
    )


def test_la_popup_d_un_lieu_titre_ses_evenements_sans_parler_d_avenir(
    page, page_avec_carte_figee
):
    page.goto(page_avec_carte_figee)

    carte_du_lieu = page.locator(
        ".explorer-card--lieu", has_text="La Cité du Faire E2E"
    )
    carte_du_lieu.locator(".explorer-card-focus").click()

    popup = page.locator(".leaflet-popup-content")
    expect(popup).to_contain_text("Événements : (2)")
    expect(popup).not_to_contain_text("Prochains")


def test_un_evenement_sans_url_n_est_pas_un_lien_vers_la_page(
    page, page_avec_carte_figee
):
    """Pas de href="#" target="_blank" : il rouvrirait la page dans un onglet."""
    page.goto(page_avec_carte_figee)

    carte_du_lieu = page.locator(
        ".explorer-card--lieu", has_text="La Cité du Faire E2E"
    )
    carte_du_lieu.locator(".explorer-accordion-toggle").click()

    ligne_de_l_atelier = carte_du_lieu.locator(
        ".explorer-accordion-item", has_text="Atelier ouvert E2E"
    )
    expect(ligne_de_l_atelier).to_be_visible()
    expect(ligne_de_l_atelier).not_to_have_attribute("href", "#")
    assert ligne_de_l_atelier.evaluate("element => element.tagName") == "SPAN"


# ============================================================
# Defense du JS : un guillemet dans une URL ne casse pas l'attribut
# / JS defense: a quote in a URL does not break the attribute
# ============================================================
SLUG_DE_LA_PAGE_PIEGEE = "e2e-carte-figee-piegee"
URL_PIEGEE = 'https://x.example.org/" data-pirate="1'


@pytest.fixture
def page_avec_url_piegee(django_shell):
    """
    Pose en base une URL piegee SANS passer par la verification (save() sans
    full_clean()). Le serveur la refuse a l'import ; on teste ici la deuxieme
    barriere : escapeHtml (explorer.js) doit echapper le guillemet.
    / Stores a trapped URL bypassing validation, to test the second barrier:
    escapeHtml must escape the quote.
    """
    lieux = [
        {
            "nom": "Lieu piégé E2E",
            "latitude": 45.75,
            "longitude": 4.83,
            "url": URL_PIEGEE,
            "evenements": [{"nom": "Événement piégé E2E", "url": URL_PIEGEE}],
        }
    ]
    code_de_creation = f"""
import json
from pages.models import Bloc, Page
Page.objects.filter(slug="{SLUG_DE_LA_PAGE_PIEGEE}").delete()
page = Page.objects.create(titre="E2E carte piégée", slug="{SLUG_DE_LA_PAGE_PIEGEE}", publie=True, affichage_nav="")
Bloc.objects.create(page=page, type_bloc=Bloc.CARTE_FIGEE,
                    donnees_carte_figee=json.loads({json.dumps(json.dumps(lieux))}))
"""
    django_shell(code_de_creation)
    yield f"https://lespass.{DOMAIN}/{SLUG_DE_LA_PAGE_PIEGEE}/"
    django_shell(
        f'from pages.models import Page; Page.objects.filter(slug="{SLUG_DE_LA_PAGE_PIEGEE}").delete()'
    )


def test_un_guillemet_dans_une_url_n_ajoute_aucun_attribut(page, page_avec_url_piegee):
    page.goto(page_avec_url_piegee)

    carte_du_lieu = page.locator(".explorer-card--lieu", has_text="Lieu piégé E2E")
    carte_du_lieu.locator(".explorer-accordion-toggle").click()
    carte_du_lieu.locator(".explorer-card-focus").click()
    page.locator('[data-testid="explorer-pill-event"]').click()
    page.locator('[data-testid="explorer-pill-lieu"]').click()

    # Aucun element de la page ne porte l'attribut injecte.
    # / No element of the page carries the injected attribute.
    expect(page.locator("[data-pirate]")).to_have_count(0)
    # Le lien garde l'URL entiere, guillemet compris, comme simple texte d'attribut.
    # / The link keeps the whole URL, quote included, as plain attribute text.
    lien_visiter = carte_du_lieu.locator(".explorer-card-link")
    expect(lien_visiter).to_have_attribute("href", URL_PIEGEE)
