# Audit SEO technique : accueil par défaut du skin V2 (la-filature.tibillet.coop)

Date : 2026-10-12. Périmètre : SEO technique, données structurées, performance.
Méthode : environ 41 requêtes GET publiques (curl, à peu près 1 par seconde) sur la-filature.tibillet.coop, raffinerie.tibillet.re et claf.tibillet.coop, plus la lecture du code dans /home/jonas/TiBillet/dev/Lespass (sans le modifier). Je n'ai pas lancé de navigateur headless : il n'y a donc pas de mesure LCP/CLS réelle, seulement des poids et des en-têtes.
Légende : **[V]** = vérifié (mesure en prod ou code lu), **[S]** = supposé (déduit, à confirmer).

---

## Notes

| Catégorie | Note | Justification |
|---|---|---|
| **Technique (crawl, indexation)** | **66/100** | Les bases sont là (200, 301 http→https, slash final, robots, sitemap, canonical, `lang`, meta robots). Mais le canonical reprend la query string, les pages filtrées `?tag=` sont indexables, la même URL sert FR et EN sans hreflang, le `lastmod` du sitemap n'est pas fiable et la 404 est en `index`. |
| **Données structurées** | **45/100** | Organization et WebSite sont présents et le JSON se parse. Mais le bloc est écrit à la main dans le gabarit (entités HTML dans le JSON), le logo pointe vers la photo de partage, `sameAs` est vide alors que le site web existe, il n'y a ni type « lieu » (Place/EventVenue), ni geo, ni téléphone, ni événements sur l'accueil. |
| **Performance** | **40/100** | TTFB bon (0,19 s), HTTP/2, polices en `swap`. Mais **aucune compression HTTP**, ~470 Ko de CSS bloquant non compressé, un hero de 391 Ko sans preload (servi aussi sur mobile), des images de cartes surdimensionnées sans `lazy`, ni WebP ni AVIF, des CSS maison en `no-cache`, `/media` sans en-tête de cache et Leaflet chargé d'office. |

---

## Ce qui marche [V]

- `/` répond 200 en HTTP/2. TTFB ≈ 0,19 s, total ≈ 0,23 s (depuis la France).
- `http://` → 301 → `https://`. `/event` → 301 → `/event/` (slash final cohérent). Le sous-domaine `www.` n'existe pas (pas de doublon www).
- `<html lang="fr">` et en-tête `Content-Language: fr`. `og:locale` suit la langue (`fr_FR` / `en_US`).
- Head complet : `<title>`, meta description, `meta robots index, follow`, canonical absolu, Open Graph complet (image 1200×630 avec dimensions et alt), Twitter `summary_large_image`, flux RSS déclaré.
- Un seul `<h1>` (nom du lieu), puis `<h2>` « Ce qui arrive » et des `<h3>` par carte d'événement.
- `robots.txt` dynamique par tenant, avec la ligne `Sitemap:` (`BaseBillet/views_robots.py:40-46`). Le blocage `Disallow: /` hors prod passe par `should_noindex()` : c'est bien conçu.
- `sitemap.xml` par tenant, en https, sur le domaine principal du tenant (`BaseBillet/sitemap.py:38-44`). Il contient 33 événements, `/`, `/event/` et `/federation/`. Les sections vides sont exclues (`sitemap.py:82-129`). Le `X-Robots-Tag: noindex` sur le sitemap vient de la vue Django et ne gêne pas.
- **Multi-tenant, contenu dupliqué :** je n'ai pas observé de duplication. Sur la-filature, les 22 liens d'événements de l'agenda pointent tous vers `la-filature.tibillet.coop`. Côté code, un événement fédéré renvoie vers son lieu d'origine (`event.full_url` avec la mention « via domaine », `pages/templates/cotton/V2/event_card.html:28,77,92`). Il n'est pas re-servi sous le sous-domaine qui l'affiche. raffinerie et claf n'affichent que leurs propres événements. [V]
- Les pages événement ont un JSON-LD `Event` construit en Python avec `json.dumps` (`pages/templatetags/pages_tags.py:409-510`), valide (parse OK), avec `location.geo`.
- Les images ont `width`/`height` (anti-CLS). Le logo France 2030 a des dimensions explicites.
- bootstrap.bundle et sweetalert sont en `defer`, bootstrap-icons est chargé de façon non bloquante (`media=print` + `onload`). Les polices sont auto-hébergées en woff2 avec `font-display: swap`. Aucun CDN tiers.
- En-têtes de sécurité : HSTS (1 jour, montée progressive volontaire), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `COOP`, `Permissions-Policy`.
- Les bibliothèques tierces versionnées (bootstrap, htmx, swal) ont `max-age=31536000, immutable`.

