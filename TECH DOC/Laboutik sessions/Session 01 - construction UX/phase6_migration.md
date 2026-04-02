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
- verify_transactions existe deja (cree en Phase 3)

⚠️ FORMAT DU DUMP :
Avant de commencer, DEMANDER AU MAINTENEUR :
- Comment generer le dump depuis l'ancien Fedow (pg_dump ? management command ? JSON ?)
- Comment generer le dump depuis l'ancien LaBoutik
- Quel format (JSON prefere pour la portabilite)
- Si un script d'export est necessaire cote ancien serveur, le signaler.

Le format JSON attendu pour Fedow (a confirmer avec le mainteneur) :
{
  "assets": [{"uuid": "...", "name": "...", "category": "...", ...}],
  "wallets": [{"uuid": "...", "email": "...", "public_pem": "...", ...}],
  "cards": [{"tag_id": "...", "uuid": "...", "wallet_uuid": "...", ...}],
  "tokens": [{"wallet_uuid": "...", "asset_uuid": "...", "value": 1234, ...}],
  "transactions": [{"uuid": "...", "hash": "...", "sender_uuid": "...", ...}],
  "federations": [{"name": "...", "assets_uuids": [...], "places_uuids": [...]}]
}

Tache :

PARTIE A — Script d'export ancien Fedow (OPTIONNEL, a valider)

0. Si le mainteneur le demande, creer un script d'export :
   OLD_REPOS/Fedow/fedow_core/management/commands/export_fedow_data.py
   - Serialise les modeles Fedow en JSON
   - Format decrit ci-dessus
   - ⚠️ Ce script tourne sur l'ANCIEN serveur, pas sur Lespass

PARTIE B — Import Fedow (fedow_core/management/commands/import_fedow_data.py)

1. Accepte un dump JSON en entree (--source=path/to/dump.json)
2. Ordre d'import (respecter les FK) :
   Asset → Wallet → CarteCashless → Token → Transaction → Federation
3. Regles :
   - Preserver les UUID originaux (uuid=ancien_uuid sur chaque objet)
   - Mapper FedowUser → TibilletUser (par email, case-insensitive)
     Si aucun TibilletUser → CREER un user (minimal : email + is_active=False)
     Logger un WARNING pour chaque user cree
   - Mapper Place → Customers.Client (par domaine ou UUID)
     Si aucun Client → ERREUR (le tenant doit exister avant l'import)
   - Marquer migrated=True sur les Transaction importees
   - L'id est auto-attribue par Django (BigAutoField, ordre chronologique)
   - Le hash original est conserve tel quel (sera recalcule en Phase 7)
   - Dry-run par defaut (--commit pour appliquer)
4. Afficher un resume detaille apres chaque import :
   - Nombre d'objets importes par type
   - Nombre de users crees
   - Nombre d'erreurs/warnings
   - Somme des Token.value par asset

PARTIE C — Import LaBoutik (laboutik/management/commands/import_laboutik_data.py)

5. Idem pour les donnees LaBoutik :
   CategorieProduct → Product enrichi (champs POS) → PointDeVente → CartePrimaire → Table
6. Regles specifiques :
   - Les Categorie LaBoutik → CategorieProduct (mapper couleur inline → champs hexa)
   - Les Articles → Product (mapper Methode → methode_caisse, creer Price en euros)
   - Les MoyenPaiement → Asset fedow_core (mapper par name ou UUID)
   - Les ArticleVendu sont DEJA dans LigneArticle (via webhook historique) → ne PAS reimporter
   - Dry-run par defaut (--commit pour appliquer)

PARTIE D — Verification post-import

7. Ajouter des verifications dans les commands (apres --commit) :
   - sum(Token.value) == somme attendue par asset
   - Nombre de Transaction == nombre dans le dump
   - Chaque CarteCashless a un wallet lie
   - manage.py verify_transactions passe

8. Creer un management command `verify_import` (fedow_core/management/commands/verify_import.py) :
   - Compare le dump JSON avec les donnees importees
   - Verifie que chaque UUID du dump existe dans la DB
   - Verifie les sommes de Token
   - Retourne un rapport detaille

⚠️ TOUJOURS en dry-run d'abord. --commit seulement apres validation.
⚠️ NE PAS supprimer les anciens serveurs. NE PAS modifier fedow_connect.
⚠️ Si un doute sur le format du dump → demander au mainteneur.
⚠️ Les anciens serveurs DOIVENT continuer de fonctionner apres l'import.
```

## Tests

### pytest — tests/pytest/test_import_fedow.py

```python
# Tests a ecrire :
#
# 1. test_dry_run_sans_ecriture
#    Setup : dump JSON de test (5 assets, 10 wallets, 50 transactions)
#    Action : import_fedow_data --source=test.json (sans --commit)
#    Verify : count avant == count apres pour tous les modeles
#
# 2. test_import_preserve_uuid
#    Action : import avec --commit
#    Verify : Transaction.objects.get(uuid=uuid_du_dump) existe
#
# 3. test_import_migrated_true
#    Verify : toutes les Transaction importees ont migrated=True
#
# 4. test_import_mapper_user_par_email
#    Setup : TibilletUser avec email "test@test.com" existe
#    Action : import wallet avec email "test@test.com"
#    Verify : le wallet est lie au TibilletUser existant
#
# 5. test_import_cree_user_manquant
#    Setup : pas de TibilletUser avec email "new@test.com"
#    Action : import wallet avec email "new@test.com"
#    Verify : TibilletUser cree avec is_active=False
#
# 6. test_import_tenant_inexistant_erreur
#    Setup : dump reference un Place/Client qui n'existe pas
#    Verify : ERROR, import refuse
#
# 7. test_verify_transactions_post_import
#    Action : import --commit puis verify_transactions
#    Verify : 0 erreur
#
# 8. test_somme_tokens_coherente
#    Verify : sum(Token.value) pour chaque asset == somme dans le dump
```

### pytest — tests/pytest/test_import_laboutik.py

```python
# 9. test_import_categories — Categorie → CategorieProduct
# 10. test_import_articles — Articles → Product + Price
# 11. test_import_pdv — PointDeVente avec M2M products
# 12. test_import_ne_reimporte_pas_articles_vendus — ArticleVendu ignore
```

Lancer : `docker exec lespass_django poetry run pytest tests/pytest/test_import_fedow.py tests/pytest/test_import_laboutik.py -v`

### Verification manuelle

- Import dry-run affiche un resume sans rien ecrire
- Import --commit cree les objets en DB avec les bons UUID
- verify_transactions passe apres l'import
- verify_import compare dump vs DB
- Les anciens serveurs continuent de fonctionner

## Checklist fin d'etape

- [ ] Dry-run OK (resume coherent, 0 erreur)
- [ ] Import --commit OK sur donnees de test
- [ ] verify_transactions passe
- [ ] verify_import passe
- [ ] Les UUID sont preserves
- [ ] Les users manquants sont crees avec is_active=False
- [ ] Somme des Token.value coherente
- [ ] Anciens serveurs toujours fonctionnels
- [ ] Mettre a jour CHANGELOG.md
- [ ] Creer `A TESTER et DOCUMENTER/phase6-migration.md`
- [ ] **Checkpoint securite Phase 6** : UUID pas de collision, migrated=True, transactions locales intactes

## Modele recommande

**Opus** — migration de donnees, zero perte, UUID preservation
