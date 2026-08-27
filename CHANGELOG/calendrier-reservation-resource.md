# Calendrier de réservation de ressources avec confirmation inline
/ Resource booking calendar with inline confirmation

## Ce qui a été fait / What was done

Intégration des maquettes `booking/templates/temp/calendrier_panier_tibillet_journee_complete.html`
et `booking/templates/temp/calendrier-panier-mobile.html` dans la vue de détail d'une ressource.

The mockups `booking/templates/temp/calendrier_panier_tibillet_journee_complete.html` and
`booking/templates/temp/calendrier-panier-mobile.html` are integrated into the resource detail view.

### Modifications / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/views.py` | `resource_page` : structure les créneaux par semaine/jour via `_build_calendar_weeks()`, par jour individuel via `_build_mobile_days()`, et fournit les ressources via `_get_resource_choices()`. `book` : retourne le partial HTMX quand `request.htmx`. |
| `booking/templates/booking/views/resource.html` | Calendrier responsive : version desktop (navigation par semaine) et version mobile (sélecteur de ressource, barre de jours, navigation par jour avec 1 jour à la fois). Sans panier. |
| `booking/templates/booking/partials/book_form.html` | Formulaire de confirmation chargé dans SweetAlert2. |
| `booking/doc/plan-calendrier-resource-v0.2.md` | Plan d'intégration. |

## Tests à réaliser / Tests to run

### Test 1 : Affichage desktop
1. Ouvrir `/booking/<pk>/resource/` pour une ressource avec des créneaux.
2. Vérifier que la grille desktop s'affiche avec les jours de la semaine et les heures.
3. Vérifier que la navigation par semaine fonctionne (précédent/suivant).
4. Vérifier que les créneaux libres sont en vert et cliquables.
5. Vérifier que les créneaux complets sont grisés et non cliquables.

### Test 2 : Affichage mobile
1. Ouvrir `/booking/<pk>/resource/` sur une fenêtre < 768px de large (ou via DevTools).
2. Vérifier que le sélecteur de ressource est visible en haut.
3. Vérifier que la barre de jours affiche tous les jours disponibles.
4. Vérifier que la grille affiche 1 colonne (le jour actif).
5. Vérifier que les flèches précédent/suivant changent bien de jour.
6. Vérifier qu'un clic sur un jour dans la barre affiche le jour correspondant.

### Test 3 : Sélecteur de ressource
1. En mobile, ouvrir le sélecteur de ressource.
2. Choisir une autre ressource.
3. Vérifier que la page redirige vers `/booking/<pk>/resource/` de la ressource choisie.

### Test 4 : Confirmation inline
1. Cliquer sur un créneau libre (desktop ou mobile).
2. Vérifier que SweetAlert2 s'ouvre avec le formulaire de confirmation.
3. Vérifier que le créneau sélectionné est bien affiché.
4. Choisir un tarif et confirmer.
5. Vérifier que la réservation est créée et que la redirection vers `my_bookings` ou Stripe checkout a lieu.

### Test 5 : Cas non connecté
1. Se déconnecter.
2. Ouvrir `/booking/<pk>/resource/`.
3. Le calendrier doit s'afficher.
4. Au clic sur un créneau libre, la popup doit afficher le formulaire, mais la soumission doit rediriger vers la connexion (comportement existant de `book`).

### Test 6 : Erreur de validation
1. Ouvrir le formulaire de confirmation.
2. Soumettre avec un nombre de créneaux invalide (ex: 0 ou supérieur au max).
3. Vérifier que la popup affiche les erreurs sans fermer.

### Test 7 : Responsive
1. Afficher la page sur desktop (> 768px) : vérifier la grille desktop, pas la version mobile.
2. Réduire la fenêtre en mobile (< 768px) : vérifier la version mobile avec 1 colonne et la barre de jours.
3. Ré-agrandir : revenir à la grille desktop.

## Compatibilité / Compatibility

- Pas de migration nécessaire.
- Les templates `temp/` ne sont pas supprimés et restent disponibles comme référence visuelle.
- La page `booking/views/book.html` reste fonctionnelle comme fallback no-JS.
- Les tests de `booking/tests/` échouent actuellement sur une référence préexistante à
  `Resource.name` ; ce n'est pas lié à cette feature.

## Commandes utiles / Useful commands

```bash
# Vérifier la syntaxe Django
poetry run python manage.py check

# Vérifier la compilation des templates
poetry run python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')
django.setup()
from django.template import engines
for name in ['booking/views/resource.html', 'booking/partials/book_form.html']:
    engines['django'].get_template(name)
    print(f'Template {name} OK')
"

# Workflow i18n
poetry run python manage.py makemessages -l fr
poetry run python manage.py makemessages -l en
poetry run python manage.py compilemessages
```
