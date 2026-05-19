# Plan d'implémentation — Chantier 01 (EVENT_WIZARD)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Hub documentaire :** [INDEX.md](INDEX.md) — **Spec source :** [SPEC.md](SPEC.md)
> **Hub OTP lié :** [../OTP/SPEC.md](../OTP/SPEC.md) (session S1 ci-dessous implémente le chantier 01 du hub OTP)
>
> **Garde-fous projet (rappel mainteneur) :**
> - **JAMAIS d'opération `git`** (commit/add/push/checkout --/stash/reset/clean). Les étapes « Préparer le commit » de ce plan OUTPUTENT un message de commit suggéré ; le mainteneur l'exécute lui-même.
> - **Ne JAMAIS de `Co-Authored-By: Claude` dans les messages de commit.**
> - **Ne pas lancer `runserver_plus`** — le serveur tourne déjà dans byobu sur `:8002`.
> - **Pas de `ruff format` sur fichiers existants** — uniquement sur fichiers neufs créés par ce plan.
> - **Pas de `makemessages` / `compilemessages` autonome** — le mainteneur s'en occupe en fin de session.
> - **Tests pytest** : `docker exec lespass_django poetry run pytest <chemin> -q`.

**Goal :** Implémenter deux wizards de création d'évènement (admin et public anonyme avec OTP), plus un service OTP DRY réutilisable, plus la modération admin via badge Unfold.

**Architecture :** Service OTP stateless dans `AuthBillet/` (consommé par le wizard public). Vues `EventWizardAdmin` et `EventWizardPublic` dans `BaseBillet/views.py`. Stockage en session HTTP — pas de modèle draft. Champ `Event.is_proposal` pour la modération.

**Tech Stack :** Django 5.x, DRF (ViewSet+Serializer explicite), HTMX/CSS-only toggles, django-tenants, django-unfold, pytest, pytest-django.

---

## Vue d'ensemble des sessions

| Session | Sujet | Durée estimée | Bloque |
|---|---|---|---|
| S1 | Service OTP DRY (`AuthBillet/otp_service.py` + `otp_session.py` + templates email + tests) | 3-4 h | S4 |
| S2 | Modèle `Event.is_proposal` + cleanup de l'offcanvas existant | 1-2 h | S3, S5 |
| S3 | Wizard admin (2 steps) + tests | 3-4 h | — |
| S4 | Wizard public (OTP + 2 steps + done) + tests | 4-5 h | — |
| S5 | Modération admin (badge sidebar + filtre + action bulk) + boutons event/list | 2 h | — |
| S6 | Doc (`A TESTER`) + CHANGELOG + traductions (mainteneur) | 1 h | — |

**Ordre recommandé** : S1 → S2 → S3 puis S4 (parallélisable avec S3 si subagents), puis S5 → S6.

---

## Session S1 — Service OTP DRY

**Référence spec :** [../OTP/SPEC.md](../OTP/SPEC.md) sections 4, 5, 7, 8.

### Files

- Create: `AuthBillet/otp_service.py`
- Create: `AuthBillet/otp_session.py`
- Create: `AuthBillet/templates/auth/emails/otp_code.html`
- Create: `AuthBillet/templates/auth/emails/otp_code.txt`
- Create: `tests/pytest/test_otp_service.py`
- Create: `tests/pytest/test_otp_session.py`

### S1.1 — Service stateless : test FAIL pour la génération

- [ ] **S1.1.1 — Créer le fichier `tests/pytest/test_otp_service.py` avec les premiers tests qui DOIVENT FAIL**

```python
"""
Tests unitaires du service OTP stateless.
/ Unit tests for the stateless OTP service.

LOCALISATION : tests/pytest/test_otp_service.py

Pas de DB, pas de tenant — service pur.
/ No DB, no tenant — pure service.
"""

import re

import pytest

from AuthBillet.otp_service import (
    OTP_LENGTH,
    OTP_MAX_ATTEMPTS,
    OTP_RESEND_COOLDOWN_SECONDS,
    OTP_TTL_SECONDS,
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
        codes = {generer_code_otp() for _ in range(100)}
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
```

- [ ] **S1.1.2 — Lancer les tests : ils DOIVENT échouer (module absent)**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_otp_service.py -q`
Expected : `ModuleNotFoundError: No module named 'AuthBillet.otp_service'`

### S1.2 — Service stateless : implémentation minimale (3 fonctions pures)

- [ ] **S1.2.1 — Créer `AuthBillet/otp_service.py`**

```python
"""
Service OTP stateless reutilisable.
/ Stateless reusable OTP service.

LOCALISATION : AuthBillet/otp_service.py

Genere, hashe, verifie et envoie un code OTP a 6 chiffres.
Ne stocke RIEN — l'appelant choisit ou poser le hash et l'expiration
(session HTTP, modele DB, cache Redis...).

Voir TECH_DOC/SESSIONS/OTP/SPEC.md pour la spec complete.
/ See TECH_DOC/SESSIONS/OTP/SPEC.md for the full spec.
"""

import hashlib
import hmac
import secrets
from typing import Optional

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _


# Constantes au top du module pour modification centralisee.
# / Constants at module top for centralized tuning.
OTP_LENGTH = 6
OTP_TTL_SECONDS = 600           # 10 minutes
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60


def generer_code_otp() -> str:
    """
    Genere un code OTP aleatoire de 6 chiffres.
    / Generates a random 6-digit OTP code.

    Utilise `secrets` (crypto-sur) plutot que `random`.
    """
    return "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))


def hash_code_otp(code: str) -> str:
    """
    Hash SHA-256 d'un code OTP. Jamais stocker le code en clair.
    / SHA-256 hash of an OTP code. Never store cleartext.
    """
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def verifier_code_otp(code_soumis: str, hash_stocke: str) -> bool:
    """
    Compare un code soumis au hash stocke en temps constant.
    / Constant-time comparison.

    `hmac.compare_digest` empeche les attaques par timing.
    """
    if not code_soumis or not hash_stocke:
        return False
    return hmac.compare_digest(hash_code_otp(code_soumis), hash_stocke)


def envoyer_email_otp(
    email_destinataire: str,
    code_otp: str,
    libelle_action: str,
    nom_organisation: Optional[str] = None,
) -> None:
    """
    Envoie l'email OTP via les templates generiques.
    / Sends the OTP email via the generic templates.

    :param email_destinataire: email du destinataire / recipient email
    :param code_otp: code clair a inclure dans le mail / cleartext code
    :param libelle_action: ex "Proposer un evenement", "Connexion"
    :param nom_organisation: nom du lieu/tenant (footer mail, optionnel)
    """
    contexte_email = {
        "code": code_otp,
        "expires_minutes": OTP_TTL_SECONDS // 60,
        "libelle_action": libelle_action,
        "nom_organisation": nom_organisation or "",
    }
    sujet = _("%(action)s : votre code de verification") % {"action": libelle_action}
    corps_texte = render_to_string("auth/emails/otp_code.txt", contexte_email)
    corps_html = render_to_string("auth/emails/otp_code.html", contexte_email)
    send_mail(
        subject=sujet,
        message=corps_texte,
        html_message=corps_html,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email_destinataire],
        fail_silently=False,
    )
```

- [ ] **S1.2.2 — Lancer les tests : les 11 tests passent (sauf `envoyer_email_otp` non testé encore)**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_otp_service.py -q`
Expected : `11 passed`

### S1.3 — Templates email génériques

- [ ] **S1.3.1 — Créer `AuthBillet/templates/auth/emails/otp_code.txt`**

```
{{ libelle_action }}

Votre code de verification : {{ code }}

Ce code est valable {{ expires_minutes }} minutes.

Si vous n'avez pas demande ce code, ignorez ce message.

{% if nom_organisation %}--
{{ nom_organisation }}{% endif %}
```

- [ ] **S1.3.2 — Créer `AuthBillet/templates/auth/emails/otp_code.html`**

```html
{% load i18n %}
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>{{ libelle_action }}</title>
</head>
<body style="font-family: Arial, sans-serif; background-color: #f8f9fa; margin: 0; padding: 24px;">
    <div style="max-width: 480px; margin: 0 auto; background-color: #ffffff; padding: 32px; border-radius: 8px; border: 1px solid #dee2e6;">
        <h1 style="margin: 0 0 16px; font-size: 20px; color: #212529;">
            {{ libelle_action }}
        </h1>
        <p style="margin: 0 0 16px; color: #495057; font-size: 14px;">
            {% translate "Voici votre code de verification :" %}
        </p>
        <div style="font-family: 'Courier New', monospace; font-size: 32px; letter-spacing: 8px; text-align: center; background-color: #f1f3f5; padding: 20px; border-radius: 6px; color: #212529; font-weight: bold;">
            {{ code }}
        </div>
        <p style="margin: 16px 0 0; color: #6c757d; font-size: 13px;">
            {% blocktranslate with minutes=expires_minutes %}Ce code est valable {{ minutes }} minutes.{% endblocktranslate %}
        </p>
        <p style="margin: 8px 0 0; color: #6c757d; font-size: 13px;">
            {% translate "Si vous n'avez pas demande ce code, ignorez ce message." %}
        </p>
        {% if nom_organisation %}
        <hr style="border: none; border-top: 1px solid #dee2e6; margin: 24px 0 16px;">
        <p style="margin: 0; color: #adb5bd; font-size: 12px; text-align: center;">
            {{ nom_organisation }}
        </p>
        {% endif %}
    </div>
</body>
</html>
```

### S1.4 — Test d'envoi email OTP

- [ ] **S1.4.1 — Ajouter les tests `TestEnvoyerEmailOtp` dans `tests/pytest/test_otp_service.py`**

```python
# Ajouter en bas du fichier
from unittest.mock import patch


class TestEnvoyerEmailOtp:
    @patch("AuthBillet.otp_service.send_mail")
    def test_appelle_send_mail_avec_destinataire(self, mock_send):
        from AuthBillet.otp_service import envoyer_email_otp
        envoyer_email_otp("user@example.com", "123456", "Connexion")
        assert mock_send.called
        _args, kwargs = mock_send.call_args
        assert kwargs["recipient_list"] == ["user@example.com"]

    @patch("AuthBillet.otp_service.send_mail")
    def test_inclut_le_code_dans_le_corps_texte(self, mock_send):
        from AuthBillet.otp_service import envoyer_email_otp
        envoyer_email_otp("u@x.fr", "987654", "Connexion")
        _args, kwargs = mock_send.call_args
        assert "987654" in kwargs["message"]

    @patch("AuthBillet.otp_service.send_mail")
    def test_inclut_le_code_dans_le_corps_html(self, mock_send):
        from AuthBillet.otp_service import envoyer_email_otp
        envoyer_email_otp("u@x.fr", "987654", "Connexion")
        _args, kwargs = mock_send.call_args
        assert "987654" in kwargs["html_message"]

    @patch("AuthBillet.otp_service.send_mail")
    def test_sujet_contient_libelle_action(self, mock_send):
        from AuthBillet.otp_service import envoyer_email_otp
        envoyer_email_otp("u@x.fr", "123456", "Proposer un evenement")
        _args, kwargs = mock_send.call_args
        assert "Proposer un evenement" in str(kwargs["subject"])

    @patch("AuthBillet.otp_service.send_mail")
    def test_footer_contient_nom_organisation_si_fourni(self, mock_send):
        from AuthBillet.otp_service import envoyer_email_otp
        envoyer_email_otp("u@x.fr", "123456", "Test", nom_organisation="Mon Lieu")
        _args, kwargs = mock_send.call_args
        assert "Mon Lieu" in kwargs["message"]
        assert "Mon Lieu" in kwargs["html_message"]
```

- [ ] **S1.4.2 — Lancer : tous les tests passent**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_otp_service.py -q`
Expected : `16 passed`

### S1.5 — Helper OtpSession : tests FAIL

- [ ] **S1.5.1 — Créer `tests/pytest/test_otp_session.py`**

```python
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


@pytest.fixture
def request_avec_session():
    """
    Fournit un objet request Django avec session active.
    / Provides a Django request with an active session.
    """
    rf = RequestFactory()
    request = rf.get("/")
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    return request


class TestOtpSessionStart:
    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_pose_les_cles_en_session(self, _mock_mail, request_avec_session):
        from AuthBillet.otp_session import OtpSession
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
        from AuthBillet.otp_session import OtpSession
        otp = OtpSession(request_avec_session, prefix="test_flow")
        otp.start("u@x.fr", libelle_action="Proposer un evenement")
        assert mock_mail.called
        _args, kwargs = mock_mail.call_args
        # 3eme argument positionnel = libelle_action
        # / 3rd positional arg = libelle_action
        assert mock_mail.call_args[0][2] == "Proposer un evenement"


