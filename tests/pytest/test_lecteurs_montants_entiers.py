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

RÈGLE MÉTIER TESTÉE — LES TOTAUX CÔTÉ CLIENT (fin du fichier)
Tout montant d'argent montré au client, à l'admin ou dans un fichier se lit dans les
montants entiers écrits à la vente : `total_ttc` (net vendu), `total_ht`, `total_tva`
de chaque ligne. Jamais `amount × qty` (prix unitaire × quantité), qui se trompe d'un
centime sur un article payé avec deux moyens, et qui compte la part offerte.
Lecteurs vérifiés : `Reservation.total_paid`, `Paiement_stripe.total` et `.articles`,
`Booking.total_paid` et `.to_pay`, le mail d'annulation d'un booking, la fiche
utilisateur de l'admin, la colonne « Total » des ventes de l'admin et de l'onglet des
ventes d'une adhésion, l'écran « Émettre un avoir », le formulaire d'annulation
d'adhésion, l'export des lignes de vente et la facture d'une adhésion.
/ Every money amount shown to the customer, the admin or in a file is read from the
whole-cent amounts written at sale time, never from unit price × quantity.

BASE PARTAGÉE (fin du fichier)
Les tests des totaux tournent dans le lieu `lespass`, marqués `django_db` : chaque test
annule sa transaction à la fin (tests/PIEGES.md 13.1). Stripe (catalogue, remboursement)
et Celery sont simulés. La caisse est activée en mémoire (`configuration_modifiee`),
jamais enregistrée (tests/PIEGES.md 13.22). Les ventes sont écrites par le service de
vente, ou par le vrai geste (caisse, admin) quand le test le dit.
/ Shared venue, rolled back per test; Stripe and Celery faked; sales through the sale
service or the real gesture.

D'OÙ VIENNENT LES VALEURS ATTENDUES (totaux côté client)
- L'exemple fil rouge du chantier (CHANTIER-05-diagnostic.md) : 3 articles à 3,50 €
  payés 5,00 € en monnaie locale + 5,50 € par CB. Deux parts : prix unitaire 350,
  quantités 1,428571 et 1,571429, nets 500 et 550. Total juste : 1050 (10,50 €).
  `amount × qty` tronqué donne 499 + 550 = 1049 (10,49 €).
- Une entrée à 20,00 € dont 5,00 € offerts : catalogue 2000, part offerte 500, net
  1500. HT = arrondi(1500 × 100 / 120) = 1250, TVA = 1500 − 1250 = 250.
  `amount × qty` donne 2000 (20,00 €), la part offerte comprise.
- Un billet à 15,00 € offert à la caisse : net 0 ; son avoir n'a qu'un règlement
  « offert » de −1500 (fiche D).
- Une adhésion à 35,00 € payée 10,00 € avec la carte (monnaie locale) + 25,00 € par CB
  (complément) : deux parts de 1000 et 2500, total 3500.
/ Expected values: the chantier's running example (10.50, not 10.49), a 20.00 entry with
5.00 offered (net 15.00, HT 12.50, VAT 2.50), an offered 15.00 ticket (net 0), a 35.00
membership paid 10.00 card + 25.00 CB.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-G-lecteurs.md (§2, §2.1,
§4, §5 tests 1, 2, 3, 11, 11b, 12 et 17 ; machine à états T21).

Lancer / Run : make test ARGS="tests/pytest/test_lecteurs_montants_entiers.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import re  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime, time, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import pytest  # noqa: E402
from django.db import connection  # noqa: E402
from django.utils import timezone, translation  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402
from django_tenants.utils import tenant_context  # noqa: E402

