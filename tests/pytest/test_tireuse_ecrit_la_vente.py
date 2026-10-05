"""
Tests de la tireuse : chaque tirage facturé écrit aussi sa `Vente`, ses règlements, et
les montants entiers de ses articles.
/ Tap tests: each billed pour also writes its `Vente`, its payments, and the whole-cent
amounts of its items.

LOCALISATION : tests/pytest/test_tireuse_ecrit_la_vente.py

RÈGLE MÉTIER TESTÉE
Un tirage facturé au `pour_end` produit UNE vente encaissée (`REGLEE`, numérotée,
chaînée), d'origine `TIREUSE`, dans la même transaction que les débits des monnaies.
- Le total du tirage est arrondi au centime DEMI-HAUT (86,5 c → 87 c), et l'écran de la
  tireuse annonce le même montant que la facture.
- UNE ligne par tirage (D15) : `qty` = les litres facturés, `amount`
  = le prix au litre, total par la formule ; ni moyen, ni monnaie, ni carte, ni
  portefeuille sur la ligne (Q-H2).
- La part payée en jetons cadeau (TNF) est vendue hors TVA (`part_en_jetons`) : un
  jeton dépensé solde la dette du lieu (D8 bis). Son règlement est « jetons » (LG).
- Un règlement par transaction `fedow_core` créée : montant et uuid copiés de la
  transaction.
- Le coût d'achat porte sur les litres facturés, au prix d'achat du fût (au litre).
- Solde insuffisant : on facture le volume autorisé au badge (Q-H13), le débordement
  n'est pas facturé ; le poids pour le stock garde le volume servi ; la vente tient.
- Temps (TIM) et fidélité (FID) ne paient jamais un tirage.
/ One billed pour writes ONE settled, numbered, chained sale. Half-up total (screen =
bill). One line in litres at the price per litre; the gift-token part is sold
without VAT. One payment per local transaction. Cost on the litres of the part. Time and
loyalty never pay a pour.

COMMENT CHAQUE TEST RETROUVE SA VENTE
La base est partagée avec le serveur de dev. Chaque test crée SA carte : il retrouve sa
vente par cette carte (`Vente.carte`). Chaque test qui lit une vente finit par
`verifier_egalites(vente)` (tests/pytest/fabriques_vente.py) et compare des entiers
exacts.
/ Each test creates ITS card and finds its sale through it; it ends with
verifier_egalites(vente).

SIMULATIONS
Les tests passent par les vraies routes de la tireuse (`authorize` puis `event`
`pour_end`), avec la clé API du terminal de la tireuse (tests/pytest/
fabriques_controlvanne.py). Chaque test crée sa tireuse, son fût, sa carte : tout est
marqué `django_db`, la transaction est annulée à la fin (tests/PIEGES.md 13.1), rien ne
reste en base de dev. Les monnaies débitées vivent dans `fedow_core`, en base locale.
L'ancien Fedow (serveur distant) est simulé par une fixture automatique : lieu relié,
solde distant nul, débit distant interdit, aucun envoi réseau réel. La tireuse lit ce
solde au badge d'une carte d'utilisateur ; le paiement avec l'ancien Fedow est testé
dans test_tireuse_ancien_fedow.py.
/ The old Fedow is faked (linked, zero balance, no debit, no real network call); paying
with it is tested in test_tireuse_ancien_fedow.py.
Le test du chaînage lit la numérotation des ventes : il tourne dans un schéma à lui
(`FastTenantTestCase`), où aucune autre vente n'existe. Le singleton
`LaboutikConfiguration` y est créé à la main (tests/PIEGES.md 9.86) : il porte la clé de
l'empreinte des ventes.
/ Real tap routes, rolled-back transaction per test, local currencies only. The chaining
test runs in a dedicated schema.

CODE PARCOURU / CODE EXERCISED
- controlvanne/viewsets.py — TireuseViewSet.authorize, TireuseViewSet.event,
  _cloturer_session_et_facturer, _construire_payload_session ;
- controlvanne/billing.py — calculer_montant_centimes, facturer_tirage ;
- BaseBillet/services_vente.py — le service de vente.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-C-tireuse-qr.md (§1, §3, §4)
et CHANTIER-05-montants-entiers.md (§2, §8).

Lancer / Run : make test ARGS="tests/pytest/test_tireuse_ecrit_la_vente.py"
"""

import json
import uuid
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection
from django.test import Client as ClientHttpDjango
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import tenant_context

from fabriques_controlvanne import cle_api_de_la_tireuse
from fabriques_vente import (
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)

# Nom de domaine du lieu de test partagé (le lieu « lespass » de la base de dev).
# / Domain of the shared test venue (the "lespass" venue of the dev database).
DOMAINE_DU_LIEU_PARTAGE = "lespass.tibillet.localhost"

# Code de devise d'une monnaie créée par le test, selon sa catégorie.
# / Currency code of a currency created by the test, by category.
CODE_DEVISE_PAR_CATEGORIE = {
    "TNF": "EUR",
    "TLF": "EUR",
    "TIM": "TMP",
    "FID": "PTS",
}


