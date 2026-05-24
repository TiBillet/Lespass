# Guidelines TIBILLET

## Projet

**Lespass** est un moteur de billetterie, d'adhesion et de gestion de budget contributif. 
C'est une brique de l'ecosysteme TiBillet (avec LaBoutik pour la caisse/cashless et Fedow pour le portefeuille federe). 
Fabrique par la Cooperative Code Commun, licence AGPLv3.

Stack : Django 4.2, Python 3.11, Django REST Framework, PostgreSQL 13, Redis, Memcached, Celery, Poetry, Docker.

## FALC — Principe fondamental

**FALC = Facile A Lire et Comprendre.** C'est LA regle numero un du projet.

Ce projet est un commun numerique cooperatif. Le code doit etre lisible par des developpeurs non-experts. Concretement :

- **Noms de variables explicites et verbeux.** La longueur n'est pas un probleme.
- **Commentaires bilingues FR/EN** qui expliquent le *pourquoi*, pas le *quoi*.
- **Preferer les boucles `for` simples** aux comprehensions complexes. Le verbeux > le malin.
- **Phrases courtes, mots simples** dans les commentaires et les docstrings.
- **Pas de sucre syntaxique qui masque la logique.** On veut voir ce qui se passe. Eviter les abstractions magiques, les decorateurs complexes, les metaclasses. Le code doit se lire de haut en bas sans devoir aller fouiller dans 5 fichiers.

## Architecture — Choix deliberes

### Controleurs : `viewsets.ViewSet` (pas ModelViewSet)

On utilise `viewsets.ViewSet` de DRF comme controleur, y compris pour les vues qui rendent du HTML.
**Pas de `ModelViewSet`** : c'est trop de magie cachee. On ecrit explicitement `list()`, `retrieve()`, `create()`, etc.
Si besoin de route supplémentaire, on utilise les actions `@action()`.

Les ViewSets retournent soit :
- Des **templates Django** (pages completes ou partiels HTMX) pour l'UI
- Du **JSON** uniquement pour l'API v2 (`api_v2/`)

Exemple type (module `crowds`) :
```python
class InitiativeViewSet(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [permissions.AllowAny]

    def list(self, request):
        # ... queryset explicite, pas de get_queryset() magique
        return render(request, "crowds/views/list.html", context)

    def retrieve(self, request, pk=None):
        initiative = get_object_or_404(Initiative, uuid=pk)
        return render(request, "crowds/views/detail.html", context)

    @action(detail=True, methods=["POST"])
    def vote(self, request, pk=None):
        # ... retourne un partiel HTMX
        return render(request, "crowds/partial/votes_badge.html", context)
```

### Validation : `serializers.Serializer` (pas de Django Forms)

**On n'utilise pas les forms Django.** Chaque input est valide par un `serializers.Serializer` de DRF.
Pas de `ModelSerializer` sauf dans `api_v2/` pour les endpoints JSON semantiques.

### Frontend : HTMX + Bootstrap 5

