import datetime
import logging

from BaseBillet.models import Configuration, LigneArticle
from django.db import connection
from fedow_connect.utils import dround

from BaseBillet.tasks import CeleryMailerClass
from django.utils.translation import gettext_lazy as _, activate
from django.utils import timezone
from django.utils.formats import date_format
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
                montant_de_la_vente += ligne.total_ttc
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


# ---------------------------------------------------------------------------
# BÉNÉVOLAT — mails / VOLUNTEERING — emails
# Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§5.3 étape 6, §5.4)
# ---------------------------------------------------------------------------

def _adresse_du_lieu_et_logo(config):
    """
    Le domaine du lieu (pour les liens absolus) et l'adresse de son logo.
    / The venue domain (for absolute links) and its logo URL.
    """
    domaine_du_lieu = connection.tenant.get_primary_domain().domain
    image_url_place = "https://tibillet.coop/static/assets/logo-couleur.svg"
    if hasattr(config, 'img') and hasattr(config.img, 'med') and config.img.med:
        image_url_place = f"https://{domaine_du_lieu}{config.img.med.url}"
    return domaine_du_lieu, image_url_place


@app.task
def envoyer_confirmation_benevole(inscription_uuid: str, par_l_equipe: bool = False):
    """
    Envoie à la personne le mail de confirmation de son inscription sur un besoin.
    / Sends the sign-up confirmation email to the volunteer.

    LOCALISATION : booking/tasks.py

    Appelée par booking/views_benevolat.py (inscrire), après le commit.
    par_l_equipe=True : c'est l'équipe qui a inscrit la personne (spec §5.10) ;
    c'est l'appelant qui choisit le texte, pas le champ inscrit_par.
    / par_l_equipe=True: the team signed the person up; the caller picks the text.
    """
    from booking.benevolat import jeton_de_desistement, plage_horaire
    from booking.models import InscriptionBenevole

    config = Configuration.get_solo()
    activate(config.language)

    try:
        inscription = InscriptionBenevole.objects.select_related(
            "user", "besoin__tache", "besoin__planning",
        ).get(pk=inscription_uuid)
    except InscriptionBenevole.DoesNotExist:
        # La personne s'est retirée avant l'envoi : rien à confirmer.
        # / The person withdrew before sending: nothing to confirm.
        logger.info(f"envoyer_confirmation_benevole : inscription {inscription_uuid} absente")
        return False

    besoin = inscription.besoin
    domaine_du_lieu, image_url_place = _adresse_du_lieu_et_logo(config)

    # La date dans le sujet : plusieurs inscriptions ne donnent pas des mails identiques.
    # / The date in the subject: several sign-ups don't give identical emails.
    title = f"{config.organisation} - " + _("C'est noté : %(tache)s, %(jour)s") % {
        "tache": besoin.tache.name, "jour": date_format(besoin.date, "l j F"),
    }
    context = {
        'title': title,
        'organisation': config.organisation,
        'image_url_place': image_url_place,
        'besoin': besoin,
        'plage': plage_horaire(besoin),
        'par_l_equipe': par_l_equipe,
        'url_du_planning': f"https://{domaine_du_lieu}/booking/benevolat/{besoin.planning.slug}/",
        'url_de_mes_creneaux': f"https://{domaine_du_lieu}/my_account/my_volunteering/",
        'url_de_desistement': (
            f"https://{domaine_du_lieu}/booking/benevolat/desistement/{jeton_de_desistement(inscription)}/"
        ),
    }

    mail = CeleryMailerClass(
        inscription.user.email,
        title,
        template="booking/benevolat/emails/confirmation.html",
        context=context,
    )
    mail.send()
    return bool(mail.sended)


