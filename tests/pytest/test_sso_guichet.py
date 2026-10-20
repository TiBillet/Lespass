"""
Tests du guichet de connexion commun à tous les lieux (SSO).
/ Tests of the login desk shared by all venues (SSO).

LOCALISATION : tests/pytest/test_sso_guichet.py
Code testé :
- AuthBillet/sso.py (le ticket) ;
- AuthBillet/views_sso.py (le guichet, schéma public : /sso/, /sso/code/,
  /sso/code/verifier/) ;
- BaseBillet/views.py : connexion, connexion_retour, TiBilletLogin.login_fullpage
  (le lieu).

QUI VISE QUOI :
- le guichet : client de test avec HTTP_HOST="tibillet.localhost" (domaine
  principal du tenant public) ;
- le lieu : client de test avec HTTP_HOST="lespass.tibillet.localhost".
/ Desk: HTTP_HOST of the public tenant. Venue: HTTP_HOST of lespass.

PIÈGES (tests/PIEGES.md) :
- Le cache est le VRAI memcached, partagé avec le serveur de dev. On l'isole sans
  le vider : un email et une IP uniques par test, et `cache.delete_many` de leurs
  clés en fin de test, dans le contexte de `public` (là où vivent les clés du
  code). Jamais `cache.clear()` (section « Ne PAS utiliser `cache.clear()` »).
  Les clés « ticket déjà servi » ont un nom au hasard et vivent 120 s : on ne
  les efface pas.
- Les tâches Celery sont patchées : un `.delay()` direct part vers le vrai broker.
  La tâche mail du code, et `ticket_celery_mailer` / `webhook_reservation`
  appelées quand une ancienne réservation `F` passe en `FA`.
- L'appel Fedow (portefeuille) du retour sur le lieu est patché.
- Les comptes et réservations sont créés dans `tenant_context`, pas
  `schema_context` (FakeTenant, piège 9.1), et supprimés en fin de test.
/ Real shared memcached: unique email/IP, targeted delete_many, never
cache.clear(). Celery tasks and Fedow patched. tenant_context, cleanup.
"""

import time
from datetime import timedelta
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from django.core import signing
from django.core.cache import cache
from django.test import Client as ClientDeTest
from django.utils import timezone
from django_tenants.utils import tenant_context

import fabriques_reservation
from AuthBillet.connexion_par_code import cle_cache, cle_cache_ip
from AuthBillet.models import TermUser, TibilletUser
from AuthBillet.sso import (
    fabriquer_un_ticket,
    lire_un_ticket,
    trouver_le_lieu_du_domaine,
)
from BaseBillet.models import Event, Reservation, Ticket
from Customers.models import Client

DOMAINE_DU_GUICHET = "tibillet.localhost"
DOMAINE_DU_LIEU = "lespass.tibillet.localhost"
DOMAINE_DU_DEUXIEME_LIEU = "festival.tibillet.localhost"

# La tâche mail du code. Le service l'importe au moment de l'appel : patcher
# l'attribut du module BaseBillet.tasks suffit.
# / Login-code mail task, imported at call time by the service.
CHEMIN_DE_LA_TACHE_MAIL = "BaseBillet.tasks.code_de_connexion_celery_mailer"
# Le portefeuille Fedow créé au retour sur le lieu.
# / Fedow wallet created when coming back to the venue.
CHEMIN_DE_FEDOW = "BaseBillet.views.FedowAPI"

SUFFIXES_DES_CLES_D_UN_EMAIL = [
    "empreinte",
    "essais",
    "dernier_envoi",
    "envois_de_l_heure",
]

# Un `state` quelconque, pour les tests du guichet seul (sans passer par le lieu).
# / Any state, for desk-only tests.
STATE_DE_TEST = "state-de-test-du-guichet"


# --- Fixtures ---


@pytest.fixture
def tenant_public():
    """Le tenant du guichet. / The desk tenant."""
    return Client.objects.get(schema_name="public")


