# SPEC — Brouillons de newsletter Ghost depuis les événements fédérés

> **Hub :** [INDEX.md](INDEX.md)
> **Prérequis :** [CHANTIER-01 — Redresser la sémantique des tags fédérés](CHANTIER-01-semantique-tags-federes.md)
> **Date :** 2026-07-13 · **Branche :** `main-newsletter` (partie de `main`)
> **Statut :** relue (agent Fable 5) et corrigée. Prête pour le plan d'implémentation.
>
> **Contraintes projet :** aucune opération git de l'assistant · pas de `makemessages` /
> `compilemessages` auto · serveur tenu par le mainteneur dans byobu ·
> `ruff format` **jamais** sur un fichier pré-existant.

---

## 1. Objectif

Un gestionnaire de tenant Lespass anime une instance **Ghost** auto-hébergée (blog +
newsletter). Chaque semaine ou chaque mois, il veut envoyer à ses abonnés l'agenda des
événements à venir — **les siens et ceux de son réseau fédéré**. Aujourd'hui il recopie tout à
la main dans l'éditeur Ghost.

Un bouton dans l'admin Lespass doit **fabriquer le brouillon à sa place**. Il ne lui reste qu'à
relire, élaguer, et envoyer depuis Ghost.

**Ce qu'on ne fait pas :** publier, ou envoyer l'email. Le post est créé en `status: draft`, et
rien d'autre. **L'envoi reste un geste humain, dans Ghost.**

---

## 2. Ce qui existe déjà (à réutiliser, pas à réécrire)

Vérifié sur `main-newsletter`.

| Brique | Emplacement | Ce qu'elle fait |
|---|---|---|
| `GhostConfig` | `BaseBillet/models.py:3700` | Singleton **par tenant**. `ghost_url`, `ghost_key` (chiffrée Fernet : `get_api_key()` / `set_api_key()`), `ghost_last_log`. |
| `GhostConfigAdmin` | `Administration/admin_tenant.py:3740` | L'admin Unfold. Il a **déjà** `actions_detail = ["test_api_ghost_admin_button"]` — on **ajoute** à cette liste, on ne la remplace pas. |
| Génération du JWT Ghost | `BaseBillet/tasks.py:1562` (`send_to_ghost_email`) | Le pattern officiel : `HS256`, header `kid`, payload `iat` / `exp` (+5 min) / `aud: /admin/`, secret décodé depuis l'hexa. |
| `FederatedPlace` | `BaseBillet/models.py:3659` | Les voisins fédérés : `tenant` (FK → `Client`), `tag_filter`, `tag_exclude`. |
| `federated_events_filter` | `BaseBillet/views.py:1881` | Le **moteur de l'agenda fédéré**. Non réutilisable tel quel (méthode de ViewSet, cachée, paginée), mais c'est la **référence de comportement** : la newsletter doit montrer le même ensemble d'événements que l'agenda. |
| `Event.full_url` | `BaseBillet/models.py:1895` | **Calculé à chaque `save()`.** `https://{domaine}/event/{slug}/` pour un event interne ; l'URL du site tiers si `is_external=True`. **À utiliser tel quel** — ne pas reconstruire l'URL à la main. |
| `Event.published_prices()` | `BaseBillet/models.py:1822` | Les `Price` publiés des produits de l'event. |
| `seo/services.py` | — | `build_stdimage_variation_url()`, et le matching de tags **par slug** entre tenants. |
| `requests`, `pyjwt` | `pyproject.toml` | Déjà là. **Aucune nouvelle dépendance.** |

**Aujourd'hui Ghost sert uniquement à synchroniser les adhérents** vers les *members* Ghost.
Créer un brouillon de post, c'est **la même instance, la même authentification, un autre
endpoint**.

> L'app `pages` et son bloc `NEWSLETTER` (formulaire d'inscription Ghost) existent sur
> `main-fedow-import`, **pas sur `main`**. Cette spec n'en dépend pas.

---

## 3. Décisions de cadrage

