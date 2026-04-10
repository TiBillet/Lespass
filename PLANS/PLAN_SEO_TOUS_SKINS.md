# Plan : SEO — Appliquer a tous les skins

## Contexte

Le skin `faire_festival` a ete corrige pour le SEO (session 2026-04-10).
Ces corrections n'existent PAS dans le skin `reunion` ni dans aucun autre skin.
A terme, il faudrait mutualiser dans un base template commun ou un partial partage.

## Ce qui a ete fait sur faire_festival (a reporter)

### 1. Canonical URL
- `<link rel="canonical" href="{{ request.build_absolute_uri }}">`
- Fichier : `faire_festival/base.html`
- **Absent de** : `reunion/base.html`

### 2. JSON-LD Organization + WebSite
- Schema.org `Organization` : nom, description, logo, adresse, reseaux sociaux
- Schema.org `WebSite` : nom, url
- Fichier : `faire_festival/base.html` (bloc `<script type="application/ld+json">`)
- **Absent de** : `reunion/base.html`

### 3. Meta descriptions uniques par page
- Chaque page surcharge `{% block meta_description %}` avec un texte unique
- Pages corrigees : `home.html`, `le_faire_festival.html`, `infos_pratiques.html`
- **reunion** : seul `event/retrieve.html` surcharge ce bloc, les autres ont la description par defaut

### 4. OG/Twitter title+description uniques par page
- Chaque page surcharge `{% block og_title %}`, `{% block og_description %}`, `{% block twitter_title %}`, `{% block twitter_description %}`
- **reunion** : meme probleme, seul `event/retrieve.html` surcharge

### 5. `<h1>` sur chaque page
- Ajoute en `visually-hidden` quand le titre est une image
- **reunion** : a verifier page par page

### 6. `<main>` unique
- Les pages enfants ne doivent pas re-declarer `<main>` si le base.html le fournit
- **reunion** : a verifier

## Approche recommandee

### Option A — Partial partage (recommandee)
Creer un partial `partials/seo_jsonld.html` commun, inclus par tous les base.html :
```html
{% include "partials/seo_jsonld.html" %}
```
Contient le JSON-LD Organization + WebSite. Chaque skin l'inclut dans son `<head>`.

### Option B — Base template commun
Faire heriter `faire_festival/base.html` et `reunion/base.html` d'un `_base_seo.html` abstrait.
Plus propre mais plus de refactoring.

## Checklist pour la prochaine session

- [ ] Ajouter `<link rel="canonical">` dans `reunion/base.html`
- [ ] Creer le partial JSON-LD et l'inclure dans `reunion/base.html`
- [ ] Verifier les `<h1>` de chaque page du skin `reunion`
- [ ] Verifier les `<main>` en double dans le skin `reunion`
- [ ] Ajouter des meta descriptions uniques sur les pages `reunion` (home, event/list, membership/list)
- [ ] Surcharger OG/Twitter dans les pages `reunion`
- [ ] Verifier que `og:image` rend une URL absolue (pas relative)
- [ ] Tester avec Google Rich Results Test sur un tenant public

## Autres corrections faites sur faire_festival (non SEO)

### Securite emails
- `email_generique.html` : retire `| escapejs` sur `main_text_2`, ajoute `clean_html()` sur 3 champs dans `tasks.py`
- `buy_confirmation.html` : `clean_html()` sur `custom_confirmation_message`

### Images
- 9 PNG convertis en WebP (6.8 Mo → 850 Ko, -87%)
- 4 petits PNG gardes (WebP plus lourd sur les illustrations flat)
- Fichiers morts conserves volontairement (maquette = archive)

### Carte interactive
- Image statique `carte.webp` remplacee par Leaflet + CartoDB Positron
- Coordonnees GPS depuis `config.postal_address.latitude/longitude`
- Marqueur custom "F" jaune (#FFD700) / bleu (#0077F5)
- `{% localize off %}` pour eviter la virgule francaise dans les coordonnees JS
- Adresse affichee depuis `config.postal_address` (avec fallback `config.adress`)

### Footer
- Adresse dynamique depuis `config.postal_address` (etait hardcodee)

### Navbar
- `href=""` → `href="#"` sur le bouton Contact

### HTML
- `<p>` mal ferme dans infos_pratiques.html
- Texte non traduit ajoute dans `{% translate %}`
