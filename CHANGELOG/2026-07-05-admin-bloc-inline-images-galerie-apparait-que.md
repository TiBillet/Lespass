# Admin bloc : l'inline « Images de galerie » n'apparaît que sur un bloc GALERIE / Block admin: the gallery-images inline only shows on GALERIE blocks

**Date :** 2026-07-05
**Migration :** Non / No

`ImageGalerie` ne sert qu'au bloc GALERIE (modèle porteur de ses images) mais
l'inline s'affichait sur TOUS les types de blocs (bruit dans le formulaire).
`BlocAdmin.get_inlines` ne le retourne plus que pour un bloc GALERIE
enregistré ; à la création (type inconnu côté serveur), il apparaît après le
premier enregistrement — flux Django standard.
