"""
L'écran « Ventes » de la caisse (récapitulatif en cours) et le rapport temps réel de
l'admin montrent les MÊMES chiffres pour le même service.
/ The register's "Sales" screen (current recap) and the admin's real-time report show
the SAME figures for the same service.

LOCALISATION : tests/pytest/test_recap_en_cours_coherence_admin.py

RÈGLES MÉTIER TESTÉES
- L'écran « Ventes » (`laboutik/views.py` `recap_en_cours`) garde la forme de la
  maquette : Total, fond de caisse et solde, « Par moyen de paiement », « Par point de
  vente », TVA, « Offerts (hors argent) », et les historiques (« Historique de vente »
  par article, « Synthèse par moyen »). Le rapport complet reste dans l'admin.
- Chaque chiffre de l'écran est LU dans le rapport des ventes unique
  (`comptabilite.rapport.RapportDesVentes`), sur la même période (depuis la dernière
  clôture) et le même périmètre (toutes origines) que le rapport temps réel de
  l'admin (`comptabilite/admin.py` `rapport_temps_reel`). Les deux écrivent les
  montants par la même fonction (`euros_a_la_francaise`) : le texte de chaque total
  de l'écran est celui de l'admin.
- « Par point de vente » (`RapportDesVentes.chiffre_affaires_par_point_de_vente`) :
  le chiffre d'affaires par point de vente de la vente ; les ventes sans point de
  vente (admin, en ligne) sous « Sans point de vente » ; les lignes additionnent le
  chiffre d'affaires TTC.
/ Each figure of the screen is read in the single sales report, same period and scope
as the admin's real-time report; both write amounts with the same formatter.

LE JEU DE VENTES (écrit PAR LE SERVICE DE VENTE, `fabriques_vente.py`)
Au « Comptoir cohérence » (point de vente de la caisse), fond de caisse 50,00 € :
1. deux jus à 3,50 € en espèces (700) ;
2. une bière à 5,00 € en CB (500), puis corrigée en espèces (vente CORRECTION au
   comptoir : CB −500, espèces +500) ;
3. une bière à 5,00 € en monnaie locale (500, cashless) ;
4. un jus offert par le bouton OFFRIR (net 0, valeur catalogue 3,50 €) ;
5. une pesée : 0,350 kg de comté à 20,00 €/kg = 700, en espèces ;
6. un gobelet consigné 1,00 € en espèces (100), puis rendu (avoir, −100 espèces) ;
7. une recharge de 10,00 € en espèces (hors chiffre d'affaires) ;
8. une sortie de caisse de 3,00 € (300).
À la « Tireuse cohérence » : un tirage de 0,500 L à 8,00 €/L = 400, en monnaie
locale. Dans l'admin (sans point de vente) : l'avoir d'un jus de la vente 1, rendu
en espèces (−350).

D'OÙ VIENNENT LES VALEURS ATTENDUES (calcul à la main)
- Chiffre d'affaires TTC : 700 + 500 + 500 + 0 + 700 + 100 − 100 + 400 − 350 = 2450
  (« 24,50 € ») ; la recharge n'en est pas.
- Par moyen : espèces 700 + 700 + 100 − 100 − 350 + 500 (correction) = 1550 ; CB
  500 − 500 = 0 ; monnaie locale 500 + 400 = 900. Somme 2450.
- Par point de vente : comptoir 700 + 500 + 500 + 0 + 700 + 100 − 100 = 2400 ;
  tireuse 400 ; sans point de vente −350. Somme 2450.
- Recharges par moyen : espèces 1000.
- Quantités : le comté « 0,350 kg », le tirage « 0,50 L » (Q-H4).
- Les autres textes attendus sont ceux de l'admin, lus dans son contexte : c'est la
  cohérence elle-même qui est testée.
/ Hand-computed: revenue 2450, by method cash 1550 / card 0 / local 900, by point of
sale 2400 / 400 / −350; other expected texts are the admin's.

SCHÉMA DÉDIÉ : le lieu ne contient que les ventes du test (`FastTenantTestCase`),
chaque test annule sa transaction. Le rendu complet d'Unfold plante en test : la vue
de l'admin est appelée avec un `render` bouchonné, qui garde son contexte.
/ Dedicated schema; the admin view is called with a stubbed render.

Lancer / Run : make test ARGS="tests/pytest/test_recap_en_cours_coherence_admin.py"
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import html  # noqa: E402
import re  # noqa: E402
from datetime import timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest.mock import patch  # noqa: E402

from django.contrib.messages.storage.fallback import FallbackStorage  # noqa: E402
from django.contrib.sessions.middleware import SessionMiddleware  # noqa: E402
from django.db import connection  # noqa: E402
from django.http import HttpResponse  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.utils import timezone  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

from Administration.admin.site import staff_admin_site  # noqa: E402
from AuthBillet.models import TibilletUser, Wallet  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Configuration,
    PaymentMethod,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Vente  # noqa: E402
from BaseBillet.services_vente import (  # noqa: E402
    ajouter_reglement,
    ecrire_la_vente_d_avoir_d_une_ligne,
    encaisser_vente,
    ouvrir_vente,
)
from comptabilite.admin import ClotureCaisseAdmin  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from comptabilite.rapport import (  # noqa: E402
    CLE_SANS_POINT_DE_VENTE,
    RapportDesVentes,
)
from fabriques_ecran import (  # noqa: E402
    euros,
    lire_l_element,
    moins_euros,
    texte_sans_espaces_en_trop,
    textes_des_elements,
)
from fabriques_panier import identifiant_unique  # noqa: E402
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from fedow_core.models import Asset  # noqa: E402
from laboutik.models import LaboutikConfiguration, PointDeVente, SortieCaisse  # noqa: E402

URL_DU_RECAP_EN_COURS = "/laboutik/caisse/recap-en-cours/"
URL_DU_RAPPORT_TEMPS_REEL = "/admin/comptabilite/cloturecaisse/rapport-temps-reel/"
FOND_DE_CAISSE_EN_CENTIMES = 5000


def lignes_d_un_tableau_de_la_page(page, testid):
    """
    Les rangées du corps d'un tableau de la page (`data-testid`), chaque rangée la
    liste des textes de ses cellules (entités décodées, espaces ramenées à une seule).
    / The body rows of a page table, as lists of cell texts.
    """
    tableau = re.search(
        rf'data-testid="{testid}".*?<tbody[^>]*>(.*?)</table>', page, re.DOTALL
    )
    assert tableau is not None, f"Tableau {testid} absent de la page."
    rangees = []
    for rangee in re.findall(r"<tr[^>]*>(.*?)</tr>", tableau.group(1), re.DOTALL):
        cellules = []
        for cellule in re.findall(r"<td[^>]*>(.*?)</td>", rangee, re.DOTALL):
            cellules.append(texte_sans_espaces_en_trop(html.unescape(cellule)))
        rangees.append(cellules)
    return rangees


def lignes_d_un_tableau_de_l_admin(sections_de_l_admin, testid):
    """
    Les rangées d'un tableau du rapport temps réel de l'admin (le `testid` du
    tableau dans `sections_pour_affichage`), chaque rangée la liste des textes de
    ses cellules, espaces ramenées à une seule.
    / The rows of an admin report table, as lists of cell texts.
    """
    for section in sections_de_l_admin:
        for tableau in section["tableaux"]:
            if tableau["testid"] == testid:
                rangees = []
                for ligne in tableau["lignes"]:
                    cellules = []
                    for cellule in ligne:
                        cellules.append(texte_sans_espaces_en_trop(cellule["texte"]))
                    rangees.append(cellules)
                return rangees
    raise AssertionError(f"Tableau {testid} absent du rapport de l'admin.")


def texte(montant_attendu):
    """Un montant attendu, espaces ramenées à une seule. / Collapsed spaces."""
    return texte_sans_espaces_en_trop(montant_attendu)


class TestRecapEnCoursCoherentAvecLAdmin(FastTenantTestCase):
    """
    L'écran « Ventes » et le rapport temps réel de l'admin, sur le même jeu de ventes.
    / The "Sales" screen and the admin's real-time report, on the same sales.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_recap_coherence"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-recap-coherence.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test recap coherence"

    def setUp(self):
        """
        Le lieu (Paris, aucun e-mail de rapport), le fond de caisse, les tarifs, le
        comptoir, la tireuse, une monnaie locale et un administrateur connecté.
        / The venue, the cash float, prices, counter, tap, local currency, an admin.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Toutes les valeurs sont écrites ici : le cache garde celles du test d'avant.
        # / Every value is written here: the cache keeps the previous test's.
        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.rapport_emails = ""
        configuration.rapport_periodicite = Configuration.PERIODICITE_NONE
        configuration.save()

        # Le singleton de la caisse (tests/PIEGES.md 9.86) : clé des empreintes et fond.
        # Le fond est remis à 0 à la fin : le cache survit à l'annulation.
        # / The register singleton: fingerprint key and cash float, reset at the end.
        configuration_de_la_caisse = LaboutikConfiguration.get_solo()
        configuration_de_la_caisse.fond_de_caisse = FOND_DE_CAISSE_EN_CENTIMES
        configuration_de_la_caisse.save()
        self.addCleanup(self._remettre_le_fond_de_caisse_a_zero)

        self.tarif_du_jus = creer_tarif_vendu(nom="Jus", prix_en_euros="3.50")
        self.tarif_de_la_biere = creer_tarif_vendu(nom="Biere", prix_en_euros="5.00")
        self.tarif_du_comte = creer_tarif_vendu(nom="Comte", prix_en_euros="20.00")
        self.tarif_du_fut = creer_tarif_vendu(
            nom="Fut", prix_en_euros="8.00", categorie_article=Product.FUT
        )
        self.tarif_du_gobelet = creer_tarif_vendu(
            nom="Gobelet", prix_en_euros="1.00", methode_caisse=Product.VENTE
        )
        self.tarif_du_retour = creer_tarif_vendu(
            nom="Retour gobelet",
            prix_en_euros="-1.00",
            methode_caisse=Product.RETOUR_CONSIGNE,
        )
        produit_de_retour = self.tarif_du_retour.productsold.product
        produit_de_retour.consigne_remboursee = self.tarif_du_gobelet.productsold.product
        produit_de_retour.save()
        self.tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="10.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )

        self.comptoir = PointDeVente.objects.create(
            name="Comptoir cohérence",
            comportement=PointDeVente.DIRECT,
            hidden=True,
        )
        self.tireuse = PointDeVente.objects.create(
            name="Tireuse cohérence", hidden=True
        )

        portefeuille_d_origine = Wallet.objects.create(
            name=f"Portefeuille recap coherence {identifiant_unique()}"
        )
        self.monnaie_locale = Asset.objects.create(
            name="Monnaie locale cohérence",
            currency_code="EUR",
            category=Asset.TLF,
            tenant_origin=self.tenant,
            wallet_origin=portefeuille_d_origine,
        )

        # `TibilletUser` vit dans le schéma public ; il est annulé avec le test.
        # / TibilletUser lives in the public schema; rolled back with the test.
        email_de_l_admin = f"admin-recap-coherence-{identifiant_unique()}@tibillet.localhost"
        self.administrateur = TibilletUser.objects.create(
            email=email_de_l_admin,
            username=email_de_l_admin,
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        self.administrateur.client_admin.add(self.tenant)
        self.client_http = TenantClient(self.tenant, HTTP_ACCEPT_LANGUAGE="fr")
        self.client_http.force_login(self.administrateur)

    def _remettre_le_fond_de_caisse_a_zero(self):
        """Le fond de caisse revient au défaut. / Cash float back to default."""
        configuration_de_la_caisse = LaboutikConfiguration.get_solo()
        configuration_de_la_caisse.fond_de_caisse = 0
        configuration_de_la_caisse.save()

    # ------------------------------------------------------------------
    # Le jeu de ventes
    # / The sales
    # ------------------------------------------------------------------

    def _vendre(self, articles, reglements, point_de_vente=None, origine=None):
        """
        Une vente réglée, écrite par le service, au comptoir par défaut.
        / A settled sale written by the service, at the counter by default.
        """
        if point_de_vente is None:
            point_de_vente = self.comptoir
        if origine is None:
            origine = SaleOrigin.LABOUTIK
        vente = fabriquer_vente_encaissee(
            origine=origine,
            point_de_vente=point_de_vente,
            articles=articles,
            reglements=reglements,
        )
        verifier_egalites(vente)
        return vente

    def _article(self, tarif_vendu, quantite, prix_unitaire, taux_tva="20", **autres):
        """Un article pour `fabriquer_vente_encaissee`. / An item for the factory."""
        article = {
            "pricesold": tarif_vendu,
            "quantite": Decimal(quantite),
            "prix_unitaire": prix_unitaire,
            "taux_tva": Decimal(taux_tva),
        }
        article.update(autres)
        return article

    def _le_jeu_de_ventes(self):
        """
        Le jeu de ventes de la docstring du module.
        / The module docstring's sales.
        """
        # 1. Deux jus en espèces. / Two juices in cash.
        vente_des_jus = self._vendre(
            [self._article(self.tarif_du_jus, "2", 350)],
            [{"moyen": PaymentMethod.CASH, "montant": 700}],
        )

        # 2. Une bière en CB, corrigée en espèces au comptoir.
        # / A beer by card, corrected to cash at the counter.
        vente_en_cb = self._vendre(
            [self._article(self.tarif_de_la_biere, "1", 500)],
            [{"moyen": PaymentMethod.CC, "montant": 500}],
        )
        correction = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.CORRECTION,
            point_de_vente=self.comptoir,
            vente_liee=vente_en_cb,
        )
        ajouter_reglement(correction, moyen=PaymentMethod.CC, montant=-500)
        ajouter_reglement(correction, moyen=PaymentMethod.CASH, montant=500)
        verifier_egalites(encaisser_vente(correction))

        # 3. Une bière en monnaie locale (cashless). / A beer in local currency.
        self._vendre(
            [self._article(self.tarif_de_la_biere, "1", 500)],
            [
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 500,
                    "asset": self.monnaie_locale.uuid,
                }
            ],
        )

        # 4. Un jus offert (bouton OFFRIR) : le service ajoute le règlement offert.
        # / A gifted juice: the service adds the offered payment.
        self._vendre(
            [self._article(self.tarif_du_jus, "1", 350, offert_en_totalite=True)],
            [],
        )

        # 5. Une pesée : 0,350 kg de comté à 20,00 €/kg, en espèces.
        # / A weighing: 0.350 kg of cheese at 20.00 €/kg, in cash.
        self._vendre(
            [
                self._article(
                    self.tarif_du_comte, "0.350", 2000, weight_quantity=350
                )
            ],
            [{"moyen": PaymentMethod.CASH, "montant": 700}],
        )

        # 6. Un gobelet consigné, puis rendu (avoir au comptoir).
        # / A deposit cup, then returned (credit note at the counter).
        self._vendre(
            [self._article(self.tarif_du_gobelet, "1", 100)],
            [{"moyen": PaymentMethod.CASH, "montant": 100}],
        )
        vente_du_retour = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.AVOIR,
            point_de_vente=self.comptoir,
            articles=[self._article(self.tarif_du_retour, "1", -100)],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": -100}],
        )
        verifier_egalites(vente_du_retour)

        # 7. Une recharge de 10,00 € en espèces. / A 10.00 € top-up in cash.
        self._vendre(
            [self._article(self.tarif_de_la_recharge, "1", 1000, taux_tva="0")],
            [{"moyen": PaymentMethod.CASH, "montant": 1000}],
        )

        # 8. Un tirage de 0,500 L à 8,00 €/L, en monnaie locale, à la tireuse.
        # / A 0.500 L pour at 8.00 €/L, in local currency, at the tap.
        self._vendre(
            [self._article(self.tarif_du_fut, "0.500", 800, weight_quantity=50)],
            [
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": 400,
                    "asset": self.monnaie_locale.uuid,
                }
            ],
            point_de_vente=self.tireuse,
            origine=SaleOrigin.TIREUSE,
        )

        # 9. L'avoir d'un jus, dans l'admin, rendu en espèces (sans point de vente).
        # / A juice credit note, in the admin, refunded in cash (no point of sale).
        ligne_des_jus = vente_des_jus.articles.first()
        article_d_avoir = ecrire_la_vente_d_avoir_d_une_ligne(
            ligne_des_jus,
            quantite=Decimal("1"),
            moyen_rembourse=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
        )
        verifier_egalites(Vente.objects.get(pk=article_d_avoir.vente_id))

        # 10. Une sortie de caisse de 3,00 €. / A 3.00 € cash withdrawal.
        SortieCaisse.objects.create(
            point_de_vente=self.comptoir,
            operateur=self.administrateur,
            montant_total=300,
            ventilation={"100": 3},
        )

    # ------------------------------------------------------------------
    # Les deux écrans
    # / The two screens
    # ------------------------------------------------------------------

    def _page_du_recap(self, vue=""):
        """
        L'écran « Ventes » (page complète), ou un historique (`vue`) rendu seul,
        comme le bouton le demande (cible HTMX « detail-contenu »).
        / The Sales screen, or a history rendered alone like its button asks.
        """
        if vue:
            reponse = self.client_http.get(
                f"{URL_DU_RECAP_EN_COURS}?vue={vue}",
                HTTP_HX_REQUEST="true",
                HTTP_HX_TARGET="detail-contenu",
            )
        else:
            reponse = self.client_http.get(URL_DU_RECAP_EN_COURS)
        page = reponse.content.decode()
        assert reponse.status_code == 200, page[:400]
        return page

    def _sections_du_rapport_de_l_admin(self):
        """
        Le rapport temps réel de l'admin, bornes par défaut (le service en cours) :
        les sections passées au gabarit (`sections_pour_affichage`).
        / The admin's real-time report with default bounds: the template sections.
        """
        contexte_capture = {}

        def rendu_bouchonne(requete, nom_du_gabarit, contexte=None, *args, **kwargs):
            contexte_capture.update(contexte)
            return HttpResponse("bouchon")

        requete = RequestFactory().get(URL_DU_RAPPORT_TEMPS_REEL)
        requete.user = self.administrateur
        SessionMiddleware(lambda requete_recue: None).process_request(requete)
        requete.session.save()
        requete._messages = FallbackStorage(requete)
        admin_des_clotures = ClotureCaisseAdmin(ClotureCaisse, staff_admin_site)
        with patch("django.shortcuts.render", side_effect=rendu_bouchonne):
            admin_des_clotures.rapport_temps_reel(requete)
        return contexte_capture["sections"]

    # ------------------------------------------------------------------
    # Les tests
    # / The tests
    # ------------------------------------------------------------------

    def test_chaque_total_de_l_ecran_ventes_est_celui_de_l_admin(self):
        """
        Le jeu de ventes. Chaque total de l'écran « Ventes » est le texte du même
        total du rapport temps réel de l'admin : Total, par moyen de paiement, TVA
        par taux, fond de caisse et mouvements du tiroir, solde, offerts.
        / Every total of the Sales screen is the admin's text for the same total.
        """
        self._le_jeu_de_ventes()

        page = self._page_du_recap()
        sections_de_l_admin = self._sections_du_rapport_de_l_admin()

        # Total = chiffre d'affaires TTC (2450, calcul à la main), comme l'admin.
        # / Total = revenue incl. tax, like the admin.
        texte_du_total, _attributs = lire_l_element(page, "recap-total")
        totaux_de_l_admin = lignes_d_un_tableau_de_l_admin(
            sections_de_l_admin, "chiffre-affaires-totaux"
        )
        assert texte_sans_espaces_en_trop(texte_du_total) == texte(euros("24,50"))
        assert totaux_de_l_admin[0] == [
            "Chiffre d'affaires TTC",
            texte_sans_espaces_en_trop(texte_du_total),
        ]

        # Par moyen de paiement : mêmes lignes, même ordre (calcul à la main).
        # / By payment method: same rows, same order.
        lignes_par_moyen = lignes_d_un_tableau_de_la_page(page, "recap-totaux-moyen")
        assert lignes_par_moyen == lignes_d_un_tableau_de_l_admin(
            sections_de_l_admin, "chiffre-affaires-par-moyen"
        )
        assert lignes_par_moyen == [
            ["Espèces", texte(euros("15,50"))],
            ["Carte bancaire", texte(euros("0,00"))],
            [lignes_par_moyen[2][0], texte(euros("9,00"))],
        ]

        # TVA par taux : la caisse écrit Taux, HT, TVA, TTC ; l'admin Taux, TTC, HT, TVA.
        # / VAT by rate: same figures, columns in another order.
        lignes_de_tva_de_l_admin = []
        for taux, ttc, ht, tva in lignes_d_un_tableau_de_l_admin(
            sections_de_l_admin, "chiffre-affaires-par-taux"
        ):
            lignes_de_tva_de_l_admin.append([taux, ht, tva, ttc])
        assert lignes_d_un_tableau_de_la_page(page, "recap-tva") == lignes_de_tva_de_l_admin

        # Le tiroir : fond, mouvements non nuls, solde, comme les lignes de l'admin.
        # / The drawer: float, non-zero movements, balance, like the admin's rows.
        lignes_du_tiroir_de_l_admin = lignes_d_un_tableau_de_l_admin(
            sections_de_l_admin, "caisse-especes"
        )
        texte_du_fond, _attributs = lire_l_element(page, "recap-fond-de-caisse")
        texte_du_solde, _attributs = lire_l_element(page, "recap-solde-du-tiroir")
        assert lignes_du_tiroir_de_l_admin[0] == [
            "Fond de caisse",
            texte_sans_espaces_en_trop(texte_du_fond),
        ]
        assert lignes_du_tiroir_de_l_admin[-1] == [
            "Solde théorique",
            texte_sans_espaces_en_trop(texte_du_solde),
        ]
        mouvements_attendus = []
        for libelle, montant in lignes_du_tiroir_de_l_admin[1:-1]:
            if montant != texte(euros("0,00")):
                mouvements_attendus.append(f"{libelle} · {montant}")
        assert textes_des_elements(page, "recap-mouvement-du-tiroir") == (
            mouvements_attendus
        )
        assert texte(moins_euros("3,00")) in mouvements_attendus[-1]

        # Offerts : article, quantité, valeur catalogue, comme l'admin.
        # / Gifts: item, quantity, catalogue value, like the admin.
        offerts_de_l_admin = []
        for produit, quantite, valeur, _cout in lignes_d_un_tableau_de_l_admin(
            sections_de_l_admin, "offerts-par-produit"
        ):
            offerts_de_l_admin.append([produit, quantite, valeur])
        assert lignes_d_un_tableau_de_la_page(page, "recap-offerts") == offerts_de_l_admin
        assert offerts_de_l_admin[0][1:] == ["1", texte(euros("3,50"))]

    def test_par_point_de_vente_additionne_le_total(self):
        """
        Le jeu de ventes. « Par point de vente » : comptoir 24,00 €, tireuse 4,00 €,
        les ventes de l'admin sous « Sans point de vente » (−3,50 €), à la fin.
        Somme 24,50 € = le Total.
        / By point of sale: counter, tap, then "without point of sale".
        """
        self._le_jeu_de_ventes()

        page = self._page_du_recap()

        assert lignes_d_un_tableau_de_la_page(page, "recap-par-pv") == [
            ["Comptoir cohérence", texte(euros("24,00"))],
            ["Tireuse cohérence", texte(euros("4,00"))],
            ["Sans point de vente", texte(moins_euros("3,50"))],
        ]

    def test_historique_par_article_est_le_detail_de_l_admin(self):
        """
        Le jeu de ventes. L'historique de vente par article (une ligne par produit :
        nom, quantité, total) est le détail des ventes par produit de l'admin
        (produit, quantité, TTC). La pesée s'écrit « 0,350 kg », le tirage « 0,50 L ».
        / The by-item history is the admin's sales detail by product.
        """
        self._le_jeu_de_ventes()

        page = self._page_du_recap(vue="detail_articles")
        sections_de_l_admin = self._sections_du_rapport_de_l_admin()

        articles_de_l_admin = []
        for (
            _categorie,
            produit,
            quantite,
            ttc,
            _ht,
            _offert,
            _cout,
        ) in lignes_d_un_tableau_de_l_admin(sections_de_l_admin, "detail-ventes-par-produit"):
            articles_de_l_admin.append([produit, quantite, ttc])

        # Les rangées de catégorie ont deux cellules (la première sur deux colonnes) :
        # seules les rangées d'article en ont trois.
        # / Category rows have two cells; article rows three.
        articles_de_l_ecran = []
        for rangee in lignes_d_un_tableau_de_la_page(page, "recap-detail-articles"):
            if len(rangee) == 3:
                articles_de_l_ecran.append(rangee)
        assert sorted(articles_de_l_ecran) == sorted(articles_de_l_admin)

        nom_du_comte = self.tarif_du_comte.productsold.product.name
        nom_du_fut = self.tarif_du_fut.productsold.product.name
        assert [nom_du_comte, "0,350 kg", texte(euros("7,00"))] in articles_de_l_ecran
        assert [nom_du_fut, "0,50 L", texte(euros("4,00"))] in articles_de_l_ecran

    def test_synthese_par_moyen_chiffre_d_affaires_et_recharges_de_l_admin(self):
        """
        Le jeu de ventes. La synthèse par moyen : la ligne « Chiffre d'affaires »
        reprend le chiffre d'affaires par moyen de l'admin, la ligne « Recharges »
        les recharges encaissées par moyen de son annexe (espèces 10,00 €).
        / The synthesis: revenue by method and top-ups by method, like the admin.
        """
        self._le_jeu_de_ventes()

        page = self._page_du_recap(vue="par_moyen")
        sections_de_l_admin = self._sections_du_rapport_de_l_admin()

        lignes_de_la_synthese = lignes_d_un_tableau_de_la_page(
            page, "recap-synthese-operations"
        )
        ligne_du_chiffre_d_affaires = lignes_de_la_synthese[0]
        ligne_des_recharges = lignes_de_la_synthese[1]

        montants_par_moyen_de_l_admin = []
        for _libelle, montant in lignes_d_un_tableau_de_l_admin(
            sections_de_l_admin, "chiffre-affaires-par-moyen"
        ):
            montants_par_moyen_de_l_admin.append(montant)
        assert ligne_du_chiffre_d_affaires == (
            ["Chiffre d'affaires"] + montants_par_moyen_de_l_admin + [texte(euros("24,50"))]
        )

        # Les recharges de l'admin : sa ligne « Recharges encaissées » et ses lignes
        # « dont <moyen> ».
        # / The admin's top-ups: its total row and its "of which <method>" rows.
        recharges_de_l_admin = {}
        for section in sections_de_l_admin:
            for tableau in section["tableaux"]:
                for ligne in tableau["lignes"]:
                    libelle = ligne[0]["texte"]
                    if libelle == "Recharges encaissées" or libelle.startswith("dont Esp"):
                        recharges_de_l_admin[libelle] = texte_sans_espaces_en_trop(
                            ligne[-1]["texte"]
                        )
        assert ligne_des_recharges[0] == "Recharges"
        assert ligne_des_recharges[1] == recharges_de_l_admin["dont Espèces"]
        assert ligne_des_recharges[-1] == recharges_de_l_admin["Recharges encaissées"]
        assert ligne_des_recharges[-1] == texte(euros("10,00"))

    def test_chiffre_affaires_par_point_de_vente_du_rapport(self):
        """
        La méthode publique du rapport : une clé par point de vente (son uuid), les
        ventes sans point de vente sous « sans_point_de_vente » ; la somme des lignes
        vaut le chiffre d'affaires TTC (2450).
        / The report's public method: keys, names, and the rows add up to revenue.
        """
        self._le_jeu_de_ventes()

        maintenant = timezone.now()
        rapport = RapportDesVentes(
            maintenant - timedelta(hours=1), maintenant + timedelta(hours=1)
        )
        par_point_de_vente = rapport.chiffre_affaires_par_point_de_vente()

        assert par_point_de_vente == {
            str(self.comptoir.uuid): {
                "nom": "Comptoir cohérence",
                "total_ttc_en_centimes": 2400,
            },
            str(self.tireuse.uuid): {
                "nom": "Tireuse cohérence",
                "total_ttc_en_centimes": 400,
            },
            CLE_SANS_POINT_DE_VENTE: {
                "nom": "Sans point de vente",
                "total_ttc_en_centimes": -350,
            },
        }
        assert rapport.section_chiffre_affaires()["total_ttc_en_centimes"] == 2450
