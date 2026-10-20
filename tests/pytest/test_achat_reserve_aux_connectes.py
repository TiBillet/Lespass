"""
Réserver un billet et adhérer exigent d'être connecté.
/ Booking a ticket and joining require being logged in.

LOCALISATION : tests/pytest/test_achat_reserve_aux_connectes.py

Code testé :
- BaseBillet/views.py : EventMVT.get_permissions, EventMVT.reservation,
  EventMVT.action_reservation, MembershipMVT.get_permissions, MembershipMVT.create ;
- les gabarits commun/formulaires/reservation.html, commun/adhesion/form.html et
  commun/offcanvas/connexion.html (ce qu'un anonyme voit).
/ Tested code: EventMVT and MembershipMVT permissions and email injection, templates.

POURQUOI :
- un anonyme ne peut plus réserver ni adhérer au nom d'un autre (il tapait un email) ;
- une personne connectée réserve et adhère toujours pour ELLE-MÊME : la vue remplace
  l'email posté par celui de son compte. Un tarif réservé aux adhérents ne s'obtient
  donc pas en postant l'email d'un adhérent.
/ An anonymous visitor can no longer book or join for someone else; a logged-in
person always books and joins for themselves.

PIÈGES (tests/PIEGES.md, section « Panier : tests et parité avec / sans panier ») :
- `django_db` donne un rollback (13.1) : pas de ménage à la main (13.24) ;
- un client neuf par test, `force_login` dedans (13.10) ;
- Stripe (catalogue) et Celery simulés (13.3, 13.4) ;
- formulaires postés avec l'en-tête HTMX (13.8).

Lancer / Run :
docker exec lespass_django bash -c "ulimit -v 8000000; timeout 600 poetry run pytest /DjangoFiles/tests/pytest/test_achat_reserve_aux_connectes.py -v"
"""

from types import SimpleNamespace

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_une_adhesion_active,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db

# Les formulaires du front sont envoyés par HTMX (hx-post).
# / Front forms are sent by HTMX.
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
    / The `lespass` venue, with Stripe and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    stripe=mock_stripe,
                    taches_demandees=taches_demandees,
                )


def un_email_que_personne_n_a():
    """Un email unique, sans compte. / A unique email, with no account."""
    return f"test+autre{identifiant_unique()}@mock.test"


def poster_une_reservation(client, evenement, tarif, email):
    """POST du formulaire de réservation (« Payer maintenant »).
    / POST of the booking form."""
    return client.post(
        f"/event/{evenement.slug}/reservation/",
        {"event": str(evenement.uuid), "email": email, str(tarif.uuid): "1"},
        **EN_TETE_HTMX,
    )


def poster_une_adhesion(client, tarif, email):
    """POST du formulaire d'adhésion (« Payer maintenant »).
    / POST of the membership form."""
    return client.post(
        "/memberships/",
        {
            "price": str(tarif.uuid),
            "email": email,
            "firstname": "Ada",
            "lastname": "Lovelace",
            "acknowledge": "true",
            "newsletter": "false",
        },
        **EN_TETE_HTMX,
    )


# --------------------------------------------------------------------------
# Un anonyme est refusé (403)
# / An anonymous visitor is refused (403)
# --------------------------------------------------------------------------


def test_un_anonyme_ne_peut_pas_reserver(lieu):
    """POST /event/<slug>/reservation/ sans être connecté : 403, rien n'est créé,
    pas même un compte à l'email tapé.
    / Anonymous booking: 403, nothing created, not even an account."""
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import Product, Reservation

    atelier = creer_evenement_avec_tarif(categorie=Product.FREERES)
    email_tape = un_email_que_personne_n_a()

    reponse = poster_une_reservation(
        client_connecte(), atelier.evenement, atelier.tarif, email_tape
    )

    assert reponse.status_code == 403
    assert not TibilletUser.objects.filter(email=email_tape).exists()
    assert not Reservation.objects.filter(event=atelier.evenement).exists()


