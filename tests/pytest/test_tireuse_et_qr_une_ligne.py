"""
La tireuse et le paiement QR / NFC écrivent UNE ligne par article. Quand l'argent
réellement débité diffère du prix de l'article, la différence devient un article
« Écart d'encaissement » (D15, D26).
/ The tap and the QR / NFC payment write ONE line per item. When the money really
debited differs from the item's price, the difference becomes a "collection gap" item.

LOCALISATION : tests/pytest/test_tireuse_et_qr_une_ligne.py

RÈGLES MÉTIER TESTÉES
Tireuse (D15) :
- un tirage = UNE ligne, quel que soit le nombre de monnaies débitées ;
- `qty` = les litres facturés (volume en ml / 1000, arrondi à 3 décimales D'ABORD),
  `amount` = le prix au litre en centimes, total = la formule (prix × quantité, arrondi
  demi-haut), calculé une seule fois sur la quantité arrondie ;
- l'écran de la tireuse, la facture et la ligne donnent le même centime ;
- la part payée en jetons cadeau (moyen LG) va dans `part_en_jetons` ;
- le coût d'achat porte sur les litres facturés ;
- le volume facturé est le plus petit du volume servi et du volume autorisé au badge
  (arrondi vers le bas au ml, Q-H13) : le débordement n'est pas facturé, le stock
  baisse du volume réellement servi ;
- le filet : si l'ancien Fedow échoue après le badge, la ligne garde son prix et ce
  qui manque devient un article « Écart d'encaissement — reçu en moins » (D26).
QR / NFC en ligne :
- un paiement = UNE ligne : `qty` 1, `amount` = le montant demandé, le tarif vendu de la
  demande, l'uuid de la demande (l'écran de l'encaisseur, `check_payment`, interroge cet
  uuid), les métadonnées recopiées ;
- un règlement par transaction de l'ancien Fedow ;
- Fedow débite moins (ou plus) que demandé : la ligne garde le montant demandé, et la
  différence devient un article d'écart « reçu en moins » (ou « reçu en plus ») ;
- les deux mails portent l'argent réellement débité.
Colonnes vides (Q-H2) : les lignes payées de la tireuse et du QR / NFC ne remplissent
pas le moyen (`payment_method`), la monnaie (`asset`), la carte ni le portefeuille. La
ligne de DEMANDE d'un QR code non payé (sans vente) reste telle quelle.
Aucune part : `_calculer_qty_partielles` n'existe pas dans le code de production.
Lecteurs (tests 11 à 18) : un tirage s'affiche en litres (caisse, ticket, Z, admin) et
compte pour UN article, même sous 5 ml ; un écart n'est pas un article ; un écart payé
en cashless n'est pas de l'argent dans la réconciliation ; l'avoir d'une ligne QR
s'écrit (métadonnées en dictionnaire, en texte JSON pour une ligne historique, ou en
texte vide ou blanc) ; la page du payeur QR affiche l'argent débité.
Volume autorisé au badge (test 19) : il lit le prix au litre arrondi comme celui de la
ligne (demi-haut), la facture de ce volume ne dépasse jamais le solde.
/ Tap: one line, litres × price per litre (quantity rounded first), screen = bill =
line, token part, cost on litres, authorised volume billed (overflow free), missing
money after an old Fedow failure → "received less" gap item. QR / NFC:
one line at the requested amount with the request uuid, one payment per remote
transaction, gap item on partial or over debit, mails at the debited amount. Empty
method / currency / card / wallet columns. No more parts.

D'OÙ VIENNENT LES VALEURS ATTENDUES (calculées à la main)
- 500 ml à 6 €/L : 0,500 × 600 = 300 ; coût 0,500 × 300 = 150 ; HT 250, TVA 50 ;
- 500 ml à 8 €/L : 0,500 × 800 = 400 ; HT arrondi(400 × 100 / 120 = 333,33) = 333 ;
  jetons 100 : HT = 100 + arrondi(300 × 100 / 120 = 250) = 350, TVA 50 ;
- 200 de solde à 6 €/L : 333,33 ml autorisés → 333 ml ; 0,333 × 600 = 199,8 → 200 ;
- 300 de solde à 6 €/L : 500 ml autorisés ; 530 ml servis → 0,500 L, 300, stock −53 cl ;
- 3,505 €/L : 350,5 → 351 c/L (demi-haut) ; 351 de solde → 1000 ml (au pair, 350 c/L :
  1002 ml, facturés 352) ;
- 333,7 ml à 7,50 €/L : la quantité d'abord, 0,3337 → 0,334 L ; 0,334 × 750 = 250,5 →
  251. (Sans arrondir la quantité : 0,3337 × 750 = 250,275 → 250.)
- QR 1000 débité 800 : ligne 1000, écart −200 ; débité 1100 : ligne 1000, écart +100.
/ Hand-computed values.

COMMENT CHAQUE TEST RETROUVE SA VENTE
La base est partagée avec le serveur de dev. Un tirage retrouve sa vente par la carte
que le test a créée (`Vente.carte`) ; un paiement QR / NFC, par l'uuid de sa demande
(la ligne payée garde cet uuid). Chaque test qui lit une vente finit par
`verifier_egalites(vente)` (tests/pytest/fabriques_vente.py).
/ A pour finds its sale through the test's card; a QR / NFC payment through its request
uuid. Each test ends with verifier_egalites(vente).

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin
(tests/PIEGES.md 13.1), rien ne reste en base de dev. Les mails partent après la
validation en base (`transaction.on_commit`) : les tests qui les lisent passent par
`django_capture_on_commit_callbacks(execute=True)`.
- Tireuse : les vraies routes (`authorize`, `event` `pour_update` / `pour_end`), avec la
  clé API du terminal de la tireuse. Les fabriques viennent de
  test_tireuse_ecrit_la_vente.py ; l'ancien Fedow simulé (test 2) vient de
  test_tireuse_ancien_fedow.py. Les cartes sans utilisateur ne lisent jamais l'ancien
  Fedow : aucun appel réseau.
- QR / NFC : l'ancien Fedow est simulé (`fedow_connect.fedow_api.FedowAPI` pour la
  confirmation, la vue l'importe DANS la méthode ; `BaseBillet.validators.FedowAPI` pour
  la lecture de carte). Celery est simulé (`taches_celery_enregistrees`) : on lit le nom
  et les arguments des tâches, rien ne part au worker.
- Tout envoi HTTP réel du client de l'ancien Fedow (`_get`, `_post`) fait échouer le
  test.
/ Rolled back per test. Real tap routes. Old Fedow and Celery faked; any real HTTP call
to the old Fedow fails the test.

CODE PARCOURU / CODE EXERCISED
- controlvanne/billing.py — calculer_montant_centimes, facturer_tirage ;
- controlvanne/viewsets.py — authorize, event, _construire_payload_session ;
- BaseBillet/views.py — QrCodeScanPay.generate_qrcode, valid_payment, process_with_nfc,
  check_payment, _ecrire_la_vente_payee ;
- BaseBillet/services_vente.py — ajouter_article, ajouter_l_article_d_ecart_d_encaissement,
  encaisser_vente.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-H-retrait.md (§2, §2.1,
§5 tests 4 et 5b) ; CHANTIER-05-montants-entiers.md (D15, D26) ;
CHANTIER-05-C-tireuse-qr.md (§1, §1 bis) ; CHANTIER-05-SUIVI.md (§5 Q-H2, Q-H3,
Q-H13) ; brief CHANTIER-05-briefs/05-H-1-ter.md (tests 5 et 6).

Lancer / Run : make test ARGS="tests/pytest/test_tireuse_et_qr_une_ligne.py"
"""

import json
import logging
import os
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from django.test import Client as ClientHttpDjango
from django_tenants.utils import tenant_context

from fabriques_panier import (
    client_connecte,
    configuration_modifiee,
    taches_celery_enregistrees,
)
from fabriques_vente import verifier_egalites
from test_caisse_une_ligne_par_article import (
    DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE,
    quantite_et_unite,
    rapport_de_l_instant_de_la_vente,
    texte_normalise,
    textes_des_cellules,
)
from test_caracterisation_en_ligne import (
    arguments_des_taches,
    creer_un_administrateur_du_lieu,
)
from test_caracterisation_qr import creer_un_encaisseur, creer_un_payeur, fedow_simule
from test_tireuse_ancien_fedow import (
    AncienFedowSimule,
    simuler_l_ancien_fedow,
    transaction_distante,
)
from test_tireuse_ecrit_la_vente import (
    DOMAINE_DU_LIEU_PARTAGE,
    _creer_une_carte,
    _creer_une_tireuse,
    _debits_de_la_carte,
    _la_vente_du_tirage,
    _monnaie_du_lieu,
    _poster,
    _servir_un_tirage,
)

pytestmark = pytest.mark.django_db

# Adresses du paiement par QR code (BaseBillet/urls.py).
# / QR code payment addresses.
URL_DE_LA_GENERATION_DU_QRCODE = "/qrcodescanpay/generate_qrcode/"
URL_DE_LA_CONFIRMATION_DU_PAIEMENT = "/qrcodescanpay/valid_payment/"
URL_DE_LA_LECTURE_DE_CARTE = "/qrcodescanpay/process_with_nfc/"


