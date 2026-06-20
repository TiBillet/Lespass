"""
Management command pour charger un plan comptable par defaut dans un tenant.
/ Management command to load a default chart of accounts into a tenant.

Deux jeux de donnees disponibles :
- bar_resto  : plan comptable pour bar/restaurant (15 comptes)
- association : plan comptable pour association/salle de spectacle (10 comptes)

Charge aussi les mappings de moyens de paiement par defaut.
/ Two fixture sets available:
- bar_resto  : chart of accounts for bar/restaurant (15 accounts)
- association : chart of accounts for association/venue (10 accounts)

Also loads default payment method mappings.

LOCALISATION : laboutik/management/commands/charger_plan_comptable.py

Usage :
    docker exec lespass_django poetry run python manage.py charger_plan_comptable \
        --schema=lespass --jeu=bar_resto

    # Reinitialiser avant de charger
    # / Reset before loading
    docker exec lespass_django poetry run python manage.py charger_plan_comptable \
        --schema=lespass --jeu=association --reset
"""

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context


# --- Fixtures ---

# Plan comptable bar/restaurant (15 comptes)
# / Bar/restaurant chart of accounts (15 accounts)
PLAN_BAR_RESTO = [
    {'numero': '7072000', 'libelle': 'Boissons a 20%',                   'nature': 'VENTE',               'tva': '20.00'},
    {'numero': '7071000', 'libelle': 'Boissons a 10%',                   'nature': 'VENTE',               'tva': '10.00'},
    {'numero': '7011000', 'libelle': 'Alimentaire a 10%',                'nature': 'VENTE',               'tva': '10.00'},
    {'numero': '7010500', 'libelle': 'Alimentaire a emporter 5,5%',      'nature': 'VENTE',               'tva': '5.50'},
    {'numero': '51120001','libelle': 'Paiement CB',                      'nature': 'TRESORERIE',          'tva': None},
    {'numero': '5300000', 'libelle': 'Paiement Especes',                 'nature': 'TRESORERIE',          'tva': None},
    {'numero': '51120002','libelle': 'Paiement Tickets Restaurants',     'nature': 'TRESORERIE',          'tva': None},
    {'numero': '51120000','libelle': 'Paiement en cheque',               'nature': 'TRESORERIE',          'tva': None},
    {'numero': '445712',  'libelle': 'TVA 20%',                          'nature': 'TVA',                 'tva': '20.00'},
    {'numero': '445710',  'libelle': 'TVA 10%',                          'nature': 'TVA',                 'tva': '10.00'},
    {'numero': '445705',  'libelle': 'TVA 5,5%',                         'nature': 'TVA',                 'tva': '5.50'},
    {'numero': '709000',  'libelle': 'Remises',                          'nature': 'SPECIAL',             'tva': None},
    {'numero': '5811000', 'libelle': 'Caisse (mouvements especes)',      'nature': 'SPECIAL',             'tva': None},
    {'numero': '758000',  'libelle': 'Ecart de gestion +',               'nature': 'PRODUIT_EXCEPTIONNEL','tva': None},
    {'numero': '658000',  'libelle': 'Ecart de gestion -',               'nature': 'CHARGE',              'tva': None},
    {'numero': '41910000','libelle': 'Avances clients (cashless)',       'nature': 'TIERS',               'tva': None},
]

# Plan comptable association/salle (10 comptes)
# / Association/venue chart of accounts (10 accounts)
PLAN_ASSOCIATION = [
    {'numero': '706000',  'libelle': 'Prestations de services',          'nature': 'VENTE',     'tva': '20.00'},
    {'numero': '707000',  'libelle': 'Ventes de marchandises',           'nature': 'VENTE',     'tva': '20.00'},
    {'numero': '706300',  'libelle': 'Billetterie',                      'nature': 'VENTE',     'tva': '5.50'},
    {'numero': '756000',  'libelle': 'Cotisations',                      'nature': 'VENTE',     'tva': None},
    {'numero': '512000',  'libelle': 'Banque',                           'nature': 'TRESORERIE','tva': None},
    {'numero': '530000',  'libelle': 'Caisse',                           'nature': 'TRESORERIE','tva': None},
    {'numero': '419100',  'libelle': 'Avances clients (cashless)',       'nature': 'TIERS',     'tva': None},
    {'numero': '445710',  'libelle': 'TVA collectee 20%',                'nature': 'TVA',       'tva': '20.00'},
    {'numero': '445712',  'libelle': 'TVA collectee 5,5%',               'nature': 'TVA',       'tva': '5.50'},
    {'numero': '709000',  'libelle': 'Remises',                          'nature': 'SPECIAL',   'tva': None},
]

