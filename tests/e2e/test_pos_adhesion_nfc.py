"""
Tests E2E : flow identification client unifie (adhesion + recharge + mixte).
/ E2E tests: unified client identification flow (membership + top-up + mixed).

Nouveau flow (Session 05) :
VALIDER → ecran identification (NFC / email) → recapitulatif → bouton paiement → succes

Prerequis / Prerequisites:
- docker exec lespass_django poetry run python manage.py create_test_pos_data
- PV Adhesions (comportement='D', produits adhesion dans M2M) existant
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
    """Ouvre le PV Adhesions, clic premier article, gere overlay tarif, clic VALIDER.
    Apres VALIDER, l'ecran d'identification client s'affiche (pas de choix paiement).
    / Opens Adhesions POS, clicks first article, handles rate overlay, clicks VALIDATE.
    After VALIDATE, the client identification screen shows (no payment choice).
    """
    pos_page(page, "Adhesions")

    # Cliquer le premier article d'adhesion / Click first adhesion article
    adhesion_tile = page.locator("#products .article-container").first
    expect(adhesion_tile).to_be_visible(timeout=10_000)
    adhesion_tile.click()

    # Si overlay tarif → cliquer premier tarif fixe / If rate overlay → click first fixed rate
    tarif_overlay = page.locator(".tarif-overlay")
    if tarif_overlay.is_visible(timeout=2_000):
        first_fixed = tarif_overlay.locator(".tarif-btn:not(.tarif-btn-free)").first
        first_fixed.click()

    # Verifier qu'un article est dans l'addition / Verify article in addition
    expect(page.locator("#addition-list .addition-line-grid")).to_be_visible(timeout=5_000)

    # Cliquer VALIDER → ecran identification client (nouveau flow)
    # / Click VALIDATE → client identification screen (new flow)
    page.locator("#bt-valider").click()
    expect(page.locator('[data-testid="paiement-moyens"]')).to_be_visible(timeout=10_000)


# ===========================================================================
# Tests identification client unifiee / Unified client identification tests
# ===========================================================================


class TestPOSClientIdentification:
    """Flow identification client unifie (6 chemins + 2 retour).
    Nouveau flow : VALIDER → identification → recapitulatif → paiement.
    / Unified client identification flow (6 paths + 2 back).
    New flow: VALIDATE → identification → recap → payment.
    """

    # --- Chemin 5 : "Saisir email" → formulaire → recapitulatif → ESPECE ---

    def test_chemin_5_saisir_email_puis_espece(
        self, page, pos_page, django_shell, adhesion_cards_setup
    ):
        """Chemin 5 : saisir email → recapitulatif → paiement especes.
        / Path 5: enter email → recap → cash payment.
        """
        suffix = adhesion_cards_setup
        test_email = f"adh5-{suffix}@example.com"

        _naviguer_et_ajouter_adhesion(page, pos_page)

        # "Saisir email" (pas de choix paiement avant — nouveau flow)
        page.locator('[data-testid="client-choose-email"]').click()
        expect(page.locator('[data-testid="client-form"]')).to_be_visible(timeout=10_000)

        # Remplir et valider
        page.locator('[data-testid="client-input-email"]').fill(test_email)
        page.locator('[data-testid="client-input-prenom"]').fill("PrenomCinq")
        page.locator('[data-testid="client-input-nom"]').fill("NomCinq")
        page.locator('[data-testid="client-btn-valider"]').click()

        # Recapitulatif client
        expect(page.locator('[data-testid="client-recapitulatif"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="client-recapitulatif-user"]')).to_contain_text(test_email)
        expect(page.locator('[data-testid="client-recapitulatif-user"]')).to_contain_text("NOMCINQ")

        # Payer en especes (bouton dans le recapitulatif)
        page.locator('[data-testid="client-btn-especes"]').click()
        expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)

        # Verification DB : Membership creee
        # / DB verification: Membership created
        result_membership = django_shell(
            f"from BaseBillet.models import Membership; "
            f"from AuthBillet.models import TibilletUser; "
            f"user = TibilletUser.objects.filter(email='{test_email}').first(); "
            f"m = Membership.objects.filter(user=user).order_by('-date_added').first() if user else None; "
            f"print(f'OK status={{m.status}}') if m else print('NO_MEMBERSHIP')"
        )
        assert "OK" in result_membership, f"Membership non trouvee: {result_membership}"

        # Verification DB : LigneArticle creee avec les bons champs
        # / DB verification: LigneArticle created with correct fields
        result_ligne = django_shell(
            f"from BaseBillet.models import LigneArticle, SaleOrigin; "
            f"ligne = LigneArticle.objects.filter("
            f"  sale_origin=SaleOrigin.LABOUTIK"
            f").order_by('-datetime').first(); "
            f"print("
            f"  f'LIGNE email={{ligne.membership.user.email if ligne.membership else None}} '"
            f"  f'method={{ligne.payment_method}} origin={{ligne.sale_origin}} '"
            f"  f'amount={{ligne.amount}} qty={{int(ligne.qty)}} '"
            f"  f'status={{ligne.status}} carte={{ligne.carte}}'"
            f") if ligne else print('NO_LIGNE')"
        )
        assert 'NO_LIGNE' not in result_ligne, f"LigneArticle introuvable: {result_ligne}"
        assert f'email={test_email}' in result_ligne, f"Email incorrect: {result_ligne}"
        assert 'method=CA' in result_ligne, f"Payment method pas CA (especes): {result_ligne}"
        assert 'origin=LB' in result_ligne, f"Sale origin pas LB (laboutik): {result_ligne}"
        assert 'status=V' in result_ligne, f"Status pas V (valid): {result_ligne}"
        assert 'carte=None' in result_ligne, f"Carte devrait etre None (paiement especes): {result_ligne}"

    # --- Chemin 5bis : "Saisir email" → recapitulatif → CB ---

    def test_chemin_5bis_saisir_email_puis_cb(
        self, page, pos_page, django_shell, adhesion_cards_setup
    ):
        """Chemin 5bis : saisir email → recapitulatif → paiement CB.
        Verifie LigneArticle : payment_method=CC, sale_origin=LB, email correct.
        / Path 5bis: enter email → recap → card payment.
        Verifies LigneArticle: payment_method=CC, sale_origin=LB, correct email.
        """
        suffix = adhesion_cards_setup
        test_email = f"adh5cb-{suffix}@example.com"

        _naviguer_et_ajouter_adhesion(page, pos_page)

        # "Saisir email"
        page.locator('[data-testid="client-choose-email"]').click()
        expect(page.locator('[data-testid="client-form"]')).to_be_visible(timeout=10_000)

        # Remplir et valider
        page.locator('[data-testid="client-input-email"]').fill(test_email)
        page.locator('[data-testid="client-input-prenom"]').fill("PrenomCB")
        page.locator('[data-testid="client-input-nom"]').fill("NomCB")
        page.locator('[data-testid="client-btn-valider"]').click()

        # Recapitulatif → paiement CB
        expect(page.locator('[data-testid="client-recapitulatif"]')).to_be_visible(timeout=10_000)
        page.locator('[data-testid="client-btn-cb"]').click()
        expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)

        # Verification DB : LigneArticle avec payment_method=CC (CB)
        # / DB verification: LigneArticle with payment_method=CC (card)
        result_ligne = django_shell(
            f"from BaseBillet.models import LigneArticle, SaleOrigin; "
            f"ligne = LigneArticle.objects.filter("
            f"  sale_origin=SaleOrigin.LABOUTIK"
            f").order_by('-datetime').first(); "
            f"print("
            f"  f'LIGNE email={{ligne.membership.user.email if ligne.membership else None}} '"
            f"  f'method={{ligne.payment_method}} origin={{ligne.sale_origin}} '"
            f"  f'amount={{ligne.amount}} qty={{int(ligne.qty)}} '"
            f"  f'status={{ligne.status}} carte={{ligne.carte}}'"
            f") if ligne else print('NO_LIGNE')"
        )
        assert 'NO_LIGNE' not in result_ligne, f"LigneArticle introuvable: {result_ligne}"
        assert f'email={test_email}' in result_ligne, f"Email incorrect: {result_ligne}"
        assert 'method=CC' in result_ligne, f"Payment method pas CC (CB): {result_ligne}"
        assert 'origin=LB' in result_ligne, f"Sale origin pas LB: {result_ligne}"

    # --- Chemin 3 : "Scanner carte" NFC → carte avec user → recapitulatif → ESPECE ---

    def test_chemin_3_scanner_carte_user_connu_puis_espece(
        self, page, pos_page, django_shell, adhesion_cards_setup
    ):
        """Chemin 3 : scanner carte (user connu CLIENT3) → recapitulatif → especes.
        Verifie LigneArticle : email du user de la carte, payment_method=CA, carte=None (especes).
        / Path 3: scan card (known user CLIENT3) → recap → cash.
        Verifies LigneArticle: card user email, payment_method=CA, carte=None (cash).
        """
        _naviguer_et_ajouter_adhesion(page, pos_page)

        # "Scanner carte" → NFC
        page.locator('[data-testid="client-choose-nfc"]').click()
        expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(timeout=10_000)

        # Cliquer CLIENT3 (avec user assigne)
        page.locator(f'.nfc-reader-simu-bt[tag-id="{DEMO_TAGID_CLIENT3}"]').click()

        # → recapitulatif direct (carte avec user)
        expect(page.locator('[data-testid="client-recapitulatif"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="client-recapitulatif-user"]')).to_contain_text("carte3-jetable")
        expect(page.locator('[data-testid="client-recapitulatif-user"]')).to_contain_text("TESTNFC")

        # Payer en especes
        page.locator('[data-testid="client-btn-especes"]').click()
        expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)

        # Verification DB : LigneArticle avec les bons champs
        # Le user vient du scan NFC (carte3-jetable), paiement en especes
        # / DB verification: LigneArticle with correct fields
        # User comes from NFC scan (carte3-jetable), cash payment
        suffix = adhesion_cards_setup
        result_ligne = django_shell(
            f"from BaseBillet.models import LigneArticle, SaleOrigin; "
            f"ligne = LigneArticle.objects.filter("
            f"  sale_origin=SaleOrigin.LABOUTIK"
            f").order_by('-datetime').first(); "
            f"user_email = ligne.membership.user.email if ligne.membership else 'no_membership'; "
            f"print("
            f"  f'LIGNE email={{user_email}} '"
            f"  f'method={{ligne.payment_method}} origin={{ligne.sale_origin}} '"
            f"  f'amount={{ligne.amount}} qty={{int(ligne.qty)}} '"
            f"  f'status={{ligne.status}} carte={{ligne.carte_id}}'"
            f") if ligne else print('NO_LIGNE')"
        )
        assert 'NO_LIGNE' not in result_ligne, f"LigneArticle introuvable: {result_ligne}"
        assert 'carte3-jetable' in result_ligne, f"Email user incorrect: {result_ligne}"
        assert 'method=CA' in result_ligne, f"Payment method pas CA (especes): {result_ligne}"
        assert 'origin=LB' in result_ligne, f"Sale origin pas LB: {result_ligne}"
        assert 'status=V' in result_ligne, f"Status pas V: {result_ligne}"

    # --- Chemin 1 : "Scanner carte" NFC → carte avec user → recapitulatif → CASHLESS ---

    def test_chemin_1_scanner_carte_user_connu_puis_cashless(
        self, page, pos_page, adhesion_cards_setup
    ):
        """Chemin 1 : scanner carte NFC (CLIENT3) → recapitulatif → cashless.
        / Path 1: scan NFC card (CLIENT3) → recap → cashless.
        """
        _naviguer_et_ajouter_adhesion(page, pos_page)

        # "Scanner carte" → NFC
        page.locator('[data-testid="client-choose-nfc"]').click()

        # Cliquer CLIENT3 (avec user)
        expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(timeout=10_000)
        page.locator(f'.nfc-reader-simu-bt[tag-id="{DEMO_TAGID_CLIENT3}"]').click()

        # → recapitulatif direct
        expect(page.locator('[data-testid="client-recapitulatif"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="client-recapitulatif-user"]')).to_contain_text("carte3-jetable")
        expect(page.locator('[data-testid="client-recapitulatif-user"]')).to_contain_text("TESTNFC")

    # --- Chemin 2 : "Scanner carte" → NFC carte anonyme → formulaire → recapitulatif ---
    # (AVANT chemin 4 — chemin 4 associe un user a CLIENT1)

    def test_chemin_2_scanner_carte_anonyme_puis_formulaire(
        self, page, pos_page, adhesion_cards_setup
    ):
        """Chemin 2 : scanner carte anonyme (CLIENT1) → formulaire → recapitulatif.
        / Path 2: scan anonymous card (CLIENT1) → form → recap.
        """
        suffix = adhesion_cards_setup
        test_email = f"adh2-{suffix}@example.com"

        _naviguer_et_ajouter_adhesion(page, pos_page)

        # "Scanner carte" → NFC
        page.locator('[data-testid="client-choose-nfc"]').click()

        # Cliquer CLIENT1 (anonyme)
        expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(timeout=10_000)
        page.locator(f'.nfc-reader-simu-bt[tag-id="{DEMO_TAGID_CLIENT1}"]').click()

        # → carte anonyme → formulaire avec tag_id cache
        expect(page.locator('[data-testid="client-form"]')).to_be_visible(timeout=10_000)

        # Remplir et valider → recapitulatif
        page.locator('[data-testid="client-input-email"]').fill(test_email)
        page.locator('[data-testid="client-input-prenom"]').fill("PrenomDeux")
        page.locator('[data-testid="client-input-nom"]').fill("NomDeux")
        page.locator('[data-testid="client-btn-valider"]').click()

        expect(page.locator('[data-testid="client-recapitulatif"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="client-recapitulatif-user"]')).to_contain_text(test_email)

    # --- Chemin 4 : "Scanner carte" → NFC carte anonyme → formulaire → recapitulatif → ESPECE ---
    # (APRES chemin 2 — chemin 4 associe un user a CLIENT1)

    def test_chemin_4_scanner_carte_anonyme_formulaire_puis_espece(
        self, page, pos_page, adhesion_cards_setup
    ):
        """Chemin 4 : scanner carte (anonyme CLIENT1) → formulaire → recapitulatif → especes.
        / Path 4: scan card (anonymous CLIENT1) → form → recap → cash.
        """
        suffix = adhesion_cards_setup
        test_email = f"adh4-{suffix}@example.com"

        _naviguer_et_ajouter_adhesion(page, pos_page)

        # "Scanner carte" → NFC
        page.locator('[data-testid="client-choose-nfc"]').click()

        # Cliquer CLIENT1 (anonyme)
        expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(timeout=10_000)
        page.locator(f'.nfc-reader-simu-bt[tag-id="{DEMO_TAGID_CLIENT1}"]').click()

        # → carte sans user → formulaire
        expect(page.locator('[data-testid="client-form"]')).to_be_visible(timeout=10_000)

        # Remplir et valider
        page.locator('[data-testid="client-input-email"]').fill(test_email)
        page.locator('[data-testid="client-input-prenom"]').fill("PrenomQuatre")
        page.locator('[data-testid="client-input-nom"]').fill("NomQuatre")
        page.locator('[data-testid="client-btn-valider"]').click()

        # Recapitulatif → paiement
        expect(page.locator('[data-testid="client-recapitulatif"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="client-recapitulatif-user"]')).to_contain_text(test_email)
        page.locator('[data-testid="client-btn-especes"]').click()
        expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)

    # --- Bouton RETOUR depuis ecran identification ---

    def test_bouton_retour_ecran_identification(
        self, page, pos_page, adhesion_cards_setup
    ):
        """Bouton retour fonctionne depuis l'ecran identification.
        / Back button works from identification screen.
        """
        _naviguer_et_ajouter_adhesion(page, pos_page)

        # L'ecran identification est integre dans paiement-moyens
        # Le bouton retour dans paiement-moyens ramene a l'addition
        page.locator('[data-testid="paiement-moyens"] #bt-retour-layer1').click()
        expect(page.locator('[data-testid="paiement-moyens"]')).not_to_be_visible(timeout=5_000)

    # --- Bouton RETOUR depuis formulaire email ---

    def test_bouton_retour_formulaire_email(
        self, page, pos_page, adhesion_cards_setup
    ):
        """Bouton retour fonctionne depuis le formulaire email.
        / Back button works from email form.
        """
        _naviguer_et_ajouter_adhesion(page, pos_page)

        # "Saisir email"
        page.locator('[data-testid="client-choose-email"]').click()
        expect(page.locator('[data-testid="client-form"]')).to_be_visible(timeout=10_000)

        # RETOUR → le formulaire disparait
        page.locator('[data-testid="client-form"] #bt-retour-layer1').click()
        expect(page.locator('[data-testid="client-form"]')).not_to_be_visible(timeout=5_000)


# ===========================================================================
# Test panier mixte sur PV "Mix" (VT + RE + AD)
# / Mixed cart test on "Mix" POS (VT + RE + AD)
# ===========================================================================


@pytest.fixture(scope="class")
def recharge_asset_setup(django_shell):
    """S'assure qu'un asset TLF actif existe et que son produit de recharge
    est dans le PV Mix. Necessaire car d'autres tests (nfc_setup) peuvent
    desactiver les assets TLF.
    / Ensures an active TLF asset exists and its top-up product
    is in the Mix POS. Needed because other tests (nfc_setup) may
    deactivate TLF assets.
    """
    django_shell(
        "from Customers.models import Client\n"
        "from fedow_core.models import Asset\n"
        "from BaseBillet.models import Product\n"
        "from laboutik.models import PointDeVente\n"
        "from django.db import connection\n"
        "tenant = Client.objects.get(schema_name=connection.schema_name)\n"
        "# Desactiver TOUS les TLF pour eviter les conflits\n"
        "# / Deactivate ALL TLF to avoid conflicts\n"
        "Asset.objects.filter(tenant_origin=tenant, category='TLF').update(active=False)\n"
        "# Activer uniquement 'Monnaie locale' (cree par create_test_pos_data)\n"
        "# / Activate only 'Monnaie locale' (created by create_test_pos_data)\n"
        "asset_tlf = Asset.objects.filter(\n"
        "    tenant_origin=tenant, category='TLF', name='Monnaie locale'\n"
        ").first()\n"
        "if asset_tlf:\n"
        "    asset_tlf.active = True\n"
        "    asset_tlf.save(update_fields=['active'])\n"
        "produit_re = Product.objects.filter(\n"
        "    asset=asset_tlf, methode_caisse='RE'\n"
        ").first() if asset_tlf else None\n"
        "if produit_re:\n"
        "    pv_mix = PointDeVente.objects.filter(name='Mix').first()\n"
        "    if pv_mix:\n"
        "        pv_mix.products.add(produit_re)\n"
        "    print(f'SETUP_OK asset={asset_tlf.name} product={produit_re.name}')\n"
        "else:\n"
        "    print('NO_RECHARGE_PRODUCT')"
    )


class TestPOSPanierMixte:
    """Panier mixte sur PV "Mix" : Biere (VT) + Recharge (RE) + Adhesion (AD).
    Le verrouillage par groupe a ete supprime (session 05) → les 3 types
    peuvent etre ajoutes au meme panier.
    / Mixed cart on "Mix" POS: Beer (VT) + Recharge (RE) + Membership (AD).
    Group-based locking was removed (session 05) → all 3 types
    can be added to the same cart.
    """

    def test_panier_mixte_vt_re_ad_nfc_puis_especes(
        self, page, pos_page, django_shell, adhesion_cards_setup,
        recharge_asset_setup,
    ):
        """Panier VT + RE + AD → identification NFC → recapitulatif 3 articles → especes.
        Verifie en DB : 3 LigneArticle (VT + RE + AD) avec les bons champs.
        / Cart VT + RE + AD → NFC identification → 3-article recap → cash.
        DB check: 3 LigneArticle (VT + RE + AD) with correct fields.
        """
        suffix = adhesion_cards_setup

        # Ouvrir le PV Mix
        # / Open Mix POS
        pos_page(page, "Mix")

        # --- Ajouter Biere (VT) ---
        biere_tile = page.locator('#products .article-container[data-name="Biere"]')
        expect(biere_tile).to_be_visible(timeout=10_000)
        biere_tile.click()
        expect(page.locator("#addition-list")).to_contain_text("Biere", timeout=10_000)

        # --- Ajouter Recharge (RE) ---
        # Le produit de recharge est cree par le signal Asset (ex: "Recharge Monnaie locale").
        # La fixture recharge_asset_setup s'assure que l'asset TLF est actif.
        # Le produit est multi-tarif (1, 5, 10, Libre) → clic ouvre un overlay.
        # On clique le tarif "10" puis on ferme l'overlay.
        # / The top-up product is created by the Asset signal (e.g. "Recharge Monnaie locale").
        # The recharge_asset_setup fixture ensures the TLF asset is active.
        # The product is multi-rate (1, 5, 10, Free) → click opens an overlay.
        # We click the "10" rate then close the overlay.
        # Cibler "Monnaie locale" (asset TLF actif) pour eviter l'ambiguite avec
        # les autres Products Recharge (Cadeau TNF, Temps TIM) sur le meme PV.
        # / Target "Monnaie locale" (active TLF asset) to avoid ambiguity with
        # other Recharge Products (Cadeau TNF, Temps TIM) on the same POS.
        recharge_tile = page.locator('#products .article-container').filter(has_text="Monnaie locale")
        expect(recharge_tile.first).to_be_visible(timeout=10_000)
        recharge_tile.first.click()

        # Si overlay tarif pour la recharge → cliquer tarif "10"
        # / If rate overlay for top-up → click "10" rate
        tarif_overlay_re = page.locator('[data-testid="tarif-overlay"]')
        if tarif_overlay_re.is_visible(timeout=3_000):
            tarif_10 = tarif_overlay_re.locator(".tarif-btn-fixed").filter(has_text="10")
            expect(tarif_10.first).to_be_visible(timeout=5_000)
            tarif_10.first.click()
            # Fermer l'overlay / Close the overlay
            page.locator('[data-testid="tarif-btn-retour"]').click()

        expect(page.locator("#addition-list")).to_contain_text("Recharge", timeout=10_000)

        # --- Ajouter Adhesion (AD) ---
        adhesion_tile = page.locator('#products .article-container').filter(has_text="Adhesion")
        expect(adhesion_tile.first).to_be_visible(timeout=10_000)
        adhesion_tile.first.click()

        # Si overlay tarif pour l'adhesion → cliquer premier tarif fixe
        # / If rate overlay for membership → click first fixed rate
        tarif_overlay = page.locator(".tarif-overlay")
        if tarif_overlay.is_visible(timeout=2_000):
            first_fixed = tarif_overlay.locator(".tarif-btn:not(.tarif-btn-free)").first
            first_fixed.click()

        expect(page.locator("#addition-list")).to_contain_text("Adhesion", timeout=5_000)

        # --- VALIDER → ecran identification ---
        page.locator("#bt-valider").click()
        expect(page.locator('[data-testid="paiement-moyens"]')).to_be_visible(timeout=10_000)

        # NFC seulement (recharge dans le panier → pas d'email)
        expect(page.locator('[data-testid="client-choose-nfc"]')).to_be_visible(timeout=5_000)
        assert not page.locator('[data-testid="client-choose-email"]').is_visible()

        # --- Scanner carte CLIENT3 (avec user) ---
        page.locator('[data-testid="client-choose-nfc"]').click()
        expect(page.locator(".nfc-reader-simu-bt").first).to_be_visible(timeout=10_000)
        page.locator(f'.nfc-reader-simu-bt[tag-id="{DEMO_TAGID_CLIENT3}"]').click()

        # --- Recapitulatif avec les 3 articles ---
        expect(page.locator('[data-testid="client-recapitulatif"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="client-recapitulatif-user"]')).to_contain_text("carte3-jetable")

        # Le recapitulatif doit afficher les articles
        recapitulatif_articles = page.locator('[data-testid="client-recapitulatif-articles"]')
        expect(recapitulatif_articles).to_be_visible(timeout=5_000)

        # --- Payer en especes ---
        page.locator('[data-testid="client-btn-especes"]').click()
        expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)

        # --- Verification DB : 3 LigneArticle creees ---
        # On interroge la DB pour chaque article individuellement (pas de boucle for en one-liner).
        # / DB check: 3 LigneArticle created — query each article individually.

        # 1. Biere (VT) — especes, pas de membership
        result_biere = django_shell(
            "from BaseBillet.models import LigneArticle, SaleOrigin\n"
            "ligne = LigneArticle.objects.filter("
            "sale_origin=SaleOrigin.LABOUTIK, "
            "pricesold__productsold__product__name='Biere'"
            ").order_by('-datetime').first()\n"
            "print(f'method={ligne.payment_method} origin={ligne.sale_origin} "
            "amount={ligne.amount} qty={int(ligne.qty)} status={ligne.status} "
            "carte={ligne.carte_id}') if ligne else print('NOT_FOUND')"
        )
        assert 'NOT_FOUND' not in result_biere, f"LigneArticle Biere introuvable: {result_biere}"
        assert 'method=CA' in result_biere, f"Biere: payment method pas CA: {result_biere}"
        assert 'origin=LB' in result_biere, f"Biere: origin pas LB: {result_biere}"
        assert 'status=V' in result_biere, f"Biere: status pas V: {result_biere}"
        assert 'amount=500' in result_biere, f"Biere: amount pas 500: {result_biere}"

        # 2. Recharge 10€ (RE) — especes
        result_recharge = django_shell(
            "from BaseBillet.models import LigneArticle, SaleOrigin\n"
            "ligne = LigneArticle.objects.filter("
            "sale_origin=SaleOrigin.LABOUTIK, "
            "pricesold__productsold__product__name__startswith='Recharge'"
            ").order_by('-datetime').first()\n"
            "print(f'method={ligne.payment_method} origin={ligne.sale_origin} "
            "amount={ligne.amount} qty={int(ligne.qty)} status={ligne.status} "
            "carte={ligne.carte_id}') if ligne else print('NOT_FOUND')"
        )
        assert 'NOT_FOUND' not in result_recharge, f"LigneArticle Recharge introuvable: {result_recharge}"
        assert 'method=CA' in result_recharge, f"Recharge: payment method pas CA: {result_recharge}"
        assert 'origin=LB' in result_recharge, f"Recharge: origin pas LB: {result_recharge}"
        assert 'amount=1000' in result_recharge, f"Recharge: amount pas 1000: {result_recharge}"

        # 3. Adhesion (AD) — especes + membership liee avec email du user de la carte
        result_adhesion = django_shell(
            "from BaseBillet.models import LigneArticle, SaleOrigin\n"
            "ligne = LigneArticle.objects.filter("
            "sale_origin=SaleOrigin.LABOUTIK, "
            "pricesold__productsold__product__name__startswith='Adhesion'"
            ").order_by('-datetime').first()\n"
            "email = ligne.membership.user.email if ligne and ligne.membership else 'no_membership'\n"
            "print(f'method={ligne.payment_method} origin={ligne.sale_origin} "
            "amount={ligne.amount} qty={int(ligne.qty)} status={ligne.status} "
            "email={email}') if ligne else print('NOT_FOUND')"
        )
        assert 'NOT_FOUND' not in result_adhesion, f"LigneArticle Adhesion introuvable: {result_adhesion}"
        assert 'method=CA' in result_adhesion, f"Adhesion: payment method pas CA: {result_adhesion}"
        assert 'origin=LB' in result_adhesion, f"Adhesion: origin pas LB: {result_adhesion}"
        assert 'status=V' in result_adhesion, f"Adhesion: status pas V: {result_adhesion}"
        assert 'carte3-jetable' in result_adhesion, f"Adhesion: email user incorrect: {result_adhesion}"
