"""
Libelle de prix commun : evenements, adhesions, ressources.
/ Shared price label: events, memberships, resources.

LOCALISATION : BaseBillet/services_libelle_prix.py

Ce module fabrique le petit texte de prix affiche sur les cartes et les fiches.
Il est le seul endroit qui decide de ce texte.
/ Builds the short price text shown on cards and detail pages. Single source of truth.

REGLES (testees dans cet ordre, le premier cas qui marche gagne) :
1. Au moins un prix libre       -> « Prix libre dès X € » (ou « Prix libre » si X vaut 0).
                                   X est le plus petit montant de tous les tarifs en euros.
2. Que des tarifs en points ou en temps (vendus a la caisse seulement)
                                -> None : la carte n'affiche pas de prix.
3. Aucun tarif, ou tous a 0 €   -> « Entrée libre » (evenement) ou « Gratuit » (adhesion, ressource).
4. Un seul montant different    -> « 12 € ».
5. Plusieurs montants           -> « De 10 à 25 € ».

APPELE PAR :
- BaseBillet/views.py : EventMVT (agenda, fiche, evenements federes) et MembershipMVT (liste)
- booking/views.py : BookingViewSet.list

Le texte est pose sur l'objet dans l'attribut `libelle_prix` (pas un champ du modele).
Il est lu par cotton/V2/event_card.html, membership_card.html, ressource_card.html
et pages/classic/partials/reservation_declencheur.html.
/ The text is set on the object as `libelle_prix` and read by the card templates.
"""

from django.utils import formats
from django.utils.translation import gettext

from BaseBillet.models import Product

TYPE_EVENEMENT = "evenement"
TYPE_ADHESION = "adhesion"
TYPE_RESSOURCE = "ressource"


def formater_montant(montant):
    """
    Met un montant en texte, sans centimes inutiles, selon la langue active.
    / Formats an amount as text, without useless cents, in the active language.

    Exemples en francais : 12.00 -> "12"     12.50 -> "12,50"

    :param montant: un Decimal
    :return: le montant en texte (str), sans le symbole euro
    """
    montant_est_un_entier = montant == montant.to_integral_value()
    if montant_est_un_entier:
        return formats.number_format(montant, decimal_pos=0)
    return formats.number_format(montant, decimal_pos=2)


def tarif_est_en_euros(tarif):
    """
    Dit si un tarif se paie en euros.
    / Tells whether a price is paid in euros.

    Un tarif lie a un asset (monnaie locale, points) ou non fiduciaire (temps)
    se vend a la caisse seulement. Il ne compte pas dans le prix affiche.
    / Asset or non-fiduciary prices are POS-only: not an euro price.
    """
    if tarif.asset_id is not None:
        return False
    if tarif.non_fiduciaire:
        return False
    return True


def tarifs_publies_de_l_evenement(event):
    """
    Renvoie les tarifs de billetterie publies et non archives d'un evenement.
    / Returns an event's published, non-archived ticketing prices.

    On parcourt event.products.all() puis product.prices.all() en Python.
    INDISPENSABLE : un .filter() ici referait une requete SQL par evenement
    et court-circuiterait le prefetch_related de federated_events_filter.
    / Iterates the prefetched relations. A .filter() would cause one query per event.

    Seuls les produits BILLET et FREERES comptent : une adhesion obligatoire
    liee a l'evenement ne fait pas son prix d'entree.
    / Only ticket and free-booking products count.

    A appeler DANS le tenant_context de l'evenement : les tarifs vivent
    dans le schema du lieu.
    / Must be called INSIDE the event's tenant_context.
    """
    tarifs_publies = []
    for product in event.products.all():
        produit_est_de_la_billetterie = product.categorie_article in (
            Product.BILLET,
            Product.FREERES,
        )
        if not produit_est_de_la_billetterie:
            continue

        for tarif in product.prices.all():
            if tarif.archived or not tarif.publish:
                continue
            tarifs_publies.append(tarif)
    return tarifs_publies


def libelle_prix(tarifs, type_objet):
    """
    Fabrique le texte du prix a partir d'une liste de tarifs.
    / Builds the price text from a list of prices.

    Voir les REGLES en haut du fichier.
    / See RULES at the top of the file.

    :param tarifs: des Price deja filtres (publies, non archives)
    :param type_objet: TYPE_EVENEMENT, TYPE_ADHESION ou TYPE_RESSOURCE
    :return: le texte (str), ou None si rien n'est a afficher
    """
    # On garde seulement les tarifs payables en euros.
    # / Keep only euro prices.
    tarifs_en_euros = []
    il_y_a_des_tarifs_hors_euros = False
    for tarif in tarifs:
        if tarif_est_en_euros(tarif):
            tarifs_en_euros.append(tarif)
        else:
            il_y_a_des_tarifs_hors_euros = True

    montants = []
    il_y_a_un_prix_libre = False
    for tarif in tarifs_en_euros:
        montants.append(tarif.prix)
        if tarif.free_price:
            il_y_a_un_prix_libre = True

    # Regle 1 : prix libre. Le montant en base d'un prix libre est le minimum accepte.
    # / Rule 1: open price. Its stored amount is the minimum accepted.
    if il_y_a_un_prix_libre:
        montant_le_plus_bas = min(montants)
        if montant_le_plus_bas > 0:
            return gettext("Prix libre dès %(montant)s €") % {
                "montant": formater_montant(montant_le_plus_bas),
            }
        return gettext("Prix libre")

    # Regle 2 : uniquement des tarifs a la caisse -> pas de prix affiche.
    # / Rule 2: POS-only prices -> no price shown.
    if not tarifs_en_euros and il_y_a_des_tarifs_hors_euros:
        return None

    # Regle 3 : aucun tarif, ou tous a zero.
    # / Rule 3: no price, or every price is zero.
    montants_payants = []
    for montant in montants:
        if montant > 0:
            montants_payants.append(montant)
    if not montants_payants:
        if type_objet == TYPE_EVENEMENT:
            # S'il y a un prix gratuit, on change le libellé
            if len(montants) >= 1:
                return gettext("Réservation gratuite")
            return gettext("Entrée libre")
        return gettext("Gratuit")

    # Regle 4 : un seul montant different (deux tarifs a 10 € comptent pour un).
    # / Rule 4: a single distinct amount.
    montant_minimum = min(montants)
    montant_maximum = max(montants)
    if montant_minimum == montant_maximum:
        return gettext("%(montant)s €") % {
            "montant": formater_montant(montant_minimum),
        }

    # Regle 5 : plusieurs montants -> le plus bas et le plus haut.
    # / Rule 5: several amounts -> lowest and highest.
    return gettext("De %(minimum)s à %(maximum)s €") % {
        "minimum": formater_montant(montant_minimum),
        "maximum": formater_montant(montant_maximum),
    }
