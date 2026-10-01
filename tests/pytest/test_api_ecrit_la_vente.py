"""
Tests des ventes écrites par l'API et par l'ancienne caisse : adhésion gratuite, recharge
cadeau de l'API v2, billets « payés ailleurs » de l'API v2, webhook Fedow d'adhésion.
Chaque chemin écrit une `Vente`, par le service de vente, et l'encaisse.
/ Sales written by the API and by the legacy register: free membership, API v2 gift
refill, API v2 "paid elsewhere" tickets, Fedow membership webhook. Each path writes a
`Vente` through the sale service and settles it.

LOCALISATION : tests/pytest/test_api_ecrit_la_vente.py

L'ADHÉSION GRATUITE (`MembershipValidator`, branche gratuite)
Elle sert à l'API v2 (origine API, mode de paiement « FREE » par défaut) et au front
(origine « en ligne », adhésion à 0 €). La ligne de l'adhésion est l'article d'une vente
ouverte avec elle : origine = celle de la ligne, client = l'adhérent.
- Montant non nul en « offert » (FREE) : règle « offert à montant non nul » du service de
  vente. La part offerte vaut tout le total catalogue (source OFFRIR), le net vendu vaut
  0, et un règlement FREE du même montant est écrit.
- Montant 0 : vente à 0, aucun règlement.
La vente est encaissée APRÈS le passage « payée » de la ligne : le déclencheur de
l'adhésion (`trigger_A`, e-mails, échéance) tourne d'abord et passe la ligne VALID.
/ Free membership: one sale opened with the line; non-zero FREE amount = fully offered
with a FREE payment; 0 = sale at 0. Settled AFTER the line's "paid" trigger.

LA RECHARGE CADEAU DE L'API V2 (`WalletRefillViewSet`)
La ligne de recharge naît « créée » (CREATED) AVANT l'appel à Fedow, dans une vente
EN_ATTENTE ouverte avec elle (origine = celle de la ligne, « en ligne » ; client = le
destinataire de la recharge).
- Fedow répond : la ligne passe VALID et la vente est encaissée. L'article de recharge
  est hors chiffre d'affaires, offert en totalité (OFFRIR), avec un règlement FREE.
- Fedow échoue : la ligne passe FAILED, la vente RESTE EN_ATTENTE, sans numéro (son
  règlement FREE, écrit avec l'article offert, est déjà là : sans effet comptable tant
  que la vente n'est pas encaissée).
- Le nouvel essai (même clé d'idempotence, même ligne) encaisse LA MÊME vente : une
  seule vente pour toutes les demandes.
`Vente.unite` vaut la monnaie créditée (son uuid) seulement pour du temps ou des points
(TIM, FID). Une monnaie cadeau (TNF) est libellée en euros : `unite` reste "EUR".
L'anti double crédit reste le verrou de `LigneArticle.idempotency_key` : même clé pendant
un crédit en cours, ou même clé avec un autre corps → 409.
/ API v2 gift refill: the line is born CREATED in a PENDING sale. Success: settled (off
revenue, fully offered, FREE payment). Failure: the sale stays PENDING; the retry settles
the same sale. Unit = the currency only for time or points. The 409 lock stays.

LES BILLETS « PAYÉS AILLEURS » DE L'API V2 (`additionalProperty paymentMethod`)
La caisse LaBoutik a déjà encaissé l'argent (« cash » = espèces, « card » = carte
bancaire). Les lignes des billets entrent dans une vente (origine = celle des lignes,
LaBoutik). UN règlement au moyen déclaré (CA ou CC), du total net des lignes payées, puis
la vente est encaissée. Une « réservation gratuite » du même appel n'écrit aucune ligne :
ses billets sont créés, et la vente ne contient que les lignes payées.
/ API v2 "paid elsewhere": one sale, one payment at the declared method for the net total
of the paid lines, then settled. A free booking of the same call writes no line.

LA RÉSERVATION DE L'API V2 EST ÉCRITE EN ENTIER OU PAS DU TOUT
(`ReservationViewSet.create`, « payé ailleurs » et réservation gratuite)
Réservation, billets, lignes, vente, règlement et encaissement sont écrits dans une seule
transaction. Si l'encaissement échoue, rien n'est écrit : ni réservation, ni billet, ni
ligne, ni vente. L'erreur remonte : la réponse est une erreur serveur (500, Sentry). Ces
tests passent par la vraie route (`POST /api/v2/reservations/`), car la transaction est
posée par la vue.
/ The API v2 reservation is all or nothing: if the settlement fails, nothing is written
and the response is a server error (500). Tested through the real route.

LE WEBHOOK FEDOW D'ADHÉSION (`Membership_fwh`, ancienne caisse)
Une adhésion vendue par l'ancienne caisse arrive par Fedow. Sa ligne (moyen inconnu,
origine LaBoutik) entre dans une vente (client = l'adhérent, vide s'il est inconnu de
Lespass), avec UN règlement « inconnu »
(UNKNOWN) du montant, encaissée. Ligne, vente et encaissement sont écrits ensemble ou pas
du tout. Un rejeu de la même transaction Fedow n'écrit rien de plus.
/ Fedow membership webhook: one sale, one UNKNOWN payment, settled; all or nothing; a
replay writes nothing more.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin, rien ne reste
en base de dev (tests/PIEGES.md 13.1). Stripe (session et catalogue), Fedow et Celery
sont simulés : aucun appel réseau, aucune tâche envoyée au worker.
/ Rolled-back transaction per test. Stripe, Fedow and Celery are faked.

CODE PARCOURU / CODE EXERCISED
- BaseBillet/validators.py — MembershipValidator (branche gratuite), TicketCreator
  (branche `paid_externally`) ;
- api_v2/serializers.py — MembershipCreateSerializer, ReservationCreateSerializer ;
- api_v2/views.py — WalletRefillViewSet (recharge cadeau, `_creer_ligne_article_recharge`),
  ReservationViewSet.create (la transaction de la réservation) ;
- BaseBillet/views.py — MembershipMVT.create (adhésion du front) ;
- fedow_connect/views.py — Membership_fwh.retrieve (webhook Fedow d'adhésion) ;
- BaseBillet/services_vente.py — ouvrir_vente, ajouter_article, ajouter_reglement,
  encaisser_vente.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-D-en-ligne-avoirs.md (§3,
§5 tests 13 et 16) ; CHANTIER-05-SUIVI.md (§4 « D-2 » et « Relecture Fable D-1 + D-2 »,
§5 du 2026-10-01) ; briefs CHANTIER-05-briefs/05-D-2c.md et 05-D-1z.md.

Lancer / Run : make test ARGS="tests/pytest/test_api_ecrit_la_vente.py"
"""

