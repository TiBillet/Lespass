# Chantier 01 — Description longue des évènements

**Date :** 2026-11-27
**Statut :** codée le 2026-11-27 (parties A à E), relue par Fable, non commitée
**Hub :** [INDEX.md](INDEX.md)

---

## 1. Le problème

Sur https://la-filature.tibillet.coop/event/la-bande-a-balk-270109-2020-d2f19c17/,
la description de l'évènement s'affiche en deux morceaux :

- un début en **gris**, dans une colonne étroite ;
- la suite en **noir**, sur toute la largeur.

Le texte venait d'un mail Protonmail, copié puis collé dans l'admin. Entre ce qui
est collé, ce que montre l'admin à la réouverture et ce que montre le site, le
texte change. Il perd des paragraphes, des listes et des espaces.

Ce chantier corrige les quatre couches en cause : le rendu public, l'éditeur
Trix, le nettoyage serveur et les entrées en texte brut.

---

## 2. Ce qui a été constaté (et comment)

Tout a été vérifié le 2026-11-27 : API v2 de La Filature (lecture seule), base de
dev, Chrome sur `https://lespass.tibillet.localhost/`, events de test
« Test texte riche » et « Test wizard texte » en dev.

### C1 — Le template met du HTML de bloc dans un `<p>` (cause du gris/noir)

`pages/templates/pages/V2/vues/evenement.html` (bloc `evenement_description`) :

```html
<p class="page-intro">{{ event.long_description|safe }}</p>
```

Le HTML interdit un `<p>`, un `<ul>` ou un `<h2>` à l'intérieur d'un `<p>`. Le
navigateur ferme donc le `<p class="page-intro">` dès le premier bloc rencontré.
La suite du texte sort du conteneur.

`.page-intro` (`V2.css`) vaut `color: var(--color-text-muted); max-width: 62ch`.
Résultat mesuré dans Chrome sur la page de prod :

| Morceau | Conteneur réel | Couleur | Largeur |
|---|---|---|---|
| `Créé en 2008 … responsable.` | `p.page-intro` | gris `rgb(99,81,94)` | 62ch |
| `<p>La Bande à Balk, c'est aussi :</p>` et la suite | aucun | noir `rgb(23,20,26)` | pleine |

Le rendu dépend donc de la **première balise** du texte :

- texte tapé au clavier (pas de `<p>` après nettoyage) → tout en gris, 62ch ;
- texte qui commence par un `<p>` (collage) → `p.page-intro` vide, tout en noir.

Le premier bloc gris de la page de prod est la `short_description`. Il est
rendu normalement juste au-dessus.

**Origine :** jusqu'au commit `3dc853fc` (2026-10-07, « update according to
DA »), la description longue était rendue dans sa propre section :

```html
<section class="section" id="schedule" data-testid="evenement-description">
    <h2 class="section__title">{% translate 'À propos' %}</h2>
    <div class="event-prose">{{ event.long_description | safe }}</div>
```

Ce commit l'a déplacée dans l'en-tête, en `<p class="page-intro">`. La classe
`.event-prose` existe toujours dans `V2.css` (puces, marges, tableaux, largeur
70ch), mais **plus aucun template ne l'utilise**.

### C2 — Pas de puces ni de marges sur le site

Hors de `.event-prose`, le reset global `ul { list-style: none; padding: 0 }`
(`V2.css`) s'applique. Mesuré dans Chrome : `ul` sans puce, `h2` à 31 px (la
taille des titres de section de la page), marges des `<p>` à 0.

### C3 — nh3 supprime les `<div>` de Trix

Trix (Unfold 0.89, Trix 2.1.1) écrit chaque bloc dans un `<div>`. Une saisie au
clavier donne, mesuré dans Chrome :

```html
<div>Bonjour,<br><br>Deuxième paragraphe.<br>Ligne suivante.</div>
```

`ALLOWED_TAGS` (`Administration/utils.py`) ne contient pas `div`. nh3 retire la
balise et garde son contenu :

