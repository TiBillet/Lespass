# Session 03 — Exports PDF et CSV

> **Chantier :** Bilan billetterie interne (sous-projet 1/3)
> **Spec :** `../specs/2026-04-03-bilan-billetterie-design.md`
> **Plan global :** `../plans/2026-04-03-bilan-billetterie-plan.md`
> **Dépend de :** Session 01 (`RapportBilletterieService`) + Session 02 (URLs `get_urls()` dans EventAdmin)
> **Produit :** Export PDF via WeasyPrint + export CSV délimiteur `;`

---

## Objectif

L'organisateur clique sur "Export PDF" ou "Export CSV" depuis la page bilan et télécharge un fichier. Le PDF est un document propre A4 paysage (sans graphiques JS — remplacés par des tableaux). Le CSV est exploitable dans Excel français.

---

## Contexte technique

### Pattern existant dans laboutik

Les clôtures laboutik ont déjà des exports PDF et CSV :
- PDF : `laboutik/views.py` utilise WeasyPrint avec un template HTML dédié
- CSV : délimiteur `;`, UTF-8 BOM, `csv.writer`

Réutiliser les mêmes patterns.

### WeasyPrint

Déjà installé dans le projet (utilisé par laboutik). Import : `from weasyprint import HTML`.

```python
# Pattern PDF
html_string = render_to_string("admin/event/bilan_pdf.html", contexte)
pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()
response = HttpResponse(pdf, content_type='application/pdf')
response['Content-Disposition'] = f'attachment; filename="bilan-{event.slug}.pdf"'
```

### URLs (posées en Session 02)

