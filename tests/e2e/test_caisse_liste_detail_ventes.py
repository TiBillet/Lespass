"""
tests/e2e/test_caisse_liste_detail_ventes.py — Liste, detail et ticket d'une vente a la
caisse, dans le navigateur.
/ Register sales list, detail and receipt, in the browser.

LOCALISATION : tests/e2e/test_caisse_liste_detail_ventes.py

CE QUI EST TESTE :
Une vente payee avec deux moyens (monnaie locale + carte bancaire) :
- la liste des ventes (Historique de commande) montre UNE ligne : numero, total
  10,50 €, moyens en clair « 5,50 € Carte bancaire + 5,00 € <monnaie locale> » ;
- un clic sur la ligne deplie le detail (insere par JavaScript, `toggleDetailVente`)
  : un article « 3 » jus, les deux reglements, un seul bouton « Corriger » (celui de
  la carte bancaire) ;
- le bouton « Ré-imprimer » du detail envoie l'uuid de la VENTE a la route
  d'impression et affiche un retour.
Le depliage du detail et l'activation de ses boutons HTMX (`htmx.process`) ne se
testent que dans un vrai navigateur.
/ One two-method sale: one list row, the detail unfolded by JavaScript, the reprint
button sends the sale uuid.

DONNEES :
La vente est ecrite par le service de vente (`BaseBillet/services_vente.py`), au
point de vente « Bar » seede par `create_test_pos_data`, avec la monnaie locale (TLF)
du lieu. Fil rouge : 3 jus a 3,50 € = 10,50 €, payes 5,00 € en monnaie locale et
5,50 € par carte bancaire (deux parts : 350 × 1,428571 → 500, 350 × 1,571429 → 550).
Elle est reglee maintenant : elle est la plus recente du service en cours, en tete
de la premiere page.
/ The sale is written by the sale service at the seeded "Bar" point of sale.

LANCEMENT / RUN :
    make e2e ARGS="tests/e2e/test_caisse_liste_detail_ventes.py"
"""

import json
import re

import pytest
from playwright.sync_api import expect

NOM_DU_POINT_DE_VENTE = "Bar"

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
def vente_monnaie_locale_et_carte_bancaire(django_shell, ensure_pos_data):
    """Ecrit, par le service de vente, la vente du fil rouge au point de vente
    « Bar », et rend son uuid, son numero, le nom de la monnaie locale et l'uuid du
    point de vente.
    / Writes the running-example sale through the sale service; returns its data."""
    # Garde : le lieu doit avoir une monnaie locale (TLF) active, seedee par
    # `create_test_pos_data`. Sans elle, le test echoue avec un message clair.
    # / Guard: the venue needs an active local currency (TLF).
    sortie_de_la_garde = django_shell(
        "from django.db import connection\n"
        "from fedow_core.models import Asset\n"
        "monnaie_locale = Asset.objects.filter(tenant_origin=connection.tenant,"
        " category=Asset.TLF, active=True, archive=False).first()\n"
        "print('MONNAIE_LOCALE_PRESENTE=' + str(monnaie_locale is not None))"
    )
    if "MONNAIE_LOCALE_PRESENTE=True" not in sortie_de_la_garde:
        pytest.fail(
            "Le lieu n'a pas de monnaie locale (TLF) active. Reseeder : "
            "docker exec lespass_django poetry run python manage.py create_test_pos_data"
        )

    sortie = django_shell(
        "import json\n"
        "import uuid\n"
        "from decimal import Decimal\n"
        "from django.db import connection\n"
        "from BaseBillet.models import LigneArticle, PaymentMethod, Price, PriceSold,"
        " Product, ProductSold, SaleOrigin\n"
        "from BaseBillet.models_vente import Vente\n"
        "from BaseBillet.services_vente import ajouter_article, ajouter_reglement,"
        " encaisser_vente, ouvrir_vente\n"
        "from fedow_core.models import Asset\n"
        "from laboutik.models import PointDeVente\n"
        "lieu = connection.tenant\n"
        f"point_de_vente = PointDeVente.objects.get(name='{NOM_DU_POINT_DE_VENTE}')\n"
        "monnaie_locale = Asset.objects.filter(tenant_origin=lieu, category=Asset.TLF,"
        " active=True, archive=False).first()\n"
        "jus, _c = Product.objects.get_or_create(name='Jus liste ventes E2E',"
        " defaults={'methode_caisse': Product.VENTE})\n"
        "tarif, _c = Price.objects.get_or_create(product=jus, name='Verre',"
        " defaults={'prix': Decimal('3.50')})\n"
        "tarif_vendu = PriceSold.objects.create(productsold=ProductSold.objects.create("
        "product=jus), price=tarif, prix=tarif.prix)\n"
        "identifiant_du_paiement = uuid.uuid4()\n"
        "vente = ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE,"
        " point_de_vente=point_de_vente)\n"
        "ajouter_article(vente, pricesold=tarif_vendu, quantite=Decimal('1.428571'),"
        " prix_unitaire=350, taux_tva=Decimal('20'), total_catalogue_impose=500,"
        " payment_method=PaymentMethod.LOCAL_EURO, asset=monnaie_locale.uuid,"
        " status=LigneArticle.VALID, uuid_transaction=identifiant_du_paiement,"
        " point_de_vente=point_de_vente)\n"
        "ajouter_article(vente, pricesold=tarif_vendu, quantite=Decimal('1.571429'),"
        " prix_unitaire=350, taux_tva=Decimal('20'), total_catalogue_impose=550,"
        " payment_method=PaymentMethod.CC, status=LigneArticle.VALID,"
        " uuid_transaction=identifiant_du_paiement, point_de_vente=point_de_vente)\n"
        "ajouter_reglement(vente, moyen=PaymentMethod.LOCAL_EURO, montant=500,"
        " asset=monnaie_locale.uuid)\n"
        "ajouter_reglement(vente, moyen=PaymentMethod.CC, montant=550)\n"
        "vente = encaisser_vente(vente)\n"
        "print('VENTE_LISTE_JSON=' + json.dumps({\n"
        "    'uuid': str(vente.uuid),\n"
        "    'numero': vente.numero,\n"
        "    'monnaie_locale': monnaie_locale.name,\n"
        "    'uuid_pv': str(point_de_vente.uuid),\n"
        "}))"
    )
    return _lire_json_marque(sortie, "VENTE_LISTE_JSON=")


