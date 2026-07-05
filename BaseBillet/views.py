import json
import logging
import os
import re
import uuid

from Administration.utils import clean_text
from datetime import date as date_type, timedelta
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
from django.db import connection, IntegrityError, transaction as db_transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, HttpRequest, Http404, HttpResponseRedirect
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
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
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from ApiBillet.permissions import TenantAdminPermission, CanInitiatePaymentPermission, CanCreateEventPermission
from ApiBillet.serializers import get_or_create_price_sold, dec_to_int
from AuthBillet.models import TibilletUser, Wallet, HumanUser
from AuthBillet.serializers import MeSerializer
from AuthBillet.utils import get_or_create_user
from AuthBillet.views import activate
from BaseBillet.models import Configuration, Ticket, Product, Event, Tag, Paiement_stripe, Membership, Reservation, \
    FormbricksConfig, FormbricksForms, FederatedPlace, Carrousel, LigneArticle, PriceSold, \
    Price, ProductSold, PaymentMethod, PostalAddress, SaleOrigin, ProductFormField, GhostConfig, BrevoConfig, \
    FederationConfiguration
from BaseBillet.tasks import create_membership_invoice_pdf, send_membership_invoice_to_email, \
    contact_mailer, send_to_ghost_email, send_sale_to_laboutik, \
    send_payment_success_admin, send_payment_success_user, send_reservation_cancellation_user, \
    send_ticket_cancellation_user, send_email_generique, \
    send_membership_pending_admin, send_membership_pending_user, send_membership_payment_link_user
from BaseBillet.validators import LoginEmailValidator, MembershipValidator, LinkQrCodeValidator, TenantCreateValidator, \
    ReservationValidator, ContactValidator, QrCodeScanPayNfcValidator, EventQuickCreateSerializer, \
    PaiementHorsLigneSerializer, WizardPlaceSelectSerializer, WizardPlaceMapSerializer, \
    WizardEventSerializer
from Administration.utils import clean_html as admin_clean_html
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
def _contexte_page_erreur(request):
    """
    Contexte pour les pages d'erreur 404/500 : celui de get_context, qui
    résout base_template selon le skin du tenant ET selon HTMX (shell complet
    en navigation normale, fragment headless en réponse HTMX — la page
    d'erreur devient ainsi swappable par le listener htmx:beforeSwap des
    shells). Repli minimal si get_context échoue (tenant cassé, DB down :
    on veut TOUJOURS pouvoir afficher une page d'erreur).
    / Context for the 404/500 error pages: get_context's one, which resolves
    base_template by tenant skin AND by HTMX (full shell on normal navigation,
    headless fragment on HTMX responses — making the error page swappable by
    the shells' htmx:beforeSwap listener). Minimal fallback if get_context
    fails (broken tenant, DB down: an error page must ALWAYS render).

    LOCALISATION : BaseBillet/views.py
    """
    try:
        return get_context(request)
    except Exception as erreur_contexte:
        logger.warning(f"page erreur : get_context indisponible, repli classic ({erreur_contexte})")
        return {"base_template": "pages/classic/shell.html", "main_nav": []}


def handler404(request, exception=None):
    """
    404 personnalisée, consciente du skin et d'HTMX (actif quand DEBUG=0).
    / Custom 404, skin-aware and HTMX-aware (active when DEBUG=0).

    LOCALISATION : BaseBillet/views.py — déclaré dans TiBillet/urls_tenants.py
    """
    template_context = _contexte_page_erreur(request)
    return render(request, '404.html', template_context, status=404)


def handler500(request, exception=None):
    """
    Custom 500 error handler that passes the exception to the template.
    Enrichi (2026-07-05) : contexte de get_context pour que la page 500 prenne
    le skin du tenant et soit swappable en HTMX (cf. _contexte_page_erreur).
    / Enriched: get_context's context so the 500 page follows the tenant skin
    and is HTMX-swappable.
    """
    import sys
    exc_type, exc_value, exc_traceback = sys.exc_info()

    # Use the passed exception if available, otherwise use the one from sys.exc_info()
    exception_to_use = exception if exception else exc_value

    context = _contexte_page_erreur(request)
    context.update({
        'exception': str(exception_to_use) if exception_to_use else None,
        'type_exception': type(exception_to_use).__name__ if exception_to_use else None,
    })
    logger.info({'exception': context.get('exception'), 'type_exception': context.get('type_exception')})
    return render(request, '500.html', context, status=500)


def encode_uid(pk):
    return force_str(urlsafe_base64_encode(force_bytes(pk)))


def get_skin_courant():
    """
    Retourne le skin actif du tenant courant, lu sur le singleton
    pages.ConfigurationSite (deplace depuis BaseBillet.Configuration).
    Defaut "reunion" si indisponible (table absente, schema public, etc.).
    / Returns the current tenant's active skin, read from the
    pages.ConfigurationSite singleton (moved from BaseBillet.Configuration).
    Defaults to "reunion" if unavailable (missing table, public schema, etc.).
    """
    try:
        from pages.models import ConfigurationSite
        skin = ConfigurationSite.get_solo().skin
        return skin or "reunion"
    except Exception:
        return "reunion"


# NOTE migration skins (CHANTIER-08) : l'ancien resolver get_skin_template a été
# supprimé. Toute résolution de gabarit passe par pages.services.gabarit_skin()
# (pages/<skin>/… avec fallback pages/classic/). Contrat complet :
# TECH_DOC/SESSIONS/SKINS/CONTRAT-DE-SKIN.md
# / The legacy get_skin_template resolver was removed. All skin template
# resolution goes through pages.services.gabarit_skin().


def get_context(request):
    # context_cached = cache.get(f'get_context_{connection.tenant.uuid}')
    # if context_cached:
    #     return context_cached

    config = Configuration.get_solo()
    crowd_config = CrowdConfig.get_solo()

    # SYSTÈME DE SKIN (CHANTIER-01) : le squelette est résolu par le nouveau
    # resolver unifié pages.services.gabarit_skin(). Si le skin fournit le
    # gabarit (pages/<skin>/shell.html), on l'utilise. Sinon fallback
    # automatique sur le socle pages/classic/.
    # / SKIN SYSTEM: the skeleton is resolved by the unified resolver
    # pages.services.gabarit_skin(), with automatic fallback to pages/classic/.
    from pages.services import gabarit_skin
    if request.htmx:
        base_template = gabarit_skin("headless.html")
    else:
        base_template = gabarit_skin("shell.html")

    serialized_user = MeSerializer(request.user).data if request.user.is_authenticated else None

    # Le lien "Fédération"
    meta_url = cache.get('meta_url')
    if not meta_url:
        meta = Client.objects.filter(categorie=Client.META).first()
        if meta:
            meta_url = f"https://{meta.get_primary_domain().domain}"
            cache.set('meta_url', meta_url, 3600 * 24)

    # Formbricks existe ?
    formbricks_config = FormbricksConfig.get_solo()

    context = {
        "base_template": base_template,
        "page": request.GET.get('page', 1),
        "tags": request.GET.getlist('tag'),
        "url_name": request.resolver_match.url_name if request.resolver_match else None,
        "user": request.user,
        "profile": serialized_user,
        "config": config,
        "crowd_config": crowd_config,
        "meta_url": meta_url,
        "header": True,
        # "tenant": connection.tenant,
        "formbricks_api_host": formbricks_config.api_host,
        "mode_test": True if os.environ.get('TEST') == '1' else False,
        "loading_delay": 400,
        "carrousel_event_list": Carrousel.objects.filter(on_event_list_page=True).order_by('order'),
        "main_nav": []
    }

    navbar: list = context["main_nav"]

    # « Le Faire Festival » et « Infos pratiques » NE sont PLUS codes en dur ici :
    # ce sont desormais des Page de l'app pages (ajoutees plus bas via la boucle
    # des pages publiees). La navbar n'a donc plus de hardcode specifique au skin.
    # / "Le Faire Festival" and "Infos pratiques" are NO LONGER hardcoded here: they
    # are now pages-app Page objects (added below via the published-pages loop).

    # ORDRE DE LA NAVBAR : les pages de l'app pages d'abord (ajoutees plus bas
    # via navbar_pages, inseres EN TETE), puis reseau/crowdfunding, et EN FIN de
    # menu : agenda, adhesions, contact (le contact est code dans le gabarit
    # navbar, toujours dernier).
    # / NAVBAR ORDER: pages-app pages first (built below in navbar_pages and
    # inserted at the head), then network/crowdfunding, and at the END of the
    # menu: agenda, memberships, contact (contact lives in the navbar template,
    # always last).

    # Activation du menu "Réseau local" : pilotee UNIQUEMENT par le flag
    # config.module_federation. Le test d'existence de FederatedPlace est
    # devenu superflu depuis le support des entrantes : un tenant sans
    # FederatedPlace sortante peut quand meme avoir des voisins entrants
    # (autres tenants qui le federent), donc afficher /federation/ a du sens.
    # Si jamais le tenant n'a vraiment aucun voisin, la vue affiche le
    # message "Aucune autre place federee pour le moment.".
    # / "Local network" menu activation: driven ONLY by the
    # config.module_federation flag. The existence test on FederatedPlace
    # became superfluous when we added incoming-edge support: a tenant with
    # no outgoing FederatedPlace can still have incoming neighbors, so
    # showing /federation/ makes sense. If the tenant has no neighbor at
    # all, the view shows the "No other federated place" message.
    if config.module_federation:
        navbar.append({
            'name': 'federation',
            'url': '/federation/',
            'label': _('Local network'),
            'icon': 'diagram-2-fill'
        })

    if crowd_config.active and Initiative.objects.exists() and config.module_crowdfunding:
        navbar.append({
            'name': f'crowd-list',
            'url': '/contrib/',
            'label': f'{crowd_config.title}',
            'icon': 'people-fill'
        })

    # Pages publiees du tenant (app pages), ajoutees a la navigation.
    # La page d'accueil (est_accueil) pointe vers la racine "/" ; les autres
    # pages vers /<slug>/. Le tout uniquement si le module pages est actif.
    # Import local pour eviter un import circulaire avec pages.views.
    # / Tenant published pages (pages app), added to the navigation.
    # The home page (est_accueil) links to the root "/"; the other pages to
    # /<slug>/. Only if the pages module is active.
    # Local import to avoid a circular import with pages.views.
    navbar_pages: list = []
    if config.module_pages:
        from pages.models import Page

        pages_publiees = (
            Page.objects.filter(publie=True)
            .select_related("parent")
            .order_by("position", "titre")
        )
        # Index des sous-pages publiees par parent (uuid) pour les menus deroulants.
        # / Index of published sub-pages by parent (uuid) for the dropdown menus.
        enfants_par_parent: dict = {}
        for page_publiee in pages_publiees:
            if page_publiee.parent_id:
                enfants_par_parent.setdefault(page_publiee.parent_id, []).append(page_publiee)

        for page_publiee in pages_publiees:
            # Les sous-pages sont rendues DANS le dropdown de leur parent, pas a plat.
            # / Sub-pages are rendered IN their parent's dropdown, not flat.
            if page_publiee.parent_id:
                continue
            url_page = "/" if page_publiee.est_accueil else f"/{page_publiee.slug}/"
            navbar_pages.append({
                'name': f'page-{page_publiee.slug}',
                'url': url_page,
                'label': page_publiee.titre,
                'icon': 'house-door' if page_publiee.est_accueil else 'file-earmark-text',
                # Sous-pages (menu deroulant) : liste vide si la page n'en a pas.
                # / Sub-pages (dropdown menu): empty list if the page has none.
                'children': [
                    {
                        'name': f'page-{enfant.slug}',
                        'url': f'/{enfant.slug}/',
                        'label': enfant.titre,
                        'icon': 'file-earmark-text',
                    }
                    for enfant in enfants_par_parent.get(page_publiee.pk, [])
                ],
            })

    # Fin de menu, toujours dans cet ordre : agenda puis adhesions
    # (le bouton contact est dans le gabarit navbar, toujours apres eux).
    # / End of menu, always in this order: agenda then memberships
    # (the contact button lives in the navbar template, always after them).
    if config.module_billetterie:
        navbar.append({
            'name': 'event-list',
            'url': '/event/',
            'label': config.event_menu_name if config.event_menu_name else _('Calendar'),
            'icon': 'calendar-date'
        })

    if config.module_adhesion:
        navbar.append({
            'name': 'memberships_mvt',
            'url': '/memberships/',
            'label': config.membership_menu_name if config.membership_menu_name else _('Subscriptions'),
            'icon': 'person-badge'
        })

    # Assemblage final : pages en tete, puis le reste (reseau, crowdfunding,
    # agenda, adhesions). / Final assembly: pages first, then the rest.
    context["main_nav"] = navbar_pages + navbar

    # cache.set(f'get_context_{connection.tenant.uuid}', context, 10)
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
            if settings.TEST or settings.DEBUG:
                token = user.get_connect_token()
                base_url = connection.tenant.get_primary_domain().domain
                connexion_url = f"https://{base_url}/emailconfirmation/{token}"
                messages.add_message(request, messages.INFO, format_html(f"<a href='{connexion_url}'>TEST MODE</a>"))

            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

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
    except ValueError as e:
        # Message explicite venant du signal (réservation expirée, évènement complet)
        # L'utilisateur voit le message sur la page d'accueil après la redirection
        # / Explicit message from signal (expired reservation, full event)
        # / User sees the message on the homepage after redirect
        messages.add_message(request, messages.WARNING, str(e))
        return redirect('index')
    except Exception as e:
        logger.error(f"emailconfirmation error: {e}")
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
                template_context['base_template'] = 'fonctionnel/blank_base.html'
                # Logout au cas où on scanne les cartes à la suite.
                logout(request)
                return render(request, "fonctionnel/register.html", context=template_context)

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
            if settings.TEST or settings.DEBUG:
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
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

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
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

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
                return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

        # Opération de fusion entre la carte liée au qrcode et le wallet de l'user :
        qrcode_uuid = validator.validated_data['qrcode_uuid']
        linked_serialized_card = fedowAPI.NFCcard.linkwallet_cardqrcode(user=user, qrcode_uuid=qrcode_uuid)
        if not linked_serialized_card:
            # QR code inconnu de Fedow (carte non enregistrée / pas encore activée) ou
            # échec de la liaison. On affiche un message explicite et on s'arrête : sans
            # ce return, le code plus bas faisait linked_serialized_card['qrcode_uuid']
            # sur False → TypeError "'bool' object is not subscriptable" (500).
            # / Unknown QR code on Fedow side (card not registered / not activated yet) or
            # link failure. Show an explicit message and stop: without this return, the code
            # below did linked_serialized_card['qrcode_uuid'] on False → TypeError 500.
            messages.add_message(request, messages.ERROR,
                                 _("Cette carte n'est pas reconnue. Elle n'est peut-être pas encore activée."))
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

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

        return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

    def get_permissions(self):
        permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]


