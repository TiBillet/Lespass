# Plan d'implémentation — S4 (Chantier 01 / App `comptabilite`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.
>
> **Hub :** [`INDEX.md`](INDEX.md) — **Spec :** [`SPEC.md`](SPEC.md) §6, §9
>
> **Garde-fous projet :**
> - **JAMAIS d'opération `git`**. Output suggested commit at the end.
> - **Pas de `runserver_plus`** — serveur byobu sur port 8002.
> - **Pas de `ruff format` sur fichiers existants** — uniquement sur fichiers neufs.

**Goal :** Ajouter 4 boutons d'export sur la fiche détail d'une clôture comptable : **CSV, Excel (.xlsx), PDF (A4), FEC** (Fichier des Écritures Comptables — format légal français 18 colonnes). À la fin de S4 : un trésorier ouvre une clôture, clique « Excel » et télécharge un .xlsx multi-section prêt à archiver/envoyer à son comptable.

**Architecture :**
- 4 modules métier purs (`csv_export.py`, `excel_export.py`, `pdf.py`, `fec.py`) : prennent une `ClotureCaisse`, lisent `cloture.rapport_json`, retournent un `(bytes, filename, content_type)`. Pas de logique Django dans ces modules.
- 4 URLs admin enregistrées via `get_urls()` + 4 méthodes courtes dans `ClotureCaisseAdmin` qui appellent les modules.
- 4 boutons dans `change_form_before.html` (header sticky, classes Tailwind Unfold).
- Tests pytest : pour chaque export, vérifier `response.status_code == 200`, `Content-Type` correct, `Content-Disposition: attachment`, taille > 0.

**Tech Stack :**
- CSV : stdlib `csv` + `io.StringIO`, UTF-8 BOM, séparateur `;`.
- Excel : `openpyxl` (déjà installé via poetry).
- PDF : `weasyprint` (déjà installé en V1, utilisé par les tickets).
- FEC : génération texte tab-separated, encodage CP1252 (norme française).

---

## File structure produite par S4

```
comptabilite/
├── csv_export.py                                    # nouveau (~80 lignes)
├── excel_export.py                                  # nouveau (~150 lignes)
├── pdf.py                                           # nouveau (~80 lignes)
├── fec.py                                           # nouveau (~120 lignes)
├── admin.py                                         # MODIFIÉ : +4 URLs, +4 méthodes
└── templates/
    └── comptabilite/
        ├── admin/
        │   └── change_form_before.html              # MODIFIÉ : +bandeau 4 boutons
        └── pdf/
            └── rapport_comptable.html               # nouveau (template WeasyPrint)

tests/pytest/
└── test_comptabilite_exports.py                     # nouveau (~120 lignes, 4-6 tests)
```

Pas de modification du modèle, des services, ou des tâches Celery.

---

## Découpage en 3 blocs subagent

| Bloc | Tasks | Sortie |
|---|---|---|
| **B1** | `csv_export.py` + `excel_export.py` + 2 URLs admin + 2 boutons + 2 tests | CSV et Excel téléchargeables |
| **B2** | `pdf.py` + template `pdf/rapport_comptable.html` + 1 URL admin + 1 bouton + 1 test | PDF A4 téléchargeable |
| **B3** | `fec.py` + 1 URL admin + 1 bouton + 1 test + finitions UI (bandeau export complet) | FEC téléchargeable, S4 complète |

---

## Bloc B1 — Exports CSV + Excel

### Files
- Create: `comptabilite/csv_export.py`
- Create: `comptabilite/excel_export.py`
- Modify: `comptabilite/admin.py` (+2 URLs, +2 méthodes, +helper `_telecharger`)
- Modify: `comptabilite/templates/comptabilite/admin/change_form_before.html` (+bandeau 2 boutons)
- Create: `tests/pytest/test_comptabilite_exports.py` (2 tests)

### Tests TDD

```python
"""
Tests pour les exports comptables (CSV, Excel, PDF, FEC).
/ Tests for accounting exports (CSV, Excel, PDF, FEC).

LOCALISATION : tests/pytest/test_comptabilite_exports.py
Pattern : live dev DB, meme conftest que les autres tests comptabilite.
"""
import pytest
from django_tenants.utils import tenant_context
from django.utils import timezone
from datetime import timedelta

# Reuse the same conftest pattern (django_db_setup + _enable_db_access)
@pytest.fixture(scope="session")
def django_db_setup():
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client_avec_cloture():
    """
    Cree un admin_client + 1 cloture J recente pour les tests d'export.
    Retourne (client, domain, tenant, cloture_uuid).
    """
    from django.test import Client as DjangoClient
    from Customers.models import Client as TenantClient
    from AuthBillet.models import TibilletUser
    from comptabilite.models import ClotureCaisse
    from comptabilite.tasks import generer_cloture_pour_tenant

    tenant = TenantClient.objects.exclude(schema_name="public").first()
    domain = tenant.domains.first()

    with tenant_context(tenant):
        admin_user, _ = TibilletUser.objects.get_or_create(
            email="admin@admin.com",
            defaults={"is_staff": True, "is_superuser": True, "is_active": True},
        )
        if not admin_user.is_staff:
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.is_active = True
            admin_user.save()

        # Cloture sur une periode passee distincte (eviter collisions tests)
        fin = timezone.now() - timedelta(days=200)
        debut = fin - timedelta(days=1)
        ClotureCaisse.objects.filter(datetime_debut=debut, datetime_fin=fin).delete()
        cloture_uuid = generer_cloture_pour_tenant(
            schema_name=tenant.schema_name, niveau="J",
            datetime_debut_iso=debut.isoformat(),
            datetime_fin_iso=fin.isoformat(),
        )

    client = DjangoClient(HTTP_HOST=domain.domain)
    client.force_login(admin_user)
    return client, domain, tenant, cloture_uuid


def test_export_csv_retourne_fichier(admin_client_avec_cloture):
    """GET .../exporter-csv/ retourne un CSV avec les bons headers."""
    client, _, tenant, cloture_uuid = admin_client_avec_cloture
    url = f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/exporter-csv/"
    response = client.get(url)
    assert response.status_code == 200
    assert "text/csv" in response["Content-Type"]
    assert "attachment" in response["Content-Disposition"]
    assert ".csv" in response["Content-Disposition"]
    contenu = response.content.decode("utf-8-sig")  # decode BOM
    assert "Rapport de cl" in contenu or "Closure" in contenu  # FR/EN header

    # Cleanup
    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()


def test_export_excel_retourne_fichier(admin_client_avec_cloture):
    """GET .../exporter-excel/ retourne un .xlsx avec les bons headers."""
    client, _, tenant, cloture_uuid = admin_client_avec_cloture
    url = f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/exporter-excel/"
    response = client.get(url)
    assert response.status_code == 200
    assert "spreadsheetml" in response["Content-Type"]
    assert "attachment" in response["Content-Disposition"]
    assert ".xlsx" in response["Content-Disposition"]
    # Taille minimale d'un xlsx valide (zip + xml internes) : ~5 KB
    assert len(response.content) > 4000

    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()
```

