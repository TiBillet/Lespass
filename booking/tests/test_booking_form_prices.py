"""
Tests de l'affichage des tarifs dans le formulaire de réservation.
/ Tests of the price display in the booking form.

LOCALISATION : booking/tests/test_booking_form_prices.py

Spécification : booking/spec/main/booking-form.md, section « Tarifs ».
/ Specification: booking/spec/main/booking-form.md, section "Tarifs".

Chaque test fabrique sa ressource dans une transaction annulée à la fin
(`django_db`) : rien ne reste en base de dev.
/ Each test builds its resource inside a rolled-back transaction (`django_db`).

Lancement / Run:
    docker exec lespass_django poetry run pytest booking/tests/test_booking_form_prices.py -v
"""
import re
import sys

import pytest
from django_tenants.utils import tenant_context

# Les fabriques du panier (ressource avec créneaux, adhésion, client connecté)
# sont dans tests/pytest/. On les réutilise au lieu de les recopier.
# / The cart factories live in tests/pytest/: reuse them instead of copying them.
sys.path.insert(0, '/DjangoFiles/tests/pytest')
from fabriques_panier import (  # noqa: E402
    ajouter_un_tarif,
    client_connecte,
    creer_adhesion,
    creer_ressource_avec_tarif,
    creer_une_adhesion_active,
    creer_utilisateur,
)

pytestmark = pytest.mark.django_db

EN_TETE_HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def lieu(tenant):
    """Le lieu `lespass`, pendant tout le test. / The `lespass` venue, for the whole test."""
    with tenant_context(tenant):
        yield tenant


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


# --------------------------------------------------------------------------
# Outils de lecture du formulaire
# / Form reading helpers
# --------------------------------------------------------------------------


def formulaire_de_reservation(client, location):
    """
    Le HTML du formulaire de réservation pour le premier créneau de la ressource,
    demandé comme la page de la ressource le demande : en HTMX (popup).
    / The booking form HTML for the resource's first slot, requested like the
    resource page does: through HTMX (popup).
    """
    debut_naif = location.debut_du_creneau.replace(tzinfo=None).isoformat()
    reponse = client.get(
        f"/booking/{location.ressource.pk}/book/",
        {"start_datetime": debut_naif},
        **EN_TETE_HTMX,
    )
    assert reponse.status_code == 200
    return reponse.content.decode()


def texte_sans_balises(html):
    """Le texte visible d'un morceau de HTML, espaces regroupés.
    / The visible text of an HTML fragment, whitespace collapsed."""
    sans_commentaires = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    sans_balises = re.sub(r"<[^>]+>", " ", sans_commentaires)
    return " ".join(sans_balises.split())


def bloc_du_tarif(html, tarif):
    """
    Le morceau de HTML d'un tarif : de son conteneur jusqu'au tarif suivant
    (ou la fin de la liste). None si le tarif n'est pas affiché.
    / The HTML of one price: from its container to the next price (or the
    end of the list). None when the price is not displayed.
    """
    marqueur = f'data-testid="booking-price-{tarif.uuid}"'
    position_du_marqueur = html.find(marqueur)
    if position_du_marqueur == -1:
        return None
    # On part du début de la balise qui porte le marqueur.
    # / Start at the opening of the tag that carries the marker.
    debut = html.rfind("<", 0, position_du_marqueur)
    fins_possibles = []
    for marqueur_de_fin in ['data-testid="booking-price-', "<script"]:
        position = html.find(marqueur_de_fin, position_du_marqueur + len(marqueur))
        if position != -1:
            fins_possibles.append(position)
    fin = min(fins_possibles) if fins_possibles else len(html)
    return html[debut:fin]


def choix_du_tarif(bloc, tarif):
    """La balise <input> radio du tarif, ou None. / The price's radio <input>, or None."""
    resultat = re.search(
        r'<input[^>]*name="price"[^>]*value="' + str(tarif.uuid) + r'"[^>]*>',
        bloc,
        flags=re.S,
    )
    if resultat is None:
        return None
    return resultat.group(0)


def client_en_francais(utilisateur):
    """
    Client connecté qui lit les pages en français : les nouveaux textes sont des textes
    source en français, et le format des montants suit la langue (« 8,33 »).
    / Logged-in client reading pages in French (French source texts, French number format).
    """
    client = client_connecte(utilisateur)
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "fr"
    return client


def libelle_du_tarif(html, tarif):
    """
    Le texte du libellé (<label>) du choix d'un tarif, espaces regroupés.
    / The text of a price choice's <label>, whitespace collapsed.
    """
    bloc = bloc_du_tarif(html, tarif)
    resultat = re.search(
        r'<label[^>]*for="price-' + str(tarif.uuid) + r'"[^>]*>(.*?)</label>',
        bloc,
        flags=re.S,
    )
    assert resultat is not None
    return texte_sans_balises(resultat.group(1))