Les routes `/bilan/pdf/` et `/bilan/csv/` sont déjà déclarées dans `get_urls()` depuis la Session 02 (ou à ajouter maintenant si elles n'ont pas été incluses).

```
/admin/basebillet/event/{uuid}/bilan/pdf/    → vue_bilan_pdf
/admin/basebillet/event/{uuid}/bilan/csv/    → vue_bilan_csv
```

### Service disponible

```python
service = RapportBilletterieService(event)
# Toutes les méthodes retournent des dicts avec des montants en centimes
```

---

## Tâches

### 3.1 — Export CSV

**Fichiers :**
- Modifier : `Administration/admin/events.py` (ajouter vue `vue_bilan_csv`)
- Créer : `tests/pytest/test_bilan_exports.py`

**Format CSV :**
- Délimiteur : `;`
- Encodage : UTF-8 BOM (`\ufeff` en début de fichier)
- Nombres décimaux avec point (pas virgule)
- Montants en euros (centimes / 100), 2 décimales
- Sections séparées par une ligne vide + titre en majuscules

**Structure du fichier :**

```
BILAN DE BILLETTERIE
Evenement;{event.name}
Date;{event.datetime}
Jauge max;{jauge_max}

SYNTHESE
Billets vendus;{billets_vendus}
Billets scannes;{billets_scannes}
No-show;{no_show}
CA TTC;{ca_ttc / 100:.2f}
Remboursements;{remboursements / 100:.2f}
CA net;{ca_net / 100:.2f}

VENTES PAR TARIF
Tarif;Vendus;Offerts;CA TTC;HT;TVA;Rembourses
{nom};{vendus};{offerts};{ca_ttc/100:.2f};{ca_ht/100:.2f};{tva/100:.2f};{rembourses}
...

PAR MOYEN DE PAIEMENT
Moyen;Montant;Pourcentage;Nb billets
{label};{montant/100:.2f};{pourcentage};{nb_billets}
...

PAR CANAL DE VENTE
Canal;Nb billets;Montant
{label};{nb_billets};{montant/100:.2f}
...

SCANS
Scannes;{scannes}
Non scannes;{non_scannes}
Annules;{annules}

CODES PROMO
Code;Utilisations;Reduction;Manque a gagner
{nom};{utilisations};{taux_reduction}%;{manque_a_gagner/100:.2f}
...

REMBOURSEMENTS
Nombre;{nombre}
Montant total;{montant_total/100:.2f}
Taux;{taux}%
```

Les sections conditionnelles (canaux, codes promo) ne sont écrites que si les données existent.

**Vue :**

```python
def vue_bilan_csv(self, request, object_id):
    """
    Exporte le bilan de billetterie en CSV.
    / Exports ticketing report as CSV.
    """
    import csv

    event = get_object_or_404(Event, pk=object_id)
    service = RapportBilletterieService(event)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="bilan-{event.slug}.csv"'
    response.write('\ufeff')  # BOM UTF-8 pour Excel français

    writer = csv.writer(response, delimiter=';')
    # ... écriture section par section
    return response
```

**Test :**

```python
def test_export_csv(admin_client, event_with_mixed_sales):
    url = f"/admin/basebillet/event/{event_with_mixed_sales.pk}/bilan/csv/"
    response = admin_client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    content = response.content.decode('utf-8-sig')
    assert "SYNTHESE" in content
    assert "VENTES PAR TARIF" in content
    assert ";" in content  # délimiteur point-virgule
```

---

### 3.2 — Export PDF (WeasyPrint)

**Fichiers :**
- Modifier : `Administration/admin/events.py` (ajouter vue `vue_bilan_pdf`)
- Créer : `Administration/templates/admin/event/bilan_pdf.html`

**Le template PDF :**
- HTML autonome (pas d'extends Unfold — WeasyPrint ne charge pas le layout admin)
- CSS print intégré dans une balise `<style>`
- A4 paysage : `@page { size: A4 landscape; margin: 15mm; }`
- Police : sans-serif (pas de Luciole en PDF, elle n'est pas embarquée)
- Pas de Chart.js — les graphiques sont remplacés par des tableaux de données
- En-tête : nom event, date, lieu, logo (si `Configuration.img` existe)
- Pied : "Généré par TiBillet le {date}"

**Structure du template :**

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Bilan — {{ event.name }}</title>
    <style>
        @page { size: A4 landscape; margin: 15mm; }
        body { font-family: sans-serif; font-size: 11pt; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
        th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: right; }
        th { background: #f5f5f5; text-align: left; }
        h1 { font-size: 18pt; margin-bottom: 5px; }
        h2 { font-size: 13pt; margin-top: 20px; border-bottom: 1px solid #333; }
        .header-info { color: #666; margin-bottom: 15px; }
        .total-row { font-weight: bold; background: #f0f0f0; }
        .footer { margin-top: 30px; font-size: 9pt; color: #999; text-align: center; }
    </style>
</head>
<body>
    <!-- En-tête -->
    <!-- Section Synthèse (tableau, pas de chart) -->
    <!-- Section Ventes par tarif (tableau) -->
    <!-- Section Moyens de paiement (tableau) -->
    <!-- Section Canaux de vente (tableau, conditionnel) -->
    <!-- Section Scans (tableau, pas de bar chart) -->
    <!-- Section Codes promo (tableau, conditionnel) -->
    <!-- Section Remboursements -->
    <!-- Pied de page -->
</body>
</html>
```

**Vue :**

```python
def vue_bilan_pdf(self, request, object_id):
    """
    Exporte le bilan de billetterie en PDF (WeasyPrint).
    / Exports ticketing report as PDF.
    """
    from django.template.loader import render_to_string
    from weasyprint import HTML

    event = get_object_or_404(Event, pk=object_id)
    service = RapportBilletterieService(event)

    contexte = {
        "event": event,
        "synthese": service.calculer_synthese(),
        "ventes_par_tarif": service.calculer_ventes_par_tarif(),
        "par_moyen_paiement": service.calculer_par_moyen_paiement(),
        "par_canal": service.calculer_par_canal(),
        "scans": service.calculer_scans(),
        "codes_promo": service.calculer_codes_promo(),
        "remboursements": service.calculer_remboursements(),
        "date_generation": timezone.now(),
    }

    html_string = render_to_string("admin/event/bilan_pdf.html", contexte)
    pdf = HTML(string=html_string).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    nom_fichier = f"bilan-{event.slug}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
    return response
```

**Test :**

```python
def test_export_pdf(admin_client, event_with_mixed_sales):
    url = f"/admin/basebillet/event/{event_with_mixed_sales.pk}/bilan/pdf/"
    response = admin_client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert len(response.content) > 1000  # PDF non vide

def test_export_pdf_event_sans_ventes(admin_client, event_without_sales):
    url = f"/admin/basebillet/event/{event_without_sales.pk}/bilan/pdf/"
    response = admin_client.get(url)
    assert response.status_code == 200  # Le PDF se génère même sans données
```

---

### 3.3 — Boutons export dans la page bilan

**Fichier :** modifier `Administration/templates/admin/event/bilan.html` (créé en Session 02)

Ajouter en haut de la page, dans la première card :

```html
<div style="display: flex; gap: 8px; justify-content: flex-end; margin-bottom: 16px;">
    <a href="pdf/"
       style="background: var(--color-primary-600); color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 14px;">
        <span class="material-symbols-outlined" style="vertical-align: middle; font-size: 18px;" aria-hidden="true">picture_as_pdf</span>
        {% translate "Export PDF" %}
    </a>
    <a href="csv/"
       style="background: var(--color-primary-600); color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 14px;">
        <span class="material-symbols-outlined" style="vertical-align: middle; font-size: 18px;" aria-hidden="true">download</span>
        {% translate "Export CSV" %}
    </a>
</div>
```

Les URLs sont relatives (`pdf/` et `csv/`) depuis la page `/bilan/`.

---

## Vérification finale

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bilan_exports.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

---

## Résultat attendu

- Vue CSV : fichier `;` UTF-8 BOM, toutes les sections, montants en euros
- Vue PDF : A4 paysage, WeasyPrint, tableaux, pas de JS
- Boutons "Export PDF" et "Export CSV" dans la page bilan
- ~4 tests pytest exports
- 0 régression