import comptabilite.tasks  # noqa: E402
from Administration.admin.site import staff_admin_site  # noqa: E402
from Administration.admin_tenant import LigneArticleInline  # noqa: E402
from Administration.importers.lignearticle_exporter import (  # noqa: E402
    LigneArticleExportResource,
)
from ApiBillet.serializers import get_or_create_price_sold  # noqa: E402
from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Configuration,
    LigneArticle,
    Membership,
    Paiement_stripe,
    PaymentMethod,
    Reservation,
    SaleOrigin,
)
from BaseBillet.models_vente import Vente  # noqa: E402
from BaseBillet.services_vente import (  # noqa: E402
    ajouter_article,
    ajouter_reglement,
    encaisser_vente,
    ouvrir_vente,
)
from BaseBillet.tasks import create_membership_invoice_pdf  # noqa: E402
from booking.models import Booking  # noqa: E402
from booking.tasks import send_booking_cancellation_user  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from fabriques_ecran import (  # noqa: E402
    lire_l_element,
    tableaux_de_la_page,
    textes_des_elements,
)
from fabriques_panier import (  # noqa: E402
    catalogue_stripe_simule,
    configuration_modifiee,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_ressource_avec_tarif,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from fedow_connect.models import FedowConfig  # noqa: E402
from test_caisse_effets_adhesion import (  # noqa: E402
    completer_le_paiement_de_l_adhesion,
    creer_la_carte_de_l_adherente_avec_10_euros,
)
from test_caracterisation_annulations import (  # noqa: E402
    annuler_des_billets_depuis_l_admin,
    rembourser_comme_stripe,
    vendre_un_billet_offert_a_la_caisse,
)
from test_caracterisation_caisse import (  # noqa: E402
    creer_un_point_de_vente,
    payer_a_la_caisse,
)
from test_caracterisation_en_ligne import (  # noqa: E402
    EN_TETE_HTMX,
    creer_un_administrateur_du_lieu,
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
        Ouvre l'écran du détail de la vente de cette ligne (par l'uuid de la vente,
        comme l'historique des ventes). Rend le HTML de l'écran.
        / Opens the sale detail screen of this line's sale. Returns its HTML.
        """
        reponse = self.client_du_caissier.get(
            f"{DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE}{ligne.vente_id}/"
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

    def test_correction_refusee_ligne_sans_vente(self):
        """
        Une ligne de bière en espèces écrite SANS vente (comme les lignes d'avant
        les ventes, base de dev seulement). Aucune J n'existe. La corriger en CB est
        refusé (400), rien n'est écrit. L'écran du détail s'ouvre par l'uuid d'une
        vente : une ligne sans vente n'y apparaît jamais.
        / A beer line written WITHOUT a sale, no J: correcting it is refused. The
        detail screen opens by a sale's uuid: such a line never shows there.
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

        reponse = self._corriger_en_cb(ligne_sans_vente)

        self._verifier_le_refus(reponse, ligne_sans_vente, MESSAGE_VENTE_PAS_REGLEE)

    def test_detail_vente_sans_bouton_corriger_vente_en_attente(self):
        """
        Une ligne de bière en espèces dans une vente jamais encaissée : l'écran du
        détail de cette vente s'affiche, dit « En attente » (son statut) et ne
        propose pas le bouton « Corriger moyen » (la route la refuserait).
        / A beer line in a pending sale: the detail shows "En attente" and does not
        offer "Correct".
        """
        ligne_en_attente = self._ecrire_une_biere_dans_une_vente_en_attente()

        contenu = self._ouvrir_le_detail_de_la_vente(ligne_en_attente)

        self.assertEqual(textes_des_elements(contenu, "detail-statut"), ["En attente"])
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


# ==========================================================================
# LES TOTAUX CÔTÉ CLIENT — base partagée, lieu `lespass`
# / CUSTOMER-SIDE TOTALS — shared database, `lespass` venue
# ==========================================================================

# Un montant de 15,00 € tel qu'un écran l'écrit, en anglais (« 15.00 € ») ou en
# français (« 15,00 € ») : la langue de l'écran ne compte pas ici.
# / 15.00 € as a screen writes it, in English or French.
MONTANT_DE_15_EUROS_A_L_ECRAN = re.compile(r"15[.,]00 €")


@pytest.fixture
def lieu(tenant, mock_stripe):
    """
    Le lieu `lespass`, avec Stripe (session, catalogue, remboursement) et Celery
    simulés pendant tout le test. Les signaux activent la langue du lieu sans la
    remettre (tests/PIEGES.md 10.5) : elle est remise à la fin.
    / The `lespass` venue, Stripe and Celery faked; the language is reset at the end.

    `taches_demandees` se remplit au fil du test : une paire (nom court, arguments)
    par tâche demandée.
    / `taches_demandees` fills up during the test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees() as taches_demandees:
                with patch(
                    "stripe.Refund.create", side_effect=rembourser_comme_stripe
                ):
                    yield SimpleNamespace(
                        tenant=tenant,
                        taches_demandees=taches_demandees,
                    )
    translation.deactivate()


def montant_lu_dans_une_cellule(texte_de_la_cellule):
    """
    Le montant d'une cellule de tableau : « 25,00€ » ou « 25.00 € » → Decimal("25.00").
    / The amount of a table cell, whatever the decimal separator.
    """
    texte_sans_euro = texte_de_la_cellule.replace("€", "")
    texte_sans_espace = texte_sans_euro.replace(" ", "").replace(chr(0xA0), "")
    texte_avec_un_point = texte_sans_espace.replace(",", ".")
    return Decimal(texte_avec_un_point)


def ajouter_trois_articles_en_deux_parts(vente, tarif_vendu, **champs_des_deux_parts):
    """
    Ajoute à la vente l'exemple fil rouge du chantier : 3 articles à 3,50 € payés
    5,00 € en monnaie locale + 5,50 € par CB. Deux parts, comme les écrit la caisse
    quand un article est payé avec deux moyens : prix unitaire 350, quantités
    1,428571 (monnaie locale, net 500) et 1,571429 (CB, net 550).
    Rend les deux parts.
    / Adds the running example: 3 items at 3.50 € paid 5.00 local + 5.50 CB, in two
    parts. Returns both parts.

    :param champs_des_deux_parts: champs posés sur les deux parts (`reservation`,
        `booking`, `status`…)
    """
    part_en_monnaie_locale = ajouter_article(
        vente,
        pricesold=tarif_vendu,
        quantite=Decimal("1.428571"),
        prix_unitaire=350,
        taux_tva=Decimal("20"),
        total_catalogue_impose=500,
        payment_method=PaymentMethod.LOCAL_EURO,
        **champs_des_deux_parts,
    )
    part_par_carte_bancaire = ajouter_article(
        vente,
        pricesold=tarif_vendu,
        quantite=Decimal("1.571429"),
        prix_unitaire=350,
        taux_tva=Decimal("20"),
        total_catalogue_impose=550,
        payment_method=PaymentMethod.CC,
        **champs_des_deux_parts,
    )
    return [part_en_monnaie_locale, part_par_carte_bancaire]


def vendre_trois_articles_en_deux_parts(**champs_des_deux_parts):
    """
    Une vente de caisse réglée : l'exemple fil rouge (deux parts, 500 + 550), avec
    ses deux règlements (monnaie locale 500, CB 550). Rend la vente.
    / A settled register sale: the running example and its two payments.
    """
    tarif_vendu = creer_tarif_vendu(
        nom="Article a 3,50", prix_en_euros="3.50", taux_tva="20.00"
    )
    vente = ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE)
    ajouter_trois_articles_en_deux_parts(vente, tarif_vendu, **champs_des_deux_parts)
    ajouter_reglement(vente, moyen=PaymentMethod.LOCAL_EURO, montant=500)
    ajouter_reglement(vente, moyen=PaymentMethod.CC, montant=550)
    encaisser_vente(vente)
    verifier_egalites(vente)
    return vente


def ecrire_une_entree_dont_5_euros_offerts(
    vente, tarif_vendu, moyen_d_argent, paiement_stripe=None, **champs_de_la_ligne
):
    """
    Écrit dans la vente ouverte une entrée à 20,00 € dont 5,00 € offerts (catalogue
    2000, part offerte 500, net 1500, TVA 20 %), avec ses deux règlements : 1500 au
    moyen d'argent donné (relié au paiement Stripe s'il est donné), 500 « offert ».
    Puis encaisse la vente. Rend la ligne, relue en base.
    / Writes a 20.00 € entry with 5.00 € offered into the open sale, with its two
    payments, then settles the sale. Returns the line.
    """
    ligne = ajouter_article(
        vente,
        pricesold=tarif_vendu,
        quantite=Decimal("1"),
        prix_unitaire=2000,
        taux_tva=Decimal("20"),
        part_offerte=500,
        source_offert=LigneArticle.SourceOffert.OFFRIR,
        payment_method=moyen_d_argent,
        paiement_stripe=paiement_stripe,
        **champs_de_la_ligne,
    )
    ajouter_reglement(
        vente, moyen=moyen_d_argent, montant=1500, paiement_stripe=paiement_stripe
    )
    ajouter_reglement(vente, moyen=PaymentMethod.FREE, montant=500)
    encaisser_vente(vente)
    verifier_egalites(vente)
    ligne.refresh_from_db()
    return ligne


def creer_une_reservation_validee(acheteur):
    """
    Une réservation validée de l'acheteur, pour un événement dans une semaine. Créée
    directement : une création ne déclenche aucune transition de la machine à états.
    / A validated reservation, created directly (no state machine transition).
    """
    concert = creer_evenement_avec_tarif(prix="3.50")
    return Reservation.objects.create(
        user_commande=acheteur,
        event=concert.evenement,
        status=Reservation.VALID,
    )


def creer_un_booking_dans_deux_mois(acheteur):
    """
    Un booking d'une heure d'une ressource, dans deux mois : la date limite
    d'annulation (24 h avant) n'est pas passée.
    / A one-hour booking in two months: the cancellation deadline has not passed.
    """
    location = creer_ressource_avec_tarif(prix="3.50")
    return Booking.objects.create(
        resource=location.ressource,
        user=acheteur,
        start_datetime=timezone.now() + timedelta(days=60),
        slot_duration_minutes=60,
        slot_count=1,
    )


# --------------------------------------------------------------------------
# Réservation : total payé
# / Reservation: total paid
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_reservation_total_paid_1050(lieu):
    """
    Fiche test 11. Une réservation réglée par l'exemple fil rouge (deux parts : 500 en
    monnaie locale, 550 par CB). `total_paid()` vaut 10,50 €, la somme des nets des
    deux parts, et pas 10,49 € (prix × quantité tronqué).
    / Sheet test 11: total_paid() is 10.50, not 10.49.
    """
    reservation = creer_une_reservation_validee(creer_utilisateur())
    vendre_trois_articles_en_deux_parts(
        reservation=reservation, status=LigneArticle.VALID
    )

    assert reservation.total_paid() == Decimal("10.50")


@pytest.mark.django_db
def test_billet_entierement_offert_total_paid_zero_avoir_free_seul(
    lieu, django_capture_on_commit_callbacks
):
    """
    Fiche test 11b. Un billet à 15,00 € vendu à la caisse et OFFERT par le gérant
    (vrai geste de la caisse). Il n'a rien coûté : `total_paid()` vaut 0.
    L'admin l'annule (action « Cancel and refund » de la liste des billets) : son avoir
    est une vente AVOIR dont le seul règlement est « offert » −1500 ; aucun règlement
    d'argent.
    / Sheet test 11b: an offered 15.00 ticket: total_paid() is 0; its credit note has
    one FREE payment of −1500 and no money payment.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="15.00")
    reservation = vendre_un_billet_offert_a_la_caisse(lieu, acheteur, concert)
    ligne_du_billet_offert = LigneArticle.objects.get(reservation=reservation)
    total_paye_du_billet_offert = reservation.total_paid()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    with django_capture_on_commit_callbacks(execute=True):
        reponse = annuler_des_billets_depuis_l_admin(
            client_de_l_admin, [reservation.tickets.get()]
        )

    assert reponse.status_code == 302
    avoir = LigneArticle.objects.get(credit_note_for=ligne_du_billet_offert)
    vente_d_avoir = Vente.objects.get(pk=avoir.vente_id)
    assert vente_d_avoir.nature == Vente.Nature.AVOIR
    moyens_et_montants_des_reglements = []
    for reglement in vente_d_avoir.reglements.all():
        moyens_et_montants_des_reglements.append((reglement.moyen, reglement.montant))
    assert moyens_et_montants_des_reglements == [(PaymentMethod.FREE, -1500)]

    assert total_paye_du_billet_offert == 0