class SpecialAdminAction(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]
    permission_classes = [TenantAdminPermission, ]

    @action(detail=True, methods=['POST'])
    def toggle_user_right(self, request, pk):
        user = get_object_or_404(HumanUser, pk=pk)
        tenant = connection.tenant
        referer = request.headers.get('Referer') or f"/admin/AuthBillet/humanuser/{pk}/change/"
        logger.info(f"toggle_user_right : {request.data}")

        if request.GET.get('action') == 'client_admin':
            if user.client_admin.filter(pk=tenant.pk).exists():
                user.client_admin.remove(tenant)
                user.is_staff = False
                user.save(update_fields=['is_staff'])
                messages.info(request, _("Admin right removed"))
            else:
                user.client_admin.add(tenant)
                messages.success(request, _("Admin right granted: with great power comes great responsibility."))

        elif request.GET.get('action') == 'initiate_payment':
            if user.initiate_payment.filter(pk=tenant.pk).exists():
                user.initiate_payment.remove(tenant)
                messages.info(request, _("Right removed: initiate payment"))
            else:
                user.initiate_payment.add(tenant)
                messages.success(request, _("Right granted: initiate payment"))

        elif request.GET.get('action') == 'create_event':
            if user.create_event.filter(pk=tenant.pk).exists():
                user.create_event.remove(tenant)
                messages.info(request, _("Right removed: Event create"))
            else:
                user.create_event.add(tenant)
                messages.success(request, _("Right granted: Event create"))

        elif request.GET.get('action') == 'manage_crowd':
            if user.manage_crowd.filter(pk=tenant.pk).exists():
                user.manage_crowd.remove(tenant)
                messages.info(request, _("Right removed: Manage crowds"))
            else:
                user.manage_crowd.add(tenant)
                messages.success(request, _("Right granted: Manage crowds"))

        else:
            messages.error(request, _("No right selected"))

        return HttpResponseClientRedirect(referer)


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
                return render(request, "fonctionnel/connexion/partials/fullpage_inner.html", context=template_context)
            return render(request, "fonctionnel/connexion/fullpage.html", context=template_context)

        # POST: email submitted
        validator = LoginEmailValidator(data=request.POST)
        if not validator.is_valid():
            logger.error(validator.errors)
            template_context['errors'] = validator.errors
            template_context['email'] = request.POST.get('email', '')
            if request.htmx:
                return render(request, "fonctionnel/connexion/partials/fullpage_inner.html", context=template_context)
            return render(request, "fonctionnel/connexion/fullpage.html", context=template_context)

        email = validator.validated_data['email']
        user = get_or_create_user(email=email, send_mail=True, force_mail=True, next_url=next_url)

        # On success: swap only main content for HTMX and push URL
        return render(request, "fonctionnel/connexion/partials/confirmation_inner.html", context=template_context)

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
            # Session expirée pendant une navigation HTMX (onglets du compte en
            # hx-get) : un redirect() classique serait suivi EN SILENCE par le
            # XHR et la home serait swappée DANS l'onglet, URL inchangée.
            # HX-Redirect fait faire au navigateur une vraie navigation vers /.
            # / Session expired during an HTMX navigation (account tabs use
            # hx-get): a classic redirect() would be silently followed by the
            # XHR and the home page swapped INSIDE the tab, URL unchanged.
            # HX-Redirect makes the browser do a real navigation to /.
            if request.htmx:
                return HttpResponseClientRedirect('/?login=1')
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

        # Liste des tenants que l'utilisateur peut administrer
        # / List of tenants the user can administer
        user = request.user
        current_tenant = connection.tenant

        if user.is_superuser:
            # Superuser : ses client_admin + le tenant courant (toujours present)
            # / Superuser: their client_admin + current tenant (always included)
            admin_pks = set(user.client_admin.values_list('pk', flat=True))
            admin_pks.add(current_tenant.pk)
            tenants_admin = Client.objects.filter(
                pk__in=admin_pks
            ).prefetch_related('domains')
        else:
            tenants_admin = user.client_admin.prefetch_related('domains').all()

        template_context['tenants_admin'] = tenants_admin

        if not request.user.email_valid:
            logger.warning("User email not active")
            messages.add_message(request, messages.WARNING,
                                 _("Please validate your email to access all the features of your profile area."))

        return render(request, "fonctionnel/compte/index.html", context=template_context)

    @action(detail=False, methods=['GET'])
    def balance(self, request: HttpRequest):
        template_context = get_context(request)
        # Pas de header sur cette page
        template_context['header'] = False
        template_context['account_tab'] = 'balance'

        return render(request, "fonctionnel/compte/balance.html", context=template_context)

    @action(detail=False, methods=['GET'])
    def my_cards(self, request):
        fedowAPI = FedowAPI()
        cards = fedowAPI.NFCcard.retrieve_card_by_signature(request.user)
        context = {
            'cards': cards
        }
        return render(request, "fonctionnel/compte/partials/card_table.html", context=context)

    @action(detail=True, methods=['GET'], permission_classes=[TenantAdminPermission])
    def admin_my_cards(self, request, pk):
        fedowAPI = FedowAPI()
        user = get_object_or_404(HumanUser, pk=pk)
        cards = fedowAPI.NFCcard.retrieve_card_by_signature(user)
        wallet = fedowAPI.wallet.cached_retrieve_by_signature(user).validated_data
        tokens = [token for token in wallet.get('tokens') if token.get('asset_category') not in ['SUB', 'BDG']]

        # Transactions des 72 dernieres heures, via la signature de l'user de la fiche.
        # La signature retrouve tout l'historique du wallet (y compris les transactions
        # d'un ancien wallet ephemere fusionne : elles apparaissent via les actions FUS).
        # On encadre l'appel Fedow : s'il echoue, on n'affiche rien plutot que de casser la page.
        # / Last 72h transactions via the profile user's signature. The signature returns the
        # full wallet history (including a merged ephemeral wallet, shown as FUS actions).
        # The Fedow call is wrapped: on failure we show nothing instead of breaking the page.
        transactions_recentes = []
        try:
            transactions_paginees = fedowAPI.transaction.paginated_list_by_wallet_signature(user).validated_data
            limite_72h = timezone.now() - timedelta(hours=72)
            for transaction in transactions_paginees.get('results', []):
                date_transaction = transaction.get('datetime')
                if not (date_transaction and date_transaction >= limite_72h):
                    continue
                # On exclut les transactions d'adhesion (asset de categorie SUBSCRIPTION),
                # comme on exclut deja les adhesions du solde de tokens plus haut.
                # / Skip membership transactions (SUBSCRIPTION asset category), as we
                # already exclude memberships from the token balance above.
                asset_transaction = transaction.get('serialized_asset') or {}
                if asset_transaction.get('category') == 'SUB':
                    continue
                transactions_recentes.append(transaction)
        except Exception as erreur_fedow:
            logger.error(f"admin_my_cards : transactions Fedow indisponibles pour {user} : {erreur_fedow}")

        context = {
            'cards': cards,
            'tokens': tokens,
            'transactions': transactions_recentes,
            'actions_choices': TransactionSimpleValidator.TYPE_ACTION,
            'user_pk': pk,
        }
        return render(request, "admin/membership/wallet_info.html", context=context)

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

        return render(request, "fonctionnel/compte/reservations.html", context=context)

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
            try:
                fedowAPI = FedowAPI()
                lost_card_report = fedowAPI.NFCcard.lost_my_card_by_signature(user, number_printed=number_printed)
                if lost_card_report:
                    messages.add_message(request, messages.SUCCESS,
                                         _("Your wallet has been detached from this card. You can scan a new one to link it again."))
                else:
                    messages.add_message(request, messages.ERROR,
                                         _("Error when detaching your card. Contact an administrator."))
            except Exception as e:
                logger.error(f"admin_lost_my_card error: {e}")
                messages.add_message(request, messages.ERROR,
                                     _("Error when detaching your card. Contact an administrator."))
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

    @action(detail=True, methods=['GET'])
    def lost_my_card(self, request, pk):
        if request.user.email_valid:
            try:
                fedowAPI = FedowAPI()
                lost_card_report = fedowAPI.NFCcard.lost_my_card_by_signature(request.user, number_printed=pk)
                if lost_card_report:
                    messages.add_message(request, messages.SUCCESS,
                                         _("Your wallet has been detached from this card. You can scan a new one to link it again."))
                else:
                    messages.add_message(request, messages.ERROR,
                                         _("Error when detaching your card. Contact an administrator."))
            except Exception as e:
                logger.error(f"lost_my_card error: {e}")
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

        return render(request, "fonctionnel/compte/partials/token_table.html", context=context)

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
        return render(request, "fonctionnel/compte/partials/transaction_history.html", context=context)

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

        # On exclut le schema public : il ne contient pas les tables des TENANT_APPS
        # (BaseBillet_membership n'y existe pas). Si le Client public se retrouve dans
        # client_achat (cas du root/staff), l'iterer ferait planter toute la page
        # avec "relation BaseBillet_membership does not exist".
        # / Skip the public schema: it has no TENANT_APPS tables.
        for tenant in user.client_achat.exclude(schema_name='public'):
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
        return render(request, "fonctionnel/compte/membership/memberships.html", context=context)

    @action(detail=False, methods=['GET'])
    def card(self, request: HttpRequest) -> HttpResponse:
        context = get_context(request)
        context['account_tab'] = 'card'
        return render(request, "fonctionnel/compte/card.html", context=context)

    @action(detail=False, methods=['GET'])
    def profile(self, request: HttpRequest) -> HttpResponse:
        context = get_context(request)
        context['account_tab'] = 'profile'
        return render(request, "fonctionnel/compte/preferences.html", context=context)

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

    @action(detail=True, methods=['GET'], permission_classes=[CanInitiatePaymentPermission, ])
    def check_payment(self, request: HttpRequest, pk=None):
        user = request.user

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
        return render(request, "fonctionnel/qrcode_scan_pay/fragments/check_payment.html", context=context)

    @action(detail=False, methods=['GET'], permission_classes=[CanInitiatePaymentPermission, ])
    def get_generator(self, request: HttpRequest):

        user = request.user
        # GET de la route /qrcodegenerator
        # On livre le template qui permet de générer un qrcode
        template_context = get_context(request)
        return render(request, "fonctionnel/qrcode_scan_pay/generator.html", context=template_context)

    @action(detail=False, methods=['POST'], permission_classes=[CanInitiatePaymentPermission, ])
    def generate_qrcode(self, request: HttpRequest):
        # POST de la route /qrcodegenerator qui génère le qrcode
        data = request.POST
        logger.info(f"QRCODEGENERATOR POST : {data}")
        user = request.user

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
            metadata=json.dumps({"admin": str(request.user.email)}),
            sale_origin=SaleOrigin.QRCODE_MA,
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

        return render(request, "fonctionnel/qrcode_scan_pay/generator.html", context=template_context)

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
            return render(request, "fonctionnel/qrcode_scan_pay/scanner.html", context=template_context)

        # if request.method == 'POST' : # C'est le résultat du scanner
        #     import ipdb; ipdb.set_trace()

    @action(methods=['POST'], detail=False, permission_classes=[CanInitiatePaymentPermission, ])
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
                    sale_origin=SaleOrigin.NFC_MA,
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
        permissions.AllowAny, ])  # on permet a tout le monde de scanner un qrcode, mais si tu n'es pas loggué, on te redirige
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
            return render(request, "fonctionnel/qrcode_scan_pay/scanner.html", context=template_context)

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
                return render(request, "fonctionnel/qrcode_scan_pay/payment_error.html", context=template_context)

            logger.info(f"Processed LigneArticle: {ligne_article_uuid}")

        except LigneArticle.DoesNotExist:
            logger.error(f"No LigneArticle found with UUID: {ligne_article_uuid_hex}")
            template_context['error_message'] = _("Invalid QR code: payment not found")
            return render(request, "fonctionnel/qrcode_scan_pay/payment_error.html", context=template_context)

        except Exception as e:
            logger.error(f"Error processing QR code: {str(e)}")
            messages.add_message(request, messages.ERROR, _("Invalid QR code format"))
            return render(request, "fonctionnel/qrcode_scan_pay/scanner.html")

        # Check the wallet on fedow
        user = request.user
        from fedow_connect.fedow_api import FedowAPI
        fedow_api = FedowAPI()
        fedow_api.wallet.get_or_create_wallet(user)
        user_balance = fedow_api.wallet.get_total_fiducial_and_all_federated_token(user)
        template_context['user_balance'] = user_balance
        template_context['insufficient_funds'] = amount > user_balance

        # Render the payment validation template
        return render(request, "fonctionnel/qrcode_scan_pay/payment_validation.html", context=template_context)

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
            return render(request, "fonctionnel/qrcode_scan_pay/payment_error.html", context=template_context)

        except Exception as e:
            logger.error(f"Error processing QR code: {str(e)}")
            messages.add_message(request, messages.ERROR, _("Invalid QR code format"))
            return render(request, "fonctionnel/qrcode_scan_pay/scanner.html")

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
            return render(request, "fonctionnel/qrcode_scan_pay/insufficient_funds.html", context=template_context)

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
                    sale_origin=SaleOrigin.QRCODE_MA,
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

            return render(request, "fonctionnel/qrcode_scan_pay/payment_confirmation.html", context=template_context)


        except Exception as e:
            logger.error(f"Error validating payment: {str(e)}")
            template_context['error_message'] = _("Error validating payment")
            return render(request, "fonctionnel/qrcode_scan_pay/payment_error.html", context=template_context)

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
        return HttpResponseRedirect('https://tibillet.coop/')

    # Si le module pages est actif et qu'une page d'accueil (app pages) est
    # definie ET publiee, elle est servie sur la racine "/" a la place de la
    # home par defaut. Import local pour eviter un import circulaire.
    # / If the pages module is active and a published home page (pages app) is
    # set, it is served on the root "/" instead of the default home.
    # Local import to avoid a circular import.
    if Configuration.get_solo().module_pages:
        from pages.models import Page
        page_accueil = Page.objects.filter(est_accueil=True, publie=True).first()
        if page_accueil:
            from pages.views import rendre_page
            return rendre_page(request, page_accueil)

    template_context = get_context(request)

    # Slugs des pages CMS publiées : la vieille home ff (gabarit de repli)
    # conditionne ses boutons « Infos pratiques » / « Le Faire Festival » sur
    # cette liste — leurs routes en dur n'existent plus, seules les pages CMS
    # publiées répondent sur /<slug>/. Liste vide si le module est éteint.
    # / Published CMS page slugs: the legacy ff home (fallback template) shows
    # its buttons only when the matching CMS page is published — the hardcoded
    # routes are gone, only published CMS pages answer on /<slug>/.
    slugs_pages_publiees = []
    if Configuration.get_solo().module_pages:
        from pages.models import Page
        slugs_pages_publiees = list(Page.objects.filter(publie=True).values_list('slug', flat=True))
    template_context['slugs_pages_publiees'] = slugs_pages_publiees

    # Résolution du gabarit par le resolver unifié (CHANTIER-05).
    # / Unified skin resolver (skins migration).
    from pages.services import gabarit_skin
    template_path = gabarit_skin("vues/accueil.html")

    return render(request, template_path, context=template_context)


# NOTE nettoyage 2026-07-05 : les vues infos_pratiques() et le_faire_festival()
# ont été SUPPRIMÉES. Leurs routes avaient déjà été retirées de BaseBillet/urls.py :
# ces contenus sont des pages CMS de l'app pages (seedées par
# charger_demo_faire_festival), servies par le catch-all /<slug>/.
# / Cleanup note: the infos_pratiques() and le_faire_festival() views were
# REMOVED. Their routes were already gone from BaseBillet/urls.py: these
# contents are pages-app CMS pages served by the /<slug>/ catch-all.


class FederationViewset(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]
    permission_classes = [permissions.AllowAny]

    def list(self, request):
        """
        Affiche l'explorer (carte + liste) restreint au tenant courant
        et a ses lieux federes via FederatedPlace.
        / Renders the explorer (map + list) restricted to the current tenant
        and its federated places via FederatedPlace.

        LOCALISATION : BaseBillet/views.py — FederationViewset.list

        Reprend la meme source de donnees que le public /explorer/
        (SEOCache via build_explorer_data_for_tenants) en filtrant
        sur les UUIDs des FederatedPlace + le tenant courant.

        Reuses the same data source as the public /explorer/
        (SEOCache via build_explorer_data_for_tenants) by filtering
        on FederatedPlace UUIDs + the current tenant.
        """
        from seo.services import build_explorer_data_for_tenants, appliquer_options_federation
        from seo.models import SEOCache
        from seo.views_common import (
            get_seo_cache,
            build_json_ld_federation,
            build_json_ld_breadcrumb,
            json_for_html,
        )

        config = Configuration.get_solo()
        current_uuid = str(connection.tenant.uuid)

        # Options d'affichage du tenant (singleton FederationConfiguration).
        # / Tenant display options (FederationConfiguration singleton).
        from BaseBillet.models import FederationConfiguration
        config_federation = FederationConfiguration.get_solo()

        # Arretes SORTANTES : les FederatedPlace dans le schema du tenant courant.
        # = "les lieux avec lesquels JE federe (declaration de mon cote)".
        # / OUTGOING edges: FederatedPlace in current tenant's schema.
        # = "places I federate with (my declaration)".
        outgoing_uuids = {
            str(fp.tenant.uuid)
            for fp in FederatedPlace.objects.select_related('tenant').all()
        }

        # Arretes ENTRANTES : les FederatedPlace d'AUTRES tenants pointant vers moi.
        # Pre-calcule par le Celery task refresh_seo_cache (UNION ALL cross-schema).
        # = "les lieux qui federent AVEC moi (declaration de leur cote)".
        # / INCOMING edges: FederatedPlace from OTHER tenants pointing to me.
        # Pre-computed by refresh_seo_cache Celery task (cross-schema UNION ALL).
        # = "places that federate WITH me (their declaration)".
        # Seulement si l'option du tenant est activee (afficher_lieux_entrants).
        # / Only if the tenant option is enabled (afficher_lieux_entrants).
        incoming_uuids = set()
        if config_federation.afficher_lieux_entrants:
            incoming_data = get_seo_cache(SEOCache.FEDERATION_INCOMING) or {}
            incoming_uuids = set(
                incoming_data.get("by_tenant", {}).get(current_uuid, [])
            )

        # Federation automatique par tags : les lieux de TOUT le reseau ayant un
        # event futur public portant un des tags choisis dans la config. Lecture
        # 100% cache (AGGREGATE_EVENTS, veto private inclus). S'ajoute aux voisins.
        # / Tag-based auto federation: venues from the WHOLE network with a public
        # future event carrying one of the chosen tags. Cache-only read.
        from seo.services import get_tenant_uuids_with_event_tags
        tags_federation_slugs = [t.slug for t in config_federation.tags_federation.all()]
        thematic_uuids = get_tenant_uuids_with_event_tags(tags_federation_slugs)

        # Union : voisins directs (graphe) + abonnements thematiques (cache).
        # / Union: direct neighbors (graph) + thematic subscriptions (cache).
        other_federated_uuids = (outgoing_uuids | incoming_uuids | thematic_uuids)
        other_federated_uuids.discard(current_uuid)

        # Ensemble final pour l'explorer : voisins + tenant courant.
        # / Final set for the explorer: neighbors + current tenant.
        all_uuids = other_federated_uuids | {current_uuid}
        sorted_uuids = sorted(all_uuids)
        explorer_data = build_explorer_data_for_tenants(sorted_uuids)

        # Filtre "event a venir" + tri des lieux selon la config du tenant.
        # / "Upcoming event" filter + venue sort according to tenant config.
        explorer_data = appliquer_options_federation(
            explorer_data,
            afficher_seulement_avec_event=config_federation.afficher_seulement_lieux_avec_event,
            tri_des_lieux=config_federation.tri_des_lieux,
            afficher_lieux_sans_adresse=config_federation.afficher_lieux_sans_adresse,
        )

        # Etat vide : a-t-on AUTRE chose que le tenant courant sur la carte ?
        # / Empty state: do we have something OTHER than the current tenant on the map?
        has_other_federated_places = bool(other_federated_uuids)

        # JSON-LD federation : declare la structure du reseau pour les LLMs et
        # les moteurs de recherche. Le tenant courant = racine, les autres lieux
        # de la liste = subOrganization. memberOf pointe vers le reseau TiBillet.
        # / Federation JSON-LD: declares the network structure to LLMs and
        # search engines. Current tenant = root, other lieux = subOrganization.
        # memberOf points to the global TiBillet network.
        federation_members = []
        self_lieu_data = None
        for lieu in explorer_data.get("tenants", []):
            domain = lieu.get("domain", "")
            member_url = f"https://{domain}/" if domain else ""
            member_dict = {
                "name": lieu.get("name", ""),
                "url": member_url,
                "short_description": lieu.get("short_description", ""),
                "locality": lieu.get("locality", ""),
                "country": lieu.get("country", ""),
                "logo_url": lieu.get("logo_url") or "",
            }
            if lieu.get("tenant_id") == current_uuid:
                self_lieu_data = member_dict
            else:
                federation_members.append(member_dict)

        # Racine du JSON-LD = tenant courant. Si le SEOCache n'a pas encore
        # de donnees pour le tenant courant (refresh non encore lance), on
        # utilise les valeurs courantes de config en fallback.
        # / JSON-LD root = current tenant. If SEOCache has no data yet for
        # current tenant, fall back to current config values.
        root_url = request.build_absolute_uri("/")
        if self_lieu_data:
            root_name = self_lieu_data["name"] or config.organisation
            root_description = self_lieu_data.get("short_description") or ""
            root_address = {}
            if self_lieu_data.get("locality"):
                root_address["addressLocality"] = self_lieu_data["locality"]
            if self_lieu_data.get("country"):
                root_address["addressCountry"] = self_lieu_data["country"]
        else:
            # Fallback : config.organisation peut etre une chaine vide.
            # / Fallback: config.organisation can be an empty string.
            root_name = config.organisation or connection.tenant.name
            root_description = (config.short_description or "")
            root_address = {}

        federation_json_ld_dict = build_json_ld_federation(
            root_name=root_name,
            root_url=root_url,
            federation_members=federation_members,
            root_description=root_description,
            root_address=root_address or None,
            member_of={
                "name": "TiBillet — Réseau coopératif de lieux culturels",
                "url": "https://tibillet.coop/",
            },
        )
        federation_json_ld = json_for_html(federation_json_ld_dict)

        # BreadcrumbList : Accueil > Reseau local. Pour les rich snippets SERP.
        # / BreadcrumbList: Home > Local network. For SERP rich snippets.
        breadcrumb_json_ld_dict = build_json_ld_breadcrumb([
            {"name": str(config.organisation), "url": root_url},
            {"name": str(_("Réseau local")), "url": request.build_absolute_uri()},
        ])
        breadcrumb_json_ld = json_for_html(breadcrumb_json_ld_dict)

        # Contexte standard du skin + variables specifiques a l'explorer
        # / Standard skin context + explorer-specific variables
        from django.conf import settings
        template_context = get_context(request)
        template_context.update({
            'explorer_data': explorer_data,
            'current_tenant_uuid': current_uuid,
            'maptiler_key': settings.MAPTILER_KEY,
            'has_other_federated_places': has_other_federated_places,
            'federation_json_ld': federation_json_ld,
            'breadcrumb_json_ld': breadcrumb_json_ld,
            'page_title': _('Réseau local'),
            'texte_introduction': config_federation.texte_introduction,
        })

        # Résolution du gabarit par le resolver unifié (CHANTIER-05).
        # / Unified skin resolver (skins migration).
        from pages.services import gabarit_skin
        template_path = gabarit_skin("vues/reseau.html")
        return render(request, template_path, context=template_context)


