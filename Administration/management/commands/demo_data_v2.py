import logging
import os
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django_tenants.utils import tenant_context, schema_context
from django.db import connection
from faker import Faker

from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Product, OptionGenerale, Price, Configuration, Event, Tag, PostalAddress, \
    FormbricksConfig, FormbricksForms, ProductFormField, FederatedPlace, Membership
from Customers.models import Client, Domain
from fedow_connect.fedow_api import FedowAPI, AssetFedow
from fedow_connect.models import FedowConfig
from fedow_public.models import AssetFedowPublic
from crowds.models import Initiative, Contribution, Participation, BudgetItem, Vote
from decimal import Decimal

logger = logging.getLogger(__name__)

"""
Récap — Cas d'usage à couvrir pour la démo TiBillet (fixtures JSON)

Évènements (Le Tiers‑Lustre doit contenir l'ensemble des cas) :
- Évènement payant avec tarif préférentiel si adhérent.
- Évènement à prix libre.
- Scène ouverte avec réservation gratuite (FREERES).
- Conférence en entrée libre, sans réservation.
- Journée apprenante avec formulaire dynamique (nom, prénom, téléphone, type de lieu — multi‑sélection, plusieurs cases à cocher, booléen « je veux être bénévole »).
- Chantier participatif avec sous‑évènements de type ACTION.

Adhésions (Le Tiers‑Lustre) :
- Adhésion classique avec deux tarifs (Plein, Solidaire).
- Adhésion à prix libre.
- Abonnement récurrent AMAP (hebdomadaire, mensuel, annuel).
- Adhésion à validation manuelle (non sélective : tous les tarifs nécessitent validation).
- Adhésion danse avec limites par tarif (ex.: 20 places Débutant, 15 places Avancé).

Règles générales :
- Chaque objet (évènement, produit, tarif) devrait idéalement comporter short_description et long_description.
- Ajouter des tags cohérents (type de musique, Entrée libre, Visio, Présentiel, etc.).
- Les clés du JSON correspondent aux champs des modèles et sont utilisées via get_or_create pour assurer l'idempotence.
"""


