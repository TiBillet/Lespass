"""
Tests E2E : paiements POS (espèces, CB, NFC cashless).
/ E2E tests: POS payments (cash, card, NFC cashless).

Conversion de tests/playwright/tests/laboutik/39-laboutik-pos-paiement.spec.ts

Prérequis / Prerequisites:
- docker exec lespass_django poetry run python manage.py create_test_pos_data
- Carte primaire tag_id_cm=A49E8E2A
- DEMO=1 dans l'environnement (boutons simulation NFC)
"""

import os
import re

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e

DEMO_TAGID_CM = os.environ.get("DEMO_TAGID_CM", "A49E8E2A")
DEMO_TAGID_CLIENT1 = os.environ.get("DEMO_TAGID_CLIENT1", "52BE6543")
DEMO_TAGID_CLIENT2 = os.environ.get("DEMO_TAGID_CLIENT2", "C63A0A4C")
DEMO_TAGID_CLIENT3 = os.environ.get("DEMO_TAGID_CLIENT3", "D74B1B5D")
DEMO_TAGID_CLIENT4 = os.environ.get("DEMO_TAGID_CLIENT4", "E85C2C6E")


# ---------------------------------------------------------------------------
# Helpers paiement / Payment helpers
# ---------------------------------------------------------------------------

def _add_article_and_validate(page, article_name):
    """Clic tuile article → vérif addition → clic VALIDER → panneau moyens visible.
    / Click article tile → verify addition → click VALIDER → payment panel visible.
    """
    tile = page.locator("#products .article-container").filter(has_text=article_name).first
    expect(tile).to_be_visible(timeout=10_000)
    tile.click()
    expect(page.locator("#addition-list")).to_contain_text(article_name, timeout=5_000)


def _click_valider(page):
    """Clic VALIDER → panneau moyens de paiement visible.
    / Click VALIDER → payment methods panel visible.
    """
    page.locator("#bt-valider").click()
    expect(page.locator('[data-testid="paiement-moyens"]')).to_be_visible(timeout=10_000)


def _pay_especes(page):
    """Choisir ESPÈCE → confirmer → succès.
    / Choose CASH → confirm → success.
    """
    page.locator('[data-testid="paiement-moyens"]').get_by_text("ESPÈCE").click()
    expect(page.locator('[data-testid="paiement-confirmation"]')).to_be_visible(timeout=10_000)
    page.locator("#bt-valider-layer2").click()
    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)


def _pay_cb(page):
    """Choisir CB → confirmer → succès.
    / Choose CB → confirm → success.
    """
    page.locator('[data-testid="paiement-moyens"]').get_by_text("CB").click()
    expect(page.locator('[data-testid="paiement-confirmation"]')).to_be_visible(timeout=10_000)
    page.locator("#bt-valider-layer2").click()
    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)


def _pay_nfc(page, tag_id):
    """Choisir CASHLESS → cliquer carte NFC simulation → succès.
    / Choose CASHLESS → click NFC simulation card → success.
    """
    page.locator('[data-testid="paiement-moyens"]').get_by_text("CASHLESS").click()
    expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(timeout=10_000)
    page.locator(f'.nfc-reader-simu-bt[tag-id="{tag_id}"]').click()
    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)


def _retour_caisse(page):
    """Clic RETOUR dans l'écran de succès → panier vide.
    / Click RETOUR in success screen → empty cart.
    """
    page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click()
    expect(page.locator('[data-testid="paiement-succes"]')).not_to_be_visible(timeout=5_000)
    expect(page.locator('[data-testid="addition-empty-placeholder"]')).to_be_visible(timeout=5_000)


# ===========================================================================
# Tests espèces et CB / Cash and card tests
# ===========================================================================


