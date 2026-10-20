"""
Réservation de ressource à validation manuelle : la demande.
/ Resource booking with manual validation: the request.

LOCALISATION : tests/pytest/test_booking_validation_manuelle.py

Spec : TECH_DOC/SESSIONS/BOOKING/SPEC.md (fiches A à D).

Un tarif de ressource qui porte `manual_validation` ne crée pas une réservation
payée tout de suite : il crée une DEMANDE (statut ADMIN_WAITING). La vente et sa
ligne existent déjà, avec le montant à payer plus tard. Il n'y a ni session Stripe
ni encaissement. Le créneau reste occupé pendant l'attente.
/ A manual validation price creates a REQUEST (ADMIN_WAITING): sale and line exist,
no Stripe session, no settlement, and the slot stays taken.

Code testé :
- booking/booking_engine.py : validate_new_booking, get_existing_bookings_for_resource
- Administration/admin/products.py : ResourcePriceInline, ResourcePriceInlineForm
- booking/views.py : _book_get, _book_post, cancel_confirm, pay, admin_accept, admin_refuse
- Administration/admin/resources.py : BookingAdmin.changeform_view (panneau d'actions)
- booking/booking_engine.py : get_checkout_stripe, expirer_la_session_stripe_ouverte
- BaseBillet/triggers.py : trigger_C
- booking/models.py : Booking.annulation_possible, Booking.cancel_and_refund_booking
- booking/tasks.py : send_booking_request_admin, send_booking_request_user,
  send_booking_cancellation_user, send_booking_accepted_user, send_booking_refused_user
- BaseBillet/views.py : MyAccount.my_bookings

Chaque test est marqué `django_db` : pytest-django l'exécute dans une transaction annulée.
/ Every test runs in a rolled-back transaction.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_booking_validation_manuelle.py -v
"""

