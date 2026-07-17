<!-- Hallmark · design-system: skin « miete » · studied: yes · DNA-source: url
     source: https://web.archive.org/web/20250321051225/https://lamiete.com/
     axes: light / humanist-sans (Luciole) / warm (vermillon ~37°)
     pre-emit critique: P5 H4 E4 S5 R5 V4
-->

# Design — skin `miete` (Lespass / TiBillet)

Système de design **verrouillé, à portée d'un seul skin**. Il régit
`pages/templates/pages/miete/` et rien d'autre.
/ Locked design system, scoped to ONE skin. Governs `pages/templates/pages/miete/` only.

> **Ce fichier vit DANS le skin, et pas à la racine du projet. C'est délibéré.**
> Hallmark lit un `design.md` racine comme le système de TOUT le projet, et
> inverse alors sa règle de diversification : toutes les pages doivent partager
> ce système. Poser l'ADN de la MIETE à la racine imposerait le vermillon d'un
> tiers-lieu de Villeurbanne au kiosk (« Signalétique », ambre ~68°), à laboutik
> et au socle `classic`. Un skin est une variante, pas la maison.
> Ici, le système voyage avec le skin : qui copie `pages/miete/` emporte sa
> règle avec lui, et qui ne le copie pas n'en hérite pas.
> / Lives INSIDE the skin, not at project root: a root design.md would hijack the
> whole project's system, including the kiosk's amber theme. Here the system
> travels with the skin.

## System

- Genre · **playful** (tiers-lieu associatif, accueil, communauté)
- Macrostructure · **Long Document** (18 sections empilées dans la source)
- Nav · **bulles** (bespoke) — voir ci-dessous. La source était un N11 mega-menu
  (14 entrées + menu secondaire + recherche) ; on ne le reprend pas.
- Footer · **Ft3 index en colonnes** (Contact · Actualités · Accessibilité · Mentions légales)
- Theme · **studied-DNA « MIETE »** — cousin catalogue : **Hum**
- Axes · light / humanist-sans (Luciole) / warm (vermillon ~37°)

**Le geste signature : le menu est fait de bulles.** La MIETE dessine des bulles
de pensée (nuage plein + contour noir volontairement désaligné + bulle-queue +
trois pétales + deux pastilles). Le skin les vectorise et en fait ses entrées de
menu. La grammaire, relevée sur les originaux, vit dans `partials/bulle.html`.

**Ce qui change par rapport aux originaux, et c'est tout l'enjeu :** les `.png`
du lieu ont leur libellé **cuit dans le pixel**. Un lecteur d'écran ne le voit
pas, et le bouton « Augmenter le texte » du lieu ne le grossit pas. Ici le
dessin est décoratif (`aria-hidden`) et le libellé est du **vrai texte HTML**,
traduisible, dimensionné en `em` — quand le texte grossit, la bulle grossit avec.
/ The venue's own PNGs bake their label into the pixels: invisible to a screen
reader, unscalable by their own text-size tool. Here the drawing is decorative
and the label is real HTML text sized in `em`.

**Le parti pris central : une seule famille, choisie pour la lisibilité.**
La source déclare Luciole sur *tous* les rôles typographiques. Ce n'est pas un
pairing display+body, c'est le cas « la mono-fonte EST le design ». Luciole est
dessinée pour la basse vision : zéro barre, `a` à empattement, 6 et 9
dissymétriques. On ne la remplace pas.
/ Single family by design — Luciole is drawn for low vision. Do not substitute.

## Provenance

- **Source** · `https://web.archive.org/web/20250321051225/https://lamiete.com/`
  (WordPress + Elementor 3.28, thème `napoli-IN`, The Events Calendar)
- **Mode** · URL · **Extrait le** · 2026-07-16
- **Attestation** · (a) site du lieu — La MIETE, *Maison de l'Initiative de
  l'Engagement, du Troc et de l'Échange*, tiers-lieu à Villeurbanne.
- **Confiance** · Les jetons de couleur et les fontes sont **exacts** (lus dans
  le kit Elementor `post-3296.css`). Le **rythme est inconnu** — le HTML seul ne
  dit pas si la densité respire ou si elle est templatée. Une capture d'écran
  lèverait cet angle mort.
- **Décalage temporel** · page capturée le 2025-03-21, kit CSS le plus proche
  archivé le **2024-08-15**. Les jetons peuvent avoir bougé entre les deux.

## Tokens

