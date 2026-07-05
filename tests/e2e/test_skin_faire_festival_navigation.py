"""
Tests E2E : navigation HTMX sous le skin faire_festival (tenant chantefrein).
/ E2E tests: HTMX navigation under the faire_festival skin (chantefrein tenant).

LOCALISATION : tests/e2e/test_skin_faire_festival_navigation.py

POURQUOI CE TEST : le skin faire_festival etait un angle mort total des suites
(aucun test E2E ne le naviguait). Deux bugs y ont ete trouves en revue manuelle
(2026-07-05) : les panneaux #contactPanel/#loginPanel absents du fragment
headless (boutons morts apres un swap), et les vues qui renvoyaient le document
COMPLET aux requetes HTMX. Ce test verrouille les deux comportements.
/ WHY: the faire_festival skin was a blind spot of the test suites (no E2E
navigated it). Two bugs were found there by manual review: the global offcanvas
panels missing from the headless fragment (dead buttons after a swap), and the
views returning the FULL document to HTMX requests. This test locks both.

Flow :
1. Chargement complet de /event/ sur chantefrein (skin faire_festival).
2. Clic navbar « Adhesions » (hx-get, hx-target=body) -> swap HTMX reel.
3. Verifie : URL poussee, skin toujours applique, UNE seule navbar,
   pas de document imbrique (le fragment headless a bien ete servi).
4. Ouvre le panneau contact puis le panneau connexion (les ids du contrat
   doivent exister DANS le fragment) -> les deux s'affichent.
"""

import os

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
URL_CHANTEFREIN = f"https://chantefrein.{DOMAIN}"


def test_navigation_htmx_skin_faire_festival_et_panneaux(page):
    """Navigation HTMX sous skin ff : fragment headless + panneaux du contrat."""
    # 1. Chargement complet de l'agenda (squelette shell.html).
    # / Full load of the agenda page (shell.html skeleton).
    page.goto(f"{URL_CHANTEFREIN}/event/")
    expect(page.locator(".skin-faire-festival").first).to_be_visible()

    # 2. Clic sur le lien navbar « Adhesions » : c'est un hx-get avec
    # hx-target="body" -> reponse via headless.html (fragment).
    # / Click the "Memberships" navbar link: hx-get with hx-target="body".
    lien_adhesions = page.locator('a[hx-get="/memberships/"]').first
    lien_adhesions.click()
    page.wait_for_url(lambda url: "/memberships/" in url)

    # 3. Apres le swap : le skin est toujours la, une SEULE navbar, et aucun
    # document complet imbrique dans le body (preuve que le fragment headless
    # a ete servi, pas le document shell entier).
    # / After the swap: skin still applied, ONE navbar, and no nested full
    # document inside the body (proof the headless fragment was served).
    expect(page.locator(".skin-faire-festival").first).to_be_visible()
    nombre_de_navbars = page.locator("nav").count()
    assert nombre_de_navbars == 1, f"navbar dupliquee apres swap ({nombre_de_navbars})"
    document_imbrique = page.evaluate("!!document.body.querySelector('html, head')")
    assert document_imbrique is False, "document complet imbrique dans le body"

    # 4. Les panneaux globaux du contrat existent DANS le fragment et
    # s'ouvrent (bug historique : absents du headless ff -> boutons morts).
    # / The contract's global panels exist IN the fragment and open
    # (historical bug: missing from the ff headless -> dead buttons).
    page.locator('[data-bs-target="#contactPanel"]').first.click()
    expect(page.locator("#contactPanel")).to_be_visible()
    # Fermeture par le bouton de fermeture du panneau — PAS par la touche
    # Echap : Bootstrap n'ecoute Echap qu'une fois la transition finie et le
    # focus piege dans le panneau (verifie dans Chrome : Echap trop tot, avant
    # la fin du "showing", est ignore -> test flaky). Le clic sur le bouton
    # auto-attend la stabilite de l'element (Playwright actionability).
    # / Close via the panel's close button — NOT the Escape key: Bootstrap only
    # listens for Escape once the transition is done and focus is trapped
    # (verified in Chrome: an early Escape during "showing" is ignored ->
    # flaky test). Clicking the button auto-waits for element stability.
    page.locator('#contactPanel [data-bs-dismiss="offcanvas"]').first.click()
    expect(page.locator("#contactPanel")).not_to_be_visible()

    page.locator('[data-bs-target="#loginPanel"]').first.click()
    expect(page.locator("#loginPanel")).to_be_visible()
