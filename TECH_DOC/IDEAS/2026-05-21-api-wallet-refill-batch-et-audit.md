# API wallet-refill — lot (batch), journal d'audit & digest anti-abus — note d'idée

> **Date** : 2026-05-21
> **Statut** : Exploration en cours, **pas de code** sur le batch/audit. La route **mono est déjà livrée** (voir `TECH_DOC/SESSIONS/API_GIFT_REFILL/`). À reprendre en `/brainstorming` puis `/writing-plans`.
> **Auteur** : Jonas + Claude (Opus 4.7)
> **Branche** : `main` (Lespass)

---

## 1. Contexte — ce qui existe déjà (livré)

Route **mono** `POST /api/v2/wallet-refills/` (cf `SESSIONS/API_GIFT_REFILL/SPEC.md`) :
- Body `{email, asset, amount}`, header `Authorization: Api-Key`, header optionnel `Idempotency-Key`.
- Crédite un asset **non fiduciaire** (`AssetFedowPublic.REFILLABLE_CATEGORIES` = TNF/TIM/FID/BDG) sur la tirelire d'un user via `FedowAPI.transaction.refill_from_lespass_to_user_wallet`.
- Clé API restreinte à **un seul asset** via `ExternalApiKey.gift_asset` (FK = interrupteur + restriction).
- Plafond `GIFT_REFILL_MAX_AMOUNT = 10000`. Idempotence cache (rejeu → `208 Already Reported`).
- Réponse `201` schema.org `MoneyTransfer` (`identifier` = uuid transaction Fedow).
- 11 tests verts.

**Ce qui manque (objet de cette note) :** mode lot + traçabilité/anti-abus.

---

## 2. Besoin exprimé

1. **Recharge par lot (batch)** : envoyer une liste `[{email, amount}]` pour un même asset, avec un retour par email (`{email, 201/208/…}`).
2. **Surveillance des abus** : pouvoir savoir qui a crédité quoi, sans se faire spammer par les notifications.

---

## 3. Décisions d'exploration prises (à confirmer en brainstorming)

| Sujet | Décision explorée |
|---|---|
| Endpoint | **Un seul endpoint polymorphe** `/wallet-refills/` : mono `{email,asset,amount}` OU batch `{asset, recipients:[{email,amount}]}`, détecté par la présence de `recipients`. Rétrocompatible. |
| Asset | **À la racine** du batch (une clé = un asset), pas par item. |
| Montant | Unité brute (int), comme le mono. |
| Idempotence batch | **Par item** : clé cache `{idempotency_key}:{email}` → un email déjà crédité renvoie `208`. |
| Plafond batch | Limite du **nombre d'items** (anti-abus / charge). Valeur évoquée : ~50 (sync) ou ~500 (async). |
| Code HTTP batch (si retour synchrone) | **`207 Multi-Status`** — et c'est le seul contexte où `208` est *conforme* à la RFC 5842 (208 vit dans un 207). |

---

## 4. Modèle de traitement du batch — sync vs async

### Option A — Synchrone (la plus FALC)
- La requête boucle sur les items et renvoie un **`207` immédiat** avec `{email, status}` par item.
- Réutilise la logique mono (helper partagé `refill_one`).
- **Limite basse (~50)** car N appels HTTP Fedow séquentiels dans la requête → risque de timeout au-delà.
- Zéro nouvelle infra. Donne le retour par email tout de suite.

### Option B — Async Celery + GET statut (cache)
- POST → `202 Accepted` + `batchId` ; tâche Celery ; le client **poll** `GET /wallet-refills/batch/{batchId}/` qui renvoie le `207`.
- État du batch en cache Redis (TTL). +1 endpoint, +1 tâche. Protocole en 2 temps.

### Option C — Async Celery + **mail récap admin** (retenu provisoirement, puis nuancé)
- POST → `202` + `batchId` ; tâche Celery ; **un mail récap** part à l'admin (au lieu d'un endpoint GET).
- Plus simple que B (pas d'endpoint statut, pas de cache de statut, pas de poll).
- Tenant propagé automatiquement à la tâche via **`tenant_schemas_celery`** (déjà utilisé par le projet, cf `TiBillet/celery.py`).

---

## 5. Problème du bruit & idée du digest horaire

Un **mail par recharge** (mono ou item) est ingérable (50 appels = 50 mails). Idée Jonas : **un récap par heure**.

### Solution proposée — digest « debounce » par cache (SANS Celery Beat)
- À chaque recharge : `cache.add("refill_digest_pending:<tenant>", timeout=3600)`.
  `cache.add` = `SETNX` Redis (atomique) → **n'arme la tâche qu'une fois par heure**.
- Si l'`add` réussit (1ʳᵉ recharge de l'heure) → `notify_refill_digest.apply_async(countdown=3600)`.
- 1 h plus tard, le **worker Celery** (pas Beat) dépile la tâche, lit les recharges de la dernière heure, envoie **un seul mail récap** à l'admin ; le flag expire seul.
- Résultat : **1 mail/heure max par tenant**, pas de Beat, pas de `settings.py`, pas de race condition.

