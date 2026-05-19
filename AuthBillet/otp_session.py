"""
Helper OTP pour stockage en session HTTP.
/ HTTP session helper for OTP storage.

LOCALISATION : AuthBillet/otp_session.py

Wrapper FALC autour de `otp_service` pour le cas "stockage en session".
Chaque flow OTP utilise un prefixe distinct pour pouvoir cohabiter
(ex: "event_proposal" et "login" coexistent dans la meme session HTTP).
"""

from datetime import datetime, timedelta
from typing import Optional

from django.utils import timezone

from AuthBillet.otp_service import (
    OTP_MAX_ATTEMPTS,
    OTP_RESEND_COOLDOWN_SECONDS,
    OTP_TTL_SECONDS,
    envoyer_email_otp,
    generer_code_otp,
    hash_code_otp,
    verifier_code_otp,
)


class OtpSession:
    """
    Gere un flow OTP stocke en session HTTP avec un prefixe donne.
    / Manages an OTP flow stored in HTTP session under a given prefix.
    """

    def __init__(self, request, prefix: str):
        self.request = request
        self.prefix = prefix

    def _cle_session(self, suffixe: str) -> str:
        """
        Construit la cle session : "<prefix>_otp_<suffixe>".
        / Builds the session key.
        """
        return f"{self.prefix}_otp_{suffixe}"

    def start(
        self,
        email: str,
        libelle_action: str,
        nom_organisation: Optional[str] = None,
    ) -> None:
        """
        Genere un code, le stocke (hash), et l'envoie par mail.
        / Generates a code, stores hash, sends email.
        """
        code = generer_code_otp()
        expire_a = timezone.now() + timedelta(seconds=OTP_TTL_SECONDS)
        self.request.session[self._cle_session("email")] = email
        self.request.session[self._cle_session("hash")] = hash_code_otp(code)
        self.request.session[self._cle_session("expires_at")] = expire_a.isoformat()
        self.request.session[self._cle_session("attempts")] = 0
        self.request.session[self._cle_session("last_sent_at")] = timezone.now().isoformat()
        self.request.session[self._cle_session("confirmed")] = False
        envoyer_email_otp(email, code, libelle_action, nom_organisation)

    def verify(self, code_soumis: str) -> bool:
        """
        Verifie le code soumis. Incremente le compteur de tentatives.
        / Verifies the submitted code. Increments attempts counter.
        """
        hash_stocke = self.request.session.get(self._cle_session("hash"))
        expires_at_iso = self.request.session.get(self._cle_session("expires_at"))
        attempts = self.request.session.get(self._cle_session("attempts"), 0)

        if not hash_stocke or not expires_at_iso:
            return False
        if attempts >= OTP_MAX_ATTEMPTS:
            return False
        if timezone.now() > datetime.fromisoformat(expires_at_iso):
            return False

        self.request.session[self._cle_session("attempts")] = attempts + 1
        if verifier_code_otp(code_soumis, hash_stocke):
            self.request.session[self._cle_session("confirmed")] = True
            return True
        return False

    def is_confirmed(self) -> bool:
        """
        Retourne True si le code a deja ete verifie avec succes.
        / Returns True if the code was already verified successfully.
        """
        return bool(self.request.session.get(self._cle_session("confirmed")))

    def email(self) -> str:
        """
        Retourne l'email associe au flow OTP courant (chaine vide si pas demarre).
        / Returns the email tied to the current OTP flow (empty string if not started).
        """
        return self.request.session.get(self._cle_session("email"), "")

    def attempts_remaining(self) -> int:
        """
        Nombre de tentatives restantes avant blocage.
        / Remaining attempts before lockout.
        """
        attempts = self.request.session.get(self._cle_session("attempts"), 0)
        return max(0, OTP_MAX_ATTEMPTS - attempts)

    def can_resend(self) -> bool:
        """
        True si le cooldown est ecoule depuis le dernier envoi.
        / True if the resend cooldown has elapsed.
        """
        last_sent_iso = self.request.session.get(self._cle_session("last_sent_at"))
        if not last_sent_iso:
            return True
        delta = timezone.now() - datetime.fromisoformat(last_sent_iso)
        return delta.total_seconds() >= OTP_RESEND_COOLDOWN_SECONDS

    def seconds_before_resend(self) -> int:
        """
        Secondes a attendre avant de pouvoir renvoyer un code.
        / Seconds to wait before a resend is allowed.
        """
        last_sent_iso = self.request.session.get(self._cle_session("last_sent_at"))
        if not last_sent_iso:
            return 0
        delta = timezone.now() - datetime.fromisoformat(last_sent_iso)
        return max(0, int(OTP_RESEND_COOLDOWN_SECONDS - delta.total_seconds()))

    def reset(self) -> None:
        for suffix in (
            "email", "hash", "expires_at", "attempts",
            "last_sent_at", "confirmed",
        ):
            self.request.session.pop(self._cle_session(suffix), None)
