# Session 06 — Tuiles billet dans la grille + données event + types PV

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django + HTMX + Cotton).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

Le PV de type `BILLETTERIE` ('T') construit ses articles depuis les événements futurs.
Pas de double typage : le Product n'a pas besoin de `methode_caisse='BI'` pour apparaître.
C'est le **type du PV** qui détermine le chargement automatique.

Les events apparaissent comme **pseudo-catégories** dans la sidebar `<c-categories>` existante.
Filtre CSS côté client (instantané, `cat-{event_uuid}`), pas de round-trip HTMX.

## CE QUI A ÉTÉ FAIT

### Types PV restaurés (migration 0005)

- `ADHESION = 'A'`, `CASHLESS = 'C'`, `BILLETTERIE = 'T'` ajoutés à `COMPORTEMENT_CHOICES`
- `KIOSK` reste supprimé (app séparée dans le futur)
- Le type du PV détermine le chargement automatique, le M2M est toujours chargé en plus
- Fixture `create_test_pos_data` mise à jour : Cashless→CASHLESS, Adhesions→ADHESION, Accueil Festival→BILLETTERIE

### Composant Cotton `billet_tuile.html` + CSS

- `laboutik/templates/cotton/billet_tuile.html` : layout paysage, data-* compatibles articles.js
- `laboutik/static/css/billet_tuile.css` : grid-column span 2, jauge statique, responsive
- Intégré dans `cotton/articles.html` via `{% include %}` conditionnel
- Chargé dans `base.html`

### Données de test

- Catégorie "Billetterie", 2 Products BI, 2 Events futurs (demain + après-demain, jauge 50)
- PV "Accueil Festival" (type BILLETTERIE) : 2 billets + Bière + Eau
- Billets ajoutés au PV "Mix"

### Enrichissement `_construire_donnees_articles()`

- Pré-chargement Events en 1 requête (anti N+1)
- `methode_caisse` ajouté à tous les article_dict
- Articles BI enrichis avec dict `event` (uuid, name, datetime, jauge, pourcentage, complet)
- Jauge statique (WebSocket en phase 4)

## TÂCHES COMPLÉTÉES

### TÂCHE A — Charger depuis events quand PV est BILLETTERIE ✅

- `_construire_donnees_articles()` : quand PV BILLETTERIE, charge events futurs (datetime >= now - 1j)
- 1 tuile = 1 Price. ID unique par Price (pas Product) pour éviter doublons panier
- Jauge : Price.stock si défini, sinon Event.jauge_max
- Couleurs par event (palette cyclique 8 couleurs)
- Events sans produit publiés filtrés
- Articles M2M chargés en plus

### TÂCHE B — Events comme pseudo-catégories ✅

- `_construire_donnees_categories()` : events futurs ajoutés avec `is_event: True`, date, jauge
- UUID event = id pseudo-catégorie → filtre CSS `cat-{event_uuid}` fonctionne

### TÂCHE C — Rendu event dans `cotton/categories.html` ✅

- `{% if cat.is_event %}` : date + mini-jauge + `data-testid`
- CSS : `.category-event` avec date, jauge, places
- Sidebar scrollable (scrollbar fine 4px)
- `aria-hidden` sur toutes les icônes, `aria-label` sur la jauge

### TÂCHE D — Adapter templates ✅

- `billet_tuile.html` : classe `article-container` ajoutée (clic fonctionne)
- CSS responsive : portrait (span 1) < 599px, icône réduite 600-1022px
- `visually-hidden` ajouté au CSS laboutik

### Polish ✅

- Spinner loading-states (extension HTMX officielle, délai 400ms)
- Navigation PV burger menu convertie en hx-get (anti-blink)
- `aria-hidden` sur icônes pré-existantes (categories.html, header.html)
- Products billet retirés de create_test_pos_data (plus nécessaires)
- 55 tests pytest passent (0 erreur)

## VÉRIFICATION

```bash
docker exec lespass_django poetry run python manage.py tenant_command create_test_pos_data --schema=lespass
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

### Vérification manuelle

Ouvrir le PV "Accueil Festival" (type BILLETTERIE) :
- [ ] Tuiles billet en paysage (2 colonnes) avec jauge et date
- [ ] Tuiles standard (Bière, Eau) en carré
- [ ] Sidebar : catégories classiques + events avec date et mini-jauge
- [ ] Filtre par event dans la sidebar → seules les tuiles de cet event
- [ ] Clic tuile billet → article ajouté au panier
- [ ] PV "Bar" (type DIRECT) → inchangé, pas de tuiles billet

### Ce qu'on ne touche PAS

- `panier_necessite_client` / `panier_a_billets` → session 07
- `moyens_paiement()` → session 07
- JS existant (`articles.js`, `tarif.js`, `addition.js`)
