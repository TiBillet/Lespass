"""
Commande de création des données de démonstration pour le module booking.
/ Management command to create demo data for the booking module.

LOCALISATION : booking/management/commands/create_booking_fixtures.py

Données créées :
- Calendrier "Calendrier général" avec jours fériés français et fermetures.
- Planning hebdomadaire "Coworking weekdays" (lun–ven, 8 créneaux × 60 min).
- Planning hebdomadaire "Salles de répét' weekend" (sam–dim, 3 créneaux × 180 min).
- Produits communs : Coworking, Imprimante 3D, Petite salle, Grande salle.
- Ressources liées à ces produits : Coworking (capacité 3), Imprimante 3D (capacité 1),
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

import requests

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from BaseBillet.models import Product
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
        products_by_name = self._create_products()
        self._create_resources(
            calendrier,
            coworking_opening,
            repet_opening,
            products_by_name,
        )

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

    def _create_products(self):
        """
        Crée les produits communs aux ressources.
        / Creates the shared products for bookable resources.

        LOCALISATION : booking/management/commands/create_booking_fixtures.py

        Les champs nom, descriptions et image sont sur le modèle Product.
        Chaque ressource est ensuite liée à son produit via une ForeignKey.
        / Name, descriptions and image live on the Product model.
        Each resource is then linked to its product through a ForeignKey.

        Les images sont téléchargées depuis picsum.photos.
        / Images are downloaded from picsum.photos.
        """
        products_data = [
            {
                "name": "Coworking",
                "short_description": "Espace de travail partagé, 3 postes.",
                "long_description": (
                    "Espace de travail partagé, 3 postes disponibles simultanément. "
                    "Prises, WiFi haut débit, café."
                ),
                "image_url": "https://picsum.photos/seed/coworking/800/400",
            },
            {
                "name": "Imprimante 3D",
                "short_description": "Imprimante FDM Prusa MK4.",
                "long_description": (
                    "Imprimante FDM Prusa MK4. Filament PLA fourni. "
                    "Formation obligatoire avant première utilisation."
                ),
                "image_url": "https://picsum.photos/seed/imprimante3d/800/400",
            },
            {
                "name": "Petite salle",
                "short_description": "Salle de répétition 20 m².",
                "long_description": (
                    "Salle de répétition insonorisée, 20 m². "
                    "Batterie, amplis et câblage inclus. Capacité : 4 musiciens."
                ),
                "image_url": "https://picsum.photos/seed/petitesalle/800/400",
            },
            {
                "name": "Grande salle",
                "short_description": "Grande salle de répétition 40 m².",
                "long_description": (
                    "Grande salle de répétition, 40 m². Scène surélevée, sono complète. "
                    "Idéale pour les groupes de 6 personnes et plus."
                ),
                "image_url": "https://picsum.photos/seed/grandesalle/800/400",
            },
        ]

        products_by_name = {}
        for data in products_data:
            product, _created = Product.objects.update_or_create(
                name=data["name"],
                defaults={
                    "categorie_article": Product.RESOURCE,
                    "short_description": data["short_description"],
                    "long_description": data["long_description"],
                    "publish": True,
                },
            )

            if data.get("image_url") and not product.img:
                try:
                    response = requests.get(data["image_url"], timeout=10)
                    response.raise_for_status()
                    product.img.save(
                        f"resource_{data['name'].replace(' ', '_').lower()}.jpg",
                        ContentFile(response.content),
                        save=True,
                    )
                except requests.RequestException as erreur_telechargement:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Image non téléchargée pour {data['name']} : {erreur_telechargement}"
                        )
                    )

            products_by_name[data["name"]] = product

        return products_by_name

    def _create_resources(self, calendrier, coworking_opening, repet_opening, products_by_name):
        """
        Crée les ressources réservables liées à leurs produits.
        / Creates the bookable resources linked to their products.

        LOCALISATION : booking/management/commands/create_booking_fixtures.py

        Les champs spécifiques (calendrier, planning, capacité, groupe)
        restent sur le modèle Resource. Le nom et l'image viennent du produit lié.
        / Specific fields (calendar, schedule, capacity, group) stay on Resource.
        Name and image come from the linked product.

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

        resources_data = [
            {
                "product_name": "Coworking",
                "calendar": calendrier,
                "weekly_opening": coworking_opening,
                "capacity": 3,
                "group": None,
            },
            {
                "product_name": "Imprimante 3D",
                "calendar": calendrier,
                "weekly_opening": coworking_opening,
                "capacity": 1,
                "group": None,
            },
            {
                "product_name": "Petite salle",
                "calendar": calendrier,
                "weekly_opening": repet_opening,
                "capacity": 1,
                "group": groupe_repet,
            },
            {
                "product_name": "Grande salle",
                "calendar": calendrier,
                "weekly_opening": repet_opening,
                "capacity": 1,
                "group": groupe_repet,
            },
        ]

        for data in resources_data:
            Resource.objects.update_or_create(
                product=products_by_name[data["product_name"]],
                defaults={
                    "calendar": data["calendar"],
                    "weekly_opening": data["weekly_opening"],
                    "capacity": data["capacity"],
                    "group": data["group"],
                },
            )
