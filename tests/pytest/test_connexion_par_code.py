"""
Tests du service de connexion par code (envoi et vérification du code).
/ Tests of the login-by-code service (sending and checking the code).

LOCALISATION : tests/pytest/test_connexion_par_code.py
Code testé : AuthBillet/connexion_par_code.py, et la tâche
BaseBillet/tasks.py::code_de_connexion_celery_mailer.

PIÈGES (tests/PIEGES.md) :
- Le cache est le VRAI memcached, partagé avec le serveur de dev. On l'isole sans
  le vider : un email et une IP uniques par test, et `cache.delete_many` de leurs
  clés en fin de test. Jamais `cache.clear()` : sur memcached c'est un
  `flush_all`, tous lieux confondus (section « Ne PAS utiliser `cache.clear()` »).
- La tâche mail est patchée : un `.delay()` direct part vers le vrai broker (le
  projet n'a pas de `task_always_eager`).
- Le guichet tourne sur `public` : les appels au service sont faits dans
  `tenant_context(<tenant public>)`. Le lieu est un vrai tenant
  (`tenant_context`, pas `schema_context` qui pose un FakeTenant, piège 9.1).
/ Real shared memcached: unique email/IP per test and targeted delete_many,
never cache.clear(). Mail task patched. Service called on `public`.
"""

import logging
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.core.cache import cache, caches
from django.db import connection
from django.test import override_settings
from django_tenants.utils import tenant_context

from AuthBillet.connexion_par_code import (
    cle_cache,
    cle_cache_ip,
    envoyer_un_code_de_connexion,
    verifier_le_code_de_connexion,
)
from Customers.models import Client

# Chemin de la tâche mail à patcher. Le service l'importe au moment de l'appel :
# patcher l'attribut du module BaseBillet.tasks suffit.
# / Mail task path. The service imports it at call time.
CHEMIN_DE_LA_TACHE_MAIL = "BaseBillet.tasks.code_de_connexion_celery_mailer"

SUFFIXES_DES_CLES_D_UN_EMAIL = [
    "empreinte",
    "essais",
    "dernier_envoi",
    "envois_de_l_heure",
]


@pytest.fixture
def tenant_public():
    """Le tenant du guichet (schéma public). / The public tenant (login desk)."""
    return Client.objects.get(schema_name="public")


@pytest.fixture
def cles_a_nettoyer(tenant_public):
    """
    Fabrique des emails et des IP uniques, et efface leurs clés du cache en fin de test.
    / Makes unique emails and IPs, and deletes their cache keys after the test.

    Les clés vivent sur le schéma public : on les efface dans son contexte.
    / Keys live on the public schema: we delete them in its context.
    """
    emails_utilises = []
    ips_utilisees = [None]

    def nouvel_email():
        email = f"code-{uuid4().hex[:8]}@test.local"
        emails_utilises.append(email)
        return email

    def nouvelle_ip():
        # Plage IPv6 2001:db8::/32 : réservée à la documentation, jamais routée.
        # / 2001:db8::/32 is reserved for documentation.
        ip = f"2001:db8::{uuid4().hex[:4]}:{uuid4().hex[:4]}"
        ips_utilisees.append(ip)
        return ip

    yield nouvel_email, nouvelle_ip

    cles = []
    for email in emails_utilises:
        for suffixe in SUFFIXES_DES_CLES_D_UN_EMAIL:
            cles.append(cle_cache(email, suffixe))
    for ip in ips_utilisees:
        cles.append(cle_cache_ip(ip))
    with tenant_context(tenant_public):
        cache.delete_many(cles)


def code_envoye_par_le_dernier_mail(tache_mail_patchee):
    """Le code en clair passé au dernier .delay(). / Cleartext code of the last .delay()."""
    arguments_positionnels = tache_mail_patchee.delay.call_args.args
    return arguments_positionnels[1]


def oublier_le_dernier_envoi(tenant_public, email):
    """
    Efface la clé du délai de 60 s, pour enchaîner deux envois sans attendre.
    / Deletes the 60 s delay key, to send twice without waiting.
    """
    with tenant_context(tenant_public):
        caches["verrous"].delete(cle_cache(email, "dernier_envoi"))


# --- Envoi du code / Sending the code ---


def test_le_code_est_garde_en_cache_et_le_mail_programme(
    tenant, tenant_public, cles_a_nettoyer
):
    nouvel_email, nouvelle_ip = cles_a_nettoyer
    email = nouvel_email()

    with patch(CHEMIN_DE_LA_TACHE_MAIL) as tache_mail:
        with tenant_context(tenant_public):
            resultat = envoyer_un_code_de_connexion(email, nouvelle_ip(), "fr", tenant)
            empreinte_en_cache = cache.get(cle_cache(email, "empreinte"))

    assert resultat == "envoye"
    tache_mail.delay.assert_called_once()
    email_du_mail, code_du_mail, langue_du_mail = tache_mail.delay.call_args.args
    assert email_du_mail == email
    assert langue_du_mail == "fr"
    # On garde l'empreinte, jamais le code en clair.
    # / The fingerprint is kept, never the cleartext code.
    assert empreinte_en_cache is not None
    assert empreinte_en_cache != code_du_mail