```
<div>Bonjour,<br><br>Para 2</div><div><br></div><ul>…</ul><div>fin</div>
→ Bonjour,<br><br>Para 2<br><ul>…</ul>fin
```

Le texte enregistré n'a plus de structure de blocs. C'est pour ça que la
description de La Bande à Balk commence par `<br><br> Créé en 2008…` : ce sont
les restes des blocs du début, supprimés par la personne.

### C4 — Un collage HTML éclate les listes et colle les paragraphes

Reproduit en dev avec `editor.insertHTML()`. C'est la fonction appelée par Trix
pour un collage HTML. Le vrai presse-papiers n'est pas pilotable depuis
l'extension Chrome. Source : un mail typique avec des `<p>` et une liste
indentée.

Sortie de Trix :

```html
<p>Bonjour,<br>Présentation :La Bande est un groupe.<br>Créé en 2008 avec le
<a href="https://cmtra.org/">CMTRA</a>.La Bande, c'est aussi :</p>
<div> </div><ul><li>une dizaine de musiciens,</li></ul>
<div> </div><ul><li>de nombreux <a …>concerts</a>,</li></ul>
<div> </div><ul><li>4 albums.</li></ul>
<p>Lien : <a …>…</a></p><div><br></div>
```

Deux défauts :

1. **Listes éclatées.** Les espaces et retours à la ligne entre deux `<li>`
   deviennent des blocs `<div> </div>`. Chaque puce finit dans son propre `<ul>`.
   Après nh3 : `</ul> <ul>`, exactement comme en prod.
2. **Paragraphes collés.** Les `<p>` consécutifs fusionnent en un seul, sans
   espace : « Présentation :La Bande ». Voir C5.

Un mail mis en page avec un tableau (newsletter) est mis à plat :
`Grand titre H1Texte font bleu | <img …>`. Le `<h1>` (absent de Trix) et
l'`alt` des images disparaissent. L'image reste chargée depuis le site d'origine.

### C5 — Le bloc `p` d'Unfold fusionne les paragraphes, même sans collage

La config d'Unfold (`unfold/forms/js/trix.config.js`) déclare :

```js
Trix.config.blockAttributes.p = { tagName: "p", breakOnReturn: true, terminal: true }
```

Il manque `group: false`. Trix regroupe donc les `<p>` qui se suivent en un seul
bloc et colle leur texte. Mesuré dans Chrome, **à la simple ouverture** du
formulaire :

| HTML en base | Ce que Trix renvoie dans le champ |
|---|---|
| `<p>Un.</p><p>Deux.</p><p>Trois.</p>` | `<p>Un.Deux.Trois.</p>` |
| `<p>Intro :</p><ul><li>a</li></ul><p>Fin.</p>` | inchangé (la liste sépare) |
| idem, avec `blockAttributes.p.group = false` | `<p>Un.</p><p>Deux.</p><p>Trois.</p>` |
| `<div>Un.</div><div>Deux.</div>` | inchangé |

Conséquence : tout contenu en `<p>` consécutifs est **abîmé au premier
enregistrement dans l'admin**, même sans y toucher. C'est le cas des
descriptions créées par l'API v2 ou collées. Sur les 91 events de La Filature,
2 ont des `<p>` consécutifs.

Le bouton ¶ de la barre ne crée qu'un seul paragraphe : la touche Entrée revient
au bloc `<div>` par défaut (vérifié avec la config Unfold intacte).

### C6 — Chaque enregistrement ajoute un `<br>` en fin de texte

Mesuré en dev en réenregistrant trois fois le même event sans le modifier :

```
…</p><br>   →   …</p><br><br>   →   …</p><br><br><br>
```

Mécanisme : nh3 transforme `<div><br></div>` en `<br>`. Trix relit ce `<br>` nu
et le remet dans un bloc avec un `<br>` de plus : `<div><br><br></div>`. Au
prochain nettoyage, on obtient `<br><br>`, et ainsi de suite. Sur La Filature,
10 events finissent par des `<br>` et 7 commencent par des `<br>`.

