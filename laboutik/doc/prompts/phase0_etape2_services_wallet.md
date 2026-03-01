# Phase 0, Etape 2 — Services fedow_core

## Prompt

```
On travaille sur la Phase 0 du plan laboutik/doc/PLAN_INTEGRATION.md
Etape 2 sur 3 : la couche de service fedow_core/services.py.

Les modeles sont crees (etape 1 faite). Lis le plan section 6 (remplacement
fedow_connect) et le MEMORY.md.

Contexte :
- fedow_core est en SHARED_APPS. Pas d'isolation auto par tenant.
- Chaque methode de service DOIT filtrer par tenant.
- Le service remplace fedow_connect/fedow_api.py (700 lignes HTTP).
- Pattern FALC : methodes statiques explicites, noms verbeux, commentaires bilingues.
- Tout est en centimes (int).

Tache (1 fichier : fedow_core/services.py) :

1. AssetService :
   - obtenir_assets_du_tenant(tenant) — assets crees par ce tenant
   - obtenir_assets_accessibles(tenant) — assets du tenant + federes
   - creer_asset(tenant, name, category, currency_code, wallet_origin)

2. WalletService :
   - obtenir_solde(wallet, asset) — Token.value pour un asset
   - obtenir_solde_total(wallet) — tous les Token du wallet
   - crediter(wallet, asset, montant_en_centimes) — augmenter Token.value
   - debiter(wallet, asset, montant_en_centimes) — diminuer Token.value
     → raise SoldeInsuffisant si value < montant
   - Les operations crediter/debiter doivent etre dans transaction.atomic()
     avec select_for_update() sur le Token (verrouillage par ligne)

3. TransactionService :
   - creer(sender, receiver, asset, amount, action, **kwargs)
     → dans transaction.atomic() :
       debiter sender + crediter receiver + creer Transaction
     → l'id est auto-increment (BigAutoField, geré par Django)
     → le hash est null (Phase 2 du plan de migration, pas de calcul)
   - creer_vente(sender_wallet, receiver_wallet, asset, montant, card=None, primary_card=None)
     → wrapper FALC pour action=SALE
   - creer_recharge(sender_wallet, receiver_wallet, asset, montant)
     → wrapper FALC pour action=REFILL

4. Creer l'exception SoldeInsuffisant dans fedow_core/exceptions.py

⚠️ NE PAS creer de vues, d'URLs, ou d'admin. Juste le service.
⚠️ NE PAS toucher aux modeles (deja faits en etape 1).
⚠️ Les operations sur Token (crediter/debiter) utilisent select_for_update()
   sur la LIGNE Token, pas sur l'asset. C'est un verrou par ligne, pas cross-tenant.

Verification :
docker exec lespass_django poetry run python manage.py check
docker exec lespass_django poetry run python -c "from fedow_core.services import WalletService, TransactionService, AssetService; print('OK')"
```

## Verification

- Le service importe sans erreur
- `manage.py check` passe
- Les methodes sont explicites, FALC, commentees FR/EN
- select_for_update() est sur Token, pas sur Asset ou Transaction

## Modele recommande

**Opus** — atomicite, verrous, logique metier critique
