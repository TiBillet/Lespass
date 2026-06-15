"""
Tests E2E : avoir comptable (credit note) sur LigneArticle depuis l'admin.
/ E2E tests: accounting credit note on LigneArticle from the admin.

Conversion de tests/playwright/tests/32-admin-credit-note.spec.ts

Scenarios :
1. Emettre un avoir sur une ligne VALID -> succes, ligne negative creee.
2. Tenter un 2e avoir sur la meme ligne -> erreur "already exists".

Strategie : on cree une adhesion gratuite (qui genere une LigneArticle VALID),
puis on emet un avoir dessus depuis l'URL emettre_avoir dans l'admin.
/ Strategy: create a free membership (generates a VALID LigneArticle),
then issue a credit note from the admin emettre_avoir URL.
"""

import datetime
import os
import random
import shutil
import string

import pytest
import requests as http_requests


pytestmark = pytest.mark.e2e


# --- Configuration URL pour les appels API directs ---
# Meme logique que tests/e2e/conftest.py : depuis le container, on passe par
# le Docker gateway (Traefik) avec un header Host ; depuis l'hote, URL directe.
# / Same logic as tests/e2e/conftest.py: from container, go through the
# Docker gateway (Traefik) with a Host header; from host, direct URL.
SUB = os.environ.get("SUB", "lespass")
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
DOCKER_GATEWAY = os.environ.get("DOCKER_GATEWAY", "172.17.0.1")
INSIDE_CONTAINER = shutil.which("docker") is None
API_BASE_URL = f"https://{DOCKER_GATEWAY}" if INSIDE_CONTAINER else f"https://{SUB}.{DOMAIN}"
API_HOST_HEADER = f"{SUB}.{DOMAIN}" if INSIDE_CONTAINER else None


def _random_id():
    """Genere un suffixe unique (DB dev partagee, pas de rollback).
    / Generates a unique suffix (shared dev DB, no rollback).
    """
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _api_headers(api_key):
    """Construit les headers d'authentification API v2.
    / Builds API v2 authentication headers.
    """
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    if API_HOST_HEADER:
        headers["Host"] = API_HOST_HEADER
    return headers


def _create_membership_api(api_key, price_uuid, email, first_name="Credit", last_name="Note", payment_mode="FREE"):
    """Cree une adhesion via POST /api/v2/memberships/ (schema.org ProgramMembership).
    Equivalent de createMembershipApi dans tests/playwright/tests/utils/api.ts.
    / Creates a membership via POST /api/v2/memberships/ (schema.org ProgramMembership).
    Equivalent of createMembershipApi in tests/playwright/tests/utils/api.ts.
    """
    # validUntil : dans 365 jours (abonnement annuel)
    # / validUntil: in 365 days (yearly subscription)
    valid_until = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
    ).isoformat()

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
        "validUntil": valid_until,
        "additionalProperty": [
            {
                "@type": "PropertyValue",
                "name": "paymentMode",
                "value": payment_mode,
            },
        ],
    }
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
    return {"ok": resp.ok, "status": resp.status_code, "data": data, "text": resp.text[:500]}


