# CHANTIER 07 — Simplification du moteur : catalogue resserré, arbre, sidebar

> Spec actionnable. Vague 5. Rédigée puis réécrite le 2026-07-18 après arbitrage du
> mainteneur et deux relectures adverses (agent Fable).
> Lire `SPEC.md`, `ETAT-REPRISE.md` et `tests/PIEGES.md` avant d'attaquer.
> **Rien n'est en production.** Casser les URLs, les données, les blocs — et en
> supprimer — est explicitement autorisé (mainteneur, 2026-07-18).

## 1. L'intention

Ce chantier n'ajoute pas de fonctionnalités. Il rend le moteur assez simple pour qu'un
front léger, plus tard, tienne en trois clics :

```
bouton +  →  modal « quel type de bloc ? »  →  saisie du contenu  →  fini
```

Tout ce qui ne sert pas cet objectif est coupé. Tout ce qui le contrarie est supprimé,
même si ça marche aujourd'hui.

**Le front n'est pas dans ce chantier** (décision mainteneur 2026-07-18). Il sera traité
séparément, en HTMX + session admin, via le process `/djc` complet. Conséquence directe :
**l'API v2 n'est pas le contrat du front** — elle reste celui des agents et du MCP. La
question « session ou clé API » est donc tranchée : **session**. Voir §7 pour ce que le
futur chantier front devra reprendre.

### Les deux obstacles traités ici

1. **Le catalogue à 19 types.** Un modal à 19 entrées n'est pas « trois clics ».
2. **Le groupement implicite** (`services.py:74-157`) : ajouter un bloc change la mise
   en page de deux autres, sans le dire.

## 2. Décisions verrouillées

### 2.1 Le catalogue passe de 19 types à 7

Les 19 types décrivent des **rendus**, pas des **intentions**. Le nouveau catalogue est
organisé par intention de l'utilisateur :

| Type | Intention | Remplace |
|---|---|---|
| `TEXTE` | « j'écris du texte » | `PARAGRAPHE`, `MARKDOWN` |
| `SECTION` | « je mets quelque chose en avant » | `HERO`, `CTA`, `IMAGE_TEXTE`, `CARTE`, `TEMOIGNAGE` |
| `IMAGES` | « je montre une ou plusieurs images » | `IMAGE`, `GALERIE`, `PARTENAIRES` |
| `INTEGRATION` | « j'intègre un truc externe » | `EMBED`, `IFRAME`, `NEWSLETTER` |
| `LIEU` | « je montre où c'est » | `CARTE_LEAFLET` + `INFOS` (fusion 2→1) |
| `FAQ` | « je réponds à des questions » | `FAQ` |
| `LISTE` | « je liste des choses automatiquement » | `EVENEMENTS`, `LISTE_SOUS_PAGES` |

`VIDEO_TEXTE` **n'est pas absorbé : il est supprimé.** Le champ `video` (mp4 uploadé)
disparaît, et avec lui la section composée « vidéo à gauche / texte + cartes + bouton à
droite » du skin `faire_festival` (`page.html:135-182`). C'est une perte assumée, pas
une migration. Pour une vidéo : `INTEGRATION` en affichage `VIDEO`.

**Le champ `affichage`** (choices) porte la variation visuelle à l'intérieur d'un type :

| Type | Valeurs d'`affichage` |
|---|---|
| `SECTION` | `BANNIERE` · `TEXTE_IMAGE_GAUCHE` · `TEXTE_IMAGE_DROITE` · `CARTE` · `APPEL_ACTION` · `CITATION` |
| `IMAGES` | `PLEINE_LARGEUR` · `VIGNETTE_TITRE` · `GRILLE` · `BANDE_LOGOS` |
| `INTEGRATION` | `VIDEO` · `WIDGET` · `NEWSLETTER` |
| `TEXTE`, `LIEU`, `FAQ`, `LISTE` | — (un seul rendu) |

Trois précisions imposées par la relecture :

- **`TEXTE_IMAGE_GAUCHE` / `TEXTE_IMAGE_DROITE` remplacent le champ `image_position`.**
  Il est utilisé **3 fois** par `charger_site_codecommun.py` (lignes 523, 549, 571) pour
  alterner délibérément les modules TiBillet. Le supprimer et alterner en `nth-child`
  serait exactement la mise en page décidée dans le dos de l'utilisateur qu'on bannit.