import logging
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient
from rest_framework_api_key.models import APIKey

from api_v2.serializers import MembershipCreateSerializer, ReservationCreateSerializer
from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import (
    ExternalApiKey,
    FedowTransaction,
    LigneArticle,
    Membership,
    PaymentMethod,
    Product,
    Reservation,
    SaleOrigin,
    Ticket,
)
from BaseBillet.models_vente import Vente
from fabriques_panier import (
    PREFIXE_DE_TEST,
    ajouter_un_tarif,
    catalogue_stripe_simule,
    client_connecte,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_vente import verifier_egalites
from fedow_public.models import AssetFedowPublic
from test_admin_ecrit_la_vente import (
    encaissement_qui_echoue,
    statuts_des_articles_a_l_encaissement,
)
from test_caracterisation_en_ligne import adherer_sans_panier

pytestmark = pytest.mark.django_db

# Adresse de la recharge cadeau de l'API v2 (api_v2/urls.py).
# / API v2 gift refill address.
URL_DE_LA_RECHARGE = "/api/v2/wallet-refills/"

# Nom de domaine du lieu de test : le middleware django-tenants en déduit le schéma.
# / Test venue domain: django-tenants resolves the schema from it.
DOMAINE_DU_LIEU = "lespass.tibillet.localhost"


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
# Assistants communs
# / Shared helpers
# --------------------------------------------------------------------------


def la_vente_unique_des_lignes(lignes):
    """
    Rend LA vente dont les articles sont ces lignes. Échoue si une ligne n'a pas de
    vente, ou si les lignes sont dans plusieurs ventes.
    / Returns THE sale whose items are these lines. Fails on a line without sale, or
    on lines spread over several sales.
    """
    ventes_trouvees = set()
    for ligne in lignes:
        ligne.refresh_from_db()
        assert ligne.vente_id is not None, (
            f"La ligne {ligne.uuid} n'a pas de vente (LigneArticle.vente vide)."
        )
        ventes_trouvees.add(ligne.vente_id)
    assert len(ventes_trouvees) == 1, (
        f"Les lignes sont dans {len(ventes_trouvees)} vente(s), une attendue."
    )
    return Vente.objects.get(pk=ventes_trouvees.pop())


def verifier_la_vente_encaissee(vente, origine_attendue, client_attendu):
    """
    Relit la vente en base et vérifie qu'elle est une VENTE encaissée : REGLEE,
    numérotée, avec l'origine et le client attendus.
    / Reads the sale back: VENTE, settled, numbered, expected origin and client.

    :return: la vente relue, pour les vérifications propres à chaque test
    """
    vente_relue = Vente.objects.get(pk=vente.pk)
    assert vente_relue.nature == Vente.Nature.VENTE
    assert vente_relue.statut == Vente.Statut.REGLEE, (
        f"La vente n'est pas encaissée (statut {vente_relue.statut})."
    )
    assert vente_relue.numero is not None
    assert vente_relue.origine == origine_attendue
    assert vente_relue.client == client_attendu
    return vente_relue


def moyens_et_montants_des_reglements(vente):
    """
    Les règlements de la vente, relus en base : une liste de couples (moyen, montant),
    triée.
    / The sale's payments, read back: a sorted list of (method, amount) pairs.
    """
    reglements_lus = []
    for reglement in vente.reglements.all():
        reglements_lus.append((reglement.moyen, reglement.montant))
    return sorted(reglements_lus)


def identifiants_des_articles(vente):
    """Les clés des articles de la vente, en ensemble. / The sale's item keys, as a set."""
    identifiants = set()
    for article in vente.articles.all():
        identifiants.add(article.pk)
    return identifiants


# --------------------------------------------------------------------------
# Adhésion gratuite : API v2 et front
# / Free membership: API v2 and front
# --------------------------------------------------------------------------


def adherer_par_l_api_v2(tarif, email):
    """
    Crée une adhésion par le serializer d'entrée de l'API v2, comme le fait la vue :
    validation, puis `save()`. Sans `paymentMode`, l'API prend le mode « FREE » : pas de
    Stripe, l'adhésion est validée tout de suite.
    / Creates a membership through the API v2 input serializer. Without paymentMode the
    API uses "FREE": no Stripe, validated at once.

    :return: l'adhésion (`Membership`) créée
    """
    serializer_d_adhesion = MembershipCreateSerializer(
        data={
            "member": {
                "@type": "Person",
                "email": email,
                "givenName": "Ada",
                "familyName": "Lovelace",
            },
            "membershipPlan": {"@type": "Offer", "identifier": str(tarif.uuid)},
        }
    )
    serializer_d_adhesion.is_valid(raise_exception=True)
    return serializer_d_adhesion.save()


def test_adhesion_gratuite_api_montant_non_nul_offerte(lieu):
    """
    Fiche test 13. Par l'API v2, en mode « FREE », une adhésion à un tarif de 15 €.
    Aucun paiement Stripe. La ligne de l'adhésion est écrite au prix (1500), en
    « offert » : part offerte = 1500 (source OFFRIR), net vendu 0. Elle est VALID (le
    déclencheur de l'adhésion a tourné).
    Sa vente : origine API, client = l'adhérente, REGLEE, numérotée, UN règlement FREE de
    1500. L'ORDRE : quand la vente passe REGLEE, la ligne est déjà VALID.
    / Test 13: 15 € membership through the API in FREE mode: fully offered line, one FREE
    payment of 1500, sale settled AFTER the line went VALID.
    """
    adhesion = creer_adhesion(prix="15.00")
    email_de_l_adherente = f"test+apivente{identifiant_unique()}@mock.test"

    with statuts_des_articles_a_l_encaissement() as statuts_a_l_encaissement:
        adhesion_creee = adherer_par_l_api_v2(adhesion.tarif, email_de_l_adherente)

    assert lieu.stripe.mock_create.call_count == 0
    adhesion_creee.refresh_from_db()
    assert adhesion_creee.status == Membership.ONCE
    ligne = LigneArticle.objects.get(membership=adhesion_creee)
    assert ligne.status == LigneArticle.VALID
    assert ligne.payment_method == PaymentMethod.FREE

    adherente = TibilletUser.objects.get(email=email_de_l_adherente)
    vente = verifier_la_vente_encaissee(
        la_vente_unique_des_lignes([ligne]),
        origine_attendue=SaleOrigin.API,
        client_attendu=adherente,
    )
    article_offert = vente.articles.get()
    assert article_offert.amount == 1500
    assert article_offert.total_catalogue == 1500
    assert article_offert.part_offerte == 1500
    assert article_offert.source_offert == LigneArticle.SourceOffert.OFFRIR
    assert article_offert.total_ttc == 0
    assert moyens_et_montants_des_reglements(vente) == [(PaymentMethod.FREE, 1500)]

    # Un seul encaissement, et la ligne était déjà VALID à ce moment-là.
    # / One settlement, and the line was already VALID at that moment.
    assert statuts_a_l_encaissement == [[LigneArticle.VALID]]
    verifier_egalites(vente)


def test_adhesion_gratuite_front_montant_zero_vente_a_zero(lieu):
    """
    Par le formulaire d'adhésion du front, une adhésion à un tarif de 0 €. Aucun
    paiement Stripe. La ligne de l'adhésion (0, « offert ») est VALID. Sa vente : origine
    « en ligne » (LP), client = l'adhérent, REGLEE, numérotée, total 0, AUCUN règlement.
    Elle est encaissée après le passage « payée » de la ligne.
    / A 0 € membership through the front form: the line is VALID; its sale (online
    origin, client = member) is settled at 0, numbered, no payment, after the trigger.
    """
    adherent = creer_utilisateur()
    client = client_connecte(adherent)
    adhesion_gratuite = creer_adhesion(prix="0.00")

    with statuts_des_articles_a_l_encaissement() as statuts_a_l_encaissement:
        adherer_sans_panier(client, adherent, adhesion_gratuite.tarif)

    assert lieu.stripe.mock_create.call_count == 0
    adhesion_creee = Membership.objects.get(
        user=adherent, price=adhesion_gratuite.tarif
    )
    assert adhesion_creee.status == Membership.ONCE
    ligne = LigneArticle.objects.get(membership=adhesion_creee)
    assert ligne.status == LigneArticle.VALID
    assert ligne.payment_method == PaymentMethod.FREE

    vente = verifier_la_vente_encaissee(
        la_vente_unique_des_lignes([ligne]),
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=adherent,
    )
    assert vente.total_catalogue == 0
    assert vente.reglements.count() == 0
    assert statuts_a_l_encaissement == [[LigneArticle.VALID]]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# Recharge cadeau de l'API v2
# / API v2 gift refill
# --------------------------------------------------------------------------


def creer_une_cle_api_de_recharge(lieu, categorie_de_la_monnaie):
    """
    Une monnaie du lieu, de la catégorie donnée (cadeau TNF, temps TIM, fidélité FID),
    et une clé API v2 autorisée à la recharger.
    / A venue currency of the given category and an API v2 key allowed to top it up.

    Rend un objet avec `cle` (le texte à mettre dans l'en-tête) et `monnaie`.
    """
    portefeuille_du_lieu = Wallet.objects.create(origin=lieu.tenant)
    monnaie = AssetFedowPublic.objects.create(
        name=f"{PREFIXE_DE_TEST} monnaie {identifiant_unique()}",
        currency_code="TST",
        wallet_origin=portefeuille_du_lieu,
        origin=lieu.tenant,
        category=categorie_de_la_monnaie,
    )
    cle_api, texte_de_la_cle = APIKey.objects.create_key(
        name=f"{PREFIXE_DE_TEST} recharge {identifiant_unique()}"
    )
    ExternalApiKey.objects.create(
        name=f"{PREFIXE_DE_TEST} recharge {identifiant_unique()}",
        key=cle_api,
        gift_asset=monnaie,
    )
    return SimpleNamespace(cle=texte_de_la_cle, monnaie=monnaie)


def demander_une_recharge(cle_api, destinataire, montant, cle_d_idempotence):
    """
    Le partenaire appelle l'API v2 pour créditer `montant` unités de la monnaie à
    `destinataire`, avec sa clé d'idempotence (en-tête `Idempotency-Key`).
    / The partner calls API v2 to credit `montant` units, with its idempotency key.
    """
    client_du_partenaire = APIClient()
    return client_du_partenaire.post(
        URL_DE_LA_RECHARGE,
        data={
            "email": destinataire.email,
            "asset": str(cle_api.monnaie.uuid),
            "amount": montant,
        },
        format="json",
        SERVER_NAME=DOMAINE_DU_LIEU,
        HTTP_AUTHORIZATION=f"Api-Key {cle_api.cle}",
        HTTP_IDEMPOTENCY_KEY=cle_d_idempotence,
    )


def lignes_de_recharge_de_la_monnaie(monnaie):
    """
    Les lignes de vente « recharge » de cette monnaie. La vue range chaque recharge sous
    un produit dédié à la monnaie, nommé « Recharge <nom de la monnaie> »
    (api_v2/views.py, `_creer_ligne_article_recharge`).
    / The refill sale lines of this currency, found through the per-currency product.
    """
    return LigneArticle.objects.filter(
        pricesold__productsold__product__name=f"Recharge {monnaie.name}"
    )


def ventes_des_recharges_de_la_monnaie(monnaie):
    """Les ventes dont un article est une recharge de cette monnaie.
    / The sales holding a refill line of this currency."""
    return Vente.objects.filter(
        articles__pricesold__productsold__product__name=f"Recharge {monnaie.name}"
    ).distinct()


def fedow_qui_repond(identifiant_de_la_transaction):
    """Fedow simulé qui crédite la tirelire et rend sa transaction.
    / Faked Fedow that credits the wallet and returns its transaction."""

    def crediter_la_tirelire(user, amount, asset, metadata):
        return {"uuid": identifiant_de_la_transaction}

    return crediter_la_tirelire


def fedow_en_panne(user, amount, asset, metadata):
    """Fedow simulé qui ne répond pas. / Faked Fedow that does not answer."""
    raise ConnectionError("Fedow ne répond pas")


def verifier_l_article_de_recharge_offert(vente, montant_attendu):
    """
    L'unique article de la vente est la recharge : hors chiffre d'affaires, TVA 0,
    offerte en totalité (part offerte = total catalogue, source OFFRIR, net 0), et la
    vente a UN règlement FREE du même montant.
    / The sale's only item is the refill: off revenue, VAT 0, fully offered, one FREE
    payment of the same amount.
    """
    article_de_recharge = vente.articles.get()
    assert article_de_recharge.hors_chiffre_affaires is True
    assert article_de_recharge.vat == 0
    assert article_de_recharge.amount == montant_attendu
    assert article_de_recharge.total_catalogue == montant_attendu
    assert article_de_recharge.part_offerte == montant_attendu
    assert article_de_recharge.source_offert == LigneArticle.SourceOffert.OFFRIR
    assert article_de_recharge.total_ttc == 0
    assert moyens_et_montants_des_reglements(vente) == [
        (PaymentMethod.FREE, montant_attendu)
    ]


def test_recharge_api_v2_echec_puis_nouvel_essai_une_vente(lieu):
    """
    Fiche test 16. Un partenaire offre 300 jetons cadeau, avec sa clé d'idempotence.
    1. Fedow est en panne : réponse 502. La ligne passe FAILED. Elle est pourtant déjà
       l'article d'une vente, ouverte avec elle : cette vente RESTE EN_ATTENTE, sans
       numéro (origine « en ligne », celle de la ligne ; client = le destinataire). Son
       règlement FREE, écrit avec l'article offert, est déjà là.
    2. Nouvel essai, même clé : Fedow répond, réponse 201. La MÊME ligne passe VALID, et
       LA MÊME vente est encaissée : REGLEE, numérotée, article de recharge hors chiffre
       d'affaires offert en totalité, règlement FREE de 300.
    Une seule vente de plus en base pour les deux demandes.
    / Test 16: Fedow down → line FAILED, its sale stays PENDING without number; retry with
    the same key → the SAME sale is settled. One single sale for both requests.
    """
    destinataire = creer_utilisateur()
    cle_api = creer_une_cle_api_de_recharge(lieu, AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT)
    cle_d_idempotence = f"test-apivente-{uuid.uuid4().hex}"
    nombre_de_ventes_avant = Vente.objects.count()

    with (
        patch("fedow_connect.models.FedowConfig.can_fedow", return_value=True),
        patch("fedow_connect.fedow_api.FedowAPI") as fedow_simule,
    ):
        recharger_la_tirelire = (
            fedow_simule.return_value.transaction.refill_from_lespass_to_user_wallet
        )

        # 1. Fedow en panne : la vente reste EN_ATTENTE, sans numéro.
        # / 1. Fedow down: the sale stays PENDING, without number.
        recharger_la_tirelire.side_effect = fedow_en_panne
        reponse_du_premier_essai = demander_une_recharge(
            cle_api, destinataire, 300, cle_d_idempotence
        )
        assert reponse_du_premier_essai.status_code == 502
        ligne_de_recharge = lignes_de_recharge_de_la_monnaie(cle_api.monnaie).get()
        assert ligne_de_recharge.status == LigneArticle.FAILED

        vente_apres_l_echec = la_vente_unique_des_lignes([ligne_de_recharge])
        assert vente_apres_l_echec.nature == Vente.Nature.VENTE
        assert vente_apres_l_echec.statut == Vente.Statut.EN_ATTENTE
        assert vente_apres_l_echec.numero is None
        # Le règlement FREE est écrit AVEC l'article offert (règle « offert à montant
        # non nul » du service) : il est là, mais la vente non encaissée n'a aucun
        # effet comptable.
        # / The FREE payment is written WITH the offered item; the unsettled sale has
        # no accounting effect.
        assert moyens_et_montants_des_reglements(vente_apres_l_echec) == [
            (PaymentMethod.FREE, 300)
        ]
        assert vente_apres_l_echec.origine == SaleOrigin.LESPASS
        assert vente_apres_l_echec.client == destinataire
        assert identifiants_des_articles(vente_apres_l_echec) == {ligne_de_recharge.pk}

        # 2. Nouvel essai avec la même clé : Fedow répond.
        # / 2. Retry with the same key: Fedow answers.
        recharger_la_tirelire.side_effect = fedow_qui_repond(str(uuid.uuid4()))
        reponse_du_nouvel_essai = demander_une_recharge(
            cle_api, destinataire, 300, cle_d_idempotence
        )

    assert reponse_du_nouvel_essai.status_code == 201
    assert lignes_de_recharge_de_la_monnaie(cle_api.monnaie).count() == 1
    ligne_de_recharge.refresh_from_db()
    assert ligne_de_recharge.status == LigneArticle.VALID

    # La même vente, maintenant encaissée. Une seule vente de plus en base.
    # / The same sale, now settled. One single extra sale in the database.
    vente_encaissee = la_vente_unique_des_lignes([ligne_de_recharge])
    assert vente_encaissee.pk == vente_apres_l_echec.pk
    assert Vente.objects.count() == nombre_de_ventes_avant + 1
    assert ventes_des_recharges_de_la_monnaie(cle_api.monnaie).count() == 1
    vente_encaissee = verifier_la_vente_encaissee(
        vente_encaissee,
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=destinataire,
    )
    assert vente_encaissee.unite == "EUR"
    verifier_l_article_de_recharge_offert(vente_encaissee, montant_attendu=300)
    verifier_egalites(vente_encaissee)


def recharger_avec_succes(lieu, categorie_de_la_monnaie, montant):
    """
    Une recharge de `montant` unités d'une monnaie de la catégorie donnée, Fedow qui
    répond. Rend la monnaie et la vente de la recharge.
    / One successful refill of a currency of the given category. Returns the currency
    and the refill's sale.
    """
    destinataire = creer_utilisateur()
    cle_api = creer_une_cle_api_de_recharge(lieu, categorie_de_la_monnaie)

    with (
        patch("fedow_connect.models.FedowConfig.can_fedow", return_value=True),
        patch("fedow_connect.fedow_api.FedowAPI") as fedow_simule,
    ):
        fedow_simule.return_value.transaction.refill_from_lespass_to_user_wallet.side_effect = fedow_qui_repond(
            str(uuid.uuid4())
        )
        reponse = demander_une_recharge(
            cle_api, destinataire, montant, f"test-apivente-{uuid.uuid4().hex}"
        )

    assert reponse.status_code == 201
    ligne_de_recharge = lignes_de_recharge_de_la_monnaie(cle_api.monnaie).get()
    assert ligne_de_recharge.status == LigneArticle.VALID
    vente = la_vente_unique_des_lignes([ligne_de_recharge])
    return SimpleNamespace(
        monnaie=cle_api.monnaie, vente=vente, destinataire=destinataire
    )


def test_recharge_api_v2_temps_unite_points(lieu):
    """
    Une recharge de 120 unités de monnaie temps (TIM). Le temps n'est pas de l'argent :
    la vente est dans l'unité de la monnaie créditée (`Vente.unite` = son uuid). Elle est
    encaissée, l'article de recharge offert en totalité, règlement FREE de 120.
    / A 120-unit time-currency refill: the sale's unit is the credited currency (its
    uuid); settled, fully offered, FREE payment of 120.
    """
    recharge = recharger_avec_succes(lieu, AssetFedowPublic.TIME, 120)

    vente = verifier_la_vente_encaissee(
        recharge.vente,
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=recharge.destinataire,
    )
    assert vente.unite == str(recharge.monnaie.uuid)
    verifier_l_article_de_recharge_offert(vente, montant_attendu=120)
    verifier_egalites(vente)


def test_recharge_api_v2_cadeau_unite_eur(lieu):
    """
    Une recharge de 500 jetons cadeau (TNF). Une monnaie cadeau est libellée en euros :
    la vente garde `unite` = "EUR" (sinon le rapport la classerait « points » et
    l'exclurait de tout). Elle est encaissée, l'article de recharge offert en totalité,
    règlement FREE de 500.
    / A 500-token gift refill: a gift currency is euro-denominated, the sale keeps
    unite = "EUR"; settled, fully offered, FREE payment of 500.
    """
    recharge = recharger_avec_succes(lieu, AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT, 500)

    vente = verifier_la_vente_encaissee(
        recharge.vente,
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=recharge.destinataire,
    )
    assert vente.unite == "EUR"
    verifier_l_article_de_recharge_offert(vente, montant_attendu=500)
    verifier_egalites(vente)


def test_recharge_api_v2_idempotence_toujours_409(lieu):
    """
    Le verrou anti double crédit reste celui de `LigneArticle.idempotency_key`.
    1. Pendant que Fedow crédite la première demande, le partenaire renvoie la même
       demande (même clé) : réponse 409, un crédit est déjà en cours. Rien n'est écrit.
    2. Après le succès, la même clé avec un autre montant : réponse 409.
    Fedow n'est appelé qu'une fois. Une seule ligne, une seule vente, encaissée une fois
    (un seul règlement FREE de 300).
    / The anti double-credit lock stays on LigneArticle.idempotency_key: same key during a
    credit in progress → 409; same key, other amount → 409. One line, one settled sale.
    """
    destinataire = creer_utilisateur()
    cle_api = creer_une_cle_api_de_recharge(lieu, AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT)
    cle_d_idempotence = f"test-apivente-{uuid.uuid4().hex}"
    nombre_de_ventes_avant = Vente.objects.count()
    reponses_pendant_le_credit = []

    def fedow_qui_recoit_un_doublon_pendant_le_credit(user, amount, asset, metadata):
        # Le partenaire renvoie la même demande pendant que Fedow crédite la première.
        # / The partner sends the same request again while Fedow credits the first one.
        reponse_du_doublon = demander_une_recharge(
            cle_api, destinataire, 300, cle_d_idempotence
        )
        reponses_pendant_le_credit.append(reponse_du_doublon.status_code)
        return {"uuid": str(uuid.uuid4())}

    with (
        patch("fedow_connect.models.FedowConfig.can_fedow", return_value=True),
        patch("fedow_connect.fedow_api.FedowAPI") as fedow_simule,
    ):
        recharger_la_tirelire = (
            fedow_simule.return_value.transaction.refill_from_lespass_to_user_wallet
        )
        recharger_la_tirelire.side_effect = (
            fedow_qui_recoit_un_doublon_pendant_le_credit
        )
        reponse_de_la_premiere_demande = demander_une_recharge(
            cle_api, destinataire, 300, cle_d_idempotence
        )
        reponse_avec_un_autre_montant = demander_une_recharge(
            cle_api, destinataire, 999, cle_d_idempotence
        )

    assert reponse_de_la_premiere_demande.status_code == 201
    assert reponses_pendant_le_credit == [409]
    assert reponse_avec_un_autre_montant.status_code == 409
    assert recharger_la_tirelire.call_count == 1

    ligne_de_recharge = lignes_de_recharge_de_la_monnaie(cle_api.monnaie).get()
    assert ligne_de_recharge.status == LigneArticle.VALID
    assert Vente.objects.count() == nombre_de_ventes_avant + 1
    vente = verifier_la_vente_encaissee(
        la_vente_unique_des_lignes([ligne_de_recharge]),
        origine_attendue=SaleOrigin.LESPASS,
        client_attendu=destinataire,
    )
    verifier_l_article_de_recharge_offert(vente, montant_attendu=300)
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# API v2 : billets « payés ailleurs » (caisse LaBoutik)
# / API v2: tickets "paid elsewhere" (LaBoutik register)
# --------------------------------------------------------------------------


def reserver_par_l_api_v2_paye_ailleurs(evenement, quantites_par_tarif, email, moyen):
    """
    Crée une réservation par le serializer d'entrée de l'API v2, déjà payée à la caisse
    (`additionalProperty paymentMethod` = "cash" ou "card"), comme le fait la vue.
    / Creates an API v2 reservation already paid at the register ("cash" or "card").

    :return: la `Reservation` créée
    """
    billets_demandes = []
    for tarif, quantite in quantites_par_tarif.items():
        billets_demandes.append(
            {
                "@type": "Ticket",
                "identifier": str(tarif.uuid),
                "ticketQuantity": quantite,
            }
        )
    serializer_de_reservation = ReservationCreateSerializer(
        data={
            "reservationFor": {"@type": "Event", "identifier": str(evenement.uuid)},
            "underName": {"@type": "Person", "email": email},
            "reservedTicket": billets_demandes,
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "paymentMethod", "value": moyen},
            ],
        }
    )
    serializer_de_reservation.is_valid(raise_exception=True)
    return serializer_de_reservation.save()