# ---------------------------------------------------------------------------
# L'ancien Fedow simulé : solde nul, aucun envoi réseau réel
# / The faked old Fedow: zero balance, no real network call
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def ancien_fedow_simule_sans_solde():
    """
    Le lieu `lespass` est relié au vrai ancien Fedow en dev : au badge d'une carte
    d'utilisateur, la tireuse lirait son solde distant. Ici, la lecture rend « relié,
    solde 0 » : les soldes vérifiés par ces tests restent ceux des monnaies locales.
    Un débit distant, ou tout envoi HTTP du client de l'ancien Fedow (`_get`, `_post`),
    fait échouer le test.
    / The old Fedow read returns "linked, balance 0"; a remote debit or any real HTTP
    call fails the test.
    """
    envois_reseau_tentes = []

    def envoi_reseau_interdit(*arguments, **arguments_nommes):
        envois_reseau_tentes.append((arguments, arguments_nommes))
        raise AssertionError(
            "Appel réseau réel vers l'ancien Fedow interdit dans un test pytest."
        )

    debit_distant_interdit = mock.MagicMock(
        side_effect=AssertionError("Aucun débit de l'ancien Fedow dans ces tests.")
    )
    with mock.patch(
        "laboutik.views.lire_depensable_fed_frais", return_value=(0, True)
    ):
        with mock.patch("laboutik.views._debiter_legacy", new=debit_distant_interdit):
            with mock.patch(
                "fedow_connect.fedow_api._post", side_effect=envoi_reseau_interdit
            ):
                with mock.patch(
                    "fedow_connect.fedow_api._get", side_effect=envoi_reseau_interdit
                ):
                    yield

    assert envois_reseau_tentes == [], (
        f"Envois réseau réels tentés vers l'ancien Fedow : {envois_reseau_tentes}"
    )
    assert debit_distant_interdit.called is False


# ---------------------------------------------------------------------------
# Fabriques du test
# / Test factories
# ---------------------------------------------------------------------------


def _monnaie_du_lieu(lieu, categorie):
    """
    La monnaie de cette catégorie que la tireuse du lieu utilise.
    / The currency of this category that the venue's tap uses.

    On lit la monnaie avec LA MÊME requête que la tireuse
    (`AssetService.obtenir_assets_accessibles`, puis la première de la catégorie) : un
    solde posé sur une autre monnaie de la même catégorie serait invisible pour la
    tireuse (tests/PIEGES.md 9.97). Si le lieu n'en a aucune, le test en crée une : elle
    disparaît au rollback.
    / Same query as the tap (PIEGES 9.97); created if missing (rolled back).

    :param lieu: le `Client` (lieu) du test
    :param categorie: `Asset.TNF`, `Asset.TLF`, `Asset.TIM` ou `Asset.FID`
    :return: l'`Asset`
    """
    from fedow_core.services import AssetService, WalletService

    with tenant_context(lieu):
        monnaie_vue_par_la_tireuse = (
            AssetService.obtenir_assets_accessibles(lieu)
            .filter(category=categorie)
            .first()
        )
        if monnaie_vue_par_la_tireuse is not None:
            return monnaie_vue_par_la_tireuse

        portefeuille_du_lieu = WalletService.get_or_create_wallet_tenant(lieu)
        monnaie_creee = AssetService.creer_asset(
            tenant=lieu,
            name=f"TEST monnaie tireuse {categorie}",
            category=categorie,
            currency_code=CODE_DEVISE_PAR_CATEGORIE[categorie],
            wallet_origin=portefeuille_du_lieu,
        )
        return monnaie_creee


def _creer_une_tireuse(lieu, prix_du_litre_en_euros, prix_achat_du_litre_en_centimes=0):
    """
    Une tireuse neuve, son fût (TVA 20 %) et la clé API de son terminal.
    / A fresh tap, its keg (20 % VAT) and its terminal's API key.

    La création de la tireuse fabrique aussi son point de vente et son terminal
    (signal `post_save`, controlvanne/signals.py). Le point de vente est caché, comme
    tout point de vente de test (tests/PIEGES.md 9.41).
    / Creating the tap also creates its POS and terminal (post_save signal).

    :param lieu: le `Client` (lieu) du test
    :param prix_du_litre_en_euros: texte, ex. "8.00"
    :param prix_achat_du_litre_en_centimes: prix d'achat du fût au litre (int), 0 = inconnu
    :return: (la `TireuseBec` relue en base, les en-têtes HTTP de sa clé API)
    """
    from BaseBillet.models import Price, Product, Tva
    from controlvanne.models import TireuseBec
    from laboutik.models import PointDeVente

    identifiant = uuid.uuid4().hex[:8]
    with tenant_context(lieu):
        # Le taux est unique en base : on réutilise celui qui existe déjà.
        # / The rate is unique in the database: reuse the existing one.
        tva_de_la_biere, _tva_creee = Tva.objects.get_or_create(
            tva_rate=Decimal("20.00")
        )
        fut = Product.objects.create(
            name=f"TEST fût tireuse vente {identifiant}",
            categorie_article=Product.FUT,
            tva=tva_de_la_biere,
            prix_achat=prix_achat_du_litre_en_centimes,
        )
        Price.objects.create(
            product=fut,
            name="Litre",
            prix=Decimal(prix_du_litre_en_euros),
            poids_mesure=True,
        )
        tireuse = TireuseBec.objects.create(
            nom_tireuse=f"TEST tireuse vente {identifiant}",
            enabled=True,
            fut_actif=fut,
            reservoir_illimite=True,
        )
        tireuse.refresh_from_db()
        PointDeVente.objects.filter(pk=tireuse.point_de_vente_id).update(hidden=True)

    cle_api = cle_api_de_la_tireuse(lieu, tireuse)
    entetes_http = {"HTTP_AUTHORIZATION": f"Api-Key {cle_api}"}
    return tireuse, entetes_http


