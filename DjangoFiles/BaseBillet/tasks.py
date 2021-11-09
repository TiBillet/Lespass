# import base64
import os
import smtplib
from io import BytesIO
import segno
import barcode
from djoser import utils

from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string, get_template
from django.utils import timezone
from BaseBillet.models import Configuration, Reservation, Ticket
from TiBillet.celery import app

import logging
logger = logging.getLogger(__name__)
# from celery.utils.log import get_task_logger
# logger = get_task_logger(__name__)


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
        self.config = Configuration.get_solo()
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

        if EMAIL_HOST and EMAIL_PORT and EMAIL_HOST_USER and EMAIL_HOST_PASSWORD and self.config.email:
            return True
        else:
            return False

    def send(self):
        if self.html and self.config_valid():
            logger.info(f'  WORKDER CELERY : send_mail')
            mail = EmailMultiAlternatives(
                self.title,
                self.text,
                self.config.email,
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



def create_ticket_pdf(ticket: Ticket):
    qr = segno.make(f"{ticket.uuid}", micro=False)

    buffer_svg = BytesIO()
    qr.save(buffer_svg, kind='svg', scale=8)

    CODE128 = barcode.get_barcode_class('code128')
    bar_svg = BytesIO()
    bar_secret = utils.encode_uid(f"{ticket.uuid}".split('-')[4])

    bar = CODE128(f"{bar_secret}")
    options = {
        'module_height': 30,
        'module_width': 0.6,
        'font_size': 10,
    }
    bar.write(bar_svg, options = options)

    context = {
        'ticket': ticket,
        'config': Configuration.get_solo(),
        'img_svg': buffer_svg.getvalue().decode('utf-8'),
        'bar_svg': bar_svg.getvalue().decode('utf-8'),
        # 'bar_svg64': base64.b64encode(bar_svg.getvalue()).decode('utf-8'),
    }

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
def ticket_celery_mailer(reservation_uuid: str):
    logger.info(f'      WORKDER CELERY app.task ticket_celery_mailer : {reservation_uuid}')
    config = Configuration.get_solo()
    reservation = Reservation.objects.get(pk=reservation_uuid)

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
        try :
            mail.send()
            logger.info(f"mail.sended : {mail.sended}")

            if mail.sended :
                reservation.mail_send = True
                reservation.status = Reservation.VALID
                reservation.save()

        except smtplib.SMTPRecipientsRefused as e:

            logger.error(f"ERROR {timezone.now()} Erreur envoie de mail pour reservation {reservation} : {e}")
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