@pytest.mark.parametrize(
    "moyen_declare, moyen_du_reglement",
    [
        ("cash", PaymentMethod.CASH),
        ("card", PaymentMethod.CC),
    ],
    ids=["especes_une_vente_reglement_ca", "carte_reglement_cc"],
)
def test_api_v2_paye_ailleurs_une_vente_reglement_au_moyen_declare(
    lieu, moyen_declare, moyen_du_reglement
):
    """
    `test_api_v2_paye_ailleurs_especes_une_vente_reglement_ca` et
    `…_carte_reglement_cc` du brief. Par l'API v2, la caisse envoie deux billets à 10 €
    déjà payés (« cash », puis « card »). Aucun paiement Stripe. La ligne des billets
    (VALID) est l'article d'UNE vente : origine LaBoutik (celle de la ligne), client = la
    personne réservée, REGLEE, numérotée. UN règlement au moyen déclaré (espèces CA,
    carte CC), du total net : 2000.
    / Two 10 € tickets already paid at the register: one sale (LaBoutik origin), settled,
    one payment at the declared method for the net total (2000).
    """
    concert = creer_evenement_avec_tarif(prix="10.00")
    email_de_la_personne = f"test+apivente{identifiant_unique()}@mock.test"
    nombre_de_ventes_avant = Vente.objects.count()

    reservation = reserver_par_l_api_v2_paye_ailleurs(
        concert.evenement, {concert.tarif: 2}, email_de_la_personne, moyen_declare
    )

    assert lieu.stripe.mock_create.call_count == 0
    assert reservation.status == Reservation.VALID
    ligne_des_billets = LigneArticle.objects.get(reservation=reservation)
    assert ligne_des_billets.status == LigneArticle.VALID

    assert Vente.objects.count() == nombre_de_ventes_avant + 1
    personne_reservee = TibilletUser.objects.get(email=email_de_la_personne)
    vente = verifier_la_vente_encaissee(
        la_vente_unique_des_lignes([ligne_des_billets]),
        origine_attendue=SaleOrigin.LABOUTIK,
        client_attendu=personne_reservee,
    )
    assert vente.articles.get().total_catalogue == 2000
    assert vente.total_ttc == 2000
    assert moyens_et_montants_des_reglements(vente) == [(moyen_du_reglement, 2000)]
    verifier_egalites(vente)