@app.task
def prevenir_l_equipe_d_un_desistement(besoin_uuid: str, nom_de_la_personne: str):
    """
    Prévient l'équipe du lieu (Configuration.email) qu'une personne ne viendra plus,
    quand elle se retire après le délai de retrait (P10).
    / Tells the venue team that someone withdrew after the deadline (P10).

    LOCALISATION : booking/tasks.py

    Appelée par booking/views_benevolat.py (retirer), après la suppression de
    l'inscription : on reçoit donc le besoin et le nom, pas l'inscription.
    / Called after the sign-up is deleted: receives the need and the name.
    """
    from booking.benevolat import plage_horaire
    from booking.models import BesoinBenevole

    config = Configuration.get_solo()
    activate(config.language)

    if not config.email:
        logger.warning("prevenir_l_equipe_d_un_desistement : le lieu n'a pas d'email")
        return False

    try:
        besoin = BesoinBenevole.objects.select_related("tache", "planning").get(pk=besoin_uuid)
    except BesoinBenevole.DoesNotExist:
        logger.info(f"prevenir_l_equipe_d_un_desistement : besoin {besoin_uuid} absent")
        return False

    domaine_du_lieu, image_url_place = _adresse_du_lieu_et_logo(config)

    title = f"{config.organisation} - " + _("%(nom)s ne pourra pas venir") % {"nom": nom_de_la_personne}
    context = {
        'title': title,
        'organisation': config.organisation,
        'image_url_place': image_url_place,
        'besoin': besoin,
        'plage': plage_horaire(besoin),
        'nom_de_la_personne': nom_de_la_personne,
        'nombre_inscrits': besoin.nombre_inscrits(),
        'url_de_l_admin': f"https://{domaine_du_lieu}/admin/booking/planningbenevole/{besoin.planning.pk}/change/",
    }

    mail = CeleryMailerClass(
        config.email,
        title,
        template="booking/benevolat/emails/desistement_equipe.html",
        context=context,
    )
    mail.send()
    return bool(mail.sended)


@app.task
def rappeler_les_benevoles_du_lendemain():
    """
    Chaque matin : un mail de rappel à chaque personne inscrite à un besoin de DEMAIN,
    dans tous les lieux.
    / Every morning: a reminder to everyone signed up for a need TOMORROW, in every venue.

    LOCALISATION : booking/tasks.py
    Programmée dans TiBillet/celery.py (cron_rappel_des_benevoles, 8h UTC).
    Même boucle que membership_renewal_reminder (BaseBillet/tasks.py) : on saute
    `public` et les emplacements vides (WAITING_CONFIG, schéma peut-être pas migré).
    Un lieu en erreur est journalisé et n'empêche pas les suivants.
    / Skips public and WAITING_CONFIG slots; a failing venue doesn't stop the others.
    """
    from django_tenants.utils import get_tenant_model, tenant_context

    from Customers.models import Client

    lieux = get_tenant_model().objects.exclude(schema_name="public").exclude(categorie=Client.WAITING_CONFIG)
    for lieu in lieux:
        try:
            with tenant_context(lieu):
                rappeler_les_benevoles_du_lendemain_du_lieu()
        except Exception:
            # logger.exception garde la pile d'appels : Sentry la reçoit.
            # / logger.exception keeps the traceback for Sentry.
            logger.exception(f"rappeler_les_benevoles_du_lendemain : lieu {lieu.schema_name} en erreur")