---

## Constats

### CRITIQUE

#### C1. Aucune compression HTTP (ni gzip ni brotli), sur le HTML comme sur les CSS et JS [V]
- **Preuve :** j'envoie `Accept-Encoding: gzip, br` et aucune réponse ne porte `Content-Encoding` : le HTML (61 976 o), `bootstrap.min.5.3.3.css` (232 758 o transférés), `V2.css` (140 225 o), `tb-blocs.css` (82 363 o), `htmx.min` (48 101 o), `bootstrap.bundle` (80 673 o).
- **Mesure :** gains gzip -9 calculés sur les mêmes fichiers :
  | Ressource | Brut | gzip |
  |---|---|---|
  | HTML accueil | 62 Ko | 15,8 Ko |
  | bootstrap.min.css | 233 Ko | 30,7 Ko |
  | V2.css | 140 Ko | 40,5 Ko |
  | tb-blocs.css | 82 Ko | 25,4 Ko |
  | bootstrap.bundle.js | 81 Ko | 23,7 Ko |
  | sweetalert2 | 71 Ko | 19,0 Ko |
  | htmx | 48 Ko | 15,6 Ko |
  | leaflet.js | 148 Ko | 42,4 Ko |

  Le CSS bloquant passe de **≈ 468 Ko à ≈ 101 Ko**. Le texte total de la page, de ≈ 900 Ko à ≈ 230 Ko.
- **Impact :** c'est le premier frein au FCP et au LCP sur mobile 3G/4G, sur **les ~500 lieux à la fois**. Il pèse sur les Core Web Vitals, donc sur le classement.
- **Code :** `nginx_prod/lespass_prod.conf` ne contient aucune directive `gzip`. L'image nginx officielle laisse `gzip` commenté par défaut. Traefik (TLS en amont) ne compresse pas non plus [S : pas de middleware `compress` vu dans le dépôt]. Le commentaire de `shell.html:143` (« 24 Ko gzippés ») suppose une compression qui n'existe pas en prod.
- **Correction :** dans le bloc `server` de `lespass_prod.conf` :
  ```nginx
  gzip on;
  gzip_vary on;
  gzip_proxied any;          # les réponses Gunicorn passent par proxy_pass
  gzip_comp_level 5;
  gzip_min_length 1024;
  gzip_types text/css application/javascript text/javascript application/json application/xml image/svg+xml text/plain application/rss+xml;
  ```
  Autre option : le middleware `compress` de Traefik sur le routeur Lespass. À la place, on peut aussi pré-compresser les statiques à la construction (`gzip_static on` + `.gz`, ou brotli).

---

### HAUT

