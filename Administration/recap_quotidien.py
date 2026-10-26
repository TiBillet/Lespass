"""
Administration/recap_quotidien.py
Le récap du matin des admins : ce qui s'est passé la veille, rubrique par rubrique.
/ The admins' morning recap: what happened yesterday, section by section.

LOCALISATION : Administration/recap_quotidien.py

Ce fichier calcule la fenêtre de « la veille » et les rubriques : demandes à
valider, ruptures de stock, adhésions, réservations, ressources, bénévolat,
événements, financement participatif, annulations et remboursements.
Tout objet d'une rubrique est né (ou a changé d'état) pendant la veille.
Il calcule aussi les compteurs sans détail des rapports de clôture H et M
(`compteurs_de_la_periode`, appelée par comptabilite/tasks.py).
/ This file computes the "yesterday" window, the sections, and the detail-free
counters of the weekly and monthly closure reports.

Une rubrique est un dict :
{"cle", "titre", "nombre", "lignes", "nombre_de_lignes_cachees", "lien"}.
Une rubrique vide n'existe pas (la fonction rend None).
/ A section is a dict. An empty section does not exist (the function returns None).

Spécifications : TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/SPEC.md (chantier 01)
et TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/CHANTIER-02-recap-allege.md (chantier 02).
"""

from datetime import datetime, time, timedelta, timezone as timezone_de_python

import logging

from django.db import connection
from django.db.models import F
from django.utils.formats import date_format
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from BaseBillet.models import (
    Configuration,
    Event,
    LigneArticle,
    Membership,
    Reservation,
)
from BaseBillet.tasks import CeleryMailerClass
from booking.models import Booking, InscriptionBenevole
from comptabilite.models import ClotureCaisse, ConfigurationDesRapports
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
from inventaire.models import MouvementStock, TypeMouvement

logger = logging.getLogger(__name__)

FUSEAU_UTC = timezone_de_python.utc

# Le récap ne part pas avant cette heure (heure du lieu).
# / The recap is not sent before this hour (venue time).
HEURE_D_ENVOI_DU_RECAP = 7

# Au-delà, la rubrique montre « et N autres ».
# / Beyond this, the section shows "and N others".
NOMBRE_DE_LIGNES_MONTREES_PAR_RUBRIQUE = 5

# Les statuts « normaux » : ils ne sont pas écrits sur la ligne, le titre de la
# rubrique les dit déjà. Tout autre statut est écrit (par défaut, on informe).
# ADMIN_WAITING est normal : c'est le statut de toute la rubrique « en attente »,
# et les rubriques « nouvelles » l'excluent.
# / "Normal" statuses are not written on the line. Any other status is written.
STATUTS_NORMAUX_D_UNE_ADHESION = [
    Membership.ONCE,
    Membership.AUTO,
    Membership.ADMIN,
    Membership.LABOUTIK,
    Membership.ADMIN_WAITING,
]
STATUTS_NORMAUX_D_UNE_RESERVATION = [
    Reservation.VALID,
    Reservation.PAID,
    Reservation.FREERES_USERACTIV,
]
STATUTS_NORMAUX_D_UN_BOOKING = [
    Booking.PAID_BY_USER,
    Booking.NO_ADMIN_VALID,
    Booking.FREERES_USERACTIV,
    Booking.ADMIN_WAITING,
]

# Les lignes d'avoir : un remboursement ou un avoir écrit.
# / Credit lines: a written refund or credit note.
STATUTS_DES_LIGNES_D_AVOIR = [LigneArticle.REFUNDED, LigneArticle.CREDIT_NOTE]


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


# ---------------------------------------------------------------------------
# Les sources : un ensemble filtré sur [debut, fin[ par source.
# Le récap quotidien en tire ses lignes, les rapports H/M leurs compteurs :
# les deux lisent donc exactement le même filtre.
# / The sources: one queryset filtered on [debut, fin[ per source, shared by the
# daily recap (lines) and the H/M reports (counts).
# ---------------------------------------------------------------------------


def _demandes_d_adhesion(debut, fin):
    """
    Demandes d'adhésion créées dans la période, encore à valider.
    / Membership requests created in the period, still awaiting validation.
    """
    return Membership.objects.filter(
        status=Membership.ADMIN_WAITING,
        date_added__gte=debut,
        date_added__lt=fin,
    )


def _nouvelles_adhesions(debut, fin):
    """
    Adhésions créées dans la période, hors statuts non aboutis, annulés ou à valider
    (les demandes à valider ont leur propre rubrique).
    / Memberships created in the period, without unfinished, cancelled or pending ones.
    """
    return Membership.objects.filter(
        date_added__gte=debut, date_added__lt=fin
    ).exclude(
        status__in=[
            Membership.WAITING_PAYMENT,
            Membership.CANCELED,
            Membership.ADMIN_CANCELED,
            Membership.ADMIN_WAITING,
        ]
    )


