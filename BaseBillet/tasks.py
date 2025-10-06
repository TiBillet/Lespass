# import base64
import datetime
import json
import logging
import os
import smtplib
import time
from io import BytesIO
from time import sleep
from uuid import UUID

import jwt
import requests
import segno
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.contrib.auth import get_user_model
# from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.core.serializers.json import DjangoJSONEncoder
from django.core.signing import TimestampSigner
from django.db import connection
from django.template.loader import render_to_string, get_template
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.formats import date_format
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import get_tenant_model, tenant_context
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

from ApiBillet.serializers import LigneArticleSerializer, MembershipSerializer
from AuthBillet.models import TibilletUser
from BaseBillet.models import Reservation, Ticket, Configuration, Membership, Webhook, LigneArticle, \
    GhostConfig, BrevoConfig, Product, Price
from MetaBillet.models import WaitingConfiguration
from TiBillet.celery import app
from fedow_connect.fedow_api import FedowAPI
from fedow_connect.utils import dround

logger = logging.getLogger(__name__)


def encode_uid(pk):
    return force_str(urlsafe_base64_encode(force_bytes(pk)))


def decode_uid(pk):
    return force_str(urlsafe_base64_decode(pk))


class CeleryMailerClass():

    def __init__(self,
                 email: str or list,
                 title: str,
                 text=None,
                 html=None,
                 template=None,
                 context=None,
                 attached_files=None,
                 ):

        self.title = title
        self.email = email
        self.text = text
        self.html = html
        self.context = context
        self.attached_files = attached_files
        self.sended = None
        self.return_email = os.environ.get('DEFAULT_FROM_EMAIL', os.environ['EMAIL_HOST_USER'])
        if template and context:
            self.html = render_to_string(template, context=context)
        else:
            self.html = self.text

    def config_valid(self):
        EMAIL_HOST = os.environ.get('EMAIL_HOST')
        EMAIL_PORT = os.environ.get('EMAIL_PORT')

        # Adresse d'envoi peut/doit être différente du login du serveur mail.
        # Error si ni DEFAULT ni HOST

        if all([
            EMAIL_HOST,
            EMAIL_PORT,
            # Not required for local server
            # EMAIL_HOST_USER,
            # EMAIL_HOST_PASSWORD,
            self.return_email,  # return email
            self.title,
            self.email,
        ]):
            return True
        else:
            return False

    def send(self):
        # logger.info("SELF.HTML : ",self.html)
        # import ipdb; ipdb.set_trace()

        if self.html and self.config_valid():
            to = self.email if type(self.email) is list else [self.email, ]

            logger.info(f'  WORKDER CELERY : send_mail - {self.title}')
            mail = EmailMultiAlternatives(
                self.title,
                self.text,
                self.return_email,
                to,
                headers={"List-Unsubscribe": f"<mailto: {self.return_email}?subject=unsubscribe>"},
            )
            mail.attach_alternative(self.html, "text/html")

            if self.attached_files:
                for filename, file in self.attached_files.items():
                    mail.attach(filename, file, 'application/pdf')

            mail_return = mail.send(fail_silently=False)

            if mail_return == 1:
                self.sended = True
                # logger.info(f'      WORKER CELERY mail envoyé : {mail_return} - {self.email}')
                # logger.info(f'          title : {self.title}')
                # logger.info(f'          text : {self.text}')
                # logger.info(f'          html len : {len(str(self.html))}')
                # logger.info(f'          return_email : {self.return_email}')
            else:
                logger.error(f'     WORKER CELERY mail non envoyé : {mail_return} - {self.email}')

            return mail_return
        else:
            logger.error(f'Pas de contenu HTML ou de configuration email valide')
            raise ValueError('Pas de contenu HTML ou de configuration email valide')


def report_to_pdf(report):
    template_name = 'report/ticketz.html'
    font_config = FontConfiguration()
    template = get_template(template_name)
    html = template.render(report)
    pdf_binary = HTML(string=html).write_pdf(
        font_config=font_config,
    )
    logger.info(f"  WORKER CELERY : report_to_pdf - {report.get('organisation')} {report.get('date')} bytes")
    return pdf_binary


def create_membership_invoice_pdf(membership: Membership):
    config = Configuration.get_solo()
    activate(config.language)
    template_name = 'invoice/invoice.html'
    font_config = FontConfiguration()
    template = get_template(template_name)

    user = membership.user

    # Determine recipient email safely; membership may be anonymous (no linked user)
    email = None
    try:
        email = getattr(user, 'email', None)
    except Exception:
        email = None
    # As a last resort, leave empty string to avoid AttributeError downstream
    if not email:
        email = ''

    context = {
        'config': config,
        'paiement': membership.stripe_paiement.first(),
        'membership': membership,
        'email': email,
    }

    html = template.render(context)
    css = CSS(string=
              '''
                @font-face {
                  font-family: BeStrong;
                  src: url(file:///DjangoFiles/BaseBillet/static/polices/Playwrite_IS/PlaywriteIS-VariableFont_wght.ttf);
                }
                @font-face {
                  font-family: Libre Barcode;
                  src: url(file:///DjangoFiles/ApiBillet/templates/ticket/librebarcode128-regular.ttf);
                }
                @font-face {
                  font-family: Barlow Condensed;
                  src: url(file:///DjangoFiles/ApiBillet/templates/ticket/barlowcondensed-regular.otf)
                }
                @font-face {
                  font-family: Barlow Condensed;
                  font-weight: 300;
                  src: url(file:///DjangoFiles/ApiBillet/templates/ticket/barlowcondensed-light.otf);
                }
                @font-face {
                  font-family: Barlow Condensed;
                  font-weight: 700;
                  src: url(file:///DjangoFiles/ApiBillet/templates/ticket/barlowcondensed-bold.otf);
                }
              ''',
              font_config=font_config)

    pdf_binary = HTML(string=html).write_pdf(
        stylesheets=[css],
        font_config=font_config,
    )

    return pdf_binary


def context_for_membership_email(membership: "Membership"):
    config = Configuration.get_solo()
    activate(config.language)
    domain = connection.tenant.get_primary_domain().domain
    image_url = "https://tibillet.org/fr/img/design/logo-couleur.svg"
    if hasattr(config.img, 'med'):
        image_url = f"https://{domain}{config.img.med.url}"

    additionnal_text_3 = None
    if membership.price.fedow_reward_enabled:
        if membership.price.fedow_reward_amount > 0 and membership.price.fedow_reward_asset :
            additionnal_text_3 = _("Your membership entitles you to ") + f"{dround(membership.price.fedow_reward_amount)} {membership.price.fedow_reward_asset.name.upper()} " + _("credited to your TiBillet wallet. You can check your balance in the ‘My Account’ section.")

    membership.refresh_from_db()
    context = {
        'username': membership.member_name(),
        'now': timezone.now(),
        'title': f"{config.organisation} : {membership.price.product.name}",
        'image_url': image_url,
        'objet': _("Confirmation email"),
        'sub_title': _("Welcome aboard !"),
        'main_text': _("Your payment for ") + f"{membership.price.product.name}" + _(" has been received."),
        'main_text_2': config.additional_text_in_membership_mail,
        'main_text_3': additionnal_text_3,
        'table_info': {
            _('Receipt for:'): f'{membership.member_name()}',
            _('Product'): f'{membership.price.product.name} - {membership.price.name}',
            _('Contribution'): f'{membership.contribution_value} {config.currency_code}',
            _('Date'): date_format(membership.last_contribution, format='DATE_FORMAT', use_l10n=True),
            _('Valid until'): date_format(membership.get_deadline(), format='DATE_FORMAT', use_l10n=True),
        },
        'button_color': "#009058",
        'button': {
            'text': _('REQUEST RECEIPT'),
            'url': f'https://{domain}/memberships/{membership.pk}/invoice/',
        },
        'next_text_1': _("If you receive this email by mistake, please contact the TiBillet team."),
        # 'next_text_2': "next_text_2",
        'end_text': _('See you soon!'),
        'signature': _("Marvin, the TiBillet robot"),
    }

    if membership.price.recurring_payment:
        context['table_info'][_('Recurring payment')] = _("Yes")
        context['table_info'][_('Next payment withdrawal')] = date_format(membership.get_deadline(), format='DATE_FORMAT', use_l10n=True)

    # Ajout des options str si il y en a :
    if membership.option_generale.count() > 0:
        context['table_info']['Options'] = f"{membership.options()}"
    return context