#### H1. Le canonical (et `og:url`) reprend la query string sur l'accueil par défaut et sur toutes les vues hors CMS [V]
- **Preuve :** `https://la-filature.tibillet.coop/?utm_source=test` renvoie `<link rel="canonical" href="https://la-filature.tibillet.coop/?utm_source=test">` et le même `og:url`. Même chose sur `/event/?tag=discussion` : canonical sur `/event/?tag=discussion` et `index, follow`.
- **Impact :** chaque URL trackée (newsletter, réseaux sociaux, QR code) ou filtrée se déclare canonique. Il y a dispersion des signaux et des doublons. C'est aggravé par les badges de tags sur chaque carte d'accueil (`/event/?tag=…`), qui créent des dizaines de variantes crawlables de l'agenda par lieu, multipliées par 500 lieux.
- **Code :** `pages/templates/pages/V2/shell.html:65` (`{% block canonical %}{{ request.build_absolute_uri }}{% endblock %}`), `shell.html:29` (`og:url`) et `shell.html:48` (`twitter:url`). Ni `vues/accueil.html` ni `vues/agenda.html` ne surchargent ce bloc. `page.html:17-25` a déjà corrigé le problème pour les pages CMS, mais seulement pour elles. Le JSON-LD `Event.url` reprend aussi la query string (`pages_tags.py:434`).
- **Correction :** par défaut dans `shell.html`, utiliser `{{ request.scheme }}://{{ request.get_host }}{{ request.path }}` (sans query) pour le canonical, `og:url` et `twitter:url`. Mettre la même chose dans `jsonld_event` (`request.build_absolute_uri(request.path)`). Pour les filtres `?tag=` de l'agenda : `noindex, follow`, ou un canonical vers `/event/`.

#### H2. L'image hero de l'accueil par défaut (candidate LCP) n'a pas de preload et est servie en FHD même sur mobile [V]
- **Preuve :** le hero est un fond CSS `--tb-hero-image: url('/media/images/a-la-filature-…fhd.jpg')`, soit **390 671 o, JPEG 1594×972**. Le `<head>` ne contient aucun `<link rel="preload" as="image">`.
- **Impact :** le navigateur ne découvre l'image qu'après le téléchargement et le parsing des ~470 Ko de CSS non compressé (C1). Le LCP est probablement > 2,5 s sur mobile [S : pas de mesure navigateur]. Un téléphone télécharge les mêmes 391 Ko qu'un écran 1920 px.
- **Code :** `pages/templates/pages/V2/vues/accueil.html:30-32` utilise toujours `config.img.fhd.url`. Le preload existe pour le hero CMS (`pages/templates/pages/V2/page.html:69-71`) mais n'a pas été repris dans l'accueil par défaut.
- **Correction :** ajouter dans `accueil.html` un `{% block extra_meta %}` avec `<link rel="preload" as="image" href="{{ config.img.fhd.url }}" imagesrcset="{{ config.img.med.url }} 480w, {{ config.img.hdr.url }} 1280w, {{ config.img.fhd.url }} 1920w" imagesizes="100vw" fetchpriority="high">`. Encore mieux : remplacer le fond CSS par un vrai `<img srcset sizes fetchpriority="high">` positionné en `object-fit: cover`.

#### H3. Images des cartes : variante choisie selon la taille de l'écran et non celle de l'emplacement, sans `loading="lazy"` [V]
- **Preuve :** `<source srcset="…fhd.jpg" media="(min-width: 1920px), (min-height: 1920px)">`, puis `hdr` dès 1280 px de large. Sur un écran de bureau 1366 px, la carte « atelier » (≈ 380 px de large) charge `atelier.hdr.jpg` = **168 739 o (906×1280)**. Sur un écran 1920 px, elle charge `atelier.fhd.jpg` = **292 601 o (1358×1920)**. Le logo de l'en-tête (≈ 48 px affiché) charge `…logo….hdr.png` = 39 029 o (512×512), au lieu de la miniature de 13 Ko. Aucun `loading`, `decoding` ou `fetchpriority` sur les `<img>`.
- **Impact :** plusieurs centaines de Ko inutiles sur l'accueil, et bien plus sur `/event/` (21 cartes). Ces images sont toutes sous la ligne de flottaison mais téléchargées immédiatement, en concurrence avec le hero.
- **Code :** `BaseBillet/templates/commun/partials/picture.html:15-19` (sources pilotées par `media`) et `:32-37` (`<img>` sans `loading`). Ce partiel est utilisé par `cotton/V2/event_card.html:33` et `V2/tenant_header.html:33`.
- **Correction :** abandonner les `<source media=…>` au profit d'un seul `<img src="{{ img.med.url }}" srcset="{{ img.crop.url }} 480w, {{ img.med.url }} 960w, {{ img.hdr.url }} 1280w" sizes="{{ sizes|default:'(min-width: 992px) 33vw, 100vw' }}" loading="lazy" decoding="async">`, avec un paramètre `sizes` et `eager` pour les usages au-dessus de la ligne de flottaison. Pour le logo, `sizes="48px"`.

