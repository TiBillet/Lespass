# Audit SEO du moteur de pages — skins `classic` et `faire_festival`

Date : 2026-07-20
Périmètre : app `pages/`, ses deux skins, sur les 3 tenants de démonstration
(`lespass`, `festival`, `la-maison-des-communs`), 43 pages publiées, les 19
gabarits de blocs et les 20 combinaisons (type, affichage) du catalogue.

Méthode : lecture du code + rendu HTTP réel (`curl`) sur chaque page, mesure
octet par octet des assets servis. Les constats ci-dessous portent tous une
preuve : sortie de commande ou `fichier:ligne`.

Rappel de contexte : le serveur de dev force `noindex, nofollow` sur tout
(`TiBillet/seo_indexing.py`, flags `DEBUG/TEST/DEMO/STRIPE_TEST`). C'est voulu.
Tous les constats ci-dessous décrivent donc le comportement qu'aurait le site
une fois ces flags à `0` en production.

---

## 1. Bloquant

### B1 — Deux `<main>` imbriqués sur tout le skin `classic`

`pages/templates/pages/classic/shell.html:171` ouvre un `<main>`, et
`pages/templates/pages/classic/page.html:57` en ouvre un second à l'intérieur.
Vérifié sur le rendu : `curl -sk https://lespass.tibillet.localhost/ | grep -c "<main"` → **2**.

HTML5 interdit plus d'un `<main>` par document et interdit l'imbrication. Un
lecteur d'écran annonce deux zones « contenu principal ». Le skin
`faire_festival` n'a pas ce défaut (un seul `<main>`, `shell.html:227`).

**Correction** : dans `classic/page.html:57`, remplacer le second `<main>` par
un `<div>`. La grille CSS `.tb-page.tb-flux` continue de fonctionner à
l'identique — c'est la classe qui porte la mise en page, pas la balise.

### B2 — `og:title` et `twitter:title` ignorent `meta_title` (les deux skins)

`classic/page.html:22` et `faire_festival/page.html:17` :
`{% block og_title %}{{ page_courante.titre }} | ...{% endblock %}`.

Le `<title>` utilise pourtant bien `meta_title|default:titre`. Résultat sur
l'accueil `lespass`, où `meta_title` est renseigné :

```
<title>Lespass — concerts, ateliers et adhésion coopérative | Lespass</title>
<meta property="og:title" content="Accueil | Lespass">
```

Toute carte de partage social affiche « Accueil » au lieu du titre travaillé.

**Correction** : `{{ page_courante.meta_title|default:page_courante.titre }}`
dans les blocs `og_title` et `twitter_title` des deux skins.

### B3 — Skin `classic` : `twitter:title` / `twitter:description` jamais surchargés

`classic/page.html` définit `og_title`, `og_description`, `og_image`,
`twitter_image` — mais **pas** `twitter_title` ni `twitter_description`. Ces
deux balises restent donc figées à la valeur par défaut du site sur *toutes*
les pages du tenant :

```
<meta name="twitter:title" content="Accueil | La Maison des Communs">
<meta name="twitter:description" content="Lieu de démo: atelier partagé et entraide.">
```

… identique sur `/blog/`, `/formations/`, `/codensamb-preambule/`, `/tibillet/`.
Le skin `faire_festival` définit bien ces deux blocs (`page.html:20-21`) : c'est
une divergence entre skins, pas un choix.

**Correction** : ajouter les deux blocs manquants dans `classic/page.html`, en
miroir de `faire_festival`.

### B4 — Collision de slugs : les `re_path` de routage ne sont pas ancrés

`TiBillet/urls_tenants.py` déclare `re_path(r'api/', ...)`, `r'rss/'`,
`r'fedow/'`, `r'crowd/'`, `r'contrib/'`, `r'newsletter/'`, `r'fwh/'`,
`r'logout/'` — **sans `^`**. Django applique ces motifs avec `.search()`, donc
ils matchent n'importe où dans le chemin.

Tests réels (aucune page de ce nom n'existe : la collision est au niveau du
routage, indépendante du contenu) :