```css
:root {
    /* --- Surfaces. Source : #ffffff dominant, #303030 en bandeau sombre. --- */
    --color-paper:        oklch(100% 0 0);          /* #ffffff — source        */
    --color-paper-2:      oklch(96.5% 0 90);        /* dérivé — surface douce  */
    --color-paper-dark:   oklch(30.9% 0 90);        /* #303030 — bandeau       */
    --color-rule:         oklch(90.7% 0 90);        /* #e0e0e0 — filets        */

    /* --- Encre. Les deux passent AA largement. --- */
    --color-ink:          oklch(44.6% 0 90);        /* #545454 — 7,57:1        */
    --color-ink-strong:   oklch(30.9% 0 90);        /* #303030 — 13,20:1       */

    /* --- Accent. LIRE « Notes » AVANT d'utiliser --color-accent sur du texte. */
    --color-accent:       oklch(63.7% 0.186 37);    /* #E5562B — la marque     */
    --color-accent-ink:   oklch(0% 0 0);            /* NOIR dessus — 5,70:1    */
    --color-accent-text:  oklch(53.4% 0.165 36.6);  /* #B83E18 — 5,61:1/blanc  */
    --color-focus:        oklch(53.4% 0.165 36.6);  /* #B83E18 — 5,61:1/blanc  */

    /* --- Palette des bulles, relevée sur les DESSINS du lieu (les .png), pas  */
    /*     sur son CSS, qui ne la déclare nulle part. Le chiffre est le         */
    /*     contraste avec l'encre noire : toutes passent AA.                     */
    --bulle-jaune:        oklch(88.4% 0.126 85);    /* #FFD271 — 14,71:1       */
    --bulle-vert:         oklch(74.1% 0.142 133);   /* #86BE5C —  9,53:1       */
    --bulle-cyan:         oklch(76.7% 0.089 210);   /* #69C3D3 — 10,35:1       */
    --bulle-rose:         oklch(65.0% 0.203 357);   /* #E94A90 —  5,85:1       */
    --bulle-vermillon:    oklch(63.7% 0.186 37);    /* #E5562B —  5,70:1       */

    /* --- Typographie. Luciole est DEJA dans le projet :                      */
    /*     BaseBillet/static/commun/font/luciole/ (4 woff2, CC BY 4.0).        */
    /*     Le skin n'embarque AUCUNE fonte. Pas de pages/static/miete/fonts/.  */
    --font-display: "Luciole", system-ui, sans-serif;   /* 600                 */
    --font-body:    "Luciole", system-ui, sans-serif;   /* 400                 */
    /* Pas de mono dans l'ADN. Roboto 500 n'occupe qu'un rôle accent résiduel  */
    /* dans la source — non repris.                                            */

    /* Échelle typo — la source tient en TROIS tailles : 14 / 18 / 24 px.      */
    /* Le 14px du corps est relevé à 16px : voir « Notes ».                    */
    --text-body:    1rem;      /* 16px — dévié de la source (14px)             */
    --text-lead:    1.125rem;  /* 18px — source                                */
    --text-display: 1.5rem;    /* 24px — source                                */

    /* Espacement 4pt nommé, --space-3xs … --space-4xl : voir tokens.css.      */

    --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
    --dur-fast: 180ms;  --dur-base: 240ms;

    /* La source n'a qu'UN rayon, 3px. La MIETE est quasi-carrée.              */
    --radius-card:  3px;
    --radius-input: 3px;
    --radius-pill:  3px;
}
```

## CTA voice

**La règle vient des bulles du lieu : encre NOIRE sur aplat coloré, jamais du blanc.**
Le vermillon porte 3,62:1 face au blanc (échec AA) mais 5,70:1 face au noir. Les
dessins de la MIETE ont toujours mis du noir dedans ; ce sont ses boutons CSS
(label blanc) qui échouaient. On suit les dessins, pas le CSS.
/ Black ink on colour fills. The venue's own artwork already got this right; its
CSS buttons did not.

- **Primary** · fond `--color-accent` · label `--color-accent-ink` (noir) ·
  rayon 3px · bordure 2px pleine (la source borde ses boutons à 2px).
- **Secondary** · contour + label `--color-accent-text` sur papier · même rayon.
- **Texte courant** en accent → `--color-accent-text` obligatoire : le vermillon
  de marque ne passe pas sur le papier blanc.

## Motion stance

- **Motion-cut.** La source n'embarque aucune bibliothèque de motion — juste les
  classes `e-animation` d'Elementor (un « pop » au survol) qu'on ne reprend pas.
- Repli `prefers-reduced-motion` · fondu d'opacité ≤ 150 ms.

## Notes — ce qu'on ne reprend PAS

1. **Le label blanc sur l'accent est un défaut de la source, pas une signature.**
   Le kit déclare `color:#FFFFFF` sur les boutons, posés sur le vermillon :
   **3,62:1**, sous le seuil AA de 4,5:1. Sur un site dont l'identité est
   l'accessibilité, c'est une contradiction.
   **La correction ne vient pas de nous, elle vient du lieu lui-même :** ses
   bulles dessinées mettent toujours du **noir** sur la couleur, et le noir sur
   ce même vermillon donne 5,70:1. On généralise donc la règle des dessins à
   tout le skin, et on abandonne celle des boutons. Reste `--color-accent-text`
   (`#B83E18`, 5,61:1) pour l'accent **en texte sur papier blanc**, où même le
   noir ne peut rien pour la teinte de marque.
2. **Deux vermillons pour un.** La source déclare `#E6582B` (kit) *et* `#E5562A`
   (bordure de bouton). Incohérence d'origine. On n'en garde qu'un.
3. **Le corps à 14px.** La source pose 14px, compensé par le bouton « Augmenter
   le texte ». Un plancher à 16px vaut mieux qu'une rustine. Relevé.
4. **`transition: all`** — 20 occurrences dans les CSS de la source. Interdit ici.
5. **Le CSS d'Elementor** est machine-généré et scopé par ID de widget
   (`.elementor-element-a1b2c3`). Rien à en sauver : on prend l'ADN, pas
   l'implémentation.
6. **La barre d'outils d'accessibilité n'est pas un skin.** Augmenter/Diminuer le
   texte, Niveaux de gris, Contraste négatif, Liens soulignés, Police lisible,
   Réinitialiser — ça touche TOUTES les pages et demande des préférences
   persistées. Sa place serait `shell.html`, c'est un chantier distinct, et il
   n'est pas tranché.

## Attribution

Luciole © Laurent Bourcellier & Jonathan Perez — **CC BY 4.0**.
Licence déjà présente dans le repo : `BaseBillet/static/polices/Luciole/Read Me.txt`.
L'attribution doit survivre à toute redistribution du skin.

## Exports

`tokens.css` fera foi une fois le skin construit. Pour des exports Tailwind v4
`@theme`, DTCG `tokens.json` ou variables shadcn/ui, demander
*« extend design.md with Tailwind exports »*.