| Décision | Choix | Pourquoi |
|---|---|---|
| **Périmètre des events** | Tenant courant **+ son réseau fédéré** | C'est le sens de « fédéré ». |
| **Sémantique des tags** | Celle des `help_text` : `tag_filter` = n'afficher **que** ces tags, `tag_exclude` = **exclure** ces tags | Le moteur fait aujourd'hui l'inverse. **CHANTIER-01 le corrige d'abord.** La newsletter est écrite directement sur la sémantique correcte. |
| **Cohérence avec l'agenda** | La newsletter montre **le même ensemble** d'événements que l'agenda du site | Un abonné qui clique doit retrouver ce qu'il a lu. Impose de reprendre **tous** les filtres du moteur (§6.3). |
| **Déclenchement** | **Deux boutons** dans l'admin : « 7 jours », « 30 jours » | Couvre « hebdo et/ou mensuel » sans formulaire ni cron. |
| **Exécution** | **Synchrone** (pas de Celery) | Quelques requêtes + un POST : < 2 s. Feedback immédiat, lien cliquable. Pas de contexte tenant à repasser à une tâche de fond. |
| **Images** | **Référencées** par URL publique TiBillet | Zéro upload, zéro pollution du storage Ghost quand on régénère un brouillon dix fois en testant. |
| **Format envoyé** | **HTML sémantique** aux conventions `kg-*`, **sans styles inline** | Voir §4. C'est le cœur de la spec. |
| **Contenu par event** | Fiche **complète** | C'est un brouillon : mieux vaut trop de matière à élaguer que d'avoir à aller rechercher une info manquante. |
| **Structure** | Une **app** `newsletter/`, **sans modèle** | Pourra devenir un module de dashboard, et une brique activable/facturable (hébergement Ghost on-premise). `GhostConfig` suffit. Aucune migration. |

---

## 4. Le point technique central : pourquoi du HTML, et lequel

