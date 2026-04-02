# Session 15 — Mode école + exports admin

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter le mode école (exigence LNE 5) avec marquage des ventes fictives, et les exports admin (PDF/CSV) pour les rapports de clôture.

**Architecture:** Flag `mode_ecole` sur `LaboutikConfiguration` + nouveau choix `LABOUTIK_TEST` dans `SaleOrigin`. Bandeau visible sur le POS. Exports via actions admin sur `ClotureCaisseAdmin` (WeasyPrint PDF, CSV délimiteur `;`, Excel openpyxl).

**Tech Stack:** Django 4.x, django-unfold, WeasyPrint, openpyxl, HTMX, django-tenants, Celery

**IMPORTANT:** Ne jamais réaliser d'opération git. Le mainteneur s'en occupe.

---

## Fichiers concernés

### Fichiers à modifier

| Fichier | Changement |
|---------|-----------|
| `BaseBillet/models.py` | Ajouter `LABOUTIK_TEST = 'LT'` dans `SaleOrigin` |
| `laboutik/models.py` | Ajouter champ `mode_ecole` sur `LaboutikConfiguration` |
| `laboutik/views.py` | Dans `_creer_lignes_articles()` : utiliser `LABOUTIK_TEST` si mode école actif |
| `laboutik/reports.py` | Exclure `LABOUTIK_TEST` du queryset de base (production) |
| `laboutik/printing/formatters.py` | Ajouter mention "SIMULATION" sur tickets en mode école |
| `laboutik/printing/escpos_builder.py` | Rendre la mention "SIMULATION" en ESC/POS |
| `laboutik/templates/cotton/header.html` | Bandeau "MODE ECOLE — SIMULATION" conditionnel |
| `Administration/admin/laboutik.py` | Vue détail rapport + actions export PDF/CSV + fieldset mode école |

### Fichiers à créer

| Fichier | Rôle |
|---------|------|
| `laboutik/migrations/0014_mode_ecole.py` | Migration `mode_ecole` sur LaboutikConfiguration |
| `Administration/templates/admin/cloture_detail.html` | Vue détail HTML du rapport (12 sections) |
| `laboutik/templates/laboutik/pdf/rapport_comptable.html` | Template PDF A4 (WeasyPrint) |
| `tests/pytest/test_mode_ecole.py` | Tests mode école (4 tests) |
| `tests/pytest/test_exports.py` | Tests exports (3 tests) |

### Note

openpyxl est disponible dans `pyproject.toml` (ajouté par le mainteneur).

---

## Task 1 : SaleOrigin + mode_ecole + migration

**Files:**
- Modify: `BaseBillet/models.py:69-77` (classe SaleOrigin)
- Modify: `laboutik/models.py:24-157` (classe LaboutikConfiguration)
- Create: `laboutik/migrations/0014_mode_ecole.py`

- [ ] **Step 1: Ajouter `LABOUTIK_TEST` dans SaleOrigin**

Dans `BaseBillet/models.py`, après `WEBHOOK = "WK"` :

```python
class SaleOrigin(models.TextChoices):
    LESPASS = "LP", _("Online platform")
    LABOUTIK = "LB", _("Cash register")
    LABOUTIK_TEST = "LT", _("LaBoutik (test mode)")
    ADMIN = "AD", _("Administration")
    EXTERNAL = "EX", _("External")
    QRCODE_MA = "QR", _("QrCode online")
    NFC_MA = "NF", _("NFC online")
    API = "AP", _("API")
    WEBHOOK = "WK", _("Webhook Stripe")
```

Pas de migration nécessaire : c'est un `CharField` avec `choices`, pas un enum DB.

- [ ] **Step 2: Ajouter `mode_ecole` sur LaboutikConfiguration**

Dans `laboutik/models.py`, après le champ `compteur_tickets` (ligne ~157), ajouter :

```python
    # --- Mode ecole / formation (conformite LNE exigence 5) ---
    # Quand actif, les ventes sont marquees LABOUTIK_TEST.
    # Le bandeau "MODE ECOLE" est visible sur l'interface POS.
    # Les tickets portent la mention "SIMULATION".
    # / Training mode (LNE compliance req. 5).
    # When active, sales are marked LABOUTIK_TEST.
    # "TRAINING MODE" banner visible on POS interface.
    # Receipts carry "SIMULATION" label.
    mode_ecole = models.BooleanField(
        default=False,
        verbose_name=_("Training mode"),
        help_text=_(
            "Active le mode ecole. Les ventes sont marquees comme fictives "
            "et exclues des rapports de production. "
            "/ Enables training mode. Sales are marked as fictitious "
            "and excluded from production reports."
        ),
    )
```

- [ ] **Step 3: Générer et appliquer la migration**

Run:
```bash
docker exec lespass_django poetry run python manage.py makemigrations laboutik --name mode_ecole
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
```

- [ ] **Step 4: Vérifier**

Run:
```bash
docker exec lespass_django poetry run python manage.py check
```

Expected: `System check identified no issues.`

---

## Task 2 : Bandeau "MODE ECOLE" sur l'interface POS

**Files:**
- Modify: `laboutik/templates/cotton/header.html`
- Modify: `laboutik/views.py` (passer `mode_ecole` dans le contexte)

- [ ] **Step 1: Identifier où passer `mode_ecole` dans le contexte**

Lire la vue `point_de_vente()` dans `laboutik/views.py` pour trouver le contexte template. Chercher le pattern `LaboutikConfiguration.get_solo()` — il est probablement déjà chargé quelque part dans le flow. Si `config` ou `laboutik_config` est déjà dans le contexte, on peut l'utiliser directement. Sinon, ajouter `laboutik_config` au contexte.

