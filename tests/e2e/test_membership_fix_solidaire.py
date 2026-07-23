"""
Tests E2E : activation de la validation manuelle pour le tarif Solidaire.
/ E2E tests: enable manual_validation for the Solidaire price.

Conversion de tests/playwright/tests/07-fix-solidaire-manual-validation.spec.ts

Ce test vérifie qu'un admin peut activer la case "Validation manuelle" (manual_validation)
sur le tarif "Solidaire" du produit "Adhésion à validation sélective (Le Tiers-Lustre)".

/ This test verifies that an admin can enable the "manual_validation" checkbox
on the "Solidaire" price of the "Adhésion à validation sélective (Le Tiers-Lustre)" product.

ATTENTION : ce test modifie des données en DB partagée sans rollback.
Il peut activer ou laisser activée la validation manuelle sur le tarif Solidaire.
/ WARNING: this test modifies shared DB data without rollback.
It may enable or leave enabled the manual validation on the Solidaire price.
"""

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e

# Fragment du nom du produit contenant le tarif Solidaire.
# / Fragment of the product name containing the Solidaire price.
PRODUCT_NAME_FRAGMENT = "validation sélective"


class TestMembershipFixSolidaire:
    """Activation de la validation manuelle pour le tarif Solidaire.
    / Enable manual_validation for the Solidaire price.
    """

    def test_enable_manual_validation_for_solidaire(
        self, page, login_as_admin, django_shell
    ):
        """Active la case manual_validation sur le tarif Solidaire du produit
        "Adhésion à validation sélective (Le Tiers-Lustre)".
        / Enables manual_validation checkbox on the Solidaire price of
        the "Adhésion à validation sélective (Le Tiers-Lustre)" product.
        """
        # --- Étape 1 : Récupérer les UUIDs du produit et du tarif via le shell Django ---
        # On utilise django_shell pour éviter la dépendance à l'affichage dans la
        # changelist admin (qui peut lister des produits dans un proxy différent).
        # / Step 1: Get product and price UUIDs via Django shell
        # We use django_shell to avoid dependency on the admin changelist display
        # (which may list products under a different proxy).
        try:
            price_uuid = django_shell(
                "from BaseBillet.models import Product, Price;"
                " products = Product.objects.filter(name__icontains='validation selective');"
                " products2 = Product.objects.filter(name__icontains='validation s\\u00e9lective');"
                " all_products = list(products) + [p for p in products2 if p not in list(products)];"
                " price = None;"
                " [price := pr for p in all_products for pr in p.prices.all() if pr.name == 'Solidaire'];"
                " print(str(price.uuid) if price else 'NOT_FOUND')"
            )
        except RuntimeError as exc:
            pytest.fail(
                "django_shell a echoue lors de la recherche du tarif : un shell "
                f"Django injoignable rend ce test ROUGE, pas ignore.\n{exc}"
            )

        if price_uuid == "NOT_FOUND" or not price_uuid:
            pytest.fail(
                "Tarif 'Solidaire' du produit 'Adhésion à validation sélective' "
                "introuvable en base : ce test n'a rien a activer. Reseeder : "
                "docker exec lespass_django poetry run python manage.py demo_data_v2"
            )

        # --- Étape 2 : Connexion admin ---
        # / Step 2: Admin login
        login_as_admin(page)

        # --- Étape 3 : Naviguer directement vers la page d'édition du tarif ---
        # L'URL de modification d'un Price suit le pattern :
        # /admin/BaseBillet/price/<uuid>/change/
        # / Step 3: Navigate directly to the price edit page
        # The Price edit URL follows the pattern:
        # /admin/BaseBillet/price/<uuid>/change/
        price_edit_url = f"/admin/BaseBillet/price/{price_uuid}/change/"
        page.goto(price_edit_url)
        page.wait_for_load_state("networkidle")

        # Vérifier qu'on est bien sur la page d'édition du tarif Solidaire.
        # / Verify we're on the Solidaire price edit page.
        page_content = page.content()
        assert "Solidaire" in page_content or price_uuid in page.url, (
            f"La page d'édition du tarif n'a pas chargé correctement. URL: {page.url}"
        )

        # --- Étape 4 : Vérifier la présence du champ manual_validation ---
        # Un champ absent du formulaire est une REGRESSION de l'admin : le
        # gestionnaire ne peut plus activer la validation manuelle. C'est
        # exactement ce que ce test surveille — donc ROUGE.
        # / Step 4: A missing field is an admin REGRESSION: the manager can no
        # longer enable manual validation. That is what this test watches — RED.
        checkbox = page.locator('input[name="manual_validation"]')

        if checkbox.count() == 0:
            pytest.fail(
                "Champ 'manual_validation' absent du formulaire de tarif dans "
                f"l'admin ({price_edit_url}) : la validation manuelle n'est plus "
                "activable par un gestionnaire."
            )

        # --- Étape 5 : Activer la case si elle n'est pas encore cochée ---
        # / Step 5: Enable the checkbox if not already checked
        already_checked = checkbox.is_checked()

        if not already_checked:
            checkbox.check()

        # --- Étape 6 : Sauvegarder le formulaire ---
        # Django admin Unfold : le bouton Save peut être un <button> ou <input>.
        # On cherche le bouton avec name="_save" ou type="submit" et texte "Save".
        # / Step 6: Save the form
        # Django admin Unfold: Save button can be a <button> or <input>.
        # We look for name="_save" or type="submit" with text "Save".
        save_button = (
            page.locator('[name="_save"]').first
            if page.locator('[name="_save"]').count() > 0
            else page.locator('button[type="submit"], input[type="submit"]').first
        )
        save_button.click()
        page.wait_for_load_state("networkidle")

        # --- Étape 7 : Vérifier que la sauvegarde a réussi ---
        # Django admin affiche un message "was saved successfully" ou redirige
        # vers la changelist. On vérifie l'absence de .errorlist.
        # / Step 7: Verify that save succeeded
        # Django admin shows "was saved successfully" or redirects to changelist.
        # We verify the absence of .errorlist.
        current_url = page.url
        page_content_after = page.content()

        assert "errorlist" not in page_content_after or "was saved successfully" in page_content_after, (
            f"Erreur probable lors de la sauvegarde du tarif Solidaire. URL: {current_url}"
        )

        # --- Étape 8 : Re-naviguer vers la page d'édition pour confirmer l'état ---
        # Après sauvegarde Django admin redirige vers la changelist — on revient
        # sur la page du tarif pour vérifier que la case est bien cochée.
        # / Step 8: Re-navigate to the edit page to confirm the state
        # After save Django admin redirects to changelist — we return to the
        # price page to verify the checkbox is checked.
        page.goto(price_edit_url)
        page.wait_for_load_state("networkidle")

        checkbox_after = page.locator('input[name="manual_validation"]')
        if checkbox_after.count() > 0:
            assert checkbox_after.is_checked(), (
                "La case manual_validation devrait être cochée après sauvegarde"
            )
