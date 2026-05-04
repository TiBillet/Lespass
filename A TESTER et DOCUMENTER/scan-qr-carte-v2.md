# Scan QR carte V2 (fedow_core) — Tests manuels

## Ce qui a ete fait

Bascule du flow public de scan QR vers `fedow_core/services.py:CarteService`.
Dispatch V1/V2 via `Configuration.server_cashless` : les anciens tenants legacy
restent sur `fedow_connect` (HTTP Fedow distant), les nouveaux sur `fedow_core`.

### Modifications
| Fichier | Changement |
|---|---|
| `fedow_core/services.py` | +classe `CarteService` (3 methodes) |
| `fedow_core/exceptions.py` | +3 exceptions metier |
| `BaseBillet/views.py` | Dispatch V1/V2 dans 4 vues |

## Tests a realiser

### Test 1 : Scan carte vierge -> formulaire -> login
1. Creer une `CarteCashless` sur le tenant `lespass` via l'admin (ou fixture).
2. `Configuration.server_cashless` sur lespass doit etre `None` (V2 actif).
3. Aller sur `https://lespass.tibillet.localhost/qr/<carte.uuid>/`
4. Verification : formulaire email affiche.
5. Saisir email + prenom + nom, soumettre.
6. Verification : redirection vers `/my_account/`, user logue.
7. Verification en base :
```
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from QrcodeCashless.models import CarteCashless
carte = CarteCashless.objects.get(uuid='<uuid>')
print(f'user={carte.user.email}')
print(f'wallet_ephemere={carte.wallet_ephemere}')
print(f'user.wallet={carte.user.wallet}')
"
```
8. Attendu : `user=...@test.local`, `wallet_ephemere=None`, `user.wallet=Wallet`.

### Test 2 : Redirection cross-domain
1. Scan la meme carte depuis `https://autre.tibillet.localhost/qr/<uuid>/`
2. Verification : 302 vers `https://lespass.tibillet.localhost/qr/<uuid>/`

### Test 3 : Anti-vol (user a deja une carte)
1. User A a une carte liee. Creer une 2e carte vierge.
2. Scan carte 2 -> formulaire -> saisir email de user A.
3. Attendu : message erreur "Vous avez deja une carte TiBillet..."
4. Verification en base : carte 2 reste `user=None`.

### Test 4 : Fusion avec tokens
1. Carte vierge scannee -> wallet_ephemere cree.
2. Ajouter manuellement un Token de 1000 centimes sur ce wallet_ephemere.
3. Scan + saisir email nouveau user.
4. Attendu : Token transfere sur user.wallet + Transaction FUSION en base.
5. Verification :
```
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from fedow_core.models import Transaction
print(Transaction.objects.filter(action='FUS').count())
"
```

### Test 5 : Perte de carte
1. User connecte, carte liee.
2. Aller sur MyAccount, cliquer "Carte perdue".
3. Attendu : message succes, carte detachee (`user=None, wallet_ephemere=None`).
4. Verification : `user.wallet` reste intact, ses tokens aussi.

### Test 6 : Coexistence V1 (si tenant legacy disponible)
1. Sur un tenant avec `Configuration.server_cashless` renseigne, refaire le Test 1.
2. Attendu : le flow passe par `fedow_connect` (logs HTTP visibles), comportement V1 inchange.

## Compatibilite

- Aucun changement de schema. Rollback = revert du code uniquement.
- Les adhesions anonymes liees par `card_number` sont rattrapees automatiquement lors du link.
- Les tenants legacy ne sont pas impactes (dispatch V1 conserve).
