"""
Administration/recap_quotidien.py
Le récap du matin des admins : ce qui s'est passé la veille, rubrique par rubrique.
/ The admins' morning recap: what happened yesterday, section by section.

LOCALISATION : Administration/recap_quotidien.py

Ce fichier calcule la fenêtre de « la veille » et les rubriques de billetterie,
d'adhésions, de ressources, de bénévolat, d'événements, de financement
participatif, de remboursements et d'annulations.
/ This file computes the "yesterday" window and the ticketing, membership,
resource, volunteer, event, crowdfunding, refund and cancellation sections.

Une rubrique est un dict :
{"cle", "titre", "est_un_stock", "nombre", "nombre_de_nouveaux",
 "lignes", "nombre_de_lignes_cachees", "lien"}.
Une rubrique vide n'existe pas (la fonction rend None).
/ A section is a dict. An empty section does not exist (the function returns None).

Spécification : TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/SPEC.md
"""

from datetime import datetime, time, timedelta, timezone as timezone_de_python

import logging

from django.db import connection
from django.db.models import F
from django.utils.formats import date_format
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    Configuration,
    Event,
    LigneArticle,
    Membership,
    Reservation,
)
from BaseBillet.tasks import CeleryMailerClass
from booking.models import Booking, InscriptionBenevole
from comptabilite.models import ClotureCaisse
from comptabilite.pdf import generer_pdf_cloture
from comptabilite.presentation import (
    euros_a_la_francaise,
    montant_a_la_francaise_dans_l_unite,
)
from crowds.models import (
    BudgetItem,
    Contribution,
    Initiative,
    Participation,
    Vote,
)

logger = logging.getLogger(__name__)

FUSEAU_UTC = timezone_de_python.utc

# Le récap ne part pas avant cette heure (heure du lieu).
# / The recap is not sent before this hour (venue time).
HEURE_D_ENVOI_DU_RECAP = 7

# Au-delà, la rubrique montre « et N autres ».
# / Beyond this, the section shows "and N others".
NOMBRE_DE_LIGNES_MONTREES_PAR_RUBRIQUE = 10


def fenetre_de_la_veille(maintenant, fuseau_du_lieu):
    """
    LOCALISATION : Administration/recap_quotidien.py

    [veille 00:00, aujourd'hui 00:00[ en heure du lieu, rendus en UTC.
    On compte minuit à minuit en heure locale, puis on convertit : la veille d'un
    changement d'heure dure donc 23 h ou 25 h.
    / [yesterday 00:00, today 00:00[ in venue time, returned in UTC.
    """
    aujourd_hui = timezone.localtime(maintenant, fuseau_du_lieu).date()
    hier = aujourd_hui - timedelta(days=1)
    debut = datetime.combine(hier, time(0), tzinfo=fuseau_du_lieu)
    fin = datetime.combine(aujourd_hui, time(0), tzinfo=fuseau_du_lieu)
    return debut.astimezone(FUSEAU_UTC), fin.astimezone(FUSEAU_UTC)


def _construire_la_rubrique(
    cle,
    titre,
    lien,
    ensemble,
    champ_de_date,
    fonction_de_ligne,
    debut,
    fin,
    est_un_stock=False,
):
    """
    LOCALISATION : Administration/recap_quotidien.py

    Transforme un ensemble d'objets en dict de rubrique, ou None s'il est vide.
    `ensemble` est déjà filtré ; pour un stock c'est tout le stock, et les
    « nouveaux » sont ceux dont `champ_de_date` tombe dans la fenêtre.
    / Turns a queryset into a section dict, or None when empty.
    """
    ensemble = ensemble.order_by(F(champ_de_date).desc(nulls_last=True), "-pk")
    nombre = ensemble.count()
    if nombre == 0:
        return None

    if est_un_stock:
        filtre_de_la_fenetre = {
            f"{champ_de_date}__gte": debut,
            f"{champ_de_date}__lt": fin,
        }
        nombre_de_nouveaux = ensemble.filter(**filtre_de_la_fenetre).count()
    else:
        nombre_de_nouveaux = nombre

    lignes = []
    for objet in ensemble[:NOMBRE_DE_LIGNES_MONTREES_PAR_RUBRIQUE]:
        lignes.append(fonction_de_ligne(objet))

    return _dict_de_la_rubrique(
        cle, titre, est_un_stock, nombre, nombre_de_nouveaux, lignes, lien
    )


