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
from BaseBillet.models import Product, OptionGenerale, Price, Configuration, Event, Tag, PostalAddress, FormbricksConfig, FormbricksForms
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
        tenant1 = Client.objects.get(name=sub)
        tenant1.name = "Le Tiers-Lustre"

        tenant1.save()

        # Fabrication d'un deuxième tenant pour de la fédération
        with schema_context('public'):
            name = "Chantefrein"
            domain = os.getenv("DOMAIN")
            tenant, created = Client.objects.get_or_create(
                schema_name=slugify(name),
                name=name,
                on_trial=False,
                categorie=Client.SALLE_SPECTACLE,
            )
            Domain.objects.get_or_create(
                domain=f'{slugify(name)}.{domain}',
                tenant=tenant,
                is_primary=True
            )
            # Sans envoie d'email pour l'instant, on l'envoie quand tout sera bien terminé
            user: TibilletUser = get_or_create_user(os.environ['ADMIN_EMAIL'], send_mail=False)
            user.client_admin.add(tenant)
            user.is_staff = True
            user.save()

        tenant2 = Client.objects.get(name="Chantefrein")

        for tenant in [tenant1, tenant2]:
            with tenant_context(tenant):
                fake = Faker('fr_FR')
                logger.info(f"Start demo_data. Sub : {sub}, tenant : {tenant}")

                ### CONFIGURATION VARIABLE ####

                config = Configuration.get_solo()
                config.organisation = tenant.name
                config.short_description = f"Instance de démonstration  du collectif imaginaire « {tenant.name} »."
                config.long_description = (
                    "Bienvenue sur Lespass, la plateforme en ligne de TiBillet."
                    "\nVous trouverez ici des exemples d'évènements à réserver et d'adhésions à prendre."
                    " Vous pouvez choisir entre tarifs gratuits, payants, en prix libre ou soumis à adhésion."
                    " Les adhésions peuvent être mensuelles ou annuelles, ponctuelles ou réccurentes."
                    "\nEnfin, vous avez en démonstration une badgeuse pour la gestion d'accès d'un espace de co-working.")
                config.tva_number = fake.bban()[:20]
                config.siren = fake.siret()[:20]
                config.phone = fake.phone_number()[:20]
                config.email = os.environ['ADMIN_EMAIL']
                config.stripe_mode_test = True
                config.stripe_connect_account_test = os.environ.get('TEST_STRIPE_CONNECT_ACCOUNT')
                config.stripe_payouts_enabled = True
                config.site_web = "https://tibillet.org"
                config.legal_documents = "https://tibillet.org/cgucgv"
                config.twitter = "https://twitter.com/tibillet"
                config.facebook = "https://facebook.com/tibillet"
                config.instagram = "https://instagram.com/tibillet"
                # config.federated_with.add(tenant1)
                # config.federated_with.add(tenant2)

                postal_address = PostalAddress.objects.create(
                    name="Manapany",
                    street_address=fake.street_address(),
                    address_locality=fake.city(),
                    address_region=fake.region(),
                    postal_code='69100',
                    address_country='FR',
                    latitude=43.90545495459708,
                    longitude=7.532343890994476,
                    comment="Bus 42 et métro : Arrêt D. Adams. Merci d'eteindre votre moteur d'improbabilité infinie.",
                    is_main=True,
                )

                config.postal_address = postal_address
                config.save()


                postal_address_2 = PostalAddress.objects.create(
                    name="Libre Roya",
                    street_address=fake.street_address(),
                    address_locality=fake.city(),
                    address_region=fake.region(),
                    postal_code=fake.postcode(),
                    address_country='France',
                    latitude=-21.37271167192088,
                    longitude=55.58819666101755,
                    comment="Parking sur le col des Aravis. Boisson offerte si vous venez à velo. Paix et prospérité.",
                    is_main=False,
                )


                # Configuration de Formbricks
                formbricks_config = FormbricksConfig.get_solo()
                formbricks_api_key = os.environ.get('TEST_FORMBRICKS_API', '')
                if formbricks_api_key:
                    formbricks_config.set_api_key(formbricks_api_key)
                    formbricks_config.save()


                ### LINK TO FEDOW
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
                    name="Végétarien·ne",
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
                    description="Une table en terrasse",
                )

                interieur, created = OptionGenerale.objects.get_or_create(
                    name="Salle",
                    description="Une table à l'intérieur",
                )

                terasse, created = OptionGenerale.objects.get_or_create(
                    name="Terrasse",
                    description="Une table en terrasse",
                )

                ### MEMBERSHIP ###

                adhesion_asso, created = Product.objects.get_or_create(
                    name=f"Adhésion ({tenant.name})",
                    short_description=f"Adhérez au collectif {tenant.name}",
                    long_description="Vous pouvez prendre une adhésion en une seule fois, ou payer tous les mois.",
                    categorie_article=Product.ADHESION,
                )
                adhesion_asso.option_generale_checkbox.add(option_membre_actif)

                adhesion_asso_annuelle, created = Price.objects.get_or_create(
                    product=adhesion_asso,
                    name="Annuelle",
                    short_description="Adhésion annuelle",
                    prix=20,
                    recurring_payment=False,
                    subscription_type=Price.YEAR,
                )

                adhesion_asso_mensuelle_recurente, created = Price.objects.get_or_create(
                    product=adhesion_asso,
                    name="Mensuelle",
                    short_description="Adhésion mensuelle récurente",
                    prix=2,
                    recurring_payment=True,
                    subscription_type=Price.MONTH,
                )

                prix_libre, created = Price.objects.get_or_create(
                    product=adhesion_asso,
                    name="Prix libre",
                    short_description="Prix libre",
                    prix=1,
                    free_price=True,
                    subscription_type=Price.YEAR,
                )

                amap, created = Product.objects.get_or_create(
                    name=f"Panier AMAP ({tenant.name})",
                    short_description=f"Adhésion au panier de l'AMAP partenaire {tenant.name}",
                    long_description="Association pour le maintien d'une agriculture paysanne. Recevez un panier chaque semaine.",
                    categorie_article=Product.ADHESION,

                )
                amap.option_generale_radio.add(livraison_asso)
                amap.option_generale_radio.add(livraison_maison)

                amap_annuelle, created = Price.objects.get_or_create(
                    product=amap,
                    name="Annuelle",
                    short_description="Adhésion annuelle",
                    prix=400,
                    recurring_payment=False,
                    subscription_type=Price.YEAR,
                )

                amap_mensuelle_recurente, created = Price.objects.get_or_create(
                    product=amap,
                    name="Mensuelle",
                    short_description="Adhésion récurente",
                    prix=40,
                    recurring_payment=True,
                    subscription_type=Price.MONTH,
                )

                ### BADGEUSE ###

                badgeuse_cowork, created = Product.objects.get_or_create(
                    name=f"Badgeuse co-working ({tenant.name})",
                    short_description="Accès à l'espace de co-working.",
                    long_description="Merci de pointer à chaque entrée ET sortie même pour un passage rapide. Les adhérent·es bénéficient de 3h gratuites par semaine.",
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
                rock, created = Tag.objects.get_or_create(name='Rock', color='#3B71CA')
                jazz, created = Tag.objects.get_or_create(name='Jazz', color='#14A44D')
                world, created = Tag.objects.get_or_create(name='World', color='#DC4C64')
                gratuit, created = Tag.objects.get_or_create(name='Gratuit', color='#E4A11B')
                entree_libre, created = Tag.objects.get_or_create(name='Entrée libre', color='#FBFBFB')
                chantiers, created = Tag.objects.get_or_create(name='chantiers', color='#54B4D3')

                event_entree_libre, created = Event.objects.get_or_create(
                    name=f"Scène ouverte : Entrée libre",
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
                    name="Réservation gratuite",
                    short_description="Réservation gratuite",
                    categorie_article=Product.FREERES,
                    nominative=False,
                )

                event_gratuit_avec_free_resa, created = Event.objects.get_or_create(
                    name=f"Disco Caravane : Gratuit avec réservation",
                    datetime=fake.future_datetime('+7d'),
                    jauge_max=200,
                    max_per_user=4,
                    short_description="Attention, places limitées, pensez à réserver !",
                    long_description="Un évènement gratuit, avec une jauge maximale de 200 personnes et un nombre de billets limité à 4 par réservation."
                                     "\nBillets non nominatifs.\nÇa fait pas mal pour une caravane hein ?",
                    categorie=Event.CONCERT,
                    postal_address=postal_address,
                )
                event_gratuit_avec_free_resa.products.add(free_resa)

                event_gratuit_avec_free_resa.tag.add(jazz)
                event_gratuit_avec_free_resa.tag.add(gratuit)

                ### PAYANT AVEC PRIX LIBRE ###

                free_price_resa, created = Product.objects.get_or_create(
                    name="Réservation à prix libre",
                    short_description="Réservation à prix libre",
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
                    name=f"Concert caritatif : Entrée a prix libre",
                    datetime=fake.future_datetime('+7d'),
                    jauge_max=200,
                    max_per_user=4,
                    short_description="Attention, places limitées, pensez à réserver !",
                    long_description="Un évènement à prix libre, avec une jauge maximale de 200 personnes et un nombre de billets limité à 1 par réservation."
                                     "\nBillets non nominatifs.",
                    categorie=Event.CONCERT,
                    postal_address=postal_address_2,
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
                    name="Tarif adhérent",
                    short_description="Tarif adhérent",
                    prix=10,
                    product=billet,
                    adhesion_obligatoire=adhesion_asso,
                )

                event_payant_nominatif_tarif_asso, created = Event.objects.get_or_create(
                    name=f"What the Funk ? Spectacle payant",
                    datetime=fake.future_datetime('+7d'),
                    jauge_max=600,
                    max_per_user=10,
                    short_description="Spectacle payant avec tarif préférentiel pour les adhérents à l'association.",
                    long_description="Jauge maximale de 600 personnes et nombre de billets limité à 10 par réservation."
                                     "\nBillets nominatifs.",
                    categorie=Event.CONCERT,
                )
                event_payant_nominatif_tarif_asso.products.add(billet)
                event_payant_nominatif_tarif_asso.tag.add(world)

                # TODO: Gratuit mais avec recharge cashless obligatoire
                # TODO: Multi artiste

                # Création de l'événement principal "Chantier participatif : besoin de volontaires"
                event_chantier_participatif, created = Event.objects.get_or_create(
                    name="Chantier participatif : besoin de volontaires",
                    datetime=fake.future_datetime('+14d'),
                    short_description="Venez participer à nos chantiers collectifs !",
                    long_description="Nous avons besoin de volontaires pour différentes actions de chantier participatif. "
                                     "Inscrivez-vous aux différentes sessions selon vos disponibilités et compétences.",
                    categorie=Event.CHANTIER,
                    postal_address=postal_address,
                    jauge_max=30,
                    max_per_user=1,
                )
                event_chantier_participatif.tag.add(chantiers)
                event_chantier_participatif.tag.add(gratuit)

                # Création des sous-événements de type Action
                sous_event_jardinage, created = Event.objects.get_or_create(
                    name="Jardinage et plantation",
                    datetime=fake.future_datetime('+15d'),
                    short_description="Aménagement du jardin partagé",
                    long_description="Venez nous aider à planter, désherber et aménager notre jardin partagé. "
                                     "Apportez vos gants et votre bonne humeur !",
                    categorie=Event.ACTION,
                    jauge_max=10,
                    max_per_user=1,
                    parent=event_chantier_participatif,
                )
                sous_event_jardinage.tag.add(chantiers)

                sous_event_peinture, created = Event.objects.get_or_create(
                    name="Peinture et décoration",
                    datetime=fake.future_datetime('+16d'),
                    short_description="Rafraîchissement des murs et décorations",
                    long_description="Session de peinture pour rafraîchir les murs du local. "
                                     "Nous fournirons le matériel, venez avec des vêtements adaptés.",
                    categorie=Event.ACTION,
                    jauge_max=8,
                    max_per_user=1,
                    parent=event_chantier_participatif,
                )
                sous_event_peinture.tag.add(chantiers)

                sous_event_bricolage, created = Event.objects.get_or_create(
                    name="Bricolage et réparations",
                    datetime=fake.future_datetime('+17d'),
                    short_description="Petits travaux de bricolage",
                    long_description="Nous avons besoin de personnes pour effectuer divers travaux de bricolage : "
                                     "réparation de mobilier, installation d'étagères, etc. "
                                     "Si vous avez des compétences en bricolage, rejoignez-nous !",
                    categorie=Event.ACTION,
                    jauge_max=5,
                    max_per_user=1,
                    parent=event_chantier_participatif,
                )
                sous_event_bricolage.tag.add(chantiers)

                ### EVENT WITH FORMBRICKS FORM ###
                if os.environ.get('TEST_FORMBRICKS_ADH_FORM') and os.environ.get('TEST_FORMBRICKS_ADH_FORM'):
                    # Create a product with a Formbricks form
                    formbricks_event_product, created = Product.objects.get_or_create(
                        name="Billet avec formulaire Formbricks",
                        short_description="Démonstration d'un billet avec formulaire personnalisé",
                        long_description="Ce produit est une démonstration de l'intégration avec Formbricks. "
                                        "Après l'achat, un formulaire personnalisé sera présenté pour recueillir des informations supplémentaires.",
                        categorie_article=Product.BILLET,
                        nominative=True,
                    )

                    # Create a price for the product
                    formbricks_event_price, created = Price.objects.get_or_create(
                        name="Tarif standard",
                        short_description="Tarif standard avec formulaire",
                        prix=15,
                        product=formbricks_event_product,
                    )

                    # Create a Formbricks form for the product
                    formbricks_event_form_id = os.environ.get('TEST_FORMBRICKS_EVENT_FORM', '')
                    if formbricks_event_form_id:
                        formbricks_event_form, created = FormbricksForms.objects.get_or_create(
                            environmentId=formbricks_event_form_id,
                            trigger_name="event_booking",
                            product=formbricks_event_product,
                        )

                    # Create an event that uses this product
                    formbricks_tag, created = Tag.objects.get_or_create(name='Formulaire', color='#9C27B0')

                    event_with_formbricks, created = Event.objects.get_or_create(
                        name="Atelier participatif avec formulaire personnalisé",
                        datetime=fake.future_datetime('+10d'),
                        jauge_max=30,
                        max_per_user=2,
                        short_description="Démonstration d'un événement avec formulaire Formbricks",
                        long_description="Cet événement est une démonstration de l'intégration avec Formbricks. "
                                        "Après la réservation, un formulaire personnalisé sera présenté pour recueillir "
                                        "des informations supplémentaires sur vos préférences et besoins.",
                        categorie=Event.CONFERENCE,
                        postal_address=postal_address,
                    )
                    event_with_formbricks.products.add(formbricks_event_product)
                    event_with_formbricks.tag.add(formbricks_tag)

                    ### MEMBERSHIP WITH FORMBRICKS FORM ###

                    # Create a membership product with a Formbricks form
                    formbricks_membership, created = Product.objects.get_or_create(
                        name="Adhésion avec formulaire personnalisé",
                        short_description="Démonstration d'une adhésion avec formulaire Formbricks",
                        long_description="Cette adhésion est une démonstration de l'intégration avec Formbricks. "
                                        "Après l'achat, un formulaire personnalisé sera présenté pour recueillir "
                                        "des informations supplémentaires sur le nouvel adhérent.",
                        categorie_article=Product.ADHESION,
                    )

                    # Create prices for the membership
                    formbricks_membership_annual, created = Price.objects.get_or_create(
                        product=formbricks_membership,
                        name="Annuelle",
                        short_description="Adhésion annuelle avec formulaire",
                        prix=25,
                        recurring_payment=False,
                        subscription_type=Price.YEAR,
                    )

                    formbricks_membership_monthly, created = Price.objects.get_or_create(
                        product=formbricks_membership,
                        name="Mensuelle",
                        short_description="Adhésion mensuelle récurrente avec formulaire",
                        prix=3,
                        recurring_payment=True,
                        subscription_type=Price.MONTH,
                    )

                    # Create a Formbricks form for the membership
                    formbricks_adh_form_id = os.environ.get('TEST_FORMBRICKS_ADH_FORM', '')
                    if formbricks_adh_form_id:
                        formbricks_adh_form, created = FormbricksForms.objects.get_or_create(
                            environmentId=formbricks_adh_form_id,
                            trigger_name="membership_registration",
                            product=formbricks_membership,
                        )
