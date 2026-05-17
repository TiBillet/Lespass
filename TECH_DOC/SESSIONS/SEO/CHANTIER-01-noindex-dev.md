# CHANTIER 01 — Desindexer les instances DEV / DEMO / TEST

## Statut

- **Phase** : Implementation terminee, en attente de test manuel et deploiement
- **Priorite** : Urgent (perte de marque sur filaos.re et devtib.fr qui
  apparaissent dans Google/Bing alors qu'ils ne devraient pas)
- **Estime** : ~2h de code + ecriture des tests (realise)
- **Tests automatises** : 11 / 11 verts (`tests/pytest/test_seo_indexing.py`)

## 1. Contexte

Plusieurs instances Lespass sont publiquement indexees sur Google et
Bing :

- `filaos.re` — instance de dev La Reunion, devant le tenant principal
  dans la SERP sur certaines requetes "TiBillet"
- `devtib.fr` — instance de dev/test, premiere position sur Bing

Ces sites tournent avec `DEBUG=1`, `TEST=1`, `DEMO=1`, `STRIPE_TEST=1`
dans leur `.env`. Aucun signal SEO ne les protege actuellement : leurs
2 vues `robots_txt` (une dans `seo/views_common.py`, une dans
`BaseBillet/views_robots.py`) servent systematiquement
`User-agent: * / Allow: /`.

Objectif : empecher les bots d'indexer toute instance non-prod, et
pousser Google a desindexer celles deja en SERP.

## 2. Regle metier

Une reponse HTTP est marquee `noindex, nofollow` quand **au moins un
flag d'environnement** est a `1` :

- `DEBUG=1`
- `TEST=1`
- `DEMO=1`
- `STRIPE_TEST=1`

Sinon : indexation normale.

**Pourquoi pas de verification du host** (DOMAIN / ADDITIONAL_DOMAINS) :
Django bloque deja les hosts inconnus via `ALLOWED_HOSTS` avant que
nos vues s'executent. En pratique, une instance non-prod a TOUJOURS
au moins un des 4 flags actif (cf. `.env` des instances filaos.re et
devtib.fr). Ajouter une regle host n'aurait couvert qu'un cas tordu
ou un host non-prod aurait ete autorise dans `ALLOWED_HOSTS` ET aurait
oublie tous les flags dev — quasi-impossible en pratique. Decision
prise par Jonas le 2026-05-17 : on garde la regle simple, FALC.

## 3. Pourquoi pas de middleware

Un `X-Robots-Tag: noindex` HTTP (via middleware) et un
`<meta name="robots" content="noindex">` HTML font le **meme job** aux
yeux de Google. Pas besoin des deux.

Comme Lespass sert quasi exclusivement du HTML (pas d'API JSON
indexable), le meta tag dans les bases templates suffit. On evite un
middleware = moins de magie, plus FALC, et la logique reste visible
dans chaque template / vue qui l'utilise.

Defense en profondeur quand meme :
- `robots.txt` qui dit `Disallow: /` (empeche le crawl)
- `<meta name="robots">` dans les bases templates (empeche
  l'indexation des pages deja decouvertes par lien)

## 4. Design

### 4.1 Helper pur — `TiBillet/seo_indexing.py` (nouveau fichier)

Une fonction `should_noindex() -> bool` (sans argument) qui verifie
les 4 flags d'environnement. Pure, testable seule.

```python
"""
Helper pour decider si une reponse doit etre marquee noindex.
/ Helper to decide if a response must be marked noindex.

LOCALISATION : TiBillet/seo_indexing.py
"""

import os
from django.conf import settings


def _get_allowed_seo_hosts():
    """
    Liste des hostnames consideres comme "prod" et indexables.
    Lit DOMAIN + ADDITIONAL_DOMAINS depuis l'environnement.
    / List of hostnames considered "prod" and indexable.
    Reads DOMAIN + ADDITIONAL_DOMAINS from the environment.

    On ne lit PAS settings.ALLOWED_HOSTS : il contient des entrees
    techniques (localhost, 127.0.0.1) qu'on ne veut pas exposer au
    referencement.
    """
    hosts = []
    main_domain = os.environ.get('DOMAIN', '').strip().lower()
    if main_domain:
        hosts.append(main_domain)

    additional = os.environ.get('ADDITIONAL_DOMAINS', '')
    for domain in additional.split(','):
        domain = domain.strip().lower()
        if domain:
            hosts.append(domain)
    return hosts


def _host_matches_whitelist(host, allowed_hosts):
    """
    Verifie si host == un domaine autorise, ou est un sous-domaine
    d'un domaine autorise.
    / Returns True if host equals or is a subdomain of an allowed host.
    """
    for allowed in allowed_hosts:
        if host == allowed:
            return True
        # Le "." prefixe evite "tibillet.coop.fake.com" qui matcherait
        # par endswith simple. On veut un VRAI sous-domaine.
        # / Leading "." prevents "tibillet.coop.fake.com" from matching.
        if host.endswith('.' + allowed):
            return True
    return False


def should_noindex(request):
    """
    True si la reponse doit etre marquee `noindex, nofollow`.
    / True if the response must be marked `noindex, nofollow`.

    LOCALISATION : TiBillet/seo_indexing.py

    Cas qui declenchent le noindex :
    1. Au moins un flag d'env a 1 : DEBUG, TEST, DEMO, STRIPE_TEST.
    2. Le host courant n'est pas dans la whitelist
       (DOMAIN ou ADDITIONAL_DOMAINS, sous-domaines inclus).
    """
    # Cas 1 : flags dev/test/demo
    # / Case 1: dev/test/demo flags
    if getattr(settings, 'DEBUG', False):
        return True
    if os.environ.get('TEST') == '1':
        return True
    if os.environ.get('DEMO') == '1':
        return True
    if os.environ.get('STRIPE_TEST') == '1':
        return True

    # Cas 2 : host hors whitelist
    # / Case 2: host outside whitelist
    host_with_maybe_port = request.get_host()
    host = host_with_maybe_port.split(':')[0].lower()

    allowed_hosts = _get_allowed_seo_hosts()
    if not allowed_hosts:
        # Pas de DOMAIN configure -> conservatif : noindex
        # / No DOMAIN configured -> conservative: noindex
        return True

    if not _host_matches_whitelist(host, allowed_hosts):
        return True

    return False
```

### 4.2 Vues `robots.txt` — 2 fichiers a modifier

#### `seo/views_common.py:robots_txt`

```python
def robots_txt(request):
    from TiBillet.seo_indexing import should_noindex

    if should_noindex(request):
        # Instance non indexable : on bloque le crawl entier.
        # / Non-indexable instance: block all crawling.
        return HttpResponse(
            "User-agent: *\nDisallow: /\n",
            content_type="text/plain",
        )

    # Instance prod : crawl autorise + reference du sitemap
    # / Prod instance: crawl allowed + sitemap reference
    domain = request.get_host()
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    robots_content = (
        f"User-agent: *\n"
        f"Allow: /\n"
        f"\n"
        f"Sitemap: {domain}/sitemap.xml\n"
    )
    return HttpResponse(robots_content, content_type="text/plain")
```

#### `BaseBillet/views_robots.py:robots_txt`

Meme logique, meme appel a `should_noindex(request)`.

### 4.3 Context processor — `TiBillet/seo_indexing.py` (meme fichier)

On ajoute une petite fonction dans le meme module :

```python
def noindex_context(request):
    """
    Context processor : expose `noindex_seo: bool` a tous les templates.
    / Context processor: exposes `noindex_seo: bool` to all templates.

    A enregistrer dans settings.TEMPLATES.OPTIONS.context_processors.
    """
    return {'noindex_seo': should_noindex(request)}
```

Enregistrement dans `TiBillet/settings.py` (TEMPLATES section,
`context_processors` list — **touche settings, signaler au mainteneur
avant le commit**) :

```python
'context_processors': [
    'django.template.context_processors.debug',
    'django.template.context_processors.request',
    'django.contrib.auth.context_processors.auth',
    'django.contrib.messages.context_processors.messages',
    'TiBillet.seo_indexing.noindex_context',  # ← AJOUT
],
```

### 4.4 Meta tag dans les bases templates

Etat actuel (verifie a l'ecriture de la spec) :

| Template | Balise `<meta name="robots">` actuelle |
|---|---|
| `seo/templates/seo/base.html` | OUI — `{% block meta_robots %}index, follow{% endblock %}` |
| `BaseBillet/templates/reunion/base.html` | OUI — meme pattern `index, follow` par defaut |
| `BaseBillet/templates/faire_festival/base.html` | OUI — meme pattern `index, follow` par defaut |
| `BaseBillet/templates/htmx/base.html` | **NON** — pas de meta robots du tout |

**Pour les 3 qui ont deja un block `meta_robots`** : on modifie le
default de "index, follow" pour qu'il devienne "noindex, nofollow"
quand `noindex_seo` est vrai. Les overrides page-specifiques (ex.
explorer.html qui surcharge ce block en noindex) restent prioritaires
par construction de `{% block %}` Django.

```html
<meta name="robots" content="{% block meta_robots %}{% if noindex_seo %}noindex, nofollow{% else %}index, follow{% endif %}{% endblock %}">
```

**Pour `htmx/base.html`** : on ajoute la meme ligne (creation du bloc
`meta_robots`). Note : ce template est de toute facon a enrichir
serieusement au chantier 02 (meta description, OG, Twitter Card,
canonical, JSON-LD) — la ligne ajoutee ici est une premiere brique.

### 4.5 Tests

Nouveau fichier `tests/pytest/test_seo_indexing.py` avec 5 tests
unitaires sur `should_noindex` :

| # | Nom | Cas teste |
|---|-----|-----------|
| 1 | `test_should_noindex_quand_debug_est_actif` | DEBUG=True dans settings -> True |
| 2 | `test_should_noindex_quand_env_test_egal_1` | os.environ TEST=1 -> True |
| 3 | `test_should_noindex_quand_env_demo_egal_1` | os.environ DEMO=1 -> True |
| 4 | `test_should_noindex_quand_env_stripe_test_egal_1` | os.environ STRIPE_TEST=1 -> True |
| 5 | `test_should_indexer_quand_tous_les_flags_sont_a_zero` | Tous flags 0 -> False (indexable) |

Patron de test (FALC, bilingue, monkeypatch env) :

```python
def test_should_noindex_quand_env_demo_egal_1(monkeypatch, rf):
    # On force DEBUG a False pour isoler le flag DEMO
    # / Force DEBUG to False to isolate the DEMO flag
    monkeypatch.setattr(settings, 'DEBUG', False)
    monkeypatch.setenv('TEST', '0')
    monkeypatch.setenv('DEMO', '1')
    monkeypatch.setenv('STRIPE_TEST', '0')
    monkeypatch.setenv('DOMAIN', 'tibillet.coop')

    request = rf.get('/', HTTP_HOST='tibillet.coop')
    assert should_noindex(request) is True
```

Test E2E (optionnel, pour le chantier 02) : verifier que la SERP
Google ne contient plus filaos.re apres 2 semaines via Search Console.

## 5. Fichiers modifies / crees

| Action | Fichier | Description |
|---|---|---|
| Nouveau | `TiBillet/seo_indexing.py` | Helper `should_noindex` + context processor |
| Modifie | `seo/views_common.py` (`robots_txt`) | Branche sur `should_noindex` |
| Modifie | `BaseBillet/views_robots.py` (`robots_txt`) | Branche sur `should_noindex` |
| Modifie | `TiBillet/settings.py` (TEMPLATES) | +1 ligne context_processor (**toucher settings, signaler**) |
| Modifie | `seo/templates/seo/base.html` | Etendre logique `<meta name="robots">` |
| Modifie | `BaseBillet/templates/htmx/base.html` | +bloc `<meta name="robots">` conditionnel |
| Modifie | `BaseBillet/templates/reunion/base.html` | +bloc `<meta name="robots">` conditionnel |
| Modifie | `BaseBillet/templates/faire_festival/base.html` | +bloc `<meta name="robots">` conditionnel |
| Nouveau | `tests/pytest/test_seo_indexing.py` | 10 tests unitaires |
| Modifie | `CHANGELOG.md` | Section dediee chantier SEO 01 |
| Nouveau | `A TESTER et DOCUMENTER/seo-noindex-dev.md` | Procedure de test manuel |

## 6. Plan de tests manuel (apres implementation)

1. **Local dev (`tibillet.localhost`, DEBUG=1)** :
   - `curl http://tibillet.localhost:8002/robots.txt` -> `Disallow: /`
   - Page d'accueil -> view-source -> `<meta name="robots" content="noindex, nofollow">`
2. **Faux instance prod** : forcer `DEBUG=0`, `TEST=0`, `DEMO=0`,
   `STRIPE_TEST=0`, `DOMAIN=tibillet.coop`, `ADDITIONAL_DOMAINS=`,
   acceder via `http://tibillet.localhost:8002/` -> noindex (car
   host=tibillet.localhost ≠ tibillet.coop).
3. **Faux instance prod 2** : memes flags a 0,
   `DOMAIN=tibillet.localhost` -> page tibillet.localhost = indexable
   (pas de meta noindex, robots.txt=Allow).

## 7. Risques et points d'attention

- **Si quelqu'un oublie le context processor dans settings** : les
  templates ne recevront pas `noindex_seo` et ne mettront pas le meta.
  Le `robots.txt` continuera a fonctionner (il appelle directement le
  helper). Defense possible : `{% if noindex_seo|default:False %}` dans
  le template, mais en pratique on suppose que settings.py n'est pas
  casse.
- **Cache CDN / Cloudflare** : si filaos.re passe par un CDN, la
  bascule du robots.txt peut etre cachee. Verifier le cache apres
  deploiement (purge si necessaire).
- **Google Search Console** : pour acceler la desindexation des
  instances deja en SERP, soumettre l'URL en "Remove URLs" apres
  deploiement. Sinon, Google peut mettre des semaines.
- **Une instance prod avec un flag oublie** : si quelqu'un deploie en
  prod avec `STRIPE_TEST=1` (oubli), tout le site passe en noindex.
  C'est le comportement voulu — mais c'est un risque a connaitre.
  Mitigation : check de l'env au boot Django + monitoring Sentry sur
  le `Disallow: /` servi par robots.txt en prod.

## 8. Hors scope

Explicitement reporte au chantier 02 :

- Enrichir `htmx/base.html` avec meta description, OG, Twitter Card,
  canonical, JSON-LD.
- Faire pareil sur `reunion/base.html` et `faire_festival/base.html`.

Le chantier 01 se limite a la desindexation. Aucune autre amelioration
SEO ne doit etre faite dans le meme PR.

## 9. Journal d'avancement

- **2026-05-17 (matin)** : Spec ecrite, en attente de validation utilisateur.
- **2026-05-17 (apres-midi)** : Spec validee par Jonas. Implementation :
  1. Helper `TiBillet/seo_indexing.py` cree (FALC bilingue, 167 lignes).
  2. Vues robots.txt branchees sur le helper (`seo/views_common.py` et
     `BaseBillet/views_robots.py`).
  3. Context processor enregistre dans `TiBillet/settings.py` (+1 ligne).
  4. Les 4 bases templates modifies pour rendre `<meta name="robots">`
     conditionnel sur `noindex_seo`.
  5. `tests/pytest/test_seo_indexing.py` : 11 tests, tous verts en 0.32s.
  6. `ruff check` propre sur les fichiers neufs. `django check` : 0 issue.
  7. CHANGELOG.md et `A TESTER et DOCUMENTER/seo-noindex-dev.md` mis a jour.

- **2026-05-17 (soir)** : Simplification suite a feedback Jonas. La
  regle 2 (host hors whitelist) est retiree car redondante avec la
  regle 1 en pratique : toute instance non-prod a deja un des 4 flags
  actif, et Django bloque deja les hosts inconnus via `ALLOWED_HOSTS`.
  Resultat :
  1. Helper passe de 167 a 89 lignes. `should_noindex()` n'a plus de
     parametre `request` (decision globale a l'instance).
  2. Vues robots.txt simplifiees : appel sans argument.
  3. Tests passent de 11 a 5 (4 flags + 1 cas "indexable").
  4. Spec, CHANGELOG et "A TESTER" mis a jour.

- **2026-05-17 (soir, suite)** : Relecture critique du code. 4 frictions
  identifiees et corrigees :
  1. **Asymetrie DEBUG vs autres flags** : DEBUG etait lu via
     `settings.DEBUG`, les autres via `os.environ`. Uniformise sur
     `os.environ` pour les 4. Le helper n'importe plus Django settings.
     Boucle sur une tuple `_NOINDEX_FLAGS` au lieu de 4 if dupliques.
  2. **Imports locaux mensongers** dans les 2 vues robots.txt : le
     commentaire pretendait eviter un import circulaire qui n'existait
     pas. Imports remontes en top-level.
  3. **Docstring verbeux** sur "pourquoi pas de host" : reduit a 2 lignes
     avec renvoi a la spec.
  4. **Tests refactores** : fixture `env_clean` (pattern pytest standard),
     parametrize sur les 4 flags pour reduire la duplication. Passe de
     78 a 50 lignes.

  Resultat final : helper 78 lignes, tests 50 lignes, 5 tests verts en
  0.30s, ruff `All checks passed!`.

  Restant : test manuel par Jonas puis deploiement prod + demande de
  suppression d'URLs via Google Search Console / Bing Webmaster pour
  desindexer effectivement filaos.re et devtib.fr.