#### H4. JSON-LD Organization écrit à la main dans le gabarit : entités HTML dans le JSON, mauvais logo, `sameAs` vide [V]
- **Preuve (extrait prod) :**
  ```json
  "logo": "https://la-filature.tibillet.coop/media/images/a-la-filature-un-tiers-lieu-occupe-et-anime.social_card.jpg",
  "description": "… L&#x27;Université Populaire de Villeurbanne …",
  "sameAs": []
  ```
  - `&#x27;` est littéral dans le JSON : l'échappement automatique HTML de Django s'applique dans `<script>`, où il n'est pas décodé. Google lit donc « L&#x27;Université ».
  - `logo` pointe vers la **photo de partage 1200×630** (`get_social_card`), alors que le lieu a un vrai logo (`config.logo`, `cropped-Filature-logo-final-tricolore`, carré 512×512). Google attend un logo carré, au moins 112×112.
  - `sameAs: []` alors que `config.site_web = https://lafilature-villeurbanne.fr/` est affiché dans l'en-tête.
  - [S] Un `\` ou un caractère de contrôle dans `organisation` ou `short_description` rendrait le JSON invalide : c'est exactement la classe de bug déjà corrigée pour `Event` (docstring de `pages_tags.py:409-428`, « audit SEO 2026-07-05 »).
- **Impact :** Knowledge Panel et logo dans les résultats dégradés, signal d'entité faible. Le même gabarit est servi sur les 500 lieux.
- **Code :** `pages/templates/pages/V2/shell.html:79-107` (logo `:87`, description `:88`, sameAs `:89`). Un constructeur Python existe déjà : `seo/views_common.py:103` (`build_json_ld_organization`).
- **Correction :** remplacer le bloc par un template tag `{% jsonld_site %}` qui fait `json.dumps` (même échappement que `jsonld_event`, `pages_tags.py:506-510`). Y mettre `logo = config.logo.med`, `image = config.img`, `sameAs = [site_web, facebook, instagram, twitter]` filtré sur les valeurs non vides, ainsi que `telephone`, `email` et `geo`.

---

### MOYEN

#### M1. Pas de type « lieu » ni d'événements dans les données structurées de l'accueil [V]
- **Preuve :** l'accueil ne contient que `Organization` et `WebSite`. Il n'y a ni `Place`/`EventVenue`/`LocalBusiness` avec `geo` (les coordonnées 45.776963 / 4.877935 sont pourtant dans le HTML de la carte), ni `telephone` (affiché : 0698895330), ni `ItemList` des 3 événements affichés.
- **Impact :** occasion manquée pour le SEO local (tiers-lieu, adresse physique) et pour la découverte des événements depuis la page la plus forte du site.
- **Code :** `shell.html:79-107` et `vues/accueil.html` (aucun `extra_meta`). `seo/views_common.py:248` fournit déjà `build_json_ld_item_list`.
- **Correction :** sur l'accueil, `@type: ["Organization", "EventVenue"]` (ou `Place` + `Organization` reliés par `@id`) avec `address`, `geo`, `telephone`, `url`, `image`. Ajouter un `ItemList` des événements à venir (url + nom), via un `{% block extra_meta %}` dans `accueil.html`. Ajouter `@id` (`https://…/#organization`, `#website`) pour relier le graphe aux `Event.organizer` des pages événement.

