# Skin V2 : relecture du style et corrections / V2 skin: style review and fixes

**Date :** 2026-09-13
**Migration :** Non

## Resume / Summary
**Quoi / What :** relecture complète du style du skin V2 de Lespass
(`pages/static/V2/css/V2.css`), puis correction des points relevés : 4
critiques, 9 majeurs, 6 mineurs.
- **Contraste** : le bouton principal, le solde, le bouton « Recharger » et le
  gris discret passent tous le seuil WCAG AA de 4,5:1.
- **Accessibilité** : les boutons radio des missions bénévoles étaient invisibles
  et inaccessibles au clavier ; ils sont rétablis.
- **Système** : échelle typographique en `rem`, toutes les couleurs et tous les
  mouvements passent par des variables, plus aucun `ease` par défaut.
- **Nettoyage** : ~290 lignes de composants de maquette non branchés sortent de
  `V2.css` vers une réserve non chargée.
- **Bug** : un thème sombre choisi sur un autre skin passait les composants
  Bootstrap en sombre sur le papier clair du V2. Le V2 est désormais fixé en clair.

/ Full style review of the V2 skin, then fixes: AA contrast on brand moments,
volunteer radios restored, rem type scale, tokenised colours and motion, unused
mockup CSS moved to a non-loaded reserve, dark theme leak from other skins fixed.

**Pourquoi / Why :** l'identité de la DA v1 est solide (couleur réservée aux gestes
TiBillet, Luciole + Unbounded), mais la fusion de la maquette avait laissé des
contrastes sous le seuil précisément sur les moments de marque, des valeurs en dur,
des tailles au demi-pixel et du CSS mort.

## Choix d'implementation / Implementation notes

### Critiques / Critical
- **`--letchi-fond: #ea3b69`** (nouveau) : le letchi éclairci de 4 %. L'encre sur
  le letchi canonique ne donnait que 4,45:1 — un bouton de 14,5px gras n'est pas
  du « grand texte ». Sur `--letchi-fond` : 4,63:1, écart invisible.
  `--color-primary` pointe dessus ; `--letchi` reste la valeur de charte (dégradés
  décoratifs). Triplets Bootstrap `--bs-primary-rgb` / `--bs-btn-focus-shadow-rgb`
  mis à jour (`234, 59, 105`). Le survol/appui de `.btn-primary` **éclaircit**
  (mélange avec du blanc) au lieu d'assombrir : le texte est en encre.
  `--grad-chaud` part de `--letchi-fond`.
- **Solde (`.me-card__amount`)** : encre pleine + filet `--grad-chaud` dessous.
  Le dégradé en `background-clip: text` tombait à 1,92:1 côté zanana.
- **`.btn--signature` (« Recharger »)** : `--grad-chaud` + texte encre (4,63 à 9,5:1)
  au lieu de `--grad-nuit` + texte blanc (3,25:1). `--grad-nuit` reste au talisman.