Quand les `<div>` sont conservés, l'aller-retour Trix est **stable** (vérifié :
`loadHTML(x)` puis relecture donne `x`).

### C7 — Le texte brut perd ses sauts de ligne (wizard public)

Le wizard « Ajouter un évènement » (`/event/propose/`) a une `<textarea>`
(`BaseBillet/templates/fonctionnel/event_wizard/_events_inner.html`).
`_creer_event_depuis_brouillon` (`BaseBillet/views.py`) enregistre le texte tel
quel, passé par `clean_html`. Le template l'affiche ensuite avec `|safe`, comme
du HTML.

Saisi dans Chrome :

```
Bonjour,

Premier paragraphe.
Ligne 2.

- puce un
- puce deux

Lien : https://exemple.org
```

Affiché sur la page : `Bonjour, Premier paragraphe. Ligne 2. - puce un - puce deux Lien : https://exemple.org`,
sur une seule ligne, lien non cliquable. Le texte est intact en base, mais à
l'ouverture dans l'admin, Trix le met aussi sur une seule ligne :
`<div>Bonjour, Premier paragraphe. … https://exemple.org</div>`. Le premier
enregistrement par un modérateur (validation d'une proposition) **perd les
sauts de ligne pour de bon**.

Sur La Filature : 16 events en texte brut, dont aucun avec un saut de ligne.
Le risque est réel mais pas encore arrivé.

L'API v2 (`EventCreateSerializer.validate_description`,
`EventPatchSerializer.validate_description`) a le même comportement pour une
`description` en texte brut.

### C8 — Ce qui n'est pas en cause

- **Les serializers de l'API v2** : ils appellent `clean_html`, comme l'admin.
  L'event de La Filature a été saisi dans l'admin.
  Deux autres chemins d'écriture **n'appellent pas** `clean_html` (voir §4) :
  l'API historique (`ApiBillet/serializers.py`, `EventCreateSerializer` et
  `EventWriteSerializer`) et l'import CSV de l'admin (`EventResource` dans
  `Administration/admin_tenant.py`, qui ne passe pas par `save_model`).
- **Les balises de la barre d'outils** : H2, H3, H4, gras, italique, souligné,
  barré, lien, citation, code, listes. Toutes passent nh3 sans perte (vérifié).

---

## 3. Ce qu'on change

Cinq parties. A, B et C sont indépendantes et livrables séparément. A seule
règle le gris/noir sur le site.

### A — Rendu public : la description longue dans un `<div class="event-prose">`

**Fichier :** `pages/templates/pages/V2/vues/evenement.html`, en-tête de
l'évènement (`.event-hero__body`).

**Ordre décidé par le mainteneur (2026-11-27) :** titre → description courte →
galerie d'images (`Event.carrousel`) → description longue → fiches pratiques
(Quand / Où / Organisé par). Avant, la galerie était entre le titre et la
description courte, et les deux descriptions se suivaient sans espace.

La galerie entre dans le bloc `evenement_description`, entre les deux
descriptions. Les noms de blocs sont figés par le contrat de skin : on ne les
renomme pas, on n'en crée pas. Aucun autre template n'étend la page V2.

```html
{% block evenement_description %}
{% if event.short_description %}
    <p class="page-intro" data-testid="evenement-description-courte">{{ event.short_description }}</p>
{% endif %}

{# Galerie d'images de l'évènement (Event.carrousel, rempli dans l'admin). #}
{# Entre la description courte (le résumé) et la description longue. #}
{# / Event image gallery, between the short and the long description. #}
{% if event.carrousel.all %}
    <section class="event-hero__galerie" aria-label="{% translate "Images de l'évènement" %}">
        {% include 'pages/V2/partials/evenement_galerie.html' with slides=event.carrousel.all %}
    </section>
{% endif %}

{% if event.long_description %}
    {# <div> et non <p> : le HTML saisi dans l'admin contient des blocs #}
    {# (paragraphes, listes, titres), interdits dans un <p>. #}
    {# / <div>, not <p>: admin HTML holds block elements. #}
    <div class="event-prose" data-testid="evenement-description-longue">
        {{ event.long_description|safe }}
    </div>
{% endif %}
{% endblock evenement_description %}
```

