# SEO de l'accueil (titre, accueil vide, JSON-LD) et compression gzip / Home SEO (title, empty home, JSON-LD) and gzip compression

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- **Titre de l'accueil** (skins V2 et classic) : « nom du lieu — ville » au lieu de « Accueil | nom du lieu ». Le suffixe « | nom » des shells passe dans un bloc `title_suffixe`, vidé par l'accueil.
- **Meta description « None »** corrigée : le filtre `default` passe AVANT `striptags` (accueils V2/classic, réseau classic) ; les agendas classic/faire_festival n'ajoutent plus « - None ».
- **Accueil vide** (ni événement, ni image, ni description écrite par le lieu) : `noindex, follow`, et `/` sort du sitemap du lieu. Règle unique : `TiBillet/seo_indexing.py:accueil_par_defaut_est_vide`.
- **JSON-LD Organization** construit en Python (`{% jsonld_organisation %}`, `pages_tags.py`) dans les trois shells : plus d'entités HTML ni de JSON cassé ; `logo` = logo du lieu ; `sameAs` = site web + réseaux ; adresse sans champ vide.
- **Préchargement** de l'image du hero sur l'accueil V2.
- **gzip** dans nginx de prod (`nginx_prod/lespass_prod.conf`), y compris les pages HTML (`gzip_proxied any`).

/ Home title "venue — city"; "None" meta description fixed; empty homes are noindex and out of the sitemap; venue JSON-LD built in Python; hero preload; gzip in production nginx.

**Pourquoi / Why :** Audit SEO du 2026-10-12 (`TECH_DOC/SESSIONS/SEO/AUDIT-ACCUEIL-V2/RECAP.md`, chantiers 10 et 12).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/seo_indexing.py` | `accueil_par_defaut_est_vide()` + `DEBUT_DU_TEXTE_DE_BIENVENUE` |
| `BaseBillet/views.py` (`index`) | contexte `accueil_est_vide` |
| `BaseBillet/sitemap.py` (`StaticViewSitemap`) | `/` seulement si accueil CMS publié ou accueil non vide |
| `pages/templates/pages/{V2,classic}/vues/accueil.html` | titre, `title_suffixe`, robots, ordre des filtres ; préchargement du hero (V2) |
| `pages/templates/pages/{V2,classic}/shell.html` + `headless.html` | bloc `title_suffixe` |
| `pages/templates/pages/{V2,classic,faire_festival}/shell.html` | `{% jsonld_organisation %}` remplace le JSON écrit à la main |
| `pages/templates/pages/classic/vues/reseau.html`, `{classic,faire_festival}/vues/agenda.html` | bug « None » |
| `pages/templatetags/pages_tags.py` | tag `jsonld_organisation` |
| `nginx_prod/lespass_prod.conf` | bloc `gzip` |
| `tests/pytest/test_seo_accueil.py` | 12 tests (vérifiés par mutation) |

---

## Comment tester (a la main) / Manual test
### Accueil (en prod après déploiement)
1. `curl -s https://la-filature.tibillet.coop/ | grep -E '<title>|name="description"|preload'` → `<title>La Filature — Villeurbanne</title>`, une description, le préchargement du hero.
2. Un lieu sans description courte : la description vaut le nom du lieu, jamais « None ».
3. Un lieu vide (texte « Bienvenue dans votre nouvel espace ! », sans image ni événement) : `<meta name="robots" content="noindex, follow">` et `/` absent de `https://<lieu>/sitemap.xml`.
4. JSON-LD : coller l'accueil dans https://validator.schema.org/ → Organization et WebSite valides, sans `&#x27;`.

### gzip
1. Déployer `nginx_prod/lespass_prod.conf`, puis `docker exec lespass_nginx nginx -t && docker exec lespass_nginx nginx -s reload`.
2. `curl -s -o /dev/null -D - -H 'Accept-Encoding: gzip' https://la-filature.tibillet.coop/ | grep -i content-encoding` → `Content-Encoding: gzip` (page HTML).
3. Même chose sur `/static/V2/css/V2.css` (140 Ko → ~41 Ko, mesuré en local).

`docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_seo_accueil.py -q`
