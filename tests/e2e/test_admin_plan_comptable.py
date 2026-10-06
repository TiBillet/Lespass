"""
Test E2E : les écrans du plan comptable et « Plan complet ? ».
/ E2E test: the chart of accounts screens and "Complete plan?".

LOCALISATION : tests/e2e/test_admin_plan_comptable.py

UN SEUL PARCOURS (chantier 05, fiche E-2) :
1. l'entrée « Plan comptable » du menu « Ventes & comptabilité » ouvre l'onglet
   « Gérer » (la balance) ; l'onglet « Configurer » mène aux trois écrans de réglage
   (comptes, moyens de paiement, monnaies), reliés par leur second niveau, chacun
   avec « Plan complet ? » en tête ;
2. le moyen « Stripe » (SN), utilisé par des ventes réglées du lieu, perd son compte :
   le bouton « Vérifier le plan » le signale ;
3. on lui pose son compte dans son formulaire : le bouton ne le signale plus.
/ One journey: the menu leads to the three screens; a used method without account is
reported by "Complete plan?"; setting its account makes the report disappear.

Ce que pytest ne peut pas vérifier : les liens réels de la barre latérale, le
formulaire avec son widget d'autocomplétion, l'enchaînement dans un vrai navigateur.
/ What pytest cannot check: real sidebar links, the autocomplete widget, the journey.

DONNÉES : le lieu `lespass` de la base de dev. La fixture vide le compte de la
correspondance SN (la ligne reste) et le remet à la fin, même si le test échoue.
Aucune vente n'est créée (une vente réglée est scellée et ne s'efface pas).
/ Data: the dev `lespass` venue. The fixture empties the SN mapping's account and puts
it back at the end, even on failure. No sale is created.

Code testé : Administration/admin/dashboard.py (menu), Administration/admin/laboutik.py
(écrans), Administration/templates/admin/comptable/*.html, laboutik/plan_comptable.py
(`ce_qui_manque_pour_exporter`).

LANCEMENT / RUN :
    make e2e ARGS="tests/e2e/test_admin_plan_comptable.py"
"""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.e2e

LIEN_DE_LA_BALANCE = "/admin/laboutik/comptecomptable/balance/"
LIEN_DU_PLAN_COMPTABLE = "/admin/laboutik/comptecomptable/"
LIEN_DES_COMPTES_DES_MOYENS = "/admin/laboutik/mappingmoyendepaiement/"
LIEN_DES_COMPTES_DES_MONNAIES = "/admin/laboutik/mappingmonnaie/"

# Le moyen dont on retire le compte : « Stripe » (SN), toujours utilisé par les
# ventes en ligne réglées du lieu de dev.
# / The method whose account is removed: Stripe (SN), always used on the dev venue.
MOYEN_DU_PARCOURS = "SN"


@pytest.fixture
def correspondance_sn_sans_compte(django_shell):
    """
    Vide le compte de la correspondance SN du lieu `lespass`, puis le remet.
    / Empties the SN mapping's account on `lespass`, then puts it back.
    """
    sortie = django_shell(
        "from BaseBillet.models_vente import Reglement; "
        "from laboutik.models import MappingMoyenDePaiement; "
        f"assert Reglement.objects.filter(vente__statut='REGLEE', moyen='{MOYEN_DU_PARCOURS}').exists(), "
        "'aucune vente reglee en SN dans le lieu de dev'; "
        f"c = MappingMoyenDePaiement.objects.get(moyen_de_paiement='{MOYEN_DU_PARCOURS}'); "
        "print(c.pk); print(c.compte_de_tresorerie.numero_de_compte); "
        "c.compte_de_tresorerie = None; c.save()"
    ).splitlines()
    pk_de_la_correspondance = sortie[-2]
    numero_du_compte_d_origine = sortie[-1]

    yield SimpleNamespace(
        pk=pk_de_la_correspondance, numero_du_compte=numero_du_compte_d_origine
    )

    # Le compte d'origine revient, quoi qu'ait fait le test.
    # / The original account comes back, whatever the test did.
    django_shell(
        "from laboutik.models import CompteComptable, MappingMoyenDePaiement; "
        f"c = MappingMoyenDePaiement.objects.get(pk='{pk_de_la_correspondance}'); "
        "c.compte_de_tresorerie = CompteComptable.objects.get("
        f"numero_de_compte='{numero_du_compte_d_origine}'); "
        "c.save()"
    )


