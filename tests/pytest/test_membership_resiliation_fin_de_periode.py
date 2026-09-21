"""
Une adhesion resiliee court jusqu'a la fin de la periode deja payee.
/ A cancelled membership runs until the end of the paid period.

LOCALISATION : tests/pytest/test_membership_resiliation_fin_de_periode.py

Quand l'adherent arrete son prelevement automatique, Stripe est mis en
`cancel_at_period_end=True` : le debit s'arrete, mais la periode deja payee
court jusqu'a son terme. TiBillet doit dire la meme chose, sinon on coupe
l'adhesion de quelqu'un qui a paye jusqu'au 15 du mois.

Les deux statuts d'annulation ne sont PAS symetriques, et c'est voulu :

- CANCELED (l'adherent) : le renouvellement s'arrete, l'acces court jusqu'a
  la deadline. Rien n'est rembourse.
- ADMIN_CANCELED (un gestionnaire) : effet immediat. L'action admin archive
  l'adhesion et peut emettre un avoir (BaseBillet/views.py, action
  d'annulation) : laisser l'acces reviendrait a offrir l'adhesion.

/ CANCELED (member-initiated) keeps access until the deadline; ADMIN_CANCELED
is immediate because the admin action archives and may issue a credit note.
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
def adhesion_de_test(tenant):
    """Un produit d'adhesion limite a 1 par personne, son tarif, et un adherent.

    Nettoie tout a la fin : la suite tourne sur la base dev, pas sur une base
    de test jetable.
    / Cleans up: the suite runs on the dev database, not a throwaway one.
    """
    suffixe = str(uuid_module.uuid4())[:8]

    with tenant_context(tenant):
        produit = Product.objects.create(
            name=f"TEST resiliation {suffixe}",
            categorie_article=Product.ADHESION,
            max_per_user=1,
        )
        tarif = Price.objects.create(
            product=produit,
            name="Mensuel",
            prix=10,
            subscription_type=Price.MONTH,
            recurring_payment=True,
            max_per_user=1,
        )
        adherent = TibilletUser.objects.create(
            email=f"test-resiliation-{suffixe}@tibillet.test",
            username=f"test-resiliation-{suffixe}@tibillet.test",
        )

        yield tenant, tarif, adherent

        Membership.objects.filter(user=adherent).delete()
        adherent.delete()
        tarif.delete()
        try:
            produit.delete()
        except Exception:
            # django-stdimage plante dans son post_delete quand le produit n'a
            # pas d'image (cf. tests/PIEGES.md 10.1). Le produit de test reste
            # alors en base : sans consequence, son nom porte un uuid unique.
            # / django-stdimage crashes on image-less products; harmless here.
            pass


def _creer_adhesion(tarif, adherent, statut, deadline):
    """Cree une adhesion deja payee, dans le statut et l'echeance demandes.
    / Creates an already-paid membership with the given status and deadline."""
    return Membership.objects.create(
        user=adherent,
        price=tarif,
        status=statut,
        last_contribution=timezone.localtime() - timedelta(days=5),
        deadline=deadline,
    )


def test_une_adhesion_resiliee_reste_valide_jusqu_a_sa_deadline(adhesion_de_test):
    """Le coeur du sujet : resilier n'est pas expirer.
    / The point: cancelling is not expiring."""
    tenant, tarif, adherent = adhesion_de_test

    with tenant_context(tenant):
        adhesion = _creer_adhesion(
            tarif,
            adherent,
            Membership.CANCELED,
            timezone.localtime() + timedelta(days=20),
        )

        assert adhesion.is_valid() is True, (
            "Une adhesion resiliee dont la periode payee court encore doit "
            "rester valide : l'adherent a paye jusqu'a sa deadline."
        )


def test_une_adhesion_resiliee_et_echue_n_est_plus_valide(adhesion_de_test):
    """Passe la deadline, la resiliation produit bien une adhesion terminee.
    / Past the deadline, a cancelled membership is over."""
    tenant, tarif, adherent = adhesion_de_test

    with tenant_context(tenant):
        adhesion = _creer_adhesion(
            tarif,
            adherent,
            Membership.CANCELED,
            timezone.localtime() - timedelta(days=1),
        )

        assert adhesion.is_valid() is False, (
            "Une adhesion resiliee dont la deadline est passee doit etre invalide."
        )


def test_une_annulation_admin_coupe_l_acces_immediatement(adhesion_de_test):
    """ADMIN_CANCELED n'est PAS aligne sur CANCELED, et c'est volontaire :
    l'action admin archive l'adhesion et peut emettre un avoir.
    / ADMIN_CANCELED is deliberately immediate: the admin action archives the
    membership and may issue a credit note."""
    tenant, tarif, adherent = adhesion_de_test

    with tenant_context(tenant):
        adhesion = _creer_adhesion(
            tarif,
            adherent,
            Membership.ADMIN_CANCELED,
            timezone.localtime() + timedelta(days=20),
        )

        assert adhesion.is_valid() is False, (
            "Une annulation administrative doit couper l'acces immediatement, "
            "meme si la deadline est dans le futur : un avoir a pu etre emis."
        )


def test_une_adhesion_resiliee_ne_bloque_pas_une_nouvelle_adhesion(adhesion_de_test):
    """Resilier puis re-adherer doit rester possible tout de suite.

    max_per_user exclut les annulees au niveau SQL (Price.max_per_user_reached),
    independamment de is_valid(). Ce test verrouille le fait qu'assouplir
    is_valid() pour les resiliations n'enferme personne.
    / Cancelling then re-subscribing must stay possible: max_per_user excludes
    cancelled memberships in SQL, independently of is_valid().
    """
    tenant, tarif, adherent = adhesion_de_test

    with tenant_context(tenant):
        _creer_adhesion(
            tarif,
            adherent,
            Membership.CANCELED,
            timezone.localtime() + timedelta(days=20),
        )

        assert tarif.max_per_user_reached(adherent) is False, (
            "Une adhesion resiliee ne doit jamais bloquer une nouvelle "
            "adhesion, meme si sa periode payee court encore."
        )
