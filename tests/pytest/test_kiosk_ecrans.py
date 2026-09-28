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

import time
from unittest.mock import MagicMock, patch

import pytest
from django_tenants.utils import tenant_context

from AuthBillet.models import TermUser, TibilletUser
from Customers.models import Client
from QrcodeCashless.models import CarteCashless
from kiosk.models import PaymentsIntent, ReglagesBorne
from kiosk.views import CLE_SESSION_ADMIN_BORNE, DUREE_OUVERTURE_CONFIGURATION_SECONDES
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
    balise_du_bloc_erreur = contenu[
        debut_du_bloc_erreur : contenu.index(">", debut_du_bloc_erreur)
    ]
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


def _ouvrir_la_configuration(client):
    """Pose la carte primaire dans la modale admin. / Taps the primary card."""
    client.post("/kiosk/acces_admin/", data={"tag_id": TAG_ID_PRIMAIRE})


def _mettre_la_recharge(terminal, active):
    """Regle directement la recharge de la borne. / Sets the refill directly."""
    ReglagesBorne.objects.update_or_create(
        terminal=terminal, defaults={"recharge_active": active}
    )


@pytest.mark.django_db
def test_basculer_module_applique_l_etat_voulu_meme_rejoue(tenant, borne):
    """L'interrupteur envoie l'etat VOULU : rejouer « couper » laisse coupe.
    / The switch sends the WANTED state: replaying "off" stays off."""
    utilisateur, terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        _ouvrir_la_configuration(client)
        donnees_couper = {"module": "recharge", "activer": "false"}
        client.post("/kiosk/basculer_module/", data=donnees_couper)
        reponse = client.post("/kiosk/basculer_module/", data=donnees_couper)

        assert ReglagesBorne.objects.get(terminal=terminal).recharge_active is False
    assert "Aucun service mis en route." in reponse.content.decode()


@pytest.mark.django_db
def test_basculer_module_sans_carte_primaire_ne_change_rien(tenant, borne):
    """Sans configuration ouverte : HX-Redirect vers l'accueil, rien ne change.
    / Without an open configuration: redirect home, nothing changes."""
    utilisateur, terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        reponse = client.post(
            "/kiosk/basculer_module/", data={"module": "recharge", "activer": "false"}
        )
        reglages = ReglagesBorne.objects.filter(terminal=terminal).first()

    assert reponse["HX-Redirect"] == "/kiosk/"
    assert reglages is None or reglages.recharge_active is True


@pytest.mark.django_db
def test_demarrer_sans_carte_primaire_renvoie_a_l_accueil(tenant, borne):
    """Demarrer sans configuration ouverte : simple retour a l'accueil.
    / Start without an open configuration: back home."""
    utilisateur, _terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        reponse = client.post("/kiosk/demarrer/")

    assert reponse["HX-Redirect"] == "/kiosk/"


@pytest.mark.django_db
def test_demarrer_est_refuse_quand_aucun_service_n_est_actif(tenant, borne):
    """Recharge coupee : Demarrer affiche une erreur au lieu de rediriger.
    / Refill off: Start shows an error instead of redirecting."""
    utilisateur, terminal = borne
    with tenant_context(tenant):
        _mettre_la_recharge(terminal, active=False)
        client = _client(utilisateur, tenant)
        _ouvrir_la_configuration(client)
        reponse = client.post("/kiosk/demarrer/")

    assert "HX-Redirect" not in reponse
    assert 'data-testid="kiosk-error-message"' in reponse.content.decode()


@pytest.mark.django_db
def test_demarrer_rend_la_borne_au_public_et_ferme_la_configuration(tenant, borne):
    """Demarrer : HX-Redirect vers /kiosk/, et la configuration se referme.
    / Start: redirect to /kiosk/, and the configuration closes."""
    utilisateur, _terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        _ouvrir_la_configuration(client)
        reponse = client.post("/kiosk/demarrer/")
        reponse_configuration = client.get("/kiosk/configuration/")

    assert reponse["HX-Redirect"] == "/kiosk/"
    assert reponse_configuration.status_code == 302


