"""
tests/pytest/test_api_v2_comptabilite.py
L'API comptable de TiBillet : ce qu'un logiciel comptable (Dolibarr, Paheko…) lit
chaque nuit pour ranger les clôtures du lieu dans sa comptabilité.
/ TiBillet's accounting API: what an accounting software reads each night to file the
venue's closures in its books.

LOCALISATION : tests/pytest/test_api_v2_comptabilite.py

RÈGLES MÉTIER TESTÉES (spec TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-06-connecteurs-
comptables/CHANTIER-06-A-api-comptable.md)
- Une clé d'API a le droit « comptabilite » (A1) ; la clé seule suffit (A2). Sans
  en-tête, avec une clé inconnue ou sans le droit : 403.
- `GET /api/v2/closures/` liste SEULEMENT les clôtures J qui ont des ventes, sans la J
  « reprise », dans l'ordre des numéros (A4). Le curseur `after_number` garde les J de
  numéro plus grand (A11) : une J créée en retard par le filet (finie AVANT le passage
  précédent du logiciel) est quand même vue. `after_number` qui n'est pas un entier
  positif : 400.
- `GET /api/v2/closures/<uuid>/entries/` rend les écritures de `ecritures_de_l_export`
  avec les noms des colonnes du FEC, montants en centimes, dates ISO, SANS `ValidDate`
  (A5, A6, A7). Recalculées à chaque appel, avec le plan du moment (A8).
- `GET /api/v2/closures/<uuid>/fec/` rend exactement le fichier du bouton de l'admin.
- Refus (A9) : clôture hors de la liste (H / M / A, J sans vente, J reprise, uuid
  inconnu) → 404 `not_exportable` ; compte manquant → 409 `missing_account` ; écriture
  déséquilibrée → 409 `unbalanced_entry`.
- La J reprise est refusée par la MÊME règle à l'admin et à l'API (A10), avec la même
  phrase.
- `GET /api/v2/accounts/` rend tous les comptes du lieu, actifs ou non, triés par
  numéro ; il charge le plan par défaut si le lieu n'en a aucun. `treasury` marque
  les comptes où l'argent d'une vente arrive (moyens, monnaies, 419100).
/ Business rules tested: key right, J-only list with a number cursor, entries in FEC
column names without ValidDate, FEC identical to the admin button, 404 / 409 refusals,
same go-live rule for admin and API, the venue's accounts.

LE CONTRAT LU PAR CES TESTS
- `ExternalApiKey.comptabilite` : le droit de lire la comptabilité.
- `comptabilite.tasks.refus_du_fec_avant_la_mise_en_service(cloture)` : la phrase du
  refus, ou None.
- `comptabilite.tasks.journees_a_importer(apres_le_numero=None)` : les J à importer.

Schéma dédié (`FastTenantTestCase`) : les tests lisent des clôtures et la chaîne des
ventes (tronc 05 §8).
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
from io import StringIO  # noqa: E402
from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.contrib import messages  # noqa: E402
from django.contrib.messages.storage.fallback import FallbackStorage  # noqa: E402
from django.contrib.sessions.middleware import SessionMiddleware  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.utils import translation  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402
from rest_framework_api_key.models import APIKey  # noqa: E402

import comptabilite.tasks  # noqa: E402
from Administration.admin.site import staff_admin_site  # noqa: E402
from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    CategorieProduct,
    Configuration,
    ExternalApiKey,
    PaymentMethod,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement  # noqa: E402
from comptabilite.admin import ClotureCaisseAdmin  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from comptabilite.ventilation import ecritures_de_l_export  # noqa: E402
from fabriques_panier import identifiant_unique  # noqa: E402
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from laboutik.models import CompteComptable, LaboutikConfiguration, MappingMonnaie  # noqa: E402

FUSEAU_DE_PARIS = ZoneInfo("Europe/Paris")

DOMAINE_DU_LIEU_DE_TEST = "test-api-comptable.tibillet.localhost"

# La phrase du refus du FEC avant la mise en service (fiche R §11.4), avec sa date.
# / The FEC refusal sentence before the go-live, with its date.
MESSAGE_DU_REFUS_AVANT_LA_MISE_EN_SERVICE = (
    "Le FEC commence à la date de mise en service de la comptabilité ({date}). "
    "Pour avant, utilisez les rapports mensuels."
)


def heure_de_paris(annee, mois, jour, heure, minute=0):
    """Un moment en heure de Paris. / A moment in Paris time."""
    return datetime(annee, mois, jour, heure, minute, tzinfo=FUSEAU_DE_PARIS)


def reponse_vide_pour_le_middleware(requete):
    """
    Le middleware de session demande la fonction qui produit la réponse suivante ; le
    test n'en a pas besoin : il n'appelle que `process_request`.
    / The session middleware wants a "next response" function; the test does not.
    """
    return None


class TestApiComptable(FastTenantTestCase):
    """
    L'API comptable : droit de la clé, liste des J, écritures, fichier FEC, refus, plan.
    / The accounting API: key right, J list, entries, FEC file, refusals, chart.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_api_comptable"

    @classmethod
    def get_test_tenant_domain(cls):
        return DOMAINE_DU_LIEU_DE_TEST

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test API comptable"

    def setUp(self):
        """
        Le lieu de test (Paris, fermeture à 2 h, aucun mail de rapport), une entrée à
        3,50 € (type « billet » : le plan par défaut lui donne 706000 sans catégorie de
        caisse), une clé d'API avec le droit « comptabilité » et le client HTTP.
        / The test venue, an entry ticket at 3.50 €, an API key with the accounting
        right, and the HTTP client.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse doit exister en base (tests/PIEGES.md 9.86) : il
        # porte la clé des empreintes.
        # / The register singleton must exist in the database (fingerprint key).
        LaboutikConfiguration.get_solo().save()

        # Toutes les valeurs lues par les clôtures sont écrites ici : le cache de la
        # configuration garde les valeurs du test précédent.
        # / Every value read by the closures is written here (the cache survives).
        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.heure_de_fermeture = time(2, 0)
        configuration.save()

        self.tarif_de_l_entree = creer_tarif_vendu(
            nom="Entree",
            prix_en_euros="3.50",
            taux_tva="20.00",
            categorie_article=Product.BILLET,
        )

        self.cle_comptable = self._creer_une_cle_d_api(droit_comptabilite=True)

        self.client = APIClient()
        self.client.defaults["HTTP_HOST"] = DOMAINE_DU_LIEU_DE_TEST

    # ------------------------------------------------------------------
    # Outils du test
    # / Test helpers
    # ------------------------------------------------------------------

    def _creer_une_cle_d_api(self, droit_comptabilite):
        """
        Une clé d'API du lieu, avec ou sans le droit « comptabilité ». Rend le texte
        de la clé, celui qu'un logiciel met dans l'en-tête `Authorization`.
        / A venue API key, with or without the accounting right; returns the key text.
        """
        nom_de_la_cle = f"compta-{identifiant_unique()}"
        cle_technique, texte_de_la_cle = APIKey.objects.create_key(name=nom_de_la_cle)
        ExternalApiKey.objects.create(
            name=nom_de_la_cle,
            key=cle_technique,
            comptabilite=droit_comptabilite,
        )
        return texte_de_la_cle

    def _lire(self, adresse, cle=None):
        """
        Un GET de l'API avec la clé comptable du test (ou une autre clé).
        / A GET on the API with the test's accounting key (or another key).
        """
        cle_a_utiliser = cle if cle is not None else self.cle_comptable
        return self.client.get(adresse, HTTP_AUTHORIZATION=f"Api-Key {cle_a_utiliser}")

    def _heure_figee(self, moment):
        """
        Remplace l'heure de Django par `moment` pendant le bloc `with`.
        / Replaces Django's clock with `moment` inside the `with` block.
        """
        return patch("django.utils.timezone.now", return_value=moment)

    def _vendre_une_entree_a(self, moment, tarif_vendu=None, prix_en_centimes=350):
        """
        Une vente de caisse encaissée à `moment` : une entrée (ou un autre tarif) en
        espèces, TVA 20 %.
        / A register sale settled at `moment`, paid in cash.
        """
        tarif_a_vendre = tarif_vendu if tarif_vendu is not None else self.tarif_de_l_entree
        with self._heure_figee(moment):
            vente = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": tarif_a_vendre,
                        "quantite": Decimal("1"),
                        "prix_unitaire": prix_en_centimes,
                        "taux_tva": Decimal("20"),
                    },
                ],
                reglements=[{"moyen": PaymentMethod.CASH, "montant": prix_en_centimes}],
            )
        verifier_egalites(vente)
        return vente

    def _cloturer_la_journee_a(self, moment):
        """
        Le « Z de fin de service » à `moment` : la J glissante du lieu.
        / The end-of-service Z at `moment`.
        """
        with self._heure_figee(moment):
            uuid_de_la_cloture = comptabilite.tasks.generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            )
        return ClotureCaisse.objects.get(uuid=uuid_de_la_cloture)

    def _cloturer_le_mois_precedent_a(self, moment):
        """
        La clôture M du mois qui précède `moment`, en heure locale du lieu.
        / The M closure of the month before `moment`.
        """
        with self._heure_figee(moment):
            uuid_de_la_cloture = comptabilite.tasks.generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_MENSUEL,
            )
        return ClotureCaisse.objects.get(uuid=uuid_de_la_cloture)

    def _lancer_la_tache_horaire_a(self, moment):
        """
        La tâche horaire du lieu (filet J, puis H, M, A) à `moment`.
        / The venue's hourly task at `moment`.
        """
        with self._heure_figee(moment):
            comptabilite.tasks.generer_les_clotures_automatiques_du_lieu(
                self.tenant.schema_name
            )

    def _creer_la_j_de_reprise_a(self, moment):
        """
        La commande de la J « reprise » sur le lieu du test, à `moment`. Rend la J.
        / Runs the "reprise" J command at `moment`; returns the J.
        """
        with self._heure_figee(moment):
            call_command(
                "creer_la_cloture_de_reprise",
                "--schema",
                self.tenant.schema_name,
                stdout=StringIO(),
                stderr=StringIO(),
            )
        return ClotureCaisse.objects.get(
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            rapport_json__en_tete__reprise=True,
        )

    def _numeros_de_la_liste(self, adresse="/api/v2/closures/"):
        """
        Les numéros des clôtures rendues par la liste, dans l'ordre de la réponse.
        / The numbers of the closures returned by the list, in response order.
        """
        reponse = self._lire(adresse)
        assert reponse.status_code == 200, reponse.content
        numeros = []
        for element in reponse.json()["results"]:
            numeros.append(element["number"])
        return numeros

    def _exporter_le_fec_par_l_admin(self, cloture):
        """
        Le bouton « FEC » de la fiche d'une clôture, appelé comme l'admin l'appelle,
        en français. Rend la réponse et la liste des messages (niveau, texte).
        / The admin "FEC" button, called like the admin does.
        """
        email_de_l_administrateur = f"admin-{identifiant_unique()}@tibillet.localhost"
        administrateur = TibilletUser.objects.create(
            email=email_de_l_administrateur,
            username=email_de_l_administrateur,
            is_staff=True,
            is_superuser=True,
        )
        requete = RequestFactory().get(
            f"/admin/comptabilite/cloturecaisse/{cloture.uuid}/exporter-fec/"
        )
        requete.user = administrateur
        SessionMiddleware(reponse_vide_pour_le_middleware).process_request(requete)
        requete._messages = FallbackStorage(requete)
        admin_des_clotures = ClotureCaisseAdmin(ClotureCaisse, staff_admin_site)

        with translation.override("fr"):
            reponse = admin_des_clotures.exporter_fec(requete, cloture.uuid)
            messages_affiches = []
            for message in requete._messages:
                messages_affiches.append((message.level, str(message)))
        return reponse, messages_affiches

    def _une_j_avec_une_entree(self):
        """
        Une entrée vendue le 10 mars 2026 à 20 h, puis la J à 23 h.
        / One entry sold on 10 March 2026 at 8 pm, then the J at 11 pm.
        """
        self._vendre_une_entree_a(heure_de_paris(2026, 3, 10, 20, 0))
        return self._cloturer_la_journee_a(heure_de_paris(2026, 3, 10, 23, 0))

    # ------------------------------------------------------------------
    # 1-2. Le droit de la clé / The key right
    # ------------------------------------------------------------------

    def test_sans_cle_ou_sans_droit_comptabilite_refuse(self):
        """
        Sans en-tête `Authorization`, ou avec une clé du lieu SANS le droit
        « comptabilité » : 403 sur la liste et sur le plan. Avec le droit : 200.
        / No header, or a key without the accounting right: 403. With it: 200.
        """
        cle_sans_le_droit = self._creer_une_cle_d_api(droit_comptabilite=False)

        # Les routes d'une clôture refusent aussi, AVANT de chercher la clôture : un
        # uuid quelconque suffit (relecture de sécurité, M-13).
        # / A closure's routes refuse too, before looking up the closure.
        un_uuid_quelconque = uuid.uuid4()
        for route in ["entries", "fec"]:
            adresse = f"/api/v2/closures/{un_uuid_quelconque}/{route}/"
            assert self.client.get(adresse).status_code == 403
            assert self._lire(adresse, cle=cle_sans_le_droit).status_code == 403

        for adresse in ["/api/v2/closures/", "/api/v2/accounts/"]:
            reponse_sans_en_tete = self.client.get(adresse)
            assert reponse_sans_en_tete.status_code == 403

            reponse_sans_le_droit = self._lire(adresse, cle=cle_sans_le_droit)
            assert reponse_sans_le_droit.status_code == 403

            reponse_avec_le_droit = self._lire(adresse)
            assert reponse_avec_le_droit.status_code == 200

    def test_cle_inconnue_ou_d_un_autre_lieu_refusee(self):
        """
        Une clé bien formée mais absente du schéma du lieu (c'est le cas de la clé
        d'un autre lieu : les clés vivent dans le schéma de leur lieu) : 403.
        / A well-formed key missing from the venue's schema (like another venue's
        key): 403.
        """
        cle_technique, texte_de_la_cle = APIKey.objects.create_key(
            name=f"autre-{identifiant_unique()}"
        )
        cle_technique.delete()

        reponse = self._lire("/api/v2/closures/", cle=texte_de_la_cle)

        assert reponse.status_code == 403

    # ------------------------------------------------------------------
    # 3-6. La liste des clôtures à importer / The list of closures to import
    # ------------------------------------------------------------------

    def test_liste_ne_donne_que_les_j_avec_ventes_dans_l_ordre(self):
        """
        Deux J avec ventes (27 février, 2 mars), la M de février, et une J sans vente
        écrite à la main : la liste ne rend que les deux J, dans l'ordre des numéros.
        La M, la J sans vente et un uuid inconnu : 404 `not_exportable` sur `entries`
        et sur `fec`.
        / Two J with sales, the February M and a J without sales: only the two J, by
        number. The others: 404 not_exportable.
        """
        self._vendre_une_entree_a(heure_de_paris(2026, 2, 27, 20, 0))
        j_du_27_fevrier = self._cloturer_la_journee_a(heure_de_paris(2026, 2, 27, 23, 0))
        self._vendre_une_entree_a(heure_de_paris(2026, 3, 2, 20, 0))
        j_du_2_mars = self._cloturer_la_journee_a(heure_de_paris(2026, 3, 2, 23, 0))
        mois_de_fevrier = self._cloturer_le_mois_precedent_a(
            heure_de_paris(2026, 3, 10, 12, 0)
        )
        j_sans_vente = ClotureCaisse.objects.create(
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            numero_sequentiel=990001,
            datetime_debut=heure_de_paris(2026, 3, 10, 18, 0),
            datetime_fin=heure_de_paris(2026, 3, 10, 23, 0),
            rapport_json={"en_tete": {"fuseau_horaire": "Europe/Paris"}},
        )

        assert self._numeros_de_la_liste() == [
            j_du_27_fevrier.numero_sequentiel,
            j_du_2_mars.numero_sequentiel,
        ]

        uuids_hors_de_la_liste = [
            mois_de_fevrier.uuid,
            j_sans_vente.uuid,
            uuid.uuid4(),
        ]
        for uuid_hors_de_la_liste in uuids_hors_de_la_liste:
            for route in ["entries", "fec"]:
                reponse = self._lire(
                    f"/api/v2/closures/{uuid_hors_de_la_liste}/{route}/"
                )
                assert reponse.status_code == 404, (uuid_hors_de_la_liste, route)
                assert reponse.json()["code"] == "not_exportable"

    def test_liste_sans_la_j_reprise(self):
        """
        Un lieu repris : la J « reprise » (tout l'historique) n'est pas dans la liste ;
        la J ordinaire qui la suit y est.
        / A venue taken over: the "reprise" J is not listed; the next ordinary J is.
        """
        self._vendre_une_entree_a(heure_de_paris(2026, 3, 1, 20, 0))
        j_de_reprise = self._creer_la_j_de_reprise_a(heure_de_paris(2026, 3, 2, 10, 0))
        self._vendre_une_entree_a(heure_de_paris(2026, 3, 2, 20, 0))
        j_ordinaire = self._cloturer_la_journee_a(heure_de_paris(2026, 3, 2, 23, 0))

        numeros = self._numeros_de_la_liste()

        assert numeros == [j_ordinaire.numero_sequentiel]
        assert j_de_reprise.numero_sequentiel not in numeros

    def test_after_number_ne_rend_que_les_suivantes_et_refuse_un_texte(self):
        """
        Trois J. `after_number` = n° de la première : les deux suivantes. Le numéro de
        la dernière : liste vide. Un texte ou un nombre négatif : 400.
        / Three J; after_number keeps the following ones; text or negative: 400.
        """
        journees = []
        for jour in [3, 4, 5]:
            self._vendre_une_entree_a(heure_de_paris(2026, 3, jour, 20, 0))
            journees.append(self._cloturer_la_journee_a(heure_de_paris(2026, 3, jour, 23, 0)))
        premiere, deuxieme, troisieme = journees

        assert self._numeros_de_la_liste(
            f"/api/v2/closures/?after_number={premiere.numero_sequentiel}"
        ) == [deuxieme.numero_sequentiel, troisieme.numero_sequentiel]
        assert self._numeros_de_la_liste(
            f"/api/v2/closures/?after_number={troisieme.numero_sequentiel}"
        ) == []

        # « 1 » suivi de 18 zéros : 19 chiffres, refusé (au-delà de 4300 chiffres,
        # int() lèverait une erreur 500 ; relecture de sécurité, M-9).
        # / 19 digits refused (security review, M-9).
        for valeur_refusee in ["douze", "-1", "1.5", "1" + "0" * 18]:
            reponse = self._lire(f"/api/v2/closures/?after_number={valeur_refusee}")
            assert reponse.status_code == 400, valeur_refusee

    def test_j_creee_en_retard_est_vue_avec_after_number(self):
        """
        Le piège d'un curseur par date (relecture Fable, I-2) : le logiciel passe le
        11 mars à 6 h et ne voit que la J du 10. Le filet de la nuit tourne en retard
        (6 h 30) et crée une J qui finit à 4 h, AVANT ce passage. Avec `after_number`
        = n° de la J du 10, la liste suivante la rend quand même.
        / A late J (ending before the previous pass) is still returned by the number
        cursor.
        """
        self._vendre_une_entree_a(heure_de_paris(2026, 3, 9, 20, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 10, 5, 0))
        j_du_9_mars = ClotureCaisse.derniere_journaliere()
        self._vendre_une_entree_a(heure_de_paris(2026, 3, 10, 20, 0))

        moment_du_passage_du_logiciel = heure_de_paris(2026, 3, 11, 6, 0)
        assert self._numeros_de_la_liste() == [j_du_9_mars.numero_sequentiel]

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 6, 30))
        j_creee_en_retard = ClotureCaisse.derniere_journaliere()
        assert j_creee_en_retard.numero_sequentiel != j_du_9_mars.numero_sequentiel
        assert j_creee_en_retard.datetime_fin < moment_du_passage_du_logiciel

        assert self._numeros_de_la_liste(
            f"/api/v2/closures/?after_number={j_du_9_mars.numero_sequentiel}"
        ) == [j_creee_en_retard.numero_sequentiel]

    # ------------------------------------------------------------------
    # 7-9. Les écritures et le fichier / Entries and file
    # ------------------------------------------------------------------

    def test_entries_egales_a_ecritures_de_l_export(self):
        """
        Une entrée à 3,50 € en espèces : une écriture CAISSE, débit 530000 350,
        crédit 706000 292 et 445711 58. Le JSON reprend `ecritures_de_l_export` avec
        les noms du FEC, en centimes, dates ISO. La liste donne la même date
        comptable et les adresses des deux routes.
        / One entry in cash: one CAISSE entry; the JSON mirrors ecritures_de_l_export.
        """
        cloture = self._une_j_avec_une_entree()

        reponse = self._lire(f"/api/v2/closures/{cloture.uuid}/entries/")

        assert reponse.status_code == 200, reponse.content
        donnees = reponse.json()
        assert donnees["closure"] == str(cloture.uuid)
        assert donnees["number"] == cloture.numero_sequentiel
        assert donnees["accountingDate"] == "2026-03-10"
        assert donnees["currency"] == "EUR"
        assert donnees["amountUnit"] == "cent"

        ecritures_attendues = []
        for ecriture in ecritures_de_l_export(cloture)["ecritures"]:
            lignes_attendues = []
            for ligne in ecriture["lignes"]:
                lignes_attendues.append(
                    {
                        "CompteNum": ligne["compte"],
                        "CompteLib": ligne["libelle"],
                        "Debit": ligne["debit"],
                        "Credit": ligne["credit"],
                    }
                )
            ecritures_attendues.append(
                {
                    "JournalCode": ecriture["journal"],
                    "JournalLib": ecriture["libelle_du_journal"],
                    "EcritureNum": ecriture["numero_d_ecriture"],
                    "EcritureDate": ecriture["date"].isoformat(),
                    "PieceRef": ecriture["piece"],
                    "PieceDate": ecriture["date"].isoformat(),
                    "EcritureLib": ecriture["libelle"],
                    "lines": lignes_attendues,
                }
            )
        assert donnees["entries"] == ecritures_attendues

        # Les valeurs, écrites en clair (pas seulement « égal à la fonction »).
        # / The values, written plainly.
        assert len(donnees["entries"]) == 1
        ecriture_de_la_caisse = donnees["entries"][0]
        assert ecriture_de_la_caisse["JournalCode"] == "CAISSE"
        assert ecriture_de_la_caisse["EcritureNum"] == f"{cloture.numero_sequentiel}-CAISSE"
        assert ecriture_de_la_caisse["PieceRef"] == str(cloture.numero_sequentiel)
        montants_par_compte = {}
        for ligne in ecriture_de_la_caisse["lines"]:
            montants_par_compte[ligne["CompteNum"]] = (ligne["Debit"], ligne["Credit"])
        assert montants_par_compte == {
            "530000": (350, 0),
            "706000": (0, 292),
            "445711": (0, 58),
        }

        reponse_de_la_liste = self._lire("/api/v2/closures/")
        element = reponse_de_la_liste.json()["results"][0]
        assert element["uuid"] == str(cloture.uuid)
        assert element["accountingDate"] == "2026-03-10"
        assert element["startDate"].endswith("+01:00")
        assert element["endDate"] == "2026-03-10T23:00:00+01:00"
        assert element["entries"].endswith(f"/api/v2/closures/{cloture.uuid}/entries/")
        assert element["fec"].endswith(f"/api/v2/closures/{cloture.uuid}/fec/")

    def test_entries_sans_valid_date_et_equilibrees(self):
        """
        Le JSON n'a nulle part de `ValidDate` (import non verrouillé, A7) ; chaque
        écriture est équilibrée ; les montants sont des entiers.
        / No ValidDate anywhere; every entry balanced; whole-number amounts.
        """
        cloture = self._une_j_avec_une_entree()

        reponse = self._lire(f"/api/v2/closures/{cloture.uuid}/entries/")

        assert "ValidDate" not in reponse.content.decode("utf-8")
        for ecriture in reponse.json()["entries"]:
            total_des_debits = 0
            total_des_credits = 0
            for ligne in ecriture["lines"]:
                assert isinstance(ligne["Debit"], int)
                assert isinstance(ligne["Credit"], int)
                total_des_debits += ligne["Debit"]
                total_des_credits += ligne["Credit"]
            assert total_des_debits == total_des_credits

    def test_fec_identique_au_bouton_de_l_admin(self):
        """
        La route `fec` rend, octet pour octet, le fichier du bouton « FEC » de
        l'admin, avec le même nom de fichier.
        / The fec route returns the admin button's file, byte for byte, same name.
        """
        cloture = self._une_j_avec_une_entree()

        reponse_de_l_api = self._lire(f"/api/v2/closures/{cloture.uuid}/fec/")
        reponse_de_l_admin, _messages = self._exporter_le_fec_par_l_admin(cloture)

        assert reponse_de_l_api.status_code == 200
        assert reponse_de_l_api.content == reponse_de_l_admin.content
        assert (
            reponse_de_l_api["Content-Disposition"]
            == reponse_de_l_admin["Content-Disposition"]
        )
        assert reponse_de_l_api["Content-Type"].startswith("text/plain")
        assert f"FEC-20260310-{cloture.numero_sequentiel}.txt" in (
            reponse_de_l_api["Content-Disposition"]
        )

        # Un logiciel qui demande du texte (Accept: text/plain) reçoit le même fichier,
        # pas un 406 (relecture de sécurité, M-14).
        # / A client asking for text gets the same file, not a 406.
        reponse_en_texte = self.client.get(
            f"/api/v2/closures/{cloture.uuid}/fec/",
            HTTP_AUTHORIZATION=f"Api-Key {self.cle_comptable}",
            HTTP_ACCEPT="text/plain",
        )
        assert reponse_en_texte.status_code == 200
        assert reponse_en_texte.content == reponse_de_l_admin.content

    # ------------------------------------------------------------------
    # 10-11. Les refus de calcul / Computation refusals
    # ------------------------------------------------------------------

    def test_compte_manquant_409_missing_account(self):
        """
        Une planche (mode de caisse « vente ») sans catégorie de caisse n'a pas de
        compte : `entries` et `fec` répondent 409 `missing_account`, avec la phrase de
        l'exception (elle nomme la J).
        / A product without account: 409 missing_account on entries and fec.
        """
        tarif_de_la_planche = creer_tarif_vendu(
            nom="Planche sans categorie",
            prix_en_euros="8.00",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
            avec_compte=False,
        )
        self._vendre_une_entree_a(
            heure_de_paris(2026, 3, 10, 20, 0),
            tarif_vendu=tarif_de_la_planche,
            prix_en_centimes=800,
        )
        cloture = self._cloturer_la_journee_a(heure_de_paris(2026, 3, 10, 23, 0))

        for route in ["entries", "fec"]:
            reponse = self._lire(f"/api/v2/closures/{cloture.uuid}/{route}/")
            assert reponse.status_code == 409, route
            assert reponse.json()["code"] == "missing_account"
            assert f"n° {cloture.numero_sequentiel}" in reponse.json()["detail"]

    def test_ecriture_desequilibree_409_unbalanced_entry(self):
        """
        Une donnée altérée après la J (le règlement passe de 3,50 € à 4,00 € par
        `update()`) : `entries` et `fec` répondent 409 `unbalanced_entry`.
        / Data altered after the J: 409 unbalanced_entry on entries and fec.
        """
        vente = self._vendre_une_entree_a(heure_de_paris(2026, 3, 10, 20, 0))
        cloture = self._cloturer_la_journee_a(heure_de_paris(2026, 3, 10, 23, 0))
        Reglement.objects.filter(vente=vente).update(montant=400)

        for route in ["entries", "fec"]:
            reponse = self._lire(f"/api/v2/closures/{cloture.uuid}/{route}/")
            assert reponse.status_code == 409, route
            assert reponse.json()["code"] == "unbalanced_entry"

    # ------------------------------------------------------------------
    # 12. Même règle de mise en service pour l'admin et l'API
    # / Same go-live rule for admin and API
    # ------------------------------------------------------------------

    def test_refus_de_la_j_reprise_meme_regle_pour_admin_et_api(self):
        """
        La J « reprise » : la fonction partagée rend la phrase de la fiche R §11.4
        (avec la date de mise en service en heure du lieu) ; l'admin l'affiche et ne
        télécharge rien ; l'API répond 404 `not_exportable` avec la même phrase. Une J
        ordinaire n'a pas de refus.
        / The "reprise" J: same sentence from the shared function, the admin and the
        API. An ordinary J has no refusal.
        """
        self._vendre_une_entree_a(heure_de_paris(2026, 3, 1, 20, 0))
        j_de_reprise = self._creer_la_j_de_reprise_a(heure_de_paris(2026, 3, 2, 10, 0))
        self._vendre_une_entree_a(heure_de_paris(2026, 3, 2, 20, 0))
        j_ordinaire = self._cloturer_la_journee_a(heure_de_paris(2026, 3, 2, 23, 0))
        phrase_attendue = MESSAGE_DU_REFUS_AVANT_LA_MISE_EN_SERVICE.format(
            date="02/03/2026"
        )

        with translation.override("fr"):
            phrase_de_la_fonction = comptabilite.tasks.refus_du_fec_avant_la_mise_en_service(
                j_de_reprise
            )
            refus_de_la_j_ordinaire = (
                comptabilite.tasks.refus_du_fec_avant_la_mise_en_service(j_ordinaire)
            )
        assert phrase_de_la_fonction == phrase_attendue
        assert refus_de_la_j_ordinaire is None

        reponse_de_l_admin, messages_affiches = self._exporter_le_fec_par_l_admin(
            j_de_reprise
        )
        assert "Content-Disposition" not in reponse_de_l_admin
        messages_d_erreur = []
        for niveau, texte in messages_affiches:
            if niveau == messages.ERROR:
                messages_d_erreur.append(texte)
        assert messages_d_erreur == [phrase_attendue]

        for route in ["entries", "fec"]:
            with translation.override("fr"):
                reponse = self._lire(f"/api/v2/closures/{j_de_reprise.uuid}/{route}/")
            assert reponse.status_code == 404, route
            assert reponse.json()["code"] == "not_exportable"
            assert reponse.json()["detail"] == phrase_attendue

    # ------------------------------------------------------------------
    # 13-14. Le plan comptable du lieu / The venue's chart of accounts
    # ------------------------------------------------------------------

    def test_accounts_tous_les_comptes_y_compris_inactifs(self):
        """
        Tous les comptes du lieu, triés par numéro, avec leur libellé ; un compte
        inactif (707900) est rendu avec `active` à faux.
        / Every account, sorted by number; an inactive one has active = false.
        """
        CompteComptable.objects.filter(numero_de_compte="707900").update(est_actif=False)

        reponse = self._lire("/api/v2/accounts/")

        assert reponse.status_code == 200
        comptes_rendus = reponse.json()["results"]
        numeros_rendus = []
        for compte in comptes_rendus:
            numeros_rendus.append(compte["accountNumber"])
        numeros_en_base = sorted(
            CompteComptable.objects.values_list("numero_de_compte", flat=True)
        )
        assert numeros_rendus == numeros_en_base

        compte_des_jetons = None
        for compte in comptes_rendus:
            if compte["accountNumber"] == "707900":
                compte_des_jetons = compte
        assert compte_des_jetons == {
            "accountNumber": "707900",
            "name": CompteComptable.objects.get(
                numero_de_compte="707900"
            ).libelle_du_compte,
            "active": False,
            "treasury": False,
        }

    def test_accounts_marque_les_comptes_de_tresorerie(self):
        """
        `treasury` est vrai pour les comptes où l'argent d'une vente arrive : celui
        d'un moyen de paiement (530000 pour les espèces), celui d'une monnaie, et le
        419100 des recharges. Faux pour un compte de vente.
        / `treasury` is true for payment method, currency and top-up accounts; false
        for a sales account.
        """
        compte_de_la_monnaie, _ = CompteComptable.objects.get_or_create(
            numero_de_compte="467900",
            defaults={
                "libelle_du_compte": "Monnaie de test",
                "nature_du_compte": CompteComptable.TRESORERIE,
            },
        )
        MappingMonnaie.objects.create(
            asset_uuid=uuid.uuid4(), compte_de_tresorerie=compte_de_la_monnaie
        )

        reponse = self._lire("/api/v2/accounts/")

        assert reponse.status_code == 200
        tresorerie_par_numero = {}
        for compte in reponse.json()["results"]:
            tresorerie_par_numero[compte["accountNumber"]] = compte["treasury"]
        assert tresorerie_par_numero["530000"] is True
        assert tresorerie_par_numero["467900"] is True
        assert tresorerie_par_numero["419100"] is True
        assert tresorerie_par_numero["706000"] is False
        assert tresorerie_par_numero["707900"] is False

    def test_accounts_charge_le_plan_si_le_lieu_n_en_a_aucun(self):
        """
        Un lieu sans aucun compte : la route charge le plan par défaut (le filet) et le
        rend.
        / A venue without any account: the route loads the default chart and returns
        it.
        """
        MappingMonnaie.objects.all().delete()
        CompteComptable.objects.all().delete()
        assert CompteComptable.objects.count() == 0

        reponse = self._lire("/api/v2/accounts/")

        assert reponse.status_code == 200
        numeros_rendus = []
        for compte in reponse.json()["results"]:
            numeros_rendus.append(compte["accountNumber"])
        assert "707900" in numeros_rendus
        assert len(numeros_rendus) == CompteComptable.objects.count()
        assert CompteComptable.objects.count() > 0

    def test_entries_suivent_le_plan_du_moment(self):
        """
        Les écritures sont recalculées à chaque appel (A8) : après la J, l'entrée est
        rangée dans une catégorie de caisse reliée au 707000 ; l'appel suivant écrit
        707000 au lieu de 706000.
        / Entries are recomputed at each call with the current chart.
        """
        cloture = self._une_j_avec_une_entree()

        def comptes_de_l_ecriture():
            reponse = self._lire(f"/api/v2/closures/{cloture.uuid}/entries/")
            comptes = []
            for ligne in reponse.json()["entries"][0]["lines"]:
                comptes.append(ligne["CompteNum"])
            return comptes

        assert "706000" in comptes_de_l_ecriture()

        categorie_des_entrees = CategorieProduct.objects.create(
            name=f"Entrees {identifiant_unique()}",
            compte_comptable=CompteComptable.objects.get(numero_de_compte="707000"),
        )
        produit_de_l_entree = self.tarif_de_l_entree.productsold.product
        produit_de_l_entree.categorie_pos = categorie_des_entrees
        produit_de_l_entree.save()

        comptes_apres_le_changement = comptes_de_l_ecriture()
        assert "707000" in comptes_apres_le_changement
        assert "706000" not in comptes_apres_le_changement
