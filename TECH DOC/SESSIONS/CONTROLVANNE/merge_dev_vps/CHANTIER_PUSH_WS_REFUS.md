# Chantier — Push WebSocket des refus dans `authorize`

**Date** : 2026-05-05
**Statut** : 🟡 À reprendre — décisions prises (option B + option i)
**Branche** : `dev_vps`
**Contexte** : Review du merge `dev_vps` → `V2`. Mike push 4 messages de refus au kiosk via WS dans `TireuseViewSet.authorize`, plus 1 variante reset dans `event(card_removed)`. Le pattern est dupliqué, certains refus sont muets (incohérence UX), et un timer JS 4s coexiste avec un push card_removed serveur (redondance).

---

## 1. Constat

### 1.1 Inventaire complet des refus dans `authorize`

| Cas | Localisation | Push WS aujourd'hui ? | Décision retenue |
|---|---|---|---|
| 1 — TireuseBec inexistante | `viewsets.py:206-210` | ❌ | ❌ — 404 dur, pas de kiosk associé |
| 2 — Carte inconnue | `viewsets.py:215-217` | ❌ | ✅ **Push à ajouter** |
| 3 — Tireuse `disabled` + carte normale | `viewsets.py:236-237` | ❌ | ❌ — déjà couvert par signal post_save (toggle live) + état initial WS |
| 4 — Carte maintenance pendant service | `viewsets.py:244-250` | ❌ | ✅ **Push à ajouter** (option B retenue, cf. §3) |
| 5 — Cashless non configuré | `viewsets.py:302-311` | ✅ | ✅ — conserver via `_push_refus` |
| 6 — Prix non configuré | `viewsets.py:327-336` | ✅ | ✅ — conserver via `_push_refus` |
| 7 — Fût vide | `viewsets.py:356-365` | ✅ | ✅ — conserver via `_push_refus` |
| 8 — Solde insuffisant | `viewsets.py:378-388` | ✅ | ✅ — conserver via `_push_refus` |
| `card_removed` sans session | `viewsets.py:482-498` | ✅ | ✅ — conserver (reset kiosk) |

**Cible : 6 push** (cas 2, 4, 5, 6, 7, 8) + reset card_removed.

### 1.2 Problèmes du code actuel

1. **Asymétrie d'UX** : cas 2 et 4 muets, cas 5-8 verbeux. L'utilisateur ne sait pas pourquoi sa carte est refusée dans la moitié des cas.

2. **Payload obèse** : chaque push appelle `_construire_payload_session(tireuse, None)` qui fait **3 queries SQL** (`liquid_label`, `prix_litre`, `reservoir_max_ml`) pour reconstituer un état tireuse qui n'a pas changé depuis l'état initial reçu par le kiosk.

3. **Pattern dupliqué 5×** :
   ```python
   _push_ws_kiosk(tireuse, {
       **_construire_payload_session(tireuse, None),
       "authorized": False,
       "present": True,
       "uid": uid,
       "message": "...",
   })
   ```

4. **Usage limite** : `_construire_payload_session(tireuse, None)` — la fonction est conçue pour une `RfidSession`, pas `None`. Sémantiquement bancal.

5. **Redondance reset** : 3 mécanismes coexistent pour le même besoin "remettre le kiosk en En attente après refus" :
   - Push `card_removed` serveur (fiable, le Pi envoie toujours card_removed depuis le fix Mike)
   - Push `card_removed` Pi → serveur (déclencheur)
   - Timer JS 4s côté `panel_kiosk.js:343-352` (commentaire Mike : "le Pi n'envoie pas toujours card_removed sans session active" — workaround)

   Mike a corrigé le bug Pi ET ajouté le timer JS. Les deux ne sont plus utiles ensemble.

---

## 2. Solution POC / YAGNI

### 2.1 Helper unique