```
documentation-api/  -> 403      test-crowd/    -> 200 (sert /crowd/)
notre-api/          -> 403      notre-crowd/   -> 200 (sert /crowd/)
guide-newsletter/   -> 403      test-contrib/  -> 200 (sert /crowd/)
mon-fwh/            -> 403      test-fedow/    -> 403
test-normal-slug/   -> 404      (comportement attendu)
```

`pages/models.py:42-54` (`SLUGS_RESERVES`) ne protège que les slugs **exacts**,
et la liste ne contient ni `rss`, ni `fedow`, ni `crowd`, ni `contrib`, ni
`newsletter`, ni `fwh`, ni `logout`. Un gestionnaire peut donc créer sans le
moindre avertissement une page `guide-newsletter` — définitivement
inatteignable.

C'est l'élargissement d'un piège déjà connu du projet
(`piege_slug_403_route_non_ancree`).

**Correction, en deux temps** :
1. Ancrer les `re_path` avec `^` dans `urls_tenants.py` — corrige la cause.
2. Étendre `SLUGS_RESERVES` et faire rejeter aussi les slugs qui *se terminent*
   par un mot réservé — défense en profondeur.

**Note d'arbitrage** : le point 1 touche le routage global du projet, hors de
l'app `pages/`. À valider par le mainteneur avant application : un `^` mal placé
casse une route de production. Le point 2 est sans risque et suffit à protéger
l'utilisateur du moteur de pages.

### B5 — Images : aucun `srcset`, un mobile télécharge du 1920 px

`grep -rn "srcset" pages/templates/` → **0 résultat**. Chaque gabarit sert une
variation fixe :

| Gabarit | Variation servie |
|---|---|
| `bloc_section_banniere` (classic, fond CSS) | `.fhd` (1920 px) |
| `bloc_images_pleine_largeur`, `bloc_images_vignette_titre` | `.fhd` (1920 px) |
| `_section_texte_image`, `bloc_section_media_et_cartes` | `.hdr` (1280 px) |
| `bloc_section_carte`, `bloc_images_grille`, `bloc_images_bande_logos` | `.med` (480 px) |

Poids mesuré (`curl -skI`, Content-Length) sur l'accueil `lespass` :
**27 images = 2 280 741 o (2,23 Mo)**, soit ~68 % des 3,35 Mo de la page.
Pièces les plus lourdes : `404-6.fhd.jpg` 323 785 o, `404-9.hdr.jpg` 314 322 o,
et un simple logo partenaire `Demeter.med.png` à **230 066 o** pour 480 px.

Même ordre de grandeur sur `festival` (1,08 Mo) et `la-maison-des-communs` (1,41 Mo).

**Correction** : ajouter une variation mobile (~640-750 px) à
`VARIATIONS_IMAGE` (`pages/models.py:590`), passer les gabarits en
`srcset`/`sizes`, et ajouter une option `quality` aux variations stdimage.

---

### B6 — La page d'accueil est servie à deux adresses, chacune se déclarant canonique

`est_accueil` fait servir la page sur `/`, mais la route attrape-tout
`/<slug>/` la sert **aussi** : `/accueil/` répondait 200 sur les 3 tenants,
avec un canonical auto-référent `https://…/accueil/`. Deux URLs indexables pour
le même contenu, chacune se proclamant l'originale.

### B7 — Le canonical recopiait la query string

`shell.html:44` : `{{ request.build_absolute_uri }}`. Vérifié :
`/?utm_source=test&foo=bar` produisait
`<link rel="canonical" href="https://…/?utm_source=test&amp;foo=bar">`. La
balise ne dédupliquait donc rien : chaque lien tracké créait sa propre page
« canonique ».

**Correction (B6 + B7, appliquée)** : le canonical est désormais construit
depuis `Page.get_absolute_url()`, la source unique de l'adresse d'une page.
Comme cette méthode retourne `/` pour la page d'accueil, les deux problèmes se
règlent d'un coup : `/accueil/` et `/?utm_source=…` pointent tous deux vers
`https://…/`.