class TestPOSPaiementEspecesCB:
    """Paiements espèces et CB / Cash and card payments."""

    def test_01_deux_paiements_consecutifs_especes_puis_cb(self, page, pos_page, django_shell):
        """Deux paiements consécutifs : espèces (Biere) puis CB (Coca).
        Valide le fix du bug HTMX reset.
        / Two consecutive payments: cash (Biere) then card (Coca).
        Validates the HTMX reset bug fix.
        """
        pos_page(page, "Bar")

        # --- Paiement 1 : Biere par espèces ---
        _add_article_and_validate(page, "Biere")
        _click_valider(page)
        _pay_especes(page)

        success_text = page.locator('[data-testid="paiement-succes"]').inner_text()
        assert "espèce" in success_text.lower(), f"Attendu 'espèce' dans: {success_text[:80]}"

        _retour_caisse(page)

        # --- Paiement 2 : Coca par CB (fix HTMX reset) ---
        _add_article_and_validate(page, "Coca")
        _click_valider(page)
        _pay_cb(page)

        success_text = page.locator('[data-testid="paiement-succes"]').inner_text()
        assert "carte bancaire" in success_text.lower(), f"Attendu 'carte bancaire' dans: {success_text[:80]}"

        _retour_caisse(page)

        # --- Vérification DB : LigneArticle espèces Biere ---
        result_ca = django_shell(
            "from BaseBillet.models import LigneArticle; "
            "from django.utils import timezone; from datetime import timedelta; "
            "now = timezone.now(); "
            "ligne = LigneArticle.objects.filter("
            "datetime__gte=now - timedelta(minutes=10), "
            "payment_method='CA', sale_origin='LB', "
            "pricesold__productsold__product__name='Biere'"
            ").order_by('-datetime').first(); "
            "print(f'pk={str(ligne.pk)[:8]} pm={ligne.payment_method}') if ligne else print('NOT_FOUND')"
        )
        assert "NOT_FOUND" not in result_ca, f"LigneArticle espèces Biere non trouvée: {result_ca}"
        assert "pm=CA" in result_ca

        # --- Vérification DB : LigneArticle CB Coca ---
        result_cc = django_shell(
            "from BaseBillet.models import LigneArticle; "
            "from django.utils import timezone; from datetime import timedelta; "
            "now = timezone.now(); "
            "ligne = LigneArticle.objects.filter("
            "datetime__gte=now - timedelta(minutes=10), "
            "payment_method='CC', sale_origin='LB', "
            "pricesold__productsold__product__name='Coca'"
            ").order_by('-datetime').first(); "
            "print(f'pk={str(ligne.pk)[:8]} pm={ligne.payment_method}') if ligne else print('NOT_FOUND')"
        )
        assert "NOT_FOUND" not in result_cc, f"LigneArticle CB Coca non trouvée: {result_cc}"
        assert "pm=CC" in result_cc

    def test_02_verification_admin_lignearticle(self, page, pos_page, login_as_admin):
        """Vérification admin : LigneArticle visibles dans /admin/.
        / Admin verification: LigneArticle visible in /admin/.
        """
        login_as_admin(page)

        page.goto("/admin/BaseBillet/lignearticle/")
        page.wait_for_load_state("networkidle")

        # Chercher Biere / Search Biere
        search_input = page.locator('input[name="q"]').first
        search_input.fill("Biere")
        search_input.press("Enter")
        page.wait_for_load_state("networkidle")

        rows = page.locator("#result_list tbody tr")
        assert rows.count() >= 1, "Aucune LigneArticle trouvée pour Biere"

        # Chercher Coca / Search Coca
        search_input = page.locator('input[name="q"]').first
        search_input.fill("Coca")
        search_input.press("Enter")
        page.wait_for_load_state("networkidle")

        rows = page.locator("#result_list tbody tr")
        assert rows.count() >= 1, "Aucune LigneArticle trouvée pour Coca"


# ===========================================================================
# Tests NFC cashless / NFC cashless tests
# ===========================================================================


@pytest.fixture(scope="module")
def nfc_setup(django_shell):
    """Setup NFC : asset TLF + wallet CLIENT1 + crédit.
    / NFC setup: TLF asset + CLIENT1 wallet + credit.
    """
    result = django_shell(
        "from AuthBillet.models import Wallet\n"
        "from QrcodeCashless.models import CarteCashless\n"
        "from Customers.models import Client\n"
        "from fedow_core.models import Asset\n"
        "from fedow_core.services import WalletService\n"
        "from django.db import transaction as db_transaction\n"
        "tenant = Client.objects.get(schema_name='lespass')\n"
        "wallet_lieu, _ = Wallet.objects.get_or_create(name='[pw_test] Lieu NFC')\n"
        "Asset.objects.filter(tenant_origin=tenant, category='TLF', active=True).update(active=False)\n"
        "asset_tlf = Asset.objects.filter(name='[pw_test] TestCoin', tenant_origin=tenant).first()\n"
        "if not asset_tlf:\n"
        "    asset_tlf = Asset.objects.create(name='[pw_test] TestCoin', tenant_origin=tenant, category='TLF', currency_code='EUR', wallet_origin=wallet_lieu, active=True)\n"
        "asset_tlf.active = True\n"
        "asset_tlf.wallet_origin = wallet_lieu\n"
        "asset_tlf.save(update_fields=['active', 'wallet_origin'])\n"
        "wallet_client, _ = Wallet.objects.get_or_create(name='[pw_test] Client1 NFC')\n"
        f"carte = CarteCashless.objects.get(tag_id='{DEMO_TAGID_CLIENT1}')\n"
        "carte.wallet_ephemere = wallet_client\n"
        "carte.user = None\n"
        "carte.save(update_fields=['wallet_ephemere', 'user'])\n"
        "with db_transaction.atomic():\n"
        "    WalletService.crediter(wallet=wallet_client, asset=asset_tlf, montant_en_centimes=5000)\n"
        "solde = WalletService.obtenir_solde(wallet=wallet_client, asset=asset_tlf)\n"
        "print(f'SETUP_OK solde={solde}')"
    )
    assert "SETUP_OK" in result, f"NFC setup failed: {result}"
    return result


