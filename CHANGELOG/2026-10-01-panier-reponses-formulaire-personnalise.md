# Panier : réponses au formulaire personnalisé validées comme le parcours direct / Cart: custom form answers validated like the direct flow

**Date :** 2026-10-01
**Migration :** Non

**FR :** Quand on ajoutait une adhésion ou des billets au panier, les réponses au formulaire
personnalisé étaient recopiées telles quelles depuis le formulaire. Le parcours sans panier,
lui, passe par `build_custom_form_from_request` (`BaseBillet/validators.py`). Les deux
parcours ne rangeaient donc pas les réponses de la même façon :

| | Parcours direct | Panier (avant) |
|---|---|---|
| Clé de la réponse | Libellé de la question | Clé technique du champ |
| Case à cocher | Oui / non | Texte « on » |
| Choix multiple | Liste de toutes les valeurs | Dernière valeur cochée seulement |
| Question obligatoire | Vérifiée | Non vérifiée |
| Choix hors liste | Refusé | Accepté |

Conséquence visible : une réponse enregistrée par le panier n'était pas retrouvée sous le
libellé de sa question, alors que le reste du code (affichage dans l'admin, éditeur de
réponses des adhésions, export) lit les réponses sous ce libellé.

Le panier utilise maintenant la même fonction que le parcours direct. Une question obligatoire
sans réponse, ou un choix invalide, bloque l'ajout au panier avec un message qui nomme la
question. Pour les billets, seules les questions des produits dont au moins un billet est
demandé sont lues, comme dans `ReservationValidator` : une question obligatoire d'un autre
produit de l'événement ne bloque pas l'ajout.

Le panier n'étant pas encore en production, aucune réponse n'a été enregistrée avec l'ancien
format : pas de reprise de données.

**EN :** Adding a membership or tickets to the cart copied the custom form answers as-is
(field key, raw text, last value only for a multiple choice, no validation). The cart now
uses the same builder as the direct flow, `build_custom_form_from_request`: answers are
stored under the question label, booleans and lists are converted, required questions and
invalid choices are refused with a message naming the question. For tickets, only the
questions of products with a requested ticket are read. The cart is not in production yet:
no data migration.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | Nouveau helper `reponses_du_formulaire_personnalise_pour_le_panier` (appelle `build_custom_form_from_request`, transforme l'erreur en message lisible) ; utilisé par `PanierMVT.add_membership` et `PanierMVT.add_tickets_batch` |
| `BaseBillet/views.py` | Nouveau helper `quantite_de_billets_demandee` : lecture de la quantité saisie, sortie de la boucle de `add_tickets_batch` (même règle qu'avant) pour savoir quels produits sont demandés avant l'ajout |
| `tests/pytest/test_panier_formulaire_personnalise.py` | Nouveaux tests : rangement sous le libellé, question obligatoire, choix multiple, case à cocher, question d'un produit non choisi, adhésion |

### Comment tester / How to test

1. Ajouter à un produit billet une question obligatoire et une question à choix multiple.
2. Sur la page de l'événement, ajouter un billet au panier sans répondre à la question
   obligatoire : message d'erreur nommant la question, rien n'est ajouté.
3. Répondre, cocher deux choix, ajouter au panier, payer.
4. Admin > Réservations > la réservation : les deux réponses apparaissent sous le libellé
   des questions, avec les deux choix.

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_formulaire_personnalise.py -v
```
