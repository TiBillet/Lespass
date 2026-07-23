"""
tests/pytest/test_qrcodescanpay_permissions.py
Permissions des vues de paiement par QR code.
/ QR code payment views permissions.

LOCALISATION : tests/pytest/test_qrcodescanpay_permissions.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
`CanInitiatePaymentPermission` sur les vues `QrCodeScanPay`. La distinction
metier est fine et doit rester verrouillee :

- ENCAISSER (`get_generator`, `generate_qrcode`) demande le droit explicite
  `initiate_payment` sur le tenant, ou d'etre admin / superuser ;
- PAYER (`get_scanner`) demande seulement d'etre authentifie.

Un adherent lambda peut donc scanner pour payer, mais ne peut pas fabriquer une
demande de paiement.
/ Collecting requires an explicit right; paying only requires being logged in.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_qrcodescanpay_permissions.py -v
"""

import uuid

import pytest
from django.contrib import messages as django_messages
from django.contrib.messages import get_messages
from django.test import Client
from django_tenants.utils import tenant_context

from AuthBillet.models import HumanUser, TermUser, TibilletUser
from Customers.models import Client as TenantClient


# ---------------------------------------------------------------------------
# Fixtures et utilitaires
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant():
    """Le tenant de developpement. / The development tenant."""
    return TenantClient.objects.get(schema_name="lespass")


def _client_navigateur():
    """Client de test pointant sur le domaine du tenant.
    / Test client aimed at the tenant domain."""
    return Client(HTTP_HOST="lespass.tibillet.localhost")


def _creer_humain(tenant, prefixe, email_valide=True):
    """Cree un HumanUser jetable dans le schema du tenant.
    / Creates a throwaway HumanUser inside the tenant schema.

    Chaque test cree le sien : la suite tourne sur la base de DEV, sans
    rollback. Un identifiant unique evite toute collision entre les runs.
    / Each test creates its own: the suite runs on the DEV database with no
    rollback. A unique id avoids collisions between runs.

    `email_valide` vaut True par defaut car c'est l'etat d'un adherent normal.
    Le scanner de paiement REFUSE un compte dont l'email n'est pas valide :
    laisser False par defaut ferait echouer les tests du cas nominal pour une
    raison sans rapport avec ce qu'ils verifient.
    / `email_valide` defaults to True because that is a normal member's state.
    The payment scanner REFUSES an account with an unverified email.
    """
    identifiant_unique = f"{prefixe}_{uuid.uuid4().hex[:8]}@example.com"
    with tenant_context(tenant):
        return HumanUser.objects.create(
            email=identifiant_unique,
            username=identifiant_unique,
            email_valid=email_valide,
        )


def _niveaux_des_messages(response):
    """Renvoie les niveaux des messages django poses pendant la requete.
    / Returns the levels of the django messages set during the request.

    On lit le NIVEAU (SUCCESS / ERROR) et jamais le texte : les libelles
    passent par gettext, donc leur valeur depend de la langue active au moment
    du run. Comparer du texte rendrait ce test dependant de la locale.
    / We read the LEVEL, never the text: labels go through gettext, so their
    value depends on the active language. Comparing text would make this test
    locale-dependent.
    """
    return [message.level for message in get_messages(response.wsgi_request)]


# ---------------------------------------------------------------------------
# 1. Encaisser demande un droit explicite
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_generateur_de_paiement_refuse_a_un_adherent_sans_droit(tenant):
    """Un humain authentifie SANS le droit initiate_payment ne peut pas encaisser.
    / An authenticated human WITHOUT initiate_payment cannot collect payments."""
    utilisateur = _creer_humain(tenant, "sans_droit")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        assert client.get("/qrcodescanpay/get_generator/").status_code == 403
        assert client.post("/qrcodescanpay/generate_qrcode/", {}).status_code == 403
    finally:
        with tenant_context(tenant):
            utilisateur.delete()


@pytest.mark.django_db
def test_generateur_de_paiement_autorise_avec_le_droit_initiate_payment(tenant):
    """Le droit initiate_payment sur CE tenant ouvre le generateur.
    / The initiate_payment right on THIS tenant opens the generator."""
    utilisateur = _creer_humain(tenant, "avec_droit")
    with tenant_context(tenant):
        utilisateur.initiate_payment.add(tenant)
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        assert client.get("/qrcodescanpay/get_generator/").status_code == 200
    finally:
        with tenant_context(tenant):
            utilisateur.delete()