**À lire avant d'écrire une ligne de code.** C'est la partie contre-intuitive.
*(Argument vérifié dans le source de Koenig lors de la relecture — parsers à l'appui.)*

### 4.1 Ghost ne stocke pas du HTML

Le contenu d'un post Ghost est du **Lexical** : un JSON en arbre, avec des **cartes** typées —
`image`, `button`, `header`, `callout`, `bookmark`, `divider`, `html`, `gallery`… (28 types dans
`kg-default-nodes`).

Ghost possède par ailleurs un **système de design newsletter** complet, réglé dans son
interface : couleur de fond, polices, graisse des titres, image d'en-tête, couleur des titres de
section, style des boutons (carré / arrondi / pilule, plein / contour), pied de page.

**L'apparence de la newsletter est donc le travail de Ghost, pas le nôtre.**

### 4.2 Alors pourquoi ne pas envoyer du Lexical ?

Parce que **le format Lexical de Ghost n'est pas documenté.** La doc de l'Admin API ne décrit que
le nœud paragraphe. Le schéma des cartes n'existe que dans le source JavaScript de Koenig, et il
est versionné par Ghost.

Fabriquer du Lexical à la main, ce serait posséder une correspondance JSON non documentée,
fragile, à revalider à chaque montée de version — **pour un bénéfice nul.**

### 4.3 Le HTML reconstruit les cartes natives — c'est prévu pour

Le convertisseur `?source=html` (`kg-html-to-lexical`) enregistre **tous** les nœuds Koenig
(`...DEFAULT_NODES`) et laisse chacun parser le DOM via son `importDOM()`.

Vérifié dans le source de `TryGhost/Koenig` :

- **`image-parser.ts`** — un `<img>` devient une **carte image native** (`src`, `alt`, `title`,
  dimensions conservés). Un `<figure><img><figcaption>` devient une carte image **avec légende**.
  Les classes `kg-width-wide` / `kg-width-full` pilotent la largeur.
- **`button-parser.ts`** — un `<div class="kg-button-card">` contenant un `<a class="kg-btn" href>`
  devient une **carte bouton native**. L'alignement vient d'une regex `kg-align-(left|center)` :
  **`kg-align-center` est valide, `kg-align-right` n'existe pas.**
- **`horizontalrule-parser.ts`** — `<hr>` devient une **carte divider**.
- `<h2>`, `<p>`, `<a>`, listes, citations : nœuds Lexical de base.

C'est **voulu** : Ghost rend Lexical → HTML avec ses classes `kg-*`, et sait relire ce HTML pour
reconstituer les cartes. **Le round-trip fait partie de la conception.**

**En émettant les conventions `kg-*`, on obtient exactement les mêmes objets natifs qu'en postant
du Lexical — mais par le chemin documenté et supporté.** Le brouillon s'ouvre dans l'éditeur Ghost
en **cartes manipulables**, pas en pavé HTML opaque.

### 4.4 La règle qui en découle : aucun style inline

La doc Ghost prévient que la conversion est **lossy** (« the HTML rendered by Ghost may be
different from the source HTML »). Ce n'est pas un problème **si** on n'envoie que des structures
que Ghost sait mapper — ce qui est exactement le cas du §4.5.

En stylant nous-mêmes (attributs `style`, tableaux de mise en page), on court-circuiterait le
système de design de Ghost et on deviendrait responsable de la compatibilité Outlook / Gmail /
mode sombre. **On ne le fait pas.**

> **Filet de sécurité, en dernier recours seulement :**
> `<!--kg-card-begin: html-->…<!--kg-card-end: html-->` force une carte HTML sans perte.
> Ce bloc n'est **ni stylé par Ghost, ni éditable en cartes**. Pas pour le rendu nominal.

### 4.5 Le mapping retenu, pour une fiche d'événement

**Décision du 2026-07-13, prise après essai bout-en-bout sur une vraie instance Ghost 6.52 :**
chaque événement est une **carte `product`**, suivie de sa description longue en paragraphes.

La carte `product` de Ghost (image + titre + description + bouton) est *exactement* une fiche
d'événement. Elle se reconstruit depuis le HTML (`product-parser.ts`), Ghost la style avec la
couleur d'accent du site, et — argument décisif — **elle possède un renderer email dédié**
(`product-renderer.ts`, sortie en `<table>`) : Ghost sait la transformer en HTML d'email
compatible avec tous les clients. Du HTML brut n'aurait jamais eu ça.

| Élément | HTML émis | Objet dans Ghost |
|---|---|---|
| L'événement (image, nom, lieu, date, tarif, bouton) | `<div class="kg-card kg-product-card">` — structure canonique ci-dessous | **Carte product** |
| Description **longue** | **brute, telle quelle**, en paragraphes SOUS la carte — voir §7.2 | Paragraphes / listes / gras |
| Séparation entre deux events | `<hr>` | **Carte divider** |

**Pourquoi la description longue reste HORS de la carte :** dans la carte, elle passerait en petit
gris clair (le style de `productDescription`). Sur dix lignes, c'est illisible. En paragraphes
normaux juste en dessous, elle est lisible — et le gestionnaire la supprime d'un geste si elle est
de trop. On garde la fiche complète **et** la lisibilité d'un agenda.

**La structure canonique** (copiée sur `product-renderer.ts` — c'est elle qui garantit le
round-trip) :

```html
<div class="kg-card kg-product-card">
  <div class="kg-product-card-container">
    <img src="…" width="960" height="540" class="kg-product-card-image" loading="lazy" />
    <div class="kg-product-card-title-container">
      <h4 class="kg-product-card-title">Nom de l'événement</h4>
    </div>
    <div class="kg-product-card-description"><p>Organisateur — Lieu</p><p>Date — Tarif</p><p>Description courte</p></div>
    <a href="…" class="kg-product-card-button kg-product-card-btn-accent" target="_blank" rel="noopener noreferrer"><span>Réserver</span></a>
  </div>
</div>
```

> **PIÈGE vérifié en réel : les `<br>` sont avalés.** Dans `productDescription`, seuls les `<p>`
> survivent au parseur ; un `<br>` est remplacé par une espace, et le lieu se retrouve collé à la
> date. **Une info = un `<p>`.** Ne jamais utiliser `<br>` dans la description de la carte.

> **Les étoiles de notation** (`kg-product-card-rating-active`) ne sont **pas** émises : sans
> elles, `productRatingEnabled` reste à `false`. C'est ce qu'on veut.

---

## 5. Architecture — l'app `newsletter/`

Nouvelle app Django, **sans modèle** (donc sans migration), déclarée dans `TENANT_APPS`
(`TiBillet/settings.py:181`).

```
newsletter/
├── __init__.py
├── apps.py
├── client_ghost.py     ← parle à Ghost. Ne connaît ni les events ni TiBillet.
├── collecte.py         ← rassemble les events du réseau. Ne connaît ni Ghost ni le HTML.
├── rendu.py            ← fiches → HTML. Ne connaît ni Ghost ni la base.
├── services.py         ← orchestre les trois. Seul point d'entrée de l'admin.
└── templates/newsletter/
    └── email_evenements.html
```

Chaque module est testable seul. `services.py` est la seule couture.

**On ne touche pas à `send_to_ghost_email`.** Elle fonctionne ; la refactoriser pour partager le
JWT serait hors sujet. On la fera migrer le jour où on y touchera pour une autre raison.

---

## 6. La collecte — `collecte.py`

### 6.1 Pourquoi ne pas réutiliser le cache SEO

`seo/services.py` agrège déjà des events cross-tenant, mais son cache ne porte que `name`,
`slug`, `short_description`, `datetime`, `img`. **Ni description longue, ni adresse, ni tarif.**
Il est taillé pour les popups de la carte.

On lit donc les `Event` **complets** dans les schémas voisins.

### 6.2 C'est possible parce que la fédération est intra-instance

`FederatedPlace.tenant` est une **FK vers `Client`** : les voisins sont **d'autres schémas de la
même base Postgres**. On y accède avec `tenant_context()`. **Aucun appel HTTP entre instances.**

### 6.3 L'algorithme

> **La règle d'or : le même ensemble d'événements que l'agenda du site** (`federated_events_filter`,
> `views.py:1966-1988`). Chaque filtre ci-dessous existe parce que le moteur l'applique. En oublier
> un, c'est envoyer aux abonnés des événements qu'ils ne retrouveront pas sur le site.

