"""
tests/e2e/test_caisse_vente_en_points.py — Vente en points a la caisse, dans le navigateur.
/ Points sale at the register, in the browser.

LOCALISATION : tests/e2e/test_caisse_vente_en_points.py

CE QUI EST TESTE :
La caisse affiche un article vendu en points (monnaie FID) ou en temps (TIM) avec
le nom de sa monnaie, jamais en « € » : tuile, popup des tarifs, panier, ecran des
moyens de paiement, ecran de succes. Un panier en points ne propose que la carte
NFC, et un panier qui melange points et euros est refuse des « VALIDER ».
Le JavaScript (tarif.js, addition.js) ne se teste que dans un vrai navigateur.

DONNEES :
Le test cree ses propres objets (idempotent) : le point de vente « Comptoir points
E2E », un article « Pins E2E » a 300 points, une « Biere E2E » a deux tarifs (5 € et
1 heure), et une carte client credite de points. Il s'appuie sur les monnaies FID et
TIM du lieu et sur la carte primaire seedees par `create_test_pos_data`.
/ The test creates its own objects; it relies on the seeded FID/TIM currencies and
  primary card.

LANCEMENT / RUN :
    make e2e ARGS="tests/e2e/test_caisse_vente_en_points.py"
"""

import json

import pytest
from playwright.sync_api import expect

NOM_DU_POINT_DE_VENTE = "Comptoir points E2E"

# `CarteCashless.tag_id` est limite a 8 caracteres (PIEGES 9.31).
# / CarteCashless.tag_id is limited to 8 characters.
TAG_DE_LA_CARTE_CLIENT = "E2EPTS01"

# La carte primaire du caissier, seedee par `create_test_pos_data`.
# / The cashier's primary card, seeded by create_test_pos_data.
TAG_DE_LA_CARTE_PRIMAIRE = "A49E8E2A"


def _lire_json_marque(sortie, marqueur):
    """Extrait le JSON imprime par le shell Django derriere un marqueur.
    / Extracts the JSON printed by the Django shell behind a marker."""
    for ligne in sortie.splitlines():
        if ligne.startswith(marqueur):
            return json.loads(ligne[len(marqueur) :])
    pytest.fail(
        f"Le shell Django n'a rien imprime derriere '{marqueur}'. "
        f"Sortie : {sortie[-800:]}"
    )