- **`VIGNETTE_TITRE` est conservé.** Décision mainteneur documentée du 2026-07-05
  (`models.py:436-441`), citée en jurisprudence dans cette spec : la supprimer serait se
  contredire.
- **`INTEGRATION` : les trois affichages sont obligatoires et explicites**, parce qu'ils
  sélectionnent **trois pipelines de sécurité différents** — whitelist codée + URL
  reconstruite (`embed_iframe`), whitelist ROOT + sandbox + hauteur (`iframe_libre`),
  script Ghost (`bloc_newsletter.html`). Deviner le pipeline depuis l'URL serait
  l'interrupteur caché qu'on bannit, **sur un sujet de sécurité**.

### 2.2 `TEXTE` est du markdown, point

`PARAGRAPHE.texte` stocke du HTML nettoyé par `clean_html` au save. `MARKDOWN.texte`
stocke de la source markdown, **exemptée** de `clean_html` en trois endroits (`admin.py`
save_model, `serializers.py:2031-2046`, `views.py:1283-1286`) et sécurisée au rendu par
`nh3`.

Faire dépendre ce choix d'un select ferait **changer le pipeline de sécurité** selon une
valeur d'affichage. C'est bien plus dangereux qu'`affichage_image`. Donc :

**`TEXTE` = markdown, un seul pipeline.** Les blocs `PARAGRAPHE` existants sont migrés
(leur HTML reste valide dans du markdown, `nh3` le filtre au rendu). Une règle, zéro
branche.

### 2.3 `affichage` doit être validé contre le type

Django ne sait pas conditionner des choices par la valeur d'un autre champ : un seul
`CharField` porte l'**union** des valeurs, donc `SECTION` + `affichage=BANDE_LOGOS` est
stockable tel quel. Sans garde, c'est la faiblesse du `variante` écarté, juste déplacée.

La table §2.1 devient une constante `AFFICHAGES_PAR_TYPE` dans `blocs_catalogue.py`,
**appliquée à trois endroits, pas un** :

