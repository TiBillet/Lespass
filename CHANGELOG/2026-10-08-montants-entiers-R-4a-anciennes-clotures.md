# Exporter puis supprimer les anciennes clôtures / Export then delete the old closures

**Date :** 2026-10-08
**Migration :** Non

## Résumé / Summary
**Quoi / What :** nouvelle commande `manage.py anciennes_clotures`. `--exporter <dossier>` écrit un fichier JSON par lieu et un `resume.csv`, sans rien écrire en base. `--supprimer --export <dossier> [--executer]` supprime les clôtures d'un lieu seulement si leur nombre en base égale celui du résumé (à blanc sans `--executer`). / New command: export one JSON file per venue plus a summary; delete a venue's closures only when the database count equals the summary.
**Pourquoi / Why :** les clôtures faites par l'ancien calcul ne sont pas chaînées et n'ont pas le format actuel (décision Q-R16). La nuit de la bascule, elles sont exportées avant les migrations (étape 4) puis supprimées après (étape 7), avant la J « reprise ». / Old closures are exported before the migrations and deleted after them, before the "reprise" J.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/management/commands/anciennes_clotures.py` | Nouvelle commande, SQL brut, une transaction par lieu |
| `tests/pytest/test_anciennes_clotures.py` | 7 tests |

---

## Comment tester (a la main) / Manual test
### Test 1 — export
1. `manage.py anciennes_clotures --exporter /tmp/export_clotures` (dossier vide).
2. Vérifier un `<schéma>.json` par lieu qui a des clôtures et un `resume.csv` (schéma, domaine, nombre).
3. Relancer sur le même dossier : refus, rien n'est écrasé.

### Test 2 — suppression
1. `manage.py anciennes_clotures --supprimer --export /tmp/export_clotures` : à blanc, rien n'est supprimé.
2. Ajouter `--executer` : seuls les lieux dont le nombre colle sont vidés ; les autres sont listés en refus.

### Verifs DB
- `SELECT count(*) FROM "<schéma>".comptabilite_cloturecaisse;` avant et après.
