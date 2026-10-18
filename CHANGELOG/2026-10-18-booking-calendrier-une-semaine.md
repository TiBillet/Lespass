# Calendrier d'une ressource : une semaine à la fois / Resource calendar: one week at a time

**Date :** 2026-10-18
**Migration :** Non

## Resume / Summary
**Quoi / What :** la page de réservation d'une ressource (`/booking/<pk>/resource/`) calcule et rend **une semaine** (lundi → dimanche). « Semaine précédente / suivante » recharge la zone seule en htmx ; l'adresse porte `?semaine=AAAA-MM-JJ` (n'importe quel jour, ramené à son lundi). Par défaut : la semaine en cours, même vide (« Aucun créneau cette semaine. »). Une semaine après l'horizon donne la dernière semaine réservable. Le créneau qui finit à minuit tient désormais dans la grille. Les templates orphelins `resource_day*.html` sont supprimés.
/ The resource booking page computes and renders ONE week; week links reload the zone with htmx and push `?semaine=`. Default: current week. Midnight-ending slots now fit the grid. Orphan templates removed.

**Pourquoi / Why :** la page rendait tout l'horizon d'un coup, deux fois (desktop + mobile) : 2 Mo à 90 jours, 8,7 Mo à 550 jours (onglet figé). Spec : `TECH_DOC/SESSIONS/TODO/BOOKING-pagination-htmx-calendrier.md` (relue par Opus, validée par le mainteneur).
/ The page rendered the whole horizon twice: 2 MB at 90 days, 8.7 MB at 550 days.

Mesures (salle de résidence et concert, horizon 90 jours, base de dev) :

| | Avant | Après |
|---|---|---|
| Page (semaine en cours) | 2 Mo | ~118 Ko |
| Zone d'une semaine entière (htmx) | — | ~250 Ko brut, ~93 Ko sans les espaces d'indentation |

Points notables :
- la fenêtre de calcul est construite au **fuseau du lieu** : le moteur (`generate_theoretical_slots`) lit le fuseau dans `window.start` ; `timezone.now()` brut (UTC) aurait décalé les créneaux de la semaine en cours ;
- une réservation de plusieurs créneaux d'affilée s'arrête au dimanche minuit (`data-group-end` = fin du groupe dans la semaine), décision du mainteneur ;
- tout le JS est délégué sur `#booking-calendar` (la page est rejouée par `hx-target="body"` depuis les cartes) ; aucun `<script>` dans le partial ;
- les sélecteurs de ressource sont sortis des cartes : styles, sélecteurs, zone et légende sont rendus sans condition ; l'état vide global « Aucun créneau disponible prochainement. » disparaît.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/views.py` | `_semaine_affichee()` (choix de la semaine, fenêtre au fuseau du lieu) ; `resource_page()` calcule une semaine et rend la zone seule si `HX-Target: booking-calendrier-semaine` ; bug de minuit dans `_build_calendar_weeks()` / `_build_mobile_days()` |
| `booking/templates/booking/partials/resource_semaine.html` | Nouveau : navigation de semaine + grille desktop + jours mobiles d'une semaine |
| `booking/templates/booking/views/resource.html` | Structure sans condition, sélecteurs sortis des cartes, inclusion du partial ; JS délégué sur `#booking-calendar`, focus sur le titre après un changement de semaine, état mobile initial rendu côté serveur |
| `booking/templates/booking/views/resource_day.html`, `booking/templates/booking/partials/resource_day_calendar.html` | Supprimés (orphelins depuis `2c99b791`) |
| `tests/pytest/test_booking_calendrier_semaine.py` | Nouveau : 15 tests (dont bornes des liens de semaine, semaine vide demandée, coupure au dimanche minuit) |
| `tests/e2e/test_booking_calendrier_semaine.py` | Nouveau : 3 tests (htmx sans rechargement + retour arrière, mobile 375 px, clic sur un créneau de la 2ᵉ semaine) |
| `TECH_DOC/SESSIONS/TODO/BOOKING-pagination-htmx-calendrier.md` | Spec |

Nouvelle chaîne à traduire (msgid FR) : « Aucun créneau cette semaine. ». Le workflow i18n est à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

### Test 1 — desktop
1. Ouvrir `/booking/` → « Salle de résidence et concert » (fixtures de démo).
2. La semaine en cours s'affiche, titre « 12 – 18 octobre » par exemple, sans flèche « précédente ».
3. « Semaine suivante » : la zone change sans recharger, l'adresse porte `?semaine=`, le titre change.
4. Les soirées des jours de concert sont « Complet » ; la soirée 18 h – 00 h finit sur la ligne 24:00.
5. Retour arrière du navigateur : la semaine d'avant revient.
6. Sur la dernière semaine réservable, la flèche « suivante » a disparu.

### Test 2 — mobile (375 px)
1. Barre des 7 jours de la semaine, premier jour actif, flèche « jour précédent » grisée.
2. Les flèches de jour restent dans la semaine ; « Semaine suivante » (au-dessus) change de semaine.
3. Pas de défilement horizontal de la page.

### Test 3 — réserver
1. Connecté, semaine suivante, clic sur un créneau libre : le formulaire s'ouvre dans le panneau.
2. Ajouter au panier, recharger la page sur la même semaine (`?semaine=` garde la semaine) : le créneau est « Panier ».

### Test 4 — adresse
- `?semaine=abc` ou une date passée → semaine en cours ; `?semaine=2099-01-05` → dernière semaine réservable.

### Verifs automatiques
- `make test ARGS="tests/pytest/test_booking_calendrier_semaine.py"`
- `make e2e ARGS="tests/e2e/test_booking_calendrier_semaine.py"`
- Vérifiés par mutation : fenêtre en UTC brut, correction de minuit (desktop puis mobile), rendu de la zone (`HX-Target`), borne du lien « suivante », fenêtre prolongée au-delà du dimanche minuit, focus / flèche de jour / clic délégué en JS.
- Relu par un agent Fable le 2026-10-18 : aucun bloquant, aucune régression ; ses corrections (tests des bornes, semaine vide, coupure au dimanche minuit ; deux commentaires) sont intégrées.

### Limite connue
Le bouton « Retour » en haut de la page fait `history.back()`. Chaque changement de semaine ajoute une entrée d'historique (`hx-push-url`) : après N semaines, « Retour » remonte N semaines avant de quitter la page.