import re
from decimal import Decimal

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    creer_ressource_avec_tarif,
    creer_utilisateur,
    noms_des_taches,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les tâches et signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5)."""
    from django.utils import translation

    yield
    translation.deactivate()


def creer_ressource_a_validation_manuelle(prix="12.00", prix_libre=False):
    """
    Une ressource d'une place, dont le tarif horaire est à validation manuelle.
    / A one-seat resource whose hourly price needs manual validation.
    """
    location = creer_ressource_avec_tarif(prix=prix, capacite=1, prix_libre=prix_libre)
    location.tarif.manual_validation = True
    location.tarif.save()
    return location


def demander_le_creneau(location, personne, custom_amount=None):
    """
    Réserve le premier créneau d'une heure de la ressource, comme la réservation directe.
    / Books the resource's first one-hour slot, like the direct booking flow.
    """
    from BaseBillet.models import PaymentMethod
    from booking.booking_engine import validate_new_booking

    return validate_new_booking(
        resource=location.ressource,
        start_datetime=location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=1,
        member=personne,
        price=location.tarif,
        external_payment_method=PaymentMethod.STRIPE_NOFED,
        custom_amount=custom_amount,
    )


# ---------------------------------------------------------------------------
# La demande / The request
# ---------------------------------------------------------------------------


def test_un_tarif_a_validation_manuelle_cree_une_demande_sans_paiement_stripe(tenant):
    from BaseBillet.models import Paiement_stripe
    from booking.models import Booking

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()

        est_cree, booking, checkout_url = demander_le_creneau(
            location, creer_utilisateur()
        )

        assert est_cree is True
        assert booking.status == Booking.ADMIN_WAITING
        assert checkout_url is None
        assert not Paiement_stripe.objects.filter(booking=booking).exists()


def test_la_demande_ouvre_sa_vente_et_garde_sa_ligne_au_montant_du_creneau(tenant):
    from BaseBillet.models import LigneArticle
    from BaseBillet.models_vente import Vente

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle(prix="12.00")

        _est_cree, booking, _checkout_url = demander_le_creneau(
            location, creer_utilisateur()
        )

        ligne_du_creneau = booking.lignearticles.get()
        assert ligne_du_creneau.status == LigneArticle.CREATED
        assert ligne_du_creneau.amount == 1200
        assert ligne_du_creneau.vente.statut == Vente.Statut.EN_ATTENTE
        assert booking.to_pay() > 0


def test_la_demande_a_prix_libre_garde_le_montant_choisi(tenant):
    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle(prix="5.00", prix_libre=True)

        _est_cree, booking, _checkout_url = demander_le_creneau(
            location, creer_utilisateur(), custom_amount=Decimal("20.00")
        )

        assert booking.lignearticles.get().amount == 2000


# ---------------------------------------------------------------------------
# Le créneau retenu / The held slot
# ---------------------------------------------------------------------------


def test_une_demande_en_attente_occupe_le_creneau(tenant):
    from booking.booking_engine import get_existing_bookings_for_resource

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()

        _est_cree, booking, _checkout_url = demander_le_creneau(
            location, creer_utilisateur()
        )

        reservations_qui_occupent = get_existing_bookings_for_resource(
            location.ressource
        )
        assert booking in reservations_qui_occupent


def test_une_deuxieme_demande_sur_le_meme_creneau_est_refusee(tenant):
    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()
        demander_le_creneau(location, creer_utilisateur())

        est_cree, message_d_erreur, _checkout_url = demander_le_creneau(
            location, creer_utilisateur()
        )

        assert est_cree is False
        assert "fully booked" in message_d_erreur or "complet" in message_d_erreur


# ---------------------------------------------------------------------------
# Garde-fou : jamais de demande dans une commande du panier
# / Guard: never a request inside a cart order
# ---------------------------------------------------------------------------


def test_une_demande_dans_une_commande_du_panier_leve_une_erreur(tenant):
    from BaseBillet.models import Commande
    from booking.booking_engine import validate_new_booking
    from booking.models import Booking

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()
        acheteur = creer_utilisateur()
        commande_du_panier = Commande.objects.create(
            user=acheteur,
            email_acheteur=acheteur.email,
            first_name="Ada",
            last_name="Lovelace",
        )

        with pytest.raises(ValueError, match="validation manuelle"):
            validate_new_booking(
                resource=location.ressource,
                start_datetime=location.debut_du_creneau,
                slot_duration_minutes=60,
                slot_count=1,
                member=acheteur,
                price=location.tarif,
                commande=commande_du_panier,
                create_checkout=False,
            )

        assert not Booking.objects.filter(commande=commande_du_panier).exists()


# ---------------------------------------------------------------------------
# Sans validation manuelle, rien ne change / Without manual validation, nothing changes
# ---------------------------------------------------------------------------


def test_un_tarif_gratuit_sans_validation_manuelle_reste_confirme_tout_de_suite(tenant):
    from BaseBillet.models import LigneArticle, PaymentMethod
    from BaseBillet.models_vente import Vente
    from booking.models import Booking

    with tenant_context(tenant):
        location = creer_ressource_avec_tarif(prix="0.00")

        _est_cree, booking, checkout_url = demander_le_creneau(
            location, creer_utilisateur(actif=True)
        )

        ligne_du_creneau = booking.lignearticles.get()
        assert checkout_url is None
        assert booking.status == Booking.FREERES_USERACTIV
        assert ligne_du_creneau.status == LigneArticle.VALID
        assert ligne_du_creneau.payment_method == PaymentMethod.FREE
        assert ligne_du_creneau.vente.statut == Vente.Statut.REGLEE


# ---------------------------------------------------------------------------
# Admin : le drapeau est réglable sur les tarifs d'une ressource
# / Admin: the flag can be set on a resource's prices
# ---------------------------------------------------------------------------


def test_l_inline_des_tarifs_de_ressource_propose_la_validation_manuelle(tenant):
    from Administration.admin.products import (
        ResourcePriceInline,
        ResourcePriceInlineForm,
    )

    with tenant_context(tenant):
        formulaire_de_tarif = ResourcePriceInlineForm()

    assert "manual_validation" in ResourcePriceInline.fields
    assert "manual_validation" in formulaire_de_tarif.fields
    assert "demande" in str(formulaire_de_tarif.fields["manual_validation"].help_text)


def test_l_inline_des_tarifs_de_ressource_ne_propose_ni_jauge_ni_maximum_par_personne():
    # Le moteur de réservation ne lit ni Price.stock ni Price.max_per_user :
    # les proposer laisserait croire à une limite qui n'existe pas.
    # / The booking engine ignores both fields: showing them would fake a limit.
    from Administration.admin.products import ResourcePriceInline

    champs_a_plat = []
    for champ_ou_ligne in ResourcePriceInline.fields:
        if isinstance(champ_ou_ligne, tuple):
            champs_a_plat.extend(champ_ou_ligne)
        else:
            champs_a_plat.append(champ_ou_ligne)

    assert "stock" not in champs_a_plat
    assert "max_per_user" not in champs_a_plat


# ---------------------------------------------------------------------------
# Fiche B : le parcours de la personne (formulaire, réponse, compte, annulation)
# / Card B: the person's flow (form, response, account, cancellation)
# ---------------------------------------------------------------------------

EN_TETE_HTMX = {"HTTP_HX_REQUEST": "true"}


def client_de_mon_compte(tenant, utilisateur):
    """
    Le client connecté, avec un compte actif et un portefeuille local.
    « Mon compte » demande un portefeuille à Fedow en HTTP si le compte n'en a pas
    (BaseBillet/views.py, MyAccount.dispatch) : on en pose un local avant, par update(),
    qui ne déclenche aucun signal (tests/PIEGES.md 12.17).
    / Logged-in client with an active account and a local wallet (no Fedow call).
    """
    from AuthBillet.models import TibilletUser, Wallet

    portefeuille_local = Wallet.objects.create(
        name=f"TEST_validation_manuelle portefeuille {utilisateur.pk}",
        origin=tenant,
    )
    TibilletUser.objects.filter(pk=utilisateur.pk).update(
        is_active=True, wallet=portefeuille_local
    )
    utilisateur.refresh_from_db()
    return client_connecte(utilisateur)


def envoyer_le_formulaire_du_creneau(client, location):
    """
    POST du formulaire du créneau (une heure), comme la popup de la ressource.
    / POSTs the slot form (one hour), like the resource popup.
    """
    from datetime import timedelta

    debut = location.debut_du_creneau
    fin = debut + timedelta(hours=1)
    return client.post(
        f"/booking/{location.ressource.pk}/book/",
        {
            "resource": str(location.ressource.pk),
            "price_uuid": str(location.tarif.uuid),
            "start_datetime": debut.replace(tzinfo=None).isoformat(),
            "end_time": fin.replace(tzinfo=None).isoformat(),
            "firstname": "Ada",
            "lastname": "Lovelace",
        },
        **EN_TETE_HTMX,
    )


def passer_le_delai_d_annulation(location):
    """
    Le créneau est dans deux jours : un délai de 1000 h est donc déjà dépassé.
    / The slot is in two days: a 1000 h deadline has already passed.
    """
    location.ressource.cancellation_deadline_hours = 1000
    location.ressource.save()


def test_le_formulaire_d_un_tarif_manuel_propose_d_envoyer_une_demande(tenant):
    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()
        client = client_connecte(creer_utilisateur())

        reponse = client.get(
            f"/booking/{location.ressource.pk}/book/",
            {
                "start_datetime": location.debut_du_creneau.replace(
                    tzinfo=None
                ).isoformat()
            },
            **EN_TETE_HTMX,
        )

        contenu = reponse.content.decode()
        assert reponse.status_code == 200
        bouton_radio_du_tarif = re.search(
            rf'<input id="price-{location.tarif.uuid}"[^>]*>', contenu
        ).group(0)
        assert 'data-manual-validation="true"' in bouton_radio_du_tarif
        assert 'data-testid="booking-send-request"' in contenu


def test_envoyer_la_demande_redirige_vers_mes_reservations_et_lance_les_deux_mails(
    tenant, django_capture_on_commit_callbacks
):
    from django.contrib.messages import get_messages
    from django.urls import reverse
    from django.utils import translation
    from booking.models import Booking

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()
        personne = creer_utilisateur()
        client = client_connecte(personne)

        with taches_celery_enregistrees() as taches_demandees:
            with django_capture_on_commit_callbacks(execute=True):
                reponse = envoyer_le_formulaire_du_creneau(client, location)

        demande = Booking.objects.get(user=personne, resource=location.ressource)
        assert demande.status == Booking.ADMIN_WAITING
        assert reponse["HX-Redirect"] == (
            reverse("my_account-my-bookings") + f"?new={demande.pk}"
        )
        assert sorted(noms_des_taches(taches_demandees)) == [
            "send_booking_request_admin",
            "send_booking_request_user",
        ]

        with translation.override("en"):
            message_attendu = translation.gettext(
                "Votre demande de réservation a été envoyée. "
                "Vous recevrez une confirmation ou une invitation à payer par mail."
            )
        messages_poses = [
            str(message) for message in get_messages(reponse.wsgi_request)
        ]
        assert messages_poses == [message_attendu]


def test_une_demande_en_attente_s_affiche_dans_mes_reservations_et_reste_annulable(
    tenant,
):
    from django.urls import reverse

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()
        passer_le_delai_d_annulation(location)
        personne = creer_utilisateur()
        client = client_de_mon_compte(tenant, personne)
        _est_cree, demande, _checkout_url = demander_le_creneau(location, personne)

        reponse = client.get(reverse("my_account-my-bookings"))

        contenu = reponse.content.decode()
        assert reponse.status_code == 200
        assert f'data-testid="booking-badge-request-{demande.pk}"' in contenu
        assert f'data-testid="booking-cancel-{demande.pk}"' in contenu


def test_retirer_une_demande_apres_le_delai_annule_la_vente_sans_rien_debiter(tenant):
    from django.contrib.messages import get_messages
    from django.utils import translation
    from BaseBillet.models import LigneArticle
    from BaseBillet.models_vente import Vente
    from booking.models import Booking

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()
        passer_le_delai_d_annulation(location)
        personne = creer_utilisateur()
        client = client_connecte(personne)
        _est_cree, demande, _checkout_url = demander_le_creneau(location, personne)

        with taches_celery_enregistrees() as taches_demandees:
            reponse = client.post(f"/booking/{demande.pk}/cancel/", **EN_TETE_HTMX)

        demande.refresh_from_db()
        ligne_du_creneau = demande.lignearticles.get()
        assert demande.status == Booking.USER_CANCELED
        assert ligne_du_creneau.status == LigneArticle.CANCELED
        assert ligne_du_creneau.vente.statut == Vente.Statut.ANNULEE
        assert noms_des_taches(taches_demandees) == ["send_booking_cancellation_user"]

        with translation.override("en"):
            message_attendu = translation.gettext(
                "Votre demande est annulée. Rien n'a été débité."
            )
        messages_poses = [
            str(message) for message in get_messages(reponse.wsgi_request)
        ]
        assert messages_poses == [message_attendu]


def test_une_reservation_confirmee_reste_bloquee_par_le_delai_d_annulation(tenant):
    from booking.models import Booking

    with tenant_context(tenant):
        location = creer_ressource_avec_tarif(prix="0.00")
        passer_le_delai_d_annulation(location)
        personne = creer_utilisateur(actif=True)
        client = client_connecte(personne)
        _est_cree, reservation, _checkout_url = demander_le_creneau(location, personne)

        with taches_celery_enregistrees():
            client.post(f"/booking/{reservation.pk}/cancel/", **EN_TETE_HTMX)

        reservation.refresh_from_db()
        assert reservation.status == Booking.FREERES_USERACTIV


# ---------------------------------------------------------------------------
# Fiche B : les mails / Card B: the emails
# ---------------------------------------------------------------------------


def test_le_mail_admin_part_aux_admins_du_lieu_avec_le_lien_vers_la_demande(tenant):
    from unittest.mock import patch
    from booking.tasks import send_booking_request_admin

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()
        administratrice = creer_utilisateur(prenom="Grace", nom="Hopper")
        administratrice.client_admin.add(tenant)
        _est_cree, demande, _checkout_url = demander_le_creneau(
            location, creer_utilisateur()
        )

        with patch("BaseBillet.tasks.send_email_generique") as envoi_du_mail:
            send_booking_request_admin(str(demande.pk))

        contexte_du_mail = envoi_du_mail.call_args.kwargs["context"]
        destinataires = envoi_du_mail.call_args.kwargs["email"]
        assert administratrice.email in destinataires
        assert (
            f"/admin/booking/booking/{demande.pk}/change/"
            in contexte_du_mail["button"]["url"]
        )


def test_le_mail_de_la_personne_part_a_son_adresse(tenant):
    from unittest.mock import patch
    from booking.tasks import send_booking_request_user

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()
        personne = creer_utilisateur()
        _est_cree, demande, _checkout_url = demander_le_creneau(location, personne)

        with patch("BaseBillet.tasks.send_email_generique") as envoi_du_mail:
            send_booking_request_user(str(demande.pk))

        assert envoi_du_mail.call_args.kwargs["email"] == personne.email


def test_le_mail_d_annulation_d_une_demande_dit_que_rien_n_a_ete_debite(tenant):
    from unittest.mock import patch
    from django.utils import translation
    from booking.tasks import send_booking_cancellation_user

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()
        _est_cree, demande, _checkout_url = demander_le_creneau(
            location, creer_utilisateur()
        )
        demande.cancel_and_refund_booking()

        with patch("booking.tasks.CeleryMailerClass") as mailer:
            send_booking_cancellation_user(str(demande.pk), demande_non_payee=True)
            texte_attendu = translation.gettext(
                "Votre demande est annulée. Rien n'a été débité."
            )

        contexte_du_mail = mailer.call_args.kwargs["context"]
        assert contexte_du_mail["cancel_text"] == texte_attendu
        assert contexte_du_mail["refund_amount"] is None


# ---------------------------------------------------------------------------
# Fiche C : le paiement d'une demande validée
# / Card C: paying a validated request
# ---------------------------------------------------------------------------


@pytest.fixture
def lieu_et_stripe(tenant, mock_stripe):
    """
    Le lieu, avec la session Stripe et le catalogue Stripe simulés.
    / The venue, with the Stripe session and catalogue faked.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            yield mock_stripe


