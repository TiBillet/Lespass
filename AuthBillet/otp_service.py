"""
Service OTP stateless reutilisable.
/ Stateless reusable OTP service.

LOCALISATION : AuthBillet/otp_service.py

Genere, hashe, verifie et envoie un code OTP à 6 chiffres.
Ne stocke RIEN — l'appelant choisit ou poser le hash et l'expiration
(session HTTP, modele DB, cache Redis...).

Voir TECH_DOC/SESSIONS/OTP/SPEC.md pour la spec complete.
/ See TECH_DOC/SESSIONS/OTP/SPEC.md for the full spec.
"""

import hmac
import secrets
from typing import Optional

from django.template.loader import render_to_string
from django.utils.crypto import salted_hmac
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
    return "".join(secrets.choice("0123456789") for _unused in range(OTP_LENGTH))


def hash_code_otp(code: str) -> str:
    """
    Empreinte d'un code OTP. On garde l'empreinte, jamais le code en clair.
    / Fingerprint of an OTP code. Never store cleartext.

    L'empreinte est un HMAC-SHA256 avec la cle secrete du projet (SECRET_KEY).
    Un SHA-256 simple ne suffit pas : il n'y a qu'un million de codes possibles.
    Avec une copie du cache, on les essaierait tous en une seconde.
    Sans la cle secrete, c'est impossible.
    / HMAC-SHA256 keyed with SECRET_KEY: a plain SHA-256 of a 6-digit code
    is brute-forced instantly from a cache dump.

    Resultat : 64 caracteres hexadecimaux. / Result: 64 hex characters.
    """
    return salted_hmac("AuthBillet.otp", code, algorithm="sha256").hexdigest()


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
) -> Optional[bool]:
    """
    Envoie l'email OTP via le pattern projet `CeleryMailerClass`.
    / Sends the OTP email via the project-wide `CeleryMailerClass` pattern.

    Renvoie `mail.sended` : True si le serveur mail a accepte le message,
    None sinon. L'appelant journalise l'echec.
    / Returns `mail.sended`: True if the mail server accepted it, None otherwise.

    On reutilise `BaseBillet.tasks.CeleryMailerClass` plutot que `send_mail`
    direct pour beneficier (DRY) :
      - du fallback `DEFAULT_FROM_EMAIL` -> `EMAIL_HOST_USER`,
      - du header `List-Unsubscribe`,
      - du check `config_valid()` (EMAIL_HOST, EMAIL_PORT, return_email...),
      - de la cohabitation avec les autres envois du projet (logs unifies).

    Import local : `BaseBillet.tasks` charge Stripe / Fedow / Brevo / Ghost
    au module load. On evite d'embarquer ces deps a l'import du service OTP
    (utilise dans des contextes "legers" comme un futur login OTP).
    / Local import: avoid pulling Stripe/Fedow/Brevo/Ghost at OTP service
    load time. Same pattern as onboard/tasks.py.

    :param email_destinataire: email du destinataire / recipient email
    :param code_otp: code clair a inclure dans le mail / cleartext code
    :param libelle_action: ex "Proposer un evenement", "Connexion"
    :param nom_organisation: nom du lieu/tenant (footer mail, optionnel)
    """
    # Import local — cf. docstring ci-dessus.
    # / Local import — see docstring above.
    from BaseBillet.tasks import CeleryMailerClass

    contexte_email = {
        "code": code_otp,
        "expires_minutes": OTP_TTL_SECONDS // 60,
        "libelle_action": libelle_action,
        "nom_organisation": nom_organisation or "",
    }
    # Sujet : code en TETE pour que la notification mobile (souvent
    # tronquee apres ~30 caracteres) reste utile — le destinataire lit le
    # code sans avoir a ouvrir le mail. Pattern aligne sur onboard.
    # / Subject: code FIRST so the mobile notification (often truncated)
    # stays useful — user reads code without opening the email.
    sujet = _("%(code)s – votre code de vérification (%(action)s)") % {
        "code": code_otp,
        "action": libelle_action,
    }
    # Pre-render du texte brut. Le HTML est rendu par `CeleryMailerClass`
    # via le couple `template` + `context`.
    # / Pre-render plain text body. HTML rendered by CeleryMailerClass.
    corps_texte = render_to_string("auth/emails/otp_code.txt", contexte_email)

    mail = CeleryMailerClass(
        email=email_destinataire,
        title=sujet,
        text=corps_texte,
        template="auth/emails/otp_code.html",
        context=contexte_email,
    )
    mail.send()
    return mail.sended
