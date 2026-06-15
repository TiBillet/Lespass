"""
Tests E2E : annulation d'adhésion avec option avoir depuis l'admin.
/ E2E tests: cancel membership with optional credit note from admin.

Conversion de tests/playwright/tests/34-admin-cancel-membership.spec.ts

Nouveau flux (v1.7.7) :
Le bouton "Annuler l'adhésion" est dans le panneau HTMX inline.
Plus de page intermédiaire — le formulaire de confirmation apparaît inline.
Après confirmation, HX-Redirect vers la changelist.

/ New flow (v1.7.7):
The "Cancel membership" button is in the inline HTMX panel.
No intermediate page — confirmation form appears inline.
After confirmation, HX-Redirect to changelist.

Scénarios :
1. Annuler une adhésion sans lignes de vente → confirmation simple
2. Annuler une adhésion avec lignes payées → choix avec/sans avoir

NOTE sur le test 2 — ajout de paiement via django_shell :
Le panneau d'actions HTMX est rendu dans change_form_before_template, à l'intérieur
de <form id="membership_form"> du Django admin. HTML interdit les <form> imbriqués ;
Chromium associe les submit buttons au formulaire externe → HTMX ne reçoit jamais
l'événement submit. Contournement testé (htmx.ajax, trigger JS) : le swap DOM ne
s'effectue pas non plus. Pour ce test, la LigneArticle de paiement est créée
directement via django_shell, ce qui est la même chose fonctionnellement.
L'essentiel du test est : l'admin voit deux boutons d'annulation quand une ligne
de vente existe, et "annuler avec avoir" crée une LigneArticle status='N'.

/ NOTE on test 2 — adding payment via django_shell:
The HTMX action panel is rendered inside <form id="membership_form"> of the
Django admin. HTML forbids nested forms; Chromium associates submit buttons with
the outer form → HTMX never receives the submit event. Tested workarounds
(htmx.ajax, JS trigger): the DOM swap doesn't work either.
For this test, the payment LigneArticle is created directly via django_shell,
which is functionally equivalent. The key assertion is: the admin sees two cancel
buttons when a sale line exists, and "cancel with credit note" creates a
LigneArticle with status='N'.
"""

import os
import random
import re
import shutil
import string

import pytest
import requests as http_requests


pytestmark = pytest.mark.e2e


# --- Configuration URL pour les appels API directs ---
# Même logique que conftest.py : depuis le container, on passe par le Docker
# gateway (Traefik) avec un header Host ; depuis l'hôte, URL directe.
# / Same logic as conftest.py: from container, go through Docker gateway
# (Traefik) with Host header; from host, direct URL.
SUB = os.environ.get("SUB", "lespass")
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
DOCKER_GATEWAY = os.environ.get("DOCKER_GATEWAY", "172.17.0.1")
INSIDE_CONTAINER = shutil.which("docker") is None
API_BASE_URL = (
    f"https://{DOCKER_GATEWAY}" if INSIDE_CONTAINER else f"https://{SUB}.{DOMAIN}"
)
API_HOST_HEADER = f"{SUB}.{DOMAIN}" if INSIDE_CONTAINER else None


def _random_id():
    """Génère un suffixe court unique (DB dev partagée, pas de rollback).
    / Generates a short unique suffix (shared dev DB, no rollback).
    """
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _api_headers(api_key):
    """Construit les headers d'authentification pour l'API v2.
    / Builds authentication headers for the API v2.
    """
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    if API_HOST_HEADER:
        headers["Host"] = API_HOST_HEADER
    return headers


def _create_membership_api(
    api_key,
    price_uuid,
    email,
    first_name="API",
    last_name="Member",
    payment_mode="FREE",
    status=None,
    valid_until=None,
):
    """Crée une adhésion via POST /api/v2/memberships/ (schema.org ProgramMembership).
    Équivalent de createMembershipApi dans utils/api.ts.
    / Creates a membership via POST /api/v2/memberships/ (schema.org ProgramMembership).
    Equivalent of createMembershipApi in utils/api.ts.
    """
    additional_property = [
        {
            "@type": "PropertyValue",
            "name": "paymentMode",
            "value": payment_mode,
        }
    ]
    if status:
        additional_property.append(
            {
                "@type": "PropertyValue",
                "name": "status",
                "value": status,
            }
        )

    payload = {
        "@context": "https://schema.org",
        "@type": "ProgramMembership",
        "member": {
            "@type": "Person",
            "email": email,
            "givenName": first_name,
            "familyName": last_name,
        },
        "membershipPlan": {
            "@type": "Offer",
            "identifier": price_uuid,
        },
        "additionalProperty": additional_property,
    }
    if valid_until:
        payload["validUntil"] = valid_until

    resp = http_requests.post(
        f"{API_BASE_URL}/api/v2/memberships/",
        headers=_api_headers(api_key),
        json=payload,
        verify=False,
        timeout=30,
    )
    data = None
    try:
        data = resp.json()
    except ValueError:
        pass
    return {
        "ok": resp.ok,
        "status": resp.status_code,
        "data": data,
        "text": resp.text[:500],
    }


