import json
import logging

import stripe
from django.contrib.auth import get_user_model
from django.db import connection
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from stripe._error import InvalidRequestError

from BaseBillet.models import Configuration, LigneArticle, Paiement_stripe, Reservation, Price, PriceSold, \
    PaymentMethod, SaleOrigin
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)
User = get_user_model()



"""
FR1420041010050500013M02606	L'état du PaymentIntent passe de processing à succeeded.
FR3020041010050500013M02609	L'état du PaymentIntent passe de processing à succeeded au bout d'au moins trois minutes.
FR8420041010050500013M02607	L'état du PaymentIntent passe de processing à requires_payment_method.
FR7920041010050500013M02600	L'état du PaymentIntent passe de processing à requires_payment_methodau bout d'au moins trois minutes.
FR5720041010050500013M02608	L'état du PaymentIntent passe de processing à succeeded, mais un litige est immédiatement créé.
FR9720041010050000000343434	Le paiement échoue avec un code d'erreur charge_exceeds_source_limit , car le montant du paiement entraîne un dépassement de la limite hebdomadaire de volume de paiement du compte.
FR5920041010050000000121212	Le paiement échoue avec un code d'erreur charge_exceeds_weekly_limit , car le montant du paiement dépasse la limite du volume de transactions du compte.
FR9720041010050000002222227	Échec du paiement avec un code d’échec insufficient_funds.
"""

