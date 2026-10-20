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
def send_booking_cancellation_user(booking_uuid: str, demande_non_payee: bool = False):
    """
    Envoie un email à l'utilisateur pour confirmer l'annulation de sa réservation booking.
    / Emails the user to confirm the cancellation of their booking.

    demande_non_payee=True : la personne a retiré une demande à validation manuelle
    où rien n'était payé. L'appelant le lit AVANT l'annulation
    (Booking.est_une_demande_non_payee) : après, le statut est USER_CANCELED.
    / demande_non_payee=True: an unpaid manual validation request was withdrawn.
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

    # Une demande non payée : pas de remboursement, pas de montant à afficher.
    # / An unpaid request: no refund, no amount to show.
    cancel_text = booking.cancel_text()
    if demande_non_payee:
        cancel_text = _("Votre demande est annulée. Rien n'a été débité.")
        refund_amount = None

    currency_symbol = "€"
    context = {
        'title': title,
        'organisation': config.organisation,
        'booking': booking,
        'cancel_text': cancel_text,
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
# VALIDATION MANUELLE — mails des demandes de réservation
# / MANUAL VALIDATION — booking request emails
# Spec : TECH_DOC/SESSIONS/BOOKING/SPEC.md (§5.7)
# ---------------------------------------------------------------------------

def _creneau_de_la_demande(booking, config):
    """
    « lundi 3 novembre 2026, 10:00 – 12:00 », à l'heure du lieu.
    / The booked slot, in the venue timezone.
    """
    fuseau_du_lieu = config.get_tzinfo()
    debut = timezone.localtime(booking.start_datetime, fuseau_du_lieu)
    fin = timezone.localtime(booking.end_datetime, fuseau_du_lieu)
    return f"{date_format(debut, 'l j F Y, H:i')} – {date_format(fin, 'H:i')}"


@app.task
def send_booking_request_admin(booking_pk: str):
    """
    Prévient les administrateurs du lieu qu'une demande de réservation attend leur décision.
    / Tells the venue admins that a booking request awaits their decision.

    LOCALISATION : booking/tasks.py

    Appelée par booking/views.py (_book_post), après le commit.
    Destinataires : les admins du lieu, sinon l'adresse du lieu (Configuration.email).
    / Called after commit. Recipients: the venue admins, else Configuration.email.
    """
    from AuthBillet.models import TibilletUser
    from BaseBillet.tasks import send_email_generique

    config = Configuration.get_solo()
    activate(config.language)

    try:
        booking = Booking.objects.select_related("resource", "user").get(pk=booking_pk)
    except Booking.DoesNotExist:
        logger.error(f"send_booking_request_admin : booking {booking_pk} introuvable")
        return False

    adresses_des_admins = list(
        TibilletUser.objects.filter(client_admin=connection.tenant).values_list("email", flat=True)
    )
    if not adresses_des_admins and config.email:
        adresses_des_admins = [config.email]
    if not adresses_des_admins:
        logger.warning("send_booking_request_admin : aucune adresse admin")
        return False

    domaine_du_lieu, image_url_place = _adresse_du_lieu_et_logo(config)
    nom_de_la_personne = f"{booking.first_name or ''} {booking.last_name or ''}".strip()

    context = {
        "username": _("Administrateur"),
        "now": timezone.now(),
        "title": f"{config.organisation} : " + _("Nouvelle demande de réservation"),
        "image_url": image_url_place,
        "sub_title": _("Administration"),
        "main_text": _("Une demande de réservation attend votre validation."),
        "table_info": {
            _("Ressource"): booking.resource.name,
            _("Créneau"): _creneau_de_la_demande(booking, config),
            _("Personne"): nom_de_la_personne,
            _("Email"): booking.user.email,
        },
        "button_color": "#2d76a6",
        "button": {
            "text": _("Ouvrir la demande"),
            "url": f"https://{domaine_du_lieu}/admin/booking/booking/{booking.pk}/change/",
        },
        "end_text": _("Merci"),
        "signature": _("Marvin, le TiBillet robot"),
    }
    send_email_generique(context=context, email=adresses_des_admins)
    return True


@app.task
def send_booking_request_user(booking_pk: str):
    """
    Confirme à la personne que sa demande de réservation est bien reçue.
    / Confirms to the person that their booking request was received.

    LOCALISATION : booking/tasks.py

    Appelée par booking/views.py (_book_post), après le commit.
    / Called by booking/views.py (_book_post), after commit.
    """
    from BaseBillet.tasks import send_email_generique

    config = Configuration.get_solo()
    activate(config.language)

    try:
        booking = Booking.objects.select_related("resource", "user").get(pk=booking_pk)
    except Booking.DoesNotExist:
        logger.error(f"send_booking_request_user : booking {booking_pk} introuvable")
        return False

    domaine_du_lieu, image_url_place = _adresse_du_lieu_et_logo(config)

    context = {
        "username": booking.first_name or booking.user.email,
        "now": timezone.now(),
        "title": f"{config.organisation} : " + _("Votre demande de réservation est enregistrée"),
        "image_url": image_url_place,
        "sub_title": _("Réservation"),
        "main_text": _(
            "L'équipe va étudier votre demande. "
            "Vous recevrez une réponse par mail : une confirmation ou une invitation à payer."
        ),
        "table_info": {
            _("Ressource"): booking.resource.name,
            _("Créneau"): _creneau_de_la_demande(booking, config),
        },
        "button_color": "#2d76a6",
        "button": {
            "text": _("Voir mes réservations"),
            "url": f"https://{domaine_du_lieu}/my_account/my_bookings/",
        },
        "end_text": _("Merci"),
        "signature": _("Marvin, le TiBillet robot"),
    }
    send_email_generique(context=context, email=booking.user.email)
    return True


@app.task
def send_booking_accepted_user(booking_pk: str):
    """
    Dit à la personne que sa demande est acceptée.
    / Tells the person their request was accepted.

    LOCALISATION : booking/tasks.py

    Appelée par booking/views.py (admin_accept), après le commit : le statut lu ici
    est donc celui posé par l'admin.
    - ADMIN_VALID (il reste à payer) : bouton « Payer ma réservation » (BookingViewSet.pay).
    - Sinon (gratuit, FREERES ou FREERES_USERACTIV) : « Votre réservation est confirmée ».
    / Called after commit. To pay: "Pay my booking" button. Free: "confirmed".
    """
    from BaseBillet.tasks import send_email_generique

    config = Configuration.get_solo()
    activate(config.language)

    try:
        booking = Booking.objects.select_related("resource", "user").get(pk=booking_pk)
    except Booking.DoesNotExist:
        logger.error(f"send_booking_accepted_user : booking {booking_pk} introuvable")
        return False

    domaine_du_lieu, image_url_place = _adresse_du_lieu_et_logo(config)

    reste_a_payer = booking.status == Booking.ADMIN_VALID
    if reste_a_payer:
        titre = _("Votre demande de réservation est acceptée")
        texte = _("Bonne nouvelle : l'équipe a accepté votre demande. Il reste à payer pour confirmer la réservation.")
        bouton = {
            "text": _("Payer ma réservation"),
            "url": f"https://{domaine_du_lieu}/booking/{booking.pk}/pay/",
        }
    else:
        titre = _("Votre réservation est confirmée")
        texte = _("Bonne nouvelle : l'équipe a accepté votre demande. Votre réservation est confirmée.")
        bouton = {
            "text": _("Voir mes réservations"),
            "url": f"https://{domaine_du_lieu}/my_account/my_bookings/",
        }

    table_info = {
        _("Ressource"): booking.resource.name,
        _("Créneau"): _creneau_de_la_demande(booking, config),
    }
    if reste_a_payer:
        table_info[_("Montant")] = f"{booking.to_pay()} {config.currency_code}"

    context = {
        "username": booking.first_name or booking.user.email,
        "now": timezone.now(),
        "title": f"{config.organisation} : " + titre,
        "image_url": image_url_place,
        "sub_title": _("Réservation"),
        "main_text": texte,
        "table_info": table_info,
        "button_color": "#2d76a6",
        "button": bouton,
        "end_text": _("Merci"),
        "signature": _("Marvin, le TiBillet robot"),
    }
    send_email_generique(context=context, email=booking.user.email)
    return True


@app.task
def send_booking_refused_user(booking_pk: str):
    """
    Dit à la personne que sa demande n'a pas pu être acceptée, avec le motif s'il existe.
    / Tells the person their request was refused, with the reason if any.

    LOCALISATION : booking/tasks.py

    Appelée par booking/views.py (admin_refuse), après le commit.
    Le motif va dans main_text_3, affiché échappé : main_text_2 est rendu avec |safe
    (emails/email_generique.html), et le motif est un texte tapé à la main.
    / Called after commit. The reason goes to main_text_3 (escaped), never main_text_2 (|safe).
    """
    from BaseBillet.tasks import send_email_generique

    config = Configuration.get_solo()
    activate(config.language)

    try:
        booking = Booking.objects.select_related("resource", "user").get(pk=booking_pk)
    except Booking.DoesNotExist:
        logger.error(f"send_booking_refused_user : booking {booking_pk} introuvable")
        return False

    domaine_du_lieu, image_url_place = _adresse_du_lieu_et_logo(config)

    context = {
        "username": booking.first_name or booking.user.email,
        "now": timezone.now(),
        "title": f"{config.organisation} : " + _("Votre demande de réservation n'a pas pu être acceptée"),
        "image_url": image_url_place,
        "sub_title": _("Réservation"),
        "main_text": _("L'équipe n'a pas pu accepter votre demande. Rien n'a été débité."),
        "table_info": {
            _("Ressource"): booking.resource.name,
            _("Créneau"): _creneau_de_la_demande(booking, config),
        },
        "end_text": _("Merci"),
        "signature": _("Marvin, le TiBillet robot"),
    }
    if booking.motif_du_refus:
        context["main_text_3"] = _("Motif : %(motif)s") % {"motif": booking.motif_du_refus}

    send_email_generique(context=context, email=booking.user.email)
    return True


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
    # Seulement les plannings actifs : un planning désactivé ne crée plus de créneaux.
    # / Active plannings only: a deactivated planning creates nothing.
    plannings_hebdomadaires_actifs = PlanningBenevole.objects.filter(
        type_de_planning=PlanningBenevole.HEBDOMADAIRE, published=True,
    )
    for planning in plannings_hebdomadaires_actifs:
        nombre_de_besoins_crees += creer_les_besoins_de_la_semaine_type(planning)

    logger.info(f"creer_les_besoins_des_semaines_types : {nombre_de_besoins_crees} besoins créés")
    return nombre_de_besoins_crees