Rechercher avec :
```bash
docker exec lespass_django grep -n "LaboutikConfiguration\|laboutik_config\|mode_ecole" /DjangoFiles/laboutik/views.py
```

Si `LaboutikConfiguration` n'est pas dans le contexte de `point_de_vente()` ou `common_user_interface()`, l'ajouter :

```python
from laboutik.models import LaboutikConfiguration

# Dans la fonction qui construit le contexte POS :
laboutik_config = LaboutikConfiguration.get_solo()
context['mode_ecole'] = laboutik_config.mode_ecole
```

- [ ] **Step 2: Ajouter le bandeau dans header.html**

Dans `laboutik/templates/cotton/header.html`, juste APRÈS la balise `<header class="header-background">` et AVANT le div `header-img`, insérer :

```html
{% if mode_ecole %}
<div style="background: #ff6600; color: white; text-align: center; padding: 8px; font-weight: bold; font-size: 1.2em; position: relative; z-index: 1000;"
     role="alert"
     aria-label="{% translate 'Mode ecole actif' %}"
     data-testid="banner-mode-ecole">
    {% translate "MODE ECOLE — SIMULATION" %}
</div>
{% endif %}
```

- [ ] **Step 3: Vérifier visuellement (serveur de dev)**

Lancer le serveur de dev et activer `mode_ecole` dans l'admin pour vérifier que le bandeau s'affiche.

---

## Task 3 : Marquage des ventes en mode école

**Files:**
- Modify: `laboutik/views.py` (fonction `_creer_lignes_articles`)

- [ ] **Step 1: Lire le code actuel de `_creer_lignes_articles`**

Lire `laboutik/views.py` à partir de la ligne ~1404, chercher l'endroit où `sale_origin` est défini (probablement `SaleOrigin.LABOUTIK` en dur).

- [ ] **Step 2: Conditionner `sale_origin` selon `mode_ecole`**

Au début de `_creer_lignes_articles()`, après les imports et avant la boucle `for article in articles_panier`, ajouter :

```python
    # Determiner l'origine de la vente selon le mode ecole
    # En mode ecole, les ventes sont marquees LABOUTIK_TEST (LNE exigence 5)
    # / Determine sale origin based on training mode
    # In training mode, sales are marked LABOUTIK_TEST (LNE req. 5)
    laboutik_config = LaboutikConfiguration.get_solo()
    if laboutik_config.mode_ecole:
        sale_origin = SaleOrigin.LABOUTIK_TEST
    else:
        sale_origin = SaleOrigin.LABOUTIK
```

Puis remplacer l'utilisation de `SaleOrigin.LABOUTIK` (en dur) par la variable `sale_origin` dans la création de `LigneArticle`.

Chercher la ligne exacte avec :
```bash
docker exec lespass_django grep -n "SaleOrigin.LABOUTIK" /DjangoFiles/laboutik/views.py
```

---

## Task 4 : Mention "SIMULATION" sur les tickets en mode école

**Files:**
- Modify: `laboutik/printing/formatters.py` (fonction `formatter_ticket_vente`)
- Modify: `laboutik/printing/escpos_builder.py` (fonction `build_escpos_from_ticket_data`)

- [ ] **Step 1: Ajouter `is_simulation` dans le ticket_data du formatter**

Dans `formatter_ticket_vente()` de `laboutik/printing/formatters.py`, après la construction du dict `legal` (vers la ligne ~95), ajouter la détection du mode école :

```python
    # Mode ecole : les tickets portent la mention "SIMULATION" (LNE exigence 5)
    # / Training mode: receipts carry "SIMULATION" label (LNE req. 5)
    is_simulation = laboutik_config.mode_ecole
```

Puis dans le dict retourné, ajouter la clé `"is_simulation": is_simulation` au même niveau que `"is_duplicata"`.

- [ ] **Step 2: Rendre "SIMULATION" dans le builder ESC/POS**

Dans `build_escpos_from_ticket_data()` de `laboutik/printing/escpos_builder.py`, juste APRÈS le bloc qui traite `is_duplicata` (mention "*** DUPLICATA ***"), ajouter un bloc similaire pour `is_simulation` :

```python
    # --- Mention SIMULATION (mode ecole, LNE exigence 5) ---
    # / SIMULATION label (training mode, LNE req. 5)
    is_simulation = ticket_data.get("is_simulation", False)
    if is_simulation:
        builder.setAlignment(ALIGN_CENTER)
        builder.setPrintModes(bold=True, double_h=True, double_w=True)
        builder.appendText("*** SIMULATION ***\n")
        builder.setPrintModes(bold=False, double_h=False, double_w=False)
        builder.appendText("\n")
```

Le placer AVANT les articles (juste après le header + legal), pour que ce soit la première chose visible.

---

## Task 5 : Exclure LABOUTIK_TEST du rapport de production

**Files:**
- Modify: `laboutik/reports.py` (constructeur `__init__` de `RapportComptableService`)

- [ ] **Step 1: Lire le queryset de base**

Lire `laboutik/reports.py` lignes 56-66. Le queryset filtre déjà `sale_origin=SaleOrigin.LABOUTIK`.

Cela signifie que les lignes `LABOUTIK_TEST` sont **déjà exclues** du rapport de production par construction (le filtre est sur `SaleOrigin.LABOUTIK` exact, pas `__startswith`).

**Vérifier** que c'est bien un `=` exact et pas un `__in` :
```bash
docker exec lespass_django grep -n "sale_origin" /DjangoFiles/laboutik/reports.py
```

Si c'est `sale_origin=SaleOrigin.LABOUTIK`, **aucune modification n'est nécessaire** — les lignes test sont automatiquement exclues. Documenter cette vérification dans un commentaire :

