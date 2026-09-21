"""
Annuler une adhesion depuis l'admin doit pouvoir resilier l'abonnement Stripe.

LOCALISATION : tests/pytest/test_admin_annulation_abonnement_stripe.py

Jusqu'ici, l'annulation administrative posait ADMIN_CANCELED sans jamais parler
a Stripe : l'abonnement continuait de prelever le membre. Pire, au prelevement
suivant, le webhook `invoice.paid` retrouvait la fiche et le trigger la repassait
en AUTO avec une nouvelle echeance — une adhesion annulee, et peut-etre
remboursee par avoir, redevenait active toute seule.

Deux protections, testees ici :

1. La modal d'annulation propose de resilier l'abonnement, et seulement sur une
   adhesion en prelevement automatique.
2. Une garde dans BaseBillet.triggers : un paiement ne reactive jamais une
   adhesion ADMIN_CANCELED. C'est le filet quand l'appel a Stripe a echoue —
   cet echec est volontairement non bloquant, donc silencieux.

/ Cancelling a membership from the admin must be able to cancel the Stripe
subscription. Two protections: the modal's checkbox, and a guard in the trigger
so a payment never revives an admin-cancelled membership.
"""

import uuid as uuid_module
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import Membership, Price, Product

pytestmark = pytest.mark.django_db


@pytest.fixture
def adhesion_en_prelevement(tenant):
    """Une adhesion AUTO avec un identifiant d'abonnement Stripe simule.
    / An AUTO membership with a simulated Stripe subscription id."""
    suffixe = str(uuid_module.uuid4())[:8]

    with tenant_context(tenant):
        produit = Product.objects.create(
            name=f"TEST annul stripe {suffixe}",
            categorie_article=Product.ADHESION,
        )
        tarif = Price.objects.create(
            product=produit,
            name="Mensuel",
            prix=Decimal("10.00"),
            subscription_type=Price.MONTH,
            recurring_payment=True,
        )
        adherent = TibilletUser.objects.create(
            email=f"test-annul-{suffixe}@tibillet.test",
            username=f"test-annul-{suffixe}@tibillet.test",
        )
        adhesion = Membership.objects.create(
            user=adherent,
            price=tarif,
            status=Membership.AUTO,
            stripe_id_subscription=f"sub_test_{suffixe}",
            first_contribution=timezone.localtime() - timedelta(days=30),
            last_contribution=timezone.localtime(),
            deadline=timezone.localtime() + timedelta(days=30),
        )

        yield tenant, adhesion, adherent

        Membership.objects.filter(user=adherent).delete()
        adherent.delete()
        tarif.delete()
        try:
            produit.delete()
        except Exception:
            # django-stdimage plante dans son post_delete sans image
            # (cf. tests/PIEGES.md 10.1) : sans consequence, nom unique.
            pass


def _patcher_stripe():
    """Neutralise les deux appels sortants de la vue.

    `get_stripe_connect_account()` n'est pas un simple getter : sans compte
    Connect enregistre, il en CREE un chez Stripe (BaseBillet/models.py). Le
    patcher n'est pas une commodite, c'est une precaution.
    / Neutralises both outgoing calls. get_stripe_connect_account() CREATES a
    Stripe account when none is stored, so patching it is a safety measure.
    """
    return (
        patch("stripe.Subscription.modify"),
        patch(
            "BaseBillet.models.Configuration.get_stripe_connect_account",
            return_value="acct_test",
        ),
    )


# ---------------------------------------------------------------------------
# La modal
# ---------------------------------------------------------------------------


def test_la_case_de_resiliation_est_proposee_sur_une_adhesion_en_prelevement(
    admin_client, adhesion_en_prelevement
):
    """Sur une adhesion AUTO, la modal propose de resilier l'abonnement."""
    tenant, adhesion, _adherent = adhesion_en_prelevement

    reponse = admin_client.get(f"/memberships/{adhesion.pk}/cancel/")

    assert reponse.status_code == 200, reponse.status_code
    contenu = reponse.content.decode()
    assert "membership-cancel-resilier-stripe" in contenu, (
        "La case de resiliation de l'abonnement Stripe doit etre proposee sur "
        "une adhesion en prelevement automatique."
    )


def test_la_case_est_absente_sur_une_adhesion_sans_prelevement(
    admin_client, adhesion_en_prelevement
):
    """Sur une adhesion ONCE, la case n'a pas lieu d'etre : rien a resilier."""
    tenant, adhesion, _adherent = adhesion_en_prelevement

    with tenant_context(tenant):
        adhesion.status = Membership.ONCE
        adhesion.save(update_fields=["status"])

    reponse = admin_client.get(f"/memberships/{adhesion.pk}/cancel/")

    assert reponse.status_code == 200, reponse.status_code
    assert "membership-cancel-resilier-stripe" not in reponse.content.decode(), (
        "La case ne doit pas apparaitre sur une adhesion sans prelevement "
        "automatique : l'appel a Stripe echouerait pour rien."
    )


# ---------------------------------------------------------------------------
# L'annulation
# ---------------------------------------------------------------------------


