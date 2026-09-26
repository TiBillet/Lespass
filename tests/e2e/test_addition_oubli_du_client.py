"""
tests/e2e/test_addition_oubli_du_client.py — Le client d'une vente ne passe pas a la suivante.
/ A sale's client does not leak into the next sale.

LOCALISATION : tests/e2e/test_addition_oubli_du_client.py

LE BUG (2026-09-25) :
Vente d'un billet avec une carte liee a une personne : OK. Juste apres, vente d'un billet
avec une carte ANONYME : la personne precedente reapparaissait et recevait les billets.
Cause : l'email, le prenom, le nom et la carte lue restaient dans #addition-form apres la
vente. Avec une carte anonyme, le serveur n'a pas de proprietaire de carte : il se rabat
sur l'email du formulaire (identifier_client, _creer_billets), donc l'email perime.
/ Stale client fields in #addition-form made an anonymous card reuse the previous client.

LA CORRECTION (laboutik/static/js/addition.js) :
additionOublierLeClient() efface ces champs :
- a la remise a zero du panier (additionReset, « Nouvelle vente ») ;
- au debut de chaque identification (hx_display_type_payment.html, action 'oublierLeClient').

PAS BESOIN DU SERVEUR :
la page monte le vrai composant cotton/addition.html (rendu par Django) et les vrais
scripts tibilletUtils.js et addition.js. Les champs du client sont ajoutes exactement
comme le fait hx_display_type_payment.html (message 'additionManageForm', createAndPopInput).
/ No server: real addition component, real scripts, same messages as the templates.

LANCEMENT / RUN :
    docker exec lespass_django poetry run pytest tests/e2e/test_addition_oubli_du_client.py -v
"""

import os

import pytest
from django.conf import settings
from django.template import engines
from django_cotton.compiler_regex import CottonCompiler


DOSSIER_JS = os.path.join(settings.BASE_DIR, "laboutik", "static", "js")


def _lire_script(nom_du_fichier):
    with open(os.path.join(DOSSIER_JS, nom_du_fichier), encoding="utf-8") as fichier:
        return fichier.read()


def _rendre_le_panier():
    """
    Rend le vrai composant <c-addition /> avec un contexte minimal.
    / Renders the real <c-addition /> component with a minimal context.
    """
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
    Page avec #event-organizer, le panier, htmx et les scripts inclus AVANT la fin du
    chargement : leurs ecouteurs DOMContentLoaded se branchent comme en vrai.
    / Page with the cart and the scripts inlined so DOMContentLoaded listeners attach.
    """
    erreurs_javascript = []
    page.on("pageerror", lambda erreur: erreurs_javascript.append(str(erreur)))
    html = (
        "<html><body>"
        '<div id="event-organizer"></div>'
        + _rendre_le_panier()
        + "<script>" + _lire_script("htmx@2.0.6.min.js") + "</script>"
        + "<script>" + _lire_script("tibilletUtils.js") + "</script>"
        + "<script>" + _lire_script("addition.js") + "</script>"
        + "</body></html>"
    )
    page.set_content(html)
    yield page
    assert erreurs_javascript == [], f"Erreurs JavaScript : {erreurs_javascript}"


def _ranger_le_client(page, email, prenom, nom, tag_id):
    """
    Range un client dans #addition-form, comme hx_display_type_payment.html
    (mode client_identifie) apres le scan d'une carte liee a une personne.
    / Stores a client in #addition-form, like the identified-client payment screen.
    """
    page.evaluate(
        """([email, prenom, nom, tagId]) => {
            const champs = {email_adhesion: email, prenom_adhesion: prenom, nom_adhesion: nom, tag_id: tagId}
            for (const [nom, valeur] of Object.entries(champs)) {
                sendEventOrganizer({
                    src: {file: 'test', method: 'rangerLeClient'},
                    msg: 'additionManageForm',
                    data: {actionType: 'createAndPopInput', name: nom, value: valeur},
                })
            }
        }""",
        [email, prenom, nom, tag_id],
    )


def _valeur(page, nom_du_champ):
    """Valeur d'un champ de #addition-form, ou None s'il n'existe pas.
    / Value of an #addition-form field, or None if missing."""
    return page.evaluate(
        """(nom) => {
            const champ = document.querySelector(`#addition-form [name="${nom}"]`)
            return champ ? champ.value : null
        }""",
        nom_du_champ,
    )


