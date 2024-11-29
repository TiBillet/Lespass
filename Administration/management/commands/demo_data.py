import logging
import os
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
from django_tenants.utils import tenant_context, schema_context
from faker import Faker

from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Product, OptionGenerale, Price, Configuration, Event, Tag, PostalAddress
from Customers.models import Client, Domain
from fedow_connect.fedow_api import FedowAPI
from fedow_connect.models import FedowConfig

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

        # Fabrication d'un tenant pour de la fédération
        with schema_context('public'):
            name = "L'intérupteur"
            domain = os.getenv("DOMAIN")
            tenant, created = Client.objects.get_or_create(
                schema_name=slugify(name),
                name=name,
                on_trial=False,
                categorie=Client.SALLE_SPECTACLE,
            )
            Domain.objects.get_or_create(
                domain=f'{slugify(name)}.tibillet.localhost',
                tenant=tenant,
                is_primary=True
            )
            # Sans envoie d'email pour l'instant, on l'envoie quand tout sera bien terminé
            user: TibilletUser = get_or_create_user(os.environ['ADMIN_EMAIL'], send_mail=False)
            user.client_admin.add(tenant)
            user.is_staff = True
            user.save()

        tenant1 = Client.objects.get(name=sub)
        tenant2 = Client.objects.get(name="L'intérupteur")
        for tenant in [tenant1, tenant2]:
            with tenant_context(tenant):
                fake = Faker('fr_FR')
                logger.info(f"Start demo_data. Sub : {sub}, tenant : {tenant}")

                ### CONFIGURATION VARIABLE ####

                config = Configuration.get_solo()
                config.organisation = tenant.name
                config.short_description = f"Les scènes de {tenant.name} : un espace de démonstration."
                config.long_description = (
                    "Vous trouverez ici un exemple de plusieurs types d'évènements, d'adhésions et d'abonnements."
                    "\nGratuit, payant, avec prix préférentiels."
                    "\nAbonnement mensuels récurents ou adhésion annuelle."
                    "\nAinsi qu'une badgeuse pour la gestion d'accès d'un co working.")
                config.tva_number = fake.bban()[:20]
                config.siren = fake.siret()[:20]
                config.phone = fake.phone_number()[:20]
                config.email = os.environ['ADMIN_EMAIL']
                config.stripe_mode_test = True
                config.stripe_connect_account_test = os.environ.get('TEST_STRIPE_CONNECT_ACCOUNT')
                config.site_web = "https://tibillet.org"
                config.legal_documents = "https://tibillet.org/cgucgv"
                config.twitter = "https://twitter.com/tibillet"
                config.facebook = "https://facebook.com/tibillet"
                config.instagram = "https://instagram.com/tibillet"
                config.federated_with.add(tenant1)
                config.federated_with.add(tenant2)

                postal_address = PostalAddress.objects.create(
                    street_address=fake.street_address(),
                    address_locality=fake.city(),
                    address_region=fake.region(),
                    postal_code=fake.postcode(),
                    address_country='France',
                    latitude=fake.latitude(),
                    longitude=fake.longitude(),
                    comment=fake.sentence(),
                    is_main=True,
                )
                config.postal_address = postal_address
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
                    name="Intolérance au gluten",
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
                    name=f"Adhésion {tenant.name}",
                    short_description=f"Adhérez à l'association {tenant.name}",
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

                prix_libre, created = Price.objects.get_or_create(
                    product=adhesion_asso,
                    name="Prix libre",
                    short_description="Prix libre",
                    prix='1',
                    free_price=True,
                    subscription_type=Price.YEAR,
                )

                amap, created = Product.objects.get_or_create(
                    name=f"Panier AMAP {tenant.name}",
                    short_description=f"Adhésion au panier de l'AMAP {tenant.name}",
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
                    name=f"Badgeuse Co-Working {tenant.name}",
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
                world, created = Tag.objects.get_or_create(name='World Music')
                gratuit, created = Tag.objects.get_or_create(name='Gratuit')
                entree_libre, created = Tag.objects.get_or_create(name='Entrée libre')

                event_entree_libre, created = Event.objects.get_or_create(
                    name=f"{fake.word().capitalize()} : Entrée libre",
                    datetime=fake.future_datetime('+7d'),
                    short_description="Scène ouverte Rock !",
                    long_description="Un évènement gratuit, ouvert à tous.tes sans réservation."
                                     "\nSeul les artistes annoncés et les descriptions sont affichés.",
                    categorie=Event.CONCERT,
                    postal_address=postal_address,
                )
                event_entree_libre.tag.add(rock)
                event_entree_libre.tag.add(gratuit)
                event_entree_libre.tag.add(entree_libre)

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
                    name=f"{fake.word().capitalize()} : Gratuit avec reservation",
                    datetime=fake.future_datetime('+7d'),
                    jauge_max=200,
                    max_per_user=4,
                    short_description="Attention, places limités, pensez à réserver !",
                    long_description="Un évènement gratuit, avec une jauge maximale de 200 personnes et un nombre de billet limités à 4 par reservation."
                                     "\nBillets non nominatifs.",
                    categorie=Event.CONCERT,
                    postal_address=postal_address,
                )
                event_gratuit_avec_free_resa.products.add(free_resa)

                event_gratuit_avec_free_resa.tag.add(jazz)
                event_gratuit_avec_free_resa.tag.add(gratuit)

                ### PAYANT AVEC PRIX LIBRE ###

                free_price_resa, created = Product.objects.get_or_create(
                    name="Reservation à prix libre",
                    short_description="Reservation à prix libre",
                    categorie_article=Product.BILLET,
                    nominative=False,
                )

                free_price_resa_price, created = Price.objects.get_or_create(
                    name="Prix libre",
                    prix=1,
                    free_price=True,
                    short_description="Prix libre",
                    product=free_price_resa,
                )
                prix_libre, created = Tag.objects.get_or_create(name='Prix libre')

                event_prix_libre, created = Event.objects.get_or_create(
                    name=f"{fake.word().capitalize()} : Entrée a prix libre",
                    datetime=fake.future_datetime('+7d'),
                    jauge_max=200,
                    max_per_user=4,
                    short_description="Attention, places limités, pensez à réserver !",
                    long_description="Un évènement gratuit, avec une jauge maximale de 200 personnes et un nombre de billet limités à 4 par reservation."
                                     "\nBillets non nominatifs.",
                    categorie=Event.CONCERT,
                    postal_address=postal_address,
                )
                event_prix_libre.products.add(free_price_resa)
                event_prix_libre.tag.add(jazz)
                event_prix_libre.tag.add(prix_libre)

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
                    name=f"{fake.word().capitalize()} : Spectacle payant",
                    datetime=fake.future_datetime('+7d'),
                    jauge_max=600,
                    max_per_user=10,
                    short_description="Spectacle payant avec tarif préférentiel pour les adhérants à l'association",
                    long_description="Jauge maximale de 600 personnes et un nombre de billet limités à 10 par reservation."
                                     "\nBillets nominatifs.",
                    categorie=Event.CONCERT,
                    postal_address=postal_address,
                )
                event_payant_nominatif_tarif_asso.products.add(billet)
                event_payant_nominatif_tarif_asso.tag.add(world)


                # TODO: Gratuit mais avec recharge cashless obligatoire
                # TODO: Multi artiste
