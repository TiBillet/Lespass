"""
Structure des payloads WebSocket envoyés par _ws_push() vers le kiosk et le dashboard admin.

Tous les champs sont optionnels (total=False) car le payload varie selon le contexte.
Champs TOUJOURS présents : tireuse_bec, present, authorized, vanne_ouverte, message.
"""
from typing import TypedDict


class WsPayload(TypedDict, total=False):
    # --- Identité de la tireuse (toujours présents) ---
    tireuse_bec: str           # Nom lisible de la tireuse
    tireuse_bec_uuid: str      # UUID de la tireuse (absent sur les erreurs très précoces)
    present: bool              # Carte physiquement détectée
    authorized: bool           # Tirage autorisé
    vanne_ouverte: bool        # Vanne ouverte côté Pi
    message: str               # Message affiché sur le kiosk

    # --- Carte / session normale ---
    uid: str                   # UID RFID de la carte
    liquid_label: str          # Nom de la boisson affichée
    balance: str               # Solde de la carte (Decimal sérialisé en str)
    prix_litre: str            # Prix effectif au litre (Decimal sérialisé en str)
    currency: str              # Symbole monétaire, toujours "€" (ex-champ monnaie, supprimé en Phase 1)

    # --- Niveau du réservoir ---
    reservoir_ml: float        # Volume restant estimé (ml)
    reservoir_max_ml: float    # Volume de référence du fût plein (ml)

    # --- Volume versé en cours de tirage ---
    volume_ml: float           # Volume cumulé depuis le début de la session (ml)
    debit_cl_min: float        # Débit instantané (cL/min)

    # --- Mode maintenance ---
    maintenance: bool          # True si la tireuse est en mode nettoyage

    # --- Contrôle de flux ---
    force_close: bool          # True si Django demande la fermeture immédiate (solde épuisé)
