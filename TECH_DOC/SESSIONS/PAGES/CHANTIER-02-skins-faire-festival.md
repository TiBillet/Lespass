# CHANTIER 02 — Skins des blocs + adaptation faire_festival

**Statut** : En cours · **Démarré** : 2026-06-28

## Objectif

Donner aux templates de blocs un **niveau de skin** (`pages/templates/pages/<skin>/`),
défaut **`classic`**, et adapter le moteur pour le skin **faire_festival**. But final :
**chantefrein** (moteur pages, module ON, skin faire_festival) doit être **exactement
comme le-coeur-en-or** (home legacy faire_festival hardcodée, module OFF), mais via des
blocs qui contiennent le texte et les images du Faire Festival.

## Décisions validées (brainstorming 2026-06-28)

1. **Archi skins** : `pages/templates/pages/<skin>/page.html` + `…/<skin>/partials/bloc_<type>.html`.
   Défaut `classic` (renommage de l'existant). Résolution skin du tenant
   (`ConfigurationSite.skin`) → dossier, **fallback `classic`** par bloc (Django
   `{% include liste %}` / `render(request, [..])` = select_template, premier trouvé).
2. **Nouveaux blocs génériques** (réutilisables, habillés par skin) — PAS spécifiques
   faire_festival. **Règle : chaque nouveau bloc a un template `classic` ET `faire_festival`.**
3. **Cartes répétées** : bloc **`CARTE`** générique (champs plats) ; la vue **regroupe
   les CARTE consécutives** dans une même grille (`<div class="tb-grille">`). Pas de JSON.
4. **Bascule** `le-coeur-en-or` et `chantefrein` en skin `faire_festival`.
   - le-coeur-en-or : module OFF → home legacy (référence).
   - chantefrein : module ON → home pages (cible à faire matcher).

## Bloc `CARTE` (générique)
Champs plats : `surtitre` (ex. « JOUR 01 »), `image`, `titre`, `texte`, `badge`
(ex. « gratuit »), `bouton_label`, `bouton_url`. Le template s'adapte à ce qui est
rempli (image → style étape/tuto ; surtitre sans image → style jour).

## Décomposition de la home faire_festival (cible chantefrein)
HERO(logo + badge date + sous-titre) → VIDEO_TEXTE(« c'est quoi ? ») → CARTE×3 (jours)
→ CTA(« En savoir plus ») → [image-titre tuto] → CARTE×3 (étapes tuto).

## Étapes

| # | Étape | Statut |
|---|-------|--------|
| A | Archi skins (dossier `classic` + fallback + template-tag) + bascule 2 tenants | ✅ Fait |
| B | Templates faire_festival des 5 blocs EXISTANTS | ✅ Fait |
| C | Nouveaux blocs `CARTE` (+ regroupement) & `VIDEO_TEXTE` & `IMAGE` (templates classic + faire_festival) | ✅ Fait |
| D | Peupler la home de chantefrein (contenu festival) → comparer à le-coeur-en-or | ✅ Fait |

**Résultat** : chantefrein (moteur pages) reproduit **PIXEL-PERFECT** la home
faire_festival de le-coeur-en-or (legacy), section 2 comprise (vidéo à gauche /
texte + cartes JOUR imbriquées + bouton à droite).

**Comment le nesting est obtenu sans casser le modèle de blocs** : `grouper_blocs`
détecte un `VIDEO_TEXTE` suivi de `CARTE` consécutives (+ un `CTA`) et les regroupe
en un groupe **`section_video`**. Le template faire_festival/page.html rend ce groupe
comme la section 2 du legacy (2 colonnes). En skin `classic`, ce même groupe est
empilé (vidéo+texte, grille de cartes, bouton). Les blocs restent des CARTE
indépendantes (décomposition préservée).

Types de groupes (`pages.services.grouper_blocs`) : `solo`, `grille`, `section_video`.

## Point ouvert (étape D)
Images festival = statics (`faire_festival/image/*.webp`). Pour les blocs : soit fixture
qui copie dans le media de chantefrein, soit champ `image_statique` (chemin static) en
plus de l'upload. À trancher en étape D.

## Journal
- **2026-06-28** — Brainstorming validé (archi skins, blocs génériques, CARTE+regroupement,
  condition : tout nouveau bloc a un template classic). Chantier ouvert.
