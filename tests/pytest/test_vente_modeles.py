"""
Tests des modèles de la vente : champs entiers de l'article, contraintes de base, TVA
explicite, et champs ajoutés à `Paiement_stripe`.
/ Tests of the sale models: integer fields of the item, database constraints, explicit
VAT, and fields added to `Paiement_stripe`.

LOCALISATION : tests/pytest/test_vente_modeles.py

CE QUE CES TESTS REGARDENT
- `LigneArticle.save()` : un producteur qui ne passe pas `vat` garde la TVA du produit ;
  une TVA de 0 posée par le service de vente (marqueur `_tva_explicite`) est respectée ;
- les contraintes de base de données : une ligne dont les montants ne se tiennent pas, ou
  un règlement de 0, sont refusés par PostgreSQL, même hors du service ;
- `Paiement_stripe.vente` : la vente d'origine du paiement ;
- `Paiement_stripe.moyen` : le moyen Stripe (SEPA ou carte), posé à la mise à jour du
  paiement.
/ What these tests check: LigneArticle.save() VAT rules, database constraints, and the
two new Paiement_stripe fields.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-A-vente-reglement.md
(§2, §7, « Machine à états » T1) et CHANTIER-05-montants-entiers.md (§3).

CODE TESTÉ / CODE UNDER TEST
- BaseBillet/models.py — LigneArticle (champs, contraintes, save()), Paiement_stripe
  (vente, moyen, update_checkout_status()) ;
- BaseBillet/models_vente.py — Vente, Reglement.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin, rien ne reste
en base de dev (tests/PIEGES.md 13.1). Stripe est simulé (`mock_stripe`) : aucun appel
réseau.
/ Rolled-back transaction per test. Stripe is faked.

Lancer / Run : make test ARGS="tests/pytest/test_vente_modeles.py"
"""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from django_tenants.utils import tenant_context