def _dict_de_la_rubrique(
    cle, titre, est_un_stock, nombre, nombre_de_nouveaux, lignes, lien
):
    """
    LOCALISATION : Administration/recap_quotidien.py

    Le dict d'une rubrique. `lignes` contient déjà les lignes montrées (10 au plus).
    / The section dict. `lignes` already holds the shown lines (10 at most).
    """
    return {
        "cle": cle,
        "titre": titre,
        "est_un_stock": est_un_stock,
        "nombre": nombre,
        "nombre_de_nouveaux": nombre_de_nouveaux,
        "lignes": lignes,
        "nombre_de_lignes_cachees": nombre - len(lignes),
        "lien": lien,
    }


def _nom_de_la_personne(utilisateur, prenom=None, nom=None):
    """
    Prénom + nom, sinon e-mail, sinon « (sans nom) ». Ne plante jamais sur None.
    / First + last name, else e-mail, else "(no name)". Never fails on None.
    """
    nom_complet = f"{prenom or ''} {nom or ''}".strip()
    if nom_complet:
        return nom_complet
    if utilisateur is not None:
        nom_de_l_utilisateur = (
            f"{utilisateur.first_name or ''} {utilisateur.last_name or ''}".strip()
        )
        if nom_de_l_utilisateur:
            return nom_de_l_utilisateur
        if utilisateur.email:
            return utilisateur.email
    return _("(sans nom)")


def _ligne_d_une_adhesion(adhesion):
    """
    Une ligne : personne, produit, statut.
    / One line: person, product, status.
    """
    personne = _nom_de_la_personne(
        adhesion.user, adhesion.first_name, adhesion.last_name
    )
    produit = _("(sans nom)")
    if adhesion.price is not None:
        produit = adhesion.price.product.name
    return f"{personne} — {produit} — {adhesion.get_status_display()}"


def _ligne_d_une_reservation(reservation):
    """
    Une ligne : personne, événement, statut.
    / One line: person, event, status.
    """
    personne = _nom_de_la_personne(reservation.user_commande)
    evenement = reservation.event.name if reservation.event else _("(sans nom)")
    return f"{personne} — {evenement} — {reservation.get_status_display()}"


def _ligne_d_un_booking(booking):
    """
    Une ligne : personne, ressource, statut.
    / One line: person, resource, status.
    """
    personne = _nom_de_la_personne(booking.user, booking.first_name, booking.last_name)
    return f"{personne} — {booking.resource.name} — {booking.get_status_display()}"


def _ligne_d_une_inscription(inscription):
    """
    Une ligne : bénévole, tâche, date du besoin.
    / One line: volunteer, task, need date.
    """
    personne = _nom_de_la_personne(inscription.user)
    return f"{personne} — {inscription.besoin.tache.name} — {date_format(inscription.besoin.date, 'SHORT_DATE_FORMAT')}"


def _etat_d_un_evenement(evenement):
    """
    L'état d'un événement : proposition, publié ou brouillon.
    / An event's state: proposal, published or draft.
    """
    if evenement.is_proposal and not evenement.published:
        return _("proposition en attente")
    if evenement.published:
        return _("publié")
    return _("brouillon")


def _ligne_d_un_evenement(evenement):
    """
    Une ligne : nom et état de l'événement.
    / One line: event name and state.
    """
    return f"{evenement.name or _('(sans nom)')} — {_etat_d_un_evenement(evenement)}"


def _ligne_d_une_proposition(evenement):
    """
    Une ligne : le nom de la proposition.
    / One line: the proposal's name.
    """
    return evenement.name or _("(sans nom)")


def _rubrique_nouvelles_adhesions(debut, fin, domaine):
    """
    Adhésions créées hier, hors statuts non aboutis ou annulés.
    / Memberships created yesterday, without unfinished or cancelled ones.
    """
    adhesions = Membership.objects.filter(
        date_added__gte=debut, date_added__lt=fin
    ).exclude(
        status__in=[
            Membership.WAITING_PAYMENT,
            Membership.CANCELED,
            Membership.ADMIN_CANCELED,
            Membership.ADMIN_WAITING,
        ]
    )
    return _construire_la_rubrique(
        "nouvelles_adhesions",
        _("Nouvelles adhésions"),
        f"https://{domaine}/admin/BaseBillet/membership/",
        adhesions.select_related("user", "price__product"),
        "date_added",
        _ligne_d_une_adhesion,
        debut,
        fin,
    )


def _rubrique_adhesions_en_attente(debut, fin, domaine):
    """
    Stock des demandes d'adhésion à valider.
    / Stock of membership requests awaiting validation.
    """
    adhesions = Membership.objects.filter(status=Membership.ADMIN_WAITING)
    return _construire_la_rubrique(
        "adhesions_en_attente",
        _("Demandes d'adhésion en attente"),
        f"https://{domaine}/admin/BaseBillet/membership/",
        adhesions.select_related("user", "price__product"),
        "date_added",
        _ligne_d_une_adhesion,
        debut,
        fin,
        est_un_stock=True,
    )


