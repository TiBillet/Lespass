# CHANTIER-10 — Le socle : contrat de jetons + identité éditoriale

**Statut :** spec écrite (2026-07-16), en cours de code.
**Propriétaire :** agent socle/classic. **Arbitrage Jonas du 2026-07-16** : le socle
(`pages/templates/pages/classic/**` + `pages/static/pages/css/tb-blocs.css`) a UN
propriétaire unique. Les skins gardent la règle d'autonomie dans leur dossier.

**Objectif :** rendre au socle une identité qui ne soit pas un défaut de framework,
et donner aux skins le contrat de jetons qui leur manque pour poser leur teinte
sans forker `tb-blocs.css`.

## Périmètre — ce qui est touché, ce qui ne l'est PAS

| | |
|---|---|
| ✅ Touché | `pages/static/pages/css/tb-blocs.css`, `pages/templates/pages/classic/**` |
| ❌ PAS touché | `pages/models.py`, **aucune migration** (ce chantier ne crée aucun skin, donc aucune `choice`) |
| ❌ PAS touché | `commun/**` — rayon de souffle hors `pages` (`ticket.html`, `loading.html`). Les `--kouler-*` de `commun/css/vars.css` sont **lus**, jamais modifiés. |
| ❌ PAS touché | `BaseBillet/models.py` — `Tag.style_attr` / `contrast_fg` restent tels quels (voir §5) |

Objections des agents `la_filature` et `miete` sur models.py/migrations/`commun/` :
**acceptées et intégrées ci-dessus.**

## 1. Diagnostic — d'où vient le « générique »

**`--bs-primary` n'est défini nulle part dans le projet.** Aucun champ en base, aucun
template, aucun CSS. Le `#0d6efd` visible partout est le **défaut de Bootstrap 5.3** —
personne ne l'a jamais choisi. Or `tb-blocs.css:47` fait :

```css
--tb-accent: var(--bs-primary, #1d4ed8);   /* le repli #1d4ed8 ne sert JAMAIS */
```

`tb-blocs.css` est par ailleurs un bon système : entièrement tokenisé, thème éditorial
assumé, conforme Hallmark (accent unique, focus visible, reduced-motion, `minmax(0,1fr)`).
**Le problème n'est pas le système : c'est qu'il est chaîné sur une valeur que personne
n'a décidée.**

**Deuxième cause, plus grave :** `tb-blocs.css:24` pose les jetons sur `.tb-page`, et
`classic/page.html:50` met `class="tb-page"` sur le `<main>` **des pages CMS uniquement**.
Donc **navbar, footer, `vues/agenda`, `vues/adhesions`, `vues/evenement` ne reçoivent
aucun jeton `--tb-*`** — ils sont en Bootstrap brut (`btn-primary`, `card`, Ft3). C'est
là que vit l'essentiel du « trop bootstrap ». On ne peut pas les redessiner avec des
jetons qui ne les atteignent pas.

**Troisième :** la seule expression de l'identité du socle est `--mayaj-pons`
(`linear-gradient(90deg, curcuma, letchi)`) sur la barre de dates de l'agenda — le geste
le plus « généré » possible.

## 2. Le parti pris — l'identité existe déjà dans le repo

Le skin par défaut s'appelle **`reunion`**. `commun/css/vars.css` porte une palette
créole nommée (`--kouler-kari`, `--kouler-losean`, `--kouler-letsi`, `--kouler-sousou`,
`--kouler-piton`, `--kouler-pitonbraz`) qui ne sert **qu'aux dégradés**.

**Décision : ne pas inventer une palette OKLCH sortie de nulle part — ce serait
exactement le geste d'IA qu'on fuit. Remonter les kouler au rang d'accent et les sortir
du dégradé.** Le design a alors une raison d'être.

### Contrastes mesurés (WCAG 2.1, calculés — non estimés)

