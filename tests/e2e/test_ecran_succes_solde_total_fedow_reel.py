"""
tests/e2e/test_ecran_succes_solde_total_fedow_reel.py
L'écran après vente de la caisse, contre le VRAI Fedow et le VRAI Stripe.
/ The POS after-sale screen, against the REAL Fedow and the REAL Stripe.

LOCALISATION : tests/e2e/test_ecran_succes_solde_total_fedow_reel.py

POURQUOI CE FICHIER EXISTE / WHY THIS FILE EXISTS
--------------------------------------------------
Une carte peut porter de la monnaie locale (base Lespass) et du FED (ancien Fedow).
L'écran après vente doit afficher ce qui a été payé, monnaie par monnaie, et le solde
total de la carte. tests/pytest/test_ecran_succes_solde_total.py le vérifie avec un
Fedow simulé. Ce fichier vérifie que le vrai Fedow rend bien les mêmes chiffres : le
montant lu à l'écran est comparé au solde relu sur le serveur Fedow.
/ Pytest checks it with a fake Fedow. Here the screen is compared to the real server.

LES QUATRE CAS (café à 1,50 €, recharge FED réelle de 3,00 €)
1. Le local suffit : 5,00 € local + 3,00 € FED, un café → total 6,50 €, FED intact.
2. Local partiel, FED suffisant : 1,00 € + 3,00 €, un café → total 2,50 €.
3. Local et FED insuffisants : 1,00 € + 3,00 €, trois cafés (4,50 €) → 0,50 € en
   espèces, total 0,00 €.
4. Local insuffisant, pas de FED : 1,00 €, un café → 0,50 € en espèces, total 0,00 €.

D'OÙ VIENT L'ARGENT / WHERE THE MONEY COMES FROM
- le FED vient d'un vrai paiement Stripe : l'API de recharge (`/api/v2/wallet-refills/`)
  refuse le FED et la monnaie locale ;
- la monnaie locale est créditée directement dans `fedow_core`, comme
  test_carte_perdue_recharge_fed.py.
/ FED comes from a real Stripe payment: the refill API refuses FED and local currency.

CE QUE CES TESTS LAISSENT DERRIÈRE EUX / WHAT THESE TESTS LEAVE BEHIND
Rien n'est annulé : une carte et un adhérent neufs par test, un paiement Stripe de test
de 3 € (cas 1 à 3) et une vente encaissée.
/ Nothing is rolled back: a new card and member per test, a 3 € Stripe test payment.

PRÉREQUIS : voir tests/e2e/test_carte_liee_par_qrcode_fed_en_caisse.py (serveur de dev,
ancien Fedow, données POS, `stripe listen`).

LANCEMENT / RUN :
    make e2e ARGS="tests/e2e/test_ecran_succes_solde_total_fedow_reel.py -v -s"
"""

import re
import uuid as uuid_module

import pytest
from playwright.sync_api import expect

from tests.e2e.test_carte_liee_par_qrcode_fed_en_caisse import (
    NOM_DU_COMPTOIR,
    _creer_une_carte_neuve_chez_l_ancien_fedow_seulement,
    _fed_de_l_adherent_sans_cache,
    _lier_la_carte_par_son_qrcode,
    _lire_json_marque,
    _recharger_du_fed_en_ligne,
    _scanner_la_carte,
    _verifier_que_le_fed_est_credite,
    ancien_fedow_joignable,  # noqa: F401
    comptoir_du_cafe,  # noqa: F401
)
from tests.e2e.test_parcours_fedow_reel import carte_primaire_declaree_a_l_ancien_fedow  # noqa: F401

pytestmark = [
    pytest.mark.caisse,
    pytest.mark.monnaie,
    pytest.mark.usefixtures(
        "carte_primaire_declaree_a_l_ancien_fedow", "ancien_fedow_joignable"
    ),
]


