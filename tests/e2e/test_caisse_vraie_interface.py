"""
tests/e2e/test_caisse_vraie_interface.py — Le JavaScript de la caisse, dans la VRAIE caisse.
/ The POS JavaScript, in the REAL POS page.

LOCALISATION : tests/e2e/test_caisse_vraie_interface.py

CE QUI EST TESTE :
Quatre comportements de la caisse sont aussi testes sur une page fabriquee (rapide, sans
serveur, beaucoup de cas limites) :
- test_tarif_popup.py            : la popup des tarifs ;
- test_garde_stock_au_clic.py    : un clic ne peut pas ajouter plus que le stock ;
- test_addition_oubli_du_client.py : le client d'une vente ne passe pas a la suivante ;
- test_addition_bouton_valider_grise.py : VALIDER est grise pendant la requete.
Ici, chacun est rejoue de bout en bout dans la vraie caisse : vrai gabarit, vrais
scripts dans leur vrai ordre, vrai CSS, vraies reponses du serveur, donnees construites
par la vraie vue. Une page fabriquee ne voit ni un script manquant dans le gabarit, ni
une donnee dont la vue a change la forme, ni la vraie hauteur du bandeau et du panier.
/ Four POS behaviours also tested on a fabricated page are replayed end to end in the
  real POS: real template, scripts, CSS, server answers and view-built data.

DONNEES :
Le test cree ses propres objets (idempotent) : le point de vente « Caisse interface E2E »
(billetterie), une « Pression E2E » a trois tarifs (Demi, Pinte, Soutien a prix libre),
un « Sirop E2E » a un tarif, un « Cidre E2E » en stock bloquant, un evenement futur avec
un billet, une carte liee a une personne et une carte anonyme. Il s'appuie sur la carte
primaire seedee par `create_test_pos_data`.
/ The test creates its own objects; it relies on the seeded primary card.

LANCEMENT / RUN :
    make e2e ARGS="tests/e2e/test_caisse_vraie_interface.py"
"""

import json

import pytest
from playwright.sync_api import expect


# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>` (list: make help, or pytest.ini).
pytestmark = [pytest.mark.caisse]

NOM_DU_POINT_DE_VENTE = "Caisse interface E2E"
NOM_DE_L_EVENEMENT = "Concert caisse interface E2E"

# `CarteCashless.tag_id` est limite a 8 caracteres (PIEGES 9.31).
# / CarteCashless.tag_id is limited to 8 characters.
TAG_DE_LA_CARTE_D_ALICE = "E2EOUB01"
TAG_DE_LA_CARTE_ANONYME = "E2EOUB02"
EMAIL_D_ALICE = "e2e-oubli-alice@tibillet.localhost"

# La carte primaire du caissier, seedee par `create_test_pos_data`.
# / The cashier's primary card, seeded by create_test_pos_data.
TAG_DE_LA_CARTE_PRIMAIRE = "A49E8E2A"

