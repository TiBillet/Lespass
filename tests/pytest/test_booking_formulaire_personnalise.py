"""
Réservation de ressource : les questions du formulaire dynamique du produit sont posées,
validées, enregistrées sur le Booking, puis affichées (compte, admin) et exportées.
/ Resource booking: the product's dynamic form questions are asked, validated, stored on
the Booking, then shown (account, admin) and exported.

LOCALISATION : tests/pytest/test_booking_formulaire_personnalise.py

Code testé / Tested code :
- booking/views.py : BookingViewSet._book_post (réservation directe)
- BaseBillet/views.py : PanierMVT.add_resource (panier)
- BaseBillet/services_commande.py : CommandeService.materialiser (panier -> Booking)
- booking/booking_engine.py : validate_new_booking(custom_form=...)
- BaseBillet/templates/commun/formulaires/champs_produit.html (partial des questions)
- pages/templates/pages/V2/vues/compte/bookings.html (accordéon des réponses)
- Administration/templates/admin/booking/custom_form.html (fiche admin)
- Administration/importers/resources_bookings_exporters.py (colonnes de l'export)

Les tarifs sont gratuits (0 €) : la réservation est confirmée sans passer par Stripe,
par les deux parcours.
/ Prices are free: the booking is confirmed without Stripe, through both flows.

Chaque test est marqué `django_db` : pytest-django l'exécute dans une transaction annulée.
/ Every test runs in a rolled-back transaction.

Lancer / Run : make test ARGS="tests/pytest/test_booking_formulaire_personnalise.py"
"""

import json
import re
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string
from django.urls import reverse
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    creer_ressource_avec_tarif,
    creer_utilisateur,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db

SANS_PANIER = "sans_panier"
AVEC_PANIER = "avec_panier"
LES_DEUX_PARCOURS = [SANS_PANIER, AVEC_PANIER]

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
    Le lieu `lespass`, avec Stripe et Celery simulés pendant tout le test.
    / The `lespass` venue, with Stripe and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees():
                yield SimpleNamespace(tenant=tenant, stripe=mock_stripe)


def ajouter_une_question(produit, label, field_type="ST", required=False, options=None):
    """Ajoute une question au formulaire dynamique du produit.
    / Adds a question to the product's dynamic form."""
    from BaseBillet.models import ProductFormField

    return ProductFormField.objects.create(
        product=produit,
        label=label,
        field_type=field_type,
        required=required,
        options=options,
    )


def reserver_une_ressource(parcours, client, location, reponses_du_formulaire):
    """
    Réserve une heure de la ressource, avec les champs « form__* » donnés.
    / Books one hour of the resource, with the given "form__*" fields.

    Sans panier : POST /booking/<ressource>/book/.
    Avec panier : ajout au panier, puis paiement (gratuit ici).
    Rend la réponse de la réservation directe, ou celle de l'AJOUT au panier.
    """
    debut = location.debut_du_creneau
    fin = debut + timedelta(hours=1)
    donnees_du_formulaire = {
        "resource": str(location.ressource.pk),
        "price_uuid": str(location.tarif.uuid),
        "start_datetime": debut.replace(tzinfo=None).isoformat(),
        "end_time": fin.replace(tzinfo=None).isoformat(),
        "firstname": "Ada",
        "lastname": "Lovelace",
    }
    donnees_du_formulaire.update(reponses_du_formulaire)

    if parcours == SANS_PANIER:
        return client.post(
            f"/booking/{location.ressource.pk}/book/",
            donnees_du_formulaire,
            **EN_TETE_HTMX,
        )

    reponse_de_l_ajout = client.post(
        "/panier/add/resource/", donnees_du_formulaire, **EN_TETE_HTMX
    )
    client.post("/panier/checkout/", **EN_TETE_HTMX)
    return reponse_de_l_ajout


def booking_de(acheteur, location):
    """Le booking de l'acheteur sur cette ressource, ou None.
    / The buyer's booking on this resource, or None."""
    from booking.models import Booking

    return Booking.objects.filter(user=acheteur, resource=location.ressource).first()


