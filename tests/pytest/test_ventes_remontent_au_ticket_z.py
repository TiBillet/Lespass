"""
tests/pytest/test_ventes_remontent_au_ticket_z.py
Une vente encaissee doit peser sur le ticket X et sur le ticket Z.
/ A collected sale must weigh on the X and Z tickets.

LOCALISATION : tests/pytest/test_ventes_remontent_au_ticket_z.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
Le contrat que les tests de vente du depot ne verifiaient pas. Ils s'arretent
tous a « la LigneArticle existe, avec le bon montant et le bon moyen de
paiement ». C'est necessaire, mais ca ne dit rien de ce qui compte pour le
gestionnaire : **le montant apparait-il sur son ticket de caisse ?**

Une vente peut etre parfaitement enregistree ET rester invisible du rapport — il
suffit qu'elle porte une origine que le rapport ne lit pas. C'est exactement ce
qui s'est produit avec les remboursements de carte et les ventes de tireuse.

Ces tests partent donc des VRAIES routes de paiement, jamais d'une LigneArticle
fabriquee a la main, et remontent jusqu'aux montants du rapport.

/ The contract the repo's sale tests never checked. They all stop at "the line
exists with the right amount"; none asks whether the amount reaches the
register ticket. A sale can be perfectly recorded and still be invisible to the
report — that is what happened with card refunds and tap sales.

POURQUOI `FastTenantTestCase` / WHY FastTenantTestCase
-------------------------------------------------------
Cette classe cree un schema isole et annule tout entre chaque test. On peut donc
asserter des montants EXACTS — `especes == 1100` — la ou les tests qui tournent
sur la base de dev partagee doivent se contenter de deltas ou d'inegalites.
C'est ce qui permet de verifier qu'un total est juste, et pas seulement qu'il a
augmente.
/ This class creates an isolated schema and rolls back between tests, so we can
assert EXACT amounts instead of deltas or inequalities.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_ventes_remontent_au_ticket_z.py -v
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')

import django  # noqa: E402

django.setup()

from datetime import timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402

from django.utils import timezone  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    CategorieProduct, LigneArticle, PaymentMethod, Price, PriceSold, Product,
    ProductSold, SaleOrigin, Tva,
)
from laboutik.models import ClotureCaisse, PointDeVente  # noqa: E402
from laboutik.reports import RapportComptableService  # noqa: E402

# Prix unitaires choisis pour que les totaux ne puissent pas coincider par
# hasard : 5,50 € et 3,20 € ne partagent aucun diviseur parlant, et leurs
# multiples restent distincts.
# / Unit prices chosen so totals cannot coincide by accident.
PRIX_BIERE_EUROS = Decimal('5.50')
PRIX_CAFE_EUROS = Decimal('3.20')

PRIX_BIERE_CENTIMES = 550
PRIX_CAFE_CENTIMES = 320

TAUX_TVA_BIERE = 20
TAUX_TVA_CAFE = 10


class TestLesVentesRemontentAuTicketZ(FastTenantTestCase):
    """Chaque vente passe par sa vraie route, puis on lit le rapport.
    / Every sale goes through its real route, then we read the report."""

    # Schema et domaine PROPRES a ce fichier : deux classes qui partageraient le
    # meme nom de schema se marcheraient dessus, et `Client.name` porte une
    # contrainte d'unicite qu'il faut renseigner explicitement.
    # / Schema and domain specific to this file: two classes sharing a schema
    # name would collide, and Client.name is unique and must be set explicitly.
    @classmethod
    def get_test_schema_name(cls):
        return 'test_ticket_z'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-ticket-z.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = 'Test Ticket Z'

    def setUp(self):
        """Un point de vente, deux produits a taux de TVA differents, un caissier.
        / One point of sale, two products at different VAT rates, one cashier."""
        # `self.tenant` est pose par `FastTenantTestCase.setUpClass`.
        # / self.tenant is set by FastTenantTestCase.setUpClass.
        #
        # Le rollback du test precedent a rendu le `search_path` au schema
        # public : il faut le reposer avant toute ecriture.
        # / The previous test's rollback returned the search_path to public.
        from django.db import connection

        connection.set_tenant(self.tenant)

        # La caisse V2 est derriere un garde d'acces qui exige le module actif,
        # et `module_caisse` depend lui-meme de `module_monnaie_locale`.
        # / The V2 register sits behind an access guard requiring the module,
        # and module_caisse itself depends on module_monnaie_locale.
        from BaseBillet.models import Configuration

        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.save()

        # Le singleton de la caisse n'existe pas encore dans ce schema neuf :
        # `get_solo()` rend un objet en memoire, jamais ecrit. Le paiement
        # incremente ensuite son compteur de tickets avec `update_fields`, ce qui
        # leve « Save with update_fields did not affect any rows ». Un `save()`
        # sans `update_fields` materialise la ligne (PIEGES 9.86).
        # / The register singleton does not exist yet in this fresh schema:
        # get_solo() returns an unsaved in-memory object, and the payment then
        # updates its ticket counter with update_fields, which raises. A plain
        # save() materializes the row.
        from laboutik.models import LaboutikConfiguration

        LaboutikConfiguration.get_solo().save()

        self.categorie = CategorieProduct.objects.create(name='Boissons ticket Z')

        # Le taux de TVA d'une ligne de vente ne vient PAS de `Price.vat`, qui
        # n'est qu'un code d'affichage ('VG', 'DX'...). Il est calcule a la
        # creation de la LigneArticle depuis `Product.tva.tva_rate`, et retombe
        # sur la Configuration si le produit n'en porte aucun (PIEGES 9.66).
        # Pour tester la ventilation, il faut donc de vrais objets Tva.
        # / A line's VAT rate does NOT come from Price.vat, which is only a
        # display code. It is computed from Product.tva.tva_rate at line
        # creation, falling back to the Configuration. Real Tva objects needed.
        tva_a_vingt, _cree = Tva.objects.get_or_create(tva_rate=Decimal(TAUX_TVA_BIERE))
        tva_a_dix, _cree = Tva.objects.get_or_create(tva_rate=Decimal(TAUX_TVA_CAFE))

        self.biere = Product.objects.create(
            name='Biere ticket Z',
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
            prix_achat=Decimal('1.00'),
            tva=tva_a_vingt,
        )
        self.prix_biere = Price.objects.create(
            product=self.biere,
            name='Pinte',
            prix=PRIX_BIERE_EUROS,
        )

        self.cafe = Product.objects.create(
            name='Cafe ticket Z',
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
            prix_achat=Decimal('0.30'),
            tva=tva_a_dix,
        )
        self.prix_cafe = Price.objects.create(
            product=self.cafe,
            name='Tasse',
            prix=PRIX_CAFE_EUROS,
        )

        self.point_de_vente = PointDeVente.objects.create(
            name='Comptoir ticket Z',
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )
        self.point_de_vente.products.add(self.biere, self.cafe)

        # `TibilletUser` vit en SHARED_APPS : `get_or_create` evite un conflit
        # d'unicite si un autre schema de test a deja cree ce compte.
        # / TibilletUser lives in SHARED_APPS: get_or_create avoids a uniqueness
        # clash if another test schema already created this account.
        self.caissier, _cree = TibilletUser.objects.get_or_create(
            email='caissier-ticket-z@tibillet.localhost',
            defaults={
                'username': 'caissier-ticket-z@tibillet.localhost',
                'is_staff': True,
                'is_active': True,
            },
        )
        self.caissier.client_admin.add(self.tenant)

        self.navigateur = TenantClient(self.tenant)
        self.navigateur.force_login(self.caissier)

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _encaisser(self, moyen_de_paiement, produit, prix, quantite=1):
        """Encaisse une vente par la VRAIE route de paiement du point de vente.

        Passer par la route plutot que de fabriquer la LigneArticle est tout
        l'interet de ce fichier : c'est la route qui decide de l'origine, du
        statut, du moyen de paiement et du point de vente. Une LigneArticle
        ecrite a la main court-circuite precisement ce qu'on veut verifier.
        / Going through the route is the whole point: the route decides origin,
        status, payment method and point of sale. A hand-written line
        short-circuits exactly what we want to check.
        """
        prix_centimes = int(round(prix.prix * 100))
        donnees = {
            'uuid_pv': str(self.point_de_vente.uuid),
            'moyen_paiement': moyen_de_paiement,
            'total': str(prix_centimes * quantite),
            'given_sum': '0',
            f'repid-{produit.uuid}': str(quantite),
        }
        reponse = self.navigateur.post('/laboutik/paiement/payer/', data=donnees)
        assert reponse.status_code == 200, reponse.content.decode()[:400]
        return reponse

    def _rapport(self):
        """Le rapport de caisse sur une fenetre qui encadre tout le test.
        / The register report over a window framing the whole test."""
        maintenant = timezone.now()
        return RapportComptableService(
            point_de_vente=self.point_de_vente,
            datetime_debut=maintenant - timedelta(hours=1),
            datetime_fin=maintenant + timedelta(hours=1),
        )

    # ------------------------------------------------------------------
    # Les moyens de paiement du comptoir
    # ------------------------------------------------------------------

    def test_une_vente_en_especes_pese_sur_le_total_especes(self):
        """Deux pintes reglees en liquide : 11,00 € au poste especes.
        / Two pints paid in cash: 11.00 € under the cash heading."""
        self._encaisser('espece', self.biere, self.prix_biere, quantite=2)

        totaux = self._rapport().calculer_totaux_par_moyen()

        assert totaux['especes'] == 2 * PRIX_BIERE_CENTIMES
        assert totaux['carte_bancaire'] == 0
        assert totaux['total'] == 2 * PRIX_BIERE_CENTIMES

    def test_une_vente_par_carte_bancaire_pese_sur_le_total_carte(self):
        """Une pinte reglee par carte : rien au poste especes.
        / One pint paid by card: nothing under the cash heading."""
        self._encaisser('carte_bancaire', self.biere, self.prix_biere)

        totaux = self._rapport().calculer_totaux_par_moyen()

        assert totaux['carte_bancaire'] == PRIX_BIERE_CENTIMES
        assert totaux['especes'] == 0
        assert totaux['total'] == PRIX_BIERE_CENTIMES

    def test_le_total_general_est_la_somme_des_moyens_encaisses(self):
        """Trois ventes, deux moyens : le total doit valoir leur somme exacte.

        C'est la verification qu'aucun test du depot ne faisait : un moyen de
        paiement oublie dans l'addition du total passerait inapercu tant qu'on
        ne verifie chaque poste qu'isolement.
        / No repo test did this: a payment method left out of the total would go
        unnoticed as long as each heading is only checked in isolation.
        """
        self._encaisser('espece', self.biere, self.prix_biere, quantite=2)
        self._encaisser('carte_bancaire', self.cafe, self.prix_cafe, quantite=3)

        totaux = self._rapport().calculer_totaux_par_moyen()

        especes_attendues = 2 * PRIX_BIERE_CENTIMES
        carte_attendue = 3 * PRIX_CAFE_CENTIMES

        assert totaux['especes'] == especes_attendues
        assert totaux['carte_bancaire'] == carte_attendue
        assert totaux['total'] == especes_attendues + carte_attendue

    # ------------------------------------------------------------------
    # Le detail : produits, categories, TVA
    # ------------------------------------------------------------------

    def test_le_detail_des_ventes_nomme_les_produits_vendus(self):
        """Le produit vendu apparait dans le detail, sous sa categorie.

        Ce detail alimente le PDF et le CSV envoyes au gestionnaire. S'il est
        vide, le ticket ne justifie plus rien.
        / This detail feeds the PDF and CSV sent to the manager.
        """
        self._encaisser('espece', self.biere, self.prix_biere, quantite=2)

        detail = self._rapport().calculer_detail_ventes()

        assert self.categorie.name in detail
        noms_vendus = [
            article['nom'] for article in detail[self.categorie.name]['articles']
        ]
        assert self.biere.name in noms_vendus
        assert detail[self.categorie.name]['total_ttc'] == 2 * PRIX_BIERE_CENTIMES

    def test_la_ventilation_tva_separe_les_taux(self):
        """Deux produits a taux differents produisent deux lignes de TVA.

        La ventilation TVA est ce qu'un controle fiscal regarde en premier.
        Melanger deux taux, ou en perdre un, rend la cloture inexploitable.
        / The VAT breakdown is the first thing an audit looks at.
        """
        self._encaisser('espece', self.biere, self.prix_biere)
        self._encaisser('espece', self.cafe, self.prix_cafe)

        tva = self._rapport().calculer_tva()

        assert '20.00%' in tva
        assert '10.00%' in tva
        assert tva['20.00%']['total_ttc'] == PRIX_BIERE_CENTIMES
        assert tva['10.00%']['total_ttc'] == PRIX_CAFE_CENTIMES

    def test_le_montant_hors_taxe_se_deduit_du_ttc(self):
        """HT + TVA doit redonner exactement le TTC encaisse.

        L'arrondi se fait au centime : la somme des deux doit retomber sur le
        montant reellement encaisse, sans centime perdu.
        / Rounding is done to the cent: HT + VAT must land back exactly on the
        collected amount, with no cent lost.
        """
        self._encaisser('espece', self.biere, self.prix_biere, quantite=4)

        ligne_de_tva = self._rapport().calculer_tva()['20.00%']

        assert (
            ligne_de_tva['total_ht'] + ligne_de_tva['total_tva']
            == ligne_de_tva['total_ttc']
        )
        assert ligne_de_tva['total_ttc'] == 4 * PRIX_BIERE_CENTIMES

    # ------------------------------------------------------------------
    # Le solde du tiroir
    # ------------------------------------------------------------------

    def test_le_solde_de_caisse_suit_les_encaissements_en_especes(self):
        """Le solde annonce doit correspondre a ce qu'il y a dans le tiroir.

        C'est ce que le caissier compare a son comptage physique en fin de
        service. Une carte bancaire ne remplit pas le tiroir : elle ne doit pas
        entrer dans ce solde.
        / This is what the cashier compares to the physical count. A card payment
        does not fill the till and must not enter this balance.
        """
        self._encaisser('espece', self.biere, self.prix_biere, quantite=2)
        self._encaisser('carte_bancaire', self.biere, self.prix_biere)

        solde = self._rapport().calculer_solde_caisse()

        assert solde['entrees_especes'] == 2 * PRIX_BIERE_CENTIMES
        assert solde['solde'] == solde['fond_de_caisse'] + 2 * PRIX_BIERE_CENTIMES

    # ------------------------------------------------------------------
    # Le perimetre : ce qui entre, ce qui reste dehors
    # ------------------------------------------------------------------

    def test_une_vente_en_ligne_n_entre_pas_dans_le_rapport_de_caisse(self):
        """Une vente de la billetterie en ligne ne pese pas sur le tiroir.

        Les ventes en ligne sont suivies par le service de comptabilite, qui
        exclut justement la caisse. Les compter des deux cotes doublerait le
        chiffre d'affaires.
        / Online sales are tracked by the accounting service, which excludes the
        register. Counting them twice would double the revenue.
        """
        self._encaisser('espece', self.biere, self.prix_biere)

        # Une vente en ligne, ecrite directement : elle ne passe pas par la
        # caisse, donc il n'y a pas de route de point de vente a appeler.
        #
        # Elle porte volontairement `CASH`, un moyen que le rapport SAIT
        # additionner. Avec un moyen qu'il ignore (`STRIPE_NOFED` par exemple),
        # le test passerait meme si l'origine entrait dans le perimetre : il ne
        # prouverait plus rien. C'est ce que l'exclusion doit ecarter, pas
        # l'arithmetique des moyens de paiement.
        # / It deliberately carries CASH, a method the report knows how to sum.
        # With a method it ignores, the test would pass even if the origin
        # entered the scope, proving nothing.
        produit_vendu = ProductSold.objects.create(product=self.biere)
        tarif_vendu = PriceSold.objects.create(
            productsold=produit_vendu, price=self.prix_biere, prix=PRIX_BIERE_EUROS,
        )
        LigneArticle.objects.create(
            pricesold=tarif_vendu,
            qty=1,
            amount=9999,
            payment_method=PaymentMethod.CASH,
            status=LigneArticle.VALID,
            sale_origin=SaleOrigin.LESPASS,
        )

        totaux = self._rapport().calculer_totaux_par_moyen()

        assert totaux['especes'] == PRIX_BIERE_CENTIMES, (
            "Une vente en ligne s'est glissee dans le rapport de caisse."
        )
        assert totaux['total'] == PRIX_BIERE_CENTIMES

    def test_une_vente_de_tireuse_entre_dans_le_rapport(self):
        """Une biere tiree au comptoir est une vente de caisse.

        Elle porte un point de vente et decremente le stock : l'exclure
        amputerait le chiffre d'affaires et fausserait la marge, puisque le fut
        serait decompte sans recette en face.
        / A tapped beer carries a point of sale and decrements stock: excluding
        it would understate revenue and distort margin.
        """
        produit_vendu = ProductSold.objects.create(product=self.biere)
        tarif_vendu = PriceSold.objects.create(
            productsold=produit_vendu, price=self.prix_biere, prix=PRIX_BIERE_EUROS,
        )
        LigneArticle.objects.create(
            pricesold=tarif_vendu,
            qty=1,
            amount=PRIX_BIERE_CENTIMES,
            vat=TAUX_TVA_BIERE,
            payment_method=PaymentMethod.LOCAL_EURO,
            status=LigneArticle.VALID,
            sale_origin=SaleOrigin.TIREUSE,
            point_de_vente=self.point_de_vente,
        )

        totaux = self._rapport().calculer_totaux_par_moyen()

        assert totaux['cashless'] == PRIX_BIERE_CENTIMES
        assert totaux['total'] == PRIX_BIERE_CENTIMES

    def test_une_vente_annulee_ne_pese_pas_sur_le_rapport(self):
        """Seules les ventes valides comptent.

        Une ligne restee en cours de creation, ou annulee, ne represente aucun
        encaissement : la compter gonflerait la recette annoncee.
        / Only valid sales count. A pending or cancelled line represents no
        collection and would inflate the announced revenue.
        """
        self._encaisser('espece', self.biere, self.prix_biere)

        produit_vendu = ProductSold.objects.create(product=self.biere)
        tarif_vendu = PriceSold.objects.create(
            productsold=produit_vendu, price=self.prix_biere, prix=PRIX_BIERE_EUROS,
        )
        LigneArticle.objects.create(
            pricesold=tarif_vendu,
            qty=1,
            amount=7777,
            payment_method=PaymentMethod.CASH,
            status=LigneArticle.CREATED,
            sale_origin=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
        )

        totaux = self._rapport().calculer_totaux_par_moyen()

        assert totaux['total'] == PRIX_BIERE_CENTIMES

    # ------------------------------------------------------------------
    # Le ticket Z : la cloture fige ce que le ticket X annoncait
    # ------------------------------------------------------------------

    def test_la_cloture_fige_les_montants_annonces_par_le_ticket_x(self):
        """Ticket X et ticket Z doivent dire la meme chose.

        Le ticket X est la photo de l'instant, le ticket Z l'arrete. Si les deux
        divergent, le caissier ne peut plus se fier a ce qu'il voit pendant le
        service.
        / The X ticket is the live snapshot, the Z ticket freezes it. Divergence
        would make the live view untrustworthy.
        """
        self._encaisser('espece', self.biere, self.prix_biere, quantite=2)
        self._encaisser('carte_bancaire', self.cafe, self.prix_cafe, quantite=3)

        totaux_du_ticket_x = self._rapport().calculer_totaux_par_moyen()

        reponse = self.navigateur.post(
            '/laboutik/caisse/cloturer/',
            data={'uuid_pv': str(self.point_de_vente.uuid)},
        )
        assert reponse.status_code == 200, reponse.content.decode()[:400]

        cloture = ClotureCaisse.objects.order_by('-datetime_cloture').first()
        assert cloture is not None

        assert cloture.total_especes == totaux_du_ticket_x['especes']
        assert cloture.total_carte_bancaire == totaux_du_ticket_x['carte_bancaire']
        assert cloture.total_cashless == totaux_du_ticket_x['cashless']
        assert cloture.total_general == totaux_du_ticket_x['total']

    def test_le_ticket_z_porte_le_detail_des_ventes(self):
        """Le rapport fige dans la cloture contient les sections de detail.

        C'est ce que le PDF et le CSV relisent, parfois des annees apres. Un
        rapport fige sans detail rend la cloture injustifiable.
        / This is what the PDF and CSV re-read, sometimes years later.
        """
        self._encaisser('espece', self.biere, self.prix_biere, quantite=2)

        self.navigateur.post(
            '/laboutik/caisse/cloturer/',
            data={'uuid_pv': str(self.point_de_vente.uuid)},
        )
        cloture = ClotureCaisse.objects.order_by('-datetime_cloture').first()

        from laboutik.reports import sections_de_detail_pour_export

        sections = sections_de_detail_pour_export(cloture.rapport_json)

        assert self.biere.name in sections['par_produit']
        assert sections['par_produit'][self.biere.name]['total'] == 2 * PRIX_BIERE_CENTIMES
        assert sections['par_categorie'][self.categorie.name] == 2 * PRIX_BIERE_CENTIMES
        assert sections['par_tva']['20.00%']['total_ttc'] == 2 * PRIX_BIERE_CENTIMES

    def test_une_cloture_sans_vente_est_refusee(self):
        """Cloturer sans rien avoir encaisse n'a pas de sens.

        Une cloture vide creerait un numero sequentiel et un maillon de chaine
        pour rien, et brouillerait la piste d'audit.
        / An empty closure would burn a sequence number and a chain link for
        nothing, blurring the audit trail.
        """
        reponse = self.navigateur.post(
            '/laboutik/caisse/cloturer/',
            data={'uuid_pv': str(self.point_de_vente.uuid)},
        )

        assert reponse.status_code == 400

    def test_deux_clotures_successives_ne_comptent_pas_deux_fois(self):
        """Ce qui a ete cloture ne revient pas dans la cloture suivante.

        C'est la garantie la plus importante de la cloture : sans elle, le
        chiffre d'affaires du mois serait la somme de comptages qui se
        recouvrent.
        / The most important guarantee: without it, monthly revenue would be a
        sum of overlapping counts.
        """
        self._encaisser('espece', self.biere, self.prix_biere, quantite=2)
        self.navigateur.post(
            '/laboutik/caisse/cloturer/',
            data={'uuid_pv': str(self.point_de_vente.uuid)},
        )
        premiere_cloture = ClotureCaisse.objects.order_by('-datetime_cloture').first()

        self._encaisser('espece', self.cafe, self.prix_cafe)
        self.navigateur.post(
            '/laboutik/caisse/cloturer/',
            data={'uuid_pv': str(self.point_de_vente.uuid)},
        )
        seconde_cloture = ClotureCaisse.objects.order_by('-datetime_cloture').first()

        assert seconde_cloture.pk != premiere_cloture.pk
        assert premiere_cloture.total_especes == 2 * PRIX_BIERE_CENTIMES
        assert seconde_cloture.total_especes == PRIX_CAFE_CENTIMES, (
            "La seconde cloture a recompte les ventes de la premiere."
        )

    def test_le_numero_de_cloture_s_incremente(self):
        """Les cloture se suivent sans trou : la piste d'audit en depend.
        / Closures follow one another without gaps: the audit trail depends on it.
        """
        self._encaisser('espece', self.biere, self.prix_biere)
        self.navigateur.post(
            '/laboutik/caisse/cloturer/',
            data={'uuid_pv': str(self.point_de_vente.uuid)},
        )
        premiere = ClotureCaisse.objects.order_by('-datetime_cloture').first()

        self._encaisser('espece', self.cafe, self.prix_cafe)
        self.navigateur.post(
            '/laboutik/caisse/cloturer/',
            data={'uuid_pv': str(self.point_de_vente.uuid)},
        )
        seconde = ClotureCaisse.objects.order_by('-datetime_cloture').first()

        assert seconde.numero_sequentiel == premiere.numero_sequentiel + 1

    def test_un_moyen_de_paiement_non_ventile_manque_au_total_general(self):
        """Une vente reglee par un moyen que le rapport n'additionne pas.

        `calculer_totaux_par_moyen` construit son total en additionnant CINQ
        postes : especes, carte bancaire, cashless, cheque, federe. Toute vente
        de caisse reglee autrement compte dans le NOMBRE de transactions, dans
        le detail des ventes et dans la ventilation TVA — mais pas dans le total
        general. Le ticket ne s'equilibre alors plus avec lui-meme.

        Le cas se produit en vrai : une adhesion reglee depuis un portefeuille
        federe arrive en caisse avec un moyen de paiement inconnu
        (`fedow_connect/views.py`), et le paiement retombe sur « inconnu » des
        que le code de moyen recu ne fait partie d'aucun de ces cinq postes.

        Ce test DECRIT le comportement actuel. Il est la pour que la divergence
        soit connue et mesurable, et pour echouer le jour ou quelqu'un modifie
        la composition du total sans s'en rendre compte.

        / The total sums FIVE headings. A register sale paid any other way counts
        in the transaction count, the sales detail and the VAT breakdown, but not
        in the general total: the ticket no longer balances with itself. This
        test DESCRIBES current behaviour so the divergence stays measurable.
        """
        self._encaisser('espece', self.biere, self.prix_biere)

        produit_vendu = ProductSold.objects.create(product=self.cafe)
        tarif_vendu = PriceSold.objects.create(
            productsold=produit_vendu, price=self.prix_cafe, prix=PRIX_CAFE_EUROS,
        )
        LigneArticle.objects.create(
            pricesold=tarif_vendu,
            qty=1,
            amount=PRIX_CAFE_CENTIMES,
            payment_method=PaymentMethod.UNKNOWN,
            status=LigneArticle.VALID,
            sale_origin=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
        )

        rapport = self._rapport()
        totaux = rapport.calculer_totaux_par_moyen()
        detail = rapport.calculer_detail_ventes()

        # La vente est bien dans le detail : elle existe pour le rapport.
        # / The sale is in the detail: the report does see it.
        total_du_detail = sum(
            donnees['total_ttc'] for donnees in detail.values()
        )
        assert total_du_detail == PRIX_BIERE_CENTIMES + PRIX_CAFE_CENTIMES

        # Mais elle manque au total general.
        # / But it is missing from the general total.
        assert totaux['total'] == PRIX_BIERE_CENTIMES
        assert total_du_detail != totaux['total'], (
            "Le total general couvre desormais tous les moyens de paiement : "
            "mettre a jour ce test, la divergence a ete corrigee."
        )
