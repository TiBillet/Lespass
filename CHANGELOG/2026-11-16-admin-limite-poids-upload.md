# Admin : un fichier trop lourd est refusé avant l'envoi, le formulaire est gardé / Admin: a too heavy file is rejected before sending, the form is kept

**Date :** 2026-11-16
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Nouveau script `static/js/admin_limite_upload.js`, chargé sur toutes les pages de l'admin (`UNFOLD["SCRIPTS"]`).
- Dès qu'un fichier est choisi, le script additionne le poids de tous les fichiers du formulaire. Au-delà de 11,5 Mo (limite nginx de 12 Mo, moins 0,5 Mo de marge pour les champs texte), il vide le champ, remet le libellé du champ comme au chargement (sur une fiche existante : l'adresse de l'image enregistrée), affiche un message rouge sous le champ (`role="alert"`), et ne touche pas au reste du formulaire.
- Message en français ou en anglais selon la langue de l'admin.

/ New admin script: when a file is chosen, it sums the weight of every file of the form. Over 11.5 MB (nginx 12 MB limit minus a margin) it empties the field and shows a message under it; the rest of the form is untouched.

**Pourquoi / Why :** nginx refuse toute requête de plus de 12 Mo (`client_max_body_size 12M`) avec sa propre page « 413 Request Entity Too Large ». Django ne reçoit rien et ne peut pas renvoyer le formulaire : tout ce qui avait été saisi était perdu.
/ nginx answers its own 413 page above 12 MB; Django never sees the request, so the filled form was lost.

**Limites nginx vérifiées / Checked nginx limits :** `12M` dans `nginx_prod/lespass_prod.conf` (`location /`), `nginx_prod/lespass_bascule.conf` (niveau serveur) et `nginx/lespass_dev.conf`. Si cette valeur change, changer `LIMITE_NGINX_EN_OCTETS` dans le script.

**Textes du message :** écrits en français et en anglais dans le script, selon la langue de l'admin (`<html lang>`). Le projet n'a pas de catalogue de traduction JavaScript.

**Déploiement :** fichier statique nouveau → `collectstatic` nécessaire.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `static/js/admin_limite_upload.js` | Nouveau script |
| `TiBillet/settings.py` | Ajout du script dans `UNFOLD["SCRIPTS"]` |
| `tests/e2e/test_admin_limite_upload.py` | 5 tests E2E (nouveau, famille `admin`) |

---

## Comment tester (a la main) / Manual test
### Test 1 — fichier trop lourd
1. Admin → Agenda et Billetterie → Évènements → Ajouter.
2. Saisir un nom.
3. Choisir une image de plus de 12 Mo dans « Image principale ».
4. Attendu : message rouge « Fichier trop lourd (… Mo)… Le fichier a été retiré, le reste du formulaire est intact. » ; le champ image est vide ; le nom est toujours là.

### Test 2 — plusieurs fichiers dont le total dépasse
1. Choisir une image de 8 Mo dans « Image principale », puis 6 Mo dans « Ajouter des images ».
2. Attendu : le second choix est refusé, le message indique « déjà choisis dans d'autres champs : 8 Mo ».

### Test 3 — fichier léger
1. Choisir une image de 1 Mo : aucun message, le fichier est gardé.

### Test 4 — fiche existante avec une image
1. Ouvrir un évènement qui a déjà une image principale.
2. Choisir une image de plus de 12 Mo.
3. Attendu : message rouge ; le cadre du champ affiche toujours l'adresse de l'image enregistrée ; « Enregistrer » garde l'ancienne image.

### Verifs automatiques
- `make e2e admin`, ou : `docker exec lespass_django poetry run pytest tests/e2e/test_admin_limite_upload.py -q`
