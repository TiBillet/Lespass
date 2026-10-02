"""
Tests des ventes en ligne payées par Stripe : chaque producteur qui ouvre un paiement
Stripe ouvre aussi sa `Vente`, EN ATTENTE, avec ses articles.
/ Online sales paid through Stripe: every producer that opens a Stripe payment also opens
its `Vente`, PENDING, with its items.

LOCALISATION : tests/pytest/test_en_ligne_ecrit_la_vente.py

LA RÈGLE TESTÉE
Un paiement Stripe = une vente d'origine (R5). Quand un producteur crée ses lignes de
vente et son `Paiement_stripe` (le checkout) :
- il ouvre une vente de nature VENTE, avec l'origine qu'ont ses lignes et l'acheteur
  connu comme client ;
- ses lignes sont les articles de cette vente, écrits par le service de vente
  (`ajouter_article`) : montants entiers, TVA du produit (sinon celle du lieu) ;
- la vente est rangée dans `Paiement_stripe.vente` ;
- la vente reste EN_ATTENTE : aucun numéro, aucun règlement. Elle est encaissée plus
  tard, quand Stripe confirme le paiement (point d'encaissement unique).
Un paiement abandonné ou expiré laisse sa vente EN_ATTENTE, sans numéro (T6).
/ One Stripe payment = one original sale. Opened with the checkout, PENDING, no number,
no payment; its items are the payment's lines, written by the sale service.

LES PRODUCTEURS TESTÉS (un paiement Stripe direct chacun)
- billets hors panier (`TicketCreator`, formulaire de l'événement) ;
- adhésion en ligne (`MembershipValidator.get_checkout_stripe`) ;
- lien de paiement d'une adhésion validée par l'admin (`get_checkout_for_membership`) ;
- réservation de ressource hors panier (`validate_new_booking`) ;
- crowds : contribution à une initiative.
/ Producers tested: tickets, membership, membership payment link, booking, crowds
contribution.

LE PANIER (un paiement pour toute la commande)
`CommandeService.materialiser` ouvre UNE vente pour toute la commande, juste après la
`Commande`. Il la passe aux producteurs (adhésions, `TicketCreator`, `validate_new_booking`),
qui y ajoutent leurs lignes. `Commande.vente` et `Paiement_stripe.vente` portent cette
vente.
/ The cart opens ONE sale for the whole order and passes it to the producers.
`Commande.vente` and `Paiement_stripe.vente` carry it.

LES VOIES GRATUITES (total 0, pas de Stripe)
Une vente gratuite est encaissée à 0 : REGLEE, numérotée (c'est une opération
enregistrée), sans aucun règlement. Elle est encaissée par l'appelant qui écrit la
DERNIÈRE ligne, jamais avant :
- réservation à 0 € du front (`TicketCreator`, appelé par `ReservationValidator`) ;
- réservation gratuite de l'API v2 : les lignes « réservation gratuite » que l'API ajoute
  après `TicketCreator` entrent dans la MÊME vente (celle de `TicketCreator`, sinon une
  vente ouverte par l'API, origine API), puis la vente est encaissée. La quantité reçue
  en texte est convertie en entier ; une quantité décimale est refusée. Un prix non nul
  sur une réservation gratuite est entièrement offert (part offerte, règlement FREE) ;
- booking gratuit (`validate_new_booking`) ;
- panier gratuit (`CommandeService._finaliser_gratuit`). Un panier qui n'a que des
  réservations gratuites n'écrit aucune ligne : sa vente vide est ANNULEE, sans numéro.
Pas de vente sans ligne : une réservation gratuite seule, hors panier, n'ouvre pas de
vente. Une réservation à 0 € annulée après coup (place perdue) garde sa vente REGLEE à 0
(trou T16, accepté : montant 0, aucun effet comptable).
/ Free paths: the sale is settled at 0 (REGLEE, numbered, no payment) by the caller that
writes the LAST line. The API v2 free-booking lines go into the same sale. A cart with
free bookings only cancels its empty sale. No sale without a line.

LE RENOUVELLEMENT D'ABONNEMENT
La ligne de l'échéance est écrite dans une vente ouverte avec elle, au prix unitaire de
Stripe et à la quantité de la ligne de facture : son total catalogue vaut le total de la
facture. Le paiement de l'échéance porte la vente.
Le webhook `invoice.paid` relit l'adhésion sous verrou avant de comparer la facture à
`last_stripe_invoice` : la même facture envoyée deux fois (rejeu, envois simultanés)
ne crée qu'un paiement et qu'une vente.
/ Subscription renewal: the instalment line is written in a sale opened with it, at
Stripe's unit price and the invoice line quantity. The membership is read under lock:
the same invoice posted twice makes one payment and one sale.

LE MONTANT ENCAISSÉ
Quand Stripe confirme le paiement, le montant qu'il annonce (en centimes) est rangé dans
`Paiement_stripe.montant_encaisse`, par les deux chemins qui constatent le paiement :
- le retour de checkout (`update_checkout_status`) : `amount_total` de la session ;
- la facture d'abonnement payée (branche `INVOICE` du webhook `invoice.paid`) :
  `amount_paid` de la facture. Une facture payée par le solde du client vaut 0.
Le montant vient de Stripe, jamais du catalogue : les tests imposent un montant
différent du total des articles pour le prouver.
/ The amount Stripe announces is stored in `Paiement_stripe.montant_encaisse` by both
paths that record the payment. It comes from Stripe, never from the catalogue.

L'ENCAISSEMENT (point unique)
Quand le paiement passe « payé » (transition en `pre_save` de `Paiement_stripe`), la fin
de `set_ligne_article_paid` appelle `encaisser_vente_stripe(paiement)` :
- la vente passe REGLEE, numérotée, avec UN règlement au moyen du paiement
  (`Paiement_stripe.moyen`) et au montant encaissé (`montant_encaisse`) ;
- montant encaissé 0 (facture payée par le solde du client) : aucun règlement ;
- montant différent du catalogue : un article « Écart d'encaissement » (reçu en plus :
  quantité +1 ; reçu en moins : quantité −1), TVA 0, hors chiffre d'affaires, ligne
  VALID sans paiement Stripe, et une alerte au journal (ERROR) ;
- rejouée, elle ne réécrit rien (vente déjà REGLEE) ;
- une erreur d'encaissement ne sort jamais du `pre_save` (T4) : elle est journalisée,
  le client est payé, la vente reste EN_ATTENTE et se rejoue en rappelant la fonction ;
- un paiement sans vente (antérieur au chantier) n'encaisse rien, sans erreur.
Stripe dit « non » : `CANCELED` (aucun paiement requis) ou SEPA refusé → vente ANNULEE,
sans numéro. Une erreur d'annulation ne sort pas non plus du `pre_save` (T4) : elle est
journalisée, le paiement passe CANCELED, la vente reste telle quelle. Pour le SEPA
refusé, une erreur d'annulation ne sort pas du webhook : elle est journalisée, le
paiement passe « échoué », l'adhésion est réarmée. Une session expirée
ne change rien : la vente reste EN_ATTENTE (T6), et un paiement tardif (`EXPIRE → PAID`)
l'encaisse.
/ Settlement at the single point: REGLEE, one payment at the collected amount, gap item
when Stripe's amount differs, idempotent, errors never leave the pre_save; CANCELED and
refused SEPA cancel the sale (a cancellation error is logged, never raised); an expired
session changes nothing.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin, rien ne reste
en base de dev (tests/PIEGES.md 13.1). Stripe (session et catalogue) et Celery sont
simulés : aucun appel réseau, aucune tâche envoyée au worker.
/ Rolled-back transaction per test. Stripe and Celery are faked.

CODE PARCOURU / CODE EXERCISED
- BaseBillet/validators.py — TicketCreator, ReservationValidator,
  MembershipValidator.get_checkout_stripe ;
- api_v2/serializers.py — ReservationCreateSerializer (réservation gratuite) ;
- BaseBillet/views.py — MembershipMVT.get_checkout_for_membership ;
- booking/booking_engine.py — validate_new_booking, get_checkout_stripe ;
- crowds/views.py — InitiativeViewSet.contribute ;
- BaseBillet/services_commande.py — CommandeService.materialiser (panier) ;
- PaiementStripe/views.py — CreationPaiementStripe,
  new_entry_from_stripe_subscription_invoice (renouvellement d'abonnement) ;
- BaseBillet/services_vente.py — ouvrir_vente, ajouter_article, encaisser_vente,
  annuler_vente, encaisser_vente_stripe ;
- BaseBillet/signals.py — activator_free_reservation (réservation annulée faute de place) ;
- BaseBillet/signals.py — set_ligne_article_paid (point d'encaissement unique),
  transition PENDING → CANCELED ;
- BaseBillet/models.py — Paiement_stripe.update_checkout_status (montant encaissé) ;
- ApiBillet/views.py — paiment_stripe_validator, branche INVOICE (montant encaissé) ;
  webhook `checkout.session.async_payment_failed` (SEPA refusé) ;
- tests/pytest/conftest.py — la fixture `mock_stripe` (montants renvoyés par Stripe).

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-D-en-ligne-avoirs.md (§1,
§2.1, §2.2, §2.3, §3 voies gratuites, §5 tests 1 à 10, 14 et 15, trous T4, T5, T6, T16) ;
CHANTIER-05-SUIVI.md §4 (grandes relectures de la fiche D) ; brief
CHANTIER-05-briefs/05-D-4a.md.

Lancer / Run : make test ARGS="tests/pytest/test_en_ligne_ecrit_la_vente.py"
"""

import json
import logging
import time
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import stripe
from django.db import connection
from django.db.models import Q
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework import serializers