1. `Bloc.clean()` — refus si l'affichage n'appartient pas au type ;
2. les serializers API (création **et** `partial_update`, qui ne fait aucun `full_clean`
   aujourd'hui) ;
3. `GET /api/v2/block-types/` — contrat des agents et du MCP.

### 2.4 `LISTE` : la source est un champ, pas un affichage

`SOUS_PAGES` / `EVENEMENTS` n'est pas une variation visuelle, c'est une **source de
données**. Un champ `affichage` qui sélectionne une requête est de la sémantique
brouillée. `LISTE` porte donc :

- `source` (choices : `SOUS_PAGES` · `EVENEMENTS`),
- `page_source` (FK, `null` = page courante, `on_delete=PROTECT`) quand `source=SOUS_PAGES`,
- `nombre_max`.

### 2.5 `grouper_blocs` est supprimé — et la grille vit dans `<main>`

`services.py:74-157` décide aujourd'hui sans le dire : `VIDEO_TEXTE` absorbe les `CARTE`
suivantes plus un `CTA` ; les `CARTE` consécutives fusionnent en grille ; `INFOS` +
`CARTE_LEAFLET` se collent côte à côte ; les `FAQ` consécutives passent en deux
colonnes. Dans un front `+` → modal, c'est rédhibitoire.

**Chaque bloc se rend seul.** Mais « les grilles passent en CSS » n'est pas une solution
tant qu'on n'a pas dit **où vit la grille** : `grid` opère sur les enfants d'un
conteneur, or chaque bloc est aujourd'hui une `<section>` pleine largeur portant son
propre `.tb-bloc__contenu`.

**Décision : `<main>` devient une grille 12 colonnes.** Chaque bloc y prend `span 12`
par défaut ; `SECTION`/`affichage=CARTE` prend `span 4`, `FAQ` prend `span 6`. Des blocs
consécutifs coulent alors côte à côte sans une ligne de Python. Le balisage externe de
tous les partials est à réécrire — c'est le vrai coût du lot C, acté ici et pas
découvert en vol.

Perte assumée : la maçonnerie équilibrée en `column-count` des FAQ du skin festival
(`faire_festival/page.html:105`) n'est pas reproductible en grid.

### 2.6 Le blog est retiré du moteur

Décision mainteneur 2026-07-18 : l'usage d'un outil externe pour le blog est encore en
réflexion, le moteur n'a pas à porter le cas en attendant.

Disparaissent :

- **`Page.est_blog`** — il portait deux responsabilités : le typage sémantique (JSON-LD
  `Article` + byline date/auteur : `views.py:64`, `page.html:63-70`, `pages_tags.py:46`)
  **et** le masquage de ses enfants dans le dropdown navbar
  (`BaseBillet/views.py:292`), soit un mécanisme de navigation concurrent de celui de la
  navbar. Les deux partent.
- **Le JSON-LD `Article` et la byline visible.** Une page est une page.
- **L'option `afficher_date` sur `LISTE`**, qui n'existait que pour un index d'articles.
- **Les 19 fixtures `pages/fixtures/site_codecommun/blog/`** et l'entrée `blog` du
  manifeste (`manifest.py:71-79`). Il reste 8 fichiers `docs/`.

Trois effets de bord agréables, vérifiés le 2026-07-18 :

1. **Une valeur d'`affichage_nav` en moins.** Le cas « index dans la navbar, enfants hors
   dropdown » n'existait que pour le blog. Une section de doc à 15 sous-pages sera en
   `SIDEBAR`, pas en `NAVBAR` — le problème ne se pose plus. La matrice §2.8 reste à
   **trois** valeurs.
2. **Plus aucune admonition à traiter.** Les seules occurrences `:::note` étaient dans
   `blog/2023-10-14-hypermedia-on-whateveryoulike.md` — **zéro dans `docs/`**. La
   décision de ne pas supporter la syntaxe Docusaurus devient sans objet.
3. **Un piège documenté disparaît** : le commentaire `manifest.py:135` signale un article
   dont le slug finissant par « fedow » déclenchait un 403 (route core non ancrée).

### 2.7 L'arbre passe à N niveaux, les URLs restent plates

- **Profondeur maximale : 6.** Vérifié le 2026-07-18 : la vraie doc TiBillet atteint
  exactement **5** niveaux (`guide-des-lieux/billetterie-agenda-lespass/
  faq-billetterie-agenda-lespass/gerer-ses-ventes-avec-stripe/gerer-les-paiements-…`,
  dans `../documentation_v3/content/zensical.toml`). Un niveau de marge, pas plus.
- `clean()` : les trois règles « un seul niveau » (`models.py:337-351`) sont remplacées
  par deux gardes — anti-cycle et profondeur. C'est moins de code qu'aujourd'hui.
- **Les URLs restent `/<slug>/`, `slug` reste `unique=True` global.**
- **`parent` passe en `on_delete=PROTECT`.** Question indépendante de la forme des URLs :
  sous `SET_NULL`, supprimer un nœud intermédiaire promeut ses enfants **à la racine** —
  15 pages de doc déboulent dans la navbar, avec une valeur `affichage_nav` stockée que
  personne n'a jamais vue puisque masquée par `conditional_fields`.
- `limit_choices_to` (`models.py:302`) retiré.
- **`est_accueil` ne peut pas avoir d'enfants** (`clean()`) : servie sur `/` tout en
  portant un slug, ses enfants auraient un rattachement ambigu.

> **L'URL hiérarchique est coupée du chantier.** C'était toute la complexité : ancrage du
> routage core, résolution multi-segments, 404 partiel, double contrainte d'unicité (les
> `NULL` de Postgres rendent `unique_together(parent, slug)` inopérant à la racine),
> réécriture des liens figés en base par `charger_site_codecommun.py:437-462`, API
> ambiguë par slug.
>
> L'arbre et l'URL sont deux choses distinctes : le gain de l'arbre est la *navigation*
> — sidebar, précédent/suivant, fil d'Ariane — et elle fonctionne avec des URLs plates.
> Google accepte un `BreadcrumbList` non miroir du chemin. Chantier séparé, rien ici ne
> l'empêche.
>
> **Contrepartie à assumer** : à profondeur 5, une doc répète naturellement ses feuilles
> (« installation », « configuration » sous chaque produit). Avec `slug unique=True`
> global, l'auteur devra préfixer à la main. L'admin doit donc afficher l'erreur
> d'unicité **avec le chemin de la page en conflit**, sinon c'est indéchiffrable.

