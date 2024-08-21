from datetime import timedelta
from os.path import exists
from random import randint

import requests
import stripe
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
from django_tenants.utils import tenant_context

from BaseBillet.models import Membership, Product, OptionGenerale, Price, Configuration, Event, Tag
from Customers.models import Client, Domain
import os

from fedow_connect.fedow_api import FedowAPI
from fedow_connect.models import FedowConfig
from root_billet.models import RootConfiguration

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    # def add_arguments(self, parser):
    # Named (optional) arguments
    # parser.add_argument(
    #     '--tdd',
    #     action='store_true',
    #     help='Demo data for Test drived dev',
    # )

    def handle(self, *args, **options):
        # START MIGRATE AND INSTALL BEFORE THIS SCRIPT
        sub = os.environ['SUB']
        tenant = Client.objects.get(name=sub)
        with tenant_context(tenant):
            logger.info(f"Start demo_data. Sub : {sub}, tenant : {tenant}")

            ### CONFIGURATION VARIABLE ####

            config = Configuration.get_solo()
            config.organisation = sub.capitalize()
            config.short_description = "Les scènes oniriques du TiBilletistan : un espace de démonstration."
            config.long_description = (
                "Vous trouverez ici un exemple de plusieurs types d'évènements, d'adhésions et d'abonnements."
                "\nGratuit, payant, avec prix préférenciel."
                "\nAbonnement mensuels récurents ou ahdésion annuelle.")
            config.adress = "42 Rue Douglas Adams"
            config.postal_code = "97480"
            config.city = "Saint Joseph"
            config.tva_number = "4242424242424242"
            config.siren = "424242424242"
            config.phone = "06 42 42 42 42"
            config.email = os.environ['ADMIN_EMAIL']
            config.site_web = "https://tibillet.org"
            config.legal_documents = "https://tibillet.org/cgucgv"
            config.twitter = "https://twitter.com/tibillet"
            config.facebook = "https://facebook.com/tibillet"
            config.instagram = "https://instagram.com/tibillet"
            config.save()

            ### LINK TO FEDOW

            # TODO: a faire dans la création de nouveau tenant, connection fedow obligatoire et check admin wallet
            ## Liaison tenant avec Fedow
            fedowAPI = FedowAPI()
            # La première création de l'instance FedowAPI génère un nouveau lieu coté Fedow s'il n'existe pas.
            # avec la fonction : fedowAPI.place.create()
            assert FedowConfig.get_solo().can_fedow()

            ### PRODUCT ###
            option_membre_actif, created = OptionGenerale.objects.get_or_create(
                name="Membre actif.ve",
                description="Je souhaite m'investir à donf !",
            )

            vege, created = OptionGenerale.objects.get_or_create(
                name="Vegetarien",
                description="Je suis végé",
            )

            intolerance, created = OptionGenerale.objects.get_or_create(
                name="Intolérance au glutent",
            )

            livraison_asso, created = OptionGenerale.objects.get_or_create(
                name="Livraison à l'asso"
            )

            livraison_maison, created = OptionGenerale.objects.get_or_create(
                name="Livraison à la maison"
            )

            terasse, created = OptionGenerale.objects.get_or_create(
                name="Terrasse",
                description="Une table en terasse",
            )

            interieur, created = OptionGenerale.objects.get_or_create(
                name="Salle",
                description="Une table à l'intérieur",
            )

            terasse, created = OptionGenerale.objects.get_or_create(
                name="Terrasse",
                description="Une table en terasse",
            )

            ### MEMBERSHIP ###

            adhesion_asso, created = Product.objects.get_or_create(
                name="Adhésion associative",
                short_description="Adhérez à l'association",
                long_description="Vous pouvez prendre une adhésion en une seule fois, ou payer tout les mois.",
                categorie_article=Product.ADHESION,
            )
            adhesion_asso.option_generale_checkbox.add(option_membre_actif)

            adhesion_asso_annuelle, created = Price.objects.get_or_create(
                product=adhesion_asso,
                name="Annuelle",
                short_description="Adhésion annuelle",
                prix='20',
                recurring_payment=False,
                subscription_type=Price.YEAR,
            )

            adhesion_asso_mensuelle_recurente, created = Price.objects.get_or_create(
                product=adhesion_asso,
                name="Mensuelle",
                short_description="Adhésion mensuelle récurente",
                prix='2',
                recurring_payment=True,
                subscription_type=Price.MONTH,
            )

            amap, created = Product.objects.get_or_create(
                name="Panier AMAP",
                short_description="Adhésion au panier AMAP",
                long_description="Association pour le maintient d'une agriculture paysanne, recevez un panier par semaine.",
                categorie_article=Product.ADHESION,

            )
            amap.option_generale_radio.add(livraison_asso)
            amap.option_generale_radio.add(livraison_maison)

            amap_annuelle, created = Price.objects.get_or_create(
                product=amap,
                name="Annuel",
                short_description="Adhésion annuel",
                prix='400',
                recurring_payment=False,
                subscription_type=Price.YEAR,
            )

            amap_mensuelle_recurente, created = Price.objects.get_or_create(
                product=amap,
                name="Mensuel",
                short_description="Adhésion récurente",
                prix='40',
                recurring_payment=True,
                subscription_type=Price.MONTH,
            )

            ### BADGEUSE ###

            badgeuse_cowork, created = Product.objects.get_or_create(
                name="Badgeuse Co-Working",
                short_description="Badger l'acces au co working",
                long_description="Venez pointer votre présence.",
                categorie_article=Product.BADGE,
            )

            badge_zero, created = Price.objects.get_or_create(
                product=badgeuse_cowork,
                name="Passage",
                short_description="Pointage d'un passage",
                prix=0,
                recurring_payment=False,
            )

            # badge_jour, created = Price.objects.get_or_create(
            #     product=badgeuse_cowork,
            #     name="Jour",
            #     short_description="Pointage payant pour la journée",
            #     prix=5,
            #     recurring_payment=False,
            # )
            #
            # badge_hour, created = Price.objects.get_or_create(
            #     product=badgeuse_cowork,
            #     name="Heure",
            #     short_description="Pointage à l'heure",
            #     prix=1,
            #     recurring_payment=False,
            # )

            ### EVENTS ###
            rock, created = Tag.objects.get_or_create(name='Rock')
            jazz, created = Tag.objects.get_or_create(name='Jazz')
            prix_libre, created = Tag.objects.get_or_create(name='Prix libre')

            event_entree_libre, created = Event.objects.get_or_create(
                name="Entrée libre",
                datetime=timezone.now() + timedelta(days=10),
                short_description="Scène ouverte Rock !",
                long_description="Un évènement gratuit, ouvert à tous.tes sans réservation."
                                 "\nSeul les artistes annoncés et les descriptions sont affichés.",
                categorie=Event.CONCERT,
            )
            event_entree_libre.tag.add(prix_libre)
            event_entree_libre.tag.add(rock)

            ### GRATUIT MAIS AVEC RESERVATION OBLIGATOIRE ###

            free_resa, created = Product.objects.get_or_create(
                name="Reservation gratuite",
                short_description="Reservation gratuite",
                categorie_article=Product.FREERES,
                nominative=False,
            )

            free_resa_price, created = Price.objects.get_or_create(
                name="Tarif gratuit",
                prix=0,
                short_description="Tarif gratuit",
                product=free_resa,
            )

            event_gratuit_avec_free_resa, created = Event.objects.get_or_create(
                name="Gratuit avec reservation",
                datetime=timezone.now() + timedelta(days=12),
                jauge_max=200,
                max_per_user=4,
                short_description="Attention, places limités, pensez à réserver !",
                long_description="Un évènement gratuit, avec une jauge maximale de 200 personnes et un nombre de billet limités à 4 par reservation."
                                 "\nBillets non nominatifs.",
                categorie=Event.CONCERT,
            )
            event_gratuit_avec_free_resa.products.add(free_resa)
            event_gratuit_avec_free_resa.tag.add(prix_libre)
            event_gratuit_avec_free_resa.tag.add(jazz)

            ### PAYANT AVEC BILLET NOMINATIFS ET TARIF PREFERENTIEL ###

            billet, created = Product.objects.get_or_create(
                name="Billet",
                short_description="Billet",
                categorie_article=Product.BILLET,
                nominative=True,
            )

            plein_tarif, created = Price.objects.get_or_create(
                name="Plein tarif",
                short_description="Plein tarif",
                prix=20,
                product=billet,
            )

            tarif_adherant, created = Price.objects.get_or_create(
                name="Tarif Adhérant",
                short_description="Plein tarif",
                prix=10,
                product=billet,
                adhesion_obligatoire=adhesion_asso,
            )

            event_payant_nominatif_tarif_asso, created = Event.objects.get_or_create(
                name="Spectacle payant",
                datetime=timezone.now() + timedelta(days=13),
                jauge_max=600,
                max_per_user=10,
                short_description="Spectacle payant avec tarif préférentiel pour les adhérants à l'association",
                long_description="Jauge maximale de 600 personnes et un nombre de billet limités à 10 par reservation."
                                 "\nBillets nominatifs.",
                categorie=Event.CONCERT,
            )
            event_payant_nominatif_tarif_asso.products.add(billet)

            # TODO: Gratuit mais avec recharge cashless obligatoire
            # TODO: Multi artiste
