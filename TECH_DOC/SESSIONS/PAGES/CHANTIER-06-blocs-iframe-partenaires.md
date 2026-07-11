# CHANTIER 06 — Blocs `IFRAME` (intégration hauteur-libre) + `PARTENAIRES` (bande de logos)

> Spec actionnable. Vague : blocs riches (suite de la vague 2). Édité 2026-07-11.
> Lire `SPEC.md`, `ETAT-REPRISE.md`, et la matrice `TYPE_BLOC_CHOICES` dans
> `pages/models.py` avant d'attaquer.

## 1. Contexte & besoin

Deux blocs manquent au catalogue de l'app `pages` :

1. **Intégration hauteur-libre** (`IFRAME`) : intégrer un formulaire d'inscription
   newsletter (ex. Ghost), un widget, un formulaire tiers. Ce n'est **pas** une
   vidéo : hauteur variable, pas de ratio 16:9. Le bloc `EMBED` existant est
   volontairement restreint (whitelist vidéo YouTube/Vimeo/PeerTube) et reconstruit
   l'URL d'embed ; il ne convient pas.
2. **Encart partenaires** (`PARTENAIRES`) : afficher une suite de logos, chaque
   logo cliquable vers le site du partenaire.

### Décisions prises avec le mainteneur (2026-07-11)

- **IFRAME = bloc dédié** (pas de fusion avec EMBED/VIDEO_TEXTE) : sémantique claire,
  hauteur libre ≠ ratio vidéo. **Réutilise le champ `embed_url`** existant (pas de
  champ `iframe_url` dédié → moins de dette).
- **Whitelist globale ROOT** : le modèle de sécurité retenu est une liste de domaines
  autorisés portée par `RootConfiguration` (app `root_billet`, SHARED_APPS), éditable
  **uniquement par le superadmin ROOT** dans l'admin root. Un iframe n'est rendu que si
  son hôte est dans cette liste — **jamais d'iframe vers un hôte arbitraire** (même
  politique que le tag `embed_iframe`).
- **PARTENAIRES réutilise l'inline `ImageGalerie`** (comme GALERIE/MARKDOWN). On ajoute
  un champ **`lien_url`** à `ImageGalerie` → mécanisme « image cliquable » **réutilisable
  par tout bloc à `ImageGalerie`** (GALERIE en profite aussi).
- **Skin `classic` seulement** au départ ; `faire_festival` retombe dessus via le
  fallback `select_template` du tag `{% templates_bloc %}`. Habillage FF plus tard si besoin.

## 2. Modèles

### 2.1 `pages/models.py` — nouveaux types de blocs

Ajouter au catalogue `Bloc` :

```python
IFRAME = "IFRAME"
PARTENAIRES = "PARTENAIRES"
```

Et dans `TYPE_BLOC_CHOICES` (libellés source **FR**) :

```python
(IFRAME, _("Contenu intégré libre (newsletter, formulaire — domaines autorisés par le ROOT)")),
(PARTENAIRES, _("Partenaires (bande de logos cliquables)")),
```

### 2.2 `pages/models.py` — champ `hauteur_px` sur `Bloc`