- **Missions bénévoles** : `.checkbox-line input { display: none }` retirait le
  bouton radio (le gabarit n'a pas de `.box` de remplacement). Le champ n'est plus
  masqué — et seulement visuellement — que s'il est suivi d'une `.box`.

### Majeurs / Major
- **Variables de couleur** : `--color-hover`, `--color-hover-soft`,
  `--color-overlay-hover`, `--color-rule`, `--color-grid-line`,
  `--color-surface-sunken`, `--color-primary-border`, `--color-avatar`,
  `--color-text-inverse`, `--color-inverse-*`, `--color-surface-overlay`,
  `--shadow-pin`, `--grad-talisman`. Les dégradés référencent les couleurs de charte.
- **Échelle typo** : 24 tailles en px → `--text-2xs` … `--text-2xl` + `--text-display`
  (rem). Arrondis au pas voisin (13,5 → 14, 14,5 → 15, 30 → 28). Les `line-height`
  en px des boutons et badges passent en rem.
- **Unbounded** : titre de page en `clamp(1.75rem, 1.1rem + 2.6vw, 3rem)` (28 → 48px),
  coupure des mots longs ; titres de section et de bloc en graisse 500 au lieu de 700.
- **Mobile** : `overflow-x: clip` sur `html`/`body` ; grilles en `minmax(0, 1fr)` ;
  raccourcis de lieux 5 → 3 → 2 colonnes ; `.me-card` passe à la ligne.
- **Capitales espacées** : 10 étiquettes en casse normale, gras 13px (sommaire,
  fil d'Ariane, faits du lieu, étiquettes d'info, solde, compteur de résultats…).
  Gardées : eyebrow, en-têtes de tableau, pastille de date, numéro de carte.
  Les textes des gabarits étaient déjà en minuscules : aucune traduction touchée.
- **Code mort** (vérifié : aucune occurrence dans les `.html`/`.js`/`.mjs`/`.py`) :
  - supprimé : `.mockup-switch`, `.module.is-open`, `.talisman-layout`, `.footer-cta__row` ;
  - déplacé vers **`pages/static/V2/css/V2-reserve.css`** (chargé par aucun
    gabarit) : composants prévus par les `V2-HERE` — `.ledger`, `.pin-btn` +
    `.favorite-card`, panneau de filtres d'agenda, poignée de glisser-déposer,
    cloche de notifications, `.role-card`, `.help-card`, `.feature-card`,
    `.stat-box`, `.profile-header`, `.footer-links`, `.stat-pill`, `.toc`,
    `.layout-with-sidebar`, `.event-grid`.
- **Mouvement** : `--dur-fast`, `--dur-base`, `--ease-out`, `--ease-in-out` ;
  appui d'1px sur `.btn`/`.icon-btn`/`.tag-pill` ; `prefers-reduced-motion`
  global sur les **transitions** (pas les animations : les spinners Bootstrap se
  ralentissent déjà eux-mêmes, les figer masquerait le chargement).
- **`!important`** : 3 retirés sur 4, en réglant les variables que Bootstrap et
  `explorer.css` lisent déjà (`--bs-secondary-rgb` sur le badge du panier,
  `--bs-primary` sur `.explorer-card--current`). Reste `object-fit: contain` sur
  le logo, imposé par l'include partagé `commun/partials/picture.html`.
- **Cartes dans des cartes (version légère)** : `.service-card` sans cadre dans un
  module de Mon espace (filet en tête) ; `.map-panel` sans bordure dans
  `.venue-brief` ; `.me-card` sans bordure dans l'en-tête « moi ».

### Mineurs / Minor
- **Footer** : un seul aplat en dégradé (« Faire un don ») ; « Créer un espace » et
  « Contribuer » en boutons blancs avec une pastille en dégradé. Libellés autorisés
  sur deux lignes (débordaient à 320px).
- **`--color-text-faint`** : `#808080` (3,73:1) → `#6b6b6b` (5,0:1 sur papier).
  `.legal-badge` passe en `--color-text-muted` (fond du footer plus sombre).
- **Cibles tactiles** : boutons d'icône à 44px sur `pointer: coarse`.
- **Centrage d'encre** : `text-box: trim-both cap alphabetic` là où c'est supporté,
  le `translateY(2px)` reste en repli.
- **Styles inline** : `style="margin-top: …"` des grilles → `.grid--sous-titre` /
  `.grid--sous-titre-serre`.
- **Thème** : `pages/V2/shell.html` ne charge plus `theme-switcher.mjs` et fixe
  `data-bs-theme="light"`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/static/V2/css/V2.css` | Tout ce qui précède (2 521 → ~2 350 lignes) |
| `pages/static/V2/css/V2-reserve.css` (nouveau, non chargé) | Composants de maquette en attente de branchement |
| `pages/templates/pages/V2/shell.html` | Thème clair fixé, `theme-switcher.mjs` retiré |
| `pages/templates/pages/V2/vues/accueil.html`, `adhesions.html`, `agenda.html`, `evenement.html` | Styles inline des grilles remplacés par des classes |

### Migration
- **Migration necessaire / Migration required :** Non

---

## Comment tester (a la main) / Manual test

Prérequis : un tenant en skin V2. Vérifier chaque point à 320, 375 et 1280px.

### Test 1 — Contrastes et moments de marque
1. Mon espace : le solde est en encre avec un filet dégradé dessous ; « Recharger »
   est en dégradé chaud, texte encre.
2. Boutons principaux (`.btn--primary`, `.btn-primary` du panneau de connexion) :
   teinte letchi quasi identique ; au survol, le fond s'éclaircit.
3. Panier : ajouter un article → pastille letchi ; en anonyme → pastille grise
   (après la mise à jour HTMX aussi).

### Test 2 — Missions bénévoles
1. Page d'un événement avec actions bénévoles, ouvrir l'accordéon.
2. Les boutons radio sont visibles ; sélection à la souris puis au clavier
   (Tab, flèches), coché en encre.

### Test 3 — Typographie et mise en page
1. Titre de page : ~28px en téléphone, ~48px en grand écran ; un nom long ne
   déborde pas.
2. Titres de section plus légers (Unbounded 500).
3. Étiquettes (sommaire, fil d'Ariane, « Quand / Où », « Adresse ») en casse normale.
4. Aucun défilement horizontal ; Mon espace à 375px : raccourcis sur 2 colonnes,
   carte et solde l'un sous l'autre.
5. Modules de Mon espace : services en entrées à filet, sans cadre ; les cartes
   de « Mon agenda » gardent le leur.

### Test 4 — Footer, tactile, mouvement
1. Footer : un seul bouton en aplat dégradé, deux boutons blancs à pastille.
2. Sur téléphone : barre utilisateur à boutons 44px ; sur une page CMS à sommaire,
   le sommaire ne passe pas sous la barre au défilement.
3. Système en « mouvement réduit » : plus aucune transition.
4. Page Réseau : la carte « Vous êtes ici » a un contour encre.

### Test 5 — Thème sombre
1. Skin classic : activer le thème sombre.
2. Ouvrir une page V2 : tout reste clair, panneau de connexion et menus compris.

### Verifs automatiques
- Non lancées pendant la session (docker indisponible dans l'environnement).
- `docker exec lespass_django poetry run pytest tests/pytest/ -q`
- E2E avec `lespass` en V2 (voir `2026-09-11-v2-da-v1-luciole-unbounded.md`) ;
  `test_theme_language` échoue en V2, comme avant (pas de mode sombre).
