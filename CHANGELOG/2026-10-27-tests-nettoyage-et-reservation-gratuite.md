# Tests : retrait des tests de supprimer_lieux_inactifs, message de la réservation gratuite / Tests: drop supprimer_lieux_inactifs tests, free booking message

**Date :** 2026-10-27
**Migration :** Non

## Resume / Summary
**Quoi / What :** refactoring interne des tests, sans impact utilisateur.
- `tests/pytest/test_supprimer_lieux_inactifs.py` supprimé (55 tests). La commande
  `supprimer_lieux_inactifs` reste dans le code ; `Administration/nettoyage_des_lieux.py` aussi
  (utilisé par `anciennes_clotures`).
- `test_reservation_gratuite_redirection.py` : le message attendu est le msgid traduit dans la
  langue de la requête (anglais, cf. `client_connecte`), plus le texte source écrit en dur.
/ Internal test refactoring: drop the 55 tests of an unused command; compare the toast with the
msgid translated into the request language.

**Pourquoi / Why :**
- La suppression en masse des lieux inactifs a été abandonnée le 2026-10-09 (jamais lancée en
  prod, cf. `TECH_DOC/SESSIONS/TODO/ADMIN-suppression-tenant-superadmin.md`). Ses tests ne
  pouvaient pas utiliser la transaction annulée : chacun copiait un schéma complet. Coût : 8 min
  seuls, ~14 min dans la suite complète.
- Le test de la réservation gratuite échouait depuis l'ajout de la traduction anglaise du
  message (2026-10-21) : le client de test parle anglais et le message est figé dans cette langue.
/ The bulk deletion was abandoned; its tests cost ~14 min of the suite. The free booking test
broke when the English translation was added.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/test_supprimer_lieux_inactifs.py` | Supprimé |
| `tests/pytest/test_reservation_gratuite_redirection.py` | `traduit_comme_la_requete()` pour le message attendu |

---

## Comment tester (a la main) / Manual test
- `make test ARGS="tests/pytest/test_reservation_gratuite_redirection.py"` → 6 passed.
- La suite complète ne contient plus `test_supprimer_lieux_inactifs.py`.
- Pour lancer un jour la commande : `manage.py supprimer_lieux_inactifs` (à blanc par défaut).
  Ses tests sont récupérables dans l'historique git (commit `de481eae` et suivants).
