"""
Tests E2E : création du produit d'adhésion récurrente via l'admin.
/ E2E tests: creation of recurring membership product via admin.

Conversion de tests/playwright/tests/04-membership-recurring.spec.ts

Ce test vérifie que :
/ This test verifies that:
- Un admin peut créer un produit d'adhésion récurrente via le proxy MembershipProduct
  / An admin can create a recurring membership product via the MembershipProduct proxy
- Deux tarifs à PAIEMENT RÉCURRENT (case « Paiement récurrent » cochée) peuvent être
  ajoutés en inline : "Journalière" (2€, D) et "Mensuelle" (20€, M), et la base les
  enregistre bien comme récurrents
  / Two RECURRING-PAYMENT prices can be added inline and are stored as recurring
- Le produit est visible sur la page publique /memberships/
  / The product is visible on the public /memberships/ page

Le produit porte un nom UNIQUE par run, et il est supprimé en fin de test (base de dev
partagée, sans rollback). Avant, le test éditait un produit de référence s'il existait
(2 tarifs de plus à chaque run), ne cochait jamais « Paiement récurrent », et ne
vérifiait qu'un nom sur la page publique.
/ The product has a UNIQUE name per run and is deleted at the end (shared dev DB).
"""

import uuid

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _add_inline_price(page, price_data):
    """Ajoute un tarif dans l'inline #prices-group du formulaire admin produit.
    / Adds a price in the admin product form's #prices-group inline.

    Clique sur "Add another" (bouton a.add-row dans #prices-group), puis remplit
    le nouveau rang selon l'index détecté avant le clic.
    / Clicks "Add another" (a.add-row button in #prices-group), then fills
    the new row using the index detected before the click.

    price_data dict attendu / expected:
    - name (str)              : libellé du tarif
    - prix (int)              : montant entier (pas de virgule — locale FR)
    - subscription_type (str) : 'D' | 'M' | 'Y' | ...
    Le paiement récurrent est TOUJOURS coché : c'est l'objet de ce fichier.
    / Recurring payment is ALWAYS checked: it is what this file is about.
    """
    prices_section = page.locator('#prices-group')

    # Compter les lignes existantes (hors template __prefix__) pour calculer l'index.
    # / Count existing rows (excluding __prefix__ template) to compute the index.
    count_before = prices_section.locator(
        'input[name^="prices-"][name$="-name"]:not([name*="__prefix__"])'
    ).count()

    # Cliquer sur le bouton d'ajout inline.
    # / Click the inline add button.
    add_button = prices_section.locator('a.add-row').first
    add_button.click()

    # Attendre que le nouveau champ name soit visible.
    # / Wait for the new name field to become visible.
    form_index = count_before
    name_input = prices_section.locator(f'input[name="prices-{form_index}-name"]')
    name_input.wait_for(state='visible', timeout=5_000)

    # Remplir le libellé du tarif.
    # / Fill the price label.
    name_input.fill(price_data['name'])

    # Remplir le montant en entier (évite le problème de séparateur décimal FR).
    # / Fill the amount as integer (avoids FR decimal separator issue).
    prices_section.locator(
        f'input[name="prices-{form_index}-prix"]'
    ).fill(str(price_data['prix']))

    # Sélectionner le type d'abonnement récurrent (D=quotidien, M=mensuel, Y=annuel…).
    # / Select the recurring subscription type (D=daily, M=monthly, Y=annual…).
    prices_section.locator(
        f'select[name="prices-{form_index}-subscription_type"]'
    ).select_option(price_data['subscription_type'])

    # Cocher « Paiement récurrent » (prélèvement Stripe à chaque échéance).
    # / Check "Recurring payment" (Stripe charge at every due date).
    case_recurrente = prices_section.locator(f'input[name="prices-{form_index}-recurring_payment"]')
    expect(case_recurrente).to_have_count(1)
    case_recurrente.check()


