<!-- Hallmark · studied: yes · DNA-source: url
     source-url: https://lafilature-villeurbanne.fr/ (WordPress 6.9.4 + Divi)
     macrostructure: Ecosystem Index · genre: playful · theme: studied-DNA
     axes: papier clair (96.3%) / display-condensed / chromatique-multi (CMJ)
     papier oklch(96.3% 0.071 98.1) · accents #1C9DD8 · #E51B74 · #F6E921
     display: Bayon · body: Asap · rhythm: unknown (URL mode)
-->

# Design — La Filature (skin `la_filature`)

Système de design verrouillé, extrait du site historique du lieu. Les runs
Hallmark suivants lisent ce fichier en premier ; les pages s'y conforment.
La diversification s'inverse : les pages doivent **partager** ce système, pas
s'en distinguer. Amender volontairement — le fichier fait règle.

> **Portée.** Ce fichier décrit UN skin (`la_filature`), pas le repo Lespass.
> Il ne s'applique ni à `classic` ni à `faire_festival`. Voir
> [`CONTRAT-DE-SKIN.md`](../../../../TECH_DOC/SESSIONS/SKINS/CONTRAT-DE-SKIN.md)
> — un skin décrit à quoi ça ressemble, jamais ce que ça fait. Zéro code Python.
>
> **Ce dossier ne contient que 2 gabarits** (`shell.html`, `page.html`) : tout
> le reste retombe sur `classic` via le resolver `pages.services.gabarit_skin`
> et suit donc ses corrections futures. L'habillage est ENTIÈREMENT en CSS —
> c'est le parti pris du skin, pas un raccourci.

## System

- Genre · **playful** (tiers-lieu, communauté, palette vive, boutons pilule).
  Mobilier éditorial en second (filets sous titres, rythme de sections marqué).
- Macrostructure · **Ecosystem Index** (penchant Photographic) — la page fait
  *parcourir les facettes du lieu*, elle ne déclare pas. Chaque bloc est une
  facette (programmation, cantine, pavillon…) avec son propre CTA vers plus loin.
- Theme · **studied-DNA** (source : url). Cousin catalogue le plus proche :
  **Riso** — mais la Filature pousse le duo-ton riso en CMJ complet.
- Axes · papier clair (L 96.3 %) / display-condensed (Bayon, romain) /
  chromatique-multi (cyan-bleu primaire 235.6°, rotation magenta + jaune)

## Provenance

- **Source** · `https://lafilature-villeurbanne.fr/` — mode URL (HTML + les 2
  seuls CSS same-origin du site), extrait le **2026-07-16**.
- **Attestation** · cas (a) — **site détenu par le client**. Lieu récupéré,
  migration de WordPress+Divi vers l'app `pages`. Ce n'est pas une référence
  externe : c'est un actif de marque qu'on rapatrie.
- **Confiance** · Tokens **exacts** (extraits du CSS source). Fonts **exactes**
  (déclarées via Google Fonts). Rythme **inconnu** — le HTML seul ne dit pas si
  la densité respire ou se répète. Une capture lèverait cet angle mort.

## Tokens

**La source de vérité est `pages/static/la_filature/css/la_filature.css`.** Ce
bloc en est le résumé ; en cas d'écart, c'est le CSS qui a raison.

Deux conventions se rencontrent ici, et il faut les distinguer :

- **Les jetons du socle** (`--tb-*`, `--skin-*`) — **on ne les nomme pas, on les
  consomme.** Contrat figé, propriétaire = l'agent socle. Voir
  [`CHANTIER-10-SOCLE-TOKENS.md`](../../../../TECH_DOC/SESSIONS/SKINS/CHANTIER-10-SOCLE-TOKENS.md).
- **Notre palette** (`--filature-*`) — préfixe **namespacé volontairement**.
  `faire_festival` utilise `--couleur-*` et `commun/css/vars.css` expose des
  `--kouler-*` : un `--couleur-cyan` nu finirait par se cogner à quelqu'un.

