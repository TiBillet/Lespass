"""
tests/pytest/test_kiosk_credit.py — Credit de la carte apres un paiement a la borne.
/ Card credit after a kiosk payment.

LOCALISATION : tests/pytest/test_kiosk_credit.py

Ce qui est teste (kiosk/credit.py, kiosk/models.py, kiosk/carte.py) :
1. Un paiement reussi credite la carte dans la base locale (fedow_core),
   comme a la caisse : jeton, transaction, ligne de vente.
2. Le credit n'a lieu qu'UNE fois, meme appele deux fois.
3. Un paiement pas reussi, ou sans carte, ne credite rien.
4. get_from_stripe credite la carte quand Stripe repond « succeeded ».
5. Le solde affiche par la borne additionne Fedow distant + base locale.

Aucun appel reseau : la carte a un portefeuille « ephemere » local (pas de
Fedow a interroger), Stripe et Fedow sont mockes.
/ No network call: the card has a local ephemeral wallet; Stripe and Fedow
are mocked.
"""

import uuid as uuid_module
from unittest.mock import MagicMock, patch

import pytest
from django.db.models import Q
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from BaseBillet.models import LigneArticle, PaymentMethod
from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import WalletService
from kiosk.credit import crediter_la_carte_du_paiement, trouver_le_produit_de_recharge_de_la_borne
from kiosk.models import PaymentsIntent
from laboutik.models import Terminal

PREFIXE = "[kiosk_credit_test]"
TAG_CARTE = "KCR00001"
NOM_BORNE = "TEST_CREDIT_Borne"


@pytest.fixture
def tenant():
    return Client.objects.get(schema_name="lespass")


@pytest.fixture
def produit_de_recharge(tenant):
    """
    Le produit « Recharge euros » que la borne utilise. Si le lieu n'a pas de
    monnaie locale, on en cree une de test (le signal fedow_core cree le produit).
    / The top-up product the kiosk uses; create a test currency if none.
    """
    asset_de_test = None
    with tenant_context(tenant):
        produit, tarif_libre = trouver_le_produit_de_recharge_de_la_borne()
        if tarif_libre is None:
            wallet_du_lieu, _created = Wallet.objects.get_or_create(name=f"{PREFIXE} Lieu")
            asset_de_test, _created = Asset.objects.get_or_create(
                name=f"{PREFIXE} Locale",
                category=Asset.TLF,
                defaults={
                    "currency_code": "EUR",
                    "wallet_origin": wallet_du_lieu,
                    "tenant_origin": tenant,
                },
            )
            asset_de_test.archive = False
            asset_de_test.active = True
            asset_de_test.save()
            produit, tarif_libre = trouver_le_produit_de_recharge_de_la_borne()

    yield produit

    # La monnaie de test ne doit pas rester visible dans la vraie caisse.
    # / The test currency must not stay visible in the real POS.
    if asset_de_test is not None:
        with tenant_context(tenant):
            asset_de_test.archive = True
            asset_de_test.active = False
            asset_de_test.save()


@pytest.fixture
def carte_et_borne(tenant):
    """Une carte anonyme (portefeuille local vide) et une borne.
    Nettoie avant ET apres. / An anonymous card with an empty local wallet, and
    a kiosk. Cleans up before AND after."""

    def _nettoyer():
        with tenant_context(tenant):
            cartes = CarteCashless.objects.filter(tag_id=TAG_CARTE)
            wallets = Wallet.objects.filter(name=f"{PREFIXE} Wallet carte")
            PaymentsIntent.objects.filter(terminal__name=NOM_BORNE).delete()
            LigneArticle.objects.filter(carte__in=cartes).delete()
            Transaction.objects.filter(
                Q(card__in=cartes) | Q(receiver__in=wallets) | Q(sender__in=wallets)
            ).delete()
            Token.objects.filter(wallet__in=wallets).delete()
            cartes.delete()
            wallets.delete()
            Terminal.objects.filter(name=NOM_BORNE).delete()

    _nettoyer()
    with tenant_context(tenant):
        detail, _created = Detail.objects.get_or_create(
            base_url=f"{PREFIXE}_DETAIL",
            origine=tenant,
            defaults={"generation": 0},
        )
        wallet_de_la_carte = Wallet.objects.create(name=f"{PREFIXE} Wallet carte")
        carte = CarteCashless.objects.create(
            tag_id=TAG_CARTE,
            number=TAG_CARTE,
            uuid=uuid_module.uuid4(),
            detail=detail,
            wallet_ephemere=wallet_de_la_carte,
        )
        borne = Terminal.objects.create(name=NOM_BORNE)

    yield carte, borne
    _nettoyer()


def _paiement(borne, carte, statut=PaymentsIntent.SUCCEEDED, montant=1500):
    return PaymentsIntent.objects.create(
        terminal=borne,
        card=carte,
        amount=montant,
        status=statut,
        payment_intent_stripe_id="pi_test_kiosk_credit",
    )


@pytest.mark.django_db
def test_paiement_reussi_credite_la_carte_en_monnaie_locale(tenant, produit_de_recharge, carte_et_borne):
    """Un paiement reussi credite le montant sur la monnaie locale de la carte,
    et cree une ligne de vente « carte bancaire », comme a la caisse.
    / A successful payment credits the local currency and creates a CC sale line."""
    carte, borne = carte_et_borne
    with tenant_context(tenant):
        paiement = _paiement(borne, carte)

        credit_fait = crediter_la_carte_du_paiement(paiement.pk)

        assert credit_fait is True
        solde = WalletService.obtenir_solde(carte.wallet_ephemere, produit_de_recharge.asset)
        assert solde == 1500

        paiement.refresh_from_db()
        assert paiement.carte_creditee_le is not None

        lignes = LigneArticle.objects.filter(carte=carte)
        assert lignes.count() == 1
        assert lignes.first().amount == 1500
        assert lignes.first().payment_method == PaymentMethod.CC


