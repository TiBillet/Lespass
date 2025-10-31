import json
import logging
import os
import re
import uuid
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import segno
import stripe
from django.contrib import messages
from django.contrib.auth import logout, login
from django.contrib.messages import MessageFailure
from django.core import signing
from django.core.cache import cache
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.core.signing import TimestampSigner
from django.db import connection
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, HttpRequest, Http404, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.encoding import force_str, force_bytes
from django.utils.html import format_html
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import requires_csrf_token
from django.views.decorators.http import require_GET
from django_htmx.http import HttpResponseClientRedirect
from django_tenants.utils import tenant_context
from rest_framework import viewsets, permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ApiBillet.permissions import TenantAdminPermission
from AuthBillet.models import TibilletUser, Wallet, HumanUser
from AuthBillet.serializers import MeSerializer
from AuthBillet.utils import get_or_create_user
from AuthBillet.views import activate
from BaseBillet.models import Configuration, Ticket, Product, Event, Paiement_stripe, Membership, Reservation, \
    FormbricksConfig, FormbricksForms, FederatedPlace, Carrousel, LigneArticle, PriceSold, \
    Price, ProductSold, PaymentMethod
from BaseBillet.tasks import create_membership_invoice_pdf, send_membership_invoice_to_email, new_tenant_mailer, \
    contact_mailer, new_tenant_after_stripe_mailer, send_to_ghost_email, send_sale_to_laboutik, \
    send_payment_success_admin, send_payment_success_user, send_reservation_cancellation_user, \
    send_ticket_cancellation_user, send_email_generique, \
    send_membership_pending_admin, send_membership_pending_user, send_membership_payment_link_user
from BaseBillet.validators import LoginEmailValidator, MembershipValidator, LinkQrCodeValidator, TenantCreateValidator, \
    ReservationValidator, ContactValidator, QrCodeScanPayNfcValidator
from Customers.models import Client, Domain
from MetaBillet.models import WaitingConfiguration
from TiBillet import settings
from crowds.models import CrowdConfig, Initiative
from fedow_connect.fedow_api import FedowAPI
from fedow_connect.models import FedowConfig
from fedow_connect.utils import dround
from fedow_connect.validators import TransactionSimpleValidator
from fedow_public.models import AssetFedowPublic
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)

"""
class SmallAnonRateThrottle(UserRateThrottle):
    # Un throttle pour 10 requetes par jours uniquement
    scope = 'smallanon'
"""


@requires_csrf_token
def handler500(request, exception=None):
    """
    Custom 500 error handler that passes the exception to the template.
    """
    import sys
    exc_type, exc_value, exc_traceback = sys.exc_info()

    # Use the passed exception if available, otherwise use the one from sys.exc_info()
    exception_to_use = exception if exception else exc_value

    context = {
        'exception': str(exception_to_use) if exception_to_use else None,
        'type_exception': type(exception_to_use).__name__ if exception_to_use else None,
    }
    logger.info(context)
    return render(request, '500.html', context, status=500)


def encode_uid(pk):
    return force_str(urlsafe_base64_encode(force_bytes(pk)))


def get_context(request):

    context_cached = cache.get(f'get_context_{connection.tenant.uuid}')
    if context_cached:
        return context_cached

    config = Configuration.get_solo()
    crowd_config = CrowdConfig.get_solo()
    # logger.debug("request.htmx") if request.htmx else None
    base_template = "reunion/headless.html" if request.htmx else "reunion/base.html"
    serialized_user = MeSerializer(request.user).data if request.user.is_authenticated else None

    # Le lien "Fédération"
    meta_url = cache.get('meta_url')
    if not meta_url:
        meta = Client.objects.filter(categorie=Client.META)[0]
        meta_url = f"https://{meta.get_primary_domain().domain}"
        cache.set('meta_url', meta_url, 3600 * 24)

    # Formbricks existe ?
    formbricks_config = FormbricksConfig.get_solo()

    context = {
        "base_template": base_template,
        "page": request.GET.get('page', 1),
        "tags": request.GET.getlist('tag'),
        "url_name": request.resolver_match.url_name,
        "user": request.user,
        "profile": serialized_user,
        "config": config,
        "crowd_config": crowd_config,
        "meta_url": meta_url,
        "header": True,
        # "tenant": connection.tenant,
        "formbricks_api_host": formbricks_config.api_host,
        "mode_test": True if os.environ.get('TEST') == '1' else False,
        "carrousel_event_list": Carrousel.objects.filter(on_event_list_page=True).order_by('order'),
        "main_nav": [
            {'name': 'event-list', 'url': '/event/',
             'label': config.event_menu_name if config.event_menu_name else _('Calendar'),
             'icon': 'calendar-date'},
            {'name': 'memberships_mvt', 'url': '/memberships/',
             'label': config.membership_menu_name if config.membership_menu_name else _('Subscriptions'),
             'icon': 'person-badge'},
        ]
    }

    navbar: list = context["main_nav"]
    agenda_federation_active = FederatedPlace.objects.exists()
    asset_federation_active = AssetFedowPublic.objects.filter(federated_with__isnull=False).exists()
    if agenda_federation_active or asset_federation_active:
        navbar.append(
            {'name': 'federation', 'url': '/federation/',
             'label': 'Local network', 'icon': 'diagram-2-fill'}
        )

    if crowd_config.active and Initiative.objects.exists():
        navbar.append(
            {'name': f'crowd-list', 'url': '/crowd/',
             'label': f'{crowd_config.title}', 'icon': 'piggy-bank'}
        )

    cache.set(f'get_context_{connection.tenant.uuid}', context, 10)
    return context


# S'execute juste après un retour Webhook ou redirection une fois le paiement stripe effectué.
# ex : BaseBillet.views.EventMVT.stripe_return
def paiement_stripe_reservation_validator(request, paiement_stripe):
    reservation = paiement_stripe.reservation

    #### PRE CHECK : On vérifie que le paiement n'a pas déja été traité :

    # Le paiement est en cours de traitement,
    # probablement pas le webhook POST qui arrive depuis Stripe avant le GET de redirection de l'user
    if paiement_stripe.traitement_en_cours:
        messages.success(request, _("Payment confirmed. Tickets are being generated and sent to your email."))
        return paiement_stripe

    # Déja été traité et il est en erreur.
    if reservation.status == Reservation.PAID_ERROR:
        messages.error(request, _("Payment rejected."))
        return False

    # Déja traité et validé.
    if (paiement_stripe.status == Paiement_stripe.VALID or
            reservation.status == Reservation.VALID):
        messages.success(request,
                         _('Payment confirmed. Tickets sent to your email. You can also view your tickets through "My account > Bookings".'))
        return paiement_stripe

    #### END PRE CHECK

    # Si c'est une source depuis INVOICE, c'est un paiement récurent automatique.
    # L'object vient d'être créé, on vérifie que la facture stripe est payée et on met en VALID
    # TODO: Que pour les webhook post stripe. A poser dans le model a coté de update_checkout_status ?
    if paiement_stripe.source == Paiement_stripe.INVOICE:
        paiement_stripe.traitement_en_cours = True
        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        invoice = stripe.Invoice.retrieve(
            paiement_stripe.invoice_stripe,
            stripe_account=Configuration.get_solo().get_stripe_connect_account()
        )

        if not invoice.status == 'paid':
            logger.info(
                f"paiement_stripe.source == Paiement_stripe.INVOICE -> stripe invoice : {invoice.status} - paiement : {paiement_stripe.status}")
            messages.error(request, _(f'Stripe invoice : {invoice.status} - payment : {paiement_stripe.status}'))
            return False

        paiement_stripe.status = Paiement_stripe.PAID
        paiement_stripe.last_action = timezone.now()
        paiement_stripe.traitement_en_cours = True
        paiement_stripe.save()

        logger.info("paiement_stripe.source == Paiement_stripe.INVOICE -> Paiement récurent et facture générée.")
        messages.success(request, _("Recurring payment and bill generated."))
        return paiement_stripe

    # C'est un paiement stripe checkout non traité, on tente de le valider
    if paiement_stripe.status != Paiement_stripe.VALID:
        checkout_status = paiement_stripe.update_checkout_status()
        # on vérifie le changement de status
        paiement_stripe.refresh_from_db()

        logger.info("*" * 30)
        logger.info(
            f"{timezone.now()} - paiment_stripe_reservation_validator - checkout_status : {checkout_status}")
        logger.info(
            f"{timezone.now()} - paiment_stripe_reservation_validator - paiement_stripe.save() {paiement_stripe.status}")
        logger.info("*" * 30)

        messages.success(request,
                         _('Payment confirmed. Tickets sent to your email. You can also view your tickets through "My account > Bookings".'))
        return paiement_stripe

    raise Exception('paiment_stripe_reservation_validator : aucune condition remplies ?')


class Ticket_html_view(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk_uuid):
        ticket = get_object_or_404(Ticket, uuid=pk_uuid)
        qr = segno.make(f"{ticket.qrcode()}", micro=False)

        buffer_svg = BytesIO()
        qr.save(buffer_svg, kind="svg", scale=4.5)

        # CODE128 = barcode.get_barcode_class("code128")
        # buffer_barcode_SVG = BytesIO()
        # bar_secret = encode_uid(f"{ticket.uuid}".split("-")[4])
        #
        # bar = CODE128(f"{bar_secret}")
        # options = {
        #     "module_height": 30,
        #     "module_width": 0.6,
        #     "font_size": 10,
        # }
        # bar.write(buffer_barcode_SVG, options=options)

        context = {
            "ticket": ticket,
            "config": Configuration.get_solo(),
            "img_svg": buffer_svg.getvalue().decode("utf-8"),
            # 'img_svg64': base64.b64encode(buffer_svg.getvalue()).decode('utf-8'),
            # "bar_svg": buffer_barcode_SVG.getvalue().decode("utf-8"),
            # 'bar_svg64': base64.b64encode(buffer_barcode_SVG.getvalue()).decode('utf-8'),
        }

        return render(request, "ticket/ticket.html", context=context)
        # return render(request, 'ticket/qrtest.html', context=context)


def test_jinja(request):
    context = {
        "list": [1, 2, 3, 4, 5, 6],
        "var1": "",
        "var2": "",
        "var3": "",
        "var4": "hello",
    }
    return TemplateResponse(request, "htmx/views/test_jinja.html", context=context)


def deconnexion(request):
    # un logout peut-il mal se passer ?
    logout(request)
    messages.add_message(request, messages.SUCCESS, _("Logout successful"))
    return redirect('index')


def connexion(request):
    if request.method == 'POST':
        validator = LoginEmailValidator(data=request.POST)
        if validator.is_valid():
            # Création de l'user et envoie du mail de validation
            email = validator.validated_data['email']
            user = get_or_create_user(email=email, send_mail=True, force_mail=True)
            if not user.wallet:
                fedowAPI = FedowAPI()
                fedowAPI.wallet.get_or_create_wallet(user)
            messages.add_message(request, messages.SUCCESS, _("To access your space, please validate\n"
                                                              "your email address. Don't forget to check your spam!"))

            # On est sur le moteur de démonstration / test
            # Pour les tests fonctionnel, on a besoin de vérifier le token, on le génère ici.
            if settings.TEST:
                token = user.get_connect_token()
                base_url = connection.tenant.get_primary_domain().domain
                connexion_url = f"https://{base_url}/emailconfirmation/{token}"
                messages.add_message(request, messages.INFO, format_html(f"<a href='{connexion_url}'>TEST MODE</a>"))

            return HttpResponseClientRedirect(request.headers['Referer'])

        logger.error(validator.errors)
    messages.add_message(request, messages.WARNING, "Email validation error")
    return redirect('index')


def emailconfirmation(request, token):
    try:
        activate(request, token)
        next_url = request.GET.get('next', None)
        if next_url:
            while next_url.endswith('/'):
                next_url = next_url[:-1]
            # l'url est signé par Django
            next_url = signing.loads(next_url)
            return HttpResponseRedirect(next_url)
        return redirect('index')
    except Exception as e:
        raise Http404("Error on email confirmation")


