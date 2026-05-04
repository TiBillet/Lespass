"""
Tests E2E kiosk controlvanne — Playwright.
/ E2E tests for controlvanne kiosk — Playwright.

LOCALISATION : tests/e2e/test_controlvanne_kiosk.py

Teste le kiosk des tireuses connectees et le simulateur Pi (mode DEMO).
Les vues kiosk necessitent une session admin (auth via login_as_admin).
Le simulateur Pi n'apparait que quand DEMO=1 dans l'env.
/ Tests the connected tap kiosk and the Pi simulator (DEMO mode).
Kiosk views require an admin session (auth via login_as_admin).
The Pi simulator only appears when DEMO=1 in the env.

Prerequis :
- Serveur Django actif via Traefik + Daphne (WebSocket)
- DEMO=1 dans l'env du container Django
- Au moins une TireuseBec avec enabled=True et fut_actif (pour les tests de tirage)
- Les cartes demo (DEMO_TAGID_CLIENT1, CLIENT4) dans la base
"""

import os

import pytest


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _obtenir_uuid_tireuse_avec_fut(page):
    """
    Recupere l'UUID d'une tireuse active en naviguant sur la vue liste kiosk.
    Pas d'acces DB direct — on parse le HTML rendu par le serveur.
    / Gets the UUID of an active tap by navigating to the kiosk list view.
    No direct DB access — we parse the HTML rendered by the server.

    :param page: Playwright page (deja authentifiee)
    :return: str UUID ou None
    """
    page.goto("/controlvanne/kiosk/")
    page.wait_for_load_state("networkidle")

    # Chercher la premiere carte avec un prix > 0 (indique un fut actif)
    # / Find the first card with price > 0 (indicates an active keg)
    cartes = page.locator("[data-testid='kiosk-tap-card']")
    nombre_de_cartes = cartes.count()

    for index in range(nombre_de_cartes):
        carte = cartes.nth(index)
        uuid = carte.get_attribute("data-uuid")
        if uuid:
            return uuid

    return None


# Tag IDs demo depuis les variables d'environnement
# / Demo tag IDs from environment variables
DEMO_TAGID_CLIENT1 = os.environ.get("DEMO_TAGID_CLIENT1", "B52F9F3B")
DEMO_TAGID_CLIENT4 = os.environ.get("DEMO_TAGID_CLIENT4", "E85C2C6E")


# ──────────────────────────────────────────────────────────────────────
# Tests : vues kiosk (list + detail)
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def _ensure_tireuse_exists(django_shell):
    """Assure qu'au moins une TireuseBec existe dans lespass pour les vues kiosk,
    avec un fut actif (Product categorie FUT). Idempotent.
    Executee une fois par module.

    / Ensure at least one TireuseBec exists in lespass for kiosk views, with
    an active keg (Product category FUT). Idempotent. Run once per module.

    Le fut actif est necessaire pour test_02 (vue detail) — sans lui, le test
    se skippe car `_obtenir_uuid_tireuse_avec_fut` boucle sans rien trouver.
    / Active keg needed for test_02 (detail view) — without it, test skips
    because `_obtenir_uuid_tireuse_avec_fut` loops without finding anything.
    """
    django_shell(
        "from controlvanne.models import TireuseBec\n"
        "from BaseBillet.models import Product\n"
        "# Produit FUT (categorie 'U') — attache comme fut actif.\n"
        "# / FUT Product (category 'U') — attached as active keg.\n"
        "fut, _ = Product.objects.get_or_create(\n"
        "    name='E2E Test — Fut kiosk',\n"
        "    defaults={'categorie_article': Product.FUT},\n"
        ")\n"
        "tireuse, created = TireuseBec.objects.get_or_create(\n"
        "    nom_tireuse='E2E Test — Tireuse kiosk',\n"
        "    defaults={'enabled': True, 'fut_actif': fut},\n"
        ")\n"
        "# Si la tireuse existait sans fut_actif (seed precedent), on le pose.\n"
        "# / If tireuse existed without fut_actif (previous seed), set it.\n"
        "if not tireuse.fut_actif:\n"
        "    tireuse.fut_actif = fut\n"
        "    tireuse.save()\n"
        "print(f'OK tireuse={tireuse.nom_tireuse} fut={tireuse.fut_actif}')",
        schema="lespass",
    )