# --------------------------------------------------------------------------
# Paiement Stripe : total et articles (mails d'échec, facture)
# / Stripe payment: total and items (failure mails, invoice)
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_paiement_stripe_total_et_articles_sur_le_net_vendu(lieu):
    """
    Une vente en ligne payée par Stripe : une entrée à 20,00 € dont 5,00 € offerts.
    Stripe a reçu 15,00 €. Le total du paiement (`total()`, lu par les mails d'échec
    et de refus et par la facture) vaut 15,00 €, et la liste de ses articles
    (`articles()`) annonce 15,00 € pour l'entrée, pas 20,00 €.
    / An online sale paid by Stripe: a 20.00 entry with 5.00 offered. total() and
    articles() say 15.00, not 20.00.
    """
    acheteur = creer_utilisateur()
    vente_en_ligne = ouvrir_vente(
        origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur
    )
    # Une création : aucune transition de la machine à états ne part.
    # / A creation: no state machine transition runs.
    paiement = Paiement_stripe.objects.create(
        user=acheteur,
        status=Paiement_stripe.VALID,
        moyen=PaymentMethod.STRIPE_NOFED,
        payment_intent_id=f"pi_test_{identifiant_unique()}",
        vente=vente_en_ligne,
    )
    tarif_vendu = creer_tarif_vendu(nom="Entree", prix_en_euros="20.00")
    ecrire_une_entree_dont_5_euros_offerts(
        vente_en_ligne,
        tarif_vendu,
        PaymentMethod.STRIPE_NOFED,
        paiement_stripe=paiement,
        status=LigneArticle.VALID,
    )

    assert paiement.total() == Decimal("15.00")
    nom_du_produit = tarif_vendu.productsold.product.name
    nom_du_tarif = tarif_vendu.price.name
    assert paiement.articles() == f"{nom_du_produit} / {nom_du_tarif} / 15.00€"


