"""
Pass multi-événements : transformer l'achat d'un pass en billets, un par événement.
/ Multi-event pass: turn a pass purchase into tickets, one per event.

LOCALISATION : BaseBillet/services_pass.py

FLUX D'UN ACHAT :
1. Le panier (services_commande.py) ou la caisse (laboutik/views.py) appelle
   deplier_le_pass(produit, quantite).
2. Pour chaque événement du pass, il crée une Reservation. En ligne, il appelle
   TicketCreator avec `identifiants_des_passes`.
3. Chaque billet est créé au prix de la ligne de son événement, avec l'identifiant de
   son pass (Ticket.pass_vendu). Le même identifiant sur tous les événements relie les
   billets d'un même pass.
"""
from uuid import uuid4


def deplier_le_pass(produit_pass, quantite):
    """
    Prépare l'achat de `quantite` passes.
    / Prepares the purchase of `quantite` passes.

    LOCALISATION : BaseBillet/services_pass.py

    :return: dict avec
        - "identifiants_des_passes" : un UUID par pass acheté, à donner à tous les
          événements du pass ;
        - "lignes_du_pass" : les EvenementDuPass, du premier au dernier événement.
    """
    identifiants_des_passes = []
    for _numero_du_pass in range(int(quantite)):
        identifiants_des_passes.append(uuid4())

    lignes_du_pass = list(produit_pass.lignes_du_pass())

    return {
        "identifiants_des_passes": identifiants_des_passes,
        "lignes_du_pass": lignes_du_pass,
    }


def repartir_le_montant_du_pass(lignes_du_pass, montant_en_centimes):
    """
    Pass à prix libre : répartit le montant payé (pour UN pass) entre ses événements.
    Chaque événement reçoit d'abord son prix dans le pass (son minimum), puis le reste est
    partagé à parts égales entre tous les événements. Le dernier prend l'arrondi au
    centime : la somme des parts vaut toujours le montant payé.
    / Free-price pass: each event gets its minimum, the rest is split equally; the last
    event takes the rounding.

    LOCALISATION : BaseBillet/services_pass.py

    Exemple : minimums 10 € et 0 €, 30 € payés → reste 20 € → 20 € et 10 €.

    :param lignes_du_pass: les EvenementDuPass, dans l'ordre de deplier_le_pass
    :param montant_en_centimes: montant payé pour un pass (int), au moins la somme des minimums
    :return: liste des parts en centimes (int), dans l'ordre des lignes
    """
    minimums_en_centimes = []
    for ligne_du_pass in lignes_du_pass:
        minimums_en_centimes.append(int(round(ligne_du_pass.prix * 100)))

    nombre_d_evenements = len(minimums_en_centimes)
    reste_a_partager = int(montant_en_centimes) - sum(minimums_en_centimes)
    part_egale_du_reste = reste_a_partager // nombre_d_evenements

    parts_en_centimes = []
    for minimum_en_centimes in minimums_en_centimes:
        parts_en_centimes.append(minimum_en_centimes + part_egale_du_reste)
    arrondi_restant = int(montant_en_centimes) - sum(parts_en_centimes)
    parts_en_centimes[-1] += arrondi_restant
    return parts_en_centimes