STOCK_DU_CIDRE = 2


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
def caisse_de_test(django_shell, ensure_pos_data):
    """Cree (ou retrouve) le point de vente, les articles, l'evenement et les cartes.
    / Creates (or finds) the POS, items, event and cards."""
    sortie = django_shell(
        "import json\n"
        "from datetime import timedelta\n"
        "from decimal import Decimal\n"
        "from django.db import connection\n"
        "from django.utils import timezone\n"
        "from AuthBillet.models import TibilletUser, Wallet\n"
        "from BaseBillet.models import Event, Price, Product\n"
        "from QrcodeCashless.models import CarteCashless\n"
        "from laboutik.models import CartePrimaire, PointDeVente\n"
        "lieu = connection.tenant\n"
        f"pv, _c = PointDeVente.objects.get_or_create(name='{NOM_DU_POINT_DE_VENTE}',"
        " defaults={'comportement': PointDeVente.BILLETTERIE, 'service_direct': True,"
        " 'afficher_les_prix': True, 'accepte_especes': True,"
        " 'accepte_carte_bancaire': True})\n"
        # Pression : deux tarifs fixes et un prix libre -> popup des tarifs
        # / Draught beer: two fixed rates and a free price -> rate popup
        "pression, _c = Product.objects.get_or_create(name='Pression E2E',"
        " defaults={'methode_caisse': Product.VENTE})\n"
        "demi, _c = Price.objects.get_or_create(product=pression, name='Demi',"
        " defaults={'prix': Decimal('3.00'), 'order': 1})\n"
        "pinte, _c = Price.objects.get_or_create(product=pression, name='Pinte',"
        " defaults={'prix': Decimal('5.50'), 'order': 2})\n"
        "soutien, _c = Price.objects.get_or_create(product=pression, name='Soutien',"
        " defaults={'prix': Decimal('2.00'), 'free_price': True, 'order': 3})\n"
        # Sirop : un seul tarif -> ajout direct au panier
        # / Syrup: a single rate -> straight into the cart
        "sirop, _c = Product.objects.get_or_create(name='Sirop E2E',"
        " defaults={'methode_caisse': Product.VENTE})\n"
        "Price.objects.get_or_create(product=sirop, name='Verre',"
        " defaults={'prix': Decimal('2.00')})\n"
        # Cidre : un seul tarif, en stock bloquant (remis a niveau par stock_du_cidre)
        # / Cider: one rate, blocking stock (reset by stock_du_cidre)
        "cidre, _c = Product.objects.get_or_create(name='Cidre E2E',"
        " defaults={'methode_caisse': Product.VENTE})\n"
        "Price.objects.get_or_create(product=cidre, name='Bouteille',"
        " defaults={'prix': Decimal('4.00')})\n"
        # Vendu pour de vrai (sans annulation) : le produit a un compte, sinon la
        # vraie journée du lieu ne s'exporte plus (FEC, Dolibarr).
        # / Really sold: the product needs an account.
        "import sys\n"
        "sys.path.insert(0, '/DjangoFiles/tests/pytest')\n"
        "from fabriques_vente import donner_un_compte_au_produit\n"
        "for produit_vendu_en_euros in [pression, sirop, cidre]:\n"
        "    donner_un_compte_au_produit(produit_vendu_en_euros)\n"
        "pv.products.add(pression, sirop, cidre)\n"
        # Billet : un evenement futur (la caisse billetterie liste les evenements futurs)
        # / Ticket: a future event (the ticketing POS lists future events)
        "billet, _c = Product.objects.get_or_create(name='Billet caisse interface E2E',"
        " defaults={'categorie_article': Product.BILLET, 'publish': True})\n"
        "plein_tarif, _c = Price.objects.get_or_create(product=billet, name='Plein tarif',"
        " defaults={'prix': Decimal('15.00'), 'publish': True})\n"
        f"evenement = Event.objects.filter(name='{NOM_DE_L_EVENEMENT}').first()\n"
        "if evenement is None:\n"
        f"    evenement = Event.objects.create(name='{NOM_DE_L_EVENEMENT}',"
        " datetime=timezone.now() + timedelta(days=30), jauge_max=30000, published=True)\n"
        "evenement.datetime = timezone.now() + timedelta(days=30)\n"
        "evenement.published = True\n"
        "evenement.archived = False\n"
        "evenement.save()\n"
        "evenement.products.add(billet)\n"
        f"primaire = CartePrimaire.objects.filter(carte__tag_id='{TAG_DE_LA_CARTE_PRIMAIRE}').first()\n"
        "if primaire is not None:\n"
        "    primaire.points_de_vente.add(pv)\n"
        # Alice et sa carte, plus une carte anonyme (sans personne)
        # / Alice and her card, plus an anonymous card (no person)
        f"alice, _c = TibilletUser.objects.get_or_create(email='{EMAIL_D_ALICE}',"
        f" defaults={{'username': '{EMAIL_D_ALICE}', 'first_name': 'Alice', 'last_name': 'Martin'}})\n"
        "if alice.wallet is None:\n"
        "    alice.wallet = Wallet.objects.create(origin=lieu, name='Wallet E2E Alice')\n"
        "    alice.save()\n"
        f"carte_alice, _c = CarteCashless.objects.get_or_create(tag_id='{TAG_DE_LA_CARTE_D_ALICE}',"
        f" defaults={{'number': '{TAG_DE_LA_CARTE_D_ALICE}', 'user': alice}})\n"
        "if carte_alice.user_id != alice.pk:\n"
        "    carte_alice.user = alice\n"
        "    carte_alice.save()\n"
        f"carte_anonyme, _c = CarteCashless.objects.get_or_create(tag_id='{TAG_DE_LA_CARTE_ANONYME}',"
        f" defaults={{'number': '{TAG_DE_LA_CARTE_ANONYME}'}})\n"
        "if carte_anonyme.user_id is not None:\n"
        "    carte_anonyme.user = None\n"
        "    carte_anonyme.save()\n"
        "print('CAISSE_INTERFACE_JSON=' + json.dumps({\n"
        "    'primaire': primaire is not None,\n"
        "    'pression': str(pression.uuid),\n"
        "    'demi': str(demi.uuid),\n"
        "    'pinte': str(pinte.uuid),\n"
        "    'soutien': str(soutien.uuid),\n"
        "    'sirop': str(sirop.uuid),\n"
        "    'cidre': str(cidre.uuid),\n"
        "    'evenement': str(evenement.uuid),\n"
        "}))"
    )
    donnees = _lire_json_marque(sortie, "CAISSE_INTERFACE_JSON=")
    if not donnees["primaire"]:
        pytest.fail(f"Carte primaire {TAG_DE_LA_CARTE_PRIMAIRE} introuvable (seed).")
    return donnees