### 2.8 `affichage_nav` — matrice de visibilité

`affichage_nav = NAVBAR | SIDEBAR | AUCUN`, défaut `NAVBAR`. Lu **uniquement sur la
racine** de l'arbre, hérité par les descendants ; masqué par `conditional_fields` dès que
`parent` est renseigné — sinon c'est une valeur saisissable et silencieusement ignorée,
donc de la magie au sens FALC.

| État | Navbar | Sidebar | Sitemap | Préc./suiv. | Fil d'Ariane |
|---|---|---|---|---|---|
| `NAVBAR` | ✅ (dropdown si enfants) | ❌ | ✅ | ❌ | ✅ |
| `SIDEBAR` (racine) | ✅ 1 entrée | ✅ | ✅ | ✅ | ✅ |
| `SIDEBAR` (descendant) | ❌ | ✅ | ✅ | ✅ | ✅ |
| `AUCUN` | ❌ | ❌ | ✅ | ❌ | ✅ |
| `publie=False` | ❌ | ❌ | ❌ | ❌ | ❌ |
| `noindex=True` | inchangé | inchangé | ❌ | inchangé | inchangé |

`AUCUN` **reste dans le sitemap** : la page est atteignable par URL et par un bloc
`LISTE`, elle est simplement hors navigation. C'est `noindex` qui la sort des moteurs.

### 2.9 Ce qui est conservé et ce qui est écarté

**Conservé** (demande explicite du mainteneur) : fil d'Ariane, table des matières,
sous-pages.

**Écarté** :
- **M2M de pages sélectionnées** sur `LISTE` — le FK `page_source` couvre le besoin (les
  modules TiBillet sont des frères sous un même parent dans `zensical.toml`), se met à
  jour tout seul, évite un modèle `through` ordonné. À reconsidérer **sur preuve**.
- **Les admonitions Docusaurus** — sans objet depuis le retrait du blog (§2.6).
- **La TOC en troisième colonne.** Un `<details>` en tête de contenu évite le layout
  trois colonnes, le deuxième burger et tout l'arbitrage responsive.
- **La recherche plein texte.** À déclencher quand codecommun dépasse ~50 pages.
- **L'app `seo/`.** On n'y touche pas.
- **Le front de construction de blocs.** Chantier séparé, en HTMX + session, via `/djc`.

## 3. Pré-requis vérifié en test — `nh3` supprime `id` **et** `class`

Exécuté dans le conteneur le 2026-07-18 :

```
--- markdown brut ---
<h2 id="presentation-du-cafe">Présentation du café</h2>
<div class="codehilite"><pre><code><span class="n">x</span>…

--- après nh3.clean ---
<h2>Présentation du café</h2>
<div><pre><code><span>x</span>…
```

