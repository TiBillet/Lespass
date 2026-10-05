"""
La « part payée en jetons » d'un article vendu (`LigneArticle.part_en_jetons`) et tous
ceux qui la lisent (chantier 05, session H-1b-1).
/ The "part paid in tokens" of a sold item and every reader of it (chantier 05,
session H-1b-1).

LOCALISATION : tests/pytest/test_part_en_jetons.py

RÈGLE MÉTIER TESTÉE
Un jeton cadeau dépensé (monnaie des bénévoles, moyen LG) est une VENTE ordinaire,
dans le chiffre d'affaires, hors TVA, au compte 707900 (D8 bis). Ce n'est PAS de
l'offert : la part offerte ne bouge pas, et le règlement LG compte dans les deux
égalités de la vente.
Un article payé en partie en jetons et en partie en argent est UNE ligne (Q-H1). Elle
porte un champ entier, en centimes : la part payée en jetons.
- la formule (une seule dans le projet, `calculer_montants_article`) :
    net      = total catalogue − part offerte
    HT       = part en jetons + arrondi_demi_haut((net − part en jetons) × 100 / (100 + taux))
    TVA      = net − HT
  La part en jetons reste entre 0 et le net (entre le net et 0 pour un avoir) ;
- la base refuse une part en jetons hors bornes, et toute part en jetons sur une
  ligne hors chiffre d'affaires ; une ligne d'une vente réglée ne change plus sa part
  en jetons ; l'empreinte de la vente la couvre ;
- la caisse et la tireuse écrivent UNE ligne par article : sa `part_en_jetons` est la
  somme de ses débits en jetons, au taux du produit ;
- le rapport met la part en jetons au taux « 0.00 », le reste à son taux ; le FEC
  écrit la part en jetons au 707900, le reste au compte de la catégorie, la TVA du
  reste au compte de son taux ; le ticket fait la même coupe ; l'archive fiscale porte
  la colonne ;
- l'avoir d'une ligne mixte rend un règlement LG (la part en jetons, monnaie et carte
  du règlement LG de la vente d'origine) et le reste en argent ; l'avoir d'une partie
  de la quantité d'une ligne avec une part en jetons est refusé, sauf pour une ligne
  ENTIÈREMENT en jetons ;
- l'avoir de jetons payés par plusieurs cartes d'une même monnaie rend UN règlement
  LG, de cette monnaie, sans carte ; des jetons de plusieurs monnaies dans une vente :
  l'avoir est refusé, dès l'écran (l'aperçu annonce ce que le POST fera) ;
- « Remboursé par » : une ligne mixte a de l'argent à rendre (net − part en jetons) ;
  une ligne entièrement en jetons n'en a pas ;
- une vente en points n'a jamais de part en jetons ; un article hors chiffre
  d'affaires non plus ;
- le CA par taux ne retire un taux que si TOUTES ses lignes sont entièrement en
  jetons : un taux à 0 par une vente et son avoir reste affiché ;
- « Plan complet ? » ne lit pas le moyen de la ligne pour les jetons ; il exige le
  707900 dès qu'un article a une part en jetons, et n'exige pas de compte de TVA pour
  un taux dont les lignes n'ont aucune TVA ;
- l'ancien rapport de la caisse (`laboutik/reports.py`, qui recalcule la TVA depuis le
  taux) n'est plus joignable : ni sa page temps réel, ni la liste de l'ancienne
  clôture de la caisse, ni une entrée du menu.
/ A spent gift token is an ordinary sale, 0 % VAT, account 707900. A mixed item is ONE
line with a "part paid in tokens" field; every reader (formula, database, fingerprint,
register, tap, report, FEC, receipt, archive, credit notes, "Refunded by", "Complete
plan?") reads that field, never the line's payment method. The old register report
is no longer reachable.

LA VENTE « À LA FORME DE DEMAIN »
Une bière à 5,00 € (TVA 20 %) payée 3,00 € en jetons cadeau et 2,00 € en monnaie
locale : UNE ligne, quantité 1, prix 500, part en jetons 300, moyen de la ligne VIDE.
Deux règlements : jetons (LG) 300 + monnaie locale (LE) 200, avec la monnaie et la
carte du client. Écrite par le service de vente (`tests/pytest/fabriques_vente.py`),
comme la caisse l'écrira après la fusion (H-1b-2). Le produit est rangé dans une
catégorie de caisse reliée au compte 707000.
/ Tomorrow's shape: ONE line (500, tokens 300), empty line method, payments LG 300 +
LE 200, written by the sale service.

CONTRAT SUPPOSÉ (ce que ces tests attendent du code)
- `calculer_montants_article(..., part_en_jetons=...)` et
  `ajouter_article(vente, ..., part_en_jetons=...)` (BaseBillet/services_vente.py) ;
  un `float`, une part hors bornes : `ValueError` ;
- le champ `LigneArticle.part_en_jetons` (entier, défaut 0) ;
- la colonne `part_en_jetons` dans `articles.csv` de l'archive fiscale
  (laboutik/archivage.py `COLONNES_ARTICLES`) ;
- le refus de l'avoir partiel contient « rembourser l'article entier ».
/ Assumed contract: the service parameter, the model field, the archive column, the
refusal text.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin
(tests/PIEGES.md 13.1), rien ne reste en base de dev. La caisse est activée EN MÉMOIRE
par `configuration_modifiee()` (tests/PIEGES.md 13.22). Stripe (session, catalogue) et
Celery sont simulés (tests/PIEGES.md 13.3, 13.4). Le client est créé dans chaque test,
dans le lieu (tests/PIEGES.md 13.10). La tireuse : l'ancien Fedow est simulé (solde
nul, aucun débit, aucun envoi réseau).
Base partagée, et non schéma dédié : chaque test ne lit que SES ventes. Le rapport est
lu sur une période d'une microseconde autour de l'encaissement de la vente ; le FEC
sur une clôture J en mémoire dont la plage est le numéro de la vente ; la chaîne des
empreintes sur la plage de ce numéro ; « Plan complet ? » par le nom unique du produit.
/ Rolled back per test; register module on in memory; Stripe and Celery faked. Each
test only reads its own sales (one-microsecond report period, in-memory J closure,
chain range of one sale, unique product name).

D'OÙ VIENNENT LES VALEURS ATTENDUES (calculées à la main)
- 500 à 20 %, jetons 300 : HT = 300 + arrondi(200 × 100 / 120 = 166,67) = 467, TVA 33 ;
- 500 à 20 %, jetons 500 : HT = 500 + 0 = 500, TVA 0 ;
- 500 à 20 %, jetons 0 : HT = arrondi(500 × 100 / 120 = 416,67) = 417, TVA 83 ;
- le reste 200 à 20 % : HT 167, TVA 33 ;
- tireuse : 50 cl à 8 €/L = 400, payés 100 en jetons + 300 en monnaie locale ; part
  jetons HT 100, TVA 0 ; part monnaie locale HT = arrondi(300 / 1,2) = 250, TVA 50 ;
- deux bières = 1000 ; une bière rendue = −500.
/ Hand-computed values.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-H-retrait.md (§2, §2.1,
§5 test 2) ; CHANTIER-05-montants-entiers.md (§2, D8 bis, D10, D13) ;
CHANTIER-05-SUIVI.md (§4 relecture Opus de la spec H-1, §5 Q-H1) ; brief
CHANTIER-05-briefs/05-H-1b-1.md et 05-H-1b-1-bis.md.

Lancer / Run : make test ARGS="tests/pytest/test_part_en_jetons.py"
"""

import uuid as uuid_module
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.db import IntegrityError, transaction
from django.test import Client as ClientHttpDjango
from django.test import RequestFactory
from django.utils import translation
from django_tenants.utils import tenant_context