def tarif_reserve_aux_adherents(location, nom="Tarif adhérent", prix="8.00"):
    """Ajoute à la ressource un tarif fixe réservé aux adhérents d'une adhésion.
    / Adds a fixed members-only price, tied to one membership, to the resource."""
    adhesion = creer_adhesion()
    tarif = ajouter_un_tarif(location.produit, prix=prix, nom=nom)
    tarif.adhesions_obligatoires.add(adhesion.produit)
    return tarif, adhesion


# --------------------------------------------------------------------------
# Formulaire de réservation : l'accès
# / Booking form: access
# --------------------------------------------------------------------------


def test_formulaire_de_reservation_visiteur_non_connecte_redirige(lieu):
    """
    Un visiteur non connecté n'a pas le formulaire : il est renvoyé vers `/`, avec
    l'avertissement « Please login to access this page. ».
    / A visitor who is not logged in gets no form: redirected to `/`, with a warning.
    """
    from django.contrib.messages import WARNING

    location = creer_ressource_avec_tarif(prix="12.00")
    debut_naif = location.debut_du_creneau.replace(tzinfo=None).isoformat()

    reponse = client_connecte().get(
        f"/booking/{location.ressource.pk}/book/",
        {"start_datetime": debut_naif},
        **EN_TETE_HTMX,
    )

    assert reponse.get("HX-Redirect") == "/"
    assert 'name="price"' not in reponse.content.decode()
    messages_du_visiteur = []
    for message in reponse.wsgi_request._messages:
        messages_du_visiteur.append((message.level, str(message)))
    assert (WARNING, "Please login to access this page.") in messages_du_visiteur


# --------------------------------------------------------------------------
# Tarifs : les tarifs listés
# / Tarifs: the listed prices
# --------------------------------------------------------------------------


def test_tarifs_exemple(lieu):
    """
    L'exemple de la spec : créneaux de 180 minutes, un tarif fixe, deux tarifs à prix
    libre (avec et sans minimum), un tarif gratuit, un tarif archivé.
    / The spec example: 180-minute slots, a fixed price, two pay-what-you-want prices
    (with and without minimum), a free price, an archived price.
    """
    location = creer_ressource_avec_tarif(prix="12.00", duree_du_creneau_en_minutes=180)
    plein_tarif = location.tarif
    plein_tarif.name = "Plein tarif"
    plein_tarif.save()
    soutien = ajouter_un_tarif(location.produit, prix="5.00", nom="Soutien", free_price=True)
    solidaire = ajouter_un_tarif(
        location.produit, prix="0.00", nom="Solidaire", free_price=True
    )
    benevoles = ajouter_un_tarif(location.produit, prix="0.00", nom="Bénévoles")
    ancien_tarif = ajouter_un_tarif(
        location.produit, prix="9.00", nom="Ancien tarif", archived=True
    )

    html = formulaire_de_reservation(client_en_francais(creer_utilisateur()), location)

    assert "Tarifs :" in texte_sans_balises(html)
    assert libelle_du_tarif(html, plein_tarif) == "Plein tarif - 36 € / créneau"
    assert libelle_du_tarif(html, soutien) == "Soutien - prix libre dès 15 € / créneau"
    assert libelle_du_tarif(html, solidaire) == "Solidaire - prix libre"
    assert libelle_du_tarif(html, benevoles) == "Bénévoles - gratuit"
    assert 'placeholder="Montant par créneau, 15 € minimum"' in bloc_du_tarif(html, soutien)
    assert 'placeholder="Montant par créneau"' in bloc_du_tarif(html, solidaire)
    assert bloc_du_tarif(html, ancien_tarif) is None


def test_tarifs_un_tarif_pas_en_vente_n_apparait_pas(lieu):
    """
    Un tarif non publié, ou archivé, n'est pas listé.
    / An unpublished or archived price is not listed.
    """
    location = creer_ressource_avec_tarif(prix="12.00")
    non_publie = ajouter_un_tarif(location.produit, prix="7.00", nom="Caché")
    non_publie.publish = False
    non_publie.save()
    archive = ajouter_un_tarif(location.produit, prix="6.00", nom="Archivé", archived=True)

    html = formulaire_de_reservation(client_connecte(creer_utilisateur()), location)

    assert bloc_du_tarif(html, location.tarif) is not None
    assert bloc_du_tarif(html, non_publie) is None
    assert bloc_du_tarif(html, archive) is None


