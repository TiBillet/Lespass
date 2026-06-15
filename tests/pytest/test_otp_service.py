"""
Tests unitaires du service OTP stateless.
/ Unit tests for the stateless OTP service.

LOCALISATION : tests/pytest/test_otp_service.py

Pas de DB, pas de tenant — service pur.
/ No DB, no tenant — pure service.
"""

import re
from unittest.mock import patch

import pytest

from AuthBillet.otp_service import (
    OTP_LENGTH,
    OTP_MAX_ATTEMPTS,
    OTP_RESEND_COOLDOWN_SECONDS,
    OTP_TTL_SECONDS,
    envoyer_email_otp,
    generer_code_otp,
    hash_code_otp,
    verifier_code_otp,
)


class TestGenererCodeOtp:
    def test_a_6_chiffres_exactement(self):
        code = generer_code_otp()
        assert len(code) == OTP_LENGTH == 6

    def test_uniquement_des_chiffres(self):
        code = generer_code_otp()
        assert re.fullmatch(r"\d{6}", code)

    def test_aleatoire_sur_100_echantillons(self):
        # 100 codes generes -> au moins 95 differents
        # / 100 codes generated -> at least 95 distinct
        codes = {generer_code_otp() for _unused in range(100)}
        assert len(codes) >= 95


class TestHashCodeOtp:
    def test_deterministe(self):
        # Meme code -> meme hash
        # / Same code -> same hash
        assert hash_code_otp("123456") == hash_code_otp("123456")

    def test_hash_different_du_code(self):
        assert hash_code_otp("123456") != "123456"

    def test_longueur_64_caracteres_hex(self):
        # SHA-256 hex = 64 chars
        h = hash_code_otp("123456")
        assert len(h) == 64
        assert re.fullmatch(r"[0-9a-f]{64}", h)


class TestVerifierCodeOtp:
    def test_succes_avec_bon_code(self):
        h = hash_code_otp("123456")
        assert verifier_code_otp("123456", h) is True

    def test_echec_avec_mauvais_code(self):
        h = hash_code_otp("123456")
        assert verifier_code_otp("999999", h) is False

    def test_echec_avec_code_vide(self):
        h = hash_code_otp("123456")
        assert verifier_code_otp("", h) is False

    def test_echec_avec_hash_vide(self):
        assert verifier_code_otp("123456", "") is False


class TestConstantes:
    def test_ttl_aligne_sur_10_minutes(self):
        assert OTP_TTL_SECONDS == 600

    def test_max_attempts_a_5(self):
        assert OTP_MAX_ATTEMPTS == 5

    def test_cooldown_resend_a_60s(self):
        assert OTP_RESEND_COOLDOWN_SECONDS == 60


class TestEnvoyerEmailOtp:
    """
    Le service OTP delegue l'envoi a `BaseBillet.tasks.CeleryMailerClass`
    (pattern projet, cf. onboard/tasks.py). On mocke la classe au point
    d'utilisation pour verifier les arguments passes et l'appel a `.send()`.
    / The OTP service delegates sending to CeleryMailerClass (project
    pattern). We mock the class at usage point and verify args + .send().
    """

    @patch("BaseBillet.tasks.CeleryMailerClass")
    def test_appelle_celery_mailer_avec_destinataire(self, MockMailer):
        envoyer_email_otp("user@example.com", "123456", "Connexion")
        assert MockMailer.called
        _args, kwargs = MockMailer.call_args
        assert kwargs["email"] == "user@example.com"
        MockMailer.return_value.send.assert_called_once()

    @patch("BaseBillet.tasks.CeleryMailerClass")
    def test_inclut_le_code_dans_le_corps_texte(self, MockMailer):
        envoyer_email_otp("u@x.fr", "987654", "Connexion")
        _args, kwargs = MockMailer.call_args
        # Le texte brut est pre-rendu avant l'instanciation.
        # / Plain text is pre-rendered before instantiation.
        assert "987654" in kwargs["text"]

    @patch("BaseBillet.tasks.CeleryMailerClass")
    def test_passe_template_html_avec_code_dans_le_contexte(self, MockMailer):
        # Le HTML est rendu cote CeleryMailerClass via le template +
        # contexte. On verifie ici qu'on passe bien le code dans le ctx.
        # / HTML rendered by CeleryMailerClass from template + context.
        envoyer_email_otp("u@x.fr", "987654", "Connexion")
        _args, kwargs = MockMailer.call_args
        assert kwargs["template"] == "auth/emails/otp_code.html"
        assert kwargs["context"]["code"] == "987654"

    @patch("BaseBillet.tasks.CeleryMailerClass")
    def test_sujet_contient_libelle_action(self, MockMailer):
        envoyer_email_otp("u@x.fr", "123456", "Proposer un evenement")
        _args, kwargs = MockMailer.call_args
        assert "Proposer un evenement" in str(kwargs["title"])

    @patch("BaseBillet.tasks.CeleryMailerClass")
    def test_footer_contient_nom_organisation_si_fourni(self, MockMailer):
        envoyer_email_otp("u@x.fr", "123456", "Test", nom_organisation="Mon Lieu")
        _args, kwargs = MockMailer.call_args
        # Le texte brut contient le nom (template .txt rendu en amont).
        # Le HTML est rendu cote CeleryMailerClass ; on verifie via ctx.
        # / Plain text rendered upstream contains the name. HTML rendered
        # by CeleryMailerClass; we verify via the passed context.
        assert "Mon Lieu" in kwargs["text"]
        assert kwargs["context"]["nom_organisation"] == "Mon Lieu"
