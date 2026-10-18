# Image vignette d'évènement retirée de l'admin / Event sticker image removed from admin

**Date :** 2026-10-18
**Migration :** Non

## Resume / Summary
**Quoi / What :** le champ « Image vignette » (`Event.sticker_img`) n'apparaît plus dans le formulaire admin des évènements. Les vues de l'agenda ne calculent plus `event.sticker_img`. Le skin `faire_festival` affiche l'image principale (`event.img`, avec son repli adresse → configuration) sur ses cartes d'agenda. Le champ reste dans le modèle et dans l'API v2.
/ The "Sticker image" field is no longer shown in the event admin form. Agenda views no longer compute `event.sticker_img`. The `faire_festival` skin shows the main image on its agenda cards. The field stays in the model and the v2 API.

**Pourquoi / Why :** le skin V2 n'affiche plus la vignette nulle part (cartes, carrousel et page évènement utilisent `event.img`). Le champ embrouillait la saisie dans l'admin.
/ The V2 skin no longer displays the sticker image anywhere; the field was confusing in the admin.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `sticker_img` retiré du fieldset de `EventAdmin` |
| `BaseBillet/views.py` | 4 lignes `event.sticker_img = event.get_sticker_img()` supprimées |
| `pages/templates/pages/faire_festival/vues/agenda.html` | Carte : `event.img.med` au lieu de `event.sticker_img.med` |
| `pages/templates/pages/faire_festival/vues/agenda_liste_suite.html` | Idem pour la pagination |
| `tests/pytest/test_seo_canonical_doublons.py` | Ligne qui reproduisait le calcul de la vue supprimée |

Non modifié : le champ `Event.sticker_img`, la méthode `Event.get_sticker_img()` (encore appelée par `pages/classic/partials/carte_evenement.html`), `PostalAddress.sticker_img`, l'API v2.

---

## Comment tester (a la main) / Manual test
### Test 1 — admin
1. Admin → Évènements → ouvrir un évènement.
2. Vérifier que le champ « Image vignette » n'apparaît plus, et que « Image principale » est toujours là.
3. Enregistrer : pas d'erreur.

### Test 2 — agenda V2
1. Sur un lieu en skin V2, ouvrir `/event/`.
2. Les cartes affichent l'image principale (ou celle de l'adresse / du lieu si l'évènement n'en a pas). Rendu inchangé.

### Test 3 — agenda faire_festival
1. Passer un lieu en skin `faire_festival`, ouvrir `/event/`.
2. Les cartes affichent l'image principale de l'évènement (repli adresse puis lieu), plus l'ancienne vignette.
3. Cliquer « voir plus » : les cartes suivantes suivent la même règle.

### Test 4 — agenda classic
1. Passer un lieu en skin `classic`, ouvrir `/event/`.
2. Les cartes affichent toujours une image (vignette existante en base, sinon vignette de l'adresse, logo du lieu ou image principale).