# ---------------------------------------------------------------------------
# Garde-fous communs
# / Common guards
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def aucun_envoi_reel_vers_l_ancien_fedow():
    """
    Pendant chaque test, les envois HTTP du client de l'ancien Fedow (`_get`, `_post`)
    échouent, et la liste des envois tentés doit être vide à la fin du test. Un test
    qui oublie de simuler l'ancien Fedow tombe au lieu de débiter une vraie carte.
    / Every real HTTP call of the old Fedow client fails, and none may be attempted.
    """
    envois_reseau_tentes = []

    def envoi_reseau_interdit(*arguments, **arguments_nommes):
        envois_reseau_tentes.append((arguments, arguments_nommes))
        raise AssertionError(
            "Appel réseau réel vers l'ancien Fedow interdit dans un test pytest."
        )

    with mock.patch("fedow_connect.fedow_api._post", side_effect=envoi_reseau_interdit):
        with mock.patch(
            "fedow_connect.fedow_api._get", side_effect=envoi_reseau_interdit
        ):
            yield

    assert envois_reseau_tentes == [], (
        f"Envois réseau réels tentés vers l'ancien Fedow : {envois_reseau_tentes}"
    )


@pytest.fixture(autouse=True)
def langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, avec Celery simulé pendant tout le test.
    / The `lespass` venue, with Celery faked for the whole test.

    `taches_demandees` se remplit au fil du test : une paire (nom court, arguments) par
    tâche demandée.
    / `taches_demandees` fills up during the test: one (short name, args) per task.
    """
    with tenant_context(tenant):
        with taches_celery_enregistrees() as taches_demandees:
            yield SimpleNamespace(tenant=tenant, taches_demandees=taches_demandees)


# ---------------------------------------------------------------------------
# Lecture des articles d'une vente
# / Reading the items of a sale
# ---------------------------------------------------------------------------


def champ_vide(valeur):
    """
    Vrai si un champ de la ligne est vide : None ou texte vide.
    / True when a line field is empty: None or an empty text.
    """
    return valeur is None or valeur == ""


def noms_des_produits_d_ecart():
    """Les noms des deux produits système « Écart d'encaissement ».
    / Names of the two "collection gap" system products."""
    from BaseBillet.services_vente import (
        NOM_ECART_RECU_EN_MOINS,
        NOM_ECART_RECU_EN_PLUS,
    )

    return [NOM_ECART_RECU_EN_PLUS, NOM_ECART_RECU_EN_MOINS]


def articles_hors_ecart(vente):
    """
    Les articles vendus de la vente, sans les articles d'écart d'encaissement.
    / The sale's sold items, without the collection gap items.
    """
    return list(
        vente.articles.exclude(
            pricesold__productsold__product__name__in=noms_des_produits_d_ecart()
        )
    )


def articles_d_ecart(vente):
    """
    Les articles « Écart d'encaissement » de la vente (reçu en plus ou en moins).
    / The sale's "collection gap" items.
    """
    return list(
        vente.articles.filter(
            pricesold__productsold__product__name__in=noms_des_produits_d_ecart()
        )
    )


def le_seul_article_hors_ecart(vente):
    """
    L'article vendu de la vente : il doit y en avoir un et un seul.
    / The sale's sold item: exactly one.
    """
    articles = articles_hors_ecart(vente)
    assert len(articles) == 1, (
        f"Une ligne et une seule attendue, trouvée(s) : {len(articles)} "
        f"(quantités : {[article.qty for article in articles]})."
    )
    return articles[0]


def metadonnees_lues(ligne):
    """
    Les métadonnées d'une ligne, en dictionnaire. La vue les écrit en texte JSON dans
    un `JSONField` : on relit le texte si besoin.
    / A line's metadata as a dict (the view writes JSON text into a JSONField).
    """
    metadonnees = ligne.metadata
    if isinstance(metadonnees, str):
        metadonnees = json.loads(metadonnees)
    return metadonnees or {}


# ---------------------------------------------------------------------------
# Le paiement QR / NFC
# / The QR / NFC payment
# ---------------------------------------------------------------------------


def generer_une_demande(client_de_l_encaisseur, montant_en_centimes):
    """
    L'encaisseur génère un QR code de ce montant, en euros. Rend la demande (ligne « en
    attente »), retrouvée par l'uuid lu dans la page rendue.
    / The collector generates a QR code of this amount; returns the pending request.
    """
    from BaseBillet.models import LigneArticle

    reponse = client_de_l_encaisseur.post(
        URL_DE_LA_GENERATION_DU_QRCODE,
        {"amount": str(montant_en_centimes / 100), "asset_type": "EUR"},
    )
    assert reponse.status_code == 200, reponse.content.decode()[:400]
    uuid_de_la_demande = reponse.context["ligne_article_uuid_hex"]
    return LigneArticle.objects.get(uuid=uuid.UUID(uuid_de_la_demande))


def transaction_de_l_ancien_fedow(montant_en_centimes):
    """
    Une transaction telle que la rend le débit de l'ancien Fedow, et l'uuid (texte) de
    sa monnaie : `({"uuid", "asset", "amount"}, uuid de la monnaie)`.
    / A transaction as returned by the old Fedow debit, and its currency uuid (text).
    """
    uuid_de_la_monnaie = str(uuid.uuid4())
    transaction = {
        "uuid": uuid.uuid4(),
        "asset": uuid_de_la_monnaie,
        "amount": montant_en_centimes,
    }
    return transaction, uuid_de_la_monnaie


def confirmer_par_qrcode(payeur, demande, faux_fedow):
    """
    L'adhérent confirme le paiement du QR code depuis son téléphone (`valid_payment`).
    / The member confirms the QR code payment from their phone.
    """
    with mock.patch("fedow_connect.fedow_api.FedowAPI", return_value=faux_fedow):
        reponse = client_connecte(payeur).post(
            URL_DE_LA_CONFIRMATION_DU_PAIEMENT,
            {"ligne_article_uuid_hex": demande.uuid.hex},
        )
    assert reponse.status_code == 200, reponse.content.decode()[:400]
    return reponse


def payer_par_lecture_de_carte(client_de_l_encaisseur, payeur, demande, faux_fedow):
    """
    Le lecteur de l'encaisseur lit la carte de l'adhérent (`process_with_nfc`). La carte
    est rattachée au portefeuille du payeur sur l'ancien Fedow (simulé).
    / The collector's reader reads the member's card (`process_with_nfc`).
    """
    faux_fedow.NFCcard.card_tag_id_retrieve.return_value = {
        "wallet_uuid": str(payeur.wallet.uuid),
        "is_wallet_ephemere": False,
    }
    tag_de_la_carte = uuid.uuid4().hex[:8].upper()
    with mock.patch("BaseBillet.validators.FedowAPI", return_value=faux_fedow):
        reponse = client_de_l_encaisseur.post(
            URL_DE_LA_LECTURE_DE_CARTE,
            {"tagSerial": tag_de_la_carte, "ligne_article_uuid_hex": demande.uuid.hex},
        )
    assert reponse.status_code == 202, reponse.content.decode()[:400]
    return reponse


def creer_un_payeur_avec_portefeuille():
    """
    Un adhérent qui paie, adresse confirmée, avec un portefeuille local : la lecture de
    carte retrouve l'adhérent par ce portefeuille.
    / A paying member with a local wallet: the card read finds the member through it.
    """
    from AuthBillet.models import Wallet

    payeur = creer_un_payeur()
    payeur.wallet = Wallet.objects.create(
        name=f"TEST portefeuille QR une ligne {uuid.uuid4().hex[:8]}"
    )
    payeur.save()
    return payeur


def la_vente_de_la_demande(demande):
    """
    La vente du paiement : celle de la ligne qui garde l'uuid de la demande.
    / The payment's sale: the one of the line keeping the request uuid.
    """
    from BaseBillet.models import LigneArticle

    ligne_payee = LigneArticle.objects.get(uuid=demande.uuid)
    assert ligne_payee.vente_id is not None, "La demande payée n'a pas de vente."
    return ligne_payee.vente


# ---------------------------------------------------------------------------
# 1 — Tireuse : une ligne en litres, au prix du litre
# / 1 — Tap: one line in litres, at the price per litre
# ---------------------------------------------------------------------------


def test_tireuse_une_ligne_litres_prix_au_litre(tenant):
    """
    500 ml à 6 €/L (fût acheté 3 € le litre), payés en monnaie locale (TLF) :
    - UNE ligne : `qty` 0,500 (litres servis), `amount` 600 (prix au litre), total
      catalogue 300 = net = le débit ; HT 250, TVA 50 ;
    - coût d'achat sur les litres servis : 0,500 × 300 = 150 ;
    - le poids pour le stock reste en centilitres (50) ;
    - un règlement de 300, copié du débit.
    / 500 ml at 6 €/L: one line, qty 0.500, amount 600, total 300 = debit; cost on
    0.500 L.
    """
    from BaseBillet.models import PaymentMethod, SaleOrigin
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(
        tenant, prix_du_litre_en_euros="6.00", prix_achat_du_litre_en_centimes=300
    )
    carte, _portefeuille = _creer_une_carte(tenant, [(monnaie_locale, 1000)])

    _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "500.00",
    )

    with tenant_context(tenant):
        vente = _la_vente_du_tirage(carte)
        assert articles_d_ecart(vente) == []

        lignes = list(vente.articles.all())
        assert len(lignes) == 1
        ligne = lignes[0]
        assert ligne.qty == Decimal("0.500")
        assert ligne.amount == 600
        assert ligne.total_catalogue == 300
        assert ligne.part_offerte == 0
        assert ligne.part_en_jetons == 0
        assert ligne.total_ttc == 300
        assert ligne.total_ht == 250
        assert ligne.total_tva == 50
        assert ligne.cout_achat == 150
        assert ligne.weight_quantity == 50
        assert ligne.sale_origin == SaleOrigin.TIREUSE

        debits = _debits_de_la_carte(carte)
        assert len(debits) == 1
        assert debits[0].amount == 300
        assert ligne.total_ttc == debits[0].amount

        reglement = vente.reglements.get()
        assert reglement.moyen == PaymentMethod.LOCAL_EURO
        assert reglement.montant == 300
        assert reglement.fedow_transaction_uuid == debits[0].uuid
        assert vente.total_ttc == 300

        verifier_egalites(vente)


# ---------------------------------------------------------------------------
# 2 — Tireuse : monnaie locale puis ancien Fedow, toujours une ligne
# / 2 — Tap: local currency then old Fedow, still one line
# ---------------------------------------------------------------------------


def test_tireuse_monnaie_locale_et_ancien_fedow_une_ligne(tenant):
    """
    500 ml à 8 €/L = 400, par une carte reliée à un utilisateur : 100 en monnaie locale
    (TLF du lieu), puis le reste (300) sur l'ancien Fedow (TLF fédérés).
    - UNE ligne : `qty` 0,500, `amount` 800, total 400, HT 333, TVA 67 ;
    - DEUX règlements : monnaie locale 100 (uuid de la transaction locale), et ancien
      Fedow 300 (uuid de la transaction distante dans `reference_externe`).
    / 400 = 100 local + 300 old Fedow: one line, two payments.
    """
    from BaseBillet.models import PaymentMethod
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, _portefeuille = _creer_une_carte(
        tenant, [(monnaie_locale, 100)], avec_un_utilisateur=True
    )

    transaction_en_tlf_federes = transaction_distante(PaymentMethod.LOCAL_EURO, 300)
    ancien_fedow = AncienFedowSimule(
        solde_en_centimes=1000,
        transactions_rendues=[transaction_en_tlf_federes],
    )
    lecture_simulee, debit_simule = simuler_l_ancien_fedow(ancien_fedow)
    with lecture_simulee, debit_simule:
        _servir_un_tirage(
            ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
            entetes_http,
            tireuse,
            carte,
            "500.00",
        )

    assert len(ancien_fedow.debits) == 1
    _utilisateur, montant_demande_a_l_ancien_fedow, _uuid = ancien_fedow.debits[0]
    assert montant_demande_a_l_ancien_fedow == 300

    with tenant_context(tenant):
        vente = _la_vente_du_tirage(carte)
        assert articles_d_ecart(vente) == []

        ligne = le_seul_article_hors_ecart(vente)
        assert vente.articles.count() == 1
        assert ligne.qty == Decimal("0.500")
        assert ligne.amount == 800
        assert ligne.total_catalogue == 400
        assert ligne.total_ttc == 400
        assert ligne.total_ht == 333
        assert ligne.total_tva == 67

        debits_locaux = _debits_de_la_carte(carte)
        assert len(debits_locaux) == 1

        reglements = list(vente.reglements.all())
        assert len(reglements) == 2
        reglements_lus = []
        for reglement in reglements:
            reglements_lus.append(
                (
                    reglement.moyen,
                    reglement.montant,
                    reglement.fedow_transaction_uuid,
                    reglement.reference_externe or "",
                )
            )
        reglements_attendus = [
            (PaymentMethod.LOCAL_EURO, 100, debits_locaux[0].uuid, ""),
            (
                PaymentMethod.LOCAL_EURO,
                300,
                None,
                transaction_en_tlf_federes[3],
            ),
        ]
        assert sorted(reglements_lus, key=str) == sorted(reglements_attendus, key=str)

        verifier_egalites(vente)


# ---------------------------------------------------------------------------
# 3 — Tireuse : jetons cadeau et monnaie locale, une ligne avec sa part en jetons
# / 3 — Tap: gift tokens and local currency, one line with its token part
# ---------------------------------------------------------------------------


def test_tireuse_jetons_une_ligne_part_en_jetons(tenant):
    """
    500 ml à 8 €/L = 400, payés 100 en jetons cadeau (TNF) puis 300 en monnaie locale
    (TLF), par une carte anonyme :
    - UNE ligne : `qty` 0,500, `amount` 800, total 400, rien d'offert ;
    - part payée en jetons = le débit en jetons = 100 ; la TVA ne porte que sur le
      reste : HT 100 + 250 = 350, TVA 50 ;
    - deux règlements : jetons (LG) 100, monnaie locale (LE) 300.
    / 400 paid 100 tokens + 300 local: one line, token part 100 = token debit, VAT on
    the remainder only.
    """
    from BaseBillet.models import PaymentMethod
    from fedow_core.models import Asset

    jetons_cadeau = _monnaie_du_lieu(tenant, Asset.TNF)
    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, _portefeuille = _creer_une_carte(
        tenant, [(jetons_cadeau, 100), (monnaie_locale, 1000)]
    )

    _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "500.00",
    )

    with tenant_context(tenant):
        vente = _la_vente_du_tirage(carte)
        assert articles_d_ecart(vente) == []
        assert vente.articles.count() == 1

        ligne = le_seul_article_hors_ecart(vente)
        assert ligne.qty == Decimal("0.500")
        assert ligne.amount == 800
        assert ligne.total_catalogue == 400
        assert ligne.part_offerte == 0
        assert ligne.total_ttc == 400

        debit_en_jetons = None
        for debit in _debits_de_la_carte(carte):
            if debit.asset_id == jetons_cadeau.pk:
                debit_en_jetons = debit
        assert debit_en_jetons is not None
        assert ligne.part_en_jetons == debit_en_jetons.amount
        assert ligne.part_en_jetons == 100
        assert ligne.total_ht == 350
        assert ligne.total_tva == 50

        assert vente.reglements.count() == 2
        assert vente.reglements.get(moyen=PaymentMethod.LOCAL_GIFT).montant == 100
        assert vente.reglements.get(moyen=PaymentMethod.LOCAL_EURO).montant == 300

        verifier_egalites(vente)


# ---------------------------------------------------------------------------
# 4 — Tireuse : solde insuffisant, on facture le volume autorisé au badge
# / 4 — Tap: balance too low, the volume authorised at the badge is billed
# ---------------------------------------------------------------------------


def test_tireuse_solde_insuffisant_facture_le_volume_autorise(tenant, caplog):
    """
    La carte n'a que 200 en monnaie locale, à 6 €/L : au badge, le volume autorisé est
    200 / 600 × 1000 = 333,33 ml, arrondi VERS LE BAS au millilitre : 333 ml. Le
    Raspberry Pi déborde et annonce 500 ml servis (Q-H13) :
    - la ligne porte le volume autorisé : `qty` 0,333, `amount` 600, total
      0,333 × 600 = 199,8 → 200, jamais plus que le solde lu au badge ;
    - AUCUN article d'écart, AUCUN avertissement « non encaissé » : l'argent débité
      (200) couvre la ligne ;
    - UN règlement de 200 ; la carte est vide ;
    - le poids pour le stock garde le volume réellement servi : 50 cl.
    / Balance 200 at 6 €/L: 333 ml authorised (rounded down), 500 ml poured: the line
    bills 0.333 L (200), no gap, no warning, one 200 payment; weight 50 cl.
    """
    from BaseBillet.models import PaymentMethod
    from fedow_core.models import Asset, Token

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="6.00")
    carte, portefeuille = _creer_une_carte(tenant, [(monnaie_locale, 200)])

    caplog.set_level(logging.WARNING, logger="controlvanne.billing")
    reponse = _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "500.00",
    )
    assert reponse.json()["montant_centimes"] == 200

    avertissements_de_la_facture = []
    for enregistrement in caplog.records:
        avertissement_de_la_tireuse = (
            enregistrement.name == "controlvanne.billing"
            and enregistrement.levelno == logging.WARNING
        )
        if avertissement_de_la_tireuse:
            avertissements_de_la_facture.append(enregistrement.getMessage())
    assert avertissements_de_la_facture == []

    with tenant_context(tenant):
        solde_restant = Token.objects.get(
            wallet=portefeuille, asset=monnaie_locale
        ).value
        assert solde_restant == 0

        vente = _la_vente_du_tirage(carte)
        assert articles_d_ecart(vente) == []

        ligne = le_seul_article_hors_ecart(vente)
        assert ligne.qty == Decimal("0.333")
        assert ligne.amount == 600
        assert ligne.total_ttc == 200
        assert ligne.weight_quantity == 50

        reglement = vente.reglements.get()
        assert reglement.moyen == PaymentMethod.LOCAL_EURO
        assert reglement.montant == 200
        assert vente.total_ttc == 200

        verifier_egalites(vente)


# ---------------------------------------------------------------------------
# 5 — Tireuse : l'écran, la facture et la ligne au même centime
# / 5 — Tap: screen, bill and line at the same cent
# ---------------------------------------------------------------------------


def test_tireuse_ecran_et_facture_au_meme_centime(tenant):
    """
    333,7 ml à 7,50 €/L : la quantité est arrondie d'abord (0,334 L), puis le montant
    est calculé une fois sur cette quantité : 0,334 × 750 = 250,5 → 251.
    Le montant annoncé par l'écran pendant le service (`pour_update`), le montant
    facturé (`pour_end`), le débit, et le total de la ligne valent tous 251.
    / 333.7 ml at 7.50 €/L: quantity rounded first (0.334 L), then 251. Screen, bill,
    debit and line total are all 251.
    """
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="7.50")
    carte, _portefeuille = _creer_une_carte(tenant, [(monnaie_locale, 1000)])
    client_http = ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE)
    donnees_de_la_carte = {"tireuse_uuid": str(tireuse.uuid), "uid": carte.tag_id}

    # On capture les messages envoyés à l'écran de la tireuse (le kiosk).
    # / Capture the messages sent to the tap screen (the kiosk).
    messages_envoyes_a_l_ecran = []

    def capturer_le_message(uuid_de_la_tireuse, message, uuid_du_lieu):
        messages_envoyes_a_l_ecran.append(message)

    with mock.patch(
        "controlvanne.viewsets.pousser_aux_kiosks", side_effect=capturer_le_message
    ):
        reponse_du_badge = _poster(
            client_http, entetes_http, "authorize", donnees_de_la_carte
        )
        assert reponse_du_badge.json()["authorized"] is True

        _poster(
            client_http,
            entetes_http,
            "event",
            {**donnees_de_la_carte, "event_type": "pour_update", "volume_ml": "333.70"},
        )
        message_pendant_le_service = messages_envoyes_a_l_ecran[-1]

        reponse_de_fin = _poster(
            client_http,
            entetes_http,
            "event",
            {**donnees_de_la_carte, "event_type": "pour_end", "volume_ml": "333.70"},
        )

    assert reponse_de_fin.status_code == 200, reponse_de_fin.content
    montant_de_l_ecran = message_pendant_le_service["prix_servi_centimes"]
    assert montant_de_l_ecran == 251
    assert reponse_de_fin.json()["montant_centimes"] == 251

    with tenant_context(tenant):
        vente = _la_vente_du_tirage(carte)
        ligne = le_seul_article_hors_ecart(vente)
        assert ligne.qty == Decimal("0.334")
        assert ligne.amount == 750
        assert ligne.total_ttc == montant_de_l_ecran

        debits = _debits_de_la_carte(carte)
        assert len(debits) == 1
        assert debits[0].amount == montant_de_l_ecran
        assert articles_d_ecart(vente) == []

        verifier_egalites(vente)


# ---------------------------------------------------------------------------
# 6 — QR code payé avec deux monnaies : une ligne, l'uuid de la demande
# / 6 — QR code paid with two currencies: one line, the request uuid
# ---------------------------------------------------------------------------


def test_qr_deux_monnaies_une_ligne_uuid_de_la_demande(lieu):
    """
    Un QR code de 12,50 € est payé 5,00 € en monnaie locale (TLF → LE) et 7,50 € en
    monnaie fédérée (FED → SF) :
    - UNE ligne : `qty` 1, `amount` 1250, total 1250, le tarif vendu de la demande,
      l'uuid de la demande, les métadonnées de la demande recopiées, aucune part en
      jetons ;
    - DEUX règlements : LE 500 et SF 750, chacun avec l'uuid de sa transaction distante
      dans `reference_externe` ;
    - l'écran de l'encaisseur (`check_payment`, interrogé avec l'uuid de la demande)
      voit le paiement.
    / A 12.50 € QR code paid 5.00 TLF + 7.50 FED: one line (qty 1, amount 1250, request
    uuid), two payments; check_payment sees the payment.
    """
    from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin

    client_de_l_encaisseur = creer_un_encaisseur(lieu)
    payeur = creer_un_payeur()
    demande = generer_une_demande(client_de_l_encaisseur, 1250)
    tarif_vendu_de_la_demande = demande.pricesold_id
    email_de_l_encaisseur = metadonnees_lues(demande)["admin"]

    transaction_locale, monnaie_locale = transaction_de_l_ancien_fedow(500)
    transaction_federee, monnaie_federee = transaction_de_l_ancien_fedow(750)
    faux_fedow = fedow_simule(
        transactions_du_debit=[transaction_locale, transaction_federee],
        monnaies_du_fedow={
            monnaie_locale: {"category": "TLF"},
            monnaie_federee: {"category": "FED"},
        },
    )

    confirmer_par_qrcode(payeur, demande, faux_fedow)

    vente = la_vente_de_la_demande(demande)
    assert vente.origine == SaleOrigin.QRCODE_MA
    assert articles_d_ecart(vente) == []
    assert vente.articles.count() == 1

    ligne = le_seul_article_hors_ecart(vente)
    assert ligne.uuid == demande.uuid
    assert ligne.qty == Decimal("1")
    assert ligne.amount == 1250
    assert ligne.total_catalogue == 1250
    assert ligne.total_ttc == 1250
    assert ligne.part_en_jetons == 0
    assert ligne.pricesold_id == tarif_vendu_de_la_demande
    assert ligne.status == LigneArticle.VALID
    assert ligne.sale_origin == SaleOrigin.QRCODE_MA
    assert metadonnees_lues(ligne)["admin"] == email_de_l_encaisseur

    reglements_lus = []
    for reglement in vente.reglements.all():
        reglements_lus.append(
            (reglement.moyen, reglement.montant, reglement.reference_externe)
        )
    assert sorted(reglements_lus, key=str) == sorted(
        [
            (PaymentMethod.LOCAL_EURO, 500, str(transaction_locale["uuid"])),
            (PaymentMethod.STRIPE_FED, 750, str(transaction_federee["uuid"])),
        ],
        key=str,
    )

    reponse_de_l_ecran = client_de_l_encaisseur.get(
        f"/qrcodescanpay/{demande.uuid.hex}/check_payment/"
    )
    assert reponse_de_l_ecran.status_code == 200
    assert reponse_de_l_ecran.context["is_valid"] is True

    verifier_egalites(vente)


# ---------------------------------------------------------------------------
# 7 — QR / NFC : débit partiel, l'écart devient un article « reçu en moins »
# / 7 — QR / NFC: partial debit, the gap becomes a "received less" item
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("chemin_de_paiement", ["qrcode", "lecture_de_carte"])
def test_qr_debit_partiel_ecart_d_encaissement(
    lieu, django_capture_on_commit_callbacks, chemin_de_paiement
):
    """
    10,00 € demandés, l'ancien Fedow ne débite que 8,00 € (monnaie locale). Par le QR
    code (`valid_payment`) comme par la lecture de carte (`process_with_nfc`) :
    - la ligne garde le montant demandé : `qty` 1, `amount` 1000, total 1000 ;
    - un article « Écart d'encaissement — reçu en moins » : `qty` −1, `amount` 200,
      total −200 ;
    - UN règlement de 800 ; la vente vaut 800 ;
    - les deux mails (au lieu, à l'adhérent) portent l'argent réellement débité : 800.
    / 10.00 requested, 8.00 debited (QR, then card read): line 1000, "received less"
    gap −200, payment 800, both mails at 800.
    """
    from BaseBillet.models import PaymentMethod
    from BaseBillet.services_vente import NOM_ECART_RECU_EN_MOINS

    client_de_l_encaisseur = creer_un_encaisseur(lieu)
    payeur = creer_un_payeur_avec_portefeuille()
    demande = generer_une_demande(client_de_l_encaisseur, 1000)

    transaction_partielle, monnaie_locale = transaction_de_l_ancien_fedow(800)
    faux_fedow = fedow_simule(
        transactions_du_debit=[transaction_partielle],
        monnaies_du_fedow={monnaie_locale: {"category": "TLF"}},
    )
    # On ne garde que les tâches demandées par le paiement.
    # / Keep only the tasks requested by the payment.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        if chemin_de_paiement == "qrcode":
            confirmer_par_qrcode(payeur, demande, faux_fedow)
        else:
            payer_par_lecture_de_carte(
                client_de_l_encaisseur, payeur, demande, faux_fedow
            )

    vente = la_vente_de_la_demande(demande)

    ligne = le_seul_article_hors_ecart(vente)
    assert ligne.uuid == demande.uuid
    assert ligne.qty == Decimal("1")
    assert ligne.amount == 1000
    assert ligne.total_ttc == 1000

    ecarts = articles_d_ecart(vente)
    assert len(ecarts) == 1
    article_d_ecart = ecarts[0]
    assert article_d_ecart.pricesold.productsold.product.name == NOM_ECART_RECU_EN_MOINS
    assert article_d_ecart.qty == Decimal("-1")
    assert article_d_ecart.amount == 200
    assert article_d_ecart.total_ttc == -200

    reglement = vente.reglements.get()
    assert reglement.moyen == PaymentMethod.LOCAL_EURO
    assert reglement.montant == 800
    assert vente.total_ttc == 800

    # Les deux mails : (montant, date, lieu, e-mail) et (e-mail, montant, date, lieu).
    # / The two mails: (amount, date, venue, e-mail) and (e-mail, amount, date, venue).
    mails_au_lieu = arguments_des_taches(
        lieu.taches_demandees, "send_payment_success_admin"
    )
    mails_a_l_adherent = arguments_des_taches(
        lieu.taches_demandees, "send_payment_success_user"
    )
    assert len(mails_au_lieu) == 1
    assert len(mails_a_l_adherent) == 1
    assert mails_au_lieu[0][0] == 800
    assert mails_a_l_adherent[0][1] == 800

    verifier_egalites(vente)


# ---------------------------------------------------------------------------
# 8 — QR : débit supérieur, l'écart devient un article « reçu en plus »
# / 8 — QR: over debit, the gap becomes a "received more" item
# ---------------------------------------------------------------------------


def test_qr_debit_superieur_ecart_recu_en_plus(lieu):
    """
    10,00 € demandés, l'ancien Fedow débite 11,00 € (monnaie fédérée) :
    - la ligne garde le montant demandé : `qty` 1, `amount` 1000, total 1000 ;
    - un article « Écart d'encaissement — reçu en plus » : `qty` 1, `amount` 100,
      total +100 ;
    - UN règlement de 1100 ; la vente vaut 1100.
    / 10.00 requested, 11.00 debited: line 1000, "received more" gap +100.
    """
    from BaseBillet.models import PaymentMethod
    from BaseBillet.services_vente import NOM_ECART_RECU_EN_PLUS

    client_de_l_encaisseur = creer_un_encaisseur(lieu)
    payeur = creer_un_payeur()
    demande = generer_une_demande(client_de_l_encaisseur, 1000)

    transaction_superieure, monnaie_federee = transaction_de_l_ancien_fedow(1100)
    faux_fedow = fedow_simule(
        transactions_du_debit=[transaction_superieure],
        monnaies_du_fedow={monnaie_federee: {"category": "FED"}},
    )

    confirmer_par_qrcode(payeur, demande, faux_fedow)

    vente = la_vente_de_la_demande(demande)

    ligne = le_seul_article_hors_ecart(vente)
    assert ligne.qty == Decimal("1")
    assert ligne.amount == 1000
    assert ligne.total_ttc == 1000

    ecarts = articles_d_ecart(vente)
    assert len(ecarts) == 1
    article_d_ecart = ecarts[0]
    assert article_d_ecart.pricesold.productsold.product.name == NOM_ECART_RECU_EN_PLUS
    assert article_d_ecart.qty == Decimal("1")
    assert article_d_ecart.amount == 100
    assert article_d_ecart.total_ttc == 100

    reglement = vente.reglements.get()
    assert reglement.moyen == PaymentMethod.STRIPE_FED
    assert reglement.montant == 1100
    assert vente.total_ttc == 1100

    verifier_egalites(vente)


# ---------------------------------------------------------------------------
# 9 — Colonnes vides sur les lignes payées ; la demande non payée garde les siennes
# / 9 — Empty columns on paid lines; the unpaid request keeps its own
# ---------------------------------------------------------------------------


def test_lignes_tireuse_et_qr_sans_moyen_ni_monnaie(lieu):
    """
    Un tirage (comme le test 1) et un QR code payé avec deux monnaies (comme le test 6) :
    leurs lignes laissent vides le moyen (`payment_method`), la monnaie (`asset`), la
    carte et le portefeuille (Q-H2). Ces informations vivent dans les règlements.
    Un second QR code, jamais payé : sa ligne de demande (sans vente) reste telle
    quelle, avec son moyen « QR code » et son origine « QR code ».
    / A pour and a paid QR code: their lines leave method, currency, card and wallet
    empty. An unpaid QR request (no sale) keeps its QR method.
    """
    from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
    from fedow_core.models import Asset

    # Le tirage. / The pour.
    monnaie_locale_du_lieu = _monnaie_du_lieu(lieu.tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(
        lieu.tenant, prix_du_litre_en_euros="6.00"
    )
    carte, _portefeuille = _creer_une_carte(
        lieu.tenant, [(monnaie_locale_du_lieu, 1000)]
    )
    _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "500.00",
    )

    # Le QR code payé, puis le QR code jamais payé.
    # / The paid QR code, then the never-paid QR code.
    client_de_l_encaisseur = creer_un_encaisseur(lieu)
    payeur = creer_un_payeur()
    demande_payee = generer_une_demande(client_de_l_encaisseur, 1250)
    transaction_locale, monnaie_locale = transaction_de_l_ancien_fedow(500)
    transaction_federee, monnaie_federee = transaction_de_l_ancien_fedow(750)
    faux_fedow = fedow_simule(
        transactions_du_debit=[transaction_locale, transaction_federee],
        monnaies_du_fedow={
            monnaie_locale: {"category": "TLF"},
            monnaie_federee: {"category": "FED"},
        },
    )
    confirmer_par_qrcode(payeur, demande_payee, faux_fedow)
    demande_jamais_payee = generer_une_demande(client_de_l_encaisseur, 1250)

    with tenant_context(lieu.tenant):
        vente_du_tirage = _la_vente_du_tirage(carte)
        vente_du_qrcode = la_vente_de_la_demande(demande_payee)

        for vente in [vente_du_tirage, vente_du_qrcode]:
            lignes_de_la_vente = list(vente.articles.all())
            assert len(lignes_de_la_vente) >= 1
            for ligne in lignes_de_la_vente:
                assert champ_vide(ligne.payment_method), (
                    f"Moyen de la ligne : {ligne.payment_method!r} (attendu : vide)."
                )
                assert champ_vide(ligne.asset), (
                    f"Monnaie de la ligne : {ligne.asset!r}."
                )
                assert ligne.carte_id is None, (
                    f"Carte de la ligne : {ligne.carte_id!r}."
                )
                assert ligne.wallet_id is None, (
                    f"Portefeuille de la ligne : {ligne.wallet_id!r}."
                )
            verifier_egalites(vente)

        demande_relue = LigneArticle.objects.get(uuid=demande_jamais_payee.uuid)
        assert demande_relue.vente_id is None
        assert demande_relue.status == LigneArticle.CREATED
        assert demande_relue.payment_method == PaymentMethod.QRCODE_MA
        assert demande_relue.sale_origin == SaleOrigin.QRCODE_MA


# ---------------------------------------------------------------------------
# 11 — Une ligne de tireuse s'affiche en litres au détail, au ticket et au Z
# / 11 — A tap line shows in litres in the detail, the receipt and the Z report
# ---------------------------------------------------------------------------


def test_tireuse_affichee_en_litres_au_detail_au_ticket_et_au_z(lieu):
    """
    Un tirage de 500 ml à 6 €/L, d'un fût SANS stock (la règle « stock en cl → L » ne
    s'applique pas : c'est le type « fût » qui donne les litres) :
    - l'écran du détail de la vente montre « 0,50 L », « 6,00 €/L » et « 3,00 € » ;
    - le ticket imprimé montre « 0,50 L » et le prix au litre ;
    - le rapport (« Ventes par produit » du Z) donne 0,500 avec l'unité « L » ;
    - la marge compte le tirage pour UN article au coût inconnu (comme une pesée).
    / A 500 ml pour from a keg without stock: "0,50 L" on the detail screen, the
    receipt and the Z report; one item with unknown cost in the margin.
    """
    from comptabilite.presentation import sections_pour_affichage
    from fedow_core.models import Asset
    from laboutik.printing.escpos_builder import build_escpos_from_ticket_data
    from laboutik.printing.formatters import formatter_ticket_vente

    monnaie_locale = _monnaie_du_lieu(lieu.tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(
        lieu.tenant, prix_du_litre_en_euros="6.00"
    )
    carte, _portefeuille = _creer_une_carte(lieu.tenant, [(monnaie_locale, 1000)])
    _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "500.00",
    )
    vente = _la_vente_du_tirage(carte)
    nom_du_fut = tireuse.fut_actif.name

    # L'écran du détail de la vente (caisse activée en mémoire).
    # / The sale detail screen (register module on in memory).
    client_de_l_administrateur = creer_un_administrateur_du_lieu(lieu)
    with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
        reponse = client_de_l_administrateur.get(
            f"{DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE}{vente.uuid}/"
        )
    contenu_du_detail = reponse.content.decode()
    assert reponse.status_code == 200, contenu_du_detail[:400]
    assert textes_des_cellules(contenu_du_detail, "detail-qty") == ["0,50 L"]
    assert textes_des_cellules(contenu_du_detail, "detail-prix-unit") == ["6,00 €/L"]
    assert textes_des_cellules(contenu_du_detail, "detail-total-ligne") == ["3,00 €"]

    # Le ticket, tel que l'imprimante ESC/POS l'imprimerait.
    # / The receipt, as the ESC/POS printer would print it.
    donnees_du_ticket = formatter_ticket_vente(vente, None)
    texte_du_ticket = build_escpos_from_ticket_data(
        576, dict(donnees_du_ticket)
    ).decode("utf-8", errors="ignore")
    texte_du_ticket = texte_normalise(texte_du_ticket)
    assert "0,50 L" in texte_du_ticket, texte_du_ticket
    assert "/L" in texte_du_ticket, texte_du_ticket

    # Le rapport : la ligne du fût dans « Ventes par produit ».
    # / The report: the keg's row in "Sales by product".
    rapport = rapport_de_l_instant_de_la_vente(vente)
    sections_affichees = sections_pour_affichage(
        {
            "chiffre_affaires": rapport.section_chiffre_affaires(),
            "detail": rapport.section_detail(),
        }
    )
    tableau_par_produit = None
    for section in sections_affichees:
        for tableau in section["tableaux"]:
            if tableau["testid"] == "detail-ventes-par-produit":
                tableau_par_produit = tableau
    assert tableau_par_produit is not None, "Le tableau « Ventes par produit » manque."
    lignes_du_fut = []
    for ligne_du_tableau in tableau_par_produit["lignes"]:
        if ligne_du_tableau[1]["texte"] == nom_du_fut:
            lignes_du_fut.append(ligne_du_tableau)
    assert len(lignes_du_fut) == 1
    cellule_de_la_quantite = lignes_du_fut[0][2]
    quantite_lue, unite_lue = quantite_et_unite(
        texte_normalise(cellule_de_la_quantite["texte"])
    )
    assert quantite_lue == Decimal("0.50"), cellule_de_la_quantite["texte"]
    assert unite_lue == "L", cellule_de_la_quantite["texte"]

    marge_brute = rapport.section_marge_brute()
    assert marge_brute["nombre_d_articles_au_cout_inconnu"] == 1
    verifier_egalites(vente)


# ---------------------------------------------------------------------------
# 10 — Plus aucune part dans le code de production
# / 10 — No more parts in the production code
# ---------------------------------------------------------------------------


def test_plus_aucune_part_dans_le_code():
    """
    `_calculer_qty_partielles` (le découpage d'un article en parts) n'existe plus dans
    `laboutik.views`, et aucun fichier Python de production ne la nomme : ni import (une
    importation peut tenir sur plusieurs lignes, d'où la recherche du nom seul), ni
    appel, ni commentaire qui renverrait vers une fonction disparue. Les tests et les
    migrations ne sont pas lus. Pas de vente ici : pas de `verifier_egalites`.
    / `_calculer_qty_partielles` is gone from `laboutik.views`, and no production Python
    file names it (tests and migrations are not read). No sale here.
    """
    import laboutik.views

    assert not hasattr(laboutik.views, "_calculer_qty_partielles")

    nom_recherche = "_calculer_qty_partielles"
    dossiers_ignores = {"tests", "migrations", "node_modules", "www", "__pycache__"}
    racine_du_projet = Path(__file__).resolve().parents[2]

    fichiers_qui_la_nomment = []
    for dossier, sous_dossiers, fichiers in os.walk(racine_du_projet):
        # On ne descend ni dans les dossiers ignorés, ni dans les dossiers cachés
        # (.venv, .git…).
        # / Do not walk into ignored or hidden folders.
        sous_dossiers_a_parcourir = []
        for sous_dossier in sous_dossiers:
            dossier_cache = sous_dossier.startswith(".")
            if dossier_cache or sous_dossier in dossiers_ignores:
                continue
            sous_dossiers_a_parcourir.append(sous_dossier)
        sous_dossiers[:] = sous_dossiers_a_parcourir

        for nom_du_fichier in fichiers:
            if not nom_du_fichier.endswith(".py"):
                continue
            chemin_du_fichier = Path(dossier) / nom_du_fichier
            contenu = chemin_du_fichier.read_text(encoding="utf-8", errors="ignore")
            if nom_recherche in contenu:
                fichiers_qui_la_nomment.append(
                    str(chemin_du_fichier.relative_to(racine_du_projet))
                )

    assert fichiers_qui_la_nomment == [], (
        f"Fichiers de production qui nomment encore {nom_recherche} : "
        f"{fichiers_qui_la_nomment}"
    )


# ---------------------------------------------------------------------------
# Outils des tests 12 à 18
# / Helpers of tests 12 to 18
# ---------------------------------------------------------------------------


def servir_un_tirage_avec_un_ecart(lieu):
    """
    Un tirage de 500 ml à 6 €/L (300) avec un écart, par le filet de la tireuse : la
    carte (reliée à un utilisateur) a 200 en monnaie locale et 1000 sur l'ancien Fedow
    au badge ; à la fin du service, le débit de l'ancien Fedow (100) échoue. La ligne
    vaut 300, l'article « Écart d'encaissement — reçu en moins » −100, un règlement de
    200 en monnaie locale. Rend (la vente, la tireuse).
    / A 300 pour with a gap through the safety net (old Fedow debit fails): line 300,
    "received less" gap −100, one 200 local payment.
    """
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(lieu.tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(
        lieu.tenant, prix_du_litre_en_euros="6.00"
    )
    carte, _portefeuille = _creer_une_carte(
        lieu.tenant, [(monnaie_locale, 200)], avec_un_utilisateur=True
    )
    ancien_fedow = AncienFedowSimule(
        solde_en_centimes=1000,
        erreur_au_debit=ConnectionError("Ancien Fedow simulé : réseau coupé."),
    )
    lecture_simulee, debit_simule = simuler_l_ancien_fedow(ancien_fedow)
    with lecture_simulee, debit_simule:
        _servir_un_tirage(
            ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
            entetes_http,
            tireuse,
            carte,
            "500.00",
        )
    return _la_vente_du_tirage(carte), tireuse


def payer_un_qrcode_avec_un_debit_partiel(lieu):
    """
    Un QR code de 10,00 € dont l'ancien Fedow ne débite que 8,00 € (monnaie locale) :
    la ligne vaut 1000, l'écart « reçu en moins » −200, un règlement de 800. Rend
    (la vente, la demande, la réponse de la confirmation).
    / A 10.00 QR code debited 8.00: line 1000, gap −200, payment 800.
    """
    client_de_l_encaisseur = creer_un_encaisseur(lieu)
    payeur = creer_un_payeur()
    demande = generer_une_demande(client_de_l_encaisseur, 1000)
    transaction_partielle, monnaie_locale = transaction_de_l_ancien_fedow(800)
    faux_fedow = fedow_simule(
        transactions_du_debit=[transaction_partielle],
        monnaies_du_fedow={monnaie_locale: {"category": "TLF"}},
    )
    reponse = confirmer_par_qrcode(payeur, demande, faux_fedow)
    return la_vente_de_la_demande(demande), demande, reponse


# ---------------------------------------------------------------------------
# 12 — La tireuse facture le volume autorisé, pas le débordement
# / 12 — The tap bills the authorised volume, not the overflow
# ---------------------------------------------------------------------------


def test_tireuse_facture_le_volume_autorise_pas_le_debordement(lieu):
    """
    Carte anonyme à 300 en monnaie locale, fût à 6 €/L avec un stock en centilitres.
    Au badge, le solde permet 500 ml (300 / 600 × 1000) : c'est le volume autorisé de
    la session. Le Raspberry Pi déborde et annonce 530 ml servis (Q-H13) :
    - la ligne porte le volume AUTORISÉ : 0,500 L à 600, total 300 ; le débordement
      (30 ml) n'est pas facturé ;
    - AUCUN article d'écart : l'argent débité (300) couvre la ligne ;
    - UN règlement de 300 ; la vente vaut 300 ;
    - le poids pour le stock et le décrément du stock gardent le volume RÉELLEMENT
      servi : 53 cl.
    / Balance 300, 500 ml authorised, 530 ml poured: the line bills 0.500 L (300), no
    gap, one 300 payment; the stock goes down by the real 53 cl.
    """
    from BaseBillet.models import PaymentMethod
    from controlvanne.models import RfidSession
    from fedow_core.models import Asset
    from inventaire.models import Stock, UniteStock

    monnaie_locale = _monnaie_du_lieu(lieu.tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(
        lieu.tenant, prix_du_litre_en_euros="6.00"
    )
    stock_du_fut = Stock.objects.create(
        product=tireuse.fut_actif, quantite=10000, unite=UniteStock.CL
    )
    carte, _portefeuille = _creer_une_carte(lieu.tenant, [(monnaie_locale, 300)])

    reponse = _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "530.00",
    )
    assert reponse.json()["montant_centimes"] == 300

    session_du_tirage = RfidSession.objects.get(carte=carte)
    assert session_du_tirage.allowed_ml_session == Decimal("500.00")

    vente = _la_vente_du_tirage(carte)
    assert articles_d_ecart(vente) == []
    ligne_du_tirage = le_seul_article_hors_ecart(vente)
    assert ligne_du_tirage.qty == Decimal("0.500")
    assert ligne_du_tirage.amount == 600
    assert ligne_du_tirage.total_ttc == 300
    assert ligne_du_tirage.weight_quantity == 53

    reglements = []
    for reglement in vente.reglements.all():
        reglements.append((reglement.moyen, reglement.montant))
    assert reglements == [(PaymentMethod.LOCAL_EURO, 300)]
    assert vente.total_ttc == 300

    stock_du_fut.refresh_from_db()
    assert stock_du_fut.quantite == 10000 - 53
    verifier_egalites(vente)


def test_tireuse_ancien_fedow_en_echec_ecart_recu_en_moins_en_filet(lieu):
    """
    Le filet de l'article d'écart : carte reliée à un utilisateur, 100 en monnaie
    locale, 1000 sur l'ancien Fedow au badge (le volume autorisé couvre 500 ml). À la
    fin du service (500 ml à 6 €/L = 300), le débit de l'ancien Fedow (200) échoue :
    l'argent débité (100) ne couvre pas la ligne (300). La ligne garde son prix, et
    l'article « Écart d'encaissement — reçu en moins » porte −200 ; un règlement de 100.
    / Safety net: the old Fedow debit fails after the badge; line 300, "received less"
    gap −200, one 100 payment.
    """
    from BaseBillet.models import PaymentMethod
    from BaseBillet.services_vente import NOM_ECART_RECU_EN_MOINS
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(lieu.tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(
        lieu.tenant, prix_du_litre_en_euros="6.00"
    )
    carte, _portefeuille = _creer_une_carte(
        lieu.tenant, [(monnaie_locale, 100)], avec_un_utilisateur=True
    )

    ancien_fedow = AncienFedowSimule(
        solde_en_centimes=1000,
        erreur_au_debit=ConnectionError("Ancien Fedow simulé : réseau coupé."),
    )
    lecture_simulee, debit_simule = simuler_l_ancien_fedow(ancien_fedow)
    with lecture_simulee, debit_simule:
        reponse = _servir_un_tirage(
            ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
            entetes_http,
            tireuse,
            carte,
            "500.00",
        )
    assert reponse.json()["montant_centimes"] == 100
    assert len(ancien_fedow.debits) == 1
    assert ancien_fedow.debits[0][1] == 200

    vente = _la_vente_du_tirage(carte)
    ligne_du_tirage = le_seul_article_hors_ecart(vente)
    assert ligne_du_tirage.qty == Decimal("0.500")
    assert ligne_du_tirage.total_ttc == 300

    ecarts = articles_d_ecart(vente)
    assert len(ecarts) == 1
    assert ecarts[0].pricesold.productsold.product.name == NOM_ECART_RECU_EN_MOINS
    assert ecarts[0].total_ttc == -200

    reglements = []
    for reglement in vente.reglements.all():
        reglements.append((reglement.moyen, reglement.montant))
    assert reglements == [(PaymentMethod.LOCAL_EURO, 100)]
    verifier_egalites(vente)


# ---------------------------------------------------------------------------
# 13 — L'avoir d'une ligne QR s'écrit, que ses métadonnées soient un dict ou un texte
# / 13 — A QR line's credit note is written, metadata as a dict or as a text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forme_des_metadonnees", ["dictionnaire", "ancien_texte_json"])
def test_avoir_d_une_ligne_qr_possible(lieu, forme_des_metadonnees):
    """
    Un QR code de 10,00 € payé en entier (monnaie locale). La ligne payée garde les
    métadonnées de la demande sous forme de DICTIONNAIRE (le `JSONField` les rend telles
    quelles). L'avoir de la ligne s'écrit : article −1000, un règlement espèces −1000 ;
    ses métadonnées reprennent celles de la ligne (l'encaisseur) et l'uuid de la ligne
    d'origine.
    Cas « ancien texte JSON » : une ligne déjà en base dont les métadonnées sont un
    TEXTE JSON (écrit par `json.dumps`, lignes historiques, reprise R) : l'avoir
    s'écrit aussi, avec les mêmes métadonnées.
    / A paid QR line keeps the request metadata as a dict; its credit note is written
    (−1000, one cash payment), metadata carried over. An old line with JSON-text
    metadata gets its credit note too.
    """
    import json

    from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
    from BaseBillet.services_vente import ecrire_la_vente_d_avoir_d_une_ligne

    client_de_l_encaisseur = creer_un_encaisseur(lieu)
    payeur = creer_un_payeur()
    demande = generer_une_demande(client_de_l_encaisseur, 1000)
    email_de_l_encaisseur = metadonnees_lues(demande)["admin"]
    transaction_complete, monnaie_locale = transaction_de_l_ancien_fedow(1000)
    faux_fedow = fedow_simule(
        transactions_du_debit=[transaction_complete],
        monnaies_du_fedow={monnaie_locale: {"category": "TLF"}},
    )
    confirmer_par_qrcode(payeur, demande, faux_fedow)
    vente_du_qrcode = la_vente_de_la_demande(demande)
    ligne_du_qrcode = le_seul_article_hors_ecart(vente_du_qrcode)

    if forme_des_metadonnees == "dictionnaire":
        assert isinstance(ligne_du_qrcode.metadata, dict), (
            f"Métadonnées de la ligne QR : {ligne_du_qrcode.metadata!r} (attendu : dict)."
        )
    else:
        # Une ligne historique : les mêmes métadonnées, écrites en texte JSON.
        # / A historical line: the same metadata, written as JSON text.
        metadonnees_en_texte = json.dumps(metadonnees_lues(ligne_du_qrcode))
        LigneArticle.objects.filter(pk=ligne_du_qrcode.pk).update(
            metadata=metadonnees_en_texte
        )
        ligne_du_qrcode.refresh_from_db()
        assert isinstance(ligne_du_qrcode.metadata, str)

    ligne_d_avoir = ecrire_la_vente_d_avoir_d_une_ligne(
        ligne_du_qrcode,
        Decimal("1"),
        moyen_rembourse=PaymentMethod.CASH,
        origine=SaleOrigin.ADMIN,
    )
    vente_d_avoir = ligne_d_avoir.vente

    assert ligne_d_avoir.total_ttc == -1000
    reglements_de_l_avoir = []
    for reglement in vente_d_avoir.reglements.all():
        reglements_de_l_avoir.append((reglement.moyen, reglement.montant))
    assert reglements_de_l_avoir == [(PaymentMethod.CASH, -1000)]

    metadonnees_de_l_avoir = metadonnees_lues(ligne_d_avoir)
    assert metadonnees_de_l_avoir["admin"] == email_de_l_encaisseur
    assert metadonnees_de_l_avoir["original_lignearticle_uuid"] == str(
        ligne_du_qrcode.uuid
    )
    verifier_egalites(vente_d_avoir)


# ---------------------------------------------------------------------------
# 14 — Réconciliation : un écart payé en cashless n'est pas de l'argent
# / 14 — Reconciliation: a gap paid in cashless is not money
# ---------------------------------------------------------------------------


def test_reconciliation_ecart_cashless_hors_argent(lieu):
    """
    Une vente de 10,00 € en espèces, puis un tirage de 3,00 € payé 2,00 € en monnaie
    locale : l'ancien Fedow échoue pour le reste, écart « reçu en moins » −1,00 €
    (`servir_un_tirage_avec_un_ecart`). Le rapport de ces deux ventes :
    - réconciliation : « ventes payées en argent » 1000 (les espèces seules), écarts
      d'encaissement EN ARGENT 0 (l'écart du tirage est payé en cashless) ;
    - annexe « Écarts d'encaissement » : le total garde tous les écarts (−100), dont
      payés en cashless −100 (`dont_payes_en_cashless_en_centimes`).
    / Cash sale 10.00 then a 3.00 pour paid 2.00 in local currency: reconciliation
    counts 1000 money sales and 0 money gaps; the annex keeps −100, of which −100
    cashless.
    """
    from datetime import timedelta

    from BaseBillet.models import PaymentMethod, SaleOrigin
    from BaseBillet.models_vente import Vente
    from comptabilite.rapport import RapportDesVentes
    from fabriques_vente import creer_tarif_vendu, fabriquer_vente_encaissee

    tarif_du_jus = creer_tarif_vendu(nom="Jus reconciliation", prix_en_euros="10.00")
    vente_en_especes = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": tarif_du_jus,
                "quantite": Decimal("1"),
                "prix_unitaire": 1000,
                "taux_tva": Decimal("20"),
            },
        ],
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 1000}],
    )
    vente_du_tirage, _tireuse = servir_un_tirage_avec_un_ecart(lieu)

    # La période couvre exactement les deux encaissements.
    # / The period covers exactly the two settlements.
    debut_de_la_periode = Vente.objects.get(
        pk=vente_en_especes.pk
    ).datetime_encaissement
    fin_de_la_periode = Vente.objects.get(
        pk=vente_du_tirage.pk
    ).datetime_encaissement + timedelta(microseconds=1)
    rapport = RapportDesVentes(debut=debut_de_la_periode, fin=fin_de_la_periode)

    reconciliation = rapport.section_reconciliation()
    assert reconciliation["argent_recu_en_centimes"] == 1000
    assert reconciliation["ventes_payees_en_argent_en_centimes"] == 1000
    assert reconciliation["ecarts_d_encaissement_en_centimes"] == 0

    annexe_des_ecarts = rapport.section_annexe()["ecarts_d_encaissement"]
    assert annexe_des_ecarts["total_en_centimes"] == -100
    assert annexe_des_ecarts["dont_payes_en_cashless_en_centimes"] == -100

    verifier_egalites(vente_en_especes)
    verifier_egalites(vente_du_tirage)


# ---------------------------------------------------------------------------
# 15 — Liste des ventes de la caisse : un tirage avec écart compte 1 article
# / 15 — Register sales list: a pour with a gap counts 1 item
# ---------------------------------------------------------------------------


def test_liste_des_ventes_tirage_avec_ecart_un_article(lieu):
    """
    Un tirage de 3,00 € payé 2,00 €, l'ancien Fedow ayant échoué pour le reste (une
    ligne + un écart « reçu en moins », `servir_un_tirage_avec_un_ecart`). La liste
    des ventes de la caisse, filtrée sur le point de vente de la tireuse, affiche
    « 1 article(s) » : un tirage compte pour un article, et l'écart n'est pas un
    article vendu.
    / A pour with a gap: the register sales list shows 1 item (the gap is not an item).
    """
    vente_du_tirage, tireuse = servir_un_tirage_avec_un_ecart(lieu)

    client_de_l_administrateur = creer_un_administrateur_du_lieu(lieu)
    with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
        reponse = client_de_l_administrateur.get(
            "/laboutik/caisse/liste-ventes/",
            {"pv": str(tireuse.point_de_vente.uuid)},
        )
    contenu_de_la_liste = reponse.content.decode()
    assert reponse.status_code == 200, contenu_de_la_liste[:400]

    nombres_d_articles = textes_des_cellules(
        contenu_de_la_liste, "vente-nombre-articles"
    )
    assert len(nombres_d_articles) == 1, nombres_d_articles
    nombre_affiche = nombres_d_articles[0].split(" ")[0]
    assert nombre_affiche == "1", nombres_d_articles
    verifier_egalites(vente_du_tirage)


# ---------------------------------------------------------------------------
# 16 — Fiche « Vente » de l'admin : un tirage s'affiche en litres
# / 16 — Admin sale page: a pour shows in litres
# ---------------------------------------------------------------------------


def test_admin_tirage_affiche_en_litres(lieu):
    """
    Un tirage de 500 ml à 6 €/L d'un fût SANS stock. La fiche « Vente » de l'admin
    (articles de la vente) montre la quantité « 0,50 L » et le prix « 6,00 €/L » : un
    fût s'affiche toujours en litres (même règle que le détail de la caisse, Q-H4).
    / A 500 ml pour from a keg without stock: the admin sale page shows "0,50 L" and
    "6,00 €/L".
    """
    from Administration.admin.site import staff_admin_site
    from Administration.admin_tenant import ArticlesDeLaVenteInline
    from BaseBillet.models_vente import Vente
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(lieu.tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(
        lieu.tenant, prix_du_litre_en_euros="6.00"
    )
    carte, _portefeuille = _creer_une_carte(lieu.tenant, [(monnaie_locale, 1000)])
    _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "500.00",
    )
    vente_du_tirage = _la_vente_du_tirage(carte)
    ligne_du_tirage = le_seul_article_hors_ecart(vente_du_tirage)

    articles_de_la_vente = ArticlesDeLaVenteInline(Vente, staff_admin_site)
    quantite_affichee = texte_normalise(
        str(articles_de_la_vente.quantite(ligne_du_tirage))
    )
    prix_affiche = texte_normalise(
        str(articles_de_la_vente.prix_unitaire(ligne_du_tirage))
    )
    assert quantite_affichee == "0,50 L"
    assert prix_affiche == "6,00 €/L"
    verifier_egalites(vente_du_tirage)


# ---------------------------------------------------------------------------
# 17 — Page du payeur QR : l'argent débité
# / 17 — QR payer page: the money debited
# ---------------------------------------------------------------------------


def test_page_du_payeur_qr_affiche_l_argent_debite(lieu):
    """
    QR code de 10,00 € dont l'ancien Fedow ne débite que 8,00 €. La page de
    confirmation que le payeur voit (`valid_payment`) affiche l'argent réellement
    débité, 8,00 €, comme les mails et les réponses JSON.
    / A 10.00 QR code debited 8.00: the payer's confirmation page shows 8.00.
    """
    import re

    vente_du_qrcode, _demande, reponse = payer_un_qrcode_avec_un_debit_partiel(lieu)

    assert reponse.context["amount"] == 800
    contenu_de_la_page = reponse.content.decode()
    montants_affiches = re.findall(
        r'<span class="fs-4">\s*([^<]+?)\s*</span>', contenu_de_la_page
    )
    assert montants_affiches, contenu_de_la_page[:400]
    assert montants_affiches[0] in ("8.00", "8,00"), montants_affiches
    verifier_egalites(vente_du_qrcode)


# ---------------------------------------------------------------------------
# 18 — Un tirage de moins de 5 ml reste une vente au volume
# / 18 — A pour under 5 ml stays a volume sale
# ---------------------------------------------------------------------------


def test_tirage_de_moins_de_5_ml_reste_au_volume(lieu):
    """
    Un tirage de 4 ml à 6 €/L (0,004 L × 600 = 2,4 → 2 centimes), d'un fût sans prix
    d'achat. Le poids en centilitres (`weight_quantity`) vaut 0 (4 ml arrondis au cl),
    mais la ligne d'un fût reste une vente au volume :
    - détail des ventes par produit : quantité 0,004 avec l'unité « L » ;
    - marge : le tirage compte pour UN article au coût inconnu.
    / A 4 ml pour (weight_quantity 0): still a volume sale, unit "L", one item.
    """
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(lieu.tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(
        lieu.tenant, prix_du_litre_en_euros="6.00"
    )
    carte, _portefeuille = _creer_une_carte(lieu.tenant, [(monnaie_locale, 1000)])
    _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "4.00",
    )
    vente_du_tirage = _la_vente_du_tirage(carte)
    ligne_du_tirage = le_seul_article_hors_ecart(vente_du_tirage)
    assert ligne_du_tirage.qty == Decimal("0.004")
    assert ligne_du_tirage.weight_quantity == 0
    assert ligne_du_tirage.total_ttc == 2

    rapport = rapport_de_l_instant_de_la_vente(vente_du_tirage)
    lignes_du_fut = []
    for ligne_du_detail in rapport.section_detail()["ventes_par_produit"].values():
        if ligne_du_detail["nom"] == tireuse.fut_actif.name:
            lignes_du_fut.append(ligne_du_detail)
    assert len(lignes_du_fut) == 1, lignes_du_fut
    assert Decimal(lignes_du_fut[0]["quantite"]) == Decimal("0.004")
    assert lignes_du_fut[0]["unite"] == "L"

    marge_brute = rapport.section_marge_brute()
    assert marge_brute["nombre_d_articles_au_cout_inconnu"] == 1
    verifier_egalites(vente_du_tirage)


# ---------------------------------------------------------------------------
# 19 — Volume autorisé au badge : le même arrondi du prix au litre que la ligne
# / 19 — Volume allowed at the badge: the same price-per-litre rounding as the line
# ---------------------------------------------------------------------------


def test_volume_autorise_meme_arrondi_que_le_prix_de_la_ligne(lieu):
    """
    Un fût à 3,505 €/L. La ligne du tirage porte le prix au litre arrondi au centime
    DEMI-HAUT : 350,5 → 351 centimes (`calculer_prix_au_litre_en_centimes`). Le
    volume autorisé au badge lit le MÊME prix : avec 351 centimes de solde, il vaut
    351 / 351 × 1000 = 1000 ml. Avec un arrondi au pair (350 centimes), il vaudrait
    351 / 350 × 1000 = 1002,857 → 1002 ml, et la facture de ce volume (1,002 × 351 =
    351,7 → 352) dépasserait le solde lu au badge.
    / A 3.505 €/L keg: the line's price per litre is rounded half up (351 cents). The
    allowed volume reads the SAME price: 351 cents of balance → 1000 ml, and its bill
    (351) never exceeds the balance. A half-even rounding (350) would allow 1002 ml,
    billed 352.
    """
    from controlvanne.billing import (
        calculer_montant_centimes,
        calculer_prix_au_litre_en_centimes,
        calculer_volume_autorise_ml,
    )

    prix_du_litre_en_euros = Decimal("3.505")
    solde_lu_au_badge_en_centimes = 351

    volume_autorise_en_ml = calculer_volume_autorise_ml(
        solde_lu_au_badge_en_centimes,
        prix_du_litre_en_euros,
        reservoir_disponible_ml=50000,
    )

    assert calculer_prix_au_litre_en_centimes(prix_du_litre_en_euros) == 351
    assert volume_autorise_en_ml == Decimal("1000")
    montant_de_la_facture_en_centimes = calculer_montant_centimes(
        volume_autorise_en_ml, prix_du_litre_en_euros
    )
    assert montant_de_la_facture_en_centimes <= solde_lu_au_badge_en_centimes


# ---------------------------------------------------------------------------
# 20 — L'avoir d'une ligne aux métadonnées en texte vide ou blanc
# / 20 — The credit note of a line whose metadata is an empty or blank text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("texte_des_metadonnees", ["", "   "], ids=["vide", "blanc"])
def test_avoir_d_une_ligne_aux_metadonnees_texte_vide(lieu, texte_des_metadonnees):
    """
    Un QR code de 10,00 € payé en entier (monnaie locale). La ligne payée est ramenée
    à des métadonnées en TEXTE vide (ou blanc), comme une ligne historique sans
    métadonnées. L'avoir de la ligne s'écrit quand même : un texte vide ou blanc vaut
    « aucune métadonnée ». Les métadonnées de l'avoir sont seulement l'uuid de la ligne
    d'origine.
    / A paid QR line whose metadata is an empty (or blank) text: its credit note is
    written; its metadata only holds the original line uuid.
    """
    from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
    from BaseBillet.services_vente import ecrire_la_vente_d_avoir_d_une_ligne

    client_de_l_encaisseur = creer_un_encaisseur(lieu)
    payeur = creer_un_payeur()
    demande = generer_une_demande(client_de_l_encaisseur, 1000)
    transaction_complete, monnaie_locale = transaction_de_l_ancien_fedow(1000)
    faux_fedow = fedow_simule(
        transactions_du_debit=[transaction_complete],
        monnaies_du_fedow={monnaie_locale: {"category": "TLF"}},
    )
    confirmer_par_qrcode(payeur, demande, faux_fedow)
    vente_du_qrcode = la_vente_de_la_demande(demande)
    ligne_du_qrcode = le_seul_article_hors_ecart(vente_du_qrcode)
    LigneArticle.objects.filter(pk=ligne_du_qrcode.pk).update(
        metadata=texte_des_metadonnees
    )
    ligne_du_qrcode.refresh_from_db()
    assert ligne_du_qrcode.metadata == texte_des_metadonnees

    ligne_d_avoir = ecrire_la_vente_d_avoir_d_une_ligne(
        ligne_du_qrcode,
        Decimal("1"),
        moyen_rembourse=PaymentMethod.CASH,
        origine=SaleOrigin.ADMIN,
    )

    ligne_d_avoir_relue = LigneArticle.objects.get(pk=ligne_d_avoir.pk)
    assert ligne_d_avoir_relue.total_ttc == -1000
    assert ligne_d_avoir_relue.metadata == {
        "original_lignearticle_uuid": str(ligne_du_qrcode.uuid)
    }
    verifier_egalites(ligne_d_avoir_relue.vente)
