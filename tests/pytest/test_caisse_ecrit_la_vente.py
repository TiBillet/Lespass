"""
Tests de la caisse : chaque encaissement écrit aussi sa `Vente`, ses règlements, et les
montants entiers de ses articles. Paiement à UN moyen (espèces, CB, chèque, OFFRIR,
recharges, consigne), paiement par la carte NFC du client (cascade des monnaies,
jetons, points, monnaie du réseau), et carte qui ne suffit pas, le reste étant réglé
en espèces, en CB ou par une deuxième carte.
/ Register tests: each collection also writes its `Vente`, its payments, and the
whole-cent amounts of its items. One-method payments, NFC card payments, and card
payments completed in cash, by bank card or by a second card.

LOCALISATION : tests/pytest/test_caisse_ecrit_la_vente.py

RÈGLE MÉTIER TESTÉE
Un clic sur un moyen de paiement qui réussit produit UNE vente encaissée (`REGLEE`,
numérotée), dans la même transaction que les lignes de vente. Les lignes restent écrites
comme aujourd'hui (même `amount`, même `qty`, mêmes champs historiques), et reçoivent en
plus leur vente et leurs montants entiers. Les règlements sont copiés de l'argent
réellement encaissé, jamais recalculés depuis les lignes.
Cas particuliers :
- OFFRIR (mode gérant) et recharge cadeau : article entièrement offert, règlement FREE ;
- recharge en euros : article hors chiffre d'affaires, TVA 0, dans la même vente que le
  reste du panier ;
- retour de consigne : vente `AVOIR`, règlement négatif, au prix et au taux de TVA du
  produit consigne relié (`Product.consigne_remboursee`) ; sans consigne reliée, refus.
  Son coût d'achat est celui du gobelet, en négatif. Quand la caisse ne sait pas
  calculer son prix (pas de consigne reliée, ou gobelet sans tarif en euros), le
  retour n'a pas de tuile.
/ One successful click on a payment method writes ONE settled sale, in the same
transaction as the sale lines. Payments are copied from the money really collected.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-B-caisse.md (§1, §2, §3, §6)
et CHANTIER-05-montants-entiers.md (§2, §4 D8, D10, D11, §5).
Brief : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-briefs/05-B-1.md.

COMMENT CHAQUE TEST RETROUVE SA VENTE
La base est partagée avec le serveur de dev : un test ne lit que SA vente. Il la retrouve
par la clé d'idempotence qu'il a lui-même envoyée (`Vente.idempotency_key` reprend la clé
du paiement), ou, pour la recharge cadeau (sans clé), par la ligne de son propre tarif.
Chaque test finit par `verifier_egalites(vente)` (tests/pytest/fabriques_vente.py) et
compare des entiers exacts.
Pendant la transition, un article payé avec plusieurs moyens est coupé en parts, une
par monnaie : aucun test de ce fichier n'asserte le HT d'une part (tronc §5), seulement
les totaux de la vente.
/ Each test finds ITS sale through the idempotency key it sent, and ends with
verifier_egalites(vente). No test asserts the HT of a part, only the sale totals.

PAIEMENT PAR CARTE NFC : LES RÈGLEMENTS VIENNENT DES DÉBITS
Les règlements sont copiés des débits réellement faits, jamais des lignes : un règlement
par transaction `fedow_core` créée (son montant, son uuid dans `fedow_transaction_uuid`),
un règlement par transaction du réseau (monnaie fédérée, serveur Fedow distant : son uuid
dans `reference_externe`). Un jeton cadeau dépensé solde la dette du lieu (D8 bis) : la
part payée en jetons est une vente ordinaire, hors TVA, réglée « jetons » (LG).
/ Payments are copied from the real debits, never from the lines.

CODE PARCOURU / CODE EXERCISED
- laboutik/views.py — PaiementViewSet.payer, _executer_avec_cle_idempotence,
  _payer_en_especes, _payer_par_carte_ou_cheque (CB et OFFRIR),
  _rembourser_consigne_par_nfc, _creer_lignes_articles (et sa boucle HMAC),
  _executer_recharges, PaiementViewSet.identifier_client (recharge cadeau seule) ;
- laboutik/views.py — _payer_par_nfc, _creer_lignes_articles_cascade (et sa boucle
  HMAC), _debiter_legacy, _repartir_legacy_sur_articles ;
- laboutik/views.py — PaiementViewSet.payer_complementaire,
  _executer_paiement_complementaire (la carte ne suffit pas : le reste en espèces, en
  CB ou par une deuxième carte, la monnaie du réseau pouvant en payer une partie) ;
- laboutik/views.py — CommandeViewSet.payer_commande (commande de table payée en
  espèces, en CB, en chèque ou par la carte NFC du client) ;
- laboutik/views.py — PaiementViewSet.corriger_moyen_paiement (correction du moyen
  de paiement d'une vente déjà encaissée : une vente `CORRECTION` liée, la vente
  d'origine ne change pas) ;
- BaseBillet/services_vente.py — le service de vente (fiche A).

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin (tests/PIEGES.md
13.1), rien ne reste en base de dev. La caisse est activée par `configuration_modifiee()`,
jamais enregistrée (tests/PIEGES.md 13.22). Celery est simulé (tests/PIEGES.md 13.4).
Les recharges, le retour de consigne par carte et la cascade des monnaies du lieu
écrivent dans `fedow_core`, en base locale : aucun appel réseau. La monnaie du réseau
(serveur Fedow distant) est simulée : son solde (`lire_depensable_fed_frais`) et son
débit (`FedowAPI`), jamais appelés pour de vrai.
/ Rolled-back transaction per test. Register module on in memory only. Celery faked.
The remote Fedow network is faked.

Lancer / Run : make test ARGS="tests/pytest/test_caisse_ecrit_la_vente.py"
"""

import csv
import html
import logging
import re
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.db import connection
from django.db.models import Q
from django.utils import timezone, translation
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from BaseBillet.models import (
    LigneArticle,
    PaymentMethod,
    Price,
    PriceSold,
    Product,
    ProductSold,
    SaleOrigin,
    Tva,
)
from BaseBillet.models_vente import Vente
from BaseBillet.services_vente import EgaliteDeVenteRompue
from fabriques_panier import (
    client_connecte,
    configuration_modifiee,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_vente import verifier_egalites
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import AssetService, WalletService
from laboutik.archivage import generer_fichiers_archive
from laboutik.integrity import verifier_chaine_ventes
from laboutik.models import (
    ArticleCommandeSauvegarde,
    CartePrimaire,
    CommandeSauvegarde,
    CorrectionPaiement,
    LaboutikConfiguration,
    Table,
)
from QrcodeCashless.models import CarteCashless
from test_caracterisation_caisse import (
    creer_un_point_de_vente,
    creer_une_carte_nfc_chargee,
    payer_a_la_caisse,
    statuts_des_articles_de_la_commande,
)
from test_caracterisation_en_ligne import creer_un_administrateur_du_lieu

pytestmark = pytest.mark.django_db

# Adresses de la caisse (laboutik/urls.py).
# / Cash register addresses.
URL_DU_PAIEMENT_CAISSE = "/laboutik/paiement/payer/"
URL_DE_L_IDENTIFICATION_DU_CLIENT = "/laboutik/paiement/identifier_client/"

# Début du nom de tout ce que ces tests créent.
# / Prefix of everything these tests create.
PREFIXE_DES_TESTS = "TEST_caisse_vente"


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, caisse activée, avec Celery simulé pendant tout le test.
    / The `lespass` venue, register switched on, with Celery faked for the whole test.

    La caisse n'est accessible que si le module caisse (et donc le module monnaie
    locale) est actif. On l'active EN MÉMOIRE : `configuration_modifiee()` ne sauve
    jamais la `Configuration`, dont le cache est partagé avec le serveur live.
    / The register needs its module on. It is switched on in memory only.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    taches_demandees=taches_demandees,
                )


# --------------------------------------------------------------------------
# Ce qu'il faut pour vendre : des articles avec leur TVA, des cartes, des monnaies
# / What selling needs: articles with their VAT, cards, currencies
# --------------------------------------------------------------------------


def creer_un_article_de_caisse(
    nom,
    prix_en_euros,
    taux_tva,
    methode_caisse=Product.VENTE,
    prix_achat_en_centimes=0,
    asset=None,
    prix_libre=False,
    vendu_au_poids=False,
):
    """
    Un produit vendu à la caisse, avec son taux de TVA et un tarif en euros.
    Rend un objet avec `produit` et `tarif`.
    / A product sold at the register, with its VAT rate and a euro price.

    :param nom: début du nom du produit (un identifiant unique est ajouté)
    :param prix_en_euros: prix du tarif, en texte (ex. "3.50", "-1.00" pour un retour)
    :param taux_tva: taux de TVA du produit, en texte (ex. "20.00", "5.50")
    :param methode_caisse: `Product.methode_caisse` (VENTE, RECHARGE_EUROS…)
    :param prix_achat_en_centimes: `Product.prix_achat`, dans l'unité de vente ; 0 = inconnu
    :param asset: monnaie du produit (recharge, retour de consigne), ou None
    :param prix_libre: True pour un tarif à prix libre (le prix est alors le minimum)
    :param vendu_au_poids: True pour un tarif au poids (le prix est alors celui du kilo)
    """
    # Le taux est unique en base : on réutilise celui qui existe déjà.
    # / The rate is unique in the database: reuse the existing one.
    tva_du_produit, _tva_creee = Tva.objects.get_or_create(tva_rate=Decimal(taux_tva))
    produit = Product.objects.create(
        name=f"{PREFIXE_DES_TESTS} {nom} {identifiant_unique()}",
        methode_caisse=methode_caisse,
        tva=tva_du_produit,
        prix_achat=prix_achat_en_centimes,
        asset=asset,
        publish=True,
    )
    tarif = Price.objects.create(
        product=produit,
        name="Tarif unique",
        prix=Decimal(prix_en_euros),
        publish=True,
        free_price=prix_libre,
        poids_mesure=vendu_au_poids,
    )
    return SimpleNamespace(produit=produit, tarif=tarif)


def monnaie_locale_du_lieu(lieu):
    """
    La monnaie locale (TLF) que la caisse utilise : la PREMIÈRE du lieu, par ordre de
    nom, lue par la même requête que la caisse (tests/PIEGES.md 9.97).
    / The local currency the register uses: the FIRST one of the venue, by name.
    """
    return (
        AssetService.obtenir_assets_accessibles(lieu.tenant)
        .filter(category=Asset.TLF)
        .first()
    )


def monnaie_cadeau_du_lieu(lieu):
    """La monnaie cadeau (TNF) du lieu, lue comme la caisse la lit.
    / The venue's gift currency (TNF), read like the register reads it."""
    return (
        AssetService.obtenir_assets_accessibles(lieu.tenant)
        .filter(category=Asset.TNF)
        .first()
    )


def creer_une_carte_primaire_en_mode_gerant(point_de_vente):
    """
    La carte primaire d'un gérant, en mode gérant, autorisée sur ce point de vente.
    Le mode gérant est lu EN BASE par la caisse (`CartePrimaire.edit_mode`).
    / A manager's primary card, in manager mode, allowed on this point of sale.

    `tag_id` et `number` font 8 caractères au plus (tests/PIEGES.md 9.31).
    """
    identifiant_de_la_carte = identifiant_unique().upper()
    carte_du_gerant = CarteCashless.objects.create(
        tag_id=identifiant_de_la_carte,
        number=identifiant_de_la_carte,
        uuid=uuid.uuid4(),
    )
    carte_primaire = CartePrimaire.objects.create(
        carte=carte_du_gerant,
        edit_mode=True,
    )
    carte_primaire.points_de_vente.add(point_de_vente)
    return carte_du_gerant


# --------------------------------------------------------------------------
# Gestes du caissier
# / Cashier actions
# --------------------------------------------------------------------------


def nouvelle_cle_d_idempotence():
    """
    Une clé d'idempotence, comme celle que l'écran des moyens de paiement pose dans
    le formulaire (`cle_idempotence_paiement`). Rendue en texte : c'est ainsi que
    `Vente.idempotency_key` la garde.
    / An idempotency key, like the one the payment screen puts in the form.
    """
    return str(uuid.uuid4())


def cle_de_panier(article, numero_de_ligne=None):
    """
    La clé d'un article dans le formulaire de la caisse (#addition-form) :
    `<produit>--<tarif>`, plus `--<n>` pour une ligne à montant variable (prix libre,
    poids), comme addition.js.
    / The article key in the register form, plus `--<n>` for a variable-amount line.
    """
    cle = f"{article.produit.uuid}--{article.tarif.uuid}"
    if numero_de_ligne is not None:
        cle = f"{cle}--{numero_de_ligne}"
    return cle


def payer_un_panier_compose_a_la_caisse(
    client_du_caissier,
    point_de_vente,
    champs_du_panier,
    moyen_de_paiement,
    cle_d_idempotence,
    autres_champs=None,
):
    """
    Le caissier valide un panier (plusieurs articles, prix libre, poids…) avec un
    moyen de paiement, par la vraie route de paiement de la caisse.
    / The cashier validates a cart with one payment method, through the real route.

    `champs_du_panier` : les champs du panier, déjà formés (`repid-…`, `custom-…`,
    `weight-…`), comme addition.js les envoie.
    Paiement exact : `given_sum` vaut 0, il n'y a pas de monnaie à rendre. Le champ
    `total` n'est pas lu par la caisse (elle recalcule le total depuis la base).
    / Exact payment: no change to give back. The `total` field is not read.
    """
    donnees_du_formulaire = {
        "uuid_pv": str(point_de_vente.uuid),
        "moyen_paiement": moyen_de_paiement,
        "total": "0",
        "given_sum": "0",
        "cle_idempotence_paiement": cle_d_idempotence,
    }
    donnees_du_formulaire.update(champs_du_panier)
    if autres_champs is not None:
        donnees_du_formulaire.update(autres_champs)
    return client_du_caissier.post(URL_DU_PAIEMENT_CAISSE, donnees_du_formulaire)


# --------------------------------------------------------------------------
# Assistants de lecture
# / Reading helpers
# --------------------------------------------------------------------------


def retrouver_la_vente_de_la_cle(cle_d_idempotence):
    """
    La vente écrite par le paiement qui portait cette clé d'idempotence.
    Il en faut exactement une : zéro veut dire que la caisse n'a pas écrit de vente,
    deux qu'un rejeu en a écrit une seconde.
    / The sale written by the payment that carried this key. Exactly one is expected.
    """
    ventes_de_la_cle = list(Vente.objects.filter(idempotency_key=cle_d_idempotence))
    assert len(ventes_de_la_cle) == 1, (
        f"Attendu : une vente pour la clé {cle_d_idempotence}, "
        f"trouvé : {len(ventes_de_la_cle)}."
    )
    return ventes_de_la_cle[0]


def reglements_de_la_vente(vente):
    """
    Les règlements de la vente, relus en base : une liste triée de paires
    (moyen, montant en centimes).
    / The sale's payments, read back: a sorted list of (method, amount) pairs.
    """
    paires_moyen_montant = []
    for reglement in vente.reglements.all():
        paires_moyen_montant.append((reglement.moyen, reglement.montant))
    return sorted(paires_moyen_montant)


def nombre_de_transactions_de_la_carte(carte):
    """
    Le nombre de transactions `fedow_core` qui touchent le portefeuille de la carte :
    envoyées (débit d'un achat) ou reçues (crédit d'une recharge).
    / The number of fedow_core transactions touching the card's wallet.
    """
    portefeuille_de_la_carte = carte.wallet_ephemere
    return Transaction.objects.filter(
        Q(sender=portefeuille_de_la_carte) | Q(receiver=portefeuille_de_la_carte)
    ).count()


def seul_article_de_la_vente(vente):
    """
    L'unique article de la vente, relu en base.
    / The sale's only item, read back.
    """
    articles_de_la_vente = list(vente.articles.all())
    assert len(articles_de_la_vente) == 1, (
        f"Attendu : un seul article dans la vente, trouvé : {len(articles_de_la_vente)}."
    )
    return articles_de_la_vente[0]


# --------------------------------------------------------------------------
# 1 — Espèces : trois jus, une vente, un règlement
# / 1 — Cash: three juices, one sale, one payment
# --------------------------------------------------------------------------


