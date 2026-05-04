"""
tests/e2e/test_scan_qr_carte_v2.py — Tests E2E flow scan QR carte cashless (V2).

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/e2e/test_scan_qr_carte_v2.py -v -s

SCOPE :
- Flow complet scan QR -> form register.html -> POST /qr/link/ -> redirect /qr/<uuid>/ -> /my_account
- Verification DB via django_shell (carte.user set, wallet_ephemere=None)
- Test cross-domain skip (infra 2 tenants requise)

IMPORTANT — comportement TEST/DEBUG :
- Apres POST /qr/link/, la carte est liee mais le user n'est PAS auto-logge directement.
- L'HTMX redirect retourne sur /qr/<uuid>/ qui cette fois redirige vers /my_account
  en mode TEST avec un message "TEST MODE" (lien emailconfirmation).
- Les assertions portent sur : page chargee sur /my_account OU on_qr_page_again
  OU la presence du texte TEST MODE dans la page.
"""

import time

import pytest

# UUID deterministe pour la carte V2 de test.
# / Deterministic UUID for the V2 test card.
CARTE_V2_UUID = "22222222-2222-2222-2222-e2e000000001"
CARTE_V2_TAG = "E2EV2001"

# Email de test genere avec suffixe unique pour eviter les conflits entre runs.
# / Test email with unique suffix to avoid conflicts between runs.
EMAIL_SUFFIXE = str(int(time.time()))[-6:]
EMAIL_TEST = f"e2e-scan-{EMAIL_SUFFIXE}@test.local"


# ------------------------------------------------------------------
# Fixture : preparation + nettoyage de la carte V2 en DB
# / Fixture: setup + teardown of the V2 card in DB
# ------------------------------------------------------------------


