from datetime import datetime

from django.shortcuts import render, redirect

# Create your views here.
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.translation import ugettext_lazy as _

from BaseBillet.models import Configuration, Event
from BaseBillet.validator import ReservationValidator


class index(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        configuration = Configuration.get_solo()

        events = Event.objects.filter(datetime__gt=datetime.now())
        if len(events) > 0 :
            first_event = events[0]
        else :
            first_event = None

        context = {
            'configuration': configuration,
            'events': events[1:],
            'first_event': first_event,
        }

        return render(request, 'html5up-massively/index.html', context=context)




class event(APIView):
    permission_classes = [AllowAny]

    def get(self, request, id):
        event = get_object_or_404(Event, pk=id)
        configuration = Configuration.get_solo()

        context = {
            'configuration': configuration,
            'event': event,
        }

        return render(request, 'html5up-massively/event.html', context=context)

    def post(self, request, id):

        reservation_validator = ReservationValidator(data=request.data)
        if reservation_validator.is_valid():
            data_reservation = reservation_validator.validated_data
            event = get_object_or_404(Event, pk=id)
            configuration = Configuration.get_solo()

            reste_place = configuration.jauge_max - event.reservations
            if data_reservation.get('qty') > reste_place:
                raise serializers.ValidationError(_(f"Il ne reste plus que {reste_place} places"))

            context = {
                'configuration': configuration,
                'event': event,
                'message': 'Merci de valider votre réservation sur votre boite mail',
            }

            return render(request, 'html5up-massively/event.html', context=context)
        else:
            print(f"validator.errors : {reservation_validator.errors}")
            return Response(reservation_validator.errors, status=status.HTTP_400_BAD_REQUEST)