class ScanQrCode(viewsets.ViewSet):  # /qr
    authentication_classes = [SessionAuthentication, ]

    def retrieve(self, request, pk=None):
        # TODO: Serializer ?
        try:
            qrcode_uuid: uuid.uuid4 = uuid.UUID(pk)
        except ValueError:
            logger.warning("ValueError, not an uuid")
            raise Http404()
        except Exception as e:
            logger.error(e)
            raise e

        # 1) checket fedow 2) checker origin card 3) rediriger vers primary_domain
        # redirection des cartes génériques
        tenant: Client = connection.tenant
        # Besoin d'etre sur un tenant qui a déja échangé avec Fedow
        if tenant.categorie != Client.SALLE_SPECTACLE:
            tenant = Client.objects.filter(categorie=Client.SALLE_SPECTACLE).first()
        with tenant_context(tenant):
            fedowAPI = FedowAPI()
            serialized_qrcode_card = fedowAPI.NFCcard.qr_retrieve(qrcode_uuid)
            if not serialized_qrcode_card:
                raise Http404("Unknow qrcode_uuid")

            lespass_domain = serialized_qrcode_card['origin']['place']['lespass_domain']
            if not lespass_domain:
                raise Http404("Origin error")

            domain = get_object_or_404(Domain, domain=lespass_domain)
            primary_domain = domain.tenant.get_primary_domain()
            if not primary_domain.domain in request.build_absolute_uri():
                return HttpResponseRedirect(f"https://{primary_domain}/qr/{qrcode_uuid}/")

            if not serialized_qrcode_card:
                logger.warning(f"serialized_qrcode_card {qrcode_uuid} non valide")
                raise Http404()

            # La carte n'a pas d'user, on redirige vers la page de renseignement d'user
            if serialized_qrcode_card['is_wallet_ephemere']:
                logger.info("Wallet ephemere, on demande le mail")
                template_context = get_context(request)
                template_context['qrcode_uuid'] = qrcode_uuid
                template_context['base_template'] = 'reunion/blank_base.html'
                # Logout au cas où on scanne les cartes à la suite.
                logout(request)
                return render(request, "reunion/views/register.html", context=template_context)

            # Si wallet non ephemere, alors on a un user :
            wallet = Wallet.objects.get(uuid=serialized_qrcode_card['wallet_uuid'])

            user: TibilletUser = wallet.user
            user.is_active = True
            user.save()

            # Parti pris : On logue l'user lorsqu'il scanne sa carte.
            login(request, user)

            # Pour les tests :
            # On est sur le moteur de démonstration / test
            # Pour les tests fonctionnel, on a besoin de vérifier le token, on le génère ici.
            if settings.TEST:
                token = user.get_connect_token()
                base_url = connection.tenant.get_primary_domain().domain
                connexion_url = f"https://{base_url}/emailconfirmation/{token}"
                messages.add_message(request, messages.INFO, format_html(f"<a href='{connexion_url}'>TEST MODE</a>"))

            return redirect("/my_account")

    # @action(detail=False, methods=['POST'])
    # def link_with_email_confirm(self, request):
    # Si l'user a déja une carte

    @action(detail=False, methods=['POST'])
    def link(self, request):
        # data=request.POST.dict() in the controler for boolean
        # logger.info(request.POST.dict())
        # import ipdb; ipdb.set_trace()
        # data=request.POST.dict() in the controler for boolean
        validator = LinkQrCodeValidator(data=request.POST.dict())
        if not validator.is_valid():
            for error in validator.errors:
                logger.error(f"{error} : {validator.errors[error][0]}")
                messages.add_message(request, messages.ERROR, f"{error} : {validator.errors[error][0]}")
            return HttpResponseClientRedirect(request.headers['Referer'])

        # Le mail est envoyé
        email = validator.validated_data['email']
        user: TibilletUser = get_or_create_user(email, force_mail=True)
        if validator.validated_data.get('newsletter'):
            send_to_ghost_email.delay(email)

        # import ipdb; ipdb.set_trace()
        if not user:
            # Le mail n'est pas validé par django (example.org?)
            messages.add_message(request, messages.ERROR, f"{_('Invalid email')}")
            logger.error("email validé par validateur DRF mais pas par get_or_create_user "
                         "-> email de confirmation a renvoyé une erreur")
            return HttpResponseClientRedirect(request.headers['Referer'])

        if validator.data.get('lastname') and not user.last_name:
            user.last_name = validator.data.get('lastname')
        if validator.data.get('firstname') and not user.first_name:
            user.first_name = validator.data.get('firstname')
        if validator.data.get('newsletter'):
            send_to_ghost_email.delay(email, f"{user.first_name} {user.last_name}")
        # On retire le mail valid : impose la vérification du mail en cas de nouvelle carte
        user.email_valid = False
        user.save()

        fedowAPI = FedowAPI()
        wallet, created = fedowAPI.wallet.get_or_create_wallet(user)
        # Si l'user possède déja un wallet et une carte référencée dans Fedow,

        # il ne peut pas avoir de deuxièmes cartes
        # Evite le vol de carte : si je connais l'email d'une personne,
        # je peux avoir son wallet juste en mettant son email sur une nouvelle carte…
        # Fonctionne de concert avec la vérification chez Fedow : fedow_core.views.linkwallet_cardqrcode : 385
        if not created:
            logger.info(f"wallet {wallet} non created after get_or_create_wallet")
            retrieve_wallet = fedowAPI.wallet.retrieve_by_signature(user)
            if retrieve_wallet.validated_data['has_user_card']:
                messages.add_message(request, messages.ERROR,
                                     _("You seem to already have a TiBillet card linked to your wallet. "
                                       "Please revoke it first in your profile area to link a new one."))
                return HttpResponseClientRedirect(request.headers['Referer'])

        # Opération de fusion entre la carte liée au qrcode et le wallet de l'user :
        qrcode_uuid = validator.validated_data['qrcode_uuid']
        linked_serialized_card = fedowAPI.NFCcard.linkwallet_cardqrcode(user=user, qrcode_uuid=qrcode_uuid)
        if not linked_serialized_card:
            messages.add_message(request, messages.ERROR, _("Not valid"))

        # On retourne sur la page GET /qr/
        # Qui redirigera si besoin et affichera l'erreur
        logger.info(
            f"SCAN QRCODE LINK : wallet : {wallet}, user : {wallet.user}, card qrcode : {linked_serialized_card['qrcode_uuid']} ")

        # On check si des adhésions n'ont pas été faites avec la carte en wallet ephemère
        card_number = linked_serialized_card.get('number_printed')
        if card_number:
            for membership in Membership.objects.filter(
                    user__isnull=True,
                    card_number=card_number):
                membership.user = user
                membership.first_name = user.first_name
                membership.last_name = user.last_name
                membership.save()

        return HttpResponseClientRedirect(request.headers['Referer'])

    def get_permissions(self):
        permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]


class TiBilletLogin(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]

    @action(detail=False, methods=['GET', 'POST'], permission_classes=[permissions.AllowAny])
    def login_fullpage(self, request):
        template_context = get_context(request)
        next_url = request.GET.get('next', None)
        logger.info(f"login_fullpage next_url : {next_url}")
        if request.method == 'GET':  # Render email form or confirmation page
            # Optional next parameter sended in the email confirm button
            if next_url:
                template_context['next'] = next_url
            if request.htmx:
                return render(request, "reunion/views/login/partials/fullpage_inner.html", context=template_context)
            return render(request, "reunion/views/login/fullpage.html", context=template_context)

        # POST: email submitted
        validator = LoginEmailValidator(data=request.POST)
        if not validator.is_valid():
            logger.error(validator.errors)
            template_context['errors'] = validator.errors
            template_context['email'] = request.POST.get('email', '')
            if request.htmx:
                return render(request, "reunion/views/login/partials/fullpage_inner.html", context=template_context)
            return render(request, "reunion/views/login/fullpage.html", context=template_context)

        email = validator.validated_data['email']
        user = get_or_create_user(email=email, send_mail=True, force_mail=True, next_url=next_url)

        # On success: swap only main content for HTMX and push URL
        return render(request, "reunion/views/login/partials/confirmation_inner.html", context=template_context)

    @action(detail=True, methods=['GET'], permission_classes=[permissions.IsAuthenticated])
    def redirect_session_to_another_tenant(self, request, pk):
        """
        Cross-tenant session handoff.
        pk is a base64url-encoded absolute URL (the original QR code URL on another tenant).
        We verify the current session is authenticated, ensure the target domain exists in our multi-tenant Domains,
        then redirect the browser to the target tenant's emailconfirmation endpoint with a one-time token and a
        signed "next" back to the requested QR code URL. The login will be transparent for the user.
        """
        # 1) Decode base64url-encoded target URL
        import base64
        from urllib.parse import urlparse

        def b64url_decode(data: str) -> str:
            # restore padding
            padding = '=' * ((4 - len(data) % 4) % 4)
            data_padded = (data + padding).encode('utf-8')
            return base64.urlsafe_b64decode(data_padded).decode('utf-8')

        try:
            target_url = b64url_decode(pk)
        except Exception as e:
            logger.error(f"redirect_session_to_another_tenant: invalid encoded URL: {e}")
            messages.add_message(request, messages.ERROR, _("Invalid redirect target"))
            return redirect('/')

        # 2) Validate URL and domain
        parsed = urlparse(target_url)
        if not parsed.scheme or not parsed.netloc:
            messages.add_message(request, messages.ERROR, _("Invalid redirect target"))
            return redirect('/')
        # remove potential port when comparing with Domain.domain
        host = parsed.netloc.split(':')[0]

        if not Domain.objects.filter(domain=host).exists():
            logger.warning(f"redirect_session_to_another_tenant: domain not managed: {host}")
            messages.add_message(request, messages.ERROR, _("Unknown destination domain"))
            return redirect('/')

        # 3) Generate a one-time token for the current user
        user: TibilletUser = request.user
        try:
            token = user.get_connect_token()
        except Exception as e:
            logger.error(f"redirect_session_to_another_tenant: cannot generate token: {e}")
            messages.add_message(request, messages.ERROR, _("Unable to prepare login on destination"))
            return redirect('/')

        # 4) Sign the next URL so that emailconfirmation accepts it
        try:
            signed_next = signing.dumps(target_url)
        except Exception as e:
            logger.error(f"redirect_session_to_another_tenant: cannot sign next URL: {e}")
            messages.add_message(request, messages.ERROR, _("Unable to prepare redirection"))
            return redirect('/')

        # 5) Redirect to the destination tenant's emailconfirmation with the token and next
        redirect_url = f"https://{host}/emailconfirmation/{token}?next={signed_next}"
        return HttpResponseRedirect(redirect_url)


