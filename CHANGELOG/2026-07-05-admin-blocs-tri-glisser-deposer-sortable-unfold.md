# Admin blocs : tri par glisser-déposer (sortable Unfold) / Blocks admin: drag-and-drop sorting (Unfold sortable)

**Date :** 2026-07-05
**Migration :** Non / No

La liste des Blocs (`/admin/pages/bloc/`) et l'inline des images de galerie
utilisent le **sortable d'Unfold** (comme la démo formula/circuit) :
`ordering_field = "position"` + `hide_ordering_field = True` — poignée de
glisser-déposer à la place de la saisie manuelle du nombre, positions
enregistrées dans l'ordre affiché. Conseil d'usage : filtrer par page avant
de trier (sinon les blocs de toutes les pages se mélangent dans la liste).