class TestOtpSessionVerify:
    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_code_correct_marque_confirmed(self, _m, request_avec_session):
        from AuthBillet.otp_session import OtpSession
        from AuthBillet.otp_service import hash_code_otp
        otp = OtpSession(request_avec_session, prefix="test_flow")
        otp.start("u@x.fr", libelle_action="Test")
        # Recuperer le hash depuis la session et tester avec un code connu.
        # Astuce : on patche generer_code_otp pour controler le code emis.
        # Test alternatif : on poste un hash connu.
        request_avec_session.session["test_flow_otp_hash"] = hash_code_otp("000111")
        assert otp.verify("000111") is True
        assert otp.is_confirmed() is True

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_code_incorrect_retourne_false_et_increment(self, _m, request_avec_session):
        from AuthBillet.otp_session import OtpSession
        from AuthBillet.otp_service import hash_code_otp
        otp = OtpSession(request_avec_session, prefix="test_flow")
        otp.start("u@x.fr", libelle_action="Test")
        request_avec_session.session["test_flow_otp_hash"] = hash_code_otp("000111")
        assert otp.verify("999999") is False
        assert request_avec_session.session["test_flow_otp_attempts"] == 1
        assert otp.is_confirmed() is False

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_max_attempts_retourne_false_meme_si_code_correct(self, _m, request_avec_session):
        from AuthBillet.otp_session import OtpSession
        from AuthBillet.otp_service import hash_code_otp
        otp = OtpSession(request_avec_session, prefix="test_flow")
        otp.start("u@x.fr", libelle_action="Test")
        request_avec_session.session["test_flow_otp_hash"] = hash_code_otp("000111")
        request_avec_session.session["test_flow_otp_attempts"] = 5
        assert otp.verify("000111") is False

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_expiration_retourne_false(self, _m, request_avec_session):
        from AuthBillet.otp_session import OtpSession
        from AuthBillet.otp_service import hash_code_otp
        otp = OtpSession(request_avec_session, prefix="test_flow")
        otp.start("u@x.fr", libelle_action="Test")
        request_avec_session.session["test_flow_otp_hash"] = hash_code_otp("000111")
        # Force une expiration dans le passe / Force expiry in the past
        past = (timezone.now() - timedelta(seconds=10)).isoformat()
        request_avec_session.session["test_flow_otp_expires_at"] = past
        assert otp.verify("000111") is False

    def test_sans_session_prealable_retourne_false(self, request_avec_session):
        from AuthBillet.otp_session import OtpSession
        otp = OtpSession(request_avec_session, prefix="absent")
        assert otp.verify("000111") is False


class TestOtpSessionState:
    def test_is_confirmed_initialement_false(self, request_avec_session):
        from AuthBillet.otp_session import OtpSession
        otp = OtpSession(request_avec_session, prefix="x")
        assert otp.is_confirmed() is False

    def test_email_retourne_chaine_vide_si_pas_start(self, request_avec_session):
        from AuthBillet.otp_session import OtpSession
        otp = OtpSession(request_avec_session, prefix="x")
        assert otp.email() == ""

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_attempts_remaining_decroit(self, _m, request_avec_session):
        from AuthBillet.otp_session import OtpSession
        from AuthBillet.otp_service import hash_code_otp
        otp = OtpSession(request_avec_session, prefix="x")
        otp.start("u@x.fr", libelle_action="Test")
        request_avec_session.session["x_otp_hash"] = hash_code_otp("000111")
        assert otp.attempts_remaining() == 5
        otp.verify("999999")
        assert otp.attempts_remaining() == 4


class TestOtpSessionResend:
    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_can_resend_true_apres_cooldown(self, _m, request_avec_session):
        from AuthBillet.otp_session import OtpSession
        otp = OtpSession(request_avec_session, prefix="x")
        otp.start("u@x.fr", libelle_action="Test")
        past = (timezone.now() - timedelta(seconds=120)).isoformat()
        request_avec_session.session["x_otp_last_sent_at"] = past
        assert otp.can_resend() is True

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_can_resend_false_avant_cooldown(self, _m, request_avec_session):
        from AuthBillet.otp_session import OtpSession
        otp = OtpSession(request_avec_session, prefix="x")
        otp.start("u@x.fr", libelle_action="Test")
        # last_sent_at = maintenant -> false
        # / last_sent_at = now -> false
        assert otp.can_resend() is False

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_seconds_before_resend_positif(self, _m, request_avec_session):
        from AuthBillet.otp_session import OtpSession
        otp = OtpSession(request_avec_session, prefix="x")
        otp.start("u@x.fr", libelle_action="Test")
        assert 0 < otp.seconds_before_resend() <= 60


class TestOtpSessionReset:
    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_efface_toutes_les_cles_du_prefixe(self, _m, request_avec_session):
        from AuthBillet.otp_session import OtpSession
        otp = OtpSession(request_avec_session, prefix="x")
        otp.start("u@x.fr", libelle_action="Test")
        otp.reset()
        s = request_avec_session.session
        for suffix in ("email", "hash", "expires_at", "attempts", "last_sent_at", "confirmed"):
            assert f"x_otp_{suffix}" not in s

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_ne_touche_pas_aux_cles_d_autres_prefixes(self, _m, request_avec_session):
        from AuthBillet.otp_session import OtpSession
        otp_a = OtpSession(request_avec_session, prefix="flow_a")
        otp_b = OtpSession(request_avec_session, prefix="flow_b")
        otp_a.start("a@x.fr", libelle_action="A")
        otp_b.start("b@x.fr", libelle_action="B")
        otp_a.reset()
        assert request_avec_session.session.get("flow_b_otp_email") == "b@x.fr"
```

- [ ] **S1.5.2 — Lancer : tous DOIVENT FAIL**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_otp_session.py -q`
Expected : `ModuleNotFoundError: No module named 'AuthBillet.otp_session'`

### S1.6 — Helper OtpSession : implémentation

- [ ] **S1.6.1 — Créer `AuthBillet/otp_session.py`**

```python
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

    def _k(self, suffix: str) -> str:
        return f"{self.prefix}_otp_{suffix}"

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
        self.request.session[self._k("email")] = email
        self.request.session[self._k("hash")] = hash_code_otp(code)
        self.request.session[self._k("expires_at")] = expire_a.isoformat()
        self.request.session[self._k("attempts")] = 0
        self.request.session[self._k("last_sent_at")] = timezone.now().isoformat()
        self.request.session[self._k("confirmed")] = False
        envoyer_email_otp(email, code, libelle_action, nom_organisation)

    def verify(self, code_soumis: str) -> bool:
        """
        Verifie le code soumis. Incremente le compteur de tentatives.
        / Verifies the submitted code. Increments attempts counter.
        """
        hash_stocke = self.request.session.get(self._k("hash"))
        expires_at_iso = self.request.session.get(self._k("expires_at"))
        attempts = self.request.session.get(self._k("attempts"), 0)

        if not hash_stocke or not expires_at_iso:
            return False
        if attempts >= OTP_MAX_ATTEMPTS:
            return False
        if timezone.now() > datetime.fromisoformat(expires_at_iso):
            return False

        self.request.session[self._k("attempts")] = attempts + 1
        if verifier_code_otp(code_soumis, hash_stocke):
            self.request.session[self._k("confirmed")] = True
            return True
        return False

    def is_confirmed(self) -> bool:
        return bool(self.request.session.get(self._k("confirmed")))

    def email(self) -> str:
        return self.request.session.get(self._k("email"), "")

    def attempts_remaining(self) -> int:
        attempts = self.request.session.get(self._k("attempts"), 0)
        return max(0, OTP_MAX_ATTEMPTS - attempts)

    def can_resend(self) -> bool:
        last_sent_iso = self.request.session.get(self._k("last_sent_at"))
        if not last_sent_iso:
            return True
        delta = timezone.now() - datetime.fromisoformat(last_sent_iso)
        return delta.total_seconds() >= OTP_RESEND_COOLDOWN_SECONDS

    def seconds_before_resend(self) -> int:
        last_sent_iso = self.request.session.get(self._k("last_sent_at"))
        if not last_sent_iso:
            return 0
        delta = timezone.now() - datetime.fromisoformat(last_sent_iso)
        return max(0, int(OTP_RESEND_COOLDOWN_SECONDS - delta.total_seconds()))

    def reset(self) -> None:
        for suffix in (
            "email", "hash", "expires_at", "attempts",
            "last_sent_at", "confirmed",
        ):
            self.request.session.pop(self._k(suffix), None)
```

- [ ] **S1.6.2 — Lancer tous les tests OTP**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_otp_service.py tests/pytest/test_otp_session.py -q`
Expected : `~28 passed` (16 service + ~12 session)

### S1.7 — Préparer le commit S1

- [ ] **S1.7.1 — Lister les fichiers modifiés**

```bash
git status --short
```

Attendu :
```
A  AuthBillet/otp_service.py
A  AuthBillet/otp_session.py
A  AuthBillet/templates/auth/emails/otp_code.html
A  AuthBillet/templates/auth/emails/otp_code.txt
A  tests/pytest/test_otp_service.py
A  tests/pytest/test_otp_session.py
```

- [ ] **S1.7.2 — Préparer le message de commit (le mainteneur exécute)**

```
feat(AuthBillet): add stateless OTP service + HTTP session helper

- AuthBillet/otp_service.py: 4 pure functions (generate, hash, verify, send)
- AuthBillet/otp_session.py: OtpSession class for HTTP session storage
- templates/auth/emails/otp_code.{html,txt}: generic OTP email templates
- 28 unit tests in tests/pytest/test_otp_*.py (100% coverage)

First consumer: BaseBillet event proposal wizard (next session).
Future consumers: login OTP, SSO, onboard migration.

Spec: TECH_DOC/SESSIONS/OTP/SPEC.md
```

---

## Session S2 — Modèle `Event.is_proposal` + cleanup

**Référence spec :** [SPEC.md](SPEC.md) sections 7, 3 (Code supprimé).

### Files

- Modify: `BaseBillet/models.py` (classe `Event`, ajout 1 champ)
- Create: `BaseBillet/migrations/0XXX_event_is_proposal.py` (généré par `makemigrations`)
- Modify: `BaseBillet/views.py` (suppression de 4 méthodes EventMVT + nettoyage `get_permissions`)
- Delete: `BaseBillet/templates/reunion/views/event/partial/simple_add_event.html`
- Delete: `BaseBillet/templates/reunion/views/event/partial/address_simple_add.html`
- Modify: `BaseBillet/templates/reunion/views/event/list.html` (suppression offcanvas)
- Modify: `BaseBillet/urls.py` (si les routes sont déclarées séparément)

### S2.1 — Vérifier l'usage de `EventQuickCreateSerializer` avant suppression

- [ ] **S2.1.1 — Chercher tous les usages**

```bash
docker exec lespass_django bash -c "cd /DjangoFiles && grep -rn 'EventQuickCreateSerializer' --include='*.py'"
```

Si **uniquement** dans `BaseBillet/views.py:simple_create_event` et `BaseBillet/validators.py` (définition), il sera supprimable plus tard. Si utilisé dans des tests ou ailleurs, **noter et conserver le serializer** dans validators.py (sera référencé par le nouveau wizard admin qui reprend sa logique).

**Décision :** ce plan conserve `EventQuickCreateSerializer` jusqu'à S3 (où la nouvelle logique de wizard admin reprend une partie de son code). Suppression définitive en S3 si possible.

### S2.2 — Ajouter le champ `is_proposal` au modèle Event

- [ ] **S2.2.1 — Modifier `BaseBillet/models.py` classe `Event` (après la ligne `published = ...`)**

```python
    is_proposal = models.BooleanField(
        default=False,
        verbose_name=_("Public proposal"),
        help_text=_(
            "Event submitted via the public proposal wizard, "
            "awaiting admin validation."
        ),
    )
```

Placer juste après `published` et avant `archived` (ligne ~1475 dans `models.py`).

- [ ] **S2.2.2 — Générer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet --name event_is_proposal
```

Expected output : `Migrations for 'BaseBillet': 0XXX_event_is_proposal.py - Add field is_proposal to event`

- [ ] **S2.2.3 — Appliquer la migration sur tous les schemas**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

Expected : `Migration applied` sur chaque tenant.

- [ ] **S2.2.4 — Vérifier le champ en base**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import schema_context
from BaseBillet.models import Event
with schema_context('lespass'):
    e = Event.objects.first()
    print('is_proposal sur Event :', hasattr(e, 'is_proposal'))
    print('default value :', Event._meta.get_field('is_proposal').default)
"
```

Expected : `is_proposal sur Event : True` et `default value : False`.

### S2.3 — Test du nouveau champ

- [ ] **S2.3.1 — Créer `tests/pytest/test_event_is_proposal_field.py`**

```python
"""
Test du champ Event.is_proposal (chantier EVENT_WIZARD).
/ Test for the Event.is_proposal field.
"""

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

from Customers.models import Client


@pytest.mark.django_db
def test_is_proposal_default_false():
    from BaseBillet.models import Event
    tenant = Client.objects.exclude(schema_name="public").first()
    with tenant_context(tenant):
        event = Event.objects.create(
            name="Test default flag",
            datetime=timezone.now() + timezone.timedelta(days=1),
        )
        assert event.is_proposal is False
        event.delete()


@pytest.mark.django_db
def test_is_proposal_can_be_set_true():
    from BaseBillet.models import Event
    tenant = Client.objects.exclude(schema_name="public").first()
    with tenant_context(tenant):
        event = Event.objects.create(
            name="Test proposal flag",
            datetime=timezone.now() + timezone.timedelta(days=1),
            is_proposal=True,
            published=False,
        )
        assert event.is_proposal is True
        assert event.published is False
        event.delete()
```

- [ ] **S2.3.2 — Lancer**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_event_is_proposal_field.py -q`
Expected : `2 passed`

### S2.4 — Cleanup : suppression de l'offcanvas existant et des vues `simple_*`

- [ ] **S2.4.1 — Supprimer les vues obsolètes dans `BaseBillet/views.py`**

Localiser et **supprimer entièrement** les méthodes suivantes de la classe `EventMVT` (lignes ~2310-2466) :
- `simple_add_event` (action GET)
- `simple_create_event` (action POST)
- `address_add_form` (action GET)
- `address_create` (action POST)

- [ ] **S2.4.2 — Nettoyer `EventMVT.get_permissions` (lignes ~1775-1781)**

Avant :
```python
def get_permissions(self):
    if self.action in ['simple_add_event', 'simple_create_event', 'address_add_form', 'address_create']:
        permission_classes = [CanCreateEventPermission]
    else:
        permission_classes = [permissions.AllowAny]
    return [permission() for permission in permission_classes]
```