def test_case_cochee_l_abonnement_stripe_est_resilie_en_fin_de_periode(
    admin_client, adhesion_en_prelevement
):
    """Case cochee : Stripe est appele avec cancel_at_period_end.

    La periode deja payee court jusqu'a son terme — TiBillet ne rembourse
    jamais automatiquement. / The already-paid period runs to its end.
    """
    tenant, adhesion, _adherent = adhesion_en_prelevement
    patch_modify, patch_connect = _patcher_stripe()

    with patch_modify as stripe_modify, patch_connect:
        admin_client.post(
            f"/memberships/{adhesion.pk}/cancel/",
            {"with_credit_note": "0", "resilier_abonnement_stripe": "1"},
        )

    assert stripe_modify.called, (
        "Stripe n'a pas ete appele alors que la case de resiliation etait cochee."
    )
    _args, kwargs = stripe_modify.call_args
    assert kwargs.get("cancel_at_period_end") is True, (
        f"L'abonnement doit etre resilie en fin de periode, pas immediatement "
        f"(kwargs recus : {kwargs})."
    )

    with tenant_context(tenant):
        adhesion.refresh_from_db()
        assert adhesion.status == Membership.ADMIN_CANCELED


def test_case_decochee_stripe_n_est_pas_appele(admin_client, adhesion_en_prelevement):
    """Case decochee : aucune resiliation. Le navigateur n'envoie alors rien."""
    tenant, adhesion, _adherent = adhesion_en_prelevement
    patch_modify, patch_connect = _patcher_stripe()

    with patch_modify as stripe_modify, patch_connect:
        admin_client.post(
            f"/memberships/{adhesion.pk}/cancel/",
            {"with_credit_note": "0"},
        )

    assert not stripe_modify.called, (
        "Stripe ne doit pas etre appele quand la case n'est pas cochee."
    )

    with tenant_context(tenant):
        adhesion.refresh_from_db()
        assert adhesion.status == Membership.ADMIN_CANCELED


def test_un_echec_stripe_n_empeche_jamais_l_annulation(
    admin_client, adhesion_en_prelevement
):
    """Stripe injoignable : l'adhesion est annulee quand meme.

    L'appel reseau ne doit jamais faire perdre l'annulation deja enregistree.
    L'echec part en ERROR (alerte Sentry) et un humain resilie a la main.
    / A Stripe outage must never lose the cancellation already recorded.
    """
    tenant, adhesion, _adherent = adhesion_en_prelevement
    _patch_modify, patch_connect = _patcher_stripe()

    with patch("stripe.Subscription.modify", side_effect=Exception("Stripe down")), patch_connect:
        admin_client.post(
            f"/memberships/{adhesion.pk}/cancel/",
            {"with_credit_note": "0", "resilier_abonnement_stripe": "1"},
        )

    with tenant_context(tenant):
        adhesion.refresh_from_db()
        assert adhesion.status == Membership.ADMIN_CANCELED, (
            "Un echec Stripe a fait perdre l'annulation : c'est exactement ce "
            "que le try/except doit empecher."
        )


# ---------------------------------------------------------------------------
# La garde du trigger
# ---------------------------------------------------------------------------


def test_un_paiement_ne_reactive_jamais_une_adhesion_annulee_par_un_admin(
    adhesion_en_prelevement,
):
    """Le filet de securite : un prelevement tardif ne ressuscite pas la fiche.

    Arrive quand l'abonnement tourne encore : case decochee, ou appel a Stripe
    echoue (l'echec est non bloquant, donc silencieux).
    / The safety net: a late payment must not revive the membership.
    """
    from types import SimpleNamespace

    from BaseBillet.triggers import update_membership_state_after_stripe_paiement

    tenant, adhesion, _adherent = adhesion_en_prelevement

    with tenant_context(tenant):
        adhesion.status = Membership.ADMIN_CANCELED
        adhesion.save(update_fields=["status"])

        # La garde sort avant tout acces au tarif vendu : un double suffit.
        # Corollaire, verifie par mutation : si la garde disparait, la fonction
        # poursuit et bute sur ce double incomplet (AttributeError sur
        # `pricesold`) au lieu de rougir sur l'assertion metier ci-dessous. Le
        # test rougit dans les deux cas — c'est l'essentiel — mais le message
        # sera obscur : commencer par verifier que la garde est bien en place
        # dans BaseBillet/triggers.py.
        # / Corollary, checked by mutation: without the guard the function goes
        # on and trips on this deliberately minimal double. The test still
        # fails, but with an obscure message — check the guard first.
        paiement = SimpleNamespace(
            invoice_stripe="in_test_apres_annulation",
            subscription=adhesion.stripe_id_subscription,
        )
        ligne = SimpleNamespace(membership=adhesion, paiement_stripe=paiement)

        resultat = update_membership_state_after_stripe_paiement(ligne)

        assert resultat is adhesion, (
            "La garde doit retourner l'adhesion : l'appelant enchaine "
            "immediatement sur set_deadline()."
        )

        adhesion.refresh_from_db()
        assert adhesion.status == Membership.ADMIN_CANCELED, (
            "Une adhesion annulee par un admin a ete reactivee par un paiement."
        )
        assert adhesion.last_stripe_invoice == "in_test_apres_annulation", (
            "La facture doit etre enregistree malgre la garde : c'est la seule "
            "deduplication du webhook, sans elle un rejeu Stripe creerait une "
            "deuxieme vente."
        )