def niveau_du_toast(reponse):
    """Le niveau du toast envoyé par `HX-Trigger`, ou None.
    / The level of the toast sent through `HX-Trigger`, or None."""
    en_tete = reponse.get("HX-Trigger")
    if not en_tete:
        return None
    return json.loads(en_tete)["panierToast"]["level"]


def client_de_mon_compte(lieu, utilisateur):
    """
    Le client connecté à « Mon compte », avec un compte actif et un portefeuille local.
    / The user logged in to "My account", with an active account and a local wallet.

    « Mon compte » demande un portefeuille à Fedow en HTTP si le compte n'en a pas
    (BaseBillet/views.py, MyAccount.dispatch) : on en pose un local avant, par update(),
    qui ne déclenche aucun signal (tests/PIEGES.md 12.17). Même méthode que
    test_caracterisation_annulations.py.
    / "My account" asks Fedow for a wallet: set a local one first, with update().
    """
    from AuthBillet.models import TibilletUser, Wallet

    portefeuille_local = Wallet.objects.create(
        name=f"TEST_booking_formulaire portefeuille {utilisateur.pk}",
        origin=lieu.tenant,
    )
    TibilletUser.objects.filter(pk=utilisateur.pk).update(
        is_active=True, wallet=portefeuille_local
    )
    utilisateur.refresh_from_db()
    return client_connecte(utilisateur)


def creer_un_booking_avec_reponses(reponses):
    """Un Booking enregistré directement en base, avec ses réponses.
    / A Booking saved straight to the database, with its answers."""
    from booking.models import Booking

    location = creer_ressource_avec_tarif(prix="0.00")
    booking = Booking.objects.create(
        resource=location.ressource,
        user=creer_utilisateur(),
        start_datetime=location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=1,
        # Statut confirmé : « Mes réservations » n'affiche que les réservations confirmées.
        # / Confirmed status: "My bookings" only lists confirmed bookings.
        status=Booking.FREERES_USERACTIV,
        custom_form=reponses,
    )
    return booking, location


# --------------------------------------------------------------------------
# Réservation : les réponses arrivent sur le Booking
# / Booking: answers reach the Booking
# --------------------------------------------------------------------------


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_la_reponse_est_rangee_sous_le_libelle_dans_le_booking(lieu, parcours):
    """La réponse est enregistrée sous le LIBELLÉ de la question, par les deux parcours.
    / The answer is stored under the question LABEL, through both flows."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="0.00")
    question = ajouter_une_question(location.produit, "Nombre de musiciens")

    reserver_une_ressource(parcours, client, location, {f"form__{question.name}": "4"})

    booking = booking_de(acheteur, location)
    assert booking is not None
    assert booking.custom_form == {"Nombre de musiciens": "4"}


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_un_choix_multiple_garde_toutes_les_cases_cochees(lieu, parcours):
    """Un choix multiple est enregistré en liste, avec toutes les cases cochées.
    / A multi-select is stored as a list with every checked value."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="0.00")
    question = ajouter_une_question(
        location.produit,
        "Matériel",
        field_type="MS",
        options=["Ampli", "Batterie", "Micro"],
    )

    reserver_une_ressource(
        parcours, client, location, {f"form__{question.name}": ["Ampli", "Micro"]}
    )

    booking = booking_de(acheteur, location)
    assert booking.custom_form == {"Matériel": ["Ampli", "Micro"]}


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_sans_question_le_booking_n_a_pas_de_reponses(lieu, parcours):
    """Un produit sans question : la réservation passe, custom_form vaut None.
    / A product without questions: booking succeeds, custom_form is None."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="0.00")

    reserver_une_ressource(parcours, client, location, {})

    booking = booking_de(acheteur, location)
    assert booking is not None
    assert booking.custom_form is None


# --------------------------------------------------------------------------
# Question obligatoire sans réponse : refus propre
# / Required question left empty: clean refusal
# --------------------------------------------------------------------------


def test_reservation_directe_question_obligatoire_vide_renvoie_422_sans_booking(lieu):
    """Sans panier : une question obligatoire vide renvoie le formulaire en 422, avec le
    libellé de la question, et aucun Booking n'est créé.
    / Direct flow: an empty required question returns the form as 422, no Booking."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="0.00")
    ajouter_une_question(location.produit, "Nom du groupe", required=True)

    reponse = reserver_une_ressource(SANS_PANIER, client, location, {})

    assert reponse.status_code == 422
    assert "Nom du groupe" in reponse.content.decode()
    assert booking_de(acheteur, location) is None