Après :
```python
def get_permissions(self):
    # EventMVT n'expose plus que des vues publiques (list/retrieve).
    # Les actions admin de creation d'evenement vivent dans EventWizardAdmin (S3).
    # / EventMVT now only exposes public views. Admin create actions live in EventWizardAdmin.
    return [permissions.AllowAny()]
```

- [ ] **S2.4.3 — Supprimer les templates obsolètes**

```bash
docker exec lespass_django bash -c "rm /DjangoFiles/BaseBillet/templates/reunion/views/event/partial/simple_add_event.html"
docker exec lespass_django bash -c "rm /DjangoFiles/BaseBillet/templates/reunion/views/event/partial/address_simple_add.html"
```

- [ ] **S2.4.4 — Nettoyer `list.html` : supprimer offcanvas et l'ancien bouton admin**

Dans `BaseBillet/templates/reunion/views/event/list.html`, supprimer :
- Le bloc `{% if user|can_create_event_tag %}...<button>Ajouter un évènement</button>...{% endif %}` (lignes ~49-62) — il sera remplacé en S5 par un nouveau bouton vers le wizard.
- Le bloc `<style>#adminAddEventPanel { ... }</style>` (lignes ~100-103).
- Tout le bloc `<div class="offcanvas-start offcanvas" tabindex="-1" id="adminAddEventPanel" ...>...</div>` (lignes ~104-112).

**Note** : le placement des nouveaux boutons admin + public sera fait en S5. À ce stade, la page event/list n'a temporairement plus de bouton de création.

- [ ] **S2.4.5 — Vérifier que les tests existants passent**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_events_list.py tests/pytest/test_event_*.py -q`
Expected : tests verts. Si un test échoue parce qu'il référence `simple_create_event`, le marquer `pytest.skip` ou le supprimer si caduque.

### S2.5 — Préparer le commit S2

- [ ] **S2.5.1 — Lister + message**

```
feat(BaseBillet): add Event.is_proposal field + remove old offcanvas

- BaseBillet/models.py: +Event.is_proposal (BooleanField default=False)
- BaseBillet/migrations/0XXX_event_is_proposal.py
- Remove simple_add_event/simple_create_event/address_add_form/address_create views
- Remove simple_add_event.html + address_simple_add.html partials
- Remove offcanvas adminAddEventPanel from list.html
- Cleanup EventMVT.get_permissions

The Event create UI is temporarily missing on event/list — restored in S5
with new wizard buttons.

Spec: TECH_DOC/SESSIONS/EVENT_WIZARD/SPEC.md sections 7, 3
```

---

## Session S3 — Wizard ADMIN (2 steps)

**Référence spec :** [SPEC.md](SPEC.md) section 5.

### Files

- Modify: `BaseBillet/validators.py` (ajout 2 serializers + helpers réutilisables)
- Modify: `BaseBillet/views.py` (ajout `EventWizardAdmin` ViewSet)
- Modify: `BaseBillet/urls.py` (ajout 2 routes)
- Create: `BaseBillet/templates/reunion/views/event/wizard/_base.html`
- Create: `BaseBillet/templates/reunion/views/event/wizard/_form_lieu.html`
- Create: `BaseBillet/templates/reunion/views/event/wizard/admin_step1_place.html`
- Create: `BaseBillet/templates/reunion/views/event/wizard/admin_step2_event.html`
- Create: `tests/pytest/test_event_wizard_admin.py`

### S3.1 — Serializers wizard

- [ ] **S3.1.1 — Ajouter `WizardPlaceSerializer` dans `BaseBillet/validators.py`**

Placer en fin de fichier, après `EventQuickCreateSerializer` :

```python
class WizardPlaceSerializer(serializers.Serializer):
    """
    Step "Lieu" des wizards event admin/public.
    / "Place" step for admin/public event wizards.

    Soit `postal_address` (pk d'une PostalAddress existante),
    soit le bloc nouvelle adresse complet (name + 4 champs + lat/lng).
    / Either `postal_address` (pk of an existing PostalAddress),
    or the full new-address block (name + 4 fields + lat/lng).
    """

    # Cas "adresse existante" / "existing address" case
    postal_address = serializers.CharField(required=False, allow_blank=True)

    # Cas "nouveau lieu" / "new place" case
    new_address_name = serializers.CharField(
        required=False, allow_blank=True, max_length=200,
    )
    street_address = serializers.CharField(
        required=False, allow_blank=True, max_length=255,
    )
    postal_code = serializers.CharField(
        required=False, allow_blank=True, max_length=20,
    )
    address_locality = serializers.CharField(
        required=False, allow_blank=True, max_length=120,
    )
    address_country = serializers.CharField(
        required=False, allow_blank=True, max_length=80, default="France",
    )
    # Champs prefixes par le widget carte / Fields prefixed by the map widget
    place_latitude = serializers.FloatField(
        required=False, min_value=-90, max_value=90, allow_null=True,
    )
    place_longitude = serializers.FloatField(
        required=False, min_value=-180, max_value=180, allow_null=True,
    )
    place_adresse = serializers.CharField(
        required=False, allow_blank=True, max_length=500,
    )

    def validate(self, attrs):
        from BaseBillet.models import PostalAddress

        # On determine le mode : pk fourni OU bloc nouvelle adresse.
        # / Determine mode: pk provided OR new address block.
        pk_value = (attrs.get("postal_address") or "").strip()

        if pk_value:
            # Mode "existante" : verifier que le pk existe.
            # / "Existing" mode: verify pk exists.
            if not PostalAddress.objects.filter(pk=pk_value).exists():
                raise serializers.ValidationError({
                    "postal_address": _("Adresse selectionnee introuvable."),
                })
            attrs["_mode"] = "existing"
            return attrs

        # Mode "nouveau" : tous les champs sont requis.
        # / "New" mode: all fields required.
        manquants = []
        for champ in ("new_address_name", "street_address", "postal_code",
                      "address_locality"):
            if not (attrs.get(champ) or "").strip():
                manquants.append(champ)
        if attrs.get("place_latitude") is None:
            manquants.append("place_latitude")
        if attrs.get("place_longitude") is None:
            manquants.append("place_longitude")

        if manquants:
            erreurs = {champ: [_("Ce champ est obligatoire.")] for champ in manquants}
            raise serializers.ValidationError(erreurs)

        attrs["_mode"] = "new"
        return attrs


class WizardEventAdminSerializer(serializers.Serializer):
    """
    Step "Event" du wizard admin : mini-form + jauge_max + tags.
    / Admin event wizard "Event" step: mini-form + jauge_max + tags.
    """

    name = serializers.CharField(max_length=200)
    datetime = serializers.DateTimeField()
    long_description = serializers.CharField(
        required=False, allow_blank=True, max_length=5000,
    )
    image = serializers.ImageField(required=False, allow_null=True)
    jauge_max = serializers.IntegerField(
        required=False, allow_null=True, min_value=1,
    )
    tags = serializers.CharField(required=False, allow_blank=True)