L'OKLCH sert à *dériver* les variantes encre, pas à remplacer les valeurs
livrées : le projet livre en hex (convention `faire_festival`).

```css
:root {
  /* ---- Palette du lieu / The venue's palette --------------------------- */
  --filature-creme:         #FFF4BD;  /* oklch(96.3% 0.071 98.1) — LE papier, PAS blanc */
  --filature-encre:         #2A2621;  /* 13.54:1 sur crème — voir Notes § 3 */

  /* LE GESTE : saturé. Filets, aplats, bordures. JAMAIS du texte. */
  --filature-cyan:          #1C9DD8;  /* oklch(65.9% 0.134 235.6) */
  --filature-magenta:       #E51B74;  /* oklch(60.2% 0.232 2.8)   */
  --filature-jaune:         #F6E921;  /* oklch(91.6% 0.189 105.3) */

  /* L'ENCRE : même teinte, assombrie, portante. Pas de jumeau jaune (Notes § 2). */
  --filature-cyan-encre:    #0076AE;  /* 4.50:1 sur crème · 5.00:1 sous blanc */
  --filature-magenta-encre: #DA006C;  /* 4.51:1 sur crème · 5.00:1 sous blanc */

  /* ---- Point d'entrée CHROME (navbar, footer, vues non-CMS) ------------ */
  /* Le socle LIT ces variables depuis :root (indirection) : on gagne quel que
     soit l'ordre de chargement. Sans ça, le chrome prendrait le défaut du
     socle au-dessus de nos blocs CMJ. */
  --skin-accent:            var(--filature-cyan-encre);
  --skin-accent-vif:        var(--filature-cyan);
  --skin-accent-contraste:  #FFFFFF;
}
```

**Jetons du socle repris sur `.tb-page`** : `--tb-surface` (crème),
`--tb-surface-alt` (blanc), `--tb-texte` (encre), `--tb-police-titre` (Bayon),
`--tb-rayon` / `--tb-rayon-sm` (25px, pilule), `--tb-ombre` / `--tb-ombre-forte`
(`none` — le site d'origine n'a aucune ombre, la profondeur se fait à la couleur
pleine). Corps : Asap 19px. Filet : `--filature-filet: 6px`. Titre :
`clamp(2.5rem, 6vw, 4.375rem)` — 70px au plafond, voir Notes § 10.

## Le geste signature — rotation CMJ par bloc

**La règle centrale du skin, et la seule chose à ne pas perdre.** Chaque bloc
s'ouvre sur un titre Bayon de sa teinte, souligné d'un filet de 6 px de la même
teinte. La teinte tourne **cyan → magenta → jaune**, puis recommence.

```css
/* Cycle de 3, quel que soit le nombre de blocs : 5, 7, 12 — il boucle.
   Sélecteur volontairement plus profond que le :root du socle : la portée
   nous fait gagner sans dépendre de l'ordre de chargement. */
.tb-page .tb-bloc:nth-of-type(3n+1) { /* cyan    */ --tb-accent: var(--filature-cyan-encre);    --tb-accent-contraste: #FFFFFF; --tb-accent-vif: var(--filature-cyan);    --tb-fond: var(--filature-cyan-encre);    --tb-fond-contraste: #FFFFFF; }
.tb-page .tb-bloc:nth-of-type(3n+2) { /* magenta */ --tb-accent: var(--filature-magenta-encre); --tb-accent-contraste: #FFFFFF; --tb-accent-vif: var(--filature-magenta); --tb-fond: var(--filature-magenta-encre); --tb-fond-contraste: #FFFFFF; }
.tb-page .tb-bloc:nth-of-type(3n+3) { /* jaune   */ --tb-accent: var(--filature-encre);         --tb-accent-contraste: #FFFFFF; --tb-accent-vif: var(--filature-jaune);   --tb-fond: var(--filature-jaune);         --tb-fond-contraste: var(--filature-encre); }

.tb-bloc__titre { color: var(--tb-accent);
                  border-bottom: var(--filature-filet) solid var(--tb-accent-vif); }
```

