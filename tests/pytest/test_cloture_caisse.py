"""
Le bouton « Clôturer » de la caisse et ce qui l'entoure : la clôture journalière
unique du lieu (`comptabilite.ClotureCaisse`, la « J »), l'écran du Z, les
téléchargements et l'envoi du rapport, le ticket Z, le début du service en cours.
/ The register "Close" button and around it: the venue's single daily closure (J),
the Z screen, the report downloads and e-mail, the Z ticket, the current service start.

LOCALISATION : tests/pytest/test_cloture_caisse.py

RÈGLES MÉTIER TESTÉES
- Le bouton crée la J unique du lieu, par la tâche de clôture de `comptabilite`. Il y
  pose l'opérateur (`responsable`) et le point de vente d'où il est lancé (pour
  information : une J couvre tout le lieu).
- Il garde ses deux effets : les commandes de table ouvertes sont annulées, les tables
  occupées ou servies sont libérées.
- « Rien à clôturer » : sans vente réglée depuis la dernière J (ou sans aucune vente),
  le bouton répond 400 « Aucune vente à clôturer » et ne crée aucune clôture.
- Seule une carte primaire en mode gérant clôture, même si elle n'est pas liée au
  point de vente (une J couvre tout le lieu). Une carte sans mode gérant reçoit un
  refus 400 affiché dans #messages ; l'écran Ventes lui montre un bouton désactivé.
  Sans carte (session admin) : pas de restriction.
- L'écran du Z montre l'essentiel du rapport stocké dans la J : le chiffre d'affaires,
  les règlements, le tiroir (caisse espèces), la phrase de réconciliation. Ses seuls
  gestes : « Imprimer un duplicata » et « Fermer la caisse ». Son header n'a pas de
  bouton retour.
- La caisse ne télécharge ni n'envoie aucun rapport, et ne mène pas à l'admin : le
  PDF, le CSV et l'e-mail sont réservés à l'admin. Le duplicata du Z part sur
  l'imprimante du terminal avec les métadonnées du Z (type CLOT, uuid de la J) ;
  sans imprimante ou broker en panne : message clair en 400.
- Chaque impression du ticket Z est tracée : le ticket envoyé à l'imprimante porte ses
  métadonnées (type CLOT, uuid de la J). Le ticket Z est formaté depuis le rapport
  stocké dans la J.
- Le début du service en cours est la fin de la dernière J ; sans vente réglée
  depuis, il n'y a pas de service en cours (None). Un lieu sans J : la première
  ligne d'article des ventes réglées, toutes origines.
- « Rien à clôturer » ne fait aucun effet (tables et commandes inchangées). Les
  demandes au broker (impression, e-mail) viennent après les effets du bouton, et un
  broker en panne n'empêche ni la J ni l'écran du Z.
- Le ticket Z écrit ses heures dans le fuseau figé du rapport, imprime le numéro de
  la clôture et le nombre d'opérations numérotées, une ligne par moyen cashless.
- Les réglages d'e-mail de la caisse (`LaboutikConfiguration.rapport_emails`,
  `rapport_periodicite`) ne sont plus proposés dans l'admin : seuls ceux du lieu
  comptent.
/ The button creates the venue's single J with its operator and point of sale, keeps
its two table effects, refuses when there is nothing to close. The Z screen, the
downloads, the e-mail, the Z ticket and the service start all read the single closure.

SCHÉMA DÉDIÉ
Une J lit TOUTES les ventes du lieu : ce fichier tourne dans un lieu qui ne contient
que ses propres ventes (`FastTenantTestCase`, tronc §8.5 du chantier 05). Chaque test
annule sa transaction à la fin : rien n'arrive dans la base de dev. Le singleton
`LaboutikConfiguration` est créé en base (tests/PIEGES.md 9.86) : il porte la clé des
empreintes et le fond de caisse. La `Configuration` du lieu est réécrite à chaque
test : son cache (django-solo) survit à l'annulation de la transaction.
Les ventes sont écrites PAR LE SERVICE (`fabriques_vente.py`). Les tâches Celery sont
interceptées (`taches_celery_enregistrees`) : aucune n'est envoyée au worker.
/ Dedicated schema, rolled back after each test. Sales through the sale service.
Celery tasks are intercepted.

D'OÙ VIENNENT LES VALEURS ATTENDUES (calcul à la main)
Deux ventes au comptoir, fond de caisse 50,00 € :
- vente A : trois jus à 3,50 € (TVA 20 %), en espèces : 3 × 350 = 1050 ;
- vente B : une bière à 5,00 € (TVA 20 %), en carte bancaire : 500.
Chiffre d'affaires TTC : 1050 + 500 = 1550 → « 15,50 € ».
Règlements : espèces 1050 → « 10,50 € » ; carte bancaire 500 → « 5,00 € ».
Tiroir : fond 5000 + espèces reçues 1050 − rendues 0 + corrections 0 − sorties 0
= 6050 → « 60,50 € ».
Réconciliation : argent reçu 1550 = ventes payées en argent 1550 + recharges 0
− remboursements 0 − cartes vidées 0 + écarts 0 (forme de la phrase :
`comptabilite/presentation.py` `phrase_de_reconciliation`, fiche F §2).
Les montants attendus sont écrits à la main par `euros()`, avec les espaces
insécables du format à la française.
/ Hand-computed values: two sales (1050 cash, 500 card), cash float 50.00 €.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-G-lecteurs.md (§2, §2.1),
CHANTIER-05-F-rapport-unique.md (§2, §3.1).

Lancement / Run:
    make test ARGS="tests/pytest/test_cloture_caisse.py"
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import re  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from celery.app.task import Task  # noqa: E402
from kombu.exceptions import OperationalError  # noqa: E402

from django.db import connection  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

import comptabilite.tasks  # noqa: E402
from Administration.admin_tenant import staff_admin_site  # noqa: E402
from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Configuration, LigneArticle, PaymentMethod, Product, SaleOrigin,
)
from BaseBillet.models_vente import Vente  # noqa: E402
from BaseBillet.services_vente import (  # noqa: E402
    ajouter_article,
    ajouter_l_article_d_ecart_d_encaissement,
    ajouter_reglement,
    encaisser_vente,
    ouvrir_vente,
)
from comptabilite.models import ClotureCaisse  # noqa: E402
from fabriques_ecran import SIGNE_MOINS, euros, lire_l_element  # noqa: E402
from fabriques_panier import taches_celery_enregistrees  # noqa: E402
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from laboutik.models import (  # noqa: E402
    CartePrimaire, CommandeSauvegarde, LaboutikConfiguration, PointDeVente, Printer,
    Table,
)
from QrcodeCashless.models import CarteCashless  # noqa: E402
from laboutik.models import ClotureCaisse as AncienneClotureCaisse  # noqa: E402
from laboutik.printing.formatters import formatter_ticket_cloture  # noqa: E402
from laboutik.views import _calculer_datetime_ouverture_service  # noqa: E402


# Adresse de la clôture au comptoir (laboutik/urls.py).
# / Counter closure address.
URL_DE_LA_CLOTURE = '/laboutik/caisse/cloturer/'

# Le fuseau UTC (celui du serveur de test).
# / The UTC time zone (the test server's).
FUSEAU_UTC = ZoneInfo("UTC")

# Le fond de caisse du lieu de test, en centimes (50,00 €).
# / The test venue's cash float, in cents.
FOND_DE_CAISSE_EN_CENTIMES = 5000


class BrokerEnPanne:
    """
    Remplace l'envoi d'une tâche Celery par une panne du broker : chaque demande
    lève `OperationalError`. Avant de lever, elle note l'état de la table et de la
    commande du test : on voit ainsi si les effets du bouton étaient déjà faits.
    / Replaces a Celery request by a broker failure; records the table and order
    states at each call.
    """

    def __init__(self, table, commande):
        self.table = table
        self.commande = commande
        self.etats_vus_a_chaque_appel = []

    def appeler(self, tache, *arguments, **options):
        statut_de_la_table = Table.objects.get(pk=self.table.pk).statut
        statut_de_la_commande = CommandeSauvegarde.objects.get(
            pk=self.commande.pk
        ).statut
        self.etats_vus_a_chaque_appel.append((statut_de_la_table, statut_de_la_commande))
        raise OperationalError("Broker injoignable (test)")


class TestClotureCaisse(FastTenantTestCase):
    """
    Le bouton « Clôturer » de la caisse, sur la clôture unique, dans un lieu isolé.
    / The register "Close" button, on the single closure, in an isolated venue.
    """

    # Schéma et domaine propres à ce fichier : deux fichiers qui partageraient le même
    # schéma se marcheraient dessus. `Client.name` est unique et obligatoire.
    # / Schema and domain specific to this file. Client.name is unique and required.
    @classmethod
    def get_test_schema_name(cls):
        return 'test_cloture_caisse'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-cloture-caisse.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = 'Test Cloture Caisse'

    def setUp(self):
        """
        Un comptoir, un jus à 3,50 € et une bière à 5,00 €, un fond de caisse de
        50,00 €, un admin connecté (en français).
        / A counter, a juice and a beer, a 50.00 € cash float, a logged-in admin.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Les routes de la caisse sont gardées par `module_caisse`, qui exige
        # `module_monnaie_locale`. Aucun e-mail de rapport : une J n'envoie rien.
        # Toutes les valeurs sont écrites ici : le cache garde celles du test d'avant.
        # / Register routes need module_caisse. No report e-mail. Every value is
        # written here: the cache keeps the previous test's values.
        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.rapport_emails = ""
        configuration.rapport_periodicite = Configuration.PERIODICITE_NONE
        configuration.save()

        # Le singleton de la caisse, en base (tests/PIEGES.md 9.86) : la clé des
        # empreintes et le fond de caisse lu par le tiroir de la J.
        # / The register singleton, in the database: fingerprint key and cash float.
        configuration_de_la_caisse = LaboutikConfiguration.get_solo()
        configuration_de_la_caisse.fond_de_caisse = FOND_DE_CAISSE_EN_CENTIMES
        configuration_de_la_caisse.save()

        self.tarif_du_jus = creer_tarif_vendu(
            nom="Jus", prix_en_euros="3.50", taux_tva="20.00",
        )
        self.tarif_de_la_biere = creer_tarif_vendu(
            nom="Biere", prix_en_euros="5.00", taux_tva="20.00",
        )
        self.point_de_vente = PointDeVente.objects.create(
            name='Comptoir test cloture',
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            hidden=True,
        )

        # `TibilletUser` vit dans le schéma public (SHARED_APPS). Il est créé dans la
        # transaction du test, donc annulé avec elle.
        # / TibilletUser lives in the public schema; rolled back with the test.
        self.admin, _admin_cree = TibilletUser.objects.get_or_create(
            email='admin-test-cloture@tibillet.localhost',
            defaults={
                'username': 'admin-test-cloture@tibillet.localhost',
                'is_staff': True,
                'is_active': True,
            },
        )
        self.admin.client_admin.add(self.tenant)

        # Client HTTP routé vers le lieu de test, avec la session de l'admin, en
        # français (les textes attendus sont en français).
        # / HTTP client routed to the test venue, admin session, in French.
        self.client_http = TenantClient(self.tenant, HTTP_ACCEPT_LANGUAGE='fr')
        self.client_http.force_login(self.admin)

        self.post_data = {'uuid_pv': str(self.point_de_vente.uuid)}

    # ------------------------------------------------------------------
    # Outils du test
    # / Test helpers
    # ------------------------------------------------------------------

    def _vendre(self, tarif_vendu, quantite, prix_unitaire, moyen):
        """
        Une vente de caisse réglée, au comptoir du test : `quantite` articles au prix
        unitaire donné (TVA 20 %), payés avec un seul moyen. La ligne porte ses champs
        historiques (moyen, statut validé, point de vente), comme la caisse l'écrit.
        / A settled register sale at the test counter, paid with one method.
        """
        montant_en_centimes = prix_unitaire * quantite
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            operateur=self.admin,
            articles=[
                {
                    'pricesold': tarif_vendu,
                    'quantite': Decimal(quantite),
                    'prix_unitaire': prix_unitaire,
                    'taux_tva': Decimal('20'),
                    'payment_method': moyen,
                    'status': LigneArticle.VALID,
                    'uuid_transaction': uuid.uuid4(),
                    'point_de_vente': self.point_de_vente,
                },
            ],
            reglements=[{'moyen': moyen, 'montant': montant_en_centimes}],
        )
        verifier_egalites(vente)
        return vente

    def _vendre_trois_jus_en_especes_et_une_biere_en_cb(self):
        """
        Les deux ventes du calcul à la main (docstring du module) : vente A, trois jus
        en espèces (1050) ; vente B, une bière en carte bancaire (500).
        / The two hand-computed sales: A, three juices in cash; B, one beer by card.
        """
        vente_a = self._vendre(self.tarif_du_jus, 3, 350, PaymentMethod.CASH)
        vente_b = self._vendre(self.tarif_de_la_biere, 1, 500, PaymentMethod.CC)
        return vente_a, vente_b

    def _cliquer_sur_cloturer(self):
        """Le caissier clique sur « Clôturer ». / The cashier clicks "Close"."""
        return self.client_http.post(URL_DE_LA_CLOTURE, data=self.post_data)

    def _cloturer_par_la_tache(self):
        """
        Une J créée par la tâche de clôture, sans passer par le bouton (le filet
        automatique, par exemple). Rend la J.
        / A J created by the closure task, without the button. Returns the J.
        """
        uuid_de_la_j = comptabilite.tasks.generer_cloture_pour_tenant(
            schema_name=self.tenant.schema_name,
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        )
        assert uuid_de_la_j is not None, "La J aurait dû être créée."
        return ClotureCaisse.objects.get(uuid=uuid_de_la_j)

    def _la_seule_j_du_lieu(self):
        """La seule J du lieu de test. / The test venue's only J."""
        clotures_journalieres = list(
            ClotureCaisse.objects.filter(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
        )
        assert len(clotures_journalieres) == 1, (
            f"Attendu : une J, trouvé : {len(clotures_journalieres)}."
        )
        return clotures_journalieres[0]

    # ------------------------------------------------------------------
    # Le bouton crée la J unique
    # / The button creates the single J
    # ------------------------------------------------------------------

    def test_bouton_pose_le_responsable_et_le_point_de_vente_sur_la_j(self):
        """
        Le bouton lancé par l'admin, depuis le comptoir du test : la J porte
        l'opérateur (`responsable`) et ce point de vente.
        / The J carries the operator and the point of sale the button was used from.
        """
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)

        reponse = self._cliquer_sur_cloturer()

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        j_du_bouton = self._la_seule_j_du_lieu()
        assert j_du_bouton.responsable_id == self.admin.pk
        assert j_du_bouton.point_de_vente_id == self.point_de_vente.pk

    def test_bouton_la_j_couvre_les_ventes_du_lieu_avec_leurs_totaux(self):
        """
        Les deux ventes du calcul à la main, puis le bouton : la J couvre les ventes
        n° 1 et 2, deux ventes, CA TTC 1550, argent reçu 1550 (1050 espèces + 500 CB).
        / The J covers sales 1 and 2: two sales, revenue 1550, money received 1550.
        """
        vente_a, vente_b = self._vendre_trois_jus_en_especes_et_une_biere_en_cb()

        reponse = self._cliquer_sur_cloturer()

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        j_du_bouton = self._la_seule_j_du_lieu()
        assert j_du_bouton.numero_premiere_vente == vente_a.numero
        assert j_du_bouton.numero_derniere_vente == vente_b.numero
        assert j_du_bouton.nombre_transactions == 2
        assert j_du_bouton.total_general == 1550
        assert j_du_bouton.total_argent_recu == 1550

    # ------------------------------------------------------------------
    # Les deux effets gardés : tables et commandes
    # / The two kept effects: tables and orders
    # ------------------------------------------------------------------

    def test_cloture_ferme_tables(self):
        """
        Deux tables occupées et une vente : après le bouton, les deux tables sont
        libres.
        / Two occupied tables and one sale: after the button, both tables are free.
        """
        table1 = Table.objects.create(name='Test Cloture T1', statut=Table.OCCUPEE)
        table2 = Table.objects.create(name='Test Cloture T2', statut=Table.OCCUPEE)
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)

        reponse = self._cliquer_sur_cloturer()

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        table1.refresh_from_db()
        table2.refresh_from_db()
        assert table1.statut == Table.LIBRE
        assert table2.statut == Table.LIBRE

    def test_cloture_annule_commandes_ouvertes(self):
        """
        Une commande ouverte et une vente : après le bouton, la commande est annulée.
        / One open order and one sale: after the button, the order is cancelled.
        """
        commande = CommandeSauvegarde.objects.create(
            statut=CommandeSauvegarde.OPEN,
            commentaire='Test cloture',
        )
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)

        reponse = self._cliquer_sur_cloturer()

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        commande.refresh_from_db()
        assert commande.statut == CommandeSauvegarde.CANCEL

    # ------------------------------------------------------------------
    # Rien à clôturer
    # / Nothing to close
    # ------------------------------------------------------------------

    def test_rien_a_cloturer_aucune_vente_depuis_la_derniere_j(self):
        """
        Une vente, puis une J ; aucune vente depuis. Le bouton répond 400 « Aucune
        vente à clôturer » et ne crée aucune clôture (ni nouvelle J, ni ancienne
        clôture).
        / A sale, a J, no sale since: 400 "nothing to close", no closure created.
        """
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        self._cloturer_par_la_tache()

        reponse = self._cliquer_sur_cloturer()

        assert reponse.status_code == 400
        assert "Aucune vente à clôturer" in reponse.content.decode()
        assert ClotureCaisse.objects.count() == 1
        assert AncienneClotureCaisse.objects.count() == 0

    def test_rien_a_cloturer_lieu_sans_aucune_vente(self):
        """
        Un lieu sans aucune vente : le bouton répond 400 « Aucune vente à clôturer »,
        aucune clôture n'est créée.
        / A venue without any sale: 400 "nothing to close", no closure.
        """
        reponse = self._cliquer_sur_cloturer()

        assert reponse.status_code == 400
        assert "Aucune vente à clôturer" in reponse.content.decode()
        assert ClotureCaisse.objects.count() == 0
        assert AncienneClotureCaisse.objects.count() == 0

    # ------------------------------------------------------------------
    # Qui peut clôturer : la carte primaire en mode gérant
    # / Who may close: the primary card in manager mode
    # ------------------------------------------------------------------

    def _carte_primaire(self, tag_id, mode_gerant, liee_au_point_de_vente):
        """
        Une carte primaire (carte du caissier), en mode gérant ou non, liée ou non
        au comptoir du test. Rend son tag NFC.
        / A primary card, manager mode or not, linked or not to the test counter.
        Returns its NFC tag.
        """
        carte_du_caissier = CarteCashless.objects.create(tag_id=tag_id, number=tag_id)
        carte_primaire = CartePrimaire.objects.create(
            carte=carte_du_caissier, edit_mode=mode_gerant
        )
        if liee_au_point_de_vente:
            carte_primaire.points_de_vente.add(self.point_de_vente)
        return tag_id

    def _ouvrir_l_ecran_ventes(self, tag_id_de_la_carte):
        """L'écran « Ventes » de la caisse, ouvert avec une carte primaire.
        / The register "Sales" screen, opened with a primary card."""
        return self.client_http.get(
            '/laboutik/caisse/recap-en-cours/',
            {'uuid_pv': str(self.point_de_vente.uuid), 'tag_id_cm': tag_id_de_la_carte},
        )

    def test_carte_en_mode_gerant_cloture_meme_sans_lien_au_point_de_vente(self):
        """
        Une carte en mode gérant, PAS liée au comptoir : elle clôture quand même.
        La J couvre tout le lieu, le lien au point de vente ne compte pas.
        / A manager-mode card NOT linked to the counter still closes: the J
        covers the whole venue.
        """
        tag_du_gerant = self._carte_primaire(
            "CLGE0001", mode_gerant=True, liee_au_point_de_vente=False
        )
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)

        reponse = self.client_http.post(
            URL_DE_LA_CLOTURE, data={**self.post_data, 'tag_id_cm': tag_du_gerant}
        )

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        assert ClotureCaisse.objects.count() == 1

    def test_carte_sans_mode_gerant_ne_cloture_pas_et_le_message_s_affiche(self):
        """
        Une carte SANS mode gérant, pourtant liée au comptoir : refus 400 avec un
        message, rendu dans #messages (HX-Retarget, sinon htmx n'affiche rien).
        Aucune J n'est créée.
        / A card WITHOUT manager mode, though linked: 400 with a message rendered
        in #messages. No J is created.
        """
        tag_du_caissier = self._carte_primaire(
            "CLCA0001", mode_gerant=False, liee_au_point_de_vente=True
        )
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)

        reponse = self.client_http.post(
            URL_DE_LA_CLOTURE, data={**self.post_data, 'tag_id_cm': tag_du_caissier}
        )

        assert reponse.status_code == 400
        assert reponse["HX-Retarget"] == "#messages"
        assert "Seule une carte en mode gérant peut clôturer les caisses." in (
            reponse.content.decode()
        )
        assert ClotureCaisse.objects.count() == 0

    def test_ecran_ventes_carte_sans_mode_gerant_bouton_de_cloture_desactive(self):
        """
        L'écran « Ventes » avec une carte sans mode gérant : pas de bouton de
        clôture actif ni de popup, un bouton désactivé « Clôture réservée au mode
        gérant » à la place.
        / Sales screen with a non-manager card: a disabled button instead.
        """
        tag_du_caissier = self._carte_primaire(
            "CLCA0002", mode_gerant=False, liee_au_point_de_vente=True
        )
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)

        contenu = self._ouvrir_l_ecran_ventes(tag_du_caissier).content.decode()

        assert 'data-testid="btn-cloture-caisse-reservee-au-gerant"' in contenu
        assert "Clôture réservée au mode gérant" in contenu
        assert 'data-testid="btn-cloture-caisse"' not in contenu
        assert 'data-testid="cloture-confirmation"' not in contenu

    def test_ecran_ventes_carte_en_mode_gerant_bouton_de_cloture_actif(self):
        """
        L'écran « Ventes » avec une carte en mode gérant : le bouton « Clôturer
        toutes les caisses » et sa popup sont là.
        / Sales screen with a manager-mode card: the close button and its popup.
        """
        tag_du_gerant = self._carte_primaire(
            "CLGE0002", mode_gerant=True, liee_au_point_de_vente=True
        )
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)

        contenu = self._ouvrir_l_ecran_ventes(tag_du_gerant).content.decode()

        assert 'data-testid="btn-cloture-caisse"' in contenu
        assert 'data-testid="cloture-confirmation"' in contenu
        assert 'data-testid="btn-cloture-caisse-reservee-au-gerant"' not in contenu

    # ------------------------------------------------------------------
    # L'écran du Z
    # / The Z screen
    # ------------------------------------------------------------------

    def test_ecran_du_z_chiffre_affaires_reglements_tiroir_et_reconciliation(self):
        """
        Les deux ventes du calcul à la main, puis le bouton. L'écran du Z montre :
        - le chiffre d'affaires TTC : 15,50 € ;
        - les règlements : espèces 10,50 €, carte bancaire 5,00 € ;
        - le tiroir : fond 50,00 €, solde théorique 60,50 € ;
        - la phrase de réconciliation (argent reçu 15,50 €).
        / The Z screen shows revenue, payments, cash drawer and reconciliation.
        """
        self._vendre_trois_jus_en_especes_et_une_biere_en_cb()

        reponse = self._cliquer_sur_cloturer()

        page = reponse.content.decode()
        assert reponse.status_code == 200, page[:400]
        texte_du_total, _attributs = lire_l_element(page, "cloture-total-general")
        assert euros("15,50") in texte_du_total
        assert "Opérations numérotées : 2" in texte_du_total

        texte_du_chiffre_d_affaires, _attributs = lire_l_element(
            page, "cloture-chiffre-affaires"
        )
        assert euros("15,50") in texte_du_chiffre_d_affaires

        texte_des_reglements, _attributs = lire_l_element(page, "cloture-reglements")
        assert euros("10,50") in texte_des_reglements
        assert euros("5,00") in texte_des_reglements

        texte_du_tiroir, _attributs = lire_l_element(page, "cloture-caisse-especes")
        assert euros("50,00") in texte_du_tiroir
        assert euros("60,50") in texte_du_tiroir

        texte_de_la_reconciliation, _attributs = lire_l_element(
            page, "cloture-phrase-reconciliation"
        )
        phrase_attendue = (
            f"Argent reçu {euros('15,50')} = ventes payées en argent {euros('15,50')} "
            f"+ recharges {euros('0,00')} {SIGNE_MOINS} remboursements {euros('0,00')} "
            f"{SIGNE_MOINS} cartes vidées {euros('0,00')} "
            f"+ écarts d'encaissement {euros('0,00')}"
        )
        assert phrase_attendue in texte_de_la_reconciliation

    def test_ecran_du_z_seulement_le_duplicata_et_fermer_la_caisse(self):
        """
        L'écran du Z n'a que deux gestes : « Imprimer un duplicata » et « Fermer la
        caisse ». Ni téléchargement, ni envoi, ni lien vers l'admin : ils sont
        réservés à l'admin.
        / The Z screen has only two actions: print a duplicate, close the register.
        """
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)

        reponse = self._cliquer_sur_cloturer()

        page = reponse.content.decode()
        assert reponse.status_code == 200, page[:400]
        j_du_bouton = self._la_seule_j_du_lieu()
        _texte, attributs_du_duplicata = lire_l_element(page, "cloture-btn-duplicata")
        assert attributs_du_duplicata.get("hx-post") == (
            f"/laboutik/caisse/{j_du_bouton.uuid}/imprimer_duplicata_z/"
        )
        assert 'data-testid="btn-fermer-caisse"' in page
        assert "rapport_pdf" not in page
        assert "rapport_csv" not in page
        assert "envoyer_rapport" not in page
        assert "/admin/" not in page

        # Seul le bloc du total est annoncé à l'arrivée du Z, pas tout l'écran.
        # / Only the total block is announced when the Z arrives.
        _texte, attributs_de_l_ecran = lire_l_element(page, "cloture-rapport")
        _texte, attributs_du_total = lire_l_element(page, "cloture-total-general")
        assert "aria-live" not in attributs_de_l_ecran
        assert attributs_du_total.get("aria-live") == "polite"

    def test_ecran_du_z_header_sans_bouton_retour(self):
        """
        L'écran du Z remplace le header de l'écran Ventes (hx-swap-oob) par un
        header SANS bouton retour : après une clôture, on ne revient pas en arrière.
        / The Z screen swaps in a header WITHOUT back button.
        """
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)

        reponse = self._cliquer_sur_cloturer()

        page = reponse.content.decode()
        assert reponse.status_code == 200, page[:400]
        texte_du_titre, _attributs = lire_l_element(page, "header-titre")
        assert "Clôture" in texte_du_titre
        assert 'id="hdr-retour-zone"' in page
        assert 'hx-swap-oob="true"' in page
        assert 'data-testid="header-btn-retour"' not in page

    # ------------------------------------------------------------------
    # Le duplicata du ticket Z, et rien d'autre à la caisse
    # / The Z ticket duplicate, and nothing else at the register
    # ------------------------------------------------------------------

    def test_routes_de_telechargement_et_d_envoi_absentes_de_la_caisse(self):
        """
        Le PDF, le CSV et l'envoi du rapport sont réservés à l'admin : la caisse
        n'a plus ces routes (404).
        / PDF, CSV and e-mail are admin-only: the register has no such routes.
        """
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        j_du_lieu = self._cloturer_par_la_tache()

        for route in ['rapport_pdf', 'rapport_csv']:
            reponse = self.client_http.get(f'/laboutik/caisse/{j_du_lieu.uuid}/{route}/')
            assert reponse.status_code == 404, route
        reponse = self.client_http.post(
            f'/laboutik/caisse/{j_du_lieu.uuid}/envoyer_rapport/'
        )
        assert reponse.status_code == 404

    def test_duplicata_imprime_le_ticket_z_trace_type_clot_lien_vers_la_j(self):
        """
        Le terminal a une imprimante : le duplicata part à l'impression avec les
        métadonnées du Z (type « CLOT », uuid de la J). La tâche d'impression le
        marque DUPLICATA (le Z a déjà été imprimé). La caisse dit « Duplicata
        envoyé à l'imprimante ».
        / The duplicate is sent with the Z's metadata; the register confirms.
        """
        imprimante_du_terminal = Printer.objects.create(
            name='Imprimante test duplicata', printer_type=Printer.MOCK,
        )
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        j_du_lieu = self._cloturer_par_la_tache()

        with patch(
            'laboutik.views.imprimante_du_terminal',
            return_value=imprimante_du_terminal,
        ):
            with taches_celery_enregistrees() as taches_demandees:
                reponse = self.client_http.post(
                    f'/laboutik/caisse/{j_du_lieu.uuid}/imprimer_duplicata_z/'
                )

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        assert "Duplicata envoyé à l&#x27;imprimante" in reponse.content.decode()
        impressions_demandees = []
        for nom_de_la_tache, arguments in taches_demandees:
            if nom_de_la_tache == 'imprimer_async':
                impressions_demandees.append(arguments)
        assert len(impressions_demandees) == 1
        cle_de_l_imprimante, donnees_du_ticket, _schema = impressions_demandees[0]
        assert cle_de_l_imprimante == str(imprimante_du_terminal.pk)
        metadonnees = donnees_du_ticket['impression_meta']
        assert metadonnees['type_justificatif'] == 'CLOT'
        assert metadonnees['cloture_uuid'] == str(j_du_lieu.uuid)
        assert metadonnees['operateur_pk'] == str(self.admin.pk)

    def test_duplicata_sans_imprimante_message_clair_en_400(self):
        """
        Le terminal n'a pas d'imprimante : 400 (la caisse n'affiche que les 400 et
        422) avec un message clair, aucune impression demandée.
        / No printer: 400 with a clear message, nothing is printed.
        """
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        j_du_lieu = self._cloturer_par_la_tache()

        with patch('laboutik.views.imprimante_du_terminal', return_value=None):
            with taches_celery_enregistrees() as taches_demandees:
                reponse = self.client_http.post(
                    f'/laboutik/caisse/{j_du_lieu.uuid}/imprimer_duplicata_z/'
                )

        assert reponse.status_code == 400
        assert "Aucune imprimante configurée pour ce terminal" in (
            reponse.content.decode()
        )
        assert taches_demandees == []

    def test_duplicata_broker_en_panne_message_clair_en_400(self):
        """
        Le broker de Celery est en panne : pas d'erreur 500, un 400 avec un
        message clair (affiché par la caisse).
        / Broker down: no 500, a 400 with a clear message.
        """
        imprimante_du_terminal = Printer.objects.create(
            name='Imprimante test duplicata panne', printer_type=Printer.MOCK,
        )
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        j_du_lieu = self._cloturer_par_la_tache()

        with patch(
            'laboutik.views.imprimante_du_terminal',
            return_value=imprimante_du_terminal,
        ):
            with patch.object(
                Task,
                'apply_async',
                autospec=True,
                side_effect=OperationalError("Broker injoignable (test)"),
            ):
                reponse = self.client_http.post(
                    f'/laboutik/caisse/{j_du_lieu.uuid}/imprimer_duplicata_z/'
                )

        assert reponse.status_code == 400
        assert "Le duplicata n&#x27;a pas pu être envoyé à l&#x27;imprimante." in (
            reponse.content.decode()
        )

    def test_duplicata_uuid_inconnu_404(self):
        """
        Un uuid qui n'est pas celui d'une clôture du lieu : 404.
        / A uuid that is not a closure of the venue: 404.
        """
        reponse = self.client_http.post(
            f'/laboutik/caisse/{uuid.uuid4()}/imprimer_duplicata_z/'
        )

        assert reponse.status_code == 404

    # ------------------------------------------------------------------
    # Le ticket Z
    # / The Z ticket
    # ------------------------------------------------------------------

    def test_bouton_imprime_le_ticket_z_trace_type_clot_lien_vers_la_j(self):
        """
        Le terminal qui clôture a une imprimante : le ticket Z part à l'impression
        avec ses métadonnées de traçabilité, type « CLOT » et uuid de la J créée.
        / The Z ticket is sent with its tracking metadata: type CLOT and the J's uuid.
        """
        imprimante_du_terminal = Printer.objects.create(
            name='Imprimante test cloture', printer_type=Printer.MOCK,
        )
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)

        with patch(
            'laboutik.views.imprimante_du_terminal',
            return_value=imprimante_du_terminal,
        ):
            with taches_celery_enregistrees() as taches_demandees:
                reponse = self._cliquer_sur_cloturer()

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        j_du_bouton = self._la_seule_j_du_lieu()
        impressions_demandees = []
        for nom_de_la_tache, arguments in taches_demandees:
            if nom_de_la_tache == 'imprimer_async':
                impressions_demandees.append(arguments)
        assert len(impressions_demandees) == 1
        _cle_de_l_imprimante, donnees_du_ticket, _schema = impressions_demandees[0]
        assert 'impression_meta' in donnees_du_ticket
        metadonnees = donnees_du_ticket['impression_meta']
        assert metadonnees['type_justificatif'] == 'CLOT'
        assert metadonnees['cloture_uuid'] == str(j_du_bouton.uuid)

    def test_ticket_z_formate_depuis_le_rapport_de_la_j(self):
        """
        Le ticket Z d'une J garde la forme lue par les imprimantes (en-tête, articles,
        total, QR, pied) : une ligne par moyen d'argent (espèces 1050, CB 500), et un
        total de 1550. Dans ce lieu, CA TTC et argent reçu valent tous deux 1550.
        / The J's Z ticket keeps the printers' shape: one line per money method, total
        1550.
        """
        self._vendre_trois_jus_en_especes_et_une_biere_en_cb()
        j_du_lieu = self._cloturer_par_la_tache()

        donnees_du_ticket = formatter_ticket_cloture(j_du_lieu)

        assert set(donnees_du_ticket.keys()) == {
            'header', 'articles', 'total', 'qrcode', 'footer',
        }
        montants_des_lignes = []
        for ligne_du_ticket in donnees_du_ticket['articles']:
            montants_des_lignes.append(ligne_du_ticket['total'])
        assert sorted(montants_des_lignes) == [500, 1050]
        assert donnees_du_ticket['total']['amount'] == 1550

    def test_ticket_z_heures_dans_le_fuseau_du_lieu_numero_et_operations(self):
        """
        Un lieu en Martinique (UTC−4) ; le serveur est en UTC. Une vente encaissée le
        10/03/2026 à 14 h UTC, la J à 15 h UTC. Le ticket Z écrit ses heures dans le
        fuseau figé du rapport : début de période 10 h, fin 11 h (heure de la
        Martinique, jamais celle du serveur). Il imprime le numéro de la clôture
        (« Clôture n° 1 ») et le nombre d'opérations numérotées (1).
        / A Martinique venue: Z hours in the report's frozen time zone; closure number
        and numbered operations printed.
        """
        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "America/Martinique"
        configuration.save()
        with patch(
            'django.utils.timezone.now',
            return_value=datetime(2026, 3, 10, 14, 0, tzinfo=FUSEAU_UTC),
        ):
            self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        with patch(
            'django.utils.timezone.now',
            return_value=datetime(2026, 3, 10, 15, 0, tzinfo=FUSEAU_UTC),
        ):
            j_du_lieu = self._cloturer_par_la_tache()

        donnees_du_ticket = formatter_ticket_cloture(j_du_lieu)

        assert donnees_du_ticket['header']['date'] == "10/03/2026 11:00"
        assert "Clôture n° 1" in donnees_du_ticket['footer']
        # Le pied écrit la date courte (année sur deux chiffres) : « Début de
        # période: 10/03/26 10:00 » fait exactement 32 caractères, la largeur du
        # ticket.
        # / The footer writes the short date: exactly 32 characters.
        assert "Début de période: 10/03/26 10:00" in donnees_du_ticket['footer']
        assert len("Début de période: 10/03/26 10:00") == 32
        assert "Fermeture: 10/03/26 11:00" in donnees_du_ticket['footer']
        assert donnees_du_ticket['total']['label'] == "Opérations numérotées: 1"
        lignes_trop_larges = []
        for ligne_du_pied in donnees_du_ticket['footer']:
            if len(ligne_du_pied) > 32:
                lignes_trop_larges.append(ligne_du_pied)
        assert lignes_trop_larges == []

    def test_ticket_z_recharge_a_part_et_lignes_qui_font_le_total(self):
        """
        Une recharge de 20,00 € payée en espèces, puis une bière de 20,00 € payée en
        monnaie locale (cashless). La recharge n'est pas du chiffre d'affaires : elle
        le devient quand elle est dépensée.
        - Au-dessus du TOTAL : le chiffre d'affaires par moyen, une seule ligne,
          monnaie locale 2000 (espèces 2000 − 2000 de recharge = 0, non imprimée).
        - TOTAL : 2000 (chiffre d'affaires TTC) ; les lignes du dessus font le total.
        - Sous le total, à part : « Recharges: 20.00 EUR ».
        / Top-up 20 in cash, beer 20 in local currency: one line (local 2000), TOTAL
        2000, "Recharges 20" apart.
        """
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge", prix_en_euros="20.00", taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )
        tarif_de_la_grande_biere = creer_tarif_vendu(
            nom="Grande biere", prix_en_euros="20.00", taux_tva="20.00",
        )
        vente_de_la_recharge = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            articles=[{
                'pricesold': tarif_de_la_recharge,
                'quantite': Decimal('1'),
                'prix_unitaire': 2000,
                'taux_tva': Decimal('0'),
            }],
            reglements=[{'moyen': PaymentMethod.CASH, 'montant': 2000}],
        )
        verifier_egalites(vente_de_la_recharge)
        self._vendre(tarif_de_la_grande_biere, 1, 2000, PaymentMethod.LOCAL_EURO)
        j_du_lieu = self._cloturer_par_la_tache()

        donnees_du_ticket = formatter_ticket_cloture(j_du_lieu)

        montants_des_lignes = []
        for ligne_du_ticket in donnees_du_ticket['articles']:
            montants_des_lignes.append(ligne_du_ticket['total'])
        assert montants_des_lignes == [2000]
        assert donnees_du_ticket['total']['amount'] == 2000
        assert sum(montants_des_lignes) == donnees_du_ticket['total']['amount']
        assert "Recharges: 20.00 EUR" in donnees_du_ticket['footer']

    def test_ticket_z_ecart_d_encaissement_a_part_sous_le_total(self):
        """
        Un billet à 20,00 € vendu en ligne, payé par Stripe, qui encaisse 20,03 € :
        un écart d'encaissement de +3, hors chiffre d'affaires.
        - Au-dessus du TOTAL : Stripe 2003 − 3 = 2000, une seule ligne.
        - TOTAL : 2000 (chiffre d'affaires TTC) ; les lignes du dessus font le total.
        - Sous le total, à part : exactement « Écarts d'encaissement: 0.03 EUR »
          (signe positif : Stripe a encaissé plus que le billet).
        / A Stripe ticket with a +3 gap: one line 2000, TOTAL 2000, the gap line apart.
        """
        tarif_du_billet = creer_tarif_vendu(
            nom="Billet", prix_en_euros="20.00", taux_tva="5.50",
        )
        vente_en_ligne = ouvrir_vente(
            origine=SaleOrigin.LESPASS,
            nature=Vente.Nature.VENTE,
        )
        ajouter_article(
            vente_en_ligne,
            pricesold=tarif_du_billet,
            quantite=Decimal('1'),
            prix_unitaire=2000,
            taux_tva=Decimal('5.5'),
        )
        ajouter_l_article_d_ecart_d_encaissement(vente_en_ligne, 3)
        ajouter_reglement(
            vente_en_ligne, moyen=PaymentMethod.STRIPE_NOFED, montant=2003,
        )
        verifier_egalites(encaisser_vente(vente_en_ligne))
        j_du_lieu = self._cloturer_par_la_tache()

        donnees_du_ticket = formatter_ticket_cloture(j_du_lieu)

        montants_des_lignes = []
        for ligne_du_ticket in donnees_du_ticket['articles']:
            montants_des_lignes.append(ligne_du_ticket['total'])
        assert montants_des_lignes == [2000]
        assert donnees_du_ticket['total']['amount'] == 2000
        assert sum(montants_des_lignes) == donnees_du_ticket['total']['amount']
        lignes_d_ecart = []
        for ligne_du_pied in donnees_du_ticket['footer']:
            if ligne_du_pied.startswith("Écarts d'encaissement"):
                lignes_d_ecart.append(ligne_du_pied)
        assert lignes_d_ecart == ["Écarts d'encaissement: 0.03 EUR"]

    def test_ticket_z_une_ligne_par_moyen_cashless(self):
        """
        Une bière (500) payée en monnaie locale (LE) et un jus (350) payé en jetons
        cadeau (LG). Le ticket Z porte une ligne par moyen cashless, pas une ligne
        « Cashless » de 850.
        / One line per cashless method (500 and 350), not one 850 line.
        """
        self._vendre(self.tarif_de_la_biere, 1, 500, PaymentMethod.LOCAL_EURO)
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.LOCAL_GIFT)
        j_du_lieu = self._cloturer_par_la_tache()

        donnees_du_ticket = formatter_ticket_cloture(j_du_lieu)

        montants_des_lignes = []
        for ligne_du_ticket in donnees_du_ticket['articles']:
            montants_des_lignes.append(ligne_du_ticket['total'])
        assert sorted(montants_des_lignes) == [350, 500]

    # ------------------------------------------------------------------
    # Le bouton et le broker
    # / The button and the broker
    # ------------------------------------------------------------------

    def test_bouton_rien_a_cloturer_ne_touche_ni_tables_ni_commandes(self):
        """
        Une vente, puis la J faite par la tâche (le filet, par exemple). Une table
        occupée et une commande ouverte. Le caissier clique « Clôturer » : rien à
        clôturer (400), et le bouton ne fait AUCUN effet : la table reste occupée,
        la commande reste ouverte (comme avant la clôture unique).
        / Nothing to close after the net's J: 400, the table stays occupied and the
        order stays open.
        """
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        self._cloturer_par_la_tache()
        table_occupee = Table.objects.create(name='Test rien a cloturer', statut=Table.OCCUPEE)
        commande_ouverte = CommandeSauvegarde.objects.create(
            statut=CommandeSauvegarde.OPEN, commentaire='Test rien a cloturer',
        )

        reponse = self._cliquer_sur_cloturer()

        assert reponse.status_code == 400
        table_occupee.refresh_from_db()
        commande_ouverte.refresh_from_db()
        assert table_occupee.statut == Table.OCCUPEE
        assert commande_ouverte.statut == CommandeSauvegarde.OPEN

    def test_broker_en_panne_effets_faits_avant_et_ecran_du_z_affiche(self):
        """
        Le lieu a un destinataire de rapport en périodicité journalière, le
        terminal a une imprimante, mais le broker est en panne : chaque demande de
        tâche lève une erreur. Une table occupée, une commande ouverte, une vente.
        Le clic répond 200 avec l'écran du Z : la J existe, la table est libérée et
        la commande annulée, et ces deux effets sont déjà faits à l'appel au broker.
        Seule l'impression du ticket Z demande le broker : une J ne demande pas
        d'e-mail (son Z part dans le récap du matin).
        / Broker down: the J exists, the Z screen shows, and the table/order effects
        were already done at the broker call (the print only: a J requests no e-mail).
        """
        configuration = Configuration.get_solo()
        configuration.rapport_emails = 'compta@lieu-de-test.org'
        configuration.rapport_periodicite = Configuration.PERIODICITE_JOURNALIER
        configuration.save()
        imprimante_du_terminal = Printer.objects.create(
            name='Imprimante broker en panne', printer_type=Printer.MOCK,
        )
        table_occupee = Table.objects.create(name='Test broker', statut=Table.OCCUPEE)
        commande_ouverte = CommandeSauvegarde.objects.create(
            statut=CommandeSauvegarde.OPEN, commentaire='Test broker',
        )
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        broker_en_panne = BrokerEnPanne(table_occupee, commande_ouverte)

        with patch(
            'laboutik.views.imprimante_du_terminal',
            return_value=imprimante_du_terminal,
        ):
            with patch.object(
                Task, 'apply_async', autospec=True, side_effect=broker_en_panne.appeler,
            ):
                reponse = self._cliquer_sur_cloturer()

        page = reponse.content.decode()
        assert reponse.status_code == 200, page[:400]
        assert 'data-testid="cloture-rapport"' in page
        self._la_seule_j_du_lieu()
        table_occupee.refresh_from_db()
        commande_ouverte.refresh_from_db()
        assert table_occupee.statut == Table.LIBRE
        assert commande_ouverte.statut == CommandeSauvegarde.CANCEL
        # Une seule demande au broker, l'impression, tentée après les effets. Une J
        # ne demande pas d'e-mail : son Z part dans le récap du matin.
        # / One broker request only, the print, after the effects. A J requests no
        # e-mail: its Z goes in the morning recap.
        assert broker_en_panne.etats_vus_a_chaque_appel == [
            (Table.LIBRE, CommandeSauvegarde.CANCEL),
        ]

    def test_bouton_lieu_en_periodicite_j_aucun_email_separe(self):
        """
        Le lieu veut ses rapports journaliers, avec un destinataire. Un clic sur
        « Clôturer » crée la J et ne demande aucun e-mail : le Z de cette J part dans
        le récap du matin des admins.
        / Daily reports venue: one click creates the J and requests no e-mail; its Z
        goes in the admins' morning recap.
        """
        configuration = Configuration.get_solo()
        configuration.rapport_emails = 'compta@lieu-de-test.org'
        configuration.rapport_periodicite = Configuration.PERIODICITE_JOURNALIER
        configuration.save()
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)

        with taches_celery_enregistrees() as taches_demandees:
            reponse = self._cliquer_sur_cloturer()

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        self._la_seule_j_du_lieu()
        demandes_d_email = []
        for nom_de_la_tache, arguments in taches_demandees:
            if nom_de_la_tache.startswith('envoyer_email_cloture'):
                demandes_d_email.append((nom_de_la_tache, arguments))
        assert demandes_d_email == []

    # ------------------------------------------------------------------
    # Le début du service en cours
    # / The current service start
    # ------------------------------------------------------------------

    def test_debut_du_service_egal_a_la_fin_de_la_derniere_j(self):
        """
        Une vente, une J, puis une vente : le service en cours commence à la fin de
        la J (`datetime_fin`), pas à l'heure de la vente qui la suit.
        / The current service starts at the end of the last J.
        """
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        j_du_lieu = self._cloturer_par_la_tache()
        self._vendre(self.tarif_de_la_biere, 1, 500, PaymentMethod.CC)

        debut_du_service = _calculer_datetime_ouverture_service()

        assert debut_du_service == j_du_lieu.datetime_fin

    def test_debut_du_service_aucune_vente_depuis_la_derniere_j(self):
        """
        Une vente, puis une J ; aucune vente depuis. Il n'y a pas de service en
        cours : None (lu « aucune vente en cours » par le ticket X, le récap, la
        sortie de caisse, le rapport temps réel et la liste des ventes).
        / A sale, a J, no sale since: no current service, None.
        """
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        self._cloturer_par_la_tache()

        debut_du_service = _calculer_datetime_ouverture_service()

        assert debut_du_service is None

    def test_debut_du_service_lieu_sans_j_premiere_ligne_des_ventes_reglees(self):
        """
        Un lieu sans J : le service commence à l'heure de la première ligne d'article
        des ventes réglées (écrite juste avant l'encaissement de sa vente).
        / A venue without J: the service starts at the first item line of the
        settled sales.
        """
        premiere_vente = self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        self._vendre(self.tarif_de_la_biere, 1, 500, PaymentMethod.CC)
        premiere_ligne = LigneArticle.objects.get(vente=premiere_vente)

        debut_du_service = _calculer_datetime_ouverture_service()

        assert debut_du_service == premiere_ligne.datetime

    def test_debut_du_service_lieu_sans_j_ignore_une_vente_en_attente_plus_ancienne(self):
        """
        Un lieu sans J. D'abord une ligne de bière dans une vente EN ATTENTE (jamais
        encaissée), puis une vente réglée. Le service commence à la ligne de la vente
        réglée : la ligne de la vente en attente, plus ancienne, ne compte pas.
        / Without J: an older line of a PENDING sale, then a settled sale; the service
        starts at the settled sale's line.
        """
        vente_en_attente = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VENTE,
            point_de_vente=self.point_de_vente,
        )
        ligne_en_attente = ajouter_article(
            vente_en_attente,
            pricesold=self.tarif_de_la_biere,
            quantite=Decimal('1'),
            prix_unitaire=500,
            taux_tva=Decimal('20'),
        )
        vente_reglee = self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        ligne_reglee = LigneArticle.objects.get(vente=vente_reglee)
        assert ligne_en_attente.datetime < ligne_reglee.datetime

        debut_du_service = _calculer_datetime_ouverture_service()

        assert debut_du_service == ligne_reglee.datetime

    def test_debut_du_service_lieu_sans_j_vente_en_ligne_seule(self):
        """
        Un lieu sans J dont la seule vente réglée est EN LIGNE (pas de caisse) : le
        service couvre toutes les origines, il commence à la ligne de cette vente.
        / A venue without J whose only settled sale is ONLINE: the service covers
        every origin and starts at that sale.
        """
        vente_en_ligne = fabriquer_vente_encaissee(
            origine=SaleOrigin.LESPASS,
            articles=[
                {
                    'pricesold': self.tarif_de_la_biere,
                    'quantite': Decimal('1'),
                    'prix_unitaire': 500,
                    'taux_tva': Decimal('20'),
                },
            ],
            reglements=[{'moyen': PaymentMethod.STRIPE_NOFED, 'montant': 500}],
        )
        ligne_de_la_vente_en_ligne = LigneArticle.objects.get(vente=vente_en_ligne)

        debut_du_service = _calculer_datetime_ouverture_service()

        assert debut_du_service == ligne_de_la_vente_en_ligne.datetime

    # ------------------------------------------------------------------
    # Les réglages d'e-mail de la caisse
    # / The register's e-mail settings
    # ------------------------------------------------------------------

    def test_reglages_d_email_de_la_caisse_caches_de_l_admin(self):
        """
        L'admin de la configuration de la caisse ne propose ni `rapport_emails` ni
        `rapport_periodicite` : seuls les destinataires du lieu comptent.
        / The register configuration admin does not show its e-mail settings.
        """
        admin_de_la_configuration_de_la_caisse = staff_admin_site._registry[
            LaboutikConfiguration
        ]
        champs_proposes = []
        for _titre, options_du_bloc in admin_de_la_configuration_de_la_caisse.fieldsets:
            for nom_du_champ in options_du_bloc['fields']:
                champs_proposes.append(nom_du_champ)

        assert 'rapport_emails' not in champs_proposes
        assert 'rapport_periodicite' not in champs_proposes