@pytest.fixture
def menage(tenant, tenant_public):
    """
    Fabrique des emails et des IP uniques, et range ce que le test crée.
    En fin de test : clés du cache effacées (sur public), réservations et
    comptes supprimés (dans le contexte du lieu), événements archivés.
    / Unique emails and IPs; cleans cache keys, reservations, accounts, events.
    """

    class Menage:
        def __init__(self):
            self.emails = []
            self.ips = []

        def nouvel_email(self):
            email = f"sso-{uuid4().hex[:8]}@test.local"
            self.emails.append(email)
            return email

        def nouvelle_ip(self):
            # 2001:db8::/32 : plage réservée à la documentation, jamais routée.
            # / Documentation-only IPv6 range.
            ip = f"2001:db8::{uuid4().hex[:4]}:{uuid4().hex[:4]}"
            self.ips.append(ip)
            return ip

        def client_du_guichet(self):
            return ClientDeTest(
                HTTP_HOST=DOMAINE_DU_GUICHET, REMOTE_ADDR=self.nouvelle_ip()
            )

    rangement = Menage()
    yield rangement

    cles_du_cache = []
    for email in rangement.emails:
        for suffixe in SUFFIXES_DES_CLES_D_UN_EMAIL:
            cles_du_cache.append(cle_cache(email, suffixe))
    for ip in rangement.ips:
        cles_du_cache.append(cle_cache_ip(ip))
    with tenant_context(tenant_public):
        cache.delete_many(cles_du_cache)

    with tenant_context(tenant):
        for email in rangement.emails:
            Reservation.objects.filter(user_commande__email=email).delete()
            TibilletUser.objects.filter(email=email).delete()


@pytest.fixture
def taches_patchees():
    """
    Patche la tâche mail du code, les tâches du passage F → FA, et Fedow.
    / Patches the code mail task, the F → FA tasks, and Fedow.
    """
    with (
        patch(CHEMIN_DE_LA_TACHE_MAIL) as tache_mail,
        patch("BaseBillet.signals.ticket_celery_mailer") as tache_billets,
        patch("BaseBillet.signals.webhook_reservation") as tache_webhook,
        patch(CHEMIN_DE_FEDOW) as fedow,
    ):
        yield {
            "mail": tache_mail,
            "billets": tache_billets,
            "webhook": tache_webhook,
            "fedow": fedow,
        }


# --- Petites fonctions / Helpers ---


def creer_un_compte(
    tenant, email, actif=True, espece=TibilletUser.TYPE_HUM, email_error=False
):
    """Crée un compte dans le contexte du lieu. / Creates an account in the venue context."""
    with tenant_context(tenant):
        if espece == TibilletUser.TYPE_TERM:
            return TermUser.objects.create(email=email, username=email)
        return TibilletUser.objects.create(
            email=email,
            username=email,
            espece=espece,
            is_active=actif,
            email_valid=actif,
            email_error=email_error,
        )


def creer_un_evenement(tenant, jours_avant_l_evenement=7, jauge_max=100):
    """
    Crée un événement, archivé en fin de test par la fixture automatique.
    / Creates an event, archived after the test by the autouse fixture.
    """
    with tenant_context(tenant):
        debut = timezone.now() + timedelta(days=jours_avant_l_evenement)
        evenement = Event.objects.create(
            name=f"Test SSO {uuid4().hex[:8]}",
            datetime=debut,
            end_datetime=debut + timedelta(hours=2),
            jauge_max=jauge_max,
        )
    fabriques_reservation.EVENEMENTS_A_ARCHIVER.append(evenement.pk)
    return evenement


def creer_une_ancienne_reservation_gratuite(
    tenant, user, evenement, nombre_de_billets=0
):
    """
    Une réservation gratuite en attente (`F`), comme en a laissé l'ancienne
    réservation anonyme.
    / An old pending free reservation (F).
    """
    with tenant_context(tenant):
        reservation = Reservation.objects.create(
            user_commande=user,
            event=evenement,
            status=Reservation.FREERES,
            to_mail=True,
        )
        for _numero in range(nombre_de_billets):
            Ticket.objects.create(reservation=reservation, status=Ticket.NOT_ACTIV)
    return reservation


