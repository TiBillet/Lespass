"""
tests/pytest/test_rapports_cheque.py — Le chèque doit aller jusqu'au bout de la chaîne
comptable. / The check must reach the end of the accounting chain.

LOCALISATION : tests/pytest/test_rapports_cheque.py

POURQUOI CE FICHIER / WHY THIS FILE :
Un chèque est correctement encaissé au comptoir : `"CH"` devient
`PaymentMethod.CHEQUE`, et `RapportComptableService` le compte et l'ajoute au total
général. Puis il disparaît.

`ClotureCaisse` n'a longtemps porté que trois totaux — espèces, carte bancaire,
cashless — et rien pour le chèque. Les lecteurs de ces colonnes ont donc perdu
l'information, et le plus grave de tous est l'archivage LNE, l'archive fiscale
inaltérable, qui écrivait `total_cheque = '0'` EN DUR.

La conséquence tient en une ligne : dès qu'un chèque est encaissé,
`especes + carte + cashless != total_general` dans la clôture stockée, et l'archive
légale est fausse.

C'est cette chaîne, de l'encaissement à l'archive, que ce fichier surveille.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_rapports_cheque.py -v
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import csv
import re
from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.utils import timezone as dj_timezone
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    CategorieProduct,
    Configuration,
    LigneArticle,
    PaymentMethod,
    Price,
    PriceSold,
    Product,
    ProductSold,
    SaleOrigin,
)
import comptabilite.tasks
from comptabilite.models import ClotureCaisse as ClotureCaisseUnique
from fabriques_vente import fabriquer_vente_encaissee, verifier_egalites
from laboutik.models import LaboutikConfiguration, PointDeVente
from laboutik.reports import RapportComptableService
from fabriques_ecran import euros


# Les trois encaissements du scenario, en centimes.
# Trois moyens differents pour que le total general ne puisse pas etre juste par
# hasard : si le cheque etait ignore, le total tomberait a 3000 au lieu de 4500.
# / The scenario's three payments, in cents. Three different methods so the grand
#   total cannot be right by accident.
MONTANT_ESPECES_CENTIMES = 1000
MONTANT_CARTE_CENTIMES = 2000
MONTANT_CHEQUE_CENTIMES = 1500


class TestRapportsCheque(FastTenantTestCase):
    """
    Le chemin complet du chèque : rapport → clôture → archive fiscale.
    / The check's full path: report → closure → tax archive.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_rapports_cheque"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-rapports-cheque.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = "Test Rapports Cheque"

    def setUp(self):
        # Re-poser le search_path apres le rollback du test precedent.
        # / Re-set search_path after the previous test's rollback.
        connection.set_tenant(self.tenant)

        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        # Aucun e-mail de rapport : une clôture journalière n'envoie rien.
        # / No report e-mail: a daily closure sends nothing.
        configuration.rapport_emails = ""
        configuration.save()

        # Le singleton de la caisse porte la clé des empreintes (tests/PIEGES.md 9.86).
        # / The register singleton carries the fingerprint key.
        LaboutikConfiguration.get_solo().save()

        self.categorie = CategorieProduct.objects.create(name="Boissons test cheque")
        self.produit = Product.objects.create(
            name="Biere test cheque",
            categorie_article=Product.VENTE,
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
            publish=True,
        )
        self.prix = Price.objects.create(
            product=self.produit,
            name="Pinte",
            prix=Decimal("5.00"),
            publish=True,
        )
        self.point_de_vente = PointDeVente.objects.create(
            name="Comptoir test cheque",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            accepte_cheque=True,
        )
        self.point_de_vente.products.add(self.produit)

        # La periode observee, large des deux cotes pour que l'heure de la machine
        # n'ait aucune influence sur le resultat.
        # / The observed period, wide on both sides so the machine clock cannot matter.
        self.debut = dj_timezone.now() - timedelta(hours=1)
        self.fin = dj_timezone.now() + timedelta(hours=1)

        # Le caissier, pour cloturer depuis le comptoir comme le fait un humain.
        # / The cashier, to close from the counter the way a human does.
        self.caissier, _cree = TibilletUser.objects.get_or_create(
            email="caissier-rapports-cheque@tibillet.localhost",
            defaults={
                "username": "caissier-rapports-cheque@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        self.caissier.client_admin.add(self.tenant)
        self.client_http = TenantClient(self.tenant)
        self.client_http.force_login(self.caissier)

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _encaisser(self, montant_centimes, moyen_de_paiement):
        """
        Ecrit une ligne de vente encaissee par un moyen donne.
        / Writes one sale line collected by a given payment method.

        On ecrit directement la LigneArticle plutot que de passer par le POS : ce
        fichier teste la CHAINE COMPTABLE, pas le parcours de vente. Le parcours a ses
        propres tests.
        / We write the LigneArticle directly: this file tests the ACCOUNTING CHAIN,
          not the sale journey, which has its own tests.
        """
        product_sold, _cree = ProductSold.objects.get_or_create(
            product=self.produit,
            event=None,
            defaults={"categorie_article": self.produit.categorie_article},
        )
        price_sold, _cree_prix = PriceSold.objects.get_or_create(
            productsold=product_sold,
            price=self.prix,
            defaults={"prix": self.prix.prix},
        )
        return LigneArticle.objects.create(
            pricesold=price_sold,
            qty=1,
            amount=montant_centimes,
            sale_origin=SaleOrigin.LABOUTIK,
            payment_method=moyen_de_paiement,
            status=LigneArticle.VALID,
            point_de_vente=self.point_de_vente,
        )

    def _encaisser_les_trois_moyens(self):
        """Especes, carte bancaire ET cheque. / Cash, card AND check."""
        self._encaisser(MONTANT_ESPECES_CENTIMES, PaymentMethod.CASH)
        self._encaisser(MONTANT_CARTE_CENTIMES, PaymentMethod.CC)
        self._encaisser(MONTANT_CHEQUE_CENTIMES, PaymentMethod.CHEQUE)

    def _vendre(self, montant_centimes, moyen_de_paiement):
        """
        Une vente reglee au comptoir, ecrite par le service de vente : une biere au
        montant donne (TVA 20 %), payee avec un seul moyen. La cloture unique lit les
        VENTES et leurs reglements.
        / A settled counter sale written by the sale service; the single closure reads
        sales and payments.
        """
        product_sold, _cree = ProductSold.objects.get_or_create(
            product=self.produit,
            event=None,
            defaults={"categorie_article": self.produit.categorie_article},
        )
        price_sold, _cree_prix = PriceSold.objects.get_or_create(
            productsold=product_sold,
            price=self.prix,
            defaults={"prix": self.prix.prix},
        )
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            articles=[
                {
                    "pricesold": price_sold,
                    "quantite": Decimal("1"),
                    "prix_unitaire": montant_centimes,
                    "taux_tva": Decimal("20"),
                    "payment_method": moyen_de_paiement,
                    "status": LigneArticle.VALID,
                    "point_de_vente": self.point_de_vente,
                },
            ],
            reglements=[{"moyen": moyen_de_paiement, "montant": montant_centimes}],
        )
        verifier_egalites(vente)
        return vente

    def _vendre_avec_les_trois_moyens(self):
        """
        Trois ventes : especes (1000), carte bancaire (2000) ET cheque (1500).
        / Three sales: cash, card AND check.
        """
        self._vendre(MONTANT_ESPECES_CENTIMES, PaymentMethod.CASH)
        self._vendre(MONTANT_CARTE_CENTIMES, PaymentMethod.CC)
        self._vendre(MONTANT_CHEQUE_CENTIMES, PaymentMethod.CHEQUE)

    def _cloturer_la_journee(self):
        """
        La cloture journaliere unique du lieu (J), creee par la tache de cloture.
        / The venue's single daily closure (J), created by the closure task.
        """
        uuid_de_la_j = comptabilite.tasks.generer_cloture_pour_tenant(
            schema_name=self.tenant.schema_name,
            niveau=ClotureCaisseUnique.NIVEAU_JOURNALIER,
        )
        return ClotureCaisseUnique.objects.get(uuid=uuid_de_la_j)

    def _totaux(self):
        """Les totaux par moyen de paiement sur la periode.
        / Totals per payment method over the period."""
        service = RapportComptableService(self.point_de_vente, self.debut, self.fin)
        return service.calculer_totaux_par_moyen()

    # ------------------------------------------------------------------ #
    #  T1 — Le rapport
    # ------------------------------------------------------------------ #

    def test_le_rapport_isole_le_cheque_et_le_compte_dans_le_total(self):
        """
        Le chèque a sa propre ligne, et il pèse dans le total général.
        / The check has its own line, and it counts toward the grand total.
        """
        self._encaisser_les_trois_moyens()

        totaux = self._totaux()

        self.assertEqual(totaux["cheque"], MONTANT_CHEQUE_CENTIMES)
        self.assertEqual(
            totaux["total"],
            MONTANT_ESPECES_CENTIMES + MONTANT_CARTE_CENTIMES + MONTANT_CHEQUE_CENTIMES,
            "Le total general doit inclure le cheque.",
        )

    # ------------------------------------------------------------------ #
    #  T2 — La cloture stockee
    # ------------------------------------------------------------------ #

    def test_la_cloture_stocke_le_total_cheque(self):
        """
        Ce que la clôture retient du chèque, une fois le rapport oublié.

        Le `rapport_json` garde tout, mais les exports (CSV, PDF) et l'archive LNE
        lisent les COLONNES. Sans colonne pour le chèque, ils ne peuvent pas le voir.
        / The rapport_json keeps everything, but the exports and the tax archive read
          the COLUMNS.
        """
        from laboutik.models import ClotureCaisse

        self._encaisser_les_trois_moyens()
        totaux = self._totaux()

        cloture = ClotureCaisse.objects.create(
            point_de_vente=self.point_de_vente,
            datetime_ouverture=self.debut,
            datetime_cloture=self.fin,
            niveau=ClotureCaisse.JOURNALIERE,
            numero_sequentiel=1,
            total_especes=totaux["especes"],
            total_carte_bancaire=totaux["carte_bancaire"],
            total_cashless=totaux["cashless"],
            total_cheque=totaux["cheque"],
            total_general=totaux["total"],
            nombre_transactions=3,
        )

        self.assertEqual(cloture.total_cheque, MONTANT_CHEQUE_CENTIMES)

    def test_les_totaux_de_la_cloture_se_recomposent_en_total_general(self):
        """
        L'identité comptable qui doit toujours tenir.

        `especes + carte + cashless + cheque == total_general`. Sans colonne chèque,
        cette somme était fausse de tout le montant des chèques : la clôture affichait
        un total général que ses propres lignes ne justifiaient pas.
        / The accounting identity that must always hold.
        """
        from laboutik.models import ClotureCaisse

        self._encaisser_les_trois_moyens()
        totaux = self._totaux()

        cloture = ClotureCaisse.objects.create(
            point_de_vente=self.point_de_vente,
            datetime_ouverture=self.debut,
            datetime_cloture=self.fin,
            niveau=ClotureCaisse.JOURNALIERE,
            numero_sequentiel=1,
            total_especes=totaux["especes"],
            total_carte_bancaire=totaux["carte_bancaire"],
            total_cashless=totaux["cashless"],
            total_cheque=totaux["cheque"],
            total_general=totaux["total"],
            nombre_transactions=3,
        )

        somme_des_moyens = (
            cloture.total_especes
            + cloture.total_carte_bancaire
            + cloture.total_cashless
            + cloture.total_cheque
        )
        self.assertEqual(
            somme_des_moyens,
            cloture.total_general,
            "Les moyens de paiement doivent recomposer exactement le total general.",
        )

    def test_une_cloture_sans_cheque_garde_un_total_cheque_nul(self):
        """
        Le cas courant ne doit pas régresser : sans chèque, le total reste à zéro.
        / The common case must not regress.
        """
        from laboutik.models import ClotureCaisse

        self._encaisser(MONTANT_ESPECES_CENTIMES, PaymentMethod.CASH)
        totaux = self._totaux()

        cloture = ClotureCaisse.objects.create(
            point_de_vente=self.point_de_vente,
            datetime_ouverture=self.debut,
            datetime_cloture=self.fin,
            niveau=ClotureCaisse.JOURNALIERE,
            numero_sequentiel=1,
            total_especes=totaux["especes"],
            total_carte_bancaire=totaux["carte_bancaire"],
            total_cashless=totaux["cashless"],
            total_cheque=totaux["cheque"],
            total_general=totaux["total"],
            nombre_transactions=1,
        )

        self.assertEqual(cloture.total_cheque, 0)

    def test_la_cloture_declenchee_au_comptoir_enregistre_le_total_cheque(self):
        """
        La vraie clôture, celle que le caissier déclenche, doit retenir le chèque.

        Les autres tests de ce fichier écrivent la `ClotureCaisse` eux-mêmes : ils
        prouvent que la colonne existe et qu'elle se lit, pas que le code de clôture
        la remplit. C'est pourtant LE chemin emprunté chaque soir : la clôture manuelle
        extrait les totaux du rapport, et elle en oubliait un.
        / The other tests write the closure themselves: they prove the column exists,
          not that the closing code fills it. This is the path used every evening.

        La clôture du bouton est la J unique : le chèque est un règlement d'argent de
        son rapport (1500), et les règlements d'argent recomposent son chiffre
        d'affaires : 1000 + 2000 + 1500 = 4500.
        / The button's closure is the single J: the check is a money payment of its
        report, and the money payments add up to its revenue (4500).
        """
        self._vendre_avec_les_trois_moyens()

        reponse = self.client_http.post(
            "/laboutik/caisse/cloturer/",
            data={"uuid_pv": str(self.point_de_vente.uuid)},
        )

        self.assertEqual(reponse.status_code, 200)
        cloture = ClotureCaisseUnique.objects.get(
            niveau=ClotureCaisseUnique.NIVEAU_JOURNALIER
        )
        argent_par_moyen = cloture.rapport_json["reglements"]["argent"]["par_moyen"]
        self.assertEqual(
            argent_par_moyen[PaymentMethod.CHEQUE]["total_en_centimes"],
            MONTANT_CHEQUE_CENTIMES,
            "La cloture du comptoir doit enregistrer les cheques encaisses.",
        )
        somme_des_moyens = 0
        for ligne_du_moyen in argent_par_moyen.values():
            somme_des_moyens += ligne_du_moyen["total_en_centimes"]
        self.assertEqual(somme_des_moyens, 4500)
        self.assertEqual(somme_des_moyens, cloture.total_general)

    # Les clôtures mensuelles et annuelles de la caisse ne somment plus les colonnes
    # des journalières : la clôture unique relit les ventes de la période
    # (tests/pytest/test_cloture_unique.py, test_mois_calendaire_egal_ventes_du_mois).
    # / Monthly and yearly closures no longer sum the daily columns: the single
    # closure reads the period's sales.

    # ------------------------------------------------------------------ #
    #  T3 — Les exports remis au gestionnaire
    # ------------------------------------------------------------------ #

    # Les exports CSV, PDF et tableur d'une clôture sont ceux de la clôture unique
    # (`comptabilite/`) : ils parcourent les sections du rapport, sans liste de moyens
    # écrite en dur, et leurs totaux égalent le rapport
    # (tests/pytest/test_comptabilite_exports.py, test_csv_totaux_egaux_au_rapport et
    # test_pdf_totaux_egaux_au_rapport).
    # / Closure exports are the single closure's: no hard-coded method list, totals
    # equal to the report (test_comptabilite_exports.py).

    def test_lecran_de_cloture_au_comptoir_affiche_la_ligne_cheque(self):
        """
        L'écran que le caissier lit en fin de service doit être complet.

        Il liste les moyens puis le total général. Un moyen absent de la liste rend ce
        total inexplicable pour la personne qui compte sa caisse : elle voit un écart
        sans savoir d'où il vient.
        / The end-of-service screen lists the methods then the grand total: a missing
          method makes that total unexplainable to whoever counts the drawer.

        L'écran du Z montre les règlements de la J : le bloc des règlements porte le
        chèque (« 15,00 € ») à côté des espèces (« 10,00 € ») et de la carte
        (« 20,00 € ») ; leur somme, « 45,00 € », est le chiffre d'affaires affiché.
        / The Z screen's payments block carries the check next to cash and card.
        """
        self._vendre_avec_les_trois_moyens()

        reponse = self.client_http.post(
            "/laboutik/caisse/cloturer/",
            data={"uuid_pv": str(self.point_de_vente.uuid)},
        )

        page = reponse.content.decode()
        self.assertEqual(reponse.status_code, 200, page[:400])
        bloc_des_reglements = re.search(
            r'data-testid="cloture-reglements".*?</section>', page, re.DOTALL
        )
        self.assertIsNotNone(bloc_des_reglements, "Bloc des règlements absent.")
        texte_des_reglements = bloc_des_reglements.group(0)
        self.assertIn(euros("15,00"), texte_des_reglements)
        self.assertIn(euros("10,00"), texte_des_reglements)
        self.assertIn(euros("20,00"), texte_des_reglements)
        self.assertIn(euros("45,00"), page)

    def test_le_ticket_z_imprime_porte_la_ligne_cheque(self):
        """
        Le ticket Z est un justificatif papier : ses lignes doivent expliquer son total.
        Il est formaté depuis le rapport de la J unique : total = chiffre d'affaires
        TTC (4500), une ligne par moyen, chèque compris.
        / The Z ticket is a paper receipt: its lines must account for its total.
        """
        from laboutik.printing.formatters import formatter_ticket_cloture

        self._vendre_avec_les_trois_moyens()
        cloture = self._cloturer_la_journee()

        ticket = formatter_ticket_cloture(cloture)

        lignes_par_nom = {article["name"]: article["total"] for article in ticket["articles"]}
        self.assertIn("Chèque", lignes_par_nom, f"Lignes imprimees : {list(lignes_par_nom)}")
        self.assertEqual(lignes_par_nom["Chèque"], MONTANT_CHEQUE_CENTIMES)
        self.assertEqual(
            sum(lignes_par_nom.values()),
            ticket["total"]["amount"],
            "Les lignes imprimees doivent recomposer le total imprime.",
        )

    # ------------------------------------------------------------------ #
    #  T4 — L'archive fiscale : LE test qui aurait attrape le bug
    # ------------------------------------------------------------------ #

    def test_larchive_lne_exporte_le_vrai_montant_des_cheques(self):
        """
        L'archive fiscale doit dire la vérité sur les chèques.

        C'est le test qui manquait. `archivage.py` déclarait bien `total_cheque` dans
        les colonnes de son export, mais écrivait `'0'` en dur, avec un commentaire
        expliquant que le modèle n'avait pas le champ. L'archive légale annonçait donc
        zéro chèque à un contrôle, quel que soit le montant réellement encaissé.

        Une archive fiscale qui ment n'est pas un détail de confort : c'est l'objet
        même de l'obligation d'inaltérabilité.

        L'archive exporte les ventes : le chèque est un règlement (`reglements.csv`,
        moyen CH, 1500), et la J du soir porte le total des trois moyens
        (`clotures.csv`, 1000 + 2000 + 1500 = 4500).
        / The tax archive must tell the truth about checks. It hard-coded '0'. The
        check is a payment row (CH, 1500); the J carries the three methods' total.
        """
        from laboutik.archivage import generer_fichiers_archive

        self._vendre_avec_les_trois_moyens()
        cloture_j = self._cloturer_la_journee()

        fichiers_de_l_archive = generer_fichiers_archive(
            schema=self.tenant.schema_name
        )

        texte_des_reglements = fichiers_de_l_archive["reglements.csv"].decode(
            "utf-8-sig"
        )
        reglements_archives = list(
            csv.DictReader(texte_des_reglements.splitlines(), delimiter=";")
        )
        montants_des_cheques = []
        for reglement in reglements_archives:
            if reglement["moyen"] == PaymentMethod.CHEQUE:
                montants_des_cheques.append(reglement["montant"])
        self.assertEqual(
            montants_des_cheques,
            [str(MONTANT_CHEQUE_CENTIMES)],
            "L'archive fiscale doit porter le montant reel des cheques, pas zero.",
        )

        texte_des_clotures = fichiers_de_l_archive["clotures.csv"].decode("utf-8-sig")
        clotures_archivees = list(
            csv.DictReader(texte_des_clotures.splitlines(), delimiter=";")
        )
        self.assertEqual(len(clotures_archivees), 1)
        self.assertEqual(clotures_archivees[0]["uuid"], str(cloture_j.uuid))
        self.assertEqual(clotures_archivees[0]["total_general"], "4500")
