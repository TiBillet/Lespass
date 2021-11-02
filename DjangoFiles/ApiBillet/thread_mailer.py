import os
import threading
from django.core.mail import send_mail, EmailMessage, EmailMultiAlternatives
from django.db import connection
from django.template.loader import render_to_string
from django.utils import timezone
from stripe.http_client import requests
from weasyprint import HTML
from BaseBillet.models import Configuration, Reservation, Ticket

import logging

logger = logging.getLogger(__name__)

'''
from ApiBillet.thread_mailer import ThreadMaileur
config = Configuration.get_solo()
context = {'config': config, }
mail = ThreadMaileur('jturbeaux@pm.me', "Vos Billets", template='mails/ticket.html', context=context)
mail.send_with_tread()
'''


class ThreadMaileur():

    def __init__(self,
                 email: str,
                 title: str,
                 text=None,
                 html=None,
                 template=None,
                 context=None,
                 urls_for_attached_files=None,
                 ):

        self.title = title
        self.email = email
        self.text = text
        self.html = html
        self.config = Configuration.get_solo()
        self.context = context
        self.urls_for_attached_files = urls_for_attached_files

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

            if self.urls_for_attached_files:
                for filename, url in self.urls_for_attached_files.items():
                    response = requests.get(url)
                    if response.status_code == 200:
                        mail.attach(filename, response.content, 'application/pdf')

            mail_return = mail.send(fail_silently=False)

            if mail_return == 1:
                logger.info(f'      mail envoyé : {mail_return} - {self.email}')
            else:
                logger.error(f'     mail non envoyé : {mail_return} - {self.email}')
            return mail
        else:
            logger.error(f'Pas de contenu HTML ou de configuration email valide')
            raise ValueError('Pas de contenu HTML ou de configuration email valide')

    def send_with_tread(self):

        # self.send()
        logger.info(f'{timezone.now()} on lance le thread email {self.email}')
        thread_email = threading.Thread(target=self.send)
        thread_email.start()
        logger.info(f'{timezone.now()} Thread email lancé')
