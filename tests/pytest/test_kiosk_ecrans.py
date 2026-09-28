"""
tests/pytest/test_kiosk_ecrans.py — Ecrans de la borne (refonte d'apres la maquette).
/ Kiosk screens (redesign from the mock-up).

Ce qui est teste / What is tested :
- lecture de la carte : solde affiche, modale « carte non enregistree » ;
- recapitulatif : le nouveau solde est calcule par le SERVEUR ;
- recharge : le solde avant recharge est enregistre sur le paiement ;
- ecran final : montant ajoute + nouveau solde (contexte_ecran_final) ;
- configuration : carte primaire, interrupteur, demarrage, borne en pause.

Fedow est toujours mocke (kiosk.carte.FedowAPI) : aucun appel reseau.
/ Fedow is always mocked: no network call.

Lancement / Run:
    poetry run pytest tests/pytest/test_kiosk_ecrans.py -v --api-key dummy
"""

from unittest.mock import MagicMock, patch

import pytest
from django_tenants.utils import tenant_context

from AuthBillet.models import TermUser, TibilletUser
from Customers.models import Client
from QrcodeCashless.models import CarteCashless
from kiosk.models import PaymentsIntent, ReglagesBorne
from laboutik.models import CartePrimaire, Terminal

TAG_ID_CLIENT = "EC000001"
TAG_ID_PRIMAIRE = "EC000002"
EMAIL_BORNE = "test-kiosk-ecrans@tibillet.localhost"


def _reponse_fedow(solde_tlf_centimes=1000, solde_fed_centimes=450, est_anonyme=False):
    """Fausse reponse de FedowAPI().NFCcard.retrieve(), au format CardValidator.
    / Fake NFCcard.retrieve() answer, CardValidator-shaped."""
    return {
        "number_printed": "AB124F2A",
        "is_wallet_ephemere": est_anonyme,
        "wallet": {
            "tokens": [
                {"asset_category": "TLF", "value": solde_tlf_centimes},
                {"asset_category": "FED", "value": solde_fed_centimes},
                # Un badge ne compte pas dans le solde en euros.
                # / A badge does not count in the euro balance.
                {"asset_category": "BDG", "value": 7},
            ],
        },
    }


@pytest.fixture
def tenant():
    return Client.objects.get(schema_name="lespass")


@pytest.fixture
def borne(tenant):
    """Une borne role Kiosque, avec son lecteur et deux cartes (client + primaire).
    Nettoie avant ET apres. / A Kiosk-role device with reader and two cards."""

    def _nettoyer():
        with tenant_context(tenant):
            PaymentsIntent.objects.filter(
                terminal__name__startswith="TEST_ECRANS_"
            ).delete()
            Terminal.objects.filter(name__startswith="TEST_ECRANS_").delete()
            CarteCashless.objects.filter(
                tag_id__in=[TAG_ID_CLIENT, TAG_ID_PRIMAIRE]
            ).delete()
            TermUser.objects.filter(email=EMAIL_BORNE).delete()

    _nettoyer()
    with tenant_context(tenant):
        utilisateur = TermUser.objects.create(
            email=EMAIL_BORNE,
            username=EMAIL_BORNE,
            terminal_role=TibilletUser.ROLE_KIOSQUE,
            is_active=True,
        )
        terminal = Terminal.objects.create(
            name="TEST_ECRANS_Borne", term_user=utilisateur
        )

        from laboutik.models import TPEBancaire

        TPEBancaire.objects.create(
            name="TEST_ECRANS_Lecteur",
            terminal=terminal,
            stripe_id="tmr_test_ecrans",
            registration_code="simulated-wpe",
        )

        CarteCashless.objects.create(tag_id=TAG_ID_CLIENT, number=TAG_ID_CLIENT)
        carte_primaire = CarteCashless.objects.create(
            tag_id=TAG_ID_PRIMAIRE, number=TAG_ID_PRIMAIRE
        )
        CartePrimaire.objects.create(carte=carte_primaire)

    yield utilisateur, terminal
    _nettoyer()


def _client(utilisateur, tenant):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=utilisateur)
    client.defaults["SERVER_NAME"] = f"{tenant.schema_name}.tibillet.localhost"
    return client


# --------------------------------------------------------------------------- #
# Lecture de la carte / Card reading                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_lecture_carte_affiche_le_solde_en_euros(tenant, borne):
    """Le solde = jetons TLF + FED, sans les badges ; affiche en euros.
    / Balance = TLF + FED tokens, badges excluded; shown in euros."""
    utilisateur, _terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        with patch("kiosk.carte.FedowAPI") as faux_fedow:
            faux_fedow.return_value.NFCcard.retrieve.return_value = _reponse_fedow()
            reponse = client.post(
                "/kiosk/check_request_card/", data={"tag_id": TAG_ID_CLIENT}
            )

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="kiosk-etape-solde"' in contenu
    assert "14,50" in contenu
    assert "4F2A" in contenu
    assert "kiosk-modale-non-enregistree" not in contenu