def test_vente_especes_trois_jus_une_vente_un_reglement(lieu):
    """
    Le caissier vend 3 jus à 3,50 € (TVA 20 %) en espèces.
    Une vente `VENTE` réglée et numérotée, de la caisse, sur ce point de vente. Un
    règlement espèces de 10,50 €. Un article : catalogue 1050, net 1050, HT 875,
    TVA 175. La ligne garde ses champs d'aujourd'hui (prix unitaire, quantité, moyen
    espèces, statut validé, identifiant de paiement).
    L'opérateur de la vente est l'administrateur connecté à la caisse : le test ne
    présente pas de carte primaire (`tag_id_cm`).
    / 3 juices at 3.50 € (20 % VAT) in cash: one settled, numbered sale; one cash
    payment of 1050; one item 1050 / 875 / 175. The line keeps today's fields. The
    operator is the logged-in venue admin (no primary card here).
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([jus.produit])
    # L'administrateur est créé ici (et non par `creer_un_administrateur_du_lieu`) : le
    # test compare l'opérateur de la vente à cet utilisateur.
    # / Created here: the test compares the sale operator to this user.
    administrateur_du_lieu = creer_utilisateur(prenom="Admin", nom="Lieu")
    administrateur_du_lieu.client_admin.add(lieu.tenant)
    client_du_caissier = client_connecte(administrateur_du_lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        jus,
        quantite=3,
        moyen_de_paiement="espece",
        autres_champs={"cle_idempotence_paiement": cle_d_idempotence},
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.nature == Vente.Nature.VENTE
    assert vente.statut == Vente.Statut.REGLEE
    assert vente.numero is not None
    assert vente.origine == SaleOrigin.LABOUTIK
    assert vente.point_de_vente_id == point_de_vente.pk
    assert vente.operateur_id == administrateur_du_lieu.pk
    assert reglements_de_la_vente(vente) == [(PaymentMethod.CASH, 1050)]

    article = seul_article_de_la_vente(vente)
    assert article.total_catalogue == 1050
    assert article.part_offerte == 0
    assert article.total_ttc == 1050
    assert article.total_ht == 875
    assert article.total_tva == 175
    assert article.hors_chiffre_affaires is False

    # La ligne garde ses champs historiques : les anciens rapports les lisent
    # jusqu'à la fiche H.
    # / The line keeps its historical fields: old reports read them until sheet H.
    assert article.amount == 350
    assert article.qty == 3
    assert article.vat == Decimal("20")
    assert article.payment_method == PaymentMethod.CASH
    assert article.status == LigneArticle.VALID
    assert str(article.uuid_transaction) == cle_d_idempotence

    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 2 — Carte bancaire, prix libre : le total catalogue est la somme saisie
# / 2 — Card, free price: the catalogue total is the amount entered
# --------------------------------------------------------------------------


def test_vente_cb_prix_libre(lieu):
    """
    Un don à prix libre (minimum 1,00 €) : le caissier saisit 7,50 €, payé par carte
    bancaire. L'article vaut 7,50 € au catalogue ; un règlement CB de 7,50 €.
    / A free-price donation (minimum 1.00 €): 7.50 € entered, paid by card. The item's
    catalogue total is 750; one card payment of 750.
    """
    don = creer_un_article_de_caisse(
        "don prix libre", prix_en_euros="1.00", taux_tva="20.00", prix_libre=True
    )
    point_de_vente = creer_un_point_de_vente([don.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    cle_de_la_ligne = cle_de_panier(don, numero_de_ligne=1)
    champs_du_panier = {
        f"repid-{cle_de_la_ligne}": "1",
        f"custom-{cle_de_la_ligne}": "750",
    }

    reponse = payer_un_panier_compose_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        moyen_de_paiement="carte_bancaire",
        cle_d_idempotence=cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    article = seul_article_de_la_vente(vente)
    assert article.amount == 750
    assert article.qty == 1
    assert article.total_catalogue == 750
    assert article.total_ttc == 750
    assert reglements_de_la_vente(vente) == [(PaymentMethod.CC, 750)]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 3 — OFFRIR en mode gérant : tout est offert, règlement FREE du catalogue
# / 3 — GIFT in manager mode: everything offered, FREE payment of the catalogue
# --------------------------------------------------------------------------


def test_offrir_en_mode_gerant_part_offerte_totale(lieu):
    """
    Le gérant (carte primaire en mode gérant) offre 2 verres de vin à 5,00 € (TVA 20 %).
    L'article garde son prix catalogue (10,00 €), entièrement offert par le lieu :
    net 0, HT 0, TVA 0. Un seul règlement, « offert » (FREE), de 10,00 €.
    / The manager gifts 2 glasses of wine at 5.00 €: catalogue 1000, all offered,
    net 0, VAT 0; one FREE payment of 1000.
    """
    vin = creer_un_article_de_caisse("vin", prix_en_euros="5.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([vin.produit])
    carte_du_gerant = creer_une_carte_primaire_en_mode_gerant(point_de_vente)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        vin,
        quantite=2,
        moyen_de_paiement="gift",
        autres_champs={
            "tag_id_cm": carte_du_gerant.tag_id,
            "cle_idempotence_paiement": cle_d_idempotence,
        },
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.statut == Vente.Statut.REGLEE
    article = seul_article_de_la_vente(vente)
    assert article.total_catalogue == 1000
    assert article.part_offerte == 1000
    assert article.source_offert == LigneArticle.SourceOffert.OFFRIR
    assert article.total_ttc == 0
    assert article.total_ht == 0
    assert article.total_tva == 0
    assert reglements_de_la_vente(vente) == [(PaymentMethod.FREE, 1000)]
    assert vente.total_offert == 1000
    assert vente.total_ttc == 0
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 4 — Recharge seule : vente ordinaire, article hors chiffre d'affaires, TVA 0
# / 4 — Top-up only: ordinary sale, off-revenue item, VAT 0
# --------------------------------------------------------------------------


def test_recharge_seule_hors_ca_tva_zero(lieu):
    """
    Le client recharge sa carte de 10,00 € de monnaie locale, payés en espèces.
    Le produit de recharge porte une TVA de 20 % : elle ne s'applique pas. Une recharge
    est une dette envers le porteur (D10), pas une vente taxée.
    La vente est une vente ordinaire (`VENTE`). L'article est hors chiffre d'affaires,
    avec une TVA 0 écrite en base, et HT = net. Un règlement espèces de 10,00 €.
    / A 10.00 € top-up paid in cash. The product carries 20 % VAT, which does not apply:
    ordinary sale, off-revenue item with VAT 0 in the database; one cash payment.
    """
    monnaie_locale = monnaie_locale_du_lieu(lieu)
    recharge = creer_un_article_de_caisse(
        "recharge euros",
        prix_en_euros="10.00",
        taux_tva="20.00",
        methode_caisse=Product.RECHARGE_EUROS,
        asset=monnaie_locale,
    )
    point_de_vente = creer_un_point_de_vente([recharge.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=0)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        recharge,
        quantite=1,
        moyen_de_paiement="espece",
        autres_champs={
            "tag_id": carte_du_client.tag_id,
            "cle_idempotence_paiement": cle_d_idempotence,
        },
    )

    assert reponse.status_code == 200
    # La TVA est lue sur la ligne du tarif d'abord : c'est elle que lisent les anciens
    # rapports (ticket Z, archive fiscale, FEC de la caisse).
    # / The VAT is read on the price's line first: old reports read it.
    ligne_de_la_recharge = LigneArticle.objects.get(pricesold__price=recharge.tarif)
    assert ligne_de_la_recharge.vat == Decimal("0")

    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.nature == Vente.Nature.VENTE
    article = seul_article_de_la_vente(vente)
    assert article.pk == ligne_de_la_recharge.pk
    assert article.hors_chiffre_affaires is True
    assert article.total_catalogue == 1000
    assert article.total_ttc == 1000
    assert article.total_ht == 1000
    assert article.total_tva == 0
    assert reglements_de_la_vente(vente) == [(PaymentMethod.CASH, 1000)]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 5 — Une bière et une recharge dans le même panier : une seule vente
# / 5 — A beer and a top-up in the same cart: one single sale
# --------------------------------------------------------------------------


def test_biere_et_recharge_meme_panier_une_seule_vente(lieu):
    """
    Un panier : une bière à 5,00 € et une recharge de 10,00 €, payés en espèces.
    UNE vente, avec deux articles : la bière (dans le chiffre d'affaires) et la
    recharge (hors chiffre d'affaires). Un seul règlement espèces de 15,00 €.
    Toutes les lignes portent l'identifiant du paiement, recharge comprise.
    / One cart: a 5.00 € beer and a 10.00 € top-up, in cash. ONE sale, two items
    (one off revenue), one cash payment of 1500. Every line carries the payment id.
    """
    monnaie_locale = monnaie_locale_du_lieu(lieu)
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    recharge = creer_un_article_de_caisse(
        "recharge euros",
        prix_en_euros="10.00",
        taux_tva="20.00",
        methode_caisse=Product.RECHARGE_EUROS,
        asset=monnaie_locale,
    )
    point_de_vente = creer_un_point_de_vente([biere.produit, recharge.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=0)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(recharge)}": "1",
    }

    reponse = payer_un_panier_compose_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        moyen_de_paiement="espece",
        cle_d_idempotence=cle_d_idempotence,
        autres_champs={"tag_id": carte_du_client.tag_id},
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    articles_de_la_vente = list(vente.articles.all())
    assert len(articles_de_la_vente) == 2

    articles_hors_chiffre_affaires = []
    for article in articles_de_la_vente:
        if article.hors_chiffre_affaires:
            articles_hors_chiffre_affaires.append(article)
    assert len(articles_hors_chiffre_affaires) == 1
    assert articles_hors_chiffre_affaires[0].pricesold.price_id == recharge.tarif.pk

    for article in articles_de_la_vente:
        assert str(article.uuid_transaction) == cle_d_idempotence, (
            f"La ligne {article.pricesold} n'a pas l'identifiant du paiement."
        )

    assert reglements_de_la_vente(vente) == [(PaymentMethod.CASH, 1500)]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 6 — Recharge cadeau : offerte en totalité, règlement FREE
# / 6 — Gift top-up: fully offered, FREE payment
# --------------------------------------------------------------------------


def test_recharge_cadeau_offerte_en_totalite(lieu):
    """
    Le caissier crédite 10,00 € de monnaie cadeau sur la carte d'un client. Le panier
    ne contient que cette recharge cadeau : la caisse crédite dès l'identification de
    la carte, sans écran de paiement (`identifier_client`, tests/PIEGES.md 9.94).
    L'article est hors chiffre d'affaires, entièrement offert par le lieu (net 0,
    source OFFRIR). Un seul règlement « offert » (FREE) de 10,00 € : le cadeau émis.
    Ce parcours n'a pas de clé d'idempotence : la vente est retrouvée par la ligne du
    tarif créé pour ce test.
    / 10.00 € of gift currency credited at card identification. Off-revenue item,
    fully offered (net 0, OFFRIR); one FREE payment of 1000. No idempotency key here:
    the sale is found through the line of this test's own price.
    """
    monnaie_cadeau = monnaie_cadeau_du_lieu(lieu)
    recharge_cadeau = creer_un_article_de_caisse(
        "recharge cadeau",
        prix_en_euros="10.00",
        taux_tva="20.00",
        methode_caisse=Product.RECHARGE_CADEAU,
        asset=monnaie_cadeau,
    )
    point_de_vente = creer_un_point_de_vente([recharge_cadeau.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=0)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)

    reponse = client_du_caissier.post(
        URL_DE_L_IDENTIFICATION_DU_CLIENT,
        {
            "uuid_pv": str(point_de_vente.uuid),
            "tag_id": carte_du_client.tag_id,
            f"repid-{cle_de_panier(recharge_cadeau)}": "1",
        },
    )

    assert reponse.status_code == 200
    ligne_de_la_recharge = LigneArticle.objects.get(
        pricesold__price=recharge_cadeau.tarif
    )
    assert ligne_de_la_recharge.vente_id is not None, (
        "La ligne de la recharge cadeau n'appartient à aucune vente."
    )
    vente = Vente.objects.get(pk=ligne_de_la_recharge.vente_id)
    assert vente.statut == Vente.Statut.REGLEE
    article = seul_article_de_la_vente(vente)
    assert article.hors_chiffre_affaires is True
    assert article.total_catalogue == 1000
    assert article.part_offerte == 1000
    assert article.source_offert == LigneArticle.SourceOffert.OFFRIR
    assert article.total_ttc == 0
    assert article.total_tva == 0
    assert reglements_de_la_vente(vente) == [(PaymentMethod.FREE, 1000)]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 6b — Recharge cadeau mêlée à d'autres articles : refusée
# / 6b — Gift top-up mixed with other items: refused
# --------------------------------------------------------------------------

# Le refus d'un panier qui mêle une recharge cadeau à d'autres articles (msgid
# français). Le test le compare dans la langue de la réponse (`Content-Language`) :
# il reste vrai quelle que soit la traduction.
# / The refusal of a cart mixing a gift top-up with other items (French msgid),
# compared in the response's language.
MESSAGE_RECHARGE_CADEAU_A_PART = (
    "La recharge cadeau se fait à part : retirez les autres articles."
)


@pytest.mark.parametrize("moyen_de_paiement", ["espece", "nfc"])
def test_recharge_cadeau_melangee_a_d_autres_articles_refusee(lieu, moyen_de_paiement):
    """
    Un panier : une bière à 5,00 € et une recharge cadeau de 10,00 €. La recharge
    cadeau se fait à part (décision du mainteneur) : sinon la caisse demanderait au
    client de payer le cadeau. Le serveur refuse le panier (400), quel que soit le moyen
    de paiement : aucune ligne, aucune vente, aucune transaction sur la carte (ni crédit
    du cadeau, ni débit de la bière).
    / A beer and a gift top-up in one cart: refused by the server (400), whatever the
    payment method. No line, no sale, no transaction on the card.
    """
    monnaie_cadeau = monnaie_cadeau_du_lieu(lieu)
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    recharge_cadeau = creer_un_article_de_caisse(
        "recharge cadeau",
        prix_en_euros="10.00",
        taux_tva="20.00",
        methode_caisse=Product.RECHARGE_CADEAU,
        asset=monnaie_cadeau,
    )
    point_de_vente = creer_un_point_de_vente([biere.produit, recharge_cadeau.produit])
    # La carte porte de quoi payer la bière : un refus n'est donc pas un solde trop bas.
    # / The card can pay the beer: a refusal is not a low balance.
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=2000)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(recharge_cadeau)}": "1",
    }
    nombre_de_transactions_avant = nombre_de_transactions_de_la_carte(carte_du_client)

    reponse = payer_un_panier_compose_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        moyen_de_paiement=moyen_de_paiement,
        cle_d_idempotence=cle_d_idempotence,
        autres_champs={"tag_id": carte_du_client.tag_id},
    )

    assert reponse.status_code == 400
    with translation.override(reponse["Content-Language"]):
        message_de_refus_attendu = translation.gettext(MESSAGE_RECHARGE_CADEAU_A_PART)
    assert message_de_refus_attendu in reponse.content.decode()
    assert not Vente.objects.filter(idempotency_key=cle_d_idempotence).exists()
    assert not LigneArticle.objects.filter(pricesold__price=biere.tarif).exists()
    assert not LigneArticle.objects.filter(
        pricesold__price=recharge_cadeau.tarif
    ).exists()
    nombre_de_transactions_apres = nombre_de_transactions_de_la_carte(carte_du_client)
    assert nombre_de_transactions_apres == nombre_de_transactions_avant


def test_complement_refuse_le_melange_recharge_cadeau(lieu):
    """
    Une requête forgée arrive DIRECTEMENT sur le paiement complémentaire, sans passer
    par `payer` (qui refuse déjà ce panier) : une bière et une recharge cadeau, avec un
    complément en espèces. La garde du complément la refuse aussi (400, message), avant
    tout débit : aucune ligne, aucune vente, aucune transaction sur la carte.
    / A forged request straight to the complementary payment: refused as well (400),
    before any debit. No line, no sale, no transaction on the card.
    """
    monnaie_cadeau = monnaie_cadeau_du_lieu(lieu)
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    recharge_cadeau = creer_un_article_de_caisse(
        "recharge cadeau",
        prix_en_euros="10.00",
        taux_tva="20.00",
        methode_caisse=Product.RECHARGE_CADEAU,
        asset=monnaie_cadeau,
    )
    point_de_vente = creer_un_point_de_vente([biere.produit, recharge_cadeau.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=300)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    nombre_de_transactions_avant = nombre_de_transactions_de_la_carte(carte_du_client)

    reponse = client_du_caissier.post(
        "/laboutik/paiement/payer_complementaire/",
        {
            "uuid_pv": str(point_de_vente.uuid),
            "cle_idempotence_paiement": cle_d_idempotence,
            f"repid-{cle_de_panier(biere)}": "1",
            f"repid-{cle_de_panier(recharge_cadeau)}": "1",
            "tag_id_carte1": carte_du_client.tag_id,
            "moyen_complement": "espece",
            "given_sum": "0",
        },
    )

    assert reponse.status_code == 400
    with translation.override(reponse["Content-Language"]):
        message_de_refus_attendu = translation.gettext(MESSAGE_RECHARGE_CADEAU_A_PART)
    assert message_de_refus_attendu in reponse.content.decode()
    assert not Vente.objects.filter(idempotency_key=cle_d_idempotence).exists()
    assert not LigneArticle.objects.filter(pricesold__price=biere.tarif).exists()
    assert not LigneArticle.objects.filter(
        pricesold__price=recharge_cadeau.tarif
    ).exists()
    nombre_de_transactions_apres = nombre_de_transactions_de_la_carte(carte_du_client)
    assert nombre_de_transactions_apres == nombre_de_transactions_avant


def test_recharge_cadeau_seule_par_la_route_payer_aucun_reglement_d_argent(lieu):
    """
    Une recharge cadeau SEULE, postée sur la route de paiement en espèces. L'écran ne
    propose pas ce chemin (la carte identifiée suffit, `identifier_client`), mais une
    requête peut l'emprunter. La caisse crédite le cadeau sans rien encaisser : une
    vente, AUCUN règlement d'argent, un seul règlement « offert » (FREE) du montant du
    cadeau. Sans cela, un règlement espèces de 10,00 € s'ajouterait à un cadeau offert,
    et les égalités de la vente seraient rompues.
    / A gift top-up ALONE posted on the cash payment route: one sale, NO money payment,
    one FREE payment of the gift amount.
    """
    monnaie_cadeau = monnaie_cadeau_du_lieu(lieu)
    recharge_cadeau = creer_un_article_de_caisse(
        "recharge cadeau",
        prix_en_euros="10.00",
        taux_tva="20.00",
        methode_caisse=Product.RECHARGE_CADEAU,
        asset=monnaie_cadeau,
    )
    point_de_vente = creer_un_point_de_vente([recharge_cadeau.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=0)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        recharge_cadeau,
        quantite=1,
        moyen_de_paiement="espece",
        autres_champs={
            "tag_id": carte_du_client.tag_id,
            "cle_idempotence_paiement": cle_d_idempotence,
        },
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.statut == Vente.Statut.REGLEE
    article = seul_article_de_la_vente(vente)
    assert article.hors_chiffre_affaires is True
    assert article.part_offerte == 1000
    assert article.total_ttc == 0
    assert reglements_de_la_vente(vente) == [(PaymentMethod.FREE, 1000)]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 7, 8 — Retour de consigne : vente AVOIR, au prix et au taux du gobelet vendu
# / 7, 8 — Deposit return: CREDIT NOTE sale, at the sold cup's price and rate
# --------------------------------------------------------------------------


def creer_un_gobelet_et_son_retour(lieu):
    """
    ÉTAT DE DÉPART : un gobelet consigné vendu 1,00 € (TVA 20 %), et le produit
    « Retour de consigne » qui le rembourse (`consigne_remboursee`), avec son propre
    prix (−1,50 €) et son propre taux de TVA (5,5 %), tous deux DIFFÉRENTS de ceux du
    gobelet. Le retour rend de la monnaie locale.
    Rend un objet avec `gobelet` et `retour` (chacun : `produit`, `tarif`).
    / STARTING STATE: a 1.00 € deposit cup (20 % VAT) and the "deposit return" product
    that refunds it, with its own price (−1.50 €) and VAT (5.5 %), both DIFFERENT.

    Le prix et le taux propres du retour sont volontairement faux : la caisse doit
    utiliser partout le prix et le taux du gobelet (D11). Si elle lisait ceux du produit
    de retour, les tests le verraient (−150 au lieu de −100, 5,5 % au lieu de 20 %).
    / The return's own price and rate are wrong on purpose: the register must use the
    cup's everywhere (D11).
    """
    gobelet = creer_un_article_de_caisse(
        "gobelet consigne", prix_en_euros="1.00", taux_tva="20.00"
    )
    retour = creer_un_article_de_caisse(
        "retour gobelet",
        prix_en_euros="-1.50",
        taux_tva="5.50",
        methode_caisse=Product.RETOUR_CONSIGNE,
        asset=monnaie_locale_du_lieu(lieu),
    )
    retour.produit.consigne_remboursee = gobelet.produit
    retour.produit.save()
    return SimpleNamespace(gobelet=gobelet, retour=retour)


def prix_de_la_tuile_a_la_caisse(client_du_caissier, point_de_vente, produit):
    """
    Le prix (en centimes, texte) que la caisse pose sur la tuile d'un produit : l'attribut
    `data-price` de la grille (laboutik/templates/cotton/articles.html). C'est ce prix
    que le JavaScript additionne dans le panier et affiche.
    / The price (cents, text) the register puts on a product tile: `data-price`.
    """
    reponse_de_la_grille = client_du_caissier.get(
        "/laboutik/caisse/point_de_vente/",
        {"uuid_pv": str(point_de_vente.uuid)},
    )
    assert reponse_de_la_grille.status_code == 200
    html_de_la_grille = reponse_de_la_grille.content.decode()
    motif_de_la_tuile = re.compile(
        r'data-uuid="' + re.escape(str(produit.uuid)) + r'"[^>]*?data-price="([^"]*)"'
    )
    correspondance = motif_de_la_tuile.search(html_de_la_grille)
    assert correspondance is not None, "La tuile du produit est absente de la grille."
    return correspondance.group(1)


def test_retour_consigne_reprend_prix_et_tva_du_gobelet(lieu):
    """
    Le client rapporte son gobelet ; le caissier rembourse 1,00 € sur sa carte.
    Partout, la caisse utilise le prix du GOBELET (1,00 €), jamais celui du produit de
    retour (−1,50 €) : sur la tuile (−100, un remboursement), dans le recrédit de la
    carte (100), dans l'article (−100).
    La vente est un AVOIR, sans vente liée (le gobelet est anonyme). L'article reprend
    le taux du GOBELET (20 %), pas celui du produit de retour (5,5 %) : il annule
    exactement la vente du gobelet, TVA comprise (D11). Montants : −100 / HT −83 /
    TVA −17. La ligne garde un prix négatif et une quantité positive jusqu'à la fiche H.
    Un règlement négatif en monnaie locale, de −1,00 €, sur la carte : c'est la
    transaction de recrédit de la carte.
    / A cup returned, 1.00 € refunded on the card. The CUP's price is used everywhere
    (tile, card re-credit, item), and the CUP's rate (20 %). CREDIT NOTE sale, one
    negative local-currency payment, the card's re-credit transaction.
    """
    consigne = creer_un_gobelet_et_son_retour(lieu)
    point_de_vente = creer_un_point_de_vente([consigne.retour.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=0)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    # La tuile du retour porte le prix du gobelet, en remboursement.
    # / The return tile carries the cup's price, as a refund.
    prix_de_la_tuile = prix_de_la_tuile_a_la_caisse(
        client_du_caissier, point_de_vente, consigne.retour.produit
    )
    assert prix_de_la_tuile == "-100"

    reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        consigne.retour,
        quantite=1,
        moyen_de_paiement="nfc",
        autres_champs={
            "tag_id": carte_du_client.tag_id,
            "cle_idempotence_paiement": cle_d_idempotence,
        },
    )

    assert reponse.status_code == 200
    # La carte est recréditée du prix du gobelet.
    # / The card is re-credited with the cup's price.
    monnaie_locale = monnaie_locale_du_lieu(lieu)
    transaction_de_recredit = Transaction.objects.get(
        receiver=carte_du_client.wallet_ephemere,
        asset=monnaie_locale,
        action=Transaction.REFILL,
    )
    assert transaction_de_recredit.amount == 100

    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.nature == Vente.Nature.AVOIR
    assert vente.vente_liee_id is None
    assert vente.statut == Vente.Statut.REGLEE

    # L'article garde le tarif vendu du produit de retour (décision de l'orchestrateur,
    # SUIVI §4), avec le prix et le taux du gobelet.
    # / The item keeps the return product's sold price, with the cup's price and rate.
    article = seul_article_de_la_vente(vente)
    assert article.pricesold.price_id == consigne.retour.tarif.pk
    assert article.vat == Decimal("20")
    assert article.amount == -100
    assert article.qty == 1
    assert article.total_catalogue == -100
    assert article.total_ttc == -100
    assert article.total_ht == -83
    assert article.total_tva == -17

    reglements = list(vente.reglements.all())
    assert len(reglements) == 1
    reglement = reglements[0]
    assert reglement.moyen == PaymentMethod.LOCAL_EURO
    assert reglement.montant == -100
    assert reglement.asset == monnaie_locale.uuid
    assert reglement.carte_id == carte_du_client.pk
    assert reglement.fedow_transaction_uuid == transaction_de_recredit.uuid
    verifier_egalites(vente)


def test_retour_consigne_especes_vente_avoir(lieu):
    """
    Le client rapporte son gobelet ; le caissier lui rend 1,00 € en espèces : le prix
    du gobelet, pas celui du produit de retour (−1,50 €). L'écran de la caisse annonce
    1,00 € à rendre.
    La vente est un AVOIR ; un règlement espèces NÉGATIF de −1,00 € ; l'article vaut
    −1,00 € au catalogue, à 20 %.
    / A cup returned, 1.00 € (the cup's price) given back in cash; the screen shows
    1.00 € to give back. CREDIT NOTE sale, one NEGATIVE cash payment of −100.
    """
    consigne = creer_un_gobelet_et_son_retour(lieu)
    point_de_vente = creer_un_point_de_vente([consigne.retour.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        consigne.retour,
        quantite=1,
        moyen_de_paiement="espece",
        autres_champs={"cle_idempotence_paiement": cle_d_idempotence},
    )

    assert reponse.status_code == 200
    # L'écran de succès annonce la somme à rendre, en euros (valeur absolue).
    # / The success screen shows the amount to give back, in euros.
    assert reponse.context["total"] == 1

    # La ligne garde le tarif vendu du produit de retour, au prix du gobelet.
    # / The line keeps the return product's sold price, at the cup's price.
    ligne_du_retour = LigneArticle.objects.get(pricesold__price=consigne.retour.tarif)
    assert ligne_du_retour.amount == -100

    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.nature == Vente.Nature.AVOIR
    article = seul_article_de_la_vente(vente)
    assert article.pk == ligne_du_retour.pk
    assert article.vat == Decimal("20")
    assert article.total_catalogue == -100
    assert reglements_de_la_vente(vente) == [(PaymentMethod.CASH, -100)]
    verifier_egalites(vente)


def test_retour_consigne_sans_consigne_reliee_refuse(lieu):
    """
    Un produit « Retour de consigne » qui ne dit pas quelle consigne il rembourse ne
    peut pas être encaissé : la caisse ne connaîtrait ni le prix ni le taux à annuler.
    Le paiement est refusé (400), et rien n'est écrit : ni vente, ni ligne.
    / A deposit return without a linked deposit product is refused (400): no sale,
    no line written.
    """
    retour_sans_consigne = creer_un_article_de_caisse(
        "retour sans consigne",
        prix_en_euros="-1.00",
        taux_tva="20.00",
        methode_caisse=Product.RETOUR_CONSIGNE,
        asset=monnaie_locale_du_lieu(lieu),
    )
    point_de_vente = creer_un_point_de_vente([retour_sans_consigne.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        retour_sans_consigne,
        quantite=1,
        moyen_de_paiement="espece",
        autres_champs={"cle_idempotence_paiement": cle_d_idempotence},
    )

    assert reponse.status_code == 400
    assert not Vente.objects.filter(idempotency_key=cle_d_idempotence).exists()
    assert not LigneArticle.objects.filter(
        pricesold__price=retour_sans_consigne.tarif
    ).exists()


# --------------------------------------------------------------------------
# Retour de consigne : le coût d'achat est celui du gobelet, en négatif
# / Deposit return: the purchase cost is the cup's, negative
# --------------------------------------------------------------------------


def poser_les_prix_d_achat(consigne, prix_achat_du_gobelet, prix_achat_du_retour):
    """
    Pose le prix d'achat (en centimes, à la pièce) du gobelet et celui du produit de
    retour. Écrit par `update()` : aucun signal, rien d'autre ne change.
    / Sets the purchase price (cents, per piece) of the cup and of the return product.

    Le prix d'achat du produit de retour est volontairement NON NUL (99) : la caisse ne
    doit jamais le lire. S'il était lu, le coût de l'article le montrerait.
    / The return product's own purchase price is NON-ZERO on purpose: it must never be
    read.
    """
    Product.objects.filter(pk=consigne.gobelet.produit.pk).update(
        prix_achat=prix_achat_du_gobelet
    )
    Product.objects.filter(pk=consigne.retour.produit.pk).update(
        prix_achat=prix_achat_du_retour
    )


def test_retour_consigne_cout_d_achat_du_gobelet_en_negatif(lieu):
    """
    Le client rapporte DEUX gobelets ; le caissier lui rend l'argent en espèces.
    Le gobelet a coûté 0,30 € au lieu. Un gobelet rendu annule son coût dans la marge
    (D21, « retours de consigne en négatif ») : le coût d'achat de l'article vaut
    2 × −30 = −60 centimes. Le prix d'achat du produit de retour (99) n'est pas lu.
    / Two cups returned, cash given back. The cup cost 0.30 €: a returned cup cancels
    its cost in the margin, so the item's purchase cost is 2 × −30 = −60. The return
    product's own purchase price (99) is not read.
    """
    consigne = creer_un_gobelet_et_son_retour(lieu)
    poser_les_prix_d_achat(consigne, prix_achat_du_gobelet=30, prix_achat_du_retour=99)
    point_de_vente = creer_un_point_de_vente([consigne.retour.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        consigne.retour,
        quantite=2,
        moyen_de_paiement="espece",
        autres_champs={"cle_idempotence_paiement": cle_d_idempotence},
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.nature == Vente.Nature.AVOIR
    article = seul_article_de_la_vente(vente)
    assert article.qty == 2
    assert article.total_catalogue == -200
    assert article.cout_achat == -60
    assert reglements_de_la_vente(vente) == [(PaymentMethod.CASH, -200)]
    verifier_egalites(vente)


def test_retour_consigne_par_carte_cout_d_achat_du_gobelet_en_negatif(lieu):
    """
    Même règle quand le gobelet est remboursé sur la carte du client (recrédit, chemin
    `_rembourser_consigne_par_nfc`) : un gobelet rendu, coût d'achat −30 centimes.
    / Same rule when the cup is refunded onto the customer's card: one cup returned,
    purchase cost −30.
    """
    consigne = creer_un_gobelet_et_son_retour(lieu)
    poser_les_prix_d_achat(consigne, prix_achat_du_gobelet=30, prix_achat_du_retour=99)
    point_de_vente = creer_un_point_de_vente([consigne.retour.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=0)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        consigne.retour,
        quantite=1,
        moyen_de_paiement="nfc",
        autres_champs={
            "tag_id": carte_du_client.tag_id,
            "cle_idempotence_paiement": cle_d_idempotence,
        },
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.nature == Vente.Nature.AVOIR
    article = seul_article_de_la_vente(vente)
    assert article.total_catalogue == -100
    assert article.cout_achat == -30
    verifier_egalites(vente)


def test_retour_consigne_gobelet_sans_prix_d_achat_cout_inconnu(lieu):
    """
    Le gobelet n'a pas de prix d'achat (0 = inconnu, D21) : le coût d'achat du retour
    est inconnu aussi (vide), comme pour tout article au prix d'achat inconnu. Le prix
    d'achat du produit de retour (99) ne le remplace pas.
    / The cup has no purchase price (0 = unknown): the return's purchase cost is unknown
    too (empty). The return product's own purchase price (99) does not stand in.
    """
    consigne = creer_un_gobelet_et_son_retour(lieu)
    poser_les_prix_d_achat(consigne, prix_achat_du_gobelet=0, prix_achat_du_retour=99)
    point_de_vente = creer_un_point_de_vente([consigne.retour.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        consigne.retour,
        quantite=1,
        moyen_de_paiement="espece",
        autres_champs={"cle_idempotence_paiement": cle_d_idempotence},
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    article = seul_article_de_la_vente(vente)
    assert article.cout_achat is None
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# Retour de consigne : pas de tuile quand la caisse ne sait pas calculer son prix
# / Deposit return: no tile when the register cannot compute its price
# --------------------------------------------------------------------------


def html_de_la_grille_de_la_caisse(client_du_caissier, point_de_vente):
    """
    La page de la caisse d'un point de vente (la grille des tuiles), en texte.
    / The register page of a point of sale (the tile grid), as text.
    """
    reponse_de_la_grille = client_du_caissier.get(
        "/laboutik/caisse/point_de_vente/",
        {"uuid_pv": str(point_de_vente.uuid)},
    )
    assert reponse_de_la_grille.status_code == 200
    return reponse_de_la_grille.content.decode()


def la_tuile_du_produit_est_affichee(html_de_la_grille, produit):
    """
    Vrai si la grille contient la tuile du produit : son attribut
    `data-testid="article-<uuid>"` (laboutik/templates/cotton/articles.html).
    / True if the grid holds the product's tile.
    """
    attribut_de_la_tuile = f'data-testid="article-{produit.uuid}"'
    return attribut_de_la_tuile in html_de_la_grille


def test_tuile_retour_consigne_sans_consigne_reliee_masquee(lieu):
    """
    Un produit « Retour de consigne » qui ne dit pas quelle consigne il rembourse n'a
    pas de tuile : la caisse ne sait pas quel prix rendre. La tuile d'un article
    ordinaire du même point de vente est bien là : la grille est donc affichée.
    / A deposit return without a linked deposit has no tile. An ordinary item of the
    same point of sale has its tile: the grid is displayed.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    retour_sans_consigne = creer_un_article_de_caisse(
        "retour sans consigne",
        prix_en_euros="-1.00",
        taux_tva="20.00",
        methode_caisse=Product.RETOUR_CONSIGNE,
        asset=monnaie_locale_du_lieu(lieu),
    )
    point_de_vente = creer_un_point_de_vente(
        [biere.produit, retour_sans_consigne.produit]
    )
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)

    html_de_la_grille = html_de_la_grille_de_la_caisse(
        client_du_caissier, point_de_vente
    )

    assert la_tuile_du_produit_est_affichee(html_de_la_grille, biere.produit)
    assert not la_tuile_du_produit_est_affichee(
        html_de_la_grille, retour_sans_consigne.produit
    )


def test_tuile_retour_consigne_gobelet_sans_tarif_en_euros_masquee(lieu):
    """
    Le retour est relié à son gobelet, mais le seul tarif en euros du gobelet a été
    dépublié après coup : la caisse ne sait plus quel prix rendre. Le retour n'a pas
    de tuile. La tuile d'un article ordinaire du même point de vente est bien là.
    / The return is linked to its cup, but the cup's only euro price was unpublished
    afterwards: no tile for the return. An ordinary item keeps its tile.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    consigne = creer_un_gobelet_et_son_retour(lieu)
    Price.objects.filter(pk=consigne.gobelet.tarif.pk).update(publish=False)
    point_de_vente = creer_un_point_de_vente(
        [biere.produit, consigne.retour.produit]
    )
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)

    html_de_la_grille = html_de_la_grille_de_la_caisse(
        client_du_caissier, point_de_vente
    )

    assert la_tuile_du_produit_est_affichee(html_de_la_grille, biere.produit)
    assert not la_tuile_du_produit_est_affichee(
        html_de_la_grille, consigne.retour.produit
    )


# --------------------------------------------------------------------------
# 17 — Le HT d'une ligne est celui du service : 111 centimes à 20 % → 93
# / 17 — A line's HT is the service's: 111 cents at 20 % → 93
# --------------------------------------------------------------------------


def test_ht_de_la_part_111_centimes_vaut_93(lieu):
    """
    Un article à 1,11 € (TVA 20 %) payé en espèces. 111 × 100 / 120 = 92,5 : l'arrondi
    « demi vers le haut » du service donne 93 (TVA 18). Un arrondi au pair (`round()`
    de Python) donnerait 92, et HT + TVA ne vaudrait plus le net.
    La boucle d'empreinte (HMAC) de la caisse tourne toujours sur la ligne, mais elle
    ne recalcule pas le HT : relu en base, il vaut 93.
    / An item at 1.11 € (20 % VAT) in cash: half-up gives HT 93 (VAT 18), round() would
    give 92. The HMAC loop still runs on the line, without recomputing HT.
    """
    article_a_111 = creer_un_article_de_caisse(
        "article a 1,11", prix_en_euros="1.11", taux_tva="20.00"
    )
    point_de_vente = creer_un_point_de_vente([article_a_111.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        article_a_111,
        quantite=1,
        moyen_de_paiement="espece",
        autres_champs={"cle_idempotence_paiement": cle_d_idempotence},
    )

    assert reponse.status_code == 200
    # Le HT est lu sur la ligne du tarif d'abord, relu en base APRÈS la boucle HMAC.
    # / HT is read on the price's line first, read back AFTER the HMAC loop.
    ligne_de_l_article = LigneArticle.objects.get(pricesold__price=article_a_111.tarif)
    assert ligne_de_l_article.total_ht == 93
    assert ligne_de_l_article.hmac_hash != "", "La boucle HMAC n'a pas chaîné la ligne."

    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    article = seul_article_de_la_vente(vente)
    assert article.pk == ligne_de_l_article.pk
    assert article.total_ttc == 111
    assert article.total_ht == 93
    assert article.total_tva == 18
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 17b — Vente au poids : le coût d'achat porte sur le poids réel
# / 17b — Weighed sale: the purchase cost is on the real weight
# --------------------------------------------------------------------------


def test_vente_au_poids_cout_sur_le_poids_reel(lieu):
    """
    350 g de fromage à 20,00 €/kg (prix d'achat 8,00 €/kg), payés en espèces.
    La ligne garde `qty = 1` et le poids (350 g) dans `weight_quantity`, comme
    aujourd'hui. Prix : 7,00 €. Le coût d'achat porte sur le poids réel :
    0,350 kg × 800 = 280 centimes (et non 800, le coût d'un kilo).
    / 350 g of cheese at 20.00 €/kg (bought 8.00 €/kg), in cash. qty stays 1, the
    weight is in weight_quantity. Price 700; purchase cost on the real weight: 280.
    """
    fromage = creer_un_article_de_caisse(
        "fromage au poids",
        prix_en_euros="20.00",
        taux_tva="5.50",
        prix_achat_en_centimes=800,
        vendu_au_poids=True,
    )
    point_de_vente = creer_un_point_de_vente([fromage.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    cle_de_la_ligne = cle_de_panier(fromage, numero_de_ligne=1)
    champs_du_panier = {
        f"repid-{cle_de_la_ligne}": "1",
        f"weight-{cle_de_la_ligne}": "350",
        f"custom-{cle_de_la_ligne}": "700",
    }

    reponse = payer_un_panier_compose_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        moyen_de_paiement="espece",
        cle_d_idempotence=cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    article = seul_article_de_la_vente(vente)
    assert article.amount == 700
    assert article.qty == 1
    assert article.weight_quantity == 350
    assert article.total_catalogue == 700
    assert article.cout_achat == 280
    assert reglements_de_la_vente(vente) == [(PaymentMethod.CASH, 700)]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 22 — Double appui sur « Valider » : une seule vente
# / 22 — Double tap on "Validate": one single sale
# --------------------------------------------------------------------------


def test_rejeu_meme_cle_idempotence_une_seule_vente(lieu):
    """
    Le caissier appuie deux fois sur « Valider » pour 2 bières à 5,00 € en espèces.
    Les deux envois portent la MÊME clé d'idempotence. Les deux réponses sont des
    succès, mais une seule vente existe pour cette clé, avec un seul article et un
    seul règlement espèces de 10,00 €.
    / The same cash payment posted twice with the SAME key: both answers succeed, but
    only one sale exists, with one item and one cash payment of 1000.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champ_de_la_cle = {"cle_idempotence_paiement": cle_d_idempotence}

    premiere_reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        biere,
        quantite=2,
        moyen_de_paiement="espece",
        autres_champs=champ_de_la_cle,
    )
    deuxieme_reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        biere,
        quantite=2,
        moyen_de_paiement="espece",
        autres_champs=champ_de_la_cle,
    )

    assert premiere_reponse.status_code == 200
    assert deuxieme_reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    article = seul_article_de_la_vente(vente)
    assert article.total_catalogue == 1000
    assert reglements_de_la_vente(vente) == [(PaymentMethod.CASH, 1000)]
    verifier_egalites(vente)


# ==========================================================================
# PAIEMENT PAR LA CARTE NFC DU CLIENT (cascade des monnaies)
# / PAYMENT WITH THE CUSTOMER'S NFC CARD (currency cascade)
# ==========================================================================
#
# La caisse débite la carte monnaie par monnaie, dans un ordre fixe : jetons cadeau
# (TNF), puis monnaie locale (TLF), puis monnaie fédérée (FED). Un article payé avec
# deux monnaies est écrit en deux lignes (« parts »), une par monnaie.
# / The register debits the card currency by currency: gift tokens, then local
# currency, then federated currency. An item paid with two currencies is two lines.


def ajouter_un_solde_sur_la_carte(carte, monnaie, montant_en_centimes):
    """
    Pose un solde de `montant_en_centimes` dans `monnaie`, sur le portefeuille de la
    carte. La monnaie ne doit pas déjà être sur la carte : `creer_une_carte_nfc_chargee`
    y pose déjà la monnaie locale.
    / Puts a balance in `monnaie` on the card's wallet. The currency must not already
    be on the card (the card helper already puts the local currency there).
    """
    Token.objects.create(
        wallet=carte.wallet_ephemere,
        asset=monnaie,
        value=montant_en_centimes,
    )


def solde_de_la_carte(carte, monnaie):
    """Le solde de la carte dans cette monnaie, relu en base (centimes).
    / The card's balance in this currency, read back (cents)."""
    return WalletService.obtenir_solde(wallet=carte.wallet_ephemere, asset=monnaie)


def transactions_de_vente_de_la_carte(carte):
    """
    Les transactions `fedow_core` de VENTE débitées sur le portefeuille de la carte :
    les débits réellement faits par la caisse. La carte est créée par le test : ses
    transactions sont celles du test.
    / The fedow_core SALE transactions debited from the card's wallet: the real debits.
    """
    return list(
        Transaction.objects.filter(
            sender=carte.wallet_ephemere,
            action=Transaction.SALE,
        )
    )


def reglements_en_detail(vente):
    """
    Les règlements de la vente, relus en base : une liste triée de tuples
    (moyen, montant, uuid de la transaction fedow_core ou None).
    / The sale's payments, read back: sorted (method, amount, fedow_core uuid) tuples.
    """
    reglements_lus = []
    for reglement in vente.reglements.all():
        reglements_lus.append(
            (reglement.moyen, reglement.montant, reglement.fedow_transaction_uuid)
        )
    return sorted(reglements_lus, key=str)


def debits_en_detail(transactions):
    """
    Les débits réellement faits, dans la même forme que `reglements_en_detail` (sans
    le moyen) : une liste triée de paires (montant, uuid de la transaction).
    / The real debits as sorted (amount, uuid) pairs.
    """
    debits_lus = []
    for transaction_de_vente in transactions:
        debits_lus.append((transaction_de_vente.amount, transaction_de_vente.uuid))
    return sorted(debits_lus, key=str)


def payer_par_la_carte_du_client(
    client_du_caissier, point_de_vente, champs_du_panier, carte, cle_d_idempotence
):
    """
    Le caissier valide un panier et le client pose sa carte NFC : la vraie route de
    paiement de la caisse, moyen « nfc ».
    / The cashier validates a cart and the customer taps the NFC card: the real route.
    """
    return payer_un_panier_compose_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        moyen_de_paiement="nfc",
        cle_d_idempotence=cle_d_idempotence,
        autres_champs={"tag_id": carte.tag_id},
    )


def articles_de_la_vente_par_moyen(vente):
    """
    Les articles (parts) de la vente, rangés par moyen de paiement de la ligne :
    {moyen: [article, …]}.
    / The sale's items (parts), grouped by the line's payment method.
    """
    articles_par_moyen = {}
    for article in vente.articles.all():
        if article.payment_method not in articles_par_moyen:
            articles_par_moyen[article.payment_method] = []
        articles_par_moyen[article.payment_method].append(article)
    return articles_par_moyen


# --------------------------------------------------------------------------
# 10 — Un règlement par transaction fedow_core, de son montant
# / 10 — One payment per fedow_core transaction, of its amount
# --------------------------------------------------------------------------


def test_reglement_fedow_egal_montant_de_la_transaction(lieu):
    """
    Une bière à 5,00 € et un jus à 3,50 €, payés par la carte du client, qui porte
    3,00 € de jetons cadeau et 10,00 € de monnaie locale. La cascade débite 3,00 € de
    jetons (sur la bière) et 5,50 € de monnaie locale (reste de la bière + le jus) :
    deux transactions, une par monnaie. La monnaie locale couvre DEUX parts.
    La vente a un règlement par transaction réellement créée : même montant, et
    l'uuid de cette transaction dans `fedow_transaction_uuid`. La somme des règlements
    vaut la somme des débits.
    / A beer (5.00 €) and a juice (3.50 €) paid by card: 3.00 € of gift tokens and
    5.50 € of local currency, two transactions. One payment per transaction created,
    with its amount and its uuid.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit, jus.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=1000)
    ajouter_un_solde_sur_la_carte(carte_du_client, monnaie_cadeau_du_lieu(lieu), 300)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(jus)}": "1",
    }

    reponse = payer_par_la_carte_du_client(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        carte_du_client,
        cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    transactions_creees = transactions_de_vente_de_la_carte(carte_du_client)
    assert len(transactions_creees) == 2

    # Un règlement par transaction : même montant, même uuid.
    # / One payment per transaction: same amount, same uuid.
    reglements_lus = list(vente.reglements.all())
    assert len(reglements_lus) == len(transactions_creees)
    paires_des_reglements = []
    for reglement in reglements_lus:
        paires_des_reglements.append(
            (reglement.montant, reglement.fedow_transaction_uuid)
        )
        assert reglement.carte_id == carte_du_client.pk
    assert sorted(paires_des_reglements, key=str) == debits_en_detail(
        transactions_creees
    )

    somme_des_reglements = 0
    for reglement in reglements_lus:
        somme_des_reglements += reglement.montant
    somme_des_debits = 0
    for transaction_de_vente in transactions_creees:
        somme_des_debits += transaction_de_vente.amount
    assert somme_des_reglements == somme_des_debits == 850

    assert reglements_de_la_vente(vente) == [
        (PaymentMethod.LOCAL_EURO, 550),
        (PaymentMethod.LOCAL_GIFT, 300),
    ]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 11 — Deux articles, une seule monnaie : un seul règlement
# / 11 — Two items, one currency: a single payment
# --------------------------------------------------------------------------


def test_deux_articles_meme_monnaie_un_seul_reglement_par_monnaie(lieu):
    """
    Une bière à 5,00 € et un jus à 3,50 €, payés par la carte du client en monnaie
    locale seulement (10,00 € sur la carte). La caisse fait UNE transaction de 8,50 €
    pour la monnaie locale : la vente a deux articles et UN règlement monnaie locale
    de 8,50 €, qui porte l'uuid de cette transaction.
    / Two items paid in local currency only: one 8.50 € transaction, so two items and
    ONE local-currency payment of 850, carrying the transaction's uuid.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit, jus.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=1000)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(jus)}": "1",
    }

    reponse = payer_par_la_carte_du_client(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        carte_du_client,
        cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.articles.count() == 2
    transactions_creees = transactions_de_vente_de_la_carte(carte_du_client)
    assert len(transactions_creees) == 1
    transaction_de_la_monnaie_locale = transactions_creees[0]
    assert reglements_en_detail(vente) == [
        (PaymentMethod.LOCAL_EURO, 850, transaction_de_la_monnaie_locale.uuid)
    ]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 12a — Jetons et monnaie locale sur UN article : parts entières
# / 12a — Tokens and local currency on ONE item: whole parts
# --------------------------------------------------------------------------


def test_jetons_et_monnaie_locale_sur_un_article_parts_entieres(lieu):
    """
    Une bière à 5,00 € (TVA 20 %) payée par la carte du client : 3,00 € de jetons
    cadeau, puis 2,00 € de monnaie locale. L'article est coupé en deux parts entières.
    - part jetons : catalogue 300, rien d'offert, net 300 (vente ordinaire, D8 bis) ;
    - part monnaie locale : catalogue 200, rien d'offert, net 200.
    Un règlement « jetons » (LG) de 300 et un règlement monnaie locale (LE) de 200.
    Vente : catalogue 500, offert 0, net 500, HT 467 (300 à TVA 0 + 167), TVA 33.
    / A 5.00 € beer paid 3.00 € in gift tokens + 2.00 € in local currency: two whole
    parts, nothing offered, payments LG 300 + LE 200; sale totals.
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
    articles_par_moyen = articles_de_la_vente_par_moyen(vente)
    assert sorted(articles_par_moyen.keys()) == [
        PaymentMethod.LOCAL_EURO,
        PaymentMethod.LOCAL_GIFT,
    ]
    assert len(articles_par_moyen[PaymentMethod.LOCAL_GIFT]) == 1
    assert len(articles_par_moyen[PaymentMethod.LOCAL_EURO]) == 1

    part_en_jetons = articles_par_moyen[PaymentMethod.LOCAL_GIFT][0]
    assert part_en_jetons.total_catalogue == 300
    assert part_en_jetons.part_offerte == 0
    assert part_en_jetons.source_offert == ""
    assert part_en_jetons.total_ttc == 300

    part_en_monnaie_locale = articles_par_moyen[PaymentMethod.LOCAL_EURO][0]
    assert part_en_monnaie_locale.total_catalogue == 200
    assert part_en_monnaie_locale.part_offerte == 0
    assert part_en_monnaie_locale.total_ttc == 200

    # Les deux parts gardent leurs champs historiques : même prix unitaire, une
    # quantité partielle chacune, la carte du client.
    # / Both parts keep their historical fields: unit price, partial quantity, card.
    for part in (part_en_jetons, part_en_monnaie_locale):
        assert part.amount == 500
        assert part.carte_id == carte_du_client.pk
        assert str(part.uuid_transaction) == cle_d_idempotence

    assert reglements_de_la_vente(vente) == [
        (PaymentMethod.LOCAL_EURO, 200),
        (PaymentMethod.LOCAL_GIFT, 300),
    ]
    assert vente.total_catalogue == 500
    assert vente.total_offert == 0
    assert vente.total_ttc == 500
    assert vente.total_ht == 467
    assert vente.total_tva == 33
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 12a bis — La part payée en jetons est une vente ordinaire, sans TVA (D8 bis)
# / 12a bis — The part paid in tokens is an ordinary sale, without VAT (D8 bis)
# --------------------------------------------------------------------------


def test_jetons_vente_ordinaire_tva_zero(lieu):
    """
    Une bière à 5,00 € (TVA 20 %) payée par la carte du client : 3,00 € de jetons
    cadeau, puis 2,00 € de monnaie locale. L'article est coupé en deux parts.
    Un jeton dépensé solde la dette du lieu envers le porteur (D8 bis) : la part payée
    en jetons est une VENTE ORDINAIRE, hors TVA.
    - part jetons : catalogue 300, rien d'offert, sans source d'offert, net 300, TVA 0 %
      (HT 300, TVA 0) ;
    - part monnaie locale : catalogue 200, net 200, TVA 20 % (HT 167, TVA 33).
    Le règlement « jetons » (LG) de 300 est un vrai règlement : il compte dans les deux
    égalités. Vente : catalogue 500, offert 0, net 500, HT 467, TVA 33.
    / A 5.00 € beer paid 3.00 € in gift tokens + 2.00 € in local currency. The token
    part is an ordinary sale without VAT (net 300, nothing offered, VAT 0); the LG
    payment counts in both equalities. Sale: net 500, HT 467, VAT 33.
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
    articles_par_moyen = articles_de_la_vente_par_moyen(vente)
    assert len(articles_par_moyen[PaymentMethod.LOCAL_GIFT]) == 1
    assert len(articles_par_moyen[PaymentMethod.LOCAL_EURO]) == 1

    # La part en jetons : une vente ordinaire, au taux 0.
    # / The token part: an ordinary sale, at a 0 rate.
    part_en_jetons = articles_par_moyen[PaymentMethod.LOCAL_GIFT][0]
    assert part_en_jetons.total_catalogue == 300
    assert part_en_jetons.part_offerte == 0
    assert part_en_jetons.source_offert == ""
    assert part_en_jetons.total_ttc == 300
    assert part_en_jetons.vat == 0
    assert part_en_jetons.total_ht == 300
    assert part_en_jetons.total_tva == 0

    # La part en monnaie locale garde la TVA du produit.
    # / The local currency part keeps the product's VAT.
    part_en_monnaie_locale = articles_par_moyen[PaymentMethod.LOCAL_EURO][0]
    assert part_en_monnaie_locale.vat == Decimal("20.00")
    assert part_en_monnaie_locale.total_ttc == 200
    assert part_en_monnaie_locale.total_ht == 167
    assert part_en_monnaie_locale.total_tva == 33

    assert reglements_de_la_vente(vente) == [
        (PaymentMethod.LOCAL_EURO, 200),
        (PaymentMethod.LOCAL_GIFT, 300),
    ]
    assert vente.total_catalogue == 500
    assert vente.total_offert == 0
    assert vente.total_ttc == 500
    assert vente.total_ht == 467
    assert vente.total_tva == 33
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 14 — Vente en points : unité = la monnaie, TVA 0, un règlement par transaction
# / 14 — Points sale: unit = the currency, VAT 0, one payment per transaction
# --------------------------------------------------------------------------


def creer_une_monnaie_de_points(lieu):
    """
    Une monnaie de points de fidélité (FID) du lieu, avec son propre portefeuille
    d'origine. Une monnaie FID ne crée pas de produit de recharge (signal d'Asset).
    / A loyalty points currency (FID) of the venue. FID creates no top-up product.
    """
    portefeuille_du_lieu = Wallet.objects.create(
        name=f"{PREFIXE_DES_TESTS} portefeuille points {identifiant_unique()}",
        origin=lieu.tenant,
    )
    return AssetService.creer_asset(
        tenant=lieu.tenant,
        name=f"{PREFIXE_DES_TESTS} points {identifiant_unique()}",
        category=Asset.FID,
        currency_code="PTS",
        wallet_origin=portefeuille_du_lieu,
    )


def creer_un_article_en_points(nom, prix_en_points, monnaie_de_points):
    """
    Un produit de caisse dont le seul tarif est en points (`non_fiduciaire`, monnaie
    posée). Le produit porte une TVA de 20 % : une vente en points ne doit pas la
    reprendre.
    Rend un objet avec `produit` et `tarif`.
    / A register product whose only price is in points. The product carries 20 % VAT,
    which a points sale must not use.
    """
    tva_du_produit, _tva_creee = Tva.objects.get_or_create(tva_rate=Decimal("20.00"))
    produit = Product.objects.create(
        name=f"{PREFIXE_DES_TESTS} {nom} {identifiant_unique()}",
        methode_caisse=Product.VENTE,
        tva=tva_du_produit,
        publish=True,
    )
    tarif = Price.objects.create(
        product=produit,
        name="Points",
        prix=Decimal(prix_en_points),
        non_fiduciaire=True,
        asset=monnaie_de_points,
        publish=True,
    )
    return SimpleNamespace(produit=produit, tarif=tarif)


def test_vente_en_points_unite_monnaie_tva_zero(lieu):
    """
    Un pin's et une médaille à 3 points chacun, payés par la carte du client (6 points).
    La caisse débite les points article par article : deux transactions de 300
    centièmes de points.
    La vente est tenue dans la monnaie de points : `unite` = uuid de la monnaie. TVA 0
    partout (des points ne sont pas de l'argent), bien que le produit porte 20 %. Un
    règlement « non monétaire » (NM) par transaction, avec son montant et son uuid.
    / A pin and a medal at 3 points each, paid by card: two point transactions. The
    sale's unit is the points currency's uuid, VAT 0 everywhere, one NM payment per
    transaction.
    """
    monnaie_de_points = creer_une_monnaie_de_points(lieu)
    pins = creer_un_article_en_points("pins", "3.00", monnaie_de_points)
    medaille = creer_un_article_en_points("medaille", "3.00", monnaie_de_points)
    point_de_vente = creer_un_point_de_vente([pins.produit, medaille.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=0)
    ajouter_un_solde_sur_la_carte(carte_du_client, monnaie_de_points, 600)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(pins)}": "1",
        f"repid-{cle_de_panier(medaille)}": "1",
    }

    reponse = payer_par_la_carte_du_client(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        carte_du_client,
        cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.unite == str(monnaie_de_points.uuid)
    assert vente.total_ttc == 600
    assert vente.total_tva == 0
    for article in vente.articles.all():
        assert article.vat == Decimal("0")
        assert article.total_tva == 0

    transactions_creees = transactions_de_vente_de_la_carte(carte_du_client)
    assert len(transactions_creees) == 2
    reglements_attendus = []
    for transaction_de_vente in transactions_creees:
        reglements_attendus.append(
            (
                PaymentMethod.NON_MONETAIRE,
                transaction_de_vente.amount,
                transaction_de_vente.uuid,
            )
        )
    assert reglements_en_detail(vente) == sorted(reglements_attendus, key=str)
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 15, 16 — Monnaie du réseau (serveur Fedow distant, simulé)
# / 15, 16 — Network currency (remote Fedow server, faked)
# --------------------------------------------------------------------------


def creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu):
    """
    ÉTAT DE DÉPART : la carte NFC d'un membre (carte liée à un utilisateur), sans
    aucun solde dans les monnaies du lieu. Seule une carte liée à un utilisateur peut
    payer avec la monnaie du réseau (`_payer_par_nfc` lit son solde sur Fedow).
    Le lien est posé par `update()` : aucun signal.
    / STARTING STATE: a member's card (linked to a user), with no local balance. Only a
    linked card can pay with the network currency. Linked by update(): no signal.
    """
    membre = creer_utilisateur(prenom="Membre", nom="Reseau")
    carte = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=0)
    CarteCashless.objects.filter(pk=carte.pk).update(user=membre)
    carte.refresh_from_db()
    return carte