def _creer_une_carte(lieu, soldes_par_monnaie, avec_un_utilisateur=False):
    """
    Une carte NFC neuve, son portefeuille, et un solde par monnaie.
    / A fresh NFC card, its wallet, and one balance per currency.

    Sans utilisateur, le portefeuille est celui de la carte (`wallet_ephemere`). Avec un
    utilisateur, c'est celui de l'utilisateur : la tireuse le prend en premier.
    / Without user: the card's own wallet. With a user: the user's wallet.

    :param lieu: le `Client` (lieu) du test
    :param soldes_par_monnaie: liste de couples (Asset, solde en centimes)
    :param avec_un_utilisateur: True pour relier la carte à un utilisateur
    :return: (la `CarteCashless`, son `Wallet`)
    """
    from AuthBillet.models import TibilletUser, Wallet
    from fedow_core.models import Token
    from QrcodeCashless.models import CarteCashless

    identifiant = uuid.uuid4().hex[:8].upper()
    with tenant_context(lieu):
        portefeuille = Wallet.objects.create(
            origin=lieu, name=f"TEST portefeuille tireuse {identifiant}"
        )

        if avec_un_utilisateur:
            email = f"test+tireusevente{identifiant.lower()}@mock.test"
            utilisateur = TibilletUser.objects.create(
                email=email,
                username=email,
                first_name="Camille",
            )
            utilisateur.wallet = portefeuille
            utilisateur.save()
            carte = CarteCashless.objects.create(
                tag_id=identifiant,
                number=uuid.uuid4().hex[:8].upper(),
                user=utilisateur,
            )
        else:
            carte = CarteCashless.objects.create(
                tag_id=identifiant,
                number=uuid.uuid4().hex[:8].upper(),
                wallet_ephemere=portefeuille,
            )

        for monnaie, solde_en_centimes in soldes_par_monnaie:
            Token.objects.create(
                wallet=portefeuille, asset=monnaie, value=solde_en_centimes
            )

    return carte, portefeuille


def _poster(client_http, entetes_http, route, donnees):
    """
    POST JSON sur une route de la tireuse. / JSON POST to a tap route.
    """
    return client_http.post(
        f"/controlvanne/api/tireuse/{route}/",
        data=json.dumps(donnees),
        content_type="application/json",
        **entetes_http,
    )


def _servir_un_tirage(client_http, entetes_http, tireuse, carte, volume_en_ml):
    """
    Un service complet, comme le Raspberry Pi : badge (`authorize`), puis fin de
    service (`event` `pour_end`) avec le volume servi.
    / A full pour, like the Raspberry Pi: badge, then pour end with the served volume.

    :param volume_en_ml: texte, ex. "500.00"
    :return: la réponse du `pour_end`
    """
    donnees_de_la_carte = {"tireuse_uuid": str(tireuse.uuid), "uid": carte.tag_id}

    reponse_du_badge = _poster(
        client_http, entetes_http, "authorize", donnees_de_la_carte
    )
    assert reponse_du_badge.status_code == 200, reponse_du_badge.content
    assert reponse_du_badge.json()["authorized"] is True, reponse_du_badge.json()

    reponse_de_fin = _poster(
        client_http,
        entetes_http,
        "event",
        {**donnees_de_la_carte, "event_type": "pour_end", "volume_ml": volume_en_ml},
    )
    assert reponse_de_fin.status_code == 200, reponse_de_fin.content
    return reponse_de_fin


def _la_vente_du_tirage(carte):
    """
    LA vente de tireuse écrite pour cette carte : il doit y en avoir une et une seule.
    À appeler dans le lieu du test.
    / THE tap sale written for this card: exactly one. Call inside the test venue.
    """
    from BaseBillet.models import SaleOrigin
    from BaseBillet.models_vente import Vente

    ventes_de_la_carte = list(
        Vente.objects.filter(carte=carte, origine=SaleOrigin.TIREUSE)
    )
    assert len(ventes_de_la_carte) == 1, (
        f"Un tirage écrit une vente et une seule : {len(ventes_de_la_carte)} "
        f"trouvée(s) pour la carte {carte.tag_id}."
    )
    return ventes_de_la_carte[0]


def _debits_de_la_carte(carte):
    """
    Les transactions de vente `fedow_core` de cette carte, dans l'ordre de création.
    / The fedow_core sale transactions of this card, in creation order.
    """
    from fedow_core.models import Transaction

    return list(
        Transaction.objects.filter(card=carte, action=Transaction.SALE).order_by("id")
    )