Un seul nouveau champ, utilisé par le bloc IFRAME (les autres blocs l'ignorent) :

```python
# Hauteur en pixels de l'iframe du bloc IFRAME. Un formulaire newsletter n'a pas
# de ratio fixe (contrairement a une video 16:9) : on fixe une hauteur explicite.
# / Iframe height in pixels for the IFRAME block. A newsletter form has no fixed
# ratio (unlike a 16:9 video): we set an explicit height.
hauteur_px = models.PositiveIntegerField(
    default=600,
    validators=[MinValueValidator(100), MaxValueValidator(4000)],
    verbose_name=_("Hauteur de l'iframe (pixels)"),
    help_text=_("Hauteur du cadre intégré, en pixels (bloc Contenu intégré libre)."),
)
```

> Le champ `embed_url` est **réutilisé** tel quel pour l'URL de l'iframe. Généraliser
> son `help_text` pour couvrir les deux usages (vidéo pour EMBED, contenu libre pour
> IFRAME), sans casser la sémantique d'EMBED.

### 2.3 `pages/models.py` — champ `lien_url` sur `ImageGalerie`

```python
# Lien optionnel de l'image : si renseigne, l'image devient cliquable (nouvel onglet).
# Utilise par le bloc PARTENAIRES (logo -> site du partenaire) mais valable pour
# TOUT bloc a ImageGalerie (ex. GALERIE). Le HTML du lien est dans le template.
# / Optional image link: if set, the image becomes clickable (new tab). Used by the
# PARTENAIRES block (logo -> partner site) but valid for ANY ImageGalerie block.
lien_url = models.CharField(
    max_length=500,
    blank=True,
    validators=[valider_url_sans_schema_dangereux],  # cf. ci-dessous
    verbose_name=_("Lien de l'image"),
    help_text=_("Lien optionnel : rend l'image cliquable (nouvel onglet). Ex. site d'un partenaire."),
)
```

> **Sécurité XSS (bloquant, review fable)** : l'inline `ImageGalerie` est enregistrée
> par le formset, **pas** par `BlocAdmin.save_model` → elle ne bénéficie PAS de la
> neutralisation `url_a_schema_dangereux` appliquée à `bouton_url`/`embed_url`
> (`pages/admin.py:489-492`). Un `lien_url = "javascript:…"` ressortirait tel quel dans
> `href="{{ image.lien_url }}"` d'une page publique. **Correctif FALC** : un validator de
> modèle `valider_url_sans_schema_dangereux` (rejette `javascript:`, `data:`, etc., en
> réutilisant `Administration.utils.url_a_schema_dangereux`) posé sur le champ →
> protège l'admin ET l'API v2. Ne pas se reposer sur un override `save_formset`.

### 2.4 `root_billet/models.py` — whitelist ROOT

Ajouter à `RootConfiguration` :

```python
# Liste blanche GLOBALE des hotes autorises a etre integres dans un bloc IFRAME
# (app pages), un domaine par ligne. Editable UNIQUEMENT par le superadmin ROOT.
# Partagee par tous les tenants (RootConfiguration est en SHARED_APPS, schema public).
# / GLOBAL whitelist of hosts allowed to be embedded in an IFRAME block (pages app),
# one domain per line. ROOT-superadmin only. Shared across tenants (SHARED_APPS).
domaines_embed_autorises = models.TextField(
    blank=True,
    default="",
    verbose_name=_("Domaines d'intégration autorisés (iframe)"),
    help_text=_("Un domaine par ligne (ex. newsletter.ghost.io). Ces hôtes seuls "
                "peuvent être intégrés dans un bloc « Contenu intégré libre »."),
)
```

## 3. Admin

### 3.1 `RootConfigurationAdmin` sur `staff_admin_site` — superadmin strict (DÉCISION FIGÉE)

**Constat review fable** : `Administration/admin_root.py` est **entièrement commenté**
(code mort), importé nulle part, route commentée (`urls_public.py:8`,
`urls_tenants.py:97`). On **ne le réactive pas**.

**Décision mainteneur (2026-07-11)** : répliquer le pattern des ModelAdmin réservés au
superadmin (comme `TenantAdmin(Client)`, `admin_tenant.py:3560`, enregistré sur
`staff_admin_site`). On enregistre un nouvel admin **`RootConfigurationAdmin`** sur
`staff_admin_site` :

- **`@admin.register(RootConfiguration, site=staff_admin_site)`** (le projet n'utilise
  pas l'autodiscover ; l'import du module déclenche le register — cf. `pages/admin.py`
  importé par `admin_tenant.py`). Prévoir l'import dans le point d'entrée admin.
- **Accès superadmin STRICT** : les 4 `has_view/add/change/delete_permission` renvoient
  **`request.user.is_superuser`** — PAS `TenantAdminPermissionWithRequest` (qui laisserait
  passer un admin tenant, cf. `ApiBillet/permissions.py:79-87`). Ainsi le modèle
  n'apparaît dans la sidebar/changelist **que** pour le superadmin ROOT.
- **`fields = ("domaines_embed_autorises",)`** UNIQUEMENT : ne JAMAIS exposer les clés
  Stripe/Fedow de `RootConfiguration`.
- **Singleton** : `RootConfiguration` est un `SingletonModel` (django-solo). Combiner avec
  l'admin Unfold — au choix `class RootConfigurationAdmin(SingletonModelAdmin, ModelAdmin)`
  (redirige la changelist vers l'unique instance) ; à valider au dev (compat Unfold/solo).
- **SHARED/singleton** : enregistré sur l'admin tenant, il édite la **même** ligne
  publique quel que soit le tenant depuis lequel le ROOT y accède (voulu : config globale).

> Ne JAMAIS exposer ce champ dans un admin accessible aux admins tenant.

### 3.2 `pages/admin.py` — conditional_fields + inline

- **`fields`** de `BlocAdmin` : ajouter `hauteur_px` (l'URL passe déjà par `embed_url`).
- **`conditional_fields`** :
  - **`titre`** *(bloquant review fable — admin.py:436)* : la liste énumère les types
    autorisés ; **ajouter `'IFRAME'` et `'PARTENAIRES'`**, sinon le champ titre est masqué
    dans le formulaire de ces blocs (alors que les templates §4.2 le rendent).
  - `embed_url` : passer de `"type_bloc == 'EMBED'"` à
    `"['EMBED','IFRAME'].includes(type_bloc)"`.
  - `hauteur_px` : `"type_bloc == 'IFRAME'"`.
- **`get_inlines`** *(admin.py:346)* : ajouter `Bloc.PARTENAIRES` au tuple
  `(Bloc.GALERIE, Bloc.MARKDOWN)` qui renvoie `[ImageGalerieInline]`. (L'inline
  n'apparaît qu'après le 1er save — flux Django standard existant, OK.)
- **`ImageGalerieInline.fields`** : ajouter `lien_url`.
- Mettre à jour le commentaire « 16 types » de `pages/admin.py:373` (→ 18 types).

## 4. Rendu

### 4.1 `pages/templatetags/pages_tags.py` — tag `iframe_libre`

> Nom **`iframe_libre`** (PAS `iframe_embed` : trop proche de l'existant `embed_iframe`,
> confusion garantie — review fable).

Nouveau tag `@register.simple_tag` `iframe_libre(url, hauteur)` :

1. Helper `_domaines_embed_autorises()` → lit
   `RootConfiguration.get_solo().domaines_embed_autorises`, split par lignes. **Normaliser
   chaque ligne** : strip, minuscules, et **retirer un éventuel schéma/slash** (`urlparse`
   puis `.hostname or valeur`) car un ROOT collera souvent `https://newsletter.ghost.io/`.
   Ignorer les vides. Lecture depuis un tenant : **OK confirmé** (déjà fait dans
   `BaseBillet/views.py:385`, `PaiementStripe/views.py:83`… — table SHARED en `public`,
   search_path `[tenant, public]`). Le `schema_context('public')` de secours est superflu.
2. Parse l'URL (`urlparse`). **Rejeter si `scheme != "https"`** (comme `embed_iframe`
   pages_tags.py:184 ; un iframe `http:` serait de toute façon bloqué en mixed content).
   Récupère l'hôte en minuscules (`urlparse` retire déjà le port).
3. Hôte ∈ whitelist (match exact sur `hostname`) → rendre :
   ```html
   <div class="tb-bloc__embed-cadre">
     <iframe src="{escape(url)}" title="{% translate 'Contenu intégré' %}" height="{int(hauteur)}"
             loading="lazy" referrerpolicy="no-referrer"
             sandbox="allow-scripts allow-same-origin allow-forms allow-popups"></iframe>
   </div>
   ```
   `src` **échappé**, hauteur **castée en int**.
4. Schéma ≠ https / hôte absent / URL invalide → **chaîne vide** (jamais d'iframe
   arbitraire). En admin/preview, le template §4.2 affiche un message « hôte non autorisé »
   (même pattern honnête que `bloc_embed.html`) plutôt qu'une section muette.

> Ne PAS reconstruire l'URL comme `embed_iframe` (on garde l'URL telle quelle, c'est le
> principe d'un iframe libre), mais l'échapper et **borner la source par la whitelist**.

**Sandbox** : `allow-scripts` + `allow-same-origin` ensemble n'affaiblissent PAS la
sécurité ici, car le contenu embarqué est **cross-origin** (il garde sa propre origine,
pas celle de la plateforme) et l'hôte est borné par la whitelist ROOT. **Consigne (→ §8)** :
ne JAMAIS whitelister un domaine de la plateforme ni d'un tenant (sinon `allow-same-origin`
annulerait le bac à sable).

**Cache django-solo (review fable)** : `SOLO_CACHE` est actif + `KEY_FUNCTION` scopée par
schéma (`settings.py`). Après une écriture ROOT de la whitelist (schéma public), les tenants
gardent une copie périmée jusqu'au `SOLO_CACHE_TIMEOUT` (défaut ~5 min). → dans le
`save()`/l'admin qui édite la whitelist, appeler **`cache.clear()`** (pattern existant
`RootConfiguration.set_stripe_api`, `root_billet/models.py:51`), sinon le test manuel
« ROOT ajoute le domaine → le bloc s'affiche » échoue pendant ~5 min.

