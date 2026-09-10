# Peau TiBillet pour l'admin Unfold / TiBillet skin for the Unfold admin

**Date :** 2026-09-08
**Migration :** Non

## Resume / Summary

**Quoi / What :** l'admin Django passe du theme par defaut de django-unfold
(fond gris-bleu froid, accent violet) a l'identite TiBillet de la maquette
`TEMP-tibillet-admin-main/` : papier chaud `#f4f2ec`, vert de marque `#1D9E75`,
densite plus serree, arrondis plus doux. Le mode sombre est conserve.
/ The Django admin moves from django-unfold's default theme to the TiBillet
identity: warm paper, brand green, tighter density. Dark mode is preserved.

**Pourquoi / Why :** une maquette d'identite avait ete produite mais n'etait
pas integree. Le point de depart etait favorable : `UNFOLD` n'avait ni `COLORS`
ni `STYLES`, et **aucun template coeur d'Unfold n'etait surcharge**. Il etait
donc possible de tout faire en deux cles de settings et une feuille CSS, sans
toucher au DOM ni au Python metier.

**Ce qui n'est PAS dans ce lot / Out of scope :** la refonte de l'arborescence
de navigation proposee par la maquette (Domaines *Lespass / Laboutik / Lerezo /
Lekontrib / Lemachines* -> Modules -> onglets *Gerer / Configurer / Analyser*).
C'est un chantier Python (`get_sidebar_navigation`, `dashboard_callback`), pas
un chantier de style. Voir « Suites » en fin de fichier.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/settings.py` (dict `UNFOLD`) | `+ COLORS` (8 rampes), `+ BORDER_RADIUS`, `+ STYLES` |
| `static/css/tibillet-admin.css` | **neuf** — feuille de finition, 42 regles |

Aucun template, aucun `ModelAdmin`, aucun modele n'a ete touche.

## Comment ca marche / How it works

### 1. La palette, en Python seul

`UNFOLD["COLORS"]` est injecte par Unfold en variables `--color-{nom}-{poids}`
dans un `<style id="unfold-theme-colors">` place sur le `<body>`. Toutes les
classes `bg-base-50`, `text-primary-600`, `border-base-200` s'y alimentent :
regler ces rampes recolore l'admin entiere, mode sombre compris, sans CSS.

Les rampes ont ete construites en OKLCH pour retomber **exactement** sur les
couleurs de la maquette aux paliers qui comptent :

| Palier Unfold | Rendu | Jeton de la maquette |
|---|---|---|
| `base-100` | `#f0eee7` | `--line-soft` |
| `base-200` | `#e7e4db` | `--line` |
| `base-400` | `#9a9891` | `--ink-mut` |
| `base-600` | `#5f5e5a` | `--ink-soft` |
| `primary-50` | `#e3f4ec` | `--brand-soft` |
| `primary-600` | `#1d9e75` | `--brand` |
| `primary-800` | `#0f6e56` | `--brand-txt` |
| `font.important-light` | `#26251f` | `--ink` |

L'echelle d'encre de la maquette (`--ink` / `--ink-soft` / `--ink-mut`) tombe
pile sur les trois jetons `font.*` d'Unfold : la correspondance est 1:1.

**Point non documente, verifie dans `unfold/sites.py:_get_colors` :** la boucle
est `for name, weights in colors.items()`, donc **`COLORS` accepte des noms de
rampe arbitraires**, pas seulement `base` / `primary` / `font`. Declarer
`green`, `orange`, `blue`, `red` et `yellow` recolore d'un coup **tous** les
badges `@display(label=...)`, les messages, les booleens et l'interrupteur —
sans une ligne de CSS. C'est ce qui a permis de vider l'etape CSS de moitie.

### 2. La forme, en CSS

`static/css/tibillet-admin.css` ne s'occupe que de la forme : fonds, densite,
arrondis, survols. Il ne redefinit jamais une variable `--color-*`.

