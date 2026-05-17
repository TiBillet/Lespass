# SPEC SEO Lespass — Vision globale

## 1. Pourquoi ce dossier

Lespass est une plateforme de billetterie multi-tenant. Chaque tenant
est un lieu (filaos.re, ciboulette, raffinerie...) qui veut etre
trouve sur Google et apparaitre dans les reponses des LLMs (ChatGPT,
Claude, Perplexity, Gemini, Google AI Overview).

L'app `seo/` (deja en place) sert la landing ROOT (tibillet.coop) et
agrege les lieux + evenements via un cache cross-schema. Mais le SEO
des **pages tenant** reste largement insuffisant, et les instances de
dev (filaos.re, devtib.fr) sont indexees alors qu'elles ne devraient
pas l'etre.

Ce dossier suit le chantier SEO sur plusieurs sessions. Il est aligne
sur le **Google AI Optimization Guide** publie le 15 mai 2026.

## 2. Principes — ce que Google a dit le 15 mai 2026

Source : https://developers.google.com/search/docs/fundamentals/ai-optimization-guide

> "SEO for AI is just SEO."

Points cles :

- **AI Overviews et AI Mode** utilisent le **meme index Search** que
  les resultats classiques, avec le **meme classement**. Pas de
  pipeline IA separe.
- Section officielle "Mythbusting" : pas besoin de `llms.txt`, pas de
  schema "AI-specific", pas de chunking, pas de reecriture pour LLMs.
- Recette : contenu **non-commodity** (du vecu, du contenu unique,
  pas du rehash), fondamentaux SEO classiques (crawlabilite, semantic
  HTML, page experience, mobile), pas de scaled content abuse.

Ce qui se traduit dans Lespass par :

- **Garder** les bonnes pratiques deja en place dans `seo/` (sitemap,
  robots.txt, OG, Twitter Card, JSON-LD Organization / WebSite /
  ItemList / Federation, canonical, accessibilite).
- **Ne pas** investir dans des hacks GEO/AEO inutiles.
- **Investir** dans : la propagation de ces signaux aux **pages
  tenants** (chantier 02), la creation de pages indexables pour les
  **sitelinks Google** (chantier 03), et la **desindexation** des
  instances non-prod (chantier 01).

## 3. Etat actuel

### Landing ROOT (`seo/`) — solide

- Sitemap cross-tenant, robots.txt dynamique, canonical, OG, Twitter
  Card, 3 JSON-LD (Organization, WebSite+SearchAction, ItemList ou
  Federation).
- Cache L1 Memcached + L2 DB (SEOCache), refresh Celery toutes les 4h.
- Accessibilite (ARIA, heading hierarchy), i18n locale, semantic HTML.

### Pages tenant (`BaseBillet/templates/htmx/base.html`) — pauvre

Comparaison avec `seo/base.html` :

| Element | ROOT | TENANT |
|---|---|---|
| `<title>` unique par page | Oui | Non (toujours `{org} | TiBillet`) |
| `<meta description>` | Oui | Non |
| Open Graph | Oui complet | Non |
| Twitter Card | Oui | Non |
| `<link rel="canonical">` | Oui | Non |
| JSON-LD | Oui (Org+WebSite+List) | Non |
| `<meta name="robots">` | Oui | Non |

Consequence : un event filaos.re est servi avec un `<head>` quasi
vide. Faible richesse SERP, zero chance de sitelinks, et les bots IA
n'identifient pas le contenu comme un Event schema.org.

### `robots.txt`

Deux vues identiques :
- `seo/views_common.py:robots_txt` (ROOT public)
- `BaseBillet/views_robots.py:robots_txt` (tenant)

Les deux servent **toujours** `User-agent: * / Allow: /` sans
condition. Resultat : devtib.fr et filaos.re sont publiquement
indexables alors que ce sont des instances de dev/demo.

### Variables d'environnement disponibles

Dans `.env` :
- `DEBUG=1` — mode debug Django
- `TEST=1` — flag de test
- `DEMO=1` — flag demo
- `STRIPE_TEST=1` — Stripe en mode test
- `DOMAIN='tibillet.localhost'` — domaine principal (wildcard
  sans sous-domaine). En prod : `tibillet.coop`.
- `DOMAIN_REGEX='^.+\.tibillet\.localhost$$'` — regex Traefik.
- `ADDITIONAL_DOMAINS='domainbis.localhost'` — domaines additionnels
  comma-separated (lus dans `settings.py:90-91`).

## 4. Chantiers (vue d'ensemble)

### 01 — Desindexer DEV / DEMO / TEST — **en cours**

Voir [CHANTIER-01-noindex-dev.md](./CHANTIER-01-noindex-dev.md).

Regle metier : une reponse HTTP est `noindex` si **au moins un flag
d'environnement** est a `1` :

- `DEBUG=1`
- `TEST=1`
- `DEMO=1`
- `STRIPE_TEST=1`

(Une regle supplementaire sur le host a ete envisagee puis ecartee
le 2026-05-17 : redondante en pratique avec les 4 flags + Django
bloque deja les hosts inconnus via `ALLOWED_HOSTS`.)

### 02 — Enrichir le base template tenant — **a faire**

Faire passer `BaseBillet/templates/htmx/base.html` au meme niveau que
`seo/base.html` : meta description, OG, Twitter Card, canonical,
JSON-LD `Organization` (Local Business + PostalAddress + geo si
disponible), `<meta name="robots">` conditionnel sur le helper du
chantier 01.

Puis pour chaque page (event, lieu, agenda) : JSON-LD `Event` /
`Place` avec startDate, endDate, location, offers, image.

### 03 — Pages indexables ROOT pour sitelinks Google — **a faire**

Creer 5 a 8 pages dediees indexables : `/fonctionnalites/`, sous-pages
par feature, `/cooperative/`, `/demonstration/`, `/contact/`. Chaque
page = H1 unique + meta unique + 500-1000 mots de contenu
non-commodity (du vecu coop, des cas concrets : filaos, Raffinerie,
chiffres reels).

But : permettre a Google de remonter des sitelinks (Demonstration,
Presentation, Application Android...) comme sur tibillet.org/docs.

### 04 — Breadcrumbs + sameAs Organization — **a faire**

Petits gains : utiliser le builder `build_json_ld_breadcrumb` (deja
present dans `seo/views_common.py:210`, actuellement inutilise) sur
les pages `/lieux/`, `/evenements/`, `/recherche/`. Ajouter `sameAs`
(LinkedIn, Mastodon, GitHub) au JSON-LD Organization de la ROOT.

## 5. Ce qu'on ne fera pas (anti-patterns)

Liste explicite pour eviter de reouvrir le debat plus tard :

- **Pas de `llms.txt`** (cf. Atom Atomic
  `491b2fe3-049c-4b2d-86bf-ae2fc41b6b31`).
- **Pas de schema "AI-specific"** (ca n'existe pas).
- **Pas de generation de pages quasi-identiques** par tenant /
  ville / niche (= scaled content abuse, penalite).
- **Pas de `meta keywords`** (deprecated depuis 2009).
- **Pas de AMP** (deprecated par Google 2021, focus Core Web Vitals).
- **Pas de middleware** pour ajouter `X-Robots-Tag` HTTP partout
  (le `<meta robots>` HTML suffit pour les pages indexables, et le
  `robots.txt` couvre le reste — cf. design du chantier 01).
