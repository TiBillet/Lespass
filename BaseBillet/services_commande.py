"""
Orchestrateur de matérialisation d'un panier en objets DB.
/ Cart-to-DB materialization orchestrator.

Responsabilité unique : transformer un PanierSession en Commande + N Reservations
+ M Memberships + LigneArticle + éventuel Paiement_stripe. Le tout atomique.

/ Single responsibility: transform a PanierSession into Commande + N Reservations
+ M Memberships + LigneArticle + optional Paiement_stripe. Atomic.
"""
import logging
from decimal import Decimal

from django.db import connection, transaction
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class CommandeServiceError(Exception):
    """Erreur à la matérialisation.
    / Error during materialization."""


class CommandeService:
    """
    Service stateless qui matérialise un panier en DB.
    / Stateless service that materializes a cart to DB.
    """

    @staticmethod
    @transaction.atomic
    def materialiser(panier, user, first_name, last_name, email):
        """
        Transforme le panier en objets DB et retourne la Commande créée.

        Args:
            panier: PanierSession instance.
            user: TibilletUser (déjà résolu par email au niveau de la vue).
            first_name, last_name, email: infos acheteur.

        Returns:
            Commande: la commande créée avec son status (PENDING si Stripe
                nécessaire, PAID si commande gratuite).

        Raises:
            CommandeServiceError: si le panier est invalide ou vide.
            InvalidItemError (via re-validation): si un item du panier n'est
                plus valide au moment du checkout.

        / Transforms the cart into DB objects and returns the created Commande.
        """
        from BaseBillet.models import (
            Commande, LigneArticle, Membership, PaymentMethod, Price,
            Reservation, SaleOrigin,
        )
        from ApiBillet.serializers import dec_to_int, get_or_create_price_sold

        if panier.is_empty():
            raise CommandeServiceError(_("Cart is empty."))

        # Phase 0 : re-validation complète des items contre la DB.
        # Si stock épuisé, price dépublié, adhésion supprimée, etc. → InvalidItemError
        # qui remonte naturellement (atomic rollback → aucune écriture DB).
        # / Phase 0: full re-validation of items against DB.
        panier.revalidate_all()

        # -- Création de la Commande pivot (status=PENDING) --
        # -- Create the pivot Commande (status=PENDING) --
        promo_code = panier.promo_code()
        commande = Commande.objects.create(
            user=user,
            email_acheteur=email,
            first_name=first_name,
            last_name=last_name,
            status=Commande.PENDING,
            promo_code=promo_code,
        )

        all_lines = []
        total_centimes = 0

        # -- Phase 1 : Memberships en premier --
        # -- Phase 1: Memberships first --
        for item in panier.items():
            if item['type'] != 'membership':
                continue
            price = Price.objects.get(uuid=item['price_uuid'])
            amount_dec = CommandeService._resolve_amount(price, item)
            membership = Membership.objects.create(
                user=user,
                price=price,
                commande=commande,
                contribution_value=amount_dec,
                status=Membership.WAITING_PAYMENT,
                first_name=first_name,
                last_name=last_name,
                newsletter=False,
                custom_form=item.get('custom_form') or None,
            )
            if item.get('options'):
                from BaseBillet.models import OptionGenerale
                opts = OptionGenerale.objects.filter(
                    uuid__in=item['options']
                )
                if opts.exists():
                    membership.option_generale.set(opts)

            price_sold = get_or_create_price_sold(price, custom_amount=amount_dec)
            amount_cts = dec_to_int(amount_dec)
            line = LigneArticle.objects.create(
                pricesold=price_sold,
                membership=membership,
                payment_method=PaymentMethod.STRIPE_NOFED,
                amount=amount_cts,
                qty=1,
                sale_origin=SaleOrigin.LESPASS,
                promotional_code=(promo_code if promo_code and promo_code.product == price.product else None),
            )
            all_lines.append(line)
            total_centimes += amount_cts

        # -- Phase 2 : Reservations groupées par event_uuid --
        # -- Phase 2: Reservations grouped by event_uuid --
        from BaseBillet.models import Event
        tickets_par_event = {}
        for item in panier.items():
            if item['type'] != 'ticket':
                continue
            tickets_par_event.setdefault(item['event_uuid'], []).append(item)

        for event_uuid, items_event in tickets_par_event.items():
            event = Event.objects.get(uuid=event_uuid)
            # Construction d'un products_dict conforme au format attendu par TicketCreator
            # / Build a products_dict compatible with TicketCreator's expected format
            products_dict = {}
            custom_amounts = {}
            for it in items_event:
                price = Price.objects.get(uuid=it['price_uuid'])
                qty = int(it['qty'])
                products_dict.setdefault(price.product, {})
                products_dict[price.product][price] = products_dict[price.product].get(price, 0) + qty
                if it.get('custom_amount'):
                    custom_amounts[price.uuid] = Decimal(str(it['custom_amount']))

            # Tous les items de cet event partagent options + custom_form
            # (une seule soumission de booking_form.html par event).
            # / All items from this event share options + custom_form
            # (single submission of booking_form.html per event).
            first_item = items_event[0]
            custom_form = first_item.get('custom_form') or None
            options_uuids = first_item.get('options') or []

            reservation = Reservation.objects.create(
                user_commande=user,
                event=event,
                commande=commande,
                custom_form=custom_form,
                status=Reservation.CREATED,
            )
            if options_uuids:
                from BaseBillet.models import OptionGenerale
                opts = OptionGenerale.objects.filter(uuid__in=options_uuids)
                if opts.exists():
                    reservation.options.set(opts)

            # TicketCreator gère Tickets + LigneArticle. On bloque son Stripe.
            # / TicketCreator handles Tickets + LigneArticle. We disable its Stripe.
            from BaseBillet.validators import TicketCreator
            creator = TicketCreator(
                reservation=reservation,
                products_dict=products_dict,
                promo_code=promo_code,
                custom_amounts=custom_amounts,
                sale_origin=SaleOrigin.LESPASS,
                create_checkout=False,  # <-- clé : pas de Stripe ici
            )
            for line in creator.list_line_article_sold:
                all_lines.append(line)
                total_centimes += int(line.amount * line.qty)

        # -- Phase 3/4 : Stripe ou gratuit --
        # -- Phase 3/4: Stripe or free --
        if total_centimes > 0:
            CommandeService._creer_paiement_stripe(commande, user, all_lines)
            # Status reste PENDING — Stripe webhook basculera en PAID via signaux
        else:
            CommandeService._finaliser_gratuit(commande, all_lines)

        logger.info(
            f"CommandeService.materialiser OK : commande={commande.uuid_8()}, "
            f"lignes={len(all_lines)}, total_cts={total_centimes}, status={commande.status}"
        )
        return commande

    @staticmethod
    def _resolve_amount(price, item):
        """Calcule le montant Decimal à utiliser pour ce price + item.
        / Compute the Decimal amount to use for this price + item."""
        if price.free_price and item.get('custom_amount'):
            return Decimal(str(item['custom_amount']))
        return price.prix or Decimal("0.00")

    @staticmethod
    def _creer_paiement_stripe(commande, user, lignes):
        """Phase 3 — crée un Paiement_stripe consolidé pour toutes les lignes.
        / Phase 3 — create a consolidated Paiement_stripe for all lines."""
        from BaseBillet.models import LigneArticle, Paiement_stripe
        from PaiementStripe.views import CreationPaiementStripe

        tenant = connection.tenant
        metadata = {
            'tenant': f'{tenant.uuid}',
            'tenant_name': f'{tenant.name}',
            'commande_uuid': f'{commande.uuid}',
        }

        # Détection : y a-t-il des billets dans la commande ?
        # Si oui → SEPA refusé (billets à utiliser rapidement).
        # Si non (adhésion-only) → SEPA autorisé si config ON.
        # / Detection: does the order contain tickets?
        # If yes → deny SEPA (tickets must be usable quickly).
        # If no (adhesion-only) → allow SEPA if config ON.
        contains_tickets = any(
            line.reservation is not None for line in lignes
        )

        new_paiement = CreationPaiementStripe(
            user=user,
            liste_ligne_article=lignes,
            metadata=metadata,
            reservation=None,  # Pas de FK : le pivot est Commande
            source=Paiement_stripe.FRONT_BILLETTERIE,
            success_url="stripe_return/",
            cancel_url="stripe_return/",
            absolute_domain=f"https://{tenant.get_primary_domain()}/panier/",
            accept_sepa=(not contains_tickets),
        )
        if not new_paiement.is_valid():
            raise CommandeServiceError(_("Payment creation failed."))

        paiement = new_paiement.paiement_stripe_db
        paiement.lignearticles.all().update(status=LigneArticle.UNPAID)

        commande.paiement_stripe = paiement
        commande.save(update_fields=["paiement_stripe"])

    @staticmethod
    def _finaliser_gratuit(commande, lignes):
        """
        Phase 4 — commande gratuite (total 0€) : pas de Stripe, tout VALID direct.
        / Phase 4 — free order (total 0€): no Stripe, all VALID direct.
        """
        from django.utils import timezone
        from BaseBillet.models import Commande, LigneArticle, Membership, PaymentMethod, Reservation

        now = timezone.now()

        # Memberships de la commande → ONCE + deadline
        # / Commande's memberships → ONCE + deadline
        for membership in commande.memberships_commande.all():
            if not membership.first_contribution:
                membership.first_contribution = now
            membership.last_contribution = now
            membership.payment_method = PaymentMethod.FREE
            membership.status = Membership.ONCE
            membership.save()
            membership.set_deadline()

        # Reservations de la commande → FREERES/FREERES_USERACTIV selon user.is_active
        # / Commande's reservations → FREERES/FREERES_USERACTIV per user.is_active
        for reservation in commande.reservations.all():
            user = reservation.user_commande
            reservation.status = (
                Reservation.FREERES_USERACTIV if user.is_active else Reservation.FREERES
            )
            reservation.save()

        # LigneArticle → VALID + payment_method=FREE
        # / LigneArticle → VALID + payment_method=FREE
        for line in lignes:
            line.status = LigneArticle.VALID
            line.payment_method = PaymentMethod.FREE
            line.save(update_fields=["status", "payment_method"])

        commande.status = Commande.PAID
        commande.paid_at = now
        commande.save(update_fields=["status", "paid_at"])
