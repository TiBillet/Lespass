# Chantier 08 — Bloc « Carte figée » : la carte du réseau, avec des données importées en JSON

**Statut :** codé le 2026-11-03 (non commité), relu par Fable
**Date :** 2026-11-03
**Hub :** [INDEX.md](./INDEX.md)

## 1. Intention

Un lieu veut publier sur son site une carte « photo d'un moment ». Exemple : le bilan des
Journées Portes Toujours Ouvertes 2026 (JPTO), avec 163 événements sur 74 adresses.

La carte « Autour de nous » (`FederationViewset.list`, `BaseBillet/views.py`, gabarit `vues/reseau.html`) fait déjà exactement ce
qu'il faut à l'écran : une carte et une liste des lieux, et, au clic sur un lieu, ses
événements. Mais elle lit le cache SEO, qui ne contient que les **événements à venir** des
espaces TiBillet fédérés. Un bilan porte sur des événements passés, et parfois sur des lieux
qui ne sont pas sur TiBillet.

Le chantier crée donc **un nouveau type de bloc** pour l'éditeur de site. Ce bloc affiche
**le même outil de carte**, avec **la même expérience**, mais il lit **des données figées**,
importées par l'admin du lieu sous la forme d'un **fichier JSON**.

C'est une carte éphémère : on la fabrique pour une occasion, on la place dans une page avec
son entrée de menu, et on l'oublie. Elle ne suit pas la base.

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
- L'admin d'un lieu ajoute un bloc « Carte figée » à une page, depuis l'éditeur de site.
- Il importe un fichier JSON : une liste de lieux, chacun avec ses événements.
- La page affiche la carte du réseau, sans changement d'expérience : recherche, bascule
  lieux/événements, puces de tags, marqueurs regroupés, popup, liste, bouton carte/liste
  sur mobile.
- L'aide du champ montre un exemple de fichier, replié dans un accordéon.

**Non-objectifs**
- Pas d'import CSV : le JSON seul suffit.
- Pas de géocodage. Les coordonnées GPS sont **obligatoires** dans le fichier.
- Pas de lien avec la base : le bloc ne lit ni les événements, ni les tags, ni les adresses
  de TiBillet.
- Pas d'historique des imports, pas de versions. Un nouvel import remplace l'ancien.
- Pas d'outil d'export de la base vers ce format. Pour le bilan JPTO, le fichier sera
  fabriqué à la main, à partir de l'export déjà fait.

**Anti-objectifs (ce serait un échec, même si ça marche)**
- Une deuxième copie de `explorer.js` ou du widget, qui dériverait de l'original.
- Une retouche qui change le comportement de la page « Autour de nous » ou de `/explorer/`.
- Un format de fichier qui oblige l'admin à connaître le format interne de l'explorer
  (`points`, `tenants`, `pa_id`…).

## 3. Le format du fichier JSON

Le fichier est **une liste de lieux**. Chaque lieu porte **ses événements**.

```json
[
  {
    "nom": "La Cité du Faire",
    "latitude": 45.7578,
    "longitude": 4.8320,
    "adresse": "12 rue de l'Exemple, 69003 Lyon",
    "url": "https://lacitedufaire.example.org/",
    "evenements": [
      {
        "nom": "Visite guidée de la Cité du Faire",
        "date": "2026-10-02T14:00",
        "url": "https://lacitedufaire.example.org/visite/",
        "tags": ["JPTO", "Visite"]
      },
      {
        "nom": "Atelier ouvert",
        "date": "2026-10-03"
      }
    ]
  },
  {
    "nom": "Tiers-lieu sans événement",
    "latitude": 48.5734,
    "longitude": 7.7521
  }
]
```

