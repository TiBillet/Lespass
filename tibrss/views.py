from django.db import connection
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseNotFound
from django.contrib.syndication.views import Feed
from django.urls import reverse
from django.utils import feedgenerator
from django.utils import timezone
from icalendar import Calendar, Event as ICalEvent
from datetime import datetime, timedelta
from django.core.mail import send_mail
from django.conf import settings

from BaseBillet.models import Event, Configuration, Reservation
from Customers.models import Client
from django.contrib.auth import get_user_model


class LatestEntriesEvent(Feed):
    description = "Derniers évènements créés"
    base_url = "https://www.tibilet.coop"

    def link(self):
        link = "/rss/latest/feed/"
        try:
            if connection.tenant:
                if connection.tenant.categorie != Client.ROOT:
                    link = f"https://{connection.tenant.get_primary_domain().domain}/rss/latest/feed/"
                    self.base_url = f"https://{connection.tenant.get_primary_domain().domain}"
        except AttributeError:
            link = "https://www.tibillet.coop/rss/latest/feed/"

        return link


    def title(self):
        name_orga = ""
        try:
            if connection.tenant:
                if connection.tenant.categorie != Client.ROOT:
                    config = Configuration.get_solo()
                    name_orga = f"{config.organisation}"
        except AttributeError:
            name_orga = ""

        return f"{name_orga} : Derniers évènements créés"

    def items(self):
        """

        :return: list
        """
        return Event.objects.order_by('-created')[:20]

    def item_title(self, item: Event):
        return f"{item.name} : {item.datetime.strftime('%D %R')}"

    def item_description(self, item: Event):
        if item.short_description and item.long_description:
            return f"{item.short_description} - {item.long_description}"
        elif item.long_description:
            return item.long_description
        elif item.long_description:
            return item.long_description

        return ""

    # item_link is only needed if NewsItem has no get_absolute_url method.
    def item_link(self, item):
        # return reverse('show_event', args=[item.slug])
        return item.url()

    def item_pubdate(self, item: Event):
        return item.created

    def item_enclosures(self, item: Event):
        if item.img :
            url_img = self.base_url + item.img.med.url
            return [feedgenerator.Enclosure(url_img, str(item.img.size), "image/jpg")]

        return ""

class ICalFeed:
    def __init__(self):
        self.cal = Calendar()
        self.cal.add('prodid', '-//TiBillet Calendar//tibillet.org//')
        self.cal.add('version', '2.0')
        self.cal.add('name', self.get_calendar_name())
        self.cal.add('description', self.get_calendar_description())
        self.cal.add('timezone', timezone.get_current_timezone().zone)

    def get_calendar_name(self):
        try:
            if connection.tenant and connection.tenant.categorie != Client.ROOT:
                config = Configuration.get_solo()
                return f"{config.organisation} - Événements"
        except AttributeError:
            pass
        return "TiBillet - Événements"

    def get_calendar_description(self):
        try:
            if connection.tenant and connection.tenant.categorie != Client.ROOT:
                config = Configuration.get_solo()
                return f"Calendrier des événements de {config.organisation}"
        except AttributeError:
            pass
        return "Calendrier des événements TiBillet"

    def get_events(self):
        return Event.objects.all().order_by('datetime')

    def generate(self):
        for event in self.get_events():
            ical_event = ICalEvent()
            ical_event.add('summary', event.name)
            ical_event.add('dtstart', event.datetime)
            
            # Utiliser end_datetime si disponible, sinon calculer une durée par défaut de 2h
            if event.end_datetime:
                ical_event.add('dtend', event.end_datetime)
            else:
                ical_event.add('dtend', event.datetime + timedelta(hours=2))
            
            ical_event.add('dtstamp', datetime.now())
            ical_event.add('uid', f"{event.uuid}@tibillet.org")
            
            # Description
            description = []
            if event.short_description:
                description.append(event.short_description)
            if event.long_description:
                description.append(event.long_description)
            if description:
                ical_event.add('description', '\n'.join(description))

            # URL de l'événement
            ical_event.add('url', event.url())

            # Lieu
            if event.postal_address:
                ical_event.add('location', str(event.postal_address))

            self.cal.add_component(ical_event)

        return self.cal.to_ical()