from api_v2.serializers import ReservationCreateSerializer
from AuthBillet.models import TibilletUser
from BaseBillet import services_vente
from BaseBillet.models import (
    LigneArticle,
    Membership,
    Paiement_stripe,
    PaymentMethod,
    Product,
    PromotionalCode,
    Reservation,
    SaleOrigin,
    Tva,
)
from BaseBillet.models_vente import Reglement, Vente
from BaseBillet.services_commande import CommandeService
from BaseBillet.services_panier import PanierSession
from BaseBillet.services_vente import EgaliteDeVenteRompue
from booking.models import Booking
from crowds.models import Contribution, Initiative
from laboutik.integrity import calculer_hmac_vente
from laboutik.models import LaboutikConfiguration
from PaiementStripe.views import new_entry_from_stripe_subscription_invoice
from fabriques_vente import verifier_egalites
from fabriques_panier import (
    PREFIXE_DE_TEST,
    ajouter_un_tarif,
    catalogue_stripe_simule,
    client_connecte,
    configuration_modifiee,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_ressource_avec_tarif,
    creer_un_billet_deja_vendu,
    creer_utilisateur,
    identifiant_unique,
    noms_des_taches,
    requete_avec_session,
    taches_celery_enregistrees,
)
from test_caracterisation_admin_api import reserver_une_ressource_sans_panier
from test_caracterisation_en_ligne import (
    EN_TETE_HTMX,
    adherer_sans_panier,
    envoyer_un_evenement_stripe,
    objet_session_de_paiement,
    reserver_des_billets_sans_panier,
    revenir_de_stripe_billetterie,
    soumettre_un_prelevement_sepa,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant, mock_stripe):
    """
    Le lieu `lespass`, avec Stripe (session + catalogue) et Celery simulés pendant tout le test.
    / The `lespass` venue, with Stripe (session + catalogue) and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    stripe=mock_stripe,
                    taches_demandees=taches_demandees,
                )


# --------------------------------------------------------------------------
# L'assistant commun : la vente du paiement, relue en base
# / The shared helper: the payment's sale, read back from the database
# --------------------------------------------------------------------------


def verifier_la_vente_en_attente_du_paiement(
    paiement, origine_attendue, client_attendu, total_catalogue_attendu
):
    """
    Relit le paiement et sa vente en base, puis vérifie la règle de la vente en ligne
    ouverte avec le checkout.
    / Reads the payment and its sale back, then checks the rule of an online sale opened
    with the checkout.

    Ce qui est vérifié :
    - le paiement porte sa vente (`Paiement_stripe.vente`) ;
    - la vente est une VENTE, EN_ATTENTE, sans numéro, sans aucun règlement ;
    - son origine est celle des lignes, son client est l'acheteur ;
    - ses articles sont exactement les lignes du paiement ;
    - la somme des totaux catalogue de ses articles vaut le montant attendu (centimes).
    / Checks: the payment carries its sale; VENTE, PENDING, no number, no payment;
    origin and client; items = payment lines; exact catalogue total in cents.

    :return: la vente, pour les vérifications propres à chaque test
    """
    paiement.refresh_from_db()
    assert paiement.vente_id is not None, (
        "Le paiement Stripe n'a pas de vente d'origine (Paiement_stripe.vente vide)."
    )
    vente = Vente.objects.get(pk=paiement.vente_id)

    assert vente.nature == Vente.Nature.VENTE
    assert vente.statut == Vente.Statut.EN_ATTENTE
    assert vente.numero is None
    assert vente.reglements.count() == 0
    assert vente.origine == origine_attendue
    assert vente.client == client_attendu

    articles_de_la_vente = set()
    for article in vente.articles.all():
        articles_de_la_vente.add(article.pk)
    lignes_du_paiement = set()
    for ligne in LigneArticle.objects.filter(paiement_stripe=paiement):
        lignes_du_paiement.add(ligne.pk)
    assert articles_de_la_vente == lignes_du_paiement

    total_catalogue_des_articles = 0
    for article in vente.articles.all():
        total_catalogue_des_articles += article.total_catalogue
    assert total_catalogue_des_articles == total_catalogue_attendu

    return vente


def donner_un_taux_de_tva_au_produit(produit, taux_en_pour_cent):
    """
    Rattache un taux de TVA au produit. `update()` : aucun signal de Product ne part.
    / Attaches a VAT rate to the product. update(): no Product signal fires.
    """
    tva, _tva_creee = Tva.objects.get_or_create(tva_rate=Decimal(taux_en_pour_cent))
    Product.objects.filter(pk=produit.pk).update(tva=tva)


# --------------------------------------------------------------------------
# Billets hors panier
# / Tickets without cart
# --------------------------------------------------------------------------


def test_checkout_billets_vente_en_attente_sans_numero(lieu):
    """
    Fiche test 1. Deux billets à 10 € et un billet réduit à 5 € réservés sans panier.
    Le checkout ouvre UNE vente : EN_ATTENTE, sans numéro, sans règlement, origine « en
    ligne » (LP), client = l'acheteur. Ses articles sont les deux lignes du paiement :
    2 × 1000 et 1 × 500, soit 2500 centimes au catalogue. La TVA est celle du produit
    (5,5 %), et le hors taxes est calculé avec elle.
    / Sheet test 1: two 10 € tickets and one 5 € ticket without cart. One PENDING sale,
    no number, no payment; items = the payment lines, 2500 cents; product VAT 5.5 %.
    """
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")
    tarif_reduit = concert.produit.prices.create(
        name="Tarif réduit", prix=Decimal("5.00"), publish=True
    )
    donner_un_taux_de_tva_au_produit(concert.produit, "5.50")

    reserver_des_billets_sans_panier(
        client, acheteur, concert.evenement, {concert.tarif: 2, tarif_reduit: 1}
    )
    reservation = Reservation.objects.get(
        user_commande=acheteur, event=concert.evenement
    )
    paiement = reservation.paiements.get()

    vente = verifier_la_vente_en_attente_du_paiement(
        paiement,
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=acheteur,
        total_catalogue_attendu=2500,
    )

    # Forme des lignes inchangée : prix unitaire et quantité d'aujourd'hui, toujours
    # « non payées » en attendant Stripe. TVA du produit, hors taxes calculé avec elle :
    # 2000 → 1896 HT ; 500 → 474 HT.
    # / Unchanged line shape; product VAT; excl. tax computed with it.
    lignes_par_prix_unitaire = {}
    for article in vente.articles.all():
        lignes_par_prix_unitaire[article.amount] = article
    ligne_plein_tarif = lignes_par_prix_unitaire[1000]
    ligne_tarif_reduit = lignes_par_prix_unitaire[500]

    assert ligne_plein_tarif.qty == Decimal("2")
    assert ligne_plein_tarif.total_catalogue == 2000
    assert ligne_plein_tarif.vat == Decimal("5.50")
    assert ligne_plein_tarif.total_ht == 1896
    assert ligne_plein_tarif.status == LigneArticle.UNPAID

    assert ligne_tarif_reduit.qty == Decimal("1")
    assert ligne_tarif_reduit.total_catalogue == 500
    assert ligne_tarif_reduit.vat == Decimal("5.50")
    assert ligne_tarif_reduit.total_ht == 474
    assert ligne_tarif_reduit.status == LigneArticle.UNPAID

    # Une seule vente pour cette réservation, et la réservation attend le paiement.
    # / One single sale for this reservation, which waits for the payment.
    assert (
        Vente.objects.filter(articles__reservation=reservation).distinct().count() == 1
    )
    reservation.refresh_from_db()
    assert reservation.status == Reservation.UNPAID


# --------------------------------------------------------------------------
# Adhésion en ligne, et lien de paiement d'une adhésion validée
# / Online membership, and payment link of a validated membership
# --------------------------------------------------------------------------


def test_adhesion_en_ligne_vente_en_attente(lieu):
    """
    Une adhésion à 15 € prise sans panier. Le checkout ouvre une vente EN_ATTENTE, sans
    numéro ni règlement, origine « en ligne » (LP), client = l'adhérent. Son unique
    article est la ligne de l'adhésion : 1500 centimes.
    / A 15 € membership without cart: one PENDING sale whose only item is the membership
    line, 1500 cents.
    """
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="15.00")

    adherer_sans_panier(client, acheteur, adhesion.tarif)
    adhesion_creee = Membership.objects.get(user=acheteur, price=adhesion.tarif)
    paiement = adhesion_creee.stripe_paiement.get()

    vente = verifier_la_vente_en_attente_du_paiement(
        paiement,
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=acheteur,
        total_catalogue_attendu=1500,
    )

    article_de_l_adhesion = vente.articles.get()
    assert article_de_l_adhesion.membership == adhesion_creee
    assert article_de_l_adhesion.amount == 1500
    assert article_de_l_adhesion.qty == Decimal("1")
    assert article_de_l_adhesion.status == LigneArticle.UNPAID


def preparer_une_adhesion_validee_par_l_admin():
    """
    ÉTAT DE DÉPART : une adhésion à validation manuelle (20 €), déjà validée par l'admin
    (`ADMIN_VALID`). Son lien de paiement est actif.
    / STARTING STATE: a manually-validated membership the admin already validated.
    """
    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="20.00", validation_manuelle=True)
    adhesion_validee = Membership.objects.create(
        user=acheteur,
        price=adhesion.tarif,
        status=Membership.ADMIN_VALID,
        contribution_value=Decimal("20.00"),
        first_name="Ada",
        last_name="Lovelace",
    )
    return adhesion_validee


def ouvrir_le_lien_de_paiement(adhesion_validee):
    """Le client ouvre le lien de paiement reçu par mail.
    / The member opens the payment link received by email."""
    client_de_l_adherent = client_connecte(adhesion_validee.user)
    return client_de_l_adherent.get(
        f"/memberships/{adhesion_validee.uuid}/get_checkout_for_membership/"
    )


def test_lien_de_paiement_adhesion_deux_liens_deux_ventes(lieu):
    """
    Le lien de paiement d'une adhésion validée (20 €) est ouvert deux fois. Entre les
    deux, la session Stripe du premier a expiré : la vue passe le premier paiement
    « expiré » et crée une nouvelle ligne et un nouveau paiement.
    Chaque paiement a SA vente (R5). La première reste EN_ATTENTE, sans numéro (T6) ;
    la seconde aussi, en attendant Stripe. Chacune porte l'article de 2000 centimes de
    son propre paiement.
    / The payment link is opened twice; the first Stripe session expired in between.
    Each payment has ITS sale; the first stays PENDING without number (T6).
    """
    adhesion_validee = preparer_une_adhesion_validee_par_l_admin()
    adherent = adhesion_validee.user

    ouvrir_le_lien_de_paiement(adhesion_validee)
    premier_paiement = adhesion_validee.stripe_paiement.get()

    # La session du premier paiement a expiré chez Stripe : le lien en recrée une.
    # / The first payment's session expired at Stripe: the link creates a new one.
    lieu.stripe.session.status = "expired"
    ouvrir_le_lien_de_paiement(adhesion_validee)
    second_paiement = adhesion_validee.stripe_paiement.exclude(
        pk=premier_paiement.pk
    ).get()

    premier_paiement.refresh_from_db()
    assert premier_paiement.status == Paiement_stripe.EXPIRE

    premiere_vente = verifier_la_vente_en_attente_du_paiement(
        premier_paiement,
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=adherent,
        total_catalogue_attendu=2000,
    )
    seconde_vente = verifier_la_vente_en_attente_du_paiement(
        second_paiement,
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=adherent,
        total_catalogue_attendu=2000,
    )
    assert premiere_vente.pk != seconde_vente.pk


# --------------------------------------------------------------------------
# Réservation de ressource hors panier
# / Resource booking without cart
# --------------------------------------------------------------------------


def test_booking_direct_vente_en_attente(lieu):
    """
    Un créneau d'une heure d'une ressource à 12 €/h, réservé par son formulaire, sans
    panier. Le checkout ouvre une vente EN_ATTENTE, sans numéro ni règlement, origine
    « en ligne » (LP), client = la personne qui réserve. Son unique article est la ligne
    du booking : 1200 centimes.
    / A one-hour slot at 12 €/h booked without cart: one PENDING sale whose only item is
    the booking line, 1200 cents.
    """
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="12.00")

    reserver_une_ressource_sans_panier(client, location)
    booking = Booking.objects.get(user=acheteur, resource=location.ressource)
    paiement = Paiement_stripe.objects.get(booking=booking)

    vente = verifier_la_vente_en_attente_du_paiement(
        paiement,
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=acheteur,
        total_catalogue_attendu=1200,
    )

    article_du_booking = vente.articles.get()
    assert article_du_booking.booking == booking
    assert article_du_booking.amount == 1200
    assert article_du_booking.status == LigneArticle.UNPAID
    booking.refresh_from_db()
    assert booking.status == Booking.WAITING_PAYMENT


# --------------------------------------------------------------------------
# Crowds : contribution à une initiative
# / Crowds: contribution to an initiative
# --------------------------------------------------------------------------


def test_crowds_contribution_vente_en_attente(lieu):
    """
    Une contribution de 15 € à une initiative en paiement direct. Le checkout ouvre une
    vente EN_ATTENTE, sans numéro ni règlement, origine « en ligne » (LP, tests/PIEGES.md
    9.21), client = la personne qui contribue. Son unique article est la ligne de la
    contribution : 1500 centimes. Le produit technique « crowdfunding » n'a pas de TVA :
    l'article prend le taux par défaut du lieu, ici 10 % (réglage patché, jamais
    enregistré : tests/PIEGES.md 13.22). Hors taxes : 1500 × 100 / 110 → 1364.
    / A 15 € direct-debit contribution: one PENDING sale, one 1500-cent item, venue
    default VAT (the technical product has none), patched to 10 %.
    """
    contributeur = creer_utilisateur()
    client = client_connecte(contributeur)
    initiative = Initiative.objects.create(
        name=f"{PREFIXE_DE_TEST} initiative {identifiant_unique()}",
        direct_debit=True,
    )

    with configuration_modifiee(vat_taxe=Decimal("10.00")):
        reponse = client.post(
            f"/crowd/{initiative.pk}/contribute/",
            data=json.dumps(
                {"amount": 1500, "contributor_name": "Ada", "description": "Merci"}
            ),
            content_type="application/json",
        )
    assert reponse.status_code == 200
    contribution = Contribution.objects.get(initiative=initiative)

    vente = verifier_la_vente_en_attente_du_paiement(
        contribution.paiement_stripe,
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=contributeur,
        total_catalogue_attendu=1500,
    )

    article_de_la_contribution = vente.articles.get()
    assert article_de_la_contribution.pk == contribution.ligne_article_id
    assert article_de_la_contribution.vat == Decimal("10.00")
    assert article_de_la_contribution.total_ht == 1364


# --------------------------------------------------------------------------
# Voies gratuites : la vente est encaissée à 0
# / Free paths: the sale is settled at 0
# --------------------------------------------------------------------------


def verifier_la_vente_gratuite_encaissee(vente, origine_attendue, client_attendu):
    """
    Relit la vente en base et vérifie la règle d'une vente gratuite : une VENTE,
    encaissée (REGLEE), numérotée, sans aucun règlement, pour un total catalogue de 0.
    / Reads the sale back and checks the free-sale rule: VENTE, settled, numbered, no
    payment, catalogue total 0.

    :return: la vente relue, pour les vérifications propres à chaque test
    """
    vente_relue = Vente.objects.get(pk=vente.pk)
    assert vente_relue.nature == Vente.Nature.VENTE
    assert vente_relue.statut == Vente.Statut.REGLEE, (
        f"La vente gratuite n'est pas encaissée (statut {vente_relue.statut})."
    )
    assert vente_relue.numero is not None
    assert vente_relue.reglements.count() == 0
    assert vente_relue.total_catalogue == 0
    assert vente_relue.origine == origine_attendue
    assert vente_relue.client == client_attendu
    return vente_relue


def la_vente_unique_de_la_reservation(reservation):
    """
    Rend LA vente dont les articles sont les lignes de la réservation. Échoue s'il n'y en
    a aucune, ou plus d'une.
    / Returns THE sale whose items are the reservation's lines. Fails on none or several.
    """
    ventes_de_la_reservation = Vente.objects.filter(
        articles__reservation=reservation
    ).distinct()
    assert ventes_de_la_reservation.count() == 1, (
        f"La réservation a {ventes_de_la_reservation.count()} vente(s), une attendue."
    )
    return ventes_de_la_reservation.get()


def test_reservation_gratuite_vente_encaissee_a_zero(lieu):
    """
    Un billet payant à 0 €, réservé sans panier. Aucun paiement Stripe n'est créé (le
    total vaut 0). La vente est ouverte avant la ligne, puis encaissée à 0 après elle :
    REGLEE, numérotée, sans règlement, origine « en ligne » (LP), client = l'acheteur.
    Son unique article est la ligne du billet, validée en « offert ».
    / A 0 € paid-category ticket without cart: no Stripe; the sale is settled at 0,
    numbered, no payment; its only item is the ticket line, valid as "free".
    """
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert_gratuit = creer_evenement_avec_tarif(prix="0.00")

    reserver_des_billets_sans_panier(
        client, acheteur, concert_gratuit.evenement, {concert_gratuit.tarif: 1}
    )
    reservation = Reservation.objects.get(
        user_commande=acheteur, event=concert_gratuit.evenement
    )
    assert lieu.stripe.mock_create.call_count == 0
    assert not reservation.paiements.exists()

    vente = verifier_la_vente_gratuite_encaissee(
        la_vente_unique_de_la_reservation(reservation),
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=acheteur,
    )
    article_du_billet = vente.articles.get()
    assert article_du_billet.total_catalogue == 0
    assert article_du_billet.status == LigneArticle.VALID
    assert article_du_billet.payment_method == PaymentMethod.FREE
    verifier_egalites(vente)


def test_reservation_freeres_seule_aucune_vente(lieu):
    """
    Témoin : une « réservation gratuite » (FREERES) seule, sans panier. Elle n'écrit
    aucune ligne de vente, donc aucune vente n'est ouverte : pas de vente sans ligne.
    / Witness: a free booking alone, without cart, writes no sale line: no sale is opened.
    """
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    atelier_gratuit = creer_evenement_avec_tarif(categorie=Product.FREERES)
    nombre_de_ventes_avant = Vente.objects.count()

    reserver_des_billets_sans_panier(
        client, acheteur, atelier_gratuit.evenement, {atelier_gratuit.tarif: 1}
    )
    reservation = Reservation.objects.get(
        user_commande=acheteur, event=atelier_gratuit.evenement
    )
    assert reservation.status == Reservation.FREERES_USERACTIV
    assert not LigneArticle.objects.filter(reservation=reservation).exists()
    assert Vente.objects.count() == nombre_de_ventes_avant


def test_reservation_a_zero_annulee_garde_sa_vente_reglee(lieu):
    """
    Trou T16 (accepté). Un visiteur anonyme réserve le dernier billet à 0 € d'un concert
    (jauge 1). Son compte n'est pas encore activé : la réservation attend la confirmation
    de son adresse mail (FREERES). La vente est déjà encaissée à 0.
    Il confirme 40 minutes plus tard : sa place n'est plus retenue, et une autre personne
    a pris le dernier billet entre-temps. La réservation passe ANNULEE. La vente, elle,
    reste REGLEE à 0, numérotée : montant 0, aucun effet comptable.
    / T16 (accepted): a 0 € reservation cancelled afterwards (seat lost while waiting for
    the email confirmation) keeps its sale settled at 0.
    """
    from datetime import timedelta as duree

    client_anonyme = client_connecte()
    concert = creer_evenement_avec_tarif(prix="0.00", jauge_max=1)
    email_du_visiteur = f"test+chantierpanier{identifiant_unique()}@mock.test"
    client_anonyme.post(
        f"/event/{concert.evenement.slug}/reservation/",
        {
            "event": str(concert.evenement.uuid),
            "email": email_du_visiteur,
            str(concert.tarif.uuid): "1",
        },
        **EN_TETE_HTMX,
    )
    visiteur = TibilletUser.objects.get(email=email_du_visiteur)
    reservation = Reservation.objects.get(
        user_commande=visiteur, event=concert.evenement
    )
    assert reservation.status == Reservation.FREERES

    # La place n'est plus retenue (plus de 30 minutes), et le dernier billet est vendu
    # à une autre personne. `update()` : `Reservation.datetime` est en auto_now
    # (tests/PIEGES.md 13.19).
    # / The seat is no longer held, and the last ticket is sold to someone else.
    Reservation.objects.filter(pk=reservation.pk).update(
        datetime=timezone.now() - duree(minutes=40)
    )
    creer_un_billet_deja_vendu(creer_utilisateur(), concert)

    # La confirmation de l'adresse mail active le compte : la machine à états annule la
    # réservation et lève une erreur pour prévenir le visiteur.
    # / Confirming the email activates the account: the reservation is cancelled.
    visiteur.is_active = True
    with pytest.raises(ValueError):
        visiteur.save()

    reservation.refresh_from_db()
    assert reservation.status == Reservation.CANCELED
    vente = verifier_la_vente_gratuite_encaissee(
        la_vente_unique_de_la_reservation(reservation),
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=visiteur,
    )
    verifier_egalites(vente)


def test_booking_gratuit_vente_encaissee_a_zero(lieu):
    """
    Un créneau d'une heure d'une ressource gratuite (0 €/h), réservé sans panier. Aucun
    paiement Stripe. La vente du booking est encaissée à 0 : REGLEE, numérotée, sans
    règlement, origine « en ligne » (LP), client = la personne qui réserve. Son unique
    article est la ligne du booking, validée en « offert ».
    / A free resource slot without cart: the booking's sale is settled at 0, numbered, no
    payment; its only item is the booking line, valid as "free".
    """
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location_gratuite = creer_ressource_avec_tarif(prix="0.00")

    reserver_une_ressource_sans_panier(client, location_gratuite)
    booking = Booking.objects.get(user=acheteur, resource=location_gratuite.ressource)
    assert lieu.stripe.mock_create.call_count == 0
    assert booking.status == Booking.FREERES_USERACTIV

    ventes_du_booking = Vente.objects.filter(articles__booking=booking).distinct()
    assert ventes_du_booking.count() == 1
    vente = verifier_la_vente_gratuite_encaissee(
        ventes_du_booking.get(),
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=acheteur,
    )
    article_du_booking = vente.articles.get()
    assert article_du_booking.booking == booking
    assert article_du_booking.status == LigneArticle.VALID
    assert article_du_booking.payment_method == PaymentMethod.FREE
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# API v2 : la réservation gratuite et ses lignes « réservation gratuite »
# / API v2: the free reservation and its free-booking lines
# --------------------------------------------------------------------------


def reserver_par_l_api_v2(evenement, quantites_par_tarif, email, prix_par_tarif=None):
    """
    Crée une réservation par le serializer d'entrée de l'API v2, comme le fait
    `ReservationViewSet.create` (api_v2/views.py) : validation, puis `save()`.
    / Creates a reservation through the API v2 input serializer, like the view does.

    `quantites_par_tarif` : {tarif: quantité}. La quantité est envoyée telle quelle : un
    entier, ou un texte comme le ferait un client JSON (`"2"`).
    `prix_par_tarif` : {tarif: prix en euros, texte}, le champ `price` d'un billet
    (api_v2/openapi-schema.yaml : un texte). Absent par défaut.
    / The quantity is sent as is. `prix_par_tarif`: the optional `price` field (a text).

    :return: la `Reservation` créée
    """
    if prix_par_tarif is None:
        prix_par_tarif = {}
    billets_demandes = []
    for tarif, quantite in quantites_par_tarif.items():
        billet_demande = {
            "@type": "Ticket",
            "identifier": str(tarif.uuid),
            "ticketQuantity": quantite,
        }
        if tarif in prix_par_tarif:
            billet_demande["price"] = prix_par_tarif[tarif]
        billets_demandes.append(billet_demande)
    serializer_de_reservation = ReservationCreateSerializer(
        data={
            "reservationFor": {"@type": "Event", "identifier": str(evenement.uuid)},
            "underName": {"@type": "Person", "email": email},
            "reservedTicket": billets_demandes,
        }
    )
    serializer_de_reservation.is_valid(raise_exception=True)
    return serializer_de_reservation.save()


@pytest.mark.parametrize("produit_cree_en_premier", ["payant", "reservation_gratuite"])
def test_reservation_gratuite_api_v2_meme_vente_que_ticket_creator(
    lieu, produit_cree_en_premier
):
    """
    Fiche test 14. Par l'API v2, dans le même appel : un billet d'un tarif payant à 0 €
    et une « réservation gratuite » (FREERES) du même événement.
    `TicketCreator` écrit la ligne du billet à 0 € dans SA vente ; l'API écrit ensuite la
    ligne de la réservation gratuite dans CETTE MÊME vente, puis l'encaisse :
    - une seule vente de plus en base ;
    - ses articles sont TOUTES les lignes de la réservation (les deux) ;
    - REGLEE, numérotée, sans règlement, origine API, client = la personne réservée.
    Les deux ordres des produits sont joués (tests/PIEGES.md 13.15).
    / Sheet test 14: a 0 € paid-category ticket and a free booking in one API call. One
    sale holds both lines and is settled at the end. Both product orders are played.
    """
    if produit_cree_en_premier == "payant":
        concert = creer_evenement_avec_tarif(prix="0.00")
        tarif_payant_a_zero = concert.tarif
        produit_gratuit = Product.objects.create(
            name=f"{PREFIXE_DE_TEST} gratuit {identifiant_unique()}",
            categorie_article=Product.FREERES,
        )
        concert.evenement.products.add(produit_gratuit)
        tarif_reservation_gratuite = produit_gratuit.prices.get(prix=0)
    else:
        concert = creer_evenement_avec_tarif(categorie=Product.FREERES)
        tarif_reservation_gratuite = concert.tarif
        produit_payant = Product.objects.create(
            name=f"{PREFIXE_DE_TEST} billet {identifiant_unique()}",
            categorie_article=Product.BILLET,
        )
        concert.evenement.products.add(produit_payant)
        tarif_payant_a_zero = ajouter_un_tarif(produit_payant, prix="0.00", nom="Gratuit")
    email_de_la_personne = f"test+chantierpanier{identifiant_unique()}@mock.test"
    nombre_de_ventes_avant = Vente.objects.count()

    reservation = reserver_par_l_api_v2(
        concert.evenement,
        {tarif_payant_a_zero: 1, tarif_reservation_gratuite: 1},
        email_de_la_personne,
    )

    assert lieu.stripe.mock_create.call_count == 0
    assert Vente.objects.count() == nombre_de_ventes_avant + 1
    personne_reservee = TibilletUser.objects.get(email=email_de_la_personne)
    vente = verifier_la_vente_gratuite_encaissee(
        la_vente_unique_de_la_reservation(reservation),
        origine_attendue=SaleOrigin.API,
        client_attendu=personne_reservee,
    )

    # Les articles de la vente sont exactement les deux lignes de la réservation.
    # / The sale's items are exactly the reservation's two lines.
    articles_de_la_vente = set()
    for article in vente.articles.all():
        articles_de_la_vente.add(article.pk)
    lignes_de_la_reservation = set()
    for ligne in LigneArticle.objects.filter(reservation=reservation):
        lignes_de_la_reservation.add(ligne.pk)
    assert len(lignes_de_la_reservation) == 2
    assert articles_de_la_vente == lignes_de_la_reservation
    assert vente.articles.filter(
        pricesold__price=tarif_reservation_gratuite, status=LigneArticle.FREERES
    ).count() == 1
    verifier_egalites(vente)


def test_api_v2_quantite_texte_castee_en_entier(lieu):
    """
    Fiche test 15. Par l'API v2, une « réservation gratuite » seule, quantité envoyée en
    texte : `"2"`. `TicketCreator` n'écrit aucune ligne (pas de vente) ; l'API écrit la
    ligne, dans une vente qu'elle ouvre (origine API), puis l'encaisse à 0. La quantité
    de la ligne est l'entier 2, comme le nombre de billets.
    / Sheet test 15: free booking alone through the API, quantity sent as text "2". The
    API opens its own sale (API origin), settles it at 0; the line quantity is 2.
    """
    atelier_gratuit = creer_evenement_avec_tarif(categorie=Product.FREERES)
    email_de_la_personne = f"test+chantierpanier{identifiant_unique()}@mock.test"

    reservation = reserver_par_l_api_v2(
        atelier_gratuit.evenement,
        {atelier_gratuit.tarif: "2"},
        email_de_la_personne,
    )

    assert reservation.tickets.count() == 2
    personne_reservee = TibilletUser.objects.get(email=email_de_la_personne)
    vente = verifier_la_vente_gratuite_encaissee(
        la_vente_unique_de_la_reservation(reservation),
        origine_attendue=SaleOrigin.API,
        client_attendu=personne_reservee,
    )
    ligne_de_la_reservation_gratuite = vente.articles.get()
    assert ligne_de_la_reservation_gratuite.qty == Decimal("2")
    assert ligne_de_la_reservation_gratuite.status == LigneArticle.FREERES
    verifier_egalites(vente)


def test_reservation_freeres_api_v2_prix_non_nul_offerte(lieu):
    """
    Par l'API v2, une « réservation gratuite » seule, avec un prix envoyé : `"5.00"`.
    La ligne est écrite au prix de 500 centimes, en « offert » (moyen FREE). C'est la
    règle « offert à montant non nul » du service de vente : la part offerte vaut tout
    le total catalogue (source OFFRIR), le net vendu vaut 0, et un règlement FREE de 500
    est ajouté. La vente, ouverte par l'API (origine API), est encaissée : REGLEE,
    numérotée, égalités tenues.
    / Free booking through the API with a price "5.00": the line is fully offered (500),
    one FREE payment of 500, the API's sale is settled and both equalities hold.
    """
    atelier_gratuit = creer_evenement_avec_tarif(categorie=Product.FREERES)
    email_de_la_personne = f"test+chantierpanier{identifiant_unique()}@mock.test"

    reservation = reserver_par_l_api_v2(
        atelier_gratuit.evenement,
        {atelier_gratuit.tarif: 1},
        email_de_la_personne,
        prix_par_tarif={atelier_gratuit.tarif: "5.00"},
    )

    vente = Vente.objects.get(pk=la_vente_unique_de_la_reservation(reservation).pk)
    assert vente.statut == Vente.Statut.REGLEE
    assert vente.numero is not None
    assert vente.origine == SaleOrigin.API
    assert vente.client == TibilletUser.objects.get(email=email_de_la_personne)

    article_offert = vente.articles.get()
    assert article_offert.amount == 500
    assert article_offert.total_catalogue == 500
    assert article_offert.part_offerte == 500
    assert article_offert.source_offert == LigneArticle.SourceOffert.OFFRIR
    assert article_offert.total_ttc == 0

    reglement_offert = vente.reglements.get()
    assert reglement_offert.moyen == PaymentMethod.FREE
    assert reglement_offert.montant == 500
    verifier_egalites(vente)


def test_api_v2_quantite_decimale_refusee(lieu):
    """
    Fiche test 15, second cas. Par l'API v2, une quantité décimale (`"2.5"`) est refusée
    avec une erreur de validation claire. Rien n'est créé : ni réservation, ni vente.
    / Sheet test 15, second case: a decimal quantity is refused with a clear validation
    error; nothing is created.
    """
    atelier_gratuit = creer_evenement_avec_tarif(categorie=Product.FREERES)
    email_de_la_personne = f"test+chantierpanier{identifiant_unique()}@mock.test"
    nombre_de_ventes_avant = Vente.objects.count()

    with pytest.raises(serializers.ValidationError):
        reserver_par_l_api_v2(
            atelier_gratuit.evenement,
            {atelier_gratuit.tarif: "2.5"},
            email_de_la_personne,
        )

    assert not Reservation.objects.filter(event=atelier_gratuit.evenement).exists()
    assert Vente.objects.count() == nombre_de_ventes_avant


# --------------------------------------------------------------------------
# Panier : une seule vente pour toute la commande
# / Cart: one single sale for the whole order
# --------------------------------------------------------------------------


def payer_le_panier(panier, acheteur):
    """
    Matérialise le panier comme le fait la vue du panier (`PanierMVT.checkout`), puis
    relit la commande en base.
    / Materializes the cart the way the cart view does, then reads the order back.
    """
    commande, _succes = CommandeService.materialiser(
        panier,
        acheteur,
        first_name=acheteur.first_name,
        last_name=acheteur.last_name,
        email=acheteur.email,
    )
    commande.refresh_from_db()
    return commande


def montants_des_articles(vente):
    """
    Liste triée des couples (prix unitaire, quantité) des articles de la vente.
    / Sorted list of (unit price, quantity) pairs of the sale's items.
    """
    montants = []
    for article in vente.articles.all():
        montants.append((article.amount, article.qty))
    montants.sort()
    return montants


def test_panier_billets_booking_adhesion_une_seule_vente(lieu):
    """
    Fiche test 5. Un panier réunit une adhésion (15 €), deux billets à 10 € d'un
    concert, un billet à 8 € d'un spectacle et un créneau d'une heure d'une ressource
    (12 €/h). Il est payé par UN paiement Stripe, donc par UNE vente (R5).
    La vente est ouverte par le panier et passée aux producteurs :
    - une seule vente de plus en base ;
    - EN_ATTENTE, sans numéro, sans règlement, origine « en ligne » (LP), client =
      l'acheteur ;
    - ses articles sont TOUTES les lignes du paiement (adhésion, billets des deux
      événements, booking) : 1500 + 2 × 1000 + 800 + 1200 = 5500 centimes ;
    - la commande et le paiement portent cette même vente.
    / Sheet test 5: membership + tickets of two events + one resource slot in one cart.
    One payment, one sale opened by the cart; its items are ALL the payment lines,
    5500 cents; the order and the payment carry that sale.
    """
    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00")
    concert = creer_evenement_avec_tarif(prix="10.00", jours_avant_l_evenement=7)
    spectacle = creer_evenement_avec_tarif(prix="8.00", jours_avant_l_evenement=9)
    location = creer_ressource_avec_tarif(prix="12.00")
    nombre_de_ventes_avant = Vente.objects.count()

    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)
    panier.add_ticket(spectacle.evenement.uuid, spectacle.tarif.uuid, qty=1)
    panier.add_resource(
        resource_uuid=location.ressource.pk,
        price_uuid=location.tarif.uuid,
        start_datetime=location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=1,
    )
    commande = payer_le_panier(panier, acheteur)
    paiement = commande.paiement_stripe

    vente = verifier_la_vente_en_attente_du_paiement(
        paiement,
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=acheteur,
        total_catalogue_attendu=5500,
    )

    # Une seule vente pour toute la commande : aucun producteur n'ouvre la sienne.
    # / One single sale for the whole order: no producer opens its own.
    assert Vente.objects.count() == nombre_de_ventes_avant + 1
    assert commande.vente_id == vente.pk
    assert paiement.vente_id == vente.pk

    # Les quatre lignes, chacune avec le prix unitaire et la quantité d'aujourd'hui.
    # / The four lines, each with today's unit price and quantity.
    assert montants_des_articles(vente) == [
        (800, Decimal("1")),
        (1000, Decimal("2")),
        (1200, Decimal("1")),
        (1500, Decimal("1")),
    ]
    assert vente.articles.filter(membership__commande=commande).count() == 1
    assert vente.articles.filter(reservation__commande=commande).count() == 2
    assert vente.articles.filter(booking__commande=commande).count() == 1
    for article in vente.articles.all():
        assert article.status == LigneArticle.UNPAID


def test_panier_deux_codes_promo_et_prix_libre_une_seule_vente(lieu):
    """
    Un seul événement, mais QUATRE appels à `TicketCreator` sur la même réservation :
    - un billet du produit A (10 €) avec le code A (-50 %) → 500 centimes ;
    - un billet du produit B (10 €) avec le code B (-20 %) → 800 centimes ;
      (un appel par code promo) ;
    - deux billets d'un tarif à prix libre du produit A, saisis à 12 € puis à 7 €
      (un appel par article à prix libre).
    Toutes ces lignes vont dans LA vente du panier : une seule vente de plus, dont les
    articles sont les quatre lignes du paiement, 500 + 800 + 1200 + 700 = 3200 centimes.
    / One event, FOUR TicketCreator calls (two promo codes, two free-price items): all
    lines go into THE cart's sale, 3200 cents.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    produit_b = Product.objects.create(
        name=f"{PREFIXE_DE_TEST} billet B {identifiant_unique()}",
        categorie_article=Product.BILLET,
    )
    concert.evenement.products.add(produit_b)
    tarif_b = ajouter_un_tarif(produit_b, prix="10.00", nom="Plein tarif B")
    tarif_a_prix_libre = ajouter_un_tarif(
        concert.produit, prix="5.00", nom="Prix libre", free_price=True
    )
    code_du_produit_a = PromotionalCode.objects.create(
        name=f"{PREFIXE_DE_TEST}_moitie_{identifiant_unique()}",
        discount_rate=Decimal("50.00"),
        product=concert.produit,
    )
    code_du_produit_b = PromotionalCode.objects.create(
        name=f"{PREFIXE_DE_TEST}_vingt_{identifiant_unique()}",
        discount_rate=Decimal("20.00"),
        product=produit_b,
    )
    nombre_de_ventes_avant = Vente.objects.count()

    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(
        concert.evenement.uuid,
        concert.tarif.uuid,
        qty=1,
        promotional_code_name=code_du_produit_a.name,
    )
    panier.add_ticket(
        concert.evenement.uuid,
        tarif_b.uuid,
        qty=1,
        promotional_code_name=code_du_produit_b.name,
    )
    panier.add_ticket(
        concert.evenement.uuid, tarif_a_prix_libre.uuid, qty=1, custom_amount="12.00"
    )
    panier.add_ticket(
        concert.evenement.uuid, tarif_a_prix_libre.uuid, qty=1, custom_amount="7.00"
    )
    commande = payer_le_panier(panier, acheteur)

    vente = verifier_la_vente_en_attente_du_paiement(
        commande.paiement_stripe,
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=acheteur,
        total_catalogue_attendu=3200,
    )

    assert Vente.objects.count() == nombre_de_ventes_avant + 1
    assert commande.vente_id == vente.pk
    assert montants_des_articles(vente) == [
        (500, Decimal("1")),
        (700, Decimal("1")),
        (800, Decimal("1")),
        (1200, Decimal("1")),
    ]
    # Les quatre lignes sont sur la même réservation.
    # / The four lines are on the same reservation.
    reservation = commande.reservations.get()
    assert vente.articles.filter(reservation=reservation).count() == 4