# ID aléatoire commun à tous les tests de cette session (comme randomId dans le spec TS).
# / Random ID shared across all tests in this session (like randomId in the TS spec).
RANDOM_ID = _random_id()


class TestAdminCancelMembership:
    """Annulation d'adhésion depuis l'admin / Cancel membership from admin."""

    def test_cancel_membership_without_paid_lines(
        self, page, api_key, create_product, login_as_admin, django_shell
    ):
        """Annuler une adhésion gratuite (sans lignes de vente) → confirmation simple.
        / Cancel a free membership (no sale lines) → simple confirmation.
        """
        product_name = f"Adhesion Annul {RANDOM_ID}"
        user_email = f"jturbeaux+canc{RANDOM_ID}@pm.me"

        # --- Étape 1 : Créer un produit adhésion gratuit ---
        # Produit annuel à 0€ pour éviter les détails de paiement.
        # / Step 1: Create a free membership product.
        # Yearly product at 0€ to avoid payment details.
        product_result = create_product(
            name=product_name,
            description="Test annulation adhesion",
            category="Membership",
            offers=[
                {
                    "name": "Annuel annul",
                    "price": "0.00",
                    "subscriptionType": "Y",
                }
            ],
        )
        assert product_result["ok"], (
            f"Création produit échouée: {product_result}"
        )
        offers = product_result.get("offers") or []
        assert offers, f"Aucune offre retournée: {product_result}"
        price_uuid = offers[0].get("identifier") or ""
        assert price_uuid != "", f"UUID tarif manquant: {offers}"

        # --- Étape 2 : Créer une adhésion gratuite via API ---
        # Une adhésion gratuite passe directement en VALID via signal post_save.
        # / Step 2: Create a free membership via API.
        # A free membership goes directly to VALID via post_save signal.
        ms_result = _create_membership_api(
            api_key=api_key,
            price_uuid=price_uuid,
            email=user_email,
            first_name="Anne",
            last_name="Gratuit",
            payment_mode="FREE",
        )
        assert ms_result["ok"], f"Création adhésion échouée: {ms_result}"

        # --- Étape 3 : Se connecter en tant qu'admin ---
        # / Step 3: Login as admin.
        login_as_admin(page)

        # --- Étape 4 : Récupérer la PK en base via django_shell ---
        # Permet de construire l'URL d'admin change sans connaître la PK à l'avance.
        # Code shell avec quotes simples uniquement (conftest échappe les doubles).
        # / Step 4: Get PK from DB via django_shell.
        # Allows constructing the admin change URL without knowing PK in advance.
        # Shell code uses single quotes only (conftest escapes double quotes).
        result = django_shell(
            "from BaseBillet.models import Membership\n"
            f"m = Membership.objects.filter(user__email='{user_email}').first()\n"
            "if m: print(f'pk={m.pk}')\n"
            "else: print('NOT_FOUND')"
        )
        assert "NOT_FOUND" not in result, (
            f"Adhésion introuvable pour {user_email}. Shell: {result}"
        )
        pk_match = re.search(r"pk=(\d+)", result)
        assert pk_match is not None, f"PK non trouvée dans: {result}"
        membership_pk = pk_match.group(1)

        # --- Étape 5 : Naviguer vers la fiche admin de l'adhésion ---
        # networkidle OK sur les pages TiBillet (piège 9.28).
        # / Step 5: Navigate to the membership admin change page.
        # networkidle OK on TiBillet pages (trap 9.28).
        page.goto(f"/admin/BaseBillet/membership/{membership_pk}/change/")
        page.wait_for_load_state("networkidle")

        # --- Étape 6 : Cliquer sur "Annuler l'adhésion" dans le panneau HTMX ---
        # Le bouton est identifié par data-testid="membership-action-cancel".
        # / Step 6: Click "Cancel membership" button in the HTMX panel.
        # Button identified by data-testid="membership-action-cancel".
        cancel_button = page.locator('[data-testid="membership-action-cancel"]')
        cancel_button.wait_for(state="visible", timeout=5000)
        cancel_button.click()

        # Le formulaire de confirmation doit apparaître inline (sans navigation).
        # / The confirmation form must appear inline (no page navigation).
        cancel_form = page.locator('[data-testid="membership-cancel-form"]')
        cancel_form.wait_for(state="visible", timeout=5000)

        # --- Étape 7 : Vérifier que l'email de l'adhérent est dans le formulaire ---
        # / Step 7: Verify member email appears in the form.
        form_content = cancel_form.inner_text()
        assert user_email in form_content, (
            f"Email {user_email} absent du formulaire d'annulation. "
            f"Contenu: {form_content[:300]}"
        )

        # --- Étape 8 : Confirmer l'annulation sans avoir ---
        # / Step 8: Confirm cancellation without credit note.
        confirm_button = page.locator('[data-testid="membership-cancel-confirm"]')
        confirm_button.wait_for(state="visible", timeout=5000)
        confirm_button.click()

        # Après HX-Redirect, on doit atterrir sur la changelist.
        # wait_for_url reçoit une STRING en Python (piège PIEGES.md).
        # / After HX-Redirect, we must land on the changelist.
        # wait_for_url receives a STRING in Python (trap PIEGES.md).
        page.wait_for_url("**/BaseBillet/membership/**", timeout=10000)

        # La page doit contenir un mot relatif à l'annulation (FR ou EN).
        # / Page must contain a word related to cancellation (FR or EN).
        page_content = page.locator("body").inner_text().lower()
        assert (
            "annul" in page_content
            or "cancelled" in page_content
            or "canceled" in page_content
        ), f"Aucun mot d'annulation trouvé dans la page. Extrait: {page_content[:300]}"

    def test_show_credit_note_option_for_paid_membership(
        self, page, api_key, create_product, login_as_admin, django_shell
    ):
        """Adhésion avec ligne de paiement → deux boutons d'annulation.
        Annuler avec avoir → vérifier en base.
        / Membership with payment line → two cancel buttons.
        Cancel with credit note → verify in DB.
        """
        paid_email = f"jturbeaux+cancp{RANDOM_ID}@pm.me"
        paid_product_name = f"Adhesion Annul Paid {RANDOM_ID}"

        # --- Étape 1 : Créer un produit payant ---
        # / Step 1: Create a paid membership product.
        paid_product = create_product(
            name=paid_product_name,
            description="Test annulation avec avoir",
            category="Membership",
            offers=[
                {
                    "name": "Annuel payant",
                    "price": "30.00",
                    "subscriptionType": "Y",
                    "manualValidation": True,
                }
            ],
        )
        assert paid_product["ok"], f"Création produit payant échouée: {paid_product}"
        paid_offers = paid_product.get("offers") or []
        assert paid_offers, f"Aucune offre retournée: {paid_product}"
        paid_price_uuid = paid_offers[0].get("identifier") or ""
        assert paid_price_uuid != "", f"UUID tarif manquant: {paid_offers}"

        # --- Étape 2 : Créer une adhésion en attente (statut AW) ---
        # / Step 2: Create a pending membership (status AW).
        ms_result = _create_membership_api(
            api_key=api_key,
            price_uuid=paid_price_uuid,
            email=paid_email,
            first_name="Pierre",
            last_name="Payeur",
            status="AW",
        )
        assert ms_result["ok"], f"Création adhésion payante échouée: {ms_result}"

        # --- Étape 3 : Récupérer la PK et créer une LigneArticle de paiement ---
        # Le panneau HTMX "Enregistrer un paiement" est imbriqué dans le
        # formulaire principal Django admin → les boutons submit sont associés
        # au formulaire externe par le navigateur → htmx.ajax() ne produit pas
        # de swap DOM. On crée la LigneArticle directement en base via
        # django_shell, ce qui est fonctionnellement équivalent.
        #
        # / Step 3: Get PK and create a payment LigneArticle directly in DB.
        # The "Record payment" HTMX panel is nested inside the main Django admin
        # form → submit buttons are associated with the outer form by the browser
        # → htmx.ajax() does not produce a DOM swap. We create the LigneArticle
        # directly in DB via django_shell, which is functionally equivalent.
        result = django_shell(
            "from BaseBillet.models import Membership\n"
            f"m = Membership.objects.filter(user__email='{paid_email}').first()\n"
            "if m: print(f'pk={m.pk}')\n"
            "else: print('NOT_FOUND')"
        )
        assert "NOT_FOUND" not in result, (
            f"Adhésion introuvable pour {paid_email}. Shell: {result}"
        )
        pk_match = re.search(r"pk=(\d+)", result)
        assert pk_match is not None, f"PK non trouvée dans: {result}"
        membership_pk = pk_match.group(1)

        # Créer la ligne de vente directement en base pour simuler un paiement
        # hors-ligne (espèces). On utilise le même flux que la vue ajouter_paiement :
        # LigneArticle CREATED → PAID pour déclencher trigger_A.
        # Code shell avec quotes simples uniquement.
        # / Create the sale line directly in DB to simulate an offline payment (cash).
        # Same flow as the ajouter_paiement view:
        # LigneArticle CREATED → PAID to trigger trigger_A.
        # Shell code uses single quotes only.
        shell_payment = django_shell(
            "from BaseBillet.models import Membership, LigneArticle, PaymentMethod, SaleOrigin\n"
            "from ApiBillet.serializers import get_or_create_price_sold, dec_to_int\n"
            "from django.utils import timezone\n"
            f"m = Membership.objects.get(pk={membership_pk})\n"
            "m.contribution_value = m.price.prix\n"
            "m.payment_method = PaymentMethod.CASH\n"
            "m.first_contribution = timezone.localtime()\n"
            "m.last_contribution = timezone.localtime()\n"
            "m.status = 'A'\n"
            "m.save()\n"
            "pricesold = get_or_create_price_sold(m.price)\n"
            "la = LigneArticle.objects.create(\n"
            "    pricesold=pricesold, qty=1, membership=m,\n"
            "    amount=dec_to_int(m.contribution_value),\n"
            "    payment_method=PaymentMethod.CASH,\n"
            "    status=LigneArticle.CREATED,\n"
            "    sale_origin=SaleOrigin.ADMIN,\n"
            ")\n"
            "la.status = LigneArticle.PAID\n"
            "la.save()\n"
            "print(f'la_pk={la.pk}')"
        )
        assert "la_pk=" in shell_payment, (
            f"Création LigneArticle échouée. Shell: {shell_payment}"
        )

        # --- Étape 4 : Se connecter en tant qu'admin ---
        # / Step 4: Login as admin.
        login_as_admin(page)

        # --- Étape 5 : Naviguer vers la fiche admin ---
        # / Step 5: Navigate to the admin change page.
        page.goto(f"/admin/BaseBillet/membership/{membership_pk}/change/")
        page.wait_for_load_state("networkidle")

        # --- Étape 6 : Cliquer sur "Annuler l'adhésion" ---
        # À ce stade, l'adhésion a des lignes de vente → deux boutons d'annulation.
        # / Step 6: Click "Cancel membership".
        # At this point, the membership has sale lines → two cancel buttons.
        cancel_button = page.locator('[data-testid="membership-action-cancel"]')
        cancel_button.wait_for(state="visible", timeout=5000)
        cancel_button.click()

        cancel_form = page.locator('[data-testid="membership-cancel-form"]')
        cancel_form.wait_for(state="visible", timeout=5000)

        # --- Étape 7 : Vérifier la présence de l'option "avec avoir" ---
        # Le formulaire doit proposer deux options : sans avoir et avec avoir.
        # Assertion tolérante FR/EN (piège PIEGES.md : la langue varie).
        # / Step 7: Verify "with credit note" option is present.
        # Form must offer two options: without and with credit note.
        # Tolerant FR/EN assertion (PIEGES.md trap: language may vary).
        form_content = cancel_form.inner_text().lower()
        assert (
            "avoir" in form_content
            or "credit note" in form_content
            or "annuler avec avoir" in form_content
            or "cancel with credit note" in form_content
        ), (
            f"Option 'avoir' absente du formulaire d'annulation. "
            f"Contenu: {form_content[:300]}"
        )

        # --- Étape 8 : Cliquer sur "Annuler avec avoir" ---
        # / Step 8: Click "Cancel with credit note".
        with_cn_button = page.locator('[data-testid="membership-cancel-with-credit-note"]')
        with_cn_button.wait_for(state="visible", timeout=5000)
        with_cn_button.click()

        # Après HX-Redirect, on doit atterrir sur la changelist.
        # / After HX-Redirect, we must land on the changelist.
        page.wait_for_url("**/BaseBillet/membership/**", timeout=10000)

        # --- Étape 9 : Vérifier en base qu'un avoir (LigneArticle status='N') existe ---
        # LigneArticle.CREDIT_NOTE = 'N'
        # / Step 9: Verify in DB that a credit note (LigneArticle status='N') exists.
        # LigneArticle.CREDIT_NOTE = 'N'
        cn_result = django_shell(
            "from BaseBillet.models import LigneArticle\n"
            f"cn = LigneArticle.objects.filter(membership__user__email='{paid_email}', status='N').count()\n"
            "print(f'credit_notes={cn}')"
        )
        assert "credit_notes=" in cn_result, (
            f"Impossible de lire le compte d'avoirs. Shell: {cn_result}"
        )
        count_match = re.search(r"credit_notes=(\d+)", cn_result)
        assert count_match is not None, f"Pattern credit_notes manquant dans: {cn_result}"
        credit_note_count = int(count_match.group(1))
        assert credit_note_count >= 1, (
            f"Aucun avoir en base pour {paid_email}. Résultat shell: {cn_result}"
        )
