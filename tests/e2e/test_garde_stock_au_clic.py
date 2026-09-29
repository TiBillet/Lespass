"""
tests/e2e/test_garde_stock_au_clic.py — Un clic ne peut pas ajouter plus que le stock.
/ A click cannot add more than the stock.

LOCALISATION : tests/e2e/test_garde_stock_au_clic.py

LE BUG (2026-09-29) :
Stock de 2 bieres, vente hors stock interdite : un 3e clic sur la tuile ajoutait
une 3e biere au panier. Le refus n'arrivait qu'au clic VALIDER (serveur).
/ 3rd click on a 2-unit blocking stock was added; refusal only came on VALIDER.

LA CORRECTION (laboutik/static/js/articles.js) :
verifierStockAvantAjout() compte ce que le panier demande deja pour le produit
(quantite x contenance, pesees comprises) et refuse l'ajout qui depasserait le stock.
Elle lit le stock et "vente hors stock autorisee" sur le badge de la tuile, que le
WebSocket met a jour. Refus : le clic est bloque tout de suite, puis la popup
standard hx_messages.html est demandee au serveur (GET /laboutik/paiement/stock_insuffisant/).

PAS BESOIN DU SERVEUR :
la page monte les vrais composants (<c-articles />, <c-addition />, hx_messages.html)
rendus par Django, et les vrais scripts. Les articles ont la forme produite par
laboutik/views.py (_construire_donnees_articles). Playwright sert la page depuis une
origine fictive et repond a la route stock_insuffisant avec le vrai hx_messages.html :
le test verifie les parametres envoyes. Le texte du message est teste cote pytest
(test_stock_negatif.py).
/ No server: real components and scripts, article dicts shaped like the view's.

LANCEMENT / RUN :
    docker exec lespass_django poetry run pytest tests/e2e/test_garde_stock_au_clic.py -v
"""

import json
import os
from urllib.parse import parse_qs, urlparse

import pytest
from django.conf import settings
from django.template import engines
from django_cotton.compiler_regex import CottonCompiler


DOSSIER_JS = os.path.join(settings.BASE_DIR, "laboutik", "static", "js")


def _lire_script(nom_du_fichier):
    with open(os.path.join(DOSSIER_JS, nom_du_fichier), encoding="utf-8") as fichier:
        return fichier.read()


def _rendre(source_cotton, contexte):
    """Rend un bout de template cotton. / Renders a cotton template snippet."""
    source_compilee = CottonCompiler().process(source_cotton)
    return engines["django"].from_string(source_compilee).render(contexte)


CATEGORIE = {"id": "CAT", "name": "Bar", "icon": "", "icone_type": ""}


def _article_a_l_unite(stock, autoriser_hors_stock):
    """Biere a la piece (contenance 1). / Beer sold per unit."""
    return {
        "id": "BIERE",
        "name": "Biere",
        "prix": 300,
        "contenance": 1,
        "categorie": CATEGORIE,
        "multi_tarif": False,
        "est_adhesion": False,
        "tarifs_json": "[]",
        "a_poids_mesure": False,
        "methode_caisse": "VT",
        "stock_quantite": stock,
        "stock_autoriser_hors_stock": autoriser_hors_stock,
        "stock_bloquant": stock <= 0 and not autoriser_hors_stock,
        "stock_en_alerte": False,
        "stock_en_rupture": stock <= 0,
        "stock_quantite_lisible": str(stock),
    }


def _article_multi_tarif_en_cl(stock_cl):
    """Fut de 100 cl, tarif Pinte = 50 cl, vente hors stock interdite.
    / 100 cl keg, Pint rate = 50 cl, out-of-stock sale forbidden."""
    tarifs = [
        {"price_uuid": "DEMI", "name": "Demi", "prix_centimes": 300, "contenance": 25},
        {
            "price_uuid": "PINTE",
            "name": "Pinte",
            "prix_centimes": 550,
            "contenance": 50,
        },
    ]
    return {
        "id": "FUT",
        "name": "IPA",
        "prix": 300,
        "contenance": 25,
        "categorie": CATEGORIE,
        "multi_tarif": True,
        "tarifs": tarifs,
        "est_adhesion": False,
        "tarifs_json": json.dumps(tarifs),
        "a_poids_mesure": False,
        "methode_caisse": "VT",
        "stock_quantite": stock_cl,
        "stock_autoriser_hors_stock": False,
        "stock_bloquant": False,
        "stock_en_alerte": False,
        "stock_en_rupture": False,
        "stock_quantite_lisible": f"{stock_cl} cl",
    }