def _ouvrir_la_liste_des_ventes(page, login_as_admin, vente):
    """Ouvre la liste des ventes (page complete) du point de vente de la vente.
    / Opens the sales list (full page)."""
    login_as_admin(page)
    page.goto(
        f"/laboutik/caisse/liste-ventes/?uuid_pv={vente['uuid_pv']}"
        f"&tag_id_cm={TAG_DE_LA_CARTE_PRIMAIRE}"
    )
    page.wait_for_load_state("networkidle")


def _ligne_de_la_vente(page, vente):
    """La ligne de la liste qui porte le numero de la vente.
    / The list row carrying the sale number."""
    numero_de_la_vente = page.locator(
        '[data-testid="vente-numero"]',
        has_text=re.compile(rf"^\s*{vente['numero']}\s*$"),
    )
    return page.locator("tr.ventes-ligne-cliquable").filter(has=numero_de_la_vente)


def test_la_liste_montre_une_ligne_avec_les_moyens_en_clair(
    page, login_as_admin, vente_monnaie_locale_et_carte_bancaire
):
    """Une seule ligne pour la vente : total 10,50 €, moyens « 5,50 € Carte
    bancaire + 5,00 € <monnaie locale> ».
    / One row: total 10.50 €, methods in words."""
    vente = vente_monnaie_locale_et_carte_bancaire
    _ouvrir_la_liste_des_ventes(page, login_as_admin, vente)

    ligne = _ligne_de_la_vente(page, vente)

    expect(ligne).to_have_count(1)
    expect(ligne.locator('[data-testid="vente-total"]')).to_have_text("10,50 €")
    expect(ligne.locator('[data-testid="vente-moyens"]')).to_have_text(
        f"5,50 € Carte bancaire + 5,00 € {vente['monnaie_locale']}"
    )


def test_le_detail_deplie_montre_trois_jus_et_les_deux_reglements(
    page, login_as_admin, vente_monnaie_locale_et_carte_bancaire
):
    """Un clic sur la ligne deplie le detail : un article « 3 », les reglements
    5,50 € et 5,00 €, un seul bouton « Corriger » (la carte bancaire).
    / A click unfolds the detail: one item "3", both payments, one Correct button."""
    vente = vente_monnaie_locale_et_carte_bancaire
    _ouvrir_la_liste_des_ventes(page, login_as_admin, vente)

    _ligne_de_la_vente(page, vente).click()

    detail = page.locator('[data-testid="ventes-detail-collapse"]')
    expect(detail).to_be_visible()
    expect(detail.locator('[data-testid="detail-qty"]')).to_have_text(["3"])
    expect(detail.locator('[data-testid="detail-reglement-montant"]')).to_have_text(
        ["5,50 €", "5,00 €"]
    )
    expect(detail.locator('[data-testid="btn-corriger"]')).to_have_count(1)


def test_le_bouton_reimprimer_envoie_l_uuid_de_la_vente(
    page, login_as_admin, vente_monnaie_locale_et_carte_bancaire
):
    """Le bouton « Ré-imprimer » du detail deplie envoie l'uuid de la vente a la
    route d'impression, et un retour s'affiche sous les boutons.
    / The reprint button sends the sale uuid; a feedback shows below the buttons."""
    vente = vente_monnaie_locale_et_carte_bancaire
    _ouvrir_la_liste_des_ventes(page, login_as_admin, vente)
    _ligne_de_la_vente(page, vente).click()
    detail = page.locator('[data-testid="ventes-detail-collapse"]')
    expect(detail).to_be_visible()

    with page.expect_request(
        lambda requete: "imprimer_ticket" in requete.url and requete.method == "POST"
    ) as requete_d_impression:
        detail.locator('[data-testid="btn-reimprimer"]').click()

    donnees_envoyees = requete_d_impression.value.post_data or ""
    assert f"uuid_vente={vente['uuid']}" in donnees_envoyees, donnees_envoyees
    # Une session admin n'est pas un terminal : il n'a pas d'imprimante. La route
    # le dit, dans la zone de retour sous les boutons.
    # / An admin session is not a terminal: no printer; the route says so.
    expect(detail.locator('[data-testid="reimpression-feedback"]')).to_contain_text(
        "Aucune imprimante configurée pour ce terminal"
    )
