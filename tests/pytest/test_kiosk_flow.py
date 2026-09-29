"""
tests/pytest/test_kiosk_flow.py — Tests DEMO du parcours de recharge kiosque (CHANTIER-02, Tasks 02A + 02B).
tests/pytest/test_kiosk_flow.py — DEMO tests for the kiosk refill flow (CHANTIER-02, Tasks 02A + 02B).

Les tests refill_with_wisepos et list_renders (mockes) verifient que la bonne vue
est appelee sans exiger le rendu HTML complet. Le test test_kiosk_list_renders_recharge_page_for_real
(Task 02B) rend reellement kiosk/recharge.html (templates + static desormais crees)
et verifie un fragment HTML attendu, sans mocker render.
/ The refill_with_wisepos and list_renders (mocked) tests check the right view is called
without requiring the full HTML render. test_kiosk_list_renders_recharge_page_for_real
(Task 02B) really renders kiosk/recharge.html (templates + static now created)
and checks an expected HTML fragment, without mocking render.

Lancement / Run:
    docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_flow.py -v --api-key dummy
"""

from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.http import HttpResponse
from django.test import override_settings
from django_tenants.utils import tenant_context

from AuthBillet.models import TermUser, TibilletUser
from Customers.models import Client
from QrcodeCashless.models import CarteCashless
from kiosk.models import PaymentsIntent
from laboutik.models import Terminal

TEST_TAG_ID = "AAAA1111"


@pytest.fixture
def tenant():
    # Tenant de dev. Aligner le schema_name sur test_kiosk_models.py.
    return Client.objects.get(schema_name="lespass")


@pytest.fixture
def clean_kiosk(tenant):
    """Nettoie les objets TEST_ crees par ce module, avant ET apres.
    / Cleans up the TEST_ objects created by this module, before AND after."""
    def _clean():
        with tenant_context(tenant):
            PaymentsIntent.objects.filter(terminal__name__startswith="TEST_KIOSK_").delete()
            Terminal.objects.filter(name__startswith="TEST_KIOSK_").delete()
            CarteCashless.objects.filter(tag_id=TEST_TAG_ID).delete()
            TermUser.objects.filter(email="test-kiosk@tibillet.localhost").delete()
    _clean()
    yield
    _clean()


@pytest.fixture
def kiosk_user_and_terminal(tenant, clean_kiosk):
    """Un TermUser role Kiosque, appaire a un Terminal WisePOS via term_user.
    / A TermUser with the Kiosk role, paired to a WisePOS Terminal via term_user."""
    with tenant_context(tenant):
        user = TermUser.objects.create(
            email="test-kiosk@tibillet.localhost",
            username="test-kiosk@tibillet.localhost",
            terminal_role=TibilletUser.ROLE_KIOSQUE,
            is_active=True,
        )
        terminal = Terminal.objects.create(name="TEST_KIOSK_Borne1", term_user=user)

        # LA BORNE DOIT AVOIR UN LECTEUR DE CARTE BRANCHE.
        # Sans lui, la vue refuse le rechargement avant meme d'appeler Stripe (« aucun
        # lecteur branche sur cette borne ») — et le mock ne serait jamais atteint.
        # / The kiosk MUST have a card reader plugged in, or the view refuses before Stripe.
        from laboutik.models import TPEBancaire
        TPEBancaire.objects.create(
            name="TEST_KIOSK_Lecteur1",
            terminal=terminal,
            stripe_id="tmr_test_kiosk",
            registration_code="simulated-wpe",
        )

        return user, terminal


def _authenticated_client(user, tenant):
    """Client DRF authentifie par session (force_authenticate), route vers le tenant.
    / DRF client session-authenticated (force_authenticate), routed to the tenant."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["SERVER_NAME"] = f"{tenant.schema_name}.tibillet.localhost"
    return client


@pytest.mark.django_db
def test_kiosk_list_renders_recharge_template(tenant, kiosk_user_and_terminal):
    """GET /kiosk/ rend bien kiosk/recharge.html (parcours de recharge).
    / GET /kiosk/ renders kiosk/recharge.html (refill flow)."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        client = _authenticated_client(user, tenant)
        with patch("kiosk.views.render") as mock_render:
            mock_render.return_value = HttpResponse(status=200)
            response = client.get("/kiosk/")

    assert response.status_code == 200
    template_name = mock_render.call_args[0][1]
    assert template_name == "kiosk/recharge.html"


