"""
tests/pytest/test_rapport_temps_reel.py — Les écrans du service en cours : ticket X,
récapitulatif en cours, sortie de caisse.
/ The current service screens: X ticket, current recap, cash withdrawal.

Couvre : `TestServiceEnCours` ci-dessous. Le rapport temps réel est celui de l'admin
de la comptabilité (tests/pytest/test_comptabilite_admin.py).
Covers: `TestServiceEnCours` below. The real-time report is the accounting admin's.

RÈGLES MÉTIER TESTÉES (`TestServiceEnCours`)
Le service en cours commence à la fin de la dernière clôture journalière unique (J)
du lieu. Le ticket X, le récapitulatif en cours et la sortie de caisse lisent le
rapport des ventes unique (`comptabilite.rapport.RapportDesVentes`) de ce début
jusqu'à maintenant, jamais stocké :
- ticket X imprimé (`imprimer_ticket_x`) : une ligne par moyen de paiement, total =
  chiffre d'affaires TTC (comme le ticket Z), pied avec le fond de caisse, les
  espèces reçues et le solde théorique du tiroir (section « caisse espèces ») ;
- récapitulatif en cours (`recap_en_cours`) : les sections du rapport mises en forme
  par `comptabilite/presentation.py` (`sections_pour_affichage`), au style de la
  caisse ;
- sortie de caisse (`sortie_de_caisse`) : le fond et le solde théorique du tiroir.
Une vente encaissée avant la J n'est jamais dans ces écrans.
/ The current service starts at the end of the last single J. The X ticket, the
current recap and the cash withdrawal read the single sales report from that start
to now. A sale before the J never shows.

D'OÙ VIENNENT LES VALEURS ATTENDUES (calcul à la main)
Fond de caisse 50,00 € (5000). Un jus vaut 3,50 € (350), une bière 5,00 € (500).
- AVANT la J : trois jus en espèces (1050), puis la J.
- APRÈS la J (le service en cours) : deux jus en espèces (700), une bière en CB
  (500), une carte de 2,00 € vidée au comptoir, les espèces rendues (−200), et une
  sortie de caisse de 3,00 € (300).
Chiffre d'affaires TTC : 700 + 500 = 1200 (« 12,00 € ») ; la vente d'avant la J
(1050, « 10,50 € ») n'y est pas.
Règlements : espèces 700 (« 7,00 € »), CB 500 (« 5,00 € ») ; le vidage n'est pas un
règlement de vente (section annexe du rapport).
Tiroir, lignes signées (l'argent qui sort est négatif) : fond 5000 + reçues 700 +
rendues −200 + corrections 0 + sorties −300 = 5200 (« 52,00 € »). Espèces nettes du
service : 5200 − 5000 = 200. Les espèces rendues d'un vidage de carte sortent du
tiroir : sans elles, le solde serait 5400.
Réconciliation : argent reçu 700 + 500 − 200 = 1000 (« 10,00 € ») = ventes payées en
argent 1200 + recharges 0 − remboursements 0 − cartes vidées 200 + écarts 0.
/ Hand computation: revenue 1200, payments cash 700 / card 500, drawer 5200, money
received 1000.

Utilise FastTenantTestCase (django-tenants) : schema isole, TenantClient pour le routage URL.
Uses FastTenantTestCase (django-tenants): isolated schema, TenantClient for URL routing.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-G-lecteurs.md (§2),
CHANTIER-05-F-rapport-unique.md (§2).

Lancement / Run:
    make test ARGS="tests/pytest/test_rapport_temps_reel.py"
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import re  # noqa: E402
import uuid  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest.mock import patch  # noqa: E402

from celery.app.task import Task  # noqa: E402
from django.db import connection  # noqa: E402
from kombu.exceptions import OperationalError  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

import comptabilite.tasks  # noqa: E402
from AuthBillet.models import TibilletUser, Wallet  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Configuration, LigneArticle, PaymentMethod, SaleOrigin,
)
from BaseBillet.models_vente import Vente  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from fabriques_panier import identifiant_unique, taches_celery_enregistrees  # noqa: E402
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from fedow_core.models import Asset  # noqa: E402
from laboutik.models import (  # noqa: E402
    LaboutikConfiguration,
    PointDeVente,
    Printer,
    SortieCaisse,
)
from fabriques_ecran import (  # noqa: E402
    SIGNE_MOINS,
    euros,
    lire_l_element,
    moins_euros,
)


# Le fond de caisse du lieu de test, en centimes (50,00 €).
# / The test venue's cash float, in cents.
FOND_DE_CAISSE_EN_CENTIMES = 5000

# Adresses de la caisse (laboutik/urls.py).
# / Register addresses.
URL_DU_TICKET_X = '/laboutik/caisse/imprimer-ticket-x/'
URL_DU_RECAP_EN_COURS = '/laboutik/caisse/recap-en-cours/'
URL_DE_LA_SORTIE_DE_CAISSE = '/laboutik/caisse/sortie-de-caisse/'


class TestServiceEnCours(FastTenantTestCase):
    """
    Ticket X, récapitulatif en cours et sortie de caisse sur le rapport des ventes
    unique, du début du service (fin de la dernière J) jusqu'à maintenant.
    / X ticket, current recap and cash withdrawal on the single sales report.
    """

    @classmethod
    def get_test_schema_name(cls):
        return 'test_service_en_cours'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-service-en-cours.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = 'Test service en cours'

    def setUp(self):
        """
        Un comptoir, un jus à 3,50 € et une bière à 5,00 €, un fond de caisse de
        50,00 €, un admin connecté (en français).
        / A counter, a juice and a beer, a 50.00 € cash float, a logged-in admin.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Toutes les valeurs sont écrites ici : le cache garde celles du test d'avant.
        # Aucun e-mail de rapport : une J n'envoie rien.
        # / Every value is written here. No report e-mail.
        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.rapport_emails = ""
        configuration.rapport_periodicite = Configuration.PERIODICITE_NONE
        configuration.save()

        # Le singleton de la caisse, en base (tests/PIEGES.md 9.86) : la clé des
        # empreintes et le fond de caisse lu par le tiroir.
        # / The register singleton: fingerprint key and cash float.
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
            name='Comptoir service en cours',
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            hidden=True,
        )

        # `TibilletUser` vit dans le schéma public ; il est annulé avec le test.
        # / TibilletUser lives in the public schema; rolled back with the test.
        self.admin, _admin_cree = TibilletUser.objects.get_or_create(
            email='admin-test-service-en-cours@tibillet.localhost',
            defaults={
                'username': 'admin-test-service-en-cours@tibillet.localhost',
                'is_staff': True,
                'is_active': True,
            },
        )
        self.admin.client_admin.add(self.tenant)

        self.client_http = TenantClient(self.tenant, HTTP_ACCEPT_LANGUAGE='fr')
        self.client_http.force_login(self.admin)

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
            reglements=[{'moyen': moyen, 'montant': prix_unitaire * quantite}],
        )
        verifier_egalites(vente)
        return vente

    def _vider_une_carte(self, montant_en_centimes):
        """
        Une carte en monnaie locale vidée au comptoir, les espèces rendues : la vente
        VIDAGE_CARTE n'a pas d'article, ses règlements s'annulent (monnaie locale
        +montant, espèces −montant).
        / A local currency card emptied at the counter, cash given back.
        """
        portefeuille_d_origine = Wallet.objects.create(
            name=f"Portefeuille service en cours {identifiant_unique()}"
        )
        monnaie_locale = Asset.objects.create(
            name="Monnaie locale service en cours",
            currency_code="EUR",
            category=Asset.TLF,
            tenant_origin=self.tenant,
            wallet_origin=portefeuille_d_origine,
        )
        vente_du_vidage = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VIDAGE_CARTE,
            point_de_vente=self.point_de_vente,
            reglements=[
                {
                    'moyen': PaymentMethod.LOCAL_EURO,
                    'montant': montant_en_centimes,
                    'asset': monnaie_locale.uuid,
                },
                {'moyen': PaymentMethod.CASH, 'montant': -montant_en_centimes},
            ],
        )
        verifier_egalites(vente_du_vidage)

    def _cloturer_la_journee(self):
        """La J du lieu, maintenant, par la vraie tâche. / The venue's J, now."""
        uuid_de_la_j = comptabilite.tasks.generer_cloture_pour_tenant(
            schema_name=self.tenant.schema_name,
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        )
        assert uuid_de_la_j is not None, "La J aurait dû être créée."

    def _une_journee_close_puis_le_service_en_cours(self):
        """
        Le décor du calcul à la main (docstring du module) : trois jus en espèces,
        la J ; puis deux jus en espèces, une bière en CB, une carte de 2,00 € vidée
        et une sortie de caisse de 3,00 € (trois pièces de 1 €).
        / The hand-computed setting: three cash juices, the J; then two cash juices,
        a card beer, a 2.00 € card emptied and a 3.00 € cash withdrawal.
        """
        self._vendre(self.tarif_du_jus, 3, 350, PaymentMethod.CASH)
        self._cloturer_la_journee()
        self._vendre(self.tarif_du_jus, 2, 350, PaymentMethod.CASH)
        self._vendre(self.tarif_de_la_biere, 1, 500, PaymentMethod.CC)
        self._vider_une_carte(200)
        SortieCaisse.objects.create(
            point_de_vente=self.point_de_vente,
            operateur=self.admin,
            montant_total=300,
            ventilation={"100": 3},
        )

    def _imprimer_le_ticket_x(self):
        """
        Le caissier imprime le ticket X, depuis un terminal qui a une imprimante.
        Rend le ticket envoyé à l'imprimante (les données de `imprimer_async`).
        / The cashier prints the X ticket. Returns the ticket sent to the printer.
        """
        imprimante_du_terminal = Printer.objects.create(
            name='Imprimante service en cours', printer_type=Printer.MOCK,
        )
        with patch(
            'laboutik.views.imprimante_du_terminal',
            return_value=imprimante_du_terminal,
        ):
            with taches_celery_enregistrees() as taches_demandees:
                reponse = self.client_http.post(
                    URL_DU_TICKET_X, data={'uuid_pv': str(self.point_de_vente.uuid)}
                )
        assert reponse.status_code == 200, reponse.content.decode()[:400]

        tickets_envoyes = []
        for nom_de_la_tache, arguments in taches_demandees:
            if nom_de_la_tache == 'imprimer_async':
                _cle_de_l_imprimante, donnees_du_ticket, _schema = arguments
                tickets_envoyes.append(donnees_du_ticket)
        assert len(tickets_envoyes) == 1
        return tickets_envoyes[0]

    def _montants_des_lignes(self, ticket):
        """Les montants des lignes d'un ticket, triés. / A ticket's line amounts."""
        montants = []
        for ligne_du_ticket in ticket['articles']:
            montants.append(ligne_du_ticket['total'])
        return sorted(montants)

    # ------------------------------------------------------------------
    # Ticket X
    # / X ticket
    # ------------------------------------------------------------------

    def test_ticket_x_lignes_total_et_tiroir_du_service_en_cours(self):
        """
        Le décor du calcul à la main. Le ticket X porte une ligne espèces (700) et une
        ligne CB (500), un total de 1200 (chiffre d'affaires TTC). Son pied porte le
        tiroir, lignes signées et non nulles : fond 50.00, espèces reçues 7.00,
        espèces rendues −2.00, sorties −3.00, solde 52.00. Les corrections (0) ne
        sont pas imprimées. Les lignes au-dessus du solde s'additionnent en solde :
        50 + 7 − 2 − 3 = 52.
        / X ticket: lines 700 and 500, total 1200; drawer lines 50.00, 7.00, −2.00,
        −3.00, balance 52.00, adding up.
        """
        self._une_journee_close_puis_le_service_en_cours()

        ticket = self._imprimer_le_ticket_x()

        assert self._montants_des_lignes(ticket) == [500, 700]
        assert ticket['total']['amount'] == 1200
        # Sous le total, à part : la carte vidée (−200), pas du chiffre d'affaires.
        # / Under the total, apart: the emptied card (−200), not revenue.
        assert "Cartes vidées: -2.00 EUR" in ticket['footer']
        lignes_du_tiroir = self._lignes_du_tiroir_du_ticket(ticket)
        assert lignes_du_tiroir == [
            "Fond de caisse: 50.00 EUR",
            "Espèces reçues: 7.00 EUR",
            "Espèces rendues: -2.00 EUR",
            "Sorties de caisse: -3.00 EUR",
            "Solde théorique: 52.00 EUR",
        ]
        montants_au_dessus_du_solde = []
        for ligne_du_tiroir in lignes_du_tiroir[:-1]:
            montants_au_dessus_du_solde.append(self._montant_d_une_ligne(ligne_du_tiroir))
        assert sum(montants_au_dessus_du_solde) == self._montant_d_une_ligne(
            lignes_du_tiroir[-1]
        )
        # Aucune ligne de pied plus large que le ticket (32 caractères) : l'imprimante
        # ne coupe pas une ligne au milieu d'un mot.
        # / No footer line wider than the 32-char ticket.
        lignes_trop_larges = []
        for ligne_du_pied in ticket['footer']:
            if len(ligne_du_pied) > 32:
                lignes_trop_larges.append(ligne_du_pied)
        assert lignes_trop_larges == []

    def _lignes_du_tiroir_du_ticket(self, ticket):
        """
        Les lignes du tiroir au pied d'un ticket X : après la ligne vide, jusqu'à la
        ligne du solde comprise.
        / The drawer lines of an X ticket footer: after the blank line, up to the
        balance line.
        """
        lignes_du_tiroir = []
        apres_la_ligne_vide = False
        for ligne_du_pied in ticket['footer']:
            if ligne_du_pied == "":
                apres_la_ligne_vide = True
                continue
            if not apres_la_ligne_vide:
                continue
            lignes_du_tiroir.append(ligne_du_pied)
            if ligne_du_pied.startswith("Solde théorique"):
                break
        return lignes_du_tiroir

    def _montant_d_une_ligne(self, ligne_du_ticket):
        """
        Le montant d'une ligne « Libellé: 12.34 EUR », en centimes (entier signé).
        / The amount of a "Label: 12.34 EUR" line, in signed cents.
        """
        texte_du_montant = ligne_du_ticket.split(": ")[-1].replace(" EUR", "")
        return int(round(Decimal(texte_du_montant) * 100))

    def test_ticket_x_broker_en_panne_message_clair_pas_d_erreur_500(self):
        """
        Une vente en espèces, puis le ticket X demandé alors que le broker de Celery
        est en panne (`OperationalError`) : la route ne tombe pas en erreur 500, elle
        répond 503 avec un message clair.
        / Broker down: the X ticket route answers 503 with a clear message, no 500.
        """
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        imprimante_du_terminal = Printer.objects.create(
            name='Imprimante broker en panne', printer_type=Printer.MOCK,
        )

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
                    URL_DU_TICKET_X, data={'uuid_pv': str(self.point_de_vente.uuid)}
                )

        assert reponse.status_code == 503
        assert "Le ticket X n&#x27;a pas pu être envoyé" in reponse.content.decode()

    def test_ticket_x_ne_montre_que_les_ventes_d_apres_la_j(self):
        """
        Trois jus en espèces (1050), la J, puis une bière en CB (500). Le ticket X ne
        porte que la bière : une ligne de 500, un total de 500.
        / Sale before the J, then one after: the X ticket shows only the one after.
        """
        self._vendre(self.tarif_du_jus, 3, 350, PaymentMethod.CASH)
        self._cloturer_la_journee()
        self._vendre(self.tarif_de_la_biere, 1, 500, PaymentMethod.CC)

        ticket = self._imprimer_le_ticket_x()

        assert self._montants_des_lignes(ticket) == [500]
        assert ticket['total']['amount'] == 500

    # ------------------------------------------------------------------
    # Récapitulatif en cours
    # / Current recap
    # ------------------------------------------------------------------

    def test_recap_en_cours_chiffre_affaires_reglements_et_tiroir(self):
        """
        Le décor du calcul à la main. Le récapitulatif montre les sections du rapport
        mises en forme par la présentation partagée :
        - chiffre d'affaires : 12,00 € ;
        - règlements : espèces 7,00 €, CB 5,00 €, et la ligne « Total argent » de la
          présentation (12,00 €) ;
        - caisse espèces, une cellule par ligne, montants signés : fond 50,00 €,
          espèces reçues 7,00 €, espèces rendues −2,00 €, corrections 0,00 €,
          sorties de caisse −3,00 €, solde théorique 52,00 €.
        / The recap shows the report sections formatted by the shared presentation.
        """
        self._une_journee_close_puis_le_service_en_cours()

        reponse = self.client_http.get(URL_DU_RECAP_EN_COURS)

        page = reponse.content.decode()
        assert reponse.status_code == 200, page[:400]
        texte_du_chiffre_d_affaires, _attributs = lire_l_element(
            page, 'recap-chiffre-affaires'
        )
        assert euros('12,00') in texte_du_chiffre_d_affaires

        texte_des_reglements, _attributs = lire_l_element(page, 'recap-reglements')
        assert euros('7,00') in texte_des_reglements
        assert euros('5,00') in texte_des_reglements
        assert 'Total argent' in texte_des_reglements

        # Les cellules du tiroir, lues une à une : « 2,00 € » est contenu dans
        # « 52,00 € », chercher un texte dans la section ne prouverait rien.
        # / The drawer cells, read one by one: "2,00 €" is inside "52,00 €".
        assert self._lignes_du_tiroir_du_recap(page) == [
            ('Fond de caisse', euros('50,00')),
            ('Espèces reçues', euros('7,00')),
            ('Espèces rendues', moins_euros('2,00')),
            ('Corrections', euros('0,00')),
            ('Sorties de caisse', moins_euros('3,00')),
            ('Solde théorique', euros('52,00')),
        ]

    def _lignes_du_tiroir_du_recap(self, page):
        """
        Les lignes (libellé, montant) du tableau de la section « caisse espèces » du
        récapitulatif (`data-testid="recap-caisse-especes"`), lues cellule par
        cellule.
        / The (label, amount) rows of the recap's cash drawer table, cell by cell.
        """
        section_du_tiroir = re.search(
            r'data-testid="recap-caisse-especes".*?</section>', page, re.DOTALL
        )
        assert section_du_tiroir is not None, page[:400]
        return re.findall(
            r'<tr>\s*<td>([^<]*)</td>\s*<td class="num">([^<]*)</td>\s*</tr>',
            section_du_tiroir.group(0),
        )

    def test_recap_en_cours_section_repliee_titre_lu_une_seule_fois(self):
        """
        Une section repliée du récapitulatif (`<details>`) porte son titre dans le
        `<summary>`, qui nomme la section (id « <testid>-titre ») ; la section incluse
        ne le répète pas dans un `<h3>` : un lecteur d'écran lit le titre une fois.
        / A folded section carries its title in the <summary> only.
        """
        self._une_journee_close_puis_le_service_en_cours()

        reponse = self.client_http.get(URL_DU_RECAP_EN_COURS)

        page = reponse.content.decode()
        assert reponse.status_code == 200, page[:400]
        testids_des_sections_repliees = re.findall(
            r'data-testid="(recap-[a-z-]+)-repliee"', page
        )
        assert testids_des_sections_repliees, "Aucune section repliée dans le récap."
        for testid_de_la_section in testids_des_sections_repliees:
            assert f'<summary id="{testid_de_la_section}-titre">' in page
            assert page.count(f'id="{testid_de_la_section}-titre"') == 1

    def test_recap_en_cours_phrase_de_reconciliation(self):
        """
        Le décor du calcul à la main. Le récapitulatif écrit la phrase de
        réconciliation du rapport : argent reçu 10,00 € = ventes payées en argent
        12,00 € + recharges 0,00 € − remboursements 0,00 € − cartes vidées 2,00 €
        + écarts d'encaissement 0,00 €.
        / The recap writes the report's reconciliation sentence.
        """
        self._une_journee_close_puis_le_service_en_cours()

        reponse = self.client_http.get(URL_DU_RECAP_EN_COURS)

        page = reponse.content.decode()
        assert reponse.status_code == 200, page[:400]
        texte_de_la_phrase, _attributs = lire_l_element(
            page, 'recap-reconciliation-phrase'
        )
        phrase_attendue = (
            f"Argent reçu {euros('10,00')} = ventes payées en argent {euros('12,00')} "
            f"+ recharges {euros('0,00')} {SIGNE_MOINS} remboursements {euros('0,00')} "
            f"{SIGNE_MOINS} cartes vidées {euros('2,00')} "
            f"+ écarts d'encaissement {euros('0,00')}"
        )
        assert texte_de_la_phrase == phrase_attendue

    def test_recap_en_cours_ne_montre_que_les_ventes_d_apres_la_j(self):
        """
        Trois jus en espèces (10,50 €), la J, puis une bière en CB (5,00 €). Le
        chiffre d'affaires du récapitulatif vaut 5,00 €, et 10,50 € n'apparaît nulle
        part sur l'écran.
        / Sale before the J, then one after: the recap shows only the one after.
        """
        self._vendre(self.tarif_du_jus, 3, 350, PaymentMethod.CASH)
        self._cloturer_la_journee()
        self._vendre(self.tarif_de_la_biere, 1, 500, PaymentMethod.CC)

        reponse = self.client_http.get(URL_DU_RECAP_EN_COURS)

        page = reponse.content.decode()
        assert reponse.status_code == 200, page[:400]
        texte_du_chiffre_d_affaires, _attributs = lire_l_element(
            page, 'recap-chiffre-affaires'
        )
        assert euros('5,00') in texte_du_chiffre_d_affaires
        assert euros('10,50') not in page

    def test_recap_en_cours_nomme_le_point_de_vente_des_ventes(self):
        """
        Une bière en CB au comptoir du test, sans J : le chiffre d'affaires par
        journal du récapitulatif nomme le point de vente (« Comptoir service en
        cours »), avec 5,00 €.
        / The recap's revenue by journal names the sale's point of sale.
        """
        self._vendre(self.tarif_de_la_biere, 1, 500, PaymentMethod.CC)

        reponse = self.client_http.get(URL_DU_RECAP_EN_COURS)

        page = reponse.content.decode()
        assert reponse.status_code == 200, page[:400]
        texte_du_chiffre_d_affaires, _attributs = lire_l_element(
            page, 'recap-chiffre-affaires'
        )
        assert self.point_de_vente.name in texte_du_chiffre_d_affaires
        assert euros('5,00') in texte_du_chiffre_d_affaires

    def test_recap_en_cours_aucune_vente_depuis_la_j(self):
        """
        Une vente, la J, rien depuis : le récapitulatif dit « aucune vente » (pas de
        service en cours).
        / A sale, the J, nothing since: the recap says "no sale".
        """
        self._vendre(self.tarif_du_jus, 1, 350, PaymentMethod.CASH)
        self._cloturer_la_journee()

        reponse = self.client_http.get(URL_DU_RECAP_EN_COURS)

        page = reponse.content.decode()
        assert reponse.status_code == 200, page[:400]
        assert 'data-testid="recap-aucune-vente"' in page

    # ------------------------------------------------------------------
    # Sortie de caisse
    # / Cash withdrawal
    # ------------------------------------------------------------------

    def test_sortie_de_caisse_lignes_du_tiroir_qui_s_additionnent(self):
        """
        Le décor du calcul à la main. L'écran de sortie de caisse montre les lignes
        du tiroir, dans l'ordre, signées comme le ticket X (l'argent qui sort est
        négatif) : fond 50,00 €, espèces reçues 7,00 €, espèces rendues −2,00 €,
        corrections 0,00 €, sorties de caisse −3,00 €, solde théorique 52,00 €.
        Elles s'additionnent : 50 + 7 − 2 + 0 − 3 = 52. Le formulaire porte les
        espèces nettes du service pour son contrôle : `data-especes` = 5200 − 5000
        = 200.
        / The cash withdrawal screen shows the drawer lines, in order, adding up; the
        form carries the net cash (200) for its check.
        """
        self._une_journee_close_puis_le_service_en_cours()

        reponse = self.client_http.get(
            f'{URL_DE_LA_SORTIE_DE_CAISSE}?uuid_pv={self.point_de_vente.uuid}'
        )

        page = reponse.content.decode()
        assert reponse.status_code == 200, page[:400]
        lignes_affichees = re.findall(
            r'data-testid="sortie-tiroir-ligne"[^>]*>\s*<span>([^<]*)</span>\s*'
            r'<b>([^<]*)</b>',
            page,
        )
        assert lignes_affichees == [
            ("Fond de caisse", euros("50,00")),
            ("Espèces reçues", euros("7,00")),
            ("Espèces rendues", moins_euros("2,00")),
            ("Corrections", euros("0,00")),
            ("Sorties de caisse", moins_euros("3,00")),
            ("Solde théorique", euros("52,00")),
        ]
        assert 'data-fond="5000"' in page
        assert 'data-especes="200"' in page
        # Les lignes affichées au-dessus du solde s'additionnent en solde.
        # / The displayed lines above the balance add up to it.
        montants_affiches = []
        for _libelle, texte_du_montant in lignes_affichees:
            montants_affiches.append(self._centimes_d_un_montant_affiche(texte_du_montant))
        assert sum(montants_affiches[:-1]) == montants_affiches[-1]

    def test_sortie_de_caisse_apres_la_j_et_avant_toute_vente_comptee_tout_de_suite(
        self,
    ):
        """
        Trois jus en espèces, la J, puis une sortie de caisse de 3,00 € AVANT toute
        vente. Le tiroir commence à la fin de la J, même sans vente : l'écran de
        sortie montre la sortie et le solde théorique 50,00 − 3,00 = 47,00 €, et le
        formulaire porte `data-especes` = 4700 − 5000 = −300 (le contrôle du
        formulaire ne laisse pas retirer une deuxième fois le même argent).
        / A withdrawal after the J and before any sale counts at once: balance
        47.00 €, data-especes −300.
        """
        self._vendre(self.tarif_du_jus, 3, 350, PaymentMethod.CASH)
        self._cloturer_la_journee()
        SortieCaisse.objects.create(
            point_de_vente=self.point_de_vente,
            operateur=self.admin,
            montant_total=300,
            ventilation={"100": 3},
        )

        reponse = self.client_http.get(
            f'{URL_DE_LA_SORTIE_DE_CAISSE}?uuid_pv={self.point_de_vente.uuid}'
        )

        page = reponse.content.decode()
        assert reponse.status_code == 200, page[:400]
        lignes_affichees = re.findall(
            r'data-testid="sortie-tiroir-ligne"[^>]*>\s*<span>([^<]*)</span>\s*'
            r'<b>([^<]*)</b>',
            page,
        )
        assert ("Sorties de caisse", moins_euros("3,00")) in lignes_affichees
        assert lignes_affichees[-1] == ("Solde théorique", euros("47,00"))
        assert 'data-especes="-300"' in page

    def _centimes_d_un_montant_affiche(self, texte_du_montant):
        """
        « 1 234,50 € » (espaces insécables) → 123450 centimes.
        / A French-formatted amount → cents.
        """
        texte_sans_euro = texte_du_montant.replace("€", "").replace(chr(0xA0), "")
        texte_avec_point = texte_sans_euro.replace(chr(0x2212), "-").replace(",", ".")
        return int(round(Decimal(texte_avec_point.strip()) * 100))
