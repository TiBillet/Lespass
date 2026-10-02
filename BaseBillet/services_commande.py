"""
Orchestrateur de matérialisation d'un panier en objets DB.
/ Cart-to-DB materialization orchestrator.

Responsabilité unique : transformer un PanierSession en Commande + N Reservations
+ M Memberships + LigneArticle + éventuel Paiement_stripe. Le tout atomique.
Toute la commande est UNE vente (BaseBillet/models_vente.py) : un paiement Stripe = une
vente (R5). Les lignes de vente sont les articles de cette vente.

/ Single responsibility: transform a PanierSession into Commande + N Reservations
+ M Memberships + LigneArticle + optional Paiement_stripe. Atomic.
The whole order is ONE sale; the sale lines are its items.
"""
from datetime import datetime
import logging
from decimal import Decimal, InvalidOperation

from django.db import connection, transaction
from django.utils.translation import gettext_lazy as _

from BaseBillet.models import Membership, Price
from BaseBillet.models_vente import Vente
from BaseBillet.services_panier import InvalidItemError
from BaseBillet.services_vente import ajouter_article, annuler_vente, encaisser_vente, ouvrir_vente
from booking.models import Resource, Booking
from laboutik.views import _taux_tva_de_la_ligne_de_caisse

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
            OU
            Errors : si le panier.revalidate_all() a échoué, retourne la liste des erreurs

            Et retourne un flag (bool) indiquant si la materialisation à réussi ou non

        Raises:
            CommandeServiceError: si le panier est invalide ou vide.
            InvalidItemError (via re-validation): si un item du panier n'est
                plus valide au moment du checkout.

        / Transforms the cart into DB objects and returns the created Commande.
        """

        # On utilise explicitement un context manager transaction.atomic() plutôt
        # que le décorateur, afin de pouvoir activer l'isolation SERIALIZABLE sur
        # la transaction extérieure. `validate_new_booking` est ensuite appelé
        # à l'intérieur de cette transaction et hérite de l'isolation SERIALIZABLE
        # de PostgreSQL, ce qui protège les créneaux de ressources contre les
        # sur-réservations concurrentes (lecture de la capacité + insertion de
        # Booking atomisées par SSI).
        # / We use an explicit transaction.atomic() context manager rather than the
        # decorator so we can enable SERIALIZABLE isolation on the outer transaction.
        # validate_new_booking is then called inside this transaction and inherits
        # the SERIALIZABLE isolation, protecting resource slots from concurrent
        # overbooking (capacity reads + Booking inserts are atomic under SSI).
        already_in_transaction = connection.in_atomic_block

        with transaction.atomic():
            if not already_in_transaction:
                connection.cursor().execute(
                    'SET TRANSACTION ISOLATION LEVEL SERIALIZABLE'
                )

            from BaseBillet.models import (
                Commande, Membership, PaymentMethod, Price,
                Reservation, SaleOrigin,
            )
            from ApiBillet.serializers import dec_to_int, get_or_create_price_sold

            if panier.is_empty():
                raise CommandeServiceError(_("Cart is empty."))

            # Phase 0 : re-validation complète des items contre la DB.
            # Si stock épuisé, price dépublié, adhésion supprimée, etc. → InvalidItemError
            # qui remonte naturellement (atomic rollback → aucune écriture DB).
            # / Phase 0: full re-validation of items against DB.
            errors = panier.revalidate_all()
            if len(errors) > 0:
                return errors, False

            # Resolution des prenom/nom finaux pour la Commande pivot :
            # - priorite aux valeurs stockees sur le premier item membership qui en a
            #   (collectees par membership/form.html),
            # - sinon fallback sur les args de la fonction (user.first_name).
            # Ainsi un utilisateur sans profil renseigne obtient une Commande
            # avec de vrais prenom/nom des que le panier contient une adhesion.
            # / Resolve final first/last name for the Commande pivot:
            # - prioritize the first membership item with names (from the form),
            # - fallback to function args (user.first_name) otherwise.
            # Ensures users without a filled profile still get proper names.
            buyer_firstname = first_name
            buyer_lastname = last_name
            for item in panier.items():
                if item.get('type') != 'membership':
                    continue
                item_fn = (item.get('firstname') or '').strip()
                item_ln = (item.get('lastname') or '').strip()
                if item_fn and item_ln:
                    buyer_firstname = item_fn
                    buyer_lastname = item_ln
                    break

            # Resolution des promo codes : chaque item porte son propre
            # `promotional_code_name` (stocke par PanierSession.add_* apres
            # validation stricte : actif, is_usable, lie au product du price).
            # Helper qui transforme le nom en instance PromotionalCode, ou None.
            # On charge en batch les codes necessaires pour limiter les queries.
            # / Per-item promo codes: each item carries `promotional_code_name`
            # (server-validated at add time). Helper maps name→instance. Batch load.
            from BaseBillet.models import PromotionalCode
            needed_names = {
                item.get('promotional_code_name')
                for item in panier.items()
                if item.get('promotional_code_name')
            }
            promo_by_name = {
                p.name: p
                for p in PromotionalCode.objects.filter(name__in=needed_names)
            } if needed_names else {}

            def _resolve_promo(item):
                name = item.get('promotional_code_name')
                return promo_by_name.get(name) if name else None

            # -- Création de la Commande pivot (status=PENDING) --
            # Le Commande.promo_code pivot prend le premier code rencontre (il
            # est purement informatif — l'application se fait ligne par ligne).
            # / The Commande.promo_code pivot takes the first code found (purely
            # informative — actual application is done line-by-line).
            pivot_promo_code = None
            for item in panier.items():
                pivot_promo_code = _resolve_promo(item)
                if pivot_promo_code:
                    break

            # La vente de toute la commande : UNE vente pour un paiement (R5). Elle est
            # ouverte ici, avec la Commande et dans la même transaction, puis passée à
            # chaque producteur (adhésions, TicketCreator, validate_new_booking), qui y
            # écrit ses lignes. Elle reste EN_ATTENTE : elle est encaissée quand le
            # paiement est confirmé. Une commande gratuite l'encaisse à 0 dans
            # `_finaliser_gratuit`, après le passage de ses lignes.
            # / The whole order's sale: ONE sale per payment. Opened here with the Order,
            # passed to every producer. It stays PENDING until the payment is confirmed;
            # a free order settles it at 0 in `_finaliser_gratuit`.
            vente = ouvrir_vente(
                origine=SaleOrigin.LESPASS,
                nature=Vente.Nature.VENTE,
                client=user,
            )

            commande = Commande.objects.create(
                user=user,
                email_acheteur=email,
                first_name=buyer_firstname,
                last_name=buyer_lastname,
                status=Commande.PENDING,
                promo_code=pivot_promo_code,
                vente=vente,
            )

            all_lines = []

            # Le total de la commande (décision Stripe ou gratuit, garde des 0,50 €) est
            # la somme des totaux catalogue de ses articles : le montant écrit dans la
            # vente, jamais recalculé à côté.
            # / The order total is the sum of its items' catalogue totals.
            total_centimes = 0

            # -- Phase 1 : Memberships en premier --
            # -- Phase 1: Memberships first --
            for item in panier.items():
                if item['type'] != 'membership':
                    continue
                price = Price.objects.get(uuid=item['price_uuid'])
                amount_dec = CommandeService._resolve_amount(price, item)

                # Code promo de cet item specifiquement (pas du panier global).
                # / Promo code for this specific item (not cart-global).
                item_promo_code = _resolve_promo(item)

                # Prenom/nom : priorite aux valeurs de l'item (collectees par
                # membership/form.html), puis fallback sur les args de la fonction
                # (issus de user.first_name / user.last_name).
                # / First/last name: prioritize item values (collected by the
                # membership form), fallback to function args (user.first_name).
                item_firstname = (item.get('firstname') or '').strip()
                item_lastname = (item.get('lastname') or '').strip()
                resolved_firstname = item_firstname or first_name
                resolved_lastname = item_lastname or last_name

                membership = Membership.objects.create(
                    user=user,
                    price=price,
                    commande=commande,
                    contribution_value=amount_dec,
                    status=Membership.WAITING_PAYMENT,
                    first_name=resolved_firstname,
                    last_name=resolved_lastname,
                    newsletter=item.get('newsletter', False),
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
                # Le code n'est applique que si lie au product (double-check
                # redondant avec la validation a l'ajout, mais safe).
                # / Code applied only if linked to the product (redundant safety check).
                applicable_promo = item_promo_code if (
                    item_promo_code and item_promo_code.product_id == price.product_id
                ) else None
                # La ligne de l'adhésion, écrite par le service de vente dans la vente de
                # la commande : montants entiers et TVA (celle du produit, sinon celle du
                # lieu). Même règle de TVA que la caisse et les producteurs en ligne.
                # / The membership line, written by the sale service into the order's sale.
                # Same VAT rule as the register and the online producers.
                line = ajouter_article(
                    vente,
                    pricesold=price_sold,
                    quantite=1,
                    prix_unitaire=amount_cts,
                    taux_tva=_taux_tva_de_la_ligne_de_caisse(
                        price.product, PaymentMethod.STRIPE_NOFED
                    ),
                    membership=membership,
                    payment_method=PaymentMethod.STRIPE_NOFED,
                    sale_origin=SaleOrigin.LESPASS,
                    promotional_code=applicable_promo,
                )

                all_lines.append(line)
                total_centimes += line.total_catalogue

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
                # Construction des products_dict attendus par TicketCreator, pour les items a
                # prix fixe. Ils sont regroupes par code promo : TicketCreator n'accepte qu'un
                # code, et deux ajouts successifs sur le meme evenement peuvent porter deux
                # codes (lies a deux produits differents). Dans un groupe, les quantites d'un
                # meme tarif s'additionnent.
                # Un montant saisi ne vaut que si le tarif est ENCORE a prix libre : sinon
                # (tarif passe en prix fixe depuis l'ajout), le billet est facture au prix fixe.
                # / Build TicketCreator products_dicts for fixed-price items, grouped by promo
                # code (TicketCreator takes one code). A typed amount only counts if the price
                # is still a free price.
                products_dict_par_code_promo = {}
                items_a_prix_libre = []
                for it in items_event:
                    price = Price.objects.get(uuid=it['price_uuid'])
                    if it.get('custom_amount') and price.free_price:
                        items_a_prix_libre.append(it)
                        continue
                    qty = int(it['qty'])
                    nom_du_code_promo = it.get('promotional_code_name') or None
                    products_dict = products_dict_par_code_promo.setdefault(nom_du_code_promo, {})
                    products_dict.setdefault(price.product, {})
                    products_dict[price.product][price] = products_dict[price.product].get(price, 0) + qty

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

                # TicketCreator gère Tickets + LigneArticle, un appel par code promo. On bloque
                # son Stripe : CommandeService crée UN paiement pour toute la Commande.
                # Il n'applique le code qu'aux tarifs de SON produit (method_B).
                # Il reçoit la vente de la commande : ses lignes en sont les articles.
                # / TicketCreator handles Tickets + LigneArticle, one call per promo code, with
                # its Stripe disabled. It applies the code only to its own product's prices.
                # It receives the order's sale: its lines are the sale's items.
                from BaseBillet.validators import TicketCreator
                for nom_du_code_promo, products_dict in products_dict_par_code_promo.items():
                    creator = TicketCreator(
                        reservation=reservation,
                        products_dict=products_dict,
                        promo_code=_resolve_promo({'promotional_code_name': nom_du_code_promo}),
                        sale_origin=SaleOrigin.LESPASS,
                        create_checkout=False,
                        vente=vente,
                    )
                    for line in creator.list_line_article_sold:
                        all_lines.append(line)
                        total_centimes += line.total_catalogue

                # Un item a prix libre garde SON montant : il passe dans son propre
                # TicketCreator, sur la meme reservation. Additionner ses quantites avec un
                # autre item du meme tarif facturerait les deux au dernier montant saisi.
                # / A free-price item keeps ITS amount: it gets its own TicketCreator, on the
                # same reservation. Merging it with another item of the same price would bill
                # both at the last amount typed.
                for item_a_prix_libre in items_a_prix_libre:
                    price = Price.objects.get(uuid=item_a_prix_libre['price_uuid'])
                    montant_saisi = Decimal(str(item_a_prix_libre['custom_amount']))
                    creator = TicketCreator(
                        reservation=reservation,
                        products_dict={price.product: {price: int(item_a_prix_libre['qty'])}},
                        promo_code=_resolve_promo(item_a_prix_libre),
                        custom_amounts={price.uuid: montant_saisi},
                        sale_origin=SaleOrigin.LESPASS,
                        create_checkout=False,
                        vente=vente,
                    )
                    for line in creator.list_line_article_sold:
                        all_lines.append(line)
                        total_centimes += line.total_catalogue

            # -- Phase 3 : Reservation de resource -- #
            # -- Phase 3 : Reservation de resource -- #
            from booking.models import Resource
            from booking.booking_engine import validate_new_booking
            tickets_par_event = {}
            for item in panier.items():
                if item['type'] != 'resource':
                    continue

                price = Price.objects.get(uuid=item['price_uuid'])

                # Prénom/nom : priorité aux valeurs de l'item (collectées par le formulaire de
                # réservation), puis repli sur les arguments de la fonction
                # (`user.first_name` / `user.last_name`).
                # / First/last name: item values first (from the booking form), then the
                # function arguments.
                item_firstname = (item.get('firstname') or '').strip()
                item_lastname = (item.get('lastname') or '').strip()

                resolved_firstname = item_firstname or first_name
                resolved_lastname = item_lastname or last_name

                resource = Resource.objects.get(pk=item.get('resource_uuid'))

                # Montant saisi pour un tarif à prix libre. Un tarif fixe n'en a pas.
                # La chaîne "None" est traitée comme une absence de montant : une session vit
                # 12 semaines et d'anciens paniers en contiennent encore.
                # / Amount typed for a free price; a fixed price has none. The "None" string
                # counts as no amount: sessions live 12 weeks and old carts still hold it.
                montant_saisi = item.get('custom_amount')
                custom_amount = None
                if montant_saisi not in (None, '', 'None'):
                    custom_amount = Decimal(montant_saisi)

                is_valid, result, checkout_url = validate_new_booking(
                    resource              = resource,
                    start_datetime        = datetime.fromisoformat(item.get('start_datetime')),
                    slot_duration_minutes = int(item.get('slot_duration_minutes')),
                    slot_count            = int(item.get('slot_count')),
                    member                = user,
                    commande = commande,
                    price = price,
                    external_payment_method=PaymentMethod.STRIPE_NOFED,
                    create_checkout = False,
                    last_name=resolved_lastname,
                    first_name=resolved_firstname,
                    custom_amount=custom_amount,
                    vente=vente,
                )

                if not is_valid:
                    raise CommandeServiceError(_("Booking not valide : ") + result)

                # Pas de code promo sur une ligne de ressource : aucun formulaire ne le
                # propose, et `validate_new_booking` ne déduit aucune remise (SPEC §1.6, C7).
                # La ligne comptable annoncerait sinon une remise qui n'a pas été faite.
                # / No promo code on a resource line: no form offers one and no discount is
                # applied, so recording a code would make the sale line lie.
                for ligne in result.lignearticles.all():
                    all_lines.append(ligne)
                    total_centimes += ligne.total_catalogue


            # -- Phase 3/4 : Stripe ou gratuit --
            # -- Phase 3/4: Stripe or free --
            # Stripe refuse un paiement dont le total est entre 0,01 € et 0,49 €. On refuse
            # avant de l'appeler, avec un message clair ; la transaction est annulée et les
            # articles restent dans le panier.
            # / Stripe refuses a payment whose total is between 0.01 € and 0.49 €: refuse
            # before calling it, with a clear message.
            if 0 < total_centimes < 50:
                raise CommandeServiceError(_("The amount must be 0 (free) or at least €0.50."))

            if total_centimes > 0:
                CommandeService._creer_paiement_stripe(commande, user, all_lines, vente)
                # Status reste PENDING — Stripe webhook basculera en PAID via signaux
            else:
                # Commande gratuite : pas de Stripe, la vente est encaissée à 0 (ou annulée
                # si elle n'a aucun article) à la fin de la finalisation.
                # / Free order: no Stripe, the sale is settled at 0 (or cancelled if empty).
                CommandeService._finaliser_gratuit(commande, all_lines)

            logger.info(
                f"CommandeService.materialiser OK : commande={commande.uuid_8()}, "
                f"lignes={len(all_lines)}, total_cts={total_centimes}, status={commande.status}"
            )
            return commande, True

    @staticmethod
    def _resolve_amount(price, item):
        """Calcule le montant Decimal à utiliser pour ce price + item.
        / Compute the Decimal amount to use for this price + item."""
        if price.free_price and item.get('custom_amount'):
            return Decimal(str(item['custom_amount']))

        return price.prix or Decimal("0.00")

    @staticmethod
    def _creer_paiement_stripe(commande, user, lignes, vente):
        """Phase 3 — crée un Paiement_stripe consolidé pour toutes les lignes.
        Le paiement porte la vente de la commande (`vente`), posée dans son INSERT.
        / Phase 3 — create a consolidated Paiement_stripe for all lines. The payment
        carries the order's sale, set in its INSERT."""
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
        # Une « réservation gratuite » n'a pas de ligne de vente : on regarde donc aussi les
        # réservations de la Commande (leurs billets attendent le paiement).
        # / Detection: does the order contain tickets? If yes → deny SEPA. A free booking has
        # no sale line, so the Order's reservations are checked too.
        contains_tickets = commande.reservations.exists() or any(
            line.reservation is not None for line in lignes
        )

        # Pareil pour les bookings, réservation potentiellement proche dans le temps
        contains_bookings = any(
            line.booking is not None for line in lignes
        )

        # Le success_url pointe vers l'action `stripe_return` sur EventMVT
        # (`/event/<paiement_stripe_uuid>/stripe_return/`) — meme flow que
        # pour une reservation directe (validators.py:345). Pas d'action
        # stripe_return sur PanierMVT, donc on reutilise celle d'EventMVT
        # qui est generique : update checkout status + redirect vers
        # `/my_account/my_reservations/` (ou `/event/` si anonyme).
        # / success_url → EventMVT.stripe_return (same pattern as direct
        # reservations). PanierMVT has no stripe_return action, so we reuse
        # the generic one which updates status + redirects to user account.
        new_paiement = CreationPaiementStripe(
            user=user,
            liste_ligne_article=lignes,
            metadata=metadata,
            reservation=None,  # Pas de FK : le pivot est Commande
            booking=None, # Pas de FK : le pivot est Commande
            source=Paiement_stripe.FRONT_BILLETTERIE,
            success_url="stripe_return/",
            cancel_url="stripe_return/",
            absolute_domain=f"https://{tenant.get_primary_domain()}/event/",
            accept_sepa=(not contains_tickets and not contains_bookings),
            vente=vente,
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
        Phase 4 — commande gratuite (total 0€) : pas de Stripe. Les lignes sont validées en
        « offert » ; les adhésions passent par le déclencheur de paiement (mail, récompense
        monnaie) ; les réservations et bookings prennent leur statut gratuit.
        / Phase 4 — free order (total 0€): no Stripe. Lines valid as "free", memberships go
        through the payment trigger, reservations and bookings get their free status.
        Enfin la vente de la commande est encaissée à 0, ou annulée si elle est vide.
        / Finally the order's sale is settled at 0, or cancelled if empty.
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

        # Reservations de la commande → FREERES/FREERES_USERACTIV selon user.is_active.
        # Au panier, TicketCreator ne pose jamais ce statut (create_checkout=False) : chaque
        # reservation est encore « creee ». Ce passage unique active et envoie tous ses billets
        # (machine a etats, signals.py), gratuits comme billets a 0 €.
        # / Commande's reservations → FREERES/FREERES_USERACTIV per user.is_active. In the
        # cart, TicketCreator never sets it: this single save activates and mails every ticket.
        for reservation in commande.reservations.all():
            user = reservation.user_commande
            reservation.status = (
                Reservation.FREERES_USERACTIV if user.is_active else Reservation.FREERES
            )
            reservation.save()

        for booking in commande.bookings.all():
            user = booking.user
            booking.status =  (
                Booking.FREERES_USERACTIV if user.is_active else Booking.FREERES
            )
            booking.save()


        # LigneArticle → payment_method=FREE, puis :
        # - ligne d'adhesion : passage par PAID, comme le parcours direct d'une adhesion
        #   gratuite. La machine a etats lance alors trigger_A (mail de confirmation,
        #   recompense monnaie, rattachement de l'adherent au lieu), qui passe la ligne a VALID ;
        # - ligne de billet : passage par PAID, comme le parcours direct d'un billet a 0 €.
        #   trigger_B envoie la vente a LaBoutik et passe la ligne a VALID ;
        # - ligne de booking : VALID directement. Elle ne doit pas passer par PAID :
        #   trigger_C mettrait le booking gratuit en "paye par l'utilisateur".
        # / LigneArticle → FREE, then: membership and ticket lines through PAID (trigger_A /
        # trigger_B run and set them VALID); booking lines straight to VALID.
        for line in lignes:
            line.payment_method = PaymentMethod.FREE
            if line.membership_id:
                # Recharger l'adhesion AVANT de passer la ligne en PAID. La ligne porte
                # l'objet cree en phase 1, reste "en attente de paiement" en memoire.
                # trigger_A (declenche par PAID) sauve cette adhesion (set_deadline) : un
                # objet perime ecraserait le statut ONCE pose plus haut dans cette methode.
                # / Reload the membership BEFORE setting the line PAID: trigger_A saves it,
                # and a stale object would overwrite the ONCE status set above.
                line.membership.refresh_from_db()
                line.status = LigneArticle.PAID
            elif line.reservation_id:
                line.status = LigneArticle.PAID
            else:
                line.status = LigneArticle.VALID
            line.save(update_fields=["status", "payment_method"])

        commande.status = Commande.PAID
        commande.paid_at = now
        commande.save(update_fields=["status", "paid_at"])

        # La vente de la commande, après le passage de TOUTES ses lignes :
        # - elle a des articles : encaissée à 0 (REGLEE, numérotée, aucun règlement),
        #   c'est une opération enregistrée ;
        # - elle n'a aucun article (commande de « réservations gratuites » seules, qui
        #   n'écrivent pas de ligne) : annulée, sans numéro. Pas de vente sans ligne.
        # / The order's sale, after ALL its lines: settled at 0 if it has items, cancelled
        # (no number) if it has none.
        vente_de_la_commande = commande.vente
        if vente_de_la_commande.articles.exists():
            encaisser_vente(vente_de_la_commande)
        else:
            annuler_vente(vente_de_la_commande)
