from django.http import HttpResponse, HttpRequest
from django.shortcuts import render, redirect,  get_object_or_404

from django.template.response import TemplateResponse

from django.views.decorators.http import require_GET

from django.utils.encoding import force_str, force_bytes
from django.utils.http import urlsafe_base64_encode

from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from ApiBillet.views import request_for_data_cashless
from AuthBillet.serializers import MeSerializer
from AuthBillet.utils import get_or_create_user
from AuthBillet.views import activate

from BaseBillet.models import Configuration, Ticket, OptionGenerale, Product, Event

from django.contrib.auth import logout, login
from django.contrib import messages

import segno
import barcode
import uuid

from io import BytesIO

def encode_uid(pk):
    return force_str(urlsafe_base64_encode(force_bytes(pk)))

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

def deconnexion(request):
    logout(request)
    messages.add_message(request, messages.SUCCESS, "Déconnexion")
    return redirect('home')

def connexion(request):
    if request.method == 'POST':
        try:
            email = request.POST.get('login-email')
            # Création de l'user et envoie du mail de validation
            user = get_or_create_user(email=email, send_mail=True)

            if user.is_authenticated == True:
                login(request, user)
                messages.add_message(request, messages.SUCCESS, "Connexion ok.")
                return redirect('home')

            print(f"user = {user.__dict__}")
            if user.is_authenticated == False:
                messages.add_message(request, messages.SUCCESS, "Pour acceder à votre espace et réservations, merci de valider\n votre adresse email. Pensez à regarder dans les spams !")

        except Exception as error:
            messages.add_message(request, messages.WARNING, str(error))

        return redirect('home')

# TODO: authentifier le user/email (si-dessous, ne fonctionne pas)
def emailconfirmation(request, uuid, token):
    activate(request, uuid, token)
    return redirect('home')

def showModalMessageInEnterPage(request):
    return TemplateResponse(request, 'htmx/components/modal_message.html', context={})


@require_GET
def home(request):
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
