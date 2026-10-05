"""
Exports des billets et des adhésions : colonnes des réponses au formulaire personnalisé.
/ Ticket and membership exports: custom form answer columns.

LOCALISATION : tests/pytest/test_export_reponses_formulaire.py

Code testé / Tested code :
- Administration/importers/reponses_formulaire_export.py (cles_des_reponses_a_exporter)
- Administration/importers/ticket_exporter.py (TicketExportResource.before_export)
- Administration/importers/membership_importers.py (MembershipExportResource.before_export)

Issue GitHub #290 :
- les questions sortent dans l'ordre d'affichage, pas par ordre alphabétique.

Chaque test est marqué `django_db` : pytest-django l'exécute dans une transaction annulée.
/ Every test runs in a rolled-back transaction.

Lancer / Run : make test ARGS="tests/pytest/test_export_reponses_formulaire.py"
"""

from types import SimpleNamespace

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_un_billet_deja_vendu,
    creer_utilisateur,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db


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


def ajouter_les_questions(produit):
    """
    Trois questions créées dans le DÉSORDRE : ordre d'affichage 3, 1, 2. Leurs libellés
    ne sont pas dans l'ordre alphabétique de l'affichage (l'ancien export triait ainsi).
    / Three questions created out of order; labels are not in alphabetical display order.

    :return: les questions dans l'ordre d'affichage
    """
    from BaseBillet.models import ProductFormField

    question_3 = ProductFormField.objects.create(
        product=produit, label="A - Régime alimentaire ?", field_type="ST", order=3,
    )
    question_1 = ProductFormField.objects.create(
        product=produit, label="C - Quel atelier ?", field_type="ST", order=1,
    )
    question_2 = ProductFormField.objects.create(
        product=produit, label="B - Comment êtes-vous venu ?", field_type="ST", order=2,
    )
    return [question_1, question_2, question_3]


def reponses_a_toutes_les_questions(questions):
    """Une réponse par question, rangée sous son libellé.
    / One answer per question, stored under its label."""
    reponses = {}
    for question in questions:
        reponses[question.label] = f"Réponse à {question.label}"
    return reponses


def colonnes_des_reponses_billets(billetterie):
    """Les colonnes de réponses de l'export des billets de l'événement.
    / Answer columns of the event's ticket export."""
    from Administration.importers.ticket_exporter import TicketExportResource
    from BaseBillet.models import Ticket

    billets = Ticket.objects.filter(reservation__event=billetterie.evenement)
    ressource = TicketExportResource()
    ressource.before_export(billets)
    return ressource._custom_form_keys


def preparer_un_billet_avec_reponses(reponses):
    """Un billet vendu, dont la réservation porte ces réponses.
    / A sold ticket whose reservation holds these answers."""
    from BaseBillet.models import Reservation

    billetterie = creer_evenement_avec_tarif(prix="10.00")
    questions = ajouter_les_questions(billetterie.produit)
    creer_un_billet_deja_vendu(creer_utilisateur(), billetterie)
    reservation = Reservation.objects.get(event=billetterie.evenement)
    reservation.custom_form = reponses(questions)
    reservation.save()
    return billetterie, questions


# --------------------------------------------------------------------------
# Billets / Tickets
# --------------------------------------------------------------------------


def test_billets_les_questions_sortent_dans_l_ordre_d_affichage(lieu):
    """Ordre d'affichage (1, 2, 3), pas l'ordre alphabétique des libellés (A, B, C).
    / Display order, not alphabetical label order."""
    billetterie, questions = preparer_un_billet_avec_reponses(reponses_a_toutes_les_questions)

    colonnes = colonnes_des_reponses_billets(billetterie)

    assert colonnes == [question.label for question in questions]


def test_billets_une_reponse_sans_question_sort_en_fin_de_tableau(lieu):
    """Question renommée ou supprimée : la réponse sort quand même, à la fin.
    / Renamed or deleted question: the answer is still exported, at the end."""
    def reponses_avec_une_orpheline(questions):
        reponses = reponses_a_toutes_les_questions(questions)
        reponses["Ancienne question supprimée"] = "Vieille réponse"
        return reponses

    billetterie, questions = preparer_un_billet_avec_reponses(reponses_avec_une_orpheline)

    colonnes = colonnes_des_reponses_billets(billetterie)

    assert colonnes[-1] == "Ancienne question supprimée"
    assert colonnes[:3] == [question.label for question in questions]


def test_billets_l_export_complet_contient_les_reponses(lieu):
    """De bout en bout : les titres et les cellules du fichier exporté.
    / End to end: headers and cells of the exported file."""
    from Administration.importers.ticket_exporter import TicketExportResource
    from BaseBillet.models import Ticket

    billetterie, questions = preparer_un_billet_avec_reponses(reponses_a_toutes_les_questions)
    billets = Ticket.objects.filter(reservation__event=billetterie.evenement)

    tableau = TicketExportResource().export(queryset=billets)

    ligne = dict(zip(tableau.headers, tableau[0]))
    assert ligne[questions[0].label] == f"Réponse à {questions[0].label}"


# --------------------------------------------------------------------------
# Adhésions / Memberships
# --------------------------------------------------------------------------


def preparer_une_adhesion_avec_reponses():
    """Une adhésion dont le produit a trois questions, toutes répondues.
    / A membership whose product has three answered questions."""
    from BaseBillet.models import Membership

    adhesion = creer_adhesion(prix="15.00")
    questions = ajouter_les_questions(adhesion.produit)
    Membership.objects.create(
        user=creer_utilisateur(),
        price=adhesion.tarif,
        custom_form=reponses_a_toutes_les_questions(questions),
    )
    return adhesion, questions


def colonnes_des_reponses_adhesions(adhesion):
    """Les colonnes de réponses de l'export des adhésions de ce produit.
    / Answer columns of this product's membership export."""
    from Administration.importers.membership_importers import MembershipExportResource
    from BaseBillet.models import Membership

    adhesions = Membership.objects.filter(price__product=adhesion.produit)
    ressource = MembershipExportResource()
    ressource.before_export(adhesions)
    return ressource._custom_form_keys


def test_adhesions_les_questions_sortent_dans_l_ordre_d_affichage(lieu):
    """Même règle que les billets.
    / Same rule as tickets."""
    adhesion, questions = preparer_une_adhesion_avec_reponses()

    colonnes = colonnes_des_reponses_adhesions(adhesion)

    assert colonnes == [question.label for question in questions]