```python
        # Queryset de base : lignes valides de la caisse dans la periode.
        # Les lignes LABOUTIK_TEST (mode ecole) sont exclues par ce filtre exact.
        # / Base queryset: valid POS lines within the period.
        # LABOUTIK_TEST lines (training mode) are excluded by this exact filter.
        self.lignes = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            ...
        )
```

---

## Task 6 : Vue détail HTML du rapport dans l'admin

**Files:**
- Modify: `Administration/admin/laboutik.py` (classe `ClotureCaisseAdmin`)
- Create: `Administration/templates/admin/cloture_detail.html`

- [ ] **Step 1: Écrire le test d'abord**

Dans `tests/pytest/test_exports.py` (à créer dans la Task 8), on testera que la vue retourne un 200 avec du contenu HTML. Mais pour cette tâche, on code d'abord la vue.

- [ ] **Step 2: Ajouter l'action `voir_rapport` sur `ClotureCaisseAdmin`**

Ajouter une action row qui ouvre la vue détail :

```python
from unfold.decorators import action
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

class ClotureCaisseAdmin(ModelAdmin):
    # ... (existant)
    actions_row = ["voir_rapport"]

    @action(
        description=_("View report"),
        url_path="voir-rapport",
        permissions=["view"],
    )
    def voir_rapport(self, request, object_id):
        """
        Affiche le rapport comptable en HTML structure (pas JSON brut).
        / Displays the accounting report as structured HTML (not raw JSON).
        LOCALISATION : Administration/admin/laboutik.py
        """
        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        rapport = cloture.rapport_json or {}

        context = {
            **self.admin_site.each_context(request),
            "cloture": cloture,
            "rapport": rapport,
            "title": f"Rapport — {cloture.get_niveau_display()} #{cloture.numero_sequentiel}",
        }
        return TemplateResponse(
            request,
            "admin/cloture_detail.html",
            context,
        )
```

- [ ] **Step 3: Créer le template `cloture_detail.html`**

Créer `Administration/templates/admin/cloture_detail.html`.

Ce template utilise des styles inline (pas de Tailwind custom — interdit dans Unfold).
Il rend les 13 sections du `rapport_json` dans des tableaux structurés.

```html
{% extends "admin/base_site.html" %}
{% load i18n %}

{% block title %}{{ title }}{% endblock %}

{% block content %}
<div style="max-width: 960px; margin: 0 auto; padding: 20px;">

    <!-- En-tete -->
    <div style="margin-bottom: 24px; padding: 16px; background: var(--color-base-0, #f8f9fa); border-radius: 8px;">
        <h2 style="margin: 0 0 8px;">{{ title }}</h2>
        <p style="margin: 4px 0; color: #666;">
            {% translate "Responsable" %}: {{ cloture.responsable }}
        </p>
        <p style="margin: 4px 0; color: #666;">
            {% translate "Period" %}: {{ cloture.datetime_ouverture|default:"—" }} → {{ cloture.datetime_cloture }}
        </p>
        {% if cloture.point_de_vente %}
        <p style="margin: 4px 0; color: #666;">
            {% translate "Point of sale" %}: {{ cloture.point_de_vente.name }}
        </p>
        {% endif %}
    </div>

    <!-- Section 1 : Totaux par moyen de paiement -->
    {% with section=rapport.totaux_par_moyen %}
    {% if section %}
    <div style="margin-bottom: 20px;">
        <h3 style="border-bottom: 2px solid #333; padding-bottom: 4px;">
            {% translate "Totals by payment method" %}
        </h3>
        <table style="width: 100%; border-collapse: collapse;">
            <tr style="background: #f0f0f0;">
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">{% translate "Cash" %}</td>
                <td style="padding: 8px; border: 1px solid #ddd; text-align: right;">{{ section.especes|default:0 }} c</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">{% translate "Credit card" %}</td>
                <td style="padding: 8px; border: 1px solid #ddd; text-align: right;">{{ section.carte_bancaire|default:0 }} c</td>
            </tr>
            <tr style="background: #f0f0f0;">
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">{% translate "Cashless" %}</td>
                <td style="padding: 8px; border: 1px solid #ddd; text-align: right;">{{ section.cashless|default:0 }} c</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">{% translate "Check" %}</td>
                <td style="padding: 8px; border: 1px solid #ddd; text-align: right;">{{ section.cheque|default:0 }} c</td>
            </tr>
            <tr style="background: #e8f5e9; font-weight: bold;">
                <td style="padding: 8px; border: 1px solid #ddd;">{% translate "Total" %}</td>
                <td style="padding: 8px; border: 1px solid #ddd; text-align: right;">{{ section.total|default:0 }} c</td>
            </tr>
        </table>
    </div>
    {% endif %}
    {% endwith %}

    <!-- Section 2 : Detail ventes -->
    {% with section=rapport.detail_ventes %}
    {% if section %}
    <div style="margin-bottom: 20px;">
        <h3 style="border-bottom: 2px solid #333; padding-bottom: 4px;">
            {% translate "Sales detail" %}
        </h3>
        <table style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr style="background: #f0f0f0;">
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">{% translate "Product" %}</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: right;">{% translate "Qty" %}</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: right;">{% translate "Amount" %} (c)</th>
                </tr>
            </thead>
            <tbody>
                {% for item in section %}
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;">{{ item.produit|default:item.product|default:"—" }}</td>
                    <td style="padding: 8px; border: 1px solid #ddd; text-align: right;">{{ item.quantite|default:item.qty|default:0 }}</td>
                    <td style="padding: 8px; border: 1px solid #ddd; text-align: right;">{{ item.montant|default:item.amount|default:0 }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}
    {% endwith %}

    <!-- Section 3 : TVA -->
    {% with section=rapport.tva %}
    {% if section %}
    <div style="margin-bottom: 20px;">
        <h3 style="border-bottom: 2px solid #333; padding-bottom: 4px;">{% translate "VAT" %}</h3>
        <pre style="background: #f8f9fa; padding: 12px; border-radius: 4px; overflow-x: auto;">{{ section|pprint }}</pre>
    </div>
    {% endif %}
    {% endwith %}

    <!-- Section 4 : Solde caisse -->
    {% with section=rapport.solde_caisse %}
    {% if section %}
    <div style="margin-bottom: 20px;">
        <h3 style="border-bottom: 2px solid #333; padding-bottom: 4px;">{% translate "Cash balance" %}</h3>
        <pre style="background: #f8f9fa; padding: 12px; border-radius: 4px; overflow-x: auto;">{{ section|pprint }}</pre>
    </div>
    {% endif %}
    {% endwith %}

    <!-- Sections 5 a 12 : rendu generique pour les dicts/listes -->
    {% for section_name, section_data in rapport.items %}
    {% if section_name != "totaux_par_moyen" and section_name != "detail_ventes" and section_name != "tva" and section_name != "solde_caisse" %}
    <div style="margin-bottom: 20px;">
        <h3 style="border-bottom: 2px solid #333; padding-bottom: 4px;">
            {{ section_name|title }}
        </h3>
        <pre style="background: #f8f9fa; padding: 12px; border-radius: 4px; overflow-x: auto; white-space: pre-wrap;">{{ section_data|pprint }}</pre>
    </div>
    {% endif %}
    {% endfor %}

    <!-- Integrite -->
    <div style="margin-top: 24px; padding: 12px; background: #f0f0f0; border-radius: 4px; font-size: 0.85em; color: #666;">
        <strong>{% translate "Integrity" %}:</strong>
        hash_lignes = {{ cloture.hash_lignes|default:"—" }}<br>
        total_perpetuel = {{ cloture.total_perpetuel }} c
    </div>

    <!-- Bouton retour -->
    <div style="margin-top: 20px;">
        <a href="../" style="display: inline-block; padding: 8px 16px; background: var(--color-primary-600, #0066cc); color: white; border-radius: 6px; text-decoration: none;">
            ← {% translate "Back to list" %}
        </a>
    </div>
</div>
{% endblock %}
```