def _le_debit_de_la_monnaie(debits, monnaie):
    """
    Le seul débit fait dans cette monnaie. / The only debit made in this currency.
    """
    debits_de_la_monnaie = []
    for debit in debits:
        if debit.asset_id == monnaie.pk:
            debits_de_la_monnaie.append(debit)
    assert len(debits_de_la_monnaie) == 1, (
        f"Un seul débit attendu en {monnaie.category}, trouvé(s) : "
        f"{len(debits_de_la_monnaie)}."
    )
    return debits_de_la_monnaie[0]


# ---------------------------------------------------------------------------
# Tests sur la base partagée (transaction annulée à la fin de chaque test)
# / Tests on the shared database (transaction rolled back after each test)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tirage_50cl_une_vente_un_reglement(tenant):
    """
    50 cl à 8 €/L, payés en monnaie locale (TLF), par une carte reliée à un utilisateur :
    - UNE vente `TIREUSE`, réglée, numérotée, au point de vente de la tireuse, avec la
      carte et son utilisateur comme client ; total 400, HT 333, TVA 67 (20 %) ;
    - UN règlement « monnaie locale » (LE) de 400, copié de la transaction `fedow_core`
      (même montant, même uuid), avec la monnaie, la carte et le portefeuille ;
    - UNE ligne : `amount` 800 (prix au litre), `qty` 0,500, 50 cl pour le stock,
      origine TIREUSE, point de vente, identifiant de paiement ; ni moyen, ni monnaie,
      ni carte, ni portefeuille (Q-H2) ; la session de la tireuse pointe sur elle.
    / 50 cl at 8 €/L paid in local currency: one settled sale, one payment copied from
    the transaction, one line of 0.500 L at 800 per litre.
    """
    from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
    from BaseBillet.models_vente import Vente
    from controlvanne.models import RfidSession
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, portefeuille = _creer_une_carte(
        tenant, [(monnaie_locale, 1000)], avec_un_utilisateur=True
    )

    reponse = _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "500.00",
    )
    assert reponse.json()["montant_centimes"] == 400

    with tenant_context(tenant):
        vente = _la_vente_du_tirage(carte)

        # La vente : réglée, numérotée, à la tireuse, avec la carte et son client.
        # / The sale: settled, numbered, at the tap, with the card and its customer.
        assert vente.statut == Vente.Statut.REGLEE
        assert vente.numero is not None
        assert vente.nature == Vente.Nature.VENTE
        assert vente.origine == SaleOrigin.TIREUSE
        assert vente.point_de_vente_id == tireuse.point_de_vente_id
        assert vente.point_de_vente_id is not None
        assert vente.carte_id == carte.pk
        assert vente.client_id == carte.user_id
        assert vente.total_catalogue == 400
        assert vente.total_offert == 0
        assert vente.total_ttc == 400
        assert vente.total_ht == 333
        assert vente.total_tva == 67

        # Un seul débit, et un seul règlement copié de lui.
        # / One debit, and one payment copied from it.
        debits = _debits_de_la_carte(carte)
        assert len(debits) == 1
        debit_en_monnaie_locale = debits[0]
        assert debit_en_monnaie_locale.asset_id == monnaie_locale.pk
        assert debit_en_monnaie_locale.amount == 400

        reglements = list(vente.reglements.all())
        assert len(reglements) == 1
        reglement = reglements[0]
        assert reglement.moyen == PaymentMethod.LOCAL_EURO
        assert reglement.montant == debit_en_monnaie_locale.amount
        assert reglement.fedow_transaction_uuid == debit_en_monnaie_locale.uuid
        assert reglement.asset == monnaie_locale.uuid
        assert reglement.carte_id == carte.pk
        assert reglement.wallet_id == portefeuille.pk

        # La ligne : les litres servis au prix du litre, et ses montants entiers.
        # / The line: litres served at the price per litre, whole-cent amounts.
        lignes = list(vente.articles.all())
        assert len(lignes) == 1
        ligne = lignes[0]
        assert ligne.amount == 800
        assert ligne.qty == Decimal("0.500")
        assert ligne.weight_quantity == 50
        assert ligne.sale_origin == SaleOrigin.TIREUSE
        assert ligne.payment_method is None
        assert ligne.status == LigneArticle.VALID
        assert ligne.asset is None
        assert ligne.carte_id is None
        assert ligne.wallet_id is None
        assert ligne.point_de_vente_id == tireuse.point_de_vente_id
        assert ligne.uuid_transaction is not None
        assert ligne.vat == Decimal("20.00")
        assert ligne.total_catalogue == 400
        assert ligne.part_offerte == 0
        assert ligne.total_ttc == 400
        assert ligne.total_ht == 333
        assert ligne.total_tva == 67

        # La session de la tireuse pointe sur la ligne du tirage.
        # / The tap session points to the pour's line.
        session_du_tirage = RfidSession.objects.get(carte=carte)
        assert session_du_tirage.ligne_article_id == ligne.pk

        verifier_egalites(vente)


