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
