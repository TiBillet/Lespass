# laboutik/utils/method.py
# Fonctions utilitaires pour le calcul des paiements et le traitement du formulaire d'addition.
# Utility functions for payment calculation and addition form processing.
#
# Ces fonctions travaillent sur les données mock (pas de modèles Django).
# These functions work on mock data (no Django models).

from laboutik.utils import mockData


def selectionner_moyens_paiement(point_de_vente, uuids_articles, donnees_post):
    """
    Détermine les moyens de paiement disponibles pour les articles sélectionnés.
    Determines available payment methods for the selected articles.

    Chaque article appartient à un "bt_groupement" qui définit ses moyens de paiement.
    On prend l'union de tous les moyens, filtrée par ce que le point de vente accepte.
    Each article belongs to a "bt_groupement" that defines its payment methods.
    We take the union of all methods, filtered by what the point of sale accepts.

    Args:
        point_de_vente: dict du point de vente avec ses articles et config
        uuids_articles: liste des UUIDs des articles sélectionnés
        donnees_post: données POST du formulaire (non utilisé ici, conservé pour compatibilité)

    Returns:
        liste de codes moyens de paiement acceptés (ex: ["espece", "nfc", "carte_bancaire"])
    """
    moyens_paiement_acceptes = []
    articles_du_pv = point_de_vente['articles']

    for uuid_article in uuids_articles:
        # Récupérer les moyens de paiement définis par le groupement de l'article
        # Get the payment methods defined by the article's grouping
        article = mockData.get_article_from_uuid(uuid_article, articles_du_pv)
        moyens_paiement_article = article['bt_groupement']['moyens_paiement'].split('|')

        for code_moyen in moyens_paiement_article:
            # Éviter les doublons
            # Avoid duplicates
            if code_moyen in moyens_paiement_acceptes:
                continue

            # Vérifier que le point de vente accepte ce moyen de paiement
            # Check that the point of sale accepts this payment method
            moyen_est_accepte = False

            if code_moyen == 'espece' and point_de_vente['accepte_especes']:
                moyen_est_accepte = True

            if code_moyen == 'carte_bancaire' and point_de_vente['accepte_carte_bancaire']:
                moyen_est_accepte = True

            if code_moyen == 'CH' and point_de_vente['accepte_cheque']:
                moyen_est_accepte = True

            # NFC (cashless) est toujours accepté s'il est dans le groupement
            # NFC (cashless) is always accepted if it's in the grouping
            if code_moyen == 'nfc':
                moyen_est_accepte = True

            if moyen_est_accepte:
                moyens_paiement_acceptes.append(code_moyen)

    return moyens_paiement_acceptes


def calculer_total_addition(point_de_vente, uuids_articles, donnees_post):
    """
    Calcule le total de l'addition en euros à partir des articles sélectionnés.
    Calculates the addition total in euros from the selected articles.

    Les prix sont stockés en centimes dans le mock. On divise par 100 à la fin.
    Prices are stored in cents in the mock. We divide by 100 at the end.

    Args:
        point_de_vente: dict du point de vente avec ses articles
        uuids_articles: liste des UUIDs des articles sélectionnés
        donnees_post: données POST contenant les quantités (clé "repid-<uuid>")

    Returns:
        total en euros (float), ex: 12.50
    """
    articles_du_pv = point_de_vente['articles']
    total_en_centimes = 0

    for uuid_article in uuids_articles:
        # Prix unitaire de l'article (en centimes)
        # Unit price of the article (in cents)
        prix_unitaire = mockData.get_article_from_uuid(uuid_article, articles_du_pv)['prix']

        # Quantité sélectionnée par le caissier
        # Quantity selected by the cashier
        quantite = int(donnees_post.get('repid-' + uuid_article))

        total_en_centimes = total_en_centimes + (quantite * prix_unitaire)

    # Convertir en euros / Convert to euros
    total_en_euros = total_en_centimes / 100
    return total_en_euros


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
