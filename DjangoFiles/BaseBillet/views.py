from django.http import HttpResponseRedirect, HttpResponse, HttpRequest
from django.shortcuts import render
from django.template.response import TemplateResponse

from django.views.decorators.http import require_GET

from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from BaseBillet.models import Configuration, Ticket, OptionGenerale, Product, Event

import segno
import barcode
import uuid

from io import BytesIO

from BaseBillet.tasks import encode_uid


class index(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return HttpResponseRedirect("https://tibillet.org")

        # configuration = Configuration.get_solo()
        # if not configuration.activer_billetterie:
        #     return HttpResponseRedirect('https://www.tibillet.re')
        #
        #
        # context = {
        #     'configuration': configuration,
        #     'events': Event.objects.filter(datetime__gt=datetime.now()),
        #     'categorie_billet': Product.BILLET,
        # }
        #
        # if configuration.template_billetterie :
        #     return render(request, f'{configuration.template_billetterie}/lieu.html', context=context)
        # else :
        #     return render(request, 'arnaud_mvc/lieu.html', context=context)


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


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    if request.htmx:
        base_template = "htmx/partial.html"
    else:
        base_template = "htmx/base.html"

    host = "http://" + request.get_host()
    if request.is_secure():
        host = "https://" + request.get_host()

    # import ipdb; ipdb.set_trace()
    img = '/media/' + str(Configuration.get_solo().img)

    context = {
        "base_template": base_template,
        "host": host,
        "url_name": request.resolver_match.url_name,
        "header": {
            "img": img,
            "organisation": Configuration.get_solo().organisation,
            "short_description": Configuration.get_solo().short_description,
            "long_description": Configuration.get_solo().long_description
        },
        "tenant": Configuration.get_solo().organisation,
        "events": Event.objects.all(),
        "user": request.user,
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
        },
    }
    return render(request, "htmx/views/home.html", context=context)

@require_GET
def event(request: HttpRequest, slug) -> HttpResponse:
    if request.htmx:
        base_template = "htmx/partial.html"
    else:
        base_template = "htmx/base.html"

    host = "http://" + request.get_host()
    if request.is_secure():
        host = "https://" + request.get_host()

    event = Event.objects.get(slug=slug)
    
    context = {
        "base_template": base_template,
        "host": host,
        "url_name": request.resolver_match.url_name,
        "header": {
            "img": event.img_variations()['fhd'],
            "organisation": event.name,
            "short_description": event.short_description,
            "long_description": event.long_description
        },
        "tenant": Configuration.get_solo().organisation,
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
            "config": Configuration.get_solo(),
            "membership": Product.objects.get(uuid=uuid),
        }

        return render(request, "htmx/forms/membership_form.html", context=context)


@require_GET
def memberships(request: HttpRequest) -> HttpResponse:
    if request.htmx:
        base_template = "htmx/partial.html"
    else:
        base_template = "htmx/base.html"

    host = "http://" + request.get_host()
    if request.is_secure():
        host = "https://" + request.get_host()

    context = {
        "base_template": base_template,
        "host": host,
        "url_name": request.resolver_match.url_name,
        "config": Configuration.get_solo(),
        "memberships": Product.objects.filter(categorie_article="A"),
    }

    return render(request, "htmx/views/memberships.html", context=context)
