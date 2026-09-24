# Pages (admin) — suites de l'aperçu en direct / Pages admin — live preview follow-ups

**Date :** 2026-09-23
**Origine :** refonte de l'édition des pages dans l'admin, et audit djc de cette refonte.
Voir `CHANGELOG/2026-09-23-pages-apercu-admin.md` (sections A à F).

Points relevés mais volontairement **non traités**, avec la raison et le
correctif envisagé.
/ Items found and deliberately left undone.

---

## 1. En-tête de « Contenu de la page » périmé après une action dans l'iframe / Stale header after an action inside the iframe

*(Point 7 de l'audit — jugé secondaire.)*

**Constat.** Sur la fiche Page, les boutons ↑ ↓ ✕ vivent dans l'iframe d'aperçu. Après une action, le serveur répond `HX-Refresh` et **seule l'iframe** se recharge. L'en-tête de la section, lui, est dans la page de l'admin (`admin/pages/page/blocs_de_la_page.html`) et ne bouge pas.

**Scénarios d'échec :**
- supprimer un bloc : le texte « 5 blocs » reste affiché au lieu de « 4 blocs » ;
- supprimer le **dernier** bloc : l'iframe devient vide, au lieu du message « Cette page n'a pas encore de bloc » ;
- cliquer sur ✕ ou ↓ pour un bloc déjà supprimé dans un autre onglet : la vue répond 404. L'écouteur `htmx:beforeSwap` du shell affiche alors la page 404 du skin **dans** l'iframe, à la place des blocs.

**Piste écartée : `hx-swap-oob`.** Un échange hors-bande ne remplace des éléments que dans le document qui a reçu la réponse, ici celui de l'iframe. L'en-tête est dans un autre document, celui de l'admin : la réponse ne peut pas l'atteindre. De plus, `HX-Refresh` recharge l'iframe, donc le corps de la réponse n'est même pas utilisé.

**Pistes, de la plus simple à la plus lourde :**
1. **Déplacer l'en-tête dans le document de l'iframe** (recommandé). Le compteur, le menu « + Ajouter en tête » et le message « page vide » seraient rendus par `admin/pages/apercu/_blocs.html` quand `avec_outils` est vrai, en styles en ligne comme les barres d'actions. `HX-Refresh` les recalcule alors avec le reste, sans JavaScript de communication. Dans la page de l'admin, il ne reste que le titre de section et l'iframe, toujours affichée, même vide. Coût : environ 1 h.
2. **Retirer le compteur** de l'en-tête et toujours afficher l'iframe, qui dirait elle-même « aucun bloc ». Coût : 15 min, mais on perd l'information « N blocs » en tête de section.
3. **Faire prévenir la page par l'iframe** (`window.parent.postMessage`), et recharger la section en HTMX côté admin. Plus de JavaScript et deux documents à synchroniser : c'est la moins lisible des trois.

**Dans tous les cas, pour le 404 :** faire répondre `HX-Refresh` par `vue_deplacer_bloc` et `vue_retirer_bloc` même quand le bloc est introuvable. L'aperçu se recharge alors proprement, avec l'ordre réel des blocs. Environ 10 lignes dans `pages/admin_apercu.py`, plus un test.

## 2. Suggestions de l'audit non retenues pour l'instant / Audit suggestions not applied yet

- **Scripts tiers dans le document d'aperçu.** L'aperçu charge le `shell.html` du skin avec tous ses scripts, dont formbricks s'il est configuré, et le recharge à chaque frappe. Ce n'est pas un nouveau risque : les pages publiques sont déjà sur le même domaine que l'admin. Mais c'est inutile et bruyant. **Correctif :** entourer ces scripts de `{% if not apercu_admin %}` dans les 3 shells.
- **Menu « + » répété sur chaque bloc.** `_elements_avec_outils` construit le menu complet des modèles (≈ 25 URL) pour chaque bloc. Une page de 50 blocs, c'est ≈ 1250 `reverse()` et des `<template>` lourds. **Correctif :** un seul menu dans le document, avec `inserer_apres` posé au clic, ou les URL calculées une fois par requête.
- **Deux chemins de validation.** La sauvegarde passe par `ModelForm` + `LignesField`, l'aperçu par `ApercuBlocSerializer`. Ils peuvent diverger : `nombre_max` est limité à 1000 dans l'aperçu, et à rien dans le modèle. **Correctif :** poser les bornes au même endroit (validateurs du modèle), et les relire dans le serializer.

## 3. Hors du périmètre de l'audit / Outside the audit scope

- **Plan B : édition directe dans le bloc.** Il faudrait des attributs `contenteditable` et `data-champ` dans les gabarits de bloc en mode `apercu_admin`, plus un `postMessage` vers le formulaire parent. Coût : annoter environ 60 gabarits sur 3 skins. En attente d'un retour d'usage sur l'aperçu.
- **Vidéo choisie mais pas encore envoyée.** Contrairement aux images, elle n'a pas d'emplacement dans l'aperçu : une balise `<video>` ne peut pas afficher d'image. **Piste :** en mode `apercu_admin`, les gabarits vidéo afficheraient un cadre hachuré à la place de la balise `<video>`.
