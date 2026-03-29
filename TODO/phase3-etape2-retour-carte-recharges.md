# Phase 3.2 — Retour carte, recharges, securite

## Ce qui a ete fait

Corrections de securite et implementation des recharges cashless payees en especes/CB.

### Modifications

| Fichier | Changement |
|---|---|
| `laboutik/views.py` | 5 nouvelles fonctions utilitaires + modifications des 3 flux de paiement |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | Mode recharge avec scan NFC client |
| `tests/pytest/test_retour_carte_recharges.py` | 13 tests (9 existants maj + 4 nouveaux) |

### Detail des changements views.py

| Fonction | Role |
|---|---|
| `_obtenir_ou_creer_wallet(carte)` | Retourne le wallet d'une carte. Cree un wallet ephemere si aucun n'existe. |
| `_valider_carte_primaire_pour_pv(tag_id_cm, uuid_pv)` | Verifie que la carte primaire a acces au PV demande. Leve PermissionDenied sinon. |
| `_panier_contient_recharges(articles)` | Detecte si le panier contient des recharges (RE/RC/TM). |
| `_executer_recharges(articles, wallet, carte, code, ip)` | Execute les recharges via TransactionService.creer_recharge(). Reutilisable par especes/CB. |
| `_determiner_moyens_paiement(pv, articles)` | Exclut NFC si le panier contient des recharges. |

### Regles metier implementees

1. **Recharge cashless via cashless interdit** — NFC masque dans le template, garde serveur dans `_payer_par_nfc()`
2. **Panier mixte (ventes + recharges)** — force especes/CB only (pas de NFC)
3. **Scan carte client au moment du paiement** — le template affiche le lecteur NFC avant la confirmation
4. **Wallet ephemere auto-cree** — si une carte n'a ni user.wallet ni wallet_ephemere
5. **Validation CartePrimaire / PV** — dans point_de_vente(), payer(), moyens_paiement(), cloturer()

## Tests a realiser

### Test 1 : Recharge euros en especes
1. Ouvrir la caisse (scanner carte primaire)
2. Ajouter un article "Recharge 10 EUR" (methode_caisse=RE)
3. Cliquer "Payer" → les boutons affichent "Recharge : scannez la carte client"
4. Le bouton CASHLESS ne doit PAS apparaitre
5. Cliquer "ESPECE"
6. Scanner la carte client
7. Verification : le wallet client a ete credite de 1000 centimes (10 EUR)

```bash
# Verifier en base
docker exec lespass_django poetry run python manage.py shell -c "
from fedow_core.services import WalletService
from QrcodeCashless.models import CarteCashless
carte = CarteCashless.objects.get(tag_id='<TAG_ID_CLIENT>')
wallet = carte.user.wallet if carte.user else carte.wallet_ephemere
print('Soldes:', WalletService.obtenir_tous_les_soldes(wallet))
"
```

### Test 2 : Recharge NFC impossible
1. Ajouter un article "Recharge 10 EUR" (RE)
2. Tenter de forger un POST avec moyen_paiement=nfc
3. Verification : reponse 400 avec message "Les recharges ne peuvent pas etre payees en cashless"

### Test 3 : Wallet ephemere auto-cree
1. Scanner une carte NFC inconnue (pas de user, pas de wallet_ephemere)
2. Faire un retour carte (verifier_carte → retour_carte)
3. Verification : un wallet ephemere a ete cree et attache a la carte

### Test 4 : Validation PV / carte primaire
1. Creer une carte primaire avec acces a un seul PV (ex: "Bar")
2. Tenter d'acceder a un autre PV via URL forgee
3. Verification : reponse 403 (PermissionDenied)

### Test 5 : Recharge cadeau (RC) et temps (TM)
1. Ajouter un article "Recharge Cadeau" (RC) et payer en especes avec scan client
2. Verification : Token TNF credite
3. Ajouter un article "Recharge Temps" (TM) et payer en CB avec scan client
4. Verification : Token TIM credite

## Tests automatises

```bash
# Tous les tests Phase 3.2
docker exec lespass_django poetry run pytest tests/pytest/test_retour_carte_recharges.py -v

# Tests de non-regression (especes/CB, NFC, fedow_core, navigation)
docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py tests/pytest/test_paiement_cashless.py tests/pytest/test_fedow_core.py tests/pytest/test_caisse_navigation.py -v
```

## Compatibilite

- Les flux de paiement existants (ventes VT, adhesions AD en NFC) ne sont pas modifies
- Le code mock (mockData.py, method.py) n'a pas ete touche (prevu Phase 7)
- Les tests Playwright existants (39, 40, 41) doivent passer sans regression
