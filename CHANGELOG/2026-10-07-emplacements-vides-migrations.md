# Emplacements vides : migrations réparées, tâches protégées / Empty slots: repaired migrations, protected tasks

**Date :** 2026-10-07
**Migration :** Non

## Resume / Summary

**Quoi / What :**
- `cron_morning` migre chaque matin **tous** les emplacements vides (`WAITING_CONFIG`) qui ne sont pas à jour, pas seulement ceux créés le jour même. Une migration en échec n'arrête plus les suivantes ni le rappel d'adhésion. La tâche est notée en échec à la fin.
- Un nouveau lieu (`create_tenant`) reçoit le premier emplacement **entièrement migré**. Il ne reçoit jamais un emplacement à moitié migré.
- Le rappel de renouvellement d'adhésion et les clôtures comptables automatiques ignorent les emplacements vides. Pour le rappel, un lieu en erreur n'empêche plus les rappels des lieux suivants.
- Nouvelle fonction `schema_est_entierement_migre(schema_name)`, qui fait la même vérification que `migrate --check`, sur le schéma du lieu.

/ `cron_morning` now migrates every out-of-date empty slot each morning; a failed migration no longer stops the others nor the membership reminder. `create_tenant` only hands out a fully migrated slot. The renewal reminder and automatic closures skip empty slots; for the reminder, a failing venue no longer stops the next ones.

**Pourquoi / Why :**
En preprod, à 5h00 UTC, `cron_morning` migrait un nouvel emplacement pendant que les clôtures horaires (lancées elles aussi à minute 0) et le rappel lisaient ce même schéma. Résultat : un interblocage PostgreSQL (`deadlock detected`) et une migration interrompue. L'emplacement est resté à moitié migré, les suivants sont restés vides, et rien ne les re-migrait. `create_tenant` pouvait alors donner un schéma cassé à un nouveau lieu. Le rappel s'arrêtait au premier schéma vide (`relation "BaseBillet_membership" does not exist`), et les lieux suivants ne recevaient pas leurs rappels.
/ A preprod deadlock between the morning slot migration and hourly tasks reading the same schema left half-migrated slots that were never repaired and could be given to a new venue.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Customers/etat_des_migrations.py` | **Nouveau** : `schema_est_entierement_migre()` (vérifie que la table `django_migrations` existe dans le schéma du lieu, puis que le plan de migration est vide) |
| `Administration/management/commands/cron_morning.py` | `migrer_les_emplacements_pas_a_jour()` remplace `run_waiting_migrations()` : tous les emplacements pas à jour, du plus ancien au plus récent ; toute erreur d'un emplacement est isolée ; rappel envoyé puis erreur levée à la fin |
| `BaseBillet/validators.py` | `create_tenant` : premier emplacement entièrement migré, erreur claire si aucun |
| `BaseBillet/tasks.py` | `membership_renewal_reminder` : exclut `WAITING_CONFIG`, `try/except` par lieu (diff surtout de réindentation, voir `git diff -w`) |
| `comptabilite/tasks.py` | `generer_les_clotures_automatiques` : exclut `WAITING_CONFIG` |
| `tests/pytest/test_emplacements_vides_migrations.py` | **Nouveau** : 12 tests (vérification de migration, cron_morning, rappel, create_tenant) |
| `tests/pytest/test_comptabilite_celery.py` | Le test des clôtures exclut `WAITING_CONFIG`, plus un test dédié |

---

## Comment tester (a la main) / Manual test

### Test 1 — état des emplacements (preprod ou dev)
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from Customers.models import Client
from Customers.etat_des_migrations import schema_est_entierement_migre
for c in Client.objects.filter(categorie=Client.WAITING_CONFIG).order_by('pk'):
    print(c.schema_name, schema_est_entierement_migre(c.schema_name))
"
```
Attendu : `True` partout. Un `False` signale un emplacement vide ou à moitié migré : le schéma `36c8db2260724724b1c7546a62d1a4b9` de la preprod devrait sortir à `False` avant réparation.

### Test 2 — réparation par cron_morning
1. Lancer `docker exec lespass_django poetry run python /DjangoFiles/manage.py cron_morning`.
2. Les logs ne montrent `Migrating schema: …` que pour les emplacements à `False` du test 1.
3. Relancer le test 1 : tout est à `True`.
4. Relancer `cron_morning` : aucune ligne `Migrating schema` (tout est à jour).

### Test 3 — création d'un lieu
Passer un onboarding complet (`/onboard/`) : le lieu est créé normalement. Si aucun emplacement n'est entièrement migré, l'écran de lancement affiche `No fully migrated waiting tenant…`. Lancer alors `cron_morning` (ou `migrate_schemas --schema <slot>`), puis « Réessayer ».

### Verifs automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_emplacements_vides_migrations.py tests/pytest/test_comptabilite_celery.py -q
```
Chaque test a été vu en échec sur une mutation volontaire du code qu'il protège. Le fichier est relancé plusieurs fois de suite pour écarter un test instable (ordre des emplacements, interblocage).