class MyAccount(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]
    permission_classes = [permissions.IsAuthenticated, ]

    def dispatch(self, request, *args, **kwargs):
        """
        Vérifie si l'utilisateur est authentifié avant d'accéder à la page "My Account".
        Si l'utilisateur n'est pas authentifié, il est redirigé vers la page d'accueil (/).
        Cela évite l'erreur 403 Forbidden pour les utilisateurs anonymes.

        Cette méthode est appelée pour chaque requête avant d'exécuter la méthode spécifique (list, wallet, etc.).
        Elle sert de point de contrôle d'authentification centralisé pour toutes les actions de cette vue.
        """
        if not request.user.is_authenticated:
            messages.add_message(request, messages.WARNING,
                                 _("Please login to access this page."))
            return redirect('/')

        # check que le wallet existe bien :
        if not request.user.wallet:
            fedowAPI = FedowAPI()
            fedowAPI.wallet.get_or_create_wallet(request.user)
        return super().dispatch(request, *args, **kwargs)

    def list(self, request: HttpRequest):
        template_context = get_context(request)
        # Pas de header sur cette page
        template_context['header'] = False
        template_context['account_tab'] = 'index'

        if not request.user.email_valid:
            logger.warning("User email not active")
            messages.add_message(request, messages.WARNING,
                                 _("Please validate your email to access all the features of your profile area."))

        return render(request, "reunion/views/account/index.html", context=template_context)

    @action(detail=False, methods=['GET'])
    def balance(self, request: HttpRequest):
        template_context = get_context(request)
        # Pas de header sur cette page
        template_context['header'] = False
        template_context['account_tab'] = 'balance'

        return render(request, "reunion/views/account/balance.html", context=template_context)

    """
    # Plus besoin : c'est le /my_account (list) qui prend le relai
    @action(detail=False, methods=['GET'])
    def wallet(self, request: HttpRequest) -> HttpResponse:
        template_context = get_context(request)
        # Pas de header sur cette page
        template_context['header'] = False
        return render(request, "htmx/views/my_account/my_account_wallet.html", context=template_context)
    """

    @action(detail=False, methods=['GET'])
    def my_cards(self, request):
        fedowAPI = FedowAPI()
        cards = fedowAPI.NFCcard.retrieve_card_by_signature(request.user)
        context = {
            'cards': cards
        }
        return render(request, "reunion/partials/account/card_table.html", context=context)

    @action(detail=True, methods=['GET'])
    def admin_my_cards(self, request, pk):
        tenant = request.tenant
        admin = request.user
        if admin.is_tenant_admin(tenant):
            fedowAPI = FedowAPI()
            user = get_object_or_404(HumanUser, pk=pk)
            cards = fedowAPI.NFCcard.retrieve_card_by_signature(user)
            wallet = fedowAPI.wallet.cached_retrieve_by_signature(user).validated_data
            tokens = [token for token in wallet.get('tokens') if token.get('asset_category') not in ['SUB', 'BDG']]

            context = {
                'cards': cards,
                'tokens': tokens,
                'user_pk': pk,
            }
            return render(request, "admin/membership/wallet_info.html", context=context)
        return HttpResponse("No cards")

    @action(detail=False, methods=['GET'])
    def my_reservations(self, request):
        reservations = Reservation.objects.filter(
            user_commande=request.user,
            status__in=[
                Reservation.FREERES,
                Reservation.FREERES_USERACTIV,
                Reservation.PAID,
                Reservation.PAID_ERROR,
                Reservation.PAID_NOMAIL,
                Reservation.VALID,
            ]
        )
        context = get_context(request)
        context['reservations'] = reservations
        context['account_tab'] = 'reservations'

        return render(request, "reunion/views/account/reservations.html", context=context)

    @action(detail=True, methods=['POST'])
    def cancel_reservation(self, request, pk):
        resa = get_object_or_404(Reservation, pk=pk, user_commande=request.user)
        # Prevent cancel if any ticket already scanned
        if resa.tickets.filter(status=Ticket.SCANNED).exists():
            messages.add_message(request, messages.ERROR, _("You cannot cancel a reservation with scanned tickets."))
            return HttpResponseClientRedirect('/my_account/my_reservations/')
        # Mark reservation as canceled
        try:
            cancel_text = resa.cancel_and_refund_resa()
            messages.add_message(request, messages.SUCCESS,
                                 _("Your reservation has been cancelled.") + f" {cancel_text}")
            # Trigger email notification to the user via Celery
            try:
                send_reservation_cancellation_user.delay(str(resa.uuid))
            except Exception as ce:
                logger.error(f"Failed to queue cancellation email for reservation {resa.uuid}: {ce}")
            return HttpResponseClientRedirect('/my_account/my_reservations/')
        except Exception as e:
            logger.error(f"Error canceling reservation {pk}: {e}")
            messages.add_message(request, messages.ERROR,
                                 _("An error occurred while cancelling your reservation.") + f" : {e}")
            return HttpResponseClientRedirect('/my_account/my_reservations/')

    @action(detail=True, methods=['POST'])
    def cancel_ticket(self, request, pk):
        ticket = get_object_or_404(Ticket, pk=pk, reservation__user_commande=request.user)
        try:
            msg = ticket.reservation.cancel_and_refund_ticket(ticket)
            messages.add_message(request, messages.SUCCESS,
                                 _("Your ticket has been cancelled.") + (f" {msg}" if msg else ""))
            # Trigger email notification to the user via Celery
            try:
                send_ticket_cancellation_user.delay(str(ticket.uuid))
            except Exception as ce:
                logger.error(f"Failed to queue cancellation email for ticket {ticket.uuid}: {ce}")
            if request.headers.get('HX-Request'):
                return HttpResponse("")
            return HttpResponseClientRedirect('/my_account/my_reservations/')
        except Exception as e:
            logger.error(f"Error canceling ticket {pk}: {e}")
            messages.add_message(request, messages.ERROR,
                                 _("An error occurred while cancelling your ticket.") + f" : {e}")
            if request.headers.get('HX-Request'):
                return HttpResponse("", status=400)
            return HttpResponseClientRedirect('/my_account/my_reservations/')

    @action(detail=False, methods=['GET'])
    def resend_activation_email(self, request):
        user = request.user
        email = request.user.email
        user = get_or_create_user(email, force_mail=True)
        messages.add_message(request, messages.SUCCESS,
                             _("Mail sent, please check spam too!"))
        return HttpResponseClientRedirect('/my_account/')

    @action(detail=True, methods=['GET'])
    def admin_lost_my_card(self, request, pk, *args, **kwargs):
        tenant = request.tenant
        admin = request.user
        user_pk, number_printed = pk.split(':')
        user = get_object_or_404(HumanUser, pk=user_pk)
        if admin.is_tenant_admin(tenant):
            fedowAPI = FedowAPI()
            lost_card_report = fedowAPI.NFCcard.lost_my_card_by_signature(user, number_printed=number_printed)
            if lost_card_report:
                messages.add_message(request, messages.SUCCESS,
                                     _("Your wallet has been detached from this card. You can scan a new one to link it again."))
            else:
                messages.add_message(request, messages.ERROR,
                                     _("Error when detaching your card. Contact an administrator."))
            return HttpResponseClientRedirect(request.headers['Referer'])

    @action(detail=True, methods=['GET'])
    def lost_my_card(self, request, pk):
        if request.user.email_valid:
            fedowAPI = FedowAPI()
            lost_card_report = fedowAPI.NFCcard.lost_my_card_by_signature(request.user, number_printed=pk)
            if lost_card_report:
                messages.add_message(request, messages.SUCCESS,
                                     _("Your wallet has been detached from this card. You can scan a new one to link it again."))
            else:
                messages.add_message(request, messages.ERROR,
                                     _("Error when detaching your card. Contact an administrator."))
            return HttpResponseClientRedirect('/my_account/')
        else:
            logger.warning(_("User email not active"))
            return HttpResponseClientRedirect('/my_account/')

    @action(detail=False, methods=['GET'])
    def refund_online(self, request):
        user = request.user
        fedowAPI = FedowAPI()
        wallet = fedowAPI.wallet.cached_retrieve_by_signature(user).validated_data
        token_fed = [token for token in wallet.get('tokens') if token['asset']['is_stripe_primary'] == True]
        if len(token_fed) != 1:
            messages.add_message(request, messages.ERROR,
                                 _("You do not have a federated wallet. Maybe you loaded money directly at a register?"))
            return HttpResponseClientRedirect('/my_account/')

        value = token_fed[0]['value']
        if value < 1:
            messages.add_message(request, messages.ERROR,
                                 _(f"Your wallet is already empty."))
            return HttpResponseClientRedirect('/my_account/')

        status_code, result = fedowAPI.wallet.refund_fed_by_signature(user)
        if status_code == 202:
            # On clear le cache du wallet
            cache.delete(f"wallet_user_{user.wallet.uuid}")
            messages.add_message(request, messages.SUCCESS,
                                 _("A refund has been made to the provided account. Thank you!"))
            # Send confirmation email to the user via Celery
            amount_eur = dround(value)
            context = {
                'username': user.full_name() or user.email,
                'title': f"Remboursement de {amount_eur} € initié",
                'sub_title': "TiBillet",
                'main_text': f"La demande de remboursement de la somme {amount_eur} € a été envoyée à notre prestataire bancaire (Stripe).",
                'main_text_2': f"Il apparaitra sur votre relevé sous 10 jours. Passé ce délai sans remboursement, veuillez nous contacter sur contact@tibillet.re, nous pourrons vérifier ensemble.",
                'table_info': {'Montant remboursé': f'{amount_eur} €'},
                'end_text': "À bientôt !",
                'signature': "Marvin, le robot TiBillet",
            }
            send_email_generique.delay(context=context, email=user.email)
            return HttpResponseClientRedirect('/my_account/')
        else:
            messages.add_message(request, messages.WARNING,
                                 _(f"Apologies, it seems you need to manually request a refund. You can go to one of the collective's register, or send ar email to: contact@tibillet.re ."))
            return HttpResponseClientRedirect('/my_account/')

    @staticmethod
    def get_place_cached_info(place_uuid):
        # Recherche des infos dans le cache :
        place_info = cache.get(f"place_uuid")
        if place_info:
            logger.info("place info from cache GET")
            return place_info.get(place_uuid)
        else:
            # Va chercher dans toute les configs de tous les tenants de l'instance
            place_info = {}
            for tenant in Client.objects.filter(categorie=Client.SALLE_SPECTACLE):
                with tenant_context(tenant):
                    fedow_config = FedowConfig.get_solo()
                    this_place_uuid = fedow_config.fedow_place_uuid
                    config = Configuration.get_solo()
                    place_info[this_place_uuid] = {
                        'organisation': config.organisation,
                        'logo': config.logo,
                    }

            logger.info("place info to cache SET")
            cache.set(f"place_uuid", place_info, 3600)
        return place_info.get(place_uuid)

    @action(detail=False, methods=['GET'])
    def tokens_table(self, request):
        config = Configuration.get_solo()
        fedowAPI = FedowAPI()
        wallet = fedowAPI.wallet.cached_retrieve_by_signature(request.user).validated_data

        # On retire les adhésions, on les affiche dans l'autre table
        tokens = [token for token in wallet.get('tokens') if token.get('asset_category') not in ['SUB', 'BDG']]

        for token in tokens:
            names_of_place_federated = []
            # Recherche du logo du lieu d'origin de l'asset
            if token['asset']['place_origin']:
                # L'asset fédéré n'a pas d'origin
                place_uuid_origin = token['asset']['place_origin']['uuid']
                place_info = self.get_place_cached_info(place_uuid_origin)
                token['asset']['logo'] = place_info.get('logo')
                names_of_place_federated.append(place_info.get('organisation'))
            # Recherche des noms des lieux fédérés

            for place_federated in token['asset']['place_uuid_federated_with']:
                place = self.get_place_cached_info(place_federated)
                if place:
                    names_of_place_federated.append(place.get('organisation'))
            token['asset']['names_of_place_federated'] = names_of_place_federated

            # Recherche de la dernière action du token fédéré
            # if token['asset']['category'] == 'FED':
            #     last_federated_transaction: datetime = token['last_transaction']['datetime']

        print(tokens)

        # On fait la liste des lieux fédérés pour les pastilles dans le tableau html
        context = {
            'config': config,
            'tokens': tokens,
        }

        return render(request, "reunion/partials/account/token_table.html", context=context)

    @action(detail=False, methods=['GET'])
    def transactions_table(self, request):
        config = Configuration.get_solo()
        fedowAPI = FedowAPI()
        # On utilise ici .data plutot que validated_data pour executer les to_representation (celui du WalletSerializer)
        # et les serializer.methodtruc
        paginated_list_by_wallet_signature = fedowAPI.transaction.paginated_list_by_wallet_signature(
            request.user).validated_data

        transactions = paginated_list_by_wallet_signature.get('results')
        next_url = paginated_list_by_wallet_signature.get('next')
        previous_url = paginated_list_by_wallet_signature.get('previous')

        context = {
            'actions_choices': TransactionSimpleValidator.TYPE_ACTION,
            'config': config,
            'transactions': transactions,
            'next_url': next_url,
            'previous_url': previous_url,
        }
        return render(request, "reunion/partials/account/transaction_history.html", context=context)

    ### ONGLET ADHESION
    @action(detail=False, methods=['GET'])
    def membership(self, request: HttpRequest) -> HttpResponse:
        context = get_context(request)
        context['account_tab'] = 'memberships'  # l'onglet de la page admin
        user: TibilletUser = request.user

        # Classement par valid / not valid
        # On utilise des booléans pour que sur le template, on fasse for is_valid, membership_list in memberships_dict.items.
        # On peut alors conditionner simplement sur le if is_valid :)
        memberships_dict = {True: [], False: []}

        for tenant in user.client_achat.all():
            with tenant_context(tenant):
                memberships = Membership.objects.filter(
                    last_contribution__isnull=False,
                    user=user,
                ).select_related('price', 'price__product').prefetch_related("option_generale").order_by('deadline')

                for membership in memberships:
                    membership.origin = Configuration.get_solo().organisation
                    if membership.is_valid():
                        memberships_dict[True].append(membership)
                    else:
                        memberships_dict[False].append(membership)

        context['memberships_dict'] = memberships_dict
        return render(request, "reunion/views/account/membership/memberships.html", context=context)

    @action(detail=False, methods=['GET'])
    def card(self, request: HttpRequest) -> HttpResponse:
        context = get_context(request)
        context['account_tab'] = 'card'
        return render(request, "reunion/views/account/card.html", context=context)

    @action(detail=False, methods=['GET'])
    def profile(self, request: HttpRequest) -> HttpResponse:
        context = get_context(request)
        context['account_tab'] = 'profile'
        return render(request, "reunion/views/account/preferences.html", context=context)

    #### REFILL STRIPE PRIMARY ####

    @action(detail=False, methods=['GET'])
    def refill_wallet(self, request):
        user = request.user
        fedowAPI = FedowAPI()
        # C'est fedow qui génère la demande de paiement à Stripe.
        # Il ajoute dans les metadonnée les infos du wallet, et le signe.
        # Lors du retour du paiement, la signature est vérifiée pour être sur que la demande de paiement vient bien de Fedow.
        stripe_checkout_url = fedowAPI.wallet.get_federated_token_refill_checkout(user)
        if stripe_checkout_url:
            # Redirection du client vers le lien stripe demandé par Fedow
            return HttpResponseClientRedirect(stripe_checkout_url)
        else:
            messages.add_message(request, messages.ERROR, _("Not available. Contact an admin."))
            return HttpResponseClientRedirect('/my_account/')

    @action(detail=True, methods=['GET'])
    def return_refill_wallet(self, request, pk=None):
        # On demande confirmation à Fedow qui a du recevoir la validation en webhook POST
        # Fedow vérifie la signature du paiement dans les metada Stripe
        # C'est Fedow entré le metadata signé, c'est lui qui vérifie.
        user = request.user
        fedowAPI = FedowAPI()

        try:
            wallet = fedowAPI.wallet.retrieve_from_refill_checkout(user, pk)
            if wallet:
                messages.add_message(request, messages.SUCCESS, _("Refilled wallet"))
            else:
                messages.add_message(request, messages.ERROR, _("Payment verification error"))
        except Exception as e:
            messages.add_message(request, messages.ERROR, _("Payment verification error"))

        return redirect('/my_account/')


