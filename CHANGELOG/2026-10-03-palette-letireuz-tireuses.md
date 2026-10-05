# Palette « Létireuz » pour l'accent des tireuses / "Létireuz" palette for tap accent colors

**Date :** 2026-10-03
**Migration :** Non

## Resume / Summary
**Quoi / What :** Les pastilles « Couleur principale » d'un fût (admin) proposent la palette « Létireuz » : 11 couleurs vives (blue, teal, violet, green, pink, olive, brown, orange, red, lime, indigo — tokens `--color-tireuse-{teinte}`), à la place des 14 couleurs précédentes.
/ The keg "main color" swatches now offer the 11-color "Létireuz" palette instead of the previous 14 colors.

**Pourquoi / Why :** Palette fournie par le design (nuancier Létireuz, couleurs échantillonnées au pixel). Pour teal et pink, ce sont les pastilles qui font foi (`#009EB3`, `#FF589F`), pas les étiquettes du nuancier.
/ Palette provided by design; for teal and pink the actual swatch colors are used, not the labels.

**Attention accessibilité / Accessibility note :** le texte de l'écran tireuse reste blanc. Avec le blanc, le contraste va de 2,94:1 (pink) à 4,99:1 (indigo) : seuls violet, brown et indigo passent 4,5:1. Sur la carte sombre `#2a2d2f`, brown (2,81) et indigo (2,78) passent sous 3:1.
/ Screen text stays white: only violet, brown, indigo reach 4.5:1; brown and indigo are below 3:1 on the dark card.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/products.py` | `COULEURS_ACCENT` = palette Létireuz (11 couleurs, token en commentaire) |
| `Administration/templates/admin/product/widget_couleur_accent.html` | Commentaires mis à jour |
| `controlvanne/static/controlvanne/css/tireuse.css` | Commentaire sur le contraste du texte blanc |
| `tests/pytest/test_controlvanne_ecran_calibration.py` | Les tests de contraste deviennent : « la liste = palette Létireuz » + « codes en minuscules » |

Nouvelles chaînes traduisibles : « Rose », « Brun », « Orange », « Citron vert » (workflow i18n à lancer).

---

## Comment tester (a la main) / Manual test
### Test 1 — pastilles dans l'admin
1. Admin > Fûts > ouvrir un fût.
2. Champ « Couleur principale » : 11 pastilles + « Aucune ».
3. Choisir « Rose », enregistrer, rouvrir : la pastille Rose est cochée.

### Test 2 — fût avec une ancienne couleur
1. Ouvrir un fût qui avait une couleur de l'ancienne palette (ex. `#8b59e2`).
2. Elle apparaît en premier (« Couleur actuelle ») : rien n'est perdu.

### Test 3 — écran de la tireuse
1. Brancher le fût sur une tireuse, ouvrir le kiosk.
2. Le fond prend la couleur choisie. Vérifier la lisibilité du texte blanc, surtout sur pink, olive et orange.

### Verifs DB / Playwright
- `pytest tests/pytest/test_controlvanne_ecran_calibration.py`
