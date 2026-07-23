---
name: djc
description: DJC — Django + HTMX development with explicit, readable code patterns. Use this skill whenever working on Django projects with HTMX, server-rendered UIs, ViewSets, templates, form handling, or validation. Also use it when writing any Django view that returns HTML, any DRF serializer for form validation, any HTMX partial or interaction, or any template with dynamic behavior. Prioritizes code readability over cleverness — verbose variable names, explicit methods, no magic abstractions. Covers i18n, accessibility, multi-tenancy, HTMX error handling, CHANGELOG, documentation, and translations workflow.
---

# Stack Cooperative Code Commun — Django + HTMX Readable Patterns

Guidelines for building Django applications with HTMX. Code must be **FALC** (Facile A Lire et Comprendre) — readable by non-expert developers.

## Core Philosophy

- **Verbose variable names** — length is never a problem. `products_available_in_stock` > `products`
- **Explicit over implicit** — no magic, no decorators that hide logic, no metaclasses
- **Simple for loops** over complex comprehensions
- **Bilingual comments FR/EN** — French comments are written in FALC (Facile a Lire et a Comprendre): simple words, short sentences, one idea per sentence, no jargon, no abbreviations. English comments are just a one-line summary of the French comment.
- **Code reads top-to-bottom** — no jumping across 5 files to understand a flow

## FALC Commenting Method

Use this commenting structure for **all code** (JavaScript, Python, Django templates):

### Principles

1. **FR first**: Detailed explanations, business logic, execution flow
2. **EN second**: One-line summary only (`/ Brief description`)
3. **LOCATION required**: Always indicate file path for navigation
4. **Document inter-file communication**: Events, imports, dependencies
5. **Call Flow**: For complex functions, document execution flow

### Le commentaire s'adresse au PROCHAIN LECTEUR, pas au relecteur de ta PR

C'est la faute la plus frequente, et elle est invisible sur le moment.

Quand tu viens de corriger quelque chose, tu as la tete pleine du bug, de l'ancienne
version, de la raison de ton choix. Tu ecris alors des commentaires qui **racontent ta
session** : « Avant, on lisait X… », « Ce test confondait Y et Z… », « Correction du
bug #446 ». Ces phrases s'adressent a la personne qui relit ton diff **aujourd'hui**.

Mais le diff est merge dans deux jours, et **l'« avant » n'existe plus**. Il ne reste
qu'un lecteur, dans six mois, qui doit comprendre le code **tel qu'il est**. Pour lui,
ton recit est du bruit — pire, il l'oblige a se representer un code disparu pour
comprendre le code present. L'historique, c'est le travail de git et du CHANGELOG.

| Ecris | N'ecris pas |
|---|---|
| **CE QUE FAIT** le code (FALC, verbeux, bilingue) | « Avant, cette methode faisait X » |
| **UNE CONTRAINTE** que le code ne peut pas montrer tout seul | « J'ai choisi A plutot que B parce que… » |
| Le **FLUX** (qui appelle qui, quel evenement declenche quoi) | « Correction du bug #446 » / « Suite a la review… » |
| Un **TODO** avec ce qu'il faut faire | Une justification adressee au relecteur |

**La nuance qui compte — le « pourquoi » reste legitime quand c'est une CONTRAINTE.**
Le test : *« si quelqu'un ignore ce commentaire, est-ce qu'il CASSE le code ? »*

- **OUI → garde-le.** Il protege le code contre une « simplification » qui le casserait :
  ```python
  # INDISPENSABLE meme avec autocomplete_fields : l'autocompletion ne pilote que
  # l'affichage. C'est le queryset du champ qui VALIDE la valeur postee — sans ce
  # filtre, un pk force pointant vers la carte d'un autre lieu serait accepte.
  def formfield_for_foreignkey(self, db_field, request, **kwargs):
  ```
  Sans ce commentaire, quelqu'un supprime la methode en la croyant redondante.

- **NON → supprime-le.** C'est de l'historique de session :
  ```python
  # MAL : raconte la session, pas le code
  # Avant, ce test lisait get_solo().module_kiosk, c'est-a-dire la valeur reelle du
  # tenant. Des que quelqu'un activait le module, le test tombait en echec. Il
  # confondait « valeur par defaut » et « valeur actuelle ».

  # BIEN : enonce la contrainte, au present
  # On lit le DEFAUT DU CHAMP, jamais get_solo() : la Configuration du tenant porte
  # la valeur reelle, qu'un gestionnaire peut activer depuis l'admin. La lire ici
  # rendrait le test dependant de l'etat de la base.
  ```

Formule toujours la contrainte **au present**, comme une regle qui s'applique au code tel
qu'il est — jamais comme le recit de ce qui s'est passe.

### JavaScript Example

```javascript
/**
 * Ajoute un article au panier
 * / Adds item to cart
 *
 * LOCALISATION : laboutik/static/js/addition.js
 *
 * Handler de l'evenement 'additionInsertArticle'.
 * Flux : clic article -> articles.js:addArticle -> 'articlesAdd' ->
 * tibilletUtils.js:eventsOrganizer() -> CETTE FONCTION
 *
 * Actions :
 * - Cree input cache 'repid-{uuid}' dans le formulaire
 * - Cree ligne d'affichage dans #addition-list
 * - Recalcule total et emet 'additionTotalChange'
 *
 * COMMUNICATION :
 * Recoit : 'additionInsertArticle' depuis tibilletUtils.js
 * Emet : 'additionTotalChange' -> updateBtValider sur #bt-valider
 *
 * @param {Object} param0 - event.detail avec uuid, price, quantity, name, currency
 */
function additionInsertArticle({ detail }) {
    // Calcule le total en centimes (prix x quantite)
    // / Calculates total in cents
    const total = price * quantity;
}
```

### Python/Django Example

```python
def process_payment(request, order_uuid):
    """
    Traite un paiement et cree la transaction
    / Processes payment and creates transaction

    LOCALISATION : base/views.py

    Cette vue est appelee par le formulaire de paiement (templates/payment/form.html).
    Elle utilise Stripe pour le traitement et cree un enregistrement Transaction.

    FLUX :
    1. Recoit POST depuis payment/form.html
    2. Valide les donnees avec PaymentSerializer
    3. Appelle Stripe API pour creer le paiement
    4. Cree Transaction en base de donnees
    5. Envoie email de confirmation via Celery

    DEPENDENCIES :
    - Stripe API (voir services/stripe.py)
    - Celery pour les emails asynchrones

    :param request: Objet Request Django
    :param order_uuid: UUID de la commande (str)
    :return: Redirect vers page de confirmation ou formulaire avec erreurs
    """
    # Recupere la commande depuis la base
    # / Gets order from database
    order = get_object_or_404(Order, uuid=order_uuid)
```

### Template Example

```html
<!--
BOUTON VALIDER - CONFIRMER LA VENTE
/ Validation button - Confirm sale

LOCALISATION : templates/laboutik/common_user_interface.html

Action : Affiche les options de paiement pour finaliser la vente

FLUX DU CLIC SUR VALIDER :
1. Clic sur #bt-valider
2. Envoie evenement 'additionDisplayPaymentTypes' -> #event-organizer
3. tibilletUtils.js route vers addition.js:additionDisplayPaymentTypes()
4. Si articles presents : declenche formulaire HTMX
5. Affiche partial/hx_display_type_payment.html avec les boutons de paiement
-->
<div id="bt-valider">
    <button>Valider</button>
</div>
```

