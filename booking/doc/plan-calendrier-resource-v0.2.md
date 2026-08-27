# Plan d'integration — Calendrier resource v0.2
/ Integration plan — Resource calendar v0.2

**Date / Date:** 2026-07-10
**Auteur / Author:** opencode
**Statut / Status:** approuve pour implementation / approved for implementation

> **Note de session / Session note:**
> Nouvelle session de travail le 2026-07-13 — passage du calendrier mobile de 2 jours à 1 jour par page.
> / New work session on 2026-07-13 — mobile calendar changed from 2 days to 1 day per page.

## Contexte / Context

Les templates `booking/templates/temp/calendrier_panier_tibillet_journee_complete.html`
et `booking/templates/temp/calendrier-panier-mobile.html` sont des maquettes statiques
d'un calendrier de reservation. L'objectif est de les transformer en template dynamique
pour la vue `resource_page` du module booking, avec confirmation inline via SweetAlert2.

The templates `booking/templates/temp/calendrier_panier_tibillet_journee_complete.html`
and `booking/templates/temp/calendrier-panier-mobile.html` are static mockups of a booking
calendar. The goal is to turn them into a dynamic template for the booking module's
`resource_page` view, with inline confirmation via SweetAlert2.

## Decisions de conception / Design decisions

1. **Vue cible / Target view:** `resource_page` dans `booking/views.py`.
   Elle calcule deja les creneaux avec `compute_slots(resource)` et `annotate_slots_for_display()`.
   / It already computes slots with `compute_slots(resource)` and `annotate_slots_for_display()`.

2. **Template unique responsive / Single responsive template:**
   On fusionne les deux maquettes en un seul `resource.html` qui s'adapte a la largeur
   (desktop: grille 5 jours, mobile: grille 1 jour + navigation par jour).
   / We merge both mockups into one `resource.html` that adapts to width
   (desktop: 5-day grid, mobile: 1-day grid + day navigation).

3. **Pas de panier integre / No embedded cart:**
   Les blocs "Mon panier" des maquettes sont supprimes. Le panier existe deja sous
   une autre forme dans le projet.
   / The "My cart" blocks from the mockups are removed. The cart already exists
   elsewhere in the project.

4. **Confirmation inline / Inline confirmation:**
   Au clic sur un creneau libre, SweetAlert2 ouvre un popup qui charge le formulaire
   de confirmation via HTMX depuis la vue `book`.
   / Clicking a free slot opens a SweetAlert2 popup that loads the confirmation form
   via HTMX from the `book` view.

5. **Donnees dynamiques sans JSON bootstrap / Dynamic data without JSON bootstrap:**
   Les cellules sont generees cote serveur. Les informations necessaires au clic
   (datetime, group_end, duree, capacite) sont dans les attributs `data-*`.
   / Cells are server-rendered. Click data (datetime, group_end, duration, capacity)
   lives in `data-*` attributes.

6. **Fallback no-JS / No-JS fallback:**
   La page `book.html` reste fonctionnelle. Si JavaScript est desactive, les liens
   directs vers `booking-book` continuent de marcher.
   / The `book.html` page remains functional. If JavaScript is disabled, direct links
   to `booking-book` still work.

## Fichiers modifies et crees / Modified and created files

| Fichier / File | Action | Description |
|---|---|---|
| `booking/templates/booking/views/resource.html` | Modifier / Modify | Remplacer la liste de creneaux par le calendrier responsive. |
| `booking/templates/booking/partials/book_form.html` | Creer / Create | Formulaire de confirmation affiche dans SweetAlert2. |
| `booking/views.py` | Modifier / Modify | Adapter `resource_page` ; ajuster `book` pour retourner un partial HTMX quand `request.htmx`. |
| `booking/urls.py` | Aucun / None | Les URLs existantes restent valides. |

## Flux detaille / Detailed flow

### 1. Affichage du calendrier / Calendar display