def test_panier_gratuit_vente_encaissee_a_zero(lieu):
    """
    Une commande à 0 € : un billet d'un concert à 0 € et une adhésion à 0 €. Aucun
    paiement Stripe n'est créé. La vente ouverte par le panier est encaissée à 0 après
    le passage des lignes : REGLEE, numérotée, sans règlement, origine « en ligne » (LP),
    client = l'acheteur. La commande la porte, et ses articles sont les deux lignes de la
    commande, pour 0 centime.
    / A 0 € order (ticket + membership): no Stripe; the cart's sale is settled at 0 after
    the lines, numbered, no payment; the order carries it; its items are the two lines.
    """
    acheteur = creer_utilisateur()
    concert_gratuit = creer_evenement_avec_tarif(prix="0.00")
    adhesion_gratuite = creer_adhesion(prix="0.00")
    nombre_de_ventes_avant = Vente.objects.count()

    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(
        concert_gratuit.evenement.uuid, concert_gratuit.tarif.uuid, qty=1
    )
    panier.add_membership(adhesion_gratuite.tarif.uuid)
    commande = payer_le_panier(panier, acheteur)

    assert lieu.stripe.mock_create.call_count == 0
    assert commande.paiement_stripe is None
    assert commande.vente_id is not None, (
        "La commande gratuite n'a pas de vente (Commande.vente vide)."
    )
    assert Vente.objects.count() == nombre_de_ventes_avant + 1

    vente = verifier_la_vente_gratuite_encaissee(
        Vente.objects.get(pk=commande.vente_id),
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=acheteur,
    )

    # Les articles de la vente sont exactement les lignes de la commande.
    # / The sale's items are exactly the order's lines.
    articles_de_la_vente = set()
    for article in vente.articles.all():
        articles_de_la_vente.add(article.pk)
    lignes_de_la_commande = set()
    for ligne in LigneArticle.objects.filter(
        Q(reservation__commande=commande) | Q(membership__commande=commande)
    ):
        lignes_de_la_commande.add(ligne.pk)
    assert len(lignes_de_la_commande) == 2
    assert articles_de_la_vente == lignes_de_la_commande
    verifier_egalites(vente)


