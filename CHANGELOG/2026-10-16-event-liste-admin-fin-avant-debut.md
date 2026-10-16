# Liste admin des évènements : plus de 500 sur un évènement incohérent / Event admin list: no more 500 on an inconsistent event

**Date :** 2026-10-16
**Migration :** Non

## Resume / Summary
**Quoi / What :** dans la liste admin des évènements, cocher « publié » sur un évènement dont la fin est avant le début affiche maintenant une erreur sur la ligne au lieu d'une page 500. `Event.full_clean()` transforme l'erreur de date de fin en erreur générale quand le champ de fin n'est pas dans le formulaire.
/ In the event admin list, ticking "published" on an event ending before it starts now shows a row error instead of a 500. `Event.full_clean()` turns the end date error into a non-field error when the end field is not in the form.

**Pourquoi / Why :** Sentry BILLETTERIE-COOP-V2 — `ValueError: 'EventForm' has no field named 'end_datetime'`. Le formulaire de la liste (list_editable) ne contient que `published` ; Django refuse une erreur rattachée à un champ absent. Les évènements créés avant la règle « fin après début » peuvent avoir des dates incohérentes.
/ The changelist form only holds `published`; Django rejects an error attached to a missing field. Events created before the "end after start" rule may hold inconsistent dates.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Event.full_clean()` : erreur de fin → erreur générale si `end_datetime` est exclu |
| `tests/pytest/test_event_fin_avant_debut.py` | Test du formulaire de liste (`published` seul) sur un évènement incohérent |

---

## Comment tester (a la main) / Manual test
### Test 1 — évènement incohérent
1. Dans le shell, rendre un évènement incohérent :
   `docker exec -it lespass_django poetry run python manage.py tenant_command shell -s lespass`
   puis `e = Event.objects.first(); Event.objects.filter(pk=e.pk).update(end_datetime=e.datetime - timedelta(hours=2))`
2. Admin → Évènements → cocher/décocher « publié » sur cet évènement → Enregistrer.
3. Attendu : pas de 500, message « La fin de l'évènement doit être après son début. » sur la ligne, publication inchangée.

### Test 2 — cas nominal
1. Cocher « publié » sur un évènement aux dates cohérentes → Enregistrer.
2. Attendu : enregistré normalement.