def _credit_client1(django_shell, montant=5000):
    """Recrédite CLIENT1 pour s'assurer qu'il a assez de solde.
    / Re-credits CLIENT1 to ensure sufficient balance.
    """
    django_shell(
        "from AuthBillet.models import Wallet\n"
        "from Customers.models import Client\n"
        "from fedow_core.models import Asset\n"
        "from fedow_core.services import WalletService\n"
        "from django.db import transaction as db_transaction\n"
        "tenant = Client.objects.get(schema_name='lespass')\n"
        "asset_tlf = Asset.objects.filter(name='[pw_test] TestCoin', tenant_origin=tenant, active=True).first()\n"
        "wallet_client = Wallet.objects.get(name='[pw_test] Client1 NFC')\n"
        "with db_transaction.atomic():\n"
        f"    WalletService.crediter(wallet=wallet_client, asset=asset_tlf, montant_en_centimes={montant})\n"
        "print('CREDIT_OK')"
    )


class TestPOSPaiementNFC:
    """Paiements NFC cashless / NFC cashless payments."""

    def test_03_nfc_solde_suffisant(self, page, pos_page, django_shell, nfc_setup):
        """Paiement NFC avec solde suffisant (CLIENT1).
        / NFC payment with sufficient balance (CLIENT1).
        """
        pos_page(page, "Bar")

        _add_article_and_validate(page, "Biere")
        _click_valider(page)
        _pay_nfc(page, DEMO_TAGID_CLIENT1)

        # Vérifier soldes multi-asset affichés après paiement NFC
        # La refonte cascade affiche des badges multi-asset au lieu d'un solde unique.
        # / Verify multi-asset balances displayed after NFC payment.
        # The cascade refactor shows multi-asset badges instead of a single balance.
        expect(page.locator('[data-testid="soldes-multi-asset"]')).to_be_visible()
        # Au moins 1 badge de solde doit être visible / At least 1 balance badge must be visible
        premier_badge = page.locator('[data-testid="solde-asset-1"]')
        expect(premier_badge).to_be_visible()
        badge_text = premier_badge.inner_text()
        assert "€" in badge_text, f"Badge solde sans '€': {badge_text}"

        _retour_caisse(page)

        # Vérification DB : LigneArticle NFC (LE) / DB check: NFC LigneArticle (LE)
        result = django_shell(
            "from BaseBillet.models import LigneArticle; "
            "from django.utils import timezone; from datetime import timedelta; "
            "now = timezone.now(); "
            "ligne = LigneArticle.objects.filter("
            "datetime__gte=now - timedelta(minutes=5), "
            "payment_method='LE', sale_origin='LB', "
            "pricesold__productsold__product__name='Biere'"
            ").order_by('-datetime').first(); "
            "print(f'pk={str(ligne.pk)[:8]} pm={ligne.payment_method}') if ligne else print('NOT_FOUND')"
        )
        assert "NOT_FOUND" not in result, f"LigneArticle NFC Biere non trouvée: {result}"
        assert "pm=LE" in result

        # Vérification DB : Transaction SALE fedow_core
        result_tx = django_shell(
            "from fedow_core.models import Transaction; "
            "from QrcodeCashless.models import CarteCashless; "
            "from django.utils import timezone; from datetime import timedelta; "
            "now = timezone.now(); "
            f"carte = CarteCashless.objects.get(tag_id='{DEMO_TAGID_CLIENT1}'); "
            "tx = Transaction.objects.filter("
            "action=Transaction.SALE, card=carte, "
            "datetime__gte=now - timedelta(minutes=5)"
            ").order_by('-id').first(); "
            "print(f'tx_id={tx.pk} action={tx.action}') if tx else print('NOT_FOUND')"
        )
        assert "NOT_FOUND" not in result_tx
        assert "action=SAL" in result_tx

    def test_04_nfc_carte_inconnue(self, page, pos_page, nfc_setup):
        """Paiement NFC carte inconnue (CLIENT4 E85C2C6E).
        / NFC payment with unknown card (CLIENT4).
        """
        pos_page(page, "Bar")

        _add_article_and_validate(page, "Biere")
        _click_valider(page)

        page.locator('[data-testid="paiement-moyens"]').get_by_text("CASHLESS").click()
        expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(timeout=10_000)

        page.locator(f'.nfc-reader-simu-bt[tag-id="{DEMO_TAGID_CLIENT4}"]').click()
        expect(page.locator("#messages")).to_contain_text("Carte inconnue", timeout=10_000)

    def test_05_nfc_solde_insuffisant(self, page, pos_page, nfc_setup):
        """Paiement NFC solde insuffisant (CLIENT3 D74B1B5D, solde 0).
        La cascade ne couvre rien → écran complément de paiement.
        / NFC payment with insufficient balance (CLIENT3, balance 0).
        Cascade covers nothing → payment complement screen.
        """
        pos_page(page, "Bar")

        _add_article_and_validate(page, "Biere")
        _click_valider(page)

        page.locator('[data-testid="paiement-moyens"]').get_by_text("CASHLESS").click()
        expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(timeout=10_000)

        page.locator(f'.nfc-reader-simu-bt[tag-id="{DEMO_TAGID_CLIENT3}"]').click()
        # La refonte cascade affiche l'écran complément au lieu de "fonds insuffisants".
        # / The cascade refactor shows the complement screen instead of "insufficient funds".
        expect(page.locator('[data-testid="complement-paiement"]')).to_be_visible(timeout=15_000)
        expect(page.locator('[data-testid="complement-reste-a-payer"]')).to_be_visible()
        expect(page.locator('[data-testid="complement-reste-a-payer"]')).to_contain_text("Reste")

    def test_06_nfc_puis_especes_consecutifs(self, page, pos_page, django_shell, nfc_setup):
        """NFC puis espèces consécutifs (valide reset HTMX NFC→cash).
        / NFC then cash consecutive (validates HTMX NFC→cash reset).
        """
        _credit_client1(django_shell)
        pos_page(page, "Bar")

        # Paiement A : Biere par NFC
        _add_article_and_validate(page, "Biere")
        _click_valider(page)
        _pay_nfc(page, DEMO_TAGID_CLIENT1)
        _retour_caisse(page)

        # Paiement B : Coca par espèces (après reset NFC)
        _add_article_and_validate(page, "Coca")
        _click_valider(page)
        _pay_especes(page)

        success_text = page.locator('[data-testid="paiement-succes"]').inner_text()
        assert "espèce" in success_text.lower(), f"Attendu 'espèce' dans: {success_text[:80]}"
        _retour_caisse(page)

    def test_07_deux_nfc_consecutifs(self, page, pos_page, django_shell, nfc_setup):
        """Deux paiements NFC consécutifs (valide reset NFC→NFC).
        / Two consecutive NFC payments (validates NFC→NFC reset).
        """
        _credit_client1(django_shell)
        pos_page(page, "Bar")

        # Paiement A : Eau par NFC
        _add_article_and_validate(page, "Eau")
        _click_valider(page)
        _pay_nfc(page, DEMO_TAGID_CLIENT1)
        _retour_caisse(page)

        # Paiement B : Coca par NFC (après reset NFC)
        _add_article_and_validate(page, "Coca")
        _click_valider(page)
        _pay_nfc(page, DEMO_TAGID_CLIENT1)

        page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click()
        expect(page.locator('[data-testid="paiement-succes"]')).not_to_be_visible(timeout=5_000)

        # Vérification DB : au moins 2 transactions récentes
        result = django_shell(
            "from fedow_core.models import Transaction; "
            "from QrcodeCashless.models import CarteCashless; "
            "from django.utils import timezone; from datetime import timedelta; "
            "now = timezone.now(); "
            f"carte = CarteCashless.objects.get(tag_id='{DEMO_TAGID_CLIENT1}'); "
            "txs = Transaction.objects.filter("
            "action=Transaction.SALE, card=carte, "
            "datetime__gte=now - timedelta(minutes=3)"
            ").order_by('-id'); "
            "print(f'tx_count={txs.count()}')"
        )
        count_match = re.search(r"tx_count=(\d+)", result)
        assert count_match, f"Pas de tx_count dans: {result}"
        assert int(count_match.group(1)) >= 2, f"Attendu >= 2 transactions, trouvé {count_match.group(1)}"

    def test_08_nfc_multi_articles_solde_exact(self, page, pos_page, django_shell, nfc_setup):
        """NFC multi-articles : Chips + Cacahuetes = 3.50€, vérifie solde exact.
        / NFC multi-item: Chips + Cacahuetes = 3.50€, verifies exact balance.
        """
        # Recréditer et noter le solde avant / Re-credit and note balance before
        solde_avant_result = django_shell(
            "from AuthBillet.models import Wallet\n"
            "from Customers.models import Client\n"
            "from fedow_core.models import Asset\n"
            "from fedow_core.services import WalletService\n"
            "from django.db import transaction as db_transaction\n"
            "tenant = Client.objects.get(schema_name='lespass')\n"
            "asset_tlf = Asset.objects.filter(name='[pw_test] TestCoin', tenant_origin=tenant, active=True).first()\n"
            "wallet_client = Wallet.objects.get(name='[pw_test] Client1 NFC')\n"
            "with db_transaction.atomic():\n"
            "    WalletService.crediter(wallet=wallet_client, asset=asset_tlf, montant_en_centimes=5000)\n"
            "solde = WalletService.obtenir_solde(wallet=wallet_client, asset=asset_tlf)\n"
            "print(f'SOLDE_AVANT={solde}')"
        )
        solde_avant_match = re.search(r"SOLDE_AVANT=(\d+)", solde_avant_result)
        assert solde_avant_match, f"Pas de SOLDE_AVANT dans: {solde_avant_result}"
        solde_avant = int(solde_avant_match.group(1))

        pos_page(page, "Bar")

        # Ajouter Chips + Cacahuetes / Add Chips + Cacahuetes
        tile_chips = page.locator("#products .article-container").filter(has_text="Chips").first
        expect(tile_chips).to_be_visible(timeout=10_000)
        tile_chips.click()
        expect(page.locator("#addition-list")).to_contain_text("Chips", timeout=5_000)

        tile_caca = page.locator("#products .article-container").filter(has_text="Cacahuetes").first
        expect(tile_caca).to_be_visible(timeout=5_000)
        tile_caca.click()
        expect(page.locator("#addition-list")).to_contain_text("Cacahuetes", timeout=5_000)

        # Payer par NFC / Pay via NFC
        _click_valider(page)
        _pay_nfc(page, DEMO_TAGID_CLIENT1)
        # Vérifier soldes multi-asset après paiement NFC
        # / Verify multi-asset balances after NFC payment
        expect(page.locator('[data-testid="soldes-multi-asset"]')).to_be_visible()
        expect(page.locator('[data-testid="solde-asset-1"]')).to_be_visible()

        _retour_caisse(page)

        # Vérifier solde exact : diminution de 350 centimes (2€ + 1.50€)
        solde_apres_result = django_shell(
            "from AuthBillet.models import Wallet; "
            "from Customers.models import Client; "
            "from fedow_core.models import Asset; "
            "from fedow_core.services import WalletService; "
            "tenant = Client.objects.get(schema_name='lespass'); "
            "asset_tlf = Asset.objects.filter(name='[pw_test] TestCoin', tenant_origin=tenant, active=True).first(); "
            "wallet_client = Wallet.objects.get(name='[pw_test] Client1 NFC'); "
            "solde = WalletService.obtenir_solde(wallet=wallet_client, asset=asset_tlf); "
            "print(f'SOLDE_APRES={solde}')"
        )
        solde_apres_match = re.search(r"SOLDE_APRES=(\d+)", solde_apres_result)
        assert solde_apres_match, f"Pas de SOLDE_APRES dans: {solde_apres_result}"
        solde_apres = int(solde_apres_match.group(1))

        difference = solde_avant - solde_apres
        assert difference == 350, (
            f"Solde avant={solde_avant}c, après={solde_apres}c, "
            f"diff={difference}c, attendu=350c"
        )
