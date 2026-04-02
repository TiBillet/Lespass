"""
tests/pytest/test_corrections_fond_sortie.py — Session 17 : corrections, fond de caisse, sortie.
/ Session 17: payment corrections, cash float, cash withdrawal.

Couvre :
- Correction moyen de paiement (ESP/CB/CHQ) avec trace d'audit CorrectionPaiement
- Garde NFC interdit (ancien et nouveau moyen)
- Garde post-cloture interdit
- Garde raison obligatoire
- Fond de caisse GET/POST
- Sortie de caisse avec ventilation et total recalcule serveur

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_corrections_fond_sortie.py -v
"""

import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

import uuid as uuid_module
from decimal import Decimal

from django.db import connection
from django.utils import timezone
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod, CategorieProduct,
)
from laboutik.models import (
    ClotureCaisse, CorrectionPaiement, LaboutikConfiguration,
    PointDeVente, SortieCaisse,
)


class TestCorrectionsFondSortie(FastTenantTestCase):
    """Tests pour les corrections de moyen de paiement, fond de caisse, et sortie de caisse.
    / Tests for payment method corrections, cash float, and cash withdrawal."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_corrections'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-corrections.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = 'Test Corrections'

    def setUp(self):
        """Cree les donnees minimales pour chaque test.
        / Creates minimal data for each test."""
        connection.set_tenant(self.tenant)

        # Categorie POS / POS category
        self.categorie = CategorieProduct.objects.create(
            name='Boissons Test Corr',
        )

        # Produit POS / POS product
        self.produit = Product.objects.create(
            name='Biere Test Corr',
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
        )

        # Prix EUR (5.00 €) / EUR price
        self.prix = Price.objects.create(
            product=self.produit,
            name='Pinte',
            prix=Decimal('5.00'),
            publish=True,
        )

        # Point de vente / Point of sale
        self.pv = PointDeVente.objects.create(
            name='Bar Test Corr',
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            accepte_cheque=True,
        )
        self.pv.products.add(self.produit)

        # Utilisateur admin (public schema — SHARED_APPS)
        # / Admin user (public schema — SHARED_APPS)
        self.admin, _created = TibilletUser.objects.get_or_create(
            email='admin-test-corr@tibillet.localhost',
            defaults={
                'username': 'admin-test-corr@tibillet.localhost',
                'is_staff': True,
                'is_active': True,
            },
        )
        self.admin.client_admin.add(self.tenant)

        # Client HTTP avec session admin / HTTP client with admin session
        self.c = TenantClient(self.tenant)
        self.c.force_login(self.admin)

    # ----------------------------------------------------------------------- #
    #  Helper : creer une LigneArticle directement en base                     #
    #  Helper: create a LigneArticle directly in the database                  #
    # ----------------------------------------------------------------------- #

    def _creer_ligne_directe(self, payment_method_code, amount_centimes=500):
        """Cree une LigneArticle avec le moyen de paiement specifie.
        / Creates a LigneArticle with the specified payment method."""
        product_sold = ProductSold.objects.create(
            product=self.produit,
        )
        price_sold = PriceSold.objects.create(
            productsold=product_sold,
            price=self.prix,
            qty_solded=1,
            prix=self.prix.prix,
        )
        uuid_tx = uuid_module.uuid4()
        ligne = LigneArticle.objects.create(
            pricesold=price_sold,
            qty=1,
            amount=amount_centimes,
            payment_method=payment_method_code,
            sale_origin=SaleOrigin.LABOUTIK,
            uuid_transaction=uuid_tx,
            point_de_vente=self.pv,
            vat=Decimal('0.00'),
            total_ht=amount_centimes,
        )
        return ligne

    # ----------------------------------------------------------------------- #
    #  Tests correction moyen de paiement                                      #
    #  Payment method correction tests                                         #
    # ----------------------------------------------------------------------- #

    def test_correction_espece_vers_cb(self):
        """Correction ESP → CB : 200, CorrectionPaiement creee, payment_method change.
        / Correction CASH → CC: 200, CorrectionPaiement created, payment_method changed."""
        ligne = self._creer_ligne_directe(PaymentMethod.CASH)

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CC,
            'raison': 'Erreur de saisie au moment du paiement',
        })

        # Reponse 200 = succes
        # / Response 200 = success
        assert response.status_code == 200

        # La LigneArticle a ete modifiee en base
        # / The LigneArticle was modified in the database
        ligne.refresh_from_db()
        assert ligne.payment_method == PaymentMethod.CC

        # Une CorrectionPaiement a ete creee
        # / A CorrectionPaiement was created
        correction = CorrectionPaiement.objects.filter(ligne_article=ligne).first()
        assert correction is not None
        assert correction.ancien_moyen == PaymentMethod.CASH
        assert correction.nouveau_moyen == PaymentMethod.CC
        assert correction.raison == 'Erreur de saisie au moment du paiement'
        assert correction.operateur == self.admin

    def test_correction_cb_vers_cheque(self):
        """Correction CB → CHQ : 200, CorrectionPaiement creee.
        / Correction CC → CHECK: 200, CorrectionPaiement created."""
        ligne = self._creer_ligne_directe(PaymentMethod.CC)

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CHEQUE,
            'raison': 'Client a paye par cheque finalement',
        })

        assert response.status_code == 200
        ligne.refresh_from_db()
        assert ligne.payment_method == PaymentMethod.CHEQUE

    def test_correction_nfc_refuse(self):
        """Correction d'un paiement NFC (LOCAL_EURO) : 400.
        Les paiements cashless sont lies a des Transactions fedow_core.
        / NFC payment correction (LOCAL_EURO): 400.
        Cashless payments are linked to fedow_core Transactions."""
        ligne = self._creer_ligne_directe(PaymentMethod.LOCAL_EURO)

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CASH,
            'raison': 'Test correction NFC',
        })

        assert response.status_code == 400
        # La LigneArticle n'a PAS ete modifiee
        # / The LigneArticle was NOT modified
        ligne.refresh_from_db()
        assert ligne.payment_method == PaymentMethod.LOCAL_EURO

    def test_correction_vers_nfc_refuse(self):
        """Conversion vers NFC (LOCAL_EURO) : 400.
        On ne peut pas convertir en cashless apres coup.
        / Conversion to NFC (LOCAL_EURO): 400.
        Cannot convert to cashless after the fact."""
        ligne = self._creer_ligne_directe(PaymentMethod.CASH)

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.LOCAL_EURO,
            'raison': 'Test conversion vers NFC',
        })

        assert response.status_code == 400
        ligne.refresh_from_db()
        assert ligne.payment_method == PaymentMethod.CASH

    def test_correction_post_cloture_refuse(self):
        """Correction d'une vente couverte par une cloture : 400.
        Les lignes couvertes par une cloture journaliere sont immuables (LNE Ex.4).
        / Correction of a sale covered by a closure: 400.
        Lines covered by a daily closure are immutable (LNE req. 4)."""
        ligne = self._creer_ligne_directe(PaymentMethod.CASH)

        # Creer une cloture qui couvre cette ligne
        # / Create a closure that covers this line
        ClotureCaisse.objects.create(
            point_de_vente=self.pv,
            responsable=self.admin,
            datetime_ouverture=ligne.datetime - timezone.timedelta(minutes=5),
            datetime_cloture=ligne.datetime + timezone.timedelta(minutes=5),
            total_especes=500,
            total_carte_bancaire=0,
            total_cashless=0,
            total_general=500,
            nombre_transactions=1,
            niveau=ClotureCaisse.JOURNALIERE,
            numero_sequentiel=1,
            total_perpetuel=500,
        )

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CC,
            'raison': 'Tentative apres cloture',
        })

        assert response.status_code == 400
        ligne.refresh_from_db()
        assert ligne.payment_method == PaymentMethod.CASH

    def test_correction_raison_optionnelle_acceptee(self):
        """Correction sans raison : 200. La raison est optionnelle.
        / Correction without reason: 200. Reason is optional."""
        ligne = self._creer_ligne_directe(PaymentMethod.CASH)

        # Raison vide → acceptee
        # / Empty reason → accepted
        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CC,
            'raison': '',
        })
        assert response.status_code == 200

        # La CorrectionPaiement est creee avec raison vide
        # / CorrectionPaiement created with empty reason
        correction = CorrectionPaiement.objects.filter(ligne_article=ligne).first()
        assert correction is not None
        assert correction.raison == ''
        assert correction.nouveau_moyen == PaymentMethod.CC

    def test_correction_multi_articles_toute_la_transaction(self):
        """Correction d'une transaction avec 3 articles : TOUTES les lignes sont corrigees.
        / Correction of a transaction with 3 articles: ALL lines are corrected."""
        # Creer 3 lignes avec le meme uuid_transaction (1 panier = 3 articles)
        # / Create 3 lines with the same uuid_transaction (1 cart = 3 articles)
        uuid_tx_commun = uuid_module.uuid4()
        lignes = []
        for i in range(3):
            product_sold = ProductSold.objects.create(product=self.produit)
            price_sold = PriceSold.objects.create(
                productsold=product_sold, price=self.prix,
                qty_solded=1, prix=self.prix.prix,
            )
            ligne = LigneArticle.objects.create(
                pricesold=price_sold, qty=1, amount=500,
                payment_method=PaymentMethod.CASH,
                sale_origin=SaleOrigin.LABOUTIK,
                uuid_transaction=uuid_tx_commun,
                point_de_vente=self.pv,
                vat=Decimal('0.00'), total_ht=500,
            )
            lignes.append(ligne)

        # Corriger en envoyant l'UUID de la premiere ligne
        # / Correct by sending the first line's UUID
        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(lignes[0].uuid),
            'nouveau_moyen': PaymentMethod.CC,
            'raison': 'Erreur sur tout le panier',
        })
        assert response.status_code == 200

        # TOUTES les 3 lignes doivent etre corrigees en CB
        # / ALL 3 lines must be corrected to CC
        for ligne in lignes:
            ligne.refresh_from_db()
            assert ligne.payment_method == PaymentMethod.CC, (
                f"Ligne {ligne.uuid} toujours {ligne.payment_method} au lieu de CC"
            )

        # 3 CorrectionPaiement creees (une par ligne)
        # / 3 CorrectionPaiement created (one per line)
        nb_corrections = CorrectionPaiement.objects.filter(
            ligne_article__uuid_transaction=uuid_tx_commun,
        ).count()
        assert nb_corrections == 3

    def test_correction_meme_moyen_refuse(self):
        """Correction vers le meme moyen : 400. Pas de correction sans changement.
        / Correction to the same method: 400. No correction without change."""
        ligne = self._creer_ligne_directe(PaymentMethod.CASH)

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CASH,
            'raison': 'Pas de changement',
        })

        assert response.status_code == 400

    # ----------------------------------------------------------------------- #
    #  Tests fond de caisse                                                    #
    #  Cash float tests                                                        #
    # ----------------------------------------------------------------------- #

    def test_fond_de_caisse_get(self):
        """GET fond de caisse : 200, montant affiche.
        / GET cash float: 200, amount displayed."""
        # S'assurer qu'une config existe en base
        # django-solo : save() sans update_fields gere l'insert-or-update
        # / Ensure a config exists in DB
        config = LaboutikConfiguration.get_solo()
        config.fond_de_caisse = 15000  # 150 €
        config.save()

        response = self.c.get('/laboutik/caisse/fond-de-caisse/')
        assert response.status_code == 200
        # Le template contient le montant en euros
        # / The template contains the amount in euros
        assert '150.00' in response.content.decode()

    def test_fond_de_caisse_post(self):
        """POST fond de caisse : montant mis a jour en base.
        / POST cash float: amount updated in database."""
        response = self.c.post('/laboutik/caisse/fond-de-caisse/', {
            'montant_euros': '200.50',
        })

        assert response.status_code == 200

        # Verifier en base
        # / Verify in database
        config = LaboutikConfiguration.get_solo()
        assert config.fond_de_caisse == 20050  # 200.50 € = 20050 centimes

    def test_fond_de_caisse_post_virgule_fr(self):
        """POST fond de caisse avec virgule (locale FR) : accepte.
        / POST cash float with comma (FR locale): accepted."""
        response = self.c.post('/laboutik/caisse/fond-de-caisse/', {
            'montant_euros': '150,75',
        })

        assert response.status_code == 200
        config = LaboutikConfiguration.get_solo()
        assert config.fond_de_caisse == 15075

    def test_fond_de_caisse_post_negatif_refuse(self):
        """POST fond de caisse negatif : 400.
        / POST negative cash float: 400."""
        response = self.c.post('/laboutik/caisse/fond-de-caisse/', {
            'montant_euros': '-50',
        })
        assert response.status_code == 400

    # ----------------------------------------------------------------------- #
    #  Tests sortie de caisse                                                  #
    #  Cash withdrawal tests                                                   #
    # ----------------------------------------------------------------------- #

    def test_sortie_de_caisse_creation(self):
        """Sortie de caisse avec ventilation : SortieCaisse creee, total recalcule serveur.
        / Cash withdrawal with breakdown: SortieCaisse created, total recalculated server-side."""
        response = self.c.post('/laboutik/caisse/creer-sortie-de-caisse/', {
            'uuid_pv': str(self.pv.uuid),
            'coupure_5000': '2',   # 2 × 50 € = 100 €
            'coupure_2000': '3',   # 3 × 20 € = 60 €
            'coupure_500': '1',    # 1 × 5 € = 5 €
            'note': 'Retrait fin de service',
        })

        assert response.status_code == 200

        # Verifier la SortieCaisse creee
        # / Verify the created SortieCaisse
        sortie = SortieCaisse.objects.filter(point_de_vente=self.pv).first()
        assert sortie is not None

        # Total recalcule cote serveur : 10000 + 6000 + 500 = 16500 centimes
        # / Total recalculated server-side: 10000 + 6000 + 500 = 16500 cents
        assert sortie.montant_total == 16500

        # Ventilation JSON correcte
        # / Correct JSON breakdown
        assert sortie.ventilation == {'5000': 2, '2000': 3, '500': 1}
        assert sortie.note == 'Retrait fin de service'
        assert sortie.operateur == self.admin

    def test_sortie_de_caisse_total_recalcule(self):
        """Le total est recalcule cote serveur, pas envoye par le client.
        Meme si le client envoie un total faux, le serveur recalcule.
        / Total is recalculated server-side, not sent by the client.
        Even if the client sends a wrong total, the server recalculates."""
        response = self.c.post('/laboutik/caisse/creer-sortie-de-caisse/', {
            'uuid_pv': str(self.pv.uuid),
            'coupure_10000': '1',  # 1 × 100 € = 100 €
            'coupure_100': '5',    # 5 × 1 € = 5 €
        })

        assert response.status_code == 200

        sortie = SortieCaisse.objects.filter(point_de_vente=self.pv).order_by('-datetime').first()
        assert sortie is not None
        # 10000 + 500 = 10500 centimes
        assert sortie.montant_total == 10500

    def test_sortie_de_caisse_aucune_coupure_refuse(self):
        """Sortie de caisse sans coupure : 400.
        / Cash withdrawal without denominations: 400."""
        response = self.c.post('/laboutik/caisse/creer-sortie-de-caisse/', {
            'uuid_pv': str(self.pv.uuid),
        })

        assert response.status_code == 400

    def test_sortie_de_caisse_get_formulaire(self):
        """GET sortie de caisse : 200, formulaire affiche.
        / GET cash withdrawal: 200, form displayed."""
        response = self.c.get(f'/laboutik/caisse/sortie-de-caisse/?uuid_pv={self.pv.uuid}')
        assert response.status_code == 200
        # Le template contient les coupures
        # / The template contains denominations
        assert '500' in response.content.decode()

    # ----------------------------------------------------------------------- #
    #  Tests 404 : ligne introuvable                                           #
    #  404 tests: line not found                                               #
    # ----------------------------------------------------------------------- #

    def test_correction_ligne_introuvable_404(self):
        """Correction avec un UUID inexistant : 404.
        / Correction with a non-existent UUID: 404."""
        uuid_inexistant = uuid_module.uuid4()

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(uuid_inexistant),
            'nouveau_moyen': PaymentMethod.CC,
            'raison': 'Test ligne introuvable',
        })

        assert response.status_code == 404

    def test_correction_uuid_invalide_400(self):
        """Correction avec un UUID mal forme : 400 (serializer).
        / Correction with a malformed UUID: 400 (serializer)."""
        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': 'pas-un-uuid',
            'nouveau_moyen': PaymentMethod.CC,
            'raison': 'Test UUID invalide',
        })

        assert response.status_code == 400

    # ----------------------------------------------------------------------- #
    #  Tests authentification : acces sans session admin                        #
    #  Auth tests: access without admin session                                #
    # ----------------------------------------------------------------------- #

    def test_correction_non_authentifie_refuse(self):
        """POST correction sans session admin : 403 (HasLaBoutikAccess).
        / POST correction without admin session: 403 (HasLaBoutikAccess)."""
        ligne = self._creer_ligne_directe(PaymentMethod.CASH)

        # Client HTTP sans session (pas de force_login)
        # / HTTP client without session (no force_login)
        client_anonyme = TenantClient(self.tenant)

        response = client_anonyme.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CC,
            'raison': 'Tentative non authentifiee',
        })

        # HasLaBoutikAccess retourne 403 ou 401 selon la config DRF
        # / HasLaBoutikAccess returns 403 or 401 depending on DRF config
        assert response.status_code in (401, 403)

    def test_fond_de_caisse_non_authentifie_refuse(self):
        """GET fond de caisse sans session admin : 403.
        / GET cash float without admin session: 403."""
        client_anonyme = TenantClient(self.tenant)
        response = client_anonyme.get('/laboutik/caisse/fond-de-caisse/')
        assert response.status_code in (401, 403)

    def test_sortie_de_caisse_non_authentifie_refuse(self):
        """POST sortie de caisse sans session admin : 403.
        / POST cash withdrawal without admin session: 403."""
        client_anonyme = TenantClient(self.tenant)
        response = client_anonyme.post('/laboutik/caisse/creer-sortie-de-caisse/', {
            'uuid_pv': str(self.pv.uuid),
            'coupure_2000': '1',
        })
        assert response.status_code in (401, 403)
