"""
Une adhesion annulee par un gestionnaire n'affiche pas « A expiré dans 11 mois ».
/ A membership cancelled by a manager does not show "Expired in 11 months".

LOCALISATION : tests/pytest/test_membership_annulee_par_un_admin.py

Issue #450. L'annulation depuis l'admin (MembershipMVT.cancel) passe l'adhesion
en ADMIN_CANCELED et date l'annulation dans `annulee_le`. Elle garde la
`deadline` de la periode payee : c'est voulu (le commit qui la remettait a
maintenant a ete annule, c2ca56f). Mais la carte de « Mon compte » affichait
`{% translate 'Expired' %} {{ membership.deadline|naturaltime }}`, soit
« A expiré dans 11 mois » pour une date encore dans le futur.

La carte affiche maintenant « Annulée le <date> » pour ces adhesions, dans les
deux skins. Une adhesion vraiment echue garde « A expiré il y a ... ».

/ Issue #450. The admin cancel keeps the paid `deadline` on purpose and dates
the cancellation in `annulee_le`. The account card used to print "Expired" next
to a future deadline. It now prints "Cancelled on <date>" for these memberships,
in both skins. A truly lapsed membership keeps "Expired ... ago".
"""

import uuid as uuid_module
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.template.defaultfilters import date as filtre_date
from django.template.loader import render_to_string
from django.test import Client as ClientDjango
from django.utils import timezone
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import Membership, Price, Product

pytestmark = pytest.mark.django_db

GABARITS_CARTE = [
    "pages/classic/vues/compte/membership/membership_card.html",
    "pages/V2/vues/compte/membership/membership_card.html",
]


@pytest.fixture
def adhesion_annuelle(tenant):
    """Un produit d'adhesion annuelle, son tarif, et un adherent.

    Nettoie tout a la fin : la suite tourne sur la base dev.
    / Cleans up: the suite runs on the dev database.
    """
    suffixe = str(uuid_module.uuid4())[:8]

    with tenant_context(tenant):
        produit = Product.objects.create(
            name=f"TEST annulee admin {suffixe}",
            categorie_article=Product.ADHESION,
        )
        tarif = Price.objects.create(
            product=produit,
            name="Annuelle",
            prix=20,
            subscription_type=Price.YEAR,
        )
        adherent = TibilletUser.objects.create(
            email=f"test-annulee-admin-{suffixe}@tibillet.test",
            username=f"test-annulee-admin-{suffixe}@tibillet.test",
        )

        yield tenant, tarif, adherent

        Membership.objects.filter(user=adherent).delete()
        adherent.delete()
        tarif.hard_delete()
        try:
            produit.delete()
        except Exception:
            # django-stdimage plante sur un produit sans image (tests/PIEGES.md 10.1).
            # / django-stdimage crashes on image-less products; harmless here.
            pass


def _creer_adhesion(tarif, adherent, statut, deadline, annulee_le=None):
    """Cree une adhesion deja payee. / Creates an already-paid membership."""
    return Membership.objects.create(
        user=adherent,
        price=tarif,
        status=statut,
        last_contribution=timezone.localtime() - timedelta(days=5),
        deadline=deadline,
        annulee_le=annulee_le,
    )


def _rendre_la_carte(gabarit, adhesion):
    """Rend la carte comme la vue de « Mon compte » : `est_valide` pose avant.
    / Renders the card the way the account view does: `est_valide` set first."""
    adhesion.est_valide = adhesion.is_valid()
    return render_to_string(gabarit, {"membership": adhesion})


@pytest.mark.parametrize("gabarit", GABARITS_CARTE)
def test_la_carte_d_une_adhesion_annulee_par_un_admin_donne_la_date_d_annulation(
    adhesion_annuelle, gabarit
):
    """Deadline dans 11 mois, annulee aujourd'hui : « Annulée le <aujourd'hui> ».
    / Deadline 11 months away, cancelled today: "Cancelled on <today>"."""
    tenant, tarif, adherent = adhesion_annuelle

    with tenant_context(tenant):
        maintenant = timezone.now()
        adhesion = _creer_adhesion(
            tarif,
            adherent,
            Membership.ADMIN_CANCELED,
            timezone.localtime() + timedelta(days=330),
            annulee_le=maintenant,
        )
        contenu = _rendre_la_carte(gabarit, adhesion)

    assert "Annulée le" in contenu, contenu[-600:]
    assert filtre_date(maintenant) in contenu, contenu[-600:]
    assert "A expiré dans" not in contenu, (
        "Une adhesion annulee par un admin ne doit pas annoncer une expiration "
        "dans le futur (issue #450)."
    )


