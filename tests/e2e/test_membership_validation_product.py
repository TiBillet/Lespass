"""
Tests E2E : création du produit d'adhésion à validation sélective via l'admin.
/ E2E tests: creation of selective-validation membership product via admin.

Conversion de tests/playwright/tests/05-membership-validation.spec.ts

Ce test vérifie que :
/ This test verifies that:
- Un admin peut créer un produit d'adhésion "Adhésion à validation sélective
  (Le Tiers-Lustre) <suffixe>" via le proxy MembershipProduct.
  / An admin can create a selective-validation membership product via the proxy.
- Deux tarifs peuvent être ajoutés en inline : "Solidaire" (2€, Y, validation manuelle
  COCHÉE) et "Plein tarif" (30€, Y, sans validation), et la base les enregistre ainsi.
  / Two prices: "Solidaire" (manual validation CHECKED) and "Plein tarif" (without).
- Le produit est visible sur la page publique /memberships/.
  / The product is visible on the public /memberships/ page.

Le produit porte un nom UNIQUE par run, et il est supprimé en fin de test (base de dev
partagée, sans rollback). Le produit de référence "Adhésion à validation sélective
(Le Tiers-Lustre)", créé par demo_data_v2 et utilisé par test_membership_fix_solidaire.py,
n'est plus touché. Avant, le test l'éditait (2 tarifs de plus à chaque run), ne cochait
jamais la validation manuelle, et ne vérifiait qu'un nom sur la page publique.
/ The product has a UNIQUE name per run and is deleted at the end; the seeded
reference product is no longer touched.
"""

import uuid

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e

PREFIXE_DU_PRODUIT = "Adhésion à validation sélective (Le Tiers-Lustre)"


def _add_inline_price(page, price_data):
    """Ajoute un tarif dans l'inline #prices-group du formulaire admin produit.
    / Adds a price in the admin product form's #prices-group inline.

    Clique sur "Add another" (bouton a.add-row dans #prices-group), puis remplit
    le nouveau rang selon l'index détecté avant le clic.
    / Clicks "Add another" (a.add-row button in #prices-group), then fills
    the new row using the index detected before the click.

    price_data dict attendu / expected:
    - name (str)              : libellé du tarif
    - prix (int)              : montant (entier pour éviter problèmes de locale FR)
    - subscription_type (str) : 'Y' | 'M' | ...
    - manual_validation (bool, optionnel) : cocher « Validation manuelle requise »
    """
    prices_section = page.locator('#prices-group')

    # Compter les lignes de tarifs existantes avant le clic pour calculer l'index.
    # On se base sur l'input "name" (pas __prefix__) pour éviter de compter le
    # template de formulaire vide.
    # / Count existing price rows before click to compute the index.
    # Based on "name" input (excluding __prefix__) to avoid counting empty template.
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

    # Cocher « Validation manuelle requise » quand le tarif l'exige : l'adhesion
    # attend alors l'accord d'un admin avant tout paiement.
    # / Check "Manual validation required" when the price needs it.
    if price_data.get('manual_validation'):
        case_validation = prices_section.locator(
            f'input[name="prices-{form_index}-manual_validation"]'
        )
        expect(case_validation).to_have_count(1)
        case_validation.check()


class TestMembershipValidationProduct:
    """Création du produit d'adhésion à validation sélective via le proxy admin.
    / Creation of selective-validation membership product via the admin proxy.
    """

    def test_create_adhesion_validation_selective_with_2_prices(
        self, page, login_as_admin, django_shell
    ):
        """Crée le produit avec 2 tarifs (dont un à validation manuelle), vérifie la base
        et /memberships/.
        / Creates the product with 2 prices (one with manual validation), checks the
        database and /memberships/.
        """
        nom_du_produit = f"{PREFIXE_DU_PRODUIT} {uuid.uuid4().hex[:6]}"
        try:
            # --- Étape 1 : Connexion admin, formulaire de création ---
            # / Step 1: admin login, creation form
            login_as_admin(page)
            page.goto('/admin/BaseBillet/membershipproduct/add/')
            page.wait_for_load_state('networkidle')

            # --- Étape 2 : Informations de base ---
            # / Step 2: basic info
            page.locator('input[name="name"]').fill(nom_du_produit)
            page.locator('input[name="short_description"]').first.fill(
                'Tarif solidaire soumis à validation manuelle'
            )

            # --- Étape 3 : Deux tarifs, le solidaire à validation manuelle ---
            # / Step 3: two prices, the solidarity one with manual validation
            _add_inline_price(page, {
                'name': 'Solidaire', 'prix': 2, 'subscription_type': 'Y',
                'manual_validation': True,
            })
            _add_inline_price(page, {'name': 'Plein tarif', 'prix': 30, 'subscription_type': 'Y'})

            # --- Étape 4 : Enregistrer ---
            # / Step 4: save
            page.locator('[name="_save"]').first.click()
            page.wait_for_load_state('networkidle')

            # --- Étape 5 : La base porte exactement ce qu'on a saisi ---
            # Validation manuelle sur « Solidaire » seulement.
            # / Step 5: manual validation on "Solidaire" only.
            sortie = django_shell(
                "from BaseBillet.models import Product\n"
                f"produits = Product.objects.filter(name='{nom_du_produit}')\n"
                "print('NOMBRE=' + str(produits.count()))\n"
                "p = produits.first()\n"
                "print('CATEGORIE=' + str(p.categorie_article if p else None))\n"
                "tarifs = sorted((t.name, int(t.prix), t.subscription_type, t.manual_validation) "
                "for t in p.prices.all()) if p else []\n"
                "print('TARIFS=' + repr(tarifs))"
            )
            assert "NOMBRE=1" in sortie, f"Produit non enregistre (ou en double) : {sortie[-300:]}"
            assert "CATEGORIE=A" in sortie, f"Le produit n'est pas une adhesion : {sortie[-300:]}"
            assert (
                "TARIFS=[('Plein tarif', 30, 'Y', False), ('Solidaire', 2, 'Y', True)]" in sortie
            ), f"Les tarifs enregistres ne sont pas ceux saisis (validation comprise) : {sortie[-300:]}"

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