- **Rendu cote serveur uniquement.** Les vues retournent du HTML (pages completes ou partiels). Pas de JSON pour l'UI.
- **HTMX** pour les interactions dynamiques : `hx-get`, `hx-post`, `hx-target`, `hx-swap`, `hx-push-url`.
- **Bootstrap 5** pour le style et la grille.
- **Minimal JavaScript.** JS seulement pour les toasts SweetAlert2 et les petites interactions.
- **Anti-blink** : navigation liste/detail via `hx-target="body"` + `hx-swap="innerHTML"` pour ne pas recharger le `<head>`.
- **Toujours conserver `href`/`action`** pour le repli sans JS.
- **CSRF** : `hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'` sur le `<body>`.
- **i18n** : `{% translate %}` / `gettext` pour tout texte visible. **Texte source en français par defaut** : le libelle ecrit dans `{% translate "..." %}` / `_()` est en FR ; la traduction EN est generee *depuis* le FR (jamais l'inverse). Ne plus creer de nouveaux msgid en anglais. (Du code ancien a encore des msgid EN : ne pas les convertir hors session.)

### Loading overlay (extension `loading-states`)

L'extension HTMX `loading-states` gere l'overlay de chargement pendant les navigations.
Active sur `<body>` via `hx-ext="loading-states"`.

**Principe :** un overlay frosted glass (flou gaussien + voile sombre) apparait uniquement si la requete dure plus de `loading_delay` ms (defaut : 400ms). Les requetes rapides ne declenchent rien.

- **Overlay** : `reunion/loading.html` — inclus dans `base.html` et `headless.html`
- **Delai configurable** : variable `loading_delay` dans `get_context()` (views.py), injectee via `{{ loading_delay|default:'400' }}`
- **Declenchement** : attribut `data-loading-target="#tibillet-spinner"` sur le conteneur parent des liens de navigation
- **Scope** : ne jamais mettre `data-loading-target` sur un conteneur qui contient des formulaires (`hx-post`). Scoper au plus pres des liens de navigation.

Attributs utilises :
- `data-loading-class="active"` — sur le spinner, ajoute une classe CSS (permet les transitions)
- `data-loading-delay="{{ loading_delay|default:'400' }}"` — debounce, pas de blink si requete rapide
- `data-loading-target="#tibillet-spinner"` — sur les conteneurs de liens, pointe vers l'overlay
- `data-loading-disable` — desactive un bouton pendant la requete (utile pour les formulaires)

```html
<!-- Conteneur de liens de navigation — scope du spinner -->
<nav data-loading-target="#tibillet-spinner" data-loading-delay="{{ loading_delay|default:'400' }}">
    <a href="/event/" hx-get="/event/" hx-target="body" hx-push-url="true">Agenda</a>
</nav>

<!-- NE PAS faire : data-loading-target sur un conteneur avec des formulaires -->
<div data-loading-target="#tibillet-spinner">  <!-- MAUVAIS -->
    <form hx-post="/save/">...</form>  <!-- Le spinner va se declencher ici aussi -->
</div>
```

Regle CSS requise (deja dans `loading.html`) :
```css
[data-loading] { display: none; }
```

Pattern HTMX pour les toasts (reponses partielles) :
```python
# Cote controleur : utiliser HX-Trigger + django.messages
messages.add_message(request, messages.SUCCESS, _("Action reussie !"))
payload = [{"level": m.level_tag, "text": str(m)} for m in get_messages(request)]
response = render(request, "mon/partial.html", context)
response["HX-Trigger"] = json.dumps({"toast": {"items": payload}})
return response
```

### Templates

- Etendre la base du skin (`reunion/base.html`, `faire_festival/base.html`, etc.)
- Factoriser en partiels (`partial/*.html`) pour les blocs HTMX reutilisables.
- Multi-skin : chaque skin est un dossier dans `BaseBillet/templates/<skin_name>/`.

## Multi-Tenancy (django-tenants)

Base PostgreSQL unique avec isolation par schema. Chaque lieu/organisation a son propre schema.

- **Apps partagees** (schema public) : `Customers`, `AuthBillet`, `Administration`
- **Apps tenant** (schema par tenant) : `BaseBillet`, `ApiBillet`, `api_v2`, `PaiementStripe`, `fedow_connect`, `crowds`...
- Routage URL : `TiBillet/urls_public.py` (domaine racine) vs `TiBillet/urls_tenants.py` (sous-domaines)
- Cache tenant-aware via `django_tenants.cache.make_key`
- Migrations : `python manage.py migrate_schemas --executor=multiprocessing`

## Modules principaux

| Module | Role |
|--------|------|
| `BaseBillet` | Coeur : modeles Event, Product, Offering, Reservation, Membership, Sale + vues templates |
| `Administration` | Admin Django (django-unfold). Fichier principal : `admin_tenant.py` |
| `AuthBillet` | Modele User custom (TibilletUser), auth, OAuth2/SSO |
| `seo` | **SHARED_APPS.** Cache cross-tenant pour landing publique, explorer, sitemap-index. Source unique pour le widget Leaflet (JS+CSS+widget+data builder) partage entre `/explorer/` public et `/federation/` tenant. |
| `api_v2` | API semantique schema.org/JSON-LD (voir `api_v2/GUIDELINES.md`) |
| `ApiBillet` | API REST legacy (v1) |
| `PaiementStripe` | Webhooks Stripe, paiements, abonnements, remboursements |
| `fedow_connect` | Client API Fedow (tokens SSA, monnaie locale/temps) |
| `crowds` | Financement participatif avec contribution adaptive/cascade (voir `crowds/GUIDELINES.md`) |
| `Customers` | Modeles Client/Domain pour django-tenants |
| `wsocket` | Django Channels / WebSocket |

### Couplage seo ↔ BaseBillet

`seo` (SHARED_APPS) et `BaseBillet` (TENANT_APPS) s'importent mutuellement (imports
locaux pour eviter les cycles au load). Pattern bidirectionnel assume :

- `BaseBillet.views::FederationViewset` importe `seo.services`, `seo.models`,
  `seo.views_common` (pour acceder au SEOCache cross-tenant).
- `seo.services::build_tenant_config_data` importe `BaseBillet.models.Configuration`
  (pour lire la config singleton de chaque tenant).
- `seo.views_common::humans_txt` importe `BaseBillet.views_humans` (reuse du
  parseur de fichier VERSION).

Les imports sont LOCAUX (dans la methode, pas au load time du module) pour
eviter les ImportError au demarrage. Si `seo/` doit etre extrait en
microservice un jour, ces 3 imports sont les points a casser.