from Administration.admin import dashboard
from BaseBillet.models import (
    CategorieProduct,
    LigneArticle,
    PaymentMethod,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Vente
from BaseBillet.services_vente import (
    ajouter_article,
    calculer_montants_article,
    ecrire_la_vente_d_avoir_d_une_ligne,
    ligne_sans_argent_a_rendre,
    ouvrir_vente,
)
from comptabilite.models import ClotureCaisse
from comptabilite.rapport import RapportDesVentes
from comptabilite.ventilation import ventiler_cloture
from fabriques_panier import (
    catalogue_stripe_simule,
    configuration_modifiee,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_vente import (
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from laboutik.integrity import verifier_chaine_ventes
from laboutik.models import CompteComptable, LaboutikConfiguration
from laboutik.plan_comptable import ce_qui_manque_pour_exporter
from laboutik.printing.formatters import formatter_ticket_vente
from QrcodeCashless.models import CarteCashless
from test_caisse_ecrit_la_vente import (
    ajouter_un_solde_sur_la_carte,
    article_dans_l_archive_lne,
    cle_de_panier,
    creer_un_article_de_caisse,
    monnaie_cadeau_du_lieu,
    monnaie_locale_du_lieu,
    nouvelle_cle_d_idempotence,
    payer_par_la_carte_du_client,
    reglements_de_la_vente,
    retrouver_la_vente_de_la_cle,
)
from test_caracterisation_caisse import (
    creer_un_point_de_vente,
    creer_une_carte_nfc_chargee,
)
from test_caracterisation_en_ligne import creer_un_administrateur_du_lieu
from test_tireuse_ecrit_la_vente import (
    DOMAINE_DU_LIEU_PARTAGE,
    _creer_une_carte,
    _creer_une_tireuse,
    _la_vente_du_tirage,
    _monnaie_du_lieu,
    _servir_un_tirage,
)

pytestmark = pytest.mark.django_db

# Le début du texte d'une anomalie « empreinte fausse » (laboutik/integrity.py).
# / The start of a "wrong fingerprint" anomaly text.
DEBUT_DE_L_ANOMALIE_EMPREINTE_FAUSSE = "Empreinte fausse"

# Le refus d'un avoir sur une partie de la quantité d'un article avec une part en
# jetons (même consigne que pour une part offerte).
# / The refusal of a partial credit note on an item with a token part.
REFUS_DE_L_AVOIR_PARTIEL = "rembourser l'article entier"


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant, mock_stripe):
    """
    Le lieu `lespass`, caisse activée en mémoire, avec Stripe (session, catalogue) et
    Celery simulés pendant tout le test.
    / The `lespass` venue, register on in memory, Stripe and Celery faked.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with catalogue_stripe_simule():
                with taches_celery_enregistrees() as taches_demandees:
                    yield SimpleNamespace(
                        tenant=tenant,
                        taches_demandees=taches_demandees,
                    )


@pytest.fixture
def ancien_fedow_sans_solde_ni_debit():
    """
    L'ancien Fedow (serveur distant) pour la tireuse : lieu relié, solde distant nul.
    Un débit distant ou un envoi HTTP réel fait échouer le test. Les soldes lus par la
    tireuse restent ceux des monnaies locales du test.
    / The old Fedow for the tap: linked, zero balance; a remote debit or a real HTTP
    call fails the test.
    """
    debit_distant_interdit = mock.MagicMock(
        side_effect=AssertionError("Aucun débit de l'ancien Fedow dans ce test.")
    )
    envoi_reseau_interdit = mock.MagicMock(
        side_effect=AssertionError("Aucun envoi réseau vers l'ancien Fedow.")
    )
    with mock.patch("laboutik.views.lire_depensable_fed_frais", return_value=(0, True)):
        with mock.patch("laboutik.views._debiter_legacy", new=debit_distant_interdit):
            with mock.patch("fedow_connect.fedow_api._post", new=envoi_reseau_interdit):
                with mock.patch(
                    "fedow_connect.fedow_api._get", new=envoi_reseau_interdit
                ):
                    yield
    assert debit_distant_interdit.called is False
    assert envoi_reseau_interdit.called is False


# --------------------------------------------------------------------------
# Outils : la vente à la forme de demain
# / Helpers: tomorrow's shape sale
# --------------------------------------------------------------------------


def creer_une_carte_du_client():
    """
    Une carte NFC neuve, sans portefeuille : la carte que les règlements cashless de la
    vente citent. `tag_id` et `number` font 8 caractères (tests/PIEGES.md 9.31).
    / A fresh NFC card, cited by the sale's cashless payments.
    """
    identifiant_de_la_carte = identifiant_unique().upper()
    return CarteCashless.objects.create(
        tag_id=identifiant_de_la_carte,
        number=identifiant_de_la_carte,
        uuid=uuid_module.uuid4(),
    )


def creer_une_biere_rangee_dans_les_boissons():
    """
    Le tarif vendu d'une bière à 5,00 € (TVA 20 %), rangée dans une catégorie de caisse
    neuve reliée au compte 707000. Rend le tarif vendu, le produit et la catégorie.
    / A 5.00 € beer (20 % VAT) in a new POS category linked to account 707000.
    """
    compte_des_marchandises = CompteComptable.objects.get(numero_de_compte="707000")
    categorie_des_boissons = CategorieProduct.objects.create(
        name=f"TEST jetons boissons {identifiant_unique()}",
        compte_comptable=compte_des_marchandises,
    )
    tarif_vendu = creer_tarif_vendu(
        nom="Bière jetons",
        prix_en_euros="5.00",
        taux_tva="20.00",
        methode_caisse=Product.VENTE,
    )
    produit = tarif_vendu.productsold.product
    produit.categorie_pos = categorie_des_boissons
    produit.save()
    return SimpleNamespace(
        tarif_vendu=tarif_vendu,
        produit=produit,
        categorie=categorie_des_boissons,
    )


def vendre_des_bieres_a_la_forme_de_demain(
    lieu, nombre_de_bieres, part_en_jetons, montant_en_monnaie_locale
):
    """
    ÉTAT DE DÉPART : une vente de caisse réglée, écrite par le service de vente, à la
    forme de demain. UNE ligne : `nombre_de_bieres` bières à 5,00 € (TVA 20 %), au
    moyen vide, avec sa part en jetons. Règlements : jetons (LG) de `part_en_jetons` et
    monnaie locale (LE) de `montant_en_monnaie_locale`, chacun avec sa monnaie et la
    carte du client (un montant nul n'écrit pas de règlement). Rend la vente relue, sa
    ligne, la carte, les deux monnaies et la bière.
    / STARTING STATE: tomorrow's shape, ONE line with its token part, payments LG + LE
    with their currency and the customer's card.

    :param nombre_de_bieres: quantité de la ligne (int)
    :param part_en_jetons: centimes payés en jetons (int)
    :param montant_en_monnaie_locale: centimes payés en monnaie locale (int)
    """
    biere = creer_une_biere_rangee_dans_les_boissons()
    jetons_cadeau = monnaie_cadeau_du_lieu(lieu)
    monnaie_locale = monnaie_locale_du_lieu(lieu)
    assert jetons_cadeau is not None, "Le lieu n'a pas de monnaie cadeau (TNF)."
    assert monnaie_locale is not None, "Le lieu n'a pas de monnaie locale (TLF)."
    carte_du_client = creer_une_carte_du_client()

    reglements = []
    if part_en_jetons != 0:
        reglements.append(
            {
                "moyen": PaymentMethod.LOCAL_GIFT,
                "montant": part_en_jetons,
                "asset": jetons_cadeau.uuid,
                "carte": carte_du_client,
            }
        )
    if montant_en_monnaie_locale != 0:
        reglements.append(
            {
                "moyen": PaymentMethod.LOCAL_EURO,
                "montant": montant_en_monnaie_locale,
                "asset": monnaie_locale.uuid,
                "carte": carte_du_client,
            }
        )

    vente = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": biere.tarif_vendu,
                "quantite": Decimal(nombre_de_bieres),
                "prix_unitaire": 500,
                "taux_tva": Decimal("20"),
                "part_en_jetons": part_en_jetons,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=reglements,
        carte=carte_du_client,
    )
    vente_relue = Vente.objects.get(pk=vente.pk)
    return SimpleNamespace(
        vente=vente_relue,
        ligne=vente_relue.articles.get(),
        carte=carte_du_client,
        jetons_cadeau=jetons_cadeau,
        monnaie_locale=monnaie_locale,
        biere=biere,
    )


def vendre_la_biere_mixte(lieu):
    """
    La vente de référence : une bière 500, payée 300 en jetons + 200 en monnaie locale.
    / The reference sale: one 500 beer, 300 tokens + 200 local currency.
    """
    return vendre_des_bieres_a_la_forme_de_demain(
        lieu, nombre_de_bieres=1, part_en_jetons=300, montant_en_monnaie_locale=200
    )


def reglements_en_detail(vente):
    """
    Les règlements de la vente, relus en base : une liste triée de tuples
    (moyen, montant, monnaie, clé de la carte).
    / The sale's payments, read back: sorted (method, amount, currency, card) tuples.
    """
    reglements_lus = []
    for reglement in vente.reglements.all():
        reglements_lus.append(
            (reglement.moyen, reglement.montant, reglement.asset, reglement.carte_id)
        )
    return sorted(reglements_lus, key=str)


def la_vente_d_avoir_liee_a(vente_d_origine):
    """
    LA vente AVOIR liée à cette vente : il doit y en avoir une et une seule.
    / THE AVOIR sale linked to this sale: exactly one.
    """
    ventes_d_avoir = list(
        Vente.objects.filter(nature=Vente.Nature.AVOIR, vente_liee=vente_d_origine)
    )
    assert len(ventes_d_avoir) == 1, (
        f"Attendu : une vente AVOIR liée, trouvé : {len(ventes_d_avoir)}."
    )
    return ventes_d_avoir[0]


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


def url_de_l_avoir_d_une_ligne(ligne):
    """L'adresse du bouton « Avoir » d'une ligne de vente (admin).
    / The address of a sale line's "Credit note" button."""
    return f"/admin/BaseBillet/lignearticle/{ligne.pk}/emettre_avoir/"


def url_de_l_avoir_total(vente):
    """L'adresse de l'action « Avoir total » d'une vente (admin).
    / The address of a sale's "Full credit note" action."""
    return f"/admin/BaseBillet/vente/{vente.uuid}/avoir_total/"


# --------------------------------------------------------------------------
# 1 — La formule : la TVA porte sur le reste
# / 1 — The formula: VAT is on the remainder
# --------------------------------------------------------------------------


def test_formule_part_en_jetons_tva_sur_le_reste(lieu):
    """
    500 à 20 % : la part en jetons est à TVA 0, la TVA porte sur le reste.
    - jetons 300 : HT 300 + 167 = 467, TVA 33, net 500 ;
    - jetons 500 : HT 500, TVA 0 ;
    - jetons 0 : la formule d'avant, HT 417, TVA 83.
    Tous les montants rendus sont des `int`. Le service écrit la même chose sur la
    ligne (part en jetons 300, HT 467, TVA 33).
    / 500 at 20 %: tokens 300 → HT 467 VAT 33; tokens 500 → HT 500 VAT 0; tokens 0 →
    HT 417 VAT 83. All int. The service writes the same on the line.
    """
    montants_jetons_300 = calculer_montants_article(
        prix_unitaire=500,
        quantite=Decimal("1"),
        taux_tva=Decimal("20"),
        part_en_jetons=300,
    )
    assert montants_jetons_300["total_ttc"] == 500
    assert montants_jetons_300["total_ht"] == 467
    assert montants_jetons_300["total_tva"] == 33
    assert type(montants_jetons_300["total_ht"]) is int
    assert type(montants_jetons_300["total_tva"]) is int

    montants_jetons_500 = calculer_montants_article(
        prix_unitaire=500,
        quantite=Decimal("1"),
        taux_tva=Decimal("20"),
        part_en_jetons=500,
    )
    assert montants_jetons_500["total_ttc"] == 500
    assert montants_jetons_500["total_ht"] == 500
    assert montants_jetons_500["total_tva"] == 0

    montants_jetons_0 = calculer_montants_article(
        prix_unitaire=500,
        quantite=Decimal("1"),
        taux_tva=Decimal("20"),
        part_en_jetons=0,
    )
    assert montants_jetons_0["total_ttc"] == 500
    assert montants_jetons_0["total_ht"] == 417
    assert montants_jetons_0["total_tva"] == 83

    # Le service écrit la ligne avec la même formule.
    # / The service writes the line with the same formula.
    vente_mixte = vendre_la_biere_mixte(lieu)
    ligne_relue = LigneArticle.objects.get(pk=vente_mixte.ligne.pk)
    assert ligne_relue.part_en_jetons == 300
    assert ligne_relue.part_offerte == 0
    assert ligne_relue.total_ttc == 500
    assert ligne_relue.total_ht == 467
    assert ligne_relue.total_tva == 33
    verifier_egalites(vente_mixte.vente)


# --------------------------------------------------------------------------
# 2 — Une part en jetons hors bornes est refusée (service et base)
# / 2 — An out-of-bounds token part is refused (service and database)
# --------------------------------------------------------------------------


def test_part_en_jetons_refusee_hors_bornes(lieu):
    """
    Le service refuse (ValueError) : une part en jetons plus grande que le net, une
    part négative sur une vente, une part positive sur un avoir (quantité négative),
    un `float`. La base refuse (contrainte) : une part en jetons plus grande que le
    net, et toute part en jetons sur une ligne hors chiffre d'affaires (recharge).
    / The service refuses tokens > net, negative tokens on a sale, positive tokens on
    a credit note, a float. The database refuses tokens > net and any tokens on an
    off-revenue line.
    """
    # Le service, avant tout calcul. / The service, before any computation.
    with pytest.raises(ValueError):
        calculer_montants_article(
            prix_unitaire=500,
            quantite=Decimal("1"),
            taux_tva=Decimal("20"),
            part_en_jetons=600,
        )
    with pytest.raises(ValueError):
        calculer_montants_article(
            prix_unitaire=500,
            quantite=Decimal("1"),
            taux_tva=Decimal("20"),
            part_en_jetons=-100,
        )
    with pytest.raises(ValueError):
        calculer_montants_article(
            prix_unitaire=500,
            quantite=Decimal("-1"),
            taux_tva=Decimal("20"),
            part_en_jetons=300,
        )
    with pytest.raises(ValueError):
        calculer_montants_article(
            prix_unitaire=500,
            quantite=Decimal("1"),
            taux_tva=Decimal("20"),
            part_en_jetons=300.0,
        )

    # La base : une part en jetons plus grande que le net (500).
    # / The database: tokens greater than the net (500).
    vente_mixte = vendre_la_biere_mixte(lieu)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LigneArticle.objects.filter(pk=vente_mixte.ligne.pk).update(
                part_en_jetons=600
            )

    # La base : une recharge (hors chiffre d'affaires) ne porte aucune part en jetons.
    # / The database: a top-up (off revenue) carries no token part.
    tarif_de_la_recharge = creer_tarif_vendu(
        nom="Recharge jetons",
        prix_en_euros="10.00",
        taux_tva="0.00",
        methode_caisse=Product.RECHARGE_EUROS,
    )
    vente_de_la_recharge = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": tarif_de_la_recharge,
                "quantite": Decimal("1"),
                "prix_unitaire": 1000,
                "taux_tva": Decimal("0"),
            }
        ],
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 1000}],
    )
    ligne_de_la_recharge = vente_de_la_recharge.articles.get()
    assert ligne_de_la_recharge.hors_chiffre_affaires is True
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LigneArticle.objects.filter(pk=ligne_de_la_recharge.pk).update(
                part_en_jetons=100
            )

    verifier_egalites(vente_mixte.vente)
    verifier_egalites(vente_de_la_recharge)