```
Entrée : nombre_de_jours (7 ou 30)

fenetre_debut = maintenant - 1 jour      # comme le moteur : on garde les events d'hier
fenetre_fin   = maintenant + nombre_de_jours

# Construction de la liste des tenants (DÉDOUBLONNÉE : FederatedPlace.tenant n'est pas
# unique et peut pointer vers le tenant courant lui-même)
tenants = [ (tenant_courant, tag_filter=[], tag_exclude=[]) ]
        + [ (fp.tenant, fp.tag_filter, fp.tag_exclude) pour chaque FederatedPlace ]
        + fédération automatique par tags (FederationConfiguration.tags_federation),
          identifiée via seo.services.get_tenant_uuids_with_event_tags()

# Les slugs des tags sont extraits ICI, AVANT d'entrer dans le contexte du voisin (§6.4)

Pour chaque (tenant, slugs_filter, slugs_exclude) :
    with tenant_context(tenant):
        events = Event.objects.filter(
            published=True,
            archived=False,
            datetime__gte=fenetre_debut,
            datetime__lt=fenetre_fin,
        ).exclude(
            categorie=Event.ACTION       # créneaux de bénévolat : affichés dans l'event parent
        ).filter(
            parent__isnull=True          # pas les events enfants
        )

        si tenant != tenant_courant :
            events = events.filter(private=False)   # veto de non-fédérabilité

        si slugs_filter  : events = events.filter(tag__slug__in=slugs_filter)    # n'afficher QUE
        si slugs_exclude : events = events.exclude(tag__slug__in=slugs_exclude)  # exclure

        → construire la fiche de chaque event (§6.5)

Sortie : les fiches, triées par date croissante, tous tenants confondus.
```