def demande_validee(location, personne):
    """
    Une demande que l'admin a acceptée (ADMIN_VALID), pas encore payée.
    update() ne déclenche aucun signal et n'envoie aucun mail.
    / A request accepted by the admin, not paid yet (update(): no signal).
    """
    from booking.models import Booking

    _est_cree, demande, _checkout_url = demander_le_creneau(location, personne)
    Booking.objects.filter(pk=demande.pk).update(status=Booking.ADMIN_VALID)
    demande.refresh_from_db()
    return demande


def test_payer_une_demande_validee_ouvre_stripe_et_garde_le_statut(lieu_et_stripe):
    from booking.models import Booking

    location = creer_ressource_a_validation_manuelle()
    personne = creer_utilisateur()
    demande = demande_validee(location, personne)

    reponse = client_connecte(personne).get(f"/booking/{demande.pk}/pay/")

    demande.refresh_from_db()
    assert reponse.status_code == 302
    assert reponse["Location"] == lieu_et_stripe.session.url
    assert demande.status == Booking.ADMIN_VALID
    assert demande.paiements.count() == 1


def test_une_session_encore_ouverte_est_reutilisee_sans_deuxieme_paiement(
    lieu_et_stripe,
):
    location = creer_ressource_a_validation_manuelle()
    personne = creer_utilisateur()
    demande = demande_validee(location, personne)
    client = client_connecte(personne)
    client.get(f"/booking/{demande.pk}/pay/")
    lieu_et_stripe.session.status = "open"

    reponse = client.get(f"/booking/{demande.pk}/pay/")

    assert reponse.status_code == 302
    assert reponse["Location"] == lieu_et_stripe.session.url
    assert demande.paiements.count() == 1
    assert lieu_et_stripe.mock_create.call_count == 1


