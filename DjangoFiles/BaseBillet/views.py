from django.conf import settings
from django.http import HttpResponseRedirect, HttpResponse, HttpRequest
from django.shortcuts import render
from django.template.response import TemplateResponse

from django.views.decorators.http import require_GET

from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from ApiBillet.views import request_for_data_cashless
from AuthBillet.serializers import MeSerializer
from AuthBillet.utils import get_or_create_user

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator

from BaseBillet.models import Configuration, Ticket, OptionGenerale, Product, Event

import segno
import barcode
import uuid
import logging

from io import BytesIO

from BaseBillet.tasks import encode_uid

# dev test
import time

globalContext = None


def get_context(request):
    config = Configuration.get_solo()
    base_template = "htmx/partial.html" if request.htmx else "htmx/base.html"

    host = f"https://{request.get_host()}" if request.is_secure() else f"http://{request.get_host()}"
    print(f"-> host = {host}")

    serialized_user = MeSerializer(request.user).data if request.user.is_authenticated else None
    # TODO: le faire dans le serializer
    if config.server_cashless and config.key_cashless and request.user.is_authenticated:
        serialized_user['cashless'] = request_for_data_cashless(request.user)

    context = {
        "messageToShowInEnterPage": None,
        "base_template": base_template,
        "host": host,
        "url_name": request.resolver_match.url_name,
        "configuration": config,
        "user": request.user,
        "profile": serialized_user,
        "tenant": config.organisation,
        "header": {
            "img": config.img.fhd.url,
            "title": config.organisation,
            "short_description": config.short_description,
            "long_description": config.long_description
        },
        "events": Event.objects.all(),
        "fake_event": {
            "uuid": "fakeEven-ece7-4b30-aa15-b4ec444a6a73",
            "name": "Nom de l'évènement",
            "short_description": "Cliquer sur le bouton si-dessous.",
            "long_description": None,
            "categorie": "CARDE_CREATE",
            "tag": [],
            "products": [],
            "options_radio": [],
            "options_checkbox": [],
            "img_variations": {"crop": "/media/images/1080_v39ZV53.crop"},
            "artists": [],
        }
    }
    return context


def decode_uid(pk):
    return force_str(urlsafe_base64_decode(pk))


# class index(APIView):
#   permission_classes = [AllowAny]
#
#   def get(self, request):
#     return HttpResponseRedirect("https://tibillet.org")


class Ticket_html_view(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk_uuid):
        ticket = get_object_or_404(Ticket, uuid=pk_uuid)
        qr = segno.make(f"{ticket.uuid}", micro=False)

        buffer_svg = BytesIO()
        qr.save(buffer_svg, kind="svg", scale=8)

        CODE128 = barcode.get_barcode_class("code128")
        buffer_barcode_SVG = BytesIO()
        bar_secret = encode_uid(f"{ticket.uuid}".split("-")[4])

        bar = CODE128(f"{bar_secret}")
        options = {
            "module_height": 30,
            "module_width": 0.6,
            "font_size": 10,
        }
        bar.write(buffer_barcode_SVG, options=options)

        context = {
            "ticket": ticket,
            "config": Configuration.get_solo(),
            "img_svg": buffer_svg.getvalue().decode("utf-8"),
            # 'img_svg64': base64.b64encode(buffer_svg.getvalue()).decode('utf-8'),
            "bar_svg": buffer_barcode_SVG.getvalue().decode("utf-8"),
            # 'bar_svg64': base64.b64encode(buffer_barcode_SVG.getvalue()).decode('utf-8'),
        }

        return render(request, "ticket/ticket.html", context=context)
        # return render(request, 'ticket/qrtest.html', context=context)


def create_product(request):
    if request.method == "POST":
        print(f"reception du formulaire {request.POST}")

        # Erreur :
        errors = [
            {"id": "tibillet-product-name", "msg": "erreur de validation"},
        ]
        context = {"errors": errors}
        return TemplateResponse(
            request, "htmx/subscription/modal.html", context=context
        )

    options = OptionGenerale.objects.all()
    options_list = []
    for ele in options:
        options_list.append({"value": str(ele.uuid), "name": ele.name})

    categorie_list = [
        {"value": "B", "name": "Billet payant"},
        {"value": "P", "name": "Pack d'objets"},
        {"value": "R", "name": "Recharge cashless"},
        {"value": "S", "name": "Recharge suspendue"},
        {"value": "T", "name": "Vetement"},
        {"value": "M", "name": "Merchandasing"},
        {"value": "A", "name": "Abonnement et/ou adhésion associative"},
        {"value": "D", "name": "Don"},
        {"value": "F", "name": "Reservation gratuite"},
        {"value": "V", "name": "Nécessite une validation manuelle"},
    ]

    context = {
        "uuid": uuid,
        "options_list": options_list,
        "categorie_list": categorie_list,
        "Product": Product,
    }
    return TemplateResponse(request, "htmx/views/create_product.html", context=context)


def test_jinja(request):
    context = {
        "list": [1, 2, 3, 4, 5, 6],
        "var1": "",
        "var2": "",
        "var3": "",
        "var4": "hello",
    }
    return TemplateResponse(request, "htmx/views/test_jinja.html", context=context)


