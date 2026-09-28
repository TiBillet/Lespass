"""
tests/e2e/test_tarif_popup.py — Popup de choix du tarif de la caisse (tarif.js).
/ POS rate selection popup (tarif.js).

LOCALISATION : tests/e2e/test_tarif_popup.py

CE QUI EST TESTE :
laboutik/static/js/tarif.js construit la popup en JavaScript quand on touche
un article a plusieurs tarifs. On teste ici son comportement dans un vrai
navigateur : tarif fixe, prix libre (tuile + pave numerique), poids / mesure,
fermeture, garde de stock, echappement du HTML.

PAS BESOIN DU SERVEUR :
Ces tests n'utilisent ni Traefik ni la base. Ils montent une page minimale :
- le vrai CSS (palette, overlay, numpad, tarif) ;
- les vrais modeles <template> du pave, rendus par le composant serveur
  cotton/numpad.html (comme dans cotton/articles.html) ;
- les vrais scripts tibilletUtils.js et tarif.js.
Chaque ajout au panier emet 'organizerMsg' sur #event-organizer : on
l'enregistre dans window.ajouts_au_panier pour le verifier.
/ No server needed: a minimal page with the real CSS, the real keypad
templates (server component) and the real scripts. Cart additions are recorded.

LANCEMENT / RUN :
    docker exec lespass_django poetry run pytest tests/e2e/test_tarif_popup.py -v
"""

import os

import pytest
from django.conf import settings
from django.template import engines
from django_cotton.compiler_regex import CottonCompiler


# ------------------------------------------------------------------ #
#  Page de test / Test page
# ------------------------------------------------------------------ #

DOSSIER_LABOUTIK = os.path.join(settings.BASE_DIR, "laboutik")


def _lire_fichier_statique(chemin_relatif):
    """Lit un fichier de laboutik/static. / Reads a laboutik/static file."""
    chemin_complet = os.path.join(DOSSIER_LABOUTIK, "static", chemin_relatif)
    with open(chemin_complet, encoding="utf-8") as fichier:
        return fichier.read()


def _rendre_composant_cotton(source_du_composant):
    """
    Rend un tag cotton comme le ferait un gabarit (<c-numpad ... />).
    / Renders a cotton tag the way a template would.
    """
    source_compilee = CottonCompiler().process(source_du_composant)
    return engines["django"].from_string(source_compilee).render({})


def _construire_page_de_la_caisse():
    """
    Construit le HTML minimal : CSS, zones de la caisse, modeles du pave.
    Les modeles sont les memes que dans cotton/articles.html.
    / Builds the minimal HTML: CSS, POS zones, keypad templates.
    """
    feuilles_de_style = ""
    for nom_du_fichier in ["palette.css", "modele00.css", "overlay.css", "numpad.css", "tarif.css"]:
        feuilles_de_style += "<style>" + _lire_fichier_statique("css/" + nom_du_fichier) + "</style>"

    pave_poids = _rendre_composant_cotton(
        '<c-numpad id="tarif-pave-modele" effacer="retour" virgule="non" />'
    )
    pave_montant = _rendre_composant_cotton(
        '<c-numpad id="tarif-pave-montant-modele" effacer="retour" />'
    )

    return (
        feuilles_de_style
        + '<body style="margin:0">'
        + '<div id="event-organizer"></div>'
        + '<form id="addition-form"></form>'
        + '<div id="products" style="height:900px;width:834px"><p id="grille-articles">grille</p></div>'
        + '<template id="tarif-modele-pave">' + pave_poids + "</template>"
        + '<template id="tarif-modele-pave-montant">' + pave_montant + "</template>"
        + "</body>"
    )


# Tarifs d'exemple : deux fixes, un prix libre, un au poids.
# / Sample rates: two fixed, one free price, one by weight.
TARIF_DEMI = {"price_uuid": "DEMI", "name": "Demi", "prix_centimes": 400}
TARIF_PINTE = {"price_uuid": "PINTE", "name": "Pinte", "prix_centimes": 700}
TARIF_SOUTIEN = {"price_uuid": "SOUTIEN", "name": "Soutien", "prix_centimes": 200, "free_price": True}
TARIF_POIDS = {
    "price_uuid": "POIDS",
    "name": "Au poids",
    "prix_centimes": 2400,
    "poids_mesure": True,
    "unite_saisie_label": "g",
    "prix_reference_label": "/kg",
}