def test_panier_freeres_seules_vente_vide_annulee(lieu):
    """
    Un panier qui n'a qu'une « réservation gratuite » (FREERES). Aucune ligne de vente
    n'est écrite. La vente ouverte par le panier reste donc vide : elle est ANNULEE à la
    finalisation, sans numéro, sans article, sans règlement. La commande la porte.
    / A cart with free bookings only writes no sale line: its empty sale is cancelled,
    without number, item or payment.
    """
    acheteur = creer_utilisateur()
    atelier_gratuit = creer_evenement_avec_tarif(categorie=Product.FREERES)

    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(
        atelier_gratuit.evenement.uuid, atelier_gratuit.tarif.uuid, qty=1
    )
    commande = payer_le_panier(panier, acheteur)

    assert commande.paiement_stripe is None
    assert not LigneArticle.objects.filter(reservation__commande=commande).exists()
    vente = Vente.objects.get(pk=commande.vente_id)
    assert vente.statut == Vente.Statut.ANNULEE, (
        f"La vente vide du panier n'est pas annulée (statut {vente.statut})."
    )
    assert vente.numero is None
    assert vente.articles.count() == 0
    assert vente.reglements.count() == 0


# --------------------------------------------------------------------------
# Renouvellement d'abonnement : la ligne de l'échéance dans sa vente
# / Subscription renewal: the instalment line in its sale
# --------------------------------------------------------------------------


def creer_un_abonnement_en_cours(abonne):
    """
    ÉTAT DE DÉPART : un abonnement en cours (adhésion à 15 €, récurrente), première
    échéance payée.
    / STARTING STATE: a running subscription, first instalment paid.
    """
    adhesion = creer_adhesion(prix="15.00", recurrente=True)
    adhesion_abonnee = Membership.objects.create(
        user=abonne,
        price=adhesion.tarif,
        status=Membership.AUTO,
        contribution_value=Decimal("15.00"),
        first_name="Ada",
        last_name="Lovelace",
        stripe_id_subscription=f"sub_test_{identifiant_unique()}",
        last_stripe_invoice="in_test_premiere_echeance",
        current_iteration=1,
        deadline=timezone.now() + timedelta(days=2),
    )
    return adhesion_abonnee


def ligne_de_facture_simulee(total_de_la_ligne, quantite, prix_unitaire_decimal):
    """
    Une ligne de facture Stripe, avec la forme de l'API utilisée par le projet
    (stripe-python 12, version d'API « basil ») : une ligne de facture n'a pas
    d'attribut `price` ; le prix unitaire est dans `pricing.unit_amount_decimal`
    (texte, en centimes). `amount` est le TOTAL de la ligne.
    `prix_unitaire_decimal=None` : la ligne n'a pas de `pricing` du tout.
    / A Stripe invoice line, shaped like the project's API version (basil): no `price`
    attribute; the unit price is `pricing.unit_amount_decimal` (text, cents); `amount`
    is the line TOTAL. `prix_unitaire_decimal=None`: no `pricing` at all.
    """
    if prix_unitaire_decimal is None:
        return SimpleNamespace(amount=total_de_la_ligne, quantity=quantite)

    return SimpleNamespace(
        amount=total_de_la_ligne,
        quantity=quantite,
        pricing=SimpleNamespace(
            type="price_details",
            price_details=SimpleNamespace(
                price="price_test_abonnement", product="prod_test_abonnement"
            ),
            unit_amount_decimal=prix_unitaire_decimal,
        ),
    )


def payer_l_echeance(adhesion_abonnee, ligne_de_facture):
    """
    Stripe prélève une échéance : la facture (une ligne) est relue chez Stripe
    (simulé), puis l'échéance crée sa ligne de vente et son paiement, comme le fait le
    webhook `invoice.paid` (ApiBillet/views.py).
    / Stripe charges an instalment: the invoice is read back (faked), then the
    instalment creates its sale line and payment, as the `invoice.paid` webhook does.

    :return: le `Paiement_stripe` de l'échéance
    """
    identifiant_de_la_nouvelle_facture = f"in_test_{identifiant_unique()}"
    facture_stripe_simulee = SimpleNamespace(
        id=identifiant_de_la_nouvelle_facture,
        status="paid",
        amount_paid=ligne_de_facture.amount,
        lines={"data": [ligne_de_facture]},
        parent=SimpleNamespace(
            subscription_details=SimpleNamespace(
                subscription=adhesion_abonnee.stripe_id_subscription
            )
        ),
    )

    with patch("stripe.Invoice.retrieve", return_value=facture_stripe_simulee):
        paiement_de_l_echeance = new_entry_from_stripe_subscription_invoice(
            user=adhesion_abonnee.user,
            id_invoice=identifiant_de_la_nouvelle_facture,
            membership=adhesion_abonnee,
        )

    assert paiement_de_l_echeance.source == Paiement_stripe.INVOICE
    return paiement_de_l_echeance


def test_abonnement_quantite_2_prix_unitaire(lieu):
    """
    Fiche test 10, partie écriture. Stripe prélève une échéance d'un abonnement de
    quantité 2, au prix unitaire de 15 €. La ligne de facture porte `quantity` = 2,
    `amount` = 3000 (le TOTAL de la ligne) et `pricing.unit_amount_decimal` = "1500"
    (le prix unitaire). La facture vaut donc 30 €.
    La ligne de vente est écrite au prix UNITAIRE (1500) et à la quantité de la facture
    (2) : son total catalogue vaut la facture, 3000 centimes, et pas le double. Son
    `PriceSold` est au prix unitaire (15,00 €). Elle est l'article d'une vente ouverte
    avec elle : EN_ATTENTE, sans numéro ni règlement, origine « webhook Stripe » (WK),
    client = l'abonné. Le paiement de l'échéance porte cette vente.
    / Sheet test 10, writing part: a quantity-2 instalment at 15 € each. The line is
    written at the UNIT price and the invoice quantity: catalogue total = invoice total,
    3000 cents, not twice. It is the item of a PENDING sale carried by the payment.
    """
    abonne = creer_utilisateur()
    adhesion_abonnee = creer_un_abonnement_en_cours(abonne)

    paiement_de_l_echeance = payer_l_echeance(
        adhesion_abonnee,
        ligne_de_facture_simulee(
            total_de_la_ligne=3000, quantite=2, prix_unitaire_decimal="1500"
        ),
    )

    vente = verifier_la_vente_en_attente_du_paiement(
        paiement_de_l_echeance,
        origine_attendue=SaleOrigin.WEBHOOK,
        client_attendu=abonne,
        total_catalogue_attendu=3000,
    )

    article_de_l_echeance = vente.articles.get()
    assert article_de_l_echeance.amount == 1500
    assert article_de_l_echeance.qty == Decimal("2")
    assert article_de_l_echeance.pricesold.prix == Decimal("15.00")
    assert article_de_l_echeance.membership == adhesion_abonnee
    assert article_de_l_echeance.payment_method == PaymentMethod.STRIPE_RECURENT
    assert article_de_l_echeance.status == LigneArticle.UNPAID


def test_abonnement_prix_unitaire_decimal_arrondi_demi_haut(lieu):
    """
    Le prix unitaire Stripe peut porter des décimales de centime :
    `unit_amount_decimal` = "1500.5". Il est arrondi au centime, au demi supérieur :
    1501 (ni 1500 par troncature, ni 1500 par l'arrondi « au pair »). Quantité 2 :
    l'article vaut 1501 × 2 = 3002 centimes au catalogue. La ligne de facture, elle,
    vaut 3001 : l'écart d'un centime sera traité à l'encaissement, pas ici.
    / Stripe's unit price may carry cent decimals: "1500.5" is rounded half-up to 1501.
    Quantity 2: 3002 cents at catalogue; the 1-cent gap with the invoice line (3001) is
    handled at settlement, not here.
    """
    abonne = creer_utilisateur()
    adhesion_abonnee = creer_un_abonnement_en_cours(abonne)

    paiement_de_l_echeance = payer_l_echeance(
        adhesion_abonnee,
        ligne_de_facture_simulee(
            total_de_la_ligne=3001, quantite=2, prix_unitaire_decimal="1500.5"
        ),
    )

    vente = verifier_la_vente_en_attente_du_paiement(
        paiement_de_l_echeance,
        origine_attendue=SaleOrigin.WEBHOOK,
        client_attendu=abonne,
        total_catalogue_attendu=3002,
    )

    article_de_l_echeance = vente.articles.get()
    assert article_de_l_echeance.amount == 1501
    assert article_de_l_echeance.qty == Decimal("2")
    assert article_de_l_echeance.pricesold.prix == Decimal("15.01")