def transaction_du_reseau(categorie, montant_en_centimes):
    """
    Une transaction telle que le serveur Fedow distant la rend après un débit : son
    uuid, la monnaie débitée, le montant, et la fiche de la monnaie (catégorie « FED »
    pour la monnaie fédérée, « TLF » pour la monnaie locale d'un autre lieu).
    / A transaction as the remote Fedow server returns it after a debit.
    """
    return {
        "uuid": str(uuid.uuid4()),
        "asset": str(uuid.uuid4()),
        "amount": montant_en_centimes,
        "serialized_asset": {"category": categorie},
    }


def fedow_du_reseau_simule(transactions_rendues):
    """
    Le client du serveur Fedow distant (`FedowAPI`), simulé : son débit rend les
    transactions données. Aucun appel réseau.
    / The remote Fedow client, faked: its debit returns the given transactions.
    """
    faux_fedow = MagicMock()
    faux_fedow.transaction.to_place_from_qrcode.return_value = transactions_rendues
    return faux_fedow


def test_legacy_un_reglement_par_transaction_legacy(lieu):
    """
    Une bière à 5,00 € et un jus à 3,50 € (8,50 €), payés par la carte d'un membre qui
    n'a rien dans les monnaies du lieu : tout est payé avec la monnaie du réseau. Le
    serveur Fedow débite 3,00 € de monnaie locale d'un autre lieu (TLF) et 5,50 € de
    monnaie fédérée (FED) : deux transactions distantes.
    La vente a UN règlement par transaction distante (pas un par part d'article) :
    monnaie locale (LE) 300 et monnaie fédérée (SF) 550. Chaque règlement porte l'uuid
    de SA transaction dans `reference_externe` (elle vit sur le serveur distant), la
    monnaie débitée dans `asset`, et pas de `fedow_transaction_uuid` (réservé aux
    transactions locales).
    / 8.50 € paid by the network currency: two remote transactions (TLF 300, FED 550).
    One payment per remote transaction, with its uuid in `reference_externe`.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit, jus.produit])
    carte_du_membre = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(jus)}": "1",
    }
    transaction_en_monnaie_locale = transaction_du_reseau("TLF", 300)
    transaction_en_monnaie_federee = transaction_du_reseau("FED", 550)
    faux_fedow = fedow_du_reseau_simule(
        [transaction_en_monnaie_locale, transaction_en_monnaie_federee]
    )

    with patch("laboutik.views.lire_depensable_fed_frais", return_value=(850, True)):
        with patch("laboutik.views.FedowAPI", return_value=faux_fedow):
            reponse = payer_par_la_carte_du_client(
                client_du_caissier,
                point_de_vente,
                champs_du_panier,
                carte_du_membre,
                cle_d_idempotence,
            )

    assert reponse.status_code == 200
    assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)

    reglements_lus = []
    for reglement in vente.reglements.all():
        reglements_lus.append(
            (
                reglement.moyen,
                reglement.montant,
                reglement.reference_externe,
                str(reglement.asset),
                reglement.fedow_transaction_uuid,
            )
        )
    assert sorted(reglements_lus, key=str) == sorted(
        [
            (
                PaymentMethod.LOCAL_EURO,
                300,
                transaction_en_monnaie_locale["uuid"],
                transaction_en_monnaie_locale["asset"],
                None,
            ),
            (
                PaymentMethod.STRIPE_FED,
                550,
                transaction_en_monnaie_federee["uuid"],
                transaction_en_monnaie_federee["asset"],
                None,
            ),
        ],
        key=str,
    )
    verifier_egalites(vente)


def test_egalite_rompue_apres_debit_legacy_journalisee(lieu, caplog):
    """
    Même panier que le test précédent (8,50 €, tout en monnaie du réseau). Le débit du
    réseau est fait (hors de la transaction de base : il ne s'annule pas), puis la
    vente ne peut pas être encaissée : ses égalités sont rompues
    (`EgaliteDeVenteRompue`, simulée à l'encaissement).
    La caisse journalise un INCIDENT (le montant débité sur le réseau, la carte, l'uuid
    de chaque transaction du réseau) pour une régularisation à la main, et rend son
    écran d'erreur (jamais une erreur 500). Rien n'est écrit : ni vente, ni ligne.
    / Same cart, the network debit is done, then the sale cannot be settled (broken
    equality, faked). The register logs an INCIDENT (amount, card, network transaction
    uuids), shows its error screen (never a 500), and writes nothing.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit, jus.produit])
    carte_du_membre = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(jus)}": "1",
    }
    transaction_en_monnaie_locale = transaction_du_reseau("TLF", 300)
    transaction_en_monnaie_federee = transaction_du_reseau("FED", 550)
    faux_fedow = fedow_du_reseau_simule(
        [transaction_en_monnaie_locale, transaction_en_monnaie_federee]
    )
    egalite_rompue = EgaliteDeVenteRompue(
        "Égalité simulée par le test : règlements 850, articles 851."
    )

    with caplog.at_level(logging.ERROR, logger="laboutik.views"):
        with patch("laboutik.views.lire_depensable_fed_frais", return_value=(850, True)):
            with patch("laboutik.views.FedowAPI", return_value=faux_fedow):
                with patch("laboutik.views.encaisser_vente", side_effect=egalite_rompue):
                    reponse = payer_par_la_carte_du_client(
                        client_du_caissier,
                        point_de_vente,
                        champs_du_panier,
                        carte_du_membre,
                        cle_d_idempotence,
                    )

    # Le débit du réseau a bien eu lieu : c'est ce qui rend l'incident nécessaire.
    # / The network debit did happen: that is why the incident is needed.
    assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1

    # L'écran d'erreur de la caisse, pas une erreur du serveur, pas un succès.
    # / The register's error screen: not a server error, not a success.
    assert reponse.status_code < 500
    contenu_de_la_reponse = reponse.content.decode()
    assert 'data-testid="alerte-messages"' in contenu_de_la_reponse
    assert 'data-testid="paiement-succes"' not in contenu_de_la_reponse

    # L'incident est journalisé, avec le montant débité sur le réseau et la carte.
    # / The incident is logged with the network amount and the card.
    messages_d_incident = []
    for enregistrement in caplog.records:
        message_journalise = enregistrement.getMessage()
        est_une_erreur = enregistrement.levelno >= logging.ERROR
        if est_une_erreur and "INCIDENT" in message_journalise:
            messages_d_incident.append(message_journalise)
    assert len(messages_d_incident) == 1, (
        f"Attendu : un incident journalisé, trouvé : {messages_d_incident}"
    )
    assert "850" in messages_d_incident[0]
    assert carte_du_membre.tag_id in messages_d_incident[0]
    # Les uuid des transactions du réseau : sans eux, personne ne peut retrouver ni
    # régulariser à la main l'argent débité sur le serveur distant.
    # / The network transaction uuids: needed to find and fix the debited money by hand.
    assert transaction_en_monnaie_locale["uuid"] in messages_d_incident[0]
    assert transaction_en_monnaie_federee["uuid"] in messages_d_incident[0]

    # Rien n'est écrit.
    # / Nothing is written.
    assert not Vente.objects.filter(idempotency_key=cle_d_idempotence).exists()
    assert not LigneArticle.objects.filter(pricesold__price=biere.tarif).exists()
    assert not LigneArticle.objects.filter(pricesold__price=jus.tarif).exists()