> Ces deux constats viennent de la relecture. Les quatre agents d'audit avaient
> tous certifié le canonical « correct » — c'est précisément là que se
> cachaient les seuls vrais doublons du site.

### B8 — Site bilingue, mais une seule URL et aucun `hreflang`

Le site sert le français et l'anglais sur **les mêmes URLs**, par négociation
de contenu :

```
curl -H "Accept-Language: en" https://lespass…/  →  <html lang="en">
curl                          https://lespass…/  →  <html lang="fr">
```

Aucun `hreflang` dans le rendu (`grep -c hreflang` → 0), aucune URL par langue.
Or Googlebot crawle essentiellement sans `Accept-Language` : **la version
anglaise du site n'existe pas pour les moteurs de recherche**. Le
`Vary: Accept-Language` est bien posé, mais Google ne s'en sert pas pour
indexer deux variantes.

**Non corrigé — décision produit.** Rendre l'anglais indexable suppose des URLs
distinctes par langue (`/en/…` via `i18n_patterns`, ou un sous-domaine), plus
les `hreflang` réciproques. C'est un chantier d'architecture d'URLs, pas un
correctif de gabarit : à arbitrer avant d'être implémenté.

---

## 2. Majeur

### M1 — `bloc_lieu` produit des `<h3>` orphelins

Sur `/infos-pratiques/` (festival) : `<h1>Infos pratiques</h1>` suivi
directement de `<h3>VOITURE</h3>`, `<h3>BUS</h3>`, `<h3>TRAIN</h3>`.

`faire_festival/partials/bloc_lieu.html:43` rend un `<h3>` par item de
transport mais n'affiche jamais le titre du bloc. Côté `classic`
(`bloc_lieu.html:69`), le `<h2>` du bloc n'est rendu que dans la colonne carte,
sous `{% if bloc.points_gps %}` : un bloc lieu sans GPS perd son `<h2>` et
laisse ses `<h3>` sans parent.

**Correction** : rendre le `<h2>{{ bloc.titre }}</h2>` inconditionnellement en
tête du bloc, dans les deux skins.

### M2 — `bloc_liste` masque son `<h2>` → saut h1 → h3 sur les pages-index

`classic/partials/bloc_liste.html:20-27` :
`{% if bloc.titre and bloc.titre != page_courante.titre %}`. Le garde-fou
évite un doublon visuel « Blog / Blog », mais supprime le `<h2>` du plan. Sur
`/blog/` : `<h1>Blog</h1>` puis directement `<h3>Lettre ouverte…</h3>`.

**Correction** : garder le `<h2>` dans le DOM et le masquer visuellement
(`class="visually-hidden"`) plutôt que de le retirer.

### M3 — `alt` vide sur des images de contenu

Pas de champ `alt` dédié sur `Bloc` : les gabarits reprennent `bloc.titre` ou
`img.legende`, tous deux optionnels. Sur l'accueil `festival`, 3 cartes de
tutoriel (`photo_tutos-07/08/09`) sortent en `alt=""` — ni titre, ni légende,
ni alternative textuelle, alors que l'image *est* le contenu
(`faire_festival/partials/bloc_section_carte.html:18`).

**Correction** : ajouter un champ `alt` optionnel sur `Bloc`, avec repli sur
`titre`. À défaut, avertissement en admin quand une image n'a ni titre ni
légende.

### M4 — Aucune image ne porte `width`/`height` (CLS)