#### M2. Une seule URL pour deux langues, choisie par `Accept-Language` ou par cookie, sans hreflang [V]
- **Preuve :** avec `Accept-Language: en-US`, la même URL `/` renvoie `<html lang="en">`, `Content-Language: en`, `<title>Home | La Filature</title>`, `og:locale en_US`, avec le même canonical. Il n'y a aucun `hreflang` dans le code (grep vide). Le changement de langue passe par un POST `/i18n/setlang/` puis un rechargement (`BaseBillet/static/commun/js/language-switcher.mjs`).
- **Impact :** la version EN n'est jamais indexable en tant que telle. Un robot qui envoie `Accept-Language: en` (certains crawlers Bing ou IA) indexera l'interface anglaise sous l'URL française [S]. Le titre de l'accueil peut varier d'un crawl à l'autre. Le contenu du lieu (descriptions, événements) reste en français dans les deux cas : l'intérêt d'une version EN indexée est donc faible.
- **Code :** `TiBillet/settings.py:393` (`LocaleMiddleware`), `:591` (`LANGUAGE_CODE='fr'`). Il n'y a pas d'`i18n_patterns`.
- **Correction (simple) :** assumer le FR comme seule version indexable. Servir la langue par défaut quand aucun cookie de langue n'est posé (ne pas négocier `Accept-Language` pour les visiteurs anonymes), et ne rien déclarer en hreflang. **(Complète)** : `i18n_patterns` avec un préfixe `/en/` et un hreflang `fr`/`en`/`x-default`. C'est plus lourd et peu rentable vu que le contenu est en FR.

#### M3. Sitemap : `lastmod` = date de création, accueil sans `lastmod` et moins prioritaire que les événements [V]
- **Preuve :** les événements ont `<lastmod>` = date de création (ex. `nerf-vague` : 2026-10-08) et `priority 0.7`. `/`, `/event/` et `/federation/` n'ont pas de `lastmod` et sont en `priority 0.5`. Le sitemap liste 33 événements dont 12 passés (septembre et début octobre).
- **Impact :** Google ignore un `lastmod` qu'il juge non fiable, et la modification d'un événement (date, tarif) n'est pas signalée. `priority` et `changefreq` sont ignorés par Google, mais l'incohérence reste visible pour les autres moteurs.
- **Code :** `BaseBillet/sitemap.py:59-61` (`return obj.created`), `:57` (tous les publiés, y compris passés), `:79-80`.
- **Correction :** `lastmod` = champ de dernière modification de l'Event (en ajouter un `auto_now` s'il n'existe pas). Pour `index` et `event-list`, `lastmod` = date de modification du plus récent événement publié. Garder les événements passés est acceptable (pages d'archive), mais on peut ne lister que ceux de moins de 12 mois.

#### M4. CSS bloquant lourd et scripts synchrones dans le `<head>` [V]
- **Preuve :** 6 feuilles bloquantes (bootstrap 233 Ko, V2 140 Ko, tb-blocs 82 Ko, tibillet 7,5 Ko, swal 4,3 Ko, vars 0,9 Ko), soit ≈ 468 Ko bruts. `htmx.min` (48 Ko) et `loading-states.js` (5 Ko) sont synchrones dans le `<head>`. `cartes/tb_fond_de_carte.js` est synchrone au milieu du `<body>`. `swal.css` est bloquant alors que SweetAlert n'est utilisé qu'à l'interaction. `tibillet.css` est à la fois préchargé et lié (preload inutile).
- **Impact :** cela retarde le FCP et le LCP, surtout sans compression (C1).
- **Code :** `shell.html:111-152` (CSS), `:179` et `:210` (htmx et loading-states non defer, choix assumé dans le commentaire `:172-178`), `vues/accueil.html:141` (script bloquant).
- **Correction :** charger `swal.css` comme bootstrap-icons (`media=print onload`). Passer `htmx` et `loading-states` en `defer` (l'ordre entre scripts `defer` est garanti, le risque évoqué dans le commentaire n'existe donc pas). Mettre `tb_fond_de_carte.js` en `defer` ou dans `charger()`. À terme, purger bootstrap.min.css (la majorité des classes ne sert pas au V2) [S].