def rappeler_les_benevoles_du_lendemain_du_lieu():
    """
    Les rappels du lieu courant (à appeler dans un tenant_context).
    / The current venue's reminders (call inside a tenant_context).

    « Demain » = la date de demain DANS LE FUSEAU DU LIEU, pas en UTC.
    Seulement les inscriptions sans rappel (rappel_envoye_le vide), sur un planning
    publié. rappel_envoye_le est rempli juste après un envoi réussi : relancer la tâche
    n'envoie rien deux fois.
    / Tomorrow in the venue timezone. rappel_envoye_le prevents a second send.

    :return: le nombre de rappels envoyés
    """
    from booking.benevolat import jeton_de_desistement, plage_horaire
    from booking.models import InscriptionBenevole

    config = Configuration.get_solo()
    activate(config.language)
    fuseau_du_lieu = config.get_tzinfo()
    demain_au_lieu = timezone.now().astimezone(fuseau_du_lieu).date() + datetime.timedelta(days=1)

    inscriptions_a_rappeler = InscriptionBenevole.objects.filter(
        besoin__date=demain_au_lieu,
        besoin__planning__published=True,
        rappel_envoye_le__isnull=True,
    ).select_related("user", "besoin__tache", "besoin__planning")

    if not inscriptions_a_rappeler.exists():
        return 0

    domaine_du_lieu, image_url_place = _adresse_du_lieu_et_logo(config)
    nombre_de_rappels_envoyes = 0
    for inscription in inscriptions_a_rappeler:
        # Un mail qui échoue (adresse refusée, sujet invalide…) est journalisé — donc
        # visible dans Sentry — sans priver les autres bénévoles de leur rappel : la tâche
        # ne repasse que demain, et « demain » aura changé.
        # / A failing email is logged without blocking the others' reminders.
        try:
            besoin = inscription.besoin
            if besoin.est_une_journee():
                title = _("Demain : %(tache)s. Merci !") % {"tache": besoin.tache.name}
            else:
                title = _("Demain %(plage)s : %(tache)s. Merci !") % {
                    "plage": plage_horaire(besoin), "tache": besoin.tache.name,
                }
            context = {
                'title': title,
                'organisation': config.organisation,
                'image_url_place': image_url_place,
                'besoin': besoin,
                'plage': plage_horaire(besoin),
                'url_de_mes_creneaux': f"https://{domaine_du_lieu}/my_account/my_volunteering/",
                'url_de_desistement': (
                    f"https://{domaine_du_lieu}/booking/benevolat/desistement/{jeton_de_desistement(inscription)}/"
                ),
            }
            mail = CeleryMailerClass(
                inscription.user.email,
                f"{config.organisation} - {title}",
                template="booking/benevolat/emails/rappel.html",
                context=context,
            )
            mail.send()
            if mail.sended:
                InscriptionBenevole.objects.filter(pk=inscription.pk).update(rappel_envoye_le=timezone.now())
                nombre_de_rappels_envoyes += 1
            else:
                logger.warning(f"rappel bénévole non envoyé à {inscription.user.email} (inscription {inscription.pk})")
        except Exception:
            logger.exception(f"rappel bénévole en erreur pour l'inscription {inscription.pk}")

    logger.info(f"rappeler_les_benevoles_du_lendemain : {nombre_de_rappels_envoyes} rappels envoyés")
    return nombre_de_rappels_envoyes


@app.task
def creer_les_besoins_des_semaines_types():
    """
    Chaque nuit : ouvre les semaines à venir des plannings hebdomadaires de bénévoles
    (crée les besoins de leur semaine type), dans tous les lieux.
    / Every night: opens the coming weeks of weekly volunteer plannings, in every venue.

    LOCALISATION : booking/tasks.py
    Programmée dans TiBillet/celery.py (cron_besoins_des_semaines_types, 3h UTC).
    Même boucle que rappeler_les_benevoles_du_lendemain : on saute `public` et les
    emplacements vides (WAITING_CONFIG). Un lieu en erreur est journalisé et n'empêche
    pas les suivants.
    / Same loop as the reminder: skips public and WAITING_CONFIG slots.
    """
    from django_tenants.utils import get_tenant_model, tenant_context

    from Customers.models import Client

    lieux = get_tenant_model().objects.exclude(schema_name="public").exclude(categorie=Client.WAITING_CONFIG)
    for lieu in lieux:
        try:
            with tenant_context(lieu):
                creer_les_besoins_des_semaines_types_du_lieu()
        except Exception:
            logger.exception(f"creer_les_besoins_des_semaines_types : lieu {lieu.schema_name} en erreur")


def creer_les_besoins_des_semaines_types_du_lieu():
    """
    Les plannings hebdomadaires du lieu courant (à appeler dans un tenant_context).
    Le calcul de la fenêtre et le verrou sont dans booking/benevolat.py
    (creer_les_besoins_de_la_semaine_type) : relancer la tâche ne crée rien deux fois.
    / The current venue's weekly plannings (call inside a tenant_context).

    :return: le nombre de besoins créés
    """
    from booking.benevolat import creer_les_besoins_de_la_semaine_type
    from booking.models import PlanningBenevole

    nombre_de_besoins_crees = 0
    plannings_hebdomadaires = PlanningBenevole.objects.filter(type_de_planning=PlanningBenevole.HEBDOMADAIRE)
    for planning in plannings_hebdomadaires:
        nombre_de_besoins_crees += creer_les_besoins_de_la_semaine_type(planning)

    logger.info(f"creer_les_besoins_des_semaines_types : {nombre_de_besoins_crees} besoins créés")
    return nombre_de_besoins_crees