class CreationPaiementStripe():

    def __init__(self,
                 user: User,
                 liste_ligne_article: list,
                 metadata: dict,
                 reservation: (Reservation, None),
                 source: str = None,
                 absolute_domain: (str, None) = None,
                 success_url: (str, None) = None,
                 cancel_url: (str, None) = None,
                 invoice=None,
                 ) -> None:

        # On va chercher les informations de configuration
        # et test si tout est ok pour créer un paiement
        self.user = user
        self.email_paiement = user.email
        self.invoice = invoice
        self.liste_ligne_article = liste_ligne_article
        self.reservation = reservation
        self.source = source

        self.metadata = metadata
        self.metadata_json = json.dumps(self.metadata)

        # Construction du retour :
        self.absolute_domain = absolute_domain
        self.success_url = success_url
        self.cancel_url = cancel_url

        # On instancie Stripe et entre en db le paiement en state Pending
        self.stripe_api_key = self._stripe_api_key()
        self.config = Configuration.get_solo()
        self.stripe_connect_account = self.config.get_stripe_connect_account()

        self.paiement_stripe_db = self._send_paiement_stripe_in_db()

        # Création des items prices et de l'instancee de paiement Stripe
        self.line_items = self._set_stripe_line_items()
        self.mode = self._mode()

        # S'il existe une facture de paiement récurrent.
        # La classe a été intanciée pour entrer en db le paiement.
        # Pas besoin de créer une nouvelle session
        self.checkout_session = None
        if not self.invoice:
            self.checkout_session = self._checkout_session()

    def _stripe_api_key(self):
        # La clé root comme clé par default pour tout paiement.
        api_key = RootConfiguration.get_solo().get_stripe_api()
        if not api_key:
            raise serializers.ValidationError(_(f"No Stripe Api Key in configuration"))
        stripe.api_key = api_key
        return stripe.api_key

    def _send_paiement_stripe_in_db(self):
        dict_paiement = {
            'user': self.user,
            'metadata_stripe': self.metadata_json,
            'reservation': self.reservation,
            'source': self.source,
            'status': Paiement_stripe.PENDING,
        }

        if self.invoice:
            dict_paiement['invoice_stripe'] = self.invoice.id
            if bool(self.invoice.parent.subscription_details.subscription):
                dict_paiement['subscription'] = self.invoice.parent.subscription_details.subscription

        paiementStripeDb = Paiement_stripe.objects.create(**dict_paiement)

        for ligne_article in self.liste_ligne_article:
            ligne_article: LigneArticle
            ligne_article.paiement_stripe = paiementStripeDb
            ligne_article.save()

        return paiementStripeDb

    def _set_stripe_line_items(self, force=False):
        """
        Retourne une liste de dictionnaire avec l'objet line_item de stripe et la quantitée à payer.

        :param force: Force la création de l'id Stripe
        :return:
        """
        line_items = []
        for ligne in self.liste_ligne_article:
            ligne: LigneArticle
            line_items.append(
                {
                    "price": f"{ligne.pricesold.get_id_price_stripe(force=force)}",
                    "quantity": int(ligne.qty),
                }
            )

        return line_items

    def _mode(self):
        """
        Mode Stripe payment ou subscription
        Si c'est une subscription avec une récurrence max, on le modifiera dans le retour stripe
        Le controleur pour la récurrence :
        :return: string
        """
        mode = 'payment'
        for ligne in self.liste_ligne_article:
            ligne : LigneArticle
            price = ligne.pricesold.price
            if price.recurring_payment:
                mode = 'subscription'
                break
        logger.info(f"Stripe payment method: {mode}")

        return mode

    def dict_checkout_creator(self):
        """
        Retourne un dict pour la création de la session de paiement
        https://stripe.com/docs/api/checkout/sessions/create
        :return: dict
        """
        success_url = f"{self.absolute_domain}{self.paiement_stripe_db.uuid}/{self.success_url}"
        cancel_url = f"{self.absolute_domain}{self.paiement_stripe_db.uuid}/{self.cancel_url}"

        payment_method_types = ["card",]
        if not self.reservation and self.config.stripe_accept_sepa:
            payment_method_types.append("sepa_debit")

        data_checkout = {
            'success_url': f'{success_url}',
            'cancel_url': f'{cancel_url}',
            'payment_method_types': payment_method_types,
            'customer_email': f'{self.user.email}',
            'line_items': self.line_items,
            'mode': self.mode,
            'metadata': self.metadata,
            'client_reference_id': f"{self.user.pk}",
            'stripe_account': f'{self.stripe_connect_account}',
        }

        if self.mode == 'payment' and self.config.stripe_invoice :
            data_checkout['invoice_creation'] = {"enabled": True,}
        return data_checkout

    def _checkout_session(self):

        data_checkout = self.dict_checkout_creator()
        try:
            checkout_session = stripe.checkout.Session.create(**data_checkout)
        except InvalidRequestError as e:
            logger.warning(f"InvalidRequestError on checkout session creation : {e}")

            # Si l'erreur concerne sepa_debit, on retire ce moyen de paiement et on reessaie
            # If the error is about sepa_debit, remove it and retry
            if 'sepa_debit' in str(e):
                logger.warning("SEPA debit rejected by Stripe, retrying without it")
                data_checkout['payment_method_types'] = ['card']
                # Desactiver le flag pour eviter les prochaines erreurs
                # Disable the flag to prevent future errors
                self.config.stripe_accept_sepa = False
                self.config.save(update_fields=['stripe_accept_sepa'])
                checkout_session = stripe.checkout.Session.create(**data_checkout)
            elif 'total amount due must add up' in str(e).lower() or 'minimum amount' in str(e).lower():
                # Le montant total est inférieur au minimum Stripe (€0.50).
                # Ne pas retenter — la validation en amont aurait dû bloquer ceci.
                raise serializers.ValidationError(str(e))
            elif 'account or business name' in str(e).lower():
                # Compte Stripe Connect du tenant mal configure : pas de nom commercial.
                # L'utilisateur final ne peut rien y faire. On loggue le tenant pour
                # que l'admin sache ou intervenir, et on renvoie un message generique.
                # / Tenant's Stripe Connect account is missing a business name.
                logger.error(
                    f"Stripe account misconfigured for tenant "
                    f"{connection.tenant.schema_name}: {e}"
                )
                raise serializers.ValidationError(
                    _("Online payment is temporarily unavailable. Please contact the site administrator.")
                )
            else:
                # L'id stripe d'un prix est mauvais.
                # Probablement du a un changement d'etat de test/prod.
                # On force la creation de nouvel ID en relancant la boucle self.line_items avec force=True
                self.line_items = self._set_stripe_line_items(force=True)
                data_checkout = self.dict_checkout_creator()
                checkout_session = stripe.checkout.Session.create(**data_checkout)

        logger.info(" ")
        logger.info("-" * 40)
        logger.info(f"Création d'un nouveau paiment stripe. Metadata : {self.metadata}")
        logger.info(f"checkout_session.id {checkout_session.id} payment_intent : {checkout_session.payment_intent}")
        logger.info("-" * 40)
        logger.info(" ")

        self.paiement_stripe_db.payment_intent_id = checkout_session.payment_intent
        self.paiement_stripe_db.checkout_session_id_stripe = checkout_session.id
        self.paiement_stripe_db.status = Paiement_stripe.PENDING
        self.paiement_stripe_db.save()

        return checkout_session

    def is_valid(self):
        if self.checkout_session:
            if self.checkout_session.id and \
                    self.checkout_session.url:
                return True

        # Pas besoin de checkout, c'est déja payé.
        if self.invoice:
            return True

        else:
            return False

    def redirect_to_stripe(self):
        if self.checkout_session:
            return HttpResponseRedirect(self.checkout_session.url)
        else:
            return None


