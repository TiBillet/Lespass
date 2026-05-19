# OTP — Chantier 01 : service OTP DRY stateless + helper session HTTP

**Date :** 2026-05-19
**Statut :** Spec rédigée, en attente de revue (puis writing-plans)
**Premier consommateur :** [EVENT_WIZARD chantier 01](../EVENT_WIZARD/SPEC.md) (wizard public de proposition d'évènement)

## 1. Contexte

Le projet Lespass a déjà un mécanisme OTP fonctionnel dans `onboard/` (wizard d'onboarding nouveau tenant, déployé 2026-05-14). Ce mécanisme stocke les codes OTP directement dans le modèle `WaitingConfiguration` (schema `meta`) :
- champs `otp_hash`, `otp_expires_at`, `otp_attempts`, `last_otp_sent_at`, `email_confirmed`
- logique dans `onboard/services.py` (génération, envoi, vérification)
- templates email dans `onboard/templates/onboard/emails/otp_code.{html,txt}`

Cette implémentation est **liée au modèle `WaitingConfiguration`** — donc inutilisable telle quelle hors onboard. Or plusieurs cas d'usage émergent :
- Wizard public de proposition d'évènement (anonyme, schema tenant)
- Futur login OTP (utilisateur existant, schema tenant)
- Futur SSO / vérification email (utilisateur OIDC, schema tenant)

Le besoin : **un service OTP générique, stateless, où l'appelant choisit où stocker le hash et l'expiration** (session HTTP, modèle Django, cache Redis).

Onboard continue d'utiliser sa logique custom **inchangée** tant que ça fonctionne (FALC : on ne touche pas à ce qui marche). Un chantier futur pourra migrer onboard vers ce service (3 appels à remplacer) si cela apporte un bénéfice.

## 2. Décisions structurantes

| Sujet | Décision | Pourquoi |
|---|---|---|
| Service stateless | 4 fonctions pures, ne stocke rien | Permet usage en session / DB / cache au choix de l'appelant |
| Localisation | `AuthBillet/otp_service.py` + `AuthBillet/otp_session.py` | AuthBillet est SHARED_APPS — accessible depuis tout schéma |
| Hash | SHA-256 + `hmac.compare_digest` | Pas de code en clair, constant-time, anti-timing attack |
| Génération | `secrets.choice` sur chiffres 0-9 | Crypto-sûr, contrairement à `random` |
| Longueur code | 6 chiffres | Standard de fait (banques, Google, GitHub) |
| TTL | 10 minutes | Compromis confort / sécurité — alignement onboard |
| Max attempts | 5 | Limite anti-brute-force |
| Cooldown resend | 60 secondes | Évite le flood d'emails |
| Templates email | 1 couple `.html` / `.txt` paramétré par `libelle_action` | DRY — un seul template pour tous les usages |
| Helper session HTTP | Classe `OtpSession(request, prefix)` | Préfixe = cohabitation de plusieurs flows OTP simultanés dans la même session |
| Onboard | Inchangé tant que fonctionnel | Migration optionnelle dans un chantier futur |

## 3. Architecture

```
AuthBillet/
├── otp_service.py                          # NOUVEAU — service stateless (4 fonctions pures + constantes)
├── otp_session.py                          # NOUVEAU — helper classe OtpSession pour session HTTP
└── templates/auth/emails/
    ├── otp_code.html                       # NOUVEAU — template HTML générique
    └── otp_code.txt                        # NOUVEAU — template texte (fallback mail client)

tests/pytest/
├── test_otp_service.py                     # ~10 tests unitaires (pas de DB nécessaire)
└── test_otp_session.py                     # ~12 tests session HTTP
```

Aucune migration de modèle. Aucun signal. Aucune dépendance ajoutée (`secrets`, `hashlib`, `hmac` sont stdlib).

## 4. API publique

### 4.1 `AuthBillet/otp_service.py` — service stateless

```python
"""
Service OTP stateless reutilisable.
/ Stateless reusable OTP service.

LOCALISATION : AuthBillet/otp_service.py

Genere, hashe, verifie et envoie un code OTP a 6 chiffres.
Ne stocke RIEN — l'appelant choisit ou poser le hash et l'expiration
(session HTTP, modele DB, cache Redis...).

Usages prevus :
  - Wizard public de proposition d'evenement (session HTTP)
  - Futur login OTP (modele User ou cache)
  - Futur SSO/OIDC (verification email)
  - Migration onboard (remplacement de la logique WaitingConfiguration)

/ Generates, hashes, verifies and sends a 6-digit OTP code.
Stores NOTHING — the caller decides where to put the hash and expiry.
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
    :param code_otp: code clair a inclure dans le mail / cleartext code to include
    :param libelle_action: ex "Proposer un evenement", "Connexion" — affiche
                           dans le sujet et le corps du mail
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

### 4.2 `AuthBillet/otp_session.py` — helper session HTTP

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

    Usage minimal :
        otp = OtpSession(request, prefix="event_proposal")
        otp.start("user@example.com", libelle_action="Proposer un evenement")
        otp.verify("123456")    # -> True / False
        otp.is_confirmed()      # -> True apres verify reussi
        otp.email()             # -> email confirme
        otp.can_resend()        # -> True si cooldown ecoule
        otp.reset()             # -> efface toutes les cles du prefixe
    """

    def __init__(self, request, prefix: str):
        self.request = request
        self.prefix = prefix

    def _k(self, suffix: str) -> str:
        # Construit la cle session : "<prefix>_otp_<suffix>".
        # / Builds the session key.
        return f"{self.prefix}_otp_{suffix}"

    def start(
        self,
        email: str,
        libelle_action: str,
        nom_organisation: str = None,
    ) -> None:
        """
        Genere un code, le stocke (hash) en session, et l'envoie par mail.
        / Generates a code, stores hash in session, sends email.
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
        Verifie le code. Incremente le compteur de tentatives.
        / Verifies the code. Increments attempts counter.
        Retourne False si pas de hash en session, max attempts atteint,
        code expire, ou code incorrect.
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
        """Nombre de tentatives restantes avant blocage.
        / Remaining attempts before lockout."""
        attempts = self.request.session.get(self._k("attempts"), 0)
        return max(0, OTP_MAX_ATTEMPTS - attempts)

    def can_resend(self) -> bool:
        """True si le cooldown est ecoule depuis le dernier envoi.
        / True if the resend cooldown has elapsed."""
        last_sent_iso = self.request.session.get(self._k("last_sent_at"))
        if not last_sent_iso:
            return True
        delta = timezone.now() - datetime.fromisoformat(last_sent_iso)
        return delta.total_seconds() >= OTP_RESEND_COOLDOWN_SECONDS

    def seconds_before_resend(self) -> int:
        """Combien de secondes avant de pouvoir resend.
        / How many seconds before resend is allowed."""
        last_sent_iso = self.request.session.get(self._k("last_sent_at"))
        if not last_sent_iso:
            return 0
        delta = timezone.now() - datetime.fromisoformat(last_sent_iso)
        return max(0, int(OTP_RESEND_COOLDOWN_SECONDS - delta.total_seconds()))

    def reset(self) -> None:
        """Efface toutes les cles OTP du prefixe.
        / Wipes all OTP keys for this prefix."""
        for suffix in (
            "email", "hash", "expires_at", "attempts",
            "last_sent_at", "confirmed",
        ):
            self.request.session.pop(self._k(suffix), None)
```

## 5. Templates email

### 5.1 `AuthBillet/templates/auth/emails/otp_code.txt`

```
{{ libelle_action }}

Votre code de verification : {{ code }}

Ce code est valable {{ expires_minutes }} minutes.

Si vous n'avez pas demande ce code, ignorez ce message.

{% if nom_organisation %}--
{{ nom_organisation }}{% endif %}
```

### 5.2 `AuthBillet/templates/auth/emails/otp_code.html`

Template HTML simple, inline styles uniquement (cohérent avec les clients email). Mise en page : titre `libelle_action`, gros bloc `code` en monospace, paragraphe explicatif, footer `nom_organisation` si fourni. Pas de tracking, pas d'images, pas de liens (un OTP ne contient AUCUN lien cliquable — principe de sécurité).

Variables : `{{ code }}`, `{{ expires_minutes }}`, `{{ libelle_action }}`, `{{ nom_organisation }}`.

## 6. Cas d'usage — patterns d'utilisation

### 6.1 Session HTTP (cas wizard event public)

```python
# Generation + envoi
otp = OtpSession(request, prefix="event_proposal")
otp.start(
    email="user@example.com",
    libelle_action=str(_("Proposer un evenement")),
    nom_organisation=Configuration.get_solo().organisation,
)

# Verification (vue de saisie du code)
if otp.verify(request.POST.get("otp", "")):
    return redirect("event-propose-place")

# Garde au debut des vues post-OTP
if not otp.is_confirmed():
    return redirect("event-propose-email")

# Resend
if not otp.can_resend():
    messages.error(request, _("Patientez %(s)s secondes.") % {"s": otp.seconds_before_resend()})
    return redirect("event-propose-verify")
otp.start(otp.email(), libelle_action=...)
```

### 6.2 Modèle Django (cas futur login OTP — illustratif)

Le service stateless est utilisable directement sans `OtpSession` quand on veut stocker dans la base. Exemple pour un futur login OTP :

```python
from AuthBillet.otp_service import (
    generer_code_otp, hash_code_otp, verifier_code_otp,
    envoyer_email_otp, OTP_TTL_SECONDS,
)

# Vue "demande code"
code = generer_code_otp()
user.login_otp_hash = hash_code_otp(code)
user.login_otp_expires_at = timezone.now() + timedelta(seconds=OTP_TTL_SECONDS)
user.login_otp_attempts = 0
user.save(update_fields=["login_otp_hash", "login_otp_expires_at", "login_otp_attempts"])
envoyer_email_otp(user.email, code, libelle_action=str(_("Connexion")))

# Vue "verification code"
if user.login_otp_attempts >= OTP_MAX_ATTEMPTS:
    raise PermissionDenied
if timezone.now() > user.login_otp_expires_at:
    raise PermissionDenied
user.login_otp_attempts += 1
if verifier_code_otp(submitted_code, user.login_otp_hash):
    user.login_otp_hash = ""  # invalide le code apres usage
    user.save()
    login(request, user)
```

Note : pour le login, ajouter les champs sur le modèle `User` (ou créer un modèle `LoginOtp` lié) est une décision du chantier login. Le service ne l'impose pas.

### 6.3 Cache Redis (cas futur SSO — illustratif)

```python
# Genere + stocke en cache (TTL natif Redis)
code = generer_code_otp()
cache.set(f"sso_otp:{user.uuid}", {
    "hash": hash_code_otp(code),
    "attempts": 0,
}, timeout=OTP_TTL_SECONDS)
envoyer_email_otp(user.email, code, libelle_action=_("Verification SSO"))

# Verify
entry = cache.get(f"sso_otp:{user.uuid}")
if not entry or entry["attempts"] >= OTP_MAX_ATTEMPTS:
    raise PermissionDenied
entry["attempts"] += 1
cache.set(f"sso_otp:{user.uuid}", entry, timeout=OTP_TTL_SECONDS)
if verifier_code_otp(submitted, entry["hash"]):
    cache.delete(f"sso_otp:{user.uuid}")
    # ... emettre token SSO
```

## 7. Sécurité

| Risque | Mitigation |
|---|---|
| Stockage code en clair | Hash SHA-256 systématique — jamais persisté en clair |
| Timing attack sur la comparaison | `hmac.compare_digest` (constant-time) |
| Génération non crypto-sûre | `secrets.choice` (PEP 506) plutôt que `random` |
| Brute-force du code (6 chiffres = 10^6) | Max 5 tentatives — empêche d'épuiser l'espace |
| Replay du code après usage | À la charge de l'appelant : invalider le hash après `verify` réussi (le helper `OtpSession` ne le fait pas par défaut car le code peut être réutilisé pendant la session) |
| Flood d'emails | Cooldown 60s entre deux `start()` + throttling DRF à l'appelant |
| Liens cliquables dans l'email | **Aucun lien dans le template OTP** — règle stricte pour ne pas fingerprint le code |
| Fuite via logs Django | `envoyer_email_otp` n'utilise pas `logger.info(code)` — vérifier au code review |
| Tracking pixel email | Aucune image externe dans le template HTML |

## 8. Tests pytest

### 8.1 `tests/pytest/test_otp_service.py` (~10 tests, ~1s)

Tests **unitaires purs** — pas de DB, pas de tenant.

```python
class TestGenererCodeOtp:
    def test_a_6_chiffres_exactement(self): ...
    def test_uniquement_des_chiffres(self): ...
    def test_aleatoire_sur_100_echantillons(self):
        # >= 95 codes uniques sur 100 generations
        ...

class TestHashCodeOtp:
    def test_deterministe(self):
        # Meme code -> meme hash
        ...
    def test_hash_different_du_code(self): ...
    def test_longueur_64_caracteres_hex(self):
        # SHA-256 hex = 64 chars
        ...

class TestVerifierCodeOtp:
    def test_succes_avec_bon_code(self): ...
    def test_echec_avec_mauvais_code(self): ...
    def test_echec_avec_code_vide(self): ...
    def test_echec_avec_hash_vide(self): ...

class TestEnvoyerEmailOtp:
    def test_appelle_send_mail_avec_destinataire(self, mocker): ...
    def test_inclut_le_code_dans_le_corps(self, mocker): ...
    def test_sujet_contient_libelle_action(self, mocker): ...
    def test_footer_contient_nom_organisation_si_fourni(self, mocker): ...
```

### 8.2 `tests/pytest/test_otp_session.py` (~12 tests, ~2s)

`RequestFactory` + `SessionMiddleware` pour simuler une session HTTP. Mock de `envoyer_email_otp` pour ne pas envoyer de vrais mails.

```python
class TestOtpSessionStart:
    def test_pose_les_cles_en_session(self): ...
    def test_envoie_email_avec_libelle_action(self, mocker): ...
    def test_initialise_attempts_a_zero(self): ...

class TestOtpSessionVerify:
    def test_code_correct_marque_confirmed(self): ...
    def test_code_incorrect_retourne_false_et_increment_attempts(self): ...
    def test_apres_max_attempts_retourne_false_meme_si_code_correct(self): ...
    def test_apres_expiration_retourne_false(self, freezer): ...
    def test_sans_session_prealable_retourne_false(self): ...

class TestOtpSessionState:
    def test_is_confirmed_initialement_false(self): ...
    def test_email_retourne_chaine_vide_si_pas_start(self): ...
    def test_attempts_remaining_decroit_a_chaque_verify(self): ...

class TestOtpSessionResend:
    def test_can_resend_true_apres_cooldown(self, freezer): ...
    def test_can_resend_false_avant_cooldown(self): ...
    def test_seconds_before_resend_decroit_dans_le_temps(self, freezer): ...

class TestOtpSessionReset:
    def test_efface_toutes_les_cles_du_prefixe(self): ...
    def test_ne_touche_pas_aux_cles_d_autres_prefixes(self):
        # Garantit la cohabitation de plusieurs flows OTP
        ...
```

### 8.3 Pièges connus (cf. `tests/PIEGES.md`)

- **Mock email** : intercepter `AuthBillet.otp_service.envoyer_email_otp` directement (pas `django.core.mail.send_mail`) — cible plus précise.
- **Test d'expiration** : utiliser `freezegun` (déjà dispo dans pyproject) ou `monkeypatch` sur `django.utils.timezone.now`. Importer `timezone` localement dans le module à patcher pour que le mock soit pris.
- **Variables locales** : ne JAMAIS utiliser `_` comme variable car cela écraserait `gettext._`. Toujours `_unused`, `_created`, etc.
- **Session HTTP dans pytest-django** : `client.session` puis assigner les clés directement et appeler `.save()`. Le `Session` instance retourné est lazy.

### 8.4 Couverture cible

- `AuthBillet/otp_service.py` : **100%**
- `AuthBillet/otp_session.py` : **100%**

## 9. Migration / interopérabilité

### 9.1 Onboard (statu quo)

Onboard continue d'utiliser sa logique custom (`onboard/services.py` + champs `WaitingConfiguration.otp_*` + templates `onboard/templates/onboard/emails/otp_code.{html,txt}`). Aucune modification.

### 9.2 Onboard (migration future, hors scope)

Pour migrer onboard quand quelqu'un voudra le faire :
1. Remplacer `onboard.services.generate_otp_for_wc(wc)` par 3 appels au service :
   ```python
   from AuthBillet.otp_service import generer_code_otp, hash_code_otp, envoyer_email_otp, OTP_TTL_SECONDS
   code = generer_code_otp()
   wc.otp_hash = hash_code_otp(code)
   wc.otp_expires_at = timezone.now() + timedelta(seconds=OTP_TTL_SECONDS)
   wc.save(update_fields=["otp_hash", "otp_expires_at"])
   envoyer_email_otp(wc.email, code, libelle_action=str(_("Creer votre espace TiBillet")))
   ```
2. Supprimer `onboard.services.verify_otp_for_wc(wc, code)` au profit de `verifier_code_otp(code, wc.otp_hash)`.
3. Supprimer les templates onboard email OTP (redondants avec ceux d'AuthBillet).

Aucun changement de schéma DB nécessaire — les champs `WaitingConfiguration.otp_*` restent identiques.

### 9.3 Coexistence

Les préfixes session OtpSession garantissent que plusieurs flows OTP peuvent cohabiter sans interférence :
- `event_proposal_otp_*` (wizard public event)
- `login_otp_*` (futur login)
- etc.

Onboard ne touche pas à la session HTTP (il vit dans `meta` avec `WaitingConfiguration`), donc aucun conflit.

## 10. Hors scope du chantier 01

| Item | Raison |
|---|---|
| Migration onboard | Pas urgente, onboard fonctionne. Chantier futur (CHANTIER-03 du hub). |
| Login OTP | Feature distincte, chantier dédié (CHANTIER-02 du hub) — utilisera le service. |
| TOTP (RFC 6238 / Google Authenticator) | Extension future si besoin 2FA app — chantier dédié (CHANTIER-05). |
| Branchement SSO/OIDC | Feature distincte (CHANTIER-04). |
| Tests E2E Playwright sur les flows OTP | Reporté — les tests unitaires + d'intégration suffisent pour ce service générique. Les consommateurs (wizard event) auront leurs propres tests E2E. |
| Internationalisation des templates email au-delà du `libelle_action` | Le service est neutre, la traduction se fait par l'appelant qui passe `libelle_action=str(_("..."))`. Les templates `auth/emails/otp_code.{html,txt}` utilisent `{% translate %}` Django pour le texte fixe. |

## 11. Documentation / suivi

- `A TESTER et DOCUMENTER/otp-service.md` : scénarios de test manuel
  1. Envoi mail réel via SMTP de dev (vérifier corps + sujet)
  2. Cohabitation 2 flows dans la même session (préfixes différents)
  3. Expiration code après 10 minutes
  4. Verrouillage après 5 tentatives
  5. Cooldown resend 60s
- `CHANGELOG.md` : entrée à ajouter (cf. EVENT_WIZARD/SPEC.md section 12)

## 12. Références

- [OWASP — OTP Best Practices](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
- [PEP 506 — `secrets` module](https://peps.python.org/pep-0506/)
- [`hmac.compare_digest` — Python docs](https://docs.python.org/3/library/hmac.html#hmac.compare_digest)
- Pattern existant Lespass : `onboard/services.py` (à migrer dans le futur)
- Premier consommateur : [EVENT_WIZARD/SPEC.md](../EVENT_WIZARD/SPEC.md) section 6 (wizard public)