@pytest.mark.parametrize("produit_cree_en_premier", ["payant", "reservation_gratuite"])
def test_api_v2_paye_ailleurs_et_reservation_gratuite_meme_vente(
    lieu, produit_cree_en_premier
):
    """
    Par l'API v2, dans le même appel, payé en espèces à la caisse : un billet à 10 € et
    une « réservation gratuite » (FREERES) du même événement. En « payé ailleurs », l'API
    n'écrit pas de ligne pour la réservation gratuite : ses billets sont créés, sans
    ligne de vente. La seule ligne de la réservation est celle du billet payé ; elle est
    l'unique article d'UNE vente : origine LaBoutik, REGLEE, numérotée, UN règlement
    espèces de 1000.
    Les deux ordres des produits sont joués (tests/PIEGES.md 13.15).
    / A paid ticket and a free booking in one "paid in cash" API call: no line for the
    free booking; the paid line is the only item of ONE settled sale, one cash payment of
    1000. Both product orders played.
    """
    if produit_cree_en_premier == "payant":
        concert = creer_evenement_avec_tarif(prix="10.00")
        tarif_payant = concert.tarif
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
        tarif_payant = ajouter_un_tarif(produit_payant, prix="10.00", nom="Plein tarif")
    email_de_la_personne = f"test+apivente{identifiant_unique()}@mock.test"
    nombre_de_ventes_avant = Vente.objects.count()

    reservation = reserver_par_l_api_v2_paye_ailleurs(
        concert.evenement,
        {tarif_payant: 1, tarif_reservation_gratuite: 1},
        email_de_la_personne,
        "cash",
    )

    assert lieu.stripe.mock_create.call_count == 0
    assert reservation.status == Reservation.VALID
    assert reservation.tickets.count() == 2

    # Une seule ligne : celle du billet payé. Aucune ligne pour la réservation gratuite.
    # / One single line: the paid ticket's. No line for the free booking.
    ligne_du_billet_paye = LigneArticle.objects.get(reservation=reservation)
    assert ligne_du_billet_paye.pricesold.price == tarif_payant
    assert ligne_du_billet_paye.status == LigneArticle.VALID
    assert not LigneArticle.objects.filter(
        pricesold__price=tarif_reservation_gratuite
    ).exists()

    assert Vente.objects.count() == nombre_de_ventes_avant + 1
    personne_reservee = TibilletUser.objects.get(email=email_de_la_personne)
    vente = verifier_la_vente_encaissee(
        la_vente_unique_des_lignes([ligne_du_billet_paye]),
        origine_attendue=SaleOrigin.LABOUTIK,
        client_attendu=personne_reservee,
    )
    assert identifiants_des_articles(vente) == {ligne_du_billet_paye.pk}
    assert vente.total_catalogue == 1000
    assert moyens_et_montants_des_reglements(vente) == [(PaymentMethod.CASH, 1000)]
    verifier_egalites(vente)