def new_entry_from_stripe_subscription_invoice(user, id_invoice, membership):
    stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
    stripe_invoice = stripe.Invoice.retrieve(
        id_invoice,
        stripe_account=Configuration.get_solo().get_stripe_connect_account()
    )
    tenant = connection.tenant

    lines = stripe_invoice.lines
    lignes_articles = []

    from ApiBillet.serializers import get_or_create_price_sold
    for line in lines['data']:
        # id_price_stripe = line.pricing.price_details.price
        ligne_article = LigneArticle.objects.create(
            # pricesold=PriceSold.objects.get(id_price_stripe=id_price_stripe)
            pricesold=get_or_create_price_sold(membership.price, custom_amount=line.amount), #PriceSold.objects.get(id_price_stripe=id_price_stripe)
            payment_method=PaymentMethod.STRIPE_RECURENT,
            amount=line.amount,
            qty=line.quantity,
            membership=membership,
            sale_origin=SaleOrigin.WEBHOOK,
        )
        lignes_articles.append(ligne_article)
        logger.info(f"new_entry_from_stripe_subscription_invoice. ligne_article : {ligne_article.uuid} {ligne_article.payment_method}")
    # on reprend les même metadata que dans BaseBillet.validators.MembershipValidator.get_checkout_stripe
    metadata = {
        'tenant': f'{tenant.uuid}',
        'tenant_name': f'{tenant.name}',
        'price_uuid': f"{membership.price.uuid}",
        'product_price_name': f"{membership.price.product.name} {membership.price.name}",
        'membership_uuid': f"{membership.uuid}",
        'user': f"{user.email}",
        'from_stripe_invoice': f"{stripe_invoice.id}",
    }

    new_paiement_stripe = CreationPaiementStripe(
        user=user,
        liste_ligne_article=lignes_articles,
        metadata=metadata,
        reservation=None,
        source=Paiement_stripe.INVOICE,
        invoice=stripe_invoice,
        absolute_domain=None,
    )

    if new_paiement_stripe.is_valid():
        paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
        membership.stripe_paiement.add(paiement_stripe)
        # Passage à UNPAID pour lancer les triggers
        paiement_stripe.lignearticles.all().update(status=LigneArticle.UNPAID)

        return paiement_stripe