Le titre prend l'**encre** (lisible), le filet prend le **geste** (saturé). Les
deux sont de la même famille chromatique : l'œil lit une seule couleur.

**Quatre rôles par bloc, à ne pas confondre — tous du contrat socle :**

| Jeton | Rôle | Pourquoi ça compte ici |
|---|---|---|
| `--tb-accent` | L'**encre**. Le socle l'utilise en `color:` **7 fois** (liens de `.tb-bloc__texte`, fil d'ariane, intitulés). | **Doit toujours être lisible sur le papier.** Y mettre du jaune pour obtenir un aplat jaune mettrait les liens à 1.14:1 — sans que l'aplat, lui, paraisse fautif. C'est le piège que le contrat évite. |
| `--tb-accent-contraste` | Ce qui se pose **sur** `--tb-accent`. | Blanc sur les trois teintes (5.00 / 5.00 / 15.03:1). |
| `--tb-accent-vif` | Le **geste** : filets, bordures, anneaux. Le socle **n'y pose jamais de texte** (garantie explicite du contrat). | C'est cette garantie qui rend le jaune **sûr**. Notre filet de 6 px vit ici. |
| `--tb-fond` + `--tb-fond-contraste` | L'**aplat** d'un bloc plein et l'encre dessus. Repli : `--tb-accent` si on ne pose rien. | **C'est ici que le retournement du jaune prend effet** — pas dans `--tb-accent`. |

**Un seul filet par titre.** Le socle dessine son propre filet de `2.5rem × 3px`
**au-dessus** des `h2` (`h2.tb-bloc__titre::before`). L'ADN n'en a qu'un : 6 px,
**en dessous**, à la largeur du texte. On coupe celui du socle
(`.tb-page h2.tb-bloc__titre::before { display: none }`) — son intention (un
rappel discret) n'est pas la nôtre (un soulignement franc).

**Divergence résolue** (elle était ouverte tant que le socle avait un accent
unique `--bs-primary`) : le contrat `CHANTIER-10` fait des jetons un contrat
**par bloc** et non un singleton global. La rotation tient donc en 3 sélecteurs
dans notre CSS, sans forker `tb-blocs.css`. Règle retenue au passage :
**« ne pas renommer le sûr, nommer le dangereux »**.

**Divergence résolue** (elle était ouverte tant que le socle avait un accent
unique `--bs-primary`) : le contrat `CHANTIER-10` fait de `--tb-accent` /
`--tb-accent-vif` un contrat **par bloc** et non un singleton global. La
rotation tient donc en 3 sélecteurs dans notre CSS, sans forker `tb-blocs.css`.
Règle retenue au passage : **« ne pas renommer le sûr, nommer le dangereux »** —
`--tb-accent` garde sa sémantique de valeur portante, le geste arrive dans un
jeton neuf.

## Mode sombre — les deux neutres échangent

**L'ADN du lieu n'a pas de mode sombre. Le skin en a un quand même, et c'est
délibéré.** Le thème est une **préférence utilisateur** (bouton de navbar +
`localStorage`, cf. `commun/js/theme-switcher.mjs`), pas un réglage de marque.
Un skin qui la confisquerait parce que son papier est crème ferait passer sa
marque avant le confort de lecture de la personne. Et ne rien faire produit un
chrome sombre au-dessus de blocs crème : **une combinaison que personne n'a
dessinée**.

Le principe vient de l'ADN lui-même : le lieu a **deux neutres**, un crème et une
encre. En sombre, ils **permutent**. Même rapport (13.54:1), simplement retourné.

| | Clair | Sombre |
|---|---|---|
| Papier | `--filature-creme` `#FFF4BD` | `--filature-encre` `#2A2621` |
| Texte | `--filature-encre` | `--filature-creme` (13.54:1) |
| Titre | l'**encre** de la teinte | la teinte **vive** |
| Filet 6 px | la teinte **vive** | la teinte **vive** |

**Ce qui s'inverse, et pourquoi.** En clair, titre en encre + filet en vif : deux
valeurs de la même teinte, parce que le papier clair *interdit* au vif de porter
du texte. Sur papier sombre la contrainte tombe — le vif porte le texte (cyan
4.91:1, jaune 11.87:1). Titre et filet redeviennent donc **une seule teinte**,
c'est-à-dire exactement ce que faisait le site d'origine.

**Le jaune n'a plus besoin d'être retourné** en sombre : il porte son texte tout
seul (11.87:1). Le retournement était une contrainte du papier clair, pas une
propriété du jaune.

**Le magenta est la seule teinte éclaircie** : `#E51B74` tombe à 3.39:1 sur le
papier sombre. `--filature-magenta-sombre` `#FF3E88` (`oklch(67.2% 0.232 2.8)`)
satisfait **les deux** contraintes à la fois — 4.51:1 sur le papier *et* 4.51:1
sous l'encre en aplat. Le cyan et le jaune passent tels quels.

Spécificité : `[data-bs-theme="dark"] .tb-page .tb-bloc:nth-of-type(…)` (0,4,0)
bat la règle de rotation (0,3,0). Aucun `!important`, aucun changement au contrat
du socle.

## Mapping blocs `pages` → sections d'origine

L'app couvre déjà la page d'accueil historique, sans bloc nouveau à écrire :

| Section du site Divi | Type de bloc `pages` |
|---|---|
| Hero photo « Occupation temporaire… » | `HERO` |
| « Prochainement » (programmation) | `EVENEMENTS` + `CTA` |
| « Le bar / cantine » (grille 3 colonnes, 18 images) | `GALERIE` + `CTA` |
| « Le pavillon » | `IMAGE_TEXTE` + `CTA` |
| Aplat cyan + formulaire | `NEWSLETTER` |
| « Infos pratiques » (page dédiée) | `INFOS` + `CARTE_LEAFLET` |

## CTA voice

- Primary · fond **blanc** · texte `var(--tb-accent)` · bordure
  `var(--filature-filet)` de `var(--tb-accent-vif)` · rayon 25px (pilule).
  Le bouton « plein » du site d'origine est en fait un bouton **blanc à grosse
  bordure** — on reprend ce rapport plutôt que l'aplat du socle.
- Survol · le rapport s'inverse : fond `var(--tb-accent)`, texte
  `var(--tb-accent-contraste)`.
- Sur un bloc plein (hero, CTA) · fond `var(--tb-fond-contraste)`, texte
  `var(--tb-fond)` — l'inverse du bloc, donc lisible par construction.
- **Copie · verbale et située. À garder tel quel.** Le site d'origine écrit
  « Qu'est-ce qu'on mange à la Cantine ? », « En savoir plus sur le Pavillon »,
  « Découvrir toute la programmation du mois ». Jamais « En savoir plus » nu.
  Une question comme libellé de bouton est autorisée ici — c'est la voix du lieu.

## Motion stance

- **motion-cut.** Le site d'origine ne charge aucune bibliothèque (ni GSAP, ni
  framer-motion, ni Lenis, ni Lottie) et n'anime rien : ne pas en ajouter.
