# Fuseau horaire : la liste quitte le modèle / Timezone: the list leaves the model

**Date :** 2026-11-19
**Migration :** Oui — `BaseBillet/migrations/0240_fuseau_horaire_sans_liste_de_choix.py`
(`AlterField` déclaratif sur `Configuration.fuseau_horaire`, `sqlmigrate` = `no-op`, aucun SQL)

## Resume / Summary
**Quoi / What :** le champ `Configuration.fuseau_horaire` n'a plus de `choices`. Le menu déroulant et la
validation des fuseaux sont faits par le formulaire de l'admin (`ConfigurationAdmin.formfield_for_dbfield`),
qui calcule la liste à chaque affichage. / `Configuration.fuseau_horaire` no longer has `choices`; the admin
form builds the dropdown and validates the value at display time.

**Pourquoi / Why :** la liste vient de `zoneinfo.available_timezones()` et dépend des fichiers de fuseaux
installés sur la machine. Django la recopiait dans la migration. En production, la liste différait de celle
de la migration `0224`, et chaque `migrate` affichait « Your models in app(s): 'BaseBillet' have changes that
are not yet reflected in a migration ». / The list depends on the machine and was copied into migrations, so
production `migrate` kept reporting un-migrated model changes.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `TZ_CHOICES` et `choices=` retirés de `fuseau_horaire` |
| `Administration/admin_tenant.py` | `ConfigurationAdmin.formfield_for_dbfield` : `ChoiceField` des fuseaux de la machine, triés ; `import zoneinfo` |
| `BaseBillet/migrations/0240_fuseau_horaire_sans_liste_de_choix.py` | **nouveau** — `AlterField` sans SQL |
| `tests/pytest/test_configuration_fuseau_horaire_choix.py` | **nouveau** — 4 tests : modèle sans `choices`, liste de l'admin, fuseau connu accepté, fuseau inconnu refusé |

---

## Comment tester (a la main) / Manual test

### Test 1 — le menu déroulant existe toujours
1. Admin du lieu → « Paramètres » → onglet « Réglages ».
2. Le champ « Fuseau horaire » est un menu déroulant, pas un champ texte.
3. La valeur actuelle du lieu est sélectionnée.
4. Choisir « Indian/Reunion », enregistrer : la page se recharge sans erreur, la valeur est gardée.

### Test 2 — le message de migration a disparu
Après déploiement :
```
docker exec <conteneur> poetry run python manage.py makemigrations BaseBillet --dry-run
```
Attendu : « No changes detected in app 'BaseBillet' », en dev comme en prod.

### Verifs automatiques
```
docker exec lespass_django poetry run pytest tests/pytest/test_configuration_fuseau_horaire_choix.py -v
```