def test_une_session_terminee_affiche_le_paiement_en_cours_sans_nouvelle_session(
    lieu_et_stripe,
):
    location = creer_ressource_a_validation_manuelle()
    personne = creer_utilisateur()
    demande = demande_validee(location, personne)
    client = client_connecte(personne)
    client.get(f"/booking/{demande.pk}/pay/")
    lieu_et_stripe.session.status = "complete"

    reponse = client.get(f"/booking/{demande.pk}/pay/")

    assert reponse.status_code == 200
    assert (
        'data-testid="booking-pay-info-paiement_en_cours"' in reponse.content.decode()
    )
    assert lieu_et_stripe.mock_create.call_count == 1


def test_une_reservation_deja_payee_affiche_la_page_deja_payee(lieu_et_stripe):
    from booking.models import Booking

    location = creer_ressource_a_validation_manuelle()
    personne = creer_utilisateur()
    demande = demande_validee(location, personne)
    Booking.objects.filter(pk=demande.pk).update(status=Booking.PAID_BY_USER)

    reponse = client_connecte(personne).get(f"/booking/{demande.pk}/pay/")

    assert reponse.status_code == 200
    assert 'data-testid="booking-pay-info-deja_payee"' in reponse.content.decode()
    assert lieu_et_stripe.mock_create.call_count == 0


