"""
Tests E2E Playwright : page /explorer/ (ROOT) — pills exclusives, tag chips, URL.
/ E2E Playwright tests: ROOT /explorer/ page — exclusive pills, tag chips, URL.

LOCALISATION : tests/e2e/test_explorer_ux_pills_tags.py
Voir TECH_DOC/SESSIONS/SEO/CHANTIER-06-explorer-ux-pills-tags.md.

Pattern conftest : pas de live_server Django. Le serveur tourne dans byobu
et est accessible via Traefik. L'URL est construite depuis l'env DOMAIN
(défaut : tibillet.localhost). Chromium contourne la résolution DNS localhost
via --host-resolver-rules (défini dans conftest.py).
/ conftest pattern: no Django live_server. Server runs in byobu, accessible
via Traefik. URL built from DOMAIN env var (default: tibillet.localhost).
Chromium bypasses localhost DNS resolution via --host-resolver-rules (set
in conftest.py).
"""

import os

import pytest
from playwright.sync_api import expect


# URL de base de l'explorer (ROOT, pas un tenant).
# / Base URL of the explorer (ROOT, not a tenant).
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
EXPLORER_URL = f"https://www.{DOMAIN}/explorer/"

pytestmark = pytest.mark.e2e


# ============================================================
# FIXTURE — refresh SEO cache before tests
# ============================================================


@pytest.fixture(autouse=True, scope="module")
def refresh_cache():
    """
    Rafraichit le cache SEO une fois avant tous les tests du module.
    Garantit que les events + tags sont a jour dans SEOCache.
    / Refresh the SEO cache once before all tests in this module.
    Ensures events + tags are up-to-date in SEOCache.

    Scope "module" : un seul appel au lieu d'un par test.
    / Scope "module": a single call instead of one per test.

    Execution via subprocess docker (meme pattern que les fixtures api_key et
    e2e_slugs dans conftest.py) — fonctionne depuis le host ET depuis le container.
    / Execution via docker subprocess (same pattern as api_key and e2e_slugs
    fixtures in conftest.py) — works from host AND from inside the container.

    Si le refresh echoue (serveur absent, CI sans docker), on logge et on continue.
    Les tests utiliseront le cache existant ou afficheront un SKIP adequat.
    / If refresh fails (server absent, CI without docker), log and continue.
    Tests will use existing cache or show an adequate SKIP.
    """
    import subprocess
    import shutil

    inside_container = shutil.which("docker") is None

    if inside_container:
        cmd = [
            "python", "/DjangoFiles/manage.py",
            "tenant_command", "shell", "-s", "public", "-c",
            "from seo.tasks import refresh_seo_cache; refresh_seo_cache()",
        ]
        env = {**os.environ, "TEST": "1", "PYTHONPATH": "/DjangoFiles"}
        cwd = "/DjangoFiles"
    else:
        cmd = [
            "docker", "exec", "-e", "TEST=1",
            "lespass_django", "poetry", "run", "python",
            "manage.py",
            "tenant_command", "shell", "-s", "public", "-c",
            "from seo.tasks import refresh_seo_cache; refresh_seo_cache()",
        ]
        env = None
        cwd = None

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=60,
        env=env, cwd=cwd,
    )
    if result.returncode != 0:
        import warnings
        warnings.warn(
            f"refresh_seo_cache a echoue (rc={result.returncode}). "
            f"Les tests utiliseront le cache existant. "
            f"Stderr : {result.stderr[:200]}",
            stacklevel=2,
        )


# ============================================================
# HELPERS
# ============================================================


def goto_explorer(page, params=""):
    """
    Navigue vers l'explorer et attend que les cards soient presentes.
    / Navigate to explorer and wait for cards to appear.
    """
    url = EXPLORER_URL + (params if params else "")
    page.goto(url)
    # Attendre le conteneur de liste — toujours present meme vide.
    # / Wait for the list container — always present even if empty.
    page.wait_for_selector("#explorer-list", timeout=10_000)
    # La liste peut etre vide (aucun lieu/event en dev) ; on attend
    # networkidle pour laisser le JS s'initialiser completement.
    # / List may be empty (no venue/event in dev); wait for networkidle
    # to let JS fully initialize.
    page.wait_for_load_state("networkidle")


# ============================================================
# TESTS
# ============================================================