```
GET /booking/<pk>/resource/
  -> BookingViewSet.resource_page()
       -> compute_slots(resource) + annotate_slots_for_display()
       -> render resource.html
```

Le template affiche :
- Un selecteur de ressource (lecture seule, ou navigation si plusieurs ressources).
- Une navigation par semaine (fleches + libelle "Semaine du X au Y").
- Une grille de creneaux colorée selon l'etat.
- Une legende : Libre / Occupe / Selectionne.

The template shows:
- A resource selector (read-only, or navigation if multiple resources).
- Week navigation (arrows + "Week of X to Y" label).
- A colored slot grid based on state.
- A legend: Free / Busy / Selected.

### 2. Etats des cellules / Cell states

- **Libre / Free:** `remaining_capacity > 0` → cliquable, ouvre la popup.
- **Occupe / Busy:** `remaining_capacity == 0` → non cliquable.
- **Passe / Past:** avant `timezone.now()` → non cliquable.

### 3. Clic sur un creneau libre / Click on a free slot

```
onclick:
  -> Swal.fire({ html: '<div id="booking-popup-content"></div>', ... })
  -> htmx.ajax('GET', '/booking/<pk>/book/?start_datetime=...&group_end=...', {
       target: '#booking-popup-content',
       swap: 'innerHTML'
     })
```

La vue `book` detecte `request.htmx` et retourne `booking/partials/book_form.html`
au lieu de la page complete `booking/views/book.html`.

The `book` view detects `request.htmx` and returns `booking/partials/book_form.html`
instead of the full `booking/views/book.html` page.

### 4. Formulaire de confirmation / Confirmation form

Le partial contient :
- Affichage du creneau selectionne.
- Liste des tarifs disponibles (`resource.product.prices.all`).
- Nombre de creneaux si plusieurs sont disponibles consecutivement.
- Champs `firstname` et `lastname`.
- Champs caches : `start_datetime`, `group_end`, `resource`, `price`.
- Bouton de confirmation.

The partial contains:
- Display of the selected slot.
- List of available prices (`resource.product.prices.all`).
- Slot count if several consecutive slots are available.
- `firstname` and `lastname` fields.
- Hidden fields: `start_datetime`, `group_end`, `resource`, `price`.
- Confirmation button.

### 5. Soumission / Submission

```
Formulaire / Form -> hx-post="/panier/add/resource/" (ou booking-book POST)
  -> Si succes / If success: Swal.close() + redirection checkout ou my_bookings
  -> Si erreur / If error: re-render du formulaire dans la popup avec les erreurs
```

## Gestion des erreurs / Error handling

- Si le serializer est invalide : retour 422 avec le partial contenant les erreurs.
- Si le creneau est pris en cours de validation (race condition) : message dans la popup.
- Si l'utilisateur n'est pas connecte : le lien de connexion est propose dans la popup.

## Accessibilite et i18n / Accessibility and i18n

- Tous les textes utilisent `{% translate %}` ou `{% blocktrans %}`.
- Chaque element interactif a un `data-testid` au format `booking-<element>-<context>`.
- Les icones decoratives ont `aria-hidden="true"`.
- Les zones dynamiques (grille, popup) ont `aria-live="polite"`.
- Les groupes de boutons ont `role="group"` et `aria-label`.

## Tests a realiser / Tests to run

```bash
# Tests unitaires du moteur et des vues
# / Unit tests for engine and views
docker exec lespass_django poetry run pytest booking/tests/ -v

# Verifications de style
# / Style checks
docker exec lespass_django poetry run ruff check booking/views.py
```

## Notes / Notes

- On ne supprime pas les templates `temp/` ; on les garde comme reference visuelle.
- On ne modifie pas `booking_engine.py` ; on reutilise `compute_slots` et `annotate_slots_for_display`.
- On suit le skill djc : ViewSet explicite, serializers DRF, HTMX server-rendered, pas de JSON bootstrap.