```

### S3.2 — Vues `EventWizardAdmin`

- [ ] **S3.2.1 — Ajouter le ViewSet dans `BaseBillet/views.py`** (en fin de fichier)

```python
class EventWizardAdmin(viewsets.ViewSet):
    """
    Wizard admin de creation d'evenement. 2 etapes, full pages.
    / Admin wizard for event creation. 2 steps, full pages.

    Step 1 : Lieu (adresse existante ou creation via widget carte).
    Step 2 : Event (mini-form + jauge_max + tags).
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [CanCreateEventPermission]

    SESSION_PREFIX = "event_wizard_admin"

    def _session_key(self, suffix: str) -> str:
        return f"{self.SESSION_PREFIX}_{suffix}"

    @action(detail=False, methods=["GET", "POST"], url_path="place")
    def step1_place(self, request):
        """
        GET  : rend la page step1.
        POST : valide + cree l'adresse si necessaire + redirige step2.
        / GET: renders step1. POST: validates + creates address if needed.
        """
        addresses = PostalAddress.objects.all().order_by("name", "address_locality")
        config = Configuration.get_solo()

        ctx_commun = {
            "wizard_title": _("Ajouter un evenement"),
            "wizard_step_label": _("Etape 1 / 2 — Lieu"),
            "addresses": addresses,
            "default_address_pk": config.postal_address.pk if config.postal_address else None,
            "form_action_url": reverse("event-admin-wizard-place"),
            "next_step_label": _("Continuer vers les details"),
        }

        if request.method == "GET":
            context = get_context(request)
            context.update(ctx_commun)
            context.update({"initial": {}, "errors": {}})
            return render(request, "reunion/views/event/wizard/admin_step1_place.html",
                          context=context)

        # POST
        serializer = WizardPlaceSerializer(data=request.POST)
        if not serializer.is_valid():
            context = get_context(request)
            context.update(ctx_commun)
            context.update({
                "initial": request.POST.dict(),
                "errors": serializer.errors,
            })
            return render(request, "reunion/views/event/wizard/admin_step1_place.html",
                          context=context, status=422)

        data = serializer.validated_data
        if data["_mode"] == "existing":
            postal_address_pk = data["postal_address"]
        else:
            # Creation d'une PostalAddress via le serializer schema.org existant.
            # / Create a PostalAddress via the existing schema.org serializer.
            from api_v2.serializers import PostalAddressCreateSerializer
            payload = {
                "name": data["new_address_name"],
                "streetAddress": data["street_address"],
                "addressLocality": data["address_locality"],
                "postalCode": data["postal_code"],
                "addressCountry": data.get("address_country") or "France",
            }
            pa_ser = PostalAddressCreateSerializer(data=payload, context={"request": request})
            pa_ser.is_valid(raise_exception=True)
            addr = pa_ser.save()
            # Ajouter lat/lng (non gere par le serializer schema.org).
            # / Add lat/lng (not handled by the schema.org serializer).
            addr.latitude = data["place_latitude"]
            addr.longitude = data["place_longitude"]
            addr.save(update_fields=["latitude", "longitude"])
            postal_address_pk = str(addr.pk)

        request.session[self._session_key("postal_address_pk")] = postal_address_pk
        return redirect("event-admin-wizard-event")

    @action(detail=False, methods=["GET", "POST"], url_path="event")
    def step2_event(self, request):
        """
        Garde : postal_address_pk en session sinon redirect step1.
        GET : rend le mini-form. POST : cree l'event publie.
        / Guard: needs postal_address_pk in session. GET: renders form. POST: creates event.
        """
        postal_address_pk = request.session.get(self._session_key("postal_address_pk"))
        if not postal_address_pk:
            return redirect("event-admin-wizard-place")

        try:
            postal_address = PostalAddress.objects.get(pk=postal_address_pk)
        except PostalAddress.DoesNotExist:
            request.session.pop(self._session_key("postal_address_pk"), None)
            return redirect("event-admin-wizard-place")

        all_tags = Tag.objects.all().order_by("name")

        ctx_commun = {
            "wizard_title": _("Ajouter un evenement"),
            "wizard_step_label": _("Etape 2 / 2 — Details"),
            "postal_address": postal_address,
            "all_tags": all_tags,
        }

        if request.method == "GET":
            context = get_context(request)
            context.update(ctx_commun)
            context.update({"initial": {}, "errors": {}})
            return render(request, "reunion/views/event/wizard/admin_step2_event.html",
                          context=context)

        # POST
        # Note : pour les ImageField on doit donner request.POST + request.FILES.
        # / For ImageField support: pass request.POST + request.FILES.
        data_combined = request.POST.copy()
        for f_key in request.FILES:
            data_combined[f_key] = request.FILES[f_key]
        serializer = WizardEventAdminSerializer(data=data_combined)
        if not serializer.is_valid():
            context = get_context(request)
            context.update(ctx_commun)
            context.update({
                "initial": request.POST.dict(),
                "errors": serializer.errors,
            })
            return render(request, "reunion/views/event/wizard/admin_step2_event.html",
                          context=context, status=422)

        validated = serializer.validated_data
        event = Event(
            name=validated["name"].strip(),
            datetime=validated["datetime"],
            long_description=admin_clean_html(validated.get("long_description") or ""),
            postal_address=postal_address,
            created_by=request.user if request.user.is_authenticated else None,
            published=True,
            is_proposal=False,
        )
        if validated.get("image"):
            event.img = validated["image"]
        if validated.get("jauge_max"):
            event.jauge_max = validated["jauge_max"]
            event.show_gauge = True
        event.save()

        # Tags : split virgule/point-virgule, get_or_create chaque.
        # / Tags: split by comma/semicolon, get_or_create each.
        tags_input = validated.get("tags", "")
        if tags_input:
            for tname in re.split(r"[,;]", tags_input):
                tname = tname.strip()
                if not tname:
                    continue
                tag_obj, _tag_created = Tag.objects.get_or_create(name=tname)
                event.tag.add(tag_obj)

        # Rattacher le produit FREERES si jauge_max
        # / Attach FREERES product if jauge_max
        if validated.get("jauge_max"):
            free_res = Product.objects.filter(
                categorie_article=Product.FREERES, publish=True, archive=False
            ).first()
            if free_res:
                event.products.add(free_res)

        # Nettoyer la session / Clear session
        for suffix in ("postal_address_pk",):
            request.session.pop(self._session_key(suffix), None)

        messages.add_message(request, messages.SUCCESS, _("Evenement cree !"))
        return redirect(reverse("event-detail", kwargs={"pk": event.slug or event.uuid}))
```

Imports nécessaires à ajouter en haut de `BaseBillet/views.py` si pas déjà présents :
```python
import re
from django.urls import reverse
from BaseBillet.validators import WizardPlaceSerializer, WizardEventAdminSerializer
```

### S3.3 — Routes admin

- [ ] **S3.3.1 — Ajouter les routes dans `BaseBillet/urls.py`**

Localiser le bloc d'URLs du module, ajouter :

```python
# Wizard admin de creation d'evenement (S3 EVENT_WIZARD).
# / Admin event creation wizard.
event_wizard_admin_step1 = EventWizardAdmin.as_view({
    "get": "step1_place", "post": "step1_place",
})
event_wizard_admin_step2 = EventWizardAdmin.as_view({
    "get": "step2_event", "post": "step2_event",
})

# Dans urlpatterns :
path("event/admin/wizard/place/", event_wizard_admin_step1, name="event-admin-wizard-place"),
path("event/admin/wizard/event/", event_wizard_admin_step2, name="event-admin-wizard-event"),
```

Import en haut de `urls.py` si nécessaire :
```python
from BaseBillet.views import EventWizardAdmin
```

### S3.4 — Templates wizard admin

- [ ] **S3.4.1 — Créer `BaseBillet/templates/reunion/views/event/wizard/_base.html`**

```html
{% extends base_template %}
{% load i18n %}

{% comment %}
LOCALISATION: BaseBillet/templates/reunion/views/event/wizard/_base.html

Layout de base reutilisable par tous les wizards event.
/ Reusable base layout for all event wizards.

Variables attendues :
  - wizard_title (str) : titre principal de la page
  - wizard_step_label (str) : "Etape 1 / 2"
  - wizard_back_url (str?) : URL du bouton "Precedent" si applicable
{% endcomment %}

{% block title %}{{ wizard_title|default:_("Wizard") }}{% endblock %}

{% block main %}
<section class="container" style="max-width: 720px;">
    <header class="mb-4 pt-4">
        {% if wizard_step_label %}
            <p class="text-muted small mb-1">{{ wizard_step_label }}</p>
        {% endif %}
        <h1 class="h3 mb-0">{{ wizard_title }}</h1>
    </header>

    {% block step_content %}{% endblock %}

    {% if wizard_back_url %}
        <div class="mt-3">
            <a href="{{ wizard_back_url }}" class="btn btn-link"
               data-testid="wizard-back">
                <i class="bi bi-arrow-left me-1" aria-hidden="true"></i>
                {% translate "Precedent" %}
            </a>
        </div>
    {% endif %}
</section>
{% endblock %}
```

- [ ] **S3.4.2 — Créer `BaseBillet/templates/reunion/views/event/wizard/_form_lieu.html`** (partial réutilisé admin + public)

```html
{% load i18n %}
{% comment %}
LOCALISATION: BaseBillet/templates/reunion/views/event/wizard/_form_lieu.html

Partial reutilisable pour la step "Lieu" des wizards admin et public.
Toggle radio CSS-only entre "Adresse existante" et "Nouveau lieu".
/ Reusable partial for the "Place" step (admin + public wizards).
CSS-only radio toggle between "Existing address" and "New place".

Variables attendues :
  - form_action_url (str)
  - addresses (queryset PostalAddress)
  - default_address_pk (uuid?) : adresse pre-selectionnee si mode existant
  - initial (dict) : valeurs re-injectees apres une 422
  - errors (dict) : erreurs par champ
  - next_step_label (str) : libelle du bouton submit
{% endcomment %}

<style>
    /* Toggle CSS-only : on cache les blocs non actifs.
       / CSS-only toggle: hide non-active blocks. */
    .wizard-mode-existing-fields,
    .wizard-mode-new-fields { display: none; }
    .wizard-mode-toggle input[value="existing"]:checked ~ .wizard-mode-existing-fields,
    .wizard-mode-toggle input[value="new"]:checked ~ .wizard-mode-new-fields {
        display: block;
    }
</style>

{% if errors %}
<div class="alert alert-danger mb-3" role="alert" data-testid="wizard-place-errors">
    <strong>{% translate "Merci de corriger les erreurs ci-dessous." %}</strong>
    <ul class="mb-0 mt-1 small">
        {% for field, msgs in errors.items %}
            {% if field != "_mode" %}
            <li><strong>{{ field }}</strong> :
                {% for msg in msgs %}{{ msg }}{% if not forloop.last %} / {% endif %}{% endfor %}
            </li>
            {% endif %}
        {% endfor %}
    </ul>
</div>
{% endif %}

<form method="post" action="{{ form_action_url }}" enctype="multipart/form-data"
      novalidate data-testid="wizard-place-form" class="vstack gap-3">
    {% csrf_token %}

    <div class="wizard-mode-toggle">
        <div class="btn-group mb-3" role="group" aria-label="{% translate 'Mode de saisie' %}">
            <input type="radio" class="btn-check" name="_form_mode" id="mode-existing" value="existing"
                   {% if not initial.new_address_name %}checked{% endif %}>
            <label class="btn btn-outline-primary" for="mode-existing">
                {% translate "Utiliser une adresse existante" %}
            </label>

            <input type="radio" class="btn-check" name="_form_mode" id="mode-new" value="new"
                   {% if initial.new_address_name %}checked{% endif %}>
            <label class="btn btn-outline-primary" for="mode-new">
                {% translate "Creer un nouveau lieu" %}
            </label>
        </div>

        <div class="wizard-mode-existing-fields">
            <label for="postal_address" class="form-label">{% translate "Adresse" %}</label>
            <select id="postal_address" name="postal_address" class="form-select"
                    data-testid="wizard-place-select">
                <option value="">{% translate "-- Choisir --" %}</option>
                {% for a in addresses %}
                    <option value="{{ a.pk }}"
                        {% if initial.postal_address|stringformat:"s" == a.pk|stringformat:"s" %}selected
                        {% elif default_address_pk and not initial.postal_address and default_address_pk|stringformat:"s" == a.pk|stringformat:"s" %}selected
                        {% endif %}>
                        {{ a.name|default:a.address_locality }}{% if a.postal_code %} ({{ a.postal_code }}){% endif %}
                    </option>
                {% endfor %}
            </select>
        </div>

        <div class="wizard-mode-new-fields">
            <div class="mb-3">
                <label for="new_address_name" class="form-label">
                    {% translate "Nom du lieu" %} <span class="text-danger">*</span>
                </label>
                <input type="text" id="new_address_name" name="new_address_name"
                       class="form-control" maxlength="200"
                       value="{{ initial.new_address_name|default:'' }}"
                       data-testid="wizard-place-new-name">
                <div class="form-text">{% translate "Exemple : Grande salle, Salle du bas, Accueil..." %}</div>
            </div>

            {% include "widgets/widget_carte_adresse.html" with identifiant_widget="place" hauteur_carte="350px" champs_adresse_separes=True latitude_initiale=initial.place_latitude longitude_initiale=initial.place_longitude adresse_initiale=initial.place_adresse %}
        </div>
    </div>

    <div class="d-flex justify-content-end pt-2">
        <button type="submit" class="btn btn-primary btn-lg"
                data-testid="wizard-place-submit">
            {{ next_step_label|default:_("Continuer") }}
            <i class="bi bi-arrow-right ms-1" aria-hidden="true"></i>
        </button>
    </div>
</form>
```

- [ ] **S3.4.3 — Créer `BaseBillet/templates/reunion/views/event/wizard/admin_step1_place.html`**

```html
{% extends "reunion/views/event/wizard/_base.html" %}
{% load i18n %}

{% block step_content %}
<p class="text-muted mb-3">
    {% translate "Choisissez l'adresse de l'evenement, ou creez un nouveau lieu via la carte." %}
</p>

{% include "reunion/views/event/wizard/_form_lieu.html" %}
{% endblock %}
```

**Note importante** : `wizard_title` et `wizard_step_label` sont lus par `_base.html` depuis le contexte de la vue (pas de `{% with %}`, pas de `{% block %}` override). **Toutes les vues wizard** doivent les ajouter au contexte avant `render()` :

```python
# Dans EventWizardAdmin.step1_place, context.update(...)
context.update({
    ...
    "wizard_title": _("Ajouter un evenement"),
    "wizard_step_label": _("Etape 1 / 2 — Lieu"),
})

# Dans EventWizardAdmin.step2_event, context.update(...)
context.update({
    ...
    "wizard_title": _("Ajouter un evenement"),
    "wizard_step_label": _("Etape 2 / 2 — Details"),
})
```

Appliquer la même règle dans toutes les vues `EventWizardPublic` (voir S4.2 — les `context.update` y incluent déjà `wizard_title` et `wizard_step_label`).

- [ ] **S3.4.4 — Créer `BaseBillet/templates/reunion/views/event/wizard/admin_step2_event.html`**

```html
{% extends "reunion/views/event/wizard/_base.html" %}
{% load i18n %}

{% block step_content %}

<div class="alert alert-info py-2 mb-3" role="status">
    <i class="bi bi-geo-alt me-1" aria-hidden="true"></i>
    {% blocktranslate with name=postal_address.name|default:postal_address.address_locality city=postal_address.address_locality %}Lieu choisi : <strong>{{ name }}</strong> — {{ city }}{% endblocktranslate %}
    <a href="{% url 'event-admin-wizard-place' %}" class="ms-2 small text-decoration-none"
       data-testid="wizard-event-change-place">
        <i class="bi bi-pencil" aria-hidden="true"></i> {% translate "Modifier" %}
    </a>
</div>

{% if errors %}
<div class="alert alert-danger mb-3" role="alert" data-testid="wizard-event-errors">
    <ul class="mb-0 small">
        {% for field, msgs in errors.items %}
        <li><strong>{{ field }}</strong> : {{ msgs|join:" / " }}</li>
        {% endfor %}
    </ul>
</div>
{% endif %}

<form method="post" action="{% url 'event-admin-wizard-event' %}"
      enctype="multipart/form-data" novalidate
      data-testid="wizard-admin-event-form" class="vstack gap-3">
    {% csrf_token %}

    <div>
        <label for="name" class="form-label">
            {% translate "Nom de l'evenement" %} <span class="text-danger">*</span>
        </label>
        <input type="text" id="name" name="name" required maxlength="200"
               value="{{ initial.name|default:'' }}" class="form-control"
               data-testid="wizard-admin-event-name">
    </div>

    <div>
        <label for="datetime" class="form-label">
            {% translate "Date et heure" %} <span class="text-danger">*</span>
        </label>
        <input type="datetime-local" id="datetime" name="datetime" required
               value="{{ initial.datetime|default:'' }}" class="form-control"
               data-testid="wizard-admin-event-datetime">
    </div>

    <div>
        <label for="long_description" class="form-label">{% translate "Description" %}</label>
        <textarea id="long_description" name="long_description" rows="4"
                  maxlength="5000" class="form-control"
                  data-testid="wizard-admin-event-description">{{ initial.long_description|default:'' }}</textarea>
    </div>

    <div>
        <label for="image" class="form-label">{% translate "Image (optionnel)" %}</label>
        <input type="file" id="image" name="image" accept="image/jpeg,image/png,image/webp"
               class="form-control" data-testid="wizard-admin-event-image">
        <div class="form-text">{% translate "JPEG, PNG ou WebP — 5 Mo maximum." %}</div>
    </div>

    <div>
        <label for="jauge_max" class="form-label">{% translate "Jauge maximale (capacite)" %}</label>
        <input type="number" id="jauge_max" name="jauge_max" min="1" step="1"
               inputmode="numeric"
               value="{{ initial.jauge_max|default:'' }}" class="form-control"
               data-testid="wizard-admin-event-jauge">
        <div class="form-text">{% translate "Laissez vide si pas besoin de reservation." %}</div>
    </div>

    <div>
        <label for="tags" class="form-label">{% translate "Tags (separes par des virgules)" %}</label>
        <input type="text" id="tags" name="tags" list="tags-list"
               value="{{ initial.tags|default:'' }}" class="form-control"
               data-testid="wizard-admin-event-tags">
        <datalist id="tags-list">
            {% for t in all_tags %}<option value="{{ t.name }}">{{ t.name }}</option>{% endfor %}
        </datalist>
    </div>

    <div class="d-flex justify-content-between pt-2">
        <a href="{% url 'event-admin-wizard-place' %}" class="btn btn-link"
           data-testid="wizard-admin-event-prev">
            <i class="bi bi-arrow-left me-1" aria-hidden="true"></i> {% translate "Precedent" %}
        </a>
        <button type="submit" class="btn btn-success btn-lg"
                data-testid="wizard-admin-event-submit">
            <i class="bi bi-check2-circle me-1" aria-hidden="true"></i>
            {% translate "Creer l'evenement" %}
        </button>
    </div>
</form>
{% endblock %}
```

### S3.5 — Tests wizard admin

- [ ] **S3.5.1 — Créer `tests/pytest/test_event_wizard_admin.py`**

```python
"""
Tests du wizard admin de creation d'evenement (S3).
/ Tests for the admin event creation wizard (S3).