@app.task
def send_membership_invoice_to_email(membership_uuid: str):
    time.sleep(1)  # pour donner le tps de récupérer l'objet

    # Retry mechanism for getting membership
    attempts = 0
    max_attempts = 10
    wait_time = 2  # seconds

    while attempts < max_attempts:
        try:
            membership = Membership.objects.get(uuid=membership_uuid)
            user = membership.user
            # Mails de confirmation qui contient un lien vers la facture :
            logger.info(f"    update_membership_state_after_paiement : Envoi de la confirmation par email")
            send_email_generique(
                context=context_for_membership_email(membership),
                email=f"{user.email}",
            )
            logger.info(f"    update_membership_state_after_paiement : Envoi de la confirmation par email DELAY")
            return True
        except Membership.DoesNotExist:
            attempts += 1
            if attempts >= max_attempts:
                logger.error(f"Membership with uuid {membership_uuid} not found after {max_attempts} attempts")
                raise Exception(f"Membership with uuid {membership_uuid} not found after {max_attempts} attempts")
            logger.warning(
                f"Membership with uuid {membership_uuid} not found, retrying in {wait_time} seconds (attempt {attempts}/{max_attempts})")
            time.sleep(wait_time)

    # This should never be reached due to the exception in the loop
    return False


@app.task
def send_membership_pending_admin(membership_uuid: str):
    """Envoie un mail aux administrateurs du tenant pour prévenir d'une demande d'adhésion à valider."""
    # Attendre un peu que l'objet soit disponible en DB
    time.sleep(1)

    attempts, max_attempts, wait_time = 0, 10, 2
    while attempts < max_attempts:
        try:
            membership = Membership.objects.get(uuid=membership_uuid)
            break
        except Membership.DoesNotExist:
            attempts += 1
            if attempts >= max_attempts:
                logger.error(f"send_membership_pending_admin: membership {membership_uuid} introuvable")
                return False
            time.sleep(wait_time)

    config = Configuration.get_solo()
    activate(config.language)

    tenant = connection.tenant
    domain = tenant.get_primary_domain().domain

    # Récupération des emails des admins du tenant
    try:
        admin_emails = list(TibilletUser.objects.filter(client_admin=tenant).values_list('email', flat=True))
    except Exception:
        admin_emails = []
    if not admin_emails and getattr(config, 'email', None):
        admin_emails = [config.email]

    image_url = "https://tibillet.org/fr/img/design/logo-couleur.svg"
    try:
        if hasattr(config, 'img') and hasattr(config.img, 'med') and config.img.med:
            image_url = f"https://{domain}{config.img.med.url}"
    except Exception:
        pass

    title = _(f"{config.organisation} : Nouvelle demande d'adhésion en attente")

    context = {
        'username': _("Administrateur"),
        'now': timezone.now(),
        'title': title,
        'image_url': image_url,
        'sub_title': _("Administration"),
        'main_text': _("Une nouvelle demande d'adhésion est en attente de validation manuelle."),
        'main_text_2': f"{membership.member_name()} — {membership.price.product.name} — {membership.price.name}",
        'table_info': {
            _('Adhérent'): f'{membership.member_name()}',
            _('Produit'): f'{membership.price.product.name} - {membership.price.name}',
            _('Email'): f"{membership.user.email if membership.user else ''}",
            _('Date de demande'): date_format(membership.date_added, format='DATETIME_FORMAT', use_l10n=True),
        },
        'button_color': "#009058",
        'button': {
            'text': _("Ouvrir l’administration"),
            'url': f'https://{domain}/admin/BaseBillet/membership/'
        },
        'end_text': _('Merci'),
        'signature': _("Marvin, le TiBillet robot"),
    }

    try:
        if admin_emails:
            send_email_generique(context=context, email=admin_emails)
            logger.info("send_membership_pending_admin: mail envoyé")
            return True
        else:
            logger.warning("send_membership_pending_admin: aucun email admin trouvé")
            return False
    except Exception as e:
        logger.error(f"send_membership_pending_admin: erreur d'envoi {e}")
        return False


@app.task
def send_membership_pending_user(membership_uuid: str):
    """Envoie un mail à l'utilisateur pour lui indiquer que sa demande est en attente de validation manuelle."""
    time.sleep(1)
    attempts, max_attempts, wait_time = 0, 10, 2
    while attempts < max_attempts:
        try:
            membership = Membership.objects.get(uuid=membership_uuid)
            break
        except Membership.DoesNotExist:
            attempts += 1
            if attempts >= max_attempts:
                logger.error(f"send_membership_pending_user: membership {membership_uuid} introuvable")
                return False
            time.sleep(wait_time)

    config = Configuration.get_solo()
    activate(config.language)
    tenant = connection.tenant
    domain = tenant.get_primary_domain().domain

    user = membership.user
    if not user or not getattr(user, 'email', None):
        logger.warning("send_membership_pending_user: aucun destinataire")
        return False

    image_url = "https://tibillet.org/fr/img/design/logo-couleur.svg"
    try:
        if hasattr(config, 'img') and hasattr(config.img, 'med') and config.img.med:
            image_url = f"https://{domain}{config.img.med.url}"
    except Exception:
        pass

    title = _(f"{config.organisation} : Votre demande d'adhésion est en attente")

    # Texte principal
    main_text = _("Votre demande d'adhésion a bien été enregistrée.") + " " + \
                _("Elle est maintenant en attente de validation manuelle par un administrateur.")

    # Texte additionnel si prix > 0
    main_text_2 = None
    try:
        if membership.price and membership.price.prix and membership.price.prix > 0:
            main_text_2 = _("Dès validation, un lien de paiement vous sera envoyé par email.")
    except Exception:
        pass

    # Bouton de validation d'email si nécessaire
    button = None
    try:
        if hasattr(user, 'email_valid') and not user.email_valid:
            button = {
                'text': _("Valider mon email"),
                'url': forge_connexion_url(user, f"https://{domain}")
            }
    except Exception:
        button = None

    context = {
        'username': membership.member_name() or user.full_name() or user.email,
        'now': timezone.now(),
        'title': title,
        'image_url': image_url,
        'sub_title': _("Adhésion"),
        'main_text': main_text,
        'main_text_2': main_text_2,
        'table_info': {
            _('Produit'): f'{membership.price.product.name} - {membership.price.name}',
            _('Tarif'): f'{membership.price.name}',
            _('Montant'): f"{dround(membership.price.prix)} {config.currency_code}",
            _('Date de demande'): date_format(membership.date_added, format='DATETIME_FORMAT', use_l10n=True),
        },
        'button_color': "#009058",
        'button': button,
        'next_text_1': _("Si vous n'êtes pas à l'origine de cette demande, merci de contacter l'équipe TiBillet."),
        'end_text': _("À bientôt !"),
        'signature': _("Marvin, le robot TiBillet"),
    }

    try:
        send_email_generique(context=context, email=f"{user.email}")
        logger.info("send_membership_pending_user: mail envoyé")
        return True
    except Exception as e:
        logger.error(f"send_membership_pending_user: erreur d'envoi {e}")
        return False