class HomeViewset(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]

    @action(detail=False, methods=['POST'])
    def contact(self, request):
        logger.info(request.data)
        validator = ContactValidator(data=request.data, context={'request': request})
        if not validator.is_valid():
            for error in validator.errors:
                messages.add_message(request, messages.ERROR, f"{error} : {validator.errors[error][0]}")
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

        contact_mailer.delay(
            sender=validator.validated_data['email'],
            subject=validator.validated_data['subject'],
            message=validator.validated_data['message'],
        )

        messages.add_message(request, messages.SUCCESS, _("Message sent, you have been sent a copy. Thank you!"))
        return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

    def get_permissions(self):
        # if self.action in ['create']:
        #     permission_classes = [permissions.IsAuthenticated]
        # else:
        permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]


class EventMVT(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]

    def get_permissions(self):
        # EventMVT n'expose plus que des vues publiques (list/retrieve).
        # Les actions admin de creation d'evenement vivent dans EventWizardAdmin (S3).
        # / EventMVT now only exposes public views. Admin create actions live in EventWizardAdmin.
        return [permissions.AllowAny()]

    def federated_events_get(self, slug):
        for place in FederatedPlace.objects.all().select_related('tenant'):
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
        for place in FederatedPlace.objects.all().select_related('tenant'):
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

    def federated_events_filter(self, tags=None, search=None, page=1, thematique=None, date_filter=None):
        # Cache : on cache les deux cas les plus fréquents sur un gros agenda (festival) :
        #   1) la page principale (page 1, aucun filtre)
        #   2) une page filtrée par date seule (un jour précis, sans autre filtre)
        # Les filtres combinés (tags, recherche, thématique) restent NON cachés : ils sont rares.
        # La clé inclut un jeton de version par tenant, réécrit à chaque Event.save().
        # Quand le jeton change, la page principale ET toutes les pages par date sont
        # invalidées d'un coup (les anciennes clés ne sont plus lues et expirent via le TTL).
        # / Cache the two frequent cases (main page + single-date page). Combined filters stay
        # / uncached. Keys embed a per-tenant version token, rewritten in Event.save().
        page_principale = (page == 1 and not tags and not search and not thematique and not date_filter)
        date_seule = bool(date_filter) and not tags and not search and not thematique

        cache_key = None
        if page_principale or date_seule:
            # Jeton de version du cache liste pour ce tenant (défaut 'v0' si jamais écrit)
            # / List-cache version token for this tenant (default 'v0' if never written)
            version = cache.get(f'event_list_version_{connection.tenant.uuid}', 'v0')
            if date_seule:
                cache_key = f'event_list_{connection.tenant.uuid}_{version}_date_{date_filter.isoformat()}'
            else:
                cache_key = f'event_list_{connection.tenant.uuid}_{version}'
            cached = cache.get(cache_key)
            if cached:
                return cached

        dated_events = {}
        all_dates_set = set()       # Toutes les dates disponibles (avant pagination)
        all_tags_by_slug = {}       # slug -> Tag object (dédupliqué par slug entre tenants)
        all_thematiques_by_slug = {}  # slug -> Tag object (thématiques des events visibles)
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

        # Fédération automatique par tags : on ajoute les tenants de TOUT le
        # réseau TiBillet qui ont un évènement futur public portant un des tags
        # choisis dans FederationConfiguration.tags_federation. L'identification
        # est 100% cache (AGGREGATE_EVENTS, veto private inclus) ; le rendu réutilise
        # le moteur ci-dessous (objets Event, private=False appliqué d'office car
        # tenant != this_tenant). Liste vide -> rien d'ajouté (comportement actuel).
        # / Tag-based auto federation: add network tenants having a public future
        # event carrying one of the chosen tags. Cache-only identification, then
        # rendered by the same engine. Empty list -> nothing added.
        from seo.services import get_tenant_uuids_with_event_tags
        tags_federation_slugs = [
            tag.slug for tag in FederationConfiguration.get_solo().tags_federation.all()
        ]
        if tags_federation_slugs:
            uuids_deja_presents = {str(t["tenant"].uuid) for t in tenants}
            uuids_thematiques = get_tenant_uuids_with_event_tags(tags_federation_slugs)
            uuids_a_ajouter = uuids_thematiques - uuids_deja_presents
            for client_thematique in Client.objects.filter(uuid__in=uuids_a_ajouter):
                tenants.append({
                    "tenant": client_thematique,
                    "tag_filter": [],
                    # tag_exclude = INCLURE uniquement ces tags (sémantique
                    # historique inversée du moteur) : on ne récupère que les
                    # events thématiques de ce tenant.
                    # / tag_exclude = include-only these tags (engine's inverted
                    # semantics): only this tenant's thematic events are fetched.
                    "tag_exclude": tags_federation_slugs,
                })

        # Récupération de tous les évènements de la fédération
        for tenant in tenants:
            with ((tenant_context(tenant['tenant']))):
                events = Event.objects.select_related(
                    'postal_address',
                ).prefetch_related(
                    'tag', 'products', 'products__prices', 'artists', 'artists__artist',
                ).filter(
                    published=True,
                    datetime__gte=timezone.localtime() - timedelta(days=1),  # On prend les évènement a partir d'hier
                ).exclude(
                    tag__slug__in=tenant['tag_filter']
                ).exclude(
                    categorie=Event.ACTION
                )  # Les Actions sont affichés dans la page de l'evenement parent

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

                if thematique:
                    events = events.filter(thematique__slug=thematique)

                # Collecte de TOUTES les dates et tags avant pagination
                # Requêtes légères : dates() et values_list() évitent les subqueries lourdes
                # / Collect ALL dates and tags before pagination (lightweight queries)
                all_dates_set.update(events.dates('datetime', 'day'))
                tag_pks = set(events.order_by().values_list('tag__pk', flat=True))
                tag_pks.discard(None)
                for tag in Tag.objects.filter(pk__in=tag_pks):
                    if tag.slug not in all_tags_by_slug:
                        all_tags_by_slug[tag.slug] = tag
                thematique_pks = set(events.order_by().values_list('thematique__pk', flat=True))
                thematique_pks.discard(None)
                for th in Tag.objects.filter(pk__in=thematique_pks):
                    if th.slug not in all_thematiques_by_slug:
                        all_thematiques_by_slug[th.slug] = th

                # Filtre par date : on restreint les évènements affichés au jour choisi.
                # Important : on filtre APRÈS la collecte des dates/tags ci-dessus,
                # pour que les menus déroulants restent complets (changer de jour reste possible).
                # / Date filter: restrict displayed events to the chosen day.
                # / Applied AFTER collecting dates/tags so dropdowns stay complete.
                events_a_afficher = events
                if date_filter:
                    events_a_afficher = events_a_afficher.filter(datetime__date=date_filter)

                events_tries = events_a_afficher.order_by('datetime').distinct()

                if date_filter:
                    # Un jour précis est sélectionné : on affiche TOUS les évènements de ce jour,
                    # sans pagination (un festival a rarement plus de 100 évènements sur une journée).
                    # / A specific day is selected: show ALL its events, no pagination.
                    paginated_events = events_tries
                    paginated_info['page'] = page
                    paginated_info['has_next'] = False
                    paginated_info['has_previous'] = False
                else:
                    # Pagination : 200 évènements par page par tenant
                    # / Pagination: 200 events per page per tenant
                    paginator = Paginator(events_tries, 200)
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

        # Toutes les dates triées (pour le dropdown filtre)
        # / All dates sorted (for filter dropdown)
        sorted_all_dates = sorted(all_dates_set)

        # Tous les tags triés par nom (pour le dropdown filtre)
        # / All tags sorted by name (for filter dropdown)
        sorted_all_tags = sorted(all_tags_by_slug.values(), key=lambda t: t.name.lower())

        # Toutes les thématiques triées par nom (pour le dropdown filtre)
        # / All thematiques sorted by name (for filter dropdown)
        sorted_all_thematiques = sorted(all_thematiques_by_slug.values(), key=lambda t: t.name.lower())

        result = (sorted_dict_by_date, paginated_info, sorted_all_dates, sorted_all_tags, sorted_all_thematiques)

        # On met en cache la page principale OU la page filtrée par date seule
        # (cache_key n'est défini que dans ces deux cas, voir le haut de la méthode).
        # Durée : 1 heure. Invalidé dans Event.save() via le jeton de version.
        # / Cache the main page OR the single-date page (cache_key set only in those cases).
        # / Duration: 1 hour. Invalidated in Event.save() via the version token.
        if cache_key:
            cache.set(cache_key, result, 3600)

        return result

    def _parse_date_filter(self, raw_date):
        """
        Convertit un paramètre date ISO ("2025-03-15") en objet date.
        Retourne None si le paramètre est absent ou invalide.
        / Parse an ISO date param into a date object. None if missing/invalid.

        LOCALISATION : BaseBillet/views.py — EventMVT
        Utilisé par list() et partial_list() pour le filtre par jour.
        """
        if not raw_date:
            return None
        try:
            return date_type.fromisoformat(raw_date)
        except (ValueError, TypeError):
            # Paramètre invalide : on ignore et on affiche tout
            # / Invalid param: ignore and show everything
            return None

    def _querystring_filtres(self, search=None, tags=None, thematique=None):
        """
        Construit la querystring des filtres actifs (recherche, tags, thématique)
        pour les conserver dans le bouton "charger plus".
        / Build active-filters querystring to keep them in the "load more" button.

        LOCALISATION : BaseBillet/views.py — EventMVT

        Le filtre par date est volontairement exclu : quand une date est choisie,
        on affiche tous les évènements du jour sans pagination, donc pas de bouton.
        / Date filter is excluded on purpose: a chosen day shows everything, no button.
        """
        from urllib.parse import urlencode

        filtres_actifs = {}
        if search:
            filtres_actifs['search'] = search
        if thematique:
            filtres_actifs['thematique'] = thematique
        if tags:
            filtres_actifs['tag'] = tags
        # doseq=True : gère la liste de tags (tag=a&tag=b)
        # / doseq=True: handles the list of tags (tag=a&tag=b)
        return urlencode(filtres_actifs, doseq=True)

    @action(detail=False, methods=['POST', 'GET'])
    def partial_list(self, request):
        logger.info(f"request.data : {request.data}")

        search = request.data.get('search')  # on s'assure que c'est bien une string. Todo : Validator !
        if not search:  # Pour le get réalisé par le clic sur l'adresse
            search = request.GET.get('search')

        if search:
            search = str(search)

        tags = request.GET.getlist('tag')
        page = int(request.GET.get('page') or 1)

        logger.info(f"request.GET : {request.GET}")

        thematique_slug = request.GET.get('thematique')
        # Filtre par date (format ISO "2025-03-15") — None si absent/invalide
        # / Date filter (ISO format) — None if missing/invalid
        date_filter = self._parse_date_filter(request.GET.get('date'))

        ctx = {}  # le dict de context pour template
        ctx['dated_events'], ctx['paginated_info'], _dates, _tags, _thematiques = self.federated_events_filter(
            tags=tags, search=search, page=page, thematique=thematique_slug, date_filter=date_filter
        )

        # On conserve les filtres actifs (recherche, tags, thématique) dans le bouton "charger plus"
        # / Keep active filters in the "load more" button
        ctx['querystring_filtres'] = self._querystring_filtres(
            search=search, tags=tags, thematique=thematique_slug
        )

        # Résolution du gabarit par le resolver unifié (CHANTIER-03) :
        # pages/<skin>/vues/…, sinon fallback pages/classic/.
        # Si page > 1, on utilise le gabarit « suite » (sans header RSS).
        # / Unified skin resolver: pages/<skin>/vues/…, fallback pages/classic/.
        from pages.services import gabarit_skin
        if page > 1:
            template_path = gabarit_skin("vues/agenda_liste_suite.html")
        else:
            template_path = gabarit_skin("vues/agenda_liste.html")

        return render(request, template_path, context=ctx)

    # La page get /
    def list(self, request: HttpRequest):
        # TODO pour pouvoir sauvegader l'url de recherche :
        # - tout passer en GET ( et non pas le partial_list POST plus haut )
        # - passer sur du partial render avec HTMX
        context = get_context(request)
        # Reglages d'agenda participatif (sur FederationConfiguration) : pilotent
        # l'affichage du bouton "Proposer un evenement" sur la page agenda.
        # / Participatory-agenda settings (on FederationConfiguration): drive the
        # "Propose an event" button on the agenda page.
        context['federation_config'] = FederationConfiguration.get_solo()
        tags = request.GET.getlist('tag')
        search = request.GET.get('search')
        if search:
            search = str(search)
        page = request.GET.get('page', 1)
        thematique_slug = request.GET.get('thematique')
        # Paramètre de filtre par date (format ISO : "2025-03-15"), validé en objet date.
        # Le filtrage se fait en base (SQL), pas après la pagination.
        # / Date filter param (ISO), validated to a date object. Filtered in SQL, not after pagination.
        date_filter = self._parse_date_filter(request.GET.get('date'))

        # Données pour les filtres (tags, thématiques, recherche, date)
        # / Data for filter UI (tags, thematiques, search, date)
        context['active_tag'] = Tag.objects.filter(slug=tags[0]).first() if tags else None
        context['tags'] = tags
        context['search'] = search
        context['active_thematique'] = thematique_slug
        # active_date : string ISO (URL/affichage) ; active_date_obj : objet date (libellé du dropdown)
        # / active_date: ISO string (URL/display) ; active_date_obj: date object (dropdown label)
        context['active_date'] = date_filter.isoformat() if date_filter else None
        context['active_date_obj'] = date_filter

        # federated_events_filter applique le filtre date en SQL et désactive la pagination ce jour-là.
        # Il retourne aussi TOUTES les dates et tags (menus déroulants complets).
        # / federated_events_filter applies the date filter in SQL and disables pagination for that day.
        # / It also returns ALL dates and tags (complete dropdowns).
        context['dated_events'], context['paginated_info'], all_dates_list, all_tags_list, all_thematiques_list = self.federated_events_filter(
            tags=tags, search=search, page=page, thematique=thematique_slug, date_filter=date_filter
        )

        # Toutes les dates disponibles pour le dropdown filtre (pas limité à la pagination)
        # / All available dates for filter dropdown (not limited to pagination)
        context['all_dates'] = all_dates_list

        # Tous les tags des events visibles (publiés, futurs) pour le dropdown filtre
        # / All tags from visible events (published, future) for filter dropdown
        context['all_tags'] = all_tags_list

        # Toutes les thématiques des events visibles
        # / All thematiques from visible events
        context['all_thematiques'] = all_thematiques_list

        # On conserve les filtres actifs (recherche, tags, thématique) dans le bouton "charger plus"
        # / Keep active filters in the "load more" button
        context['querystring_filtres'] = self._querystring_filtres(
            search=search, tags=tags, thematique=thematique_slug
        )

        # Résolution du gabarit par le resolver unifié (CHANTIER-03).
        # / Unified skin resolver (skins migration).
        from pages.services import gabarit_skin
        template_path = gabarit_skin("vues/agenda.html")

        # On renvoie la page en entier
        return render(request, template_path, context=context)

    @action(detail=False, methods=['GET'])
    def embed(self, request):
        template_context = get_context(request)
        template_context['dated_events'], template_context['paginated_info'], _dates, _tags, _thematiques = self.federated_events_filter()
        template_context['embed'] = True
        # CHANTIER-03 : l'embed suivait TOUJOURS le look reunion (chemin en dur).
        # Il suit désormais le skin du tenant, comme la page agenda normale
        # (les guards {% if not embed %} des squelettes masquent navbar/footer).
        # / The embed iframe now follows the tenant skin instead of a hardcoded
        # reunion path. The shells' embed guards still hide navbar/footer.
        from pages.services import gabarit_skin
        response = render(
            request, gabarit_skin("vues/agenda.html"),
            context=template_context,
        )
        # Pour rendre la page dans un iframe, on vide le header X-Frame-Options pour dire au navigateur que c'est ok.
        response['X-Frame-Options'] = ''
        return response

    def retrieve(self, request, pk=None, **kwargs):
        slug = pk
        hex8 = None
        match = re.search(r'([0-9a-fA-F]{8})(?:/)?$', pk)
        if match:
            hex8 = match.group(1)

        logger.info(f"slug : {slug}")
        logger.info(f"hex8 : {hex8}")

        # Si False, alors le bouton reserver renvoi vers la page event du tenant.
        event_in_this_tenant = False
        # Defaults to prevent UnboundLocalError when event is retrieved from federation
        products = []
        prices = []
        product_max_per_user_reached = []
        price_max_per_user_reached = []
        event_max_per_user_reached = False

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

            # Récupération des produits et des prix pour :
            # - afficher le min / max
            # - vérifier le max par user

            # Précharger les prix en même temps que les produits
            event_products = event.products.prefetch_related("prices")
            products = list(event_products)

            # Récupération des prix
            prices = [price for product in products for price in product.prices.all()]

            # Si l'user est connecté, on vérifie qu'il n'a pas déja reservé
            product_max_per_user_reached = []
            price_max_per_user_reached = []
            event_max_per_user_reached = False

            if request.user.is_authenticated:
                for product in products:
                    if product.max_per_user_reached(user=request.user, event=event):
                        logger.info(
                            f"product.max_per_user_reached : {product.name} {product.max_per_user_reached(user=request.user, event=event)}")
                        product_max_per_user_reached.append(product)
                for price in prices:
                    logger.info(
                        f"price.max_per_user_reached : {price.name} {price.max_per_user_reached(user=request.user, event=event)}")
                    if price.max_per_user_reached(user=request.user, event=event):
                        price_max_per_user_reached.append(price)

                event_max_per_user_reached = event.max_per_user_reached_on_this_event(request.user)

            tarifs = [price.prix for price in prices]
            # Calcul des prix min et max
            event.price_min = min(tarifs) if tarifs else None
            event.price_max = max(tarifs) if tarifs else None

            # Vérification de l'existence d'un prix libre (sans requêtes supplémentaires)
            event.free_price = any(
                price.free_price for product in products for price in product.prices.all()
            )

            event_in_this_tenant = True

        except Event.DoesNotExist:
            # L'évent n'est pas
            logger.info("Event.DoesNotExist on tenant, check to federation")
            if hex8:
                event = self.federated_events_get_hex8(hex8)
            else:
                event = self.federated_events_get(slug)

        except Event.MultipleObjectsReturned:
            logger.info("Url de lien mal formé, plusieurs events ?")
            return redirect("/event/")

        if not event:  # Event pas trouvé, on redirige vers la page d'évènement complète
            logger.info("Event.DoesNotExist on federation, redirect")
            return redirect("/event/")

        template_context = get_context(request)
        # Attribution directe à l'event (en mémoire, pas en base)
        event.prices = prices
        template_context['product_max_per_user_reached'] = product_max_per_user_reached
        template_context['price_max_per_user_reached'] = price_max_per_user_reached
        template_context['event'] = event
        template_context['event_in_this_tenant'] = event_in_this_tenant
        template_context['event_max_per_user_reached'] = event_max_per_user_reached

        # On prépare les prix publiés pour le template (utilisé par le sélecteur de billet)
        # On s'assure que price.name n'est jamais None pour éviter les "undefined" en JS
        # Tri par poids du produit parent, puis par ordre du tarif, puis par prix
        # Sort by parent product weight, then by rate display order, then by price
        event.published_prices = Price.objects.filter(
            product__event=event,
            product__categorie_article__in=[Product.BILLET, Product.FREERES],
            publish=True,
        ).order_by('product__poids', 'order', 'prix')
        for p in event.published_prices:
            if p.name is None:
                p.name = ""

        # L'evènement possède des sous évènement.
        # Pour l'instant : uniquement des ACTIONS
        if event.children.exists():
            template_context['action_total_jauge'] = event.children.all().aggregate(total_value=Sum('jauge_max'))[
                                                         'total_value'] or 0
            template_context['inscrits'] = Ticket.objects.filter(reservation__event__parent=event).count()

        # Résolution du gabarit par le resolver unifié (CHANTIER-03).
        # / Unified skin resolver (skins migration).
        from pages.services import gabarit_skin
        template_path = gabarit_skin("vues/evenement.html")

        return render(request, template_path, context=template_context)

    @action(detail=True, methods=['POST'], permission_classes=[permissions.IsAuthenticated])
    def action_reservation(self, request, pk=None):
        event = get_object_or_404(Event, pk=pk)

        user = request.user
        action = get_object_or_404(Event, pk=request.data.get('action'), categorie=Event.ACTION)

        if Ticket.objects.filter(reservation__user_commande=user, reservation__event__in=event.children.all()).exists():
            messages.add_message(request, messages.ERROR,
                                 _("You have already checked for an action on this event."))
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

        if not user:
            messages.add_message(request, messages.ERROR, _("Please log in first."))
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

        validator = ReservationValidator(data={
            "email": user.email,
            "event": action.pk,
        }, context={'request': request})

        if not validator.is_valid():
            logger.error(f"ReservationViewset CREATE ERROR : {validator.errors}")
            for error in validator.errors:
                messages.add_message(request, messages.ERROR, f"{validator.errors[error][0]}")
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

        messages.add_message(request, messages.SUCCESS, _("Thank you! You are going to receive a validation email.."))
        return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

    @action(detail=True, methods=['POST'])
    def reservation(self, request, pk):
        # Vérification que l'évent existe bien sur ce tenant.
        # event = get_object_or_404(Event, slug=pk)
        logger.debug(f"Event Reservation : {request.data}")
        validator = ReservationValidator(data=request.data, context={'request': request})

        if not validator.is_valid():
            logger.error(f"ReservationViewset CREATE ERROR : {validator.errors}")
            for error in validator.errors:
                messages.add_message(request, messages.ERROR, f"{validator.errors[error][0]}")
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

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

                return render(request, "fonctionnel/event/formbricks.html", context=context)

        # SI on a un besoin de paiement, on redirige vers :
        if validator.checkout_link:
            logger.debug("validator reservation OK, get checkout link -> redirect")
            return HttpResponseClientRedirect(validator.checkout_link)

        # On passe l'user resolu par le validator (via l'email saisi),
        # pas request.user qui peut etre AnonymousUser si le visiteur n'est pas connecte.
        # Le template choisit son message selon user.is_active : il doit refleter
        # l'etat reel utilise par TicketCreator.method_F pour decider d'envoyer
        # les billets immediatement (user actif) ou un mail de validation (user inactif).
        return render(request, "fonctionnel/event/reservation_ok.html", context={
            "user": validator.reservation.user_commande,
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


class Badge(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]

    def list(self, request: HttpRequest):
        template_context = get_context(request)
        template_context["badges"] = Product.objects.filter(categorie_article=Product.BADGE, publish=True)
        template_context["account_tab"] = "punchclock"
        return render(request, "fonctionnel/compte/punchclock.html", context=template_context)

    @action(detail=True, methods=['GET'])
    def badge_in(self, request: HttpRequest, pk):
        product = get_object_or_404(Product, uuid=pk)
        user = request.user
        fedowAPI = FedowAPI()
        transaction = fedowAPI.badge.badge_in(user, product)

        messages.add_message(request, messages.SUCCESS, _(f"Check in registered!"))

        return render(request, "fonctionnel/compte/partials/badge_switch.html", context={})

    @action(detail=False, methods=['GET'])
    def check_out(self, request: HttpRequest):
        template_context = get_context(request)
        fedowAPI = FedowAPI()
        messages.add_message(request, messages.SUCCESS, _(f"Check out registered!"))
        return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

    def get_permissions(self):
        if self.action in ['retrieve']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]


class MembershipMVT(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, ]

    def create(self, request):
        logger.info(f"new membership : {request.data}")
        membership_validator = MembershipValidator(data=request.data, context={'request': request})
        if not membership_validator.is_valid():
            # Validation d'entree echouee (souvent un bot qui POST le formulaire vide ou partiel).
            # Ce n'est pas une erreur serveur : on logge en info, pas en warning, pour ne pas
            # generer de bruit dans Sentry sur une soumission invalide attendue.
            # / Failed input validation (often a bot posting an empty/partial form). Not a server error.
            logger.info(f"Membership create — validation refusee : {membership_validator.errors}")
            error_messages = [str(item) for sublist in membership_validator.errors.values() for item in sublist]
            messages.add_message(request, messages.ERROR, error_messages)
            return HttpResponseClientRedirect(request.headers.get('Referer', '/'))

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
            return render(request, "fonctionnel/adhesion/formbricks.html", context=context)

        if membership_validator.price.manual_validation:
            # Dans le cas d'une validation manuelle, on affiche un message dans l'offcanvas via un template partiel
            membership: Membership = membership_validator.membership
            context = {'membership': membership}
            return render(request, "commun/adhesion/pending_manual_validation.html", context=context)

        # Le lien de paiement a été généré, on envoi sur Stripe
        elif membership_validator.checkout_stripe_url:
            return HttpResponseClientRedirect(membership_validator.checkout_stripe_url)

        # Adhésion gratuite (montant 0€) : validée directement sans passer par Stripe
        # Free membership (0€ amount): validated directly, no Stripe redirect
        elif membership_validator.membership.status == Membership.ONCE:
            membership: Membership = membership_validator.membership
            context = {'membership': membership}
            return render(request, "commun/adhesion/free_confirmed.html", context=context)

        else:
            msg = "Une erreur lors de la gestion de vos adhésion est survenue, merci de contacter un administrateur."
            logger.error(f"MembershipViewset ERROR {msg} : {membership_validator.membership}")
            raise ValueError(msg)

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

        # Résolution du gabarit par le resolver unifié (CHANTIER-04).
        # / Unified skin resolver (skins migration).
        from pages.services import gabarit_skin
        template_path = gabarit_skin("vues/adhesions.html")

        return render(
            request, template_path,
            context=template_context,
        )

    @action(detail=False, methods=['GET'])
    def embed(self, request):
        template_context = get_context(request)
        template_context['products'] = Product.objects.filter(categorie_article=Product.ADHESION,
                                                              publish=True).prefetch_related('tag')
        template_context['embed'] = True
        # CHANTIER-04 : l'embed suivait TOUJOURS le look reunion (chemin en dur).
        # Il suit désormais le skin du tenant, comme la page adhésions normale.
        # / The embed iframe now follows the tenant skin instead of a hardcoded path.
        from pages.services import gabarit_skin
        response = render(
            request, gabarit_skin("vues/adhesions.html"),
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
            context = get_context(request)
            context['product'] = product

            # On prépare les prix publiés pour le template
            published_prices = product.prices.filter(publish=True).order_by('order', 'prix')
            context['published_prices'] = published_prices
            context['published_prices_count'] = published_prices.count()

            # On check que l'user n'a pas déja prix un abonnement limité
            price_max_per_user_reached = []
            if request.user.is_authenticated:
                if product.max_per_user_reached(user=request.user):
                    return render(request, "commun/adhesion/already_has_membership.html", context=context)

                # Vérification des limites par tarif (Price)
                # / Check per-rate (Price) limits
                for price in published_prices:
                    if price.max_per_user_reached(user=request.user):
                        price_max_per_user_reached.append(price)

            context['price_max_per_user_reached'] = price_max_per_user_reached

            # Pré-remplissage du formulaire dynamique si l'user a déjà une adhésion avec custom_form
            # Pre-fill dynamic form if user already has a membership with custom_form data
            prefill = {}
            if request.user.is_authenticated:
                # On cherche la dernière adhésion de cet user pour ce produit qui a un custom_form rempli
                # Find the most recent membership for this product that has custom_form data
                last_membership = (
                    Membership.objects
                    .filter(
                        user=request.user,
                        price__product=product,
                        custom_form__isnull=False,
                    )
                    .exclude(custom_form={})
                    .order_by('-date_added')
                    .first()
                )
                if last_membership:
                    # On construit un dict name → valeur pour le template
                    # Le JSON stocke avec le label comme clé, mais le template utilise field.name
                    # Build a name → value mapping for the template
                    # JSON stores with label as key, but template inputs use field.name
                    stored_data = last_membership.custom_form
                    for field in product.form_fields.all():
                        label_key = (field.label or '').strip() or field.name
                        if label_key in stored_data:
                            prefill[field.name] = stored_data[label_key]

            context['prefill'] = prefill

            # On teste la presence reelle d'une cle (truthiness) et pas "is not None" :
            # un CharField vide via le form admin vaut '' (pas None), ce qui passerait
            # "is not None" a tort et afficherait le switch newsletter sans config.
            # / Truthiness check: an empty CharField is '' (not None) when blanked via admin.
            context["newsletter_active"] = bool(GhostConfig.get_solo().ghost_key) or bool(BrevoConfig.get_solo().api_key)

            return render(request, "commun/adhesion/form.html", context=context)

        except Product.DoesNotExist:
            try:
                # Il est possible que ça soit sur un autre tenant ?
                url = self.get_federated_membership_url(uuid=pk)
                if url:
                    return HttpResponseClientRedirect(url)
                else:
                    # Si le produit n'existe pas dans les tenants fédérés, on affiche la page 404 personnalisée
                    context = get_context(request)
                    return render(request, "commun/adhesion/404.html", context=context, status=404)
            except Exception as e:
                # En cas d'erreur lors de la recherche dans les tenants fédérés, on affiche la page 404 personnalisée
                context = get_context(request)
                return render(request, "commun/adhesion/404.html", context=context, status=404)
        except Exception as e:
            # Pour toute autre erreur, on affiche la page 404 personnalisée
            context = get_context(request)
            return render(request, "commun/adhesion/404.html", context=context, status=404)

    @action(detail=True, methods=['GET'])
    def get_checkout_for_membership(self, request, pk):
        """
        Redirige l'utilisateur vers le checkout Stripe pour payer son adhesion.
        Lien recu par email apres validation manuelle par un admin.
        / Redirects user to Stripe checkout for membership payment.

        LOCALISATION : BaseBillet/views.py

        Protection contre les doubles paiements :
        - Si une session Stripe est encore ouverte, on reutilise l'URL existante.
        - Si l'utilisateur a deja valide son prelevement (SEPA en cours),
          on affiche une page d'information au lieu de creer un nouveau checkout.
        - Sinon, on cree un nouveau checkout normalement.

        FLUX :
        1. Recoit GET depuis le lien email envoye par send_membership_payment_link_user
        2. Cherche un Paiement_stripe existant lie a cette adhesion
        3. Si trouve : verifie le statut de la session Stripe
        4. Redirige vers Stripe ou affiche une page d'info
        """
        # On récupère l'adhésion SANS filtrer sur le statut. Cela permet
        # d'afficher un message clair selon l'état de l'adhésion, au lieu du
        # 404 JSON brut renvoyé auparavant par get_object_or_404.
        # / Fetch the membership WITHOUT a status filter, so we can show a clear
        # message depending on its state, instead of the previous raw JSON 404.
        try:
            membership = Membership.objects.get(uuid=uuid.UUID(pk))
        except (Membership.DoesNotExist, ValueError):
            context = get_context(request)
            return render(
                request,
                "fonctionnel/adhesion/payment_link_invalid.html",
                context=context,
                status=404,
            )

        context = get_context(request)
        context['membership'] = membership

        # Adhésion déjà payée (CB) ou active (abonnement) : plus rien à payer.
        # / Membership already paid (card) or active (subscription): nothing to pay.
        if membership.status in [Membership.ONCE, Membership.AUTO]:
            return render(
                request,
                "fonctionnel/adhesion/payment_already_done.html",
                context=context,
            )

        # Paiement déjà soumis, débit en cours (SEPA jusqu'à 14 jours).
        # On ne recrée surtout PAS de checkout : ce serait un 2e prélèvement.
        # / Payment already submitted, debit pending (SEPA up to 14 days).
        # We must NOT recreate a checkout: it would be a 2nd debit.
        if membership.status == Membership.PAYMENT_PENDING:
            return render(
                request,
                "fonctionnel/adhesion/payment_already_pending.html",
                context=context,
            )

        # Adhésion annulée, ou lien reçu avant validation admin : lien inactif.
        # / Cancelled membership, or link used before admin validation: dead link.
        if membership.status != Membership.ADMIN_VALID:
            return render(
                request,
                "fonctionnel/adhesion/payment_link_invalid.html",
                context=context,
                status=409,
            )

        # À partir d'ici : statut ADMIN_VALID, on peut créer/réutiliser un checkout.
        # / From here: ADMIN_VALID status, we can create/reuse a checkout.

        # Chercher un paiement Stripe deja en cours pour cette adhesion
        # On filtre sur PENDING et OPEN : ce sont les statuts avant encaissement
        # / Look for an existing pending Stripe payment for this membership
        paiement_stripe_existant = membership.stripe_paiement.filter(
            status__in=[Paiement_stripe.PENDING, Paiement_stripe.OPEN],
            checkout_session_id_stripe__isnull=False,
        ).order_by('-order_date').first()

        if paiement_stripe_existant:
            try:
                # Interroger l'API Stripe pour connaitre l'etat reel de la session
                # / Query Stripe API to get the real session status
                stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
                config = Configuration.get_solo()
                session_stripe = stripe.checkout.Session.retrieve(
                    paiement_stripe_existant.checkout_session_id_stripe,
                    stripe_account=config.get_stripe_connect_account(),
                )

                # Cas 1 : Session encore ouverte — on reutilise l'URL
                # L'utilisateur n'a pas encore rempli le formulaire de paiement
                # / Case 1: Session still open — reuse the URL
                if session_stripe.status == 'open' and session_stripe.url:
                    logger.info(
                        f"get_checkout_for_membership : reutilisation session existante {session_stripe.id}")
                    return redirect(session_stripe.url)

                # Cas 2 : Session "complete" — l'utilisateur a deja valide son paiement
                # Pour le SEPA, le prelevement peut prendre jusqu'a 14 jours.
                # On ne doit PAS creer un nouveau checkout.
                # / Case 2: Session "complete" — user already submitted payment (SEPA pending)
                if session_stripe.status == 'complete':
                    logger.info(
                        f"get_checkout_for_membership : session {session_stripe.id} deja completee, "
                        f"paiement en cours de traitement")
                    context = get_context(request)
                    context['membership'] = membership
                    return render(
                        request,
                        "fonctionnel/adhesion/payment_already_pending.html",
                        context=context,
                    )

                # Cas 3 : Session expiree cote Stripe — on marque et on repart
                # / Case 3: Session expired on Stripe side — mark and create new one
                logger.info(
                    f"get_checkout_for_membership : session {session_stripe.id} "
                    f"status={session_stripe.status}, on en cree une nouvelle")
                paiement_stripe_existant.status = Paiement_stripe.EXPIRE
                paiement_stripe_existant.save(update_fields=['status'])

            except Exception as e:
                # Erreur API Stripe : en cas de doute, on NE recrée PAS de
                # checkout (cela pourrait générer un 2e prélèvement). On affiche
                # la page "paiement en cours". L'adhérent réessaiera plus tard si
                # le paiement n'avait pas abouti ; aucun risque de doublon.
                # / Stripe API error: when in doubt, do NOT recreate a checkout
                # (risk of a 2nd debit). Show the "payment pending" page instead.
                logger.warning(
                    f"get_checkout_for_membership : erreur recuperation session Stripe, "
                    f"affichage page paiement en cours (pas de nouveau checkout) : {e}")
                return render(
                    request,
                    "fonctionnel/adhesion/payment_already_pending.html",
                    context=context,
                )

        # Aucun paiement existant ou session expiree : on cree un nouveau checkout
        # / No existing payment or expired session: create a new checkout
        checkout_url = MembershipValidator.get_checkout_stripe(membership)
        logger.info(f"get_checkout_for_membership : nouveau checkout {checkout_url}")
        return redirect(checkout_url)
        # return HttpResponseClientRedirect(checkout_url)

    @action(detail=True, methods=['POST'])
    def admin_accept(self, request, pk):
        """
        Valide une adhésion en attente et envoie le lien de paiement par email.
        / Validates a pending membership and sends the payment link by email.

        LOCALISATION : BaseBillet/views.py — MembershipMVT

        FLUX :
        - Statut AW (1re validation) : passe en ADMIN_VALID + envoie le mail de paiement
        - Statut AV (renvoi)         : ne change pas le statut, renvoie juste le mail
        - Autres statuts             : avertissement + redirection

        Utilise uuid comme pk (non standard — historique). Ne pas modifier.
        / Uses uuid as pk (non-standard — legacy). Do not modify.

        DÉPENDANCES :
        - Celery : send_membership_payment_link_user (BaseBillet/tasks.py)
        - Template : admin/membership/partials/admin_accept_success.html
        """
        user = request.user
        tenant = request.tenant

        try:
            est_admin = user.is_authenticated and hasattr(user, 'is_tenant_admin') and user.is_tenant_admin(tenant)
        except Exception:
            est_admin = False
        if not est_admin:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        membership = get_object_or_404(Membership, uuid=uuid.UUID(pk))

        # Première validation : statut AW → AV
        # / First validation: status AW → AV
        if membership.status == Membership.ADMIN_WAITING:
            membership.status = Membership.ADMIN_VALID
            membership.save(update_fields=["status"])

        # Renvoi du mail : statut déjà AV, pas de changement de statut
        # / Resend email: status already AV, no status change
        elif membership.status == Membership.ADMIN_VALID:
            pass

        # Statut incompatible avec cette action
        # / Status incompatible with this action
        else:
            messages.add_message(request, messages.WARNING, _("Cette adhésion n'est pas en attente de validation."))
            referer = request.headers.get('Referer') or f"/admin/BaseBillet/membership/{membership.pk}/change/"
            return HttpResponseClientRedirect(referer)

        # Envoie le lien de paiement par email (tâche de fond Celery)
        # / Send payment link by email (Celery background task)
        try:
            send_membership_payment_link_user.delay(str(membership.uuid))
        except Exception as e:
            logger.error(f"Erreur d'enqueue send_membership_payment_link_user: {e}")

        try:
            messages.add_message(request, messages.SUCCESS,
                                 _("L'adhésion a été acceptée. Un email de paiement a été envoyé."))
        except Exception:
            pass

        # Réponse HTMX : retourne le partial de succès pour la zone #response-accept
        # / HTMX response: return success partial for the #response-accept zone
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

    def _build_form_fields_for_membership(self, membership, values_override=None):
        """
        Construit la structure de données des champs du formulaire pour une adhésion.
        Build form fields data structure for a membership.

        Utilise label_key (le label du champ) comme clé, car c'est ainsi que
        les valeurs sont stockées dans membership.custom_form (cf. validators.py:63).
        Uses label_key (the field label) as key, because that's how values
        are stored in membership.custom_form (see validators.py:63).

        Si values_override est fourni (ex: request.POST), les valeurs viennent de là.
        If values_override is provided (e.g. request.POST), values come from there.
        """
        form_fields = {}

        # Vérification que l'adhésion a un prix ET un produit
        # Check that membership has a price AND a product
        membership_has_price = membership.price is not None
        if membership_has_price:
            membership_has_product = membership.price.product is not None
        else:
            membership_has_product = False

        if not (membership_has_price and membership_has_product):
            return form_fields

        product = membership.price.product
        product_form_fields = ProductFormField.objects.filter(product=product).order_by('order')

        for field in product_form_fields:
            # Calcul de label_key : même logique que validators.py:63
            # Compute label_key: same logic as validators.py:63
            label_key = (field.label or '').strip() or field.name

            # Récupération de la valeur
            # Get the value
            if values_override is not None:
                # Valeurs depuis POST (on utilise label_key comme name des inputs)
                # Values from POST (we use label_key as input name)
                field_is_boolean = field.field_type == ProductFormField.FieldType.BOOLEAN
                if field_is_boolean:
                    current_value = values_override.get(label_key) == 'true'
                elif field.field_type == ProductFormField.FieldType.MULTI_SELECT:
                    current_value = values_override.getlist(label_key)
                else:
                    current_value = values_override.get(label_key, "")
            else:
                # Valeurs depuis le JSON custom_form existant
                # Values from existing custom_form JSON
                current_value = ""
                if membership.custom_form:
                    current_value = membership.custom_form.get(label_key, "")

            # Préparation des options : field.options est un JSONField (déjà une liste Python)
            # Prepare options: field.options is a JSONField (already a Python list)
            options_list = []
            field_is_single_select = field.field_type == ProductFormField.FieldType.SINGLE_SELECT
            field_is_radio_select = field.field_type == ProductFormField.FieldType.RADIO_SELECT
            field_is_multi_select = field.field_type == ProductFormField.FieldType.MULTI_SELECT
            field_has_options = field_is_single_select or field_is_radio_select or field_is_multi_select

            if field_has_options and field.options:
                # field.options est déjà une liste (JSONField), on filtre les vides
                # field.options is already a list (JSONField), filter out empties
                if isinstance(field.options, list):
                    for option in field.options:
                        option_str = str(option).strip()
                        if option_str:
                            options_list.append(option_str)
                else:
                    # Fallback si c'est une chaîne (ne devrait pas arriver)
                    # Fallback if it's a string (should not happen)
                    for option in str(field.options).split(','):
                        option_stripped = option.strip()
                        if option_stripped:
                            options_list.append(option_stripped)

            form_fields[label_key] = {
                'label': field.label,
                'field_type': field.field_type,
                'value': current_value,
                'required': field.required,
                'options': options_list,
            }

        # Ajout des champs "orphelins" : présents dans le JSON mais pas dans ProductFormField
        # Add "orphan" fields: present in JSON but not defined in ProductFormField
        # (par exemple les champs ajoutés manuellement via "Ajouter un champ")
        # (e.g. fields added manually via "Add a field")
        if membership.custom_form:
            for json_key, json_value in membership.custom_form.items():
                # Si cette clé est déjà couverte par un ProductFormField, on passe
                # If this key is already covered by a ProductFormField, skip
                if json_key in form_fields:
                    continue

                # Valeur depuis POST si disponible, sinon depuis le JSON
                # Value from POST if available, otherwise from JSON
                if values_override is not None:
                    current_value = values_override.get(json_key, "")
                else:
                    current_value = json_value if json_value is not None else ""

                # Champ libre = texte court, pas obligatoire, pas d'options
                # Free-form field = short text, not required, no options
                form_fields[json_key] = {
                    'label': json_key,
                    'field_type': 'ST',
                    'value': current_value,
                    'required': False,
                    'options': [],
                }

        return form_fields

    def _check_tenant_admin(self, request):
        """
        Vérifie que l'utilisateur est admin du tenant courant.
        Check that the user is admin of the current tenant.
        Retourne True/False.
        """
        user = request.user
        tenant = request.tenant
        try:
            user_is_authenticated = user.is_authenticated
            user_has_method = hasattr(user, 'is_tenant_admin')
            user_is_tenant_admin = user.is_tenant_admin(tenant) if user_has_method else False
            return user_is_authenticated and user_has_method and user_is_tenant_admin
        except Exception:
            return False

    @action(detail=True, methods=['GET'])
    def admin_edit_json_form(self, request, pk):
        """
        Point d'entrée HTMX pour afficher le formulaire d'édition des champs JSON custom_form.
        HTMX endpoint to display the edit form for custom_form JSON fields.
        """
        if not self._check_tenant_admin(request):
            return HttpResponse(_("Accès refusé"), status=403)

        membership_uuid = uuid.UUID(pk)
        membership = get_object_or_404(Membership, uuid=membership_uuid)

        form_fields = self._build_form_fields_for_membership(membership)

        context = {
            'membership': membership,
            'form_fields': form_fields,
            'errors': None,
        }
        return render(request, "admin/membership/partials/custom_form_edit.html", context)

    @action(detail=True, methods=['GET'])
    def admin_cancel_edit(self, request, pk):
        """
        Point d'entrée HTMX pour annuler l'édition et retourner à la vue en lecture seule.
        HTMX endpoint to cancel editing and return to read-only view.
        """
        if not self._check_tenant_admin(request):
            return HttpResponse(_("Accès refusé"), status=403)

        membership_uuid = uuid.UUID(pk)
        membership = get_object_or_404(Membership, uuid=membership_uuid)

        context = {
            'membership': membership
        }
        return render(request, "admin/membership/partials/custom_form_edit_success.html", context)

    @action(detail=True, methods=['POST'])
    def admin_change_json_form(self, request, pk):
        """
        Point d'entrée HTMX pour sauvegarder les modifications du custom_form.
        HTMX endpoint to save changes to custom_form JSON fields.
        """
        if not self._check_tenant_admin(request):
            return HttpResponse(_("Accès refusé"), status=403)

        membership_uuid = uuid.UUID(pk)
        membership = get_object_or_404(Membership, uuid=membership_uuid)

        if not membership.price or not membership.price.product:
            return HttpResponse(_("Produit non trouvé"), status=400)

        product = membership.price.product
        product_form_fields = ProductFormField.objects.filter(product=product).order_by('order')

        # Validation et traitement des données du formulaire
        # Validate and process form data
        errors = []
        updated_data = dict(membership.custom_form) if membership.custom_form else {}

        for field in product_form_fields:
            # Calcul de label_key : même logique que validators.py:63
            # Compute label_key: same logic as validators.py:63
            label_key = (field.label or '').strip() or field.name

            # Récupération de la valeur envoyée via POST (les inputs utilisent label_key comme name)
            # Get value sent via POST (inputs use label_key as name)
            # Sanitisation des valeurs pour éviter l'injection HTML/XSS
            # Sanitize values to prevent HTML/XSS injection
            field_is_boolean = field.field_type == ProductFormField.FieldType.BOOLEAN
            if field_is_boolean:
                value_from_post = request.POST.get(label_key) == 'true'
            elif field.field_type == ProductFormField.FieldType.MULTI_SELECT:
                raw_list = request.POST.getlist(label_key)
                value_from_post = [clean_text(v) for v in raw_list]
            else:
                value_from_post = clean_text(request.POST.get(label_key, ""))

            # Validation des champs obligatoires
            # Validate required fields
            field_is_required = field.required
            value_is_empty = not value_from_post

            if field_is_required and value_is_empty:
                error_message = _(f"Le champ '{field.label}' est obligatoire.")
                errors.append(error_message)
                continue

            # Mise à jour avec label_key (pas field.name) pour rester cohérent avec le JSON
            # Update with label_key (not field.name) to stay consistent with JSON
            updated_data[label_key] = value_from_post

        # Collecte des label_keys des ProductFormField pour identifier les orphelins
        # Collect ProductFormField label_keys to identify orphan fields
        known_label_keys = set()
        for field in product_form_fields:
            known_label_keys.add((field.label or '').strip() or field.name)

        # Mise à jour des champs orphelins (ajoutés manuellement, pas dans ProductFormField)
        # Update orphan fields (added manually, not in ProductFormField)
        if membership.custom_form:
            for json_key in membership.custom_form:
                if json_key in known_label_keys:
                    continue
                # Sanitisation de la valeur orpheline / Sanitize orphan value
                value_from_post = clean_text(request.POST.get(json_key, ""))
                updated_data[json_key] = value_from_post

        # Si il y a des erreurs, on retourne le formulaire avec les valeurs POST
        # If there are errors, return form with POST values
        if errors:
            form_fields = self._build_form_fields_for_membership(membership, values_override=request.POST)
            context = {
                'membership': membership,
                'form_fields': form_fields,
                'errors': errors,
            }
            return render(request, "admin/membership/partials/custom_form_edit.html", context)

        # Pas d'erreurs : sauvegarde
        # No errors: save
        try:
            membership.custom_form = updated_data
            membership.save(update_fields=['custom_form'])

            logger.info(f"Admin {request.user.email} a modifié le custom_form de l'adhésion {membership.uuid}")

        except Exception as e:
            logger.error(f"Erreur sauvegarde custom_form pour adhésion {membership.uuid}: {e}")

            error_message = _(f"Erreur lors de l'enregistrement : {str(e)}")
            errors.append(error_message)

            form_fields = self._build_form_fields_for_membership(membership, values_override=request.POST)
            context = {
                'membership': membership,
                'form_fields': form_fields,
                'errors': errors,
            }
            return render(request, "admin/membership/partials/custom_form_edit.html", context)

        # Succès : retour à la vue lecture seule
        # Success: return to read-only view
        context = {
            'membership': membership
        }
        return render(request, "admin/membership/partials/custom_form_edit_success.html", context)

    @action(detail=True, methods=['GET'])
    def admin_add_custom_field_form(self, request, pk):
        """
        Point d'entrée HTMX pour afficher le mini-formulaire d'ajout d'un champ libre.
        HTMX endpoint to display the form for adding a free-form custom field.
        """
        if not self._check_tenant_admin(request):
            return HttpResponse(_("Accès refusé"), status=403)

        membership_uuid = uuid.UUID(pk)
        membership = get_object_or_404(Membership, uuid=membership_uuid)

        context = {
            'membership': membership,
            'errors': None,
        }
        return render(request, "admin/membership/partials/custom_form_add_field.html", context)

    @action(detail=True, methods=['POST'])
    def admin_add_custom_field(self, request, pk):
        """
        Point d'entrée HTMX pour ajouter un champ libre au custom_form JSON.
        HTMX endpoint to add a free-form field to the custom_form JSON.

        Permet d'ajouter une paire clé/valeur qui n'est pas définie dans ProductFormField.
        Allows adding a key/value pair not defined in ProductFormField.
        """
        if not self._check_tenant_admin(request):
            return HttpResponse(_("Accès refusé"), status=403)

        membership_uuid = uuid.UUID(pk)
        membership = get_object_or_404(Membership, uuid=membership_uuid)

        # Récupération et sanitisation des valeurs du formulaire
        # Get and sanitize form values
        field_label = clean_text(request.POST.get('new_field_label', '')).strip()
        field_value = clean_text(request.POST.get('new_field_value', '')).strip()

        # Validation : le label est obligatoire
        # Validation: label is required
        errors = []
        if not field_label:
            errors.append(_("Le nom du champ est obligatoire."))

        # Vérification que la clé n'existe pas déjà
        # Check that the key doesn't already exist
        current_data = dict(membership.custom_form) if membership.custom_form else {}
        if field_label in current_data:
            errors.append(_(f"Le champ '{field_label}' existe déjà."))

        if errors:
            context = {
                'membership': membership,
                'errors': errors,
            }
            return render(request, "admin/membership/partials/custom_form_add_field.html", context)

        # Ajout du champ dans le JSON
        # Add the field to JSON
        current_data[field_label] = field_value
        membership.custom_form = current_data
        membership.save(update_fields=['custom_form'])

        logger.info(f"Admin {request.user.email} a ajouté le champ '{field_label}' au custom_form de {membership.uuid}")

        # Retour à la vue lecture seule avec message de succès
        # Return to read-only view with success message
        context = {
            'membership': membership,
        }
        return render(request, "admin/membership/partials/custom_form_edit_success.html", context)

    @action(detail=True, methods=['POST'])
    def send_invoice(self, request, pk=None):
        """
        Envoie le reçu PDF par email à l'adhérent.
        / Sends the PDF receipt by email to the member.

        LOCALISATION : BaseBillet/views.py — MembershipMVT

        FLUX :
        1. Reçoit POST depuis le panneau HTMX admin (actions_panel.html)
        2. Récupère l'adhésion par pk (entier Django)
        3. Lance la tâche Celery send_membership_invoice_to_email
        4. Retourne un partial HTML de confirmation

        DÉPENDANCES :
        - Celery : send_membership_invoice_to_email (BaseBillet/tasks.py)
        - Template : admin/membership/partials/send_invoice_success.html
        """
        membership = get_object_or_404(
            Membership.objects.select_related('user'),
            pk=pk,
        )
        # Lance l'envoi du PDF par email en tâche de fond
        # / Sends the PDF by email as a background task
        send_membership_invoice_to_email.delay(str(membership.uuid))

        return render(request, "admin/membership/partials/send_invoice_success.html", {
            "membership": membership,
        })

    @action(detail=True, methods=['GET', 'POST'])
    def ajouter_paiement(self, request, pk=None):
        """
        Enregistre un paiement hors-ligne sur une adhésion en attente.
        / Records an offline payment on a pending membership.

        LOCALISATION : BaseBillet/views.py — MembershipMVT

        FLUX :
        GET  : retourne le formulaire de paiement (partial HTMX)
        POST :
          1. Valide avec PaiementHorsLigneSerializer
          2. Met à jour l'adhésion (contribution_value, payment_method, status → ONCE)
          3. Crée LigneArticle CREATED puis PAID → déclenche trigger_A (deadline, email, Fedow)
          4. Retourne un partial de succès

        DÉPENDANCES :
        - PaiementHorsLigneSerializer (BaseBillet/validators.py)
        - get_or_create_price_sold, dec_to_int (ApiBillet/serializers.py)
        - Signal pre_save sur LigneArticle → trigger_A (BaseBillet/signals.py)
        - Templates : admin/membership/partials/ajouter_paiement_form.html
                      admin/membership/partials/ajouter_paiement_success.html
        """
        membership = get_object_or_404(
            Membership.objects.select_related('price', 'price__product', 'price__fedow_reward_asset', 'user'),
            pk=pk,
        )

        # Garde : uniquement pour les adhésions en attente de paiement
        # / Guard: only for memberships awaiting payment
        statuts_autorises = [Membership.WAITING_PAYMENT, Membership.ADMIN_WAITING, Membership.ADMIN_VALID]
        if membership.status not in statuts_autorises:
            return render(request, "admin/membership/partials/ajouter_paiement_form.html", {
                "membership": membership,
                "error": _("Cette adhésion n'est pas en attente de paiement."),
                "moyens_de_paiement": PaymentMethod.classic(),
            })

        if request.method == 'GET':
            # Retourne le formulaire avec le montant par défaut pré-rempli
            # / Returns the form with the default amount pre-filled
            montant_par_defaut = membership.price.prix if membership.price else ""
            return render(request, "admin/membership/partials/ajouter_paiement_form.html", {
                "membership": membership,
                "montant_par_defaut": montant_par_defaut,
                "moyens_de_paiement": PaymentMethod.classic(),
            })

        # POST : validation avec serializer (stack-ccc : jamais de try/except inline)
        # / POST: validate with serializer (stack-ccc: never inline try/except)
        serializer_paiement = PaiementHorsLigneSerializer(data=request.POST)
        if not serializer_paiement.is_valid():
            # Retourne le formulaire avec les erreurs inline
            # / Returns the form with inline errors
            return render(request, "admin/membership/partials/ajouter_paiement_form.html", {
                "membership": membership,
                "montant_par_defaut": request.POST.get("amount", ""),
                "moyens_de_paiement": PaymentMethod.classic(),
                "errors": serializer_paiement.errors,
            })

        montant_valide = serializer_paiement.validated_data['amount']
        moyen_paiement_valide = serializer_paiement.validated_data['payment_method']

        # 1. Mise à jour de l'adhésion AVANT la création de LigneArticle
        #    trigger_A a besoin de last_contribution pour calculer la deadline
        # / Update membership BEFORE creating LigneArticle (trigger_A needs last_contribution)
        membership.contribution_value = dround(montant_valide)
        membership.payment_method = moyen_paiement_valide
        if not membership.first_contribution:
            membership.first_contribution = timezone.localtime()
        membership.last_contribution = timezone.localtime()
        membership.status = Membership.ONCE
        membership.save()

        # 2. Crée la LigneArticle en CREATED puis la passe en PAID
        #    CREATED → PAID déclenche trigger_A via signal pre_save
        # / Creates LigneArticle as CREATED then sets to PAID — triggers trigger_A
        pricesold = get_or_create_price_sold(membership.price)
        ligne_article_paiement = LigneArticle.objects.create(
            pricesold=pricesold,
            qty=1,
            membership=membership,
            amount=dec_to_int(membership.contribution_value),
            payment_method=moyen_paiement_valide,
            status=LigneArticle.CREATED,
            sale_origin=SaleOrigin.ADMIN,
        )
        ligne_article_paiement.status = LigneArticle.PAID
        ligne_article_paiement.save()

        return render(request, "admin/membership/partials/ajouter_paiement_success.html", {
            "membership": membership,
        })

    @action(detail=True, methods=['GET', 'POST'])
    def cancel(self, request, pk=None):
        """
        Annule une adhésion avec option de créer un avoir comptable.
        / Cancels a membership with option to create a credit note.

        LOCALISATION : BaseBillet/views.py — MembershipMVT

        FLUX :
        GET  : retourne le formulaire de confirmation inline (partial HTMX)
        POST :
          1. Passe l'adhésion en ADMIN_CANCELED
          2. Crée les avoirs si demandé (with_credit_note=1 dans le POST)
          3. Retourne HX-Redirect vers la changelist (adhésion terminée)

        DÉPENDANCES :
        - LigneArticle.credit_notes (related_name de credit_note_for FK)
        - Template : admin/membership/partials/cancel_form.html
        """
        membership = get_object_or_404(
            Membership.objects.select_related('user', 'price', 'price__product'),
            pk=pk,
        )

        # Lignes de vente payées liées à cette adhésion, sans avoir existant
        # / Paid sale lines for this membership, without existing credit note
        lignes_de_vente_payees = LigneArticle.objects.filter(
            membership=membership,
            status__in=[LigneArticle.VALID, LigneArticle.PAID],
        ).exclude(
            credit_notes__isnull=False,
        ).select_related('pricesold', 'pricesold__productsold')

        if request.method == 'GET':
            # Retourne le formulaire de confirmation inline
            # / Returns the inline confirmation form
            return render(request, "admin/membership/partials/cancel_form.html", {
                "membership": membership,
                "membership_email": membership.user.email if membership.user else "—",
                "has_paid_lines": lignes_de_vente_payees.exists(),
                "lignes_payees": lignes_de_vente_payees,
            })

        # POST : annulation effective
        # / POST: actual cancellation
        membership.archiver = True
        membership.status = Membership.ADMIN_CANCELED
        membership.save()

        # Crée les avoirs si demandé
        # / Creates credit notes if requested
        creation_avoirs_demandee = request.POST.get("with_credit_note") == "1"
        if creation_avoirs_demandee:
            nombre_avoirs_crees = 0
            for ligne in lignes_de_vente_payees:
                avoir = LigneArticle.objects.create(
                    pricesold=ligne.pricesold,
                    qty=-ligne.qty,
                    amount=ligne.amount,
                    vat=ligne.vat,
                    paiement_stripe=ligne.paiement_stripe,
                    membership=membership,
                    payment_method=ligne.payment_method,
                    asset=ligne.asset,
                    wallet=ligne.wallet,
                    sale_origin=SaleOrigin.ADMIN,
                    credit_note_for=ligne,
                    status=LigneArticle.CREATED,
                )
                avoir.status = LigneArticle.CREDIT_NOTE
                avoir.save()
                nombre_avoirs_crees += 1

            messages.success(
                request,
                _("Adhésion annulée. %(count)d avoir(s) créé(s).") % {"count": nombre_avoirs_crees}
            )
        else:
            messages.success(request, _("Adhésion annulée."))

        # Redirige vers la liste des adhésions (HX-Redirect pour HTMX)
        # / Redirects to the membership list (HX-Redirect for HTMX)
        url_liste_adhesions = reverse('staff_admin:BaseBillet_membership_changelist')
        response = HttpResponse(status=204)
        response['HX-Redirect'] = url_liste_adhesions
        return response

    @action(detail=True, methods=['GET'])
    def cancel_reset(self, request, pk=None):
        """
        Vide la zone de réponse #response-cancel (utilisateur clique "Retour" dans le formulaire).
        / Clears the #response-cancel response zone (user clicks "Back" in the form).

        LOCALISATION : BaseBillet/views.py — MembershipMVT

        Le bouton "Annuler l'adhésion" reste toujours visible dans la barre d'actions.
        Retourner "" suffit à vider la zone via hx-swap="innerHTML".
        / The "Cancel membership" button stays visible in the toolbar at all times.
        Returning "" is enough to clear the zone via hx-swap="innerHTML".
        """
        return HttpResponse("")

    @action(detail=True, methods=['GET'])
    def ajouter_paiement_reset(self, request, pk=None):
        """
        Vide la zone de réponse #response-paiement (utilisateur clique "Annuler" dans le formulaire).
        / Clears the #response-paiement response zone (user clicks "Cancel" in the form).

        LOCALISATION : BaseBillet/views.py — MembershipMVT

        Le bouton "Enregistrer un paiement" reste toujours visible dans la barre d'actions.
        / The "Register payment" button stays visible in the toolbar at all times.
        """
        return HttpResponse("")

    @action(detail=True, methods=['GET'])
    def renouveller(self, request, pk=None):
        """
        Affiche une boîte de confirmation avant de naviguer vers le formulaire de renouvellement.
        / Shows a confirmation box before navigating to the renewal form.

        LOCALISATION : BaseBillet/views.py — MembershipMVT

        FLUX :
        GET : retourne le partial de confirmation avec l'URL pré-remplie en contexte.
        / GET: returns the confirmation partial with the pre-filled URL as context.
        Le bouton "Continuer" du partial est un lien direct (navigation normale).
        / The partial's "Continue" button is a direct link (normal navigation).

        DÉPENDANCES :
        - Template : admin/membership/partials/renouveller_confirm.html
        """
        from urllib.parse import urlencode as urllib_urlencode

        membership = get_object_or_404(
            Membership.objects.select_related('user', 'price', 'price__product'),
            pk=pk,
        )

        # Construction de l'URL du formulaire d'ajout avec les champs pré-remplis
        # / Build the add form URL with pre-filled fields
        url_formulaire_ajout = reverse('staff_admin:BaseBillet_membership_add')
        params_renouvellement = {}
        if getattr(membership, 'user', None) and getattr(membership.user, 'email', None):
            params_renouvellement['email'] = membership.user.email
        if membership.price_id:
            params_renouvellement['price'] = membership.price_id
        if membership.contribution_value is not None:
            params_renouvellement['contribution'] = str(membership.contribution_value)
        if membership.payment_method:
            params_renouvellement['payment_method'] = membership.payment_method
        if membership.first_name:
            params_renouvellement['first_name'] = membership.first_name
        if membership.last_name:
            params_renouvellement['last_name'] = membership.last_name
        url_renouvellement = f"{url_formulaire_ajout}?{urllib_urlencode(params_renouvellement, doseq=True)}"

        return render(request, "admin/membership/partials/renouveller_confirm.html", {
            "membership": membership,
            "renouveller_url": url_renouvellement,
        })

    @action(detail=True, methods=['GET'])
    def renouveller_reset(self, request, pk=None):
        """
        Vide la zone de réponse #response-renouveller (utilisateur clique "Annuler").
        / Clears the #response-renouveller response zone (user clicks "Cancel").

        LOCALISATION : BaseBillet/views.py — MembershipMVT
        """
        return HttpResponse("")

    def get_permissions(self):
        if self.action in [
            'invoice_to_mail', 'admin_accept',
            'admin_edit_json_form', 'admin_cancel_edit', 'admin_change_json_form',
            'admin_add_custom_field_form', 'admin_add_custom_field',
            'send_invoice', 'cancel', 'ajouter_paiement',
            'cancel_reset', 'ajouter_paiement_reset',
            'renouveller', 'renouveller_reset',
        ]:
            permission_classes = [TenantAdminPermission, ]

        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]


# =============================================================================
# Classe `Tenant` (ViewSet) — SUPPRIMEE lors de la session 2026-05-16.
# / Class `Tenant` (ViewSet) — REMOVED during the 2026-05-16 session.
# =============================================================================
#
# Cette classe melangeait deux responsabilites disjointes :
#
# 1. Creation de tenant via le flow legacy `/tenant/new/`. Remplace par
#    l'app `onboard/` (wizard multi-step avec OTP, magic-link et SSO).
#    Methodes supprimees : `new`, `create_waiting_configuration`,
#    `emailconfirmation_tenant`, `onboard_stripe`, `onboard_stripe_return`.
#
# 2. Onboarding Stripe Connect d'un tenant EXISTANT (depuis l'admin
#    Unfold). Migre vers `PaiementStripe/views.py::StripeConnectOnboardingViewSet`.
#    Methodes deplacees : `onboard_stripe_from_config`,
#    `onboard_stripe_return_from_config`.
#
# / This class mixed two disjoint responsibilities: (1) legacy tenant
# creation flow, now in `onboard/`; (2) Stripe Connect onboarding for
# an existing tenant, moved to `PaiementStripe/views.py::StripeConnectOnboardingViewSet`.
#
# References :
#   - `TECH_DOC/SESSIONS/ONBOARD/03-session-recap.md`
#   - `TECH_DOC/SESSIONS/MOYENS_PAIEMENT/01-stripe-migration-spec.md`


# =============================================================================
# Helpers communs du choix de lieu (wizards admin + public).
# Le choix de lieu se fait en 2 pages, comme l'onboarding :
#   Page 1 (choix)  : adresse existante (liste filtrable) OU nom d'un nouveau lieu.
#   Page 2 (carte)  : carte pre-remplie avec le nom -> recherche auto + adresse.
# Les deux wizards partagent la logique ; seuls changent les URLs, le prefixe
# de session et les templates. On factorise ici au niveau module.
# / Shared place-selection helpers (admin + public wizards). Two pages like the
# onboarding flow: page 1 picks an existing address (filterable list) or a new
# place name; page 2 shows the map pre-filled with that name (auto-search). Both
# wizards share this logic; only URLs, session prefix and templates differ.
# =============================================================================

def _wizard_lieu_session_key(session_prefix, suffix):
    """Construit la cle de session prefixee pour le choix de lieu.
    / Build the prefixed session key for the place selection."""
    return f"{session_prefix}_{suffix}"


def _wizard_etape_choix_lieu(request, *, template, contexte_commun,
                             session_prefix, map_url_name, event_url_name):
    """
    Page 1 commune (admin + public) : choix du lieu.

    GET  : affiche le toggle (adresse existante filtrable / nouveau lieu).
    POST :
      - adresse existante -> on memorise le pk et on file a l'etape event.
      - nouveau lieu       -> on memorise le nom et on file a la page carte.

    / Shared step 1 (admin + public): place selection. GET shows the toggle;
    POST routes to the event step (existing) or to the map page (new).
    """
    addresses = PostalAddress.objects.all().order_by("name", "address_locality")
    config = Configuration.get_solo()

    contexte_page = dict(contexte_commun)
    contexte_page.update({
        "addresses": addresses,
        "default_address_pk": config.postal_address.pk if config.postal_address else None,
        # Email du proposeur : affiche seulement pour un visiteur anonyme.
        # / Proposer email: shown only for an anonymous visitor.
        "demander_email": not request.user.is_authenticated,
    })

    if request.method == "GET":
        context = get_context(request)
        context.update(contexte_page)
        context.update({"initial": {}, "errors": {}})
        return render(request, template, context=context)

    # POST
    serializer = WizardPlaceSelectSerializer(data=request.POST, context={"request": request})
    if not serializer.is_valid():
        context = get_context(request)
        context.update(contexte_page)
        context.update({"initial": request.POST.dict(), "errors": serializer.errors})
        return render(request, template, context=context, status=422)

    data = serializer.validated_data

    # Email du proposeur (anonyme) : on le garde en session pour la
    # finalisation (creation/recuperation du compte SANS validation immediate).
    # / Proposer email (anonymous): kept in session for finalization
    # (account get_or_create WITHOUT immediate email validation).
    email_proposeur = (data.get("email_proposeur") or "").strip()
    if email_proposeur:
        request.session[_wizard_lieu_session_key(session_prefix, "email_proposeur")] = email_proposeur

    # Ce formulaire (adresse existante OU nouveau lieu saisi à la main) ne vient
    # PAS d'une fiche Tiers-Lieux. On nettoie un éventuel pré-remplissage TL
    # resté en session — cas : l'utilisateur avait cliqué « Utiliser ce lieu »
    # puis est revenu en arrière pour saisir le lieu à la main. Sans ce nettoyage,
    # la page carte poserait le marqueur sur l'ancienne fiche (GPS résiduel) au
    # lieu de lancer la recherche Nominatim sur le nouveau nom.
    # / This form (existing address OR hand-typed new place) does NOT come from a
    # Tiers-Lieux record. Clear any leftover TL pre-fill in session (user clicked
    # "Use this place" then went back to type manually). Otherwise the map step
    # would place the marker on the stale record instead of running Nominatim.
    request.session.pop(_wizard_lieu_session_key(session_prefix, "tierslieux_adresse_recherche"), None)
    request.session.pop(_wizard_lieu_session_key(session_prefix, "tierslieux_prefill"), None)

    if data["_mode"] == "existing":
        # Adresse existante : on garde le pk et on nettoie un eventuel nom.
        # / Existing address: keep the pk, clear any pending new-place name.
        request.session[_wizard_lieu_session_key(session_prefix, "postal_address_pk")] = data["postal_address"]
        request.session.pop(_wizard_lieu_session_key(session_prefix, "new_address_name"), None)
        return redirect(event_url_name)

    # Nouveau lieu : on garde le nom et on va sur la page carte.
    # / New place: keep the name and go to the map page.
    request.session[_wizard_lieu_session_key(session_prefix, "new_address_name")] = data["new_address_name"]
    request.session.pop(_wizard_lieu_session_key(session_prefix, "postal_address_pk"), None)
    return redirect(map_url_name)


def _wizard_etape_carte_lieu(request, *, template, contexte_commun,
                             session_prefix, choix_url_name, event_url_name):
    """
    Page 2 commune (admin + public) : carte du nouveau lieu.

    Le nom du lieu a ete saisi en page 1 et vit en session ; on s'en sert pour
    pre-remplir la recherche de la carte (le widget lance la recherche tout
    seul). POST -> cree la PostalAddress et file a l'etape event.

    / Shared step 2 (admin + public): new-place map. The place name lives in
    session (entered on page 1) and pre-fills the map search (the widget
    auto-runs it). POST creates the PostalAddress and goes to the event step.
    """
    nom_nouveau_lieu = request.session.get(
        _wizard_lieu_session_key(session_prefix, "new_address_name")
    )
    if not nom_nouveau_lieu:
        # Pas de nom en session (acces direct) -> retour au choix du lieu.
        # / No name in session (direct access) -> back to place selection.
        return redirect(choix_url_name)

    contexte_page = dict(contexte_commun)
    contexte_page.update({"new_address_name": nom_nouveau_lieu})

    # Texte de recherche pré-rempli pour le widget carte : si on vient d'une
    # fiche Tiers-Lieux (CHANTIER-04), on passe l'adresse complète pour que le
    # géocodage trouve le bon point ; sinon le nom du lieu suffit.
    # / Pre-filled search text for the map widget: full address if coming from a
    # Tiers-Lieux record, otherwise the place name.
    adresse_recherche = request.session.get(
        _wizard_lieu_session_key(session_prefix, "tierslieux_adresse_recherche")
    )
    contexte_page.update({"adresse_recherche": adresse_recherche or nom_nouveau_lieu})

    # Pré-remplissage GPS + adresse structurée (si on vient d'une fiche
    # Tiers-Lieux avec coordonnées) : le widget carte pose le marqueur sur la
    # géoloc de l'API et remplit les champs DIRECTEMENT, sans géocodage.
    # On garantit TOUTES les clés (même vides) : dans un template Django,
    # `valeur|default:prefill.latitude` lève VariableDoesNotExist si la clé
    # `latitude` manque (la résolution d'un ARGUMENT de filtre ne tolère pas une
    # clé absente, contrairement à l'opérande principal). En saisie manuelle, le
    # prefill est absent -> dict de clés vides -> le widget bascule sur Nominatim.
    # / GPS + structured-address pre-fill (from a Tiers-Lieux record with coords):
    # the widget places the marker and fills fields directly. We ensure ALL keys
    # (even empty): a missing dict key in a filter argument (`default:prefill.x`)
    # raises VariableDoesNotExist. Manual entry -> empty keys -> widget uses Nominatim.
    prefill_session = request.session.get(
        _wizard_lieu_session_key(session_prefix, "tierslieux_prefill")
    ) or {}
    prefill = {
        "latitude": prefill_session.get("latitude", ""),
        "longitude": prefill_session.get("longitude", ""),
        "street_address": prefill_session.get("street_address", ""),
        "postal_code": prefill_session.get("postal_code", ""),
        "address_locality": prefill_session.get("address_locality", ""),
    }
    contexte_page.update({"prefill": prefill})

    if request.method == "GET":
        context = get_context(request)
        context.update(contexte_page)
        context.update({"initial": {}, "errors": {}})
        return render(request, template, context=context)

    # POST
    serializer = WizardPlaceMapSerializer(data=request.POST)
    if not serializer.is_valid():
        context = get_context(request)
        context.update(contexte_page)
        context.update({"initial": request.POST.dict(), "errors": serializer.errors})
        return render(request, template, context=context, status=422)

    data = serializer.validated_data
    # Creation de la PostalAddress via le serializer schema.org existant.
    # / Create the PostalAddress via the existing schema.org serializer.
    from api_v2.serializers import PostalAddressCreateSerializer
    payload = {
        "name": nom_nouveau_lieu,
        "streetAddress": data["street_address"],
        "addressLocality": data["address_locality"],
        "postalCode": data["postal_code"],
        "addressCountry": data.get("address_country") or "France",
    }
    pa_ser = PostalAddressCreateSerializer(data=payload, context={"request": request})
    pa_ser.is_valid(raise_exception=True)
    addr = pa_ser.save()
    # Ajout lat/lng (non gere par le serializer schema.org).
    # / Add lat/lng (not handled by the schema.org serializer).
    addr.latitude = data["place_latitude"]
    addr.longitude = data["place_longitude"]
    addr.save(update_fields=["latitude", "longitude"])

    request.session[_wizard_lieu_session_key(session_prefix, "postal_address_pk")] = str(addr.pk)
    request.session.pop(_wizard_lieu_session_key(session_prefix, "new_address_name"), None)
    request.session.pop(_wizard_lieu_session_key(session_prefix, "tierslieux_adresse_recherche"), None)
    request.session.pop(_wizard_lieu_session_key(session_prefix, "tierslieux_prefill"), None)
    return redirect(event_url_name)


# =============================================================================
# Helpers communs des brouillons d'evenements (etape "events" des 2 wizards).
# On peut ajouter PLUSIEURS evenements avant de finaliser (repris du formulaire
# multi-events de l'onboarding). Les brouillons vivent en session HTTP (liste
# de dicts) ; les images uploadees sont stockees en `default_storage` et seul
# leur chemin relatif est garde dans la session. La finalisation (propre a
# chaque wizard) cree N `Event` partageant le lieu choisi a l'etape 1.
# / Shared event-draft helpers (the "events" step of both wizards). The user
# can add SEVERAL events before finalizing (mirrors the onboarding multi-event
# form). Drafts live in the HTTP session (list of dicts); uploaded images go to
# default_storage and only their relative path is kept in the session. Finalize
# (per-wizard) creates N Events sharing the place chosen at step 1.
# =============================================================================

def _wizard_drafts_key(session_prefix):
    """Cle de session de la liste des brouillons d'events.
    / Session key of the event drafts list."""
    return f"{session_prefix}_event_drafts"


def _wizard_get_drafts(request, session_prefix):
    """Liste des brouillons (jamais None).
    / Drafts list (never None)."""
    return request.session.get(_wizard_drafts_key(session_prefix), [])


def _wizard_set_drafts(request, session_prefix, drafts):
    """Ecrit la liste des brouillons en session.
    / Persist the drafts list in session."""
    request.session[_wizard_drafts_key(session_prefix)] = drafts
    request.session.modified = True


def _wizard_store_draft_image(image_file, session_prefix):
    """
    Stocke une image de brouillon dans `default_storage` et renvoie son
    chemin relatif (gardable en session JSON, compatible S3). Meme approche
    que l'onboarding (cf. onboard/views.py events_add).
    / Store a draft image in default_storage and return its relative path
    (JSON-session friendly, S3-compatible). Same approach as onboarding.
    """
    import os
    import uuid as uuid_module

    from django.core.files.storage import default_storage

    _, extension = os.path.splitext(image_file.name or "")
    extension = (extension or ".bin").lower()
    chemin_cible = (
        f"event_wizard_drafts/{session_prefix}/"
        f"{uuid_module.uuid4().hex}{extension}"
    )
    return default_storage.save(chemin_cible, image_file)


def _wizard_render_events_inner(request, *, session_prefix, inner_context, status=200):
    """
    Rend le partial HTMX `_events_inner.html` (liste des brouillons + sous-form
    d'ajout). Cible des swaps add/remove. `inner_context` porte les variables
    propres au wizard (add_url, remove_url_name, show_admin_fields, all_tags).
    / Render the HTMX partial `_events_inner.html` (drafts list + add sub-form).
    Target of the add/remove swaps. `inner_context` carries wizard-specific
    variables (add_url, remove_url_name, show_admin_fields, all_tags).
    """
    contexte = dict(inner_context)
    contexte.setdefault("errors", {})
    contexte.setdefault("initial", {})
    contexte["events"] = _wizard_get_drafts(request, session_prefix)
    return render(
        request,
        "fonctionnel/event_wizard/_events_inner.html",
        context=contexte,
        status=status,
    )


def _wizard_events_add_generic(request, *, serializer_class, session_prefix,
                               build_draft, inner_context):
    """
    Ajoute un brouillon d'event (commun admin + public).
    Valide le sous-form, stocke l'image eventuelle, append le brouillon en
    session, puis re-rend le partial liste+form. En cas d'erreur : re-rend
    avec les erreurs et les valeurs saisies (status 422), liste inchangee.
    / Add an event draft (shared admin + public). Validate, store optional
    image, append to session, re-render the list+form partial. On error:
    re-render with errors + submitted values (422), list unchanged.
    """
    # Pour les ImageField : fusionner POST + FILES.
    # / For ImageField support: merge POST + FILES.
    data_combined = request.POST.copy()
    for f_key in request.FILES:
        data_combined[f_key] = request.FILES[f_key]

    serializer = serializer_class(data=data_combined)
    if not serializer.is_valid():
        # On renvoie 200 (et NON 422) volontairement : HTMX ne swappe pas les
        # reponses 4xx par defaut, et le skin reunion n'a pas de config
        # `htmx:beforeOnLoad` pour forcer le swap sur erreur. Renvoyer 200 avec
        # le partial re-rendu (erreurs + valeurs saisies) garantit l'affichage.
        # Meme choix que le multi-events de l'onboarding.
        # / Return 200 (NOT 422) on purpose: HTMX won't swap 4xx by default and
        # the reunion skin has no swap-on-error config. 200 + the re-rendered
        # partial (errors + submitted values) guarantees display. Same choice
        # as the onboarding multi-event form.
        return _wizard_render_events_inner(
            request,
            session_prefix=session_prefix,
            inner_context={
                **inner_context,
                "errors": serializer.errors,
                "initial": request.POST.dict(),
            },
        )

    validated = serializer.validated_data
    image_path = None
    if validated.get("image"):
        image_path = _wizard_store_draft_image(validated["image"], session_prefix)

    # Le wizard decide quels champs garder dans le brouillon (public vs admin).
    # / The wizard decides which fields to keep in the draft (public vs admin).
    draft = build_draft(validated, image_path)

    drafts = _wizard_get_drafts(request, session_prefix)
    drafts.append(draft)
    _wizard_set_drafts(request, session_prefix, drafts)

    return _wizard_render_events_inner(
        request, session_prefix=session_prefix, inner_context=inner_context,
    )


def _wizard_events_remove_generic(request, idx, *, session_prefix, inner_context):
    """
    Retire le brouillon a l'index `idx` (commun admin + public) et supprime
    son image temporaire eventuelle. Re-rend le partial liste+form.
    / Remove the draft at index `idx` (shared) and delete its temp image if
    any. Re-render the list+form partial.
    """
    drafts = _wizard_get_drafts(request, session_prefix)
    try:
        index = int(idx)
    except (TypeError, ValueError):
        index = -1

    if 0 <= index < len(drafts):
        brouillon_retire = drafts.pop(index)
        # Nettoyage de l'image temporaire (si presente).
        # / Clean up the temp image (if any).
        if brouillon_retire.get("image"):
            from django.core.files.storage import default_storage
            try:
                default_storage.delete(brouillon_retire["image"])
            except Exception as erreur_suppression:
                logger.warning(
                    "Suppression image brouillon échouée: %s", erreur_suppression
                )
        _wizard_set_drafts(request, session_prefix, drafts)

    return _wizard_render_events_inner(
        request, session_prefix=session_prefix, inner_context=inner_context,
    )


def _attacher_image_brouillon(event, draft):
    """
    Migre l'image temporaire du brouillon (event_wizard_drafts/...) vers le champ
    img de l'event (dossier images/).
    save=False : l'event sera sauve UNE seule fois par l'appelant, donc les signaux
    post_save ne se declenchent qu'une fois.
    ATTENTION : le fichier temporaire n'est PAS supprime ici. La creation des
    events est enveloppee dans transaction.atomic() (doublon possible) : un
    rollback DB n'annule pas une suppression de fichier, et les brouillons
    conserves en session referencent encore ce chemin. La suppression se fait
    par l'appelant APRES le commit (step2_event).
    / Migrate the draft temp image into event.img (images/).
    save=False: the caller saves the event once (signals fire once).
    WARNING: the temp file is NOT deleted here. Event creation runs inside
    transaction.atomic() (duplicates possible): a DB rollback does not undo a
    file deletion, and the session drafts still reference this path. The
    caller deletes temp files AFTER the commit (step2_event).

    LOCALISATION : BaseBillet/views.py
    """
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    chemin_temp = draft.get("image")
    if not chemin_temp or not default_storage.exists(chemin_temp):
        return
    with default_storage.open(chemin_temp, "rb") as fichier_temp:
        contenu = fichier_temp.read()
    extension = os.path.splitext(chemin_temp)[1] or ".jpg"
    # Recopie reelle dans images/ (variations StdImage generees a la sauvegarde).
    # / Real copy into images/ (StdImage variations generated on save).
    event.img.save(f"event_{uuid.uuid4().hex[:8]}{extension}", ContentFile(contenu), save=False)


def _creer_event_depuis_brouillon(draft, postal_address, user, est_staff):
    """
    Cree un Event depuis un brouillon du wizard UNIFIE (CHANTIER-03).
    - Staff -> event publie (published=True, is_proposal=False).
    - Public -> proposition (published=False, is_proposal=True) + tag automatique
      (FederationConfiguration.tag_auto_proposition) si configure.
    Tags du formulaire : staff = creation libre ; public = UNIQUEMENT les tags
    EXISTANTS (anti-spam, pas de creation par un visiteur).
    jauge_max + produit FREERES : pour tous (staff comme proposeurs).
    / Create an Event from a unified-wizard draft. Staff -> published; public ->
    proposal + auto tag; public form tags limited to existing tags (no creation).

    LOCALISATION : BaseBillet/views.py
    """
    from django.utils.dateparse import parse_datetime

    event = Event(
        name=(draft.get("name") or "").strip(),
        datetime=parse_datetime(draft["datetime"]),
        long_description=admin_clean_html(draft.get("long_description") or ""),
        postal_address=postal_address,
        created_by=user if user.is_authenticated else None,
        published=est_staff,
        is_proposal=not est_staff,
    )
    _attacher_image_brouillon(event, draft)

    # Jauge + produit FREERES : pour tous (staff comme proposeurs).
    # / Gauge + FREERES product: for everyone (staff and proposers).
    jauge = draft.get("jauge_max")
    if jauge:
        event.jauge_max = jauge
        event.show_gauge = True
    event.save()

    # Reglages d'agenda participatif (deplaces sur FederationConfiguration).
    # / Participatory-agenda settings (moved to FederationConfiguration).
    federation_config = FederationConfiguration.get_solo()

    # Tags saisis dans le formulaire (sépares par virgule/point-virgule).
    # / Form tags (comma/semicolon separated).
    noms_tags = [t.strip() for t in re.split(r"[,;]", draft.get("tags") or "") if t.strip()]
    if est_staff:
        # Staff : creation libre des tags.
        # / Staff: free tag creation.
        for tname in noms_tags:
            tag_obj, _tag_created = Tag.objects.get_or_create(name=tname)
            event.tag.add(tag_obj)
    else:
        # Public : on ne garde que les tags EXISTANTS (pas de creation).
        # / Public: keep only EXISTING tags (no creation).
        for tag_obj in Tag.objects.filter(name__in=noms_tags):
            event.tag.add(tag_obj)
        # Tag automatique des propositions, si configure.
        # / Automatic proposal tag, if configured.
        if federation_config.tag_auto_proposition_id:
            event.tag.add(federation_config.tag_auto_proposition)

    if jauge:
        free_res = Product.objects.filter(
            categorie_article=Product.FREERES, publish=True, archive=False
        ).first()
        if free_res:
            event.products.add(free_res)

    return event


class EventWizard(viewsets.ViewSet):
    """
    Wizard event UNIFIE (front, CHANTIER-03). Remplace EventWizardAdmin +
    EventWizardPublic. Un seul parcours, comportement selon le contexte :
    - Staff (droits de creation d'event) : champs jauge/tags, event PUBLIE.
    - Public (connecte ou anonyme autorise) : proposition moderee + tag auto.
    Acces public conditionne par module_agenda_participatif + proposition_anonyme_autorisee.
    / Unified front event wizard. Staff -> published; public -> moderated proposal.

    LOCALISATION : BaseBillet/views.py
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [permissions.AllowAny]

    SESSION_PREFIX = "event_wizard"

    def _session_key(self, suffix):
        return f"{self.SESSION_PREFIX}_{suffix}"

    def _est_staff(self, request):
        # Staff = a les droits de creation d'event (meme permission que l'ancien wizard admin).
        # / Staff = has event-creation rights (same permission as the old admin wizard).
        return bool(CanCreateEventPermission().has_permission(request, self))

    def _garde_acces(self, request):
        """
        Garde d'acces du wizard. Staff : toujours autorise. Public : seulement si
        l'agenda participatif est actif ; anonyme : seulement si autorise par la config.
        / Access guard. Staff always; public if participatory agenda on; anonymous
        only if allowed by config.
        Retourne un redirect/raise si refuse, None sinon.
        """
        if self._est_staff(request):
            return None
        federation_config = FederationConfiguration.get_solo()
        if not federation_config.module_agenda_participatif:
            raise Http404()
        if not request.user.is_authenticated and not federation_config.proposition_anonyme_autorisee:
            messages.add_message(request, messages.WARNING,
                                 _("Merci de vous connecter d'abord."))
            return redirect(f"{reverse('event-list')}?login=1")
        return None

    def _postal_address_ou_redirect(self, request):
        pk = request.session.get(self._session_key("postal_address_pk"))
        if not pk:
            return None, redirect("event-wizard-place")
        try:
            return PostalAddress.objects.get(pk=pk), None
        except PostalAddress.DoesNotExist:
            request.session.pop(self._session_key("postal_address_pk"), None)
            return None, redirect("event-wizard-place")

    def _inner_context_events(self, request, postal_address):
        est_staff = self._est_staff(request)
        return {
            "add_url": reverse("event-wizard-events-add"),
            "remove_url_name": "event-wizard-events-remove",
            "show_admin_fields": est_staff,
            # Tags existants : pour le staff (autocomplete libre) ET le public
            # (selection parmi l'existant, pas de creation).
            # / Existing tags: free for staff, selection-only for public.
            "all_tags": Tag.objects.all().order_by("name"),
            "postal_address": postal_address,
        }

    def _build_draft(self, validated, image_path):
        # tags + jauge_max stockes dans le brouillon ; le filtrage par role
        # se fait a la creation (_creer_event_depuis_brouillon).
        # / tags + jauge_max kept in the draft; role filtering happens at creation.
        draft = {
            "name": validated["name"].strip(),
            "datetime": validated["datetime"].isoformat(),
            "long_description": validated.get("long_description") or "",
            "tags": validated.get("tags", ""),
            "jauge_max": validated.get("jauge_max"),
        }
        if image_path:
            draft["image"] = image_path
        return draft

    @action(detail=False, methods=["GET", "POST"], url_path="place", url_name="place")
    def step1_place(self, request):
        garde = self._garde_acces(request)
        if garde:
            return garde
        est_staff = self._est_staff(request)
        contexte_commun = {
            "wizard_title": _("Ajouter un évènement") if est_staff else _("Proposer un évènement"),
            "wizard_step_label": _("Lieu"),
            "form_action_url": reverse("event-wizard-place"),
            "next_step_label": _("Continuer"),
        }
        return _wizard_etape_choix_lieu(
            request,
            template="fonctionnel/event_wizard/public_step1_place.html",
            contexte_commun=contexte_commun,
            session_prefix=self.SESSION_PREFIX,
            map_url_name="event-wizard-map",
            event_url_name="event-wizard-event",
        )

    @action(detail=False, methods=["GET", "POST"], url_path="map", url_name="map")
    def step_map(self, request):
        garde = self._garde_acces(request)
        if garde:
            return garde
        est_staff = self._est_staff(request)
        contexte_commun = {
            "wizard_title": _("Ajouter un évènement") if est_staff else _("Proposer un évènement"),
            "wizard_step_label": _("Localiser le nouveau lieu"),
            "form_action_url": reverse("event-wizard-map"),
            "next_step_label": _("Continuer"),
            "wizard_back_url": reverse("event-wizard-place"),
        }
        return _wizard_etape_carte_lieu(
            request,
            template="fonctionnel/event_wizard/public_step_map.html",
            contexte_commun=contexte_commun,
            session_prefix=self.SESSION_PREFIX,
            choix_url_name="event-wizard-place",
            event_url_name="event-wizard-event",
        )

    @action(detail=False, methods=["GET", "POST"], url_path="event", url_name="event")
    def step2_event(self, request):
        garde = self._garde_acces(request)
        if garde:
            return garde
        postal_address, redirection = self._postal_address_ou_redirect(request)
        if redirection:
            return redirection
        est_staff = self._est_staff(request)

        if request.method == "GET":
            context = get_context(request)
            context.update({
                "wizard_title": _("Ajouter des évènements") if est_staff else _("Proposer des évènements"),
                "wizard_step_label": _("Évènements"),
                "finalize_url": reverse("event-wizard-event"),
                "finalize_label": _("Créer les évènements") if est_staff else _("Envoyer ma proposition"),
                "back_url": reverse("event-wizard-place"),
                "est_staff": est_staff,
                "events": _wizard_get_drafts(request, self.SESSION_PREFIX),
                "errors": {}, "initial": {},
            })
            context.update(self._inner_context_events(request, postal_address))
            return render(request, "fonctionnel/event_wizard/step2_event.html",
                          context=context)

        # POST = finalisation.
        # / POST = finalize.
        drafts = _wizard_get_drafts(request, self.SESSION_PREFIX)
        if not drafts:
            messages.add_message(request, messages.WARNING,
                _("Ajoutez au moins un évènement avant de continuer."))
            return redirect("event-wizard-event")

        # Qui sera l'auteur (created_by) des evenements ?
        # - staff / connecte : l'utilisateur de la requete.
        # - anonyme : on cree (ou recupere) un compte depuis l'email saisi a
        #   l'etape 1, SANS envoyer le mail de validation (send_mail=False).
        #   La personne validera son email elle-meme plus tard. L'evenement
        #   reste une proposition moderee (est_staff=False).
        # / Event author (created_by): request user for staff/logged-in. For an
        # anonymous visitor we get_or_create a user from the step-1 email
        # WITHOUT sending the validation mail; the event stays a moderated
        # proposal.
        user_pour_creation = request.user
        if not est_staff and not request.user.is_authenticated:
            email_proposeur = request.session.get(self._session_key("email_proposeur"))
            if not email_proposeur:
                # Email perdu (session expiree, acces direct) : retour etape 1.
                # / Email lost (expired session, direct access): back to step 1.
                messages.add_message(request, messages.WARNING,
                    _("Merci d'indiquer votre adresse e-mail pour proposer un évènement."))
                return redirect("event-wizard-place")
            user_pour_creation = get_or_create_user(email_proposeur, send_mail=False)
            if user_pour_creation is None:
                # get_or_create_user renvoie None si l'email est marque en erreur.
                # / get_or_create_user returns None if the email is flagged in error.
                messages.add_message(request, messages.ERROR,
                    _("Cette adresse e-mail pose un problème. Merci de nous contacter."))
                return redirect("event-wizard-place")

        # Creation en bloc : tout ou rien. Un doublon (name + datetime,
        # unique_together sur Event) levait un 500 brut ; on le transforme en
        # message de formulaire et on garde les brouillons en session pour
        # que la personne corrige.
        # / All-or-nothing creation. A duplicate (name + datetime,
        # unique_together on Event) used to raise a bare 500; turn it into a
        # form message and keep the drafts in session so the user can fix.
        evenements_crees = []
        try:
            with db_transaction.atomic():
                for draft in drafts:
                    evenements_crees.append(
                        _creer_event_depuis_brouillon(draft, postal_address, user_pour_creation, est_staff)
                    )
        except IntegrityError as erreur_integrite:
            # Trace pour le diagnostic en prod : le message utilisateur suppose
            # un doublon name+datetime, mais toute violation d'integrite passe ici.
            # / Prod diagnostics trace: the user message assumes a name+datetime
            # duplicate, but any integrity violation lands here.
            logger.warning(f"EventWizard finalize IntegrityError : {erreur_integrite}")
            messages.add_message(request, messages.WARNING,
                _("Un évènement avec le même nom existe déjà à cette date. "
                  "Modifiez le nom ou la date avant de valider."))
            return redirect("event-wizard-event")

        # COMMIT reussi : on peut maintenant supprimer les images temporaires
        # des brouillons. Pas avant — un rollback DB n'annule pas une
        # suppression de fichier, et les brouillons conserves en session en
        # auraient encore besoin pour un nouvel essai (cf. _attacher_image_brouillon).
        # / COMMIT succeeded: temp draft images can now be deleted. Not before —
        # a DB rollback does not undo a file deletion, and the session drafts
        # would still need them for a retry.
        from django.core.files.storage import default_storage
        for draft in drafts:
            chemin_temp = draft.get("image")
            if chemin_temp and default_storage.exists(chemin_temp):
                default_storage.delete(chemin_temp)

        request.session.pop(_wizard_drafts_key(self.SESSION_PREFIX), None)
        request.session.pop(self._session_key("postal_address_pk"), None)
        request.session.pop(self._session_key("email_proposeur"), None)
        request.session.modified = True

        nombre = len(evenements_crees)
        if est_staff:
            messages.add_message(request, messages.SUCCESS,
                _("%(n)s évènement(s) créé(s).") % {"n": nombre})
            if nombre == 1:
                ev = evenements_crees[0]
                return redirect(reverse("event-detail", kwargs={"pk": ev.slug or ev.uuid}))
            return redirect("event-list")
        # Public : page de remerciement.
        # / Public: thank-you page.
        return redirect("event-wizard-done")

    @action(detail=False, methods=["POST"], url_path="events/add", url_name="events-add")
    def events_add(self, request):
        garde = self._garde_acces(request)
        if garde:
            return garde
        postal_address, redirection = self._postal_address_ou_redirect(request)
        if redirection:
            return redirection
        return _wizard_events_add_generic(
            request,
            serializer_class=WizardEventSerializer,
            session_prefix=self.SESSION_PREFIX,
            build_draft=self._build_draft,
            inner_context=self._inner_context_events(request, postal_address),
        )

    @action(detail=False, methods=["POST"],
            url_path=r"events/remove/(?P<idx>[0-9]+)", url_name="events-remove")
    def events_remove(self, request, idx=None):
        garde = self._garde_acces(request)
        if garde:
            return garde
        postal_address, redirection = self._postal_address_ou_redirect(request)
        if redirection:
            return redirection
        return _wizard_events_remove_generic(
            request, idx,
            session_prefix=self.SESSION_PREFIX,
            inner_context=self._inner_context_events(request, postal_address),
        )

    # -------------------------------------------------------------------------
    # Intégration recensement Tiers-Lieux (CHANTIER-04). Trois aides HTMX à
    # l'étape 1 : détecter l'instance du proposeur, chercher son lieu dans le
    # recensement national, et l'utiliser pour pré-remplir le nouveau lieu.
    # / Tiers-Lieux directory integration (CHANTIER-04). Three HTMX helpers on
    # step 1: detect the proposer's instance, search the national directory,
    # and use a record to pre-fill the new place.
    # -------------------------------------------------------------------------

    @action(detail=False, methods=["GET"], url_path="check-instance", url_name="check-instance")
    def check_instance(self, request):
        """
        Détecte si l'email saisi correspond à un compte qui administre déjà une
        ou plusieurs instances TiBillet. Renvoie un encart d'invitation
        (non-bloquant) ou une réponse vide. Déclenché en HTMX au blur de l'email.
        / Detect whether the typed email belongs to an account that already
        manages TiBillet instance(s). Returns an invitation partial or empty.

        LOCALISATION : BaseBillet/views.py
        """
        email = (request.GET.get("email_proposeur") or "").strip()
        if not email:
            return HttpResponse("")

        # Rate-limit léger par IP : limite l'énumération email -> instance.
        # Au-delà de 20 requêtes/min/IP, on répond vide (silencieux : aucun
        # indice qu'une limite existe). Clé scopée au tenant courant.
        # / Light per-IP rate-limit to curb email -> instance enumeration:
        # beyond 20 req/min/IP, return empty silently. Tenant-scoped cache key.
        ip = request.META.get("REMOTE_ADDR", "")
        cle_rate = f"check_instance_rate:{connection.tenant.uuid}:{ip}"
        nb_appels = cache.get(cle_rate, 0)
        if nb_appels >= 20:
            return HttpResponse("")
        cache.set(cle_rate, nb_appels + 1, 60)

        # Le modèle User est SHARED : on peut chercher dans le schéma courant.
        # / The User model is SHARED: we can search from the current schema.
        user = TibilletUser.objects.filter(email__iexact=email).first()
        if not user:
            return HttpResponse("")

        # Instances administrées par ce compte (M2M client_admin). On construit
        # pour chacune le lien vers son propre wizard de proposition.
        # / Instances managed by this account; build the link to each wizard.
        instances = []
        for tenant in user.client_admin.all():
            domaine = tenant.get_primary_domain()
            if not domaine:
                continue
            instances.append({
                "name": tenant.name,
                "wizard_url": f"https://{domaine.domain}/event/wizard/place/",
            })

        if not instances:
            return HttpResponse("")

        # Tags que CE tenant fédère automatiquement : à suggérer au proposeur
        # pour que son évènement remonte ici (cf. CHANTIER FEDERATION).
        # / Tags this tenant auto-federates: suggested so the event shows here.
        federation_config = FederationConfiguration.get_solo()
        tags_a_suggerer = [tag.name for tag in federation_config.tags_federation.all()]

        return render(request, "fonctionnel/event_wizard/_instance_trouvee.html", {
            "instances": instances,
            "tags_a_suggerer": tags_a_suggerer,
        })

    @action(detail=False, methods=["GET"], url_path="search-tierslieux", url_name="search-tierslieux")
    def search_tierslieux(self, request):
        """
        Cherche le lieu du proposeur dans le recensement national Tiers-Lieux.
        Déclenché en HTMX (débounce) quand aucune adresse locale ne correspond.
        / Search the proposer's place in the national Tiers-Lieux directory.

        LOCALISATION : BaseBillet/views.py
        """
        from BaseBillet.services.tiers_lieux import rechercher_tiers_lieux

        terme = (request.GET.get("q") or "").strip()
        # On évite les recherches trop courtes (bruit + charge API externe).
        # / Avoid too-short searches (noise + external API load).
        if len(terme) < 3:
            return HttpResponse("")

        fiches = rechercher_tiers_lieux(terme)
        # Le client indique si la liste locale est vide : on n'affiche le message
        # "aucun lieu trouvé" + création de lieu que dans ce cas (sinon réponse
        # vide, car l'utilisateur a déjà des adresses locales).
        # / The client tells whether the local list is empty: we only show the
        # "nothing found" + create CTA then (otherwise empty response).
        local_vide = request.GET.get("local_vide") == "1"
        return render(request, "fonctionnel/event_wizard/_tierslieux_resultats.html", {
            "fiches": fiches,
            "terme": terme,
            "local_vide": local_vide,
        })

    @action(detail=False, methods=["POST"], url_path="use-tierslieux", url_name="use-tierslieux")
    def use_tierslieux(self, request):
        """
        Mémorise la fiche Tiers-Lieux choisie et redirige vers l'étape carte
        pré-remplie. Le proposeur valide ensuite comme une création de lieu
        normale (la carte géocode l'adresse complète et remplit les champs).
        / Store the chosen Tiers-Lieux record and redirect to the pre-filled map
        step. The proposer then validates like a normal place creation.

        LOCALISATION : BaseBillet/views.py
        """
        garde = self._garde_acces(request)
        if garde:
            return garde

        # Email du proposeur (visiteur anonyme) : le bouton « Utiliser ce lieu »
        # est un formulaire DISTINCT du form principal de l'etape 1, donc l'email
        # saisi plus haut n'y est pas poste nativement (le JS l'y injecte). On le
        # memorise en session ICI, exactement comme le fait _wizard_etape_choix_lieu
        # pour le chemin classique. Sans ca, la finalisation ne retrouve pas
        # l'email et renvoie l'utilisateur au debut. Obligatoire pour un anonyme.
        # / Proposer email (anonymous visitor): the "Use this place" button is a
        # SEPARATE form from step 1's main form, so the email above is not POSTed
        # natively (the JS injects it). Store it in session HERE, just like
        # _wizard_etape_choix_lieu does for the classic path. Required for anonymous.
        if not request.user.is_authenticated:
            email_proposeur = (request.POST.get("email_proposeur") or "").strip()
            if not email_proposeur:
                messages.add_message(request, messages.WARNING,
                    _("Merci d'indiquer votre adresse e-mail pour proposer un évènement."))
                return redirect("event-wizard-place")
            request.session[self._session_key("email_proposeur")] = email_proposeur

        from BaseBillet.services.tiers_lieux import valider_coordonnees

        # Champs reçus du POST (fiche choisie OU POST forgé) : on les borne avant
        # de les mettre en session. Le nom alimentera `PostalAddress.name`
        # (max 400) à l'étape carte ; on tronque ici pour ne pas polluer la
        # session avec un input démesuré. / Fields from POST (chosen record OR a
        # forged POST): bound before storing in session. The name feeds
        # `PostalAddress.name` (max 400) at the map step; truncate here.
        nom = (request.POST.get("name") or "").strip()[:200]
        if not nom:
            return redirect("event-wizard-place")
        rue = (request.POST.get("street_address") or "").strip()[:250]
        code_postal = (request.POST.get("postal_code") or "").strip()[:20]
        ville = (request.POST.get("locality") or "").strip()[:120]

        # Adresse complète envoyée au widget carte comme texte de recherche :
        # le widget géocode (Nominatim) et remplit les champs adresse.
        # / Full address fed to the map widget as search text: it geocodes and
        # fills the address fields.
        morceaux = [nom, rue, code_postal, ville]
        adresse_recherche = " ".join(morceau for morceau in morceaux if morceau)

        # L'étape carte exige un nom de lieu en session ; on garde aussi
        # l'adresse de recherche pour pré-remplir le widget.
        # / The map step requires a place name in session; we also keep the
        # search address to pre-fill the widget.
        request.session[self._session_key("new_address_name")] = nom
        request.session[self._session_key("tierslieux_adresse_recherche")] = adresse_recherche

        # GPS + adresse structurée de la fiche (si dispo) : on les garde pour
        # poser le marqueur et remplir les champs DIRECTEMENT à l'étape carte,
        # sans géocodage Nominatim (qui échoue sur les libellés complexes type
        # « MIETE (Maison...) 150 Rue... »). `adresse_recherche` reste le repli
        # (recherche Nominatim) quand la fiche n'a pas de GPS. On valide les
        # coordonnées (un POST forgé pourrait envoyer du texte). Sinon on nettoie.
        # / GPS + structured address from the record (if any): kept to place the
        # marker and fill the fields directly on the map step, no Nominatim
        # geocode. We validate the coords (a forged POST could send text).
        latitude, longitude = valider_coordonnees(
            request.POST.get("latitude"), request.POST.get("longitude"))
        if latitude is not None and longitude is not None:
            request.session[self._session_key("tierslieux_prefill")] = {
                "latitude": latitude,
                "longitude": longitude,
                "street_address": rue,
                "postal_code": code_postal,
                "address_locality": ville,
            }
        else:
            request.session.pop(self._session_key("tierslieux_prefill"), None)

        request.session.pop(self._session_key("postal_address_pk"), None)
        request.session.modified = True
        return redirect("event-wizard-map")

    @action(detail=False, methods=["GET"], url_path="done", url_name="done")
    def done(self, request):
        context = get_context(request)
        context.update({
            "wizard_title": _("Merci !"),
            "wizard_step_label": "",
        })
        return render(request, "fonctionnel/event_wizard/public_done.html",
                      context=context)