LOCALISATION : tests/pytest/test_event_wizard_admin.py
"""

import pytest
from django.urls import reverse
from django_tenants.utils import tenant_context

from Customers.models import Client


@pytest.fixture
def tenant():
    return Client.objects.exclude(schema_name="public").first()


@pytest.fixture
def admin_user(tenant):
    from AuthBillet.models import TibilletUser
    with tenant_context(tenant):
        user = TibilletUser.objects.filter(email="admin@admin.com").first()
        assert user, "Pre-requis : utilisateur admin@admin.com existe."
        return user


@pytest.mark.django_db
class TestStep1PlaceAccess:
    def test_get_step1_redirige_anonyme(self, client):
        url = reverse("event-admin-wizard-place")
        resp = client.get(url)
        assert resp.status_code in (302, 403)

    def test_get_step1_403_pour_user_non_admin(self, client):
        # Cas user authentifie mais pas admin
        # / Authenticated but non-admin user
        ...

    def test_get_step1_ok_pour_admin(self, client, admin_user, tenant):
        client.force_login(admin_user)
        with tenant_context(tenant):
            resp = client.get(reverse("event-admin-wizard-place"))
            assert resp.status_code == 200
            assert b"wizard-place-form" in resp.content


@pytest.mark.django_db
class TestStep1PlaceSubmit:
    def test_post_avec_adresse_existante_redirige_step2(self, client, admin_user, tenant):
        from BaseBillet.models import PostalAddress
        with tenant_context(tenant):
            addr = PostalAddress.objects.first()
            assert addr
            client.force_login(admin_user)
            resp = client.post(reverse("event-admin-wizard-place"), {
                "postal_address": str(addr.pk),
            })
            assert resp.status_code == 302
            assert resp.url == reverse("event-admin-wizard-event")
            assert client.session["event_wizard_admin_postal_address_pk"] == str(addr.pk)

    def test_post_avec_nouveau_lieu_cree_postal_address(self, client, admin_user, tenant):
        from BaseBillet.models import PostalAddress
        with tenant_context(tenant):
            client.force_login(admin_user)
            count_before = PostalAddress.objects.count()
            resp = client.post(reverse("event-admin-wizard-place"), {
                "new_address_name": "Salle des fetes",
                "street_address": "10 rue des Lilas",
                "postal_code": "97400",
                "address_locality": "Saint-Denis",
                "address_country": "France",
                "place_latitude": "-20.88",
                "place_longitude": "55.45",
                "place_adresse": "10 rue des Lilas, Saint-Denis",
            })
            assert resp.status_code == 302
            assert PostalAddress.objects.count() == count_before + 1
            new_addr = PostalAddress.objects.order_by("-pk").first()
            assert new_addr.name == "Salle des fetes"
            assert float(new_addr.latitude) == -20.88

    def test_post_sans_choix_renvoie_422(self, client, admin_user, tenant):
        with tenant_context(tenant):
            client.force_login(admin_user)
            resp = client.post(reverse("event-admin-wizard-place"), {})
            assert resp.status_code == 422

    def test_post_nouveau_lieu_sans_lat_lng_renvoie_422(self, client, admin_user, tenant):
        with tenant_context(tenant):
            client.force_login(admin_user)
            resp = client.post(reverse("event-admin-wizard-place"), {
                "new_address_name": "X",
                "street_address": "1 rue",
                "postal_code": "97400",
                "address_locality": "Saint-Denis",
            })
            assert resp.status_code == 422
            assert b"place_latitude" in resp.content or b"latitude" in resp.content


@pytest.mark.django_db
class TestStep2EventAccess:
    def test_get_step2_sans_session_redirige_step1(self, client, admin_user, tenant):
        with tenant_context(tenant):
            client.force_login(admin_user)
            resp = client.get(reverse("event-admin-wizard-event"))
            assert resp.status_code == 302
            assert resp.url == reverse("event-admin-wizard-place")


@pytest.mark.django_db
class TestStep2EventSubmit:
    def _seed_session(self, client, tenant):
        from BaseBillet.models import PostalAddress
        with tenant_context(tenant):
            addr = PostalAddress.objects.first()
            session = client.session
            session["event_wizard_admin_postal_address_pk"] = str(addr.pk)
            session.save()
            return addr

    def test_post_minimum_cree_event_publie(self, client, admin_user, tenant):
        from BaseBillet.models import Event
        addr = self._seed_session(client, tenant)
        client.force_login(admin_user)
        with tenant_context(tenant):
            resp = client.post(reverse("event-admin-wizard-event"), {
                "name": "Mon premier event wizard",
                "datetime": "2026-12-31T20:00",
                "long_description": "Hello",
            })
            assert resp.status_code == 302
            event = Event.objects.filter(name="Mon premier event wizard").first()
            assert event
            assert event.published is True
            assert event.is_proposal is False
            assert event.postal_address_id == addr.pk
            assert event.created_by == admin_user

    def test_post_avec_tags_cree_tags_inexistants(self, client, admin_user, tenant):
        from BaseBillet.models import Event, Tag
        self._seed_session(client, tenant)
        client.force_login(admin_user)
        with tenant_context(tenant):
            resp = client.post(reverse("event-admin-wizard-event"), {
                "name": "Event with tags",
                "datetime": "2026-12-31T20:00",
                "tags": "Atelier, Gratuit, Nouveau-Tag-Wizard",
            })
            assert resp.status_code == 302
            event = Event.objects.get(name="Event with tags")
            tag_names = list(event.tag.values_list("name", flat=True))
            assert "Atelier" in tag_names
            assert "Nouveau-Tag-Wizard" in tag_names

    def test_post_succes_nettoie_session(self, client, admin_user, tenant):
        self._seed_session(client, tenant)
        client.force_login(admin_user)
        with tenant_context(tenant):
            client.post(reverse("event-admin-wizard-event"), {
                "name": "Cleanup test",
                "datetime": "2026-12-31T20:00",
            })
            assert "event_wizard_admin_postal_address_pk" not in client.session
```

- [ ] **S3.5.2 — Lancer les tests wizard admin**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_event_wizard_admin.py -q`
Expected : `≥ 8 passed` (les tests laissés `...` doivent être implémentés ou skippés explicitement). Itérer jusqu'au vert.

### S3.6 — Préparer le commit S3

```
feat(BaseBillet): add admin event creation wizard (2 steps)

- BaseBillet/validators.py: +WizardPlaceSerializer, +WizardEventAdminSerializer
- BaseBillet/views.py: +EventWizardAdmin ViewSet (step1_place, step2_event)
- BaseBillet/urls.py: +2 routes (event-admin-wizard-place|event)
- templates/reunion/views/event/wizard/: _base.html, _form_lieu.html,
  admin_step1_place.html, admin_step2_event.html
- tests/pytest/test_event_wizard_admin.py: 9 tests (access, validation, creation)

The wizard uses widget_carte_adresse.html (Leaflet + geosearch) for new
places. Session storage `event_wizard_admin_*` keys.

Spec: TECH_DOC/SESSIONS/EVENT_WIZARD/SPEC.md section 5
```

---

## Session S4 — Wizard PUBLIC (OTP + 2 steps + done)

**Référence spec :** [SPEC.md](SPEC.md) section 6. **Dépend de S1** (service OTP).

### Files

- Modify: `BaseBillet/validators.py` (+`EventProposalEmailSerializer`, +`WizardEventPublicSerializer`)
- Modify: `BaseBillet/views.py` (+`EventWizardPublic` ViewSet)
- Modify: `BaseBillet/urls.py` (+6 routes)
- Create: `BaseBillet/templates/reunion/views/event/wizard/public_step0_email.html`
- Create: `BaseBillet/templates/reunion/views/event/wizard/public_step0_verify.html`
- Create: `BaseBillet/templates/reunion/views/event/wizard/public_step1_place.html`
- Create: `BaseBillet/templates/reunion/views/event/wizard/public_step2_event.html`
- Create: `BaseBillet/templates/reunion/views/event/wizard/public_done.html`
- Create: `tests/pytest/test_event_wizard_public.py`

### S4.1 — Serializers

- [ ] **S4.1.1 — Ajouter dans `BaseBillet/validators.py`**

```python
class EventProposalEmailSerializer(serializers.Serializer):
    """
    Step 0 du wizard public : email + confirmation + honeypot.
    / Step 0 of public wizard: email + confirm + honeypot.
    """
    email = serializers.EmailField(required=True)
    email_confirm = serializers.EmailField(required=True)
    # Honeypot : doit etre vide. Si rempli -> bot.
    # / Honeypot: must be empty. If filled -> bot.
    website = serializers.CharField(required=False, allow_blank=True)

    def validate_website(self, value):
        if value:
            raise serializers.ValidationError(_("Spam detected."))
        return value

    def validate(self, attrs):
        if attrs["email"].lower() != attrs["email_confirm"].lower():
            raise serializers.ValidationError({
                "email_confirm": _("Les emails ne correspondent pas."),
            })
        return attrs


class WizardEventPublicSerializer(serializers.Serializer):
    """
    Step 2 du wizard public : strict mini-form.
    / Public wizard step 2: strict mini-form.
    """
    name = serializers.CharField(max_length=200)
    datetime = serializers.DateTimeField()
    long_description = serializers.CharField(
        required=False, allow_blank=True, max_length=5000,
    )
    image = serializers.ImageField(required=False, allow_null=True)
```

### S4.2 — ViewSet `EventWizardPublic`

- [ ] **S4.2.1 — Ajouter dans `BaseBillet/views.py` (après EventWizardAdmin)**

```python
class EventWizardPublic(viewsets.ViewSet):
    """
    Wizard public anonyme de proposition d'evenement.
    OTP email + 2 steps (place, event) + done.

    L'event est cree avec published=False, is_proposal=True, soumis a
    moderation admin (badge sidebar + filtre + action bulk).

    / Public anonymous event proposal wizard.
    OTP email + 2 steps + done.
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    SESSION_PREFIX = "event_proposal"
    OTP_PREFIX = "event_proposal"  # cle session OTP

    def _session_key(self, suffix: str) -> str:
        return f"{self.SESSION_PREFIX}_{suffix}"

    def _otp(self, request):
        from AuthBillet.otp_session import OtpSession
        return OtpSession(request, prefix=self.OTP_PREFIX)

    def _require_otp_confirmed(self, request):
        """Garde : retourne un Redirect si OTP non confirme, None sinon.
        / Guard: returns Redirect if OTP not confirmed, None otherwise."""
        if not self._otp(request).is_confirmed():
            return redirect("event-propose-email")
        return None

    @action(detail=False, methods=["GET", "POST"], url_path="email",
            throttle_classes=[AnonRateThrottle])
    def step0_email(self, request):
        if request.method == "GET":
            context = get_context(request)
            context.update({
                "wizard_title": _("Proposer un evenement"),
                "wizard_step_label": _("Etape 1 — Votre email"),
                "initial": {}, "errors": {},
            })
            return render(request, "reunion/views/event/wizard/public_step0_email.html",
                          context=context)

        # POST
        serializer = EventProposalEmailSerializer(data=request.POST)
        if not serializer.is_valid():
            context = get_context(request)
            context.update({
                "wizard_title": _("Proposer un evenement"),
                "wizard_step_label": _("Etape 1 — Votre email"),
                "initial": request.POST.dict(),
                "errors": serializer.errors,
            })
            return render(request, "reunion/views/event/wizard/public_step0_email.html",
                          context=context, status=422)

        config = Configuration.get_solo()
        self._otp(request).start(
            email=serializer.validated_data["email"],
            libelle_action=str(_("Proposer un evenement")),
            nom_organisation=config.organisation,
        )
        return redirect("event-propose-verify")

    @action(detail=False, methods=["GET", "POST"], url_path="verify")
    def step0_verify(self, request):
        otp = self._otp(request)
        if not otp.email():
            return redirect("event-propose-email")

        if request.method == "GET":
            context = get_context(request)
            context.update({
                "wizard_title": _("Proposer un evenement"),
                "wizard_step_label": _("Etape 2 — Code de verification"),
                "email": otp.email(),
                "attempts_remaining": otp.attempts_remaining(),
                "can_resend": otp.can_resend(),
                "seconds_before_resend": otp.seconds_before_resend(),
                "errors": {},
            })
            return render(request, "reunion/views/event/wizard/public_step0_verify.html",
                          context=context)

        # POST
        if otp.verify(request.POST.get("otp", "").strip()):
            return redirect("event-propose-place")

        # Echec : si max attempts atteint, reset + retour step0
        # / Failure: if max attempts reached, reset + back to step0
        if otp.attempts_remaining() == 0:
            otp.reset()
            messages.add_message(request, messages.ERROR,
                _("Trop de tentatives. Recommencez avec votre email."))
            return redirect("event-propose-email")

        context = get_context(request)
        context.update({
            "wizard_title": _("Proposer un evenement"),
            "wizard_step_label": _("Etape 2 — Code de verification"),
            "email": otp.email(),
            "attempts_remaining": otp.attempts_remaining(),
            "can_resend": otp.can_resend(),
            "seconds_before_resend": otp.seconds_before_resend(),
            "errors": {"otp": [_("Code incorrect ou expire.")]},
        })
        return render(request, "reunion/views/event/wizard/public_step0_verify.html",
                      context=context, status=422)

    @action(detail=False, methods=["POST"], url_path="resend",
            throttle_classes=[AnonRateThrottle])
    def step0_resend(self, request):
        otp = self._otp(request)
        if not otp.email():
            return redirect("event-propose-email")
        if not otp.can_resend():
            messages.add_message(request, messages.WARNING,
                _("Patientez %(s)s secondes avant de redemander un code.") % {
                    "s": otp.seconds_before_resend(),
                })
            return redirect("event-propose-verify")

        config = Configuration.get_solo()
        otp.start(
            email=otp.email(),
            libelle_action=str(_("Proposer un evenement")),
            nom_organisation=config.organisation,
        )
        messages.add_message(request, messages.SUCCESS,
            _("Nouveau code envoye."))
        return redirect("event-propose-verify")

    @action(detail=False, methods=["GET", "POST"], url_path="place")
    def step1_place(self, request):
        guard = self._require_otp_confirmed(request)
        if guard:
            return guard

        # Logique identique a EventWizardAdmin.step1_place sauf URL et
        # cle session. On factorise via une fonction _handle_place.
        # / Same logic as admin step1 except URL + session prefix.
        return self._handle_place(request,
            template="reunion/views/event/wizard/public_step1_place.html",
            form_action_url=reverse("event-propose-place"),
            next_step_url=reverse("event-propose-event"),
            wizard_step_label=_("Etape 3 / 4 — Lieu"),
        )

    def _handle_place(self, request, template, form_action_url,
                       next_step_url, wizard_step_label):
        """
        Factorisation de la logique step "Lieu" entre admin et public.
        / Shared "Place" step logic between admin and public wizards.
        """
        addresses = PostalAddress.objects.all().order_by("name", "address_locality")
        config = Configuration.get_solo()

        if request.method == "GET":
            context = get_context(request)
            context.update({
                "wizard_title": _("Proposer un evenement"),
                "wizard_step_label": wizard_step_label,
                "addresses": addresses,
                "default_address_pk": config.postal_address.pk if config.postal_address else None,
                "form_action_url": form_action_url,
                "next_step_label": _("Continuer"),
                "initial": {}, "errors": {},
            })
            return render(request, template, context=context)

        serializer = WizardPlaceSerializer(data=request.POST)
        if not serializer.is_valid():
            context = get_context(request)
            context.update({
                "wizard_title": _("Proposer un evenement"),
                "wizard_step_label": wizard_step_label,
                "addresses": addresses,
                "default_address_pk": config.postal_address.pk if config.postal_address else None,
                "form_action_url": form_action_url,
                "next_step_label": _("Continuer"),
                "initial": request.POST.dict(),
                "errors": serializer.errors,
            })
            return render(request, template, context=context, status=422)

        data = serializer.validated_data
        if data["_mode"] == "existing":
            postal_address_pk = data["postal_address"]
        else:
            from api_v2.serializers import PostalAddressCreateSerializer
            payload = {
                "name": data["new_address_name"],
                "streetAddress": data["street_address"],
                "addressLocality": data["address_locality"],
                "postalCode": data["postal_code"],
                "addressCountry": data.get("address_country") or "France",
            }
            pa_ser = PostalAddressCreateSerializer(data=payload, context={"request": request})
            pa_ser.is_valid(raise_exception=True)
            addr = pa_ser.save()
            addr.latitude = data["place_latitude"]
            addr.longitude = data["place_longitude"]
            addr.save(update_fields=["latitude", "longitude"])
            postal_address_pk = str(addr.pk)

        request.session[self._session_key("postal_address_pk")] = postal_address_pk
        return redirect(next_step_url)

    @action(detail=False, methods=["GET", "POST"], url_path="event")
    def step2_event(self, request):
        guard = self._require_otp_confirmed(request)
        if guard:
            return guard

        postal_address_pk = request.session.get(self._session_key("postal_address_pk"))
        if not postal_address_pk:
            return redirect("event-propose-place")

        try:
            postal_address = PostalAddress.objects.get(pk=postal_address_pk)
        except PostalAddress.DoesNotExist:
            return redirect("event-propose-place")

        if request.method == "GET":
            context = get_context(request)
            context.update({
                "wizard_title": _("Proposer un evenement"),
                "wizard_step_label": _("Etape 4 / 4 — Details"),
                "postal_address": postal_address,
                "initial": {}, "errors": {},
            })
            return render(request, "reunion/views/event/wizard/public_step2_event.html",
                          context=context)

        # POST
        data_combined = request.POST.copy()
        for fkey in request.FILES:
            data_combined[fkey] = request.FILES[fkey]
        serializer = WizardEventPublicSerializer(data=data_combined)
        if not serializer.is_valid():
            context = get_context(request)
            context.update({
                "wizard_title": _("Proposer un evenement"),
                "wizard_step_label": _("Etape 4 / 4 — Details"),
                "postal_address": postal_address,
                "initial": request.POST.dict(),
                "errors": serializer.errors,
            })
            return render(request, "reunion/views/event/wizard/public_step2_event.html",
                          context=context, status=422)

        validated = serializer.validated_data
        event = Event(
            name=validated["name"].strip(),
            datetime=validated["datetime"],
            long_description=admin_clean_html(validated.get("long_description") or ""),
            postal_address=postal_address,
            created_by=None,
            published=False,
            is_proposal=True,
        )
        if validated.get("image"):
            event.img = validated["image"]
        event.save()

        # Reset complet : on libere toute la session du wizard public
        # / Full reset: release all wizard session keys
        request.session.pop(self._session_key("postal_address_pk"), None)
        self._otp(request).reset()

        return redirect("event-propose-done")

    @action(detail=False, methods=["GET"], url_path="done")
    def done(self, request):
        context = get_context(request)
        context.update({
            "wizard_title": _("Merci !"),
            "wizard_step_label": "",
        })
        return render(request, "reunion/views/event/wizard/public_done.html",
                      context=context)
