"""
tests/pytest/test_archivage_fiscal.py — Session 18 : archivage fiscal, journal, verification.
/ Session 18: fiscal archiving, operations log, verification.

Couvre :
- JournalOperation (creation, chainage HMAC)
- HistoriqueFondDeCaisse (creation directe, creation via API)
- Archivage ZIP (generation, contenu, hash, periode max)
- Verification d'archive (OK, KO)
- Acces fiscal (dossier)
- meta.json (contenu)

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_archivage_fiscal.py -v
"""

import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

import io
import json
import os
import tempfile
import zipfile
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod, CategorieProduct,
)
from laboutik.models import (
    HistoriqueFondDeCaisse, JournalOperation, LaboutikConfiguration,
    PointDeVente,
)


class TestArchivageFiscal(FastTenantTestCase):
    """Tests pour l'archivage fiscal, le journal des operations et la verification d'integrite.
    / Tests for fiscal archiving, operations log and integrity verification."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_archivage'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-archivage.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = 'Test Archivage'

    def setUp(self):
        """Cree les donnees minimales pour chaque test.
        / Creates minimal data for each test."""
        connection.set_tenant(self.tenant)

        # Config HMAC / HMAC config
        self.config = LaboutikConfiguration.get_solo()
        self.config.set_hmac_key('cle-test-archivage-2026')
        self.config.fond_de_caisse = 5000  # 50.00 €
        self.config.save()
        self.cle_hmac = self.config.get_hmac_key()

        # Categorie + Produit + Prix / Category + Product + Price
        self.categorie = CategorieProduct.objects.create(name='Boissons Test Arch')
        self.produit = Product.objects.create(
            name='Biere Test Arch', methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
        )
        self.prix = Price.objects.create(
            product=self.produit, name='Pinte', prix=Decimal('5.00'), publish=True,
        )

        # Point de vente / Point of sale
        self.pv = PointDeVente.objects.create(
            name='Bar Test Arch', comportement=PointDeVente.DIRECT,
            service_direct=True, accepte_especes=True,
        )
        self.pv.products.add(self.produit)

        # Utilisateur admin (public schema — SHARED_APPS)
        # / Admin user (public schema — SHARED_APPS)
        self.admin, _ = TibilletUser.objects.get_or_create(
            email='admin-arch@tibillet.localhost',
            defaults={'username': 'admin-arch@tibillet.localhost', 'is_staff': True, 'is_active': True},
        )
        self.admin.client_admin.add(self.tenant)

        # Client HTTP avec session admin / HTTP client with admin session
        self.c = TenantClient(self.tenant)
        self.c.force_login(self.admin)

        # Creer une LigneArticle pour les donnees d'archive
        # / Create a LigneArticle for archive data
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

    # ----------------------------------------------------------------------- #
    #  1. JournalOperation : creation                                          #
    # ----------------------------------------------------------------------- #

    def test_journal_operation_creation(self):
        """Creer une entree via creer_entree_journal() : type, details, hmac_hash non vide et 64 chars.
        / Create an entry via creer_entree_journal(): type, details, non-empty hmac_hash of 64 chars."""
        from laboutik.archivage import creer_entree_journal

        entree = creer_entree_journal(
            type_operation='ARCHIVAGE',
            details={'test': True, 'raison': 'test unitaire'},
            cle_secrete=self.cle_hmac,
            operateur=self.admin,
        )

        assert entree.type_operation == 'ARCHIVAGE'
        assert entree.details == {'test': True, 'raison': 'test unitaire'}
        assert entree.hmac_hash != ''
        assert len(entree.hmac_hash) == 64

    # ----------------------------------------------------------------------- #
    #  2. JournalOperation : chainage HMAC                                     #
    # ----------------------------------------------------------------------- #

    def test_journal_operation_hmac_chaine(self):
        """Creer 2 entrees : les HMAC doivent etre differents (chainage).
        / Create 2 entries: HMACs must differ (chaining)."""
        from laboutik.archivage import creer_entree_journal

        entree_1 = creer_entree_journal(
            type_operation='ARCHIVAGE',
            details={'numero': 1},
            cle_secrete=self.cle_hmac,
        )
        entree_2 = creer_entree_journal(
            type_operation='VERIFICATION',
            details={'numero': 2},
            cle_secrete=self.cle_hmac,
        )

        # Les deux HMAC doivent etre differents car l'entree 2 chaine sur l'entree 1
        # / Both HMACs must differ because entry 2 chains on entry 1
        assert entree_1.hmac_hash != entree_2.hmac_hash
        assert len(entree_1.hmac_hash) == 64
        assert len(entree_2.hmac_hash) == 64

    # ----------------------------------------------------------------------- #
    #  3. HistoriqueFondDeCaisse : creation directe                            #
    # ----------------------------------------------------------------------- #

    def test_historique_fond_de_caisse_creation(self):
        """Creation directe en base : les montants sont corrects.
        / Direct DB creation: amounts are correct."""
        hist = HistoriqueFondDeCaisse.objects.create(
            ancien_montant=5000,
            nouveau_montant=10000,
            raison='Test direct',
            operateur=self.admin,
            point_de_vente=self.pv,
        )

        hist.refresh_from_db()
        assert hist.ancien_montant == 5000
        assert hist.nouveau_montant == 10000
        assert hist.raison == 'Test direct'

    # ----------------------------------------------------------------------- #
    #  4. HistoriqueFondDeCaisse : via API fond-de-caisse                      #
    # ----------------------------------------------------------------------- #

    def test_historique_fond_via_api(self):
        """POST sur /laboutik/caisse/fond-de-caisse/ : un HistoriqueFondDeCaisse est cree.
        / POST to /laboutik/caisse/fond-de-caisse/: a HistoriqueFondDeCaisse is created."""
        # Le fond de caisse initial est 5000 centimes (50.00 €)
        # / Initial cash float is 5000 cents (50.00 €)
        ancien_montant = self.config.fond_de_caisse

        response = self.c.post('/laboutik/caisse/fond-de-caisse/', {
            'montant_euros': '100.00',
        })
        assert response.status_code == 200

        # Verifier qu'un HistoriqueFondDeCaisse a ete cree
        # / Verify a HistoriqueFondDeCaisse was created
        hist = HistoriqueFondDeCaisse.objects.order_by('-datetime').first()
        assert hist is not None
        assert hist.ancien_montant == ancien_montant  # 5000
        assert hist.nouveau_montant == 10000  # 100.00 € = 10000 centimes

    # ----------------------------------------------------------------------- #
    #  5. Archivage : genere un ZIP                                            #
    # ----------------------------------------------------------------------- #

    def test_archiver_genere_zip(self):
        """call_command('archiver_donnees') genere un fichier ZIP non vide.
        / call_command('archiver_donnees') generates a non-empty ZIP file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut='2020-01-01',
                fin='2020-12-31',
                output=tmpdir,
            )

            # Trouver le fichier ZIP genere / Find the generated ZIP file
            fichiers = [f for f in os.listdir(tmpdir) if f.endswith('.zip')]
            assert len(fichiers) == 1, f"Attendu 1 ZIP, trouve {len(fichiers)}"

            chemin_zip = os.path.join(tmpdir, fichiers[0])
            taille = os.path.getsize(chemin_zip)
            assert taille > 0, "Le fichier ZIP ne doit pas etre vide"

    # ----------------------------------------------------------------------- #
    #  6. Archive : contient les fichiers attendus                             #
    # ----------------------------------------------------------------------- #

    def test_archive_contient_fichiers_attendus(self):
        """Le ZIP contient 9 fichiers : 6 CSV + donnees.json + meta.json + hash.json.
        / The ZIP contains 9 files: 6 CSVs + donnees.json + meta.json + hash.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut='2020-01-01',
                fin='2020-12-31',
                output=tmpdir,
            )

            fichiers_zip = [f for f in os.listdir(tmpdir) if f.endswith('.zip')]
            chemin_zip = os.path.join(tmpdir, fichiers_zip[0])

            with zipfile.ZipFile(chemin_zip, 'r') as zf:
                noms = set(zf.namelist())

            attendus = {
                'lignes_article.csv', 'clotures.csv', 'corrections.csv',
                'impressions.csv', 'sorties_caisse.csv', 'historique_fond.csv',
                'donnees.json', 'meta.json', 'hash.json',
            }
            assert noms == attendus, f"Fichiers manquants ou en trop : {noms.symmetric_difference(attendus)}"

    # ----------------------------------------------------------------------- #
    #  7. Archive : hash integrite OK                                          #
    # ----------------------------------------------------------------------- #

    def test_archive_hash_integrite(self):
        """Lire le ZIP, appeler verifier_hash_archive(), est_valide doit etre True.
        / Read the ZIP, call verifier_hash_archive(), est_valide must be True."""
        from laboutik.archivage import verifier_hash_archive

        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut='2020-01-01',
                fin='2020-12-31',
                output=tmpdir,
            )

            fichiers_zip = [f for f in os.listdir(tmpdir) if f.endswith('.zip')]
            chemin_zip = os.path.join(tmpdir, fichiers_zip[0])

            with open(chemin_zip, 'rb') as f:
                zip_bytes = f.read()

            est_valide, _details = verifier_hash_archive(zip_bytes, self.cle_hmac)
            assert est_valide is True

    # ----------------------------------------------------------------------- #
    #  8. Archive : periode max 1 an (365 jours)                               #
    # ----------------------------------------------------------------------- #

    def test_archive_periode_max_1_an(self):
        """Periode > 365 jours : CommandError avec '365' dans le message.
        / Period > 365 days: CommandError with '365' in message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(CommandError, match='365'):
                call_command(
                    'archiver_donnees',
                    schema=self.tenant.schema_name,
                    debut='2020-01-01',
                    fin='2021-06-01',
                    output=tmpdir,
                )

    # ----------------------------------------------------------------------- #
    #  9. Verification archive OK                                              #
    # ----------------------------------------------------------------------- #

    def test_verifier_archive_ok(self):
        """Creer une archive puis la verifier : pas de sys.exit(1).
        / Create an archive then verify: no sys.exit(1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut='2020-01-01',
                fin='2020-12-31',
                output=tmpdir,
            )

            fichiers_zip = [f for f in os.listdir(tmpdir) if f.endswith('.zip')]
            chemin_zip = os.path.join(tmpdir, fichiers_zip[0])

            # La verification ne doit PAS lever SystemExit
            # / Verification must NOT raise SystemExit
            call_command(
                'verifier_archive',
                archive=chemin_zip,
                schema=self.tenant.schema_name,
            )

    # ----------------------------------------------------------------------- #
    #  10. Verification archive KO (fichier modifie)                           #
    # ----------------------------------------------------------------------- #

    def test_verifier_archive_ko(self):
        """Creer une archive, modifier un fichier dans le ZIP, verifier → sys.exit(1).
        / Create an archive, modify a file inside the ZIP, verify → sys.exit(1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut='2020-01-01',
                fin='2020-12-31',
                output=tmpdir,
            )

            fichiers_zip = [f for f in os.listdir(tmpdir) if f.endswith('.zip')]
            chemin_zip = os.path.join(tmpdir, fichiers_zip[0])

            # Lire le ZIP original, modifier un CSV, re-ecrire le ZIP
            # / Read original ZIP, modify a CSV, re-write the ZIP
            with open(chemin_zip, 'rb') as f:
                zip_bytes_original = f.read()

            buffer_in = io.BytesIO(zip_bytes_original)
            buffer_out = io.BytesIO()

            with zipfile.ZipFile(buffer_in, 'r') as zf_in:
                with zipfile.ZipFile(buffer_out, 'w', zipfile.ZIP_DEFLATED) as zf_out:
                    for nom in zf_in.namelist():
                        contenu = zf_in.read(nom)
                        if nom == 'lignes_article.csv':
                            # Alterer le contenu / Tamper with the content
                            contenu = contenu + b'\nDONNEES FALSIFIEES'
                        zf_out.writestr(nom, contenu)

            # Ecrire le ZIP modifie / Write the modified ZIP
            with open(chemin_zip, 'wb') as f:
                f.write(buffer_out.getvalue())

            # La verification doit lever SystemExit(1)
            # / Verification must raise SystemExit(1)
            with pytest.raises(SystemExit) as exc_info:
                call_command(
                    'verifier_archive',
                    archive=chemin_zip,
                    schema=self.tenant.schema_name,
                )
            assert exc_info.value.code == 1

    # ----------------------------------------------------------------------- #
    #  11. Acces fiscal : genere un dossier                                    #
    # ----------------------------------------------------------------------- #

    def test_acces_fiscal_genere_dossier(self):
        """call_command('acces_fiscal') genere un dossier avec README.txt, lignes_article.csv, hash.json, meta.json.
        / call_command('acces_fiscal') generates a folder with README.txt, lignes_article.csv, hash.json, meta.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'acces_fiscal',
                schema=self.tenant.schema_name,
                output=tmpdir,
            )

            # Trouver le sous-dossier genere / Find the generated subfolder
            sous_dossiers = [d for d in os.listdir(tmpdir) if os.path.isdir(os.path.join(tmpdir, d))]
            assert len(sous_dossiers) == 1, f"Attendu 1 dossier, trouve {len(sous_dossiers)}"

            chemin_dossier = os.path.join(tmpdir, sous_dossiers[0])
            fichiers_dans_dossier = set(os.listdir(chemin_dossier))

            # Verifier les fichiers attendus / Verify expected files
            for fichier_attendu in ['README.txt', 'lignes_article.csv', 'hash.json', 'meta.json']:
                assert fichier_attendu in fichiers_dans_dossier, (
                    f"Fichier manquant : {fichier_attendu}"
                )

    # ----------------------------------------------------------------------- #
    #  12. JournalOperation apres archivage                                    #
    # ----------------------------------------------------------------------- #

    def test_journal_operation_apres_archivage(self):
        """Compter les JournalOperation avant/apres archivage : +1 avec type ARCHIVAGE.
        / Count JournalOperation before/after archiving: +1 with type ARCHIVAGE."""
        nb_avant = JournalOperation.objects.count()

        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut='2020-01-01',
                fin='2020-12-31',
                output=tmpdir,
            )

        nb_apres = JournalOperation.objects.count()
        assert nb_apres == nb_avant + 1

        # La derniere entree est de type ARCHIVAGE
        # / The last entry has type ARCHIVAGE
        derniere = JournalOperation.objects.order_by('-datetime', '-pk').first()
        assert derniere.type_operation == 'ARCHIVAGE'

    # ----------------------------------------------------------------------- #
    #  13. Archive CSV : contenu lignes_article.csv                            #
    # ----------------------------------------------------------------------- #

    def test_archive_csv_contenu(self):
        """Ouvrir le ZIP, lire lignes_article.csv : en-tetes corrects et au moins 1 ligne de donnees.
        / Open ZIP, read lignes_article.csv: correct headers and at least 1 data row."""
        # Utiliser une periode d'1 an qui couvre aujourd'hui (auto_now_add = now)
        # / Use a 1-year period that covers today (auto_now_add = now)
        from datetime import date, timedelta
        aujourd_hui = date.today()
        debut = (aujourd_hui - timedelta(days=180)).isoformat()
        fin = (aujourd_hui + timedelta(days=180)).isoformat()

        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut=debut,
                fin=fin,
                output=tmpdir,
            )

            fichiers_zip = [f for f in os.listdir(tmpdir) if f.endswith('.zip')]
            chemin_zip = os.path.join(tmpdir, fichiers_zip[0])

            with zipfile.ZipFile(chemin_zip, 'r') as zf:
                csv_bytes = zf.read('lignes_article.csv')

            # Le CSV commence par BOM UTF-8 / CSV starts with UTF-8 BOM
            contenu = csv_bytes.decode('utf-8-sig')
            lignes = contenu.strip().split('\n')

            # Au moins l'en-tete + 1 ligne de donnees / At least header + 1 data row
            assert len(lignes) >= 2, f"Attendu au moins 2 lignes (header + data), trouve {len(lignes)}"

            # Verifier les en-tetes / Verify headers
            en_tete = lignes[0]
            for colonne in ['uuid', 'datetime', 'prix_ttc_centimes', 'payment_method', 'taux_tva']:
                assert colonne in en_tete, f"Colonne manquante dans l'en-tete : {colonne}"

    # ----------------------------------------------------------------------- #
    #  14. Archive meta.json : contenu                                         #
    # ----------------------------------------------------------------------- #

    def test_archive_meta_json(self):
        """Ouvrir le ZIP, lire meta.json : contient 'organisation', 'schema', compteurs.lignes_article.
        / Open ZIP, read meta.json: contains 'organisation', 'schema', compteurs.lignes_article."""
        # Periode d'1 an couvrant aujourd'hui / 1-year period covering today
        from datetime import date, timedelta
        aujourd_hui = date.today()
        debut = (aujourd_hui - timedelta(days=180)).isoformat()
        fin = (aujourd_hui + timedelta(days=180)).isoformat()

        with tempfile.TemporaryDirectory() as tmpdir:
            call_command(
                'archiver_donnees',
                schema=self.tenant.schema_name,
                debut=debut,
                fin=fin,
                output=tmpdir,
            )

            fichiers_zip = [f for f in os.listdir(tmpdir) if f.endswith('.zip')]
            chemin_zip = os.path.join(tmpdir, fichiers_zip[0])

            with zipfile.ZipFile(chemin_zip, 'r') as zf:
                meta_bytes = zf.read('meta.json')

            meta = json.loads(meta_bytes.decode('utf-8'))

            # Cles attendues / Expected keys
            assert 'organisation' in meta, "Cle 'organisation' manquante dans meta.json"
            assert 'schema' in meta, "Cle 'schema' manquante dans meta.json"
            assert meta['schema'] == self.tenant.schema_name

            # Compteurs / Counters
            assert 'compteurs' in meta, "Cle 'compteurs' manquante dans meta.json"
            compteurs = meta['compteurs']
            assert 'lignes_article' in compteurs, "Cle 'lignes_article' manquante dans compteurs"
            # Au moins 1 ligne d'article (celle creee dans setUp)
            # / At least 1 article line (the one created in setUp)
            assert compteurs['lignes_article'] >= 1