### TODO Format

```javascript
// TODO : Variable non declaree avec let/const, cree une globale implicite
// / Global variable created implicitly
total = 0;
```

```python
# TODO : Cette requete fait N+1 queries, a optimiser avec select_related
# / N+1 query issue, optimize with select_related
books = Book.objects.all()
for book in books:
    print(book.author.name)  # Requete supplementaire pour chaque author
```

## ViewSet Pattern (DRF)

Use `viewsets.ViewSet`, **never** `ModelViewSet`. Write explicit methods — `list()`, `retrieve()`, `create()`, etc.

The reason: `ModelViewSet` hides too much behind `get_queryset()`, `get_serializer_class()`, and other magic methods. When a new contributor reads the code, they should see exactly what query runs and what template renders, without chasing through a chain of overrides.

```python
class BookViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def list(self, request):
        # Requete explicite, pas de get_queryset() cache
        # Explicit query, no hidden get_queryset()
        books_published_only = Book.objects.select_related('author').filter(
            is_published=True
        )
        return render(request, "books/list.html", {'books': books_published_only})

    def retrieve(self, request, pk=None):
        book = get_object_or_404(Book, uuid=pk)
        return render(request, "books/detail.html", {'book': book})
```

For custom routes, use `@action()`:
```python
    @action(detail=True, methods=["POST"])
    def publish(self, request, pk=None):
        book = get_object_or_404(Book, uuid=pk)

        book_already_published = book.is_published
        if book_already_published:
            return render(request, "books/partials/already_published.html", {'book': book})

        book.is_published = True
        book.published_at = timezone.now()
        book.save(update_fields=['is_published', 'published_at'])

        return render(request, "books/partials/publish_button.html", {'book': book})
```

## Validation: DRF Serializers Only

**Dans les vues (front, HTMX, API) : jamais de Django Forms.** La validation passe par
`serializers.Serializer`. `ModelSerializer` n'est tolere que dans `api_v2/` (endpoints JSON).

Pourquoi : les Django Forms melangent la validation et le rendu HTML. Avec les serializers
DRF, la validation reste dans une couche claire et les templates gerent l'affichage.

**LA SEULE EXCEPTION — l'admin Django/Unfold.** Dans l'admin, le `ModelForm` est le seul
mecanisme disponible : `ModelAdmin.add_form` / `form` n'acceptent rien d'autre. Le projet en
utilise (`CarteCashlessAddForm`, `MembershipAddForm`). **N'essaie pas d'y mettre un serializer
DRF : ca ne se branche pas.** Pour tout ce qui touche a l'admin, c'est le skill **`unfold`**
qui fait foi.

```python
class BookCreateSerializer(serializers.Serializer):
    title = serializers.CharField(
        max_length=200,
        error_messages={
            'required': 'Le titre est obligatoire / Title is required',
        }
    )
    description = serializers.CharField(required=False, allow_blank=True)

    def validate_title(self, value):
        title_cleaned = value.strip()
        if Book.objects.filter(title__iexact=title_cleaned).exists():
            raise serializers.ValidationError(
                'Un livre avec ce titre existe deja / A book with this title already exists'
            )
        return title_cleaned
```

## HTMX Integration

Server-rendered HTML only. No JSON for UI. HTMX handles dynamic interactions.

### Règle fondamentale : Python serveur > JavaScript client

Toujours préférer la logique serveur à la logique client.
Quand une information doit changer ou être calculée, c'est le serveur Python
qui le fait et renvoie un partial HTML via HTMX. Le JavaScript ne doit pas
porter de logique métier.

#### Anti-pattern : bootstrap JSON + JavaScript

Ce pattern vient des SPA (React, Vue). Il n'a pas sa place dans une stack HTMX :

```html
<!-- MAL — injecte les données en JSON pour que le JS les lise -->
<script>
  window.evenementsGroupes = {{ evenements_groupes_json|safe }};
</script>
```

```python
# MAL — double envoi : même donnée en HTML ET en JSON
context = {
    "evenements_groupes": evenements_groupes,              # pour le template
    "evenements_groupes_json": dumps(evenements_groupes),  # inutile
}
```

#### Pattern correct : data-* dans le HTML, partial HTMX pour les mises à jour

Les données dont le JS a besoin au moment du clic (uuid, prix, flags) vont
dans des attributs `data-*` sur l'élément HTML. C'est tout.
Si la donnée doit se rafraîchir (ex : places restantes), un partial HTMX la
remplace — pas du JS qui lit un `window.xxx`.

```html
<!-- BON — les data-* portent les infos nécessaires au JS -->
<div class="article-btn"
     data-id="{{ tarif.product_uuid }}"
     data-prix="{{ tarif.prix_centimes }}"
     data-event-uuid="{{ event.uuid }}"
     onclick="addArticle('{{ tarif.product_uuid }}', {{ tarif.prix_centimes }})">
  {{ tarif.name }}
</div>
```

```html
<!-- BON — rafraîchissement de la jauge via HTMX, pas via JS + JSON -->
<span id="jauge-{{ event.uuid }}"
      hx-get="{% url 'laboutik-jauge' event.uuid %}"
      hx-trigger="every 30s"
      aria-live="polite">
  {{ event.places_restantes }} {% translate "places restantes" %}
</span>
```

#### Règle de décision rapide

```
Une donnée change après un événement utilisateur ?
  → HTMX partial (hx-get / hx-post → renvoie du HTML)

Une donnée est statique au chargement, le JS en a besoin au clic ?
  → data-* sur l'élément HTML

Une donnée nécessite du JS + window.xxx pour fonctionner ?
  → Revoir l'architecture — c'est un signal que la logique est au mauvais endroit
```

#### Cas particulier : `{% load json_script %}` n'existe pas

`json_script` est un **filtre natif Django** (`{{ valeur|json_script:"id" }}`),
pas une library. `{% load json_script %}` lève une `TemplateSyntaxError`.
Ne jamais écrire `{% load json_script %}`.

Si `|json_script` est vraiment nécessaire (cas rare : bootstrapper un composant
JS qui n'a pas d'équivalent HTMX), l'utiliser sans `{% load %}` et documenter
pourquoi le pattern HTMX ne convient pas.

### Anti-Blink Navigation

Navigate between list and detail without page flash:

```html
<a
    href="{% url 'book-detail' pk=book.uuid %}"
    hx-get="{% url 'book-detail' pk=book.uuid %}"
    hx-target="body"
    hx-swap="innerHTML"
    hx-push-url="true"
>
    {{ book.title }}
</a>
<!-- Le href est conserve pour le fallback sans JS -->
<!-- href is kept for no-JS fallback -->
```

### CSRF Token

Always on `<body>`:
```html
<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
```

### HTMX Base Template Selection

Quand une meme vue sert une PAGE COMPLETE et des PARTIELS HTMX, le gabarit de base est
choisi selon le type de requete :