def test_abonnement_sans_pricing_ligne_entiere_quantite_1(lieu, caplog):
    """
    Une ligne de facture sans `pricing` (quantité 2, total 3000) : le prix unitaire
    Stripe est inconnu. L'article vaut alors la ligne ENTIÈRE : prix unitaire = le total
    de la ligne (3000), quantité 1. Jamais 3000 × 2 : pas de double compte. Un
    avertissement est journalisé.
    / An invoice line without `pricing` (quantity 2, total 3000): the item is the WHOLE
    line, 3000 × 1, never 3000 × 2; a warning is logged.
    """
    abonne = creer_utilisateur()
    adhesion_abonnee = creer_un_abonnement_en_cours(abonne)

    with caplog.at_level("WARNING", logger="PaiementStripe.views"):
        paiement_de_l_echeance = payer_l_echeance(
            adhesion_abonnee,
            ligne_de_facture_simulee(
                total_de_la_ligne=3000, quantite=2, prix_unitaire_decimal=None
            ),
        )

    vente = verifier_la_vente_en_attente_du_paiement(
        paiement_de_l_echeance,
        origine_attendue=SaleOrigin.WEBHOOK,
        client_attendu=abonne,
        total_catalogue_attendu=3000,
    )

    article_de_l_echeance = vente.articles.get()
    assert article_de_l_echeance.amount == 3000
    assert article_de_l_echeance.qty == Decimal("1")
    assert article_de_l_echeance.pricesold.prix == Decimal("30.00")

    avertissements_de_l_echeance = []
    for enregistrement in caplog.records:
        if (
            enregistrement.name == "PaiementStripe.views"
            and enregistrement.levelname == "WARNING"
        ):
            avertissements_de_l_echeance.append(enregistrement)
    assert len(avertissements_de_l_echeance) == 1


# --------------------------------------------------------------------------
# Le montant encaissé : ce que Stripe annonce, rangé sur le paiement
# / The collected amount: what Stripe announces, stored on the payment
# --------------------------------------------------------------------------


def test_fixture_stripe_rend_le_total_des_articles(lieu):
    """
    La session simulée par `mock_stripe` annonce, en centimes, le total catalogue de la
    vente du paiement le plus récent qui porte son identifiant de session :
    - un paiement sans vente : 0 ;
    - puis deux billets à 10 € et un billet réduit à 5 €, réservés sans panier : 2500.
    / The simulated session announces the catalogue total of the newest payment's sale:
    0 for a payment without sale, then 2500 cents after a ticket checkout.
    """
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)

    # Un paiement sans vente, qui porte l'identifiant de la session simulée.
    # / A payment without sale, carrying the simulated session id.
    Paiement_stripe.objects.create(
        user=acheteur, checkout_session_id_stripe=lieu.stripe.session.id
    )
    assert lieu.stripe.session.amount_total == 0

    concert = creer_evenement_avec_tarif(prix="10.00")
    tarif_reduit = concert.produit.prices.create(
        name="Tarif réduit", prix=Decimal("5.00"), publish=True
    )
    reserver_des_billets_sans_panier(
        client, acheteur, concert.evenement, {concert.tarif: 2, tarif_reduit: 1}
    )

    assert lieu.stripe.session.amount_total == 2500


def test_fixture_stripe_facture_rend_le_total_des_articles(lieu):
    """
    La facture simulée par `mock_stripe` (`stripe.Invoice.retrieve`) est payée et annonce
    le total catalogue de la vente du paiement qui porte son identifiant de facture :
    - l'échéance d'un abonnement de quantité 2 à 15 € : 3000 ;
    - une facture qu'aucun paiement ne porte : 0.
    / The simulated invoice is paid and announces the catalogue total of the sale of the
    payment carrying its id: 3000 for a quantity-2 instalment, 0 for an unknown invoice.
    """
    abonne = creer_utilisateur()
    adhesion_abonnee = creer_un_abonnement_en_cours(abonne)
    paiement_de_l_echeance = payer_l_echeance(
        adhesion_abonnee,
        ligne_de_facture_simulee(
            total_de_la_ligne=3000, quantite=2, prix_unitaire_decimal="1500"
        ),
    )

    facture_de_l_echeance = stripe.Invoice.retrieve(
        paiement_de_l_echeance.invoice_stripe, stripe_account=None
    )
    assert facture_de_l_echeance.status == "paid"
    assert facture_de_l_echeance.amount_paid == 3000

    facture_inconnue = stripe.Invoice.retrieve(
        f"in_test_{identifiant_unique()}", stripe_account=None
    )
    assert facture_inconnue.amount_paid == 0


def test_paiement_confirme_pose_le_montant_encaisse(lieu):
    """
    Deux billets à 10 € et un billet réduit à 5 € (2500 centimes au catalogue), réservés
    sans panier. Stripe annonce 2400 centimes pour la session. Au retour de checkout
    payé, le paiement porte `montant_encaisse` = 2400 : le montant vient de Stripe, pas
    du catalogue.
    / Checkout paid: Stripe announces 2400 cents (catalogue 2500); the payment stores
    `montant_encaisse` = 2400, taken from Stripe, not from the catalogue.
    """
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")
    tarif_reduit = concert.produit.prices.create(
        name="Tarif réduit", prix=Decimal("5.00"), publish=True
    )
    reserver_des_billets_sans_panier(
        client, acheteur, concert.evenement, {concert.tarif: 2, tarif_reduit: 1}
    )
    reservation = Reservation.objects.get(
        user_commande=acheteur, event=concert.evenement
    )
    paiement = reservation.paiements.get()

    # Stripe annonce un montant différent du catalogue.
    # / Stripe announces an amount different from the catalogue.
    lieu.stripe.session.amount_total = 2400

    revenir_de_stripe_billetterie(client, paiement)

    paiement.refresh_from_db()
    assert paiement.status in (Paiement_stripe.PAID, Paiement_stripe.VALID)
    assert paiement.montant_encaisse == 2400


def envoyer_la_facture_payee(
    lieu, adhesion_abonnee, montant_paye, ligne_de_facture=None
):
    """
    Stripe prélève une échéance de l'abonnement et envoie `invoice.paid` au webhook du
    lieu. La facture relue chez Stripe annonce `montant_paye` centimes (`amount_paid`).
    Le webhook crée le paiement de l'échéance, puis le constate payé par la branche
    `INVOICE`.
    / Stripe charges an instalment and posts `invoice.paid`; the invoice announces
    `montant_paye` cents.

    :param ligne_de_facture: la ligne de la facture (`ligne_de_facture_simulee`) ; None =
        une ligne de 15 €, quantité 1
    :return: le `Paiement_stripe` de l'échéance, relu en base
    """
    identifiant_de_la_nouvelle_facture = f"in_test_{identifiant_unique()}"
    reponse_du_webhook = poster_la_facture_payee(
        lieu,
        adhesion_abonnee,
        identifiant_de_la_nouvelle_facture,
        montant_paye,
        ligne_de_facture,
    )

    assert reponse_du_webhook.status_code == 202
    return Paiement_stripe.objects.get(invoice_stripe=identifiant_de_la_nouvelle_facture)


def poster_la_facture_payee(
    lieu,
    adhesion_abonnee,
    identifiant_de_la_facture,
    montant_paye,
    ligne_de_facture=None,
):
    """
    Envoie au webhook du lieu l'événement `invoice.paid` de la facture
    `identifiant_de_la_facture` (une échéance de l'abonnement). Rejouer la même facture :
    rappeler avec le même identifiant, comme Stripe qui renvoie un événement.
    La facture est patchée ici, et non prise dans `mock_stripe` : la création du
    paiement de l'échéance lit aussi ses lignes et son abonnement.
    / Posts the `invoice.paid` event of that invoice to the venue webhook. Same id =
    Stripe replaying the event. Patched here: the instalment creation reads its lines.

    :param ligne_de_facture: la ligne de la facture (`ligne_de_facture_simulee`) ; None =
        une ligne de 15 €, quantité 1
    :return: la réponse du webhook
    """
    if ligne_de_facture is None:
        ligne_de_facture = ligne_de_facture_simulee(
            total_de_la_ligne=1500, quantite=1, prix_unitaire_decimal="1500"
        )

    facture_stripe_simulee = SimpleNamespace(
        id=identifiant_de_la_facture,
        status="paid",
        amount_paid=montant_paye,
        lines={"data": [ligne_de_facture]},
        parent=SimpleNamespace(
            subscription_details=SimpleNamespace(
                subscription=adhesion_abonnee.stripe_id_subscription
            )
        ),
    )
    evenement_facture_payee = {
        "id": identifiant_de_la_facture,
        "billing_reason": "subscription_cycle",
        "paid": True,
        "subscription": adhesion_abonnee.stripe_id_subscription,
        "subscription_details": {
            "metadata": {
                "tenant": str(lieu.tenant.uuid),
                "membership_uuid": str(adhesion_abonnee.uuid),
                "price_uuid": str(adhesion_abonnee.price.uuid),
            }
        },
        "metadata": {},
    }

    with patch("stripe.Invoice.retrieve", return_value=facture_stripe_simulee):
        reponse_du_webhook = envoyer_un_evenement_stripe(
            "invoice.paid", evenement_facture_payee
        )
    return reponse_du_webhook


def test_facture_payee_pose_le_montant_encaisse(lieu):
    """
    Une échéance d'abonnement à 15 € (1500 centimes au catalogue). La facture payée
    annonce 1450 centimes (`amount_paid`). Le webhook `invoice.paid` constate le paiement
    par la branche `INVOICE` : le paiement porte `montant_encaisse` = 1450.
    / Instalment at 1500 cents; the paid invoice announces 1450; the `INVOICE` branch
    stores `montant_encaisse` = 1450.
    """
    abonne = creer_utilisateur()
    adhesion_abonnee = creer_un_abonnement_en_cours(abonne)

    paiement_de_l_echeance = envoyer_la_facture_payee(
        lieu, adhesion_abonnee, montant_paye=1450
    )

    assert paiement_de_l_echeance.source == Paiement_stripe.INVOICE
    assert paiement_de_l_echeance.status in (
        Paiement_stripe.PAID,
        Paiement_stripe.VALID,
    )
    assert paiement_de_l_echeance.montant_encaisse == 1450


def test_facture_payee_par_le_solde_client_montant_zero_pose(lieu):
    """
    Une échéance d'abonnement à 15 €, payée par le solde du client chez Stripe : la
    facture est « paid » et annonce 0 centime (`amount_paid` = 0). Le paiement porte
    `montant_encaisse` = 0, et non « vide » (`None`) : 0 est un montant constaté.
    / Instalment paid by the customer balance: `amount_paid` = 0. The payment stores
    `montant_encaisse` = 0, not None: 0 is a recorded amount.
    """
    abonne = creer_utilisateur()
    adhesion_abonnee = creer_un_abonnement_en_cours(abonne)

    paiement_de_l_echeance = envoyer_la_facture_payee(
        lieu, adhesion_abonnee, montant_paye=0
    )

    assert paiement_de_l_echeance.montant_encaisse is not None, (
        "La branche INVOICE n'a pas posé le montant encaissé (montant_encaisse vide)."
    )
    assert paiement_de_l_echeance.montant_encaisse == 0


# --------------------------------------------------------------------------
# L'encaissement : la vente passe REGLEE au point unique
# / Settlement: the sale becomes REGLEE at the single point
# --------------------------------------------------------------------------

# Les noms des deux produits système d'écart d'encaissement (fiche D §2.2).
# / Names of the two system products for a collection gap.
NOM_ECART_RECU_EN_PLUS = "Écart d'encaissement — reçu en plus"
NOM_ECART_RECU_EN_MOINS = "Écart d'encaissement — reçu en moins"

# Le journal du point d'encaissement (l'appel protégé par `try`) et celui du service de
# vente (l'alerte d'écart, le paiement sans vente).
# / Logger of the settlement call site, and logger of the sale service.
JOURNAL_DU_POINT_D_ENCAISSEMENT = "BaseBillet.signals"
JOURNAL_DU_SERVICE_DE_VENTE = "BaseBillet.services_vente"
# Le journal du webhook Stripe (ApiBillet/views.py).
# / The Stripe webhook logger.
JOURNAL_DU_WEBHOOK_STRIPE = "ApiBillet.views"


def reserver_des_billets_a_payer(lieu):
    """
    Deux billets à 10 € et un billet réduit à 5 €, réservés sans panier : 2500 centimes
    au catalogue. La session Stripe simulée reçoit un identifiant unique : le webhook
    retrouve le paiement par cet identifiant, et la base de dev garde les paiements
    des autres tests.
    / Two 10 € tickets and one 5 € ticket without cart, 2500 cents. Unique session id:
    the webhook finds the payment by it.

    :return: un objet avec `client`, `acheteur`, `reservation` et `paiement`
    """
    lieu.stripe.session.id = f"cs_test_encaissement_{identifiant_unique()}"
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")
    tarif_reduit = concert.produit.prices.create(
        name="Tarif réduit", prix=Decimal("5.00"), publish=True
    )
    reserver_des_billets_sans_panier(
        client, acheteur, concert.evenement, {concert.tarif: 2, tarif_reduit: 1}
    )
    reservation = Reservation.objects.get(
        user_commande=acheteur, event=concert.evenement
    )
    paiement = reservation.paiements.get()
    assert paiement.checkout_session_id_stripe == lieu.stripe.session.id
    return SimpleNamespace(
        client=client,
        acheteur=acheteur,
        reservation=reservation,
        paiement=paiement,
    )


def vente_du_paiement(paiement):
    """
    Relit le paiement, puis sa vente d'origine, en base.
    / Reads the payment back, then its original sale.
    """
    paiement.refresh_from_db()
    assert paiement.vente_id is not None, (
        "Le paiement Stripe n'a pas de vente d'origine (Paiement_stripe.vente vide)."
    )
    return Vente.objects.get(pk=paiement.vente_id)