@pytest.mark.django_db
def test_tirage_jetons_et_monnaie_locale_une_ligne(tenant):
    """
    50 cl à 8 €/L = 400, payés 100 en jetons cadeau (TNF) puis 300 en monnaie locale
    (TLF), par une carte anonyme :
    - UNE ligne : `amount` 800, `qty` 0,500, total catalogue 400, rien d'offert, part
      payée en jetons 100 (D8 bis) ;
    - deux règlements copiés des deux transactions : jetons (LG) 100, monnaie locale
      (LE) 300 ; la vente n'a pas de client.
    / 400 paid 100 gift tokens + 300 local currency: one line (token part 100), two
    payments copied from the two transactions.
    """
    from BaseBillet.models import PaymentMethod
    from fedow_core.models import Asset

    jetons_cadeau = _monnaie_du_lieu(tenant, Asset.TNF)
    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, _portefeuille = _creer_une_carte(
        tenant, [(jetons_cadeau, 100), (monnaie_locale, 1000)]
    )

    reponse = _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "500.00",
    )
    assert reponse.json()["montant_centimes"] == 400

    with tenant_context(tenant):
        vente = _la_vente_du_tirage(carte)
        assert vente.client_id is None
        assert vente.total_catalogue == 400
        assert vente.total_offert == 0
        assert vente.total_ttc == 400
        assert vente.total_ht == 350
        assert vente.total_tva == 50

        # UNE ligne : rien d'offert, la part en jetons est une vente (D8 bis).
        # / ONE line: nothing offered, the token part is a sale.
        ligne = vente.articles.get()
        assert ligne.total_catalogue == 400
        assert ligne.part_offerte == 0
        assert ligne.source_offert == ""
        assert ligne.total_ttc == 400
        assert ligne.part_en_jetons == 100
        assert ligne.amount == 800
        assert ligne.qty == Decimal("0.500")

        # Deux règlements, chacun copié de sa transaction.
        # / Two payments, each copied from its transaction.
        debits = _debits_de_la_carte(carte)
        assert len(debits) == 2
        debit_en_jetons = _le_debit_de_la_monnaie(debits, jetons_cadeau)
        debit_en_monnaie_locale = _le_debit_de_la_monnaie(debits, monnaie_locale)

        assert vente.reglements.count() == 2
        reglement_en_jetons = vente.reglements.get(moyen=PaymentMethod.LOCAL_GIFT)
        assert reglement_en_jetons.montant == 100
        assert reglement_en_jetons.montant == debit_en_jetons.amount
        assert reglement_en_jetons.fedow_transaction_uuid == debit_en_jetons.uuid
        assert reglement_en_jetons.asset == jetons_cadeau.uuid

        reglement_en_monnaie_locale = vente.reglements.get(
            moyen=PaymentMethod.LOCAL_EURO
        )
        assert reglement_en_monnaie_locale.montant == 300
        assert reglement_en_monnaie_locale.montant == debit_en_monnaie_locale.amount
        assert (
            reglement_en_monnaie_locale.fedow_transaction_uuid
            == debit_en_monnaie_locale.uuid
        )
        assert reglement_en_monnaie_locale.asset == monnaie_locale.uuid

        verifier_egalites(vente)


@pytest.mark.django_db
def test_tireuse_jetons_vente_ordinaire_tva_zero(tenant):
    """
    50 cl à 8 €/L = 400 (fût à TVA 20 %), payés 100 en jetons cadeau (TNF) puis 300 en
    monnaie locale (TLF). Un jeton dépensé solde la dette du lieu (D8 bis) : la part
    payée en jetons est une VENTE ORDINAIRE, hors TVA. UNE ligne :
    - catalogue 400, rien d'offert, sans source d'offert, net 400, part payée en jetons
      100, taux du fût (20 %) ; la TVA ne porte que sur le reste (300) :
      HT 100 + 250 = 350, TVA 50 ;
    - le règlement « jetons » (LG) de 100 compte dans les deux égalités.
    Vente : catalogue 400, offert 0, net 400, HT 350, TVA 50.
    / 400 paid 100 gift tokens + 300 local currency: one line, token part 100 without
    VAT. Sale: net 400, HT 350, VAT 50.
    """
    from BaseBillet.models import PaymentMethod
    from fedow_core.models import Asset

    jetons_cadeau = _monnaie_du_lieu(tenant, Asset.TNF)
    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, _portefeuille = _creer_une_carte(
        tenant, [(jetons_cadeau, 100), (monnaie_locale, 1000)]
    )

    reponse = _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "500.00",
    )
    assert reponse.json()["montant_centimes"] == 400

    with tenant_context(tenant):
        vente = _la_vente_du_tirage(carte)

        # La ligne : hors TVA pour sa part payée en jetons, au taux du fût pour le
        # reste.
        # / The line: no VAT on its token part, the keg's rate on the rest.
        ligne = vente.articles.get()
        assert ligne.total_catalogue == 400
        assert ligne.part_offerte == 0
        assert ligne.source_offert == ""
        assert ligne.total_ttc == 400
        assert ligne.part_en_jetons == 100
        assert ligne.vat == Decimal("20.00")
        assert ligne.total_ht == 350
        assert ligne.total_tva == 50

        assert vente.reglements.get(moyen=PaymentMethod.LOCAL_GIFT).montant == 100
        assert vente.reglements.get(moyen=PaymentMethod.LOCAL_EURO).montant == 300
        assert vente.total_catalogue == 400
        assert vente.total_offert == 0
        assert vente.total_ttc == 400
        assert vente.total_ht == 350
        assert vente.total_tva == 50

        verifier_egalites(vente)