| kouler | sur `#ffffff` | sur `#212529` (sombre) | rôle |
|---|---|---|---|
| `pitonbraz` `#291e26` | **16.06:1** | — | encre |
| `piton` `#63515e` | **7.32:1** | — | encre douce |
| `letsi` `#e93363` | 4.10:1 | 3.76:1 | **geste** (≥3:1, jamais du texte) |
| `letsi-encre` `#e61c51` | **4.52:1** | 3.42:1 | encre portante (clair) |
| `letsi-clair` `#ed547c` | — | **4.53:1** | encre portante (sombre) |
| `kari` `#e9b322` | 1.92:1 | 8.03:1 | geste/fond seulement |
| `losean` `#4296cc` | 3.25:1 | 4.75:1 | geste (clair) |
| `sousou` `#259d49` | 3.50:1 | — | geste |
| ~~`bs-primary` `#0d6efd`~~ | 4.50:1 | — | **à retirer** |

**Règle qui en sort** (convergence indépendante avec `DESIGN-LA-FILATURE.md` § Notes 2 —
les deux agents ont trouvé le même mur) : **une teinte claire et saturée est un geste,
pas une encre.** `letsi` en aplat ne porte **aucun** texte : ni blanc (4.10:1) ni encre
(3.91:1). Les deux échouent.