@app.task
def send_membership_payment_link_user(membership_uuid: str):
    """Envoie un email à l'adhérent avec le lien de paiement Stripe après validation admin."""
    time.sleep(1)
    try:
        membership = Membership.objects.get(uuid=UUID(membership_uuid))
    except Membership.DoesNotExist:
        logger.error(f"send_membership_payment_link_user: membership {membership_uuid} introuvable")
        return False

    config = Configuration.get_solo()
    activate(config.language)

    tenant = connection.tenant
    tenant_url = tenant.get_primary_domain().domain

    # Construit l'email
    user = membership.user
    if not user or not getattr(user, 'email', None):
        logger.warning("send_membership_payment_link_user: destinataire manquant")
        return False

    title = _(f"{config.organisation} : Paiement de votre adhésion")
    context = {
        'username': membership.member_name() or user.full_name() or user.email,
        'now': timezone.now(),
        'title': title,
        'sub_title': _("Adhésion"),
        'main_text': _("Votre demande a été acceptée. Vous pouvez régler votre adhésion en cliquant sur le bouton ci-dessous."),
        'table_info': {
            _('Produit'): f'{membership.price.product.name} - {membership.price.name}',
            _('Montant'): f"{dround(membership.price.prix)} {config.currency_code}",
        },
        'button_color': "#009058",
        'button': {
            'text': _("Payer maintenant"),
            'url': f"https://{tenant_url}/memberships/{membership.uuid}/get_checkout_for_membership",
        },
        'end_text': _("Merci !"),
        'signature': _("Marvin, le robot TiBillet"),
    }

    try:
        send_email_generique(context=context, email=f"{user.email}")
        logger.info("send_membership_payment_link_user: mail envoyé")
        return True
    except Exception as e:
        logger.error(f"send_membership_payment_link_user: erreur d'envoi {e}")
        return False


#### SEND INFO TO LABOUTIK"}

@shared_task(bind=True, max_retries=20)
def send_stripe_bank_deposit_to_laboutik(self, payload):
    # Le max de temps entre deux retries : 24 heures
    MAX_RETRY_TIME = 86400  # 24 * 60 * 60 seconds = 24 h
    config = Configuration.get_solo()
    # On check si le serveur cashless est bien opérationnel :
    try:
        if not config.check_serveur_cashless():
            logger.warning(f"No serveur cashless on config. send_stripe_bank_deposit_to_laboutik not sended")
            return True
    except Exception as exc:
        logger.error(f"Erreur lors de config.check_serveur_cashless() Serveur down ?")
        # Ajoute un backoff exponentiel pour les autres erreurs
        retry_delay = min(3 ** self.request.retries, MAX_RETRY_TIME)
        raise self.retry(exc=exc, countdown=retry_delay)
    except MaxRetriesExceededError:
        logger.error(f"La tâche a échoué après plusieurs tentatives pour {config.check_serveur_cashless()}")

    json_data = json.dumps(payload, cls=DjangoJSONEncoder)

    url = f'{config.server_cashless}/api/stripebankdepositfromlespass'
    try:
        logger.info(f"start celery_post_request to {url}")
        response = requests.post(
            url,
            headers={
                "Authorization": f"Api-Key {config.key_cashless}",
                "Content-type": "application/json",
            },
            data=json_data,
            verify=bool(not settings.DEBUG),
            timeout=2,
        )
        if response.status_code == 200:
            logger.info("send_stripe_bank_deposit_to_laboutik sended_to_laboutik = True")
        # Si la réponse est 404, on déclenche un retry
        if response.status_code == 404:
            # Augmente le délai de retry avec un backoff exponentiel
            retry_delay = min(3 ** self.request.retries, MAX_RETRY_TIME)
            raise self.retry(countdown=retry_delay)

    except requests.exceptions.RequestException as exc:
        # Log et retry en cas d’erreur réseau ou autre exception
        logger.error(f"Erreur lors de l'envoi de la requête POST à {url}: {exc}")

        # Ajoute un backoff exponentiel pour les autres erreurs
        retry_delay = min(3 ** self.request.retries, MAX_RETRY_TIME)
        raise self.retry(exc=exc, countdown=retry_delay)

    except MaxRetriesExceededError:
        logger.error(f"La tâche a échoué après plusieurs tentatives pour {url}")


@shared_task(bind=True, max_retries=20)
def send_refund_to_laboutik(self, ligne_article_pk):
    # Le max de temps entre deux retries : 24 heures
    MAX_RETRY_TIME = 86400  # 24 * 60 * 60 seconds = 24 h
    config = Configuration.get_solo()

    # On check si le serveur cashless est bien opérationnel :
    try:
        if not config.check_serveur_cashless():
            logger.warning(f"No serveur cashless on config. Article not sended")
            return True
    except Exception as exc:
        logger.error(f"Erreur lors de config.check_serveur_cashless() Serveur down ?")
        # Ajoute un backoff exponentiel pour les autres erreurs
        retry_delay = min(3 ** self.request.retries, MAX_RETRY_TIME)
        raise self.retry(exc=exc, countdown=retry_delay)
    except MaxRetriesExceededError:
        logger.error(f"La tâche a échoué après plusieurs tentatives pour {config.check_serveur_cashless()}")

    # Tache lancé sur un celery. Le save n'est peut être pas encore réalisé coté trigger.
    ligne_article = LigneArticle.objects.get(pk=ligne_article_pk)
    logger.info(f"send_refund_to_laboutik -> ligne_article status : {ligne_article.get_status_display()}")

    serialized_ligne_article = LigneArticleSerializer(ligne_article).data
    json_data = json.dumps(serialized_ligne_article, cls=DjangoJSONEncoder)

    url = f'{config.server_cashless}/api/refundfromlespass'
    try:
        logger.info(f"start celery_post_request to {url}")
        response = requests.post(
            url,
            headers={
                "Authorization": f"Api-Key {config.key_cashless}",
                "Content-type": "application/json",
            },
            data=json_data,
            verify=bool(not settings.DEBUG),
            timeout=2,
        )

        # Si la réponse est 404, on déclenche un retry
        if response.status_code == 200:
            logger.info("sended_to_laboutik = True")
            ligne_article.sended_to_laboutik = True
            ligne_article.save()
        if response.status_code == 404:
            # Augmente le délai de retry avec un backoff exponentiel
            retry_delay = min(3 ** self.request.retries, MAX_RETRY_TIME)
            raise self.retry(countdown=retry_delay)

    except requests.exceptions.RequestException as exc:
        # Log et retry en cas d’erreur réseau ou autre exception
        logger.error(f"Erreur lors de l'envoi de la requête POST à {url}: {exc}")

        # Ajoute un backoff exponentiel pour les autres erreurs
        retry_delay = min(3 ** self.request.retries, MAX_RETRY_TIME)
        raise self.retry(exc=exc, countdown=retry_delay)

    except MaxRetriesExceededError:
        logger.error(f"La tâche a échoué après plusieurs tentatives pour {url}")