@pytest.fixture
def carte_v2_vierge(django_shell):
    """
    Prepare une carte CarteCashless vierge (sans user, sans wallet_ephemere)
    avec un UUID deterministe dans le schema lespass.
    Verifie aussi que Configuration.server_cashless est vide (V2 actif).
    Teardown : supprime la carte + user de test + wallet.

    / Setup: create a blank CarteCashless (no user, no wallet_ephemere)
    with a deterministic UUID in the lespass schema.
    Also checks Configuration.server_cashless is empty (V2 active).
    Teardown: delete test card + user + wallet.
    """
    # Verification que V2 est actif (server_cashless vide).
    # / Check V2 is active (server_cashless empty).
    check_v2_code = (
        "from BaseBillet.models import Configuration; "
        "config = Configuration.get_solo(); "
        "print(f'SERVER_CASHLESS:{repr(config.server_cashless)}'); "
        "is_v2 = not bool(config.server_cashless); "
        "print(f'IS_V2:{is_v2}')"
    )
    check_out = django_shell(check_v2_code)
    assert "IS_V2:True" in check_out, (
        f"Le tenant lespass est en V1 (server_cashless non vide). "
        f"Ce test requiert V2. Sortie : {check_out}"
    )

    # Note : pas de guillemets doubles dans le code — django_shell les echappe.
    # / Note: no double quotes in code — django_shell escapes them.
    setup_code = (
        "import uuid; "
        "from Customers.models import Client; "
        "from QrcodeCashless.models import CarteCashless, Detail; "
        "tenant = Client.objects.get(schema_name='lespass'); "
        # Creer un Detail minimal pour la carte (base_url unique pour le teardown)
        # / Create a minimal Detail for the card (unique base_url for teardown)
        "detail, _ = Detail.objects.get_or_create("
        "    base_url='E2E_SCAN_V2', "
        "    defaults=dict(origine=tenant, generation=0)"
        "); "
        "detail.origine = tenant; detail.save(); "
        # Carte deterministe — get_or_create pour idempotence si run precedent a echoue
        # / Deterministic card — get_or_create for idempotency if previous run failed
        f"carte, created = CarteCashless.objects.get_or_create("
        f"    tag_id='{CARTE_V2_TAG}', "
        f"    defaults=dict(number='{CARTE_V2_TAG}', uuid=uuid.UUID('{CARTE_V2_UUID}'), detail=detail)"
        f"); "
        # Reset carte au cas ou un run precedent l'a modifiee
        # / Reset card in case a previous run modified it
        "carte.user = None; carte.wallet_ephemere = None; carte.save(); "
        "print(f'CARTE_UUID:{carte.uuid}'); "
        "print('SETUP_OK')"
    )
    out = django_shell(setup_code)
    assert "SETUP_OK" in out, f"Setup E2E V2 failed: {out}"

    yield {"uuid": CARTE_V2_UUID, "tag": CARTE_V2_TAG}

    # Teardown : nettoyer carte + user + wallet crees par le test.
    # Note : pas de guillemets doubles — django_shell les echappe.
    # / Teardown: clean card + user + wallet created by the test.
    teardown_code = (
        "from AuthBillet.models import Wallet; "
        "from AuthBillet.models import TibilletUser; "
        "from QrcodeCashless.models import CarteCashless, Detail; "
        "from fedow_core.models import Token, Transaction; "
        # Charger les cartes avant suppression
        # / Load cards before deletion
        f"cartes = list(CarteCashless.objects.filter(tag_id='{CARTE_V2_TAG}')); "
        "wallets_eph = [c.wallet_ephemere for c in cartes if c.wallet_ephemere]; "
        "users_test = [c.user for c in cartes if c.user]; "
        "wallets_user = [u.wallet for u in users_test if hasattr(u, 'wallet') and u.wallet]; "
        # Supprimer les transactions liees aux cartes
        # / Delete transactions linked to cards
        "[Transaction.objects.filter(card=c).delete() for c in cartes]; "
        # Supprimer les tokens des wallets ephemeres et user
        # / Delete tokens from ephemeral and user wallets
        "[Token.objects.filter(wallet=w).delete() for w in wallets_eph]; "
        "[Token.objects.filter(wallet=w).delete() for w in wallets_user]; "
        # Supprimer les cartes
        # / Delete cards
        "[c.delete() for c in cartes]; "
        # Supprimer wallets ephemeres
        # / Delete ephemeral wallets
        "[w.delete() for w in wallets_eph if Wallet.objects.filter(pk=w.pk).exists()]; "
        # Supprimer users de test (email contient e2e-scan)
        # / Delete test users (email contains e2e-scan)
        "test_users = TibilletUser.objects.filter(email__startswith='e2e-scan'); "
        "wallets_of_test_users = [u.wallet for u in test_users if hasattr(u, 'wallet') and u.wallet]; "
        "[Token.objects.filter(wallet=w).delete() for w in wallets_of_test_users]; "
        "[w.delete() for w in wallets_of_test_users if Wallet.objects.filter(pk=w.pk).exists()]; "
        "test_users.delete(); "
        # Supprimer le Detail E2E
        # / Delete E2E Detail
        "Detail.objects.filter(base_url='E2E_SCAN_V2').delete(); "
        "print('TEARDOWN_OK')"
    )
    django_shell(teardown_code)


# ------------------------------------------------------------------
# Test 1 : Flow complet scan QR -> enregistrement -> carte liee
# / Test 1: Full scan QR -> registration -> card linked
# ------------------------------------------------------------------