# --------------------------------------------------------------------------
# Booking : total payé, reste à payer, mail d'annulation
# / Booking: total paid, amount to pay, cancellation mail
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_booking_total_paid_1050(lieu):
    """
    Un booking réglé par l'exemple fil rouge (deux parts validées, 500 + 550) :
    `total_paid()` vaut 10,50 €, pas 10,49 €.
    / A booking settled with the running example: total_paid() is 10.50.
    """
    booking = creer_un_booking_dans_deux_mois(creer_utilisateur())
    vendre_trois_articles_en_deux_parts(booking=booking, status=LigneArticle.VALID)

    assert booking.total_paid() == Decimal("10.50")


@pytest.mark.django_db
def test_booking_reste_a_payer_1050(lieu):
    """
    Un booking dont la vente est ouverte, pas encore réglée : l'exemple fil rouge en
    deux parts « créées » (500 + 550). `to_pay()` (lu pour choisir Stripe ou gratuit)
    vaut 10,50 €, pas 10,49 €.
    / A booking whose sale is still open: to_pay() is 10.50.
    """
    acheteur = creer_utilisateur()
    booking = creer_un_booking_dans_deux_mois(acheteur)
    tarif_vendu = creer_tarif_vendu(
        nom="Creneau a 3,50", prix_en_euros="3.50", taux_tva="20.00"
    )
    vente_ouverte = ouvrir_vente(
        origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur
    )
    ajouter_trois_articles_en_deux_parts(
        vente_ouverte, tarif_vendu, booking=booking, status=LigneArticle.CREATED
    )

    assert booking.to_pay() == Decimal("10.50")