```python
from pages.services import gabarit_skin

def get_context(request):
    config = Configuration.get_solo()

    # Requete HTMX -> gabarit sans habillage. Sinon -> le squelette complet.
    # / HTMX request -> headless template. Otherwise -> the full shell.
    if request.htmx:
        base_template = gabarit_skin("headless.html")
    else:
        base_template = gabarit_skin("shell.html")

    return {"base_template": base_template, "config": config}
```

**Le resolveur est `pages.services.gabarit_skin(nom_du_gabarit)`** — il renvoie
`pages/<skin>/<nom>` si le skin courant fournit le gabarit, sinon il retombe sur le socle
`pages/classic/<nom>`.

**ATTENTION — deux pieges d'ancien code :**
- `get_skin_template(config, ...)` **N'EXISTE PLUS** (resolveur legacy supprime, cf.
  `BaseBillet/views.py`). Ne jamais l'ecrire : `ImportError` immediat.
- Le squelette s'appelle **`shell.html`**, pas `base.html`.

### HTMX Client-Side Validation

Validate inputs **before** the HTMX request fires using `htmx:configRequest`. This avoids unnecessary server round-trips:

```javascript
// Valider côté client AVANT d'envoyer la requête HTMX
// Validate client-side BEFORE sending the HTMX request
form.addEventListener("htmx:configRequest", function(event) {
    if (!validateInputs()) {
        event.preventDefault();  // Bloque la requete HTMX / Stops the HTMX request
    }
});
```

### HTMX Loading Overlay (extension `loading-states`)

The `loading-states` extension manages a global loading overlay during navigation. Activated on `<body>` via `hx-ext="loading-states"`.

**UX principle:** the overlay (frosted glass blur + dark veil) only appears if the request takes longer than `loading_delay` ms (400). Fast requests show nothing — no blink. The delay comes from `get_context()` (`BaseBillet/views.py`).

#### L'overlay a UN SEUL déclencheur — et tu n'as rien à écrire

`#tibillet-spinner` (dans `commun/loading.html`) porte lui-même le couple
`data-loading-class="active"` + `data-loading-delay`. L'extension le retrouve à **chaque**
requête htmx du document : son scope est `document.body` tant qu'aucun `data-loading-states`
n'est posé. Toute navigation et toute soumission de formulaire l'allument donc déjà, après
le délai.

**Conséquence pratique : pour qu'un lien ou un formulaire affiche l'overlay, il n'y a
RIEN à ajouter dessus.** C'est déjà le cas.

#### Le piège : `data-loading-class` sans `data-loading-delay`

Dans `loading-states.js`, `queueLoadingState()` cherche le délai avec
`htmx.closest(sourceElt, '[data-loading-delay]')`. **Si aucun délai n'est trouvé, il n'y a
pas de temporisation du tout** — le callback part immédiatement. Un élément qui porte
`data-loading-class` sans délai affiche donc l'overlay en ~3 ms, et il le fait sur
**toutes** les requêtes de la page, pas seulement les siennes (le scope est global).

```html
<!-- MAUVAIS : allume l'overlay en ~3 ms, sur TOUTE requete de la page -->
<!-- BAD: fires the overlay in ~3 ms, on EVERY request of the page -->
<form hx-post="/memberships/"
      data-loading-target="#tibillet-spinner"
      data-loading-class="active">

<!-- BON : rien. #tibillet-spinner s'en charge, avec le delai. -->
<!-- GOOD: nothing. #tibillet-spinner already handles it, with the delay. -->
<form hx-post="/memberships/">
```

#### `data-loading-target` seul ne déclenche rien

C'est un **redirecteur**, pas un déclencheur : il n'agit que sur un élément portant déjà un
attribut actif (`data-loading`, `data-loading-class`, `-class-remove`, `-disable`,
`-aria-busy`). Posé sur un `<nav>` ou un conteneur de liens qui n'en porte aucun, il est
sans effet — du code mort qui donne l'illusion d'un scope.

Le seul usage légitime : un **spinner local**, quand une zone de la page charge seule et
qu'on ne veut pas voiler tout l'écran. Il se cible lui-même et porte son propre délai
(voir `#token-table-loader` dans `fonctionnel/compte/balance.html`) :

```html
<div id="token-table-loader" data-loading data-loading-class="active" class="text-center">
    <div class="spinner-border" role="status">
        <span class="visually-hidden">{% translate "Chargement..." %}</span>
    </div>
</div>
<div hx-get="/my_account/tokens_table/" hx-trigger="revealed"
     data-loading-target="#token-table-loader"
     data-loading-delay="{{ loading_delay|default:'400' }}"></div>
```

- `data-loading-disable` sur un bouton : à laisser **sans délai**, la désactivation immédiate
  est ce qui empêche le double-clic.

Required CSS rule (already in `loading.html`) — elle cache les spinners **locaux**, ceux qui
portent `data-loading`. Elle ne s'applique pas à `#tibillet-spinner`, masqué par son
`opacity: 0` :
```css
[data-loading] { display: none; }
```

**Comment vérifier** — l'inspection visuelle ne suffit pas, un overlay qui flashe 50 ms se
voit mal. Dans la console du navigateur :
```js
new MutationObserver(m => console.log(performance.now(), sp.classList.contains('active')))
  .observe(sp = document.querySelector('#tibillet-spinner'),
           {attributes: true, attributeFilter: ['class']});
```
Puis navigue : l'écart entre la requête et le passage à `active` doit valoir le délai, pas
quelques millisecondes.

### Quirks htmx — Comportements surprenants à connaître

