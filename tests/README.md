# Rapport des Tests - Lespass

Ce document liste les tests présents dans le projet, leur classification et leur statut d'exécution actuel.

## Classification des Tests

Les tests sont principalement des tests d'intégration pour l'API v2, utilisant le framework `pytest`.

### 1. API v2 - Intégration (Pytest)

Ces tests vérifient le bon fonctionnement des endpoints de l'API v2 en effectuant des requêtes HTTP réelles.

*   **Partie : Événements (Events)**
    *   `tests/pytest/test_event_create.py` : Création simple d'un événement.
    *   `tests/pytest/test_event_create_extended.py` : Création d'un événement avec des champs schema.org étendus.
    *   `tests/pytest/test_event_delete.py` : Création puis suppression d'un événement.
    *   `tests/pytest/test_event_images.py` : Création d'un événement avec upload d'images.
    *   `tests/pytest/test_event_retrieve.py` : Récupération d'un événement par son UUID.
    *   `tests/pytest/test_events_list.py` : Liste des événements.
*   **Partie : Adresses Postales (Postal Address)**
    *   `tests/pytest/test_postal_address_crud.py` : Cycle de vie (Création, Liste) des adresses postales.
    *   `tests/pytest/test_postal_address_images.py` : Création d'une adresse avec images.
*   **Partie : Mixte (Events & Postal Address)**
    *   `tests/pytest/test_event_link_address.py` : Association d'une adresse à un événement existant.
*   **Partie : Ventes (Sales)**
    *   `tests/pytest/api/test_sales_api.py` : Liste et récupération des lignes de vente.

---

## Résultats de l'exécution

Les tests ont été lancés depuis l'hôte avec la commande suivante :
`poetry run pytest tests/pytest/ --api-key PvHzgK6L.OiN6kKYJSnj2zomdMOqSOAU1B6as42N5`

**Résumé : 10 réussites, 0 échec.**

### ✅ Tests qui fonctionnent (PASS)

| Fichier | Description |
| :--- | :--- |
| `tests/pytest/test_event_create.py` | Création simple d'un événement |
| `tests/pytest/test_event_create_extended.py` | Création d'un événement avec champs schema.org étendus |
| `tests/pytest/test_event_images.py` | Création d'un événement avec upload d'images |
| `tests/pytest/test_event_delete.py` | Création puis suppression d'un événement |
| `tests/pytest/test_events_list.py` | Liste des événements |
| `tests/pytest/test_event_retrieve.py` | Récupération d'un événement par son UUID |
| `tests/pytest/test_postal_address_crud.py` | CRUD Adresses postales |
| `tests/pytest/test_postal_address_images.py` | Adresses postales avec images |
| `tests/pytest/test_event_link_address.py` | Liaison adresse à un événement |
| `tests/pytest/api/test_sales_api.py` | Liste et récupération des lignes de vente |

### ❌ Tests qui ne fonctionnent pas (FAIL)

Aucun. Tous les tests d'intégration de l'API v2 sont désormais fonctionnels.

---

## Notes Techniques sur les corrections apportées

1.  **Violation de contrainte `NOT NULL` (Events)** : Le sérialiseur de création d'événement (`api_v2/serializers.py`) a été corrigé pour inclure explicitement `archived=False` lors de la création en base de données. Les champs optionnels avec des valeurs par défaut dans le modèle Django sont désormais gérés correctement pour éviter de passer des valeurs `None` quand elles ne sont pas fournies.
2.  **Test Sales API sur l'hôte** : Le test `tests/pytest/api/test_sales_api.py` nécessitait l'accès à l'ORM Django pour préparer les données. Une commande management `prepare_sales_test_data` a été créée pour effectuer cette préparation de manière isolée. Le test a été adapté pour appeler cette commande via `docker exec` lorsqu'il détecte qu'il est exécuté depuis l'hôte, permettant ainsi de faire passer les tests depuis l'hôte tout en gardant une isolation correcte des données.