### Implémentation `comptabilite/csv_export.py`

```python
"""
Export CSV d'une cloture comptable.
/ CSV export of an accounting closure.

LOCALISATION : comptabilite/csv_export.py

Format : separateur ';', UTF-8 avec BOM (pour ouverture directe dans Excel).
Lit cloture.rapport_json (pre-calcule par S2), pas de recalcul.
Toutes les valeurs monetaires sont en centimes dans rapport_json :
on les affiche en euros (xx.xx) ici.

/ Format: ';' separator, UTF-8 with BOM (so Excel opens it correctly).
Reads cloture.rapport_json (pre-computed by S2), no re-aggregation.
"""
import csv
import io


def _euros(centimes):
    """Convertit centimes (int) en string '12.34' (jamais None)."""
    if centimes is None:
        return "0.00"
    return f"{centimes / 100:.2f}"


def generer_csv_cloture(cloture) -> tuple:
    """
    Retourne (bytes, filename, content_type) pour l'export CSV.
    / Returns (bytes, filename, content_type) for the CSV export.
    """
    rapport = cloture.rapport_json or {}
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL)

    # En-tete generale / Header
    writer.writerow(["Rapport de cloture comptable"])
    writer.writerow(["Numero", cloture.numero_sequentiel])
    writer.writerow(["Niveau", cloture.get_niveau_display()])
    writer.writerow(["Debut", cloture.datetime_debut.strftime("%Y-%m-%d %H:%M")])
    writer.writerow(["Fin", cloture.datetime_fin.strftime("%Y-%m-%d %H:%M")])
    writer.writerow(["Transactions", cloture.nombre_transactions])
    writer.writerow(["Total TTC (EUR)", _euros(cloture.total_general)])
    writer.writerow(["Total HT (EUR)", _euros(cloture.total_ht)])
    writer.writerow(["Total TVA (EUR)", _euros(cloture.total_tva)])
    writer.writerow(["Hash lignes", cloture.hash_lignes or ""])
    writer.writerow([])

    # 1. Totaux par moyen / Totals by payment method
    writer.writerow(["[Totaux par moyen de paiement]"])
    writer.writerow(["Code", "Libelle", "Total (EUR)", "Nb"])
    for code, item in (rapport.get("totaux_par_moyen") or {}).items():
        if code in ("total", "currency_code"):
            continue
        if isinstance(item, dict):
            writer.writerow([code, item.get("label", ""), _euros(item.get("total")), item.get("nb", 0)])
    writer.writerow([])

    # 2. TVA / VAT
    writer.writerow(["[Ventilation TVA]"])
    writer.writerow(["Taux %", "Total HT", "Total TVA", "Total TTC"])
    for taux, item in (rapport.get("tva") or {}).items():
        if isinstance(item, dict):
            writer.writerow([
                item.get("taux", taux),
                _euros(item.get("total_ht")),
                _euros(item.get("total_tva")),
                _euros(item.get("total_ttc")),
            ])
    writer.writerow([])

    # 3. Adhesions
    writer.writerow(["[Adhesions]"])
    writer.writerow(["Produit", "Tarif", "Moyen paiement", "Total (EUR)", "Nb"])
    for item in (rapport.get("adhesions") or {}).get("detail", {}).values():
        writer.writerow([
            item.get("nom_produit", ""),
            item.get("nom_tarif", ""),
            item.get("moyen_paiement_label") or item.get("moyen_paiement", ""),
            _euros(item.get("total")),
            item.get("nb", 0),
        ])
    writer.writerow([])

    # 4. Billets
    writer.writerow(["[Billets evenements]"])
    writer.writerow(["Evenement", "Date", "Produit", "Tarif", "Total (EUR)", "Nb"])
    for item in (rapport.get("billets") or {}).get("detail", {}).values():
        writer.writerow([
            item.get("nom_event", ""),
            item.get("date_event", ""),
            item.get("nom_produit", ""),
            item.get("nom_tarif", ""),
            _euros(item.get("total")),
            item.get("nb", 0),
        ])
    writer.writerow([])

    # 5. Remboursements
    writer.writerow(["[Remboursements et avoirs]"])
    writer.writerow(["Type", "Total (EUR)", "Nb"])
    rb = rapport.get("remboursements") or {}
    cn = rb.get("credit_notes", {})
    rf = rb.get("refunded", {})
    writer.writerow(["Avoirs (credit notes)", _euros(cn.get("total")), cn.get("nb", 0)])
    writer.writerow(["Remboursements (refunded)", _euros(rf.get("total")), rf.get("nb", 0)])

    # Encodage UTF-8 avec BOM (sequence ﻿ au debut) pour ouverture Excel.
    # / UTF-8 with BOM (﻿ prefix) for Excel compatibility.
    contenu_bytes = ("﻿" + buffer.getvalue()).encode("utf-8")
    filename = f"cloture-{cloture.numero_sequentiel}-{cloture.datetime_fin:%Y%m%d}.csv"
    return contenu_bytes, filename, "text/csv; charset=utf-8"
```