htmx a des comportements par défaut qui peuvent surprendre. Les connaître évite
des heures de debug. (Source : https://htmx.org/quirks/)

#### 1. Le swap par défaut est `innerHTML`, pas `outerHTML`

htmx remplace le **contenu intérieur** de la cible, pas l'élément lui-même.
Si on veut remplacer l'élément entier (y compris ses attributs), il faut
`hx-swap="outerHTML"` explicitement.

```html
<!-- Par défaut : remplace le CONTENU de #result, pas la div elle-même -->
<div id="result" hx-get="/api/data" hx-target="#result">
    Ancien contenu
</div>

<!-- Si on veut remplacer la div entière (attributs inclus) : -->
<div id="result" hx-get="/api/data" hx-target="#result" hx-swap="outerHTML">
    Ancien contenu
</div>
```

**Dans notre stack** : on utilise souvent `hx-target="body" hx-swap="innerHTML"`
pour la navigation anti-blink — c'est cohérent avec le défaut.

#### 2. Les erreurs HTTP (4xx/5xx) ne déclenchent PAS de swap

Par défaut, si le serveur renvoie une erreur 422 (validation) ou 500,
htmx **ne fait rien** — pas de swap, pas de message. C'est le piège le plus
courant avec les formulaires.

**Solution dans notre stack** : configurer htmx au démarrage pour swapper
aussi sur les codes d'erreur utiles :

```javascript
// Configure htmx pour afficher le HTML renvoyé même en cas d'erreur serveur
// / Configure htmx to swap content even on server error responses
document.addEventListener("htmx:beforeOnLoad", function(event) {
    const status_code_de_la_reponse = event.detail.xhr.status;

    // On accepte le swap pour les erreurs de validation (422)
    // et les erreurs serveur (500) — le serveur renvoie du HTML utile
    // / Allow swap for validation errors (422) and server errors (500)
    if (status_code_de_la_reponse === 422 || status_code_de_la_reponse === 500) {
        event.detail.shouldSwap = true;
        event.detail.isError = false;
    }
});
```

Côté Django, renvoyer le formulaire avec les erreurs en 422 :
```python
# Si le serializer est invalide, on renvoie le partial avec les erreurs
# / If serializer is invalid, return partial with errors and 422 status
if not serializer_de_validation.is_valid():
    return render(request, "module/partials/form.html", {
        "serializer": serializer_de_validation,
    }, status=422)
```

#### 3. L'héritage d'attributs peut créer des effets de bord

Les éléments enfants héritent des attributs htmx de leurs parents.
C'est pratique (un seul `hx-target` sur un conteneur), mais ça peut
provoquer des comportements inattendus si on n'en est pas conscient.

```html
<!-- Tous les liens/boutons à l'intérieur héritent de hx-target="#content" -->
<div hx-target="#content">
    <a hx-get="/page1">Page 1</a>  <!-- cible #content — OK -->
    <a hx-get="/page2">Page 2</a>  <!-- cible #content — OK -->

    <!-- ATTENTION : ce bouton aussi hérite de hx-target="#content" -->
    <!-- même si on voulait qu'il cible autre chose -->
    <button hx-post="/delete">Supprimer</button>
</div>
```

**Règle** : toujours déclarer `hx-target` explicitement sur les éléments
qui ont un comportement différent du conteneur parent. En cas de doute,
être explicite plutôt que de compter sur l'héritage.

#### 4. `hx-boost` est pratique mais piégeux

`hx-boost="true"` transforme automatiquement les liens et formulaires
classiques en requêtes AJAX. C'est tentant mais ça introduit des
complications avec l'historique navigateur, le chargement de scripts,
et les conflits de scope global.

**Règle dans notre stack** : préférer des `hx-get` / `hx-post` explicites
sur chaque élément plutôt que `hx-boost` sur un conteneur. C'est plus
verbeux mais beaucoup plus prévisible et debuggable.

#### 5. htmx doit être chargé en script bloquant

htmx est conçu pour être chargé avec une balise `<script>` classique
bloquante. Ne pas utiliser `type="module"`, `defer`, ou `async` —
sinon les attributs `hx-*` présents dans le HTML initial ne seront
pas traités correctement.

```html
<!-- BON : script bloquant classique -->
<script src="/static/js/htmx.min.js"></script>

<!-- MAUVAIS : htmx risque de ne pas s'initialiser correctement -->
<script src="/static/js/htmx.min.js" defer></script>
<script src="/static/js/htmx.min.js" type="module"></script>
```

#### 6. Cibler `<body>` force toujours un `innerHTML`

Même si on met `hx-swap="outerHTML"`, cibler le `<body>` fait toujours
un `innerHTML`. C'est un comportement historique de htmx. En pratique,
ça veut dire qu'on ne peut pas modifier les attributs du `<body>` via
un swap htmx — il faut passer par un event `htmx:afterSettle` si besoin.

#### 7. Les requêtes GET sur éléments non-formulaire ignorent le formulaire parent

Un bouton avec `hx-get` à l'intérieur d'un `<form>` n'enverra PAS les
valeurs du formulaire. C'est différent du comportement en `hx-post`.
Utiliser `hx-include` pour inclure explicitement les champs nécessaires.

```html
<form>
    <input name="search" type="text">
    <!-- Ce bouton N'ENVOIE PAS la valeur de "search" par défaut -->
    <button hx-get="/search" hx-target="#results">Chercher</button>

    <!-- Correction : inclure explicitement le champ -->
    <button hx-get="/search" hx-target="#results"
            hx-include="[name='search']">Chercher</button>
</form>
```

## Toasts / Notifications

Pattern: use `django.messages` + `HX-Trigger` header. Never return JSON to drive UI.

```python
def delete(self, request, pk=None):
    book = get_object_or_404(Book, uuid=pk)
    book_title_for_message = book.title  # Sauvegarder AVANT suppression / Save BEFORE deletion
    book.delete()

    messages.add_message(request, messages.SUCCESS,
        f'"{book_title_for_message}" supprime / deleted')

    messages_list = get_messages(request)
    toast_payload = [{"level": m.level_tag, "text": str(m)} for m in messages_list]

    response = render(request, "books/partials/empty.html")
    response["HX-Trigger"] = json.dumps({"toast": {"items": toast_payload}})
    return response
```

## i18n (Internationalization)

Every user-visible text must be translatable. Use `{% translate %}` for short strings and `{% blocktrans %}` for sentences with variables.

**Source text in French by default.** The string written inside `{% translate "..." %}` / `_()` is the **French** label; the English translation is generated *from* the French (never the other way around). Do not create new msgids in English. (Older code still has English msgids — do not convert them out of scope, but stop adding new ones.)

```html
<!-- Texte simple / Simple text -->
<span>{% translate "Cloture" %}</span>

<!-- Texte avec variables / Text with variables -->
<p class="visually-hidden mb-0">
    {% blocktrans with percent=initiative.progress_percent_int goal=initiative.total_funding_amount %}
        Avancement du financement : {{ percent }} pour cent sur un objectif de {{ goal }}.
    {% endblocktrans %}
</p>
```

In Python views and serializers:
```python
from django.utils.translation import gettext_lazy as _

messages.add_message(request, messages.SUCCESS, _("Réservation créée !"))
```

Error messages in serializers should also use `_()`:
```python
raise serializers.ValidationError(_('A book with this title already exists'))
```

## Accessibility

Accessibility is not optional. The project must work with screen readers (NVDA, VoiceOver, etc.). Every template must follow these rules:

1. **Decorative icons** are hidden from screen readers:
```html
<i class="bi bi-piggy-bank me-1" aria-hidden="true"></i>{{ config.name_goal }}
```

2. **Meaningful groups** get `aria-label`:
```html
<p class="mb-2" aria-label="Tags">
    {% for tag in initiative.tags.all %}
        <span class="badge">{{ tag.name }}</span>
    {% endfor %}
</p>
```

3. **Visual-only data** gets a `visually-hidden` text equivalent for screen readers:
```html
<div class="progress" style="height: .5rem;">
    <div class="progress-bar" role="progressbar"
         aria-valuenow="{{ percent }}" aria-valuemin="0" aria-valuemax="100">
    </div>
</div>
<p class="visually-hidden">
    {% blocktrans with percent=percent %}Progress: {{ percent }} percent{% endblocktrans %}
</p>
```

4. **Dynamic content regions** use `aria-live` so screen readers announce updates after HTMX swaps:
```html
<!-- Zone mise a jour par HTMX — le lecteur d'ecran annonce les changements -->
<!-- Region updated by HTMX — screen reader announces changes -->
<div id="search-results" aria-live="polite">
    {% include "partials/search_results.html" %}
</div>
```

5. **Semantic roles** on interactive containers:
```html
<form role="search" action="" method="get"
      hx-get="{% url 'initiative-list' %}" hx-target="#results">
    ...
</form>

<div class="btn-group" role="group" aria-label="{% translate 'Actions' %}">
    ...
</div>
```

6. **Spinners and loading states** are announced:
```html
<div class="spinner-border text-primary" role="status">
    <span class="visually-hidden">{% translate "Chargement..." %}</span>
</div>
```

7. **Use Bootstrap semantic classes** (`text-body`, `text-muted`, `bg-body-tertiary`) to respect light/dark themes.

## Test Attributes (`data-testid`)

Every interactive element and every meaningful content block must have a `data-testid` attribute. This serves two purposes:
- **E2E testing** (Playwright) can locate elements reliably without depending on CSS classes or text content
- **Accessibility auditing** tools can identify testable regions

Naming convention: `<module>-<element>-<context>`, all lowercase with hyphens.

```html
<!-- Boutons d'action / Action buttons -->
<button type="submit" class="btn btn-warning btn-sm" data-testid="btn-close">
    {% translate "Cloturer" %}
</button>

<!-- Conteneurs de contenu / Content containers -->
<div class="card" data-testid="crowds-summary">
    ...
</div>

<!-- Panneaux ouvrants / Expandable panels -->
<a class="btn btn-primary" data-testid="booking-open-panel"
   hx-get="{% url 'booking-form' pk=event.uuid %}" hx-target="#booking-container">
    {% translate "Reserver" %}
</a>

<!-- Badges et indicateurs / Badges and indicators -->
<span class="badge bg-secondary" data-testid="badge-closed">
    <i class="bi bi-lock" aria-hidden="true"></i> {% translate "Cloture" %}
</span>
```

When writing a new template, think: "Could a Playwright test or a screen reader find this element?" If not, add `data-testid` and the appropriate ARIA attribute.

## Multi-Tenancy (django-tenants)

Cette section s'applique uniquement aux projets multi-tenant.
This section applies only to multi-tenant projects.

**Projets multi-tenant / Multi-tenant projects :** TiBillet, Lespass
**Projets single-tenant / Single-tenant projects :** O2Badge, Hypostasia, et tout autre projet qui n'utilise pas `django-tenants`

Si le projet sur lequel tu travailles n'est pas dans la liste multi-tenant ci-dessus,
ignore cette section entierement.
If the project you are working on is not in the multi-tenant list above,
ignore this section entirely.

---

Pour les projets multi-tenant, chaque vue s'execute dans un schema de base de donnees
propre au tenant. Etre attentif dans ces cas :
For multi-tenant projects, every view runs inside a tenant schema. Be aware of this when:

- **Building cache keys** — always include the tenant ID:
```python
from django.db import connection

def _cache_key(tenant_id, user_id):
    return f"mymodule:data:{tenant_id}:{user_id}"

tenant_id = connection.tenant.pk
cache_key = _cache_key(tenant_id, user.pk)
```

- **Passing tenant to external services** (e.g. Stripe metadata):
```python
stripe_metadata = {
    "tenant": f"{connection.tenant.uuid}",
    "object_uuid": f"{obj.pk}",
}
```

- **Tenant-scoped singletons** (via django-solo): `Configuration.get_solo()` returns the config for the current tenant automatically.

### Executer du code dans le contexte d'un tenant specifique

Quand une tache de fond (Celery, management command, script) doit agir sur
les donnees d'un tenant precis, utiliser `tenant_context` pour se placer
dans le bon schema.
When a background task needs to act on a specific tenant's data, use
`tenant_context` to switch to the correct schema.
```python
from django_tenants.utils import tenant_context
from customers.models import Client  # Le modele tenant de ton projet
# / The tenant model of your project

# Recuperer le tenant cible
# / Get the target tenant
tenant_to_process = Client.objects.get(schema_name="nom_du_tenant")

# Executer du code dans le contexte de ce tenant
# / Execute code in the context of this tenant
with tenant_context(tenant_to_process):
    # Toutes les requetes ici s'executent dans le schema du tenant
    # / All queries here run inside the tenant's schema
    reservations_a_relancer = Reservation.objects.filter(
        status="pending",
        send_reminder=False,
    )
    for reservation in reservations_a_relancer:
        send_reminder_email(reservation)
```

Pour iterer sur **tous les tenants** (ex: tache Celery globale) :
To iterate over **all tenants** (e.g. global Celery task):
```python
from django_tenants.utils import tenant_context
from customers.models import Client

# Recupere tous les tenants actifs — exclut le schema public
# / Get all active tenants — excludes public schema
all_active_tenants = Client.objects.filter(is_active=True)

for tenant in all_active_tenants:
    with tenant_context(tenant):
        # Traitement isole par tenant
        # / Isolated processing per tenant
        do_something_for_this_tenant(tenant)
```

### Piege : "relation does not exist" = schema public

Si une requete leve `ProgrammingError: relation "BaseBillet_xxx" does not exist`,
c'est presque toujours parce que le code tourne sur le **schema public**.
Les tables des TENANT_APPS n'existent que dans les schemas tenant.

If a query raises `ProgrammingError: relation "BaseBillet_xxx" does not exist`,
it's almost always because the code runs on the **public schema**.
TENANT_APPS tables only exist in tenant schemas.

**Diagnostic rapide / Quick diagnostic:** `print(connection.schema_name)` — si ca affiche `"public"`, c'est confirme.

**Causes frequentes / Common causes:**
- Management command lancee via `docker exec` sans `tenant_context`
- `connection.schema_name` vaut `"public"` par defaut (hors middleware HTTP)
- `call_command()` depuis une autre commande : le schema n'est pas herite si la commande appelee re-set le contexte

**Pattern correct pour une management command qui touche des TENANT_APPS :**
**Correct pattern for a management command that touches TENANT_APPS:**
```python
from django.db import connection
from django_tenants.utils import schema_context
from Customers.models import Client

class Command(BaseCommand):
    def handle(self, *args, **options):
        # Si deja dans un tenant_context (schema != "public"), on l'utilise.
        # Sinon (lancement standalone), on prend le premier tenant non-public.
        # / If already in a tenant_context, use it. Otherwise, pick the first tenant.
        schema = connection.schema_name
        if schema == "public":
            tenant = Client.objects.exclude(schema_name="public").first()
            if not tenant:
                self.stderr.write("Aucun tenant trouve.")
                return
            schema = tenant.schema_name

        with schema_context(schema):
            # ... code qui touche des TENANT_APPS
```

### Migrations de donnees (data migrations)

Les tables des TENANT_APPS n'existent **pas** dans le schema `public`.
Une data migration qui tente d'y acceder depuis `public` leve une erreur.
Toujours verifier le schema courant en debut de fonction et retourner
immediatement si on est dans `public`.

The tables of TENANT_APPS do **not** exist in the `public` schema.
A data migration that tries to access them from `public` will raise an error.
Always check the current schema at the start of the function and return
immediately if running in `public`.
```python
"""
Migration de donnees : exemple de pattern securise pour TENANT_APPS.
/ Data migration: safe pattern example for TENANT_APPS.
"""
from django.db import connection, migrations


def nom_explicite_de_la_migration(apps, schema_editor):
    """
    Corrige les donnees dans MonModele pour tous les tenants.
    / Fixes data in MyModel for all tenants.

    IMPORTANT : MonModele est une TENANT_APP.
    La table n'existe pas dans le schema public.
    On retourne immediatement si on est dans public.

    IMPORTANT: MyModel is a TENANT_APP.
    The table does not exist in the public schema.
    We return immediately if running in public.
    """
    # Verification du schema — protection obligatoire pour les TENANT_APPS
    # / Schema check — mandatory guard for TENANT_APPS
    schema_courant = connection.schema_name
    schema_est_public = (schema_courant == 'public')

    if schema_est_public:
        # On ne fait rien dans le schema public — la table n'existe pas ici
        # / Do nothing in public schema — the table does not exist here
        return

    # Recupere le modele via l'historique de migration (pas d'import direct)
    # / Get the model via migration history (no direct import)
    MonModele = apps.get_model('MonApp', 'MonModele')

    # Applique la correction et compte les lignes modifiees
    # / Apply the fix and count modified rows
    nombre_de_lignes_modifiees = MonModele.objects.filter(
        champ_a_corriger="valeur_incorrecte",
    ).update(
        champ_a_corriger="valeur_correcte",
    )

    # Affiche un resume si des lignes ont ete modifiees
    # / Print a summary if rows were modified
    if nombre_de_lignes_modifiees:
        print(
            f"  -> [{schema_courant}] "
            f"{nombre_de_lignes_modifiees} ligne(s) corrigee(s)"
        )


class Migration(migrations.Migration):
    dependencies = [
        ('MonApp', '0001_previous_migration'),
    ]

    operations = [
        migrations.RunPython(
            nom_explicite_de_la_migration,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
```

## Template Structure

Les skins vivent dans **`pages/templates/pages/<skin>/`** (et NON dans
`BaseBillet/templates/`, qui etait l'ancien emplacement).

```
pages/templates/pages/
+-- classic/              # Le SOCLE : filet de securite permanent.
|   +-- shell.html        #   Squelette complet (HTMX, CSRF, toasts)
|   +-- headless.html     #   Sans habillage — pour les reponses HTMX
|   +-- page.html
|   +-- partials/
|   +-- vues/
+-- faire_festival/       # Un skin : ne surcharge que ce qu'il veut
```

`gabarit_skin("shell.html")` renvoie `pages/<skin>/shell.html` si le skin courant le
fournit, **sinon** il retombe automatiquement sur `pages/classic/shell.html`. Un skin n'a
donc besoin de redefinir que les gabarits qu'il veut changer.

Le squelette s'appelle **`shell.html`** — plus `base.html`.

## Admin Templates (Django Unfold)

When creating custom templates for the Django Unfold admin, **always use inline styles** for custom styling. Unfold bundles its own Tailwind subset — custom Tailwind classes like `bg-yellow-600` or `text-red-500` are NOT included and will render invisible (white on white).

```html
<!-- BON : styles inline, toujours visibles -->
<!-- GOOD: inline styles, always visible -->
<button style="background-color: #d97706; color: white; padding: 8px 16px; border-radius: 6px;">
    {% translate "Annuler avec avoir" %}
</button>

<!-- MAUVAIS : classes Tailwind custom absentes du bundle Unfold -->
<!-- BAD: custom Tailwind classes missing from Unfold bundle -->
<button class="bg-yellow-600 text-white px-4 py-2 rounded-md">
    {% translate "Annuler avec avoir" %}
</button>
```

Use Unfold CSS variables when available: `var(--color-primary-600)`, `var(--color-base-0)`, etc.

## CHANGELOG Workflow

Chaque feature, correction ou changement notable produit **un fichier par chantier** dans le dossier `CHANGELOG/` a la racine du projet. Ce fichier fusionne deux besoins autrefois separes (l'entree CHANGELOG **et** la fiche « a tester ») : **une seule ecriture, deux lecteurs**.

### Nommage

`CHANGELOG/YYYY-MM-DD-slug.md` — date du jour + slug court et parlant (`newsletter-sommaire-ancres`, `avoir-credit-note`, `fk-reservation-lignearticle`). Un chantier qui s'etale sur plusieurs jours = on **edite le meme fichier** (on ne le renomme pas, on ne recree pas).

### Format

```markdown
# Titre FR / Title EN

**Date :** 2026-07-15
**Migration :** Non   (si Oui : nom de la migration + commande)

## Resume / Summary
**Quoi / What :** description courte de ce qui a change (bilingue).
**Pourquoi / Why :** raison du changement (bilingue).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `module/file.py` | Description courte |

---

## Comment tester (a la main) / Manual test
### Test 1 — scenario nominal
1. Etape 1
2. Etape 2
3. Verification attendue

### Test 2 — cas limites
...

### Verifs DB / Playwright
- Commandes `docker exec ... manage.py shell` pour verifier en base si pertinent
- Scenario Playwright a ecrire ou existant
```

### Regles

1. **Le `---` separe les deux publics.** Au-dessus : le resume concis, bilingue, chronologique (l'ancienne entree CHANGELOG). En dessous : le detail humain « comment verifier a la main » (l'ancienne fiche « A TESTER »).
2. **Bilingue FR/EN** pour l'entete (titre + Quoi/Pourquoi). Le detail des tests manuels peut rester en FR.
3. **Un fichier par chantier**, cree **en meme temps que le code** — pas apres, pas plus tard.
4. **Flag migration** toujours renseigne (Oui/Non) dans l'entete.
5. **Vue chronologique** = le prefixe date des noms de fichiers + `git log`. Pas de gros fichier `CHANGELOG.md` unique (supprime), pas de sous-dossier `TEST_OK` (les tests auto sont la garantie ; les scenarios manuels restent une doc de reference).
6. **Refactoring interne sans impact utilisateur** : creer quand meme le fichier, avec la mention « Refactoring interne / Internal refactoring ».

## i18n (Traductions FR/EN)

### INTERDIT : ne JAMAIS lancer makemessages ni compilemessages toi-meme

**`makemessages` et `compilemessages` sont lances par le MAINTENEUR, jamais par toi.**

`makemessages` rescanne TOUT le projet : il reecrit les deux fichiers `.po` en entier,
deplace des centaines de lignes sans rapport avec ta session, et fabrique des traductions
« fuzzy » fausses. Le mainteneur se retrouve avec un diff illisible qu'il n'a pas demande.

Ce que tu fais a la place, quand ta feature ajoute des textes visibles :

1. Ecrire les chaines avec `_()`, `{% translate %}`, `{% blocktrans %}` — **msgid en FRANCAIS**
   (langue de reference du projet). Ne plus creer de msgid en anglais. Du code ancien en a
   encore : ne pas les convertir hors session.
2. **Le signaler au mainteneur** dans ton rapport de fin : « cette feature ajoute N chaines
   traduisibles, le workflow i18n est a lancer ».
3. Si le mainteneur demande le travail de traduction, c'est le skill **`i18n-translate`** qui
   pilote — et lui non plus ne lance pas `makemessages`.

### Texte source en francais

Le texte ecrit dans `_("...")` est le **francais**. La traduction anglaise en est deduite,
jamais l'inverse. Le `.po` FR a donc `msgid` = `msgstr` (FR) ; le `.po` EN porte l'anglais.

## Code Navigation — Recherche dans le Projet

Quand Claude Code cherche a localiser du code existant dans le projet
(avant d'ecrire une vue, un serializer, ou un template), utiliser
`ripgrep` (`rg`) plutot que `grep` ou `cat`.

### Pourquoi ripgrep plutot que grep ?

`grep` cherche dans TOUT — y compris `node_modules`, `.git`, les fichiers
compiles et les fichiers binaires. C'est lent et bruyant sur un gros projet.

`ripgrep` respecte automatiquement `.gitignore`, est ecrit en Rust (tres rapide),
et affiche les resultats avec coloration et numero de ligne.

Les deux font une recherche **textuelle exacte**. Pour une recherche par sens,
utiliser des termes plus generiques ou plusieurs recherches ciblees.

### Commandes utiles
```bash
# Chercher un mot dans tout le projet
# / Search a word across the whole project
rg "stripe"

# Chercher uniquement dans les fichiers Python
# / Search only in Python files
rg "stripe" -t py

# Chercher uniquement dans les templates HTML
# / Search only in HTML templates
rg "hx-post" -t html

# Chercher avec contexte (3 lignes avant et apres)
# / Search with context (3 lines before and after)
rg "def process_payment" -C 3

# Chercher le nom d'une classe ou d'une fonction precise
# / Search for a specific class or function name
rg "class ReservationViewSet"
rg "def toggle_publish"

# Chercher dans un sous-dossier specifique
# / Search in a specific subfolder
rg "reservation" ./BaseBillet/

# Lister uniquement les fichiers qui contiennent le mot
# / List only files containing the word
rg "stripe" -l
```

### Regle d'usage pour Claude Code

Avant d'ouvrir un fichier entier avec `cat`, utiliser `rg` pour localiser
precisement les lignes pertinentes. Cela evite de charger des centaines
de lignes inutiles dans le contexte.

| Situation | Commande a eviter | Commande a utiliser |
|---|---|---|
| Trouver une vue metier | `cat views.py` (fichier entier) | `rg "def.*paiement" -t py` |
| Trouver un template | `find . -name "*.html"` | `rg "reservation" -t html -l` |
| Localiser un serializer | `grep -r "Serializer" .` | `rg "class.*Serializer" -t py` |
| Trouver un signal Django | `grep -r "post_save" .` | `rg "post_save" -t py` |
| Chercher un ID HTML | `grep -r "bt-valider" .` | `rg "bt-valider" -t html` |

## CSS Extraction — Ordre de cascade

Quand on extrait du CSS inline (`<style>` blocks) vers des fichiers `.css` externes charges via `<link>` dans le `<head>` :

**Probleme** : Dans le HTML original, les `<style>` des composants (Cotton, partials) dans le `<body>` apparaissent APRES le `{% block css %}` du `<head>`. Les composants gagnent la cascade naturellement. Avec des fichiers externes tous dans le `<head>`, c'est l'ordre des `<link>` qui decide.

**Regle** : Charger les fichiers "base/layout" (ex: `views.css`) AVANT les fichiers "composants" (ex: `articles.css`, `addition.css`). Ainsi les composants peuvent surcharger les styles de base, comme dans le code original.

```html
<!-- BON : layout d'abord, composants ensuite -->
<link rel="stylesheet" href="{% static 'css/views.css' %}" />
<link rel="stylesheet" href="{% static 'css/articles.css' %}" />

<!-- MAUVAIS : articles.css surcharge par views.css -->
<link rel="stylesheet" href="{% static 'css/articles.css' %}" />
<link rel="stylesheet" href="{% static 'css/views.css' %}" />
```

**Verification** : Toujours verifier visuellement dans Chrome apres extraction CSS, AVANT de lancer les tests.

## Operations destructives — interdictions absolues

Ces regles protegent le working tree du mainteneur. Le projet Lespass
peut avoir plusieurs heures de travail non committe a un instant T —
une seule commande destructive efface tout.

### Git : aucune ecriture sans accord explicite

**Interdictions strictes** (meme sur suggestion d'un autre outil) :

- `git commit`, `git push`, `git add` — le mainteneur commit lui-meme
- `git checkout -- <file>`, `git restore -- <file>` — efface les
  modifications non committees
- `git stash` — cache les modifications hors working tree, facile a
  perdre si on oublie
- `git reset --hard`, `git reset HEAD~` — destructif
- `git clean -f`, `git clean -fd` — supprime les fichiers untracked
- `git branch -D`, `git worktree remove --force`

**Incident de reference** : Session 32 (2026-04-20), un subagent a
lance `git checkout -- BaseBillet/views.py` pour annuler un reformat
ruff indesirable. Resultat : 4h de dev Session 32 (dispatch V2 +
helpers + methodes) effaces. Restauration par PyCharm local history.

### Brief des subagents : l'interdiction git EN TETE

Quand on dispatch un subagent, la regle "no git" doit apparaitre en
premiere ligne apres le titre, pas en milieu de bullet list. Exemple :

```
You are implementing Task N of Session XX.

## HARD RULE — READ FIRST
NEVER run git commands: no commit, no push, no add,
AND no checkout --, no stash, no reset --hard, no restore --,
no clean -f. The maintainer handles ALL git operations.
If your task says "Commit", OUTPUT the suggested message
in your final report and STOP.
```

Ne jamais se contenter d'un bullet "NEVER execute git commands" au
milieu d'une liste de 10 regles — le subagent peut le rater.

### `ruff format` ET `ruff check --fix` sont dangereux sur les fichiers existants

Les deux commandes peuvent casser un fichier pre-existant, **pour des raisons
differentes**. Ne pas se fier a l'idee (fausse — elle a deja casse Lespass) que
« seul `format` est dangereux, `--fix` est sans risque ».

| Commande | Le danger sur un fichier pre-existant |
|---|---|
| `ruff format` | **Reformate le fichier ENTIER** : indentation, guillemets, sauts de ligne, sur des milliers de lignes que tu n'as pas ecrites → diff enorme non lie a la session. |
| `ruff check --fix` | Supprime les **imports a effet de bord nus** (F401) : un import dont le seul but est d'**executer** le module (`@admin.register`, `@receiver`, `@app.task`) est vu comme « mort » et **supprime en silence**. L'enregistrement disparait → `admin.E039`, **Django ne boote plus**. Incident reel : `from Administration.admin import (products, prices)` supprime → **319 tests en erreur**, symptome a des kilometres de la cause. |

**Ne jamais se fier au `# noqa: F401`** : rien ne garantit que tous les imports a
effet de bord soient proteges (audit Lespass : 141 imports F401 « fixables », aucune
config ruff a l'epoque).

**Regle** :
- **Fichier NEUF** (cree dans la session) → `ruff check --fix` **et** `ruff format` : rien a casser, il n'existait pas avant toi.
- **Fichier PRE-EXISTANT** :
  - `ruff format` → **jamais**.
  - `ruff check --fix` → seulement apres avoir **inspecte a la main** les imports « inutilises » (surtout `admin*.py`, `apps.py`, `signals.py`, `triggers.py`, `settings.py`, `__init__.py`), **puis** lance `manage.py check` **et la suite complete** (pas seulement les tests du domaine touche).

La parade durable est en place : `[tool.ruff.lint.per-file-ignores]` dans `pyproject.toml`
interdit F401 sur ces fichiers, plus un test qui echoue si un enregistrement d'admin disparait.

Si un `--fix` ou un `format` produit un diff qui te surprend : **ne rollback pas avec git**,
previens le mainteneur.

### En cas de reformat indesirable ou de modification accidentelle

**Ne PAS tenter de rollback via git.** Alerter le mainteneur,
documenter precisement ce qui s'est passe, et attendre ses
instructions. Options possibles :

- PyCharm local history (si IDE ouvert cote mainteneur)
- `git stash` manuel par le mainteneur
- Resaisie du code depuis la doc de session (plan ou spec)
- `git reset --hard` par le mainteneur si c'est le bon choix

Le mainteneur decide. Jamais l'assistant.

## Anti-Patterns to Avoid

| Don't | Do Instead | Why |
|-------|------------|-----|
| `ModelViewSet` | `ViewSet` with explicit methods | Magic hides logic |
| Django Forms **dans une vue** | DRF Serializers | Separe la validation du rendu. (Exception : dans l'admin Unfold, le `ModelForm` est le seul mecanisme possible — voir le skill `unfold`) |
| JSON responses for UI | HTML partials + `HX-Trigger` | Server-rendered, no client routing |
| `window.xxx = {{ data\|safe }}` dans un template | `data-*` sur l'élément HTML + partial HTMX pour les mises à jour | Le JS ne doit pas porter de logique métier |
| `{% load json_script %}` | Rien — c'est un filtre natif, pas une library | `{% load json_script %}` lève une `TemplateSyntaxError` |
| `hx-swap` on `<html>` or `<head>` | `hx-target="body" hx-swap="innerHTML"` | Prevents asset reload blink |
| Complex comprehensions | Simple for loops | FALC readability |
| Hardcoded strings in templates | `{% translate %}` / `_()` | i18n required |
| Icons without `aria-hidden="true"` | Add `aria-hidden="true"` on decorative icons | Accessibility |
| HTMX target without `aria-live` | Add `aria-live="polite"` on dynamic regions | Screen readers miss updates |
| Interactive element without `data-testid` | Add `data-testid="module-element-context"` | E2E tests break on class changes |
| Cache keys without tenant ID | Include `connection.tenant.pk` | Multi-tenant isolation |
| Server-side validation only | Add `htmx:configRequest` client check too | Fewer unnecessary round-trips |
| `get_queryset()` / `get_serializer_class()` | Inline explicit queries and serializer calls | No hidden dispatch |
| Tailwind classes in Unfold admin | Inline styles or CSS variables | Custom classes not in Unfold bundle |
| Lancer `makemessages` / `compilemessages` toi-meme | Ecrire les `_()` en FR, puis SIGNALER au mainteneur que le workflow i18n est a lancer | `makemessages` reecrit les deux `.po` en entier et fabrique des fuzzy faux |
| Skip CHANGELOG / oublier la fiche de test | Un fichier `CHANGELOG/YYYY-MM-DD-slug.md` : resume en haut, comment tester en bas (separes par `---`) | Changement non trace + non testable par le mainteneur |
| `git checkout --`, `git stash`, `git reset --hard` | Alerter le mainteneur, attendre ses instructions | Efface le travail non committe (incident Session 32 : 4h perdues) |
| `ruff format <fichier-existant>` | Ne lancer que sur des fichiers **neufs** ; sinon alerter le mainteneur | Reformate des milliers de lignes pre-existantes non liees a la session |
| `ruff check --fix` sur `admin*.py`, `apps.py`, `signals.py`, `triggers.py`, `settings.py`, `__init__.py` | Inspecter **a la main** les imports « inutilises » AVANT ; apres tout `--fix` lancer `manage.py check` + la suite complete | `--fix` supprime les imports a effet de bord **nus** (`@admin.register`, `@receiver`) → `admin.E039`, Django ne boote plus (incident : 319 tests en erreur) |

## Tests

### Lancer les tests → skill `tibillet-test`

**Pour LANCER ou DIAGNOSTIQUER les tests, utilise le skill `tibillet-test`.** Il porte les
commandes a jour, l'arbre de decision des echecs typiques de ce projet (schemas `test_*`
perimes, fuite de schema multi-tenant, `502` quand le serveur est down) et la procedure de
purge a froid.

Ne duplique PAS ces commandes ici : c'est exactement comme ca que ce skill s'est mis a
mentir (il a longtemps annonce « 234 tests, ~70s » alors qu'il y en a 787, et renvoyait
vers un `tests/TESTS_README.md` supprime depuis).

**Regle de session** : apres toute modification significative, lancer les tests du domaine
touche. Ne pas attendre la fin de la session.

### Ou ecrire le test : pytest ou E2E ?

| La chose testee… | Ou |
|---|---|
| est du **Python** (modele, serializer, vue, API, validation serveur) | `tests/pytest/` |
| est du **JS / CSS / navigateur** (web component, SweetAlert2, swap HTMX, NFC) | `tests/e2e/` (Playwright) |
| est les **deux** | pytest pour le serveur, E2E pour le rendu |

Les tests pytest **ne peuvent pas** executer de JavaScript (pas de navigateur).
Les tests E2E **ne peuvent pas** faire de ROLLBACK DB (pas de LiveServer avec django-tenants).

### Regles d'or pour ecrire un test

1. **Atomique** — un test fait une seule chose. Un test = une action.
2. **Noms verbeux** — noms longs et clairs, pas d'abreviations.
3. **Bilingue FR/EN** — commentaires en francais, resume anglais.
4. **FALC** — mots simples, comprehensibles par tous.
5. **Deux `conftest.py` separes** — `tests/pytest/conftest.py` (fixtures DB) et
   `tests/e2e/conftest.py` (fixtures navigateur) sont independants. Ne pas creer de
   conftest a la racine.

**AVANT d'ecrire un test, lire `tests/PIEGES.md`** (~155 pieges documentes). Les plus
frequents, en multi-tenant : `schema_context()` pose un `FakeTenant` (tout modele qui lit
`connection.tenant.uuid` plante → utiliser `tenant_context()`), `CarteCashless` est en
SHARED_APPS (schema `public`), et `_, _created = get_or_create()` casse `gettext` (`_` en
variable locale).

### Verification du code Python (ruff)

Apres chaque modification de fichier Python :

| Le fichier est… | Commande | Pourquoi |
|---|---|---|
| **neuf** (cree dans la session) | `ruff check --fix <fichier>` puis `ruff format <fichier>` | Rien a casser : il n'existait pas avant toi |
| **pre-existant** | **JAMAIS `ruff format`** ; `ruff check --fix` seulement apres inspection manuelle des imports « inutilises » + `manage.py check` + suite complete | `format` reformate le fichier ENTIER (des milliers de lignes que tu n'as pas ecrites). `--fix` supprime les imports a effet de bord **nus** (`@admin.register`) → `admin.E039`, Django ne boote plus. |

**Les DEUX sont dangereux sur un fichier pre-existant**, pas seulement `format`.
Voir « `ruff format` ET `ruff check --fix` sont dangereux sur les fichiers existants »
plus haut (incidents : reformat de milliers de lignes ; suppression d'imports → 319 tests en erreur).

## References

For complete working examples with full CRUD, pagination, filtering, and more patterns:
- `references/viewset-patterns.md` — Full ViewSet implementations (CRUD, read-only, relations)
- `references/htmx-patterns.md` — 10 HTMX interaction patterns (search, confirm, infinite scroll, tabs, upload, polling)

## Evaluation

- `evals/evals.json` — 6 evaluation prompts (French)
- `evals/evals_en.json` — Same evaluations in English
- `evals/guide_evaluations.md` — How to run and interpret evals

