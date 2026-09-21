import logging

from BaseBillet.models import Configuration, LigneArticle
from django.db import connection
from fedow_connect.utils import dround

from BaseBillet.tasks import CeleryMailerClass
from django.utils.translation import gettext_lazy as _, activate
from django.utils import timezone
from TiBillet.celery import app
from booking.models import Booking

logger = logging.getLogger(__name__)


@app.task
def send_booking_cancellation_user(booking_uuid: str):
    """
    Envoie un email à l'utilisateur pour confirmer l'annulation de sa réservation booking.
    """
    config = Configuration.get_solo()
    activate(config.language)

    try:
        booking = Booking.objects.get(pk=booking_uuid)
    except Booking.DoesNotExist:
        logger.error(f"send_booking_cancellation_user: booking {booking_uuid} does not exist")
        return False

    title = f"{config.organisation.capitalize()} - " + _("Your booking has been cancelled.")

    # Image/logo du lieu
    image_url_place = "https://tibillet.coop/static/assets/logo-couleur.svg"
    try:
        domain = connection.tenant.get_primary_domain().domain
        if hasattr(config, 'img') and hasattr(config.img, 'med') and config.img.med:
            image_url_place = f"https://{domain}{config.img.med.url}"
    except Exception:
        pass

    # Montant remboursé = montant de la vente d'origine (lignes payées).
    # Pas total_paid() : le mail part après l'annulation, il compte déjà le remboursement et vaut 0.
    # / Refunded amount = original sale amount (paid lines).
    # Not total_paid(): the mail is sent after cancellation, it already counts the refund and is 0.
    refund_amount = 0

    try:
        if booking.can_refund():
            montant_de_la_vente = 0
            for ligne in booking.lignearticles.filter(status__in=[LigneArticle.PAID, LigneArticle.VALID]):
                montant_de_la_vente += int(ligne.amount * ligne.qty)
            refund_amount = dround(montant_de_la_vente)
    except Exception:
        refund_amount = None

    currency_symbol = "€"
    context = {
        'title': title,
        'organisation': config.organisation,
        'booking': booking,
        'cancel_text': booking.cancel_text(),
        'refund_amount': refund_amount,
        'currency_symbol': currency_symbol,
        'now': timezone.now(),
        'image_url_place': image_url_place,
    }

    mail = CeleryMailerClass(
        booking.user.email,
        title,
        template="booking/emails/booking_cancellation.html",
        context=context,
    )
    mail.send()
    return bool(mail.sended)
