"""
Backfill : passe en PAYMENT_PENDING les adhésions dont le mandat de paiement a
déjà été soumis (SEPA en cours) mais qui sont restées en ADMIN_VALID parce
qu'elles ont été créées AVANT le correctif « lien de paiement à usage unique ».

/ Backfill: move to PAYMENT_PENDING the memberships whose payment was already
submitted (SEPA in progress) but stayed ADMIN_VALID because they were created
BEFORE the "single-use payment link" fix.

Pourquoi : le correctif bascule les NOUVELLES soumissions via le webhook. Les
adhésions déjà en cours au moment du déploiement gardent un lien actif qui
pourrait recréer un checkout (donc un 2e prélèvement). Ce script les régularise.

Détection (deux niveaux) :
1. LOCAL (fiable, par défaut) : adhésion ADMIN_VALID + un paiement PENDING dont
   une ligne porte payment_method=STRIPE_SEPA_NOFED. Ce moyen de paiement n'est
   posé QUE par le webhook `checkout.session.completed`, donc sa présence prouve
   que le mandat a bien été soumis.
2. STRIPE (option --verify-stripe) : pour les adhésions ADMIN_VALID avec un
   paiement PENDING/OPEN mais sans moyen SEPA encore posé localement, on
   interroge Stripe. Si la session est `complete`, le mandat a été soumis.

Exemples / Usage :
    # Dry-run sur un tenant (n'écrit rien) :
    docker exec lespass_django poetry run python manage.py backfill_membership_payment_pending --schema lespass
    # Appliquer réellement :
    docker exec lespass_django poetry run python manage.py backfill_membership_payment_pending --schema lespass --apply
    # Confirmer en plus via l'API Stripe les cas douteux :
    docker exec lespass_django poetry run python manage.py backfill_membership_payment_pending --schema lespass --verify-stripe --apply
"""

import argparse
import logging

from django.core.management.base import BaseCommand
from django_tenants.utils import get_tenant_model, tenant_context

from Customers.models import Client

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Régularise les adhésions dont le mandat SEPA est déjà soumis mais "
        "restées en ADMIN_VALID (les passe en PAYMENT_PENDING)."
    )

    def add_arguments(self, parser):
        parser.formatter_class = argparse.RawTextHelpFormatter
        parser.add_argument(
            "--schema",
            type=str,
            default=None,
            help="Ne traiter qu'un tenant (schema_name). Par défaut : tous sauf ROOT.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Applique réellement les changements. Sans ce flag : dry-run (rien n'est écrit).",
        )
        parser.add_argument(
            "--verify-stripe",
            action="store_true",
            help="Interroge Stripe pour confirmer les cas sans moyen de paiement SEPA local.",
        )

    def handle(self, *args, **options):
        appliquer = options["apply"]
        verifier_stripe = options["verify_stripe"]
        schema_cible = options["schema"]

        # On exclut le schema ROOT : pas d'adhésion là-bas.
        # / Exclude the ROOT schema: no membership there.
        TenantModel = get_tenant_model()
        tenants = TenantModel.objects.exclude(categorie=Client.ROOT)
        if schema_cible:
            tenants = tenants.filter(schema_name=schema_cible)

        total = 0
        for tenant in tenants:
            with tenant_context(tenant):
                total += self._traiter_tenant(tenant, appliquer, verifier_stripe)

        mode = "APPLIQUÉ" if appliquer else "DRY-RUN (aucune modification écrite)"
        self.stdout.write(
            self.style.SUCCESS(f"[{mode}] {total} adhésion(s) concernée(s) au total.")
        )

    def _traiter_tenant(self, tenant, appliquer, verifier_stripe):
        """Traite un tenant et retourne le nombre d'adhésions concernées.
        / Process one tenant and return the number of affected memberships.
        """
        from BaseBillet.models import Membership, Paiement_stripe, PaymentMethod

        # 1. Candidates LOCALES : ADMIN_VALID + un paiement PENDING dont une ligne
        #    est en SEPA (preuve que le mandat a été soumis via le webhook).
        #    Les deux conditions portent sur le MÊME paiement (même jointure).
        # / Local candidates: ADMIN_VALID + a PENDING payment with a SEPA line.
        a_basculer = set(
            Membership.objects.filter(
                status=Membership.ADMIN_VALID,
                stripe_paiement__status=Paiement_stripe.PENDING,
                stripe_paiement__lignearticles__payment_method=PaymentMethod.STRIPE_SEPA_NOFED,
            ).distinct()
        )

        # 2. Option Stripe : confirmer les adhésions ADMIN_VALID avec un paiement
        #    PENDING/OPEN mais sans moyen SEPA encore posé localement.
        # / Stripe option: confirm ADMIN_VALID memberships with a pending payment
        #    but no SEPA payment_method set locally yet.
        if verifier_stripe:
            deja_vues = {m.pk for m in a_basculer}
            ambigues = (
                Membership.objects.filter(
                    status=Membership.ADMIN_VALID,
                    stripe_paiement__status__in=[Paiement_stripe.PENDING, Paiement_stripe.OPEN],
                    stripe_paiement__checkout_session_id_stripe__isnull=False,
                )
                .exclude(pk__in=deja_vues)
                .distinct()
            )
            for membership in ambigues:
                if self._mandat_soumis_sur_stripe(membership):
                    a_basculer.add(membership)

        # 3. Affichage (toujours) + application (si --apply).
        # / Print (always) + apply (if --apply).
        for membership in a_basculer:
            email = getattr(membership.user, "email", "—")
            self.stdout.write(
                f"  [{tenant.schema_name}] {membership.uuid} {email} : "
                f"ADMIN_VALID → PAYMENT_PENDING"
            )
            if appliquer:
                membership.status = Membership.PAYMENT_PENDING
                membership.save(update_fields=["status"])

        return len(a_basculer)

    def _mandat_soumis_sur_stripe(self, membership) -> bool:
        """Retourne True si une session Stripe de l'adhésion est `complete`
        (mandat soumis). En cas d'erreur API, retourne False (on ne bascule pas,
        par prudence).
        / Returns True if one Stripe session is `complete` (mandate submitted).
        On API error, returns False (do not move, by caution).
        """
        import stripe

        from BaseBillet.models import Paiement_stripe, Configuration
        from root_billet.models import RootConfiguration

        stripe.api_key = RootConfiguration.get_solo().get_stripe_api()
        compte_connect = Configuration.get_solo().get_stripe_connect_account()

        paiements = membership.stripe_paiement.filter(
            status__in=[Paiement_stripe.PENDING, Paiement_stripe.OPEN],
            checkout_session_id_stripe__isnull=False,
        )
        for paiement in paiements:
            try:
                session = stripe.checkout.Session.retrieve(
                    paiement.checkout_session_id_stripe,
                    stripe_account=compte_connect,
                )
                if session.status == "complete":
                    return True
            except Exception as e:
                logger.warning(
                    f"backfill_membership_payment_pending : erreur Stripe sur "
                    f"{paiement.checkout_session_id_stripe} : {e}"
                )
        return False
