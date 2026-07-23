<!-- Hallmark · design system · studied: yes · DNA-source: url (projetcollectif.ca)
     genre: playful · macrostructure: Ecosystem Index · theme: studied-DNA
     axes: papier clair (L>85) / sans humaniste / accent vert chromatique
     révisions : relecture Fable 2026-07-22 · passe UI/a11y 2026-07-22 -->

# Design — ADN « collectif »

Système de design verrouillé, extrait de `projetcollectif.ca`. Destiné à un
**skin du module `pages`** (à côté de `classic` et `faire_festival`), pas à
l'ensemble du dépôt. Amender volontairement — le fichier fait règle.

Implémentation de référence : [`collectif-blocks/`](collectif-blocks/) —
bibliothèque HTML/CSS autonome, 19 blocs, ouvrable dans un navigateur.

---

## 1. Le cœur du système : un thème par bloc

C'est la vraie découverte, et elle ne se voit pas sur une capture. **Le site
n'a pas un thème, il en a douze — et le thème se pose bloc par bloc.**

```html
<section class="b-highlight" data-theme="sun">   <!-- aplat jaune -->
<a       class="c-tile"      data-theme="ink">   <!-- carte noire  -->
```

Chaque thème ne redéfinit que deux ou trois variables :

```css
[data-theme="sun"] { --theme-surface: #FFE32B;
                     --theme-surface-base: #FFF29E;
                     --theme-text-invert: #0B3F2E; }
```

Tout le reste du CSS est écrit contre `--theme-*`, **jamais contre une couleur
de la palette**. C'est ce qui permet à une même carte d'être crème sur la page
d'accueil, noire dans la grille d'actualités et jaune sur une fiche
initiative, sans une ligne de CSS supplémentaire.

Douze thèmes relevés dans leur bundle. Chaque initiative a le sien ; sa page
s'y repeint entièrement.

**Conséquence pour Lespass :** ce n'est pas la même chose qu'un skin. Le skin
choisit le *vocabulaire graphique* (`SiteConfiguration.skin`, global au site) ;
le thème choisit la *couleur d'un aplat* (par bloc). Les deux se composent.

## 2. System

- Genre · **playful** (chaleureux, arrondi, illustré — retenue éditoriale)
- Macrostructure · **Ecosystem Index** — plusieurs surfaces de découverte
  empilées. Pas de tunnel marketing.
- Thème · **studied-DNA** (source : projetcollectif.ca)
- Axes · papier clair (L > 85 %) / sans humaniste / accent vert chromatique

### Archétypes

| Zone | Archétype | Réglages |
|---|---|---|
| Hero accueil | **H2 Split diptyque** | ratio 6/6 · droite = illustration · séparateur = espace négatif · carte actus en surimpression |
| Hero rubrique | H2 + fil d'Ariane | marque ronde + titre + surtitre mono **sous** le titre + lede + une action |
| Nav | **N5 Floating pill** | pilule blanche flottante, alignée à droite, wordmark à gauche |
| Section phare | **F2 Sticky scroll stack** | volet gauche = liste (active en clair, inactives en gris) |
| Liste | **F6 Product card grid** | cartes pleine largeur, eyebrow mono + titre + lede + lien fléché |
| Actualités | Mosaïque | spans irréguliers, **un thème par tuile** |
| Adhésion | **Ft7 Newsletter first** | deux cartes, formulaire à droite |
| Footer | **Ft3 Index** | wordmark + 3 colonnes, puis bandeau partenaires pleine largeur |

### Traitement de l'illustration — règle non négociable

**Fond uni, illustration détourée.** L'aplat de page est une couleur pleine,
sans dégradé ; l'illustration flotte dessus, **sans cadre, sans panneau, sans
coins arrondis**. Elle est massive et **déborde sous la ligne de flottaison**
plutôt que de rentrer dans une colonne de grille.