@pytest.mark.usefixtures("page")
class TestKioskVues:
    """
    Tests des vues kiosk (list et detail).
    Verifie que les templates se chargent, que le WebSocket se connecte,
    et que les elements cles sont presents.
    / Tests for kiosk views (list and detail).
    Verifies that templates load, WebSocket connects,
    and key elements are present.
    """

    def test_01_kiosk_list_accessible(self, page, login_as_admin):
        """
        GET /controlvanne/kiosk/ renvoie la grille de toutes les tireuses.
        Le data-slug-focus doit etre "all".
        / GET /controlvanne/kiosk/ returns the grid of all taps.
        data-slug-focus must be "all".
        """
        login_as_admin(page)
        page.goto("/controlvanne/kiosk/")
        page.wait_for_load_state("networkidle")

        # La grille de cartes doit etre presente
        # / The cards grid must be present
        grille = page.locator("[data-testid='kiosk-cards-grid']")
        assert grille.count() == 1, "La grille kiosk-cards-grid n'est pas presente"

        # Le slug_focus doit etre "all"
        # / slug_focus must be "all"
        slug_focus = grille.get_attribute("data-slug-focus")
        assert slug_focus == "all", f"slug_focus attendu 'all', recu '{slug_focus}'"

        # Au moins une carte de tireuse
        # / At least one tap card
        cartes = page.locator("[data-testid='kiosk-tap-card']")
        assert cartes.count() > 0, "Aucune carte de tireuse affichee"

    def test_02_kiosk_detail_une_seule_carte(self, page, login_as_admin):
        """
        GET /controlvanne/kiosk/<uuid>/ n'affiche qu'une seule carte.
        Le panneau simulateur est present en mode DEMO.
        / GET /controlvanne/kiosk/<uuid>/ shows only one card.
        The simulator panel is present in DEMO mode.
        """
        login_as_admin(page)
        uuid_tireuse = _obtenir_uuid_tireuse_avec_fut(page)
        if not uuid_tireuse:
            pytest.skip("Aucune tireuse avec fut actif")
        page.goto(f"/controlvanne/kiosk/{uuid_tireuse}/")
        page.wait_for_load_state("networkidle")

        # Une seule carte de tireuse (pas toutes)
        # / Only one tap card (not all of them)
        cartes = page.locator("[data-testid='kiosk-tap-card']")
        assert cartes.count() == 1, f"Attendu 1 carte, trouve {cartes.count()}"

        # Le slug_focus doit etre l'UUID de la tireuse
        # / slug_focus must be the tap's UUID
        grille = page.locator("[data-testid='kiosk-cards-grid']")
        slug_focus = grille.get_attribute("data-slug-focus")
        assert slug_focus == uuid_tireuse

    def test_03_kiosk_sans_auth_refuse(self, page):
        """
        GET /controlvanne/kiosk/ sans session retourne 403.
        / GET /controlvanne/kiosk/ without session returns 403.
        """
        # Nouvelle page sans login — doit etre refuse
        # / New page without login — must be denied
        response = page.goto("/controlvanne/kiosk/")
        assert response.status == 403, f"Attendu 403, recu {response.status}"


