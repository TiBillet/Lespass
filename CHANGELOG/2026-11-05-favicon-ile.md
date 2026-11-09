# Nouveau favicon « île » / New "island" favicon

**Date :** 2026-11-05
**Migration :** Non

## Resume / Summary
**Quoi / What :** le favicon devient l'île seule (palmier et montagne du logo « île »), sur fond
transparent, remplie du dégradé de marque « Soleil » (jaune en bas, rose en haut). Le même favicon
sert partout : sites des lieux, tibillet.coop, LaBoutik et admin. Le cadre coupe la pointe gauche de la
plage pour grossir l'île. Le logo complet (île + ticket « tiB »), noir uni, sert pour
la barre de navigation de tibillet.coop et la pastille en haut du rail de l'admin (blanc en thème
sombre), ainsi que pour l'`apple-touch-icon`. Les
icônes de l'application Android reprennent `logo_ile_color.png` du kit graphique, avec des coins
arrondis.
/ The favicon becomes the island alone, on a transparent background, filled with the "Soleil"
brand gradient. The same favicon is used everywhere: venue sites, tibillet.coop, LaBoutik and
admin. The plain black full logo is used for the tibillet.coop navbar, the admin rail tile (white
in dark theme) and the apple-touch-icon. Android app icons use the kit's
`logo_ile_color.png`, with rounded corners.

**Pourquoi / Why :** changement d'identité visuelle. L'ancien favicon des lieux était un PNG de
36×36 px, et la caisse affichait encore l'ancien logo rond « TB ».
/ Visual identity change. The venues' old favicon was a 36×36 PNG, and the POS still showed the
old round "TB" logo.

Le SVG est vectorisé (potrace) depuis `8.Graphisme/kit/logos/png/logo_ile_fondblanc.png` : le
SVG `monochrome.svg` du kit n'a pas le même dessin (montagne, bord du ticket).
/ The SVG is traced from the kit PNG: the kit's `monochrome.svg` has a different drawing.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/static/commun/img/favicon.svg` | Nouveau : île seule, dégradé « Soleil » (`radialGradient` qui reprend le CSS de la marque), fond transparent |
| `BaseBillet/static/commun/img/logo-ile-noir.svg`, `logo-ile-blanc.svg` | Nouveaux : logo complet en couleur fixe, pour la nav de tibillet.coop et la pastille de l'admin, qui ont leur propre thème |
| `BaseBillet/static/commun/img/favicon.png` | Île seule « Soleil », fond transparent, 192×192 (avant : 36×36) |
| `BaseBillet/static/commun/img/apple-touch-icon.png` | Nouveau : logo complet, 180×180, fond blanc opaque (iOS remplace la transparence par du noir) |
| `seo/static/seo/favicon.svg` | Même SVG que `commun/img/favicon.svg` |
| `seo/static/seo/favicon-192.png`, `seo/static/seo/apple-touch-icon.png` | Mêmes fichiers que leurs équivalents `commun/img/` (apple-touch passe de 96 à 180 px) |
| `laboutik/static/images/favicon.ico` | Île seule « Soleil », 16/32/48 px (remplace le logo rond « TB ») |
| `laboutik_client_pi_desktop_v2/www/favicon.ico`, `laboutik_client_android_v2/mobile-app/www/favicon.ico` | Même `.ico` |
| `laboutik_client_android_v2/mobile-app/res/android/*.png` | Icônes d'application ldpi→xxxhdpi (36 à 192 px), réduites depuis `kit/logos/png/logo_ile_color.png` (200 px), coins arrondis (rayon 18 %, coins transparents). Le splash (`splash-square.png`) affiche déjà `couleur.svg` du kit : inchangé |
| `pages/templates/pages/{classic,V2,faire_festival}/shell.html`, `BaseBillet/templates/fonctionnel/blank_base.html` | Balises SVG + PNG 192 + apple-touch-icon |
| `laboutik/templates/laboutik/base.html`, `laboutik/templates/laboutik/views/telecharger_application.html` | Balise SVG ajoutée avant le `.ico` |
| `seo/templates/seo/base.html` | Logo de la nav : `commun/img/logo-ile-noir.svg` |
| `seo/static/seo/seo.css` | `[data-bs-theme="dark"] .navbar-brand-logo { filter: invert(1); }` : le logo devient blanc en thème sombre |
| `TiBillet/settings.py` | `UNFOLD["SITE_ICON"]` (noir/blanc selon le thème de l'admin) remplace `SITE_SYMBOL` ; `UNFOLD["SITE_FAVICONS"]` pose le même `favicon.svg` dans l'onglet de l'admin |
| Supprimés / Deleted | `laboutik/static/images/favicon2.ico`, `BaseBillet/static/mvt_htmx/images/favicon.png`, `seo/static/assets/favicon.svg` (aucune référence) |

---

## Comment tester (a la main) / Manual test

### Test 1 — onglet d'un lieu
1. Ouvrir `https://lespass.tibillet.localhost/` (vider le cache : le favicon est très collant).
2. L'onglet affiche l'île seule, en dégradé « Soleil » (jaune en bas, rose en haut). Elle reste visible avec le navigateur en thème clair
   comme en thème sombre.

### Test 2 — site tibillet.coop (schéma public)
1. Ouvrir la page d'accueil du schéma public.
2. L'onglet affiche l'île « Soleil » (comme au test 1).
3. Le logo complet de la nav est noir uni. Basculer le site en thème sombre : il devient blanc.

### Test 3 — admin
1. Ouvrir `/admin/`. L'onglet affiche l'île en dégradé « Soleil », comme sur le front.
2. La pastille en haut à gauche du rail affiche le logo complet noir, à la place de l'icône ticket.

### Test 4 — caisse
1. Ouvrir LaBoutik. L'onglet affiche l'île « Soleil » (plus le logo rond « TB »).

### Test 5 — kiosque, tireuse, fedow_public
1. Ces pages n'ont pas de balise favicon : le navigateur demande `/favicon.ico`, redirigé vers
   `commun/img/favicon.png`. L'onglet affiche l'île « Soleil ».

### Test 6 — applications natives
1. Android : l'icône (île grise, ticket « tiB » en couleur, fond gris clair, coins arrondis) n'apparaît qu'après
   une recompilation de l'APK.
2. Client Pi : le `.ico` est servi par son serveur local, à vérifier après mise à jour du client.

### Verifs
- `curl -skI https://lespass.tibillet.localhost/static/commun/img/favicon.svg` → `200 image/svg+xml`.
- En prod : `collectstatic` nécessaire pour les nouveaux fichiers (`favicon.svg`, `logo-ile-noir.svg`,
  `logo-ile-blanc.svg`, `apple-touch-icon.png`).
