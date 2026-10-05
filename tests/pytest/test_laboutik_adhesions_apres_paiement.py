"""
Adhesions actives affichees sur l'ecran de succes d'un paiement cashless.
/ Active memberships shown on the cashless payment success screen.

LOCALISATION : tests/pytest/test_laboutik_adhesions_apres_paiement.py

Code teste / Tested code :
- laboutik/views.py : _adhesions_actives_de_la_carte()
- laboutik/views.py : _adhesions_a_afficher_apres_paiement()
  (reglage LaboutikConfiguration.show_membership_after_payment)
- laboutik/templates/laboutik/partial/hx_return_payment_success.html

La carte est remplacee par un objet simple : les fonctions ne lisent que carte.user.
CarteCashless est en SHARED_APPS (schema public), inutile de la creer ici.
/ The card is a plain object: the helpers only read carte.user.

Chaque test est marque `django_db` : pytest-django l'execute dans une transaction annulee.
/ Every test runs in a rolled-back transaction.

Lancer / Run : make test ARGS="tests/pytest/test_laboutik_adhesions_apres_paiement.py"
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    creer_adhesion,
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
    Le lieu `lespass`, avec Stripe (catalogue) et Celery simules pendant tout le test.
    / The `lespass` venue, with the Stripe catalogue and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees():
                yield SimpleNamespace(tenant=tenant)


def regler_l_affichage_des_adhesions(active):
    """Active ou desactive le reglage laboutik. / Turns the laboutik setting on or off."""
    from laboutik.models import LaboutikConfiguration

    configuration_laboutik = LaboutikConfiguration.get_solo()
    configuration_laboutik.show_membership_after_payment = active
    configuration_laboutik.save()


def carte_d_un_adherent(statut=None):
    """
    Cree un utilisateur avec une adhesion valide un an, et renvoie une carte a son nom.
    / Creates a user with a membership valid for one year, returns a card in their name.

    :param statut: statut de l'adhesion (par defaut, celui du modele)
    :return: (carte, adhesion)
    """
    from BaseBillet.models import Membership

    adhesion_produit = creer_adhesion(prix="15.00")
    adherent = creer_utilisateur(prenom="Élodie", nom="Bérénice")
    champs_de_l_adhesion = {
        "user": adherent,
        "price": adhesion_produit.tarif,
        "first_name": "Élodie",
        "last_name": "Bérénice",
        "deadline": timezone.now() + timedelta(days=365),
    }
    if statut is not None:
        champs_de_l_adhesion["status"] = statut
    adhesion = Membership.objects.create(**champs_de_l_adhesion)

    carte = SimpleNamespace(user=adherent)
    return carte, adhesion


def test_une_carte_anonyme_n_a_aucune_adhesion_active(lieu):
    """Carte sans titulaire : liste vide. / Card without holder: empty list."""
    from laboutik.views import _adhesions_actives_de_la_carte

    carte_anonyme = SimpleNamespace(user=None)

    assert _adhesions_actives_de_la_carte(carte_anonyme) == []


def test_l_adhesion_valide_du_titulaire_est_renvoyee(lieu):
    """Une adhesion en cours est renvoyee. / A running membership is returned."""
    from laboutik.views import _adhesions_actives_de_la_carte

    carte, adhesion = carte_d_un_adherent()

    assert _adhesions_actives_de_la_carte(carte) == [adhesion]


def test_l_adhesion_annulee_par_l_admin_n_est_pas_renvoyee(lieu):
    """Annulation administrative : effet immediat. / Admin cancellation is immediate."""
    from BaseBillet.models import Membership
    from laboutik.views import _adhesions_actives_de_la_carte

    carte, _adhesion = carte_d_un_adherent(statut=Membership.ADMIN_CANCELED)

    assert _adhesions_actives_de_la_carte(carte) == []


def test_reglage_desactive_aucune_adhesion_apres_paiement(lieu):
    """Reglage off (defaut) : rien a afficher. / Setting off (default): nothing to show."""
    from laboutik.views import _adhesions_a_afficher_apres_paiement

    regler_l_affichage_des_adhesions(active=False)
    carte, _adhesion = carte_d_un_adherent()

    assert _adhesions_a_afficher_apres_paiement(carte) == []


def test_reglage_active_les_adhesions_sont_renvoyees_apres_paiement(lieu):
    """Reglage on : les adhesions actives sont renvoyees. / Setting on: memberships returned."""
    from laboutik.views import _adhesions_a_afficher_apres_paiement

    regler_l_affichage_des_adhesions(active=True)
    carte, adhesion = carte_d_un_adherent()

    assert _adhesions_a_afficher_apres_paiement(carte) == [adhesion]


def test_ecran_de_succes_affiche_les_adhesions_actives(lieu):
    """
    Avec des adhesions, l'ecran de succes montre leur nom et leur fin.
    Le bloc est hors du cadre de la carte : il s'affiche meme sans solde a montrer.
    / With memberships, the success screen shows their name and end date,
    even when there is no balance to show.
    """
    carte, adhesion = carte_d_un_adherent()

    html = render_to_string(
        "laboutik/partial/hx_return_payment_success.html",
        {
            "payment": {"moyen_paiement": "nfc", "total": 1500, "given_sum": 0},
            "cartes_apres_paiement": [],
            "adhesions_actives": [adhesion],
        },
    )

    assert 'data-testid="paiement-succes-adhesions"' in html
    assert 'data-testid="paiement-succes-adhesion-1"' in html
    assert adhesion.price.product.name in html
    assert adhesion.deadline.strftime("%d/%m/%Y") in html


def test_ecran_de_succes_sans_adhesion_n_affiche_pas_le_bloc():
    """Liste vide (reglage off) : pas de bloc. / Empty list (setting off): no block."""
    html = render_to_string(
        "laboutik/partial/hx_return_payment_success.html",
        {
            "payment": {"moyen_paiement": "nfc", "total": 1500, "given_sum": 0},
            "cartes_apres_paiement": [],
            "adhesions_actives": [],
        },
    )

    assert 'data-testid="paiement-succes-adhesions"' not in html
