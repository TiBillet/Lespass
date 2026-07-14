# Phase 0, Etape 3 — Admin Unfold + tests + checkpoint securite

## Prompt

```
On travaille sur la Phase 0 du plan laboutik/doc/PLAN_INTEGRATION.md
Etape 3 sur 3 : admin Unfold + tests unitaires + checkpoint securite.

Les modeles et services sont crees (etapes 1-2 faites).
Lis le plan section 13 (admin Unfold) et memory/tests_validation.md (Phase 0).

Tache :

PARTIE A — Admin Unfold (1 fichier : fedow_core/admin.py)

1. Enregistrer les modeles dans Unfold :
   - Asset : list_display = name, category, currency_code, tenant_origin, active
   - Token : list_display = wallet, asset, value (lecture seule)
   - Transaction : list_display = id, action, amount, sender, receiver, datetime
     (lecture seule, pas de create/edit)
   - Federation : list_display = name, description

2. Section menu Unfold : "Fedow > Monnaies et tokens", "Fedow > Transactions", etc.

PARTIE B — Tests unitaires (1 fichier : tests/pytest/test_fedow_core.py ou similaire)

Ecrire les tests decrits dans memory/tests_validation.md Phase 0 :

1. test_fedow_core_base — creer Asset, Wallet, Token, crediter, verifier value
2. test_id_auto_increment — 2 transactions, verifier id croissant (BigAutoField)
3. test_solde_insuffisant — debiter un wallet vide → SoldeInsuffisant
4. test_pas_de_leak_cross_tenant — assets du tenant A non visibles via service du tenant B

PARTIE C — Checkpoint securite

5. Verifier : Asset.objects.all() retourne TOUT (pas filtre par tenant)
6. Verifier : AssetService.obtenir_assets_du_tenant(tenant_a) ne retourne PAS les assets de tenant_b
7. Verifier : une Transaction cree dans le contexte du tenant A a bien tenant=tenant_a

Lancer les tests :
docker exec lespass_django poetry run pytest tests/pytest/test_fedow_core.py -v

⚠️ Si les tests necessitent des fixtures tenant, regarde comment les tests
   existants dans tests/pytest/ configurent les tenants (conftest.py).
⚠️ Ne modifie PAS les modeles ou les services. Si un test echoue, signale-le.
```

## Verification

- Tous les tests passent (4 tests minimum)
- Le test de leak cross-tenant est le plus important
- L'admin affiche les modeles fedow_core dans le bon menu

## Modele recommande

Sonnet — tests + admin, pattern repetitif
