from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render
from django.template.response import TemplateResponse

from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from BaseBillet.models import Configuration, Ticket, OptionGenerale

import segno
import barcode

from io import BytesIO

from BaseBillet.tasks import encode_uid


class index(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return HttpResponseRedirect('https://tibillet.org')

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




class event(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        return HttpResponseRedirect('https://www.tibillet.re')
    #     configuration = Configuration.get_solo()
    #     event = get_object_or_404(Event, slug=slug)
    #
    #     context = {
    #         'configuration': configuration,
    #         'categorie_billet': Product.BILLET,
    #         'event': event,
    #     }
    #
    #     if configuration.template_billetterie :
    #         return render(request, f'{configuration.template_billetterie}/event.html', context=context)
    #     else :
    #         return render(request, 'arnaud_mvc/event.html', context=context)




class Ticket_html_view(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk_uuid):
        ticket = get_object_or_404(Ticket, uuid=pk_uuid)
        qr = segno.make(f"{ticket.uuid}", micro=False)

        buffer_svg = BytesIO()
        qr.save(buffer_svg, kind='svg', scale=8)

        CODE128 = barcode.get_barcode_class('code128')
        buffer_barcode_SVG = BytesIO()
        bar_secret = encode_uid(f"{ticket.uuid}".split('-')[4])

        bar = CODE128(f"{bar_secret}")
        options = {
            'module_height': 30,
            'module_width': 0.6,
            'font_size': 10,
        }
        bar.write(buffer_barcode_SVG, options=options)

        context = {
            'ticket': ticket,
            'config': Configuration.get_solo(),
            'img_svg': buffer_svg.getvalue().decode('utf-8'),
            # 'img_svg64': base64.b64encode(buffer_svg.getvalue()).decode('utf-8'),
            'bar_svg': buffer_barcode_SVG.getvalue().decode('utf-8'),
            # 'bar_svg64': base64.b64encode(buffer_barcode_SVG.getvalue()).decode('utf-8'),

        }

        return render(request, 'ticket/ticket.html', context=context)
        # return render(request, 'ticket/qrtest.html', context=context)



def products(request):
    options = OptionGenerale.objects.all()
    options_list = []
    for ele in options:
        options_list.append({'value': str(ele.uuid), 'name': ele.name})

    categorie_list = [
        { 'value': 'B', 'name': 'Billet payant'},
        { 'value': 'P', 'name': "Pack d'objets"},
        { 'value': 'R', 'name': 'Recharge cashless'},
        { 'value': 'S', 'name': 'Recharge suspendue'},
        { 'value': 'T', 'name': 'Vetement'},
        { 'value': 'M', 'name': 'Merchandasing'},
        { 'value': 'A', 'name': "Abonnement et/ou adhésion associative"},
        { 'value': 'D', 'name': 'Don'},
        { 'value': 'F', 'name': 'Reservation gratuite'},
        { 'value': 'V', 'name': 'Nécessite une validation manuelle'}
    ]
    context = {
        'options_list': options_list,
        'categorie_list': categorie_list
    }
    return TemplateResponse(request, 'htmx/products/createProducts.html', context=context)
    

def getOptionGenerale(request):
    queryset = OptionGenerale.objects.all()
    fragmentHtml = '<select id="product-options-checkbox" multiple>'
    if request.GET.get('id') == 'radio':
        fragmentHtml = '<select id="product-options-radio" multiple>'

    for ele in queryset:
        fragmentHtml = fragmentHtml + '<option value="' + str(ele.uuid) +'">' + ele.name + '</option>'
    
    fragmentHtml = fragmentHtml + '</select>'
    print(request.GET.get('id'))
    return HttpResponse(fragmentHtml, content_type="text/plain")