def _rubrique_nouvelles_reservations(debut, fin, domaine):
    """
    Réservations de billets créées hier, hors statuts non aboutis ou annulés.
    / Ticket bookings created yesterday, without unfinished or cancelled ones.
    """
    reservations = Reservation.objects.filter(
        created_at__gte=debut, created_at__lt=fin
    ).exclude(
        status__in=[Reservation.CREATED, Reservation.UNPAID, Reservation.CANCELED]
    )
    return _construire_la_rubrique(
        "nouvelles_reservations",
        _("Nouvelles réservations"),
        f"https://{domaine}/admin/BaseBillet/reservation/",
        reservations.select_related("user_commande", "event"),
        "created_at",
        _ligne_d_une_reservation,
        debut,
        fin,
    )


def _rubrique_nouvelles_reservations_de_ressources(debut, fin, domaine):
    """
    Réservations de ressources faites hier, hors statuts non aboutis ou annulés.
    / Resource bookings made yesterday, without unfinished or cancelled ones.

    Une demande à valider (ADMIN_WAITING) n'est pas une réservation :
    elle a sa propre rubrique, `_rubrique_demandes_de_reservation_en_attente`.
    / A request awaiting validation is not a booking: it has its own section.
    """
    bookings = Booking.objects.filter(booked_at__gte=debut, booked_at__lt=fin).exclude(
        status__in=[
            Booking.WAITING_PAYMENT,
            Booking.ADMIN_WAITING,
            Booking.ADMIN_CANCELED,
            Booking.USER_CANCELED,
        ]
    )
    return _construire_la_rubrique(
        "nouvelles_reservations_de_ressources",
        _("Nouvelles réservations de ressources"),
        f"https://{domaine}/admin/booking/booking/",
        bookings.select_related("user", "resource"),
        "booked_at",
        _ligne_d_un_booking,
        debut,
        fin,
    )


def _rubrique_demandes_de_reservation_en_attente(debut, fin, domaine):
    """
    Stock des demandes de réservation de ressources à valider.
    / Stock of resource booking requests awaiting validation.

    Le lien ouvre la liste des réservations filtrée sur ce statut.
    / The link opens the booking list filtered on this status.
    """
    demandes = Booking.objects.filter(status=Booking.ADMIN_WAITING)
    return _construire_la_rubrique(
        "demandes_de_reservation_en_attente",
        _("Demandes de réservation en attente"),
        f"https://{domaine}/admin/booking/booking/?status__exact={Booking.ADMIN_WAITING}",
        demandes.select_related("user", "resource"),
        "booked_at",
        _ligne_d_un_booking,
        debut,
        fin,
        est_un_stock=True,
    )


def _rubrique_nouvelles_inscriptions_benevoles(debut, fin, domaine):
    """
    Inscriptions de bénévoles faites hier.
    / Volunteer sign-ups made yesterday.
    """
    inscriptions = InscriptionBenevole.objects.filter(
        created_at__gte=debut, created_at__lt=fin
    )
    return _construire_la_rubrique(
        "nouvelles_inscriptions_benevoles",
        _("Nouvelles inscriptions de bénévoles"),
        f"https://{domaine}/admin/booking/inscriptionbenevole/",
        inscriptions.select_related("user", "besoin__tache"),
        "created_at",
        _ligne_d_une_inscription,
        debut,
        fin,
    )


def _rubrique_nouveaux_evenements(debut, fin, domaine):
    """
    Événements créés hier, avec leur état.
    / Events created yesterday, with their state.
    """
    # Les sous-événements et les actions s'affichent dans leur événement parent,
    # comme dans l'admin des événements : on ne les compte pas à part.
    # / Sub-events and actions show inside their parent event, as in the event admin.
    evenements = (
        Event.objects.filter(created_at__gte=debut, created_at__lt=fin)
        .exclude(categorie=Event.ACTION)
        .exclude(parent__isnull=False)
    )
    return _construire_la_rubrique(
        "nouveaux_evenements",
        _("Nouveaux événements"),
        f"https://{domaine}/admin/BaseBillet/event/",
        evenements,
        "created_at",
        _ligne_d_un_evenement,
        debut,
        fin,
    )


def _rubrique_propositions_en_attente(debut, fin, domaine):
    """
    Stock des propositions d'événements à valider.
    / Stock of event proposals awaiting validation.
    """
    propositions = Event.objects.filter(is_proposal=True, published=False)
    return _construire_la_rubrique(
        "propositions_en_attente",
        _("Propositions d'événements en attente"),
        f"https://{domaine}/admin/BaseBillet/event/",
        propositions,
        "created_at",
        _ligne_d_une_proposition,
        debut,
        fin,
        est_un_stock=True,
    )