### 4.2 Templates de blocs (skin `classic`)

> **Conventions (review fable)** : suivre le BEM/testid des partials existants
> (`bloc_embed.html`, `bloc_markdown.html`) : `tb-bloc tb-bloc--<type>`, `tb-bloc__titre`,
> `data-testid="bloc-<type>"` — PAS `tb-bloc-iframe`/`pages-bloc-iframe`.

- **`pages/templates/pages/classic/partials/bloc_iframe.html`** :
  ```html
  {% load pages_tags i18n %}
  <section class="tb-bloc tb-bloc--iframe" data-testid="bloc-iframe">
    {% if bloc.titre %}<h2 class="tb-bloc__titre">{{ bloc.titre }}</h2>{% endif %}
    {% iframe_libre bloc.embed_url bloc.hauteur_px as iframe_html %}
    {% if iframe_html %}
      {{ iframe_html }}
    {% else %}
      {# Hôte non autorisé : message honnête (comme bloc_embed.html), pas de section muette #}
      <p class="tb-bloc__note">{% translate "Contenu non affiché : hôte non autorisé." %}</p>
    {% endif %}
  </section>
  ```
- **`pages/templates/pages/classic/partials/bloc_partenaires.html`** : bande/grille de
  logos depuis `bloc.images_galerie.all`. Chaque logo :
  ```html
  {% if image.lien_url %}
    <a href="{{ image.lien_url }}" target="_blank" rel="noopener"
       class="tb-bloc__partenaire-lien" aria-label="{% blocktranslate with nom=image.legende %}Partenaire {{ nom }}{% endblocktranslate %}">
      <img src="{{ image.image.med.url }}" alt="{{ image.legende }}" loading="lazy">
    </a>
  {% else %}
    <img src="{{ image.image.med.url }}" alt="{{ image.legende }}" loading="lazy">
  {% endif %}
  ```
  Logos monochromes au repos, couleur au survol (CSS `filter: grayscale`) — conforme
  Hallmark. `data-testid="bloc-partenaires"`.