#### M5. Carte Leaflet chargée systématiquement sur l'accueil [V]
- **Preuve :** le script inline (`accueil.html:142-202`) injecte immédiatement `leaflet.css` (14 Ko) et `leaflet.js` (148 Ko bruts, 42 Ko gzip), puis les tuiles MapTiler (plusieurs requêtes et centaines de Ko [S]).
- **Impact :** CPU et réseau en concurrence avec le rendu initial, pour un élément secondaire.
- **Correction :** n'appeler `charger(initCarteAccueil)` qu'au premier `IntersectionObserver` sur `#carte-accueil` (ou au clic sur une image statique).

#### M6. Cache navigateur : CSS maison en `no-cache` sans version, `/media` sans aucun en-tête de cache [V]
- **Preuve :** `V2.css`, `tb-blocs.css`, `tibillet.css`, `vars.css`, `favicon.png` et `france_2030.png` sont en `Cache-Control: no-cache`, d'où une revalidation (aller-retour 304) à chaque page. Les images `/media/...` n'ont **ni `Cache-Control` ni `Expires`** (cache heuristique seulement).
- **Code :** `nginx_prod/lespass_prod.conf:180` (`no-cache` par défaut pour `/static`), `:228-240` (`location /media` sans en-tête de cache).
- **Correction :** `ManifestStaticFilesStorage` (noms hachés), puis `immutable` sur tout `/static`. Dans `location /media` : `add_header Cache-Control "public, max-age=2592000";`. Les noms StdImage changent quand l'image change [S : sinon `max-age` plus court].

#### M7. Pas de formats d'image modernes [V]
- **Preuve :** toutes les variantes StdImage sont en JPEG ou PNG (hero 391 Ko, social card 279 Ko, logo PNG).
- **Correction :** générer des variantes WebP (ou AVIF) dans les `variations` StdImageField et les proposer via `<source type="image/webp">`. Gain attendu : 25 à 50 % du poids des images.

#### M8. `<title>` générique et court, `og:title` différent, meta description trop longue [V]
- **Preuve :** `<title>Accueil | La Filature</title>` (21 caractères, commence par un mot vide de sens), `og:title` = « La Filature ». Meta description de 199 caractères, tronquée vers 155-160 dans les résultats.
- **Code :** `vues/accueil.html:4` (`{% translate 'Accueil' %}` + `| organisation` depuis `shell.html:25`), `:6`.
- **Correction :** sur l'accueil, surcharger le bloc `title` en entier pour produire `{{ config.organisation }} — {{ ville }} : agenda, adhésion…`, sans « Accueil | ». Cela demande de surcharger le `<title>` complet, donc un bloc dédié dans `shell.html`. Aligner `og:title` dessus. Conseiller une `short_description` ≤ 155 caractères dans l'admin (indication ou compteur).

#### M9. JSON-LD Event : pas d'`offers` pour les événements gratuits ni d'`eventAttendanceMode` [V]
- **Preuve :** « Radio Social Club » (entrée libre) n'a pas d'`offers`, et il n'y a ni `eventAttendanceMode`, ni `isAccessibleForFree`. `addressCountry: "France"` (nom) plutôt que le code ISO `FR`.
- **Impact :** avertissements dans le test des résultats enrichis et éligibilité réduite à l'affichage « événements ». Ce constat concerne les pages liées depuis l'accueil.
- **Code :** `pages/templatetags/pages_tags.py:494-504` (`offers` seulement si un prix publié existe).
- **Correction :** sans tarif, mettre `offers: {"@type":"Offer","price":0,"priceCurrency":"EUR","availability":"InStock","url":…}` et `isAccessibleForFree: true`. Ajouter toujours `eventAttendanceMode: OfflineEventAttendanceMode`. Normaliser le pays en ISO-2.