ORIGINE_FICTIVE = "http://caisse.test"


@pytest.fixture
def caisse(page):
    """
    Renvoie ouvrir(articles) : monte la grille, le panier et #messages,
    puis les vrais scripts (leurs ecouteurs DOMContentLoaded se branchent).
    Les demandes de message stock sont notees dans page.demandes_stock.
    / Returns open(articles). Stock message requests are recorded in page.demandes_stock.
    """
    erreurs_javascript = []
    page.on("pageerror", lambda erreur: erreurs_javascript.append(str(erreur)))
    page.demandes_stock = []

    popup_de_refus = _rendre(
        '{% include "laboutik/partial/hx_messages.html" %}',
        {"msg_type": "warning", "msg_content": "Biere : stock insuffisant."},
    )

    def repondre_message_stock(route):
        # Note les parametres envoyes par articles.js, repond la vraie popup
        # / Records the parameters sent by articles.js, answers the real popup
        parametres = parse_qs(urlparse(route.request.url).query)
        page.demandes_stock.append(
            {cle: valeurs[0] for cle, valeurs in parametres.items()}
        )
        route.fulfill(status=200, content_type="text/html", body=popup_de_refus)

    def ouvrir(articles):
        contexte = {
            "pv": {"id": "PV-TEST", "comportement": "D", "articles": articles},
            "card": {"tag_id": "CARTE-PRIMAIRE", "name": "Caissier"},
            "currency_data": {"symbol": "€"},
            "hostname_client": "",
        }
        html = (
            "<html><body>"
            '<div id="event-organizer"></div>'
            + _rendre("<c-articles />", contexte)
            + _rendre("<c-addition />", contexte)
            + '<div id="messages" aria-live="polite"></div>'
            + "<script>"
            + _lire_script("htmx@2.0.6.min.js")
            + "</script>"
            + "<script>"
            + _lire_script("tibilletUtils.js")
            + "</script>"
            + "<script>"
            + _lire_script("addition.js")
            + "</script>"
            + "<script>"
            + _lire_script("articles.js")
            + "</script>"
            + "<script>"
            + _lire_script("tarif.js")
            + "</script>"
            + "</body></html>"
        )
        page.route(
            ORIGINE_FICTIVE + "/laboutik/paiement/stock_insuffisant/**",
            repondre_message_stock,
        )
        page.route(
            ORIGINE_FICTIVE + "/",
            lambda route: route.fulfill(
                status=200, content_type="text/html", body=html
            ),
        )
        page.goto(ORIGINE_FICTIVE + "/")

    yield ouvrir

    assert erreurs_javascript == [], f"Erreurs JavaScript : {erreurs_javascript}"


def _cliquer_la_tuile(page, uuid):
    """
    Clic sur un enfant direct de la tuile, comme un doigt :
    manageKey() lit event.target.parentNode.
    / Click a direct child of the tile: manageKey() reads event.target.parentNode.
    """
    page.evaluate(
        "uuid => document.querySelector(`[data-uuid='${uuid}'] .article-name-layer`).click()",
        uuid,
    )


def _quantite_au_panier(page, nom_de_ligne):
    return page.evaluate(
        """nom => {
            const champ = document.querySelector(`#addition-form [name="repid-${nom}"]`)
            return champ ? Number(champ.value) : 0
        }""",
        nom_de_ligne,
    )


def _attendre_la_popup_de_refus(page):
    """La popup standard hx_messages.html arrive dans #messages.
    / The standard hx_messages.html popup lands in #messages."""
    page.wait_for_selector('#messages [data-testid="alerte-messages"]')


def _popup_de_refus_presente(page):
    return page.locator('#messages [data-testid="alerte-messages"]').count() > 0


