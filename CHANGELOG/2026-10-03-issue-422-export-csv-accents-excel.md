# Issue #422 : accents cassés dans les exports CSV ouverts avec Excel / Broken accents in CSV exports opened in Excel

**Date :** 2026-10-03
**Migration :** Non

## Resume / Summary

**Quoi / What :** Les exports CSV (et TSV) de l'admin commencent maintenant par un BOM UTF-8.
Concerne les exports des adhésions, des lignes comptables (ventes), des événements et des
billets. Les exports JSON, YAML, HTML gardent leur encodage d'avant (sans BOM). Les formats
binaires (XLSX, XLS, ODS) ne changent pas.
/ Admin CSV and TSV exports (memberships, sale lines, events, tickets) now start with a
UTF-8 BOM. JSON/YAML/HTML stay BOM-free, binary formats are unchanged.

**Pourquoi / Why :** Sans BOM, Excel lit un CSV UTF-8 en Windows-1252 : « é » devient « Ã© ».
LibreOffice et Google Sheets détectent l'UTF-8 tout seuls, c'est pourquoi le bug ne se voyait
pas partout. Le BOM n'est pas mis dans les exports JSON, car un JSON ne doit pas commencer
par un BOM (JSON.parse le refuse). C'est pour ça qu'on n'utilise pas l'attribut
`to_encoding` de django-import-export, qui s'applique à tous les formats texte.
/ Without a BOM, Excel reads UTF-8 CSV as Windows-1252. The BOM is restricted to CSV/TSV
because JSON must not start with one, hence no `to_encoding`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/mixins.py` | Nouveau `ExportCsvLisibleParExcelMixin` : encode les exports CSV/TSV en `utf-8-sig` |
| `Administration/admin_tenant.py` | Mixin ajouté (en tête d'héritage) à `MembershipAdmin`, `LigneArticleAdmin`, `EventAdmin`, `TicketAdmin` |
| `tests/pytest/test_export_csv_bom_excel.py` | Nouveaux tests : ordre d'héritage des 4 admins, BOM en tête du CSV, accents intacts, pas de BOM en JSON |

---

## Comment tester (a la main) / Manual test

### Test 1 — scénario nominal (Excel)
1. Admin du lieu → Adhésions. Avoir au moins une adhésion avec un accent (nom, prénom ou tarif).
2. Bouton « Exporter », format **csv**, valider.
3. Double-cliquer sur le fichier dans Excel (Windows ou Mac).
4. Attendu : les accents sont corrects (« Élodie », pas « Ã‰lodie »).

Le séparateur reste la virgule. Dans un Excel en français, les colonnes peuvent donc
apparaître regroupées dans une seule cellule. Ce problème est distinct de l'encodage et
n'est pas traité ici : le format XLSX, proposé en premier, l'évite.

### Test 2 — les autres exports
Refaire le test 1 sur : Ventes → lignes comptables (action d'export), Événements, Billets.

### Test 3 — formats non concernés
- Export **json** : le fichier ne commence pas par les octets `EF BB BF`
  (`head -c 3 fichier.json | xxd`).
- Export **xlsx** : s'ouvre comme avant.

### Verifs DB / Playwright
- Pas de donnée en base modifiée.
- Tests automatiques : `make test ARGS="tests/pytest/test_export_csv_bom_excel.py"`