@pytest.mark.django_db
def test_mail_d_annulation_du_booking_annonce_1050(lieu):
    """
    Un booking réglé par l'exemple fil rouge (500 + 550). Le mail d'annulation annonce
    le montant de la vente d'origine : 10,50 €, pas 10,49 €.
    / The booking cancellation mail announces 10.50, not 10.49.
    """
    booking = creer_un_booking_dans_deux_mois(creer_utilisateur())
    vendre_trois_articles_en_deux_parts(booking=booking, status=LigneArticle.VALID)

    with patch("booking.tasks.CeleryMailerClass") as envoi_de_mail_simule:
        send_booking_cancellation_user(str(booking.pk))

    contexte_du_mail = envoi_de_mail_simule.call_args.kwargs["context"]
    assert contexte_du_mail["refund_amount"] == Decimal("10.50")


# --------------------------------------------------------------------------
# Admin : fiche utilisateur, colonnes « Total », écran d'avoir, annulation d'adhésion
# / Admin: user page, "Total" columns, credit note screen, membership cancellation
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_fiche_utilisateur_admin_montant_paye_1050(lieu):
    """
    La fiche d'un utilisateur dans l'admin liste ses réservations avec le montant
    payé. Une réservation réglée par l'exemple fil rouge (500 + 550) y vaut 10,50 €,
    pas 10,49 €.
    / The admin user page shows 10.50 paid for the running example reservation.
    """
    acheteur = creer_utilisateur()
    reservation = creer_une_reservation_validee(acheteur)
    vendre_trois_articles_en_deux_parts(
        reservation=reservation, status=LigneArticle.VALID
    )
    # La fiche utilisateur ne montre que les clients du lieu (`client_achat`).
    # / The admin user page only shows the venue's customers.
    acheteur.client_achat.add(lieu.tenant)
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse = client_de_l_admin.get(f"/admin/AuthBillet/humanuser/{acheteur.pk}/change/")

    assert reponse.status_code == 200
    montants_affiches = []
    for evenement_a_venir in reponse.context["evenements_a_venir"]:
        montants_affiches.append(evenement_a_venir["montant"])
    assert montants_affiches == [Decimal("10.50")]