def test_le_clic_de_trop_est_refuse_quand_la_vente_hors_stock_est_interdite(
    page, caisse
):
    """Stock 2, interdit : 2 clics passent, le 3e est refuse avec un message.
    / Stock 2, forbidden: 2 clicks pass, the 3rd is refused with a message."""
    caisse([_article_a_l_unite(stock=2, autoriser_hors_stock=False)])

    _cliquer_la_tuile(page, "BIERE")
    _cliquer_la_tuile(page, "BIERE")
    assert _quantite_au_panier(page, "BIERE") == 2
    assert page.demandes_stock == []

    _cliquer_la_tuile(page, "BIERE")
    _attendre_la_popup_de_refus(page)

    assert _quantite_au_panier(page, "BIERE") == 2
    # Le serveur recoit : ce qui est DEJA au panier (2) et ce que le clic ajoutait (1)
    # / The server gets what is ALREADY in the cart (2) and what the click added (1)
    assert page.demandes_stock == [
        {"product_uuid": "BIERE", "quantite_au_panier": "2", "quantite_a_ajouter": "1"}
    ]


def test_le_clic_passe_quand_la_vente_hors_stock_est_autorisee(page, caisse):
    """Stock 2, autorise : un 3e clic passe, pas de message.
    / Stock 2, allowed: a 3rd click passes, no message."""
    caisse([_article_a_l_unite(stock=2, autoriser_hors_stock=True)])

    for _numero_de_clic in range(3):
        _cliquer_la_tuile(page, "BIERE")

    assert _quantite_au_panier(page, "BIERE") == 3
    assert page.demandes_stock == []
    assert not _popup_de_refus_presente(page)


def test_la_garde_suit_le_stock_mis_a_jour_par_le_websocket(page, caisse):
    """Stock 1 : le 2e clic est refuse. Le WebSocket annonce 5 (reception) : il passe.
    / Stock 1: 2nd click refused. WebSocket announces 5: it passes."""
    caisse([_article_a_l_unite(stock=1, autoriser_hors_stock=False)])
    _cliquer_la_tuile(page, "BIERE")
    _cliquer_la_tuile(page, "BIERE")
    assert _quantite_au_panier(page, "BIERE") == 1

    # Meme attribut que hx_stock_badge.html apres une reception
    # / Same attribute as hx_stock_badge.html after a reception
    page.evaluate(
        "() => { document.querySelector('#stock-badge-BIERE').dataset.stockQuantite = '5' }"
    )
    _attendre_la_popup_de_refus(page)
    page.click('[data-testid="alerte-messages-retour"]')
    _cliquer_la_tuile(page, "BIERE")

    assert _quantite_au_panier(page, "BIERE") == 2


def test_un_tarif_de_la_popup_compte_sa_contenance(page, caisse):
    """Fut 100 cl, Pinte = 50 cl : 2 pintes passent, la 3e est refusee.
    / 100 cl keg, Pint = 50 cl: 2 pints pass, the 3rd is refused."""
    caisse([_article_multi_tarif_en_cl(stock_cl=100)])
    _cliquer_la_tuile(page, "FUT")

    page.click('[data-testid="tarif-btn-PINTE"]')
    page.click('[data-testid="tarif-btn-PINTE"]')
    assert _quantite_au_panier(page, "FUT--PINTE") == 2

    page.click('[data-testid="tarif-btn-PINTE"]')
    _attendre_la_popup_de_refus(page)

    assert _quantite_au_panier(page, "FUT--PINTE") == 2
    # 2 pintes = 100 cl deja au panier, la 3e ajoutait 50 cl
    # / 2 pints = 100 cl already in the cart, the 3rd added 50 cl
    assert page.demandes_stock == [
        {"product_uuid": "FUT", "quantite_au_panier": "100", "quantite_a_ajouter": "50"}
    ]


def test_les_tarifs_differents_du_meme_produit_sont_additionnes(page, caisse):
    """Fut 100 cl : 1 pinte (50) + 2 demis (25+25) = 100 cl, un 3e demi est refuse.
    / 100 cl keg: 1 pint + 2 halves = 100 cl, a 3rd half is refused."""
    caisse([_article_multi_tarif_en_cl(stock_cl=100)])
    _cliquer_la_tuile(page, "FUT")

    page.click('[data-testid="tarif-btn-PINTE"]')
    page.click('[data-testid="tarif-btn-DEMI"]')
    page.click('[data-testid="tarif-btn-DEMI"]')
    assert _quantite_au_panier(page, "FUT--DEMI") == 2

    page.click('[data-testid="tarif-btn-DEMI"]')
    _attendre_la_popup_de_refus(page)

    assert _quantite_au_panier(page, "FUT--DEMI") == 2
    assert page.demandes_stock[0]["quantite_au_panier"] == "100"
    assert page.demandes_stock[0]["quantite_a_ajouter"] == "25"