- Transitions de survol uniquement, sur `transform` / `opacity`, `--duree-base`.
- `prefers-reduced-motion: reduce` → fondu d'opacité ≤ 150 ms.

## Exports

`tokens.css` n'existe pas côté skin : la source de vérité est le `:root` du
CSS du skin (`pages/static/la_filature/css/la_filature.css`), sur le modèle de
`pages/static/faire_festival/css/faire_festival.css`. Pour un export Tailwind
v4 `@theme` ou DTCG `tokens.json`, demander *« étends design.md avec les exports
Tailwind »*.

## Notes — ce qui ne doit PAS être repris

L'ADN est le geste couleur, la typo et le rythme des facettes. Le reste est de
la dette Divi. À laisser derrière :

1. **Les échecs de contraste — le point dur.** Le CSS source déclare, en
   section 3, un corps **blanc 25 px sur fond blanc** (`1.00:1` — invisible) et
   le titre « Le pavillon » en **jaune sur blanc** (`1.27:1`). Aucune image de
   fond n'est déclarée pour cette section dans les deux CSS du site. Ailleurs :
   cyan sur crème `2.76:1` (échoue même le seuil 3:1 du gros texte), jaune sur
   cyan `2.42:1`. **À vérifier sur une capture avant de conclure à un bug de
   production** — mais dans tous les cas le skin ne reprend pas ces valeurs.