def _montant_dans_la_devise_du_projet(montant_en_centiemes, projet):
    """
    Le montant écrit dans la devise du projet : « € » (ou vide) donne des euros,
    toute autre devise (« heures », une monnaie locale...) est écrite telle quelle.
    / The amount written in the project's currency: "€" or empty gives euros.
    """
    devise = (projet.currency or "").strip()
    if devise == "€":
        devise = ""
    return montant_a_la_francaise_dans_l_unite(montant_en_centiemes, devise)


def _ligne_d_un_projet(projet):
    """
    Une ligne : le nom du projet.
    / One line: the project's name.
    """
    return projet.name or _("(sans nom)")


def _ligne_d_une_ligne_de_budget(ligne_de_budget):
    """
    Une ligne : projet, description, montant demandé, état.
    / One line: project, description, requested amount, state.
    """
    description = (ligne_de_budget.description or "").strip() or _("(sans nom)")
    montant = _montant_dans_la_devise_du_projet(
        ligne_de_budget.amount, ligne_de_budget.initiative
    )
    etat = ligne_de_budget.get_state_display()
    return f"{ligne_de_budget.initiative.name} — {description} — {montant} — {etat}"


def _ligne_d_une_contribution(contribution):
    """
    Une ligne : contributeur, projet, montant payé, statut du paiement.
    / One line: contributor, project, paid amount, payment status.
    """
    personne = _nom_de_la_personne(
        contribution.contributor, contribution.contributor_name
    )
    montant = _montant_dans_la_devise_du_projet(
        contribution.amount, contribution.initiative
    )
    statut = contribution.get_payment_status_display()
    return f"{personne} — {contribution.initiative.name} — {montant} — {statut}"


def _ligne_d_un_vote(vote):
    """
    Une ligne : votant, projet.
    / One line: voter, project.
    """
    personne = _nom_de_la_personne(vote.user)
    return f"{personne} — {vote.initiative.name}"


def _ligne_d_une_participation(participation):
    """
    Une ligne : participant, projet, état.
    / One line: participant, project, state.
    """
    personne = _nom_de_la_personne(participation.participant)
    etat = participation.get_state_display()
    return f"{personne} — {participation.initiative.name} — {etat}"


def _nom_de_l_objet_rembourse(ligne_article):
    """
    Le nom de ce qui a été remboursé : événement, produit d'adhésion, ressource,
    sinon produit de la ligne (article de caisse).
    / Name of what was refunded: event, membership product, resource, else the
    line's product (register item).
    """
    if ligne_article.reservation is not None:
        if ligne_article.reservation.event is not None:
            return ligne_article.reservation.event.name
    if ligne_article.membership is not None:
        if ligne_article.membership.price is not None:
            return ligne_article.membership.price.product.name
    if ligne_article.booking is not None:
        return ligne_article.booking.resource.name
    produit_vendu = ligne_article.pricesold.productsold
    return produit_vendu.product.name or _("(sans nom)")


def _ligne_d_un_remboursement(ligne_article):
    """
    Une ligne : objet remboursé, argent rendu. Le total_ttc d'un avoir est négatif
    (en centimes) : on écrit l'argent rendu, en positif.
    / One line: refunded object, money given back (total_ttc is negative cents).
    """
    nom = _nom_de_l_objet_rembourse(ligne_article)
    argent_rendu = euros_a_la_francaise(-ligne_article.total_ttc)
    return f"{nom} — {argent_rendu}"


def _rubrique_nouveaux_projets(debut, fin, domaine):
    """
    Projets de financement participatif créés hier.
    / Crowdfunding projects created yesterday.
    """
    projets = Initiative.objects.filter(created_at__gte=debut, created_at__lt=fin)
    return _construire_la_rubrique(
        "nouveaux_projets",
        _("Nouveaux projets"),
        f"https://{domaine}/admin/crowds/initiative/",
        projets,
        "created_at",
        _ligne_d_un_projet,
        debut,
        fin,
    )


def _rubrique_nouvelles_lignes_de_budget(debut, fin, domaine):
    """
    Lignes de budget proposées hier.
    / Budget lines proposed yesterday.
    """
    lignes_de_budget = BudgetItem.objects.filter(
        created_at__gte=debut, created_at__lt=fin
    )
    return _construire_la_rubrique(
        "nouvelles_lignes_de_budget",
        _("Nouvelles lignes de budget"),
        f"https://{domaine}/admin/crowds/initiative/",
        lignes_de_budget.select_related("initiative"),
        "created_at",
        _ligne_d_une_ligne_de_budget,
        debut,
        fin,
    )