def test_un_anonyme_ne_peut_pas_cocher_une_action(lieu):
    """POST /event/<pk>/action_reservation/ sans être connecté : 403, pas une 500.
    Le `permission_classes` de l'@action est ignoré : get_permissions() décide.
    / Anonymous action_reservation: 403, not a 500."""
    concert = creer_evenement_avec_tarif()

    reponse = client_connecte().post(
        f"/event/{concert.evenement.pk}/action_reservation/",
        {"action": str(concert.evenement.pk)},
        **EN_TETE_HTMX,
    )

    assert reponse.status_code == 403


def test_un_anonyme_ne_peut_pas_adherer(lieu):
    """POST /memberships/ sans être connecté : 403, aucune adhésion, aucun compte.
    / Anonymous membership: 403, nothing created."""
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import Membership

    adhesion = creer_adhesion(prix="0.00")
    email_tape = un_email_que_personne_n_a()

    reponse = poster_une_adhesion(client_connecte(), adhesion.tarif, email_tape)

    assert reponse.status_code == 403
    assert not TibilletUser.objects.filter(email=email_tape).exists()
    assert not Membership.objects.filter(price=adhesion.tarif).exists()


# --------------------------------------------------------------------------
# Ce qui reste public, ce qui reste réservé aux admins
# / What stays public, what stays admin-only
# --------------------------------------------------------------------------


def test_la_liste_partielle_des_evenements_reste_publique_en_post(lieu):
    """`partial_list` est un POST public (les filtres de l'agenda) : le contrôle des
    permissions se fait sur le nom de l'action, jamais sur la méthode HTTP.
    / partial_list is a public POST: permissions go by action name, not HTTP method."""
    reponse = client_connecte().post(
        "/event/partial_list/", {"search": "concert"}, **EN_TETE_HTMX
    )

    assert reponse.status_code == 200


def test_la_fiche_admin_d_un_evenement_reste_reservee_aux_admins_du_lieu(lieu):
    """`admin_show_event_detail` montre les noms et emails des acheteurs : refusé à un
    anonyme ET à une personne connectée qui n'est pas admin du lieu.
    / The admin event detail stays tenant-admin only."""
    concert = creer_evenement_avec_tarif()
    adresse = f"/event/{concert.evenement.pk}/admin_show_event_detail/"

    reponse_anonyme = client_connecte().get(adresse)
    reponse_non_admin = client_connecte(creer_utilisateur()).get(adresse)

    assert reponse_anonyme.status_code == 403
    assert reponse_non_admin.status_code == 403


# --------------------------------------------------------------------------
# Une personne connectée réserve et adhère pour elle-même
# / A logged-in person books and joins for themselves
# --------------------------------------------------------------------------


def test_un_connecte_qui_poste_l_email_d_un_autre_reserve_pour_lui_meme(lieu):
    """L'email posté est remplacé par celui du compte connecté : la réservation est à son
    nom, validée tout de suite (`FA`), et aucun compte n'est créé à l'autre email.
    / The posted email is replaced by the account's: booking in their name, FA."""
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import Product, Reservation

    acheteur = creer_utilisateur()
    atelier = creer_evenement_avec_tarif(categorie=Product.FREERES)
    email_d_un_autre = un_email_que_personne_n_a()

    reponse = poster_une_reservation(
        client_connecte(acheteur), atelier.evenement, atelier.tarif, email_d_un_autre
    )

    reservation = Reservation.objects.get(event=atelier.evenement)
    assert reservation.user_commande == acheteur
    assert reservation.status == Reservation.FREERES_USERACTIV
    assert not TibilletUser.objects.filter(email=email_d_un_autre).exists()
    # Réservation gratuite : redirection htmx vers « Mes réservations ».
    # / Free booking: htmx redirect to "My bookings".
    assert reponse.status_code == 200
    assert reponse["HX-Redirect"].endswith("/my_account/my_reservations/")