@pytest.mark.django_db
def test_admin_colonne_total_des_ventes_sur_le_net_vendu(lieu):
    """
    La liste des ventes de l'admin (`LigneArticleAdmin`), colonne « Total » : une
    entrée à 20,00 € dont 5,00 € offerts vaut 15,00 €, pas 20,00 €.
    / The admin sale list "Total" column: 15.00, not 20.00.
    """
    vente = ouvrir_vente(origine=SaleOrigin.ADMIN, nature=Vente.Nature.VENTE)
    ligne = ecrire_une_entree_dont_5_euros_offerts(
        vente,
        creer_tarif_vendu(nom="Entree", prix_en_euros="20.00"),
        PaymentMethod.CASH,
        status=LigneArticle.VALID,
    )
    admin_des_ventes = staff_admin_site._registry[LigneArticle]

    assert admin_des_ventes.total_decimal(ligne) == Decimal("15.00")


@pytest.mark.django_db
def test_admin_onglet_des_ventes_de_l_adhesion_total_sur_le_net_vendu(lieu):
    """
    L'onglet des ventes de la fiche adhésion (`LigneArticleInline`), colonne
    « Total » : une adhésion à 20,00 € dont 5,00 € offerts vaut 15,00 €, pas 20,00 €.
    / The membership page's sales tab "Total" column: 15.00, not 20.00.
    """
    adhesion = creer_adhesion(prix="20.00")
    adhesion_vendue = Membership.objects.create(
        user=creer_utilisateur(),
        price=adhesion.tarif,
        status=Membership.ADMIN_VALID,
    )
    vente = ouvrir_vente(origine=SaleOrigin.ADMIN, nature=Vente.Nature.VENTE)
    ligne = ecrire_une_entree_dont_5_euros_offerts(
        vente,
        get_or_create_price_sold(adhesion.tarif),
        PaymentMethod.CASH,
        membership=adhesion_vendue,
        status=LigneArticle.VALID,
    )
    onglet_des_ventes = LigneArticleInline(Membership, staff_admin_site)

    assert onglet_des_ventes.total_decimal(ligne) == Decimal("15.00")


