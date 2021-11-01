from datetime import datetime

from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect

# Create your views here.
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.translation import ugettext_lazy as _

from AuthBillet.email import ActivationEmail
from BaseBillet.models import Configuration, Event, Reservation, LigneArticle
from BaseBillet.validator import ReservationValidator
from django.db import connection
from AuthBillet.models import TibilletUser

from threading import Thread


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


def creation_de_la_reservation(user: TibilletUser, event: Event, data):

    reservation = Reservation.objects.create(
        user_commande = user,
        event= event,
    )

    if data.get('radio_generale'):
        reservation.options.add(data.get('radio_generale')[0])

    for option_checkbox in data.get('option_checkbox'):
        reservation.options.add(option_checkbox)

    # import ipdb; ipdb.set_trace()
    #
    for billet in data.get('billets'):
        qty = data.get('billets')[billet]
        LigneArticle.objects.create(
            reservation = reservation,
            billet = billet,
            qty = qty,
        )

    for article in data.get('products'):
        qty = data.get('products')[article]
        LigneArticle.objects.create(
            reservation = reservation,
            article = article,
            qty = qty,
        )

    return reservation


#Modèle MVC
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

        print(request.data)

        reservation_validator = ReservationValidator(data=request.data)

        if reservation_validator.is_valid():
            print(reservation_validator.validated_data)
            configuration = Configuration.get_solo()
            context = {}

            data_reservation = reservation_validator.validated_data
            event = get_object_or_404(Event, pk=id)

            # import ipdb; ipdb.set_trace()
            # reste_place = configuration.jauge_max - event.reservations
            # if data_reservation.get('qty') > reste_place:
            #     raise serializers.ValidationError(_(f"Il ne reste plus que {reste_place} places"))

            if request.user.is_anonymous:
                User: TibilletUser = get_user_model()
                email = data_reservation.get('email')
                user, created = User.objects.get_or_create(username=email, email=email)

                if created:
                    user.is_active = False
                    user.first_name = data_reservation.get('nom')
                    user.last_name = data_reservation.get('prenom')
                    user.phone = data_reservation.get('phone')
                    user.client_source = connection.tenant
                    user.client_achat.add(connection.tenant)
                    user.save()

                request.user = user

            if not request.user.is_active or not request.user.password :

                print(f"{request.user} not active or no password")
                # on retire les commande non validé pour éviter les doublons
                # et on le remet non actif si pas de mot de passe :
                asupr = Reservation.objects.filter(user_commande=request.user, status=Reservation.MAIL_NON_VALIDEE, event=event)
                asupr.delete()
                request.user.is_active = False
                request.user.save()

                email_activation = ActivationEmail(request)

                # email_activation.send(to=[email,])
                thread_email = Thread(
                    target=email_activation.send,
                    kwargs={'to': [request.user.email, ],
                            'from_email': configuration.email}
                )

                thread_email.start()

                context['message'] = "Merci pour votre réservation ! \n" \
                                     "Il semble que vous n'avez pas encore de compte TiBillet. \n" \
                                     "Merci de vérifier votre boite mail pour valider votre réservation. \n" \
                                     "( N'oubliez pas de regarder dans les spams si vous ne voyez rien venir. ) \n" \
                                     "Merci !"

            elif request.user.is_active:
                print("is is_active !")

            reservation = creation_de_la_reservation(request.user, event, data_reservation)

            context['configuration'] = configuration
            context['event'] = event

            return render(request, 'html5up-massively/event.html', context=context)
        else:
            print(f"validator.errors : {reservation_validator.errors}")
            return Response(reservation_validator.errors, status=status.HTTP_400_BAD_REQUEST)
