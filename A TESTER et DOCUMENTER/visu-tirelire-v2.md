# Visualisation tirelire V2 (Session 32)

## Ce qui a ete fait

La vue `MyAccount.tokens_table` (`BaseBillet/views.py`) dispatch sur `peut_recharger_v2(user)` :

- Verdict `"v2"` -> nouvelle methode `_tokens_table_v2` qui lit `fedow_core.Token` local
- Autres verdicts (`"v1_legacy"`, `"wallet_legacy"`, `"feature_desactivee"`) -> code V1 actuel inchange (appel `FedowAPI`)

Nouveau partial `reunion/partials/account/token_table_v2.html` : 2 sous-tableaux (Monnaies fiduciaires + Temps & fidelite) avec message d'accueil si aucun token.

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | Dispatch + methode + 2 helpers + imports fedow_core |
| `BaseBillet/templates/reunion/partials/account/token_table_v2.html` | Nouveau partial |
| `tests/pytest/test_tokens_table_v2.py` | 9 tests pytest |
| `tests/PIEGES.md` | Entree 11.9 cross-schema cascade |
| `locale/*/LC_MESSAGES/django.po` | 7 strings i18n |
| `CHANGELOG.md` | Entree bilingue |

## Tests a realiser

### Test 1 : Scenario nominal (user V2 avec token FED)
1. Se connecter comme `admin@admin.com` sur `https://lespass.tibillet.localhost/`
2. Aller sur `/my_account/balance/`
3. Si pas encore de tokens : cliquer **Recharger TiBillets**, payer 20€ avec carte test `4242 4242 4242 4242` (`12/42`, `424`)
4. Apres retour, verifier sur `/my_account/balance/` :
   - Section "Ma tirelire" en haut avec les 3 boutons d'action (inchange)
   - En dessous, section **"Monnaies"** avec une ligne :
     - Solde : **20,00 TiBillets** + badge `Fiduciaire federee`
     - Utilisable chez : badge bleu **"Utilisable partout"**
   - Pas de sous-tableau "Temps & fidelite" (aucun token TIM/FID)

### Test 2 : User neuf (aucun token)
1. Creer un compte neuf : se deconnecter, s'inscrire avec un nouvel email
2. Valider email
3. Aller sur `/my_account/balance/`
4. Verifier :
   - Section "Ma tirelire" en haut avec bouton **Recharger TiBillets**
   - En dessous, **pas de tableau** mais un message :
     - Icone `bi-wallet2` + "You don't have any TiBillets yet."
     - Lien "Refill your wallet above" -> scroll vers la section tirelire

### Test 3 : Non-regression V1 legacy
1. Se connecter sur un tenant avec `Configuration.server_cashless` renseigne (ex: un tenant connecte a LaBoutik externe)
2. Aller sur `/my_account/balance/`
3. Verifier que l'ancien tableau V1 s'affiche (3 colonnes : Solde / Utilisation / Derniere transaction), avec eventuellement le logo SVG TiBillets pour les tokens `is_stripe_primary`
4. Verifier dans le HTML (inspecter) : **pas** de `id="tokens-v2-container"`

### Test 4 : Feature desactivee
1. Admin : mettre `module_monnaie_locale=False` sur le tenant courant
2. Aller sur `/my_account/balance/`
3. Verifier que le bouton "Recharger TiBillets" est cache (comportement inchange Session 31)
4. Le tableau s'affiche toujours (code V1 appele), meme si pas de bouton refill

### Commandes DB utiles

```python
# Depuis docker exec lespass_django poetry run python /DjangoFiles/manage.py shell_plus

# Voir les tokens d'un user V2
from AuthBillet.models import TibilletUser
from fedow_core.models import Token

user = TibilletUser.objects.get(email="admin@admin.com")
tokens = Token.objects.filter(wallet=user.wallet).select_related("asset")
for t in tokens:
    print(f"{t.asset.name} ({t.asset.category}) : {t.value} centimes")

# Vider le cache des infos lieux
from django.core.cache import cache
cache.delete("tenant_info_v2")
```

### Commande pytest rapide

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py -v --api-key dummy
```

## Compatibilite

- V1 legacy inchange : zero modification du code V1 dans `tokens_table`
- `FedowAPI` toujours appele pour les verdicts `v1_legacy`, `wallet_legacy`, `feature_desactivee`
- Aucune migration DB
- Pas d'impact sur le POS V2 (`laboutik/views.py` continue d'utiliser `WalletService.obtenir_tous_les_soldes` sans prefetch federations)

## Hors scope (sessions futures)

- Migration users `wallet_legacy` vers fedow_core local
- Suppression de `FedowAPI`
- Affichage des transactions V2 (`transactions_table` -> V2) — rester sur V1 pour l'instant
- Badges de categorie colores avec palette creole (renvoye a revue visuelle, fichier CSS optionnel)