def _nouvelles_reservations(debut, fin):
    """
    Réservations de billets créées dans la période, hors statuts non aboutis ou annulés.
    / Ticket bookings created in the period, without unfinished or cancelled ones.
    """
    return Reservation.objects.filter(
        created_at__gte=debut, created_at__lt=fin
    ).exclude(
        status__in=[Reservation.CREATED, Reservation.UNPAID, Reservation.CANCELED]
    )


def _demandes_de_reservation_de_ressources(debut, fin):
    """
    Demandes de réservation de ressources faites dans la période, encore à valider.
    / Resource booking requests made in the period, still awaiting validation.
    """
    return Booking.objects.filter(
        status=Booking.ADMIN_WAITING,
        booked_at__gte=debut,
        booked_at__lt=fin,
    )


def _nouvelles_reservations_de_ressources(debut, fin):
    """
    Réservations de ressources faites dans la période, hors statuts non aboutis,
    annulés ou à valider (les demandes à valider ont leur propre rubrique).
    / Resource bookings made in the period, without unfinished, cancelled or pending ones.
    """
    return Booking.objects.filter(booked_at__gte=debut, booked_at__lt=fin).exclude(
        status__in=[
            Booking.WAITING_PAYMENT,
            Booking.ADMIN_WAITING,
            Booking.ADMIN_CANCELED,
            Booking.USER_CANCELED,
        ]
    )


def _nouvelles_inscriptions_benevoles(debut, fin):
    """
    Inscriptions de bénévoles faites dans la période.
    / Volunteer sign-ups made in the period.
    """
    return InscriptionBenevole.objects.filter(created_at__gte=debut, created_at__lt=fin)


def _nouveaux_evenements(debut, fin):
    """
    Événements créés dans la période (par l'équipe ou proposés par le public).
    / Events created in the period (by the team or proposed by the public).
    """
    # Les sous-événements et les actions s'affichent dans leur événement parent,
    # comme dans l'admin des événements : on ne les compte pas à part.
    # / Sub-events and actions show inside their parent event, as in the event admin.
    return (
        Event.objects.filter(created_at__gte=debut, created_at__lt=fin)
        .exclude(categorie=Event.ACTION)
        .exclude(parent__isnull=False)
    )


def _nouveaux_projets(debut, fin):
    """
    Projets de financement participatif créés dans la période.
    / Crowdfunding projects created in the period.
    """
    return Initiative.objects.filter(created_at__gte=debut, created_at__lt=fin)


def _nouvelles_lignes_de_budget(debut, fin):
    """
    Lignes de budget proposées dans la période.
    / Budget lines proposed in the period.
    """
    return BudgetItem.objects.filter(created_at__gte=debut, created_at__lt=fin)


def _contributions_payees(debut, fin):
    """
    Contributions payées dans la période (la date de paiement compte, pas celle de
    création).
    / Contributions paid in the period (the payment date counts, not the creation date).
    """
    return Contribution.objects.filter(
        paid_at__gte=debut,
        paid_at__lt=fin,
        payment_status__in=[
            Contribution.PaymentStatus.PAID,
            Contribution.PaymentStatus.PAID_ADMIN,
        ],
    )


def _nouveaux_votes(debut, fin):
    """
    Votes donnés dans la période.
    / Votes cast in the period.
    """
    return Vote.objects.filter(created_at__gte=debut, created_at__lt=fin)


def _nouvelles_participations(debut, fin):
    """
    Participations demandées dans la période.
    / Participations requested in the period.
    """
    return Participation.objects.filter(created_at__gte=debut, created_at__lt=fin)


def _noms_des_articles_tombes_en_rupture(debut, fin):
    """
    Les noms des articles d'inventaire passés de plus de 0 à 0 ou moins pendant la
    période, triés par ordre alphabétique, chacun une seule fois.
    / Names of the inventory items that went from above 0 to 0 or below in the period.

    Un ajustement d'inventaire (AJ) ne compte pas : c'est une correction faite par
    l'admin, pas une rupture. Un article déjà à 0 avant la période n'est pas « tombé ».
    / An inventory adjustment does not count. An item already at 0 did not "fall".
    """
    mouvements_qui_font_tomber_le_stock = (
        MouvementStock.objects.filter(
            cree_le__gte=debut,
            cree_le__lt=fin,
            quantite_avant__gt=0,
            # quantite_avant + quantite <= 0, écrit sans addition dans le filtre.
            # / quantite_avant + quantite <= 0, written without an addition.
            quantite__lte=-F("quantite_avant"),
        )
        .exclude(type_mouvement=TypeMouvement.AJ)
    )
    noms = set(
        mouvements_qui_font_tomber_le_stock.values_list(
            "stock__product__name", flat=True
        )
    )
    return sorted(noms)