# --------------------------------------------------------------------------
# API v2 : la réservation est écrite en entier ou pas du tout
# / API v2: the reservation is written all or nothing
# --------------------------------------------------------------------------

# Adresse de création d'une réservation de l'API v2 (api_v2/urls.py).
# / API v2 reservation creation address.
URL_DES_RESERVATIONS = "/api/v2/reservations/"


def creer_une_cle_api_de_reservation():
    """
    Une clé API v2 autorisée à créer des réservations (permission `reservation`).
    / An API v2 key allowed to create reservations.

    :return: le texte de la clé, à mettre dans l'en-tête `Authorization`
    """
    cle_api, texte_de_la_cle = APIKey.objects.create_key(
        name=f"TEST_reservation {identifiant_unique()}"
    )
    ExternalApiKey.objects.create(
        name=f"TEST_reservation {identifiant_unique()}",
        key=cle_api,
        reservation=True,
    )
    return texte_de_la_cle


def reserver_par_la_route_api_v2(
    texte_de_la_cle, evenement, quantites_par_tarif, email, moyen=None
):
    """
    Appelle la vraie route de l'API v2 : `POST /api/v2/reservations/`. La transaction de
    la réservation est posée par la vue : passer par le serializer seul ne la voit pas.
    `moyen` : "cash" ou "card" pour un billet « payé ailleurs », rien sinon.
    Une erreur non prévue de la vue devient une réponse 500, comme en production : le
    client de test ne relance pas l'exception (`raise_request_exception = False`).
    / Calls the real API v2 route. The transaction is set by the view. An unexpected
    error becomes a 500 response, like in production.

    :return: la réponse de la route
    """
    billets_demandes = []
    for tarif, quantite in quantites_par_tarif.items():
        billets_demandes.append(
            {
                "@type": "Ticket",
                "identifier": str(tarif.uuid),
                "ticketQuantity": quantite,
            }
        )
    donnees_de_la_reservation = {
        "@context": "https://schema.org",
        "@type": "Reservation",
        "reservationFor": {"@type": "Event", "identifier": str(evenement.uuid)},
        "underName": {"@type": "Person", "email": email},
        "reservedTicket": billets_demandes,
    }
    if moyen is not None:
        donnees_de_la_reservation["additionalProperty"] = [
            {"@type": "PropertyValue", "name": "paymentMethod", "value": moyen},
        ]

    client_de_la_caisse = APIClient()
    client_de_la_caisse.raise_request_exception = False
    return client_de_la_caisse.post(
        URL_DES_RESERVATIONS,
        donnees_de_la_reservation,
        format="json",
        SERVER_NAME=DOMAINE_DU_LIEU,
        HTTP_AUTHORIZATION=f"Api-Key {texte_de_la_cle}",
    )