def _rubrique_lignes_de_budget_en_attente(debut, fin, domaine):
    """
    Stock des lignes de budget à valider.
    / Stock of budget lines awaiting validation.
    """
    lignes_de_budget = BudgetItem.objects.filter(state=BudgetItem.State.REQUESTED)
    return _construire_la_rubrique(
        "lignes_de_budget_en_attente",
        _("Lignes de budget en attente"),
        f"https://{domaine}/admin/crowds/initiative/",
        lignes_de_budget.select_related("initiative"),
        "created_at",
        _ligne_d_une_ligne_de_budget,
        debut,
        fin,
        est_un_stock=True,
    )


def _rubrique_contributions_payees(debut, fin, domaine):
    """
    Contributions payées hier (la date de paiement compte, pas celle de création).
    / Contributions paid yesterday (the payment date counts, not the creation date).
    """
    contributions = Contribution.objects.filter(
        paid_at__gte=debut,
        paid_at__lt=fin,
        payment_status__in=[
            Contribution.PaymentStatus.PAID,
            Contribution.PaymentStatus.PAID_ADMIN,
        ],
    )
    return _construire_la_rubrique(
        "contributions_payees",
        _("Contributions payées"),
        f"https://{domaine}/admin/crowds/initiative/",
        contributions.select_related("contributor", "initiative"),
        "paid_at",
        _ligne_d_une_contribution,
        debut,
        fin,
    )


def _rubrique_nouveaux_votes(debut, fin, domaine):
    """
    Votes donnés hier.
    / Votes cast yesterday.
    """
    votes = Vote.objects.filter(created_at__gte=debut, created_at__lt=fin)
    return _construire_la_rubrique(
        "nouveaux_votes",
        _("Nouveaux votes"),
        f"https://{domaine}/admin/crowds/initiative/",
        votes.select_related("user", "initiative"),
        "created_at",
        _ligne_d_un_vote,
        debut,
        fin,
    )


def _rubrique_nouvelles_participations(debut, fin, domaine):
    """
    Participations demandées hier.
    / Participations requested yesterday.
    """
    participations = Participation.objects.filter(
        created_at__gte=debut, created_at__lt=fin
    )
    return _construire_la_rubrique(
        "nouvelles_participations",
        _("Nouvelles participations"),
        f"https://{domaine}/admin/crowds/initiative/",
        participations.select_related("participant", "initiative"),
        "created_at",
        _ligne_d_une_participation,
        debut,
        fin,
    )


def _rubrique_participations_en_attente(debut, fin, domaine):
    """
    Stock des participations à valider.
    / Stock of participations awaiting validation.
    """
    participations = Participation.objects.filter(state=Participation.State.REQUESTED)
    return _construire_la_rubrique(
        "participations_en_attente",
        _("Participations en attente"),
        f"https://{domaine}/admin/crowds/initiative/",
        participations.select_related("participant", "initiative"),
        "created_at",
        _ligne_d_une_participation,
        debut,
        fin,
        est_un_stock=True,
    )


def _rubrique_remboursements(debut, fin, domaine):
    """
    Remboursements et avoirs écrits hier : l'argent rendu, pas le prix catalogue.
    / Refunds and credit notes written yesterday: the money given back.
    """
    lignes_d_avoir = LigneArticle.objects.filter(
        datetime__gte=debut,
        datetime__lt=fin,
        status__in=[LigneArticle.REFUNDED, LigneArticle.CREDIT_NOTE],
    )
    return _construire_la_rubrique(
        "remboursements",
        _("Remboursements"),
        f"https://{domaine}/admin/BaseBillet/vente/",
        lignes_d_avoir.select_related(
            "reservation__event",
            "membership__price__product",
            "booking__resource",
            "pricesold__productsold__product",
        ),
        "datetime",
        _ligne_d_un_remboursement,
        debut,
        fin,
    )


def _identifiants_rembourses(nom_du_champ_de_lien, objets):
    """
    Parmi `objets`, les identifiants qui ont une ligne REFUNDED ou CREDIT_NOTE.
    Une seule requête pour tous les objets d'un type.
    / Among `objets`, the ids with a REFUNDED or CREDIT_NOTE line. One query per type.
    """
    identifiants = [objet.pk for objet in objets]
    if not identifiants:
        return set()
    filtre = {f"{nom_du_champ_de_lien}__in": identifiants}
    lignes = LigneArticle.objects.filter(
        status__in=[LigneArticle.REFUNDED, LigneArticle.CREDIT_NOTE], **filtre
    )
    return set(lignes.values_list(nom_du_champ_de_lien, flat=True))


