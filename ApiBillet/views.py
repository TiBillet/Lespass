# Create your views here.

import json
import logging
from datetime import datetime, timedelta

import pytz
import stripe
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.db import connection
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import tenant_context
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import permission_classes, action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
# from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from ApiBillet.permissions import TenantAdminApiPermission, TibilletUser, get_apikey_valid
from ApiBillet.serializers import EventSerializer, PriceSerializer, ProductSerializer, ReservationSerializer, \
    ReservationValidator, ConfigurationSerializer, TicketSerializer, \
    OptionsSerializer, ProductCreateSerializer, EmailSerializer
from AuthBillet.models import HumanUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Event, Price, Product, Reservation, Configuration, Ticket, Paiement_stripe, \
    OptionGenerale, Membership
from BaseBillet.tasks import create_ticket_pdf, send_stripe_bank_deposit_to_laboutik
from Customers.models import Client
from TiBillet import settings
from fedow_connect.fedow_api import FedowAPI
from fedow_connect.utils import rsa_decrypt_string, rsa_encrypt_string, get_public_key, data_to_b64
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)


# class DecimalEncoder(json.JSONEncoder):
#     def default(self, o):
#         if isinstance(o, decimal.Decimal):
#             return str(o)
#         return super(DecimalEncoder, self).default(o)


def get_permission_Api_LR_Any_CU_Admin(self: ViewSet):
    # Si c'est list/retrieve -> pour tout le monde
    # Pour le reste, c'est clé API + admin tenant
    if self.action in ['list', 'retrieve']:
        # Tout le monde peut list et retrieve
        permission_classes = [permissions.AllowAny]
    else:
        api_key = get_apikey_valid(self)
        user = api_key.user if api_key else None
        if not user:
            return False

        # user doit être admin dans tenant
        self.request.user = user
        permission_classes = [TenantAdminApiPermission]

    return [permission() for permission in permission_classes]


def get_permission_Api_LR_Admin_CU_Any(self: ViewSet):
    # Si c'est list/retrieve -> clé API + admin tenant
    # Pour le reste, c'est tout le monde
    if self.action in ['list', 'retrieve']:

        api_key = get_apikey_valid(self)
        user = api_key.user if api_key else None
        if not user:
            return Http404
        # user doit être admin dans tenant
        self.request.user = user
        permission_classes = [TenantAdminApiPermission]

    else:
        permission_classes = [permissions.AllowAny]
    return [permission() for permission in permission_classes]


def get_permission_Api_ALL_Admin(self: ViewSet):
    # clé API + admin tenant pour tout
    api_key = get_apikey_valid(self)
    user = api_key.user if api_key else None
    if not user:
        return Http404
    # user doit être admin dans tenant
    self.request.user = user
    permission_classes = [TenantAdminApiPermission]
    return [permission() for permission in permission_classes]


### END GET PERMISSION ###

class TarifBilletViewSet(viewsets.ViewSet):

    def list(self, request):
        queryset = Price.objects.all().order_by('prix')
        serializer = PriceSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request):
        serializer = PriceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        return get_permission_Api_LR_Any_CU_Admin(self)


class ProductViewSet(viewsets.ViewSet):

    def retrieve(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        serializer = ProductSerializer(product, context={'request': request})
        return Response(serializer.data)

    def list(self, request):
        serializer = ProductSerializer(
            Product.objects.filter(
                publish=True,
            ),
            many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request):
        # Le sérializer de création prend des listes pour les options en M2M
        serializer = ProductCreateSerializer(data=request.data)
        if serializer.is_valid():
            product = serializer.save()
            if getattr(serializer, 'img_img', None):
                product.img.save(serializer.img_name, serializer.img_img.fp)

            # Le sérializer de création prend des listes pour les options en M2M
            # On utilise le sérializer de liste pour le retour.
            return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)
        for error in [serializer.errors[error][0] for error in serializer.errors]:
            if error.code == "unique":
                return Response(serializer.errors, status=status.HTTP_409_CONFLICT)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        return get_permission_Api_LR_Any_CU_Admin(self)


class TenantViewSet(viewsets.ViewSet):
    def list(self, request):
        places_serialized_with_uuid = []
        configurations = []
        categories = []
        if 'place' in request.get_full_path():
            categories = [Client.SALLE_SPECTACLE, Client.FESTIVAL]
        if 'artist' in request.get_full_path():
            categories = [Client.ARTISTE]

        for tenant in Client.objects.filter(categorie__in=categories):
            with tenant_context(tenant):
                places_serialized_with_uuid.append({"uuid": f"{tenant.uuid}"})
                configurations.append(Configuration.get_solo())

        places_serialized = ConfigurationSerializer(configurations, context={'request': request}, many=True)

        for key, value in enumerate(places_serialized.data):
            places_serialized_with_uuid[key].update(value)

        return Response(places_serialized_with_uuid)

    def retrieve(self, request, pk=None):
        tenant = get_object_or_404(Client.objects.filter(categorie__in=['S', 'F']), pk=pk)
        with tenant_context(tenant):
            place_serialized = ConfigurationSerializer(Configuration.get_solo(), context={'request': request})
            place_serialized_with_uuid = {'uuid': f"{tenant.uuid}"}
            place_serialized_with_uuid.update(place_serialized.data)
        return Response(place_serialized_with_uuid)

    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [permissions.AllowAny]
            return [permission() for permission in permission_classes]
        else:
            return get_permission_Api_LR_Any_CU_Admin(self)
        # permission_classes = [permissions.AllowAny]


