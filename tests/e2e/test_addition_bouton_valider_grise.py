"""
tests/e2e/test_addition_bouton_valider_grise.py — Le clic VALIDER ne signale plus de selecteur introuvable.
/ Clicking VALIDER no longer logs a missing selector.

LOCALISATION : tests/e2e/test_addition_bouton_valider_grise.py

LE BUG (2026-09-29) : au clic sur VALIDER, la console affichait
'The selector "#bt-valider-layer2" on hx-disabled-elt returned no matches!'.
#addition-form sert a toutes les etapes du paiement. Au clic VALIDER du pied de page
(POST moyens_paiement), le bouton #bt-valider-layer2 n'existe pas encore : il n'apparait
qu'avec la popup de confirmation (hx_confirm_payment.html).
/ #addition-form serves every payment step; #bt-valider-layer2 only exists later.

LA CORRECTION (cotton/addition.html) : hx-disabled-elt="#bt-valider-layer2, #bt-valider".
htmx ne signale une erreur que si AUCUN element n'est trouve. En plus, le VALIDER du pied
de page est grise pendant la requete (views.css : #bt-valider[disabled]).

PAS BESOIN DU SERVEUR : vrai composant <c-addition />, vrai htmx. Playwright sert la page
depuis une origine fictive et fait attendre la reponse de moyens_paiement.
/ No server: real component and htmx; Playwright holds the moyens_paiement response.

LANCEMENT / RUN :
    docker exec lespass_django poetry run pytest tests/e2e/test_addition_bouton_valider_grise.py -v
"""

import os

import pytest
from django.conf import settings
from django.template import engines
from django_cotton.compiler_regex import CottonCompiler


DOSSIER_JS = os.path.join(settings.BASE_DIR, "laboutik", "static", "js")
ORIGINE_FICTIVE = "http://caisse.test"


def _lire_script(nom_du_fichier):
    with open(os.path.join(DOSSIER_JS, nom_du_fichier), encoding="utf-8") as fichier:
        return fichier.read()


def _rendre_le_panier():
    """Rend le vrai composant <c-addition />. / Renders the real <c-addition />."""
    source_compilee = CottonCompiler().process("<c-addition />")
    contexte = {
        "pv": {"id": "PV-TEST", "comportement": "D"},
        "card": {"tag_id": "CARTE-PRIMAIRE", "name": "Caissier"},
        "currency_data": {"symbol": "€"},
        "hostname_client": "",
    }
    return engines["django"].from_string(source_compilee).render(contexte)


@pytest.fixture
def caisse(page):
    """
    Page : #bt-valider du pied de page, le panier, #messages et #confirm.
    La reponse de moyens_paiement attend que le test la libere.
    Les messages de console d'erreur sont notes dans page.erreurs_console.
    / Page with footer VALIDER, cart, #messages and #confirm. The response waits.
    """
    erreurs_javascript = []
    page.on("pageerror", lambda erreur: erreurs_javascript.append(str(erreur)))
    page.erreurs_console = []
    page.on(
        "console",
        lambda message: (
            page.erreurs_console.append(message.text)
            if message.type == "error"
            else None
        ),
    )

    html = (
        "<html><body>"
        '<div id="event-organizer"></div>'
        '<div id="bt-valider" class="footer-bt">VALIDER</div>'
        + _rendre_le_panier()
        + '<div id="messages"></div><div id="confirm"></div>'
        + "<script>"
        + _lire_script("htmx@2.0.6.min.js")
        + "</script>"
        + "<script>"
        + _lire_script("tibilletUtils.js")
        + "</script>"
        + "<script>"
        + _lire_script("addition.js")
        + "</script>"
        + "</body></html>"
    )

    reponses_en_attente = []

    def retenir_la_reponse(route):
        reponses_en_attente.append(route)

    page.route(
        ORIGINE_FICTIVE + "/laboutik/paiement/moyens_paiement/", retenir_la_reponse
    )
    page.route(
        ORIGINE_FICTIVE + "/",
        lambda route: route.fulfill(status=200, content_type="text/html", body=html),
    )
    page.goto(ORIGINE_FICTIVE + "/")
    page.reponses_en_attente = reponses_en_attente

    yield page

    assert erreurs_javascript == [], f"Erreurs JavaScript : {erreurs_javascript}"


def test_valider_ne_signale_plus_de_selecteur_introuvable(caisse):
    """Envoi du formulaire au clic VALIDER : aucune erreur "returned no matches".
    / Submitting on VALIDER: no "returned no matches" error."""
    page = caisse
    page.evaluate("() => htmx.trigger('#addition-form', 'validerPaiement')")
    page.wait_for_function(
        "() => document.querySelector('#bt-valider').hasAttribute('disabled')"
    )

    erreurs_de_selecteur = [
        texte for texte in page.erreurs_console if "returned no matches" in texte
    ]
    assert erreurs_de_selecteur == []


def test_valider_est_grise_pendant_la_requete_puis_reactive(caisse):
    """VALIDER porte disabled pendant la requete, et le perd a la reponse.
    / VALIDER is disabled while the request runs, then re-enabled."""
    page = caisse
    page.evaluate("() => htmx.trigger('#addition-form', 'validerPaiement')")
    page.wait_for_function(
        "() => document.querySelector('#bt-valider').hasAttribute('disabled')"
    )

    page.wait_for_function("n => n > 0", arg=len(page.reponses_en_attente))
    page.reponses_en_attente[0].fulfill(
        status=200, content_type="text/html", body='<div id="messages">ok</div>'
    )

    page.wait_for_function(
        "() => !document.querySelector('#bt-valider').hasAttribute('disabled')"
    )