| Clé | Niveau | Obligatoire | Règle |
|---|---|---|---|
| `nom` | lieu | oui | texte non vide |
| `latitude` | lieu | oui | nombre entre -90 et 90 |
| `longitude` | lieu | oui | nombre entre -180 et 180 |
| `adresse` | lieu | non | texte affiché sous le nom, dans la liste et dans la popup |
| `url` | lieu | non | lien `http://` ou `https://` uniquement |
| `evenements` | lieu | non | liste, vide permise |
| `nom` | événement | oui | texte non vide |
| `date` | événement | non | date ISO 8601 : `2026-10-02` ou `2026-10-02T14:00` |
| `url` | événement | non | lien `http://` ou `https://` uniquement |
| `tags` | événement | non | liste de textes |

**Règles de validation**
- Le fichier doit être du JSON valide, en UTF-8, et faire **2 Mo au plus**.
- La racine doit être une liste, avec au moins un lieu.
- **Une URL qui ne commence pas par `http://` ou `https://` est refusée.** C'est une
  contrainte de sécurité : `explorer.js` échappe le texte, mais une URL `javascript:` posée
  dans un `href` s'exécuterait quand même au clic.
- Une clé inconnue est ignorée sans erreur, pour qu'un fichier un peu plus riche passe.
- Les erreurs sont **toutes listées d'un coup**, avec leur position, par exemple :
  « Lieu 3 (« La Grenze ») : la latitude doit être un nombre entre -90 et 90. » ou
  « Lieu 5, événement 2 : l'URL doit commencer par http:// ou https://. »
- Si le fichier contient au moins une erreur, **rien n'est enregistré**. Le bloc garde ses
  données précédentes.

## 4. Les décisions déjà prises

**Prises par le mainteneur**
- Un bloc de l'éditeur de site, fabriqué par l'admin du lieu.
- Les données sont figées. Elles viennent d'un fichier, jamais de la base.
- Le fichier est **en JSON seul**, avec **les événements imbriqués dans le lieu**.
- Les coordonnées GPS sont présentes dans le fichier.
- Le rendu reprend **le même outil de carte** (même widget, même JS), avec la même expérience.
- L'aide du champ d'import contient **un exemple de fichier, dans un accordéon**.
- Pas de sur-ingénierie.

**Prises par l'auteur de la spec (à relire)**
- **Un nouveau type de bloc**, plutôt qu'une nouvelle disposition du bloc LIEU. Le bloc LIEU
  rend une petite carte Leaflet à côté d'infos pratiques. Son gabarit n'a rien de commun
  avec l'explorer.
- **On stocke le fichier nettoyé, pas le format de l'explorer.** La base garde la liste des
  lieux validée, au format du fichier. La conversion vers `{points, tenants}` se fait au
  rendu. Ainsi, le contenu stocké reste lisible, et il ne dépend pas du format interne de
  l'explorer.
- **Le fichier lui-même n'est pas conservé.** Seul son contenu validé est gardé.
- **Une seule carte figée par page.** `explorer.js` utilise des id fixes (`#explorer-root`,
  `#explorer-data`, `#explorer-map`…). `Bloc.clean()` refuse donc un deuxième bloc de ce
  type sur la même page.
- **La retouche du JS se limite aux liens** : préférer l'`url` fournie quand elle existe
  (voir §6).

## 5. Le modèle et l'éditeur

### 5.1 Le modèle (`pages/models.py`)

- Nouveau type : `Bloc.CARTE_FIGEE = "CARTE_FIGEE"`. Son libellé dans
  `TYPE_BLOC_CHOICES` est `_("Carte figée (lieux et événements importés en JSON)")`.
- Nouveau champ :
  ```python
  donnees_carte_figee = models.JSONField(
      default=list,
      blank=True,
      verbose_name=_("Données de la carte figée"),
  )
  ```
  Il contient la liste des lieux validée, au format du §3.
- Migration : un seul `AddField`, plus la mise à jour des `choices` de `type_bloc`.
  `pages` est en `SHARED_APPS` et en `TENANT_APPS`, donc la migration tourne sur tous les
  schémas, `public` compris.