class QrCodeScanPay(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]

    @action(detail=True, methods=['GET'], permission_classes=[TenantAdminPermission, ])
    def check_payment(self, request: HttpRequest, pk=None):
        user = request.user
        this_tenant: Client = connection.tenant
        if not user.is_tenant_admin(this_tenant):
            return HttpResponse(status=403)

        la_uuid = uuid.UUID(pk)
        is_valid = False
        try:
            is_valid = LigneArticle.objects.filter(uuid=la_uuid, status=LigneArticle.VALID).exists()
        except Exception:
            pass

        context = {
            "is_valid": is_valid,
            "ligne_article_uuid_hex": la_uuid.hex,
        }
        return render(request, "reunion/views/qrcode_scan_pay/fragments/check_payment.html", context=context)

    @action(detail=False, methods=['GET'], permission_classes=[TenantAdminPermission, ])
    def get_generator(self, request: HttpRequest):

        user = request.user
        this_tenant: Client = connection.tenant
        if not user.is_tenant_admin(this_tenant):
            messages.add_message(request, messages.ERROR, _("You are not authorized to access this page."))
            return redirect('/')
        # GET de la route /qrcodegenerator
        # On livre le template qui permet de générer un qrcode
        template_context = get_context(request)
        return render(request, "reunion/views/qrcode_scan_pay/generator.html", context=template_context)

    @action(detail=False, methods=['POST'], permission_classes=[TenantAdminPermission, ])
    def generate_qrcode(self, request: HttpRequest):
        # POST de la route /qrcodegenerator qui génère le qrcode
        data = request.POST
        logger.info(f"QRCODEGENERATOR POST : {data}")
        user = request.user

        this_tenant: Client = connection.tenant
        if not user.is_tenant_admin(this_tenant):
            messages.add_message(request, messages.ERROR, _("You are not authorized to access this page."))
            return redirect('/')

        # Get the form data
        amount = int(dround(Decimal(data.get('amount'))) * 100)
        asset_type = data.get('asset_type', 'EUR')

        if not amount or not asset_type:
            messages.add_message(request, messages.ERROR, _("Amount and asset type are required"))
            return redirect('qrcodescanpay-get-generator')

        # Create product and price entries
        product = Product.objects.get_or_create(name=_('Sale via QR code link'), categorie_article=Product.QRCODE_MA)[0]
        product_sold = ProductSold.objects.get_or_create(product=product)[0]
        price = Price.objects.get_or_create(name=f"{dround(amount)}€", product=product, prix=dround(amount))[0]
        price_sold = PriceSold.objects.get_or_create(productsold=product_sold, price=price, prix=dround(amount))[0]

        # Create LigneArticle with metadata containing admin email
        ligne_article = LigneArticle.objects.create(
            pricesold=price_sold,
            qty=1,
            amount=amount,
            payment_method=PaymentMethod.QRCODE_MA,
            status=LigneArticle.CREATED,
            metadata=json.dumps({"admin": str(request.user.email)})
        )

        # Use the UUID directly in the QR code
        qr_data = ligne_article.uuid.hex

        # Generate QR code
        base_url = connection.tenant.get_primary_domain().domain
        qr_code_content = f"https://{base_url}/qrcodescanpay/{qr_data}/process_qrcode"

        # Prepare context for template
        template_context = get_context(request)
        template_context['qrcode_generated'] = True
        template_context['amount'] = amount
        template_context['asset_type'] = asset_type
        template_context['qrcode_content'] = qr_code_content
        template_context['ligne_article_uuid_hex'] = qr_data

        return render(request, "reunion/views/qrcode_scan_pay/generator.html", context=template_context)

    @action(detail=False, methods=['GET'], permission_classes=[permissions.IsAuthenticated, ])
    def get_scanner(self, request: HttpRequest):
        if request.method == 'GET':  # On demande le scanner
            user = request.user
            if not user.email_valid:
                messages.add_message(request, messages.ERROR, _("Please validate your email address."))
                return redirect('/my_account/')

            # GET de la route /qrcodescanpay
            # On livre le template qui lance la caméra pour scanner un qrcode
            template_context = get_context(request)
            return render(request, "reunion/views/qrcode_scan_pay/scanner.html", context=template_context)

        # if request.method == 'POST' : # C'est le résultat du scanner
        #     import ipdb; ipdb.set_trace()

    @action(methods=['POST'], detail=False, permission_classes=[TenantAdminPermission, ])
    def process_with_nfc(self, request):
        nfc_validator = QrCodeScanPayNfcValidator(data=request.data, context={'request': request})
        if not nfc_validator.is_valid():
            logger.info(f"NFC validation failed: {nfc_validator.errors}")
            return Response(nfc_validator.errors, status=status.HTTP_400_BAD_REQUEST)

        # Si c'est valid, alors tout est passé, même la vérification du solde du portefeuille.
        ligne_article: LigneArticle = nfc_validator.ligne_article
        tag_id = nfc_validator.tag_id
        wallet = nfc_validator.wallet

        # Attache les infos NFC et la carte sur la ligne article
        # metadata peut être déjà un dict (JSONField) ou une chaîne JSON
        if isinstance(ligne_article.metadata, dict):
            metadata = ligne_article.metadata
        else:
            metadata = json.loads(ligne_article.metadata) if ligne_article.metadata else {}
        metadata['nfc'] = {
            'tag_id': tag_id,
            'read_at': timezone.now().isoformat(),
            'reader': request.user.email,
            'user': wallet.user.email,
        }
        ligne_article.metadata = json.dumps(metadata, cls=DjangoJSONEncoder) if not isinstance(metadata,
                                                                                               dict) else metadata
        ligne_article.save(update_fields=['metadata'])

        # lancement de la transaction via Fedow api
        try:
            fedowAPI = nfc_validator.fedowAPI
            transactions = fedowAPI.transaction.to_place_from_qrcode(
                metadata=metadata,
                amount=ligne_article.amount,
                asset_type="EURO",
                user=wallet.user,
            )
            assert transactions is not None
            assert type(transactions) is list
            # on supprime la ligne article pour la recréer en fonction de la ou des transactions
            total_amount = ligne_article.amount
            metadata['transactions'] = transactions
            pricesold = ligne_article.pricesold
            ex_ligne_article_uuid = ligne_article.uuid
            ligne_article.delete()
            for transaction in transactions:
                # On récupère les infos de l'asset :
                asset_used = fedowAPI.asset.retrieve(str(transaction['asset']))
                if asset_used['category'] == 'FED':
                    mp = PaymentMethod.STRIPE_FED
                elif asset_used['category'] == 'TLF':
                    mp = PaymentMethod.LOCAL_EURO
                else:
                    raise Exception("Unknown asset category")

                # Create LigneArticle with metadata containing admin email
                ligne_article = LigneArticle.objects.create(
                    uuid=ex_ligne_article_uuid if transactions.index(transaction) == 0 else uuid.uuid4(),
                    pricesold=pricesold,
                    qty=dround(Decimal(transaction['amount'] / total_amount)),
                    amount=transaction['amount'],
                    payment_method=mp,
                    status=LigneArticle.VALID,
                    metadata=json.dumps(metadata, cls=DjangoJSONEncoder),
                    asset=transaction['asset'],
                    wallet=wallet,
                )

                # import ipdb; ipdb.set_trace()
                # Chaque transaction doit être bien enregistré sur LaBoutik avec le bon Asset indiqué
                send_sale_to_laboutik.delay(ligne_article.uuid)

            # Envoi des emails de confirmation (admin et utilisateur)
            try:
                place = connection.tenant.name
                # Email admin
                send_payment_success_admin.delay(total_amount, timezone.now(), place, request.user.email)
                # Email user
                send_payment_success_user.delay(wallet.user.email, total_amount, timezone.now(), place)
            except Exception as e_mail:
                logger.error(f"Error sending payment confirmation emails: {e_mail}")

        except Exception as e:
            logger.error(f"Error validating payment: {str(e)}")
            raise f"Error validating payment: {str(e)}"

        # C'est un retour vers une swal alert -> on fait pas de HTML pour une fois
        return Response({
            'status': 'Paiement OK',
            'user_email': wallet.user.email,
            'amount_paid': dround(ligne_article.amount),
            'balance': dround(nfc_validator.user_balance - ligne_article.amount),
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['GET'], permission_classes=[
        permissions.AllowAny, ])  # on permet a tout le monde de scanner un qrcode, mais si tu n'est pas loggué, on te redirige
    def process_qrcode(self, request: HttpRequest, pk):
        user = request.user
        if not user.is_authenticated:
            # On redirige vers la page de login full page avec un next vers ici
            signed_next_url = signing.dumps(request.get_full_path())
            logger.info(f"process_qrcode no auth, need redirect. signed_next_url : {signed_next_url}")
            return redirect(f'/login/login_fullpage?next={signed_next_url}')

        if not user.email_valid:
            messages.add_message(request, messages.ERROR, _("Please validate your email address."))
            return redirect('/my_account/')

        ligne_article_uuid_hex = pk
        template_context = get_context(request)

        if not ligne_article_uuid_hex:
            messages.add_message(request, messages.ERROR, _("No QR code content received"))
            return render(request, "reunion/views/qrcode_scan_pay/scanner.html", context=template_context)

        # Process the QR code content
        try:
            from uuid import UUID
            ligne_article_uuid = UUID(ligne_article_uuid_hex)
            ligne_article = LigneArticle.objects.get(uuid=ligne_article_uuid)
            logger.info(f"Found LigneArticle: {ligne_article}")

            # Get payment information from LigneArticle
            amount = ligne_article.amount
            asset_type = "EURO"  # Default to EURO

            # Update metadata with user email and uuid hex for Fedow
            metadata = json.loads(ligne_article.metadata) if ligne_article.metadata else {}
            metadata["scanner_email"] = user.email
            metadata["ligne_article_uuid_hex"] = ligne_article_uuid_hex
            ligne_article.metadata = json.dumps(metadata, cls=DjangoJSONEncoder)
            ligne_article.save()

            # Set the payment details in the template context
            tenant = connection.tenant
            template_context['payment_location'] = tenant.name
            template_context['amount'] = amount
            template_context['asset_type'] = asset_type
            template_context['ligne_article_uuid_hex'] = ligne_article_uuid_hex

            # Check if the LigneArticle is already validated
            if ligne_article.status == LigneArticle.VALID:
                template_context['error_message'] = _("This payment has already been processed")
                return render(request, "reunion/views/qrcode_scan_pay/payment_error.html", context=template_context)

            logger.info(f"Processed LigneArticle: {ligne_article_uuid}")

        except LigneArticle.DoesNotExist:
            logger.error(f"No LigneArticle found with UUID: {ligne_article_uuid_hex}")
            template_context['error_message'] = _("Invalid QR code: payment not found")
            return render(request, "reunion/views/qrcode_scan_pay/payment_error.html", context=template_context)

        except Exception as e:
            logger.error(f"Error processing QR code: {str(e)}")
            messages.add_message(request, messages.ERROR, _("Invalid QR code format"))
            return render(request, "reunion/views/qrcode_scan_pay/scanner.html")

        # Check the wallet on fedow
        user = request.user
        from fedow_connect.fedow_api import FedowAPI
        fedow_api = FedowAPI()
        fedow_api.wallet.get_or_create_wallet(user)
        user_balance = fedow_api.wallet.get_total_fiducial_and_all_federated_token(user)
        template_context['user_balance'] = user_balance
        template_context['insufficient_funds'] = amount > user_balance

        # Render the payment validation template
        return render(request, "reunion/views/qrcode_scan_pay/payment_validation.html", context=template_context)

    @action(detail=False, methods=['POST'], permission_classes=[permissions.IsAuthenticated, ])
    def valid_payment(self, request: HttpRequest):
        user = request.user
        if not user.email_valid:
            messages.add_message(request, messages.ERROR, _("Please validate your email address."))
            return redirect('/my_account/')

        # Process the payment validation
        data = request.POST
        logger.info(f"PAYMENT VALIDATION POST: {data}")

        template_context = get_context(request)

        ligne_article_uuid_hex = data.get('ligne_article_uuid_hex')
        try:
            from uuid import UUID
            ligne_article_uuid = UUID(ligne_article_uuid_hex)
            ligne_article = LigneArticle.objects.get(uuid=ligne_article_uuid)
            logger.info(f"Found LigneArticle: {ligne_article}")

        except LigneArticle.DoesNotExist:
            logger.error(f"No LigneArticle found with UUID: {ligne_article_uuid_hex}")
            template_context['error_message'] = _("Invalid QR code: payment not found")
            return render(request, "reunion/views/qrcode_scan_pay/payment_error.html", context=template_context)

        except Exception as e:
            logger.error(f"Error processing QR code: {str(e)}")
            messages.add_message(request, messages.ERROR, _("Invalid QR code format"))
            return render(request, "reunion/views/qrcode_scan_pay/scanner.html")

        if not ligne_article_uuid_hex:
            messages.add_message(request, messages.ERROR, _("Missing QR code content"))
            return redirect('qrcodescanpay-list')

        # Get payment information from LigneArticle
        amount = ligne_article.amount
        asset_type = "EURO"  # Default to EURO

        # Get admin information from metadata
        metadata = json.loads(ligne_article.metadata) if ligne_article.metadata else {}
        # Check the wallet on fedow
        user = request.user
        from fedow_connect.fedow_api import FedowAPI
        fedow_api = FedowAPI()
        wallet, created = fedow_api.wallet.get_or_create_wallet(user)
        user_balance = fedow_api.wallet.get_total_fiducial_and_all_federated_token(user)

        if user_balance < amount:
            # Insufficient funds scenario
            # Set the payment details in the template context
            tenant = connection.tenant
            template_context['payment_location'] = tenant.name
            template_context['amout'] = amount
            template_context['user_balance'] = user_balance  # Example balance
            return render(request, "reunion/views/qrcode_scan_pay/insufficient_funds.html", context=template_context)

        # lancement de la transaction via Fedow api
        try:
            transactions = fedow_api.transaction.to_place_from_qrcode(
                metadata=metadata,
                amount=amount,
                asset_type=asset_type,
                user=user,
            )
            assert transactions is not None
            assert type(transactions) is list
            # on supprime la ligne article pour la recréer en fonction de la ou des transactions
            total_amount = ligne_article.amount
            metadata['transactions'] = transactions
            pricesold = ligne_article.pricesold
            ex_ligne_article_uuid = ligne_article.uuid
            ligne_article.delete()
            for transaction in transactions:
                # On récupère les infos de l'asset :
                asset_used = fedow_api.asset.retrieve(str(transaction['asset']))
                if asset_used['category'] == 'FED':
                    mp = PaymentMethod.STRIPE_FED
                elif asset_used['category'] == 'TLF':
                    mp = PaymentMethod.LOCAL_EURO
                else:
                    raise Exception("Unknown asset category")

                # Create LigneArticle with metadata containing admin email
                ligne_article = LigneArticle.objects.create(
                    uuid=ex_ligne_article_uuid if transactions.index(transaction) == 0 else uuid.uuid4(),
                    pricesold=pricesold,
                    qty=dround(Decimal(transaction['amount'] / total_amount)),
                    amount=transaction['amount'],
                    payment_method=mp,
                    status=LigneArticle.VALID,
                    metadata=json.dumps(metadata, cls=DjangoJSONEncoder),
                    asset=transaction['asset'],
                    wallet=wallet,
                )

                # import ipdb; ipdb.set_trace()
                # Chaque transaction doit être bien enregistré sur LaBoutik avec le bon Asset indiqué
                send_sale_to_laboutik.delay(ligne_article.uuid)

            # Set the payment details in the template context
            tenant = connection.tenant
            template_context['payment_location'] = tenant.name
            template_context['amount'] = amount
            template_context['payment_time'] = timezone.now().strftime("%d/%m/%Y %H:%M")
            template_context['user_balance'] = fedow_api.wallet.get_total_fiducial_and_all_federated_token(user)

            # Envoi des emails de confirmation (admin et utilisateur)
            try:
                payment_time_str = template_context['payment_time']
                place = tenant.name
                # Email admin
                send_payment_success_admin.delay(amount, payment_time_str, place, user.email)
                # Email user
                send_payment_success_user.delay(user.email, amount, payment_time_str, place)
            except Exception as e_mail:
                logger.error(f"Error sending payment confirmation emails: {e_mail}")

            return render(request, "reunion/views/qrcode_scan_pay/payment_confirmation.html", context=template_context)


        except Exception as e:
            logger.error(f"Error validating payment: {str(e)}")
            template_context['error_message'] = _("Error validating payment")
            return render(request, "reunion/views/qrcode_scan_pay/payment_error.html", context=template_context)

    '''
    def get_permissions(self):
        if self.action in [ # Action de création et de vérification du lien de paiement, reservé a un admin de lieu
            'check_payment',
            'get_generator',
            'generate_qrcode',
        ]:
            permission_classes = [TenantAdminPermission,]
        elif self.action in [
            "list"
        ]:
            permission_classes = [permissions.IsAuthenticated]
        # else:
        return [permission() for permission in permission_classes]
    '''


@require_GET
def index(request):
    # On redirige vers la page d'adhésion en attendant que les events soient disponibles
    tenant: Client = connection.tenant
    if tenant.categorie in [Client.WAITING_CONFIG, Client.ROOT]:
        return HttpResponseRedirect('https://tibillet.org/')

    template_context = get_context(request)
    return render(request, "reunion/views/home.html", context=template_context)


class FederationViewset(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]
    permission_classes = [permissions.AllowAny]

    def list(self, request):
        template_context = get_context(request)

        def build_federated_places():
            results = list()
            tenants = list()

            actual_tenant = connection.tenant
            tenants.append(actual_tenant)
            # Les lieux fédéré en agenda
            for fed in FederatedPlace.objects.all():
                if fed.tenant not in tenants :
                    tenants.append(fed.tenant)
            # Les lieux fédéré en Asset
            for asset in AssetFedowPublic.objects.all():
                tenant_origin = asset.origin
                if tenant_origin not in tenants:
                    tenants.append(tenant_origin)
                for tenant in asset.federated_with.all():
                    if tenant not in tenants:
                        tenants.append(tenant)

            logger.info(f"Tenants: {tenants}")

            for client in list(set(tenants)):
                if client.categorie != Client.ROOT:
                    with tenant_context(client):
                        tenant = connection.tenant
                        logger.info(f"with tenant_context(client): {client}")
                        logger.info(f"with tenant: {tenant}")
                        logger.info(f"with categorie: {tenant.categorie}")

                        config = Configuration.get_solo()

                        assets = list()

                        # les assets fédérés
                        for asset in tenant.federated_assets_fedow_public.exclude(
                                category__in=[
                                    AssetFedowPublic.BADGE,
                                    AssetFedowPublic.SUBSCRIPTION,
                                ]):
                            assets.append(asset)

                        # Les assets créés
                        for asset in tenant.assets_fedow_public.exclude(
                                category__in=[
                                    AssetFedowPublic.BADGE,
                                    AssetFedowPublic.SUBSCRIPTION,
                                ]):
                            if asset not in assets:
                                assets.append(asset)

                        results.append({
                            "organisation": config.organisation,
                            "slug": config.slug,
                            "short_description": config.short_description,
                            "long_description": config.long_description,
                            "img": config.get_social_card,
                            "assets": [{"name":f"{asset.name}"} for asset in assets],
                            "url": config.full_url(),
                        })

                return results

        federated_places = None
        # federated_places = cache.get('federated_places')
        if not federated_places:
            federated_places = build_federated_places()
            cache.set('federated_places', federated_places, 60)

        template_context['federated_places'] = federated_places
        logger.info(f"Federated places: {federated_places}")
        return render(request, "reunion/views/federation/list.html", context=template_context)


class HomeViewset(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]

    @action(detail=False, methods=['POST'])
    def contact(self, request):
        logger.info(request.data)
        validator = ContactValidator(data=request.data, context={'request': request})
        if not validator.is_valid():
            for error in validator.errors:
                messages.add_message(request, messages.ERROR, f"{error} : {validator.errors[error][0]}")
            return HttpResponseClientRedirect(request.headers['Referer'])

        contact_mailer.delay(
            sender=validator.validated_data['email'],
            subject=validator.validated_data['subject'],
            message=validator.validated_data['message'],
        )

        messages.add_message(request, messages.SUCCESS, _("Message sent, you have been sent a copy. Thank you!"))
        return HttpResponseClientRedirect(request.headers['Referer'])

    def get_permissions(self):
        # if self.action in ['create']:
        #     permission_classes = [permissions.IsAuthenticated]
        # else:
        permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]


