"""
Tests E2E : champs conditionnels d'un tarif ajoute depuis la page de CREATION d'un produit.
/ E2E tests: conditional fields of a price added on the product CREATION page.

LOCALISATION : tests/e2e/test_admin_tarif_champs_conditionnels_creation.py

Sur la page de creation, il n'y a aucun tarif au chargement (extra = 0).
Le tarif apparait quand on clique sur « Ajouter un autre tarif ».
Le script Administration/static/admin/js/inline_conditional_fields.js doit alors
appliquer les regles a cette nouvelle ligne :
- « iteration » est cache tant que « paiement recurrent » n'est pas coche
- le jeton et le montant de recharge sont caches tant que la recharge n'est pas activee

/ On the creation page there is no price row at load (extra = 0). The row is added
by the "Add another" button, and the JS must apply the rules to it.

Le test n'enregistre rien : aucun nettoyage de la base n'est necessaire.
/ The test saves nothing: no database cleanup needed.
"""

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _ajouter_un_tarif_et_renvoyer_son_index(page):
    """Clique sur « Ajouter un autre » dans #prices-group et renvoie l'index de la ligne.
    / Clicks "Add another" in #prices-group and returns the new row index.
    """
    section_des_tarifs = page.locator("#prices-group")

    # On compte les lignes deja presentes, sans le gabarit vide "__prefix__"
    # / Count existing rows, without the "__prefix__" empty template
    nombre_de_tarifs_avant_le_clic = section_des_tarifs.locator(
        'input[name^="prices-"][name$="-name"]:not([name*="__prefix__"])'
    ).count()

    section_des_tarifs.locator("a.add-row").first.click()

    index_du_nouveau_tarif = nombre_de_tarifs_avant_le_clic
    section_des_tarifs.locator(
        f'input[name="prices-{index_du_nouveau_tarif}-name"]'
    ).wait_for(state="visible", timeout=5_000)
    return index_du_nouveau_tarif


class TestChampsConditionnelsTarifPageDeCreation:
    """Regles conditionnelles appliquees aux tarifs ajoutes en creation de produit.
    / Conditional rules applied to prices added while creating a product.
    """

    def test_iteration_cachee_puis_affichee_selon_paiement_recurrent(
        self, page, login_as_admin
    ):
        """« iteration » suit la case « paiement recurrent » sur un tarif ajoute.
        / "iteration" follows the "recurring payment" checkbox on an added price.
        """
        login_as_admin(page)
        page.goto("/admin/BaseBillet/membershipproduct/add/")
        page.wait_for_load_state("networkidle")

        index_du_tarif = _ajouter_un_tarif_et_renvoyer_son_index(page)
        champ_iteration = page.locator(f"#id_prices-{index_du_tarif}-iteration")
        case_paiement_recurrent = page.locator(
            f"#id_prices-{index_du_tarif}-recurring_payment"
        )

        # Par defaut, le paiement recurrent est decoche : iteration est cache
        # / By default recurring payment is unchecked: iteration is hidden
        expect(champ_iteration).to_be_hidden()

        case_paiement_recurrent.check()
        expect(champ_iteration).to_be_visible()

        case_paiement_recurrent.uncheck()
        expect(champ_iteration).to_be_hidden()

    def test_recharge_fedow_cachee_par_defaut_sur_deux_tarifs_ajoutes(
        self, page, login_as_admin
    ):
        """Le montant de recharge est cache sur chaque tarif ajoute, pas seulement le premier.
        / The top-up amount is hidden on every added price, not only the first one.
        """
        login_as_admin(page)
        page.goto("/admin/BaseBillet/membershipproduct/add/")
        page.wait_for_load_state("networkidle")

        index_du_premier_tarif = _ajouter_un_tarif_et_renvoyer_son_index(page)
        index_du_second_tarif = _ajouter_un_tarif_et_renvoyer_son_index(page)

        for index_du_tarif in (index_du_premier_tarif, index_du_second_tarif):
            expect(
                page.locator(f"#id_prices-{index_du_tarif}-fedow_reward_amount")
            ).to_be_hidden()

        # Activer la recharge sur le second tarif ne montre QUE son montant
        # / Enabling the top-up on the second price shows ONLY its amount
        page.locator(f"#id_prices-{index_du_second_tarif}-fedow_reward_enabled").check()
        expect(
            page.locator(f"#id_prices-{index_du_second_tarif}-fedow_reward_amount")
        ).to_be_visible()
        expect(
            page.locator(f"#id_prices-{index_du_premier_tarif}-fedow_reward_amount")
        ).to_be_hidden()
