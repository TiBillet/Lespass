"""
Les lecteurs de la caisse sur la clôture unique du lieu (`comptabilite.ClotureCaisse`).
/ The register readers on the venue's single closure (`comptabilite.ClotureCaisse`).

LOCALISATION : tests/pytest/test_lecteurs_montants_entiers.py

RÈGLE MÉTIER TESTÉE — LA CORRECTION DU MOYEN DE PAIEMENT
Une vente couverte par une clôture journalière (J) ne se corrige plus : la J a figé
ses règlements. Une vente est couverte quand elle a un numéro et que ce numéro est
inférieur ou égal au numéro de la dernière vente de la DERNIÈRE J du lieu
(`numero_derniere_vente`).
Seule une vente réglée (elle a un numéro), faite à la caisse, payée en espèces, CB ou
chèque, et pas encore couverte par une J, se corrige. Tout le reste est refusé :
- une vente couverte par une J (le plus grand numéro de dernière vente des J ; une M
  ou une A ne compte pas) ;
- une ligne écrite sans vente ;
- une ligne dont la vente n'est pas encore réglée (« en attente », sans numéro) ;
- une vente d'une autre origine que la caisse (en ligne, admin) ;
- un autre moyen que espèces, CB ou chèque (Stripe, cashless, hors argent).
Chaque refus est vérifié avec son message.
Deux lecteurs appliquent cette règle :
- la route `corriger_moyen_paiement` (`laboutik/views.py`) : refus en 400, rien
  n'est écrit (ni trace `CorrectionPaiement`, ni vente `CORRECTION`, ni nouveau
  moyen sur la ligne) ;
- l'écran du détail d'une vente (`detail_vente`) : le bouton « Corriger moyen »
  (`data-testid="btn-corriger"`) n'est proposé que si la correction est possible.
/ A sale covered by the venue's last daily closure (its number ≤ the J's last sale
number) can no longer be corrected. Only a settled sale not yet covered is corrected;
a line without a sale and a pending sale are refused. The correction route refuses
(400, nothing written) and the sale detail screen hides its "Correct" button.

RÈGLE MÉTIER TESTÉE — LE BOUTON « CLÔTURER » ET LE TICKET Z
- Le bouton « Clôturer » de la caisse crée la J unique du lieu, qui couvre ses
  ventes, et plus jamais une ancienne clôture (`laboutik.ClotureCaisse`).
- Le journal des impressions (`ImpressionLog.cloture`) pointe vers la J unique.
  Chaque impression d'un ticket Z est écrite dans ce journal, liée à sa J ; la
  deuxième impression du même Z est un DUPLICATA, et le ticket envoyé à
  l'imprimante le dit (`is_duplicata`).
/ The "Close" button creates the single J, never an old closure. The print log points
to the single J; the second print of the same Z is a DUPLICATE.

SCHÉMA DÉDIÉ
Une J lit TOUTES les ventes du lieu : il faut un lieu qui ne contient que les ventes
du test (`FastTenantTestCase`). Chaque test annule sa transaction à la fin. Le
singleton `LaboutikConfiguration` est créé en base (tests/PIEGES.md 9.86) : il porte
la clé des empreintes. La `Configuration` du lieu est réécrite à chaque test : son
cache (django-solo) survit à l'annulation de la transaction.
Les ventes sont écrites PAR LE SERVICE (`fabriques_vente.py`), jamais à la main. Les
J sont créées par la vraie tâche (`comptabilite.tasks.generer_cloture_pour_tenant`),
à l'heure réelle : chaque vente du test est encaissée avant la J qui la suit.
Aucune ancienne clôture (`laboutik.ClotureCaisse`) n'existe dans ce lieu : une garde
qui la lirait encore ne verrait jamais rien.
/ Dedicated schema, rolled back after each test. Sales through the sale service, J
through the real task. No old closure exists in this venue.

D'OÙ VIENNENT LES VALEURS ATTENDUES
Aucune valeur d'argent n'est assertée : ces tests portent sur un refus ou un accord.
Le code HTTP 400 du refus est celui des autres gardes de la même route (moyen
cashless, vente hors argent, même moyen). Une bière vaut 5,00 €, TVA 20 % ; elle est
payée en espèces (règlement espèces de 500).
/ No money value is asserted: refusal or acceptance only. 400 is the code of the other
guards of the same route.

Pour le ticket Z : la valeur attendue est celle de la tâche d'impression, qui compte
les impressions précédentes du même justificatif (0 → original, 1 → duplicata).

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-G-lecteurs.md (§2, §2.1,
§5 tests 1, 2 et 3).

Lancer / Run : make test ARGS="tests/pytest/test_lecteurs_montants_entiers.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import uuid  # noqa: E402
from datetime import datetime, time  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.db import connection  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

import comptabilite.tasks  # noqa: E402
from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Configuration,
    LigneArticle,
    PaymentMethod,
    SaleOrigin,
)
from BaseBillet.models_vente import Vente  # noqa: E402
from BaseBillet.services_vente import ajouter_article, ouvrir_vente  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from laboutik.models import (  # noqa: E402
    CorrectionPaiement,
    ImpressionLog,
    LaboutikConfiguration,
    PointDeVente,
    Printer,
)
from laboutik.models import ClotureCaisse as AncienneClotureCaisse  # noqa: E402
from laboutik.printing.tasks import imprimer_async  # noqa: E402

# Adresses de la caisse (laboutik/urls.py).
# / Register addresses.
URL_DE_LA_CORRECTION_DU_MOYEN = "/laboutik/paiement/corriger_moyen_paiement/"
DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE = "/laboutik/caisse/detail-vente/"

# Le bouton « Corriger moyen » de l'écran du détail d'une vente
# (laboutik/templates/laboutik/partial/hx_detail_vente.html).
# / The "Correct" button of the sale detail screen.
BOUTON_CORRIGER_DU_DETAIL = 'data-testid="btn-corriger"'

# Les messages de refus attendus, écrits à la main (la caisse répond en français).
# / The expected refusal messages, hand-written (the register answers in French).
MESSAGE_VENTE_COUVERTE = (
    "Cette vente est couverte par une cloture. Modification interdite."
)
MESSAGE_VENTE_PAS_REGLEE = "Seule une vente réglée peut être corrigée."
MESSAGE_VENTE_PAS_FAITE_A_LA_CAISSE = (
    "Seule une vente faite à la caisse peut être corrigée."
)
MESSAGE_MOYEN_PAS_CORRIGEABLE = (
    "Seul un paiement en espèces, par carte bancaire ou par chèque peut être corrigé."
)

FUSEAU_DE_PARIS = ZoneInfo("Europe/Paris")


def heure_de_paris(annee, mois, jour, heure, minute=0):
    """Un moment en heure de Paris. / A moment in Paris time."""
    return datetime(annee, mois, jour, heure, minute, tzinfo=FUSEAU_DE_PARIS)


class TestGardeDeCorrectionSurLaClotureUnique(FastTenantTestCase):
    """
    La correction du moyen de paiement est refusée pour une vente couverte par la
    dernière J unique, pour une ligne sans vente et pour une vente en attente.
    / The payment method correction is refused for a sale covered by the last single
    J, for a line without a sale and for a pending sale.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_lecteurs_cloture_unique"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-lecteurs-cloture-unique.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test lecteurs cloture unique"

    def setUp(self):
        """
        Le lieu de test : son singleton de caisse, sa configuration (caisse active,
        Paris, aucun e-mail de rapport), un point de vente, une bière à 5,00 € et un
        administrateur connecté à la caisse.
        / The test venue: register singleton, configuration, a point of sale, a beer
        at 5.00 € and a logged-in admin.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse doit exister en base (tests/PIEGES.md 9.86) : il
        # porte la clé des empreintes des ventes et des clôtures.
        # / The register singleton must exist in the database (fingerprint key).
        LaboutikConfiguration.get_solo().save()

        # Les routes de la caisse sont gardées par `module_caisse`, qui exige
        # `module_monnaie_locale`. Aucun e-mail de rapport : la J n'envoie rien.
        # Toutes les valeurs sont écrites ici : le cache de la configuration garde
        # celles du test précédent.
        # / Register routes need module_caisse (which needs module_monnaie_locale).
        # No report e-mail. Every value is written here: the cache keeps old values.
        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.heure_de_fermeture = time(2, 0)
        configuration.rapport_emails = ""
        configuration.save()

        self.point_de_vente = PointDeVente.objects.create(
            name="Bar lecteurs cloture unique",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            accepte_cheque=True,
        )

        self.tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere",
            prix_en_euros="5.00",
            taux_tva="20.00",
        )

        # L'administrateur vit dans le schéma public (SHARED_APPS) ; il est créé dans
        # la transaction du test, annulée à la fin.
        # / The admin lives in the public schema; created inside the rolled-back test.
        self.administrateur_du_lieu, _utilisateur_cree = (
            TibilletUser.objects.get_or_create(
                email="admin-test-lecteurs-cloture@tibillet.localhost",
                defaults={
                    "username": "admin-test-lecteurs-cloture@tibillet.localhost",
                    "is_staff": True,
                    "is_active": True,
                },
            )
        )
        self.administrateur_du_lieu.client_admin.add(self.tenant)

        # La caisse répond en français : les messages de refus attendus le sont.
        # / The register answers in French, like the expected refusal messages.
        self.client_du_caissier = TenantClient(self.tenant, HTTP_ACCEPT_LANGUAGE="fr")
        self.client_du_caissier.force_login(self.administrateur_du_lieu)

    # ------------------------------------------------------------------
    # Outils du test
    # / Test helpers
    # ------------------------------------------------------------------

    def _vendre_une_biere(self, origine, moyen):
        """
        Une vente réglée : une bière à 5,00 € (TVA 20 %), de l'origine donnée, payée
        avec le moyen donné. La ligne porte aussi ses champs historiques (moyen,
        identifiant du paiement, point de vente), comme une vente faite à la caisse :
        la correction et l'écran du détail les lisent.
        Rend la ligne de la bière.
        / A settled sale: one beer, given origin and method. The line carries its
        legacy fields. Returns the beer line.
        """
        identifiant_du_paiement = uuid.uuid4()
        vente = fabriquer_vente_encaissee(
            origine=origine,
            point_de_vente=self.point_de_vente,
            operateur=self.administrateur_du_lieu,
            articles=[
                {
                    "pricesold": self.tarif_de_la_biere,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                    "payment_method": moyen,
                    "uuid_transaction": identifiant_du_paiement,
                    "point_de_vente": self.point_de_vente,
                },
            ],
            reglements=[
                {"moyen": moyen, "montant": 500},
            ],
        )
        verifier_egalites(vente)
        return vente.articles.get()

    def _vendre_une_biere_en_especes(self):
        """
        Une vente de caisse réglée : une bière à 5,00 € payée en espèces. Rend la
        ligne de la bière.
        / A settled register sale: one beer paid in cash. Returns the beer line.
        """
        return self._vendre_une_biere(SaleOrigin.LABOUTIK, PaymentMethod.CASH)

    def _ecrire_une_biere_dans_une_vente_en_attente(self):
        """
        Une ligne de bière en espèces dans une vente ouverte mais jamais encaissée :
        la vente est « en attente », sans numéro ni règlement.
        Rend la ligne de la bière.
        / A beer line in a sale opened but never settled: pending, no number.
        """
        vente_en_attente = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VENTE,
            point_de_vente=self.point_de_vente,
            operateur=self.administrateur_du_lieu,
        )
        ligne_de_la_biere = ajouter_article(
            vente_en_attente,
            pricesold=self.tarif_de_la_biere,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("20"),
            payment_method=PaymentMethod.CASH,
            uuid_transaction=uuid.uuid4(),
            point_de_vente=self.point_de_vente,
        )
        return ligne_de_la_biere

    def _cloturer_la_journee(self):
        """
        Le « Z de fin de service » : crée la J du lieu, maintenant, par la vraie
        tâche. Rend la J créée.
        / The end-of-service Z: creates the venue's J now, through the real task.
        """
        uuid_de_la_j = comptabilite.tasks.generer_cloture_pour_tenant(
            schema_name=self.tenant.schema_name,
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        )
        self.assertIsNotNone(uuid_de_la_j, "La J aurait dû être créée.")
        return ClotureCaisse.objects.get(uuid=uuid_de_la_j)

    def _corriger_en_cb(self, ligne):
        """
        Le caissier corrige le moyen de la ligne en CB, par la vraie route, comme le
        formulaire de l'historique des ventes l'envoie.
        / The cashier corrects the line's method into CB, through the real route.
        """
        donnees_du_formulaire = {
            "ligne_uuid": str(ligne.uuid),
            "nouveau_moyen": PaymentMethod.CC,
            "raison": "Erreur de moyen au moment du paiement",
        }
        return self.client_du_caissier.post(
            URL_DE_LA_CORRECTION_DU_MOYEN, donnees_du_formulaire
        )

    def _ouvrir_le_detail_de_la_vente(self, ligne):
        """
        Ouvre l'écran du détail de la vente de cette ligne (par son identifiant de
        paiement, comme l'historique des ventes). Rend le HTML de l'écran.
        / Opens the sale detail screen of this line. Returns its HTML.
        """
        reponse = self.client_du_caissier.get(
            f"{DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE}{ligne.uuid_transaction}/"
        )
        contenu = reponse.content.decode()
        self.assertEqual(reponse.status_code, 200, contenu[:400])
        return contenu

    def _verifier_le_refus(
        self, reponse, ligne, message_attendu, moyen_d_origine=PaymentMethod.CASH
    ):
        """
        Après un refus : 400 avec le message attendu ; la ligne garde son moyen
        d'origine, aucune trace de correction n'existe pour elle, et le lieu n'a
        aucune vente `CORRECTION`.
        / After a refusal: 400 with the expected message; the line keeps its method,
        no audit trail, no CORRECTION sale.
        """
        contenu = reponse.content.decode()
        self.assertEqual(reponse.status_code, 400, contenu[:400])
        self.assertIn(message_attendu, contenu)
        ligne.refresh_from_db()
        self.assertEqual(ligne.payment_method, moyen_d_origine)
        self.assertFalse(
            CorrectionPaiement.objects.filter(ligne_article=ligne).exists()
        )
        self.assertFalse(
            Vente.objects.filter(nature=Vente.Nature.CORRECTION).exists()
        )

    # ------------------------------------------------------------------
    # La route de correction
    # / The correction route
    # ------------------------------------------------------------------

    def test_correction_refusee_apres_la_j_unique(self):
        """
        Une bière payée en espèces, puis le Z de fin de service : la J couvre la
        vente (son numéro est le dernier de la J). Le caissier tente de corriger en
        CB : refus (400). Rien n'est écrit, et la vente d'origine ne change pas
        (même statut, même numéro, même empreinte).
        / A cash beer, then the Z: the J covers the sale (its number is the J's last).
        Correcting into CB is refused (400); nothing is written; the sale unchanged.
        """
        ligne_de_la_biere = self._vendre_une_biere_en_especes()
        vente_d_origine = ligne_de_la_biere.vente
        j_de_fin_de_service = self._cloturer_la_journee()
        # La J couvre bien la vente : c'est sa dernière vente.
        # / The J does cover the sale: it is its last sale.
        self.assertEqual(
            j_de_fin_de_service.numero_derniere_vente, vente_d_origine.numero
        )
        empreinte_avant = (
            vente_d_origine.statut,
            vente_d_origine.numero,
            vente_d_origine.hmac_hash,
        )

        reponse = self._corriger_en_cb(ligne_de_la_biere)

        self._verifier_le_refus(reponse, ligne_de_la_biere, MESSAGE_VENTE_COUVERTE)
        vente_d_origine.refresh_from_db()
        self.assertEqual(
            (
                vente_d_origine.statut,
                vente_d_origine.numero,
                vente_d_origine.hmac_hash,
            ),
            empreinte_avant,
        )

    def test_correction_refusee_vente_couverte_par_la_derniere_de_deux_j(self):
        """
        Une bière, une J ; une deuxième bière, une deuxième J. La deuxième bière est
        couverte par la DERNIÈRE J (pas par la première, qui s'arrête avant elle) :
        sa correction est refusée (400), rien n'est écrit.
        / Beer, J; second beer, second J. The second beer is covered by the LAST J
        (not by the first one): its correction is refused (400), nothing written.
        """
        self._vendre_une_biere_en_especes()
        premiere_j = self._cloturer_la_journee()
        ligne_de_la_deuxieme_biere = self._vendre_une_biere_en_especes()
        deuxieme_j = self._cloturer_la_journee()
        # La première J s'arrête avant la deuxième bière ; la dernière J la couvre.
        # / The first J ends before the second beer; the last J covers it.
        numero_de_la_deuxieme_vente = ligne_de_la_deuxieme_biere.vente.numero
        self.assertLess(premiere_j.numero_derniere_vente, numero_de_la_deuxieme_vente)
        self.assertEqual(deuxieme_j.numero_derniere_vente, numero_de_la_deuxieme_vente)

        reponse = self._corriger_en_cb(ligne_de_la_deuxieme_biere)

        self._verifier_le_refus(
            reponse, ligne_de_la_deuxieme_biere, MESSAGE_VENTE_COUVERTE
        )

    def test_correction_refusee_vente_couverte_par_la_premiere_de_deux_j(self):
        """
        Une bière, une J ; une deuxième bière, une deuxième J. La PREMIÈRE bière est
        couverte par la première J : sa correction est refusée (400), rien n'est
        écrit, même si la dernière J ne commence qu'après elle.
        / Beer 1, J1, beer 2, J2: correcting beer 1 is refused, nothing written.
        """
        ligne_de_la_premiere_biere = self._vendre_une_biere_en_especes()
        premiere_j = self._cloturer_la_journee()
        self._vendre_une_biere_en_especes()
        deuxieme_j = self._cloturer_la_journee()
        # La dernière J commence après la première bière ; la première J la couvre.
        # / The last J starts after beer 1; the first J covers it.
        numero_de_la_premiere_vente = ligne_de_la_premiere_biere.vente.numero
        self.assertEqual(premiere_j.numero_derniere_vente, numero_de_la_premiere_vente)
        self.assertGreater(
            deuxieme_j.numero_premiere_vente, numero_de_la_premiere_vente
        )

        reponse = self._corriger_en_cb(ligne_de_la_premiere_biere)

        self._verifier_le_refus(
            reponse, ligne_de_la_premiere_biere, MESSAGE_VENTE_COUVERTE
        )

    def test_correction_refusee_vente_couverte_par_le_filet_puis_la_m_du_mois(self):
        """
        Une vente le 31 mars à 23 h, une le 1er avril à 1 h (heure de Paris, fermeture
        à 2 h). La tâche horaire du 1er avril à 5 h crée d'abord la J du filet, qui
        finit au seuil du 1er (2 h + 2 h = 4 h) et couvre les deux ventes ; puis la M
        de mars, qui finit à minuit et ne couvre que la vente du 31. La M, plus
        récente, ne couvre pas la vente de 1 h : sa correction reste refusée, la J la
        couvre.
        / Sales on Mar 31 11 pm and Apr 1 1 am. The hourly task creates the J (to the
        4 am threshold, both sales), then the March M (to midnight, only the first).
        Correcting the 1 am sale is still refused: the J covers it.
        """
        with patch(
            "django.utils.timezone.now", return_value=heure_de_paris(2026, 3, 31, 23)
        ):
            ligne_du_31_mars = self._vendre_une_biere_en_especes()
        with patch(
            "django.utils.timezone.now", return_value=heure_de_paris(2026, 4, 1, 1)
        ):
            ligne_du_1er_avril = self._vendre_une_biere_en_especes()
        with patch(
            "django.utils.timezone.now", return_value=heure_de_paris(2026, 4, 1, 5)
        ):
            comptabilite.tasks.generer_les_clotures_automatiques_du_lieu(
                self.tenant.schema_name
            )
        # Le décor : la J du filet finit au seuil du 1er (4 h) et couvre la vente de
        # 1 h ; la M de mars, créée après elle, finit à minuit et s'arrête au 31.
        # / The setting: J to the 4 am threshold covers the 1 am sale; the later March
        # M ends at midnight with the Mar 31 sale.
        j_du_filet = ClotureCaisse.objects.get(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
        m_de_mars = ClotureCaisse.objects.get(niveau=ClotureCaisse.NIVEAU_MENSUEL)
        self.assertEqual(j_du_filet.datetime_fin, heure_de_paris(2026, 4, 1, 4))
        self.assertEqual(
            j_du_filet.numero_derniere_vente, ligne_du_1er_avril.vente.numero
        )
        self.assertEqual(m_de_mars.datetime_fin, heure_de_paris(2026, 4, 1, 0))
        self.assertEqual(m_de_mars.numero_derniere_vente, ligne_du_31_mars.vente.numero)
        self.assertGreater(m_de_mars.numero_sequentiel, j_du_filet.numero_sequentiel)

        reponse = self._corriger_en_cb(ligne_du_1er_avril)

        self._verifier_le_refus(reponse, ligne_du_1er_avril, MESSAGE_VENTE_COUVERTE)

    def test_correction_refusee_vente_en_ligne_stripe(self):
        """
        Une vente en ligne payée par Stripe (moyen « SN »), corrigée par un POST
        forgé vers la route de la caisse : refus (400, « seuls espèces, CB ou
        chèque »), rien n'est écrit. Aucune J n'existe.
        / An online Stripe sale corrected through a forged POST: refused, nothing
        written.
        """
        ligne_stripe = self._vendre_une_biere(
            SaleOrigin.LESPASS, PaymentMethod.STRIPE_NOFED
        )

        reponse = self._corriger_en_cb(ligne_stripe)

        self._verifier_le_refus(
            reponse,
            ligne_stripe,
            MESSAGE_MOYEN_PAS_CORRIGEABLE,
            moyen_d_origine=PaymentMethod.STRIPE_NOFED,
        )

    def test_correction_refusee_vente_en_especes_faite_dans_l_admin(self):
        """
        Une vente en espèces déclarée dans l'admin (origine « Administration »), pas
        à la caisse. Le moyen est corrigeable, mais seule une vente faite à la caisse
        se corrige à la caisse : refus (400), rien n'est écrit.
        / A cash sale declared in the admin, not at the register: refused, nothing
        written.
        """
        ligne_de_l_admin = self._vendre_une_biere(SaleOrigin.ADMIN, PaymentMethod.CASH)

        reponse = self._corriger_en_cb(ligne_de_l_admin)

        self._verifier_le_refus(
            reponse, ligne_de_l_admin, MESSAGE_VENTE_PAS_FAITE_A_LA_CAISSE
        )

    def test_correction_acceptee_vente_reglee_pas_encore_couverte(self):
        """
        Une bière, puis la J ; une deuxième bière, payée APRÈS la J. Le lieu a donc
        une J, mais elle ne couvre pas la deuxième vente (son numéro est plus grand
        que le dernier de la J). La correction en CB de la deuxième bière est
        acceptée (200) : la ligne passe en CB, avec sa trace de correction, et une
        vente `CORRECTION` liée à la vente d'origine est écrite.
        / Beer, J; second beer paid AFTER the J. The J does not cover it: correcting
        it into CB is accepted (200), with its audit trail and a CORRECTION sale.
        """
        self._vendre_une_biere_en_especes()
        j_de_fin_de_service = self._cloturer_la_journee()
        ligne_de_la_deuxieme_biere = self._vendre_une_biere_en_especes()
        vente_d_origine = ligne_de_la_deuxieme_biere.vente
        # La vente est réglée (elle a un numéro) et la J s'arrête avant elle.
        # / The sale is settled (it has a number) and the J ends before it.
        self.assertEqual(vente_d_origine.statut, Vente.Statut.REGLEE)
        self.assertGreater(
            vente_d_origine.numero, j_de_fin_de_service.numero_derniere_vente
        )

        reponse = self._corriger_en_cb(ligne_de_la_deuxieme_biere)

        self.assertEqual(reponse.status_code, 200, reponse.content.decode()[:400])
        ligne_de_la_deuxieme_biere.refresh_from_db()
        self.assertEqual(ligne_de_la_deuxieme_biere.payment_method, PaymentMethod.CC)
        self.assertEqual(
            CorrectionPaiement.objects.filter(
                ligne_article=ligne_de_la_deuxieme_biere,
                ancien_moyen=PaymentMethod.CASH,
                nouveau_moyen=PaymentMethod.CC,
            ).count(),
            1,
        )
        self.assertEqual(
            Vente.objects.filter(
                nature=Vente.Nature.CORRECTION,
                vente_liee=vente_d_origine,
            ).count(),
            1,
        )

    def test_correction_refusee_vente_en_attente(self):
        """
        Une ligne de bière en espèces dans une vente jamais encaissée (« en
        attente », sans numéro). Aucune J n'existe. Le caissier tente de corriger
        en CB : refus (400), rien n'est écrit. Seule une vente réglée se corrige.
        / A beer line in a never-settled sale (pending, no number). No J. Correcting
        into CB is refused (400), nothing written: only a settled sale is corrected.
        """
        ligne_en_attente = self._ecrire_une_biere_dans_une_vente_en_attente()
        self.assertIsNone(ligne_en_attente.vente.numero)
        self.assertFalse(ClotureCaisse.objects.exists())

        reponse = self._corriger_en_cb(ligne_en_attente)

        self._verifier_le_refus(reponse, ligne_en_attente, MESSAGE_VENTE_PAS_REGLEE)

    # ------------------------------------------------------------------
    # L'écran du détail d'une vente
    # / The sale detail screen
    # ------------------------------------------------------------------

    def test_detail_vente_sans_bouton_corriger_apres_la_j_unique(self):
        """
        Une bière payée en espèces, puis la J qui la couvre : l'écran du détail de
        la vente ne propose pas le bouton « Corriger moyen ».
        / A cash beer covered by the J: the detail screen does not offer "Correct".
        """
        ligne_de_la_biere = self._vendre_une_biere_en_especes()
        self._cloturer_la_journee()

        contenu = self._ouvrir_le_detail_de_la_vente(ligne_de_la_biere)

        self.assertNotIn(BOUTON_CORRIGER_DU_DETAIL, contenu)

    def test_detail_vente_bouton_corriger_vente_reglee_pas_encore_couverte(self):
        """
        Une bière, puis la J ; une deuxième bière payée en espèces APRÈS la J. Le
        détail de la deuxième vente propose le bouton « Corriger moyen » : elle est
        réglée et pas encore couverte.
        / Beer, J, second cash beer after the J: its detail offers "Correct".
        """
        self._vendre_une_biere_en_especes()
        self._cloturer_la_journee()
        ligne_de_la_deuxieme_biere = self._vendre_une_biere_en_especes()

        contenu = self._ouvrir_le_detail_de_la_vente(ligne_de_la_deuxieme_biere)

        self.assertIn(BOUTON_CORRIGER_DU_DETAIL, contenu)

    def test_detail_vente_sans_bouton_corriger_ligne_sans_vente(self):
        """
        Une ligne de bière en espèces écrite SANS vente (comme les lignes d'avant
        les ventes, base de dev seulement). Aucune J n'existe. L'écran du détail ne
        propose pas le bouton « Corriger moyen » (la route la refuserait).
        / A beer line written WITHOUT a sale, no J: no "Correct" button.
        """
        ligne_sans_vente = LigneArticle.objects.create(
            pricesold=self.tarif_de_la_biere,
            qty=1,
            amount=500,
            payment_method=PaymentMethod.CASH,
            status=LigneArticle.VALID,
            sale_origin=SaleOrigin.LABOUTIK,
            uuid_transaction=uuid.uuid4(),
            point_de_vente=self.point_de_vente,
        )
        self.assertIsNone(ligne_sans_vente.vente_id)

        contenu = self._ouvrir_le_detail_de_la_vente(ligne_sans_vente)

        self.assertNotIn(BOUTON_CORRIGER_DU_DETAIL, contenu)

    def test_detail_vente_sans_bouton_corriger_vente_en_attente(self):
        """
        Une ligne de bière en espèces dans une vente jamais encaissée : l'écran du
        détail ne propose pas le bouton « Corriger moyen » (la route la refuserait).
        / A beer line in a pending sale: the detail screen does not offer "Correct".
        """
        ligne_en_attente = self._ecrire_une_biere_dans_une_vente_en_attente()

        contenu = self._ouvrir_le_detail_de_la_vente(ligne_en_attente)

        self.assertNotIn(BOUTON_CORRIGER_DU_DETAIL, contenu)


class ImprimanteSimulee:
    """
    Remplace l'envoi réel à l'imprimante : garde une copie de chaque ticket reçu et
    répond que l'impression a réussi.
    / Replaces the real printer call: keeps a copy of each ticket, answers success.
    """

    def __init__(self):
        self.tickets_recus = []

    def imprimer(self, imprimante, donnees_du_ticket):
        self.tickets_recus.append(dict(donnees_du_ticket))
        return {"ok": True}


class TestBoutonCloturerEtTicketZSurLaClotureUnique(FastTenantTestCase):
    """
    Le bouton « Clôturer » crée la J unique ; le journal des impressions du ticket Z
    pointe vers elle, et la deuxième impression du même Z est un DUPLICATA.
    / The "Close" button creates the single J; the Z print log points to it, and the
    second print of the same Z is a DUPLICATE.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_lecteurs_bouton_z"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-lecteurs-bouton-z.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test lecteurs bouton Z"

    def setUp(self):
        """
        Le lieu de test : son singleton de caisse, sa configuration (caisse active,
        Paris, aucun e-mail de rapport), un point de vente, une bière à 5,00 € et un
        administrateur connecté à la caisse.
        / The test venue: register singleton, configuration, a point of sale, a beer
        and a logged-in admin.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse porte la clé des empreintes (tests/PIEGES.md 9.86).
        # / The register singleton carries the fingerprint key.
        LaboutikConfiguration.get_solo().save()

        # Toutes les valeurs sont écrites ici : le cache de la configuration garde
        # celles du test précédent.
        # / Every value is written here: the cache keeps the previous test's values.
        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.rapport_emails = ""
        configuration.save()

        self.point_de_vente = PointDeVente.objects.create(
            name="Bar lecteurs bouton Z",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            hidden=True,
        )
        self.tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere",
            prix_en_euros="5.00",
            taux_tva="20.00",
        )

        # L'administrateur vit dans le schéma public ; il est annulé avec le test.
        # / The admin lives in the public schema; rolled back with the test.
        self.administrateur_du_lieu, _utilisateur_cree = (
            TibilletUser.objects.get_or_create(
                email="admin-test-lecteurs-bouton-z@tibillet.localhost",
                defaults={
                    "username": "admin-test-lecteurs-bouton-z@tibillet.localhost",
                    "is_staff": True,
                    "is_active": True,
                },
            )
        )
        self.administrateur_du_lieu.client_admin.add(self.tenant)

        self.client_du_caissier = TenantClient(self.tenant)
        self.client_du_caissier.force_login(self.administrateur_du_lieu)

    def _vendre_une_biere_en_especes(self):
        """
        Une vente de caisse réglée au comptoir du test : une bière à 5,00 € en
        espèces, ligne validée comme la caisse l'écrit. Rend la vente.
        / A settled register sale: one beer in cash. Returns the sale.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            operateur=self.administrateur_du_lieu,
            articles=[
                {
                    "pricesold": self.tarif_de_la_biere,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 500,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.CASH,
                    "status": LigneArticle.VALID,
                    "uuid_transaction": uuid.uuid4(),
                    "point_de_vente": self.point_de_vente,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 500}],
        )
        verifier_egalites(vente)
        return vente

    def _ticket_z_avec_ses_metadonnees(self, cloture):
        """
        Un ticket Z minimal, avec les métadonnées de traçabilité que la tâche
        d'impression lit : type « CLOT », uuid de la clôture.
        / A minimal Z ticket with the tracking metadata the print task reads.
        """
        return {
            "header": {"title": "CLOTURE", "subtitle": "", "date": ""},
            "articles": [],
            "total": {"amount": 0, "label": ""},
            "qrcode": None,
            "footer": [],
            "impression_meta": {
                "uuid_transaction": None,
                "cloture_uuid": str(cloture.uuid),
                "type_justificatif": ImpressionLog.CLOTURE,
                "operateur_pk": str(self.administrateur_du_lieu.pk),
                "format_emission": "P",
            },
        }

    def test_bouton_cloturer_cree_la_cloture_unique(self):
        """
        Une bière vendue, puis le bouton « Clôturer » : 200, une J unique est créée
        et couvre la vente (sa dernière vente est celle-ci) ; aucune ancienne clôture
        (`laboutik.ClotureCaisse`) n'est créée.
        / One beer sold, then the "Close" button: one single J covering the sale, no
        old closure.
        """
        vente = self._vendre_une_biere_en_especes()

        reponse = self.client_du_caissier.post(
            "/laboutik/caisse/cloturer/", {"uuid_pv": str(self.point_de_vente.uuid)}
        )

        self.assertEqual(reponse.status_code, 200, reponse.content.decode()[:400])
        clotures_journalieres = list(
            ClotureCaisse.objects.filter(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
        )
        self.assertEqual(len(clotures_journalieres), 1)
        self.assertEqual(clotures_journalieres[0].numero_derniere_vente, vente.numero)
        self.assertEqual(AncienneClotureCaisse.objects.count(), 0)

    def test_fk_de_cloture_vers_la_cloture_unique(self):
        """
        Une J unique, puis son ticket Z imprimé deux fois par la tâche d'impression.
        Le journal des impressions a deux lignes, liées à la J unique : la première
        est l'original, la deuxième un DUPLICATA. Le ticket envoyé à l'imprimante le
        dit aussi : `is_duplicata` faux, puis vrai.
        / A single J, its Z ticket printed twice: two log rows linked to the J, the
        second one a DUPLICATE; the ticket sent to the printer says so too.
        """
        self._vendre_une_biere_en_especes()
        uuid_de_la_j = comptabilite.tasks.generer_cloture_pour_tenant(
            schema_name=self.tenant.schema_name,
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        )
        j_du_lieu = ClotureCaisse.objects.get(uuid=uuid_de_la_j)
        imprimante = Printer.objects.create(
            name="Imprimante lecteurs bouton Z", printer_type=Printer.MOCK
        )
        imprimante_simulee = ImprimanteSimulee()

        with patch(
            "laboutik.printing.imprimer", side_effect=imprimante_simulee.imprimer
        ):
            imprimer_async(
                str(imprimante.pk),
                self._ticket_z_avec_ses_metadonnees(j_du_lieu),
                self.tenant.schema_name,
            )
            imprimer_async(
                str(imprimante.pk),
                self._ticket_z_avec_ses_metadonnees(j_du_lieu),
                self.tenant.schema_name,
            )

        impressions_du_z = list(
            ImpressionLog.objects.filter(
                type_justificatif=ImpressionLog.CLOTURE
            ).order_by("datetime")
        )
        self.assertEqual(len(impressions_du_z), 2)
        self.assertEqual(impressions_du_z[0].cloture_id, j_du_lieu.uuid)
        self.assertEqual(impressions_du_z[1].cloture_id, j_du_lieu.uuid)
        self.assertFalse(impressions_du_z[0].is_duplicata)
        self.assertTrue(impressions_du_z[1].is_duplicata)

        self.assertEqual(len(imprimante_simulee.tickets_recus), 2)
        self.assertFalse(imprimante_simulee.tickets_recus[0]["is_duplicata"])
        self.assertTrue(imprimante_simulee.tickets_recus[1]["is_duplicata"])
