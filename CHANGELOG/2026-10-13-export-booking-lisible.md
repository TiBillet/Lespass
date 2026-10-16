# Export lisible des réservations de ressources / Readable resource bookings export

**Date :** 2026-10-13
**Migration :** Non

## Resume / Summary
**Quoi / What :** l'export admin des réservations (Booking) sort des colonnes lisibles : date, heure de début, heure de fin (à l'heure du lieu), durée, ressource, email, prénom, nom, statut en libellé, total payé, date de réservation.
/ The admin Booking export now outputs readable columns: date, start and end time in venue time, duration, resource, email, names, status label, total paid, booking date.
**Pourquoi / Why :** l'export automatique sortait les données brutes (ids, dates UTC, codes statut).
/ The automatic export dumped raw data (ids, UTC dates, status codes).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/models.py` | `Booking` : `start_datetime_local`, `end_datetime_local`, `date_display`, `start_time_display`, `end_time_display` ; constante `STATUTS_DES_LIGNES_PAYEES` (partagée avec `total_paid`) |
| `Administration/importers/resources_bookings_exporters.py` | Nouvelle classe `BookingExportResource` ; total payé au format `12,50` |
| `Administration/admin/resources.py` | `BookingAdmin` en export seul (`ExportActionModelAdmin`), `get_export_queryset` : `select_related` + somme SQL du total payé (une requête pour tout l'export) |
| `tests/pytest/test_export_booking.py` | 5 tests (heures locales, créneau après minuit, ligne exportée, format du total, somme SQL = `total_paid()`) |

---

## Comment tester (a la main) / Manual test
### Test 1 — scenario nominal
1. Admin → Réservations (Bookings) → Exporter → CSV.
2. Ouvrir le fichier dans un tableur.
3. Vérifier : colonnes « Date », « Heure de début », « Heure de fin » à l'heure du lieu (comparer avec l'agenda), statut en toutes lettres, pas de « None ».

### Test 2 — cas limites
- Une réservation sans prénom/nom : cases vides.
- Un créneau tard le soir : la date est celle du jour local.
- Une réservation non payée : « Total payé » vaut `0,00`. La colonne se somme dans Excel.

### Verifs DB / Playwright
- `poetry run pytest tests/pytest/test_export_booking.py -v`
