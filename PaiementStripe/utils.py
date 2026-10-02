import stripe
import logging
from decimal import Decimal

from django.db import transaction
from stripe import InvalidRequestError
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

def partial_refund_payment(paiement, config, ligne_articles, specified_quantity=None):
    """
    Rembourse par Stripe tout ou partie d'un paiement, et écrit le remboursement comme
    UNE vente AVOIR liée à la vente du paiement.
    / Refunds all or part of a payment through Stripe, and writes the refund as ONE
    AVOIR sale linked to the payment's sale.

    LOCALISATION : PaiementStripe/utils.py

    APPELÉE PAR : BaseBillet/models.py `Reservation.cancel_and_refund_resa` et
    `cancel_and_refund_ticket` ; booking/models.py `Booking.cancel_and_refund_booking`.

    QUANTITÉ RENDUE PAR LIGNE (les lignes doivent appartenir au paiement) :
    - `specified_quantity` s'il est donné : la même quantité pour TOUTES les lignes ;
    - sinon l'attribut `to_refund_qty` posé sur la ligne par l'appelant ;
    - sinon toute la quantité de la ligne.
    Une ligne qui n'est ni VALID ni PAID, ou dont la quantité rendue vaut 0, n'est pas
    remboursée.
    / Quantity per line: specified_quantity, else line.to_refund_qty, else the whole
    line. Lines not VALID/PAID or with nothing to give back are skipped.

    FLUX (tout dans UNE transaction, tout ou rien) :
    1. Rien à rendre sur aucune ligne : aucune vente n'est ouverte.
    2. Vente du paiement existante mais pas réglée : refus (ValueError), AVANT Stripe.
    2a. Le paiement Stripe est verrouillé (`select_for_update`), en premier : deux
       demandes sur le même paiement (deux lignes, deux billets) passent l'une après
       l'autre. La seconde relit ce que la première a écrit.
    2b. Chaque ligne est verrouillée et sa quantité déjà rendue relue
       (`quantite_restante_de_la_ligne_sous_verrou`) : refus (ValueError), AVANT Stripe,
       si la quantité demandée dépasse ce qui reste. Deux demandes pour la même ligne
       (double clic) ne remboursent jamais deux fois.
    3. Vente AVOIR, origine LESPASS, liée à la vente du paiement (vide pour un paiement
       antérieur aux ventes), client = celui de cette vente. Un article par ligne
       (`ajouter_l_article_d_avoir`), écrit AVANT Stripe : un refus du service (avoir
       partiel d'un article avec une part offerte, quantité hors bornes) arrête tout
       avant que Stripe ne rende de l'argent.
    4. Montant demandé = −Σ nets des articles (centimes entiers), plafonné à ce que
       Stripe détient encore pour ce paiement : `montant_encaisse` moins les
       remboursements déjà écrits (une vente encaissée avec un écart « reçu en moins »
       a des articles plus chers que l'argent reçu). Paiement sans `montant_encaisse`
       (antérieur au chantier) : pas de plafond. Moins d'un centime : pas d'appel à
       Stripe. Sinon `stripe.Refund.create`, avec la clé d'idempotence
       `remboursement-{paiement.uuid}-{n}`, n = nombre de règlements négatifs déjà
       écrits pour ce paiement (lu sous le verrou du paiement, point 2a). Un nouvel essai après un
       échec (rien d'écrit) reprend la MÊME clé : Stripe renvoie le MÊME remboursement,
       sans rendre d'argent de plus. Le remboursement suivant, une fois le précédent
       écrit, a une clé nouvelle. Limite : Stripe garde une clé 24 h ; un nouvel essai
       plus tardif rembourserait de nouveau.
    5. UN règlement Stripe négatif, montant = −`refund.amount` (LU sur l'objet renvoyé
       par Stripe, jamais calculé), au moyen du paiement (repli : le moyen de la ligne),
       relié au paiement, référence externe = `refund.id`.
    6. La part offerte des articles, tracée par un règlement FREE négatif. La règle
       « offert » du service a pu l'écrire déjà (moyen historique FREE) : jamais deux
       fois. (Aucune ligne payée par Stripe n'a de part offerte aujourd'hui.)
    7. Écart (règlement d'argent − Σ nets des articles) non nul : un article « Écart
       d'encaissement » (`ajouter_l_article_d_ecart_d_encaissement`), alerte ERROR.
    8. `encaisser_vente`, PUIS les transitions : le paiement passe « remboursé en
       partie » (ou « remboursé » si tout est rendu), les articles passent REFUNDED
       (déclencheur de l'ancien LaBoutik, BaseBillet/signals.py).
    Une écriture qui échoue APRÈS le remboursement Stripe : rien n'est écrit, l'erreur
    est journalisée (ERROR, Sentry) avec l'id et le montant du remboursement, pour un
    rapprochement à la main, puis remontée à l'appelant.
    / One transaction: payment locked, lines locked and already refunded quantity read
    again, AVOIR sale, items BEFORE Stripe, Stripe refund capped at what Stripe still
    holds, with an idempotency key (same key on a retry), one
    negative payment of refund.amount with refund.id, FREE payment for the offered part,
    gap item, settle, then transitions. A failure after the refund is logged with its id
    and re-raised; nothing is written.

    :param paiement: le `Paiement_stripe` à rembourser
    :param config: la `Configuration` du lieu (compte Stripe Connect)
    :param ligne_articles: les `LigneArticle` du paiement à rembourser
    :param specified_quantity: quantité rendue sur chaque ligne, ou None
    """
    from BaseBillet.models import Paiement_stripe, LigneArticle, PaymentMethod, SaleOrigin
    from BaseBillet.models_vente import Reglement, Vente
    from BaseBillet.services_vente import (
        ajouter_l_article_d_avoir,
        ajouter_l_article_d_ecart_d_encaissement,
        ajouter_reglement,
        encaisser_vente,
        ouvrir_vente,
        quantite_restante_de_la_ligne_sous_verrou,
    )

    # Une quantité imposée à 0 ne rembourse rien : c'est une erreur de l'appelant.
    # / A forced quantity of 0 refunds nothing: a caller error.
    if specified_quantity == 0:
        raise ValueError(_("Vous devez rembourser au moins un article"))

    # Chaque ligne doit appartenir au paiement remboursé.
    # / Every line must belong to the refunded payment.
    for ligne_article in ligne_articles:
        if not paiement.lignearticles.filter(pk=ligne_article.pk).exists():
            raise ValueError(_("Une LigneArticle n'est pas lié au bon paiement"))

    # Le PaymentIntent à rembourser : lu sur la session Checkout, sinon celui gardé sur
    # le paiement (session expirée ou paiement sans session).
    # / The PaymentIntent to refund: from the Checkout session, else the stored one.
    paiement: Paiement_stripe
    try:
        checkout = paiement.get_checkout_session()
        payment_intent = checkout.payment_intent
    except Exception:
        payment_intent = paiement.payment_intent_id

    # La quantité rendue de chaque ligne remboursable.
    # / The quantity given back for each refundable line.
    lignes_et_quantites_a_rendre = []
    for ligne_article in ligne_articles:
        ligne_remboursable = ligne_article.status in [LigneArticle.VALID, LigneArticle.PAID]
        if not ligne_remboursable:
            continue

        quantite_rendue = ligne_article.qty
        if specified_quantity:
            quantite_rendue = specified_quantity
        elif hasattr(ligne_article, "to_refund_qty"):
            quantite_rendue = ligne_article.to_refund_qty

        # Rien à rendre sur cette ligne : par exemple un tarif dont tous les billets sont
        # déjà annulés, quand on annule ensuite toute la réservation.
        # / Nothing to give back on this line (e.g. tickets already cancelled one by one).
        if quantite_rendue > 0:
            lignes_et_quantites_a_rendre.append((ligne_article, Decimal(quantite_rendue)))

    try:
        with transaction.atomic():
            # 2a. Le paiement, verrouillé et relu, EN PREMIER : tout ce qui suit (n, le
            # plafond) est lu sous ce verrou. Deux demandes sur le même paiement (deux
            # lignes, deux billets) passent l'une après l'autre ; la seconde lit les
            # règlements de la première, donc n + 1.
            # / 2a. The payment, locked and read again, FIRST: n and the cap are read
            # under this lock. Two requests on one payment run one after the other.
            paiement_verrouille = Paiement_stripe.objects.select_for_update().get(
                pk=paiement.pk
            )

            vente_d_avoir = None
            articles_d_avoir = []
            somme_des_nets_rendus = 0

            if lignes_et_quantites_a_rendre:
                # 2. Une vente d'origine pas réglée ne reçoit pas d'avoir.
                # / 2. An unsettled original sale gets no credit note.
                vente_d_origine = paiement.vente
                if vente_d_origine is not None:
                    vente_d_origine.refresh_from_db()
                    if vente_d_origine.statut != Vente.Statut.REGLEE:
                        raise ValueError(
                            f"La vente d'origine {vente_d_origine.uuid} du paiement Stripe "
                            f"{paiement.uuid} n'est pas réglée (statut "
                            f"{vente_d_origine.statut}) : le remboursement est impossible."
                        )
                    client_de_la_vente_liee = vente_d_origine.client
                else:
                    client_de_la_vente_liee = None

                # 2b. Sous verrou, ce qui reste à rendre sur chaque ligne, AVANT Stripe.
                # / 2b. Under lock, what is left to give back on each line, BEFORE Stripe.
                for ligne_article, quantite_rendue in lignes_et_quantites_a_rendre:
                    quantite_restante = quantite_restante_de_la_ligne_sous_verrou(
                        ligne_article
                    )
                    if quantite_rendue > quantite_restante:
                        raise ValueError(
                            f"La quantité remboursée ({quantite_rendue}) dépasse ce qui "
                            f"reste à rendre sur la ligne {ligne_article.uuid} "
                            f"({quantite_restante}) : un avoir ou un remboursement a "
                            f"déjà été fait."
                        )

                # 3. La vente AVOIR et ses articles, AVANT Stripe.
                # / 3. The AVOIR sale and its items, BEFORE Stripe.
                vente_d_avoir = ouvrir_vente(
                    origine=SaleOrigin.LESPASS,
                    nature=Vente.Nature.AVOIR,
                    client=client_de_la_vente_liee,
                    vente_liee=vente_d_origine,
                )
                for ligne_article, quantite_rendue in lignes_et_quantites_a_rendre:
                    article_d_avoir = ajouter_l_article_d_avoir(
                        vente_d_avoir, ligne_article, quantite_rendue
                    )
                    articles_d_avoir.append(article_d_avoir)
                    somme_des_nets_rendus += article_d_avoir.total_ttc

            # 4. Le remboursement Stripe, du net rendu (les nets d'un avoir sont négatifs).
            # Moins d'un centime : rien à demander à Stripe.
            # / 4. The Stripe refund, of the net given back. Under one cent: no call.
            montant_demande_a_stripe = -somme_des_nets_rendus

            # Plafond : Stripe ne rend jamais plus qu'il ne détient pour ce paiement.
            # La différence avec les articles devient l'article d'écart (point 7).
            # / Cap: Stripe never gives back more than it holds for this payment.
            montant_encaisse_par_stripe = paiement_verrouille.montant_encaisse
            if montant_encaisse_par_stripe is not None:
                somme_des_remboursements_deja_ecrits = 0
                for reglement_negatif in Reglement.objects.filter(
                    paiement_stripe=paiement_verrouille,
                    montant__lt=0,
                ):
                    somme_des_remboursements_deja_ecrits += reglement_negatif.montant
                montant_encore_detenu_par_stripe = (
                    montant_encaisse_par_stripe + somme_des_remboursements_deja_ecrits
                )
                if montant_demande_a_stripe > montant_encore_detenu_par_stripe:
                    montant_demande_a_stripe = max(montant_encore_detenu_par_stripe, 0)

            refund = None
            if montant_demande_a_stripe >= 1:
                # La clé d'idempotence : n = remboursements déjà ÉCRITS pour ce paiement,
                # compté sous le verrou du paiement (point 2a). Un essai qui a échoué n'a
                # rien écrit : le nouvel essai garde la même clé, et Stripe renvoie le
                # même remboursement. Deux demandes sur deux lignes du même paiement
                # passent l'une après l'autre : la seconde lit n + 1.
                # / The idempotency key: n = refunds already WRITTEN for this payment,
                # counted under the payment lock. A failed try wrote nothing: the retry
                # keeps the key, same refund. Two requests on one payment run one after
                # the other: the second one reads n + 1.
                nombre_de_remboursements_deja_ecrits = Reglement.objects.filter(
                    paiement_stripe=paiement,
                    montant__lt=0,
                ).count()
                cle_d_idempotence = (
                    f"remboursement-{paiement.uuid}-{nombre_de_remboursements_deja_ecrits}"
                )
                refund = stripe.Refund.create(
                    payment_intent=payment_intent,
                    reason='requested_by_customer',
                    amount=montant_demande_a_stripe,
                    stripe_account=config.get_stripe_connect_account(),
                    idempotency_key=cle_d_idempotence,
                )
                logger.info(f"Remboursement Stripe {refund.id} : {refund.status}")

            # Désormais, l'argent est peut-être parti chez Stripe : toute erreur est
            # journalisée avec l'id et le montant du remboursement.
            # / From here, money may have left Stripe: any error is logged with the refund.
            try:
                if vente_d_avoir is not None:
                    # 5. UN règlement d'argent, au montant RENVOYÉ par Stripe.
                    # / 5. ONE money payment, of the amount RETURNED by Stripe.
                    montant_rendu_par_stripe = 0
                    if refund is not None:
                        montant_rendu_par_stripe = refund.amount
                    if montant_rendu_par_stripe != 0:
                        moyen_du_remboursement = (
                            paiement.moyen or lignes_et_quantites_a_rendre[0][0].payment_method
                        )
                        ajouter_reglement(
                            vente_d_avoir,
                            moyen=moyen_du_remboursement,
                            montant=-montant_rendu_par_stripe,
                            paiement_stripe=paiement,
                            reference_externe=refund.id,
                        )

                    # 6. La part offerte annulée, en FREE, jamais deux fois.
                    # / 6. The cancelled offered part, as FREE, never twice.
                    somme_des_parts_offertes_rendues = 0
                    for article_d_avoir in articles_d_avoir:
                        somme_des_parts_offertes_rendues += article_d_avoir.part_offerte
                    part_offerte_deja_tracee = 0
                    for reglement_offert in Reglement.objects.filter(
                        vente=vente_d_avoir, moyen=PaymentMethod.FREE
                    ):
                        part_offerte_deja_tracee += reglement_offert.montant
                    part_offerte_a_tracer = (
                        somme_des_parts_offertes_rendues - part_offerte_deja_tracee
                    )
                    if part_offerte_a_tracer != 0:
                        ajouter_reglement(
                            vente_d_avoir,
                            moyen=PaymentMethod.FREE,
                            montant=part_offerte_a_tracer,
                        )

                    # 7. L'écart entre l'argent rendu et les nets des articles.
                    # / 7. The gap between the money given back and the items' nets.
                    ecart_en_centimes = -montant_rendu_par_stripe - somme_des_nets_rendus
                    ajouter_l_article_d_ecart_d_encaissement(vente_d_avoir, ecart_en_centimes)

                    # 8. Encaisser, PUIS les transitions.
                    # / 8. Settle, THEN the transitions.
                    encaisser_vente(vente_d_avoir)

                    if ecart_en_centimes != 0:
                        # Pas de remboursement Stripe quand le plafond tombe à 0.
                        # / No Stripe refund when the cap drops to 0.
                        identifiant_du_remboursement = "aucun"
                        if refund is not None:
                            identifiant_du_remboursement = refund.id
                        logger.error(
                            f"Écart d'encaissement sur la vente d'avoir {vente_d_avoir.uuid} "
                            f"(remboursement Stripe {identifiant_du_remboursement} du "
                            f"paiement {paiement.uuid}) : Stripe a rendu "
                            f"{montant_rendu_par_stripe} centimes ({montant_demande_a_stripe} "
                            f"demandés) pour {-somme_des_nets_rendus} centimes d'articles "
                            f"(écart {ecart_en_centimes})."
                        )

                if refund is not None:
                    paiement.status = Paiement_stripe.PARTIALLY_REFUNDED
                    paiement.save()

                # Le passage à REFUNDED déclenche l'envoi à l'ancien LaBoutik.
                # / Turning REFUNDED triggers the sending to the legacy LaBoutik.
                for article_d_avoir in articles_d_avoir:
                    article_d_avoir.status = LigneArticle.REFUNDED
                    article_d_avoir.save()

                # Tout le paiement est rendu : il passe « remboursé ».
                # / The whole payment is given back: it turns REFUNDED.
                if paiement.is_fully_refunded():
                    paiement.status = Paiement_stripe.REFUNDED
                    paiement.save()

            except Exception as erreur_apres_le_remboursement:
                if refund is not None:
                    logger.error(
                        f"Remboursement Stripe {refund.id} de {refund.amount} centimes "
                        f"(paiement {paiement.uuid}) FAIT chez Stripe, mais rien n'est "
                        f"écrit en base : {erreur_apres_le_remboursement}. À rapprocher "
                        f"à la main."
                    )
                raise

    # Stripe refuse la demande (paiement inconnu, montant trop grand…) : rien n'est écrit.
    # / Stripe refuses the request: nothing is written.
    except InvalidRequestError as e:
        logger.error(f"CheckoutStripe Refund InvalidRequestError {e}")
        # Stripe refuses the refund of this payment.
        raise ValueError(
            f"Stripe refuse le remboursement du paiement {paiement.uuid} : {e}"
        )
    # Toute autre erreur (refus du service, échec d'écriture) : journalisée, puis remontée
    # telle quelle à l'appelant.
    # / Any other error (service refusal, write failure): logged, then re-raised as is.
    except Exception as e:
        logger.error(f"CheckoutStripe Refund Exception : {e}")
        raise e
