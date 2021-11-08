import os
from io import BytesIO
import base64
import segno

from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string, get_template
from django.utils import timezone
from BaseBillet.models import Configuration, Reservation, Ticket
from TiBillet.celery import app

import logging

logger = logging.getLogger(__name__)


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
            logger.info(f'  send_mail')
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
                logger.info(f'      mail envoyé : {mail_return} - {self.email}')
            else:
                logger.error(f'     mail non envoyé : {mail_return} - {self.email}')
            return mail_return
        else:
            logger.error(f'Pas de contenu HTML ou de configuration email valide')
            raise ValueError('Pas de contenu HTML ou de configuration email valide')



def create_ticket_pdf(ticket: Ticket):
    qr = segno.make(f'{ticket.uuid}')

    buffer_png = BytesIO()
    qr.save(buffer_png, kind='PNG', scale=15)
    img_str = base64.b64encode(buffer_png.getvalue()).decode('utf-8')

    buffer_svg = BytesIO()
    qr.save(buffer_svg, kind='svg', scale=10)


    context = {
        'ticket': ticket,
        'config': Configuration.get_solo(),
        'img_str': base64.b64encode(buffer_png.getvalue()).decode('utf-8'),
        'img_svg': buffer_svg.getvalue().decode('utf-8'),
        'img_svg64': base64.b64encode(buffer_svg.getvalue()).decode('utf-8'),
    }

    template_name = 'ticket/ticket.html'
    # template_name = 'ticket/qrtest.html'
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
        font_config=font_config
    )

    return pdf_binary


@app.task
def ticket_celery_mailer(reservation_uuid: str):
    '''
    for ticket in reservation.tickets.filter(status=Ticket.NOT_SCANNED):
        response = requests.get(ticket.pdf_url())
        print(response.status_code)
    '''

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
        mail.send()
        return True
    except Exception as e:
        logger.error(f"{timezone.now()} Erreur envoie de mail pour reservation {reservation} : {e}")
        raise Exception
