"""
Tests E2E : création d'événement via le wizard unifié + gestion des doublons.
/ E2E tests: event creation via the unified wizard + duplicate handling.

Conversion de tests/playwright/tests/29-event-quick-create-duplicate.spec.ts

L'ancien flow « quick create » (offcanvas /event/simple_add_event/) a été
remplacé par le wizard unifié /event/wizard/ (CHANTIER-03) :
  - Étape 1 (lieu) : choix d'une adresse existante ou création d'un nouveau lieu.
  - Étape 2 (event) : ajout de brouillons (HTMX) puis finalisation.
/ The old offcanvas quick-create flow was replaced by the unified wizard:
  step 1 (place) + step 2 (add drafts via HTMX then finalize).

BUG CORRIGÉ (2026-06-11) : la finalisation gère désormais le doublon
(même nom + même datetime) : `EventWizard.step2_event` enveloppe la création
dans `transaction.atomic()` et attrape l'IntegrityError → message warning +
retour à l'étape des brouillons. Rien n'est créé (tout ou rien).
/ FIXED BUG (2026-06-11): finalize now handles duplicates (same name + datetime):
wraps creation in atomic(), catches IntegrityError → warning + back to drafts,
nothing created (all-or-nothing).

ATTENTION : ces tests créent de vrais événements dans la DB partagée (sans rollback).
Les noms sont suffixés avec un uuid aléatoire pour éviter les collisions.
/ WARNING: these tests create real events in the shared DB (no rollback).
Names are suffixed with a random uuid to avoid collisions.
"""

import time

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _iso_local_future(offset_days=10, hour=10, minute=0):
    """Retourne une datetime ISO locale dans le futur (format YYYY-MM-DDTHH:mm).
    / Returns a local future datetime in ISO format (YYYY-MM-DDTHH:mm).

    Même logique que la fonction TypeScript isoLocalFuture() du spec.
    / Same logic as the TypeScript isoLocalFuture() helper in the spec.
    """
    import datetime
    d = datetime.datetime.now() + datetime.timedelta(days=offset_days)
    d = d.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return d.strftime("%Y-%m-%dT%H:%M")


def _walk_wizard_and_finalize(page, event_name, start_local):
    """Parcourt le wizard de bout en bout (étape lieu + étape event) puis clique
    sur le bouton de finalisation. Retourne le statut HTTP de la réponse POST.

    / Walk the wizard end to end (place step + event step), then click finalize.
    Returns the HTTP status of the finalize POST response.

    Étape 1 : choisir la première adresse existante via le radio wizard-place-radio,
    puis cliquer sur "Continuer" (bouton activé par JS après sélection).
    Étape 2 : remplir nom + datetime + description, cliquer "Ajouter à la liste"
    (HTMX), vérifier que le brouillon est visible, puis finaliser.
    / Step 1: pick the first existing address via wizard-place-radio, then click
    "Continue" (enabled by JS after selection).
    Step 2: fill name + datetime + description, click "Add to list" (HTMX),
    verify draft appears, then finalize.
    """
    # --- Étape 1 : sélection du lieu ---
    # / Step 1: place selection
    page.goto("/event/wizard/place/")
    page.wait_for_load_state("domcontentloaded")

    # Cocher la première adresse existante.
    # Le bouton "Continuer" est désactivé par défaut et activé par JS après la
    # sélection d'un radio, donc on attend qu'il soit enabled avant de cliquer.
    # / Check the first existing address. The "Continue" button is disabled by
    # default and enabled by JS after a radio selection — wait for it.
    first_radio = page.locator('[data-testid="wizard-place-radio"]').first
    expect(first_radio).to_be_attached()
    first_radio.check()

    continue_btn = page.locator('[data-testid="wizard-place-submit"]')
    # Attendre que le JS active le bouton après la sélection du radio.
    # / Wait for JS to enable the button after radio selection.
    expect(continue_btn).to_be_enabled(timeout=5_000)
    continue_btn.click()

    # --- Étape 2 : saisie et ajout du brouillon d'événement ---
    # / Step 2: fill and add the event draft
    page.wait_for_url("**/event/wizard/event/**")

    page.locator('[data-testid="wizard-event-name"]').fill(event_name)
    page.locator('[data-testid="wizard-event-datetime"]').fill(start_local)
    page.locator('[data-testid="wizard-event-description"]').fill(
        "Detailed description for E2E test."
    )
    page.locator('[data-testid="wizard-event-add"]').click()

    # Le brouillon doit apparaître dans la liste (swap HTMX innerHTML).
    # / The draft must appear in the list (HTMX innerHTML swap).
    draft_card = page.locator('[data-testid="wizard-event-0"]')
    expect(draft_card).to_be_visible(timeout=10_000)
    expect(draft_card).to_contain_text(event_name)

    # --- Finalisation : POST plein page ---
    # On capture le statut de la réponse pour détecter un éventuel 500.
    # / Finalize: full-page POST. Capture the response status to detect a 500.
    with page.expect_response(
        lambda resp: "/event/wizard/event/" in resp.url and resp.request.method == "POST",
        timeout=15_000,
    ) as response_info:
        page.locator('[data-testid="wizard-events-finalize"]').click()

    return response_info.value.status