```python
def _push_refus(tireuse, message, **extras):
    """
    Payload minimal pour informer le kiosk d'un refus d'autorisation.
    / Minimal payload to inform the kiosk of an authorization refusal.

    LOCALISATION : controlvanne/viewsets.py

    Le kiosk a déjà l'état de la tireuse (liquid_label, prix_litre, etc.) en mémoire JS
    depuis le payload initial. Un refus = juste afficher un message, pas re-publier
    tout l'état.
    / The kiosk already has tap state (liquid_label, prix_litre, etc.) in JS memory
    from the initial payload. A refusal = just display a message, not re-publish
    the full state.
    """
    payload = {
        "tireuse_bec_uuid": str(tireuse.uuid),
        "authorized": False,
        "message": message,
    }
    payload.update(extras)
    _push_ws_kiosk(tireuse, payload)
```

3 champs obligatoires. Zéro query SQL. Le kiosk JS lit `message`, met à jour le badge "Refusé" + texte, garde le reste de son état affiché.

### 2.2 Usage dans `authorize`

```python
# Cas 2 — Carte inconnue
if not carte:
    _push_refus(tireuse, "Carte inconnue.")
    return Response({"authorized": False, "message": "Unknown card."})

# Cas 4 — Carte maintenance pendant service
if is_maintenance and tireuse.enabled:
    _push_refus(tireuse, "Carte maintenance refusée pendant le service.")
    return Response({"authorized": False, "message": "Maintenance card refused: tap is in service."})

# Cas 5 — Cashless non configuré
if not contexte:
    _push_refus(tireuse, "Cashless non configuré pour ce lieu.")
    return Response({"authorized": False, "message": "No cashless asset configured for this venue."})

# Cas 6 — Prix non configuré
if prix_litre <= 0:
    _push_refus(tireuse, "Prix non configuré pour ce fût.")
    return Response({"authorized": False, "message": "No price configured for the active keg."})

# Cas 7 — Fût vide
if not tireuse.reservoir_illimite and reservoir_disponible <= 0:
    _push_refus(tireuse, "Fût vide.")
    return Response({"authorized": False, "message": "Empty keg."})

# Cas 8 — Solde insuffisant
if allowed_ml <= 0:
    _push_refus(tireuse, "Solde insuffisant.", balance=f"{solde_centimes / 100:.2f}")
    return Response({"authorized": False, "message": "Insufficient funds.", "solde_centimes": solde_centimes})
```

### 2.3 Suppression du timer JS 4s

`controlvanne/static/controlvanne/js/panel_kiosk.js:343-352` — supprimer le bloc :
```js
if (payload.authorized === false) {
    if (c.resetTimer) clearTimeout(c.resetTimer);
    c.resetTimer = setTimeout(function () { c.resetTimer = null; reinitialiserCarte(c); }, 4000);
}
```

Justification : le Pi envoie maintenant `card_removed` dans tous les cas (avec ou sans session_id, fix Mike `tibeer_controller.py:_handle_card_removal`). Le serveur push un reset_payload au card_removed. Le timer JS est redondant.

---

## 3. Justification des décisions

### 3.1 Pourquoi pas de push pour le cas 3 (tireuse disabled + carte normale)

Le signal `post_save` de `TireuseBec` (`signals.py:201-219`) se déclenche au moment où l'admin toggle `enabled`. `_snapshot_for_bec(tb)` (lignes 33-71) détecte `not tb.enabled` et push immédiatement :
```python
{
    "tireuse_bec_uuid": str(tb.uuid),
    "maintenance": True,
    "present": False,
    "authorized": False,
    "vanne_ouverte": False,
    "message": "En Maintenance",
}
```

Le kiosk passe en "En Maintenance" en temps réel. Si un client pose ensuite une carte normale, le serveur la refuse côté API (Response JSON pour le Pi) mais le kiosk continue d'afficher "En Maintenance". Cohérent — pas besoin de push de refus.

**Cas limite à signaler** : si un client a déjà sa carte posée au moment du toggle disable, la vanne reste ouverte côté Pi (pas de mécanisme pour la fermer via signal). Désynchro affichage/physique. Pas critique mais à connaître.

### 3.2 Pourquoi push pour le cas 4 (option B retenue)

Décision métier validée : on conserve la règle de Mike "carte maintenance refusée pendant le service" pour bloquer techniquement l'usage opportuniste comme carte gratuite.

