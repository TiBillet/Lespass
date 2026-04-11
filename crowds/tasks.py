from __future__ import annotations

import logging
from typing import Iterable, List

from celery import shared_task
from django.db import connection
from django.utils.translation import gettext_lazy as _, activate
from django.utils import timezone
from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context

from BaseBillet.tasks import CeleryMailerClass
from BaseBillet.models import Configuration
from Customers.models import Client
from .models import Initiative, Participation, Contribution

logger = logging.getLogger(__name__)
User = get_user_model()



def _currency(initiative: Initiative) -> str:
    try:
        return initiative.asset.currency_code
    except Exception:
        return "EUR"


@shared_task
def email_participation_requested_admin(schema_name: str, initiative_uuid: str, participation_uuid: str) -> bool:
    """Notify the place admins that a participation has been requested (state requested).
    Uses tenant schema switching to render with the correct Configuration and URLs.
    """
    try:
        with schema_context(schema_name):
            # connection.tenant retourne un FakeTenant dans schema_context
            # (pas un vrai Client avec les M2M). On charge le vrai Client.
            # / connection.tenant returns a FakeTenant in schema_context
            # (not a real Client with M2M). We load the real Client.
            client: Client = Client.objects.get(schema_name=schema_name)
            config = Configuration.get_solo()
            activate(config.language)

            part = Participation.objects.select_related("initiative", "participant").get(pk=participation_uuid)
            init = part.initiative

            recipients = [user.email for user in client.user_admin.all()]
            if not recipients:
                logger.warning("crowds.email_participation_requested_admin: no recipients found")
                return False

            subject = f"{config.organisation} — " + _("Nouvelle participation demandée")
            context = {
                "title": subject,
                "organisation": config.organisation,
                "now": timezone.now(),
                "initiative": init,
                "participation": part,
                "participant_email": getattr(part.participant, "email", ""),
                "participant_name": getattr(part.participant, "get_full_name", lambda: "")() or getattr(part.participant, "first_name", "") or getattr(part.participant, "email", ""),
                "requested_amount_eur": (part.requested_amount_cents or 0) / 100,
                "currency": _currency(init),
            }
            sent_any = False
            for to in recipients:
                try:
                    mail = CeleryMailerClass(
                        to,
                        subject,
                        template="crowds/email/participation_requested_admin.html",
                        context=context,
                    )
                    mail.send()
                    sent_any = sent_any or bool(mail.sended)
                except Exception as e:
                    logger.error(f"crowds.email_participation_requested_admin: error sending to {to}: {e}")
            return sent_any
    except Exception as e:
        logger.exception(f"crowds.email_participation_requested_admin failed: {e}")
        return False


