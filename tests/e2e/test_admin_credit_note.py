"""
Tests E2E : avoir comptable (credit note) sur un article depuis la fiche « Vente ».
/ E2E tests: accounting credit note on one item from the admin "Sale" page.

Conversion de tests/playwright/tests/32-admin-credit-note.spec.ts

Scenarios :
1. Emettre un avoir sur une ligne VALID -> succes, ligne negative creee.
2. Tenter un 2e avoir sur la meme ligne -> refus « deja remboursee en totalite ».

Strategie : on cree une adhesion gratuite (qui genere une LigneArticle VALID dans une
vente), puis on emet un avoir dessus par l'ecran « Avoir sur un article » de la fiche
de sa vente (l'ecran s'ouvre, l'admin valide toute la quantite).
/ Strategy: create a free membership (generates a VALID LigneArticle in a sale),
then issue a credit note through the sale page "Credit note on one item" screen.
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
        # On force le status a 'V' (VALID) si seule une ligne 'P' existe. On lit
        # aussi sa vente : l'avoir se fait depuis la fiche de la vente.
        # / Step 2: Get the PK of the VALID LigneArticle and its sale from DB.
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
            "    print(f'vente={ligne.vente_id}')\n"
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
        vente_pk = None
        for line in db_result.splitlines():
            if line.startswith("vente="):
                vente_pk = line.split("=", 1)[1].strip()
        assert vente_pk not in (None, "None"), (
            f"La LigneArticle n'a pas de vente : {db_result}"
        )
        adresse_de_l_avoir = (
            f"/admin/BaseBillet/vente/{vente_pk}/avoir_sur_un_article/?ligne={ligne_pk}"
        )

        # --- Etape 3 : Se connecter en admin et emettre un avoir ---
        # L'ecran « Avoir sur un article » de la fiche de la vente, pour cette ligne
        # (GET). L'adhesion est gratuite, au moyen « offert » : la ligne est
        # entierement offerte, l'ecran n'a donc PAS de champ « Rembourse par ».
        # L'admin valide la quantite proposee (toute la ligne) : la vue ecrit l'avoir
        # et ouvre la fiche de la vente d'avoir, avec un message de succes.
        # / Step 3: open the sale page "Credit note on one item" screen for the line.
        # Free membership: no "Refunded by" field. Confirm: the credit note is written
        # and the credit note sale page opens with a success message.
        login_as_admin(page)

        page.goto(adresse_de_l_avoir)
        page.wait_for_load_state("networkidle")
        assert page.locator('[data-testid="avoir-article-ecran"]').is_visible(), (
            f"Ecran d'avoir non affiche. Contenu : {page.inner_text('body')[:500]}"
        )
        assert page.locator('[data-testid="avoir-moyen-rembourse"]').count() == 0, (
            "Une ligne entierement offerte ne doit pas proposer « Rembourse par »."
        )

        page.locator('[data-testid="avoir-valider"]').click()
        page.wait_for_load_state("networkidle")

        # Verifier le message de succes (FR ou EN selon la langue active)
        # / Check success message (FR or EN depending on active language)
        page_content = page.inner_text("body")
        avoir_created = "avoir émis" in page_content.lower()
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

        # --- Etape 4b : Verifier les ventes dans la liste des ventes ---
        # On cherche par l'e-mail de l'adherent (client des deux ventes). On attend
        # au moins 2 ventes : la vente d'origine et la vente d'avoir, chacune avec
        # son badge de nature (« Vente » / « Avoir »).
        # / Step 4b: the sales list, searched by the member e-mail: the original
        # sale and the credit note sale, with their nature badges.
        page.goto(f"/admin/BaseBillet/vente/?q={user_email}")
        page.wait_for_load_state("networkidle")

        rows = page.locator("#result_list tbody tr")
        row_count = rows.count()
        assert row_count >= 2, (
            f"Attendu >= 2 ventes (originale + avoir), obtenu : {row_count}"
        )
        # Les badges de la colonne « Nature », en FR ou en EN, quelle que soit la casse.
        # / The "Nature" column badges, FR or EN, any case.
        natures_affichees = []
        for cellule in page.locator("td.field-nature_affichee").all():
            natures_affichees.append(cellule.inner_text().strip().lower())
        has_sale = "vente" in natures_affichees or "sale" in natures_affichees
        has_credit_note = "avoir" in natures_affichees or "credit note" in natures_affichees
        assert has_sale, f"Badge « Vente » introuvable : {natures_affichees}"
        assert has_credit_note, f"Badge « Avoir » introuvable : {natures_affichees}"

        # --- Etape 5 : Tenter un 2e avoir -> doit etre bloque ---
        # Tout est deja rendu : l'ecran ne s'ouvre pas, la fiche de la vente
        # s'affiche avec « deja remboursee en totalite ».
        # / Step 5: Try a 2nd credit note -> must be blocked: everything is already
        # given back, the sale page shows the refusal.
        page.goto(adresse_de_l_avoir)
        page.wait_for_load_state("networkidle")

        page_content_2 = page.inner_text("body")
        is_blocked = "déjà remboursée en totalité" in page_content_2.lower()
        assert is_blocked, (
            f"Le 2e avoir devrait etre bloque. Contenu : {page_content_2[:500]}"
        )