96 `<img>` sur les 7 pages inspectées, **0** avec `width=`/`height=` (seule
exception : la photo d'auteur 48×48 de `faire_festival/bloc_section_citation`).
Chaque image provoque un décalage de mise en page à son arrivée.

**Correction** : poser `width`/`height` (ou `aspect-ratio` en CSS) sur chaque
`<img>` des gabarits.

### M5 — Retour à la ligne littéral dans la `meta description` (skin `classic`)

`classic/shell.html:12-13` met `content="` et le contenu du bloc sur deux
lignes. Rendu réel :

```
<meta name="description" content="
            Découvrez le projet coopératif de Lespass : sa raison d&#x27;être…">
```

Le skin `faire_festival` n'a pas ce défaut (balise sur une seule ligne).

**Correction** : remettre la balise sur une seule ligne.

### M6 — `<title>` non borné quand `meta_title` est vide

`meta_title` est plafonné à 70 caractères (`models.py:281`), mais `titre` à 200
(`models.py:201`), et le `<title>` retombe dessus. Observé : 99 caractères sur
`/codensamb-preambule/`, tronqué par Google.

**Correction** : renseigner `meta_title` à l'import markdown, et/ou avertir en
admin quand `titre` dépasse ~60 caractères sans `meta_title`.

### M7 — `FAQPage` : les réponses sortent soudées dans le JSON-LD

`pages_tags.py:135` : `strip_tags(bloc.texte)` sur du HTML riche. Les balises
`</p>`/`</li>` disparaissent sans séparateur :

```json
"text": "…donne la possibilité de :Faire découvrir la fabrication…Partager, mutualiser…"
```

**Correction** : insérer une espace avant de dépouiller les balises de bloc.

### M8 — L'image LCP du skin `classic` est un fond CSS : découverte tardive

`classic/partials/bloc_section_banniere.html:16` pose l'image héros en
`--tb-hero-image: url(…)`, lue par `tb-blocs.css:432`.

> **Correction apportée par la relecture.** La première version de ce rapport
> affirmait qu'une image en `background-image` n'est jamais candidate LCP.
> C'est faux : la spécification LCP inclut explicitement les images chargées
> via `url()`. Les exclusions réelles sont les dégradés, les images à faible
> entropie et les images plein-viewport. Le héros **est** donc mesuré et
> apparaîtra bien dans Search Console.

Ce qui reste vrai, et justifie la correction : l'image n'est découverte
qu'après le parsing de `tb-blocs.css` (fichier externe), et un fond CSS
n'accepte ni `fetchpriority` ni `srcset`. Soit 209 704 o sur le chemin
critique, sans levier d'optimisation.

**Correction** : soit un vrai `<img>` en position absolue derrière le contenu
(permet `fetchpriority="high"`, `srcset`, et entre dans les mesures), soit à
minima un `<link rel="preload" as="image" fetchpriority="high">`.

### M9 — 204 Ko de JavaScript bloquant dans le `<head>`

`classic/shell.html:101,114,145,146` (et `faire_festival/shell.html:91,106,155,158`)
chargent sans `defer` ni `async` : bootstrap.bundle (80 673 o), htmx (48 101 o),
loading-states (5 116 o), sweetalert2 (70 718 o) = **204 608 o** qui bloquent le
parsing avant le premier rendu, sur toutes les pages. La convention `defer`
existe déjà dans le projet (`page.html:56` sur `sommaire_actif.js`).

**Correction** : ajouter `defer` aux quatre balises. L'ordre d'exécution des
scripts `defer` est préservé, donc le handler inline `htmx:beforeSwap` continue
de fonctionner.

### M10 — Ni compression ni cache HTTP sur les assets

`curl -skI --compressed` sur `tb-blocs.css` (77 131 o) et
`bootstrap.min.css` (232 758 o) : **aucun `Content-Encoding`**, **aucun
`Cache-Control`**. Ni `nginx/lespass_dev.conf` ni `nginx_prod/lespass_prod.conf`
ne portent `gzip on` ou `expires`. Bootstrap seul compresserait de 232 Ko à
~30 Ko.

**Correction** : `gzip_static on` + `expires` sur les blocs `location /static`
et `/media`. **Hors périmètre du moteur de pages** : c'est de l'infra, à
arbitrer par le mainteneur (un CDN en façade peut déjà compenser en prod).

---

## 3. Mineur

| # | Constat | Emplacement |
|---|---|---|
| m1 | `og:locale` absent | les deux `shell.html` |
| m2 | `og:image:alt` jamais spécifique à la page | les deux `page.html` |
| m3 | `WebPage` sans `datePublished`/`dateModified` alors que `created_at`/`updated_at` existent | `pages_tags.py:120` |
| m4 | `target="_blank"` sans `rel="noopener"` (4 liens) | `faire_festival/partials/footer.html:39,43,47,144` |
| m5 | Navbar principale sans `aria-label`, alors que les 3 autres `<nav>` en ont un | `navbar.html:3` (×2 skins) |
| m6 | `<a href="">` sur un déclencheur d'action (« Aide et contact ») — devrait être un `<button>` | `classic/partials/navbar.html:54` |
| m7 | Boutons langue/thème sans `aria-label` (seulement `title`) | `classic/partials/navbar.html:67,77` |
| m8 | `title` d'iframe générique et identique pour tous les embeds | `pages_tags.py:281,365` |
| m9 | `?section=` du sitemap ne filtre rien (les commentaires du code documentent un comportement inexistant) | `urls_tenants.py:31`, `pages/sitemap.py:20` |
| m10 | Bloc LISTE sans pagination : au-delà de `nombre_max`, les sous-pages deviennent orphelines du maillage interne | `bloc_liste.html:80` |
| m11 | FAQ non repliable côté `faire_festival` (incohérence entre skins, pas de défaut SEO) | `faire_festival/partials/bloc_faq.html:9` |
| m12 | `alt` du logo héros identique au `<h1 class="visually-hidden">` → double énonciation | `faire_festival/partials/bloc_section_banniere.html:19` |

### Constats de contenu (pas de code)

- **Meta descriptions dupliquées** : `ecosocialisme_numerique` / `link` / `rtl-cr`
  partagent la même ; idem `federation-part1`/`part2` et `link-python`/`subject-python`.
- **Pages fines** : `a-propos` (75 mots), `journal` (80), `notre-histoire` (83),
  `presentation` (41), `repair-cafe-bilan-un-an` (148).
- **Markdown mal formé** sur `/codensamb-preambule/` : le titre de page est
  répété en `#` dans le corps (d'où un `<h2>` identique au `<h1>`), et un fence
  ` ```python= ` (syntaxe HackMD, non supportée) fait interpréter les
  commentaires Python `# …` comme des titres — deux `<h2>` parasites.

---

## 4. Ce qui est correct

Vérifié et sain :

- Aucune URL hiérarchique ne répond en double
  (`/blog/codensamb-preambule/` → 404). En revanche le canonical lui-même
  n'était **pas** sain : voir B6 et B7.
- `noindex` par page correctement câblé, superposé au flag d'environnement.
- `<html lang>`, `<meta viewport>` (pas de `user-scalable=no`).
- Aucune balise dupliquée entre le socle BaseBillet et les skins.
- JSON-LD syntaxiquement valide partout ; `FAQPage` émis uniquement s'il y a des
  blocs FAQ ; `BreadcrumbList` fidèle à la hiérarchie.
- `robots.txt` construit depuis `request.get_host()` — correct en multi-tenant.
- Sitemap XML valide, accueil non dupliqué, `noindex` exclus, 87 URLs toutes en 200.
- Redirections : slash manquant → 301 direct, HTTP → HTTPS → 301 direct, aucune chaîne.
- Brouillons : 404 pour un anonyme, preview pour le staff.
- **Accessibilité** : c'est la partie la plus soignée. Contrastes WCAG AA
  précalculés et testés (`marque.css`), cibles tactiles ≥ 44 px,
  `:focus-visible` défini par composant sans jamais un `outline:none` orphelin,
  `prefers-reduced-motion` respecté, sommaire `<details>` natif au clavier.
- **Zéro dépendance externe** : aucune webfont CDN, aucun `preconnect` tiers.
- **Mobile** : débordement `100vw` déjà neutralisé par `overflow-x: clip`, avec
  la raison documentée dans le CSS.
- **HTMX** : rendu serveur complet au premier chargement, `hx-push-url` posé,
  `<title>` mis à jour au swap. Rien n'est invisible à un crawler.
- **Bloc FAQ (classic)** : `<details>/<summary>` natif, réponses dans le DOM au
  chargement — donc indexables.

---

## 5. Ce qui a été corrigé

Appliqué et vérifié sur le rendu réel. Les 87 URLs des 3 tenants répondent
toujours 200 après ces changements.

| Constat | Correction | Fichiers |
|---|---|---|
| B1 | Le second `<main>` devient un `<div>` | `classic/page.html` |
| B2+B3 | `og:title`/`twitter:title` partent de `meta_title` ; les blocs `twitter_title`/`twitter_description`/`og_image_alt` manquants sont ajoutés au skin classic | les deux `page.html` |
| B6+B7 | Canonical construit depuis `get_absolute_url()` via un nouveau `{% block canonical %}` | les deux `shell.html` + `page.html` |
| B4 | Les 10 `re_path` du routage tenant et le `re_path` du routage public sont ancrés avec `^` | `TiBillet/urls_tenants.py`, `TiBillet/urls_public.py` |
| B4 (suite) | `SLUGS_RESERVES` complété (12 mots, routes exactes) ; ancrage verrouillé par un test de comportement | `pages/models.py`, `tests/pytest/test_site_codecommun.py` |
| M1 | Le `<h2>` du bloc LIEU coiffe le bloc, sans condition sur le GPS | les deux `bloc_lieu.html` + `tb-blocs.css` |
| M2 | Le `<h2>` du bloc LISTE est masqué visuellement, plus supprimé | `bloc_liste.html` |
| M5 | `meta description` sur une seule ligne | `classic/shell.html` |
| M7 | Réponses FAQ : séparateur inséré avant `strip_tags` | `pages_tags.py` |
| m1 | `og:locale` ajouté | les deux `shell.html` |
| m3 | `datePublished`/`dateModified` dans le `WebPage` | `pages_tags.py` |
| m4 | `rel="noopener"` sur les 4 liens externes | `faire_festival/partials/footer.html` |
| m5 | `aria-label` sur la navbar principale | les deux `navbar.html` |
| m6 | `<a href="">` → `<button>` | `classic/partials/navbar.html` |
| m7 | `aria-label` sur les boutons langue et thème | `classic/partials/navbar.html` |
| m8 | Le titre du bloc devient le `title` de l'iframe | `pages_tags.py` + 2 gabarits |
| RSS-1 | `logout/` n'inclut plus l'urlconf RSS ; vraie route de déconnexion posée en alias de `deconnexion/` | `urls_tenants.py`, `BaseBillet/urls.py` |
| RSS-2 | Autodiscovery du flux (`<link rel="alternate" type="application/rss+xml">`) ajouté dans le `<head>` | les deux `shell.html` |

### Corrections issues de la relecture du code

Une seconde relecture, portant cette fois sur le code écrit, a trouvé six défauts
dans les corrections elles-mêmes. Tous rectifiés :

- **`.tb-bloc__leaflet-titre` désalignait le titre.** La section parente porte
  déjà `padding-inline` ; ma règle en ajoutait un second, décalant le `<h2>`
  d'une gouttière par rapport aux colonnes — l'inverse de ce que son commentaire
  affirmait. Règle supprimée : le cadrage du parent suffit.
- **`og:locale` produisait `en_EN`.** Le territoire n'est pas la langue en
  majuscules ; `en_EN` n'existe pas. Les deux locales du site sont désormais
  écrites explicitement (`fr_FR` / `en_US`).
- **`aria-label` en anglais sur le site français.** J'avais introduit un msgid
  `Main menu` inexistant, alors que la convention du projet veut un texte source
  **français** — et que le msgid `Menu principal` existait déjà, traduit.
- **La branche `br` du nettoyage FAQ était morte.** `<br>` est auto-fermant :
  le motif `</(…|br|…)>` ne matchait que `</br>`, forme qu'aucun éditeur ne
  produit. Un saut de ligne dans une réponse recollait donc les mots.
- **`SUFFIXES_RESERVES` était devenu nuisible.** Une fois les `re_path` ancrés,
  `notre-crowd` ou `guide-newsletter` sont des slugs parfaitement valides — le
  validateur les refusait quand même, et ses commentaires décrivaient au présent
  une faille corrigée dans le même lot. Supprimé. Seule l'extension de
  `SLUGS_RESERVES` (routes exactes) est conservée.
- **m6 n'était corrigé qu'à un endroit sur quatre.** Les trois autres
  déclencheurs d'`offcanvas` (footer classic, navbar et footer festival) sont
  passés en `<button>`.

Le test qui verrouillait l'ancien bug (`test_aucun_slug_ne_finit_par_un_token_de_route_non_ancree`)
gardait une fiction : il interdisait des slugs redevenus valides. Il est remplacé
par `test_les_routes_core_sont_ancrees_et_ne_capturent_pas_un_slug_de_page`, qui
vérifie le **comportement** (`resolve()` mène-t-il bien au moteur de pages ?) et
casse donc si un `^` disparaît.

Enfin, les commentaires qui racontaient l'historique du bug plutôt que de décrire
le code actuel ont été raccourcis, conformément à la règle FALC du projet.

### Tests

`912 passed` (pytest, 118 s) et `67 passed, 1 skipped` (E2E Playwright, 8 min),
**0 échec**. Les E2E ont d'abord dû être débloqués : Chromium avait disparu du
conteneur lors d'un rebuild Docker (68 erreurs de setup, sans rapport avec le
code) ; il a été réinstallé.

**Aucune migration n'est nécessaire** (`makemigrations --check` : *No changes
detected*) : seul le corps du validateur a changé, pas la signature du champ.
Aucun slug de page existante ne devient invalide (vérifié sur tous les schémas).

