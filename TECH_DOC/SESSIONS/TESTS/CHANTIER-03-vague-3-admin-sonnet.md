# CHANTIER 03 — Vague 3 : specs admin migrés par agents Sonnet

Statut : ✅ TERMINÉ (2026-06-11)

## Optimisation de coût vs vague 2

| | Vague 2 | Vague 3 |
|---|---|---|
| Agents | 16 (2 par spec : conversion + vérif) | **8 (1 par spec, fait tout)** |
| Modèle | hérité de la session (Fable) | **Sonnet** (`model: 'sonnet'` sur `agent()`) |
| Lectures par agent | conftest 850 lignes + PIEGES.md | **cheat-sheet dans le prompt** (fixtures + pièges) |
| Tokens agents | ~917k | **~560k** (pour 8 specs admin plus complexes) |

## Résultat : 8/8 verts (13 tests Python)

| Spec TS | Fichier Python | Tests | Verdict |
|---|---|---|---|
| 26-admin-membership-custom-form-edit | `test_admin_membership_custom_form_edit.py` | 1 | ✅ |
| 32-admin-credit-note | `test_admin_credit_note.py` | 1 | ✅ |
| 33-admin-ajouter-paiement | `test_admin_ajouter_paiement.py` | 2 | ✅ |
| 34-admin-cancel-membership | `test_admin_cancel_membership.py` | 2 | ✅ |
| 35-admin-membership-list-status | `test_admin_membership_list_status.py` | 3 | ✅ premier coup |
| 37-admin-adhesions-obligatoires-m2m | `test_admin_adhesions_obligatoires_m2m.py` | 1 | ✅ premier coup |
| 38-event-adhesion-obligatoire-check | `test_event_adhesion_obligatoire_check.py` | 1 | ✅ |
| 39-admin-reservation-cancel | `test_admin_reservation_cancel.py` | 2 | ✅ |

Les 8 specs TS sont supprimés. Suite TS restante : 14 specs.

## Pièges découverts (à connaître pour les vagues suivantes)

1. **Playwright Python : `.first` est une propriété**, pas une méthode `.first()`
   (3 agents ont fait l'erreur — désormais dans la cheat-sheet).
2. **Locale FR + inputs number** : un `<input type="number" value="25,00">`
   (virgule, `USE_L10N`) est rejeté par le navigateur. Ne pas asserter la
   valeur pré-remplie ; `fill("25")` avec un entier.
3. **Badges Unfold en FR** : « Confirmé », « Payé en ligne », « Avoir » —
   assertions en regex FR/EN ou recherche minuscules dans `page.content()`.
4. **Inlines admin** : bouton d'ajout = `a.add-row` dans `#prices-group` /
   `#form_fields-group` (le texte du lien est traduit, ne pas le cibler).

## ⚠️ À vérifier par le mainteneur — formulaires imbriqués HTMX dans l'admin

L'agent du spec 34 rapporte : le panneau d'actions HTMX de la fiche admin
Membership est rendu DANS le `<form>` principal du Django admin
(`change_form_before_template`). Le HTML interdit les formulaires imbriqués —
Chromium rattache les boutons submit au formulaire externe et HTMX ne reçoit
pas le submit (depuis Playwright en tout cas ; le spec TS 33 « ajouter
paiement » passe pourtant par cette UI avec succès). Le test Python contourne
via `django_shell` (création LigneArticle CREATED→PAID équivalente).
**À vérifier à la main** : le bouton « Ajouter un paiement » de la fiche
adhésion fonctionne-t-il dans un vrai navigateur ? Si oui, le piège est
spécifique au contexte Playwright/timing ; si non, c'est un bug UI réel.

## Reste à migrer

- **Vague 4 (en cours)** : 03, 04, 05, 06, 07, 14, 17, 22, 27, 36, 43
- **Vague 5** : 25 (duplication produit), 29 (event quick create), 40 (explorer markers)
