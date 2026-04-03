"""
tests/pytest/test_export_comptable.py — Session 20 : export comptable, plan comptable, FEC.
/ Session 20: accounting export, chart of accounts, FEC.

Couvre :
- CompteComptable (creation, champs)
- MappingMoyenDePaiement (creation, lien FK, null ignore)
- CategorieProduct.compte_comptable (FK vers CompteComptable)
- charger_plan_comptable (bar_resto : 15 comptes, association : 10 comptes)
- generer_fec (18 colonnes, equilibre debits/credits, format montants, format dates)
- FEC avec categorie non mappee (avertissements)

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_export_comptable.py -v
"""

import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

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


class TestExportComptable(FastTenantTestCase):
    """Tests pour l'export comptable : modeles, plan comptable, generateur FEC.
    / Tests for accounting export: models, chart of accounts, FEC generator."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_export_compta'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-export-compta.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = 'Test Export Compta'

    def setUp(self):
        """Cree les donnees minimales pour chaque test.
        / Creates minimal data for each test."""
        connection.set_tenant(self.tenant)

        # Nettoyer les singletons et les donnees des tests precedents
        # (FastTenantTestCase ne rollback pas)
        # / Clean singletons and data from previous tests
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

        # Categorie + Produit + Prix / Category + Product + Price
        self.categorie = CategorieProduct.objects.create(name='Boissons Test')
        self.produit = Product.objects.create(
            name='Biere', methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
        )
        self.prix = Price.objects.create(
            product=self.produit, name='Pinte', prix=Decimal('5.00'), publish=True,
        )

        # Point de vente / Point of sale
        self.pv = PointDeVente.objects.create(
            name='Bar Test Compta', comportement=PointDeVente.DIRECT,
            service_direct=True, accepte_especes=True,
        )
        self.pv.products.add(self.produit)

        # LigneArticle (une vente de 5€ TTC, 4.17€ HT, TVA 20%)
        # / One sale of 5€ incl. VAT, 4.17€ excl. VAT, 20% VAT
        product_sold = ProductSold.objects.create(product=self.produit)
        price_sold = PriceSold.objects.create(
            productsold=product_sold, prix=Decimal('5.00'), qty_solded=1, price=self.prix,
        )
        self.ligne = LigneArticle.objects.create(
            pricesold=price_sold,
            amount=500, total_ht=417, qty=1, vat=Decimal('20.00'),
            payment_method=PaymentMethod.CASH, status='V',
            sale_origin=SaleOrigin.LABOUTIK,
            point_de_vente=self.pv,
        )

        # Utilisateur admin / Admin user
        self.admin, _ = TibilletUser.objects.get_or_create(
            email='admin-compta@tibillet.localhost',
            defaults={'username': 'admin-compta@tibillet.localhost', 'is_staff': True, 'is_active': True},
        )
        self.admin.client_admin.add(self.tenant)

    # ------------------------------------------------------------------- #
    #  Helpers                                                             #
    # ------------------------------------------------------------------- #

    def _creer_cloture_avec_rapport(self):
        """Cree une ClotureCaisse avec un rapport_json complet.
        / Creates a ClotureCaisse with a complete rapport_json."""
        rapport_json = {
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
        cloture = ClotureCaisse.objects.create(
            point_de_vente=self.pv,
            responsable=self.admin,
            datetime_ouverture=timezone.now(),
            datetime_cloture=timezone.now(),
            total_especes=500,
            total_general=500,
            nombre_transactions=1,
            rapport_json=rapport_json,
        )
        return cloture

    def _charger_plan_et_mapper_categorie(self):
        """Charge le plan bar_resto, associe le compte vente 20% a la categorie.
        / Loads bar_resto plan, links the 20% sales account to the category."""
        call_command(
            'charger_plan_comptable',
            schema=self.tenant.schema_name,
            jeu='bar_resto',
        )
        # Associer le compte de vente 20% a la categorie "Boissons Test"
        # / Link the 20% sales account to the "Boissons Test" category
        compte_vente = CompteComptable.objects.get(numero_de_compte='7072000')
        self.categorie.compte_comptable = compte_vente
        self.categorie.save()

    # ------------------------------------------------------------------- #
    #  1. CompteComptable : creation                                       #
    # ------------------------------------------------------------------- #

    def test_compte_comptable_creation(self):
        """Creer un CompteComptable, verifier les champs.
        / Create a CompteComptable, verify fields."""
        compte = CompteComptable.objects.create(
            numero_de_compte='7072000',
            libelle_du_compte='Ventes boissons 20%',
            nature_du_compte=CompteComptable.VENTE,
            taux_de_tva=Decimal('20.00'),
        )

        compte.refresh_from_db()
        assert compte.numero_de_compte == '7072000'
        assert compte.libelle_du_compte == 'Ventes boissons 20%'
        assert compte.nature_du_compte == CompteComptable.VENTE
        assert compte.taux_de_tva == Decimal('20.00')
        assert compte.est_actif is True

    # ------------------------------------------------------------------- #
    #  2. MappingMoyenDePaiement : creation avec FK                        #
    # ------------------------------------------------------------------- #

    def test_mapping_moyen_paiement_creation(self):
        """Creer un MappingMoyenDePaiement lie a un CompteComptable.
        / Create a MappingMoyenDePaiement linked to a CompteComptable."""
        compte = CompteComptable.objects.create(
            numero_de_compte='5300000',
            libelle_du_compte='Caisse especes',
            nature_du_compte=CompteComptable.TRESORERIE,
        )
        mapping = MappingMoyenDePaiement.objects.create(
            moyen_de_paiement='CA',
            libelle_moyen='Especes',
            compte_de_tresorerie=compte,
        )

        mapping.refresh_from_db()
        assert mapping.moyen_de_paiement == 'CA'
        assert mapping.libelle_moyen == 'Especes'
        assert mapping.compte_de_tresorerie == compte

    # ------------------------------------------------------------------- #
    #  3. MappingMoyenDePaiement : null = ignore                           #
    # ------------------------------------------------------------------- #

    def test_mapping_moyen_null_ignore(self):
        """MappingMoyenDePaiement avec compte_de_tresorerie=None est valide.
        / MappingMoyenDePaiement with compte_de_tresorerie=None is valid."""
        mapping = MappingMoyenDePaiement.objects.create(
            moyen_de_paiement='LE',
            libelle_moyen='Cashless local',
            compte_de_tresorerie=None,
        )

        mapping.refresh_from_db()
        assert mapping.compte_de_tresorerie is None

    # ------------------------------------------------------------------- #
    #  4. CategorieProduct.compte_comptable FK                             #
    # ------------------------------------------------------------------- #

    def test_categorie_avec_compte(self):
        """CategorieProduct.compte_comptable FK vers CompteComptable fonctionne.
        / CategorieProduct.compte_comptable FK to CompteComptable works."""
        compte = CompteComptable.objects.create(
            numero_de_compte='7072000',
            libelle_du_compte='Ventes boissons 20%',
            nature_du_compte=CompteComptable.VENTE,
            taux_de_tva=Decimal('20.00'),
        )
        self.categorie.compte_comptable = compte
        self.categorie.save()

        self.categorie.refresh_from_db()
        assert self.categorie.compte_comptable == compte
        assert self.categorie.compte_comptable.numero_de_compte == '7072000'

    # ------------------------------------------------------------------- #
    #  5. charger_plan_comptable : bar_resto → 15 comptes                  #
    # ------------------------------------------------------------------- #

    def test_charger_plan_bar_resto(self):
        """charger_plan_comptable jeu=bar_resto cree 16 CompteComptable.
        (15 comptes originaux + 1 compte 4191 avances clients cashless)
        / charger_plan_comptable jeu=bar_resto creates 16 CompteComptable."""
        call_command(
            'charger_plan_comptable',
            schema=self.tenant.schema_name,
            jeu='bar_resto',
        )

        nb_comptes = CompteComptable.objects.count()
        assert nb_comptes == 16, f"Attendu 16 comptes, trouve {nb_comptes}"

    # ------------------------------------------------------------------- #
    #  6. charger_plan_comptable : association → 10 comptes                #
    # ------------------------------------------------------------------- #

    def test_charger_plan_association(self):
        """charger_plan_comptable jeu=association cree 10 CompteComptable.
        / charger_plan_comptable jeu=association creates 10 CompteComptable."""
        call_command(
            'charger_plan_comptable',
            schema=self.tenant.schema_name,
            jeu='association',
        )

        nb_comptes = CompteComptable.objects.count()
        assert nb_comptes == 10, f"Attendu 10 comptes, trouve {nb_comptes}"

    # ------------------------------------------------------------------- #
    #  7. FEC : 18 colonnes par ligne                                      #
    # ------------------------------------------------------------------- #

    def test_fec_18_colonnes(self):
        """Chaque ligne du FEC (hors en-tete) a 18 champs separes par tabulation.
        / Each FEC line (except header) has 18 tab-separated fields."""
        from laboutik.fec import generer_fec

        self._charger_plan_et_mapper_categorie()
        cloture = self._creer_cloture_avec_rapport()

        contenu_bytes, nom_fichier, avertissements = generer_fec(
            ClotureCaisse.objects.filter(pk=cloture.pk),
            self.tenant.schema_name,
        )

        contenu = contenu_bytes.decode('utf-8')
        lignes = [l for l in contenu.split('\r\n') if l.strip()]

        # L'en-tete a 18 colonnes / Header has 18 columns
        en_tete = lignes[0].split('\t')
        assert len(en_tete) == 18, f"En-tete : attendu 18 colonnes, trouve {len(en_tete)}"

        # Au moins 1 ligne de donnees (debit especes + credit vente HT + credit TVA)
        # / At least 1 data line (cash debit + sales credit HT + VAT credit)
        assert len(lignes) >= 2, f"Attendu au moins 2 lignes (header + data), trouve {len(lignes)}"

        # Chaque ligne de donnees a 18 champs / Each data line has 18 fields
        for i, ligne in enumerate(lignes[1:], start=2):
            champs = ligne.split('\t')
            assert len(champs) == 18, f"Ligne {i} : attendu 18 champs, trouve {len(champs)}"

    # ------------------------------------------------------------------- #
    #  8. FEC : equilibre debits = credits                                 #
    # ------------------------------------------------------------------- #

    def test_fec_equilibre_debits_credits(self):
        """La somme des debits = la somme des credits dans le FEC.
        / Sum of debits = sum of credits in the FEC."""
        from laboutik.fec import generer_fec

        self._charger_plan_et_mapper_categorie()
        cloture = self._creer_cloture_avec_rapport()

        contenu_bytes, nom_fichier, avertissements = generer_fec(
            ClotureCaisse.objects.filter(pk=cloture.pk),
            self.tenant.schema_name,
        )

        contenu = contenu_bytes.decode('utf-8')
        lignes = [l for l in contenu.split('\r\n') if l.strip()]

        # Colonnes : index 11 = Debit, index 12 = Credit
        # / Columns: index 11 = Debit, index 12 = Credit
        total_debit = Decimal('0')
        total_credit = Decimal('0')

        for ligne in lignes[1:]:  # Sauter l'en-tete / Skip header
            champs = ligne.split('\t')
            debit_str = champs[11].replace(',', '.')
            credit_str = champs[12].replace(',', '.')
            total_debit += Decimal(debit_str)
            total_credit += Decimal(credit_str)

        assert total_debit == total_credit, (
            f"Desequilibre : total debit={total_debit}, total credit={total_credit}"
        )

    # ------------------------------------------------------------------- #
    #  9. FEC : montants avec virgule                                      #
    # ------------------------------------------------------------------- #

    def test_fec_format_montants_virgule(self):
        """Les montants utilisent la virgule comme separateur decimal ("5,00" pas "5.00").
        / Amounts use comma as decimal separator ("5,00" not "5.00")."""
        from laboutik.fec import generer_fec

        self._charger_plan_et_mapper_categorie()
        cloture = self._creer_cloture_avec_rapport()

        contenu_bytes, nom_fichier, avertissements = generer_fec(
            ClotureCaisse.objects.filter(pk=cloture.pk),
            self.tenant.schema_name,
        )

        contenu = contenu_bytes.decode('utf-8')
        lignes = [l for l in contenu.split('\r\n') if l.strip()]

        # Verifier que les montants non-nuls contiennent une virgule
        # / Verify non-zero amounts contain a comma
        for ligne in lignes[1:]:
            champs = ligne.split('\t')
            debit = champs[11]
            credit = champs[12]

            # Chaque montant doit avoir une virgule (meme "0,00")
            # / Each amount must have a comma (even "0,00")
            assert ',' in debit, f"Debit sans virgule : '{debit}'"
            assert ',' in credit, f"Credit sans virgule : '{credit}'"

            # Pas de point dans les montants / No dot in amounts
            assert '.' not in debit, f"Debit avec point : '{debit}'"
            assert '.' not in credit, f"Credit avec point : '{credit}'"

    # ------------------------------------------------------------------- #
    #  10. FEC : dates au format AAAAMMJJ                                  #
    # ------------------------------------------------------------------- #

    def test_fec_format_dates_aaaammjj(self):
        """Les dates sont au format AAAAMMJJ (sans tirets).
        / Dates are YYYYMMDD format (no dashes)."""
        from laboutik.fec import generer_fec
        import re

        self._charger_plan_et_mapper_categorie()
        cloture = self._creer_cloture_avec_rapport()

        contenu_bytes, nom_fichier, avertissements = generer_fec(
            ClotureCaisse.objects.filter(pk=cloture.pk),
            self.tenant.schema_name,
        )

        contenu = contenu_bytes.decode('utf-8')
        lignes = [l for l in contenu.split('\r\n') if l.strip()]

        # Colonnes date : index 3 (EcritureDate), 9 (PieceDate), 15 (ValidDate)
        # / Date columns: index 3, 9, 15
        pattern_date = re.compile(r'^\d{8}$')

        for i, ligne in enumerate(lignes[1:], start=2):
            champs = ligne.split('\t')
            for idx_col in [3, 9, 15]:
                valeur = champs[idx_col]
                assert pattern_date.match(valeur), (
                    f"Ligne {i}, colonne {idx_col} : date invalide '{valeur}' "
                    f"(attendu AAAAMMJJ sans tirets)"
                )

    # ------------------------------------------------------------------- #
    #  11. FEC : categorie non mappee → avertissement                      #
    # ------------------------------------------------------------------- #

    def test_fec_categorie_non_mappee(self):
        """Export FEC avec categorie sans compte comptable : fonctionne + avertissement.
        / FEC export with unmapped category: works + warning returned."""
        from laboutik.fec import generer_fec

        # Charger le plan pour avoir les comptes TVA et mappings paiement
        # MAIS ne pas associer de compte_comptable a la categorie
        # / Load the plan for TVA accounts and payment mappings
        # BUT do NOT link a compte_comptable to the category
        call_command(
            'charger_plan_comptable',
            schema=self.tenant.schema_name,
            jeu='bar_resto',
        )

        cloture = self._creer_cloture_avec_rapport()

        contenu_bytes, nom_fichier, avertissements = generer_fec(
            ClotureCaisse.objects.filter(pk=cloture.pk),
            self.tenant.schema_name,
        )

        # Le FEC doit quand meme etre genere (pas d'exception)
        # / FEC must still be generated (no exception)
        assert contenu_bytes is not None
        assert len(contenu_bytes) > 0

        # Un avertissement doit mentionner la categorie non mappee
        # / A warning must mention the unmapped category
        assert len(avertissements) >= 1, "Attendu au moins 1 avertissement pour categorie non mappee"
        avertissement_trouve = any('Boissons Test' in a for a in avertissements)
        assert avertissement_trouve, (
            f"Aucun avertissement ne mentionne 'Boissons Test'. "
            f"Avertissements : {avertissements}"
        )

        # Le FEC contient le compte 000000 (compte par defaut pour categorie non mappee)
        # / FEC contains account 000000 (default for unmapped category)
        contenu = contenu_bytes.decode('utf-8')
        assert '000000' in contenu, "Le compte 000000 devrait apparaitre pour la categorie non mappee"