C'est ce qui donne au site son air dessiné plutôt que son air de gabarit. Une
illustration posée dans une boîte à coins arrondis avec un fond dégradé produit
exactement l'inverse — l'aplat redevient une carte, et la page redevient un
template.

Le cadre existe, mais c'est une **variante** : réservé aux dessins au trait sur
fond blanc, qui ont besoin d'une limite (fiches initiative).

**Autre détail du fold** : le bouton d'action se pose **sur la dernière ligne
du titre**, dans le flux du texte — pas sur une rangée à lui.

## 3. Provenance

- Source · `https://projetcollectif.ca/` — mode **URL + rendu réel**,
  extrait le 2026-07-22.
- Attestation · le mainteneur déclare **détenir les droits sur le site source**.
- Fiabilité :
  - **Couleurs : exactes** (custom properties du bundle `app-HzdJDyGR.css`).
    Conversions OKLCH revérifiées par calcul.
  - **Polices : exactes** (déclarations `@font-face`, woff2 auto-hébergés).
  - **Dimensions : exactes, rebasées.** La source pose `html{font-size:10px}` :
    tous ses `rem` valent 10 px. Les valeurs ci-dessous sont dans cette base.
  - **Rythme : observé** (rendu réel en 1440 px et 360 px, pas seulement le
    HTML — le HTML servi est une coquille SPA vide).
  - **Mouvement : choix du skin, pas extraction.** La source n'a ni courbe
    nommée ni `prefers-reduced-motion` (voir §8).
- Stack de la source · Craft CMS headless + front Vue/Vite (boilerplate
  « Arepa », agence Mambo Mambo) + Umami auto-hébergé. **Pas WordPress.**
  La source a elle aussi un constructeur de pages par blocs.

## 4. Tokens

Base : `html { font-size: 62.5% }` → **1 rem = 10 px**, et la préférence de
taille de police de l'utilisateur reste respectée (ce que `font-size: 10px`
casserait). Source de vérité : [`collectif-blocks/tokens.css`](collectif-blocks/tokens.css).

```css
:root {
  /* Palette — l'encre n'est jamais noire : vert forêt */
  --color-forest:      #0B3F2E;  /* oklch(32.9% 0.061 166) encre           */
  --color-forest-mid:  #3C6558;  /* oklch(47.2% 0.051 172) encre secondaire */
  --color-sage:        #6D8C82;  /* oklch(61.3% 0.038 173) UI seulement    */
  --color-sage-light:  #9DB2AB;  /* bordures                                */

  --color-karry-200:   #FFF6EC;  /* oklch(97.7% 0.016 71)  fond de page    */
  --color-karry-300:   #FFF1E2;  /* oklch(96.5% 0.025 69)                  */
  --color-karry-400:   #FFEDD9;  /* oklch(95.5% 0.033 70)                  */
  --color-karry-500:   #FFE8CF;  /* oklch(94.3% 0.042 70)  aplat crème     */
  --color-sisal:       #DBD2C1;  /* oklch(86.6% 0.025 83)  greige          */
  --color-bone:        #F1EDE6;  /* oklch(94.7% 0.010 82)  filet           */

  --color-emerald:     #59C280;  /* oklch(73.5% 0.137 154)                 */
  --color-chetwode:    #B2C4F6;  /* oklch(82.4% 0.073 269) pervenche       */

  /* Indirection — les blocs ne référencent QUE ce niveau */
  --theme-surface / --theme-surface-base / --theme-surface-light
  --theme-surface-primary / --theme-surface-invert / --theme-surface-accent
  --theme-text-primary / --theme-text-secondary / --theme-text-tertiary
  --theme-text-invert / --theme-border-primary / --theme-border-secondary

  /* Typographie — deux familles, licences distinctes */
  --ff-heading: "Work Sans", system-ui, sans-serif;   /* SIL OFL 1.1  */
  --ff-body:    "Work Sans", system-ui, sans-serif;
  --ff-mono:    "Roboto Mono", ui-monospace, monospace; /* Apache 2.0 */

  /* Échelle de type — fluide, calée sur les paliers réels */
  --text-d1: 40px @1024 → 80px @1440   /* lh .95  ls -1.2px  poids 600 */
  --text-h1: 30 → 60                    /* lh .95  ls -0.9px            */
  --text-h2: 30 → 40                    /* lh .95  ls -0.6px            */
  --text-h3: 30                         --text-h4: 20 → 24
  --text-h5: 18                         --text-h6: 16
  --text-p1: 20 @420 → 24 @1440 (lh 1.2)   --text-p2: 18
  --text-p3: 16                         --text-p4: 14
  --text-c1: 14  mono 500 CAPITALES  ls −0.28px
  --text-c2: 12  mono 500 CAPITALES  ls −0.24px

  /* Espacement — pas de 5 px (ce n'est PAS une échelle 4pt) */
  2xs 5 · xs 10 · sm 15 · md 20→25 · lg 25→30 · xl 30→60 · 2xl 60→120

  /* Grille : 4 → 6 → 8 → 12 colonnes · gouttière 20 → 30 px
     Conteneur max 1610 px · marge 20 → 30 px */

  /* Rayons */
  --radius-sm: 5px · --radius-md: 10px · --radius-lg: 15→20px
  --radius-pill: 999rem   /* tout ce qui se clique */

  --shadow-card: 0 4px 12px rgb(0 0 0 / .08);
}
```

