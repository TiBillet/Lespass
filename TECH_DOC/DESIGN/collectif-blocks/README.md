# Bibliothèque de blocs « collectif » — étude HTML/CSS

Reproduction autonome, en HTML/CSS pur, du vocabulaire de blocs de
`projetcollectif.ca`. **Aucune dépendance à TiBillet** : trois fichiers, zéro
build, zéro JavaScript obligatoire.

| Fichier | Rôle |
|---|---|
| `tokens.css` | Couleurs, thèmes, typographie, espacement, rayons, mouvement |
| `blocks.css` | Le chrome (nav, pied, ruban) et les 19 blocs |
| `index.html` | Page de démonstration : chaque bloc rendu, étiqueté par son code |

**Pour voir :**

```bash
cd TECH_DOC/DESIGN/collectif-blocks && python3 -m http.server 8899
# puis http://localhost:8899/index.html
```

Un simple double-clic sur `index.html` marche aussi (le seul appel réseau est
l'import Google Fonts ; sans réseau, la page retombe sur les polices système).

Vérifié au rendu à **360 / 768 / 1440 px** : zéro débordement horizontal, zéro
commande sous 44 × 44 px, la nav se replie en bouton sous 1024 px.

---

## 1. Ce que la source fait vraiment

Le point qu'on ne voit pas en regardant une capture : **le site n'a pas un
thème, il en a douze**, et le thème se pose **par bloc**.

```html
<section class="b-highlight" data-theme="sun">   <!-- aplat jaune -->
<a     class="c-tile"       data-theme="ink">   <!-- carte noire -->
```

Chaque thème ne redéfinit que deux ou trois variables :

```css
[data-theme="sun"] { --theme-surface: #FFE32B;
                     --theme-surface-base: #FFF29E;
                     --theme-text-invert: #0B3F2E; }
```

Tout le reste du système est écrit contre `--theme-*`, jamais contre une
couleur. C'est ce qui permet à une même carte d'être crème sur la page
d'accueil, noire dans une grille d'actualités et jaune sur une fiche
initiative — **sans une ligne de CSS supplémentaire**.

Douze thèmes relevés dans leur bundle : `karry` (crème), `sisal` (greige),
`emerald`, `bottle-green` (sauge), `chetwode` (pervenche), `en-commun` (noir),
`jdso` (#FF5C30), `portes-ouvertes` (#E50914), `maison-des-demarches`
(#FFE32B), plus trois autres. Chaque initiative a sa couleur ; la page de
l'initiative s'y repeint entièrement.

Reproduit ici sous des noms neutres : `karry` · `sisal` · `emerald` · `sage` ·
`chetwode` · `sun` · `flame` · `crimson` · `ink`.

---

## 2. Le catalogue reproduit

Codes tels qu'étiquetés dans `index.html`.

| Code | Bloc | Nom chez eux | Variantes |
|---|---|---|---|
| B01 | Hero | `HeroBase` | accueil (titre + illustration) · rubrique (fil d'Ariane + marque + surtitre) · pleine hauteur |
| B02 | Fil d'actualités posé sur le hero | — (composé) | 1 à 3 entrées |
| B03 | Titre seul | `BlockHeading`, `BlockHeadingWithList` | aligné · centré |
| B04 | Texte riche | `BlockText` | — |
| B05 | Deux colonnes titre/contenu | `BlockSideBySide` | normal · inversé |
| B06 | Panneau de mises en avant | `BlockHighlightGrid` | 2 à 4 colonnes, thémable |
| B07 | Liste de cartes | `BlockCardsList` | petite · moyenne · large |
| B08 | Mosaïque | grille de nouvelles | spans irréguliers, thème par tuile |
| B09 | Appel à l'action | `BlockCta`, `BlockCtaLarge`, `BlockCtaSquare`, `BlockCtasGrid` | panneau · grille de cartes-actions |
| B10 | Citation | `BlockQuote` | — |
| B11 | Galerie | `BlockGallery`, `BlockGalleryCard` | grille · carte |
| B12 | Accordéon | `BlockAccordions` | `<details>` natif |
| B13 | Programme | `BlockSchedules` | heure / contenu / durée |
| B14 | Trombinoscope | `BlockPushTeam` | — |
| B15 | Phrase-choc épinglée | `BlockStickyCatchphrase` | `position: sticky` |
| B16 | Carrousel | `BlockContentCarousel`, `BlockStoriesCarousel` | `scroll-snap` natif |
| B17 | Panneau d'informations | `MetadataPanel` | collé au défilement |
| B18 | Image | `BlockImage` | encadrée · pleine largeur |
| B19 | Espaceur | `BlockSpacer` | — |

Plus, hors blocs : nav pilule, pied + bandeau partenaires, ruban décoratif,
aplat pleine largeur (`.is-bleed`).

**Ce qui n'est pas reproduit, volontairement** : leurs illustrations et leurs
photos. Les aplats géométriques `.c-art` sont construits en CSS et tiennent la
place. Le ruban `.c-ribbon` est un tracé de substitution — le vrai est un
motif dessiné à la main, à remplacer par celui du lieu.

---

## 3. Corrections apportées à la source

Reproduire n'est pas recopier. Neuf écarts assumés :

1. **Base rem.** La source pose `html{font-size:10px}`, ce qui écrase la
   préférence de taille de police de l'utilisateur. On utilise `62.5%` :
   mêmes valeurs `rem`, préférence respectée.
2. **`prefers-reduced-motion`.** Absent des 129 Ko de leur CSS. Ajouté ici,
   avec neutralisation des `sticky` et du `scroll-snap`.
3. **Contraste du texte secondaire.** Leur gris-sauge `#6D8C82` sur crème
   plafonne à 3,43:1 — sous le seuil AA. `--theme-text-secondary` pointe donc
   sur `#3C6558` (6,15:1) ; `#6D8C82` est relégué à l'UI non textuelle.
4. **Titre en vrai texte.** Leur `<h1>` de page d'accueil est un SVG — la
   chaîne `"h1"` n'apparaît pas une seule fois dans leurs 838 Ko de JS. Ici,
   les titres sont des `<h1>`/`<h2>`.
5. **Anneau de focus visible.** Ils utilisent `#9DB2AB` : **2,09:1** sur
   crème, très en dessous des 3:1 exigés. Ici : encre forêt, 3 px, **11,13:1**.
6. **Cibles tactiles.** Leurs liens fléchés font 32 px. Ici, tout ce qui se
   clique fait **44 × 44 px** minimum.
7. **Thème `flame` requalifié.** Leur orange `#FF5C30` porte du blanc :
   **3,08:1**. On garde la couleur comme *surface d'affichage* (grands titres,
   badges) avec l'encre forêt (3,87:1) et on interdit le texte courant dessus.
8. **Interligne du corps de texte.** La source est à 1,2. On monte à **1,5** :
   en dessous, la lecture longue fatigue, et rien dans l'identité ne repose
   sur un corps de texte serré. Les titres restent à 0,95.
9. **Icônes en SVG.** Un sprite `<symbol>` + `<use>`, trait 1,5 px, style
   contour. Jamais de glyphe typographique ni d'emoji : le rendu dépendrait de
   la police installée et la couleur ne serait pas pilotable par token.

Détails de finition ajoutés : `text-wrap: pretty` sur le display et `balance`
sur les titres de section (jamais l'inverse — `balance` sur un titre de fold
donne cinq lignes courtes au lieu de quatre pleines), `tabular-nums` sur les
dates, heures et compteurs, `min()` sur les pistes de grille en `rem` pour
qu'elles ne figent jamais plus large que le viewport.

Conservé tel quel : la pilule de nav, l'inversion du bouton au survol (fond
qui bascule en vert forêt, pastille qui s'inverse), le tracking **négatif**
des étiquettes mono (−0,28 px / −0,24 px, poids 500), les rayons généreux,
l'ombre presque invisible.

---

## 4. Comparaison avec `pages/blocs_catalogue.py`

L'existant TiBillet : **7 types, 15 affichages**. Le collectif : **19
composants de bloc**.

### Ce que TiBillet couvre déjà

| Bloc collectif | Équivalent TiBillet |
|---|---|
| `BlockText` | `TEXTE` |
| `BlockQuote` | `SECTION` / `CITATION` |
| `BlockCardsList` | `SECTION` / `CARTE` (le regroupement en grille est automatique) |
| `BlockCta*` (leurs **quatre** composants) | `SECTION` / `APPEL_ACTION` — **un seul** |
| `BlockGallery`, `BlockGalleryCard` | `IMAGES` / `GRILLE` |
| `BlockImage` | `IMAGES` / `PLEINE_LARGEUR`, `VIGNETTE_TITRE` |
| `BlockAccordions` | `FAQ` |
| `BlockPushInitiatives` | `LISTE` source `SOUS_PAGES` |
| `BlockArticles` | `LISTE` source `EVENEMENTS` |
| `BlockHighlightGrid` | `SECTION` / `MEDIA_ET_CARTES` (approchant : sous-cartes en données texte) |

Sur ce périmètre, **la règle TiBillet est meilleure que la leur**. Ils ont
quatre composants de CTA (`Cta`, `CtaLarge`, `CtaSquare`, `CtasGrid`) là où
TiBillet a un type et un affichage. C'est exactement l'explosion du catalogue
que la §9 de `pages/README.md` interdit — et la preuve, en vrai, que la règle
est bonne.

### Ce que TiBillet a et qu'eux n'ont pas

- **`LIEU`** — carte GPS + infos pratiques dans un seul bloc.
- **`INTEGRATION`** — et surtout ses trois pipelines de sécurité distincts
  (whitelist vidéo / whitelist ROOT + sandbox / script Ghost). Le collectif
  n'a pas d'équivalent.

### Les manques réels

| Manque | Nature | Coût |
|---|---|---|
| **Thème par bloc** | Architectural | Un champ `theme` sur `Bloc` + les tokens `--theme-*`. C'est le seul vrai chantier. |
| Programme / horaires (`B13`) | Nouveau **type** | Légitime : c'est une intention (« je publie un déroulé »), pas une forme. |
| Trombinoscope (`B14`) | Nouveau **type** ou affichage de `LISTE` | À trancher : si la donnée vient d'un modèle Membre, c'est une `LISTE`. |
| Carrousel (`B16`) | **Affichage** de `LISTE` | `CARROUSEL` à côté du rendu par défaut. |
| Mosaïque (`B08`) | **Affichage** de `LISTE` | `MOSAIQUE`. |
| Fil d'actu sur le hero (`B02`) | **Affichage** de `LISTE` | `CARTE_HERO`. Pas un type — c'est la même requête, une autre forme. |
| Deux colonnes titre/texte (`B05`) | **Affichage** de `SECTION` | `DEUX_COLONNES` : comme `TEXTE_IMAGE_*` mais sans image. |
| Titre seul (`B03`) | **Affichage** de `SECTION` | `TITRE_SEUL`. |
| Espaceur (`B19`) | — | Probablement à ne pas faire : le rythme doit venir du gabarit, pas de l'auteur. |

Bilan : **six affichages, un ou deux types, et un chantier de fond** (le thème
par bloc). Le reste est déjà là.

### La différence qui compte

TiBillet a **un skin par site** (`SiteConfiguration.skin`, appliqué
globalement). Le collectif a **un thème par bloc**. Ce ne sont pas deux
implémentations de la même idée : le skin choisit *le vocabulaire graphique*,
le thème choisit *la couleur d'un aplat*. Les deux peuvent coexister — un skin
`collectif` qui expose neuf thèmes posables bloc par bloc.

C'est ce que fait la démo : `blocks.css` est le skin, `data-theme` est le
réglage laissé à la personne qui écrit la page.
