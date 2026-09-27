"""
Tests E2E : activation de la validation manuelle sur un tarif, depuis sa page d'admin.
/ E2E tests: enable manual_validation on a price, from its admin page.

Conversion de tests/playwright/tests/07-fix-solidaire-manual-validation.spec.ts

Ce test vérifie qu'un admin peut activer la case « Validation manuelle requise »
(manual_validation) sur la page d'édition d'un tarif, et que la base l'enregistre.
/ This test verifies that an admin can enable manual_validation on a price's edit
page, and that the database stores it.

Le test crée SON produit et SON tarif « Solidaire », NON coché au départ : sinon il
« vérifierait » un état qu'il n'a pas produit. Avant, il prenait un tarif « Solidaire »
au hasard dans le produit de référence (5 en base au 2026-09-27, dont 4 déjà cochés). Le
produit est supprimé en fin de test (base de dev partagée, sans rollback).
/ The test creates ITS product and ITS unchecked "Solidaire" price, then deletes them.
"""

import uuid

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e



class TestMembershipFixSolidaire:
    """Activation de la validation manuelle pour le tarif Solidaire.
    / Enable manual_validation for the Solidaire price.
    """

    def test_enable_manual_validation_for_solidaire(
        self, page, login_as_admin, django_shell
    ):
        """Coche la validation manuelle d'un tarif « Solidaire » non coché, et vérifie la base.
        / Checks manual validation on an unchecked "Solidaire" price, and checks the database.
        """
        nom_du_produit = f"Adhésion validation Solidaire E2E {uuid.uuid4().hex[:6]}"
        try:
            # --- Étape 1 : Un produit d'adhésion et un tarif « Solidaire » NON coché ---
            # / Step 1: a membership product and an UNCHECKED "Solidaire" price
            sortie = django_shell(
                "from BaseBillet.models import Price, Product\n"
                f"produit = Product.objects.create(name='{nom_du_produit}', "
                "categorie_article=Product.ADHESION, publish=True)\n"
                "tarif = Price.objects.create(product=produit, name='Solidaire', prix=2, "
                "subscription_type=Price.YEAR, manual_validation=False, publish=True)\n"
                "print('TARIF_UUID=' + str(tarif.uuid))"
            )
            assert "TARIF_UUID=" in sortie, f"Tarif non cree : {sortie[-300:]}"
            uuid_du_tarif = sortie.split("TARIF_UUID=")[1].split()[0]

            # --- Étape 2 : La page d'édition du tarif ---
            # / Step 2: the price edit page
            login_as_admin(page)
            page.goto(f"/admin/BaseBillet/price/{uuid_du_tarif}/change/")
            page.wait_for_load_state("networkidle")

            # --- Étape 3 : La case existe, décochée, et on la coche ---
            # Absente = REGRESSION de l'admin : un gestionnaire ne pourrait plus
            # activer la validation manuelle.
            # / Step 3: the checkbox exists, unchecked, and gets checked.
            case = page.locator('input[name="manual_validation"]')
            expect(case).to_have_count(1)
            expect(case).not_to_be_checked()
            case.check()

            # --- Étape 4 : Enregistrer ---
            # / Step 4: save
            page.locator('[name="_save"]').first.click()
            page.wait_for_load_state("networkidle")

            # --- Étape 5 : La base a enregistré la validation manuelle ---
            # / Step 5: the database stored manual validation
            etat = django_shell(
                "from BaseBillet.models import Price\n"
                f"print('VALIDATION=' + str(Price.objects.get(uuid='{uuid_du_tarif}').manual_validation))"
            )
            assert "VALIDATION=True" in etat, (
                f"La validation manuelle n'a pas ete enregistree : {etat[-300:]}"
            )
        finally:
            # Nettoyage : le tarif d'abord (Price.product est PROTECT), puis le produit.
            # / Cleanup: the price first (Price.product is PROTECT), then the product.
            django_shell(
                "from BaseBillet.models import Price, Product\n"
                f"Price.objects.filter(product__name='{nom_du_produit}').delete()\n"
                f"Product.objects.filter(name='{nom_du_produit}').delete()"
            )