**Le retournement du jaune** (idée de l'agent `la_filature`, vérifiée et généralisée) :
quand une teinte n'a pas de jumeau encre viable, inverser le rapport — elle devient
**fond**, l'encre passe **dessus**. `kari` en texte sur blanc = 1.92:1 (échec) ;
`kari` en fond avec `pitonbraz` dessus = **8.36:1** (OK).

## 3. LE CONTRAT DE JETONS — figé

**Les NOMS sont figés** (au sens du `CONTRAT-DE-SKIN.md` § 4) et ne changeront plus.
**Les VALEURS par défaut ne le sont pas** : elles sont *testées*
(`tests/pytest/test_socle_contrastes.py`), pas contractuelles, et peuvent être
recalibrées. Un skin ne les copie donc jamais — il pose les siennes.
**La source de vérité des valeurs est le `:root` de `tb-blocs.css`, pas ce fichier.**

```css
/* SOCLE — pages/static/pages/css/tb-blocs.css */
:root {
  --tb-accent:           var(--skin-accent,           #dc184b); /* ENCRE PORTANTE */
  --tb-accent-vif:       var(--skin-accent-vif,       #e93363); /* LE GESTE */
  --tb-accent-contraste: var(--skin-accent-contraste, #ffffff); /* se pose SUR --tb-accent */
  --tb-fond:             var(--skin-fond,             var(--tb-accent));           /* FOND d'un élément plein */
  --tb-fond-contraste:   var(--skin-fond-contraste,   var(--tb-accent-contraste)); /* l'encre SUR --tb-fond */
  --tb-texte-doux:       var(--skin-texte-doux,       #63515e);
}
[data-bs-theme="dark"] {
  --tb-accent:           var(--skin-accent-sombre,           #ef6a8d);
  --tb-accent-contraste: var(--skin-accent-contraste-sombre, #291e26);
  --tb-texte-doux:       var(--skin-texte-doux-sombre,       #a5919f);
}
```

### `--tb-fond` — pourquoi un troisième couple

`--tb-accent` sert **trois** rôles dans le fichier, mesurés sur les 22 usages :
**encre** (`color:`, 7×), **geste** (`border`/`outline`, 7×), **fond**
(`background-color`, 4×, toujours appariées à `--tb-accent-contraste`).

C'est cette conflation qui rend une teinte claire impossible : poser
`--skin-accent: <jaune>` pour obtenir un CTA jaune teinte du même coup
`.tb-fil-ariane a` et `.tb-bloc__texte a` à 1.92:1. Le fond est donc découplé de
l'encre. **Par défaut `--tb-fond: var(--tb-accent)` → comportement strictement
identique si un skin ne pose rien.** Les trois agents ont buté sur cette
conflation indépendamment (l'agent `miete` l'avait même documentée dans
`miete.css:404` en sacrifiant son vermillon de marque à la lisibilité des liens ;
avec `--tb-fond` il récupère les deux).

### La règle du geste sur un aplat *(apport de l'agent `la_filature`)*

`--tb-accent-vif` et `--tb-fond` sont de la **même famille chromatique** — c'est
tout l'intérêt du système, l'œil doit lire une seule couleur. Conséquence directe :
**un filet vif tracé SUR un aplat de sa propre teinte est invisible, par
construction et non par accident.**

> **Règle : `--tb-accent-vif` n'est un geste valide que sur le PAPIER. Sur un
> aplat, le geste passe à `--tb-fond-contraste`.**

Vaut pour tous les skins, pas seulement celui qui l'a découvert.

### Sémantique — pourquoi ces noms

**`--tb-accent` reste LA VALEUR PORTANTE.** C'est déjà sa sémantique de fait :
`tb-blocs.css:205-208` fait `.tb-bloc__bouton--plein { background-color: var(--tb-accent);
color: var(--tb-accent-contraste) }`, et `:219` `.tb-bloc__bouton--contour:hover` idem.
**22 usages** en dépendent. Le renommer en « teinte vive » aurait cassé les 22 : un skin
posant du jaune dans `--tb-accent` obtenait du texte blanc à 1.13:1.

> **Règle retenue (formulation de l'agent `la_filature`, objection acceptée) :
> « ne pas renommer le sûr, nommer le dangereux ».** Le jeton vif est **nouveau** ; le
> jeton portant est **inchangé**. Zéro régression.

**`--tb-accent-vif` est le geste** : filets, bordures, aplats décoratifs. **Le socle n'y
pose JAMAIS de texte.** Un skin peut donc y mettre du jaune sans rien casser.

### Garanties du socle

1. Le socle garantit `--tb-accent-contraste` sur `--tb-accent` **≥ 4.5:1** pour **ses**
   valeurs (clair 4.52:1, sombre 4.71:1).
2. Le socle ne pose **jamais** de texte sur `--tb-accent-vif`.
3. Un skin qui pose `--skin-accent` est **responsable** de fournir un
   `--skin-accent-contraste` cohérent.

### Points d'entrée pour un skin — pourquoi une indirection et pas un `:root`

`classic/page.html:49` charge `tb-blocs.css` **tard** (dans le `<body>`), après le CSS
du skin chargé dans le `<head>` de son `shell.html`. À spécificité égale, **le dernier
chargé gagne** : un `:root { --tb-accent: … }` posé par un skin **perdrait**.
(L'agent `la_filature` avait déjà contourné ça en re-déclarant son `<link>` dans son
`page.html` — le hack devient inutile pour les jetons.)

D'où l'indirection : **le socle LIT une variable que le skin POSE**. Le skin gagne
quel que soit l'ordre de chargement, parce que c'est une *autre* variable.

```css
/* SKIN — n'importe où, n'importe quand dans son propre CSS */
:root { --skin-accent: #0076AE; --skin-accent-vif: var(--couleur-cyan); }

/* Rotation par bloc : la PORTÉE fait gagner, pas l'ordre */
.tb-page .tb-bloc:nth-of-type(3n+1) { --tb-accent: #0076AE; --tb-accent-vif: var(--couleur-cyan); }
```

Chrome (navbar/footer/vues) → `--skin-accent` sur `:root`. Blocs → `--tb-accent` sur un
sélecteur plus profond. Les deux cohabitent : plus de navbar rose au-dessus de blocs CMJ.

**Où poser ses `--skin-*` :** sur `:root` (ou la classe de skin du `<body>`), **jamais
sur un conteneur interne**. Le chrome vit hors de `<main class="tb-page">` : des
`--skin-*` posés sur `.tb-page` ne l'atteignent pas.

### Les 9 points d'entrée, et l'asymétrie du mode sombre

| Point d'entrée | En sombre |
|---|---|
| `--skin-accent` | **remplacé** par `--skin-accent-sombre` |
| `--skin-accent-contraste` | **remplacé** par `--skin-accent-contraste-sombre` |
| `--skin-texte-doux` | **remplacé** par `--skin-texte-doux-sombre` |
| `--skin-accent-vif` | traverse inchangé |
| `--skin-fond` | traverse inchangé |
| `--skin-fond-contraste` | traverse inchangé |

> **Piège :** un skin qui ne pose **que** la version claire de l'un des trois premiers
> retombe **silencieusement** sur le défaut du socle en thème sombre — un letsi rose au
> milieu de son identité. Poser les deux versions, ou aucune.

### Les boutons Bootstrap de marque

`.btn-primary` et `.btn-outline-primary` sont rebranchés sur les jetons dans
`tb-blocs.css` (via `--bs-btn-*`). Un skin n'a donc **rien à faire** pour que le
déclencheur de réservation, le « voir plus » de l'agenda et les boutons de l'accueil
prennent son accent.

`btn-success` / `btn-danger` / `btn-warning` ne sont **pas** rebranchés : ce sont des
couleurs **sémantiques** (le vert d'une adhésion validée, le rouge d'un événement
complet). Ce fichier atteignant aussi le chrome partagé de `commun/`, les repeindre y
casserait le sens.

## 4. Portée levée : `.tb-page` → `:root`

Les jetons quittent `.tb-page` pour `:root`. Conséquence voulue : **le chrome reçoit
enfin les jetons** et devient skinnable en CSS, conformément au `CONTRAT-DE-SKIN.md` § 2
(« retouche visuelle du chrome = CSS global depuis le skin uniquement »).

Les propriétés non-jetons de `.tb-page` (`overflow-x: clip`, `color`, `background-color`)
**restent sur `.tb-page`** — ce sont des règles, pas des jetons.

## 5. Mode sombre — la contrainte non évidente

`tb-blocs.css` n'a **aucune** gestion du sombre : il l'obtient gratuitement en déléguant
à `var(--bs-body-color)` / `var(--bs-body-bg)` / `var(--bs-tertiary-bg)` /
`var(--bs-border-color)`, que Bootstrap permute sur `[data-bs-theme]`.

**Ces chaînes-là sont BONNES et sont conservées.** Elles sont neutres et théme-conscientes.
Seule la chaîne **accent** est cassée : `--bs-primary` n'est pas théme-conscient, c'est
une couleur de marque que personne n'a posée.

**Piège 1 — deux bascules, pas une.** En sombre, l'accent doit s'éclaircir **et
`--tb-accent-contraste` doit passer du blanc à l'encre** (le blanc ne tient pas sur
l'accent éclairci : 2.95:1 ; l'encre `#291e26` passe à 5.44:1). Sans ce second
point, **tous les boutons pleins du site échouent en thème sombre.**

**Piège 2 — le site a DEUX surfaces, il faut calibrer sur la pire.** C'est le piège
le plus coûteux du chantier : **il a frappé trois fois de suite.**

| | corps `--bs-body-bg` | pied `--bs-tertiary-bg` |
|---|---|---|
| clair | `#ffffff` | `#f6f5f1` (plus **sombre**) |
| sombre | `#212529` | `#2b3035` (plus **clair**) |

Le pied de page et les surfaces alternées sont sur la **tertiary**. Une encre
calibrée sur le seul corps de page réussit là où on la teste et **échoue dans le
pied, en silence** :

- `--tb-accent` clair `#e61c51` : 4.52:1 sur blanc, **4.14:1** sur la tertiary → échec
- `--tb-accent` sombre `#ed547c` : 4.53:1 sur le corps, **3.91:1** sur le pied → échec
- `--tb-texte-doux` sombre `#9b8495` : 4.50:1 sur le corps, **3.89:1** sur le pied → échec

Les trois ont été trouvés par le **rendu** et par `test_socle_contrastes.py`, jamais
par un calcul sur une seule surface. Valeurs retenues : `#dc184b` (4.91 / 4.50),
`#ef6a8d` (5.23 / 4.51), `#a5919f` (5.25 / 4.53).

> **Règle : toute encre se calibre sur la surface la PIRE des deux, jamais sur le
> corps de page seul.** C'est ce que vérifie `tests/pytest/test_socle_contrastes.py`.

## 6. Les badges de tags — donnée du lieu, pas design

`Tag.color` est un champ **choisi par le lieu** dans l'admin (défaut `#0dcaf0`). On n'y
touche pas : coder ses catégories par couleur est une vraie fonctionnalité.

Mais `Tag.contrast_fg` (`BaseBillet/models.py:150`) choisit noir/blanc en **YIQ**, qui
n'est pas WCAG : sur `letsi` il retourne blanc → **4.10:1, échec**. `style_attr` produit
donc des badges illisibles selon la couleur choisie.

**`BaseBillet/models.py` est hors périmètre** (partagé, et l'agent `la_filature` a
raison sur le risque de collision). On ne corrige pas `contrast_fg` : **on cesse de
l'utiliser** dans les templates du socle. La couleur du lieu passe en **pastille /
filet**, le libellé en encre. Le code couleur est respecté, la lisibilité est garantie
quelle que soit la couleur choisie, et 17 rectangles cessent de hurler.

## 7. Fichiers

| Fichier | Changement |
|---|---|
| `pages/static/pages/css/tb-blocs.css` | Jetons `.tb-page` → `:root` ; chaîne accent cassée ; `--tb-accent-vif` ajouté ; bloc `[data-bs-theme="dark"]` |
| `pages/templates/pages/classic/vues/agenda_liste.html` | Barre de dates : dégradé `--mayaj-pons` → filet `--tb-accent-vif` |
| `pages/templates/pages/classic/vues/agenda_liste_suite.html` | idem |
| `pages/templates/pages/classic/vues/agenda.html` | Badges de tags : aplat `style_attr` → pastille + encre |
| `pages/templates/pages/classic/partials/carte_evenement.html` | idem + sortie de Bootstrap |
| `pages/templates/pages/classic/vues/adhesions.html` | Grille `card`/`btn-primary` → jetons `--tb-*` |
| `pages/templates/pages/classic/partials/footer.html` | Ft3 + boutons vert/jaune Bootstrap → jetons |
| `pages/templates/pages/classic/partials/navbar.html` | Sortie de `btn-primary` |

## 8. Plan de tests

- `tests/pytest/test_gabarit_skin.py` — doit rester vert (résolution inchangée).
- **Contraste** : script de vérification des couples (`--tb-accent` / `--tb-accent-contraste`)
  en clair ET en sombre, ≥ 4.5:1.
- **Chrome, les 3 skins** : tour visuel `classic` / `faire_festival` / `la_filature` /
  `miete` en clair et en sombre — le fallback fait que le socle atterrit chez eux.
- **Non-régression jetons** : aucun `var(--bs-primary)` restant dans `tb-blocs.css`.

## 9. Journal

- **2026-07-16** — Diagnostic (`--bs-primary` non défini ; jetons prisonniers de
  `.tb-page` ; identité kouler enterrée sous les dégradés). Arbitrage Jonas : le socle a
  un propriétaire unique. Objections `la_filature` sur models.py / migrations / `commun/`
  acceptées. **Objection sur le nommage du crochet acceptée** — `--tb-accent` reste
  l'encre portante, le geste devient `--tb-accent-vif` (« ne pas renommer le sûr, nommer
  le dangereux »). Contrat figé à 5 noms + 2 pour le sombre. Retournement du jaune
  généralisé au `kari` (1.92:1 → 8.36:1).