@pytest.fixture
def caisse(page):
    """
    Page de caisse minimale avec tarif.js charge.
    Renvoie une fonction ouvrir(tarifs, nom) qui ouvre la popup.
    / Minimal POS page with tarif.js loaded. Returns an open(rates, name) helper.
    """
    erreurs_javascript = []
    page.on("pageerror", lambda erreur: erreurs_javascript.append(str(erreur)))
    page.set_viewport_size({"width": 834, "height": 900})
    page.set_content(_construire_page_de_la_caisse())
    page.add_script_tag(content=_lire_fichier_statique("js/tibilletUtils.js"))
    page.add_script_tag(content=_lire_fichier_statique("js/tarif.js"))

    # Enregistre chaque ajout au panier, et fait ce que fait addition.js :
    # un champ repid-<ligne> dans #addition-form, ou tarif.js relit la quantite.
    # / Records each cart addition and, like addition.js, keeps a repid-<line>
    #   field in #addition-form (tarif.js reads the quantity from it).
    page.evaluate("""() => {
        window.ajouts_au_panier = []
        document.querySelector('#event-organizer').addEventListener('organizerMsg', (event) => {
            const ajout = event.detail.data
            window.ajouts_au_panier.push(ajout)
            const formulaire = document.querySelector('#addition-form')
            let champ = formulaire.querySelector(`[name="repid-${ajout.lineId}"]`)
            if (!champ) {
                champ = document.createElement('input')
                champ.name = 'repid-' + ajout.lineId
                formulaire.appendChild(champ)
            }
            champ.value = ajout.quantity
        })
    }""")

    def ouvrir(tarifs, nom_du_produit="IPA pression"):
        page.evaluate(
            """([tarifs, nom]) => tarifSelection({detail: {
                uuid: 'PRODUIT', name: nom, currency: '€', tarifs: tarifs}})""",
            [tarifs, nom_du_produit],
        )

    yield ouvrir

    assert erreurs_javascript == [], f"Erreurs JavaScript : {erreurs_javascript}"


def _ajouts(page):
    return page.evaluate("window.ajouts_au_panier")


def _toucher(page, touches, zone):
    """Appuie sur des touches du pave d'une zone. / Presses keypad keys in a zone."""
    for touche in touches:
        page.click(f'{zone} .numpad-touch[data-key="{touche}"]')


# ------------------------------------------------------------------ #
#  Tarif fixe / Fixed rate
# ------------------------------------------------------------------ #

def test_tarif_fixe_ajoute_au_panier_et_la_popup_reste_ouverte(page, caisse):
    """Deux touches sur « Pinte » : meme ligne, quantite 1 puis 2, popup toujours ouverte.
    / Two taps on "Pinte": same line, quantity 1 then 2, popup still open."""
    caisse([TARIF_DEMI, TARIF_PINTE])

    page.click('[data-testid="tarif-btn-PINTE"]')
    page.click('[data-testid="tarif-btn-PINTE"]')

    ajouts = _ajouts(page)
    assert [ajout["quantity"] for ajout in ajouts] == [1, 2]
    assert ajouts[0]["lineId"] == ajouts[1]["lineId"] == "PRODUIT--PINTE"
    assert ajouts[1]["price"] == 700
    assert page.locator('[data-testid="tarif-overlay"]').count() == 1


def test_tarif_fixe_affiche_le_prix_avec_une_virgule(page, caisse):
    """Le prix du tarif s'affiche « 4,00 € ». / Price shown as "4,00 €"."""
    caisse([TARIF_DEMI])

    texte_du_bouton = page.inner_text('[data-testid="tarif-btn-DEMI"]')
    assert "4,00 €" in texte_du_bouton


# ------------------------------------------------------------------ #
#  Fermeture / Closing
# ------------------------------------------------------------------ #

def test_la_croix_ferme_la_popup_et_restaure_la_grille(page, caisse):
    """La croix remet la grille d'articles. / The cross restores the article grid."""
    caisse([TARIF_DEMI, TARIF_PINTE])

    page.click('[data-testid="tarif-btn-retour"]')

    assert page.locator('[data-testid="tarif-overlay"]').count() == 0
    assert page.locator("#grille-articles").count() == 1


def test_toucher_le_voile_ferme_la_popup(page, caisse):
    """Toucher la grille voilee ferme la popup. / Tapping the veil closes the popup."""
    caisse([TARIF_DEMI, TARIF_PINTE])

    page.click("#tarif-overlay", position={"x": 5, "y": 5})

    assert page.locator('[data-testid="tarif-overlay"]').count() == 0