# Mappings de moyens de paiement par jeu de donnees.
# La valeur est le numero de compte (str) ou None si le moyen est ignore.
# / Payment method mappings per fixture set.
# The value is the account number (str) or None if the method is ignored.

# Libelles humains des moyens de paiement
# / Human-readable payment method labels
LIBELLES_MOYENS = {
    'CA': 'Especes',
    'CC': 'Carte bancaire',
    'CH': 'Cheque',
    'LE': 'Cashless local',
    'LG': 'Cashless cadeau',
    'QR': 'QR / NFC',
    'SN': 'Stripe (en ligne)',
    'NA': 'Offert',
}

# Mapping pour bar_resto : CA→5300000, CC→51120001, CH→51120000, SN→51120001
# Les autres (LE, LG, QR, NA) sont ignores (None)
# / Bar_resto mapping: CA→5300000, CC→51120001, CH→51120000, SN→51120001
# Others (LE, LG, QR, NA) are ignored (None)
MAPPING_BAR_RESTO = {
    'CA': '5300000',
    'CC': '51120001',
    'CH': '51120000',
    # Cashless : avances clients (4191). L'argent a ete encaisse lors de la recharge.
    # La vente cashless "consomme" l'avance. Si le gerant prefere ignorer le
    # cashless dans le FEC, il peut mettre ce mapping a null dans l'admin.
    # / Cashless: customer advances (4191). Money was collected at top-up.
    # The cashless sale "consumes" the advance.
    'LE': '41910000',
    'LG': None,  # Cadeau = pas d'encaissement, pas d'avance. Ignorer dans le FEC.
    'QR': '51120001',  # QR/NFC = paiement en ligne (vrais euros). / QR/NFC = online payment (real euros).
    'SN': '51120001',
    'NA': None,
}

# Mapping pour association : CA→530000, CC→512000, CH→512000, SN→512000
# Les autres (LE, LG, QR, NA) sont ignores (None)
# / Association mapping: CA→530000, CC→512000, CH→512000, SN→512000
# Others (LE, LG, QR, NA) are ignored (None)
MAPPING_ASSOCIATION = {
    'CA': '530000',
    'CC': '512000',
    'CH': '512000',
    # Cashless → 419100 Avances clients (meme logique que bar_resto)
    # / Cashless → 419100 Customer advances
    'LE': '419100',
    'LG': None,  # Cadeau = pas d'encaissement. / Gift = no collection.
    'QR': '512000',  # QR/NFC = paiement en ligne (vrais euros). / QR/NFC = online payment (real euros).
    'SN': '512000',
    'NA': None,
}

# Index des plans et mappings par cle de jeu
# / Plans and mappings index by fixture key
PLANS = {
    'bar_resto':    PLAN_BAR_RESTO,
    'association':  PLAN_ASSOCIATION,
}

MAPPINGS = {
    'bar_resto':    MAPPING_BAR_RESTO,
    'association':  MAPPING_ASSOCIATION,
}


