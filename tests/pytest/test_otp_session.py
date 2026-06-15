"""
Tests du helper OtpSession (stockage en session HTTP).
/ Tests for the OtpSession helper (HTTP session storage).

LOCALISATION : tests/pytest/test_otp_session.py
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils import timezone

from AuthBillet.otp_service import hash_code_otp
from AuthBillet.otp_session import OtpSession


@pytest.fixture
def request_avec_session():
    """
    Fournit un objet request Django avec session active.
    / Provides a Django request with an active session.

    Note : on n'appelle pas `session.save()` pour eviter un acces DB
    inutile dans ces tests unitaires (la session dict-like fonctionne en memoire).
    / Note: we skip `session.save()` to avoid needless DB access in these unit tests
    (the dict-like session works in memory).
    """
    rf = RequestFactory()
    request = rf.get("/")
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    return request


class TestOtpSessionStart:
    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_pose_les_cles_en_session(self, _mock_mail, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="test_flow")
        otp.start("user@example.com", libelle_action="Test")
        s = request_avec_session.session
        assert s["test_flow_otp_email"] == "user@example.com"
        assert "test_flow_otp_hash" in s
        assert "test_flow_otp_expires_at" in s
        assert s["test_flow_otp_attempts"] == 0
        assert s["test_flow_otp_confirmed"] is False

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_envoie_email_avec_libelle_action(self, mock_mail, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="test_flow")
        otp.start("u@x.fr", libelle_action="Proposer un evenement")
        assert mock_mail.called
        _args, kwargs = mock_mail.call_args
        # 3eme argument positionnel = libelle_action
        # / 3rd positional arg = libelle_action
        assert mock_mail.call_args[0][2] == "Proposer un evenement"


class TestOtpSessionVerify:
    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_code_correct_marque_confirmed(self, _mock_mail, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="test_flow")
        otp.start("u@x.fr", libelle_action="Test")
        # On ecrase le hash de la session par un hash connu pour pouvoir
        # tester le code en clair correspondant.
        # / We override the session hash with a known one so we can verify
        # the matching cleartext code.
        request_avec_session.session["test_flow_otp_hash"] = hash_code_otp("000111")
        assert otp.verify("000111") is True
        assert otp.is_confirmed() is True

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_code_incorrect_retourne_false_et_increment(self, _mock_mail, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="test_flow")
        otp.start("u@x.fr", libelle_action="Test")
        request_avec_session.session["test_flow_otp_hash"] = hash_code_otp("000111")
        assert otp.verify("999999") is False
        assert request_avec_session.session["test_flow_otp_attempts"] == 1
        assert otp.is_confirmed() is False

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_max_attempts_retourne_false_meme_si_code_correct(self, _mock_mail, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="test_flow")
        otp.start("u@x.fr", libelle_action="Test")
        request_avec_session.session["test_flow_otp_hash"] = hash_code_otp("000111")
        request_avec_session.session["test_flow_otp_attempts"] = 5
        assert otp.verify("000111") is False

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_expiration_retourne_false(self, _mock_mail, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="test_flow")
        otp.start("u@x.fr", libelle_action="Test")
        request_avec_session.session["test_flow_otp_hash"] = hash_code_otp("000111")
        # Force une expiration dans le passe / Force expiry in the past
        past = (timezone.now() - timedelta(seconds=10)).isoformat()
        request_avec_session.session["test_flow_otp_expires_at"] = past
        assert otp.verify("000111") is False

    def test_sans_session_prealable_retourne_false(self, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="absent")
        assert otp.verify("000111") is False


class TestOtpSessionState:
    def test_is_confirmed_initialement_false(self, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="x")
        assert otp.is_confirmed() is False

    def test_email_retourne_chaine_vide_si_pas_start(self, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="x")
        assert otp.email() == ""

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_attempts_remaining_decroit(self, _mock_mail, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="x")
        otp.start("u@x.fr", libelle_action="Test")
        request_avec_session.session["x_otp_hash"] = hash_code_otp("000111")
        assert otp.attempts_remaining() == 5
        otp.verify("999999")
        assert otp.attempts_remaining() == 4


class TestOtpSessionResend:
    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_can_resend_true_apres_cooldown(self, _mock_mail, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="x")
        otp.start("u@x.fr", libelle_action="Test")
        past = (timezone.now() - timedelta(seconds=120)).isoformat()
        request_avec_session.session["x_otp_last_sent_at"] = past
        assert otp.can_resend() is True

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_can_resend_false_avant_cooldown(self, _mock_mail, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="x")
        otp.start("u@x.fr", libelle_action="Test")
        # last_sent_at = maintenant -> false
        # / last_sent_at = now -> false
        assert otp.can_resend() is False

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_seconds_before_resend_positif(self, _mock_mail, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="x")
        otp.start("u@x.fr", libelle_action="Test")
        assert 0 < otp.seconds_before_resend() <= 60


class TestOtpSessionReset:
    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_efface_toutes_les_cles_du_prefixe(self, _mock_mail, request_avec_session):
        otp = OtpSession(request_avec_session, prefix="x")
        otp.start("u@x.fr", libelle_action="Test")
        otp.reset()
        s = request_avec_session.session
        for suffix in ("email", "hash", "expires_at", "attempts", "last_sent_at", "confirmed"):
            assert f"x_otp_{suffix}" not in s

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_ne_touche_pas_aux_cles_d_autres_prefixes(self, _mock_mail, request_avec_session):
        otp_a = OtpSession(request_avec_session, prefix="flow_a")
        otp_b = OtpSession(request_avec_session, prefix="flow_b")
        otp_a.start("a@x.fr", libelle_action="A")
        otp_b.start("b@x.fr", libelle_action="B")
        otp_a.reset()
        assert request_avec_session.session.get("flow_b_otp_email") == "b@x.fr"