def test_exception_imprevue_apres_debit_legacy_journalisee(lieu, caplog):
    """
    Même panier que le test précédent (8,50 €, tout en monnaie du réseau). Le débit du
    réseau est fait (hors de la transaction de base : il ne s'annule pas), puis une
    erreur imprévue survient pendant l'écriture de la vente (simulée à l'encaissement
    par une `RuntimeError`).
    La caisse journalise UN INCIDENT (le montant débité sur le réseau, la carte, l'uuid
    de chaque transaction du réseau) pour une régularisation à la main, puis relaie
    l'erreur (erreur 500 volontaire). Le client de test Django relaie l'exception de la
    vue : le test l'attend avec `pytest.raises`. Rien n'est écrit : ni vente, ni ligne.
    / Same cart, the network debit is done, then an unexpected error happens while
    writing the sale. One INCIDENT (amount, card, network transaction uuids), then the
    error is re-raised (the test client re-raises it). Nothing written.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit, jus.produit])
    carte_du_membre = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(jus)}": "1",
    }
    transaction_en_monnaie_locale = transaction_du_reseau("TLF", 300)
    transaction_en_monnaie_federee = transaction_du_reseau("FED", 550)
    faux_fedow = fedow_du_reseau_simule(
        [transaction_en_monnaie_locale, transaction_en_monnaie_federee]
    )
    erreur_imprevue = RuntimeError("Erreur imprévue simulée par le test.")

    with caplog.at_level(logging.ERROR, logger="laboutik.views"):
        with patch("laboutik.views.lire_depensable_fed_frais", return_value=(850, True)):
            with patch("laboutik.views.FedowAPI", return_value=faux_fedow):
                with patch("laboutik.views.encaisser_vente", side_effect=erreur_imprevue):
                    with pytest.raises(RuntimeError):
                        payer_par_la_carte_du_client(
                            client_du_caissier,
                            point_de_vente,
                            champs_du_panier,
                            carte_du_membre,
                            cle_d_idempotence,
                        )

    # Le débit du réseau a bien eu lieu : c'est ce qui rend l'incident nécessaire.
    # / The network debit did happen: that is why the incident is needed.
    assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1

    # L'incident est journalisé, avec le montant débité sur le réseau, la carte et
    # l'uuid de chaque transaction du réseau.
    # / The incident is logged with the network amount, the card and every uuid.
    messages_d_incident = []
    for enregistrement in caplog.records:
        message_journalise = enregistrement.getMessage()
        est_une_erreur = enregistrement.levelno >= logging.ERROR
        if est_une_erreur and "INCIDENT" in message_journalise:
            messages_d_incident.append(message_journalise)
    assert len(messages_d_incident) == 1, (
        f"Attendu : un incident journalisé, trouvé : {messages_d_incident}"
    )
    assert re.search(r"\b850\b", messages_d_incident[0])
    assert carte_du_membre.tag_id in messages_d_incident[0]
    assert transaction_en_monnaie_locale["uuid"] in messages_d_incident[0]
    assert transaction_en_monnaie_federee["uuid"] in messages_d_incident[0]

    # Rien n'est écrit.
    # / Nothing is written.
    assert not Vente.objects.filter(idempotency_key=cle_d_idempotence).exists()
    assert not LigneArticle.objects.filter(pricesold__price=biere.tarif).exists()
    assert not LigneArticle.objects.filter(pricesold__price=jus.tarif).exists()


# --------------------------------------------------------------------------
# 17c — Le HT de la vente par la cascade : 111 centimes à 20 % → 93
# / 17c — The sale HT through the cascade: 111 cents at 20 % → 93
# --------------------------------------------------------------------------


def test_ht_111_centimes_vaut_93_par_la_cascade(lieu):
    """
    Un article à 1,11 € (TVA 20 %) payé par la carte du client, en monnaie locale
    seulement. 111 × 100 / 120 = 92,5 : l'arrondi « demi vers le haut » du service
    donne 93 (TVA 18). La boucle d'empreinte (HMAC) de la cascade tourne toujours sur
    la ligne, sans recalculer le HT au pair (92). La vente a HT 93, TVA 18.
    / A 1.11 € item (20 % VAT) paid by card in local currency: sale HT 93, VAT 18. The
    cascade HMAC loop still chains the line without recomputing HT.
    """
    article_a_111 = creer_un_article_de_caisse(
        "article a 1,11", prix_en_euros="1.11", taux_tva="20.00"
    )
    point_de_vente = creer_un_point_de_vente([article_a_111.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=200)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_par_la_carte_du_client(
        client_du_caissier,
        point_de_vente,
        {f"repid-{cle_de_panier(article_a_111)}": "1"},
        carte_du_client,
        cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.total_ttc == 111
    assert vente.total_ht == 93
    assert vente.total_tva == 18
    for article in vente.articles.all():
        assert article.hmac_hash != "", "La boucle HMAC n'a pas chaîné la ligne."
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 17d — Vente au poids par la cascade : le coût porte sur le poids réel
# / 17d — Weighed sale through the cascade: the cost is on the real weight
# --------------------------------------------------------------------------


def test_vente_au_poids_par_la_cascade_cout_sur_le_poids_reel(lieu):
    """
    350 g de fromage à 20,00 €/kg (prix d'achat 8,00 €/kg), payés par la carte du
    client en monnaie locale seulement. La ligne garde `qty = 1` et le poids (350 g)
    dans `weight_quantity`. Prix : 7,00 €. Le coût d'achat porte sur le poids réel :
    0,350 kg × 800 = 280 centimes (et non 800, le coût d'un kilo).
    / 350 g of cheese at 20.00 €/kg (bought 8.00 €/kg), paid by card: purchase cost on
    the real weight, 280.
    """
    fromage = creer_un_article_de_caisse(
        "fromage au poids",
        prix_en_euros="20.00",
        taux_tva="5.50",
        prix_achat_en_centimes=800,
        vendu_au_poids=True,
    )
    point_de_vente = creer_un_point_de_vente([fromage.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=1000)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    cle_de_la_ligne = cle_de_panier(fromage, numero_de_ligne=1)
    champs_du_panier = {
        f"repid-{cle_de_la_ligne}": "1",
        f"weight-{cle_de_la_ligne}": "350",
        f"custom-{cle_de_la_ligne}": "700",
    }

    reponse = payer_par_la_carte_du_client(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        carte_du_client,
        cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    article = seul_article_de_la_vente(vente)
    assert article.amount == 700
    assert article.qty == 1
    assert article.weight_quantity == 350
    assert article.total_catalogue == 700
    assert article.cout_achat == 280
    assert reglements_de_la_vente(vente) == [(PaymentMethod.LOCAL_EURO, 700)]
    verifier_egalites(vente)


def test_vente_au_poids_payee_avec_deux_monnaies_cout_sur_le_poids_reel(lieu):
    """
    350 g de fromage à 20,00 €/kg (prix d'achat 8,00 €/kg), soit 7,00 €, payés par la
    carte du client : 4,20 € de jetons cadeau (60 %) puis 2,80 € de monnaie locale
    (40 %). L'article est coupé en deux parts. Chaque part porte le coût de SA fraction
    du poids réel : 0,350 kg × 60 % × 800 = 168 et 0,350 kg × 40 % × 800 = 112. La
    somme des coûts des parts vaut le coût réel du fromage vendu : 280 (et non 800 par
    part, ni 480 pour la part à 60 %).
    / 350 g of cheese (7.00 €) paid 60 % in gift tokens and 40 % in local currency: two
    parts, each costing its share of the real weight; the parts' costs add up to 280.
    """
    fromage = creer_un_article_de_caisse(
        "fromage au poids",
        prix_en_euros="20.00",
        taux_tva="5.50",
        prix_achat_en_centimes=800,
        vendu_au_poids=True,
    )
    point_de_vente = creer_un_point_de_vente([fromage.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=280)
    ajouter_un_solde_sur_la_carte(carte_du_client, monnaie_cadeau_du_lieu(lieu), 420)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    cle_de_la_ligne = cle_de_panier(fromage, numero_de_ligne=1)
    champs_du_panier = {
        f"repid-{cle_de_la_ligne}": "1",
        f"weight-{cle_de_la_ligne}": "350",
        f"custom-{cle_de_la_ligne}": "700",
    }

    reponse = payer_par_la_carte_du_client(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        carte_du_client,
        cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    parts_du_fromage = list(vente.articles.all())
    assert len(parts_du_fromage) == 2
    somme_des_couts_des_parts = 0
    for part in parts_du_fromage:
        assert part.weight_quantity == 350
        assert part.cout_achat is not None
        somme_des_couts_des_parts += part.cout_achat
    assert somme_des_couts_des_parts == 280
    assert vente.total_catalogue == 700
    assert reglements_de_la_vente(vente) == [
        (PaymentMethod.LOCAL_EURO, 280),
        (PaymentMethod.LOCAL_GIFT, 420),
    ]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 22b — Double appui sur « Valider » en NFC : une vente, un seul débit
# / 22b — Double tap on "Validate" with NFC: one sale, one debit
# --------------------------------------------------------------------------


def test_rejeu_nfc_meme_cle_une_seule_vente(lieu):
    """
    Le client pose sa carte pour une bière à 5,00 € ; le même paiement part deux fois
    avec la MÊME clé d'idempotence. Les deux réponses sont des succès, mais une seule
    vente existe pour cette clé, la carte n'est débitée qu'une fois (une transaction,
    solde 10,00 € → 5,00 €).
    / The same NFC payment posted twice with the SAME key: one sale, one debit only.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=1000)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {f"repid-{cle_de_panier(biere)}": "1"}

    premiere_reponse = payer_par_la_carte_du_client(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        carte_du_client,
        cle_d_idempotence,
    )
    deuxieme_reponse = payer_par_la_carte_du_client(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        carte_du_client,
        cle_d_idempotence,
    )

    assert premiere_reponse.status_code == 200
    assert deuxieme_reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert len(transactions_de_vente_de_la_carte(carte_du_client)) == 1
    assert solde_de_la_carte(carte_du_client, monnaie_locale_du_lieu(lieu)) == 500
    assert reglements_de_la_vente(vente) == [(PaymentMethod.LOCAL_EURO, 500)]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# Recharge cadeau seule, postée sur la route de paiement NFC
# / Gift top-up alone, posted on the NFC payment route
# --------------------------------------------------------------------------


def test_recharge_cadeau_seule_par_la_route_nfc_meme_vente_avec_identifiant(lieu):
    """
    Une recharge cadeau de 10,00 € SEULE, postée sur la route de paiement avec le
    moyen « nfc ». L'écran ne propose pas ce chemin (la carte identifiée suffit,
    `identifier_client`), mais une requête peut l'emprunter : le paiement NFC crédite
    alors la recharge cadeau lui-même.
    La recharge est un article de la vente du paiement (retrouvée par la clé), hors
    chiffre d'affaires, entièrement offert (source OFFRIR, net 0), avec l'identifiant
    du paiement sur sa ligne. Un seul règlement « offert » (FREE) de 10,00 €, aucun
    règlement d'argent.
    / A gift top-up ALONE posted on the NFC route: an item of the payment's sale,
    fully offered, with the payment id on its line; one FREE payment of 1000.
    """
    recharge_cadeau = creer_un_article_de_caisse(
        "recharge cadeau",
        prix_en_euros="10.00",
        taux_tva="20.00",
        methode_caisse=Product.RECHARGE_CADEAU,
        asset=monnaie_cadeau_du_lieu(lieu),
    )
    point_de_vente = creer_un_point_de_vente([recharge_cadeau.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=0)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_par_la_carte_du_client(
        client_du_caissier,
        point_de_vente,
        {f"repid-{cle_de_panier(recharge_cadeau)}": "1"},
        carte_du_client,
        cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.statut == Vente.Statut.REGLEE
    article = seul_article_de_la_vente(vente)
    assert article.pricesold.price_id == recharge_cadeau.tarif.pk
    assert article.hors_chiffre_affaires is True
    assert article.total_catalogue == 1000
    assert article.part_offerte == 1000
    assert article.source_offert == LigneArticle.SourceOffert.OFFRIR
    assert article.total_ttc == 0
    assert str(article.uuid_transaction) == cle_d_idempotence
    assert reglements_de_la_vente(vente) == [(PaymentMethod.FREE, 1000)]
    verifier_egalites(vente)


# ==========================================================================
# LA CARTE NE SUFFIT PAS : LE RESTE EN ESPÈCES OU EN CB (paiement complémentaire)
# / THE CARD IS NOT ENOUGH: THE REST IN CASH OR BY CARD (complementary payment)
# ==========================================================================
#
# Le client pose sa carte, mais son solde ne couvre pas le panier. L'écran « reste à
# payer » propose alors les espèces ou la CB pour le reste. Le serveur refait la cascade
# de la carte (il ne se fie pas à ce que l'écran lui renvoie), débite la carte, et
# règle le reste avec le moyen choisi. Si la carte est celle d'un membre, la monnaie du
# réseau (serveur Fedow distant, simulé) peut payer une partie du reste avant les
# espèces ou la CB.
# Une seule vente pour tout le paiement : un règlement par débit de la carte, un par
# transaction du réseau, et UN règlement espèces ou CB du reste dû.
# / The card does not cover the cart: the rest is paid in cash or by bank card. One sale:
# one payment per card debit, one per network transaction, ONE cash/CB payment of the
# amount due.

# Adresse du paiement complémentaire (laboutik/urls.py).
# / Complementary payment address.
URL_DU_PAIEMENT_COMPLEMENTAIRE = "/laboutik/paiement/payer_complementaire/"


def payer_le_reste_en_especes_ou_en_cb(
    client_du_caissier,
    point_de_vente,
    champs_du_panier,
    carte,
    moyen_du_reste,
    cle_d_idempotence,
    somme_donnee_en_centimes="",
):
    """
    Le caissier règle le reste du panier que la carte ne couvre pas : la vraie route du
    paiement complémentaire, comme l'écran « reste à payer » l'envoie.
    / The cashier pays what the card does not cover, through the real route.

    `moyen_du_reste` : "espece" ou "carte_bancaire".
    `somme_donnee_en_centimes` : ce que le client tend en espèces, en centimes, comme
    le pavé des espèces l'envoie ; vide = compte juste.
    Le serveur refait lui-même la cascade de la carte : l'écran n'a pas besoin de lui
    renvoyer le détail de la cascade. La clé d'idempotence est celle du paiement.
    / Empty given sum = exact amount. The server recomputes the card cascade itself.
    """
    donnees_du_formulaire = {
        "uuid_pv": str(point_de_vente.uuid),
        "cle_idempotence_paiement": cle_d_idempotence,
        "tag_id_carte1": carte.tag_id,
        "moyen_complement": moyen_du_reste,
        "given_sum": somme_donnee_en_centimes,
    }
    donnees_du_formulaire.update(champs_du_panier)
    return client_du_caissier.post(
        URL_DU_PAIEMENT_COMPLEMENTAIRE, donnees_du_formulaire
    )


def reglements_complets_de_la_vente(vente):
    """
    Les règlements de la vente, relus en base, avec tout ce qui dit d'où vient
    l'argent : une liste triée de tuples (moyen, montant, monnaie, carte, portefeuille,
    uuid de la transaction fedow_core, référence externe).
    / The sale's payments with where the money comes from, as sorted tuples.
    """
    reglements_lus = []
    for reglement in vente.reglements.all():
        monnaie_du_reglement = None
        if reglement.asset is not None:
            monnaie_du_reglement = str(reglement.asset)
        reglements_lus.append(
            (
                reglement.moyen,
                reglement.montant,
                monnaie_du_reglement,
                reglement.carte_id,
                reglement.wallet_id,
                reglement.fedow_transaction_uuid,
                reglement.reference_externe,
            )
        )
    return sorted(reglements_lus, key=str)


# --------------------------------------------------------------------------
# 9 — L'exemple fil rouge : trois jus, 5,00 € sur la carte, 5,50 € en CB
# / 9 — The running example: three juices, 5.00 € on the card, 5.50 € by bank card
# --------------------------------------------------------------------------


def test_nfc_trois_jus_500_le_550_cb_parts_entieres(lieu):
    """
    Trois jus à 3,50 € (TVA 20 %, 10,50 €). La carte du client porte 5,00 € de monnaie
    locale : elle paie 5,00 €, le reste (5,50 €) est réglé en CB.
    L'article est coupé en deux parts, une par moyen, qui gardent leurs champs
    d'aujourd'hui (prix unitaire 350, quantité partielle, la carte, l'identifiant du
    paiement) et portent chacune l'argent réel de la part : catalogue 500 et 550.
    Une vente de la caisse, réglée, numérotée : catalogue 1050, net 1050, HT 875,
    TVA 175. Deux règlements : monnaie locale 500, copié de la transaction de la carte
    (son uuid, la monnaie, la carte, le portefeuille), et CB 550.
    / Three 3.50 € juices: 5.00 € in local currency on the card, 5.50 € by bank card.
    Two whole parts (500 / 550); one settled sale 1050 / 875 / 175; payments LE 500
    (copied from the card transaction) and CB 550.
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([jus.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500)
    # L'administrateur est créé ici : le test compare l'opérateur de la vente à lui.
    # / Created here: the test compares the sale operator to this user.
    administrateur_du_lieu = creer_utilisateur(prenom="Admin", nom="Lieu")
    administrateur_du_lieu.client_admin.add(lieu.tenant)
    client_du_caissier = client_connecte(administrateur_du_lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_le_reste_en_especes_ou_en_cb(
        client_du_caissier,
        point_de_vente,
        {f"repid-{cle_de_panier(jus)}": "3"},
        carte_du_client,
        moyen_du_reste="carte_bancaire",
        cle_d_idempotence=cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.nature == Vente.Nature.VENTE
    assert vente.statut == Vente.Statut.REGLEE
    assert vente.numero is not None
    assert vente.origine == SaleOrigin.LABOUTIK
    assert vente.point_de_vente_id == point_de_vente.pk
    assert vente.operateur_id == administrateur_du_lieu.pk
    assert vente.carte_id == carte_du_client.pk
    assert vente.total_catalogue == 1050
    assert vente.total_offert == 0
    assert vente.total_ttc == 1050
    assert vente.total_ht == 875
    assert vente.total_tva == 175

    # Deux parts, une par moyen, avec l'argent réel de chaque part.
    # / Two parts, one per method, each with its real money.
    articles_par_moyen = articles_de_la_vente_par_moyen(vente)
    assert sorted(articles_par_moyen.keys()) == [
        PaymentMethod.CC,
        PaymentMethod.LOCAL_EURO,
    ]
    assert len(articles_par_moyen[PaymentMethod.LOCAL_EURO]) == 1
    assert len(articles_par_moyen[PaymentMethod.CC]) == 1
    part_en_monnaie_locale = articles_par_moyen[PaymentMethod.LOCAL_EURO][0]
    part_en_cb = articles_par_moyen[PaymentMethod.CC][0]
    assert part_en_monnaie_locale.total_catalogue == 500
    assert part_en_monnaie_locale.total_ttc == 500
    assert part_en_cb.total_catalogue == 550
    assert part_en_cb.total_ttc == 550

    # Les deux parts gardent leurs champs historiques (tronc §5).
    # / Both parts keep their historical fields.
    assert part_en_monnaie_locale.qty == Decimal("1.428571")
    assert part_en_cb.qty == Decimal("1.571429")
    for part in (part_en_monnaie_locale, part_en_cb):
        assert part.amount == 350
        assert part.carte_id == carte_du_client.pk
        assert str(part.uuid_transaction) == cle_d_idempotence

    # Le règlement en monnaie locale est COPIÉ de la transaction de la carte.
    # / The local-currency payment is COPIED from the card transaction.
    transactions_creees = transactions_de_vente_de_la_carte(carte_du_client)
    assert len(transactions_creees) == 1
    transaction_de_la_carte = transactions_creees[0]
    assert transaction_de_la_carte.amount == 500
    monnaie_locale = monnaie_locale_du_lieu(lieu)
    assert reglements_complets_de_la_vente(vente) == sorted(
        [
            (PaymentMethod.CC, 550, None, None, None, None, ""),
            (
                PaymentMethod.LOCAL_EURO,
                500,
                str(monnaie_locale.uuid),
                carte_du_client.pk,
                carte_du_client.wallet_ephemere_id,
                transaction_de_la_carte.uuid,
                "",
            ),
        ],
        key=str,
    )
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 12 — Jetons bénévoles + CB : la part en jetons est une vente hors TVA
# / 12 — Volunteer tokens + bank card: the token part is a sale outside VAT
# --------------------------------------------------------------------------


def test_jetons_benevoles_puis_cb_part_en_jetons_vendue_hors_tva(lieu):
    """
    Une bière à 5,00 € (TVA 20 %). La carte du client porte 3,00 € de jetons cadeau
    (bénévoles) et rien d'autre : les jetons paient 3,00 €, le reste (2,00 €) est réglé
    en CB.
    Un jeton dépensé solde la dette du lieu (D8 bis) :
    - part jetons : catalogue 300, rien d'offert, net 300, TVA 0 ;
    - part CB : net 200, TVA 20 %.
    Vente : offert 0, net 500, HT 467 (300 + 167), TVA 33 (la TVA ne porte que sur la
    part en argent). Deux règlements : « jetons » (LG) 300 et CB 200.
    / A 5.00 € beer: 3.00 € of gift tokens + 2.00 € by bank card. The token part is an
    ordinary sale at 0 % VAT (net 300); the card part net 200. Sale: net 500, HT 467,
    VAT 33. Payments LG 300 + CB 200.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=0)
    monnaie_cadeau = monnaie_cadeau_du_lieu(lieu)
    ajouter_un_solde_sur_la_carte(carte_du_client, monnaie_cadeau, 300)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_le_reste_en_especes_ou_en_cb(
        client_du_caissier,
        point_de_vente,
        {f"repid-{cle_de_panier(biere)}": "1"},
        carte_du_client,
        moyen_du_reste="carte_bancaire",
        cle_d_idempotence=cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    articles_par_moyen = articles_de_la_vente_par_moyen(vente)
    assert sorted(articles_par_moyen.keys()) == [
        PaymentMethod.CC,
        PaymentMethod.LOCAL_GIFT,
    ]
    assert len(articles_par_moyen[PaymentMethod.LOCAL_GIFT]) == 1
    assert len(articles_par_moyen[PaymentMethod.CC]) == 1

    part_en_jetons = articles_par_moyen[PaymentMethod.LOCAL_GIFT][0]
    assert part_en_jetons.total_catalogue == 300
    assert part_en_jetons.part_offerte == 0
    assert part_en_jetons.source_offert == ""
    assert part_en_jetons.total_ttc == 300

    part_en_cb = articles_par_moyen[PaymentMethod.CC][0]
    assert part_en_cb.part_offerte == 0
    assert part_en_cb.total_ttc == 200

    assert vente.total_catalogue == 500
    assert vente.total_offert == 0
    assert vente.total_ttc == 500
    assert vente.total_ht == 467
    assert vente.total_tva == 33
    assert reglements_de_la_vente(vente) == [
        (PaymentMethod.CC, 200),
        (PaymentMethod.LOCAL_GIFT, 300),
    ]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 12b — Espèces : le règlement est le reste dû, pas la somme donnée
# / 12b — Cash: the payment is the amount due, not the amount handed over
# --------------------------------------------------------------------------


def test_complement_especes_reglement_egal_au_reste_du_pas_a_la_somme_donnee(lieu):
    """
    Trois jus à 3,50 € (10,50 €), 5,00 € sur la carte du client : il reste 5,50 € à
    payer en espèces. Le client tend un billet de 10,00 €, la caisse rend 4,50 €.
    La monnaie rendue n'est pas un règlement : le règlement espèces vaut le reste dû,
    5,50 €, jamais la somme donnée.
    / 5.50 € left to pay in cash, the customer hands over 10.00 €: the cash payment is
    the amount due (550), never the amount handed over.
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([jus.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_le_reste_en_especes_ou_en_cb(
        client_du_caissier,
        point_de_vente,
        {f"repid-{cle_de_panier(jus)}": "3"},
        carte_du_client,
        moyen_du_reste="espece",
        cle_d_idempotence=cle_d_idempotence,
        somme_donnee_en_centimes="1000",
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert reglements_de_la_vente(vente) == [
        (PaymentMethod.CASH, 550),
        (PaymentMethod.LOCAL_EURO, 500),
    ]
    assert vente.total_ttc == 1050
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 15b — Le réseau paie une partie du reste, les espèces le solde
# / 15b — The network pays part of the rest, cash pays the balance
# --------------------------------------------------------------------------


def test_complement_legacy_partiel_un_reglement_par_transaction_legacy(lieu):
    """
    Une bière à 5,00 € et un jus à 3,50 € (8,50 €), payés avec la carte d'un membre qui
    n'a rien dans les monnaies du lieu. Le réseau ne peut payer que 7,00 € : le serveur
    Fedow débite 2,00 € de monnaie locale d'un autre lieu (TLF) et 5,00 € de monnaie
    fédérée (FED), deux transactions distantes. Le reste, 1,50 €, est réglé en espèces.
    La transaction FED couvre DEUX parts d'articles (3,00 € de la bière, 2,00 € du jus).
    La vente a UN règlement par transaction distante (pas un par part d'article) :
    monnaie locale (LE) 200 et monnaie fédérée (SF) 500, chacun avec l'uuid de SA
    transaction dans `reference_externe`, sa monnaie, la carte, et pas de
    `fedow_transaction_uuid` (réservé aux transactions locales). Plus UN règlement
    espèces du reste dû, 150. Le client de la vente est le membre.
    / 8.50 €: the network pays 7.00 € (TLF 200 + FED 500, two remote transactions; the
    FED one covers two item parts), cash pays 1.50 €. One payment per remote transaction
    (uuid in `reference_externe`), plus one cash payment of 150. The sale's customer is
    the member.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit, jus.produit])
    carte_du_membre = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(jus)}": "1",
    }
    transaction_en_monnaie_locale = transaction_du_reseau("TLF", 200)
    transaction_en_monnaie_federee = transaction_du_reseau("FED", 500)
    faux_fedow = fedow_du_reseau_simule(
        [transaction_en_monnaie_locale, transaction_en_monnaie_federee]
    )

    with patch("laboutik.views.lire_depensable_fed_frais", return_value=(700, True)):
        with patch("laboutik.views.FedowAPI", return_value=faux_fedow):
            reponse = payer_le_reste_en_especes_ou_en_cb(
                client_du_caissier,
                point_de_vente,
                champs_du_panier,
                carte_du_membre,
                moyen_du_reste="espece",
                cle_d_idempotence=cle_d_idempotence,
            )

    assert reponse.status_code == 200
    # Un seul débit du réseau, de ce qu'il peut payer.
    # / One network debit, of what it can pay.
    assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1
    arguments_du_debit = faux_fedow.transaction.to_place_from_qrcode.call_args.kwargs
    assert arguments_du_debit["amount"] == 700

    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.client_id == carte_du_membre.user_id
    assert vente.carte_id == carte_du_membre.pk
    assert vente.total_ttc == 850

    # La transaction FED couvre deux parts : un règlement par part en ferait deux.
    # / The FED transaction covers two parts: one payment per part would make two.
    parts_payees_en_monnaie_federee = vente.articles.filter(
        payment_method=PaymentMethod.STRIPE_FED
    )
    assert parts_payees_en_monnaie_federee.count() == 2

    reglements_lus = []
    for reglement in vente.reglements.all():
        monnaie_du_reglement = None
        if reglement.asset is not None:
            monnaie_du_reglement = str(reglement.asset)
        reglements_lus.append(
            (
                reglement.moyen,
                reglement.montant,
                reglement.reference_externe,
                monnaie_du_reglement,
                reglement.fedow_transaction_uuid,
            )
        )
    assert sorted(reglements_lus, key=str) == sorted(
        [
            (
                PaymentMethod.LOCAL_EURO,
                200,
                transaction_en_monnaie_locale["uuid"],
                transaction_en_monnaie_locale["asset"],
                None,
            ),
            (
                PaymentMethod.STRIPE_FED,
                500,
                transaction_en_monnaie_federee["uuid"],
                transaction_en_monnaie_federee["asset"],
                None,
            ),
            (PaymentMethod.CASH, 150, "", None, None),
        ],
        key=str,
    )
    for reglement in vente.reglements.all():
        if reglement.moyen != PaymentMethod.CASH:
            assert reglement.carte_id == carte_du_membre.pk
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 15c — Le réseau paie tout le reste : aucun règlement espèces
# / 15c — The network pays the whole rest: no cash payment
# --------------------------------------------------------------------------


def test_complement_reseau_paie_tout_le_reste_aucun_reglement_especes(lieu):
    """
    Une bière à 5,00 € et un jus à 3,50 € (8,50 €), payés avec la carte d'un membre qui
    porte 3,00 € de monnaie locale du lieu. L'écran « reste à payer » a proposé les
    espèces pour 5,50 €. Mais au moment du complément, le solde du réseau relu à neuf
    couvre tout ce reste (il a grandi depuis l'écran NFC) : le serveur Fedow débite
    1,50 € de monnaie locale d'un autre lieu (TLF) et 4,00 € de monnaie fédérée (FED).
    Il ne reste rien à payer en espèces : la vente n'a AUCUN règlement espèces (ni de
    montant 0). Ses règlements : la transaction de la carte (LE 300, son uuid dans
    `fedow_transaction_uuid`), et une par transaction du réseau (LE 150, SF 400, leur
    uuid dans `reference_externe`).
    / 8.50 €: the card pays 3.00 €, the freshly read network balance covers the whole
    5.50 € rest. No cash payment at all (not even 0): one payment for the card
    transaction, one per network transaction.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit, jus.produit])
    carte_du_membre = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    # La carte du membre porte 3,00 € de monnaie locale du lieu.
    # / The member's card holds 3.00 € of the venue's local currency.
    monnaie_locale = monnaie_locale_du_lieu(lieu)
    Token.objects.filter(
        wallet=carte_du_membre.wallet_ephemere, asset=monnaie_locale
    ).update(value=300)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(jus)}": "1",
    }
    transaction_en_monnaie_locale = transaction_du_reseau("TLF", 150)
    transaction_en_monnaie_federee = transaction_du_reseau("FED", 400)
    faux_fedow = fedow_du_reseau_simule(
        [transaction_en_monnaie_locale, transaction_en_monnaie_federee]
    )

    # Le solde du réseau relu au complément (10,00 €) dépasse le reste dû (5,50 €).
    # / The network balance read at complement time exceeds the amount due.
    with patch("laboutik.views.lire_depensable_fed_frais", return_value=(1000, True)):
        with patch("laboutik.views.FedowAPI", return_value=faux_fedow):
            reponse = payer_le_reste_en_especes_ou_en_cb(
                client_du_caissier,
                point_de_vente,
                champs_du_panier,
                carte_du_membre,
                moyen_du_reste="espece",
                cle_d_idempotence=cle_d_idempotence,
            )

    assert reponse.status_code == 200
    # Le réseau débite tout le reste, et seulement le reste.
    # / The network debits the whole rest, and only the rest.
    assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1
    arguments_du_debit = faux_fedow.transaction.to_place_from_qrcode.call_args.kwargs
    assert arguments_du_debit["amount"] == 550

    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.statut == Vente.Statut.REGLEE
    assert vente.total_ttc == 850

    transactions_creees = transactions_de_vente_de_la_carte(carte_du_membre)
    assert len(transactions_creees) == 1
    transaction_de_la_carte = transactions_creees[0]
    assert transaction_de_la_carte.amount == 300

    reglements_lus = []
    for reglement in vente.reglements.all():
        reglements_lus.append(
            (
                reglement.moyen,
                reglement.montant,
                reglement.fedow_transaction_uuid,
                reglement.reference_externe,
            )
        )
    assert sorted(reglements_lus, key=str) == sorted(
        [
            (PaymentMethod.LOCAL_EURO, 300, transaction_de_la_carte.uuid, ""),
            (
                PaymentMethod.LOCAL_EURO,
                150,
                None,
                transaction_en_monnaie_locale["uuid"],
            ),
            (
                PaymentMethod.STRIPE_FED,
                400,
                None,
                transaction_en_monnaie_federee["uuid"],
            ),
        ],
        key=str,
    )
    # Aucun règlement espèces ni CB, et aucun règlement de 0.
    # / No cash or bank card payment, and no 0 payment.
    assert not vente.reglements.filter(
        moyen__in=[PaymentMethod.CASH, PaymentMethod.CC]
    ).exists()
    assert not vente.reglements.filter(montant=0).exists()
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 16b — Égalité rompue après le débit du réseau, sur le paiement complémentaire
# / 16b — Broken equality after the network debit, on the complementary payment
# --------------------------------------------------------------------------


def test_egalite_rompue_apres_debit_legacy_journalisee_complement(lieu, caplog):
    """
    Même panier que le test précédent (8,50 €) : le réseau débite 5,00 € (hors de la
    transaction de base : il ne s'annule pas), le reste est à payer en espèces. Puis la
    vente ne peut pas être encaissée : ses égalités sont rompues
    (`EgaliteDeVenteRompue`, simulée à l'encaissement).
    La caisse journalise un INCIDENT (le montant débité sur le réseau, la carte, l'uuid
    de chaque transaction du réseau) pour une régularisation à la main, et rend son
    écran d'erreur (jamais une erreur 500). Rien n'est écrit : ni vente, ni ligne.
    / Same cart: the network debits 5.00 €, then the sale cannot be settled (broken
    equality, faked). The register logs an INCIDENT (amount, card, network transaction
    uuids), shows its error screen (never a 500), and writes nothing.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit, jus.produit])
    carte_du_membre = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(jus)}": "1",
    }
    transaction_en_monnaie_locale = transaction_du_reseau("TLF", 200)
    transaction_en_monnaie_federee = transaction_du_reseau("FED", 300)
    faux_fedow = fedow_du_reseau_simule(
        [transaction_en_monnaie_locale, transaction_en_monnaie_federee]
    )
    egalite_rompue = EgaliteDeVenteRompue(
        "Égalité simulée par le test : règlements 850, articles 851."
    )

    with caplog.at_level(logging.ERROR, logger="laboutik.views"):
        with patch("laboutik.views.lire_depensable_fed_frais", return_value=(500, True)):
            with patch("laboutik.views.FedowAPI", return_value=faux_fedow):
                with patch("laboutik.views.encaisser_vente", side_effect=egalite_rompue):
                    reponse = payer_le_reste_en_especes_ou_en_cb(
                        client_du_caissier,
                        point_de_vente,
                        champs_du_panier,
                        carte_du_membre,
                        moyen_du_reste="espece",
                        cle_d_idempotence=cle_d_idempotence,
                    )

    # Le débit du réseau a bien eu lieu : c'est ce qui rend l'incident nécessaire.
    # / The network debit did happen: that is why the incident is needed.
    assert faux_fedow.transaction.to_place_from_qrcode.call_count == 1

    # L'écran d'erreur de la caisse, pas une erreur du serveur, pas un succès.
    # / The register's error screen: not a server error, not a success.
    assert reponse.status_code < 500
    contenu_de_la_reponse = reponse.content.decode()
    assert 'data-testid="alerte-messages"' in contenu_de_la_reponse
    assert 'data-testid="paiement-succes"' not in contenu_de_la_reponse

    # L'incident est journalisé une fois, avec le montant débité sur le réseau (500,
    # comme nombre entier : pas un morceau d'uuid), la carte et les uuid des
    # transactions du réseau.
    # / The incident is logged once, with the network amount, the card and the uuids.
    messages_d_incident = []
    for enregistrement in caplog.records:
        message_journalise = enregistrement.getMessage()
        est_une_erreur = enregistrement.levelno >= logging.ERROR
        if est_une_erreur and "INCIDENT" in message_journalise:
            messages_d_incident.append(message_journalise)
    assert len(messages_d_incident) == 1, (
        f"Attendu : un incident journalisé, trouvé : {messages_d_incident}"
    )
    assert re.search(r"\b500\b", messages_d_incident[0])
    assert carte_du_membre.tag_id in messages_d_incident[0]
    assert transaction_en_monnaie_locale["uuid"] in messages_d_incident[0]
    assert transaction_en_monnaie_federee["uuid"] in messages_d_incident[0]

    # Rien n'est écrit.
    # / Nothing is written.
    assert not Vente.objects.filter(idempotency_key=cle_d_idempotence).exists()
    assert not LigneArticle.objects.filter(pricesold__price=biere.tarif).exists()
    assert not LigneArticle.objects.filter(pricesold__price=jus.tarif).exists()