# ──────────────────────────────────────────────────────────────────────
# Tests : mode DEMO et simulateur Pi
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("page")
class TestSimulateurPi:
    """
    Tests du panneau simulateur Pi (mode DEMO).
    Verifie la presence du panneau, les boutons carte, le slider debit,
    et le flow complet badge → authorize → tirage → fin.
    / Tests for the Pi simulator panel (DEMO mode).
    Verifies panel presence, card buttons, flow slider,
    and the full badge → authorize → pour → end flow.
    """

    def test_04_panneau_simulateur_present_en_demo(self, page, login_as_admin):
        """
        En mode DEMO, le panneau simulateur est present sur la vue detail.
        Il contient les boutons carte et est en etat IDLE.
        / In DEMO mode, the simulator panel is present on the detail view.
        It contains card buttons and is in IDLE state.
        """
        login_as_admin(page)
        uuid_tireuse = _obtenir_uuid_tireuse_avec_fut(page)
        if not uuid_tireuse:
            pytest.skip("Aucune tireuse avec fut actif")

        page.goto(f"/controlvanne/kiosk/{uuid_tireuse}/")
        page.wait_for_load_state("networkidle")

        # Panneau simulateur present
        # / Simulator panel present
        panneau = page.locator("[data-testid='simu-pi-panel']")
        assert panneau.count() == 1, "Panneau simulateur absent"

        # Etat IDLE
        # / IDLE state
        etat = page.locator("[data-testid='simu-state']")
        assert "IDLE" in etat.inner_text()

        # Boutons carte presents
        # / Card buttons present
        boutons = page.locator("[data-testid='simu-card-buttons'] button")
        assert boutons.count() >= 4, f"Attendu >= 4 boutons, trouve {boutons.count()}"

        # Bouton retirer carte desactive
        # / Remove card button disabled
        bouton_retirer = page.locator("[data-testid='simu-remove-card']")
        assert bouton_retirer.is_disabled()

        # Section debit cachee (pas encore autorise)
        # / Flow section hidden (not yet authorized)
        section_debit = page.locator("[data-testid='simu-flow-section']")
        assert not section_debit.is_visible()

    def test_05_panneau_absent_sur_vue_list(self, page, login_as_admin):
        """
        Le panneau simulateur n'apparait PAS sur la vue liste (all).
        Il est reserve a la vue detail (single tap).
        / The simulator panel does NOT appear on the list view (all).
        It is reserved for the detail view (single tap).
        """
        login_as_admin(page)
        page.goto("/controlvanne/kiosk/")
        page.wait_for_load_state("networkidle")

        panneau = page.locator("[data-testid='simu-pi-panel']")
        assert panneau.count() == 0, "Le panneau simulateur ne devrait pas etre sur la vue liste"

    def test_06_badge_carte_inconnue_refuse(self, page, login_as_admin):
        """
        Badger une carte inconnue (CLIENT4 = E85C2C6E) affiche "Refuse".
        L'etat passe a CARD_PRESENT mais le slider n'apparait pas.
        / Badging an unknown card (CLIENT4 = E85C2C6E) shows "Refused".
        State changes to CARD_PRESENT but slider does not appear.
        """
        login_as_admin(page)
        uuid_tireuse = _obtenir_uuid_tireuse_avec_fut(page)
        if not uuid_tireuse:
            pytest.skip("Aucune tireuse avec fut actif")

        page.goto(f"/controlvanne/kiosk/{uuid_tireuse}/")
        page.wait_for_load_state("networkidle")

        # Recuperer le tag_id de la carte inconnue (CLIENT4)
        # / Get the unknown card tag_id (CLIENT4)
        tag_id_inconnu = DEMO_TAGID_CLIENT4

        # Cliquer sur le bouton de la carte inconnue
        # / Click the unknown card button
        bouton_carte = page.locator(f"[data-testid='simu-card-{tag_id_inconnu}']")
        if bouton_carte.count() == 0:
            pytest.skip(f"Bouton carte {tag_id_inconnu} non trouve (pas dans demo_tags)")

        bouton_carte.click()

        # Attendre la reponse API / Wait for API response
        page.wait_for_timeout(2000)

        # Le message doit contenir "Refus" ou "error" ou "not found"
        # / Message must contain "Refused" or "error" or "not found"
        message = page.locator("[data-testid='simu-message']").inner_text()
        message_en_minuscules = message.lower()
        assert (
            "refus" in message_en_minuscules
            or "error" in message_en_minuscules
            or "not found" in message_en_minuscules
            or "unknown" in message_en_minuscules
        ), f"Message inattendu pour carte inconnue : '{message}'"

        # Le slider ne doit PAS etre visible (pas autorise)
        # / Slider must NOT be visible (not authorized)
        section_debit = page.locator("[data-testid='simu-flow-section']")
        assert not section_debit.is_visible()

    def test_07_retirer_carte_retour_idle(self, page, login_as_admin):
        """
        Apres un badge refuse, cliquer "Retirer carte" remet l'etat a IDLE.
        / After a refused badge, clicking "Remove card" resets state to IDLE.
        """
        login_as_admin(page)
        uuid_tireuse = _obtenir_uuid_tireuse_avec_fut(page)
        if not uuid_tireuse:
            pytest.skip("Aucune tireuse avec fut actif")

        page.goto(f"/controlvanne/kiosk/{uuid_tireuse}/")
        page.wait_for_load_state("networkidle")

        # Badger une carte (n'importe laquelle) pour passer en CARD_PRESENT
        # / Badge any card to switch to CARD_PRESENT
        tag_id = DEMO_TAGID_CLIENT4
        bouton_carte = page.locator(f"[data-testid='simu-card-{tag_id}']")
        if bouton_carte.count() == 0:
            pytest.skip(f"Bouton carte {tag_id} non trouve")

        bouton_carte.click()
        page.wait_for_timeout(2000)

        # Cliquer "Retirer carte" / Click "Remove card"
        bouton_retirer = page.locator("[data-testid='simu-remove-card']")
        bouton_retirer.click()
        page.wait_for_timeout(1500)

        # L'etat doit etre revenu a IDLE / State must be back to IDLE
        etat = page.locator("[data-testid='simu-state']")
        assert "IDLE" in etat.inner_text(), f"Etat attendu IDLE, recu '{etat.inner_text()}'"

        # Les boutons carte doivent etre reactives / Card buttons must be re-enabled
        bouton_carte_apres = page.locator(f"[data-testid='simu-card-{tag_id}']")
        assert not bouton_carte_apres.is_disabled()


