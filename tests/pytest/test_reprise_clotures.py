"""
tests/pytest/test_reprise_clotures.py
Les clôtures d'un lieu repris : la J « reprise » qui couvre tout l'historique, le
rattrapage plafonné des semaines, mois et années, les mails, le FEC refusé avant la mise
en service, et l'admin d'un règlement « reprise ».
/ Closures of a venue taken over: the "reprise" J covering the whole history, the capped
catch-up of weeks, months and years, the e-mails, the FEC refused before the go-live,
and the admin of a "reprise" payment.

LOCALISATION : tests/pytest/test_reprise_clotures.py

RÈGLES MÉTIER TESTÉES (fiche R §11 ; décisions Q-R2, Q-R3, Q-R13, QO-2, QO-4 ; décisions
de l'orchestrateur de 05-R-3, SUIVI §4)
- La MISE EN SERVICE de la comptabilité d'un lieu est la fin (`datetime_fin`) de sa J
  « reprise ». Un lieu sans J reprise n'a pas de mise en service à respecter.
- La J « reprise » est créée par une commande, une fois par lieu. Elle couvre tout
  l'historique : de la première vente réglée du lieu jusqu'à l'heure de la commande.
  Elle porte le total perpétuel de tout l'historique, comme une J normale.
- Elle est marquée `"reprise": true` dans `rapport_json["en_tete"]` AVANT le
  scellement : le `rapport_json` est dans l'empreinte de la clôture, la chaîne des
  clôtures reste donc valide.
- Elle n'envoie aucun mail. Un lieu sans vente réglée n'a pas de J reprise. Rejouée, la
  commande ne crée rien : le lieu a déjà sa J reprise. Un lieu qui a déjà une J
  ordinaire (sans J reprise) est refusé, avec un message clair : la J partirait de la
  fin de cette J et ne couvrirait pas tout l'historique. La commande passe alors au lieu
  suivant, sans s'arrêter en erreur.
- Le rattrapage des semaines, mois et années (tâche horaire) crée au plus 12 clôtures
  H / M / A par lieu et par passage (QO-4). Les suivantes viennent aux passages d'après.
- Aucun mail pour une clôture dont la fin est avant OU ÉGALE à la mise en service : la
  période est tout entière dans l'historique. Une clôture finie après envoie son mail,
  comme aujourd'hui.
- Le FEC est refusé pour la J reprise, et pour toute H / M / A qui commence avant la
  mise en service. Message (fiche R §11.4) : « Le FEC commence à la date de mise en
  service de la comptabilité (jj/mm/aaaa). Pour avant, utilisez les rapports
  mensuels. » La date est celle de la mise en service, en heure du lieu. Une période
  qui commence exactement à la mise en service n'est pas « avant » : son FEC est
  accepté. La balance du plan comptable n'est pas refusée (QO-2).
- Un règlement de référence externe « reprise » n'a aucun lien vers Stripe dans
  l'admin, même s'il est relié à un paiement Stripe : l'écran affiche « reprise ».
- Après la bascule, la première J automatique (le filet) commence à la fin de la J
  reprise.
/ Business rules tested: go-live = end of the "reprise" J; one "reprise" J per venue,
whole history, perpetual totals, marked before sealing, no e-mail, replay-safe; catch-up
capped at 12 H / M / A per run; no e-mail before go-live; FEC refused before go-live;
no Stripe link for a "reprise" payment; the first automatic J starts at its end.

LE CONTRAT LU PAR CES TESTS
- La commande `creer_la_cloture_de_reprise --schema <schéma du lieu>` : crée la J
  reprise du lieu, maintenant (heure de la commande). Sans `--schema` : tous les lieux.
- `rapport_json["en_tete"]["reprise"]` vaut `True` sur la J reprise ; une autre clôture
  n'a pas cette marque à vrai.
- `comptabilite.tasks.generer_les_clotures_automatiques_du_lieu(schema_name)` : la
  sous-tâche horaire du lieu (le filet J, puis les H, M, A finies qui manquent).
- `comptabilite.tasks.generer_cloture_pour_tenant(schema_name, niveau)` : le « Z de fin
  de service » (J demandée).
- `comptabilite.admin.ClotureCaisseAdmin.exporter_fec(request, object_id)` : un refus
  redirige vers la fiche de la clôture et affiche un message d'erreur ; un FEC accepté
  est un fichier téléchargé (`Content-Disposition: attachment`).
- `comptabilite.balance.balance_de_la_periode(premier_jour, dernier_jour)`.
- `Administration.admin_tenant._adresse_stripe_d_un_reglement(reglement)` et
  `ReglementsDeLaVenteInline.reference_et_lien_stripe(reglement)`.
- Les mails de clôture partent par la tâche Celery `envoyer_email_cloture` : les tests
  interceptent toutes les tâches demandées (`taches_celery_enregistrees`) et le mailer
  (`comptabilite.tasks.CeleryMailerClass`).
/ The contract read by these tests.

D'OÙ VIENNENT LES VALEURS ATTENDUES
Un calcul à la main, écrit en commentaire au-dessus de l'assertion. Une entrée vaut
350 centimes (TVA 20 %). Le nombre de semaines, de mois et d'années à rattraper est
compté à la main sur le calendrier, écrit au-dessus du test.
/ Hand computations, written above each assertion.

L'HEURE
L'heure d'encaissement d'une vente est scellée dans son empreinte : on ne la change
jamais après coup. Chaque vente, chaque commande et chaque passage de la tâche horaire
se fait à une heure choisie, en remplaçant `django.utils.timezone.now` pendant l'appel.
Le lieu est à Paris (CET, UTC+1, en hiver), fermeture à 2 h : le filet passe à 4 h.
La commande de reprise est lancée à 3 h du matin, heure de Paris : la date est la même
en heure de Paris, en UTC et en heure du serveur.
/ Each sale, command and hourly run happens at a chosen time (timezone.now replaced).

SCHÉMA DÉDIÉ
Une clôture lit TOUTES les ventes du lieu : il faut un lieu qui ne contient que les
ventes du test (`FastTenantTestCase`). Chaque test annule sa transaction à la fin. Le
singleton `LaboutikConfiguration` est créé en base (tests/PIEGES.md 9.86) : il porte la
clé des empreintes. La `Configuration` du lieu est réécrite à chaque test : son cache
(django-solo) survit à l'annulation de la transaction. Les ventes sont écrites PAR LE
SERVICE (`fabriques_vente.py`), jamais à la main : une J reprise ne regarde pas comment
une vente a été écrite, seulement qu'elle est réglée.
/ Dedicated schema, rolled back after each test; sales written through the service.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md (§11,
§12 étapes 10 et 11, §13 R-3, §17 QO-2 et QO-4) et le brief
CHANTIER-05-briefs/05-R-3.md.

Lancer / Run : make test ARGS="tests/pytest/test_reprise_clotures.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from datetime import date, datetime, time, timedelta  # noqa: E402
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

import comptabilite.tasks  # noqa: E402
from Administration.admin.site import staff_admin_site  # noqa: E402
from Administration.admin_tenant import (  # noqa: E402
    ReglementsDeLaVenteInline,
    _adresse_stripe_d_un_reglement,
)
from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Configuration,
    Paiement_stripe,
    PaymentMethod,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement, Vente  # noqa: E402
from BaseBillet.services_vente import ouvrir_vente  # noqa: E402
from comptabilite.admin import ClotureCaisseAdmin  # noqa: E402
from comptabilite.balance import balance_de_la_periode  # noqa: E402
from comptabilite.integrite import (  # noqa: E402
    calculer_hmac_cloture,
    verifier_chaine_clotures,
    verifier_continuite_des_journees,
)
from comptabilite.models import ClotureCaisse  # noqa: E402
from fabriques_panier import (  # noqa: E402
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from laboutik.models import LaboutikConfiguration  # noqa: E402

FUSEAU_DE_PARIS = ZoneInfo("Europe/Paris")

# Le message de refus du FEC (fiche R §11.4), avec la date de mise en service.
# / The FEC refusal message (sheet R §11.4), with the go-live date.
MESSAGE_DU_REFUS_DU_FEC = (
    "Le FEC commence à la date de mise en service de la comptabilité ({date}). "
    "Pour avant, utilisez les rapports mensuels."
)

# Le plafond du rattrapage : 12 clôtures H / M / A par lieu et par passage (QO-4).
# / The catch-up cap: 12 H / M / A closures per venue and per run.
PLAFOND_DU_RATTRAPAGE_PAR_PASSAGE = 12

# Le morceau du message de la commande quand le lieu a déjà une J ordinaire.
# / The piece of the command message when the venue already has an ordinary J.
MESSAGE_DU_LIEU_DEJA_CLOTURE = "a déjà une clôture journalière ordinaire"

# Le morceau du message de la commande quand la J reprise du lieu existe déjà.
# / The piece of the command message when the venue's "reprise" J already exists.
MESSAGE_J_REPRISE_DEJA_FAITE = "J reprise déjà faite"

# La référence externe d'un règlement repris (fiche R §7, Q-R6).
# / The external reference of a payment taken over.
REFERENCE_D_UN_REGLEMENT_REPRIS = "reprise"

# Le nom court de la tâche Celery du mail automatique d'une clôture.
# / Short name of the Celery task of a closure's automatic e-mail.
TACHE_DU_MAIL_DE_CLOTURE = "envoyer_email_cloture"

NIVEAUX_CALENDAIRES = [
    ClotureCaisse.NIVEAU_HEBDOMADAIRE,
    ClotureCaisse.NIVEAU_MENSUEL,
    ClotureCaisse.NIVEAU_ANNUEL,
]


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


def mails_de_cloture_demandes(taches_demandees):
    """
    Les tâches de mail de clôture demandées, en (nom, arguments). Le mail « demandé »
    au bouton de la caisse (`envoyer_email_cloture_demande`) en fait partie : aucun mail
    ne doit partir, quel que soit son chemin.
    / The requested closure e-mail tasks, whatever their path.
    """
    mails = []
    for nom_de_la_tache, arguments in taches_demandees:
        if nom_de_la_tache.startswith(TACHE_DU_MAIL_DE_CLOTURE):
            mails.append((nom_de_la_tache, arguments))
    return mails


class TestRepriseClotures(FastTenantTestCase):
    """
    La J reprise, le rattrapage plafonné, les mails, le FEC et l'admin d'un lieu repris.
    / The "reprise" J, the capped catch-up, e-mails, FEC and admin of a venue taken over.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_reprise_clotures"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-reprise-clotures.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test reprise des clotures"

    def setUp(self):
        """
        Le lieu de test : son singleton de caisse, sa configuration (Paris, fermeture à
        2 h, aucun mail de rapport) et une entrée à 3,50 €.
        / The test venue: register singleton, configuration, an entry ticket at 3.50 €.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse doit exister en base (tests/PIEGES.md 9.86) : il
        # porte la clé des empreintes.
        # / The register singleton must exist in the database (fingerprint key).
        LaboutikConfiguration.get_solo().save()

        # Toutes les valeurs lues par les clôtures et les mails sont écrites ici : le
        # cache de la configuration garde les valeurs du test précédent.
        # / Every value read by closures and e-mails is written here (cache survives).
        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.heure_de_fermeture = time(2, 0)
        configuration.rapport_emails = ""
        configuration.rapport_periodicite = Configuration.PERIODICITE_NONE
        configuration.save()

        # Une entrée (type « billet ») : le plan comptable par défaut lui donne son
        # compte de vente (706000) sans catégorie de caisse, le FEC peut donc l'écrire.
        # / An entry ticket: the default chart gives it 706000, so the FEC can write it.
        self.tarif_de_l_entree = creer_tarif_vendu(
            nom="Entree",
            prix_en_euros="3.50",
            taux_tva="20.00",
            categorie_article=Product.BILLET,
        )

    # ------------------------------------------------------------------
    # Outils du test
    # / Test helpers
    # ------------------------------------------------------------------

    def _heure_figee(self, moment):
        """
        Remplace l'heure de Django par `moment` pendant le bloc `with`.
        / Replaces Django's clock with `moment` inside the `with` block.
        """
        return patch("django.utils.timezone.now", return_value=moment)

    def _configurer_les_mails(self, periodicite):
        """
        Donne au lieu un destinataire de rapport et une périodicité : une clôture de ce
        niveau demande alors son mail.
        / Gives the venue a report recipient and a periodicity.
        """
        configuration = Configuration.get_solo()
        configuration.rapport_emails = "compta-reprise@mock.test"
        configuration.rapport_periodicite = periodicite
        configuration.save()

    def _vendre_des_entrees_a(self, moment, quantite=1):
        """
        Une vente de caisse encaissée à `moment` : `quantite` entrées à 3,50 € en
        espèces.
        / A register sale settled at `moment`: `quantite` entries in cash.
        """
        montant_en_centimes = 350 * quantite
        with self._heure_figee(moment):
            vente = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": self.tarif_de_l_entree,
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

    def _creer_la_j_de_reprise_a(self, moment):
        """
        Lance la commande de la J reprise sur le lieu du test, à `moment`. Rend ce
        qu'elle affiche, sortie normale et sortie d'erreur à la suite.
        / Runs the "reprise" J command on the test venue at `moment`; returns stdout
        then stderr.
        """
        sortie_de_la_commande = StringIO()
        erreurs_de_la_commande = StringIO()
        with self._heure_figee(moment):
            call_command(
                "creer_la_cloture_de_reprise",
                "--schema",
                self.tenant.schema_name,
                stdout=sortie_de_la_commande,
                stderr=erreurs_de_la_commande,
            )
        return sortie_de_la_commande.getvalue() + erreurs_de_la_commande.getvalue()

    def _lancer_la_tache_horaire_a(self, moment):
        """
        Lance la tâche horaire du lieu (filet J, puis H, M, A) à `moment`.
        / Runs the venue's hourly task at `moment`.
        """
        with self._heure_figee(moment):
            comptabilite.tasks.generer_les_clotures_automatiques_du_lieu(
                self.tenant.schema_name
            )

    def _clotures_du_niveau(self, niveau):
        """Les clôtures d'un niveau, par numéro. / Closures of a level, by number."""
        return list(
            ClotureCaisse.objects.filter(niveau=niveau).order_by("numero_sequentiel")
        )

    def _nombre_de_clotures_calendaires(self):
        """Le nombre de clôtures H, M et A du lieu. / Number of H, M, A closures."""
        return ClotureCaisse.objects.filter(niveau__in=NIVEAUX_CALENDAIRES).count()

    def _la_cloture_d_une_periode(self, niveau, debut, fin):
        """
        La clôture d'un niveau et de bornes données. Le test échoue si elle n'existe
        pas.
        / The closure of a level and bounds; fails if absent.
        """
        return ClotureCaisse.objects.get(
            niveau=niveau, datetime_debut=debut, datetime_fin=fin
        )

    def _cle_du_lieu(self):
        """La clé des empreintes du lieu. / The venue's fingerprint key."""
        return LaboutikConfiguration.get_solo().get_or_create_hmac_key()

    def _exporter_le_fec_par_l_admin(self, cloture):
        """
        Le bouton « FEC » de la fiche d'une clôture, appelé comme l'admin l'appelle,
        en français. Rend la réponse et la liste des messages (niveau, texte).
        / The admin "FEC" button, called like the admin does. Returns the response and
        the messages.
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

    def _verifier_le_refus_du_fec(self, cloture, date_de_mise_en_service_affichee):
        """
        Le FEC de la clôture est refusé : aucun fichier, retour à la fiche de la
        clôture, et un message d'erreur qui contient le message de la fiche R §11.4
        avec la date de mise en service.
        / The closure's FEC is refused: no file, back to the closure page, error message.
        """
        reponse, messages_affiches = self._exporter_le_fec_par_l_admin(cloture)

        assert reponse.status_code == 302
        assert "Content-Disposition" not in reponse
        message_attendu = MESSAGE_DU_REFUS_DU_FEC.format(
            date=date_de_mise_en_service_affichee
        )
        messages_d_erreur = []
        for niveau_du_message, texte_du_message in messages_affiches:
            if niveau_du_message == messages.ERROR:
                messages_d_erreur.append(texte_du_message)
        assert len(messages_d_erreur) == 1, messages_affiches
        assert message_attendu in messages_d_erreur[0]

    def _verifier_que_le_fec_est_accepte(self, cloture):
        """
        Le FEC de la clôture est un fichier téléchargé, sans message d'erreur, et il
        contient au moins une écriture (une ligne en plus de l'en-tête).
        / The closure's FEC is a downloaded file, with at least one entry line.
        """
        reponse, messages_affiches = self._exporter_le_fec_par_l_admin(cloture)

        assert reponse.status_code == 200, messages_affiches
        assert reponse["Content-Disposition"].startswith("attachment")
        lignes_du_fec = reponse.content.decode("utf-8").split("\r\n")
        lignes_non_vides = []
        for ligne_du_fec in lignes_du_fec:
            if ligne_du_fec != "":
                lignes_non_vides.append(ligne_du_fec)
        assert len(lignes_non_vides) > 1

    # ------------------------------------------------------------------
    # 1. La J reprise couvre tout l'historique et porte le perpétuel
    # / 1. The "reprise" J covers the whole history and carries the perpetual total
    # ------------------------------------------------------------------

    def test_j_reprise_couvre_tout_l_historique_et_porte_le_perpetuel(self):
        """
        Trois ventes d'historique : 1 entrée le 5 novembre 2025, 2 le 14 janvier 2026,
        3 le 9 mars 2026. La commande, lancée le 10 mars 2026 à 3 h, crée UNE clôture :
        une J de la première vente réglée jusqu'à l'heure de la commande, avec les
        trois ventes et le total perpétuel de tout l'historique.
        / The command creates one J from the first settled sale to the command time,
        with the three sales and the whole history's perpetual total.
        """
        premiere_vente = self._vendre_des_entrees_a(heure_de_paris(2025, 11, 5, 12, 0))
        self._vendre_des_entrees_a(heure_de_paris(2026, 1, 14, 12, 0), quantite=2)
        derniere_vente = self._vendre_des_entrees_a(
            heure_de_paris(2026, 3, 9, 20, 0), quantite=3
        )
        moment_de_la_commande = heure_de_paris(2026, 3, 10, 3, 0)

        self._creer_la_j_de_reprise_a(moment_de_la_commande)

        # La commande ne crée que la J : ni semaine, ni mois, ni année.
        # / The command creates the J only.
        j_de_reprise = ClotureCaisse.objects.get()
        assert j_de_reprise.niveau == ClotureCaisse.NIVEAU_JOURNALIER
        assert j_de_reprise.datetime_debut == heure_de_paris(2025, 11, 5, 12, 0)
        assert j_de_reprise.datetime_fin == moment_de_la_commande
        assert j_de_reprise.numero_premiere_vente == premiere_vente.numero
        assert j_de_reprise.numero_derniere_vente == derniere_vente.numero
        assert j_de_reprise.nombre_transactions == 3

        # (1 + 2 + 3) entrées × 350 = 2 100 centimes. Première J du lieu : le perpétuel
        # est son propre total (aucune J avant elle).
        # / (1 + 2 + 3) × 350 = 2 100. First J: the perpetual total is its own total.
        assert j_de_reprise.total_general == 2100
        assert j_de_reprise.total_perpetuel == 2100
        assert j_de_reprise.nombre_ventes_perpetuel == 3
        en_tete = j_de_reprise.rapport_json["en_tete"]
        assert en_tete["total_perpetuel_en_centimes"] == 2100
        assert en_tete["nombre_de_ventes_perpetuel"] == 3

    # ------------------------------------------------------------------
    # 2. La J reprise est marquée avant le scellement
    # / 2. The "reprise" J is marked before sealing
    # ------------------------------------------------------------------

    def test_j_reprise_marquee_dans_l_en_tete_et_empreinte_valide(self):
        """
        La J reprise porte `"reprise": true` dans l'en-tête de son rapport. La marque
        est dans l'empreinte : l'empreinte recalculée sur la clôture relue est celle
        qui est enregistrée, et la chaîne des clôtures n'a aucune anomalie.
        / The "reprise" J is marked in its header; the mark is inside the fingerprint.
        """
        self._vendre_des_entrees_a(heure_de_paris(2026, 1, 14, 12, 0))
        self._creer_la_j_de_reprise_a(heure_de_paris(2026, 3, 10, 3, 0))

        j_de_reprise = ClotureCaisse.objects.get(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
        assert j_de_reprise.rapport_json["en_tete"].get("reprise") is True

        cle_du_lieu = self._cle_du_lieu()
        empreinte_recalculee = calculer_hmac_cloture(
            j_de_reprise, cle_du_lieu, j_de_reprise.previous_hmac
        )
        assert empreinte_recalculee == j_de_reprise.hmac_hash
        assert verifier_chaine_clotures(cle_du_lieu) == []

    # ------------------------------------------------------------------
    # 3. La J reprise n'envoie aucun mail
    # / 3. The "reprise" J sends no e-mail
    # ------------------------------------------------------------------

    def test_j_reprise_n_envoie_aucun_mail(self):
        """
        Le lieu demande le rapport de chaque J par mail. La J reprise n'en demande
        aucun : ni tâche de mail, ni mailer appelé. Avec la même configuration, le Z
        de fin de service suivant demande son mail : la configuration est bien celle
        qui envoie.
        / The venue mails every J. The "reprise" J requests none; the next end-of-service
        Z, with the same configuration, does.
        """
        self._configurer_les_mails(Configuration.PERIODICITE_JOURNALIER)
        self._vendre_des_entrees_a(heure_de_paris(2026, 1, 14, 12, 0))

        with (
            taches_celery_enregistrees() as taches_demandees,
            patch("comptabilite.tasks.CeleryMailerClass") as faux_mailer,
        ):
            self._creer_la_j_de_reprise_a(heure_de_paris(2026, 3, 10, 3, 0))

        assert (
            ClotureCaisse.objects.filter(niveau=ClotureCaisse.NIVEAU_JOURNALIER).count()
            == 1
        )
        assert mails_de_cloture_demandes(taches_demandees) == []
        faux_mailer.assert_not_called()

        # La preuve par la J suivante : une vente le soir, puis le Z de 23 h.
        # / The proof by the next J: a sale in the evening, then the 11 pm Z.
        self._vendre_des_entrees_a(heure_de_paris(2026, 3, 10, 18, 0))
        with taches_celery_enregistrees() as taches_du_z_suivant:
            with self._heure_figee(heure_de_paris(2026, 3, 10, 23, 0)):
                uuid_du_z_suivant = comptabilite.tasks.generer_cloture_pour_tenant(
                    schema_name=self.tenant.schema_name,
                    niveau=ClotureCaisse.NIVEAU_JOURNALIER,
                )
        assert mails_de_cloture_demandes(taches_du_z_suivant) == [
            (TACHE_DU_MAIL_DE_CLOTURE, (self.tenant.schema_name, uuid_du_z_suivant)),
        ]

    # ------------------------------------------------------------------
    # 4. Lieu sans vente : aucune J reprise
    # / 4. Venue without any sale: no "reprise" J
    # ------------------------------------------------------------------

    def test_lieu_sans_vente_aucune_j_reprise(self):
        """
        Le lieu n'a aucune vente réglée : une seule vente ouverte, en attente. La
        commande ne crée aucune clôture, et ne s'arrête pas en erreur.
        / The venue has no settled sale (one pending sale only): no closure is created.
        """
        with self._heure_figee(heure_de_paris(2026, 1, 14, 12, 0)):
            ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE)
        assert Vente.objects.filter(statut=Vente.Statut.REGLEE).count() == 0

        self._creer_la_j_de_reprise_a(heure_de_paris(2026, 3, 10, 3, 0))

        assert ClotureCaisse.objects.count() == 0

    # ------------------------------------------------------------------
    # 5. Le rattrapage H / M / A est plafonné à 12 par passage
    # / 5. The H / M / A catch-up is capped at 12 per run
    # ------------------------------------------------------------------

    def test_rattrapage_plafonne_a_douze_par_passage(self):
        """
        Une entrée chaque mercredi, du 5 novembre 2025 au 18 février 2026 : 16 ventes,
        16 semaines. La J reprise le 10 mars 2026 à 3 h. Ce qui manque, compté sur le
        calendrier :
        - 16 semaines (une par mercredi) ;
        - 4 mois : novembre, décembre, janvier, février (février finit le 1ᵉʳ mars) ;
        - 1 année : 2025 (2026 n'est pas finie).
        Total : 21 clôtures H / M / A. Passage de 4 h 10 : 12 ; de 5 h 10 : les 9
        restantes ; de 6 h 10 : rien. À la fin, tout l'historique est clôturé.
        / 21 missing H / M / A: 12 at the first run, the 9 others at the second, none at
        the third; the whole history is closed in the end.
        """
        premier_mercredi = date(2025, 11, 5)
        for numero_de_la_semaine in range(16):
            jour_de_la_vente = premier_mercredi + timedelta(weeks=numero_de_la_semaine)
            self._vendre_des_entrees_a(
                heure_de_paris(
                    jour_de_la_vente.year,
                    jour_de_la_vente.month,
                    jour_de_la_vente.day,
                    12,
                    0,
                )
            )
        self._creer_la_j_de_reprise_a(heure_de_paris(2026, 3, 10, 3, 0))
        assert self._nombre_de_clotures_calendaires() == 0

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 10, 4, 10))
        assert (
            self._nombre_de_clotures_calendaires() == PLAFOND_DU_RATTRAPAGE_PAR_PASSAGE
        )

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 10, 5, 10))
        assert self._nombre_de_clotures_calendaires() == 21

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 10, 6, 10))
        assert self._nombre_de_clotures_calendaires() == 21

        assert len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_HEBDOMADAIRE)) == 16
        assert len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_MENSUEL)) == 4
        assert len(self._clotures_du_niveau(ClotureCaisse.NIVEAU_ANNUEL)) == 1

    # ------------------------------------------------------------------
    # 6. Aucun mail pour une clôture finie avant la mise en service
    # / 6. No e-mail for a closure finished before the go-live
    # ------------------------------------------------------------------

    def test_aucun_mail_pour_une_cloture_finie_avant_la_mise_en_service(self):
        """
        Le lieu demande le rapport de chaque mois par mail. Historique : une entrée le
        14 janvier et le 11 février 2026 ; J reprise le 1ᵉʳ mars à 0 h pile (la mise en
        service). Le passage du 1ᵉʳ mars à 4 h 10 clôture janvier (fini avant la mise
        en service) et février (fini EXACTEMENT à la mise en service : la période est
        tout entière dans l'historique) : aucun mail. Une entrée le 20 mars, après la
        mise en service ; le passage du 1ᵉʳ avril à 4 h 10 clôture mars, fini après :
        son mail est demandé, et lui seul.
        / Monthly e-mails: January (ended before the go-live) and February (ended exactly
        at it) send none; March, ended after, sends its own.
        """
        self._configurer_les_mails(Configuration.PERIODICITE_MENSUEL)
        self._vendre_des_entrees_a(heure_de_paris(2026, 1, 14, 12, 0))
        self._vendre_des_entrees_a(heure_de_paris(2026, 2, 11, 12, 0))
        self._creer_la_j_de_reprise_a(heure_de_paris(2026, 3, 1, 0, 0))

        with (
            taches_celery_enregistrees() as taches_du_rattrapage,
            patch("comptabilite.tasks.CeleryMailerClass") as faux_mailer,
        ):
            self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 1, 4, 10))

        # Les deux mois de l'historique sont bien clôturés, sans mail. Février finit le
        # 1ᵉʳ mars à 0 h : fin égale à la mise en service, aucun mail non plus.
        # / Both history months are closed, with no e-mail (February ends exactly at
        # the go-live).
        self._la_cloture_d_une_periode(
            ClotureCaisse.NIVEAU_MENSUEL,
            heure_de_paris(2026, 1, 1, 0, 0),
            heure_de_paris(2026, 2, 1, 0, 0),
        )
        self._la_cloture_d_une_periode(
            ClotureCaisse.NIVEAU_MENSUEL,
            heure_de_paris(2026, 2, 1, 0, 0),
            heure_de_paris(2026, 3, 1, 0, 0),
        )
        assert mails_de_cloture_demandes(taches_du_rattrapage) == []
        faux_mailer.assert_not_called()

        # Après la mise en service : le mois de mars finit le 1ᵉʳ avril.
        # / After the go-live: March ends on April 1st.
        self._vendre_des_entrees_a(heure_de_paris(2026, 3, 20, 12, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 21, 4, 10))
        with taches_celery_enregistrees() as taches_du_premier_avril:
            self._lancer_la_tache_horaire_a(heure_de_paris(2026, 4, 1, 4, 10))

        mois_de_mars = self._la_cloture_d_une_periode(
            ClotureCaisse.NIVEAU_MENSUEL,
            heure_de_paris(2026, 3, 1, 0, 0),
            heure_de_paris(2026, 4, 1, 0, 0),
        )
        assert mails_de_cloture_demandes(taches_du_premier_avril) == [
            (
                TACHE_DU_MAIL_DE_CLOTURE,
                (self.tenant.schema_name, str(mois_de_mars.uuid)),
            ),
        ]

    # ------------------------------------------------------------------
    # 7. FEC refusé sur la J reprise
    # / 7. FEC refused on the "reprise" J
    # ------------------------------------------------------------------

    def test_fec_refuse_sur_la_j_reprise_avec_le_message(self):
        """
        Historique : une entrée le 5 novembre 2025 et le 14 janvier 2026 ; J reprise le
        10 mars 2026 à 3 h. Le bouton « FEC » de la J reprise ne télécharge rien : il
        revient à la fiche avec le message « Le FEC commence à la date de mise en
        service de la comptabilité (10/03/2026). Pour avant, utilisez les rapports
        mensuels. » La balance de la période de la J reprise reste calculée (QO-2 :
        balance acceptée).
        / The "reprise" J FEC is refused with the sheet's message; the trial balance of
        its period is still computed.
        """
        self._vendre_des_entrees_a(heure_de_paris(2025, 11, 5, 12, 0))
        self._vendre_des_entrees_a(heure_de_paris(2026, 1, 14, 12, 0))
        self._creer_la_j_de_reprise_a(heure_de_paris(2026, 3, 10, 3, 0))
        j_de_reprise = ClotureCaisse.objects.get(niveau=ClotureCaisse.NIVEAU_JOURNALIER)

        self._verifier_le_refus_du_fec(j_de_reprise, "10/03/2026")

        # La J reprise est datée du jour de sa première vente (le 5 novembre 2025) :
        # la balance de ce jour la lit, sans refus. 2 entrées × 350 = 700 au débit.
        # / The "reprise" J is dated by its first sale; the balance of that day reads it.
        balance = balance_de_la_periode(date(2025, 11, 5), date(2025, 11, 5))
        assert balance["total_debit"] == 700

    # ------------------------------------------------------------------
    # 8. FEC refusé sur un mois qui commence avant la mise en service
    # / 8. FEC refused on a month starting before the go-live
    # ------------------------------------------------------------------

    def test_fec_refuse_sur_un_mois_qui_commence_avant_la_mise_en_service(self):
        """
        Historique : une entrée le 11 février et le 5 mars 2026 ; J reprise le 10 mars
        à 3 h (la mise en service). Une entrée le 20 mars, après. Le mois de mars
        commence le 1ᵉʳ mars, avant la mise en service : son FEC est refusé, bien
        qu'il contienne une J d'après la bascule. Le mois de février, tout entier dans
        l'historique, est refusé aussi.
        / March starts before the go-live: its FEC is refused, as is February's.
        """
        self._vendre_des_entrees_a(heure_de_paris(2026, 2, 11, 12, 0))
        self._vendre_des_entrees_a(heure_de_paris(2026, 3, 5, 12, 0))
        self._creer_la_j_de_reprise_a(heure_de_paris(2026, 3, 10, 3, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 10, 4, 10))
        self._vendre_des_entrees_a(heure_de_paris(2026, 3, 20, 12, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 21, 4, 10))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 4, 1, 4, 10))

        mois_de_mars = self._la_cloture_d_une_periode(
            ClotureCaisse.NIVEAU_MENSUEL,
            heure_de_paris(2026, 3, 1, 0, 0),
            heure_de_paris(2026, 4, 1, 0, 0),
        )
        self._verifier_le_refus_du_fec(mois_de_mars, "10/03/2026")

        mois_de_fevrier = self._la_cloture_d_une_periode(
            ClotureCaisse.NIVEAU_MENSUEL,
            heure_de_paris(2026, 2, 1, 0, 0),
            heure_de_paris(2026, 3, 1, 0, 0),
        )
        self._verifier_le_refus_du_fec(mois_de_fevrier, "10/03/2026")

    # ------------------------------------------------------------------
    # 9. FEC accepté à partir de la mise en service
    # / 9. FEC accepted from the go-live on
    # ------------------------------------------------------------------

    def test_fec_accepte_apres_la_mise_en_service(self):
        """
        Historique : une entrée le 11 février 2026 ; J reprise le 1ᵉʳ mars 2026 à
        0 h pile (la mise en service). Une entrée le 10 mars. La J du filet (11 mars à
        4 h) et le mois de mars commencent EXACTEMENT à la mise en service : ils ne
        commencent pas « avant », leurs FEC sont acceptés.
        / The net J and March start exactly at the go-live: not "before", their FEC are
        accepted.
        """
        self._vendre_des_entrees_a(heure_de_paris(2026, 2, 11, 12, 0))
        mise_en_service = heure_de_paris(2026, 3, 1, 0, 0)
        self._creer_la_j_de_reprise_a(mise_en_service)
        self._vendre_des_entrees_a(heure_de_paris(2026, 3, 10, 12, 0))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 4, 10))
        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 4, 1, 4, 10))

        journees = self._clotures_du_niveau(ClotureCaisse.NIVEAU_JOURNALIER)
        assert len(journees) == 2
        j_du_filet = journees[1]
        assert j_du_filet.datetime_debut == mise_en_service
        self._verifier_que_le_fec_est_accepte(j_du_filet)

        mois_de_mars = self._la_cloture_d_une_periode(
            ClotureCaisse.NIVEAU_MENSUEL,
            mise_en_service,
            heure_de_paris(2026, 4, 1, 0, 0),
        )
        self._verifier_que_le_fec_est_accepte(mois_de_mars)

    # ------------------------------------------------------------------
    # 10. Un règlement « reprise » n'a pas de lien Stripe dans l'admin
    # / 10. A "reprise" payment has no Stripe link in the admin
    # ------------------------------------------------------------------

    def test_reglement_reprise_sans_lien_stripe_dans_l_admin(self):
        """
        Un paiement Stripe qui a son identifiant de paiement (`pi_…`). Un règlement
        ordinaire relié à ce paiement a un lien vers le tableau de bord Stripe. Un
        règlement repris, relié au même paiement, de référence « reprise », n'en a
        aucun : la colonne « Référence » de l'admin affiche « reprise », sans lien.
        / A "reprise" payment linked to a Stripe payment has no Stripe link; the admin
        shows "reprise".
        """
        identifiant_du_paiement = f"pi_test_reprise_{identifiant_unique()}"
        paiement_stripe = Paiement_stripe.objects.create(
            status=Paiement_stripe.VALID,
            source=Paiement_stripe.FRONT_BILLETTERIE,
            payment_intent_id=identifiant_du_paiement,
        )
        inline_des_reglements = ReglementsDeLaVenteInline(Vente, staff_admin_site)

        # Un règlement ordinaire du paiement : son lien vers Stripe existe.
        # / An ordinary payment of the Stripe payment: its link exists.
        reglement_ordinaire = Reglement(
            moyen=PaymentMethod.STRIPE_NOFED,
            montant=1250,
            paiement_stripe=paiement_stripe,
            reference_externe="",
        )
        assert _adresse_stripe_d_un_reglement(reglement_ordinaire) == (
            f"https://dashboard.stripe.com/payments/{identifiant_du_paiement}"
        )

        # Le règlement repris d'un ancien avoir Stripe (fiche R §7) : aucun lien.
        # / The taken-over payment of an old Stripe credit note: no link.
        reglement_repris = Reglement(
            moyen=PaymentMethod.STRIPE_NOFED,
            montant=-1250,
            paiement_stripe=paiement_stripe,
            reference_externe=REFERENCE_D_UN_REGLEMENT_REPRIS,
        )
        assert _adresse_stripe_d_un_reglement(reglement_repris) is None
        with translation.override("fr"):
            reference_affichee = inline_des_reglements.reference_et_lien_stripe(
                reglement_repris
            )
        assert str(reference_affichee) == REFERENCE_D_UN_REGLEMENT_REPRIS
        assert "<a" not in str(reference_affichee)

    # ------------------------------------------------------------------
    # 11. Après la bascule, le filet part de la fin de la J reprise
    # / 11. After the switch, the net starts at the end of the "reprise" J
    # ------------------------------------------------------------------

    def test_filet_apres_la_bascule_part_de_la_fin_de_la_j_reprise(self):
        """
        Historique : une entrée le 14 janvier 2026 ; J reprise le 10 mars à 3 h. Une
        entrée le 10 mars à 19 h. Le filet du 11 mars (passage de 4 h 10) crée la J
        [fin de la J reprise, 11 mars 4 h[ : elle suit la J reprise sans trou, sa
        première vente suit la dernière de la J reprise, son perpétuel ajoute le sien
        à celui de la J reprise, et elle n'est pas marquée « reprise ».
        / The first net J starts at the end of the "reprise" J, follows it with no gap,
        adds to its perpetual total, and is not marked "reprise".
        """
        self._vendre_des_entrees_a(heure_de_paris(2026, 1, 14, 12, 0))
        self._creer_la_j_de_reprise_a(heure_de_paris(2026, 3, 10, 3, 0))
        vente_apres_la_bascule = self._vendre_des_entrees_a(
            heure_de_paris(2026, 3, 10, 19, 0)
        )

        self._lancer_la_tache_horaire_a(heure_de_paris(2026, 3, 11, 4, 10))

        j_de_reprise, j_du_filet = self._clotures_du_niveau(
            ClotureCaisse.NIVEAU_JOURNALIER
        )
        assert j_du_filet.datetime_debut == j_de_reprise.datetime_fin
        assert j_du_filet.datetime_fin == heure_de_paris(2026, 3, 11, 4, 0)
        assert j_du_filet.numero_premiere_vente == vente_apres_la_bascule.numero
        assert (
            j_du_filet.numero_premiere_vente == j_de_reprise.numero_derniere_vente + 1
        )
        # Perpétuel : 350 (J reprise) + 350 (cette J) = 700 ; 2 ventes.
        # / Perpetual: 350 + 350 = 700; 2 sales.
        assert j_du_filet.total_perpetuel == 700
        assert j_du_filet.nombre_ventes_perpetuel == 2
        assert j_du_filet.rapport_json["en_tete"].get("reprise") is not True
        assert verifier_continuite_des_journees() == []

    # ------------------------------------------------------------------
    # 12. La commande rejouée ne crée pas une seconde J reprise
    # / 12. The replayed command does not create a second "reprise" J
    # ------------------------------------------------------------------

    def test_j_reprise_rejouee_ne_cree_pas_une_seconde_cloture(self):
        """
        Historique : une entrée le 14 janvier 2026 ; J reprise le 10 mars à 3 h. Une
        entrée à 3 h 30, puis la commande rejouée à 3 h 45 : le lieu a déjà sa J
        reprise, rien n'est créé. (Sans cette garde, la vente de 3 h 30 donnerait une
        seconde J.) Un rejeu est normal : la commande dit que la J reprise est déjà
        faite, elle ne le présente pas comme un refus.
        / Replayed after a new sale, the command creates nothing: the venue already has
        its "reprise" J; the replay is reported as done, not as a refusal.
        """
        self._vendre_des_entrees_a(heure_de_paris(2026, 1, 14, 12, 0))
        self._creer_la_j_de_reprise_a(heure_de_paris(2026, 3, 10, 3, 0))
        self._vendre_des_entrees_a(heure_de_paris(2026, 3, 10, 3, 30))

        sortie_du_rejeu = self._creer_la_j_de_reprise_a(
            heure_de_paris(2026, 3, 10, 3, 45)
        )

        assert ClotureCaisse.objects.count() == 1
        assert MESSAGE_J_REPRISE_DEJA_FAITE in sortie_du_rejeu
        assert MESSAGE_DU_LIEU_DEJA_CLOTURE not in sortie_du_rejeu

    # ------------------------------------------------------------------
    # 13. Lieu qui a déjà une J ordinaire : J reprise refusée
    # / 13. Venue that already has an ordinary J: "reprise" J refused
    # ------------------------------------------------------------------

    def test_j_reprise_refusee_si_le_lieu_a_deja_une_j_ordinaire(self):
        """
        Le lieu a déjà une J ordinaire (le Z du 14 janvier 2026 à 23 h), puis une vente
        le 11 février. La commande du 10 mars à 3 h refuse la J reprise : elle partirait
        de la fin de cette J et ne couvrirait pas tout l'historique. Rien n'est créé, le
        refus est écrit avec un message clair, et la commande ne s'arrête pas en erreur
        (elle passe au lieu suivant).
        / A venue with an ordinary J: the "reprise" J is refused with a clear message,
        nothing is created, and the command does not stop on an error.
        """
        self._vendre_des_entrees_a(heure_de_paris(2026, 1, 14, 12, 0))
        with self._heure_figee(heure_de_paris(2026, 1, 14, 23, 0)):
            comptabilite.tasks.generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            )
        self._vendre_des_entrees_a(heure_de_paris(2026, 2, 11, 12, 0))

        sortie_de_la_commande = self._creer_la_j_de_reprise_a(
            heure_de_paris(2026, 3, 10, 3, 0)
        )

        assert MESSAGE_DU_LIEU_DEJA_CLOTURE in sortie_de_la_commande
        assert ClotureCaisse.objects.count() == 1
        j_ordinaire = ClotureCaisse.objects.get()
        assert j_ordinaire.rapport_json["en_tete"].get("reprise") is not True