@pytest.fixture(scope="module")
def comptoir_en_points(django_shell, ensure_pos_data):
    """Cree (ou retrouve) le point de vente, les articles et la carte du test, et
    credite la carte de 300 points.
    / Creates (or finds) the test POS, items and card; credits the card 300 points."""
    sortie = django_shell(
        "import json\n"
        "from decimal import Decimal\n"
        "from django.db import connection, transaction\n"
        "from AuthBillet.models import TibilletUser, Wallet\n"
        "from BaseBillet.models import Price, Product\n"
        "from QrcodeCashless.models import CarteCashless\n"
        "from fedow_core.models import Asset\n"
        "from fedow_core.services import WalletService\n"
        "from laboutik.models import CartePrimaire, PointDeVente\n"
        "lieu = connection.tenant\n"
        "points = Asset.objects.filter(tenant_origin=lieu, category=Asset.FID,"
        " active=True, archive=False).first()\n"
        "temps = Asset.objects.filter(tenant_origin=lieu, category=Asset.TIM,"
        " active=True, archive=False).first()\n"
        f"pv, _c = PointDeVente.objects.get_or_create(name='{NOM_DU_POINT_DE_VENTE}',"
        " defaults={'comportement': PointDeVente.DIRECT, 'service_direct': True,"
        " 'accepte_especes': True, 'accepte_carte_bancaire': True})\n"
        "pins, _c = Product.objects.get_or_create(name='Pins E2E',"
        " defaults={'methode_caisse': Product.VENTE})\n"
        "tarif_pins, _c = Price.objects.get_or_create(product=pins, name='Points',"
        " defaults={'prix': Decimal('300.00'), 'non_fiduciaire': True, 'asset': points})\n"
        "points = tarif_pins.asset or points\n"
        "biere, _c = Product.objects.get_or_create(name='Biere E2E',"
        " defaults={'methode_caisse': Product.VENTE})\n"
        "pinte, _c = Price.objects.get_or_create(product=biere, name='Pinte',"
        " defaults={'prix': Decimal('5.00'), 'order': 100})\n"
        "benevole, _c = Price.objects.get_or_create(product=biere, name='Benevole',"
        " defaults={'prix': Decimal('1.00'), 'non_fiduciaire': True, 'asset': temps,"
        " 'order': 100})\n"
        "temps = benevole.asset or temps\n"
        "pv.products.add(pins, biere)\n"
        f"primaire = CartePrimaire.objects.filter(carte__tag_id='{TAG_DE_LA_CARTE_PRIMAIRE}').first()\n"
        "if primaire is not None:\n"
        "    primaire.points_de_vente.add(pv)\n"
        "client, _c = TibilletUser.objects.get_or_create(email='e2e-points@tibillet.localhost',"
        " defaults={'username': 'e2e-points@tibillet.localhost'})\n"
        "if client.wallet is None:\n"
        "    client.wallet = Wallet.objects.create(origin=lieu, name='Wallet E2E points')\n"
        "    client.save()\n"
        f"carte, _c = CarteCashless.objects.get_or_create(tag_id='{TAG_DE_LA_CARTE_CLIENT}',"
        f" defaults={{'number': '{TAG_DE_LA_CARTE_CLIENT}', 'user': client}})\n"
        "if carte.user_id != client.pk:\n"
        "    carte.user = client\n"
        "    carte.save()\n"
        "with transaction.atomic():\n"
        "    WalletService.crediter(client.wallet, points, 30000)\n"
        "print('COMPTOIR_POINTS_JSON=' + json.dumps({\n"
        "    'points': points.name if points else None,\n"
        "    'temps': temps.name if temps else None,\n"
        "    'primaire': primaire is not None,\n"
        "    'pins': str(pins.uuid),\n"
        "    'biere': str(biere.uuid),\n"
        "    'pinte': str(pinte.uuid),\n"
        "    'benevole': str(benevole.uuid),\n"
        "}))"
    )
    donnees = _lire_json_marque(sortie, "COMPTOIR_POINTS_JSON=")
    if not donnees["points"] or not donnees["temps"]:
        pytest.fail(
            "Le lieu n'a pas de monnaie FID et TIM actives. Reseeder : "
            "docker exec lespass_django poetry run python manage.py create_test_pos_data"
        )
    if not donnees["primaire"]:
        pytest.fail(f"Carte primaire {TAG_DE_LA_CARTE_PRIMAIRE} introuvable (seed).")
    return donnees


def _toucher_la_tuile(page, uuid_du_produit):
    page.locator(f'[data-testid="article-{uuid_du_produit}"]').click()


def _valider_le_panier(page):
    bouton_valider = page.locator('[data-testid="addition-valider"]')
    expect(bouton_valider).to_be_enabled()
    bouton_valider.click()


def test_la_tuile_affiche_le_prix_en_points(page, pos_page, comptoir_en_points):
    """E19 : la tuile du Pin's affiche « 300 PF » (initiales de la monnaie, nom
    complet en infobulle), sans « € ».
    / The pin tile shows "300 PF" (currency initials, full name as tooltip), no €."""
    pos_page(page, NOM_DU_POINT_DE_VENTE)
    nom_des_points = comptoir_en_points["points"]
    initiales_des_points = ""
    for mot in nom_des_points.split():
        initiales_des_points += mot[0].upper()

    tuile = page.locator(f'[data-testid="article-{comptoir_en_points["pins"]}"]')

    expect(tuile).to_contain_text(f"300 {initiales_des_points}")
    expect(tuile.locator(f'abbr[title="{nom_des_points}"]')).to_have_count(1)
    expect(tuile).not_to_contain_text("€")


def test_la_popup_des_tarifs_affiche_chaque_unite(page, pos_page, comptoir_en_points):
    """E20 : la biere propose « 5,00 € » et « 1,00 Temps ».
    / The beer offers "5,00 €" and "1,00 Temps"."""
    pos_page(page, NOM_DU_POINT_DE_VENTE)

    _toucher_la_tuile(page, comptoir_en_points["biere"])

    tarif_en_euros = page.locator(f'[data-testid="tarif-btn-{comptoir_en_points["pinte"]}"]')
    tarif_en_temps = page.locator(f'[data-testid="tarif-btn-{comptoir_en_points["benevole"]}"]')
    expect(tarif_en_euros).to_contain_text("5,00 €")
    expect(tarif_en_temps).to_contain_text(f"1,00 {comptoir_en_points['temps']}")


