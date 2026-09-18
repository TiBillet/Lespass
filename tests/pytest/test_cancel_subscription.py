"""
Tests de la vue CancelSubscription (ApiBillet/views.py).
/ Tests for the CancelSubscription view (ApiBillet/views.py).

LOCALISATION : tests/pytest/test_cancel_subscription.py

POURQUOI CE FICHIER :
La vue rend un gabarit HTML quand la requete vient de HTMX.
Le chemin de ce gabarit vient de changer.
On verifie que chaque branche de la vue renvoie le bon code HTTP
et le bon contenu.
/ The view renders an HTML template for HTMX requests. That template
  path just changed. We check every branch returns the right status
  and the right content.

BRANCHES TESTEES / TESTED BRANCHES :
1. UUID invalide                  -> 400
2. Adhesion inconnue              -> 404
3. Adhesion non recurrente        -> 406 (JSON) / 200 (HTMX)
4. Pas d'identifiant Stripe       -> 409 (JSON) / 200 (HTMX)
5. Stripe renvoie une erreur      -> 400 (JSON) / 200 (HTMX)
6. Succes                         -> 200, statut passe a CANCELED

Lancer / Run :
  docker exec lespass_django poetry run pytest tests/pytest/test_cancel_subscription.py -v
"""

import uuid as uuid_module
from unittest.mock import patch

import pytest
import stripe
from django.test import Client as DjangoClient
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import Membership, Price, Product


# Le gabarit que la vue doit rendre pour les reponses HTMX.
# / The template the view must render for HTMX responses.
GABARIT_CARTE_ADHESION = "pages/classic/vues/compte/membership/membership_card.html"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def adherent_avec_adhesion_recurrente(tenant):
    """
    Cree un adherent avec une adhesion recurrente payee en ligne.
    / Creates a member with a recurring membership paid online.

    L'adhesion a le statut AUTO et un identifiant d'abonnement Stripe.
    C'est le seul cas ou la vue accepte d'arreter le prelevement.
    / The membership has AUTO status and a Stripe subscription id.
      This is the only case where the view accepts to stop the debit.
    """
    adresse = f"cancel-sub-{uuid_module.uuid4().hex[:8]}@tibillet.localhost"

    with tenant_context(tenant):
        utilisateur = TibilletUser.objects.create(
            email=adresse,
            username=adresse,
            is_active=True,
            email_valid=True,
        )
        produit = Product.objects.create(
            name=f"Adhesion test cancel {uuid_module.uuid4().hex[:6]}",
            categorie_article=Product.ADHESION,
        )
        tarif = Price.objects.create(
            product=produit,
            name="Mensuel",
            prix=10,
            recurring_payment=True,
            subscription_type=Price.MONTH,
        )
        adhesion = Membership.objects.create(
            user=utilisateur,
            price=tarif,
            status=Membership.AUTO,
            stripe_id_subscription="sub_test_cancel_1234",
            contribution_value=10,
        )

    yield {
        "utilisateur": utilisateur,
        "produit": produit,
        "tarif": tarif,
        "adhesion": adhesion,
    }

    # Nettoyage : la base de dev n'est pas remise a zero entre les tests.
    # / Cleanup: the dev database is not rolled back between tests.
    with tenant_context(tenant):
        Membership.objects.filter(pk=adhesion.pk).delete()
        Price.objects.filter(pk=tarif.pk).delete()
        Product.objects.filter(pk=produit.pk).delete()
        TibilletUser.objects.filter(pk=utilisateur.pk).delete()


def _navigateur_connecte(utilisateur):
    """Client Django connecte sur le tenant lespass.
    / Django client logged in on the lespass tenant."""
    client = DjangoClient(HTTP_HOST="lespass.tibillet.localhost")
    client.force_login(utilisateur)
    return client


def _poster(client, donnees, htmx=False):
    """POST sur /api/cancel_sub/, en HTMX ou en JSON.
    / POST to /api/cancel_sub/, either HTMX or JSON."""
    entetes = {}
    if htmx:
        entetes["HTTP_HX_REQUEST"] = "true"
    return client.post("/api/cancel_sub/", data=donnees, **entetes)


# --------------------------------------------------------------------------
# 1. UUID invalide / Invalid UUID
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_uuid_invalide_en_htmx_renvoie_400_et_du_html(
    adherent_avec_adhesion_recurrente,
):
    """Un UUID mal forme doit renvoyer 400 avec un bloc HTML d'erreur.
    / A malformed UUID must return 400 with an HTML error block."""
    client = _navigateur_connecte(adherent_avec_adhesion_recurrente["utilisateur"])

    reponse = _poster(client, {"uuid_membership": "pas-un-uuid"}, htmx=True)

    assert reponse.status_code == 400
    contenu = reponse.content.decode()
    assert "Invalid request." in contenu or "Requ" in contenu