def _rubrique_annulations(debut, fin, domaine):
    """
    Réservations, réservations de ressources et adhésions annulées hier.
    Une ligne est marquée « remboursé » s'il existe un avoir ou un remboursement.
    / Reservations, resource bookings and memberships cancelled yesterday.
    A line is marked "refunded" when a credit note or refund exists.
    """
    fenetre = {"annulee_le__gte": debut, "annulee_le__lt": fin}
    reservations = list(
        Reservation.objects.filter(**fenetre).select_related("user_commande", "event")
    )
    bookings = list(
        Booking.objects.filter(**fenetre).select_related("user", "resource")
    )
    adhesions = list(
        Membership.objects.filter(**fenetre).select_related("user", "price__product")
    )

    # Chaque élément : (objet, fonction de ligne, champ de lien vers LigneArticle).
    # / Each item: (object, line function, link field to LigneArticle).
    toutes_les_annulations = []
    for reservation in reservations:
        toutes_les_annulations.append(
            (reservation, _ligne_d_une_reservation, "reservation_id")
        )
    for booking in bookings:
        toutes_les_annulations.append((booking, _ligne_d_un_booking, "booking_id"))
    for adhesion in adhesions:
        toutes_les_annulations.append(
            (adhesion, _ligne_d_une_adhesion, "membership_id")
        )

    nombre = len(toutes_les_annulations)
    if nombre == 0:
        return None

    # Les plus récentes d'abord. Le tri de Python est stable : à égalité exacte,
    # l'ordre reste réservations, ressources, adhésions.
    # / Most recent first. Python's sort is stable: on an exact tie, the order stays
    # reservations, resources, memberships.
    toutes_les_annulations.sort(key=lambda element: element[0].annulee_le, reverse=True)
    lignes_montrees = toutes_les_annulations[:NOMBRE_DE_LIGNES_MONTREES_PAR_RUBRIQUE]

    # Les objets montrés, rangés par champ de lien : une requête « remboursé » par type.
    # / The shown objects, grouped by link field: one "refunded" query per type.
    objets_montres_par_champ = {
        "reservation_id": [],
        "booking_id": [],
        "membership_id": [],
    }
    for objet, fonction_de_ligne, champ_de_lien in lignes_montrees:
        objets_montres_par_champ[champ_de_lien].append(objet)

    rembourses_par_champ = {}
    for champ_de_lien, objets in objets_montres_par_champ.items():
        rembourses_par_champ[champ_de_lien] = _identifiants_rembourses(
            champ_de_lien, objets
        )

    lignes = []
    for objet, fonction_de_ligne, champ_de_lien in lignes_montrees:
        texte = fonction_de_ligne(objet)
        if objet.pk in rembourses_par_champ[champ_de_lien]:
            texte = f"{texte} — {_('remboursé')}"
        lignes.append(texte)

    # Le lien reste la liste des réservations : la rubrique mêle réservations,
    # réservations de ressources et adhésions, et aucune liste ne les réunit.
    # / The link stays the reservations list: the section mixes three models and
    # no single admin list holds them all.
    return _dict_de_la_rubrique(
        "annulations",
        _("Annulations"),
        False,
        nombre,
        nombre,
        lignes,
        f"https://{domaine}/admin/BaseBillet/reservation/",
    )


def rubriques_de_la_veille(debut, fin, domaine):
    """
    LOCALISATION : Administration/recap_quotidien.py

    Les rubriques NON VIDES, dans l'ordre du tableau de la spec.
    / The NON-EMPTY sections, in the spec's table order.
    """
    fonctions_des_rubriques = [
        _rubrique_nouvelles_adhesions,
        _rubrique_adhesions_en_attente,
        _rubrique_nouvelles_reservations,
        _rubrique_nouvelles_reservations_de_ressources,
        _rubrique_demandes_de_reservation_en_attente,
        _rubrique_nouvelles_inscriptions_benevoles,
        _rubrique_nouveaux_evenements,
        _rubrique_propositions_en_attente,
        _rubrique_nouveaux_projets,
        _rubrique_nouvelles_lignes_de_budget,
        _rubrique_lignes_de_budget_en_attente,
        _rubrique_contributions_payees,
        _rubrique_nouveaux_votes,
        _rubrique_nouvelles_participations,
        _rubrique_participations_en_attente,
        _rubrique_remboursements,
        _rubrique_annulations,
    ]
    rubriques = []
    for fonction_de_la_rubrique in fonctions_des_rubriques:
        rubrique = fonction_de_la_rubrique(debut, fin, domaine)
        if rubrique is not None:
            rubriques.append(rubrique)
    return rubriques


