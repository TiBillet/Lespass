# import base64
import json
import os
import random
import smtplib
from io import BytesIO

import requests
import segno
import barcode
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator

from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string, get_template
from django.utils import timezone

from AuthBillet.models import TibilletUser, TerminalPairingToken
from BaseBillet.models import Reservation, Ticket, Configuration
from TiBillet.celery import app

from mailjet_rest import Client

import logging

from TiBillet.settings import DEBUG

logger = logging.getLogger(__name__)


# from celery.utils.log import get_task_logger
# logger = get_task_logger(__name__)
def encode_uid(pk):
    return force_str(urlsafe_base64_encode(force_bytes(pk)))


class CeleryMailerClass():

    def __init__(self,
                 email: str,
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

        if template and context:
            self.html = render_to_string(template, context=context)

    def config_valid(self):
        EMAIL_HOST = os.environ.get('EMAIL_HOST')
        EMAIL_PORT = os.environ.get('EMAIL_PORT')
        EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
        EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')

        # Try except un peu degueulasse causé par l'envoie de task
        # depuis le tenant public pour l'envoi du mail d'appairage
        try:
            self.return_email = Configuration.get_solo().email
            assert self.return_email
        except Exception as e:
            logger.info(f'  WORKDER CELERY : self.return_email {e}')
            self.return_email = "contact@tibillet.re"

        if all([
            EMAIL_HOST,
            EMAIL_PORT,
            EMAIL_HOST_USER,
            EMAIL_HOST_PASSWORD,
            self.return_email,
        ]):
            return True
        else:
            return False

    def send(self):
        if self.html and self.config_valid():
            logger.info(f'  WORKDER CELERY : send_mail')
            mail = EmailMultiAlternatives(
                self.title,
                self.text,
                self.return_email,
                [self.email, ],
            )
            mail.attach_alternative(self.html, "text/html")

            if self.attached_files:
                for filename, file in self.attached_files.items():
                    mail.attach(filename, file, 'application/pdf')

            mail_return = mail.send(fail_silently=False)

            if mail_return == 1:
                self.sended = True
                logger.info(f'      WORKDER CELERY mail envoyé : {mail_return} - {self.email}')
            else:
                logger.error(f'     WORKDER CELERY mail non envoyé : {mail_return} - {self.email}')

            return mail_return
        else:
            logger.error(f'Pas de contenu HTML ou de configuration email valide')
            raise ValueError('Pas de contenu HTML ou de configuration email valide')


class MailJetSendator():
    def __init__(self,
                 email: str,
                 template: None,
                 context=None,
                 attached_files=None,
                 ):

        self.template = template
        self.email = email

        self.context = context
        self.attached_files = attached_files
        self.sended = None

    def config_valid(self):
        api_key = os.environ['MAILJET_APIKEY']
        api_secret = os.environ['MAILJET_SECRET']

        # Try except un peu degueulasse causé par l'envoie de task
        # depuis le tenant public pour l'envoi du mail d'appairage
        try:
            self.return_email = Configuration.get_solo().email
            assert self.return_email
        except Exception as e:
            logger.info(f'  WORKDER CELERY : self.return_email {e}')
            self.return_email = "contact@tibillet.re"

        if all([api_key,
                api_secret,
                self.template,
                self.email,
                ]):

            self.mailjet = Client(auth=(api_key, api_secret), version='v3.1')
            return True
        else:
            return False

    def send(self):
        if self.config_valid():

            data = {
                'Messages': [
                    {
                        "From": {
                            "Email": "contact@tibillet.re",
                            "Name": "TiBillet.re"
                        },
                        "To": [
                            {
                                "Email": f"{self.email}",
                                "Name": f"{self.email}"
                            }
                        ],
                        "TemplateID": self.template,
                        "TemplateLanguage": True,
                        "Subject": "{{var:place:""}} : Confirmez votre e-mail",
                        "Variables": self.context
                    }
                ]
            }
            result = self.mailjet.send.create(data=data)
            logger.info(result.status_code)
            logger.info(result.json())


def create_ticket_pdf(ticket: Ticket):
    # logger_weasy = logging.getLogger("weasyprint")
    # logger_weasy.addHandler(logging.NullHandler())
    # logger_weasy.setLevel(50)  # Only show errors, use 50
    #
    # PROGRESS_LOGGER = logging.getLogger('weasyprint.progress')
    # PROGRESS_LOGGER.addHandler(logging.NullHandler())
    # PROGRESS_LOGGER.setLevel(50)  # Only show errors, use 50

    qr = segno.make(f"{ticket.uuid}", micro=False)

    buffer_svg = BytesIO()
    qr.save(buffer_svg, kind='svg', scale=8)

    CODE128 = barcode.get_barcode_class('code128')
    bar_svg = BytesIO()

    bar_secret = encode_uid(f"{ticket.uuid}".split('-')[4])

    bar = CODE128(f"{bar_secret}")
    options = {
        'module_height': 30,
        'module_width': 0.6,
        'font_size': 10,
    }
    bar.write(bar_svg, options=options)

    context = {
        'ticket': ticket,
        'config': Configuration.get_solo(),
        'img_svg': buffer_svg.getvalue().decode('utf-8'),
        'bar_svg': bar_svg.getvalue().decode('utf-8'),
        # 'bar_svg64': base64.b64encode(bar_svg.getvalue()).decode('utf-8'),
    }

    # template_name = 'report/report.html'
    template_name = 'ticket/ticket.html'
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
def connexion_celery_mailer(user_email, base_url, subject=None):
    """

    :param subject: Sujet de l'email
    :type user_email: str
    :type url: str
    :type tenant_name: str

    """
    logger.info(f'WORKDER CELERY app.task connexion_celery_mailer : {user_email}')
    config = Configuration.get_solo()
    User = get_user_model()
    user = User.objects.get(email=user_email)

    uid = encode_uid(user.pk)
    token = default_token_generator.make_token(user)
    connexion_url = f"{base_url}/emailconfirmation/{uid}/{token}"

    # Moteur MailSend
    if config.activate_mailjet:
        context = {
            "confirmation_link": f"{connexion_url}",
            "place": f"{config.organisation}"
        }
        template = config.email_confirm_template

        mail = MailJetSendator(
            email=user.email,
            template=template,
            context=context
        )
        try:
            mail.send()
            logger.info(f"mail.sended : {mail.sended}")

        except Exception as e:
            logger.error(f"{timezone.now()} Erreur envoie de mail pour connexion {user.email} : {e}")
            raise Exception


    # Internal SMTP and html template
    else:
        if subject is None:
            subject = f"{config.organisation} : Confirmez votre email et connectez vous !"

        try:
            mail = CeleryMailerClass(
                user.email,
                subject,
                template='mails/connexion.html',
                context={
                    'config': config,
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
                user.is_active = False
                user.email_error = True
                user.save()

        except Exception as e:
            logger.error(f"{timezone.now()} Erreur envoie de mail pour connexion {user.email} : {e}")
            raise Exception


@app.task
def terminal_pairing_celery_mailer(term_user_email, subject=None):
    """

    :param subject: Sujet de l'email
    :type user_email: str
    :type url: str
    :type tenant_name: str

    """
    logger.info(f'WORKDER CELERY app.task terminal_pairing_celery_mailer : {term_user_email}')
    User = get_user_model()
    terminal_user = User.objects.get(email=term_user_email, espece=TibilletUser.TYPE_TERM)
    user_parent = terminal_user.user_parent()

    token = TerminalPairingToken.objects.create(user=terminal_user, token=random.randint(100000, 999999))
    logger.info(f'WORKDER CELERY app.task terminal_pairing_celery_mailer token: {token.token}')

    if subject is None:
        subject = f"Appairage du terminal {terminal_user.terminal_uuid} "

    try:
        mail = CeleryMailerClass(
            user_parent.email,
            subject,
            template='mails/pairing_terminal.html',
            context={
                'small_token': token.token,
                'terminal_user': terminal_user
            },
        )
        try:
            mail.send()
            logger.info(f"mail.sended : {mail.sended}")

        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"ERROR {timezone.now()} Erreur envoie de mail pour appairage {user_parent.email} : {e}")
            logger.error(f"mail.sended : {mail.sended}")
            terminal_user.is_active = False
            terminal_user.email_error = True
            terminal_user.save()

    except Exception as e:
        logger.error(f"{timezone.now()} Erreur envoie de mail pour appairage {user_parent.email} : {e}")
        raise Exception


@app.task
def ticket_celery_mailer(reservation_uuid: str):
    logger.info(f'      WORKDER CELERY app.task ticket_celery_mailer : {reservation_uuid}')
    config = Configuration.get_solo()
    reservation = Reservation.objects.get(pk=reservation_uuid)

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
                template='mails/buy_confirmation.html',
                context={
                    'config': config,
                    'reservation': reservation,
                },
                attached_files=attached_files,
            )
            try:
                mail.send()
                logger.info(f"mail.sended : {mail.sended}")

                if mail.sended:
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
def test_logger():
    logger.debug(f"{timezone.now()} debug")
    logger.info(f"{timezone.now()} info")
    logger.warning(f"{timezone.now()} warning")
    logger.error(f"{timezone.now()} error")
