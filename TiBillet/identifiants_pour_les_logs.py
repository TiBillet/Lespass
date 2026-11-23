"""
Identifiants raccourcis pour les logs.
/ Shortened identifiers for logs.

LOCALISATION : TiBillet/identifiants_pour_les_logs.py

Les logs partent dans la supervision (OpenObserve) et y restent un an. On n'y ecrit
jamais un tag NFC entier ni un e-mail : on ecrit le debut de l'identifiant, assez
pour recouper un cas precis, pas assez pour s'en servir.
- Carte : les 4 premiers caracteres du tag NFC ou du numero imprime. Le tag entier
  permet de fabriquer un clone de la carte.
- Personne, wallet, ligne de vente : les 8 premiers caracteres de l'UUID. Pour une
  personne, on le retrouve dans l'URL de sa fiche admin
  (/admin/AuthBillet/humanuser/<uuid>/change/).
- JAMAIS uuid_court() sur l'uuid d'une carte (qrcode_uuid) : ses 8 premiers
  caracteres SONT le numero imprime. Une carte passe toujours par carte_courte().
/ Logs go to the monitoring and stay a year: never a full NFC tag nor an email.
  Card: first 4 chars. Person, wallet, sale line: first 8 chars of the UUID.

Fedow a les memes fonctions, avec les memes noms : fedow_core/utils.py.
/ Fedow has the same functions, same names: fedow_core/utils.py.
"""

NOMBRE_DE_CARACTERES_GARDES_POUR_UNE_CARTE = 4
NOMBRE_DE_CARACTERES_GARDES_POUR_UN_UUID = 8


def carte_courte(tag_ou_numero_de_carte):
    """
    Renvoie le debut d'un tag NFC ou d'un numero de carte, par exemple « 89EE… ».
    / Returns the start of an NFC tag or a card number, e.g. "89EE…".
    """
    if not tag_ou_numero_de_carte:
        return "aucune"
    texte_de_la_carte = str(tag_ou_numero_de_carte).upper()
    debut_de_la_carte = texte_de_la_carte[:NOMBRE_DE_CARACTERES_GARDES_POUR_UNE_CARTE]
    return f"{debut_de_la_carte}…"


def uuid_court(valeur_uuid):
    """
    Renvoie les 8 premiers caracteres d'un UUID, par exemple « 1a2b3c4d ».
    / Returns the first 8 characters of a UUID, e.g. "1a2b3c4d".
    """
    if not valeur_uuid:
        return "aucun"
    texte_de_l_uuid = str(valeur_uuid)
    return texte_de_l_uuid[:NOMBRE_DE_CARACTERES_GARDES_POUR_UN_UUID]