def demander_un_code(
    client_du_guichet, tache_mail, email, lieu=DOMAINE_DU_LIEU, state=STATE_DE_TEST
):
    """
    Étape 1 du guichet. Renvoie (réponse, code envoyé par le dernier mail).
    / Desk step 1. Returns (response, code of the last mail).
    """
    reponse = client_du_guichet.post(
        "/sso/code/",
        {"email": email, "lieu": lieu, "state": state},
        HTTP_HX_REQUEST="true",
    )
    code_envoye = None
    if tache_mail.delay.called:
        code_envoye = tache_mail.delay.call_args.args[1]
    return reponse, code_envoye


def taper_le_code(
    client_du_guichet, email, code, lieu=DOMAINE_DU_LIEU, state=STATE_DE_TEST
):
    """Étape 2 du guichet. / Desk step 2."""
    return client_du_guichet.post(
        "/sso/code/verifier/",
        {"email": email, "code": code, "lieu": lieu, "state": state},
        HTTP_HX_REQUEST="true",
    )


def se_connecter_sur_le_guichet(
    client_du_guichet, tache_mail, email, lieu=DOMAINE_DU_LIEU, state=STATE_DE_TEST
):
    """Étapes 1 et 2 avec le bon code. / Steps 1 and 2 with the right code."""
    _reponse, code = demander_un_code(client_du_guichet, tache_mail, email, lieu, state)
    return taper_le_code(client_du_guichet, email, code, lieu, state)


def lire_le_ticket_de_l_url(url_de_retour):
    """Le ticket et le state d'une URL de retour vers le lieu. / Ticket and state of a return URL."""
    parametres = parse_qs(urlparse(url_de_retour).query)
    return parametres["ticket"][0], parametres["state"][0]


def compte_connecte(client_de_test):
    """pk (str) du compte connecté dans la session du client, ou None. / Logged-in pk or None."""
    return client_de_test.session.get("_auth_user_id")


# =============================================================================
# Service SSO (AuthBillet/sso.py)
# =============================================================================


def test_un_ticket_lu_par_le_bon_lieu_donne_le_compte():
    compte = TibilletUser(email="ticket@test.local", espece=TibilletUser.TYPE_HUM)
    ticket = fabriquer_un_ticket(compte, DOMAINE_DU_LIEU)

    contenu = lire_un_ticket(ticket, DOMAINE_DU_LIEU)

    assert contenu is not None
    assert contenu["compte"] == str(compte.pk)
    assert contenu["lieu"] == DOMAINE_DU_LIEU


def test_un_ticket_lu_une_deuxieme_fois_est_refuse():
    compte = TibilletUser(email="ticket@test.local", espece=TibilletUser.TYPE_HUM)
    ticket = fabriquer_un_ticket(compte, DOMAINE_DU_LIEU)

    assert lire_un_ticket(ticket, DOMAINE_DU_LIEU) is not None
    assert lire_un_ticket(ticket, DOMAINE_DU_LIEU) is None


def test_un_ticket_pour_un_lieu_est_refuse_par_un_autre_lieu():
    compte = TibilletUser(email="ticket@test.local", espece=TibilletUser.TYPE_HUM)
    ticket = fabriquer_un_ticket(compte, DOMAINE_DU_LIEU)

    assert lire_un_ticket(ticket, DOMAINE_DU_DEUXIEME_LIEU) is None
    # Présenté au mauvais lieu, il n'est pas consommé : le bon lieu le lit encore.
    # / Not consumed by the wrong venue.
    assert lire_un_ticket(ticket, DOMAINE_DU_LIEU) is not None


def test_un_ticket_de_plus_de_60_secondes_est_refuse():
    compte = TibilletUser(email="ticket@test.local", espece=TibilletUser.TYPE_HUM)
    # Le ticket est daté de 61 secondes dans le passé : on remplace l'horloge
    # de `signing` le temps de le fabriquer.
    # / The ticket is dated 61 s in the past by patching signing's clock.
    horloge_du_passe = MagicMock()
    horloge_du_passe.time.return_value = time.time() - 61
    with patch.object(signing, "time", horloge_du_passe):
        ticket = fabriquer_un_ticket(compte, DOMAINE_DU_LIEU)

    assert lire_un_ticket(ticket, DOMAINE_DU_LIEU) is None


