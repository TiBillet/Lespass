# Chantier — Flow calibration HTMX + intégration admin

**Date** : 2026-05-05
**Statut** : 🟡 À challenger avec Mike — décisions ouvertes
**Branche** : `dev_vps`
**Contexte** : Review du merge `dev_vps` → `V2`. Mike a créé from scratch `calibration_views.py` (246 lignes) + 7 templates. La SPEC §2.17 demandait l'intégration dans l'admin Unfold ; Mike a fait une page autonome avec polling 8s + soumission série + bouton "Ignorer". Code mort présent (4 templates).

---

## 1. Le besoin métier (rappel)

Le débitmètre YF-S201 mesure le débit via des pulses GPIO. Le Pi convertit `pulses → volume` via un facteur `flow_calibration_factor` (default 6.5). Avec usure ou changement de fût, ce facteur dérive.

Calibration : verser un volume connu dans un verre gradué, comparer au volume mesuré par Django, ajuster.

Formule : `nouveau_facteur = ancien × (volume_django / volume_réel)`

Acte d'admin **rare** (quelques fois par an par tireuse), nécessite plusieurs aller-retours physique/écran (verser → retirer carte → revenir saisir).

---

## 2. Le flow Mike

1. Admin va sur `/controlvanne/calibration/<uuid>/`
2. La page polle toutes les **8s** via HTMX vers `/sessions/?depuis=<ts>`
3. Affiche les sessions maintenance terminées avec `volume_reel_ml IS NULL`
4. L'admin saisit les volumes (ou clique "✕ Ignorer", ou laisse vide)
5. Soumet le formulaire entier → `POST /serie/` → calcul facteur moyen + applique
6. Le Pi détecte la fin de session maintenance et fait `_rafraichir_calibration` (ping serveur) → applique le nouveau facteur sans redémarrer le service Pi

### Fichiers concernés

```
controlvanne/calibration_views.py                    246 lignes (créé from scratch par Mike)
controlvanne/urls.py:46-51                           3 routes
controlvanne/templates/calibration/page.html         152 lignes (modifié)
controlvanne/templates/calibration/partial_sessions.html      108 lignes (créé)
controlvanne/templates/calibration/partial_serie_result.html  85 lignes (créé)
controlvanne/Pi/controllers/tibeer_controller.py:_rafraichir_calibration   30 lignes (créé)
```

---

## 3. Code mort à supprimer (action immédiate)

4 templates référencent des URLs qui n'existent plus dans `urls.py` :

| Template | URL référencée | Statut |
|---|---|---|
| `partial_mesure.html` | `{% url 'calibration_soumettre' %}` | URL inexistante ❌ |
| `partial_recap.html` | `{% url 'calibration_appliquer' %}` | URL inexistante ❌ |
| `partial_vide.html` | mention `calibration_supprimer` | URL inexistante ❌ |
| `partial_confirmation.html` | modifié par Mike mais jamais rendu par `calibration_views.py` | Mort ❌ |

**~270 lignes** mortes. À supprimer purement et simplement. Pas de dépendance, pas de migration. Le flow réel utilise uniquement `partial_sessions.html` + `partial_serie_result.html`.

---

## 4. Écart par rapport à la SPEC (non-bloquant)

`SPEC_CONTROLVANNE.md` §2.17 et `PLAN_PHASE_4.md` Tâche 6 demandent :
> "Modifier page.html pour hériter de `admin/base_site.html` ... Les templates de calibration sont des pages admin HTMX. Elles doivent hériter du base admin Unfold."

Mike fait `{% extends "base.html" %}` (le base kiosk autonome).

**Conséquences** :
- Pas de sidebar admin Unfold sur la page calibration
- Le bouton "← Admin" hardcodé pour revenir au formulaire tireuse
- Look différent du reste de l'admin (l'admin perd le contexte de navigation)

### Décision

🟡 **Non-bloquant — à voir à l'usage.** On laisse en l'état pour le merge. Si l'admin se sent perdu sans la sidebar Unfold pendant la calibration, on basculera vers `admin/base_site.html` ultérieurement. Coût de bascule : ~20 lignes (suppression liens hardcodés, intégration sidebar).

---

## 5. Décisions ouvertes à challenger avec Mike

### 5.1 Bouton "Ignorer" + `window.ignoredSessions` (Set JS)

