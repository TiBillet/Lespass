"""
tests/e2e/test_pos_cashless_simulateur_nfc.py
Point de vente CASHLESS : le lecteur NFC demarre apres VALIDER.
/ CASHLESS POS: the NFC reader starts after VALIDATE.

LOCALISATION : tests/e2e/test_pos_cashless_simulateur_nfc.py

BUG CORRIGE / FIXED BUG
-----------------------
Sur un PV cashless, VALIDER affiche directement « Approchez la carte »
(hx_display_type_payment.html, branche comportement C). La reponse contient
aussi un champ hors bande (hx-swap-oob : la cle d'idempotence).
htmx declenchait 'htmx:afterSwap' d'abord sur ce champ : l'ecouteur de
cotton/V2/read_nfc.html se retirait sans avoir trouve le lecteur.
initNfc() n'etait jamais appele : pas de bouton simulateur, pas de lecture.
/ The out-of-band field fired 'htmx:afterSwap' first and the reader's
listener removed itself: initNfc() never ran (no simulator, no read).

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/e2e/test_pos_cashless_simulateur_nfc.py -v -s
"""

from playwright.sync_api import expect


def test_recharge_sur_pv_cashless_affiche_le_simulateur_nfc(page, pos_page):
    # Ouvre le PV « Cashless » (donnees de create_test_pos_data)
    # / Open the "Cashless" POS (create_test_pos_data seed)
    pos_page(page, "Cashless")

    # Premiere tuile = une recharge (le PV cashless charge les recharges).
    # La popup des tarifs s'ouvre : on prend le tarif a 5 €.
    # / First tile = a top-up. The price popup opens: pick the 5 € price.
    page.locator('[data-testid^="article-"]').first.click()
    page.locator('[data-testid^="tarif-btn-"]', has_text="5,00").first.click()

    bouton_valider = page.locator('[data-testid="addition-valider"]')
    expect(bouton_valider).to_be_enabled()
    bouton_valider.click()

    # L'attente de carte s'affiche, et le lecteur a demarre :
    # en mode demo, nfc.js ajoute le bouton du simulateur.
    # / Card wait shows and the reader started: demo mode adds the simulator toggle.
    expect(page.locator('[data-testid="nfc-attente"]')).to_be_visible()
    expect(page.locator(".nfc-container .nfc-toggle-simu")).to_have_count(1)