def test_un_ticket_modifie_a_la_main_est_refuse():
    compte = TibilletUser(email="ticket@test.local", espece=TibilletUser.TYPE_HUM)
    ticket = fabriquer_un_ticket(compte, DOMAINE_DU_LIEU)
    # On change le 1er caractère du contenu (avant la signature).
    # / Change the first character of the payload.
    premier_caractere_change = "a" if ticket[0] != "a" else "b"
    ticket_modifie = premier_caractere_change + ticket[1:]

    assert lire_un_ticket(ticket_modifie, DOMAINE_DU_LIEU) is None


def test_fabriquer_un_ticket_refuse_un_compte_non_humain():
    terminal = TibilletUser(email="terminal@test.local", espece=TibilletUser.TYPE_TERM)

    with pytest.raises(ValueError):
        fabriquer_un_ticket(terminal, DOMAINE_DU_LIEU)


def test_trouver_le_lieu_du_domaine(tenant):
    assert trouver_le_lieu_du_domaine("inconnu-sso.tibillet.localhost") is None
    assert trouver_le_lieu_du_domaine(DOMAINE_DU_GUICHET) is None
    assert trouver_le_lieu_du_domaine(DOMAINE_DU_LIEU) == tenant


# =============================================================================
# Guichet (schéma public)
# =============================================================================


def test_guichet_avec_un_lieu_inconnu_affiche_une_erreur(menage):
    client_du_guichet = menage.client_du_guichet()

    reponse = client_du_guichet.get(
        "/sso/", {"lieu": "inconnu-sso.tibillet.localhost", "state": STATE_DE_TEST}
    )

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert 'data-testid="sso-erreur"' in contenu
    assert 'id="loginForm"' not in contenu


def test_guichet_affiche_l_etape_email_avec_le_nom_du_lieu(menage):
    client_du_guichet = menage.client_du_guichet()

    reponse = client_du_guichet.get(
        "/sso/", {"lieu": DOMAINE_DU_LIEU, "state": STATE_DE_TEST}
    )

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert 'id="loginForm"' in contenu
    assert 'id="loginEmail"' in contenu
    assert 'data-testid="sso-titre"' in contenu


def test_demander_un_code_ne_cree_ni_compte_ni_portefeuille(menage, taches_patchees):
    client_du_guichet = menage.client_du_guichet()
    email = menage.nouvel_email()

    reponse, code = demander_un_code(client_du_guichet, taches_patchees["mail"], email)

    assert reponse.status_code == 200
    assert 'data-testid="login-code"' in reponse.content.decode()
    assert code is not None
    # Le portefeuille appartient à un compte : pas de compte, pas de portefeuille.
    # / A wallet belongs to an account: no account, no wallet.
    assert not TibilletUser.objects.filter(email=email).exists()
    taches_patchees["fedow"].assert_not_called()


def test_le_bon_code_cree_un_compte_active_connecte_et_rattache_au_lieu(
    tenant, menage, taches_patchees
):
    client_du_guichet = menage.client_du_guichet()
    email = menage.nouvel_email()

    reponse = se_connecter_sur_le_guichet(
        client_du_guichet, taches_patchees["mail"], email
    )

    assert reponse.status_code == 200
    url_de_retour = reponse["HX-Redirect"]
    assert url_de_retour.startswith(f"https://{DOMAINE_DU_LIEU}/connexion/retour/?")

    compte = TibilletUser.objects.get(email=email)
    assert compte.is_active
    assert compte.email_valid
    assert compte.client_achat.filter(pk=tenant.pk).exists()
    # Connecté sur le guichet. / Logged in on the desk.
    assert compte_connecte(client_du_guichet) == str(compte.pk)

    ticket, state = lire_le_ticket_de_l_url(url_de_retour)
    assert state == STATE_DE_TEST
    contenu_du_ticket = lire_un_ticket(ticket, DOMAINE_DU_LIEU)
    assert contenu_du_ticket["compte"] == str(compte.pk)


def test_le_mauvais_code_ne_connecte_pas(menage, taches_patchees):
    client_du_guichet = menage.client_du_guichet()
    email = menage.nouvel_email()
    _reponse, code = demander_un_code(client_du_guichet, taches_patchees["mail"], email)
    code_faux = "000000" if code != "000000" else "111111"

    reponse = taper_le_code(client_du_guichet, email, code_faux)

    assert reponse.status_code == 200
    assert "HX-Redirect" not in reponse
    assert 'data-testid="login-code-erreur"' in reponse.content.decode()
    assert compte_connecte(client_du_guichet) is None
    assert not TibilletUser.objects.filter(email=email).exists()