# @app.task
@shared_task(bind=True, max_retries=20)
def send_sale_to_laboutik(self, ligne_article_pk):
    # Le max de temps entre deux retries : 24 heures
    MAX_RETRY_TIME = 86400  # 24 * 60 * 60 seconds = 24 h
    config = Configuration.get_solo()

    # On check si le serveur cashless est bien opérationnel :
    try:
        if not config.check_serveur_cashless():
            logger.warning(f"No serveur cashless on config. Article not sended")
            return True
    except Exception as exc:
        logger.error(f"Erreur lors de config.check_serveur_cashless() Serveur down ?")
        # Ajoute un backoff exponentiel pour les autres erreurs
        retry_delay = min(3 ** self.request.retries, MAX_RETRY_TIME)
        raise self.retry(exc=exc, countdown=retry_delay)
    except MaxRetriesExceededError:
        logger.error(f"La tâche a échoué après plusieurs tentatives pour {config.check_serveur_cashless()}")

    # Tache lancé sur un celery. Le save n'est peut être pas encore réalisé coté trigger.
    ligne_article = LigneArticle.objects.get(pk=ligne_article_pk)
    logger.info(f"send_sale_to_laboutik -> ligne_article status : {ligne_article.get_status_display()}")

    # On va relancer la requete vers la db tant que ligne_article n'est pas valide
    while ligne_article.status != LigneArticle.VALID:
        time.sleep(1)
        ligne_article.refresh_from_db()
        logger.info(f"send_sale_to_laboutik -> Ligne Article is Valid ? : {ligne_article.get_status_display()}")

    serialized_ligne_article = LigneArticleSerializer(ligne_article).data
    json_data = json.dumps(serialized_ligne_article, cls=DjangoJSONEncoder)

    url = f'{config.server_cashless}/api/salefromlespass'
    try:
        logger.info(f"start celery_post_request to {url}")
        response = requests.post(
            url,
            headers={
                "Authorization": f"Api-Key {config.key_cashless}",
                "Content-type": "application/json",
            },
            data=json_data,
            verify=bool(not settings.DEBUG),
            timeout=2,
        )
        if response.status_code == 200:
            logger.info("sended_to_laboutik = True")
            ligne_article.sended_to_laboutik = True
            ligne_article.save()
        # Si la réponse est 404, on déclenche un retry
        if response.status_code == 404:
            # Augmente le délai de retry avec un backoff exponentiel
            retry_delay = min(3 ** self.request.retries, MAX_RETRY_TIME)
            raise self.retry(countdown=retry_delay)

    except requests.exceptions.RequestException as exc:
        # Log et retry en cas d’erreur réseau ou autre exception
        logger.error(f"Erreur lors de l'envoi de la requête POST à {url}: {exc}")

        # Ajoute un backoff exponentiel pour les autres erreurs
        retry_delay = min(3 ** self.request.retries, MAX_RETRY_TIME)
        raise self.retry(exc=exc, countdown=retry_delay)

    except MaxRetriesExceededError:
        logger.error(f"La tâche a échoué après plusieurs tentatives pour {url}")


def create_ticket_pdf(ticket: Ticket):
    # logger_weasy = logging.getLogger("weasyprint")
    # logger_weasy.addHandler(logging.NullHandler())
    # logger_weasy.setLevel(50)  # Only show errors, use 50
    # PROGRESS_LOGGER = logging.getLogger('weasyprint.progress')
    # PROGRESS_LOGGER.addHandler(logging.NullHandler())
    # PROGRESS_LOGGER.setLevel(50)  # Only show errors, use 50

    # Pour faire le qrcode
    qr = segno.make(f"{ticket.qrcode()}", micro=False)
    buffer_svg = BytesIO()
    qr.save(buffer_svg, kind='svg', scale=4.6)

    config = Configuration.get_solo()
    activate(config.language)

    context = {
        'ticket': ticket,
        'config': config,
        'img_svg': buffer_svg.getvalue().decode('utf-8'),
    }

    template_name = 'ticket/ticket.html'
    # template_name = 'ticket/ticket_V2.html'

    # template_name = 'ticket/example_flight_ticket.html'
    font_config = FontConfiguration()
    template = get_template(template_name)
    html = template.render(context)

    css = CSS(string=
              '''
                @font-face {
                  font-family: Libre Barcode;
                  src: url(file:///DjangoFiles/ApiBillet/templates/ticket/librebarcode128-regular.ttf);
                }
                @font-face {
                  font-family: Barlow Condensed;
                  src: url(file:///DjangoFiles/ApiBillet/templates/ticket/barlowcondensed-regular.otf)
                }
                @font-face {
                  font-family: Barlow Condensed;
                  font-weight: 300;
                  src: url(file:///DjangoFiles/ApiBillet/templates/ticket/barlowcondensed-light.otf);
                }
                @font-face {
                  font-family: Barlow Condensed;
                  font-weight: 700;
                  src: url(file:///DjangoFiles/ApiBillet/templates/ticket/barlowcondensed-bold.otf);
                }
              ''',
              font_config=font_config)

    pdf_binary = HTML(string=html).write_pdf(
        stylesheets=[css],
        font_config=font_config,
    )

    return pdf_binary


@app.task
def redirect_post_webhook_stripe_from_public(url, data):
    headers = {"Content-type": "application/json"}
    redirect_to_tenant = requests.request(
        "POST",
        f"{url}",
        headers={"Content-type": "application/json"},
        data=json.dumps(data),
    )
    logger.info(redirect_to_tenant.content)


@app.task
def contact_mailer(sender, subject, message):
    configuration = Configuration.get_solo()
    mail = CeleryMailerClass(
        email=[sender, configuration.email],
        title=subject,
        text=message,
        template='emails/contact_email.html',
        context={
            "organisation": configuration.organisation,
            "sender": sender,
            "subject": subject,
            "message": message,
        }
    )
    mail.send()
    logger.info(f"mail.sended : {mail.sended}")


def forge_connexion_url(user, base_url):
    User = get_user_model()

    signer = TimestampSigner()
    token = urlsafe_base64_encode(signer.sign(f"{user.pk}").encode('utf8'))

    ### VERIFICATION SIGNATURE AVANT D'ENVOYER
    user_pk = signer.unsign(urlsafe_base64_decode(token).decode('utf8'), max_age=(3600 * 72))  # 3 jours
    designed_user = User.objects.get(pk=user_pk)
    assert user == designed_user

    connexion_url = f"{base_url}/emailconfirmation/{token}"
    return connexion_url

@app.task(bind=True, autoretry_for=(smtplib.SMTPException, smtplib.SMTPServerDisconnected, smtplib.SMTPAuthenticationError, ConnectionError, TimeoutError), retry_backoff=True, retry_backoff_max=600, retry_jitter=True, max_retries=6)
def connexion_celery_mailer(self, user_email,
                            base_url,
                            title=None,
                            template=None,
                            next_url=None,):
    """
    :param title: Sujet de l'email
    :type user_email: str
    :type url: str
    :type tenant_name: str
    """
    logger.info(f'WORKDER CELERY app.task connexion_celery_mailer : {user_email}')
    User = get_user_model()
    user = User.objects.get(email=user_email)
    connexion_url = forge_connexion_url(user, base_url)
    if next_url:
        logger.info(f"next_url : {next_url}")
        connexion_url += f"?next={next_url}"


    logger.info(f"connexion_celery_mailer -> connection.tenant.schema_name : {connection.tenant.schema_name}")
    logger.info(f"{connexion_url}")

    config = Configuration.get_solo()
    activate(config.language)
    organisation = config.organisation

    # Premier mail ou config non renseignée, on mets TiBIllet
    if not organisation:
        organisation = "TiBillet"

    image_url = "https://tibillet.org/fr/img/design/logo-couleur.svg"
    if hasattr(config.img, 'med'):
        image_url = f"{base_url}{config.img.med.url}"

    logger.info(f'connection.tenant.schema_name != "public" : {connection.tenant.schema_name}')
    logger.info(f'    {organisation}')

    # Internal SMTP and html template
    if title is None:
        title = f"{organisation} : Confirmez votre email"  # celery ne prend pas la traduction
    if template is None:
        template = 'emails/connexion.html'

    logger.info(f'    title : {title}')
    if settings.DEBUG:
        logger.info(f"{connexion_url}")

    try:
        mail = CeleryMailerClass(
            user.email,
            title,
            template=template,
            context={
                'organisation': organisation,
                'image_url': image_url,
                'connexion_url': connexion_url,
                'base_url': base_url,
            },
        )
        try:
            mail.send()
            logger.info(f"mail.sent: {mail.sended}")

        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"ERROR {timezone.now()} Erreur envoie de mail pour connexion {user.email} : {e}")
            logger.error(f"mail.sent: {mail.sended}")
            User = get_user_model()
            # ATTENTION : Jamais de user.save() dans celery : s'il ya un traitement en cours dans Django, ça va ecraser l'objet.
            User.objects.filter(pk=user.pk).update(is_active=False, email_error=True)

    except Exception as e:
        logger.error(f"{timezone.now()} Erreur envoie de mail pour connexion {user.email} : {e}")
        raise Exception