def clotures_j_a_joindre(seuil_de_la_veille, seuil_d_aujourd_hui):
    """
    LOCALISATION : Administration/recap_quotidien.py

    Les clôtures J à joindre au récap : celles qui finissent après le seuil de la
    veille et au plus tard au seuil d'aujourd'hui (la J du filet finit PILE au seuil,
    la borne haute est donc incluse). Une J qui finit à ou avant la mise en service
    de la comptabilité du lieu n'est pas jointe. Ordre : numéro croissant.
    / The J closures to attach: seuil_de_la_veille < end <= seuil_d_aujourd_hui,
    except those ending at or before the go-live. Ordered by number.
    """
    # Import local : comptabilite.tasks importe le récap (appel en fin de tâche).
    # / Local import: comptabilite.tasks imports the recap.
    from comptabilite.tasks import mise_en_service_du_lieu

    clotures_du_niveau_j = ClotureCaisse.objects.filter(
        niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        datetime_fin__gt=seuil_de_la_veille,
        datetime_fin__lte=seuil_d_aujourd_hui,
    )

    mise_en_service = mise_en_service_du_lieu()
    if mise_en_service is not None:
        clotures_du_niveau_j = clotures_du_niveau_j.filter(
            datetime_fin__gt=mise_en_service
        )

    return list(clotures_du_niveau_j.order_by("numero_sequentiel"))


def le_recap_a_du_contenu(rubriques, clotures):
    """
    LOCALISATION : Administration/recap_quotidien.py

    Vrai s'il y a au moins un Z, ou une rubrique qui n'est pas un stock, ou un stock
    avec au moins un nouveau. Un stock sans nouveau ne déclenche pas le mail à lui seul.
    / True if there is a Z, a non-stock section, or a stock with new items.
    """
    if len(clotures) > 0:
        return True

    for rubrique in rubriques:
        if not rubrique["est_un_stock"]:
            return True
        if rubrique["nombre_de_nouveaux"] > 0:
            return True

    return False


def destinataires_du_recap(tenant, configuration):
    """
    LOCALISATION : Administration/recap_quotidien.py

    Les admins du lieu ; s'il n'y en a aucun, l'email du lieu. Plus les adresses de
    `rapport_emails` quand la périodicité du rapport est journalière. Minuscules,
    sans espaces, sans doublon, dans l'ordre d'apparition.
    / Venue admins (or the venue e-mail if none), plus `rapport_emails` when the
    report periodicity is daily. Lowercase, trimmed, no duplicates, in order.
    """
    # Les adresses des admins sont nettoyées d'abord : le repli sur l'email du lieu
    # dépend de cette liste propre, pas de la liste brute.
    # / Admin addresses are cleaned first: the fallback depends on the cleaned list.
    destinataires = []
    for administrateur in TibilletUser.objects.filter(client_admin=tenant):
        adresse = (administrateur.email or "").strip().lower()
        if adresse and adresse not in destinataires:
            destinataires.append(adresse)

    if len(destinataires) == 0:
        adresse = (configuration.email or "").strip().lower()
        if adresse:
            destinataires.append(adresse)

    if configuration.rapport_periodicite == Configuration.PERIODICITE_JOURNALIER:
        for adresse_saisie in (configuration.rapport_emails or "").split(","):
            adresse = adresse_saisie.strip().lower()
            if adresse and adresse not in destinataires:
                destinataires.append(adresse)

    return destinataires


def preparer_le_recap_du_lieu(maintenant, borne_basse_des_z, borne_haute_des_z):
    """
    LOCALISATION : Administration/recap_quotidien.py

    Calcule le récap du lieu courant, sans rien écrire ni envoyer.
    Rend None s'il n'y a pas de contenu, sinon un dict : configuration,
    date_de_la_veille, rubriques, clotures, destinataires.
    Les titres des rubriques sont écrits dans la langue du lieu.
    / Computes the current venue's recap, writes and sends nothing. Returns None
    when there is no content.
    """
    tenant = connection.tenant
    configuration = Configuration.get_solo()
    fuseau_du_lieu = configuration.get_tzinfo()
    domaine = tenant.get_primary_domain().domain

    debut, fin = fenetre_de_la_veille(maintenant, fuseau_du_lieu)
    date_de_la_veille = timezone.localtime(debut, fuseau_du_lieu).date()

    with translation.override(configuration.language):
        rubriques = rubriques_de_la_veille(debut, fin, domaine)

    clotures = clotures_j_a_joindre(borne_basse_des_z, borne_haute_des_z)

    if not le_recap_a_du_contenu(rubriques, clotures):
        return None

    return {
        "configuration": configuration,
        "domaine": domaine,
        "date_de_la_veille": date_de_la_veille,
        "rubriques": rubriques,
        "clotures": clotures,
        "destinataires": destinataires_du_recap(tenant, configuration),
    }