def test_une_demande_refusee_rend_un_lien_plus_valable_en_409(lieu_et_stripe):
    from booking.models import Booking

    location = creer_ressource_a_validation_manuelle()
    personne = creer_utilisateur()
    demande = demande_validee(location, personne)
    Booking.objects.filter(pk=demande.pk).update(status=Booking.ADMIN_CANCELED)

    reponse = client_connecte(personne).get(f"/booking/{demande.pk}/pay/")

    assert reponse.status_code == 409
    assert lieu_et_stripe.mock_create.call_count == 0


def test_une_demande_pas_encore_validee_rend_la_page_d_attente_en_409(lieu_et_stripe):
    location = creer_ressource_a_validation_manuelle()
    personne = creer_utilisateur()
    _est_cree, demande, _checkout_url = demander_le_creneau(location, personne)

    reponse = client_connecte(personne).get(f"/booking/{demande.pk}/pay/")

    assert reponse.status_code == 409
    assert (
        'data-testid="booking-pay-info-en_attente_de_validation"'
        in reponse.content.decode()
    )
    assert lieu_et_stripe.mock_create.call_count == 0


def test_une_demande_validee_deja_reglee_n_ouvre_pas_stripe(lieu_et_stripe, tenant):
    from django.urls import reverse
    from BaseBillet.models import LigneArticle

    location = creer_ressource_a_validation_manuelle()
    personne = creer_utilisateur()
    demande = demande_validee(location, personne)
    demande.lignearticles.update(status=LigneArticle.VALID)

    reponse = client_connecte(personne).get(f"/booking/{demande.pk}/pay/")
    page_du_compte = client_de_mon_compte(tenant, personne).get(
        reverse("my_account-my-bookings")
    )

    assert 'data-testid="booking-pay-info-deja_payee"' in reponse.content.decode()
    assert lieu_et_stripe.mock_create.call_count == 0
    assert f'data-testid="booking-pay-{demande.pk}"' not in page_du_compte.content.decode()


def test_payer_sans_etre_connecte_renvoie_vers_la_connexion(lieu_et_stripe):
    from django.urls import reverse

    location = creer_ressource_a_validation_manuelle()
    demande = demande_validee(location, creer_utilisateur())

    reponse = client_connecte().get(f"/booking/{demande.pk}/pay/")

    assert reponse.status_code == 302
    assert reponse["Location"].startswith(reverse("connexion"))