**Paliers** : 420 / 576 / 768 / 1024 / 1440. Les majeurs sont 768 et 1024.

### Thèmes

| Thème | Aplat | Texte | Contraste |
|---|---|---|---|
| `karry` | `#FFE8CF` | encre | 10,03:1 |
| `sisal` | `#DBD2C1` | encre | 7,93:1 |
| `emerald` | `#59C280` | encre | 5,36:1 |
| `sage` | `#9DB2AB` | encre | 5,32:1 |
| `chetwode` | `#B2C4F6` | encre | 6,87:1 |
| `sun` | `#FFE32B` | encre | 9,22:1 |
| `crimson` | `#E50914` | blanc | 4,79:1 |
| `ink` | `#000000` | blanc | 21:1 |
| `flame` | `#FF5C30` | encre | **3,87:1 — grands titres et badges uniquement** |

`flame` est le seul thème sous le seuil AA pour du texte courant. La source y
pose du blanc (3,08:1) : c'est pire. On garde l'orange comme **surface
d'affichage**, avec l'encre forêt, et on interdit le texte de labeur dessus.

## 5. Rôles typographiques

- **Display** · Work Sans 600, interligne 0,95, gauche-biaisé. Le titre de
  fold est une phrase complète, pas un slogan.
- **Body** · Work Sans 400. Même famille : le contraste ne vient pas d'un
  second caractère de labeur.
- **Label** · Roboto Mono **500**, 12 ou 14 px, CAPITALES, **tracking négatif**
  (−0,24 / −0,28 px). Réservé aux surtitres, badges et étiquettes de pastilles.
  C'est le seul contraste typographique du système — ne pas l'étendre au corps
  de texte.

**Écart assumé vis-à-vis de la source** : leur interligne de texte courant est
à 1,2. On monte à **1,5** pour le corps de texte (les titres restent à 0,95).
En dessous de 1,5 la lecture longue fatigue, et rien dans l'identité ne repose
sur un interligne serré du corps.

## 6. CTA voice

- **Primaire** · pilule (`--radius-pill`), fond blanc, bordure `1px`, libellé
  en **Work Sans casse mixte** (jamais en mono capitales), pastille circulaire
  de 36 px à droite. Padding asymétrique `9px 11.41px 9px 24.42px`.
  **Au survol tout s'inverse** : fond → vert forêt, texte → blanc, pastille →
  blanc à texte vert. C'est la micro-signature du système.
