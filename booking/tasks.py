import datetime
import logging

from BaseBillet.models import Configuration, LigneArticle
from django.db import connection
from django.db.models import F
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

    domaine_du_lieu = _domaine_du_lieu()
    nom_de_la_personne = f"{booking.first_name or ''} {booking.last_name or ''}".strip()

    context = {
        "username": _("Administrateur"),
        "title": f"{config.organisation} : " + _("Nouvelle demande de réservation"),
        "sub_title": _("Administration"),
        "main_text": _("Une demande de réservation attend votre validation."),
        "table_info": {
            _("Ressource"): booking.resource.name,
            _("Créneau"): _creneau_de_la_demande(booking, config),
            _("Personne"): nom_de_la_personne,
            _("Email"): booking.user.email,
        },
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

    domaine_du_lieu = _domaine_du_lieu()

    context = {
        "username": booking.first_name or booking.user.email,
        "title": f"{config.organisation} : " + _("Votre demande de réservation est enregistrée"),
        "sub_title": _("Réservation"),
        "main_text": _(
            "L'équipe va étudier votre demande. "
            "Vous recevrez une réponse par mail : une confirmation ou une invitation à payer."
        ),
        "table_info": {
            _("Ressource"): booking.resource.name,
            _("Créneau"): _creneau_de_la_demande(booking, config),
        },
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

    domaine_du_lieu = _domaine_du_lieu()

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
        "title": f"{config.organisation} : " + titre,
        "sub_title": _("Réservation"),
        "main_text": texte,
        "table_info": table_info,
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

    context = {
        "username": booking.first_name or booking.user.email,
        "title": f"{config.organisation} : " + _("Votre demande de réservation n'a pas pu être acceptée"),
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

def _domaine_du_lieu():
    """
    Le domaine du lieu courant, pour les liens absolus des mails.
    Le logo du lieu, lui, vient du contexte commun des mails (BaseBillet/tasks.py,
    contexte_commun_des_mails).
    / The current venue domain, for absolute links in emails.
    """
    return connection.tenant.get_primary_domain().domain


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
    domaine_du_lieu = _domaine_du_lieu()

    # La date dans le sujet : plusieurs inscriptions ne donnent pas des mails identiques.
    # / The date in the subject: several sign-ups don't give identical emails.
    title = f"{config.organisation} - " + _("C'est noté : %(tache)s, %(jour)s") % {
        "tache": besoin.tache.name, "jour": date_format(besoin.date, "l j F"),
    }
    context = {
        'title': title,
        'organisation': config.organisation,
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
def prevenir_l_equipe_d_un_desistement(besoin_uuid: str, nom_de_la_personne: str, prenom_de_la_personne: str = None):
    """
    Prévient qu'une personne ne viendra plus, quand elle se retire après le délai
    de retrait (P10).
    Destinataires : l'équipe du lieu (Configuration.email) et chaque personne
    encore inscrite sur le même créneau.
    / Tells the venue team and the other volunteers of the same shift that
    someone withdrew after the deadline (P10).

    LOCALISATION : booking/tasks.py

    Appelée par booking/benevolat.py (retirer_une_inscription), après la suppression
    de l'inscription : on reçoit donc le besoin et le nom, pas l'inscription.
    La personne qui se retire n'est donc plus dans les inscrits : elle ne reçoit rien.
    / Called after the sign-up is deleted: the person who withdrew gets nothing.

    UN MAIL PAR DESTINATAIRE : un seul mail adressé à tout le monde montrerait
    l'adresse email de chaque bénévole aux autres.
    / One email per recipient: never expose the volunteers' addresses to each other.

    LE NOM SELON LE DESTINATAIRE : l'équipe du lieu reçoit le nom complet. Les autres
    bénévoles ne reçoivent que le prénom, comme sur le planning public : le mail de
    confirmation leur promet que leur nom n'est pas montré.
    / The team gets the full name; the other volunteers only get the first name.

    :param nom_de_la_personne: « Prénom Nom », pour l'équipe du lieu
    :param prenom_de_la_personne: le prénom public, pour les bénévoles. Absent (tâche
        mise en file avant ce paramètre) : « Une personne ».

    :return: True si au moins un mail est parti
    """
    from booking.benevolat import plage_horaire
    from booking.models import BesoinBenevole

    config = Configuration.get_solo()
    activate(config.language)

    try:
        besoin = BesoinBenevole.objects.select_related("tache", "planning").get(pk=besoin_uuid)
    except BesoinBenevole.DoesNotExist:
        logger.info(f"prevenir_l_equipe_d_un_desistement : besoin {besoin_uuid} absent")
        return False

    if not prenom_de_la_personne:
        prenom_de_la_personne = _("Une personne")

    # Les destinataires, avec le nom que chacun peut voir. Sans doublon ni adresse vide.
    # Une personne inscrite avec l'adresse du lieu reçoit un seul mail : celui de l'équipe.
    # / Recipients with the name each one may see; no duplicates, no empty address.
    destinataires = []
    adresses_deja_prises = []
    if config.email:
        destinataires.append((config.email, nom_de_la_personne))
        adresses_deja_prises.append(config.email)
    else:
        logger.warning("prevenir_l_equipe_d_un_desistement : le lieu n'a pas d'email")

    inscriptions_restantes = besoin.inscriptions.select_related("user")
    for inscription in inscriptions_restantes:
        adresse_de_la_personne = inscription.user.email
        if adresse_de_la_personne and adresse_de_la_personne not in adresses_deja_prises:
            destinataires.append((adresse_de_la_personne, prenom_de_la_personne))
            adresses_deja_prises.append(adresse_de_la_personne)

    if not destinataires:
        return False

    domaine_du_lieu = _domaine_du_lieu()

    au_moins_un_mail_envoye = False
    for adresse_du_destinataire, nom_visible in destinataires:
        title = f"{config.organisation} - " + _("%(nom)s ne pourra pas venir") % {"nom": nom_visible}
        context = {
            'title': title,
            'organisation': config.organisation,
            'besoin': besoin,
            'plage': plage_horaire(besoin),
            'nom_de_la_personne': nom_visible,
            'nombre_inscrits': besoin.nombre_inscrits(),
            # La page publique du planning : l'équipe ET les bénévoles peuvent l'ouvrir.
            # / The public planning page: both the team and the volunteers can open it.
            'url_du_planning': f"https://{domaine_du_lieu}/booking/benevolat/{besoin.planning.slug}/",
        }

        # Un envoi en erreur (adresse refusée, serveur SMTP) ne doit pas priver les
        # destinataires suivants du mail. logger.exception garde la pile d'appels :
        # Sentry la reçoit.
        # / A failing send must not stop the next recipients; Sentry gets the trace.
        try:
            mail = CeleryMailerClass(
                adresse_du_destinataire,
                title,
                template="booking/benevolat/emails/desistement_equipe.html",
                context=context,
            )
            mail.send()
        except Exception:
            logger.exception(
                f"prevenir_l_equipe_d_un_desistement : envoi impossible à {adresse_du_destinataire}"
            )
            continue
        if mail.sended:
            au_moins_un_mail_envoye = True
    return au_moins_un_mail_envoye


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
    Une personne inscrite à plusieurs créneaux demain reçoit UN seul mail qui les liste tous.
    / The current venue's reminders (call inside a tenant_context). One email per person.

    « Demain » = la date de demain DANS LE FUSEAU DU LIEU, pas en UTC.
    Seulement les inscriptions sans rappel (rappel_envoye_le vide), sur un planning
    publié. rappel_envoye_le est rempli juste après un envoi réussi : relancer la tâche
    n'envoie rien deux fois.
    / Tomorrow in the venue timezone. rappel_envoye_le prevents a second send.

    :return: le nombre de mails de rappel envoyés (un par personne)
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
    ).select_related("user", "besoin__tache", "besoin__planning").order_by(
        # Une journée entière (sans heure) passe avant les créneaux horaires.
        # / A whole-day need (no time) comes before timed slots.
        "user_id", F("besoin__heure_debut").asc(nulls_first=True),
    )

    if not inscriptions_a_rappeler.exists():
        return 0

    # Un seul mail par personne, avec tous ses créneaux de demain, dans l'ordre des heures.
    # Le dictionnaire garde l'ordre d'arrivée : celui du order_by ci-dessus.
    # / One email per person, listing all their slots for tomorrow, in time order.
    inscriptions_par_personne = {}
    for inscription in inscriptions_a_rappeler:
        if inscription.user_id not in inscriptions_par_personne:
            inscriptions_par_personne[inscription.user_id] = []
        inscriptions_par_personne[inscription.user_id].append(inscription)

    domaine_du_lieu = _domaine_du_lieu()
    nombre_de_rappels_envoyes = 0
    for inscriptions_de_la_personne in inscriptions_par_personne.values():
        # Un mail qui échoue (adresse refusée, sujet invalide…) est journalisé — donc
        # visible dans Sentry — sans priver les autres bénévoles de leur rappel : la tâche
        # ne repasse que demain, et « demain » aura changé.
        # / A failing email is logged without blocking the others' reminders.
        personne = inscriptions_de_la_personne[0].user
        try:
            # Chaque créneau garde son propre lien « Je ne peux plus venir ».
            # / Each slot keeps its own withdrawal link.
            creneaux = []
            for inscription in inscriptions_de_la_personne:
                creneaux.append({
                    'besoin': inscription.besoin,
                    'plage': plage_horaire(inscription.besoin),
                    'url_de_desistement': (
                        f"https://{domaine_du_lieu}/booking/benevolat/desistement/{jeton_de_desistement(inscription)}/"
                    ),
                })

            if len(creneaux) > 1:
                title = _("Demain : %(nombre)s créneaux. Merci !") % {"nombre": len(creneaux)}
            elif creneaux[0]['besoin'].est_une_journee():
                title = _("Demain : %(tache)s. Merci !") % {"tache": creneaux[0]['besoin'].tache.name}
            else:
                title = _("Demain %(plage)s : %(tache)s. Merci !") % {
                    "plage": creneaux[0]['plage'], "tache": creneaux[0]['besoin'].tache.name,
                }
            context = {
                'title': title,
                'organisation': config.organisation,
                'creneaux': creneaux,
                'url_de_mes_creneaux': f"https://{domaine_du_lieu}/my_account/my_volunteering/",
            }
            mail = CeleryMailerClass(
                personne.email,
                f"{config.organisation} - {title}",
                template="booking/benevolat/emails/rappel.html",
                context=context,
            )
            mail.send()
            if mail.sended:
                pk_des_inscriptions = [inscription.pk for inscription in inscriptions_de_la_personne]
                InscriptionBenevole.objects.filter(pk__in=pk_des_inscriptions).update(rappel_envoye_le=timezone.now())
                nombre_de_rappels_envoyes += 1
            else:
                logger.warning(f"rappel bénévole non envoyé à {personne.email}")
        except Exception:
            logger.exception(f"rappel bénévole en erreur pour {personne.email}")

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