**Note sur `private` :** comme le moteur, on ne l'applique **qu'aux voisins**. Un event `private`
du tenant courant reste dans **sa propre** newsletter — `private` veut dire « non fédérable »,
pas « secret ». Cohérent avec l'agenda du site.

**Note sur les events récurrents** (`Event.recurrent`) : leur `datetime` stocké peut être passé.
Ils sortiront de la fenêtre. **Traités comme l'agenda les traite — pas de traitement spécial dans
ce chantier.** À revoir si le besoin se manifeste.

### 6.4 Deux pièges à ne pas rater

**Piège 1 — les `Tag` sont des objets par tenant.** `FederatedPlace.tag_filter` pointe vers des
`Tag` du **tenant courant**, alors que les events des voisins portent des `Tag` de **leur** schéma.
Comparer les objets ou les PK ne marche pas. **Le matching se fait par `slug`.** Les slugs doivent
être extraits **avant** d'entrer dans le `tenant_context()` du voisin.

**Piège 2 — `tenant_context()`, pas `schema_context()`.** `schema_context()` pose un `FakeTenant`,
et tout modèle qui lit `connection.tenant.uuid` plante (cf. `tests/PIEGES.md`). Ici on a de vrais
objets `Client` : on utilise `tenant_context()`.

### 6.5 La fiche d'un événement

| Clé | Source | Note |
|---|---|---|
| `nom` | `event.name` | |
| `date_debut`, `date_fin` | `event.datetime`, `event.end_datetime` | Formatées dans la timezone du tenant **propriétaire** (`Configuration.get_solo().get_tzinfo()`, lue **dans son contexte**). |
| `organisateur` | `Configuration.get_solo().organisation` du tenant **propriétaire** | **Indispensable** : la newsletter mélange plusieurs lieux, il faut dire qui organise quoi. |
| `description_courte` | `event.short_description` | Texte simple. |
| `description_longue` | `event.long_description` | **C'est du HTML** — voir §7.2. |
| `lieu` | `event.postal_address` | Nom, rue, code postal, ville. Vide si absente. |
| `image_url` | §6.7 | `None` si l'event n'a pas d'image. |
| `tarif` | §6.6 | `None` si l'event n'a pas de billetterie. |
| `url_event` | **`event.full_url`** | Voir §6.7. |
| `libelle_bouton` | `event.reservation_button_name` sinon « Réserver » | Le champ existe déjà. |

### 6.6 Le calcul du tarif

Partir de **`event.published_prices()`** (`models.py:1822`) — il filtre déjà `publish=True`.
Restreindre aux produits de catégorie **`BILLET`** (`'B'`) ou **`FREERES`** (`'F'`), **publiés et
non archivés** (`Product.publish`, `Product.archive`).

Les cas, **dans cet ordre** (le premier qui matche gagne — sinon « prix libre » et « plusieurs
prix » se chevauchent) :

| # | Cas | Rendu |
|---|---|---|
| 1 | Aucun produit billetterie, ou aucun prix publié | `None` — pas de ligne tarif |
| 2 | Uniquement du `FREERES`, ou tous les prix à 0 | « Gratuit » |
| 3 | Au moins un prix `free_price=True` | « Prix libre, à partir de {prix minimum} € » (`prix` = minimum accepté) |
| 4 | Un seul prix | « {prix} € » |
| 5 | Plusieurs prix | « À partir de {prix minimum} € » |

### 6.7 Les URLs — absolues, et sur le domaine du **propriétaire**

Un event affiché dans la newsletter du tenant A peut appartenir au tenant B. Ses liens doivent
pointer vers **B**.

**Le lien « Réserver » : `event.full_url`, tel quel.** Ce champ est calculé à chaque `save()`
(`models.py:1895-1899`) et gère **les deux cas** : URL interne pour un event normal, URL du site
tiers pour un event `is_external=True`. **Ne pas le reconstruire à la main** — on enverrait les
abonnés vers une page de réservation inexistante pour les events externes.

