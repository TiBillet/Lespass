# Skin V2 — suites de la relecture du style / V2 skin — style review follow-ups

**Date :** 2026-09-13
**Origine :** relecture du style du skin V2 et corrections du même jour.
Voir `CHANGELOG/2026-09-13-v2-style-relecture-hallmark.md`.

Ce qui a été relevé mais volontairement **non traité**, avec la raison et le
correctif envisagé.
/ Items found during the review and deliberately left undone.

---

## 1. Vérifications non faites / Checks not done

- **Aucune vérification visuelle ni aucun test lancé** pendant la session (docker
  indisponible). Le parcours de `2026-09-13-v2-style-relecture-hallmark.md`
  § « Comment tester » reste entièrement à dérouler, ainsi que `pytest` et les E2E en V2.
- **`pages/static/V2/css/V2-reserve.css` n'apparaît pas dans `git status`** alors
  qu'il n'est pas ignoré (`git check-ignore` ne renvoie rien) : sans doute un réglage
  qui masque les fichiers non suivis. À ajouter explicitement s'il est gardé.

## 2. Structure / Structure

- **Cartes dans des cartes, version lourde.** Seule la couche intérieure a été
  retirée. Les modules de Mon espace restent des boîtes bordées ; la version lourde
  en ferait des sections séparées par un filet (toujours en `<details>`). Change
  nettement la page : **décision à prendre sur capture**.
- **Cartes événement dans « Mon agenda »** : encore une carte dans un module. Gardé
  exprès (la photo de couverture a besoin d'un bord) ; à revoir avec la version lourde.
- **Rythme général « tout-carte »** : cadres fins et coins arrondis partout. La
  version lourde ci-dessus en est le premier levier ; au-delà, c'est un travail de DA.

## 3. Cascade Bootstrap / Bootstrap cascade

- **Couches CSS (`@layer`)** : charger Bootstrap et `seo/static/seo/explorer.css`
  dans une couche `vendor` depuis `pages/V2/shell.html`. `V2.css` gagnerait sans
  surenchère de spécificité, et les ~30 préfixes `#explorer-root` pourraient partir.
  **Risque** : panneaux latéraux, accordéons, tunnels de réservation et d'adhésion de
  tout le V2 ; attention aux `!important` des utilitaires Bootstrap, qui dans une
  couche l'emportent sur ceux hors couche. **Chantier à part, avec passe E2E complète.**
- **Dernier `!important` subi** : `.place-id__mark--logo img { object-fit: contain !important }`.
  L'include partagé `commun/partials/picture.html` pose toujours `.object-fit-cover`
  (Bootstrap, `!important`). Correctif : un paramètre `fit` dans l'include (défaut
  `cover`), puis retirer la surcharge. Touche tous les skins.

## 4. Libellés et traductions / Labels and translations

- **Libellés longs du footer** : « Create a TiBillet space for your collective »,
  « Venez contribuer à TiBillet » passent désormais sur deux lignes (ils débordaient
  à 320px). Mieux : des libellés plus courts (« Créer un espace », « Contribuer »).
  Demande de modifier les chaînes, donc le workflow de traduction du mainteneur.

## 5. Petits restes / Leftovers

- **Classes inutilisées gardées** car elles appartiennent à des composants utilisés :
  `.place-card__*`, `.section__head` / `__rule` / `__title-marker`, `.callout__title`,
  `.avatar--sm` / `--lg`, `.grid--2` / `--4`, `.shortcut__logo` / `__meta`,
  `.talisman__holder`, `.map-pin--place`, `.badge--more`, et les familles de
  catégories non employées (`badge--`, `bg-`, `solid-` : gold, indigo, mauve, olive,
  slate, teal, terracotta). À réévaluer quand les `V2-HERE` seront branchés.
- **Styles inline restants**, non traités car hors grilles :
  - `pages/V2/vues/agenda.html:191` : `z-index: 999` en ligne sur un `sticky-top` ;
  - `pages/V2/vues/reseau.html:83` : `max-width: 800px` sur l'alerte ;
  - `pages/V2/partials/evenement_accordeon.html` et `carte_evenement.html` : styles
    Bootstrap hérités — ces deux gabarits ne sont plus inclus en V2 et sont déjà
    listés à supprimer dans `v2-da-v1-points-laisses-de-cote.md` § 3.
- **`--color-text-faint` sur fond de footer** : `#6b6b6b` y fait 4,15:1. Il n'y est
  plus employé (`.legal-badge` passé en `--color-text-muted`) ; ne pas l'y réintroduire.
- **Test E2E `test_theme_language`** : échoue toujours en V2 (pas de `#themeToggle`,
  thème désormais fixé en clair). Le marquer `skip` pour le skin V2 ou l'adapter.