@pytest.fixture
def erreurs_de_la_page(page):
    """Note les erreurs JavaScript et les erreurs de console de la vraie caisse.
    Le test echoue s'il y en a eu une.
    / Records JavaScript and console errors; the test fails if any occurred."""
    erreurs = {"javascript": [], "console": []}
    page.on("pageerror", lambda erreur: erreurs["javascript"].append(str(erreur)))
    page.on(
        "console",
        lambda message: (
            erreurs["console"].append(message.text) if message.type == "error" else None
        ),
    )
    yield erreurs
    assert erreurs["javascript"] == [], f"Erreurs JavaScript : {erreurs['javascript']}"


def _boite(page, selecteur):
    """Rectangle d'un element a l'ecran. / On-screen rectangle of an element."""
    return page.eval_on_selector(
        selecteur,
        """element => {
            const rectangle = element.getBoundingClientRect()
            return {haut: rectangle.top, bas: rectangle.bottom,
                    gauche: rectangle.left, droite: rectangle.right}
        }""",
    )


def _ouvrir_la_caisse(page, pos_page, largeur, hauteur):
    page.set_viewport_size({"width": largeur, "height": hauteur})
    pos_page(page, NOM_DU_POINT_DE_VENTE)


def _toucher_la_tuile(page, uuid_du_produit):
    page.locator(f'[data-testid="article-{uuid_du_produit}"]').click()


def _ouvrir_la_popup_des_tarifs(page, uuid_du_produit):
    """Touche la tuile, puis attend la fin de l'animation d'apparition de la boite.
    Pendant l'animation (« pop », overlay.css), Playwright juge la cible d'un clic
    masquee : il fait alors defiler les conteneurs pour reessayer, dont la grille
    #products. Un doigt ne fait jamais defiler la grille en touchant une tuile.
    / Waits for the box's entrance animation: during it Playwright sees click targets
      as covered and scrolls containers (the grid included) to retry.
    """
    _toucher_la_tuile(page, uuid_du_produit)
    expect(page.locator("#tarif-overlay")).to_be_visible()
    page.wait_for_function(
        """() => document.querySelector('.tarif-overlay-content')
            .getAnimations().every(animation => animation.playState === 'finished')"""
    )


def _quantite_au_panier(page, identifiant_de_ligne):
    """Quantite d'une ligne dans #addition-form (0 si absente).
    / Quantity of a line in #addition-form (0 if missing)."""
    return page.evaluate(
        """identifiant => {
            const champ = document.querySelector(`#addition-form [name="repid-${identifiant}"]`)
            return champ ? Number(champ.value) : 0
        }""",
        identifiant_de_ligne,
    )


# ------------------------------------------------------------------ #
#  1. Popup des tarifs : mise en page / Rate popup: layout
# ------------------------------------------------------------------ #


