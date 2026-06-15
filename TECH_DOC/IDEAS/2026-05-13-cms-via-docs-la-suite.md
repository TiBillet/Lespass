# CMS Lespass via DOCS la-suite — note d'idée pour session future

> **Date** : 2026-05-13
> **Statut** : Exploration faite, pas encore de code. Décision architecturale prise. À reprendre en `/brainstorming` puis `/writing-plans`.
> **Auteur** : Jonas + Claude (Opus 4.7)
> **Branche** : `main` (Lespass)

---

## 1. Vision

Permettre à chaque tenant Lespass d'avoir un mini-CMS (pages "À propos", "Mentions légales", "Documentation utilisateur", articles de blog, etc.) **édité collaborativement dans DOCS la-suite** (instance `notes.liiib.re` ou autre), et **publié dans le tenant** avec le skin Lespass appliqué.

**Cas d'usage type** :
- Une coopérative culturelle veut une page "Présentation du lieu" éditable par 5 personnes en temps réel, avec sous-pages "Équipe", "Tarifs", "Mentions légales"
- L'arborescence DOCS = arborescence du CMS (1 dossier = 1 sous-menu)
- Mise à jour quasi-temps-réel (cache 5 min → 1h selon TTL)

---

## 2. Décisions architecturales prises (en session 2026-05-13)

### 2.1 Source du contenu : HTML BlockNote (pas Markdown)

**Pourquoi** : la doc officielle "How to use Docs as a simple CMS" recommande explicitement le HTML :

> "HTML is the first-level export format in BlockNote.js. The Markdown export is actually converted from the HTML one. Some (more) information is lost in Markdown compared to HTML."

Endpoint : `GET /api/v1.0/documents/{uuid}/content/?content_format=html`

⚠️ Le champ `content` dans le détail document est **du Yjs CRDT base64**, PAS du HTML. Toujours passer par `/content/`.

### 2.2 Stack transformation : Python natif (PAS rehype)

**Décision** : pipeline équivalent rehype mais 100% Python.
- `lxml.html` : parse + AST + manipulation DOM
- `nh3` : sanitize XSS (Rust, drop-in remplacement bleach, plus rapide)
- ~60 lignes de Python pour 8 "plugins" maison

**Pourquoi pas rehype** : introduire Node.js dans Lespass = +1 runtime à maintenir, +1 chaîne de deps, IPC Python↔Node. Disproportionné pour transformer du HTML quand Python a tout en natif.

**Équivalences** :
| rehype | Python |
|---|---|
| `rehype-parse` | `lxml.html.fragment_fromstring()` |
| `rehype-stringify` | `lxml.html.tostring()` |
| `rehype-sanitize` | `nh3.clean()` |
| Plugin custom | fonction Python qui itère sur le tree |

### 2.3 Réutilisation de Docs2static comme bibliothèque (pas comme pipeline complet)

Le code de `CoopCodeCommun/Docs2static` (v0.6.8, sur PyPI) est **excellent FALC** mais conçu pour générer un site statique externe via Zensical et déployer sur GitHub Pages.

**On garde** :
- `parse_docs_url()` : extraction `(base_url, doc_id)` depuis une URL DOCS
- `fetch_document_content()` : appel `/content/` avec cache SQLite 24h
- `fetch_document_children()`, `fetch_document_descendants()`, `fetch_document_tree()` : récupération de l'arbre, avec gestion du rate-limit 429 et reconstruction côté client via les `path`
- `extract_frontmatter()` : parse du frontmatter YAML-like entre `<p>--- </p>...<p>---</p>`
- `is_draft()` : détection de `brouillon: oui`

**On jette** :
- Tout `zensical_backend.py` (build statique, deploy git, génération sitemap, mentions légales auto)
- La logique de `download_and_replace_images()` (on ne télécharge pas, on rewrite vers les URLs DOCS publiques)
- L'écriture sur disque

→ **Probable** : on ajoute `docs2static` comme dépendance dans `pyproject.toml` (`docs2static>=0.6.8`), on importe uniquement les fonctions utiles depuis `docs2static.main`.

### 2.4 Pas de Zensical, pas de build statique externe

**Décision** : Lespass rend les pages CMS comme n'importe quelle vue Django.

