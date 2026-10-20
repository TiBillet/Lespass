"""
Une réservation gratuite est validée tout de suite (`FA`), même pour un compte
pas encore activé.
/ A free reservation is validated at once (`FA`), even for a non-activated account.

LOCALISATION : tests/pytest/test_reservation_gratuite_validee_tout_de_suite.py
Code testé : BaseBillet/validators.py, TicketCreator (trois endroits posent le
statut gratuit) :
- `__init__` : réservation qui ne contient que des « réservations gratuites » ;
- `valider_une_reservation_a_zero_euro` : billets « payants » à 0 € ;
- `method_A` : place bénévole (événement ACTION sans produit).

RÈGLE MÉTIER :
Une réservation vient d'une personne connectée (compte forcément activé) ou de
l'API v2, à qui l'on fait confiance. Elle passe donc toujours en
`FREERES_USERACTIV` (FA) : la machine à états (BaseBillet/signals.py,
reservation_paid) active les billets, programme le mail des billets
(`ticket_celery_mailer`) et le webhook (`webhook_reservation`).
/ A reservation comes from a logged-in person or from the trusted API v2: always FA.

PIÈGES (tests/PIEGES.md) :
- Les tâches Celery sont interceptées (`taches_celery_enregistrees`) : un
  `.delay()` direct partirait vers le vrai broker.
- Catalogue Stripe simulé : un billet « payant » à 0 € appelle quand même le
  catalogue pour le tarif vendu (piège 12.16).
- `django_db` : tout est annulé en fin de test.
/ Celery tasks intercepted, Stripe catalogue faked, django_db rollback.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import QueryDict
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    creer_evenement_avec_tarif,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_reservation import creer_reservation_api

pytestmark = pytest.mark.django_db

RESERVATION_GRATUITE = "reservation_gratuite"
BILLET_PAYANT_A_ZERO_EURO = "billet_payant_a_zero_euro"


@pytest.fixture
def lieu(tenant, mock_stripe):
    """
    Le lieu `lespass`, avec Stripe et Celery simulés pendant tout le test.
    / The `lespass` venue, with Stripe and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(tenant=tenant, taches_demandees=taches_demandees)


def taches_demandees_pour(taches_demandees, nom_de_la_tache, reservation):
    """
    Nombre de fois où la tâche a été demandée pour cette réservation.
    / How many times the task was requested for this reservation.
    """
    nombre = 0
    for nom, arguments in taches_demandees:
        if nom != nom_de_la_tache:
            continue
        for argument in arguments:
            if str(argument) == str(reservation.pk):
                nombre += 1
    return nombre


@pytest.mark.parametrize(
    "sorte_de_billet", [RESERVATION_GRATUITE, BILLET_PAYANT_A_ZERO_EURO]
)
def test_api_v2_reservation_gratuite_d_un_compte_non_active_est_validee(
    lieu, api_client, auth_headers, sorte_de_billet
):
    """
    Par l'API v2, une réservation gratuite pour un email au compte non activé est
    `FA` : billets actifs, mail des billets et webhook programmés une fois.
    / Through API v2, a free reservation for a non-activated account is FA: tickets
    active, ticket mail and webhook scheduled once.
    """
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import Product, Reservation, Ticket

    if sorte_de_billet == RESERVATION_GRATUITE:
        evenement = creer_evenement_avec_tarif(categorie=Product.FREERES)
    else:
        evenement = creer_evenement_avec_tarif(prix="0.00")
    email = f"test+gratuite{identifiant_unique()}@mock.test"

    reponse = creer_reservation_api(
        api_client,
        auth_headers,
        str(evenement.evenement.uuid),
        str(evenement.tarif.uuid),
        email,
    )

    assert reponse.status_code == 201, reponse.content[:300]
    compte = TibilletUser.objects.get(email=email)
    assert not compte.is_active
    reservation = Reservation.objects.get(user_commande=compte)
    assert reservation.status == Reservation.FREERES_USERACTIV
    assert reservation.tickets.get().status == Ticket.NOT_SCANNED
    taches = lieu.taches_demandees
    assert taches_demandees_pour(taches, "ticket_celery_mailer", reservation) == 1
    assert taches_demandees_pour(taches, "webhook_reservation", reservation) == 1


def test_place_benevole_d_un_compte_non_active_est_validee(lieu):
    """
    Place bénévole (événement ACTION sans produit, réservation en un clic,
    `method_A`) pour un email au compte non activé : `FA`, mail des billets
    programmé. Ce cas n'existe pas dans l'API v2 (`reservedTicket` y est
    obligatoire) : on appelle le validateur partagé par le site, l'API et
    l'admin, avec une requête anonyme comme l'API.
    / Volunteer slot (ACTION event, no product) for a non-activated account: FA.
    """
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import Event, Reservation, SaleOrigin
    from BaseBillet.validators import ReservationValidator

    debut = timezone.now() + timedelta(days=7)
    evenement_benevole = Event.objects.create(
        name=f"TEST_gratuite benevolat {identifiant_unique()}",
        datetime=debut,
        end_datetime=debut + timedelta(hours=2),
        categorie=Event.ACTION,
        easy_reservation=True,
        published=True,
    )
    email = f"test+benevole{identifiant_unique()}@mock.test"
    donnees = QueryDict(mutable=True)
    donnees.update({"email": email, "event": str(evenement_benevole.pk)})
    requete_anonyme = SimpleNamespace(user=AnonymousUser(), data=donnees)

    validateur = ReservationValidator(
        data=donnees,
        context={"request": requete_anonyme, "sale_origin": SaleOrigin.LESPASS},
    )
    validateur.is_valid(raise_exception=True)

    assert not TibilletUser.objects.get(email=email).is_active
    reservation = Reservation.objects.get(pk=validateur.reservation.pk)
    assert reservation.status == Reservation.FREERES_USERACTIV
    taches = lieu.taches_demandees
    assert taches_demandees_pour(taches, "ticket_celery_mailer", reservation) == 1