def verifier_la_vente_reglee_du_paiement(paiement, montant_du_reglement_attendu):
    """
    Relit le paiement et sa vente, puis vérifie la règle de l'encaissement Stripe :
    - la vente est REGLEE et numérotée ;
    - elle a UN règlement, du montant encaissé, au moyen du paiement, relié au
      paiement ; ou AUCUN règlement si le montant encaissé vaut 0 ;
    - le paiement porte bien le montant attendu (`montant_encaisse`).
    / Checks the Stripe settlement rule: REGLEE, numbered, ONE payment of the collected
    amount at the payment's method (or none when the amount is 0).

    :return: la vente, pour les vérifications propres à chaque test
    """
    vente = vente_du_paiement(paiement)
    assert vente.statut == Vente.Statut.REGLEE, (
        f"La vente du paiement n'est pas encaissée (statut {vente.statut})."
    )
    assert vente.numero is not None
    assert paiement.montant_encaisse == montant_du_reglement_attendu

    reglements_de_la_vente = list(vente.reglements.all())
    if montant_du_reglement_attendu == 0:
        assert reglements_de_la_vente == []
        return vente

    assert len(reglements_de_la_vente) == 1
    reglement_stripe = reglements_de_la_vente[0]
    assert reglement_stripe.montant == montant_du_reglement_attendu
    assert reglement_stripe.moyen == paiement.moyen
    assert reglement_stripe.paiement_stripe_id == paiement.pk
    return vente


def articles_d_ecart_de_la_vente(vente):
    """
    Les articles « Écart d'encaissement » de la vente, reconnus par le nom de leur
    produit (et non par leur paiement : la ligne d'écart n'en a pas).
    / The sale's collection-gap items, found by their product name.
    """
    articles_d_ecart = []
    for article in vente.articles.all():
        nom_du_produit = article.pricesold.productsold.product.name
        if nom_du_produit in (NOM_ECART_RECU_EN_PLUS, NOM_ECART_RECU_EN_MOINS):
            articles_d_ecart.append(article)
    return articles_d_ecart


def verifier_l_article_d_ecart(
    article, nom_attendu, quantite_attendue, ecart_en_centimes
):
    """
    Vérifie un article « Écart d'encaissement » (fiche D §2.2) :
    - produit système du nom attendu, dans une catégorie du même nom ;
    - prix unitaire = |écart|, quantité +1 (reçu en plus) ou −1 (reçu en moins) ;
    - TVA 0, rien d'offert, hors chiffre d'affaires ;
    - ligne VALID, SANS paiement Stripe.
    / Checks a collection-gap item: system product and category of the expected name,
    unit price |gap|, quantity ±1, VAT 0, off revenue, VALID line without Stripe payment.
    """
    produit = article.pricesold.productsold.product
    assert produit.name == nom_attendu
    assert produit.categorie_pos is not None
    assert produit.categorie_pos.name == nom_attendu

    assert article.amount == ecart_en_centimes
    assert article.qty == Decimal(quantite_attendue)
    assert article.total_catalogue == ecart_en_centimes * quantite_attendue
    assert article.part_offerte == 0
    assert article.vat == Decimal("0")
    assert article.total_tva == 0
    assert article.hors_chiffre_affaires is True

    assert article.status == LigneArticle.VALID
    assert article.paiement_stripe_id is None


def erreurs_du_journal(caplog, nom_du_journal):
    """
    Les enregistrements de niveau ERROR (ou plus) du journal nommé.
    / ERROR (or higher) records of the named logger.
    """
    erreurs = []
    for enregistrement in caplog.records:
        if (
            enregistrement.name == nom_du_journal
            and enregistrement.levelno >= logging.ERROR
        ):
            erreurs.append(enregistrement)
    return erreurs


def empreinte_de_la_vente_valide(vente):
    """
    Recalcule l'empreinte chaînée de la vente (avec son `previous_hmac`) et la compare
    à celle enregistrée : vrai si rien n'a bougé depuis l'encaissement.
    / Recomputes the sale's chained fingerprint and compares it with the stored one.
    """
    vente_relue = Vente.objects.get(pk=vente.pk)
    cle_de_l_empreinte = LaboutikConfiguration.get_solo().get_or_create_hmac_key()
    empreinte_recalculee = calculer_hmac_vente(
        vente_relue, cle_de_l_empreinte, vente_relue.previous_hmac
    )
    return empreinte_recalculee == vente_relue.hmac_hash


def test_paiement_confirme_encaisse_au_montant_stripe(lieu):
    """
    Fiche test 2. Trois billets (2500 centimes au catalogue), payés par carte. Stripe
    annonce le total du catalogue. Au retour de checkout payé :
    - la vente du paiement passe REGLEE, numérotée ;
    - UN règlement : 2500 centimes, au moyen du paiement (carte, SN), relié au paiement ;
    - aucun article d'écart : les articles sont exactement les lignes du paiement ;
    - les deux égalités de la vente tiennent.
    / Sheet test 2: card checkout paid; the sale is settled with ONE card payment of the
    collected amount, no gap item, both equalities hold.
    """
    achat = reserver_des_billets_a_payer(lieu)

    revenir_de_stripe_billetterie(achat.client, achat.paiement)

    vente = verifier_la_vente_reglee_du_paiement(
        achat.paiement, montant_du_reglement_attendu=2500
    )
    assert achat.paiement.moyen == PaymentMethod.STRIPE_NOFED

    articles_de_la_vente = set()
    for article in vente.articles.all():
        articles_de_la_vente.add(article.pk)
    lignes_du_paiement = set()
    for ligne in LigneArticle.objects.filter(paiement_stripe=achat.paiement):
        lignes_du_paiement.add(ligne.pk)
    assert articles_de_la_vente == lignes_du_paiement
    assert articles_d_ecart_de_la_vente(vente) == []

    verifier_egalites(vente)


def test_webhook_rejoue_deux_fois_une_seule_encaisse(lieu, caplog):
    """
    Fiche test 3. Trois billets (2500 au catalogue), Stripe annonce 2400 : la vente est
    encaissée au retour de checkout, avec un article d'écart (reçu en moins).
    Puis la transition `PAID → PAID` est rejouée par le webhook : le paiement est resté
    « payé » (posé par `update()`, sans signal, comme quand une ligne n'a pas de
    déclencheur), et Stripe renvoie `checkout.session.completed`.
    Le rejeu n'écrit RIEN : toujours un seul règlement, un seul article d'écart, même
    numéro, empreinte toujours valide, et aucune erreur journalisée par l'encaissement.
    / Sheet test 3: settled with a gap item, then PAID -> PAID replayed by the webhook:
    nothing written, same number, fingerprint still valid, no error logged.
    """
    achat = reserver_des_billets_a_payer(lieu)
    lieu.stripe.session.amount_total = 2400
    revenir_de_stripe_billetterie(achat.client, achat.paiement)

    vente = verifier_la_vente_reglee_du_paiement(
        achat.paiement, montant_du_reglement_attendu=2400
    )
    numero_apres_le_premier_encaissement = vente.numero
    empreinte_apres_le_premier_encaissement = vente.hmac_hash
    nombre_d_articles_apres_le_premier_encaissement = vente.articles.count()
    assert len(articles_d_ecart_de_la_vente(vente)) == 1

    # ÉTAT DE DÉPART DU REJEU : le paiement est resté « payé », sans traitement en
    # cours. Posé par `update()`, qui ne déclenche aucun signal (tests/PIEGES.md 12.17).
    # / REPLAY STARTING STATE: the payment stayed PAID. Set by update(): no signal.
    Paiement_stripe.objects.filter(pk=achat.paiement.pk).update(
        status=Paiement_stripe.PAID, traitement_en_cours=False
    )
    caplog.clear()

    reponse_du_webhook = envoyer_un_evenement_stripe(
        "checkout.session.completed",
        objet_session_de_paiement(lieu, achat.paiement.checkout_session_id_stripe),
    )
    assert reponse_du_webhook.status_code == 200

    vente_apres_le_rejeu = verifier_la_vente_reglee_du_paiement(
        achat.paiement, montant_du_reglement_attendu=2400
    )
    assert vente_apres_le_rejeu.pk == vente.pk
    assert vente_apres_le_rejeu.numero == numero_apres_le_premier_encaissement
    assert vente_apres_le_rejeu.hmac_hash == empreinte_apres_le_premier_encaissement
    assert (
        vente_apres_le_rejeu.articles.count()
        == nombre_d_articles_apres_le_premier_encaissement
    )
    assert len(articles_d_ecart_de_la_vente(vente_apres_le_rejeu)) == 1
    assert empreinte_de_la_vente_valide(vente_apres_le_rejeu)
    assert erreurs_du_journal(caplog, JOURNAL_DU_POINT_D_ENCAISSEMENT) == []
    assert erreurs_du_journal(caplog, JOURNAL_DU_SERVICE_DE_VENTE) == []

    verifier_egalites(vente_apres_le_rejeu)


def test_retour_checkout_puis_webhook_une_seule_encaisse(lieu):
    """
    Fiche test 4. Trois billets (2500 au catalogue) : le client revient de Stripe, puis
    Stripe envoie `checkout.session.completed` pour la même session. Une seule vente
    encaissée : un seul règlement de 2500, même numéro après le webhook.
    / Sheet test 4: browser return then webhook: one settled sale, one payment, same
    number after the webhook.
    """
    achat = reserver_des_billets_a_payer(lieu)

    revenir_de_stripe_billetterie(achat.client, achat.paiement)
    vente = verifier_la_vente_reglee_du_paiement(
        achat.paiement, montant_du_reglement_attendu=2500
    )
    numero_apres_le_retour = vente.numero

    reponse_du_webhook = envoyer_un_evenement_stripe(
        "checkout.session.completed",
        objet_session_de_paiement(lieu, achat.paiement.checkout_session_id_stripe),
    )
    assert reponse_du_webhook.status_code == 200

    vente_apres_le_webhook = verifier_la_vente_reglee_du_paiement(
        achat.paiement, montant_du_reglement_attendu=2500
    )
    assert vente_apres_le_webhook.numero == numero_apres_le_retour
    assert Reglement.objects.filter(paiement_stripe=achat.paiement).count() == 1

    verifier_egalites(vente_apres_le_webhook)


def test_facture_payee_par_le_solde_client_montant_zero(lieu):
    """
    Fiche test 4b. Une échéance d'abonnement à 15 € (1500 au catalogue), payée par le
    solde du client chez Stripe : la facture annonce 0 centime. La vente est encaissée
    SANS règlement (un règlement de 0 n'existe pas), avec un article d'écart « reçu en
    moins » de −1500 : Σ règlements (0) = Σ catalogue (1500 − 1500).
    / Sheet test 4b: invoice paid by the customer balance (0): settled with NO payment
    and a −1500 "received less" gap item.
    """
    abonne = creer_utilisateur()
    adhesion_abonnee = creer_un_abonnement_en_cours(abonne)

    paiement_de_l_echeance = envoyer_la_facture_payee(
        lieu, adhesion_abonnee, montant_paye=0
    )

    vente = verifier_la_vente_reglee_du_paiement(
        paiement_de_l_echeance, montant_du_reglement_attendu=0
    )
    articles_d_ecart = articles_d_ecart_de_la_vente(vente)
    assert len(articles_d_ecart) == 1
    verifier_l_article_d_ecart(
        articles_d_ecart[0],
        nom_attendu=NOM_ECART_RECU_EN_MOINS,
        quantite_attendue=-1,
        ecart_en_centimes=1500,
    )

    verifier_egalites(vente)


def test_ligne_d_ecart_valid_sans_paiement_stripe(lieu):
    """
    Fiche test 4c. Trois billets (2500 au catalogue), Stripe annonce 2400. Le paiement
    passe VALID quand ses lignes le sont ; la ligne d'écart est créée directement VALID
    et n'a PAS de paiement Stripe : elle n'est pas une ligne du paiement.
    / Sheet test 4c: the payment goes VALID with its lines; the gap line is created
    VALID and has NO Stripe payment.
    """
    achat = reserver_des_billets_a_payer(lieu)
    lieu.stripe.session.amount_total = 2400

    revenir_de_stripe_billetterie(achat.client, achat.paiement)

    vente = verifier_la_vente_reglee_du_paiement(
        achat.paiement, montant_du_reglement_attendu=2400
    )
    assert achat.paiement.status == Paiement_stripe.VALID
    for ligne in LigneArticle.objects.filter(paiement_stripe=achat.paiement):
        assert ligne.status == LigneArticle.VALID

    articles_d_ecart = articles_d_ecart_de_la_vente(vente)
    assert len(articles_d_ecart) == 1
    ligne_d_ecart = articles_d_ecart[0]
    assert ligne_d_ecart.status == LigneArticle.VALID
    assert ligne_d_ecart.paiement_stripe_id is None
    assert not LigneArticle.objects.filter(
        paiement_stripe=achat.paiement, pk=ligne_d_ecart.pk
    ).exists()

    verifier_egalites(vente)


def test_stripe_canceled_vente_annulee_sans_numero(lieu):
    """
    Fiche test 6. Stripe répond « aucun paiement requis » (`no_payment_required`) :
    le paiement passe `PENDING → CANCELED`. La vente passe ANNULEE, sans numéro, sans
    règlement.
    / Sheet test 6: PENDING -> CANCELED cancels the sale: ANNULEE, no number, no payment.
    """
    achat = reserver_des_billets_a_payer(lieu)
    lieu.stripe.session.payment_status = "no_payment_required"

    revenir_de_stripe_billetterie(achat.client, achat.paiement)

    vente = vente_du_paiement(achat.paiement)
    assert achat.paiement.status == Paiement_stripe.CANCELED
    assert vente.statut == Vente.Statut.ANNULEE
    assert vente.numero is None
    assert vente.reglements.count() == 0


def test_session_expiree_reste_en_attente_puis_encaissee(lieu):
    """
    Fiche test 7. Trois billets (2500 au catalogue). Le client revient sans avoir payé,
    après l'expiration de la session : `PENDING → EXPIRE`. La vente ne change pas :
    EN_ATTENTE, sans numéro, sans règlement.
    Puis Stripe constate un paiement tardif : `EXPIRE → PAID`. La vente est encaissée
    telle quelle : REGLEE, numérotée, un règlement de 2500.
    / Sheet test 7: an expired session leaves the sale PENDING without number; a late
    payment (EXPIRE -> PAID) settles it.
    """
    achat = reserver_des_billets_a_payer(lieu)
    lieu.stripe.session.payment_status = "unpaid"
    lieu.stripe.session.status = "open"
    lieu.stripe.session.expires_at = time.time() - 60

    revenir_de_stripe_billetterie(achat.client, achat.paiement)

    vente = vente_du_paiement(achat.paiement)
    assert achat.paiement.status == Paiement_stripe.EXPIRE
    assert vente.statut == Vente.Statut.EN_ATTENTE
    assert vente.numero is None
    assert vente.reglements.count() == 0

    # Paiement tardif : Stripe annonce maintenant la session payée.
    # / Late payment: Stripe now reports the session paid.
    lieu.stripe.session.payment_status = "paid"
    lieu.stripe.session.status = "complete"
    revenir_de_stripe_billetterie(achat.client, achat.paiement)

    vente_encaissee = verifier_la_vente_reglee_du_paiement(
        achat.paiement, montant_du_reglement_attendu=2500
    )
    assert vente_encaissee.pk == vente.pk

    verifier_egalites(vente_encaissee)


