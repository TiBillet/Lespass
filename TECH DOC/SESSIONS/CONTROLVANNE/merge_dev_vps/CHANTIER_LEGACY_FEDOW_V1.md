# Chantier — Sync `fedow_django` V1 dans une app V2-only

**Date** : 2026-05-05
**Statut** : 🔴 À supprimer — V1 dans V2
**Branche** : `dev_vps`
**Contexte** : Review du merge `dev_vps` → `V2`. Mike a inséré ~70 lignes de sync HTTP/RSA vers `fedow_django` dans `controlvanne/billing.py`. C'est du V1 dans une app conçue uniquement pour les nouveaux tenants V2.

---

## 1. Localisation exacte

`controlvanne/billing.py:345-419`

```python
# ── Sync optionnelle vers fedow_django ──────────────────────────────────
# ...
try:
    from fedow_connect.models import FedowConfig         # ← V1
    from fedow_core.models import Asset as AssetLocal

    fedow_config = FedowConfig.get_solo()
    carte_a_un_user = carte.user is not None
    user_a_un_wallet = carte_a_un_user and bool(carte.user.wallet)
    fedow_est_configure = fedow_config.can_fedow()

    if fedow_est_configure and carte_a_un_user and user_a_un_wallet:
        from fedow_connect.fedow_api import FedowAPI     # ← V1
        fedow_api = FedowAPI()

        for tx in transactions_creees:
            if tx.asset.category != AssetLocal.FED:
                continue
            fedow_api.transaction.to_place_from_qrcode(  # ← appel HTTP/RSA
                user=carte.user,
                amount=tx.amount,
                asset_type="EURO",                        # ← API legacy
                comment=...,
            )
            ...
    elif not fedow_est_configure:
        logger.debug("Sync fedow_django ignorée : FedowConfig non configuré")
    elif not carte_a_un_user:
        logger.debug(...)
    elif not user_a_un_wallet:
        logger.debug(...)

except Exception as erreur_fedow:
    logger.warning(f"Sync fedow_django non-bloquante échouée: {erreur_fedow}")
```

---

## 2. Pourquoi c'est du legacy V1

### 2.1 Ce qu'est `fedow_connect`

`fedow_connect` est le **client HTTP+RSA** vers le serveur Fedow standalone (V1).

- `fedow_connect.models.FedowConfig.can_fedow()` = "ce tenant a-t-il une URL fedow et une clé partagée configurées ?"
- `fedow_connect.fedow_api.FedowAPI()` = client HTTP authentifié RSA vers `https://fedow.tibillet.io/...`
- `to_place_from_qrcode(...)` = endpoint REST V1 qui pousse une transaction vers Ma Tirelire

C'est **précisément le mécanisme que la fusion mono-repo V2 supprime** (cf. `PLAN_LABOUTIK.md` §2 "Architecture cible" : "1 seul Django, accès DB direct, plus de HTTP+RSA").

### 2.2 Règle de coexistence V1/V2

`PLAN_LABOUTIK.md` §2.3 :
```
V2 si :  module_monnaie_locale=True AND server_cashless IS NULL
V1 si :  server_cashless IS NOT NULL
```

L'app `controlvanne` n'est destinée qu'aux **nouveaux tenants V2**. Pour ces tenants :
- `Configuration.server_cashless = None`
- `FedowConfig.can_fedow()` retourne **False** par construction

Donc le code de sync de Mike ne s'exécute **jamais** en pratique sur les tenants cibles. C'est du code mort dès l'écriture.

### 2.3 Ce que fait laboutik V2 (référence)

`laboutik/views.py` ne contient **aucun appel** `to_place_from_qrcode`, `FedowAPI()`, `FedowConfig`. Vérifié :

```bash
$ rg "to_place_from_qrcode|FedowAPI|FedowConfig" laboutik/ --type py
laboutik/management/commands/create_test_pos_data.py:139:    from fedow_connect.models import FedowConfig
# (uniquement pour le seed de test, pas dans le code de production)
```

Les ventes laboutik V2 créent une `Transaction` `fedow_core` en DB direct via `TransactionService.creer_vente()`. Pas de sync HTTP V1.

---

## 3. Pourquoi Mike a fait ça

Hypothèses :

