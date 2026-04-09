"""
Tests E2E : flow recharge cashless complet.
/ E2E tests: full cashless top-up flow.

Teste le flow complet de recharge sur le PV Cashless :
1. Les produits de recharge apparaissent dans la grille (asset-first)
2. Recharge especes sur une carte NFC → solde augmente en DB
3. Verification solde via django_shell
4. Vente NFC apres recharge → solde diminue

Prerequis / Prerequisites:
- docker exec lespass_django poetry run python manage.py create_test_pos_data
- Assets TLF/TNF/TIM crees par create_test_pos_data (signal post_save)
- Cartes NFC de simulation (DEMO=1)
- Serveur Django actif via Traefik

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/e2e/test_pos_recharge_cashless.py -v -s --tb=short
"""

import os
import re

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e

DEMO_TAGID_CM = os.environ.get("DEMO_TAGID_CM", "A49E8E2A")
DEMO_TAGID_CLIENT1 = os.environ.get("DEMO_TAGID_CLIENT1", "52BE6543")


# ---------------------------------------------------------------------------
# Fixture : s'assurer qu'un asset TLF actif existe et que CLIENT1 a un wallet
# / Fixture: ensure an active TLF asset exists and CLIENT1 has a wallet
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def recharge_setup(django_shell):
    """Setup par test (scope=function, pas module) car d'autres tests/processus
    peuvent modifier les assets TLF entre les tests.
    - Desactive TOUS les assets TLF
    - Active uniquement 'Monnaie locale'
    - Cree/recupere un wallet pour CLIENT1
    - Lie la carte CLIENT1 au wallet
    - Remet le solde a 0 pour un etat initial propre

    / Per-test setup (scope=function, not module) because other tests/processes
    may modify TLF assets between tests.
    - Deactivates ALL TLF assets
    - Activates only 'Monnaie locale'
    - Creates/gets a wallet for CLIENT1
    - Links CLIENT1 card to the wallet
    - Resets balance to 0 for a clean initial state
    """
    result = django_shell(
        "from AuthBillet.models import Wallet\n"
        "from QrcodeCashless.models import CarteCashless\n"
        "from Customers.models import Client\n"
        "from fedow_core.models import Asset, Token\n"
        "from django.db import connection\n"
        "tenant = Client.objects.get(schema_name=connection.schema_name)\n"
        "# Desactiver TOUS les assets TLF pour eviter les conflits avec d'autres tests\n"
        "# / Deactivate ALL TLF assets to avoid conflicts with other tests\n"
        "Asset.objects.filter(tenant_origin=tenant, category='TLF').update(active=False)\n"
        "# Activer uniquement 'Monnaie locale' (cree par create_test_pos_data)\n"
        "# / Activate only 'Monnaie locale' (created by create_test_pos_data)\n"
        "asset_tlf = Asset.objects.filter(\n"
        "    tenant_origin=tenant, category='TLF', name='Monnaie locale'\n"
        ").first()\n"
        "if not asset_tlf:\n"
        "    print('NO_TLF_MONNAIE_LOCALE')\n"
        "    import sys; sys.exit(1)\n"
        "asset_tlf.active = True\n"
        "asset_tlf.save(update_fields=['active'])\n"
        "# Wallet pour CLIENT1 / Wallet for CLIENT1\n"
        "wallet_client, _ = Wallet.objects.get_or_create(\n"
        "    name='[e2e_recharge] Client1'\n"
        ")\n"
        f"carte = CarteCashless.objects.get(tag_id='{DEMO_TAGID_CLIENT1}')\n"
        "carte.wallet_ephemere = wallet_client\n"
        "carte.user = None\n"
        "carte.save(update_fields=['wallet_ephemere', 'user'])\n"
        "# Remettre le solde a 0 / Reset balance to 0\n"
        "Token.objects.filter(wallet=wallet_client, asset=asset_tlf).delete()\n"
        "print(f'SETUP_OK asset={asset_tlf.name} wallet={wallet_client.name}')"
    )
    assert "SETUP_OK" in result, f"recharge_setup failed: {result}"
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_article_and_validate(page, article_name):
    """Clic tuile article → verif addition → clic VALIDER.
    / Click article tile → verify addition → click VALIDER.
    """
    tile = page.locator("#products .article-container").filter(
        has_text=article_name
    ).first
    expect(tile).to_be_visible(timeout=10_000)
    tile.click()
    expect(page.locator("#addition-list")).to_contain_text(
        article_name, timeout=10_000
    )


