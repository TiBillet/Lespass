# Reprise des recettes arrivées sur le wallet d'un client / Moving takings back from a customer wallet

**Date :** 2026-11-02
**Migration :** Non

## Resume / Summary
**Quoi / What :** nouvelle commande `reprendre_recettes_wallet_client`. Pour un lieu, elle corrige les assets dont `wallet_origin` est le wallet d'un client : les recettes passent vers le wallet du lieu par une transaction TRANSFER, puis l'asset pointe vers le wallet du lieu. / New command that moves takings back to the venue wallet and repoints the assets.

**Pourquoi / Why :** les assets CAB de La Cabine pointent vers le wallet d'une cliente (`CHANGELOG/2026-11-02-asset-wallet-du-lieu.md`). Le correctif de l'admin ne répare pas les assets déjà créés. / The admin fix does not repair existing assets.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `fedow_core/management/commands/reprendre_recettes_wallet_client.py` | Nouvelle commande, passage à blanc par défaut |
| `tests/pytest/test_reprendre_recettes_wallet_client.py` | Nouveaux tests |

---

## Comment tester (a la main) / Manual test
### Lancer la reprise sur un lieu
La caisse du lieu doit être fermée, et une sauvegarde de la base doit être faite avant.

1. Lancer le passage à blanc, qui n'enregistre rien :

```bash
docker exec lespass_django poetry run python manage.py reprendre_recettes_wallet_client --schema la-cabine
```

2. Vérifier ce qui s'affiche : le solde du client doit être égal aux recettes reçues.
3. Noter les ventes à soi-même : elles restent à arbitrer avec le lieu.
4. Lancer la correction :

```bash
docker exec lespass_django poetry run python manage.py reprendre_recettes_wallet_client --schema la-cabine --appliquer
```

### Cas d'arrêt
Si le client a aussi de l'argent à lui, par exemple après une recharge, la commande s'arrête sur « diffère des recettes reçues » et ne change rien. Le cas est alors à examiner à la main.

### Verifs DB / Playwright
- Test automatique : `docker exec lespass_django poetry run pytest tests/pytest/test_reprendre_recettes_wallet_client.py -q`
- Ne pas lancer `verify_transactions --fix-tokens` sur ce lieu : il compte les recharges comme des débits du wallet d'origine.
