"""
Montant d'une réservation de ressource : le seul endroit qui le calcule.
/ Amount of a resource booking: the single place that computes it.

LOCALISATION : booking/montants.py

Le tarif est horaire en base (`Price.prix`). Le réservant, lui, voit et paie des
créneaux : un créneau vaut `prix × durée / 60`, arrondi au centime le plus proche, et
N créneaux valent N fois ce montant arrondi. Ainsi le réservant paie exactement ce
qu'il a lu (TECH_DOC/SESSIONS/BOOKING/CHANTIER-02-prix-par-creneau.md, R1).
Une durée multiple de 60 minutes ne demande jamais d'arrondi.
/ The price is hourly in the DB. The booker sees and pays slots: one slot is
`prix × duration / 60` rounded to the nearest cent, and N slots are N times that
rounded amount, so the booker pays exactly what they read (R1).

Pour un tarif à prix libre, le formulaire reçoit un montant PAR CRÉNEAU. On le
convertit en montant horaire dès la réception (réservation directe et panier) : la
suite (validation du minimum, panier, moteur) reste en heure. Le même calcul retrouve
ensuite le montant saisi, au centime près (R3).
/ For an open price the form receives a PER-SLOT amount, converted to an hourly
amount on reception; the rest stays hourly. The same computation then gets the typed
amount back, to the cent (R3).

APPELÉ PAR :
- booking/booking_engine.py : validate_new_booking (montant facturé, minimum)
- BaseBillet/services_panier.py : PanierSession.add_resource (estimation, minimum)
- booking/views.py et BaseBillet/views.py : conversion du montant saisi, libellés
"""
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP, InvalidOperation

UN_CENTIME = Decimal("0.01")


def montant_d_un_creneau(prix_horaire, duree_du_creneau_en_minutes):
    """
    Le montant d'un créneau, arrondi au centime le plus proche.
    / The amount of one slot, rounded to the nearest cent.

    Exemple : 10 €/h pour 40 minutes donnent 6,666… €, soit 6,67 €.

    Pour un prix libre, `prix_horaire` est le montant saisi ramené à l'heure sans
    arrondi (prix_horaire_d_un_montant_par_creneau). L'arrondi au centime retrouve alors
    exactement le montant saisi : 20 € pour 180 minutes donnent 6,666… €/h, puis 20,00 €.
    / For an open price, `prix_horaire` is the typed amount converted to hourly without
    rounding: rounding to the cent gets the typed amount back exactly.
    """
    montant_exact = (
        Decimal(str(prix_horaire))
        * Decimal(duree_du_creneau_en_minutes)
        / Decimal(60)
    )
    return montant_exact.quantize(UN_CENTIME, rounding=ROUND_HALF_UP)


def montant_de_la_reservation(prix_horaire, duree_du_creneau_en_minutes, nombre_de_creneaux):
    """
    Le montant de N créneaux consécutifs : N fois le montant arrondi d'un créneau.
    / The amount of N consecutive slots: N times the rounded amount of one slot.

    On arrondit chaque créneau, puis on multiplie : le réservant paie N fois le montant
    qu'il a lu. Arrondir le total exact donnerait parfois un centime de différence.
    Exemple : 10 €/h, 3 créneaux de 40 minutes : 3 × 6,67 = 20,01 €.
    / Round each slot, then multiply: the booker pays N times the amount they read.
    """
    montant_par_creneau = montant_d_un_creneau(prix_horaire, duree_du_creneau_en_minutes)
    return montant_par_creneau * Decimal(nombre_de_creneaux)


def minimum_d_un_creneau(prix_horaire_minimum, duree_du_creneau_en_minutes):
    """
    Le minimum d'un créneau pour un tarif à prix libre, arrondi au centime SUPÉRIEUR.
    / The per-slot minimum of an open price, rounded UP to the cent.

    Exemple : 10 €/h pour 50 minutes donnent 8,333… €, soit 8,34 €.
    L'arrondi vers le haut garantit qu'un montant égal au minimum affiché atteint le
    minimum horaire du tarif.
    / Rounding up guarantees that an amount equal to the shown minimum reaches the
    price's hourly minimum.
    """
    minimum_exact = (
        Decimal(str(prix_horaire_minimum))
        * Decimal(duree_du_creneau_en_minutes)
        / Decimal(60)
    )
    return minimum_exact.quantize(UN_CENTIME, rounding=ROUND_CEILING)


def minimum_horaire_d_un_creneau(prix_horaire_minimum, duree_du_creneau_en_minutes):
    """
    Le minimum affiché pour un créneau, ramené à l'heure comme un montant saisi.
    / The per-slot shown minimum, converted to hourly like a typed amount.

    Le moteur et le panier comparent en heure. Le passage par la même conversion donne le
    même nombre pour un montant saisi égal au minimum : il est donc accepté, et tout
    montant inférieur est refusé.
    / The engine and the cart compare hourly. The same conversion gives the same number for
    a typed amount equal to the minimum: it is accepted, and any lower amount is refused.
    """
    minimum_par_creneau = minimum_d_un_creneau(prix_horaire_minimum, duree_du_creneau_en_minutes)
    return prix_horaire_d_un_montant_par_creneau(minimum_par_creneau, duree_du_creneau_en_minutes)


def prix_horaire_d_un_montant_par_creneau(montant_saisi, duree_du_creneau_en_minutes):
    """
    Convertit le montant saisi pour un créneau en montant horaire, sans arrondi.
    / Converts the per-slot typed amount into an hourly amount, without rounding.

    Pas d'arrondi ici : 20 € pour 180 minutes donnent 6,666… €/h, et
    `montant_d_un_creneau` retrouve exactement 20 €.
    / No rounding here: 20 € for 180 minutes give 6.666… €/h, and
    `montant_d_un_creneau` gets exactly 20 € back.

    Un montant absent ou illisible est rendu tel quel : la validation qui suit
    (panier ou moteur) le refuse avec son propre message.
    / A missing or unreadable amount is returned unchanged: the following validation
    refuses it with its own message.
    """
    if montant_saisi is None or montant_saisi == "":
        return montant_saisi
    try:
        montant_par_creneau = Decimal(str(montant_saisi))
    except (InvalidOperation, ValueError):
        return montant_saisi
    if not montant_par_creneau.is_finite():
        return montant_saisi
    return montant_par_creneau * Decimal(60) / Decimal(duree_du_creneau_en_minutes)