def verifier_que_rien_n_est_ecrit_pour_l_evenement(
    evenement, tarifs, nombre_de_ventes_avant
):
    """
    Après un appel en échec : aucune réservation pour l'événement, aucun billet, aucune
    ligne de vente pour ses tarifs, et pas une vente de plus en base.
    / After a failed call: no reservation, no ticket, no sale line, no extra sale.
    """
    assert not Reservation.objects.filter(event=evenement).exists(), (
        "Une réservation est restée en base après l'échec de l'encaissement."
    )
    assert not Ticket.objects.filter(reservation__event=evenement).exists(), (
        "Des billets sont restés en base après l'échec de l'encaissement."
    )
    for tarif in tarifs:
        assert not LigneArticle.objects.filter(pricesold__price=tarif).exists(), (
            f"Une ligne de vente du tarif {tarif.name} est restée en base."
        )
    assert Vente.objects.count() == nombre_de_ventes_avant, (
        f"{Vente.objects.count() - nombre_de_ventes_avant} vente(s) de plus en base "
        f"après l'échec de l'encaissement, aucune attendue."
    )


def test_api_v2_paye_ailleurs_encaissement_en_echec_rien_n_est_ecrit(lieu):
    """
    La caisse envoie deux billets à 10 € déjà payés en espèces (« cash ») par la route
    de l'API v2. L'encaissement de la vente échoue (simulé : la vente refuse de passer
    REGLEE). La réponse est une erreur serveur (500). Rien n'est écrit : ni réservation,
    ni billet, ni ligne de vente, ni vente. Un nouvel envoi de la caisse ne crée donc pas
    une seconde réservation.
    / Two cash-paid tickets through the API v2 route; the settlement fails. The response
    is a 500 and nothing is written: no reservation, ticket, sale line or sale.
    """
    concert = creer_evenement_avec_tarif(prix="10.00")
    texte_de_la_cle = creer_une_cle_api_de_reservation()
    email_de_la_personne = f"test+apivente{identifiant_unique()}@mock.test"
    nombre_de_ventes_avant = Vente.objects.count()

    with encaissement_qui_echoue():
        reponse = reserver_par_la_route_api_v2(
            texte_de_la_cle,
            concert.evenement,
            {concert.tarif: 2},
            email_de_la_personne,
            moyen="cash",
        )

    assert reponse.status_code == 500, (
        f"Réponse {reponse.status_code} : une erreur serveur (500) est attendue."
    )
    verifier_que_rien_n_est_ecrit_pour_l_evenement(
        concert.evenement, [concert.tarif], nombre_de_ventes_avant
    )


