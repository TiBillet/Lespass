"""
tests/e2e/test_admin_card_refund.py — Test E2E flow remboursement carte (Phase 1).

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/e2e/test_admin_card_refund.py -v -s
"""
import pytest


# UUID deterministique pour la carte de test (facile a localiser dans le setup/teardown).
# / Deterministic UUID for the test card.
CARTE_E2E_UUID = "11111111-1111-1111-1111-e2e000000001"
CARTE_E2E_TAG = "E2EAD001"


@pytest.fixture
def carte_avec_solde_e2e(django_shell):
    """
    Prepare en DB une carte avec 1000c TLF + 500c FED rattachee a lespass.
    Promeut aussi l'admin de test en superuser (necessaire pour voir les cartes
    SHARED_APPS via le queryset CarteCashlessAdmin).
    Retourne l'uuid de la carte. Nettoyage en fin de test.

    / Setup: card with 1000c TLF + 500c FED attached to lespass.
    Also promotes test admin to superuser (required to see SHARED_APPS cards
    via CarteCashlessAdmin queryset).
    Returns card uuid. Cleanup at teardown.
    """
    # Promouvoir l'admin en superuser pour la duree du test
    # / Promote admin to superuser for the duration of the test
    promote_code = (
        "from django.contrib.auth import get_user_model; "
        "User = get_user_model(); "
        "u = User.objects.filter(email='admin@admin.com').first(); "
        "was_superuser = u.is_superuser if u else False; "
        "print(f'WAS_SUPERUSER:{was_superuser}'); "
        "u.is_superuser = True; u.save() if u else None; "
        "print('PROMOTE_OK')"
    )
    promote_out = django_shell(promote_code)
    assert "PROMOTE_OK" in promote_out, f"Promote admin failed: {promote_out}"
    was_superuser = "WAS_SUPERUSER:True" in promote_out

    # Note : pas de guillemets doubles dans le code — django_shell les echappe.
    # / Note: no double quotes in code — django_shell escapes them.
    setup_code = (
        "import uuid; "
        "from AuthBillet.models import Wallet; "
        "from Customers.models import Client; "
        "from QrcodeCashless.models import CarteCashless, Detail; "
        "from fedow_core.models import Asset, Token; "
        "tenant = Client.objects.get(schema_name='lespass'); "
        "wallet_lieu, _ = Wallet.objects.get_or_create(origin=tenant, name='Lieu lespass'); "
        "asset_tlf, _ = Asset.objects.get_or_create("
        "    name='E2E TLF Lespass', category=Asset.TLF,"
        "    defaults=dict(currency_code='EUR', wallet_origin=wallet_lieu, tenant_origin=tenant)"
        "); "
        "asset_fed = Asset.objects.filter(category=Asset.FED).first(); "
        "asset_fed = asset_fed or Asset.objects.create("
        "    name='E2E FED', category=Asset.FED, currency_code='EUR',"
        "    wallet_origin=wallet_lieu, tenant_origin=tenant"
        "); "
        "detail, _ = Detail.objects.get_or_create(base_url='E2E_REFUND', origine=tenant, defaults={'generation': 0}); "
        "wallet_user = Wallet.objects.create(name='E2E Wallet user'); "
        f"carte, created = CarteCashless.objects.get_or_create(tag_id='{CARTE_E2E_TAG}', defaults=dict(number='{CARTE_E2E_TAG}', uuid=uuid.UUID('{CARTE_E2E_UUID}'), detail=detail, wallet_ephemere=wallet_user)); "
        "carte.wallet_ephemere = wallet_user; carte.user = None; carte.save(); "
        # Creer les tokens directement (evite select_for_update hors atomic)
        # / Create tokens directly (avoids select_for_update outside atomic)
        "Token.objects.update_or_create(wallet=wallet_user, asset=asset_tlf, defaults={'value': 1000}); "
        "Token.objects.update_or_create(wallet=wallet_user, asset=asset_fed, defaults={'value': 500}); "
        # Afficher le PK (entier) de la carte — l'admin Django utilise le PK, pas l'UUID
        # / Print the card PK (integer) — Django admin uses PK, not UUID
        f"carte_pk = CarteCashless.objects.get(tag_id='{CARTE_E2E_TAG}').pk; "
        "print(f'CARTE_PK:{carte_pk}'); "
        "print('SETUP_OK')"
    )
    out = django_shell(setup_code)
    assert "SETUP_OK" in out, f"Setup E2E failed: {out}"

    # Extraire le PK entier de la carte (necessaire pour l'URL admin /change/)
    # / Extract the integer card PK (needed for admin /change/ URL)
    carte_pk = None
    for line in out.split('\n'):
        if line.startswith('CARTE_PK:'):
            carte_pk = line.split(':', 1)[1].strip()
            break
    assert carte_pk is not None, f"CARTE_PK introuvable dans: {out}"

    yield {"uuid": CARTE_E2E_UUID, "pk": carte_pk}

    # Note : pas de guillemets doubles — django_shell les echappe.
    # / Note: no double quotes — django_shell escapes them.
    teardown_code = (
        "from AuthBillet.models import Wallet; "
        "from QrcodeCashless.models import CarteCashless, Detail; "
        "from fedow_core.models import Asset, Token, Transaction; "
        "from BaseBillet.models import LigneArticle, Product, Price; "
        # Charger les cartes + wallets avant de supprimer quoi que ce soit
        # / Load cards + wallets before deleting anything
        f"cartes = list(CarteCashless.objects.filter(tag_id='{CARTE_E2E_TAG}')); "
        "wallets_eph = [c.wallet_ephemere for c in cartes if c.wallet_ephemere]; "
        # Supprimer LigneArticle, Transaction, Token avant les FK protegees
        # / Delete LigneArticle, Transaction, Token before protected FKs
        "[LigneArticle.objects.filter(carte=c).delete() for c in cartes]; "
        "[Transaction.objects.filter(card=c).delete() for c in cartes]; "
        # Supprimer aussi les tokens du wallet lieu lies aux assets E2E
        # / Also delete tokens on the lieu wallet linked to E2E assets
        "Token.objects.filter(wallet__name__startswith='E2E ').delete(); "
        "Token.objects.filter(asset__name__startswith='E2E ').delete(); "
        "[c.delete() for c in cartes]; "
        "[w.delete() for w in wallets_eph if Wallet.objects.filter(pk=w.pk).exists()]; "
        "Detail.objects.filter(base_url='E2E_REFUND').delete(); "
        # Supprimer les Products crees par le signal Asset post_save
        # / Delete Products created by Asset post_save signal
        "prods_e2e = Product.objects.filter(name__icontains='E2E '); "
        "[Price.objects.filter(product=p).delete() for p in prods_e2e]; "
        "prods_e2e.delete(); "
        "Asset.objects.filter(name__startswith='E2E ').delete(); "
        "Wallet.objects.filter(name__startswith='E2E ').delete(); "
        "print('TEARDOWN_OK')"
    )
    django_shell(teardown_code)

    # Retrograder l'admin si necessaire (il n'etait pas superuser avant le test)
    # / Demote admin if needed (he was not superuser before the test)
    if not was_superuser:
        demote_code = (
            "from django.contrib.auth import get_user_model; "
            "User = get_user_model(); "
            "u = User.objects.filter(email='admin@admin.com').first(); "
            "u.is_superuser = False; u.save() if u else None; "
            "print('DEMOTE_OK')"
        )
        django_shell(demote_code)


