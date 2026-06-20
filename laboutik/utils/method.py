# laboutik/utils/method.py
# Fonctions utilitaires pour le traitement du formulaire d'addition.
# Utility functions for addition form processing.


def extraire_uuids_articles(donnees_post):
    """
    Extrait les UUIDs des articles sélectionnés depuis les données POST.
    Extracts selected article UUIDs from POST data.

    Le formulaire d'addition envoie les quantités avec la clé "repid-<uuid>".
    Cette fonction filtre les clés POST pour ne garder que les UUIDs.
    The addition form sends quantities with the key "repid-<uuid>".
    This function filters POST keys to keep only the UUIDs.

    Args:
        donnees_post: QueryDict des données POST

    Returns:
        liste de strings UUID, ex: ["8f08b90d-...", "42ffe511-..."]
    """
    uuids_trouves = []
    for nom_champ in donnees_post:
        # Les champs d'articles commencent par "repid-" suivi de l'UUID
        # Article fields start with "repid-" followed by the UUID
        if nom_champ.startswith("repid-"):
            uuid_article = nom_champ[6:]  # len("repid-") == 6
            uuids_trouves.append(uuid_article)
    return uuids_trouves