@pytest.mark.django_db
def test_ecran_d_avoir_affiche_le_net_vendu(lieu):
    """
    L'écran « Émettre un avoir » d'une ligne (bouton « Avoir » de la liste des
    ventes) rappelle le montant de la ligne : une entrée à 20,00 € dont 5,00 €
    offerts affiche 15,00 €, pas 20,00 €.
    / The credit note screen shows 15.00 for the line, not 20.00.
    """
    vente = ouvrir_vente(origine=SaleOrigin.ADMIN, nature=Vente.Nature.VENTE)
    ligne = ecrire_une_entree_dont_5_euros_offerts(
        vente,
        creer_tarif_vendu(nom="Entree", prix_en_euros="20.00"),
        PaymentMethod.CASH,
        status=LigneArticle.VALID,
    )
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse = client_de_l_admin.get(
        f"/admin/BaseBillet/lignearticle/{ligne.pk}/emettre_avoir/"
    )

    assert reponse.status_code == 200
    recapitulatif, _attributs = lire_l_element(
        reponse.content.decode(), "avoir-recapitulatif"
    )
    assert MONTANT_DE_15_EUROS_A_L_ECRAN.search(recapitulatif), recapitulatif


@pytest.mark.django_db
def test_formulaire_d_annulation_d_adhesion_affiche_le_net_vendu(lieu):
    """
    Le formulaire « Annuler l'adhésion » de l'admin rappelle le dernier paiement :
    une adhésion à 20,00 € dont 5,00 € offerts, payée 15,00 € en espèces, affiche
    15,00 €, pas 20,00 €.
    / The membership cancellation form shows 15.00 for the last payment, not 20.00.
    """
    adhesion = creer_adhesion(prix="20.00")
    adhesion_vendue = Membership.objects.create(
        user=creer_utilisateur(),
        price=adhesion.tarif,
        first_name="Ada",
        last_name="Lovelace",
        status=Membership.ADMIN_VALID,
    )
    vente = ouvrir_vente(origine=SaleOrigin.ADMIN, nature=Vente.Nature.VENTE)
    ecrire_une_entree_dont_5_euros_offerts(
        vente,
        get_or_create_price_sold(adhesion.tarif),
        PaymentMethod.CASH,
        membership=adhesion_vendue,
        status=LigneArticle.VALID,
    )
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse = client_de_l_admin.get(
        f"/memberships/{adhesion_vendue.pk}/cancel/", **EN_TETE_HTMX
    )

    assert reponse.status_code == 200
    lignes_payees_affichees = textes_des_elements(
        reponse.content.decode(), "membership-cancel-ligne-payee"
    )
    assert len(lignes_payees_affichees) == 1
    assert MONTANT_DE_15_EUROS_A_L_ECRAN.search(lignes_payees_affichees[0]), (
        lignes_payees_affichees[0]
    )


# --------------------------------------------------------------------------
# Export des lignes de vente
# / Sale lines export
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_export_lignes_colonnes_entieres(lieu):
    """
    Fiche test 17. L'export des lignes de vente de l'admin a les colonnes des montants
    entiers et le numéro de la vente. Une entrée à 20,00 € dont 5,00 € offerts :
    « Total TTC » 15,00, « Total HT » 12,50, « Total TVA » 2,50, « N° de vente » le
    numéro de sa vente. Les montants sont en euros, comme les autres colonnes de
    l'export.
    / Sheet test 17: the export has the whole-cent columns (15.00, 12.50, 2.50) and the
    sale number.
    """
    vente = ouvrir_vente(origine=SaleOrigin.ADMIN, nature=Vente.Nature.VENTE)
    ligne = ecrire_une_entree_dont_5_euros_offerts(
        vente,
        creer_tarif_vendu(nom="Entree", prix_en_euros="20.00"),
        PaymentMethod.CASH,
        status=LigneArticle.VALID,
    )
    vente.refresh_from_db()

    with translation.override("fr"):
        donnees_exportees = LigneArticleExportResource().export(
            queryset=LigneArticle.objects.filter(pk=ligne.pk)
        )
        en_tetes = []
        for en_tete in donnees_exportees.headers:
            en_tetes.append(str(en_tete))

    valeurs_de_la_ligne = dict(zip(en_tetes, donnees_exportees[0]))
    assert Decimal(str(valeurs_de_la_ligne["Total TTC"])) == Decimal("15.00")
    assert Decimal(str(valeurs_de_la_ligne["Total HT"])) == Decimal("12.50")
    assert Decimal(str(valeurs_de_la_ligne["Total TVA"])) == Decimal("2.50")
    assert valeurs_de_la_ligne["N° de vente"] == vente.numero