def _objets_annules(debut, fin):
    """
    Réservations, réservations de ressources et adhésions annulées dans la période
    par une personne (`annulee_le` n'est pas posé par l'expiration d'un paiement).
    / Reservations, resource bookings and memberships cancelled in the period.
    """
    fenetre = {"annulee_le__gte": debut, "annulee_le__lt": fin}
    return {
        "reservations": Reservation.objects.filter(**fenetre),
        "bookings": Booking.objects.filter(**fenetre),
        "adhesions": Membership.objects.filter(**fenetre),
    }


def _lignes_d_avoir(debut, fin):
    """
    Lignes de remboursement et d'avoir écrites dans la période.
    / Refund and credit-note lines written in the period.
    """
    return LigneArticle.objects.filter(
        datetime__gte=debut,
        datetime__lt=fin,
        status__in=STATUTS_DES_LIGNES_D_AVOIR,
    )


# ---------------------------------------------------------------------------
# Les lignes / The lines
# ---------------------------------------------------------------------------


def _construire_la_rubrique(cle, titre, lien, ensemble, champ_de_date, fonction_de_ligne):
    """
    LOCALISATION : Administration/recap_quotidien.py

    Transforme un ensemble d'objets déjà filtré en dict de rubrique, ou None s'il est
    vide. Les lignes vont de la plus récente à la plus ancienne.
    / Turns an already filtered queryset into a section dict, or None when empty.
    """
    ensemble = ensemble.order_by(F(champ_de_date).desc(nulls_last=True), "-pk")
    nombre = ensemble.count()
    if nombre == 0:
        return None

    lignes = []
    for objet in ensemble[:NOMBRE_DE_LIGNES_MONTREES_PAR_RUBRIQUE]:
        lignes.append(fonction_de_ligne(objet))

    return _dict_de_la_rubrique(cle, titre, nombre, lignes, lien)