Deux regles d'ecriture, notees en tete du fichier, a respecter pour toute
modification future :

1. **Ne jamais envelopper ces regles dans un `@layer`.** Le CSS d'Unfold est du
   Tailwind v4 : ses ~250 Ko d'utilitaires sont dans des `@layer`. Une regle
   **sans** layer gagne toujours sur une regle **dans** un layer. C'est ce qui
   permet de tout redessiner sans `!important` et sans surcharger un template.
2. **Toujours prefixer un selecteur par `html` ou par un `#id`.** Unfold garde
   **78 Ko de CSS hors layer** en fin de son `styles.css` (`tr.selected`,
   `select`, `.selector`, `.datetimeshortcuts`, `.calendarbox`...). Contre
   celui-la on est a specificite egale, et il est charge **apres** nous : sans
   prefixe, c'est lui qui gagne.

La regle la plus importante du fichier est **l'inversion des fonds** : Unfold
met le papier sur la sidebar (`bg-base-50`) et le blanc sur le contenu
(`bg-white`), la maquette veut l'inverse. Sans cette regle, tout le reste
parait a l'envers.

## Bug corrige au passage / Bug fixed along the way

`Administration/templates/admin/dashboard.html:46` affiche le badge « V1 » avec
`bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200`. Or
Unfold ne definit dans son theme que `yellow-200` et `yellow-500` : ces quatre
variables etaient **indefinies** et le badge s'affichait donc **sans couleur**.
Declarer la rampe `yellow` complete dans `COLORS` repare ce bug preexistant.

## Points d'attention / Known caveats

**Couleurs codees en dur dans les fragments d'admin du projet.** Environ 658
attributs `style="..."` contenant un hex, repartis sur 34 fichiers de
`Administration/templates/admin/`. Un style inline bat toute feuille de style :
ces valeurs ne suivront pas la nouvelle palette.

- **Sans danger :** les 9 `var(--color-primary-600, #7c3aed)` — le violet n'etait
  qu'une valeur de repli, elle ne se declenche plus.
- **Corrige gratuitement :** les ~220 classes Tailwind (`bg-red-500`,
  `text-blue-700`...) passent par les rampes semantiques ajoutees a `COLORS`.
- **Derivera visuellement :** les gris froids bruts (`#ddd`, `#f0f0f0`,
  `#6b7280`), surtout dans `admin/cloture_detail.html` (193 occurrences) et
  `admin/cloture/rapport_before.html` (190), deux fichiers quasi identiques qui
  representent 75 % du volume. A traiter dans un ticket dedie.
- **A laisser tel quel :** `#16a34a` / `#dc2626`, verts et rouges semantiques.

**Largeur de la sidebar.** La maquette veut 264px, Unfold code 288px en dur a
trois endroits, dont un decalage pilote par Alpine sur la barre d'actions
groupees. Garde a 288px : le gain visuel ne valait pas les trois points de
fragilite.

**Retour arriere.** Retirer `COLORS`, `BORDER_RADIUS` et `STYLES` du dict
`UNFOLD` restaure integralement le theme d'origine. Aucune migration.

## A tester / To test

### 1. La feuille est bien servie

En DEBUG, `staticfiles` sert le fichier directement depuis `/DjangoFiles/static/` :
**pas besoin de `collectstatic`, pas de redemarrage**. La boucle d'iteration est
un simple Ctrl+Shift+R.

```bash
docker exec lespass_django curl -sI http://localhost:8000/static/css/tibillet-admin.css
# attendu : 200 + Content-Type: text/css
```

Dans les devtools, sur n'importe quelle page d'admin :

- `<link href="/static/css/tibillet-admin.css">` apparait **avant**
  `unfold/css/styles.css` — c'est normal, les `@layer` compensent ;
- `getComputedStyle(document.documentElement).getPropertyValue('--color-primary-600')`
  doit renvoyer `oklch(62.3% 0.123 165.5)` ;
- inspecter `#main` : notre `background-color` doit gagner, la regle `.bg-white`
  d'Unfold apparaissant barree.