- `Bloc.clean()` appelle `_verifier_la_carte_figee()`, qui :
  - refuse un bloc `CARTE_FIGEE` sans données ;
  - revérifie les données avec `nettoyer_carte_figee()` et range la version nettoyée. L'API v2
    écrit ce champ par `additionalProperty` puis appelle `full_clean()` : c'est le seul contrôle
    sur ce chemin ;
  - refuse un deuxième bloc `CARTE_FIGEE` sur la même page.
- **Les erreurs sont rattachées à `NON_FIELD_ERRORS`, jamais à un champ.** `donnees_carte_figee`
  n'est pas un champ du formulaire de l'admin. Une erreur de `Model.clean()` rattachée à un champ
  absent du `ModelForm` fait lever une `ValueError` à Django (page 500).
- Le type a un rendu unique : pas d'`affichage`, comme TEXTE, LIEU, FAQ ou LISTE.

### 5.2 Le catalogue (`pages/blocs_catalogue.py`)

- `CHAMPS_PAR_TYPE["CARTE_FIGEE"] = ["titre", "donnees_carte_figee"]`.
- Le `titre`, s'il est rempli, s'affiche au-dessus de la carte. Il est facultatif.

### 5.3 L'éditeur (`pages/admin.py`, `BlocAdminForm`)

- Nouveau champ **de formulaire**, pas de modèle : `fichier_carte_figee = forms.FileField(required=False)`.
  C'est le même principe que `texte_markdown` ou `points_gps_editeur` : un champ de
  formulaire qui alimente un champ modèle dans `save_model`.
- Il n'est visible que pour le type `CARTE_FIGEE`, par `conditional_fields`, comme les autres
  champs propres à un type.
- `donnees_carte_figee` n'est pas éditable à la main : il est retiré du formulaire, ou mis en
  lecture seule.
- Validation : `clean_fichier_carte_figee()` lit et vérifie le fichier (§5.4). Chaque erreur
  est ajoutée au champ. Puis `clean()` pose la liste propre sur `self.instance` : il le fait
  **avant** la validation du modèle, que Django lance ensuite (`_post_clean` → `full_clean`).
- **Fichier vide à la modification** : les données existantes sont gardées. On peut ainsi
  changer le titre sans réimporter.
- **Ce que voit l'admin quand des données existent déjà** : une ligne de résumé, par exemple
  « Carte actuelle : 74 lieux, 163 événements. Importer un nouveau fichier remplace tout. »
  Sans ce résumé, l'admin ne saurait pas qu'une carte est déjà chargée, puisque le champ
  fichier est toujours vide à l'ouverture.

**L'aide en accordéon.** Unfold rend le `help_text` avec `|safe`
(`unfold/helpers/help_text.html`). Le `help_text` du champ contient donc :
- une phrase courte : « Fichier JSON : une liste de lieux, chacun avec ses coordonnées GPS et
  ses événements. 2 Mo au plus. » ;
- un `<details>` replié, intitulé « Voir un exemple de fichier », qui contient l'exemple du §3
  dans un `<pre>`, puis la liste des clés obligatoires et facultatives.

Le HTML est construit avec `format_html`, et l'exemple est échappé. Le style est en
**styles inline** : le bundle Tailwind d'Unfold ne contient pas les classes non prévues
(voir le skill `unfold`). Les textes visibles passent par `_()`, avec un msgid en français.
Les clés JSON de l'exemple (`nom`, `latitude`, `evenements`…) ne se traduisent pas.

### 5.4 Le nettoyage (`pages/carte_figee.py`)

Le module `pages/carte_figee.py` regroupe toute la logique du bloc : l'exemple, la lecture,
le nettoyage, la conversion et l'aide de l'admin. Il réutilise `_texte` et `_nombre_ou_none`
de `pages/editeur_items.py`. `nettoyer_carte_figee(donnees_lues)` suit le modèle de
`nettoyer_points_gps` et renvoie `(lieux_propres, erreurs)`.
- Elle applique les règles du §3.
- Elle convertit les nombres reçus en texte (`"45.75"`) en vrais nombres. Elle supprime les
  espaces en trop autour des textes.