class EventMVT(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]

    def federated_events_get(self, slug):
        for place in FederatedPlace.objects.all():
            tenant = place.tenant
            with tenant_context(tenant):
                try:
                    event = Event.objects.select_related(
                        'postal_address',
                    ).prefetch_related(
                        'tag', 'products', 'products__prices',
                    ).get(slug=slug)
                    event.img = event.get_img()
                    event.sticker_img = event.get_sticker_img()
                    return event
                except Event.DoesNotExist:
                    continue

        return None

    def federated_events_get_hex8(self, hex8):
        for place in FederatedPlace.objects.all():
            tenant = place.tenant
            with tenant_context(tenant):
                try:
                    event = Event.objects.select_related(
                        'postal_address',
                    ).prefetch_related(
                        'tag', 'products', 'products__prices',
                    ).get(uuid__startswith=hex8)
                    event.img = event.get_img()
                    event.sticker_img = event.get_sticker_img()
                    return event
                except Event.DoesNotExist:
                    continue

        return None

    def federated_events_filter(self, tags=None, search=None, page=1):
        dated_events = {}
        paginated_info = {
            'page': page,
            'has_next': False,
            'has_previous': False,
        }

        # Création d'un dictionnaire pour mélanger les objets FederatedPlace et la place actuelle.
        tenants = [
            {
                "tenant": place.tenant,
                "tag_exclude": [tag.slug for tag in place.tag_exclude.all()],
                "tag_filter": [tag.slug for tag in place.tag_filter.all()],
            }
            for place in FederatedPlace.objects.all().prefetch_related("tag_filter", "tag_exclude")
        ]
        # Le tenant actuel
        this_tenant = connection.tenant
        tenants.append(
            {
                "tenant": this_tenant,
                "tag_filter": [],
                "tag_exclude": [],
            }
        )
        # Récupération de tous les évènements de la fédération
        for tenant in tenants:
            with ((tenant_context(tenant['tenant']))):
                events = Event.objects.select_related(
                    'postal_address',
                ).prefetch_related(
                    'tag', 'products', 'products__prices',
                ).filter(
                    published=True,
                    datetime__gte=timezone.localtime() - timedelta(days=1),
                ).exclude(tag__slug__in=tenant['tag_filter']  # On prend les évènement d'aujourd'hui
                          ).exclude(
                    categorie=Event.ACTION)  # Les Actions sont affichés dans la page de l'evenement parent

                if tenant['tenant'] != this_tenant:  # on est pas sur le tenant d'origine, on filtre le bool private
                    events = events.filter(
                        private=False
                    )

                if len(tenant['tag_exclude']) > 0:
                    events = events.filter(
                        tag__slug__in=tenant['tag_exclude'])
                if tags:
                    # Utiliser une annotation pour compter les tags correspondants
                    events = events.filter(tag__slug__in=tags).annotate(
                        tag_count=Count('tag', filter=Q(tag__slug__in=tags))
                    ).filter(tag_count=len(tags))

                elif search:
                    # On recherche dans nom, description et tag
                    events = events.filter(
                        Q(name__icontains=search) |
                        Q(postal_address__name__icontains=search) |
                        Q(postal_address__address_locality__icontains=search) |
                        Q(postal_address__postal_code__icontains=search) |
                        Q(short_description__icontains=search) |
                        Q(long_description__icontains=search) |
                        Q(tag__slug__icontains=search) |
                        Q(tag__name__icontains=search),
                    )

                # Mécanisme de pagination : 10 évènements max par lieux ? À définir dans la config' ?
                paginator = Paginator(events.order_by('datetime').distinct(), 50)
                paginated_events = paginator.get_page(page)
                paginated_info['page'] = page
                paginated_info['has_next'] = paginated_events.has_next()
                paginated_info['has_previous'] = paginated_events.has_previous()

                for event in paginated_events:
                    # On va chercher les urls d'images :
                    event.img = event.get_img()
                    event.sticker_img = event.get_sticker_img()

                    date = event.datetime.date()
                    # setdefault pour éviter de faire un if date exist dans le dict
                    dated_events.setdefault(date, []).append(event)

        # Classement du dictionnaire : TODO: mettre en cache
        sorted_dict_by_date = {
            k: sorted(v, key=lambda obj: obj.datetime) for k, v in sorted(dated_events.items())
        }

        # Retourn les évènements classés par date et les infos de pagination
        return sorted_dict_by_date, paginated_info

    @action(detail=False, methods=['POST', 'GET'])
    def partial_list(self, request):
        logger.info(f"request.data : {request.data}")

        search = request.data.get('search')  # on s'assure que c'est bien une string. Todo : Validator !
        if not search:  # Pour le get réalisé par le clic sur l'adresse
            search = request.GET.get('search')

        if search:
            search = str(search)

        tags = request.GET.getlist('tag')
        page = request.GET.get('page', 1)

        logger.info(f"request.GET : {request.GET}")

        ctx = {}  # le dict de context pour template
        ctx['dated_events'], ctx['paginated_info'] = self.federated_events_filter(tags=tags, search=search, page=page)
        return render(request, "reunion/views/event/partial/list.html", context=ctx)

    # La page get /
    def list(self, request: HttpRequest):
        # TODO pour pouvoir sauvegader l'url de recherche :
        # - tout passer en GET ( et non pas le partial_list POST plus haut )
        # - passer sur du partial render avec HTMX
        context = get_context(request)
        tags = request.GET.getlist('tag')
        # search = str(request.data['search'])  # on s'assure que c'est bien une string. Todo : Validator !
        page = request.GET.get('page', 1)
        context['dated_events'], context['paginated_info'] = self.federated_events_filter(tags=tags, page=page)
        # On renvoie la page en entier
        return render(request, "reunion/views/event/list.html", context=context)

    @action(detail=False, methods=['GET'])
    def embed(self, request):
        template_context = get_context(request)
        template_context['dated_events'], template_context['paginated_info'] = self.federated_events_filter()
        template_context['embed'] = True
        response = render(
            request, "reunion/views/event/list.html",
            context=template_context,
        )
        # Pour rendre la page dans un iframe, on vide le header X-Frame-Options pour dire au navigateur que c'est ok.
        response['X-Frame-Options'] = ''
        return response

    def retrieve(self, request, pk=None):
        slug = pk
        hex8 = None
        match = re.search(r'([0-9a-fA-F]{8})(?:/)?$', pk)
        if match:
            hex8 = match.group(1)

        logger.info(f"slug : {slug}")
        logger.info(f"hex8 : {hex8}")

        # Si False, alors le bouton reserver renvoi vers la page event du tenant.
        event_in_this_tenant = False
        try:
            if hex8:
                event = Event.objects.select_related('postal_address', ).prefetch_related('tag', 'products',
                                                                                          'products__prices').get(
                    uuid__startswith=hex8)
                logger.info(f"event avec hex8 trouvé : {event}")
            else:
                event = Event.objects.select_related('postal_address', ).prefetch_related('tag', 'products',
                                                                                          'products__prices').get(
                    slug__startswith=slug)
                logger.info(f"event avec slug trouvé : {event}")

            # selection et mise en cache des images
            event.img = event.get_img()
            event.sticker_img = event.get_sticker_img()

            # Récupération des prix
            event.prices = [price for product in event.products.all() for price in product.prices.all()]
            tarifs = [price.prix for price in event.prices]
            # Calcul des prix min et max
            event.price_min = min(tarifs) if tarifs else None
            event.price_max = max(tarifs) if tarifs else None
            # Vérification de l'existence d'un prix libre
            event.free_price = any(
                price.free_price for product in event.products.all() for price in product.prices.all())

            event_in_this_tenant = True

        except Event.DoesNotExist:
            # L'évent n'est pas
            logger.info("Event.DoesNotExist on tenant, check to federation")
            if hex8:
                event = self.federated_events_get_hex8(hex8)
            else:
                event = self.federated_events_get(slug)

        if not event:  # Event pas trouvé, on redirige vers la page d'évènement complète
            logger.info("Event.DoesNotExist on federation, redirect")
            return redirect("/event/")

        template_context = get_context(request)
        template_context['event'] = event
        template_context['event_in_this_tenant'] = event_in_this_tenant

        # L'evènement possède des sous évènement.
        # Pour l'instant : uniquement des ACTIONS
        if event.children.exists():
            template_context['action_total_jauge'] = event.children.all().aggregate(total_value=Sum('jauge_max'))[
                                                         'total_value'] or 0
            template_context['inscrits'] = Ticket.objects.filter(reservation__event__parent=event).count()

        return render(request, "reunion/views/event/retrieve.html", context=template_context)

    @action(detail=True, methods=['POST'], permission_classes=[permissions.IsAuthenticated])
    def action_reservation(self, request, pk=None):
        event = get_object_or_404(Event, pk=pk)

        user = request.user
        action = get_object_or_404(Event, pk=request.data.get('action'), categorie=Event.ACTION)

        if Ticket.objects.filter(reservation__user_commande=user, reservation__event__in=event.children.all()).exists():
            messages.add_message(request, messages.ERROR,
                                 _("You have already checked for an action on this event."))
            return HttpResponseClientRedirect(request.headers['Referer'])

        if not user:
            messages.add_message(request, messages.ERROR, _("Please log in first."))
            return HttpResponseClientRedirect(request.headers['Referer'])

        validator = ReservationValidator(data={
            "email": user.email,
            "event": action.pk,
        }, context={'request': request})

        if not validator.is_valid():
            logger.error(f"ReservationViewset CREATE ERROR : {validator.errors}")
            for error in validator.errors:
                messages.add_message(request, messages.ERROR, f"{validator.errors[error][0]}")
            return HttpResponseClientRedirect(request.headers['Referer'])

        messages.add_message(request, messages.SUCCESS, _("Thank you! You are going to receive a validation email.."))
        return HttpResponseClientRedirect(request.headers['Referer'])

    @action(detail=True, methods=['POST'])
    def reservation(self, request, pk):
        # Vérification que l'évent existe bien sur ce tenant.
        event = get_object_or_404(Event, slug=pk)
        logger.info(f"Event Reservation : {request.data}")
        validator = ReservationValidator(data=request.data, context={'request': request})

        if not validator.is_valid():
            logger.error(f"ReservationViewset CREATE ERROR : {validator.errors}")
            for error in validator.errors:
                messages.add_message(request, messages.ERROR, f"{validator.errors[error][0]}")
            return HttpResponseClientRedirect(request.headers['Referer'])

        # Le formulaire est valide.
        # Vérification de la demande de fomulaire supplémentaire avec Formbricks
        for product in validator.products:
            if product.formbricksform.exists():
                formbicks_form: FormbricksForms = product.formbricksform.first()  # On prend le premier.
                formbricks_config = FormbricksConfig.get_solo()
                checkout_stripe = validator.checkout_link if validator.checkout_link else None
                context = {'form': {'apiHost': formbricks_config.api_host,
                                    'trigger_name': formbicks_form.trigger_name,
                                    'environmentId': formbicks_form.environmentId, },
                           'reservation': validator.reservation,
                           'checkout_stripe': checkout_stripe,
                           }

                return render(request, "reunion/views/event/formbricks.html", context=context)

        # SI on a un besoin de paiement, on redirige vers :
        if validator.checkout_link:
            logger.info("validator reservation OK, get checkout link -> redirect")
            return HttpResponseClientRedirect(validator.checkout_link)

        return render(request, "reunion/views/event/reservation_ok.html", context={
            "user": request.user,
        })

    @action(detail=True, methods=['GET'])
    def stripe_return(self, request, pk, *args, **kwargs):
        # Le retour de stripe des users.
        # Il est possible que le update_checkout_status soit déja fait en post
        # par /api/webhook_stripe de ApiBillet.views.Webhook_stripe
        paiement_stripe = get_object_or_404(Paiement_stripe, uuid=pk)
        paiement_stripe.update_checkout_status()
        paiement_stripe.refresh_from_db()

        try:
            if paiement_stripe.status == Paiement_stripe.VALID or paiement_stripe.traitement_en_cours:
                messages.success(request,
                                 _('Payment confirmed. Tickets sent to your email. You can also view your tickets through "My account > Bookings".'))
            # Déja traité et validé.
            elif paiement_stripe.status == Paiement_stripe.PENDING:
                messages.add_message(request, messages.WARNING, _(f"Your payment is awaiting validation."))
            else:
                messages.add_message(request, messages.WARNING,
                                     _(f"An error has occurred, please contact the administrator."))
        except MessageFailure as e:
            # Surement un test unitaire, les messages plantent a travers la Factory Request
            pass
        except Exception as e:
            raise e

        # ex new method
        # paiement_stripe_refreshed = paiement_stripe_reservation_validator(request, paiement_stripe)

        if request.user.is_authenticated:
            return redirect('/my_account/my_reservations/')
        return redirect('/event/')

    def get_permissions(self):
        # if self.action in ['create']:
        #     permission_classes = [permissions.IsAuthenticated]
        # else:
        permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]


