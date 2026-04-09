"""
Commande de création des données de démonstration pour le module booking.
/ Management command to create demo data for the booking module.

LOCALISATION : booking/management/commands/create_booking_fixtures.py

Données créées :
- Calendrier "Calendrier général" avec jours fériés français et fermetures.
- Planning hebdomadaire "Coworking weekdays" (lun–ven, 8 créneaux × 60 min).
- Planning hebdomadaire "Salles de répét' weekend" (sam–dim, 3 créneaux × 180 min).
- Ressources : Coworking (capacité 3), Imprimante 3D (capacité 1),
  Petite salle et Grande salle (groupe "Salle de répét'", capacité 1 chacune).

La commande est idempotente — get_or_create / update_or_create à chaque appel.
Elle s'appuie sur le contexte tenant de l'appelant (pas de schema_context interne).
/ The command is idempotent. It relies on the caller's tenant context.

Lancement direct / Direct run:
    docker exec lespass_django poetry run python manage.py shell -c "
    from django_tenants.utils import schema_context
    from django.core.management import call_command
    with schema_context('lespass'):
        call_command('create_booking_fixtures')
    "
"""
import datetime

from django.core.management.base import BaseCommand

from booking.models import (
    Calendar,
    ClosedPeriod,
    OpeningEntry,
    Resource,
    ResourceGroup,
    WeeklyOpening,
)


class Command(BaseCommand):
    help = "Crée les données de démonstration pour le module booking."

    def handle(self, *args, **options):
        calendrier = self._create_calendar()
        coworking_opening = self._create_coworking_opening()
        repet_opening = self._create_repet_opening()
        self._create_resources(calendrier, coworking_opening, repet_opening)

        self.stdout.write(self.style.SUCCESS("Données booking créées avec succès."))

    def _create_calendar(self):
        """
        Crée le calendrier avec les jours fériés français et les fermetures
        pour l'année en cours.
        / Creates the calendar with French public holidays and closures
        for the current year.
        """
        calendrier, _created = Calendar.objects.get_or_create(
            name="Calendrier général",
        )

        y = datetime.date.today().year

        jours_feries = [
            (datetime.date(y, 1, 1),  "Jour de l'An"),
            (datetime.date(y, 5, 1),  "Fête du Travail"),
            (datetime.date(y, 5, 8),  "Victoire 1945"),
            (datetime.date(y, 7, 14), "Fête Nationale"),
            (datetime.date(y, 8, 15), "Assomption"),
            (datetime.date(y, 11, 1), "Toussaint"),
            (datetime.date(y, 11, 11),"Armistice"),
            (datetime.date(y, 12, 25),"Noël"),
        ]
        for date_ferie, label in jours_feries:
            ClosedPeriod.objects.get_or_create(
                calendar=calendrier,
                start_date=date_ferie,
                defaults={"end_date": date_ferie, "label": label},
            )

        fermetures = [
            (datetime.date(y, 7, 1),  datetime.date(y, 8, 31),      "Fermeture estivale"),
            (datetime.date(y, 12, 21), datetime.date(y + 1, 1, 2),  "Fermeture fin d'année"),
        ]
        for start, end, label in fermetures:
            ClosedPeriod.objects.get_or_create(
                calendar=calendrier,
                start_date=start,
                defaults={"end_date": end, "label": label},
            )

        return calendrier

    def _create_coworking_opening(self):
        """
        Crée le planning "Coworking weekdays" : lundi au vendredi,
        8 créneaux de 60 min à partir de 09:00.
        / Creates "Coworking weekdays": Monday–Friday, 8 × 60 min from 09:00.
        """
        opening, _created = WeeklyOpening.objects.get_or_create(
            name="Coworking en semaine",
        )

        weekdays = [
            OpeningEntry.MONDAY,
            OpeningEntry.TUESDAY,
            OpeningEntry.WEDNESDAY,
            OpeningEntry.THURSDAY,
            OpeningEntry.FRIDAY,
        ]
        for weekday in weekdays:
            OpeningEntry.objects.get_or_create(
                weekly_opening=opening,
                weekday=weekday,
                defaults={
                    "start_time": datetime.time(9, 0),
                    "slot_duration_minutes": 60,
                    "slot_count": 8,
                },
            )

        return opening

    def _create_repet_opening(self):
        """
        Crée le planning "Salles de répét' weekend" : samedi et dimanche,
        3 créneaux de 180 min à partir de 10:00.
        / Creates "Salles de répét' weekend": Saturday–Sunday, 3 × 180 min from 10:00.
        """
        opening, _created = WeeklyOpening.objects.get_or_create(
            name="Répét' le weekend",
        )

        weekend_days = [
            OpeningEntry.SATURDAY,
            OpeningEntry.SUNDAY,
        ]
        for weekday in weekend_days:
            OpeningEntry.objects.get_or_create(
                weekly_opening=opening,
                weekday=weekday,
                defaults={
                    "start_time": datetime.time(10, 0),
                    "slot_duration_minutes": 180,
                    "slot_count": 3,
                },
            )

        return opening

    def _create_resources(self, calendrier, coworking_opening, repet_opening):
        """
        Crée les ressources réservables.
        / Creates the bookable resources.

        Ressources sans groupe :
        - Coworking (capacité 3) — planning semaine.
        - Imprimante 3D (capacité 1) — même planning que Coworking.

        Groupe "Salle de répét'" :
        - Petite salle (capacité 1) — planning week-end.
        - Grande salle (capacité 1) — planning week-end.
        """
        groupe_repet, _created = ResourceGroup.objects.get_or_create(
            name="Salle de répét'",
        )

        Resource.objects.update_or_create(
            name="Coworking",
            defaults={
                "calendar": calendrier,
                "weekly_opening": coworking_opening,
                "capacity": 3,
                "group": None,
            },
        )
        Resource.objects.update_or_create(
            name="Imprimante 3D",
            defaults={
                "calendar": calendrier,
                "weekly_opening": coworking_opening,
                "capacity": 1,
                "group": None,
            },
        )
        Resource.objects.update_or_create(
            name="Petite salle",
            defaults={
                "calendar": calendrier,
                "weekly_opening": repet_opening,
                "capacity": 1,
                "group": groupe_repet,
            },
        )
        Resource.objects.update_or_create(
            name="Grande salle",
            defaults={
                "calendar": calendrier,
                "weekly_opening": repet_opening,
                "capacity": 1,
                "group": groupe_repet,
            },
        )
