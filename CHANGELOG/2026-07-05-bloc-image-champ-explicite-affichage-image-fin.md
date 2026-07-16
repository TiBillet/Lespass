# Bloc IMAGE : champ explicite `affichage_image` (fin de l'interrupteur caché) / IMAGE block: explicit `affichage_image` field (no more hidden toggle)

**Date :** 2026-07-05
**Migration :** Non pour la branche (champ plié dans `pages/0001` régénérée ; colonne posée à la main sur la base dev) / Folded into the regenerated `pages/0001`

Le skin faire_festival choisissait le rendu du bloc IMAGE selon la PRÉSENCE
du titre (interrupteur caché, jugé mauvais pattern par le mainteneur) : une
photo titrée devenait une vignette minuscule (« Notre démarche »). Désormais :
- **`Bloc.affichage_image`** (choices, pattern `image_position`) :
  `PLEINE_LARGEUR` (défaut, photos) ou `VIGNETTE_TITRE` (petite image-titre
  dessinée, centrée à taille naturelle). Le champ `titre` redevient un simple
  texte alternatif.
- Honoré par les DEUX skins : ff (les 2 modes historiques, choisis
  explicitement) et classic (nouvelle variante `--vignette`).
- Intégré partout : catalogue API v2, openapi, admin (`conditional_fields`
  sur le type IMAGE), seeder ff (les 2 images-titres dessinées passent en
  VIGNETTE_TITRE, la photo d'en-tête de notre-démarche en pleine largeur —
  reseedé et vérifié par captures : home ff inchangée au pixel).