- **Secondaire** · lien fléché circulaire (cercle fin + `→`), **44 × 44 px
  minimum** — la source est à 32 px, sous le seuil tactile.
- **Pastilles thématiques** · pilules pleines en accent alterné, libellé mono
  capitales.

## 7. Iconographie

**SVG uniquement.** Ni emoji, ni glyphe typographique (`✳ ◉ ▤`) : le rendu
dépend de la police installée, la couleur n'est pas pilotable par token, et
rien ne garantit la présence du caractère. Un seul jeu d'icônes, une seule
épaisseur de trait (1,5 px), un seul style (contour), alignées sur la ligne de
base du texte.

## 8. Motion stance

- Transitions **scopées à la propriété** (`color`, `background-color`,
  `transform`, `opacity`), 200–300 ms. Jamais `transition: all`.
- Une seule courbe : `--ease-out: cubic-bezier(0.16, 1, 0.3, 1)`.
  **La source n'en a aucune** — elle utilise le `ease` du navigateur partout.
  C'est un choix du skin, pas une extraction.
- Un seul primitif de révélation : fade-up léger au scroll. **Pas de
  scroll-jacking** (voir §10, note 4).
- Repli `prefers-reduced-motion: reduce` · crossfade opacité ≤ 150 ms, et
  neutralisation des `position: sticky` et du `scroll-snap`.

## 9. Signature

Le « ll » du logotype est un **ruban manuscrit** qui ressort en séparateur
décoratif pleine largeur entre les sections, en crème saturé sur crème clair.
Un seul geste graphique, réutilisé deux ou trois fois par page. C'est ce qui
empêche le site de ressembler à un gabarit — le reproduire par un motif propre
au lieu, jamais par un ornement générique.

## 10. Notes — à NE PAS reprendre de la source

1. **SPA sans rendu serveur.** Le HTML servi ne contient aucun contenu ; tout
   dépend du JS. Lespass rend côté serveur — c'est un avantage, pas un retard.
2. **Aucun `<h1>` sur la page d'accueil.** La chaîne `"h1"` n'apparaît pas une
   seule fois dans leurs 838 Ko de bundle Vue ; le titre de fold est un SVG.
   Accessibilité et référencement sacrifiés à un effet.
3. **Toutes les transitions en `ease` navigateur**, aucune courbe nommée, et
   **zéro `prefers-reduced-motion`** dans 129 Ko de CSS.
4. **Panneau épinglé de ~3600 px** (scroll-jacking sur les initiatives
   phares) : hostile au clavier et au défilement natif. Préférer une liste ou
   un carrousel accessible.
5. **Révélation au scroll bloquante.** Leur `StaggerReveal` garde le contenu
   en `opacity: 0` tant qu'on n'a pas défilé : sans JS, la page est vide. La
   révélation doit être un ajout, jamais une condition d'affichage.
6. **Contraste du texte secondaire.** `#6D8C82` sur crème = **3,43:1**, sous
   AA. Sur blanc **3,67:1**, sur crème saturé **3,09:1**. Utiliser
   `#3C6558` (**6,15:1**) pour tout texte lisible ; réserver `#6D8C82` aux
   éléments d'interface non textuels.
7. **Anneau de focus invisible.** Ils utilisent `#9DB2AB` : **2,09:1** sur
   crème, très en dessous des 3:1 exigés pour un indicateur de focus. Prendre
   l'encre forêt (**11,13:1**), 3 px.
8. **Cibles tactiles sous le seuil.** Leurs liens fléchés circulaires font
   32 px. Minimum 44 × 44 px.

Contrastes de référence : encre/papier **11,13:1** · encre/accent **5,36:1** ·
blanc/vert forêt **11,9:1**.

## 11. Réalisation dans le module `pages`

Correspondance entre les blocs de la source et le catalogue existant
(`pages/blocs_catalogue.py` : 7 types, 15 affichages).