class TestAdminCreditNote:
    """Avoir comptable admin / Admin credit note."""

    def test_create_and_block_duplicate_credit_note(
        self, page, login_as_admin, django_shell, api_key, create_product
    ):
        """Cree un avoir sur une LigneArticle VALID puis bloque un double avoir.
        / Creates a credit note on a VALID LigneArticle then blocks a duplicate.
        """
        random_id = _random_id()
        product_name = f"Adhesion CN {random_id}"
        user_email = f"jturbeaux+cn{random_id}@pm.me"

        # --- Etape 0 : Creer un produit adhesion gratuit ---
        # Un produit adhesion gratuit genere automatiquement une LigneArticle
        # avec status VALID lorsqu'on cree une adhesion via l'API.
        # / Step 0: Create a free membership product.
        # A free membership product automatically generates a VALID LigneArticle
        # when a membership is created via the API.
        product_result = create_product(
            name=product_name,
            description="Produit pour test avoir",
            category="Membership",
            offers=[{"name": "Gratuit CN", "price": "0.00", "subscriptionType": "Y"}],
        )
        assert product_result["ok"], (
            f"Creation du produit adhesion echouee : {product_result}"
        )
        offers = product_result.get("offers") or []
        assert offers, f"Aucune offre retournee par l'API : {product_result}"
        price_uuid = offers[0].get("identifier") or ""
        assert price_uuid != "", f"UUID du tarif manquant : {offers}"

        # --- Etape 1 : Creer une adhesion gratuite via API ---
        # Cela genere une LigneArticle avec status VALID (ou PAID=P) en base.
        # / Step 1: Create a free membership via API.
        # This generates a LigneArticle with VALID (or PAID=P) status in DB.
        ms_result = _create_membership_api(
            api_key=api_key,
            price_uuid=price_uuid,
            email=user_email,
            first_name="Credit",
            last_name="Note",
            payment_mode="FREE",
        )
        assert ms_result["ok"], (
            f"Creation de l'adhesion echouee : {ms_result}"
        )

        # --- Etape 2 : Recuperer le PK de la LigneArticle VALID en base ---
        # On force le status a 'V' (VALID) si seule une ligne 'P' existe,
        # pour s'assurer que l'action emettre_avoir peut s'executer.
        # La fixture django_shell echappe les guillemets DOUBLES → quotes simples uniquement.
        # / Step 2: Get the PK of the VALID LigneArticle from DB.
        # We force status to 'V' (VALID) if only a 'P' line exists,
        # to ensure emettre_avoir can run.
        # django_shell escapes DOUBLE quotes → single quotes only.
        db_result = django_shell(
            "from BaseBillet.models import LigneArticle\n"
            f"ligne = LigneArticle.objects.filter(membership__user__email='{user_email}', status__in=['V', 'P']).first()\n"
            "if not ligne:\n"
            f"    ligne = LigneArticle.objects.filter(membership__user__email='{user_email}').first()\n"
            "    if ligne:\n"
            "        ligne.status = 'V'\n"
            "        ligne.save(update_fields=['status'])\n"
            "if ligne:\n"
            "    print(f'pk={ligne.pk}')\n"
            "    print(f'status={ligne.status}')\n"
            "else:\n"
            "    print('NOT_FOUND')\n"
        )
        assert "NOT_FOUND" not in db_result, (
            f"LigneArticle introuvable pour {user_email} : {db_result}"
        )
        pk_match = None
        for line in db_result.splitlines():
            if line.startswith("pk="):
                pk_match = line.split("=", 1)[1].strip()
                break
        assert pk_match is not None, (
            f"PK de la LigneArticle non trouve dans : {db_result}"
        )
        ligne_pk = pk_match

        # --- Etape 3 : Se connecter en admin et emettre un avoir ---
        # On appelle directement l'URL emettre_avoir qui effectue l'action et
        # redirige vers la changelist avec un message de succes.
        # / Step 3: Login as admin and issue a credit note.
        # We call the emettre_avoir URL directly — it performs the action and
        # redirects to the changelist with a success message.
        login_as_admin(page)

        page.goto(f"/admin/BaseBillet/lignearticle/{ligne_pk}/emettre_avoir/")
        page.wait_for_load_state("networkidle")

        # Verifier le message de succes (FR ou EN selon la langue active)
        # / Check success message (FR or EN depending on active language)
        page_content = page.inner_text("body")
        avoir_created = (
            "credit note created" in page_content.lower()
            or "avoir cr" in page_content.lower()
        )
        assert avoir_created, (
            f"Message de succes pour l'avoir non trouve. Contenu : {page_content[:500]}"
        )

        # --- Etape 4 : Verifier en base qu'on a bien une ligne CREDIT_NOTE ---
        # La ligne avoir doit avoir status='N' et qty negative.
        # / Step 4: Verify in DB we have a CREDIT_NOTE line (status='N', negative qty).
        cn_result = django_shell(
            "from BaseBillet.models import LigneArticle\n"
            f"cn = LigneArticle.objects.filter(credit_note_for__membership__user__email='{user_email}', status='N')\n"
            "for l in cn:\n"
            "    print(f'cn_pk={l.pk} qty={l.qty} status={l.status}')\n"
            "print(f'count={cn.count()}')\n"
        )
        assert "count=1" in cn_result, (
            f"Attendu exactement 1 ligne credit note, obtenu : {cn_result}"
        )
        assert "qty=-" in cn_result, (
            f"La quantite de l'avoir devrait etre negative : {cn_result}"
        )

        # --- Etape 4b : Verifier les lignes dans la changelist admin ---
        # On filtre par nom de produit (unique) pour ne voir que nos lignes.
        # On attend au moins 2 lignes : ligne originale + avoir.
        # / Step 4b: Verify lines in the admin changelist.
        # Filter by product name (unique) to see only our lines.
        # We expect at least 2 rows: original line + credit note.
        page.goto("/admin/BaseBillet/lignearticle/")
        page.wait_for_load_state("networkidle")

        search_input = page.locator('input[name="q"]').first
        search_input.fill(product_name)
        search_input.press("Enter")
        page.wait_for_load_state("networkidle")

        rows = page.locator("#result_list tbody tr")
        row_count = rows.count()
        assert row_count >= 2, (
            f"Attendu >= 2 lignes (originale + avoir), obtenu : {row_count}"
        )

        # Verifier la presence des statuts CONFIRMED (Confirmé) et CREDIT NOTE (Avoir)
        # Unfold rend les statuts comme texte de badge via get_status_display().
        # En FR : 'Confirmé', 'Avoir'. En EN : 'Confirmed', 'Credit note'.
        # On cherche le texte dans le HTML source (plus fiable que inner_text sur badges).
        # / Check CONFIRMED (Confirmé) and CREDIT NOTE (Avoir) statuses.
        # Unfold renders statuses as badge text via get_status_display().
        # FR: 'Confirmé', 'Avoir'. EN: 'Confirmed', 'Credit note'.
        # We search the HTML source (more reliable than inner_text for badges).
        page_html = page.content()
        has_confirmed = (
            "CONFIRMED" in page_html
            or "Confirmed" in page_html
            or "Confirm" in page_html
            or "Confirmé" in page_html
            or "confirm" in page_html.lower()
        )
        has_credit_note = (
            "CREDIT NOTE" in page_html
            or "Credit note" in page_html
            or "credit note" in page_html.lower()
            or "Avoir" in page_html
            or "avoir" in page_html
        )
        assert has_confirmed, (
            f"Badge CONFIRMED introuvable dans la changelist. HTML extrait : {page_html[2000:3000]}"
        )
        assert has_credit_note, (
            f"Badge CREDIT NOTE introuvable dans la changelist. HTML extrait : {page_html[2000:3000]}"
        )

        # --- Etape 5 : Tenter un 2e avoir -> doit etre bloque ---
        # L'action doit detecter que l'avoir existe deja et afficher
        # "already exists" ou "existe deja" dans le message d'erreur.
        # / Step 5: Try a 2nd credit note -> must be blocked.
        # The action must detect the credit note already exists and display
        # "already exists" or "existe deja" in the error message.
        page.goto(f"/admin/BaseBillet/lignearticle/{ligne_pk}/emettre_avoir/")
        page.wait_for_load_state("networkidle")

        page_content_2 = page.inner_text("body")
        is_blocked = (
            "already exists" in page_content_2.lower()
            or "existe deja" in page_content_2.lower()
            or "existe déjà" in page_content_2.lower()
        )
        assert is_blocked, (
            f"Le 2e avoir devrait etre bloque. Contenu : {page_content_2[:500]}"
        )