class HereViewSet(viewsets.ViewSet):

    def list(self, request):
        config = Configuration.get_solo()
        place_serialized = ConfigurationSerializer(config, context={'request': request})

        dict_return = {'uuid': f"{connection.tenant.uuid}"}
        dict_return.update(place_serialized.data)

        products_adhesion = Product.objects.filter(
            categorie_article=Product.ADHESION,
            prices__isnull=False,
            publish=True,
        ).distinct()

        if len(products_adhesion) > 0:
            products_serializer = ProductSerializer(products_adhesion, many=True)
            dict_return['membership_products'] = products_serializer.data

        return Response(dict_return)

    def get_permissions(self):
        return get_permission_Api_LR_Any_CU_Admin(self)


class EventsSlugViewSet(viewsets.ViewSet):
    def retrieve(self, request, pk=None):
        queryset = Event.objects.filter(published=True).order_by('-datetime')
        # import ipdb; ipdb.set_trace()
        # try :
        #     date_slug = re.search(r"\d{6}-\d{4}", pk).group()
        #     date = datetime.strptime(date_slug, '%y%m%d-%H%M')
        #     TODO: Gérer les récurences ?
        # except:
        #     return Response(_("Mauvais format de date"), status=status.HTTP_406_NOT_ACCEPTABLE)
        event = get_object_or_404(queryset, slug=pk)
        serializer = EventSerializer(event)
        return Response(serializer.data)

    def get_permissions(self):
        return get_permission_Api_LR_Any_CU_Admin(self)


class EventsViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    def list(self, request):
        events = Event.objects.filter(published=True).order_by('-datetime')
        serializer = EventSerializer(events, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        event = get_object_or_404(Event, pk=pk)
        serializer = EventSerializer(event)
        return Response(serializer.data)

    """
    def create(self, request):
        serializer_create = EventCreateSerializer(data=request.data)
        if serializer_create.is_valid():
            # import ipdb; ipdb.set_trace()
            event: Event = serializer_create.validated_data
            serializer = EventSerializer(event)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        logger.error(f"EventsViewSet : {serializer_create.errors}")
        return Response(serializer_create.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        queryset = Event.objects.all().order_by('-datetime')
        event = get_object_or_404(queryset, pk=pk)
        serializer = EventSerializer(event, data=request.data, partial=True)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        queryset = Event.objects.all().order_by('-datetime')
        event = get_object_or_404(queryset, pk=pk)
        event.delete()
        return Response(('deleted'), status=status.HTTP_200_OK)

    def get_permissions(self):
        return get_permission_Api_LR_Any_CU_Admin(self)
    """


"""
class DetailCashlessCards(viewsets.ViewSet):
    def create(self, request):
        validator = DetailCashlessCardsValidator(data=request.data, context={'request': request})
        if validator.is_valid():
            with schema_context('public'):
                logger.info('Detail valide')
                detailC = validator.save()
                serializer = DetailCashlessCardsSerializer(detailC)
                return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        permission_classes = [RootPermission]
        return [permission() for permission in permission_classes]
"""

"""
class Loadcardsfromdict(viewsets.ViewSet):
    def create(self, request):
        # logger.info(request.data)

        validator = CashlessCardsValidator(data=request.data, many=True)
        if validator.is_valid():
            prems = validator.data[0]
            detail = Detail.objects.get(uuid=prems.get('detail'))
            for carte in validator.data:
                part = carte.get('url').partition('/qr/')
                base_url = f"{part[0]}{part[1]}"
                uuid_qrcode = uuid.UUID(part[2], version=4)
                if detail.uuid == uuid.UUID(carte.get('detail'), version=4) and base_url == detail.base_url:
                    try:
                        carte, created = CarteCashless.objects.get_or_create(
                            tag_id=carte['tag_id'],
                            uuid=uuid_qrcode,
                            number=carte['number'],
                            detail=detail,
                        )
                        logger.info(f"{created}: {carte}")

                    except Exception as e:
                        logger.error(e)
                        Response(_(f"Erreur d'importation {e}"),
                                 status=status.HTTP_406_NOT_ACCEPTABLE)
                else:
                    Response(_(f"Erreur d'importation : Detail ne correspond pas"),
                             status=status.HTTP_406_NOT_ACCEPTABLE)

            return Response("poulpe", status=status.HTTP_200_OK)

        return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        permission_classes = [RootPermission]
        return [permission() for permission in permission_classes]
"""

"""
class ChargeCashless(viewsets.ViewSet):
    def create(self, request):
        configuration = Configuration.get_solo()
        if not configuration.key_cashless or not configuration.server_cashless:
            return Response(_("Serveur cashless non présent dans configuration"),
                            status=status.HTTP_405_METHOD_NOT_ALLOWED)

        try:
            response = requests.request("GET",
                                        f"{configuration.server_cashless}/api/checkcarteqruuid/{request.data.get('uuid')}/",
                                        headers={"Authorization": f"Api-Key {configuration.key_cashless}"},
                                        )

            if response.status_code != 200:
                return Response(_(f"Requete non comprise : {response.status_code}"),
                                status=status.HTTP_405_METHOD_NOT_ALLOWED)
        except Exception as e:
            return Response(_(f"Serveur cashless ne répond pas : {e}"), status=status.HTTP_408_REQUEST_TIMEOUT)

        validator = ChargeCashlessValidator(data=request.data, context={'request': request})
        if validator.is_valid():
            # serializer.save()
            return Response(validator.data, status=status.HTTP_201_CREATED)
        return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]
"""


class ReservationViewset(viewsets.ViewSet):
    def list(self, request):
        queryset = Reservation.objects.all().order_by('-datetime')
        serializer = ReservationSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        queryset = Reservation.objects.all().order_by('-datetime')
        resa = get_object_or_404(queryset, pk=pk)
        serializer = ReservationSerializer(resa)
        return Response(serializer.data)

    def create(self, request):
        logger.info(f"ReservationViewset CREATE : {request.data}")
        validator = ReservationValidator(data=request.data, context={'request': request})
        if validator.is_valid():
            return Response(validator.data, status=status.HTTP_201_CREATED)

        logger.error(f"ReservationViewset CREATE ERROR : {validator.errors}")
        return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        # Tout le monde peut reserver (create), mais seul les admins peuvent lister
        return get_permission_Api_LR_Admin_CU_Any(self)


class OptionTicket(viewsets.ViewSet):
    def list(self, request):
        queryset = OptionGenerale.objects.all()
        serializer = OptionsSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request):
        validator = OptionsSerializer(data=request.data, context={'request': request})
        if validator.is_valid():
            validator.save()
            return Response(validator.data, status=status.HTTP_201_CREATED)
        else:
            for error in [validator.errors[error][0] for error in validator.errors]:
                if error.code == "unique":
                    return Response(validator.errors, status=status.HTTP_409_CONFLICT)
        return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_permissions(self):
        return get_permission_Api_LR_Any_CU_Admin(self)


def borne_temps_4h():
    now = timezone.now()
    jour = now.date()
    tzlocal = pytz.timezone(Configuration.get_solo().fuseau_horaire)
    debut_jour = tzlocal.localize(datetime.combine(jour, datetime.min.time()), is_dst=None) + timedelta(
        hours=4)
    lendemain_quatre_heure = tzlocal.localize(datetime.combine(jour, datetime.max.time()), is_dst=None) + timedelta(
        hours=4)

    if now < debut_jour:
        # Alors on demande au petit matin.
        # Les bornes sont ceux de la veille.
        return debut_jour - timedelta(days=1), debut_jour
    else:
        return debut_jour, lendemain_quatre_heure


@permission_classes([permissions.IsAuthenticated])
class CancelSubscription(APIView):
    def post(self, request):
        user = request.user
        price = request.data.get('uuid_price')

        membership = Membership.objects.get(
            user=user,
            price=price
        )

        if membership.status == Membership.AUTO:
            stripe.api_key = Configuration.get_solo().get_stripe_api()
            stripe.Subscription.delete(
                membership.stripe_id_subscription,
                # stripe_account=config.get_stripe_connect_account(),
            )
            membership.status = Membership.CANCELED
            membership.save()

            # TODO: envoyer un mail de confirmation d'annulation
            return Response(_('Automatic renewal turned off.'), status=status.HTTP_200_OK)

        return Response(_('No automatic renewal on this.'), status=status.HTTP_406_NOT_ACCEPTABLE)


@permission_classes([TenantAdminApiPermission])
class Gauge(APIView):

    # API pour avoir l'état de la jauge (GAUGE in inglishe) et des billets scannés.
    def get(self, request):
        config = Configuration.get_solo()
        debut_jour, lendemain_quatre_heure = borne_temps_4h()
        queryset = Ticket.objects.filter(
            reservation__event__datetime__gte=debut_jour,
            reservation__event__datetime__lte=lendemain_quatre_heure,
            status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED]
        )

        data = {
            "gauge_max": config.jauge_max,
            "all_tickets": queryset.count(),
            "scanned_tickets": queryset.filter(status=Ticket.SCANNED).count()
        }

        return Response(data, status=status.HTTP_200_OK)