@pytest.mark.django_db
def test_tirage_88_centimes_30_plus_58(tenant):
    """
    25 cl à 3,50 €/L = 0,250 × 350 = 87,5 c → 88 c, payés 30 en jetons cadeau puis 58
    en monnaie locale. UNE ligne de 88, dont EXACTEMENT 30 payés en jetons (l'argent
    réel du débit) ; deux règlements exacts, 30 et 58.
    / 88 c paid 30 tokens + 58 local currency: one 88 line, token part exactly 30.
    """
    from BaseBillet.models import PaymentMethod
    from fedow_core.models import Asset

    jetons_cadeau = _monnaie_du_lieu(tenant, Asset.TNF)
    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="3.50")
    carte, _portefeuille = _creer_une_carte(
        tenant, [(jetons_cadeau, 30), (monnaie_locale, 1000)]
    )

    reponse = _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "250.00",
    )
    assert reponse.json()["montant_centimes"] == 88

    with tenant_context(tenant):
        vente = _la_vente_du_tirage(carte)
        assert vente.total_catalogue == 88

        ligne = vente.articles.get()
        assert ligne.total_catalogue == 88
        assert ligne.part_en_jetons == 30
        assert ligne.amount == 350
        assert ligne.qty == Decimal("0.250")

        assert vente.reglements.get(moyen=PaymentMethod.LOCAL_GIFT).montant == 30
        assert vente.reglements.get(moyen=PaymentMethod.LOCAL_EURO).montant == 58

        verifier_egalites(vente)


@pytest.mark.django_db
def test_total_tirage_arrondi_demi_haut(tenant):
    """
    173 ml à 5 €/L = 0,173 × 500 = 86,5 c. Arrondi demi-haut : 87 c (l'arrondi au pair
    donnerait 86). La facture, le débit, le règlement, le total de la ligne et la vente
    valent 87.
    / 173 ml at 5 €/L = 86.5 c → 87 c (round-half-even would give 86).
    """
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="5.00")
    carte, _portefeuille = _creer_une_carte(tenant, [(monnaie_locale, 1000)])

    reponse = _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "173.00",
    )
    assert reponse.json()["montant_centimes"] == 87

    with tenant_context(tenant):
        debits = _debits_de_la_carte(carte)
        assert len(debits) == 1
        assert debits[0].amount == 87

        vente = _la_vente_du_tirage(carte)
        assert vente.total_catalogue == 87
        assert vente.reglements.get().montant == 87
        ligne = vente.articles.get()
        assert ligne.total_ttc == 87
        assert ligne.amount == 500
        assert ligne.qty == Decimal("0.173")

        verifier_egalites(vente)


@pytest.mark.django_db
def test_montant_ecran_egal_montant_facture_demi_haut(tenant):
    """
    173 ml à 5 €/L : l'écran de la tireuse annonce 87 c pendant le service
    (`pour_update`), et la facture du `pour_end` vaut aussi 87 c. L'écran et la facture
    utilisent la même formule : ils ne peuvent pas différer d'un centime.
    / The tap screen announces 87 c during the pour, and the bill is 87 c too.
    """
    from fedow_core.models import Asset

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="5.00")
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
            {
                **donnees_de_la_carte,
                "event_type": "pour_update",
                "volume_ml": "173.00",
            },
        )
        message_pendant_le_service = messages_envoyes_a_l_ecran[-1]

        reponse_de_fin = _poster(
            client_http,
            entetes_http,
            "event",
            {**donnees_de_la_carte, "event_type": "pour_end", "volume_ml": "173.00"},
        )

    assert message_pendant_le_service["prix_servi_centimes"] == 87
    assert reponse_de_fin.status_code == 200, reponse_de_fin.content
    assert reponse_de_fin.json()["montant_centimes"] == 87

    with tenant_context(tenant):
        vente = _la_vente_du_tirage(carte)
        assert (
            vente.total_catalogue == message_pendant_le_service["prix_servi_centimes"]
        )
        verifier_egalites(vente)


@pytest.mark.django_db
def test_tirage_solde_insuffisant_facture_le_volume_autorise(tenant):
    """
    La carte n'a que 300 c en monnaie locale : à 8 €/L, le badge autorise 375 ml. Le
    Raspberry Pi déborde et annonce 50 cl. On facture le volume autorisé (Q-H13) :
    0,375 L à 800 = 300, exactement le débit (c'est aussi ce que la réponse annonce) ;
    le débordement n'est pas facturé, aucun article d'écart. Le poids pour le stock
    garde le volume servi (50 cl). La vente vaut 300 et tient ses deux égalités.
    / Balance 300 c, 375 ml authorised, 50 cl poured: the line bills 0.375 L (300), no
    gap; weight 50 cl; the sale holds.
    """
    from BaseBillet.models import PaymentMethod
    from fedow_core.models import Asset, Token

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, portefeuille = _creer_une_carte(tenant, [(monnaie_locale, 300)])

    reponse = _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "500.00",
    )
    assert reponse.json()["montant_centimes"] == 300

    with tenant_context(tenant):
        solde_restant = Token.objects.get(
            wallet=portefeuille, asset=monnaie_locale
        ).value
        assert solde_restant == 0

        debits = _debits_de_la_carte(carte)
        assert len(debits) == 1
        assert debits[0].amount == 300

        vente = _la_vente_du_tirage(carte)
        assert vente.total_ttc == 300

        reglement = vente.reglements.get()
        assert reglement.moyen == PaymentMethod.LOCAL_EURO
        assert reglement.montant == 300
        assert reglement.fedow_transaction_uuid == debits[0].uuid

        ligne = vente.articles.get()
        assert ligne.amount == 800
        assert ligne.qty == Decimal("0.375")
        assert ligne.total_catalogue == 300
        assert ligne.weight_quantity == 50

        verifier_egalites(vente)


