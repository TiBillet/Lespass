"""
tests/pytest/test_fec_equilibre.py
La ventilation comptable d'une clôture J (`comptabilite/ventilation.py`) et le FEC
(`comptabilite/fec.py`) : une écriture par journal, équilibrée par construction,
calculée à chaque export avec le plan comptable du moment.
/ The accounting breakdown of a J closure and the FEC: one entry per journal,
balanced by construction, computed at each export with the current chart of accounts.

LOCALISATION : tests/pytest/test_fec_equilibre.py

RÈGLES MÉTIER TESTÉES (fiche F §4 ; fiche E §3 ; tronc D8 bis, D22, D23)
- Une écriture par journal et par J. Le journal d'une vente vient de `journal_pour` :
  le point de vente gagne toujours ; sans point de vente, l'origine.
- Seules les ventes réglées EN EUROS de la plage de la J sont écrites. Une vente en
  points (ou une recharge offerte en points) n'a aucune écriture.
- Débit : un compte par (moyen, monnaie) des règlements d'argent et cashless
  (`compte_pour_reglement`). Jamais l'offert (FREE) ni les points (NM).
- Crédit : les articles du chiffre d'affaires au compte de `compte_pour_article`
  (somme des HT) ; la TVA au compte trouvé PAR SON TAUX (somme des TVA ; un taux 0
  n'écrit pas de TVA) ; les articles hors chiffre d'affaires au compte de
  `compte_pour_article` (somme des TTC).
- Recharge offerte (article de recharge avec une part offerte) : débit 623400, crédit
  419100, sur la part offerte. Jetons cadeau (moyen LG, monnaie TNF du lieu) : débit
  419100 ; l'article payé en jetons au 707900 ; jetons repris au vidage au 623400.
- Les montants sont regroupés par compte dans chaque écriture. Un montant négatif
  (avoir, espèces rendues, écart reçu en moins) passe du côté opposé, en positif.
- Chaque écriture est vérifiée : Σ débits = Σ crédits, sinon refus. Un compte
  manquant : refus. Refus = aucune ligne écrite, aucun fichier téléchargé ; l'admin
  affiche un message d'erreur.
- Le FEC est recalculé à chaque export avec le plan comptable du moment.
- FEC : 18 colonnes, UTF-8 sans BOM, montants à virgule décimale, `EcritureDate` = date
  locale de la première vente de la J (date de début de service), dans le fuseau figé
  dans l'en-tête du rapport de la J. `PieceRef` = numéro de la clôture J. `ValidDate`
  remplie. Nom du fichier à une date locale.
- Le FEC d'une semaine, d'un mois, d'une année = les écritures des J DATÉES dans la
  période (le FEC fait foi par J), avec les mêmes `EcritureNum`.
- Un code journal porté par plusieurs points de vente, ou par un point de vente et un
  journal d'origine (CAISSE, TIREUSE, WEB, ADMIN) : refus, et « Plan complet ? » le
  signale.
- Le nombre de requêtes d'un export ne grandit pas avec le nombre de ventes.
/ Business rules tested: one balanced entry per journal and J, euro sales only,
accounts from the chart rules, VAT by rate, gift top-ups and gift tokens, opposite
side for negative amounts, refusal when unbalanced or an account is missing, FEC
recomputed at each export, dated by the start of service, periods = their dated J.

LE CONTRAT LU PAR CES TESTS
- `comptabilite.ventilation.ventiler_cloture(cloture_j)` : la liste des écritures de
  la J, une par journal. Chaque écriture est un dictionnaire
  {"journal": code journal (texte),
   "lignes": [{"compte": numéro du compte (texte), "libelle": libellé du compte,
               "debit": centimes (entier ≥ 0), "credit": centimes (entier ≥ 0)}]}.
- `comptabilite.ventilation.EcritureDesequilibree` : l'exception levée quand une
  écriture n'est pas équilibrée ; son message, en français, nomme le journal et
  l'écart.
- `laboutik.plan_comptable.CompteComptableManquant` : l'exception levée quand un
  compte manque.
- `comptabilite.fec.generer_fec_cloture(cloture)` : (contenu en octets, nom du
  fichier, type du contenu), pour une J ou pour une H / M / A. Lève les mêmes
  exceptions.
- `laboutik.plan_comptable.compte_de_tva_pour_taux(taux)` : le compte de TVA à ce
  taux, sinon `CompteComptableManquant`.
- `laboutik.plan_comptable.code_journal_du_point_de_vente(point_de_vente)`.
- `comptabilite.admin.ClotureCaisseAdmin.exporter_fec(request, object_id)`.
/ The contract read by these tests.

D'OÙ VIENNENT LES VALEURS ATTENDUES
Les valeurs de la fiche F §6 quand elle en donne (24b) ; le rapport de la J
(`rapport_json`, calculé par `comptabilite/rapport.py`) pour le test 20 ; sinon un
calcul à la main, écrit en commentaire au-dessus de l'assertion, avec la seule formule
d'argent du projet : HT = arrondi_demi_haut(net × 100 / (100 + taux)), TVA = net − HT.
Un jus vaut 350 centimes à 20 % : HT 292, TVA 58. Le plan comptable est celui que la
migration charge dans tout lieu neuf (`laboutik/plan_comptable_par_defaut.py`).
/ Sheet values when given; the J report for test 20; otherwise a hand computation.

L'HEURE
L'heure d'encaissement d'une vente est scellée dans son empreinte : on ne la change
jamais après coup. Chaque vente et chaque clôture se fait à une heure choisie, en
remplaçant `django.utils.timezone.now` pendant l'appel. Les dates sont en 2026, à
Paris (CET, UTC+1, en hiver).
/ Each sale and closure happens at a chosen time by replacing timezone.now.

SCHÉMA DÉDIÉ
Une clôture lit TOUTES les ventes du lieu : il faut un lieu qui ne contient que les
ventes du test (`FastTenantTestCase`). Chaque test annule sa transaction à la fin. Le
singleton `LaboutikConfiguration` est créé en base (tests/PIEGES.md 9.86). La
`Configuration` du lieu est réécrite à chaque test : son cache (django-solo) survit à
l'annulation de la transaction. Les ventes sont écrites PAR LE SERVICE
(`BaseBillet/services_vente.py`, directement ou par `fabriques_vente.py`).
/ Dedicated schema, rolled back after each test; sales written through the service.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-F-rapport-unique.md (§4,
§6 tests 19 à 25b), CHANTIER-05-E-plan-comptable.md (§3), CHANTIER-05-montants-entiers.md
(D8 bis, D22, D23).

Lancer / Run : make test ARGS="tests/pytest/test_fec_equilibre.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import re  # noqa: E402
import uuid  # noqa: E402
from datetime import date, datetime, time  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.contrib import messages  # noqa: E402
from django.contrib.messages.storage.fallback import FallbackStorage  # noqa: E402
from django.contrib.sessions.middleware import SessionMiddleware  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.utils import translation  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402

import comptabilite.tasks  # noqa: E402
from Administration.admin.site import staff_admin_site  # noqa: E402
from AuthBillet.models import TibilletUser, Wallet  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    CategorieProduct,
    Configuration,
    LigneArticle,
    Paiement_stripe,
    PaymentMethod,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement, Vente  # noqa: E402
from BaseBillet.services_vente import (  # noqa: E402
    NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE,
    ajouter_article,
    ajouter_l_article_d_ecart_d_encaissement,
    ajouter_reglement,
    ecrire_la_vente_d_avoir_d_une_ligne,
    encaisser_vente,
    ouvrir_vente,
    tarif_vendu_d_un_produit_systeme,
)
from comptabilite.admin import ClotureCaisseAdmin  # noqa: E402
from comptabilite.fec import generer_fec_cloture  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from comptabilite.ventilation import (  # noqa: E402
    EcritureDesequilibree,
    ventiler_cloture,
)
from fabriques_panier import (  # noqa: E402
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from fedow_core.models import Asset  # noqa: E402
from laboutik.models import (  # noqa: E402
    CompteComptable,
    LaboutikConfiguration,
    MappingMonnaie,
    PointDeVente,
)
from laboutik.plan_comptable import (  # noqa: E402
    LIBELLE_DU_JOURNAL_SANS_POINT_DE_VENTE,
    CompteComptableManquant,
    ce_qui_manque_pour_exporter,
    code_journal_du_point_de_vente,
    compte_de_tva_pour_taux,
)

FUSEAU_DE_PARIS = ZoneInfo("Europe/Paris")

# Les 18 colonnes du FEC (article A47 A-1 du Livre des procédures fiscales).
# / The 18 FEC columns.
COLONNES_DU_FEC = [
    "JournalCode",
    "JournalLib",
    "EcritureNum",
    "EcritureDate",
    "CompteNum",
    "CompteLib",
    "CompAuxNum",
    "CompAuxLib",
    "PieceRef",
    "PieceDate",
    "EcritureLib",
    "Debit",
    "Credit",
    "EcritureLet",
    "DateLet",
    "ValidDate",
    "Montantdevise",
    "Idevise",
]

# Noms des monnaies du test. / The test currencies' names.
NOM_DE_LA_MONNAIE_LOCALE = "Monnaie locale FEC"
NOM_DES_JETONS_CADEAU = "Jetons cadeau FEC"
NOM_DES_POINTS = "Points FEC"

# Le compte que le lieu donne à sa monnaie locale (`MappingMonnaie`) dans le scénario
# comparé au Z : il sépare l'argent de la monnaie locale des recharges (419100).
# / The account the venue gives its local currency in the scenario compared to the Z.
NUMERO_DU_COMPTE_DE_LA_MONNAIE_LOCALE = "419200"


def reponse_vide_pour_le_middleware(requete):
    """
    Le middleware de session demande la fonction qui produit la réponse suivante ; le
    test n'en a pas besoin : il n'appelle que `process_request`.
    / The session middleware wants a "next response" function; the test only calls
    process_request.
    """
    return None


def heure_de_paris(annee, mois, jour, heure, minute=0):
    """Un moment en heure de Paris. / A moment in Paris time."""
    return datetime(annee, mois, jour, heure, minute, tzinfo=FUSEAU_DE_PARIS)


# La journée des scénarios à une seule J : les ventes à 18 h, le Z à 23 h.
# / The day of single-J scenarios: sales at 6 pm, the Z at 11 pm.
MOMENT_DES_VENTES = heure_de_paris(2026, 3, 10, 18, 0)
MOMENT_DU_Z = heure_de_paris(2026, 3, 10, 23, 0)


def centimes_d_un_montant_du_fec(montant_en_texte):
    """
    Un montant du FEC (« 12,34 ») en centimes entiers (1234). Lu par le test, jamais
    par le code testé. Le montant doit avoir la forme du FEC : des chiffres, une
    VIRGULE, deux chiffres (ni point, ni signe, ni séparateur de milliers).
    / A FEC amount ("12,34") as whole cents; its shape is checked first.
    """
    assert re.fullmatch(r"\d+,\d{2}", montant_en_texte), montant_en_texte
    montant_en_euros = Decimal(montant_en_texte.replace(",", "."))
    return int(montant_en_euros * 100)


def comptes_de_l_ecriture(ecriture):
    """
    Les lignes d'une écriture de `ventiler_cloture`, sous la forme
    {numéro du compte: (débit, crédit)}.
    / An entry's lines as {account number: (debit, credit)}.
    """
    debit_et_credit_par_compte = {}
    for ligne in ecriture["lignes"]:
        debit_et_credit_par_compte[ligne["compte"]] = (ligne["debit"], ligne["credit"])
    return debit_et_credit_par_compte


def soldes_debiteurs_du_fec(lignes_du_fec):
    """
    Le solde de chaque compte du FEC : Σ débits − Σ crédits, en centimes. Un compte de
    vente a un solde négatif (il est crédité).
    / Each FEC account's balance: debits minus credits, in cents.
    """
    solde_par_compte = {}
    for ligne in lignes_du_fec:
        numero_du_compte = ligne["CompteNum"]
        if numero_du_compte not in solde_par_compte:
            solde_par_compte[numero_du_compte] = 0
        solde_par_compte[numero_du_compte] += centimes_d_un_montant_du_fec(
            ligne["Debit"]
        )
        solde_par_compte[numero_du_compte] -= centimes_d_un_montant_du_fec(
            ligne["Credit"]
        )
    return solde_par_compte


class TestFecEquilibre(FastTenantTestCase):
    """
    La ventilation d'une J et le FEC (fiche F §4, §6 tests 19 à 25b).
    / The J breakdown and the FEC.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_fec_equilibre"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-fec-equilibre.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test FEC equilibre"

    def setUp(self):
        """
        Le lieu de test (Paris, fermeture à 2 h, aucun email de rapport), une catégorie
        de caisse « Boissons » reliée au 707000, et deux boissons rangées dedans : un
        jus à 3,50 € et une bière à 3,00 € (TVA 20 %).
        / The test venue, a "Drinks" POS category linked to 707000, a juice and a beer.
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
        # / Every value read by the closure is written here (the cache survives).
        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.heure_de_fermeture = time(2, 0)
        configuration.rapport_emails = ""
        configuration.save()

        compte_des_marchandises = CompteComptable.objects.get(numero_de_compte="707000")
        self.categorie_des_boissons = CategorieProduct.objects.create(
            name=f"Boissons FEC {identifiant_unique()}",
            compte_comptable=compte_des_marchandises,
        )
        self.tarif_du_jus = self._tarif_d_une_boisson("Jus", "3.50")
        self.tarif_de_la_biere = self._tarif_d_une_boisson("Biere", "3.00")

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

    def _tarif_d_une_boisson(self, nom, prix_en_euros):
        """
        Le tarif vendu d'une boisson à 20 %, rangée dans la catégorie « Boissons »
        (compte 707000).
        / The sold price of a 20 % drink, in the "Drinks" category (707000).
        """
        tarif_vendu = creer_tarif_vendu(
            nom=nom,
            prix_en_euros=prix_en_euros,
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )
        produit = tarif_vendu.productsold.product
        produit.categorie_pos = self.categorie_des_boissons
        produit.save()
        return tarif_vendu

    def _monnaie(self, nom, categorie):
        """
        Une monnaie du moteur fedow_core, créée par le lieu de test.
        / A fedow_core currency created by the test venue.
        """
        portefeuille_d_origine = Wallet.objects.create(
            name=f"Portefeuille FEC {identifiant_unique()}"
        )
        return Asset.objects.create(
            name=nom,
            currency_code="EUR",
            category=categorie,
            tenant_origin=self.tenant,
            wallet_origin=portefeuille_d_origine,
        )

    def _point_de_vente(self, nom, code_journal=""):
        """
        Un point de vente caché (tests/PIEGES.md 9.41), créé sans passer par l'admin :
        son code journal n'est pas validé.
        / A hidden point of sale, created outside the admin: its code is not validated.
        """
        return PointDeVente.objects.create(
            name=nom, code_journal=code_journal, hidden=True
        )

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
        La clôture M du mois précédent `moment`, en heure locale du lieu.
        / The M closure of the month before `moment`.
        """
        with self._heure_figee(moment):
            uuid_de_la_cloture = comptabilite.tasks.generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_MENSUEL,
            )
        return ClotureCaisse.objects.get(uuid=uuid_de_la_cloture)

    def _vendre_un_jus(self, moyen, point_de_vente=None):
        """
        Une vente de caisse : un jus à 3,50 € réglé par `moyen`. La ligne est VALID
        (comme la caisse l'écrit) et relue en base pour la fonction des avoirs.
        / A register sale: one juice paid by `moyen`; the line is read back.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=point_de_vente,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": moyen, "montant": 350}],
        )
        verifier_egalites(vente)
        return LigneArticle.objects.get(vente=vente)

    def _billet_vendu_en_ligne_par_stripe(self, prix_en_centimes, ecart_en_centimes=0):
        """
        Un billet à 5,5 % vendu en ligne et payé par Stripe (moyen SN). Si Stripe
        encaisse un montant différent, l'écart est écrit par le service. La ligne est
        relue en base.
        / A 5.5 % ticket sold online and paid by Stripe, with an optional gap.
        """
        acheteur = creer_utilisateur()
        tarif_du_billet = creer_tarif_vendu(
            nom="Billet",
            prix_en_euros=str(Decimal(prix_en_centimes) / 100),
            taux_tva="5.50",
            categorie_article=Product.BILLET,
        )
        vente_en_ligne = ouvrir_vente(
            origine=SaleOrigin.LESPASS,
            nature=Vente.Nature.VENTE,
            client=acheteur,
        )
        paiement = Paiement_stripe.objects.create(
            user=acheteur,
            status=Paiement_stripe.VALID,
            moyen=PaymentMethod.STRIPE_NOFED,
            payment_intent_id=f"pi_test_{identifiant_unique()}",
            vente=vente_en_ligne,
        )
        ligne = ajouter_article(
            vente_en_ligne,
            pricesold=tarif_du_billet,
            quantite=Decimal("1"),
            prix_unitaire=prix_en_centimes,
            taux_tva=Decimal("5.5"),
            payment_method=PaymentMethod.STRIPE_NOFED,
            paiement_stripe=paiement,
            status=LigneArticle.VALID,
        )
        ajouter_l_article_d_ecart_d_encaissement(vente_en_ligne, ecart_en_centimes)
        ajouter_reglement(
            vente_en_ligne,
            moyen=PaymentMethod.STRIPE_NOFED,
            montant=prix_en_centimes + ecart_en_centimes,
            paiement_stripe=paiement,
        )
        vente_en_ligne = encaisser_vente(vente_en_ligne)
        verifier_egalites(vente_en_ligne)
        return LigneArticle.objects.get(pk=ligne.pk)

    def _avoir_par_le_bouton_de_l_admin(self, ligne, moyen_rembourse):
        """
        L'avoir d'une ligne entière par la fonction du bouton « Avoir » de l'admin
        (origine ADMIN). Ligne Stripe : règlement Stripe négatif sans référence externe.
        Ligne en jetons : règlement « jetons » négatif. Les tâches Celery sont
        interceptées.
        / The credit note of a whole line through the admin "Credit note" function.
        """
        with taches_celery_enregistrees():
            article_d_avoir = ecrire_la_vente_d_avoir_d_une_ligne(
                ligne,
                quantite=Decimal("1"),
                moyen_rembourse=moyen_rembourse,
                origine=SaleOrigin.ADMIN,
            )
        vente_d_avoir = Vente.objects.get(pk=article_d_avoir.vente_id)
        verifier_egalites(vente_d_avoir)
        return vente_d_avoir

    def _corriger_les_especes_en_cb(self, vente_d_origine):
        """
        La correction d'un jus payé en espèces : une vente CORRECTION liée, sans
        article, espèces −350 et CB +350.
        / The correction of a cash juice: cash −350, card +350.
        """
        vente_de_correction = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.CORRECTION,
            vente_liee=vente_d_origine,
        )
        ajouter_reglement(vente_de_correction, moyen=PaymentMethod.CASH, montant=-350)
        ajouter_reglement(vente_de_correction, moyen=PaymentMethod.CC, montant=350)
        vente_de_correction = encaisser_vente(vente_de_correction)
        verifier_egalites(vente_de_correction)

    def _recharge_offerte(self, montant_en_centimes):
        """
        Une recharge cadeau à la caisse (D8 bis) : l'article de recharge est
        entièrement offert, le service écrit sa part offerte et le règlement FREE.
        / A gift top-up at the register: fully offered, FREE payment by the service.
        """
        tarif_de_la_recharge_cadeau = creer_tarif_vendu(
            nom="Recharge cadeau",
            prix_en_euros=str(Decimal(montant_en_centimes) / 100),
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_CADEAU,
        )
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_la_recharge_cadeau,
                    "quantite": Decimal("1"),
                    "prix_unitaire": montant_en_centimes,
                    "taux_tva": Decimal("0"),
                    "offert_en_totalite": True,
                },
            ],
        )
        verifier_egalites(vente)

    def _biere_payee_en_jetons(self, jetons_cadeau):
        """
        Une bière à 3,00 € payée en jetons cadeau, comme la caisse l'écrit : la ligne
        porte le moyen LG et la monnaie des jetons, TVA 0 ; un règlement « jetons » de
        300. La ligne est VALID et relue en base.
        / A 3.00 € beer paid in gift tokens, like the register writes it.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_de_la_biere,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 300,
                    "taux_tva": Decimal("0"),
                    "payment_method": PaymentMethod.LOCAL_GIFT,
                    "asset": jetons_cadeau.uuid,
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_GIFT,
                    "montant": 300,
                    "asset": jetons_cadeau.uuid,
                },
            ],
        )
        verifier_egalites(vente)
        return LigneArticle.objects.get(vente=vente)

    def _vidage_avec_jetons_repris(self, jetons_cadeau, montant_en_centimes):
        """
        Une carte qui n'a que des jetons cadeau, vidée (D12, D8 bis) : l'article
        « Jetons cadeau repris au vidage » (hors chiffre d'affaires, TVA 0) et un
        règlement « jetons » du même montant, aucun règlement espèces.
        / A card holding only gift tokens, emptied.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VIDAGE_CARTE,
            articles=[
                {
                    "pricesold": tarif_vendu_d_un_produit_systeme(
                        NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE
                    ),
                    "quantite": Decimal("1"),
                    "prix_unitaire": montant_en_centimes,
                    "taux_tva": Decimal("0"),
                    "hors_chiffre_affaires": True,
                },
            ],
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_GIFT,
                    "montant": montant_en_centimes,
                    "asset": jetons_cadeau.uuid,
                },
            ],
        )
        verifier_egalites(vente)

    def _jus_offert_par_le_bouton_offrir(self):
        """
        Un jus offert par le bouton OFFRIR : part offerte = total, règlement FREE.
        / A juice gifted with the GIFT button.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "offert_en_totalite": True,
                },
            ],
        )
        verifier_egalites(vente)

    def _vente_en_points(self, monnaie_de_points):
        """
        Une planche vendue 500 centièmes de points (D9) : unité = la monnaie de
        points, TVA 0, règlement NM. Le produit n'a aucun compte : une vente en points
        n'en a pas besoin.
        / A board sold for 500 hundredths of points; the product has no account.
        """
        tarif_de_la_planche = creer_tarif_vendu(
            nom="Planche en points", prix_en_euros="5.00", taux_tva="0.00"
        )
        vente = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VENTE,
            unite=str(monnaie_de_points.uuid),
        )
        ajouter_article(
            vente,
            pricesold=tarif_de_la_planche,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("0"),
        )
        ajouter_reglement(
            vente,
            moyen=PaymentMethod.NON_MONETAIRE,
            montant=500,
            asset=monnaie_de_points.uuid,
        )
        vente = encaisser_vente(vente)
        verifier_egalites(vente)

    def _recharge_offerte_en_points(self, monnaie_de_points):
        """
        Une recharge offerte EN POINTS, écrite comme l'API v2 l'écrit : vente à
        l'unité de la monnaie de points, article de recharge entièrement offert,
        règlement FREE. Ce n'est pas de l'argent : aucune écriture.
        / A top-up offered in points, written like the API v2 does: no entry.
        """
        tarif_de_la_recharge_en_points = creer_tarif_vendu(
            nom="Recharge points",
            prix_en_euros="0.00",
            taux_tva="0.00",
            categorie_article=Product.RECHARGE_CASHLESS,
        )
        vente = ouvrir_vente(
            origine=SaleOrigin.LESPASS,
            nature=Vente.Nature.VENTE,
            unite=str(monnaie_de_points.uuid),
        )
        ajouter_article(
            vente,
            pricesold=tarif_de_la_recharge_en_points,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("0"),
            offert_en_totalite=True,
        )
        vente = encaisser_vente(vente)
        verifier_egalites(vente)

    def _gobelet_consigne_vendu_puis_rendu(self):
        """
        Un gobelet consigné vendu 1,00 € en espèces, puis rapporté (D11) : vente AVOIR,
        article de retour au prix négatif, 1,00 € rendu en espèces. Le retour prend le
        compte de la catégorie de la consigne (707000).
        / A deposit cup sold then returned; the return takes the cup's account.
        """
        tarif_du_gobelet = self._tarif_d_une_boisson("Gobelet", "1.00")
        tarif_du_retour = creer_tarif_vendu(
            nom="Retour gobelet",
            prix_en_euros="-1.00",
            taux_tva="20.00",
            methode_caisse=Product.RETOUR_CONSIGNE,
        )
        produit_de_retour = tarif_du_retour.productsold.product
        produit_de_retour.consigne_remboursee = tarif_du_gobelet.productsold.product
        produit_de_retour.save()

        vente_du_gobelet = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_du_gobelet,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 100,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 100}],
        )
        verifier_egalites(vente_du_gobelet)
        vente_du_retour = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.AVOIR,
            articles=[
                {
                    "pricesold": tarif_du_retour,
                    "quantite": Decimal("1"),
                    "prix_unitaire": -100,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": -100}],
        )
        verifier_egalites(vente_du_retour)

    def _adhesion_payee_par_cheque(self):
        """
        Une adhésion à 15,00 € (TVA 0) payée par chèque à la caisse : compte des
        cotisations (756000) par le type de produit.
        / A 15.00 € membership paid by cheque: membership fees account.
        """
        tarif_de_l_adhesion = creer_tarif_vendu(
            nom="Adhesion",
            prix_en_euros="15.00",
            taux_tva="0.00",
            categorie_article=Product.ADHESION,
        )
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_de_l_adhesion,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1500,
                    "taux_tva": Decimal("0"),
                },
            ],
            reglements=[{"moyen": PaymentMethod.CHEQUE, "montant": 1500}],
        )
        verifier_egalites(vente)

    def _ventes_du_scenario_compare_au_z(self):
        """
        Le scénario du test 20 (fiche F §6), toutes les ventes à 18 h. La monnaie
        locale du lieu a son propre compte (419200, `MappingMonnaie`) : son argent ne
        se mêle pas aux recharges (419100).
        a. trois jus (10,50 €) : 5,00 € en monnaie locale, 5,50 € en CB ;
        b. un jus en espèces (3,50 €), corrigé en CB ;
        c. un billet Stripe de 20,00 € (5,5 %), Stripe encaisse 20,03 € (écart +3) ;
        d. un billet Stripe de 35,00 € (5,5 %), puis son avoir par l'admin, sans
           référence de remboursement (Stripe −35,00 €, écrit au compte Stripe dès
           l'avoir) ;
        e. une recharge de 20,00 € en CB ;
        f. un jus en espèces (3,50 €), puis son avoir en espèces (−3,50 €) ;
        g. une carte de 7,00 € en monnaie locale vidée, les espèces rendues (−7,00 €).
        / The test 20 scenario: local currency with its own account, card, cash
        correction, Stripe tickets with a gap and a credit note, top-up, cash credit
        note, card emptied.

        :return: la monnaie locale
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        compte_de_la_monnaie_locale = CompteComptable.objects.create(
            numero_de_compte=NUMERO_DU_COMPTE_DE_LA_MONNAIE_LOCALE,
            libelle_du_compte="Monnaie locale du lieu (test FEC)",
            nature_du_compte=CompteComptable.TIERS,
        )
        MappingMonnaie.objects.create(
            asset_uuid=monnaie_locale.uuid,
            compte_de_tresorerie=compte_de_la_monnaie_locale,
        )
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="20.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )

        with self._heure_figee(MOMENT_DES_VENTES):
            # a. Trois jus, en deux « parts » comme la caisse les écrit.
            # / a. Three juices, in two "parts" like the register writes them.
            vente_du_fil_rouge = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": self.tarif_du_jus,
                        "quantite": Decimal("1.428571"),
                        "prix_unitaire": 350,
                        "taux_tva": Decimal("20"),
                        "total_catalogue_impose": 500,
                    },
                    {
                        "pricesold": self.tarif_du_jus,
                        "quantite": Decimal("1.571429"),
                        "prix_unitaire": 350,
                        "taux_tva": Decimal("20"),
                        "total_catalogue_impose": 550,
                    },
                ],
                reglements=[
                    {
                        "moyen": PaymentMethod.LOCAL_EURO,
                        "montant": 500,
                        "asset": monnaie_locale.uuid,
                    },
                    {"moyen": PaymentMethod.CC, "montant": 550},
                ],
            )
            verifier_egalites(vente_du_fil_rouge)

            # b. / c. / d.
            ligne_du_jus_corrige = self._vendre_un_jus(PaymentMethod.CASH)
            self._corriger_les_especes_en_cb(ligne_du_jus_corrige.vente)
            self._billet_vendu_en_ligne_par_stripe(2000, ecart_en_centimes=3)
            billet_rembourse = self._billet_vendu_en_ligne_par_stripe(3500)
            self._avoir_par_le_bouton_de_l_admin(billet_rembourse, moyen_rembourse=None)

            # e. La recharge en CB. / e. The card top-up.
            vente_de_la_recharge = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": tarif_de_la_recharge,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 2000,
                        "taux_tva": Decimal("0"),
                    },
                ],
                reglements=[{"moyen": PaymentMethod.CC, "montant": 2000}],
            )
            verifier_egalites(vente_de_la_recharge)

            # f. Le jus remboursé en espèces. / f. The juice refunded in cash.
            ligne_du_jus_rembourse = self._vendre_un_jus(PaymentMethod.CASH)
            self._avoir_par_le_bouton_de_l_admin(
                ligne_du_jus_rembourse, moyen_rembourse=PaymentMethod.CASH
            )

            # g. La carte vidée. / g. The emptied card.
            vente_du_vidage = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                nature=Vente.Nature.VIDAGE_CARTE,
                reglements=[
                    {
                        "moyen": PaymentMethod.LOCAL_EURO,
                        "montant": 700,
                        "asset": monnaie_locale.uuid,
                    },
                    {"moyen": PaymentMethod.CASH, "montant": -700},
                ],
            )
            verifier_egalites(vente_du_vidage)

        return monnaie_locale

    def _lignes_du_fec(self, cloture):
        """
        Le FEC d'une clôture, lu par le test : UTF-8 strict sans BOM, l'en-tête doit
        être les 18 colonnes, chaque ligne en a 18. Rend une liste de dictionnaires
        {colonne: valeur}.
        / The FEC of a closure, parsed: strict UTF-8 without BOM, 18 columns, one
        dict per line.
        """
        contenu_en_octets, _nom_du_fichier, type_du_contenu = generer_fec_cloture(
            cloture
        )
        assert type_du_contenu == "text/plain; charset=utf-8"
        assert not contenu_en_octets.startswith(b"\xef\xbb\xbf")
        contenu = contenu_en_octets.decode("utf-8", errors="strict")
        lignes_de_texte = contenu.split("\r\n")
        assert lignes_de_texte[0].split("\t") == COLONNES_DU_FEC

        lignes_du_fec = []
        for ligne_de_texte in lignes_de_texte[1:]:
            if ligne_de_texte == "":
                continue
            valeurs = ligne_de_texte.split("\t")
            assert len(valeurs) == len(COLONNES_DU_FEC), ligne_de_texte
            ligne_du_fec = {}
            position_de_la_colonne = 0
            for colonne in COLONNES_DU_FEC:
                ligne_du_fec[colonne] = valeurs[position_de_la_colonne]
                position_de_la_colonne += 1
            lignes_du_fec.append(ligne_du_fec)
        return lignes_du_fec

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

    # ------------------------------------------------------------------
    # 19, 20, 21 — Équilibre, égalité avec le Z, côté opposé
    # / 19, 20, 21 — Balance, equality with the Z, opposite side
    # ------------------------------------------------------------------

    def test_fec_equilibre_sur_le_scenario_complet(self):
        """
        Fiche F §6, test 19 : le scénario du test 20, plus les jetons cadeau (recharge
        offerte, bière payée en jetons puis son avoir, vidage avec jetons repris), un
        jus offert, une vente en points, une recharge offerte en points, un gobelet
        consigné rendu, un billet Stripe avec un écart reçu en moins, une adhésion par
        chèque. Une seule J.
        - chaque écriture (CAISSE, WEB, ADMIN) vaut un dictionnaire complet, calculé à
          la main ci-dessous ;
        - chaque écriture (même `EcritureNum`) : Σ débits = Σ crédits ; le fichier
          entier aussi ;
        - chaque compte écrit est un compte du plan du lieu, avec son libellé : aucun
          compte écrit en dur ; le libellé d'un journal d'origine est celui de la table.
        / The full scenario: each entry equals a hand-computed dict; every entry
        balanced; every account comes from the venue's chart with its label.
        """
        self._ventes_du_scenario_compare_au_z()
        jetons_cadeau = self._monnaie(NOM_DES_JETONS_CADEAU, Asset.TNF)
        points = self._monnaie(NOM_DES_POINTS, Asset.FID)
        with self._heure_figee(MOMENT_DES_VENTES):
            self._recharge_offerte(1000)
            ligne_de_la_biere = self._biere_payee_en_jetons(jetons_cadeau)
            self._avoir_par_le_bouton_de_l_admin(
                ligne_de_la_biere, moyen_rembourse=None
            )
            self._vidage_avec_jetons_repris(jetons_cadeau, 200)
            self._jus_offert_par_le_bouton_offrir()
            self._vente_en_points(points)
            self._recharge_offerte_en_points(points)
            self._gobelet_consigne_vendu_puis_rendu()
            self._billet_vendu_en_ligne_par_stripe(1000, ecart_en_centimes=-2)
            self._adhesion_payee_par_cheque()
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        comptes_par_journal = {}
        ecritures_de_la_j = ventiler_cloture(cloture)
        for ecriture in ecritures_de_la_j:
            comptes_par_journal[ecriture["journal"]] = comptes_de_l_ecriture(ecriture)

        # CAISSE (ventes de caisse sans point de vente), en centimes :
        # - 419200 monnaie locale : fil rouge 500 + carte vidée 700 = D 1200 ;
        # - 512100 CB : fil rouge 550 + correction 350 + recharge 2000 = D 2900 ;
        # - 511200 chèques : adhésion = D 1500 ;
        # - 623400 cadeaux : recharge offerte 1000 − jetons repris 200 = D 800 ;
        # - 530000 espèces : jus 350 − correction 350 + jus 350 − vidage 700
        #   + gobelet 100 − retour 100 = −350 → C 350 ;
        # - 419100 avances : recharge 2000 + recharge offerte 1000 − bière en jetons
        #   300 − jetons repris au vidage 200 = C 2500 ;
        # - 707000 boissons (HT) : fil rouge 875 + jus 292 + jus 292 + gobelet 83
        #   − retour 83 = C 1459 (gobelet 100 à 20 % → HT arrondi(83,33) = 83) ;
        # - 445711 TVA 20 % : 175 + 58 + 58 + 17 − 17 = C 291 ;
        # - 707900 ventes en jetons : bière C 300 ; 756000 cotisations : adhésion C 1500.
        # Débits 6400 = crédits 6400.
        # WEB (billets en ligne, Stripe) :
        # - 517100 Stripe : 2003 + 3500 + 998 = D 6501 ;
        # - 658000 écart reçu en moins : D 2 ;
        # - 706000 billets (HT) : 1896 + 3318 + 948 = C 6162 (1000 à 5,5 % →
        #   HT arrondi(947,87) = 948) ;
        # - 445713 TVA 5,5 % : 104 + 182 + 52 = C 338 ; 758000 écart reçu en plus : C 3.
        # Débits 6503 = crédits 6503.
        # ADMIN (avoirs de l'admin : billet Stripe, jus en espèces, bière en jetons) :
        # 706000 D 3318, 445713 D 182, 707000 D 292, 445711 D 58, 707900 D 300 ;
        # 517100 C 3500, 530000 C 350, 419100 C 300. Débits 4150 = crédits 4150.
        # / Each entry computed by hand.
        assert comptes_par_journal == {
            "CAISSE": {
                "419200": (1200, 0),
                "511200": (1500, 0),
                "512100": (2900, 0),
                "623400": (800, 0),
                "419100": (0, 2500),
                "445711": (0, 291),
                "530000": (0, 350),
                "707000": (0, 1459),
                "707900": (0, 300),
                "756000": (0, 1500),
            },
            "WEB": {
                "517100": (6501, 0),
                "658000": (2, 0),
                "445713": (0, 338),
                "706000": (0, 6162),
                "758000": (0, 3),
            },
            "ADMIN": {
                "445711": (58, 0),
                "445713": (182, 0),
                "706000": (3318, 0),
                "707000": (292, 0),
                "707900": (300, 0),
                "419100": (0, 300),
                "517100": (0, 3500),
                "530000": (0, 350),
            },
        }

        lignes_du_fec = self._lignes_du_fec(cloture)
        assert lignes_du_fec != []
        for ligne in lignes_du_fec:
            assert (
                ligne["JournalLib"]
                == (LIBELLE_DU_JOURNAL_SANS_POINT_DE_VENTE[ligne["JournalCode"]])
            )

        debits_par_ecriture = {}
        credits_par_ecriture = {}
        total_des_debits = 0
        total_des_credits = 0
        for ligne in lignes_du_fec:
            numero_d_ecriture = ligne["EcritureNum"]
            if numero_d_ecriture not in debits_par_ecriture:
                debits_par_ecriture[numero_d_ecriture] = 0
                credits_par_ecriture[numero_d_ecriture] = 0
            debit = centimes_d_un_montant_du_fec(ligne["Debit"])
            credit = centimes_d_un_montant_du_fec(ligne["Credit"])
            debits_par_ecriture[numero_d_ecriture] += debit
            credits_par_ecriture[numero_d_ecriture] += credit
            total_des_debits += debit
            total_des_credits += credit
        assert debits_par_ecriture == credits_par_ecriture
        assert total_des_debits == total_des_credits

        # Les ventes de caisse (CAISSE), en ligne (WEB) et les avoirs de l'admin
        # (ADMIN) : trois journaux, trois écritures.
        # / Register, online and admin sales: three journals, three entries.
        journaux_du_fec = set()
        for ligne in lignes_du_fec:
            journaux_du_fec.add(ligne["JournalCode"])
        assert journaux_du_fec == {"CAISSE", "WEB", "ADMIN"}
        assert len(debits_par_ecriture) == 3

        libelle_par_numero_du_plan = {}
        comptes_du_plan_du_lieu = CompteComptable.objects.all()
        for compte_du_plan in comptes_du_plan_du_lieu:
            libelle_par_numero_du_plan[compte_du_plan.numero_de_compte] = (
                compte_du_plan.libelle_du_compte
            )
        for ligne in lignes_du_fec:
            assert ligne["CompteNum"] in libelle_par_numero_du_plan, ligne
            assert ligne["CompteLib"] == libelle_par_numero_du_plan[ligne["CompteNum"]]

    def test_fec_egal_au_z(self):
        """
        Fiche F §6, test 20 : pour chaque compte de règlement, le solde du FEC
        (débits − crédits) vaut les règlements du Z pour ce moyen et cette monnaie ;
        pour chaque compte de vente, de TVA et hors chiffre d'affaires, le solde
        (crédits − débits) vaut le total du Z correspondant. Le Z est le rapport stocké
        dans la J (`rapport_json`). Le scénario contient des avoirs, une correction et
        un vidage de carte.
        Le vidage n'est pas en section 3 du Z (règlements) : ses espèces rendues sont
        en section 7. Ses deux règlements s'annulent (monnaie locale +700, espèces
        −700) : la monnaie locale vidée vaut donc −(espèces rendues).
        / For each payment account, the FEC balance equals the Z payments; for each
        sales, VAT and off-revenue account, the Z total. The card emptying is read
        from section 7.
        """
        monnaie_locale = self._ventes_du_scenario_compare_au_z()
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        rapport = cloture.rapport_json
        argent_par_moyen = rapport["reglements"]["argent"]["par_moyen"]
        cashless_par_moyen = rapport["reglements"]["cashless"]["par_moyen"]
        especes_rendues = rapport["annexe"]["recharges_et_cartes"]["cartes_videes"][
            "especes_rendues_en_centimes"
        ]
        par_categorie = rapport["chiffre_affaires"]["par_categorie"]
        par_taux = rapport["chiffre_affaires"]["par_taux"]
        recharges_encaissees = rapport["annexe"]["recharges_et_cartes"][
            "recharges_encaissees"
        ]
        ecarts = rapport["annexe"]["ecarts_d_encaissement"]

        soldes_attendus_lus_dans_le_z = {
            "530000": argent_par_moyen["CA"]["total_en_centimes"] + especes_rendues,
            "512100": argent_par_moyen["CC"]["total_en_centimes"],
            "517100": argent_par_moyen["SN"]["total_en_centimes"],
            NUMERO_DU_COMPTE_DE_LA_MONNAIE_LOCALE: (
                cashless_par_moyen["LE"]["par_monnaie"][str(monnaie_locale.uuid)][
                    "total_en_centimes"
                ]
                - especes_rendues
            ),
            "707000": -par_categorie[str(self.categorie_des_boissons.uuid)][
                "total_ht_en_centimes"
            ],
            "706000": -par_categorie[f"type_{Product.BILLET}"]["total_ht_en_centimes"],
            "445711": -par_taux["20.00"]["total_tva_en_centimes"],
            "445713": -par_taux["5.50"]["total_tva_en_centimes"],
            "419100": -recharges_encaissees["total_en_centimes"],
            "758000": -ecarts["total_en_centimes"],
        }

        # Les mêmes soldes, calculés à la main (débits − crédits) :
        # - 530000 espèces : jus +350, correction −350, jus +350, avoir −350, vidage
        #   −700 → −700 ;
        # - 512100 CB : 550 + 350 (correction) + 2000 (recharge) = 2900 ;
        # - 517100 Stripe : 2003 + 3500 − 3500 = 2003 ;
        # - 419200 monnaie locale : 500 + 700 (vidée) = 1200 ;
        # - 707000 boissons : −(875 + 292 + 292 − 292) = −1167 ;
        # - 706000 billets : −(1896 + 3318 − 3318) = −1896 (2000 à 5,5 % → HT 1896 ;
        #   3500 → HT arrondi(3317,54) = 3318) ;
        # - 445711 TVA 20 % : −(175 + 58 + 58 − 58) = −233 ;
        # - 445713 TVA 5,5 % : −(104 + 182 − 182) = −104 ;
        # - 419100 recharges : −2000 ; 758000 écart reçu en plus : −3.
        # Somme : −700 + 2900 + 2003 + 1200 − 1167 − 1896 − 233 − 104 − 2000 − 3 = 0.
        # / The same balances, by hand.
        assert soldes_attendus_lus_dans_le_z == {
            "530000": -700,
            "512100": 2900,
            "517100": 2003,
            NUMERO_DU_COMPTE_DE_LA_MONNAIE_LOCALE: 1200,
            "707000": -1167,
            "706000": -1896,
            "445711": -233,
            "445713": -104,
            "419100": -2000,
            "758000": -3,
        }

        assert soldes_debiteurs_du_fec(self._lignes_du_fec(cloture)) == (
            soldes_attendus_lus_dans_le_z
        )

    def test_fec_avoir_ecrit_du_cote_oppose_en_positif(self):
        """
        Fiche F §6, test 21 : un jus vendu en espèces dans une première J, puis son
        avoir en espèces dans une seconde J. L'écriture de la seconde J (journal
        ADMIN) a des montants négatifs (article −350, espèces −350) : chacun passe du
        côté opposé, en positif. 707000 au débit 292, 445711 au débit 58, 530000 au
        crédit 350. Un compte par ligne, un seul côté rempli par ligne, aucun montant
        négatif dans le FEC.
        / A credit note in its own J: negative amounts go to the opposite side, as
        positive amounts.
        """
        with self._heure_figee(heure_de_paris(2026, 3, 10, 18, 0)):
            ligne_du_jus = self._vendre_un_jus(PaymentMethod.CASH)
        self._cloturer_la_journee_a(heure_de_paris(2026, 3, 10, 18, 30))
        with self._heure_figee(heure_de_paris(2026, 3, 10, 19, 0)):
            self._avoir_par_le_bouton_de_l_admin(
                ligne_du_jus, moyen_rembourse=PaymentMethod.CASH
            )
        j_de_l_avoir = self._cloturer_la_journee_a(heure_de_paris(2026, 3, 10, 19, 30))

        ecritures = ventiler_cloture(j_de_l_avoir)

        assert len(ecritures) == 1
        assert ecritures[0]["journal"] == "ADMIN"
        assert comptes_de_l_ecriture(ecritures[0]) == {
            "707000": (292, 0),
            "445711": (58, 0),
            "530000": (0, 350),
        }
        assert len(ecritures[0]["lignes"]) == 3

        lignes_du_fec_de_l_avoir = self._lignes_du_fec(j_de_l_avoir)
        for ligne in lignes_du_fec_de_l_avoir:
            assert not ligne["Debit"].startswith("-"), ligne
            assert not ligne["Credit"].startswith("-"), ligne
            debit = centimes_d_un_montant_du_fec(ligne["Debit"])
            credit = centimes_d_un_montant_du_fec(ligne["Credit"])
            un_seul_cote_rempli = (debit == 0) != (credit == 0)
            assert un_seul_cote_rempli, ligne

    # ------------------------------------------------------------------
    # 22 et refus — Compte manquant, écriture déséquilibrée
    # / 22 and refusals — Missing account, unbalanced entry
    # ------------------------------------------------------------------

    def test_fec_refuse_si_compte_manquant(self):
        """
        Fiche F §6, test 22 : une planche (mode de caisse « vente ») sans catégorie
        de caisse n'a pas de compte (fiche E §3.3, règle 3). La ventilation et le FEC
        refusent (`CompteComptableManquant`) ; le bouton « FEC » de l'admin ne
        télécharge rien et affiche un message d'erreur qui renvoie à « Plan complet ? ».
        / A product without account: the breakdown and the FEC refuse; the admin shows
        an error pointing to "Complete plan?", no download.
        """
        tarif_de_la_planche = creer_tarif_vendu(
            nom="Planche sans categorie",
            prix_en_euros="8.00",
            taux_tva="10.00",
            methode_caisse=Product.VENTE,
        )
        with self._heure_figee(MOMENT_DES_VENTES):
            vente = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": tarif_de_la_planche,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 800,
                        "taux_tva": Decimal("10"),
                    },
                ],
                reglements=[{"moyen": PaymentMethod.CASH, "montant": 800}],
            )
            verifier_egalites(vente)
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        with self.assertRaises(CompteComptableManquant):
            ventiler_cloture(cloture)
        with self.assertRaises(CompteComptableManquant):
            generer_fec_cloture(cloture)

        reponse, messages_affiches = self._exporter_le_fec_par_l_admin(cloture)

        assert "attachment" not in reponse.get("Content-Disposition", "")
        messages_d_erreur = []
        for niveau, texte in messages_affiches:
            if niveau == messages.ERROR:
                messages_d_erreur.append(texte)
        assert len(messages_d_erreur) == 1, messages_affiches
        assert "Plan complet" in messages_d_erreur[0]

    def test_fec_refuse_si_desequilibre(self):
        """
        Une écriture déséquilibrée est refusée. Le plan comptable ne peut pas la
        produire (l'équilibre vient des deux égalités de chaque vente) : le test altère
        la donnée, comme une écriture à la main dans la base. Un jus vendu 3,50 € en
        espèces, la J, puis le règlement passe à 4,00 € par `update()` (aucun
        service). La ventilation est recalculée à l'export : espèces 400 au débit,
        292 + 58 = 350 au crédit, écart 50. Refus nommé (`EcritureDesequilibree`),
        message en français qui nomme le journal (CAISSE) et l'écart ; le bouton
        « FEC » de l'admin ne télécharge rien et affiche un message d'erreur.
        / An unbalanced entry (data altered by hand after the J) is refused.
        """
        with self._heure_figee(MOMENT_DES_VENTES):
            ligne_du_jus = self._vendre_un_jus(PaymentMethod.CASH)
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)
        Reglement.objects.filter(vente=ligne_du_jus.vente).update(montant=400)

        with translation.override("fr"):
            with self.assertRaises(EcritureDesequilibree) as refus:
                ventiler_cloture(cloture)
        message_du_refus = str(refus.exception)
        assert "CAISSE" in message_du_refus
        assert "écart de 50 centimes" in message_du_refus
        assert "déséquilibr" in message_du_refus.lower()

        with self.assertRaises(EcritureDesequilibree):
            generer_fec_cloture(cloture)

        reponse, messages_affiches = self._exporter_le_fec_par_l_admin(cloture)

        assert "attachment" not in reponse.get("Content-Disposition", "")
        messages_d_erreur = []
        for niveau, texte in messages_affiches:
            if niveau == messages.ERROR:
                messages_d_erreur.append(texte)
        assert len(messages_d_erreur) == 1, messages_affiches
        assert "CAISSE" in messages_d_erreur[0]

    # ------------------------------------------------------------------
    # 23, 24, 24b — Journaux, offerts et points, jetons cadeau
    # / 23, 24, 24b — Journals, gifts and points, gift tokens
    # ------------------------------------------------------------------

    def test_fec_un_journal_par_point_de_vente(self):
        """
        Fiche F §6, test 23 : un jus en espèces au point de vente « Bar » (journal
        BAR, dérivé du nom), un jus en CB au point de vente « Buvette » au code
        renseigné « buv2 » (journal BUV, nettoyé), un billet en ligne sans point de
        vente (journal WEB). Trois écritures, une par journal, chacune équilibrée. Le
        point de vente gagne sur l'origine (une vente de caisse sur « Bar » n'est pas
        dans CAISSE).
        / One entry per journal: the point of sale wins over the origin.
        """
        point_de_vente_du_bar = self._point_de_vente("Bar")
        point_de_vente_de_la_buvette = self._point_de_vente(
            "Buvette", code_journal="buv2"
        )
        with self._heure_figee(MOMENT_DES_VENTES):
            self._vendre_un_jus(
                PaymentMethod.CASH, point_de_vente=point_de_vente_du_bar
            )
            self._vendre_un_jus(
                PaymentMethod.CC, point_de_vente=point_de_vente_de_la_buvette
            )
            self._billet_vendu_en_ligne_par_stripe(2000)
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        ecritures = ventiler_cloture(cloture)

        comptes_par_journal = {}
        for ecriture in ecritures:
            assert ecriture["journal"] not in comptes_par_journal, ecriture["journal"]
            comptes_par_journal[ecriture["journal"]] = comptes_de_l_ecriture(ecriture)
        # Jus 350 à 20 % → HT 292, TVA 58. Billet 2000 à 5,5 % → HT 1896, TVA 104.
        # / Juice 350 → 292 + 58; ticket 2000 → 1896 + 104.
        assert comptes_par_journal == {
            "BAR": {"530000": (350, 0), "707000": (0, 292), "445711": (0, 58)},
            "BUV": {"512100": (350, 0), "707000": (0, 292), "445711": (0, 58)},
            "WEB": {"517100": (2000, 0), "706000": (0, 1896), "445713": (0, 104)},
        }

        journaux_du_fec = set()
        lignes_du_fec = self._lignes_du_fec(cloture)
        for ligne in lignes_du_fec:
            journaux_du_fec.add(ligne["JournalCode"])
            assert ligne["JournalLib"] != "", ligne
        assert journaux_du_fec == {"BAR", "BUV", "WEB"}

    def test_fec_en_utf8_garde_un_caractere_hors_cp1252(self):
        """
        Le FEC est en UTF-8 sans BOM : un point de vente nommé « Bar ☕ » (la tasse
        n'existe pas en CP1252) garde son nom intact dans `JournalLib`. Son code
        journal, dérivé du nom, reste BAR. Le fichier se décode en UTF-8 strict.
        / The FEC is UTF-8 without BOM: a name outside CP1252 stays intact.
        """
        point_de_vente_du_bar = self._point_de_vente("Bar ☕")
        with self._heure_figee(MOMENT_DES_VENTES):
            self._vendre_un_jus(
                PaymentMethod.CASH, point_de_vente=point_de_vente_du_bar
            )
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        contenu_en_octets, _nom_du_fichier, _type = generer_fec_cloture(cloture)
        contenu = contenu_en_octets.decode("utf-8", errors="strict")

        assert "Bar ☕" in contenu
        lignes_du_fec = self._lignes_du_fec(cloture)
        assert lignes_du_fec != []
        for ligne in lignes_du_fec:
            assert ligne["JournalCode"] == "BAR"
            assert ligne["JournalLib"] == "Bar ☕"

    def test_fec_refuse_deux_points_de_vente_au_meme_code_journal(self):
        """
        Deux points de vente, « Bar 1 » et « Bar 2 », sans code renseigné : leurs noms
        donnent tous deux le code BAR. Leurs ventes se mêleraient dans un journal :
        l'export est refusé (fiche E §3.2, D23). La ventilation et le FEC lèvent
        `CompteComptableManquant`, avec un message qui nomme les deux points de vente
        et le code ; le bouton « FEC » de l'admin ne joint aucun fichier et affiche ce
        message.
        / Two points of sale giving the same journal code: the export is refused.
        """
        point_de_vente_du_bar_1 = self._point_de_vente("Bar 1")
        point_de_vente_du_bar_2 = self._point_de_vente("Bar 2")
        with self._heure_figee(MOMENT_DES_VENTES):
            self._vendre_un_jus(
                PaymentMethod.CASH, point_de_vente=point_de_vente_du_bar_1
            )
            self._vendre_un_jus(
                PaymentMethod.CASH, point_de_vente=point_de_vente_du_bar_2
            )
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        with self.assertRaises(CompteComptableManquant) as refus:
            ventiler_cloture(cloture)
        message_du_refus = str(refus.exception)
        assert "« Bar 1 »" in message_du_refus
        assert "« Bar 2 »" in message_du_refus
        assert "« BAR »" in message_du_refus

        with self.assertRaises(CompteComptableManquant):
            generer_fec_cloture(cloture)

        reponse, messages_affiches = self._exporter_le_fec_par_l_admin(cloture)

        assert "attachment" not in reponse.get("Content-Disposition", "")
        messages_d_erreur = []
        for niveau, texte in messages_affiches:
            if niveau == messages.ERROR:
                messages_d_erreur.append(texte)
        assert len(messages_d_erreur) == 1, messages_affiches
        assert message_du_refus in messages_d_erreur[0]

    def test_fec_refuse_un_point_de_vente_au_code_d_un_journal_d_origine(self):
        """
        Un point de vente nommé « Caisse » donne le code journal CAISSE, celui des
        ventes de caisse sans point de vente : les deux se mêleraient dans un journal.
        Une vente sur « Caisse » et une vente de caisse sans point de vente : la
        ventilation et le FEC refusent (`CompteComptableManquant`), le message nomme le
        point de vente et le code ; l'admin ne joint aucun fichier.
        / A point of sale named "Caisse" takes the origin code CAISSE: refused.
        """
        point_de_vente_nomme_caisse = self._point_de_vente("Caisse")
        with self._heure_figee(MOMENT_DES_VENTES):
            self._vendre_un_jus(
                PaymentMethod.CASH, point_de_vente=point_de_vente_nomme_caisse
            )
            self._vendre_un_jus(PaymentMethod.CASH)
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        with self.assertRaises(CompteComptableManquant) as refus:
            ventiler_cloture(cloture)
        message_du_refus = str(refus.exception)
        assert "« Caisse »" in message_du_refus
        assert "« CAISSE »" in message_du_refus

        with self.assertRaises(CompteComptableManquant):
            generer_fec_cloture(cloture)

        reponse, messages_affiches = self._exporter_le_fec_par_l_admin(cloture)

        assert "attachment" not in reponse.get("Content-Disposition", "")
        messages_d_erreur = []
        for niveau, texte in messages_affiches:
            if niveau == messages.ERROR:
                messages_d_erreur.append(texte)
        assert len(messages_d_erreur) == 1, messages_affiches
        assert message_du_refus in messages_d_erreur[0]

    def test_plan_complet_signale_un_point_de_vente_au_code_d_un_journal_d_origine(
        self,
    ):
        """
        « Plan complet ? » signale un point de vente dont le code est celui d'un
        journal d'origine : « Web » donne WEB, réservé aux ventes en ligne sans point
        de vente. Une phrase nomme le point de vente et le code.
        / "Complete plan?" reports a point of sale using an origin journal code.
        """
        self._point_de_vente("Web")

        with translation.override("fr"):
            manques = ce_qui_manque_pour_exporter()

        phrases_sur_le_point_de_vente = []
        for manque in manques:
            if "« Web »" in manque["phrase"]:
                phrases_sur_le_point_de_vente.append(manque["phrase"])
        assert len(phrases_sur_le_point_de_vente) == 1, manques
        assert "« WEB »" in phrases_sur_le_point_de_vente[0]
        assert "réservé" in phrases_sur_le_point_de_vente[0]

    def _ventes_d_une_journee_payees_par_les_memes_moyens(
        self, nombre_de_ventes, jour, tarif_vendu, monnaie_locale
    ):
        """
        `nombre_de_ventes` articles à 3,50 € (TVA 20 %), chacun payé 2,00 € en monnaie
        locale du lieu (moyen LE, sans compte de monnaie : le compte du moyen) et
        1,50 € en CB, le `jour` (un jour de mars 2026) à 18 h ; puis la J à 23 h.
        / Items paid by the same methods on one day, then the J.

        :return: la J
        """
        with self._heure_figee(heure_de_paris(2026, 3, jour, 18, 0)):
            for _numero_de_la_vente in range(nombre_de_ventes):
                vente = fabriquer_vente_encaissee(
                    origine=SaleOrigin.LABOUTIK,
                    articles=[
                        {
                            "pricesold": tarif_vendu,
                            "quantite": Decimal("1"),
                            "prix_unitaire": 350,
                            "taux_tva": Decimal("20"),
                        },
                    ],
                    reglements=[
                        {
                            "moyen": PaymentMethod.LOCAL_EURO,
                            "montant": 200,
                            "asset": monnaie_locale.uuid,
                        },
                        {"moyen": PaymentMethod.CC, "montant": 150},
                    ],
                )
                verifier_egalites(vente)
        return self._cloturer_la_journee_a(heure_de_paris(2026, 3, jour, 23, 0))

    def test_fec_nombre_de_requetes_independant_du_nombre_de_ventes(self):
        """
        Le nombre de requêtes d'un export ne grandit pas avec le nombre de ventes : une
        J de 3 ventes et une J de 30 ventes, payées par les mêmes moyens (monnaie
        locale du lieu sans compte propre, CB), au même taux de TVA, coûtent le même
        nombre de requêtes. L'article est une entrée (type billet, sans catégorie de
        caisse) : son compte vient du plan par défaut (706000), que la ventilation lit
        une seule fois. Un premier export, non compté, remplit les caches de Django
        (types de contenu…) qui ne relèvent pas du FEC.
        / An export's query count does not grow with the number of sales.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        tarif_de_l_entree = creer_tarif_vendu(
            nom="Entree",
            prix_en_euros="3.50",
            taux_tva="20.00",
            categorie_article=Product.BILLET,
        )
        j_de_3_ventes = self._ventes_d_une_journee_payees_par_les_memes_moyens(
            3, 10, tarif_de_l_entree, monnaie_locale
        )
        j_de_30_ventes = self._ventes_d_une_journee_payees_par_les_memes_moyens(
            30, 11, tarif_de_l_entree, monnaie_locale
        )
        generer_fec_cloture(j_de_3_ventes)

        with CaptureQueriesContext(connection) as requetes_pour_3_ventes:
            generer_fec_cloture(j_de_3_ventes)
        with CaptureQueriesContext(connection) as requetes_pour_30_ventes:
            generer_fec_cloture(j_de_30_ventes)

        assert len(requetes_pour_30_ventes.captured_queries) == len(
            requetes_pour_3_ventes.captured_queries
        )

    def test_fec_un_compte_par_moyen_et_par_monnaie(self):
        """
        Un compte par (moyen, monnaie) : deux monnaies du lieu réglées par le même
        moyen LE. La première a son compte (419200, `MappingMonnaie`), la seconde n'en a
        pas et prend le compte du moyen (419100). Un jus payé avec chacune : 419200 au
        débit 350, 419100 au débit 350, jamais un seul compte pour les deux.
        / One account per (method, currency): same LE method, two currencies, two
        accounts.
        """
        monnaie_avec_son_compte = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        compte_de_la_monnaie = CompteComptable.objects.create(
            numero_de_compte=NUMERO_DU_COMPTE_DE_LA_MONNAIE_LOCALE,
            libelle_du_compte="Monnaie locale du lieu (test FEC)",
            nature_du_compte=CompteComptable.TIERS,
        )
        MappingMonnaie.objects.create(
            asset_uuid=monnaie_avec_son_compte.uuid,
            compte_de_tresorerie=compte_de_la_monnaie,
        )
        monnaie_sans_compte = self._monnaie("Seconde monnaie locale FEC", Asset.TLF)
        with self._heure_figee(MOMENT_DES_VENTES):
            for monnaie in [monnaie_avec_son_compte, monnaie_sans_compte]:
                vente = fabriquer_vente_encaissee(
                    origine=SaleOrigin.LABOUTIK,
                    articles=[
                        {
                            "pricesold": self.tarif_du_jus,
                            "quantite": Decimal("1"),
                            "prix_unitaire": 350,
                            "taux_tva": Decimal("20"),
                        },
                    ],
                    reglements=[
                        {
                            "moyen": PaymentMethod.LOCAL_EURO,
                            "montant": 350,
                            "asset": monnaie.uuid,
                        },
                    ],
                )
                verifier_egalites(vente)
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        ecritures = ventiler_cloture(cloture)

        # Deux jus : 707000 HT 2 × 292 = 584, 445711 TVA 2 × 58 = 116.
        # / Two juices.
        assert comptes_de_l_ecriture(ecritures[0]) == {
            NUMERO_DU_COMPTE_DE_LA_MONNAIE_LOCALE: (350, 0),
            "419100": (350, 0),
            "707000": (0, 584),
            "445711": (0, 116),
        }

    def test_fec_reglement_fed_au_compte_du_reseau(self):
        """
        Un règlement en monnaie fédérée (moyen SF) va au compte de sa monnaie : le
        compte du réseau (467000), comme le chargeur du plan relie les uuid du FED. Un
        jus de 3,50 € payé en FED : 467000 au débit 350, 707000 au crédit 292, 445711
        au crédit 58.
        / A federated currency payment (SF) goes to its currency's account (467000).
        """
        uuid_du_fed = uuid.uuid4()
        MappingMonnaie.objects.create(
            asset_uuid=uuid_du_fed,
            compte_de_tresorerie=CompteComptable.objects.get(numero_de_compte="467000"),
        )
        with self._heure_figee(MOMENT_DES_VENTES):
            vente = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": self.tarif_du_jus,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 350,
                        "taux_tva": Decimal("20"),
                    },
                ],
                reglements=[
                    {
                        "moyen": PaymentMethod.STRIPE_FED,
                        "montant": 350,
                        "asset": uuid_du_fed,
                    },
                ],
            )
            verifier_egalites(vente)
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        ecritures = ventiler_cloture(cloture)

        assert comptes_de_l_ecriture(ecritures[0]) == {
            "467000": (350, 0),
            "707000": (0, 292),
            "445711": (0, 58),
        }

    def test_fec_article_hors_ca_offert_qui_n_est_pas_une_recharge_n_ecrit_rien(self):
        """
        Seule la part offerte d'une RECHARGE écrit la paire 623400 / 419100. Un produit
        de caisse au mode « fidélité » (FD : choisi dans l'admin, affiché à la caisse,
        hors chiffre d'affaires) offert par le bouton OFFRIR, comme la caisse l'écrit
        (`offert_en_totalite`) : aucune ligne, et pas de compte demandé pour lui (le
        mode FD n'en a pas). Avec un jus vendu en espèces dans la même J, l'écriture
        CAISSE n'a que les lignes du jus.
        / Only a TOP-UP's offered part writes the 623400 / 419100 pair: an offered
        off-revenue loyalty item writes nothing.
        """
        tarif_du_produit_fidelite = creer_tarif_vendu(
            nom="Carte fidelite",
            prix_en_euros="5.00",
            taux_tva="0.00",
            methode_caisse=Product.FIDELITE,
        )
        with self._heure_figee(MOMENT_DES_VENTES):
            vente_offerte = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": tarif_du_produit_fidelite,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 500,
                        "taux_tva": Decimal("0"),
                        "offert_en_totalite": True,
                    },
                ],
            )
            verifier_egalites(vente_offerte)
            self._vendre_un_jus(PaymentMethod.CASH)
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        ligne_offerte = LigneArticle.objects.get(vente=vente_offerte)
        assert ligne_offerte.hors_chiffre_affaires
        assert ligne_offerte.part_offerte == 500

        ecritures = ventiler_cloture(cloture)

        assert len(ecritures) == 1
        assert comptes_de_l_ecriture(ecritures[0]) == {
            "530000": (350, 0),
            "707000": (0, 292),
            "445711": (0, 58),
        }

    def test_fec_un_compte_au_solde_nul_n_a_pas_de_ligne(self):
        """
        Les montants sont regroupés par compte dans une écriture ; un compte dont le
        solde tombe à 0 n'a aucune ligne. Dans une seule J et le seul journal CAISSE :
        une recharge de 10,00 € payée en CB (crédit 419100 1000), puis un plateau à
        10,00 € (TVA 20 %) payé avec cette monnaie locale du lieu (débit 419100 1000,
        par le compte du moyen LE). Le 419100 tombe à 0 : l'écriture a exactement
        trois lignes, CB 512100 au débit 1000, 707000 au crédit 833, 445711 au crédit
        167 (1000 à 20 % → HT arrondi(833,33) = 833, TVA 167).
        / An account whose balance nets to 0 has no line.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        tarif_de_la_recharge = creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="10.00",
            taux_tva="0.00",
            methode_caisse=Product.RECHARGE_EUROS,
        )
        tarif_du_plateau = self._tarif_d_une_boisson("Plateau", "10.00")
        with self._heure_figee(MOMENT_DES_VENTES):
            vente_de_la_recharge = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": tarif_de_la_recharge,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 1000,
                        "taux_tva": Decimal("0"),
                    },
                ],
                reglements=[{"moyen": PaymentMethod.CC, "montant": 1000}],
            )
            verifier_egalites(vente_de_la_recharge)
            vente_du_plateau = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": tarif_du_plateau,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 1000,
                        "taux_tva": Decimal("20"),
                    },
                ],
                reglements=[
                    {
                        "moyen": PaymentMethod.LOCAL_EURO,
                        "montant": 1000,
                        "asset": monnaie_locale.uuid,
                    },
                ],
            )
            verifier_egalites(vente_du_plateau)
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        ecritures = ventiler_cloture(cloture)

        assert len(ecritures) == 1
        assert ecritures[0]["journal"] == "CAISSE"
        assert ecritures[0]["lignes"] == [
            {
                "compte": "512100",
                "libelle": "Carte bancaire (TPE)",
                "debit": 1000,
                "credit": 0,
            },
            {
                "compte": "445711",
                "libelle": "TVA collectée 20 %",
                "debit": 0,
                "credit": 167,
            },
            {
                "compte": "707000",
                "libelle": "Ventes de marchandises",
                "debit": 0,
                "credit": 833,
            },
        ]

    def test_fec_aucune_ecriture_pour_offrir_et_points(self):
        """
        Fiche F §6, test 24 : un jus offert par le bouton OFFRIR, une vente en points,
        une recharge offerte EN POINTS (vente en points, règlement FREE) et un jus
        vendu en espèces, dans la même J. Seul le jus vendu est écrit : une écriture
        CAISSE, espèces 350 / 707000 292 / 445711 58. Ni le règlement FREE, ni les
        points, ni la recharge offerte en points (pas de 623400 / 419100) ; aucune
        écriture WEB.
        / Only the sold juice is written: no FREE, no points, no top-up offered in
        points.
        """
        points = self._monnaie(NOM_DES_POINTS, Asset.FID)
        with self._heure_figee(MOMENT_DES_VENTES):
            self._jus_offert_par_le_bouton_offrir()
            self._vente_en_points(points)
            self._recharge_offerte_en_points(points)
            self._vendre_un_jus(PaymentMethod.CASH)
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        ecritures = ventiler_cloture(cloture)

        assert len(ecritures) == 1
        assert ecritures[0]["journal"] == "CAISSE"
        assert comptes_de_l_ecriture(ecritures[0]) == {
            "530000": (350, 0),
            "707000": (0, 292),
            "445711": (0, 58),
        }

    def test_fec_jetons_cadeau_d8_bis(self):
        """
        Fiche F §6, test 24b (D8 bis) : quatre J, une par opération, pour voir chaque
        paire de comptes :
        - recharge offerte de 10,00 € → débit 623400 1000 / crédit 419100 1000 ;
        - bière de 3,00 € en jetons (monnaie TNF du lieu, sans compte propre : le
          compte du moyen LG) → débit 419100 300 / crédit 707900 300 (hors TVA, la
          bière est pourtant rangée dans « Boissons ») ;
        - carte vidée avec 2,00 € de jetons repris → débit 419100 200 / crédit
          623400 200 ;
        - avoir de la bière en jetons (bouton « Avoir », journal ADMIN) → débit
          707900 300 / crédit 419100 300.
        Chaque écriture est équilibrée.
        / Four J, one per operation: each pair of accounts of the gift tokens.
        """
        jetons_cadeau = self._monnaie(NOM_DES_JETONS_CADEAU, Asset.TNF)

        with self._heure_figee(heure_de_paris(2026, 3, 10, 18, 0)):
            self._recharge_offerte(1000)
        j_de_la_recharge = self._cloturer_la_journee_a(
            heure_de_paris(2026, 3, 10, 18, 30)
        )
        with self._heure_figee(heure_de_paris(2026, 3, 10, 19, 0)):
            ligne_de_la_biere = self._biere_payee_en_jetons(jetons_cadeau)
        j_de_la_biere = self._cloturer_la_journee_a(heure_de_paris(2026, 3, 10, 19, 30))
        with self._heure_figee(heure_de_paris(2026, 3, 10, 20, 0)):
            self._vidage_avec_jetons_repris(jetons_cadeau, 200)
        j_du_vidage = self._cloturer_la_journee_a(heure_de_paris(2026, 3, 10, 20, 30))
        with self._heure_figee(heure_de_paris(2026, 3, 10, 21, 0)):
            self._avoir_par_le_bouton_de_l_admin(
                ligne_de_la_biere, moyen_rembourse=None
            )
        j_de_l_avoir = self._cloturer_la_journee_a(heure_de_paris(2026, 3, 10, 21, 30))

        ecritures_attendues_par_j = [
            (j_de_la_recharge, "CAISSE", {"623400": (1000, 0), "419100": (0, 1000)}),
            (j_de_la_biere, "CAISSE", {"419100": (300, 0), "707900": (0, 300)}),
            (j_du_vidage, "CAISSE", {"419100": (200, 0), "623400": (0, 200)}),
            (j_de_l_avoir, "ADMIN", {"707900": (300, 0), "419100": (0, 300)}),
        ]
        for cloture, journal_attendu, comptes_attendus in ecritures_attendues_par_j:
            ecritures = ventiler_cloture(cloture)
            assert len(ecritures) == 1, cloture.numero_sequentiel
            assert ecritures[0]["journal"] == journal_attendu
            assert comptes_de_l_ecriture(ecritures[0]) == comptes_attendus

    # ------------------------------------------------------------------
    # 25, 25b — Le mois, la date de début de service
    # / 25, 25b — The month, the start-of-service date
    # ------------------------------------------------------------------

    def _quatre_journees_de_janvier_a_mars(self):
        """
        Quatre J et leurs ventes de jus en espèces, en heure de Paris :
        - J n° 1 : ventes le 31 janvier à 22 h et le 1ᵉʳ février à 1 h 30, Z le
          1ᵉʳ février à 2 h (datée du 31 janvier, elle déborde sur février) ;
        - J n° 2 : vente le 10 février à 20 h, Z à 23 h ;
        - J n° 3 : vente le 28 février à 21 h, Z à 22 h ;
        - J n° 4 : vente le 1ᵉʳ mars à 0 h 30, Z à 1 h. Elle commence le 28 février à
          22 h (fin de la J n° 3) : elle chevauche février, mais elle est datée du
          1ᵉʳ mars, le premier jour du mois suivant.
        / Four J around month ends.

        :return: (j_n1, j_n2, j_n3, j_n4)
        """
        with self._heure_figee(heure_de_paris(2026, 1, 31, 22, 0)):
            self._vendre_un_jus(PaymentMethod.CASH)
        with self._heure_figee(heure_de_paris(2026, 2, 1, 1, 30)):
            self._vendre_un_jus(PaymentMethod.CASH)
        j_n1 = self._cloturer_la_journee_a(heure_de_paris(2026, 2, 1, 2, 0))

        with self._heure_figee(heure_de_paris(2026, 2, 10, 20, 0)):
            self._vendre_un_jus(PaymentMethod.CASH)
        j_n2 = self._cloturer_la_journee_a(heure_de_paris(2026, 2, 10, 23, 0))

        with self._heure_figee(heure_de_paris(2026, 2, 28, 21, 0)):
            self._vendre_un_jus(PaymentMethod.CASH)
        j_n3 = self._cloturer_la_journee_a(heure_de_paris(2026, 2, 28, 22, 0))

        with self._heure_figee(heure_de_paris(2026, 3, 1, 0, 30)):
            self._vendre_un_jus(PaymentMethod.CASH)
        j_n4 = self._cloturer_la_journee_a(heure_de_paris(2026, 3, 1, 1, 0))
        return j_n1, j_n2, j_n3, j_n4

    def test_fec_mois_concatene_les_journees(self):
        """
        Fiche F §6, test 25 : le FEC du mois de février = les écritures des J DATÉES
        en février, dans l'ordre : la J n° 2 (10 février) et la J n° 3 (28 février).
        Pas la J n° 1, datée du 31 janvier, même si une de ses ventes est du
        1ᵉʳ février. Pas la J n° 4, datée du 1ᵉʳ mars (premier jour du mois suivant),
        même si elle commence le 28 février : une J n'est jamais dans deux mois. Les
        lignes sont exactement celles des FEC des deux J, `EcritureNum` compris : une
        écriture garde son numéro d'un export à l'autre. Deux écritures distinctes.
        / February's FEC = the entries of the J dated in February, not the one dated
        on the first day of March; same lines, EcritureNum included.
        """
        _j_n1, j_n2, j_n3, _j_n4 = self._quatre_journees_de_janvier_a_mars()
        mois_de_fevrier = self._cloturer_le_mois_precedent_a(
            heure_de_paris(2026, 3, 1, 5, 0)
        )

        lignes_du_fec_du_mois = self._lignes_du_fec(mois_de_fevrier)
        lignes_des_fec_des_journees = self._lignes_du_fec(j_n2) + self._lignes_du_fec(
            j_n3
        )

        assert lignes_du_fec_du_mois == lignes_des_fec_des_journees
        numeros_d_ecriture_du_mois = set()
        for ligne in lignes_du_fec_du_mois:
            numeros_d_ecriture_du_mois.add(ligne["EcritureNum"])
        assert len(numeros_d_ecriture_du_mois) == 2

    def test_fec_j_a_cheval_sur_deux_mois_datee_du_debut_de_service(self):
        """
        Fiche F §6, test 25b : la J n° 1 va du 31 janvier à 22 h au 1ᵉʳ février à
        2 h. Son écriture est datée du 31 janvier (date locale de sa première vente),
        jamais du jour de la clôture. Elle compte ses deux ventes (espèces 700) et
        elle va dans le FEC de janvier. Pour la J de numéro n (ventes de caisse sans
        point de vente, journal CAISSE) : `EcritureNum` vaut « n-CAISSE », `PieceRef`
        vaut « n », `EcritureLib` vaut « Clôture J n° n — Caisse » ; `PieceDate` et
        `ValidDate` valent la date de début de service.
        / The J from Jan 31 10 pm to Feb 1 2 am is dated Jan 31 and goes to January;
        exact entry number, piece reference and label.
        """
        with self._heure_figee(heure_de_paris(2026, 1, 31, 22, 0)):
            self._vendre_un_jus(PaymentMethod.CASH)
        with self._heure_figee(heure_de_paris(2026, 2, 1, 1, 30)):
            self._vendre_un_jus(PaymentMethod.CASH)
        j_a_cheval = self._cloturer_la_journee_a(heure_de_paris(2026, 2, 1, 2, 0))
        mois_de_janvier = self._cloturer_le_mois_precedent_a(
            heure_de_paris(2026, 2, 1, 5, 0)
        )

        lignes_de_la_j = self._lignes_du_fec(j_a_cheval)

        assert soldes_debiteurs_du_fec(lignes_de_la_j)["530000"] == 700
        numero_de_la_j = j_a_cheval.numero_sequentiel
        for ligne in lignes_de_la_j:
            assert ligne["JournalCode"] == "CAISSE", ligne
            assert ligne["EcritureNum"] == f"{numero_de_la_j}-CAISSE", ligne
            assert ligne["PieceRef"] == str(numero_de_la_j), ligne
            assert ligne["EcritureLib"] == f"Clôture J n° {numero_de_la_j} — Caisse"
            assert ligne["EcritureDate"] == "20260131", ligne
            assert ligne["PieceDate"] == "20260131", ligne
            assert ligne["ValidDate"] == "20260131", ligne

        assert self._lignes_du_fec(mois_de_janvier) == lignes_de_la_j

    def test_fec_date_de_la_j_dans_le_fuseau_fige_dans_son_rapport(self):
        """
        La date de début de service se calcule dans le fuseau figé dans l'en-tête du
        rapport de la J, pas dans le fuseau actuel du lieu. La J n° 1 commence le
        31 janvier à 22 h à Paris (21 h UTC). Le lieu passe ensuite à
        « Pacific/Auckland » (UTC+13 en février : il y serait déjà le 1ᵉʳ février à
        10 h). L'écriture reste datée du 31 janvier.
        / The start-of-service date uses the time zone frozen in the J's report.
        """
        with self._heure_figee(heure_de_paris(2026, 1, 31, 22, 0)):
            self._vendre_un_jus(PaymentMethod.CASH)
        j_n1 = self._cloturer_la_journee_a(heure_de_paris(2026, 2, 1, 2, 0))
        assert j_n1.rapport_json["en_tete"]["fuseau_horaire"] == "Europe/Paris"

        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "Pacific/Auckland"
        configuration.save()

        lignes_du_fec = self._lignes_du_fec(j_n1)
        for ligne in lignes_du_fec:
            assert ligne["EcritureDate"] == "20260131", ligne

    def test_fec_nom_du_fichier_a_la_date_locale(self):
        """
        Le nom du fichier porte une date locale. La J n° 1 va du 31 janvier à 22 h au
        1ᵉʳ février à 2 h, heure de Paris (sa fin, en UTC, est le 1ᵉʳ février à 1 h) :
        « FEC-20260131-1.txt », sa date de début de service. La M de janvier (n° 2) :
        « FEC-20260131-2.txt », son dernier jour local.
        / The file name carries a local date: the J's start of service, the period's
        last local day.
        """
        with self._heure_figee(heure_de_paris(2026, 1, 31, 22, 0)):
            self._vendre_un_jus(PaymentMethod.CASH)
        with self._heure_figee(heure_de_paris(2026, 2, 1, 1, 30)):
            self._vendre_un_jus(PaymentMethod.CASH)
        j_a_cheval = self._cloturer_la_journee_a(heure_de_paris(2026, 2, 1, 2, 0))
        mois_de_janvier = self._cloturer_le_mois_precedent_a(
            heure_de_paris(2026, 2, 1, 5, 0)
        )

        _contenu, nom_du_fichier_de_la_j, _type = generer_fec_cloture(j_a_cheval)
        _contenu, nom_du_fichier_du_mois, _type = generer_fec_cloture(mois_de_janvier)

        assert nom_du_fichier_de_la_j == "FEC-20260131-1.txt"
        assert nom_du_fichier_du_mois == "FEC-20260131-2.txt"

    def test_fec_d_une_periode_refuse_en_nommant_la_j_en_cause(self):
        """
        Un compte manquant dans le FEC d'une période nomme la J en cause : une planche
        sans catégorie (aucun compte) vendue le 10 février, la J n° 1, la M de février.
        Le refus du FEC du mois dit « Clôture J n° 1 ».
        / A missing account in a period's FEC names the J at fault.
        """
        tarif_de_la_planche = creer_tarif_vendu(
            nom="Planche sans categorie",
            prix_en_euros="8.00",
            taux_tva="10.00",
            methode_caisse=Product.VENTE,
        )
        with self._heure_figee(heure_de_paris(2026, 2, 10, 20, 0)):
            vente = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": tarif_de_la_planche,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 800,
                        "taux_tva": Decimal("10"),
                    },
                ],
                reglements=[{"moyen": PaymentMethod.CASH, "montant": 800}],
            )
            verifier_egalites(vente)
        j_n1 = self._cloturer_la_journee_a(heure_de_paris(2026, 2, 10, 23, 0))
        mois_de_fevrier = self._cloturer_le_mois_precedent_a(
            heure_de_paris(2026, 3, 1, 5, 0)
        )

        with self.assertRaises(CompteComptableManquant) as refus:
            generer_fec_cloture(mois_de_fevrier)

        assert f"Clôture J n° {j_n1.numero_sequentiel} :" in str(refus.exception)

    # ------------------------------------------------------------------
    # Plan du moment, TVA par taux, code journal
    # / Current chart, VAT by rate, journal code
    # ------------------------------------------------------------------

    def test_fec_recalcule_avec_le_plan_du_moment(self):
        """
        Le FEC est recalculé à chaque export avec le plan comptable du moment : un jus
        vendu, la J, un premier export (HT au 707000) ; puis la catégorie
        « Boissons » est reliée à un nouveau compte 707100 ; le second export écrit
        le HT au 707100 et plus rien au 707000.
        / The FEC is recomputed at each export with the current chart.
        """
        with self._heure_figee(MOMENT_DES_VENTES):
            self._vendre_un_jus(PaymentMethod.CASH)
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        soldes_du_premier_export = soldes_debiteurs_du_fec(self._lignes_du_fec(cloture))
        assert soldes_du_premier_export["707000"] == -292

        compte_des_ventes_du_bar = CompteComptable.objects.create(
            numero_de_compte="707100",
            libelle_du_compte="Ventes du bar (test FEC)",
            nature_du_compte=CompteComptable.VENTE,
        )
        self.categorie_des_boissons.compte_comptable = compte_des_ventes_du_bar
        self.categorie_des_boissons.save()

        soldes_du_second_export = soldes_debiteurs_du_fec(self._lignes_du_fec(cloture))
        assert soldes_du_second_export["707100"] == -292
        assert "707000" not in soldes_du_second_export

    def test_compte_de_tva_cherche_par_taux(self):
        """
        `compte_de_tva_pour_taux` cherche le compte de TVA par son TAUX, jamais par son
        numéro (fiche E §3.4) : 20 % → 445711 ; le compte à 5,5 % renuméroté 445790
        est toujours trouvé ; sans compte à 10 %, `CompteComptableManquant`.
        / The VAT account is looked up by rate, never by number.
        """
        assert compte_de_tva_pour_taux(Decimal("20.00")).numero_de_compte == "445711"

        compte_a_5_5 = CompteComptable.objects.get(
            nature_du_compte=CompteComptable.TVA, taux_de_tva=Decimal("5.50")
        )
        compte_a_5_5.numero_de_compte = "445790"
        compte_a_5_5.save()
        assert compte_de_tva_pour_taux(Decimal("5.50")).numero_de_compte == "445790"

        CompteComptable.objects.filter(
            nature_du_compte=CompteComptable.TVA, taux_de_tva=Decimal("10.00")
        ).delete()
        with self.assertRaises(CompteComptableManquant):
            compte_de_tva_pour_taux(Decimal("10.00"))

    def test_fec_ecrit_la_tva_au_compte_trouve_par_son_taux(self):
        """
        Le compte de TVA à 20 % renuméroté 445720 par le lieu : la TVA d'un jus vendu
        (58) est écrite au 445720.
        / A renumbered 20 % VAT account receives the juice's VAT.
        """
        compte_a_20 = CompteComptable.objects.get(
            nature_du_compte=CompteComptable.TVA, taux_de_tva=Decimal("20.00")
        )
        compte_a_20.numero_de_compte = "445720"
        compte_a_20.save()
        with self._heure_figee(MOMENT_DES_VENTES):
            self._vendre_un_jus(PaymentMethod.CASH)
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        soldes = soldes_debiteurs_du_fec(self._lignes_du_fec(cloture))

        assert soldes["445720"] == -58
        assert "445711" not in soldes

    def test_fec_aucune_ligne_de_tva_quand_la_tva_vaut_zero(self):
        """
        Un taux de 0 n'écrit pas de TVA : une adhésion à 15,00 € (TVA 0) payée par
        chèque n'a que deux lignes, chèques 511200 au débit 1500, cotisations 756000
        au crédit 1500. Aucun compte de TVA.
        / A 0 % rate writes no VAT line.
        """
        with self._heure_figee(MOMENT_DES_VENTES):
            self._adhesion_payee_par_cheque()
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        ecritures = ventiler_cloture(cloture)

        assert len(ecritures) == 1
        assert comptes_de_l_ecriture(ecritures[0]) == {
            "511200": (1500, 0),
            "756000": (0, 1500),
        }

    def test_fec_utilise_un_compte_de_tva_inactif_seul(self):
        """
        « Inactif » (`est_actif=False`) cache seulement le compte des menus de choix :
        l'export s'en sert quand même. Le compte à 20 % (445711), seul à ce taux, est
        désactivé ; un jus à 20 % est vendu : sa TVA (58) va au 445711, et « Plan
        complet ? » ne signale rien sur la TVA à 20 %.
        / An inactive VAT account alone at its rate is still used by the FEC, and
        "Complete plan?" reports nothing.
        """
        CompteComptable.objects.filter(
            nature_du_compte=CompteComptable.TVA, taux_de_tva=Decimal("20.00")
        ).update(est_actif=False)
        with self._heure_figee(MOMENT_DES_VENTES):
            self._vendre_un_jus(PaymentMethod.CASH)
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        ecritures = ventiler_cloture(cloture)

        assert comptes_de_l_ecriture(ecritures[0])["445711"] == (0, 58)

        with translation.override("fr"):
            manques = ce_qui_manque_pour_exporter()
        phrases_sur_la_tva_a_20 = []
        for manque in manques:
            if "TVA à 20 %" in manque["phrase"]:
                phrases_sur_la_tva_a_20.append(manque["phrase"])
        assert phrases_sur_la_tva_a_20 == []

    def test_fec_prefere_le_compte_de_tva_actif_meme_de_numero_plus_grand(self):
        """
        Deux comptes de TVA à 20 % : le 445711, désactivé, et un 445799 actif. Le FEC
        prend l'actif, même si son numéro est plus grand : la TVA d'un jus (58) va au
        445799, rien au 445711.
        / With an active and an inactive account at one rate, the active one wins,
        even with a larger number.
        """
        CompteComptable.objects.filter(
            nature_du_compte=CompteComptable.TVA, taux_de_tva=Decimal("20.00")
        ).update(est_actif=False)
        CompteComptable.objects.create(
            numero_de_compte="445799",
            libelle_du_compte="TVA collectée 20 % (compte actif du lieu)",
            nature_du_compte=CompteComptable.TVA,
            taux_de_tva=Decimal("20.00"),
        )
        with self._heure_figee(MOMENT_DES_VENTES):
            self._vendre_un_jus(PaymentMethod.CASH)
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        comptes = comptes_de_l_ecriture(ventiler_cloture(cloture)[0])

        assert comptes["445799"] == (0, 58)
        assert "445711" not in comptes

    def test_fec_d_une_j_sans_vente_n_a_que_l_en_tete(self):
        """
        Une J sans plage de ventes (aucune vente, écrite à la main : le filet n'en crée
        jamais) : son FEC n'a que la ligne d'en-tête, sans erreur. Le nom du fichier
        prend la date locale de sa fin (10 mars à 23 h, heure de Paris).
        / A J without sales: its FEC only has the header line; the file name takes its
        local end date.
        """
        j_sans_vente = ClotureCaisse.objects.create(
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            numero_sequentiel=990001,
            datetime_debut=heure_de_paris(2026, 3, 10, 18, 0),
            datetime_fin=MOMENT_DU_Z,
            rapport_json={"en_tete": {"fuseau_horaire": "Europe/Paris"}},
        )

        contenu_en_octets, nom_du_fichier, _type = generer_fec_cloture(j_sans_vente)

        assert self._lignes_du_fec(j_sans_vente) == []
        assert contenu_en_octets.decode("utf-8") == "\t".join(COLONNES_DU_FEC)
        assert nom_du_fichier == "FEC-20260310-990001.txt"

    def _journee_d_une_entree_payee_par_les_memes_moyens(self, tarif_vendu, monnaie, jour):
        """
        Le `jour` (un jour de 2026, date) à 18 h : une entrée à 3,50 € (TVA 20 %) payée
        2,00 € en monnaie locale du lieu (moyen LE) et 1,50 € en CB ; puis la J à 23 h.
        / One entry paid by the same methods on one day, then the J.
        """
        with self._heure_figee(
            heure_de_paris(jour.year, jour.month, jour.day, 18, 0)
        ):
            vente = fabriquer_vente_encaissee(
                origine=SaleOrigin.LABOUTIK,
                articles=[
                    {
                        "pricesold": tarif_vendu,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 350,
                        "taux_tva": Decimal("20"),
                    },
                ],
                reglements=[
                    {
                        "moyen": PaymentMethod.LOCAL_EURO,
                        "montant": 200,
                        "asset": monnaie.uuid,
                    },
                    {"moyen": PaymentMethod.CC, "montant": 150},
                ],
            )
            verifier_egalites(vente)
        return self._cloturer_la_journee_a(
            heure_de_paris(jour.year, jour.month, jour.day, 23, 0)
        )

    def test_fec_d_un_mois_comptes_lus_une_seule_fois(self):
        """
        Les comptes sont lus une fois pour tout l'export, pas une fois par J. Février
        a 2 J, mars en a 4, avec les mêmes moyens (monnaie locale du lieu sans compte
        propre, CB) et le même taux (20 %) ; l'entrée (type billet, sans catégorie)
        prend son compte dans le plan par défaut. L'écart de requêtes entre les deux
        FEC est borné par J : 2 J de plus × 4 requêtes par J (la première vente de la
        J pour sa date, puis ses ventes, leurs règlements et leurs articles) = 8 au
        plus. Si les comptes étaient relus à chaque J, l'écart serait bien plus grand
        (compte du plan par défaut, comptes des moyens et de la monnaie, compte de TVA).
        Un premier export, non compté, remplit les caches de Django.
        / Accounts are read once per export: the query gap between a 2-J and a 4-J
        month is bounded by 4 queries per extra J.
        """
        monnaie_locale = self._monnaie(NOM_DE_LA_MONNAIE_LOCALE, Asset.TLF)
        tarif_de_l_entree = creer_tarif_vendu(
            nom="Entree",
            prix_en_euros="3.50",
            taux_tva="20.00",
            categorie_article=Product.BILLET,
        )
        jours_de_fevrier = [date(2026, 2, 10), date(2026, 2, 11)]
        for jour in jours_de_fevrier:
            self._journee_d_une_entree_payee_par_les_memes_moyens(
                tarif_de_l_entree, monnaie_locale, jour
            )
        mois_de_fevrier = self._cloturer_le_mois_precedent_a(
            heure_de_paris(2026, 3, 1, 5, 0)
        )
        jours_de_mars = [
            date(2026, 3, 10),
            date(2026, 3, 11),
            date(2026, 3, 12),
            date(2026, 3, 13),
        ]
        for jour in jours_de_mars:
            self._journee_d_une_entree_payee_par_les_memes_moyens(
                tarif_de_l_entree, monnaie_locale, jour
            )
        mois_de_mars = self._cloturer_le_mois_precedent_a(
            heure_de_paris(2026, 4, 1, 5, 0)
        )
        generer_fec_cloture(mois_de_fevrier)

        with CaptureQueriesContext(connection) as requetes_du_mois_de_2_j:
            generer_fec_cloture(mois_de_fevrier)
        with CaptureQueriesContext(connection) as requetes_du_mois_de_4_j:
            generer_fec_cloture(mois_de_mars)

        # 2 J de plus, 4 requêtes au plus par J : un écart de 8 au plus.
        # / 2 more J, at most 4 queries per J: a gap of 8 at most.
        nombre_de_j_en_plus = 2
        requetes_au_plus_par_j = 4
        ecart_de_requetes = len(requetes_du_mois_de_4_j.captured_queries) - len(
            requetes_du_mois_de_2_j.captured_queries
        )
        assert ecart_de_requetes <= nombre_de_j_en_plus * requetes_au_plus_par_j, (
            ecart_de_requetes
        )
        assert len(self._lignes_du_fec(mois_de_mars)) > 0

    def test_plan_complet_nomme_un_code_journal_renseigne_sans_lettre(self):
        """
        « Plan complet ? » : un point de vente dont le code journal RENSEIGNÉ ne garde
        aucune lettre (« 123 ») est signalé par une phrase sur son code, pas sur son
        nom (son nom « Bar du haut » a des lettres).
        / "Complete plan?" names a set journal code without letters, not the name.
        """
        self._point_de_vente("Bar du haut", code_journal="123")

        with translation.override("fr"):
            manques = ce_qui_manque_pour_exporter()

        phrases_sur_le_point_de_vente = []
        for manque in manques:
            if "Bar du haut" in manque["phrase"]:
                phrases_sur_le_point_de_vente.append(manque["phrase"])
        assert len(phrases_sur_le_point_de_vente) == 1, manques
        phrase = phrases_sur_le_point_de_vente[0]
        assert "« 123 »" in phrase
        assert "son nom ne contient aucune lettre" not in phrase

    def test_code_journal_renseigne_avec_chiffres_et_accents_nettoye(self):
        """
        Le code journal renseigné d'un point de vente suit la même règle que le code
        dérivé du nom : majuscules, sans accent, lettres A à Z seulement, 10 au plus.
        Un code qui ne garde aucune lettre lève `CompteComptableManquant`. Les codes
        sont posés sans passer par l'admin (son validateur ne tourne pas).
        / A set journal code follows the name rule; no letter left raises.
        """
        code_nettoye_par_code_renseigne = {
            "bar2": "BAR",
            "Été": "ETE",
            "b-a r": "BAR",
            "ÉTÉ26": "ETE",
            "Buvette1": "BUVETTE",
        }
        for code_renseigne, code_nettoye in code_nettoye_par_code_renseigne.items():
            point_de_vente = self._point_de_vente(
                f"Point de vente {identifiant_unique()}", code_journal=code_renseigne
            )
            assert code_journal_du_point_de_vente(point_de_vente) == code_nettoye, (
                code_renseigne
            )

        point_de_vente_au_code_sans_lettre = self._point_de_vente(
            "Bar du haut", code_journal="123"
        )
        with self.assertRaises(CompteComptableManquant):
            code_journal_du_point_de_vente(point_de_vente_au_code_sans_lettre)

        # Le code dérivé du nom ne change pas. / The name-derived code is unchanged.
        point_de_vente_sans_code = self._point_de_vente("Buvette d'Été 2")
        assert code_journal_du_point_de_vente(point_de_vente_sans_code) == "BUVETTEDET"