---

### BAS

- **B1. La page 404 est en `index, follow` avec un canonical vers elle-même [V].** `/ceci-nexiste-pas-xyz/` renvoie 404 avec `<meta name="robots" content="index, follow">` et `canonical` = l'URL inexistante. Le statut 404 suffit à Google, mais la page reste incohérente. Code : `BaseBillet/templates/404.html` ne surcharge ni `meta_robots` ni `canonical`. Correction : `{% block meta_robots %}noindex, follow{% endblock %}` et un canonical vide ou absent.
- **B2. robots.txt minimal [V].** `Allow: /` seul. `/panier/`, `/my_account/`, `/connexion/`, `/i18n/` et les variantes `?tag=` ne sont pas exclus. Sur 500 lieux, une partie du budget de crawl part dans des pages sans valeur SEO. Code : `BaseBillet/views_robots.py:40-46`. Correction : `Disallow: /panier/`, `/my_account/`, `/i18n/`, et envisager `Disallow: /*?tag=` après avoir réglé H1.
- **B3. Favicon générique TiBillet de 36×36, identique sur les 500 lieux [V].** Il n'y a ni `apple-touch-icon` ni manifest. `/favicon.ico` renvoie un 301. Google recommande un multiple de 48 px. Dans les résultats, tous les lieux ont la même icône. Code : `shell.html:115`. Correction : favicon dérivé de `config.logo` (48/96/180 px) quand il existe.
- **B4. Téléphone non cliquable [V].** `0698895330` est en texte brut. Code : `vues/accueil.html:85-87`. Correction : `<a href="tel:+33698895330">` (format E.164) et `telephone` dans le JSON-LD (M1).
- **B5. Lien interne via une redirection [V].** La description longue (saisie par le lieu) contient `https://la-filature.tibillet.coop/event`, qui fait un 301 vers `/event/`. C'est un contenu admin, à corriger dans l'admin du lieu. Au passage, `long_description|safe` (`accueil.html:56`) laisse passer du HTML brut [S : plutôt une question de sécurité].
- **B6. HSTS toujours à 1 jour [V].** Le commentaire `nginx_prod/lespass_prod.conf:106-111` prévoit de passer à 1 an « après une semaine sans incident ». Pas de `Content-Security-Policy`.
- **B7. Poids mort dans le HTML [V].** ≈ 15,8 Ko de JS inline et ≈ 4,5 Ko de commentaires HTML de développeur (FR/EN, par exemple « HERO DE L'ACCUEIL PAR DÉFAUT », « CARTE LEAFLET DU LIEU ») sont envoyés sur chaque page, ainsi que 218 lignes vides. Correction : convertir les `<!-- -->` en `{# #}` / `{% comment %}`, et extraire les scripts inline récurrents (panier, offcanvas) dans un fichier statique mis en cache.
- **B8. Calcul inutile côté serveur [V].** `index()` calcule les prix de **tous** les événements fédérés (une requête `prices.filter` par produit, soit du N+1) alors que le gabarit n'en affiche que 3. Code : `BaseBillet/views.py:2821-2849`. De plus, `picture.html:35` lit `img.width`/`img.height`, ce qui ouvre le fichier image (I/O disque) à chaque carte. Le TTFB est bon aujourd'hui (0,19 s), mais il ne tiendra pas sur un lieu à forte programmation. Correction : `events_a_afficher[:3]` avant la boucle de prix, et `prefetch_related('products__prices')`.
- **B9. Pas de cache partagé possible [V].** Chaque visite anonyme reçoit un `Set-Cookie: csrftoken` et `Vary: Cookie, Accept-Language, HX-Request`, ce qui interdit un cache CDN ou micro-cache de l'accueil. À traiter seulement si la charge le justifie.
- **B10. Texte d'images vide [V].** Les images des cartes ont `alt=""`. C'est acceptable (le titre `<h3>` suit), mais cela ne contribue pas à la recherche d'images. Code : `cotton/V2/event_card.html:33`. On peut mettre `alt="{{ event.name }}"`.
- **B11. Boilerplate de pied de page identique sur 500 sites [V].** Le même paragraphe TiBillet et les mêmes 8 liens sortants (tibillet.coop, Discord, Matrix, GitHub…) sont sur chaque sous-domaine. Le risque est faible (même marque, souvent même domaine racine), mais ce texte dilue le contenu propre des accueils pauvres en texte. Code : `pages/templates/pages/V2/partials/footer.html`.
- **B12. URL de l'Organization sans slash final [V].** `"url": "https://la-filature.tibillet.coop"` alors que le canonical vaut `…coop/`. C'est cosmétique ; aligner sur la forme du canonical (`shell.html:86,103`).

---

## Estimation du poids de l'accueil (bureau 1366 px, cache vide) [V pour les fichiers mesurés, S pour le total]

| Poste | Brut (prod actuelle) | Avec gzip |
|---|---|---|
| HTML | 62 Ko | 16 Ko |
| CSS bloquant (6 fichiers) | 468 Ko | ≈ 101 Ko |
| bootstrap-icons (async) | 86 Ko | 13 Ko |
| JS (htmx, loading-states, bootstrap, swal, modules, fond de carte) | ≈ 220 Ko | ≈ 65 Ko |
| Leaflet css+js (dynamique) | 162 Ko | 46 Ko |
| Polices woff2 (Unbounded + Luciole, déjà compressées) | ≈ 140-230 Ko | idem |
| Images (hero 391 Ko, logo 39 Ko, 3 cartes ≈ 230-330 Ko, France 2030 15 Ko) | ≈ 680-780 Ko | idem (WebP : -30 à -50 %) |
| Tuiles de carte | non mesuré | |
| **Total** | **≈ 1,8-2,0 Mo** | **≈ 1,1-1,2 Mo** |

Ordre des gains, du plus rentable au moins rentable : C1 (gzip, une config nginx) > H2 (preload et taille du hero) > H3 (srcset/sizes + lazy) > M4/M5 (defer, Leaflet différé) > M6/M7 (cache, WebP).

---

## Fichiers clés
- `/home/jonas/TiBillet/dev/Lespass/pages/templates/pages/V2/shell.html` : head, canonical (l.65), og:url (l.29), JSON-LD manuel (l.79-107), assets (l.111-213)
- `/home/jonas/TiBillet/dev/Lespass/pages/templates/pages/V2/vues/accueil.html` : title (l.4), hero sans preload (l.30-32), téléphone (l.85-87), Leaflet (l.141-202)
- `/home/jonas/TiBillet/dev/Lespass/pages/templates/pages/V2/page.html` : modèle à suivre (canonical l.25, preload hero l.69-71)
- `/home/jonas/TiBillet/dev/Lespass/BaseBillet/templates/commun/partials/picture.html` : sources `media` (l.15-19), img sans lazy (l.32-37)
- `/home/jonas/TiBillet/dev/Lespass/pages/templatetags/pages_tags.py` : `jsonld_event` (l.409-510)
- `/home/jonas/TiBillet/dev/Lespass/BaseBillet/sitemap.py` : lastmod (l.59-61)
- `/home/jonas/TiBillet/dev/Lespass/BaseBillet/views_robots.py` : robots (l.40-46)
- `/home/jonas/TiBillet/dev/Lespass/BaseBillet/views.py` : `index()` (l.2780-2851)
- `/home/jonas/TiBillet/dev/Lespass/BaseBillet/templates/404.html` : pas de noindex
- `/home/jonas/TiBillet/dev/Lespass/nginx_prod/lespass_prod.conf` : pas de gzip, cache `/static` (l.180) et `/media` (l.228-240), HSTS (l.111)
