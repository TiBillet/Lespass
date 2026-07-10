"""
kiosk/tasks.py — Tache Celery de suivi du statut TPE Stripe (CHANTIER-02, Task 02A).
kiosk/tasks.py — Celery task polling the Stripe terminal payment status.

Copie rebranchee de LaBoutik htmxview/tasks.py (poll_payment_intent_status),
import rebranche sur kiosk.models. Le canal WebSocket (room_name) reste le
payment_intent_stripe_id, coherent avec le TerminalConsumer de la Task 02B.
/ Rebranched copy of LaBoutik htmxview/tasks.py (poll_payment_intent_status),
import rebranched onto kiosk.models. The WebSocket room stays the
payment_intent_stripe_id, matching the Task 02B TerminalConsumer.
"""

import logging
import time
from datetime import timedelta

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.utils import timezone

from kiosk.models import PaymentsIntent

logger = logging.getLogger(__name__)


@shared_task
def poll_payment_intent_status(payment_intent_pk, max_duration_seconds=120):
    """
    Interroge le statut de l'intention de paiement toutes les secondes, jusqu'a
    max_duration_seconds. Envoie des messages WebSocket pour mettre a jour le
    front en temps reel. S'arrete si le statut passe en SUCCEEDED/CANCELED ou
    si le delai maximum est atteint.
    / Poll the payment intent status every second for up to max_duration_seconds.
    Send WebSocket messages to update the frontend in real-time. Stop polling
    if the status becomes SUCCEEDED/CANCELED or if max_duration_seconds is reached.

    Args:
        payment_intent_pk: l'id du PaymentsIntent a surveiller / the PaymentsIntent id to poll
        max_duration_seconds: duree maximum de polling en secondes (defaut : 120)
    """
    time.sleep(1)

    logger.info(f"Starting to poll payment intent status for ID: {payment_intent_pk}")

    channel_layer = get_channel_layer()
    room_name = None

    start_time = timezone.now()
    end_time = start_time + timedelta(seconds=max_duration_seconds)

    try:
        payment_intent = PaymentsIntent.objects.get(pk=payment_intent_pk)
        logger.info(f"payment_intent {payment_intent.pk} -- status : {payment_intent.status}")
        room_name = payment_intent.payment_intent_stripe_id

        retry_count = 0
        while timezone.now() < end_time and payment_intent.status not in [PaymentsIntent.SUCCEEDED,
                                                                          PaymentsIntent.CANCELED]:
            # Statut actuel depuis Stripe / Current status from Stripe
            status = payment_intent.get_from_stripe()
            logger.info(f"Payment intent {payment_intent_pk} status: {payment_intent.get_status_display()}")

            # Envoi du statut via WebSocket / Send the status update via WebSocket
            event = {
                'type': 'message',
                'status': status,
                'status_display': payment_intent.get_status_display(),
                'timestamp': timezone.now().isoformat(),
                'retry_count': retry_count,
            }

            async_to_sync(channel_layer.group_send)(
                room_name,
                event
            )

            # Attente d'une seconde avant le prochain sondage / Wait 1 second before the next poll
            retry_count += 1
            time.sleep(1)

        logger.info(f"Finished polling payment intent status for ID: {payment_intent_pk}")

        # CAS 1 : le paiement est termine (succes ou annule) -> on pousse l'ecran final.
        # / Payment finished (success or cancel) -> push the final screen.
        if payment_intent.status in [PaymentsIntent.CANCELED, PaymentsIntent.SUCCEEDED]:
            event = {
                'type': 'template',
                'template': 'cancel.html' if payment_intent.status == PaymentsIntent.CANCELED else 'success.html',
                'status': payment_intent.status,
                'status_display': payment_intent.get_status_display(),
                'timestamp': timezone.now().isoformat(),
                'retry_count': retry_count,
            }
            async_to_sync(channel_layer.group_send)(
                room_name,
                event
            )
            return True

        # CAS 2 : on est sorti par TIMEOUT, sans succes ni annulation dans le delai.
        # On ne laisse JAMAIS l'ecran sur le spinner, MAIS on n'affiche pas un
        # « Annule » mensonger : on annule REELLEMENT cote Stripe (on lache le
        # lecteur), puis on affiche l'ecran du statut REEL. Si la carte a ete
        # capturee juste avant, l'annulation echoue, get_from_stripe (dans
        # annuler_sur_le_terminal) renvoie SUCCEEDED, et on affiche le succes.
        # Sinon le paiement passe CANCELED et l'ecran, la base et Stripe sont
        # coherents (plus de webhook Fedow qui crediterait apres un « annule »).
        # / Timeout: never leave the spinner, but do not show a lying "cancelled".
        # We really cancel on Stripe (release the reader), then show the screen for
        # the REAL status. If the card was captured just before, the cancel fails,
        # get_from_stripe returns SUCCEEDED, and we show success. Otherwise CANCELED,
        # and screen/DB/Stripe stay consistent.
        logger.warning(
            f"Polling timeout for payment intent {payment_intent_pk} "
            f"(status={payment_intent.status}) after {max_duration_seconds}s"
        )
        statut_final = payment_intent.annuler_sur_le_terminal()
        template_final = 'success.html' if statut_final == PaymentsIntent.SUCCEEDED else 'cancel.html'
        event = {
            'type': 'template',
            'template': template_final,
            'status': statut_final,
            'status_display': payment_intent.get_status_display(),
            'timestamp': timezone.now().isoformat(),
            'retry_count': retry_count,
        }
        async_to_sync(channel_layer.group_send)(
            room_name,
            event
        )
        return False

    except PaymentsIntent.DoesNotExist:
        logger.error(f"Payment intent with ID {payment_intent_pk} does not exist")
        return False
    except Exception as e:
        # On log l'erreur sans relancer d'exception : la tache ne doit pas planter.
        # / Log the error without re-raising: the task must not crash.
        logger.error(f"Error polling payment intent status: {e}")

        # Meme regle que le timeout (CAS 2) : ne JAMAIS laisser l'ecran bloque sur
        # le spinner. Best effort : on pousse l'ecran d'annulation si le canal est
        # connu. Le credit reel reste gere cote Fedow via le webhook Stripe.
        # / Same rule as the timeout (CASE 2): NEVER leave the screen stuck on the
        # spinner. Best effort: push the cancel screen if the room is known.
        # The real credit is still handled on Fedow's side via the Stripe webhook.
        if room_name:
            try:
                async_to_sync(channel_layer.group_send)(
                    room_name,
                    {
                        'type': 'template',
                        'template': 'cancel.html',
                        'status': None,
                        'status_display': '',
                        'timestamp': timezone.now().isoformat(),
                        'retry_count': 0,
                    }
                )
            except Exception as send_error:
                logger.error(f"Error sending cancel screen after polling failure: {send_error}")
        return False