def test_toucher_la_boite_ne_ferme_pas_la_popup(page, caisse):
    """Toucher le titre (dans la boite) ne ferme rien. / Tapping inside the box keeps it open."""
    caisse([TARIF_DEMI, TARIF_PINTE])

    page.click(".tarif-overlay-title")

    assert page.locator('[data-testid="tarif-overlay"]').count() == 1


# ------------------------------------------------------------------ #
#  La grille reste dans la page / The grid stays in the page
# ------------------------------------------------------------------ #

def test_la_grille_reste_dans_la_page_et_devient_inerte_pendant_la_popup(page, caisse):
    """
    La popup s'ajoute par-dessus la grille : les tuiles restent dans le DOM
    (mises a jour de stock, badges), mais inertes sous le voile.
    / The popup is appended over the grid: tiles stay in the DOM, but inert.
    """
    caisse([TARIF_DEMI, TARIF_PINTE])

    assert page.locator("#grille-articles").count() == 1
    assert page.evaluate("document.querySelector('#grille-articles').inert") is True


def test_la_fermeture_rend_la_grille_active(page, caisse):
    caisse([TARIF_DEMI, TARIF_PINTE])

    page.click('[data-testid="tarif-btn-retour"]')

    assert page.evaluate("document.querySelector('#grille-articles').inert") is False
    classes_de_la_grille = page.evaluate("document.querySelector('#products').className")
    assert "tarif-popup-ouverte" not in classes_de_la_grille


def test_le_badge_de_la_tuile_compte_les_ajouts_faits_depuis_la_popup(page, caisse):
    """
    Avant, la popup remplacait la grille : la tuile n'existait plus et son
    badge de quantite restait a 0. Maintenant il compte chaque ajout.
    / Before, the popup replaced the grid and the tile badge stayed at 0.
    """
    page.evaluate("""() => {
        const badge = document.createElement('span')
        badge.id = 'article-quantity-number-PRODUIT'
        badge.innerText = '0'
        document.querySelector('#grille-articles').appendChild(badge)
        // afficherBadgeQuantite() vit dans articles.js (non charge ici)
        // / afficherBadgeQuantite() lives in articles.js (not loaded here)
        window.afficherBadgeQuantite = () => {}
    }""")
    caisse([TARIF_DEMI, TARIF_PINTE])

    page.click('[data-testid="tarif-btn-PINTE"]')
    page.click('[data-testid="tarif-btn-DEMI"]')

    assert page.inner_text("#article-quantity-number-PRODUIT") == "2"


# ------------------------------------------------------------------ #
#  Prix libre / Free price
# ------------------------------------------------------------------ #

ZONE_PRIX_LIBRE = "#tarif-libre-SOUTIEN"


def test_prix_libre_le_pave_est_replie_au_depart(page, caisse):
    """Au depart : la tuile est visible, le pave est cache. / Tile shown, keypad hidden."""
    caisse([TARIF_SOUTIEN])

    assert page.is_visible('[data-testid="tarif-libre-ouvrir-SOUTIEN"]')
    assert page.is_hidden(ZONE_PRIX_LIBRE)


def test_prix_libre_toucher_la_tuile_ouvre_le_pave(page, caisse):
    """La tuile laisse place au pave, le focus va sur la premiere touche.
    / The tile gives way to the keypad; focus on the first key."""
    caisse([TARIF_SOUTIEN])

    page.click('[data-testid="tarif-libre-ouvrir-SOUTIEN"]')

    assert page.is_visible(ZONE_PRIX_LIBRE)
    assert page.is_hidden('[data-testid="tarif-libre-ouvrir-SOUTIEN"]')
    assert page.evaluate("document.activeElement.dataset.key") == "1"


def test_prix_libre_le_pave_a_une_virgule(page, caisse):
    """Le pave du prix libre a la touche virgule. / The free price keypad has a comma key."""
    caisse([TARIF_SOUTIEN])

    touches = page.eval_on_selector_all(
        ZONE_PRIX_LIBRE + " .numpad-touch", "els => els.map(e => e.dataset.key)"
    )
    assert "." in touches
    assert "Backspace" in touches