## 6. Ce qui reste, et pourquoi

Ces points ne sont **pas** corrigés — ils demandent un arbitrage, pas une
retouche de gabarit.

| Constat | Pourquoi il n'est pas corrigé |
|---|---|
| **B5** (srcset, 2,23 Mo d'images) | Piège relevé à la relecture : ajouter une variation à `VARIATIONS_IMAGE` ne vaut que pour les **nouveaux** uploads. Toutes les images existantes pointeraient vers un fichier inexistant (`.url` ne vérifie pas le disque) tant que `rendervariations` n'a pas tourné **sur chaque schéma tenant**. Par ailleurs l'option `quality` n'existe pas nativement dans stdimage : il faut un renderer custom. Chantier réel, à planifier. |
| **B8** (hreflang / bilingue) | Décision d'architecture d'URLs. Voir B8. |
| **M3** (champ `alt` sur `Bloc`) | Demande une migration et une reprise du contenu existant. |
| **M4** (`width`/`height` sur 96 images) | Faisable, mais poser des dimensions sur des images redimensionnées proportionnellement peut déformer la mise en page. À faire avec une vérification visuelle sur les trois largeurs d'écran — pas à l'aveugle. |
| **M9** (`defer` sur 204 Ko de JS) | La relecture a vérifié que c'est sûr (Swal gardé par `typeof`, Offcanvas dans `DOMContentLoaded`, module ES différé nativement). Mais ces shells servent **tout** le tenant, pas seulement le moteur de pages, et le gain se mesure en millisecondes contre le risque d'un bouton mort en démonstration publique. À appliquer puis tester l'interactivité en navigateur. |
| **M10** (gzip, cache HTTP) | Configuration nginx, hors code applicatif. Un CDN en façade peut déjà compenser en production. |
| **m9, m10, m11, m12** | Mineurs, sans impact sur l'indexation. |
| Constats de contenu | Meta descriptions dupliquées, pages fines, markdown mal formé de `/codensamb-preambule/` : c'est de la donnée, pas du code. |

**Point de contenu découvert en corrigeant M1** : le bloc LIEU de
`/infos-pratiques/` (festival) n'a **pas de titre en base**. Le gabarit est
maintenant correct, mais comme il n'y a rien à afficher, la page garde son saut
`h1 → h3`. Lui donner un titre (« Accès », « Venir au festival ») ajouterait un
intertitre visible qui n'existe pas sur www.fairefestival.fr : c'est à l'équipe
du festival de trancher, pas à l'audit.

## 7. Hors périmètre, signalé au passage

13 schémas de tenants (tous en UUID, résidus de suites de tests) n'ont pas la
migration `pages` appliquée : `column pages_page.affichage_nav does not exist`.
Les tenants nommés ne sont pas touchés. Ce n'est pas un défaut du moteur.