def test_tarifs_chaque_tarif_en_vente_est_un_choix(lieu):
    """
    Chaque tarif en vente est un choix (bouton radio `price`).
    / Each price on sale is one choice (a `price` radio button).
    """
    location = creer_ressource_avec_tarif(prix="12.00")
    second_tarif = ajouter_un_tarif(location.produit, prix="5.00", nom="Réduit")

    html = formulaire_de_reservation(client_connecte(creer_utilisateur()), location)

    for tarif in [location.tarif, second_tarif]:
        choix = choix_du_tarif(bloc_du_tarif(html, tarif), tarif)
        assert choix is not None
        assert 'type="radio"' in choix


def test_tarifs_libelle_du_tarif_fixe(lieu):
    """
    Un tarif fixe se lit `<name> - <montant> € / créneau`, le montant valant
    `prix × durée du créneau / 60`.
    / A fixed price reads `<name> - <amount> € / créneau`, amount = prix × duration / 60.
    """
    location = creer_ressource_avec_tarif(prix="12.00", duree_du_creneau_en_minutes=90)
    location.tarif.name = "Location salle"
    location.tarif.save()

    html = formulaire_de_reservation(client_en_francais(creer_utilisateur()), location)

    assert libelle_du_tarif(html, location.tarif) == "Location salle - 18 € / créneau"


def test_tarifs_montant_arrondi_au_centime_sans_centimes_inutiles(lieu):
    """
    Le montant d'un créneau est arrondi au centime, et s'écrit selon la langue :
    10 €/h pour 50 minutes donnent 8,333… €, affichés « 8,33 » en français.
    / The slot amount is rounded to the cent and written in the active language.
    """
    location = creer_ressource_avec_tarif(prix="10.00", duree_du_creneau_en_minutes=50)
    location.tarif.name = "Location salle"
    location.tarif.save()

    html = formulaire_de_reservation(client_en_francais(creer_utilisateur()), location)

    assert libelle_du_tarif(html, location.tarif) == "Location salle - 8,33 € / créneau"


def test_tarifs_libelle_et_champ_du_tarif_a_prix_libre(lieu):
    """
    Un tarif à prix libre se lit `<name> - prix libre dès <minimum> € / créneau`, et son
    champ de montant dit « Montant par créneau, <minimum> € minimum ».
    / A pay-what-you-want price shows its per-slot minimum, in the label and the field.
    """
    location = creer_ressource_avec_tarif(
        prix="6.00", prix_libre=True, duree_du_creneau_en_minutes=120
    )
    location.tarif.name = "Soutien"
    location.tarif.save()

    html = formulaire_de_reservation(client_en_francais(creer_utilisateur()), location)
    bloc = bloc_du_tarif(html, location.tarif)

    assert libelle_du_tarif(html, location.tarif) == "Soutien - prix libre dès 12 € / créneau"
    assert 'placeholder="Montant par créneau, 12 € minimum"' in bloc
    assert "per hour" not in texte_sans_balises(bloc)


def test_tarifs_prix_libre_sans_minimum(lieu):
    """
    Un tarif à prix libre dont `prix` vaut 0 se lit `<name> - prix libre`, et son champ
    dit « Montant par créneau ».
    / A pay-what-you-want price with a 0 minimum reads `<name> - prix libre`.
    """
    location = creer_ressource_avec_tarif(prix="0.00", prix_libre=True)
    location.tarif.name = "Solidaire"
    location.tarif.save()

    html = formulaire_de_reservation(client_en_francais(creer_utilisateur()), location)

    assert libelle_du_tarif(html, location.tarif) == "Solidaire - prix libre"
    assert 'placeholder="Montant par créneau"' in bloc_du_tarif(html, location.tarif)


def test_tarifs_tarif_gratuit(lieu):
    """
    Un tarif gratuit (fixe, `prix` à 0) se lit `<name> - gratuit`.
    / A free price (fixed, `prix` 0) reads `<name> - gratuit`.
    """
    location = creer_ressource_avec_tarif(prix="0.00")
    location.tarif.name = "Bénévoles"
    location.tarif.save()

    html = formulaire_de_reservation(client_en_francais(creer_utilisateur()), location)

    assert libelle_du_tarif(html, location.tarif) == "Bénévoles - gratuit"


def test_r2_minimum_affiche_arrondi_au_centime_superieur(lieu):
    """
    R2 : le minimum d'un prix libre est arrondi au centime supérieur. 10 €/h pour 50
    minutes donnent 8,333… €, affichés « 8,34 ».
    / R2: the open-price minimum is rounded UP to the cent: 8.333… shows as 8,34.
    """
    location = creer_ressource_avec_tarif(
        prix="10.00", prix_libre=True, duree_du_creneau_en_minutes=50
    )
    location.tarif.name = "Soutien"
    location.tarif.save()

    html = formulaire_de_reservation(client_en_francais(creer_utilisateur()), location)

    assert libelle_du_tarif(html, location.tarif) == "Soutien - prix libre dès 8,34 € / créneau"
    assert 'placeholder="Montant par créneau, 8,34 € minimum"' in bloc_du_tarif(
        html, location.tarif
    )