def _click_valider(page):
    """Clic VALIDER → panneau moyens de paiement/identification visible.
    / Click VALIDER → payment/identification panel visible.
    """
    page.locator("#bt-valider").click()
    expect(page.locator('[data-testid="paiement-moyens"]')).to_be_visible(
        timeout=10_000
    )


def _scan_nfc_client(page, tag_id):
    """Clic "Scanner carte" → attend boutons NFC → clic carte.
    / Click "Scanner carte" → wait for NFC buttons → click card.
    """
    page.locator('[data-testid="client-choose-nfc"]').click()
    expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(
        timeout=10_000
    )
    page.locator(f'.nfc-reader-simu-bt[tag-id="{tag_id}"]').click()


def _pay_especes_via_recap(page):
    """Clic bouton especes dans le recapitulatif client → succes.
    / Click cash button in client recap → success.
    """
    page.locator('[data-testid="client-btn-especes"]').click()
    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(
        timeout=15_000
    )


def _pay_nfc(page, tag_id):
    """Choisir CASHLESS → cliquer carte NFC simulation → succes.
    / Choose CASHLESS → click NFC simulation card → success.
    """
    page.locator('[data-testid="paiement-moyens"]').get_by_text("CASHLESS").click()
    expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(
        timeout=10_000
    )
    page.locator(f'.nfc-reader-simu-bt[tag-id="{tag_id}"]').click()
    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(
        timeout=15_000
    )


def _retour_caisse(page):
    """Clic RETOUR dans l'ecran de succes → panier vide.
    / Click RETOUR in success screen → empty cart.
    """
    page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click()
    expect(page.locator('[data-testid="paiement-succes"]')).not_to_be_visible(
        timeout=10_000
    )


def _get_solde_client1(django_shell):
    """Recupere le solde TLF de CLIENT1 en centimes via django_shell.
    / Gets CLIENT1's TLF balance in cents via django_shell.
    """
    result = django_shell(
        "from AuthBillet.models import Wallet\n"
        "from Customers.models import Client\n"
        "from fedow_core.models import Asset\n"
        "from fedow_core.services import WalletService\n"
        "from django.db import connection\n"
        "tenant = Client.objects.get(schema_name=connection.schema_name)\n"
        "asset_tlf = Asset.objects.filter(\n"
        "    tenant_origin=tenant, category='TLF', active=True\n"
        ").first()\n"
        "wallet = Wallet.objects.get(name='[e2e_recharge] Client1')\n"
        "solde = WalletService.obtenir_solde(wallet=wallet, asset=asset_tlf)\n"
        "print(f'SOLDE={solde}')"
    )
    match = re.search(r"SOLDE=(\d+)", result)
    assert match, f"Pas de SOLDE dans: {result}"
    return int(match.group(1))


# ===========================================================================
# Test 1 : Les produits de recharge apparaissent dans le PV Cashless
# / Test 1: Top-up products appear in the Cashless POS
# ===========================================================================


