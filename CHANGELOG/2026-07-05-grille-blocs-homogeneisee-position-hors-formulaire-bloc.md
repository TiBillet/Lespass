# Grille des blocs homogénéisée + position hors du formulaire bloc / Unified block grid + position removed from the block form

**Date :** 2026-07-05
**Migration :** Non / No

**Audit visuel (captures Playwright pleine page avant/après)** — chaque bloc
vivait sur sa propre grille : gouttières différentes, cartes « plus à
l'intérieur » que les titres, trous verticaux géants entre un titre et sa
grille. Corrections dans `tb-blocs.css` :
- **Jeton unique `--tb-gouttiere`** (clamp 1.25rem→4rem) : les 6 gouttières
  codées en dur basculent dessus (blocs, grille, fil d'ariane, leaflet, FAQ).
- **Jeton `--tb-largeur-boite`** = largeur-max + 2×gouttière : les boîtes
  AUTONOMES (grille de cartes, fil d'ariane, infos/carte leaflet, colonnes
  FAQ, titre/signature de page) portaient `max-width + padding gouttière` →
  leur contenu était décalé de +gouttière par rapport aux sections (le
  « cartes plus à l'intérieur » signalé). Le calc les aligne au pixel.
- **Rythme vertical titre→grille** : une section-titre (évènements,
  liste-sous-pages, paragraphe) suivie d'une grille lui colle désormais
  (avant : padding bas + padding haut s'additionnaient ≈ 2× l'espace de
  section de vide).
- **`text-wrap: balance`** sur les titres de blocs, de cartes et de page
  (règle /ui : pas de mot orphelin).
- Le h1/la signature de page (ajoutés à l'audit SEO) rejoignent le système
  (ils étaient sur 72ch + 1rem, collés au bord gauche).
- **Gouttière ALIGNANTE (2e passe, tous les blocs)** : deux logiques
  coexistaient — contenu centré dans largeur-max (titres, textes → bord à
  144px sur un écran de 1440) vs contenu calé à gauche de sa section (CTA
  « Rejoignez la coopérative », témoignage, grande image, image+texte,
  médias → gouttière brute à 64px). Le padding des sections devient
  `max(gouttière, (100% − largeur-max)/2)` : chaque section contraint son
  contenu dans le conteneur commun quel que soit son alignement interne.
  Vérifié par captures Playwright pleine page : grande image, embed vidéo,
  CTA (filet à 144), témoignage, Soutenir, FAQ, infos/Leaflet — tous sur la
  même verticale que les titres. Le fond des bandes (hero, CTA) reste
  pleine largeur.
- **Bloc IMAGE_TEXTE réparé (« Une salle modulable »)** : le bloc se
  double-conteneurisait (max-width + margin auto sur une section qui porte
  déjà la gouttière alignante) → colonnes rétrécies, images timbre-poste,
  décalées d'une gouttière. Double contrainte supprimée : l'image occupe
  toute sa moitié, bord posé sur le conteneur, la quinconce gauche/droite
  (image_position) est conservée.
- **Skin faire_festival vérifié** (home, infos-pratiques, notre-démarche) :
  cohérent par design (grille Bootstrap centrée, brutalisme voulu) — h1 de
  secours et fil d'ariane tombent dans le même container. Seul point
  signalé, non corrigé (choix de maquette) : le bloc IMAGE *avec titre* est
  rendu en « image-titre de section » (~50 %, centrée) — peu adapté aux
  photos d'en-tête comme celle de la démo notre-démarche.

**Admin** : le champ `position` disparaît aussi du FORMULAIRE du bloc
(l'ordre se règle au glisser-déposer dans la liste ; à la création,
save_model place le bloc en fin de page).