@app.task
def new_tenant_mailer(waiting_config_uuid: str):
    try:
        # Génération du lien qui va créer la redirection vers l'url onboard
        tenant = connection.tenant
        tenant_url = tenant.get_primary_domain().domain

        time.sleep(2)  # Attendre que la db soit bien a jour
        waiting_config = WaitingConfiguration.objects.get(uuid=waiting_config_uuid)

        signer = TimestampSigner()
        token = urlsafe_base64_encode(signer.sign(f"{waiting_config.uuid}").encode('utf8'))

        ### VERIFICATION SIGNATURE AVANT D'ENVOYER
        wc_pk = signer.unsign(urlsafe_base64_decode(token).decode('utf8'), max_age=(3600 * 72))  # 3 jours
        wv_wanted = WaitingConfiguration.objects.get(uuid=wc_pk)
        if not waiting_config == wv_wanted:
            raise Exception("signature check error")

        p_domain = connection.tenant.get_primary_domain().domain
        connexion_url = f"https://{p_domain}/tenant/{token}/emailconfirmation_tenant"

        config = Configuration.get_solo()
        activate(config.language)

        mail = CeleryMailerClass(
            waiting_config.email,
            _("TiBillet : Creation of a new instance."),
            template='reunion/views/tenant/emails/welcome_email.html',
            context={
                'waiting_config': waiting_config,
                'orga_name': f"{waiting_config.organisation.capitalize()}",
                'tenant_url': tenant_url,
                'connexion_url': connexion_url,
            }
        )
        mail.send()
        logger.info(f"mail.sended : {mail.sended}")

    except smtplib.SMTPRecipientsRefused as e:
        logger.error(
            f"ERROR {timezone.now()} Erreur mail SMTPRecipientsRefused pour report_celery_mailer : {e}")
        raise e


@app.task
def new_tenant_after_stripe_mailer(waiting_config_uuid: str):
    # Mail qui prévient l'administrateur ROOT de l'instance TiBillet qu'un nouveau tenant souhaite se créer.
    try:
        # Génération du lien qui va créer la redirection vers l'url onboard
        waiting_config = WaitingConfiguration.objects.get(uuid=waiting_config_uuid)
        logger.info(f"new_tenant_after_stripe_mailer : {waiting_config.organisation}")
        super_admin_root = [user.email for user in TibilletUser.objects.filter(is_superuser=True)]
        mail = CeleryMailerClass(
            super_admin_root,
            _(f"{waiting_config.organisation} & TiBillet : Lespass tenant creation request. ROOT admin action requested"),
            template='reunion/views/tenant/emails/after_onboard_stripe_for_superadmin.html',
            context={
                'waiting_config': waiting_config,
            }
        )
        mail.send()
        logger.info(f"mail.sended : {mail.sended}")

    except smtplib.SMTPRecipientsRefused as e:
        logger.error(
            f"ERROR {timezone.now()} Erreur mail SMTPRecipientsRefused pour report_celery_mailer : {e}")
        raise e


@app.task
def report_celery_mailer(data_report_list: list):
    configuration = Configuration.get_solo()
    if configuration.server_cashless and configuration.key_cashless:
        attached_files = {}
        for report in data_report_list:
            print(f"report : {report.get('structure')}")
            try:
                pdf_binary = report_to_pdf(report)
                attached_files[f"{report.get('structure')}-{report.get('date')}.pdf"] = pdf_binary

            except Exception as e:
                logger.info(f"ZReportPDF erreur {e}")
                raise e

        try:
            mail = CeleryMailerClass(
                configuration.email,
                _(f"TiBillet sales report - {configuration.organisation}"),
                template='mails/mail_rapport.html',
                context={'organisation': f'{configuration.organisation}'},
                attached_files=attached_files,
            )
            mail.send()
            logger.info(f"mail.sended : {mail.sended}")

        except smtplib.SMTPRecipientsRefused as e:
            logger.error(
                f"ERROR {timezone.now()} Erreur mail SMTPRecipientsRefused pour report_celery_mailer : {e}")


@app.task
def send_email_generique(context: dict = None, email: str = None, attached_files: dict = None):
    template_name = "emails/email_generique.html"
    try:
        mail = CeleryMailerClass(
            email,
            f"{context.get('title')}",
            template=template_name,
            context=context,
            attached_files=attached_files,
        )
        mail.send()
        logger.info(f"    send_email_generique : mail.sended : {mail.sended}")

    except smtplib.SMTPRecipientsRefused as e:
        logger.error(
            f"ERROR {timezone.now()} Erreur mail SMTPRecipientsRefused pour report_celery_mailer : {e}")


@app.task
def ticket_celery_mailer(reservation_uuid: str):
    logger.info(f'      WORKDER CELERY app.task ticket_celery_mailer : {reservation_uuid}')
    config = Configuration.get_solo()
    activate(config.language)

    reservation = None
    resa_try = 0
    while reservation is None and resa_try < 10:
        try :
            logger.info(f"ticket_celery_mailer -> reservation_uuid : {reservation_uuid}")
            reservation = Reservation.objects.get(pk=reservation_uuid)
        except Reservation.DoesNotExist:
            resa_try += 1
            sleep(1)

    domain = connection.tenant.get_primary_domain().domain
    image_url_place = "https://tibillet.org/fr/img/design/logo-couleur.svg"
    image_url_event = "https://tibillet.org/fr/img/design/logo-couleur.svg"
    if hasattr(config.img, 'med'):
        image_url_place = f"https://{domain}{config.img.med.url}"
    if reservation.event:
        if reservation.event.img:
            image_url_event = f"https://{domain}{reservation.event.img.med.url}"

    if not reservation.to_mail:
        reservation.status = Reservation.PAID_NOMAIL
        reservation.save()
        logger.info(f"CELERY mail reservation.to_mail : {reservation.to_mail}. On passe en PAID_NOMAIL")

    else:
        attached_files = {}
        for ticket in reservation.tickets.filter(status=Ticket.NOT_SCANNED):
            attached_files[ticket.pdf_filename()] = create_ticket_pdf(ticket)

        try:
            mail = CeleryMailerClass(
                reservation.user_commande.email,
                f"Votre reservation pour {config.organisation}",
                template='emails/buy_confirmation.html',
                context={
                    'config': config,
                    'custom_confirmation_message': reservation.event.custom_confirmation_message,
                    'reservation': reservation,
                    'image_url_place': image_url_place,
                    'image_url_event': image_url_event,
                },
                attached_files=attached_files,
            )
            try:
                mail.send()
                logger.info(f"mail.sended : {mail.sended}")

                if mail.sended:
                    logger.info("reservation.mail_send & reservation.status = Reservation.VALID & reservation.save()")
                    reservation.mail_send = True
                    reservation.status = Reservation.VALID
                    reservation.save()

            except smtplib.SMTPRecipientsRefused as e:

                logger.error(
                    f"ERROR {timezone.now()} Erreur mail SMTPRecipientsRefused pour reservation {reservation} : {e}")
                logger.error(f"mail.sended : {mail.sended}")
                reservation.mail_send = False
                reservation.mail_error = True

                reservation.status = Reservation.PAID_ERROR
                reservation.save()


        except Exception as e:
            logger.error(f"{timezone.now()} Erreur envoie de mail pour reservation {reservation} : {e}")
            raise Exception