class Command(BaseCommand):
    help = (
        'Charge un plan comptable par defaut dans un tenant. '
        '/ Loads a default chart of accounts into a tenant.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema',
            type=str,
            required=True,
            help=(
                'Nom du schema tenant (ex: lespass). '
                '/ Tenant schema name (e.g. lespass).'
            ),
        )
        parser.add_argument(
            '--jeu',
            type=str,
            required=True,
            choices=['bar_resto', 'association'],
            help=(
                'Jeu de donnees a charger : bar_resto ou association. '
                '/ Fixture set to load: bar_resto or association.'
            ),
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            default=False,
            help=(
                'Supprimer les comptes existants avant de charger. '
                '/ Delete existing accounts before loading.'
            ),
        )

    def handle(self, *args, **options):
        schema = options['schema']
        jeu = options['jeu']
        reset = options['reset']

        # --- 1. Verifier que le tenant existe ---
        # / 1. Verify that the tenant exists
        from Customers.models import Client
        try:
            Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(
                    f"Tenant '{schema}' introuvable. "
                    f"/ Tenant '{schema}' not found."
                )
            )
            return

        self.stdout.write(
            f"[{schema}] Chargement du plan comptable '{jeu}'..."
            f" / Loading '{jeu}' chart of accounts..."
        )

        with schema_context(schema):
            from laboutik.models import CompteComptable, MappingMoyenDePaiement

            # --- 2. Verification ou reset ---
            # / 2. Check or reset
            nb_existants = CompteComptable.objects.count()

            if nb_existants > 0 and not reset:
                self.stdout.write(
                    self.style.WARNING(
                        f"[{schema}] {nb_existants} compte(s) existant(s) detecte(s). "
                        f"Utilisez --reset pour ecraser. Abandon. "
                        f"/ {nb_existants} existing account(s) found. "
                        f"Use --reset to overwrite. Aborting."
                    )
                )
                return

            if reset and nb_existants > 0:
                nb_mappings = MappingMoyenDePaiement.objects.count()
                MappingMoyenDePaiement.objects.all().delete()
                CompteComptable.objects.all().delete()
                self.stdout.write(
                    self.style.WARNING(
                        f"[{schema}] {nb_existants} compte(s) et {nb_mappings} mapping(s) supprimes. "
                        f"/ {nb_existants} account(s) and {nb_mappings} mapping(s) deleted."
                    )
                )

            # --- 3. Creer les comptes comptables ---
            # / 3. Create accounting accounts
            plan = PLANS[jeu]
            comptes_crees = 0

            for entree in plan:
                CompteComptable.objects.create(
                    numero_de_compte=entree['numero'],
                    libelle_du_compte=entree['libelle'],
                    nature_du_compte=entree['nature'],
                    taux_de_tva=entree['tva'],
                )
                comptes_crees += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"[{schema}] {comptes_crees} compte(s) cree(s). "
                    f"/ {comptes_crees} account(s) created."
                )
            )

            # --- 4. Creer les mappings de moyens de paiement ---
            # On recherche les comptes par numero pour constituer les FK.
            # / 4. Create payment method mappings
            # Look up accounts by number to build the FKs.
            mapping_def = MAPPINGS[jeu]
            mappings_crees = 0

            for code_moyen, numero_compte in mapping_def.items():
                libelle = LIBELLES_MOYENS.get(code_moyen, code_moyen)

                # Chercher le compte de tresorerie si un numero est fourni
                # / Look up the treasury account if a number is provided
                compte = None
                if numero_compte is not None:
                    try:
                        compte = CompteComptable.objects.get(
                            numero_de_compte=numero_compte
                        )
                    except CompteComptable.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[{schema}] Compte {numero_compte} introuvable "
                                f"pour le moyen {code_moyen}. Mapping ignore. "
                                f"/ Account {numero_compte} not found "
                                f"for method {code_moyen}. Mapping ignored."
                            )
                        )
                        # On cree quand meme le mapping avec compte=None
                        # / Still create the mapping with compte=None

                MappingMoyenDePaiement.objects.create(
                    moyen_de_paiement=code_moyen,
                    libelle_moyen=libelle,
                    compte_de_tresorerie=compte,
                )
                mappings_crees += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"[{schema}] {mappings_crees} mapping(s) cree(s). "
                    f"/ {mappings_crees} mapping(s) created."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"[{schema}] Plan comptable '{jeu}' charge avec succes. "
                f"/ Chart of accounts '{jeu}' loaded successfully."
            )
        )
