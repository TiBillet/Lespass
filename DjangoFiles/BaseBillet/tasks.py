# import base64
import datetime
import json
import jwt
import logging
import os
import random
import smtplib
from io import BytesIO

import barcode
import requests
import segno
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.db import connection, IntegrityError
from django.template.loader import render_to_string, get_template
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode
from django.utils.text import slugify
from django_tenants.utils import tenant_context, schema_context
from requests.exceptions import ConnectionError
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration


from AuthBillet.models import TibilletUser, TerminalPairingToken
from BaseBillet.models import Reservation, Ticket, Configuration, Membership, LigneArticle, Webhook, Paiement_stripe, \
    Product
from Customers.models import Client, Domain
from MetaBillet.models import WaitingConfiguration
from TiBillet import settings
from TiBillet.celery import app
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)


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

            # si email retour n'est pas le même nom de domain que le moteur, mail non envoyé.
            assert self.return_email.partition("@")[2] == EMAIL_HOST_USER.partition("@")[2]

        except Exception as e:
            logger.warning(f'  WORKDER CELERY : self.return_email {e}')
            self.return_email = "contact@tibillet.re"

        if all([
            EMAIL_HOST,
            EMAIL_PORT,
            EMAIL_HOST_USER,
            EMAIL_HOST_PASSWORD,
            self.return_email,
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

            logger.info(f'  WORKDER CELERY : send_mail - {self.title}')
            mail = EmailMultiAlternatives(
                self.title,
                self.text,
                self.return_email,
                [self.email, ],
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


def create_invoice_pdf(paiement_stripe: Paiement_stripe):
    config = Configuration.get_solo()
    template_name = 'invoice/invoice.html'
    font_config = FontConfiguration()
    template = get_template(template_name)
    user = paiement_stripe.user
    membership = user.membership.first()

    context = {
        'config': config,
        'paiement': paiement_stripe,
        'membership': membership,
        'email': user.email,
    }
    html = template.render(context)

    css = CSS(string=
              '''
                @font-face {
                  font-family: BeStrong;
                  src: url(file:///DjangoFiles/ApiBillet/templates/invoice/BeStrongRegular.otf);
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


def create_ticket_pdf(ticket: Ticket):
    # logger_weasy = logging.getLogger("weasyprint")
    # logger_weasy.addHandler(logging.NullHandler())
    # logger_weasy.setLevel(50)  # Only show errors, use 50
    #
    # PROGRESS_LOGGER = logging.getLogger('weasyprint.progress')
    # PROGRESS_LOGGER.addHandler(logging.NullHandler())
    # PROGRESS_LOGGER.setLevel(50)  # Only show errors, use 50

    # Pour faire le qrcode
    qr = segno.make(f"{ticket.uuid}", micro=False)
    buffer_svg = BytesIO()
    qr.save(buffer_svg, kind='svg', scale=8)

    # Pour faire le barcode
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

    uid = encode_uid(user.pk)
    token = default_token_generator.make_token(user)
    connexion_url = f"{base_url}/emailconfirmation/{uid}/{token}"

    if connection.tenant.schema_name != "public":
        config = Configuration.get_solo()
        organisation = config.organisation

        img_orga = ""
        if config.img:
            img_orga = config.img.med

        logger.info(f'connection.tenant.schema_name != "public" : {connection.tenant.schema_name}')
        logger.info(f'    {organisation}')
        logger.info(f'    {img_orga}')
    else:
        organisation = "TiBillet"
        img_orga = "Logo_Tibillet_Noir_Ombre_600px.png"
        meta = Client.objects.filter(categorie=Client.META).first()
        meta_domain = f"https://{meta.get_primary_domain().domain}"
        connexion_url = f"{meta_domain}/emailconfirmation/{uid}/{token}"
        logger.info(f'connection.tenant.schema_name == "public" : {connection.tenant.schema_name}')

    # Internal SMTP and html template
    if title is None:
        title = f"{organisation} : Confirmez votre email et connectez vous !"
    if template is None:
        template = 'mails/connexion.html'

    logger.info(f'    title : {title}')

    try:
        mail = CeleryMailerClass(
            user.email,
            title,
            template=template,
            context={
                'organisation': organisation,
                'url_image': img_orga,
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


"""
@app.task
def create_tenant(waiting_configuration_uuid):
    futur_conf = WaitingConfiguration.objects.get(pk=waiting_configuration_uuid)

    slug = slugify(futur_conf.get('organisation'))
    with schema_context('public'):
        try:
            tenant, created = Client.objects.get_or_create(
                schema_name=slug,
                name=futur_conf.get('organisation'),
                categorie=futur_conf.categorie,
            )

            if not created:
                logger.error(f"{futur_conf.get('organisation')} existe déja")
                raise IntegrityError(f"{futur_conf.get('organisation')} existe déja")

            domain, created = Domain.objects.get_or_create(
                domain=f"{slug}.{os.getenv('DOMAIN')}",
                tenant=tenant,
                is_primary=True
            )

        except IntegrityError as e:
            logger.error(e)
            raise IntegrityError(e)
        except Exception as e:
            logger.error(e)
            raise Exception(e)

    with tenant_context(tenant):
        rootConf = RootConfiguration.get_solo()
        conf = Configuration.get_solo()
        import ipdb; ipdb.set_trace()

        serializer.update(instance=conf, validated_data=futur_conf)

        conf.slug = slug
        user: TibilletUser = request.user
        conf.email = user.email

        if getattr(serializer, 'info_stripe', None):
            info_stripe = serializer.info_stripe
            conf.site_web = info_stripe.business_profile.url
            conf.phone = info_stripe.business_profile.support_phone

            conf.stripe_mode_test = rootConf.stripe_mode_test
            if rootConf.stripe_mode_test:
                conf.stripe_connect_account_test = info_stripe.id
            else:
                conf.stripe_connect_account = info_stripe.id

        if getattr(serializer, 'img_img', None):
            conf.img.save(serializer.img_name, serializer.img_img.fp)
        if getattr(serializer, 'logo_img', None):
            conf.logo.save(serializer.logo_name, serializer.logo_img.fp)

        conf.save()
        conf.check_serveur_cashless()

        staff_group = Group.objects.get(name="staff")

        user.client_admin.add(tenant)
        user.is_staff = True
        user.groups.add(staff_group)
        user.save()

        place_serialized = ConfigurationSerializer(Configuration.get_solo(), context={'request': request})
        place_serialized_with_uuid = {'uuid': f"{tenant.uuid}"}
        place_serialized_with_uuid.update(place_serialized.data)

    return Response(place_serialized_with_uuid, status=status.HTTP_201_CREATED)

"""


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
def send_email_generique(context: dict = None, email: str = None, attached_files=None):
    template_name = "mails/email_generique.html"
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
def ticket_celery_mailer(reservation_uuid: str, base_url):
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
                    'base_url': base_url
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
def send_membership_to_cashless(data):
    configuration = Configuration.get_solo()
    if not configuration.server_cashless or not configuration.key_cashless:
        logger.error(f'Pas de configuration cashless')
        raise Exception(f'Fonction send_membership_to_cashless : Pas de configuration cashless')

    ligne_article = LigneArticle.objects.get(pk=data.get('ligne_article_pk'))
    user = ligne_article.paiement_stripe.user

    price_obj = ligne_article.pricesold.price
    price_decimal = ligne_article.pricesold.prix

    # Si c'est un price avec un don intégré (comme une adhésion récurente)
    # On garde 1€ pour l'instance
    if ligne_article.pricesold.gift:
        price_decimal += -1

    membre = Membership.objects.get(user=user, price=price_obj)

    if not membre.first_contribution:
        membre.first_contribution = timezone.now().date()

    membre.last_contribution = timezone.now().date()
    membre.contribution_value = price_decimal
    membre.save()

    data = {
        "email": membre.email(),
        "adhesion": price_decimal,
        "uuid_commande": ligne_article.paiement_stripe.uuid,
        "first_name": membre.first_name,
        "last_name": membre.last_name,
        "phone": membre.phone,
        "postal_code": membre.postal_code,
        "birth_date": membre.birth_date,
    }

    try:

        sess = requests.Session()
        r = sess.post(
            f'{configuration.server_cashless}/api/membership',
            headers={
                'Authorization': f'Api-Key {configuration.key_cashless}'
            },
            data=data,
            verify=bool(not settings.DEBUG),
        )

        sess.close()
        logger.info(
            f"        demande au serveur cashless pour {data}. réponse : {r.status_code} ")

        if r.status_code in [200, 201, 202]:
            ligne_article.status = LigneArticle.VALID
        else:
            logger.error(
                f"erreur réponse serveur cashless {r.status_code} {r.text}")

    except ConnectionError as e:
        logger.error(
            f"ConnectionError serveur cashless {configuration.server_cashless} : {e}")

    except Exception as e:
        raise Exception(f'Exception request send_membership_to_cashless {type(e)} : {e} ')


@app.task
def webhook_reservation(reservation_pk):
    logger.info(f"webhook_reservation : {reservation_pk} {timezone.now()} info")
    webhooks = Webhook.objects.filter(event=Webhook.RESERVATION_V)
    if webhooks.count() > 0:
        reservation = Reservation.objects.get(pk=reservation_pk)
        json = {
            "object": "reservation",
            "uuid": f"{reservation.uuid}",
            "state": f"{reservation.status}",
            "datetime": f"{reservation.datetime}",
        }

        for webhook in webhooks:
            try:
                response = requests.request("POST", webhook.url, data=json, timeout=2)
                webhook.last_response = f"{timezone.now()} - status code {response.status_code} - {response.text}"
            except Exception as e:
                logger.error(f"webhook_reservation ERROR : {reservation_pk} {timezone.now()} {e}")
                webhook.last_response = f"{timezone.now()} - {e}"
            webhook.save()


@app.task
def send_to_ghost(membership_pk):
    membership = Membership.objects.get(pk=membership_pk)

    # Email du compte :
    user = membership.user
    email = user.email
    name = f"{membership.first_name} {membership.last_name}"

    # Si tu as besoin du produit adhésion, tu peux utiliser les deux variables ci-dessous.
    # Le model est BaseBillet/models.py
    # product: Product = trigger.ligne_article.pricesold.productsold.product

    # Et ici, tu as les cred' ghost à entrer dans l'admin.
    config = Configuration.get_solo()
    ghost_url = config.ghost_url
    ghost_key = config.ghost_key

    if ghost_url and ghost_key and email and name:
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
        if response.status_code == 200:
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
                response = requests.post(ghost_url + "/ghost/api/admin/members/", json=member_data, headers=headers)

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
            config.ghost_last_log = f"{timezone.now()} : {response.text}"
            config.save()
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du log : {e}")


@app.task
def test_logger():
    logger.debug(f"{timezone.now()} debug")
    logger.info(f"{timezone.now()} info")
    logger.warning(f"{timezone.now()} warning")
    logger.error(f"{timezone.now()} error")
