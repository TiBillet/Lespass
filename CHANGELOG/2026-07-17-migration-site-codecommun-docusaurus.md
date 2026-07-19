# Migration du site Code Commun (Docusaurus → moteur pages) / Code Commun website migration

**Date :** 2026-07-17
**Migration :** Non (pas de migration Django ; commande de chargement de contenu)

## Resume / Summary

**Quoi / What :** une management command `charger_site_codecommun` reconstruit
l'ancien site vitrine Docusaurus « Coopérative Code Commun » (accueil + docs +
blog) dans le moteur pages (Page + Bloc), sur un tenant. Le contenu source
(markdown + images) est bundlé dans `pages/fixtures/site_codecommun/` — la commande
est relançable en prod sans dépendance externe.
/ A `charger_site_codecommun` management command rebuilds the old Docusaurus
showcase site (home + docs + blog) into the pages engine, on a tenant. Source
content (markdown + images) is bundled under `pages/fixtures/site_codecommun/`.

**Pourquoi / Why :** remplacer le Docusaurus par le moteur de pages/blocs de
TiBillet, en préservant le contenu et le référencement (slugs porteurs).
/ Replace Docusaurus with TiBillet's page/block engine, preserving content and SEO.

### Ce que fait la commande
- **Accueil** reconstruit à la main en blocs (l'ancienne home était du React) :
  HERO + section coopérative + **teaser services** (CTA → /services/) + 4 cartes
  logiciels + **CTA contact** (« Un projet numérique ? Discutons-en » → ouvre le
  panneau offcanvas « Contact et support » + espace contributif) + bande de
  partenaires. Les partenaires réutilisent la liste
  CANONIQUE de la landing publique (`seo.views.CONTRIBUTEURS`, logos servis depuis
  `seo/static/contributeurs/` via le finder staticfiles) — source unique de vérité,
  partagée avec le tenant public. Le logo SVG est écarté (Pillow ne redimensionne
  pas un SVG).
- **TiBillet** : page unique (`/tibillet/`) **fusionnant** les 3 fiches Créations
  (Lèspass, LaBoutik, Fedow — modules d'un même projet). Intro inspirée de la
  landing du tenant public + 3 sections IMAGE_TEXTE + CTA + galerie de captures.
- **Docs & blog** : 1 Page + 1 bloc MARKDOWN chacun, sous des pages-index de
  catégorie (Présentation, Formations, Blog) avec un bloc LISTE_SOUS_PAGES. Le
  blog est une page `est_blog` (ses enfants = Articles).
- **Services** : catégorie à fiche unique (sysadmin.md) → **inlinée en page de
  1er niveau** (`/services/`), pas de dropdown à un seul item dans la navbar.
- **Menu** : libellé blog raccourci « Recettes & blog » → « Blog ». Il ne reste
  que 2 dropdowns (Présentation, Formations). Les items Réseau/Agenda/Adhésions/
  Contribuez viennent des MODULES du tenant (config `module_*`), pas du script.
- **Images** du markdown : uploadées dans le media du tenant comme `ImageGalerie`
  du bloc, puis réécrites en `![légende](galerie:N)` (mécanisme natif). Images
  externes laissées en hotlink. **Liste noire** `IMAGES_A_IGNORER` : les
  illustrations d'ambiance décoratives du blog (python-gen, anar-libre,
  hypermedia/original, decollage, design_head, fedow_logo, congratulations…) ne
  sont ni uploadées ni rendues ; seules les images descriptives (schémas,
  captures, logos institutionnels) sont conservées.
- **Services** : contenu enrichi (`sysadmin.md`) — hébergement (TiBillet,
  Nextcloud, Odoo), **installation de Ghost**, **animation & co-construction de
  projets numériques**.
- **Liens internes** `/docs/<x>`, `/blog/<x>`, `/docs/Creations/<x>` (relatifs et
  absolus vers codecommun.coop) réécrits vers `/<slug>/`.

### Slugs & SEO
Hiérarchie Docusaurus (catégories imbriquées) **aplatie sur 1 niveau** (le moteur
sert tout à plat sur `/<slug>/`). Les slugs porteurs sont conservés
(`/charte/`, `/python-unpacking/`, `/tibillet/`…). L'URL exacte `/docs/...` /
`/blog/...` n'est pas reproductible ; les redirections **301** ancienne → nouvelle
URL sont un **chantier séparé** (à faire au niveau nginx, sur codecommun.coop).

### Piège rencontré — routing core non ancré
`TiBillet/urls_tenants.py` a des `re_path` **non ancrés** (`re_path(r'fedow/', …)`,
`api/`, `crowd/`…). Django utilise `.search()` : un slug se **terminant** par un de
ces tokens (ex. `tibillet-fedow`, `federation-part5-fedow`) est capté par la route
API DRF → **403**. Contourné SANS toucher au core : la fiche `tibillet-fedow` a
disparu dans la fusion `/tibillet/`, et l'article `federation-part5-fedow` a été
renommé `federation-part5`. Un test verrouille cette classe de bug.

### Fichiers ajoutés / Added files
| Fichier / File | Rôle / Role |
|---|---|
| `pages/management/commands/charger_site_codecommun.py` | La commande de chargement |
| `pages/fixtures/site_codecommun/manifest.py` | Arbre du site (catégories, alias, redirections) |
| `pages/fixtures/site_codecommun/docs/*.md` (8) | Corps markdown des docs |
| `pages/fixtures/site_codecommun/blog/*.md` (19) | Corps markdown des articles |
| `pages/fixtures/site_codecommun/img/**` (~97) | Images de contenu (bitmap) |
| `tests/pytest/test_site_codecommun.py` | Tests slugs (unicité, tokens 403, réservés) + réécriture liens |

### Dates de parution du blog / Blog publication dates
Les articles gardent leur VRAIE date de parution (lue dans le préfixe du nom de
fichier `AAAA-MM-JJ`, convention Docusaurus). `created_at`/`updated_at` étant des
champs auto (`auto_now_add`/`auto_now`), la commande force la date via un
`update()`. Sans ça, chaque article afficherait « Publié le \<jour de l'import\> ».
Les pages docs (non datées) gardent la date d'import.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/classic/partials/navbar.html` | Le script d'auto-ouverture d'offcanvas (déjà là pour `?login=1`) gère aussi `?contact=1` → ouvre le panneau `#contactPanel`. Additif, template classic partagé. |
| `pages/static/pages/css/tb-blocs.css` | Cartes en grille : boutons alignés en bas (`margin-top:auto` sur `.tb-bloc__bouton`, la grille étire déjà les cartes) → tous les boutons à la même hauteur quelle que soit la longueur du texte. + `text-wrap: balance` sur les titres de blocs (évite les mots orphelins). Template classic partagé. |

---

## Comment tester (à la main) / Manual test

### Pré-requis
Un tenant cible existe (en prod : `codecommun`). En dev, tester sur un tenant
sandbox sans pages (ex. `la-maison-des-communs`).

### Test 1 — chargement
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py \
    charger_site_codecommun --schema=<tenant>
```
Attendu : `Site Code Commun chargé sur '<tenant>' (~33 pages).`, **aucun warning**
`⚠ image ... ignorée`.

Relance idempotente : re-lancer la commande ne duplique pas (get_or_create par slug,
blocs vidés puis recréés). Option `--no-home` pour ne pas écraser une home existante.

### Test 2 — rendu (navigateur)
Ouvrir `https://<tenant>.tibillet.localhost/` :
1. **Accueil** : bannière « Fabrique de Communs Numériques », section coopérative,
   4 cartes logiciels avec bouton « Découvrir », bande de logos partenaires.
2. **/tibillet/** : intro + 3 sections Lèspass / LaBoutik / Fedow (images alternées
   gauche/droite), CTA, galerie de captures.
3. **/blog/** : liste des 19 articles (cartes LISTE_SOUS_PAGES). Ouvrir un article
   (ex. `/python-unpacking/`) : markdown rendu, images visibles.
4. Navbar : Présentation, TiBillet, Services, Formations, Blog (dropdowns par
   catégorie).

### Test 3 — pas de 403 (piège fedow)
```bash
BASE="https://<tenant>.tibillet.localhost"
for p in / /presentation/ /tibillet/ /services/ /formations/ /blog/ \
         /charte/ /commun_numerique/ /federation-part5/ /python-unpacking/; do
  echo "$(curl -k -s -o /dev/null -w '%{http_code}' "$BASE$p")  $p"
done
```
Attendu : **tout en 200**. (`/tibillet-fedow/` et `/federation-part5-fedow/`
renvoient encore 403 mais ne font PLUS partie du site — anciennes URL à gérer par
les 301.)

### Verifs / Tests auto
```bash
docker exec lespass_django poetry run pytest \
    /DjangoFiles/tests/pytest/test_site_codecommun.py \
    /DjangoFiles/tests/pytest/test_pages.py -q
```

### Reste à faire (chantiers séparés)
- **Redirections 301** ancienne URL Docusaurus → nouveau slug (au niveau nginx,
  sur codecommun.coop), une fois le domaine de go-live confirmé.
- **Footgun routing** : anchor les `re_path` de `TiBillet/urls_tenants.py` avec `^`
  (décision mainteneur — hors périmètre de ce chantier).
- **Brouillons** (5 non migrés) et logo partenaire SVG (La Compagnie des Tiers-lieux)
  écartés volontairement.