'''
@require_GET
def agenda(request):
    template_context = get_context(request)
    template_context['events'] = Event.objects.all()
    return render(request, "htmx/views/home.html", context=template_context)


@require_GET
def event(request: HttpRequest, slug) -> HttpResponse:
    event = get_object_or_404(Event, slug=slug)
    template_context = get_context(request)
    template_context['event'] = event
    return render(request, "htmx/views/event.html", context=template_context)


def validate_event(request):
    if request.method == 'POST':
        print("-> validate_event, méthode POST !")
        # range-start-index - range-end-index, date-index 
        data = dict(request.POST.lists())
        print(f"data = {data}")

        # validé / pas validé retourner un message
        dev_validation = True

        if dev_validation == False:
            messages.add_message(request, messages.WARNING, "Le message d'erreur !")

        if dev_validation == True:
            messages.add_message(request, messages.SUCCESS, "Réservation validée !")

    return redirect('home')

'''


def modal(request, level="info", title='Information', content: str = None):
    context = {
        "modal_message": {
            "type": level,
            "title": title,
            "content": content,
        }
    }
    return render(request, "htmx/components/modal_message.html", context=context)


class Badge(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]

    def list(self, request: HttpRequest):
        template_context = get_context(request)
        template_context["badges"] = Product.objects.filter(categorie_article=Product.BADGE, publish=True)
        template_context["account_tab"] = "punchclock"
        return render(request, "reunion/views/account/punchclock.html", context=template_context)

    @action(detail=True, methods=['GET'])
    def badge_in(self, request: HttpRequest, pk):
        product = get_object_or_404(Product, uuid=pk)
        user = request.user
        fedowAPI = FedowAPI()
        transaction = fedowAPI.badge.badge_in(user, product)

        messages.add_message(request, messages.SUCCESS, _(f"Check in registered!"))

        return render(request, "reunion/partials/account/badge_switch.html", context={})

    @action(detail=False, methods=['GET'])
    def check_out(self, request: HttpRequest):
        template_context = get_context(request)
        fedowAPI = FedowAPI()
        messages.add_message(request, messages.SUCCESS, _(f"Check out registered!"))
        return HttpResponseClientRedirect(request.headers['Referer'])

    def get_permissions(self):
        if self.action in ['retrieve']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]