# --------------------------------------------------------------------------
# 3 — La part en jetons d'une vente réglée est figée
# / 3 — The token part of a settled sale is frozen
# --------------------------------------------------------------------------


def test_part_en_jetons_figee_apres_encaissement(lieu):
    """
    Une vente réglée : changer la part en jetons de sa ligne par `save()` est refusé
    par la garde d'immutabilité, qui nomme le champ.
    / A settled sale: changing its line's token part through save() is refused by the
    immutability guard, which names the field.
    """
    vente_mixte = vendre_la_biere_mixte(lieu)
    ligne_relue = LigneArticle.objects.get(pk=vente_mixte.ligne.pk)

    ligne_relue.part_en_jetons = 200
    with pytest.raises(ValueError, match="part_en_jetons"):
        ligne_relue.save()

    assert LigneArticle.objects.get(pk=vente_mixte.ligne.pk).part_en_jetons == 300
    verifier_egalites(vente_mixte.vente)


# --------------------------------------------------------------------------
# 4 — L'empreinte de la vente couvre la part en jetons
# / 4 — The sale fingerprint covers the token part
# --------------------------------------------------------------------------


def test_empreinte_de_la_vente_couvre_la_part_en_jetons(lieu):
    """
    La part en jetons est changée par `.update()` (qui contourne la garde) : la
    vérification de la chaîne signale « empreinte fausse » pour cette vente. Avant le
    changement, elle ne signalait rien de tel.
    / The token part is changed through .update(): the chain check reports a wrong
    fingerprint for this sale, which it did not before.
    """
    vente_mixte = vendre_la_biere_mixte(lieu)
    cle_de_l_empreinte = LaboutikConfiguration.get_solo().get_or_create_hmac_key()
    numero_de_la_vente = vente_mixte.vente.numero

    def raisons_des_anomalies_de_la_vente():
        raisons = []
        anomalies = verifier_chaine_ventes(
            cle_de_l_empreinte, numero_de_la_vente, numero_de_la_vente
        )
        for anomalie in anomalies:
            if anomalie["uuid"] == str(vente_mixte.vente.uuid):
                raisons.append(anomalie["raison"])
        return raisons

    for raison_avant in raisons_des_anomalies_de_la_vente():
        assert not raison_avant.startswith(DEBUT_DE_L_ANOMALIE_EMPREINTE_FAUSSE), (
            raison_avant
        )

    LigneArticle.objects.filter(pk=vente_mixte.ligne.pk).update(part_en_jetons=200)

    raisons_apres = raisons_des_anomalies_de_la_vente()
    empreinte_fausse_signalee = False
    for raison_apres in raisons_apres:
        if raison_apres.startswith(DEBUT_DE_L_ANOMALIE_EMPREINTE_FAUSSE):
            empreinte_fausse_signalee = True
    assert empreinte_fausse_signalee, raisons_apres
    verifier_egalites(vente_mixte.vente)


