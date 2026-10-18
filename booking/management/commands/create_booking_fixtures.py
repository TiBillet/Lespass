"""
Commande de création des données de démonstration pour le module booking.
/ Management command to create demo data for the booking module.

LOCALISATION : booking/management/commands/create_booking_fixtures.py

Données créées :
- Calendrier "Calendrier général" avec jours fériés français et fermetures.
- Planning hebdomadaire "Coworking weekdays" (lun–ven, 8 créneaux × 60 min).
- Planning hebdomadaire "Salles de répét' weekend" (sam–dim, 3 créneaux × 180 min).
- Planning hebdomadaire "Résidence et concert" (tous les jours, 10h–18h et 18h–minuit).
- Produits communs : Coworking, Imprimante 3D, Petite salle, Grande salle,
  Salle de résidence et concert.
- Ressources liées à ces produits : Coworking (capacité 3), Imprimante 3D (capacité 1),
  Petite salle, Grande salle et Salle de résidence et concert (groupe "Salle de répét'",
  capacité 1 chacune).
- La Salle de résidence et concert est bloquée par tous les événements du lieu
  (Event.ressource_bloquee), sauf ceux des tests.
- Bénévolat (spec TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md) :
  - "Bar associatif" : planning « Chaque semaine », du mercredi au samedi 17h–20h et
    20h–22h, plus « Grand ménage » le mercredi 10h–13h ;
  - "Festival" : planning ponctuel, un jeudi dans 3 mois : installation (jeudi), soirées
    de vendredi et samedi en runs de 2h de 16h à 4h, désinstallation (lundi et mardi) ;
  - des inscriptions de 6 bénévoles de démo, pour montrer tous les états d'un créneau.

La commande est idempotente — get_or_create / update_or_create à chaque appel.
Elle s'appuie sur le contexte tenant de l'appelant (pas de schema_context interne).
/ The command is idempotent. It relies on the caller's tenant context.

Lancement direct / Direct run:
    docker exec lespass_django poetry run python manage.py shell -c "
    from django_tenants.utils import tenant_context
    from django.core.management import call_command
    from Customers.models import Client
    with tenant_context(Client.objects.get(schema_name='lespass')):
        call_command('create_booking_fixtures')
    "
tenant_context, PAS schema_context : Event.save() lit connection.tenant, que
schema_context remplace par un FakeTenant.
/ tenant_context, NOT schema_context: Event.save() reads connection.tenant.
"""
import datetime

import requests

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from dateutil.relativedelta import relativedelta

from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Event, Price, Product
from booking.benevolat import aujourd_hui_au_lieu, creer_les_besoins_de_la_semaine_type
from booking.models import (
    BesoinBenevole,
    Calendar,
    ClosedPeriod,
    InscriptionBenevole,
    LigneDeSemaineType,
    OpeningEntry,
    PlanningBenevole,
    Resource,
    ResourceGroup,
    TacheBenevole,
    WeeklyOpening,
)


