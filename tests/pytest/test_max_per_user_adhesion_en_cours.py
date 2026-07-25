"""
max_per_user compte les adhesions engagees mais pas encore payees.
/ max_per_user counts committed but unpaid memberships.

LOCALISATION : tests/pytest/test_max_per_user_adhesion_en_cours.py

Une adhesion n'obtient sa deadline qu'au paiement (BaseBillet.triggers TRIGGER_A).
Les statuts de Membership.STATUTS_EN_COURS (ADMIN_WAITING, ADMIN_VALID,
PAYMENT_PENDING) n'en ont donc pas, et doivent malgre tout compter dans
max_per_user : sinon la personne relance une adhesion et declenche un 2e
prelevement pendant que le premier est en cours de validation bancaire (SEPA).

WAITING_PAYMENT ne doit PAS compter : c'est l'etat d'un checkout Stripe ouvert, et
rien ne purge les paniers abandonnes. Le compter bloquerait a vie une personne
ayant ferme l'onglet Stripe. Le dernier test verrouille ce comportement.
/ WAITING_PAYMENT must NOT count: abandoned Stripe carts are never purged.
"""

import uuid as uuid_module
from datetime import timedelta

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import Membership, Price, Product

pytestmark = pytest.mark.django_db


@pytest.fixture
def produit_adhesion_limite_a_une(tenant):
    """Un produit d'adhesion limite a 1 par personne, avec son tarif et un user.

    Nettoie tout a la fin : la suite tourne sur la base dev, pas sur une base de
    test jetable.
    / Cleans up: the suite runs on the dev database, not a throwaway one.
    """
    suffixe = str(uuid_module.uuid4())[:8]

    with tenant_context(tenant):
        produit = Product.objects.create(
            name=f"TEST maxperuser {suffixe}",
            categorie_article=Product.ADHESION,
            max_per_user=1,
        )
        tarif = Price.objects.create(
            product=produit,
            name="Normal",
            prix=10,
            subscription_type=Price.YEAR,
            max_per_user=1,
        )
        adherent = TibilletUser.objects.create(
            email=f"test-maxperuser-{suffixe}@tibillet.test",
            username=f"test-maxperuser-{suffixe}@tibillet.test",
        )

        yield produit, tarif, adherent

        Membership.objects.filter(user=adherent).delete()
        adherent.delete()
        tarif.delete()
        try:
            produit.delete()
        except Exception:
            # django-stdimage plante dans son post_delete quand le produit n'a
            # pas d'image, ce qui est le cas ici (cf. tests/PIEGES.md 10.1).
            # Le produit de test reste alors en base : sans consequence, son nom
            # porte un uuid unique et aucun autre test ne le lit.
            # / django-stdimage crashes in its post_delete when the product has
            # no image (see tests/PIEGES.md 10.1). The test product then stays in
            # the database: harmless, its name carries a unique uuid.
            pass


@pytest.mark.parametrize(
    "statut_en_cours",
    [Membership.PAYMENT_PENDING, Membership.ADMIN_VALID, Membership.ADMIN_WAITING],
)
def test_adhesion_en_cours_sans_deadline_atteint_la_limite(
    tenant, produit_adhesion_limite_a_une, statut_en_cours
):
    """Une adhesion engagee et sans deadline compte dans max_per_user."""
    produit, tarif, adherent = produit_adhesion_limite_a_une

    with tenant_context(tenant):
        # deadline=None : le paiement n'est pas alle au bout, TRIGGER_A n'a pas
        # pose de deadline.
        # / deadline=None: payment never completed, so TRIGGER_A set no deadline.
        Membership.objects.create(
            user=adherent,
            price=tarif,
            status=statut_en_cours,
            deadline=None,
        )

        assert produit.max_per_user_reached(user=adherent) is True, (
            f"Une adhesion en {statut_en_cours} ne compte pas : la personne peut "
            f"en relancer une seconde et declencher un 2e prelevement."
        )
        assert tarif.max_per_user_reached(user=adherent) is True, (
            f"Le tarif ne compte pas l'adhesion en {statut_en_cours}."
        )


def test_adhesion_annulee_ne_compte_pas(tenant, produit_adhesion_limite_a_une):
    """Une adhesion annulee ne bloque pas une nouvelle adhesion."""
    produit, tarif, adherent = produit_adhesion_limite_a_une

    with tenant_context(tenant):
        Membership.objects.create(
            user=adherent,
            price=tarif,
            status=Membership.ADMIN_CANCELED,
            deadline=timezone.now() + timedelta(days=30),
        )

        assert produit.max_per_user_reached(user=adherent) is False
        assert tarif.max_per_user_reached(user=adherent) is False


def test_panier_stripe_abandonne_ne_bloque_pas_a_vie(
    tenant, produit_adhesion_limite_a_une
):
    """WAITING_PAYMENT ne compte pas : un panier abandonne ne verrouille personne.

    Rien ne purge les adhesions restees en WAITING_PAYMENT. Les compter
    empecherait definitivement d'adherer apres une simple fermeture d'onglet.
    / Nothing purges WAITING_PAYMENT memberships; counting them would lock the
      person out forever after merely closing the Stripe tab.
    """
    produit, tarif, adherent = produit_adhesion_limite_a_une

    with tenant_context(tenant):
        Membership.objects.create(
            user=adherent,
            price=tarif,
            status=Membership.WAITING_PAYMENT,
            deadline=None,
        )

        assert produit.max_per_user_reached(user=adherent) is False, (
            "Un panier Stripe abandonne bloque la personne a vie."
        )
        assert tarif.max_per_user_reached(user=adherent) is False, (
            "Un panier Stripe abandonne bloque la personne a vie."
        )