def _dict_de_la_rubrique(cle, titre, nombre, lignes, lien):
    """
    LOCALISATION : Administration/recap_quotidien.py

    Le dict d'une rubrique. `lignes` contient déjà les lignes montrées (5 au plus).
    / The section dict. `lignes` already holds the shown lines (5 at most).
    """
    return {
        "cle": cle,
        "titre": titre,
        "nombre": nombre,
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


def _ajouter_le_statut_s_il_informe(morceaux, objet, statuts_normaux):
    """
    Ajoute le statut de l'objet aux morceaux de la ligne, sauf s'il est « normal ».
    / Appends the object's status to the line parts, unless it is "normal".
    """
    if objet.status not in statuts_normaux:
        morceaux.append(objet.get_status_display())


def _ligne_d_une_adhesion(adhesion):
    """
    Une ligne : personne, produit, et le statut s'il informe.
    / One line: person, product, and the status when informative.
    """
    personne = _nom_de_la_personne(
        adhesion.user, adhesion.first_name, adhesion.last_name
    )
    produit = _("(sans nom)")
    if adhesion.price is not None:
        produit = adhesion.price.product.name
    morceaux = [personne, produit]
    _ajouter_le_statut_s_il_informe(morceaux, adhesion, STATUTS_NORMAUX_D_UNE_ADHESION)
    return " — ".join(morceaux)


def _ligne_d_une_reservation(reservation):
    """
    Une ligne : personne, événement, et le statut s'il informe.
    / One line: person, event, and the status when informative.
    """
    personne = _nom_de_la_personne(reservation.user_commande)
    evenement = reservation.event.name if reservation.event else _("(sans nom)")
    morceaux = [personne, evenement]
    _ajouter_le_statut_s_il_informe(
        morceaux, reservation, STATUTS_NORMAUX_D_UNE_RESERVATION
    )
    return " — ".join(morceaux)


def _ligne_d_un_booking(booking):
    """
    Une ligne : personne, ressource, et le statut s'il informe.
    / One line: person, resource, and the status when informative.
    """
    personne = _nom_de_la_personne(booking.user, booking.first_name, booking.last_name)
    morceaux = [personne, booking.resource.name]
    _ajouter_le_statut_s_il_informe(morceaux, booking, STATUTS_NORMAUX_D_UN_BOOKING)
    return " — ".join(morceaux)


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
    Une ligne : le nom de l'événement, et son état s'il n'est pas publié.
    / One line: the event name, and its state when not published.
    """
    nom = evenement.name or _("(sans nom)")
    if evenement.published:
        return nom
    return f"{nom} — {_etat_d_un_evenement(evenement)}"


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


# ---------------------------------------------------------------------------
# Les rubriques / The sections
# ---------------------------------------------------------------------------


def _rubrique_adhesions_en_attente(debut, fin, domaine):
    """
    Demandes d'adhésion d'hier, encore à valider.
    / Yesterday's membership requests, still awaiting validation.
    """
    return _construire_la_rubrique(
        "adhesions_en_attente",
        _("Demandes d'adhésion en attente"),
        f"https://{domaine}/admin/BaseBillet/membership/",
        _demandes_d_adhesion(debut, fin).select_related("user", "price__product"),
        "date_added",
        _ligne_d_une_adhesion,
    )


def _rubrique_demandes_de_reservation_en_attente(debut, fin, domaine):
    """
    Demandes de réservation de ressources d'hier, encore à valider.
    Le lien ouvre la liste des réservations filtrée sur ce statut.
    / Yesterday's resource booking requests. The link filters the list on this status.
    """
    return _construire_la_rubrique(
        "demandes_de_reservation_en_attente",
        _("Demandes de réservation en attente"),
        f"https://{domaine}/admin/booking/booking/?status__exact={Booking.ADMIN_WAITING}",
        _demandes_de_reservation_de_ressources(debut, fin).select_related(
            "user", "resource"
        ),
        "booked_at",
        _ligne_d_un_booking,
    )


def _rubrique_ruptures_de_stock(debut, fin, domaine):
    """
    Les articles tombés en rupture hier, sur UNE seule ligne : « A, B, C ».
    / The items that ran out yesterday, on ONE line.

    `nombre_de_lignes_cachees` est forcé à 0 : le « et N autres » est déjà dans la
    ligne. Sans ça, `_dict_de_la_rubrique` compterait les noms comme des lignes et le
    gabarit écrirait « et N autres » une seconde fois.
    / Hidden lines forced to 0: the "and N others" is already in the line.
    """
    noms = _noms_des_articles_tombes_en_rupture(debut, fin)
    nombre = len(noms)
    if nombre == 0:
        return None

    noms_montres = noms[:NOMBRE_DE_LIGNES_MONTREES_PAR_RUBRIQUE]
    ligne = ", ".join(noms_montres)
    nombre_de_noms_caches = nombre - len(noms_montres)
    if nombre_de_noms_caches > 0:
        ligne = ligne + " " + ngettext(
            "et %(nombre)s autre", "et %(nombre)s autres", nombre_de_noms_caches
        ) % {"nombre": nombre_de_noms_caches}

    rubrique = _dict_de_la_rubrique(
        "ruptures_de_stock",
        _("Tombés en rupture hier"),
        nombre,
        [ligne],
        f"https://{domaine}/admin/inventaire/stock/",
    )
    rubrique["nombre_de_lignes_cachees"] = 0
    return rubrique


def _rubrique_nouvelles_adhesions(debut, fin, domaine):
    """
    Adhésions créées hier.
    / Memberships created yesterday.
    """
    return _construire_la_rubrique(
        "nouvelles_adhesions",
        _("Nouvelles adhésions"),
        f"https://{domaine}/admin/BaseBillet/membership/",
        _nouvelles_adhesions(debut, fin).select_related("user", "price__product"),
        "date_added",
        _ligne_d_une_adhesion,
    )


def _rubrique_nouvelles_reservations(debut, fin, domaine):
    """
    Réservations de billets créées hier.
    / Ticket bookings created yesterday.
    """
    return _construire_la_rubrique(
        "nouvelles_reservations",
        _("Nouvelles réservations"),
        f"https://{domaine}/admin/BaseBillet/reservation/",
        _nouvelles_reservations(debut, fin).select_related("user_commande", "event"),
        "created_at",
        _ligne_d_une_reservation,
    )


def _rubrique_nouvelles_reservations_de_ressources(debut, fin, domaine):
    """
    Réservations de ressources faites hier.
    / Resource bookings made yesterday.
    """
    return _construire_la_rubrique(
        "nouvelles_reservations_de_ressources",
        _("Nouvelles réservations de ressources"),
        f"https://{domaine}/admin/booking/booking/",
        _nouvelles_reservations_de_ressources(debut, fin).select_related(
            "user", "resource"
        ),
        "booked_at",
        _ligne_d_un_booking,
    )


def _rubrique_nouvelles_inscriptions_benevoles(debut, fin, domaine):
    """
    Inscriptions de bénévoles faites hier.
    / Volunteer sign-ups made yesterday.
    """
    return _construire_la_rubrique(
        "nouvelles_inscriptions_benevoles",
        _("Nouvelles inscriptions de bénévoles"),
        f"https://{domaine}/admin/booking/inscriptionbenevole/",
        _nouvelles_inscriptions_benevoles(debut, fin).select_related(
            "user", "besoin__tache"
        ),
        "created_at",
        _ligne_d_une_inscription,
    )


def _rubrique_nouveaux_evenements(debut, fin, domaine):
    """
    Événements créés hier. Une proposition y est marquée « proposition en attente ».
    / Events created yesterday. A proposal is marked "pending proposal".
    """
    return _construire_la_rubrique(
        "nouveaux_evenements",
        _("Nouveaux événements"),
        f"https://{domaine}/admin/BaseBillet/event/",
        _nouveaux_evenements(debut, fin),
        "created_at",
        _ligne_d_un_evenement,
    )


def _compteurs_du_projet(compteurs_par_projet, projet):
    """
    Les compteurs d'un projet, créés à zéro au premier passage.
    / A project's counters, created at zero on first access.
    """
    if projet.pk not in compteurs_par_projet:
        compteurs_par_projet[projet.pk] = {
            "projet": projet,
            "nouveau_projet": False,
            "lignes_de_budget": 0,
            "lignes_de_budget_a_valider": 0,
            "contributions": 0,
            "montant_des_contributions": 0,
            "votes": 0,
            "participations": 0,
            "participations_a_valider": 0,
        }
    return compteurs_par_projet[projet.pk]


def _total_des_compteurs(compteurs):
    """
    Le nombre d'éléments d'un projet, pour le tri (« nouveau projet » vaut 1).
    / A project's number of items, for sorting ("new project" counts 1).
    """
    total = (
        compteurs["lignes_de_budget"]
        + compteurs["contributions"]
        + compteurs["votes"]
        + compteurs["participations"]
    )
    if compteurs["nouveau_projet"]:
        total = total + 1
    return total


def _ligne_d_un_projet(compteurs):
    """
    Une ligne : le nom du projet, puis ses seuls compteurs non nuls.
    Ex. : « Jardin — nouveau projet, 2 lignes de budget dont 1 à valider, 12 votes ».
    / One line: the project's name, then its non-zero counters only.
    """
    projet = compteurs["projet"]
    morceaux = []

    if compteurs["nouveau_projet"]:
        morceaux.append(_("nouveau projet"))

    nombre = compteurs["lignes_de_budget"]
    if nombre > 0:
        texte = ngettext(
            "%(nombre)s ligne de budget", "%(nombre)s lignes de budget", nombre
        ) % {"nombre": nombre}
        a_valider = compteurs["lignes_de_budget_a_valider"]
        if a_valider > 0:
            texte = texte + " " + _("dont %(nombre)s à valider") % {"nombre": a_valider}
        morceaux.append(texte)

    nombre = compteurs["contributions"]
    if nombre > 0:
        montant = _montant_dans_la_devise_du_projet(
            compteurs["montant_des_contributions"], projet
        )
        morceaux.append(
            ngettext(
                "%(nombre)s contribution (%(montant)s)",
                "%(nombre)s contributions (%(montant)s)",
                nombre,
            )
            % {"nombre": nombre, "montant": montant}
        )

    nombre = compteurs["votes"]
    if nombre > 0:
        morceaux.append(
            ngettext("%(nombre)s vote", "%(nombre)s votes", nombre) % {"nombre": nombre}
        )

    nombre = compteurs["participations"]
    if nombre > 0:
        texte = ngettext(
            "%(nombre)s participation", "%(nombre)s participations", nombre
        ) % {"nombre": nombre}
        a_valider = compteurs["participations_a_valider"]
        if a_valider > 0:
            texte = texte + " " + _("dont %(nombre)s à valider") % {"nombre": a_valider}
        morceaux.append(texte)

    nom_du_projet = projet.name or _("(sans nom)")
    return f"{nom_du_projet} — {', '.join(morceaux)}"


def _rubrique_financement_participatif(debut, fin, domaine):
    """
    Une ligne par projet touché hier : créé, ou qui a reçu une ligne de budget, une
    contribution payée, un vote ou une demande de participation.
    Les projets les plus actifs d'abord, puis par nom.
    / One line per project touched yesterday. Most active first, then by name.
    """
    compteurs_par_projet = {}

    for projet in _nouveaux_projets(debut, fin):
        _compteurs_du_projet(compteurs_par_projet, projet)["nouveau_projet"] = True

    for ligne_de_budget in _nouvelles_lignes_de_budget(debut, fin).select_related(
        "initiative"
    ):
        compteurs = _compteurs_du_projet(
            compteurs_par_projet, ligne_de_budget.initiative
        )
        compteurs["lignes_de_budget"] += 1
        if ligne_de_budget.state == BudgetItem.State.REQUESTED:
            compteurs["lignes_de_budget_a_valider"] += 1

    for contribution in _contributions_payees(debut, fin).select_related("initiative"):
        compteurs = _compteurs_du_projet(compteurs_par_projet, contribution.initiative)
        compteurs["contributions"] += 1
        compteurs["montant_des_contributions"] += contribution.amount or 0

    for vote in _nouveaux_votes(debut, fin).select_related("initiative"):
        _compteurs_du_projet(compteurs_par_projet, vote.initiative)["votes"] += 1

    for participation in _nouvelles_participations(debut, fin).select_related(
        "initiative"
    ):
        compteurs = _compteurs_du_projet(compteurs_par_projet, participation.initiative)
        compteurs["participations"] += 1
        if participation.state == Participation.State.REQUESTED:
            compteurs["participations_a_valider"] += 1

    nombre = len(compteurs_par_projet)
    if nombre == 0:
        return None

    compteurs_tries = sorted(
        compteurs_par_projet.values(),
        key=lambda compteurs: (
            -_total_des_compteurs(compteurs),
            (compteurs["projet"].name or "").lower(),
        ),
    )

    lignes = []
    for compteurs in compteurs_tries[:NOMBRE_DE_LIGNES_MONTREES_PAR_RUBRIQUE]:
        lignes.append(_ligne_d_un_projet(compteurs))

    return _dict_de_la_rubrique(
        "financement_participatif",
        _("Financement participatif"),
        nombre,
        lignes,
        f"https://{domaine}/admin/crowds/initiative/",
    )


def _cle_de_l_objet_d_une_ligne_d_avoir(ligne_article):
    """
    L'objet visé par une ligne d'avoir, sous forme de clé (champ de lien, pk).
    Une ligne d'avoir copie `reservation`, `membership` et `booking` de la ligne
    d'origine (BaseBillet/services_vente.py) : on regroupe sur ces liens. Un article
    de caisse sans objet garde sa propre clé.
    / The object targeted by a credit line, as a (link field, pk) key.
    """
    if ligne_article.reservation_id is not None:
        return ("reservation_id", ligne_article.reservation_id)
    if ligne_article.membership_id is not None:
        return ("membership_id", ligne_article.membership_id)
    if ligne_article.booking_id is not None:
        return ("booking_id", ligne_article.booking_id)
    return ("ligne_article", ligne_article.pk)


def _rubrique_annulations_et_remboursements(debut, fin, domaine):
    """
    Une ligne par objet, jamais deux :
    - un objet annulé hier : « Personne — Objet — Statut », puis « remboursé X € »
      s'il a au moins une ligne d'avoir (de n'importe quelle date) ;
    - une ligne d'avoir d'hier dont l'objet n'est pas annulé hier, ou sans objet
      (article de caisse) : « Objet — remboursé X € », regroupée par objet.
    Le montant est l'argent rendu : la somme de -total_ttc (centimes, négatif).
    / One line per object: cancelled yesterday (with its refund, if any), or refunded
    yesterday without being cancelled yesterday. The amount is the money given back.
    """
    objets_annules = _objets_annules(debut, fin)
    reservations = list(
        objets_annules["reservations"].select_related("user_commande", "event")
    )
    bookings = list(objets_annules["bookings"].select_related("user", "resource"))
    adhesions = list(
        objets_annules["adhesions"].select_related("user", "price__product")
    )

    # Chaque entrée : {"texte", "moment", "a_un_avoir", "argent_rendu"}.
    # / Each entry: text, moment, has a credit line, money given back (cents).
    entrees_par_cle = {}

    # 1. Les objets annulés hier.
    # / 1. Objects cancelled yesterday.
    objets_annules_par_champ = {
        "reservation_id": (reservations, _ligne_d_une_reservation),
        "booking_id": (bookings, _ligne_d_un_booking),
        "membership_id": (adhesions, _ligne_d_une_adhesion),
    }
    for champ_de_lien, (objets, fonction_de_ligne) in objets_annules_par_champ.items():
        for objet in objets:
            entrees_par_cle[(champ_de_lien, objet.pk)] = {
                "texte": fonction_de_ligne(objet),
                "moment": objet.annulee_le,
                "a_un_avoir": False,
                "argent_rendu": 0,
            }

        # Toutes les lignes d'avoir de ces objets, quelle que soit leur date : une
        # requête par type d'objet.
        # / All credit lines of these objects, whatever their date: one query per type.
        identifiants = [objet.pk for objet in objets]
        if not identifiants:
            continue
        filtre = {f"{champ_de_lien}__in": identifiants}
        lignes_d_avoir_des_objets = LigneArticle.objects.filter(
            status__in=STATUTS_DES_LIGNES_D_AVOIR, **filtre
        ).values_list(champ_de_lien, "total_ttc")
        for identifiant, total_ttc in lignes_d_avoir_des_objets:
            entree = entrees_par_cle[(champ_de_lien, identifiant)]
            entree["a_un_avoir"] = True
            entree["argent_rendu"] += -(total_ttc or 0)

    # 2. Les lignes d'avoir d'hier dont l'objet n'est pas annulé hier.
    # / 2. Yesterday's credit lines whose object was not cancelled yesterday.
    lignes_d_avoir_d_hier = _lignes_d_avoir(debut, fin).select_related(
        "reservation__event",
        "membership__price__product",
        "booking__resource",
        "pricesold__productsold__product",
    )
    cles_des_objets_annules_hier = set(entrees_par_cle.keys())
    for ligne_article in lignes_d_avoir_d_hier:
        cle = _cle_de_l_objet_d_une_ligne_d_avoir(ligne_article)
        if cle in cles_des_objets_annules_hier:
            # Déjà compté à l'étape 1, avec toutes ses lignes d'avoir.
            # / Already counted in step 1, with all its credit lines.
            continue

        if cle not in entrees_par_cle:
            entrees_par_cle[cle] = {
                "texte": _nom_de_l_objet_rembourse(ligne_article),
                "moment": ligne_article.datetime,
                "a_un_avoir": True,
                "argent_rendu": 0,
            }
        entree = entrees_par_cle[cle]
        entree["argent_rendu"] += -(ligne_article.total_ttc or 0)
        if ligne_article.datetime > entree["moment"]:
            entree["moment"] = ligne_article.datetime

    nombre = len(entrees_par_cle)
    if nombre == 0:
        return None

    # Les plus récentes d'abord. Le tri de Python est stable : à égalité exacte,
    # l'ordre reste réservations, ressources, adhésions, puis les avoirs.
    # / Most recent first. Python's sort is stable.
    entrees_triees = sorted(
        entrees_par_cle.values(), key=lambda entree: entree["moment"], reverse=True
    )

    lignes = []
    for entree in entrees_triees[:NOMBRE_DE_LIGNES_MONTREES_PAR_RUBRIQUE]:
        texte = entree["texte"]
        if entree["a_un_avoir"]:
            texte = f"{texte} — " + _("remboursé %(montant)s") % {
                "montant": euros_a_la_francaise(entree["argent_rendu"])
            }
        lignes.append(texte)

    # Le lien : la liste des ventes, qui porte les avoirs.
    # / The link: the sales list, which holds the credit notes.
    return _dict_de_la_rubrique(
        "annulations_et_remboursements",
        _("Annulations et remboursements"),
        nombre,
        lignes,
        f"https://{domaine}/admin/BaseBillet/vente/",
    )


def rubriques_de_la_veille(debut, fin, domaine):
    """
    LOCALISATION : Administration/recap_quotidien.py

    Les rubriques NON VIDES : d'abord ce qui demande une action (les demandes à
    valider), puis l'inventaire, puis les nouveautés.
    / The NON-EMPTY sections: what needs action first, then inventory, then news.
    """
    fonctions_des_rubriques = [
        # À valider / To validate
        _rubrique_adhesions_en_attente,
        _rubrique_demandes_de_reservation_en_attente,
        # Inventaire / Inventory
        _rubrique_ruptures_de_stock,
        # Nouveautés / News
        _rubrique_nouvelles_adhesions,
        _rubrique_nouvelles_reservations,
        _rubrique_nouvelles_reservations_de_ressources,
        _rubrique_nouvelles_inscriptions_benevoles,
        _rubrique_nouveaux_evenements,
        _rubrique_financement_participatif,
        _rubrique_annulations_et_remboursements,
    ]
    rubriques = []
    for fonction_de_la_rubrique in fonctions_des_rubriques:
        rubrique = fonction_de_la_rubrique(debut, fin, domaine)
        if rubrique is not None:
            rubriques.append(rubrique)
    return rubriques


def _ajouter_le_compteur(compteurs, nombre, texte_traduit):
    """
    Ajoute « texte_traduit % nombre » aux compteurs, seulement si le nombre est non nul.
    `texte_traduit` vient d'un appel `ngettext` écrit avec ses textes en clair : c'est
    ce que `makemessages` sait extraire (pas un texte passé par une variable).
    / Appends the counter text when the number is non-zero.
    """
    if nombre > 0:
        compteurs.append(texte_traduit % {"nombre": nombre})


def compteurs_de_la_periode(debut, fin):
    """
    LOCALISATION : Administration/recap_quotidien.py

    Les compteurs NON NULS de l'activité de [debut, fin[, sans aucun détail, pour
    les mails de clôture hebdomadaire et mensuelle. Chaque compteur lit la même
    source que la rubrique quotidienne correspondante.
    Rend une liste de textes, ex. ["12 nouvelles adhésions", "31 votes"].
    / The NON-ZERO activity counters of [debut, fin[, for the weekly and monthly
    closure mails. Each counter reads the same source as the daily section.

    APPELÉE PAR : comptabilite/tasks.py `_envoyer_l_email_de_la_cloture`, dans la
    langue du lieu.
    """
    compteurs = []

    nombre = _nouvelles_adhesions(debut, fin).count()
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext(
            "%(nombre)s nouvelle adhésion", "%(nombre)s nouvelles adhésions", nombre
        ),
    )

    nombre = _demandes_d_adhesion(debut, fin).count()
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext(
            "%(nombre)s demande d'adhésion", "%(nombre)s demandes d'adhésion", nombre
        ),
    )

    nombre = _nouvelles_reservations(debut, fin).count()
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext(
            "%(nombre)s nouvelle réservation",
            "%(nombre)s nouvelles réservations",
            nombre,
        ),
    )

    nombre = _nouvelles_reservations_de_ressources(debut, fin).count()
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext(
            "%(nombre)s réservation de ressource",
            "%(nombre)s réservations de ressources",
            nombre,
        ),
    )

    nombre = _demandes_de_reservation_de_ressources(debut, fin).count()
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext(
            "%(nombre)s demande de réservation de ressource",
            "%(nombre)s demandes de réservation de ressources",
            nombre,
        ),
    )

    nombre = _nouvelles_inscriptions_benevoles(debut, fin).count()
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext(
            "%(nombre)s inscription de bénévole",
            "%(nombre)s inscriptions de bénévoles",
            nombre,
        ),
    )

    # « dont N propositions » : l'état au moment de l'envoi, même règle que
    # `_etat_d_un_evenement`.
    # / "including N proposals": the state at sending time.
    evenements = _nouveaux_evenements(debut, fin)
    nombre = evenements.count()
    if nombre > 0:
        texte = ngettext(
            "%(nombre)s nouvel événement", "%(nombre)s nouveaux événements", nombre
        ) % {"nombre": nombre}
        nombre_de_propositions = evenements.filter(
            is_proposal=True, published=False
        ).count()
        if nombre_de_propositions > 0:
            texte = texte + " " + ngettext(
                "(dont %(nombre)s proposition)",
                "(dont %(nombre)s propositions)",
                nombre_de_propositions,
            ) % {"nombre": nombre_de_propositions}
        compteurs.append(texte)

    nombre = _nouveaux_projets(debut, fin).count()
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext("%(nombre)s nouveau projet", "%(nombre)s nouveaux projets", nombre),
    )

    nombre = _nouvelles_lignes_de_budget(debut, fin).count()
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext(
            "%(nombre)s ligne de budget", "%(nombre)s lignes de budget", nombre
        ),
    )

    nombre = _contributions_payees(debut, fin).count()
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext("%(nombre)s contribution", "%(nombre)s contributions", nombre),
    )

    nombre = _nouveaux_votes(debut, fin).count()
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext("%(nombre)s vote", "%(nombre)s votes", nombre),
    )

    nombre = _nouvelles_participations(debut, fin).count()
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext("%(nombre)s participation", "%(nombre)s participations", nombre),
    )

    # Deux compteurs : les objets annulés, et les lignes d'avoir (une réservation de
    # 3 billets remboursée compte 3 remboursements).
    # / Two counters: cancelled objects, and credit lines.
    objets_annules = _objets_annules(debut, fin)
    nombre = (
        objets_annules["reservations"].count()
        + objets_annules["bookings"].count()
        + objets_annules["adhesions"].count()
    )
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext("%(nombre)s annulation", "%(nombre)s annulations", nombre),
    )

    nombre = _lignes_d_avoir(debut, fin).count()
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext("%(nombre)s remboursement", "%(nombre)s remboursements", nombre),
    )

    nombre = len(_noms_des_articles_tombes_en_rupture(debut, fin))
    _ajouter_le_compteur(
        compteurs,
        nombre,
        ngettext(
            "%(nombre)s article tombé en rupture",
            "%(nombre)s articles tombés en rupture",
            nombre,
        ),
    )

    return compteurs


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

    Vrai s'il y a au moins une rubrique ou un Z. Toute rubrique ne porte que des
    objets de la veille : une rubrique non vide suffit.
    / True if there is at least one section or one Z.
    """
    if len(clotures) > 0:
        return True
    return len(rubriques) > 0


def destinataires_du_recap():
    """
    LOCALISATION : Administration/recap_quotidien.py

    Les e-mails de la liste des destinataires des réglages des envois
    (`ConfigurationDesRapports`), et eux seuls : aucun admin d'office, aucun repli
    sur l'e-mail du lieu. Liste vide = aucun mail.
    / The e-mails of the recipient list of the mail settings, and only them.
    """
    return ConfigurationDesRapports.get_solo().adresses_des_destinataires()


def lien_des_reglages_des_envois(domaine):
    """
    LOCALISATION : Administration/recap_quotidien.py

    L'adresse de la page des réglages des envois dans l'admin du lieu : le lien
    « se désabonner » en pied du récap et des mails de clôture. La page est réservée
    aux admins du lieu.
    / The address of the mail settings page: the "unsubscribe" link of the mails.
    """
    return f"https://{domaine}/admin/comptabilite/configurationdesrapports/"


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
        "destinataires": destinataires_du_recap(),
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
            "lien_des_reglages_des_envois": lien_des_reglages_des_envois(domaine),
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
    s'il est coché dans les réglages des envois, s'il est 7 h passées (heure du lieu),
    si le seuil d'aujourd'hui est passé et s'il n'a pas déjà été traité aujourd'hui.
    Rend True si un mail est parti.
    / Called from comptabilite/tasks.py inside the venue's tenant_context.
    """
    # Décoché : rien, pas même le marqueur. Recoché dans la journée, le récap du jour
    # part encore à l'heure suivante.
    # / Unticked: nothing, not even the marker.
    if not ConfigurationDesRapports.get_solo().envoyer_le_recap_quotidien:
        return False

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