@app.task
def webhook_reservation(reservation_pk, solo_webhook_pk=None):
    logger.info(f"webhook_reservation : {reservation_pk}")

    # On lance tous les webhook ou juste un seul ?
    webhooks = []
    if solo_webhook_pk:
        webhooks.append(Webhook.objects.get(pk=solo_webhook_pk))
    else:
        webhooks = Webhook.objects.filter(event=Webhook.RESERVATION_V, active=True)

    if len(webhooks) > 0:
        reservation = Reservation.objects.get(pk=reservation_pk)
        json = {
            "object": "reservation",
            "uuid": f"{reservation.uuid}",
            "state": f"{reservation.status}",
            "datetime": f"{reservation.datetime}",
        }

        for webhook in webhooks:
            try:
                response = requests.request("POST", webhook.url, data=json, timeout=2, verify=bool(not settings.DEBUG))
                webhook.last_response = f"{timezone.now()} - status code {response.status_code} - {response.content}"
                if not response.ok:
                    logger.error(f"webhook_reservation ERROR : {reservation_pk} {timezone.now()} {response.content}")
                    webhook.active = False
            except Exception as e:
                logger.error(f"webhook_reservation ERROR : {reservation_pk} {timezone.now()} {e}")
                webhook.last_response = f"{timezone.now()} - {e}"
                webhook.active = False
            webhook.save()


@app.task
def webhook_membership(membership_pk, solo_webhook_pk=None):
    logger.info(f"webhook_membership : {membership_pk}")

    # On lance tous les webhook ou juste un seul ?
    webhooks = []
    if solo_webhook_pk:
        webhooks.append(Webhook.objects.get(pk=solo_webhook_pk))
    else:
        webhooks = Webhook.objects.filter(event=Webhook.MEMBERSHIP_V, active=True)

    if len(webhooks) > 0:
        membership = Membership.objects.get(pk=membership_pk)
        # Build payload with DRF serializer
        data_sended = json.dumps(MembershipSerializer(membership).data, cls=DjangoJSONEncoder)

        # Si plusieurs webhook :
        for webhook in webhooks:
            try:
                response = requests.request("POST", webhook.url, data=data_sended, timeout=2,
                                            headers={"Content-type": "application/json"},
                                            verify=bool(not settings.DEBUG))
                logger.debug(f"############### webhook_membership ###############\n")
                logger.debug(f"data sended : {data_sended}\n")
                logger.debug(f"response : {response.content}")
                logger.debug(f"############### webhook_membership ###############\n")
                webhook.last_response = f"{timezone.now()} - status code {response.status_code} - {response.content}"
                if not response.ok:
                    logger.error(f"webhook_membership ERROR : {membership_pk} {timezone.now()} {response.content}")
                    webhook.active = False
            except Exception as e:
                logger.error(f"webhook_membership ERROR : {membership_pk} {timezone.now()} {e}")
                webhook.last_response = f"{timezone.now()} - {e}"
                webhook.active = False
            webhook.save()


@app.task
def send_to_brevo(membership_pk):
    brevo_config = BrevoConfig.get_solo()
    if brevo_config.api_key:
        try:
            # Excpet avec nouvel essaie 3 secondes plus tard.
            # Lorsque c'est créé par l'admin, le trigger se lance avant que l'objet se soit save en db.
            membership = Membership.objects.get(pk=membership_pk)
        except Membership.DoesNotExist:
            time.sleep(2)
            membership = Membership.objects.get(pk=membership_pk)

        import sib_api_v3_sdk
        from sib_api_v3_sdk.rest import ApiException
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = brevo_config.get_api_key()
        api_instance = sib_api_v3_sdk.ContactsApi(sib_api_v3_sdk.ApiClient(configuration))

        try:
            # First, check if the contact already exists
            api_instance.get_contact_info(membership.user.email)
            logger.info(f"Contact with email {membership.user.email} already exists in Brevo")
            brevo_config.last_log = f"Contact already exists: {membership.user.email}"
            brevo_config.save()
            return  # Exit as there's nothing more to do

        except ApiException as e:
            # If we get a 404, the contact doesn't exist, which is what we want
            if e.status == 404:
                # Contact doesn't exist, create it
                create_contact = sib_api_v3_sdk.CreateContact(email=membership.user.email)
                api_response = api_instance.create_contact(create_contact)
                brevo_config.last_log = f"Contact created: {api_response}"
                brevo_config.save()
            else:
                # Any other API exception should be handled as an error
                logger.error(f"send_to_brevo ERROR : {e}")
                raise e


@app.task
def send_to_ghost_email(email, name=None):
    ghost_config = GhostConfig.get_solo()
    ghost_url = ghost_config.ghost_url
    ghost_key = ghost_config.get_api_key()

    if ghost_url and ghost_key:

        ###################################
        ## Génération du token JWT
        ###################################

        # Split the key into ID and SECRET
        id, secret = ghost_key.split(':')

        # Prepare header and payload
        iat = int(datetime.datetime.now().timestamp())

        header = {'alg': 'HS256', 'typ': 'JWT', 'kid': id}
        payload = {
            'iat': iat,
            'exp': iat + 5 * 60,
            'aud': '/admin/'
        }

        # Create the token (including decoding secret)
        token = jwt.encode(payload, bytes.fromhex(secret), algorithm='HS256', headers=header)
        logger.debug(f"JWT token: " + token)

        ###################################
        ## Appels de l'API Ghost
        ###################################

        # Définir les critères de filtrage
        filter = {
            "filter": f"email:{email}"
        }
        headers = {'Authorization': f'Ghost {token}'}

        # Récupérer la liste des membres de l'instance Ghost
        response = requests.get(ghost_url + "/ghost/api/admin/members/", params=filter, headers=headers)

        # Vérifier que la réponse de l'API est valide
        if response.ok:
            # Décoder la réponse JSON
            j = response.json()
            members = j['members']

            # Si aucun membre n'a été trouvé avec l'adresse e-mail spécifiée
            if len(members) == 0:
                # Définir les informations du nouveau membre
                member_data = {
                    "members": [
                        {
                            "email": email,
                            "name": name if name else "",
                            "labels": ["TiBillet", f"import {timezone.now().strftime('%d/%m/%Y')}"]
                        }
                    ]
                }

                # Ajouter le nouveau membre à l'instance Ghost
                response = requests.post(ghost_url + "/ghost/api/admin/members/", json=member_data, headers=headers,
                                         timeout=2)

                # Vérifier que la réponse de l'API est valide
                if response.status_code == 201:
                    # Décoder la réponse JSON
                    j = response.json()
                    members = j['members']
                    logger.info(f"Le nouveau membre a été créé avec succès : {members}")
                elif response.status_code == 422 and 'Member already exists' in response.text:
                    # Idempotent case: member already exists in Ghost, treat as success
                    logger.info(f"Le membre {email} existe déjà (détection via 422), aucune action nécessaire.")
                else:
                    logger.warning(f"Erreur lors de la création du nouveau membre : {response.text}")
            else:
                # Afficher la liste des membres
                logger.info(f"Le membre {email} existe déja dans : {members}")
        else:
            logger.error(f"Erreur lors de la récupération des membres : {response.text}")

        # On met à jour les logs pour debug
        try:
            if response is not None and response.status_code == 422 and 'Member already exists' in response.text:
                # Ne pas enregistrer le message d'erreur complet pour un doublon, message explicite et bénin
                ghost_config.ghost_last_log = f"{timezone.now()} : Membre déjà existant (aucune action nécessaire)."
            else:
                ghost_config.ghost_last_log = f"{timezone.now()} : {response.text}"
            ghost_config.save()
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du log : {e}")
    else:
        logger.warning(
            f"send_to_ghost_email : ghost_url or ghost_key is empty on {connection.tenant.get_primary_domain()}")