- Elle ne garde que les clés connues.

La lecture du fichier (taille, décodage UTF-8, `json.loads`) se fait dans le formulaire, juste
avant l'appel. Un JSON illisible donne une seule erreur claire : « Le fichier n'est pas un
JSON valide (ligne 12, colonne 5). »

## 6. Le rendu

### 6.1 La conversion vers le format de l'explorer

Fonction `pages/carte_figee.py: donnees_explorer_depuis_carte_figee(lieux)`, appelée par le tag `donnees_explorer_carte_figee` (`pages/templatetags/pages_tags.py`).
Elle renvoie `{"points": [...], "tenants": [...]}`, c'est-à-dire la forme que lit
`explorer.js` (voir `seo/services.py: build_aggregate_points` et
`build_explorer_data_for_tenants`).

Pour chaque lieu, à la position `n` :
- **un `tenant`** avec `tenant_id = "lieu-<n>"`, `name = nom`, `domain = ""`, `url = url du
  lieu`, `locality = adresse`, et les autres champs vides. La carte de la liste
  (`buildLieuCard`) affiche `locality`, jamais `address_display` : c'est donc `locality` qui
  porte l'adresse dans la liste ;
- **un `point`** avec :
  - `pa_id = "lieu-<n>:0"`, `latitude`, `longitude`, `pa_name = nom`,
    `address_display = adresse`, `tenant_id = "lieu-<n>"`, `tenant_organisation = nom`,
    `tenant_domain = ""`, `url = url du lieu` ;
  - `events_futurs` : **tous** les événements du lieu, triés par date. Chacun porte
    `uuid = "lieu-<n>-ev-<m>"`, `name`, `datetime_iso = date`, `slug = ""`, `url`, et
    `tags = [{"slug": slugify(t), "name": t}, ...]` ;
  - `events_futurs_count_total` : le nombre d'événements.

Le nom `events_futurs` est trompeur pour une carte figée. On le garde pourtant : c'est la clé
que lit `explorer.js`, et on ne renomme rien.

**Pas de limite à 5 événements par lieu.** La carte réseau tronque à 5 dans le cache
(`LIMIT_EVENTS_DANS_POPUP`). Ici, un lieu peut porter 22 événements (la Maison de
l'Hospitalité dans le bilan JPTO). Ils doivent tous apparaître dans la liste. Le
constructeur vérifie que la popup reste lisible avec 20 événements. Si elle ne l'est pas, il
coupe la liste de la **popup seulement**, dans le JS, et affiche le « + N » qui existe déjà.

### 6.2 Les gabarits du bloc

**Deux gabarits, car le skin V2 habille l'explorer avec son propre balisage.** `V2.css` pose
`#explorer-root .explorer-map { position: absolute; inset: 0 }` à l'intérieur d'un `.map-panel`.
Le widget du socle n'a pas ce panneau : en V2, la carte recouvrait toute la page (vu dans
Chrome). La coquille V2 de l'explorer est donc sortie de `V2/vues/reseau.html` dans
`pages/V2/partials/explorer_coquille.html`. La page réseau et le bloc V2
(`pages/V2/partials/bloc_carte_figee.html`) l'incluent tous les deux, sans copie. Les variables
`avec_liste_serveur` et `avec_lien_explorer_global` ne sont posées que par la page réseau.

**Le socle (tous les autres skins) :**

Nouveau gabarit **socle** : `pages/templates/pages/classic/partials/bloc_carte_figee.html`.
Le résolveur de gabarits (`pages_tags.py`, autour de la ligne 1179) le trouve pour tous les
skins.