class Command(BaseCommand):
    help = "Crée les données de démonstration pour le module booking."

    def handle(self, *args, **options):
        calendrier = self._create_calendar()
        coworking_opening = self._create_coworking_opening()
        repet_opening = self._create_repet_opening()
        residence_concert_opening = self._create_residence_concert_opening()
        products_by_name = self._create_products_and_prices()
        self._create_resources(
            calendrier,
            coworking_opening,
            repet_opening,
            residence_concert_opening,
            products_by_name,
        )
        self._bloquer_la_salle_de_concert_pendant_les_evenements(products_by_name)
        benevoles = self._create_benevoles()
        self._create_planning_bar(calendrier, benevoles)
        self._create_planning_festival(benevoles)

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
            # (datetime.date(y, 7, 1),  datetime.date(y, 8, 31),      "Fermeture estivale"),
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

    def _create_residence_concert_opening(self):
        """
        Crée le planning "Résidence et concert" : tous les jours, deux créneaux.
        - Journée 10:00 – 18:00 (480 min) : résidence d'artistes.
        - Soirée 18:00 – minuit (360 min) : concert.
        Les événements de démo ont lieu surtout le soir : ils bloquent la soirée,
        la journée reste réservable.
        / Creates "Résidence et concert": every day, a 10-18 day slot and an
        18-24 evening slot. Demo events mostly block the evening slot.
        """
        opening, _created = WeeklyOpening.objects.get_or_create(
            name="Résidence et concert",
        )

        tous_les_jours = [
            OpeningEntry.MONDAY,
            OpeningEntry.TUESDAY,
            OpeningEntry.WEDNESDAY,
            OpeningEntry.THURSDAY,
            OpeningEntry.FRIDAY,
            OpeningEntry.SATURDAY,
            OpeningEntry.SUNDAY,
        ]
        for weekday in tous_les_jours:
            OpeningEntry.objects.get_or_create(
                weekly_opening=opening,
                weekday=weekday,
                start_time=datetime.time(10, 0),
                defaults={
                    "slot_duration_minutes": 480,
                    "slot_count": 1,
                },
            )
            OpeningEntry.objects.get_or_create(
                weekly_opening=opening,
                weekday=weekday,
                start_time=datetime.time(18, 0),
                defaults={
                    "slot_duration_minutes": 360,
                    "slot_count": 1,
                },
            )

        return opening

    def _create_products_and_prices(self):
        """
        Crée les produits et leurs tarifs associés pour les ressources.
        / Creates products and their associated prices for resources.

        LOCALISATION : booking/management/commands/create_booking_fixtures.py

        Les champs nom, descriptions et image sont sur le modèle Product.
        Chaque ressource est ensuite liée à des tarifs via une ManyToMany.
        / Name, descriptions and image live on the Product model.
        Each resource is then linked to prices through a ManyToMany.

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
                "price_name": "Créneau 1h",
                "price": 5.00,
            },
            {
                "name": "Imprimante 3D",
                "short_description": "Imprimante FDM Prusa MK4.",
                "long_description": (
                    "Imprimante FDM Prusa MK4. Filament PLA fourni. "
                    "Formation obligatoire avant première utilisation."
                ),
                "image_url": "https://picsum.photos/seed/imprimante3d/800/400",
                "price_name": "Créneau 1h",
                "price": 8.00,
            },
            {
                "name": "Petite salle",
                "short_description": "Salle de répétition 20 m².",
                "long_description": (
                    "Salle de répétition insonorisée, 20 m². "
                    "Batterie, amplis et câblage inclus. Capacité : 4 musiciens."
                ),
                "image_url": "https://picsum.photos/seed/petitesalle/800/400",
                "price_name": "Répétition 1h",
                "price": 12.00,
            },
            {
                "name": "Grande salle",
                "short_description": "Grande salle de répétition 40 m².",
                "long_description": (
                    "Grande salle de répétition, 40 m². Scène surélevée, sono complète. "
                    "Idéale pour les groupes de 6 personnes et plus."
                ),
                "image_url": "https://picsum.photos/seed/grandesalle/800/400",
                "price_name": "Répétition 1h",
                "price": 18.00,
            },
            {
                "name": "Salle de résidence et concert",
                "short_description": "Salle de 150 m² : résidence le jour, concert le soir.",
                "long_description": (
                    "Grande salle équipée d'une scène, d'une sono et d'un plan de feu. "
                    "En journée, elle accueille des résidences d'artistes. Le soir, "
                    "elle est réservée aux concerts du lieu : ces créneaux sont bloqués "
                    "automatiquement par la programmation."
                ),
                "image_url": "https://picsum.photos/seed/residenceconcert/800/400",
                "price_name": "Journée ou soirée",
                "price": 60.00,
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

            Price.objects.update_or_create(
                product=product,
                name=data["price_name"],
                defaults={
                    "prix": data["price"],
                    "publish": True,
                },
            )


            products_by_name[data["name"]] = product
        return products_by_name

    def _create_resources(self, calendrier, coworking_opening, repet_opening,
                          residence_concert_opening, products_by_name):
        """
        Crée les ressources réservables liées à leurs tarifs.
        / Creates the bookable resources linked to their prices.

        LOCALISATION : booking/management/commands/create_booking_fixtures.py

        Les champs spécifiques (calendrier, planning, capacité, groupe)
        restent sur le modèle Resource. Le nom et l'image viennent du produit lié.
        / Specific fields (calendar, schedule, capacity, group) stay on Resource.
        Name and image come from the linked product.

        Le groupe est facultatif : il sert seulement à ranger l'affichage.
        / The group is optional: it only organises the display.

        Groupe "Espace" :
        - Coworking (capacité 3) — planning semaine.

        Groupe "Ressource" :
        - Imprimante 3D (capacité 1) — même planning que Coworking.

        Groupe "Salle de répét'" :
        - Petite salle (capacité 1) — planning week-end.
        - Grande salle (capacité 1) — planning week-end.
        - Salle de résidence et concert (capacité 1) — tous les jours, journée
          et soirée. Horizon de 90 jours : les événements de démo sont tirés
          entre +7 et +90 jours (demo_data_v2), leurs blocages doivent être visibles.
        """
        groupe_repet, _created = ResourceGroup.objects.get_or_create(
            name="Salle de répét'",
        )
        groupe_espace, _created = ResourceGroup.objects.get_or_create(
            name="Espace",
        )
        groupe_ressource, _created = ResourceGroup.objects.get_or_create(
            name="Ressource",
        )

        resources_data = [
            {
                "name": "Salle de coworking 3 bureau",
                "description" : "Une salle lumineuse avec 3 bureau et 6 prises.",
                "product_name": "Coworking",
                "calendar": calendrier,
                "weekly_opening": coworking_opening,
                "capacity": 3,
                "group": groupe_espace,
            },
            {
                "name": "Imprimante Bambu Lab",
                "description" : "Une imprimante vraiment super et très rapide.",
                "product_name": "Imprimante 3D",
                "calendar": calendrier,
                "weekly_opening": coworking_opening,
                "capacity": 1,
                "group": groupe_ressource,
            },
            {
                "name": "Petite salle #1",
                "description" : "Une salle de 30m² permettant plein de choses.",
                "product_name": "Petite salle",
                "calendar": calendrier,
                "weekly_opening": repet_opening,
                "capacity": 1,
                "group": groupe_repet,
            },
            {
                "name": "Grande salle #1",
                "description" : "Une salle de 100m² au première étage, parfait pour tout type d'atelier",
                "product_name": "Grande salle",
                "calendar": calendrier,
                "weekly_opening": repet_opening,
                "capacity": 1,
                "group": groupe_repet,
            },
            {
                "name": "Salle de résidence et concert",
                "description": "Résidences d'artistes en journée, concerts le soir.",
                "product_name": "Salle de résidence et concert",
                "calendar": calendrier,
                "weekly_opening": residence_concert_opening,
                "capacity": 1,
                "group": groupe_repet,
                "booking_horizon_days": 90,
            },
        ]

        for data in resources_data:
            champs_de_la_ressource = {
                "name": data["name"],
                "description": data["description"],
                "calendar": data["calendar"],
                "weekly_opening": data["weekly_opening"],
                "capacity": data["capacity"],
                "group": data["group"],
            }
            # Horizon seulement s'il est donné : sinon, défaut du modèle (28 jours).
            # / Horizon only when given: otherwise the model default (28 days).
            if "booking_horizon_days" in data:
                champs_de_la_ressource["booking_horizon_days"] = data["booking_horizon_days"]
            Resource.objects.update_or_create(
                product=products_by_name[data["product_name"]],
                defaults=champs_de_la_ressource,
            )

    def _bloquer_la_salle_de_concert_pendant_les_evenements(self, products_by_name):
        """
        Rattache la salle de résidence et concert à tous les événements du lieu :
        leurs créneaux deviennent complets sur la page de réservation de la salle.
        / Links the residence & concert room to every event of the venue: the
        overlapping slots become full on the room's booking page.

        LOCALISATION : booking/management/commands/create_booking_fixtures.py

        Appelée par demo_data_v2 APRÈS la création des événements de démo.
        On exclut les événements des tests (E2E, API v2, pytest) : ils ont
        leurs propres attentes. Un événement sans date de fin ne bloquerait
        rien (booking_engine) : on lui donne début + 3 h, comme la fixture
        des événements de démo.
        / Called by demo_data_v2 AFTER the demo events. Test events are
        excluded. An event without an end gets start + 3 h.
        """
        salle_de_concert = Resource.objects.get(
            product=products_by_name["Salle de résidence et concert"],
        )

        evenements_du_lieu = (
            Event.objects.filter(archived=False)
            .exclude(name__startswith="E2E")
            .exclude(name__startswith="API v2")
            .exclude(name__startswith="[test")
        )

        nombre_d_evenements_rattaches = 0
        for evenement in evenements_du_lieu:
            evenement.ressource_bloquee = salle_de_concert
            champs_modifies = ["ressource_bloquee"]
            if evenement.end_datetime is None:
                evenement.end_datetime = evenement.datetime + datetime.timedelta(hours=3)
                champs_modifies.append("end_datetime")
            evenement.save(update_fields=champs_modifies)
            nombre_d_evenements_rattaches += 1

        self.stdout.write(
            f"Salle de résidence et concert bloquée par {nombre_d_evenements_rattaches} événement(s)."
        )


    # ------------------------------------------------------------------
    # Bénévolat / Volunteering
    # ------------------------------------------------------------------

    def _create_benevoles(self):
        """
        Six bénévoles de démo (comptes rattachés au lieu, sans mail de connexion).
        Prénom et nom ne sont écrits que s'ils sont vides : le compte est partagé.
        / Six demo volunteers. Names are written only if empty (shared account).

        :return: liste de comptes
        """
        personnes = [
            ("arthur.dent@h2g2.org", "Arthur", "Dent"),
            ("ford.prefect@h2g2.org", "Ford", "Prefect"),
            ("trillian@h2g2.org", "Trillian", "Astra"),
            ("zaphod@h2g2.org", "Zaphod", "Beeblebrox"),
            ("marvin@h2g2.org", "Marvin", "Android"),
            ("slartibartfast@h2g2.org", "Slartibartfast", "Magrathea"),
        ]
        benevoles = []
        for email, prenom, nom in personnes:
            compte = get_or_create_user(email, send_mail=False)
            champs_a_enregistrer = []
            if not compte.first_name:
                compte.first_name = prenom
                champs_a_enregistrer.append("first_name")
            if not compte.last_name:
                compte.last_name = nom
                champs_a_enregistrer.append("last_name")
            if champs_a_enregistrer:
                compte.save(update_fields=champs_a_enregistrer)
            benevoles.append(compte)
        return benevoles

    def _tache(self, nom, description):
        """
        La tâche de ce nom, créée si elle n'existe pas. Le nom n'est pas unique en base :
        on prend la première trouvée (get_or_create planterait sur un doublon).
        / The task with this name, created if missing (names are not unique).
        """
        tache = TacheBenevole.objects.filter(name=nom).first()
        if tache is None:
            tache = TacheBenevole.objects.create(name=nom, description=description)
        return tache

    def _inscrire(self, besoin, personnes):
        """Inscrit ces personnes sur ce besoin (sans doublon). / Signs these people up."""
        for personne in personnes:
            InscriptionBenevole.objects.get_or_create(besoin=besoin, user=personne)

    def _create_planning_bar(self, calendrier, benevoles):
        """
        Planning « Chaque semaine » du bar, relié au calendrier des fermetures :
        - du mercredi au samedi : « Tenir le bar » 17h–20h et 20h–22h, 2 postes ;
        - le mercredi : « Grand ménage » 10h–13h, 2 postes.
        Les créneaux viennent de la semaine type (4 semaines à l'avance). Les inscriptions
        couvrent la première semaine : créneaux couverts, à moitié, vides, et un renfort.
        Créé une seule fois : si le planning existe, on n'y touche pas.
        / Weekly bar planning. Created once; left alone if it exists.
        """
        planning, planning_vient_d_etre_cree = PlanningBenevole.objects.get_or_create(
            slug="bar-associatif",
            defaults={
                "name": "Bar associatif",
                "description": "Le bar du lieu tourne grâce aux bénévoles. Un créneau, une soirée, ou plus si affinités !",
                "published": True,
                "type_de_planning": PlanningBenevole.HEBDOMADAIRE,
                "horizon_en_semaines": 4,
                "calendrier": calendrier,
            },
        )
        if not planning_vient_d_etre_cree:
            return planning

        tenir_le_bar = self._tache("Tenir le bar", "Servir au comptoir, encaisser, garder un œil sur les verres consignés.")
        grand_menage = self._tache("Grand ménage", "Sols, frigos, réserve. Prévoir des vêtements qui ne craignent rien.")

        mercredi, samedi = 2, 5
        for jour in range(mercredi, samedi + 1):
            for heure_debut, heure_fin in [(17, 20), (20, 22)]:
                LigneDeSemaineType.objects.create(
                    planning=planning, jour_de_la_semaine=jour, tache=tenir_le_bar,
                    heure_debut=datetime.time(heure_debut), heure_fin=datetime.time(heure_fin),
                    nombre_souhaite=2,
                )
        LigneDeSemaineType.objects.create(
            planning=planning, jour_de_la_semaine=mercredi, tache=grand_menage,
            heure_debut=datetime.time(10), heure_fin=datetime.time(13), nombre_souhaite=2,
        )
        creer_les_besoins_de_la_semaine_type(planning)

        # Les 4 premiers créneaux du bar 17h–20h, puis des 20h–22h et du ménage.
        # / The first bar and cleaning slots, with varied sign-ups.
        arthur, ford, trillian, zaphod, marvin, slartibartfast = benevoles
        creneaux_du_bar_17h = list(planning.besoins.filter(
            tache=tenir_le_bar, heure_debut=datetime.time(17),
        ).order_by("date")[:4])
        creneaux_du_bar_20h = list(planning.besoins.filter(
            tache=tenir_le_bar, heure_debut=datetime.time(20),
        ).order_by("date")[:3])
        creneaux_de_menage = list(planning.besoins.filter(tache=grand_menage).order_by("date")[:2])

        self._inscrire(creneaux_du_bar_17h[0], [arthur, ford])                # couvert
        self._inscrire(creneaux_du_bar_17h[1], [trillian])                   # à moitié
        self._inscrire(creneaux_du_bar_17h[2], [zaphod, marvin, arthur])     # + 1 renfort
        # le 4e reste vide / the 4th stays empty
        self._inscrire(creneaux_du_bar_20h[0], [ford, trillian])
        self._inscrire(creneaux_du_bar_20h[2], [slartibartfast])
        self._inscrire(creneaux_de_menage[0], [marvin, slartibartfast])
        return planning

    def _create_planning_festival(self, benevoles):
        """
        Planning ponctuel du festival, autour d'un jeudi dans 3 mois :
        - jeudi : « Installation » 9h–13h et 14h–18h, 2 postes ;
        - vendredi et samedi : runs de 2h de 16h à 4h du matin, « Tenir le bar » (3 postes)
          et « Accueil / entrée » (2 postes). Un créneau appartient au jour où il COMMENCE :
          les runs 0h–2h et 2h–4h de la nuit de vendredi sont rangés le samedi, ceux de la
          nuit de samedi le dimanche ;
        - lundi et mardi : « Désinstallation » 9h–13h et 14h–18h, 2 postes.
        Créé une seule fois : si le planning existe, on n'y touche pas (ses dates dépendent
        du jour du lancement).
        / One-off festival planning around a Thursday 3 months ahead. Created once.
        """
        planning, planning_vient_d_etre_cree = PlanningBenevole.objects.get_or_create(
            slug="festival",
            defaults={
                "name": "Festival",
                "description": "Trois jours de musique : on a besoin de monde pour monter, tenir et démonter !",
                "published": True,
                "type_de_planning": PlanningBenevole.PONCTUEL,
            },
        )
        if not planning_vient_d_etre_cree:
            return planning

        installation = self._tache("Installation", "Monter la scène, les barnums et la signalétique. Chaussures fermées.")
        tenir_le_bar = self._tache("Tenir le bar", "Servir au comptoir, encaisser, garder un œil sur les verres consignés.")
        accueil = self._tache("Accueil / entrée", "Vérifier les billets, poser les bracelets, renseigner le public.")
        desinstallation = self._tache("Désinstallation", "Démonter, ranger, trier les déchets.")

        # Le premier jeudi à 3 mois ou plus d'aujourd'hui. date.weekday() : 3 = jeudi.
        # / The first Thursday at least 3 months from today.
        dans_trois_mois = aujourd_hui_au_lieu() + relativedelta(months=3)
        jeudi = dans_trois_mois + datetime.timedelta(days=(3 - dans_trois_mois.weekday()) % 7)
        vendredi = jeudi + datetime.timedelta(days=1)
        samedi = jeudi + datetime.timedelta(days=2)
        lundi = jeudi + datetime.timedelta(days=4)
        mardi = jeudi + datetime.timedelta(days=5)

        def creneau(tache, une_date, heure_debut, heure_fin, nombre_souhaite):
            return BesoinBenevole.objects.create(
                planning=planning, tache=tache, date=une_date,
                heure_debut=datetime.time(heure_debut), heure_fin=datetime.time(heure_fin),
                nombre_souhaite=nombre_souhaite,
            )

        installation_du_matin = creneau(installation, jeudi, 9, 13, 2)
        creneau(installation, jeudi, 14, 18, 2)

        # Runs de 2h de 16h à 4h : 16-18, 18-20, 20-22, 22-00 le jour même ;
        # 00-02 et 02-04 le lendemain (jour où ils commencent).
        # / 2-hour runs from 4pm to 4am; after midnight, dated the next day.
        runs_du_soir = [(16, 18), (18, 20), (20, 22), (22, 0)]
        runs_de_la_nuit = [(0, 2), (2, 4)]
        creneaux_de_la_soiree = {}
        for jour_de_la_soiree in [vendredi, samedi]:
            lendemain = jour_de_la_soiree + datetime.timedelta(days=1)
            for une_date, runs in [(jour_de_la_soiree, runs_du_soir), (lendemain, runs_de_la_nuit)]:
                for heure_debut, heure_fin in runs:
                    creneaux_de_la_soiree[(jour_de_la_soiree, heure_debut, "bar")] = creneau(
                        tenir_le_bar, une_date, heure_debut, heure_fin, 3,
                    )
                    creneaux_de_la_soiree[(jour_de_la_soiree, heure_debut, "accueil")] = creneau(
                        accueil, une_date, heure_debut, heure_fin, 2,
                    )

        for une_date in [lundi, mardi]:
            creneau(desinstallation, une_date, 9, 13, 2)
            creneau(desinstallation, une_date, 14, 18, 2)

        arthur, ford, trillian, zaphod, marvin, slartibartfast = benevoles
        self._inscrire(installation_du_matin, [slartibartfast, marvin])
        self._inscrire(creneaux_de_la_soiree[(vendredi, 16, "accueil")], [trillian])
        self._inscrire(creneaux_de_la_soiree[(vendredi, 20, "bar")], [zaphod, ford, arthur])
        self._inscrire(creneaux_de_la_soiree[(vendredi, 0, "bar")], [ford])
        self._inscrire(creneaux_de_la_soiree[(samedi, 22, "bar")], [zaphod, trillian, arthur, marvin])
        return planning