**La TOC pointerait dans le vide** (pas d'`id`) **et la coloration syntaxique serait
invisible** (pas de `class`). Whitelist d'attributs explicite obligatoire dans
`nh3.clean()`.

**Piège associé** : la démotion des titres (`pages_tags.py:523-525`) fait
`.replace("<h2>", "<h3>")` sur des chaînes **exactes, sans attributs**. Dès que
l'extension `toc` ajoute `id="…"`, ça casse **en silence**.

Bonne nouvelle : la slugification des accents est correcte (`Présentation du café` →
`presentation-du-cafe`).

## 4. Les lots

### Lot A — `Page.get_absolute_url()`

Une méthode remplace la règle `est_accueil → "/"` dupliquée. **Appelants exhaustifs :**

| Fichier | Ligne | Note |
|---|---|---|
| `pages/sitemap.py` | 46-48 | le `if obj.est_accueil` est **du code mort** : `items()` ligne 34 filtre déjà `est_accueil=False` |
| `BaseBillet/views.py` | 300 | navbar |
| `pages/admin.py` | 187 | `display_voir` |
| `api_v2/serializers.py` | 2155, 2164 | `url` et `isPartOf.url` |
| `pages/templatetags/pages_tags.py` | 100 | `BreadcrumbList` JSON-LD |
| `pages/templates/pages/classic/page.html` | 81 | fil d'Ariane visible |
| `partials/bloc_liste_sous_pages.html` | — | cartes |

**Risque** : nul. Indépendant du reste.

### Lot B — Refonte du catalogue : 19 types → 7

- `TYPE_BLOC_CHOICES` réécrit (7 entrées) ; `Bloc.affichage` + `AFFICHAGES_PAR_TYPE`
  (§2.3) ; `Bloc.source` pour `LISTE` (§2.4).
- `blocs_catalogue.CHAMPS_PAR_TYPE` réécrit — il reste la **source unique** consommée par
  l'API.
- **Champs supprimés** : `surtitre`, `badge`, `image_secondaire`, `video`,
  `image_position` (→ deux affichages), `affichage_image` (→ `affichage`), `repliable`
  (la FAQ devient **toujours accordéon**). Les champs `auteur_*` **restent** — ils ne
  servent qu'à `SECTION`/`CITATION`, c'est assumé.
- Gabarits : un partial par couple (type, affichage). Les 19 partials sont refondus.
- **Migration de données**, deux cas :
  - 1:1 pour la majorité (`HERO` → `SECTION`/`BANNIERE`, etc.) ;
  - **2:1 pour `INFOS` + `CARTE_LEAFLET` adjacents → un seul `LIEU`.** Sans ce cas
    spécial, on obtient deux blocs `LIEU` à moitié vides empilés.
  - App **dual-list** : protéger par le garde `connection.schema_name == "public"`.
- `charger_site_codecommun.py` et `pages/fixtures/site_codecommun/` mis à jour.

**Risque** : élevé, mais confiné au moteur — pas au routage, pas aux URLs.

### Lot C — Suppression de `grouper_blocs`, `<main>` en grille, retrait du blog

- `services.py:74-157` supprimé ; `views.py:67` et `page.html` simplifiés.
- `<main>` en grille 12 colonnes (§2.5) ; balisage externe de tous les partials réécrit.
- Retrait du blog (§2.6) : `Page.est_blog`, `views.py:64`, `page.html:63-70`,
  `BaseBillet/views.py:292`, `pages_tags.py:46`, les 19 fixtures `blog/` et l'entrée du
  manifeste.

**Risque** : moyen. Le rendu de plusieurs pages change — c'est voulu.

### Lot D — Arbre à N niveaux

`clean()` réécrit (anti-cycle + profondeur ≤ 6 + accueil sans enfants), `parent` en
`PROTECT`, `limit_choices_to` retiré, fil d'Ariane généralisé à la chaîne complète
(`pages_tags.py:90-108` et `page.html:73-86` sont codés en dur pour **un** niveau).
`PageViewSet.partial_update` (`api_v2/views.py:1195-1213`) revalide cycle et profondeur
via `full_clean()`.

**Coût à ne pas sous-estimer : l'admin d'arbre.** Unfold n'a pas de widget d'arbre, et le
drag-drop `ordering_field="position"` (`admin.py:125-126`) est **global**. Minimum
viable : chemin complet dans `list_display`, filtre par racine, et l'erreur d'unicité de
slug affichée avec le chemin du conflit (§2.7). Le futur front est la vraie réponse.

### Lot E — Navigation, sidebar, précédent/suivant, `affichage_nav`

- Navigation déplacée de `BaseBillet/views.py:271-317` vers `pages/services.py`. Un seul
  `Page.objects.filter(publie=True)` — **jamais `.all()`**, sinon les brouillons fuient
  dans la sidebar — puis l'arbre construit en Python (~100 pages : aucune CTE, aucun
  `django-mptt`).
- Prefetch : `views.py:47` fait `page.blocs.all()` sans
  `prefetch_related("images_galerie")` (N+1), `views.py:64` un `page.parent` de plus.
- `get_context` tourne sur **toutes** les vues : sidebar et précédent/suivant ne se
  calculent que sur les vues `pages`.