**Constat** : `partial_sessions.html` a un bouton "✕ Ignorer" qui ajoute le pk au Set `window.ignoredSessions` (~30 lignes JS dans `page.html`), vide l'input, désactive et grise la ligne. Le Set est ré-appliqué après chaque polling via `appliquerIgnores()` sur `htmx:afterSettle`.

**Mais** `calibration_views.py:174-177` dit déjà :
```python
if not valeur_brute:
    continue  # Champ laissé vide → on ignore cette session
```

→ **Un input vide suffit côté serveur**. Le bouton "Ignorer" + le Set JS + le re-render = ~30 lignes pour reproduire ce que `valeur=""` fait gratuitement.

**Question pour Mike** :
> Pourquoi avoir codé un bouton "Ignorer" + Set JS persistant alors que vider l'input fait déjà le job ? Y avait-il un cas d'usage qu'on n'a pas vu (ex: marquer "ignoré pour l'audit", garder la trace que l'admin a explicitement choisi d'ignorer) ?

**Recommandation** (à challenger) : supprimer le bouton et le JS associé. -30 lignes. L'admin vide la case ou ne la remplit pas.

### 5.2 Polling 8s vs bouton "Rafraîchir"

**Constat** : la page polle toutes les 8s en permanence via `hx-trigger="load, every 8s"`. Coût négligeable en pratique (calibration est rare) mais polling permanent même si la page reste ouverte sur un onglet oublié.

**POC alternative** : `hx-trigger="load, click from:#btn-refresh"` → charge une fois au load, puis l'admin clique pour rafraîchir quand il revient.

**Question pour Mike** :
> Pourquoi 8s en polling continu plutôt qu'un bouton "Rafraîchir" ? L'admin alterne entre verser/retirer carte/revenir saisir — un bouton à chaque retour serait suffisant. Y a-t-il un cas où l'admin observe la page sans toucher au matériel ?

**Recommandation** (à challenger) : garder le polling, c'est du polish acceptable pour un acte rare. Mais à challenger pour vérifier qu'il y a une raison.

### 5.3 Filtre `?depuis=<ts>` + bouton "Nouvelle série"

**Constat** : la page accepte `?depuis=<timestamp>` qui filtre les sessions à partir de ce moment. Le bouton "↺ Nouvelle série" pose `?depuis=<now>` dans l'URL.

**Problèmes** :
- Si l'admin oublie de cliquer "Nouvelle série", il voit toutes les sessions cumulées (y compris celles non-saisies des séries précédentes)
- Si l'admin clique "Nouvelle série" sans mesurer, les sessions précédentes deviennent **invisibles pour toujours** (pas de mécanisme "voir l'historique complet")
- Ajoute la complexité timestamps + propagation `depuis` dans hidden field POST + reset Set JS

**POC alternative** : filtre serveur fixe sur les **dernières 24h glissantes**. Pas de paramètre query, pas de bouton "Nouvelle série", pas de timestamps à gérer. L'admin voit toujours les sessions des 24h précédentes.

**Question pour Mike** :
> Le système `?depuis` + "Nouvelle série" couvre quel cas d'usage précisément ? Pourquoi pas un filtre fixe 24h ou "depuis dernière saisie" automatique ? L'admin a-t-il vraiment besoin de définir manuellement le début d'une série ?

**Recommandation** (à challenger) : à voir avec Mike s'il y a un cas d'usage qu'on rate. A priori, un filtre 24h glissantes serait plus simple et couvrirait 95% des cas.

### 5.4 `_rafraichir_calibration` côté Pi

**Constat** : après chaque session maintenance, le Pi pinge automatiquement le serveur pour récupérer le nouveau facteur de calibration (`tibeer_controller.py:_rafraichir_calibration`, ~30 lignes). L'admin n'a pas à redémarrer le service Pi pour appliquer un nouveau facteur.

**Coût** : ~30 lignes Pi + 1 ping HTTP supplémentaire après chaque retrait de carte maintenance.

**Bénéfice** : l'admin applique le facteur, retire la carte, le Pi récupère immédiatement la nouvelle valeur. Pas de SSH `systemctl restart tibeer.service`.