@pytest.mark.django_db
def test_uuid_invalide_en_json_renvoie_400(adherent_avec_adhesion_recurrente):
    """En JSON, un UUID mal forme renvoie les erreurs du serializer.
    / In JSON, a malformed UUID returns the serializer errors."""
    client = _navigateur_connecte(adherent_avec_adhesion_recurrente["utilisateur"])

    reponse = _poster(client, {"uuid_membership": "pas-un-uuid"})

    assert reponse.status_code == 400
    assert "uuid_membership" in reponse.json()


# --------------------------------------------------------------------------
# 2. Adhesion inconnue / Unknown membership
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_adhesion_inconnue_renvoie_404(adherent_avec_adhesion_recurrente):
    """Un UUID valide mais inconnu renvoie 404.
    / A valid but unknown UUID returns 404."""
    client = _navigateur_connecte(adherent_avec_adhesion_recurrente["utilisateur"])

    reponse = _poster(client, {"uuid_membership": str(uuid_module.uuid4())}, htmx=True)

    assert reponse.status_code == 404


# --------------------------------------------------------------------------
# 3. Adhesion non recurrente / Non recurring membership
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_adhesion_non_recurrente_en_htmx_renvoie_200_et_le_message_d_erreur(
    tenant, adherent_avec_adhesion_recurrente
):
    """Une adhesion payee une seule fois ne peut pas etre annulee.
    / A one-off membership cannot be canceled."""
    adhesion = adherent_avec_adhesion_recurrente["adhesion"]
    with tenant_context(tenant):
        adhesion.status = Membership.ONCE
        adhesion.save(update_fields=["status"])

    client = _navigateur_connecte(adherent_avec_adhesion_recurrente["utilisateur"])
    reponse = _poster(client, {"uuid_membership": str(adhesion.uuid)}, htmx=True)

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert "No automatic renewal" in contenu or "renouvellement" in contenu
    # La carte de l'adhesion doit bien etre rendue autour du message.
    # / The membership card must be rendered around the message.
    assert f"membership-card-{adhesion.uuid}" in contenu


@pytest.mark.django_db
def test_adhesion_non_recurrente_en_json_renvoie_406(
    tenant, adherent_avec_adhesion_recurrente
):
    """En JSON, la meme situation renvoie 406.
    / In JSON, the same situation returns 406."""
    adhesion = adherent_avec_adhesion_recurrente["adhesion"]
    with tenant_context(tenant):
        adhesion.status = Membership.ONCE
        adhesion.save(update_fields=["status"])

    client = _navigateur_connecte(adherent_avec_adhesion_recurrente["utilisateur"])
    reponse = _poster(client, {"uuid_membership": str(adhesion.uuid)})

    assert reponse.status_code == 406


# --------------------------------------------------------------------------
# 4. Identifiant d'abonnement Stripe manquant / Missing Stripe subscription id
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_sans_identifiant_stripe_en_htmx_renvoie_200_et_le_message_d_erreur(
    tenant, adherent_avec_adhesion_recurrente
):
    """Sans identifiant Stripe, on ne peut rien annuler chez Stripe.
    / Without a Stripe id, nothing can be canceled at Stripe."""
    adhesion = adherent_avec_adhesion_recurrente["adhesion"]
    with tenant_context(tenant):
        adhesion.stripe_id_subscription = None
        adhesion.save(update_fields=["stripe_id_subscription"])

    client = _navigateur_connecte(adherent_avec_adhesion_recurrente["utilisateur"])
    reponse = _poster(client, {"uuid_membership": str(adhesion.uuid)}, htmx=True)

    assert reponse.status_code == 200
    # Le texte est traduit : on accepte les deux langues.
    # / The text is translated: we accept both languages.
    contenu = reponse.content.decode()
    assert (
        "Stripe subscription ID missing" in contenu
        or "abonnement Stripe manquant" in contenu
    )


@pytest.mark.django_db
def test_sans_identifiant_stripe_en_json_renvoie_409(
    tenant, adherent_avec_adhesion_recurrente
):
    """En JSON, la meme situation renvoie 409.
    / In JSON, the same situation returns 409."""
    adhesion = adherent_avec_adhesion_recurrente["adhesion"]
    with tenant_context(tenant):
        adhesion.stripe_id_subscription = None
        adhesion.save(update_fields=["stripe_id_subscription"])

    client = _navigateur_connecte(adherent_avec_adhesion_recurrente["utilisateur"])
    reponse = _poster(client, {"uuid_membership": str(adhesion.uuid)})

    assert reponse.status_code == 409


