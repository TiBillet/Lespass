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

## CE QUI RESTE À FAIRE (cette session)

### TÂCHE A — Charger depuis events quand PV est BILLETTERIE

Dans `_construire_donnees_articles()`, quand `point_de_vente_instance.comportement == BILLETTERIE` :
- Charger les events futurs publiés ( dont ceux en cours, - 1 jour ) : `Event.objects.filter(published=True, archived=False, datetime__gte=now - 1 jour)`
- Pour chaque event, pour chaque Price publiée de chaque Product lié → 1 article_dict
- 1 tuile = 1 Price (pas 1 Product). Un produit avec 3 tarifs → 3 tuiles
- Chaque tuile porte `cat-{event_uuid}` pour le filtre sidebar
- Les articles du M2M `products` sont chargés en plus (comme avant)
- Supprimer le filtre `methode_caisse='BI'` — c'est le type du PV qui décide

#### Jauges — 3 niveaux dans les modèles

| Niveau | Champ | Modèle | Signification |
|--------|-------|--------|---------------|
| Event | `jauge_max` | Event | Capacité totale (toutes catégories confondues) |
| Product | `max_per_user` | Product | Limite par utilisateur (pas une jauge globale) |
| Price | `stock` | Price | Capacité par tarif par event (`out_of_stock(event)`) |

Exemple : Concert 500 places, Plein tarif stock=200, Réduit stock=100, VIP stock=50 → 150 non attribuées.

#### UX jauge sur la tuile : afficher la jauge la plus restrictive

- Si `Price.stock` est défini → jauge du tarif sur la tuile (ex: "12/50 VIP")
- Sinon → jauge de l'event sur la tuile (ex: "42/500")
- La jauge event est **toujours visible dans la sidebar** (pseudo-catégorie) — c'est la jauge globale
- Pas d'empilement de 3 jauges sur une tuile — illisible sur écran tactile festival
- `Price.out_of_stock(event)` détermine si la tuile est grisée (complet pour ce tarif)
- `Event.complet()` détermine si toutes les tuiles de l'event sont grisées

### TÂCHE B — Events comme pseudo-catégories dans `_construire_donnees_categories()`

Quand le PV est `BILLETTERIE`, enrichir la liste des catégories avec les events futurs :
- Chaque event → un dict catégorie avec `is_event: True`, `date`, `jauge_max`, `places_vendues`, `pourcentage`
- UUID de l'event comme `id` de la pseudo-catégorie
- La jauge event dans la sidebar = jauge globale (Event.jauge_max)
- Les catégories classiques (Bar, etc.) restent si le PV a des articles M2M classiques

### TÂCHE C — Rendu event dans `cotton/categories.html`

Ajouter `{% if cat.is_event %}` pour afficher :
- Date de l'event (format court)
- Mini-jauge (barre + texte X/Y ou COMPLET)
- `data-testid="billetterie-sidebar-event-{uuid}"`

### TÂCHE D — Adapter `cotton/articles.html` et `billet_tuile.html`

- La condition `article.methode_caisse == 'BI'` doit être remplacée par `article.is_billet` ou `article.event`
- Le composant `billet_tuile.html` reçoit les données event depuis le dict article

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