### Implémentation `comptabilite/excel_export.py`

```python
"""
Export Excel (.xlsx) d'une cloture comptable.
/ Excel (.xlsx) export of an accounting closure.

LOCALISATION : comptabilite/excel_export.py

Utilise openpyxl. Une seule feuille 'Rapport' avec sections empilees.
Styles minimalistes : titre en gras, en-tetes de section sur fond gris,
en-tetes de colonnes sur fond gris clair.

/ Uses openpyxl. Single 'Rapport' sheet with stacked sections.
Minimalist styling: bold title, dark gray section headers, light gray col headers.
"""
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


# Styles reutilises dans toutes les sections.
# Definis au niveau module (pas dans la fonction) : crees une seule fois.
# / Reusable styles defined at module level (created once).
_FONT_TITRE = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
_FILL_TITRE = PatternFill("solid", fgColor="333333")
_FONT_SECTION = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
_FILL_SECTION = PatternFill("solid", fgColor="333333")
_FONT_HEADER = Font(name="Calibri", size=10, bold=True)
_FILL_HEADER = PatternFill("solid", fgColor="F0F0F0")
_FONT_TOTAL = Font(name="Calibri", size=10, bold=True)
_FILL_TOTAL = PatternFill("solid", fgColor="E8F5E9")
_ALIGN_RIGHT = Alignment(horizontal="right")
_BORDER_THIN = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)


def _euros(centimes):
    if centimes is None:
        return 0.0
    return round(centimes / 100, 2)


def _ecrire_section_header(ws, row, titre, span=4):
    """Ecrit un titre de section sur 1 ligne fusionnee."""
    ws.cell(row=row, column=1, value=titre).font = _FONT_SECTION
    ws.cell(row=row, column=1).fill = _FILL_SECTION
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    return row + 1


def _ecrire_ligne_header(ws, row, colonnes):
    """Ecrit une ligne d'en-tetes de colonnes."""
    for col_idx, val in enumerate(colonnes, start=1):
        cell = ws.cell(row=row, column=col_idx, value=val)
        cell.font = _FONT_HEADER
        cell.fill = _FILL_HEADER
        cell.border = _BORDER_THIN
    return row + 1


def _ecrire_ligne_donnees(ws, row, valeurs, montants_indices=None):
    """Ecrit une ligne de donnees. montants_indices : indices des colonnes a aligner a droite."""
    montants_indices = montants_indices or []
    for col_idx, val in enumerate(valeurs, start=1):
        cell = ws.cell(row=row, column=col_idx, value=val)
        cell.border = _BORDER_THIN
        if col_idx in montants_indices:
            cell.alignment = _ALIGN_RIGHT
            cell.number_format = "#,##0.00"
    return row + 1


def generer_excel_cloture(cloture) -> tuple:
    """
    Retourne (bytes, filename, content_type) pour l'export Excel.
    / Returns (bytes, filename, content_type) for the Excel export.
    """
    rapport = cloture.rapport_json or {}

    wb = Workbook()
    ws = wb.active
    ws.title = "Rapport"

    row = 1

    # --- Titre / Title
    ws.cell(row=row, column=1, value=f"Cloture #{cloture.numero_sequentiel} — {cloture.get_niveau_display()}").font = _FONT_TITRE
    ws.cell(row=row, column=1).fill = _FILL_TITRE
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    row += 1
    ws.cell(row=row, column=1, value=f"Debut : {cloture.datetime_debut:%Y-%m-%d %H:%M} — Fin : {cloture.datetime_fin:%Y-%m-%d %H:%M}").font = Font(italic=True)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    row += 2

    # --- Section : Totaux par moyen
    row = _ecrire_section_header(ws, row, "Totaux par moyen de paiement")
    row = _ecrire_ligne_header(ws, row, ["Code", "Libelle", "Total (EUR)", "Nb"])
    for code, item in (rapport.get("totaux_par_moyen") or {}).items():
        if code in ("total", "currency_code"):
            continue
        if isinstance(item, dict):
            row = _ecrire_ligne_donnees(
                ws, row,
                [code, item.get("label", ""), _euros(item.get("total")), item.get("nb", 0)],
                montants_indices=[3],
            )
    row += 1

    # --- Section : TVA
    row = _ecrire_section_header(ws, row, "Ventilation TVA")
    row = _ecrire_ligne_header(ws, row, ["Taux %", "HT (EUR)", "TVA (EUR)", "TTC (EUR)"])
    for taux, item in (rapport.get("tva") or {}).items():
        if isinstance(item, dict):
            row = _ecrire_ligne_donnees(
                ws, row,
                [item.get("taux", taux),
                 _euros(item.get("total_ht")),
                 _euros(item.get("total_tva")),
                 _euros(item.get("total_ttc"))],
                montants_indices=[2, 3, 4],
            )
    row += 1

    # --- Section : Adhesions
    row = _ecrire_section_header(ws, row, "Adhesions")
    row = _ecrire_ligne_header(ws, row, ["Produit", "Tarif", "Total (EUR)", "Nb"])
    for item in (rapport.get("adhesions") or {}).get("detail", {}).values():
        row = _ecrire_ligne_donnees(
            ws, row,
            [item.get("nom_produit", ""), item.get("nom_tarif", ""),
             _euros(item.get("total")), item.get("nb", 0)],
            montants_indices=[3],
        )
    row += 1

    # --- Section : Billets
    row = _ecrire_section_header(ws, row, "Billets evenements")
    row = _ecrire_ligne_header(ws, row, ["Evenement", "Produit", "Total (EUR)", "Nb"])
    for item in (rapport.get("billets") or {}).get("detail", {}).values():
        row = _ecrire_ligne_donnees(
            ws, row,
            [item.get("nom_event", ""), item.get("nom_produit", ""),
             _euros(item.get("total")), item.get("nb", 0)],
            montants_indices=[3],
        )
    row += 1

    # --- Section : Remboursements
    row = _ecrire_section_header(ws, row, "Remboursements et avoirs")
    row = _ecrire_ligne_header(ws, row, ["Type", "Total (EUR)", "Nb", ""])
    rb = rapport.get("remboursements") or {}
    cn = rb.get("credit_notes", {})
    rf = rb.get("refunded", {})
    row = _ecrire_ligne_donnees(ws, row, ["Avoirs", _euros(cn.get("total")), cn.get("nb", 0), ""], montants_indices=[2])
    row = _ecrire_ligne_donnees(ws, row, ["Remboursements", _euros(rf.get("total")), rf.get("nb", 0), ""], montants_indices=[2])

    # --- Largeurs de colonnes auto
    for col_idx in range(1, 5):
        ws.column_dimensions[get_column_letter(col_idx)].width = 22

    # Generation des bytes
    buffer = io.BytesIO()
    wb.save(buffer)

    filename = f"cloture-{cloture.numero_sequentiel}-{cloture.datetime_fin:%Y%m%d}.xlsx"
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return buffer.getvalue(), filename, content_type
```