def test_e2e_admin_refund_flow_complet(page, login_as_admin, django_shell, carte_avec_solde_e2e):
    """
    Flow complet : login admin -> fiche carte (/change/) -> panel HTMX ->
    bouton ouvrir modal -> modal confirmation -> cliquer confirmer ->
    HX-Refresh reload -> verifier panel sans tokens + LigneArticle/Transactions en DB.

    Complete flow: admin login -> card change page -> HTMX panel ->
    open modal button -> confirm modal -> HX-Refresh reload ->
    verify empty panel + LigneArticle/Transaction state in DB.
    """
    # 1. Login admin via le flow TEST MODE
    login_as_admin(page)

    # 2. Naviguer vers la fiche carte (/change/) — nouveau flow inline
    # L'URL admin utilise le PK entier (AutoField), pas l'UUID.
    # / Navigate to card change page (/change/) — new inline flow
    # The admin URL uses the integer PK (AutoField), not the UUID.
    carte_pk = carte_avec_solde_e2e["pk"]
    change_url = f"/admin/QrcodeCashless/cartecashless/{carte_pk}/change/"
    page.goto(change_url)
    page.wait_for_load_state("domcontentloaded")

    # 3. Attendre que le panel HTMX se charge (hx-trigger="load")
    # Le conteneur initial est remplace par le refund-panel via HTMX.
    # / Wait for HTMX panel to load (hx-trigger="load").
    # The initial container is replaced by the refund-panel via HTMX.
    page.wait_for_selector('[data-testid="refund-panel"]', timeout=10_000)

    # 4. Verifier l'affichage des tokens et du total dans le panel (1000 + 500 = 1500 centimes)
    # Note : les valeurs sont affichees avec format FR (virgule) : "10,00 €"
    # / Note: values are displayed with FR format (comma): "10,00 €"
    page.wait_for_selector('[data-testid="refund-panel-tokens"]', timeout=5_000)
    contenu = page.content()
    assert "10,00" in contenu, "Solde TLF 10,00 EUR introuvable dans le panel"
    assert "5,00" in contenu, "Solde FED 5,00 EUR introuvable dans le panel"
    assert "15,00" in contenu, "Total 15,00 EUR introuvable dans le panel"

    # 5. Cliquer le bouton pour ouvrir le modal
    # / Click the button to open the modal
    page.click('[data-testid="btn-open-refund-modal"]')

    # 6. Attendre que le modal s'injecte dans #refund-modal-slot via HTMX
    # / Wait for modal to be injected into #refund-modal-slot via HTMX
    page.wait_for_selector('[data-testid="refund-modal"]', timeout=10_000)

    # 7. Ne pas cocher la checkbox "Vider la carte" — on veut tester le cas
    # "remboursement sans reinitialisation" : tokens a 0, carte conservee.
    # Apres confirmation, le panel devrait afficher refund-panel-no-tokens.
    # / Do not check "Vider la carte" checkbox — testing "refund without reset":
    # tokens set to 0, card kept. After confirm, panel shows refund-panel-no-tokens.

    # 8. Cliquer "Confirmer le remboursement"
    # / Click "Confirm refund"
    page.click('[data-testid="modal-btn-confirm"]')

    # 9. Attendre le rechargement complet de la page (HX-Refresh: true)
    # HTMX intercepte la reponse avec HX-Refresh et fait window.location.reload().
    # Playwright detecte le rechargement comme une navigation complete.
    # / Wait for full page reload (HX-Refresh: true).
    # HTMX intercepts the response with HX-Refresh and calls window.location.reload().
    # Playwright detects the reload as a full navigation.
    page.wait_for_load_state("domcontentloaded", timeout=15_000)

    # 10. Apres rechargement : attendre que le panel se recharge via HTMX
    # et verifier qu'il affiche "aucun solde remboursable" (tokens a zero, carte conservee)
    # / After reload: wait for panel to reload via HTMX
    # and verify it shows "no refundable balance" (tokens at zero, card kept)
    page.wait_for_selector('[data-testid="refund-panel"]', timeout=10_000)
    page.wait_for_selector('[data-testid="refund-panel-no-tokens"]', timeout=10_000)

    # Verifier que l'URL est toujours sur la fiche carte (/change/)
    # / Verify URL is still on the card change page (/change/)
    url_actuelle = page.url
    assert f"{carte_pk}/change/" in url_actuelle, (
        f"Pas sur la fiche carte (pk={carte_pk}) apres reload : {url_actuelle}"
    )
    assert "/refund" not in url_actuelle, (
        f"URL contient encore /refund apres le nouveau flow : {url_actuelle}"
    )

    # 11. Verifier en DB : 2 Transactions REFUND + LigneArticles (FED + CASH)
    # Note : pas de guillemets doubles — django_shell les echappe.
    # / Note: no double quotes — django_shell escapes them.
    verify_code = (
        "from QrcodeCashless.models import CarteCashless; "
        "from fedow_core.models import Transaction; "
        "from BaseBillet.models import LigneArticle, PaymentMethod; "
        f"carte = CarteCashless.objects.get(tag_id='{CARTE_E2E_TAG}'); "
        "tx_refund = Transaction.objects.filter(card=carte, action=Transaction.REFUND).count(); "
        "lignes_cash = list(LigneArticle.objects.filter(carte=carte, payment_method=PaymentMethod.CASH).values_list('amount', flat=True)); "
        "lignes_fed = list(LigneArticle.objects.filter(carte=carte, payment_method=PaymentMethod.STRIPE_FED).values_list('amount', flat=True)); "
        "print(f'TX_REFUND:{tx_refund}'); "
        "print(f'CASH_AMOUNT:{lignes_cash}'); "
        "print(f'FED_AMOUNT:{lignes_fed}')"
    )
    out = django_shell(verify_code)
    assert "TX_REFUND:2" in out, f"Expected 2 REFUND transactions, got: {out}"
    # Sortie cash = -(TLF + FED) = -1500
    assert "-1500" in out, f"Expected CASH amount -1500, got: {out}"
    # Encaissement FED positif = 500
    assert "500" in out, f"Expected FED amount 500, got: {out}"