2. **Le jaune ne porte pas de texte — on retourne le rapport.** Sur papier crème
   il plafonne à `1.14:1` ; sur le blanc du site d'origine, `1.27:1`. Son jumeau
   encre à 4.5:1 serait `#7F6F00`, un olive qui n'est plus la couleur du lieu.
   Le dédoublement encre/geste marche pour le cyan et le magenta, **pas pour le
   jaune** — d'où l'absence de `--filature-jaune-encre`.

   La sortie n'est pas de dégrader le jaune mais **d'inverser le rapport** : le
   jaune devient **fond** (`--tb-fond`) et l'encre chaude passe dessus
   (`--tb-fond-contraste`) → **11.87:1**. La couleur reste criarde *et*
   devient lisible. Le site d'origine faisait exactement l'inverse.

   **Règle générale, qui dépasse ce skin** : *une teinte claire et saturée est
   un geste, pas une encre.* Elle se pose en fond avec une encre sombre dessus,
   jamais en texte sur clair. Vérifiée indépendamment sur le `kari #e9b322` du
   socle (1.92:1 en texte sur blanc → 8.36:1 en fond sous encre). Le patron est
   repris dans `CHANTIER-10`.
3. **`#666666` comme couleur de corps** — c'est le défaut Divi, pas un choix.
   Non repris : l'encre du skin est `--filature-encre` `#2A2621`, chaude,
   accordée au papier (13.54:1 sur crème contre 5.18:1 pour le `#666`).
4. **`#2ea3f2`** — le bleu par défaut de Divi, jamais remplacé sur le site
   d'origine. N'a rien à faire dans la palette.
5. **Les séparateurs SVG en vague** entre sections — signature Divi reconnaissable
   entre toutes. Le rythme se fait au papier (crème → blanc → aplat), pas au
   découpage décoratif.
6. **`transition: all`** (×28 dans le CSS source) — animer `transform` et
   `opacity`, nommément.
7. **4 × `<h1>` par page, zéro `<main>`, zéro `<section>`** — soupe de `<div>`
   du page-builder. Le markup de `pages` est déjà sémantique : ne pas régresser.
8. **`!important` partout** — conséquence du builder, sans objet ici.
9. **Bayon n'a qu'une graisse (400) et pas d'italique.** La hiérarchie se fait
   à la taille et à la couleur, jamais à la graisse. Pas de titre en italique
   (règle Hallmark globale, et de toute façon la fonte ne l'a pas).
10. **70 px en dur ne survit pas au mobile.** L'original fixe `font-size: 70px` ;
    `.tb-bloc__titre` le passe en `clamp(2.5rem, 6vw, 4.375rem)` — l'intention
    est gardée, le plafond reste 70px, et ça tient à 320px. Titres ≤ 7 mots.
    Bayon étant condensé, le titre porte aussi `overflow-wrap: anywhere` et
    `min-width: 0` (gate Hallmark 51).