```

Imports en haut de `views.py` :
```python
from rest_framework.throttling import AnonRateThrottle
from BaseBillet.validators import EventProposalEmailSerializer, WizardEventPublicSerializer
```

### S4.3 — Routes public

- [ ] **S4.3.1 — Ajouter dans `BaseBillet/urls.py`**

```python
event_wizard_public_email = EventWizardPublic.as_view({"get": "step0_email", "post": "step0_email"})
event_wizard_public_verify = EventWizardPublic.as_view({"get": "step0_verify", "post": "step0_verify"})
event_wizard_public_resend = EventWizardPublic.as_view({"post": "step0_resend"})
event_wizard_public_place = EventWizardPublic.as_view({"get": "step1_place", "post": "step1_place"})
event_wizard_public_event = EventWizardPublic.as_view({"get": "step2_event", "post": "step2_event"})
event_wizard_public_done = EventWizardPublic.as_view({"get": "done"})

# Dans urlpatterns :
path("event/propose/", lambda r: redirect("event-propose-email"), name="event-propose"),
path("event/propose/email/", event_wizard_public_email, name="event-propose-email"),
path("event/propose/verify/", event_wizard_public_verify, name="event-propose-verify"),
path("event/propose/resend/", event_wizard_public_resend, name="event-propose-resend"),
path("event/propose/place/", event_wizard_public_place, name="event-propose-place"),
path("event/propose/event/", event_wizard_public_event, name="event-propose-event"),
path("event/propose/done/", event_wizard_public_done, name="event-propose-done"),
```

Import :
```python
from BaseBillet.views import EventWizardPublic
from django.shortcuts import redirect
```

### S4.4 — Templates wizard public

- [ ] **S4.4.1 — Créer `public_step0_email.html`**

```html
{% extends "reunion/views/event/wizard/_base.html" %}
{% load i18n %}

{% block step_content %}
<p class="text-muted mb-3">
    {% translate "Pour proposer un evenement, indiquez votre email. Vous recevrez un code a 6 chiffres pour confirmer." %}
</p>

{% if errors %}
<div class="alert alert-danger mb-3" role="alert">
    <ul class="mb-0 small">
        {% for field, msgs in errors.items %}
            {% if field != "website" %}<li><strong>{{ field }}</strong> : {{ msgs|join:" / " }}</li>{% endif %}
        {% endfor %}
    </ul>
</div>
{% endif %}