# --------------------------------------------------------------------------
# Facture d'une adhésion payée avec deux moyens à la caisse
# / Invoice of a membership paid with two methods at the register
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_facture_adhesion_multi_moyens_35_euros(lieu):
    """
    Fiche test 12. Le caissier vend une adhésion à 35,00 € (vrais gestes de la
    caisse) : la carte NFC de l'adhérente porte 10,00 € de monnaie locale, le reste
    (25,00 €) est réglé par CB sur l'écran de complément. La caisse écrit deux parts :
    1000 et 2500.
    La facture de l'adhésion (`create_membership_invoice_pdf`) compte toute la vente :
    ses lignes font 35,00 € en tout, et son total vaut 35,00 €. Pas une seule part.
    / Sheet test 12: a 35.00 membership paid 10.00 by card + 25.00 by CB: the invoice
    lines add up to 35.00 and its total is 35.00, not a single part.
    """
    adherente = creer_utilisateur(prenom="Ada", nom="Lovelace")
    adhesion = creer_adhesion(prix="35.00")
    point_de_vente = creer_un_point_de_vente([adhesion.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    carte_de_l_adherente = creer_la_carte_de_l_adherente_avec_10_euros(
        lieu, adherente
    )

    # Le lieu est dit « hors réseau Fedow » : la caisse ne lit pas le solde du réseau,
    # aucun appel réseau. La caisse est activée en mémoire, le temps de la vente.
    # / Off the Fedow network: no network call. Register switched on in memory.
    with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
        with patch.object(FedowConfig, "can_fedow", return_value=False):
            reponse_de_la_carte = payer_a_la_caisse(
                client_du_caissier,
                point_de_vente,
                adhesion,
                quantite=1,
                moyen_de_paiement="nfc",
                autres_champs={"tag_id": carte_de_l_adherente.tag_id},
            )
            reponse_du_complement = completer_le_paiement_de_l_adhesion(
                client_du_caissier,
                point_de_vente,
                adhesion,
                champs_du_complement={
                    "moyen_complement": "carte_bancaire",
                    "tag_id_carte1": carte_de_l_adherente.tag_id,
                },
            )

    assert reponse_de_la_carte.status_code == 200
    assert reponse_du_complement.status_code == 200
    nets_des_parts = []
    for part in LigneArticle.objects.filter(pricesold__price=adhesion.tarif):
        nets_des_parts.append(part.total_ttc)
    assert sorted(nets_des_parts) == [1000, 2500]
    adhesion_vendue = Membership.objects.get(user=adherente, price=adhesion.tarif)

    # Le moteur PDF est simulé : on lit la page HTML qu'il reçoit.
    # / The PDF engine is faked: we read the HTML page it receives.
    with patch("BaseBillet.tasks.HTML") as moteur_pdf_simule:
        create_membership_invoice_pdf(adhesion_vendue)
    page_de_la_facture = moteur_pdf_simule.call_args.kwargs["string"]

    # 1er tableau : les lignes (en-tête, puis une rangée par ligne ; la dernière
    # cellule est le total de la ligne). 2e tableau : le total de la facture.
    # / 1st table: the lines (last cell = line total). 2nd table: the invoice total.
    tableaux_de_la_facture = tableaux_de_la_page(page_de_la_facture)
    rangees_des_lignes = tableaux_de_la_facture[0][1:]
    somme_des_lignes_de_la_facture = Decimal("0")
    for rangee in rangees_des_lignes:
        somme_des_lignes_de_la_facture += montant_lu_dans_une_cellule(rangee[-1])
    total_de_la_facture = montant_lu_dans_une_cellule(tableaux_de_la_facture[1][1][-1])

    assert somme_des_lignes_de_la_facture == Decimal("35.00")
    assert total_de_la_facture == Decimal("35.00")