def test_prix_libre_ajouter_desactive_tant_que_rien_n_est_tape(page, caisse):
    """« Ajouter » est grise sans saisie. / "Add" is disabled while empty."""
    caisse([TARIF_SOUTIEN])
    page.click('[data-testid="tarif-libre-ouvrir-SOUTIEN"]')

    assert page.is_disabled('[data-testid="tarif-free-validate-SOUTIEN"]')


def test_prix_libre_sous_le_minimum_est_refuse(page, caisse):
    """1,50 € pour un minimum de 2,00 € : message, montant en rouge, rien au panier.
    / Below the minimum: message, red amount, nothing added."""
    caisse([TARIF_SOUTIEN])
    page.click('[data-testid="tarif-libre-ouvrir-SOUTIEN"]')
    _toucher(page, ["1", ".", "5"], ZONE_PRIX_LIBRE)

    page.click('[data-testid="tarif-free-validate-SOUTIEN"]')

    assert "Minimum : 2,00 €" in page.inner_text(ZONE_PRIX_LIBRE + " .card-montant-erreur")
    assert "is-invalide" in page.get_attribute(ZONE_PRIX_LIBRE + " .card-keypad-val", "class")
    assert _ajouts(page) == []


def test_prix_libre_ajoute_le_montant_saisi_puis_replie_le_pave(page, caisse):
    """3,50 € : ajout au panier en centimes, puis la tuile revient.
    / 3.50 €: added in cents, then the tile comes back."""
    caisse([TARIF_SOUTIEN])
    page.click('[data-testid="tarif-libre-ouvrir-SOUTIEN"]')
    _toucher(page, ["3", ".", "5", "0"], ZONE_PRIX_LIBRE)

    assert "3,50 €" in page.inner_text('[data-testid="tarif-free-validate-SOUTIEN"]')
    page.click('[data-testid="tarif-free-validate-SOUTIEN"]')

    ajouts = _ajouts(page)
    assert len(ajouts) == 1
    assert ajouts[0]["price"] == 350
    assert ajouts[0]["customAmount"] == 350
    assert page.is_hidden(ZONE_PRIX_LIBRE)
    assert page.is_visible('[data-testid="tarif-libre-ouvrir-SOUTIEN"]')


def test_prix_libre_chaque_saisie_cree_une_nouvelle_ligne(page, caisse):
    """Deux prix libres = deux lignes distinctes. / Two free prices = two separate lines."""
    caisse([TARIF_SOUTIEN])
    for touches in (["3"], ["5"]):
        page.click('[data-testid="tarif-libre-ouvrir-SOUTIEN"]')
        _toucher(page, touches, ZONE_PRIX_LIBRE)
        page.click('[data-testid="tarif-free-validate-SOUTIEN"]')

    identifiants_de_ligne = [ajout["lineId"] for ajout in _ajouts(page)]
    assert len(set(identifiants_de_ligne)) == 2


def test_prix_libre_troisieme_decimale_refusee(page, caisse):
    """1,234 donne 1,23 (regle commune montantAppliquerTouche). / 1.234 gives 1.23."""
    caisse([TARIF_SOUTIEN])
    page.click('[data-testid="tarif-libre-ouvrir-SOUTIEN"]')
    _toucher(page, ["1", ".", "2", "3", "4"], ZONE_PRIX_LIBRE)

    assert page.inner_text(ZONE_PRIX_LIBRE + " .card-keypad-saisie") == "1,23"


def test_prix_libre_la_croix_du_pave_efface_et_replie(page, caisse):
    """La croix du pave efface la saisie et remontre la tuile.
    / The keypad cross clears the entry and shows the tile again."""
    caisse([TARIF_SOUTIEN])
    page.click('[data-testid="tarif-libre-ouvrir-SOUTIEN"]')
    _toucher(page, ["8"], ZONE_PRIX_LIBRE)

    page.click(ZONE_PRIX_LIBRE + " .tarif-libre-fermer")
    page.click('[data-testid="tarif-libre-ouvrir-SOUTIEN"]')

    assert page.inner_text(ZONE_PRIX_LIBRE + " .card-keypad-saisie") == "0"


# ------------------------------------------------------------------ #
#  Poids / mesure / Weight / measure
# ------------------------------------------------------------------ #

ZONE_POIDS = "#tarif-numpad-POIDS"