# --------------------------------------------------------------------------
# 22c — Double appui sur « Valider » au paiement complémentaire : une seule vente
# / 22c — Double tap on "Validate" on the complementary payment: one single sale
# --------------------------------------------------------------------------


def test_rejeu_complement_meme_cle_une_seule_vente(lieu):
    """
    Trois jus à 3,50 € (10,50 €), 5,00 € sur la carte du client, le reste en CB. Le
    même paiement complémentaire part deux fois avec la MÊME clé d'idempotence. Les
    deux réponses sont des succès, mais une seule vente existe pour cette clé, et la
    carte n'est débitée qu'une fois (une transaction, solde 5,00 € → 0).
    / The same complementary payment posted twice with the SAME key: one sale, the card
    debited once only.
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([jus.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {f"repid-{cle_de_panier(jus)}": "3"}

    premiere_reponse = payer_le_reste_en_especes_ou_en_cb(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        carte_du_client,
        moyen_du_reste="carte_bancaire",
        cle_d_idempotence=cle_d_idempotence,
    )
    deuxieme_reponse = payer_le_reste_en_especes_ou_en_cb(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        carte_du_client,
        moyen_du_reste="carte_bancaire",
        cle_d_idempotence=cle_d_idempotence,
    )

    assert premiere_reponse.status_code == 200
    assert deuxieme_reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert len(transactions_de_vente_de_la_carte(carte_du_client)) == 1
    assert solde_de_la_carte(carte_du_client, monnaie_locale_du_lieu(lieu)) == 0
    assert reglements_de_la_vente(vente) == [
        (PaymentMethod.CC, 550),
        (PaymentMethod.LOCAL_EURO, 500),
    ]
    verifier_egalites(vente)


# ==========================================================================
# LA CARTE NE SUFFIT PAS : UNE DEUXIÈME CARTE PAIE LE RESTE
# / THE CARD IS NOT ENOUGH: A SECOND CARD PAYS THE REST
# ==========================================================================
#
# Sur l'écran « reste à payer », le caissier peut faire poser une deuxième carte. Le
# serveur refait la cascade de la carte 1, puis celle de la carte 2 sur ce qui reste.
# Si les cartes sont celles de membres, la monnaie du réseau (serveur Fedow distant,
# simulé) peut payer une partie du reste pour la carte 1, et tout le reste pour la
# carte 2. Si les deux cartes ne suffisent pas, un second écran « reste à payer »
# propose les espèces ou la CB pour ce qui manque.
# Une seule vente pour tout le paiement. Chaque règlement porte la carte qui a
# réellement payé (et son portefeuille pour un débit local). Les lignes de vente
# gardent la carte 1, comme aujourd'hui.
# / A second card pays what the first one does not cover. One sale for the whole
# payment; each payment carries the card that really paid; the lines keep card 1.


def payer_le_reste_avec_une_deuxieme_carte(
    client_du_caissier,
    point_de_vente,
    champs_du_panier,
    carte_1,
    carte_2,
    cle_d_idempotence,
):
    """
    Le client pose une deuxième carte pour payer le reste du panier : la vraie route
    du paiement complémentaire, moyen « nfc », comme l'écran « reste à payer »
    l'envoie après la lecture de la carte 2 (`tag_id`).
    / The customer taps a second card to pay the rest, through the real route.

    Le serveur refait lui-même la cascade des deux cartes : l'écran n'a pas besoin de
    lui renvoyer le détail de la cascade de la carte 1.
    / The server recomputes both cascades itself.
    """
    donnees_du_formulaire = {
        "uuid_pv": str(point_de_vente.uuid),
        "cle_idempotence_paiement": cle_d_idempotence,
        "tag_id_carte1": carte_1.tag_id,
        "moyen_complement": "nfc",
        "tag_id": carte_2.tag_id,
    }
    donnees_du_formulaire.update(champs_du_panier)
    return client_du_caissier.post(
        URL_DU_PAIEMENT_COMPLEMENTAIRE, donnees_du_formulaire
    )


def payer_le_reste_apres_les_deux_cartes(
    client_du_caissier,
    point_de_vente,
    champs_du_panier,
    carte_1,
    carte_2,
    moyen_du_reste,
    cle_d_idempotence,
    somme_donnee_en_centimes="",
):
    """
    Les deux cartes ne suffisent pas : le caissier règle ce qui manque depuis le second
    écran « reste à payer ». Ce formulaire renvoie la carte 2 dans `tag_id_carte2`.
    / Both cards are not enough: the cashier pays what is missing from the second
    remainder screen, which sends card 2 back in `tag_id_carte2`.

    `moyen_du_reste` : "espece" ou "carte_bancaire".
    `somme_donnee_en_centimes` : ce que le client tend en espèces ; vide = compte juste.
    """
    donnees_du_formulaire = {
        "uuid_pv": str(point_de_vente.uuid),
        "cle_idempotence_paiement": cle_d_idempotence,
        "tag_id_carte1": carte_1.tag_id,
        "tag_id_carte2": carte_2.tag_id,
        "moyen_complement": moyen_du_reste,
        "given_sum": somme_donnee_en_centimes,
    }
    donnees_du_formulaire.update(champs_du_panier)
    return client_du_caissier.post(
        URL_DU_PAIEMENT_COMPLEMENTAIRE, donnees_du_formulaire
    )


def solde_du_reseau_simule_par_membre(solde_par_membre):
    """
    La lecture du solde du réseau (`lire_depensable_fed_frais`), simulée pour plusieurs
    membres : rend (solde en centimes, réseau joignable) selon l'utilisateur demandé.
    Un utilisateur absent du dictionnaire n'a rien sur le réseau.
    / The network balance read, faked per member.

    :param solde_par_membre: {pk de l'utilisateur: solde en centimes}
    """

    def lire_le_solde_du_membre(utilisateur):
        if utilisateur.pk in solde_par_membre:
            return (solde_par_membre[utilisateur.pk], True)
        return (0, True)

    return lire_le_solde_du_membre


def fedow_du_reseau_simule_par_membre(transactions_par_membre):
    """
    Le client du serveur Fedow distant (`FedowAPI`), simulé pour plusieurs membres :
    le débit d'un membre rend SES transactions. Aucun appel réseau.
    / The remote Fedow client, faked per member: each member's debit returns its own
    transactions.

    :param transactions_par_membre: {pk de l'utilisateur: [transaction, …]}
    """

    def debiter_le_membre(user, **autres_arguments):
        return transactions_par_membre[user.pk]

    faux_fedow = MagicMock()
    faux_fedow.transaction.to_place_from_qrcode.side_effect = debiter_le_membre
    return faux_fedow


def montant_debite_par_membre(faux_fedow):
    """
    Les débits demandés au serveur Fedow simulé : {pk de l'utilisateur: montant}.
    / The debits asked from the faked Fedow server, per member.
    """
    montants_par_membre = {}
    for appel in faux_fedow.transaction.to_place_from_qrcode.call_args_list:
        montants_par_membre[appel.kwargs["user"].pk] = appel.kwargs["amount"]
    return montants_par_membre


# --------------------------------------------------------------------------
# 13 — Deux cartes en monnaie locale : chaque règlement porte sa carte
# / 13 — Two cards in local currency: each payment carries its own card
# --------------------------------------------------------------------------


def test_deuxieme_carte_chaque_reglement_porte_sa_carte(lieu):
    """
    Trois jus à 3,50 € (TVA 20 %, 10,50 €). La carte 1 porte 5,00 € de monnaie locale,
    la carte 2 en porte 6,00 € : la carte 1 paie 5,00 €, la carte 2 paie le reste,
    5,50 €.
    Une vente de la caisse, réglée : catalogue 1050, net 1050, HT 875, TVA 175. Sa
    carte est la carte 1.
    Deux règlements en monnaie locale, chacun COPIÉ de SA transaction : 500 avec la
    carte 1, son portefeuille et l'uuid de sa transaction ; 550 avec la carte 2, son
    portefeuille et l'uuid de sa transaction.
    Les lignes de vente gardent toutes la carte 1, comme aujourd'hui.
    / Card 1 pays 5.00 €, card 2 pays 5.50 €. One settled sale 1050 / 875 / 175 (card
    1). Two local-currency payments, each copied from its own card's transaction (card,
    wallet, transaction uuid). The lines all keep card 1.
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([jus.produit])
    carte_1 = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500)
    carte_2 = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=600)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse = payer_le_reste_avec_une_deuxieme_carte(
        client_du_caissier,
        point_de_vente,
        {f"repid-{cle_de_panier(jus)}": "3"},
        carte_1,
        carte_2,
        cle_d_idempotence,
    )

    assert reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.statut == Vente.Statut.REGLEE
    assert vente.origine == SaleOrigin.LABOUTIK
    assert vente.point_de_vente_id == point_de_vente.pk
    assert vente.carte_id == carte_1.pk
    assert vente.total_catalogue == 1050
    assert vente.total_ttc == 1050
    assert vente.total_ht == 875
    assert vente.total_tva == 175

    # Chaque carte a été débitée une fois, de sa part.
    # / Each card was debited once, of its share.
    transactions_de_la_carte_1 = transactions_de_vente_de_la_carte(carte_1)
    transactions_de_la_carte_2 = transactions_de_vente_de_la_carte(carte_2)
    assert len(transactions_de_la_carte_1) == 1
    assert len(transactions_de_la_carte_2) == 1
    transaction_de_la_carte_1 = transactions_de_la_carte_1[0]
    transaction_de_la_carte_2 = transactions_de_la_carte_2[0]
    assert transaction_de_la_carte_1.amount == 500
    assert transaction_de_la_carte_2.amount == 550

    # Chaque règlement porte SA carte, SON portefeuille et SA transaction.
    # / Each payment carries ITS card, ITS wallet and ITS transaction.
    monnaie_locale = monnaie_locale_du_lieu(lieu)
    assert reglements_complets_de_la_vente(vente) == sorted(
        [
            (
                PaymentMethod.LOCAL_EURO,
                500,
                str(monnaie_locale.uuid),
                carte_1.pk,
                carte_1.wallet_ephemere_id,
                transaction_de_la_carte_1.uuid,
                "",
            ),
            (
                PaymentMethod.LOCAL_EURO,
                550,
                str(monnaie_locale.uuid),
                carte_2.pk,
                carte_2.wallet_ephemere_id,
                transaction_de_la_carte_2.uuid,
                "",
            ),
        ],
        key=str,
    )

    # Les lignes gardent la carte 1 et l'identifiant du paiement.
    # / The lines keep card 1 and the payment id.
    for article in vente.articles.all():
        assert article.carte_id == carte_1.pk
        assert str(article.uuid_transaction) == cle_d_idempotence
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 13b — Le réseau paie pour les deux cartes : un règlement par transaction
# / 13b — The network pays for both cards: one payment per transaction
# --------------------------------------------------------------------------


