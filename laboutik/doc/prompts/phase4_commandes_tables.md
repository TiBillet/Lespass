# Phase 4 — Mode restaurant (commandes + tables)

## Prompt

```
On travaille sur la Phase 4 du plan laboutik/doc/PLAN_INTEGRATION.md
(section 10.2 + section 15). Mode restaurant.

Phases 0-3 faites. Le POS fonctionne en service direct (paiement immediat).
Maintenant on ajoute le mode "commandes par table".

Lis le plan section 10.2 (CommandeSauvegarde, ArticleCommandeSauvegarde)
et le front existant dans les templates laboutik/ pour comprendre le flux.

Tache :

PARTIE A — Modeles (laboutik/models.py)

1. CommandeSauvegarde :
   - uuid PK, service (UUIDField), responsable FK TibilletUser
   - table FK Table nullable, datetime, statut choices (OPEN/SERVED/PAID/CANCEL)
   - commentaire, archive

2. ArticleCommandeSauvegarde :
   - commande FK, product FK Product, price FK Price
   - qty SmallIntegerField, reste_a_payer IntegerField (centimes)
   - reste_a_servir SmallIntegerField
   - statut choices (EN_ATTENTE/EN_COURS/PRET/SERVI/ANNULE)

3. Migrations

PARTIE B — Vues (laboutik/views.py)

4. Ajouter les actions necessaires sur CaisseViewSet ou un nouveau
   CommandeViewSet (voir ce qui est le plus FALC) :
   - Ouvrir une table (changer statut → O)
   - Ajouter des articles a la commande
   - Marquer une commande comme servie
   - Payer une commande (reutiliser les methodes de paiement existantes)

5. Adapter les templates si necessaire pour le flux commande.

PARTIE C — Admin + tests

6. Admin Unfold : CommandeSauvegarde (lecture seule, historique)
7. Tests : ouvrir table → ajouter articles → payer → table liberee

⚠️ Le front JS pour les tables existe deja dans les templates.
   Verifier ce qui est fait avant de coder.
⚠️ NE PAS modifier les vues de paiement (reutiliser).
```

## Verification

- Ouvrir une table, ajouter des articles, payer, table liberee
- CommandeSauvegarde et ArticleCommandeSauvegarde crees en DB
- Le paiement reutilise les methodes existantes (especes, CB, NFC)

## Modele recommande

Sonnet