def test_payer_la_demande_d_une_autre_personne_rend_404(lieu_et_stripe):
    location = creer_ressource_a_validation_manuelle()
    demande = demande_validee(location, creer_utilisateur())

    reponse = client_connecte(creer_utilisateur()).get(f"/booking/{demande.pk}/pay/")

    assert reponse.status_code == 404
    assert lieu_et_stripe.mock_create.call_count == 0


def test_mes_reservations_propose_de_payer_une_demande_validee(lieu_et_stripe, tenant):
    from django.urls import reverse

    location = creer_ressource_a_validation_manuelle()
    personne = creer_utilisateur()
    demande = demande_validee(location, personne)
    client = client_de_mon_compte(tenant, personne)

    reponse = client.get(reverse("my_account-my-bookings"))

    contenu = reponse.content.decode()
    assert f'data-testid="booking-badge-to-pay-{demande.pk}"' in contenu
    assert f'href="/booking/{demande.pk}/pay/"' in contenu


def test_retirer_une_demande_validee_ferme_la_session_stripe_ouverte(lieu_et_stripe):
    from unittest.mock import patch
    from BaseBillet.models import Paiement_stripe
    from booking.models import Booking

    location = creer_ressource_a_validation_manuelle()
    personne = creer_utilisateur()
    demande = demande_validee(location, personne)
    client = client_connecte(personne)
    client.get(f"/booking/{demande.pk}/pay/")

    with patch("stripe.checkout.Session.expire") as fermeture_de_la_session:
        with taches_celery_enregistrees():
            client.post(f"/booking/{demande.pk}/cancel/", **EN_TETE_HTMX)

    demande.refresh_from_db()
    assert demande.status == Booking.USER_CANCELED
    assert fermeture_de_la_session.call_args.args[0] == lieu_et_stripe.session.id
    assert demande.paiements.get().status == Paiement_stripe.EXPIRE


# ---------------------------------------------------------------------------
# Fiche C : un paiement qui arrive après une annulation
# / Card C: a payment arriving after a cancellation
# ---------------------------------------------------------------------------


def paiement_recu_pour(demande):
    """
    Ce que fait le retour de Stripe quand la ligne passe à « payée » : le déclencheur
    de la catégorie (trigger_C pour une ressource).
    / What Stripe's return does when the line becomes PAID: the category trigger.
    """
    from BaseBillet.triggers import TRIGGER_LigneArticlePaid_ActionByCategorie

    TRIGGER_LigneArticlePaid_ActionByCategorie(demande.lignearticles.get())


@pytest.mark.parametrize("statut_annule", ["CA", "UC"])
def test_un_paiement_recu_apres_l_annulation_ne_reactive_pas_la_reservation(
    tenant, caplog, statut_annule
):
    from booking.models import Booking

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()
        demande = demande_validee(location, creer_utilisateur())
        Booking.objects.filter(pk=demande.pk).update(status=statut_annule)
        demande.refresh_from_db()

        with caplog.at_level("ERROR"):
            paiement_recu_pour(demande)

        demande.refresh_from_db()
        assert demande.status == statut_annule
        assert "déjà annulé" in caplog.text


def test_un_paiement_recu_pour_une_demande_validee_la_passe_en_payee(tenant):
    from booking.models import Booking

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()
        demande = demande_validee(location, creer_utilisateur())

        paiement_recu_pour(demande)

        demande.refresh_from_db()
        assert demande.status == Booking.PAID_BY_USER


# ---------------------------------------------------------------------------
# Fiche D : la décision de l'admin
# / Card D: the admin's decision
# ---------------------------------------------------------------------------


def client_admin_du_lieu(tenant):
    """
    Un client connecté avec un compte actif, admin du lieu.
    / A logged-in client whose active account is a venue admin.
    """
    administratrice = creer_utilisateur(actif=True, prenom="Grace", nom="Hopper")
    administratrice.client_admin.add(tenant)
    return client_connecte(administratrice)


def test_accepter_une_demande_payante_la_valide_et_envoie_le_mail_apres_le_commit(
    lieu_et_stripe, tenant, django_capture_on_commit_callbacks
):
    from booking.models import Booking

    location = creer_ressource_a_validation_manuelle()
    _est_cree, demande, _checkout_url = demander_le_creneau(
        location, creer_utilisateur()
    )
    client = client_admin_du_lieu(tenant)

    with taches_celery_enregistrees() as taches_demandees:
        with django_capture_on_commit_callbacks(execute=False) as rappels_apres_commit:
            reponse = client.post(
                f"/booking/{demande.pk}/admin_accept/", **EN_TETE_HTMX
            )
        taches_avant_le_commit = noms_des_taches(taches_demandees)
        for rappel in rappels_apres_commit:
            rappel()

    demande.refresh_from_db()
    assert reponse["HX-Refresh"] == "true"
    assert demande.status == Booking.ADMIN_VALID
    assert taches_avant_le_commit == []
    assert noms_des_taches(taches_demandees) == ["send_booking_accepted_user"]