@app.task
def send_to_ghost(membership_pk):
    ghost_config = GhostConfig.get_solo()
    ghost_url = ghost_config.ghost_url
    ghost_key = ghost_config.get_api_key()

    if ghost_url and ghost_key:
        try:
            # Excpet avec nouvel essaie 3 secondes plus tard.
            # Lorsque c'est créé par l'admin, le trigger se lance avant que l'objet se soit save en db.
            membership = Membership.objects.get(pk=membership_pk)
        except Membership.DoesNotExist:
            time.sleep(2)
            membership = Membership.objects.get(pk=membership_pk)

        # Email du compte :
        user = membership.user
        email = user.email
        name = f"{membership.first_name.capitalize()} {membership.last_name.capitalize()}"
        send_to_ghost_email(email, name)


@app.task
def send_welcome_email(email: str, username: str = None):
    """
    Envoie un email de bienvenue aux nouveaux utilisateurs.

    Args:
        email: L'adresse email du destinataire
        username: Le nom d'utilisateur (optionnel)
    """
    logger.info(f"Envoi d'un email de bienvenue à {email}")

    context = {
        'title': _("Bienvenue sur TiBillet"),
        'username': username or email.split('@')[0],
        'now': timezone.now(),
        'objet': _("Bienvenue"),
        'image_url': "https://tibillet.org/fr/img/design/logo-couleur.svg",
    }

    try:
        mail = CeleryMailerClass(
            email,
            f"{context.get('title')}",
            template="emails/welcome/welcome_email.html",
            context=context,
        )
        mail.send()
        logger.info(f"send_welcome_email : mail.sended : {mail.sended}")
        return mail.sended
    except Exception as e:
        logger.error(f"ERROR {timezone.now()} Erreur lors de l'envoi de l'email de bienvenue à {email}: {e}")
        return False


@app.task
def membership_renewal_reminder():
    """
    Envoie d'un mail de renouvellement si l'adhésion arrive a expiration le lendemain
    """
    for tenant in get_tenant_model().objects.exclude(schema_name='public'):
        with tenant_context(tenant):
            memberships = Membership.objects.filter(deadline__gte=timezone.now(),
                                                    deadline__lte=timezone.now() + timezone.timedelta(days=1),
                                                    price__recurring_payment=False, # on ne prend pas les adhésions avec paiement récurents
                                                    )

            for membership in memberships:
                config = Configuration.get_solo()
                user = membership.user
                email = user.email

                context = {
                    'title': _(f"Votre adhésion au collectif {config.organisation} arrive à expiration"),
                    'membership': membership,
                    'now': timezone.now(),
                    'objet': _(f"Votre adhésion {config.organisation} arrive à expiration"),
                    'image_url': "https://tibillet.org/fr/img/design/logo-couleur.svg",
                    'renewal_url': f"https://{tenant.get_primary_domain().domain}/memberships/"
                }

                try:
                    mail = CeleryMailerClass(
                        email,
                        f"{context.get('title')}",
                        template="emails/membership_renewal_reminder.html",
                        context=context,
                    )
                    mail.send()
                    logger.info(f"send_welcome_email : mail.sended : {mail.sended}")
                    return mail.sended
                except Exception as e:
                    logger.error(
                        f"ERROR {timezone.now()} Erreur lors de l'envoi de membership_renewal_reminder à {email}: {e}")
                    return False


@app.task
def trigger_product_update_tasks(product_pk):
    time.sleep(1)
    product = Product.objects.get(pk=product_pk)
    # On prévient LaBoutik qu'un produit adhésion et/ou badge a changé
    if product.categorie_article in [Product.ADHESION, Product.BADGE]:
        config = Configuration.get_solo()
        if config.check_serveur_cashless():
            send_to_laboutik = requests.post(
                f'{config.server_cashless}/api/trigger_product_update',
                headers={
                    'Authorization': f'Api-Key {config.key_cashless}',
                    'Origin': config.domain(),
                },
                data={"product_pk": product.pk},
                timeout=1,
                verify=bool(not settings.DEBUG),
            )
            logger.info(f"    send_to_laboutik : {send_to_laboutik.status_code} {send_to_laboutik.text}")


@app.task
def refill_from_lespass_to_user_wallet_from_price_solded(ligne_article_pk):
    time.sleep(1)  # wait for trigger pre_save
    ligne_article = LigneArticle.objects.get(pk=ligne_article_pk)

    try:
        product: Product = ligne_article.pricesold.productsold.product
        price: Price = ligne_article.pricesold.price

        if getattr(price, "fedow_reward_enabled", False) and getattr(price, "fedow_reward_asset", None) and getattr(
                price, "fedow_reward_amount", None):
            fedowAPI = FedowAPI()

            asset = getattr(price, "fedow_reward_asset", None)
            float_amount = getattr(price, "fedow_reward_amount", None)
            amount = int(dround(float_amount) * 100)

            membership = ligne_article.membership
            if asset and amount and membership.user:
                from fedow_connect.models import FedowConfig
                if FedowConfig.get_solo().can_fedow():
                    logger.info("    TRIGGER_A ADHESION PAID -> Fedow reward enabled: sending tokens to user wallet")
                    checkout_session_id_stripe = ligne_article.paiement_stripe.checkout_session_id_stripe
                    invoice_stripe_id = ligne_article.paiement_stripe.invoice_stripe # on est peut être sur un renouvellement
                    metadata = {
                        "ligne_article_uuid": str(ligne_article.uuid),
                        "membership_uuid": str(membership.uuid),
                        "product_uuid": str(product.uuid),
                        "price_uuid": str(price.uuid),
                        "checkout_session_id_stripe": checkout_session_id_stripe,
                        "invoice_stripe_id" : invoice_stripe_id,
                        "reason": f"Membership reward for {product.name} - {price.name} : {float_amount} {asset.name} ",
                    }
                    # Prevent duplicate reward if metadata already present
                    already_sent = False
                    if ligne_article.metadata and isinstance(ligne_article.metadata, dict):
                        already_sent = bool(ligne_article.metadata.get("fedow_reward"))
                    if not already_sent:
                        reward_tx = fedowAPI.transaction.refill_from_lespass_to_user_wallet(
                            user=membership.user,
                            amount=amount,
                            asset=asset,
                            metadata=metadata,
                        )
                        # Link transaction to membership and payment for traceability
                        try:
                            from BaseBillet.models import FedowTransaction
                            fedow_tx = FedowTransaction.objects.get(pk=reward_tx.get("uuid"))
                            membership.fedow_transactions.add(fedow_tx)
                            if membership.stripe_paiement.exists():
                                membership.stripe_paiement.latest('last_action').fedow_transactions.add(fedow_tx)
                        except Exception as e:
                            logger.warning(f"Could not link Fedow reward transaction: {e}")
                        # Mark on ligne_article to avoid duplicates
                        try:
                            meta = ligne_article.metadata or {}
                            meta["fedow_reward"] = {
                                "transaction_uuid": str(reward_tx.get("uuid")),
                                "hash": reward_tx.get("hash"),
                                "asset": str(asset.uuid),
                                "amount": int(amount),
                                "sent_at": timezone.now().isoformat(),
                            }
                            ligne_article.metadata = meta
                            ligne_article.save(update_fields=["metadata"])
                        except Exception as e:
                            logger.warning(f"Could not save fedow_reward metadata on LigneArticle: {e}")
                    else:
                        logger.info("    TRIGGER_A ADHESION PAID -> Fedow reward already sent for this line, skipping")
            else:
                logger.info("    TRIGGER_A ADHESION PAID -> Fedow reward config incomplete or no user, skipping")
    except Exception as e:
        logger.error(f"Fedow reward error: {e}")