def test_api_v2_reservation_gratuite_encaissement_en_echec_rien_n_est_ecrit(lieu):
    """
    Par la route de l'API v2, une « réservation gratuite » (FREERES) seule, sans moyen
    de paiement. L'API écrit sa ligne dans une vente qu'elle ouvre, puis l'encaisse à 0.
    L'encaissement échoue (simulé : la vente refuse de passer REGLEE). La réponse est
    une erreur serveur (500). Rien n'est écrit : ni réservation, ni billet, ni ligne de
    vente, ni vente.
    / A free booking alone through the API v2 route; the API writes its line in a sale
    it opens, then settles it at 0. The settlement fails: 500, nothing is written.
    """
    atelier_gratuit = creer_evenement_avec_tarif(categorie=Product.FREERES)
    texte_de_la_cle = creer_une_cle_api_de_reservation()
    email_de_la_personne = f"test+apivente{identifiant_unique()}@mock.test"
    nombre_de_ventes_avant = Vente.objects.count()

    with encaissement_qui_echoue():
        reponse = reserver_par_la_route_api_v2(
            texte_de_la_cle,
            atelier_gratuit.evenement,
            {atelier_gratuit.tarif: 1},
            email_de_la_personne,
        )

    assert reponse.status_code == 500, (
        f"Réponse {reponse.status_code} : une erreur serveur (500) est attendue."
    )
    verifier_que_rien_n_est_ecrit_pour_l_evenement(
        atelier_gratuit.evenement, [atelier_gratuit.tarif], nombre_de_ventes_avant
    )


# --------------------------------------------------------------------------
# Webhook Fedow d'adhésion (adhésion vendue par l'ancienne caisse)
# / Fedow membership webhook (membership sold by the legacy register)
# --------------------------------------------------------------------------


def preparer_une_adhesion_vendue_par_l_ancienne_caisse(montant_en_centimes=2000):
    """
    Fabrique ce que Fedow annonce quand l'ancienne caisse vend une adhésion : un tarif
    d'adhésion, un adhérent avec sa tirelire, la transaction Fedow (connue de Lespass)
    et sa description, telle que `FedowAPI.transaction.retrieve` la rend.
    / Builds what Fedow announces when the legacy register sells a membership.

    L'asset de la transaction est l'uuid du produit d'adhésion : le webhook retrouve le
    produit par lui (`Product.objects.get(pk=asset_uuid)`). Le montant est en centimes.
    / The transaction asset is the membership product's uuid; amount in cents.
    """
    adhesion = creer_adhesion(prix=f"{montant_en_centimes / 100:.2f}")
    adherent = creer_utilisateur()
    adherent.wallet = Wallet.objects.create()
    adherent.save()

    transaction_fedow = FedowTransaction.objects.create(
        uuid=uuid.uuid4(),
        hash=uuid.uuid4().hex,
        datetime=timezone.now(),
    )
    transaction_annoncee_par_fedow = {
        "uuid": str(transaction_fedow.uuid),
        "receiver": str(adherent.wallet.uuid),
        "amount": montant_en_centimes,
        "asset": str(adhesion.produit.uuid),
        "card": None,
    }
    return SimpleNamespace(
        adhesion=adhesion,
        adherent=adherent,
        transaction_fedow=transaction_fedow,
        transaction_annoncee_par_fedow=transaction_annoncee_par_fedow,
    )


def envoyer_le_webhook_fedow_d_adhesion(vente_de_l_ancienne_caisse):
    """
    Fedow prévient Lespass d'une adhésion vendue ailleurs : `GET /fwh/membership/<uuid
    de la transaction>/`. La vue relit la transaction chez Fedow (simulé).
    / Fedow notifies Lespass of a membership sold elsewhere; the view reads the
    transaction back from Fedow (faked).
    """
    with patch("fedow_connect.views.FedowAPI") as fedow_simule:
        fedow_simule.return_value.transaction.retrieve.return_value = (
            vente_de_l_ancienne_caisse.transaction_annoncee_par_fedow
        )
        client_de_fedow = APIClient()
        return client_de_fedow.get(
            f"/fwh/membership/{vente_de_l_ancienne_caisse.transaction_fedow.uuid}/",
            SERVER_NAME=DOMAINE_DU_LIEU,
        )