- Précédent/suivant : parcours en profondeur **restreint au sous-arbre `SIDEBAR`
  courant** — Docusaurus et Zensical calculent la chaîne par sidebar, jamais à travers
  les arbres. **Zéro champ.**
- Sidebar : `partials/sidebar.html`, branche courante ouverte, burger mobile (attention :
  il y a déjà un burger de navbar).
- `affichage_nav` + la matrice §2.8.
- **Des `<a>` normaux d'abord.** `hx-get`/`hx-push-url` sur sidebar et précédent/suivant
  est du polissage : après, pas dans le lot.

### Lot F — Markdown : ancres, TOC, coloration

- Whitelist `id` et `class` dans `nh3.clean()` (§3).
- Refondre la démotion des titres (`pages_tags.py:523-525`).
- Activer `toc` et `codehilite` dans `rendre_markdown` (`pages_tags.py:509-513` —
  aujourd'hui `extra` + `sane_lists` seulement). Pas `admonition` (§2.6).
- **TOC au niveau PAGE**, pas bloc : une page peut porter plusieurs blocs `TEXTE`, une TOC
  par bloc produirait plusieurs TOC et des `id` dupliqués. Rendue en `<details>` en tête
  de contenu.
- La TOC doit survivre à une navigation HTMX (scroll vers l'ancre après le swap).

## 5. Plan de tests

À réécrire (casse assumée) : `test_pages.py`, `test_pages_api.py`,
`test_site_codecommun.py`, `test_blocs_markdown_sous_pages.py`.

À ajouter :

1. Catalogue : les 7 types rendent ; chaque couple (type, affichage) a un gabarit.
2. `AFFICHAGES_PAR_TYPE` : un affichage étranger au type est refusé — en `clean()`, **et**
   en création API, **et** en `PATCH`.
3. Migration : un bloc de chaque ancien type arrive au bon couple ; **`INFOS` +
   `CARTE_LEAFLET` adjacents fusionnent en un seul `LIEU`** ; ne tourne pas sur `public`.
4. Arbre : profondeur 6 acceptée, 7 refusée ; cycle refusé ; accueil avec enfant refusé ;
   `PROTECT` empêche la suppression d'un nœud intermédiaire.
5. Navigation : un cas par ligne de la matrice §2.8.
6. Précédent/suivant : ne traverse pas deux arbres ; ignore `AUCUN` et les brouillons.
7. Markdown : `id` et `class` survivent à `nh3` ; démotion correcte **avec** attributs ;
   TOC unique sur une page à deux blocs `TEXTE`.
8. Rendu : aucun bloc n'en influence un autre (non-régression de la suppression de
   `grouper_blocs`) ; deux blocs `CARTE` consécutifs coulent côte à côte via la grille.

Multi-tenant : app dual-list, toute migration `pages` s'applique **aussi** au schéma
public. Interdiction (piège `ETAT-REPRISE` §8) de faire dépendre une migration `pages`
d'une migration `BaseBillet`.

## 6. Ordre d'exécution

```
A (get_absolute_url)  →  B (catalogue 7 types)  →  C (grouper_blocs + grille + blog)
                                                          ↓
                                      D (arbre N niveaux)  →  E (nav + sidebar)
                                                          ↓
                                                     F (markdown)
```

A est gratuit et indépendant. B est le cœur. C nettoie derrière B. D et E apportent la
navigation documentaire. F finit le contenu.

**Critères de réussite :**
1. Le site codecommun se recharge, se navigue avec sidebar et fil d'Ariane.
2. Ajouter un bloc ne modifie l'apparence d'aucun autre bloc.
3. Le catalogue tient en 7 entrées de modal.

## 7. À reprendre dans le futur chantier front (HTMX + session, via `/djc`)

Constats de la relecture, **hors périmètre ici** mais à ne pas perdre :

- **`position` n'est pas modifiable par l'API** : absent de `CHAMPS_BLOC_AUTORISES`, donc
  `PATCH /blocs/<uuid>/` ne peut pas réordonner un bloc. Sans équivalent, un front n'est
  pas un constructeur de pages. (L'admin Unfold s'en sort par son drag-drop.)
- **Aucun CRUD `ImageGalerie`** : on ne peut ni ajouter, ni supprimer, ni réordonner une
  image d'un bloc existant — seulement passer une liste d'URLs **à la création**. Or la
  fusion `IMAGES` fait de la galerie le mécanisme d'image central.
- **Le contrat de formulaire** : `GET /api/v2/block-types/` (`api_v2/views.py:1221-1231`)
  renvoie `{type, label, fields:[noms]}`. Des noms de champs ne suffisent pas à générer
  un formulaire — il manque le widget, les choices d'`affichage` par type, le label FR,
  `required`, `max_length`, `help_text`. Tout est dans `Model._meta`.
- **`partial_update` ne fait aucun `full_clean()`** — corrigé en §2.3 pour l'affichage,
  mais le constat général reste.

## 8. Points à vérifier avant exécution

- Comptage des blocs existants **par type** sur les tenants de démo (dimensionne la
  migration et la perte `VIDEO_TEXTE`).
- Rendu d'une `ImageGalerie` en pleine largeur : ses variations plafonnent à **480 px**
  (`VARIATIONS_PARTAGE`, `models.py:154-157`) alors que le champ plat `image` monte à
  1920 px (`fhd`). Unifier `IMAGES` sur `ImageGalerie` dégraderait `PLEINE_LARGEUR` — il
  faut probablement étendre les variations d'`ImageGalerie`.
- Comportement du `<main>`-grille à travers un swap HTMX `hx-target="body"`.

## 9. Journal d'avancement

| Date | État | Note |
|---|---|---|
| 2026-07-18 | V1 | Arbre + URLs hiérarchiques, 19 types conservés. Relue en adverse (Fable) ; 5 points incertains vérifiés en exécution |
| 2026-07-18 | V2 | Arbitrage mainteneur : simplicité avant exhaustivité. URLs hiérarchiques coupées, catalogue 19→7, `grouper_blocs` et `est_blog` supprimés |
| 2026-07-18 | V3 | 2e relecture adverse. Corrigés : `TEXTE`=markdown seul, affichages explicites d'`INTEGRATION`, `image_position` et `VIGNETTE_TITRE` conservés, `source` distinct d'`affichage`, validation type×affichage, `PROTECT` sur `parent`, `<main>` en grille, migration 2:1 `LIEU` |
| 2026-07-18 | V4 | Arbitrage mainteneur : **front hors périmètre** (lot G retiré → §7, question session/clé tranchée = session) et **blog retiré du moteur** (→ `NAVBAR_SEUL` supprimé, matrice à 3 valeurs, admonitions sans objet, 19 fixtures en moins) |
| 2026-07-18 | **Lot A fait** | `Page.get_absolute_url()` + 9 appelants (2 de plus que le recensement). Code mort supprimé dans `sitemap.py`. 2 tests ajoutés |
| 2026-07-18 | **Lot B fait** | Catalogue 19 → 7 types, champ `affichage`, `source`, `page_source`. Migrations 0004/0005/0006 dont conversion de données (fusion 2:1 `INFOS`+`CARTE_LEAFLET`). Vérifié au bloc près : 128 → 126 |
| 2026-07-18 | **Lot C fait** | `grouper_blocs` supprimé, `<main>` en grille 12 colonnes (`.tb-flux`), `est_blog` retiré du rendu. 17 gabarits `classic` + 13 `faire_festival` refondus |
| 2026-07-18 | Front vérifié | Audit CSS adverse (Fable) + contrôle Chrome des deux skins contre la prod `fairefestival.fr`. Corrigés : cadrage, `column-gap`, alignement des cartes (image/texte/bouton), **FAQ cassée** (styles préfixés d'un wrapper disparu), marge `auto` qui annulait `stretch` sur un item de grille, 2 sélecteurs morts |
| 2026-07-18 | Composition imbriquée | Affichage `SECTION`/`MEDIA_ET_CARTES` : les sous-cartes vivent dans le JSONField `contenu`. Restitue la section « c'est quoi ? » de la prod (média à gauche, titre + texte + cartes + bouton à droite) **sans réintroduire de groupement implicite** |
