from datetime import datetime

from django.http import HttpResponseRedirect
from django.shortcuts import render

from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from BaseBillet.models import Configuration, Event, Ticket


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
        context = {
            'ticket': ticket,
            'config': Configuration.get_solo(),
        }

        return render(request, 'ticket/ticket.html', context=context)