class MembershipMVT(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]

    # def get_federated_products(self, tags=None, search=None, page=1):
    #     pass

    def create(self, request):
        logger.info(f"new membership : {request.data}")
        membership_validator = MembershipValidator(data=request.data, context={'request': request})
        if not membership_validator.is_valid():
            logger.error(f"MembershipViewset CREATE ERROR : {membership_validator.errors}")
            error_messages = [str(item) for sublist in membership_validator.errors.values() for item in sublist]
            messages.add_message(request, messages.ERROR, error_messages)
            return HttpResponseClientRedirect(request.headers['Referer'])

        # Le formulaire est valide.
        # Vérification de la demande de fomulaire supplémentaire avec Formbricks
        as_formbricks = membership_validator.price.product.formbricksform.exists()
        if as_formbricks:
            formbicks_form: FormbricksForms = membership_validator.price.product.formbricksform.first()
            formbricks_config = FormbricksConfig.get_solo()
            membership: Membership = membership_validator.membership
            checkout_stripe = membership_validator.checkout_stripe_url
            context = {'form': {'apiHost': formbricks_config.api_host,
                                'trigger_name': formbicks_form.trigger_name,
                                'environmentId': formbicks_form.environmentId, },
                       'membership': membership,
                       'checkout_stripe': checkout_stripe,
                       }

            return render(request, "reunion/views/membership/formbricks.html", context=context)
        #
        # if formbricks.api_host and formbricks.api_key:
        # Une configuration formbricks à été trouvé.

        # Validation manuelle demandée ?
        logger.info(f"membership_validator.price.manual_validation : {membership_validator.price.manual_validation}")
        if membership_validator.price.manual_validation:
            membership: Membership = membership_validator.membership
            # Marque la fiche comme nécessitant une validation manuelle et place l'état sur "en attente"
            membership.state = Membership.ADMIN_WAITING
            membership.save(update_fields=["state"])

            # Envoyer un mail à l'admin et à l'utilisateur pour les prévenir (via Celery)
            try:
                send_membership_pending_admin.delay(str(membership.uuid))
            except Exception as e:
                logger.error(f"Erreur d'enqueue send_membership_pending_admin: {e}")
            try:
                send_membership_pending_user.delay(str(membership.uuid))
            except Exception as e:
                logger.error(f"Erreur d'enqueue send_membership_pending_user: {e}")

            # Message de confirmation à l'utilisateur
            try:
                messages.add_message(request, messages.SUCCESS,
                                     _("Votre demande d'adhésion a bien été enregistrée et est en attente de validation."))
            except Exception:
                pass

            # Dans le cas d'une validation manuelle, on affiche un message dans l'offcanvas via un template partiel
            context = {'membership': membership}
            return render(request, "reunion/views/membership/pending_manual_validation.html", context=context)

        return HttpResponseClientRedirect(membership_validator.checkout_stripe_url)

    def list(self, request: HttpRequest):
        template_context = get_context(request)

        # Récupération de tout les produits adhésions de la fédération
        tenants = [fed.tenant for fed in FederatedPlace.objects.filter(membership_visible=True)]
        federated_tenant_dict = []
        for tenant in tenants:
            with tenant_context(tenant):
                config = Configuration.get_solo()
                federated_tenant_dict.append({
                    'name': config.organisation,
                    'short_description': config.short_description,
                    'domain': tenant.get_primary_domain().domain,
                    'img_url': config.img.hdr.url if config.img else None,
                })

        template_context['federated_tenants'] = federated_tenant_dict
        template_context['products'] = Product.objects.filter(categorie_article=Product.ADHESION,
                                                              publish=True).prefetch_related('tag')

        return render(
            request, "reunion/views/membership/list.html",
            context=template_context,
        )

    @action(detail=False, methods=['GET'])
    def embed(self, request):
        template_context = get_context(request)
        template_context['products'] = Product.objects.filter(categorie_article=Product.ADHESION,
                                                              publish=True).prefetch_related('tag')
        template_context['embed'] = True
        response = render(
            request, "reunion/views/membership/list.html",
            context=template_context,
        )
        # Pour rendre la page dans un iframe, on vide le header X-Frame-Options pour dire au navigateur que c'est ok.
        response['X-Frame-Options'] = ''
        return response

    def get_federated_membership_url(self, uuid=uuid):
        config = Configuration.get_solo()
        # Récupération de tous les évènements de la fédération
        tenants = [tenant for tenant in config.federated_with.all()]
        tenants.append(connection.tenant)
        for tenant in set(tenants):
            with tenant_context(tenant):
                try:
                    product = Product.objects.get(uuid=uuid, categorie_article=Product.ADHESION, publish=True)
                    url = f"https://{tenant.get_primary_domain().domain}/memberships/{product.uuid}"
                    return url
                except Product.DoesNotExist:
                    continue

        return False

    def retrieve(self, request, pk):
        '''
        La fonction qui va chercher le formulaire d'inscription.
        - Redirige vers le bon tenant si il faut
        - Fait apparaitre formbricks si besoin
        - Renvoie une page 404 personnalisée si le produit n'existe pas
        '''
        try:
            # On essaye sur ce tenant :
            product = Product.objects.get(uuid=pk, categorie_article=Product.ADHESION, publish=True)
        except Product.DoesNotExist:
            try:
                # Il est possible que ça soit sur un autre tenant ?
                url = self.get_federated_membership_url(uuid=pk)
                if url:
                    return HttpResponseClientRedirect(url)
                else:
                    # Si le produit n'existe pas dans les tenants fédérés, on affiche la page 404 personnalisée
                    context = get_context(request)
                    return render(request, "reunion/views/membership/404.html", context=context, status=404)
            except Exception as e:
                # En cas d'erreur lors de la recherche dans les tenants fédérés, on affiche la page 404 personnalisée
                context = get_context(request)
                return render(request, "reunion/views/membership/404.html", context=context, status=404)
        except Exception as e:
            # Pour toute autre erreur, on affiche la page 404 personnalisée
            context = get_context(request)
            return render(request, "reunion/views/membership/404.html", context=context, status=404)

        context = get_context(request)
        context['product'] = product
        return render(request, "reunion/views/membership/form.html", context=context)

    @action(detail=True, methods=['GET'])
    def get_checkout_for_membership(self, request, pk):
        membership = get_object_or_404(Membership, uuid=uuid.UUID(pk))
        if membership.state != Membership.ADMIN_VALID:
            raise Exception("not admin valid state")
        checkout_url = MembershipValidator.get_checkout_stripe(membership, custom_amount=membership.contribution_value)
        logger.info(f"get_checkout_for_membership : {checkout_url}")
        return redirect(checkout_url)
        # return HttpResponseClientRedirect(checkout_url)

    @action(detail=True, methods=['POST'])
    def admin_accept(self, request, pk):
        """Accept a membership requiring manual validation and send the checkout link to the member.
        Only accessible to tenant administrators from the admin UI.
        """
        user = request.user
        tenant = request.tenant

        try:
            is_admin = user.is_authenticated and hasattr(user, 'is_tenant_admin') and user.is_tenant_admin(tenant)
        except Exception:
            is_admin = False
        if not is_admin:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        membership = get_object_or_404(Membership, uuid=uuid.UUID(pk))
        # Update state to admin validated
        if membership.state != Membership.ADMIN_WAITING:
            messages.add_message(request, messages.WARNING, _("Membership not in waiting state."))
            referer = request.headers.get('Referer') or f"/admin/BaseBillet/membership/{membership.pk}/change/"
            return HttpResponseClientRedirect(referer)

        membership.state = Membership.ADMIN_VALID
        membership.save(update_fields=["state"])

        # Send payment link email to user via Celery
        try:
            send_membership_payment_link_user.delay(str(membership.uuid))
        except Exception as e:
            logger.error(f"Erreur d'enqueue send_membership_payment_link_user: {e}")

        try:
            messages.add_message(request, messages.SUCCESS,
                                 _("L'adhésion a été acceptée. Un email de paiement a été envoyé."))
        except Exception:
            pass

        # If HTMX request, return success partial to replace the button area
        if request.headers.get('HX-Request'):
            return render(request, "admin/membership/partials/admin_accept_success.html",
                          context={"membership": membership})

        referer = request.headers.get('Referer') or f"/admin/BaseBillet/membership/{membership.pk}/change/"
        return HttpResponseClientRedirect(referer)

    @action(detail=True, methods=['GET'])
    def stripe_return(self, request, pk, *args, **kwargs):
        # Le retour de stripe des users.
        # Il est possible que le update_checkout_status soit déja fait en post
        # par /api/webhook_stripe de ApiBillet.views.Webhook_stripe
        paiement_stripe = get_object_or_404(Paiement_stripe, uuid=pk)
        paiement_stripe.update_checkout_status()
        paiement_stripe.refresh_from_db()

        try:
            if paiement_stripe.traitement_en_cours:
                messages.add_message(request, messages.SUCCESS,
                                     _(f"Your payment has been validated and is being processed. Thank you very much!"))
            elif paiement_stripe.status == Paiement_stripe.VALID:
                messages.add_message(request, messages.SUCCESS,
                                     _(f"Your subscription has been validated. You will receive a confirmation email. Thank you very much!"))
            elif paiement_stripe.status == Paiement_stripe.PENDING:
                messages.add_message(request, messages.WARNING, _(f"Your payment is awaiting validation."))
            else:
                messages.add_message(request, messages.WARNING,
                                     _(f"An error has occurred, please contact the administrator."))
        except MessageFailure as e:
            # Surement un test unitaire, les messages plantent a travers la Factory Request
            pass
        except Exception as e:
            raise e

        return redirect('/memberships/')

    @action(detail=True, methods=['GET'])
    def invoice(self, request, pk):
        '''
        - lien "recevoir une facture" dans le mail de confirmation
        - Bouton d'action "générer une facture" dans l'admin Adhésion
        '''
        membership = get_object_or_404(Membership, pk=pk)
        pdf_binary = create_membership_invoice_pdf(membership)
        if not pdf_binary:
            return HttpResponse(_('PDF generation error'), status=500)

        response = HttpResponse(pdf_binary, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="facture.pdf"'
        return response

    @action(detail=True, methods=['GET'])
    def invoice_to_mail(self, request, pk):
        '''
        - Bouton action "Envoyer une facture par mail" dans admin adhésion
        '''
        membership = get_object_or_404(Membership, pk=pk)
        send_membership_invoice_to_email.delay(str(membership.uuid))
        return Response("sended", status=status.HTTP_200_OK)

    def get_permissions(self):
        if self.action in ['invoice_to_mail', 'admin_accept']:
            permission_classes = [TenantAdminPermission, ]

        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]