class TicketViewset(viewsets.ViewSet):
    # Vérifie la clé API et que l'user de la clé est admin du tenant
    permission_classes = [TenantAdminApiPermission]

    def list(self, request):
        debut_jour, lendemain_quatre_heure = borne_temps_4h()

        queryset = Ticket.objects.filter(
            reservation__event__datetime__gte=debut_jour,
            reservation__event__datetime__lte=lendemain_quatre_heure,
            status__in=["K", "S"]
        )

        serializer = TicketSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        queryset = Ticket.objects.all()
        ticket = get_object_or_404(queryset, pk=pk)
        serializer = TicketSerializer(ticket)
        return Response(serializer.data)


class TicketPdf(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk_uuid):
        ticket = get_object_or_404(Ticket, uuid=pk_uuid)

        VALID_TICKET_FOR_PDF = [Ticket.NOT_SCANNED, Ticket.SCANNED]
        if ticket.status not in VALID_TICKET_FOR_PDF:
            return Response('Invalid ticket', status=status.HTTP_403_FORBIDDEN)

        pdf_binary = create_ticket_pdf(ticket)
        response = HttpResponse(pdf_binary, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{ticket.pdf_filename()}"'
        return response


# On vérifie que les métatada soient les meme dans la DB et chez Stripe.
def metatadata_valid(paiement_stripe_db: Paiement_stripe, checkout_session):
    metadata_stripe_json = checkout_session.metadata
    metadata_stripe = json.loads(str(metadata_stripe_json))

    metadata_db_json = paiement_stripe_db.metadata_stripe
    metadata_db = json.loads(metadata_db_json)

    try:
        assert metadata_stripe == metadata_db
        assert set(metadata_db.keys()) == set(metadata_stripe.keys())
        for key in set(metadata_stripe.keys()):
            assert metadata_db[key] == metadata_stripe[key]
        return True
    except:
        logger.error(f"{timezone.now()} "
                     f"retour_stripe {paiement_stripe_db.uuid} : "
                     f"metadata ne correspondent pas : {metadata_stripe} {metadata_db}")
        return False


# S'execute juste après un retour Webhook ou redirection une fois le paiement stripe effectué.
# ex : BaseBillet.views.EventMVT.stripe_return
def paiment_stripe_validator(request, paiement_stripe: Paiement_stripe):
    """
    A VIRER, On passe maintenant ( get et post webhook ) par Paiement_stripe.update_checkout_status()
    """

    if paiement_stripe.traitement_en_cours:
        logger.info("    paiment_stripe_validator -> traitement en cours")
        data = {
            "msg": _('Payment confirmed. Tickets being generated and sent by email.'),
        }

        if paiement_stripe.reservation:
            serializer = TicketSerializer(paiement_stripe.reservation.tickets.all().exclude(status=Ticket.SCANNED),
                                          many=True)
            data["tickets"] = serializer.data

        return Response(
            data,
            status=status.HTTP_226_IM_USED
        )

    if paiement_stripe.reservation:
        if paiement_stripe.reservation.status == Reservation.PAID_ERROR:
            return Response(
                _("Email sending error, please check the email address."),
                status=status.HTTP_412_PRECONDITION_FAILED
            )

        if paiement_stripe.status == Paiement_stripe.VALID or paiement_stripe.reservation.status == Reservation.VALID:
            logger.info("    paiment_stripe_validator -> Paiement déja validé")
            serializer = TicketSerializer(paiement_stripe.reservation.tickets.filter(status=Ticket.NOT_SCANNED),
                                          many=True, context=request)

            data = {
                "msg": _('Payment confirmed. Tickets sent by email.'),
                "tickets": serializer.data,
            }

            return Response(
                data,
                status=status.HTTP_208_ALREADY_REPORTED
            )

    stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
    config = Configuration.get_solo()

    # stripe.api_key = Configuration.get_solo().get_stripe_api()

    # SI c'est une source depuis INVOICE,
    # L'object vient d'être créé, on vérifie que la facture stripe
    # est payée et on met en VALID.
    if paiement_stripe.source == Paiement_stripe.INVOICE:
        paiement_stripe.traitement_en_cours = True
        invoice = stripe.Invoice.retrieve(
            paiement_stripe.invoice_stripe,
            stripe_account=config.get_stripe_connect_account()
        )

        if invoice.status == 'paid':
            paiement_stripe.status = Paiement_stripe.PAID
            paiement_stripe.last_action = timezone.now()
            paiement_stripe.traitement_en_cours = True
            paiement_stripe.save()

            return Response(
                _('Invoice ok'),
                status=status.HTTP_202_ACCEPTED
            )

        else:
            return Response(
                _(f'Stripe invoice: {invoice.status} - payment: {paiement_stripe.status}'),
                status=status.HTTP_402_PAYMENT_REQUIRED
            )

    # Sinon c'est un paiement stripe checkout pas encore validé
    elif paiement_stripe.status != Paiement_stripe.VALID:
        checkout_session = stripe.checkout.Session.retrieve(
            paiement_stripe.checkout_session_id_stripe,
            stripe_account=config.get_stripe_connect_account()
        )

        paiement_stripe.customer_stripe = checkout_session.customer

        # Vérifie que les metatada soient cohérentes : NTUI
        if metatadata_valid(paiement_stripe, checkout_session):
            logger.info("metadata valide")

            # Paiement foiré ou expiré
            if checkout_session.payment_status == "unpaid":
                paiement_stripe.status = Paiement_stripe.PENDING
                if datetime.now().timestamp() > checkout_session.expires_at:
                    paiement_stripe.status = Paiement_stripe.EXPIRE
                paiement_stripe.save()

                return Response(
                    f'Stripe: {checkout_session.payment_status} - payment: {paiement_stripe.status}',
                    status=status.HTTP_402_PAYMENT_REQUIRED
                )

            elif checkout_session.payment_status == "paid":

                # le .save() lance le process pre_save BaseBillet.models.send_to_cashless
                # qui modifie le status de chaque ligne
                # et envoie les informations au serveur cashless.
                # si validé par le serveur cashless, alors la ligne sera VALID.
                # Si toute les lignes sont VALID, le paiement_stripe sera aussi VALID
                # grace au post_save BaseBillet.models.check_status_stripe

                paiement_stripe.status = Paiement_stripe.PAID
                paiement_stripe.last_action = timezone.now()
                paiement_stripe.traitement_en_cours = True

                # Dans le cas d'un nouvel abonnement
                # On va chercher le numéro de l'abonnement stripe
                # Et sa facture
                if checkout_session.mode == 'subscription':
                    if bool(checkout_session.subscription):
                        paiement_stripe.subscription = checkout_session.subscription
                        subscription = stripe.Subscription.retrieve(
                            checkout_session.subscription,
                            stripe_account=config.get_stripe_connect_account()
                        )
                        paiement_stripe.invoice_stripe = subscription.latest_invoice

                paiement_stripe.save()
                logger.info("*" * 30)
                logger.info(
                    f"{datetime.now()} - paiment_stripe_validator - checkout_session.payment_status : {checkout_session.payment_status}")
                logger.info(
                    f"{datetime.now()} - paiment_stripe_validator - paiement_stripe.save() {paiement_stripe.status}")
                logger.info("*" * 30)

            else:
                paiement_stripe.status = Paiement_stripe.CANCELED
                paiement_stripe.save()
        else:
            return Response(_(f'Meta error'), status=status.HTTP_406_NOT_ACCEPTABLE)

    # on vérifie le changement de status
    paiement_stripe.refresh_from_db()

    # Derniere action : on crée et envoie les billets si besoin
    if paiement_stripe.source == Paiement_stripe.API_BILLETTERIE:
        if paiement_stripe.reservation:
            if paiement_stripe.reservation.status == Reservation.VALID:
                serializer = TicketSerializer(paiement_stripe.reservation.tickets.filter(status=Ticket.NOT_SCANNED),
                                              many=True, context=request)
                # import ipdb; ipdb.set_trace()
                data = {
                    "msg": _('Payment confirmed. Tickets sent by email.'),
                    "tickets": serializer.data,
                }
                return Response(
                    data,
                    status=status.HTTP_208_ALREADY_REPORTED
                )
        if paiement_stripe.status == Paiement_stripe.VALID:
            return Response(
                _('Payment confirmed.'),
                status=status.HTTP_208_ALREADY_REPORTED
            )

        elif paiement_stripe.status == Paiement_stripe.PAID:
            logger.info(f"Paiement_stripe.API_BILLETTERIE  : {paiement_stripe.status}")
            data = {
                "msg": _('Payment confirmed. Tickets being generated and sent by email.'),
            }
            if paiement_stripe.reservation:
                serializer = TicketSerializer(paiement_stripe.reservation.tickets.all().exclude(status=Ticket.SCANNED),
                                              many=True)
                data['tickets'] = serializer.data
            return Response(
                data,
                status=status.HTTP_202_ACCEPTED
            )

    raise Http404(f'{paiement_stripe.status}')


"""
# Déplacé dans Basebillet Tenant

@permission_classes([permissions.AllowAny])
class Onboard_stripe_return(APIView):
    def get(self, request, id_acc_connect):
        # La clé du compte principal stripe connect
        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        # Récupération des info lié au lieu via sont id account connect
        info_stripe = stripe.Account.retrieve(id_acc_connect)
        details_submitted = info_stripe.details_submitted

        if details_submitted:
            import ipdb; ipdb.set_trace()


            futur_conf = WaitingConfiguration.objects.get(stripe_connect_account=id_acc_connect)
            logger.info(f"details_submitted : {details_submitted}")
            # create_tenant(futur_conf.pk)
            return Response(f"ok", status=status.HTTP_200_OK)
        else:
            # Si les infos stripe ne sont pas complète, on renvoie l'url onboard pour les completer
            return Response(f"{create_account_link_for_onboard()}", status=status.HTTP_206_PARTIAL_CONTENT)
"""


@permission_classes([permissions.AllowAny])
class Get_user_pub_pem(APIView):
    def post(self, request):
        # Si laboutik est déja configuré sur ce tenant, on envoie bouler
        config = Configuration.get_solo()
        if config.server_cashless or config.key_cashless:
            if not settings.DEBUG:
                logger.error("cashless already config for this tenant")
                return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

        # un simple return de pub key
        # Utile pour pinger et faire la première co du cahsless laboutik
        # Il faut que l'admin dans le cashless soit le même que l'admin de ce tenant
        User = get_user_model()
        user: TibilletUser = get_object_or_404(User, email=f"{request.data['email']}")
        if not user.is_tenant_admin(connection.tenant):
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        data = {
            'public_pem': f"{user.get_public_pem()}",
        }
        return Response(data=data, status=status.HTTP_200_OK)


@permission_classes([permissions.AllowAny])
class Onboard_laboutik(APIView):
    def post(self, request):
        # Si laboutik est déja configuré sur ce tenant, on envoi bouler
        config = Configuration.get_solo()
        if config.server_cashless or config.key_cashless:
            if not settings.DEBUG:
                return Response(status=status.HTTP_409_CONFLICT)

        # On va demander une liaison cashless <-> place a Fedow :
        email_admin = f"{request.data['email']}"
        user_admin: TibilletUser = connection.tenant.user_admin.get(email=email_admin)
        logger.info(f"Création de la place Fedow avec admin : {user_admin}")
        fedowAPI = FedowAPI(admin=user_admin)

        # Ensure wallet exist for fedow api call
        fedowAPI.wallet.get_or_create_wallet(user_admin)
        # Get the temp key for the laboutik onboard
        temp_key = fedowAPI.place.link_cashless_to_place(admin=user_admin)
        fconfig = fedowAPI.fedow_config
        json_key_to_cashless = {
            "domain": fconfig.fedow_domain(),
            "uuid": f"{fconfig.fedow_place_uuid}",
            "temp_key": temp_key,
        }

        # Onboard du cashless, première connection à l'install !
        config.server_cashless = f"{request.data['server_cashless']}"
        config.laboutik_public_pem = f"{request.data['pum_pem_cashless']}"
        logger.info(f'Onboard Laboutik depuis : {config.server_cashless} pour le tenant : {connection.tenant}')

        # Un premier hello world a été fait précédemment pour envoyer la clé publique du premier admin de ce tenant
        # On tente de déchiffrer la clé api avec la clé privée de l'admin
        cypher_key_cashless = f"{request.data['key_cashless']}"
        config.key_cashless = rsa_decrypt_string(utf8_enc_string=cypher_key_cashless,
                                                 private_key=user_admin.get_private_key())

        logger.info("Serveur LaBoutik onboarded !")

        # La clé rsa ne peux chiffrer que des petites clés,
        # on chiffre alors avec fernet ET rsa (on fait comme TLS!)
        rand_key = Fernet.generate_key()
        cypher_rand_key = rsa_encrypt_string(utf8_string=rand_key.decode('utf8'),
                                             public_key=get_public_key(config.laboutik_public_pem))

        encryptor = Fernet(rand_key)
        cypher_json_key_to_cashless = encryptor.encrypt(data_to_b64(json_key_to_cashless)).decode('utf8')


        adress = f"{config.postal_address.street_address}" if config.postal_address else ""
        city = f"{config.postal_address.address_locality}" if config.postal_address else ""
        country = f"{config.postal_address.address_country}" if config.postal_address else ""
        postal_code = f"{config.postal_address.postal_code}" if config.postal_address else ""

        data = {
            'cypher_rand_key': cypher_rand_key,
            'cypher_json_key_to_cashless': cypher_json_key_to_cashless,
            "organisation_name": config.organisation,
            "adress": adress,
            "city": city,
            "country": country,
            "postal_code": postal_code,
            "tva_number": config.tva_number,
            "siren": config.siren,
            "phone": config.phone,
            "site_web": config.site_web,
        }
        # Tout s'est bien passé, on sauvegarde la configuration
        config.save()
        return Response(data=data, status=status.HTTP_200_OK)


# @permission_classes([permissions.AllowAny])
# class Onboard(APIView):
#     def get(self, request):
#         return Response(f"{create_account_link_for_onboard()}", status=status.HTTP_202_ACCEPTED)


# api check wallet
class Wallet(viewsets.ViewSet):

    @action(detail=False, methods=['POST'], permission_classes=[TenantAdminApiPermission])
    def get_stripe_checkout_with_email(self, request):
        # Création d'un lien de paiement pour une recharge Stripe.
        # Peut être réalisée par n'importe qui. Valide du moment qu'il y a paiement.
        serializer = EmailSerializer(data=request.data)
        if not serializer.is_valid():
            # success_url = request.data.get('success_url')
            # cancel_url = request.data.get('cancel_url')
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        user: "HumanUser" = get_or_create_user(email)
        if not user:
            return Response(_(f"Invalid user"), status=status.HTTP_406_NOT_ACCEPTABLE)

        fedowAPI = FedowAPI()
        stripe_checkout_url = fedowAPI.wallet.get_federated_token_refill_checkout(user)
        if stripe_checkout_url:
            # Envoi du lien
            data = {
                "stripe_checkout_url": f"{stripe_checkout_url}"
            }
            return Response(data=data, status=status.HTTP_201_CREATED)

        return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)