class TestMembershipRecurringCreate:
    """Création du produit d'adhésion récurrente via le proxy admin MembershipProduct.
    / Creation of recurring membership product via the MembershipProduct admin proxy.
    """

    def test_create_adhesion_recurrente_le_tiers_lustre(self, page, login_as_admin, django_shell):
        """Crée "Adhésion récurrente (Le Tiers-Lustre) <suffixe>" avec 2 tarifs récurrents,
        vérifie la base et /memberships/.
        / Creates the product with 2 recurring prices, checks the database and /memberships/.
        """
        nom_du_produit = f"Adhésion récurrente (Le Tiers-Lustre) {uuid.uuid4().hex[:6]}"
        try:
            # --- Étape 1 : Connexion admin, formulaire de création ---
            # Le proxy MembershipProduct fixe la catégorie ADHESION (champ caché).
            # / Step 1: admin login, creation form. The proxy sets the ADHESION category.
            login_as_admin(page)
            page.goto('/admin/BaseBillet/membershipproduct/add/')
            page.wait_for_load_state('networkidle')

            # --- Étape 2 : Informations de base ---
            # / Step 2: basic info
            page.locator('input[name="name"]').fill(nom_du_produit)
            page.locator('input[name="short_description"]').first.fill(
                'Adhésion avec paiements récurrents'
            )

            # --- Étape 3 : Deux tarifs à paiement récurrent ---
            # / Step 3: two recurring-payment prices
            _add_inline_price(page, {'name': 'Journalière', 'prix': 2, 'subscription_type': 'D'})
            _add_inline_price(page, {'name': 'Mensuelle', 'prix': 20, 'subscription_type': 'M'})

            # --- Étape 4 : Enregistrer ---
            # / Step 4: save
            page.locator('[name="_save"]').first.click()
            page.wait_for_load_state('networkidle')

            # --- Étape 5 : La base porte exactement ce qu'on a saisi ---
            # Un produit d'adhesion, deux tarifs, TOUS DEUX a paiement recurrent.
            # / Step 5: one membership product, two prices, BOTH with recurring payment.
            sortie = django_shell(
                "from BaseBillet.models import Product\n"
                f"produits = Product.objects.filter(name='{nom_du_produit}')\n"
                "print('NOMBRE=' + str(produits.count()))\n"
                "p = produits.first()\n"
                "print('CATEGORIE=' + str(p.categorie_article if p else None))\n"
                "tarifs = sorted((t.name, int(t.prix), t.subscription_type, t.recurring_payment) "
                "for t in p.prices.all()) if p else []\n"
                "print('TARIFS=' + repr(tarifs))"
            )
            assert "NOMBRE=1" in sortie, f"Produit non enregistre (ou en double) : {sortie[-300:]}"
            assert "CATEGORIE=A" in sortie, f"Le produit n'est pas une adhesion : {sortie[-300:]}"
            assert (
                "TARIFS=[('Journalière', 2, 'D', True), ('Mensuelle', 20, 'M', True)]" in sortie
            ), f"Les tarifs enregistres ne sont pas ceux saisis (recurrence comprise) : {sortie[-300:]}"

            # --- Étape 6 : Le produit est proposé sur /memberships/ ---
            # / Step 6: the product is offered on /memberships/
            page.goto('/memberships/')
            page.wait_for_load_state('networkidle')
            carte = page.locator('[data-testid^="membership-card-"]').filter(has_text=nom_du_produit)
            expect(carte).to_be_visible()
        finally:
            # Nettoyage : les tarifs d'abord (Price.product est PROTECT), puis le produit.
            # / Cleanup: prices first (Price.product is PROTECT), then the product.
            django_shell(
                "from BaseBillet.models import Price, Product\n"
                f"Price.objects.filter(product__name='{nom_du_produit}').delete()\n"
                f"Product.objects.filter(name='{nom_du_produit}').delete()"
            )