@pytest.mark.django_db
def test_kiosk_refill_with_wisepos_creates_payment_intent(tenant, kiosk_user_and_terminal):
    """POST /kiosk/refill_with_wisepos/ cree un PaymentsIntent et renvoie 200
    (Fedow, tache Celery et envoi au TPE Stripe mockes).
    / POST /kiosk/refill_with_wisepos/ creates a PaymentsIntent and returns 200
    (Fedow, Celery task and Stripe reader push are mocked)."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        CarteCashless.objects.create(tag_id=TEST_TAG_ID, number=TEST_TAG_ID)

        client = _authenticated_client(user, tenant)

        with patch("kiosk.carte.FedowAPI") as mock_fedow_api, \
             patch("kiosk.views.poll_payment_intent_status.delay") as mock_delay, \
             patch("kiosk.models.PaymentsIntent.send_to_terminal") as mock_send, \
             patch("kiosk.views.render") as mock_render:
            mock_fedow_api.return_value.NFCcard.retrieve.return_value = {"uuid": "fake", "wallet": {"tokens": []}}
            mock_delay.return_value = MagicMock(status="STARTED", result=None)
            # send_to_terminal renvoie l'intention de paiement : on la relit en base
            # / send_to_terminal returns the payment intent: read it back from the DB
            mock_send.side_effect = lambda terminal_cible: PaymentsIntent.objects.get(
                terminal=terminal, amount=1000,
            )
            mock_render.return_value = HttpResponse(status=200)

            response = client.post("/kiosk/refill_with_wisepos/", data={
                "totalAmount": "10.00",
                "tag_id": TEST_TAG_ID,
            })

        assert response.status_code == 200
        assert PaymentsIntent.objects.filter(terminal=terminal, amount=1000).exists()
        template_name = mock_render.call_args[0][1]
        assert template_name == "kiosk/waiting_credit_card_terminal.html"


@pytest.mark.django_db
def test_kiosk_refill_refuse_si_la_borne_n_a_pas_de_lecteur(tenant, clean_kiosk):
    """
    Une borne sans lecteur de carte refuse le rechargement, PROPREMENT et SANS appeler
    Stripe. Sinon l'utilisateur, devant la borne, verrait une erreur incomprehensible.
    / A kiosk with no card reader refuses the refill cleanly, WITHOUT calling Stripe.
    """
    with tenant_context(tenant):
        user = TermUser.objects.create(
            email="test-kiosk-sans-lecteur@tibillet.localhost",
            username="test-kiosk-sans-lecteur@tibillet.localhost",
            terminal_role=TibilletUser.ROLE_KIOSQUE,
            is_active=True,
        )
        # La borne existe et est appairee, mais AUCUN lecteur n'y est branche.
        # / The kiosk exists and is paired, but NO reader is plugged in.
        Terminal.objects.create(name="TEST_KIOSK_SansLecteur", term_user=user)

        CarteCashless.objects.create(tag_id=TEST_TAG_ID, number=TEST_TAG_ID)
        client = _authenticated_client(user, tenant)

        # send_to_terminal ne doit JAMAIS etre atteint : la vue refuse avant.
        # / send_to_terminal must NEVER be reached: the view refuses first.
        with patch("kiosk.carte.FedowAPI") as mock_fedow_api, \
             patch("kiosk.models.PaymentsIntent.send_to_terminal") as mock_send:
            mock_fedow_api.return_value.NFCcard.retrieve.return_value = {"uuid": "fake", "wallet": {"tokens": []}}

            response = client.post("/kiosk/refill_with_wisepos/", data={
                "totalAmount": "10.00",
                "tag_id": TEST_TAG_ID,
            })

        # La vue rend une erreur en 200 (HTMX ne swappe pas les 4xx), et n'a rien envoye.
        # / The view renders an error as 200 (HTMX won't swap 4xx) and sent nothing.
        assert response.status_code == 200
        mock_send.assert_not_called()
        assert not PaymentsIntent.objects.filter(
            terminal__name="TEST_KIOSK_SansLecteur",
        ).exists()

    with tenant_context(tenant):
        TermUser.objects.filter(
            email="test-kiosk-sans-lecteur@tibillet.localhost",
        ).delete()
        Terminal.objects.filter(name="TEST_KIOSK_SansLecteur").delete()
        CarteCashless.objects.filter(tag_id=TEST_TAG_ID).delete()


@pytest.mark.django_db
def test_kiosk_list_renders_recharge_page_for_real(tenant, kiosk_user_and_terminal):
    """GET /kiosk/ rend reellement kiosk/recharge.html, a l'etape 1 (« posez
    votre carte »). Pas de mock de render : on verifie le HTML final.
    / GET /kiosk/ actually renders kiosk/recharge.html at step 1 (tap your
    card). No render mock: checks the final HTML."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        client = _authenticated_client(user, tenant)
        response = client.get("/kiosk/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Posez votre carte sur le lecteur." in content
    assert 'data-nfc-lecture="auto"' in content
    assert 'id="tb-kiosque"' in content
    # Adaptation Task 02B : /htmx/kiosk/ -> /kiosk/ (SPEC), aucune URL LaBoutik ne doit subsister.
    # / Task 02B adaptation: /htmx/kiosk/ -> /kiosk/ (SPEC), no LaBoutik URL should remain.
    assert "/htmx/kiosk/" not in content


@pytest.mark.django_db
@override_settings(DEMO=True)
def test_kiosk_demo_page_loads_nfc_and_exposes_kiosk_context(tenant, kiosk_user_and_terminal):
    """CHANTIER-05 : en DEMO, le rendu de recharge.html charge nfc.js, et
    expose window.DEMO + window.KIOSK (avec type_app) au JS.
    / CHANTIER-05: in DEMO, the recharge.html render loads nfc.js, and exposes
    window.DEMO + window.KIOSK (with type_app) to the JS."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        client = _authenticated_client(user, tenant)
        response = client.get("/kiosk/?type_app=cordova")

    assert response.status_code == 200
    content = response.content.decode()

    # nfc.js est charge. socket.io NE l'est PAS : une borne cordova lit la carte
    # avec le plugin natif, elle n'a pas de serveur NFC local sur le port 3000.
    # / nfc.js is loaded. socket.io is NOT: a cordova kiosk has no local NFC server.
    assert "kiosk/js/nfc.js" in content
    assert "js/socket.io.min.js" not in content

    # window.DEMO pose par base.html en DEMO, avec les 5 cartes du simulateur.
    # Ce sont les memes cartes que la caisse et la tireuse (settings.DEMO_TAGID_*).
    # / window.DEMO set by base.html in DEMO, with the 5 simulator cards
    # (same cards as the POS and the tap).
    assert "window.DEMO" in content
    assert "cartesDuSimulateur" in content
    assert settings.DEMO_TAGID_CM in content
    assert settings.DEMO_TAGID_CLIENT1 in content
    assert settings.DEMO_TAGID_CLIENT2 in content
    assert settings.DEMO_TAGID_CLIENT3 in content
    assert settings.DEMO_TAGID_CLIENT4 in content
    assert "XXXXXXXX" not in content

    # window.KIOSK expose le type_app pour que nfc.js choisisse le mode hardware
    # (ici non utilise car DEMO force le simulateur, mais doit rester correct).
    # / window.KIOSK exposes type_app so nfc.js can pick the hardware mode
    # (unused here since DEMO forces the simulator, but must stay correct).
    assert "window.KIOSK" in content
    assert 'type_app: "cordova"' in content
    assert "demo: true" in content


@pytest.mark.django_db
@override_settings(DEMO=True)
def test_kiosk_demo_page_exposes_non_cordova_type_app_for_pi_mode(tenant, kiosk_user_and_terminal):
    """CHANTIER-05 : sans type_app=cordova (borne Pi/desktop), window.KIOSK.type_app
    n'est pas "cordova" : nfc.js choisira le mode NFCLO (socket.io local) plutot
    que NFCMC (plugin Cordova). Verifie au niveau contexte/rendu ; le clic
    simulateur reste un test manuel navigateur.
    / CHANTIER-05: without type_app=cordova (Pi/desktop kiosk), window.KIOSK.type_app
    is not "cordova": nfc.js will pick NFCLO mode (local socket.io) instead of
    NFCMC (Cordova plugin). Checked at context/render level; the simulator click
    remains a manual browser test."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        client = _authenticated_client(user, tenant)
        response = client.get("/kiosk/?type_app=pi")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'type_app: "pi"' in content
    # Pas de cordova.js injecte pour une cible Pi / no cordova.js injected for a Pi target
    assert "cordova.js" not in content

    # socket.io charge avant nfc.js (necessaire au mode NFCLO)
    # / socket.io loaded before nfc.js (required for NFCLO mode)
    index_socket_io = content.index("js/socket.io.min.js")
    index_nfc_js = content.index("kiosk/js/nfc.js")
    assert index_socket_io < index_nfc_js


@pytest.mark.django_db
def test_kiosk_navigateur_simple_ne_charge_pas_socket_io(tenant, kiosk_user_and_terminal):
    """Sans type_app (simple navigateur), socket.io n'est pas charge.
    Avant, la page tentait http://localhost:3000 et affichait une erreur
    « xhr poll error / CORS » dans la console, meme en prod.
    / Without type_app (plain browser), socket.io is not loaded."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        client = _authenticated_client(user, tenant)
        response = client.get("/kiosk/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "js/socket.io.min.js" not in content
    assert 'type_app: "unknown"' in content


@pytest.mark.django_db
@override_settings(DEMO=False)
def test_kiosk_accueil_affiche_une_erreur_sans_tpe(tenant, kiosk_user_and_terminal):
    """Une borne sans lecteur de carte bancaire affiche l'erreur DES l'accueil,
    au lieu de la laisser decouvrir a l'etape « Payer ».
    / A kiosk without a card reader shows the error on the home screen."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        # On debranche le lecteur de la borne / Unplug the reader from the kiosk
        from laboutik.models import TPEBancaire
        TPEBancaire.objects.filter(terminal=terminal).delete()

        # On relit l'utilisateur en base : l'objet de la fixture garde en memoire
        # sa borne ET l'ancien lecteur (cache des relations OneToOne).
        # / Reload the user: the fixture object caches its kiosk AND the old reader.
        user = TermUser.objects.get(pk=user.pk)
        client = _authenticated_client(user, tenant)
        response = client.get("/kiosk/")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-testid="kiosk-etape-sans-tpe"' in content
    assert 'data-testid="kiosk-etape-poser-carte"' not in content


@pytest.mark.django_db
@override_settings(DEMO=False)
def test_kiosk_accueil_normal_avec_un_tpe(tenant, kiosk_user_and_terminal):
    """Une borne avec son lecteur affiche « posez votre carte », sans erreur.
    / A kiosk with its reader shows "tap your card", no error."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        client = _authenticated_client(user, tenant)
        response = client.get("/kiosk/")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-testid="kiosk-etape-poser-carte"' in content
    assert 'data-testid="kiosk-etape-sans-tpe"' not in content


# --------------------------------------------------------------------------- #
# Bouton « Simuler le paiement » (DEMO) / "Simulate payment" button (DEMO)    #
# --------------------------------------------------------------------------- #

def _paiement_en_attente(terminal):
    """Un PaymentsIntent parti sur le lecteur de la borne de test.
    / A PaymentsIntent sent to the test kiosk's reader."""
    return PaymentsIntent.objects.create(
        terminal=terminal,
        amount=1000,
        reader_stripe_id="tmr_test_kiosk",
    )


@pytest.mark.django_db
@override_settings(DEMO=False)
def test_simuler_paiement_introuvable_hors_demo(tenant, kiosk_user_and_terminal):
    """Hors DEMO, la route de simulation renvoie 404 et n'appelle pas Stripe.
    / Outside DEMO, the simulation route returns 404 and does not call Stripe."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        paiement = _paiement_en_attente(terminal)
        client = _authenticated_client(user, tenant)
        with patch("stripe.terminal.Reader.TestHelpers.present_payment_method") as mock_presenter:
            response = client.post(f"/kiosk/{paiement.pk}/simuler_paiement/")

    assert response.status_code == 404
    mock_presenter.assert_not_called()


@pytest.mark.django_db
@override_settings(DEMO=True)
def test_simuler_paiement_presente_une_carte_sur_le_lecteur_du_paiement(tenant, kiosk_user_and_terminal):
    """En DEMO, le bouton presente une carte de test sur le lecteur du paiement.
    / In DEMO, the button presents a test card on the payment's reader."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        paiement = _paiement_en_attente(terminal)
        client = _authenticated_client(user, tenant)
        with patch("root_billet.models.RootConfiguration.get_stripe_api", return_value="sk_test_fake"), \
             patch("stripe.terminal.Reader.TestHelpers.present_payment_method") as mock_presenter:
            response = client.post(f"/kiosk/{paiement.pk}/simuler_paiement/")

    assert response.status_code == 200
    # Sans « issue », c'est la carte de test acceptee (4242...).
    # / Without "issue", the accepted test card is used.
    mock_presenter.assert_called_once_with(
        "tmr_test_kiosk", card_present={"number": "4242424242424242"},
    )
    assert 'data-testid="kiosk-simulation-envoyee"' in response.content.decode()


@pytest.mark.django_db
@override_settings(DEMO=True)
def test_simuler_un_refus_presente_la_carte_de_test_refusee(tenant, kiosk_user_and_terminal):
    """Le bouton « Simuler un refus » presente la carte de test refusee (4000...0002).
    / The "Simulate decline" button presents the declined test card."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        paiement = _paiement_en_attente(terminal)
        client = _authenticated_client(user, tenant)
        with patch("root_billet.models.RootConfiguration.get_stripe_api", return_value="sk_test_fake"), \
             patch("stripe.terminal.Reader.TestHelpers.present_payment_method") as mock_presenter:
            response = client.post(
                f"/kiosk/{paiement.pk}/simuler_paiement/", data={"issue": "refuse"},
            )

    assert response.status_code == 200
    mock_presenter.assert_called_once_with(
        "tmr_test_kiosk", card_present={"number": "4000000000000002"},
    )
    assert 'data-testid="kiosk-simulation-refus-envoye"' in response.content.decode()


@pytest.mark.django_db
@override_settings(DEMO=True)
def test_simuler_paiement_refuse_une_issue_inconnue(tenant, kiosk_user_and_terminal):
    """Une valeur d'« issue » inconnue renvoie 404, sans appeler Stripe.
    / An unknown "issue" value returns 404 without calling Stripe."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        paiement = _paiement_en_attente(terminal)
        client = _authenticated_client(user, tenant)
        with patch("stripe.terminal.Reader.TestHelpers.present_payment_method") as mock_presenter:
            response = client.post(
                f"/kiosk/{paiement.pk}/simuler_paiement/", data={"issue": "n_importe_quoi"},
            )

    assert response.status_code == 404
    mock_presenter.assert_not_called()


@pytest.mark.django_db
@override_settings(DEMO=True)
def test_simuler_paiement_affiche_une_erreur_si_stripe_refuse(tenant, kiosk_user_and_terminal):
    """Si Stripe refuse (vrai lecteur, pas simule), le bouton reste avec un message.
    / If Stripe refuses (real reader), the button stays with a message."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        paiement = _paiement_en_attente(terminal)
        client = _authenticated_client(user, tenant)
        with patch("root_billet.models.RootConfiguration.get_stripe_api", return_value="sk_test_fake"), \
             patch("stripe.terminal.Reader.TestHelpers.present_payment_method",
                   side_effect=Exception("reader is not simulated")):
            response = client.post(f"/kiosk/{paiement.pk}/simuler_paiement/")

    contenu = response.content.decode()
    assert response.status_code == 200
    assert 'data-testid="kiosk-error-message"' in contenu
    assert 'data-testid="kiosk-simuler-paiement"' in contenu
    # Le texte brut de Stripe n'est pas montre / Raw Stripe text is not shown
    assert "reader is not simulated" not in contenu
