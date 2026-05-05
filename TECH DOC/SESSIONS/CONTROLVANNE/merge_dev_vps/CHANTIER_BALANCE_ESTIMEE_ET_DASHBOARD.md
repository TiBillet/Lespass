# Chantier — Balance estimée pendant le tirage et push WS dashboard

**Date** : 2026-05-05
**Statut** : 🟡 À reprendre — décision α / β en attente
**Branche** : `dev_vps`
**Contexte** : Review du merge `dev_vps` → `V2`. Mike recalcule le solde DB cascade à chaque `pour_update` (toutes les 1s) pour afficher une "balance estimée" sur le kiosk. Le dashboard global a aussi besoin du push WS, mais pas du recalcul DB.

---

## 1. Décision architecturale conservée

> **Le serveur fournit le solde (à l'authorize) et récupère la vente (au pour_end). Pendant le tirage, il ne pilote rien.**

C'est explicitement la décision de la `SPEC_PHASE_6_CLIENT_PI.md` §4 :
> "Plus besoin de round-trip serveur pour forcer la fermeture."

Le Pi ferme la vanne localement quand `served_ml >= allowed_ml` (`tibeer_controller.py:172-174`). `allowed_ml` est calculé une fois à l'authorize et n'évolue pas pendant le tirage.

**Conséquence** : le serveur n'a aucun **besoin métier** de connaître le solde courant entre l'authorize et le pour_end.

---

## 2. Le besoin légitime : push WS pour le dashboard global

`controlvanne/routing.py:23-26` expose deux groupes Channels :

```
/ws/rfid/all/      → groupe rfid_state.all     (dashboard N tireuses)
/ws/rfid/<uuid>/   → groupe rfid_state.<uuid>  (kiosk 1 tireuse)
```

`_push_ws_kiosk()` (`viewsets.py:48-89`) push **vers les deux groupes simultanément** à chaque event (authorize + pour_update + pour_end + card_removed).

**Sans push WS au pour_update**, le dashboard global verrait :
- Authorize → "vanne ouverte"
- *(silence pendant 30s)*
- Pour_end → "vanne fermée, X cl servis"

Pas d'animation de jauge volume sur les autres tireuses. **Le push WS au pour_update est légitime** — il sert le dashboard et le kiosk individuel.

---

## 3. Ce qui pose problème

Mike fait **deux choses** au `pour_update` (`viewsets.py:588-613`) :

| Action | Légitimité | Coût |
|---|---|---|
| **A** — Persister `volume_end_ml`, `volume_delta_ml`, `dernier_volume_ml` sur la `RfidSession` (lignes 514-525) | ✅ **Obligatoire** — sert à `calibration_views.py` qui lit `volume_delta_ml` pour comparer au volume réel | 1 `UPDATE` SQL |
| **B** — Push WS vers `rfid_state.all` + `rfid_state.<uuid>` avec `volume_ml`, `vanne_ouverte` | ✅ **Légitime** — sert le dashboard et le kiosk | 0 SQL (channel_layer) |
| **C** — Recalculer le solde DB cascade (`obtenir_contexte_cashless` + `calculer_solde_total_cascade`) pour mettre `balance` dans le payload | ❌ **Inutile** — le solde DB n'a pas changé depuis l'authorize | **5-7 queries SQL/sec** |

A et B doivent rester. **C est à supprimer.**

---

## 4. Pourquoi C est strictement inutile

Entre l'authorize et le pour_end, **aucun débit n'est créé en DB** sur le wallet du client. Le débit cascade arrive uniquement au pour_end (`facturer_tirage` dans `transaction.atomic()`). Donc :

```
solde_DB(t=authorize) == solde_DB(t=pour_update_1) == ... == solde_DB(t=pour_update_N)
```

Recalculer N fois la même valeur = travail inutile. Le commentaire de Mike admet d'ailleurs que c'est de l'éphémère :
> "Estimer le solde restant — ici on affiche une **estimation visuelle**."

---

## 5. La solution minimaliste

### 5.1 Bloc à conserver (persistance + push WS)

```python
elif event_type == "pour_update":
    # A. Persister le volume cumulé sur la session (sert calibration + audit)
    session.volume_end_ml = volume_ml
    session.volume_delta_ml = volume_ml
    session.dernier_volume_ml = volume_ml
    session.save(update_fields=[
        "volume_end_ml", "volume_delta_ml", "dernier_volume_ml",
    ])

    # B. Push WS vers dashboard + kiosk (animation jauge)
    _push_ws_kiosk(
        tireuse,
        _construire_payload_session(
            tireuse,
            session,
            vanne_ouverte=True,
            message="Tirage en cours",
        ),
    )
```

### 5.2 Bloc à supprimer (lignes 588-613)

Le bloc `if not session.is_maintenance and tireuse.prix_litre > 0: from controlvanne.billing import ...` qui recalcule la cascade.

### 5.3 Pour afficher la balance estimée

Deux options non-exclusives :

**Option α — Calcul JS côté client (kiosk + dashboard)**
À l'authorize, le payload WS contient déjà `solde_centimes` (via `_construire_payload_session` qui transmet ce que la réponse authorize a calculé). Le JS dashboard / kiosk mémorise `solde_initial[uuid]`. À chaque pour_update reçu, il calcule :

```js
balance = solde_initial[uuid] - volume_ml * prix_litre / 1000
```

**Coût serveur : 0 query.** **Coût client : 1 soustraction.** **Lignes Python ajoutées : 0.**

**Option β — Mémoriser en DB une seule fois à l'authorize**
Ajouter `RfidSession.solde_initial_centimes = IntegerField(default=0)`. Renseigné à l'authorize quand `solde_centimes` est calculé. Au pour_update, le serveur lit `session.solde_initial_centimes - cout_volume` (la session est déjà chargée par `RfidSession.objects.get(...)` en haut de `event()` → **zéro query supplémentaire**).

**Coût serveur : 1 migration + 3 lignes au pour_update.** Plus traçable (la valeur initiale est en DB).

Recommandation : **α + β** combinés. β mémorise pour audit, α utilise la valeur côté client pour l'animation. Si demain on veut voir "solde au début / solde à la fin" dans l'historique, β l'a déjà.

---

## 6. Les artefacts morts à nettoyer (que tu pourrais avoir oubliés)

### 6.1 `force_close` dans le TypedDict

`controlvanne/ws_payloads.py:41` :
```python
force_close: bool  # True si Django demande la fermeture immédiate (solde épuisé)
```

Défini mais **jamais peuplé** dans le code serveur (vérifié via `rg force_close controlvanne/ -g '!Pi/'`). Vestige d'une intention non aboutie. À supprimer du TypedDict pour ne pas suggérer aux futurs devs que le mécanisme existe.

### 6.2 `debit_cl_min` dans le TypedDict

`controlvanne/ws_payloads.py:35` :
```python
debit_cl_min: float  # Débit instantané (cL/min)
```

Défini mais :
- Jamais calculé côté serveur dans `_construire_payload_session()`
- Mis à `0.0` en dur dans le payload initial (`signals.py:65` et `consumers.py:186`)
- Calculé uniquement dans `Pi/tests/test_debimetre.py:88` (test hardware standalone, pas remonté via API)

À supprimer ou à câbler sérieusement (le Pi connaît son débit instantané, il pourrait le passer dans `pour_update`).

### 6.3 Mismatch `debit_l_min` vs `debit_cl_min`

`consumers.py:186` envoie `"debit_l_min": 0.0` (litres/min) dans le payload de la tireuse inconnue. Mais le TypedDict définit `debit_cl_min` (centilitres/min). Incohérence silencieuse — sans conséquence en pratique (`0.0` est `0.0`), mais à uniformiser quand on nettoiera.

---

## 7. Trou fonctionnel : reconnexion dashboard

`consumers.py:_construire_payload_initial()` ligne 130-132 :
```python
# Pas de payload initial pour le groupe global
if not slug_tireuse or slug_tireuse.lower() == "all":
    return None
```

**Si le dashboard reconnecte au milieu d'un tirage** (perte WS + reconnexion auto), il ne reçoit aucun état. Il attendra le prochain push (le prochain pour_update du Pi, donc max 1s) pour se mettre à jour.

C'est OK en pratique — la latence d'1s est invisible. **Mais si la vanne est en cours et qu'aucun pour_update n'arrive ensuite** (Pi crashé / réseau Pi coupé), le dashboard reste figé sur son ancien état (vide ou périmé).

Solution si on veut robuste : pour le groupe "all", construire un payload initial qui itère toutes les `TireuseBec` du tenant et envoie l'état courant. Coût : 1 query par connexion dashboard. Pas critique mais à mentionner.

---

## 8. Aller-retour architectural Pi → serveur → Chromium local

Le Pi qui sert le kiosk fait tourner Chromium **sur la même machine**. Pourtant l'animation de la jauge transite :
```
Pi (Python) → HTTP → serveur Django → WS → Chromium (sur le Pi)
```

C'est un aller-retour réseau pour animer une jauge sur l'écran local. **Si le réseau Pi↔serveur est coupé**, le kiosk se fige même si le Pi sait que la vanne est ouverte.

Architecture alternative envisageable (mais hors scope du merge) : Pi → loopback WebSocket local → Chromium. Le Pi serait son propre serveur d'animations pour son kiosk. Le serveur distant ne servirait que pour le dashboard global.

**Décision actuelle Mike (à conserver pour la simplicité)** : tout passe par le serveur. Trade-off acceptable pour un bar bien connecté. À documenter si on veut s'en souvenir.

---

## 9. Fréquence du `pour_update`

`Pi/controllers/tibeer_controller.py` :
```python
UPDATE_INTERVAL_S = 1.0
```

Le Pi envoie un `pour_update` toutes les 1s. Sur N tireuses simultanées en heure de pointe, ça fait N requêtes/sec côté serveur.

Avec ma proposition (push WS sans recalcul cascade) :
- Coût serveur par pour_update : 1 `UPDATE` SQL (`session.save(update_fields=...)`) + 1 push channel_layer
- Pour 10 tireuses actives : 10 `UPDATE`/sec — négligeable

Avec la version Mike :
- Coût par pour_update : 1 `UPDATE` + **5-7 SELECT** + push
- Pour 10 tireuses : 50-70 SELECT/sec juste pour afficher des nombres

Si le besoin d'animer fluide n'est pas critique, on pourrait passer à 2s ou 3s côté Pi (économie ×2-3) sans dégrader l'UX dashboard. Pas urgent mais à garder en tête.

---

## 10. Race condition pour_end perdu

Si le Pi envoie `pour_end` mais le réseau perd la requête (timeout), Django ne crée pas la facturation. La bière est servie, le client a sa pinte, **aucune trace de transaction**.

Côté Mike : pas de mécanisme de retry sur `pour_end`. Le Pi log l'erreur et passe à la session suivante. **C'est acceptable pour un bar** (la facturation tireuse est un bonus par rapport à la facturation manuelle), mais à documenter comme limite connue.

Hors scope balance estimée mais lié au sujet "que faire si réseau Pi/serveur instable".

---

## 11. Bilan des actions sur ce sujet

| Action | Fichier | Lignes |
|---|---|---|
| Supprimer le recalcul cascade au pour_update | `viewsets.py:588-609` | -22 |
| Adopter option β : ajouter `RfidSession.solde_initial_centimes` | `models.py` + migration + 1 ligne authorize + 3 lignes pour_update | +5 |
| Adopter option α : push `solde_centimes` initial dans le payload authorize | déjà le cas via `_construire_payload_session` (vérifier) | 0 |
| Calculer la balance côté JS dashboard et kiosk | `panel_kiosk.js` (kiosk individuel) + future vue dashboard | ~5 lignes JS |
| Supprimer `force_close` du TypedDict | `ws_payloads.py:41` | -1 |
| Supprimer `debit_cl_min` du TypedDict (ou le câbler) | `ws_payloads.py:35` + 2 endroits | -3 |
| Corriger mismatch `debit_l_min` / `debit_cl_min` | `consumers.py:186` | +1 |
| (Optionnel) Payload initial pour groupe "all" | `consumers.py:_construire_payload_initial` | +15 |
| (Optionnel) Réduire fréquence pour_update à 2s | `Pi/controllers/tibeer_controller.py` `UPDATE_INTERVAL_S` | 0 |

**Net réaliste : ~-20 lignes serveur + ~5 lignes JS, et 0 query SQL pendant le tirage** tout en gardant l'animation dashboard.

---

## 12. Décisions à prendre

1. **α / β / α+β** pour la balance estimée ? *(recommandé : α+β)*
2. **Reconnexion dashboard** : payload initial pour le groupe "all" ou on accepte le trou fonctionnel ?
3. **Fréquence pour_update** : on garde 1s ou on passe à 2s ?
4. **Retry pour_end** : on documente la limite ou on ajoute un mécanisme de réconciliation (queue locale Pi qui rejoue les pour_end perdus) ?

À décider avec le mainteneur.

---

## 13. Fichiers à ouvrir dans PyCharm

```
controlvanne/viewsets.py:514-525       — persistance volume_delta_ml (à garder)
controlvanne/viewsets.py:588-613       — recalcul cascade (à supprimer)
controlvanne/ws_payloads.py:35,41      — artefacts morts force_close + debit_cl_min
controlvanne/consumers.py:130-132      — pas de payload initial pour "all"
controlvanne/consumers.py:186          — mismatch debit_l_min vs debit_cl_min
controlvanne/calibration_views.py:53   — utilise volume_delta_ml (raison de garder la persistance)
controlvanne/Pi/controllers/tibeer_controller.py — UPDATE_INTERVAL_S, allowed_ml
controlvanne/routing.py:23-26          — les deux canaux WS
```
