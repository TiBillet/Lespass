"""
Réservation de ressource à validation manuelle : la demande.
/ Resource booking with manual validation: the request.

LOCALISATION : tests/pytest/test_booking_validation_manuelle.py

Spec : TECH_DOC/SESSIONS/BOOKING/SPEC.md (fiche A).

Un tarif de ressource qui porte `manual_validation` ne crée pas une réservation
payée tout de suite : il crée une DEMANDE (statut ADMIN_WAITING). La vente et sa
ligne existent déjà, avec le montant à payer plus tard. Il n'y a ni session Stripe
ni encaissement. Le créneau reste occupé pendant l'attente.
/ A manual validation price creates a REQUEST (ADMIN_WAITING): sale and line exist,
no Stripe session, no settlement, and the slot stays taken.

Code testé :
- booking/booking_engine.py : validate_new_booking, get_existing_bookings_for_resource
- Administration/admin/products.py : ResourcePriceInline, ResourcePriceInlineForm

Chaque test est marqué `django_db` : pytest-django l'exécute dans une transaction annulée.
/ Every test runs in a rolled-back transaction.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_booking_validation_manuelle.py -v
"""

from decimal import Decimal

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import creer_ressource_avec_tarif, creer_utilisateur

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
            user=acheteur, email_acheteur=acheteur.email, first_name="Ada", last_name="Lovelace"
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