# ---------------------------------------------------------------------------
# Stripe Connect — onboarding pour tenant EXISTANT
# / Stripe Connect — onboarding for an EXISTING tenant
# ---------------------------------------------------------------------------
#
# Ces 2 vues geraient la connexion d'un compte Stripe Connect a un tenant
# DEJA cree, declenchee depuis l'admin Unfold (Configuration → Products →
# bouton "Creer et lier son compte Stripe" dans le CheckStripeComponent).
#
# Historique : ces methodes vivaient initialement dans
# `BaseBillet/views.py::Tenant.onboard_stripe_from_config` +
# `.onboard_stripe_return_from_config`. Le ViewSet `Tenant` melangeait
# 2 responsabilites disjointes : (1) creation de tenant via le legacy
# `/tenant/new/` (supprime lors de la session 2026-05-16 — remplace par
# l'app `onboard/`) et (2) onboarding Stripe Connect d'un tenant existant.
# Les 2 methodes (2) ont ete migrees ici, dans l'app dediee `PaiementStripe`,
# pour respecter la separation des responsabilites.
#
# Spec du chantier complet : `TECH_DOC/SESSIONS/MOYENS_PAIEMENT/01-stripe-migration-spec.md`.
#
# / These 2 views handled connecting a Stripe Connect account to an EXISTING
# tenant, triggered from the Unfold admin (Configuration → Products →
# "Create and link your Stripe account" button in CheckStripeComponent).
# Migrated here from `BaseBillet/views.py::Tenant` during the 2026-05-16
# session to separate concerns from the (now deleted) tenant creation flow.

from django.http import Http404
from django.shortcuts import redirect, render
from django_tenants.utils import schema_context  # noqa: F401  reserved for future use
from rest_framework import permissions, viewsets
from rest_framework.decorators import action


