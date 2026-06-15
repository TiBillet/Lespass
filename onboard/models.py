"""
Modeles de l'app onboard.
/ Models for the onboard app.

LOCALISATION: onboard/models.py

Pour l'instant, un seul modele : OnboardInvitation, qui represente un
code d'invitation cree par un tenant existant pour parrainer un nouveau
lieu. Le brouillon de wizard lui-meme est porte par MetaBillet.WaitingConfiguration
(etendu, cf. Task 2 du plan onboard).
/ Single model for now: OnboardInvitation, an invitation code created
by an existing tenant to sponsor a new venue. The wizard draft itself
lives on MetaBillet.WaitingConfiguration (extended).
"""

import secrets
from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def _generate_invitation_code():
    """
    Genere un code d'invitation lisible (~8 caracteres alphanumeriques URL-safe).
    / Generate a readable invitation code (~8 URL-safe alphanumeric chars).
    """
    # secrets.token_urlsafe(6) produit ~8 caracteres URL-safe (base64url sans padding).
    # / secrets.token_urlsafe(6) yields ~8 URL-safe chars (base64url, no padding).
    return secrets.token_urlsafe(6)


def _default_expires_at():
    """
    Date d'expiration par defaut : 30 jours apres creation.
    / Default expiration date: 30 days after creation.
    """
    return timezone.now() + timedelta(days=30)


class OnboardInvitation(models.Model):
    """
    Code d'invitation cree par un tenant pour parrainer un nouveau lieu.
    Si le wizard est lance avec ce code (`?invite=<code>`), le nouveau
    tenant rejoint directement la federation indiquee (pas via pending).
    / Invitation code created by a tenant to sponsor a new venue.
    If the wizard starts with this code, the new tenant joins the
    federation directly (skips pending_tenants).
    """

    code = models.CharField(
        max_length=40, unique=True, db_index=True,
        default=_generate_invitation_code,
        verbose_name=_("Invitation code"),
    )

    # TODO : Ajouter la FK `federation` vers `fedow_core.Federation` quand l'app
    # fedow_core sera disponible sur cette branche (cf. fusion mono-repo V2).
    # Tant que fedow_core n'est pas dans SHARED_APPS, Django refuse cette FK
    # (fields.E300/E307). Le wizard fonctionnera sans le lien direct vers la
    # federation tant que ce champ est commente ; ajouter en migration separee.
    # / TODO: add `federation` FK to fedow_core.Federation once fedow_core is
    # available on this branch (cf. mono-repo V2 merge). Django refuses the FK
    # while fedow_core isn't in SHARED_APPS (fields.E300/E307). The wizard works
    # without the federation link until then; add via a separate migration.
    # federation = models.ForeignKey(
    #     "fedow_core.Federation",
    #     on_delete=models.CASCADE,
    #     related_name="onboard_invitations",
    #     verbose_name=_("Target federation"),
    # )

    invited_by_user = models.ForeignKey(
        "AuthBillet.TibilletUser",
        on_delete=models.CASCADE,
        related_name="onboard_invitations_sent",
        verbose_name=_("Invited by user"),
    )
    invited_by_tenant = models.ForeignKey(
        "Customers.Client",
        on_delete=models.CASCADE,
        related_name="onboard_invitations_sent",
        verbose_name=_("Invited by tenant"),
    )
    email_invited = models.EmailField(
        null=True, blank=True,
        verbose_name=_("Invited email (optional)"),
    )
    used_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Used at"),
    )
    expires_at = models.DateTimeField(
        default=_default_expires_at,
        verbose_name=_("Expires at"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Onboard invitation")
        verbose_name_plural = _("Onboard invitations")

    def is_valid(self):
        """
        Renvoie True si l'invitation n'est pas utilisee et pas expiree.
        / True if the invitation has not been used and has not expired.
        """
        if self.used_at is not None:
            return False
        if self.expires_at <= timezone.now():
            return False
        return True

    def __str__(self):
        # NOTE : on n'inclut pas encore le nom de la federation ; cf. TODO sur
        # le champ `federation` plus haut. / NOTE: federation name not yet
        # included; see TODO on `federation` field above.
        return f"Invitation {self.code}"
