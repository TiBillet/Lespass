"""
Gateway Stripe dediee a la recharge FED V2.
Stripe gateway dedicated to V2 FED refill.

LOCALISATION : PaiementStripe/refill_federation.py

Difference avec `CreationPaiementStripe` (views.py) :
- Pas de Stripe Connect : paiement sur le compte central root (tresorerie federee)
- Pas de SEPA : UX recharge immediate uniquement (CB uniquement)
- Pas de subscription : recharge one-shot
- Metadata dediee (refill_type='FED') pour le dispatch webhook

Contrat PSP : voir `fedow_core/PSP_INTERFACE.md`.

/ Differences vs CreationPaiementStripe:
- No Stripe Connect: payment on the central root account (federated treasury)
- No SEPA: immediate refill UX only (card only)
- No subscription: one-shot refill
- Dedicated metadata (refill_type='FED') for webhook dispatch.
"""

import json
import logging

import stripe
from django.http import HttpResponseRedirect

from BaseBillet.models import LigneArticle, Paiement_stripe
from root_billet.models import RootConfiguration


logger = logging.getLogger(__name__)


class CreationPaiementStripeFederation:
    """
    Classe de creation d'un paiement Stripe pour la recharge FED V2.
    Creates a Stripe payment for V2 FED refill.

    Responsabilites :
    1. Cree le `Paiement_stripe(source=CASHLESS_REFILL)` en base
    2. Lie la `LigneArticle` au `Paiement_stripe`
    3. Construit la metadata Stripe (refill_type='FED', tenant, paiement_uuid, etc.)
    4. Appelle `stripe.checkout.Session.create()` SANS `stripe_account` (compte central)
    5. Interdit SEPA : `payment_method_types=['card']` uniquement
    6. Persiste `checkout_session_id_stripe` + `checkout_session_url`

    Usage :
        with tenant_context(tenant_federation):
            gateway = CreationPaiementStripeFederation(
                user=user,
                liste_ligne_article=[ligne],
                wallet_receiver=user.wallet,
                asset_fed=asset_fed,
                tenant_federation=tenant_federation,
                absolute_domain='https://lespass.example.com/my_account/',
                success_url='return_refill_wallet/',
            )
            return HttpResponseRedirect(gateway.checkout_session.url)
    """

    def __init__(
        self,
        user,
        liste_ligne_article,
        wallet_receiver,
        asset_fed,
        tenant_federation,
        absolute_domain: str,
        success_url: str = "return_refill_wallet/",
        cancel_url: str = "return_refill_wallet/",
    ):
        self.user = user
        self.liste_ligne_article = liste_ligne_article
        self.wallet_receiver = wallet_receiver
        self.asset_fed = asset_fed
        self.tenant_federation = tenant_federation
        self.absolute_domain = absolute_domain
        self.success_url = success_url
        self.cancel_url = cancel_url

        # Initialise la cle API Stripe root (compte central, pas de Connect).
        # / Initialize Stripe root API key (central account, no Connect).
        self.stripe_api_key = self._stripe_api_key()

        # Construit la metadata AVANT de creer le Paiement_stripe (dont l'uuid
        # sera ajoute apres creation).
        # / Build metadata BEFORE creating Paiement_stripe (uuid added after).
        self.metadata = self._build_metadata_base()

        # Cree le Paiement_stripe en base (source=CASHLESS_REFILL).
        # Met a jour la metadata avec le paiement_stripe_uuid puis repersiste
        # sur le Paiement_stripe pour que metadata_stripe en base soit cohérente
        # avec ce qui est envoyé à Stripe (audit trail).
        # / Create Paiement_stripe in DB (source=CASHLESS_REFILL).
        # Update metadata with paiement_stripe_uuid then persist again so that
        # stored metadata_stripe matches what was sent to Stripe (audit trail).
        self.paiement_stripe_db = self._send_paiement_stripe_in_db()
        self.metadata["paiement_stripe_uuid"] = f"{self.paiement_stripe_db.uuid}"
        self.paiement_stripe_db.metadata_stripe = json.dumps(self.metadata)
        self.paiement_stripe_db.save(update_fields=['metadata_stripe'])

        # Construit les line_items Stripe (via `pricesold.get_id_price_stripe`).
        # / Build Stripe line_items.
        self.line_items = self._set_stripe_line_items()

        # Cree la session Stripe (CB uniquement, pas de Connect).
        # / Create Stripe session (card only, no Connect).
        self.checkout_session = self._checkout_session()

    # ---------------------------------------------------------------------
    # Setup
    # ---------------------------------------------------------------------

    def _stripe_api_key(self):
        """
        Cle API Stripe root (compte central TiBillet, pas un compte Connect de lieu).
        / Root Stripe API key (central TiBillet account, not a venue Connect account).
        """
        api_key = RootConfiguration.get_solo().get_stripe_api()
        if not api_key:
            raise ValueError("No Stripe API key in RootConfiguration")
        stripe.api_key = api_key
        return stripe.api_key

    def _build_metadata_base(self):
        """
        Metadata PSP-agnostique selon PSP_INTERFACE.md.
        / PSP-agnostic metadata per PSP_INTERFACE.md.

        Cle `paiement_stripe_uuid` ajoutee apres la creation du Paiement_stripe.
        / Key `paiement_stripe_uuid` added after Paiement_stripe creation.
        """
        return {
            "tenant": f"{self.tenant_federation.uuid}",
            "refill_type": "FED",
            "wallet_receiver_uuid": f"{self.wallet_receiver.uuid}",
            "asset_uuid": f"{self.asset_fed.uuid}",
        }

    def _send_paiement_stripe_in_db(self):
        """
        Cree le Paiement_stripe avec source=CASHLESS_REFILL et lie les LigneArticle.
        / Creates Paiement_stripe with source=CASHLESS_REFILL and links LigneArticle.
        """
        paiement = Paiement_stripe.objects.create(
            user=self.user,
            metadata_stripe=json.dumps(self.metadata),
            source=Paiement_stripe.CASHLESS_REFILL,
            status=Paiement_stripe.PENDING,
        )

        for ligne in self.liste_ligne_article:
            ligne: LigneArticle
            ligne.paiement_stripe = paiement
            ligne.save()

        return paiement

    def _set_stripe_line_items(self):
        """
        Construit les `line_items` Stripe en mode `price_data` INLINE.
        / Builds Stripe line_items using INLINE `price_data` mode.

        On n'utilise PAS `ligne.pricesold.get_id_price_stripe()` qui creerait
        un Stripe Connect account pour le tenant `federation_fed` (via
        `Configuration.get_solo().get_stripe_connect_account()`). Ici on
        veut le compte central root, donc on envoie le prix directement
        dans `line_items` sans passer par un Price Stripe pre-cree.

        / We do NOT use `ligne.pricesold.get_id_price_stripe()` which would
        create a Stripe Connect account for the `federation_fed` tenant.
        We want the central root account, so we send the price directly
        in `line_items` without a pre-created Stripe Price.

        Reference Stripe :
        https://stripe.com/docs/api/checkout/sessions/create#create_checkout_session-line_items-price_data
        """
        line_items = []
        for ligne in self.liste_ligne_article:
            ligne: LigneArticle
            # amount en centimes (LigneArticle.amount est toujours en centimes)
            # / amount in cents (LigneArticle.amount is always in cents)
            amount_cents_unitaire = int(ligne.amount)
            line_items.append(
                {
                    "price_data": {
                        "currency": "eur",
                        "unit_amount": amount_cents_unitaire,
                        "product_data": {
                            "name": f"{ligne.pricesold.productsold.product.name}",
                        },
                    },
                    "quantity": int(ligne.qty),
                }
            )
        return line_items

    # ---------------------------------------------------------------------
    # Construction du checkout Stripe (sans Connect, sans SEPA)
    # ---------------------------------------------------------------------

    def dict_checkout_creator(self):
        """
        Dict passe a stripe.checkout.Session.create(). Volontairement minimal.
        / Dict passed to stripe.checkout.Session.create(). Intentionally minimal.

        Differences vs CreationPaiementStripe :
        - PAS de `stripe_account` (compte central)
        - PAS de `sepa_debit` (CB uniquement)
        - PAS de `invoice_creation` (pas de facture pour recharge)
        - Mode fige a 'payment' (one-shot)
        """
        success_url = (
            f"{self.absolute_domain}{self.paiement_stripe_db.uuid}/{self.success_url}"
        )
        cancel_url = (
            f"{self.absolute_domain}{self.paiement_stripe_db.uuid}/{self.cancel_url}"
        )

        data_checkout = {
            "success_url": f"{success_url}",
            "cancel_url": f"{cancel_url}",
            # CB uniquement : la recharge FED V2 exige une UX immediate,
            # pas de SEPA (qui prend 2-5 jours).
            # / Card only: V2 FED refill requires immediate UX, no SEPA.
            "payment_method_types": ["card"],
            "customer_email": f"{self.user.email}",
            "line_items": self.line_items,
            # One-shot (recharge, pas d'abonnement).
            # / One-shot (refill, not a subscription).
            "mode": "payment",
            "metadata": self.metadata,
            "client_reference_id": f"{self.user.pk}",
            # PAS de 'stripe_account' : le paiement arrive sur le compte central,
            # pas sur un compte Connect de lieu. Tresorerie federee unique.
            # / NO 'stripe_account': payment lands on central account,
            # not on a venue's Connect account. Single federated treasury.
        }
        return data_checkout

    def _checkout_session(self):
        """
        Cree la session Stripe et persiste les ids sur Paiement_stripe.
        / Creates the Stripe session and persists ids on Paiement_stripe.
        """
        data_checkout = self.dict_checkout_creator()
        checkout_session = stripe.checkout.Session.create(**data_checkout)

        logger.info(
            f"Recharge FED V2 : checkout Stripe cree "
            f"(paiement_uuid={self.paiement_stripe_db.uuid}, "
            f"session_id={checkout_session.id})"
        )

        self.paiement_stripe_db.payment_intent_id = checkout_session.payment_intent
        self.paiement_stripe_db.checkout_session_id_stripe = checkout_session.id
        self.paiement_stripe_db.checkout_session_url = checkout_session.url
        self.paiement_stripe_db.status = Paiement_stripe.PENDING
        self.paiement_stripe_db.save()

        return checkout_session

    # ---------------------------------------------------------------------
    # API publique
    # ---------------------------------------------------------------------

    def is_valid(self):
        """Retourne True si la session Stripe est prete a etre utilisee."""
        return bool(
            self.checkout_session
            and self.checkout_session.id
            and self.checkout_session.url
        )

    def redirect_to_stripe(self):
        """Helper pour rediriger l'user vers l'URL Stripe."""
        if self.checkout_session and self.checkout_session.url:
            return HttpResponseRedirect(self.checkout_session.url)
        return None