@pytest.mark.parametrize("gabarit", GABARITS_CARTE)
def test_une_annulation_admin_sans_date_reste_lisible(adhesion_annuelle, gabarit):
    """Annulation anterieure au champ `annulee_le` : « Annulé par un admin ».
    / Cancelled before `annulee_le` existed: "Cancelled by an admin"."""
    tenant, tarif, adherent = adhesion_annuelle

    with tenant_context(tenant):
        adhesion = _creer_adhesion(
            tarif,
            adherent,
            Membership.ADMIN_CANCELED,
            timezone.localtime() + timedelta(days=330),
        )
        contenu = _rendre_la_carte(gabarit, adhesion)

    assert "Annulé par un admin" in contenu, contenu[-600:]
    assert "A expiré dans" not in contenu, contenu[-600:]


@pytest.mark.parametrize("gabarit", GABARITS_CARTE)
def test_une_adhesion_echue_dit_toujours_a_expire(adhesion_annuelle, gabarit):
    """Le temoin : une adhesion payee et echue garde « A expiré il y a ... ».
    / Control: a paid, lapsed membership still says "Expired ... ago"."""
    tenant, tarif, adherent = adhesion_annuelle

    with tenant_context(tenant):
        adhesion = _creer_adhesion(
            tarif,
            adherent,
            Membership.ONCE,
            timezone.localtime() - timedelta(days=10),
        )
        contenu = _rendre_la_carte(gabarit, adhesion)

    assert "A expiré il y a" in contenu, contenu[-600:]
    assert "Annulée le" not in contenu, contenu[-600:]


def test_annuler_depuis_l_admin_puis_ouvrir_mon_compte(admin_client, adhesion_annuelle):
    """Le parcours de l'issue : l'admin annule, l'adherent ouvre son compte.
    / The issue's path: the admin cancels, the member opens their account."""
    tenant, tarif, adherent = adhesion_annuelle

    with tenant_context(tenant):
        adhesion = _creer_adhesion(
            tarif,
            adherent,
            Membership.ONCE,
            timezone.localtime() + timedelta(days=360),
        )
        # La vue de « Mon compte » itere sur `user.client_achat`.
        # / The account view loops over `user.client_achat`.
        adherent.client_achat.add(tenant)
        adherent.is_active = True
        adherent.save(update_fields=["is_active"])

    reponse = admin_client.post(
        f"/memberships/{adhesion.pk}/cancel/", {"with_credit_note": "0"}
    )
    # Succes : 204 + HX-Refresh (BaseBillet/views.py, MembershipMVT.cancel).
    # / Success: 204 + HX-Refresh.
    assert reponse.status_code == 204, reponse.status_code

    with tenant_context(tenant):
        adhesion.refresh_from_db()
        assert adhesion.status == Membership.ADMIN_CANCELED
        assert adhesion.annulee_le is not None
        # La deadline payee n'est pas touchee : c'est le choix du projet.
        # / The paid deadline is left alone: that is the project's choice.
        assert adhesion.deadline > timezone.now()

    navigateur = ClientDjango(HTTP_HOST="lespass.tibillet.localhost")
    navigateur.force_login(
        adherent, backend="django.contrib.auth.backends.ModelBackend"
    )
    # Toute page de compte demande son wallet a Fedow : appel neutralise.
    # / Every account page asks Fedow for a wallet: the call is stubbed.
    with patch("BaseBillet.views.FedowAPI", return_value=MagicMock()):
        page = navigateur.get("/my_account/membership/")

    assert page.status_code == 200, page.status_code
    contenu = page.content.decode()
    assert tarif.product.name in contenu, "L'adhesion n'apparait pas sur la page."
    assert "Annulée le" in contenu
    assert "A expiré dans" not in contenu, (
        "Apres une annulation admin, la page ne doit pas dire « A expiré dans 11 mois »."
    )
