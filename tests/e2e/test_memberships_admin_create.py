"""
Tests E2E : création du produit d'adhésion via l'admin — "Adhésion (Le Tiers-Lustre)".
/ E2E tests: creation of membership product via admin — "Adhésion (Le Tiers-Lustre)".

Conversion de tests/playwright/tests/03-memberships.spec.ts

Ce test vérifie que :
/ This test verifies that:
- Un admin peut créer un produit d'adhésion via le proxy MembershipProduct
  / An admin can create a membership product via the MembershipProduct proxy
- Deux tarifs peuvent être ajoutés en inline : "Annuelle" (20€, Y) et "Mensuelle" (2€, M)
  / Two prices can be added inline: "Annuelle" (20€, Y) and "Mensuelle" (2€, M)
- Le produit est visible sur la page publique /memberships/
  / The product is visible on the public /memberships/ page

Le produit porte un nom UNIQUE par run, et il est supprimé en fin de test (base de dev
partagée, sans rollback). Avant, le test éditait un produit de référence s'il existait :
chaque run lui ajoutait 2 tarifs (8 au 2026-09-27), et la vérification ne portait que sur
un nom présent dans d'autres produits.
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
    - name (str) : libellé du tarif
    - prix (float/int) : montant
    - subscription_type (str) : 'Y' | 'M' | ...
    - free_price (bool, optionnel) : prix libre
    """
    prices_section = page.locator('#prices-group')

    # Compter les lignes de tarifs existantes avant le clic pour calculer l'index.
    # On se base sur l'input "name" (pas __prefix__) pour éviter de compter le
    # template de formulaire vide.
    # / Count existing price rows before click to compute the index.
    # Based on the "name" input (excluding __prefix__) to avoid counting the
    # empty form template.
    count_before = prices_section.locator(
        'input[name^="prices-"][name$="-name"]:not([name*="__prefix__"])'
    ).count()

    # Cliquer sur le bouton d'ajout de l'inline prices.
    # / Click the add button of the prices inline.
    add_button = prices_section.locator('a.add-row').first
    add_button.click()

    # Attendre que le nouveau champ name soit visible.
    # / Wait for the new name field to become visible.
    form_index = count_before
    name_input = prices_section.locator(f'input[name="prices-{form_index}-name"]')
    name_input.wait_for(state='visible', timeout=5_000)

    # Remplir le nom du tarif.
    # / Fill the price name.
    name_input.fill(price_data['name'])

    # Remplir le montant. Locale FR : l'input peut afficher '0,00' mais on passe
    # un entier pour éviter les problèmes de séparateur décimal.
    # / Fill the amount. FR locale: input may show '0,00' but we pass an integer
    # to avoid decimal separator issues.
    price_input = prices_section.locator(f'input[name="prices-{form_index}-prix"]')
    price_input.fill(str(price_data['prix']))

    # Sélectionner le type d'abonnement (Y=annuel, M=mensuel, etc.).
    # / Select the subscription type (Y=annual, M=monthly, etc.).
    prices_section.locator(
        f'select[name="prices-{form_index}-subscription_type"]'
    ).select_option(price_data['subscription_type'])

    # Cocher "prix libre" si demandé.
    # / Check "free price" if requested.
    if price_data.get('free_price'):
        prices_section.locator(
            f'input[name="prices-{form_index}-free_price"]'
        ).check()


class TestMembershipsAdminCreate:
    """Création du produit d'adhésion via le proxy admin MembershipProduct.
    / Creation of membership product via the MembershipProduct admin proxy.
    """

    def test_create_product_adhesion_le_tiers_lustre(self, page, login_as_admin, django_shell):
        """Crée "Adhésion (Le Tiers-Lustre) <suffixe>" avec 2 tarifs, vérifie la base et /memberships/.
        / Creates the product with 2 prices, checks the database and /memberships/.
        """
        nom_du_produit = f"Adhésion (Le Tiers-Lustre) {uuid.uuid4().hex[:6]}"
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
                'Adhérez au collectif Le Tiers-Lustre'
            )

            # --- Étape 3 : Deux tarifs en inline ---
            # / Step 3: two inline prices
            _add_inline_price(page, {'name': 'Annuelle', 'prix': 20, 'subscription_type': 'Y'})
            _add_inline_price(page, {'name': 'Mensuelle', 'prix': 2, 'subscription_type': 'M'})

            # --- Étape 4 : Enregistrer ---
            # / Step 4: save
            page.locator('[name="_save"]').first.click()
            page.wait_for_load_state('networkidle')

            # --- Étape 5 : La base porte exactement ce qu'on a saisi ---
            # Un produit, de categorie adhesion, avec EXACTEMENT ces deux tarifs.
            # / Step 5: the database holds exactly what was typed.
            sortie = django_shell(
                "from BaseBillet.models import Product\n"
                f"produits = Product.objects.filter(name='{nom_du_produit}')\n"
                "print('NOMBRE=' + str(produits.count()))\n"
                "p = produits.first()\n"
                "print('CATEGORIE=' + str(p.categorie_article if p else None))\n"
                "tarifs = sorted((t.name, int(t.prix), t.subscription_type) for t in p.prices.all()) if p else []\n"
                "print('TARIFS=' + repr(tarifs))"
            )
            assert "NOMBRE=1" in sortie, f"Produit non enregistre (ou en double) : {sortie[-300:]}"
            assert "CATEGORIE=A" in sortie, f"Le produit n'est pas une adhesion : {sortie[-300:]}"
            assert "TARIFS=[('Annuelle', 20, 'Y'), ('Mensuelle', 2, 'M')]" in sortie, (
                f"Les tarifs enregistres ne sont pas ceux saisis : {sortie[-300:]}"
            )

            # --- Étape 6 : Le produit est proposé sur /memberships/ ---
            # La carte du composant cotton/V2/membership_card.html, filtrée sur CE nom.
            # / Step 6: the product is offered on /memberships/ (V2 card, THIS name).
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
