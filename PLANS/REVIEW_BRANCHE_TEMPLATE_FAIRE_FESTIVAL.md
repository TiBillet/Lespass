# Code Review : branche `template-faire-festival` vs `main`

**Date :** 2026-03-06
**Scope :** 28 fichiers, +617 / -245 lignes

---

## CRITIQUES (a corriger avant merge)

### 1. @font-face CSS casses (faire_festival.css)

- **Ligne 15** : `format('opentype')` sur un `.woff2` → doit etre `format('woff2')`
- **Lignes 22-23** : double `src:` sur Faire-Stencil → la 2e ecrase la 1ere, le navigateur ne charge que `.otf` (perte du woff2 compresse)
- **Ligne 22** : `format('Woff2')` avec majuscule → `format('woff2')`

**Fix :** fusionner en une seule declaration `src:` avec virgule, corriger les formats :
```css
@font-face {
    font-family: 'faireregular';
    src: url('../fonts/Faire-Regular.woff2') format('woff2'),
         url('../fonts/Faire-Regular.woff') format('woff');
    font-weight: normal;
    font-style: normal;
    font-display: swap;
}

@font-face {
    font-family: 'fairestencil';
    src: url('../fonts/Faire-Stencil.woff2') format('woff2'),
         url('../fonts/Faire-Stencil.otf') format('opentype');
    font-weight: normal;
    font-style: normal;
    font-display: swap;
}
```

### 2. Contraste jaune/blanc insuffisant (WCAG)

- `#FFCB05` sur `#FFFFFF` = ratio 1.07:1 (minimum requis : 4.5:1)
- `.bouton-charger-plus` (ligne ~273) : fond jaune + texte blanc → illisible
- **Fix :** texte bleu (`--couleur-bleu-vif`) sur fond jaune partout

Matrice de contraste :
```
Jaune (#FFCB05) + Blanc (#FFFFFF) = 1.07:1  FAIL
Jaune (#FFCB05) + Bleu (#0055FF)  = 4.56:1  OK (AAA)
Bleu (#0055FF)  + Blanc (#FFFFFF) = 8.59:1  OK (AAA)
```

### 3. i18n manquant

- `retrieve.html:310` : `"Intervenant-e-s:"` sans `{% translate %}`
- `booking_form.html` : erreurs JS en francais dur-code (lignes 37-38, 329, 354, 476) — impossible a traduire
- `booking_form.html:425` : `"per buyer"` en anglais dur-code

### 4. Fichiers PLANS/ a nettoyer

Les fichiers de planification interne ne devraient pas atterrir dans le merge vers PreProd. A supprimer ou `.gitignore` avant merge.

### 5. Maquette HTML statique (~2.4 MB)

`BaseBillet/templates/faire_festival/maquette/` contient des fichiers HTML/CSS/PNG de prototypage non-fonctionnels. A supprimer ou deplacer dans `docs/` si valeur de reference.

---

## WARNINGS (a considerer)

### Accessibilite

| Fichier | Ligne | Probleme | Fix |
|---------|-------|----------|-----|
| `list.html` | 123 | Image background sans alt/aria | `role="img" aria-label="{{ event.name }}"` |
| `retrieve.html` | 145 | Image background sans alt/aria | Idem |
| CSS global | — | Pas de `:focus-visible` custom | Ajouter outline bleu sur focus |
| `retrieve.html` | 165→372 | Saut h1 → h3 (pas de h2) | Restructurer headings |
| @font-face | — | Pas de `font-display: swap` | Ajouter (evite FOIT) |

### Templates / HTMX

| Fichier | Ligne | Probleme | Fix |
|---------|-------|----------|-----|
| `booking_form.html` | 24-67, 313-412 | ~150 lignes JS inline (validation) | Extraire en module ES6 |
| `retrieve.html` | 276 | `{{ event.long_description\|safe }}` | Verifier sanitisation en DB |
| `home.html` | 130 | `{{ config.long_description\|safe }}` | Idem |
| `booking_form.html` | 4-6 | Style CSS inline en template | Deplacer en classe CSS |
| `list.html` | 190-191 | Inline style sur badge | Creer classe CSS |

### CSS

| Fichier | Ligne | Probleme |
|---------|-------|----------|
| faire_festival.css | 652 | Media query unique (768px), pas de breakpoints intermediaires |
| faire_festival.css | 393, 551 | Selecteurs vides `.carte-jour`, `.infos-clefs` |
| faire_festival.css | 457-468, 528-539 | Duplication pseudo-element `::after` (croix placeholder) |

---

## POSITIF

### Python (solide)

- **EventResource** (admin_tenant.py) : import/export CSV bien configure, skip_unchanged
- **Bugfix MembershipAddForm** : `hasattr(self, 'user_wallet_serialized')` avant acces → previent erreur 500
- **Bugfix ReservationAddAdmin** : `amount = 0` si `PaymentMethod.FREE`
- **cron_morning.py** : migration sequentielle des nouveaux schemas uniquement (au lieu de tous les tenants) → fix critique de perf

### Templates

- HTMX bien utilise : `hx-target`, `hx-swap="beforeend"` pour pagination, `hx-push-url`
- CSRF global via `hx-headers` sur body
- Partials bien structures (navbar, booking_form)
- Commentaires FALC

### CSS

- Variables CSS bien utilisees (~100% des cas)
- Nommage FALC (`.bouton-pilule`, `.badge-date`, `.titre-evenement`)
- Structure en sections numerotees (1-21)
- Transitions coherentes et non-intrusives

---

## Checklist avant merge

- [ ] Corriger les 3 @font-face (formats, double src, font-display)
- [ ] Corriger contraste jaune/blanc sur `.bouton-charger-plus`
- [ ] Ajouter `{% translate %}` sur "Intervenant-e-s:" et erreurs JS
- [ ] Nettoyer `PLANS/` avant merge vers PreProd
- [ ] Supprimer ou deplacer `maquette/` (~2.4 MB)
- [ ] Ajouter `role="img" aria-label` sur images background
- [ ] Verifier sanitisation de `long_description|safe`
- [ ] Ajouter `:focus-visible` pour accessibilite clavier
