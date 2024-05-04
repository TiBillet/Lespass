from os.path import exists

import requests
import stripe
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django_tenants.utils import tenant_context

from BaseBillet.models import Membership, Product, OptionGenerale, Price, Configuration
from Customers.models import Client, Domain
import os

from root_billet.models import RootConfiguration

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def add_arguments(self, parser):
        # Named (optional) arguments
        parser.add_argument(
            '--tdd',
            action='store_true',
            help='Demo data for Test drived dev',
        )

    def handle(self, *args, **options):
        # START MIGRATE AND INSTALL BEFORE THIS SCRIPT
        sub = os.environ['SUB']
        tenant = Client.objects.get(name=sub)
        with tenant_context(tenant):
            config = Configuration.get_solo()
            config.organisation = "TiBilletistan"
            config.short_description = "Les scènes oniriques du TiBilletistan"
            config.long_description = ("Vous trouverez ici un exemple de plusieurs types d'évènements, d'adhésions et d'abonnements."
                                       "\nGratuit, payant, avec prix préférenciel."
                                       "\nAbonnement mensuels récurents ou ahdésion annuelle".)
            config.adress = "42 Rue Douglas Adams"
            config.postal_code = "97480"
            config.city = "Saint Jospeh"
            config.tva_number = "4242424242424242"
            config.siren = "424242424242"
            config.phone = "06 42 42 42 42"
            config.email = "contact@tibillet.re"
            config.site_web = "https://tibillet.org"
            config.legal_documents = "https://tibillet.org/cgucgv"
            config.twitter = "https://twitter.com/tibillet"
            config.facebook = "https://facebook.com/tibillet"
            config.instagram = "https://instagram.com/tibillet"
            config.save()

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
                name="Annuelle",
                short_description="Adhésion annuelle",
                prix='400',
                recurring_payment=False,
                subscription_type=Price.YEAR,
            )

            adhesion_asso_mensuelle_recurente, created = Price.objects.get_or_create(
                product=amap,
                name="Mensuelle",
                short_description="Adhésion récurente",
                prix='40',
                recurring_payment=True,
                subscription_type=Price.MONTH,
            )


            ### EVENTS ###