def test_montant_stripe_superieur_ecart_d_encaissement_758(lieu, caplog):
    """
    Fiche test 8. Trois billets (2500 au catalogue), Stripe annonce 2600 (100 centimes
    reçus en plus). La vente est encaissée avec un règlement de 2600 et un article
    « Écart d'encaissement — reçu en plus » : +100, quantité +1, TVA 0, hors chiffre
    d'affaires. Une alerte est journalisée (ERROR) par le service de vente.
    / Sheet test 8: Stripe announces 100 cents more: 2600 payment, "received more" gap
    item +100, off revenue; an ERROR alert is logged.
    """
    achat = reserver_des_billets_a_payer(lieu)
    lieu.stripe.session.amount_total = 2600

    revenir_de_stripe_billetterie(achat.client, achat.paiement)

    vente = verifier_la_vente_reglee_du_paiement(
        achat.paiement, montant_du_reglement_attendu=2600
    )
    articles_d_ecart = articles_d_ecart_de_la_vente(vente)
    assert len(articles_d_ecart) == 1
    verifier_l_article_d_ecart(
        articles_d_ecart[0],
        nom_attendu=NOM_ECART_RECU_EN_PLUS,
        quantite_attendue=1,
        ecart_en_centimes=100,
    )
    assert len(erreurs_du_journal(caplog, JOURNAL_DU_SERVICE_DE_VENTE)) >= 1

    verifier_egalites(vente)


def test_montant_stripe_inferieur_ecart_negatif_658(lieu, caplog):
    """
    Fiche test 9. Trois billets (2500 au catalogue), Stripe annonce 2400 (100 centimes
    reçus en moins). La vente est encaissée avec un règlement de 2400 et un article
    « Écart d'encaissement — reçu en moins » : prix 100, quantité −1, soit −100 au
    catalogue. Une alerte est journalisée (ERROR) par le service de vente.
    / Sheet test 9: Stripe announces 100 cents less: 2400 payment, "received less" gap
    item 100 × −1; an ERROR alert is logged.
    """
    achat = reserver_des_billets_a_payer(lieu)
    lieu.stripe.session.amount_total = 2400

    revenir_de_stripe_billetterie(achat.client, achat.paiement)

    vente = verifier_la_vente_reglee_du_paiement(
        achat.paiement, montant_du_reglement_attendu=2400
    )
    articles_d_ecart = articles_d_ecart_de_la_vente(vente)
    assert len(articles_d_ecart) == 1
    verifier_l_article_d_ecart(
        articles_d_ecart[0],
        nom_attendu=NOM_ECART_RECU_EN_MOINS,
        quantite_attendue=-1,
        ecart_en_centimes=100,
    )
    assert len(erreurs_du_journal(caplog, JOURNAL_DU_SERVICE_DE_VENTE)) >= 1

    verifier_egalites(vente)


def test_abonnement_quantite_2_encaisse_par_la_branche_invoice(lieu):
    """
    Fiche test 10, partie encaissement. Stripe prélève une échéance d'un abonnement de
    quantité 2 au prix unitaire de 15 € : la facture vaut 3000 et annonce 3000 payés.
    Le webhook `invoice.paid` constate le paiement par la branche `INVOICE` : la vente
    de l'échéance est encaissée avec UN règlement de 3000 au moyen « abonnement » (SR),
    sans article d'écart.
    / Sheet test 10, settlement part: a quantity-2 instalment (3000) settled by the
    INVOICE branch: one 3000 subscription payment (SR), no gap item.
    """
    abonne = creer_utilisateur()
    adhesion_abonnee = creer_un_abonnement_en_cours(abonne)

    paiement_de_l_echeance = envoyer_la_facture_payee(
        lieu,
        adhesion_abonnee,
        montant_paye=3000,
        ligne_de_facture=ligne_de_facture_simulee(
            total_de_la_ligne=3000, quantite=2, prix_unitaire_decimal="1500"
        ),
    )

    vente = verifier_la_vente_reglee_du_paiement(
        paiement_de_l_echeance, montant_du_reglement_attendu=3000
    )
    assert paiement_de_l_echeance.moyen == PaymentMethod.STRIPE_RECURENT
    assert articles_d_ecart_de_la_vente(vente) == []
    article_de_l_echeance = vente.articles.get()
    assert article_de_l_echeance.amount == 1500
    assert article_de_l_echeance.qty == Decimal("2")

    verifier_egalites(vente)


@contextmanager
def requetes_sql_relevees():
    """
    Relève le texte SQL de chaque requête faite dans le bloc, dans l'ordre (paramètres
    à part, sous la forme `%s`). Passe aussi par les requêtes faites pendant une requête
    HTTP du client de test.
    / Records the SQL text of every query run in the block, in order (parameters left
    out as `%s`), including those run during a test client HTTP request.

    `CaptureQueriesContext` ne convient pas ici : chaque requête HTTP vide le journal
    des requêtes de la connexion (signal `request_started` → `reset_queries`).
    / CaptureQueriesContext does not fit: each HTTP request empties the query log.

    :return: la liste des textes SQL, remplie au fil du bloc
    """
    textes_sql = []

    def relever_la_requete(executer, texte_sql, parametres, plusieurs, contexte):
        textes_sql.append(texte_sql)
        return executer(texte_sql, parametres, plusieurs, contexte)

    with connection.execute_wrapper(relever_la_requete):
        yield textes_sql


def position_de_la_premiere_requete(textes_sql, morceaux_attendus):
    """
    La place de la première requête SQL qui contient TOUS les morceaux attendus, ou None.
    / The position of the first SQL query holding ALL the expected pieces, or None.
    """
    for position, texte_sql in enumerate(textes_sql):
        tous_les_morceaux_presents = True
        for morceau in morceaux_attendus:
            if morceau not in texte_sql:
                tous_les_morceaux_presents = False
        if tous_les_morceaux_presents:
            return position
    return None


def test_renouvellement_d_abonnement_rejoue_une_seule_vente(lieu):
    """
    Stripe envoie DEUX fois `invoice.paid` pour la même échéance d'un abonnement (rejeu,
    ou deux envois simultanés).
    - Le premier envoi relit l'adhésion sous verrou (`SELECT … FOR UPDATE`) AVANT de
      comparer la facture à `last_stripe_invoice` et de créer le paiement de
      l'échéance : deux envois simultanés passent l'un après l'autre, le second voit la
      facture déjà comptée. Une seule connexion ne peut pas faire attendre le second
      envoi : on vérifie la place du verrou parmi les requêtes SQL.
    - Au total : UN paiement pour cette facture, UNE vente, UNE ligne de plus pour
      l'adhésion.
    / Stripe posts `invoice.paid` twice for the same instalment. The membership is read
    under lock BEFORE the invoice check and the payment creation (checked on the SQL
    queries). One payment, one sale, one more line.
    """
    abonne = creer_utilisateur()
    adhesion_abonnee = creer_un_abonnement_en_cours(abonne)
    nombre_de_lignes_de_l_adhesion_avant = LigneArticle.objects.filter(
        membership=adhesion_abonnee
    ).count()
    identifiant_de_la_facture = f"in_test_{identifiant_unique()}"

    with requetes_sql_relevees() as requetes_du_premier_envoi:
        reponse_du_premier_envoi = poster_la_facture_payee(
            lieu, adhesion_abonnee, identifiant_de_la_facture, montant_paye=1500
        )
    reponse_du_second_envoi = poster_la_facture_payee(
        lieu, adhesion_abonnee, identifiant_de_la_facture, montant_paye=1500
    )

    assert reponse_du_premier_envoi.status_code == 202
    assert reponse_du_second_envoi.status_code != 202

    paiements_de_la_facture = Paiement_stripe.objects.filter(
        invoice_stripe=identifiant_de_la_facture
    )
    assert paiements_de_la_facture.count() == 1
    assert (
        Vente.objects.filter(
            paiements_stripe__invoice_stripe=identifiant_de_la_facture
        ).count()
        == 1
    )
    assert (
        LigneArticle.objects.filter(membership=adhesion_abonnee).count()
        == nombre_de_lignes_de_l_adhesion_avant + 1
    )

    position_du_verrou_sur_l_adhesion = position_de_la_premiere_requete(
        requetes_du_premier_envoi, ['FROM "BaseBillet_membership"', "FOR UPDATE"]
    )
    position_de_la_creation_du_paiement = position_de_la_premiere_requete(
        requetes_du_premier_envoi, ['INSERT INTO "BaseBillet_paiement_stripe"']
    )
    assert position_de_la_creation_du_paiement is not None
    assert position_du_verrou_sur_l_adhesion is not None, (
        "L'adhésion n'est pas lue sous verrou (SELECT … FOR UPDATE) par la branche "
        "invoice.paid."
    )
    assert position_du_verrou_sur_l_adhesion < position_de_la_creation_du_paiement, (
        "L'adhésion est verrouillée APRÈS la création du paiement de l'échéance."
    )


# --------------------------------------------------------------------------
# T4 : une erreur d'encaissement ne sort jamais du pre_save
# / T4: a settlement error never leaves the pre_save
# --------------------------------------------------------------------------


def payer_avec_un_encaissement_qui_echoue(achat):
    """
    Le client revient de Stripe, payé ; l'encaissement de la vente échoue (égalité
    rompue simulée dans `encaisser_vente`, la dernière étape).
    / The buyer comes back paid; the sale settlement fails (simulated broken equality).

    :return: la réponse du retour de Stripe
    """
    erreur_simulee = EgaliteDeVenteRompue("Égalité rompue simulée par le test.")
    with patch(
        "BaseBillet.services_vente.encaisser_vente", side_effect=erreur_simulee
    ):
        reponse_du_retour = revenir_de_stripe_billetterie(achat.client, achat.paiement)
    return reponse_du_retour


def test_erreur_d_encaissement_ne_bloque_pas_le_paiement(lieu, caplog):
    """
    T4. L'encaissement échoue pendant le `pre_save` du paiement. Aucune exception ne
    sort : le retour de Stripe répond normalement, le paiement est validé, ses lignes
    aussi, la réservation est payée (les billets partent). La vente reste EN_ATTENTE,
    sans numéro et sans règlement (rien d'écrit à moitié). L'erreur est journalisée
    (ERROR) au point d'encaissement.
    / T4: the settlement fails inside the payment pre_save. No exception leaves it: the
    payment, lines and reservation go through; the sale stays PENDING, nothing half
    written; the error is logged.
    """
    achat = reserver_des_billets_a_payer(lieu)

    reponse_du_retour = payer_avec_un_encaissement_qui_echoue(achat)

    assert reponse_du_retour.status_code == 302
    achat.paiement.refresh_from_db()
    assert achat.paiement.status == Paiement_stripe.VALID
    for ligne in LigneArticle.objects.filter(paiement_stripe=achat.paiement):
        assert ligne.status == LigneArticle.VALID
    achat.reservation.refresh_from_db()
    assert achat.reservation.status == Reservation.PAID

    vente = vente_du_paiement(achat.paiement)
    assert vente.statut == Vente.Statut.EN_ATTENTE
    assert vente.numero is None
    assert vente.reglements.count() == 0
    assert len(erreurs_du_journal(caplog, JOURNAL_DU_POINT_D_ENCAISSEMENT)) >= 1


def test_paiement_canceled_annulation_en_echec_ne_bloque_pas_le_paiement(lieu, caplog):
    """
    T4, côté « non » de Stripe. Le paiement passe `PENDING → CANCELED` ; l'annulation de
    sa vente échoue pendant le `pre_save` du paiement (simulé : `annuler_vente` lève,
    comme pour une vente devenue REGLEE entre-temps). Aucune exception ne sort : le
    `save()` du paiement ne lève pas, le paiement est CANCELED en base. La vente reste
    telle quelle : EN_ATTENTE, sans numéro, sans règlement. L'erreur est journalisée
    (ERROR) dans `BaseBillet.signals`.
    / T4, Stripe's "no" side: PENDING -> CANCELED; the sale cancellation fails inside the
    payment pre_save. No exception leaves: the payment save does not raise, the payment
    is CANCELED; the sale stays PENDING, unnumbered, without payment; the error is logged.
    """
    achat = reserver_des_billets_a_payer(lieu)
    assert achat.paiement.status == Paiement_stripe.PENDING
    caplog.clear()

    erreur_simulee = ValueError("Annulation de la vente refusée, simulée par le test.")
    with caplog.at_level(logging.ERROR, logger=JOURNAL_DU_POINT_D_ENCAISSEMENT):
        with patch("BaseBillet.signals.annuler_vente", side_effect=erreur_simulee):
            achat.paiement.status = Paiement_stripe.CANCELED
            achat.paiement.save()

    achat.paiement.refresh_from_db()
    assert achat.paiement.status == Paiement_stripe.CANCELED

    vente = vente_du_paiement(achat.paiement)
    assert vente.statut == Vente.Statut.EN_ATTENTE
    assert vente.numero is None
    assert vente.reglements.count() == 0
    assert len(erreurs_du_journal(caplog, JOURNAL_DU_POINT_D_ENCAISSEMENT)) >= 1


def test_rejeu_de_l_encaissement_par_la_fonction(lieu):
    """
    T4, le rejeu. Trois billets (2500 au catalogue), Stripe annonce 2400 ; l'encaissement
    échoue au retour de Stripe : la vente reste EN_ATTENTE. On rejoue l'encaissement en
    appelant `encaisser_vente_stripe(paiement)` (le paiement est déjà VALID : un
    `save()` ne rejouerait rien). La vente est encaissée : REGLEE, un règlement de 2400,
    un article d'écart. Un second appel ne réécrit rien : même vente, même numéro,
    toujours un règlement et un article d'écart.
    / T4 replay: the failed settlement is replayed by calling `encaisser_vente_stripe`;
    a second call writes nothing.
    """
    achat = reserver_des_billets_a_payer(lieu)
    lieu.stripe.session.amount_total = 2400
    payer_avec_un_encaissement_qui_echoue(achat)
    assert vente_du_paiement(achat.paiement).statut == Vente.Statut.EN_ATTENTE

    paiement_relu = Paiement_stripe.objects.get(pk=achat.paiement.pk)
    assert paiement_relu.status == Paiement_stripe.VALID
    services_vente.encaisser_vente_stripe(paiement_relu)

    vente = verifier_la_vente_reglee_du_paiement(
        achat.paiement, montant_du_reglement_attendu=2400
    )
    assert len(articles_d_ecart_de_la_vente(vente)) == 1
    numero_apres_le_rejeu = vente.numero

    vente_rendue_par_le_second_appel = services_vente.encaisser_vente_stripe(
        Paiement_stripe.objects.get(pk=achat.paiement.pk)
    )

    assert vente_rendue_par_le_second_appel.pk == vente.pk
    vente_apres_le_second_appel = verifier_la_vente_reglee_du_paiement(
        achat.paiement, montant_du_reglement_attendu=2400
    )
    assert vente_apres_le_second_appel.numero == numero_apres_le_rejeu
    assert len(articles_d_ecart_de_la_vente(vente_apres_le_second_appel)) == 1

    verifier_egalites(vente_apres_le_second_appel)


