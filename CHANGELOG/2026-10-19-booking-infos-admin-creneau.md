# Calendrier d'une ressource : qui occupe le créneau (admin) / Resource calendar: who occupies the slot (admin)

**Date :** 2026-10-19
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Sur `/booking/<pk>/resource/`, un admin du lieu voit, dans chaque créneau occupé (complet ou partiellement réservé), un libellé court : le titre de l'événement qui bloque, sinon le nom de la personne, sinon « N réservations ».
  / Venue admins see a short occupant label in every occupied slot.
- Clic sur un créneau complet (ou au panier) : tout le bloc ouvre le détail. Créneau encore réservable : le bloc ouvre toujours le formulaire de réservation, le détail passe par le bouton (i) du coin. Le détail montre : événement (titre, horaires, jauge billets valides / jauge max) et réservations (prénom et nom si présents, e-mail, horaires, statut). Fenêtre HTML native `popover`, sans JS. Desktop et mobile.
  / Clicking a full slot opens the details (whole block); bookable slots keep the booking form and use the (i) button (event: title, times, gauge; bookings: name, email, times, status). Native HTML popover, no JS.
- Visiteurs et membres non admins : rien ne change, ces infos ne sont ni calculées ni envoyées.
  / Non-admins: nothing changes, the data is neither computed nor sent.

**Pourquoi / Why :** l'admin voyait un créneau gris « complet » sans savoir qui l'occupait. / Admins saw a full slot without knowing who held it.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/booking_engine.py` | `DisplaySlot.infos_admin` (None par défaut) |
| `booking/views.py` | `resource_page` : test `is_tenant_admin` ; `_ajouter_les_infos_admin_aux_creneaux` (2 requêtes par semaine, mêmes filtres que le moteur) ; `infos_admin` transmis à la grille desktop |
| `booking/templates/booking/partials/resource_semaine.html` | Libellé court, bouton à côté du créneau (même case de grille) : tout le bloc si non réservable, sinon (i) dans le coin ; include du détail — desktop et mobile |
| `booking/templates/booking/partials/infos_creneau_admin.html` | Nouveau : la fenêtre de détail (`popover`) |
| `booking/templates/booking/views/resource.html` | CSS du libellé, du bouton et de la fenêtre |
| `tests/pytest/test_booking_calendrier_semaine.py` | 3 tests : l'admin voit, le visiteur et le membre non admin ne voient pas |

**i18n :** nouvelles chaînes (`Créneau … - …`, `Qui occupe le créneau … - …`, `Événement qui bloque la ressource`, `Jauge`, `Réservations`, `Fermer`, `%(nombre)s réservation(s)`). Workflow i18n à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

### Test 1 — admin
1. Admin → un événement : « Ressource bloquée » = une ressource, avec date de fin, la semaine prochaine.
2. Réserver un autre créneau de cette ressource (compte membre).
3. Connecté en admin du lieu : `/booking/<pk>/resource/?semaine=<lundi suivant>`.
4. Le créneau de l'événement affiche son titre, celui de la réservation le nom (ou l'e-mail).
5. Clic n'importe où sur un créneau complet : la fenêtre montre le détail. Échap, clic à côté ou la croix la ferment.
6. Ressource de capacité > 1, créneau partiellement réservé : il reste vert et cliquable (formulaire de réservation), le (i) montre les réservations déjà faites.
7. Téléphone (ou fenêtre étroite) : même chose dans la vue jour par jour.

### Test 2 — non admin
1. Même page en anonyme, puis connecté en membre simple : créneaux gris sans libellé ni (i). Aucun e-mail dans le code source.

### Verifs DB / Playwright
- `docker exec -w /DjangoFiles lespass_django poetry run pytest tests/pytest/test_booking_calendrier_semaine.py -q` (18 verts).
- Vérifié par mutation : forcer le test admin à faux ou à vrai fait échouer les nouveaux tests.
- Pas de test E2E de l'ouverture du `popover` (comportement natif du navigateur).