class Tenant(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]
    # Tout le monde peut créer un tenant, sous reserve d'avoir validé son compte stripe
    permission_classes = [permissions.AllowAny, ]

    @action(detail=False, methods=['GET', 'POST'])
    def new(self, request, *args, **kwargs):
        """
        Le formulaire de création de nouveau tenant
        """
        context = get_context(request)
        context['email_query_params'] = request.query_params.get('email') if request.query_params.get('email') else ""
        context['name_query_params'] = request.query_params.get('name') if request.query_params.get('name') else ""

        return render(request, "reunion/views/tenant/new_tenant.html", context=context)

    @action(detail=False, methods=['POST'])
    def create_waiting_configuration(self, request, *args, **kwargs):
        """
        Reception du formulaire de création de nouveau tenant
        Création d'un objet waiting configuration
        Envoi du mail qui invite à la création d'un compte Stripe
        """
        new_tenant = TenantCreateValidator(data=request.data, context={'request': request})
        logger.info(new_tenant.initial_data)
        if not new_tenant.is_valid():
            for error in new_tenant.errors:
                messages.add_message(request, messages.ERROR, f"{error} : {new_tenant.errors[error][0]}")
            return HttpResponseClientRedirect(request.headers['Referer'])

        # Création d'un objet waiting_configuration
        validated_data = new_tenant.validated_data
        waiting_configuration = WaitingConfiguration.objects.create(
            organisation=validated_data['name'],
            email=validated_data['email'],
            laboutik_wanted=validated_data['laboutik'],
            payment_wanted=validated_data['payment_wanted'],
            # id_acc_connect=id_acc_connect,
            dns_choice=validated_data['dns_choice'],
            site_web=validated_data['website'],
            short_description=validated_data['short_description'],
        )
        # Envoi d'un mail pour vérifier le compte. Un lien vers stripe sera créé
        # new_tenant_mailer.delay(waiting_config_uuid=str(waiting_configuration.uuid))
        new_tenant_mailer.delay(waiting_config_uuid=str(waiting_configuration.uuid))

        try:
            meta = Client.objects.filter(categorie=Client.META).first()
            with tenant_context(meta):
                send_to_ghost_email.delay(validated_data['email'], name=validated_data['name'])
        except Exception as e:
            logger.error(f"new_tenant send_to_ghost_email ERROR : {e}")

        return render(request, "reunion/views/tenant/create_waiting_configuration_THANKS.html", context={})

    @action(detail=True, methods=['GET'])
    def emailconfirmation_tenant(self, request, pk):
        """
        Lien de vérification de demande de création de nouveau tenant
        Mail envoyé par tasks.new_tenant_mailer
        """
        signer = TimestampSigner()
        try:
            wc_pk = signer.unsign(urlsafe_base64_decode(pk).decode('utf8'), max_age=(3600 * 24 * 30))  # 30 jours
            wc = WaitingConfiguration.objects.get(uuid=wc_pk)
            wc.email_confirmed = True
            wc.save()

            # Idempotent behavior: if the tenant was already created, redirect directly
            if wc.tenant:
                primary_domain = f"https://{wc.tenant.get_primary_domain().domain}"
                user = get_or_create_user(wc.email, send_mail=True)
                return redirect(primary_domain)

            # Si assez de tenant en attentent de création existent :
            if Client.objects.filter(categorie=Client.WAITING_CONFIG).exists():
                tenant = wc.create_tenant()
                primary_domain = f"https://{tenant.get_primary_domain().domain}"
                user = get_or_create_user(wc.email, send_mail=False)
                token = user.get_connect_token()
                connexion_url = f"{primary_domain}/emailconfirmation/{token}"
                return redirect(connexion_url)

            else:
                context = get_context(request)
                return render(request, "reunion/views/tenant/create_waiting_configuration_MAIL_CONFIRMED.html",
                              context=context)
        except UnicodeDecodeError as e:
            messages.error(request, _("Invalid token. Please request a new confirmation email."))
            return redirect('/')

    @action(detail=True, methods=['GET'])
    def onboard_stripe(self, request, pk):
        """
        Requete provenant du mail envoyé après la création d'une configuration en attente
        Fabrication du lien stripe onboard
        """
        waiting_config = get_object_or_404(WaitingConfiguration, pk=pk)
        tenant = connection.tenant
        tenant_url = tenant.get_primary_domain().domain

        rootConf = RootConfiguration.get_solo()
        stripe.api_key = rootConf.get_stripe_api()

        if not waiting_config.id_acc_connect:
            acc_connect = stripe.Account.create(
                type="standard",
                country="FR",
            )
            id_acc_connect = acc_connect.get('id')
            waiting_config.id_acc_connect = id_acc_connect
            waiting_config.save()

        account_link = stripe.AccountLink.create(
            account=waiting_config.id_acc_connect,
            refresh_url=f"https://{tenant_url}/tenant/{waiting_config.id_acc_connect}/onboard_stripe_return/",
            return_url=f"https://{tenant_url}/tenant/{waiting_config.id_acc_connect}/onboard_stripe_return/",
            type="account_onboarding",
        )

        url_onboard = account_link.get('url')
        return redirect(url_onboard)

    @action(detail=True, methods=['GET'])
    def onboard_stripe_return(self, request, pk):
        """
        Return url après avoir terminé le onboard sur stripe
        Vérification que le mail soit bien le même (cela nous confirme qu'il existe bien, Stripe impose une double auth)
        Vérification que le formulaire a bien été complété (detail submitted)
        Envoi un mail à l'administrateur ROOT de l'insatnce TiBillet pour prévenir, vérifier, et lancer la création du tenant à la main.
        """
        details_submitted, waiting_config = False, False
        id_acc_connect = pk
        # La clé du compte principal stripe connect
        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        # Récupération des info lié au lieu via sont id account connec
        try:
            info_stripe = stripe.Account.retrieve(id_acc_connect)
            details_submitted = info_stripe.details_submitted
        except Exception as e:
            logger.error(f"onboard_stripe_return. id_acc_connect : {id_acc_connect}, erreur stripe : {e}")
            raise Http404

        if details_submitted:
            waiting_config = WaitingConfiguration.objects.get(id_acc_connect=id_acc_connect)
            waiting_config.onboard_stripe_finished = True
            waiting_config.save()
            # Envoie du mail aux superadmins
            new_tenant_after_stripe_mailer.delay(waiting_config.pk)

        context = get_context(request)
        context["details_submitted"] = details_submitted
        return render(request, "reunion/views/tenant/after_onboard_stripe.html", context=context)

        #     _("Your Stripe account does not seem to be valid. "
        #       "\nPlease complete your Stripe.com registration before creating a new TiBillet space."))
        # return redirect('/tenant/new/')

    '''
    @action(detail=False, methods=['GET'])
    def emailconfirmation(self, request, pk):
        """
        Requete provenant du mail envoyé après la création d'un tenant
        """
        wc = WaitingConfiguration.objects.get(pk=pk)
        wc.email_confirmed = True
        wc.save()
        context = get_context(request)
        return render(request, "reunion/views/tenant/create_waiting_configuration_MAIL_CONFIRMED.html", context=context)
    '''

    @action(detail=False, methods=['GET'])
    def onboard_stripe_from_config(self, request):
        """
        Requete provenant du mail envoyé après la création d'une configuration en attente
        Fabrication du lien stripe onboard
        """
        config = Configuration.get_solo()
        id_acc_connect = config.get_stripe_connect_account()
        tenant = connection.tenant
        tenant_url = tenant.get_primary_domain().domain

        rootConf = RootConfiguration.get_solo()
        stripe.api_key = rootConf.get_stripe_api()

        try:
            account_link = stripe.AccountLink.create(
                account=id_acc_connect,
                refresh_url=f"https://{tenant_url}/tenant/{id_acc_connect}/onboard_stripe_return_from_config/",
                return_url=f"https://{tenant_url}/tenant/{id_acc_connect}/onboard_stripe_return_from_config/",
                type="account_onboarding",
            )

        except stripe._error.InvalidRequestError:
            # Stripe account not valid, on le vide et on relance
            config.stripe_connect_account = None
            config.save()
            id_acc_connect = config.get_stripe_connect_account()
            account_link = stripe.AccountLink.create(
                account=id_acc_connect,
                refresh_url=f"https://{tenant_url}/tenant/{id_acc_connect}/onboard_stripe_return_from_config/",
                return_url=f"https://{tenant_url}/tenant/{id_acc_connect}/onboard_stripe_return_from_config/",
                type="account_onboarding",
            )

        url_onboard = account_link.get('url')
        return redirect(url_onboard)

    @action(detail=True, methods=['GET'])
    def onboard_stripe_return_from_config(self, request, pk):
        """
        Return url après avoir terminé le onboard sur stripe
        Vérification que le mail soit bien le même (cela nous confirme qu'il existe bien, Stripe impose une double auth)
        Vérification que le formulaire a bien été complété (detail submitted)
        Envoi un mail à l'administrateur ROOT de l'insatnce TiBillet pour prévenir, vérifier, et lancer la création du tenant à la main.
        """
        details_submitted, waiting_config = False, False
        id_acc_connect = pk
        # La clé du compte principal stripe connect
        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        # Récupération des infos liées au lieu via son id account connec
        try:
            info_stripe = stripe.Account.retrieve(id_acc_connect)
            details_submitted = info_stripe.details_submitted
        except Exception as e:
            logger.error(f"onboard_stripe_return. id_acc_connect : {id_acc_connect}, erreur stripe : {e}")
            raise Http404

        config = Configuration.get_solo()
        if info_stripe and info_stripe.get('payouts_enabled'):
            config.stripe_payouts_enabled = info_stripe.get('payouts_enabled')
            config.save()

        context = get_context(request)
        context["details_submitted"] = details_submitted
        return render(request, "reunion/views/tenant/after_onboard_stripe.html", context=context)

        #     _("Your Stripe account does not seem to be valid. "
        #       "\nPlease complete your Stripe.com registration before creating a new TiBillet space."))
        # return redirect('/tenant/new/')