# --------------------------------------------------------------------------
# T5 : prélèvement SEPA refusé ; T6 : panier abandonné
# / T5: refused SEPA debit; T6: abandoned cart
# --------------------------------------------------------------------------


def test_sepa_refuse_vente_annulee(lieu):
    """
    T5. Une adhésion validée par l'admin (20 €) est payée par prélèvement SEPA : Stripe
    envoie `checkout.session.completed` (pas encore payé), puis
    `checkout.session.async_payment_failed` (prélèvement refusé). Le paiement passe
    « échoué » ; sa vente passe ANNULEE, sans numéro, sans règlement.
    / T5: SEPA debit submitted then refused: the payment fails, its sale is cancelled,
    no number, no payment.
    """
    adhesion_validee = preparer_une_adhesion_validee_par_l_admin()
    prelevement = soumettre_un_prelevement_sepa(lieu, adhesion_validee)
    assert vente_du_paiement(prelevement.paiement).statut == Vente.Statut.EN_ATTENTE

    reponse_du_webhook = envoyer_un_evenement_stripe(
        "checkout.session.async_payment_failed",
        objet_session_de_paiement(lieu, prelevement.identifiant_de_session),
    )
    assert reponse_du_webhook.status_code == 200

    vente = vente_du_paiement(prelevement.paiement)
    assert prelevement.paiement.status == Paiement_stripe.FAILED
    assert vente.statut == Vente.Statut.ANNULEE
    assert vente.numero is None
    assert vente.reglements.count() == 0


def test_sepa_refuse_annulation_en_echec_ne_bloque_pas(lieu, caplog):
    """
    T5, avec une annulation qui échoue. Une adhésion validée par l'admin (20 €) est
    payée par prélèvement SEPA, puis Stripe annonce le refus
    (`checkout.session.async_payment_failed`). L'annulation de la vente échoue (simulé :
    `annuler_vente` lève, comme pour une vente devenue REGLEE entre-temps).
    Comme pour `CANCELED` (BaseBillet/signals.py), l'erreur ne sort pas du webhook :
    - le webhook répond 200 ; le paiement est « échoué » ;
    - l'adhésion est réarmée (« validée par l'admin ») et le mail « paiement refusé »
      est demandé ;
    - la vente reste telle quelle (EN_ATTENTE, sans numéro, sans règlement) ;
    - l'erreur est journalisée (ERROR) dans `ApiBillet.views`.
    / T5 with a failing cancellation: the error never leaves the webhook (200), the
    payment fails, the membership is rearmed, the refused mail is asked, the sale stays
    as is, the error is logged.
    """
    adhesion_validee = preparer_une_adhesion_validee_par_l_admin()
    prelevement = soumettre_un_prelevement_sepa(lieu, adhesion_validee)
    assert vente_du_paiement(prelevement.paiement).statut == Vente.Statut.EN_ATTENTE
    lieu.taches_demandees.clear()
    caplog.clear()

    erreur_simulee = ValueError("Annulation de la vente refusée, simulée par le test.")
    with caplog.at_level(logging.ERROR, logger=JOURNAL_DU_WEBHOOK_STRIPE):
        with patch(
            "BaseBillet.services_vente.annuler_vente", side_effect=erreur_simulee
        ):
            reponse_du_webhook = envoyer_un_evenement_stripe(
                "checkout.session.async_payment_failed",
                objet_session_de_paiement(lieu, prelevement.identifiant_de_session),
            )

    assert reponse_du_webhook.status_code == 200
    prelevement.paiement.refresh_from_db()
    assert prelevement.paiement.status == Paiement_stripe.FAILED
    adhesion_validee.refresh_from_db()
    assert adhesion_validee.status == Membership.ADMIN_VALID
    assert "send_payment_refused_user" in noms_des_taches(lieu.taches_demandees)

    vente = vente_du_paiement(prelevement.paiement)
    assert vente.statut == Vente.Statut.EN_ATTENTE
    assert vente.numero is None
    assert vente.reglements.count() == 0
    assert len(erreurs_du_journal(caplog, JOURNAL_DU_WEBHOOK_STRIPE)) >= 1


def test_panier_abandonne_reste_en_attente_sans_numero(lieu):
    """
    T6. Un panier (deux billets à 10 €) est matérialisé, puis abandonné : le client
    revient sans payer, après l'expiration de la session (`PENDING → EXPIRE`). La vente
    du panier ne change pas : EN_ATTENTE, sans numéro, sans règlement. Aucun effet
    comptable.
    / T6: an abandoned cart (expired session) leaves its sale PENDING, without number
    or payment.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)
    commande = payer_le_panier(panier, acheteur)
    paiement = commande.paiement_stripe

    lieu.stripe.session.payment_status = "unpaid"
    lieu.stripe.session.status = "open"
    lieu.stripe.session.expires_at = time.time() - 60
    revenir_de_stripe_billetterie(client_connecte(acheteur), paiement)

    vente = vente_du_paiement(paiement)
    assert paiement.status == Paiement_stripe.EXPIRE
    assert vente.pk == commande.vente_id
    assert vente.statut == Vente.Statut.EN_ATTENTE
    assert vente.numero is None
    assert vente.reglements.count() == 0


# --------------------------------------------------------------------------
# Cas limites : paiement sans vente, montant encaissé vide, montant lu sur l'objet
# / Edge cases: payment without sale, empty collected amount, amount read on the object
# --------------------------------------------------------------------------


def test_paiement_sans_vente_rien_n_est_encaisse(lieu, caplog):
    """
    Un paiement antérieur au chantier n'a pas de vente (ses lignes non plus). Payé, il
    passe VALID comme avant, sans erreur : l'encaissement ne fait rien et le note au
    journal (INFO, service de vente). Aucun règlement n'est écrit pour ce paiement.
    L'état de départ est posé par `update()` : la vente ouverte par le checkout est
    détachée du paiement et de ses lignes (elle reste EN_ATTENTE, sans article).
    / A pre-project payment has no sale: paid, it goes VALID as before, without error;
    settlement does nothing and logs it (INFO). No payment row is written.
    """
    achat = reserver_des_billets_a_payer(lieu)
    vente_detachee = vente_du_paiement(achat.paiement)
    Paiement_stripe.objects.filter(pk=achat.paiement.pk).update(vente=None)
    LigneArticle.objects.filter(paiement_stripe=achat.paiement).update(vente=None)
    lieu.stripe.session.amount_total = 2500

    with caplog.at_level(logging.INFO, logger=JOURNAL_DU_SERVICE_DE_VENTE):
        reponse_du_retour = revenir_de_stripe_billetterie(achat.client, achat.paiement)

    assert reponse_du_retour.status_code == 302
    achat.paiement.refresh_from_db()
    assert achat.paiement.status == Paiement_stripe.VALID
    assert achat.paiement.vente_id is None
    assert not Reglement.objects.filter(paiement_stripe=achat.paiement).exists()
    vente_detachee.refresh_from_db()
    assert vente_detachee.statut == Vente.Statut.EN_ATTENTE

    assert erreurs_du_journal(caplog, JOURNAL_DU_POINT_D_ENCAISSEMENT) == []
    assert erreurs_du_journal(caplog, JOURNAL_DU_SERVICE_DE_VENTE) == []
    infos_du_service_de_vente = []
    for enregistrement in caplog.records:
        if (
            enregistrement.name == JOURNAL_DU_SERVICE_DE_VENTE
            and enregistrement.levelno == logging.INFO
        ):
            infos_du_service_de_vente.append(enregistrement)
    assert len(infos_du_service_de_vente) >= 1


def test_montant_encaisse_vide_erreur_journalisee_vente_en_attente(lieu, caplog):
    """
    Stripe n'annonce aucun montant (`amount_total` vide) : le paiement est payé avec un
    `montant_encaisse` vide. L'encaissement refuse d'inventer un montant : erreur
    explicite (ValueError, comme les autres refus du service), journalisée au point
    d'encaissement. Le paiement passe quand même VALID ; la vente reste EN_ATTENTE,
    sans numéro ni règlement. Rappelée à la main, la fonction lève la même erreur.
    / No amount announced: the settlement refuses (ValueError), logged at the call site;
    the payment goes VALID, the sale stays PENDING. Called again, it raises.
    """
    achat = reserver_des_billets_a_payer(lieu)
    lieu.stripe.session.amount_total = None

    revenir_de_stripe_billetterie(achat.client, achat.paiement)

    achat.paiement.refresh_from_db()
    assert achat.paiement.status == Paiement_stripe.VALID
    assert achat.paiement.montant_encaisse is None
    vente = vente_du_paiement(achat.paiement)
    assert vente.statut == Vente.Statut.EN_ATTENTE
    assert vente.numero is None
    assert vente.reglements.count() == 0
    assert len(erreurs_du_journal(caplog, JOURNAL_DU_POINT_D_ENCAISSEMENT)) >= 1

    with pytest.raises(ValueError):
        services_vente.encaisser_vente_stripe(achat.paiement)
    vente.refresh_from_db()
    assert vente.statut == Vente.Statut.EN_ATTENTE


def test_montant_pose_avant_le_save(lieu):
    """
    Le montant encaissé est posé sur le paiement AVANT le `save()` qui le passe
    « payé » : l'encaissement, qui tourne pendant ce `save()` (pre_save), le lit sur
    l'objet reçu. Il n'est pas encore en base à ce moment-là.
    On le prouve avec une contribution crowds : sa ligne n'a pas de déclencheur, donc
    le paiement reste « payé » (`P`) et n'est pas réenregistré pendant le `pre_save`.
    Stripe annonce 1500 : la vente est encaissée avec un règlement de 1500, pendant
    que le paiement est encore « payé ».
    / The collected amount is set BEFORE the save() that marks the payment paid: the
    settlement reads it on the received object (not yet in the database). Proven with
    a crowds contribution, whose payment is not re-saved during the pre_save.
    """
    contributeur = creer_utilisateur()
    client = client_connecte(contributeur)
    initiative = Initiative.objects.create(
        name=f"{PREFIXE_DE_TEST} initiative {identifiant_unique()}",
        direct_debit=True,
    )
    reponse = client.post(
        f"/crowd/{initiative.pk}/contribute/",
        data=json.dumps(
            {"amount": 1500, "contributor_name": "Ada", "description": "Merci"}
        ),
        content_type="application/json",
    )
    assert reponse.status_code == 200
    contribution = Contribution.objects.get(initiative=initiative)
    paiement = contribution.paiement_stripe
    lieu.stripe.session.amount_total = 1500

    paiement.update_checkout_status()

    vente = verifier_la_vente_reglee_du_paiement(
        paiement, montant_du_reglement_attendu=1500
    )
    assert paiement.status == Paiement_stripe.PAID
    assert articles_d_ecart_de_la_vente(vente) == []

    verifier_egalites(vente)


def test_vente_annulee_puis_payee_erreur_journalisee(lieu, caplog):
    """
    La vente d'un paiement a été annulée (Stripe avait dit non), puis Stripe constate
    le paiement : l'encaissement refuse d'encaisser une vente annulée. L'erreur
    explicite est attrapée au point d'encaissement et journalisée (ERROR) : le client
    est payé, la vente reste ANNULEE, sans numéro, et rien n'est écrit (ni règlement,
    ni article d'écart). Cas à regarder à la main.
    L'état de départ est posé par `annuler_vente`, le service qu'appellent `CANCELED`
    et le SEPA refusé.
    / A cancelled sale whose payment is then confirmed: the settlement refuses, the
    error is caught and logged; the sale stays ANNULEE and nothing is written.
    """
    achat = reserver_des_billets_a_payer(lieu)
    lieu.stripe.session.amount_total = 2400
    vente = vente_du_paiement(achat.paiement)
    nombre_d_articles_avant = vente.articles.count()
    services_vente.annuler_vente(vente)

    reponse_du_retour = revenir_de_stripe_billetterie(achat.client, achat.paiement)

    assert reponse_du_retour.status_code == 302
    achat.paiement.refresh_from_db()
    assert achat.paiement.status == Paiement_stripe.VALID
    vente.refresh_from_db()
    assert vente.statut == Vente.Statut.ANNULEE
    assert vente.numero is None
    assert vente.reglements.count() == 0
    assert vente.articles.count() == nombre_d_articles_avant
    assert articles_d_ecart_de_la_vente(vente) == []
    assert len(erreurs_du_journal(caplog, JOURNAL_DU_POINT_D_ENCAISSEMENT)) >= 1


def test_moyen_vide_erreur_journalisee_vente_en_attente(lieu, caplog):
    """
    Un chemin passe le paiement « payé » avec son montant encaissé, mais sans son
    moyen (`Paiement_stripe.moyen` vide). L'encaissement refuse d'inventer un moyen :
    erreur explicite (ValueError), attrapée au point d'encaissement et journalisée.
    Le paiement passe quand même VALID ; la vente reste EN_ATTENTE, sans numéro ni
    règlement. Rappelée à la main, la fonction lève la même erreur.
    Le passage à « payé » est fait par un `save()` du test : c'est la transition
    `PENDING → PAID` du `pre_save`, comme dans les vrais chemins.
    / A path marks the payment paid with its amount but no method: the settlement
    refuses (ValueError), logged at the call site; the sale stays PENDING.
    """
    achat = reserver_des_billets_a_payer(lieu)
    paiement = Paiement_stripe.objects.get(pk=achat.paiement.pk)
    assert paiement.moyen is None

    paiement.status = Paiement_stripe.PAID
    paiement.montant_encaisse = 2500
    paiement.save()

    paiement.refresh_from_db()
    assert paiement.status == Paiement_stripe.VALID
    vente = vente_du_paiement(paiement)
    assert vente.statut == Vente.Statut.EN_ATTENTE
    assert vente.numero is None
    assert vente.reglements.count() == 0
    assert len(erreurs_du_journal(caplog, JOURNAL_DU_POINT_D_ENCAISSEMENT)) >= 1

    with pytest.raises(ValueError):
        services_vente.encaisser_vente_stripe(paiement)
    vente.refresh_from_db()
    assert vente.statut == Vente.Statut.EN_ATTENTE