Mettre à jour le commentaire d'en-tête du template (« La galerie d'images se
place juste sous le titre » → « entre la description courte et la description
longue »).

**Espacements** (`pages/static/V2/css/V2.css`). Le reset global `p { margin: 0 }`
(ligne 366) colle aujourd'hui la description courte au texte qui suit :

- la galerie garde sa marge (`.event-hero__galerie`, ligne 2506 :
  `--space-4` au-dessus, `--space-5` en dessous) ;
- `.event-prose` garde son `margin-top: var(--space-4)` : il sépare la longue
  de la courte quand il n'y a pas de galerie ;
- quand il y a une galerie, la marge du bas de la galerie et le `margin-top`
  de `.event-prose` ne s'additionnent pas (marges verticales fusionnées entre
  blocs voisins) : rien à ajouter ;
- les fiches pratiques gardent leur filet et leur marge (`.venue-facts`,
  `margin-top` et `padding-top` à `--space-5`).

À vérifier dans Chrome avec les quatre cas : courte seule, longue seule, les
deux sans galerie, les deux avec galerie.

**Fichier :** `pages/static/V2/css/V2.css`, compléter `.event-prose` :

- titres `h2`/`h3`/`h4` à une taille de texte courant (ils ne doivent pas
  rivaliser avec le titre de l'évènement) ;
- `blockquote` avec une marge et un filet à gauche ;
- garder `max-width: 70ch` et `color: var(--color-text)`.

Les règles existantes (puces, tableaux qui défilent, `pre`, marge du haut)
restent. Le dernier bloc du texte ne doit pas ajouter de marge avant les
fiches pratiques : `.event-prose > :last-child { margin-bottom: 0; }`.

Pas de règle CSS qui masque les blocs vides (`<div><br></div>`) : au milieu du
texte, ce sont les lignes vides voulues par la personne (et celles ajoutées par
le nettoyage du collage, partie B). Celles du début et de la fin sont retirées
par la partie C.

**Autres skins :**

- `pages/templates/pages/classic/partials/evenement_accordeon.html` :
  `<p>{{ event.long_description | safe }}</p>` → `<div>…</div>`. Même bug,
  dans l'accordéon « Schedule ».
- `faire_festival/vues/evenement.html` : déjà dans un `<div>`, rien à faire.

**Skin classic :** l'ordre des éléments n'y est pas modifié. Seul le `<p>` de
l'accordéon devient un `<div>`.

### B — Éditeur : une ligne de config Trix

**Simplifiée le 2026-11-27, à la demande du mainteneur (« attention à l'usine à
gaz »).** La première version prévoyait un script de nettoyage du collage, une
classe `WysiwygTibilletWidget` et sa pose sur 8 admins. Abandonné : la partie C
recolle déjà, à l'enregistrement, les listes coupées par un collage. Il ne reste
qu'un défaut côté navigateur, la fusion des `<p>` voisins (C5).

**Fichier :** `static/js/trix_paragraphes.js`, chargé sur toute l'admin par
`UNFOLD["SCRIPTS"]` (`TiBillet/settings.py`) :

```js
document.addEventListener("trix-before-initialize", function () {
    Trix.config.blockAttributes.p.group = false;
});
```

Unfold règle déjà sa config Trix de la même façon (`trix-before-initialize`).
À ce moment, `trix.config.js` d'Unfold est chargé : l'ordre des scripts dans le
`<head>` n'a pas d'importance.

**Mesuré dans Chrome (dev) :**

- `<p>Un.</p><p>Deux.</p><p>Trois.</p>` : sans le script, la fiche ouvre
  `<p>Un.Deux.Trois.</p>` ; avec, les trois paragraphes restent.
- Collage d'un HTML de mail (paragraphes, liste indentée, gras, lien) par
  `editor.insertHTML` : l'éditeur montre la liste coupée en trois et des
  `<div> </div>` **jusqu'à l'enregistrement**. En base : paragraphes séparés,
  une seule liste, gras et lien gardés. Identique à la réouverture.

**Accepté :** la liste coupée reste visible dans l'éditeur entre le collage et
l'enregistrement.

### C — Serveur : garder les `<div>` et normaliser

**Fichier :** `Administration/utils.py`.

1. Ajouter `"div"` à `ALLOWED_TAGS`, sans attribut. Corrige C3 et C6 : le format
   natif de Trix est conservé, l'aller-retour devient stable. Pas de risque de
   sécurité : un `<div>` sans attribut ne porte ni script ni style.
2. Nouvelle fonction `normaliser_html_editeur(html)`, appelée **après**
   `clean_html`. Elle travaille sur la sortie de nh3, dont la sérialisation est
   régulière : de simples remplacements par regex suffisent. Pas de nouvelle
   dépendance (ni `bs4` ni `lxml` dans le projet).
   Dans les motifs ci-dessous, « vide » veut dire `(?:\s|&nbsp;)*` : nh3
   sérialise l'espace insécable en `&nbsp;`, que `\s` ne voit pas. (Les
   données mesurées en prod et en dev contiennent un espace simple, mais Trix
   écrit parfois des `&nbsp;`.)
   - fusionner deux listes voisines : `</ul>` vide `<ul>` → rien, idem pour `ol`.
     Trix ne peut pas produire deux listes collées sans bloc entre elles : la
     fusion ne casse rien de voulu ;
   - retirer les blocs qui ne contiennent que du vide : `<div>` vide `</div>` ;
   - au **début** du texte : retirer les `<br>` nus, les blocs
     `<div>(?:\s|&nbsp;|<br>)*</div>`, et les `<br>` placés en tête du premier
     `<div>` (`<div><br><br> Créé…` → `<div>Créé…`) ;
   - à la **fin** du texte : même chose en miroir (`<br>` nus, blocs faits
     uniquement de `<br>` comme `<div><br><br></div>`, `<br>` en queue du dernier
     `<div>`).

   Ces règles visent ce que **Trix renvoie** pour l'ancien format, pas seulement
   ce qui est en base : Trix ré-emballe un `<br>` nu de fin en
   `<div><br><br></div>` (C6), et un texte nu de début dans un `<div>` (C7).