def _crediter_la_monnaie_locale(django_shell, email, montant_centimes):
    """
    Crédite l'adhérent dans la monnaie locale que la cascade de la caisse lit : la
    première accessible au lieu.
    / Credits the member in the local currency the POS cascade reads.
    """
    sortie = django_shell(
        "import json\n"
        "from django.db import connection, transaction\n"
        "from AuthBillet.models import TibilletUser\n"
        "from fedow_core.models import Asset\n"
        "from fedow_core.services import AssetService, WalletService\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "asset = AssetService.obtenir_assets_accessibles(connection.tenant)"
        ".filter(category=Asset.TLF).first()\n"
        "with transaction.atomic():\n"
        f"    WalletService.crediter(user.wallet, asset, {montant_centimes})\n"
        "print('CREDIT_JSON=' + json.dumps({\n"
        "    'solde': WalletService.obtenir_solde(wallet=user.wallet, asset=asset),\n"
        "}))"
    )
    credit = _lire_json_marque(sortie, "CREDIT_JSON=")
    assert credit["solde"] == montant_centimes, f"Crédit local inattendu : {credit}"


def _fabriquer_une_carte(
    page,
    django_shell,
    local_centimes,
    fill_stripe_card=None,
    soumettre_paiement_stripe=None,
):
    """
    Une carte neuve, liée par son QR code, avec sa monnaie locale et, si les outils
    Stripe sont fournis, 3,00 € de FED rechargés pour de vrai.
    / A new card, linked by QR code, with local currency and optionally real FED.

    :return: dict {'tag', 'email'}
    """
    carte = _creer_une_carte_neuve_chez_l_ancien_fedow_seulement(django_shell)
    email = f"e2e-solde-{uuid_module.uuid4().hex[:8]}@tibillet.test"
    _lier_la_carte_par_son_qrcode(page, carte["qrcode_uuid"], email)

    if fill_stripe_card is not None:
        recharge = _recharger_du_fed_en_ligne(
            page, django_shell, fill_stripe_card, soumettre_paiement_stripe, email
        )
        _verifier_que_le_fed_est_credite(recharge)

    _crediter_la_monnaie_locale(django_shell, email, local_centimes)
    return {"tag": carte["tag"], "email": email}


def _vendre_des_cafes(page, pos_page, comptoir, tag_de_la_carte, quantite):
    """
    Le caissier met des cafés au panier, choisit le cashless et scanne la carte.
    / The cashier adds coffees, picks cashless and scans the card.
    """
    pos_page(page, NOM_DU_COMPTOIR)
    tuile_du_cafe = page.locator(f'[data-testid="article-{comptoir["article_uuid"]}"]')
    expect(tuile_du_cafe).to_be_visible()
    for _numero_du_clic in range(quantite):
        tuile_du_cafe.click()

    bouton_valider = page.locator('[data-testid="addition-valider"]')
    expect(bouton_valider).to_be_enabled()
    bouton_valider.click()
    page.locator('[data-testid="paiement-btn-cashless"]').click()
    _scanner_la_carte(page, tag_de_la_carte)


def _regler_le_reste_en_especes(page, paye_par_la_carte, reste_attendu):
    """
    L'écran du complément annonce le payé par la carte et le reste : le caissier
    encaisse le reste en espèces, compte juste.
    / The complement screen shows the card's part and the remainder, taken in cash.
    """
    ecran_du_complement = page.locator('[data-testid="complement-paiement"]')
    expect(ecran_du_complement).to_be_visible(timeout=20_000)
    expect(
        page.locator('[data-testid="complement-carte1-disponible"]')
    ).to_contain_text(paye_par_la_carte)
    expect(
        page.locator('[data-testid="complement-reste-a-payer"]')
    ).to_contain_text(reste_attendu)
    ecran_du_complement.locator('button[hx-get*="method=espece"]').click()
    page.locator('[data-testid="paiement-btn-valider"]').click()