Il reprend le gabarit `pages/classic/vues/reseau.html` :
- Les `<link>` Leaflet, MarkerCluster et `seo/explorer.css` sont posés **dans le body**. Même
  raison que dans `reseau.html` : la navigation HTMX ne remplace que le body.
- Il inclut `{% include "seo/partials/explorer_widget.html" %}`, avec :
  - `explorer_data` : le résultat de la conversion du §6.1 ;
  - `current_tenant_uuid` vide, donc pas de « Vous êtes ici » ;
  - `maptiler_key`, déjà fourni à tous les gabarits par le context processor
    `TiBillet/maptiler.py`. Le constructeur le vérifie.
- **Libellé de la popup.** Le JS lit « Prochains événements : » dans `data-i18n-next-events`.
  Le bloc doit afficher « Événements : ». Si le partial ne permet pas de surcharger cet
  attribut, le constructeur ajoute une variable optionnelle au partial, avec l'ancien texte
  par défaut. La page réseau ne doit pas changer.
- Les `<script>` (`leaflet.js`, `markercluster.js`, `cartes/tb_fond_de_carte.js`,
  `explorer.js`) sont posés en fin de gabarit. `explorer.js` sait déjà démarrer après un swap
  HTMX (il teste `document.readyState`).
- `data-testid="bloc-carte-figee"` sur la section, et un titre `h2` si `titre` est rempli.

**Point à vérifier : deux copies de Leaflet.** Le bloc LIEU charge
`pages/vendor/leaflet/`, la carte réseau charge `seo/vendor/leaflet/`. Si une page contient
un bloc LIEU et un bloc carte figée, Leaflet risque d'être chargé deux fois. Le constructeur
vérifie ce cas, et charge une seule copie, par exemple avec un garde sur `window.L`.

**L'aperçu en direct de l'éditeur** (`apercu_bloc.css`, `admin_apercu.py`) doit afficher la
carte, ou au minimum un message clair. Le constructeur vérifie lequel des deux il obtient.

### 6.3 La retouche de `explorer.js`

Aujourd'hui, les liens sont construits avec le domaine TiBillet et le slug :
`'https://' + domain + '/'` et `'https://' + domain + '/event/' + slug + '/'`. Cela se passe
à 5 endroits : la carte de lieu (~l. 754), l'accordéon d'événements (~l. 831), la liste
d'événements (~l. 856) et la popup (~l. 1120 et 1150). Deux fonctions reconstruisent en plus
leurs objets champ par champ, et doivent recopier `url` : `collectVisibleEvents` et
`buildLieuCardsFromPAs`. Deux fonctions portent la règle : `lienDuLieu` et `lienDeLEvenement`.

La retouche : **si l'objet porte une `url`, on l'utilise. Sinon, on garde le calcul actuel.**
Un lieu ou un événement sans URL ni domaine reste sans lien utilisable, comme aujourd'hui
(`'#'`). Le constructeur vérifie que le bouton « Visiter le lieu » n'apparaît pas quand il
n'y a pas de lien.

Les données de la page réseau et de `/explorer/` ne portent pas de clé `url`. Leur
comportement ne change donc pas.

## 7. Les tests

**pytest (`tests/pytest/`)**
- `nettoyer_carte_figee` :
  - un fichier valide ;
  - chaque erreur du §3, une par test ;
  - le refus d'une URL `javascript:` ;
  - une clé inconnue ignorée ;
  - les nombres reçus en texte.
- La conversion du §6.1 : la forme des `points` et des `tenants`, le tri par date, et l'absence
  de limite à 5 événements.
- L'admin :
  - un import valide enregistre les données ;
  - un import en erreur n'enregistre rien et garde les anciennes données ;
  - un fichier vide à la modification garde les données ;
  - un deuxième bloc carte figée sur la même page est refusé.
- Le rendu de la page : le gabarit contient `#explorer-data` avec les lieux.