def test_un_panier_en_points_ne_propose_que_la_carte(page, pos_page, comptoir_en_points):
    """E21 : total du panier en points ; seul CASHLESS est propose.
    / Cart total in points; only CASHLESS is offered."""
    pos_page(page, NOM_DU_POINT_DE_VENTE)
    nom_des_points = comptoir_en_points["points"]

    _toucher_la_tuile(page, comptoir_en_points["pins"])

    # Ligne du panier et total : le nom de la monnaie, separe du nombre.
    # / Cart line and total: the currency name, spaced from the number.
    expect(page.locator("#addition-list .addition-col-price").first).to_have_text(
        f"300.00 {nom_des_points}"
    )
    expect(page.locator("#addition-total-affiche")).to_have_text(f"300.00 {nom_des_points}")
    _valider_le_panier(page)
    expect(page.locator('[data-testid="paiement-btn-cashless"]')).to_be_visible()
    expect(page.locator('[data-testid="paiement-btn-especes"]')).to_have_count(0)
    expect(page.locator('[data-testid="paiement-btn-cb"]')).to_have_count(0)
    expect(page.locator('[data-testid="paiement-btn-cheque"]')).to_have_count(0)
    expect(page.locator('[data-testid="paiement-btn-offrir"]')).to_have_count(0)
    expect(page.locator(".payment-total-val").first).to_have_text(f"300,00 {nom_des_points}")


def test_un_panier_points_et_euros_est_refuse_a_valider(page, pos_page, comptoir_en_points):
    """E22 : Pin's + pinte a 5 € : « encaissez-les séparément » des VALIDER.
    / Pin + 5 € pint: refused as soon as VALIDATE is tapped."""
    pos_page(page, NOM_DU_POINT_DE_VENTE)

    _toucher_la_tuile(page, comptoir_en_points["pins"])
    _toucher_la_tuile(page, comptoir_en_points["biere"])
    page.locator(f'[data-testid="tarif-btn-{comptoir_en_points["pinte"]}"]').click()
    _valider_le_panier(page)

    expect(page.locator("#messages")).to_contain_text("encaissez-les séparément")
    expect(page.locator('[data-testid="paiement-btn-cashless"]')).to_have_count(0)


def test_un_paiement_en_points_reussi_affiche_des_points(page, pos_page, comptoir_en_points):
    """E23 : paiement par carte NFC simulee : l'ecran de succes est en points.
    / Payment with a simulated NFC card: the success screen is in points."""
    pos_page(page, NOM_DU_POINT_DE_VENTE)
    nom_des_points = comptoir_en_points["points"]

    _toucher_la_tuile(page, comptoir_en_points["pins"])
    _valider_le_panier(page)
    page.locator('[data-testid="paiement-btn-cashless"]').click()
    # Mode demo : le bouton de simulation fait apparaitre la saisie du tag. La
    # saisie se valide par la touche Entree : le bouton « Valider » de la
    # simulation est recouvert par le fond de la popup d'attente de carte.
    # / Demo mode: the toggle shows the tag input, submitted with Enter (the
    #   simulation's button is covered by the card-wait popup backdrop).
    page.locator(".nfc-toggle-simu .touch").click()
    saisie_du_tag = page.locator("#nfc-simu-manual-input")
    saisie_du_tag.fill(TAG_DE_LA_CARTE_CLIENT)
    saisie_du_tag.press("Enter")

    succes = page.locator('[data-testid="paiement-succes"]')
    expect(succes).to_be_visible()
    expect(succes.locator(".test-return-total-achats")).to_contain_text(
        f"300,00 {nom_des_points}"
    )
    expect(succes.locator('[data-testid="paiement-carte1-debite"]')).to_contain_text(
        f"300,00 {nom_des_points}"
    )
    expect(succes).not_to_contain_text("300,00 €")


def test_retirer_la_ligne_en_points_rend_le_total_en_euros(page, pos_page, comptoir_en_points):
    """Panier Pin's + pinte, on retire le Pin's : le total repasse en euros tout de
    suite (la ligne en train de disparaitre ne compte plus).
    / Pin + pint, remove the pin: the total goes back to euros at once."""
    pos_page(page, NOM_DU_POINT_DE_VENTE)

    _toucher_la_tuile(page, comptoir_en_points["pins"])
    _toucher_la_tuile(page, comptoir_en_points["biere"])
    page.locator(f'[data-testid="tarif-btn-{comptoir_en_points["pinte"]}"]').click()
    ligne_du_pins = page.locator(f'#addition-line-{comptoir_en_points["pins"]}')
    ligne_du_pins.locator(".addition-remove-btn").click()

    expect(page.locator("#addition-total-affiche")).to_have_text("5.00 €")