def test_l_email_est_normalise_avant_tout_usage(tenant, tenant_public, cles_a_nettoyer):
    nouvel_email, nouvelle_ip = cles_a_nettoyer
    email = nouvel_email()
    email_tape_avec_majuscules_et_espaces = f"  {email.upper()}  "

    with patch(CHEMIN_DE_LA_TACHE_MAIL) as tache_mail:
        with tenant_context(tenant_public):
            envoyer_un_code_de_connexion(
                email_tape_avec_majuscules_et_espaces, nouvelle_ip(), "fr", tenant
            )
            code = code_envoye_par_le_dernier_mail(tache_mail)
            resultat = verifier_le_code_de_connexion(
                email_tape_avec_majuscules_et_espaces, code
            )

    assert tache_mail.delay.call_args.args[0] == email
    assert resultat == "ok"


def test_un_deuxieme_envoi_dans_la_minute_demande_d_attendre(
    tenant, tenant_public, cles_a_nettoyer
):
    nouvel_email, nouvelle_ip = cles_a_nettoyer
    email = nouvel_email()
    ip = nouvelle_ip()

    with patch(CHEMIN_DE_LA_TACHE_MAIL) as tache_mail:
        with tenant_context(tenant_public):
            premier_resultat = envoyer_un_code_de_connexion(email, ip, "fr", tenant)
            deuxieme_resultat = envoyer_un_code_de_connexion(email, ip, "fr", tenant)

    assert premier_resultat == "envoye"
    assert deuxieme_resultat == "attendre"
    assert tache_mail.delay.call_count == 1


def test_le_plafond_par_email_bloque_le_onzieme_code_de_l_heure(
    tenant, tenant_public, cles_a_nettoyer
):
    nouvel_email, nouvelle_ip = cles_a_nettoyer
    email = nouvel_email()
    ip = nouvelle_ip()

    resultats = []
    with patch(CHEMIN_DE_LA_TACHE_MAIL) as tache_mail:
        for _numero in range(11):
            oublier_le_dernier_envoi(tenant_public, email)
            with tenant_context(tenant_public):
                resultats.append(envoyer_un_code_de_connexion(email, ip, "fr", tenant))

    assert resultats[:10] == ["envoye"] * 10
    assert resultats[10] == "trop_de_demandes"
    assert tache_mail.delay.call_count == 10


@override_settings(CONNEXION_CODE_PLAFOND_IP_10_MIN=3)
def test_le_plafond_par_ip_bloque_et_journalise_un_avertissement(
    tenant, tenant_public, cles_a_nettoyer, caplog
):
    nouvel_email, nouvelle_ip = cles_a_nettoyer
    ip = nouvelle_ip()

    resultats = []
    with patch(CHEMIN_DE_LA_TACHE_MAIL) as tache_mail:
        with caplog.at_level(logging.WARNING, logger="AuthBillet.connexion_par_code"):
            with tenant_context(tenant_public):
                for _numero in range(4):
                    # Un email différent à chaque fois : seul le plafond par IP joue.
                    # / A new email each time: only the per-IP limit applies.
                    resultats.append(
                        envoyer_un_code_de_connexion(nouvel_email(), ip, "fr", tenant)
                    )

    assert resultats == ["envoye", "envoye", "envoye", "trop_de_demandes"]
    assert tache_mail.delay.call_count == 3
    avertissements_avec_l_ip = []
    for enregistrement in caplog.records:
        if (
            enregistrement.levelno == logging.WARNING
            and ip in enregistrement.getMessage()
        ):
            avertissements_avec_l_ip.append(enregistrement)
    assert len(avertissements_avec_l_ip) == 1


@override_settings(CONNEXION_CODE_PLAFOND_IP_10_MIN=1)
def test_une_ip_inconnue_n_est_pas_comptee(tenant, tenant_public, cles_a_nettoyer):
    nouvel_email, _nouvelle_ip = cles_a_nettoyer

    with patch(CHEMIN_DE_LA_TACHE_MAIL) as tache_mail:
        with tenant_context(tenant_public):
            premier_resultat = envoyer_un_code_de_connexion(
                nouvel_email(), None, "fr", tenant
            )
            deuxieme_resultat = envoyer_un_code_de_connexion(
                nouvel_email(), None, "fr", tenant
            )

    assert premier_resultat == "envoye"
    assert deuxieme_resultat == "envoye"
    assert tache_mail.delay.call_count == 2