**Question pour Mike** :
> Bon polish. Confirmé que c'est utile en exploitation ? Ou est-ce qu'un redémarrage manuel après calibration suffirait (l'admin est physiquement à côté du Pi) ?

**Recommandation** (à challenger) : garder. Coût faible, gain UX réel pour un acte qui se fait sur place avec le matériel. Mais si on veut alléger le Pi au max, on peut supprimer.

### 5.5 i18n + accessibilité

**Constat** :
- `page.html`, `partial_sessions.html`, `partial_serie_result.html` : ~30 textes FR en dur
- Un seul `{% translate %}` ("Operating procedure")
- Messages d'erreur dans `calibration_views.py:158, 223` sans `_()` (gettext)
- Aucun `aria-live` sur la zone polling 8s → les screen readers ratent les nouvelles sessions

**Pas une décision à challenger** — c'est une dette djc à payer. À faire dans le commit follow-up de cleanup.

**Action** :
- Annoter avec `{% translate %}` / `{% blocktrans %}` les textes user-facing
- Ajouter `_()` sur les messages d'erreur dans la vue
- Ajouter `aria-live="polite"` sur `#sessions-poll`
- Lancer `makemessages` + `compilemessages`

---

## 6. Bilan

| Action | Lignes | Statut |
|---|---|---|
| Supprimer 4 templates morts | **-270** | ✅ Action immédiate |
| Supprimer bouton "Ignorer" + Set JS | -30 | 🟡 À challenger Mike (5.1) |
| Migrer `extends` vers `admin/base_site.html` | ±20 | 🟡 Non-bloquant — à voir à l'usage |
| Polling 8s → bouton Rafraîchir | -5 | 🟡 À challenger Mike (5.2) |
| `?depuis` → filtre 24h glissantes | -10 | 🟡 À challenger Mike (5.3) |
| Garder `_rafraichir_calibration` Pi | 0 | 🟡 À challenger Mike (5.4) |
| Ajouter `{% translate %}` + `aria-live` + `_()` | +1 (aria) + annotations | ✅ Action immédiate |
| **Net possible** | **~-280 à -315 lignes** + conformité djc | |

---

## 7. Couplage avec autres chantiers

Indépendant des autres mémos `merge_dev_vps/` :
- Pas de dépendance billing (pas de cascade dans les vues calibration)
- Pas de dépendance auth-kiosk (vues protégées par `@staff_member_required`)
- Pas de dépendance push WS refus (calibration n'utilise pas le canal WS kiosk)

Peut être appliqué isolément.

---

## 8. Fichiers à ouvrir dans PyCharm

```
controlvanne/calibration_views.py:1-246       — 3 vues + 3 helpers
controlvanne/urls.py:46-51                    — 3 routes
controlvanne/templates/calibration/page.html  — squelette + JS Set ignoredSessions
controlvanne/templates/calibration/partial_sessions.html       — formulaire série
controlvanne/templates/calibration/partial_serie_result.html   — résultat application
controlvanne/templates/calibration/partial_mesure.html         — MORT
controlvanne/templates/calibration/partial_recap.html          — MORT
controlvanne/templates/calibration/partial_vide.html           — MORT
controlvanne/templates/calibration/partial_confirmation.html   — MORT
controlvanne/Pi/controllers/tibeer_controller.py:215-265       — _rafraichir_calibration
TECH DOC/SESSIONS/CONTROLVANNE/SPEC_CONTROLVANNE.md §2.17      — spec intégration Unfold
TECH DOC/SESSIONS/CONTROLVANNE/PLAN_PHASE_4.md Tâche 6         — plan détaillé
```

---

## 9. Statut des décisions

| # | Sujet | Statut | Décision finale |
|---|---|---|---|
| 1 | `extends "base.html"` vs `admin/base_site.html` | 🟡 Non-bloquant | À voir à l'usage |
| 2 | Bouton "Ignorer" + Set JS | 🟡 À challenger | Session future avec Mike |
| 3 | Polling 8s vs bouton Rafraîchir | 🟡 À challenger | Session future avec Mike |
| 4 | `?depuis` vs filtre 24h | 🟡 À challenger | Session future avec Mike |
| 5 | `_rafraichir_calibration` Pi | 🟡 À challenger | Session future avec Mike |
| 6 | i18n + aria-live | ✅ Décidé | À ajouter en cleanup |
| 7 | 4 templates morts | ✅ Décidé | À supprimer immédiatement |