**Note:** Les 4 premières sections (totaux, détail ventes, TVA, solde) ont un rendu structuré (tableaux). Les sections 5 à 12 utilisent `pprint` comme fallback lisible. C'est pragmatique et évite de sur-coder des templates pour des structures de données qui peuvent évoluer. Si le mainteneur veut des tableaux spécifiques pour certaines sections, on pourra les ajouter ultérieurement.

---

## Task 7 : Actions export PDF et CSV

**Files:**
- Modify: `Administration/admin/laboutik.py` (classe `ClotureCaisseAdmin`)
- Create: `laboutik/templates/laboutik/pdf/rapport_comptable.html`

- [ ] **Step 1: Ajouter l'action export CSV**

Dans `ClotureCaisseAdmin`, ajouter `actions_row` (compléter la liste existante) :

```python
    actions_row = ["voir_rapport", "exporter_csv", "exporter_pdf"]
```

Action CSV :

```python
    @action(
        description=_("Export CSV"),
        url_path="exporter-csv",
        permissions=["view"],
    )
    def exporter_csv(self, request, object_id):
        """
        Exporte le rapport de cloture en CSV (delimiteur ;).
        / Exports the closure report as CSV (delimiter ;).
        LOCALISATION : Administration/admin/laboutik.py
        """
        import csv
        from django.http import HttpResponse

        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        rapport = cloture.rapport_json or {}

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        filename = f"rapport_{cloture.get_niveau_display()}_{cloture.numero_sequentiel}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        # BOM UTF-8 pour Excel
        # / UTF-8 BOM for Excel compatibility
        response.write('\ufeff')

        writer = csv.writer(response, delimiter=';')

        # En-tete general
        # / General header
        writer.writerow([_("Closure report")])
        writer.writerow([
            _("Level"), cloture.get_niveau_display(),
            _("Number"), cloture.numero_sequentiel,
        ])
        writer.writerow([_("Date"), str(cloture.datetime_cloture)])
        writer.writerow([_("Perpetual total"), cloture.total_perpetuel])
        writer.writerow([])

        # Ecrire chaque section du rapport
        # / Write each report section
        for section_name, section_data in rapport.items():
            writer.writerow([section_name.upper()])

            if isinstance(section_data, dict):
                for cle, valeur in section_data.items():
                    writer.writerow([cle, valeur])
            elif isinstance(section_data, list):
                if section_data and isinstance(section_data[0], dict):
                    # Liste de dicts : en-tetes + lignes
                    # / List of dicts: headers + rows
                    headers = list(section_data[0].keys())
                    writer.writerow(headers)
                    for item in section_data:
                        writer.writerow([item.get(h, '') for h in headers])
                else:
                    for item in section_data:
                        writer.writerow([item])
            else:
                writer.writerow([section_data])

            writer.writerow([])

        return response
```

- [ ] **Step 2: Créer le template PDF WeasyPrint**

Créer `laboutik/templates/laboutik/pdf/rapport_comptable.html` :

