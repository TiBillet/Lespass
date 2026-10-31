# Événements visibles dans le planning bénévole et sur le calendrier des ressources / Events shown on the volunteer planning and the resource calendar

**Date :** 2026-10-31
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Planning bénévole (`/booking/benevolat/<slug>/`) : une ligne « Au programme » donne, pour chaque colonne de jour, les horaires et le titre des événements du lieu. Sur mobile, le récap est sous le titre du jour. La ligne n'existe que si un jour affiché a un événement.
  / Volunteer planning: an "Au programme" row gives each day's event times and titles (below the day title on mobile).
- Calendrier d'une ressource (`/booking/<pk>/resource/`) : tout le monde voit l'événement qui occupe un créneau, dans la case et dans la fenêtre de détail. Le public voit la jauge seulement si `Event.show_gauge` est actif, les horaires seulement si `Event.show_time` est actif.
  / Resource calendar: everyone sees the event occupying a slot; gauge and times follow the event's public settings.
- Restent réservés aux admins du lieu : les réservations (nom, e-mail, statut) et les événements non publiés. Le créneau d'un événement non publié reste « complet », sans titre.
  / Bookings and unpublished events remain admin-only.

**Pourquoi / Why :** les bénévoles voient ce qui se passe le jour où ils s'inscrivent, et un créneau complet dit pourquoi il l'est. / Volunteers see what happens on the day they sign up; a full slot says why.

**Performance / Performance :** une requête de plus par page, quel que soit le nombre d'événements ; aucune pour un admin sur le calendrier. Un test le vérifie sur chaque page. / One extra query per page, whatever the number of events.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/benevolat.py` | `jours_ou_afficher_un_evenement`, `horaires_d_un_evenement`, `evenements_par_jour_de_la_semaine` ; `construire_le_planning` ajoute `evenements` à chaque jour |
| `booking/templates/booking/benevolat/partials/evenements_du_jour.html` | Nouveau : la liste des événements d'un jour |
| `booking/templates/booking/benevolat/partials/grille.html`, `jours_mobile.html`, `zone.html` | Ligne « Au programme », récap mobile |
| `booking/static/booking/css/benevolat.css` | Styles du récap |
| `booking/views.py` | `_ajouter_les_infos_aux_creneaux` (ex `_ajouter_les_infos_admin_aux_creneaux`) : appelée pour tout le monde, filtre public |
| `booking/booking_engine.py` | `DisplaySlot.infos_creneau` (ex `infos_admin`) |
| `booking/templates/booking/partials/infos_creneau.html` | Renommé depuis `infos_creneau_admin.html` ; jauge et horaires conditionnels |
| `booking/templates/booking/partials/resource_semaine.html`, `views/resource.html` | Renommages `infos-admin` → `infos` (classes CSS, `data-testid`) |
| `tests/pytest/test_benevolat_semaines.py`, `test_booking_calendrier_semaine.py` | Nouveaux tests, test visiteur réécrit |

**i18n :** nouvelles chaînes `Au programme` et `Événement` / `Événements`. Workflow i18n à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

### Test 1 — planning bénévole
1. Ouvrir `/booking/benevolat/bar-associatif/` sur une semaine où un jour a un besoin et un événement.
2. La ligne « Au programme » montre « 20h–23h » puis le titre.
3. Événement sans date de fin : « 20h » seul. Événement avec « Afficher l'heure » décoché : le titre seul.
4. Concert 21h–2h : il n'apparaît que le jour de son début.
5. Événement de plusieurs jours : il apparaît chaque jour couvert, avec « 24/10 18h → 26/10 23h ».
6. Événement non publié, archivé ou de catégorie Action : absent. Événement un jour sans besoin : absent (pas de colonne).
7. Téléphone : le récap est sous le titre du jour.

### Test 2 — calendrier d'une ressource
1. Admin → un événement publié : « Ressource bloquée » = une ressource, avec date de fin.
2. En navigation privée, ouvrir la ressource sur cette semaine : le titre est dans la case, le clic ouvre la fenêtre (titre, horaires). Pas de jauge.
3. Cocher « Afficher la jauge » sur l'événement : la jauge apparaît.
4. Dépublier l'événement : le créneau reste complet, sans titre, en navigation privée. Connecté en admin, le titre reste visible.
5. Réserver un autre créneau : en navigation privée, ni nom ni e-mail dans le code source. En admin, ils y sont.

### Verifs DB / Playwright
- `docker exec -w /DjangoFiles lespass_django poetry run pytest tests/pytest/test_benevolat_semaines.py tests/pytest/test_booking_calendrier_semaine.py -q` (67 verts).
- Vérifié par mutation : les filtres de visibilité (`published`, `archived`, `ACTION`, réservations, jauge, horaires), le fuseau, les règles de jours et le filtre des événements commencés la semaine d'avant font échouer un test s'ils sont retirés. Les autres bornes de semaine (`datetime__lt`, `end_datetime__gt`) ne limitent que le volume lu, elles ne changent pas l'affichage.
- Pas de test E2E : affichage serveur et `popover` natif du navigateur. Contrôle visuel fait en anonyme, desktop et mobile.
