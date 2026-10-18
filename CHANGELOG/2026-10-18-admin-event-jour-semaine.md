# Jour de la semaine dans la liste admin des événements / Weekday in the admin event list

**Date :** 2026-10-18
**Migration :** Non

## Resume / Summary
**Quoi / What :** dans la liste admin des événements, la colonne de date affiche le jour de la semaine en abrégé (« Lun », « Mar »…), traduit selon la langue active. / The admin event list date column now shows the localised abbreviated weekday.
**Pourquoi / Why :** repérer d'un coup d'œil le jour d'un événement sans ouvrir un calendrier. / Spot an event's weekday at a glance.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `EventAdmin` : colonne `display_datetime_with_weekday` à la place de `datetime` (tri conservé via `ordering="datetime"`) |

---

## Comment tester (a la main) / Manual test
### Test 1 — affichage FR
1. Se connecter en admin (admin@admin.com), ouvrir Événements.
2. La colonne « Event start » affiche par ex. « Sam 24 octobre 2026 20:00 ».
3. Cliquer sur l'en-tête de la colonne : le tri par date fonctionne toujours.

### Test 2 — affichage EN
1. Passer l'admin en anglais.
2. La colonne affiche par ex. « Sat Oct. 24, 2026, 8 p.m. ».

### Test 3 — fuseau horaire
1. Un événement créé à 20:00 (heure du lieu) s'affiche bien à 20:00, pas en UTC.
