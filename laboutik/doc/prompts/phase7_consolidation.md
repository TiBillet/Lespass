# Phase 7 — Consolidation et nettoyage

## Prompt

```
On travaille sur la Phase 7 du plan laboutik/doc/PLAN_INTEGRATION.md
(section 15 + section 17.7).

⚠️ CETTE PHASE NE DEMARRE QUE QUAND :
- Tous les anciens tenants sont migres (Phase 6 terminee pour chaque tenant)
- Plus aucun tenant n'a server_cashless renseigne
- Le mainteneur a valide la checklist section 17.7

Lis le plan section 15 (Phase 7) et section 17.7 (checklist mainteneur).

Tache :

PARTIE A — Recalcul des hash (fedow_core/management/commands/recalculate_hashes.py)

1. Parcourir toutes les Transaction par id croissant (BigAutoField)
2. Calculer le hash SHA256 individuel (pas de chaine) pour chacune
3. Mettre a jour le champ hash
4. Afficher la progression
5. Tests : memory/tests_validation.md Phase 7

PARTIE B — Migration Django : hash NOT NULL

6. Creer une migration Django qui rend le champ hash NOT NULL + UNIQUE
   ⚠️ A lancer APRES recalculate_hashes (sinon echec garanti)

PARTIE C — Nettoyage des mocks

7. Supprimer :
   - laboutik/utils/mockData.py
   - laboutik/utils/dbJson.py
   - laboutik/utils/mockDb.json
   - laboutik/utils/method.py
   - Les imports de ces fichiers dans views.py (doit etre deja fait en Phase 2-3)

PARTIE D — Nettoyage fedow_connect

8. Supprimer :
   - fedow_connect/fedow_api.py (700 lignes HTTP → remplace par fedow_core/services.py)
   - fedow_connect.Asset (miroir cache)
   - fedow_connect.FedowConfig (config connexion distante)
9. Adapter :
   - fedow_public/views.py → utiliser fedow_core.Asset au lieu de fedow_connect.Asset
   - Garder fedow_connect/validators.py si reutilises
   - Garder fedow_connect/utils.py (Fernet encryption) si reutilise

PARTIE E — Tests finaux

10. manage.py check
11. Tests Playwright complets (a definir avec le mainteneur)
12. verify_transactions sur chaque tenant

⚠️ Chaque suppression = verifier que plus aucun import ne reference le fichier.
⚠️ NE PAS supprimer fedow_connect entierement (garder validators/utils si utilises).
```

## Verification

- recalculate_hashes termine sans erreur
- Migration hash NOT NULL appliquee
- Tous les mocks supprimes, aucun import casse
- fedow_connect nettoye
- manage.py check passe
- verify_transactions passe pour tous les tenants

## Modele recommande

Sonnet — nettoyage methodique, pattern repetitif