def test_reservation_directe_en_erreur_reaffiche_les_reponses_deja_tapees(lieu):
    """Après une erreur 422, la réponse déjà tapée à une autre question est réaffichée.
    / After a 422, the answer already typed to another question is shown again."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="0.00")
    ajouter_une_question(location.produit, "Nom du groupe", required=True)
    question_remplie = ajouter_une_question(location.produit, "Style de musique")

    reponse = reserver_une_ressource(
        SANS_PANIER,
        client,
        location,
        {f"form__{question_remplie.name}": "Jazz manouche"},
    )

    assert reponse.status_code == 422
    assert 'value="Jazz manouche"' in reponse.content.decode()


def test_panier_question_obligatoire_vide_donne_un_toast_et_un_panier_vide(lieu):
    """Avec panier : une question obligatoire vide bloque l'ajout avec un toast d'erreur.
    / Cart: an empty required question blocks the add with an error toast."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="0.00")
    ajouter_une_question(location.produit, "Nom du groupe", required=True)

    reponse = reserver_une_ressource(AVEC_PANIER, client, location, {})

    assert niveau_du_toast(reponse) == "error"
    assert client.session.get("panier", {}).get("items", []) == []
    assert booking_de(acheteur, location) is None


# --------------------------------------------------------------------------
# Partial des questions / Questions partial
# --------------------------------------------------------------------------


def test_le_partial_affiche_les_six_types_de_questions(lieu):
    """Chaque type de question est rendu avec son champ « form__<name> » et son data-testid.
    / Every question type is rendered with its "form__<name>" field and data-testid."""
    location = creer_ressource_avec_tarif(prix="0.00")
    options = ["Oui", "Non"]
    questions = [
        ajouter_une_question(location.produit, "Texte court", field_type="ST"),
        ajouter_une_question(location.produit, "Texte long", field_type="LT"),
        ajouter_une_question(
            location.produit, "Liste", field_type="SS", options=options
        ),
        ajouter_une_question(
            location.produit, "Radio", field_type="SR", options=options
        ),
        ajouter_une_question(
            location.produit, "Plusieurs", field_type="MS", options=options
        ),
        ajouter_une_question(location.produit, "Interrupteur", field_type="BL"),
    ]

    html = render_to_string(
        "commun/formulaires/champs_produit.html",
        {"product": location.produit, "testid_prefix": "resource-booking"},
    )

    for question in questions:
        assert f'name="form__{question.name}"' in html
        assert f'data-testid="resource-booking-form-field-{question.name}"' in html


def test_le_partial_remet_les_reponses_du_prefill(lieu):
    """`prefill` remet le texte tapé et coche les cases déjà choisies.
    / `prefill` puts back typed text and re-checks chosen boxes."""
    location = creer_ressource_avec_tarif(prix="0.00")
    question_texte = ajouter_une_question(location.produit, "Nom du groupe")
    question_cases = ajouter_une_question(
        location.produit, "Matériel", field_type="MS", options=["Ampli", "Micro"]
    )

    html = render_to_string(
        "commun/formulaires/champs_produit.html",
        {
            "product": location.produit,
            "testid_prefix": "resource-booking",
            "prefill": {
                question_texte.name: "Les Ours",
                question_cases.name: ["Micro"],
            },
        },
    )

    assert 'value="Les Ours"' in html
    case_micro = re.search(r'<input[^>]*value="Micro"[^>]*>', html).group(0)
    case_ampli = re.search(r'<input[^>]*value="Ampli"[^>]*>', html).group(0)
    assert "checked" in case_micro
    assert "checked" not in case_ampli


