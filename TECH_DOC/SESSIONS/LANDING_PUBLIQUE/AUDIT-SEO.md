# Audit SEO — Site public TiBillet (schéma public)

**Date :** 2026-07-17
**Périmètre :** landing `/`, hub `/features/`, pages détail `/features/<slug>/`, `/explorer/`, `/recherche/`, `robots.txt`, `sitemap.xml`, `sitemap-root.xml`.
**Servi par :** app `seo` (`seo/views.py`, `seo/base.html`, `seo/features.py`), schéma `public` de django-tenants.

Cet audit lit le code rendu côté serveur (templates + vues + JSON-LD). Il ne
remplace pas un crawl Lighthouse/Search Console en production, mais il repère les
causes racines dans le code, là où elles se corrigent.

---

## 1. Ce qui est déjà solide (à préserver)

Le site public part de loin devant la moyenne. À ne PAS casser pendant le redesign :

| Brique | État |
|---|---|
| **JSON-LD** | Riche et correct : `WebSite`+`SearchAction` (searchbox SERP), `Organization`, `ItemList` (features → sitelinks), `BreadcrumbList` (objet `@id`, forme recommandée Google), `TechArticle` (pages détail), `Organization`+`subOrganization` (fédération, lisible par LLMs). |
| **Canonical** | Présent sur chaque page (`canonical_url`). |
| **Open Graph / Twitter** | Complets : `og:type/url/title/description/site_name/image` + dimensions + `og:locale` mappé FR/EN, `twitter:card summary_large_image`. |
| **robots.txt** | Dynamique, garde `noindex` (flags env DEBUG/TEST/DEMO/STRIPE_TEST → `Disallow: /`), sinon `Allow: /` + réf sitemap. |
| **Sitemaps** | Index cross-tenant + `sitemap-root.xml` (landing, hub, chaque feature). |
| **HTML sémantique** | `<main>`, `<nav aria-label>`, `<header>`, `<section>`, fil d'Ariane avec `aria-current="page"`. |
| **Pages détail features** | Vraies pages indexables (rendu serveur complet), `lead` riche, 3 sections, maillage interne (autres features), `figcaption` portant la vraie description (a11y + SEO). |
| **Titres & metas par feature** | `page_title` (~50-60 car.) + `meta_description` (< 160 car.) rédigés, orientés mots-clés. |
| **Détails** | `text-wrap: balance` sur les titres, `alt=""` discipliné sur les décoratifs, `humans.txt`. |

---

## 2. Trous SEO à corriger (par priorité)

### 🔴 A. `hreflang` totalement absent — le plus gros trou d'un site bilingue

Le site est **bilingue FR/EN** (sélecteur `set_language`, `og:locale` mappé), mais
**aucune** balise `<link rel="alternate" hreflang="fr">` / `hreflang="en">` /
`hreflang="x-default">`. Résultat : Google ignore qu'il existe deux versions
linguistiques et peut servir la mauvaise langue en SERP, ou traiter FR et EN comme
du contenu dupliqué.

**Complication d'architecture (à acter) :** le projet n'utilise **pas**
`i18n_patterns` — la langue passe par cookie/session, l'URL est **identique** en
FR et EN (`/features/billetterie/` sert les deux selon le cookie). Le `hreflang`
classique exige des URLs distinctes par langue (`/fr/...` et `/en/...`).

**Options (décision produit) :**
1. **Accepter l'état actuel** et déclarer la page comme mono-URL multilingue via
   `og:locale` seul (imparfait mais honnête). Faible effort.
2. **Introduire des URLs par langue** (`i18n_patterns` ou paramètre) pour poser un
   vrai `hreflang`. Effort important, touche tout le routage public.

→ **Recommandation :** trancher explicitement. À court terme option 1 + documenter
la limite ; à moyen terme évaluer l'option 2 si l'EN devient un canal réel.

### 🔴 B. `/explorer/` est `noindex` MAIS listé dans `sitemap-root.xml`