@override_settings(DEBUG=False)
def test_hors_debug_le_code_n_est_pas_journalise(
    tenant, tenant_public, cles_a_nettoyer, caplog
):
    nouvel_email, nouvelle_ip = cles_a_nettoyer

    with patch(CHEMIN_DE_LA_TACHE_MAIL) as tache_mail:
        with caplog.at_level(logging.DEBUG):
            with tenant_context(tenant_public):
                envoyer_un_code_de_connexion(
                    nouvel_email(), nouvelle_ip(), "fr", tenant
                )
    code = code_envoye_par_le_dernier_mail(tache_mail)

    assert code not in caplog.text


@override_settings(DEBUG=True)
def test_en_debug_le_code_est_journalise(
    tenant, tenant_public, cles_a_nettoyer, caplog
):
    nouvel_email, nouvelle_ip = cles_a_nettoyer

    with patch(CHEMIN_DE_LA_TACHE_MAIL) as tache_mail:
        with caplog.at_level(logging.INFO, logger="AuthBillet.connexion_par_code"):
            with tenant_context(tenant_public):
                envoyer_un_code_de_connexion(
                    nouvel_email(), nouvelle_ip(), "fr", tenant
                )
    code = code_envoye_par_le_dernier_mail(tache_mail)

    assert code in caplog.text


def test_les_cles_sont_sur_public_et_le_mail_programme_dans_le_contexte_du_lieu(
    tenant, tenant_public, cles_a_nettoyer
):
    nouvel_email, nouvelle_ip = cles_a_nettoyer
    email = nouvel_email()

    # La tâche patchée note le schéma courant au moment du .delay().
    # / The patched task records the current schema at .delay() time.
    schemas_vus_par_la_tache = []

    def noter_le_schema(*args, **kwargs):
        schemas_vus_par_la_tache.append(connection.schema_name)

    tache_mail = MagicMock()
    tache_mail.delay.side_effect = noter_le_schema

    with patch(CHEMIN_DE_LA_TACHE_MAIL, tache_mail):
        with tenant_context(tenant_public):
            envoyer_un_code_de_connexion(email, nouvelle_ip(), "fr", tenant)
            empreinte_vue_sur_public = cache.get(cle_cache(email, "empreinte"))
            schema_apres_l_envoi = connection.schema_name

    with tenant_context(tenant):
        empreinte_vue_sur_le_lieu = cache.get(cle_cache(email, "empreinte"))

    assert schemas_vus_par_la_tache == [tenant.schema_name]
    assert schema_apres_l_envoi == "public"
    assert empreinte_vue_sur_public is not None
    assert empreinte_vue_sur_le_lieu is None


# --- Vérification du code / Checking the code ---


def test_le_bon_code_renvoie_ok(tenant, tenant_public, cles_a_nettoyer):
    nouvel_email, nouvelle_ip = cles_a_nettoyer
    email = nouvel_email()

    with patch(CHEMIN_DE_LA_TACHE_MAIL) as tache_mail:
        with tenant_context(tenant_public):
            envoyer_un_code_de_connexion(email, nouvelle_ip(), "fr", tenant)
            resultat = verifier_le_code_de_connexion(
                email, code_envoye_par_le_dernier_mail(tache_mail)
            )

    assert resultat == "ok"


def test_un_code_faux_renvoie_faux(tenant, tenant_public, cles_a_nettoyer):
    nouvel_email, nouvelle_ip = cles_a_nettoyer
    email = nouvel_email()

    with patch("AuthBillet.connexion_par_code.generer_code_otp", return_value="111111"):
        with patch(CHEMIN_DE_LA_TACHE_MAIL):
            with tenant_context(tenant_public):
                envoyer_un_code_de_connexion(email, nouvelle_ip(), "fr", tenant)
                resultat = verifier_le_code_de_connexion(email, "222222")

    assert resultat == "faux"


def test_sans_code_demande_ou_code_expire_renvoie_expire(
    tenant, tenant_public, cles_a_nettoyer
):
    nouvel_email, nouvelle_ip = cles_a_nettoyer
    email = nouvel_email()

    with patch(CHEMIN_DE_LA_TACHE_MAIL) as tache_mail:
        with tenant_context(tenant_public):
            envoyer_un_code_de_connexion(email, nouvelle_ip(), "fr", tenant)
            code = code_envoye_par_le_dernier_mail(tache_mail)
            # memcached efface l'empreinte au bout de 10 minutes : on l'efface nous-mêmes.
            # / memcached drops the fingerprint after 10 minutes: we drop it ourselves.
            cache.delete(cle_cache(email, "empreinte"))
            resultat = verifier_le_code_de_connexion(email, code)

    assert resultat == "expire"