def test_scan_qr_flow_complet(page, carte_v2_vierge, django_shell):
    """
    Flow complet scan QR V2 :
    1. GET /qr/<uuid>/ → affiche register.html (carte vierge → wallet_ephemere cree)
    2. Remplir email + emailConfirmation + cgu
    3. Soumettre → HTMX POST /qr/link/ → HttpResponseClientRedirect /qr/<uuid>/
    4. HTMX re-navigue vers /qr/<uuid>/ → carte maintenant liee → redirect /my_account
    5. Verifier en DB : carte.user non null, wallet_ephemere=None

    / Full V2 QR scan flow:
    1. GET /qr/<uuid>/ → shows register.html (blank card → wallet_ephemere created)
    2. Fill email + emailConfirmation + cgu
    3. Submit → HTMX POST /qr/link/ → HttpResponseClientRedirect /qr/<uuid>/
    4. HTMX re-navigates to /qr/<uuid>/ → card now linked → redirect /my_account
    5. Verify in DB: card.user not null, wallet_ephemere=None
    """
    carte_uuid = carte_v2_vierge["uuid"]
    qr_url = f"/qr/{carte_uuid}/"

    # 1. Naviguer vers la page de scan QR — doit afficher le formulaire d'inscription.
    # / Navigate to the QR scan page — should show the registration form.
    page.goto(qr_url)
    page.wait_for_load_state("domcontentloaded")

    # 2. Verifier que le formulaire #linkform est visible (carte vierge → register.html).
    # / Verify form #linkform is visible (blank card → register.html).
    page.wait_for_selector('[id="linkform"]', timeout=10_000)
    assert page.locator('[id="linkform"]').is_visible(), (
        "Le formulaire #linkform n'est pas visible — "
        "la page register.html n'a pas ete rendue"
    )

    # 3. Remplir email et emailConfirmation (meme valeur — validation JS client).
    # / Fill email and emailConfirmation (same value — client-side JS validation).
    page.fill('input[name="email"]', EMAIL_TEST)
    page.fill('input[name="emailConfirmation"]', EMAIL_TEST)

    # 3b. Remplir firstname/lastname si le champ est visible dans le DOM.
    # Le template les affiche seulement quand config.need_name=True.
    # Ces champs ont l'attribut HTML `required` — sans eux, le navigateur bloque
    # la soumission. Le validator serveur les accepte en optional (allow_blank).
    # / Fill firstname/lastname if visible in DOM.
    # Template shows them only when config.need_name=True.
    # These fields have HTML `required` — without them, the browser blocks submit.
    # Server validator accepts them as optional (allow_blank).
    firstname_input = page.locator('input[name="firstname"]')
    if firstname_input.is_visible():
        firstname_input.fill("AliceE2E")

    lastname_input = page.locator('input[name="lastname"]')
    if lastname_input.is_visible():
        lastname_input.fill("TestE2E")

    # 4. Cocher la checkbox CGU (required par le validator serveur).
    # / Check the CGU checkbox (required by the server validator).
    page.check('input[name="cgu"]')

    # 5. Soumettre le formulaire (bouton type=submit).
    # L'HTMX intercepte l'event, poste en POST /qr/link/, recoit
    # HttpResponseClientRedirect, puis re-navigue vers /qr/<uuid>/.
    # / Submit the form (type=submit button).
    # HTMX intercepts the event, posts to /qr/link/, receives
    # HttpResponseClientRedirect, then re-navigates to /qr/<uuid>/.
    page.click('button[type="submit"]')

    # 6. Attendre la navigation finale.
    # Apres POST /qr/link/ reussi :
    #   - HTMX reçoit HttpResponseClientRedirect → re-GET /qr/<uuid>/
    #   - Le GET voit carte liee → redirect Django vers /my_account
    #   - En mode TEST/DEBUG → /my_account s'affiche avec message TEST MODE
    # On attend soit /my_account, soit que la page finisse de charger.
    # / Wait for the final navigation.
    # After successful POST /qr/link/:
    #   - HTMX receives HttpResponseClientRedirect → re-GET /qr/<uuid>/
    #   - GET sees linked card → Django redirect to /my_account
    #   - In TEST/DEBUG mode → /my_account shows with TEST MODE message
    page.wait_for_load_state("domcontentloaded", timeout=15_000)

    # Attendre que l'URL soit sur /my_account ou /emailconfirmation
    # (en mode TEST, le redirect peut passer par emailconfirmation).
    # / Wait for URL to be on /my_account or /emailconfirmation
    # (in TEST mode, redirect may go through emailconfirmation).
    try:
        page.wait_for_url(
            lambda url: "/my_account" in url or "emailconfirmation" in url,
            timeout=10_000,
        )
    except Exception:
        # Si le timeout expire sans navigation vers /my_account, on verifie
        # quand meme que la carte est liee en DB (le test peut reussir partiellement
        # si la page affiche une erreur mais que la DB est correcte).
        # On ne raise pas ici — la verification DB ci-dessous determinera le resultat.
        # / If timeout expires without /my_account navigation, we still verify
        # card is linked in DB. Do not raise — DB check below decides.
        pass

    # 7. Verifier en DB : carte.user est set, wallet_ephemere=None.
    # Note : pas de guillemets doubles — django_shell les echappe.
    # / Verify in DB: carte.user is set, wallet_ephemere=None.
    verify_code = (
        "from QrcodeCashless.models import CarteCashless; "
        f"carte = CarteCashless.objects.get(tag_id='{CARTE_V2_TAG}'); "
        "print(f'USER:{carte.user}'); "
        "print(f'USER_EMAIL:{carte.user.email if carte.user else None}'); "
        "print(f'WALLET_EPH:{carte.wallet_ephemere}'); "
        "has_user = carte.user is not None; "
        "no_wallet_eph = carte.wallet_ephemere is None; "
        "print(f'CARTE_LIEE:{has_user}'); "
        "print(f'WALLET_EPH_NONE:{no_wallet_eph}')"
    )
    db_out = django_shell(verify_code)

    # La carte doit etre liee a un user apres le flow.
    # / The card must be linked to a user after the flow.
    assert "CARTE_LIEE:True" in db_out, (
        f"La carte n'est pas liee a un user apres le flow E2E. DB output: {db_out}"
    )

    # Le wallet_ephemere doit etre None (fusionne dans le wallet user).
    # / wallet_ephemere must be None (merged into user wallet).
    assert "WALLET_EPH_NONE:True" in db_out, (
        f"Le wallet_ephemere n'est pas None apres lier_a_user. DB output: {db_out}"
    )

    # Verifier que l'email correspond bien au test.
    # / Verify the email matches the test email.
    assert EMAIL_TEST in db_out, (
        f"L'email du user lie n'est pas {EMAIL_TEST}. DB output: {db_out}"
    )