# --------------------------------------------------------------------------
# 5. Stripe renvoie une erreur / Stripe returns an error
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_erreur_stripe_en_htmx_renvoie_200_et_le_message_erreur(
    adherent_avec_adhesion_recurrente,
):
    """Si Stripe refuse, l'adhesion NE DOIT PAS changer de statut.
    / If Stripe refuses, the membership must NOT change status."""
    adhesion = adherent_avec_adhesion_recurrente["adhesion"]
    client = _navigateur_connecte(adherent_avec_adhesion_recurrente["utilisateur"])

    with patch(
        "stripe.Subscription.modify",
        side_effect=stripe.error.InvalidRequestError("no such subscription", None),
    ):
        reponse = _poster(client, {"uuid_membership": str(adhesion.uuid)}, htmx=True)

    assert reponse.status_code == 200
    # Le texte est traduit : on accepte les deux langues.
    # / The text is translated: we accept both languages.
    contenu = reponse.content.decode()
    assert "Stripe error" in contenu or "Erreur Stripe" in contenu

    adhesion.refresh_from_db()
    assert adhesion.status == Membership.AUTO, (
        "Le statut ne doit pas changer si Stripe echoue"
    )


# --------------------------------------------------------------------------
# 6. Succes / Success
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_annulation_reussie_en_htmx_renvoie_la_carte_et_passe_le_statut_a_canceled(
    adherent_avec_adhesion_recurrente,
):
    """Le chemin nominal : Stripe accepte, le statut passe a CANCELED.
    / Nominal path: Stripe accepts, status becomes CANCELED."""
    adhesion = adherent_avec_adhesion_recurrente["adhesion"]
    client = _navigateur_connecte(adherent_avec_adhesion_recurrente["utilisateur"])

    abonnement_stripe_simule = type(
        "AbonnementSimule",
        (),
        {
            "id": "sub_test_cancel_1234",
            "cancel_at_period_end": True,
        },
    )()

    with patch(
        "stripe.Subscription.modify", return_value=abonnement_stripe_simule
    ) as modifier:
        reponse = _poster(client, {"uuid_membership": str(adhesion.uuid)}, htmx=True)

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert f"membership-card-{adhesion.uuid}" in contenu
    assert "Automatic renewal turned off" in contenu or "renouvellement" in contenu

    # Stripe doit etre appele avec cancel_at_period_end=True, jamais avec delete.
    # / Stripe must be called with cancel_at_period_end=True, never delete.
    assert modifier.call_args.kwargs["cancel_at_period_end"] is True

    adhesion.refresh_from_db()
    assert adhesion.status == Membership.CANCELED


@pytest.mark.django_db
def test_annulation_reussie_en_json_renvoie_les_infos_stripe(
    adherent_avec_adhesion_recurrente,
):
    """En JSON, la reponse contient l'identifiant Stripe et le drapeau d'annulation.
    / In JSON, the response carries the Stripe id and the cancel flag."""
    adhesion = adherent_avec_adhesion_recurrente["adhesion"]
    client = _navigateur_connecte(adherent_avec_adhesion_recurrente["utilisateur"])

    abonnement_stripe_simule = type(
        "AbonnementSimule",
        (),
        {
            "id": "sub_test_cancel_1234",
            "cancel_at_period_end": True,
        },
    )()

    with patch("stripe.Subscription.modify", return_value=abonnement_stripe_simule):
        reponse = _poster(client, {"uuid_membership": str(adhesion.uuid)})

    assert reponse.status_code == 200
    donnees = reponse.json()
    assert donnees["stripe"]["id"] == "sub_test_cancel_1234"
    assert donnees["stripe"]["cancel_at_period_end"] is True


# --------------------------------------------------------------------------
# 7. Coherence entre la vue et le gabarit
# / Consistency between the view and the template
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_gabarit_rendu_par_la_vue_existe():
    """Le chemin du gabarit doit etre resolvable par Django.
    / The template path must be resolvable by Django."""
    from django.template.loader import get_template

    get_template(GABARIT_CARTE_ADHESION)


@pytest.mark.django_db
def test_le_bouton_arreter_le_prelevement_est_affiche_pour_une_adhesion_auto(
    adherent_avec_adhesion_recurrente,
):
    """
    Le bouton doit apparaitre sur une adhesion AUTO valide.
    / The button must appear on a valid AUTO membership.

    C'est la coherence entre la vue et le gabarit :
    la vue n'accepte que Membership.AUTO, donc le gabarit ne doit
    proposer le bouton que dans ce cas.
    / The view only accepts Membership.AUTO, so the template must only
      offer the button in that very case.
    """
    from django.template.loader import render_to_string
    from django.utils import timezone

    adhesion = adherent_avec_adhesion_recurrente["adhesion"]
    adhesion.last_contribution = timezone.now()
    adhesion.deadline = timezone.now() + timezone.timedelta(days=30)

    html = render_to_string(GABARIT_CARTE_ADHESION, {"membership": adhesion})

    assert f"membership-cancel-auto-{adhesion.uuid}" in html, (
        "Le gabarit n'affiche pas le bouton d'arret pour une adhesion AUTO "
        f"(status={adhesion.status!r}). Le gabarit teste 'A' en dur, "
        f"or Membership.AUTO vaut {Membership.AUTO!r}."
    )