def test_deuxieme_carte_legacy_un_reglement_par_transaction_avec_sa_carte(lieu):
    """
    Une bière à 5,00 €, un jus à 3,50 € et un café à 2,00 € (10,50 €). Les deux cartes
    sont celles de membres, sans rien dans les monnaies du lieu.
    - Carte 1 : le réseau ne peut payer que 6,00 €. Le serveur Fedow débite 6,00 € de
      monnaie fédérée (FED) : une transaction distante, qui couvre DEUX parts (la
      bière, et 1,00 € du jus).
    - Carte 2 : le réseau peut payer tout le reste (4,50 €). Le serveur Fedow débite
      1,50 € de monnaie locale d'un autre lieu (TLF) et 3,00 € de monnaie fédérée
      (FED) : deux transactions distantes ; la FED couvre DEUX parts (1,00 € du jus,
      et le café).
    La vente a UN règlement par transaction distante (pas un par part d'article),
    chacun avec l'uuid de SA transaction dans `reference_externe`, sa monnaie, pas de
    `fedow_transaction_uuid` (réservé aux transactions locales), et la carte qui a été
    débitée : SF 600 pour la carte 1 ; LE 150 et SF 300 pour la carte 2.
    Le client de la vente est le membre de la carte 1.
    / 10.50 €: the network pays 6.00 € for card 1 (one FED transaction over two parts)
    and the 4.50 € rest for card 2 (TLF 150 + FED 300, the FED one over two parts). One
    payment per remote transaction, uuid in `reference_externe`, with the debited card.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    cafe = creer_un_article_de_caisse("cafe", prix_en_euros="2.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente(
        [biere.produit, jus.produit, cafe.produit]
    )
    carte_1 = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    carte_2 = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(jus)}": "1",
        f"repid-{cle_de_panier(cafe)}": "1",
    }
    transaction_federee_de_la_carte_1 = transaction_du_reseau("FED", 600)
    transaction_locale_de_la_carte_2 = transaction_du_reseau("TLF", 150)
    transaction_federee_de_la_carte_2 = transaction_du_reseau("FED", 300)
    faux_fedow = fedow_du_reseau_simule_par_membre(
        {
            carte_1.user_id: [transaction_federee_de_la_carte_1],
            carte_2.user_id: [
                transaction_locale_de_la_carte_2,
                transaction_federee_de_la_carte_2,
            ],
        }
    )
    lire_le_solde_du_reseau = solde_du_reseau_simule_par_membre(
        {carte_1.user_id: 600, carte_2.user_id: 1000}
    )

    with patch(
        "laboutik.views.lire_depensable_fed_frais", side_effect=lire_le_solde_du_reseau
    ):
        with patch("laboutik.views.FedowAPI", return_value=faux_fedow):
            reponse = payer_le_reste_avec_une_deuxieme_carte(
                client_du_caissier,
                point_de_vente,
                champs_du_panier,
                carte_1,
                carte_2,
                cle_d_idempotence,
            )

    assert reponse.status_code == 200
    # Le réseau est débité pour chacune des deux cartes : 6,00 € pour la carte 1,
    # tout le reste (4,50 €) pour la carte 2.
    # / The network is debited for both cards.
    assert montant_debite_par_membre(faux_fedow) == {
        carte_1.user_id: 600,
        carte_2.user_id: 450,
    }

    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.client_id == carte_1.user_id
    assert vente.carte_id == carte_1.pk
    assert vente.total_catalogue == 1050
    assert vente.total_ttc == 1050

    # Chaque transaction FED couvre deux parts : un règlement par part en ferait deux.
    # / Each FED transaction covers two parts: one payment per part would make two.
    parts_payees_en_monnaie_federee = vente.articles.filter(
        payment_method=PaymentMethod.STRIPE_FED
    )
    assert parts_payees_en_monnaie_federee.count() == 4

    reglements_lus = []
    for reglement in vente.reglements.all():
        monnaie_du_reglement = None
        if reglement.asset is not None:
            monnaie_du_reglement = str(reglement.asset)
        reglements_lus.append(
            (
                reglement.moyen,
                reglement.montant,
                reglement.reference_externe,
                monnaie_du_reglement,
                reglement.carte_id,
                reglement.fedow_transaction_uuid,
            )
        )
    assert sorted(reglements_lus, key=str) == sorted(
        [
            (
                PaymentMethod.STRIPE_FED,
                600,
                transaction_federee_de_la_carte_1["uuid"],
                transaction_federee_de_la_carte_1["asset"],
                carte_1.pk,
                None,
            ),
            (
                PaymentMethod.LOCAL_EURO,
                150,
                transaction_locale_de_la_carte_2["uuid"],
                transaction_locale_de_la_carte_2["asset"],
                carte_2.pk,
                None,
            ),
            (
                PaymentMethod.STRIPE_FED,
                300,
                transaction_federee_de_la_carte_2["uuid"],
                transaction_federee_de_la_carte_2["asset"],
                carte_2.pk,
                None,
            ),
        ],
        key=str,
    )

    # Les lignes gardent la carte 1, même les parts payées par le réseau de la carte 2.
    # / The lines keep card 1, even the parts paid by card 2's network money.
    for article in vente.articles.all():
        assert article.carte_id == carte_1.pk
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 13c — Les deux cartes ne suffisent pas : le reste en espèces, règlement = reste dû
# / 13c — Both cards are not enough: the rest in cash, payment = amount due
# --------------------------------------------------------------------------


def test_deuxieme_carte_puis_especes_reglement_egal_au_reste_du(lieu):
    """
    Trois jus à 3,50 € (10,50 €). La carte 1 porte 5,00 € de monnaie locale, la carte 2
    en porte 3,00 € : il manque 2,50 €.
    Le client pose la carte 2 : le second écran « reste à payer » s'affiche, rien n'est
    écrit. Le caissier règle alors les 2,50 € en espèces ; le client tend un billet de
    10,00 €, la caisse rend 7,50 €. Même clé d'idempotence pour les deux passages.
    La vente a trois règlements : monnaie locale 500 (carte 1, sa transaction),
    monnaie locale 300 (carte 2, sa transaction), et UN règlement espèces du reste dû,
    250 — jamais la somme donnée. Le règlement espèces n'a ni carte, ni portefeuille,
    ni monnaie.
    / Card 1 pays 5.00 €, card 2 pays 3.00 €, 2.50 € is paid in cash from the second
    remainder screen (10.00 € handed over). Three payments: LE 500 (card 1), LE 300
    (card 2), and ONE cash payment of the amount due, 250, never the amount handed over.
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([jus.produit])
    carte_1 = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500)
    carte_2 = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=300)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {f"repid-{cle_de_panier(jus)}": "3"}

    # 1er passage : la carte 2 ne suffit pas, le second écran « reste à payer ».
    # / 1st pass: card 2 is not enough, the second remainder screen.
    reponse_de_la_deuxieme_carte = payer_le_reste_avec_une_deuxieme_carte(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        carte_1,
        carte_2,
        cle_d_idempotence,
    )
    assert reponse_de_la_deuxieme_carte.status_code == 200
    assert 'data-testid="complement-paiement"' in (
        reponse_de_la_deuxieme_carte.content.decode()
    )
    assert not Vente.objects.filter(idempotency_key=cle_d_idempotence).exists()

    # 2e passage : le reste en espèces, avec un billet de 10,00 €.
    # / 2nd pass: the rest in cash, with a 10.00 € note.
    reponse = payer_le_reste_apres_les_deux_cartes(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        carte_1,
        carte_2,
        moyen_du_reste="espece",
        cle_d_idempotence=cle_d_idempotence,
        somme_donnee_en_centimes="1000",
    )

    assert reponse.status_code == 200
    assert 'data-testid="paiement-succes"' in reponse.content.decode()
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente.carte_id == carte_1.pk
    assert vente.total_ttc == 1050

    transaction_de_la_carte_1 = transactions_de_vente_de_la_carte(carte_1)[0]
    transaction_de_la_carte_2 = transactions_de_vente_de_la_carte(carte_2)[0]
    monnaie_locale = monnaie_locale_du_lieu(lieu)
    assert reglements_complets_de_la_vente(vente) == sorted(
        [
            (
                PaymentMethod.LOCAL_EURO,
                500,
                str(monnaie_locale.uuid),
                carte_1.pk,
                carte_1.wallet_ephemere_id,
                transaction_de_la_carte_1.uuid,
                "",
            ),
            (
                PaymentMethod.LOCAL_EURO,
                300,
                str(monnaie_locale.uuid),
                carte_2.pk,
                carte_2.wallet_ephemere_id,
                transaction_de_la_carte_2.uuid,
                "",
            ),
            (PaymentMethod.CASH, 250, None, None, None, None, ""),
        ],
        key=str,
    )
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 16c — Égalité rompue après les débits du réseau des deux cartes
# / 16c — Broken equality after the network debits of both cards
# --------------------------------------------------------------------------


def test_egalite_rompue_apres_debit_legacy_journalisee_deuxieme_carte(lieu, caplog):
    """
    Même paiement que le test 13b (8,50 €) : le réseau débite 3,00 € pour la carte 1 et
    5,50 € pour la carte 2 (hors de la transaction de base : ces débits ne s'annulent
    pas). Puis la vente ne peut pas être encaissée : ses égalités sont rompues
    (`EgaliteDeVenteRompue`, simulée à l'encaissement).
    La caisse journalise UN seul INCIDENT qui couvre les débits du réseau des DEUX
    cartes (les montants, les cartes, l'uuid de chaque transaction du réseau) pour une
    régularisation à la main, et rend son écran d'erreur (jamais une erreur 500). Rien
    n'est écrit : ni vente, ni ligne.
    / Same payment as 13b: the network debits both cards, then the sale cannot be
    settled (broken equality, faked). ONE incident covering both cards' network debits
    (amounts, cards, every transaction uuid), the error screen (never a 500), nothing
    written.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit, jus.produit])
    carte_1 = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    carte_2 = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(jus)}": "1",
    }
    transaction_federee_de_la_carte_1 = transaction_du_reseau("FED", 300)
    transaction_locale_de_la_carte_2 = transaction_du_reseau("TLF", 150)
    transaction_federee_de_la_carte_2 = transaction_du_reseau("FED", 400)
    faux_fedow = fedow_du_reseau_simule_par_membre(
        {
            carte_1.user_id: [transaction_federee_de_la_carte_1],
            carte_2.user_id: [
                transaction_locale_de_la_carte_2,
                transaction_federee_de_la_carte_2,
            ],
        }
    )
    lire_le_solde_du_reseau = solde_du_reseau_simule_par_membre(
        {carte_1.user_id: 300, carte_2.user_id: 1000}
    )
    egalite_rompue = EgaliteDeVenteRompue(
        "Égalité simulée par le test : règlements 850, articles 851."
    )

    with caplog.at_level(logging.ERROR, logger="laboutik.views"):
        with patch(
            "laboutik.views.lire_depensable_fed_frais",
            side_effect=lire_le_solde_du_reseau,
        ):
            with patch("laboutik.views.FedowAPI", return_value=faux_fedow):
                with patch("laboutik.views.encaisser_vente", side_effect=egalite_rompue):
                    reponse = payer_le_reste_avec_une_deuxieme_carte(
                        client_du_caissier,
                        point_de_vente,
                        champs_du_panier,
                        carte_1,
                        carte_2,
                        cle_d_idempotence,
                    )

    # Les deux débits du réseau ont bien eu lieu : c'est ce qui rend l'incident
    # nécessaire.
    # / Both network debits did happen: that is why the incident is needed.
    assert montant_debite_par_membre(faux_fedow) == {
        carte_1.user_id: 300,
        carte_2.user_id: 550,
    }

    # L'écran d'erreur de la caisse, pas une erreur du serveur, pas un succès.
    # / The register's error screen: not a server error, not a success.
    assert reponse.status_code < 500
    contenu_de_la_reponse = reponse.content.decode()
    assert 'data-testid="alerte-messages"' in contenu_de_la_reponse
    assert 'data-testid="paiement-succes"' not in contenu_de_la_reponse

    # Un seul incident, qui couvre les deux cartes : chaque montant débité sur le
    # réseau (comme nombre entier : pas un morceau d'uuid), chaque carte, chaque uuid.
    # / One incident covering both cards: each amount, each card, each uuid.
    messages_d_incident = []
    for enregistrement in caplog.records:
        message_journalise = enregistrement.getMessage()
        est_une_erreur = enregistrement.levelno >= logging.ERROR
        if est_une_erreur and "INCIDENT" in message_journalise:
            messages_d_incident.append(message_journalise)
    assert len(messages_d_incident) == 1, (
        f"Attendu : un incident journalisé, trouvé : {messages_d_incident}"
    )
    message_d_incident = messages_d_incident[0]
    assert re.search(r"\b300\b", message_d_incident)
    assert re.search(r"\b550\b", message_d_incident)
    assert carte_1.tag_id in message_d_incident
    assert carte_2.tag_id in message_d_incident
    assert transaction_federee_de_la_carte_1["uuid"] in message_d_incident
    assert transaction_locale_de_la_carte_2["uuid"] in message_d_incident
    assert transaction_federee_de_la_carte_2["uuid"] in message_d_incident

    # Rien n'est écrit.
    # / Nothing is written.
    assert not Vente.objects.filter(idempotency_key=cle_d_idempotence).exists()
    assert not LigneArticle.objects.filter(pricesold__price=biere.tarif).exists()
    assert not LigneArticle.objects.filter(pricesold__price=jus.tarif).exists()


# --------------------------------------------------------------------------
# 16d — Le réseau de la carte 2 est débité, celui de la carte 1 échoue
# / 16d — Card 2's network debit is done, card 1's network debit fails
# --------------------------------------------------------------------------


def test_deuxieme_carte_debit_reseau_carte1_echoue_incident_carte2_journalise(
    lieu, caplog
):
    """
    Même paiement que le test 13b (8,50 €, deux cartes de membres). Le réseau débite
    d'abord 5,50 € pour la carte 2 (appel au serveur distant : il ne s'annule pas).
    Puis le débit du réseau pour la carte 1 échoue (son solde a changé).
    La caisse demande de rescanner la carte (statut 409), comme pour tout échec de
    débit du réseau. Mais l'argent de la carte 2 est déjà prélevé sans vente : la caisse
    journalise un INCIDENT (le montant, la carte 2, l'uuid de chaque transaction de la
    carte 2) pour une régularisation à la main. Rien n'est écrit : ni vente, ni ligne.
    / Card 2's network debit is done, then card 1's fails: 409 "rescan", and ONE
    incident for card 2's debit (amount, card 2, transaction uuids). Nothing written.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit, jus.produit])
    carte_1 = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    carte_2 = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(jus)}": "1",
    }
    transaction_locale_de_la_carte_2 = transaction_du_reseau("TLF", 150)
    transaction_federee_de_la_carte_2 = transaction_du_reseau("FED", 400)
    lire_le_solde_du_reseau = solde_du_reseau_simule_par_membre(
        {carte_1.user_id: 300, carte_2.user_id: 1000}
    )

    # Le serveur Fedow simulé débite la carte 2, puis refuse le débit de la carte 1.
    # / The faked Fedow server debits card 2, then refuses card 1's debit.
    def debiter_le_membre(user, **autres_arguments):
        if user.pk == carte_2.user_id:
            return [transaction_locale_de_la_carte_2, transaction_federee_de_la_carte_2]
        raise Exception("Solde du réseau insuffisant (simulé par le test)")

    faux_fedow = MagicMock()
    faux_fedow.transaction.to_place_from_qrcode.side_effect = debiter_le_membre

    with caplog.at_level(logging.ERROR, logger="laboutik.views"):
        with patch(
            "laboutik.views.lire_depensable_fed_frais",
            side_effect=lire_le_solde_du_reseau,
        ):
            with patch("laboutik.views.FedowAPI", return_value=faux_fedow):
                reponse = payer_le_reste_avec_une_deuxieme_carte(
                    client_du_caissier,
                    point_de_vente,
                    champs_du_panier,
                    carte_1,
                    carte_2,
                    cle_d_idempotence,
                )

    # Les deux débits ont été demandés : la carte 2 (réussi), puis la carte 1 (échoué).
    # / Both debits were asked: card 2 (done), then card 1 (failed).
    assert montant_debite_par_membre(faux_fedow) == {
        carte_1.user_id: 300,
        carte_2.user_id: 550,
    }

    # L'écran « rescannez la carte », en 409, comme tout échec de débit du réseau.
    # / The "rescan the card" screen, 409, like any network debit failure.
    assert reponse.status_code == 409
    contenu_de_la_reponse = reponse.content.decode()
    assert 'data-testid="alerte-messages"' in contenu_de_la_reponse
    assert 'data-testid="paiement-succes"' not in contenu_de_la_reponse

    # Un seul incident, pour l'argent de la carte 2 prélevé sans vente.
    # / One incident, for card 2's money taken without a sale.
    messages_d_incident = []
    for enregistrement in caplog.records:
        message_journalise = enregistrement.getMessage()
        est_une_erreur = enregistrement.levelno >= logging.ERROR
        if est_une_erreur and "INCIDENT" in message_journalise:
            messages_d_incident.append(message_journalise)
    assert len(messages_d_incident) == 1, (
        f"Attendu : un incident journalisé, trouvé : {messages_d_incident}"
    )
    message_d_incident = messages_d_incident[0]
    assert re.search(r"\b550\b", message_d_incident)
    assert carte_2.tag_id in message_d_incident
    assert transaction_locale_de_la_carte_2["uuid"] in message_d_incident
    assert transaction_federee_de_la_carte_2["uuid"] in message_d_incident

    # Rien n'est écrit.
    # / Nothing is written.
    assert not Vente.objects.filter(idempotency_key=cle_d_idempotence).exists()
    assert not LigneArticle.objects.filter(pricesold__price=biere.tarif).exists()
    assert not LigneArticle.objects.filter(pricesold__price=jus.tarif).exists()


# --------------------------------------------------------------------------
# 16e — Exception imprévue après les débits du réseau des deux cartes
# / 16e — Unexpected exception after the network debits of both cards
# --------------------------------------------------------------------------


def test_deuxieme_carte_exception_imprevue_journalise_les_deux_cartes(lieu, caplog):
    """
    Même paiement que le test 16c (8,50 €) : le réseau débite 3,00 € pour la carte 1 et
    5,50 € pour la carte 2 (hors de la transaction de base : ces débits ne s'annulent
    pas). Puis une erreur imprévue survient pendant l'écriture de la vente (simulée à
    l'encaissement par une `RuntimeError`).
    La caisse journalise UN INCIDENT qui couvre les débits du réseau des DEUX cartes
    (les montants, les cartes, l'uuid de chaque transaction du réseau), puis relaie
    l'erreur (erreur 500 volontaire). Le client de test Django relaie l'exception de la
    vue : le test l'attend avec `pytest.raises`. Rien n'est écrit : ni vente, ni ligne.
    / Both cards' network debits are done, then an unexpected error happens while
    writing the sale. ONE incident covering both cards (amounts, cards, every uuid), then
    the error is re-raised (the test client re-raises it). Nothing written.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit, jus.produit])
    carte_1 = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    carte_2 = creer_une_carte_nfc_d_un_membre_sans_solde_local(lieu)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {
        f"repid-{cle_de_panier(biere)}": "1",
        f"repid-{cle_de_panier(jus)}": "1",
    }
    transaction_federee_de_la_carte_1 = transaction_du_reseau("FED", 300)
    transaction_locale_de_la_carte_2 = transaction_du_reseau("TLF", 150)
    transaction_federee_de_la_carte_2 = transaction_du_reseau("FED", 400)
    faux_fedow = fedow_du_reseau_simule_par_membre(
        {
            carte_1.user_id: [transaction_federee_de_la_carte_1],
            carte_2.user_id: [
                transaction_locale_de_la_carte_2,
                transaction_federee_de_la_carte_2,
            ],
        }
    )
    lire_le_solde_du_reseau = solde_du_reseau_simule_par_membre(
        {carte_1.user_id: 300, carte_2.user_id: 1000}
    )
    erreur_imprevue = RuntimeError("Erreur imprévue simulée par le test.")

    with caplog.at_level(logging.ERROR, logger="laboutik.views"):
        with patch(
            "laboutik.views.lire_depensable_fed_frais",
            side_effect=lire_le_solde_du_reseau,
        ):
            with patch("laboutik.views.FedowAPI", return_value=faux_fedow):
                with patch("laboutik.views.encaisser_vente", side_effect=erreur_imprevue):
                    with pytest.raises(RuntimeError):
                        payer_le_reste_avec_une_deuxieme_carte(
                            client_du_caissier,
                            point_de_vente,
                            champs_du_panier,
                            carte_1,
                            carte_2,
                            cle_d_idempotence,
                        )

    # Les deux débits du réseau ont bien eu lieu : c'est ce qui rend l'incident
    # nécessaire.
    # / Both network debits did happen: that is why the incident is needed.
    assert montant_debite_par_membre(faux_fedow) == {
        carte_1.user_id: 300,
        carte_2.user_id: 550,
    }

    # Un seul incident, qui couvre les deux cartes : chaque montant débité sur le
    # réseau, chaque carte, chaque uuid.
    # / One incident covering both cards: each amount, each card, each uuid.
    messages_d_incident = []
    for enregistrement in caplog.records:
        message_journalise = enregistrement.getMessage()
        est_une_erreur = enregistrement.levelno >= logging.ERROR
        if est_une_erreur and "INCIDENT" in message_journalise:
            messages_d_incident.append(message_journalise)
    assert len(messages_d_incident) == 1, (
        f"Attendu : un incident journalisé, trouvé : {messages_d_incident}"
    )
    message_d_incident = messages_d_incident[0]
    assert re.search(r"\b300\b", message_d_incident)
    assert re.search(r"\b550\b", message_d_incident)
    assert carte_1.tag_id in message_d_incident
    assert carte_2.tag_id in message_d_incident
    assert transaction_federee_de_la_carte_1["uuid"] in message_d_incident
    assert transaction_locale_de_la_carte_2["uuid"] in message_d_incident
    assert transaction_federee_de_la_carte_2["uuid"] in message_d_incident

    # Rien n'est écrit.
    # / Nothing is written.
    assert not Vente.objects.filter(idempotency_key=cle_d_idempotence).exists()
    assert not LigneArticle.objects.filter(pricesold__price=biere.tarif).exists()
    assert not LigneArticle.objects.filter(pricesold__price=jus.tarif).exists()


# --------------------------------------------------------------------------
# 22d — Double appui sur « Valider » avec une deuxième carte : une seule vente
# / 22d — Double tap on "Validate" with a second card: one single sale
# --------------------------------------------------------------------------


def test_rejeu_deuxieme_carte_meme_cle_une_seule_vente(lieu):
    """
    Trois jus à 3,50 € (10,50 €) : 5,00 € sur la carte 1, 6,00 € sur la carte 2. Le même
    paiement par deuxième carte part deux fois avec la MÊME clé d'idempotence. Les deux
    réponses sont des succès, mais une seule vente existe pour cette clé, et chaque
    carte n'est débitée qu'une fois (carte 1 : 5,00 € → 0 ; carte 2 : 6,00 € → 0,50 €).
    / The same second-card payment posted twice with the SAME key: one sale, each card
    debited once only.
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([jus.produit])
    carte_1 = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500)
    carte_2 = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=600)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    champs_du_panier = {f"repid-{cle_de_panier(jus)}": "3"}

    premiere_reponse = payer_le_reste_avec_une_deuxieme_carte(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        carte_1,
        carte_2,
        cle_d_idempotence,
    )
    deuxieme_reponse = payer_le_reste_avec_une_deuxieme_carte(
        client_du_caissier,
        point_de_vente,
        champs_du_panier,
        carte_1,
        carte_2,
        cle_d_idempotence,
    )

    assert premiere_reponse.status_code == 200
    assert deuxieme_reponse.status_code == 200
    vente = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    monnaie_locale = monnaie_locale_du_lieu(lieu)
    assert len(transactions_de_vente_de_la_carte(carte_1)) == 1
    assert len(transactions_de_vente_de_la_carte(carte_2)) == 1
    assert solde_de_la_carte(carte_1, monnaie_locale) == 0
    assert solde_de_la_carte(carte_2, monnaie_locale) == 50
    assert reglements_de_la_vente(vente) == [
        (PaymentMethod.LOCAL_EURO, 500),
        (PaymentMethod.LOCAL_EURO, 550),
    ]
    verifier_egalites(vente)


# ==========================================================================
# ARCHIVE FISCALE LNE : le HT et la TVA stockés sur chaque article
# / LNE FISCAL ARCHIVE: the HT and VAT stored on each item
# ==========================================================================
#
# L'archive fiscale (laboutik/archivage.py) exporte les articles des ventes dans
# `articles.csv`, avec le HT et la TVA STOCKÉS sur l'article (`total_ht`, `total_tva`),
# jamais recalculés depuis `amount × qty`. Une ligne offerte a un net vendu de 0 : HT 0,
# TVA 0, jamais une TVA inventée. Une part payée en jetons est une vente ordinaire à
# TVA 0 (D8 bis) : HT = TTC, TVA 0.
# / The fiscal archive exports the sales' items with their STORED HT and VAT.


def article_dans_l_archive_lne(ligne):
    """
    L'article tel que l'archive fiscale LNE l'exporte (`articles.csv`), par la vraie
    génération de l'archive, sur une fenêtre de dix minutes autour de maintenant. La
    base est partagée : on garde l'article du test par son uuid.
    / The item as the LNE fiscal archive exports it, through the real archive.
    """
    maintenant = timezone.now()
    fichiers_de_l_archive = generer_fichiers_archive(
        schema=connection.schema_name,
        debut=maintenant - timedelta(minutes=5),
        fin=maintenant + timedelta(minutes=5),
    )
    texte_des_articles = fichiers_de_l_archive["articles.csv"].decode("utf-8-sig")
    lecteur_des_articles = csv.DictReader(
        texte_des_articles.splitlines(), delimiter=";"
    )
    for article_exporte in lecteur_des_articles:
        if article_exporte["uuid"] == str(ligne.uuid):
            return article_exporte
    raise AssertionError(f"L'article {ligne.uuid} est absent de l'archive.")


