"""
Montant d'une réservation de ressource : le seul endroit qui le calcule.
/ Amount of a resource booking: the single place that computes it.

LOCALISATION : booking/montants.py

Le tarif est horaire en base (`Price.prix`). Le réservant, lui, voit et paie des
créneaux : pour un tarif fixe, un créneau vaut `prix × durée / 60`, arrondi aux 10
centimes les plus proches, et N créneaux valent N fois ce montant arrondi. Ainsi le
réservant paie exactement ce qu'il a lu (booking/spec/main/booking-form.md, R1).
/ The price is hourly in the DB. The booker sees and pays slots: for a fixed price, one
slot is `prix × duration / 60` rounded to the nearest 10 cents, and N slots are N times
that rounded amount, so the booker pays exactly what they read (R1).

Pour un tarif à prix libre, le formulaire reçoit un montant PAR CRÉNEAU. On le
convertit en montant horaire dès la réception (réservation directe et panier) : la
suite (validation du minimum, panier, moteur) reste en heure. Ce montant n'a pas
l'arrondi des tarifs fixes : on le paie au centime près (R3).
/ For an open price the form receives a PER-SLOT amount, converted to an hourly
amount on reception; the rest stays hourly. It is not rounded like fixed prices: it is
paid to the cent (R3).

APPELÉ PAR :
- booking/booking_engine.py : validate_new_booking (montant facturé, minimum)
- BaseBillet/services_panier.py : PanierSession.add_resource (estimation, minimum)
- booking/views.py et BaseBillet/views.py : conversion du montant saisi, libellés
"""
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP, InvalidOperation

UN_CENTIME = Decimal("0.01")

# `quantize` ne lit que l'exposant : Decimal("0.10") arrondirait au centime, pas ici.
# / `quantize` only reads the exponent: Decimal("0.10") would round to the cent.
DIX_CENTIMES = Decimal("0.1")


def _arrondi_aux_10_centimes(montant_exact, sens_de_l_arrondi):
    """
    Arrondit aux 10 centimes, et garde deux décimales : 8,3 s'écrit 8.30 dans le panier.
    / Rounds to 10 cents and keeps two decimals: 8.3 reads 8.30 in the cart.
    """
    return montant_exact.quantize(DIX_CENTIMES, rounding=sens_de_l_arrondi).quantize(UN_CENTIME)


def montant_d_un_creneau(prix_horaire, duree_du_creneau_en_minutes):
    """
    Le montant d'un créneau d'un tarif fixe, arrondi aux 10 centimes les plus proches.
    / The amount of one slot of a fixed price, rounded to the nearest 10 cents.

    Exemple : 10 €/h pour 50 minutes donnent 8,333… €, soit 8,30 €.
    """
    montant_exact = (
        Decimal(str(prix_horaire))
        * Decimal(duree_du_creneau_en_minutes)
        / Decimal(60)
    )
    return _arrondi_aux_10_centimes(montant_exact, ROUND_HALF_UP)


def montant_de_la_reservation(prix_horaire, duree_du_creneau_en_minutes, nombre_de_creneaux):
    """
    Le montant de N créneaux consécutifs d'un tarif fixe : N fois le montant arrondi
    d'un créneau.
    / The amount of N consecutive slots of a fixed price: N times the rounded amount of
    one slot.

    Exemple : 10 €/h, 3 créneaux de 40 minutes : 3 × 6,70 = 20,10 €.
    """
    montant_par_creneau = montant_d_un_creneau(prix_horaire, duree_du_creneau_en_minutes)
    return montant_par_creneau * Decimal(nombre_de_creneaux)


def montant_libre_de_la_reservation(
    montant_horaire_saisi, duree_du_creneau_en_minutes, nombre_de_creneaux
):
    """
    Le montant de N créneaux d'un tarif à prix libre : N fois le montant saisi.
    / The amount of N slots of an open price: N times the typed amount.

    Le montant saisi a été ramené à l'heure sans arrondi : l'arrondi au centime ne sert
    qu'à retrouver le montant saisi, malgré les décimales de la division.
    Exemple : 6,67 € saisis pour 40 minutes, 3 créneaux : 3 × 6,67 = 20,01 €.
    / The typed amount was converted to hourly without rounding: rounding to the cent only
    gets the typed amount back, despite the division's decimals.
    """
    montant_exact = (
        Decimal(str(montant_horaire_saisi))
        * Decimal(duree_du_creneau_en_minutes)
        / Decimal(60)
    )
    montant_par_creneau = montant_exact.quantize(UN_CENTIME, rounding=ROUND_HALF_UP)
    return montant_par_creneau * Decimal(nombre_de_creneaux)


def minimum_d_un_creneau(prix_horaire_minimum, duree_du_creneau_en_minutes):
    """
    Le minimum d'un créneau pour un tarif à prix libre, arrondi aux 10 centimes SUPÉRIEURS.
    / The per-slot minimum of an open price, rounded UP to 10 cents.

    Exemple : 10 €/h pour 50 minutes donnent 8,333… €, soit 8,40 €.
    """
    minimum_exact = (
        Decimal(str(prix_horaire_minimum))
        * Decimal(duree_du_creneau_en_minutes)
        / Decimal(60)
    )
    return _arrondi_aux_10_centimes(minimum_exact, ROUND_CEILING)


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
    `montant_libre_de_la_reservation` retrouve exactement 20 €.
    / No rounding here: 20 € for 180 minutes give 6.666… €/h, and
    `montant_libre_de_la_reservation` gets exactly 20 € back.

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