3. `sanitize_textfields` (`Administration/admin/site.py`) appelle
   `clean_html` puis `normaliser_html_editeur`. Les deux validateurs
   `validate_description` de l'API v2 et `_creer_event_depuis_brouillon` font
   de même.

Avec ces règles élargies, le contenu existant se répare au premier
enregistrement dans l'admin : Trix relit l'ancien format, la normalisation retire
ce qu'il a ré-emballé. Un test E2E le prouve (§5 : trois enregistrements d'un
event à l'ancien format donnent la même valeur dès le premier).

### D — Texte brut : le convertir en HTML à l'entrée

**Fichier :** `Administration/utils.py`, nouvelle fonction
`texte_brut_vers_html(texte)`.

- Si le texte contient déjà une balise HTML : rendu tel quel (c'est du HTML).
- Sinon, dans cet ordre (vérifié dans le conteneur par la relecture) :
  1. `urlize(texte, nofollow=True, autoescape=True)` sur le texte brut. Avec
     `autoescape=True`, `urlize` échappe lui-même le texte : pas d'`escape`
     séparé. Il doit passer **avant** les `<br>` : sinon `https://x.org<br>Suite`
     est lu comme une seule URL.
  2. remplacer chaque `\n` par `<br>\n` (le `\n` garde un espace entre les
     mots pour `striptags`, voir plus bas) ;
  3. entourer le tout d'un `<div>` ;
  4. `clean_html` puis `normaliser_html_editeur`, comme partout.

  Avant l'étape 1, les entités sont décodées (`html.unescape`) : un texte sans
  balise déjà en base est la sortie de nh3, donc déjà échappé (`Tom &amp; Jerry`).
  Une balise est un nom suivi d'une espace, d'un `/` ou d'un `>` :
  `<jean@exemple.org>` n'en est pas une.

  Résultat mesuré : `rel="nofollow"` conservé, un `<script>` fait passer le texte
  pour du HTML et `clean_html` le retire, `&` correct dans les URL, adresses mail en `mailto:` (schéma autorisé), point final
  hors du lien, `\r\n` du textarea ramenés à `\n` par nh3. C'est le format que
  Trix produit pour une saisie au clavier.

  **Vérifié le 2026-11-27 dans Chrome :** Trix relit `<br>\n` sans ajouter de
  saut de ligne (le `\n` devient un espace). Trix retire en revanche le
  `rel="nofollow"` des liens au premier enregistrement dans l'admin.

**Effet de bord sur les meta descriptions :**
`{{ event.long_description|striptags|truncatechars:150 }}` sert de meta
description, `og:description` et `twitter:description`
(`pages/templates/pages/V2/vues/evenement.html` lignes 43, 48, 54 ; idem classic
et faire_festival) et de description JSON-LD (`pages/templatetags/pages_tags.py`).
`striptags` sur `Bonjour,<br>Premier` donne `Bonjour,Premier`. Le `<br>\n` évite
ce collage pour le texte brut converti. Les events saisis dans l'admin ont déjà
ce défaut : hors périmètre, mais à noter.

**Appels :**

- `_creer_event_depuis_brouillon` (`BaseBillet/views.py`), avant `clean_html` ;
- `EventCreateSerializer.validate_description` et
  `EventPatchSerializer.validate_description` (`api_v2/serializers.py`).
  À documenter dans `api_v2/openapi-schema.yaml` (maintenu à la main) et dans
  le skill `TECH_DOC/SKILLS/tibillet-api/` : « un texte sans balise est
  converti en HTML, sauts de ligne compris ».

**Décidé (2026-11-27) :** les URL du texte brut deviennent cliquables
(`django.utils.html.urlize`). Dans le wizard, une personne colle souvent un lien
de billetterie ou de vidéo. `urlize` ajoute `rel="nofollow"`, qui est autorisé
par `ALLOWED_ATTRIBUTES`.

### E — Réparer les events déjà en base

**Décidé (2026-11-27) :** on répare tous les events de tous les lieux, sans
attendre leur prochain enregistrement.

**Fichier :** `Administration/management/commands/normaliser_textes_riches.py`
(BaseBillet n'a pas de dossier de commandes ; les fonctions viennent
d'`Administration/utils.py`).

`manage.py normaliser_textes_riches [--dry-run]` parcourt tous les tenants
(sauf `public`) et, pour chaque event dont `long_description` n'est pas vide :

1. texte sans balise HTML → `texte_brut_vers_html` (partie D : les sauts de
   ligne et les URL du wizard sont rendus) ;
2. HTML → `clean_html` puis `normaliser_html_editeur` (partie C) ;
3. enregistre par `Event.objects.filter(pk=…).update(…)` seulement si la
   valeur change : ni `save()`, ni signaux, ni traitement d'image.

Elle affiche, par tenant, le nombre d'events lus et changés. Avec
`--dry-run`, elle n'écrit rien et affiche aussi, pour les trois premiers events
changés, l'avant et l'après. Elle est stable : la relancer ne change plus rien.

**Ce qu'elle ne répare pas :** les paragraphes déjà collés en base
(`<p>Un.Deux.</p>`, C5) et les listes dont les puces sont déjà fusionnées. Le
texte d'origine est perdu, il n'y a rien à retrouver.

**Volume connu :** sur La Filature, 10 events avec des `<br>` en fin, 7 avec des
`<br>` en début, 1 avec des listes éclatées, 16 en texte brut. Les autres lieux
n'ont pas été mesurés : le `--dry-run` en prod donne ce chiffre.

**En production :** c'est le mainteneur qui lance la commande, après le
déploiement des parties C et D. D'abord `--dry-run`, ensuite la vraie passe.
Faire un dump de la base avant la vraie passe.

**Tests (pytest) :** un event par cas (texte brut multiligne, `<br>` en début
et en fin, listes voisines, HTML déjà propre) ; vérifier la valeur après la
commande, que `--dry-run` n'écrit rien, et qu'une deuxième passe ne change rien.

---

## 4. Hors périmètre (candidats pour un chantier 02)

Les parties B et C profitent automatiquement à **tous** les champs Trix, car la
config Trix et `clean_html` sont partagées.

**Fait en session 2 (2026-11-27) :** les six templates ci-dessous rendaient un
texte riche dans un `<p>`. Comme la partie C garde les `<div>`, ils sont passés
en `<div>` (même classe CSS) pour ne pas casser. Reste hors périmètre : leur
style (couleur, puces, marges), comme pour les intros V2.

| Template | Champ | Défaut (avant la session 2) |
|---|---|---|
| `BaseBillet/templates/commun/adhesion/form.html` | `product.long_description` | dans `<p>` (même bug que C1) |
| `crowds/templates/crowds/views/detail.html` | `initiative.description` | dans `<p class="lead">` (même bug que C1) |
| `crowds/templates/crowds/views/list.html` | `crowd_config.description` | dans `<p class="text-muted">` |
| `pages/templates/pages/classic/vues/accueil.html` | `config.long_description` | dans `<p class="lead">` |
| `pages/templates/pages/classic/vues/adhesions.html` | `product.long_description` | dans `<p class="card-text">` |
| `pages/templates/pages/classic/vues/compte/membership/membership_card.html` | `product.long_description` | dans `<p class="card-text">` |
| `V2/vues/services.html`, `adhesions.html`, `reseau.html`, `agenda.html` | textes d'intro | `<div class="page-intro">` : structure correcte, mais gris et sans puces |

Autres points connus, laissés de côté :

- **Écritures sans `clean_html`** pour `Event.long_description` :
  - API historique : `ApiBillet/serializers.py` (`EventCreateSerializer` ligne
    ~394, appelé par `ApiBillet/views.py` ~346 ; `EventWriteSerializer` lignes
    ~1423 et ~1444, appelé par `ApiBillet/views.py` ~322 et ~332) ;
  - import CSV de l'admin : `EventResource` (`Administration/admin_tenant.py`,
    champ `long_description`). django-import-export ne passe pas par
    `save_model`, donc pas par `sanitize_textfields`.

  Ces chemins ne reçoivent ni la partie C ni la partie D. Un CSV avec des
  sauts de ligne garde le défaut C7. À brancher sur `texte_brut_vers_html` +
  `clean_html` + `normaliser_html_editeur` dans un chantier suivant (c'est
  aussi une question de sécurité pour l'API historique, qui accepte du HTML
  non nettoyé).

- Onboarding (`onboard/templates/onboard/steps/04_descriptions.html`) : même
  textarea en texte brut que C7, pour `Configuration.long_description`.
  `texte_brut_vers_html` s'y branchera.
- Tableaux de mail mis à plat par Trix (C4) : Trix ne gère pas les tableaux.
  Accepté.
- Images collées depuis un mail : chargées depuis le site d'origine (lien
  externe), `alt` perdu. Accepté pour l'instant.