def test_pill_lieux_active_par_defaut(page):
    """
    Au chargement de /explorer/, la pill "Lieux" est active par defaut
    et la pill "Evenements" ne l'est pas.
    / On /explorer/ load, the "Lieux" pill is active by default
    and the "Evenements" pill is not.
    """
    goto_explorer(page)

    pill_lieu = page.locator('[data-testid="explorer-pill-lieu"]')
    pill_event = page.locator('[data-testid="explorer-pill-event"]')

    expect(pill_lieu).to_be_visible(timeout=5_000)
    expect(pill_event).to_be_visible(timeout=5_000)

    # Pill Lieux active / Lieux pill is active
    lieu_classes = pill_lieu.get_attribute("class") or ""
    assert "active" in lieu_classes, (
        f"Pill Lieux devrait etre active au chargement. Classes : {lieu_classes}"
    )

    # Pill Evenements inactive / Evenements pill is not active
    event_classes = pill_event.get_attribute("class") or ""
    assert "active" not in event_classes, (
        f"Pill Evenements ne devrait pas etre active au chargement. Classes : {event_classes}"
    )


def test_pill_evenements_exclusif_avec_pill_lieux(page):
    """
    Clic sur la pill Evenements desactive la pill Lieux (exclusive toggle).
    / Click on Evenements pill deactivates the Lieux pill (exclusive toggle).
    """
    goto_explorer(page)

    pill_lieu = page.locator('[data-testid="explorer-pill-lieu"]')
    pill_event = page.locator('[data-testid="explorer-pill-event"]')

    expect(pill_event).to_be_visible(timeout=5_000)
    pill_event.click()

    # Attendre que le JS applique les filtres (synchrone, mais renderList
    # peut etre lent sur grosses donnees → 500ms de marge).
    # / Wait for JS to apply filters (synchronous, but renderList
    # may be slow on large data → 500ms margin).
    page.wait_for_timeout(500)

    event_classes_apres = pill_event.get_attribute("class") or ""
    lieu_classes_apres = pill_lieu.get_attribute("class") or ""

    assert "active" in event_classes_apres, (
        f"Pill Evenements devrait etre active apres clic. Classes : {event_classes_apres}"
    )
    assert "active" not in lieu_classes_apres, (
        f"Pill Lieux devrait etre inactive apres clic sur Evenements. Classes : {lieu_classes_apres}"
    )


def test_clic_pill_event_affiche_cards_event(page):
    """
    Clic sur la pill Evenements affiche des cards event (data-type="event")
    et plus de cards lieu (data-type="lieu") — si la base de test contient
    des events futurs publies.
    / Clicking Evenements pill shows event cards (data-type="event")
    and no lieu cards (data-type="lieu") — if the test DB has published future events.
    """
    goto_explorer(page)
    page.wait_for_selector('[data-testid="explorer-pill-event"]', timeout=5_000)
    page.locator('[data-testid="explorer-pill-event"]').click()
    page.wait_for_timeout(500)

    # Si aucun event futur publie : les 2 listes sont vides. On SKIP
    # sans erreur (pas un bug, juste la base de test vide).
    # / If no published future event: both lists are empty. SKIP
    # without error (not a bug, just an empty test DB).
    cards_event = page.locator('[data-type="event"]')
    cards_lieu = page.locator('[data-type="lieu"]')

    nb_lieu = cards_lieu.count()
    nb_event = cards_event.count()

    if nb_event == 0 and nb_lieu == 0:
        pytest.skip(
            "Aucun event futur publie dans la base de test — "
            "seeder demo_data_v2 pour avoir des events."
        )

    assert nb_lieu == 0, (
        f"Des cards lieu persistent en mode Evenements ({nb_lieu} trouvees)"
    )
    assert nb_event > 0, "Aucune card event affichee en mode Evenements"


def test_url_v_event_preselectionne_pill_evenements(page):
    """
    Naviguer vers /explorer/?v=event pre-selectionne la pill Evenements.
    / Navigating to /explorer/?v=event pre-selects the Evenements pill.
    """
    goto_explorer(page, "?v=event")

    pill_event = page.locator('[data-testid="explorer-pill-event"]')
    expect(pill_event).to_be_visible(timeout=5_000)

    event_classes = pill_event.get_attribute("class") or ""
    assert "active" in event_classes, (
        f"Pill Evenements pas pre-selectionnee avec ?v=event. Classes : {event_classes}"
    )