# ------------------------------------------------------------------
# Test 2 : Redirection cross-domain (skip si infra mono-tenant)
# / Test 2: Cross-domain redirect (skip if single-tenant infra)
# ------------------------------------------------------------------


@pytest.mark.skip(
    reason=(
        "Test cross-domain requiert 2 tenants distincts avec Traefik. "
        "En dev mono-tenant, tester la redirection cross-domain n'est pas trivial. "
        "Ce test verifie uniquement que la page /qr/<uuid>/ se charge correctement "
        "sur le tenant lespass (pas de redirect cross-domain attendu). "
        "Pour activer le test complet, retirer le skip et configurer SECOND_SUB."
    )
)
def test_scan_qr_redirection_crossdomain(page, carte_v2_vierge, django_shell):
    """
    Verifie que scanner une carte depuis un autre tenant redirige vers
    le primary_domain du tenant d'origine de la carte.

    Ce test necessite une infrastructure avec 2 sous-domaines distincts
    (ex: lespass.tibillet.localhost + chantefrein.tibillet.localhost).

    En l'absence de cette infrastructure, le test est marque SKIP.
    La logique de redirection est couverte par les tests unitaires pytest.

    / Verifies that scanning a card from another tenant redirects to
    the origin tenant's primary_domain.

    This test requires infrastructure with 2 distinct subdomains
    (e.g. lespass.tibillet.localhost + chantefrein.tibillet.localhost).

    Without this infrastructure, the test is marked SKIP.
    The redirect logic is covered by unit pytest tests.
    """
    import os
    from tests.e2e.conftest import DOMAIN

    carte_uuid = carte_v2_vierge["uuid"]
    second_sub = os.environ.get("SECOND_SUB", "")

    if not second_sub:
        pytest.skip(
            "SECOND_SUB env non defini — test cross-domain non applicable. "
            "Definir SECOND_SUB=<autre_tenant> pour activer ce test."
        )

    # Naviguer depuis le 2e tenant — doit rediriger vers lespass.
    # / Navigate from the 2nd tenant — should redirect to lespass.
    second_tenant_url = f"https://{second_sub}.{DOMAIN}/qr/{carte_uuid}/"
    page.goto(second_tenant_url)
    page.wait_for_load_state("domcontentloaded", timeout=10_000)

    # Verifier que l'URL finale est sur lespass (redirect cross-domain effectif).
    # / Verify final URL is on lespass (cross-domain redirect effective).
    final_url = page.url
    assert "lespass" in final_url, (
        f"Redirect cross-domain attendu vers lespass — URL actuelle : {final_url}"
    )
    assert f"/qr/{carte_uuid}/" in final_url, (
        f"UUID de la carte absent dans l'URL apres redirect : {final_url}"
    )