def _verifier_le_plan(page):
    """
    Clique le bouton « Vérifier le plan » de l'écran, puis attend le verdict de
    « Plan complet ? » (message vert ou au moins un manque) : le verdict n'est plus
    calculé à l'ouverture de l'écran.
    / Clicks "Check the plan", then waits for the verdict (green message or a
    missing item): it is no longer computed when the screen opens.
    """
    page.locator('[data-testid="plan-complet-verifier"]').click()
    page.locator(
        '[data-testid="plan-complet-ok"], [data-testid="plan-complet-manque"]'
    ).first.wait_for()


def _manques_du_moyen(page):
    """
    Les manques de « Plan complet ? » qui nomment le moyen du parcours.
    / The "Complete plan?" items naming the journey's method.
    """
    return page.locator('[data-testid="plan-complet-manque"]').filter(
        has_text=f"({MOYEN_DU_PARCOURS})"
    )


def test_menu_mene_aux_ecrans_du_plan_et_plan_complet_suit_le_compte_pose(
    page, login_as_admin, correspondance_sn_sans_compte
):
    """
    Le menu ouvre la balance, « Configurer » mène aux trois écrans du plan ;
    « Plan complet ? » signale le moyen SN sans compte, puis ne le signale plus
    quand son compte est posé.
    / The menu opens the trial balance, "Configure" leads to the three plan
    screens; "Complete plan?" reports SN without account, then no longer.
    """
    login_as_admin(page)
    page.goto("/admin/")

    # --- 1. Le menu ouvre la balance, « Configurer » mène aux trois écrans ---
    # / The menu opens the trial balance, "Configure" leads to the three screens.
    lien_du_menu = page.locator(f'a[href="{LIEN_DE_LA_BALANCE}"]').first
    if not lien_du_menu.is_visible():
        # La section repliée s'ouvre au clic sur son titre (le h2 du bloc Alpine
        # qui contient le lien).
        # / The collapsed section opens when its title is clicked.
        titre_de_la_section = lien_du_menu.locator("xpath=ancestor::div[@x-data][1]/h2")
        titre_de_la_section.click()
    lien_du_menu.click()
    page.wait_for_url(f"**{LIEN_DE_LA_BALANCE}")
    assert page.locator('[data-testid="aide-balance"]').is_visible()

    page.locator("#tabs-items a", has_text="Configurer").click()
    page.wait_for_url(f"**{LIEN_DU_PLAN_COMPTABLE}")
    assert page.locator('[data-testid="plan-complet"]').is_visible()

    for testid_du_sous_onglet, lien_de_l_ecran in [
        ("sous-onglet-moyens", LIEN_DES_COMPTES_DES_MOYENS),
        ("sous-onglet-monnaies", LIEN_DES_COMPTES_DES_MONNAIES),
        ("sous-onglet-comptes", LIEN_DU_PLAN_COMPTABLE),
    ]:
        page.locator(f'[data-testid="{testid_du_sous_onglet}"]').click()
        page.wait_for_url(f"**{lien_de_l_ecran}")
        assert page.locator('[data-testid="plan-complet"]').is_visible()

    # --- 2. Le moyen sans compte est signalé / The method without account is reported ---
    page.goto(LIEN_DES_COMPTES_DES_MOYENS)
    _verifier_le_plan(page)
    assert _manques_du_moyen(page).count() == 1

    # --- 3. On pose son compte : le manque disparaît / Set the account: report gone ---
    page.goto(
        f"{LIEN_DES_COMPTES_DES_MOYENS}{correspondance_sn_sans_compte.pk}/change/"
    )

    # Le compte se choisit par l'autocomplétion de l'admin (select2) : on ouvre la
    # liste, on tape le numéro, on prend la proposition.
    # / The account is picked through the admin autocomplete (select2).
    page.locator("#select2-id_compte_de_tresorerie-container").click()
    page.locator(".select2-search__field").fill(
        correspondance_sn_sans_compte.numero_du_compte
    )
    page.locator(".select2-results__option").filter(
        has_text=correspondance_sn_sans_compte.numero_du_compte
    ).first.click()
    page.locator('button[name="_save"]').click()
    page.wait_for_url(f"**{LIEN_DES_COMPTES_DES_MOYENS}")

    assert page.locator('[data-testid="plan-complet"]').is_visible()
    _verifier_le_plan(page)
    assert _manques_du_moyen(page).count() == 0
