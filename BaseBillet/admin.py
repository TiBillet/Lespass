from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import path
from django.shortcuts import render
from django.contrib import messages
from django.urls import reverse

from .models import ICalImport, Event, Configuration, Reservation

@admin.register(ICalImport)
class ICalImportAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'last_sync', 'active', 'created')
    list_filter = ('active', 'created')
    search_fields = ('name', 'url')
    readonly_fields = ('last_sync', 'created', 'updated')
    actions = ['sync_selected']

    def sync_selected(self, request, queryset):
        for ical_import in queryset:
            ical_import.sync_events()
    sync_selected.short_description = "Synchroniser les calendriers sélectionnés"

class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'datetime', 'end_datetime', 'published')
    list_filter = ('published', 'datetime')
    search_fields = ('name', 'short_description', 'long_description')
    date_hierarchy = 'datetime'
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<uuid:event_uuid>/send-invitation/',
                self.admin_site.admin_view(self.send_invitation_view),
                name='event-send-invitation',
            ),
        ]
        return custom_urls + urls
    
    def send_invitation_view(self, request, event_uuid):
        event = self.get_object(request, event_uuid)
        if not event:
            return HttpResponseRedirect('../')
            
        if request.method == 'POST':
            email = request.POST.get('email')
            first_name = request.POST.get('first_name', '')
            last_name = request.POST.get('last_name', '')
            
            if not email:
                messages.error(request, "L'email est requis")
                return HttpResponseRedirect(request.path)
            
            # Créer ou récupérer l'utilisateur
            from django.contrib.auth import get_user_model
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
            from icalendar import Calendar, Event as ICalEvent
            from datetime import datetime
            
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
            ical_event.add('organizer', f"mailto:{request.user.email}")
            
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
            from django.core.mail import send_mail
            from django.conf import settings
            
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
            
            messages.success(request, f"Invitation envoyée à {email}")
            return HttpResponseRedirect('../')
            
        context = {
            'title': f"Envoyer une invitation pour {event.name}",
            'event': event,
        }
        return render(request, 'admin/send_invitation.html', context)
    
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_send_invitation'] = True
        return super().changelist_view(request, extra_context=extra_context)

admin.site.register(Event, EventAdmin)
admin.site.register(Configuration) 