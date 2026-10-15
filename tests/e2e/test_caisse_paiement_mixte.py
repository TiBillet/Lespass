"""
tests/e2e/test_caisse_paiement_mixte.py — L'ecran du paiement mixte, dans la vraie caisse.
/ The split payment screen, in the real POS.

LOCALISATION : tests/e2e/test_caisse_paiement_mixte.py

CE QUI EST TESTE :
L'ecran de repartition (partial/hx_paiement_mixte.html) est du JavaScript : saisie au
pave, ligne active, « Reste a repartir », bouton « Mettre le reste ici », activation de
VALIDER. Les tests pytest (tests/pytest/test_paiement_mixte.py) couvrent le serveur ;
ici on joue l'ecran de bout en bout, jusqu'aux reglements ecrits en base.
/ The split screen is JavaScript. The pytest file covers the server; here the screen
  is played end to end, down to the payments written in the database.

DONNEES :
Le test cree ses propres objets (idempotent) : le point de vente « Caisse mixte E2E »
(service direct, especes + CB + cheque) et une « Planche mixte E2E » a 25,00 €.
Il s'appuie sur la carte primaire seedee par `create_test_pos_data`.
/ The test creates its own objects; it relies on the seeded primary card.

LANCEMENT / RUN :
    make e2e ARGS="tests/e2e/test_caisse_paiement_mixte.py"
"""

import json
import re

import pytest
from playwright.sync_api import expect


# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>` (list: make help, or pytest.ini).
pytestmark = [pytest.mark.caisse]

NOM_DU_POINT_DE_VENTE = "Caisse mixte E2E"
NOM_DU_PRODUIT = "Planche mixte E2E"

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
def caisse_mixte(django_shell, ensure_pos_data):
    """Cree (ou retrouve) le point de vente et la planche a 25 €.
    Le point de vente est remis a especes + CB + cheque a chaque lancement.
    / Creates (or finds) the POS and the 25 € board. Methods are reset each run."""
    sortie = django_shell(
        "import json\n"
        "from decimal import Decimal\n"
        "from BaseBillet.models import Price, Product\n"
        "from laboutik.models import CartePrimaire, PointDeVente\n"
        f"pv, _c = PointDeVente.objects.get_or_create(name='{NOM_DU_POINT_DE_VENTE}',"
        " defaults={'comportement': PointDeVente.DIRECT, 'service_direct': True,"
        " 'afficher_les_prix': True})\n"
        "pv.accepte_especes = True\n"
        "pv.accepte_carte_bancaire = True\n"
        "pv.accepte_cheque = True\n"
        "pv.save()\n"
        f"planche, _c = Product.objects.get_or_create(name='{NOM_DU_PRODUIT}',"
        " defaults={'methode_caisse': Product.VENTE})\n"
        "Price.objects.get_or_create(product=planche, name='Planche',"
        " defaults={'prix': Decimal('25.00')})\n"
        "pv.products.add(planche)\n"
        f"primaire = CartePrimaire.objects.filter(carte__tag_id='{TAG_DE_LA_CARTE_PRIMAIRE}').first()\n"
        "if primaire is not None:\n"
        "    primaire.points_de_vente.add(pv)\n"
        "print('CAISSE_MIXTE_JSON=' + json.dumps({\n"
        "    'primaire': primaire is not None,\n"
        "    'pv': str(pv.uuid),\n"
        "    'planche': str(planche.uuid),\n"
        "}))"
    )
    donnees = _lire_json_marque(sortie, "CAISSE_MIXTE_JSON=")
    if not donnees["primaire"]:
        pytest.fail(f"Carte primaire {TAG_DE_LA_CARTE_PRIMAIRE} introuvable (seed).")
    return donnees


@pytest.fixture
def erreurs_de_la_page(page):
    """Note les erreurs JavaScript de la page. Le test echoue s'il y en a eu une.
    / Records JavaScript errors; the test fails if any occurred."""
    erreurs = []
    page.on("pageerror", lambda erreur: erreurs.append(str(erreur)))
    yield erreurs
    assert erreurs == [], f"Erreurs JavaScript : {erreurs}"


# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #


def _ouvrir_l_ecran_mixte(page, pos_page, caisse_mixte):
    """Caisse ouverte → planche au panier → VALIDER → tuile MIXTE.
    / Open POS → board in the cart → VALIDATE → MIXED tile."""
    page.set_viewport_size({"width": 1280, "height": 800})
    pos_page(page, NOM_DU_POINT_DE_VENTE)

    page.locator(f'[data-testid="article-{caisse_mixte["planche"]}"]').click()
    bouton_valider_le_panier = page.locator('[data-testid="addition-valider"]')
    expect(bouton_valider_le_panier).to_be_enabled()
    bouton_valider_le_panier.click()

    tuile_mixte = page.locator('[data-testid="paiement-btn-mixte"]')
    expect(tuile_mixte).to_be_visible()
    tuile_mixte.click()
    expect(page.locator('[data-testid="paiement-mixte"]')).to_be_visible()


def _taper_au_pave(page, touches):
    """Tape une suite de touches au pave de l'ecran mixte (ex : "10").
    / Types a sequence of keys on the split screen keypad."""
    for touche in touches:
        page.locator(f'#mixte-numpad [data-key="{touche}"]').click()


def _ligne(page, code_du_moyen):
    return page.locator(f'[data-testid="mixte-ligne-{code_du_moyen}"]')


def _montant(page, code_du_moyen):
    return page.locator(f'[data-testid="mixte-montant-{code_du_moyen}"]')


def _reglements_de_la_derniere_vente(django_shell, uuid_du_point_de_vente):
    """Numero et reglements de la derniere vente reglee du point de vente.
    / Number and payments of the POS's last settled sale."""
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models_vente import Vente\n"
        f"vente = Vente.objects.filter(point_de_vente__uuid='{uuid_du_point_de_vente}',"
        " statut=Vente.Statut.REGLEE).order_by('-numero').first()\n"
        "reglements = {}\n"
        "numero = None\n"
        "if vente is not None:\n"
        "    numero = vente.numero\n"
        "    for reglement in vente.reglements.all():\n"
        "        reglements[reglement.moyen] = reglement.montant\n"
        "print('VENTE_JSON=' + json.dumps({'numero': numero, 'reglements': reglements}))"
    )
    return _lire_json_marque(sortie, "VENTE_JSON=")


# ------------------------------------------------------------------ #
#  Tests
# ------------------------------------------------------------------ #


def test_ecran_mixte_affiche_une_ligne_par_moyen_et_le_total(
    page, pos_page, caisse_mixte, erreurs_de_la_page
):
    """L'ecran affiche especes, CB et cheque. La premiere ligne est active.
    Tout reste a repartir et VALIDER est grise.
    / One row per method, the first one active, everything left, VALIDATE disabled."""
    _ouvrir_l_ecran_mixte(page, pos_page, caisse_mixte)

    expect(_ligne(page, "espece")).to_be_visible()
    expect(_ligne(page, "carte_bancaire")).to_be_visible()
    expect(_ligne(page, "CH")).to_be_visible()
    expect(_ligne(page, "espece")).to_have_attribute("aria-checked", "true")
    expect(page.locator('[data-testid="mixte-reste"]')).to_have_text("25,00 €")
    expect(page.locator('[data-testid="mixte-btn-valider"]')).to_be_disabled()


def test_le_pave_remplit_la_ligne_active_et_le_reste_baisse(
    page, pos_page, caisse_mixte, erreurs_de_la_page
):
    """10 au pave : la ligne especes affiche 10 €, il reste 15,00 €.
    Un seul moyen utilise : VALIDER reste grise.
    / Typing 10 fills the cash row, 15.00 € left, VALIDATE still disabled."""
    _ouvrir_l_ecran_mixte(page, pos_page, caisse_mixte)

    _taper_au_pave(page, "10")

    expect(_montant(page, "espece")).to_contain_text("10")
    expect(page.locator("#mixte-input-espece")).to_have_value("1000")
    expect(page.locator('[data-testid="mixte-reste"]')).to_have_text("15,00 €")
    expect(page.locator('[data-testid="mixte-btn-valider"]')).to_be_disabled()


def test_mettre_le_reste_sur_une_autre_ligne_active_valider(
    page, pos_page, caisse_mixte, erreurs_de_la_page
):
    """10 en especes, puis ligne CB + « Mettre le reste ici » : CB = 15,00 €,
    reste 0,00 €, VALIDER s'active.
    / 10 cash, then card row + "put the rest here": 0.00 € left, VALIDATE enabled."""
    _ouvrir_l_ecran_mixte(page, pos_page, caisse_mixte)

    _taper_au_pave(page, "10")
    _ligne(page, "carte_bancaire").click()
    expect(_ligne(page, "carte_bancaire")).to_have_attribute("aria-checked", "true")
    expect(_ligne(page, "espece")).to_have_attribute("aria-checked", "false")
    page.locator('[data-testid="mixte-btn-reste"]').click()

    expect(_montant(page, "carte_bancaire")).to_have_text("15,00 €")
    expect(page.locator("#mixte-input-carte_bancaire")).to_have_value("1500")
    expect(page.locator('[data-testid="mixte-reste"]')).to_have_text("0,00 €")
    expect(page.locator('[data-testid="mixte-btn-valider"]')).to_be_enabled()