def test_le_bon_code_valide_une_ancienne_reservation_gratuite_du_lieu(
    tenant, menage, taches_patchees
):
    client_du_guichet = menage.client_du_guichet()
    email = menage.nouvel_email()
    compte_non_active = creer_un_compte(tenant, email, actif=False)
    evenement_a_venir = creer_un_evenement(tenant)
    reservation = creer_une_ancienne_reservation_gratuite(
        tenant, compte_non_active, evenement_a_venir
    )

    se_connecter_sur_le_guichet(client_du_guichet, taches_patchees["mail"], email)

    with tenant_context(tenant):
        reservation.refresh_from_db()
    assert reservation.status == Reservation.FREERES_USERACTIV
    taches_patchees["billets"].delay.assert_called_once_with(reservation.pk)


def test_le_bon_code_annule_une_ancienne_reservation_d_un_evenement_passe(
    tenant, menage, taches_patchees
):
    client_du_guichet = menage.client_du_guichet()
    email = menage.nouvel_email()
    compte_non_active = creer_un_compte(tenant, email, actif=False)
    evenement_passe = creer_un_evenement(tenant, jours_avant_l_evenement=-3)
    reservation = creer_une_ancienne_reservation_gratuite(
        tenant, compte_non_active, evenement_passe
    )

    se_connecter_sur_le_guichet(client_du_guichet, taches_patchees["mail"], email)

    with tenant_context(tenant):
        reservation.refresh_from_db()
    assert reservation.status == Reservation.CANCELED
    taches_patchees["billets"].delay.assert_not_called()


def test_une_ancienne_reservation_devenue_impossible_connecte_avec_un_avertissement(
    tenant, menage, taches_patchees
):
    client_du_guichet = menage.client_du_guichet()
    email = menage.nouvel_email()
    compte_non_active = creer_un_compte(tenant, email, actif=False)
    # Jauge de 1, réservation de 2 billets, faite il y a 40 minutes : sa place
    # n'est plus retenue, et l'événement est complet pour elle.
    # / Gauge 1, 2 tickets, booked 40 min ago: no longer held, event full.
    evenement_complet = creer_un_evenement(tenant, jauge_max=1)
    reservation = creer_une_ancienne_reservation_gratuite(
        tenant, compte_non_active, evenement_complet, nombre_de_billets=2
    )
    with tenant_context(tenant):
        # `update()` : Reservation.datetime est en auto_now (piège 13.19).
        # / update(): Reservation.datetime is auto_now.
        Reservation.objects.filter(pk=reservation.pk).update(
            datetime=timezone.now() - timedelta(minutes=40)
        )

    reponse = se_connecter_sur_le_guichet(
        client_du_guichet, taches_patchees["mail"], email
    )

    compte = TibilletUser.objects.get(email=email)
    assert compte_connecte(client_du_guichet) == str(compte.pk)
    with tenant_context(tenant):
        reservation.refresh_from_db()
    assert reservation.status == Reservation.CANCELED
    ticket, _state = lire_le_ticket_de_l_url(reponse["HX-Redirect"])
    contenu_du_ticket = lire_un_ticket(ticket, DOMAINE_DU_LIEU)
    assert contenu_du_ticket.get("avertissement")


def test_un_compte_avec_email_error_se_connecte(tenant, menage, taches_patchees):
    client_du_guichet = menage.client_du_guichet()
    email = menage.nouvel_email()
    creer_un_compte(tenant, email, actif=False, email_error=True)

    reponse = se_connecter_sur_le_guichet(
        client_du_guichet, taches_patchees["mail"], email
    )

    assert reponse.status_code == 200
    assert "HX-Redirect" in reponse
    compte = TibilletUser.objects.get(email=email)
    assert not compte.email_error
    assert compte.is_active
    assert compte_connecte(client_du_guichet) == str(compte.pk)