def test_le_partial_n_affiche_rien_sans_question_ni_produit(lieu):
    """Un produit sans question, ou pas de produit : le partial ne rend aucun champ.
    / A product without questions, or no product: the partial renders no field."""
    location = creer_ressource_avec_tarif(prix="0.00")

    html_sans_question = render_to_string(
        "commun/formulaires/champs_produit.html",
        {"product": location.produit, "testid_prefix": "resource-booking"},
    )
    html_sans_produit = render_to_string(
        "commun/formulaires/champs_produit.html",
        {"product": None, "testid_prefix": "resource-booking"},
    )

    assert "form__" not in html_sans_question
    assert "form__" not in html_sans_produit


# --------------------------------------------------------------------------
# Affichage : compte, admin, export
# / Display: account, admin, export
# --------------------------------------------------------------------------


def test_le_compte_affiche_les_reponses_dans_un_accordeon_propre_au_booking(lieu):
    """La page « Mes réservations » montre les réponses, dans un accordéon dont
    l'identifiant contient le pk du booking (unique dans la page).
    / "My bookings" shows the answers in an accordion whose id holds the booking pk."""
    booking, _location = creer_un_booking_avec_reponses({"Nom du groupe": "Les Ours"})
    client = client_de_mon_compte(lieu, booking.user)

    reponse = client.get(reverse("my_account-my-bookings"))

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert "Les Ours" in contenu
    assert f'id="booking{booking.pk}FormAccordion"' in contenu


def test_la_fiche_admin_affiche_les_reponses_en_tableau(lieu, admin_client):
    """La fiche admin du booking montre les réponses en tableau, pas le JSON brut.
    / The admin change view shows answers as a table, not raw JSON."""
    booking, _location = creer_un_booking_avec_reponses({"Nom du groupe": "Les Ours"})

    url = reverse("staff_admin:booking_booking_change", args=[booking.pk])
    reponse = admin_client.get(url)

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="booking-custom-form-answers"' in contenu
    assert "Les Ours" in contenu
    assert 'name="custom_form"' not in contenu


def test_l_export_ajoute_une_colonne_par_question_dans_l_ordre(lieu):
    """L'export ajoute une colonne par question, dans l'ordre d'affichage des questions.
    Une réservation sans réponse donne une case vide.
    / The export adds one column per question, in display order; no answer gives an
    empty cell."""
    from Administration.importers.resources_bookings_exporters import (
        BookingExportResource,
    )
    from booking.models import Booking

    booking, location = creer_un_booking_avec_reponses(
        {"Style": "Jazz", "Nom du groupe": "Les Ours"}
    )
    # Ordre d'affichage : « Nom du groupe » en premier, même si la réponse « Style »
    # a été rangée avant dans custom_form.
    # / Display order: "Nom du groupe" first, whatever the custom_form key order.
    premiere_question = ajouter_une_question(location.produit, "Nom du groupe")
    premiere_question.order = 1
    premiere_question.save(update_fields=["order"])
    deuxieme_question = ajouter_une_question(location.produit, "Style")
    deuxieme_question.order = 2
    deuxieme_question.save(update_fields=["order"])
    booking_sans_reponse = Booking.objects.create(
        resource=location.ressource,
        user=creer_utilisateur(),
        start_datetime=location.debut_du_creneau + timedelta(hours=1),
        slot_duration_minutes=60,
        slot_count=1,
    )

    queryset = Booking.objects.filter(
        pk__in=[booking.pk, booking_sans_reponse.pk]
    ).order_by("pk")
    tableau = BookingExportResource().export(queryset=queryset)

    assert tableau.headers[-2:] == ["Nom du groupe", "Style"]
    assert list(tableau[0])[-2:] == ["Les Ours", "Jazz"]
    assert list(tableau[1])[-2:] == ["", ""]
