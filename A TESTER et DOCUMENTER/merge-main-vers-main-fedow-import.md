# Merge `main` → `main-fedow-import`

Reunion du chantier **Newsletter / Ghost** (branche `main`) et du chantier **Fedow V2 /
LaBoutik / Kiosk / Pages** (branche `main-fedow-import`). 8 commits de `main` entrent dans
une branche qui en avait 90 d'avance.

## Ce qui a ete fait

### Les 8 conflits

| Fichier | Nature du conflit | Resolution |
|---|---|---|
| `TiBillet/settings.py` | Les deux branches ajoutent des apps au meme endroit | Union : apps fedow (`laboutik`, `kiosk`, `inventaire`, `controlvanne`, `pages`) **et** `newsletter` |
| `BaseBillet/models.py` | Deux `BooleanField` ajoutes au meme endroit de `Configuration` | Union : `module_pages` **et** `module_newsletter` |
| `Administration/admin/dashboard.py` | Carte de module + entree de menu | Union des deux cartes. **L'ancienne entree « Ghost » d'« Outils externes » est supprimee** : `main` l'a deplacee dans la nouvelle section « Newsletter ». La garder aurait fait un doublon. |
| `Administration/admin_tenant.py` | Import a effet de bord | Un seul import, a la position de `main` (apres `admin.site`, ce qui evite l'import circulaire), avec son `# noqa: F401`, **etendu aux 4 modules** (`products`, `prices`, `laboutik`, `inventaire`) + `import pages.admin` |
| `BaseBillet/views.py` | Chemins de templates divergents | Chemins de `main-fedow-import` (`commun/adhesion/`) + le `except Exception:` de `main` (le `e` n'etait pas utilise) |
| `CHANGELOG.md` | Chaque branche ajoute ses entrees en tete | Reconstruit depuis les 3 versions git. **114 entrees = 71 (base) + 4 (`main`) + 39 (`main-fedow-import`)** — aucune perdue |
| `locale/{fr,en}/LC_MESSAGES/django.po` | — | Ecrases par la version de `main`. **A regenerer** (voir plus bas) |

### Les deux pieges que git ne signalait pas

**1. Graphe de migrations casse.** `main` apporte `0221_configuration_module_newsletter`
(branchee sur `0220_…idempotency_key`), alors que `main-fedow-import` est rendue a `0228`.
Deux feuilles concurrentes → `Conflicting migrations detected`, Django refuse de demarrer.
Corrige par `makemigrations --merge` → **`0229_merge_20260714_1045.py`** (vide, elle ne fait
que reunir les deux feuilles).

**2. Template orphelin dans une arborescence morte.** `main-fedow-import` a reorganise les
templates (`reunion/` → `commun/` + `fonctionnel/`). `main`, restee sur l'ancienne arbo, y a
**ajoute** `reunion/partials/error_useful_links.html`. Git l'a laisse la — **seul survivant
d'un dossier par ailleurs supprime** — et `404.html` / `500.html`, **fusionnes sans conflit
donc en silence**, continuaient de l'inclure depuis ce chemin mort.
Deplace vers `commun/partials/error_useful_links.html` (l'emplacement canonique post-refactor,
avec `field_errors.html` et `picture.html`), et les deux `{% include %}` repointes.

### Un test rouge, corrige

Le merge a **revele** (sans le causer) une fuite de schema entre deux fichiers de test qui ne
s'etaient jamais croises :

- `test_federation_tags_semantique.py` (de `main`) colle la connexion sur `lespass` via un
  `DjangoClient(HTTP_HOST=…)` — le middleware django-tenants ne la decolle jamais.
- `test_fedow_core.py` (de `main-fedow-import`) teste des SHARED_APPS et **suppose** `public`.
- L'ordre alphabetique les met cote a cote (« fede… » < « fedo… ») → **8 tests rouges**.

Sur `main`, le pollueur n'avait **aucune victime** (`test_fedow_core.py` n'y existe pas) : le
bug etait invisible des deux cotes.
Corrige dans `test_fedow_core.py` par une fixture autouse **module-scoped** qui pose `public`
en **setup** (jamais en teardown — cf. `tests/PIEGES.md` 12.5.bis). Piege documente en fin de
`tests/PIEGES.md`.

## Etat des tests

Suite complete `tests/pytest/` : **834 passed, 0 echec** (`0:04:02`).

Le premier run, lance **a froid** (zero schema `test_*` residuel apres le flush), donnait
**826 passed + 3 failed + 5 errors** — soit les memes 834 tests. Les 8 rouges etaient tous dans
`test_fedow_core.py` (fuite de schema decrite plus haut) et sont eteints. Le run de validation,
lui, a beneficie des schemas `test_*` crees par le premier : le correctif est donc aussi valide
par une **reproduction deterministe** a deux fichiers (`test_federation_tags_semantique.py` +
`test_fedow_core.py` : rouge avant, vert apres).

## A faire par le mainteneur

### 1. i18n — a regenerer

Les deux `.po` ont ete ecrases par la version de `main` (sur ta consigne). Ils ne contiennent
donc **pas** les chaines de `main-fedow-import`. Le workflow i18n est a relancer :

```bash
# (cote mainteneur — jamais lance par l'assistant)
makemessages puis compilemessages
```

### 2. Au deploiement — purger le cache, imperativement

`module_newsletter` et `module_pages` sont deux nouveaux champs sur un `SingletonModel`
(`Configuration`). Sans purge, django-solo ressert un objet **serialise par l'ancien code**,
sans ces attributs — et comme la sidebar les lit **sur chaque page d'admin**, l'admin
**entier** repond 500 :

```
AttributeError: 'Configuration' object has no attribute 'module_newsletter'
```

```bash
docker exec lespass_django poetry run python manage.py shell -c \
  "from django.core.cache import cache; cache.clear(); print('cache purge')"
```

(Deja fait en dev pendant le merge. **A refaire a chaque deploiement.**)

### 3. Migration

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
```

Deja applique en dev. `module_newsletter` est a `False` partout : aucun tenant n'est impacte
tant qu'un superadmin ne l'active pas.

## Tests manuels a realiser

### Test 1 — L'admin repond (le canari du merge)
1. Aller sur `https://lespass.tibillet.localhost/admin/`.
2. **Attendu :** la page s'affiche. Un **500** avec `'Configuration' object has no attribute
   'module_newsletter'` signifie que le cache n'a pas ete purge (voir ci-dessus).
3. Verifier que la sidebar affiche bien les groupes des **deux** chantiers (LaBoutik,
   Inventaire, Tireuses, Pages… **et** Newsletter si le module est actif).

### Test 2 — Les deux modules coexistent dans le dashboard
1. Dashboard admin → cartes des modules.
2. **Attendu :** la carte **« Pages / site web »** (fedow) **et** la carte **« Newsletter »**
   (main) sont toutes les deux presentes.
3. Cliquer « Newsletter » en tant que **gestionnaire non-superadmin** → la modale de contact
   s'affiche (pas un refus sec).

### Test 3 — La config Ghost n'est pas en double
1. Sidebar admin → chercher « Ghost ».
2. **Attendu :** l'entree **« Serveur Ghost »** apparait **une seule fois**, dans le groupe
   **Newsletter** (visible seulement si le module est actif). Elle ne doit **plus** figurer
   dans « Outils externes », a cote de Webhook et Brevo.

### Test 4 — Les pages d'erreur et leur bloc de liens
1. Visiter une URL inexistante, ex. `https://lespass.tibillet.localhost/nawak-qui-nexiste-pas/`.
2. **Attendu :** la page 404 s'affiche, avec le bloc **« Decouvrir TiBillet »** et ses 4 liens
   (Presentation, Documentation, Creer son espace, Contribuer).
3. C'est le test du template deplace : un `TemplateDoesNotExist` sur
   `commun/partials/error_useful_links.html` signalerait un include mal repointe.
4. Idem sur un skin different (`faire_festival`) — la page d'erreur est skin-aware
   (`{% extends base_template %}`).

### Test 5 — L'admin Product / Price repond (piege `admin.E039`)
1. Aller sur `/admin/BaseBillet/product/` et `/admin/laboutik/…`.
2. **Attendu :** les changelists s'affichent. Une erreur `admin.E039` au demarrage
   signifierait que l'import a effet de bord d'`admin_tenant.py` a ete casse.
3. `manage.py check` doit renvoyer **« System check identified no issues »**.

## Compatibilite

- **Aucune donnee impactee.** La migration `0229` est vide ; `0221` ajoute un booleen a `False`.
- L'arborescence `BaseBillet/templates/reunion/` **n'existe plus** : c'est l'etat cible de
  `main-fedow-import`. Aucun template `reunion/` n'est plus resolu nulle part (verifie).
- Les references a `reunion/` qui subsistent sont de la **documentation** (`TECH_DOC/`,
  `PLANS/`, commentaires) — sans effet a l'execution.
