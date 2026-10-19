# Réservations : image et description propres à la ressource / Booking: resource's own image and description

**Date :** 2026-10-19
**Migration :** Oui — `booking/migrations/0007_resource_img.py` (champ `Resource.img` + nettoyage `clean_html` des descriptions existantes).
`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas booking`

## Resume / Summary
**Quoi / What :**
- La ressource a sa propre image (`Resource.img`, mêmes variations que `Product.img`).
  / Resources get their own image.
- `/booking/` et `/booking/<pk>/resource/` affichent l'image et la description de la **ressource**, plus celles du produit.
  / Booking pages show the resource's image and description, not the product's.
- La description de la ressource s'édite au WYSIWYG dans l'admin ; elle est nettoyée (`clean_html`) à l'enregistrement et rendue en `|safe`.
  / WYSIWYG editor in the admin; sanitized on save, rendered with `|safe`.
- Page ressource : le sélecteur de ressource est masqué quand le lieu n'en a qu'une.
  / Resource selector hidden when there is a single resource.
- En-tête du lieu (skin V2) : le lien du site web passe sur sa propre ligne, sous l'adresse.
  / Venue header: the website link sits on its own line.

**Pourquoi / Why :** une ressource doit se présenter elle-même, indépendamment du produit qui porte ses tarifs. / A resource must present itself, independently of the product carrying its prices.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/models.py` | Champ `img` (StdImageField) sur `Resource` |
| `booking/migrations/0007_resource_img.py` | AddField + RunPython de nettoyage des descriptions existantes |
| `Administration/admin/resources.py` | `WysiwygWidget` sur les TextField + `sanitize_textfields` dans `save_model` |
| `pages/templates/cotton/V2/ressource_card.html` | Image et description de la ressource |
| `booking/templates/booking/views/resource.html` | Image et description de la ressource ; sélecteurs masqués si une seule ressource ; meta description sans balises |
| `booking/views.py` | `resource_page` : contexte `plusieurs_ressources` |
| `pages/templates/pages/V2/tenant_header.html` | Séparateur « · » retiré avant le site web |
| `pages/static/V2/css/V2.css` | `.place-id__site` en `display: block` |

---

## Comment tester (a la main) / Manual test

### Test 1 — image et description de la ressource
1. Admin → Réservations → Ressources → ouvrir une ressource.
2. La description a l'éditeur WYSIWYG. Mettre un texte en gras + une liste. Ajouter une image.
3. Enregistrer, aller sur `/booking/` : la carte montre l'image et la description de la ressource (gras et liste rendus).
4. Cliquer « Réserver » : l'en-tête de la page montre la même image et la même description.

### Test 2 — XSS
1. Dans la description (mode source si dispo, sinon via shell), mettre `<script>alert(1)</script><img src=x onerror=alert(1)>`.
2. Enregistrer : le `<script>` et le `onerror` disparaissent. Aucune alerte sur `/booking/` ni sur la page ressource.

### Test 3 — sélecteur de ressource
1. Lieu avec plusieurs ressources : `/booking/<pk>/resource/` affiche le menu « Ressource » (desktop et mobile).
2. Lieu avec une seule ressource : le menu n'apparaît pas.

### Test 4 — en-tête du lieu
1. Configuration avec adresse + site web : le site web s'affiche sous l'adresse, sans « · ».

### Verifs DB / Playwright
- Pytest : `tests/pytest/test_booking_*.py` et `booking/tests/` (214 tests verts).
- Pas de test automatique pour le cas « une seule ressource » (le tenant de test en a plusieurs).