def test_poids_le_pave_n_a_pas_de_virgule(page, caisse):
    """Saisie en grammes entiers : pas de touche virgule, une case vide.
    / Whole grams: no comma key, an empty cell."""
    caisse([TARIF_POIDS])

    touches = page.eval_on_selector_all(ZONE_POIDS + " .numpad-touch", "els => els.map(e => e.dataset.key)")
    assert "." not in touches
    assert page.locator(ZONE_POIDS + " .numpad-vide").count() == 1


def test_poids_ajouter_desactive_a_zero(page, caisse):
    """« Ajouter » est grise tant que la quantite vaut 0. / "Add" disabled at 0."""
    caisse([TARIF_POIDS])

    assert page.is_disabled('[data-testid="tarif-numpad-ok-POIDS"]')


def test_poids_la_touche_retour_efface_un_chiffre(page, caisse):
    """3500 puis ⌫ donne 350. / 3500 then backspace gives 350."""
    caisse([TARIF_POIDS])
    _toucher(page, ["3", "5", "0", "0", "Backspace"], ZONE_POIDS)

    assert page.inner_text("#tarif-numpad-value-POIDS") == "350"


def test_poids_calcule_le_prix_et_ajoute_la_quantite(page, caisse):
    """350 g a 24 €/kg = 8,40 € ; la ligne porte la quantite et l'unite.
    / 350 g at 24 €/kg = 8.40 €; the line carries quantity and unit."""
    caisse([TARIF_POIDS], nom_du_produit="Comte")
    _toucher(page, ["3", "5", "0"], ZONE_POIDS)

    assert "= 8,40 €" in page.inner_text("#tarif-numpad-total-POIDS")
    page.click('[data-testid="tarif-numpad-ok-POIDS"]')

    ajout = _ajouts(page)[0]
    assert ajout["price"] == 840
    assert ajout["weightAmount"] == 350
    assert ajout["weightUnit"] == "g"
    assert ajout["name"] == "Comte (Au poids 350g)"
    assert page.inner_text("#tarif-numpad-value-POIDS") == "0"


def test_poids_cinq_chiffres_au_plus(page, caisse):
    """99999 g au plus : le sixieme chiffre est ignore. / 5 digits max."""
    caisse([TARIF_POIDS])
    _toucher(page, ["1", "2", "3", "4", "5", "6"], ZONE_POIDS)

    assert page.inner_text("#tarif-numpad-value-POIDS") == "12345"


def test_poids_bloque_si_le_stock_est_insuffisant(page, caisse):
    """Vente hors stock interdite, 100 g en stock, 150 g demandes : alerte, rien au panier.
    / Out-of-stock sale forbidden: alert, nothing added."""
    tarif_avec_stock = dict(TARIF_POIDS, stock_disponible=100, autoriser_hors_stock=False)
    caisse([tarif_avec_stock])
    _toucher(page, ["1", "5", "0"], ZONE_POIDS)

    page.click('[data-testid="tarif-numpad-ok-POIDS"]')

    assert page.is_visible("#tarif-numpad-alerte-POIDS")
    assert "Stock insuffisant" in page.inner_text("#tarif-numpad-alerte-POIDS")
    assert _ajouts(page) == []


# ------------------------------------------------------------------ #
#  Style et securite / Style and safety
# ------------------------------------------------------------------ #

def test_aucun_bouton_de_la_popup_n_a_de_bordure(page, caisse):
    """Aucun bouton ne garde la bordure par defaut du navigateur.
    / No button keeps the browser's default border."""
    caisse([TARIF_DEMI, TARIF_SOUTIEN, TARIF_POIDS])
    page.click('[data-testid="tarif-libre-ouvrir-SOUTIEN"]')

    boutons_avec_bordure = page.evaluate("""() =>
        [...document.querySelectorAll('#tarif-overlay button')]
            .filter(bouton => getComputedStyle(bouton).borderTopWidth !== '0px')
            .map(bouton => bouton.className)""")
    assert boutons_avec_bordure == []


def test_les_noms_sont_echappes(page, caisse):
    """Un nom de produit ou de tarif contenant du HTML s'affiche en texte.
    / HTML in product or rate names is shown as text."""
    nom_dangereux = '<img src=x onerror="window.pirate=1">'
    tarif_dangereux = dict(TARIF_DEMI, name=nom_dangereux)
    caisse([tarif_dangereux], nom_du_produit=nom_dangereux)

    assert page.locator("#tarif-overlay img").count() == 0
    assert page.evaluate("window.pirate") is None
    assert nom_dangereux in page.inner_text(".tarif-overlay-title")