- **`bloc_galerie.html`** (existant) : ajouter la **même** enveloppe conditionnelle
  `{% if image.lien_url %}<a target="_blank" rel="noopener">…{% endif %}` autour de
  chaque image → mécanisme « image cliquable » réutilisé.

### 4.3 Regroupement (`pages/services.py`)

Aucun regroupement pour IFRAME ni PARTENAIRES : ce sont des blocs `solo` (un bloc
PARTENAIRES contient déjà toute sa bande de logos). Vérifier qu'ils tombent bien dans la
branche `solo` de `grouper_blocs` (pas d'absorption inattendue).

### 4.4 CSS `pages/static/pages/css/tb-blocs.css`

- `.tb-iframe iframe { width: 100%; border: 0; }` (+ conteneur responsive `max-width:100%`).
- `.tb-partenaires` : grille responsive `repeat(auto-fit, minmax(120px, 1fr))`,
  logos `object-fit: contain`, `filter: grayscale(1)` au repos → `grayscale(0)` au survol,
  transition sur `filter`/`opacity` uniquement, `prefers-reduced-motion` respecté.

## 5. Migrations

- `pages/000X_iframe_partenaires` : altération `type_bloc` (choices), `+hauteur_px` (Bloc),
  `+lien_url` (ImageGalerie). S'applique **public + tenants** (dual-list). Aucune data
  migration.
- `root_billet/000X_domaines_embed` : `+domaines_embed_autorises` (RootConfiguration).
  **public seulement** (SHARED). Aucune dépendance croisée avec `pages`.

Commande (mainteneur) : `migrate_schemas --executor=multiprocessing`.

## 6. Plan de tests

**pytest DB-only** (`tests/pytest/test_pages.py`) :
1. Création d'un bloc `IFRAME` (embed_url + hauteur_px) → OK.
2. Tag `iframe_libre` : hôte **dans** la whitelist (https) → `<iframe` présent, `src` = URL, height ok.
3. Tag `iframe_libre` : hôte **hors** whitelist → **chaîne vide** (sécurité).
4. Tag `iframe_libre` : URL vide / invalide → chaîne vide (pas de crash).
4bis. Tag `iframe_libre` : URL en **`http://`** (hôte pourtant whitelisté) → chaîne vide (schéma refusé).
5. Whitelist multi-lignes (espaces, casse, `https://…/` avec schéma+slash, ligne vide) → normalisation correcte.
5bis. `lien_url = "javascript:alert(1)"` → **ValidationError** au `full_clean()` (validator modèle).
6. Bloc `PARTENAIRES` : `ImageGalerie` avec `lien_url` → inline OK.
7. Rendu `bloc_partenaires.html` : image avec `lien_url` → `<a target="_blank" rel="noopener">` ;
   sans `lien_url` → `<img>` nu.
8. Rendu `bloc_galerie.html` : `lien_url` rend l'image cliquable (mécanisme réutilisé).
9. `get_inlines` : l'inline `ImageGalerie` apparaît pour PARTENAIRES.
10. Isolation : `domaines_embed_autorises` lue depuis un contexte tenant (SHARED/public).

> Pièges tests : `tenant_context` requis (pas `schema_context`) pour tout accès à
> `connection.tenant` ; `CarteCashless`/SHARED en `public`. Voir `tests/PIEGES.md`.

**Manuel / Chrome** (`https://<tenant>.tibillet.localhost/`) :
- ROOT ajoute `newsletter.ghost.io` dans la whitelist (admin root) → un bloc IFRAME
  pointant ce domaine s'affiche ; un domaine non listé n'affiche rien.
- Bande de partenaires : logos grisés, couleur au survol, clic = nouvel onglet.

## 7. Fichiers touchés (récap)

| Fichier | Changement |
|---|---|
| `pages/models.py` | +IFRAME/PARTENAIRES (choices), +`hauteur_px` (Bloc), +`lien_url` (ImageGalerie) |
| `root_billet/models.py` | +`domaines_embed_autorises` (RootConfiguration) |
| `Administration/admin_tenant.py` (ou module admin dédié importé) | `RootConfigurationAdmin` sur `staff_admin_site`, 4 perms → `is_superuser` strict, `fields=("domaines_embed_autorises",)` |
| `pages/admin.py` | conditional_fields (`embed_url`+`hauteur_px`), get_inlines +PARTENAIRES, inline +`lien_url` |
| `pages/templatetags/pages_tags.py` | tag `iframe_libre` + helper whitelist |
| `pages/templates/pages/classic/partials/bloc_iframe.html` | nouveau |
| `pages/templates/pages/classic/partials/bloc_partenaires.html` | nouveau |
| `pages/templates/pages/classic/partials/bloc_galerie.html` | +lien cliquable conditionnel |
| `pages/static/pages/css/tb-blocs.css` | `.tb-iframe`, `.tb-partenaires` |
| `tests/pytest/test_pages.py` | +tests (§6) |
| `CHANGELOG.md` | entrée bilingue |
| `A TESTER et DOCUMENTER/` | fiche de test |

**Hors périmètre assistant** : i18n (makemessages/compilemessages) et **toute opération git** = mainteneur.

## 8. Points de vigilance

- **Imports** : `MinValueValidator`/`MaxValueValidator` (`django.core.validators`) pour
  `hauteur_px` ; `valider_url_sans_schema_dangereux` (nouveau helper `pages/models.py`
  s'appuyant sur `Administration.utils.url_a_schema_dangereux`) pour `lien_url` ;
  `from django.core.cache import cache` pour le `cache.clear()` whitelist.
- **Sécurité iframe** : la seule barrière est la whitelist ROOT. Ne jamais rendre un
  iframe si l'hôte n'y est pas **ou si le schéma n'est pas `https`**. `src` échappé,
  `sandbox` toujours présent.
- **Ne JAMAIS whitelister** un domaine de la plateforme ni d'un tenant : avec
  `allow-scripts allow-same-origin`, un contenu servi depuis la même origine casserait
  son propre bac à sable.
- **XSS `lien_url`** : validator de modèle obligatoire (l'inline ne passe pas par
  `save_model`). Cf. §2.3.
- **`embed_url` partagé EMBED/IFRAME** : deux rendus distincts (tag `embed_iframe` pour
  EMBED = whitelist vidéo + reconstruction ; tag `iframe_libre` pour IFRAME = whitelist
  ROOT + URL telle quelle). Ne pas mélanger les deux tags.
- **`hauteur_px`** cast `int` au rendu (jamais interpolé brut dans le HTML).
- **dual-list** : la migration `pages` ne dépend PAS d'une migration `root_billet`
  (insatisfiable sur public/tenant). Les deux migrations sont indépendantes.
- **django-solo + tenant** : `RootConfiguration.get_solo()` — vérifier la lecture depuis
  un tenant (cf. §4.1).