def _la_page_ne_deborde_pas(page):
    """Ni barre de defilement horizontale ni verticale sur la page.
    / No horizontal nor vertical scrollbar on the page."""
    dimensions = page.evaluate(
        """() => ({
            largeur_utile: document.documentElement.clientWidth,
            largeur_contenu: document.documentElement.scrollWidth,
            hauteur_utile: document.documentElement.clientHeight,
            hauteur_contenu: document.documentElement.scrollHeight,
            largeur_ecran: window.innerWidth,
        })"""
    )
    assert dimensions["largeur_contenu"] == dimensions["largeur_utile"], dimensions
    assert dimensions["hauteur_contenu"] == dimensions["hauteur_utile"], dimensions
    assert dimensions["largeur_utile"] == dimensions["largeur_ecran"], dimensions


def test_telephone_portrait_le_voile_va_du_bandeau_au_panier_replie(
    page, pos_page, caisse_de_test, erreurs_de_la_page
):
    """Telephone 360 x 640 : le voile couvre categories et articles, sur toute la
    largeur, du bas du VRAI bandeau jusqu'au haut du VRAI panier replie.
    / 360x640 phone: the veil spans the full width, from the real header to the real
      folded cart."""
    _ouvrir_la_caisse(page, pos_page, 360, 640)
    _ouvrir_la_popup_des_tarifs(page, caisse_de_test["pression"])

    voile = _boite(page, "#tarif-overlay")
    bandeau = _boite(page, ".header-background")
    panier = _boite(page, "#addition")
    categories = _boite(page, "#categories")

    _la_page_ne_deborde_pas(page)
    assert voile["gauche"] == 0
    assert voile["droite"] == 360
    assert voile["haut"] == bandeau["bas"]
    assert voile["bas"] == panier["haut"]
    assert voile["gauche"] <= categories["gauche"]


def test_telephone_paysage_la_popup_passe_en_plein_ecran(
    page, pos_page, caisse_de_test, erreurs_de_la_page
):
    """Telephone en paysage (640 x 360) : la zone au-dessus du panier est trop basse,
    la popup couvre tout l'ecran.
    / Landscape phone: the popup covers the whole screen."""
    _ouvrir_la_caisse(page, pos_page, 640, 360)
    _ouvrir_la_popup_des_tarifs(page, caisse_de_test["pression"])

    voile = _boite(page, "#tarif-overlay")
    boite = _boite(page, ".tarif-overlay-content")

    _la_page_ne_deborde_pas(page)
    assert voile == {"haut": 0, "bas": 360, "gauche": 0, "droite": 640}
    assert boite["haut"] >= voile["haut"]
    assert boite["bas"] <= voile["bas"]


def test_telephone_le_pave_prix_libre_reste_dans_le_voile_et_defile(
    page, pos_page, caisse_de_test, erreurs_de_la_page
):
    """Pave du prix libre ouvert sur un telephone : la boite est plus haute que la
    zone. Elle reste dans le voile et defile a l'interieur.
    / Free price keypad on a phone: the box stays inside the veil and scrolls."""
    _ouvrir_la_caisse(page, pos_page, 360, 640)
    _ouvrir_la_popup_des_tarifs(page, caisse_de_test["pression"])
    page.locator(f'[data-testid="tarif-libre-ouvrir-{caisse_de_test["soutien"]}"]').click()

    voile = _boite(page, "#tarif-overlay")
    boite = _boite(page, ".tarif-overlay-content")
    assert boite["haut"] >= voile["haut"]
    assert boite["bas"] <= voile["bas"]
    le_contenu_defile = page.eval_on_selector(
        ".tarif-overlay-content", "element => element.scrollHeight > element.clientHeight"
    )
    assert le_contenu_defile


def test_grand_ecran_le_voile_couvre_la_grille_et_laisse_le_panier_visible(
    page, pos_page, caisse_de_test, erreurs_de_la_page
):
    """Grand ecran peu haut (1280 x 600), pave du prix libre ouvert : le voile couvre
    exactement la grille des articles, le panier reste visible, la boite ne deborde pas.
    / Short large screen, keypad open: the veil covers exactly the article grid, the
      cart stays visible, the box does not overflow."""
    _ouvrir_la_caisse(page, pos_page, 1280, 600)
    _ouvrir_la_popup_des_tarifs(page, caisse_de_test["pression"])
    page.locator(f'[data-testid="tarif-libre-ouvrir-{caisse_de_test["soutien"]}"]').click()

    voile = _boite(page, "#tarif-overlay")
    grille = _boite(page, "#products")
    panier = _boite(page, "#addition")
    boite = _boite(page, ".tarif-overlay-content")

    _la_page_ne_deborde_pas(page)
    assert voile == grille
    assert voile["droite"] <= panier["gauche"]
    assert boite["haut"] >= voile["haut"]
    assert boite["bas"] <= voile["bas"]