**L'image :**
```
domaine   = tenant_proprietaire.get_primary_domain().domain
image_url = https://{domaine}{build_stdimage_variation_url(event.img.name, "crop_hdr")}
```
La variation **`crop_hdr`** (960×540), pas `crop` (480×270) : 480 px est trop petit pour un email
moderne sur écran dense.

**Robustesse :** si `get_primary_domain()` renvoie `None` (voisin mal configuré), on **saute cette
fiche** en la journalisant. Une fiche cassée ne doit **pas** faire échouer tout le brouillon.

> **Limite acceptée.** En développement local (`*.tibillet.localhost`), ces URLs ne sont pas
> joignables depuis une instance Ghost : les images ne s'afficheront pas. **C'est normal.** Le
> rendu des images se vérifie sur l'instance de dev en ligne, **`demo-tibillet.ovh`**.

---

## 7. Le rendu — `rendu.py` + le template

### 7.1 Le principe

`rendu.py` expose une fonction : liste de fiches → chaîne HTML, via `render_to_string()` sur
`newsletter/email_evenements.html`. Elle **ne touche pas à la base**.

Le template applique le mapping du §4.5. **Aucun attribut `style`.** Aucun `<table>` de mise en
page. Aucune classe CSS autre que celles que Ghost reconnaît (`kg-button-card`, `kg-align-center`,
`kg-btn`, éventuellement `kg-width-wide`).

Une intro courte en tête (« Voici les événements du réseau, du {début} au {fin}. »), puis une fiche
par event, séparées par des `<hr>`.

### 7.2 `long_description` est du HTML — ne pas l'envelopper

`Event.long_description` est édité avec un **widget Wysiwyg** (Unfold/Trix, via `formfield_overrides`
dans `EventAdmin`) et rendu `|safe` dans les templates du site. **Il contient déjà du HTML**
(`<div>`, `<br>`, `<strong>`, listes).

- L'envelopper dans un `<p>` produirait du **HTML invalide**.
- On l'émet **brut** (`|safe`), directement dans le flux. Le convertisseur Lexical le normalisera —
  une perte de mise en forme mineure est **assumée** (c'est le « lossy » du §4.4, et il est ici sans
  conséquence : gras, listes et paragraphes passent).

`short_description` est un `CharField` : texte simple, dans un `<p>`, échappé normalement.

### 7.3 Le titre du brouillon

`« Agenda du {date_debut} au {date_fin} »`, dates formatées en français.
C'est un brouillon : le gestionnaire le réécrira s'il veut.

### 7.4 i18n

