# Review du merge `dev_vps` → `V2` — Index des chantiers

**Date de la review** : 2026-05-05
**Branche source** : `origin/dev_vps` (Mike, ~1450 lignes ajoutées sur `controlvanne/`)
**Branche cible** : `V2`
**Merge-base** : `792942f2` (Session 33 task 1)

Ce dossier consolide les chantiers identifiés pendant la review. Chaque `.md` documente un sujet précis avec références fichier:ligne pour reprise PyCharm.

---

## Posture de review

> **Architecture d'abord, qualité d'écriture ensuite.**

La première review a sur-évalué le code Mike sur la qualité d'écriture (commentaires FALC bilingues, atomic block, helpers privés bien nommés) sans regarder l'architecture. ~700 lignes sur 1450 n'auraient simplement pas dû exister (redondance avec laboutik, V1 dans V2, sur-ingénierie). Cette posture est maintenant en mémoire long-terme (`feedback_review_architecture_first.md`).

Esprit transversal : **YAGNI / POC fonctionnel**. Le brief de Mike était "logique HARDWARE + mocker la stack qu'il ne comprend pas (tibillet/fedow_core/laboutik)". Il a fait l'inverse sur plusieurs points : réimplémentation au lieu de mock.

---

## Les 6 chantiers

### 🚨 Bloquants pour le merge

| # | Mémo | Sujet | Action |
|---|---|---|---|
| 1 | [CHANTIER_LEGACY_FEDOW_V1.md](CHANTIER_LEGACY_FEDOW_V1.md) | Sync `fedow_django` V1 importée dans une app V2-only (`billing.py:345-419`) | Supprimer le bloc `try: from fedow_connect ... except` |
| 2 | [CHANTIER_BILLING_REDONDANCE_LABOUTIK.md](CHANTIER_BILLING_REDONDANCE_LABOUTIK.md) | Cascade fiduciaire TNF→TLF→FED réimplémentée dans `controlvanne/billing.py` au lieu de réutiliser laboutik. **Bug fonctionnel** : LigneArticle uniforme `LOCAL_EURO` même pour TNF (cadeau) → rapports clôture LNE faussés | 3 options (refactor service partagé / exposer helpers laboutik / minimum viable). À trancher avec mainteneur. |

### ⚠️ Sécurité à durcir

| # | Mémo | Sujet | Action |
|---|---|---|---|
| 3 | [CHANTIER_AUTH_KIOSK_REDONDANCE_LABOUTIK.md](CHANTIER_AUTH_KIOSK_REDONDANCE_LABOUTIK.md) | Mécanisme d'auth kiosk parallèle au flow audité `LaBoutikAuthBridgeView`. Pas de `TermUser`, pas de throttling, pas de check révocation, durée 2 semaines au lieu de 12h, cache LocMem piège prod multi-worker. | Aligner sur laboutik : `TermUser` + `BridgeThrottle` + `set_expiry(12h)` + check `is_active` + `iri_to_uri(next_url)` |

### 🟡 Sur-ingénierie YAGNI à simplifier