def envoyer_le_recap(recap):
    """
    LOCALISATION : Administration/recap_quotidien.py

    Sans destinataire : un avertissement, False. Sinon les PDF des Z, puis le mail
    (rendu dans la langue du lieu). Rend True si le mail est parti, False sinon.
    / No recipient: a warning, False. Otherwise the Z PDFs, then the mail. True if the mail went out.
    """
    configuration = recap["configuration"]
    destinataires = recap["destinataires"]

    if len(destinataires) == 0:
        logger.warning(
            f"Récap quotidien : aucun destinataire pour {configuration.organisation}, "
            "aucun mail envoyé."
        )
        return False

    # Les PDF ne sont fabriqués qu'ici, une fois sûr qu'un mail part.
    # / PDFs are only built here, once a mail is certain to be sent.
    fuseau_du_lieu = configuration.get_tzinfo()
    clotures_pour_le_gabarit = []
    fichiers_joints = {}
    for cloture in recap["clotures"]:
        octets_du_pdf, nom_du_fichier, _type_du_fichier = generer_pdf_cloture(cloture)
        fichiers_joints[nom_du_fichier] = octets_du_pdf
        fin_en_heure_du_lieu = timezone.localtime(cloture.datetime_fin, fuseau_du_lieu)
        clotures_pour_le_gabarit.append(
            {
                "numero_sequentiel": cloture.numero_sequentiel,
                "chiffre_affaires_ttc_en_euros": euros_a_la_francaise(
                    cloture.total_general
                ),
                "nombre_transactions": cloture.nombre_transactions,
                "fin_en_heure_du_lieu": fin_en_heure_du_lieu.strftime("%d/%m/%Y %H:%M"),
            }
        )

    domaine = recap["domaine"]
    date_de_la_veille = recap["date_de_la_veille"].strftime("%d/%m/%Y")

    with translation.override(configuration.language):
        titre_du_mail = f"[{configuration.organisation}] " + _(
            "Le récap du %(date)s"
        ) % {"date": date_de_la_veille}
        image_url = "https://tibillet.coop/static/assets/logo-couleur.svg"
        if configuration.img:
            image_url = f"https://{domaine}{configuration.img.med.url}"
        contexte = {
            "config": configuration,
            "date_de_la_veille": date_de_la_veille,
            "rubriques": recap["rubriques"],
            "clotures": clotures_pour_le_gabarit,
            "lien_admin": f"https://{domaine}/admin/",
            "title": titre_du_mail,
            "objet": _("Le récap du matin"),
            "now": timezone.now(),
            "image_url": image_url,
        }
        mailer = CeleryMailerClass(
            email=destinataires,
            title=titre_du_mail,
            template="emails/recap_quotidien.html",
            context=contexte,
            attached_files=fichiers_joints,
        )
        mail_envoye = mailer.send()
    return bool(mail_envoye)


def envoyer_le_recap_du_lieu_si_c_est_l_heure(seuil_de_la_veille, seuil_d_aujourd_hui):
    """
    LOCALISATION : Administration/recap_quotidien.py

    Appelée par comptabilite/tasks.py dans le tenant_context du lieu. Le récap part
    s'il est 7 h passées (heure du lieu), si le seuil d'aujourd'hui est passé et s'il
    n'a pas déjà été traité aujourd'hui. Rend True si un mail est parti.
    / Called from comptabilite/tasks.py inside the venue's tenant_context.
    """
    configuration = Configuration.get_solo()
    maintenant = timezone.now()
    maintenant_local = timezone.localtime(maintenant, configuration.get_tzinfo())

    if maintenant_local.hour < HEURE_D_ENVOI_DU_RECAP:
        return False
    if maintenant < seuil_d_aujourd_hui:
        return False
    # Le marqueur est lu par une requête : get_solo() est en cache.
    # / The marker is read by a query: get_solo() is cached.
    deja_traite_aujourd_hui = Configuration.objects.filter(
        pk=configuration.pk, recap_quotidien_traite_le=maintenant_local.date()
    ).exists()
    if deja_traite_aujourd_hui:
        return False

    recap = preparer_le_recap_du_lieu(
        maintenant, seuil_de_la_veille, seuil_d_aujourd_hui
    )

    # Jamais configuration.save() : il appelle Stripe. Le marqueur est posé avant
    # l'envoi : un mail perdu vaut mieux qu'un doublon chaque heure.
    # / Never configuration.save(): it calls Stripe. Marker set before sending.
    # Le filtre exclude() rend la pose atomique : si une autre sous-tâche a posé le
    # marqueur entre la lecture et ici, 0 ligne change et on n'envoie rien.
    # / exclude() makes the set atomic: 0 rows changed = another sub-task took it.
    nombre_de_lignes = (
        Configuration.objects.filter(pk=configuration.pk)
        .exclude(recap_quotidien_traite_le=maintenant_local.date())
        .update(recap_quotidien_traite_le=maintenant_local.date())
    )
    Configuration.clear_cache()
    if nombre_de_lignes == 0:
        return False

    if recap is None:
        return False

    return envoyer_le_recap(recap)