def _texte_normalise(localisateur):
    """Le texte de l'élément, espaces insécables remplacés.
    / The element's text, non-breaking spaces replaced."""
    texte = localisateur.inner_text().replace("\xa0", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", texte).strip()


def _solde_total_a_l_ecran(page):
    """Attend l'écran de succès et lit le solde total affiché.
    / Waits for the success screen and reads the shown total."""
    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(
        timeout=20_000
    )
    return _texte_normalise(page.locator('[data-testid="paiement-carte1-solde-total"]'))


@pytest.mark.stripe_listen
def test_local_suffisant_le_total_compte_le_fed_reel(
    page,
    pos_page,
    django_shell,
    fill_stripe_card,
    soumettre_paiement_stripe,
    comptoir_du_cafe,  # noqa: F811
):
    """
    5,00 € local + 3,00 € de vrai FED, un café à 1,50 € : le local paie tout. L'écran
    affiche 1,50 € payé et 6,50 € au total. Le FED reste à 3,00 € chez Fedow.
    / Local pays all. Screen: 1.50 € paid, 6.50 € total. Real FED stays at 3.00 €.
    """
    carte = _fabriquer_une_carte(
        page, django_shell, 500, fill_stripe_card, soumettre_paiement_stripe
    )

    _vendre_des_cafes(page, pos_page, comptoir_du_cafe, carte["tag"], quantite=1)

    assert _solde_total_a_l_ecran(page) == "6,50 €"
    paye = _texte_normalise(page.locator('[data-testid="paiement-carte1-debite"]'))
    assert "1,50 €" in paye
    # Le reste en monnaie locale n'est pas affiché : le détail est au check carte.
    # / The local balance is hidden: the detail is on the card check.
    assert "3,50 €" not in page.locator('[data-testid="paiement-succes"]').inner_text()
    assert _fed_de_l_adherent_sans_cache(django_shell, carte["email"]) == 300


@pytest.mark.stripe_listen
def test_local_partiel_et_fed_suffisant_contre_le_fed_reel(
    page,
    pos_page,
    django_shell,
    fill_stripe_card,
    soumettre_paiement_stripe,
    comptoir_du_cafe,  # noqa: F811
):
    """
    1,00 € local + 3,00 € de vrai FED, un café à 1,50 € : 1,00 € en local, 0,50 € en
    FED. L'écran affiche la ligne TiBillet et 2,50 € au total, comme le serveur Fedow.
    / 1.00 € local, 0.50 € FED. TiBillet row, total 2.50 €, as on the Fedow server.
    """
    carte = _fabriquer_une_carte(
        page, django_shell, 100, fill_stripe_card, soumettre_paiement_stripe
    )

    _vendre_des_cafes(page, pos_page, comptoir_du_cafe, carte["tag"], quantite=1)

    assert _solde_total_a_l_ecran(page) == "2,50 €"
    ligne_du_fed = _texte_normalise(
        page.locator('[data-testid="solde-carte1-asset-2"]')
    )
    assert "TiBillet" in ligne_du_fed and "− 0,50 €" in ligne_du_fed, ligne_du_fed
    assert _fed_de_l_adherent_sans_cache(django_shell, carte["email"]) == 250


@pytest.mark.stripe_listen
def test_local_et_fed_insuffisants_le_reste_en_especes_contre_le_fed_reel(
    page,
    pos_page,
    django_shell,
    fill_stripe_card,
    soumettre_paiement_stripe,
    comptoir_du_cafe,  # noqa: F811
):
    """
    1,00 € local + 3,00 € de vrai FED, trois cafés à 4,50 € : le caissier encaisse
    0,50 € en espèces. La carte est vidée : 0,00 € à l'écran et 0 chez Fedow.
    / Three coffees: 0.50 € in cash. Card emptied: 0.00 € on screen and on Fedow.
    """
    carte = _fabriquer_une_carte(
        page, django_shell, 100, fill_stripe_card, soumettre_paiement_stripe
    )

    _vendre_des_cafes(page, pos_page, comptoir_du_cafe, carte["tag"], quantite=3)
    _regler_le_reste_en_especes(page, "4,00", "0,50")

    assert _solde_total_a_l_ecran(page) == "0,00 €"
    assert _fed_de_l_adherent_sans_cache(django_shell, carte["email"]) == 0


def test_local_insuffisant_sans_fed_le_reste_en_especes_contre_le_fed_reel(
    page,
    pos_page,
    django_shell,
    comptoir_du_cafe,  # noqa: F811
):
    """
    1,00 € local, pas de FED (la carte est connue du vrai Fedow), un café à 1,50 € : le
    caissier encaisse 0,50 € en espèces. Pas de ligne TiBillet, 0,00 € au total.
    / 1.00 € local, no FED, 0.50 € in cash. No TiBillet row, 0.00 € total.
    """
    carte = _fabriquer_une_carte(page, django_shell, 100)

    _vendre_des_cafes(page, pos_page, comptoir_du_cafe, carte["tag"], quantite=1)
    _regler_le_reste_en_especes(page, "1,00", "0,50")

    assert _solde_total_a_l_ecran(page) == "0,00 €"
    ecran_de_succes = page.locator('[data-testid="paiement-succes"]')
    assert "TiBillet" not in ecran_de_succes.inner_text()