def test_webhook_fedow_adhesion_vente_reglement_inconnu(lieu):
    """
    L'ancienne caisse a vendu une adhésion de 20 €. Fedow prévient Lespass : réponse 201.
    L'adhésion est créée (statut LaBoutik) et sa ligne (VALID, moyen inconnu, origine
    LaBoutik) est l'article d'UNE vente : origine LaBoutik, client = l'adhérent, REGLEE,
    numérotée. UN règlement « inconnu » (UNKNOWN) de 2000 : l'argent a été reçu par
    l'ancienne caisse.
    / The legacy register sold a 20 € membership: one sale (LaBoutik origin, client =
    member), settled, one UNKNOWN payment of 2000.
    """
    vente_de_l_ancienne_caisse = preparer_une_adhesion_vendue_par_l_ancienne_caisse(
        2000
    )

    reponse = envoyer_le_webhook_fedow_d_adhesion(vente_de_l_ancienne_caisse)

    assert reponse.status_code == 201
    adhesion_creee = Membership.objects.get(
        fedow_transactions=vente_de_l_ancienne_caisse.transaction_fedow
    )
    assert adhesion_creee.status == Membership.LABOUTIK
    ligne = LigneArticle.objects.get(membership=adhesion_creee)
    assert ligne.status == LigneArticle.VALID
    assert ligne.payment_method == PaymentMethod.UNKNOWN
    assert ligne.sale_origin == SaleOrigin.LABOUTIK

    vente = verifier_la_vente_encaissee(
        la_vente_unique_des_lignes([ligne]),
        origine_attendue=SaleOrigin.LABOUTIK,
        client_attendu=vente_de_l_ancienne_caisse.adherent,
    )
    assert vente.articles.get().total_catalogue == 2000
    assert moyens_et_montants_des_reglements(vente) == [(PaymentMethod.UNKNOWN, 2000)]
    verifier_egalites(vente)


def test_webhook_fedow_adhesion_rejoue_une_seule_vente(lieu):
    """
    Fedow envoie deux fois le même webhook (même transaction). Le premier : 201. Le
    second : 208 (« déjà enregistré »), il n'écrit rien. Une seule adhésion, une seule
    ligne, UNE seule vente de plus en base, encaissée, avec un seul règlement.
    / The same webhook sent twice: 201 then 208. One membership, one line, ONE sale,
    settled, with one payment.
    """
    vente_de_l_ancienne_caisse = preparer_une_adhesion_vendue_par_l_ancienne_caisse(
        2000
    )
    nombre_de_ventes_avant = Vente.objects.count()

    premiere_reponse = envoyer_le_webhook_fedow_d_adhesion(vente_de_l_ancienne_caisse)
    reponse_au_rejeu = envoyer_le_webhook_fedow_d_adhesion(vente_de_l_ancienne_caisse)

    assert premiere_reponse.status_code == 201
    assert reponse_au_rejeu.status_code == 208
    adhesion_creee = Membership.objects.get(
        fedow_transactions=vente_de_l_ancienne_caisse.transaction_fedow
    )
    ligne = LigneArticle.objects.get(membership=adhesion_creee)
    assert Vente.objects.count() == nombre_de_ventes_avant + 1
    vente = verifier_la_vente_encaissee(
        la_vente_unique_des_lignes([ligne]),
        origine_attendue=SaleOrigin.LABOUTIK,
        client_attendu=vente_de_l_ancienne_caisse.adherent,
    )
    assert moyens_et_montants_des_reglements(vente) == [(PaymentMethod.UNKNOWN, 2000)]
    verifier_egalites(vente)


def test_webhook_fedow_adhesion_adherent_inconnu_client_vide(lieu):
    """
    L'ancienne caisse a vendu une adhésion de 20 € à une carte dont la tirelire n'est
    reliée à aucun compte Lespass. Fedow prévient Lespass : réponse 201. L'adhésion est
    créée sans utilisateur. Sa ligne est l'article d'UNE vente encaissée, au client
    VIDE, avec UN règlement « inconnu » (UNKNOWN) de 2000.
    / A membership sold to a card whose wallet belongs to no Lespass account: the
    membership has no user; one settled sale with an EMPTY client, one UNKNOWN payment.
    """
    vente_de_l_ancienne_caisse = preparer_une_adhesion_vendue_par_l_ancienne_caisse(
        2000
    )
    tirelire_inconnue_de_lespass = str(uuid.uuid4())
    vente_de_l_ancienne_caisse.transaction_annoncee_par_fedow["receiver"] = (
        tirelire_inconnue_de_lespass
    )

    reponse = envoyer_le_webhook_fedow_d_adhesion(vente_de_l_ancienne_caisse)

    assert reponse.status_code == 201
    adhesion_creee = Membership.objects.get(
        fedow_transactions=vente_de_l_ancienne_caisse.transaction_fedow
    )
    assert adhesion_creee.user is None
    ligne = LigneArticle.objects.get(membership=adhesion_creee)
    assert ligne.status == LigneArticle.VALID

    vente = verifier_la_vente_encaissee(
        la_vente_unique_des_lignes([ligne]),
        origine_attendue=SaleOrigin.LABOUTIK,
        client_attendu=None,
    )
    assert moyens_et_montants_des_reglements(vente) == [(PaymentMethod.UNKNOWN, 2000)]
    verifier_egalites(vente)


def test_webhook_fedow_adhesion_encaissement_en_echec_rien_n_est_ecrit(lieu, caplog):
    """
    L'encaissement de la vente échoue (simulé). Ligne, vente et encaissement sont écrits
    ensemble ou pas du tout : il ne reste ni ligne ni vente. L'erreur est journalisée et
    la réponse reste 201 (le `try / except` du webhook l'attrape). L'adhésion, créée
    avant, reste.
    / The settlement fails: line, sale and settlement are all-or-nothing, so neither line
    nor sale remains. The error is logged, the response stays 201; the membership stays.
    """
    vente_de_l_ancienne_caisse = preparer_une_adhesion_vendue_par_l_ancienne_caisse(
        2000
    )
    nombre_de_ventes_avant = Vente.objects.count()

    with caplog.at_level(logging.ERROR, logger="fedow_connect.views"):
        with encaissement_qui_echoue():
            reponse = envoyer_le_webhook_fedow_d_adhesion(vente_de_l_ancienne_caisse)

    assert reponse.status_code == 201
    adhesion_creee = Membership.objects.get(
        fedow_transactions=vente_de_l_ancienne_caisse.transaction_fedow
    )
    assert not LigneArticle.objects.filter(membership=adhesion_creee).exists()
    assert Vente.objects.count() == nombre_de_ventes_avant

    erreurs_du_webhook = []
    for enregistrement in caplog.records:
        if (
            enregistrement.name == "fedow_connect.views"
            and enregistrement.levelno >= logging.ERROR
        ):
            erreurs_du_webhook.append(enregistrement)
    assert len(erreurs_du_webhook) >= 1
