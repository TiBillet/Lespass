"""
Tests E2E : flow adhésion POS avec identification obligatoire (6 chemins + 2 retour).
/ E2E tests: POS membership flow with mandatory identification (6 paths + 2 back).

Conversion de tests/playwright/tests/laboutik/44-laboutik-adhesion-identification.spec.ts

Prérequis / Prerequisites:
- docker exec lespass_django poetry run python manage.py create_test_pos_data
- PV Adhesions (comportement='A') existant
- Cartes 52BE6543 (anonyme), D74B1B5D (jetable), A49E8E2A (primaire)
- DEMO=1 dans l'environnement (boutons simulation NFC)
"""

import os
import random
import string

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e

DEMO_TAGID_CM = os.environ.get("DEMO_TAGID_CM", "A49E8E2A")
DEMO_TAGID_CLIENT1 = os.environ.get("DEMO_TAGID_CLIENT1", "52BE6543")
DEMO_TAGID_CLIENT3 = os.environ.get("DEMO_TAGID_CLIENT3", "D74B1B5D")


def _unique_suffix():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


# ---------------------------------------------------------------------------
# Fixture setup/teardown cartes / Card setup/teardown fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def adhesion_cards_setup(django_shell):
    """Setup : reset carte 1 (anonyme), setup carte 3 (avec user jetable).
    Teardown : reset les deux cartes.
    / Setup: reset card 1 (anonymous), setup card 3 (with disposable user).
    Teardown: reset both cards.
    """
    suffix = _unique_suffix()

    # Reset carte 1 (doit rester anonyme)
    django_shell(
        f"from laboutik.utils.test_helpers import reset_carte; "
        f"print(reset_carte('{DEMO_TAGID_CLIENT1}'))"
    )

    # Reset carte 3 puis assigner un user jetable
    django_shell(
        f"from laboutik.utils.test_helpers import reset_carte; "
        f"from QrcodeCashless.models import CarteCashless; "
        f"from AuthBillet.utils import get_or_create_user; "
        f"reset_carte('{DEMO_TAGID_CLIENT3}'); "
        f"user = get_or_create_user('carte3-jetable-{suffix}@tibillet.localhost', send_mail=False); "
        f"user.first_name = 'CarteJetable'; user.last_name = 'TestNFC'; user.save(); "
        f"carte = CarteCashless.objects.get(tag_id='{DEMO_TAGID_CLIENT3}'); "
        f"carte.user = user; carte.save(); "
        f"print(f'SETUP_OK {{user.email}} → {{carte.tag_id}}')"
    )

    yield suffix

    # Teardown : reset les deux cartes / Reset both cards
    django_shell(
        f"from laboutik.utils.test_helpers import reset_carte; "
        f"reset_carte('{DEMO_TAGID_CLIENT1}'); "
        f"reset_carte('{DEMO_TAGID_CLIENT3}'); "
        f"print('TEARDOWN_OK')"
    )


# ---------------------------------------------------------------------------
# Helper : naviguer vers PV Adhesions + ajouter article + VALIDER
# / Helper: navigate to Adhesions POS + add article + VALIDATE
# ---------------------------------------------------------------------------


def _naviguer_et_ajouter_adhesion(page, pos_page):
    """Ouvre le PV Adhesions, clic premier article, gère overlay tarif, clic VALIDER.
    / Opens Adhesions POS, clicks first article, handles rate overlay, clicks VALIDATE.
    """
    pos_page(page, comportement="A")

    # Cliquer le premier article d'adhésion / Click first adhesion article
    adhesion_tile = page.locator("#products .article-container").first
    expect(adhesion_tile).to_be_visible(timeout=10_000)
    adhesion_tile.click()

    # Si overlay tarif → cliquer premier tarif fixe / If rate overlay → click first fixed rate
    tarif_overlay = page.locator(".tarif-overlay")
    if tarif_overlay.is_visible(timeout=2_000):
        first_fixed = tarif_overlay.locator(".tarif-btn:not(.tarif-btn-free)").first
        first_fixed.click()

    # Vérifier qu'un article est dans l'addition / Verify article in addition
    expect(page.locator("#addition-list .addition-line-grid")).to_be_visible(timeout=5_000)

    # Cliquer VALIDER → écran choix paiement / Click VALIDATE → payment choice screen
    page.locator("#bt-valider").click()
    expect(page.locator('[data-testid="paiement-moyens"]')).to_be_visible(timeout=10_000)