def test_le_cinquieme_code_faux_bloque_et_le_bon_code_ne_passe_plus(
    tenant, tenant_public, cles_a_nettoyer
):
    nouvel_email, nouvelle_ip = cles_a_nettoyer
    email = nouvel_email()

    resultats = []
    with patch("AuthBillet.connexion_par_code.generer_code_otp", return_value="111111"):
        with patch(CHEMIN_DE_LA_TACHE_MAIL):
            with tenant_context(tenant_public):
                envoyer_un_code_de_connexion(email, nouvelle_ip(), "fr", tenant)
                for _numero in range(5):
                    resultats.append(verifier_le_code_de_connexion(email, "999999"))
                resultat_du_bon_code = verifier_le_code_de_connexion(email, "111111")

    assert resultats == ["faux", "faux", "faux", "faux", "bloque"]
    assert resultat_du_bon_code == "bloque"


def test_le_bon_code_passe_au_cinquieme_essai(tenant, tenant_public, cles_a_nettoyer):
    nouvel_email, nouvelle_ip = cles_a_nettoyer
    email = nouvel_email()

    with patch("AuthBillet.connexion_par_code.generer_code_otp", return_value="111111"):
        with patch(CHEMIN_DE_LA_TACHE_MAIL):
            with tenant_context(tenant_public):
                envoyer_un_code_de_connexion(email, nouvelle_ip(), "fr", tenant)
                for _numero in range(4):
                    verifier_le_code_de_connexion(email, "999999")
                resultat = verifier_le_code_de_connexion(email, "111111")

    assert resultat == "ok"


def test_le_code_ne_sert_qu_une_fois(tenant, tenant_public, cles_a_nettoyer):
    nouvel_email, nouvelle_ip = cles_a_nettoyer
    email = nouvel_email()

    with patch(CHEMIN_DE_LA_TACHE_MAIL) as tache_mail:
        with tenant_context(tenant_public):
            envoyer_un_code_de_connexion(email, nouvelle_ip(), "fr", tenant)
            code = code_envoye_par_le_dernier_mail(tache_mail)
            premier_resultat = verifier_le_code_de_connexion(email, code)
            deuxieme_resultat = verifier_le_code_de_connexion(email, code)

    assert premier_resultat == "ok"
    assert deuxieme_resultat == "expire"


def test_un_nouveau_code_remplace_l_ancien_et_remet_les_essais_a_zero(
    tenant, tenant_public, cles_a_nettoyer
):
    nouvel_email, nouvelle_ip = cles_a_nettoyer
    email = nouvel_email()
    ip = nouvelle_ip()

    with patch(
        "AuthBillet.connexion_par_code.generer_code_otp",
        side_effect=["111111", "222222"],
    ):
        with patch(CHEMIN_DE_LA_TACHE_MAIL):
            with tenant_context(tenant_public):
                envoyer_un_code_de_connexion(email, ip, "fr", tenant)
                # 4 essais faux sur le premier code : il n'en reste qu'un.
                # / 4 wrong attempts on the first code: one left.
                for _numero in range(4):
                    verifier_le_code_de_connexion(email, "999999")

            oublier_le_dernier_envoi(tenant_public, email)

            with tenant_context(tenant_public):
                envoyer_un_code_de_connexion(email, ip, "fr", tenant)
                resultat_de_l_ancien_code = verifier_le_code_de_connexion(
                    email, "111111"
                )
                resultat_du_nouveau_code = verifier_le_code_de_connexion(
                    email, "222222"
                )

    # L'ancien code est faux (et pas "bloque" : les essais sont repartis de 0).
    # / The old code is wrong (not "bloque": attempts restarted at 0).
    assert resultat_de_l_ancien_code == "faux"
    assert resultat_du_nouveau_code == "ok"


# --- Tâche mail / Mail task ---


def test_la_tache_mail_journalise_une_erreur_si_le_mail_n_est_pas_parti(tenant, caplog):
    from BaseBillet.tasks import code_de_connexion_celery_mailer

    email = f"code-{uuid4().hex[:8]}@test.local"
    with patch("BaseBillet.tasks.envoyer_email_otp", return_value=None) as envoi_patche:
        with caplog.at_level(logging.ERROR, logger="BaseBillet.tasks"):
            with tenant_context(tenant):
                # Appel direct : la tâche tourne tout de suite, sans broker.
                # / Direct call: the task runs now, without a broker.
                code_de_connexion_celery_mailer(email, "123456", "fr")

    envoi_patche.assert_called_once()
    assert envoi_patche.call_args.args == (email, "123456")
    erreurs_avec_l_email = []
    for enregistrement in caplog.records:
        if (
            enregistrement.levelno == logging.ERROR
            and email in enregistrement.getMessage()
        ):
            erreurs_avec_l_email.append(enregistrement)
    assert len(erreurs_avec_l_email) == 1