@pytest.mark.django_db
def test_lecture_carte_anonyme_ouvre_la_modale_non_enregistree(tenant, borne):
    """Une carte ephemere (non enregistree) fait apparaitre la modale.
    / An ephemeral (unregistered) card shows the modal."""
    utilisateur, _terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        with patch("kiosk.carte.FedowAPI") as faux_fedow:
            faux_fedow.return_value.NFCcard.retrieve.return_value = _reponse_fedow(
                est_anonyme=True
            )
            reponse = client.post(
                "/kiosk/check_request_card/", data={"tag_id": TAG_ID_CLIENT}
            )

    assert "kiosk-modale-non-enregistree" in reponse.content.decode()


@pytest.mark.django_db
def test_lecture_carte_inconnue_revient_a_l_etape_1_avec_erreur(tenant, borne):
    """Carte absente de la base locale : retour a « posez votre carte » + message.
    / Card unknown locally: back to step 1 with a message."""
    utilisateur, _terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        with patch("kiosk.carte.FedowAPI") as faux_fedow:
            faux_fedow.return_value.NFCcard.retrieve.return_value = _reponse_fedow()
            reponse = client.post(
                "/kiosk/check_request_card/", data={"tag_id": "FFFFFFFF"}
            )

    contenu = reponse.content.decode()
    assert 'data-testid="kiosk-etape-poser-carte"' in contenu
    assert 'data-testid="kiosk-error-message"' in contenu


# --------------------------------------------------------------------------- #
# Recapitulatif et recharge / Summary and refill                              #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_recapitulatif_calcule_le_nouveau_solde_cote_serveur(tenant, borne):
    """14,50 € + 20 € = 34,50 €, calcule par la vue.
    / 14.50 + 20 = 34.50, computed by the view."""
    utilisateur, _terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        with patch("kiosk.carte.FedowAPI") as faux_fedow:
            faux_fedow.return_value.NFCcard.retrieve.return_value = _reponse_fedow()
            reponse = client.post(
                "/kiosk/recapitulatif/",
                data={
                    "tag_id": TAG_ID_CLIENT,
                    "totalAmount": "20.00",
                },
            )

    contenu = reponse.content.decode()
    assert 'data-testid="kiosk-etape-recapitulatif"' in contenu
    assert "20,00" in contenu
    assert "34,50" in contenu
    # Le montant repart vers le paiement avec un point decimal.
    # / The amount goes to the payment with a dot decimal.
    assert 'value="20.00"' in contenu


@pytest.mark.django_db
def test_recapitulatif_refuse_un_montant_nul(tenant, borne):
    """Un montant a zero ne donne pas de recapitulatif, mais un ecran d'erreur.
    / A zero amount gives an error screen, not a summary."""
    utilisateur, _terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        with patch("kiosk.carte.FedowAPI") as faux_fedow:
            faux_fedow.return_value.NFCcard.retrieve.return_value = _reponse_fedow()
            reponse = client.post(
                "/kiosk/recapitulatif/",
                data={
                    "tag_id": TAG_ID_CLIENT,
                    "totalAmount": "0",
                },
            )

    assert 'data-testid="kiosk-etape-erreur"' in reponse.content.decode()


@pytest.mark.django_db
def test_recharge_enregistre_le_solde_avant_recharge(tenant, borne):
    """Le paiement garde le solde lu chez Fedow, pour l'ecran de succes.
    / The payment keeps the balance read from Fedow, for the success screen."""
    utilisateur, terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        with (
            patch("kiosk.carte.FedowAPI") as faux_fedow,
            patch("kiosk.views.poll_payment_intent_status.delay") as faux_delay,
            patch("kiosk.models.PaymentsIntent.send_to_terminal") as faux_envoi,
        ):
            faux_fedow.return_value.NFCcard.retrieve.return_value = _reponse_fedow()
            faux_delay.return_value = MagicMock()
            faux_envoi.side_effect = lambda terminal_cible: PaymentsIntent.objects.get(
                terminal=terminal,
                amount=2000,
            )
            reponse = client.post(
                "/kiosk/refill_with_wisepos/",
                data={
                    "tag_id": TAG_ID_CLIENT,
                    "totalAmount": "20.00",
                },
            )

        assert reponse.status_code == 200
        paiement = PaymentsIntent.objects.get(terminal=terminal, amount=2000)
        assert paiement.solde_avant_centimes == 1450


@pytest.mark.django_db
def test_contexte_ecran_final_annonce_le_nouveau_solde(tenant, borne):
    """contexte_ecran_final : montant ajoute, nouveau solde, donnees de relance.
    / contexte_ecran_final: added amount, new balance, retry data."""
    _utilisateur, terminal = borne
    with tenant_context(tenant):
        carte = CarteCashless.objects.get(tag_id=TAG_ID_CLIENT)
        paiement = PaymentsIntent.objects.create(
            terminal=terminal,
            amount=2050,
            card=carte,
            solde_avant_centimes=1450,
        )
        contexte = paiement.contexte_ecran_final()

    assert contexte["montant_ajoute_centimes"] == 2050
    assert contexte["nouveau_solde_centimes"] == 3500
    assert contexte["tag_id"] == TAG_ID_CLIENT
    assert contexte["montant_pour_formulaire"] == "20.50"