@pytest.mark.django_db
def test_tirage_cout_sur_les_litres_reels(tenant):
    """
    0,50 L servi, fût acheté 300 c le litre, payé 200 en jetons cadeau et 200 en
    monnaie locale (à 8 €/L). Le coût porte sur les litres réellement servis, quelle
    que soit la façon de payer : 0,500 L × 300 = 150, sur l'unique ligne.
    / 0.50 L at a 300 c/L purchase price, paid with two currencies: cost 150 on the
    single line.
    """
    from fedow_core.models import Asset

    jetons_cadeau = _monnaie_du_lieu(tenant, Asset.TNF)
    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(
        tenant, prix_du_litre_en_euros="8.00", prix_achat_du_litre_en_centimes=300
    )
    carte, _portefeuille = _creer_une_carte(
        tenant, [(jetons_cadeau, 200), (monnaie_locale, 1000)]
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
        ligne = vente.articles.get()
        assert ligne.qty == Decimal("0.500")
        assert ligne.cout_achat == 150

        verifier_egalites(vente)


@pytest.mark.django_db
def test_tirage_ne_prend_ni_temps_ni_fidelite(tenant):
    """
    Témoin : la carte a 500 en temps (TIM), 500 en fidélité (FID) et 1000 en monnaie
    locale (TLF). Un tirage de 400 ne débite que la monnaie locale : aucun débit, aucune
    ligne ni aucun règlement en temps ou en fidélité, et leurs soldes ne bougent pas.
    Ce test ne lit pas la vente : il fige le comportement de la tireuse avant et après
    l'écriture de la vente.
    / Witness: time and loyalty never pay a pour; only the local currency is debited.
    """
    from BaseBillet.models import LigneArticle
    from BaseBillet.models_vente import Reglement
    from fedow_core.models import Asset, Token

    monnaie_temps = _monnaie_du_lieu(tenant, Asset.TIM)
    monnaie_fidelite = _monnaie_du_lieu(tenant, Asset.FID)
    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, portefeuille = _creer_une_carte(
        tenant,
        [(monnaie_temps, 500), (monnaie_fidelite, 500), (monnaie_locale, 1000)],
    )

    reponse = _servir_un_tirage(
        ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE),
        entetes_http,
        tireuse,
        carte,
        "500.00",
    )
    assert reponse.json()["montant_centimes"] == 400

    with tenant_context(tenant):
        # Seule la monnaie locale est débitée.
        # / Only the local currency is debited.
        debits = _debits_de_la_carte(carte)
        assert len(debits) == 1
        assert debits[0].asset_id == monnaie_locale.pk
        assert debits[0].amount == 400

        # Les soldes en temps et en fidélité ne bougent pas.
        # / Time and loyalty balances do not move.
        assert Token.objects.get(wallet=portefeuille, asset=monnaie_temps).value == 500
        assert (
            Token.objects.get(wallet=portefeuille, asset=monnaie_fidelite).value == 500
        )
        assert Token.objects.get(wallet=portefeuille, asset=monnaie_locale).value == 600

        # Aucune ligne ni aucun règlement en temps ou en fidélité.
        # / No line and no payment in time or loyalty.
        uuids_du_temps_et_de_la_fidelite = [monnaie_temps.uuid, monnaie_fidelite.uuid]
        lignes_en_temps_ou_fidelite = LigneArticle.objects.filter(
            carte=carte, asset__in=uuids_du_temps_et_de_la_fidelite
        )
        assert lignes_en_temps_ou_fidelite.count() == 0
        reglements_en_temps_ou_fidelite = Reglement.objects.filter(
            carte=carte, asset__in=uuids_du_temps_et_de_la_fidelite
        )
        assert reglements_en_temps_ou_fidelite.count() == 0