from BaseBillet.models import (
    LigneArticle,
    Membership,
    Paiement_stripe,
    PaymentMethod,
    Price,
    PriceSold,
    Product,
    ProductSold,
    SaleOrigin,
    Tva,
)
from BaseBillet.models_vente import Reglement, Vente
from BaseBillet.services_vente import ajouter_article, ouvrir_vente
from fabriques_panier import (
    PREFIXE_DE_TEST,
    catalogue_stripe_simule,
    creer_adhesion,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from test_caracterisation_en_ligne import envoyer_un_evenement_stripe

pytestmark = pytest.mark.django_db


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, pendant tout le test. `tenant_context` (et non `schema_context`) :
    certains modèles lisent `connection.tenant` (tests/PIEGES.md 9.1).
    / The `lespass` venue for the whole test (tenant_context, not schema_context).
    """
    with tenant_context(tenant):
        yield tenant


def creer_un_tarif_vendu_dont_le_produit_porte_20_pourcent_de_tva(methode_caisse=None):
    """
    Un tarif vendu à 10,00 € dont le produit porte une TVA de 20 % sur sa fiche.
    / A sold price at 10.00 € whose product carries a 20 % VAT.

    C'est la TVA que `LigneArticle.save()` pose par défaut sur une ligne créée sans TVA.
    / This is the VAT that LigneArticle.save() sets by default on a line created without VAT.

    :param methode_caisse: `Product.methode_caisse` du produit (ex. une recharge), ou None
    """
    # Le taux est unique en base : on réutilise celui qui existe déjà.
    # / The rate is unique in the database: reuse the existing one.
    tva_a_20_pourcent, _tva_creee = Tva.objects.get_or_create(tva_rate=Decimal("20.00"))
    produit = Product.objects.create(
        name=f"{PREFIXE_DE_TEST} vente {identifiant_unique()}",
        categorie_article=Product.NONE,
        methode_caisse=methode_caisse,
        tva=tva_a_20_pourcent,
    )
    tarif = Price.objects.create(
        product=produit, name="Tarif unique", prix=Decimal("10.00"), publish=True
    )
    produit_vendu = ProductSold.objects.create(product=produit)
    tarif_vendu = PriceSold.objects.create(
        productsold=produit_vendu, price=tarif, prix=tarif.prix
    )
    return tarif_vendu


# --------------------------------------------------------------------------
# TVA de la ligne : défaut du produit, ou 0 explicite
# / Line VAT: product default, or explicit 0
# --------------------------------------------------------------------------


def test_create_sans_vat_garde_la_tva_du_produit(lieu):
    """
    Non-régression : une trentaine de producteurs créent leurs lignes sans passer `vat`.
    Ils comptent sur `LigneArticle.save()`, qui pose alors la TVA du produit (20 %).
    Ce test est vert sur le code d'avant le chantier 05 et doit le rester.
    / Non-regression: producers that do not pass `vat` get the product VAT (20 %).
    """
    tarif_vendu = creer_un_tarif_vendu_dont_le_produit_porte_20_pourcent_de_tva()

    ligne = LigneArticle.objects.create(
        pricesold=tarif_vendu,
        qty=Decimal("1"),
        amount=1000,
    )

    ligne.refresh_from_db()
    assert ligne.vat == Decimal("20.00")


def test_tva_zero_explicite_respectee_par_save(lieu):
    """
    Le service de vente écrit une TVA de 0 quand elle est voulue (une recharge cashless
    est hors chiffre d'affaires, TVA 0), même si le produit porte 20 %. Une recharge de
    20,00 € passe par `ajouter_article` avec un taux de 0 : la ligne relue en base garde
    ce 0, et non la TVA du produit.
    `ajouter_article` pose pour cela le marqueur `_tva_explicite = True` sur la ligne
    avant l'enregistrement (`LigneArticle.save()`).
    / A 0 VAT top-up written through `ajouter_article` keeps its 0 VAT, not the product's.
    """
    tarif_vendu = creer_un_tarif_vendu_dont_le_produit_porte_20_pourcent_de_tva(
        methode_caisse=Product.RECHARGE_EUROS
    )
    vente = ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE)

    ligne = ajouter_article(
        vente,
        pricesold=tarif_vendu,
        quantite=Decimal("1"),
        prix_unitaire=2000,
        taux_tva=Decimal("0"),
    )

    ligne.refresh_from_db()
    assert ligne.vat == Decimal("0.00")


# --------------------------------------------------------------------------
# Contraintes de base : PostgreSQL refuse des montants qui ne se tiennent pas
# / Database constraints: PostgreSQL refuses amounts that do not add up
# --------------------------------------------------------------------------


def test_contrainte_base_refuse_une_ligne_incoherente(lieu):
    """
    Trois écritures incohérentes, faites directement par l'ORM (sans le service de vente),
    sont refusées par PostgreSQL avec une `IntegrityError` :
    1. une ligne dont le net vendu n'est pas « catalogue − offert » (500 − 0 ≠ 499) ;
    2. une ligne rattachée à une vente dont « HT + TVA » ne fait pas le net vendu
       (417 + 84 ≠ 500) ;
    3. un règlement de 0 (aucun règlement de 0 n'est jamais écrit).
    / Three inconsistent writes, made through the ORM, are refused by PostgreSQL.

    Chaque écriture est dans son propre `transaction.atomic()` : après une erreur SQL, la
    transaction du test refuse toute autre requête tant qu'on n'est pas revenu au point
    de sauvegarde.
    / Each write has its own atomic() block: after an SQL error the test transaction
    refuses any other query until the savepoint is rolled back.
    """
    tarif_vendu = creer_un_tarif_vendu_dont_le_produit_porte_20_pourcent_de_tva()

    # 1. Net vendu faux, sur une ligne sans vente.
    # / 1. Wrong net, on a line without a sale.
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LigneArticle.objects.create(
                pricesold=tarif_vendu,
                qty=Decimal("1"),
                amount=500,
                total_catalogue=500,
                part_offerte=0,
                total_ttc=499,
            )

    # 2. HT + TVA faux, sur une ligne rattachée à une vente créée à la main.
    # Le net vendu, lui, est juste (500 − 0 = 500) : seule la 2ᵉ contrainte refuse.
    # / 2. Wrong HT + VAT on a line attached to a sale; only the 2nd constraint refuses.
    vente_creee_a_la_main = Vente.objects.create(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.VENTE,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LigneArticle.objects.create(
                vente=vente_creee_a_la_main,
                pricesold=tarif_vendu,
                qty=Decimal("1"),
                amount=500,
                vat=Decimal("20"),
                total_catalogue=500,
                part_offerte=0,
                total_ttc=500,
                total_ht=417,
                total_tva=84,
            )

    # 3. Règlement de 0.
    # / 3. Zero payment.
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Reglement.objects.create(
                vente=vente_creee_a_la_main,
                moyen=PaymentMethod.CASH,
                montant=0,
            )


# --------------------------------------------------------------------------
# Paiement_stripe : vente d'origine et moyen (T1)
# / Paiement_stripe: original sale and payment method (T1)
# --------------------------------------------------------------------------


def test_paiement_stripe_vente_d_origine(lieu):
    """
    Un paiement Stripe peut exister sans vente (le champ est vide par défaut). On lui
    rattache ensuite sa vente d'origine : elle est relue en base, et la vente retrouve
    son paiement par `vente.paiements_stripe`.
    / A Stripe payment exists without a sale (nullable); its original sale is then attached
    and read back, both ways.
    """
    paiement = Paiement_stripe.objects.create()
    paiement.refresh_from_db()
    assert paiement.vente is None

    vente_d_origine = Vente.objects.create(
        origine=SaleOrigin.LESPASS,
        nature=Vente.Nature.VENTE,
    )
    paiement.vente = vente_d_origine
    paiement.save()

    paiement.refresh_from_db()
    assert paiement.vente == vente_d_origine
    assert list(vente_d_origine.paiements_stripe.all()) == [paiement]


def preparer_la_session_stripe_relue(mock_stripe, forme_du_paiement):
    """
    Simule la session Stripe relue par `update_checkout_status()`, formulaire soumis
    (`complete`) et session non expirée.
    / Fakes the Stripe session read back by update_checkout_status(): submitted, not expired.

    `forme_du_paiement` choisit la branche de `update_checkout_status()`
    (BaseBillet/models.py, Paiement_stripe) :
    - "sepa_paiement_direct" : prélèvement SEPA soumis, pas encore débité ; Stripe
      renvoie un paiement (`payment_intent`) de type SEPA ;
    - "sepa_abonnement" : prélèvement SEPA soumis, pas encore débité ; pas de paiement
      direct, l'abonnement Stripe a un moyen de paiement par défaut de type SEPA ;
    - "carte" : paiement par carte, constaté payé (`paid`).
    / Picks the branch: direct SEPA, subscription SEPA (both unpaid yet), or paid by card.
    """
    mock_stripe.session.id = f"cs_test_vente_modeles_{identifiant_unique()}"
    mock_stripe.session.payment_status = "unpaid"
    mock_stripe.session.status = "complete"
    mock_stripe.session.expires_at = (timezone.now() + timedelta(hours=1)).timestamp()

    if forme_du_paiement == "carte":
        champs_de_la_session = {
            "payment_method_types": ["card"],
            "payment_intent": "pi_test_vente_modeles_carte",
        }
        mock_stripe.session.mode = "payment"
        mock_stripe.session.payment_status = "paid"

    if forme_du_paiement == "sepa_paiement_direct":
        champs_de_la_session = {
            "payment_method_types": ["card", "sepa_debit"],
            "payment_intent": "pi_test_vente_modeles_sepa",
        }
        mock_stripe.session.mode = "payment"
        champs_du_paiement = {
            "payment_method_types": ["sepa_debit"],
            "payment_method_options": {"sepa_debit": {}},
        }
        mock_stripe.pi.get = champs_du_paiement.get

    if forme_du_paiement == "sepa_abonnement":
        champs_de_la_session = {
            "payment_method_types": ["sepa_debit"],
            "payment_intent": None,
        }
        mock_stripe.session.mode = "subscription"
        mock_stripe.session.subscription = f"sub_test_{identifiant_unique()}"

    mock_stripe.session.get = champs_de_la_session.get


@pytest.mark.parametrize(
    "forme_du_paiement, moyen_attendu, statut_attendu",
    [
        # Le prélèvement n'est pas encore débité : le paiement reste en attente.
        # / The debit is not taken yet: the payment stays pending.
        (
            "sepa_paiement_direct",
            PaymentMethod.STRIPE_SEPA_NOFED,
            Paiement_stripe.PENDING,
        ),
        ("sepa_abonnement", PaymentMethod.STRIPE_SEPA_NOFED, Paiement_stripe.PENDING),
        ("carte", PaymentMethod.STRIPE_NOFED, Paiement_stripe.PAID),
    ],
)
def test_paiement_stripe_moyen_sepa_pose_a_la_mise_a_jour(
    lieu, mock_stripe, forme_du_paiement, moyen_attendu, statut_attendu
):
    """
    T1 : `update_checkout_status()` pose le moyen sur le paiement lui-même
    (`Paiement_stripe.moyen`), en plus des lignes. C'est la seule source du moyen d'un
    règlement Stripe une fois le champ `payment_method` retiré des lignes.
    - Un prélèvement SEPA reconnu reçoit « Stripe SEPA » (`SP`). Deux branches le
      reconnaissent : le paiement direct et l'abonnement.
    - Un paiement constaté payé qui n'est pas un SEPA reçoit « Stripe CB » (`SN`).
    / T1: SEPA detected -> SP (two branches); paid and not SEPA -> SN.
    """
    preparer_la_session_stripe_relue(mock_stripe, forme_du_paiement)
    paiement = Paiement_stripe.objects.create(
        checkout_session_id_stripe=mock_stripe.session.id,
        status=Paiement_stripe.PENDING,
    )

    # Le moyen de paiement par défaut de l'abonnement, relu chez Stripe : un SEPA.
    # / The subscription's default payment method, read back at Stripe: SEPA.
    moyen_de_paiement_stripe_simule = SimpleNamespace(type="sepa_debit")
    with patch(
        "stripe.PaymentMethod.retrieve", return_value=moyen_de_paiement_stripe_simule
    ):
        paiement.update_checkout_status()

    paiement.refresh_from_db()
    assert paiement.moyen == moyen_attendu
    assert paiement.status == statut_attendu


def test_paiement_stripe_moyen_sr_pose_a_la_creation_d_une_echeance(lieu, mock_stripe):
    """
    T1, abonnement : Stripe prélève une échéance d'un abonnement et envoie
    `invoice.paid`. Le webhook crée un nouveau paiement pour cette échéance
    (`new_entry_from_stripe_subscription_invoice`, PaiementStripe/views.py). Ce paiement
    porte le moyen « Stripe récurrent » (`SR`) dès sa création.
    Ce flux ne passe pas par `update_checkout_status()` : il n'y a pas de session de
    paiement, seulement une facture.
    / T1, subscription: the `invoice.paid` webhook creates the instalment payment,
    which carries `moyen = SR` from its creation.

    Même parcours que la caractérisation P15
    (test_caracterisation_en_ligne.py, `test_renouvellement_abonnement_iteration_et_statut_auto`).
    / Same flow as characterization P15.
    """
    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00", recurrente=True)
    identifiant_de_l_abonnement = f"sub_test_{identifiant_unique()}"
    identifiant_de_la_nouvelle_facture = f"in_test_{identifiant_unique()}"

    # ÉTAT DE DÉPART : un abonnement en cours, première échéance payée.
    # / STARTING STATE: a running subscription, first instalment paid.
    adhesion_abonnee = Membership.objects.create(
        user=acheteur,
        price=adhesion.tarif,
        status=Membership.AUTO,
        contribution_value=Decimal("15.00"),
        first_name="Ada",
        last_name="Lovelace",
        stripe_id_subscription=identifiant_de_l_abonnement,
        last_stripe_invoice="in_test_premiere_echeance",
        current_iteration=1,
        deadline=timezone.now() + timedelta(days=2),
    )

    # La facture relue chez Stripe : payée, une ligne de 15 € (en centimes).
    # / The invoice read back at Stripe: paid, one 15 € line (in cents).
    facture_stripe_simulee = SimpleNamespace(
        id=identifiant_de_la_nouvelle_facture,
        status="paid",
        # Une vraie facture Stripe porte toujours `amount_paid` : il est lu comme le
        # montant encaissé du paiement de l'échéance.
        # / A real Stripe invoice always carries `amount_paid`, read as the collected amount.
        amount_paid=1500,
        lines={"data": [SimpleNamespace(amount=1500, quantity=1)]},
        parent=SimpleNamespace(
            subscription_details=SimpleNamespace(
                subscription=identifiant_de_l_abonnement
            )
        ),
    )
    evenement_facture_payee = {
        "id": identifiant_de_la_nouvelle_facture,
        "billing_reason": "subscription_cycle",
        "paid": True,
        "subscription": identifiant_de_l_abonnement,
        "subscription_details": {
            "metadata": {
                "tenant": str(lieu.uuid),
                "membership_uuid": str(adhesion_abonnee.uuid),
                "price_uuid": str(adhesion.tarif.uuid),
            }
        },
        "metadata": {},
    }

    # Le catalogue Stripe et Celery sont simulés : la ligne de l'échéance demande un
    # identifiant de prix Stripe, et le webhook demande des tâches.
    # / Stripe catalogue and Celery are faked.
    with catalogue_stripe_simule():
        with taches_celery_enregistrees():
            with patch("stripe.Invoice.retrieve", return_value=facture_stripe_simulee):
                reponse_du_webhook = envoyer_un_evenement_stripe(
                    "invoice.paid", evenement_facture_payee
                )

    assert reponse_du_webhook.status_code == 202
    paiement_de_l_echeance = Paiement_stripe.objects.get(
        invoice_stripe=identifiant_de_la_nouvelle_facture
    )
    assert paiement_de_l_echeance.moyen == PaymentMethod.STRIPE_RECURENT