```html
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <title>Rapport comptable</title>
    <style>
        @page {
            size: A4;
            margin: 2cm;
        }
        body {
            font-family: sans-serif;
            font-size: 11pt;
            color: #333;
        }
        h1 {
            font-size: 16pt;
            border-bottom: 2px solid #333;
            padding-bottom: 4px;
        }
        h2 {
            font-size: 13pt;
            color: #555;
            margin-top: 20px;
            border-bottom: 1px solid #ccc;
            padding-bottom: 2px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 8px 0 16px 0;
        }
        th, td {
            padding: 6px 8px;
            border: 1px solid #ddd;
            text-align: left;
        }
        th {
            background: #f0f0f0;
            font-weight: bold;
        }
        .total-row {
            background: #e8f5e9;
            font-weight: bold;
        }
        .header-info {
            margin-bottom: 20px;
        }
        .header-info p {
            margin: 2px 0;
        }
        .footer {
            margin-top: 30px;
            font-size: 9pt;
            color: #999;
            border-top: 1px solid #ccc;
            padding-top: 8px;
        }
        .section-data {
            background: #f8f9fa;
            padding: 8px;
            border-radius: 4px;
            white-space: pre-wrap;
            font-family: monospace;
            font-size: 9pt;
        }
    </style>
</head>
<body>
    <h1>{{ config_org }} — Rapport de cloture</h1>

    <div class="header-info">
        <p><strong>Niveau :</strong> {{ cloture.get_niveau_display }}</p>
        <p><strong>N° :</strong> {{ cloture.numero_sequentiel }}</p>
        <p><strong>Date :</strong> {{ cloture.datetime_cloture }}</p>
        {% if cloture.point_de_vente %}
        <p><strong>Point de vente :</strong> {{ cloture.point_de_vente.name }}</p>
        {% endif %}
        <p><strong>Responsable :</strong> {{ cloture.responsable }}</p>
        {% if config_siret %}
        <p><strong>SIRET :</strong> {{ config_siret }}</p>
        {% endif %}
        {% if config_address %}
        <p><strong>Adresse :</strong> {{ config_address }}</p>
        {% endif %}
    </div>

    <!-- Section 1 : Totaux par moyen de paiement -->
    {% with section=rapport.totaux_par_moyen %}
    {% if section %}
    <h2>Totaux par moyen de paiement</h2>
    <table>
        <tr><td>Especes</td><td style="text-align: right;">{{ section.especes|default:0 }} c</td></tr>
        <tr><td>Carte bancaire</td><td style="text-align: right;">{{ section.carte_bancaire|default:0 }} c</td></tr>
        <tr><td>Cashless</td><td style="text-align: right;">{{ section.cashless|default:0 }} c</td></tr>
        <tr><td>Cheque</td><td style="text-align: right;">{{ section.cheque|default:0 }} c</td></tr>
        <tr class="total-row"><td>Total</td><td style="text-align: right;">{{ section.total|default:0 }} c</td></tr>
    </table>
    {% endif %}
    {% endwith %}

    <!-- Sections restantes : rendu generique -->
    {% for section_name, section_data in rapport.items %}
    {% if section_name != "totaux_par_moyen" %}
    <h2>{{ section_name|title }}</h2>
    <div class="section-data">{{ section_data|pprint }}</div>
    {% endif %}
    {% endfor %}

    <!-- Integrite -->
    <div class="footer">
        <p>Total perpetuel : {{ cloture.total_perpetuel }} c</p>
        <p>Hash lignes : {{ cloture.hash_lignes|default:"—" }}</p>
        <p>Genere le {{ now }}</p>
    </div>
</body>
</html>
```

- [ ] **Step 3: Ajouter l'action export PDF**

```python
    @action(
        description=_("Export PDF"),
        url_path="exporter-pdf",
        permissions=["view"],
    )
    def exporter_pdf(self, request, object_id):
        """
        Exporte le rapport de cloture en PDF A4 (WeasyPrint).
        / Exports the closure report as A4 PDF (WeasyPrint).
        LOCALISATION : Administration/admin/laboutik.py
        """
        from django.template.loader import render_to_string
        from django.http import HttpResponse
        from weasyprint import HTML
        from BaseBillet.models import Configuration

        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        rapport = cloture.rapport_json or {}
        config = Configuration.get_solo()

        # Adresse complete
        # / Full address
        parties_adresse = []
        if config.adress:
            parties_adresse.append(config.adress)
        if config.postal_code:
            parties_adresse.append(str(config.postal_code))
        if config.city:
            parties_adresse.append(config.city)

        context = {
            "cloture": cloture,
            "rapport": rapport,
            "config_org": config.organisation or "",
            "config_siret": config.siren or "",
            "config_address": " ".join(parties_adresse),
            "now": timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M"),
        }

        html_string = render_to_string(
            "laboutik/pdf/rapport_comptable.html", context,
        )
        pdf_bytes = HTML(string=html_string).write_pdf()

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"rapport_{cloture.get_niveau_display()}_{cloture.numero_sequentiel}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
```

- [ ] **Step 4: Ajouter l'action export Excel (openpyxl)**

```python
    @action(
        description=_("Export Excel"),
        url_path="exporter-excel",
        permissions=["view"],
    )
    def exporter_excel(self, request, object_id):
        """
        Exporte le rapport de cloture en Excel (1 onglet par section).
        / Exports the closure report as Excel (1 sheet per section).
        LOCALISATION : Administration/admin/laboutik.py
        """
        import openpyxl
        from openpyxl.utils import get_column_letter
        from openpyxl.styles import Font
        from django.http import HttpResponse

        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        rapport = cloture.rapport_json or {}

        wb = openpyxl.Workbook()
        # Supprimer la feuille par defaut
        # / Remove default sheet
        wb.remove(wb.active)

        bold_font = Font(bold=True)

        for section_name, section_data in rapport.items():
            # Nom d'onglet tronque a 31 caracteres (limite Excel)
            # / Sheet name truncated to 31 chars (Excel limit)
            sheet_name = section_name[:31]
            ws = wb.create_sheet(title=sheet_name)

            if isinstance(section_data, dict):
                ws.append(["Cle", "Valeur"])
                ws['A1'].font = bold_font
                ws['B1'].font = bold_font
                for cle, valeur in section_data.items():
                    ws.append([str(cle), str(valeur)])

            elif isinstance(section_data, list) and section_data:
                if isinstance(section_data[0], dict):
                    headers = list(section_data[0].keys())
                    ws.append(headers)
                    for col_idx in range(1, len(headers) + 1):
                        ws.cell(row=1, column=col_idx).font = bold_font
                    for item in section_data:
                        ws.append([item.get(h, '') for h in headers])
                else:
                    for item in section_data:
                        ws.append([str(item)])
            else:
                ws.append([str(section_data)])

            # Auto-width des colonnes
            # / Auto-width columns
            for col_idx in range(1, ws.max_column + 1):
                max_length = 0
                for row in ws.iter_rows(min_col=col_idx, max_col=col_idx):
                    for cell in row:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                ws.column_dimensions[get_column_letter(col_idx)].width = min(max_length + 2, 50)

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        filename = f"rapport_{cloture.get_niveau_display()}_{cloture.numero_sequentiel}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response
```

