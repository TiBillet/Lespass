# C-C / C1 — Solde complet (local + FED réseau) au scan carte POS

Lot C-C de l'intégration laboutik V2 (scénario S6). **C1 = lecture** : afficher le solde complet
(monnaies locales fedow_core + FED du réseau fédéré) au scan d'une carte au POS V2.
L'écriture (débit FED dans la cascade) est le lot **C2**, pas encore fait.

## Ce qui a été fait

| Fichier | Changement |
|---|---|
| `fedow_connect/fedow_api.py` | `get_total_fiducial_and_all_federated_token(user, use_cache=True)` — `use_cache=False` lit le wallet **frais** (`retrieve_by_signature`) au lieu du cache 10 s. Défaut `True` = aucun changement pour les appelants existants (my_account, etc.). |
| `laboutik/views.py` | Helper module-level `obtenir_solde_complet_carte(carte)` ; `retour_carte` l'utilise ; imports `FedowAPI`/`FedowConfig`. |
| `laboutik/templates/laboutik/partial/hx_card_feedback.html` | Cran « Réseau (FED) » (montant, ou « Indisponible » si Fedow injoignable). Affichage server-side, **zéro JS**. |
| `tests/pytest/test_c1_solde_complet_carte.py` | 5 tests (mock FedowAPI). |

### Le helper `obtenir_solde_complet_carte(carte)`
Retourne un dict :
- `tokens_locaux` : liste (asset_name, asset_category, value_euros, provenance)
- `locaux_centimes` : total des monnaies locales (int, centimes)
- `fed_centimes` : solde FED dépensable lu **en temps réel** (int, centimes), 0 si indisponible
- `fed_disponible` : `False` si carte anonyme / pas de place Fedow / Fedow injoignable
- `total_centimes` : `locaux_centimes + fed_centimes`

**Gardes** : le FED n'est lu que si `carte.user is not None` **et** `fedow_config.can_fedow()`
(on teste `can_fedow()` AVANT d'instancier `FedowAPI`, pour ne pas déclencher de création de place).
Tout est sous `try/except` → si Fedow ne répond pas, on garde les locaux et on signale le réseau
indisponible. **La vente n'est jamais bloquée.**

## Tests automatiques

```bash
docker exec lespass_django bash -c "cd /DjangoFiles && poetry run pytest tests/pytest/test_c1_solde_complet_carte.py -v"
```
Attendu : **5 passed**. Suite complète : `pytest tests/pytest/ -q` → **267 passed, 1 skipped**.

## Tests manuels (smoke Chrome)

> ⚠️ **Redémarrer le serveur d'abord** (`Ctrl+C` puis `rsp` dans le pane byobu) : le template
> `hx_card_feedback.html` n'est pas hot-reloadé (piège 11.6 — cache de templates).

Prérequis : env V2 (`lespass`, `can_fedow()=True`, Fedow docker up), `create_test_pos_data --schema=lespass`.

### Test 1 — Carte liée, scan au POS
1. POS : `/laboutik/caisse/point_de_vente/?uuid_pv=<PV>&tag_id_cm=<DEMO_TAGID_CM>`.
2. DEMO=True → bouton toggle simu (icône `< >` en haut à droite) → cliquer une carte démo **liée à un user**.
3. **Attendu** : l'écran retour carte s'affiche. Le détail des soldes montre les monnaies locales
   **et** un cran « Réseau » :
   - si le user a un solde FED sur le Fedow distant → ligne « Réseau / Monnaie fédérée (FED) » avec le montant ;
   - sinon (pas de solde FED) → pas de ligne Réseau (montant 0 masqué).
   - « Solde total » = locaux + FED.

### Test 2 — Dégradé Fedow down
1. Arrêter le Fedow distant : `docker stop fedow_django`.
2. Scanner une carte **liée**.
3. **Attendu** : l'écran s'affiche **sans blocage ni 500**, les soldes locaux sont visibles, et le
   cran Réseau indique « Indisponible » (—). Vérifier le log serveur :
   `obtenir_solde_complet_carte : solde FED indisponible — ...`.
4. Relancer Fedow : `docker start fedow_django`.

### Test 3 — Carte anonyme
1. Scanner une carte démo **anonyme** (sans user).
2. **Attendu** : pas de cran Réseau du tout (le FED exige une carte liée), aucun appel Fedow.

## Vérifications en base (optionnel)

```bash
# Solde FED réel d'un user sur le Fedow distant (depuis un shell Lespass) :
docker exec lespass_django bash -c "cd /DjangoFiles && poetry run python manage.py tenant_command shell --schema=lespass"
# >>> from fedow_connect.fedow_api import FedowAPI
# >>> from AuthBillet.models import TibilletUser
# >>> u = TibilletUser.objects.get(email='...')
# >>> FedowAPI().wallet.get_total_fiducial_and_all_federated_token(u, use_cache=False)  # centimes
```

## Compatibilité

- **Aucun impact V1** : `retour_carte` / `hx_card_feedback.html` sont des vues `laboutik` (caisse V2).
  Les tenants V1 (LaBoutik externe) ne passent pas par là.
- **Appelants existants de `get_total_fiducial_and_all_federated_token`** : inchangés (`use_cache=True`
  par défaut).
- **Coût** : 1 appel HTTP Fedow par scan de carte **liée** (régime identique à LaBoutik V1).
  Timeout actuel = 30 s (héritage `_get`). Optimisation « timeout court » à prévoir au monitoring (C2/C4).