<form method="post" action="{% url 'event-propose-email' %}"
      novalidate data-testid="propose-email-form" class="vstack gap-3">
    {% csrf_token %}

    {# Honeypot : invisible pour les humains, visible pour les bots. #}
    {# / Honeypot: invisible to humans, visible to bots. #}
    <div style="position:absolute; left:-9999px;" aria-hidden="true">
        <label for="website">Website</label>
        <input type="text" id="website" name="website" tabindex="-1" autocomplete="off">
    </div>

    <div>
        <label for="email" class="form-label">{% translate "Email" %} <span class="text-danger">*</span></label>
        <input type="email" id="email" name="email" required class="form-control"
               value="{{ initial.email|default:'' }}" data-testid="propose-email">
    </div>

    <div>
        <label for="email_confirm" class="form-label">{% translate "Confirmer l'email" %} <span class="text-danger">*</span></label>
        <input type="email" id="email_confirm" name="email_confirm" required class="form-control"
               value="{{ initial.email_confirm|default:'' }}" data-testid="propose-email-confirm">
    </div>

    <div class="d-flex justify-content-between pt-2">
        <a href="{% url 'event-list' %}" class="btn btn-link">{% translate "Annuler" %}</a>
        <button type="submit" class="btn btn-primary btn-lg" data-testid="propose-email-submit">
            {% translate "Envoyer le code" %} <i class="bi bi-envelope ms-1" aria-hidden="true"></i>
        </button>
    </div>
</form>
{% endblock %}
```

- [ ] **S4.4.2 — Créer `public_step0_verify.html`**

```html
{% extends "reunion/views/event/wizard/_base.html" %}
{% load i18n %}

{% block step_content %}
<p class="text-muted mb-3">
    {% blocktranslate with email=email %}Un code a 6 chiffres a ete envoye a <strong>{{ email }}</strong>. Saisissez-le ci-dessous.{% endblocktranslate %}
</p>

{% if errors.otp %}
<div class="alert alert-danger mb-3" role="alert" data-testid="propose-verify-error">
    {{ errors.otp|join:" / " }}
    {% if attempts_remaining %}
        <br><small>{% blocktranslate with n=attempts_remaining %}Tentatives restantes : {{ n }}.{% endblocktranslate %}</small>
    {% endif %}
</div>
{% endif %}

<form method="post" action="{% url 'event-propose-verify' %}"
      novalidate data-testid="propose-verify-form" class="vstack gap-3">
    {% csrf_token %}
    <div>
        <label for="otp" class="form-label">{% translate "Code a 6 chiffres" %} <span class="text-danger">*</span></label>
        <input type="text" id="otp" name="otp" required pattern="\d{6}" maxlength="6"
               inputmode="numeric" autocomplete="one-time-code"
               class="form-control form-control-lg text-center"
               style="font-family: monospace; letter-spacing: 0.5em;"
               data-testid="propose-otp-input">
    </div>

    <div class="d-flex justify-content-between align-items-center pt-2">
        <form method="post" action="{% url 'event-propose-resend' %}" class="d-inline">
            {% csrf_token %}
            <button type="submit" class="btn btn-link btn-sm" data-testid="propose-resend"
                    {% if not can_resend %}disabled{% endif %}>
                {% if can_resend %}
                    {% translate "Renvoyer le code" %}
                {% else %}
                    {% blocktranslate with s=seconds_before_resend %}Renvoyer dans {{ s }}s{% endblocktranslate %}
                {% endif %}
            </button>
        </form>
        <button type="submit" class="btn btn-primary btn-lg" data-testid="propose-verify-submit">
            {% translate "Verifier" %} <i class="bi bi-arrow-right ms-1" aria-hidden="true"></i>
        </button>
    </div>
</form>
{% endblock %}
```

**Note** : un `<form>` imbriqué dans un autre `<form>` est invalide en HTML. Pour le bouton "Renvoyer le code", utiliser un formulaire séparé OU un lien `hx-post` HTMX. Correction : sortir le `<form action='resend'>` hors du form principal :

```html
<form method="post" action="{% url 'event-propose-verify' %}" novalidate class="vstack gap-3">
    {% csrf_token %}
    <div>...input otp...</div>
    <div class="d-flex justify-content-end pt-2">
        <button type="submit" class="btn btn-primary btn-lg">...</button>
    </div>
</form>

<form method="post" action="{% url 'event-propose-resend' %}" class="mt-3 text-center">
    {% csrf_token %}
    <button type="submit" class="btn btn-link btn-sm" {% if not can_resend %}disabled{% endif %}>...</button>
</form>
```

Adapter le template ci-dessus en conséquence.

- [ ] **S4.4.3 — Créer `public_step1_place.html`**

```html
{% extends "reunion/views/event/wizard/_base.html" %}
{% load i18n %}

{% block step_content %}
<p class="text-muted mb-3">
    {% translate "Choisissez le lieu de l'evenement." %}
</p>

{% include "reunion/views/event/wizard/_form_lieu.html" %}
{% endblock %}
```

- [ ] **S4.4.4 — Créer `public_step2_event.html`**

```html
{% extends "reunion/views/event/wizard/_base.html" %}
{% load i18n %}

{% block step_content %}
<div class="alert alert-info py-2 mb-3" role="status">
    <i class="bi bi-geo-alt me-1" aria-hidden="true"></i>
    {% blocktranslate with name=postal_address.name|default:postal_address.address_locality city=postal_address.address_locality %}Lieu : <strong>{{ name }}</strong> — {{ city }}{% endblocktranslate %}
    <a href="{% url 'event-propose-place' %}" class="ms-2 small text-decoration-none">
        <i class="bi bi-pencil" aria-hidden="true"></i> {% translate "Modifier" %}
    </a>
</div>

{% if errors %}
<div class="alert alert-danger mb-3" role="alert">
    <ul class="mb-0 small">
        {% for field, msgs in errors.items %}<li><strong>{{ field }}</strong> : {{ msgs|join:" / " }}</li>{% endfor %}
    </ul>
</div>
{% endif %}

<form method="post" action="{% url 'event-propose-event' %}"
      enctype="multipart/form-data" novalidate
      data-testid="propose-event-form" class="vstack gap-3">
    {% csrf_token %}

    <div>
        <label for="name" class="form-label">{% translate "Nom de l'evenement" %} <span class="text-danger">*</span></label>
        <input type="text" id="name" name="name" required maxlength="200"
               value="{{ initial.name|default:'' }}" class="form-control"
               data-testid="propose-event-name">
    </div>

    <div>
        <label for="datetime" class="form-label">{% translate "Date et heure" %} <span class="text-danger">*</span></label>
        <input type="datetime-local" id="datetime" name="datetime" required
               value="{{ initial.datetime|default:'' }}" class="form-control"
               data-testid="propose-event-datetime">
    </div>

    <div>
        <label for="long_description" class="form-label">{% translate "Description" %}</label>
        <textarea id="long_description" name="long_description" rows="4" maxlength="5000"
                  class="form-control"
                  data-testid="propose-event-description">{{ initial.long_description|default:'' }}</textarea>
    </div>

    <div>
        <label for="image" class="form-label">{% translate "Image (optionnel)" %}</label>
        <input type="file" id="image" name="image" accept="image/jpeg,image/png,image/webp"
               class="form-control" data-testid="propose-event-image">
        <div class="form-text">{% translate "JPEG, PNG ou WebP — 5 Mo maximum." %}</div>
    </div>

    <div class="alert alert-warning small mt-2">
        <i class="bi bi-info-circle me-1" aria-hidden="true"></i>
        {% translate "Votre proposition sera relue par un administrateur avant publication." %}
    </div>

    <div class="d-flex justify-content-between pt-2">
        <a href="{% url 'event-propose-place' %}" class="btn btn-link">
            <i class="bi bi-arrow-left me-1" aria-hidden="true"></i> {% translate "Precedent" %}
        </a>
        <button type="submit" class="btn btn-primary btn-lg" data-testid="propose-event-submit">
            {% translate "Envoyer ma proposition" %}
        </button>
    </div>
</form>
{% endblock %}
```

- [ ] **S4.4.5 — Créer `public_done.html`**

```html
{% extends "reunion/views/event/wizard/_base.html" %}
{% load i18n %}

{% block step_content %}
<div class="text-center py-4" data-testid="propose-done">
    <i class="bi bi-check-circle text-success" style="font-size: 3rem;" aria-hidden="true"></i>
    <h2 class="h4 mt-3">{% translate "Merci pour votre proposition !" %}</h2>
    <p class="text-muted">
        {% translate "Votre proposition d'evenement a ete enregistree." %}<br>
        {% translate "Un administrateur va la valider, puis elle apparaitra dans l'agenda." %}
    </p>
    <a href="{% url 'event-list' %}" class="btn btn-primary mt-3">
        <i class="bi bi-arrow-left me-1" aria-hidden="true"></i>
        {% translate "Retour a l'agenda" %}
    </a>
</div>
{% endblock %}
```

### S4.5 — Tests wizard public

- [ ] **S4.5.1 — Créer `tests/pytest/test_event_wizard_public.py`**

```python
"""
Tests du wizard public anonyme de proposition d'evenement (S4).
/ Tests for the public anonymous event proposal wizard.

LOCALISATION : tests/pytest/test_event_wizard_public.py
"""

from unittest.mock import patch

import pytest
from django.urls import reverse
from django_tenants.utils import tenant_context

from Customers.models import Client


@pytest.fixture
def tenant():
    return Client.objects.exclude(schema_name="public").first()


@pytest.mark.django_db
class TestStep0Email:
    def test_get_accessible_anonyme(self, client, tenant):
        with tenant_context(tenant):
            resp = client.get(reverse("event-propose-email"))
            assert resp.status_code == 200
            assert b"propose-email-form" in resp.content

    def test_post_emails_non_concordants_422(self, client, tenant):
        with tenant_context(tenant):
            resp = client.post(reverse("event-propose-email"), {
                "email": "a@x.fr", "email_confirm": "b@x.fr",
            })
            assert resp.status_code == 422

    def test_post_honeypot_rempli_422(self, client, tenant):
        with tenant_context(tenant):
            resp = client.post(reverse("event-propose-email"), {
                "email": "a@x.fr", "email_confirm": "a@x.fr",
                "website": "https://spam.example",
            })
            assert resp.status_code == 422

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_post_succes_envoie_mail_et_redirige(self, mock_mail, client, tenant):
        with tenant_context(tenant):
            resp = client.post(reverse("event-propose-email"), {
                "email": "a@x.fr", "email_confirm": "a@x.fr",
            })
            assert resp.status_code == 302
            assert resp.url == reverse("event-propose-verify")
            assert mock_mail.called


@pytest.mark.django_db
class TestStep0Verify:
    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_get_sans_email_redirige_email(self, _m, client, tenant):
        with tenant_context(tenant):
            resp = client.get(reverse("event-propose-verify"))
            assert resp.status_code == 302
            assert resp.url == reverse("event-propose-email")

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_code_correct_redirige_place(self, _m, client, tenant):
        from AuthBillet.otp_service import hash_code_otp
        with tenant_context(tenant):
            client.post(reverse("event-propose-email"), {
                "email": "a@x.fr", "email_confirm": "a@x.fr",
            })
            session = client.session
            session["event_proposal_otp_hash"] = hash_code_otp("000111")
            session.save()
            resp = client.post(reverse("event-propose-verify"), {"otp": "000111"})
            assert resp.status_code == 302
            assert resp.url == reverse("event-propose-place")

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_code_incorrect_422(self, _m, client, tenant):
        from AuthBillet.otp_service import hash_code_otp
        with tenant_context(tenant):
            client.post(reverse("event-propose-email"), {
                "email": "a@x.fr", "email_confirm": "a@x.fr",
            })
            session = client.session
            session["event_proposal_otp_hash"] = hash_code_otp("000111")
            session.save()
            resp = client.post(reverse("event-propose-verify"), {"otp": "999999"})
            assert resp.status_code == 422


@pytest.mark.django_db
class TestBypassImpossible:
    def test_step1_place_sans_otp_redirige_email(self, client, tenant):
        with tenant_context(tenant):
            resp = client.get(reverse("event-propose-place"))
            assert resp.status_code == 302
            assert resp.url == reverse("event-propose-email")

    def test_step2_event_sans_otp_redirige_email(self, client, tenant):
        with tenant_context(tenant):
            resp = client.get(reverse("event-propose-event"))
            assert resp.status_code == 302
            assert resp.url == reverse("event-propose-email")


@pytest.mark.django_db
class TestSubmissionFinale:
    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_step2_cree_event_proposal(self, _m, client, tenant):
        from BaseBillet.models import Event, PostalAddress
        with tenant_context(tenant):
            addr = PostalAddress.objects.first()
            session = client.session
            session["event_proposal_otp_confirmed"] = True
            session["event_proposal_otp_email"] = "a@x.fr"
            session["event_proposal_postal_address_pk"] = str(addr.pk)
            session.save()

            resp = client.post(reverse("event-propose-event"), {
                "name": "Proposition publique test",
                "datetime": "2026-12-31T20:00",
            })
            assert resp.status_code == 302
            assert resp.url == reverse("event-propose-done")
            event = Event.objects.filter(name="Proposition publique test").first()
            assert event is not None
            assert event.published is False
            assert event.is_proposal is True
            assert event.created_by is None

    @patch("AuthBillet.otp_session.envoyer_email_otp")
    def test_step2_succes_reset_session(self, _m, client, tenant):
        from BaseBillet.models import PostalAddress
        with tenant_context(tenant):
            addr = PostalAddress.objects.first()
            session = client.session
            session["event_proposal_otp_confirmed"] = True
            session["event_proposal_otp_email"] = "a@x.fr"
            session["event_proposal_postal_address_pk"] = str(addr.pk)
            session.save()

            client.post(reverse("event-propose-event"), {
                "name": "Test reset",
                "datetime": "2026-12-31T20:00",
            })
            assert "event_proposal_postal_address_pk" not in client.session
            assert "event_proposal_otp_confirmed" not in client.session


@pytest.mark.django_db
class TestDone:
    def test_done_accessible_sans_garde(self, client, tenant):
        with tenant_context(tenant):
            resp = client.get(reverse("event-propose-done"))
            assert resp.status_code == 200
            assert b"propose-done" in resp.content
```

- [ ] **S4.5.2 — Lancer les tests wizard public**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_event_wizard_public.py -q`
Expected : tests verts. Itérer.

### S4.6 — Préparer le commit S4

```
feat(BaseBillet): add public anonymous event proposal wizard

- BaseBillet/validators.py: +EventProposalEmailSerializer, +WizardEventPublicSerializer
- BaseBillet/views.py: +EventWizardPublic ViewSet (OTP step0 + place + event + done)
- BaseBillet/urls.py: +7 routes (event-propose-*)
- templates/reunion/views/event/wizard/: public_step0_email.html, public_step0_verify.html,
  public_step1_place.html, public_step2_event.html, public_done.html
- tests/pytest/test_event_wizard_public.py: ~12 tests (OTP, bypass, submission)

Uses AuthBillet.otp_session.OtpSession with prefix "event_proposal".
Created events: published=False, is_proposal=True, created_by=None.

Spec: TECH_DOC/SESSIONS/EVENT_WIZARD/SPEC.md section 6
```

---

## Session S5 — Modération admin + boutons event/list

**Référence spec :** [SPEC.md](SPEC.md) sections 8 et 10.3.

### Files

- Modify: `Administration/admin/dashboard.py` (+badge callback + entrée sidebar)
- Modify: `Administration/admin_tenant.py` (+filtre IsProposalFilter + action approuver_propositions sur EventAdmin)
- Modify: `BaseBillet/templates/reunion/views/event/list.html` (ajout 2 boutons)
- Create: `tests/pytest/test_event_proposal_admin.py`

### S5.1 — Badge sidebar Unfold

- [ ] **S5.1.1 — Ajouter le callback dans `Administration/admin/dashboard.py`**

Ajouter après `adhesion_badge_callback` :

```python
def event_proposals_badge_callback(request):
    """
    Compte des propositions d'event en attente de validation.
    / Count of pending event proposals.

    Affiche un badge "+ N" sur le menu "Events" si des propositions
    publiques attendent moderation (is_proposal=True, published=False).
    """
    from BaseBillet.models import Event
    count = Event.objects.filter(is_proposal=True, published=False).count()
    return f"+ {count}" if count else None
```

- [ ] **S5.1.2 — Brancher le badge sur l'item "Events"**

Localiser dans `get_sidebar_navigation()` la section `module_billetterie`, l'item correspondant aux events (link `staff_admin:BaseBillet_event_changelist`). Ajouter la clé `badge` :

```python
{
    "title": _("Events"),
    "icon": "event",
    "link": reverse_lazy("staff_admin:BaseBillet_event_changelist"),
    "badge": "Administration.admin.dashboard.event_proposals_badge_callback",
    "permission": admin_permission,
},
```

### S5.2 — Filtre + action bulk sur EventAdmin

- [ ] **S5.2.1 — Localiser `EventAdmin` dans `Administration/admin_tenant.py`**

```bash
grep -n "class EventAdmin\|@admin.register(Event" /home/jonas/TiBillet/dev/Lespass/Administration/admin_tenant.py
```

- [ ] **S5.2.2 — Ajouter le filtre `IsProposalFilter`** juste au-dessus de la classe `EventAdmin`

```python
class IsProposalFilter(admin.SimpleListFilter):
    """
    Filtre sidebar Unfold pour distinguer propositions publiques en
    attente, propositions approuvees et events normaux.
    / Unfold sidebar filter for pending proposals, approved proposals
    and regular events.
    """
    title = _("Proposal status")
    parameter_name = "proposal_status"

    def lookups(self, request, model_admin):
        return [
            ("pending", _("Proposals pending")),
            ("approved", _("Proposals approved")),
            ("regular", _("Regular events")),
        ]

    def queryset(self, request, queryset):
        if self.value() == "pending":
            return queryset.filter(is_proposal=True, published=False)
        if self.value() == "approved":
            return queryset.filter(is_proposal=True, published=True)
        if self.value() == "regular":
            return queryset.filter(is_proposal=False)
        return queryset
```

- [ ] **S5.2.3 — Ajouter le filtre dans `list_filter` de `EventAdmin`**

```python
list_filter = [IsProposalFilter, ...autres filtres existants...]
```

- [ ] **S5.2.4 — Ajouter l'action bulk `approuver_propositions`** dans `EventAdmin`

```python
@admin.action(description=_("Approve and publish selected proposals"))
def approuver_propositions(self, request, queryset):
    """
    Action bulk : pour chaque event selectionne qui est une proposition
    en attente, set is_proposal=False + published=True.
    / Bulk action: approve and publish selected pending proposals.
    """
    nb_approuvees = queryset.filter(is_proposal=True, published=False).update(
        is_proposal=False,
        published=True,
    )
    self.message_user(
        request,
        _("%(n)s proposal(s) approved.") % {"n": nb_approuvees},
        messages.SUCCESS,
    )
```

Et l'ajouter à `actions` :
```python
actions = ["approuver_propositions", ...autres actions...]
```

### S5.3 — Boutons sur event/list

- [ ] **S5.3.1 — Modifier `BaseBillet/templates/reunion/views/event/list.html`**

Dans le bloc des filtres (zone `.ms-auto`), ajouter :

```html
<div class="ms-auto d-flex align-items-center gap-2">
    <button class="btn btn-outline-secondary btn-sm d-inline-flex d-md-none"
            type="button" data-bs-toggle="collapse" data-bs-target="#tagFiltersCollapse">
        <i class="bi bi-sliders"></i> {% translate 'Filtres' %}
    </button>

    {# Bouton admin (admin uniquement) — wizard 2 etapes #}
    {# / Admin button (admin only) — 2-step wizard #}
    {% if user|can_create_event_tag %}
        <a class="btn btn-sm btn-success"
           href="{% url 'event-admin-wizard-place' %}"
           data-testid="btn-event-admin-add">
            <i class="bi bi-plus-circle" aria-hidden="true"></i>
            {% translate 'Ajouter un evenement' %}
        </a>
    {% endif %}

    {# Bouton public (tout le monde) — wizard avec OTP #}
    {# / Public button (everyone) — wizard with OTP #}
    <a class="btn btn-sm btn-outline-secondary"
       href="{% url 'event-propose-email' %}"
       data-testid="btn-event-public-propose">
        <i class="bi bi-megaphone" aria-hidden="true"></i>
        {% translate 'Proposer un evenement' %}
    </a>
</div>
```

### S5.4 — Tests modération admin

- [ ] **S5.4.1 — Créer `tests/pytest/test_event_proposal_admin.py`**

```python
"""
Tests de la moderation admin pour les propositions publiques.
/ Tests for admin moderation of public proposals.
"""

import pytest
from django.urls import reverse
from django.utils import timezone
from django_tenants.utils import tenant_context

from Customers.models import Client


@pytest.fixture
def tenant():
    return Client.objects.exclude(schema_name="public").first()


@pytest.fixture
def admin_user(tenant):
    from AuthBillet.models import TibilletUser
    with tenant_context(tenant):
        return TibilletUser.objects.filter(email="admin@admin.com").first()


@pytest.mark.django_db
class TestEventProposalsBadge:
    def test_callback_compte_propositions_pending(self, tenant):
        from BaseBillet.models import Event
        from Administration.admin.dashboard import event_proposals_badge_callback
        with tenant_context(tenant):
            Event.objects.filter(is_proposal=True).delete()
            for i in range(3):
                Event.objects.create(
                    name=f"Proposition {i}",
                    datetime=timezone.now() + timezone.timedelta(days=1),
                    is_proposal=True,
                    published=False,
                )
            assert event_proposals_badge_callback(None) == "+ 3"

    def test_callback_retourne_none_si_zero(self, tenant):
        from BaseBillet.models import Event
        from Administration.admin.dashboard import event_proposals_badge_callback
        with tenant_context(tenant):
            Event.objects.filter(is_proposal=True).delete()
            assert event_proposals_badge_callback(None) is None

    def test_callback_ignore_events_publies(self, tenant):
        from BaseBillet.models import Event
        from Administration.admin.dashboard import event_proposals_badge_callback
        with tenant_context(tenant):
            Event.objects.filter(is_proposal=True).delete()
            Event.objects.create(
                name="Approuvee",
                datetime=timezone.now() + timezone.timedelta(days=1),
                is_proposal=True,
                published=True,
            )
            assert event_proposals_badge_callback(None) is None


@pytest.mark.django_db
class TestActionBulkApprouver:
    def test_action_approuver_set_published_true_et_is_proposal_false(self, tenant, admin_user, client):
        from BaseBillet.models import Event
        with tenant_context(tenant):
            Event.objects.filter(is_proposal=True).delete()
            ev = Event.objects.create(
                name="A approuver",
                datetime=timezone.now() + timezone.timedelta(days=1),
                is_proposal=True,
                published=False,
            )
            client.force_login(admin_user)
            url = reverse("staff_admin:BaseBillet_event_changelist")
            resp = client.post(url, {
                "action": "approuver_propositions",
                "_selected_action": [str(ev.pk)],
            })
            assert resp.status_code in (200, 302)
            ev.refresh_from_db()
            assert ev.is_proposal is False
            assert ev.published is True
```

- [ ] **S5.4.2 — Lancer**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_event_proposal_admin.py -q`
Expected : tests verts.

### S5.5 — Préparer le commit S5

```
feat(Administration): event proposal moderation + wizard buttons on event/list

- Administration/admin/dashboard.py: +event_proposals_badge_callback + badge on Events item
- Administration/admin_tenant.py: +IsProposalFilter + approuver_propositions bulk action on EventAdmin
- BaseBillet/templates/reunion/views/event/list.html: +2 buttons (admin add + public propose)
- tests/pytest/test_event_proposal_admin.py: 5 tests (badge + bulk action)

Admin sees the proposals count badge in sidebar. Bulk-approve flips
is_proposal=False + published=True in one click.

Spec: TECH_DOC/SESSIONS/EVENT_WIZARD/SPEC.md sections 8 + 10.3
```

---

## Session S6 — Documentation & traductions

**Référence spec :** [SPEC.md](SPEC.md) sections 12 et 13.

### Files

- Create: `A TESTER et DOCUMENTER/event-wizards.md`
- Modify: `CHANGELOG.md` (ajout entrée chantier)
- À déclencher par le mainteneur : `makemessages` + `compilemessages` (NE PAS faire soi-même)

### S6.1 — Doc à tester

- [ ] **S6.1.1 — Créer `A TESTER et DOCUMENTER/event-wizards.md`**

```markdown
# Wizards de création et proposition d'évènement

## Ce qui a été fait

Refonte de la création d'évènement sur `event/list` en wizard 2 étapes
(admin) + ajout d'un wizard public anonyme avec OTP email pour
permettre à tout visiteur de proposer un évènement soumis à modération.

Service OTP DRY (`AuthBillet/otp_service.py` + `otp_session.py`) réutilisable
pour de futurs flows (login OTP, SSO, migration onboard).

### Modifications principales

| Fichier | Changement |
|---|---|
| `AuthBillet/otp_service.py` | NOUVEAU — service stateless |
| `AuthBillet/otp_session.py` | NOUVEAU — helper session HTTP |
| `BaseBillet/models.py` | +Event.is_proposal |
| `BaseBillet/views.py` | +EventWizardAdmin, +EventWizardPublic |
| `BaseBillet/validators.py` | +4 serializers wizard |
| `BaseBillet/templates/reunion/views/event/wizard/` | NOUVEAU (9 templates) |
| `Administration/admin_tenant.py` | +badge + filtre + action bulk |

## Tests à réaliser

### Test 1 : Wizard admin — adresse existante
1. Se connecter en admin (`admin@admin.com`).
2. Aller sur `/event/`.
3. Cliquer "Ajouter un évènement".
4. Garder "Utiliser une adresse existante", sélectionner l'adresse par défaut.
5. Cliquer "Continuer".
6. Remplir nom, date, description.
7. Cliquer "Créer l'évènement".
   - **Attendu** : redirection vers la page detail, toast succès, event apparait sur l'agenda.

### Test 2 : Wizard admin — nouveau lieu via carte
1. Sur step 1, basculer sur "Créer un nouveau lieu".
2. Saisir un nom de lieu (ex: "Salle des fêtes").
3. Utiliser la barre de recherche Leaflet pour trouver une adresse.
4. Déplacer le marqueur pour ajuster.
5. Vérifier que les 4 champs (rue, code postal, ville, pays) sont remplis automatiquement.
6. Cliquer "Continuer".
   - **Attendu** : PostalAddress créée en base avec `latitude` et `longitude` non null. Step 2 affiche le lieu en bandeau.

### Test 3 : Wizard public — flow complet
1. Se déconnecter (visiteur anonyme).
2. Sur `/event/`, cliquer "Proposer un évènement".
3. Saisir un email valide deux fois, soumettre.
4. Vérifier réception du mail (boite test).
5. Saisir le code à 6 chiffres, soumettre.
6. Choisir un lieu existant, soumettre.
7. Remplir nom + date + description.
8. Soumettre.
   - **Attendu** : page "Merci !", event créé avec `is_proposal=True, published=False`, n'apparait PAS sur `/event/`.

### Test 4 : Modération
1. Reconnexion admin.
2. Aller dans l'admin Django, vérifier le badge "+ 1" sur "Events" dans la sidebar.
3. Cliquer "Events", filtrer par "Proposals pending".
4. Cocher la proposition, lancer l'action "Approve and publish selected proposals".
   - **Attendu** : badge disparait, event devient visible sur `/event/`.

### Test 5 : Anti-spam
1. En anonyme, soumettre 3 demandes d'email consécutives en moins d'une heure.
   - **Attendu** : la 4e renvoie 429 (Throttle DRF).
2. Tenter de poster directement sur `/event/propose/event/` sans avoir fait l'OTP.
   - **Attendu** : redirection vers `/event/propose/email/`.

### Test 6 : Honeypot
1. Avec curl : `POST /event/propose/email/` avec `website=spam.example`.
   - **Attendu** : 422, pas d'email envoyé, aucune session OTP créée.

## Compatibilité

- Onboard inchangé : continue d'utiliser sa logique OTP custom.
- Les events existants restent `is_proposal=False` (défaut migration).
- L'ancien offcanvas a été retiré : tout test E2E le ciblant doit être adapté.

## Commandes de vérification en base

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import schema_context
from BaseBillet.models import Event
with schema_context('lespass'):
    print('Propositions en attente :', Event.objects.filter(is_proposal=True, published=False).count())
    print('Propositions approuvees :', Event.objects.filter(is_proposal=True, published=True).count())
"
```
```

### S6.2 — CHANGELOG

- [ ] **S6.2.1 — Ajouter dans `CHANGELOG.md` (en haut, après le titre)**

```markdown
## N. Wizards de création et proposition d'évènement / Event wizards

**Quoi / What:** Refonte de la création d'évènement en wizard 2 étapes (admin) avec carte interactive Leaflet pour les nouvelles adresses. Ajout d'un wizard public anonyme protégé par OTP email permettant à tout visiteur de proposer un évènement soumis à modération admin (badge sidebar Unfold + filtre + action bulk).

**Pourquoi / Why:** Améliorer l'UX admin (offcanvas → wizard plus FALC) et ouvrir la plateforme aux contributions publiques avec modération. Mettre en place un service OTP DRY (`AuthBillet/otp_service.py`) réutilisable pour de futurs flows (login OTP, SSO).

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `AuthBillet/otp_service.py` | NOUVEAU — service OTP stateless DRY |
| `AuthBillet/otp_session.py` | NOUVEAU — helper session HTTP |
| `AuthBillet/templates/auth/emails/otp_code.{html,txt}` | NOUVEAU — templates email génériques |
| `BaseBillet/models.py` | +`Event.is_proposal` (BooleanField default=False) |
| `BaseBillet/views.py` | +`EventWizardAdmin`, +`EventWizardPublic` ViewSets. Suppression `EventMVT.simple_*` |
| `BaseBillet/validators.py` | +4 serializers wizard |
| `BaseBillet/urls.py` | +8 routes (admin + public) |
| `BaseBillet/templates/reunion/views/event/wizard/` | NOUVEAU (9 templates) |
| `BaseBillet/templates/reunion/views/event/list.html` | Suppression offcanvas, ajout 2 boutons (admin + public) |
| `BaseBillet/templates/reunion/views/event/partial/simple_add_event.html` | supprimé |
| `BaseBillet/templates/reunion/views/event/partial/address_simple_add.html` | supprimé |
| `Administration/admin/dashboard.py` | +`event_proposals_badge_callback` + badge sur item Events |
| `Administration/admin_tenant.py` | +`IsProposalFilter` + action `approuver_propositions` sur `EventAdmin` |
| `tests/pytest/test_otp_service.py` | NOUVEAU — 16 tests |
| `tests/pytest/test_otp_session.py` | NOUVEAU — 12 tests |
| `tests/pytest/test_event_wizard_admin.py` | NOUVEAU — 9 tests |
| `tests/pytest/test_event_wizard_public.py` | NOUVEAU — 12 tests |
| `tests/pytest/test_event_proposal_admin.py` | NOUVEAU — 5 tests |
| `TECH_DOC/SESSIONS/EVENT_WIZARD/` | NOUVEAU hub : INDEX + SPEC + PLAN |
| `TECH_DOC/SESSIONS/OTP/` | NOUVEAU hub : INDEX + SPEC |
| `A TESTER et DOCUMENTER/event-wizards.md` | NOUVEAU — scénarios de test manuel |

### Migration

- **Migration nécessaire / Migration required:** Oui
- `BaseBillet/migrations/0XXX_event_is_proposal.py` (additive, default=False, aucune data migration)
```

### S6.3 — Lancer la batterie de tests complète

- [ ] **S6.3.1 — Tous les tests nouveaux**

```bash
docker exec lespass_django poetry run pytest \
  tests/pytest/test_otp_service.py \
  tests/pytest/test_otp_session.py \
  tests/pytest/test_event_is_proposal_field.py \
  tests/pytest/test_event_wizard_admin.py \
  tests/pytest/test_event_wizard_public.py \
  tests/pytest/test_event_proposal_admin.py \
  -v
```

Expected : ~57 passed.

- [ ] **S6.3.2 — Non-régression sur les tests existants liés aux events**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_event_*.py tests/pytest/test_events_*.py -q
```

Expected : aucune régression. Si un test échoue à cause de la suppression de `simple_create_event`, le marquer skip ou supprimer si caduque.

### S6.4 — Traductions (mainteneur)

- [ ] **S6.4.1 — Demander au mainteneur de lancer**

```
Le mainteneur exécute lui-même :
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
# Édition manuelle des .po pour remplir les msgstr
docker exec lespass_django poetry run django-admin compilemessages
```

### S6.5 — Préparer le commit S6

```
docs: add EVENT_WIZARD hub + CHANGELOG + manual test scenarios

- TECH_DOC/SESSIONS/EVENT_WIZARD/INDEX.md, SPEC.md, PLAN.md
- TECH_DOC/SESSIONS/OTP/INDEX.md, SPEC.md
- A TESTER et DOCUMENTER/event-wizards.md (6 manual test scenarios)
- CHANGELOG.md: new entry for event wizards + OTP service

Translations (makemessages + compilemessages) to be run manually
by maintainer.
```

---

## Self-review du plan

Coverage spec → tasks (vérifié inline avant publication) :
- SPEC §3 Architecture → S1, S2, S3, S4, S5 (fichiers créés/modifiés couverts)
- SPEC §4 Service OTP → S1.1 → S1.7
- SPEC §5 Wizard admin → S3.1 → S3.6
- SPEC §6 Wizard public → S4.1 → S4.6
- SPEC §7 Modèle is_proposal → S2.2
- SPEC §8 Modération admin → S5.1 → S5.5
- SPEC §9 Sécurité → couvert dans S1 (OTP hash, throttle) + S4 (honeypot, garde OTP)
- SPEC §10 Templates → S3.4, S4.4, S5.3
- SPEC §11 Tests pytest → S1.1, S1.5, S3.5, S4.5, S5.4
- SPEC §12 CHANGELOG → S6.2
- SPEC §13 A TESTER → S6.1

Pas de placeholder TBD. Toutes les signatures Python sont cohérentes entre tâches (`OtpSession(request, prefix)`, `start(email, libelle_action, nom_organisation=None)`, `verify(code) -> bool`, etc.).