# ------------------------------------------------------------------ #
#  2. Garde de stock au clic / Stock guard on click
# ------------------------------------------------------------------ #


@pytest.fixture
def stock_du_cidre(django_shell, caisse_de_test):
    """Remet le cidre a STOCK_DU_CIDRE bouteilles, vente hors stock interdite.
    / Resets the cider to STOCK_DU_CIDRE bottles, out-of-stock sale forbidden."""
    django_shell(
        "from BaseBillet.models import Product\n"
        "from inventaire.models import Stock\n"
        f"cidre = Product.objects.get(uuid='{caisse_de_test['cidre']}')\n"
        "Stock.objects.update_or_create(product=cidre, defaults={"
        f"'quantite': {STOCK_DU_CIDRE}, 'autoriser_vente_hors_stock': False,"
        " 'seuil_alerte': None})\n"
    )
    return STOCK_DU_CIDRE


def test_le_clic_de_trop_sur_un_stock_bloquant_est_refuse_tout_de_suite(
    page, pos_page, caisse_de_test, stock_du_cidre, erreurs_de_la_page
):
    """Stock de 2 cidres, vente hors stock interdite : 2 clics passent, le 3e est
    refuse au clic, avec la vraie popup de message du serveur.
    / 2 ciders in stock, out-of-stock sale forbidden: the 3rd click is refused at once,
      with the server's real message popup."""
    _ouvrir_la_caisse(page, pos_page, 1280, 800)
    uuid_du_cidre = caisse_de_test["cidre"]

    _toucher_la_tuile(page, uuid_du_cidre)
    _toucher_la_tuile(page, uuid_du_cidre)
    expect(page.locator(f"#addition-line-{uuid_du_cidre}")).to_be_visible()
    assert _quantite_au_panier(page, uuid_du_cidre) == stock_du_cidre

    with page.expect_response("**/laboutik/paiement/stock_insuffisant/**") as reponse:
        _toucher_la_tuile(page, uuid_du_cidre)
    assert reponse.value.status == 200

    popup_de_refus = page.locator('#messages [data-testid="alerte-messages"]')
    expect(popup_de_refus).to_be_visible()
    expect(popup_de_refus).to_contain_text("Cidre E2E")
    assert _quantite_au_panier(page, uuid_du_cidre) == stock_du_cidre


# ------------------------------------------------------------------ #
#  3. Le client d'une vente ne passe pas a la suivante
#     / A sale's client does not leak into the next sale
# ------------------------------------------------------------------ #


def _toucher_le_billet(page):
    page.locator(
        '[data-testid^="billetterie-tuile-"]', has_text=NOM_DE_L_EVENEMENT
    ).first.click()


def _valider_le_panier(page):
    bouton_valider = page.locator('[data-testid="addition-valider"]')
    expect(bouton_valider).to_be_enabled()
    bouton_valider.click()


def _scanner_une_carte_client(page, tag_id):
    """Identification par carte : « Scanner une carte TiBillet », puis le lecteur
    simule du mode demo (saisie du tag, validee par Entree).
    / Card identification through the demo mode's simulated reader."""
    page.locator('[data-testid="client-choose-nfc"]').click()
    page.locator(".nfc-toggle-simu .touch").click()
    saisie_du_tag = page.locator("#nfc-simu-manual-input")
    saisie_du_tag.fill(tag_id)
    saisie_du_tag.press("Enter")


def _reservations_d_alice_pour_l_evenement(django_shell, uuid_de_l_evenement):
    sortie = django_shell(
        "from BaseBillet.models import Reservation\n"
        f"print('NB=' + str(Reservation.objects.filter(event__uuid='{uuid_de_l_evenement}',"
        f" user_commande__email='{EMAIL_D_ALICE}').count()))"
    )
    return int(sortie.split("NB=")[-1])