**Pourquoi** :
- Zensical est en **alpha (v0.0.x)** : risque pour la prod
- Build statique = orchestration Celery + volume Docker + nginx side-car + atomic swap → complexité élevée
- Skin Lespass déjà disponible (templates `reunion/`, `faire_festival/`, etc.) : pas besoin de répliquer
- L'arbre nav peut être construit directement depuis l'API DOCS, pas besoin de Zensical pour ça

### 2.5 CSS skin Lespass appliqué via wrapper template Django

Le doc officiel DOCS confirme cette approche :
> "Page-specific CSS is fine to add at render to tweak the style (easier than hacks in the doc)"

Pattern :
```html
<!-- cms_live/templates/cms_live/page.html -->
{% extends base_template %}
{% block extra_head %}
  <link rel="stylesheet" href="{% static 'cms_live/cms-content.css' %}">
{% endblock %}
{% block content %}
<article class="cms-content">
  <h1>{{ page.title }}</h1>
  {{ page.html|safe }}
</article>
{% endblock %}
```

CSS : `cms-content.css` style les balises HTML5 standard via le scope `.cms-content` et utilise les variables Bootstrap/skin Lespass (`var(--bs-primary)`, etc.).

---

## 3. Findings techniques sur DOCS (validation par exploration réelle)

### 3.1 Le HTML BlockNote produit

Balises **HTML5 standard** + bruit BlockNote. Pas de magie, pas de classes propriétaires majeures.

**Le bon** (utilisable direct) :
```html
<h1>Titre</h1>
<h2 data-level="2">Sous-titre</h2>
<p>Paragraphe.</p>
<ul><li><p class="bn-inline-content">Item</p></li></ul>
<ol><li><p class="bn-inline-content">Item ordonné</p></li></ol>
<strong>Gras</strong>, <em>italique</em>, <u>souligné</u>
<a target="_blank" rel="noopener noreferrer nofollow" href="...">Lien</a>
<img src="https://notes.liiib.re/media/.../attachments/...png" alt="..." width="283" ...>
```

**Le bruit** à nettoyer :
- Attributs `data-*` BlockNote : `data-level`, `data-style-type`, `data-value`, `data-editable`, `data-name`, `data-url`, `data-preview-width`
- Classes `bn-inline-content` (et autres `bn-*`)
- Styles inline imposés : `style="color: rgb(...)"`, `style="background-color: rgb(...)"`
- Spans imbriqués vides après strip des `style=` et `data-*`
- `<p></p>` vides entre blocs

### 3.2 Frontmatter — format exact observé

```html
<p>--- </p>     ← espace après le tiret possible
<p>date: 2025-09-04</p>
<p>auteur·ice : Adrienne, Axel, Jonas, Mike</p>
<p>licence : CC-BY-SA</p>
<p>keywords : TiBillet</p>
<p>résumé: Découvrez nos outils d'organisation collective.</p>
<p>brouillon: Non</p>
<p>langue : fr</p>
<p>logo: <a href="...">https://....svg</a></p>
<p>image: <a href="...">https://....jpg</a></p>
<p>---</p>
```

**Piège** : les URLs longues sont auto-wrappées dans `<a>` par BlockNote. Le regex naïf de docs2static `(.+?):\s*(.+?)` peut capturer du HTML au lieu de l'URL. **Parse avec lxml et `text_content()` plutôt que regex**.

**Cas valide** : pas de frontmatter du tout. L'extracteur doit retourner `{}` si pas de pattern trouvé.

### 3.3 Liens internes au CMS — le vrai problème à résoudre

```html
<a target="_blank" rel="noopener noreferrer nofollow"
   href="https://notes.liiib.re/docs/04fe3b58-248f-40eb-a4b0-a1245e53aaf0/">Mon compte</a>
```

DOCS écrit **toujours des URLs absolues** vers son propre domaine, même pour des liens internes (entre pages du même arbre CMS).

