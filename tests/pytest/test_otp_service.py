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
    @patch("AuthBillet.otp_service.send_mail")
    def test_appelle_send_mail_avec_destinataire(self, mock_send):
        envoyer_email_otp("user@example.com", "123456", "Connexion")
        assert mock_send.called
        _args, kwargs = mock_send.call_args
        assert kwargs["recipient_list"] == ["user@example.com"]

    @patch("AuthBillet.otp_service.send_mail")
    def test_inclut_le_code_dans_le_corps_texte(self, mock_send):
        envoyer_email_otp("u@x.fr", "987654", "Connexion")
        _args, kwargs = mock_send.call_args
        assert "987654" in kwargs["message"]

    @patch("AuthBillet.otp_service.send_mail")
    def test_inclut_le_code_dans_le_corps_html(self, mock_send):
        envoyer_email_otp("u@x.fr", "987654", "Connexion")
        _args, kwargs = mock_send.call_args
        assert "987654" in kwargs["html_message"]

    @patch("AuthBillet.otp_service.send_mail")
    def test_sujet_contient_libelle_action(self, mock_send):
        envoyer_email_otp("u@x.fr", "123456", "Proposer un evenement")
        _args, kwargs = mock_send.call_args
        assert "Proposer un evenement" in str(kwargs["subject"])

    @patch("AuthBillet.otp_service.send_mail")
    def test_footer_contient_nom_organisation_si_fourni(self, mock_send):
        envoyer_email_otp("u@x.fr", "123456", "Test", nom_organisation="Mon Lieu")
        _args, kwargs = mock_send.call_args
        assert "Mon Lieu" in kwargs["message"]
        assert "Mon Lieu" in kwargs["html_message"]