def test_accepter_une_demande_gratuite_la_confirme_et_encaisse_la_vente_a_zero(
    lieu_et_stripe, tenant, django_capture_on_commit_callbacks
):
    from BaseBillet.models import LigneArticle, PaymentMethod
    from BaseBillet.models_vente import Vente
    from booking.models import Booking

    location = creer_ressource_a_validation_manuelle(prix="0.00")
    _est_cree, demande, _checkout_url = demander_le_creneau(
        location, creer_utilisateur(actif=True)
    )
    client = client_admin_du_lieu(tenant)

    with taches_celery_enregistrees() as taches_demandees:
        with django_capture_on_commit_callbacks(execute=True):
            client.post(f"/booking/{demande.pk}/admin_accept/", **EN_TETE_HTMX)

    demande.refresh_from_db()
    ligne_du_creneau = demande.lignearticles.get()
    assert demande.status == Booking.FREERES_USERACTIV
    assert ligne_du_creneau.status == LigneArticle.VALID
    assert ligne_du_creneau.payment_method == PaymentMethod.FREE
    assert ligne_du_creneau.vente.statut == Vente.Statut.REGLEE
    assert noms_des_taches(taches_demandees) == ["send_booking_accepted_user"]


def test_un_double_clic_sur_valider_n_envoie_qu_un_mail(
    lieu_et_stripe, tenant, django_capture_on_commit_callbacks
):
    location = creer_ressource_a_validation_manuelle()
    _est_cree, demande, _checkout_url = demander_le_creneau(
        location, creer_utilisateur()
    )
    client = client_admin_du_lieu(tenant)

    with taches_celery_enregistrees() as taches_demandees:
        with django_capture_on_commit_callbacks(execute=True):
            client.post(f"/booking/{demande.pk}/admin_accept/", **EN_TETE_HTMX)
            client.post(f"/booking/{demande.pk}/admin_accept/", **EN_TETE_HTMX)

    assert noms_des_taches(taches_demandees) == ["send_booking_accepted_user"]


def test_renvoyer_le_lien_d_une_demande_validee_renvoie_le_mail(
    lieu_et_stripe, tenant, django_capture_on_commit_callbacks
):
    from booking.models import Booking

    location = creer_ressource_a_validation_manuelle()
    demande = demande_validee(location, creer_utilisateur())
    client = client_admin_du_lieu(tenant)

    with taches_celery_enregistrees() as taches_demandees:
        with django_capture_on_commit_callbacks(execute=True):
            client.post(
                f"/booking/{demande.pk}/admin_accept/",
                {"renvoyer_le_lien": "true"},
                **EN_TETE_HTMX,
            )

    demande.refresh_from_db()
    assert demande.status == Booking.ADMIN_VALID
    assert noms_des_taches(taches_demandees) == ["send_booking_accepted_user"]


def test_refuser_une_demande_validee_annule_tout_et_libere_le_creneau(
    lieu_et_stripe, tenant, django_capture_on_commit_callbacks
):
    from unittest.mock import patch
    from BaseBillet.models import LigneArticle, Paiement_stripe
    from BaseBillet.models_vente import Vente
    from booking.booking_engine import get_existing_bookings_for_resource
    from booking.models import Booking

    location = creer_ressource_a_validation_manuelle()
    personne = creer_utilisateur()
    demande = demande_validee(location, personne)
    client_connecte(personne).get(f"/booking/{demande.pk}/pay/")
    client = client_admin_du_lieu(tenant)

    with patch("stripe.checkout.Session.expire") as fermeture_de_la_session:
        with taches_celery_enregistrees() as taches_demandees:
            with django_capture_on_commit_callbacks(execute=True):
                client.post(
                    f"/booking/{demande.pk}/admin_refuse/",
                    {"motif_du_refus": "  Salle réservée pour un atelier.  "},
                    **EN_TETE_HTMX,
                )

    demande.refresh_from_db()
    ligne_du_creneau = demande.lignearticles.get()
    assert demande.status == Booking.ADMIN_CANCELED
    assert demande.annulee_le is not None
    assert demande.motif_du_refus == "Salle réservée pour un atelier."
    assert fermeture_de_la_session.call_count == 1
    assert demande.paiements.get().status == Paiement_stripe.EXPIRE
    assert ligne_du_creneau.status == LigneArticle.CANCELED
    assert ligne_du_creneau.vente.statut == Vente.Statut.ANNULEE
    assert demande not in get_existing_bookings_for_resource(location.ressource)
    assert noms_des_taches(taches_demandees) == ["send_booking_refused_user"]