class Command(BaseCommand):
    def add_arguments(self, parser):
        # Options du script
        parser.add_argument(
            '--flush',
            action='store_true',
            help=(
                "Purge les contenus (évènements, adhésions, initiatives, produits, tarifs, options, fédérations, tags) "
                "des tenants de démo avant réimport. Ne supprime pas les assets ni la configuration."
            ),
        )

    def handle(self, *args, **options):
        # FALC: On va créer des données de démonstration.
        # - On prépare une grande liste d'objets (fixtures) pour 5 tenants.
        # - On crée chaque tenant (Client + Domain) si besoin.
        # - Puis, on ajoute les objets (adresse, adhésions, évènements, tarifs…).
        # - On utilise toujours get_or_create → pas de doublons si on relance.

        # Gros objet JSON de démonstration pour 4 lieux + 1 réseau régional (adhésions uniquement)
        # Cet objet sera utilisé ultérieurement pour des opérations get_or_create idempotentes.
        # Les cas couverts: évènement gratuit sans résa, gratuit avec résa, prix libre, payant nominatif avec tarif adhérent,
        # adhésions prix libre, annuelles et récurrentes, initiatives avec et sans budget participatif.
        fake = Faker('fr_FR')
        fixtures = [
            {
               "name": "Lespass",
               "short_description": f"Instance de démonstration  du collectif imaginaire «Lespass».",
               "long_description": (
                    "Bienvenue sur Lespass, la plateforme en ligne de TiBillet."
                    "\nVous trouverez ici des exemples d'évènements à réserver et d'adhésions à prendre."
                    " Vous pouvez choisir entre tarifs gratuits, payants, en prix libre ou soumis à adhésion."
                    " Les adhésions peuvent être mensuelles ou annuelles, ponctuelles ou réccurentes."
                    "\nEnfin, vous avez en démonstration une badgeuse pour la gestion d'accès d'un espace de co-working."),
               "tva_number": fake.bban()[:20],
               "siren": fake.siret()[:20],
               "phone": fake.phone_number()[:20],
               "email": os.environ['ADMIN_EMAIL'],
               "stripe_mode_test": True,
               "stripe_connect_account_test": os.environ.get('TEST_STRIPE_CONNECT_ACCOUNT'),
               "stripe_payouts_enabled": True,
               "site_web": "https://tibillet.org",
               "legal_documents": "https://tibillet.org/cgucgv",
               "adresse": {
                    "name": "En bas de chez moi",
                    "street_address": "",
                    "address_locality": "",
                    "postal_code": "",
                    "address_country": "",
                    "latitude": "",
                    "longitude": "",
                },
                "events": [
                    {  # Gratuit, entrée libre (aucune réservation)
                        "name": "Conférence : Présenter TiBillet (entrée libre)",
                        "categorie": "CONFERENCE",
                        "short_description": "Entrée libre, sans réservation, paske c'est en visio !",
                        "long_description": "Conférence de présentation de l'outil TiBillet. Entrée libre, pas de réservation nécessaire. Tout les premier lundi de chaque mois sur https://communlundi.tiers-lieux.org/",
                        "tags": ["Entrée libre", "Conférence", "Visio"],
                    },
                    {  # Scène ouverte avec réservation gratuite (FREERES)
                        "name": "Scène ouverte — Viens comme tu es ! (réservation gratuite)",
                        "categorie": "CONCERT",
                        "jauge_max": 120,
                        "max_per_user": 4,
                        "short_description": "Scène ouverte : Viens comme tu es avec ton instrument !",
                        "long_description": "Entrée libre mais avec réservation. 4 places maximum par réservation. Soyez à l'heure, ça se remplit vite !",
                        "tags": ["Scène ouverte", "Gratuit", "Entrée libre", "Rock"],
                        "products": [
                            {
                                "name": "Réservation gratuite",
                                "categorie_article": "FREERES",
                                "nominative": False,
                                "short_description": "Réservez gratuitement vos places",
                                "long_description": "Billets gratuits, réservations recommandées pour fluidifier l'accueil.",
                            }
                        ],
                    },
                    {  # Gratuit mais réservation obligatoire (free reservation)
                        "name": "Disco Caravane — Gratuit avec réservation",
                        "categorie": "CONCERT",
                        "jauge_max": 200,
                        "max_per_user": 4,
                        "short_description": "Gratuit, réservation obligatoire",
                        "long_description": "Soirée Disco Caravane. Réservez vos places (gratuit) pour garantir votre entrée.",
                        "tags": ["Jazz", "Gratuit", "Disco"],
                        "products": [
                            {
                                "name": "Réservation gratuite",
                                "categorie_article": "FREERES",
                                "nominative": False,
                                "short_description": "Billet gratuit",
                                "long_description": "Billet gratuit nominatif non requis.",
                            }
                        ],
                    },
                    {  # Prix libre
                        "name": "Concert caritatif — Entrée à prix libre",
                        "categorie": "CONCERT",
                        "jauge_max": 200,
                        "max_per_user": 4,
                        "short_description": "Entrée à prix libre",
                        "long_description": "Les recettes soutiennent un projet solidaire. Donnez ce que vous pouvez.",
                        "tags": ["Jazz", "Prix libre"],
                        "products": [
                            {
                                "name": "Réservation à prix libre",
                                "categorie_article": "BILLET",
                                "nominative": False,
                                "short_description": "Réservation à prix libre",
                                "long_description": "Vous choisissez le montant (minimum symbolique).",
                                "prices": [
                                    {"name": "Prix libre", "prix": 1, "free_price": True,
                                     "short_description": "Prix libre",
                                     "long_description": "Montant libre fixé par vous lors du paiement."}
                                ],
                            }
                        ],
                    },
                    {  # Payant nominatif avec tarif préférentiel adhérent
                        "name": "What the Funk ? — Spectacle payant",
                        "categorie": "CONCERT",
                        "jauge_max": 600,
                        "max_per_user": 10,
                        "short_description": "Concert payant, tarifs adhérents disponibles",
                        "long_description": "Billets nominatifs. Un tarif préférentiel est proposé aux adhérents à jour de leur cotisation.",
                        "tags": ["World", "Groove"],
                        "products": [
                            {
                                "name": "Billet",
                                "categorie_article": "BILLET",
                                "nominative": True,
                                "short_description": "Billet standard",
                                "long_description": "Accès au concert What the Funk ?",
                                "prices": [
                                    {"name": "Plein tarif", "prix": 20,
                                     "short_description": "Tarif normal"},
                                    {
                                        "name": "Tarif adhérent",
                                        "prix": 10,
                                        "adhesion_obligatoire": "Adhésion Tiers Lustre",
                                        "short_description": "Réservé aux adhérent·es",
                                    },
                                ],
                            }
                        ],
                    },
                    {  # Journée apprenante avec formulaire dynamique
                        "name": "Journée apprenante — Découverte TiBillet",
                        "categorie": "CONFERENCE",
                        "jauge_max": 60,
                        "max_per_user": 2,
                        "short_description": "Atelier découverte avec formulaire d'inscription",
                        "long_description": "Formulaire dynamique: nom, prénom, téléphone, type de lieu (multi), centres d'intérêt (multi) et proposition de bénévolat.",
                        "tags": ["Atelier", "Formation", "Présentiel"],
                        "products": [
                            {
                                "name": "Inscription journée",
                                "categorie_article": "FREERES",
                                "nominative": False,
                                "short_description": "Inscription gratuite",
                                "long_description": "Participation gratuite sur inscription.",
                                "form_fields": [
                                    {"label": "Nom", "field_type": "SHORT_TEXT", "required": True, "order": 1},
                                    {"label": "Prénom", "field_type": "SHORT_TEXT", "required": True, "order": 2},
                                    {"label": "Téléphone", "field_type": "SHORT_TEXT", "required": False, "order": 3, "help_text": "Indiquez un numéro pour vous joindre le jour J."},
                                    {"label": "Type de lieu", "field_type": "MULTI_SELECT", "required": True, "order": 4, "options": ["Tiers-lieu", "MJC", "Bibliothèque", "Fablab", "Autre"]},
                                    {"label": "Centres d'intérêt", "field_type": "MULTI_SELECT", "required": False, "order": 5, "options": ["Programmation", "Billetterie", "Ateliers", "Communauté", "Numérique"]},
                                    {"label": "Je veux être bénévole", "field_type": "BOOLEAN", "required": False, "order": 6},
                                    {"label": "Votre motivation", "field_type": "LONG_TEXT", "required": False, "order": 7, "help_text": "Dites-nous en quelques phrases ce qui vous motive."},
                                    {"label": "Thématique principale", "field_type": "SINGLE_SELECT", "required": True, "order": 8, "options": ["Billetterie", "Adhésions", "Compta", "Animation", "Technique"]},
                                    {"label": "Préférence de contact", "field_type": "RADIO_SELECT", "required": True, "order": 9, "options": ["Email", "Téléphone", "Signal"]},
                                ],
                            }
                        ],
                    },
                    {  # Chantier participatif — sous-évènements d'action
                        "name": "Chantier participatif : besoin de volontaires",
                        "categorie": "CHANTIER",
                        "short_description": "Venez participer à nos chantiers collectifs !",
                        "long_description": "Plusieurs créneaux d'actions (jardinage, peinture, bricolage). Inscription par créneau.",
                        "tags": ["Chantier", "Gratuit", "Présentiel"],
                        "children": [
                            {"name": "Jardinage et plantation", "categorie": "ACTION", "jauge_max": 10},
                            {"name": "Peinture et décoration", "categorie": "ACTION", "jauge_max": 8},
                            {"name": "Bricolage et réparations", "categorie": "ACTION", "jauge_max": 5},
                        ],
                    },
                    {  # Evènements de type réunion pour tester les filtres de fédération
                        "name": "Réunion d'équipe",
                        "categorie": "CONFERENCE",
                        "short_description": "Réunion interne de l'équipe",
                        "long_description": "Point d'équipe mensuel.",
                        "tags": ["Réunion"],
                    },
                    {
                        "name": "Assemblée générale annuelle",
                        "categorie": "CONFERENCE",
                        "short_description": "AG statutaire",
                        "long_description": "Assemblée générale de l'association.",
                        "tags": ["Réunion"],
                    },
                ],
                # Actifs (assets) Fedow à créer/assurer pour ce tenant uniquement si déclarés
                # - MonaLocalim: jeton local fiat (code SSA) utilisé pour récompenser certaines adhésions
                # - MTemps: monnaie temps (code H) pour récompenser le scan de billets bénévole
                "assets": [
                    {"name": "MonaLocalim", "currency_code": "SSA", "category": "TOKEN_LOCAL_FIAT"},
                    {"name": "MTemps", "currency_code": "H", "category": "TIME"},
                ],
                "adhesions": [
                    {  # Adhésion classique plein/solidaire
                        "name": "Adhésion associative Tiers Lustre",
                        "categorie_article": "ADHESION",
                        "short_description": "Adhésion annuelle, tarif solidaire et prix libre !",
                        "long_description": "Plusieurs tarifs sont possible suivant votre bourse.",
                        # FALC: Formulaire simple lié à l'adhésion (2 champs demandés)
                        # - Un booléen: souhaite participer aux chantiers bénévoles
                        # - Un choix multiple: centres d'intérêt
                        "form_fields": [
                            {
                                "label": "je veux participer aux chantiers bénévoles",
                                "field_type": "BOOLEAN",
                                "required": False,
                                "order": 1
                            },
                            {
                                "label": "mes centres d'interet",
                                "field_type": "MULTI_SELECT",
                                "required": False,
                                "order": 2,
                                "options": ["Jardin", "Musique", "Fablab", "Hackerspace"]
                            }
                        ],
                        "prices": [
                            {"name": "Plein tarif", "prix": 30, "subscription_type": "YEAR",
                             "short_description": "Tarif normal"},
                            {"name": "Solidaire", "prix": 10, "subscription_type": "YEAR",
                             "short_description": "Tarif solidaire"},
                            {"name": "Prix libre", "prix": 1, "free_price": True, "subscription_type": "YEAR",
                             "short_description": "Prix libre"},
                        ],
                    },
                    {  # Nouvelle adhésion SSA
                        "name": "Caisse de sécurité sociale alimentaire",
                        "categorie_article": "ADHESION",
                        "short_description": "Souscrivez à la SSA ! Payez selon vos moyens, recevez selon vos besoins.",
                        "long_description": (
                            "Souscrivez à la SSA !\n"
                            "Payez selon vos moyens recevez selon vos besoins…\n"
                            "L'adhésion à la SSA vous donne droit à 100 MonaLocalims (équivalents à 100€) sur votre carte à dépenser chez tous les producteurs et commerces conventionnés. "
                            "Une validation par un.e administrateur.ice est nécessaire."
                        ),
                        "prices": [
                            {
                                "name": "Souscription mensuelle",
                                "short_description": "Prix libre récurrent — engagement 3 mois",
                                "prix": 1,
                                "free_price": True,
                                "recurring_payment": True,
                                "subscription_type": "MONTH",
                                "iteration": 3,
                                "commitment": True,
                                "manual_validation": False,
                                "fedow_reward_enabled": True,
                                "fedow_reward_amount": 100,
                                "fedow_reward_asset_name": "MonaLocalim"
                            }
                        ],
                    },
                    {
                        "name": "Panier Amap",
                        "categorie_article": "ADHESION",
                        "options_radio": ["Livraison à l'asso", "Livraison à la maison"],
                        "short_description": "Abonnement AMAP. Chaque tarif est limité en quantité, soyez les premiers ! Engagement demandée de 6 mois.",
                        "long_description": "Recevez votre panier via l'AMAP partenaire.",
                        "prices": [
                            {"name": "Panier DUO", "prix": 40, "recurring_payment": True, "subscription_type": "MONTH",
                             "short_description": "Panier DUO chaque mois — engagement 6 mois", "iteration": 6, "commitment": True, "stock": 30},
                            {"name": "Panier Famille", "prix": 60, "recurring_payment": True, "subscription_type": "MONTH",
                             "short_description": "Panier chaque mois — engagement 6 mois", "iteration": 6, "commitment": True, "stock": 20},
                            {"name": "Annuelle", "prix": 400, "subscription_type": "YEAR",
                             "short_description": "Engagement annuel", "stock": 50},
                        ],
                    },
                    {  # Adhésion à validation manuelle (non sélective)
                        "name": "Souscription à la coopérative : validation manuelle",
                        "categorie_article": "ADHESION",
                        "short_description": "Devenez sociétaire de la coopérative. Postulez ici, nous vous confirmerons par mail votre adhésion. Un lien de paiement vous sera alors envoyé.",
                        "long_description": "Tous les tarifs nécessitent une validation manuelle avant paiement.",
                        "form_fields": [
                            # FALC: Formulaire d'adhésion pour une coopérative (tous les types inclus)
                            {"label": "Nom légal complet", "field_type": "SHORT_TEXT", "required": True, "order": 1, "help_text": "Indiquez votre nom et prénom, ou la dénomination de la structure."},
                            {"label": "Adresse postale", "field_type": "SHORT_TEXT", "required": True, "order": 2, "help_text": "Rue, code postal et ville."},
                            {"label": "Type de souscripteur", "field_type": "SINGLE_SELECT", "required": True, "order": 3, "options": ["Particulier", "Association", "SCOP", "SCIC", "Entreprise", "Autre"]},
                            {"label": "Domaines d'intérêt dans la coopérative", "field_type": "MULTI_SELECT", "required": False, "order": 4, "options": ["Gouvernance", "Finances", "Animation", "Communication", "Juridique", "Technique"]},
                            {"label": "Préférence de convocation aux AG", "field_type": "RADIO_SELECT", "required": True, "order": 5, "options": ["Email", "Courrier postal"]},
                            {"label": "J'atteste avoir lu et accepte les statuts", "field_type": "BOOLEAN", "required": True, "order": 6, "help_text": "Case obligatoire pour poursuivre."},
                            {"label": "J'accepte de figurer sur le registre des sociétaires", "field_type": "BOOLEAN", "required": False, "order": 7},
                            {"label": "Numéro de pièce d'identité (optionnel)", "field_type": "SHORT_TEXT", "required": False, "order": 8},
                            {"label": "Motivations et projet au sein de la coopérative", "field_type": "LONG_TEXT", "required": False, "order": 9},
                        ],
                        "prices": [
                            {"name": "Souscription structure morale", "prix": 500, "subscription_type": "LIFE", "manual_validation": True,
                             "short_description": "Validation requise"},
                            {"name": "Souscription particulier", "prix": 50, "subscription_type": "LIFE",
                             "manual_validation": True,
                             "short_description": "Validation requise"},
                        ],
                    },
                ],
                "initiatives": [
                    # FALC: Les initiatives ci‑dessous couvrent tous les cas d’usage (LES PASS uniquement)
                    {
                        "name": "Crowdfunding simple : Financer un projet concret : H2G2, la suite !",
                        "short_description": "Un projet classique financé par des dons en €.",
                        "description": "Exemple de financement participatif classique. Franchement celui la il est génial. Si quelqu'un veut bien le lancer dans la vraie vie ... Adapter tout le guide du routard galactique en série ! Ah ! Et on veut la suite aussi de Dirk Gently !",
                        "archived": False,
                        "budget_contributif": False,
                        "adaptative_funding_goal_on_participation": False,
                        "funding_mode": "cascade",
                        "currency": "€",
                        "direct_debit": False,
                        "tags": ["Crowdfunding"],
                        "budget_items" : [
                            {"contributor": "douglas.adams@h2g2.org", "description": "Frais d'auto-stop", "amount" : 15},
                            {"contributor": "thor@dirkgently.org", "description": "Scénario", "amount" : 800},
                            {"contributor": "fondation@h2g2.org", "description": "Script", "amount" : 600},
                            {"contributor": "fondation@h2g2.org", "description": "Tournage", "amount" : 1500},
                        ],
                        "contributions": [
                            {"amount_eur": 1200, "name": "Fondation H2G2"},
                            {"amount_eur": 80, "name": "Douglas Adams"},
                            {"amount_eur": 60, "name": "Arthur Dent"},
                            {"amount_eur": 30, "name": "Ford Perfect"},
                            {"amount_eur": 1200, "name": "Zaphod Beeblebrox"},
                            {"amount_eur": 40, "name": "Tricia Mc Millan"},
                            {"amount_eur": 100, "name": "Marvin"},
                        ]
                    },
                    {
                        "name": "Budget contributif ouvert à tous.tes : Aide nous à construire notre Tiers lieux de rêve !",
                        "short_description": "Budget contributif avec objectif fixe : contributions en Monnaie Temps !",
                        "description": "Objectif de financement qui peut être mouvant suivant les idées de chantier",
                        "vote": False,
                        "archived": False,
                        "budget_contributif": True,
                        "adaptative_funding_goal_on_participation": False,
                        "funding_mode": "cascade",
                        "currency": "MTemps",
                        "direct_debit": False,
                        "tags": ["Difficultée : Intermédiaire"],
                        "budget_items": [
                            {"contributor": "zaphod@h2g2.org", "description": "Aménagement du garage pour le coeur en or", "amount": 10000},
                            {"contributor": "douglas.adams@h2g2.org", "description": "Fyord", "amount": 600},
                            {"contributor": "souris@h2g2.org", "description": "Charpente", "amount": 4000},
                        ],
                        "contributions": [
                            {"amount_eur": 1000, "name": "Collecte en ligne"},
                            {"amount_eur": 1500, "name": "Subvention locale"},
                            {"amount_eur": 25000, "name": "Mécénat"}
                        ],
                        "participations": [
                            {"user_email": f"arthur.dent@h2g2.org", "requested_value": 100, "description": f"Frais de pressing pour robe de chambre", "state": "APPROVED_ADMIN"},
                            {"user_email": f"zaphod@h2g2.org", "requested_value": 1000, "description": f"Décoration : Portrait du président de la galaxie", "state": "REQUESTED"},
                            {"user_email": f"souris@h2g2.org", "requested_value": 4200, "description": f"Construction de Compute-1", "state": "APPROVED_ADMIN"},
                            {"user_email": f"dauphins@h2g2.org", "requested_value": 420, "description": f"Salut, et merci pour le poisson !", "state": "APPROVED_ADMIN"},
                            {"user_email": f"ford@h2g2.org", "requested_value": 200, "description": f"Impression du guide sur papier", "state": "REQUESTED"},
                        ]
                    },
                    {
                        "name": "Idée ! Votez et on le fabrique !",
                        "short_description": "Voici une idée géniale : Un tutoriel pour apprendre à voler en loupant le sol. Votez, proposez des budgets et on s'y met tous si ça prend !",
                        "description": "Cette initiative sert d'exemple pour la collecte d'idées. Les membres votent pour les plus pertinentes. Quand ça prend, on spécifie, on planifie… et on se lance !",
                        "archived": False,
                        "vote": True,
                        "budget_contributif": True,
                        "adaptative_funding_goal_on_participation": True,
                        "funding_mode": "cascade",
                        "currency": "€",
                        "direct_debit": False,
                        "tags": ["Idée : Votez !", "Difficultée : Facile", "Communauté", "Rigolo"],
                        "budget_items": [
                            {"contributor": "arthur.dent@h2g2.org", "description": "La méthode : Louper le sol en une trilogie de 5 volumes", "amount": 10000},
                        ],
                        "votes":[
                            {"user_email": "arthur.dent@h2g2.org"},
                            {"user_email": "fenchurch@h2g2.org"},
                            {"user_email": "dauphins@h2g2.org"},
                            {"user_email": "marvin@h2g2.org"},
                            {"user_email": "alea.dent@h2g2.org"},
                            {"user_email": "tricia@h2g2.org"},
                        ]
                    },
                ],
                # Fédérations: ce lieu affiche des contenus d'autres tenants (avec filtres de tags)
                "federations": [
                    {
                        "tenant": "Chantefrein",
                        "include_tags": [],
                        "exclude_tags": ["Réunion"],
                        "membership_visible": True
                    },
                    {
                        "tenant": "La Maison des Communs",
                        "include_tags": ["Prix libre"],
                        "exclude_tags": ["Réunion"],
                        "membership_visible": True
                    }
                ],
            },
            {
                "name": "Chantefrein",
                "short_description": "Lieu de démo: culture, bricolage et bons moments.",
                "long_description": (
                    "Bienvenue au Chantefrein. Ici on danse, on coud et on apprend. "
                    "Exemples d'évènements payants, gratuits et à prix libre, ainsi que des adhésions simples ou récurrentes."
                ),
                "tva_number": fake.bban()[:20],
                "siren": fake.siret()[:20],
                "phone": fake.phone_number()[:20],
                "email": os.environ.get('ADMIN_EMAIL').replace("@", "+cf@", 1),
                "stripe_mode_test": True,
                "stripe_connect_account_test": None,
                "stripe_payouts_enabled": False,
                "site_web": "https://tibillet.org/lowcow",
                "legal_documents": "https://tibillet.org/cgucgv",
                "adresse": {
                    "name": "La grange conviviale",
                    "street_address": "",
                    "address_locality": "",
                    "postal_code": "",
                    "address_country": "FR",
                    "latitude": "",
                    "longitude": "",
                },
                "events": [
                    {"name": "Bal trad du vendredi", "categorie": "CONCERT", "reservation": "payante",
                     "products": [{"name": "Billet", "categorie_article": "BILLET", "nominative": True,
                                    "prices": [{"name": "Plein tarif", "prix": 12}, {"name": "Réduit", "prix": 8}]}],
                     "tags": ["World"]},
                    {"name": "Atelier couture — prix libre", "categorie": "ATELIER", "reservation": "payante",
                     "products": [{"name": "Réservation à prix libre", "categorie_article": "BILLET",
                                    "nominative": False,
                                    "prices": [{"name": "Prix libre", "prix": 1, "free_price": True}]}],
                     "tags": ["Prix libre"]},
                    {  # Evènements de type réunion pour tester les filtres de fédération
                        "name": "Point Coop' Chantefrein",
                        "categorie": "CONFERENCE",
                        "short_description": "Réunion interne de l'équipe",
                        "long_description": "Point d'équipe mensuel.",
                        "tags": ["Réunion"],
                    },
                    {
                        "name": "AG Ordinaire Chantefrein ",
                        "categorie": "CONFERENCE",
                        "short_description": "AG statutaire",
                        "long_description": "Assemblée générale de l'association.",
                        "tags": ["Réunion"],
                    },

                ],
                "adhesions": [
                    {"name": "Adhésion Chantefrein", "categorie_article": "ADHESION",
                     "prices": [
                         {"name": "Annuelle", "prix": 15, "subscription_type": "YEAR"},
                         {"name": "Mensuelle", "prix": 1.5, "recurring_payment": True, "subscription_type": "MONTH"},
                     ]},
                ],
                "initiatives": [
                    {"name": "Réparer le fournil collectif", "budget_contributif": True, "currency": "€"},
                ],
            },
            {
                "name": "Le Coeur en or",
                "short_description": "Lieu de démo: arts et causeries engagées.",
                "long_description": (
                    "Le Coeur en or propose des scènes ouvertes et des conférences. "
                    "Réservations gratuites, entrées libres et adhésions à prix libre en exemple."
                ),
                "tva_number": fake.bban()[:20],
                "siren": fake.siret()[:20],
                "phone": fake.phone_number()[:20],
                "email": os.environ.get('ADMIN_EMAIL').replace("@", "+co@", 1),
                "stripe_mode_test": True,
                "stripe_connect_account_test": "",
                "stripe_payouts_enabled": True,
                "site_web": "https://tibillet.org/coeur-en-or",
                "legal_documents": "https://tibillet.org/cgucgv",
                "adresse": {
                    "name": "Maison du projet",
                    "street_address": "",
                    "address_locality": "",
                    "postal_code": "",
                    "address_country": "FR",
                    "latitude": "",
                    "longitude": "",
                },
                "events": [
                    {"name": "Scène ouverte acoustique (entrée libre)", "categorie": "CONCERT", "reservation": "aucune",
                     "tags": ["Gratuit", "Entrée libre", "Jazz"]},
                    {"name": "Conférence écologie populaire", "categorie": "CONFERENCE", "reservation": "gratuite",
                     "products": [{"name": "Réservation gratuite", "categorie_article": "FREERES", "nominative": False}]},
                ],
                "adhesions": [
                    {"name": "Adhésion Coeur en or", "categorie_article": "ADHESION",
                     "prices": [
                         {"name": "Annuelle", "prix": 25, "subscription_type": "YEAR"},
                         {"name": "Prix libre", "prix": 1, "free_price": True, "subscription_type": "YEAR"},
                     ]},
                ],
                "initiatives": [
                    {"name": "Fresque murale participative", "budget_contributif": False, "currency": "€"},
                ],
                "federations": [
                    {
                        "tenant": "La Maison des Communs",
                        "include_tags": ["Jazz"],
                        "exclude_tags": ["Réunion"],
                        "membership_visible": False
                    }
                ],
            },
            {
                "name": "La Maison des Communs",
                "short_description": "Lieu de démo: atelier partagé et entraide.",
                "long_description": (
                    "La Maison des Communs met en avant ateliers, fêtes de quartier et adhésions récurrentes. "
                    "Découvrez les réservations à tarif unique et à prix libre."
                ),
                "tva_number": fake.bban()[:20],
                "siren": fake.siret()[:20],
                "phone": fake.phone_number()[:20],
                "email": os.environ.get('ADMIN_EMAIL').replace("@", "+mc@", 1),
                "stripe_mode_test": True,
                "stripe_connect_account_test": "",
                "stripe_payouts_enabled": True,
                "site_web": "https://tibillet.org/maison-des-communs",
                "legal_documents": "https://tibillet.org/cgucgv",
                "adresse": {
                    "name": "L'atelier partagé",
                    "street_address": "",
                    "address_locality": "",
                    "postal_code": "",
                    "address_country": "FR",
                    "latitude": "",
                    "longitude": "",
                },
                "events": [
                    {"name": "Atelier bois débutant", "categorie": "ATELIER", "reservation": "payante",
                     "products": [{"name": "Billet", "categorie_article": "BILLET", "nominative": False,
                                    "prices": [{"name": "Tarif unique", "prix": 15}]}]},
                    {"name": "Fête des voisins — prix libre", "categorie": "FETE", "reservation": "payante",
                     "products": [{"name": "Réservation à prix libre", "categorie_article": "BILLET",
                                    "nominative": False,
                                    "prices": [{"name": "Prix libre", "prix": 1, "free_price": True}]}],
                     "tags": ["Prix libre"]},
                ],
                "adhesions": [
                    {"name": "Adhésion Maison des Communs", "categorie_article": "ADHESION",
                     "prices": [
                         {"name": "Mensuelle", "prix": 3, "recurring_payment": True, "subscription_type": "MONTH"},
                         {"name": "Annuelle", "prix": 30, "subscription_type": "YEAR"},
                     ]},
                ],
                "initiatives": [
                    {"name": "Outils partagés — achat collectif", "budget_contributif": True, "currency": "€"},
                    {"name": "Documentation des savoir-faire", "budget_contributif": False, "currency": "€"},
                ],
                "federations": [
                    {
                        "tenant": "Le Coeur en or",
                        "include_tags": ["Jazz"],
                        "exclude_tags": ["Réunion"],
                        "membership_visible": True
                    }
                ],
            },
            {
                "name": "Le Réseau des lieux en réseau",
                "type": "reseau_regional",
                "short_description": "Réseau régional (démo) — adhésions uniquement.",
                "long_description": (
                    "Ce tenant représente un réseau régional de lieux. "
                    "Il ne contient que des adhésions (individuelles et structures), dont certaines récurrentes."
                ),
                "tva_number": fake.bban()[:20],
                "siren": fake.siret()[:20],
                "phone": fake.phone_number()[:20],
                "email": os.environ.get('ADMIN_EMAIL').replace("@", "+rlr@", 1),
                "stripe_mode_test": True,
                "stripe_connect_account_test": "",
                "stripe_payouts_enabled": True,
                "site_web": "https://tibillet.org/reseau",
                "legal_documents": "https://tibillet.org/cgucgv",
                "adresse": {
                    "name": "Maison du Réseau",
                    "street_address": "",
                    "address_locality": "",
                    "postal_code": "",
                    "address_country": "FR",
                    "latitude": "",
                    "longitude": "",
                },
                # Réseau régional: uniquement des adhésions
                "adhesions": [
                    {"name": "Adhésion réseau — Individuel", "categorie_article": "ADHESION",
                     "prices": [
                         {"name": "Annuelle", "prix": 10, "subscription_type": "YEAR"},
                         {"name": "Prix libre", "prix": 1, "free_price": True, "subscription_type": "YEAR"},
                     ]},
                    {"name": "Adhésion réseau — Structure", "categorie_article": "ADHESION",
                     "prices": [
                         {"name": "Annuelle", "prix": 50, "subscription_type": "YEAR"},
                         {"name": "Mensuelle", "prix": 5, "recurring_payment": True, "subscription_type": "MONTH"},
                     ]},
                ],
                "events": [],
                "initiatives": [
                    {
                        "name": "Financement participatif du réseau",
                        "short_description": "Appel à dons pour soutenir les actions du réseau.",
                        "description": "Soutenez les actions du réseau: mutualisation d'outils, rencontres et accompagnements.",
                        "funding_goal": 2500,
                        "archived": False,
                        "budget_contributif": False,
                        "adaptative_funding_goal_on_participation": False,
                        "funding_mode": "cascade",
                        "currency": "€",
                        "direct_debit": False,
                        "tags": ["Communauté"],
                        "contributions": [
                            {"amount_eur": 300, "name": "Entreprise solidaire"},
                            {"amount_eur": 150, "name": "Don individuel"}
                        ]
                    }
                ],
            },
        ]
        # -----------------------------
        # 0) Option --flush: purge sélective des données existantes des tenants ciblés
        # -----------------------------
        if options.get('flush'):
            try:
                confirmation = input(
                    "Êtes-vous bien sûr de PURGER les évènements, adhésions, initiatives, produits, tarifs, options, fédérations et tags des tenants de démo ? Tapez 'oui' pour confirmer: "
                )
            except Exception:
                confirmation = ''
            if confirmation.strip().lower() not in ['oui', 'yes']:
                self.stdout.write(self.style.WARNING("Opération annulée: aucune donnée supprimée. Relancez avec --flush et confirmez par 'oui'."))
            else:
                # Pour chaque tenant listé dans les fixtures, si le tenant existe, on purge uniquement:
                # - Events (et sous-évènements)
                # - Membership (adhésions des personnes)
                # - Initiatives et leurs objets liés (crowds: votes, participations, contributions, budget items)
                from django.db.models import ProtectedError

                with schema_context('public'):
                    for fx in fixtures:
                        name = fx.get('name')
                        if not name:
                            continue
                        schema = slugify(name)
                        tenant = Client.objects.filter(schema_name=schema).first()
                        if not tenant:
                            logger.info(f"--flush: tenant '{name}' introuvable, rien à purger.")
                            continue
                        try:
                            with tenant_context(tenant):
                                ev_deleted = 0
                                memb_deleted = 0
                                init_deleted = 0
                                price_deleted = 0
                                product_deleted = 0
                                option_deleted = 0
                                fed_deleted = 0
                                tag_deleted = 0

                                # Purge des évènements
                                try:
                                    qs = Event.objects.all()
                                    ev_deleted = qs.count()
                                    if ev_deleted:
                                        qs.delete()
                                except Exception as e:
                                    logger.warning(f"--flush {tenant.name}: erreur lors de la suppression des évènements: {e}")

                                # Purge des adhésions (instances), pas des produits/prix
                                try:
                                    qs = Membership.objects.all()
                                    memb_deleted = qs.count()
                                    if memb_deleted:
                                        qs.delete()
                                except Exception as e:
                                    logger.warning(f"--flush {tenant.name}: erreur lors de la suppression des adhésions: {e}")

                                # Purge des initiatives et des objets crowds associés
                                try:
                                    # Supprimer d'abord les objets enfants pour éviter des ProtectedError éventuelles
                                    Vote.objects.all().delete()
                                    Participation.objects.all().delete()
                                    BudgetItem.objects.all().delete()
                                    Contribution.objects.all().delete()
                                    init_deleted = Initiative.objects.count()
                                    if init_deleted:
                                        Initiative.objects.all().delete()
                                except ProtectedError as e:
                                    logger.warning(f"--flush {tenant.name}: contrainte de protection lors de la purge des initiatives: {e}")
                                except Exception as e:
                                    logger.warning(f"--flush {tenant.name}: erreur lors de la suppression des initiatives: {e}")

                                # Purge des tarifs (Price) puis des produits (Product)
                                try:
                                    qs = Price.objects.all()
                                    price_deleted = qs.count()
                                    if price_deleted:
                                        qs.delete()
                                except Exception as e:
                                    logger.warning(f"--flush {tenant.name}: erreur lors de la suppression des tarifs (Price): {e}")

                                try:
                                    qs = Product.objects.all()
                                    product_deleted = qs.count()
                                    if product_deleted:
                                        qs.delete()
                                except Exception as e:
                                    logger.warning(f"--flush {tenant.name}: erreur lors de la suppression des produits (Product): {e}")

                                # Purge des options générales
                                try:
                                    qs = OptionGenerale.objects.all()
                                    option_deleted = qs.count()
                                    if option_deleted:
                                        qs.delete()
                                except Exception as e:
                                    logger.warning(f"--flush {tenant.name}: erreur lors de la suppression des options (OptionGenerale): {e}")

                                # Purge des fédérations (puis tags)
                                try:
                                    qs = FederatedPlace.objects.all()
                                    fed_deleted = qs.count()
                                    if fed_deleted:
                                        qs.delete()
                                except Exception as e:
                                    logger.warning(f"--flush {tenant.name}: erreur lors de la suppression des fédérations (FederatedPlace): {e}")

                                try:
                                    qs = Tag.objects.all()
                                    tag_deleted = qs.count()
                                    if tag_deleted:
                                        qs.delete()
                                except Exception as e:
                                    logger.warning(f"--flush {tenant.name}: erreur lors de la suppression des tags: {e}")

                                logger.info(
                                    f"--flush {tenant.name}: évènements supprimés={ev_deleted}, adhésions supprimées={memb_deleted}, "
                                    f"initiatives supprimées={init_deleted}, tarifs supprimés={price_deleted}, produits supprimés={product_deleted}, "
                                    f"options supprimées={option_deleted}, fédérations supprimées={fed_deleted}, tags supprimés={tag_deleted}"
                                )
                        except Exception as e:
                            logger.error(f"--flush: échec de purge pour '{name}': {e}")

                self.stdout.write(self.style.SUCCESS("Purge sélective terminée. Réimport en cours…"))

        # -----------------------------
        # 1) Création des tenants (public)
        # -----------------------------
        # FALC: On crée 1 tenant par lieu. On définit aussi son sous-domaine.
        from django.utils import timezone

        def map_event_categorie(label: str):
            label = (label or '').upper()
            try:
                if label == 'CONCERT':
                    return Event.CONCERT
                if hasattr(Event, 'ATELIER') and label == 'ATELIER':
                    return getattr(Event, 'ATELIER')
                if hasattr(Event, 'CHANTIER') and label == 'CHANTIER':
                    return getattr(Event, 'CHANTIER')
                if hasattr(Event, 'ACTION') and label == 'ACTION':
                    return getattr(Event, 'ACTION')
                if hasattr(Event, 'FETE') and label == 'FETE':
                    return getattr(Event, 'FETE')
                if hasattr(Event, 'CONFERENCE') and label == 'CONFERENCE':
                    return getattr(Event, 'CONFERENCE')
            except Exception:
                pass
            return Event.CONCERT

        def map_product_categorie(label: str):
            label = (label or '').upper()
            return {
                'BILLET': Product.BILLET,
                'FREERES': Product.FREERES,
                'ADHESION': Product.ADHESION,
                'BADGE': Product.BADGE,
            }.get(label, Product.NONE)

        def map_form_field_type(label: str):
            if not label:
                return ProductFormField.FieldType.SHORT_TEXT
            m = {
                'SHORT_TEXT': ProductFormField.FieldType.SHORT_TEXT,
                'LONG_TEXT': ProductFormField.FieldType.LONG_TEXT,
                'SINGLE_SELECT': ProductFormField.FieldType.SINGLE_SELECT,
                'RADIO_SELECT': ProductFormField.FieldType.RADIO_SELECT,
                'MULTI_SELECT': ProductFormField.FieldType.MULTI_SELECT,
                'BOOLEAN': ProductFormField.FieldType.BOOLEAN,
            }
            return m.get(label.upper(), ProductFormField.FieldType.SHORT_TEXT)

        # Palette Material Design (classiques) — couleurs lisibles
        MATERIAL_COLORS = [
            # Reds / Pinks
            "#F44336", "#E91E63", "#FF5252", "#FF4081",
            # Purples / Deep Purples
            "#9C27B0", "#673AB7", "#BA68C8", "#9575CD",
            # Blues / Light Blues / Cyan
            "#3F51B5", "#2196F3", "#03A9F4", "#00BCD4", "#64B5F6", "#4DD0E1",
            # Teal / Green / Light Green
            "#009688", "#4CAF50", "#8BC34A", "#26A69A", "#66BB6A", "#9CCC65",
            # Lime / Amber / Orange / Deep Orange
            "#CDDC39", "#FFC107", "#FF9800", "#FF5722", "#FFD54F", "#FFA726", "#FF7043",
            # Brown / Blue Grey / Grey
            "#795548", "#607D8B", "#9E9E9E",
        ]

        def random_material_color() -> str:
            return random.choice(MATERIAL_COLORS)

        def ensure_tag(name: str):
            if not name:
                return None
            # FALC: On crée le tag s'il n'existe pas. On lui donne une couleur aléatoire (palette Material Design).
            t, created = Tag.objects.get_or_create(
                name=name,
                defaults={"color": random_material_color()},
            )
            # Si le tag existait mais sans couleur, on lui en assigne une maintenant (idempotent sinon).
            if not getattr(t, "color", None):
                t.color = random_material_color()
                try:
                    t.save(update_fields=["color"])
                except Exception:
                    # Si le modèle Tag n'a pas de champ color dans certains environnements, on ignore gentiment.
                    pass
            return t

        def ensure_option(name: str):
            if not name:
                return None
            opt, _ = OptionGenerale.objects.get_or_create(name=name)
            return opt

        def map_participation_state(label: str) -> str:
            """Mappe une chaîne vers une constante de Participation.State."""
            if not label:
                return Participation.State.APPROVED_ADMIN
            u = label.upper()
            mapping = {
                'REQUESTED': Participation.State.REQUESTED,
                'APPROVED_ADMIN': Participation.State.APPROVED_ADMIN,
                'COMPLETED_USER': Participation.State.COMPLETED_USER,
                'VALIDATED_ADMIN': Participation.State.VALIDATED_ADMIN,
                # Les anciennes fixtures pouvaient contenir REJECTED_ADMIN
                # Le modèle n'expose que "REJECTED"
                'REJECTED_ADMIN': Participation.State.REJECTED,
                'REJECTED': Participation.State.REJECTED,
            }
            return mapping.get(u, Participation.State.APPROVED_ADMIN)

        created_tenants: list[Client] = []
        with schema_context('public'):
            domain_base = os.getenv("DOMAIN", "example.org")

            for fx in fixtures:
                name = fx.get('name')
                admin_email = fx.get('email')

                if not name:
                    continue

                schema = slugify(name)
                # Étape 1: création/maj du tenant sans auto_create_schema
                tenant = Client.objects.filter(schema_name=schema).first()
                if not tenant:
                    tenant = Client(
                        schema_name=schema,
                        name=name,
                        on_trial=False,
                        categorie=Client.SALLE_SPECTACLE,
                    )
                    tenant.auto_create_schema = False
                    tenant.save()
                else:
                    # Harmoniser les champs principaux si le tenant existait déjà
                    updated = False
                    if tenant.name != name:
                        tenant.name = name
                        updated = True
                    if tenant.on_trial:
                        tenant.on_trial = False
                        updated = True
                    if tenant.categorie != Client.SALLE_SPECTACLE:
                        tenant.categorie = Client.SALLE_SPECTACLE
                        updated = True
                    if updated:
                        tenant.save()

                # Création idempotente du schéma via SQL (même philosophie que cron_morning)
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}";')
                except Exception as e:
                    logger.warning(f"Impossible de créer le schéma '{schema}' pour le tenant {name}: {e}")
                    raise ValueError(f"Impossible de créer le schéma '{schema}' pour le tenant {name}: {e}")

                # Domaine principal idempotent et rattaché au tenant
                try:
                    domain_str = f"{schema}.{domain_base}"
                    domain_obj, _ = Domain.objects.get_or_create(
                        domain=domain_str,
                        tenant=tenant,
                        defaults=dict(is_primary=True)
                    )
                    if not getattr(domain_obj, 'is_primary', False):
                        domain_obj.is_primary = True
                        try:
                            domain_obj.save(update_fields=['is_primary'])
                        except Exception:
                            domain_obj.save()
                except Exception as e:
                    logger.warning(f"Impossible d'assurer le domaine principal pour {name}: {e}")


                created_tenants.append(tenant)

        # -----------------------------
        # 1.b) Migrations des tenants via subprocess (multiprocessing)
        # -----------------------------
        try:
            import subprocess, sys
            logger.info("Lancement des migrations des tenants (multiprocessing)...")
            # Ne pas capturer stdout/stderr pour laisser la sortie s'afficher dans le terminal
            subprocess.run(
                [sys.executable, "manage.py", "migrate_schemas", "--executor=multiprocessing"],
                check=True,
            )
            logger.info("Migrations terminées.")
        except subprocess.CalledProcessError as e:
            logger.error(
                "Erreur de migration (return code: %s). Voir la sortie ci-dessus pour les détails.",
                e.returncode,
            )
            raise e

        # -----------------------------
        # 2) Remplissage des données par tenant
        # -----------------------------
        logger.info(f"created_tenants : {created_tenants}")
        for tenant in created_tenants:
            with (tenant_context(tenant)):
                logger.info(f"\nSeed démo pour le tenant: {tenant.name}\n")
                # Adresse principale (optionnelle)
                fx = next((f for f in fixtures if f.get('name') == tenant.name), None)
                if not fx:
                    continue

                # FALC: On ajoute l'admin comme gestionnaire du tenant.
                try:
                    admin_user: TibilletUser = get_or_create_user(fx.get('email'), send_mail=False)
                    admin_user.client_admin.add(tenant)
                    admin_user.is_staff = True
                    admin_user.save()
                except Exception as e:
                    logger.error(f"Impossible d'ajouter l'admin au tenant {name}: {e}")
                    raise e


                addr_data = fx.get('adresse') or {}
                addr_obj = None
                if addr_data:
                    addr_defaults = {
                        'street_address': addr_data.get('street_address') or '',
                        'address_locality': addr_data.get('address_locality') or '',
                        'address_region': addr_data.get('address_region') if 'address_region' in addr_data else None,
                        'postal_code': addr_data.get('postal_code') or '',
                        'address_country': addr_data.get('address_country') or 'FR',
                        'latitude': addr_data.get('latitude') or None,
                        'longitude': addr_data.get('longitude') or None,
                        'is_main': True,
                    }
                    addr_obj, _ = PostalAddress.objects.get_or_create(
                        name=addr_data.get('name') or f"Adresse {tenant.name}",
                        defaults=addr_defaults,
                    )

                # -----------------------------
                # Configuration du tenant
                # -----------------------------
                # FALC: On remplit les infos de configuration (texte d'accueil, TVA, SIREN, contact, Stripe).
                try:
                    config = Configuration.get_solo()
                    config.organisation = tenant.name
                    # Champs texte d'accueil
                    config.short_description = fx.get('short_description')
                    config.long_description = fx.get('long_description')
                    # Coordonnées et identifiants
                    config.tva_number = fx.get('tva_number')
                    config.siren = fx.get('siren')
                    config.phone = fx.get('phone')

                    config.email = admin_user.email

                    # Liens publics
                    config.site_web = fx.get('site_web')
                    config.legal_documents = fx.get('legal_documents')
                    # Stripe (mode test pour la démo)
                    config.stripe_mode_test = bool(fx.get('stripe_mode_test'))
                    config.stripe_connect_account_test = fx.get('stripe_connect_account_test')
                    config.stripe_payouts_enabled = bool(fx.get('stripe_payouts_enabled'))

                    # Adresse principale liée à la config
                    if addr_obj:
                        config.postal_address = addr_obj
                    config.save()

                except Exception as e:
                    logger.warning(f"Impossible de configurer Configuration pour {tenant.name}: {e}")

                FedowAPI()
                if not FedowConfig.get_solo().can_fedow():
                    raise Exception('Erreur on install : can_fedow = False')


                # Actifs Fedow (création sur demande seulement)
                def map_asset_category(cat: str):
                    c = (cat or '').upper()
                    try:
                        if c == 'TOKEN_LOCAL_FIAT':
                            return AssetFedowPublic.TOKEN_LOCAL_FIAT
                        if c == 'TIME':
                            return AssetFedowPublic.TIME
                        if hasattr(AssetFedowPublic, c):
                            return getattr(AssetFedowPublic, c)
                    except Exception:
                        pass
                    return AssetFedowPublic.TOKEN_LOCAL_FIAT

                assets_by_name: dict[str, AssetFedowPublic] = {}
                try:
                    declared_assets = fx.get('assets', []) or []
                except Exception:
                    declared_assets = []
                if declared_assets:
                    try:
                        fedow_config = FedowConfig.get_solo()
                        fedow_asset = AssetFedow(fedow_config=fedow_config)
                        for a in declared_assets:
                            try:
                                payload = AssetFedowPublic(
                                    name=a.get('name'),
                                    currency_code=a.get('currency_code'),
                                    category=map_asset_category(a.get('category')),
                                )
                                created = fedow_asset.get_or_create_token_asset(payload)
                                obj = AssetFedowPublic.objects.filter(uuid=created.get('uuid')).first()
                                if obj:
                                    assets_by_name[obj.name] = obj
                            except Exception as e:
                                logger.warning(f"Asset Fedow non créé/assuré pour '{tenant.name}': {e}")
                    except Exception as e:
                        logger.warning(f"Impossible d'initialiser les assets Fedow pour {tenant.name}: {e}")

                # Adhésions (produits)
                for adh in fx.get('adhesions', []) or []:
                    prod, _ = Product.objects.get_or_create(
                        name=adh['name'],
                        defaults={
                            'categorie_article': map_product_categorie(adh.get('categorie_article') or 'ADHESION'),
                            'short_description': adh.get('short_description') or '',
                            'long_description': adh.get('long_description') or '',
                        }
                    )
                    # Options (checkbox)
                    for opt_name in adh.get('options', []) or []:
                        opt = ensure_option(opt_name)
                        if opt:
                            prod.option_generale_checkbox.add(opt)
                    # Options (radio)
                    for opt_name in adh.get('options_radio', []) or []:
                        opt = ensure_option(opt_name)
                        if opt:
                            prod.option_generale_radio.add(opt)
                    # FALC: Champs de formulaire dynamiques au niveau de l'adhésion (si fournis dans la fixture)
                    for ff in adh.get('form_fields', []) or []:
                        try:
                            ProductFormField.objects.get_or_create(
                                product=prod,
                                label=ff.get('label') or 'Champ',
                                defaults={
                                    'field_type': map_form_field_type(ff.get('field_type')),
                                    'required': bool(ff.get('required')),
                                    'order': ff.get('order') or 0,
                                    'help_text': ff.get('help_text'),
                                    'options': ff.get('options'),
                                }
                            )
                        except Exception as e:
                            logger.warning(f"Impossible de créer ProductFormField pour l'adhésion '{prod.name}': {e}")
                    # Tarifs
                    for pr in adh.get('prices', []) or []:
                        sub_label = (pr.get('subscription_type') or 'YEAR').upper()
                        sub_value = getattr(Price, sub_label, Price.YEAR)
                        # Prépare les champs Fedow éventuels
                        fedow_defaults = {}
                        try:
                            if pr.get('fedow_reward_enabled'):
                                fedow_defaults['fedow_reward_enabled'] = True
                                fedow_defaults['fedow_reward_amount'] = pr.get('fedow_reward_amount')
                                # Priorité: uuid direct, sinon par nom, sinon asset local par défaut
                                asset_uuid = pr.get('fedow_reward_asset')
                                asset_name = pr.get('fedow_reward_asset_name')
                                asset_obj = None
                                if asset_uuid:
                                    asset_obj = AssetFedowPublic.objects.filter(uuid=asset_uuid).first()
                                    if not asset_obj:
                                        logger.warning(f"Asset UUID '{asset_uuid}' introuvable pour le tenant {tenant.name}. Récompense ignorée.")
                                if not asset_obj and asset_name:
                                    # Cherche dans la base du tenant, sinon dans les assets déclarés
                                    asset_obj = AssetFedowPublic.objects.filter(name=asset_name).first() or assets_by_name.get(asset_name)
                                if asset_obj:
                                    fedow_defaults['fedow_reward_asset'] = asset_obj
                                else:
                                    logger.info(f"Aucun asset Fedow lié pour le tarif '{pr.get('name')}' (produit '{prod.name}') — définissez 'fedow_reward_asset' ou 'fedow_reward_asset_name' et déclarez l'asset dans le JSON.")
                        except Exception as e:
                            logger.warning(f"Impossible de traiter la récompense Fedow pour '{adh.get('name')}': {e}")

                        price_obj, created_price = Price.objects.get_or_create(
                            product=prod,
                            name=pr['name'],
                            defaults={
                                'prix': pr.get('prix', 0),
                                'short_description': pr.get('short_description') or '',
                                'long_description': pr.get('long_description') or '',
                                'stock': pr.get('stock'),
                                'manual_validation': bool(pr.get('manual_validation')),
                                'max_per_user': pr.get('max_per_user'),
                                'iteration': pr.get('iteration'),
                                'commitment': bool(pr.get('commitment')),
                                'recurring_payment': bool(pr.get('recurring_payment')),
                                'subscription_type': sub_value,
                                'free_price': bool(pr.get('free_price')),
                                **fedow_defaults,
                            }
                        )
                        # FALC: Vérification simple — si la fixture demande LIFE, on log l'état réel en base
                        if sub_label == 'LIFE':
                            try:
                                logger.info(
                                    f"Tarif LIFE détecté pour '{prod.name}' → '{price_obj.name}' (créé={created_price}). "
                                    f"Valeur enregistrée: subscription_type='{price_obj.subscription_type}' (attendu='{Price.LIFE}')"
                                )
                            except Exception:
                                pass

                # Évènements
                for ev in fx.get('events', []) or []:
                    # FALC: Date aléatoire dans le futur (entre +6 et +18 mois)
                    try:
                        when = fake.date_time_between(
                            start_date="+180d",
                            end_date="+540d",
                            tzinfo=timezone.get_current_timezone(),
                        )
                    except Exception:
                        # Secours: +200 jours
                        when = timezone.now() + timedelta(days=200)
                    event_obj, created_event = Event.objects.get_or_create(
                        name=ev['name'],
                        defaults={
                            'datetime': when,
                            'categorie': map_event_categorie(ev.get('categorie') or 'CONCERT'),
                            'postal_address': addr_obj,
                            'jauge_max': ev.get('jauge_max') or 50,
                            'max_per_user': ev.get('max_per_user') or 10,
                            'short_description': ev.get('short_description') or '',
                            'long_description': ev.get('long_description') or '',
                        }
                    )

                    for tag_name in ev.get('tags', []) or []:
                        tag = ensure_tag(tag_name)
                        if tag:
                            event_obj.tag.add(tag)

                    # FALC: Pour l'évènement Chantier participatif, on ajoute une mention de récompense en monnaie temps
                    # et on s'assure que le tag « Monnaie temps » est présent.
                    if ev.get('name') == "Chantier participatif : besoin de volontaires":
                        bonus_text = (
                            "\n\nRécompense en monnaie temps :\n"
                            "Inscrivez‑vous aux missions bénévoles et recevez de la monnaie temps sur votre portefeuille TiBillet.\n"
                            "Dépensez cette monnaie temps dans le FabLab', à l'espace coworking ou réservez un atelier musique."
                        )
                        try:
                            new_ld = (event_obj.long_description or "")
                            if "monnaie temps".lower() not in new_ld.lower():
                                new_ld = (ev.get('long_description') or new_ld or "") + bonus_text
                                event_obj.long_description = new_ld
                                event_obj.save(update_fields=['long_description'])
                        except Exception:
                            pass
                        tag_mt = ensure_tag("Monnaie temps")
                        if tag_mt:
                            event_obj.tag.add(tag_mt)

                    # Produits liés à l'évènement
                    for prod_def in ev.get('products', []) or []:
                        p, _ = Product.objects.get_or_create(
                            name=prod_def['name'],
                            defaults={
                                'categorie_article': map_product_categorie(prod_def.get('categorie_article')),
                                'nominative': bool(prod_def.get('nominative')),
                                'short_description': prod_def.get('short_description') or '',
                                'long_description': prod_def.get('long_description') or '',
                            }
                        )
                        # Tarifs du produit
                        for pr in prod_def.get('prices', []) or []:
                            defaults = {
                                'prix': pr.get('prix', 0),
                                'free_price': bool(pr.get('free_price')),
                                'short_description': pr.get('short_description') or '',
                                'long_description': pr.get('long_description') or '',
                                'stock': pr.get('stock'),
                                'manual_validation': bool(pr.get('manual_validation')),
                                'max_per_user': pr.get('max_per_user'),
                                'iteration': pr.get('iteration'),
                                'commitment': bool(pr.get('commitment')),
                                'recurring_payment': bool(pr.get('recurring_payment')),
                                'subscription_type': getattr(Price, (pr.get('subscription_type') or 'NA').upper(), Price.NA),
                            }
                            adhesion_name = pr.get('adhesion_obligatoire')
                            if adhesion_name:
                                try:
                                    adhesion_prod = Product.objects.get(name=adhesion_name)
                                    defaults['adhesion_obligatoire'] = adhesion_prod
                                except Product.DoesNotExist:
                                    logger.warning(f"Adhésion requise '{adhesion_name}' introuvable pour '{p.name}'.")
                            Price.objects.get_or_create(
                                product=p,
                                name=pr['name'],
                                defaults=defaults,
                            )
                        event_obj.products.add(p)

                        # Champs de formulaire optionnels
                        for ff in prod_def.get('form_fields', []) or []:
                            try:
                                ProductFormField.objects.get_or_create(
                                    product=p,
                                    label=ff.get('label') or 'Champ',
                                    defaults={
                                        'field_type': map_form_field_type(ff.get('field_type')),
                                        'required': bool(ff.get('required')),
                                        'order': ff.get('order') or 0,
                                        'help_text': ff.get('help_text'),
                                        'options': ff.get('options'),
                                    }
                                )
                            except Exception as e:
                                logger.warning(f"Impossible de créer ProductFormField pour '{p.name}': {e}")

                    # Sous-évènements (actions) avec parent
                    for child in ev.get('children', []) or []:
                        # FALC: Chaque sous‑évènement se place après le parent, avec un petit décalage aléatoire
                        child_when = when + timedelta(days=random.randint(0, 14), hours=random.randint(1, 6))
                        child_event, _ = Event.objects.get_or_create(
                            name=child['name'],
                            defaults={
                                'datetime': child_when,
                                'categorie': map_event_categorie(child.get('categorie') or 'ACTION'),
                                'postal_address': addr_obj,
                                'jauge_max': child.get('jauge_max') or 10,
                                'max_per_user': child.get('max_per_user') or 1,
                                'parent': event_obj,
                            }
                        )

                        # FALC: Pour les sous‑évènements d'action, on crée un produit de réservation gratuite
                        # et on active une récompense de monnaie temps au scan du billet.
                        try:
                            action_prod, _ = Product.objects.get_or_create(
                                name=f"Inscription bénévolat — {child['name']}",
                                defaults={
                                    'categorie_article': Product.FREERES,
                                    'nominative': False,
                                    'short_description': "Inscription gratuite pour cette action",
                                    'long_description': "Votre aide est précieuse ! Une petite récompense en monnaie temps vous sera créditée lors du scan de votre billet.",
                                }
                            )
                            # Lier le produit à l'évènement enfant
                            child_event.products.add(action_prod)

                            # Récupère/crée le tarif gratuit (post_save crée normalement un 0€)
                            price = Price.objects.filter(product=action_prod).order_by('order').first()
                            if not price:
                                price, _ = Price.objects.get_or_create(
                                    product=action_prod,
                                    name="Tarif gratuit",
                                    defaults={'prix': 0}
                                )
                            # Activer la récompense au scan
                            updated_fields = []
                            if not price.reward_on_ticket_scanned:
                                price.reward_on_ticket_scanned = True
                                updated_fields.append('reward_on_ticket_scanned')
                            # Utiliser l'asset de type TIME uniquement s'il est déclaré (ex: "MTemps")
                            time_asset = assets_by_name.get('MTemps')
                            if time_asset and price.fedow_reward_asset_id != getattr(time_asset, 'uuid', None):
                                price.fedow_reward_asset = time_asset
                                updated_fields.append('fedow_reward_asset')
                            # Montant symbolique par scan (1 unité de temps)
                            if price.fedow_reward_amount != 1:
                                price.fedow_reward_amount = 1
                                updated_fields.append('fedow_reward_amount')
                            if updated_fields:
                                try:
                                    price.save(update_fields=updated_fields)
                                except Exception:
                                    price.save()
                        except Exception as e:
                            logger.warning(f"Impossible de configurer la récompense monnaie temps pour '{child.get('name')}' : {e}\n")

                logger.info(f"Données importées pour {tenant.name} (idempotent)")

                # -----------------------------
                # Initiatives (crowds) — import depuis les fixtures
                # -----------------------------
                # FALC: On intègre les initiatives ici pour centraliser toutes les données démo dans ce JSON.
                inits = fx.get('initiatives', []) or []
                if inits:
                    # Préparer des tags utiles (couleurs déjà gérées par ensure_tag)
                    admin_email_env = config.email

                    for init in inits:
                        # Préparer une variable d'initiative hors try pour éviter UnboundLocalError en cas d'échec
                        initiative_obj = None
                        try:
                            name = init.get('name')
                            if not name:
                                continue
                            # funding_goal (en unités) peut exister dans les fixtures uniquement
                            # Il n'est plus stocké sur le modèle. On le conserve pour éventuellement
                            # générer des lignes budgétaires par défaut si aucune n'est fournie.
                            currency = init.get('currency') or '€'
                            goal_units = init.get('funding_goal') or 0

                            initiative_obj, _ = Initiative.objects.get_or_create(
                                name=name,
                                defaults=dict(
                                    short_description=init.get('short_description') or '',
                                    description=init.get('description') or '',
                                    archived=bool(init.get('archived', False)),
                                    vote=bool(init.get('vote', False)),
                                    budget_contributif=bool(init.get('budget_contributif', False)),
                                    adaptative_funding_goal_on_participation=bool(init.get('adaptative_funding_goal_on_participation', False)),
                                    funding_mode=init.get('funding_mode') or 'cascade',
                                    currency=currency,
                                    direct_debit=bool(init.get('direct_debit', False)),
                                )
                            )
                            # Mise à jour minimale si l'objet existait déjà (idempotent + refresh)
                            fields_to_update = []
                            for fld, fxkey, transform in [
                                ('short_description', 'short_description', str),
                                ('description', 'description', str),
                                ('currency', 'currency', str),
                            ]:
                                val = init.get(fxkey)
                                if val is not None and getattr(initiative_obj, fld) != transform(val):
                                    setattr(initiative_obj, fld, transform(val))
                                    fields_to_update.append(fld)
                            for bfield in ['archived', 'budget_contributif', 'adaptative_funding_goal_on_participation', 'direct_debit']:
                                if bfield in init and getattr(initiative_obj, bfield) != bool(init.get(bfield)):
                                    setattr(initiative_obj, bfield, bool(init.get(bfield)))
                                    fields_to_update.append(bfield)
                            if 'funding_mode' in init and initiative_obj.funding_mode != init.get('funding_mode'):
                                initiative_obj.funding_mode = init.get('funding_mode')
                                fields_to_update.append('funding_mode')
                            if fields_to_update:
                                initiative_obj.save(update_fields=fields_to_update)

                            # Tags
                            for tag_name in init.get('tags', []) or []:
                                t = ensure_tag(tag_name)
                                if t:
                                    initiative_obj.tags.add(t)

                            # Lier un asset (ex: monnaie temps) si demandé
                            asset_name = init.get('asset_name')
                            if asset_name:
                                try:
                                    asset_obj = AssetFedowPublic.objects.filter(name=asset_name).first()
                                    if asset_obj and getattr(initiative_obj, 'asset_id', None) != asset_obj.uuid:
                                        initiative_obj.asset = asset_obj
                                        initiative_obj.save(update_fields=['asset'])
                                except Exception as e:
                                    logger.warning(f"Impossible de lier l'asset '{asset_name}' à l'initiative '{name}': {e}")

                            # -----------------------------
                            # Lignes budgétaires (BudgetItem)
                            # -----------------------------
                            # Nouveau: l'objectif total affiché provient de la somme des BudgetItem approuvés.
                            # Le JSON de démo peut fournir init['budget_items'] comme liste de dicts:
                            #   { description, amount_eur, state(optional: requested/approved/rejected),
                            #     contributor_email(optional), validator_email(optional) }
                            try:
                                budget_items = init.get('budget_items') or []
                            except Exception:
                                budget_items = []

                            # Helper pour récupérer un utilisateur par email (ou créer un placeholder)
                            def _get_user(email: str) -> TibilletUser | None:
                                try:
                                    if not email:
                                        return None
                                    user = TibilletUser.objects.filter(email=email).first()
                                    if user:
                                        return user
                                    # fallback: créer un user minimal via utilitaire
                                    try:
                                        u = get_or_create_user(email=email)
                                        return u
                                    except Exception:
                                        return None
                                except Exception:
                                    return None

                            # Création depuis fixtures si fournis
                            created_any_bi = False
                            for bi in budget_items:
                                try:
                                    desc = (bi.get('description') or '').strip()
                                    # Supporte amount_eur (clé historique) et amount (nouvelle clé en unités)
                                    raw_amount = bi.get('amount_eur')
                                    if raw_amount is None:
                                        raw_amount = bi.get('amount')
                                    amt_eur = Decimal(str(raw_amount or 0))
                                except Exception:
                                    desc = ''
                                    amt_eur = Decimal('0')
                                if not desc or amt_eur <= 0:
                                    continue
                                # Les BudgetItem.amount sont stockés en centimes (int)
                                try:
                                    amt_cents = int((amt_eur * 100).to_integral_value())
                                except Exception:
                                    amt_cents = int(round(float(amt_eur) * 100))
                                state = (bi.get('state') or 'approved').strip().lower()
                                if state not in ['requested', 'approved', 'rejected']:
                                    state = 'approved'
                                # Supporte contributor_email (historique) et contributor (nouvelle clé email)
                                contributor_email = bi.get('contributor_email') or bi.get('contributor')
                                contributor = _get_user(contributor_email or admin_email_env)
                                validator = None
                                if state in ['approved', 'rejected']:
                                    validator = _get_user(bi.get('validator_email') or admin_email_env)

                                # Idempotence renforcée: utiliser (initiative, description, contributor) comme clé
                                try:
                                    contributor_key = contributor or TibilletUser.objects.filter(email=admin_email_env).first()
                                    bi_obj, created = BudgetItem.objects.get_or_create(
                                        initiative=initiative_obj,
                                        description=desc,
                                        contributor=contributor_key,
                                        defaults={
                                            'amount': amt_cents,
                                            'state': state,
                                            'validator': validator if state in ['approved', 'rejected'] else None,
                                        }
                                    )
                                    if not created:
                                        updates = []
                                        if bi_obj.amount != amt_cents:
                                            bi_obj.amount = amt_cents
                                            updates.append('amount')
                                        if bi_obj.state != state:
                                            bi_obj.state = state
                                            updates.append('state')
                                        if state in ['approved', 'rejected'] and validator and bi_obj.validator_id != getattr(validator, 'id', None):
                                            bi_obj.validator = validator
                                            updates.append('validator')
                                        if updates:
                                            try:
                                                bi_obj.save(update_fields=updates)
                                            except Exception:
                                                bi_obj.save()
                                    created_any_bi = created_any_bi or created
                                except Exception as e:
                                    logger.warning(f"BudgetItem non créé pour '{name}': {e}")

                            # Si aucune ligne n'est fournie dans le JSON, générer une répartition simple (60/40)
                            if not budget_items and (goal_units or 0) > 0:
                                try:
                                    admin_user = TibilletUser.objects.filter(email=admin_email_env).first()
                                    if not admin_user:
                                        admin_user = _get_user(admin_email_env)
                                    g = Decimal(str(goal_units))
                                    p1 = (g * Decimal('0.6')).quantize(Decimal('0.01'))
                                    p2 = (g - p1).quantize(Decimal('0.01'))
                                    # Conversion en centimes
                                    p1_cents = int((p1 * 100).to_integral_value())
                                    p2_cents = int((p2 * 100).to_integral_value())
                                    defaults_common = {
                                        'contributor': admin_user,
                                        'state': 'approved',
                                        'validator': admin_user,
                                    }
                                    # BI 1
                                    BudgetItem.objects.get_or_create(
                                        initiative=initiative_obj,
                                        description=f"{name} – Poste A",
                                        amount=p1_cents,
                                        defaults=defaults_common,
                                    )
                                    # BI 2
                                    BudgetItem.objects.get_or_create(
                                        initiative=initiative_obj,
                                        description=f"{name} – Poste B",
                                        amount=p2_cents,
                                        defaults=defaults_common,
                                    )
                                except Exception as e:
                                    logger.warning(f"Impossible de générer des BudgetItem par défaut pour '{name}': {e}")

                            # Contributions (financières ou en unité)
                            for c in init.get('contributions', []) or []:
                                try:
                                    amount_eur = float(c.get('amount_eur', 0))
                                    amount_cents = int(round(amount_eur * 100))
                                except Exception:
                                    amount_cents = 0
                                contributor_name = (c.get('name') or '')
                                if amount_cents <= 0:
                                    continue
                                exists = Contribution.objects.filter(
                                    initiative=initiative_obj,
                                    amount=amount_cents,
                                    contributor_name=contributor_name or "",
                                    payment_status=Contribution.PaymentStatus.PAID_ADMIN,
                                ).exists()
                                if not exists:
                                    Contribution.objects.create(
                                        initiative=initiative_obj,
                                        amount=amount_cents,
                                        contributor_name=contributor_name,
                                        payment_status=Contribution.PaymentStatus.PAID_ADMIN,
                                    )

                            # Si des participations sont fournies dans le JSON, activer automatiquement
                            # l'affichage du budget contributif pour rendre la section visible sur le front.
                            try:
                                provided_parts = (init.get('participations', []) or [])
                                if provided_parts and not getattr(initiative_obj, 'budget_contributif', False):
                                    initiative_obj.budget_contributif = True
                                    initiative_obj.save(update_fields=['budget_contributif'])
                            except Exception:
                                # ne bloque pas le seed si erreur
                                pass

                            # Participations (demandes de budget)
                            for p in init.get('participations', []) or []:
                                # Remplacement de variable d'env dans l'email si nécessaire
                                raw_email = p.get('user_email') or ''
                                user_email = raw_email.replace('${ADMIN_EMAIL}', admin_email_env) if raw_email else admin_email_env
                                try:
                                    # Autoriser la participation bénévole si requested_value est vide/0
                                    requested_raw = p.get('requested_value')
                                    requested_val = float(requested_raw) if (requested_raw is not None and requested_raw != "") else 0.0
                                except Exception:
                                    requested_val = 0
                                requested_cents = int(round(requested_val * 100)) if requested_val > 0 else None
                                desc = p.get('description') or ''
                                state = map_participation_state(p.get('state'))
                                time_spent = p.get('time_spent_minutes')

                                user = get_or_create_user(user_email, send_mail=False)
                                # Idempotence: ne pas inclure le montant dans la clé, car il peut évoluer
                                part, created = Participation.objects.get_or_create(
                                    initiative=initiative_obj,
                                    participant=user,
                                    description=desc,
                                    defaults={"state": state, "amount": requested_cents},
                                )
                                updates = []
                                if part.amount != requested_cents:
                                    part.amount = requested_cents
                                    updates.append('amount')
                                if part.state != state:
                                    part.state = state
                                    updates.append('state')
                                if time_spent is not None and state in (Participation.State.COMPLETED_USER, Participation.State.VALIDATED_ADMIN):
                                    if part.time_spent_minutes != int(time_spent):
                                        part.time_spent_minutes = int(time_spent)
                                        updates.append('time_spent_minutes')
                                if updates:
                                    part.save(update_fields=updates)
                        except Exception as e:
                            logger.warning(f"Erreur lors de l'import de l'initiative '{init.get('name')}' pour {tenant.name}: {e}")
                        
                        # -----------------------------
                        # Votes depuis fixtures
                        # -----------------------------
                        try:
                            provided_votes = init.get('votes') or []
                        except Exception:
                            provided_votes = []
                        if provided_votes and initiative_obj:
                            # S'assurer que l'initiative a bien l'option de vote activée si des votes sont fournis
                            if not getattr(initiative_obj, 'vote', False):
                                try:
                                    initiative_obj.vote = True
                                    initiative_obj.save(update_fields=['vote'])
                                except Exception:
                                    pass
                            for v in provided_votes:
                                try:
                                    u_email = (v.get('user_email') or '').strip()
                                except Exception:
                                    u_email = ''
                                if not u_email:
                                    continue
                                try:
                                    voter = get_or_create_user(u_email, send_mail=False)
                                    Vote.objects.get_or_create(initiative=initiative_obj, user=voter)
                                except Exception as e:
                                    logger.warning(f"Vote non créé pour '{initiative_obj.name}' ({u_email}): {e}")
                        elif provided_votes and not initiative_obj:
                            # Si l'initiative a échoué à être créée, on ne peut pas créer les votes
                            logger.warning(
                                f"Votes fournis mais initiative introuvable/non créée pour '{init.get('name')}' sur tenant {tenant.name}. Votes ignorés."
                            )

                # -----------------------------
                # Fédérations (agenda + adhésions)
                # -----------------------------
                # FALC: Après la création de TOUS les tenants, on peut lier des fédérations
                # entre lieux. Ici, on lit le bloc "federations" du JSON du tenant courant.
                feds = fx.get('federations', []) or []
                if feds:
                    for fed in feds:
                        try:
                            target_name = fed.get('tenant')
                            if not target_name:
                                continue
                            # Récupérer le tenant cible (dans le schéma public)
                            with schema_context('public'):
                                target_client = Client.objects.filter(name=target_name).first()
                            if not target_client:
                                logger.warning(f"Federation ignorée: tenant cible '{target_name}' introuvable pour {tenant.name}")
                                continue
                            # Créer/mettre à jour la fédération
                            fp, created_fp = FederatedPlace.objects.get_or_create(tenant=target_client)
                            updates = []
                            membership_visible = bool(fed.get('membership_visible'))
                            if fp.membership_visible != membership_visible:
                                fp.membership_visible = membership_visible
                                updates.append('membership_visible')
                            if updates:
                                try:
                                    fp.save(update_fields=updates)
                                except Exception:
                                    fp.save()

                            # Tags: include (tag_filter) et exclude (tag_exclude)
                            include_tags = [t for t in (fed.get('include_tags') or []) if t]
                            exclude_tags = [t for t in (fed.get('exclude_tags') or []) if t]

                            if include_tags is not None:
                                tag_objs = []
                                for name in include_tags:
                                    t = ensure_tag(name)
                                    if t:
                                        tag_objs.append(t)
                                # set() est idempotent et remplace la liste courante par la souhaitée
                                if tag_objs is not None:
                                    fp.tag_filter.set(tag_objs)

                            if exclude_tags is not None:
                                tag_objs = []
                                for name in exclude_tags:
                                    t = ensure_tag(name)
                                    if t:
                                        tag_objs.append(t)
                                if tag_objs is not None:
                                    fp.tag_exclude.set(tag_objs)
                        except Exception as e:
                            logger.warning(f"Erreur lors de la configuration d'une fédération pour {tenant.name}: {e}")

        # -----------------------------
        # 3) Diversité des origines utilisateurs (demo)
        # -----------------------------
        try:
            user_emails = set()
            for fx in fixtures:
                for init in (fx.get('initiatives') or []):
                    for v in (init.get('votes') or []):
                        email = (v.get('user_email') or '').strip()
                        if email:
                            user_emails.add(email)
                    for p in (init.get('participations') or []):
                        email = (p.get('user_email') or '').strip()
                        if email:
                            user_emails.add(email)
            if user_emails and created_tenants:
                seed_tenant = created_tenants[0]
                with tenant_context(seed_tenant):
                    for email in user_emails:
                        get_or_create_user(email, send_mail=False)
                with schema_context('public'):
                    for email in user_emails:
                        user = TibilletUser.objects.filter(email=email).first()
                        if not user:
                            continue
                        user.client_source = random.choice(created_tenants)
                        user.save(update_fields=['client_source'])
        except Exception as e:
            logger.warning(f"Erreur lors de l'assignation aléatoire des origines utilisateur: {e}")
