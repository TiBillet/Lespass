"""
tests/pytest/test_cloture_unique.py
La clôture unique d'un lieu (`comptabilite.ClotureCaisse`) : la journée glissante (J),
le filet automatique à l'heure de fermeture + 2 h, les clôtures semaine, mois et année
calendaires en heure locale, et la chaîne des clôtures.
/ The single closure of a venue: the sliding day (J), the automatic safety net at
closing time + 2 h, calendar week / month / year closures in local time, and the chain
of closures.

LOCALISATION : tests/pytest/test_cloture_unique.py

RÈGLES MÉTIER TESTÉES (fiche F §3 ; tronc D19, D28)
- La J demandée (le « Z de fin de service ») couvre [fin de la J précédente, moment de
  la clôture[. La première J d'un lieu commence à sa première vente réglée. Sans vente
  réglée depuis la J précédente, aucune J n'est créée. Une J ne se crée jamais dans
  une transaction déjà ouverte (son verrou court n'en serait plus un).
- La J porte sa plage de ventes [première, dernière], ses totaux (CA TTC, HT, TVA,
  argent reçu, nombre de ventes) et ses perpétuels : total perpétuel = celui de la J
  précédente + le CA TTC de cette J ; nombre de ventes perpétuel, de même.
- Le filet automatique (tâche horaire) : le seuil du jour est l'heure de fermeture du
  lieu + 2 h, en heure locale (`Configuration.fuseau_horaire`) ; avant ce seuil, c'est
  le seuil de la veille. Le filet fait le Z que personne n'a fait : il crée la J
  [fin de la dernière J, seuil[ si la dernière J finit avant le seuil courant (ou s'il
  n'y en a pas) ET qu'il y a au moins une vente réglée dans cette plage. La J du filet
  FINIT AU SEUIL : les ventes d'après le seuil attendent la J suivante (un service n'est
  jamais coupé en deux). Jamais une égalité d'heure : une tâche manquée à 4 h est
  rattrapée à 5 h. Rejouée, elle ne crée rien. Le seuil est comparé en UTC : la nuit
  d'un changement d'heure ne crée pas de seconde J.
- La tâche horaire de tous les lieux lance une sous-tâche par lieu : un lieu en erreur
  est journalisé et n'empêche pas les autres.
- Semaine (lundi-dimanche), mois, année : calendaires en heure locale du lieu.
  Calculées sur les ventes de la période, jamais comme la somme des J. Une période sans
  aucune vente n'a pas de clôture. Des bornes données à la main doivent avoir un fuseau
  et être une vraie semaine / un vrai mois / une vraie année du lieu.
- Une H / M / A n'est créée qu'après le filet du jour où elle finit (heure de fermeture
  + 2 h, ce jour-là) : la J de la dernière soirée de la période est créée avant elle,
  et la H / M / A porte les perpétuels de cette J.
- La tâche horaire crée TOUTES les périodes finies qui manquent depuis la dernière
  clôture du niveau (ou depuis la première vente du lieu), dans l'ordre chronologique :
  une tâche arrêtée plusieurs semaines rattrape toutes les semaines manquées.
- Une H / M / A ne se crée jamais dans une transaction déjà ouverte : juste avant son
  calcul, elle prend puis relâche le verrou des ventes dans une transaction courte.
- La commande `generer_cloture` : une erreur dans un lieu n'arrête pas les autres ; elle
  finit en erreur (code de sortie non nul).
- Aucune garde de module : un lieu « caisse seule » (ni billetterie ni adhésion) a ses
  clôtures.
- `rapport_json` = les sections du rapport des ventes (`RapportDesVentes`), plus, dans
  l'en-tête : niveau, numéro de clôture, total perpétuel, nombre de ventes perpétuel. Les
  sections « caisse espèces » et « intégrité » ne sont stockées que dans une J (chaque J
  a déjà vérifié la chaîne des ventes de sa plage).
- Une seule chaîne de clôtures, tous niveaux, dans l'ordre des numéros : chaque clôture
  porte l'empreinte HMAC (clé du lieu) de son contenu, `rapport_json` compris, et
  l'empreinte de la clôture précédente ("" pour la première). Une altération est vue.
- `verify_clotures` vérifie la chaîne des clôtures et, pour chaque J, la chaîne des
  ventes de sa plage.
/ Business rules tested: sliding J, totals and perpetual totals, the hourly safety net
in local time, calendar H / M / A computed on sales, no module guard, stored report,
one chain of closures, the audit command.

LE CONTRAT LU PAR CES TESTS
- `comptabilite.tasks.generer_cloture_pour_tenant(schema_name, niveau)` : crée la
  clôture du niveau. J : la J glissante, maintenant (le « Z de fin de service »). H / M /
  A : la période précédente, en heure locale du lieu. Rend l'uuid (texte) de la clôture
  créée, ou None si rien n'est créé (aucune vente, ou période déjà clôturée).
- `comptabilite.tasks.generer_les_clotures_automatiques_du_lieu(schema_name)` : la
  sous-tâche horaire d'un lieu (le filet J, puis les H, M, A finies qui manquent).
- `comptabilite.integrite.verifier_chaine_clotures(cle)` : la liste des anomalies de la
  chaîne des clôtures du lieu, chacune `{"numero", "uuid", "raison"}` (numéro de
  clôture) ; vide si la chaîne est saine.
- Champs de `ClotureCaisse` : `numero_premiere_vente`, `numero_derniere_vente`,
  `total_argent_recu`, `nombre_ventes_perpetuel`, `hmac_hash`, `previous_hmac`.
- En-tête du rapport stocké (`rapport_json["en_tete"]`) : `niveau`,
  `numero_de_cloture`, `total_perpetuel_en_centimes`, `nombre_de_ventes_perpetuel`.
- `Configuration.heure_de_fermeture` (heure, défaut 02:00).
/ The contract read by these tests.

D'OÙ VIENNENT LES VALEURS ATTENDUES
Les valeurs de la fiche F §6 quand elle en donne ; sinon un calcul à la main, écrit en
commentaire au-dessus de l'assertion. Un jus vaut 350 centimes, TVA 20 % : HT =
arrondi_demi_haut(350 × 100 / 120) = arrondi(291,67) = 292 ; TVA = 350 − 292 = 58
(tronc §2, TVA calculée par ligne).
/ The sheet's values when given; otherwise a hand computation above the assertion.

L'HEURE
L'heure d'encaissement d'une vente est scellée dans son empreinte : on ne la change
jamais après coup. Chaque vente, chaque clôture et chaque passage de la tâche horaire
se fait donc à une heure choisie, en remplaçant `django.utils.timezone.now` pendant
l'appel. Les dates sont en 2026 : le passage à l'heure d'été de Paris est le dimanche
29 mars (CET, UTC+1, avant ; CEST, UTC+2, après). La Martinique est à UTC−4, sans
heure d'été.
/ Time: the settlement time is fingerprinted, never changed afterwards; each sale,
closure and hourly run happens at a chosen time by replacing timezone.now.

SCHÉMA DÉDIÉ
Une clôture lit TOUTES les ventes du lieu : il faut un lieu qui ne contient que les
ventes du test (`FastTenantTestCase`). Chaque test annule sa transaction à la fin. Le
singleton `LaboutikConfiguration` est créé en base (tests/PIEGES.md 9.86) : il porte la
clé des empreintes. La `Configuration` du lieu est réécrite à chaque test (fuseau,
heure de fermeture, modules, emails) : son cache (django-solo) survit à l'annulation de
la transaction, il doit donc toujours recevoir les valeurs du test.
Les ventes sont écrites PAR LE SERVICE (`fabriques_vente.py`), jamais à la main.
/ Dedicated schema, rolled back after each test; the venue Configuration is rewritten
in every test because its cache survives the rollback.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-F-rapport-unique.md (§3,
§6 tests 14 à 18), CHANTIER-05-montants-entiers.md (D19, D28).

Lancer / Run : make test ARGS="tests/pytest/test_cloture_unique.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from datetime import datetime, time  # noqa: E402
from decimal import Decimal  # noqa: E402
from io import StringIO  # noqa: E402
from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.core.management import call_command  # noqa: E402
from django.core.management.base import CommandError  # noqa: E402
from django.db import connection, transaction  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402

import comptabilite.tasks  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Configuration,
    PaymentMethod,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement, Vente  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from Customers.models import Client  # noqa: E402
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from laboutik.models import LaboutikConfiguration  # noqa: E402

FUSEAU_DE_PARIS = ZoneInfo("Europe/Paris")
FUSEAU_DE_LA_MARTINIQUE = ZoneInfo("America/Martinique")
FUSEAU_UTC = ZoneInfo("UTC")

# Les sections du rapport stocké dans une J (`RapportDesVentes.toutes_les_sections()`).
# / The report sections stored in a J.
SECTIONS_DU_RAPPORT_D_UNE_J = {
    "en_tete",
    "chiffre_affaires",
    "reglements",
    "caisse_especes",
    "reconciliation",
    "offerts",
    "annexe",
    "points",
    "marge_brute",
    "detail",
    "integrite",
}

# Une semaine, un mois, une année : les mêmes, sans la caisse espèces (un fond de
# caisse n'a de sens que pour une journée) ni l'intégrité (vérifiée par chaque J).
# / A week, month, year: the same without the cash drawer nor integrity.
SECTIONS_DU_RAPPORT_D_UNE_PERIODE = SECTIONS_DU_RAPPORT_D_UNE_J - {
    "caisse_especes",
    "integrite",
}


def heure_de_paris(annee, mois, jour, heure, minute=0):
    """Un moment en heure de Paris. / A moment in Paris time."""
    return datetime(annee, mois, jour, heure, minute, tzinfo=FUSEAU_DE_PARIS)


def heure_utc(annee, mois, jour, heure, minute=0):
    """Un moment en UTC. / A moment in UTC."""
    return datetime(annee, mois, jour, heure, minute, tzinfo=FUSEAU_UTC)


class TestClotureUnique(FastTenantTestCase):
    """
    La clôture unique : J glissante, filet horaire, H / M / A locales, chaîne.
    / The single closure: sliding J, hourly net, local H / M / A, chain.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_cloture_unique"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-cloture-unique.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test cloture unique"

    def setUp(self):
        """
        Le lieu de test : son singleton de caisse, sa configuration (Paris, fermeture à
        2 h, billetterie et adhésion actives, aucun email de rapport) et un jus à 3,50 €.
        / The test venue: register singleton, configuration, a juice at 3.50 €.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse doit exister en base (tests/PIEGES.md 9.86) : il
        # porte la clé des empreintes.
        # / The register singleton must exist in the database (fingerprint key).
        LaboutikConfiguration.get_solo().save()

        # Toutes les valeurs lues par la clôture sont écrites ici : le cache de la
        # configuration garde les valeurs du test précédent.
        # / Every value read by the closure is written here: the config cache keeps the
        # previous test's values.
        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.heure_de_fermeture = time(2, 0)
        configuration.module_billetterie = True
        configuration.module_adhesion = True
        configuration.rapport_emails = ""
        configuration.save()

        self.tarif_du_jus = creer_tarif_vendu(
            nom="Jus",
            prix_en_euros="3.50",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )

    # ------------------------------------------------------------------
    # Outils du test
    # / Test helpers
    # ------------------------------------------------------------------

    def _changer_la_configuration(self, **valeurs):
        """
        Écrit des valeurs dans la configuration du lieu (et dans son cache).
        / Writes values into the venue configuration (and its cache).
        """
        configuration = Configuration.get_solo()
        for nom_du_champ, valeur in valeurs.items():
            setattr(configuration, nom_du_champ, valeur)
        configuration.save()

    def _vendre_des_jus_a(self, moment, quantite=1):
        """
        Une vente de caisse encaissée à `moment` : `quantite` jus à 3,50 € en espèces.
        / A register sale settled at `moment`: `quantite` juices in cash.
        """
        montant_en_centimes = 350 * quantite
        with patch("django.utils.timezone.now", return_value=moment):
            vente = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": self.tarif_du_jus,
                        "quantite": Decimal(quantite),
                        "prix_unitaire": 350,
                        "taux_tva": Decimal("20"),
                    },
                ],
                reglements=[
                    {"moyen": PaymentMethod.CASH, "montant": montant_en_centimes},
                ],
            )
        verifier_egalites(vente)
        return vente

    def _cloturer_a(self, moment, niveau=ClotureCaisse.NIVEAU_JOURNALIER):
        """
        Lance la clôture d'un niveau à `moment` (pour J : le « Z de fin de service »).
        Rend la clôture créée, ou None.
        / Runs the closure of a level at `moment`. Returns the closure, or None.
        """
        with patch("django.utils.timezone.now", return_value=moment):
            uuid_de_la_cloture = comptabilite.tasks.generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=niveau,
            )
        if uuid_de_la_cloture is None:
            return None
        return ClotureCaisse.objects.get(uuid=uuid_de_la_cloture)

    def _lancer_la_tache_horaire_a(self, moment):
        """
        Lance la tâche horaire du lieu (filet J, puis H, M, A) à `moment`.
        / Runs the venue's hourly task at `moment`.
        """
        with patch("django.utils.timezone.now", return_value=moment):
            comptabilite.tasks.generer_les_clotures_automatiques_du_lieu(
                self.tenant.schema_name
            )

    def _clotures_du_niveau(self, niveau):
        """Les clôtures d'un niveau, par numéro. / Closures of a level, by number."""
        return list(
            ClotureCaisse.objects.filter(niveau=niveau).order_by("numero_sequentiel")
        )

    def _cle_du_lieu(self):
        """La clé des empreintes du lieu. / The venue's fingerprint key."""
        return LaboutikConfiguration.get_solo().get_or_create_hmac_key()

    # ------------------------------------------------------------------
    # 14 — La J de fin de service : plage, totaux, perpétuels
    # / 14 — The end-of-service J: range, totals, perpetual totals
    # ------------------------------------------------------------------

    def test_cloture_j_fin_de_service_plage_et_perpetuel(self):
        """
        Deux jus vendus, J n° 1 ; un jus vendu, J n° 2. Chaque J porte sa plage, ses
        totaux et ses perpétuels ; la J n° 2 commence où la J n° 1 finit.
        / Two juices, J no. 1; one juice, J no. 2: range, totals, perpetual totals.
        """
        premiere_vente = self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 18, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 18, 30))
        premiere_j = self._cloturer_a(heure_de_paris(2026, 3, 10, 19, 0))

        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 20, 0))
        deuxieme_j = self._cloturer_a(heure_de_paris(2026, 3, 10, 23, 0))

        # La première J d'un lieu commence à sa première vente réglée ; elle finit au
        # moment de la clôture.
        # / The first J starts at the first settled sale; it ends at closing time.
        heure_de_la_premiere_vente = Vente.objects.get(
            pk=premiere_vente.pk
        ).datetime_encaissement
        self.assertEqual(premiere_j.niveau, ClotureCaisse.NIVEAU_JOURNALIER)
        self.assertEqual(premiere_j.numero_sequentiel, 1)
        self.assertEqual(premiere_j.datetime_debut, heure_de_la_premiere_vente)
        self.assertEqual(premiere_j.datetime_fin, heure_de_paris(2026, 3, 10, 19, 0))

        # J n° 1 : ventes n° 1 et 2, deux jus. CA 2 × 350 = 700 ; HT 2 × 292 = 584 ;
        # TVA 2 × 58 = 116 ; argent reçu 700 (espèces). Perpétuels : 0 + 700, 0 + 2.
        # / J no. 1: sales 1 and 2, two juices.
        self.assertEqual(premiere_j.numero_premiere_vente, 1)
        self.assertEqual(premiere_j.numero_derniere_vente, 2)
        self.assertEqual(premiere_j.nombre_transactions, 2)
        self.assertEqual(premiere_j.total_general, 700)
        self.assertEqual(premiere_j.total_ht, 584)
        self.assertEqual(premiere_j.total_tva, 116)
        self.assertEqual(premiere_j.total_argent_recu, 700)
        self.assertEqual(premiere_j.total_perpetuel, 700)
        self.assertEqual(premiere_j.nombre_ventes_perpetuel, 2)

        # J n° 2 : [fin de la J n° 1, 23 h[, vente n° 3. CA 350. Perpétuels :
        # 700 + 350 = 1050 ; 2 + 1 = 3 (fiche F §6 test 14 : précédent + CA).
        # / J no. 2: from the end of J no. 1, sale 3; perpetual = previous + this J.
        self.assertEqual(deuxieme_j.numero_sequentiel, 2)
        self.assertEqual(deuxieme_j.datetime_debut, premiere_j.datetime_fin)
        self.assertEqual(deuxieme_j.datetime_fin, heure_de_paris(2026, 3, 10, 23, 0))
        self.assertEqual(deuxieme_j.numero_premiere_vente, 3)
        self.assertEqual(deuxieme_j.numero_derniere_vente, 3)
        self.assertEqual(deuxieme_j.total_general, 350)
        self.assertEqual(deuxieme_j.total_perpetuel, 1050)
        self.assertEqual(deuxieme_j.nombre_ventes_perpetuel, 3)

        # Le rapport stocké : toutes les sections, et l'en-tête de la clôture.
        # / The stored report: every section, and the closure header.
        self.assertEqual(
            set(deuxieme_j.rapport_json.keys()), SECTIONS_DU_RAPPORT_D_UNE_J
        )
        en_tete = deuxieme_j.rapport_json["en_tete"]
        self.assertEqual(en_tete["niveau"], ClotureCaisse.NIVEAU_JOURNALIER)
        self.assertEqual(en_tete["numero_de_cloture"], 2)
        self.assertEqual(en_tete["total_perpetuel_en_centimes"], 1050)
        self.assertEqual(en_tete["nombre_de_ventes_perpetuel"], 3)
        self.assertEqual(en_tete["numero_premiere_vente"], 3)
        self.assertEqual(en_tete["numero_derniere_vente"], 3)

    def test_deux_j_se_suivent_sans_trou_ni_chevauchement_de_plage(self):
        """
        Deux ventes, J ; deux ventes, J. Les plages se suivent : la seconde commence au
        numéro qui suit la fin de la première, et à l'heure où la première finit.
        / Two consecutive J: no gap, no overlap, in numbers and in time.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 10, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 11, 0))
        premiere_j = self._cloturer_a(heure_de_paris(2026, 3, 10, 12, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 13, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 14, 0))
        deuxieme_j = self._cloturer_a(heure_de_paris(2026, 3, 10, 15, 0))

        # Plages [1, 2] puis [3, 4] ; 2 + 2 = les 4 ventes, chacune une seule fois.
        # / Ranges [1, 2] then [3, 4].
        self.assertEqual(
            (premiere_j.numero_premiere_vente, premiere_j.numero_derniere_vente), (1, 2)
        )
        self.assertEqual(
            (deuxieme_j.numero_premiere_vente, deuxieme_j.numero_derniere_vente), (3, 4)
        )
        self.assertEqual(
            deuxieme_j.numero_premiere_vente, premiere_j.numero_derniere_vente + 1
        )
        self.assertEqual(deuxieme_j.datetime_debut, premiere_j.datetime_fin)
        self.assertEqual(
            premiere_j.nombre_transactions + deuxieme_j.nombre_transactions, 4
        )

    def test_j_sans_vente_depuis_la_precedente_n_est_pas_creee(self):
        """
        Une J, puis une nouvelle demande de J sans vente entre les deux : rien n'est
        créé (fiche F §3.1 : pas de nouvelle J sans vente depuis la précédente).
        / A J request without any sale since the previous J creates nothing.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 10, 0))
        self._cloturer_a(heure_de_paris(2026, 3, 10, 12, 0))

        seconde_demande = self._cloturer_a(heure_de_paris(2026, 3, 10, 18, 0))

        self.assertIsNone(seconde_demande)
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

    def test_deux_appels_de_la_tache_a_la_meme_heure_ne_creent_qu_une_j(self):
        """
        Une vente le 10 à 22 h ; la tâche horaire est lancée deux fois de suite le 11
        à 4 h 10 (deux workers, ou une tâche rejouée) : une seule J.
        / Two runs of the hourly task at the same time create one J.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 22, 0))

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 4, 10))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 4, 10))

        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

    def test_vente_encaissee_pendant_le_calcul_de_la_j_va_dans_la_j_suivante(self):
        """
        Une vente à 10 h ; la J est demandée à 12 h. Pendant le calcul de son rapport
        (après la fixation de sa fin, avant sa création), un jus est encaissé à
        12 h 01 : le calcul ne tient aucun verrou des ventes, la caisse encaisse. Ce
        jus n'est pas dans la J (plage [1, 1], CA 350) ; il est dans la J suivante
        (plage [2, 2]).
        Simulation : `RapportDesVentes` est remplacé, le temps du premier calcul, par
        une fonction qui encaisse la vente puis calcule le vrai rapport.
        / A sale settled while the J report is computed is not in that J, but in the
        next one.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 10, 0))

        rapport_des_ventes_reel = comptabilite.tasks.RapportDesVentes

        def rapport_avec_une_vente_pendant_le_calcul(debut, fin):
            self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 12, 1))
            return rapport_des_ventes_reel(debut, fin)

        with patch(
            "comptabilite.tasks.RapportDesVentes",
            side_effect=rapport_avec_une_vente_pendant_le_calcul,
        ):
            premiere_j = self._cloturer_a(heure_de_paris(2026, 3, 10, 12, 0))
        deuxieme_j = self._cloturer_a(heure_de_paris(2026, 3, 10, 14, 0))

        self.assertEqual(premiere_j.datetime_fin, heure_de_paris(2026, 3, 10, 12, 0))
        self.assertEqual(
            (premiere_j.numero_premiere_vente, premiere_j.numero_derniere_vente), (1, 1)
        )
        self.assertEqual(premiere_j.total_general, 350)
        self.assertEqual(
            (deuxieme_j.numero_premiere_vente, deuxieme_j.numero_derniere_vente), (2, 2)
        )

    def test_j_creee_par_un_autre_appel_pendant_le_calcul_rien_n_est_cree(self):
        """
        Une vente à 10 h ; deux demandes de J. Pendant le calcul du rapport de la
        première, la seconde crée sa J (simulée : `RapportDesVentes` remplacé, le temps
        du premier calcul, par une fonction qui lance la seconde demande puis calcule le
        vrai rapport). Au moment de se créer, la première voit qu'une J est née
        entre-temps : elle ne crée rien. Une seule J.
        / If another call created a J during the report computation, nothing is created.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 10, 0))

        rapport_des_ventes_reel = comptabilite.tasks.RapportDesVentes
        premier_calcul_deja_passe = []

        def rapport_avec_une_autre_j_pendant_le_calcul(debut, fin):
            if not premier_calcul_deja_passe:
                premier_calcul_deja_passe.append(True)
                comptabilite.tasks._creer_la_cloture_journaliere()
            return rapport_des_ventes_reel(debut, fin)

        with patch(
            "comptabilite.tasks.RapportDesVentes",
            side_effect=rapport_avec_une_autre_j_pendant_le_calcul,
        ):
            premiere_demande = self._cloturer_a(heure_de_paris(2026, 3, 10, 12, 0))

        self.assertIsNone(premiere_demande)
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

    # ------------------------------------------------------------------
    # 15 — Le filet horaire
    # / 15 — The hourly safety net
    # ------------------------------------------------------------------

    def test_filet_4h_cree_la_j_seulement_s_il_y_a_des_ventes(self):
        """
        Paris, fermeture 2 h (seuil 4 h). Une J de fin de service le 10 à 20 h. Le 11
        à 4 h 30, aucune vente depuis : la tâche ne crée rien. Une vente à 4 h 40 (après
        le seuil) ; à 5 h, la tâche ne crée toujours rien : la vente est du service du
        11. Le 12 à 4 h 10, la J [10 à 20 h, 12 à 4 h[ la contient.
        / The net only closes sales made before the threshold.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 19, 0))
        self._cloturer_a(heure_de_paris(2026, 3, 10, 20, 0))

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 4, 30))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

        self._vendre_des_jus_a(heure_de_paris(2026, 3, 11, 4, 40))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 5, 0))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 12, 4, 10))

        clotures_j = self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)
        self.assertEqual(len(clotures_j), 2)
        # La J du filet couvre [10 à 20 h, 12 à 4 h[ : la vente n° 2.
        # / The net's J covers the sale no. 2.
        self.assertEqual(
            clotures_j[1].datetime_debut, heure_de_paris(2026, 3, 10, 20, 0)
        )
        self.assertEqual(clotures_j[1].datetime_fin, heure_de_paris(2026, 3, 12, 4, 0))
        self.assertEqual(clotures_j[1].numero_premiere_vente, 2)
        self.assertEqual(clotures_j[1].numero_derniere_vente, 2)

    def test_la_j_du_filet_finit_au_seuil(self):
        """
        Une vente le 10 à 22 h. La tâche de 4 h n'a pas tourné ; celle de 5 h 30 crée
        la J : elle finit au seuil (11 à 4 h), pas à 5 h 30.
        / The net's J ends at the threshold, not at the run time.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 22, 0))

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 5, 30))

        clotures_j = self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)
        self.assertEqual(len(clotures_j), 1)
        self.assertEqual(clotures_j[0].datetime_fin, heure_de_paris(2026, 3, 11, 4, 0))

    def test_filet_apres_un_z_la_vente_du_lendemain_soir_attend_le_seuil_suivant(self):
        """
        Une vente le 10 à 23 h ; le Z de fin de service le 11 à 1 h. Une vente le 11 à
        18 h (le service du soir commence). La tâche de 19 h ne crée rien (le service
        n'est pas coupé en deux). La tâche du 12 à 4 h 10 crée la J [11 à 1 h, 12 à
        4 h[ : la vente n° 2.
        / An evening sale after a Z waits for the next threshold.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 23, 0))
        self._cloturer_a(heure_de_paris(2026, 3, 11, 1, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 11, 18, 0))

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 19, 0))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 12, 4, 10))
        clotures_j = self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)
        self.assertEqual(len(clotures_j), 2)
        self.assertEqual(
            clotures_j[1].datetime_debut, heure_de_paris(2026, 3, 11, 1, 0)
        )
        self.assertEqual(clotures_j[1].datetime_fin, heure_de_paris(2026, 3, 12, 4, 0))
        self.assertEqual(
            (clotures_j[1].numero_premiere_vente, clotures_j[1].numero_derniere_vente),
            (2, 2),
        )

    def test_premiere_vente_du_lieu_a_18h_aucune_j_avant_le_seuil(self):
        """
        La toute première vente du lieu, le 10 à 18 h. La tâche de 19 h ne crée rien
        (le seuil courant, le 10 à 4 h, est avant la vente). La tâche du 11 à 4 h 10
        crée la J.
        / The venue's very first sale at 18:00: no J before the next threshold.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 18, 0))

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 10, 19, 0))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 0
        )

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 4, 10))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

    def test_filet_nuit_du_passage_a_l_heure_d_ete_une_seule_j(self):
        """
        Paris, fermeture à 0 h 30 : seuil à 2 h 30. La nuit du 28 au 29 mars 2026, on
        passe de 2 h (CET) à 3 h (CEST) : 2 h 30 n'existe pas, le seuil est 1 h 30 UTC
        (0 h 30 CET + 2 h). Une vente le 28 à 22 h. La tâche passe à 0 h, 1 h, 2 h et
        3 h UTC : rien à 1 h UTC (3 h CEST à l'horloge, mais le seuil n'est pas atteint
        en UTC) ; une J à 2 h UTC, qui finit au seuil ; aucune seconde J.
        / Spring DST night: one J, ending at the threshold, never in the future.
        """
        self._changer_la_configuration(heure_de_fermeture=time(0, 30))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 28, 22, 0))

        self._lancer_la_tache_horaire_a(heure_utc(2026, 3, 29, 0, 0))
        self._lancer_la_tache_horaire_a(heure_utc(2026, 3, 29, 1, 0))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 0
        )

        self._lancer_la_tache_horaire_a(heure_utc(2026, 3, 29, 2, 0))
        self._lancer_la_tache_horaire_a(heure_utc(2026, 3, 29, 3, 0))

        clotures_j = self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)
        self.assertEqual(len(clotures_j), 1)
        self.assertEqual(clotures_j[0].datetime_fin, heure_utc(2026, 3, 29, 1, 30))
        self.assertLessEqual(clotures_j[0].datetime_fin, clotures_j[0].created_at)

    def test_filet_nuit_du_passage_a_l_heure_d_hiver_une_seule_j(self):
        """
        Paris, fermeture à 0 h 30 : seuil à 2 h 30. La nuit du 24 au 25 octobre 2026,
        on passe de 3 h (CEST) à 2 h (CET) : 2 h 30 existe deux fois, le seuil est la
        première (0 h 30 UTC). Une vente le 24 à 22 h. La tâche passe à 23 h, 0 h, 1 h et
        2 h UTC : rien à 0 h UTC ; une J à 1 h UTC (2 h CET à l'horloge, mais le seuil
        est passé en UTC), qui finit au seuil ; aucune seconde J.
        / Autumn DST night: one J at the first run after the threshold in UTC.
        """
        self._changer_la_configuration(heure_de_fermeture=time(0, 30))
        self._vendre_des_jus_a(heure_de_paris(2026, 10, 24, 22, 0))

        self._lancer_la_tache_horaire_a(heure_utc(2026, 10, 24, 23, 0))
        self._lancer_la_tache_horaire_a(heure_utc(2026, 10, 25, 0, 0))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 0
        )

        self._lancer_la_tache_horaire_a(heure_utc(2026, 10, 25, 1, 0))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

        self._lancer_la_tache_horaire_a(heure_utc(2026, 10, 25, 2, 0))
        clotures_j = self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)
        self.assertEqual(len(clotures_j), 1)
        self.assertEqual(clotures_j[0].datetime_fin, heure_utc(2026, 10, 25, 0, 30))

    def test_cloture_j_refusee_dans_une_transaction_ouverte(self):
        """
        Une J demandée dans une transaction déjà ouverte est refusée (RuntimeError) : le
        verrou des ventes ne serait relâché qu'à la fin de cette transaction, et la
        caisse attendrait pendant tout le calcul du rapport.
        / A J requested inside an open transaction is refused.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 10, 0))

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self._cloturer_a(heure_de_paris(2026, 3, 10, 12, 0))

    def test_tache_d_un_lieu_journalise_son_erreur_avec_le_nom_du_lieu(self):
        """
        Une erreur dans la tâche horaire d'un lieu est journalisée avec le schéma du
        lieu, puis remontée (Celery la note en échec).
        / An error in a venue's hourly task is logged with the venue's schema.
        """
        with patch(
            "comptabilite.tasks._creer_la_cloture_journaliere",
            side_effect=RuntimeError("panne simulée"),
        ):
            with self.assertLogs("comptabilite.tasks", level="ERROR") as journal:
                with self.assertRaises(RuntimeError):
                    self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 4, 10))

        self.assertIn(self.tenant.schema_name, "\n".join(journal.output))

    def test_filet_4h_heure_locale_du_lieu(self):
        """
        Fiche F §6 test 15b. Une J de fin de service le 9 mars à 20 h UTC, puis une
        vente à 22 h UTC. La tâche passe le 10 mars à 4 h 30 UTC (celle de 4 h n'a pas
        tourné) :
        - lieu en Martinique (UTC−4) : il est 0 h 30 le 10, le seuil courant est le 9
          à 4 h locale (8 h UTC), la dernière J finit après lui → rien ;
        - lieu à Paris (UTC+1) : il est 5 h 30 le 10, le seuil courant est le 10 à 4 h
          locale (3 h UTC), la dernière J finit avant lui et une vente a eu lieu
          depuis → une J (« au moins » 4 h, pas « égal à » 4 h) ;
        - rejouée une heure plus tard à Paris : aucune seconde J.
        Le même lieu change de fuseau entre les deux passages : un seul schéma de test.
        / Local time of the venue: Martinique no J, Paris one J, replayed nothing.
        """
        self._vendre_des_jus_a(heure_utc(2026, 3, 9, 19, 0))
        self._cloturer_a(heure_utc(2026, 3, 9, 20, 0))
        self._vendre_des_jus_a(heure_utc(2026, 3, 9, 22, 0))

        self._changer_la_configuration(fuseau_horaire="America/Martinique")
        self._lancer_la_tache_horaire_a(heure_utc(2026, 3, 10, 4, 30))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

        self._changer_la_configuration(fuseau_horaire="Europe/Paris")
        self._lancer_la_tache_horaire_a(heure_utc(2026, 3, 10, 4, 30))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 2
        )

        self._lancer_la_tache_horaire_a(heure_utc(2026, 3, 10, 5, 30))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 2
        )

    def test_filet_suit_l_heure_de_fermeture_plus_deux_heures(self):
        """
        Fiche F §6 test 15c : fermeture à 23 h → filet à 1 h. Une J de fin de service
        le 10 à 20 h, une vente à 22 h. Le 11 à 0 h 30 : le seuil courant est le 10 à
        1 h, la dernière J finit après lui → rien. Le 11 à 1 h 30 : le seuil courant est
        le 11 à 1 h → la J.
        / Closing time 23:00: the net runs from 1:00.
        """
        self._changer_la_configuration(heure_de_fermeture=time(23, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 19, 0))
        self._cloturer_a(heure_de_paris(2026, 3, 10, 20, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 22, 0))

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 0, 30))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 1, 30))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 2
        )

    def test_filet_par_defaut_a_4h_pas_avant(self):
        """
        Fiche F §6 test 15c : l'heure de fermeture par défaut est 2 h → filet à 4 h.
        Une J de fin de service le 10 à 20 h, une vente à 22 h. Le 11 à 3 h 30 : rien.
        Le 11 à 4 h 30 : la J.
        / Default closing time 02:00: the net runs from 4:00, not before.
        """
        heure_de_fermeture_par_defaut = Configuration._meta.get_field(
            "heure_de_fermeture"
        ).default
        self.assertEqual(heure_de_fermeture_par_defaut, time(2, 0))

        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 19, 0))
        self._cloturer_a(heure_de_paris(2026, 3, 10, 20, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 22, 0))

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 3, 30))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 4, 30))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 2
        )

    def test_filet_ne_cree_qu_une_j_par_jour_meme_avec_des_ventes_l_apres_midi(self):
        """
        Une vente le 10 à 22 h ; la tâche de 4 h 10 le 11 crée la J. Une vente le 11 à
        15 h ; la tâche de 16 h ne crée rien : la dernière J (11 à 4 h 10) ne finit pas
        avant le seuil courant (11 à 4 h). La tâche du 12 à 4 h 10 crée la J suivante.
        / One J per day: afternoon sales wait for the next day's threshold.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 22, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 4, 10))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

        self._vendre_des_jus_a(heure_de_paris(2026, 3, 11, 15, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 16, 0))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 12, 4, 10))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 2
        )

    def test_filet_apres_un_z_de_fin_de_service_sans_nouvelle_vente_ne_fait_rien(self):
        """
        Une vente le 10 à 23 h ; le Z de fin de service est fait le 11 à 1 h (avant le
        seuil de 4 h). La tâche de 4 h 10 ne crée rien : aucune vente depuis.
        / After an end-of-service Z and no new sale, the net does nothing.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 23, 0))
        self._cloturer_a(heure_de_paris(2026, 3, 11, 1, 0))

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 4, 10))

        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 1
        )

    def test_lieu_caisse_seule_a_ses_clotures(self):
        """
        Un lieu sans billetterie ni adhésion (caisse seule) : une vente à la caisse, la J
        est créée (aucune garde de module : le rapport compte toutes les origines).
        / A POS-only venue gets its closures.
        """
        self._changer_la_configuration(
            module_billetterie=False, module_adhesion=False, module_caisse=True
        )
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 18, 0))

        cloture_j = self._cloturer_a(heure_de_paris(2026, 3, 10, 20, 0))

        self.assertIsNotNone(cloture_j)
        self.assertEqual(cloture_j.total_general, 350)

    # ------------------------------------------------------------------
    # 16, 17 — Semaine, mois, année : calendaires, en heure locale
    # / 16, 17 — Week, month, year: calendar, local time
    # ------------------------------------------------------------------

    def test_mois_calendaire_egal_ventes_du_mois(self):
        """
        Fiche F §6 test 16. Une J de soirée à cheval sur deux mois : un jus le 31 mars
        à 22 h (Paris, CEST : 20 h UTC), deux jus le 1ᵉʳ avril à 1 h (23 h UTC le 31
        mars). La tâche du 1ᵉʳ avril à 4 h 10 crée la J (les deux ventes) et la M de
        mars : seulement le jus du 31 (chaque vente dans son mois, en heure locale ; la
        M n'est pas la somme des J).
        / A J across two months: the March M only counts the March sale (local time).
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 31, 22, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 4, 1, 1, 0), quantite=2)

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 4, 1, 4, 10))

        clotures_j = self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)
        self.assertEqual(len(clotures_j), 1)
        # La J : 350 + 700 = 1050.
        # / The J: 350 + 700.
        self.assertEqual(clotures_j[0].total_general, 1050)

        clotures_m = self._clotures_du_niveau(ClotureCaisse.NIVEAU_MENSUEL)
        self.assertEqual(len(clotures_m), 1)
        mois_de_mars = clotures_m[0]
        # Mars en heure de Paris : du 1ᵉʳ mars 0 h (CET) au 1ᵉʳ avril 0 h (CEST).
        # / March in Paris time.
        self.assertEqual(mois_de_mars.datetime_debut, heure_de_paris(2026, 3, 1, 0, 0))
        self.assertEqual(mois_de_mars.datetime_fin, heure_de_paris(2026, 4, 1, 0, 0))
        # Seulement la vente n° 1 : 350 (HT 292, TVA 58).
        # / Only sale no. 1.
        self.assertEqual(mois_de_mars.total_general, 350)
        self.assertEqual(mois_de_mars.total_ht, 292)
        self.assertEqual(mois_de_mars.total_tva, 58)
        self.assertEqual(mois_de_mars.nombre_transactions, 1)
        self.assertEqual(mois_de_mars.numero_premiere_vente, 1)
        self.assertEqual(mois_de_mars.numero_derniere_vente, 1)

    def test_cloture_hebdomadaire_calendaire_non_vide(self):
        """
        Fiche F §6 test 17. Semaine du lundi 9 au dimanche 15 mars (Paris) : un jus le
        mercredi 11 à 12 h, un jus le dimanche 15 à 23 h 30. Un jus le lundi 16 à 0 h 30
        (le 15 à 23 h 30 UTC : encore dimanche en UTC). La tâche du lundi 16 à 1 h 10
        ne crée pas encore la H : le filet du lundi (4 h) n'est pas passé. La tâche de
        4 h 10 crée la H de la semaine : les deux premiers jus seulement. Rejouée à
        5 h 10 : toujours une seule H.
        / The previous calendar week in local time, after Monday's net; replayed, still
        one H.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 11, 12, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 15, 23, 30))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 16, 0, 30))

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 16, 1, 10))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_HEBDOMADAIRE)), 0
        )

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 16, 4, 10))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 16, 5, 10))

        clotures_h = self._clotures_du_niveau(ClotureCaisse.NIVEAU_HEBDOMADAIRE)
        self.assertEqual(len(clotures_h), 1)
        semaine = clotures_h[0]
        self.assertEqual(semaine.datetime_debut, heure_de_paris(2026, 3, 9, 0, 0))
        self.assertEqual(semaine.datetime_fin, heure_de_paris(2026, 3, 16, 0, 0))
        # Deux jus : 2 × 350 = 700, ventes n° 1 et 2.
        # / Two juices.
        self.assertEqual(semaine.total_general, 700)
        self.assertEqual(semaine.nombre_transactions, 2)
        self.assertEqual(semaine.numero_premiere_vente, 1)
        self.assertEqual(semaine.numero_derniere_vente, 2)

    def test_mois_sans_vente_pas_de_cloture(self):
        """
        Février sans aucune vente (une vente le 2 mars seulement) : la clôture du mois
        de février, demandée le 5 mars, n'est pas créée : une période sans vente n'a
        jamais de clôture (pas de clôture vide).
        / A month without any sale has no closure.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 2, 12, 0))

        cloture_m = self._cloturer_a(
            heure_de_paris(2026, 3, 5, 10, 0), niveau=ClotureCaisse.NIVEAU_MENSUEL
        )

        self.assertIsNone(cloture_m)
        self.assertEqual(len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_MENSUEL)), 0)

    def test_cloture_h_m_a_sans_section_caisse_especes(self):
        """
        Une vente le 10 février. Le 2 mars, la J et la M de février : la J stocke la
        caisse espèces, la M ne la stocke pas (un fond de caisse n'a pas de sens sur un
        mois).
        / The cash drawer section is stored in a J only.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 2, 10, 12, 0))

        cloture_j = self._cloturer_a(heure_de_paris(2026, 3, 2, 10, 0))
        cloture_m = self._cloturer_a(
            heure_de_paris(2026, 3, 2, 10, 0), niveau=ClotureCaisse.NIVEAU_MENSUEL
        )

        self.assertEqual(
            set(cloture_j.rapport_json.keys()), SECTIONS_DU_RAPPORT_D_UNE_J
        )
        self.assertEqual(
            set(cloture_m.rapport_json.keys()), SECTIONS_DU_RAPPORT_D_UNE_PERIODE
        )
        self.assertEqual(
            cloture_m.rapport_json["en_tete"]["niveau"], ClotureCaisse.NIVEAU_MENSUEL
        )

    def test_cloture_h_m_a_sans_section_integrite(self):
        """
        Une vente le 10 février. Le 2 mars, la J et la M de février : la J stocke
        l'intégrité (la chaîne des ventes de sa plage), la M ne la stocke pas (chaque J
        l'a déjà vérifiée ; une année entière coûterait des centaines de milliers de
        requêtes).
        / The integrity section is stored in a J only.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 2, 10, 12, 0))

        cloture_j = self._cloturer_a(heure_de_paris(2026, 3, 2, 10, 0))
        cloture_m = self._cloturer_a(
            heure_de_paris(2026, 3, 2, 10, 0), niveau=ClotureCaisse.NIVEAU_MENSUEL
        )

        self.assertIn("integrite", cloture_j.rapport_json)
        self.assertNotIn("integrite", cloture_m.rapport_json)

    def test_m_de_fin_de_mois_creee_apres_la_j_de_la_derniere_soiree(self):
        """
        Un jus le 30 avril à 22 h (Paris), dernière soirée du mois. La tâche du 1ᵉʳ mai
        à 0 h 30 ne crée rien : ni J (la vente est après le seuil courant, le 30 à
        4 h), ni M d'avril (le filet du 1ᵉʳ mai, à 4 h, n'est pas passé). La tâche de
        4 h 10 crée la J de la soirée du 30, PUIS la M d'avril : numéros croissants, et
        la M porte les perpétuels de cette J (350 et 1 vente).
        / The month-end M is created after the J of the last evening, with its
        perpetual totals.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 4, 30, 22, 0))

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 5, 1, 0, 30))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)), 0
        )
        self.assertEqual(len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_MENSUEL)), 0)

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 5, 1, 4, 10))

        clotures_j = self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)
        clotures_m = self._clotures_du_niveau(ClotureCaisse.NIVEAU_MENSUEL)
        self.assertEqual(len(clotures_j), 1)
        self.assertEqual(len(clotures_m), 1)
        j_de_la_derniere_soiree = clotures_j[0]
        mois_d_avril = clotures_m[0]
        self.assertEqual(mois_d_avril.datetime_debut, heure_de_paris(2026, 4, 1, 0, 0))
        self.assertLess(
            j_de_la_derniere_soiree.numero_sequentiel, mois_d_avril.numero_sequentiel
        )
        # Les perpétuels de la M sont ceux de la J de la soirée du 30 : 350, 1 vente.
        # / The M's perpetual totals are the J's: 350, 1 sale.
        self.assertEqual(j_de_la_derniere_soiree.total_perpetuel, 350)
        self.assertEqual(
            mois_d_avril.total_perpetuel, j_de_la_derniere_soiree.total_perpetuel
        )
        self.assertEqual(
            mois_d_avril.nombre_ventes_perpetuel,
            j_de_la_derniere_soiree.nombre_ventes_perpetuel,
        )

    def test_m_demandee_avant_le_filet_du_jour_ou_elle_finit_n_est_pas_creee(self):
        """
        La commande demande la M d'avril le 1ᵉʳ mai à 0 h 30 : rien n'est créé (le filet
        du 1ᵉʳ mai, à 4 h, n'est pas passé). Redemandée à 4 h 10 : la M est créée.
        / A requested M is not created before the net of the day it ends.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 4, 30, 22, 0))

        m_demandee_trop_tot = self._cloturer_a(
            heure_de_paris(2026, 5, 1, 0, 30), niveau=ClotureCaisse.NIVEAU_MENSUEL
        )
        m_demandee_apres_le_filet = self._cloturer_a(
            heure_de_paris(2026, 5, 1, 4, 10), niveau=ClotureCaisse.NIVEAU_MENSUEL
        )

        self.assertIsNone(m_demandee_trop_tot)
        self.assertIsNotNone(m_demandee_apres_le_filet)

    def test_tache_arretee_trois_semaines_rattrape_les_trois_h_dans_l_ordre(self):
        """
        Un jus le mercredi 4 mars ; la tâche du lundi 9 mars à 4 h 10 crée la H du 2 au
        8 mars. Puis la tâche s'arrête trois semaines : un jus les mercredis 11, 18 et
        25 mars. Au premier passage, le lundi 30 mars à 4 h 10, les trois H manquées
        sont créées, dans l'ordre chronologique : semaines du 9, du 16 et du 23 mars,
        chacune avec son jus (350).
        / A task stopped for three weeks creates the three missed H at its first run,
        in chronological order.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 4, 12, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 9, 4, 10))
        self.assertEqual(
            len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_HEBDOMADAIRE)), 1
        )

        self._vendre_des_jus_a(heure_de_paris(2026, 3, 11, 12, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 18, 12, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 25, 12, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 30, 4, 10))

        clotures_h = self._clotures_du_niveau(ClotureCaisse.NIVEAU_HEBDOMADAIRE)
        self.assertEqual(len(clotures_h), 4)
        h_rattrapees = clotures_h[1:]
        debuts_des_h_rattrapees = []
        for semaine in h_rattrapees:
            debuts_des_h_rattrapees.append(semaine.datetime_debut)
            self.assertEqual(semaine.total_general, 350)
        # Les numéros croissants suivent les semaines dans l'ordre du calendrier.
        # / Increasing numbers follow the weeks in calendar order.
        self.assertEqual(
            debuts_des_h_rattrapees,
            [
                heure_de_paris(2026, 3, 9, 0, 0),
                heure_de_paris(2026, 3, 16, 0, 0),
                heure_de_paris(2026, 3, 23, 0, 0),
            ],
        )

    def test_premier_passage_cree_les_h_depuis_la_premiere_vente_du_lieu(self):
        """
        Aucune H encore : un jus les mercredis 4 et 11 mars. La tâche du lundi 16 mars à
        4 h 10 crée les deux semaines depuis la première vente du lieu : du 2 au 8,
        puis du 9 au 15 mars.
        / Without any H yet, the first run creates every week since the first sale.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 4, 12, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 11, 12, 0))

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 16, 4, 10))

        clotures_h = self._clotures_du_niveau(ClotureCaisse.NIVEAU_HEBDOMADAIRE)
        debuts_des_h = []
        for semaine in clotures_h:
            debuts_des_h.append(semaine.datetime_debut)
        self.assertEqual(
            debuts_des_h,
            [heure_de_paris(2026, 3, 2, 0, 0), heure_de_paris(2026, 3, 9, 0, 0)],
        )

    def test_decembre_et_annee_clotures_au_premier_janvier(self):
        """
        Un jus le 15 décembre 2026 à 20 h (Paris). La tâche du 1ᵉʳ janvier 2027 à
        4 h 10 crée la M de décembre [1ᵉʳ décembre, 1ᵉʳ janvier[ et l'A de 2026
        [1ᵉʳ janvier 2026, 1ᵉʳ janvier 2027[, chacune avec ce jus (350).
        / December and the year 2026 are closed on January 1st.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 12, 15, 20, 0))

        self._lancer_la_tache_horaire_a(heure_de_paris(2027, 1, 1, 4, 10))

        clotures_m = self._clotures_du_niveau(ClotureCaisse.NIVEAU_MENSUEL)
        clotures_a = self._clotures_du_niveau(ClotureCaisse.NIVEAU_ANNUEL)
        self.assertEqual(len(clotures_m), 1)
        self.assertEqual(len(clotures_a), 1)
        self.assertEqual(
            (clotures_m[0].datetime_debut, clotures_m[0].datetime_fin),
            (heure_de_paris(2026, 12, 1, 0, 0), heure_de_paris(2027, 1, 1, 0, 0)),
        )
        self.assertEqual(
            (clotures_a[0].datetime_debut, clotures_a[0].datetime_fin),
            (heure_de_paris(2026, 1, 1, 0, 0), heure_de_paris(2027, 1, 1, 0, 0)),
        )
        self.assertEqual(clotures_m[0].total_general, 350)
        self.assertEqual(clotures_a[0].total_general, 350)

    def test_cloture_h_m_a_refusee_dans_une_transaction_ouverte(self):
        """
        Une M demandée dans une transaction déjà ouverte est refusée (RuntimeError) :
        juste avant son calcul, elle prend puis relâche le verrou des ventes dans une
        transaction courte, qui ne serait relâchée qu'à la fin de la transaction
        ouverte.
        / An H / M / A requested inside an open transaction is refused.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 2, 10, 12, 0))

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self._cloturer_a(
                    heure_de_paris(2026, 3, 2, 10, 0),
                    niveau=ClotureCaisse.NIVEAU_MENSUEL,
                )

    # ------------------------------------------------------------------
    # La commande `generer_cloture`
    # / The `generer_cloture` command
    # ------------------------------------------------------------------

    def _lancer_generer_cloture(self, *arguments):
        """
        Lance `generer_cloture` sur le lieu de test. Rend (sortie, erreurs, exception
        levée ou None).
        / Runs the command on the test venue; returns stdout, stderr, raised error.
        """
        sortie = StringIO()
        erreurs = StringIO()
        exception_levee = None
        try:
            call_command(
                "generer_cloture",
                f"--tenant={self.tenant.schema_name}",
                *arguments,
                stdout=sortie,
                stderr=erreurs,
            )
        except CommandError as erreur_de_la_commande:
            exception_levee = erreur_de_la_commande
        return sortie.getvalue(), erreurs.getvalue(), exception_levee

    def test_generer_cloture_refuse_des_bornes_sans_fuseau(self):
        """
        Des bornes ISO sans fuseau (« 2026-02-01T00:00 ») sont ambiguës : refusées. La
        commande finit en erreur et le dit.
        / Bounds without a time zone are refused.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 2, 10, 12, 0))

        _sortie, erreurs, exception_levee = self._lancer_generer_cloture(
            "--niveau=M",
            "--datetime-debut=2026-02-01T00:00",
            "--datetime-fin=2026-03-01T00:00",
        )

        self.assertIsNotNone(exception_levee)
        self.assertIn("fuseau", erreurs)
        self.assertEqual(len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_MENSUEL)), 0)

    def test_generer_cloture_refuse_un_mois_qui_n_est_pas_celui_du_lieu(self):
        """
        Lieu à Paris : le mois de février en UTC (« 2026-02-01T00:00+00:00 » →
        « 2026-03-01T00:00+00:00 ») n'est pas février en heure de Paris (qui commence
        le 31 janvier à 23 h UTC) : refusé.
        / A month that is not the venue's local month is refused.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 2, 10, 12, 0))

        _sortie, erreurs, exception_levee = self._lancer_generer_cloture(
            "--niveau=M",
            "--datetime-debut=2026-02-01T00:00+00:00",
            "--datetime-fin=2026-03-01T00:00+00:00",
        )

        self.assertIsNotNone(exception_levee)
        self.assertIn("heure locale", erreurs)
        self.assertEqual(len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_MENSUEL)), 0)

    def test_generer_cloture_accepte_le_mois_du_lieu(self):
        """
        Février en heure de Paris (« 2026-02-01T00:00+01:00 » →
        « 2026-03-01T00:00+01:00 »), une vente le 10 : la M est créée, sans erreur.
        / The venue's local month is accepted.
        """
        self._vendre_des_jus_a(heure_de_paris(2026, 2, 10, 12, 0))

        _sortie, _erreurs, exception_levee = self._lancer_generer_cloture(
            "--niveau=M",
            "--datetime-debut=2026-02-01T00:00+01:00",
            "--datetime-fin=2026-03-01T00:00+01:00",
        )

        self.assertIsNone(exception_levee)
        clotures_m = self._clotures_du_niveau(ClotureCaisse.NIVEAU_MENSUEL)
        self.assertEqual(len(clotures_m), 1)
        self.assertEqual(clotures_m[0].datetime_debut, heure_de_paris(2026, 2, 1, 0, 0))

    def test_generer_cloture_une_erreur_dans_un_lieu_n_arrete_pas_les_autres(self):
        """
        Tous les lieux : la clôture du lieu de test lève une erreur (simulée), les
        autres lieux sont quand même traités ; la commande finit en erreur. La tâche
        de clôture est remplacée : rien n'est écrit.
        / An error in one venue does not stop the others; the command ends in error.
        """
        schemas_des_lieux = set(
            Client.objects.exclude(schema_name="public").values_list(
                "schema_name", flat=True
            )
        )

        def cloture_en_panne_dans_le_lieu_de_test(schema_name, **arguments):
            if schema_name == self.tenant.schema_name:
                raise RuntimeError("panne simulée")
            return None

        sortie = StringIO()
        erreurs = StringIO()
        with patch(
            "comptabilite.tasks.generer_cloture_pour_tenant",
            side_effect=cloture_en_panne_dans_le_lieu_de_test,
        ) as cloture_simulee:
            with self.assertRaises(CommandError):
                call_command(
                    "generer_cloture", "--niveau=M", stdout=sortie, stderr=erreurs
                )

        schemas_traites = set()
        for appel in cloture_simulee.call_args_list:
            schemas_traites.add(appel.kwargs["schema_name"])
        self.assertEqual(schemas_traites, schemas_des_lieux)
        self.assertIn(self.tenant.schema_name, erreurs.getvalue())

    # ------------------------------------------------------------------
    # 18 — La chaîne des clôtures
    # / 18 — The chain of closures
    # ------------------------------------------------------------------

    def test_cloture_chainee_et_alteration_detectee(self):
        """
        Fiche F §6 test 18. Une J en février, la M de février, une J en mars : une seule
        chaîne, dans l'ordre des numéros, tous niveaux. Saine : aucune anomalie. Puis le
        `rapport_json` de la J n° 1 est modifié par `update()` (une écriture à la main
        dans la base) : une anomalie, sur la clôture n° 1 (empreinte fausse).
        / One chain across levels; altering rapport_json is detected.
        """
        from comptabilite.integrite import verifier_chaine_clotures

        self._vendre_des_jus_a(heure_de_paris(2026, 2, 10, 12, 0))
        premiere_j = self._cloturer_a(heure_de_paris(2026, 2, 10, 20, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 2, 12, 0))
        mois_de_fevrier = self._cloturer_a(
            heure_de_paris(2026, 3, 2, 13, 0), niveau=ClotureCaisse.NIVEAU_MENSUEL
        )
        deuxieme_j = self._cloturer_a(heure_de_paris(2026, 3, 2, 20, 0))

        # L'ordre des numéros : J n° 1, M n° 2, J n° 3.
        # / Numbering order.
        self.assertEqual(
            [
                premiere_j.numero_sequentiel,
                mois_de_fevrier.numero_sequentiel,
                deuxieme_j.numero_sequentiel,
            ],
            [1, 2, 3],
        )
        # Chaque clôture est reliée à la précédente, tous niveaux.
        # / Each closure is linked to the previous one, every level.
        self.assertEqual(premiere_j.previous_hmac, "")
        self.assertEqual(len(premiere_j.hmac_hash), 64)
        self.assertEqual(mois_de_fevrier.previous_hmac, premiere_j.hmac_hash)
        self.assertEqual(deuxieme_j.previous_hmac, mois_de_fevrier.hmac_hash)

        self.assertEqual(verifier_chaine_clotures(self._cle_du_lieu()), [])

        rapport_altere = dict(premiere_j.rapport_json)
        rapport_altere["chiffre_affaires"] = dict(rapport_altere["chiffre_affaires"])
        rapport_altere["chiffre_affaires"]["total_ttc_en_centimes"] = 1
        ClotureCaisse.objects.filter(pk=premiere_j.pk).update(
            rapport_json=rapport_altere
        )

        anomalies = verifier_chaine_clotures(self._cle_du_lieu())
        numeros_des_clotures_en_anomalie = []
        for anomalie in anomalies:
            numeros_des_clotures_en_anomalie.append(anomalie["numero"])
        self.assertEqual(numeros_des_clotures_en_anomalie, [1])
        self.assertIn("Empreinte fausse", anomalies[0]["raison"])

    def test_verify_clotures_detecte_un_maillon_casse_et_une_vente_alteree(self):
        """
        Deux J. L'empreinte de la J n° 1 est écrasée (`update()`) : la J n° 2 n'est plus
        reliée à elle (maillon cassé). Le règlement de la vente n° 1 (dans la plage de la
        J n° 1) passe en CB par `update()`. `verify_clotures --tenant` signale les deux.
        / The audit command reports a broken link and an altered sale.
        """
        vente_numero_1 = self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 10, 0))
        premiere_j = self._cloturer_a(heure_de_paris(2026, 3, 10, 12, 0))
        self._vendre_des_jus_a(heure_de_paris(2026, 3, 10, 13, 0))
        self._cloturer_a(heure_de_paris(2026, 3, 10, 15, 0))

        ClotureCaisse.objects.filter(pk=premiere_j.pk).update(hmac_hash="0" * 64)
        Reglement.objects.filter(vente=vente_numero_1).update(moyen=PaymentMethod.CC)

        sortie_de_la_commande = StringIO()
        call_command(
            "verify_clotures",
            f"--tenant={self.tenant.schema_name}",
            stdout=sortie_de_la_commande,
        )
        texte_de_la_sortie = sortie_de_la_commande.getvalue()

        self.assertIn("Maillon cassé", texte_de_la_sortie)
        self.assertIn("clôture n° 2", texte_de_la_sortie)
        self.assertIn("la vente n° 1", texte_de_la_sortie)
        self.assertNotIn("aucune anomalie", texte_de_la_sortie)