def test_une_reservation_payee_ne_se_refuse_pas(lieu_et_stripe, tenant):
    from booking.models import Booking

    location = creer_ressource_a_validation_manuelle()
    demande = demande_validee(location, creer_utilisateur())
    Booking.objects.filter(pk=demande.pk).update(status=Booking.PAID_BY_USER)
    client = client_admin_du_lieu(tenant)

    with taches_celery_enregistrees() as taches_demandees:
        client.post(f"/booking/{demande.pk}/admin_refuse/", **EN_TETE_HTMX)

    demande.refresh_from_db()
    assert demande.status == Booking.PAID_BY_USER
    assert noms_des_taches(taches_demandees) == []


@pytest.mark.parametrize("action_admin", ["admin_accept", "admin_refuse"])
def test_une_personne_qui_n_est_pas_admin_recoit_403(lieu_et_stripe, action_admin):
    from booking.models import Booking

    location = creer_ressource_a_validation_manuelle()
    personne = creer_utilisateur(actif=True)
    _est_cree, demande, _checkout_url = demander_le_creneau(location, personne)

    reponse = client_connecte(personne).post(
        f"/booking/{demande.pk}/{action_admin}/", **EN_TETE_HTMX
    )

    demande.refresh_from_db()
    assert reponse.status_code == 403
    assert demande.status == Booking.ADMIN_WAITING


def test_la_fiche_admin_d_une_demande_affiche_le_panneau_valider_refuser(
    lieu_et_stripe, admin_client
):
    from django.urls import reverse

    location = creer_ressource_a_validation_manuelle()
    _est_cree, demande, _checkout_url = demander_le_creneau(
        location, creer_utilisateur()
    )

    reponse = admin_client.get(
        reverse("staff_admin:booking_booking_change", args=[demande.pk])
    )

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="booking-action-accept"' in contenu
    assert 'data-testid="booking-action-refuse"' in contenu


def test_la_fiche_admin_d_une_reservation_payee_n_a_pas_de_panneau(
    lieu_et_stripe, admin_client
):
    from django.urls import reverse
    from booking.models import Booking

    location = creer_ressource_a_validation_manuelle()
    demande = demande_validee(location, creer_utilisateur())
    Booking.objects.filter(pk=demande.pk).update(status=Booking.PAID_BY_USER)

    reponse = admin_client.get(
        reverse("staff_admin:booking_booking_change", args=[demande.pk])
    )

    assert reponse.status_code == 200
    assert 'data-testid="booking-actions-panel"' not in reponse.content.decode()


# ---------------------------------------------------------------------------
# Fiche D : les mails de décision / Card D: decision emails
# ---------------------------------------------------------------------------


def test_le_mail_d_acceptation_d_une_demande_payante_porte_le_lien_de_paiement(tenant):
    from unittest.mock import patch
    from booking.tasks import send_booking_accepted_user

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()
        demande = demande_validee(location, creer_utilisateur())

        with patch("BaseBillet.tasks.send_email_generique") as envoi_du_mail:
            send_booking_accepted_user(str(demande.pk))

        contexte_du_mail = envoi_du_mail.call_args.kwargs["context"]
        assert contexte_du_mail["button"]["url"].endswith(f"/booking/{demande.pk}/pay/")


def test_le_mail_d_acceptation_d_une_demande_gratuite_n_a_pas_de_lien_de_paiement(
    tenant,
):
    from unittest.mock import patch
    from booking.models import Booking
    from booking.tasks import send_booking_accepted_user

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle(prix="0.00")
        _est_cree, demande, _checkout_url = demander_le_creneau(
            location, creer_utilisateur()
        )
        Booking.objects.filter(pk=demande.pk).update(status=Booking.FREERES_USERACTIV)

        with patch("BaseBillet.tasks.send_email_generique") as envoi_du_mail:
            send_booking_accepted_user(str(demande.pk))

        contexte_du_mail = envoi_du_mail.call_args.kwargs["context"]
        assert "/pay/" not in contexte_du_mail["button"]["url"]


def test_le_mail_de_refus_reprend_le_motif_sans_le_marquer_sur(tenant):
    from unittest.mock import patch
    from booking.models import Booking
    from booking.tasks import send_booking_refused_user

    with tenant_context(tenant):
        location = creer_ressource_a_validation_manuelle()
        _est_cree, demande, _checkout_url = demander_le_creneau(
            location, creer_utilisateur()
        )
        Booking.objects.filter(pk=demande.pk).update(
            status=Booking.ADMIN_CANCELED, motif_du_refus="Salle fermée <b>ce jour</b>"
        )

        with patch("BaseBillet.tasks.send_email_generique") as envoi_du_mail:
            send_booking_refused_user(str(demande.pk))

        contexte_du_mail = envoi_du_mail.call_args.kwargs["context"]
        assert "Salle fermée <b>ce jour</b>" in str(contexte_du_mail["main_text_3"])
        assert "main_text_2" not in contexte_du_mail