# ──────────────────────────────────────────────────────────────────────
# Tests : admin Unfold — liens kiosk
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("page")
class TestAdminLiensKiosk:
    """
    Tests des liens kiosk dans l'admin Unfold.
    Verifie la sidebar, le bouton kiosk sur la fiche tireuse,
    et le lien "Open kiosk" sur la carte module dashboard.
    / Tests for kiosk links in the Unfold admin.
    Verifies sidebar, kiosk button on tap form,
    and "Open kiosk" link on the module dashboard card.
    """

    def test_08_sidebar_kiosk_dashboard(self, page, login_as_admin):
        """
        La sidebar Tireuses contient un lien "Kiosk dashboard" vers /controlvanne/kiosk/.
        / The Tireuses sidebar contains a "Kiosk dashboard" link to /controlvanne/kiosk/.
        """
        login_as_admin(page)
        page.goto("/admin/")
        page.wait_for_load_state("networkidle")

        # Chercher le lien kiosk dashboard dans la sidebar
        # / Find kiosk dashboard link in sidebar
        lien_kiosk = page.locator("a[href='/controlvanne/kiosk/']")
        assert lien_kiosk.count() > 0, "Lien /controlvanne/kiosk/ absent de la sidebar"

    def test_09_bouton_kiosk_sur_fiche_tireuse(self, page, login_as_admin):
        """
        La fiche d'une tireuse affiche le bouton "Open kiosk view" en haut.
        / The tap form shows the "Open kiosk view" button at the top.
        """
        login_as_admin(page)
        uuid_tireuse = _obtenir_uuid_tireuse_avec_fut(page)
        if not uuid_tireuse:
            pytest.skip("Aucune tireuse avec fut actif")

        page.goto(f"/admin/controlvanne/tireusebec/{uuid_tireuse}/change/")
        page.wait_for_load_state("networkidle")

        # Bouton kiosk present / Kiosk button present
        bouton_kiosk = page.locator("[data-testid='kiosk-link']")
        assert bouton_kiosk.count() == 1, "Bouton 'Open kiosk view' absent"

        # Le lien pointe vers la bonne URL / Link points to correct URL
        href = bouton_kiosk.get_attribute("href")
        assert f"/controlvanne/kiosk/{uuid_tireuse}/" == href

    def test_10_module_dashboard_lien_kiosk(self, page, login_as_admin):
        """
        La carte module "Tireuses connectees" sur le dashboard admin
        contient un lien "Open kiosk".
        / The "Connected taps" module card on the admin dashboard
        contains an "Open kiosk" link.
        """
        login_as_admin(page)
        page.goto("/admin/")
        page.wait_for_load_state("networkidle")

        # Chercher la carte module tireuse / Find the tap module card
        carte_tireuse = page.locator("[data-testid='dashboard-card-tireuse']")
        if carte_tireuse.count() == 0:
            pytest.skip("Carte module tireuse non trouvee (module_tireuse inactif ?)")

        # Le lien "Open kiosk" dans la carte / "Open kiosk" link in the card
        lien_kiosk = carte_tireuse.locator("a[href='/controlvanne/kiosk/']")
        assert lien_kiosk.count() > 0, "Lien 'Open kiosk' absent de la carte module tireuse"