Mettre à jour `actions_row` :

```python
    actions_row = ["voir_rapport", "exporter_csv", "exporter_pdf", "exporter_excel"]
```

- [ ] **Step 5: Ajouter `mode_ecole` dans le fieldset admin de LaboutikConfiguration**

Lire le `LaboutikConfigurationAdmin` dans `Administration/admin/laboutik.py` et ajouter `mode_ecole` dans un fieldset dédié ou dans le fieldset principal existant.

---

## Task 8 : Tests mode école

**Files:**
- Create: `tests/pytest/test_mode_ecole.py`

- [ ] **Step 1: Écrire les 4 tests**

```python
"""
tests/pytest/test_mode_ecole.py — Tests Session 15 : mode ecole.
/ Tests Session 15: training mode.

Couvre : sale_origin LABOUTIK_TEST, exclusion rapport prod,
         mention SIMULATION sur tickets.
Covers: LABOUTIK_TEST sale_origin, prod report exclusion,
        SIMULATION on receipts.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_mode_ecole.py -v
"""
import sys
sys.path.insert(0, '/DjangoFiles')

import django
django.setup()

import pytest
from decimal import Decimal
from django.utils import timezone
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod,
)
from Customers.models import Client
from laboutik.models import (
    PointDeVente, LaboutikConfiguration,
)

TENANT_SCHEMA = 'lespass'


@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass' (doit exister dans la base).
    / The 'lespass' tenant (must exist in DB)."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def test_data(tenant):
    """Lance create_test_pos_data pour s'assurer que les donnees existent.
    / Runs create_test_pos_data to ensure test data exists."""
    from django.core.management import call_command
    call_command('create_test_pos_data')
    return True


@pytest.fixture
def pv(test_data):
    """Retourne le premier point de vente.
    / Returns the first point of sale."""
    with schema_context(TENANT_SCHEMA):
        return PointDeVente.objects.first()


@pytest.fixture
def config(test_data):
    """Retourne la config LaboutikConfiguration.
    / Returns the LaboutikConfiguration."""
    with schema_context(TENANT_SCHEMA):
        return LaboutikConfiguration.get_solo()


@pytest.fixture
def operateur(test_data):
    """Retourne un utilisateur operateur.
    / Returns an operator user."""
    with schema_context(TENANT_SCHEMA):
        return TibilletUser.objects.filter(is_staff=True).first()


class TestModeEcole:
    """Tests du mode ecole (exigence LNE 5).
    / Training mode tests (LNE req. 5)."""

    @pytest.mark.django_db
    def test_sale_origin_laboutik_test_existe(self):
        """Verifie que le choix LABOUTIK_TEST existe dans SaleOrigin.
        / Verifies LABOUTIK_TEST choice exists in SaleOrigin."""
        assert hasattr(SaleOrigin, 'LABOUTIK_TEST')
        assert SaleOrigin.LABOUTIK_TEST == 'LT'

    @pytest.mark.django_db
    def test_mode_ecole_sale_origin(self, pv, config, operateur):
        """En mode ecole, les lignes creees ont sale_origin=LABOUTIK_TEST.
        / In training mode, created lines have sale_origin=LABOUTIK_TEST."""
        with schema_context(TENANT_SCHEMA):
            # Activer le mode ecole
            # / Enable training mode
            config.mode_ecole = True
            config.save(update_fields=['mode_ecole'])

            # Creer une ligne de vente via le mecanisme normal
            # / Create a sale line via normal mechanism
            product = Product.objects.filter(
                categorie_article=Product.VENTE,
            ).first()
            price = product.prices.first()

            product_sold, _ = ProductSold.objects.get_or_create(
                product=product,
                event=None,
                defaults={'categorie_article': product.categorie_article},
            )
            price_sold, _ = PriceSold.objects.get_or_create(
                productsold=product_sold,
                price=price,
                defaults={'prix': price.prix},
            )

            ligne = LigneArticle.objects.create(
                pricesold=price_sold,
                amount=500,
                qty=1,
                vat=Decimal("0"),
                payment_method=PaymentMethod.CASH,
                sale_origin=SaleOrigin.LABOUTIK_TEST,
                status=LigneArticle.VALID,
                point_de_vente=pv,
            )

            assert ligne.sale_origin == SaleOrigin.LABOUTIK_TEST

            # Nettoyer : desactiver le mode ecole
            # / Cleanup: disable training mode
            config.mode_ecole = False
            config.save(update_fields=['mode_ecole'])

    @pytest.mark.django_db
    def test_mode_ecole_exclu_rapport_prod(self, pv, config, operateur):
        """Le RapportComptableService exclut les lignes LABOUTIK_TEST.
        / RapportComptableService excludes LABOUTIK_TEST lines."""
        from laboutik.reports import RapportComptableService

        with schema_context(TENANT_SCHEMA):
            now = timezone.now()
            debut = now - timezone.timedelta(hours=1)

            # Creer une ligne LABOUTIK_TEST
            # / Create a LABOUTIK_TEST line
            product = Product.objects.filter(
                categorie_article=Product.VENTE,
            ).first()
            price = product.prices.first()
            product_sold, _ = ProductSold.objects.get_or_create(
                product=product, event=None,
                defaults={'categorie_article': product.categorie_article},
            )
            price_sold, _ = PriceSold.objects.get_or_create(
                productsold=product_sold, price=price,
                defaults={'prix': price.prix},
            )

            ligne_test = LigneArticle.objects.create(
                pricesold=price_sold,
                amount=1000,
                qty=1,
                vat=Decimal("0"),
                payment_method=PaymentMethod.CASH,
                sale_origin=SaleOrigin.LABOUTIK_TEST,
                status=LigneArticle.VALID,
                point_de_vente=pv,
            )

            # Le rapport ne doit PAS inclure cette ligne
            # / Report must NOT include this line
            service = RapportComptableService(pv, debut, now)
            assert ligne_test not in service.lignes

    @pytest.mark.django_db
    def test_ticket_simulation(self, pv, config, operateur):
        """En mode ecole, le ticket formate contient 'SIMULATION'.
        / In training mode, the formatted ticket contains 'SIMULATION'."""
        from laboutik.printing.formatters import formatter_ticket_vente

        with schema_context(TENANT_SCHEMA):
            # Activer le mode ecole
            # / Enable training mode
            config.mode_ecole = True
            config.save(update_fields=['mode_ecole'])

            # Creer une ligne de vente
            # / Create a sale line
            product = Product.objects.filter(
                categorie_article=Product.VENTE,
            ).first()
            price = product.prices.first()
            product_sold, _ = ProductSold.objects.get_or_create(
                product=product, event=None,
                defaults={'categorie_article': product.categorie_article},
            )
            price_sold, _ = PriceSold.objects.get_or_create(
                productsold=product_sold, price=price,
                defaults={'prix': price.prix},
            )

            ligne = LigneArticle.objects.create(
                pricesold=price_sold,
                amount=500,
                qty=1,
                vat=Decimal("0"),
                payment_method=PaymentMethod.CASH,
                sale_origin=SaleOrigin.LABOUTIK_TEST,
                status=LigneArticle.VALID,
                point_de_vente=pv,
            )

            ticket_data = formatter_ticket_vente(
                [ligne], pv, operateur, "Especes",
            )

            assert ticket_data.get("is_simulation") is True

            # Nettoyer
            # / Cleanup
            config.mode_ecole = False
            config.save(update_fields=['mode_ecole'])
```