def test_archive_lne_ligne_offerte_exporte_ses_montants_stockes(lieu):
    """
    Le gérant offre une bière à 5,00 € (TVA 20 %). L'article est entièrement offert :
    total catalogue 500, part offerte 500, net vendu 0. L'archive exporte les montants
    stockés : TTC 0, HT 0, TVA 0, part offerte 500. Jamais une TVA inventée sur un
    article offert.
    / A 5.00 € beer gifted by the manager: the archive exports the stored amounts
    (TTC 0, HT 0, VAT 0, offered part 500).
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    carte_du_gerant = creer_une_carte_primaire_en_mode_gerant(point_de_vente)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)

    reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        biere,
        quantite=1,
        moyen_de_paiement="gift",
        autres_champs={
            "tag_id_cm": carte_du_gerant.tag_id,
            "cle_idempotence_paiement": nouvelle_cle_d_idempotence(),
        },
    )

    assert reponse.status_code == 200
    ligne_de_la_biere = LigneArticle.objects.get(pricesold__price=biere.tarif)
    article_exporte = article_dans_l_archive_lne(ligne_de_la_biere)
    assert article_exporte["total_catalogue"] == "500"
    assert article_exporte["part_offerte"] == "500"
    assert article_exporte["total_ttc"] == "0"
    assert article_exporte["total_ht"] == "0"
    assert article_exporte["total_tva"] == "0"


def test_archive_lne_part_en_jetons_tva_zero(lieu):
    """
    Un vin à 10,00 € (TVA 20 %) payé par la carte du client : 6,00 € de jetons cadeau
    et 4,00 € de monnaie locale. Deux parts, au prix unitaire 1000, quantités 0,6 et
    0,4. La part en jetons est une vente ordinaire à TVA 0 (D8 bis) : l'archive exporte
    HT 600, TVA 0. La part en monnaie locale : HT = arrondi(400 / 1,2 = 333,33) = 333,
    TVA 67.
    / A 10.00 € wine paid 6.00 € in tokens + 4.00 € in local currency: the archive
    exports token part HT 600 VAT 0 (0 % VAT, D8 bis), local part HT 333 VAT 67.
    """
    vin = creer_un_article_de_caisse("vin", prix_en_euros="10.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([vin.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=400)
    ajouter_un_solde_sur_la_carte(carte_du_client, monnaie_cadeau_du_lieu(lieu), 600)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)

    reponse = payer_par_la_carte_du_client(
        client_du_caissier,
        point_de_vente,
        {f"repid-{cle_de_panier(vin)}": "1"},
        carte_du_client,
        nouvelle_cle_d_idempotence(),
    )

    assert reponse.status_code == 200
    part_en_jetons = LigneArticle.objects.get(
        pricesold__price=vin.tarif, payment_method=PaymentMethod.LOCAL_GIFT
    )
    part_en_monnaie_locale = LigneArticle.objects.get(
        pricesold__price=vin.tarif, payment_method=PaymentMethod.LOCAL_EURO
    )
    part_en_jetons_exportee = article_dans_l_archive_lne(part_en_jetons)
    assert part_en_jetons_exportee["total_ht"] == "600"
    assert part_en_jetons_exportee["total_tva"] == "0"
    part_en_monnaie_locale_exportee = article_dans_l_archive_lne(part_en_monnaie_locale)
    assert part_en_monnaie_locale_exportee["total_ht"] == "333"
    assert part_en_monnaie_locale_exportee["total_tva"] == "67"


def test_archive_lne_ligne_ordinaire_inchangee(lieu):
    """
    Témoin : une bière à 5,00 € (TVA 20 %) payée en espèces. L'archive exporte
    HT = arrondi(500 / 1,2 = 416,67) = 417 et TVA 83, comme avant.
    / Witness: a 5.00 € beer paid in cash: the archive exports HT 417, VAT 83.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)

    reponse = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        biere,
        quantite=1,
        moyen_de_paiement="espece",
        autres_champs={"cle_idempotence_paiement": nouvelle_cle_d_idempotence()},
    )

    assert reponse.status_code == 200
    ligne_de_la_biere = LigneArticle.objects.get(pricesold__price=biere.tarif)
    article_exporte = article_dans_l_archive_lne(ligne_de_la_biere)
    assert article_exporte["total_ht"] == "417"
    assert article_exporte["total_tva"] == "83"


# L'archive exporte les articles des VENTES (tests/pytest/test_archive_lne_ventes.py) :
# une ligne écrite sans vente n'en fait pas partie.
# / The archive exports the SALES' items: a line without a sale is not part of it.


def test_archive_lne_part_au_centime_tva_stockee(lieu):
    """
    Trois jus à 3,50 € (TVA 20 %, 10,50 €) payés par la carte du client : 5,50 € de
    jetons cadeau, puis 5,00 € de monnaie locale. La part en monnaie locale garde le
    prix unitaire 350 et une quantité partielle de 1,428571 : `amount × qty` vaut
    499,99985, entre deux centimes.
    L'archive exporte l'argent réel stocké sur la part : TTC 500,
    HT = arrondi(500 / 1,2 = 416,67) = 417, TVA = 500 − 417 = 83. Une TVA recalculée
    par `int(amount × qty) − HT` donnerait 499 − 417 = 82.
    / Three 3.50 € juices paid 5.50 € in tokens + 5.00 € in local currency: the local
    part exports its stored TTC 500, HT 417, VAT 83 (a recomputed one: 82).
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([jus.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500)
    ajouter_un_solde_sur_la_carte(carte_du_client, monnaie_cadeau_du_lieu(lieu), 550)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)

    reponse = payer_par_la_carte_du_client(
        client_du_caissier,
        point_de_vente,
        {f"repid-{cle_de_panier(jus)}": "3"},
        carte_du_client,
        nouvelle_cle_d_idempotence(),
    )

    assert reponse.status_code == 200
    # La cascade débite les jetons d'abord (550), puis la monnaie locale (500) : la
    # part en monnaie locale est la dernière, sa quantité est le reste (3 − 1,571429).
    # / The cascade debits tokens first, then local currency: the local part is last.
    part_en_monnaie_locale = LigneArticle.objects.get(
        pricesold__price=jus.tarif, payment_method=PaymentMethod.LOCAL_EURO
    )
    assert part_en_monnaie_locale.amount == 350
    assert part_en_monnaie_locale.qty == Decimal("1.428571")

    part_exportee = article_dans_l_archive_lne(part_en_monnaie_locale)

    assert part_exportee["total_ttc"] == "500"
    assert part_exportee["total_ht"] == "417"
    assert part_exportee["total_tva"] == "83"


# ==========================================================================
# COMMANDE DE TABLE : le paiement écrit la vente, et la commande la garde
# / TABLE ORDER: the payment writes the sale, and the order keeps it
# ==========================================================================
#
# Une commande de table se paie par sa propre route (`payer_commande`). Le panier vient
# des articles de la commande, jamais du formulaire. Le paiement écrit une vente, comme
# au comptoir, et la commande garde cette vente dans `CommandeSauvegarde.vente`.
# Le reste ne change pas : commande payée, articles servis, table libérée.
# La clé du paiement est choisie par la caisse, pas par le test : la vente est lue
# sur la commande, et les lignes du tarif créé pour le test doivent lui appartenir.
# / A table order is paid through its own route. The payment writes a sale, and the
# order keeps it. The rest is unchanged. The sale is read on the order; the test's
# own price lines must belong to it.

URL_DU_PAIEMENT_D_UNE_COMMANDE = "/laboutik/commande/payer/{uuid_de_la_commande}/"


def creer_une_table_occupee_avec_sa_commande(article, quantite):
    """
    ÉTAT DE DÉPART : une table occupée, qui porte une commande ouverte (`OP`) d'un
    article en attente. Rend un objet avec `table` et `commande`.
    / STARTING STATE: an occupied table holding an open order of one waiting article.
    """
    table = Table.objects.create(
        name=f"{PREFIXE_DES_TESTS} table {identifiant_unique()}",
        statut=Table.OCCUPEE,
    )
    commande = CommandeSauvegarde.objects.create(
        table=table,
        statut=CommandeSauvegarde.OPEN,
    )
    ArticleCommandeSauvegarde.objects.create(
        commande=commande,
        product=article.produit,
        price=article.tarif,
        qty=quantite,
        statut=ArticleCommandeSauvegarde.EN_ATTENTE,
    )
    return SimpleNamespace(table=table, commande=commande)


def payer_la_commande_de_table(
    client_du_caissier, point_de_vente, commande, moyen_de_paiement, autres_champs=None
):
    """
    Le caissier paie une commande de table, par la vraie route de la caisse.
    Seuls le point de vente et le moyen de paiement sont envoyés : les articles sont
    lus dans la commande.
    / The cashier pays a table order through the real route. Items come from the order.

    `moyen_de_paiement` : "espece", "carte_bancaire", "CH" ou "nfc".
    `autres_champs` : champs en plus (somme donnée, tag de la carte du client…).
    """
    donnees_du_formulaire = {
        "uuid_pv": str(point_de_vente.uuid),
        "moyen_paiement": moyen_de_paiement,
    }
    if autres_champs is not None:
        donnees_du_formulaire.update(autres_champs)
    adresse_du_paiement = URL_DU_PAIEMENT_D_UNE_COMMANDE.format(
        uuid_de_la_commande=commande.uuid
    )
    return client_du_caissier.post(adresse_du_paiement, donnees_du_formulaire)


def vente_des_lignes_du_tarif(tarif):
    """
    La vente qui porte les lignes de ce tarif. Le tarif est créé par le test : ses
    lignes sont celles du test. Elles doivent toutes appartenir à la même vente.
    / The sale holding the lines of this price. All lines must share one sale.
    """
    lignes_du_tarif = list(LigneArticle.objects.filter(pricesold__price=tarif))
    assert len(lignes_du_tarif) >= 1, "Aucune ligne de vente pour ce tarif."
    identifiants_des_ventes = set()
    for ligne in lignes_du_tarif:
        identifiants_des_ventes.add(ligne.vente_id)
    assert identifiants_des_ventes != {None}, (
        "Les lignes de la commande n'appartiennent à aucune vente."
    )
    assert len(identifiants_des_ventes) == 1, (
        f"Attendu : une seule vente pour les lignes, trouvé : {identifiants_des_ventes}."
    )
    return Vente.objects.get(pk=lignes_du_tarif[0].vente_id)


def verifier_que_la_commande_est_payee_et_la_table_libre(table, commande):
    """
    Ce que le paiement d'une table fait aujourd'hui, et qui ne change pas : commande
    payée (`PA`), articles servis (`SV`), table libre (`L`).
    / What paying a table does today, unchanged: order PAID, items SERVED, table FREE.
    """
    commande.refresh_from_db()
    table.refresh_from_db()
    assert commande.statut == CommandeSauvegarde.PAID
    assert statuts_des_articles_de_la_commande(commande) == [
        ArticleCommandeSauvegarde.SERVI
    ]
    assert table.statut == Table.LIBRE


# --------------------------------------------------------------------------
# 18 — Commande de table payée en espèces : la commande garde sa vente
# / 18 — Table order paid in cash: the order keeps its sale
# --------------------------------------------------------------------------


def test_paiement_table_especes_vente_liee_a_la_commande(lieu):
    """
    Une table porte une commande ouverte de deux bières à 5,00 € (TVA 20 %). Le client
    donne 20,00 € en espèces. Le paiement écrit une vente de la caisse, réglée et
    numérotée : catalogue 1000, net 1000, HT 833, TVA 167, au point de vente, à
    l'opérateur, avec pour clé l'identifiant du paiement porté par les lignes. Un seul
    règlement espèces de 10,00 € : le montant encaissé, pas la somme donnée.
    La commande garde cette vente. Comme aujourd'hui : commande payée, article servi,
    table libre.
    / Two 5.00 € beers on an open table order, 20.00 € given in cash. One settled sale
    (1000 / 833 / 167) with the payment id as key; one cash payment of 1000, not the
    given sum. The order keeps the sale; order paid, item served, table free.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    table_et_commande = creer_une_table_occupee_avec_sa_commande(biere, quantite=2)
    # L'administrateur est créé ici : le test compare l'opérateur de la vente à lui.
    # / Created here: the test compares the sale operator to this user.
    administrateur_du_lieu = creer_utilisateur(prenom="Admin", nom="Lieu")
    administrateur_du_lieu.client_admin.add(lieu.tenant)
    client_du_caissier = client_connecte(administrateur_du_lieu)

    reponse = payer_la_commande_de_table(
        client_du_caissier,
        point_de_vente,
        table_et_commande.commande,
        moyen_de_paiement="espece",
        autres_champs={"given_sum": "2000"},
    )

    assert reponse.status_code == 200
    commande = table_et_commande.commande
    verifier_que_la_commande_est_payee_et_la_table_libre(
        table_et_commande.table, commande
    )

    # La commande garde la vente écrite par le paiement.
    # / The order keeps the sale written by the payment.
    assert commande.vente_id is not None, "La commande payée n'a pas de vente."
    vente = commande.vente
    assert vente_des_lignes_du_tarif(biere.tarif).pk == vente.pk

    assert vente.nature == Vente.Nature.VENTE
    assert vente.statut == Vente.Statut.REGLEE
    assert vente.numero is not None
    assert vente.origine == SaleOrigin.LABOUTIK
    assert vente.point_de_vente_id == point_de_vente.pk
    assert vente.operateur_id == administrateur_du_lieu.pk
    assert vente.total_catalogue == 1000
    assert vente.total_offert == 0
    assert vente.total_ttc == 1000
    assert vente.total_ht == 833
    assert vente.total_tva == 167

    # La clé de la vente est l'identifiant du paiement, le même que sur les lignes.
    # / The sale key is the payment id, the same as on the lines.
    article = seul_article_de_la_vente(vente)
    assert article.uuid_transaction is not None
    assert vente.idempotency_key == str(article.uuid_transaction)
    assert article.payment_method == PaymentMethod.CASH
    assert article.amount == 500
    assert article.qty == 2

    assert reglements_de_la_vente(vente) == [(PaymentMethod.CASH, 1000)]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 18b — Commande de table payée en CB ou en chèque : le règlement de ce moyen
# / 18b — Table order paid by bank card or cheque: a payment of that method
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "moyen_de_paiement, moyen_attendu_en_base",
    [
        ("carte_bancaire", PaymentMethod.CC),
        ("CH", PaymentMethod.CHEQUE),
    ],
)
def test_paiement_table_cb_vente_liee_a_la_commande(
    lieu, moyen_de_paiement, moyen_attendu_en_base
):
    """
    La même commande de deux bières à 5,00 €, payée en CB, ou en chèque. La vente est
    réglée par UN règlement de ce moyen, de 10,00 €, et la commande la garde. Comme
    aujourd'hui : commande payée, article servi, table libre.
    / The same order paid by bank card or cheque: one payment of that method (1000),
    and the order keeps the sale.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    table_et_commande = creer_une_table_occupee_avec_sa_commande(biere, quantite=2)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)

    reponse = payer_la_commande_de_table(
        client_du_caissier,
        point_de_vente,
        table_et_commande.commande,
        moyen_de_paiement=moyen_de_paiement,
    )

    assert reponse.status_code == 200
    commande = table_et_commande.commande
    verifier_que_la_commande_est_payee_et_la_table_libre(
        table_et_commande.table, commande
    )

    assert commande.vente_id is not None, "La commande payée n'a pas de vente."
    vente = commande.vente
    assert vente_des_lignes_du_tarif(biere.tarif).pk == vente.pk
    assert vente.statut == Vente.Statut.REGLEE
    assert vente.total_catalogue == 1000
    assert vente.total_ttc == 1000
    assert vente.total_ht == 833
    assert vente.total_tva == 167
    article = seul_article_de_la_vente(vente)
    assert article.payment_method == moyen_attendu_en_base
    assert vente.idempotency_key == str(article.uuid_transaction)
    assert reglements_de_la_vente(vente) == [(moyen_attendu_en_base, 1000)]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# 19 — Commande de table payée par la carte NFC : la vente du paiement NFC
# / 19 — Table order paid by NFC card: the NFC payment's sale
# --------------------------------------------------------------------------


def test_paiement_table_nfc_vente_liee_a_la_commande(lieu):
    """
    La commande de deux bières à 5,00 € est payée avec la carte NFC du client, qui
    porte 20,00 € de monnaie locale. Le paiement NFC de la caisse écrit sa vente : un
    règlement en monnaie locale de 10,00 €, copié de la transaction de la carte (son
    uuid dans `fedow_transaction_uuid`). C'est CETTE vente que la commande garde.
    Comme aujourd'hui : commande payée, article servi, table libre, carte débitée de
    10,00 €.
    / The order is paid by the customer's NFC card (20.00 € of local currency). The NFC
    payment writes its sale (one local-currency payment of 1000, copied from the card
    transaction). The order keeps THAT sale.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    table_et_commande = creer_une_table_occupee_avec_sa_commande(biere, quantite=2)
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=2000)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)

    reponse = payer_la_commande_de_table(
        client_du_caissier,
        point_de_vente,
        table_et_commande.commande,
        moyen_de_paiement="nfc",
        autres_champs={"tag_id": carte_du_client.tag_id},
    )

    assert reponse.status_code == 200
    commande = table_et_commande.commande
    verifier_que_la_commande_est_payee_et_la_table_libre(
        table_et_commande.table, commande
    )
    assert solde_de_la_carte(carte_du_client, monnaie_locale_du_lieu(lieu)) == 1000

    # La vente écrite par le paiement NFC : réglée par la transaction de la carte.
    # / The sale written by the NFC payment: settled by the card transaction.
    vente_du_paiement_nfc = vente_des_lignes_du_tarif(biere.tarif)
    assert vente_du_paiement_nfc.statut == Vente.Statut.REGLEE
    assert vente_du_paiement_nfc.carte_id == carte_du_client.pk
    assert vente_du_paiement_nfc.total_catalogue == 1000
    assert vente_du_paiement_nfc.total_ttc == 1000
    transactions_creees = transactions_de_vente_de_la_carte(carte_du_client)
    assert len(transactions_creees) == 1
    transaction_de_la_carte = transactions_creees[0]
    assert reglements_en_detail(vente_du_paiement_nfc) == [
        (PaymentMethod.LOCAL_EURO, 1000, transaction_de_la_carte.uuid)
    ]

    # La commande garde CETTE vente.
    # / The order keeps THAT sale.
    assert commande.vente_id is not None, "La commande payée n'a pas de vente."
    assert commande.vente_id == vente_du_paiement_nfc.pk
    verifier_egalites(vente_du_paiement_nfc)


# --------------------------------------------------------------------------
# 19b — Carte NFC sans assez de solde : aucune vente, la commande reste ouverte
# / 19b — NFC card without enough balance: no sale, the order stays open
# --------------------------------------------------------------------------


def test_paiement_table_nfc_refuse_aucune_vente_commande_ouverte(lieu):
    """
    La commande de deux bières à 5,00 € (10,00 €) est présentée à une carte NFC
    anonyme qui ne porte que 3,00 € de monnaie locale. La caisse propose de compléter
    le paiement : rien n'est encaissé. Aucune ligne, aucune vente, la carte n'est pas
    débitée ; la commande reste ouverte, sans vente, et la table reste occupée.
    / A 10.00 € order presented to an anonymous card holding 3.00 €: nothing is
    collected. No line, no sale, no debit; the order stays open with no sale, the table
    stays occupied.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    table_et_commande = creer_une_table_occupee_avec_sa_commande(biere, quantite=2)
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=300)
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)

    reponse = payer_la_commande_de_table(
        client_du_caissier,
        point_de_vente,
        table_et_commande.commande,
        moyen_de_paiement="nfc",
        autres_champs={"tag_id": carte_du_client.tag_id},
    )

    assert reponse.status_code == 200
    assert b"paiement-succes" not in reponse.content
    commande = table_et_commande.commande
    table = table_et_commande.table
    commande.refresh_from_db()
    table.refresh_from_db()
    assert commande.statut == CommandeSauvegarde.OPEN
    assert commande.vente_id is None
    assert statuts_des_articles_de_la_commande(commande) == [
        ArticleCommandeSauvegarde.EN_ATTENTE
    ]
    assert table.statut == Table.OCCUPEE

    assert not LigneArticle.objects.filter(pricesold__price=biere.tarif).exists()
    assert not Vente.objects.filter(carte=carte_du_client).exists()
    assert transactions_de_vente_de_la_carte(carte_du_client) == []
    assert solde_de_la_carte(carte_du_client, monnaie_locale_du_lieu(lieu)) == 300


# ==========================================================================
# CORRECTION DE MOYEN DE PAIEMENT : une vente CORRECTION liée, l'origine ne change pas
# / PAYMENT METHOD CORRECTION: a linked CORRECTION sale, the original never changes
# ==========================================================================
#
# Le caissier s'est trompé de moyen (espèces au lieu de CB). Il corrige après coup,
# depuis l'historique des ventes. Deux choses sont écrites, dans la même transaction :
# - la correction des lignes, comme aujourd'hui : une trace `CorrectionPaiement` par
#   ligne, et le nouveau `payment_method` sur les lignes (les anciens rapports le
#   lisent jusqu'à la fiche H) ;
# - une vente `CORRECTION`, liée à la vente d'origine, sans article, avec deux
#   règlements qui s'annulent : −montant à l'ancien moyen, +montant au nouveau. Le
#   montant est la somme des `total_ttc` des lignes corrigées.
# La vente d'origine est déjà encaissée : elle ne change jamais (D14). Mêmes règlements,
# même empreinte, et la vérification de la chaîne ne signale rien pour elle.
# / The line correction stays as today (audit trail + new payment_method). On top of it,
# a CORRECTION sale linked to the original one, without items, with two payments that
# cancel out. The original sale never changes.
#
# BASE PARTAGÉE, ET NON SCHÉMA DÉDIÉ
# La vérification de la chaîne parcourt toutes les ventes du lieu. Ces tests ne lisent
# que les anomalies de LEURS ventes. Une anomalie d'une vente dépend de ses propres
# données et de la vente qui la précède dans la chaîne, posée sous le verrou du lieu par
# `encaisser_vente`. Aucun test n'asserte une valeur de numéro ni la santé de la chaîne
# entière. Aucun test de ce fichier ne crée de clôture.
# / Shared database: the tests only read the anomalies of THEIR sales, which depend on
# their own data and on their predecessor. No number value is asserted.

# Adresse de la correction (laboutik/urls.py).
# / Correction address.
URL_DE_LA_CORRECTION_DU_MOYEN = "/laboutik/paiement/corriger_moyen_paiement/"


def corriger_le_moyen_de_paiement(client_du_caissier, ligne, nouveau_moyen):
    """
    Le caissier corrige le moyen de paiement d'une ligne, par la vraie route, comme le
    formulaire de l'historique des ventes l'envoie (`hx_corriger_moyen_paiement.html`).
    / The cashier corrects a line's payment method, through the real route.

    :param ligne: la `LigneArticle` cliquée dans l'historique
    :param nouveau_moyen: `PaymentMethod.CASH`, `CC` ou `CHEQUE`
    """
    # Le moyen que le formulaire affiche : celui de la ligne, relu en base (le
    # formulaire est rouvert à chaque correction).
    # / The method the form shows: the line's, read back.
    donnees_du_formulaire = {
        "ligne_uuid": str(ligne.uuid),
        "ancien_moyen": LigneArticle.objects.get(pk=ligne.pk).payment_method,
        "nouveau_moyen": nouveau_moyen,
        "raison": "Erreur de moyen au moment du paiement",
    }
    return client_du_caissier.post(URL_DE_LA_CORRECTION_DU_MOYEN, donnees_du_formulaire)


def ventes_de_correction_liees_a(vente_d_origine):
    """
    Les ventes `CORRECTION` liées à cette vente d'origine, par numéro croissant.
    / The CORRECTION sales linked to this original sale, by increasing number.
    """
    return list(
        Vente.objects.filter(
            nature=Vente.Nature.CORRECTION,
            vente_liee=vente_d_origine,
        ).order_by("numero")
    )


def nombre_de_ventes_de_correction():
    """
    Le nombre de ventes `CORRECTION` du lieu. Un test le lit avant et après son geste :
    l'écart est ce que le geste a écrit.
    / The number of CORRECTION sales of the venue, read before and after an action.
    """
    return Vente.objects.filter(nature=Vente.Nature.CORRECTION).count()


def photographie_de_la_vente(vente):
    """
    Ce qui ne change jamais sur une vente encaissée, relu en base : statut, numéro,
    empreinte, empreinte précédente, totaux, articles (leurs uuid) et règlements
    complets. Deux photographies égales = la vente n'a pas bougé.
    Le `payment_method` des lignes n'y est pas : la correction le change encore,
    pour les anciens rapports.
    / What never changes on a settled sale, read back. The lines' payment_method is
    not in it: the correction still changes it, for the old reports.
    """
    vente_relue = Vente.objects.get(pk=vente.pk)
    uuids_des_articles = []
    for article in vente_relue.articles.all():
        uuids_des_articles.append(str(article.uuid))
    return {
        "statut": vente_relue.statut,
        "numero": vente_relue.numero,
        "hmac_hash": vente_relue.hmac_hash,
        "previous_hmac": vente_relue.previous_hmac,
        "total_catalogue": vente_relue.total_catalogue,
        "total_offert": vente_relue.total_offert,
        "total_ttc": vente_relue.total_ttc,
        "total_ht": vente_relue.total_ht,
        "total_tva": vente_relue.total_tva,
        "articles": sorted(uuids_des_articles),
        "reglements": reglements_complets_de_la_vente(vente_relue),
    }


def anomalies_de_la_chaine_pour(vente):
    """
    Les anomalies que `verifier_chaine_ventes` signale pour CETTE vente (leurs
    raisons). La chaîne entière est parcourue, seules les anomalies de la vente sont
    gardées : la base est partagée.
    / The anomalies the chain check reports for THIS sale (their reasons).
    """
    cle_de_l_empreinte = LaboutikConfiguration.get_solo().get_or_create_hmac_key()
    raisons_pour_la_vente = []
    for anomalie in verifier_chaine_ventes(cle_de_l_empreinte):
        if anomalie["uuid"] == str(vente.uuid):
            raisons_pour_la_vente.append(anomalie["raison"])
    return raisons_pour_la_vente


def verifier_la_vente_de_correction(
    vente_de_correction, vente_d_origine, point_de_vente, operateur
):
    """
    Ce que toute vente `CORRECTION` de la caisse porte : réglée et numérotée, de la
    caisse, liée à la vente d'origine, au point de vente et à l'opérateur de la
    correction, sans article, et chaînée sans anomalie.
    / What every register CORRECTION sale carries: settled, numbered, linked, without
    items, chained without anomaly.
    """
    assert vente_de_correction.nature == Vente.Nature.CORRECTION
    assert vente_de_correction.statut == Vente.Statut.REGLEE
    assert vente_de_correction.numero is not None
    assert vente_de_correction.origine == SaleOrigin.LABOUTIK
    assert vente_de_correction.vente_liee_id == vente_d_origine.pk
    assert vente_de_correction.point_de_vente_id == point_de_vente.pk
    assert vente_de_correction.operateur_id == operateur.pk
    assert vente_de_correction.articles.count() == 0
    assert anomalies_de_la_chaine_pour(vente_de_correction) == []


# --------------------------------------------------------------------------
# 21 — Espèces corrigées en CB : une vente CORRECTION, l'origine inchangée
# / 21 — Cash corrected into bank card: one CORRECTION sale, the original unchanged
# --------------------------------------------------------------------------


def test_correction_moyen_nouvelle_vente_correction(lieu):
    """
    Trois jus à 3,50 € (TVA 20 %) payés en espèces : une vente réglée de 10,50 €,
    un règlement espèces de 1050. Le caissier corrige : c'était une CB.
    Ceinture : la ligne passe en CB, avec sa trace `CorrectionPaiement` (espèces → CB).
    Bretelles : une vente `CORRECTION`, réglée, liée à la vente d'origine, au point de
    vente et à l'opérateur de la correction, sans article, avec deux règlements :
    espèces −1050 et CB +1050 (somme 0).
    La vente d'origine ne change pas : mêmes règlements, même empreinte, et la
    vérification de la chaîne ne signale rien pour elle.
    / Three juices paid in cash (1050), corrected into bank card. The line becomes CB
    with its audit trail; a CORRECTION sale linked to the original, without items,
    payments CASH −1050 / CB +1050. The original sale is unchanged.
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([jus.produit])
    # L'administrateur est créé ici : le test compare l'opérateur de la correction à lui.
    # / Created here: the test compares the correction operator to this user.
    administrateur_du_lieu = creer_utilisateur(prenom="Admin", nom="Lieu")
    administrateur_du_lieu.client_admin.add(lieu.tenant)
    client_du_caissier = client_connecte(administrateur_du_lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse_du_paiement = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        jus,
        quantite=3,
        moyen_de_paiement="espece",
        autres_champs={"cle_idempotence_paiement": cle_d_idempotence},
    )
    assert reponse_du_paiement.status_code == 200
    vente_d_origine = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert reglements_de_la_vente(vente_d_origine) == [(PaymentMethod.CASH, 1050)]
    ligne_des_jus = seul_article_de_la_vente(vente_d_origine)
    vente_d_origine_avant_la_correction = photographie_de_la_vente(vente_d_origine)

    reponse = corriger_le_moyen_de_paiement(
        client_du_caissier, ligne_des_jus, PaymentMethod.CC
    )

    assert reponse.status_code == 200

    # Ceinture : la correction des lignes, comme aujourd'hui.
    # / Belt: the line correction, as today.
    ligne_des_jus.refresh_from_db()
    assert ligne_des_jus.payment_method == PaymentMethod.CC
    assert (
        CorrectionPaiement.objects.filter(
            ligne_article=ligne_des_jus,
            ancien_moyen=PaymentMethod.CASH,
            nouveau_moyen=PaymentMethod.CC,
        ).count()
        == 1
    )

    # Bretelles : une vente CORRECTION liée, deux règlements qui s'annulent.
    # / Braces: one linked CORRECTION sale, two payments that cancel out.
    ventes_de_correction = ventes_de_correction_liees_a(vente_d_origine)
    assert len(ventes_de_correction) == 1, (
        f"Attendu : une vente CORRECTION liée, trouvé : {len(ventes_de_correction)}."
    )
    vente_de_correction = ventes_de_correction[0]
    verifier_la_vente_de_correction(
        vente_de_correction, vente_d_origine, point_de_vente, administrateur_du_lieu
    )
    assert reglements_de_la_vente(vente_de_correction) == [
        (PaymentMethod.CASH, -1050),
        (PaymentMethod.CC, 1050),
    ]

    # La vente d'origine ne change jamais (D14).
    # / The original sale never changes.
    assert photographie_de_la_vente(vente_d_origine) == (
        vente_d_origine_avant_la_correction
    )
    assert anomalies_de_la_chaine_pour(vente_d_origine) == []

    verifier_egalites(vente_d_origine)
    verifier_egalites(vente_de_correction)