class StripeConnectOnboardingViewSet(viewsets.ViewSet):
    """
    Onboarding Stripe Connect pour un tenant existant (depuis l'admin Unfold).

    Pas d'onboarding initial (= creation de tenant) ici — celui-ci est dans
    l'app `onboard/`. Stripe Connect est demande PLUS TARD, au moment ou
    l'admin du tenant essaie de creer son premier produit payant. Choix
    UX volontaire : Stripe Connect demande des infos sensibles
    (IBAN, identite, justificatifs) qu'on ne veut pas demander dans le
    wizard d'onboarding initial.

    Routes :
      - `GET /stripe/onboard/from_config/` -> redirige vers une AccountLink
        Stripe ou l'utilisateur saisit ses infos.
      - `GET /stripe/onboard/return_from_config/<id_acc_connect>/` -> retour
        de Stripe, met a jour `Configuration.stripe_payouts_enabled`.

    / Stripe Connect onboarding for an EXISTING tenant (from the Unfold
    admin). Not the initial tenant creation — that's in `onboard/`. Stripe
    is intentionally deferred until the admin tries to create a paid product.
    """

    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=["GET"], url_path="onboard/from_config")
    def onboard_from_config(self, request):
        """
        GET `/stripe/onboard/from_config/` — initie l'onboarding Stripe.

        Cree ou recupere le compte Stripe Connect du tenant courant, forge
        une `stripe.AccountLink` (URL hosted Stripe) et redirige.

        En cas d'`InvalidRequestError` (compte Stripe expire / supprime cote
        Stripe), on vide `Configuration.stripe_connect_account` et on relance
        — `get_stripe_connect_account()` recreera un nouveau compte.

        / GET `/stripe/onboard/from_config/` — initiate Stripe onboarding.
        Creates/fetches the Stripe Connect account, builds an AccountLink,
        redirects. On InvalidRequestError (account expired/removed at
        Stripe), reset and retry.
        """
        config = Configuration.get_solo()
        id_acc_connect = config.get_stripe_connect_account()
        tenant = connection.tenant
        tenant_url = tenant.get_primary_domain().domain

        rootConf = RootConfiguration.get_solo()
        stripe.api_key = rootConf.get_stripe_api()

        # `return_url` et `refresh_url` pointent sur la NOUVELLE route
        # `/stripe/onboard/return_from_config/<id>/` (pas l'ancienne
        # `/tenant/<id>/onboard_stripe_return_from_config/`).
        # / return_url + refresh_url point to the NEW route.
        url_retour = (
            f"https://{tenant_url}/stripe/onboard/return_from_config/"
            f"{id_acc_connect}/"
        )

        try:
            account_link = stripe.AccountLink.create(
                account=id_acc_connect,
                refresh_url=url_retour,
                return_url=url_retour,
                type="account_onboarding",
            )
        except InvalidRequestError as exc_premiere_tentative:
            # WARNING niveau Sentry (breadcrumb) : c'est attendu si l'ID
            # stocke devient invalide, mais utile pour debug. Le `exc_info`
            # permet de voir le message Stripe complet en cas d'enquete.
            # / WARNING level for Sentry breadcrumb: expected when stored
            # ID becomes invalid, but useful for diagnosis.
            logger.warning(
                "Stripe onboard: AccountLink.create failed (first attempt), "
                "clearing stored ID and retrying. tenant=%s mode_test=%s "
                "id_acc_connect=%s error=%s",
                connection.schema_name, config.stripe_mode_test,
                id_acc_connect, exc_premiere_tentative,
            )
            # Compte Stripe invalide : l'ID stocke ne correspond pas a la
            # plateforme actuelle (compte supprime cote Stripe, ou compte
            # cree avec une autre cle API). On vide LE BON champ selon le
            # mode (test / prod), puis on relance — `get_stripe_connect_account`
            # creera un nouveau compte avec la cle API actuelle.
            #
            # PIEGE corrige 2026-05-16 : l'ancien code (legacy
            # `Tenant.onboard_stripe_from_config`) vidait TOUJOURS
            # `stripe_connect_account` (champ PROD) meme en mode test, du
            # coup `get_stripe_connect_account` continuait a renvoyer
            # l'ancien `stripe_connect_account_test` invalide → Stripe
            # re-rejetait. `Configuration` a 2 champs separes
            # (`stripe_connect_account` pour prod, `stripe_connect_account_test`
            # pour test) — il faut vider le bon selon `stripe_mode_test`.
            #
            # / Stripe account invalid: clear the RIGHT field based on mode
            # (test vs prod), then retry. The legacy code always cleared
            # the PROD field even in test mode, causing infinite "account
            # not connected" errors in test mode.
            if config.stripe_mode_test:
                config.stripe_connect_account_test = None
            else:
                config.stripe_connect_account = None
            config.save()
            id_acc_connect = config.get_stripe_connect_account()
            url_retour = (
                f"https://{tenant_url}/stripe/onboard/return_from_config/"
                f"{id_acc_connect}/"
            )
            account_link = stripe.AccountLink.create(
                account=id_acc_connect,
                refresh_url=url_retour,
                return_url=url_retour,
                type="account_onboarding",
            )

        return redirect(account_link.get("url"))

    @action(
        detail=False,
        methods=["GET"],
        url_path=r"onboard/return_from_config/(?P<id_acc_connect>[^/.]+)",
    )
    def onboard_return_from_config(self, request, id_acc_connect=None):
        """
        GET `/stripe/onboard/return_from_config/<id_acc_connect>/` —
        retour de Stripe apres l'onboarding hosted page.

        Verifie `details_submitted` ET `payouts_enabled` via l'API Stripe,
        puis met a jour `Configuration.stripe_payouts_enabled` pour debloquer
        la creation de produits payants cote admin.

        / GET return URL from Stripe onboarding. Checks `details_submitted`
        and `payouts_enabled` via Stripe API, then updates
        `Configuration.stripe_payouts_enabled`.
        """
        details_submitted = False

        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        try:
            info_stripe = stripe.Account.retrieve(id_acc_connect)
            details_submitted = info_stripe.details_submitted
        except Exception as e:
            logger.error(
                "stripe_onboard_return: id_acc_connect=%s erreur stripe: %s",
                id_acc_connect, e,
            )
            raise Http404

        config = Configuration.get_solo()
        if info_stripe and info_stripe.get("payouts_enabled"):
            config.stripe_payouts_enabled = info_stripe.get("payouts_enabled")
            config.save()

        # Choix du base template selon HTMX (cf. pattern projet).
        # / Choose base template depending on HTMX request type.
        from BaseBillet.views import get_context

        context = get_context(request)
        context["details_submitted"] = details_submitted
        return render(
            request,
            "paiementstripe/after_onboard_stripe.html",
            context=context,
        )