def ical_feed(request):
    feed = ICalFeed()
    response = HttpResponse(feed.generate(), content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="events.ics"'
    # En-têtes pour permettre la mise à jour automatique dans Nextcloud
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def generate_invitation_ical(request, event_uuid):
    """
    Génère une invitation iCal pour un événement spécifique
    """
    try:
        event = Event.objects.get(uuid=event_uuid)
        reservation = Reservation.objects.get(event=event, user_commande=request.user)
        
        cal = Calendar()
        cal.add('prodid', '-//TiBillet//FR')
        cal.add('version', '2.0')
        cal.add('method', 'REQUEST')
        
        ical_event = ICalEvent()
        ical_event.add('summary', event.name)
        ical_event.add('dtstart', event.datetime)
        if event.end_datetime:
            ical_event.add('dtend', event.end_datetime)
        ical_event.add('dtstamp', datetime.now())
        ical_event.add('uid', f"{event.uuid}@tibillet.org")
        ical_event.add('sequence', reservation.ical_sequence)
        
        # Ajouter le participant
        ical_event.add('attendee', f"mailto:{reservation.user_commande.email}")
        ical_event.add('organizer', f"mailto:{settings.DEFAULT_FROM_EMAIL}")
        
        # Description
        description = []
        if event.short_description:
            description.append(event.short_description)
        if event.long_description:
            description.append(event.long_description)
        if description:
            ical_event.add('description', '\n'.join(description))
        
        # Lieu
        if event.postal_address:
            ical_event.add('location', str(event.postal_address))
        
        cal.add_component(ical_event)
        
        response = HttpResponse(cal.to_ical(), content_type='text/calendar; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="invitation_{event.slug}.ics"'
        return response
        
    except (Event.DoesNotExist, Reservation.DoesNotExist):
        return HttpResponseNotFound("Événement ou réservation non trouvé")

def send_event_invitation(request, event_uuid):
    """
    Envoie une invitation iCal par email pour un événement
    """
    event = get_object_or_404(Event, uuid=event_uuid)
    email = request.POST.get('email')
    first_name = request.POST.get('first_name', '')
    last_name = request.POST.get('last_name', '')
    
    if not email:
        return HttpResponseNotFound("Email requis")
    
    # Créer ou récupérer l'utilisateur
    User = get_user_model()
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            'first_name': first_name,
            'last_name': last_name
        }
    )
    
    # Créer la réservation
    reservation, created = Reservation.objects.get_or_create(
        event=event,
        user_commande=user,
        defaults={
            'status': Reservation.CREATED,
            'ical_sequence': 0
        }
    )
    
    # Générer l'invitation iCal
    cal = Calendar()
    cal.add('prodid', '-//TiBillet//FR')
    cal.add('version', '2.0')
    cal.add('method', 'REQUEST')
    
    ical_event = ICalEvent()
    ical_event.add('summary', event.name)
    ical_event.add('dtstart', event.datetime)
    if event.end_datetime:
        ical_event.add('dtend', event.end_datetime)
    ical_event.add('dtstamp', datetime.now())
    ical_event.add('uid', f"{event.uuid}@tibillet.org")
    ical_event.add('sequence', reservation.ical_sequence)
    
    # Ajouter le participant avec les liens d'action
    ical_event.add('attendee', f"mailto:{email}")
    ical_event.add('organizer', f"mailto:{settings.DEFAULT_FROM_EMAIL}")
    
    # Description avec liens d'action
    description = []
    if event.short_description:
        description.append(event.short_description)
    if event.long_description:
        description.append(event.long_description)
    
    # Ajouter les liens d'action
    accept_url = request.build_absolute_uri(
        reverse('accept_invitation', args=[event.uuid, reservation.uuid])
    )
    decline_url = request.build_absolute_uri(
        reverse('decline_invitation', args=[event.uuid, reservation.uuid])
    )
    
    description.append(f"\nPour accepter l'invitation : {accept_url}")
    description.append(f"Pour refuser l'invitation : {decline_url}")
    
    ical_event.add('description', '\n'.join(description))
    
    # Lieu
    if event.postal_address:
        ical_event.add('location', str(event.postal_address))
    
    cal.add_component(ical_event)
    
    # Envoyer l'email avec l'invitation
    subject = f"Invitation à l'événement : {event.name}"
    message = f"""
    Bonjour {first_name or 'participant'},

    Vous êtes invité à l'événement "{event.name}" qui aura lieu le {event.datetime.strftime('%d/%m/%Y à %H:%M')}.
    
    Pour répondre à cette invitation, vous pouvez :
    1. Utiliser les liens dans l'email
    2. Utiliser votre client mail (Gmail, Outlook, etc.)
    
    Pour accepter : {accept_url}
    Pour refuser : {decline_url}
    
    Cordialement,
    L'équipe
    """
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
    
    return HttpResponse("Invitation envoyée avec succès")

def accept_invitation(request, event_uuid, reservation_uuid):
    """
    Gère l'acceptation d'une invitation
    """
    event = get_object_or_404(Event, uuid=event_uuid)
    reservation = get_object_or_404(Reservation, uuid=reservation_uuid, event=event)
    
    # Mettre à jour le statut de la réservation
    reservation.status = Reservation.VALID
    reservation.ical_sequence += 1
    reservation.save()
    
    # Envoyer un email de confirmation
    subject = f"Confirmation de participation à {event.name}"
    message = f"""
    Bonjour {reservation.user_commande.first_name or 'participant'},

    Votre participation à l'événement "{event.name}" a été confirmée.
    Date : {event.datetime.strftime('%d/%m/%Y à %H:%M')}
    
    À bientôt !
    
    Cordialement,
    L'équipe
    """
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [reservation.user_commande.email],
        fail_silently=False,
    )
    
    return HttpResponse("Participation confirmée avec succès")

def decline_invitation(request, event_uuid, reservation_uuid):
    """
    Gère le refus d'une invitation
    """
    event = get_object_or_404(Event, uuid=event_uuid)
    reservation = get_object_or_404(Reservation, uuid=reservation_uuid, event=event)
    
    # Mettre à jour le statut de la réservation
    reservation.status = Reservation.CANCELED
    reservation.ical_sequence += 1
    reservation.save()
    
    # Envoyer un email de confirmation
    subject = f"Confirmation de non-participation à {event.name}"
    message = f"""
    Bonjour {reservation.user_commande.first_name or 'participant'},

    Nous avons bien reçu votre refus de participer à l'événement "{event.name}".
    
    Nous espérons vous voir lors d'un prochain événement !
    
    Cordialement,
    L'équipe
    """
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [reservation.user_commande.email],
        fail_silently=False,
    )
    
    return HttpResponse("Non-participation confirmée avec succès")