# --------------------------------------------------------------------------
# 5 — Caisse : la ligne porte sa part en jetons
# / 5 — Register: the line carries its token part
# --------------------------------------------------------------------------


def test_caisse_ligne_porte_sa_part_en_jetons(lieu):
    """
    Caisse, route réelle, carte NFC du client : une bière à 5,00 € (TVA 20 %) payée
    3,00 € en jetons cadeau puis 2,00 € en monnaie locale. UNE ligne (H-1b-2) : part
    en jetons 300, taux = celui du produit (20 %), HT = 300 + 167 = 467, TVA 33.
    Règlements LG 300 + LE 200. Vente : HT 467, TVA 33.
    / Register, real route: ONE line, tokens 300 at the product's rate, HT 467, VAT 33.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=200)
    ajouter_un_solde_sur_la_carte(carte_du_client, monnaie_cadeau_du_lieu(lieu), 300)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_par_la_carte_du_client(
        client_du_caissier,
        point_de_vente,
        {f"repid-{cle_de_panier(biere)}": "1"},
        carte_du_client,
        cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    lignes_de_la_vente = list(vente.articles.all())
    assert len(lignes_de_la_vente) == 1
    ligne_de_la_biere = lignes_de_la_vente[0]
    assert ligne_de_la_biere.part_en_jetons == 300
    assert ligne_de_la_biere.vat == Decimal("20.00")
    assert ligne_de_la_biere.part_offerte == 0
    assert ligne_de_la_biere.total_ttc == 500
    assert ligne_de_la_biere.total_ht == 467
    assert ligne_de_la_biere.total_tva == 33

    assert reglements_de_la_vente(vente) == [
        (PaymentMethod.LOCAL_EURO, 200),
        (PaymentMethod.LOCAL_GIFT, 300),
    ]
    assert vente.total_ht == 467
    assert vente.total_tva == 33
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 6 — Tireuse : la part LG porte sa part en jetons
# / 6 — Tap: the LG part carries its token part
# --------------------------------------------------------------------------


def test_tireuse_part_lg_porte_sa_part_en_jetons(
    lieu, ancien_fedow_sans_solde_ni_debit
):
    """
    Tireuse, routes réelles : 50 cl à 8 €/L = 400 (fût à TVA 20 %), payés 100 en
    jetons cadeau puis 300 en monnaie locale. UNE ligne (H-1c) : part en jetons 100,
    taux du fût (20 %), HT = 100 + arrondi(300 × 100 / 120) = 350, TVA 50.
    / Tap, real routes: one line, token part 100 at the keg's rate, HT 350, VAT 50.
    """
    from fedow_core.models import Asset

    jetons_cadeau = _monnaie_du_lieu(lieu.tenant, Asset.TNF)
    monnaie_locale = _monnaie_du_lieu(lieu.tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(
        lieu.tenant, prix_du_litre_en_euros="8.00"
    )
    carte, _portefeuille = _creer_une_carte(
        lieu.tenant, [(jetons_cadeau, 100), (monnaie_locale, 1000)]
    )

    reponse = _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "500.00",
    )
    assert reponse.json()["montant_centimes"] == 400

    with tenant_context(lieu.tenant):
        vente = _la_vente_du_tirage(carte)

        ligne_du_tirage = vente.articles.get()
        assert ligne_du_tirage.part_en_jetons == 100
        assert ligne_du_tirage.vat == Decimal("20.00")
        assert ligne_du_tirage.total_ttc == 400
        assert ligne_du_tirage.total_ht == 350
        assert ligne_du_tirage.total_tva == 50

        assert vente.total_ht == 350
        assert vente.total_tva == 50
        verifier_egalites(vente)


# --------------------------------------------------------------------------
# 7 — Rapport : la part en jetons au taux « 0.00 »
# / 7 — Report: the token part at the "0.00" rate
# --------------------------------------------------------------------------


def test_rapport_ca_par_taux_met_les_jetons_au_taux_zero(lieu):
    """
    La vente à la forme de demain (une ligne 500, jetons 300, à 20 %). Chiffre
    d'affaires par taux : « 0.00 » TTC 300 (HT 300, TVA 0) et « 20.00 » TTC 200 (HT
    167, TVA 33). Total du chiffre d'affaires : 500 (HT 467, TVA 33).
    La période du rapport ne contient que l'instant d'encaissement de la vente.
    / Tomorrow's sale: revenue by rate "0.00" 300 and "20.00" 200; total 500.
    """
    vente_mixte = vendre_la_biere_mixte(lieu)
    instant_de_l_encaissement = vente_mixte.vente.datetime_encaissement
    rapport = RapportDesVentes(
        debut=instant_de_l_encaissement,
        fin=instant_de_l_encaissement + timedelta(microseconds=1),
    )

    chiffre_affaires = rapport.section_chiffre_affaires()

    assert chiffre_affaires["par_taux"] == {
        "0.00": {
            "total_ttc_en_centimes": 300,
            "total_ht_en_centimes": 300,
            "total_tva_en_centimes": 0,
        },
        "20.00": {
            "total_ttc_en_centimes": 200,
            "total_ht_en_centimes": 167,
            "total_tva_en_centimes": 33,
        },
    }
    assert chiffre_affaires["total_ttc_en_centimes"] == 500
    assert chiffre_affaires["total_ht_en_centimes"] == 467
    assert chiffre_affaires["total_tva_en_centimes"] == 33
    verifier_egalites(vente_mixte.vente)


# --------------------------------------------------------------------------
# 8 — FEC : les jetons au 707900, le reste à la catégorie
# / 8 — FEC: tokens to 707900, the remainder to the category
# --------------------------------------------------------------------------


def test_fec_ecrit_les_jetons_au_707900_et_le_reste_a_la_categorie(lieu):
    """
    La vente à la forme de demain, ventilée par une clôture J dont la plage est cette
    seule vente (clôture en mémoire, jamais enregistrée) :
    - 707900 (ventes réglées en jetons) crédit 300, hors TVA ;
    - 707000 (compte de la catégorie de la bière) crédit 167 ;
    - 445711 (TVA 20 %) crédit 33 ;
    - l'écriture est équilibrée : débits 500 = crédits 500.
    / Tomorrow's sale ventilated by an in-memory J whose range is this sale only:
    707900 C 300, category 707000 C 167, VAT 445711 C 33, balanced.
    """
    vente_mixte = vendre_la_biere_mixte(lieu)
    numero_de_la_vente = vente_mixte.vente.numero
    cloture_de_cette_seule_vente = ClotureCaisse(
        niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        numero_sequentiel=0,
        numero_premiere_vente=numero_de_la_vente,
        numero_derniere_vente=numero_de_la_vente,
    )

    # Aucun code journal refusé : la base partagée peut porter des collisions de codes
    # qui ne concernent pas cette vente.
    # / No refused journal code: the shared database may hold unrelated collisions.
    ecritures = ventiler_cloture(cloture_de_cette_seule_vente, codes_journal_refuses={})

    assert len(ecritures) == 1
    comptes = comptes_de_l_ecriture(ecritures[0])
    assert comptes["707900"] == (0, 300)
    assert comptes["707000"] == (0, 167)
    assert comptes["445711"] == (0, 33)

    total_des_debits = 0
    total_des_credits = 0
    for debit, credit in comptes.values():
        total_des_debits += debit
        total_des_credits += credit
    assert total_des_debits == 500
    assert total_des_credits == 500
    verifier_egalites(vente_mixte.vente)


# --------------------------------------------------------------------------
# 9 — Ticket client : TVA par taux avec les jetons
# / 9 — Customer receipt: VAT by rate with tokens
# --------------------------------------------------------------------------


def test_ticket_tva_par_taux_avec_les_jetons(lieu):
    """
    Le ticket de la vente à la forme de demain : une ligne de TVA à 0 % (HT 300, TVA 0,
    TTC 300) et une à 20 % (HT 167, TVA 33, TTC 200). Totaux HT 467, TVA 33.
    / The receipt: a 0 % VAT row (300 / 0 / 300) and a 20 % row (167 / 33 / 200).
    """
    vente_mixte = vendre_la_biere_mixte(lieu)

    ticket = formatter_ticket_vente(vente_mixte.vente, None)

    lignes_de_tva = sorted(ticket["tva_breakdown"], key=lambda ligne: ligne["rate"])
    assert lignes_de_tva == [
        {"rate": "0.00", "ht": 300, "tva": 0, "ttc": 300},
        {"rate": "20.00", "ht": 167, "tva": 33, "ttc": 200},
    ]
    assert ticket["total_ht"] == 467
    assert ticket["total_tva"] == 33
    verifier_egalites(vente_mixte.vente)


# --------------------------------------------------------------------------
# 10 — Archive fiscale : la colonne de la part en jetons
# / 10 — Fiscal archive: the token part column
# --------------------------------------------------------------------------


def test_archive_porte_la_part_en_jetons(lieu):
    """
    L'archive fiscale (`articles.csv`, vraie génération) porte la colonne
    `part_en_jetons`, et la valeur 300 pour la ligne de la vente à la forme de demain.
    / The fiscal archive's articles.csv carries the part_en_jetons column, value 300.
    """
    vente_mixte = vendre_la_biere_mixte(lieu)

    article_exporte = article_dans_l_archive_lne(vente_mixte.ligne)

    assert "part_en_jetons" in article_exporte, sorted(article_exporte.keys())
    assert article_exporte["part_en_jetons"] == "300"
    verifier_egalites(vente_mixte.vente)


# --------------------------------------------------------------------------
# 11 — Avoir total d'une ligne mixte : jetons et argent
# / 11 — Full credit note of a mixed line: tokens and money
# --------------------------------------------------------------------------


def test_avoir_total_ligne_mixte_rend_lg_et_argent(lieu):
    """
    « Avoir total » de la vente à la forme de demain. L'écran demande « Remboursé
    par » (200 d'argent à rendre) et annonce des jetons rendus. L'admin choisit
    « Espèces » :
    - règlements de l'avoir : jetons (LG) −300, avec la monnaie et la carte du
      règlement LG de la vente d'origine ; espèces (CA) −200 ;
    - article d'avoir : le miroir de la ligne, part en jetons −300, net −500, HT −467,
      TVA −33.
    / Full credit note, refunded in cash: LG −300 (currency and card of the original LG
    payment) and cash −200; mirrored item with tokens −300.
    """
    vente_mixte = vendre_la_biere_mixte(lieu)
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_ecran = client_de_l_admin.get(url_de_l_avoir_total(vente_mixte.vente))
    assert reponse_de_l_ecran.status_code == 200
    assert "moyen_rembourse" in reponse_de_l_ecran.context["form"].fields
    assert reponse_de_l_ecran.context["il_y_a_des_jetons_rendus"] is True

    reponse = client_de_l_admin.post(
        url_de_l_avoir_total(vente_mixte.vente),
        {"moyen_rembourse": PaymentMethod.CASH},
    )

    assert reponse.status_code == 302
    vente_d_avoir = la_vente_d_avoir_liee_a(vente_mixte.vente)
    assert vente_d_avoir.statut == Vente.Statut.REGLEE
    assert reglements_en_detail(vente_d_avoir) == sorted(
        [
            (PaymentMethod.CASH, -200, None, None),
            (
                PaymentMethod.LOCAL_GIFT,
                -300,
                vente_mixte.jetons_cadeau.uuid,
                vente_mixte.carte.pk,
            ),
        ],
        key=str,
    )

    article_d_avoir = vente_d_avoir.articles.get()
    assert article_d_avoir.part_en_jetons == -300
    assert article_d_avoir.total_ttc == -500
    assert article_d_avoir.total_ht == -467
    assert article_d_avoir.total_tva == -33
    verifier_egalites(vente_d_avoir)


# --------------------------------------------------------------------------
# 12 — Avoir partiel : refusé sur une ligne mixte, permis entièrement en jetons
# / 12 — Partial credit note: refused on a mixed line, allowed fully in tokens
# --------------------------------------------------------------------------


def test_avoir_partiel_ligne_mixte_refuse(lieu):
    """
    - une bière sur deux d'une ligne mixte (1000, jetons 600, monnaie locale 400) :
      refus « rembourser l'article entier », rien n'est écrit ;
    - une bière sur deux d'une ligne ENTIÈREMENT en jetons (1000, jetons 1000) : avoir
      accepté, lui aussi entièrement en jetons (net −500, part en jetons −500), réglé
      par un seul règlement jetons −500 (monnaie et carte du règlement LG d'origine).
    / One beer of two: refused on a mixed line; accepted on a fully token-paid line,
    fully in tokens too (LG −500).
    """
    vente_mixte = vendre_des_bieres_a_la_forme_de_demain(
        lieu, nombre_de_bieres=2, part_en_jetons=600, montant_en_monnaie_locale=400
    )
    with pytest.raises(ValueError, match=REFUS_DE_L_AVOIR_PARTIEL):
        ecrire_la_vente_d_avoir_d_une_ligne(
            vente_mixte.ligne,
            quantite=Decimal("1"),
            moyen_rembourse=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
        )
    assert not Vente.objects.filter(
        nature=Vente.Nature.AVOIR, vente_liee=vente_mixte.vente
    ).exists()

    vente_en_jetons = vendre_des_bieres_a_la_forme_de_demain(
        lieu, nombre_de_bieres=2, part_en_jetons=1000, montant_en_monnaie_locale=0
    )
    article_d_avoir = ecrire_la_vente_d_avoir_d_une_ligne(
        vente_en_jetons.ligne,
        quantite=Decimal("1"),
        moyen_rembourse=None,
        origine=SaleOrigin.ADMIN,
    )

    article_relu = LigneArticle.objects.get(pk=article_d_avoir.pk)
    assert article_relu.qty == Decimal("-1")
    assert article_relu.total_ttc == -500
    assert article_relu.part_en_jetons == -500
    assert article_relu.total_tva == 0
    vente_d_avoir = Vente.objects.get(pk=article_relu.vente_id)
    assert reglements_en_detail(vente_d_avoir) == [
        (
            PaymentMethod.LOCAL_GIFT,
            -500,
            vente_en_jetons.jetons_cadeau.uuid,
            vente_en_jetons.carte.pk,
        )
    ]
    verifier_egalites(vente_mixte.vente)
    verifier_egalites(vente_d_avoir)


# --------------------------------------------------------------------------
# 13 — Une ligne mixte a de l'argent à rendre
# / 13 — A mixed line has money to give back
# --------------------------------------------------------------------------


def test_ligne_mixte_a_de_l_argent_a_rendre(lieu):
    """
    `ligne_sans_argent_a_rendre` lit la part en jetons, pas le moyen de la ligne :
    - ligne mixte (500, jetons 300, moyen vide) : faux, 200 sont à rendre ; l'écran
      « Émettre un avoir » affiche le champ « Remboursé par » ;
    - ligne entièrement en jetons (500, jetons 500, moyen vide) : vrai ; l'écran n'a
      pas de champ « Remboursé par » ;
    - ligne sans vente (historique) au moyen LG : vrai, lue par son moyen.
    / ligne_sans_argent_a_rendre reads the token part: false for the mixed line (field
    shown), true for a fully token-paid line (no field), true for a historical LG line.
    """
    vente_mixte = vendre_la_biere_mixte(lieu)
    vente_en_jetons = vendre_des_bieres_a_la_forme_de_demain(
        lieu, nombre_de_bieres=1, part_en_jetons=500, montant_en_monnaie_locale=0
    )

    assert ligne_sans_argent_a_rendre(vente_mixte.ligne) is False
    assert ligne_sans_argent_a_rendre(vente_en_jetons.ligne) is True

    # Une ligne d'avant le chantier, sans vente : son moyen LG reste le seul indice.
    # Objet en mémoire, jamais enregistré. / A historical line, in memory only.
    ligne_historique_payee_en_jetons = LigneArticle(
        payment_method=PaymentMethod.LOCAL_GIFT,
        vente=None,
    )
    assert ligne_sans_argent_a_rendre(ligne_historique_payee_en_jetons) is True

    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    ecran_de_la_ligne_mixte = client_de_l_admin.get(
        url_de_l_avoir_d_une_ligne(vente_mixte.ligne)
    )
    assert ecran_de_la_ligne_mixte.status_code == 200
    assert "moyen_rembourse" in ecran_de_la_ligne_mixte.context["form"].fields

    ecran_de_la_ligne_en_jetons = client_de_l_admin.get(
        url_de_l_avoir_d_une_ligne(vente_en_jetons.ligne)
    )
    assert ecran_de_la_ligne_en_jetons.status_code == 200
    assert "moyen_rembourse" not in ecran_de_la_ligne_en_jetons.context["form"].fields

    verifier_egalites(vente_mixte.vente)
    verifier_egalites(vente_en_jetons.vente)


# --------------------------------------------------------------------------
# 14 — « Plan complet ? » ne lit pas le moyen de la ligne pour les jetons
# / 14 — "Complete plan?" does not read the line's method for tokens
# --------------------------------------------------------------------------


def test_plan_complet_sans_moyen_de_ligne_pour_les_jetons(lieu):
    """
    - une ligne mixte au moyen vide, d'une bière rangée dans une catégorie reliée au
      707000 : « Plan complet ? » ne la signale pas « sans compte » ;
    - une ligne ENTIÈREMENT en jetons, au moyen vide, d'un produit « vente » SANS
      catégorie (il n'a donc aucun compte) : pas signalée non plus, car tout va au
      707900 et rien au compte du produit.
    Le plan du lieu a le 707900 : aucun manque ne nomme ces produits.
    / A mixed line (product with an account) and a fully token-paid line (product
    without account), both with an empty method: none is reported "without account".
    """
    vente_mixte = vendre_la_biere_mixte(lieu)
    tarif_sans_categorie = creer_tarif_vendu(
        nom="Planche sans catégorie",
        prix_en_euros="5.00",
        taux_tva="20.00",
        methode_caisse=Product.VENTE,
    )
    vente_entierement_en_jetons = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": tarif_sans_categorie,
                "quantite": Decimal("1"),
                "prix_unitaire": 500,
                "taux_tva": Decimal("20"),
                "part_en_jetons": 500,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[{"moyen": PaymentMethod.LOCAL_GIFT, "montant": 500}],
    )
    noms_des_produits = [
        vente_mixte.biere.produit.name,
        tarif_sans_categorie.productsold.product.name,
    ]
    assert CompteComptable.objects.filter(numero_de_compte="707900").exists()

    manques = ce_qui_manque_pour_exporter()

    phrases_qui_nomment_un_produit = []
    for manque in manques:
        for nom_du_produit in noms_des_produits:
            if nom_du_produit in manque["phrase"]:
                phrases_qui_nomment_un_produit.append(manque["phrase"])
    assert phrases_qui_nomment_un_produit == []
    verifier_egalites(vente_mixte.vente)
    verifier_egalites(vente_entierement_en_jetons)


# --------------------------------------------------------------------------
# 15 — L'ancien rapport de la caisse n'est plus joignable
# / 15 — The old register report is no longer reachable
# --------------------------------------------------------------------------

# Les adresses de l'ancien moteur de rapport de la caisse (laboutik/reports.py). Écrites
# en clair : la route et l'admin retirés, `reverse()` ne les trouverait plus.
# / The old register report engine addresses, written out (reverse() would fail).
ADRESSE_DU_RAPPORT_TEMPS_REEL_DE_LA_CAISSE = "/laboutik/caisse/rapport-temps-reel/"
ADRESSE_DE_L_ANCIENNE_CLOTURE_DE_LA_CAISSE = "/admin/laboutik/cloturecaisse/"


def test_ancien_rapport_caisse_n_est_plus_joignable(lieu):
    """
    L'ancien moteur recalcule la TVA depuis le taux de la ligne : faux sur une part en
    jetons. Ses écrans sont coupés :
    - la page « rapport temps réel » de la caisse répond 404 ;
    - la liste de l'ancienne clôture de la caisse (admin) répond 404 ;
    - aucune entrée du menu de l'admin ne mène à l'une ou l'autre.
    / The old engine recomputes VAT from the rate: its screens answer 404 and no menu
    entry leads to them.
    """
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_du_rapport = client_de_l_admin.get(
        ADRESSE_DU_RAPPORT_TEMPS_REEL_DE_LA_CAISSE
    )
    assert reponse_du_rapport.status_code == 404

    reponse_de_la_liste = client_de_l_admin.get(
        ADRESSE_DE_L_ANCIENNE_CLOTURE_DE_LA_CAISSE
    )
    assert reponse_de_la_liste.status_code == 404

    sections_du_menu = dashboard._construire_sections_modules(
        RequestFactory().get("/admin/")
    )
    entrees_vers_l_ancien_moteur = []
    for section in sections_du_menu:
        for entree in section.get("items", []):
            lien_de_l_entree = str(entree.get("link"))
            mene_a_l_ancien_moteur = lien_de_l_entree in [
                ADRESSE_DU_RAPPORT_TEMPS_REEL_DE_LA_CAISSE,
                ADRESSE_DE_L_ANCIENNE_CLOTURE_DE_LA_CAISSE,
            ]
            if mene_a_l_ancien_moteur:
                entrees_vers_l_ancien_moteur.append(lien_de_l_entree)
    assert entrees_vers_l_ancien_moteur == []


# --------------------------------------------------------------------------
# 16 — Jetons payés par deux cartes : un règlement LG, sans carte
# / 16 — Tokens paid by two cards: one LG payment, without card
# --------------------------------------------------------------------------


def vendre_une_biere_en_jetons_par_deux_reglements(lieu, monnaie_du_second_reglement):
    """
    ÉTAT DE DÉPART : une bière à 5,00 € (TVA 20 %) ENTIÈREMENT payée en jetons (part
    en jetons 500), par deux règlements « jetons » : 300 par la carte A, dans la
    monnaie cadeau du lieu, puis 200 par la carte B, dans `monnaie_du_second_reglement`.
    Rend la vente relue, la monnaie cadeau du lieu et les deux cartes.
    / STARTING STATE: a beer fully paid in tokens by two LG payments (card A 300 in the
    venue's gift currency, card B 200 in the given currency).

    :param monnaie_du_second_reglement: uuid de la monnaie du règlement de la carte B
        (None : la monnaie cadeau du lieu, la même que celle de la carte A)
    """
    biere = creer_une_biere_rangee_dans_les_boissons()
    jetons_cadeau = monnaie_cadeau_du_lieu(lieu)
    assert jetons_cadeau is not None, "Le lieu n'a pas de monnaie cadeau (TNF)."
    if monnaie_du_second_reglement is None:
        monnaie_du_second_reglement = jetons_cadeau.uuid
    carte_a = creer_une_carte_du_client()
    carte_b = creer_une_carte_du_client()

    vente = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": biere.tarif_vendu,
                "quantite": Decimal("1"),
                "prix_unitaire": 500,
                "taux_tva": Decimal("20"),
                "part_en_jetons": 500,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[
            {
                "moyen": PaymentMethod.LOCAL_GIFT,
                "montant": 300,
                "asset": jetons_cadeau.uuid,
                "carte": carte_a,
            },
            {
                "moyen": PaymentMethod.LOCAL_GIFT,
                "montant": 200,
                "asset": monnaie_du_second_reglement,
                "carte": carte_b,
            },
        ],
        carte=carte_a,
    )
    return SimpleNamespace(
        vente=Vente.objects.get(pk=vente.pk),
        jetons_cadeau=jetons_cadeau,
        carte_a=carte_a,
        carte_b=carte_b,
    )


def test_avoir_jetons_payes_par_deux_cartes_un_reglement_sans_carte(lieu):
    """
    - Même monnaie, deux cartes : « Avoir total » s'ouvre sans « Remboursé par » (aucun
      argent) et annonce des jetons rendus. Le POST écrit UN règlement « jetons »
      −500, dans la monnaie de la vente, SANS carte (le compte 419100 ne dépend que de
      la monnaie).
    - Deux monnaies de jetons : refus dès l'écran (l'aperçu annonce ce que le POST
      ferait), et le POST est refusé aussi ; aucune vente AVOIR n'est écrite.
    / Same currency, two cards: one LG payment of −500, in the sale's currency, without
    card. Two token currencies: refused from the screen on, and by the POST.
    """
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    # Même monnaie, deux cartes. / Same currency, two cards.
    vente_deux_cartes = vendre_une_biere_en_jetons_par_deux_reglements(
        lieu, monnaie_du_second_reglement=None
    )
    reponse_de_l_ecran = client_de_l_admin.get(
        url_de_l_avoir_total(vente_deux_cartes.vente)
    )
    assert reponse_de_l_ecran.status_code == 200
    assert "moyen_rembourse" not in reponse_de_l_ecran.context["form"].fields
    assert reponse_de_l_ecran.context["il_y_a_des_jetons_rendus"] is True

    reponse = client_de_l_admin.post(url_de_l_avoir_total(vente_deux_cartes.vente), {})

    assert reponse.status_code == 302
    vente_d_avoir = la_vente_d_avoir_liee_a(vente_deux_cartes.vente)
    assert reglements_en_detail(vente_d_avoir) == [
        (PaymentMethod.LOCAL_GIFT, -500, vente_deux_cartes.jetons_cadeau.uuid, None)
    ]
    verifier_egalites(vente_deux_cartes.vente)
    verifier_egalites(vente_d_avoir)

    # Deux monnaies de jetons. / Two token currencies.
    vente_deux_monnaies = vendre_une_biere_en_jetons_par_deux_reglements(
        lieu, monnaie_du_second_reglement=uuid_module.uuid4()
    )
    reponse_de_l_ecran_refuse = client_de_l_admin.get(
        url_de_l_avoir_total(vente_deux_monnaies.vente)
    )
    assert reponse_de_l_ecran_refuse.status_code == 302
    reponse_du_post_refuse = client_de_l_admin.post(
        url_de_l_avoir_total(vente_deux_monnaies.vente), {}
    )
    assert reponse_du_post_refuse.status_code == 302
    assert not Vente.objects.filter(
        nature=Vente.Nature.AVOIR, vente_liee=vente_deux_monnaies.vente
    ).exists()
    verifier_egalites(vente_deux_monnaies.vente)


# --------------------------------------------------------------------------
# 17 — Une vente en points n'a pas de part en jetons
# / 17 — A points sale has no token part
# --------------------------------------------------------------------------


def test_part_en_jetons_refusee_sur_une_vente_en_points(lieu):
    """
    Une vente tenue en points (`unite` = l'uuid de la monnaie de points, TVA 0) :
    ajouter un article avec une part en jetons est refusé (ValueError), et aucun
    article n'est écrit.
    / A points sale: adding an item with a token part is refused, nothing written.
    """
    tarif_en_points = creer_tarif_vendu(
        nom="Café en points", prix_en_euros="5.00", taux_tva="0.00"
    )
    vente_en_points = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.VENTE,
        unite=str(uuid_module.uuid4()),
    )

    with pytest.raises(ValueError, match="jetons"):
        ajouter_article(
            vente_en_points,
            pricesold=tarif_en_points,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("0"),
            part_en_jetons=100,
        )

    assert not LigneArticle.objects.filter(vente=vente_en_points).exists()


# --------------------------------------------------------------------------
# 18 — « Plan complet ? » signale le 707900 absent
# / 18 — "Complete plan?" reports the missing 707900
# --------------------------------------------------------------------------


def test_plan_complet_signale_le_707900_absent(lieu):
    """
    Une part en jetons est vendue, puis le compte 707900 (ventes réglées en jetons) est
    supprimé du plan : « Plan complet ? » signale le manque, en nommant le numéro
    (section 1 bis). Le compte revient au rollback de la fin du test.
    / A token part is sold, then 707900 is deleted: "Complete plan?" names it.
    """
    vente_mixte = vendre_la_biere_mixte(lieu)
    CompteComptable.objects.filter(numero_de_compte="707900").delete()

    manques = ce_qui_manque_pour_exporter()

    phrases_qui_nomment_le_707900 = []
    for manque in manques:
        if "707900" in manque["phrase"]:
            phrases_qui_nomment_le_707900.append(manque["phrase"])
    assert len(phrases_qui_nomment_le_707900) == 1, phrases_qui_nomment_le_707900
    verifier_egalites(vente_mixte.vente)


# --------------------------------------------------------------------------
# 19 — La base refuse une part en jetons de signe opposé au net
# / 19 — The database refuses a token part of the opposite sign
# --------------------------------------------------------------------------


def test_contrainte_signe_de_la_part_en_jetons(lieu):
    """
    Un avoir (net −500) : la base refuse une part en jetons positive (+100), même
    écrite par `.update()` qui contourne le service.
    / A credit note (net −500): the database refuses a positive token part.
    """
    tarif_de_la_biere = creer_tarif_vendu(
        nom="Bière avoir", prix_en_euros="5.00", taux_tva="20.00"
    )
    vente_d_avoir = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.AVOIR,
        articles=[
            {
                "pricesold": tarif_de_la_biere,
                "quantite": Decimal("-1"),
                "prix_unitaire": 500,
                "taux_tva": Decimal("20"),
            }
        ],
        reglements=[{"moyen": PaymentMethod.CASH, "montant": -500}],
    )
    ligne_de_l_avoir = vente_d_avoir.articles.get()
    assert ligne_de_l_avoir.total_ttc == -500

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LigneArticle.objects.filter(pk=ligne_de_l_avoir.pk).update(
                part_en_jetons=100
            )
    verifier_egalites(vente_d_avoir)


# --------------------------------------------------------------------------
# 20 — Le service refuse une part en jetons sur un article hors chiffre d'affaires
# / 20 — The service refuses a token part on an off-revenue item
# --------------------------------------------------------------------------


def test_part_en_jetons_refusee_hors_chiffre_affaires(lieu):
    """
    Une recharge en euros est hors chiffre d'affaires : `ajouter_article` refuse une
    part en jetons (ValueError, avant la base), et aucun article n'est écrit.
    / A top-up is off revenue: ajouter_article refuses a token part before the database.
    """
    tarif_de_la_recharge = creer_tarif_vendu(
        nom="Recharge jetons refusée",
        prix_en_euros="10.00",
        taux_tva="0.00",
        methode_caisse=Product.RECHARGE_EUROS,
    )
    vente = ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE)

    with pytest.raises(ValueError, match="hors chiffre d'affaires"):
        ajouter_article(
            vente,
            pricesold=tarif_de_la_recharge,
            quantite=Decimal("1"),
            prix_unitaire=1000,
            taux_tva=Decimal("0"),
            part_en_jetons=100,
        )

    assert not LigneArticle.objects.filter(vente=vente).exists()


# --------------------------------------------------------------------------
# 21 — Un taux à 0 par une vente et son avoir reste dans le CA par taux
# / 21 — A rate at 0 through a sale and its credit note stays in revenue by rate
# --------------------------------------------------------------------------


def test_taux_garde_si_ventes_et_avoirs_s_annulent(lieu):
    """
    Au taux 20 % : une bière entièrement en jetons (500), un jus à 3,50 € en espèces,
    puis l'avoir de ce jus. Le reste du taux 20 % vaut 0 (le jus et son avoir
    s'annulent), mais toutes ses lignes ne sont pas entièrement en jetons : le taux
    « 20.00 » reste affiché, à 0, comme sans jetons. Les jetons vont au taux « 0.00 ».
    La période couvre ces trois ventes, de la première à la dernière encaissée.
    / At 20 %: a fully token-paid beer, a juice and its credit note. The 20 % rate
    keeps showing at 0; the tokens go to "0.00".
    """
    vente_en_jetons = vendre_des_bieres_a_la_forme_de_demain(
        lieu, nombre_de_bieres=1, part_en_jetons=500, montant_en_monnaie_locale=0
    )
    tarif_du_jus = creer_tarif_vendu(
        nom="Jus avoir", prix_en_euros="3.50", taux_tva="20.00"
    )
    vente_du_jus = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": tarif_du_jus,
                "quantite": Decimal("1"),
                "prix_unitaire": 350,
                "taux_tva": Decimal("20"),
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
    )
    article_d_avoir = ecrire_la_vente_d_avoir_d_une_ligne(
        vente_du_jus.articles.get(),
        quantite=Decimal("1"),
        moyen_rembourse=PaymentMethod.CASH,
        origine=SaleOrigin.ADMIN,
    )
    vente_d_avoir = Vente.objects.get(pk=article_d_avoir.vente_id)

    rapport = RapportDesVentes(
        debut=vente_en_jetons.vente.datetime_encaissement,
        fin=vente_d_avoir.datetime_encaissement + timedelta(microseconds=1),
    )
    chiffre_affaires = rapport.section_chiffre_affaires()

    assert chiffre_affaires["par_taux"] == {
        "0.00": {
            "total_ttc_en_centimes": 500,
            "total_ht_en_centimes": 500,
            "total_tva_en_centimes": 0,
        },
        "20.00": {
            "total_ttc_en_centimes": 0,
            "total_ht_en_centimes": 0,
            "total_tva_en_centimes": 0,
        },
    }
    verifier_egalites(vente_en_jetons.vente)
    verifier_egalites(Vente.objects.get(pk=vente_du_jus.pk))
    verifier_egalites(vente_d_avoir)


# --------------------------------------------------------------------------
# 22 — « Plan complet ? » : pas de compte de TVA pour un taux sans TVA
# / 22 — "Complete plan?": no VAT account for a rate without VAT
# --------------------------------------------------------------------------

# Un taux que le plan par défaut n'a pas (ni 20, ni 10, ni 5,5, ni 2,1 %), et qu'aucune
# autre vente de la base partagée n'utilise : seul ce test peut le faire apparaître
# dans « Plan complet ? ».
# / A rate absent from the default plan and unused elsewhere in the shared database.
TAUX_SANS_COMPTE_DE_TVA = "8.50"
TAUX_SANS_COMPTE_DE_TVA_ECRIT_A_LA_FRANCAISE = "8,5"


def test_plan_complet_sans_compte_de_tva_pour_une_ligne_sans_tva(lieu):
    """
    Une ligne ENTIÈREMENT en jetons au taux de son produit (8,5 %, un taux sans compte
    de TVA dans le plan) : sa TVA vaut 0, le FEC n'écrit aucune TVA. « Plan complet ? »
    ne signale donc pas de compte de TVA manquant à ce taux.
    Le brief cite 20 % : sur la base partagée, d'autres ventes à 20 % et son compte
    existant rendraient ce test aveugle ; un taux propre au test garde la même règle.
    / A fully token-paid line at a rate without VAT account: no missing VAT account.
    """
    tarif_au_taux_sans_compte = creer_tarif_vendu(
        nom="Bière taux sans compte",
        prix_en_euros="5.00",
        taux_tva=TAUX_SANS_COMPTE_DE_TVA,
        methode_caisse=Product.VENTE,
    )
    vente_entierement_en_jetons = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": tarif_au_taux_sans_compte,
                "quantite": Decimal("1"),
                "prix_unitaire": 500,
                "taux_tva": Decimal(TAUX_SANS_COMPTE_DE_TVA),
                "part_en_jetons": 500,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[{"moyen": PaymentMethod.LOCAL_GIFT, "montant": 500}],
    )
    ligne_en_jetons = vente_entierement_en_jetons.articles.get()
    assert ligne_en_jetons.total_tva == 0

    manques = ce_qui_manque_pour_exporter()

    debut_de_la_phrase_du_taux = (
        f"Des ventes ont une TVA à {TAUX_SANS_COMPTE_DE_TVA_ECRIT_A_LA_FRANCAISE} %"
    )
    phrases_du_taux = []
    for manque in manques:
        if manque["phrase"].startswith(debut_de_la_phrase_du_taux):
            phrases_du_taux.append(manque["phrase"])
    assert phrases_du_taux == []
    verifier_egalites(vente_entierement_en_jetons)