### 2. Controle visuel, en mode clair ET en mode sombre

Le mode sombre se bascule depuis la sidebar (ou Ctrl/Cmd + E).

| # | Ecran | URL | Ce qu'on regarde |
|---|---|---|---|
| 1 | Dashboard | `/admin/` | cartes de modules, interrupteurs, **badge « V1 » qui doit enfin avoir une couleur** |
| 2 | Sidebar | n'importe ou | rail **blanc** sur contenu **papier** ; lien actif en pastille vert pale ; titres de section en petites capitales |
| 3 | Changelist dense | `/admin/BaseBillet/event/` | en-tete de colonnes en capitales, **pas de zebrures**, survol de ligne, separateurs discrets, bouton « + » au degrade |
| 4 | Selection de lignes | cocher 2 lignes de l'ecran 3 | ligne selectionnee en **vert pale**, surtout **pas** en jaune pale |
| 5 | Navigation par date | `/admin/BaseBillet/reservation/` | etapes `date_hierarchy` en pastilles |
| 6 | Formulaire + onglets | `/admin/BaseBillet/configuration/` | onglets **soulignes** (et non segmentes), `fieldset` en carte bordee, barre d'enregistrement opaque |
| 7 | Formulaire + inlines | `/admin/BaseBillet/product/` | inlines, `conditional_fields` |
| 8 | Zoo de widgets | `/admin/AuthBillet/humanuser/` (ajout) | **chevron des `select` en gris chaud**, case a cocher, interrupteur vert, date, select2 |
| 9 | Page comptable | `/admin/comptabilite/cloturecaisse/` | pire cas de couleurs codees en dur : **constater** la derive des gris froids, ne pas la corriger ici |
| 10 | Responsive | reduire la fenetre a moins de 1024px sur l'ecran 3 | la changelist bascule en cartes : verifier que les regles de cellules ne cassent rien (elles sont enfermees dans un `@media`, mais a confirmer a l'oeil) |

### 3. Non-regression fonctionnelle

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_*.py -v
docker exec lespass_django poetry run pytest tests/e2e/test_admin_*.py -v -s
```

23 tests E2E traversent l'admin. Un `COLORS` malforme fait lever `_get_colors`
et met **toutes** les pages d'admin en 500 : ces tests attrapent donc
immediatement une erreur de settings. En revanche ils **n'attrapent pas** les
regressions visuelles — l'etape 2 ci-dessus reste indispensable.

Un test E2E cible `.bg-green-100, .bg-blue-100`. On redefinit les *variables*,
jamais les classes : il doit continuer de passer. S'il echoue, c'est le signal
qu'une classe a ete touchee par erreur.

**Deja verifie au moment d'ecrire cette fiche :** `manage.py check` propre,
30 tests pytest d'admin au vert, feuille CSS equilibree (0 `@layer`,
0 `!important`, 42 regles toutes prefixees `html` / `#id` / `@media`).

## Suites / Next steps

1. **Architecture Domaines -> Modules** — `get_sidebar_navigation`
   (`Administration/admin/dashboard.py:50`) et `dashboard_callback` (l. 1317).
   Le projet a deja l'ossature (`MODULE_FIELDS`, cartes de modules, modale
   d'activation) : l'ecart avec la maquette est plus faible qu'il n'y parait.
2. **De-durcir les couleurs** des 34 fragments, en commencant par factoriser
   `cloture_detail.html` et `cloture/rapport_before.html`.
3. **Les 59 `verbose_name` manquants** recenses en fin de
   `TEMP-tibillet-admin-main/ADMIN-HANDOFF.md` : 59 colonnes de l'admin
   s'affichent aujourd'hui en anglais. Les `.po` ne s'editent pas a la main —
   passer par `makemessages` / `compilemessages`.
4. **Supprimer `TEMP-tibillet-admin-main/`** une fois la peau validee (dossier
   non suivi par git aujourd'hui).