# ===========================================================================
# Tests adhésion identification / Membership identification tests
# ===========================================================================


class TestPOSAdhesionIdentification:
    """Flow adhésion avec identification obligatoire (6 chemins).
    / Membership flow with mandatory identification (6 paths).
    """

    # --- Chemin 5 : ESPECE → "Saisir email" → formulaire → confirmation → PAYER ---

    def test_chemin_5_espece_saisir_email(
        self, page, pos_page, django_shell, adhesion_cards_setup
    ):
        """Chemin 5 : espèce → saisir email → confirmation → paiement.
        / Path 5: cash → enter email → confirmation → payment.
        """
        suffix = adhesion_cards_setup
        test_email = f"adh5-{suffix}@example.com"

        _naviguer_et_ajouter_adhesion(page, pos_page)

        # ESPECE → écran identification
        page.locator('[data-testid="adhesion-btn-especes"]').click()
        expect(page.locator('[data-testid="adhesion-choose-id"]')).to_be_visible(timeout=10_000)

        # "Saisir email" → formulaire
        page.locator('[data-testid="adhesion-choose-email"]').click()
        expect(page.locator('[data-testid="adhesion-form"]')).to_be_visible(timeout=10_000)

        # Remplir et valider
        page.locator('[data-testid="adhesion-input-email"]').fill(test_email)
        page.locator('[data-testid="adhesion-input-prenom"]').fill("PrenomCinq")
        page.locator('[data-testid="adhesion-input-nom"]').fill("NomCinq")
        page.locator('[data-testid="adhesion-btn-valider"]').click()

        # Confirmation
        expect(page.locator('[data-testid="adhesion-confirm"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="adhesion-confirm-user"]')).to_contain_text(test_email)
        expect(page.locator('[data-testid="adhesion-confirm-user"]')).to_contain_text("NOMCINQ")

        # Confirmer le paiement
        page.locator('[data-testid="adhesion-btn-confirmer"]').click()
        expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)

        # Vérification DB / DB verification
        result = django_shell(
            f"from BaseBillet.models import Membership; "
            f"from AuthBillet.models import TibilletUser; "
            f"user = TibilletUser.objects.filter(email='{test_email}').first(); "
            f"m = Membership.objects.filter(user=user).order_by('-date_added').first() if user else None; "
            f"print(f'OK status={{m.status}}') if m else print('NO_MEMBERSHIP')"
        )
        assert "OK" in result, f"Membership non trouvée: {result}"

    # --- Chemin 5bis : CB → "Saisir email" ---

    def test_chemin_5bis_cb_saisir_email(
        self, page, pos_page, adhesion_cards_setup
    ):
        """Chemin 5bis : CB → saisir email → confirmation → paiement.
        / Path 5bis: card → enter email → confirmation → payment.
        """
        suffix = adhesion_cards_setup
        test_email = f"adh5cb-{suffix}@example.com"

        _naviguer_et_ajouter_adhesion(page, pos_page)

        # CB → identification
        page.locator('[data-testid="adhesion-btn-cb"]').click()
        expect(page.locator('[data-testid="adhesion-choose-id"]')).to_be_visible(timeout=10_000)

        # "Saisir email"
        page.locator('[data-testid="adhesion-choose-email"]').click()
        expect(page.locator('[data-testid="adhesion-form"]')).to_be_visible(timeout=10_000)

        # Remplir et valider
        page.locator('[data-testid="adhesion-input-email"]').fill(test_email)
        page.locator('[data-testid="adhesion-input-prenom"]').fill("PrenomCB")
        page.locator('[data-testid="adhesion-input-nom"]').fill("NomCB")
        page.locator('[data-testid="adhesion-btn-valider"]').click()

        # Confirmation → paiement
        expect(page.locator('[data-testid="adhesion-confirm"]')).to_be_visible(timeout=10_000)
        page.locator('[data-testid="adhesion-btn-confirmer"]').click()
        expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)

    # --- Chemin 3 : ESPECE → "Scanner carte" NFC → carte avec user → confirmation ---

    def test_chemin_3_espece_scanner_carte_user_connu(
        self, page, pos_page, adhesion_cards_setup
    ):
        """Chemin 3 : espèce → scanner carte (user connu CLIENT3) → confirmation → paiement.
        / Path 3: cash → scan card (known user CLIENT3) → confirmation → payment.
        """
        _naviguer_et_ajouter_adhesion(page, pos_page)

        # ESPECE → identification
        page.locator('[data-testid="adhesion-btn-especes"]').click()
        expect(page.locator('[data-testid="adhesion-choose-id"]')).to_be_visible(timeout=10_000)

        # "Scanner carte" → NFC
        page.locator('[data-testid="adhesion-choose-nfc"]').click()
        expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(timeout=10_000)

        # Cliquer CLIENT3 (avec user assigné)
        page.locator(f'.nfc-reader-simu-bt[tag-id="{DEMO_TAGID_CLIENT3}"]').click()

        # → confirmation directe (carte avec user)
        expect(page.locator('[data-testid="adhesion-confirm"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="adhesion-confirm-user"]')).to_contain_text("carte3-jetable")
        expect(page.locator('[data-testid="adhesion-confirm-user"]')).to_contain_text("TESTNFC")

        # Confirmer le paiement
        page.locator('[data-testid="adhesion-btn-confirmer"]').click()
        expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)

    # --- Chemin 1 : CASHLESS → NFC carte avec user → confirmation ---

    def test_chemin_1_cashless_nfc_carte_avec_user(
        self, page, pos_page, adhesion_cards_setup
    ):
        """Chemin 1 : cashless → NFC carte avec user (CLIENT3) → confirmation directe.
        / Path 1: cashless → NFC card with user (CLIENT3) → direct confirmation.
        """
        _naviguer_et_ajouter_adhesion(page, pos_page)

        # CASHLESS → NFC directement (pas d'écran choix identification)
        page.locator('[data-testid="adhesion-btn-nfc"]').click()

        # Cliquer CLIENT3 (avec user)
        expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(timeout=10_000)
        page.locator(f'.nfc-reader-simu-bt[tag-id="{DEMO_TAGID_CLIENT3}"]').click()

        # → confirmation directe
        expect(page.locator('[data-testid="adhesion-confirm"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="adhesion-confirm-user"]')).to_contain_text("carte3-jetable")
        expect(page.locator('[data-testid="adhesion-confirm-user"]')).to_contain_text("TESTNFC")

    # --- Chemin 2 : CASHLESS → NFC carte anonyme → formulaire → confirmation ---
    # (AVANT chemin 4 — chemin 4 associe un user à CLIENT1)

    def test_chemin_2_cashless_nfc_carte_anonyme(
        self, page, pos_page, adhesion_cards_setup
    ):
        """Chemin 2 : cashless → NFC carte anonyme (CLIENT1) → formulaire → confirmation.
        / Path 2: cashless → NFC anonymous card (CLIENT1) → form → confirmation.
        """
        suffix = adhesion_cards_setup
        test_email = f"adh2-{suffix}@example.com"

        _naviguer_et_ajouter_adhesion(page, pos_page)

        # CASHLESS → NFC
        page.locator('[data-testid="adhesion-btn-nfc"]').click()

        # Cliquer CLIENT1 (anonyme)
        expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(timeout=10_000)
        page.locator(f'.nfc-reader-simu-bt[tag-id="{DEMO_TAGID_CLIENT1}"]').click()

        # → carte anonyme → formulaire avec tag_id caché
        expect(page.locator('[data-testid="adhesion-form"]')).to_be_visible(timeout=10_000)

        # Remplir et valider → confirmation
        page.locator('[data-testid="adhesion-input-email"]').fill(test_email)
        page.locator('[data-testid="adhesion-input-prenom"]').fill("PrenomDeux")
        page.locator('[data-testid="adhesion-input-nom"]').fill("NomDeux")
        page.locator('[data-testid="adhesion-btn-valider"]').click()

        expect(page.locator('[data-testid="adhesion-confirm"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="adhesion-confirm-user"]')).to_contain_text(test_email)

    # --- Chemin 4 : ESPECE → "Scanner carte" NFC → carte anonyme → formulaire → PAYER ---
    # (APRÈS chemin 2 — chemin 4 associe un user à CLIENT1)

    def test_chemin_4_espece_scanner_carte_anonyme(
        self, page, pos_page, adhesion_cards_setup
    ):
        """Chemin 4 : espèce → scanner carte (anonyme CLIENT1) → formulaire → confirmation → paiement.
        / Path 4: cash → scan card (anonymous CLIENT1) → form → confirmation → payment.
        """
        suffix = adhesion_cards_setup
        test_email = f"adh4-{suffix}@example.com"

        _naviguer_et_ajouter_adhesion(page, pos_page)

        # ESPECE → identification → scanner carte
        page.locator('[data-testid="adhesion-btn-especes"]').click()
        expect(page.locator('[data-testid="adhesion-choose-id"]')).to_be_visible(timeout=10_000)
        page.locator('[data-testid="adhesion-choose-nfc"]').click()

        # Cliquer CLIENT1 (anonyme)
        expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(timeout=10_000)
        page.locator(f'.nfc-reader-simu-bt[tag-id="{DEMO_TAGID_CLIENT1}"]').click()

        # → carte sans user → formulaire
        expect(page.locator('[data-testid="adhesion-form"]')).to_be_visible(timeout=10_000)

        # Remplir et valider
        page.locator('[data-testid="adhesion-input-email"]').fill(test_email)
        page.locator('[data-testid="adhesion-input-prenom"]').fill("PrenomQuatre")
        page.locator('[data-testid="adhesion-input-nom"]').fill("NomQuatre")
        page.locator('[data-testid="adhesion-btn-valider"]').click()

        # Confirmation → paiement
        expect(page.locator('[data-testid="adhesion-confirm"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="adhesion-confirm-user"]')).to_contain_text(test_email)
        page.locator('[data-testid="adhesion-btn-confirmer"]').click()
        expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)

    # --- Bouton RETOUR depuis écran identification ---

    def test_bouton_retour_ecran_identification(
        self, page, pos_page, adhesion_cards_setup
    ):
        """Bouton retour fonctionne depuis l'écran identification.
        / Back button works from identification screen.
        """
        _naviguer_et_ajouter_adhesion(page, pos_page)

        # ESPECE → identification
        page.locator('[data-testid="adhesion-btn-especes"]').click()
        expect(page.locator('[data-testid="adhesion-choose-id"]')).to_be_visible(timeout=10_000)

        # RETOUR → l'écran disparaît
        page.locator('[data-testid="adhesion-choose-id"] #bt-retour-layer1').click()
        expect(page.locator('[data-testid="adhesion-choose-id"]')).not_to_be_visible(timeout=5_000)

    # --- Bouton RETOUR depuis formulaire email ---

    def test_bouton_retour_formulaire_email(
        self, page, pos_page, adhesion_cards_setup
    ):
        """Bouton retour fonctionne depuis le formulaire email.
        / Back button works from email form.
        """
        _naviguer_et_ajouter_adhesion(page, pos_page)

        # ESPECE → identification → saisir email
        page.locator('[data-testid="adhesion-btn-especes"]').click()
        expect(page.locator('[data-testid="adhesion-choose-id"]')).to_be_visible(timeout=10_000)
        page.locator('[data-testid="adhesion-choose-email"]').click()
        expect(page.locator('[data-testid="adhesion-form"]')).to_be_visible(timeout=10_000)

        # RETOUR → le formulaire disparaît
        page.locator('[data-testid="adhesion-form"] #bt-retour-layer1').click()
        expect(page.locator('[data-testid="adhesion-form"]')).not_to_be_visible(timeout=5_000)