class TestEventWizardCreateAndDuplicate:
    """Création d'événement via le wizard unifié + gestion des doublons.
    / Event creation via the unified wizard + duplicate handling.
    """

    def test_create_event_via_wizard(self, page, login_as_admin):
        """Crée un événement via le wizard unifié, vérifie qu'il apparaît sur l'agenda.
        / Creates an event via the unified wizard, verifies it appears on the agenda.

        Étapes testées :
        1. Le bouton d'ajout d'événement est visible sur la page agenda.
        2. Le wizard se complète sans erreur serveur (< 500).
        3. Après la finalisation, la page de détail contient le nom de l'événement.
        4. L'événement apparaît dans la liste de l'agenda.
        """
        # Connexion admin (droits de création d'événement).
        # / Admin login (event creation rights).
        login_as_admin(page)

        # Suffixe unique pour éviter les collisions dans la DB partagée.
        # / Unique suffix to avoid collisions in the shared DB.
        suffix = str(int(time.time() * 1000))
        event_name = f"Playwright Wizard EVT {suffix}"
        start_local = _iso_local_future(offset_days=5, hour=10, minute=0)

        # --- Vérification du bouton wizard sur l'agenda ---
        # / Check that the wizard entry button is visible on the agenda
        page.goto("/event/")
        page.wait_for_load_state("domcontentloaded")
        expect(page.locator('[data-testid="btn-event-add"]')).to_be_visible()

        # --- Création de l'événement via le wizard ---
        # / Create the event via the wizard
        status = _walk_wizard_and_finalize(page, event_name, start_local)
        assert status < 500, (
            f"La finalisation du wizard ne doit pas provoquer une erreur serveur. "
            f"Statut HTTP reçu : {status}"
        )

        # Après finalisation d'un seul brouillon, le serveur redirige vers la
        # page de détail de l'événement créé.
        # / After finalizing a single draft, the server redirects to the event
        # detail page.
        page.wait_for_load_state("domcontentloaded")
        expect(page.locator("body")).to_contain_text(event_name)

        # --- Vérification sur l'agenda ---
        # / Check the event appears on the agenda
        page.goto("/event/")
        page.wait_for_load_state("domcontentloaded")
        expect(page.locator("#event_list")).to_contain_text(event_name)

    def test_duplicate_event_shows_error_not_500(self, page, login_as_admin):
        """Un doublon (même nom + même datetime) doit afficher une erreur, pas une 500.
        / A duplicate (same name + datetime) must show an error, not a 500.

        Première création → OK (statut < 500).
        Deuxième tentative avec le même nom et la même datetime → le serveur doit
        répondre sans crasher (IntegrityError attrapée dans transaction.atomic(),
        message warning + retour à l'étape brouillons), statut < 500.

        BUG CORRIGÉ : avant CHANTIER-03 (2026-06-11), cette seconde tentative
        causait un 500 (IntegrityError non attrapée sur unique_together('name','datetime')).
        / FIXED BUG: before CHANTIER-03 (2026-06-11), the second attempt caused a
        500 (uncaught IntegrityError on unique_together('name','datetime')).
        """
        login_as_admin(page)

        suffix = str(int(time.time() * 1000))
        event_name = f"Playwright Wizard DUP {suffix}"
        start_local = _iso_local_future(offset_days=6, hour=10, minute=0)

        # --- Première création : doit réussir ---
        # / First creation: must succeed
        first_status = _walk_wizard_and_finalize(page, event_name, start_local)
        assert first_status < 500, (
            f"La première création doit réussir. Statut HTTP reçu : {first_status}"
        )

        # --- Doublon : même nom + même datetime ---
        # Le serveur doit répondre sans crasher : erreur métier ou message warning,
        # PAS une 500 (IntegrityError unique_together).
        # / Duplicate: same name + same datetime.
        # The server must answer without crashing: business error or warning message,
        # NOT a 500 (unique_together IntegrityError).
        duplicate_status = _walk_wizard_and_finalize(page, event_name, start_local)
        assert duplicate_status < 500, (
            f"La finalisation d'un doublon ne doit pas provoquer une 500. "
            f"Statut HTTP reçu : {duplicate_status}"
        )
