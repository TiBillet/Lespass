# Code Review : branche `template-faire-festival` — travail d'Adrienne

**Date :** 2026-03-06
**Auteur reviewe :** Adrienne (13 commits)
**Scope :** Theme Faire Festival (CSS, templates, fonts) + 1 vue `booking_form`

Les commits de JonasFW13 (merge main, bugfixes back-end, discovery, infra) ne sont pas couverts ici.

---

## Contenu du travail d'Adrienne

### Templates et CSS (theme brutaliste Faire Festival)

**Fichiers :**
- `BaseBillet/static/faire_festival/` — CSS, fonts custom (Faire-Regular/Stencil), images, video
- `BaseBillet/templates/faire_festival/` — base, navbar, home, event/list, event/retrieve, membership/list
- `BaseBillet/templates/faire_festival/maquette/` — maquette HTML statique de reference

**Pages :**
- Accueil avec video (`motion-table.mp4`)
- Navbar avec boutons contact/login/mes billets
- Page programmation (liste events) avec filtres par tags et dropdown thematiques
- Page detail event avec offcanvas reservation (reutilise `reunion/views/event/partial/booking_form.html`)

### Vue Python : `booking_form` (commit `19f7306`)

Action GET sur `EventMVT` pour charger le formulaire de reservation dans un offcanvas depuis la page liste. Duplique une partie du contexte de `retrieve()` (prix, limites par utilisateur).

---

## CRITIQUES

### 1. @font-face CSS casses — CORRIGE

- Format MIME incorrect (woff2 declare comme opentype)
- Double `src:` qui ecrasait le woff2
- Majuscule dans `format('Woff2')`

**Statut :** corrige dans cette branche.

### 2. Filtre par thematique : FRONT SANS BACK

`list.html:73-104` affiche un dropdown avec **21 thematiques en dur** (`?theme=formation`, `?theme=bois`, etc.).

**Probleme :** aucun code back ne traite le parametre `?theme=`. La methode `federated_events_filter()` ne prend que `tags`, `search` et `page`. Le commentaire ligne 73 le confirme :
```html
<!-- TODO : Jonas doit travailler sur le back -->
```

**Resultat :** cliquer sur une thematique change l'URL mais ne filtre rien. L'utilisateur est trompe.

**Options :**
1. Coder le filtrage back (ajouter `theme` dans `federated_events_filter`)
2. Retirer le dropdown en attendant que le back soit pret
3. A minima, griser/desactiver le dropdown avec un tooltip "Bientot disponible"

### 3. Thematiques en dur dans le template

Les 21 thematiques (Formation, Bois, Metal, Textile, etc.) sont codees en dur dans le HTML. Si on code le back, il faudra les lier a un modele (Tag ? Nouveau modele Thematique ?) pour qu'elles soient dynamiques et administrables.

### 4. Contraste jaune/blanc (WCAG) — CHOIX ARTISTIQUE

Jaune `#FFCB05` sur blanc = ratio 1.07:1 (WCAG demande 4.5:1).
Le client a valide ce choix. Non bloquant pour le merge.

### 5. i18n manquant — CORRIGE

- `retrieve.html:310` : "Intervenant-e-s:" → `{% translate %}`
- `booking_form.html` : erreurs JS en dur → `{% translate %}`

**Statut :** corrige dans cette branche.

### 6. Fichiers a nettoyer avant merge

| Fichier | Raison |
|---------|--------|
| `PLANS/*.md` | Notes de travail internes, pas du code |
| `BaseBillet/templates/faire_festival/maquette/` (~2.4 MB) | Maquette HTML statique de prototypage |

---

## WARNINGS

### Accessibilite — CORRIGE (partiel)

| Probleme | Statut |
|----------|--------|
| Images background sans `role="img"` / `aria-label` | CORRIGE |
| Pas de `:focus-visible` custom | CORRIGE (outline bleu) |
| Saut h1 → h3 (pas de h2) dans `retrieve.html` | CORRIGE (h3 → h2) |
| `font-display: swap` manquant | CORRIGE |

### CSS

| Probleme | Localisation |
|----------|-------------|
| Media query unique (768px), pas de breakpoints intermediaires | `faire_festival.css:652` |
| Selecteurs vides `.carte-jour`, `.infos-clefs` | `faire_festival.css:393, 551` |
| Duplication pseudo-element `::after` (croix placeholder) x2 | `faire_festival.css:457-468, 528-539` |

### Templates

| Probleme | Localisation |
|----------|-------------|
| `{{ event.long_description\|safe }}` — XSS si pas sanitise en DB | `retrieve.html:276` |
| `{{ config.long_description\|safe }}` — idem | `home.html:130` |
| Inline style sur badge | `list.html:190-191` |

### Vue `booking_form` (Adrienne)

- Duplique la logique de contexte de `retrieve()` (prix, limites par user). A terme, extraire dans une methode partagee pour eviter la desynchronisation.
- Utilise le template `reunion/views/event/partial/booking_form.html` (partage avec le theme reunion) — OK pour la reutilisation, mais attention aux CSS specifiques Faire Festival dans ce partial.

---

## POSITIF

### Templates
- HTMX bien utilise : `hx-target`, `hx-swap="beforeend"` pour pagination, `hx-push-url`
- CSRF global via `hx-headers` sur body
- Partials bien structures (navbar, booking_form)
- Commentaires FALC en francais

### CSS
- Variables CSS bien utilisees (~100% des cas)
- Nommage FALC (`.bouton-pilule`, `.badge-date`, `.titre-evenement`)
- Structure en sections numerotees (1-21)
- Transitions coherentes et non-intrusives
- Polices custom bien integrees (woff2 + fallback)

### Filtrage par date
- Le groupement `dated_events` par jour est du code **preexistant** (pas d'Adrienne). Elle l'utilise correctement dans ses templates. Fonctionnel.

### Filtrage par tags
- Le dropdown tags fonctionne (back deja code dans `federated_events_filter`). Adrienne l'utilise correctement.

---

## Checklist avant merge

### Bloquant
- [ ] **Filtre thematique** : retirer ou desactiver le dropdown (le back n'existe pas)
- [ ] Nettoyer `PLANS/` avant merge vers PreProd
- [ ] Supprimer ou deplacer `maquette/` (~2.4 MB)

### Deja corrige (cette session)
- [x] @font-face (formats, double src, font-display)
- [x] i18n ("Intervenant-e-s:", erreurs JS)
- [x] Accessibilite (aria-label, focus-visible, headings)

### Non-bloquant (a traiter plus tard)
- [ ] Coder le filtrage par thematique en back
- [ ] Verifier sanitisation de `long_description|safe`
- [ ] Extraire la logique partagee `booking_form` / `retrieve` dans une methode commune
- [ ] Ajouter breakpoints CSS intermediaires (600px, 1200px)
- [ ] Supprimer selecteurs CSS vides
