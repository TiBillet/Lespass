"""
Tests E2E : mode focus monnaie sur la page /explorer/.
/ E2E tests: currency focus mode on /explorer/ page.

Scenarios testes :
- Clic sur la card "Fédéré TiBillet" → polygone hull sur la carte + legende visible
- Clic a nouveau sur la meme card → reset (toggle)
- Clic sur un badge monnaie d'une card lieu → meme effet
"""

import os
import re
import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e

DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
EXPLORER_URL = f"https://www.{DOMAIN}/explorer/"


def test_click_tibillet_asset_card_draws_hull_polygon(page):
    """
    Clic sur la card asset "TiBillet" dans la liste :
    - La card devient active (classe CSS explorer-card--active)
    - La legende apparait avec le nom de la monnaie
    - Un polygone SVG est dessine sur la carte (layer Leaflet)
    / Click on a "TiBillet" asset card:
    - Card becomes active (CSS class explorer-card--active)
    - Legend appears with currency name
    - SVG polygon drawn on map (Leaflet layer)
    """
    page.goto(EXPLORER_URL)
    page.wait_for_load_state("networkidle")

    # Clic sur le pill "Monnaies" pour filtrer la liste.
    # / Click on "Monnaies" pill to filter the list.
    monnaies_pill = page.get_by_role("button", name="Monnaies")
    monnaies_pill.click()

    # Clic sur la premiere card asset contenant "TiBillet".
    # / Click on the first asset card containing "TiBillet".
    tibillet_card = (
        page.locator('.explorer-card[data-type="asset"]')
        .filter(has_text="TiBillet")
        .first
    )
    expect(tibillet_card).to_be_visible(timeout=5_000)
    tibillet_card.click()

    # Verifier que la card est marquee active via la classe CSS.
    # to_have_class verifie la valeur complete de l'attribut class :
    # on utilise une regex qui matche si la classe est presente.
    # / Verify the card has the active CSS class.
    # to_have_class checks the full class attribute value :
    # we use a regex that matches if the class is present.
    expect(tibillet_card).to_have_class(
        re.compile(r"explorer-card--active"), timeout=3_000
    )

    # La legende doit apparaitre avec le nom de la monnaie.
    # / Legend must appear with the currency name.
    legend = page.locator("#explorer-asset-legend")
    expect(legend).to_be_visible(timeout=3_000)
    expect(legend).to_contain_text("TiBillet")

    # Un polygone SVG est dessine (Leaflet ajoute un <path> dans overlay-pane).
    # / A SVG polygon is drawn (Leaflet adds a <path> in overlay-pane).
    svg_paths = page.locator(".leaflet-overlay-pane svg path")
    expect(svg_paths.first).to_be_visible(timeout=3_000)


def test_click_active_asset_card_clears_focus(page):
    """
    Clic a nouveau sur la meme card asset active = reset du mode focus.
    / Click again on the same active asset card = reset focus mode.
    """
    page.goto(EXPLORER_URL)
    page.wait_for_load_state("networkidle")

    page.get_by_role("button", name="Monnaies").click()

    tibillet_card = (
        page.locator('.explorer-card[data-type="asset"]')
        .filter(has_text="TiBillet")
        .first
    )
    tibillet_card.click()
    expect(tibillet_card).to_have_class(
        re.compile(r"explorer-card--active"), timeout=3_000
    )

    # Clic a nouveau = toggle off.
    # / Click again = toggle off.
    tibillet_card.click()
    expect(tibillet_card).not_to_have_class(
        re.compile(r"explorer-card--active"), timeout=3_000
    )
    expect(page.locator("#explorer-asset-legend")).to_be_hidden(timeout=3_000)


def test_click_asset_badge_on_lieu_card_triggers_focus(page):
    """
    Clic sur un badge monnaie d'une card lieu declenche le meme focus.
    / Click on an asset badge of a lieu card triggers same focus.
    """
    page.goto(EXPLORER_URL)
    page.wait_for_load_state("networkidle")

    # S'assurer qu'on est en mode "Tous" pour voir les lieux et leurs badges.
    # Le pill "Tous" est actif par defaut ; on le cible avec son selecteur CSS
    # pour eviter le conflit avec les cards d'initiative qui ont aussi role="button".
    # / Make sure we're on "Tous" to see lieux and their badges.
    # "Tous" pill is active by default; use CSS selector to avoid conflict
    # with initiative cards that also have role="button".
    page.locator("button.explorer-pill[data-category='all']").click()

    # Trouver le premier badge monnaie sur une card lieu.
    # / Find the first asset badge on a lieu card.
    badge = page.locator(".lieu-asset-badge").first
    expect(badge).to_be_visible(timeout=5_000)
    badge.click()

    # La legende doit apparaitre.
    # / Legend must appear.
    expect(page.locator("#explorer-asset-legend")).to_be_visible(timeout=3_000)