def test_l_email_d_un_terminal_est_refuse_sans_erreur_500(
    tenant, menage, taches_patchees
):
    client_du_guichet = menage.client_du_guichet()
    email = menage.nouvel_email()
    creer_un_compte(tenant, email, espece=TibilletUser.TYPE_TERM)

    reponse = se_connecter_sur_le_guichet(
        client_du_guichet, taches_patchees["mail"], email
    )

    assert reponse.status_code == 200
    assert "HX-Redirect" not in reponse
    assert 'data-testid="login-code-erreur"' in reponse.content.decode()
    assert compte_connecte(client_du_guichet) is None


def test_deja_connecte_sur_le_guichet_le_ticket_part_tout_de_suite(tenant, menage):
    client_du_guichet = menage.client_du_guichet()
    email = menage.nouvel_email()
    compte = creer_un_compte(tenant, email)
    client_du_guichet.force_login(compte)

    reponse = client_du_guichet.get(
        "/sso/", {"lieu": DOMAINE_DU_LIEU, "state": STATE_DE_TEST}
    )

    assert reponse.status_code == 302
    assert reponse.url.startswith(f"https://{DOMAINE_DU_LIEU}/connexion/retour/?")
    ticket, state = lire_le_ticket_de_l_url(reponse.url)
    assert state == STATE_DE_TEST
    assert lire_un_ticket(ticket, DOMAINE_DU_LIEU)["compte"] == str(compte.pk)


# =============================================================================
# Lieu (BaseBillet/views.py)
# =============================================================================


def partir_vers_le_guichet(client_du_lieu, adresse_de_retour):
    """
    GET /connexion/?next=... sur le lieu. Renvoie (réponse, state envoyé au guichet).
    / GET /connexion/ on the venue. Returns (response, state sent to the desk).
    """
    reponse = client_du_lieu.get("/connexion/", {"next": adresse_de_retour})
    state = parse_qs(urlparse(reponse.url).query)["state"][0]
    return reponse, state


def test_connexion_envoie_au_guichet_avec_le_state_en_session():
    client_du_lieu = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)

    reponse, state = partir_vers_le_guichet(client_du_lieu, "/event/x/")

    assert reponse.status_code == 302
    url_du_guichet = urlparse(reponse.url)
    assert url_du_guichet.scheme == "https"
    assert url_du_guichet.netloc == DOMAINE_DU_GUICHET
    assert url_du_guichet.path == "/sso/"
    assert parse_qs(url_du_guichet.query)["lieu"] == [DOMAINE_DU_LIEU]
    assert client_du_lieu.session["sso_state"] == state
    assert client_du_lieu.session["sso_next"] == "/event/x/"


def test_connexion_avec_un_next_vers_un_autre_domaine_garde_la_racine():
    client_du_lieu = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)

    partir_vers_le_guichet(client_du_lieu, "https://site-pirate.example/vol/")

    assert client_du_lieu.session["sso_next"] == "/"


def test_connexion_deja_connecte_redirige_vers_next(tenant, menage):
    email = menage.nouvel_email()
    compte = creer_un_compte(tenant, email)
    client_du_lieu = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)
    client_du_lieu.force_login(compte)

    reponse = client_du_lieu.get("/connexion/", {"next": "/event/x/"})

    assert reponse.status_code == 302
    assert reponse.url == "/event/x/"


def test_retour_avec_un_bon_ticket_connecte_rattache_et_redirige(
    tenant, menage, taches_patchees
):
    email = menage.nouvel_email()
    compte = creer_un_compte(tenant, email)
    compte.client_achat.clear()
    client_du_lieu = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)
    _reponse, state = partir_vers_le_guichet(client_du_lieu, "/event/x/")
    ticket = fabriquer_un_ticket(compte, DOMAINE_DU_LIEU)

    reponse = client_du_lieu.get(
        "/connexion/retour/", {"ticket": ticket, "state": state}
    )

    assert reponse.status_code == 302
    assert reponse.url == "/event/x/"
    assert compte_connecte(client_du_lieu) == str(compte.pk)
    assert compte.client_achat.filter(pk=tenant.pk).exists()
    assert "sso_state" not in client_du_lieu.session


