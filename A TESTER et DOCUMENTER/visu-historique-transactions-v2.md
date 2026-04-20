# Visualisation historique transactions V2 (Session 33)

## Ce qui a ete fait

La vue `MyAccount.transactions_table` (`BaseBillet/views.py`) dispatch sur `peut_recharger_v2(user)` :

- Verdict `"v2"` -> nouvelle methode `_transactions_table_v2` qui lit `fedow_core.Transaction` local + reconstitue les wallets ephemeres via les FUSIONs(receiver=user.wallet)
- Autres verdicts -> code V1 actuel inchange (appel `FedowAPI`)

Nouveau partial `reunion/partials/account/transaction_history_v2.html` : table 4 colonnes (Date \| Action \| Montant ±signe coloré \| Structure) + pagination HTMX 40/page.

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | Dispatch + methode + 2 helpers module-level |
| `BaseBillet/templates/reunion/partials/account/transaction_history_v2.html` | Nouveau partial |
| `tests/pytest/test_transactions_table_v2.py` | 11 tests pytest |
| `locale/*/LC_MESSAGES/django.po` | 7 strings i18n |
| `CHANGELOG.md` | Entree bilingue |

## Tests a realiser

### Test 1 : Scenario nominal (user V2 avec recharge)
1. Se connecter `admin@admin.com` sur `https://lespass.tibillet.localhost/`
2. Aller sur `/my_account/balance/`
3. Recharger 20€ via le bouton "Recharger TiBillets" → carte test `4242 4242 4242 4242`
4. Cliquer sur "Historique des transactions"
5. Verifier :
   - Section "Transaction history" avec 1 ligne "Recharge +20,00 TiBillets / TiBillet"
   - Date en naturaltime ("Il y a quelques secondes") + date brute (JJ/MM/AAAA HH:MM)
   - Montant en vert (+20,00)
   - Colonne Structure = "TiBillet"

### Test 2 : User avec carte fusionnee (historique complet)
1. Depuis la caisse POS V2 d'un lieu test : ajouter manuellement un wallet_ephemere lie a une carte test + creer une transaction SALE/REFILL sur ce wallet
2. Identifier l'user sur cette carte (flow `fusionner_wallet_ephemere`)
3. Se connecter avec ce user sur `/my_account/balance/`
4. Verifier dans l'historique :
   - Les tx d'avant identification (SALE sur le lieu)
   - La ligne FUSION "Rattachement carte → compte" avec "Carte #{number}" dans Structure
   - Les tx d'apres identification

### Test 3 : User sans wallet (empty state)
1. Creer un compte neuf, ne pas recharger
2. Aller sur `/my_account/balance/` → cliquer "Historique des transactions"
3. Verifier :
   - Icone horloge + message "Aucune transaction pour l'instant."

### Test 4 : Pagination
1. Avoir >40 transactions sur un compte user V2 (seed manuel)
2. Aller sur `/my_account/balance/` → historique
3. Verifier :
   - 40 lignes affichees
   - Nav en bas : "Previous disabled | Page 1/N | Next"
   - Clic Next → page 2 (HTMX swap, pas de full reload)

### Test 5 : Non-regression V1 legacy
1. Tenant avec `Configuration.server_cashless` renseigne (ex: connecté à LaBoutik externe)
2. Aller sur `/my_account/balance/` → historique
3. Verifier l'ancien tableau V1 (colonnes Value \| Action \| Date \| Path) s'affiche
4. Inspecter HTML : **pas** de `data-testid="tx-v2-container"`

### Commandes DB utiles

```python
# docker exec lespass_django poetry run python /DjangoFiles/manage.py shell_plus

from AuthBillet.models import TibilletUser
from fedow_core.models import Transaction
from django.db.models import Q

user = TibilletUser.objects.get(email="admin@admin.com")
tx = Transaction.objects.filter(
    Q(sender=user.wallet) | Q(receiver=user.wallet)
).select_related('asset', 'sender__origin', 'receiver__origin', 'card').order_by('-datetime')
for t in tx[:10]:
    print(f"{t.datetime} | {t.get_action_display()} | {t.amount} | {t.asset.name}")

# Reconstitue wallets historiques via FUSION.
from fedow_core.models import Transaction
fusions = Transaction.objects.filter(action=Transaction.FUSION, receiver=user.wallet)
wallets_historiques = {user.wallet.pk} | {f.sender_id for f in fusions}
print(f"Wallets historiques : {wallets_historiques}")
```

### Commande pytest rapide

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py -v --api-key dummy
```

## Compatibilite

- V1 legacy inchange (template `transaction_history.html`, flow `FedowAPI`)
- `FedowAPI` toujours appele pour `v1_legacy`, `wallet_legacy`, `feature_desactivee`
- Aucune migration DB
- Pas d'impact sur le POS V2 ni la billetterie

## Hors scope (sessions futures)

- Migration wallet_legacy -> fedow_core local (avec import des tx historiques)
- Suppression de `FedowAPI`
- Filtres avancés (par asset, par action, par date)
- Export CSV/PDF de l'historique
- Regroupement par date ("Aujourd'hui", "Hier"...)
- Format des montants localisé FR (virgule au lieu de point) — actuellement `floatformat:2` Django