### Helper + vues admin

Ajouter en module-level dans `comptabilite/admin.py` :

```python
def _telecharger(bytes_data, filename, content_type):
    """
    Construit une HttpResponse de telechargement (Content-Disposition: attachment).
    / Build an HttpResponse for download (attachment).
    """
    from django.http import HttpResponse
    response = HttpResponse(bytes_data, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
```

Ajouter dans `ClotureCaisseAdmin` (dans `get_urls()` AVANT le `+ urls` :

```python
        custom = [
            path(
                "rapport-temps-reel/",
                self.admin_site.admin_view(self.rapport_temps_reel),
                name="comptabilite_cloturecaisse_temps_reel",
            ),
            path(
                "<uuid:object_id>/exporter-csv/",
                self.admin_site.admin_view(self.exporter_csv),
                name="comptabilite_cloturecaisse_csv",
            ),
            path(
                "<uuid:object_id>/exporter-excel/",
                self.admin_site.admin_view(self.exporter_excel),
                name="comptabilite_cloturecaisse_excel",
            ),
        ]
```

Et 2 méthodes courtes :

```python
    def exporter_csv(self, request, object_id):
        """Telecharge la cloture au format CSV (sections + totaux)."""
        from django.shortcuts import get_object_or_404
        from comptabilite.csv_export import generer_csv_cloture
        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        return _telecharger(*generer_csv_cloture(cloture))

    def exporter_excel(self, request, object_id):
        """Telecharge la cloture au format Excel (.xlsx)."""
        from django.shortcuts import get_object_or_404
        from comptabilite.excel_export import generer_excel_cloture
        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        return _telecharger(*generer_excel_cloture(cloture))
```

### Modification template `change_form_before.html`

Insérer un bandeau de boutons d'export AVANT le bloc « Closure summary ». Use the Edit tool to add this block at the very beginning of the `<div class="flex flex-col gap-4">`:

```html
    {% if cloture %}
        <div class="flex flex-row gap-2 flex-wrap" data-testid="comptabilite-bandeau-exports">
            <a href="exporter-csv/"
               data-testid="comptabilite-export-csv"
               class="bg-base-100 hover:bg-base-200 dark:bg-base-800 dark:hover:bg-base-700 px-3 py-2 rounded-md text-sm font-medium no-underline border border-base-200 dark:border-base-700">
                📄 {% translate "CSV" %}
            </a>
            <a href="exporter-excel/"
               data-testid="comptabilite-export-excel"
               class="bg-base-100 hover:bg-base-200 dark:bg-base-800 dark:hover:bg-base-700 px-3 py-2 rounded-md text-sm font-medium no-underline border border-base-200 dark:border-base-700">
                📊 {% translate "Excel" %}
            </a>
            {# B2 ajoutera PDF, B3 ajoutera FEC #}
        </div>
    {% endif %}
```

### Acceptance B1

- [ ] 2 tests passent : CSV + Excel téléchargeables avec bons Content-Type
- [ ] Helper `_telecharger` module-level
- [ ] 2 URLs custom dans `get_urls()`
- [ ] 2 boutons dans `change_form_before.html`
- [ ] Pas de régression : tous les tests S1+S2+S3 passent toujours
- [ ] `manage.py check` 0 issue
- [ ] Fichiers touchés : 5 (2 nouveaux + admin.py + template + test)

---

## Bloc B2 — Export PDF (WeasyPrint)

### Files
- Create: `comptabilite/pdf.py`
- Create: `comptabilite/templates/comptabilite/pdf/rapport_comptable.html`
- Modify: `comptabilite/admin.py` (+1 URL, +1 méthode `exporter_pdf`)
- Modify: `comptabilite/templates/comptabilite/admin/change_form_before.html` (+1 bouton)
- Modify: `tests/pytest/test_comptabilite_exports.py` (+1 test)

### Test

```python
def test_export_pdf_retourne_fichier(admin_client_avec_cloture):
    """GET .../exporter-pdf/ retourne un PDF A4."""
    client, _, tenant, cloture_uuid = admin_client_avec_cloture
    url = f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/exporter-pdf/"
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert "attachment" in response["Content-Disposition"]
    assert ".pdf" in response["Content-Disposition"]
    # Signature magic d'un PDF : commence par %PDF-
    assert response.content[:5] == b"%PDF-"

    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()
```

### Implémentation `comptabilite/pdf.py`

```python
"""
Export PDF d'une cloture comptable (WeasyPrint).
/ PDF export of an accounting closure (WeasyPrint).

LOCALISATION : comptabilite/pdf.py

Template HTML standalone (styles inline obligatoires pour WeasyPrint —
pas de CSS externe fiable). Format A4, marges 1.5cm.

/ Standalone HTML template (inline styles mandatory for WeasyPrint).
A4, 1.5cm margins.
"""
import io

from django.template.loader import render_to_string
from weasyprint import HTML


def _euros(centimes):
    if centimes is None:
        return "0.00"
    return f"{centimes / 100:.2f}"


def generer_pdf_cloture(cloture) -> tuple:
    """
    Retourne (bytes, filename, content_type) pour l'export PDF.
    / Returns (bytes, filename, content_type) for the PDF export.
    """
    rapport = cloture.rapport_json or {}

    # Pre-format des montants pour le template (eviter filtres custom)
    # / Pre-format amounts for template
    contexte = {
        "cloture": cloture,
        "rapport": rapport,
        "totaux_par_moyen_items": [
            {
                "code": code,
                "label": item.get("label", ""),
                "total_euros": _euros(item.get("total")),
                "nb": item.get("nb", 0),
            }
            for code, item in (rapport.get("totaux_par_moyen") or {}).items()
            if code not in ("total", "currency_code") and isinstance(item, dict)
        ],
        "tva_items": [
            {
                "taux": item.get("taux", taux),
                "ht": _euros(item.get("total_ht")),
                "tva": _euros(item.get("total_tva")),
                "ttc": _euros(item.get("total_ttc")),
            }
            for taux, item in (rapport.get("tva") or {}).items()
            if isinstance(item, dict)
        ],
        "adhesions_items": [
            {
                "nom_produit": item.get("nom_produit", ""),
                "nom_tarif": item.get("nom_tarif", ""),
                "total_euros": _euros(item.get("total")),
                "nb": item.get("nb", 0),
            }
            for item in (rapport.get("adhesions") or {}).get("detail", {}).values()
        ],
        "billets_items": [
            {
                "nom_event": item.get("nom_event", ""),
                "nom_produit": item.get("nom_produit", ""),
                "total_euros": _euros(item.get("total")),
                "nb": item.get("nb", 0),
            }
            for item in (rapport.get("billets") or {}).get("detail", {}).values()
        ],
        "infos_legales": rapport.get("infos_legales") or {},
        "cloture_total_ttc_euros": _euros(cloture.total_general),
        "cloture_total_ht_euros": _euros(cloture.total_ht),
        "cloture_total_tva_euros": _euros(cloture.total_tva),
    }

    html_string = render_to_string("comptabilite/pdf/rapport_comptable.html", contexte)
    buffer = io.BytesIO()
    HTML(string=html_string).write_pdf(buffer)

    filename = f"cloture-{cloture.numero_sequentiel}-{cloture.datetime_fin:%Y%m%d}.pdf"
    return buffer.getvalue(), filename, "application/pdf"
```

### Template `comptabilite/templates/comptabilite/pdf/rapport_comptable.html`

```bash
mkdir -p /home/jonas/TiBillet/dev/Lespass/comptabilite/templates/comptabilite/pdf
```

Template style **inline** (WeasyPrint exige du CSS dans le HTML directement, pas de fichier externe fiable) :

```html
{% load i18n %}<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Cloture {{ cloture.numero_sequentiel }}</title>
    <style>
        @page { size: A4; margin: 1.5cm; }
        body { font-family: "Helvetica", "Arial", sans-serif; font-size: 10pt; color: #222; }
        h1 { font-size: 16pt; margin: 0 0 8px 0; }
        h2 { font-size: 12pt; margin: 18px 0 8px 0; padding: 6px 10px; background: #333; color: #fff; }
        .meta { color: #666; font-size: 9pt; margin-bottom: 16px; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 6px; }
        th { background: #f0f0f0; padding: 6px 8px; text-align: left; border: 1px solid #ddd; }
        td { padding: 5px 8px; border: 1px solid #eee; }
        td.amount { text-align: right; font-family: "Courier New", monospace; }
        .total-row { font-weight: bold; background: #e8f5e9; }
        .footer { margin-top: 24px; font-size: 8pt; color: #888; border-top: 1px solid #ccc; padding-top: 8px; }
    </style>
</head>
<body>
    <h1>Cloture #{{ cloture.numero_sequentiel }} — {{ cloture.get_niveau_display }}</h1>
    <p class="meta">
        Debut : {{ cloture.datetime_debut|date:"d/m/Y H:i" }}<br>
        Fin : {{ cloture.datetime_fin|date:"d/m/Y H:i" }}<br>
        Transactions : {{ cloture.nombre_transactions }}<br>
        Total TTC : {{ cloture_total_ttc_euros }} EUR
    </p>

    <h2>Totaux par moyen de paiement</h2>
    <table>
        <thead><tr><th>Code</th><th>Libelle</th><th>Total (EUR)</th><th>Nb</th></tr></thead>
        <tbody>
            {% for item in totaux_par_moyen_items %}
                <tr>
                    <td>{{ item.code }}</td>
                    <td>{{ item.label }}</td>
                    <td class="amount">{{ item.total_euros }}</td>
                    <td class="amount">{{ item.nb }}</td>
                </tr>
            {% empty %}
                <tr><td colspan="4">Aucune transaction.</td></tr>
            {% endfor %}
        </tbody>
    </table>

    <h2>Ventilation TVA</h2>
    <table>
        <thead><tr><th>Taux</th><th>HT (EUR)</th><th>TVA (EUR)</th><th>TTC (EUR)</th></tr></thead>
        <tbody>
            {% for item in tva_items %}
                <tr>
                    <td>{{ item.taux }}%</td>
                    <td class="amount">{{ item.ht }}</td>
                    <td class="amount">{{ item.tva }}</td>
                    <td class="amount">{{ item.ttc }}</td>
                </tr>
            {% empty %}
                <tr><td colspan="4">Aucune ligne soumise a TVA.</td></tr>
            {% endfor %}
        </tbody>
    </table>

    <h2>Adhesions</h2>
    <table>
        <thead><tr><th>Produit</th><th>Tarif</th><th>Total (EUR)</th><th>Nb</th></tr></thead>
        <tbody>
            {% for item in adhesions_items %}
                <tr>
                    <td>{{ item.nom_produit }}</td>
                    <td>{{ item.nom_tarif }}</td>
                    <td class="amount">{{ item.total_euros }}</td>
                    <td class="amount">{{ item.nb }}</td>
                </tr>
            {% empty %}
                <tr><td colspan="4">Aucune adhesion sur la periode.</td></tr>
            {% endfor %}
        </tbody>
    </table>

    <h2>Billets evenements</h2>
    <table>
        <thead><tr><th>Evenement</th><th>Produit</th><th>Total (EUR)</th><th>Nb</th></tr></thead>
        <tbody>
            {% for item in billets_items %}
                <tr>
                    <td>{{ item.nom_event }}</td>
                    <td>{{ item.nom_produit }}</td>
                    <td class="amount">{{ item.total_euros }}</td>
                    <td class="amount">{{ item.nb }}</td>
                </tr>
            {% empty %}
                <tr><td colspan="4">Aucun billet sur la periode.</td></tr>
            {% endfor %}
        </tbody>
    </table>

    <div class="footer">
        <strong>{{ infos_legales.organisation }}</strong><br>
        {% if infos_legales.adresse %}{{ infos_legales.adresse }}, {% endif %}
        {% if infos_legales.code_postal %}{{ infos_legales.code_postal }} {{ infos_legales.ville }}{% endif %}<br>
        {% if infos_legales.siren %}SIREN : {{ infos_legales.siren }}{% endif %}
        {% if infos_legales.tva_number %}— TVA : {{ infos_legales.tva_number }}{% endif %}<br>
        Hash : <code style="font-family: monospace; font-size: 7pt;">{{ cloture.hash_lignes }}</code>
    </div>
</body>
</html>
```

### Acceptance B2

- [ ] PDF téléchargeable, content-type `application/pdf`, signature `%PDF-`
- [ ] Template HTML rendable par WeasyPrint sans warnings critiques
- [ ] Bouton « 📄 PDF » ajouté dans le bandeau
- [ ] 1 test passe
- [ ] Pas de régression

---

## Bloc B3 — Export FEC (Fichier des Écritures Comptables)

### Contexte FEC

Le **FEC** est un format **réglementaire français** imposé par l'article A47 A-1 du Livre des procédures fiscales. Format texte tabulé, encodage CP1252, 18 colonnes obligatoires dans un ordre précis.

Pour S4, on génère un FEC **simplifié** (un seul journal « VTE » = ventes) avec des comptes comptables **hardcodés par défaut** (les modèles `CompteComptable` / `MappingMoyenDePaiement` viennent en S5 et permettront la personnalisation).

### Files
- Create: `comptabilite/fec.py`
- Modify: `comptabilite/admin.py` (+1 URL, +1 méthode `exporter_fec`)
- Modify: `comptabilite/templates/comptabilite/admin/change_form_before.html` (+1 bouton)
- Modify: `tests/pytest/test_comptabilite_exports.py` (+1 test)

### Test

```python
def test_export_fec_retourne_fichier(admin_client_avec_cloture):
    """GET .../exporter-fec/ retourne un fichier FEC tabule."""
    client, _, tenant, cloture_uuid = admin_client_avec_cloture
    url = f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/exporter-fec/"
    response = client.get(url)
    assert response.status_code == 200
    assert "text/plain" in response["Content-Type"] or "text/tab-separated" in response["Content-Type"]
    assert "attachment" in response["Content-Disposition"]
    # Le FEC doit avoir au moins l'en-tete (18 colonnes tabulees)
    contenu = response.content.decode("cp1252")
    premiere_ligne = contenu.split("\n")[0]
    assert premiere_ligne.count("\t") == 17  # 18 colonnes = 17 tabs

    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse
        ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()
```

### Implémentation `comptabilite/fec.py`

```python
"""
Export FEC (Fichier des Ecritures Comptables) — norme francaise.
/ FEC export — French legal accounting file format.

LOCALISATION : comptabilite/fec.py

Format texte tabule, 18 colonnes obligatoires, encodage CP1252.
Reference : article A47 A-1 du Livre des procedures fiscales.

S4 : FEC simplifie avec comptes par defaut (hardcodes).
S5 ajoutera la personnalisation via CompteComptable / MappingMoyenDePaiement.

/ Tab-separated text, 18 mandatory columns, CP1252 encoding.
S4 ships a simplified FEC with hardcoded default accounts.
"""

# Comptes comptables par defaut (plan comptable francais standard PCG).
# Personnalisable en S5 via le modele CompteComptable.
# / Default accounting accounts (standard French PCG). Customizable in S5.
COMPTES_PAR_DEFAUT = {
    "client": ("411000", "Clients"),
    "banque": ("512000", "Banque"),
    "caisse": ("530000", "Caisse"),
    "cheques": ("511000", "Cheques a encaisser"),
    "tva_55": ("4457100", "TVA collectee 5.5%"),
    "tva_10": ("4457200", "TVA collectee 10%"),
    "tva_20": ("4457300", "TVA collectee 20%"),
    "ventes_billets": ("706000", "Prestations - Billets"),
    "ventes_adhesions": ("756000", "Cotisations - Adhesions"),
}

# Mapping PaymentMethod -> compte de tresorerie.
# / PaymentMethod -> treasury account.
MAPPING_PAIEMENT = {
    "CA": "caisse",
    "CC": "banque",
    "CH": "cheques",
    "TR": "banque",
    "SF": "banque", "SN": "banque", "SP": "banque", "SR": "banque",
    "QR": "banque", "LE": "client", "LG": "client",
}

# 18 colonnes obligatoires du FEC (article A47 A-1).
# / 18 mandatory FEC columns.
COLONNES_FEC = [
    "JournalCode", "JournalLib", "EcritureNum", "EcritureDate",
    "CompteNum", "CompteLib", "CompAuxNum", "CompAuxLib",
    "PieceRef", "PieceDate", "EcritureLib", "Debit", "Credit",
    "EcritureLet", "DateLet", "ValidDate", "Montantdevise", "Idevise",
]


def _euros_str(centimes):
    """Convertit centimes en string '12,34' (decimal francais)."""
    if centimes is None or centimes == 0:
        return "0,00"
    return f"{centimes / 100:.2f}".replace(".", ",")


def _ligne_fec(**champs):
    """Construit une ligne FEC tabulee a partir des colonnes."""
    return "\t".join(str(champs.get(c, "")) for c in COLONNES_FEC)


def generer_fec_cloture(cloture) -> tuple:
    """
    Retourne (bytes, filename, content_type) pour l'export FEC.
    / Returns (bytes, filename, content_type) for the FEC export.

    Strategie : 1 ecriture comptable par cloture, ventilee en N lignes :
    - 1 ligne debit par moyen de paiement (compte tresorerie)
    - 1 ligne credit par categorie de vente (billets/adhesions)
    - 1 ligne credit par taux TVA
    """
    rapport = cloture.rapport_json or {}

    journal_code = "VTE"
    journal_lib = "Ventes"
    ecriture_num = str(cloture.numero_sequentiel)
    ecriture_date = cloture.datetime_fin.strftime("%Y%m%d")
    piece_ref = f"CLOT-{cloture.numero_sequentiel}"
    piece_date = ecriture_date
    valid_date = ecriture_date
    ecriture_lib = f"Cloture {cloture.get_niveau_display()} #{cloture.numero_sequentiel}"

    lignes = ["\t".join(COLONNES_FEC)]  # en-tete

    # --- Debits : 1 ligne par moyen de paiement utilise
    # / Debits: 1 line per used payment method
    for code, item in (rapport.get("totaux_par_moyen") or {}).items():
        if code in ("total", "currency_code") or not isinstance(item, dict):
            continue
        total = item.get("total", 0)
        if total == 0:
            continue
        compte_key = MAPPING_PAIEMENT.get(code, "banque")
        num, lib = COMPTES_PAR_DEFAUT[compte_key]
        lignes.append(_ligne_fec(
            JournalCode=journal_code, JournalLib=journal_lib,
            EcritureNum=ecriture_num, EcritureDate=ecriture_date,
            CompteNum=num, CompteLib=lib,
            PieceRef=piece_ref, PieceDate=piece_date,
            EcritureLib=f"{ecriture_lib} - {item.get('label', code)}",
            Debit=_euros_str(total), Credit="0,00",
            ValidDate=valid_date, Montantdevise="", Idevise="",
        ))

    # --- Credits ventes billets (706)
    # / Credits ticket sales (706)
    total_billets_ttc = (rapport.get("billets") or {}).get("total", 0)
    if total_billets_ttc:
        num, lib = COMPTES_PAR_DEFAUT["ventes_billets"]
        lignes.append(_ligne_fec(
            JournalCode=journal_code, JournalLib=journal_lib,
            EcritureNum=ecriture_num, EcritureDate=ecriture_date,
            CompteNum=num, CompteLib=lib,
            PieceRef=piece_ref, PieceDate=piece_date,
            EcritureLib=f"{ecriture_lib} - Billets",
            Debit="0,00", Credit=_euros_str(total_billets_ttc),
            ValidDate=valid_date,
        ))

    # --- Credits adhesions (756)
    # / Credits memberships (756)
    total_adhesions_ttc = (rapport.get("adhesions") or {}).get("total", 0)
    if total_adhesions_ttc:
        num, lib = COMPTES_PAR_DEFAUT["ventes_adhesions"]
        lignes.append(_ligne_fec(
            JournalCode=journal_code, JournalLib=journal_lib,
            EcritureNum=ecriture_num, EcritureDate=ecriture_date,
            CompteNum=num, CompteLib=lib,
            PieceRef=piece_ref, PieceDate=piece_date,
            EcritureLib=f"{ecriture_lib} - Adhesions",
            Debit="0,00", Credit=_euros_str(total_adhesions_ttc),
            ValidDate=valid_date,
        ))

    # --- Credits TVA (4457X)
    # / VAT credits (4457X)
    for taux, item in (rapport.get("tva") or {}).items():
        if not isinstance(item, dict):
            continue
        tva = item.get("total_tva", 0)
        if tva == 0:
            continue
        taux_float = item.get("taux", 0)
        if taux_float <= 6:
            compte_key = "tva_55"
        elif taux_float <= 12:
            compte_key = "tva_10"
        else:
            compte_key = "tva_20"
        num, lib = COMPTES_PAR_DEFAUT[compte_key]
        lignes.append(_ligne_fec(
            JournalCode=journal_code, JournalLib=journal_lib,
            EcritureNum=ecriture_num, EcritureDate=ecriture_date,
            CompteNum=num, CompteLib=lib,
            PieceRef=piece_ref, PieceDate=piece_date,
            EcritureLib=f"{ecriture_lib} - TVA {taux_float}%",
            Debit="0,00", Credit=_euros_str(tva),
            ValidDate=valid_date,
        ))

    contenu = "\r\n".join(lignes).encode("cp1252", errors="replace")
    filename = f"FEC-{cloture.datetime_fin:%Y%m%d}-{cloture.numero_sequentiel}.txt"
    return contenu, filename, "text/plain; charset=cp1252"
```

### Bouton et URL admin

Ajouter dans `get_urls()` :

```python
            path(
                "<uuid:object_id>/exporter-fec/",
                self.admin_site.admin_view(self.exporter_fec),
                name="comptabilite_cloturecaisse_fec",
            ),
```

Méthode :

```python
    def exporter_fec(self, request, object_id):
        """Telecharge la cloture au format FEC (norme francaise)."""
        from django.shortcuts import get_object_or_404
        from comptabilite.fec import generer_fec_cloture
        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        return _telecharger(*generer_fec_cloture(cloture))
```

Bouton dans `change_form_before.html` après le bouton Excel :

```html
            <a href="exporter-pdf/"
               data-testid="comptabilite-export-pdf"
               class="bg-base-100 hover:bg-base-200 dark:bg-base-800 dark:hover:bg-base-700 px-3 py-2 rounded-md text-sm font-medium no-underline border border-base-200 dark:border-base-700">
                🖨️ {% translate "PDF" %}
            </a>
            <a href="exporter-fec/"
               data-testid="comptabilite-export-fec"
               class="bg-base-100 hover:bg-base-200 dark:bg-base-800 dark:hover:bg-base-700 px-3 py-2 rounded-md text-sm font-medium no-underline border border-base-200 dark:border-base-700"
               title="{% translate 'Fichier des Écritures Comptables (norme française)' %}">
                ⚖️ {% translate "FEC" %}
            </a>
```

### Acceptance B3

- [ ] FEC téléchargeable, 18 colonnes tabulées (17 `\t` par ligne)
- [ ] Encodage CP1252
- [ ] 1 test passe
- [ ] Bouton « ⚖️ FEC » dans le bandeau
- [ ] Pas de régression
- [ ] `manage.py check` 0 issue

---

## Vérifications finales (sortie de B3)

```bash
# Tous les tests comptabilite
docker exec -e "API_KEY=$(docker exec lespass_django poetry run python /DjangoFiles/manage.py test_api_key 2>/dev/null | tail -1)" lespass_django bash -c "cd /DjangoFiles && /DjangoFiles/.venv/bin/pytest tests/pytest/test_comptabilite_*.py -v"

# Check Django
docker exec lespass_django poetry run python /DjangoFiles/manage.py check

# Validation manuelle (par le maintaineur)
# 1. Ouvrir /admin/comptabilite/cloturecaisse/<uuid>/change/
# 2. Verifier 4 boutons (CSV, Excel, PDF, FEC)
# 3. Cliquer chacun -> fichier telecharge, ouvert correctement
```

## Commit suggéré (à fournir par B3)

```
feat(comptabilite): S4 — exports CSV, Excel, PDF (WeasyPrint), FEC

- comptabilite/csv_export.py : generer_csv_cloture (sections + totaux,
  separateur ';', UTF-8 BOM pour Excel).
- comptabilite/excel_export.py : generer_excel_cloture (openpyxl, 1 feuille
  multi-section, styles minimalistes : titre noir/blanc, sections grises,
  totaux verts).
- comptabilite/pdf.py : generer_pdf_cloture (WeasyPrint A4) +
  templates/comptabilite/pdf/rapport_comptable.html (styles inline).
- comptabilite/fec.py : generer_fec_cloture (norme francaise 18 colonnes,
  CP1252, ventilation auto debit moyen / credit ventes / credit TVA avec
  comptes hardcodes — personnalisable en S5 via CompteComptable).
- comptabilite/admin.py : +4 URLs admin, +4 methodes courtes, helper module
  _telecharger.
- change_form_before.html : bandeau 4 boutons d'export (CSV/Excel/PDF/FEC).
- tests/pytest/test_comptabilite_exports.py : 4 tests smoke (status 200,
  Content-Type, Content-Disposition, signature/structure du fichier).

Référence : TECH_DOC/SESSIONS/COMPTABILITE/SPEC.md §6, §9 (S4).
Plan : TECH_DOC/SESSIONS/COMPTABILITE/PLAN-S4-exports.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Pièges anticipés pour S4

1. **WeasyPrint et CSS externe** : WeasyPrint ne charge PAS toujours les CSS externes en production. **Toujours du CSS inline** dans le template PDF.
2. **openpyxl `merge_cells` après écriture** : appeler `merge_cells()` AVANT d'écrire dans les cellules fusionnées, sinon les styles sont perdus.
3. **CP1252 encoding** : si un caractère n'existe pas en CP1252 (ex: `€`, `œ`), `encode("cp1252", errors="replace")` met `?`. Acceptable pour le FEC.
4. **Tabulations dans les libellés FEC** : les chaînes ne doivent JAMAIS contenir de `\t` (séparateur). Si un libellé venait à en contenir, le replacer par ` ` avant écriture (à ajouter si on rencontre le cas).
5. **UTF-8 BOM** : `"﻿"` en tête du contenu pour que Excel ouvre le CSV correctement (sinon caractères accentués cassés).
6. **`<uuid:object_id>` dans le path** : les URLs FEC/PDF/Excel/CSV ont besoin du converter `<uuid:object_id>` pour parser le PK de `ClotureCaisse` (UUIDField). Sinon Django raise `Reverse error`.
7. **Tests : ne pas chercher l'organisation dans le contenu du PDF** — WeasyPrint encode le PDF, on ne peut pas grep des strings dedans facilement. Tester juste la signature `%PDF-` et la taille minimale.
8. **`get_or_404` cross-tenant** : les vues admin tournent déjà dans le bon `tenant_context`, pas besoin de wrapper.

## Estimation

- Bloc B1 (CSV + Excel) : ~40 min
- Bloc B2 (PDF) : ~30 min
- Bloc B3 (FEC) : ~30 min

**Total : ~1h40** (hors validation maintaineur).