@shared_task
def email_contribution_paid_user(schema_name: str, contribution_uuid: str) -> bool:
    """
    FR: Envoie un email de confirmation de paiement au contributeur.
        Appelé après le retour Stripe ou le webhook quand le paiement est confirmé.
        Inclut l'image de l'initiative, le montant, et un lien vers la page du projet.
    EN: Sends a payment confirmation email to the contributor.

    LOCALISATION : crowds/tasks.py

    COMMUNICATION :
    - Appelé par : contribution_stripe_return (crowds/views.py) OU Webhook_stripe (ApiBillet/views.py)
    - Envoie : email via CeleryMailerClass → template crowds/email/contribution_paid_user.html
    - Protection double envoi : l'appelant vérifie que la contribution n'est pas déjà PAID
    """
    try:
        with schema_context(schema_name):
            config = Configuration.get_solo()
            activate(config.language)

            # FR: Récupérer le vrai Client pour obtenir le domaine.
            #     schema_context() crée un FakeTenant qui n'a pas get_primary_domain().
            # EN: Get the real Client object to access the domain.
            #     schema_context() creates a FakeTenant without get_primary_domain().
            client = Client.objects.filter(schema_name=schema_name).first()
            domain = client.get_primary_domain().domain if client else "tibillet.localhost"

            contrib = Contribution.objects.select_related(
                "initiative", "contributor",
            ).get(pk=contribution_uuid)
            initiative = contrib.initiative
            utilisateur = contrib.contributor

            # FR: Pas de destinataire → on ne peut pas envoyer
            # EN: No recipient → can't send
            if not utilisateur or not getattr(utilisateur, "email", None):
                logger.warning("crowds.email_contribution_paid_user: pas de destinataire")
                return False

            # FR: Logo du lieu (header de l'email)
            # EN: Place logo (email header)
            image_url = "https://tibillet.org/fr/img/design/logo-couleur.svg"
            try:
                if hasattr(config, "img") and hasattr(config.img, "med") and config.img.med:
                    image_url = f"https://{domain}{config.img.med.url}"
            except Exception:
                pass

            # FR: Image de l'initiative (affichée dans le corps de l'email)
            #     On utilise crop_hdr (960x540) pour un bon rendu email.
            #     Si l'initiative n'a pas d'image, on ne l'affiche pas.
            # EN: Initiative image (displayed in the email body)
            #     We use crop_hdr (960x540) for good email rendering.
            #     If the initiative has no image, we skip it.
            initiative_image_url = None
            try:
                img_field = initiative.get_img()
                if img_field and hasattr(img_field, "crop_hdr") and img_field.crop_hdr:
                    initiative_image_url = f"https://{domain}{img_field.crop_hdr.url}"
            except Exception:
                pass

            # FR: Nom affiché dans l'email.
            #     On prend le nom saisi dans le formulaire, ou le prénom/nom du compte.
            #     Si aucun nom réel n'existe, on laisse vide — le template affiche juste "Bonjour".
            # EN: Display name in email.
            #     Uses contributor_name from form, or first/last name from account.
            #     If no real name exists, left empty — template just shows "Bonjour".
            a_un_vrai_nom = utilisateur.first_name or utilisateur.last_name
            nom_utilisateur = contrib.contributor_name or ""
            if not nom_utilisateur and a_un_vrai_nom:
                nom_utilisateur = utilisateur.full_name()

            # FR: Montant en euros (la base est en centimes)
            # EN: Amount in euros (stored in cents)
            montant_euros = f"{(contrib.amount or 0) / 100:.2f}"
            devise = initiative.currency or "€"

            # FR: URL vers la page publique de l'initiative
            # EN: URL to the public initiative page
            initiative_url = f"https://{domain}/crowd/{initiative.pk}/"

            # FR: Textes FALC — simples et clairs
            # EN: FALC texts — simple and clear
            subject = f"{config.organisation} — " + str(_("Votre contribution est confirmée"))

            main_text = str(_(
                "Votre paiement a bien été reçu. "
                "Merci pour votre soutien !"
            ))

            main_text_2 = str(_(
                "Vous avez contribué au projet ci-dessous. "
                "Votre contribution aide à le faire avancer."
            ))

            context = {
                "username": nom_utilisateur,
                "now": timezone.now(),
                "title": subject,
                "image_url": image_url,
                "objet": str(_("Confirmation de paiement")),
                "sub_title": str(_("Contribution")),
                "main_text": main_text,
                "main_text_2": main_text_2,
                "initiative_name": initiative.name,
                "initiative_image_url": initiative_image_url,
                "table_info": {
                    str(_("Projet")): initiative.name,
                    str(_("Montant")): f"{montant_euros} {devise}",
                    str(_("Contributeur")): contrib.contributor_name or nom_utilisateur or utilisateur.email,
                },
                "button": {
                    "url": initiative_url,
                    "text": str(_("Voir le projet")),
                },
                "button_color": "#009058",
                "end_text": str(_("Merci pour votre contribution")),
                "signature": config.organisation,
            }

            mail = CeleryMailerClass(
                utilisateur.email,
                subject,
                template="crowds/email/contribution_paid_user.html",
                context=context,
            )
            mail.send()
            return bool(mail.sended)

    except Exception as e:
        logger.exception(f"crowds.email_contribution_paid_user failed: {e}")
        return False


@shared_task
def email_contribution_paid_admin(schema_name: str, initiative_uuid: str, contribution_uuid: str) -> bool:
    """Notify the place admins that a financial contribution has been marked as paid.
    Triggered when a Contribution transitions to paid/admin_paid.
    """
    try:
        with schema_context(schema_name):
            # Charger le vrai Client (pas FakeTenant) pour acceder aux M2M.
            # / Load the real Client (not FakeTenant) to access M2M.
            client: Client = Client.objects.get(schema_name=schema_name)

            config = Configuration.get_solo()
            activate(config.language)

            contrib = Contribution.objects.select_related("initiative", "contributor").get(pk=contribution_uuid)
            init = contrib.initiative

            recipients = [user.email for user in client.user_admin.all()]
            if not recipients:
                logger.warning("crowds.email_contribution_paid_admin: no recipients found")
                return False

            subject = f"{config.organisation} — " + _("Contribution payée")
            context = {
                "title": subject,
                "organisation": config.organisation,
                "now": timezone.now(),
                "initiative": init,
                "contribution": contrib,
                "contributor_name": contrib.contributor_name or getattr(contrib.contributor, "email", ""),
                "contributor_email": getattr(contrib.contributor, "email", ""),
                "amount_eur": (contrib.amount or 0) / 100,
                "currency": _currency(init),
                "paid_at": contrib.paid_at or timezone.now(),
                "payment_status": contrib.payment_status,
            }
            sent_any = False
            for to in recipients:
                try:
                    mail = CeleryMailerClass(
                        to,
                        subject,
                        template="crowds/email/contribution_paid_admin.html",
                        context=context,
                    )
                    mail.send()
                    sent_any = sent_any or bool(mail.sended)
                except Exception as e:
                    logger.error(f"crowds.email_contribution_paid_admin: error sending to {to}: {e}")
            return sent_any
    except Exception as e:
        logger.exception(f"crowds.email_contribution_paid_admin failed: {e}")
        return False