@pytest.mark.django_db
def test_tirage_egalite_rompue_remonte_et_n_ecrit_rien(tenant):
    """
    Si l'encaissement de la vente refuse les égalités (`EgaliteDeVenteRompue`), la
    tireuse ne rattrape pas l'erreur : elle remonte jusqu'à la réponse (500, captée par
    Sentry), et RIEN n'est écrit. Les débits, les lignes et la vente sont dans la même
    transaction : ils disparaissent ensemble. Aucun argent n'est perdu. La fermeture de
    la session est dans cette transaction aussi : la session reste ouverte.
    Le client de test de Django relance l'exception de la vue au lieu de rendre la 500 :
    on l'attend donc avec `pytest.raises`.
    / A broken equality is not caught: it goes up to the response, and nothing is
    written (debits, lines and sale roll back together). The Django test client re-raises
    the view's exception instead of returning the 500.

    `encaisser_vente` est simulé à sa source (`BaseBillet.services_vente`) : la
    facturation de la tireuse l'importe au moment de l'appel.
    / encaisser_vente is faked at its source: the tap billing imports it at call time.
    """
    from BaseBillet.models import LigneArticle
    from BaseBillet.models_vente import Vente
    from BaseBillet.services_vente import EgaliteDeVenteRompue
    from controlvanne.models import RfidSession
    from fedow_core.models import Asset, Token

    monnaie_locale = _monnaie_du_lieu(tenant, Asset.TLF)
    tireuse, entetes_http = _creer_une_tireuse(tenant, prix_du_litre_en_euros="8.00")
    carte, portefeuille = _creer_une_carte(tenant, [(monnaie_locale, 1000)])
    client_http = ClientHttpDjango(HTTP_HOST=DOMAINE_DU_LIEU_PARTAGE)
    donnees_de_la_carte = {"tireuse_uuid": str(tireuse.uuid), "uid": carte.tag_id}

    reponse_du_badge = _poster(
        client_http, entetes_http, "authorize", donnees_de_la_carte
    )
    assert reponse_du_badge.json()["authorized"] is True

    with mock.patch(
        "BaseBillet.services_vente.encaisser_vente",
        side_effect=EgaliteDeVenteRompue("égalité rompue simulée par le test"),
    ):
        with pytest.raises(EgaliteDeVenteRompue):
            _poster(
                client_http,
                entetes_http,
                "event",
                {
                    **donnees_de_la_carte,
                    "event_type": "pour_end",
                    "volume_ml": "500.00",
                },
            )

    with tenant_context(tenant):
        assert Vente.objects.filter(carte=carte).count() == 0
        # La ligne ne porte pas la carte : elle est sur la vente et ses règlements
        # (Q-H2). On cherche la ligne par le fût du test.
        # / The line no longer carries the card: searched by the test's keg.
        assert (
            LigneArticle.objects.filter(
                pricesold__productsold__product=tireuse.fut_actif
            ).count()
            == 0
        )
        assert len(_debits_de_la_carte(carte)) == 0
        solde_de_la_carte = Token.objects.get(
            wallet=portefeuille, asset=monnaie_locale
        ).value
        assert solde_de_la_carte == 1000

        session_du_tirage = RfidSession.objects.get(carte=carte)
        assert session_du_tirage.ended_at is None


# ---------------------------------------------------------------------------
# Test dans un schéma dédié : le chaînage lit la numérotation des ventes du lieu
# / Test in a dedicated schema: chaining reads the venue's sale numbering
# ---------------------------------------------------------------------------


class TestTireuseVenteChainee(FastTenantTestCase):
    """
    La vente d'un tirage est chaînée sur la vente précédente du lieu, dans un schéma
    dédié (aucune autre vente n'y existe ; rollback à la fin de chaque test).
    / The pour's sale is chained on the venue's previous sale, in a dedicated schema.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_tireuse_vente"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-tireuse-vente.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test tireuse écrit la vente"

    def setUp(self):
        """
        Le lieu du test et le singleton de la caisse.
        / The test venue and the register singleton.
        """
        from laboutik.models import LaboutikConfiguration

        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse doit exister en base (PIEGES 9.86) : il porte la
        # clé de l'empreinte des ventes.
        # / The register singleton must exist in the database: it holds the HMAC key.
        LaboutikConfiguration.get_solo().save()

    def test_tirage_vente_chainee(self):
        """
        Une vente de caisse est encaissée (numéro 1), puis un tirage est servi. La vente
        du tirage porte le numéro 2, et son `previous_hmac` est l'empreinte de la vente
        numéro 1 : la tireuse écrit dans la même chaîne que la caisse. La chaîne du lieu
        ne signale aucune anomalie.
        / A register sale (number 1), then a pour: the pour's sale is number 2, chained on
        number 1; the venue chain reports nothing.
        """
        from BaseBillet.models import PaymentMethod, SaleOrigin
        from fedow_core.models import Asset
        from laboutik.integrity import verifier_chaine_ventes
        from laboutik.models import LaboutikConfiguration

        tarif_du_jus = creer_tarif_vendu(nom="Jus", prix_en_euros="3.50")
        vente_de_caisse = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[
                {
                    "pricesold": tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                },
            ],
            reglements=[
                {"moyen": PaymentMethod.CASH, "montant": 350},
            ],
        )
        assert vente_de_caisse.numero == 1

        monnaie_locale = _monnaie_du_lieu(self.tenant, Asset.TLF)
        tireuse, entetes_http = _creer_une_tireuse(
            self.tenant, prix_du_litre_en_euros="8.00"
        )
        carte, _portefeuille = _creer_une_carte(self.tenant, [(monnaie_locale, 1000)])

        _servir_un_tirage(
            TenantClient(self.tenant), entetes_http, tireuse, carte, "500.00"
        )

        with tenant_context(self.tenant):
            vente_du_tirage = _la_vente_du_tirage(carte)
            assert vente_du_tirage.numero == 2
            assert vente_du_tirage.previous_hmac == vente_de_caisse.hmac_hash
            assert len(vente_du_tirage.hmac_hash) == 64

            cle_de_l_empreinte = (
                LaboutikConfiguration.get_solo().get_or_create_hmac_key()
            )
            assert verifier_chaine_ventes(cle_de_l_empreinte) == []

            verifier_egalites(vente_du_tirage)