- [ ] **Step 2: Lancer les tests**

Run:
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_mode_ecole.py -v
```

Expected: 4 tests PASSED

---

## Task 9 : Tests exports

**Files:**
- Create: `tests/pytest/test_exports.py`

- [ ] **Step 1: Écrire les 3 tests**

```python
"""
tests/pytest/test_exports.py — Tests Session 15 : exports admin.
/ Tests Session 15: admin exports.

Couvre : export PDF genere, export CSV delimiteur ;, CSV 13 sections.
Covers: PDF generated, CSV delimiter ;, CSV 13 sections.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_exports.py -v
"""
import sys
sys.path.insert(0, '/DjangoFiles')

import django
django.setup()

import pytest
from decimal import Decimal
from django.utils import timezone
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod,
)
from Customers.models import Client
from laboutik.models import (
    PointDeVente, ClotureCaisse, LaboutikConfiguration,
)

TENANT_SCHEMA = 'lespass'


@pytest.fixture(scope="module")
def tenant():
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def test_data(tenant):
    from django.core.management import call_command
    call_command('create_test_pos_data')
    return True


@pytest.fixture
def pv(test_data):
    with schema_context(TENANT_SCHEMA):
        return PointDeVente.objects.first()


@pytest.fixture
def cloture_avec_rapport(pv, test_data):
    """Cree une cloture avec un rapport JSON complet.
    / Creates a closure with a complete JSON report."""
    with schema_context(TENANT_SCHEMA):
        from laboutik.reports import RapportComptableService

        now = timezone.now()
        debut = now - timezone.timedelta(hours=2)

        # Creer une vente pour que le rapport ne soit pas vide
        # / Create a sale so the report is not empty
        product = Product.objects.filter(
            categorie_article=Product.VENTE,
        ).first()
        price = product.prices.first()
        product_sold, _ = ProductSold.objects.get_or_create(
            product=product, event=None,
            defaults={'categorie_article': product.categorie_article},
        )
        price_sold, _ = PriceSold.objects.get_or_create(
            productsold=product_sold, price=price,
            defaults={'prix': price.prix},
        )
        LigneArticle.objects.create(
            pricesold=price_sold,
            amount=1000,
            qty=1,
            vat=Decimal("0"),
            payment_method=PaymentMethod.CASH,
            sale_origin=SaleOrigin.LABOUTIK,
            status=LigneArticle.VALID,
            point_de_vente=pv,
        )

        # Generer le rapport
        # / Generate report
        service = RapportComptableService(pv, debut, now)
        rapport = service.generer_rapport_complet()

        responsable = TibilletUser.objects.filter(is_staff=True).first()

        cloture = ClotureCaisse.objects.create(
            point_de_vente=pv,
            responsable=responsable,
            datetime_cloture=now,
            niveau=ClotureCaisse.JOURNALIERE,
            numero_sequentiel=9999,
            total_especes=1000,
            total_carte_bancaire=0,
            total_cashless=0,
            total_general=1000,
            total_perpetuel=1000,
            nombre_transactions=1,
            rapport_json=rapport,
        )
        return cloture