def login(request):
    if request.method == 'POST':
        try:
            email = request.POST.get('login-email')
            # Création de l'user et envoie du mail de validation
            user = get_or_create_user(email=email, send_mail=True)

            '''
            # login auto en DEBUG
            if settings.DEBUG:
                request.login(user)
                return HttpResponseRedirect('/')
            '''

            # Sinon, en prod, on renvoi vers le message de vérification de mail
            context = {
                "modal_message": {
                    "title": "Validation",
                    "content": "Pour acceder à votre espace et réservations, merci de valider\n votre adresse email. Pensez à regarder dans les spams !",
                    "type": 'success'
                }
            }
            return TemplateResponse(request, 'htmx/components/modal_message.html', context=context)

        except Exception as error:
            context = {
                "modal_message": {
                    "title": "Erreur",
                    "content": str(error),
                    "type": 'danger'
                }
            }
            return TemplateResponse(request, 'htmx/components/modal_message.html', context=context)


# TODO: authentifier le user/email (si-dessous, ne fonctionne pas)
def emailconfirmation(request, uuid, token):
    global globalContext
    context = get_context(request)
    User = get_user_model()
    try:
        user = User.objects.get(pk=decode_uid(uuid))
        print(f"user = {user}")
    except User.DoesNotExist:
        context['messageToShowInEnterPage'] = {
            "title": "Attention",
            "content": 'Token non valide. DoesNotExist',
            "type": 'warning'
        }
        globalContext = context
        return render(request, "htmx/views/home.html", context=context)

    except Exception as e:
        logging.getLogger(__name__).error(e)
        raise e

    if user.email_error:
        context['messageToShowInEnterPage'] = {
            "title": "Attention",
            "content": 'Mail non valide',
            "type": 'warning'
        }
        globalContext = context
        return render(request, "htmx/views/home.html", context=context)

    PR = PasswordResetTokenGenerator()
    is_token_valid = PR.check_token(user, token)
    if is_token_valid:
        user.is_active = True
        # si besoin ?
        context['refresh_token'] = RefreshToken.for_user(user)
        print(f"-> user.is_authenticated = {user.is_authenticated}")
        user.save()
        context['user'] = request.user
        # import ipdb; ipdb.set_trace()
        context['messageToShowInEnterPage'] = {
            "title": "Information",
            "content": 'Utilisateur activé / connecté !',
            "type": 'success'
        }
        globalContext = context
        return render(request, "htmx/views/home.html", context=context)

    else:
        context['messageToShowInEnterPage'] = {
            "title": "Attention",
            "content": 'Token non valide',
            "type": 'warning'
        }
        globalContext = context
        return render(request, "htmx/views/home.html", context=context)


def showModalMessageInEnterPage(request):
    global globalContext
    context = {
        "modal_message": globalContext['messageToShowInEnterPage']
    }
    globalContext['messageToShowInEnterPage'] = None
    return TemplateResponse(request, 'htmx/components/modal_message.html', context=context)


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    userTest = get_user_model()
    global globalContext
    # import ipdb; ipdb.set_trace()
    if globalContext != None:
        print("messageToShowInEnterPage = {globalContext['messageToShowInEnterPage']}")
    context = get_context(request)
    return render(request, "htmx/views/home.html", context=context)


@require_GET
def event(request: HttpRequest, slug) -> HttpResponse:
    serialized_user = MeSerializer(request.user).data if request.user.is_authenticated else None
    config = Configuration.get_solo()
    base_template = "htmx/partial.html" if request.htmx else "htmx/base.html"

    host = "http://" + request.get_host()
    if request.is_secure():
        host = "https://" + request.get_host()

    event = Event.objects.get(slug=slug)

    context = {
        "base_template": base_template,
        "host": host,
        "url_name": request.resolver_match.url_name,
        "tenant": config.organisation,
        "profile": serialized_user,
        "header": {
            "img": f"/media/{event.img}",
            "title": event.name,
            "short_description": event.short_description,
            "long_description": event.long_description
        },
        "slug": slug,
        "event": event,
        "user": request.user,
        "uuid": uuid
    }
    return render(request, "htmx/views/event.html", context=context)


class membership_form(APIView):
    permission_classes = [AllowAny]

    def get(self, request, uuid):
        print(f"uuid = {uuid}")

        host = "http://" + request.get_host()
        if request.is_secure():
            host = "https://" + request.get_host()

        context = {
            "host": host,
            "url_name": request.resolver_match.url_name,
            "membership": Product.objects.get(uuid=uuid)
        }

        return render(request, "htmx/forms/membership_form.html", context=context)


@require_GET
def memberships(request: HttpRequest) -> HttpResponse:
    config = Configuration.get_solo()
    base_template = "htmx/partial.html" if request.htmx else "htmx/base.html"

    host = "http://" + request.get_host()
    if request.is_secure():
        host = "https://" + request.get_host()

    img = '/media/' + str(Configuration.get_solo().img)
    context = {
        "base_template": base_template,
        "host": host,
        "url_name": request.resolver_match.url_name,
        "tenant": config.organisation,
        "header": {
            "img": config.img.fhd.url,
            "title": config.organisation,
            "short_description": config.short_description,
            "long_description": config.long_description
        },
        "memberships": Product.objects.filter(categorie_article="A"),
    }

    return render(request, "htmx/views/memberships.html", context=context)
