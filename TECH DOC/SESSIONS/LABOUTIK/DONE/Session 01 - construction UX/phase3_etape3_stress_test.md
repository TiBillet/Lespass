# Phase 3, Etape 3 — Stress test + verify_transactions

## Prompt

```
On travaille sur la Phase 3 du plan laboutik/doc/PLAN_INTEGRATION.md
Etape 3 sur 3 : le stress test ET le management command verify_transactions.
Lis le plan section 17.8.

Les paiements NFC, recharges et adhesions fonctionnent (etapes 1-2 faites).
Avant de deployer en prod, on doit valider la tenue en charge.

⚠️ PREREQUIS — verify_transactions :
Le management command `verify_transactions` est utilise dans le stress test
ET dans les phases 6-7. Il doit etre cree ICI, pas plus tard.

Tache en 2 parties :

PARTIE A — verify_transactions (fedow_core/management/commands/verify_transactions.py)

1. Verification de la sequence globale :
   - Parcourir Transaction.objects.order_by('id')
   - Verifier qu'il n'y a pas de trou dans les id (ex: 1,2,4 = trou)
   - Attention : les trous sont normaux apres un rollback PostgreSQL
     (la sequence avance meme si le INSERT echoue).
     → Signaler les trous comme WARNING, pas comme ERROR.

2. Verification des soldes :
   - Pour chaque (wallet, asset), calculer :
     total_credite = sum(Transaction.amount WHERE receiver=wallet AND asset=asset)
     total_debite = sum(Transaction.amount WHERE sender=wallet AND asset=asset)
     solde_attendu = total_credite - total_debite
   - Comparer avec Token.value
   - Si divergence → ERROR

3. Verification tenant :
   - Chaque Transaction doit avoir un tenant non null
   - Chaque Transaction.asset.tenant_origin doit etre le tenant de la transaction
     OU l'asset doit etre federe avec ce tenant

4. Options :
   - --tenant=SCHEMA_NAME : filtrer par tenant
   - --verbose : afficher chaque verification
   - --fix-tokens : recalculer Token.value depuis les transactions (DANGEREUX, demander confirmation)

Lancer : docker exec lespass_django poetry run python manage.py verify_transactions

PARTIE B — Stress test (tests/stress/test_charge_festival.py)

5. Setup du test :
   - 4 tenants (Customers.Client) avec chacun :
     - 1 asset TLF (monnaie locale fiduciaire)
     - 1 asset federe (partage entre les 4 via Federation)
     - 500 wallets avec Token (solde initial 10000 centimes chacun)
     - 1 PointDeVente avec 10 Products (chacun avec 1 Price)

6. Charge :
   - concurrent.futures.ThreadPoolExecutor(max_workers=80)
   - 4 × 500 = 2000 transactions concurrentes
   - Chaque thread : prendre un wallet aleatoire, payer un article aleatoire
   - Mix : 70% asset local, 30% asset federe

7. Metriques a mesurer :
   - Temps moyen par transaction
   - P95 (95e percentile)
   - Nombre de deadlocks
   - Nombre d'erreurs (hors SoldeInsuffisant qui est normal)

8. Verifications post-charge :
   - sum(Token.value) pour chaque asset == sum attendue
     (somme initiale - somme des transactions reussies)
   - manage.py verify_transactions passe sans erreur
   - 0 leak cross-tenant : aucun Token d'un tenant visible par un autre
   - Pas de trou anormal dans les id

9. Seuils de reussite :
   - Temps moyen < 50ms
   - P95 < 200ms
   - 0 deadlock
   - 0 leak cross-tenant

10. Si echec : afficher EXPLAIN ANALYZE des queries les plus lentes

⚠️ Ce test est LENT (plusieurs minutes). Ne pas le mettre en CI.
⚠️ A lancer manuellement sur un env de staging.
⚠️ NE PAS modifier le code de production. Juste les fichiers de test + management command.
⚠️ Creer le dossier tests/stress/ s'il n'existe pas.
```

## Tests

### Partie A — verify_transactions

```python
# Tests dans tests/pytest/test_verify_transactions.py :
#
# 1. test_verify_clean — base saine → 0 erreur
# 2. test_verify_detecte_token_divergent — Token.value modifie manuellement → ERROR
# 3. test_verify_detecte_transaction_sans_tenant — Transaction.tenant=None → ERROR
# 4. test_verify_option_tenant — --tenant filtre correctement
```

Lancer : `docker exec lespass_django poetry run pytest tests/pytest/test_verify_transactions.py -v`

### Partie B — Stress test

Lancer :
```bash
docker exec lespass_django poetry run python -m pytest tests/stress/test_charge_festival.py -v -s --timeout=300
```

Le test affiche un rapport :
```
=== Stress Test Results ===
Transactions attempted: 2000
Transactions succeeded: 1847
SoldeInsuffisant (normal): 153
Errors: 0
Deadlocks: 0
Avg time: 23ms
P95: 89ms
Token sums: CONSISTENT
Cross-tenant leak: NONE
verify_transactions: PASS
```

### Verification manuelle

- verify_transactions termine sans ERROR sur une base propre
- Le stress test tourne sans crash
- Les 4 seuils sont respectes (temps, deadlocks, leak, sommes)

## Checklist fin d'etape

- [ ] verify_transactions fonctionne (tester sur la base actuelle)
- [ ] Stress test passe les 4 seuils
- [ ] Mettre a jour CHANGELOG.md
- [ ] Creer `A TESTER et DOCUMENTER/phase3-etape3-stress-test.md`
- [ ] **Checkpoint securite Phase 3** : atomicite + stress + isolation tenant

## Modele recommande

Sonnet — code de test, pattern repetitif (sauf verify_transactions : Opus si la logique est complexe)
