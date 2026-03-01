# Phase 6 — Migration des donnees anciennes

## Prompt

```
On travaille sur la Phase 6 du plan laboutik/doc/PLAN_INTEGRATION.md
(section 14 + section 15 + section 17.7).

⚠️ PHASE CRITIQUE. Migration de vraies donnees de production.
Lis le plan sections 14.1, 14.2, 14.3, et 17.7 (compatibilite production).

Contexte :
- L'ancien Fedow a sa propre DB PostgreSQL (OLD_REPOS/Fedow)
- L'ancien LaBoutik a sa propre DB PostgreSQL (OLD_REPOS/LaBoutik)
- Les UUID doivent etre preserves (UUID Fedow = champ uuid unique dans Lespass)
- Les transactions importees ont migrated=True
- Les 3 anciens serveurs restent allumes pendant toute la migration

Tache :

PARTIE A — Import Fedow (fedow_core/management/commands/import_fedow_data.py)

1. Accepte un dump JSON en entree (--source=path/to/dump.json)
2. Ordre d'import (respecter les FK) :
   Asset → Wallet → CarteCashless → Token → Transaction → Federation
3. Regles :
   - Preserver les UUID originaux
   - Mapper FedowUser → TibilletUser (par email)
   - Mapper Place → Customers.Client (par domaine ou UUID)
   - Marquer migrated=True sur les Transaction importees
   - L'id est auto-attribue par Django (BigAutoField, ordre chronologique)
   - Le uuid original est preserve dans le champ uuid (UUIDField unique)
   - Le hash original est conserve tel quel (sera recalcule en Phase 7)
   - Dry-run par defaut (--commit pour appliquer)

PARTIE B — Import LaBoutik (laboutik/management/commands/import_laboutik_data.py)

4. Idem pour les donnees LaBoutik :
   CategorieProduct (deja dans BaseBillet) → Product enrichi (champs POS) → PointDeVente → CarteMaitresse → Table
5. Les ArticleVendu sont deja dans LigneArticle (via webhook historique)
   → ne PAS reimporter

PARTIE C — Verification (plan section 14.3)

6. Ajouter des verifications post-import dans les commands :
   - sum(Token.value) == somme attendue par asset
   - Nombre de Transaction == nombre dans l'ancien Fedow
   - Chaque CarteCashless a un wallet lie
   - manage.py verify_transactions passe
7. Tests dans memory/tests_validation.md Phase 6

⚠️ TOUJOURS en dry-run d'abord. --commit seulement apres validation.
⚠️ NE PAS supprimer les anciens serveurs. NE PAS modifier fedow_connect.
⚠️ Si un doute sur le format du dump → demander au mainteneur.
```

## Verification

- Import dry-run affiche un resume sans rien ecrire
- Import --commit cree les objets en DB avec les bons UUID
- verify_transactions passe apres l'import
- Les anciens serveurs continuent de fonctionner

## Modele recommande

**Opus** — migration de donnees, zero perte, UUID preservation