@pytest.mark.django_db
def test_configuration_se_referme_apres_dix_minutes(tenant, borne):
    """L'ouverture par carte primaire expire : 10 min apres, retour accueil.
    / The primary-card opening expires after 10 minutes."""
    utilisateur, _terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        _ouvrir_la_configuration(client)

        session = client.session
        session[CLE_SESSION_ADMIN_BORNE] = (
            time.time() - DUREE_OUVERTURE_CONFIGURATION_SECONDES - 1
        )
        session.save()

        reponse = client.get("/kiosk/configuration/")

    assert reponse.status_code == 302


@pytest.mark.django_db
def test_accueil_affiche_la_pause_quand_la_recharge_est_coupee(tenant, borne):
    """Recharge coupee : /kiosk/ affiche « La borne est en pause. ».
    / Refill off: /kiosk/ shows the paused screen."""
    utilisateur, terminal = borne
    with tenant_context(tenant):
        _mettre_la_recharge(terminal, active=False)
        client = _client(utilisateur, tenant)
        reponse = client.get("/kiosk/")

    assert 'data-testid="kiosk-etape-pause"' in reponse.content.decode()


@pytest.mark.django_db
def test_lecture_carte_refusee_quand_la_borne_est_en_pause(tenant, borne):
    """Garde serveur : un ecran reste ouvert ne peut pas avancer en pause.
    / Server guard: a stale screen cannot move on while paused."""
    utilisateur, terminal = borne
    with tenant_context(tenant):
        _mettre_la_recharge(terminal, active=False)
        client = _client(utilisateur, tenant)
        with patch("kiosk.carte.FedowAPI") as faux_fedow:
            reponse = client.post(
                "/kiosk/check_request_card/", data={"tag_id": TAG_ID_CLIENT}
            )

    assert 'data-testid="kiosk-etape-pause"' in reponse.content.decode()
    faux_fedow.assert_not_called()


@pytest.mark.django_db
def test_recharge_refusee_quand_la_borne_est_en_pause(tenant, borne):
    """Un POST de paiement rejoue sur une borne en pause ne cree aucun paiement.
    / A replayed payment POST on a paused kiosk creates no payment."""
    utilisateur, terminal = borne
    with tenant_context(tenant):
        _mettre_la_recharge(terminal, active=False)
        client = _client(utilisateur, tenant)
        with patch("kiosk.models.PaymentsIntent.send_to_terminal") as faux_envoi:
            reponse = client.post(
                "/kiosk/refill_with_wisepos/",
                data={"tag_id": TAG_ID_CLIENT, "totalAmount": "20.00"},
            )

        assert not PaymentsIntent.objects.filter(terminal=terminal).exists()
    assert 'data-testid="kiosk-etape-pause"' in reponse.content.decode()
    faux_envoi.assert_not_called()


@pytest.mark.django_db
def test_recapitulatif_refuse_un_montant_trop_eleve(tenant, borne):
    """Au-dela de 99 999,99 EUR (limite du pave), le serveur refuse.
    / Above the keypad limit, the server refuses."""
    utilisateur, _terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        with patch("kiosk.carte.FedowAPI") as faux_fedow:
            faux_fedow.return_value.NFCcard.retrieve.return_value = _reponse_fedow()
            reponse = client.post(
                "/kiosk/recapitulatif/",
                data={"tag_id": TAG_ID_CLIENT, "totalAmount": "100000.00"},
            )

    assert 'data-testid="kiosk-etape-erreur"' in reponse.content.decode()


@pytest.mark.django_db
def test_recapitulatif_refuse_un_montant_avec_des_centimes(tenant, borne):
    """La borne recharge en euros entiers : 20,50 EUR est refuse cote serveur.
    / Whole euros only: 20.50 is refused server-side."""
    utilisateur, _terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        with patch("kiosk.carte.FedowAPI") as faux_fedow:
            faux_fedow.return_value.NFCcard.retrieve.return_value = _reponse_fedow()
            reponse = client.post(
                "/kiosk/recapitulatif/",
                data={"tag_id": TAG_ID_CLIENT, "totalAmount": "20.50"},
            )

    contenu = reponse.content.decode()
    assert 'data-testid="kiosk-etape-erreur"' in contenu
    assert "nombre entier d" in contenu


