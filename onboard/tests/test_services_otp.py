"""
Tests des services OTP (generate_otp / verify_otp).
/ Tests for OTP services (generate_otp / verify_otp).

LOCALISATION: onboard/tests/test_services_otp.py

NOTE : on utilise `django.test.SimpleTestCase` (sans DB) car les helpers OTP
sont purement in-memory (hash + comparaison). C'est coherent avec le style
des tests `test_models.py` qui s'executent via `manage.py test` (pas pytest
— `pytest-django` n'est pas installe sur cette branche).
/ NOTE: we use `django.test.SimpleTestCase` (no DB) since OTP helpers are
purely in-memory (hash + comparison). Consistent with `test_models.py`
which runs via `manage.py test` (pytest-django isn't installed here).
"""

from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from onboard.services import generate_otp, verify_otp


class GenerateOtpTests(SimpleTestCase):
    """
    Tests unitaires du helper generate_otp().
    / Unit tests for the generate_otp() helper.
    """

    def test_generate_otp_returns_6_digits(self):
        """
        generate_otp() renvoie un code a 6 chiffres, un hash PBKDF2 non vide,
        et une expiration dans la fenetre [now, now + 11min].
        / generate_otp() returns a 6-digit code, a non-empty PBKDF2 hash,
        and an expiry within [now, now + 11min].
        """
        before = timezone.now()
        otp_clair, otp_hash, expires_at = generate_otp()
        after = timezone.now()

        # Format du clair : exactement 6 chiffres.
        # / Plain code format: exactly 6 digits.
        self.assertRegex(otp_clair, r"^\d{6}$")

        # Le hash est non vide et prefixe par l'algo Django par defaut.
        # / Hash is non-empty and prefixed by Django's default algorithm.
        self.assertTrue(otp_hash)
        self.assertTrue(
            otp_hash.startswith("pbkdf2_sha256$"),
            f"Hash inattendu : {otp_hash!r}",
        )

        # expires_at strictement apres l'instant d'appel.
        # / expires_at is strictly after the call time.
        self.assertGreater(expires_at, before)

        # expires_at <= now + 11min (TTL 10min + marge d'execution).
        # / expires_at <= now + 11min (10min TTL + execution slack).
        self.assertLessEqual(expires_at, after + timedelta(minutes=11))


class VerifyOtpTests(SimpleTestCase):
    """
    Tests unitaires du helper verify_otp().
    / Unit tests for the verify_otp() helper.
    """

    def test_verify_otp_correct(self):
        """
        Un code clair fraichement genere se verifie correctement contre son
        hash.
        / A freshly generated plain code verifies against its hash.
        """
        otp_clair, otp_hash, _ = generate_otp()
        self.assertTrue(verify_otp(otp_clair, otp_hash))

    def test_verify_otp_wrong(self):
        """
        Un code different du clair genere ne matche pas.
        / A code different from the generated one does not match.
        """
        otp_clair, otp_hash, _ = generate_otp()
        # On construit un autre code a 6 chiffres garanti different.
        # / Build another 6-digit code guaranteed to differ.
        autre = "000000" if otp_clair != "000000" else "111111"
        self.assertFalse(verify_otp(autre, otp_hash))

    def test_verify_otp_empty_hash_returns_false(self):
        """
        Si le hash stocke est vide / None, la verification renvoie False
        sans lever d'exception.
        / If the stored hash is empty / None, verification returns False
        without raising.
        """
        self.assertFalse(verify_otp("123456", ""))
        self.assertFalse(verify_otp("123456", None))

    def test_verify_otp_empty_input_returns_false(self):
        """
        Si l'utilisateur ne saisit rien, la verification renvoie False
        sans lever d'exception.
        / If the user submits nothing, verification returns False
        without raising.
        """
        _, otp_hash, _ = generate_otp()
        self.assertFalse(verify_otp("", otp_hash))
        self.assertFalse(verify_otp(None, otp_hash))

    def test_verify_otp_invalid_hash_format_returns_false(self):
        """
        Un hash de format invalide ne fait pas exploser la fonction : on
        renvoie False.
        / A malformed hash does not crash the function: we return False.
        """
        # Chaine non-vide mais pas un hash Django valide.
        # / Non-empty string but not a valid Django hash.
        self.assertFalse(verify_otp("123456", "pas-un-hash-valide"))
