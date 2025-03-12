# import base64
import datetime
import json
import logging
import os
import smtplib
from io import BytesIO

import barcode
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
from django.core.signing import Signer, TimestampSigner
from django.db import connection
from django.template.loader import render_to_string, get_template
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.text import slugify
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

from ApiBillet.serializers import LigneArticleSerializer
from AuthBillet.models import TibilletUser
from BaseBillet.models import Reservation, Ticket, Configuration, Membership, Webhook, Paiement_stripe, LigneArticle, \
    GhostConfig
from Customers.models import Client
from MetaBillet.models import WaitingConfiguration
from TiBillet.celery import app
from django.utils.translation import gettext_lazy as _

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
    template_name = 'invoice/invoice.html'
    font_config = FontConfiguration()
    template = get_template(template_name)

    user = membership.user

    context = {
        'config': config,
        'paiement': membership.stripe_paiement.first(),
        'membership': membership,
        'email': user.email,
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

    domain = connection.tenant.get_primary_domain().domain
    image_url = "https://tibillet.org/fr/img/design/logo-couleur.svg"
    if hasattr(config.img, 'med'):
        image_url = f"https://{domain}{config.img.med.url}"

    context = {
        'username': membership.member_name(),
        'now': timezone.now(),
        'title': f"{config.organisation} : {membership.price.product.name}",
        'image_url': image_url,
        'objet': _("Confirmation email"),
        'sub_title': _("Welcome aboard !"),
        'main_text': _(
            _(f"Votre paiement pour {membership.price.product.name} a bien été reçu.")),
        # 'main_text_2': _("Si vous pensez que cette demande est main_text_2, vous n'avez rien a faire de plus :)"),
        # 'main_text_3': _("Dans le cas contraire, vous pouvez main_text_3. Merci de contacter l'équipe d'administration via : contact@tibillet.re au moindre doute."),
        'table_info': {
            _('Reçu pour'): f'{membership.member_name()}',
            _('Article'): f'{membership.price.product.name} - {membership.price.name}',
            _('Contribution'): f'{membership.contribution_value}',
            _('Date'): f'{membership.last_contribution}',
            _('Valable jusque'): f'{membership.get_deadline()}',
        },
        'button_color': "#009058",
        'button': {
            'text': _('RECUPERER UNE FACTURE'),
            'url': f'https://{domain}/memberships/{membership.pk}/invoice/',
        },
        'next_text_1': _("If you receive this email in error, please contact the TiBillet team."),
        # 'next_text_2': "next_text_2",
        'end_text': _('See you soon, and bon voyage.'),
        'signature': _("Marvin, the TiBillet robot"),
    }
    # Ajout des options str si il y en a :
    if membership.option_generale.count() > 0:
        context['table_info']['Options'] = f"{membership.options()}"
    return context


def send_membership_invoice_to_email(membership: "Membership"):
    user = membership.user
    # Mails de confirmation qui contient un lien vers la facture :
    logger.info(f"    update_membership_state_after_paiement : Envoi de la confirmation par email")
    send_email_generique(
        context=context_for_membership_email(membership),
        email=f"{user.email}",
    )
    logger.info(f"    update_membership_state_after_paiement : Envoi de la confirmation par email DELAY")
    return True


def send_sale_to_laboutik(ligne_article):
    config = Configuration.get_solo()
    if config.check_serveur_cashless():
        serialized_ligne_article = LigneArticleSerializer(ligne_article).data
        json_data = json.dumps(serialized_ligne_article, cls=DjangoJSONEncoder)

        # Lancer ça dans un celery avec retry
        celery_post_request.delay(
            url=f'{config.server_cashless}/api/salefromlespass',
            data=json_data,
            headers={
                "Authorization": f"Api-Key {config.key_cashless}",
                "Content-type": "application/json",
            },
        )
    else:
        logger.warning(f"No serveur cashless on config. Membership not sended")


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
    qr.save(buffer_svg, kind='svg', scale=6)

    context = {
        'ticket': ticket,
        'config': Configuration.get_solo(),
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


@app.task
def connexion_celery_mailer(user_email, base_url, title=None, template=None):
    """

    :param title: Sujet de l'email
    :type user_email: str
    :type url: str
    :type tenant_name: str

    """
    logger.info(f'WORKDER CELERY app.task connexion_celery_mailer : {user_email}')

    User = get_user_model()
    user = User.objects.get(email=user_email)

    signer = TimestampSigner()
    token = urlsafe_base64_encode(signer.sign(f"{user.pk}").encode('utf8'))

    ### VERIFICATION SIGNATURE AVANT D'ENVOYER
    user_pk = signer.unsign(urlsafe_base64_decode(token).decode('utf8'), max_age=(3600 * 72))  # 3 jours
    designed_user = User.objects.get(pk=user_pk)
    assert user == designed_user

    # token = default_token_generator.make_token(user, )

    connexion_url = f"{base_url}/emailconfirmation/{token}"
    logger.info("connexion_celery_mailer -> connection.tenant.schema_name : {connection.tenant.schema_name}")
    config = Configuration.get_solo()
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
        title = f"{organisation} : Confirmez votre email et connectez vous !"
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
            logger.info(f"mail.sended : {mail.sended}")

        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"ERROR {timezone.now()} Erreur envoie de mail pour connexion {user.email} : {e}")
            logger.error(f"mail.sended : {mail.sended}")
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
        waiting_config = WaitingConfiguration.objects.get(uuid=waiting_config_uuid)
        create_url_for_onboard_stripe = f"https://{tenant_url}/tenant/{waiting_config_uuid}/onboard_stripe/"

        mail = CeleryMailerClass(
            waiting_config.email,
            _("TiBillet : Création d'un nouvel espace."),
            template='reunion/views/tenant/emails/onboard_stripe.html',
            context={
                'create_url_for_onboard_stripe': f'{create_url_for_onboard_stripe}',
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
def new_tenant_after_stripe_mailer(waiting_config_uuid: str):
    # Mail qui prévient l'administrateur ROOT de l'instance TiBillet qu'un nouveau tenant souhaite se créer.
    try:
        # Génération du lien qui va créer la redirection vers l'url onboard
        waiting_config = WaitingConfiguration.objects.get(uuid=waiting_config_uuid)
        logger.info(f"new_tenant_after_stripe_mailer : {waiting_config.organisation}")
        super_admin_root = [user.email for user in TibilletUser.objects.filter(is_superuser=True)]
        mail = CeleryMailerClass(
            super_admin_root,
            _(f"{waiting_config.organisation} & TiBillet : Demande de création d'un nouvel espace. Action d'admin ROOT demandée"),
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
                f"Rapport de vente TiBillet - {configuration.organisation}",
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
        if not context:
            context = {
                'username': 'UserTest',
                'now': timezone.now(),
                'title': 'Titre',
                'objet': "Objet",
                'sub_title': "sub titre",
                'main_text': "Ceci est le texte principal du mail.",
                'main_text_2': "Si vous pensez que cette demande est main_text_2, vous n'avez rien a faire de plus :)",
                'main_text_3': "Dans le cas contraire, vous pouvez main_text_3. Merci de contacter l'équipe d'administration via : contact@tibillet.re au moindre doute.",
                'table_info': {
                    'ligne 1': 'ligne 1',
                    'ligne 2': 'ligne 2',
                    'ligne 3': 'ligne 3',
                    'ligne 4': 'ligne 4',
                },
                'button_color': "#E8423FFF",
                'button': {
                    'text': 'UN BOUTON',
                    'url': f'https://perdu.com'
                },
                'next_text_1': "Si vous recevez cet email par erreur, merci de contacter l'équipe de TiBillet",
                'next_text_2': "next_text_2",
                'end_text': 'A bientôt, et bon voyage',
                'signature': "Marvin, le robot de TiBillet",
            }

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
    reservation = Reservation.objects.get(pk=reservation_uuid)

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
        configuration = Configuration.get_solo()
        # TODO: remplacer par un choix de champs sur l'admin
        return_body = {
            "object": "membership",
            "pk": str(membership.pk),
            "uuid": f"{membership.uuid}",
            "state": str(membership.status),
            "datetime": str(membership.date_added),
            "email": str(membership.email()),
            "first_name": str(membership.first_name),
            "last_name": str(membership.last_name),
            "pseudo": str(membership.pseudo),
            "price": str(membership.price_name()),
            # "user_id": str(membership.user.id), # Utile ?
            "organisation": f"{configuration.organisation}",
            "organisation_id": f"{configuration.uuid}",
        }

        # Si plusieurs webhook :
        for webhook in webhooks:
            try:
                response = requests.request("POST", webhook.url, json=return_body, timeout=2,
                                            verify=bool(not settings.DEBUG))
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
def send_to_ghost(membership_pk):
    ghost_config = GhostConfig.get_solo()
    ghost_url = ghost_config.ghost_url
    ghost_key = ghost_config.get_api_key()

    if ghost_url and ghost_key:
        membership = Membership.objects.get(pk=membership_pk) #TODO: parfois ça crash, Celery n'a pas le membership

        # Email du compte :
        user = membership.user
        email = user.email
        name = f"{membership.first_name.capitalize()} {membership.last_name.capitalize()}"

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
                            "name": name,
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
                else:
                    logger.error(f"Erreur lors de la création du nouveau membre : {response.text}")
            else:
                # Afficher la liste des membres
                logger.info(f"Le membre {email} existe déja dans : {members}")
        else:
            logger.error(f"Erreur lors de la récupération des membres : {response.text}")

        # On met à jour les logs pour debug
        try:
            ghost_config.ghost_last_log = f"{timezone.now()} : {response.text}"
            ghost_config.save()
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du log : {e}")


# @app.task
@shared_task(bind=True, max_retries=20)
def celery_post_request(self, url, headers, data):
    # Le max de temps entre deux retries : 24 heures
    MAX_RETRY_TIME = 86400  # 24 * 60 * 60 seconds = 24 h
    try:
        logger.info(f"start celery_post_request to {url}")
        response = requests.post(
            f'{url}',
            headers=headers,
            data=data,
            verify=bool(not settings.DEBUG),
            timeout=2,
        )
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


@app.task
def test_logger():
    logger.debug(f"{timezone.now()} debug")
    logger.info(f"{timezone.now()} info")
    logger.warning(f"{timezone.now()} warning")
    logger.error(f"{timezone.now()} error")
