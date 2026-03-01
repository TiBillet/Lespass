# Phase 3, Etape 3 — Stress test 4 festivals

## Prompt

```
On travaille sur la Phase 3 du plan laboutik/doc/PLAN_INTEGRATION.md
Etape 3 sur 3 : le stress test. Lis le plan section 17.8.

Les paiements NFC, recharges et adhesions fonctionnent (etapes 1-2 faites).
Avant de deployer en prod, on doit valider la tenue en charge.

Tache (1 fichier : tests/stress/test_charge_festival.py) :

1. Setup du test :
   - 4 tenants (Customers.Client) avec chacun :
     - 1 asset TLF (monnaie locale fiduciaire)
     - 1 asset federe (partage entre les 4 via Federation)
     - 500 wallets avec Token (solde initial 10000 centimes chacun)
     - 1 PointDeVente avec 10 Products (chacun avec 1 Price)

2. Charge :
   - concurrent.futures.ThreadPoolExecutor(max_workers=80)
   - 4 × 500 = 2000 transactions concurrentes
   - Chaque thread : prendre un wallet aleatoire, payer un article aleatoire
   - Mix : 70% asset local, 30% asset federe

3. Metriques a mesurer :
   - Temps moyen par transaction
   - P95 (95e percentile)
   - Nombre de deadlocks
   - Nombre d'erreurs (hors SoldeInsuffisant qui est normal)

4. Verifications post-charge :
   - sum(Token.value) pour chaque asset == sum attendue
     (somme initiale - somme des transactions reussies)
   - manage.py verify_transactions passe sans erreur
   - 0 leak cross-tenant : aucun Token d'un tenant visible par un autre
   - id (BigAutoField) sans trou

5. Seuils de reussite :
   - Temps moyen < 50ms
   - P95 < 200ms
   - 0 deadlock
   - 0 leak cross-tenant

6. Si echec : afficher EXPLAIN ANALYZE des queries les plus lentes

⚠️ Ce test est LENT. Ne pas le mettre en CI.
⚠️ A lancer manuellement sur un env de staging.
⚠️ NE PAS modifier le code de production. Juste le fichier de test.
```

## Verification

- Le test tourne sans crash
- Les 4 seuils sont respectes
- verify_transactions passe
- Les sommes de Token sont coherentes

## Modele recommande

Sonnet — code de test, pattern repetitif