Les textes du template (« Réserver », « Gratuit », « À partir de », « Prix libre », l'intro)
passent par `{% translate %}` / `{% blocktrans %}`, **msgid en français**. Ils s'ajouteront au
décompte des chaînes traduisibles **à signaler au mainteneur en fin de session** (on ne lance
jamais `makemessages` soi-même).

---

## 8. Le client Ghost — `client_ghost.py`

Deux fonctions. Ce module ignore tout des événements.

### 8.1 `forger_token_ghost(cle_admin)`

Reprend le pattern déjà éprouvé dans `send_to_ghost_email` :

```python
identifiant, secret = cle_admin.split(":")
maintenant = int(datetime.now().timestamp())
header  = {"alg": "HS256", "typ": "JWT", "kid": identifiant}
payload = {"iat": maintenant, "exp": maintenant + 5 * 60, "aud": "/admin/"}
token = jwt.encode(payload, bytes.fromhex(secret), algorithm="HS256", headers=header)
```

### 8.2 `creer_brouillon(ghost_url, cle_admin, titre, html)`

```
POST {ghost_url_nettoyee}/ghost/api/admin/posts/?source=html
Authorization: Ghost {token}
Accept-Version: v5.0
Body: {"posts": [{"title": titre, "html": html, "status": "draft"}]}
timeout = 15 s
```

- **`ghost_url_nettoyee` = `ghost_url.rstrip("/")`.** `URLField` accepte un slash final, qui
  produirait `//ghost/api/...`.
- **`status: "draft"` est non négociable.** Le post n'est jamais publié, jamais envoyé.
- `Accept-Version: v5.0` : recommandé par Ghost, gratuit.

**Retour :** l'**URL d'édition** du brouillon, construite depuis l'`id` renvoyé :
`{ghost_url_nettoyee}/ghost/#/editor/post/{id}`. C'est ce lien qu'on donne au gestionnaire.

---

## 9. L'admin — deux boutons sur `GhostConfig`

Dans `Administration/admin_tenant.py`, sur **`GhostConfigAdmin`** (`:3740`), avec le pattern
`actions_detail` + `@action` **déjà utilisé dans le projet** (voir `WebhookAdmin` `:321`, action
`test_webhook` `:347` — même structure, mêmes permissions).

> **`GhostConfigAdmin` a déjà `actions_detail = ["test_api_ghost_admin_button"]`.**
> On **ajoute** les deux entrées à la liste existante. **Ne pas l'écraser** — on supprimerait le
> bouton de test de la connexion Ghost.

```python
actions_detail = [
    "test_api_ghost_admin_button",          # existant — à conserver
    "brouillon_newsletter_7_jours",
    "brouillon_newsletter_30_jours",
]
```

Chaque action appelle `newsletter.services.creer_brouillon_newsletter(nombre_de_jours=…)` et rend
le résultat en **toast** (`django.messages`), comme `test_webhook`.

### Les cas de sortie

| Situation | Ce que voit le gestionnaire |
|---|---|
| Succès | Toast succès : « Brouillon créé avec N événements. » **+ le lien vers l'éditeur Ghost.** |
| **Zéro événement** sur la période | Toast info : « Aucun événement sur les N prochains jours. » **Aucun brouillon n'est créé** — pas de post vide dans Ghost. |
| Ghost non configuré (`ghost_url` ou `ghost_key` vide) | Toast avertissement : « Ghost n'est pas configuré. » |
| Ghost injoignable (timeout, DNS, connexion) | Toast erreur : « Instance Ghost injoignable. » |
| Clé refusée (401 / 403) | Toast erreur : « La clé Admin API est refusée par Ghost. » |
| Autre réponse non-2xx | Toast erreur : le code HTTP + le corps de la réponse, tronqué. |

Dans **tous** les cas (succès comme échec), on écrit une ligne horodatée dans
`GhostConfig.ghost_last_log`. **Le champ est écrasé, pas complété** — c'est ce que fait le code
Ghost existant, on reste cohérent.

---

## 10. Tests — `tests/pytest/test_newsletter_ghost.py`

**À lire avant d'écrire :** `tests/PIEGES.md`.

Aucun test ne tape une vraie instance Ghost. **Le mock se fait avec `unittest.mock.patch` sur
`requests.post`** — le paquet `responses` **n'est pas** dans le projet, et on n'ajoute pas de
dépendance (voir `test_stripe_membership_simple.py` pour le pattern maison).

**Collecte (le cœur, et le plus risqué) :**
- un event du tenant courant remonte ;
- un event d'un tenant **fédéré** remonte (le test qui prouve le cross-schema) ;
- un event **`private`** d'un **voisin** ne remonte pas ; un event `private` du **tenant courant**
  remonte (§6.3) ;
- `archived`, non `published`, `categorie=ACTION`, event enfant (`parent` non nul) : ne remontent pas ;
- hors fenêtre (au-delà de N jours) : ne remonte pas ;
- **`tag_filter`** non vide → **seuls** les events portant un de ces tags remontent ;
- **`tag_exclude`** non vide → les events portant un de ces tags **ne remontent pas** ;
- le matching se fait bien **par slug**, avec des objets `Tag` **distincts dans chaque schéma** —
  c'est ce que le test doit vraiment prouver ;
- un `FederatedPlace` pointant vers le tenant courant ne produit **pas** de doublon.

**Tarif :** gratuit · prix libre · prix unique · plusieurs prix · pas de billetterie (`None`) ·
prix non publié ignoré · produit archivé ignoré · **l'ordre des cas du §6.6** (un event avec
plusieurs prix dont un `free_price` → « Prix libre », pas « À partir de »).