@pytest.mark.billetterie
def test_apres_la_vente_a_alice_une_carte_anonyme_ne_reprend_pas_alice(
    page, pos_page, caisse_de_test, django_shell, erreurs_de_la_page
):
    """Vente d'un billet a Alice (carte liee), payee en especes. « Nouvelle vente ».
    Billet suivant, carte ANONYME : la caisse demande qui est le client. Elle ne
    reprend pas Alice.
    / Ticket sold to Alice (linked card), cash. "New sale". Next ticket with an
      ANONYMOUS card: the POS asks who the client is, it does not reuse Alice."""
    reservations_avant = _reservations_d_alice_pour_l_evenement(
        django_shell, caisse_de_test["evenement"]
    )
    _ouvrir_la_caisse(page, pos_page, 1280, 800)

    # --- Vente 1 : billet pour Alice, en especes / Sale 1: Alice's ticket, cash ---
    _toucher_le_billet(page)
    _valider_le_panier(page)
    _scanner_une_carte_client(page, TAG_DE_LA_CARTE_D_ALICE)
    recapitulatif = page.locator('[data-testid="client-recapitulatif-user"]')
    expect(recapitulatif).to_contain_text(EMAIL_D_ALICE)
    page.locator('[data-testid="paiement-btn-especes"]').click()
    page.locator('[data-testid="paiement-btn-valider"]').click()
    succes = page.locator('[data-testid="paiement-succes"]')
    expect(succes).to_be_visible()
    assert (
        _reservations_d_alice_pour_l_evenement(django_shell, caisse_de_test["evenement"])
        == reservations_avant + 1
    )
    succes.locator("#bt-retour-layer1").click()
    expect(succes).to_have_count(0)

    # --- Vente 2 : billet, carte anonyme / Sale 2: ticket, anonymous card ---
    _toucher_le_billet(page)
    _valider_le_panier(page)
    _scanner_une_carte_client(page, TAG_DE_LA_CARTE_ANONYME)

    # La caisse demande le client, avec un email vide. Pas de recapitulatif d'Alice.
    # / The POS asks for the client, with an empty email. No recap for Alice.
    expect(page.locator('[data-testid="client-form"]')).to_be_visible()
    expect(page.locator('[data-testid="client-input-email"]')).to_have_value("")
    expect(page.locator('[data-testid="client-recapitulatif"]')).to_have_count(0)
    expect(page.locator("#messages")).not_to_contain_text(EMAIL_D_ALICE)


# ------------------------------------------------------------------ #
#  4. VALIDER grise pendant la requete / VALIDER disabled during the request
# ------------------------------------------------------------------ #


def test_valider_est_grise_pendant_la_vraie_requete_puis_reactive(
    page, pos_page, caisse_de_test, erreurs_de_la_page
):
    """Clic VALIDER : le bouton est grise tant que le serveur n'a pas repondu (un
    double appui ne part pas), puis reactive. La console ne signale aucun selecteur
    introuvable (hx-disabled-elt).
    / VALIDER is disabled until the server answers, then re-enabled; no
      "returned no matches" console error."""
    _ouvrir_la_caisse(page, pos_page, 1280, 800)
    _toucher_la_tuile(page, caisse_de_test["sirop"])

    # La requete part vers le vrai serveur, mais Playwright la retient le temps de
    # regarder le bouton.
    # / The request goes to the real server, held by Playwright while we look.
    requetes_retenues = []
    page.route(
        "**/laboutik/paiement/moyens_paiement/**",
        lambda route: requetes_retenues.append(route),
    )
    bouton_valider = page.locator('[data-testid="addition-valider"]')
    _valider_le_panier(page)

    expect(bouton_valider).to_be_disabled()
    for _attente in range(50):
        if requetes_retenues:
            break
        page.wait_for_timeout(100)
    assert len(requetes_retenues) == 1

    requetes_retenues[0].continue_()
    page.unroute("**/laboutik/paiement/moyens_paiement/**")

    expect(page.locator('[data-testid="paiement-moyens"]')).to_be_visible()
    expect(bouton_valider).to_be_enabled()
    erreurs_de_selecteur = [
        texte for texte in erreurs_de_la_page["console"] if "returned no matches" in texte
    ]
    assert erreurs_de_selecteur == []
