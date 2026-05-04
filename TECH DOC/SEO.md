# SEO — Etat des lieux et conventions

## Architecture SEO actuelle

### Fichiers cles

| Fichier | Role |
|---|---|
| `reunion/base.html` | Meta tags, OG, Twitter, canonical, JSON-LD (via partial) |
| `faire_festival/base.html` | Idem, adapte au skin FF |
| `seo/partials/json_ld_organization.html` | JSON-LD Organization + WebSite (partial partage) |
| `BaseBillet/sitemap.py` | Sitemap XML (Events, Products, StaticViews) |
| `BaseBillet/views_robots.py` | robots.txt dynamique |

### Ce qui est en place (les 2 skins)

- **`<link rel="canonical">`** — URL absolue, surchargeable via `{% block canonical %}`
- **JSON-LD Organization + WebSite** — via partial `seo/partials/json_ld_organization.html`
- **JSON-LD Event** — sur `event/retrieve.html` (schema.org Event complet)
- **Open Graph** (og:title, og:description, og:image, og:url) — surchargeable par page
- **Twitter Card** (summary_large_image) — surchargeable par page
- **Sitemap** `/sitemap.xml` — Events + Products + pages statiques
- **robots.txt** `/robots.txt` — Allow all + lien sitemap
- **`<main>` semantique** — un seul dans chaque base.html

### og:image / twitter:image

Les URLs doivent etre **absolues** (les crawlers sociaux ne resolvent pas les chemins relatifs).
Le template utilise `https://{{ request.get_host }}{{ config.get_social_card }}` pour prefixer.
`config.get_social_card` retourne un chemin relatif (`/media/images/xxx.social_card.webp`).

### Convention pour les meta descriptions

Chaque page doit surcharger `{% block meta_description %}` avec un texte **unique** de 150-160 caracteres.
Si le block n'est pas surcharge, le defaut est `config.short_description` (identique sur toutes les pages = penalise par Google).

```html
{% block meta_description %}{% translate "Description unique pour cette page, 150-160 caracteres." %}{% endblock %}
```

Meme chose pour `{% block og_title %}`, `{% block og_description %}`, `{% block twitter_title %}`, `{% block twitter_description %}`.

### Convention pour les headings

- **Un seul `<h1>` par page** — si le titre visuel est une image, utiliser `<h1 class="visually-hidden">Titre</h1>`
- **Hierarchie stricte** : H1 → H2 → H3 (pas de niveaux sautes)
- **Les templates enfants ne declarent PAS de `<main>`** — le base.html le fournit

### Convention pour les images

- Format **WebP** prefere pour les photos (compression 80-90% vs PNG)
- Les illustrations flat/vectorielles peuvent rester en PNG (WebP parfois plus lourd)
- Toujours un attribut `alt` descriptif
- Utiliser `loading="lazy"` sur les images en dessous de la ligne de flottaison

## Blocs surchageables dans les base templates

| Bloc | Defaut | Usage |
|---|---|---|
| `{% block title %}` | "Home" | Titre de l'onglet (+ "| config.organisation" auto) |
| `{% block meta_description %}` | config.short_description | Description Google |
| `{% block meta_robots %}` | "index, follow" | Directives robots |
| `{% block og_type %}` | "website" | Type Open Graph |
| `{% block og_title %}` | "Home | config.organisation" | Titre partage social |
| `{% block og_description %}` | config.short_description | Description partage social |
| `{% block og_image %}` | config.get_social_card (absolu) | Image partage social |
| `{% block og_image_alt %}` | config.organisation | Alt de l'image OG |
| `{% block twitter_title %}` | idem og_title | Titre Twitter |
| `{% block twitter_description %}` | idem og_description | Description Twitter |
| `{% block twitter_image %}` | idem og_image | Image Twitter |
| `{% block canonical %}` | request.build_absolute_uri | URL canonique |
| `{% block json_ld_org %}` | partial Organization + WebSite | JSON-LD |
| `{% block extra_meta %}` | vide | Meta tags supplementaires |

## Pages avec meta descriptions uniques (skin faire_festival)

| Page | Titre | Description |
|---|---|---|
| `/` | Accueil | "Festival de fabrication partagee : ateliers, conferences, rencontres..." |
| `/le-faire-festival/` | Le Faire Festival | "Decouvrez le Faire Festival : le plus grand festival de fabrication en France..." |
| `/infos-pratiques/` | Infos pratiques | "Acces, horaires, plan et informations pratiques..." |
| `/event/<slug>/` | Nom de l'evenement | Description de l'evenement (deja en place) |

## Pages sans meta description unique (a faire)

- `/event/` (liste des evenements) — skin reunion ET faire_festival
- `/memberships/` (liste des adhesions) — skin reunion ET faire_festival
- Toutes les pages du skin `reunion` sauf `event/retrieve`

## Pieges SEO documentes

### Locale francaise et DecimalField dans le JS

Django rend `43,5769` (virgule) au lieu de `43.5769` (point) en locale francaise.
Utiliser `{% localize off %}...{% endlocalize %}` pour les nombres injectes dans du JavaScript.
Voir `tests/PIEGES.md` piege 71.

### og:image relatif

`config.get_social_card` retourne un chemin relatif. Toujours prefixer avec
`https://{{ request.get_host }}` dans les templates. Les crawlers sociaux ne resolvent
pas les chemins relatifs.

### `<main>` en double

Les templates enfants ne doivent PAS declarer `<main>` — le base.html le fournit.
Utiliser `<div>` dans les `{% block main %}`.

## Outils de verification

```bash
# Verifier les meta tags d'une page
docker exec lespass_django curl -s -H "Host: lespass.tibillet.localhost" \
  http://localhost:8002/ | grep -E '<title>|<meta name="description"|<link rel="canonical"|<h1|og:title|og:description|og:image|application/ld'

# Valider le JSON-LD
docker exec lespass_django curl -s -H "Host: lespass.tibillet.localhost" \
  http://localhost:8002/ | grep -A 30 'application/ld+json' | \
  python3 -c "import sys,json; data=sys.stdin.read(); start=data.index('{'); end=data.rindex('}')+1; json.loads(data[start:end]); print('JSON-LD valide')"

# Verifier le sitemap
docker exec lespass_django curl -s -H "Host: lespass.tibillet.localhost" \
  http://localhost:8002/sitemap.xml | head -20

# Verifier robots.txt
docker exec lespass_django curl -s -H "Host: lespass.tibillet.localhost" \
  http://localhost:8002/robots.txt
```

## Historique

- **2026-04-10** : Mise en place initiale SEO (canonical, JSON-LD, meta descriptions, headings, og:image absolu) sur les 2 skins. Voir `CHANGELOG.md`.
