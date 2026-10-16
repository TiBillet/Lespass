# Fiche de détail d'un évènement dans l'admin / Admin event detail page

**Date :** 2026-10-13
**Migration :** Non

## Resume / Summary
**Quoi / What :** le bouton « Voir » de la liste des évènements (admin) affiche une fiche avec les compteurs de billets (valides / jauge avec barre de progression, scannés, en attente, annulés), le tableau des billets et les réponses aux formulaires dynamiques (une colonne par question, une ligne par réservation). Les tableaux et badges sont les composants Unfold. Des filtres HTMX permettent de chercher par email, par statut de billet et par réponse à chaque question. Pas de colonne « nom » : si un lieu en a besoin, c'est une question de son formulaire. La fiche est une vraie page de l'admin (lien classique) : le bouton « retour » du navigateur fonctionne, et les filtres restent dans l'adresse. Un bouton « Voir le détail » est ajouté sur la fiche d'un évènement, à côté de « Copier l'URL publique » (visible seulement si l'évènement a une URL publique). La page est réservée aux admins du lieu.
/ The "Voir" button of the admin event list shows ticket counters, the tickets table and the dynamic form answers (one column per question, one row per reservation), using Unfold components. HTMX filters: email, ticket status, answer to each question. No "name" column: a venue that needs it adds a form question. Full admin page (plain link): browser back works and filters stay in the URL. A "see details" button is added on the event change form, next to "Copy the public url" (only shown when the event has a public URL). Tenant admins only.

**Pourquoi / Why :** voir d'un coup d'œil qui vient et ce que les gens ont répondu, et retrouver vite une personne ou un groupe (ex : tous les végans), sans ouvrir chaque réservation.
/ See at a glance who is coming and what people answered, and quickly find a person or a group, without opening each reservation.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `EventMVT.admin_show_event_detail` (contexte, filtres, choix du gabarit selon `HX-Target`) ; `get_permissions` réserve cette action à `TenantAdminPermission` ; aides `EventDetailFiltersSerializer`, `_event_detail_form_questions`, `_read_question_filters`, `_reservation_matches_filters`, `_build_tickets_table`, `_build_form_answers_table` |
| `Administration/admin_tenant.py` | `EventAdmin.event_detail_page_button` : lien classique (plus de HTMX vers #content) |
| `Administration/templates/admin/event/change_form.html` | Bouton « Voir le détail » à côté de « Copier l'URL publique » (dans le bloc `{% if original.full_url %}`) ; libellés passés en `{% translate %}` |
| `Administration/templates/admin/reservation/event_detail_page.html` | Nouveau : la page complète (gabarit de l'admin) qui inclut la fiche |
| `Administration/templates/admin/reservation/event_detail.html` | Le contenu de la fiche : en-tête, compteurs, formulaire de filtres (`hx-replace-url`) |
| `Administration/templates/admin/reservation/partials/event_detail_results.html` | Nouveau : les deux tableaux Unfold, renvoyés seuls quand un filtre change |
| `tests/pytest/test_admin_fiche_detail_evenement.py` | 16 tests : affichage, chaque filtre, filtre invalide ignoré, partial HTMX, échappement, accès refusé, page complète, filtres dans l'adresse, boutons d'accès |

---

## Comment tester (a la main) / Manual test
### Test 1 — scenario nominal
1. Admin > Évènements, cliquer « Voir » sur « Atelier cuisine partagée (démo formulaire) » (tenant lespass).
2. La fiche remplace la zone principale : nom, date, 4 compteurs (16 / 20 avec la barre de jauge).
3. Le tableau « Billets » : email (ouvre la fiche du billet), tarif, statut en badge Unfold, paiement, montant, date. Pas de colonne nom.
4. Le tableau « Réponses aux formulaires » : une colonne par question. L'email ouvre la fiche de la réservation.

### Test 2 — filtres
- Taper « lea » dans Email : après ~400 ms, seuls les billets / réponses de Léa restent, et une phrase indique « 1 réservation(s) et 2 billet(s) correspondent ».
- « Régime alimentaire » = Végan : 2 réservations (Hugo, Manon).
- « Ateliers souhaités » = Pain (choix multiple) : 5 réservations.
- « J'accepte d'être pris·e en photo » = Non : 4 réservations.
- « Allergies » contient « glu » : 2 réservations.
- « Statut du billet » = Valide et scanné : 4 billets (le tableau des réponses n'est pas filtré par statut).
- Les compteurs du haut ne changent jamais (ils comptent tout l'évènement).
- « Réinitialiser » : toute la fiche revient sans filtre.
- Filtrer (ex : Végan), cliquer un email pour ouvrir le billet, puis « retour » du navigateur : la fiche revient avec le même filtre.

### Test 3 bis — navigation
- Depuis la liste : « Voir » → fiche ; « retour » du navigateur → la liste.
- Depuis la fiche d'un évènement : bouton « Voir le détail : billets et réponses aux formulaires », à côté de « Copier l'URL publique » → fiche.
- Page d'ajout d'un évènement, ou évènement sans URL publique : pas de bouton.
- Rafraîchir la fiche (F5) ou l'ouvrir dans un nouvel onglet : la page s'affiche avec la barre latérale de l'admin.

### Test 3 — cas limites
- Évènement sans billet : « Aucun billet pour cet évènement. »
- Produits sans formulaire : « Les produits de cet évènement n'ont pas de formulaire. »
- Filtres sans résultat : « Aucun billet ne correspond aux filtres. » / « Aucune réservation ne correspond aux filtres. »
- Question supprimée après des réponses : elle garde sa colonne, en fin de tableau, avec un filtre texte.
- Ouvrir `/event/<uuid>/admin_show_event_detail/` déconnecté : 403.

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_admin_fiche_detail_evenement.py"`
- E2E à écrire : clic sur « Voir », choisir un filtre, vérifier que `#event-detail-results` se met à jour.
