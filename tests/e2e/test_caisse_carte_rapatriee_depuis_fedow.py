"""
tests/e2e/test_caisse_carte_rapatriee_depuis_fedow.py
Une carte connue SEULEMENT de l'ancien Fedow marche a la caisse des le premier scan.
/ A card known ONLY to the old Fedow works at the POS from the very first scan.

LOCALISATION : tests/e2e/test_caisse_carte_rapatriee_depuis_fedow.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
Chantier 02 « rapatriement des cartes Fedow », § 8.5 de la spec
(TECH_DOC/SESSIONS/QRCODECASHLESS/CHANTIER-02-rapatriement-cartes-fedow.md).
Une carte chargee chez l'ancien Fedow n'existe pas encore dans la base de Lespass.
Au premier scan, `trouver_ou_rapatrier_la_carte` (QrcodeCashless/services.py) la lit
chez Fedow et fabrique le miroir local (`CarteCashless` + `Detail` du lieu).
/ A card loaded on the old Fedow is missing from Lespass. On the first scan, the
service reads it on Fedow and builds the local mirror.

LE PARCOURS (lieu `lespass`, point de vente « Bar ») / THE JOURNEY
1. CHECK CARTE, scan de la carte : la fiche s'affiche (carte anonyme, 0 €).
   C'est ce scan qui rapatrie la carte (`retour_carte`).
2. Depuis la fiche : recharge de 10 € de monnaie locale, payee en especes.
3. Vente d'un Coca (3 €), payee par la carte NFC : le paiement aboutit.
4. Rescan de la carte (CHECK CARTE) : la fiche s'affiche avec 7 €.
5. En base : la `CarteCashless` existe, rattachee a un `Detail` du lieu `lespass`.
L'absence d'appel a Fedow au rescan n'est pas observable ici : elle est prouvee
par les tests pytest du chantier.
/ The absence of a Fedow call on rescan is not observable here (pytest covers it).

DONNEES / DATA
--------------
La carte est creee chez le VRAI Fedow de dev, avec un tag hexadecimal NEUF a chaque
lancement : Fedow n'a pas de route de suppression, la carte y reste.
En fin de test, la `CarteCashless` locale et son portefeuille miroir sont supprimes
s'ils le peuvent. Apres un parcours complet, ils ne le peuvent pas : la vente et les
transactions (comptabilite) les protegent (on_delete=PROTECT). On ne supprime jamais
de la comptabilite : le tag neuf suffit a rendre le test rejouable.
/ Fresh hex tag per run, the card stays on Fedow. The local card and mirror wallet
are deleted only when nothing protects them; after a full journey the sale and
transactions protect them, and accounting is never deleted.

PREREQUIS / PREREQUISITES
-------------------------
- le serveur de dev tourne, et l'ancien Fedow de dev repond (`can_fedow()` vrai) ;
- les donnees POS de test existent (fixture `ensure_pos_data`).

LANCEMENT / RUN :
    make e2e ARGS="tests/e2e/test_caisse_carte_rapatriee_depuis_fedow.py"
"""

import json
import re
import uuid as uuid_module

import pytest
from playwright.sync_api import expect


# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>` (list: make help, or pytest.ini).
pytestmark = [pytest.mark.caisse, pytest.mark.monnaie]

# Le point de vente du parcours, seede par `create_test_pos_data`.
# / The journey's point of sale, seeded by create_test_pos_data.
NOM_DU_POINT_DE_VENTE = "Bar"

# L'article vendu, et son prix en euros. Un seul tarif : il va droit au panier.
# / The sold item and its price. A single rate: straight into the cart.
NOM_DE_L_ARTICLE = "Coca"
PRIX_DE_L_ARTICLE_EUROS = 3

# La monnaie rechargee depuis la fiche de la carte, et le tarif choisi.
# / The currency topped up from the card sheet, and the chosen rate.
NOM_DE_LA_MONNAIE_RECHARGEE = "Monnaie locale"
MONTANT_DE_LA_RECHARGE_EUROS = 10


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