class TestPOSRechargeCashless:
    """Flow recharge cashless complet.
    / Full cashless top-up flow.
    """

    def test_01_produits_recharge_visibles_dans_pv_cashless(
        self, page, pos_page, recharge_setup,
    ):
        """Le PV Cashless affiche les produits de recharge avec au moins 3 tarifs.
        Le signal post_save Asset cree 4 tarifs (1, 5, 10, Libre).
        / Cashless POS displays top-up products with at least 3 rates.
        The Asset post_save signal creates 4 rates (1, 5, 10, Free).
        """
        pos_page(page, "Cashless")

        # Au moins un article avec "Recharge" dans le nom
        # / At least one article with "Recharge" in the name
        recharge_tiles = page.locator("#products .article-container").filter(
            has_text="Recharge"
        )
        expect(recharge_tiles.first).to_be_visible(timeout=10_000)
        nombre_recharges = recharge_tiles.count()
        assert nombre_recharges >= 1, (
            f"Attendu >= 1 tuile recharge, trouve {nombre_recharges}"
        )

        # Cliquer la tuile recharge pour ouvrir l'overlay multi-tarif
        # / Click the top-up tile to open the multi-rate overlay
        recharge_tiles.first.click()
        expect(page.locator('[data-testid="tarif-overlay"]')).to_be_visible(
            timeout=10_000
        )

        # Verifier au moins 3 boutons de tarif fixe (1, 5, 10)
        # Le 4eme tarif "Libre" est un bouton prix libre, pas fixe.
        # / Verify at least 3 fixed rate buttons (1, 5, 10).
        # The 4th rate "Libre" is a free-price button, not fixed.
        tarif_buttons = page.locator(
            '[data-testid="tarif-overlay"] .tarif-btn-fixed'
        )
        nombre_tarifs = tarif_buttons.count()
        assert nombre_tarifs >= 3, (
            f"Attendu >= 3 tarifs fixes, trouve {nombre_tarifs}"
        )

        # Verifier qu'il y a aussi un tarif prix libre
        # / Verify there's also a free-price rate
        tarif_libre = page.locator(
            '[data-testid="tarif-overlay"] .tarif-btn-free'
        )
        assert tarif_libre.count() >= 1, "Tarif prix libre absent"

    # ===========================================================================
    # Test 2 : Recharge especes sur une carte NFC
    # / Test 2: Cash top-up on an NFC card
    # ===========================================================================

    def test_02_recharge_especes_nfc(
        self, page, pos_page, django_shell, recharge_setup,
    ):
        """Recharge 10EUR en especes sur la carte CLIENT1.
        Flow : tuile Recharge → tarif 10 → VALIDER → identification NFC →
        scan CLIENT1 → recapitulatif → especes → succes.
        Verifie en DB que le solde a augmente de 1000 centimes.
        / Top-up 10EUR cash on CLIENT1 card.
        Flow: Recharge tile → rate 10 → VALIDER → NFC identification →
        scan CLIENT1 → recap → cash → success.
        DB check: balance increased by 1000 cents.
        """
        # Solde avant la recharge / Balance before top-up
        solde_avant = _get_solde_client1(django_shell)

        # Ouvrir le PV Cashless / Open Cashless POS
        pos_page(page, "Cashless")

        # Cliquer la tuile recharge → overlay multi-tarif
        # / Click top-up tile → multi-rate overlay
        recharge_tile = page.locator("#products .article-container").filter(
            has_text="Recharge"
        ).first
        expect(recharge_tile).to_be_visible(timeout=10_000)
        recharge_tile.click()
        expect(page.locator('[data-testid="tarif-overlay"]')).to_be_visible(
            timeout=10_000
        )

        # Cliquer le tarif "10" (10EUR) / Click the "10" rate (10EUR)
        # Les tarifs fixes ont la classe .tarif-btn-fixed, le label contient le nom du tarif.
        # / Fixed rates have .tarif-btn-fixed class, label contains rate name.
        tarif_10 = page.locator(
            '[data-testid="tarif-overlay"] .tarif-btn-fixed'
        ).filter(has_text="10")
        expect(tarif_10.first).to_be_visible(timeout=5_000)
        tarif_10.first.click()

        # Verifier que l'article est dans le panier / Verify article in cart
        expect(page.locator("#addition-list")).to_contain_text("10", timeout=10_000)

        # Fermer l'overlay / Close overlay
        page.locator('[data-testid="tarif-btn-retour"]').click()
        expect(page.locator('[data-testid="tarif-overlay"]')).not_to_be_visible(
            timeout=5_000
        )

        # VALIDER → ecran identification NFC (recharge → NFC obligatoire)
        # / VALIDER → NFC identification screen (top-up → NFC required)
        _click_valider(page)

        # Seul "Scanner carte" est disponible (pas "Saisir email")
        # / Only "Scanner carte" available (not "Saisir email")
        expect(page.locator('[data-testid="client-choose-nfc"]')).to_be_visible(
            timeout=10_000
        )

        # Scanner la carte CLIENT1 / Scan CLIENT1 card
        _scan_nfc_client(page, DEMO_TAGID_CLIENT1)

        # Recapitulatif → paiement especes
        # / Recap → cash payment
        expect(page.locator('[data-testid="client-recapitulatif"]')).to_be_visible(
            timeout=10_000
        )
        _pay_especes_via_recap(page)

        # Verifier le succes / Verify success
        success_text = page.locator(
            '[data-testid="paiement-succes"]'
        ).inner_text()
        assert "10" in success_text, (
            f"Attendu '10' dans le succes: {success_text[:120]}"
        )

        _retour_caisse(page)

        # Verification DB : solde augmente de 1000 centimes
        # / DB check: balance increased by 1000 cents
        solde_apres = _get_solde_client1(django_shell)
        difference = solde_apres - solde_avant
        assert difference == 1000, (
            f"Solde avant={solde_avant}c, apres={solde_apres}c, "
            f"diff={difference}c, attendu=1000c"
        )

    # ===========================================================================
    # Test 3 : Recharge + verification solde en DB (test autonome)
    # / Test 3: Top-up + DB balance verification (standalone test)
    # ===========================================================================

    def test_03_recharge_et_verification_solde_en_db(
        self, page, pos_page, django_shell, recharge_setup,
    ):
        """Recharge 5EUR → verifie en DB que le solde est passe de 0 a 500c.
        Test autonome, ne depend pas du test_02.
        / Top-up 5EUR → DB check that balance went from 0 to 500c.
        Standalone test, does not depend on test_02.
        """
        # Solde initial = 0 (reset par la fixture) / Initial balance = 0 (reset by fixture)
        solde_avant = _get_solde_client1(django_shell)
        assert solde_avant == 0, f"Solde initial attendu 0, trouve {solde_avant}c"

        # Ouvrir PV Cashless / Open Cashless POS
        pos_page(page, "Cashless")

        # Cliquer la tuile recharge → overlay → tarif 5 → fermer
        # / Click top-up tile → overlay → rate 5 → close
        recharge_tile = page.locator("#products .article-container").filter(
            has_text="Recharge"
        ).first
        expect(recharge_tile).to_be_visible(timeout=10_000)
        recharge_tile.click()
        expect(page.locator('[data-testid="tarif-overlay"]')).to_be_visible(
            timeout=10_000
        )
        tarif_5 = page.locator(
            '[data-testid="tarif-overlay"] .tarif-btn-fixed'
        ).filter(has_text="5")
        tarif_5.first.click()
        expect(page.locator("#addition-list")).to_contain_text("5", timeout=10_000)
        page.locator('[data-testid="tarif-btn-retour"]').click()

        # VALIDER → NFC → scan CLIENT1 → recap → especes → succes
        # / VALIDER → NFC → scan CLIENT1 → recap → cash → success
        _click_valider(page)
        _scan_nfc_client(page, DEMO_TAGID_CLIENT1)
        expect(page.locator('[data-testid="client-recapitulatif"]')).to_be_visible(
            timeout=10_000
        )
        _pay_especes_via_recap(page)
        _retour_caisse(page)

        # Verification DB : solde = 500c / DB check: balance = 500c
        solde_apres = _get_solde_client1(django_shell)
        assert solde_apres == 500, (
            f"Solde attendu 500c apres recharge 5EUR, trouve {solde_apres}c"
        )

    # ===========================================================================
    # Test 4 : Vente NFC apres recharge
    # / Test 4: NFC sale after top-up
    # ===========================================================================

    def test_04_vente_nfc_apres_recharge(
        self, page, pos_page, django_shell, recharge_setup,
    ):
        """Vente d'une Biere par NFC apres recharge → solde diminue.
        Verifie en DB : LigneArticle avec payment_method=LE et Transaction SALE.
        / Beer sale via NFC after top-up → balance decreases.
        DB check: LigneArticle with payment_method=LE and SALE Transaction.
        """
        # Crediter le wallet pour la vente NFC.
        # La fixture recharge_setup (scope=function) a deja desactive les TLF
        # parasites et remis le solde a 0. On credite ici 5000c.
        # / Credit the wallet for the NFC sale.
        # The recharge_setup fixture (scope=function) already deactivated
        # parasitic TLFs and reset the balance to 0. We credit 5000c here.
        django_shell(
            "from AuthBillet.models import Wallet\n"
            "from Customers.models import Client\n"
            "from fedow_core.models import Asset\n"
            "from fedow_core.services import WalletService\n"
            "from django.db import connection, transaction as db_tx\n"
            "tenant = Client.objects.get(schema_name=connection.schema_name)\n"
            "# Guard : desactiver les TLF parasites (processus concurrents)\n"
            "# / Guard: deactivate parasitic TLFs (concurrent processes)\n"
            "Asset.objects.filter(\n"
            "    tenant_origin=tenant, category='TLF'\n"
            ").exclude(name='Monnaie locale').update(active=False)\n"
            "asset_tlf = Asset.objects.get(\n"
            "    tenant_origin=tenant, category='TLF', name='Monnaie locale'\n"
            ")\n"
            "wallet = Wallet.objects.get(name='[e2e_recharge] Client1')\n"
            "with db_tx.atomic():\n"
            "    WalletService.crediter(\n"
            "        wallet=wallet, asset=asset_tlf, montant_en_centimes=5000\n"
            "    )\n"
            "print('CREDIT_OK')"
        )

        # Solde avant la vente / Balance before sale
        solde_avant = _get_solde_client1(django_shell)
        assert solde_avant >= 500, (
            f"Solde insuffisant pour acheter une Biere (500c) : {solde_avant}c"
        )

        # Ouvrir le PV Bar / Open Bar POS
        pos_page(page, "Bar")

        # Ajouter une Biere / Add a Beer
        _add_article_and_validate(page, "Biere")

        # VALIDER → paiement NFC / VALIDER → NFC payment
        page.locator("#bt-valider").click()
        expect(page.locator('[data-testid="paiement-moyens"]')).to_be_visible(
            timeout=10_000
        )
        _pay_nfc(page, DEMO_TAGID_CLIENT1)

        # Verifier soldes multi-asset affiches
        # / Verify multi-asset balances displayed
        expect(page.locator('[data-testid="soldes-multi-asset"]')).to_be_visible(
            timeout=10_000
        )

        _retour_caisse(page)

        # Verification DB : solde diminue de 500 centimes (Biere = 5EUR)
        # / DB check: balance decreased by 500 cents (Beer = 5EUR)
        solde_apres = _get_solde_client1(django_shell)
        difference = solde_avant - solde_apres
        assert difference == 500, (
            f"Solde avant={solde_avant}c, apres={solde_apres}c, "
            f"diff={difference}c, attendu=500c (Biere)"
        )

        # Verification DB : LigneArticle NFC (LE) pour Biere
        # / DB check: NFC LigneArticle (LE) for Beer
        result_ligne = django_shell(
            "from BaseBillet.models import LigneArticle\n"
            "from django.utils import timezone\n"
            "from datetime import timedelta\n"
            "now = timezone.now()\n"
            "ligne = LigneArticle.objects.filter(\n"
            "    datetime__gte=now - timedelta(minutes=5),\n"
            "    payment_method='LE', sale_origin='LB',\n"
            "    pricesold__productsold__product__name='Biere'\n"
            ").order_by('-datetime').first()\n"
            "print(f'pk={str(ligne.pk)[:8]} pm={ligne.payment_method}') "
            "if ligne else print('NOT_FOUND')"
        )
        assert "NOT_FOUND" not in result_ligne, (
            f"LigneArticle NFC Biere non trouvee: {result_ligne}"
        )
        assert "pm=LE" in result_ligne

        # Verification DB : Transaction SALE fedow_core
        # / DB check: fedow_core SALE Transaction
        result_tx = django_shell(
            "from fedow_core.models import Transaction\n"
            "from QrcodeCashless.models import CarteCashless\n"
            "from django.utils import timezone\n"
            "from datetime import timedelta\n"
            "now = timezone.now()\n"
            f"carte = CarteCashless.objects.get(tag_id='{DEMO_TAGID_CLIENT1}')\n"
            "tx = Transaction.objects.filter(\n"
            "    action=Transaction.SALE, card=carte,\n"
            "    datetime__gte=now - timedelta(minutes=5)\n"
            ").order_by('-id').first()\n"
            "print(f'tx_id={tx.pk} action={tx.action}') "
            "if tx else print('NOT_FOUND')"
        )
        assert "NOT_FOUND" not in result_tx, (
            f"Transaction SALE non trouvee: {result_tx}"
        )
        assert "action=SAL" in result_tx