def test_retour_avec_un_mauvais_state_ne_connecte_pas(tenant, menage, taches_patchees):
    email = menage.nouvel_email()
    compte = creer_un_compte(tenant, email)
    client_du_lieu = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)
    partir_vers_le_guichet(client_du_lieu, "/event/x/")
    ticket = fabriquer_un_ticket(compte, DOMAINE_DU_LIEU)

    reponse = client_du_lieu.get(
        "/connexion/retour/", {"ticket": ticket, "state": "un-autre-state"}
    )

    assert reponse.status_code == 302
    assert reponse.url == "/"
    assert compte_connecte(client_du_lieu) is None


def test_retour_avec_un_ticket_rejoue_ne_connecte_pas(tenant, menage, taches_patchees):
    email = menage.nouvel_email()
    compte = creer_un_compte(tenant, email)
    ticket = fabriquer_un_ticket(compte, DOMAINE_DU_LIEU)

    premier_navigateur = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)
    _reponse, premier_state = partir_vers_le_guichet(premier_navigateur, "/")
    premier_navigateur.get(
        "/connexion/retour/", {"ticket": ticket, "state": premier_state}
    )
    assert compte_connecte(premier_navigateur) == str(compte.pk)

    deuxieme_navigateur = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)
    _reponse, deuxieme_state = partir_vers_le_guichet(deuxieme_navigateur, "/")
    deuxieme_navigateur.get(
        "/connexion/retour/", {"ticket": ticket, "state": deuxieme_state}
    )

    assert compte_connecte(deuxieme_navigateur) is None


def test_retour_quand_un_autre_compte_etait_connecte(tenant, menage, taches_patchees):
    compte_precedent = creer_un_compte(tenant, menage.nouvel_email())
    nouveau_compte = creer_un_compte(tenant, menage.nouvel_email())
    client_du_lieu = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)
    client_du_lieu.force_login(compte_precedent)
    # Le state et le next sont posés comme le ferait connexion(). login() vide
    # cette session (autre compte) : connexion_retour doit les avoir lus avant.
    # / State and next set as connexion() would; login() flushes this session.
    session_du_lieu = client_du_lieu.session
    session_du_lieu["sso_state"] = "state-du-navigateur-partage"
    session_du_lieu["sso_next"] = "/event/x/"
    session_du_lieu.save()
    ticket = fabriquer_un_ticket(nouveau_compte, DOMAINE_DU_LIEU)

    reponse = client_du_lieu.get(
        "/connexion/retour/", {"ticket": ticket, "state": "state-du-navigateur-partage"}
    )

    assert reponse.url == "/event/x/"
    assert compte_connecte(client_du_lieu) == str(nouveau_compte.pk)


def test_retour_quand_fedow_est_en_panne_connecte_quand_meme(
    tenant, menage, taches_patchees
):
    email = menage.nouvel_email()
    compte = creer_un_compte(tenant, email)
    taches_patchees["fedow"].side_effect = ConnectionError("Fedow en panne")
    client_du_lieu = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)
    _reponse, state = partir_vers_le_guichet(client_du_lieu, "/event/x/")
    ticket = fabriquer_un_ticket(compte, DOMAINE_DU_LIEU)

    reponse = client_du_lieu.get(
        "/connexion/retour/", {"ticket": ticket, "state": state}
    )

    taches_patchees["fedow"].assert_called_once()
    assert reponse.url == "/event/x/"
    assert compte_connecte(client_du_lieu) == str(compte.pk)


def test_retour_affiche_l_avertissement_du_ticket(tenant, menage, taches_patchees):
    from django.contrib.messages import get_messages

    email = menage.nouvel_email()
    compte = creer_un_compte(tenant, email)
    client_du_lieu = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)
    _reponse, state = partir_vers_le_guichet(client_du_lieu, "/")
    ticket = fabriquer_un_ticket(
        compte, DOMAINE_DU_LIEU, avertissement="Événement complet."
    )

    reponse = client_du_lieu.get(
        "/connexion/retour/", {"ticket": ticket, "state": state}
    )

    textes_des_messages = [
        str(message) for message in get_messages(reponse.wsgi_request)
    ]
    assert "Événement complet." in textes_des_messages