def test_la_touche_c_efface_la_ligne_active(
    page, pos_page, caisse_mixte, erreurs_de_la_page
):
    """Repartition complete, puis « C » sur la ligne CB : la CB revient a 0,
    il reste 15,00 € et VALIDER se grise. Les especes ne bougent pas.
    / "C" clears the active row only; VALIDATE is disabled again."""
    _ouvrir_l_ecran_mixte(page, pos_page, caisse_mixte)

    _taper_au_pave(page, "10")
    _ligne(page, "carte_bancaire").click()
    page.locator('[data-testid="mixte-btn-reste"]').click()
    expect(page.locator('[data-testid="mixte-btn-valider"]')).to_be_enabled()

    _taper_au_pave(page, "C")

    expect(_montant(page, "carte_bancaire")).to_have_text("0,00 €")
    expect(page.locator("#mixte-input-carte_bancaire")).to_have_value("0")
    expect(page.locator("#mixte-input-espece")).to_have_value("1000")
    expect(page.locator('[data-testid="mixte-reste"]')).to_have_text("15,00 €")
    expect(page.locator('[data-testid="mixte-btn-valider"]')).to_be_disabled()


def test_depasser_le_total_passe_le_reste_en_negatif_et_grise_valider(
    page, pos_page, caisse_mixte, erreurs_de_la_page
):
    """20 en especes + 10 en CB pour 25 € : il reste -5,00 €, la zone passe en
    « depasse » et VALIDER reste grise.
    / Amounts above the total: negative remainder, "exceeded" state, disabled."""
    _ouvrir_l_ecran_mixte(page, pos_page, caisse_mixte)

    _taper_au_pave(page, "20")
    _ligne(page, "carte_bancaire").click()
    _taper_au_pave(page, "10")

    expect(page.locator('[data-testid="mixte-reste"]')).to_have_text("-5,00 €")
    expect(page.locator("#mixte-repartition")).to_have_class(
        re.compile(r"\bis-depasse\b")
    )
    expect(page.locator('[data-testid="mixte-btn-valider"]')).to_be_disabled()


def test_annuler_ferme_l_ecran_et_revient_au_choix_du_paiement(
    page, pos_page, caisse_mixte, erreurs_de_la_page
):
    """Annuler ferme l'ecran mixte. Le choix du moyen de paiement est toujours la.
    / Cancel closes the split screen; the payment choice is still there."""
    _ouvrir_l_ecran_mixte(page, pos_page, caisse_mixte)

    page.locator('[data-testid="mixte-btn-annuler"]').click()

    expect(page.locator('[data-testid="paiement-mixte"]')).to_have_count(0)
    expect(page.locator('[data-testid="paiement-btn-mixte"]')).to_be_visible()


def test_valider_encaisse_la_vente_avec_un_reglement_par_moyen(
    page, pos_page, caisse_mixte, django_shell, erreurs_de_la_page
):
    """10 € en especes + 15 € en CB, VALIDER : l'ecran de succes dit « paiement
    mixte », l'ecran mixte se ferme, et la nouvelle vente a deux reglements :
    especes 1000 et CB 1500.
    / Validate: success screen says "paiement mixte", the split screen closes,
      and the new sale has a 1000 cash payment and a 1500 card payment."""
    vente_avant = _reglements_de_la_derniere_vente(django_shell, caisse_mixte["pv"])
    _ouvrir_l_ecran_mixte(page, pos_page, caisse_mixte)

    _taper_au_pave(page, "10")
    _ligne(page, "carte_bancaire").click()
    page.locator('[data-testid="mixte-btn-reste"]').click()
    page.locator('[data-testid="mixte-btn-valider"]').click()

    succes = page.locator('[data-testid="paiement-succes"]')
    expect(succes).to_be_visible()
    expect(succes).to_contain_text("paiement mixte")
    expect(page.locator('[data-testid="paiement-mixte"]')).to_have_count(0)

    vente_apres = _reglements_de_la_derniere_vente(django_shell, caisse_mixte["pv"])
    assert vente_apres["numero"] != vente_avant["numero"], (
        "Aucune nouvelle vente reglee pour ce point de vente."
    )
    assert vente_apres["reglements"] == {"CA": 1000, "CC": 1500}
