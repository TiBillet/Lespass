# Formulaire dynamique sur les réservations de ressources / Dynamic form on resource bookings

**Date :** 2026-10-13
**Migration :** Oui — `booking/migrations/0002_booking_custom_form.py` (ajout du champ `Booking.custom_form`, sans reprise de données). Commande : `python manage.py migrate_schemas`

## Resume / Summary
**Quoi / What :** les questions posées sur un produit ressource (admin, onglet du formulaire dynamique) s'affichent dans le formulaire de réservation. Les réponses sont validées et enregistrées sur la réservation, par la réservation directe comme par le panier. Elles s'affichent dans « Mes réservations » et dans la fiche admin, et sortent dans l'export CSV (une colonne par question).
/ Questions set on a resource product are shown in the booking form; answers are validated and stored on the Booking (direct and cart flows), shown in "My bookings" and in the admin, and exported (one column per question).
**Pourquoi / Why :** l'admin permettait déjà de créer ces questions, mais elles n'étaient ni affichées ni enregistrées pour une réservation de ressource.
/ The admin already allowed these questions, but they were never shown nor stored for a resource booking.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/models.py` + migration `0002` | Champ `Booking.custom_form` (JSON, réponses rangées sous le libellé de la question) |
| `booking/booking_engine.py` | `validate_new_booking(..., custom_form=None)` enregistre les réponses (déjà validées par l'appelant) |
| `booking/views.py` | `_book_post` valide les réponses (422 si une question obligatoire est vide) ; `_reponses_saisies_du_formulaire` réaffiche les réponses tapées |
| `BaseBillet/views.py` | `PanierMVT.add_resource` valide les réponses (toast d'erreur), au lieu d'un `custom_form={}` en dur |
| `BaseBillet/services_commande.py` | `materialiser` transmet les réponses de l'article du panier au Booking |
| `BaseBillet/templates/commun/formulaires/champs_produit.html` | **Nouveau** partial réutilisable : les questions d'un produit (6 types), `prefill`, `testid_prefix`, JS des questions obligatoires (choix multiple, interrupteur) |
| `booking/templates/booking/partials/book_form.html` | Inclut le partial dans `#booking-form` (réservation directe et boutons du panier) |
| `pages/templates/pages/{V2,classic}/vues/compte/bookings.html` | Accordéon des réponses sous chaque réservation |
| `pages/templates/pages/{V2,classic}/vues/compte/partials/custom_form_accordion.html` | Identifiants génériques (`accordion_prefix`, `resa.uuid` ou `resa.pk`) : rendu inchangé pour les réservations d'événement |
| `Administration/admin/resources.py` + `Administration/templates/admin/booking/custom_form.html` | Fiche admin : réponses en tableau, JSON brut retiré du formulaire |
| `Administration/importers/resources_bookings_exporters.py` | Export : une colonne par question, dans l'ordre d'affichage, réponses orphelines à la fin |
| `tests/pytest/test_booking_formulaire_personnalise.py` | 15 tests (2 parcours, refus, partial, compte, admin, export) |
| `tests/e2e/test_booking_formulaire_dynamique.py` | 2 tests navigateur (réservation directe + compte, panier + admin) |

**TODO :** les formulaires billet (`commun/formulaires/reservation.html`) et adhésion (`commun/adhesion/form.html`) ont encore chacun leur copie du balisage des questions. Les brancher sur `champs_produit.html` (`testid_prefix="booking"` / `"membership"`) laissera une seule copie.

**Hors périmètre, à corriger à part :**
- `booking/views/book.html` n'existe pas : la page de réservation chargée sans HTMX lève `TemplateDoesNotExist`.
- Dans `compte/bookings.html` (les deux skins), la carte des réservations passées a un attribut `class` qui ne se ferme pas : son `data-testid` est avalé dans la classe.

---

## Comment tester (a la main) / Manual test
### Test 1 — réservation directe
1. Admin → Produits ressources → un produit → onglet du formulaire dynamique : ajouter une question texte obligatoire et un choix multiple obligatoire.
2. Front : page de la ressource → cliquer un créneau → le panneau affiche les questions sous le nom.
3. Cliquer « Payer maintenant » sans cocher de case : message sous le choix multiple, rien n'est envoyé.
4. Laisser le texte vide (retirer l'attribut `required` à l'inspecteur) : le serveur renvoie le formulaire avec le libellé de la question en erreur, les autres réponses sont toujours là.
5. Tout remplir : réservation créée. « Mes réservations » → déplier « Answers to the reservation form » : les réponses s'affichent.

### Test 2 — panier
1. Même créneau, « Ajouter au panier » avec les réponses → badge du panier à 1.
2. Sans réponse obligatoire : toast d'erreur, le panier ne bouge pas.
3. Payer le panier : la réservation porte les réponses (fiche admin).

### Test 3 — admin et export
- Admin → Réservations → la fiche : tableau « Custom form answers », pas de champ JSON.
- Exporter en CSV : une colonne par question après « Réservé le » ; une réservation sans réponse donne des cases vides.

### Verifs DB / Playwright
- `poetry run pytest tests/pytest/test_booking_formulaire_personnalise.py -v`
- `make e2e-visible panier` (contient `test_booking_formulaire_dynamique.py`)
- En base : `Booking.objects.exclude(custom_form=None).values_list('pk', 'custom_form')`