**E2E (`tests/e2e/`, Playwright)**
- Une page avec un bloc carte figée :
  - les marqueurs sont présents ;
  - la liste contient les lieux ;
  - au clic sur un lieu, ses événements s'affichent ;
  - un lien d'événement pointe vers l'`url` du fichier.
- La bascule lieux/événements et un filtre de tag fonctionnent.
- **Non-régression** : la page « Autour de nous » garde ses liens `https://<domaine>/event/<slug>/`.

Chaque test doit être vu **échouer** sur une mutation volontaire avant d'être livré.

## 8. Le reste du livrable

- Un fichier `CHANGELOG/2026-MM-JJ-bloc-carte-figee.md`, avec « Migration : Oui » et la commande.
- Les nouvelles chaînes traduisibles sont **signalées au mainteneur**. On ne lance ni
  `makemessages` ni `compilemessages`.
- Une ligne « 08 » dans `INDEX.md`.

## 9. Ce qui reste au constructeur

- Le nom exact des fonctions, et le module de la conversion (`pages/services.py` ou à côté).
- La façon de masquer `donnees_carte_figee` dans le formulaire : exclusion ou lecture seule.
- La présentation de la ligne de résumé dans l'éditeur.
- La solution au double chargement de Leaflet, si le cas se produit vraiment.
- La coupe de la popup, si 20 événements la rendent illisible.
- Le rendu dans l'API v2 pages (catalogue `block-types`) : le nouveau type y apparaîtra
  peut-être via `CHAMPS_PAR_TYPE`. Le constructeur vérifie que rien ne casse. Il n'ajoute pas
  d'import JSON par l'API dans ce chantier.

## Journal

- 2026-11-03 : spec écrite à partir du brainstorming avec le mainteneur.
- 2026-11-03 : relecture Fable. Corrigé : nom de la vue réseau, deux fonctions JS oubliées,
  ordre `clean()` du formulaire / `Bloc.clean()`, chemin d'écriture par l'API v2, adresse
  absente de la carte de la liste.
- 2026-11-03 : codé. Écarts avec la spec d'origine : module `pages/carte_figee.py` (et non
  `editeur_items.py`), erreurs du modèle en `NON_FIELD_ERRORS`, gabarit V2 + coquille partagée.
  pytest : 31 tests du bloc + 312 tests pages/fédération/SEO verts. E2E : 5 tests du bloc + 12
  de l'explorer verts. Mutations vues échouer (URL `javascript:`, lien d'événement).
  Vérifié dans Chrome sur `lespass` (skin V2) avec le bilan JPTO 2026 (72 lieux, 161 événements).
- 2026-11-03 : vérification mobile faite par le mainteneur dans Chrome (OK).
- 2026-11-03 : relecture sécurité Fable, tout corrigé :
  - XSS par guillemet dans une URL (`href` refermé) : URL validée par `urlsplit` (http/https,
    domaine présent, ni guillemet, ni chevron, ni espace, ni caractère de contrôle) ET
    `escapeHtml` échappe `"` et `'` ;
  - `RecursionError` sur un JSON très imbriqué → message clair ;
  - dates limitées à trois formes exactes ; textes limités à 200 caractères ;
  - double message d'erreur à l'import (drapeau `_fichier_importe_refuse` posé par le formulaire) ;
  - slugs de tags uniques et non vides ; événement sans lien rendu en texte ; popup limitée à 5 ;
  - `donnees_carte_figee` vidé par `Bloc.clean()` hors `CARTE_FIGEE` (écriture API sur un autre type).
  Tests : 384 pytest et 19 E2E verts ; 7 mutations vues échouer (guillemets, RecursionError,
  drapeau, vidage, forme de date, slug ASCII, `escapeHtml`).
- **Non fait :** pas de liste HTML côté serveur pour les robots (la carte n'existe que dans le
  JSON) ; pas de vérification mobile du double chargement de Leaflet (bloc LIEU + carte figée
  sur une même page).