---

## 5. Tests

Avant de livrer, chaque test doit être vu **échouer** sur une mutation volontaire
du code testé (voir la mémoire « vérification par mutation »).

### pytest (`tests/pytest/`)

- `clean_html` garde un `<div>` et retire ses attributs.
- `normaliser_html_editeur` : listes voisines fusionnées (séparées par un
  espace **et** par un `&nbsp;`), `<div> </div>` retiré, `<br>` et blocs vides
  de début et de fin retirés (y compris `<div><br><br> Texte` et
  `<div><br><br></div>` final), lignes vides du milieu inchangées.
- `normaliser_html_editeur` est stable : l'appliquer deux fois donne le même
  résultat.
- `texte_brut_vers_html` : sauts de ligne → `<br>`, texte échappé (`<script>`
  reste du texte), URL suivie d'un saut de ligne correctement coupée, HTML
  existant non modifié.
- Wizard : un event créé avec un texte multiligne est enregistré en
  `<div>…<br>…</div>`.
- API v2 : une `description` en texte brut est enregistrée en HTML.
- Rendu V2 : la page d'un event dont la description commence par `<p>` contient
  `data-testid="evenement-description-longue"` et le texte complet **à
  l'intérieur** de ce `<div>`.
- Rendu V2 : ordre dans le HTML de la page = `evenement-description-courte`,
  puis la galerie, puis `evenement-description-longue`.