def test_tarifs_un_seul_tarif_en_vente_est_preselectionne(lieu):
    """
    Un seul tarif en vente, qu'on peut choisir : il est présélectionné.
    / A single price on sale that can be chosen is pre-selected.
    """
    location = creer_ressource_avec_tarif(prix="12.00")

    html = formulaire_de_reservation(client_connecte(creer_utilisateur()), location)

    assert "checked" in choix_du_tarif(bloc_du_tarif(html, location.tarif), location.tarif)


def test_tarifs_plusieurs_tarifs_aucun_preselectionne(lieu):
    """
    Plusieurs tarifs en vente : aucun n'est présélectionné.
    / Several prices on sale: none is pre-selected.
    """
    location = creer_ressource_avec_tarif(prix="12.00")
    second_tarif = ajouter_un_tarif(location.produit, prix="5.00", nom="Réduit")

    html = formulaire_de_reservation(client_connecte(creer_utilisateur()), location)

    for tarif in [location.tarif, second_tarif]:
        assert "checked" not in choix_du_tarif(bloc_du_tarif(html, tarif), tarif)


# --------------------------------------------------------------------------
# Tarifs : les tarifs réservés aux adhérents
# / Tarifs: members-only prices
# --------------------------------------------------------------------------


def test_tarifs_reserve_aux_adherents_adhesion_valide_choix_normal(lieu):
    """
    Adhésion valide : le tarif est un choix normal.
    / Valid membership: the price is a normal choice.
    """
    location = creer_ressource_avec_tarif(prix="12.00")
    tarif, adhesion = tarif_reserve_aux_adherents(location)
    adherent = creer_utilisateur()
    creer_une_adhesion_active(adherent, adhesion)

    html = formulaire_de_reservation(client_connecte(adherent), location)
    bloc = bloc_du_tarif(html, tarif)

    assert choix_du_tarif(bloc, tarif) is not None


def test_tarifs_reserve_aux_adherents_adhesion_au_panier_choix_normal(lieu):
    """
    L'adhésion est dans le panier : le tarif est un choix normal.
    / The membership is in the cart: the price is a normal choice.
    """
    location = creer_ressource_avec_tarif(prix="12.00")
    tarif, adhesion = tarif_reserve_aux_adherents(location)
    client = client_connecte(creer_utilisateur())
    ajout = client.post(
        "/panier/add/membership/",
        {"price": str(adhesion.tarif.uuid), "firstname": "Ada", "lastname": "Lovelace"},
        **EN_TETE_HTMX,
    )
    assert ajout.status_code == 200

    html = formulaire_de_reservation(client, location)

    assert choix_du_tarif(bloc_du_tarif(html, tarif), tarif) is not None


def test_tarifs_reserve_aux_adherents_sans_adhesion(lieu):
    """
    Connecté sans adhésion : « You must have <A> or <B> to book this rate. », chaque
    adhésion en lien vers `/memberships/?open=<uuid>`, et pas de choix.
    / Logged in without membership: the message, one link per membership, no choice.
    """
    location = creer_ressource_avec_tarif(prix="12.00")
    tarif, premiere_adhesion = tarif_reserve_aux_adherents(location)
    seconde_adhesion = creer_adhesion()
    tarif.adhesions_obligatoires.add(seconde_adhesion.produit)

    html = formulaire_de_reservation(client_connecte(creer_utilisateur()), location)
    bloc = bloc_du_tarif(html, tarif)
    texte = texte_sans_balises(bloc)

    assert texte.startswith("You must have")
    assert texte.endswith("to book this rate.")
    assert " or " in texte
    for adhesion in [premiere_adhesion, seconde_adhesion]:
        assert f'href="/memberships/?open={adhesion.produit.uuid}"' in bloc
        assert adhesion.produit.name in texte
    assert choix_du_tarif(bloc, tarif) is None


def test_tarifs_reserve_aux_adherents_seul_tarif_sans_adhesion_pas_preselectionne(lieu):
    """
    Un seul tarif en vente, réservé aux adhérents, sans adhésion : il n'y a pas de
    choix, donc rien n'est présélectionné.
    / A single members-only price, no membership: no choice, so nothing pre-selected.
    """
    location = creer_ressource_avec_tarif(prix="12.00")
    location.tarif.archived = True
    location.tarif.save()
    tarif, _adhesion = tarif_reserve_aux_adherents(location)

    html = formulaire_de_reservation(client_connecte(creer_utilisateur()), location)

    assert 'name="price"' not in bloc_du_tarif(html, tarif)
