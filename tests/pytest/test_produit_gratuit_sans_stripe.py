"""
Tests du formulaire admin d'un produit : Stripe n'est exigé que pour un tarif payant.
/ Tests of the product admin form: Stripe is only required for a paid price.

LOCALISATION : tests/pytest/test_produit_gratuit_sans_stripe.py

RÈGLE MÉTIER TESTÉE
Un lieu sans compte Stripe actif (`Configuration.stripe_payouts_enabled` à False) peut
créer une adhésion dont tous les tarifs sont gratuits. Il ne peut pas créer une adhésion
avec un tarif payant : un prix au-dessus de 0 €, ou un prix libre.
La règle est dans `ProductAdminCustomForm.clean()` (Administration/admin/products.py).
Elle lit les tarifs envoyés par l'inline, dans `self.data`.
/ A venue without an active Stripe account can create a membership whose prices are all
free. It cannot create one with a paid price (above 0 €, or free price).

Issue GitHub : TiBillet/Lespass#501.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin. Stripe est
désactivé en mémoire par `configuration_modifiee()`, jamais enregistré
(tests/PIEGES.md 13.22). Le formulaire n'est jamais enregistré : on lit seulement ses
erreurs.
/ Rolled-back transaction per test. Stripe off in memory only. The form is never saved.

Lancer / Run : make test ARGS="tests/pytest/test_produit_gratuit_sans_stripe.py"
"""

import pytest
from django.http import QueryDict
from django.utils.translation import gettext
from django_tenants.utils import tenant_context

from Administration.admin.products import MembershipProductForm
from BaseBillet.models import Price, Product
from fabriques_panier import configuration_modifiee

pytestmark = pytest.mark.django_db

# Le message affiché quand Stripe manque. Même texte que dans le formulaire.
# / The message shown when Stripe is missing. Same text as in the form.
MESSAGE_STRIPE_NON_ACTIVE = (
    "Your Stripe account is not activated. To create paid items, please go to "
    "Settings/Stripe/Onboard."
)


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu_sans_stripe(tenant):
    """
    Le lieu `lespass`, avec un compte Stripe inactif, en mémoire seulement.
    / The `lespass` venue, with an inactive Stripe account, in memory only.
    """
    with tenant_context(tenant):
        with configuration_modifiee(stripe_payouts_enabled=False):
            yield tenant


def formulaire_d_adhesion_avec_un_tarif(prix, prix_libre=False):
    """
    Le formulaire admin d'une NOUVELLE adhésion, avec un seul tarif publié.
    Les clés `prices-0-...` sont celles que l'inline des tarifs envoie.
    / The admin form of a NEW membership, with a single published price.
    """
    donnees_envoyees = QueryDict(mutable=True)
    donnees_envoyees["name"] = "TEST adhésion sans Stripe"
    donnees_envoyees["categorie_article"] = Product.ADHESION
    donnees_envoyees["prices-TOTAL_FORMS"] = "1"
    donnees_envoyees["prices-0-name"] = "Tarif de test"
    donnees_envoyees["prices-0-prix"] = prix
    donnees_envoyees["prices-0-publish"] = "on"
    donnees_envoyees["prices-0-subscription_type"] = Price.YEAR
    if prix_libre:
        donnees_envoyees["prices-0-free_price"] = "on"
    return MembershipProductForm(data=donnees_envoyees)


def erreurs_generales_du_formulaire(formulaire):
    """Les erreurs qui ne visent aucun champ précis, en texte.
    / The errors that target no specific field, as text."""
    formulaire.is_valid()
    return [str(erreur) for erreur in formulaire.non_field_errors()]


def test_une_adhesion_a_zero_euro_est_acceptee_sans_stripe(lieu_sans_stripe):
    # Un tarif à 0 € ne passe jamais par Stripe : le lieu n'a pas besoin de compte.
    # / A 0 € price never goes through Stripe: the venue needs no account.
    formulaire = formulaire_d_adhesion_avec_un_tarif(prix="0")

    assert gettext(MESSAGE_STRIPE_NON_ACTIVE) not in erreurs_generales_du_formulaire(
        formulaire
    )


def test_une_adhesion_a_dix_euros_est_refusee_sans_stripe(lieu_sans_stripe):
    # Un tarif payant demande un compte Stripe actif.
    # / A paid price needs an active Stripe account.
    formulaire = formulaire_d_adhesion_avec_un_tarif(prix="10")

    assert gettext(MESSAGE_STRIPE_NON_ACTIVE) in erreurs_generales_du_formulaire(
        formulaire
    )


def test_une_adhesion_a_prix_libre_est_refusee_sans_stripe(lieu_sans_stripe):
    # Un prix libre peut être payant, même s'il affiche 0 € comme minimum.
    # / A free price can be paid, even with 0 € as its minimum.
    formulaire = formulaire_d_adhesion_avec_un_tarif(prix="0", prix_libre=True)

    assert gettext(MESSAGE_STRIPE_NON_ACTIVE) in erreurs_generales_du_formulaire(
        formulaire
    )