**Plugin OBLIGATOIRE** `rewrite_internal_links` :
1. Détecter pattern `notes.liiib.re/docs/{uuid}/` (et autres instances DOCS)
2. Lookup `uuid` dans map locale `uuid → slug-Lespass` (construite depuis l'arbre)
3. Réécrire `href="/cms/{slug}/"` (URL relative Lespass)
4. **Retirer `target="_blank"`** et alléger `rel` (lien interne, pas externe)

Sans ce plugin → l'utilisateur quitte le tenant à chaque clic interne. **Non négociable**.

### 3.4 Images — décision : laisser direct (option A)

Pattern observé : `https://notes.liiib.re/media/{owner_uuid}/attachments/{file_uuid}.{ext}`

URLs **publiques sans auth** pour les docs `computed_link_reach: "public"`.

**Décision actuelle** : laisser `<img src="https://notes.liiib.re/...">` direct dans le HTML servi. Le navigateur fetch chez DOCS.

**Avantages** : zéro stockage, zéro logique, mise à jour automatique si l'image change dans DOCS.

**À surveiller** :
- Si DOCS down, images cassées → fallback à prévoir un jour
- Pas de WebP / resize possible
- Privacy mineur : le navigateur révèle l'IP du visiteur à `notes.liiib.re`

**Bascule vers option B (proxy/cache via Lespass)** si l'un de ces points devient bloquant.

**Alt des images** : DOCS met `alt="versotibilletnfc.png"` (nom de fichier). C'est nul pour accessibility/SEO. La doc officielle dit : "Don't forget to set filenames on uploaded images, they will be used as 'alt' attributes." → **éducation des rédacteurs**, pas notre problème côté code.

### 3.5 Arbre nav — structure utilisable

```json
{
  "id": "372d6d39-...",
  "depth": 2,
  "path": "000005W0000001",   // 7 chars par niveau, préfixe = parent
  "numchild": 8,
  "title": "LES BASES ET VALEURS TIBILLET"
}
```

**182 descendants** pour le doc test, **paginés** (`?page=2`, etc.). Endpoint `/descendants/` (ou `/documents/all/?ancestor={uuid}` plus optimisé). `docs2static.fetch_document_tree()` reconstruit l'arbre côté client via les `path` (préfixe à 7 chars près).

### 3.6 Permissions / abilities

Pour un doc public en lecture :
```json
"computed_link_reach": "public",
"computed_link_role": "reader",
"abilities": {
  "content": true,
  "media_auth": true,
  "cors_proxy": true,
  "descendants": true
}
```

→ **Pas besoin de login Django→DOCS pour les docs publics**. Cas idéal pour démarrer.
→ Cas restreints (docs internes) à gérer plus tard, probablement via clé API DOCS dans `CmsConfig`.

### 3.7 Cas non encore explorés

Pas vérifié sur DOCS réel — à fetcher en début de prochaine session :
- **Tables** : `<table><thead><tbody>` — doc officielle dit "OK", à confirmer
- **Code blocks** : présent dans BlockNote
- **Blockquote** : présent dans BlockNote
- **`<accordion-list>`** : convention custom utilisée par docs2dsfr, syntaxe :
  ```
  <accordion-list>
  * First label
  Contents
  * Second label
  Contents
  </accordion-list>
  ```
  → docs2static a déjà un transform pour cette balise (cf. `process_document` dans `main.py`)

**Custom blocks BlockNote (Divider, CallOut, toggle)** : **pas supportés dans l'export DOCS** ([PR #1213 ouverte](https://github.com/suitenumerique/docs/pull/1213)). On les ignore tant que la PR n'est pas mergée.

---

## 4. Architecture cible

```
DOCS (la-suite, ex: notes.liiib.re)
  │
  ├─ /api/v1.0/documents/{uuid}/descendants/          → arbre (cache 1h)
  └─ /api/v1.0/documents/{uuid}/content/?format=html  → HTML BlockNote (cache TTL)
       │
       ↓
┌───────────────────────────────────────────────────────────────┐
│ Lespass (Django)                                              │
│ Module cms_live/  (TENANT_APPS)                               │
│                                                               │
│ ├ models.py                                                   │
│ │  └ CmsConfig (SingletonModel)                               │
│ │      ├ docs_url (URLField) — URL racine DOCS                │
│ │      ├ tree_cache_json (JSONField) — arbre snapshot         │
│ │      ├ tree_cached_at (DateTimeField)                       │
│ │      ├ webhook_secret (CharField)                           │
│ │      └ auto_sync_enabled (BooleanField)                     │
│ │                                                             │
│ ├ services.py                                                 │
│ │  ├ fetch_and_transform_page(base_url, doc_id) -> dict       │
│ │  ├ refresh_tree_cache(config)                               │
│ │  ├ build_uuid_to_slug_map(tree) -> dict                     │
│ │  └ resolve_path_to_doc_id(config, path) -> uuid|None        │
│ │                                                             │
│ ├ transformers.py  (équivalent rehype pipeline ~60 lignes)    │
│ │  ├ strip_blocknote_data_attrs(tree)                         │
│ │  ├ strip_inline_styles(tree)                                │
│ │  ├ strip_blocknote_classes(tree)                            │
│ │  ├ unwrap_empty_spans(tree)                                 │
│ │  ├ drop_empty_paragraphs(tree)                              │
│ │  ├ rewrite_internal_links(tree, uuid_to_slug)               │
│ │  ├ enhance_images(tree)  # lazy loading, etc.               │
│ │  ├ add_anchor_ids_to_headings(tree)                         │
│ │  └ convert_accordion_list(tree)  # <accordion-list>->details│
│ │                                                             │
│ ├ views.py                                                    │
│ │  └ CmsViewSet.page(request, path)                           │
│ │                                                             │
│ ├ urls.py                                                     │
│ │  ├ /cms/                  → root page                       │
│ │  ├ /cms/<path:path>/      → sub-pages                       │
│ │  └ /cms-webhook/          → POST signé HMAC (option future) │
│ │                                                             │
│ ├ admin.py                                                    │
│ │  └ CmsConfigAdmin (Unfold) — config + bouton "Sync now"     │
│ │                                                             │
│ ├ templates/cms_live/                                         │
│ │  ├ page.html              extends base_template             │
│ │  └ partials/nav_tree.html sidebar arborescence              │
│ │                                                             │
│ └ static/cms_live/cms-content.css                             │
│                                                               │
│ Cache Django : 5 min HTML page / 1h arbre nav                 │
└───────────────────────────────────────────────────────────────┘
```

---

## 5. Pipeline transformer — pseudocode

```python
# cms_live/services.py
from docs2static.main import (
    parse_docs_url,
    fetch_document_content,
    fetch_document_tree,
    extract_frontmatter,
)
from lxml import html
import nh3
from .transformers import (
    strip_blocknote_data_attrs,
    strip_inline_styles,
    strip_blocknote_classes,
    unwrap_empty_spans,
    drop_empty_paragraphs,
    rewrite_internal_links,
    enhance_images,
    add_anchor_ids_to_headings,
    convert_accordion_list,
)

def fetch_and_transform_page(base_url, doc_id, uuid_to_slug):
    """Fetch HTML d'un doc DOCS, extract frontmatter, transform, sanitize."""
    data = fetch_document_content(base_url, doc_id, "html")
    raw_html = data.get("content", "")
    frontmatter, body = extract_frontmatter(raw_html)

    # Parse en AST
    tree = html.fragment_fromstring(body, create_parent="div")

    # Plugins maison (équivalent rehype .use())
    strip_blocknote_data_attrs(tree)
    strip_inline_styles(tree)
    strip_blocknote_classes(tree)
    unwrap_empty_spans(tree)
    drop_empty_paragraphs(tree)
    rewrite_internal_links(tree, uuid_to_slug)
    enhance_images(tree)
    add_anchor_ids_to_headings(tree)
    convert_accordion_list(tree)

    cleaned_html = html.tostring(tree, encoding="unicode", method="html")

    # Sanitize XSS final
    safe_html = nh3.clean(
        cleaned_html,
        tags={"h1","h2","h3","h4","h5","h6","p","br","hr",
              "ul","ol","li","strong","em","b","i","u","s","code",
              "blockquote","pre","a","img","table","thead","tbody",
              "tr","th","td","div","span","figure","figcaption",
              "details","summary"},
        attributes={
            "a": {"href","rel","title"},
            "img": {"src","alt","loading","width","height"},
            "*": {"class","id"},
        },
    )

    return {
        "title": data.get("title", ""),
        "frontmatter": frontmatter,
        "html": safe_html,
    }
```

---

## 6. Points ouverts à trancher en début de prochaine session

| Question | Options | Notes |
|---|---|---|
| Activation par tenant | `Configuration.module_cms` (Bool) comme le Groupware existant | Cohérent avec pattern phase -1 |
| TTL cache HTML | 5 min / 15 min / 1h ? | Plus court = plus de hits DOCS, plus long = délai d'actualisation |
| TTL cache arbre nav | 1h ? | Change rarement, OK 1h |
| Sync push (webhook DOCS) ou pull (Celery periodic) ? | la-suite expose-t-elle des webhooks ? À vérifier dans la doc API | Sinon Celery toutes les 10-15 min |
| Multi-tenant : `docs_url` par tenant ? | Oui (SingletonModel `CmsConfig` par tenant) | Naturel avec django-tenants |
| Slug par doc : depuis quel champ DOCS ? | Title slugifié, OU `path` slug du frontmatter | Permettre les 2 : frontmatter override |
| Profondeur max de l'arbre affichée en sidebar | 3 niveaux ? Infini ? | Test UX nécessaire |
| Lien navbar "Documentation" / "Pages" / "CMS" / "Blog" | Personnalisable par tenant (champ texte sur `CmsConfig`) | Évite de figer le terme |
| Sitemap : intégrer URLs `/cms/...` au sitemap global ? | Oui, génération depuis l'arbre cache | 1 méthode `CmsSitemap` dans `BaseBillet/sitemap.py` |
| JSON-LD : ajouter `WebPage` / `Article` schema sur pages CMS ? | Oui, depuis frontmatter (`title`, `summary`, `date`, `auteur·ice`) | Aligné avec le module `seo/` |
| Images : option A (direct) confirmée pour démarrer ? | Oui | Plan de bascule B si besoin |

---

## 7. Cas non explorés à valider en début de prochaine session

À tester en fetchant des docs DOCS réels qui contiennent :
- [ ] **Tableau** : HTML produit, attributs BlockNote, comportement responsive
- [ ] **Blockquote** : balisage exact
- [ ] **Code block** : balise utilisée (`<pre><code>` ?), classes pour syntax highlight ?
- [ ] **`<accordion-list>`** : syntaxe custom, comment c'est exporté

URL test confirmée OK : `https://notes.liiib.re/docs/a65fc672-d634-4f49-bec3-212439df49eb/` (Doc TiBillet, 182 descendants)

---

## 8. Plan d'attaque pour la prochaine session

### Étape A (~30 min) : valider les cas non explorés
- Fetch 3-4 docs DOCS avec table / code / blockquote / accordion-list
- Compléter la matrice de findings
- Mettre à jour ce document

### Étape B (`/brainstorming`) : finaliser la spec
- Trancher les questions ouvertes (section 6)
- Confirmer pattern URLs (`/cms/<path>/`)
- Confirmer permissions tenant (admin/public/etc.)
- Spec écrite : `TECH_DOC/SESSIONS/CMS_LIVE/00-spec.md`

### Étape C (`/writing-plans`) : plan d'implémentation
- Découpage en sous-tâches < 1h chacune
- TDD avec tests d'extraction, transform, sanitize
- Plan écrit : `docs/superpowers/plans/YYYY-MM-DD-cms-live.md`

### Étape D : implémentation en `/subagent-driven-development`
- Module `cms_live/` complet
- Tests pytest + Playwright
- Doc utilisateur (comment configurer son DOCS, frontmatter, etc.)

**Effort total estimé** : 4-5 jours développeur en exécution séquentielle.

---

## 9. Références et ressources

### Code source à étudier
- **Docs2static** : `https://github.com/CoopCodeCommun/Docs2static` (v0.6.8 PyPI)
  - `docs2static/main.py` : fetch, parse arbre, extract frontmatter — **réutilisable**
  - `docs2static/zensical_backend.py` : build statique — **à ignorer**
- **docs2dsfr** (Sylvain Zimmer, Node.js) : `https://github.com/suitenumerique/st-home/tree/main/src/lib/docs2dsfr` — référence d'inspiration (pas à porter)

### Documentation officielle DOCS
- **Doc principale "How to use Docs as a simple CMS"** : `https://docs.suite.anct.gouv.fr/docs/0b65cc5b-2d72-408a-b5c1-0ff8d2a7a479/`
- **PR custom blocks export** : `https://github.com/suitenumerique/docs/pull/1213`
- **Issue BlockNote toggleable** : `https://github.com/TypeCellOS/BlockNote/issues/1936`

### Doc test riche utilisée pour l'exploration
- **Doc' TiBillet** (racine) : `https://notes.liiib.re/docs/a65fc672-d634-4f49-bec3-212439df49eb/`
- **Ma carte TiBillet (Pass)** (page enfant avec image inline) : `https://notes.liiib.re/docs/8aa90cc7-6c03-40ff-80d2-1f54d048729f/`

### Atoms Atomic référencés
- `7b252589-cc80-44d4-a86c-28b8b59aa51c` — rehype README (HTML processor unifiedjs)
- `724f8234-cd91-404f-ba1a-fa93cb5f9b19` — How to use Docs as a simple CMS (officiel la-suite)
- `5108249e-f9f2-4ee8-8f77-b7f7f405d076` — Zensical roadmap
- `20c8eb51-03a5-4aa7-a201-ad9d04a365ac` — Docs2static README

### Outils Python à étudier en avance
- **`lxml.html`** : parser HTML5 + manipulation AST — `https://lxml.de/lxmlhtml.html`
- **`nh3`** : sanitize Rust (drop-in remplacement bleach) — `https://github.com/messense/nh3`
- **`requests-cache`** : déjà utilisé par docs2static, cache SQLite 24h — `https://requests-cache.readthedocs.io/`

---

## 10. Ce qu'on n'a PAS retenu (et pourquoi)

| Approche écartée | Raison |
|---|---|
| Iframe DOCS dans Lespass | SEO ❌, accessibility ❌, mobile UX ❌ |
| Build statique Zensical + nginx side-car | Zensical alpha (v0.0.x), orchestration Celery+volumes lourde, skin différent du tenant |
| Wrapper Django qui extrait `<main>` du HTML statique zensical build | Travail Celery+stockage pour rien si on peut fetch DOCS direct |
| rehype (Node.js) | +1 runtime à maintenir, IPC, deps Node — disproportionné, `lxml`+`nh3` font le même boulot |
| Markdown comme source DOCS | Lossy (export converti depuis HTML BlockNote, perte d'info) — confirmé par doc officielle |
| Modèle Django `Page` avec `content_md` stocké en base | Pas FALC pour ce cas : la source autoritaire reste DOCS, dupliquer en base = sync à maintenir |
| `django-grapesjs` | Abandonné depuis 2022, déjà documenté dans atom existant |

---

## 11. Risques identifiés

| Risque | Impact | Mitigation |
|---|---|---|
| DOCS down → CMS Lespass HS | Fort | Cache long (1h+) + fallback "soft expire" servant le cache même expiré si DOCS injoignable |
| BlockNote change son HTML output | Moyen | Tests pytest sur snapshots HTML — détection rapide |
| XSS via contenu DOCS malveillant | Critique | `nh3.clean()` en bout de pipeline, tests dédiés |
| Path traversal via slugs DOCS | Moyen | Sanitize slug + lookup uniquement via map cache contrôlée |
| Performances : 182 docs à parser à chaque build | Moyen | Cache 1h sur arbre, fetch HTML à la demande (pas batch) |
| Lien interne mal réécrit → user quitte tenant | Moyen | Tests pytest dédiés sur `rewrite_internal_links` |
| Auteur DOCS oublie nommer ses images → alt="IMG_4521.jpg" | Faible | Documentation utilisateur dans admin Unfold |

---

## 12. Note pour Claude au moment de reprendre

**Lorsque tu rouvres ce document** :

1. Relis attentivement les sections 2 (décisions), 3 (findings), 4 (architecture), 6 (questions ouvertes)
2. Si la décision change (ex: on veut finalement du build statique), met à jour ce document en premier avant d'écrire la spec
3. Ne pas reproposer rehype / zensical / Markdown-source / iframe — c'est déjà tranché
4. Avant de coder, **fetch un doc DOCS réel pour valider** que le HTML BlockNote n'a pas changé depuis l'exploration
5. Lancer `/brainstorming` pour la spec puis `/writing-plans` pour le plan, conformément à `superpowers:using-superpowers`

**Pas de code TiBillet en mode exploration** — règle du user en session 2026-05-13.