**Logique anti-fraude trois niveaux** :
- **Préventif** : la règle bloque l'utilisation pendant le service → un employé voulant abuser doit d'abord disable la tireuse
- **Détectif** : `HistoriqueMaintenance` (`controlvanne/models.py:496`, proxy `RfidSession` filtré sur `is_maintenance=True`) trace toute utilisation de carte maintenance (carte, tireuse, volume, datetime) → audit a posteriori
- **Causal** : `LogEntry` Django (option **i** retenue) trace les toggle `enabled` via l'admin Unfold → corrélation possible "user X disable + carte maintenance utilisée 1 min plus tard"

**Note** : la règle n'est pas dans `SPEC_CONTROLVANNE.md` §2.13 (qui dit seulement "carte_maintenance existe → mode rinçage, pas de facturation"). C'est une décision Mike validée a posteriori avec le mainteneur lors du chantier review.

Push WS du cas 4 utile pour informer l'employé qui passe sa carte maintenance par erreur sur une tireuse en service (sinon il ne comprend pas pourquoi rien ne s'ouvre).

### 3.3 Audit du toggle `enabled` (option i)

Pas de modèle dédié pour l'historique des `enabled = True/False`. On s'appuie sur `django.contrib.admin.LogEntry` standard, qui trace via Unfold :
- L'user admin qui a fait le change
- Le timestamp
- L'object_id de la `TireuseBec`
- Le champ modifié (générique)

**Limite** : ne capture pas le before/after de `enabled` ni de raison saisie. Suffisant pour un POC. Si plus tard incident d'audit → migrer vers un modèle dédié `HistoriqueEnabled(tireuse, user, datetime, ancien, nouveau, raison)` (~30 lignes).

---

## 4. Bilan

| Action | Lignes |
|---|---|
| Ajouter helper `_push_refus` | +12 |
| Remplacer 4 patterns dupliqués (cas 5-8) | -32 |
| Ajouter push cas 2 et 4 | +2 |
| Supprimer timer JS 4s reset | -8 (`panel_kiosk.js`) |
| **Net** | **~-26 lignes** + UX cohérente + 0 query SQL gratuite |

---

## 5. Couplage avec autres chantiers

Ce chantier est **indépendant** des autres :
- Pas de dépendance avec `CHANTIER_BILLING_REDONDANCE_LABOUTIK.md` (le helper `_push_refus` n'utilise pas la cascade)
- Pas de dépendance avec `CHANTIER_AUTH_KIOSK_REDONDANCE_LABOUTIK.md` (refus auth API ≠ refus côté Pi)
- Pas de dépendance avec `CHANTIER_BALANCE_ESTIMEE_ET_DASHBOARD.md` (balance estimée concerne pour_update, pas authorize)

Peut être appliqué isolément en commit follow-up.

---

## 6. Fichiers à ouvrir dans PyCharm

```
controlvanne/viewsets.py:186-395       — méthode authorize (8 cas + 5 push actuels)
controlvanne/viewsets.py:482-498       — card_removed sans session (reset payload)
controlvanne/viewsets.py:48-89         — _push_ws_kiosk + _construire_payload_session (à conserver)
controlvanne/static/controlvanne/js/panel_kiosk.js:343-352   — timer JS 4s à supprimer
controlvanne/Pi/controllers/tibeer_controller.py:_handle_card_removal   — fix Mike (envoie card_removed dans tous les cas)
controlvanne/signals.py:33-71          — _snapshot_for_bec (couvre cas 3 toggle disable)
controlvanne/signals.py:201-219        — push post_save TireuseBec
controlvanne/models.py:496-504         — HistoriqueMaintenance (proxy RfidSession audit)
```

---

## 7. Décisions prises (à conserver pour la session de refactoring)

- ✅ **Option B** — on garde la règle "carte maintenance refusée pendant le service" (cas 4 push utile)
- ✅ **Option i** — pour l'audit du toggle `enabled`, on s'appuie sur `LogEntry` Django standard (pas de modèle dédié pour l'instant)
- ✅ **Cas 3 sans push** — le signal `post_save` couvre déjà via `_snapshot_for_bec` qui retourne le payload "En Maintenance"
- ✅ **Suppression timer JS 4s** — redondant avec le push `card_removed` serveur (fix Mike rend le Pi fiable sur l'envoi)
