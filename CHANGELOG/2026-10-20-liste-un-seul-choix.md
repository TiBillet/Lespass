# Un seul choix : on ouvre directement la page / Single choice: open the page directly

**Date :** 2026-10-20
**Migration :** Non

## Resume / Summary
**Quoi / What :** `/booking/` redirige vers la page de la ressource quand le lieu n'en a qu'une. `/booking/benevolat/` redirige vers le planning quand un seul planning a des besoins à venir.
/ `/booking/` redirects to the resource page when the venue has only one. `/booking/benevolat/` redirects to the planning when only one planning has upcoming needs.

**Pourquoi / Why :** une liste d'un seul élément oblige à un clic inutile.
/ A one-item list forces a useless click.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/views.py` | `BookingViewSet.list` : redirection 302 vers `booking-resource` si une seule ressource |
| `booking/views_benevolat.py` | `BenevolatViewSet.list` : redirection 302 vers `benevolat-planning` si un seul planning à venir |
| `tests/pytest/test_listes_a_un_seul_choix.py` | 4 tests : un choix → 302, deux choix → liste |

**À savoir / Note :** avec un seul choix, le texte d'introduction de la page liste (`description_booking_page`, `description_benevolat_page`) n'est plus affiché, puisque la liste n'est plus affichée.
/ With a single choice, the list page intro text is no longer shown.

---

## Comment tester (a la main) / Manual test

### Test 1 — une seule ressource
1. Dans l'admin, ne garder qu'une ressource (ou tester sur un lieu qui n'en a qu'une).
2. Cliquer sur l'entrée « Ressources » du menu.
3. Attendu : la page calendrier de la ressource s'ouvre directement, l'URL affichée est `/booking/<uuid>/resource/`.

### Test 2 — un seul planning de bénévoles à venir
1. Ne garder qu'un planning publié avec des besoins à venir.
2. Cliquer sur l'entrée « Bénévolat » du menu.
3. Attendu : le planning s'ouvre directement, l'URL affichée est `/booking/benevolat/<slug>/`.

### Test 3 — plusieurs choix
1. Avec deux ressources (ou deux plannings à venir), cliquer sur l'entrée du menu.
2. Attendu : la liste en cartes s'affiche, comme avant.

### Verifs automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_listes_a_un_seul_choix.py -v`