- `sanitize_textfields` appliqué deux fois donne le même résultat (ne passe pas
  par Trix : le vrai test de C6 est en E2E).

### E2E Playwright (`tests/e2e/`)

- Admin event : un contenu `<p>Un.</p><p>Deux.</p><p>Trois.</p>` reste intact
  après un enregistrement (C5). Fait : `tests/e2e/test_admin_texte_riche_enregistrements.py`.
- Admin event : un event à l'ancien format (`<br><br> Texte…</p><br>`, écrit
  directement en base) est ouvert et enregistré trois fois. La valeur est
  propre et identique dès le premier enregistrement (C6).
- Page publique : toute la description est dans `.event-prose` (même couleur
  calculée pour le premier et le dernier paragraphe).

### Test manuel (mainteneur)

Copier le **vrai** mail de la Bande à Balk depuis Protonmail et le coller dans
l'admin de dev. Puis comparer : l'éditeur, la réouverture après enregistrement
et la page publique. C'est le seul test avec le vrai HTML de Protonmail.

Refaire le même test avec un document **Google Docs** (gras, souligné, liste) et
un mail d'un autre webmail (Gmail ou Thunderbird). Le nettoyage du collage n'a
été mesuré que sur un mail de test écrit à la main.

---

## 6. Ordre de réalisation