def test_clic_tag_chip_ajoute_tag_dans_url(page):
    """
    Clic sur un tag chip ajoute ?tag=<slug> dans l'URL.
    / Clicking a tag chip adds ?tag=<slug> to the URL.

    SKIP si aucun chip n'est affiche (pas d'events tagges dans la base de test).
    / SKIP if no chip is displayed (no tagged events in the test DB).
    """
    goto_explorer(page)
    page.wait_for_timeout(300)  # laisser updateChips() s'executer / let updateChips() run

    chips = page.locator(".explorer-tag-chip")
    if chips.count() == 0:
        pytest.skip(
            "Aucun tag chip affiche — pas d'events tagges dans la base de test. "
            "Seeder demo_data_v2 pour avoir des events avec tags."
        )

    chip = chips.first
    slug = chip.get_attribute("data-tag-slug")
    assert slug, "Chip sans data-tag-slug"

    chip.click()
    # Attendre le debounce syncURL (300ms) + marge / Wait for syncURL debounce (300ms) + margin
    page.wait_for_timeout(500)

    assert f"tag={slug}" in page.url, (
        f"URL ne contient pas tag={slug} apres clic sur chip. URL actuelle : {page.url}"
    )


def test_clic_tag_chip_marque_chip_actif(page):
    """
    Clic sur un tag chip applique la classe explorer-tag-chip--active sur ce chip.
    / Clicking a tag chip applies the explorer-tag-chip--active class to that chip.

    SKIP si aucun chip n'est affiche.
    / SKIP if no chip is displayed.
    """
    goto_explorer(page)
    page.wait_for_timeout(300)

    chips = page.locator(".explorer-tag-chip")
    if chips.count() == 0:
        pytest.skip("Aucun tag chip affiche — pas d'events tagges.")

    chip = chips.first
    chip.click()
    page.wait_for_timeout(500)

    # Relire le chip depuis le DOM — updateChips() le rerender.
    # / Re-read the chip from DOM — updateChips() re-renders it.
    chip_rerendu = page.locator(".explorer-tag-chip--active").first
    assert chip_rerendu.count() > 0, (
        "Aucun chip n'a la classe explorer-tag-chip--active apres le clic"
    )


def test_tag_inexistant_affiche_empty_state_avec_bouton_effacer(page):
    """
    Un tag inexistant dans l'URL filtre la liste a zero et affiche l'empty
    state avec un bouton "Effacer le filtre".
    / A non-existent tag in the URL filters the list to zero and shows the
    empty state with a "Clear filter" button.
    """
    goto_explorer(page, "?v=event&tag=ce-tag-nexiste-pas-12345")

    # Attendre l'empty state / Wait for empty state
    empty = page.locator('[data-testid="explorer-empty-state"]')
    expect(empty).to_be_visible(timeout=5_000)

    # Le bouton "Effacer le filtre" est present / "Clear filter" button is present
    clear_btn = page.locator('[data-testid="explorer-clear-tag"]')
    expect(clear_btn).to_be_visible(timeout=3_000)


def test_bouton_effacer_restaure_la_liste(page):
    """
    Clic sur "Effacer le filtre" supprime le tag actif et enleve l'empty state.
    / Clicking "Clear filter" removes the active tag and hides the empty state.
    """
    goto_explorer(page, "?v=event&tag=ce-tag-nexiste-pas-12345")

    # Attendre l'empty state / Wait for empty state
    empty = page.locator('[data-testid="explorer-empty-state"]')
    expect(empty).to_be_visible(timeout=5_000)

    # Cliquer "Effacer le filtre" / Click "Clear filter"
    clear_btn = page.locator('[data-testid="explorer-clear-tag"]')
    expect(clear_btn).to_be_visible(timeout=3_000)
    clear_btn.click()

    # Attendre que le JS reactive les filtres / Wait for JS to reapply filters
    page.wait_for_timeout(500)

    # L'empty state disparait / Empty state disappears
    expect(page.locator('[data-testid="explorer-empty-state"]')).to_have_count(0)

    # Le tag disparait de l'URL / Tag disappears from URL
    assert "tag=" not in page.url, (
        f"tag= encore present dans l'URL apres Effacer : {page.url}"
    )