@pytest.mark.django_db
def test_ecran_de_succes_affiche_montant_et_nouveau_solde(tenant, borne):
    """Le sondage de secours rend le succes avec le montant et le nouveau solde.
    / The safety poll renders success with amount and new balance."""
    utilisateur, terminal = borne
    with tenant_context(tenant):
        carte = CarteCashless.objects.get(tag_id=TAG_ID_CLIENT)
        paiement = PaymentsIntent.objects.create(
            terminal=terminal,
            amount=2000,
            card=carte,
            solde_avant_centimes=1450,
            status=PaymentsIntent.SUCCEEDED,
        )
        client = _client(utilisateur, tenant)
        reponse = client.get(f"/kiosk/{paiement.pk}/status/")

    contenu = reponse.content.decode()
    assert 'data-testid="kiosk-success-page"' in contenu
    assert "20,00" in contenu
    assert "34,50" in contenu


# --------------------------------------------------------------------------- #
# Configuration de la borne / Kiosk configuration                             #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_configuration_refusee_sans_carte_primaire(tenant, borne):
    """Sans carte primaire posee, /kiosk/configuration/ renvoie a l'accueil.
    / Without a primary card, configuration redirects home."""
    utilisateur, _terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        reponse = client.get("/kiosk/configuration/")

    assert reponse.status_code == 302
    assert reponse["Location"] == "/kiosk/"


@pytest.mark.django_db
def test_acces_admin_refuse_une_carte_client(tenant, borne):
    """Une carte client ne debloque rien : etat « erreur » de la modale.
    / A client card unlocks nothing: modal error state."""
    utilisateur, _terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        reponse = client.post("/kiosk/acces_admin/", data={"tag_id": TAG_ID_CLIENT})
        reponse_configuration = client.get("/kiosk/configuration/")

    contenu = reponse.content.decode()
    assert "HX-Redirect" not in reponse
    # La balise ouvrante du bloc erreur ne porte pas l'attribut hidden.
    # / The error block's opening tag has no hidden attribute.
    debut_du_bloc_erreur = contenu.index('data-admin-etat="erreur"')
    balise_du_bloc_erreur = contenu[debut_du_bloc_erreur : contenu.index(">", debut_du_bloc_erreur)]
    assert "hidden" not in balise_du_bloc_erreur
    assert reponse_configuration.status_code == 302


@pytest.mark.django_db
def test_acces_admin_carte_primaire_ouvre_la_configuration(tenant, borne):
    """Carte primaire : HX-Redirect, puis la page de configuration s'affiche.
    / Primary card: HX-Redirect, then the configuration page renders."""
    utilisateur, _terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        reponse = client.post("/kiosk/acces_admin/", data={"tag_id": TAG_ID_PRIMAIRE})
        reponse_configuration = client.get("/kiosk/configuration/")

    assert reponse["HX-Redirect"] == "/kiosk/configuration/"
    contenu = reponse_configuration.content.decode()
    assert reponse_configuration.status_code == 200
    assert 'data-testid="kiosk-page-configuration"' in contenu
    assert "TEST_ECRANS_Borne" in contenu


@pytest.mark.django_db
def test_couper_la_recharge_met_la_borne_en_pause(tenant, borne):
    """Interrupteur -> recharge coupee ; Demarrer refuse ; l'accueil est en pause.
    Puis on la rallume et Demarrer rend la borne au public.
    / Switch off -> Start refused, home paused. Switch on -> Start works."""
    utilisateur, terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        client.post("/kiosk/acces_admin/", data={"tag_id": TAG_ID_PRIMAIRE})

        reponse_coupure = client.post(
            "/kiosk/basculer_module/", data={"module": "recharge"}
        )
        assert ReglagesBorne.objects.get(terminal=terminal).recharge_active is False
        assert "Aucun service mis en route." in reponse_coupure.content.decode()

        reponse_demarrage_refuse = client.post("/kiosk/demarrer/")
        assert "HX-Redirect" not in reponse_demarrage_refuse
        assert (
            'data-testid="kiosk-error-message"'
            in reponse_demarrage_refuse.content.decode()
        )

        reponse_accueil = client.get("/kiosk/")
        assert 'data-testid="kiosk-etape-pause"' in reponse_accueil.content.decode()

        client.post("/kiosk/basculer_module/", data={"module": "recharge"})
        reponse_demarrage = client.post("/kiosk/demarrer/")
        assert reponse_demarrage["HX-Redirect"] == "/kiosk/"

        # La configuration est refermee apres le demarrage.
        # / The configuration is closed after starting.
        assert client.get("/kiosk/configuration/").status_code == 302