**Clarification technique** (point soulevé) : Redis n'exécute rien ; il sert de **broker** (file + délai via `countdown`) et de **cache** (verrou). C'est le worker Celery qui exécute. **Beat** ne sert qu'aux tâches récurrentes à heure fixe (cron) — inutile ici puisqu'on planifie une tâche ponctuelle différée.

---

## 6. Le vrai garde-fou — journal d'audit `GiftRefillLog`

**Constat (vérifié 2026-05-21)** : aujourd'hui la recharge **mono ne laisse aucune trace exploitable** côté Lespass.
- Le seul enregistrement local est un `FedowTransaction` (`BaseBillet/models.py:2668`) **anémique** : `uuid`, `hash`, `datetime` — **ni montant, ni email, ni asset, ni clé API**.
- Le détail (montant/asset/email/`api_key`/`reason`) vit **uniquement côté Fedow** (metadata distant) + cache d'idempotence (éphémère 48 h).
- Donc **impossible de requêter** « la clé X a crédité combien, à qui, quand » → pas d'outil anti-abus.

**Proposition** : un modèle `GiftRefillLog` (TENANT_APP, ex `api_v2`) :

| Champ | Type | Rôle |
|---|---|---|
| `created` | DateTimeField (auto) | Quand |
| `api_key_name` | CharField | Quelle clé API |
| `email` | EmailField | Bénéficiaire |
| `asset_uuid` / `asset_name` | UUID / Char | Quel asset |
| `amount` | IntegerField | Combien (unité brute) |
| `status` | Char/Int | 201 / 208 / 422 / 503 |
| `transaction_uuid` | UUID null | Lien transaction Fedow |
| `mode` | Char | `mono` / `batch` |

- Écrit à **chaque** recharge (mono + chaque item de batch).
- Exposé en **admin Unfold** avec filtres (date, email, clé, asset, status) → **surveillance d'abus par consultation**, indépendante des mails.
- Le digest (§5) interroge ce journal au lieu de réaccumuler ailleurs.

→ **Le journal est le socle anti-abus ; le digest mail est optionnel** par-dessus.

---

## 7. Niveaux de simplicité (à trancher)

1. **Journal seul** (le + FALC) : `GiftRefillLog` + admin Unfold. Aucun mail, aucune tâche périodique. Surveillance par consultation.
2. **Journal + digest debounce** : §5/§6. 1 mail récap/heure max, sans Beat.
3. **Journal + digest Celery Beat** : tâche planifiée horaire classique — touche `settings.py` / `CELERY_BEAT_SCHEDULE`. Plus standard, plus intrusif.

*Penchant actuel : 1 ou 2.*

---

## 8. Esquisse d'implémentation (pour reprise)

- `api_v2/tasks.py` (nouveau) :
  - `refill_one(asset, email, amount, idempotency_key, api_key_name) -> dict` — **helper synchrone partagé** (validation plafond, idempotence cache par item, `get_or_create_user`, `can_fedow`, crédit Fedow, **écriture `GiftRefillLog`**). Utilisé par le mono (vue) ET le batch (tâche). Source unique de vérité.
  - `@app.task process_wallet_refill_batch(asset_uuid, recipients, idempotency_key, api_key_name, batch_id)` — boucle + `refill_one` + (selon §7) mail récap.
  - `@app.task notify_refill_digest()` — digest horaire (lit `GiftRefillLog` de la dernière heure → mail admin).
- `api_v2/models.py` : `GiftRefillLog` + migration (TENANT_APP).
- `api_v2/serializers.py` : `WalletRefillBatchCreateSerializer` (`asset` uuid + `recipients` liste).
- `api_v2/views.py` : `create()` détecte mono/batch ; mono = `refill_one` synchrone ; batch = validations globales + `202` + `.delay()`.
- `Administration/admin_tenant.py` (ou `api_v2/admin.py`) : admin Unfold `GiftRefillLog` (lecture seule + filtres).
- Mail admin : réutiliser `send_email_generique` + emails `TibilletUser.objects.filter(client_admin=tenant)` (fallback `config.email`), pattern `send_membership_pending_admin` (`BaseBillet/tasks.py:307`).

---

## 9. Points ouverts à trancher (prochaine session)

- Niveau §7 (journal seul vs +digest).
- Valeur de la limite batch (50 sync / 500 async).
- Le batch laisse-t-il le client sans détail (juste `202` + `batchId`) si on part sur le mail admin, ou ajoute-t-on quand même un `GET` statut ? (cf A vs C).
- Faut-il un **plafond cumulé par clé / par jour** (vrai anti-abus quantitatif), en plus du plafond par recharge ? Le `GiftRefillLog` le rendrait calculable.
- `GiftRefillLog` dans `api_v2` ou `BaseBillet` ? (cohérence avec `ExternalApiKey` qui est dans `BaseBillet`).

---

## 10. Prochaines étapes

1. Trancher §7 + §9.
2. `/brainstorming` court (le gros du design est déjà ici) → `/writing-plans` → implémentation.
3. Commencer par le **journal d'audit** (valeur immédiate, faible coût, débloque le reste).
