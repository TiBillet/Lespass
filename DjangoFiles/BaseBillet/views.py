from datetime import datetime

from django.http import HttpResponseRedirect
from django.shortcuts import render

from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from BaseBillet.models import Configuration, Event, Ticket

import base64
import segno
from io import StringIO, BytesIO

from django.template import engines
from django.http import HttpResponse

from PIL import Image

class index(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        configuration = Configuration.get_solo()
        if not configuration.activer_billetterie :
            return HttpResponseRedirect('https://www.tibillet.re')

        events = Event.objects.filter(datetime__gt=datetime.now())
        if len(events) > 0:
            first_event = events[0]
        else:
            first_event = None

        context = {
            'configuration': configuration,
            'events': events[1:],
            'first_event': first_event,
        }

        return render(request, 'html5up-massively/index.html', context=context)


class Ticket_html_view(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk_uuid):

        ticket = get_object_or_404(Ticket, uuid=pk_uuid)

        qr = segno.make(f'{ticket.uuid}')

        buffer_png = BytesIO()
        qr.save(buffer_png, kind='PNG', scale=3)

        buffer_svg = BytesIO()
        qr.save(buffer_svg, kind='svg', scale=10)

        context = {
            'ticket': ticket,
            'config': Configuration.get_solo(),
            'img_str': base64.b64encode(buffer_png.getvalue()).decode('utf-8'),
            'img_svg': buffer_svg.getvalue().decode('utf-8'),
            'img_svg64': base64.b64encode(buffer_svg.getvalue()).decode('utf-8'),
        }

        return render(request, 'ticket/ticket.html', context=context)
        # return render(request, 'ticket/qrtest.html', context=context)