"""
Panier : les réponses au formulaire personnalisé sont validées et rangées comme dans le
parcours sans panier (build_custom_form_from_request).
/ Cart: custom form answers are validated and stored like the direct flow.

LOCALISATION : tests/pytest/test_panier_formulaire_personnalise.py

Code testé / Tested code : BaseBillet/views.py
- reponses_du_formulaire_personnalise_pour_le_panier()
- PanierMVT.add_tickets_batch, PanierMVT.add_membership

Avant : le panier recopiait le formulaire tel quel, sous la clé technique du champ,
sans validation. L'export des billets ne retrouvait pas ces réponses.
/ Before: the cart copied raw values under the field key, without validation.

Chaque test est marqué `django_db` : pytest-django l'exécute dans une transaction annulée.
/ Every test runs in a rolled-back transaction.

Lancer / Run : make test ARGS="tests/pytest/test_panier_formulaire_personnalise.py"
"""

import json
from types import SimpleNamespace

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db

EN_TETE_HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, avec Stripe (catalogue) et Celery simulés pendant tout le test.
    / The `lespass` venue, with the Stripe catalogue and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees():
                yield SimpleNamespace(tenant=tenant)


def ajouter_une_question(produit, label, field_type="ST", required=False, options=None):
    """Ajoute une question au formulaire personnalisé du produit.
    / Adds a question to the product's custom form."""
    from BaseBillet.models import ProductFormField

    return ProductFormField.objects.create(
        product=produit, label=label, field_type=field_type,
        required=required, options=options,
    )


def niveau_du_toast(reponse):
    """Le niveau du toast envoyé par `HX-Trigger`, ou None.
    / The level of the toast sent through `HX-Trigger`, or None."""
    en_tete = reponse.get("HX-Trigger")
    if not en_tete:
        return None
    return json.loads(en_tete)["panierToast"]["level"]


def reponses_du_premier_item(client):
    """Les réponses au formulaire rangées sur le premier item du panier.
    / The form answers stored on the first cart item."""
    items = client.session.get("panier", {}).get("items", [])
    return items[0]["custom_form"]


def ajouter_un_billet(client, billetterie, champs_du_formulaire):
    """POST d'un billet vers le panier, avec les réponses données.
    / POSTs one ticket to the cart, with the given answers."""
    donnees = {"event": str(billetterie.evenement.uuid), str(billetterie.tarif.uuid): "1"}
    donnees.update(champs_du_formulaire)
    return client.post("/panier/add/tickets_batch/", donnees, **EN_TETE_HTMX)


# --------------------------------------------------------------------------
# Billets / Tickets
# --------------------------------------------------------------------------


def test_la_reponse_est_rangee_sous_le_libelle_de_la_question(lieu):
    """Même clé que le parcours direct : le libellé, pas la clé technique.
    / Same key as the direct flow: the label, not the field key."""
    client = client_connecte(creer_utilisateur())
    billetterie = creer_evenement_avec_tarif(prix="10.00")
    question = ajouter_une_question(billetterie.produit, "Quel atelier ?")

    reponse = ajouter_un_billet(client, billetterie, {f"form__{question.name}": "Soudure"})

    assert niveau_du_toast(reponse) == "success"
    assert reponses_du_premier_item(client) == {"Quel atelier ?": "Soudure"}


def test_une_question_obligatoire_sans_reponse_est_refusee(lieu):
    """Question obligatoire vide : le billet n'est pas ajouté, le message nomme la question.
    / Empty required question: ticket not added, the message names the question."""
    client = client_connecte(creer_utilisateur())
    billetterie = creer_evenement_avec_tarif(prix="10.00")
    ajouter_une_question(billetterie.produit, "Votre téléphone ?", required=True)

    reponse = ajouter_un_billet(client, billetterie, {})

    assert niveau_du_toast(reponse) == "error"
    message = json.loads(reponse["HX-Trigger"])["panierToast"]["text"]
    assert "Votre téléphone ?" in message
    assert client.session.get("panier", {}).get("items", []) == []


def test_un_choix_multiple_garde_toutes_les_valeurs_cochees(lieu):
    """Avant, seule la dernière valeur cochée était gardée.
    / Before, only the last ticked value was kept."""
    client = client_connecte(creer_utilisateur())
    billetterie = creer_evenement_avec_tarif(prix="10.00")
    question = ajouter_une_question(
        billetterie.produit, "Ateliers ?", field_type="MS", options=["Soudure", "Couture", "Bois"],
    )

    ajouter_un_billet(client, billetterie, {f"form__{question.name}": ["Soudure", "Bois"]})

    assert reponses_du_premier_item(client) == {"Ateliers ?": ["Soudure", "Bois"]}


def test_une_case_a_cocher_est_rangee_en_oui_non(lieu):
    """Une case cochée devient True, pas le texte « on ».
    / A ticked box becomes True, not the text "on"."""
    client = client_connecte(creer_utilisateur())
    billetterie = creer_evenement_avec_tarif(prix="10.00")
    question = ajouter_une_question(billetterie.produit, "Bénévole ?", field_type="BL")

    ajouter_un_billet(client, billetterie, {f"form__{question.name}": "on"})

    assert reponses_du_premier_item(client) == {"Bénévole ?": True}


def test_la_question_obligatoire_d_un_produit_non_choisi_ne_bloque_pas(lieu):
    """Seules les questions des produits dont un billet est demandé sont lues.
    / Only questions of products with a requested ticket are read."""
    from BaseBillet.models import Product

    client = client_connecte(creer_utilisateur())
    billetterie = creer_evenement_avec_tarif(prix="10.00")
    autre_billetterie = creer_evenement_avec_tarif(prix="5.00")
    ajouter_une_question(autre_billetterie.produit, "Question d'un autre produit", required=True)
    billetterie.evenement.products.add(Product.objects.get(pk=autre_billetterie.produit.pk))

    reponse = ajouter_un_billet(client, billetterie, {})

    assert niveau_du_toast(reponse) == "success"


# --------------------------------------------------------------------------
# Adhésion / Membership
# --------------------------------------------------------------------------


def test_adhesion_la_reponse_est_rangee_sous_le_libelle(lieu):
    """Adhésion au panier : réponse rangée sous le libellé de la question.
    / Membership in the cart: answer stored under the question label."""
    client = client_connecte(creer_utilisateur())
    adhesion = creer_adhesion(prix="15.00")
    question = ajouter_une_question(adhesion.produit, "Pseudo ?")

    reponse = client.post(
        "/panier/add/membership/",
        {
            "price": str(adhesion.tarif.uuid),
            "firstname": "Ada",
            "lastname": "Lovelace",
            f"form__{question.name}": "ada42",
        },
        **EN_TETE_HTMX,
    )

    assert niveau_du_toast(reponse) == "success"
    assert reponses_du_premier_item(client) == {"Pseudo ?": "ada42"}


def test_adhesion_question_obligatoire_sans_reponse_est_refusee(lieu):
    """Adhésion au panier : question obligatoire vide, rien n'est ajouté.
    / Membership in the cart: empty required question, nothing added."""
    client = client_connecte(creer_utilisateur())
    adhesion = creer_adhesion(prix="15.00")
    ajouter_une_question(adhesion.produit, "Pseudo ?", required=True)

    reponse = client.post(
        "/panier/add/membership/",
        {"price": str(adhesion.tarif.uuid), "firstname": "Ada", "lastname": "Lovelace"},
        **EN_TETE_HTMX,
    )

    assert niveau_du_toast(reponse) == "error"
    assert client.session.get("panier", {}).get("items", []) == []
