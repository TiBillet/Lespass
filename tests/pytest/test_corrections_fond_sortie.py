"""
tests/pytest/test_corrections_fond_sortie.py — Session 17 : corrections, fond de caisse, sortie.
/ Session 17: payment corrections, cash float, cash withdrawal.

Couvre :
- Correction moyen de paiement (ESP/CB/CHQ) avec trace d'audit CorrectionPaiement
- Garde NFC interdit (ancien et nouveau moyen)
- Garde post-cloture interdit (la vente est couverte par la derniere cloture
  journaliere du lieu, `comptabilite.ClotureCaisse`)
- Garde raison obligatoire
- Fond de caisse GET/POST
- Sortie de caisse avec ventilation et total recalcule serveur

Seule une vente reglee se corrige : chaque ligne corrigee ici appartient a une vente
reglee, ecrite par le service de vente (`fabriques_vente.py`). La cloture journaliere
est creee par la vraie tache (`comptabilite.tasks.generer_cloture_pour_tenant`) : elle
lit toutes les ventes du lieu, d'ou le schema dedie de ce fichier.
/ Only a settled sale is corrected: every corrected line here belongs to a settled
sale written by the sale service. The daily closure comes from the real task.

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
from django.utils import translation
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

import comptabilite.tasks
from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod, CategorieProduct,
)
from BaseBillet.models_vente import Vente
from comptabilite.models import ClotureCaisse
from fabriques_vente import fabriquer_vente_encaissee
from laboutik.models import (
    CorrectionPaiement, LaboutikConfiguration,
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

        # Active la caisse V2 sur ce tenant de test : les routes POS sont gardees
        # par module_caisse (HasLaBoutikTerminalAccess). Sans ca, acces -> 403.
        # module_caisse exige module_monnaie_locale : on active les deux.
        # / Enable V2 POS on this test tenant: POS routes are guarded by
        # / module_caisse. module_caisse requires module_monnaie_locale.
        # Aucun e-mail de rapport : la cloture journaliere d'un test n'envoie rien.
        # / No report e-mail: a test's daily closure sends nothing.
        from BaseBillet.models import Configuration
        config = Configuration.get_solo()
        config.module_monnaie_locale = True
        config.module_caisse = True
        config.rapport_emails = ''
        config.save()

        # Le singleton de la caisse doit exister en base (tests/PIEGES.md 9.86) : il
        # porte la cle des empreintes des ventes et des clotures.
        # / The register singleton must exist in the database (fingerprint key).
        LaboutikConfiguration.get_solo().save()

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
    #  Helpers : une vente reglee, une cloture journaliere                     #
    #  Helpers: a settled sale, a daily closure                                #
    # ----------------------------------------------------------------------- #

    def _creer_tarif_vendu_de_la_biere(self):
        """Le tarif vendu (5,00 €) qu'une ligne de biere reference.
        / The sold price (5.00 €) a beer line points to."""
        product_sold = ProductSold.objects.create(
            product=self.produit,
        )
        price_sold = PriceSold.objects.create(
            productsold=product_sold,
            price=self.prix,
            qty_solded=1,
            prix=self.prix.prix,
        )
        return price_sold

    def _creer_ligne_d_une_vente_reglee(self, payment_method_code, amount_centimes=500):
        """Une vente de caisse reglee, ecrite par le service de vente : une biere
        (TVA 0) payee avec le moyen donne. La ligne porte aussi ses champs
        historiques (moyen, identifiant du paiement, point de vente), comme une
        vente faite a la caisse. Rend la ligne.
        / A settled register sale written by the sale service: one beer paid with
        the given method. Returns the line."""
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.pv,
            articles=[
                {
                    'pricesold': self._creer_tarif_vendu_de_la_biere(),
                    'quantite': Decimal('1'),
                    'prix_unitaire': amount_centimes,
                    'taux_tva': Decimal('0'),
                    'payment_method': payment_method_code,
                    'uuid_transaction': uuid_module.uuid4(),
                    'point_de_vente': self.pv,
                },
            ],
            reglements=[
                {'moyen': payment_method_code, 'montant': amount_centimes},
            ],
        )
        return vente.articles.get()

    def _cloturer_la_journee(self):
        """Le « Z de fin de service » : la cloture journaliere du lieu, maintenant,
        par la vraie tache. Rend la cloture creee.
        / The end-of-service Z: the venue's daily closure, now, by the real task."""
        uuid_de_la_cloture = comptabilite.tasks.generer_cloture_pour_tenant(
            schema_name=self.tenant.schema_name,
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        )
        assert uuid_de_la_cloture is not None, "La cloture aurait du etre creee."
        return ClotureCaisse.objects.get(uuid=uuid_de_la_cloture)

    # ----------------------------------------------------------------------- #
    #  Tests correction moyen de paiement                                      #
    #  Payment method correction tests                                         #
    # ----------------------------------------------------------------------- #

    def test_correction_espece_vers_cb(self):
        """Correction ESP → CB : 200, CorrectionPaiement creee. La ligne garde son
        moyen (D14) : seule une vente CORRECTION deplace l'argent.
        / Correction CASH → CC: 200, CorrectionPaiement created; the line keeps its
        method (D14)."""
        ligne = self._creer_ligne_d_une_vente_reglee(PaymentMethod.CASH)

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CC,
            'raison': 'Erreur de saisie au moment du paiement',
            'ancien_moyen': ligne.payment_method,
        })

        # Reponse 200 = succes
        # / Response 200 = success
        assert response.status_code == 200

        # La LigneArticle n'est pas modifiee : la vente CORRECTION porte la correction
        # / The LigneArticle is not modified: the CORRECTION sale carries it
        ligne.refresh_from_db()
        assert ligne.payment_method == PaymentMethod.CASH
        assert Vente.objects.filter(
            nature=Vente.Nature.CORRECTION, vente_liee_id=ligne.vente_id
        ).count() == 1

        # Une CorrectionPaiement a ete creee
        # / A CorrectionPaiement was created
        correction = CorrectionPaiement.objects.filter(ligne_article=ligne).first()
        assert correction is not None
        assert correction.ancien_moyen == PaymentMethod.CASH
        assert correction.nouveau_moyen == PaymentMethod.CC
        assert correction.raison == 'Erreur de saisie au moment du paiement'
        assert correction.operateur == self.admin

    def test_correction_cb_vers_cheque(self):
        """Correction CB → CHQ : 200, CorrectionPaiement creee, la ligne garde son
        moyen (D14).
        / Correction CC → CHECK: 200, CorrectionPaiement created, the line keeps its
        method."""
        ligne = self._creer_ligne_d_une_vente_reglee(PaymentMethod.CC)

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CHEQUE,
            'raison': 'Client a paye par cheque finalement',
            'ancien_moyen': ligne.payment_method,
        })

        assert response.status_code == 200
        ligne.refresh_from_db()
        assert ligne.payment_method == PaymentMethod.CC
        correction = CorrectionPaiement.objects.get(ligne_article=ligne)
        assert correction.nouveau_moyen == PaymentMethod.CHEQUE

    def test_correction_nfc_refuse(self):
        """Correction d'un paiement NFC (LOCAL_EURO) : 400.
        Les paiements cashless sont lies a des Transactions fedow_core.
        / NFC payment correction (LOCAL_EURO): 400.
        Cashless payments are linked to fedow_core Transactions."""
        ligne = self._creer_ligne_d_une_vente_reglee(PaymentMethod.LOCAL_EURO)

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CASH,
            'raison': 'Test correction NFC',
            'ancien_moyen': ligne.payment_method,
        })

        assert response.status_code == 400
        with translation.override(response['Content-Language']):
            message_de_refus_attendu = translation.gettext(
                'Les paiements cashless ne peuvent pas etre modifies'
            )
        assert message_de_refus_attendu in response.content.decode()
        # La LigneArticle n'a PAS ete modifiee
        # / The LigneArticle was NOT modified
        ligne.refresh_from_db()
        assert ligne.payment_method == PaymentMethod.LOCAL_EURO

    def test_correction_vers_nfc_refuse(self):
        """Conversion vers NFC (LOCAL_EURO) : 400.
        On ne peut pas convertir en cashless apres coup.
        / Conversion to NFC (LOCAL_EURO): 400.
        Cannot convert to cashless after the fact."""
        ligne = self._creer_ligne_d_une_vente_reglee(PaymentMethod.CASH)

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.LOCAL_EURO,
            'raison': 'Test conversion vers NFC',
            'ancien_moyen': ligne.payment_method,
        })

        assert response.status_code == 400
        ligne.refresh_from_db()
        assert ligne.payment_method == PaymentMethod.CASH

    def test_correction_post_cloture_refuse(self):
        """Correction d'une vente couverte par une cloture : 400.
        Les ventes couvertes par la cloture journaliere sont immuables (LNE Ex.4).
        / Correction of a sale covered by a closure: 400.
        Sales covered by the daily closure are immutable (LNE req. 4)."""
        ligne = self._creer_ligne_d_une_vente_reglee(PaymentMethod.CASH)

        # La cloture journaliere du lieu couvre cette vente : c'est sa derniere vente.
        # / The venue's daily closure covers this sale: it is its last sale.
        cloture_journaliere = self._cloturer_la_journee()
        assert cloture_journaliere.numero_derniere_vente == ligne.vente.numero

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CC,
            'raison': 'Tentative apres cloture',
            'ancien_moyen': ligne.payment_method,
        })

        assert response.status_code == 400
        with translation.override(response['Content-Language']):
            message_de_refus_attendu = translation.gettext(
                'Cette vente est couverte par une cloture. Modification interdite.'
            )
        assert message_de_refus_attendu in response.content.decode()
        ligne.refresh_from_db()
        assert ligne.payment_method == PaymentMethod.CASH

    def test_correction_raison_optionnelle_acceptee(self):
        """Correction sans raison : 200. La raison est optionnelle.
        / Correction without reason: 200. Reason is optional."""
        ligne = self._creer_ligne_d_une_vente_reglee(PaymentMethod.CASH)

        # Raison vide → acceptee
        # / Empty reason → accepted
        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CC,
            'raison': '',
            'ancien_moyen': ligne.payment_method,
        })
        assert response.status_code == 200

        # La CorrectionPaiement est creee avec raison vide
        # / CorrectionPaiement created with empty reason
        correction = CorrectionPaiement.objects.filter(ligne_article=ligne).first()
        assert correction is not None
        assert correction.raison == ''
        assert correction.nouveau_moyen == PaymentMethod.CC

    def test_correction_multi_articles_toute_la_transaction(self):
        """Correction d'une transaction avec 3 articles : TOUT l'argent en especes de
        la vente est deplace (une vente CORRECTION de 1500), et chaque ligne recoit sa
        trace. Aucune ligne ne change de moyen (D14).
        / Correction of a transaction with 3 articles: ALL the sale's cash is moved
        (one CORRECTION of 1500), one trail per line, no line changes its method."""
        # Une vente reglee de 3 articles, payes ensemble en especes : 3 lignes avec
        # le meme uuid_transaction (1 panier = 3 articles), un reglement de 3 x 500.
        # / One settled sale of 3 items paid together in cash: same uuid_transaction.
        uuid_tx_commun = uuid_module.uuid4()
        articles_du_panier = []
        for _numero_de_l_article in range(3):
            articles_du_panier.append({
                'pricesold': self._creer_tarif_vendu_de_la_biere(),
                'quantite': Decimal('1'),
                'prix_unitaire': 500,
                'taux_tva': Decimal('0'),
                'payment_method': PaymentMethod.CASH,
                'uuid_transaction': uuid_tx_commun,
                'point_de_vente': self.pv,
            })
        vente_du_panier = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.pv,
            articles=articles_du_panier,
            reglements=[{'moyen': PaymentMethod.CASH, 'montant': 1500}],
        )
        lignes = list(vente_du_panier.articles.order_by('datetime'))

        # Corriger en envoyant l'UUID de la premiere ligne
        # / Correct by sending the first line's UUID
        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(lignes[0].uuid),
            'nouveau_moyen': PaymentMethod.CC,
            'raison': 'Erreur sur tout le panier',
            'ancien_moyen': lignes[0].payment_method,
        })
        assert response.status_code == 200

        # Les 3 lignes gardent leur moyen ; la vente CORRECTION deplace les 1500
        # / The 3 lines keep their method; the CORRECTION sale moves the 1500
        for ligne in lignes:
            ligne.refresh_from_db()
            assert ligne.payment_method == PaymentMethod.CASH, (
                f"Ligne {ligne.uuid} modifiee : {ligne.payment_method} au lieu de CA"
            )
        vente_de_correction = Vente.objects.get(
            nature=Vente.Nature.CORRECTION, vente_liee=vente_du_panier
        )
        montants_par_moyen = {}
        for reglement in vente_de_correction.reglements.all():
            montants_par_moyen[reglement.moyen] = reglement.montant
        assert montants_par_moyen == {
            PaymentMethod.CASH: -1500,
            PaymentMethod.CC: 1500,
        }

        # 3 CorrectionPaiement creees (une par ligne)
        # / 3 CorrectionPaiement created (one per line)
        nb_corrections = CorrectionPaiement.objects.filter(
            ligne_article__uuid_transaction=uuid_tx_commun,
        ).count()
        assert nb_corrections == 3

    def test_correction_meme_moyen_refuse(self):
        """Correction vers le meme moyen : 400. Pas de correction sans changement.
        / Correction to the same method: 400. No correction without change."""
        ligne = self._creer_ligne_d_une_vente_reglee(PaymentMethod.CASH)

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CASH,
            'raison': 'Pas de changement',
            'ancien_moyen': ligne.payment_method,
        })

        assert response.status_code == 400
        with translation.override(response['Content-Language']):
            message_de_refus_attendu = translation.gettext(
                'Le moyen de paiement est deja identique'
            )
        assert message_de_refus_attendu in response.content.decode()

    def test_correction_sans_ancien_moyen_refuse(self):
        """Correction sans le moyen vu a l'ouverture du formulaire (`ancien_moyen`,
        champ cache, obligatoire) : 400, la ligne n'est pas modifiee.
        / Correction without the method seen when opening the form: 400, unchanged."""
        ligne = self._creer_ligne_d_une_vente_reglee(PaymentMethod.CASH)

        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CC,
            'raison': 'Envoi sans le champ cache',
        })

        assert response.status_code == 400
        ligne.refresh_from_db()
        assert ligne.payment_method == PaymentMethod.CASH
        assert not CorrectionPaiement.objects.filter(ligne_article=ligne).exists()

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

    def test_sortie_de_caisse_aucune_coupure_render_alerte_plein_ecran(self):
        """Le 400 'aucune coupure' renvoie le partial plein ecran avec bouton retour
        vers le formulaire (uuid_pv conserve dans la query string).
        / The 'no denomination' 400 renders the full-screen partial with a back button
        to the form (uuid_pv preserved in query string).
        """
        response = self.c.post('/laboutik/caisse/creer-sortie-de-caisse/', {
            'uuid_pv': str(self.pv.uuid),
            'tag_id_cm': 'TAG123',
        })

        assert response.status_code == 400
        contenu = response.content.decode()

        # Carte d'alerte presente / alert card present
        assert 'data-testid="alerte-vz-card"' in contenu
        assert 'alerte-vz-card-warning' in contenu

        # Bouton retour HTMX present, ciblant le formulaire avec uuid_pv conserve
        # / HTMX back button targeting the form with preserved uuid_pv
        assert 'data-testid="alerte-vz-btn-retour"' in contenu
        assert f'uuid_pv={self.pv.uuid}' in contenu
        assert 'tag_id_cm=TAG123' in contenu
        assert 'hx-target="#ventes-zone"' in contenu

        # Plus d'usage du vieux partial hx_messages.html dans ce flow
        # / No more reference to the old hx_messages.html partial in this flow
        assert 'alerte-messages' not in contenu

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
            'ancien_moyen': PaymentMethod.CASH,
        })

        assert response.status_code == 404

    def test_correction_uuid_invalide_400(self):
        """Correction avec un UUID mal forme : 400 (serializer).
        / Correction with a malformed UUID: 400 (serializer)."""
        response = self.c.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': 'pas-un-uuid',
            'nouveau_moyen': PaymentMethod.CC,
            'raison': 'Test UUID invalide',
            'ancien_moyen': PaymentMethod.CASH,
        })

        assert response.status_code == 400

    # ----------------------------------------------------------------------- #
    #  Tests authentification : acces sans session admin                        #
    #  Auth tests: access without admin session                                #
    # ----------------------------------------------------------------------- #

    def test_correction_non_authentifie_refuse(self):
        """POST correction sans session admin : 403 (HasLaBoutikAccess).
        / POST correction without admin session: 403 (HasLaBoutikAccess)."""
        ligne = self._creer_ligne_d_une_vente_reglee(PaymentMethod.CASH)

        # Client HTTP sans session (pas de force_login)
        # / HTTP client without session (no force_login)
        client_anonyme = TenantClient(self.tenant)

        response = client_anonyme.post('/laboutik/paiement/corriger_moyen_paiement/', {
            'ligne_uuid': str(ligne.uuid),
            'nouveau_moyen': PaymentMethod.CC,
            'raison': 'Tentative non authentifiee',
            'ancien_moyen': ligne.payment_method,
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