# 21b — Vente couverte par une clôture : test_lecteurs_montants_entiers.py (schéma dédié).
# / 21b — Sale covered by a closure: test_lecteurs_montants_entiers.py.


# --------------------------------------------------------------------------
# 21c — Carte + complément espèces : seule la part espèces est corrigée
# / 21c — Card + cash complement: only the cash part is corrected
# --------------------------------------------------------------------------


def test_correction_du_complement_especes_en_cb(lieu):
    """
    Trois jus à 3,50 € (10,50 €). La carte du client porte 5,00 € de monnaie locale :
    elle paie 5,00 €, le reste (5,50 €) est réglé en espèces. Le caissier corrige la
    part espèces : c'était une CB.
    Seule la part espèces passe en CB ; la part en monnaie locale ne bouge pas. La vente
    `CORRECTION` porte le montant de la part corrigée : espèces −550 et CB +550.
    La vente d'origine ne change pas : règlements espèces 550 et monnaie locale 500,
    même empreinte.
    / Three juices: 5.00 € on the card, 5.50 € in cash. The cash part is corrected into
    CB: only that part changes; the CORRECTION sale carries its amount (CASH −550 /
    CB +550). The original sale is unchanged.
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([jus.produit])
    carte_du_client = creer_une_carte_nfc_chargee(lieu, solde_en_centimes=500)
    # L'administrateur est créé ici : le test compare l'opérateur de la correction à lui.
    # / Created here: the test compares the correction operator to this user.
    administrateur_du_lieu = creer_utilisateur(prenom="Admin", nom="Lieu")
    administrateur_du_lieu.client_admin.add(lieu.tenant)
    client_du_caissier = client_connecte(administrateur_du_lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse_du_paiement = payer_le_reste_en_especes_ou_en_cb(
        client_du_caissier,
        point_de_vente,
        {f"repid-{cle_de_panier(jus)}": "3"},
        carte_du_client,
        moyen_du_reste="espece",
        cle_d_idempotence=cle_d_idempotence,
    )
    assert reponse_du_paiement.status_code == 200
    vente_d_origine = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert reglements_de_la_vente(vente_d_origine) == [
        (PaymentMethod.CASH, 550),
        (PaymentMethod.LOCAL_EURO, 500),
    ]
    articles_par_moyen = articles_de_la_vente_par_moyen(vente_d_origine)
    assert len(articles_par_moyen[PaymentMethod.CASH]) == 1
    assert len(articles_par_moyen[PaymentMethod.LOCAL_EURO]) == 1
    part_en_especes = articles_par_moyen[PaymentMethod.CASH][0]
    part_en_monnaie_locale = articles_par_moyen[PaymentMethod.LOCAL_EURO][0]
    assert part_en_especes.total_ttc == 550
    vente_d_origine_avant_la_correction = photographie_de_la_vente(vente_d_origine)

    reponse = corriger_le_moyen_de_paiement(
        client_du_caissier, part_en_especes, PaymentMethod.CC
    )

    assert reponse.status_code == 200

    # Ceinture : seule la part espèces est corrigée.
    # / Belt: only the cash part is corrected.
    part_en_especes.refresh_from_db()
    part_en_monnaie_locale.refresh_from_db()
    assert part_en_especes.payment_method == PaymentMethod.CC
    assert part_en_monnaie_locale.payment_method == PaymentMethod.LOCAL_EURO
    assert (
        CorrectionPaiement.objects.filter(ligne_article=part_en_especes).count() == 1
    )
    assert not CorrectionPaiement.objects.filter(
        ligne_article=part_en_monnaie_locale
    ).exists()

    # Bretelles : la vente CORRECTION porte le montant de la part corrigée.
    # / Braces: the CORRECTION sale carries the corrected part's amount.
    ventes_de_correction = ventes_de_correction_liees_a(vente_d_origine)
    assert len(ventes_de_correction) == 1, (
        f"Attendu : une vente CORRECTION liée, trouvé : {len(ventes_de_correction)}."
    )
    vente_de_correction = ventes_de_correction[0]
    verifier_la_vente_de_correction(
        vente_de_correction, vente_d_origine, point_de_vente, administrateur_du_lieu
    )
    assert reglements_de_la_vente(vente_de_correction) == [
        (PaymentMethod.CASH, -550),
        (PaymentMethod.CC, 550),
    ]

    # La vente d'origine ne change jamais (D14).
    # / The original sale never changes.
    assert photographie_de_la_vente(vente_d_origine) == (
        vente_d_origine_avant_la_correction
    )
    assert anomalies_de_la_chaine_pour(vente_d_origine) == []

    verifier_egalites(vente_d_origine)
    verifier_egalites(vente_de_correction)


# --------------------------------------------------------------------------
# 21d — Ligne écrite sans vente : refus, rien n'est écrit
# / 21d — Line written without a sale: refused, nothing is written
# --------------------------------------------------------------------------


def test_correction_d_une_ligne_sans_vente_refusee(lieu):
    """
    Une ligne de caisse écrite SANS vente, comme les lignes d'avant les ventes (base
    de dev seulement) : une bière à 5,00 € en espèces. Le caissier tente de la
    corriger en CB : refus (400). Seule une vente réglée, pas encore couverte par une
    clôture journalière, se corrige ; une ligne sans vente n'a ni numéro ni
    règlement. Rien n'est écrit : la ligne reste en espèces et sans vente, sans trace
    `CorrectionPaiement`, et aucune vente `CORRECTION` n'est créée.
    / A register line written WITHOUT a sale (dev database only): correcting it into
    CB is refused (400). Only a settled sale not yet covered by a daily closure is
    corrected. Nothing is written.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    produit_vendu = ProductSold.objects.create(product=biere.produit)
    tarif_vendu = PriceSold.objects.create(
        productsold=produit_vendu, price=biere.tarif, prix=Decimal("5.00")
    )
    ligne_sans_vente = LigneArticle.objects.create(
        pricesold=tarif_vendu,
        qty=1,
        amount=500,
        payment_method=PaymentMethod.CASH,
        status=LigneArticle.VALID,
        sale_origin=SaleOrigin.LABOUTIK,
        uuid_transaction=uuid.uuid4(),
        point_de_vente=point_de_vente,
    )
    assert ligne_sans_vente.vente_id is None
    nombre_de_corrections_avant = nombre_de_ventes_de_correction()

    reponse = corriger_le_moyen_de_paiement(
        client_du_caissier, ligne_sans_vente, PaymentMethod.CC
    )

    assert reponse.status_code == 400
    with translation.override(reponse["Content-Language"]):
        message_de_refus_attendu = translation.gettext(
            "Seule une vente réglée peut être corrigée."
        )
    assert message_de_refus_attendu in reponse.content.decode()
    ligne_sans_vente.refresh_from_db()
    assert ligne_sans_vente.payment_method == PaymentMethod.CASH
    assert ligne_sans_vente.vente_id is None
    assert not CorrectionPaiement.objects.filter(
        ligne_article=ligne_sans_vente
    ).exists()
    assert nombre_de_ventes_de_correction() == nombre_de_corrections_avant


# --------------------------------------------------------------------------
# 21e — Espèces → CB → chèque : deux ventes CORRECTION, liées à la vente d'origine
# / 21e — Cash → card → cheque: two CORRECTION sales, linked to the original
# --------------------------------------------------------------------------


def test_deux_corrections_successives_deux_ventes_correction(lieu):
    """
    Trois jus à 3,50 € payés en espèces (1050). Le caissier corrige en CB, puis se
    reprend : c'était un chèque. Deux corrections, deux ventes `CORRECTION`, chacune
    liée à la vente d'origine (jamais à la correction d'avant) :
    - la 1ʳᵉ : espèces −1050, CB +1050 ;
    - la 2ᵉ : CB −1050, chèque +1050.
    La ligne finit en chèque, avec deux traces de correction. La vente d'origine ne
    change pas.
    / Three juices paid in cash (1050), corrected into CB, then into cheque. Two
    CORRECTION sales, both linked to the original: CASH −1050 / CB +1050, then
    CB −1050 / CHEQUE +1050. The original sale is unchanged.
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([jus.produit])
    # L'administrateur est créé ici : le test compare l'opérateur des corrections à lui.
    # / Created here: the test compares the corrections' operator to this user.
    administrateur_du_lieu = creer_utilisateur(prenom="Admin", nom="Lieu")
    administrateur_du_lieu.client_admin.add(lieu.tenant)
    client_du_caissier = client_connecte(administrateur_du_lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse_du_paiement = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        jus,
        quantite=3,
        moyen_de_paiement="espece",
        autres_champs={"cle_idempotence_paiement": cle_d_idempotence},
    )
    assert reponse_du_paiement.status_code == 200
    vente_d_origine = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    ligne_des_jus = seul_article_de_la_vente(vente_d_origine)
    vente_d_origine_avant_les_corrections = photographie_de_la_vente(vente_d_origine)

    reponse_de_la_premiere_correction = corriger_le_moyen_de_paiement(
        client_du_caissier, ligne_des_jus, PaymentMethod.CC
    )
    reponse_de_la_seconde_correction = corriger_le_moyen_de_paiement(
        client_du_caissier, ligne_des_jus, PaymentMethod.CHEQUE
    )

    assert reponse_de_la_premiere_correction.status_code == 200
    assert reponse_de_la_seconde_correction.status_code == 200

    # Ceinture : la ligne finit en chèque, avec une trace par correction.
    # / Belt: the line ends as cheque, with one trail per correction.
    ligne_des_jus.refresh_from_db()
    assert ligne_des_jus.payment_method == PaymentMethod.CHEQUE
    traces_de_la_ligne = []
    for trace in CorrectionPaiement.objects.filter(ligne_article=ligne_des_jus):
        traces_de_la_ligne.append((trace.ancien_moyen, trace.nouveau_moyen))
    assert sorted(traces_de_la_ligne) == [
        (PaymentMethod.CASH, PaymentMethod.CC),
        (PaymentMethod.CC, PaymentMethod.CHEQUE),
    ]

    # Bretelles : deux ventes CORRECTION, chacune liée à la vente d'origine.
    # / Braces: two CORRECTION sales, each linked to the original sale.
    ventes_de_correction = ventes_de_correction_liees_a(vente_d_origine)
    assert len(ventes_de_correction) == 2, (
        f"Attendu : deux ventes CORRECTION liées, trouvé : {len(ventes_de_correction)}."
    )
    premiere_correction = ventes_de_correction[0]
    seconde_correction = ventes_de_correction[1]
    for vente_de_correction in ventes_de_correction:
        verifier_la_vente_de_correction(
            vente_de_correction,
            vente_d_origine,
            point_de_vente,
            administrateur_du_lieu,
        )
    assert reglements_de_la_vente(premiere_correction) == [
        (PaymentMethod.CASH, -1050),
        (PaymentMethod.CC, 1050),
    ]
    assert reglements_de_la_vente(seconde_correction) == [
        (PaymentMethod.CC, -1050),
        (PaymentMethod.CHEQUE, 1050),
    ]

    # La vente d'origine ne change jamais (D14).
    # / The original sale never changes.
    assert photographie_de_la_vente(vente_d_origine) == (
        vente_d_origine_avant_les_corrections
    )
    assert anomalies_de_la_chaine_pour(vente_d_origine) == []

    verifier_egalites(vente_d_origine)
    verifier_egalites(premiere_correction)
    verifier_egalites(seconde_correction)


# --------------------------------------------------------------------------
# 21f — Lignes de deux ventes au même identifiant de paiement : seule la vente
# de la ligne cliquée est corrigée
# / 21f — Lines of two sales sharing a payment id: only the clicked line's sale
# --------------------------------------------------------------------------


def test_correction_de_lignes_de_deux_ventes_ne_touche_que_la_vente_cliquee(lieu):
    """
    Une correction porte sur les lignes de la MÊME VENTE qui ont le même moyen
    (`lignes_que_la_correction_deplace`), jamais sur un identifiant de paiement. Ce
    test fabrique deux bières payées en espèces dans deux ventes, puis la ligne de la
    2ᵉ vente reçoit l'identifiant de paiement de la 1ʳᵉ (par `.update()`, qui ne passe
    pas par la garde). Corriger la 1ʳᵉ ligne en CB ne touche que la 1ʳᵉ vente : sa
    ligne passe en CB, une vente CORRECTION de 500 lui est liée ; la ligne de la 2ᵉ
    vente reste en espèces, sans trace de correction.
    / Two cash sales whose lines share one payment id: the correction only moves
    the clicked line's sale.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_de_la_premiere_vente = nouvelle_cle_d_idempotence()
    cle_de_la_seconde_vente = nouvelle_cle_d_idempotence()
    for cle_d_idempotence in (cle_de_la_premiere_vente, cle_de_la_seconde_vente):
        reponse_du_paiement = payer_a_la_caisse(
            client_du_caissier,
            point_de_vente,
            biere,
            quantite=1,
            moyen_de_paiement="espece",
            autres_champs={"cle_idempotence_paiement": cle_d_idempotence},
        )
        assert reponse_du_paiement.status_code == 200
    premiere_vente = retrouver_la_vente_de_la_cle(cle_de_la_premiere_vente)
    seconde_vente = retrouver_la_vente_de_la_cle(cle_de_la_seconde_vente)
    ligne_de_la_premiere_vente = seul_article_de_la_vente(premiere_vente)
    ligne_de_la_seconde_vente = seul_article_de_la_vente(seconde_vente)
    LigneArticle.objects.filter(pk=ligne_de_la_seconde_vente.pk).update(
        uuid_transaction=ligne_de_la_premiere_vente.uuid_transaction
    )
    reponse = corriger_le_moyen_de_paiement(
        client_du_caissier, ligne_de_la_premiere_vente, PaymentMethod.CC
    )

    assert reponse.status_code == 200
    ligne_de_la_premiere_vente.refresh_from_db()
    ligne_de_la_seconde_vente.refresh_from_db()
    assert ligne_de_la_premiere_vente.payment_method == PaymentMethod.CC
    assert ligne_de_la_seconde_vente.payment_method == PaymentMethod.CASH
    assert not CorrectionPaiement.objects.filter(
        ligne_article=ligne_de_la_seconde_vente
    ).exists()
    vente_de_correction = Vente.objects.get(
        nature=Vente.Nature.CORRECTION, vente_liee=premiere_vente
    )
    montants_par_moyen = {}
    reglements_de_la_correction = vente_de_correction.reglements.all()
    for reglement in reglements_de_la_correction:
        montants_par_moyen[reglement.moyen] = reglement.montant
    assert montants_par_moyen == {PaymentMethod.CASH: -500, PaymentMethod.CC: 500}
    assert not Vente.objects.filter(
        nature=Vente.Nature.CORRECTION, vente_liee=seconde_vente
    ).exists()


# --------------------------------------------------------------------------
# 21g — Deux articles du même paiement : le montant est la somme des lignes
# / 21g — Two items of one payment: the amount is the sum of the lines
# --------------------------------------------------------------------------


def test_correction_de_deux_lignes_montant_egal_a_leur_somme(lieu):
    """
    Une bière à 5,00 € et un jus à 3,50 €, payés ensemble en espèces : deux lignes du
    même paiement, 8,50 €. Le caissier corrige la ligne du jus en CB : la correction
    porte sur les deux lignes (même paiement, même moyen), comme aujourd'hui. La vente
    `CORRECTION` porte la somme des deux lignes : espèces −850 et CB +850, jamais le
    montant d'une seule ligne.
    / A beer and a juice paid together in cash (850). Correcting one line corrects
    both; the CORRECTION sale carries their sum: CASH −850 / CB +850.
    """
    biere = creer_un_article_de_caisse("biere", prix_en_euros="5.00", taux_tva="20.00")
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([biere.produit, jus.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse_du_paiement = payer_un_panier_compose_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        {
            f"repid-{cle_de_panier(biere)}": "1",
            f"repid-{cle_de_panier(jus)}": "1",
        },
        moyen_de_paiement="espece",
        cle_d_idempotence=cle_d_idempotence,
    )
    assert reponse_du_paiement.status_code == 200
    vente_d_origine = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert reglements_de_la_vente(vente_d_origine) == [(PaymentMethod.CASH, 850)]
    ligne_du_jus = LigneArticle.objects.get(pricesold__price=jus.tarif)
    ligne_de_la_biere = LigneArticle.objects.get(pricesold__price=biere.tarif)

    reponse = corriger_le_moyen_de_paiement(
        client_du_caissier, ligne_du_jus, PaymentMethod.CC
    )

    assert reponse.status_code == 200
    for ligne in (ligne_du_jus, ligne_de_la_biere):
        ligne.refresh_from_db()
        assert ligne.payment_method == PaymentMethod.CC
    ventes_de_correction = ventes_de_correction_liees_a(vente_d_origine)
    assert len(ventes_de_correction) == 1, (
        f"Attendu : une vente CORRECTION liée, trouvé : {len(ventes_de_correction)}."
    )
    vente_de_correction = ventes_de_correction[0]
    assert reglements_de_la_vente(vente_de_correction) == [
        (PaymentMethod.CASH, -850),
        (PaymentMethod.CC, 850),
    ]
    verifier_egalites(vente_d_origine)
    verifier_egalites(vente_de_correction)


# --------------------------------------------------------------------------
# 21h — La vente de correction échoue : la correction des lignes est annulée aussi
# / 21h — The correction sale fails: the line correction is rolled back too
# --------------------------------------------------------------------------


def test_correction_vente_de_correction_en_echec_rien_n_est_ecrit(lieu):
    """
    Trois jus payés en espèces, corrigés en CB. L'encaissement de la vente
    `CORRECTION` échoue (simulé : `encaisser_vente` lève `EgaliteDeVenteRompue`).
    La vente de correction et la correction des lignes sont dans la même transaction :
    tout est annulé. La ligne reste en espèces, sans trace de correction, et aucune
    vente `CORRECTION` n'existe.
    / The CORRECTION sale fails to settle (simulated): the line correction is in the
    same transaction and is rolled back too.
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([jus.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse_du_paiement = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        jus,
        quantite=3,
        moyen_de_paiement="espece",
        autres_champs={"cle_idempotence_paiement": cle_d_idempotence},
    )
    assert reponse_du_paiement.status_code == 200
    vente_d_origine = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    ligne_des_jus = seul_article_de_la_vente(vente_d_origine)
    nombre_de_corrections_avant = nombre_de_ventes_de_correction()

    # Le client de test relance l'exception de la vue : on l'attend ici.
    # / The test client re-raises the view's exception: it is expected here.
    with patch(
        "laboutik.views.encaisser_vente",
        side_effect=EgaliteDeVenteRompue("échec simulé"),
    ):
        with pytest.raises(EgaliteDeVenteRompue):
            corriger_le_moyen_de_paiement(
                client_du_caissier, ligne_des_jus, PaymentMethod.CC
            )

    ligne_des_jus.refresh_from_db()
    assert ligne_des_jus.payment_method == PaymentMethod.CASH
    assert not CorrectionPaiement.objects.filter(ligne_article=ligne_des_jus).exists()
    assert nombre_de_ventes_de_correction() == nombre_de_corrections_avant


# --------------------------------------------------------------------------
# 21h — Lignes d'argent dont le montant total est nul : refus propre
# / 21h — Money lines whose total amount is zero: clean refusal
# --------------------------------------------------------------------------


def test_correction_de_lignes_au_montant_nul_refusee_rien_n_est_ecrit(lieu):
    """
    Un article à 0,00 € payé en espèces, par la vraie route de paiement : une vente
    réglée sans règlement, une ligne en espèces dont le net vendu (`total_ttc`) vaut 0.
    L'écran ne propose que « Valider » (offert) pour un panier gratuit, mais `payer()`
    ne confronte jamais le moyen reçu à la liste proposée : un POST « espece » passe.
    Le caissier corrige cette ligne en CB : il n'y a rien à corriger. Refus propre
    (400, message clair en français), jamais une erreur 500. Rien n'est écrit : la
    ligne reste en espèces, sans trace `CorrectionPaiement`, aucune vente `CORRECTION`.
    / A 0.00 € item paid in cash through the real route: a money line whose net total
    is 0. Correcting it into bank card is cleanly refused (400, clear French message),
    never a 500. Nothing written.
    """
    article_gratuit = creer_un_article_de_caisse(
        "gratuit", prix_en_euros="0.00", taux_tva="20.00"
    )
    point_de_vente = creer_un_point_de_vente([article_gratuit.produit])
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    # Le message du refus est lu en français : une traduction anglaise le changerait.
    # / The refusal message is read in French: an English translation would change it.
    client_du_caissier.defaults["HTTP_ACCEPT_LANGUAGE"] = "fr"
    cle_d_idempotence = nouvelle_cle_d_idempotence()

    reponse_du_paiement = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        article_gratuit,
        quantite=1,
        moyen_de_paiement="espece",
        autres_champs={"cle_idempotence_paiement": cle_d_idempotence},
    )
    assert reponse_du_paiement.status_code == 200
    vente_d_origine = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    ligne_gratuite = seul_article_de_la_vente(vente_d_origine)
    # L'état de départ : une ligne d'ARGENT (espèces) au net vendu nul.
    # / Starting state: a MONEY line (cash) with a zero net total.
    assert ligne_gratuite.payment_method == PaymentMethod.CASH
    assert ligne_gratuite.total_ttc == 0
    nombre_de_corrections_avant = nombre_de_ventes_de_correction()

    reponse = corriger_le_moyen_de_paiement(
        client_du_caissier, ligne_gratuite, PaymentMethod.CC
    )

    assert reponse.status_code == 400
    texte_de_la_reponse = html.unescape(reponse.content.decode()).lower()
    assert "rien à corriger : le montant est nul" in texte_de_la_reponse

    # Rien n'est écrit.
    # / Nothing is written.
    ligne_gratuite.refresh_from_db()
    assert ligne_gratuite.payment_method == PaymentMethod.CASH
    assert not CorrectionPaiement.objects.filter(ligne_article=ligne_gratuite).exists()
    assert nombre_de_ventes_de_correction() == nombre_de_corrections_avant
    assert ventes_de_correction_liees_a(vente_d_origine) == []