`seo/views.py::sitemap_root_view` liste `/explorer/`, alors que la page est
volontairement `noindex` (outil interactif). Google déconseille formellement de
mettre des URLs `noindex` dans un sitemap (signal contradictoire : « indexe-moi » /
« n'indexe pas »).

→ **Fix simple :** retirer `/explorer/` de `sitemap_root_view`. (Le JSON-LD
fédération reste, lui, utile pour les LLMs.)

### 🟠 C. `font-display` manquant sur les polices du LCP

Dans `commun/css/tibillet.css`, les `@font-face` de **`luciole`** (police du corps
= texte LCP) et **`staatliches`** n'ont **pas** `font-display`. Défaut navigateur =
`auto` ≈ FOIT : le texte reste invisible pendant le chargement de la police →
**LCP dégradé**. Seul `Playwrite IS` a `font-display: swap`.

→ **Fix :** ajouter `font-display: swap;` aux blocs `luciole` et `staatliches`.
(Fichier partagé pré-existant : édition ciblée d'une ligne par bloc, pas de reformat.)

### 🟠 D. LCP hero non priorisé

Le logo hero (`tibillet-logo-couleur.svg`, 320px) est le LCP probable sur desktop ;
sur mobile il est masqué (`display:none`) et le LCP devient le H1. Le logo n'a ni
`<link rel="preload">` ni `fetchpriority="high"`.

→ **Fix :** `fetchpriority="high"` + `width`/`height` explicites sur l'`<img>` du
logo (évite le CLS et accélère le LCP desktop).

### 🟠 E. JS bloquant dans le `<head>`

`base.html` charge `bootstrap.bundle.min.js` dans le `<head>` **sans `defer`**. Il
bloque le parsing HTML. (Contrairement à htmx qui doit rester bloquant, Bootstrap
peut être `defer`.)

→ **Fix :** `defer` sur `bootstrap.bundle`. Vérifier que rien n'en dépend au parse.

### 🟡 F. Cohérence `<title>` ↔ `H1` sur la landing

- `<title>` landing = « TiBillet — Billetterie coopérative et lieux culturels »
- `H1` landing = « Adhésion, billetterie, caisse enregistreuse et outils libres et fédérés »

Les deux sont bons séparément mais ne se renforcent pas. Idéalement le H1 reprend
les mots-clés forts du title (ou l'inverse) pour un signal cohérent.

→ **Fix :** aligner le vocabulaire (garder « billetterie coopérative », « lieux
culturels », « libre »/« fédéré » dans les deux).

### 🟡 G. H1 du hub `/features/` trop pauvre

`H1 = « Fonctionnalités »` (un mot, zéro mot-clé). Une page hub mérite un H1
descriptif : « Fonctionnalités de billetterie coopérative et de gestion de lieux
culturels ». Le `page_title` est déjà correct ; c'est le H1 visible qui est faible.

### 🟡 H. Contenu dupliqué partiel landing ↔ hub

La grille de features (`_features_grid.html`) est **identique** sur `/` et
`/features/`. Canonicals distincts (ok), mais deux pages avec le même bloc central.
Peu grave, mais le redesign peut différencier : landing = présentation riche
(taglines/leads), hub = liste dense orientée navigation.

### 🟡 I. Opportunité `SoftwareApplication` sur la landing

La landing présente un **logiciel** mais n'émet pas de JSON-LD
`SoftwareApplication` en entité principale (seulement `WebSite` + `Organization`).
Un bloc `SoftwareApplication` (`applicationCategory: BusinessApplication`,
`offers` = gratuit/libre AGPLv3, `operatingSystem: Web`) peut débloquer des
résultats enrichis. Les pages détail le référencent déjà en `about`.

### 🟡 J. Opportunité `FAQPage`

Aucune FAQ. Une section FAQ (« TiBillet prélève-t-il une commission ? », « Puis-je
récupérer mes données ? », « Est-ce vraiment gratuit ? », « Puis-je l'héberger
moi-même ? ») + JSON-LD `FAQPage` sert **deux** objectifs à la fois : rich results
SERP **et** « tout bien expliquer » (objectif produit). Contenu déjà disponible
dans `features.py` (AGPLv3, sans frais cachés, données ouvertes).

### 🟢 K. Points mineurs / à vérifier en prod

- **Dimensions `og:image`** déclarées 1200×675 : vérifier que `social-card.png`
  les respecte réellement (sinon l'aperçu social est rogné).
- **Marquee** : liens tenants dupliqués (`{% for copy in "ab" %}`), 2ᵉ copie en
  `aria-hidden` — acceptable (même `href`), pas de fix nécessaire.
- **`width`/`height`** absents des `<img>` marquee/events (CLS léger ; events déjà
  protégés par `aspect-ratio` sur le wrapper, logos non).
- **`/recherche/`** : page de résultats, canonical vers `/recherche/` sans le `q`.
  Envisager `noindex` explicite sur les résultats (évite l'indexation de pages
  query infinies).

---

## 3. Synthèse — plan d'action SEO

| # | Action | Effort | Gain | Statut |
|---|---|---|---|---|
| B | Retirer `/explorer/` du sitemap-root | XS | Cohérence crawl | À faire |
| C | `font-display: swap` (luciole, staatliches) | XS | LCP | À faire |
| D | `fetchpriority` + dims sur logo hero | XS | LCP/CLS | À faire |
| E | `defer` sur bootstrap.bundle | XS | Parse/FCP | À faire |
| F | Aligner title ↔ H1 landing | S | Pertinence | Via redesign |
| G | H1 hub descriptif | XS | Mots-clés | Via redesign |
| I | JSON-LD `SoftwareApplication` landing | S | Rich results | À faire |
| J | Section FAQ + `FAQPage` JSON-LD | M | Rich results + explicabilité | À faire |
| A | Décision `hreflang` (architecture) | — | Multilingue | **Décision produit requise** |
| H | Différencier landing vs hub | M | Anti-duplication | Via redesign |

Les items **F, G, H** se règlent naturellement pendant le redesign. **B, C, D, E**
sont des correctifs XS indépendants. **I, J** sont des ajouts de contenu/balisage.
**A** demande une décision produit (ne pas coder à l'aveugle).