def test_le_client_est_bien_range_dans_le_formulaire(caisse):
    """Point de depart : apres identification, le client est dans #addition-form.
    / Starting point: after identification the client is in #addition-form."""
    _ranger_le_client(caisse, "alice@exemple.org", "Alice", "Martin", "CARTEALICE")

    assert _valeur(caisse, "email_adhesion") == "alice@exemple.org"
    assert _valeur(caisse, "tag_id") == "CARTEALICE"


def test_nouvelle_vente_oublie_le_client_precedent(caisse):
    """« Nouvelle vente » (resetArticles) efface email, prenom, nom et carte lue.
    C'est le scenario du bug : sans ca, la carte anonyme suivante reprenait Alice.
    / "New sale" clears the previous client: the bug scenario."""
    _ranger_le_client(caisse, "alice@exemple.org", "Alice", "Martin", "CARTEALICE")

    caisse.evaluate("""() => sendEventOrganizer({
        src: {file: 'test', method: 'nouvelleVente'}, msg: 'resetArticles', data: {}})""")

    assert _valeur(caisse, "email_adhesion") is None
    assert _valeur(caisse, "prenom_adhesion") is None
    assert _valeur(caisse, "nom_adhesion") is None
    assert _valeur(caisse, "tag_id") == ""


def test_nouvelle_vente_oublie_le_contexte_du_panier(caisse):
    """La remise a zero retire aussi les drapeaux du panier (billets, adhesions...).
    / Reset also removes the cart flags."""
    caisse.evaluate("""() => {
        for (const nom of ['panier_a_billets', 'panier_a_adhesions', 'panier_a_recharges', 'moyens_paiement']) {
            sendEventOrganizer({src: {file: 'test', method: 'contexte'}, msg: 'additionManageForm',
                data: {actionType: 'createAndPopInput', name: nom, value: 'True'}})
        }
        sendEventOrganizer({src: {file: 'test', method: 'nouvelleVente'}, msg: 'resetArticles', data: {}})
    }""")

    for nom_du_champ in ["panier_a_billets", "panier_a_adhesions", "panier_a_recharges", "moyens_paiement"]:
        assert _valeur(caisse, nom_du_champ) is None, nom_du_champ


def test_nouvelle_vente_garde_les_champs_permanents(caisse):
    """Le point de vente et la carte du caissier restent : ils servent a toutes les ventes.
    / The POS and the cashier's card stay: every sale needs them."""
    _ranger_le_client(caisse, "alice@exemple.org", "Alice", "Martin", "CARTEALICE")

    caisse.evaluate("""() => sendEventOrganizer({
        src: {file: 'test', method: 'nouvelleVente'}, msg: 'resetArticles', data: {}})""")

    assert _valeur(caisse, "uuid_pv") == "PV-TEST"
    assert _valeur(caisse, "tag_id_cm") == "CARTE-PRIMAIRE"


def test_debut_d_identification_oublie_le_client_precedent(caisse):
    """Une identification abandonnee (popup fermee) ne passe pas par la remise a zero :
    le debut de l'identification suivante efface quand meme le client precedent.
    / An abandoned identification skips the reset: the next one still clears the client."""
    _ranger_le_client(caisse, "alice@exemple.org", "Alice", "Martin", "CARTEALICE")

    # Ce que fait hx_display_type_payment.html au debut d'une identification
    # / What the payment screen does when an identification starts
    caisse.evaluate("""() => sendEventOrganizer({
        src: {file: 'test', method: 'debutIdentification'}, msg: 'additionManageForm',
        data: {actionType: 'oublierLeClient'}})""")

    assert _valeur(caisse, "email_adhesion") is None
    assert _valeur(caisse, "tag_id") == ""


def test_le_client_suivant_n_est_pas_melange_avec_le_precedent(caisse):
    """Alice (carte liee), nouvelle vente, puis Bob saisi par email : seul Bob reste.
    / Alice, new sale, then Bob by email: only Bob remains."""
    _ranger_le_client(caisse, "alice@exemple.org", "Alice", "Martin", "CARTEALICE")
    caisse.evaluate("""() => sendEventOrganizer({
        src: {file: 'test', method: 'nouvelleVente'}, msg: 'resetArticles', data: {}})""")

    _ranger_le_client(caisse, "bob@exemple.org", "Bob", "Durand", "")

    assert _valeur(caisse, "email_adhesion") == "bob@exemple.org"
    assert _valeur(caisse, "prenom_adhesion") == "Bob"
    assert _valeur(caisse, "tag_id") == ""