@pytest.fixture
def carte_connue_seulement_de_l_ancien_fedow(django_shell):
    """Cree une carte chez le vrai Fedow de dev, absente de la base locale.
    / Creates a card on the real dev Fedow, missing from the local database.

    Tag neuf a chaque lancement : 8 caracteres hexadecimaux en majuscules.
    Le qrcode_uuid suit la convention de demo_data_v2 (1er bloc = le tag).
    / Fresh tag per run; qrcode_uuid follows the demo_data_v2 convention.
    """
    tag = uuid_module.uuid4().hex[:8].upper()
    qrcode_uuid = f"{tag.lower()}-0000-4000-8000-000000000000"

    # 1. Le lieu est relie a l'ancien Fedow, et le tag est inconnu en local.
    # / 1. The venue is linked to the old Fedow, and the tag is unknown locally.
    sortie = django_shell(
        "import json\n"
        "from QrcodeCashless.models import CarteCashless\n"
        "from fedow_connect.models import FedowConfig\n"
        "print('AVANT_JSON=' + json.dumps({\n"
        "    'can_fedow': FedowConfig.get_solo().can_fedow(),\n"
        f"    'cartes_locales': CarteCashless.objects.filter(tag_id='{tag}').count(),\n"
        "}))"
    )
    avant = _lire_json_marque(sortie, "AVANT_JSON=")
    if not avant["can_fedow"]:
        pytest.fail(
            "Le lieu lespass n'est pas relie a l'ancien Fedow (can_fedow() faux) : "
            "aucune carte ne peut etre rapatriee. Verifier que fedow_django tourne."
        )
    assert avant["cartes_locales"] == 0, (
        f"Le tag tire au sort {tag} existe deja en local : relancer le test."
    )

    # 2. Creation de la carte chez Fedow (anonyme, generation 1), puis relecture
    #    chez Fedow. card_tag_id_retrieve n'ecrit rien en local.
    # / 2. Card created on Fedow, then read back there (no local write).
    sortie = django_shell(
        "import json\n"
        "from QrcodeCashless.models import CarteCashless\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "FedowAPI().NFCcard.create([{\n"
        f"    'first_tag_id': '{tag}',\n"
        f"    'qrcode_uuid': '{qrcode_uuid}',\n"
        f"    'number_printed': '{tag}',\n"
        "}])\n"
        f"fiche = FedowAPI().NFCcard.card_tag_id_retrieve('{tag}')\n"
        "print('CREEE_JSON=' + json.dumps({\n"
        "    'connue_de_fedow': fiche is not None,\n"
        "    'wallet_uuid': str(fiche['wallet_uuid']) if fiche else None,\n"
        f"    'cartes_locales': CarteCashless.objects.filter(tag_id='{tag}').count(),\n"
        "}))"
    )
    creee = _lire_json_marque(sortie, "CREEE_JSON=")
    assert creee["connue_de_fedow"], f"Fedow ne connait pas la carte {tag} creee."
    assert creee["cartes_locales"] == 0, (
        f"La creation chez Fedow a cree la carte {tag} en local : le parcours "
        "ne testerait plus le rapatriement."
    )

    yield {
        "tag": tag,
        "qrcode_uuid": qrcode_uuid,
        "wallet_uuid": creee["wallet_uuid"],
    }

    # Nettoyage cible, sans jamais toucher a la comptabilite (PIEGES 12.4).
    # ProtectedError est attendue apres un parcours complet : la vente et les
    # transactions protegent la carte et le portefeuille. On les garde alors.
    # / Targeted cleanup, never touching accounting. ProtectedError is expected
    # after a full journey: sale and transactions protect card and wallet.
    sortie = django_shell(
        "from django.db import transaction\n"
        "from django.db.models.deletion import ProtectedError\n"
        "from AuthBillet.models import Wallet\n"
        "from QrcodeCashless.models import CarteCashless\n"
        "from fedow_core.models import Token\n"
        f"carte = CarteCashless.objects.filter(tag_id='{tag}').first()\n"
        "carte_supprimee = carte is None\n"
        "if carte is not None:\n"
        "    try:\n"
        "        with transaction.atomic():\n"
        "            carte.delete()\n"
        "        carte_supprimee = True\n"
        "    except ProtectedError:\n"
        "        print('CARTE=conservee')\n"
        f"wallet = Wallet.objects.filter(uuid='{creee['wallet_uuid']}').first()\n"
        "if carte_supprimee and wallet is not None:\n"
        "    try:\n"
        "        with transaction.atomic():\n"
        "            Token.objects.filter(wallet=wallet).delete()\n"
        "            wallet.delete()\n"
        "    except ProtectedError:\n"
        "        print('WALLET=conserve')\n"
    )
    print(f"\nNettoyage de la carte {tag} : {sortie or 'supprimee'}")


def test_une_carte_connue_seulement_de_l_ancien_fedow_est_rapatriee_au_premier_scan_puis_paie_a_la_caisse(
    page, pos_page, django_shell, carte_connue_seulement_de_l_ancien_fedow
):
    """Check carte (rapatriement), recharge en especes, paiement NFC, rescan.
    / Card check (fetch), cash top-up, NFC payment, rescan."""
    tag = carte_connue_seulement_de_l_ancien_fedow["tag"]

    sortie = django_shell(
        "from laboutik.models import PointDeVente\n"
        f"pv = PointDeVente.objects.get(name='{NOM_DU_POINT_DE_VENTE}')\n"
        f"article = pv.products.get(name='{NOM_DE_L_ARTICLE}')\n"
        "print('ARTICLE=' + str(article.uuid))"
    )
    uuid_de_l_article = re.search(r"ARTICLE=(\S+)", sortie).group(1)

    def scanner_la_carte():
        # Lecteur NFC simule du mode demo : saisie du tag, validee par Entree.
        # / Demo mode's simulated NFC reader: type the tag, press Enter.
        page.locator(".nfc-toggle-simu .touch").click()
        saisie_du_tag = page.locator("#nfc-simu-manual-input")
        saisie_du_tag.fill(tag)
        saisie_du_tag.press("Enter")

    pos_page(page, NOM_DU_POINT_DE_VENTE)

    # --- 1. CHECK CARTE : premier scan, la carte est rapatriee ---
    # / 1. CARD CHECK: first scan, the card is fetched from Fedow
    page.locator('[data-testid="addition-check-carte"]').click()
    scanner_la_carte()
    fiche_de_la_carte = page.locator('[data-testid="retour-carte"]')
    expect(fiche_de_la_carte).to_be_visible()
    expect(page.locator('[data-testid="retour-carte-erreur"]')).to_have_count(0)
    expect(page.locator('[data-testid="retour-carte-anonyme"]')).to_be_visible()
    expect(page.locator('[data-testid="retour-carte-soldes"]')).to_contain_text(
        re.compile(r"(?<!\d)0[,.]00")
    )

    # --- 2. Recharge de 10 € depuis la fiche, payee en especes ---
    # / 2. 10 € top-up from the card sheet, paid in cash
    zone_de_recharge = page.locator('[data-testid="retour-carte-recharge"]')
    zone_de_recharge.locator(
        '[data-testid^="recharge-produit-"]', has_text=NOM_DE_LA_MONNAIE_RECHARGEE
    ).click()
    page.locator(
        '[data-testid^="recharge-montant-"]',
        has_text=re.compile(rf"^\s*{MONTANT_DE_LA_RECHARGE_EUROS}\s"),
    ).click()
    expect(page.locator('[data-testid="recharge-confirmation"]')).to_be_visible()
    page.locator('[data-testid="recharge-btn-especes"]').click()
    page.locator('[data-testid="paiement-btn-valider"]').click()
    succes_de_la_recharge = page.locator('[data-testid="paiement-succes"]')
    expect(succes_de_la_recharge).to_be_visible()
    succes_de_la_recharge.locator("#bt-retour-layer1").click()
    expect(succes_de_la_recharge).to_have_count(0)

    # --- 3. Vente d'un Coca, payee par la carte NFC ---
    # / 3. A Coca sold, paid with the NFC card
    page.locator(f'[data-testid="article-{uuid_de_l_article}"]').click()
    bouton_valider = page.locator('[data-testid="addition-valider"]')
    expect(bouton_valider).to_be_enabled()
    bouton_valider.click()
    page.locator('[data-testid="paiement-btn-cashless"]').click()
    scanner_la_carte()
    succes_du_paiement = page.locator('[data-testid="paiement-succes"]')
    expect(succes_du_paiement).to_be_visible()
    expect(
        succes_du_paiement.locator('[data-testid="paiement-carte1-debite"]')
    ).to_contain_text(re.compile(rf"(?<!\d){PRIX_DE_L_ARTICLE_EUROS}[,.]00"))
    succes_du_paiement.locator("#bt-retour-layer1").click()
    expect(succes_du_paiement).to_have_count(0)

    # --- 4. Rescan (CHECK CARTE) : la fiche s'affiche, avec le solde restant ---
    # / 4. Rescan (CARD CHECK): the sheet shows, with the remaining balance
    solde_restant_euros = MONTANT_DE_LA_RECHARGE_EUROS - PRIX_DE_L_ARTICLE_EUROS
    page.locator('[data-testid="addition-check-carte"]').click()
    scanner_la_carte()
    expect(fiche_de_la_carte).to_be_visible()
    expect(page.locator('[data-testid="retour-carte-erreur"]')).to_have_count(0)
    expect(page.locator('[data-testid="retour-carte-soldes"]')).to_contain_text(
        re.compile(rf"(?<!\d){solde_restant_euros}[,.]00")
    )

    # --- 5. En base : la carte locale existe, rattachee au lieu lespass ---
    # / 5. In the database: the local card exists, attached to the lespass venue
    sortie = django_shell(
        "import json\n"
        "from django.db import connection\n"
        "from QrcodeCashless.models import CarteCashless\n"
        f"cartes = CarteCashless.objects.filter(tag_id='{tag}').select_related('detail')\n"
        "carte = cartes.first()\n"
        "print('CARTE_JSON=' + json.dumps({\n"
        "    'nombre': cartes.count(),\n"
        "    'number': carte.number if carte else None,\n"
        "    'uuid': str(carte.uuid) if carte else None,\n"
        "    'origine': carte.detail.origine.schema_name if (carte and carte.detail) else None,\n"
        "    'lieu_courant': connection.tenant.schema_name,\n"
        "}))"
    )
    carte_en_base = _lire_json_marque(sortie, "CARTE_JSON=")
    assert carte_en_base["nombre"] == 1, (
        f"Carte {tag} absente en local : {carte_en_base}"
    )
    assert carte_en_base["origine"] == "lespass" == carte_en_base["lieu_courant"], (
        f"La carte rapatriee n'est pas rattachee au lieu lespass : {carte_en_base}"
    )
    assert carte_en_base["number"] == tag, f"Numero imprime faux : {carte_en_base}"
    assert (
        carte_en_base["uuid"] == carte_connue_seulement_de_l_ancien_fedow["qrcode_uuid"]
    ), f"L'uuid local n'est pas le qrcode_uuid de Fedow : {carte_en_base}"