@app.task
def send_payment_success_admin(amount: int, payment_time_str: str, place: str, user_email: str):
    """
    Envoie un email à l'admin de l'instance pour confirmer la réception d'un paiement.
    """
    config = Configuration.get_solo()
    activate(config.language)
    admin_email = config.email
    title = f"{config.organisation.capitalize()} - {str(dround(amount))}€ : " + _("Payment received via QR code.")

    # Variables sémantiques pour le template
    try:
        dt = datetime.datetime.strptime(payment_time_str, '%d/%m/%Y %H:%M')
        aware_dt = timezone.make_aware(dt, timezone.get_current_timezone())
        payment_time_iso = aware_dt.isoformat()
    except Exception:
        payment_time_iso = timezone.now().isoformat()
    currency_symbol = "€"
    context = {
        'title': title,
        'amount': amount,
        'payment_time': payment_time_str,
        'payment_time_iso': payment_time_iso,
        'place': place,
        'user_email': user_email,
        'organisation': config.organisation,
        'now': timezone.now(),
        'image_url': "https://tibillet.org/fr/img/design/logo-couleur.svg",
        'currency_symbol': currency_symbol,
    }
    mail = CeleryMailerClass(
        admin_email,
        title,
        template="reunion/views/qrcode_scan_pay/email/payment_success_admin.html",
        context=context,
    )
    mail.send()
    return bool(mail.sended)


@app.task
def send_payment_success_user(user_email: str, amount: int, payment_time_str: str, place: str):
    """
    Envoie un email à l'utilisateur pour confirmer que son paiement est bien passé.
    """
    config = Configuration.get_solo()
    activate(config.language)

    title = f"{config.organisation.capitalize()} - {str(dround(amount))}€ : " + _("Your payment has been validated.")
    # Variables sémantiques pour le template
    try:
        dt = datetime.datetime.strptime(payment_time_str, '%d/%m/%Y %H:%M')
        aware_dt = timezone.make_aware(dt, timezone.get_current_timezone())
        payment_time_iso = aware_dt.isoformat()
    except Exception:
        payment_time_iso = timezone.now().isoformat()
    currency_symbol = "€"
    context = {
        'title': title,
        'amount': amount,
        'payment_time': payment_time_str,
        'payment_time_iso': payment_time_iso,
        'place': place,
        'organisation': config.organisation,
        'now': timezone.now(),
        'image_url': "https://tibillet.org/fr/img/design/logo-couleur.svg",
        'currency_symbol': currency_symbol,
    }
    mail = CeleryMailerClass(
        user_email,
        title,
        template="reunion/views/qrcode_scan_pay/email/payment_success_user.html",
        context=context,
    )
    mail.send()
    return bool(mail.sended)


@app.task
def test_logger():
    logger.debug(f"{timezone.now()} debug")
    logger.info(f"{timezone.now()} info")
    logger.warning(f"{timezone.now()} warning")
    logger.error(f"{timezone.now()} error")


@app.task
def send_reservation_cancellation_user(reservation_uuid: str):
    """
    Envoie un email à l'utilisateur pour confirmer l'annulation de sa réservation.
    """
    config = Configuration.get_solo()
    activate(config.language)

    try:
        reservation = Reservation.objects.get(pk=reservation_uuid)
    except Reservation.DoesNotExist:
        logger.error(f"send_reservation_cancellation_user: reservation {reservation_uuid} does not exist")
        return False

    title = f"{config.organisation.capitalize()} - " + _("Your reservation has been cancelled.")

    # Image/logo du lieu
    image_url_place = "https://tibillet.org/fr/img/design/logo-couleur.svg"
    try:
        domain = connection.tenant.get_primary_domain().domain
        if hasattr(config, 'img') and hasattr(config.img, 'med') and config.img.med:
            image_url_place = f"https://{domain}{config.img.med.url}"
    except Exception:
        pass

    # Montant potentiel associé à ce ticket (indicatif)
    refund_amount = 0
    try:
        if reservation.can_refund():
            for ticket in reservation.tickets.all():
                refund_amount += ticket.paid()
    except Exception:
        refund_amount = None

    currency_symbol = "€"
    context = {
        'title': title,
        'organisation': config.organisation,
        'reservation': reservation,
        'cancel_text': reservation.cancel_text(),
        'refund_amount': refund_amount,
        'currency_symbol': currency_symbol,
        'now': timezone.now(),
        'image_url_place': image_url_place,
    }

    mail = CeleryMailerClass(
        reservation.user_commande.email,
        title,
        template="emails/reservation_cancellation.html",
        context=context,
    )
    mail.send()
    return bool(mail.sended)


@app.task
def send_ticket_cancellation_user(ticket_uuid: str):
    """
    Envoie un email à l'utilisateur pour confirmer l'annulation d'un billet (ticket) individuel,
    avec indication sur le remboursement selon la politique en vigueur.
    """
    config = Configuration.get_solo()
    activate(config.language)

    try:
        ticket = Ticket.objects.get(pk=ticket_uuid)
    except Ticket.DoesNotExist:
        logger.error(f"send_ticket_cancellation_user: ticket {ticket_uuid} does not exist")
        return False

    reservation = ticket.reservation

    title = f"{config.organisation.capitalize()} - " + _("Your ticket has been cancelled.")

    # Image/logo du lieu
    image_url_place = "https://tibillet.org/fr/img/design/logo-couleur.svg"
    try:
        domain = connection.tenant.get_primary_domain().domain
        if hasattr(config, 'img') and hasattr(config.img, 'med') and config.img.med:
            image_url_place = f"https://{domain}{config.img.med.url}"
    except Exception:
        pass

    # Texte d'annulation (remboursement ou pas) réutilise la logique de réservation
    cancel_text = reservation.cancel_text()

    # Montant potentiel associé à ce ticket (indicatif)
    refund_amount = None
    try:
        if reservation.can_refund():
            refund_amount = ticket.paid()
    except Exception:
        refund_amount = None

    currency_symbol = "€"
    context = {
        'title': title,
        'organisation': config.organisation,
        'reservation': reservation,
        'ticket': ticket,
        'event': reservation.event,
        'event_datetime': reservation.event.datetime if reservation.event else None,
        'cancel_text': cancel_text,
        'refund_amount': refund_amount,
        'currency_symbol': currency_symbol,
        'now': timezone.now(),
        'image_url_place': image_url_place,
    }

    mail = CeleryMailerClass(
        reservation.user_commande.email,
        title,
        template="emails/ticket_cancellation.html",
        context=context,
    )
    mail.send()
    return bool(mail.sended)
