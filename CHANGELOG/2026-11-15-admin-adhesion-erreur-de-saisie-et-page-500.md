# Fiche adhésion : une erreur de saisie ne fait plus planter l'admin / Membership page: an input error no longer crashes the admin

**Date :** 2026-11-15
**Migration :** Oui — `BaseBillet/migrations/0239_alter_lignearticle_uuid.py` (`AlterField`, aucun SQL : `sqlmigrate BaseBillet 0239` affiche `(no-op)`). Commande : `manage.py migrate_schemas`.

## Résumé / Summary

**Quoi / What :**
- `LigneArticle.uuid` passe en `editable=False`. Les tableaux de lignes en lecture seule de l'admin (fiche adhésion, fiche vente) écrivent maintenant l'identifiant caché de chaque ligne.
- `@requires_csrf_token` décore `handler404` et `handler500`, et non plus `_contexte_page_erreur`.
- / `LigneArticle.uuid` becomes `editable=False`, so read-only admin inlines write each line's hidden id. `@requires_csrf_token` now decorates the error handlers, not the context helper.

**Pourquoi / Why :**
- Sentry `BILLETTERIE-COOP-W1` : enregistrer une fiche adhésion qui a des ventes, avec une saisie invalide (par exemple une date de fin sans heure), plantait sur `TypeError: conversion from NoneType to Decimal`. La fiche réaffichée ne retrouvait pas ses lignes de vente et fabriquait des lignes vides.
- Sentry `BILLETTERIE-COOP-W2` et `BILLETTERIE-COOP-W3` : la page 500 plantait à son tour (`'dict' object has no attribute 'set_cookie'`) dès que la page en erreur avait affiché un formulaire. Le visiteur recevait une erreur brute. Toute 404 ou 500 de ce type était touchée, pas seulement l'adhésion.
- / An invalid save on a membership with sales crashed instead of showing the error; the 500 page then crashed too whenever the failing page had rendered a CSRF token.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `LigneArticle.uuid` : `editable=False` |
| `BaseBillet/migrations/0239_alter_lignearticle_uuid.py` | Migration sans SQL / No-SQL migration |
| `BaseBillet/views.py` | `@requires_csrf_token` déplacé sur `handler404` et `handler500` |
| `tests/pytest/test_admin_adhesion_formulaire_invalide.py` | Nouveau : POST invalide sur la fiche adhésion → 200 |
| `tests/pytest/test_handlers_erreur.py` | Nouveau test : 404 et 500 après `get_token()` |

---

## Comment tester (à la main) / Manual test

### Test 1 — erreur de saisie sur une adhésion qui a des ventes
1. Ouvrir `https://lespass.tibillet.localhost/admin/BaseBillet/membership/1/change/` (ou toute adhésion dont le tableau « Ventes / Ligne comptables » a au moins une ligne).
2. Afficher le code source (Ctrl+U) : `lignearticles-0-uuid` doit être présent.
3. Dans « Date de fin », garder la date et effacer l'heure. Cliquer sur « Enregistrer ».
4. Attendu : la fiche revient avec le message rouge « Saisissez une heure valide ». Le tableau des ventes affiche les vraies lignes.

### Test 2 — enregistrement normal
1. Même fiche, saisie correcte, « Enregistrer ».
2. Attendu : retour à la liste avec le message de succès, comme avant.

### Test 3 — page 500 (seulement avec `DEBUG=0`)
En `DEBUG=1`, Django affiche sa page de debug et n'appelle pas `handler500`. Le test automatique `test_handlers_rendent_la_page_quand_le_cookie_csrf_doit_etre_pose` couvre ce cas.

### Vérifs DB / Playwright
- `docker exec lespass_django poetry run python /DjangoFiles/manage.py sqlmigrate BaseBillet 0239` → `(no-op)`.
- Tests : `pytest tests/pytest/test_admin_adhesion_formulaire_invalide.py tests/pytest/test_handlers_erreur.py`.