1. **Confusion mentale V1/V2** — Mike a probablement vu `BaseBillet/signals.py:425` ou `BaseBillet/validators.py:1044-1047` qui utilisent `FedowAPI()` (pour le legacy V1 des anciens tenants) et a copié le pattern, sans réaliser que controlvanne tourne uniquement en V2.

2. **Crainte que "Ma Tirelire" rate les ventes tireuse** — son commentaire dit :
   > "On pousse ici les débits FED/TLF vers fedow_django pour que 'Ma Tirelire' reflète les consommations tireuse"
   
   Il pensait que le client utilisateur final regarderait sa Tirelire V1 et ne verrait pas la tireuse. Mais en V2, la Tirelire est gérée différemment (via `fedow_core` direct) et controlvanne ne s'adresse pas aux tenants V1.

3. **AI assistance sans validation** — Claude Code voit `fedow_connect` utilisé ailleurs dans le repo, propose le pattern, Mike valide sans recul architectural.

---

## 4. Ce qu'on garde, ce qu'on supprime

### 4.1 À supprimer (~70 lignes)

`controlvanne/billing.py:345-419` — tout le bloc `try: from fedow_connect.models import FedowConfig ... except`

### 4.2 À conserver

Le retour de `facturer_tirage()` retourne `{"transactions": ..., "ligne_article": ..., "montant_centimes": ...}`. La création de `Transaction` `fedow_core` via `TransactionService.creer_vente()` est correcte (c'est le bon mécanisme V2). On garde tout sauf le bloc sync.

### 4.3 Comportement après suppression

- Les ventes tireuse créent une `Transaction` `fedow_core` en DB → trace dans le schéma tenant
- Pas de remontée HTTP vers `fedow.tibillet.io` (V1 standalone) → cohérent V2
- Si plus tard on veut une vue "Ma Tirelire" V2, elle interrogera `fedow_core.Transaction` directement (déjà la cible du `PLAN_LABOUTIK.md`)

---

## 5. Cas particuliers à vérifier

### 5.1 Le tenant utilise-t-il vraiment V2 uniquement ?

À confirmer avec le mainteneur. Si dans 6 mois on autorise les anciens tenants V1 à activer une tireuse, il faudrait soit :
- **Bloquer l'activation** du module tireuse pour les tenants V1 dans le dashboard Groupware (le plus simple)
- **Réintroduire la sync** mais cette fois proprement, avec des tests, et documentation

L'approche propre : **bloquer l'activation V1 pour l'instant**, ajouter la double-route plus tard si vraiment demandé.

### 5.2 Migration des cartes user.wallet

Mike vérifie `carte.user.wallet`. En V2, `user.wallet` est le wallet `AuthBillet.Wallet` (modèle SHARED_APPS). C'est aussi celui que `_obtenir_ou_creer_wallet` retourne en priorité (`laboutik/views.py:964`). Cohérent — donc pas de migration data nécessaire si on supprime juste la sync.

---

## 6. Recommandation

### Action immédiate
Supprimer le bloc `controlvanne/billing.py:345-419` lors du merge ou en commit follow-up. Net du merge.

### Action moyen terme
Si on veut à nouveau une remontée vers Ma Tirelire (V2), elle devra :
- Ne **PAS** importer `fedow_connect`
- Lire les `fedow_core.Transaction` directement (DB partagée, accès `connection.tenant`)
- Être codée comme une vue ou un endpoint API dans `BaseBillet` ou un nouveau module `tirelire`, pas dans `controlvanne`

### Brief Mike pour la suite
> "Tu n'écris **aucune** ligne qui importe `fedow_connect`, `fedow.api`, `FedowAPI`, `FedowConfig`. Ce sont des modules V1 legacy. En V2, tu accèdes directement aux modèles `fedow_core.*` et tu utilises `fedow_core.services` (TransactionService, WalletService, AssetService). Si tu vois `fedow_connect` ailleurs dans le repo, c'est pour la compat V1 des anciens tenants — controlvanne n'en a pas besoin."

---

## 7. Fichiers à ouvrir dans PyCharm

```
controlvanne/billing.py:345-419     — bloc à supprimer
fedow_connect/                       — module V1 (ne PAS importer depuis controlvanne)
laboutik/views.py:5505-5582          — référence : comment laboutik V2 fait sans fedow_connect
fedow_core/services.py:1109          — TransactionService.creer_vente (V2 = la bonne API)
TECH DOC/Laboutik sessions/PLAN_LABOUTIK.md §2  — architecture cible mono-repo
```
