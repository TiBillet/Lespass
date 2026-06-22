"""
tests/pytest/test_profils_csv_comptable.py — Session 21 : profils CSV comptable.
/ Session 21: CSV accounting profiles.

Couvre :
- ventiler_cloture : equilibre debits/credits, cashless → compte 4191
- generer_csv_comptable : Sage 50, EBP, Dolibarr, Paheko, PennyLane
- generer_fec refactorise : toujours conforme (18 colonnes, equilibre)

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_profils_csv_comptable.py -v
"""

import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

import re
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone
from django_tenants.test.cases import FastTenantTestCase

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    CategorieProduct, LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod,
)
from laboutik.models import (
    ClotureCaisse, CompteComptable, LaboutikConfiguration,
    MappingMoyenDePaiement, PointDeVente,
)


class TestProfilsCsvComptable(FastTenantTestCase):
    """Tests pour les profils CSV comptable et la ventilation.
    / Tests for CSV accounting profiles and ventilation."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_profils_csv'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-profils-csv.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = 'Test Profils CSV'

    def setUp(self):
        """Cree les donnees minimales pour chaque test.
        / Creates minimal data for each test."""
        connection.set_tenant(self.tenant)

        # Nettoyer les donnees des tests precedents
        # / Clean data from previous tests
        MappingMoyenDePaiement.objects.all().delete()
        CompteComptable.objects.all().delete()
        ClotureCaisse.objects.all().delete()
        LigneArticle.objects.all().delete()
        PriceSold.objects.all().delete()
        ProductSold.objects.all().delete()
        Price.objects.all().delete()
        Product.objects.all().delete()
        CategorieProduct.objects.all().delete()
        PointDeVente.objects.all().delete()

        # Config singleton / Singleton config
        self.config = LaboutikConfiguration.get_solo()
        self.config.save()

        # Charger le plan comptable bar_resto (comptes + mappings)
        # / Load bar_resto chart of accounts (accounts + mappings)
        call_command(
            'charger_plan_comptable',
            schema=self.tenant.schema_name,
            jeu='bar_resto',
        )

        # Categorie avec compte comptable 7072000
        # / Category with accounting account 7072000
        compte_vente = CompteComptable.objects.get(numero_de_compte='7072000')
        self.categorie = CategorieProduct.objects.create(
            name='Boissons Test',
            compte_comptable=compte_vente,
        )

        # Produit + Prix / Product + Price
        self.produit = Product.objects.create(
            name='Biere', methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
        )
        self.prix = Price.objects.create(
            product=self.produit, name='Pinte', prix=Decimal('5.00'), publish=True,
        )

        # Point de vente / Point of sale
        self.pv = PointDeVente.objects.create(
            name='Bar Test CSV', comportement=PointDeVente.DIRECT,
            service_direct=True, accepte_especes=True,
        )
        self.pv.products.add(self.produit)

        # Utilisateur admin / Admin user
        self.admin, _ = TibilletUser.objects.get_or_create(
            email='admin-csv@tibillet.localhost',
            defaults={'username': 'admin-csv@tibillet.localhost', 'is_staff': True, 'is_active': True},
        )
        self.admin.client_admin.add(self.tenant)

        # Cloture avec rapport_json (especes 500 centimes = 5€)
        # / Closure with rapport_json (cash 500 cents = 5€)
        self.rapport_json = {
            'totaux_par_moyen': {
                'especes': 500,
                'carte_bancaire': 0,
                'cashless': 0,
                'cheque': 0,
                'total': 500,
            },
            'detail_ventes': {
                'Boissons Test': {
                    'articles': [
                        {'nom': 'Biere', 'total_ht': 417, 'total_ttc': 500, 'taux_tva': 20.0, 'qty_vendus': 1.0},
                    ],
                    'total_ttc': 500,
                },
            },
            'tva': {
                '20.00%': {'taux': 20.0, 'total_ttc': 500, 'total_ht': 417, 'total_tva': 83},
            },
        }
        self.cloture = ClotureCaisse.objects.create(
            point_de_vente=self.pv,
            responsable=self.admin,
            datetime_ouverture=timezone.now(),
            datetime_cloture=timezone.now(),
            total_especes=500,
            total_general=500,
            nombre_transactions=1,
            rapport_json=self.rapport_json,
        )
        self.cloture_qs = ClotureCaisse.objects.filter(pk=self.cloture.pk)

    # ------------------------------------------------------------------- #
    #  1. ventiler_cloture : equilibre debits = credits                    #
    # ------------------------------------------------------------------- #

    def test_ventiler_cloture_debits_credits(self):
        """La somme des debits = la somme des credits apres ventilation.
        / Sum of debits = sum of credits after ventilation."""
        from laboutik.ventilation import (
            ventiler_cloture, charger_mappings_paiement,
            charger_categories_par_nom, charger_comptes_tva,
        )

        mappings = charger_mappings_paiement()
        categories = charger_categories_par_nom()
        comptes_tva = charger_comptes_tva()

        lignes, avertissements = ventiler_cloture(
            self.cloture, mappings, categories, comptes_tva
        )

        assert len(lignes) > 0, "ventiler_cloture doit retourner au moins une ligne"

        total_debit = sum(l["montant_centimes"] for l in lignes if l["sens"] == "D")
        total_credit = sum(l["montant_centimes"] for l in lignes if l["sens"] == "C")

        assert total_debit == total_credit, (
            f"Desequilibre : debit={total_debit}, credit={total_credit}"
        )

    # ------------------------------------------------------------------- #
    #  2. ventiler_cloture : cashless → compte 4191                        #
    # ------------------------------------------------------------------- #

    def test_ventiler_cloture_cashless_4191(self):
        """Cloture cashless genere une ligne debit sur un compte 4191.
        / Cashless closure generates a debit line on a 4191 account."""
        from laboutik.ventilation import (
            ventiler_cloture, charger_mappings_paiement,
            charger_categories_par_nom, charger_comptes_tva,
        )

        # Creer une cloture avec cashless=500 (pas especes)
        # / Create a closure with cashless=500 (not cash)
        rapport_cashless = {
            'totaux_par_moyen': {
                'especes': 0,
                'carte_bancaire': 0,
                'cashless': 500,
                'cheque': 0,
                'total': 500,
            },
            'detail_ventes': {
                'Boissons Test': {
                    'articles': [
                        {'nom': 'Biere', 'total_ht': 417, 'total_ttc': 500, 'taux_tva': 20.0, 'qty_vendus': 1.0},
                    ],
                    'total_ttc': 500,
                },
            },
            'tva': {
                '20.00%': {'taux': 20.0, 'total_ttc': 500, 'total_ht': 417, 'total_tva': 83},
            },
        }
        cloture_cashless = ClotureCaisse.objects.create(
            point_de_vente=self.pv,
            responsable=self.admin,
            datetime_ouverture=timezone.now(),
            datetime_cloture=timezone.now(),
            total_especes=0,
            total_general=500,
            nombre_transactions=1,
            rapport_json=rapport_cashless,
        )

        mappings = charger_mappings_paiement()
        categories = charger_categories_par_nom()
        comptes_tva = charger_comptes_tva()

        lignes, _ = ventiler_cloture(
            cloture_cashless, mappings, categories, comptes_tva
        )

        # Chercher une ligne debit avec '4191' dans le numero de compte
        # / Look for a debit line with '4191' in the account number
        lignes_4191 = [
            l for l in lignes
            if l["sens"] == "D" and "4191" in l["numero_compte"]
        ]
        assert len(lignes_4191) >= 1, (
            f"Attendu au moins 1 ligne debit 4191. "
            f"Lignes debit : {[l['numero_compte'] for l in lignes if l['sens'] == 'D']}"
        )

    # ------------------------------------------------------------------- #
    #  3. CSV Sage 50 : separateur point-virgule, 7 colonnes               #
    # ------------------------------------------------------------------- #

    def test_csv_sage_separateur_point_virgule(self):
        """Sage 50 : separateur ';', 7 colonnes par ligne de donnees.
        / Sage 50: ';' separator, 7 columns per data line."""
        from laboutik.csv_comptable import generer_csv_comptable

        contenu_bytes, nom_fichier, _ = generer_csv_comptable(
            self.cloture_qs, 'sage_50', self.tenant.schema_name
        )

        contenu = contenu_bytes.decode('utf-8')
        lignes = [l for l in contenu.split('\n') if l.strip()]

        assert len(lignes) >= 1, "Attendu au moins 1 ligne de donnees"

        # Sage 50 n'a pas d'entete (entetes=False), toutes les lignes sont des donnees
        # / Sage 50 has no header (entetes=False), all lines are data
        for i, ligne in enumerate(lignes, start=1):
            parties = ligne.split(';')
            assert len(parties) == 7, (
                f"Ligne {i} : attendu 7 parties (sep ';'), trouve {len(parties)}. "
                f"Ligne : {ligne}"
            )

    # ------------------------------------------------------------------- #
    #  4. CSV EBP : montant + sens (D ou C)                                #
    # ------------------------------------------------------------------- #

    def test_csv_ebp_montant_sens(self):
        """EBP : les lignes de donnees contiennent D ou C dans la colonne sens.
        / EBP: data lines contain D or C in the sens column."""
        from laboutik.csv_comptable import generer_csv_comptable

        contenu_bytes, _, _ = generer_csv_comptable(
            self.cloture_qs, 'ebp', self.tenant.schema_name
        )

        contenu = contenu_bytes.decode('utf-8')
        lignes = [l for l in contenu.split('\n') if l.strip()]

        assert len(lignes) >= 1, "Attendu au moins 1 ligne de donnees"

        # EBP : colonnes = numero_ligne, date, code_journal, numero_compte,
        #        libelle_auto, libelle, numero_piece, montant, sens, date_echeance
        # L'index de 'sens' est 8 (0-based)
        for i, ligne in enumerate(lignes, start=1):
            parties = ligne.split(',')
            sens = parties[8]
            assert sens in ("D", "C"), (
                f"Ligne {i} : sens attendu 'D' ou 'C', trouve '{sens}'. "
                f"Ligne : {ligne}"
            )

    # ------------------------------------------------------------------- #
    #  5. CSV Dolibarr : separateur decimal = point                        #
    # ------------------------------------------------------------------- #

    def test_csv_dolibarr_decimal_point(self):
        """Dolibarr : les montants utilisent le point comme separateur decimal.
        / Dolibarr: amounts use '.' as decimal separator."""
        from laboutik.csv_comptable import generer_csv_comptable

        contenu_bytes, _, _ = generer_csv_comptable(
            self.cloture_qs, 'dolibarr', self.tenant.schema_name
        )

        contenu = contenu_bytes.decode('utf-8')
        lignes = [l for l in contenu.split('\n') if l.strip()]

        # Dolibarr a un entete (entetes=True), on saute la 1ere ligne
        # / Dolibarr has a header (entetes=True), skip the first line
        assert len(lignes) >= 2, "Attendu au moins 2 lignes (header + data)"

        # Colonnes Dolibarr : numero_transaction, date, reference_piece,
        #   code_journal, numero_compte, compte_auxiliaire, libelle,
        #   debit (idx 7), credit (idx 8), libelle_compte
        for i, ligne in enumerate(lignes[1:], start=2):
            parties = ligne.split(',')
            debit = parties[7]
            credit = parties[8]

            # Les montants non-nuls doivent contenir un point, pas de virgule
            # / Non-zero amounts must contain a dot, no comma
            for montant in (debit, credit):
                if montant and montant != "0.00":
                    assert '.' in montant, (
                        f"Ligne {i} : montant '{montant}' sans point decimal"
                    )
                assert ',' not in montant, (
                    f"Ligne {i} : montant '{montant}' contient une virgule "
                    f"(attendu point decimal)"
                )

    # ------------------------------------------------------------------- #
    #  6. CSV Paheko : montant unique, compte_debit / compte_credit        #
    # ------------------------------------------------------------------- #

    def test_csv_paheko_montant_unique(self):
        """Paheko : les lignes debit ont compte_debit rempli et compte_credit vide,
        et inversement pour les credits.
        / Paheko: debit lines have compte_debit filled and compte_credit empty,
        and vice versa for credits."""
        from laboutik.csv_comptable import generer_csv_comptable

        contenu_bytes, _, _ = generer_csv_comptable(
            self.cloture_qs, 'paheko', self.tenant.schema_name
        )

        contenu = contenu_bytes.decode('utf-8')
        lignes = [l for l in contenu.split('\n') if l.strip()]

        # Paheko a un entete (entetes=True)
        # Colonnes : numero_ecriture, date, compte_debit (idx 2),
        #   compte_credit (idx 3), montant, libelle, numero_piece, remarques
        assert len(lignes) >= 2, "Attendu au moins 2 lignes (header + data)"

        lignes_debit = 0
        lignes_credit = 0

        for i, ligne in enumerate(lignes[1:], start=2):
            parties = ligne.split(';')
            compte_debit = parties[2]
            compte_credit = parties[3]

            # Exactement un des deux doit etre rempli
            # / Exactly one of the two must be filled
            if compte_debit:
                assert compte_credit == "", (
                    f"Ligne {i} : compte_debit='{compte_debit}' ET "
                    f"compte_credit='{compte_credit}' (un seul attendu)"
                )
                lignes_debit += 1
            else:
                assert compte_credit != "", (
                    f"Ligne {i} : ni compte_debit ni compte_credit rempli"
                )
                lignes_credit += 1

        assert lignes_debit >= 1, "Attendu au moins 1 ligne debit"
        assert lignes_credit >= 1, "Attendu au moins 1 ligne credit"

    # ------------------------------------------------------------------- #
    #  7. CSV PennyLane : code_journal = lettres uniquement                 #
    # ------------------------------------------------------------------- #

    def test_csv_pennylane_code_journal_lettres(self):
        """PennyLane : la colonne code_journal ne contient que des lettres.
        / PennyLane: the code_journal column contains only letters."""
        from laboutik.csv_comptable import generer_csv_comptable

        contenu_bytes, _, _ = generer_csv_comptable(
            self.cloture_qs, 'pennylane', self.tenant.schema_name
        )

        contenu = contenu_bytes.decode('utf-8')
        lignes = [l for l in contenu.split('\n') if l.strip()]

        # PennyLane a un entete (entetes=True)
        # Colonnes : date, code_journal (idx 1), numero_compte,
        #   libelle_compte, libelle, numero_piece, debit, credit
        assert len(lignes) >= 2, "Attendu au moins 2 lignes (header + data)"

        pattern_lettres = re.compile(r'^[A-Za-z]+$')

        for i, ligne in enumerate(lignes[1:], start=2):
            parties = ligne.split(';')
            code_journal = parties[1]
            assert pattern_lettres.match(code_journal), (
                f"Ligne {i} : code_journal='{code_journal}' "
                f"contient autre chose que des lettres"
            )

    # ------------------------------------------------------------------- #
    #  8. FEC refactorise : toujours conforme (18 colonnes, equilibre)     #
    # ------------------------------------------------------------------- #

    def test_fec_utilise_ventilation(self):
        """Le FEC refactorise produit toujours un fichier valide :
        18 colonnes par tabulation, non vide, debits = credits.
        / The refactored FEC still produces a valid file:
        18 tab-separated columns, non-empty, balanced debits=credits."""
        from laboutik.fec import generer_fec

        contenu_bytes, nom_fichier, avertissements = generer_fec(
            self.cloture_qs, self.tenant.schema_name
        )

        contenu = contenu_bytes.decode('utf-8')
        lignes = [l for l in contenu.split('\r\n') if l.strip()]

        # En-tete + au moins 1 ligne de donnees
        # / Header + at least 1 data line
        assert len(lignes) >= 2, f"Attendu au moins 2 lignes, trouve {len(lignes)}"

        # 18 colonnes par ligne
        # / 18 columns per line
        for i, ligne in enumerate(lignes, start=1):
            champs = ligne.split('\t')
            assert len(champs) == 18, (
                f"Ligne {i} : attendu 18 colonnes, trouve {len(champs)}"
            )

        # Equilibre debits = credits
        # / Balance debits = credits
        total_debit = Decimal('0')
        total_credit = Decimal('0')

        for ligne in lignes[1:]:
            champs = ligne.split('\t')
            debit_str = champs[11].replace(',', '.')
            credit_str = champs[12].replace(',', '.')
            total_debit += Decimal(debit_str)
            total_credit += Decimal(credit_str)

        assert total_debit == total_credit, (
            f"Desequilibre FEC : debit={total_debit}, credit={total_credit}"
        )
        assert total_debit > 0, "Les debits ne doivent pas etre nuls"
