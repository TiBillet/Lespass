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
- **i18n** : `{% translate %}` / `gettext` pour tout texte visible.

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
| `api_v2` | API semantique schema.org/JSON-LD (voir `api_v2/GUIDELINES.md`) |
| `ApiBillet` | API REST legacy (v1) |
| `PaiementStripe` | Webhooks Stripe, paiements, abonnements, remboursements |
| `fedow_connect` | Client API Fedow (tokens SSA, monnaie locale/temps) |
| `crowds` | Financement participatif avec contribution adaptive/cascade (voir `crowds/GUIDELINES.md`) |
| `Customers` | Modeles Client/Domain pour django-tenants |
| `wsocket` | Django Channels / WebSocket |

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

## Pieges multi-tenancy (django-tenants)

### Erreur "relation does not exist" = mauvais schema

Si une requete Django leve `ProgrammingError: relation "BaseBillet_xxx" does not exist`, c'est presque toujours parce que le code tourne sur le **schema public**. Les tables des TENANT_APPS (`BaseBillet`, `laboutik`, `crowds`, etc.) n'existent que dans les schemas tenant, pas dans `public`.

**Diagnostic rapide :** ajouter `print(connection.schema_name)` avant la requete qui plante. Si ca affiche `"public"`, c'est confirme.

**Causes frequentes :**
- Management command lancee sans `tenant_context` / `schema_context`
- `connection.schema_name` vaut `"public"` par defaut (hors middleware HTTP)
- `call_command()` depuis un autre command : le schema courant n'est pas herite automatiquement si la commande appelée re-set le schema

**Solution :** toujours verifier `connection.schema_name` en debut de commande. Si c'est `"public"` et que la commande a besoin de tables tenant, basculer explicitement :
```python
from django.db import connection
from django_tenants.utils import schema_context
from Customers.models import Client

schema = connection.schema_name
if schema == "public":
    tenant = Client.objects.exclude(schema_name="public").first()
    schema = tenant.schema_name

with schema_context(schema):
    # ... code qui touche des TENANT_APPS
```

## Anti-patterns (a eviter)

- **Reponses JSON pour piloter l'UI** — preferer HTML + `HX-Trigger` pour les toasts.
- **Swapper `html`/`head`** — provoque des clignotements et recharge les assets.
- **JS volumineux** pour des comportements que HTMX gere nativement.
- **ModelViewSet / ModelSerializer** pour les vues templates — trop de magie cachee.
- **Django Forms** — on utilise les serializers DRF.
- **Comprehensions complexes et one-liners** — preferer le code verbeux et lisible.
- **Decorateurs/metaclasses qui cachent la logique** — le code doit se lire lineairement.

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

## laboutik — UI et Design de la Caisse POS

### Police Luciole

La police **Luciole** est utilisée dans tout laboutik (`font-family: "Luciole-regular"`).
C'est une police conçue pour les personnes dyslexiques et malvoyantes — ne pas la remplacer par une autre.
Elle doit être lisible à 1-2 mètres de distance sur un écran tactile, dans un environnement sombre (festival, bar).

### Tuiles articles — Pièges CSS connus

#### 1. Font Awesome `::before` dans un `-webkit-box` → caractère de remplacement affiché

Un `<i class="fas fa-xxx">` placé à l'intérieur d'un conteneur `display: -webkit-box` ne rend pas son icône — le pseudo-élément `::before` de Font Awesome ne fonctionne pas dans ce contexte. On voit à la place le caractère Unicode de remplacement (ex: `☺`).

**Solution :** mettre l'icône comme sibling flex à l'extérieur du `-webkit-box`, pas à l'intérieur.