@pytest.mark.django_db
def test_recharge_refuse_un_montant_avec_des_centimes(tenant, borne):
    """Un POST de paiement avec des centimes ne cree aucun paiement.
    / A payment POST with cents creates no payment."""
    utilisateur, terminal = borne
    with tenant_context(tenant):
        client = _client(utilisateur, tenant)
        with (
            patch("kiosk.carte.FedowAPI") as faux_fedow,
            patch("kiosk.models.PaymentsIntent.send_to_terminal") as faux_envoi,
        ):
            faux_fedow.return_value.NFCcard.retrieve.return_value = _reponse_fedow()
            reponse = client.post(
                "/kiosk/refill_with_wisepos/",
                data={"tag_id": TAG_ID_CLIENT, "totalAmount": "20.50"},
            )

        assert not PaymentsIntent.objects.filter(terminal=terminal).exists()
    assert 'data-testid="kiosk-etape-erreur"' in reponse.content.decode()
    faux_envoi.assert_not_called()


# --------------------------------------------------------------------------- #
# Ecran de refus / Refusal screen                                             #
# --------------------------------------------------------------------------- #


def _rendre_l_ecran_de_refus(contexte_de_l_evenement):
    """Rend cancel.html comme le websocket : hors requete, `event` seul.
    / Renders cancel.html like the websocket: outside a request."""
    from django.template.loader import get_template

    return get_template("kiosk/cancel.html").render(
        context={"event": contexte_de_l_evenement}
    )


@pytest.mark.django_db
def test_refus_confirme_propose_de_reessayer(tenant, borne):
    """Annulation confirmee par Stripe : texte rassurant + bouton Reessayer.
    / Cancellation confirmed: reassuring text + retry button."""
    with tenant_context(tenant):
        html = _rendre_l_ecran_de_refus(
            {
                "statut_certain": True,
                "tag_id": TAG_ID_CLIENT,
                "montant_pour_formulaire": "20.00",
            }
        )

    assert 'data-testid="kiosk-bouton-reessayer"' in html
    assert "kiosk-refus-incertain" not in html


@pytest.mark.django_db
def test_refus_incertain_ne_propose_pas_de_reessayer(tenant, borne):
    """Statut inconnu (erreur de suivi) : texte prudent, pas de Reessayer.
    / Unknown status: cautious text, no retry."""
    with tenant_context(tenant):
        html = _rendre_l_ecran_de_refus(
            {"tag_id": TAG_ID_CLIENT, "montant_pour_formulaire": "20.00"}
        )

    assert 'data-testid="kiosk-refus-incertain"' in html
    assert "kiosk-bouton-reessayer" not in html


@pytest.mark.django_db
def test_rejeu_websocket_transmet_le_nouveau_solde(tenant, borne):
    """A la reconnexion, le consumer renvoie l'ecran final AVEC son contexte.
    / On reconnect, the consumer replays the final screen WITH its context."""
    from wsocket.consumers import TerminalConsumer

    _utilisateur, terminal = borne
    with tenant_context(tenant):
        carte = CarteCashless.objects.get(tag_id=TAG_ID_CLIENT)
        PaymentsIntent.objects.create(
            terminal=terminal,
            amount=2000,
            card=carte,
            solde_avant_centimes=1450,
            status=PaymentsIntent.SUCCEEDED,
            payment_intent_stripe_id="pi_test_ecrans_rejeu",
        )

    consumer = TerminalConsumer()
    consumer.scope = {"tenant": tenant}
    consumer.room_name = "pi_test_ecrans_rejeu"
    # On lit l'objet brut dans __dict__ (sans passer par le descripteur), puis
    # .func : la fonction synchrone sous database_sync_to_async.
    # / Raw object from __dict__, then .func: the sync function underneath.
    fonction_synchrone = TerminalConsumer.__dict__["get_finished_template_name"].func
    nom_du_template, contexte = fonction_synchrone(consumer)

    assert nom_du_template == "success.html"
    assert contexte["nouveau_solde_centimes"] == 3450
    assert contexte["statut_certain"] is True