### App `seo/` — points cles techniques

- **SEOCache** est une table dans le schema `public`. Lecture depuis n'importe
  quel tenant. Rafraichi par le Celery task `seo.tasks.refresh_seo_cache`
  toutes les 4h.
- **Cache 2 niveaux** : Memcached L1 (TTL 4h) + DB L2 fallback via
  `seo.views_common::get_seo_cache(cache_type, tenant_uuid=None)`.
- **Widget explorer** (carte Leaflet + liste filtree) : source unique dans
  `seo/templates/seo/partials/explorer_widget.html` + `seo/static/seo/explorer.{js,css}`,
  utilisee par `/explorer/` public ET `/federation/` tenant via 2 wrappers
  triviaux.
- **JS IIFE encapsule** : `seo/static/seo/explorer.js` n'expose rien sur
  `window`. Event delegation, garde-fous `try/catch`, i18n via `data-i18n-*`
  sur `#explorer-root`.
- **Vendor Leaflet** : `seo/static/seo/vendor/leaflet/` (plus de CDN externe
  en prod, pour la stabilite et la confidentialite).

### JSON-LD dans les templates — utiliser `json_for_html()`

**Pattern obligatoire pour tout JSON injecte dans `<script type="application/ld+json">`** :

```python
from seo.views_common import json_for_html
context = {"my_json_ld": json_for_html(my_json_ld_dict)}
```

```django
<script type="application/ld+json">{{ my_json_ld|safe }}</script>
```

`json_for_html()` translate `<`, `>`, `&` en sequences unicode (`<>&`).
Equivalent semantique pour un parser JSON, mais ne casse pas le HTML parent. Cas
d'usage : si un admin tenant met `</script>` dans son nom d'organisation,
le JSON-LD passe par le SEOCache et se retrouve dans la page des voisins. Sans
echappement, le `</script>` interieur ferme prematurement la balise script
→ vecteur XSS.

**Pour les donnees JSON cote JavaScript** (consommees par `JSON.parse()` ou
`fetch`), utiliser `{{ data|json_script:"my-id" }}` qui fait le meme job
nativement et expose les donnees via `document.getElementById('my-id').textContent`.

### Reverse proxy HTTPS — `SECURE_PROXY_SSL_HEADER`

Le projet tourne derriere Traefik qui termine TLS et forwarde en HTTP au
container Django. Sans `SECURE_PROXY_SSL_HEADER`, `request.scheme = 'http'`
et tous les `request.build_absolute_uri()` retournent `http://...`. Le
reglage `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`
permet a Django de detecter HTTPS via le header forwarded par Traefik
(active par defaut en mode HTTPS auto).

**Consequence** : canonical URLs, JSON-LD, et tous les liens generes avec
`request.build_absolute_uri()` sont en `https://`. Important pour le SEO.

## API v2 (api_v2/)

Vocabulaire schema.org avec champs JSON-LD. Voir `api_v2/GUIDELINES.md` pour le mapping complet.

- Auth : header `Authorization: Api-Key <key>`
- Endpoints : `/api/v2/events/`, `/api/v2/postal-addresses/`, `/api/v2/products/`, etc.
- OpenAPI maintenu manuellement dans `api_v2/openapi-schema.yaml`
- Ici on utilise `viewsets.ViewSet` aussi, mais les reponses sont du JSON semantique.

## Commandes de developpement

**Lancer le serveur en arriere-plan depuis un terminal :**

```bash
# Lance dans le terminal actuel ET garde un trace dans un fichier de log : 
docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver 0.0.0.0:8002 2>&1 | tee /DjangoFiles/logs/runserver.log
```

Les logs du serveur (tracebacks, requetes) sont ecrits dans un fichier temporaire :

**Pour que le mainteneur suive les logs en temps reel dans un terminal PyCharm :**
```bash
tail -f logs/runserver.log
```


```bash
# Demarrer la stack
docker compose up -d

# Commandes Django dans le conteneur
docker exec lespass_django poetry run python manage.py <commande>

# Migrations multi-tenant
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing

# Collectstatic
docker exec lespass_django poetry run python manage.py collectstatic --no-input

# i18n
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
docker exec lespass_django poetry run django-admin compilemessages

# Celery (lance via docker-compose, commande pour reference)
poetry run celery -A TiBillet worker -l INFO -B --concurrency=6
```

## Tests

### Backend (pytest)

```bash
# Tous les tests API
poetry run pytest tests/pytest/ -v

# Tests integration API v2 uniquement
poetry run pytest -m integration tests/pytest/

# Un seul fichier
poetry run pytest tests/pytest/test_events_list.py -qs

# Avec cle API
poetry run pytest tests/pytest --api-key <KEY> --api-base-url https://lespass.tibillet.localhost
```