**Déjà couvert** : `BlockText` → `TEXTE` · `BlockQuote` → `SECTION/CITATION` ·
`BlockCardsList` → `SECTION/CARTE` · `BlockCta*` → `SECTION/APPEL_ACTION` ·
`BlockGallery` → `IMAGES/GRILLE` · `BlockImage` → `IMAGES/PLEINE_LARGEUR` ·
`BlockAccordions` → `FAQ` · `BlockPushInitiatives` → `LISTE` source
`SOUS_PAGES` · `BlockArticles` → `LISTE` source `EVENEMENTS`.

**Ce que Lespass a en plus** : le bloc `LIEU` (carte GPS + infos pratiques) et
`INTEGRATION` avec ses trois pipelines de sécurité distincts. La source n'a
aucun équivalent.

**Ce que Lespass fait mieux** : la source a **quatre** composants de CTA
(`BlockCta`, `BlockCtaLarge`, `BlockCtaSquare`, `BlockCtasGrid`) là où Lespass
a un type et un affichage. C'est exactement l'explosion de catalogue que la §9
de `pages/README.md` interdit.

**À ajouter :**

| Besoin | Nature | Détail |
|---|---|---|
| Thème par bloc | **Architectural** | Champ `theme` sur `Bloc` + tokens `--theme-*`. Le seul vrai chantier. |
| Programme / horaires | Nouveau **type** | C'est une intention (« je publie un déroulé »), pas une forme. |
| Trombinoscope | Type **ou** affichage de `LISTE` | Selon que la donnée vient d'un modèle ou de sous-pages. |
| Carrousel | **Affichage** de `LISTE` | `CARROUSEL` |
| Mosaïque | **Affichage** de `LISTE` | `MOSAIQUE` |
| Fil d'actu sur le hero | **Affichage** de `LISTE` | `CARTE_HERO` — même requête, autre forme |
| Deux colonnes titre/texte | **Affichage** de `SECTION` | `DEUX_COLONNES` (comme `TEXTE_IMAGE_*`, sans image) |
| Titre seul | **Affichage** de `SECTION` | `TITRE_SEUL` |

Rappel de procédure (`pages/README.md` §9) : un nouvel affichage s'ajoute à
`AFFICHAGES_PAR_TYPE` **et** à `CHAMPS_PAR_AFFICHAGE`, puis on crée le
gabarit. Cinq tests de `tests/pytest/test_pages_api.py` vérifient la cohérence.

**L'espaceur de la source est volontairement écarté** : le rythme vertical
doit venir du gabarit, pas d'un bloc que l'auteur insère à la main.

## 12. Les trois exigences du mainteneur

1. **Hero pleine page** — `min-height: 100dvh` sur le hero, **désactivé sous
   768 px** (en paysage mobile il ne reste ~380 px : titre + carte actus +
   illustration n'y tiennent pas). L'illustration se retire sous 768 px.
2. **Menu à droite avec arrondis** — c'est le N5 : barre horizontale, liens
   groupés dans une pilule blanche alignée à droite, `--radius-pill`. Se
   replie en bouton sous 1024 px, avec panneau déplié en dessous. *Si un rail
   vertical est voulu à la place, c'est hors ADN — à trancher.*
3. **Bloc « derniers évènements » sur le hero** — affichage `CARTE_HERO` du
   type `LISTE` (source `EVENEMENTS`), **pas un nouveau type**. Une à trois
   entrées, vignette + surtitre + date + titre. Le chevauchement sur la
   bannière est une affaire de gabarit : le bloc `LISTE` posé juste après une
   `BANNIERE` est remonté par le skin. À partir de 1024 px seulement.

## 13. Exports

Source de vérité : [`collectif-blocks/tokens.css`](collectif-blocks/tokens.css).
Pour un export Tailwind v4 `@theme`, DTCG `tokens.json` ou variables
shadcn/ui, demander « étends design-collectif.md avec les exports Tailwind ».
