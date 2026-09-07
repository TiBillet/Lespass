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
from laboutik.models import PointDeVente
from laboutik.reports import RapportComptableService


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
        configuration.save()

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

    def _totaux(self):
        """Les totaux par moyen de paiement sur la periode.
        / Totals per payment method over the period."""
        service = RapportComptableService(self.point_de_vente, self.debut, self.fin)
        return service.calculer_totaux_par_moyen()

    def _cloturer(self, totaux, nombre_transactions):
        """
        Ecrit la ClotureCaisse a partir des totaux calcules.
        / Writes the ClotureCaisse from the computed totals.
        """
        from laboutik.models import ClotureCaisse

        service = RapportComptableService(self.point_de_vente, self.debut, self.fin)
        return ClotureCaisse.objects.create(
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
            nombre_transactions=nombre_transactions,
            rapport_json=service.generer_rapport_complet(),
        )

    def _cloturer_apres_les_trois_moyens(self):
        """Encaisse les trois moyens puis cloture. / Collects all three, then closes."""
        self._encaisser_les_trois_moyens()
        return self._cloturer(self._totaux(), nombre_transactions=3)

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
        """
        from laboutik.models import ClotureCaisse

        self._encaisser_les_trois_moyens()

        reponse = self.client_http.post(
            "/laboutik/caisse/cloturer/",
            data={"uuid_pv": str(self.point_de_vente.uuid)},
        )

        self.assertEqual(reponse.status_code, 200)
        cloture = ClotureCaisse.objects.latest("datetime_cloture")
        self.assertEqual(
            cloture.total_cheque,
            MONTANT_CHEQUE_CENTIMES,
            "La cloture du comptoir doit enregistrer les cheques encaisses.",
        )
        self.assertEqual(
            cloture.total_especes
            + cloture.total_carte_bancaire
            + cloture.total_cashless
            + cloture.total_cheque,
            cloture.total_general,
        )

    def test_la_cloture_agregee_additionne_les_cheques_des_journalieres(self):
        """
        Les clôtures mensuelles et annuelles agrègent les journalières : elles doivent
        additionner les chèques comme les trois autres moyens.

        Ce n'est pas le même code que la clôture du soir : l'agrégation passe par des
        `Sum()` sur les colonnes des clôtures sources. Un moyen de paiement absent de
        cette liste de sommes reste silencieusement à zéro pour toute la période, alors
        même que les journalières le portaient correctement.
        / Monthly and yearly closures aggregate the daily ones through Sum() on columns:
          a payment method missing from that list stays silently at zero for the whole
          period, even though the daily closures had it right.
        """
        from datetime import timedelta

        from laboutik.models import ClotureCaisse
        from laboutik.tasks import _generer_cloture_agregee

        # Deux journalieres portant chacune des cheques, dans la periode agregee.
        # / Two daily closures, each holding checks, inside the aggregated period.
        for numero in (1, 2):
            ClotureCaisse.objects.create(
                point_de_vente=self.point_de_vente,
                datetime_ouverture=self.debut,
                datetime_cloture=dj_timezone.now() - timedelta(minutes=numero),
                niveau=ClotureCaisse.JOURNALIERE,
                numero_sequentiel=numero,
                total_especes=MONTANT_ESPECES_CENTIMES,
                total_carte_bancaire=MONTANT_CARTE_CENTIMES,
                total_cashless=0,
                total_cheque=MONTANT_CHEQUE_CENTIMES,
                total_general=(
                    MONTANT_ESPECES_CENTIMES
                    + MONTANT_CARTE_CENTIMES
                    + MONTANT_CHEQUE_CENTIMES
                ),
                nombre_transactions=3,
            )

        # La fenetre d'agregation est ancree sur le fuseau du LIEU (`tasks.py`), pas sur
        # UTC. Prendre la date UTC ferait echouer ce test entre 22h et minuit UTC, quand
        # la date locale a deja change : la fenetre exclurait les clotures qu'on vient
        # de creer.
        # / The aggregation window is anchored on the VENUE's timezone, not UTC.
        aujourdhui = dj_timezone.now().astimezone(
            Configuration.get_solo().get_tzinfo()
        ).date()
        _generer_cloture_agregee(
            niveau=ClotureCaisse.MENSUELLE,
            niveau_source=ClotureCaisse.JOURNALIERE,
            date_debut=aujourdhui,
            date_fin=aujourdhui,
        )

        cloture_agregee = ClotureCaisse.objects.get(niveau=ClotureCaisse.MENSUELLE)
        self.assertEqual(
            cloture_agregee.total_cheque,
            MONTANT_CHEQUE_CENTIMES * 2,
            "La cloture agregee doit additionner les cheques des journalieres.",
        )
        self.assertEqual(
            cloture_agregee.total_especes
            + cloture_agregee.total_carte_bancaire
            + cloture_agregee.total_cashless
            + cloture_agregee.total_cheque,
            cloture_agregee.total_general,
        )

    # ------------------------------------------------------------------ #
    #  T3 — Les exports remis au gestionnaire
    # ------------------------------------------------------------------ #

    def test_lexport_csv_de_la_cloture_montre_la_ligne_cheque(self):
        """
        Le CSV est ce que le gestionnaire ouvre pour vérifier sa caisse.

        Il listait les espèces, la carte et le cashless, puis sautait au total
        général : la personne qui vérifiait ses comptes voyait un total que ses
        propres lignes ne justifiaient pas, sans savoir d'où venait l'écart.
        / The CSV is what the manager opens: it showed a grand total its own lines
          could not account for.
        """
        from laboutik.csv_export import generer_csv_cloture

        cloture = self._cloturer_apres_les_trois_moyens()

        contenu_csv = generer_csv_cloture(cloture)

        # On verifie la LIGNE, pas seulement le nombre : un montant ecrit en face du
        # mauvais libelle passerait un simple test de presence.
        # / We assert the LINE, not just the number: a value written next to the wrong
        #   label would pass a mere presence check.
        lignes_du_csv = [ligne.strip() for ligne in contenu_csv.splitlines()]
        ligne_cheque = [ligne for ligne in lignes_du_csv if ligne.startswith("Chèque")]
        self.assertEqual(
            len(ligne_cheque), 1, f"Une seule ligne Cheque attendue : {lignes_du_csv}"
        )
        self.assertIn(f"{MONTANT_CHEQUE_CENTIMES / 100:.2f}", ligne_cheque[0])

    def test_le_pdf_de_la_cloture_porte_le_total_cheque(self):
        """
        Le PDF est le justificatif imprimé et archivé : il doit être complet.
        / The PDF is the printed, archived receipt: it must be complete.
        """
        from unittest import mock

        from laboutik.pdf import generer_pdf_cloture

        cloture = self._cloturer_apres_les_trois_moyens()

        # On intercepte le HTML juste avant sa conversion en PDF.
        # Verifier seulement que « un PDF sort » ne prouverait RIEN : un PDF sortait
        # deja quand le cheque etait absent. C'est le contenu qu'il faut lire, et le
        # HTML est le dernier endroit ou il est encore lisible.
        # / We intercept the HTML right before PDF conversion: asserting that "a PDF
        #   came out" would prove nothing, since one already did without the check.
        with mock.patch("laboutik.pdf.HTML") as html_mocke:
            generer_pdf_cloture(cloture)

        self.assertTrue(html_mocke.called, "Le PDF doit avoir ete rendu.")
        html_rendu = html_mocke.call_args.kwargs["string"]

        # Le montant doit suivre le libelle « Cheque » dans le tableau des moyens, et
        # pas flotter n'importe ou dans la page.
        # / The amount must follow the "Cheque" label in the methods table.
        import re

        cellule_cheque = re.search(
            r"Chèque</td>\s*<td[^>]*>\s*([\d.,]+)", html_rendu
        )
        self.assertIsNotNone(
            cellule_cheque, "Le PDF doit porter une ligne Cheque dans ses totaux."
        )
        self.assertEqual(
            cellule_cheque.group(1).replace(",", "."),
            f"{MONTANT_CHEQUE_CENTIMES / 100:.2f}",
        )

    def test_lecran_de_cloture_au_comptoir_affiche_la_ligne_cheque(self):
        """
        L'écran que le caissier lit en fin de service doit être complet.

        Il liste les moyens puis le total général. Un moyen absent de la liste rend ce
        total inexplicable pour la personne qui compte sa caisse : elle voit un écart
        sans savoir d'où il vient.
        / The end-of-service screen lists the methods then the grand total: a missing
          method makes that total unexplainable to whoever counts the drawer.
        """
        self._encaisser_les_trois_moyens()

        reponse = self.client_http.post(
            "/laboutik/caisse/cloturer/",
            data={"uuid_pv": str(self.point_de_vente.uuid)},
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.context["total_cheque_euros"], MONTANT_CHEQUE_CENTIMES / 100)
        self.assertContains(reponse, "cloture-total-cheque")

    def test_le_ticket_z_imprime_porte_la_ligne_cheque(self):
        """
        Le ticket Z est un justificatif papier : ses lignes doivent expliquer son total.
        / The Z ticket is a paper receipt: its lines must account for its total.
        """
        from laboutik.printing.formatters import formatter_ticket_cloture

        cloture = self._cloturer_apres_les_trois_moyens()

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
        / The tax archive must tell the truth about checks. It hard-coded '0'.
        """
        from laboutik.archivage import _extraire_clotures
        from laboutik.models import ClotureCaisse

        self._encaisser_les_trois_moyens()
        totaux = self._totaux()

        ClotureCaisse.objects.create(
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

        lignes_archivees = _extraire_clotures(self.debut, self.fin)

        self.assertEqual(len(lignes_archivees), 1)
        self.assertEqual(
            lignes_archivees[0]["total_cheque"],
            str(MONTANT_CHEQUE_CENTIMES),
            "L'archive fiscale doit porter le montant reel des cheques, pas zero.",
        )