### E2E (Playwright)

```bash
cd tests/playwright
yarn install && yarn playwright install

# Un test a la fois (toujours --workers=1). Ne jamais lancer tous les tests d'un coup.
yarn playwright test --project=chromium --headed --workers=1 tests/01-login.spec.ts
```

Les tests sont numerotes pour l'ordre d'execution (01 a 24+). Carte Stripe test : `4242 4242 4242 4242`, nom : Douglas Adams, exp : 12/42, CVC : 424.

Verification DB apres un test E2E :
```bash
docker exec lespass_django poetry run python manage.py verify_test_data --type reservation --email <EMAIL>
```

### Regles d'ecriture des tests

1. **Atomique** : un test = un comportement precis.
2. **Verbeux** : noms de fonctions longs et clairs.
3. **Bilingue** : commentaires FR + EN.
4. **FALC** : mots simples.
5. **Incremental** : d'abord comprendre la structure (curl), ensuite ecrire le test.

## Accessibilite et themes

- `aria-label` pour les groupes d'info, `visually-hidden` pour decrire les valeurs.
- Ne pas encoder de texte dans les icones; elles sont decoratives (`aria-hidden="true"`).
- Utiliser les classes Bootstrap (`text-body`, `text-muted`, `bg-body-tertiary`, etc.) pour respecter clair/sombre.

## Anti-patterns (a eviter)

- **Reponses JSON pour piloter l'UI** — preferer HTML + `HX-Trigger` pour les toasts.
- **Swapper `html`/`head`** — provoque des clignotements et recharge les assets.
- **JS volumineux** pour des comportements que HTMX gere nativement.
- **ModelViewSet / ModelSerializer** pour les vues templates — trop de magie cachee.
- **Django Forms** — on utilise les serializers DRF.
- **Comprehensions complexes et one-liners** — preferer le code verbeux et lisible.
- **Decorateurs/metaclasses qui cachent la logique** — le code doit se lire lineairement.
- **`json.dumps()` dans un template `<script type="application/ld+json">`** —
  caracteres `< > &` non echappes, vecteur XSS si l'input vient de la DB.
  Utiliser `seo.views_common.json_for_html()` ou `{{ data|json_script:"id" }}`
  (voir section "JSON-LD dans les templates" plus haut).
- **CDN externes pour assets prod** (unpkg.com, cdnjs, jsDelivr, etc.) —
  fragile (dependance externe), tracking tiers possible. Vendoré dans
  `*/static/*/vendor/*/` (ex: `seo/static/seo/vendor/leaflet/`).
- **Globals JavaScript** (`var foo = ...` au top-level d'un fichier JS) — pollue
  `window`, conflit possible avec d'autres scripts. Encapsuler dans une IIFE
  `(function(){ 'use strict'; ... })();` (pattern utilise dans
  `seo/static/seo/explorer.js`).
- **Inline `onclick="..."`** dans des strings construits cote JS — fragile,
  casse avec CSP stricte, dur a tester. Utiliser event delegation sur un
  conteneur parent.
- **`setTimeout(..., N)` avec un delai magique** pour attendre un event
  (animations, transitions) — flaky en CI lent. Preferer les events natifs
  (`animationend`, `transitionend`, etc.) avec fallback timer reduit.

## Docker

| Conteneur | Role | Port |
|-----------|------|------|
| `lespass_django` | Django (Gunicorn) | 8002 |
| `lespass_celery` | Celery worker + Beat | — |
| `lespass_postgres` | PostgreSQL 13 | 5432 (interne) |
| `lespass_redis` | Redis 7.2 (broker) | — |
| `lespass_memcached` | Memcached 1.6 (cache) | — |
| `lespass_nginx` | Nginx reverse proxy | 80 |

Reseau externe `frontend` (pour Traefik). Acces : `https://lespass.tibillet.localhost`. Auto-login admin quand `DEBUG=1` et `TEST=1`.

## Stripe en dev

```bash
stripe listen --forward-to https://tibillet.localhost/api/webhook_stripe/ --skip-verify
```

## Git

**Ne jamais realiser d'operation git.** Pas de `git add`, `git commit`, `git push`, `git checkout`, `git branch`, etc. Le mainteneur s'en occupe.

## Check‑list avant merge

- [ ] Toutes les interactions renvoient du HTML (partials) — pas de JSON UI.
- [ ] Pas de « blink »: navigations `body` et swaps ciblés.
- [ ] Recherche/pagination/tag OK, URLs mises à jour (`hx-push-url`).
- [ ] FALC: libellés simples, pictos, contrastes, aides d’accessibilité.
- [ ] i18n: tous les labels dans `{% translate %}`.
- [ ] Sécurité: droits des actions, CSRF OK.
- [ ] Admin: URLs fonctionnelles dans Unfold.