@permission_classes([permissions.AllowAny])
class Webhook_stripe(APIView):

    def post(self, request):
        payload = request.data
        logger.info(f" ")
        # logger.info(f"Webhook_stripe --> {payload}")
        logger.info(f"Webhook_stripe --> {payload.get('type')} - id : {payload.get('id')}")


        # c'est une requete depuis un webhook stripe
        if payload.get('type') == "checkout.session.completed":
            if "return_refill_wallet" in payload["data"]["object"]["success_url"]:
                return Response(f"Ce checkout est pour fedow.", status=status.HTTP_205_RESET_CONTENT)

            if not payload["data"]["object"]["metadata"].get('tenant'):
                logger.error(f"Webhook_stripe Pas de tenant dans metadata --> {payload}")
                return Response(f"Pas de tenant dans metadata, pas pour nous ? {payload}",
                                status=status.HTTP_204_NO_CONTENT)

            tenant_uuid_in_metadata = payload["data"]["object"]["metadata"]["tenant"]
            if tenant_uuid_in_metadata == "payment_link" :
                return Response(f"Payment link ? Pas besoin de traitement.",status=status.HTTP_204_NO_CONTENT)

            tenant = Client.objects.get(uuid=tenant_uuid_in_metadata)
            with tenant_context(tenant):
                paiement_stripe = Paiement_stripe.objects.get(
                    checkout_session_id_stripe=payload['data']['object']['id'])
                logger.info(
                    f"Webhook_stripe --> {payload.get('type')} - id : {payload.get('id')} - with tenant_context({tenant}) -> paiment_stripe_validator")

                if paiement_stripe.traitement_en_cours:
                    return Response(f"Traitement en cours : {paiement_stripe.get_status_display()}", status=status.HTTP_208_ALREADY_REPORTED)

                paiement_stripe.update_checkout_status()
                paiement_stripe.refresh_from_db()
                return Response(f"Traité par /api/Webhook_stripe : {paiement_stripe.get_status_display()}", status=status.HTTP_200_OK)


        elif payload.get('type') == "transfer.created":

            #TODO: tout mettre dans un celery :
            stripe_connect_account = payload["data"]["object"]["destination"]
            created = datetime.fromtimestamp(payload["data"]["object"]["created"])
            transfer_id = payload["data"]["object"]["id"]

            # Vérification de la requete chez Stripe
            stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
            transfer = stripe.Transfer.retrieve(transfer_id)
            if stripe_connect_account != transfer.destination:
                raise ValueError("Transfert stripe illegal")
            amount = transfer.amount

            # On est sur le tenant root. Il faut chercher le tenant correspondant.
            for tenant in Client.objects.all().exclude(categorie=Client.ROOT):
                with tenant_context(tenant): # Comment faire sans itérer dans tout les tenant ?
                    config = Configuration.get_solo()
                    tenant_stripe_connect_account = config.get_stripe_connect_account()
                    if tenant_stripe_connect_account:
                        if tenant_stripe_connect_account == stripe_connect_account:

                            # Le paiement a déja été pris en compte
                            if Paiement_stripe.objects.filter(payment_intent_id=transfer_id).exists():
                                return Response(f"Déja pris en compte", status=status.HTTP_208_ALREADY_REPORTED)

                            try:
                                # Envoi à Fedow
                                fedowAPI = FedowAPI()
                                serializer_transaction = fedowAPI.wallet.global_asset_bank_stripe_deposit(payload)
                                hash = serializer_transaction.fedow_transaction.hash
                                uuid = serializer_transaction.fedow_transaction.uuid
                                payload['fedow_transaction_hash'] = str(hash)
                                payload['fedow_transaction_uuid'] = str(uuid)

                                # Envoie à Laboutik
                                send_stripe_bank_deposit_to_laboutik.delay(payload)
                                # logger.info(f"Envoyé à Laboutik. Création de la ligne comptable :")
                                # logger.info(f"{payload}")

                                # Création du paiement stripe
                                pstripe = Paiement_stripe.objects.create(
                                    detail=_("Versement de monnaie globale"),
                                    payment_intent_id=transfer_id,
                                    metadata_stripe=json.dumps(payload),
                                    order_date=created,
                                    status=Paiement_stripe.VALID,
                                    traitement_en_cours=True,
                                    source=Paiement_stripe.TRANSFERT,
                                    source_traitement=Paiement_stripe.WEBHOOK,
                                )
                                pstripe.fedow_transactions.add(serializer_transaction.fedow_transaction)
                                logger.info(
                                    f'transfer.created OK : Paiement_stripe.objects.created : {pstripe.uuid_8} : hash fedow {hash}')
                                return Response(
                                    f'transfer.created OK : Paiement_stripe.objects.created : {pstripe.uuid_8} : hash fedow {hash}',
                                    status=status.HTTP_201_CREATED)
                            except Exception as e:
                                logger.error(f"Error processing Stripe transfer for tenant {tenant}: {str(e)}")
                                raise e
            # send_stripe_transfert_to_laboutik(payload)


        # Prélèvement automatique d'un abonnement :
        # elif payload.get('type') == "customer.subscription.updated":
        #     # on récupère le don dans le paiement récurent si besoin
        #     logger.info(f"Webhook_stripe customer.subscription.updated : {payload['data']['object']['id']}")
        #     logger.info(f"")
        #     logger.info(f"")
        #     logger.info(f"{payload}")
        #     logger.info(f"")
        #     logger.info(f"")
        #
        # elif payload.get('type') == "invoice.paid":
        #     # logger.info(f" ")
        #     # logger.info(payload)
        #     # logger.info(f" ")
        #
        #     logger.info(f"Webhook_stripe invoice.paid : {payload}")
        #     payload_object = payload['data']['object']
        #     billing_reason = payload_object.get('billing_reason')
        #
        #     # C'est un renouvellement d'abonnement
        #     if billing_reason == 'subscription_cycle' \
        #             and payload_object.get('paid'):
        #
        #         product_sold_stripe_id = None
        #         for line in payload_object['lines']['data']:
        #             product_sold_stripe_id = line['price']['product']
        #             break
        #
        #         # On va chercher le tenant de l'abonnement grâce à l'id du product stripe
        #         # dans la requete POST
        #         with schema_context('public'):
        #             try:
        #                 product_from_public_tenant = ProductDirectory.objects.get(
        #                     product_sold_stripe_id=product_sold_stripe_id,
        #                 )
        #                 place = product_from_public_tenant.place
        #             except ProductDirectory.DoesNotExist:
        #                 logger.error(
        #                     f"Webhook_stripe invoice.paid DoesNotExist : product_sold_stripe_id {product_sold_stripe_id}, serveur de test ?")
        #                 return Response(_('ProductDirectory does not exist, test server?'),
        #                                 status=status.HTTP_204_NO_CONTENT)
        #
        #         # On a le tenant ( place ), on va chercher l'abonnement
        #         with tenant_context(place):
        #             invoice = payload_object['id']
        #             try:
        #                 membership = Membership.objects.get(
        #                     stripe_id_subscription=payload_object['subscription']
        #                 )
        #                 last_stripe_invoice = membership.last_stripe_invoice
        #
        #                 # Même adhésion, mais facture différente :
        #                 # C'est alors un renouvellement automatique.
        #                 if invoice != last_stripe_invoice:
        #                     logger.info((f'    nouvelle facture arrivée : {invoice}'))
        #                     paiement_stripe = new_entry_from_stripe_invoice(membership.user, invoice)
        #
        #                     return paiment_stripe_validator(request, paiement_stripe)
        #
        #                 else:
        #                     logger.info((f'    facture déja créée et comptabilisée : {invoice}'))
        #
        #             except Membership.DoesNotExist:
        #                 logger.info((f'    Nouvelle adhésion, facture pas encore comptabilisée : {invoice}'))
        #             except Exception:
        #                 logger.error((f'    erreur dans Webhook_stripe customer.subscription.updated : {Exception}'))
        #                 raise Exception

        # Réponse pour l'api stripe qui envoie des webhook pour tout autre que la validation de paiement.
        # Si on renvoie une erreur, ils suppriment le webhook de leur côté.
        return Response('Webhook stripe bien reçu, mais aucune action lancée.', status=status.HTTP_207_MULTI_STATUS)

    # def get(self, request, uuid_paiement):
    #     logger.info("*" * 30)
    #     logger.info(f"{datetime.now()} - Webhook_stripe GET : {uuid_paiement}")
    #     logger.info("*" * 30)
    #
    #     paiement_stripe = get_object_or_404(Paiement_stripe,
    #                                         uuid=uuid_paiement)
    #     return paiment_stripe_validator(request, paiement_stripe)