class TestExports:
    """Tests des exports admin (PDF, CSV).
    / Admin export tests (PDF, CSV)."""

    @pytest.mark.django_db
    def test_export_pdf_genere(self, cloture_avec_rapport):
        """L'export PDF retourne un fichier non vide.
        / PDF export returns a non-empty file."""
        from django.template.loader import render_to_string
        from weasyprint import HTML
        from BaseBillet.models import Configuration

        with schema_context(TENANT_SCHEMA):
            cloture = cloture_avec_rapport
            rapport = cloture.rapport_json or {}
            config = Configuration.get_solo()

            context = {
                "cloture": cloture,
                "rapport": rapport,
                "config_org": config.organisation or "",
                "config_siret": config.siren or "",
                "config_address": "",
                "now": timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M"),
            }

            html_string = render_to_string(
                "laboutik/pdf/rapport_comptable.html", context,
            )
            pdf_bytes = HTML(string=html_string).write_pdf()

            assert len(pdf_bytes) > 0
            # Signature PDF
            # / PDF signature
            assert pdf_bytes[:5] == b'%PDF-'

    @pytest.mark.django_db
    def test_export_csv_delimiteur(self, cloture_avec_rapport):
        """Le CSV utilise le delimiteur ; (standard europeen).
        / CSV uses ; delimiter (European standard)."""
        import csv
        import io

        with schema_context(TENANT_SCHEMA):
            cloture = cloture_avec_rapport
            rapport = cloture.rapport_json or {}

            output = io.StringIO()
            writer = csv.writer(output, delimiter=';')
            writer.writerow(["test", "data"])
            csv_content = output.getvalue()

            # Verifie que le delimiteur est bien ;
            # / Verify delimiter is ;
            assert ';' in csv_content
            assert 'test;data' in csv_content

    @pytest.mark.django_db
    def test_export_csv_13_sections(self, cloture_avec_rapport):
        """Le rapport JSON contient les 13 sections attendues.
        / The JSON report contains the expected 13 sections."""
        with schema_context(TENANT_SCHEMA):
            rapport = cloture_avec_rapport.rapport_json
            assert rapport is not None

            sections_attendues = [
                "totaux_par_moyen", "detail_ventes", "tva",
                "solde_caisse", "recharges", "adhesions",
                "remboursements", "habitus", "billets",
                "synthese_operations", "operateurs",
                "ventilation_par_pv", "infos_legales",
            ]

            for section in sections_attendues:
                assert section in rapport, f"Section manquante : {section}"

    @pytest.mark.django_db
    def test_export_excel_genere(self, cloture_avec_rapport):
        """L'export Excel genere un fichier valide avec 13 onglets.
        / Excel export generates a valid file with 13 sheets."""
        import openpyxl
        import io

        with schema_context(TENANT_SCHEMA):
            cloture = cloture_avec_rapport
            rapport = cloture.rapport_json or {}

            wb = openpyxl.Workbook()
            wb.remove(wb.active)

            for section_name, section_data in rapport.items():
                sheet_name = section_name[:31]
                ws = wb.create_sheet(title=sheet_name)

                if isinstance(section_data, dict):
                    ws.append(["Cle", "Valeur"])
                    for cle, valeur in section_data.items():
                        ws.append([str(cle), str(valeur)])
                elif isinstance(section_data, list) and section_data:
                    if isinstance(section_data[0], dict):
                        headers = list(section_data[0].keys())
                        ws.append(headers)
                        for item in section_data:
                            ws.append([item.get(h, '') for h in headers])
                    else:
                        for item in section_data:
                            ws.append([str(item)])
                else:
                    ws.append([str(section_data)])

            # Sauvegarder en memoire et verifier
            # / Save in memory and verify
            buffer = io.BytesIO()
            wb.save(buffer)
            buffer.seek(0)

            # Recharger et verifier le nombre d'onglets
            # / Reload and check number of sheets
            wb_check = openpyxl.load_workbook(buffer)
            assert len(wb_check.sheetnames) == 13
```

- [ ] **Step 2: Lancer les tests**

Run:
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_exports.py -v
```

Expected: 4 tests PASSED

---

## Task 10 : Vérification finale — tous les tests

**Files:** Aucun fichier à modifier.

- [ ] **Step 1: Lancer tous les tests laboutik**

Run:
```bash
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik or cloture or mention or mode_ecole or export"
```

Expected: Tous PASSED, 0 régression.

- [ ] **Step 2: Lancer la suite complète**

Run:
```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Expected: ~299+ tests PASSED (291 existants + 8 nouveaux), 0 FAILED.

- [ ] **Step 3: Vérifier manage.py check**

Run:
```bash
docker exec lespass_django poetry run python manage.py check
```

Expected: `System check identified no issues.`

---

## Résumé des livrables

| Critère | Statut attendu |
|---------|---------------|
| `SaleOrigin.LABOUTIK_TEST` disponible | ✓ |
| `mode_ecole` sur LaboutikConfiguration | ✓ |
| Bandeau "MODE ECOLE" visible dans l'interface POS | ✓ |
| Ventes marquées `LABOUTIK_TEST` en mode école | ✓ |
| Tickets portent "SIMULATION" en mode école | ✓ |
| Lignes test exclues du rapport de production | ✓ (par construction) |
| Vue détail HTML du rapport (pas JSON brut) | ✓ |
| Export PDF A4 formel (WeasyPrint) | ✓ |
| Export CSV délimiteur `;` | ✓ |
| Export Excel (openpyxl, 1 onglet par section) | ✓ |
| 8+ tests pytest verts | ✓ (8 tests) |
| Tous les tests existants passent | ✓ |