def test_un_connecte_qui_poste_l_email_d_un_autre_adhere_pour_lui_meme(
    lieu, django_capture_on_commit_callbacks
):
    """Adhésion à 0 € postée avec l'email d'un autre : l'adhésion est au nom du compte
    connecté, aucun compte n'est créé à l'autre email.
    / Free membership posted with another email: membership in the account's name."""
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import Membership

    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="0.00")
    email_d_un_autre = un_email_que_personne_n_a()

    with django_capture_on_commit_callbacks(execute=True):
        reponse = poster_une_adhesion(
            client_connecte(acheteur), adhesion.tarif, email_d_un_autre
        )

    assert reponse.status_code == 200
    adhesion_creee = Membership.objects.get(price=adhesion.tarif)
    assert adhesion_creee.user == acheteur
    assert adhesion_creee.status == Membership.ONCE
    assert not TibilletUser.objects.filter(email=email_d_un_autre).exists()


def test_un_connecte_non_adherent_n_obtient_pas_le_tarif_adherent_avec_l_email_d_un_adherent(
    lieu,
):
    """Tarif réservé aux adhérents. Une personne connectée, sans adhésion, poste l'email
    d'un adhérent : l'email est remplacé par le sien, le tarif lui est refusé.
    / Members-only price: posting a member's email does not unlock it."""
    from BaseBillet.models import Reservation

    adherent = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00")
    creer_une_adhesion_active(adherent, adhesion)
    concert = creer_evenement_avec_tarif(prix="5.00")
    concert.tarif.adhesions_obligatoires.add(adhesion.produit)
    non_adherent = creer_utilisateur()

    reponse = poster_une_reservation(
        client_connecte(non_adherent), concert.evenement, concert.tarif, adherent.email
    )

    # Refus de validation : redirection htmx avec un message, pas un refus d'accès.
    # / Validation refusal: htmx redirect with a message, not an access denial.
    assert reponse.status_code == 200
    assert not Reservation.objects.filter(event=concert.evenement).exists()
    assert not lieu.stripe.mock_create.called


# --------------------------------------------------------------------------
# Ce qu'un anonyme voit dans les formulaires
# / What an anonymous visitor sees in the forms
# --------------------------------------------------------------------------


def test_un_anonyme_voit_seulement_se_connecter_pour_reserver(lieu):
    """Page d'un événement : un seul bouton « Se connecter pour réserver », qui ouvre
    #loginPanel et demande le retour avec le panneau de réservation ouvert. Ni champ
    email, ni bouton « Payer maintenant ». Le panneau de connexion mène au guichet.
    / Event page: a single "log in to book" button, no email field, no submit button."""
    concert = creer_evenement_avec_tarif()

    reponse = client_connecte().get(f"/event/{concert.evenement.slug}/")

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="booking-login"' in contenu
    assert (
        f'data-next="/event/{concert.evenement.slug}/?openbookingPanel=true"' in contenu
    )
    assert 'data-testid="booking-submit"' not in contenu
    assert 'data-testid="booking-email"' not in contenu
    assert 'data-testid="login-guichet"' in contenu
    assert 'id="loginForm"' not in contenu


def test_un_connecte_voit_son_email_en_lecture_seule_et_payer_maintenant(lieu):
    """Page d'un événement, personne connectée : son email en lecture seule, le bouton
    « Payer maintenant », pas de bouton de connexion.
    / Logged-in: read-only email, submit button, no login button."""
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif()

    reponse = client_connecte(acheteur).get(f"/event/{concert.evenement.slug}/")

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="booking-submit"' in contenu
    assert f'id="booking-email" name="email" value="{acheteur.email}"' in contenu
    assert 'data-testid="booking-login"' not in contenu


def test_un_anonyme_voit_seulement_se_connecter_pour_adherer(lieu):
    """Formulaire d'adhésion : un seul bouton « Se connecter pour adhérer », ni champ
    email ni bouton d'envoi.
    / Membership form: a single "log in to join" button, no email field, no submit."""
    adhesion = creer_adhesion(prix="15.00")

    reponse = client_connecte().get(
        f"/memberships/{adhesion.produit.uuid}/", **EN_TETE_HTMX
    )

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="membership-login"' in contenu
    assert 'data-testid="membership-submit"' not in contenu
    assert 'data-testid="membership-email"' not in contenu