```html
<!-- BON : icône sibling du span nom, les deux dans un flex container -->
<div class="article-body-layer"> <!-- display: flex -->
    <i class="fas fa-xxx article-cat-icon" aria-hidden="true"></i>  <!-- sibling -->
    <span class="article-name-text">...</span>  <!-- -webkit-box ici -->
</div>

<!-- MAUVAIS : icône à l'intérieur du -webkit-box -->
<div style="display: -webkit-box; -webkit-line-clamp: 3;">
    <i class="fas fa-xxx"></i>  <!-- l'icône ne s'affichera pas -->
    Nom de l'article
</div>
```

#### 2. `width: 100%` + `position: absolute` avec `left` ET `right` → débordement

Quand un élément est `position: absolute` avec `left: 5px; right: 5px`, ne pas lui ajouter `width: 100%`.
En CSS, `width` prend la priorité sur `right` (en LTR) : `width: 100%` = largeur du parent entier, ce qui ignore `right: 5px` et fait déborder l'élément de 5px sur la droite. Le `overflow: hidden` du parent coupe alors les enfants au mauvais endroit.

```css
/* BON : left + right suffisent, pas besoin de width */
.article-footer-layer {
    position: absolute;
    left: 5px;
    right: 5px;
    bottom: 5px;
    /* PAS de width: 100% ici */
}

/* MAUVAIS : width:100% écrase right:5px */
.article-footer-layer {
    position: absolute;
    left: 5px;
    right: 5px;
    width: 100%;  /* déborde de 5px sur la droite */
}
```

#### 3. `calc()` avec `--css-custom-property` ≠ taille réelle de la tuile

Les tuiles utilisent `grid-template-columns: repeat(auto-fill, minmax(var(--bt-article-width), 1fr))`.
La valeur `--bt-article-width` est la taille *minimum* — la taille réelle est plus grande (le `1fr` étire les tuiles pour remplir la grille).
Utiliser `calc(var(--bt-article-width) * 0.18)` pour les polices donne donc des résultats imprévisibles.
Préférer des valeurs `rem` fixes ajustées par media query.

#### 4. Hauteur du footer avec pills wrappables

Les pills de tarifs utilisent `flex-wrap: wrap` + `max-height` pour limiter à 2 lignes.
La body-layer doit réserver un `bottom` correspondant à exactement 2 lignes de pills :

```
2 lignes × (font ~18px + padding 4px×2 + line-height 1.3) + 1 gap 3px + bottom 6px ≈ 62px
```

Si `bottom` est trop petit, le footer multi-lignes chevauche visuellement le titre.
Si `max-height` est trop petit, la 2ème ligne de pills est coupée à moitié.

### Lisibilité nocturne / accessibilité POS

La caisse est utilisée le soir dans des environnements peu éclairés (festival, bar).
Règles de lisibilité à respecter :

- **Taille de police minimum** : `1.2rem` pour les noms d'articles, `1.1rem` pour les prix
- **Contraste des pills** : fond `rgba(0,0,0,0.65)` sur tuile claire, texte `#ffffff` — ne pas descendre en dessous
- **Pills prix libre** : fond indigo `rgba(99, 102, 241, 0.85)` pour se distinguer des tarifs fixes
- **Ellipsis sur les noms longs** : `-webkit-line-clamp: 3` + `overflow: hidden` — ne jamais utiliser `max-height` seul (coupe les descendants des lettres p, g, y)
- **`data-testid`** sur chaque tuile : `data-testid="article-{{ article.id }}"` pour les tests Playwright

## Check‑list avant merge

- [ ] Toutes les interactions renvoient du HTML (partials) — pas de JSON UI.
- [ ] Pas de « blink »: navigations `body` et swaps ciblés.
- [ ] Recherche/pagination/tag OK, URLs mises à jour (`hx-push-url`).
- [ ] FALC: libellés simples, pictos, contrastes, aides d’accessibilité.
- [ ] i18n: tous les labels dans `{% translate %}`.
- [ ] Sécurité: droits des actions, CSRF OK.
- [ ] Admin: URLs fonctionnelles dans Unfold.