def test_login_fullpage_renvoie_vers_connexion_avec_le_chemin_decode():
    client_du_lieu = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)
    adresse_signee = signing.dumps("/qrcodescanpay/abc/process_qrcode/")

    reponse = client_du_lieu.get("/login/login_fullpage/", {"next": adresse_signee})

    assert reponse.status_code == 302
    assert reponse.url == "/connexion/?next=%2Fqrcodescanpay%2Fabc%2Fprocess_qrcode%2F"


def test_login_fullpage_avec_une_signature_fausse_oublie_next():
    client_du_lieu = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)

    reponse = client_du_lieu.get("/login/login_fullpage/", {"next": "pas-signe"})

    assert reponse.status_code == 302
    assert reponse.url == "/connexion/"


def test_le_lien_d_annulation_de_booking_passe_par_le_guichet_et_garde_next():
    """
    booking/views.py::cancel_confirm envoie un anonyme vers /connexion/?next=<chemin>.
    Ce lien marche tel quel avec la vue connexion : le chemin est gardé en session.
    / booking's cancel_confirm link works as is: next is kept in the session.
    """
    client_du_lieu = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)
    chemin_d_annulation = f"/booking/{uuid4()}/cancel/"

    reponse_de_booking = client_du_lieu.get(chemin_d_annulation)
    assert reponse_de_booking.status_code == 302
    reponse_de_connexion = client_du_lieu.get(reponse_de_booking.url)

    assert urlparse(reponse_de_connexion.url).netloc == DOMAINE_DU_GUICHET
    assert client_du_lieu.session["sso_next"] == chemin_d_annulation


# =============================================================================
# Parcours complet : un lieu, puis un 2e lieu sans retaper de code
# =============================================================================


def test_parcours_complet_puis_deuxieme_lieu_sans_code(tenant, menage, taches_patchees):
    email = menage.nouvel_email()
    client_du_guichet = menage.client_du_guichet()

    # 1er lieu : départ, code sur le guichet, retour.
    # / 1st venue: leave, code on the desk, come back.
    client_du_premier_lieu = ClientDeTest(HTTP_HOST=DOMAINE_DU_LIEU)
    _reponse, state = partir_vers_le_guichet(client_du_premier_lieu, "/event/x/")
    reponse_du_guichet = se_connecter_sur_le_guichet(
        client_du_guichet, taches_patchees["mail"], email, DOMAINE_DU_LIEU, state
    )
    url_de_retour = urlparse(reponse_du_guichet["HX-Redirect"])
    reponse_du_lieu = client_du_premier_lieu.get(
        f"{url_de_retour.path}?{url_de_retour.query}"
    )

    compte = TibilletUser.objects.get(email=email)
    assert reponse_du_lieu.url == "/event/x/"
    assert compte_connecte(client_du_premier_lieu) == str(compte.pk)

    # 2e lieu : le guichet donne le ticket tout de suite, sans code.
    # / 2nd venue: the desk gives the ticket at once, no code.
    nombre_de_codes_envoyes = taches_patchees["mail"].delay.call_count
    client_du_deuxieme_lieu = ClientDeTest(HTTP_HOST=DOMAINE_DU_DEUXIEME_LIEU)
    reponse_du_deuxieme_lieu, deuxieme_state = partir_vers_le_guichet(
        client_du_deuxieme_lieu, "/"
    )
    url_du_guichet = urlparse(reponse_du_deuxieme_lieu.url)
    reponse_du_guichet = client_du_guichet.get(
        f"{url_du_guichet.path}?{url_du_guichet.query}"
    )
    assert reponse_du_guichet.status_code == 302
    url_de_retour = urlparse(reponse_du_guichet.url)
    assert url_de_retour.netloc == DOMAINE_DU_DEUXIEME_LIEU
    client_du_deuxieme_lieu.get(f"{url_de_retour.path}?{url_de_retour.query}")

    assert compte_connecte(client_du_deuxieme_lieu) == str(compte.pk)
    assert taches_patchees["mail"].delay.call_count == nombre_de_codes_envoyes
    deuxieme_lieu = Client.objects.get(schema_name="festival")
    assert compte.client_achat.filter(pk=deuxieme_lieu.pk).exists()