**URL :** un event `is_external=True` produit un bouton pointant vers **`full_url`** (le site
tiers), pas vers une URL `/event/<slug>/` fabriquée.

**Rendu :** le HTML contient `kg-button-card`, `kg-btn`, un `<figure><img>` et un `<hr>` ; il **ne
contient aucun attribut `style=`** (test de non-régression sur la règle du §4.4).

**Client Ghost :** le POST part bien sur `?source=html`, avec `status: "draft"` et l'en-tête
`Authorization: Ghost <jwt>` ; un `ghost_url` avec slash final ne produit pas de `//` ; un 401 et
un timeout lèvent les erreurs attendues.

---

## 11. Hors périmètre (volontairement)

Chacun est une évolution simple **sur cette base**, pas une refonte :

- **Cron périodique** (brouillon auto chaque lundi / 1er du mois). Les boutons manuels fournissent
  déjà toute la mécanique ; il ne resterait qu'à l'appeler depuis Celery.
- **Upload des images vers Ghost** (`POST /images/upload/`) pour figer l'archive web du post.
- **Choix de la newsletter Ghost destinataire** quand l'instance en a plusieurs.
- **Traitement spécifique des events récurrents** (§6.3).
- **MCP Ghost.** Plusieurs existent (MFYDev/ghost-mcp, mtane0412, siva-sub) : ce sont des enveloppes
  autour de cette même Admin API pour piloter Ghost **depuis un LLM**. Ça n'apporte rien au produit —
  Django doit pousser un brouillon de façon déterministe. Ça resterait un confort de développement.
- **`Configuration.module_newsletter`.** L'app est le bon découpage pour en faire un module
  activable et facturable, mais on n'ajoute pas le flag tant que le besoin n'est pas là.

---

## 12. Références

**Documentation Ghost**
- Admin API : <https://docs.ghost.org/admin-api>
- Créer un post — `lexical` vs `?source=html`, l'avertissement « lossy », l'échappatoire
  `<!--kg-card-begin: html-->` : <https://docs.ghost.org/admin-api/posts/creating-a-post>
- Les cartes de l'éditeur : <https://ghost.org/help/cards/>
- Design de la newsletter : <https://ghost.org/help/email-design/>

**Code source Ghost — la preuve du §4.3** (`TryGhost/Koenig`, <https://github.com/TryGhost/Koenig>)
- `packages/kg-html-to-lexical/src/html-to-lexical.ts` — le convertisseur de `?source=html` ;
  il enregistre **`...DEFAULT_NODES`**, donc tous les nœuds Koenig participent à l'import DOM.
- `packages/kg-default-nodes/src/nodes/image/image-parser.ts` — `<img>` → carte image ;
  `<figure>` + `<figcaption>` → carte image avec légende.
- `packages/kg-default-nodes/src/nodes/button/button-parser.ts` — `<div class="kg-button-card">`
  + `<a class="kg-btn">` → carte bouton ; alignement `left` / `center` **uniquement**.
- `packages/kg-default-nodes/src/nodes/` — les 28 types de cartes.
- Issue [Ghost#19785](https://github.com/TryGhost/Ghost/issues/19785) (fermée « not planned ») :
  les `<figure><a><img>` complexes sont aplatis en cartes image. **Sans effet sur le HTML du §4.5.**

**Compose Ghost du mainteneur** : `/home/jonas/Gits/ghost/docker-compose.yml`
(Ghost `latest` + MySQL 8, derrière Traefik).

**Interne**
- [CHANTIER-01](CHANTIER-01-semantique-tags-federes.md) — le prérequis.
- `tests/PIEGES.md` — `tenant_context()` vs `schema_context()`.
- `BaseBillet/views.py:1881` — `federated_events_filter`, la référence de comportement.
- `seo/services.py` — `build_stdimage_variation_url()`, matching de tags par slug.