| # | Mémo | Sujet | Net lignes |
|---|---|---|---|
| 4 | [CHANTIER_BALANCE_ESTIMEE_ET_DASHBOARD.md](CHANTIER_BALANCE_ESTIMEE_ET_DASHBOARD.md) | Recalcul cascade DB toutes les 1s pour afficher une estimation visuelle (5-7 queries SQL/sec). Artefacts morts : `force_close`, `debit_cl_min`, mismatch `debit_l_min`/`debit_cl_min`. Trou de reconnexion dashboard. | -20 + 0 query SQL/sec |
| 5 | [CHANTIER_PUSH_WS_REFUS.md](CHANTIER_PUSH_WS_REFUS.md) | 4 patterns dupliqués + payload obèse (3 queries SQL gratuites par refus) + asymétrie UX (3 cas muets). 3 mécanismes de reset coexistent. **Décidé : option B (carte maintenance refusée pendant service) + option i (audit via LogEntry)**. | -26 |
| 6 | [CHANTIER_CALIBRATION.md](CHANTIER_CALIBRATION.md) | Flow polling 8s + soumission série + bouton "Ignorer" redondant (vider l'input fait déjà le job côté serveur). 4 templates morts. Écart à la spec sur `extends`. i18n + aria-live absents. | -270 (templates morts) + ~-30 à -45 sur le reste |

---

## Synthèse en une page

### Les 5 manques de sécurité concrets (chantier 3)

1. **Pas de `TermUser`** lié à `TireuseAPIKey` → impossible de tracer "quel terminal a fait quoi"
2. **Pas de throttling** sur `/auth-kiosk/` (laboutik = 10/min)
3. **Pas de check révocation** — flag `controlvanne_authenticated` jamais re-vérifié contre la clé
4. **Durée session non bornée** — défaut Django 2 semaines au lieu de 12h
5. **Cache LocMem** pour le `kiosk_token` → piège prod multi-worker (Daphne ≠ Gunicorn)

### Les artefacts morts à nettoyer

| Artefact | Localisation | Statut |
|---|---|---|
| Sync `fedow_django` V1 | `billing.py:345-419` (~70 lignes) | Code mort en prod V2 |
| `force_close` TypedDict | `ws_payloads.py:41` | Jamais peuplé |
| `debit_cl_min` TypedDict | `ws_payloads.py:35` | Jamais calculé |
| Mismatch `debit_l_min`/`debit_cl_min` | `consumers.py:186` | Cohérence cassée |
| 4 templates calibration | `partial_mesure/recap/vide/confirmation.html` | URLs inexistantes |
| `console.log` debug | `panel_kiosk.js:244-251` | Laissé en prod |
| Timer JS 4s reset | `panel_kiosk.js:343-352` | Redondant avec `card_removed` serveur |

### Le bug fonctionnel à corriger (chantier 2)

`controlvanne/billing.py:294-307` crée **une seule `LigneArticle`** avec `payment_method=PaymentMethod.LOCAL_EURO`, peu importe les assets débités.

Or `laboutik/views.py:3143-3149` distingue :
```python
MAPPING_ASSET_CATEGORY_PAYMENT_METHOD = {
    Asset.TNF: PaymentMethod.LOCAL_GIFT,  # LG — cadeau
    Asset.TLF: PaymentMethod.LOCAL_EURO,  # LE
    Asset.FED: PaymentMethod.LOCAL_EURO,  # LE
}
```

Conséquence : pinte payée 1€ TNF + 3€ TLF → enregistrée 4€ `LOCAL_EURO` au lieu de 1€ `LOCAL_GIFT` + 3€ `LOCAL_EURO`. **Rapports clôture (Ticket X, ventilation moyens de paiement, chaînage HMAC LNE) faussés sur les ventes tireuse.**

---

## Bilan global en lignes

| Catégorie | Lignes |
|---|---|
| Sync `fedow_django` V1 | -70 |
| Cascade redondante (option service partagé) | -250 |
| `KioskTokenView` parallèle (option alignement laboutik) | -70 |
| Recalcul cascade au pour_update | -20 |
| Push WS refus dupliqués + timer JS 4s | -26 |
| Templates calibration morts | -270 |
| Bouton "Ignorer" + Set JS calibration | -30 |
| Artefacts TypedDict + console.log debug | -15 |
| **Net si tous les chantiers appliqués** | **~-750 lignes** |

Soit **~50% du diff Mike**.

---

## Décisions prises pendant la review

| Sujet | Décision |
|---|---|
| Carte maintenance pendant service (cas 4 push refus) | **Option B** : on garde la règle anti-fraude |
| Audit du toggle `enabled` | **Option i** : `LogEntry` Django suffit pour l'instant |
| Push WS pour refus | **6 push** via helper `_push_refus` minimal |
| Cas 3 (tireuse disabled + carte normale) | Pas de push — déjà couvert par signal `post_save` |
| Suppression timer JS 4s | Oui — redondant avec `card_removed` serveur |
| Suppression sync `fedow_django` | Oui — V1 dans V2 |
| `extends "admin/base_site.html"` calibration | Non-bloquant, à voir à l'usage |
| `_rafraichir_calibration` Pi | À challenger avec Mike (recommandé : garder) |

---

## Décisions à prendre avec le mainteneur (avant merge)

1. **Cascade billing** : option 1 (service partagé `laboutik/services/cashless_payment.py`), option 2 (exposer helpers laboutik), option 3 (minimum viable) ?
2. **Auth kiosk** : refactor complet aligné laboutik, ou minimum viable (throttling + set_expiry + escape `next_url`) avant le merge ?
3. **Booking** dans `TENANT_APPS` : conserver côté V2 lors de la résolution de conflit settings.py
4. **Migration `reservoir_illimite`** : à générer après merge
5. **Patches `Install_vps/Patch_v2/feature_patches/*`** : on garde la traçabilité ou on supprime ?

---

## Décisions à challenger avec Mike (session future)

| Chantier | Question |
|---|---|
| Calibration | Bouton "Ignorer" + Set JS vs `valeur=""` — pourquoi le doublon ? |
| Calibration | Polling 8s permanent vs bouton "Rafraîchir" — quel cas d'usage ? |
| Calibration | `?depuis` + "Nouvelle série" vs filtre 24h glissantes — quel cas couvert ? |
| Calibration | `_rafraichir_calibration` Pi — confirmé utile en exploitation ? |
| Architecture | Cascade fiduciaire dans `controlvanne` — pourquoi pas réutiliser laboutik ? |
| Architecture | Sync `fedow_django` (V1) — confusion V1/V2 ou besoin métier qu'on a raté ? |

---

## Conflits de merge non-`controlvanne/`

Hors scope des chantiers ci-dessus mais à régler au moment du merge. Liste partielle :

- `BaseBillet/views.py` (±518 lignes des deux côtés)
- `BaseBillet/models.py` — V2 ajoute `module_booking`, dev_vps en retire 5 lignes
- `BaseBillet/migrations/0208_module_booking.py` + `0217_merge_*.py` — V2 only
- `Administration/admin/dashboard.py`, `admin_tenant.py`
- `Administration/management/commands/demo_data*.py`
- `fedow_core/services.py`, `exceptions.py`, `signals.py`
- `laboutik/views.py`, `nfc.js`, `tibilletUtils.js`, `templates/laboutik/partial/*.html`
- `discovery/views.py`
- `TiBillet/asgi.py`, `urls_tenants.py`, `settings.py`
- `tests/PIEGES.md` (probablement ajouts des deux côtés)
- `locale/{fr,en}/LC_MESSAGES/django.{po,mo}` (régénérés des deux côtés)

**Stratégie suggérée** : `git merge origin/dev_vps` avec résolution manuelle. Garder V2 par défaut sur les fichiers ci-dessus (sauf `controlvanne/Pi/*` et `controlvanne/templates/admin/controlvanne/tireusebec_before.html` côté dev_vps).

---

## État du dossier

```
merge_dev_vps/
├── INDEX.md                                       ← ce fichier
├── CHANTIER_LEGACY_FEDOW_V1.md                    🚨 Bloquant
├── CHANTIER_BILLING_REDONDANCE_LABOUTIK.md        🚨 Bloquant
├── CHANTIER_AUTH_KIOSK_REDONDANCE_LABOUTIK.md     ⚠️ Sécurité
├── CHANTIER_BALANCE_ESTIMEE_ET_DASHBOARD.md       🟡 Sur-ingénierie
├── CHANTIER_PUSH_WS_REFUS.md                      🟡 Sur-ingénierie
└── CHANTIER_CALIBRATION.md                        🟡 Sur-ingénierie
```
