"""
Tests des vues du panier (`PanierMVT`) : droits, réponses HTMX, ajout, retrait, paiement.
/ Cart view tests (`PanierMVT`): permissions, HTMX responses, add, remove, checkout.

LOCALISATION : tests/pytest/test_panier_mvt.py

Code testé / Tested code : PanierMVT dans BaseBillet/views.py, gabarits
BaseBillet/templates/htmx/components/panier_*.html.

Les vues répondent en HTMX :
- un toast passe par l'en-tête `HX-Trigger` : {"panierToast": {"level": ..., "text": ...}} ;
- une redirection passe par l'en-tête `HX-Redirect` (statut 200).
Les tests vérifient le NIVEAU du toast et l'état du panier ou de la base, pas le texte
traduit.
/ Views answer in HTMX: toasts in `HX-Trigger`, redirects in `HX-Redirect`. Tests check the
toast LEVEL and the cart / DB state, not the translated text.

Chaque test est marqué `django_db` : transaction annulée à la fin, rien ne reste en base.
Lancer / Run : make test ARGS="tests/pytest/test_panier_mvt.py"
"""

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.conf import settings
from django_tenants.utils import tenant_context

from fabriques_panier import (
    ajouter_un_tarif,
    catalogue_stripe_simule,
    client_connecte,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    identifiant_unique,
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
def lieu(tenant, mock_stripe):
    """
    Le lieu `lespass`, avec Stripe (session + catalogue) et Celery simulés pendant tout le test.
    / The `lespass` venue, with Stripe (session + catalogue) and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule() as catalogue_stripe:
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    stripe=mock_stripe,
                    catalogue_stripe=catalogue_stripe,
                    taches_demandees=taches_demandees,
                )


def niveau_du_toast(reponse):
    """Le niveau du toast envoyé par `HX-Trigger` ('success', 'error'…), ou None.
    / The level of the toast sent through `HX-Trigger`, or None."""
    en_tete = reponse.get("HX-Trigger")
    if not en_tete:
        return None
    return json.loads(en_tete)["panierToast"]["level"]


def items_du_panier(client):
    """Les items du panier rangés dans la session du client.
    / The cart items stored in the client's session."""
    return client.session.get("panier", {}).get("items", [])


def ajouter_des_billets(client, evenement, quantites_par_tarif, **champs_en_plus):
    """POST du formulaire de l'événement vers « Ajouter au panier ».
    / POST of the event form to "Add to cart"."""
    donnees_du_formulaire = {"event": str(evenement.uuid)}
    for tarif, quantite in quantites_par_tarif.items():
        donnees_du_formulaire[str(tarif.uuid)] = str(quantite)
    donnees_du_formulaire.update(champs_en_plus)
    return client.post(
        "/panier/add/tickets_batch/", donnees_du_formulaire, **EN_TETE_HTMX
    )


# --------------------------------------------------------------------------
# Droits d'accès
# / Access rights
# --------------------------------------------------------------------------


def test_la_page_panier_est_accessible_sans_etre_connecte(lieu):
    """`GET /panier/` : page rendue pour un visiteur anonyme (le gabarit l'invite à se connecter).
    / `GET /panier/`: page rendered for an anonymous visitor."""
    reponse = client_connecte().get("/panier/")

    assert reponse.status_code == 200
    assert b'id="panier-content"' in reponse.content


def test_le_badge_du_panier_est_accessible_sans_etre_connecte(lieu):
    """`GET /panier/badge/` : le badge est rendu pour un visiteur anonyme.
    / `GET /panier/badge/`: the badge is rendered for an anonymous visitor."""
    reponse = client_connecte().get("/panier/badge/")

    assert reponse.status_code == 200
    assert b"panier-badge" in reponse.content


@pytest.mark.parametrize(
    "adresse",
    [
        "/panier/add/tickets_batch/",
        "/panier/add/membership/",
        "/panier/add/resource/",
        "/panier/0/remove/",
        "/panier/clear/",
        "/panier/checkout/",
    ],
)
def test_les_ecritures_du_panier_sont_refusees_a_un_visiteur_anonyme(lieu, adresse):
    """Toute écriture dans le panier exige d'être connecté : 403 pour un anonyme.
    / Every cart write requires login: 403 for an anonymous visitor."""
    reponse = client_connecte().post(adresse, {}, **EN_TETE_HTMX)

    assert reponse.status_code == 403


def test_les_ecritures_du_panier_sont_refusees_a_un_compte_non_active(lieu):
    """Un compte non activé (email non vérifié) ne peut pas remplir de panier : 403.
    / A non-activated account cannot fill a cart: 403."""
    concert = creer_evenement_avec_tarif(prix="10.00")
    client = client_connecte(creer_utilisateur(actif=False))

    reponse = ajouter_des_billets(client, concert.evenement, {concert.tarif: 1})

    assert reponse.status_code == 403
    assert items_du_panier(client) == []


# --------------------------------------------------------------------------
# Ajout de billets (formulaire de l'événement)
# / Adding tickets (event form)
# --------------------------------------------------------------------------


def test_ajouter_plusieurs_tarifs_d_un_coup(lieu):
    """Deux tarifs du même événement ajoutés d'un coup : deux items, toast de succès.
    / Two prices of the same event added at once: two items, success toast."""
    client = client_connecte(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00")
    tarif_reduit = ajouter_un_tarif(concert.produit, prix="5.00")

    reponse = ajouter_des_billets(
        client, concert.evenement, {concert.tarif: 2, tarif_reduit: 1}
    )

    assert niveau_du_toast(reponse) == "success"
    quantites_par_tarif = {
        item["price_uuid"]: item["qty"] for item in items_du_panier(client)
    }
    assert quantites_par_tarif == {
        str(concert.tarif.uuid): 2,
        str(tarif_reduit.uuid): 1,
    }


def test_ajouter_des_billets_accepte_aussi_le_slug_de_l_evenement(lieu):
    """L'ancien formulaire envoie le slug de l'événement au lieu de son uuid : accepté.
    / The legacy form sends the event slug instead of its uuid: accepted."""
    client = client_connecte(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00")

    reponse = client.post(
        "/panier/add/tickets_batch/",
        {"slug": concert.evenement.slug, str(concert.tarif.uuid): "1"},
        **EN_TETE_HTMX,
    )

    assert niveau_du_toast(reponse) == "success"
    assert len(items_du_panier(client)) == 1


def test_un_code_promo_inconnu_est_refuse_avec_son_propre_message(lieu):
    """Code promo qui n'existe pas : toast d'erreur qui le dit (« code invalide »), pas un
    message sur les produits choisis ; rien n'est ajouté.
    / Unknown promo code: an error toast saying so, nothing added."""
    client = client_connecte(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00")

    reponse = ajouter_des_billets(
        client,
        concert.evenement,
        {concert.tarif: 1},
        promotional_code="TEST_panier_CODE_QUI_N_EXISTE_PAS",
    )

    toast = json.loads(reponse["HX-Trigger"])["panierToast"]
    assert toast["level"] == "error"
    assert toast["text"] == "Invalid or inactive promotional code."
    assert items_du_panier(client) == []


def test_ajouter_des_billets_d_un_evenement_inconnu_affiche_une_erreur(lieu):
    """Événement introuvable : toast d'erreur, panier vide.
    / Unknown event: error toast, empty cart."""
    client = client_connecte(creer_utilisateur())

    reponse = client.post(
        "/panier/add/tickets_batch/",
        {"slug": "evenement-qui-n-existe-pas"},
        **EN_TETE_HTMX,
    )

    assert niveau_du_toast(reponse) == "error"
    assert items_du_panier(client) == []


def test_ajouter_sans_aucune_quantite_affiche_une_erreur(lieu):
    """Toutes les quantités à zéro : toast d'erreur, panier vide.
    / All quantities at zero: error toast, empty cart."""
    client = client_connecte(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00")

    reponse = ajouter_des_billets(client, concert.evenement, {concert.tarif: 0})

    assert niveau_du_toast(reponse) == "error"
    assert items_du_panier(client) == []


def test_un_tarif_invalide_annule_tout_l_ajout(lieu):
    """Un tarif valide et un tarif non publié envoyés ensemble : rien n'est ajouté.
    / A valid price and an unpublished one sent together: nothing is added."""
    client = client_connecte(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00")
    tarif_non_publie = ajouter_un_tarif(concert.produit, prix="5.00", nom="Caché")
    tarif_non_publie.publish = False
    tarif_non_publie.save()

    reponse = ajouter_des_billets(
        client, concert.evenement, {concert.tarif: 1, tarif_non_publie: 1}
    )

    assert niveau_du_toast(reponse) == "error"
    assert items_du_panier(client) == []


@pytest.mark.parametrize(
    "quantite_trafiquee",
    ["abc", "Infinity", "NaN", "1e1000000", "-1e1000000", "10000", "-3"],
)
def test_une_quantite_trafiquee_affiche_une_erreur_sans_bloquer_le_serveur(
    lieu, quantite_trafiquee
):
    """Quantité non numérique, infinie ou démesurée (formulaire trafiqué) : toast d'erreur,
    pas d'erreur 500, réponse immédiate (« 1e1000000 » converti en entier bloquerait le
    serveur plusieurs secondes).
    / Non-numeric, infinite or huge quantity: error toast, no 500, immediate answer."""
    import time

    client = client_connecte(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00")

    debut = time.monotonic()
    reponse = ajouter_des_billets(
        client, concert.evenement, {concert.tarif: quantite_trafiquee}
    )
    duree_en_secondes = time.monotonic() - debut

    assert reponse.status_code == 200
    assert niveau_du_toast(reponse) == "error"
    assert items_du_panier(client) == []
    assert duree_en_secondes < 1


def test_le_code_promo_n_est_pose_que_sur_les_items_de_son_produit(lieu):
    """
    Un seul champ code promo pour tout l'événement : le code n'est rangé que sur les items
    du produit auquel il est lié.
    / One promo field for the whole event: the code is only stored on its product's items.
    """
    from BaseBillet.models import Product, PromotionalCode

    client = client_connecte(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00")
    produit_b = Product.objects.create(
        name=f"TEST_panier billet B {identifiant_unique()}",
        categorie_article=Product.BILLET,
    )
    concert.evenement.products.add(produit_b)
    tarif_b = ajouter_un_tarif(produit_b, prix="10.00", nom="Plein tarif B")
    code_promo = PromotionalCode.objects.create(
        name=f"TEST_panier_code_{identifiant_unique()}",
        discount_rate=Decimal("20.00"),
        product=concert.produit,
    )

    ajouter_des_billets(
        client,
        concert.evenement,
        {concert.tarif: 1, tarif_b: 1},
        promotional_code=code_promo.name,
    )

    code_par_tarif = {
        item["price_uuid"]: item["promotional_code_name"]
        for item in items_du_panier(client)
    }
    assert code_par_tarif[str(concert.tarif.uuid)] == code_promo.name
    assert code_par_tarif[str(tarif_b.uuid)] is None


def test_ajouter_et_payer_enchaine_sur_le_paiement_stripe(lieu):
    """« Ajouter au panier et payer » (`then=checkout`) : redirection vers la page Stripe.
    / "Add to cart and pay" (`then=checkout`): redirect to the Stripe page."""
    client = client_connecte(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00")

    reponse = ajouter_des_billets(
        client, concert.evenement, {concert.tarif: 1}, then="checkout"
    )

    assert reponse["HX-Redirect"] == lieu.stripe.session.url
    assert items_du_panier(client) == []


# --------------------------------------------------------------------------
# Ajout d'une adhésion (formulaire d'adhésion)
# / Adding a membership (membership form)
# --------------------------------------------------------------------------


def test_ajouter_une_adhesion_depuis_le_formulaire(lieu):
    """Le formulaire envoie le tarif dans `price` : l'adhésion arrive au panier.
    / The form sends the price in `price`: the membership lands in the cart."""
    client = client_connecte(creer_utilisateur())
    adhesion = creer_adhesion(prix="15.00")

    reponse = client.post(
        "/panier/add/membership/",
        {"price": str(adhesion.tarif.uuid), "firstname": "Ada", "lastname": "Lovelace"},
        **EN_TETE_HTMX,
    )

    assert niveau_du_toast(reponse) == "success"
    items = items_du_panier(client)
    assert items[0]["type"] == "membership"
    assert items[0]["firstname"] == "Ada"


def test_ajouter_une_adhesion_a_prix_libre_lit_le_montant_de_son_tarif(lieu):
    """Prix libre : le montant est lu dans le champ `custom_amount_<uuid du tarif>`.
    / Free price: the amount is read from `custom_amount_<price uuid>`."""
    client = client_connecte(creer_utilisateur())
    adhesion = creer_adhesion(prix="10.00", prix_libre=True)

    client.post(
        "/panier/add/membership/",
        {
            "price": str(adhesion.tarif.uuid),
            f"custom_amount_{adhesion.tarif.uuid}": "25.00",
        },
        **EN_TETE_HTMX,
    )

    assert items_du_panier(client)[0]["custom_amount"] == "25.00"


@pytest.mark.parametrize("sorte_d_adhesion", ["recurrente", "validation_manuelle"])
def test_une_adhesion_refusee_par_le_panier_affiche_une_erreur(lieu, sorte_d_adhesion):
    """Adhésion récurrente ou à validation manuelle : toast d'erreur, panier inchangé.
    / Recurring or manual-validation membership: error toast, cart unchanged."""
    client = client_connecte(creer_utilisateur())
    if sorte_d_adhesion == "recurrente":
        adhesion = creer_adhesion(prix="15.00", recurrente=True)
    else:
        adhesion = creer_adhesion(prix="15.00", validation_manuelle=True)

    reponse = client.post(
        "/panier/add/membership/", {"price": str(adhesion.tarif.uuid)}, **EN_TETE_HTMX
    )

    assert niveau_du_toast(reponse) == "error"
    assert items_du_panier(client) == []


# --------------------------------------------------------------------------
# Retrait et vidage
# / Removing and clearing
# --------------------------------------------------------------------------


def test_retirer_un_item_du_panier(lieu):
    """`POST /panier/0/remove/` retire le premier item et renvoie le contenu du panier.
    / `POST /panier/0/remove/` removes the first item and returns the cart content."""
    client = client_connecte(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00")
    ajouter_des_billets(client, concert.evenement, {concert.tarif: 1})

    reponse = client.post("/panier/0/remove/", **EN_TETE_HTMX)

    assert reponse.status_code == 200
    assert b'id="panier-content"' in reponse.content
    assert items_du_panier(client) == []


def test_le_bouton_retirer_vise_le_bon_item_quand_un_item_a_disparu(lieu):
    """
    Deux items ; le tarif du premier est supprimé entre-temps (il n'est plus affiché).
    Le bouton « retirer » du seul item affiché doit retirer CET item, pas le premier.
    / Two items; the first one's price is deleted meanwhile (no longer displayed). The
    remove button of the only displayed item must remove THAT item, not the first one.
    """
    client = client_connecte(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00", jours_avant_l_evenement=7)
    spectacle = creer_evenement_avec_tarif(prix="8.00", jours_avant_l_evenement=9)
    ajouter_des_billets(client, concert.evenement, {concert.tarif: 1})
    ajouter_des_billets(client, spectacle.evenement, {spectacle.tarif: 1})
    uuid_du_tarif_supprime = str(concert.tarif.uuid)
    concert.tarif.delete()

    page_du_panier = client.get("/panier/").content.decode()
    assert page_du_panier.count('data-testid="panier-item-remove"') == 1
    assert 'action="/panier/1/remove/"' in page_du_panier
    client.post("/panier/1/remove/", **EN_TETE_HTMX)

    tarifs_restants = [item["price_uuid"] for item in items_du_panier(client)]
    assert tarifs_restants == [uuid_du_tarif_supprime]


def test_vider_le_panier(lieu):
    """`POST /panier/clear/` vide tout le panier.
    / `POST /panier/clear/` empties the whole cart."""
    client = client_connecte(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00")
    ajouter_des_billets(client, concert.evenement, {concert.tarif: 3})

    reponse = client.post("/panier/clear/", **EN_TETE_HTMX)

    assert reponse.status_code == 200
    assert items_du_panier(client) == []


# --------------------------------------------------------------------------
# Paiement (checkout)
# / Checkout
# --------------------------------------------------------------------------


def test_payer_un_panier_vide_affiche_une_erreur(lieu):
    """Panier vide : toast d'erreur, aucune Commande.
    / Empty cart: error toast, no Order."""
    from BaseBillet.models import Commande

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)

    reponse = client.post("/panier/checkout/", **EN_TETE_HTMX)

    assert niveau_du_toast(reponse) == "error"
    assert not Commande.objects.filter(user=acheteur).exists()


def test_payer_un_panier_gratuit_redirige_vers_mes_reservations_et_vide_le_panier(lieu):
    """Panier gratuit : Commande payée, redirection vers « mes réservations », panier vidé.
    / Free cart: Order paid, redirect to "my reservations", cart emptied."""
    from BaseBillet.models import Commande, Product

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    atelier = creer_evenement_avec_tarif(categorie=Product.FREERES)
    ajouter_des_billets(client, atelier.evenement, {atelier.tarif: 1})

    reponse = client.post("/panier/checkout/", **EN_TETE_HTMX)

    assert reponse["HX-Redirect"] == "/my_account/my_reservations/"
    assert items_du_panier(client) == []
    assert Commande.objects.get(user=acheteur).status == Commande.PAID


def test_payer_un_panier_payant_redirige_vers_stripe(lieu):
    """Panier payant : redirection vers l'adresse de la session Stripe, panier vidé.
    / Paid cart: redirect to the Stripe session URL, cart emptied."""
    client = client_connecte(creer_utilisateur())
    concert = creer_evenement_avec_tarif(prix="10.00")
    ajouter_des_billets(client, concert.evenement, {concert.tarif: 1})

    reponse = client.post("/panier/checkout/", **EN_TETE_HTMX)

    assert reponse["HX-Redirect"] == lieu.stripe.session.url
    assert items_du_panier(client) == []


def test_payer_deux_fois_ne_cree_qu_une_seule_commande(lieu):
    """Double clic ou deuxième onglet : le deuxième paiement trouve un panier vide.
    / Double click or second tab: the second checkout finds an empty cart."""
    from BaseBillet.models import Commande, Product

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    atelier = creer_evenement_avec_tarif(categorie=Product.FREERES)
    ajouter_des_billets(client, atelier.evenement, {atelier.tarif: 1})
    client.post("/panier/checkout/", **EN_TETE_HTMX)

    deuxieme_reponse = client.post("/panier/checkout/", **EN_TETE_HTMX)

    assert niveau_du_toast(deuxieme_reponse) == "error"
    assert Commande.objects.filter(user=acheteur).count() == 1


def test_stripe_indisponible_ne_cree_aucune_commande_et_garde_le_panier(lieu):
    """Stripe injoignable au paiement : aucune Commande, le panier reste intact, toast d'erreur.
    / Stripe unreachable at checkout: no Order, cart intact, error toast."""
    from BaseBillet.models import Commande

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")
    ajouter_des_billets(client, concert.evenement, {concert.tarif: 1})
    lieu.stripe.mock_create.side_effect = ConnectionError("Stripe injoignable (simulé)")

    reponse = client.post("/panier/checkout/", **EN_TETE_HTMX)

    assert niveau_du_toast(reponse) == "error"
    assert not Commande.objects.filter(user=acheteur).exists()
    assert len(items_du_panier(client)) == 1


def test_un_item_devenu_invalide_au_paiement_renvoie_au_panier_avec_un_message(lieu):
    """
    Un tarif dépublié entre l'ajout et le paiement : pas de Commande, retour vers `/panier/`,
    l'item invalide est retiré, l'item encore valide reste.
    / A price unpublished between add and checkout: no Order, back to `/panier/`, the invalid
    item is removed, the still-valid one stays.
    """
    from BaseBillet.models import Commande

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00", jours_avant_l_evenement=7)
    spectacle = creer_evenement_avec_tarif(prix="8.00", jours_avant_l_evenement=9)
    ajouter_des_billets(client, concert.evenement, {concert.tarif: 1})
    ajouter_des_billets(client, spectacle.evenement, {spectacle.tarif: 1})
    concert.tarif.publish = False
    concert.tarif.save()

    reponse = client.post("/panier/checkout/", **EN_TETE_HTMX)

    assert reponse["HX-Redirect"] == "/panier/"
    assert not Commande.objects.filter(user=acheteur).exists()
    tarifs_restants = [item["price_uuid"] for item in items_du_panier(client)]
    assert tarifs_restants == [str(spectacle.tarif.uuid)]


def test_un_acheteur_sans_nom_prend_celui_du_formulaire_d_adhesion(lieu):
    """Compte sans prénom ni nom : la Commande prend ceux saisis dans le formulaire d'adhésion.
    / Account without names: the Order takes the ones typed in the membership form."""
    from BaseBillet.models import Commande

    acheteur = creer_utilisateur(prenom="", nom="")
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="15.00")
    client.post(
        "/panier/add/membership/",
        {"price": str(adhesion.tarif.uuid), "firstname": "Ada", "lastname": "Lovelace"},
        **EN_TETE_HTMX,
    )

    client.post("/panier/checkout/", **EN_TETE_HTMX)

    commande = Commande.objects.get(user=acheteur)
    assert commande.first_name == "Ada"
    assert commande.last_name == "Lovelace"


# --------------------------------------------------------------------------
# Badge du panier dans chaque skin
# / Cart badge in every skin
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "skin",
    [
        "classic",
        "V2",
        "faire_festival",
    ],
)
def test_la_barre_de_navigation_de_chaque_skin_contient_la_cible_du_badge_du_panier(
    skin,
):
    """
    Le badge du panier est mis à jour par un swap HTMX hors-bande sur `#panier-badge-nav` :
    la barre de navigation de chaque skin (incluse par son `shell.html`) doit porter cet
    élément, sinon le badge ne bouge jamais après un ajout.
    / The cart badge is updated by an out-of-band swap on `#panier-badge-nav`: every skin's
    navbar (included by its `shell.html`) must carry that element.
    """
    dossier_du_skin = Path(settings.BASE_DIR) / "pages" / "templates" / "pages" / skin
    squelette = (dossier_du_skin / "shell.html").read_text(encoding="utf-8")
    assert f"pages/{skin}/partials/navbar.html" in squelette
    barre_de_navigation = (dossier_du_skin / "partials" / "navbar.html").read_text(
        encoding="utf-8"
    )

    assert 'id="panier-badge-nav"' in barre_de_navigation