@pytest.mark.django_db
def test_generateur_de_paiement_autorise_pour_un_admin_du_tenant(tenant):
    """Un admin du tenant encaisse sans avoir besoin du droit dedie.
    / A tenant admin can collect without the dedicated right."""
    utilisateur = _creer_humain(tenant, "admin_tenant")
    with tenant_context(tenant):
        utilisateur.client_admin.add(tenant)
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        assert client.get("/qrcodescanpay/get_generator/").status_code == 200
    finally:
        with tenant_context(tenant):
            utilisateur.delete()


@pytest.mark.django_db
def test_generateur_de_paiement_refuse_a_un_utilisateur_desactive(tenant):
    """Un compte desactive perd l'acces, meme s'il gardait le droit en base.
    / A deactivated account loses access, even if it still holds the right."""
    utilisateur = _creer_humain(tenant, "desactive")
    with tenant_context(tenant):
        utilisateur.initiate_payment.add(tenant)
        utilisateur.is_active = False
        utilisateur.save()
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        assert client.get("/qrcodescanpay/get_generator/").status_code != 200
    finally:
        with tenant_context(tenant):
            utilisateur.delete()


@pytest.mark.django_db
def test_generateur_de_paiement_refuse_a_un_terminal(tenant):
    """Un terminal (espece=TE) n'encaisse pas par cette route humaine.

    La permission exige espece == TYPE_HUM. Les terminaux encaissent par les
    routes de leur propre interface (kiosk / laboutik), qui portent leurs
    propres gardes.
    / A terminal does not collect through this human route: the permission
    requires espece == TYPE_HUM. Terminals use their own interface routes.
    """
    identifiant_unique = f"{uuid.uuid4()}@terminals.local"
    with tenant_context(tenant):
        terminal = TermUser.objects.create(
            email=identifiant_unique,
            username=identifiant_unique,
            terminal_role=TibilletUser.ROLE_LABOUTIK,
            accept_newsletter=False,
        )
    try:
        client = _client_navigateur()
        client.force_login(terminal)

        assert client.get("/qrcodescanpay/get_generator/").status_code != 200
    finally:
        with tenant_context(tenant):
            terminal.delete()


@pytest.mark.django_db
def test_generateur_de_paiement_refuse_a_un_anonyme():
    """Sans session, pas de generateur de paiement.
    / No session, no payment generator."""
    client = _client_navigateur()

    assert client.get("/qrcodescanpay/get_generator/").status_code == 403


# ---------------------------------------------------------------------------
# 2. Payer ne demande PAS le droit d'encaisser
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_scanner_de_paiement_ouvert_a_tout_utilisateur_connecte(tenant):
    """Un adherent lambda peut ouvrir le scanner pour PAYER.

    Contrat asymetrique volontaire : get_scanner ne porte que IsAuthenticated,
    la ou get_generator exige CanInitiatePaymentPermission. Aligner les deux
    interdirait a un adherent de payer par QR code.
    / Deliberate asymmetry: get_scanner only requires IsAuthenticated, while
    get_generator requires CanInitiatePaymentPermission. Aligning them would
    prevent a plain member from paying by QR code.
    """
    utilisateur = _creer_humain(tenant, "scanner")
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        assert client.get("/qrcodescanpay/get_scanner/").status_code == 200
    finally:
        with tenant_context(tenant):
            utilisateur.delete()


@pytest.mark.django_db
def test_scanner_de_paiement_refuse_si_email_non_valide(tenant):
    """Sans email valide, pas de paiement par QR code : on repart vers le compte.

    Garde anti-fraude : payer engage de l'argent, donc l'adresse doit avoir ete
    confirmee. La vue ne renvoie pas 403 mais redirige vers /my_account/ avec
    un message, pour que l'utilisateur comprenne quoi faire.
    / Anti-fraud guard: paying moves money, so the address must be confirmed.
    The view redirects to /my_account/ with a message rather than returning 403.
    """
    utilisateur = _creer_humain(tenant, "email_ko", email_valide=False)
    try:
        client = _client_navigateur()
        client.force_login(utilisateur)

        response = client.get("/qrcodescanpay/get_scanner/")

        assert response.status_code == 302
        assert response.url == "/my_account/"
        assert django_messages.ERROR in _niveaux_des_messages(response)
    finally:
        with tenant_context(tenant):
            utilisateur.delete()


@pytest.mark.django_db
def test_scanner_de_paiement_refuse_a_un_anonyme():
    """Le scanner reste ferme aux visiteurs non connectes.
    / The scanner stays closed to anonymous visitors."""
    client = _client_navigateur()

    assert client.get("/qrcodescanpay/get_scanner/").status_code == 403