| Session | Contenu | Livrable seul ? |
|---|---|---|
| 1 | **A** — ordre courte → galerie → longue, templates V2 + classic, CSS `.event-prose`, test pytest de rendu | Oui : règle le gris/noir tout de suite |
| 2 | **C** — `div` autorisé, `normaliser_html_editeur`, branchements, tests | Oui |
| 3 | **B** — `static/js/trix_paragraphes.js` (une ligne), E2E | Oui |
| 4 | **D** — `texte_brut_vers_html`, wizard + API v2 + OpenAPI, tests | Oui |
| 5 | **E** — commande `normaliser_textes_riches`, tests | Après C et D |

Chaque session crée ou complète `CHANGELOG/2026-MM-DD-texte-riche-description-event.md`.
Aucune migration de schéma. Les sessions B et D ajoutent peut-être des chaînes
traduisibles : le workflow i18n est à lancer par le mainteneur.

---

## 7. Décisions du mainteneur (2026-11-27)

1. **Placement (A)** : description courte sous le titre, avant les images ;
   description longue sous la galerie d'images, avant les fiches pratiques.
2. **URL cliquables (D)** : oui, `urlize` sur le texte brut.
3. **Réparation (E)** : on répare tous les events de tous les lieux avec la
   commande `normaliser_textes_riches`.