@pytest.mark.django_db
def test_le_credit_n_a_lieu_qu_une_seule_fois(tenant, produit_de_recharge, carte_et_borne):
    """Appele deux fois (tache Celery + sondage de secours), le credit n'a lieu
    qu'une fois. / Called twice, the credit happens once."""
    carte, borne = carte_et_borne
    with tenant_context(tenant):
        paiement = _paiement(borne, carte)

        premier_appel = crediter_la_carte_du_paiement(paiement.pk)
        deuxieme_appel = crediter_la_carte_du_paiement(paiement.pk)

        assert premier_appel is True
        assert deuxieme_appel is False
        solde = WalletService.obtenir_solde(carte.wallet_ephemere, produit_de_recharge.asset)
        assert solde == 1500
        assert LigneArticle.objects.filter(carte=carte).count() == 1


@pytest.mark.django_db
def test_paiement_pas_reussi_ne_credite_rien(tenant, produit_de_recharge, carte_et_borne):
    """Un paiement encore en cours ne credite pas la carte.
    / A payment still in progress does not credit the card."""
    carte, borne = carte_et_borne
    with tenant_context(tenant):
        paiement = _paiement(borne, carte, statut=PaymentsIntent.IN_PROGRESS)

        credit_fait = crediter_la_carte_du_paiement(paiement.pk)

        assert credit_fait is False
        paiement.refresh_from_db()
        assert paiement.carte_creditee_le is None
        assert not Token.objects.filter(wallet=carte.wallet_ephemere, value__gt=0).exists()


@pytest.mark.django_db
def test_paiement_sans_carte_ne_credite_rien(tenant, produit_de_recharge, carte_et_borne):
    """Sans carte, rien a crediter (et pas d'exception).
    / No card: nothing to credit, no exception."""
    _carte, borne = carte_et_borne
    with tenant_context(tenant):
        paiement = _paiement(borne, None)

        assert crediter_la_carte_du_paiement(paiement.pk) is False
        paiement.refresh_from_db()
        assert paiement.carte_creditee_le is None


@pytest.mark.django_db
def test_get_from_stripe_credite_la_carte_quand_stripe_dit_reussi(tenant, produit_de_recharge, carte_et_borne):
    """Quand Stripe repond « succeeded », get_from_stripe passe le paiement en
    succes ET credite la carte. C'est le chemin de la tache Celery et du sondage.
    / When Stripe says "succeeded", get_from_stripe marks success AND credits."""
    carte, borne = carte_et_borne
    with tenant_context(tenant):
        paiement = _paiement(borne, carte, statut=PaymentsIntent.IN_PROGRESS)

        reponse_stripe = MagicMock(status="succeeded")
        with patch("root_billet.models.RootConfiguration.get_stripe_api", return_value="sk_test_fake"), \
             patch("stripe.PaymentIntent.retrieve", return_value=reponse_stripe):
            statut = paiement.get_from_stripe()

        assert statut == PaymentsIntent.SUCCEEDED
        assert paiement.carte_creditee_le is not None
        solde = WalletService.obtenir_solde(carte.wallet_ephemere, produit_de_recharge.asset)
        assert solde == 1500


@pytest.mark.django_db
def test_une_copie_perimee_ne_provoque_pas_de_double_credit(tenant, produit_de_recharge, carte_et_borne):
    """La tache Celery garde en memoire une copie du paiement chargee AVANT le
    credit. Quand elle voit le succes a son tour, elle ne doit pas recrediter.
    / The Celery task holds a copy loaded BEFORE the credit: it must not
    credit again when it sees the success too."""
    carte, borne = carte_et_borne
    with tenant_context(tenant):
        paiement = _paiement(borne, carte, statut=PaymentsIntent.IN_PROGRESS)
        copie_perimee = PaymentsIntent.objects.get(pk=paiement.pk)

        reponse_stripe = MagicMock(status="succeeded")
        with patch("root_billet.models.RootConfiguration.get_stripe_api", return_value="sk_test_fake"), \
             patch("stripe.PaymentIntent.retrieve", return_value=reponse_stripe):
            paiement.get_from_stripe()
            copie_perimee.get_from_stripe()

        solde = WalletService.obtenir_solde(carte.wallet_ephemere, produit_de_recharge.asset)
        assert solde == 1500
        assert LigneArticle.objects.filter(carte=carte).count() == 1


@pytest.mark.django_db
def test_le_solde_de_la_borne_additionne_fedow_et_la_base_locale(tenant, produit_de_recharge, carte_et_borne):
    """Le solde affiche = jetons en euros du Fedow distant + jetons locaux.
    / Displayed balance = remote Fedow euro tokens + local tokens."""
    from kiosk.carte import lire_la_carte_pour_la_borne

    carte, borne = carte_et_borne
    with tenant_context(tenant):
        paiement = _paiement(borne, carte)
        crediter_la_carte_du_paiement(paiement.pk)

        reponse_fedow = {
            "number_printed": TAG_CARTE,
            "is_wallet_ephemere": True,
            "wallet": {
                "uuid": str(carte.wallet_ephemere.uuid),
                "tokens": [{"asset_category": "FED", "value": 450}],
            },
        }
        with patch("kiosk.carte.FedowAPI") as faux_fedow:
            faux_fedow.return_value.NFCcard.retrieve.return_value = reponse_fedow
            carte_lue = lire_la_carte_pour_la_borne(TAG_CARTE)

    # 450 (FED distant) + 1500 (monnaie locale creditee) / remote FED + local
    assert carte_lue["solde_centimes"] == 1950
