# Rapport temps reel — Session en cours

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un bouton "Rapport en cours" sur la changelist admin des clotures de caisse qui ouvre, dans un nouvel onglet, un rapport comptable complet calcule en temps reel depuis la derniere cloture (les 13 sections de `RapportComptableService`).

**Architecture:** Nouvelle `@action` GET `rapport_temps_reel` sur `CaisseViewSet` (`laboutik/views.py`). Reutilise `_calculer_datetime_ouverture_service()` et `RapportComptableService.generer_rapport_complet()`. Template standalone HTML (pas un partial HTMX). Bouton injecte dans la changelist admin via `changelist_view()` de `ClotureCaisseAdmin`.

**Tech Stack:** Django, DRF ViewSet `@action`, template Django avec styles inline (conventions Unfold), filtre `|euros` existant.

---

### Task 1 : Action `rapport_temps_reel` dans CaisseViewSet

**Files:**
- Modify: `laboutik/views.py` (ajouter l'action apres `recap_en_cours` ~ligne 2580)

- [ ] **Step 1: Ajouter l'action `rapport_temps_reel` dans `CaisseViewSet`**

Inserer cette action apres la methode `recap_en_cours` (ligne ~2580) dans `CaisseViewSet` :

```python
    @action(
        detail=False,
        methods=["get"],
        url_path="rapport-temps-reel",
        url_name="rapport_temps_reel",
    )
    def rapport_temps_reel(self, request):
        """
        GET /laboutik/caisse/rapport-temps-reel/
        Rapport comptable complet du service en cours (lecture seule).
        Calcule en temps reel depuis la derniere cloture journaliere.
        Pas de creation de ClotureCaisse. Page standalone (nouvel onglet).
        / Full accounting report of the current shift (read-only).
        Computed in real time since the last daily closure.
        No ClotureCaisse created. Standalone page (new tab).

        LOCALISATION : laboutik/views.py

        FLUX :
        1. Calcule datetime_ouverture via _calculer_datetime_ouverture_service()
        2. Instancie RapportComptableService(pv=None, debut, fin=now())
        3. Appelle generer_rapport_complet() (13 sections)
        4. Rend rapport_temps_reel.html (page complete, pas un partial)
        """
        datetime_ouverture = _calculer_datetime_ouverture_service()

        # Si aucune vente depuis la derniere cloture, afficher un message
        # / If no sales since last closure, show a message
        if datetime_ouverture is None:
            return render(
                request,
                "admin/cloture/rapport_temps_reel.html",
                {"aucune_vente": True},
            )

        datetime_fin = dj_timezone.now()
        service = RapportComptableService(None, datetime_ouverture, datetime_fin)
        rapport = service.generer_rapport_complet()
        nombre_de_transactions = service.lignes.count()

        context = {
            "aucune_vente": False,
            "rapport": rapport,
            "datetime_ouverture": datetime_ouverture,
            "datetime_fin": datetime_fin,
            "nb_transactions": nombre_de_transactions,
        }
        return render(
            request,
            "admin/cloture/rapport_temps_reel.html",
            context,
        )
```

- [ ] **Step 2: Verifier que le serveur demarre sans erreur**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: `System check identified no issues.`

---

### Task 2 : Template `rapport_temps_reel.html`

**Files:**
- Create: `Administration/templates/admin/cloture/rapport_temps_reel.html`

- [ ] **Step 1: Creer le template standalone**

Ce template est une page HTML complete (pas un partial Unfold).
Il reprend les 13 sections de `rapport_before.html` mais avec un header adapte
(pas de cloture_obj, pas de numero sequentiel, pas de boutons d'export).

```html
{% load i18n laboutik_filters %}
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% translate "Real-time report — Current shift" %}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #fff;
            color: #333;
        }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 6px 8px; border: 1px solid #ddd; }
        th { text-align: left; }
        thead tr { background: #f0f0f0; }
        .total-row { background: #e8f5e9; font-weight: bold; }
        .section { margin-bottom: 20px; }
        .section h3 { border-bottom: 2px solid #333; padding-bottom: 4px; }
        .text-right { text-align: right; }
        .indent { padding-left: 24px; color: #666; font-style: italic; }
        .label-bold { font-weight: bold; }
        .banner {
            margin-bottom: 24px;
            padding: 16px;
            background: #fff3cd;
            border: 2px solid #ffc107;
            border-radius: 8px;
        }
        .header {
            margin-bottom: 24px;
            padding: 16px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        .empty-msg {
            text-align: center;
            padding: 60px 20px;
            color: #666;
            font-size: 1.2em;
        }
        @media print {
            body { padding: 0; }
            .banner { border-color: #333; background: #f9f9f9; }
        }
    </style>
</head>
<body>

{% if aucune_vente %}
    {# Aucune vente depuis la derniere cloture / No sales since last closure #}
    <div class="empty-msg" data-testid="rapport-aucune-vente">
        <p>{% translate "No sales since the last closure." %}</p>
        <p style="font-size: 0.9em; color: #999;">{% translate "The real-time report will appear once a sale is recorded." %}</p>
    </div>
{% else %}

    {# Bandeau d'avertissement — ce n'est pas un document comptable #}
    {# / Warning banner — this is not an accounting document #}
    <div class="banner" data-testid="rapport-banner-avertissement">
        <strong>&#9888; {% translate "Temporary report" %}</strong> —
        {% translate "This report is computed in real time. It does not correspond to a closure and has no legal value." %}
    </div>

    {# En-tete du rapport / Report header #}
    <div class="header" data-testid="rapport-header">
        <h2 style="margin: 0 0 12px;">{% translate "Real-time report — Current shift" %}</h2>
        <p style="margin: 4px 0; color: #666;">
            <strong>{% translate "Period" %}:</strong>
            {{ datetime_ouverture }} &rarr; {{ datetime_fin }}
        </p>
        <p style="margin: 4px 0; color: #666;">
            <strong>{% translate "Transactions" %}:</strong> {{ nb_transactions }}
        </p>
    </div>

    {# ── Section 1 : Totaux par moyen de paiement / Totals by payment method ── #}
    {% with section=rapport.totaux_par_moyen %}
    {% if section %}
    <div class="section" data-testid="section-totaux-par-moyen">
        <h3>{% translate "Totals by payment method" %}</h3>
        <table>
            <thead>
                <tr>
                    <th>{% translate "Payment method" %}</th>
                    <th class="text-right">{% translate "Amount" %}</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>{% translate "Cash" %}</td>
                    <td class="text-right">{{ section.especes|euros }}</td>
                </tr>
                <tr>
                    <td>{% translate "Credit card" %}</td>
                    <td class="text-right">{{ section.carte_bancaire|euros }}</td>
                </tr>
                <tr>
                    <td>{% translate "Cashless" %}</td>
                    <td class="text-right">{{ section.cashless|euros }}</td>
                </tr>
                {% if section.cashless_detail %}
                {% for asset in section.cashless_detail %}
                <tr>
                    <td class="indent">&hookrightarrow; {{ asset.nom }} ({{ asset.code }})</td>
                    <td class="text-right" style="color: #666;">{{ asset.montant|euros }}</td>
                </tr>
                {% endfor %}
                {% endif %}
                <tr>
                    <td>{% translate "Check" %}</td>
                    <td class="text-right">{{ section.cheque|euros }}</td>
                </tr>
                <tr class="total-row">
                    <td>{% translate "Total" %}</td>
                    <td class="text-right">{{ section.total|euros }}</td>
                </tr>
            </tbody>
        </table>
    </div>
    {% endif %}
    {% endwith %}

    {# ── Section 2 : Detail des ventes par categorie / Sales detail by category ── #}
    {% with section=rapport.detail_ventes %}
    {% if section %}
    <div class="section" data-testid="section-detail-ventes">
        <h3>{% translate "Sales detail" %}</h3>
        {% for categorie_nom, categorie_data in section.items %}
        <h4 style="margin: 12px 0 4px; color: #555;">{{ categorie_nom }}</h4>
        <table style="margin-bottom: 8px;">
            <thead>
                <tr>
                    <th>{% translate "Product" %}</th>
                    <th class="text-right">{% translate "Sold" %}</th>
                    <th class="text-right">{% translate "Free" %}</th>
                    <th class="text-right">{% translate "Total qty" %}</th>
                    <th class="text-right">{% translate "HT" %}</th>
                    <th class="text-right">{% translate "VAT" %}</th>
                    <th class="text-right">{% translate "TTC" %}</th>
                    <th class="text-right">{% translate "Cost" %}</th>
                    <th class="text-right">{% translate "Profit" %}</th>
                </tr>
            </thead>
            <tbody>
                {% for article in categorie_data.articles %}
                <tr>
                    <td>{{ article.nom|default:"—" }}</td>
                    <td class="text-right">{{ article.qty_vendus|default:0 }}</td>
                    <td class="text-right">{{ article.qty_offerts|default:0 }}</td>
                    <td class="text-right">{{ article.qty_total|default:0 }}</td>
                    <td class="text-right">{{ article.total_ht|euros }}</td>
                    <td class="text-right">{{ article.total_tva|euros }}</td>
                    <td class="text-right">{{ article.total_ttc|euros }}</td>
                    <td class="text-right">{{ article.cout_total|euros }}</td>
                    <td class="text-right">{{ article.benefice|euros }}</td>
                </tr>
                {% endfor %}
                <tr class="total-row">
                    <td colspan="6">{% translate "Total" %} {{ categorie_nom }}</td>
                    <td class="text-right">{{ categorie_data.total_ttc|euros }}</td>
                    <td colspan="2"></td>
                </tr>
            </tbody>
        </table>
        {% endfor %}
    </div>
    {% endif %}
    {% endwith %}

    {# ── Section 3 : TVA / VAT breakdown ── #}
    {% with section=rapport.tva %}
    {% if section %}
    <div class="section" data-testid="section-tva">
        <h3>{% translate "VAT breakdown" %}</h3>
        <table>
            <thead>
                <tr>
                    <th>{% translate "Rate" %}</th>
                    <th class="text-right">{% translate "HT" %}</th>
                    <th class="text-right">{% translate "VAT" %}</th>
                    <th class="text-right">{% translate "TTC" %}</th>
                </tr>
            </thead>
            <tbody>
                {% for taux_label, tva_data in section.items %}
                <tr>
                    <td>{{ taux_label }}</td>
                    <td class="text-right">{{ tva_data.total_ht|euros }}</td>
                    <td class="text-right">{{ tva_data.total_tva|euros }}</td>
                    <td class="text-right">{{ tva_data.total_ttc|euros }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}
    {% endwith %}

    {# ── Section 4 : Solde caisse / Cash register balance ── #}
    {% with section=rapport.solde_caisse %}
    {% if section %}
    <div class="section" data-testid="section-solde-caisse">
        <h3>{% translate "Cash register balance" %}</h3>
        <table>
            <tbody>
                <tr>
                    <td class="label-bold">{% translate "Opening float" %}</td>
                    <td class="text-right">{{ section.fond_de_caisse|euros }}</td>
                </tr>
                <tr>
                    <td class="label-bold">{% translate "Cash income" %}</td>
                    <td class="text-right">{{ section.entrees_especes|euros }}</td>
                </tr>
                {% if section.sorties_especes %}
                <tr>
                    <td class="label-bold">{% translate "Cash withdrawals" %}</td>
                    <td class="text-right" style="color: #c62828;">&minus; {{ section.sorties_especes|euros }}</td>
                </tr>
                {% endif %}
                <tr class="total-row">
                    <td>{% translate "Balance" %}</td>
                    <td class="text-right">{{ section.solde|euros }}</td>
                </tr>
            </tbody>
        </table>
    </div>
    {% endif %}
    {% endwith %}

    {# ── Section 5 : Recharges cashless / Cashless top-ups ── #}
    {% with section=rapport.recharges %}
    {% if section %}
    <div class="section" data-testid="section-recharges">
        <h3>{% translate "Cashless top-ups" %}</h3>
        <table>
            <thead>
                <tr>
                    <th>{% translate "Product" %}</th>
                    <th>{% translate "Currency" %}</th>
                    <th>{% translate "Payment method" %}</th>
                    <th class="text-right">{% translate "Amount" %}</th>
                    <th class="text-right">{% translate "Count" %}</th>
                </tr>
            </thead>
            <tbody>
                {% for code, rec in section.detail.items %}
                <tr>
                    <td>{{ rec.nom_produit|default:code }}</td>
                    <td>{{ rec.nom_monnaie|default:"—" }}</td>
                    <td>{{ rec.moyen_paiement|default:"—" }}</td>
                    <td class="text-right">{{ rec.total|euros }}</td>
                    <td class="text-right">{{ rec.nb }}</td>
                </tr>
                {% endfor %}
                <tr class="total-row">
                    <td colspan="3">{% translate "Total" %}</td>
                    <td class="text-right">{{ section.total|euros }}</td>
                    <td></td>
                </tr>
            </tbody>
        </table>
    </div>
    {% endif %}
    {% endwith %}

    {# ── Section 6 : Adhesions / Memberships ── #}
    {% with section=rapport.adhesions %}
    {% if section %}
    <div class="section" data-testid="section-adhesions">
        <h3>{% translate "Memberships" %}</h3>
        <table>
            <thead>
                <tr>
                    <th>{% translate "Product" %}</th>
                    <th>{% translate "Price tier" %}</th>
                    <th>{% translate "Payment method" %}</th>
                    <th class="text-right">{% translate "Count" %}</th>
                    <th class="text-right">{% translate "Amount" %}</th>
                </tr>
            </thead>
            <tbody>
                {% for code, adh in section.detail.items %}
                <tr>
                    <td>{{ adh.nom_produit }}</td>
                    <td>{{ adh.nom_tarif|default:"—" }}</td>
                    <td>{{ adh.moyen_paiement }}</td>
                    <td class="text-right">{{ adh.nb }}</td>
                    <td class="text-right">{{ adh.total|euros }}</td>
                </tr>
                {% endfor %}
                <tr class="total-row">
                    <td colspan="3">{% translate "Total" %}</td>
                    <td class="text-right">{{ section.nb }}</td>
                    <td class="text-right">{{ section.total|euros }}</td>
                </tr>
            </tbody>
        </table>
    </div>
    {% endif %}
    {% endwith %}

    {# ── Section 7 : Remboursements / Refunds ── #}
    {% with section=rapport.remboursements %}
    {% if section %}
    <div class="section" data-testid="section-remboursements">
        <h3>{% translate "Refunds" %}</h3>
        <table>
            <tbody>
                <tr>
                    <td class="label-bold">{% translate "Count" %}</td>
                    <td class="text-right">{{ section.nb }}</td>
                </tr>
                <tr>
                    <td class="label-bold">{% translate "Total" %}</td>
                    <td class="text-right">{{ section.total|euros }}</td>
                </tr>
            </tbody>
        </table>
    </div>
    {% endif %}
    {% endwith %}

    {# ── Section 8 : Habitus (statistiques clientele) / Customer statistics ── #}
    {% with section=rapport.habitus %}
    {% if section %}
    <div class="section" data-testid="section-habitus">
        <h3>{% translate "Customer statistics" %}</h3>
        <table>
            <thead>
                <tr>
                    <th>{% translate "Statistic" %}</th>
                    <th class="text-right">{% translate "Value" %}</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>{% translate "Cards used" %}</td>
                    <td class="text-right">{{ section.nb_cartes }}</td>
                </tr>
                <tr>
                    <td>{% translate "Total spent" %}</td>
                    <td class="text-right">{{ section.total|euros }}</td>
                </tr>
                <tr>
                    <td>{% translate "Average basket" %}</td>
                    <td class="text-right">{{ section.panier_moyen|euros }}</td>
                </tr>
                <tr>
                    <td>{% translate "Median spend" %}</td>
                    <td class="text-right">{{ section.depense_mediane|euros }}</td>
                </tr>
                <tr>
                    <td>{% translate "Median top-up" %}</td>
                    <td class="text-right">{{ section.recharge_mediane|euros }}</td>
                </tr>
                <tr>
                    <td>{% translate "Average remaining on card" %}</td>
                    <td class="text-right">{{ section.reste_moyenne|euros }}</td>
                </tr>
                <tr>
                    <td>{% translate "Median remaining on card" %}</td>
                    <td class="text-right">{{ section.med_on_card|euros }}</td>
                </tr>
                <tr>
                    <td>{% translate "New members" %}</td>
                    <td class="text-right">{{ section.nouveaux_membres }}</td>
                </tr>
            </tbody>
        </table>
    </div>
    {% endif %}
    {% endwith %}

    {# ── Section 9 : Billets / Tickets ── #}
    {% with section=rapport.billets %}
    {% if section %}
    <div class="section" data-testid="section-billets">
        <h3>{% translate "Tickets" %}</h3>
        <table>
            <thead>
                <tr>
                    <th>{% translate "Event" %}</th>
                    <th>{% translate "Date" %}</th>
                    <th>{% translate "Product / Price tier" %}</th>
                    <th class="text-right">{% translate "Count" %}</th>
                    <th class="text-right">{% translate "Amount" %}</th>
                </tr>
            </thead>
            <tbody>
                {% for cle, billet_data in section.detail.items %}
                <tr>
                    <td>{{ billet_data.nom_event }}</td>
                    <td>{{ billet_data.date_event|default:"—" }}</td>
                    <td>{{ billet_data.nom_produit }}{% if billet_data.nom_tarif %} / {{ billet_data.nom_tarif }}{% endif %}</td>
                    <td class="text-right">{{ billet_data.nb }}</td>
                    <td class="text-right">{{ billet_data.total|euros }}</td>
                </tr>
                {% endfor %}
                <tr class="total-row">
                    <td colspan="3">{% translate "Total" %}</td>
                    <td class="text-right">{{ section.nb }}</td>
                    <td class="text-right">{{ section.total|euros }}</td>
                </tr>
            </tbody>
        </table>
    </div>
    {% endif %}
    {% endwith %}

    {# ── Section 10 : Synthese des operations / Operations summary ── #}
    {% with section=rapport.synthese_operations %}
    {% if section %}
    <div class="section" data-testid="section-synthese-operations">
        <h3>{% translate "Operations summary" %}</h3>
        <table>
            <thead>
                <tr>
                    <th>{% translate "Operation" %}</th>
                    <th class="text-right">{% translate "Cash" %}</th>
                    <th class="text-right">{% translate "Credit card" %}</th>
                    <th class="text-right">{% translate "Cashless" %}</th>
                    <th class="text-right">{% translate "Total" %}</th>
                </tr>
            </thead>
            <tbody>
                {% for op_nom, op_data in section.items %}
                <tr>
                    <td class="label-bold">{{ op_nom|title }}</td>
                    <td class="text-right">{{ op_data.especes|euros }}</td>
                    <td class="text-right">{{ op_data.carte_bancaire|euros }}</td>
                    <td class="text-right">{{ op_data.cashless|euros }}</td>
                    <td class="text-right label-bold">{{ op_data.total|euros }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}
    {% endwith %}

    {# ── Section 11 : Operateurs / Operators ── #}
    {% with section=rapport.operateurs %}
    <div class="section" data-testid="section-operateurs">
        <h3>{% translate "Operators" %}</h3>
        {% if section %}
        <table>
            <thead>
                <tr>
                    <th>{% translate "Operator" %}</th>
                    <th class="text-right">{% translate "Amount" %}</th>
                </tr>
            </thead>
            <tbody>
                {% for op_nom, op_montant in section.items %}
                <tr>
                    <td>{{ op_nom }}</td>
                    <td class="text-right">{{ op_montant|euros }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p style="color: #999; font-style: italic;">{% translate "Not yet available" %}</p>
        {% endif %}
    </div>
    {% endwith %}

    {# ── Section 12 : Ventilation par point de vente / Breakdown by point of sale ── #}
    {% with section=rapport.ventilation_par_pv %}
    {% if section %}
    <div class="section" data-testid="section-ventilation-par-pv">
        <h3>{% translate "Breakdown by point of sale" %}</h3>
        <table>
            <thead>
                <tr>
                    <th>{% translate "Point of sale" %}</th>
                    <th class="text-right">{% translate "Revenue incl. tax" %}</th>
                </tr>
            </thead>
            <tbody>
                {% for pv in section %}
                <tr>
                    <td>{{ pv.nom }}</td>
                    <td class="text-right">{{ pv.total_ttc|euros }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}
    {% endwith %}

    {# ── Section 13 : Informations legales / Legal information ── #}
    {% with section=rapport.infos_legales %}
    {% if section %}
    <div class="section" data-testid="section-infos-legales">
        <h3>{% translate "Legal information" %}</h3>
        <table>
            <tbody>
                <tr>
                    <td class="label-bold">{% translate "Organisation" %}</td>
                    <td>{{ section.organisation|default:"—" }}</td>
                </tr>
                <tr>
                    <td class="label-bold">{% translate "Address" %}</td>
                    <td>{{ section.adresse|default:"—" }}</td>
                </tr>
                <tr>
                    <td class="label-bold">{% translate "Postal code" %}</td>
                    <td>{{ section.code_postal|default:"—" }}</td>
                </tr>
                <tr>
                    <td class="label-bold">{% translate "City" %}</td>
                    <td>{{ section.ville|default:"—" }}</td>
                </tr>
                <tr>
                    <td class="label-bold">{% translate "SIREN" %}</td>
                    <td>{{ section.siren|default:"—" }}</td>
                </tr>
                <tr>
                    <td class="label-bold">{% translate "VAT number" %}</td>
                    <td>{{ section.tva_number|default:"—" }}</td>
                </tr>
                <tr>
                    <td class="label-bold">{% translate "Email" %}</td>
                    <td>{{ section.email|default:"—" }}</td>
                </tr>
                <tr>
                    <td class="label-bold">{% translate "Phone" %}</td>
                    <td>{{ section.phone|default:"—" }}</td>
                </tr>
            </tbody>
        </table>
    </div>
    {% endif %}
    {% endwith %}

{% endif %}

</body>
</html>
```

- [ ] **Step 2: Verifier que le template est trouve par Django**

```bash
docker exec lespass_django poetry run python -c "
from django.template.loader import get_template
t = get_template('admin/cloture/rapport_temps_reel.html')
print('Template found:', t.origin)
"
```

Expected: path vers le fichier cree.

---

### Task 3 : Bouton sur la changelist admin

**Files:**
- Modify: `Administration/admin/laboutik.py` (~ligne 563, dans `changelist_view`)
- Modify: `Administration/templates/admin/cloture/changelist_before.html`

- [ ] **Step 1: Injecter l'URL du rapport temps reel dans le contexte de `changelist_view`**

Dans `Administration/admin/laboutik.py`, methode `changelist_view` de `ClotureCaisseAdmin` (ligne ~555), ajouter une ligne apres les URLs existantes :

```python
    def changelist_view(self, request, extra_context=None):
        """
        Injecte l'URL de l'export fiscal dans le contexte du changelist.
        Affiche un bandeau avec le bouton "Export fiscal" en haut de la liste.
        / Injects the fiscal export URL into the changelist context.
        Displays a banner with the "Export fiscal" button at the top of the list.
        LOCALISATION : Administration/admin/laboutik.py
        """
        extra_context = extra_context or {}
        extra_context['export_fiscal_url'] = '/laboutik/caisse/export-fiscal/'
        extra_context['export_fec_url'] = '/laboutik/caisse/export-fec/'
        extra_context['export_csv_comptable_url'] = '/laboutik/caisse/export-csv-comptable/'
        extra_context['rapport_temps_reel_url'] = '/laboutik/caisse/rapport-temps-reel/'
        return super().changelist_view(request, extra_context)
```

La seule ligne ajoutee est :
```python
        extra_context['rapport_temps_reel_url'] = '/laboutik/caisse/rapport-temps-reel/'
```

- [ ] **Step 2: Ajouter le bouton dans `changelist_before.html`**

Dans `Administration/templates/admin/cloture/changelist_before.html`, ajouter un bouton **apres** la div `flex-shrink-0` des boutons d'export (apres la ligne `</div>` qui ferme le groupe de boutons, avant la fermeture de `flex-col sm:flex-row`) :

Ajouter ce bloc juste apres le `</div>` qui ferme le groupe `flex items-center gap-3 flex-shrink-0` (ligne ~62) et avant la fermeture de la div `flex flex-col sm:flex-row` :

Remplacer le bloc complet `<div class="flex flex-col sm:flex-row ...">` (lignes 16-63) par :

```html
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 py-2">

                <div class="flex flex-col gap-1 min-w-0">
                    <span class="text-sm text-font-subtle-light dark:text-font-subtle-dark">
                        {% translate "Generate a signed archive (ZIP) of all POS data for the tax administration." %}
                    </span>
                    <span class="text-xs text-base-400 dark:text-base-500 flex items-center gap-1 mt-1">
                        <span class="material-symbols-outlined" style="font-size: 14px;" aria-hidden="true">lock</span>
                        {% translate "HMAC-SHA256 integrity — independently verifiable" %}
                    </span>
                </div>

                <div class="flex items-center gap-3 flex-shrink-0">
                    {% if rapport_temps_reel_url %}
                    <a href="{{ rapport_temps_reel_url }}"
                       target="_blank"
                       rel="noopener"
                       class="font-medium flex items-center gap-2 px-5 py-2.5 rounded-default justify-center whitespace-nowrap cursor-pointer transition-colors"
                       style="background-color: #16a34a; color: white;"
                       data-testid="btn-rapport-temps-reel">
                        <span class="material-symbols-outlined" style="font-size: 18px;" aria-hidden="true">monitoring</span>
                        {% translate "Current shift report" %}
                    </a>
                    {% endif %}

                    <button type="button"
                            hx-get="{{ export_fiscal_url }}"
                            hx-target="#export-fiscal-zone"
                            hx-swap="innerHTML"
                            class="font-medium flex items-center gap-2 px-5 py-2.5 rounded-default justify-center whitespace-nowrap cursor-pointer bg-primary-600 text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:focus:ring-offset-base-900 transition-colors"
                            data-testid="btn-export-fiscal">
                        <span class="material-symbols-outlined" style="font-size: 18px;" aria-hidden="true">download</span>
                        {% translate "Export fiscal" %}
                    </button>

                    {% if export_fec_url %}
                    <button type="button"
                            hx-get="{{ export_fec_url }}"
                            hx-target="#export-fiscal-zone"
                            hx-swap="innerHTML"
                            class="font-medium flex items-center gap-2 px-5 py-2.5 rounded-default justify-center whitespace-nowrap cursor-pointer bg-primary-600 text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:focus:ring-offset-base-900 transition-colors"
                            data-testid="btn-export-fec">
                        <span class="material-symbols-outlined" style="font-size: 18px;" aria-hidden="true">download</span>
                        {% translate "Export FEC" %}
                    </button>
                    {% endif %}

                    {% if export_csv_comptable_url %}
                    <button type="button"
                            hx-get="{{ export_csv_comptable_url }}"
                            hx-target="#export-fiscal-zone"
                            hx-swap="innerHTML"
                            class="font-medium flex items-center gap-2 px-5 py-2.5 rounded-default justify-center whitespace-nowrap cursor-pointer bg-primary-600 text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:focus:ring-offset-base-900 transition-colors"
                            data-testid="btn-export-csv-comptable">
                        <span class="material-symbols-outlined" style="font-size: 18px;" aria-hidden="true">download</span>
                        {% translate "Export CSV comptable" %}
                    </button>
                    {% endif %}
                </div>
            </div>
```

- [ ] **Step 3: Verifier visuellement dans le navigateur**

Ouvrir https://lespass.devtib.fr/admin/laboutik/cloturecaisse/ et verifier :
1. Le bouton vert "Rapport en cours" apparait a cote des boutons d'export
2. Cliquer ouvre un nouvel onglet avec le rapport complet
3. Si aucune vente, le message "Aucune vente depuis la derniere cloture" s'affiche

---

### Task 4 : Traductions

**Files:**
- Modify: `locale/fr/LC_MESSAGES/django.po`
- Modify: `locale/en/LC_MESSAGES/django.po`

- [ ] **Step 1: Extraire les nouvelles chaines**

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
```

- [ ] **Step 2: Editer les fichiers .po**

Chercher les nouvelles chaines et remplir les `msgstr` :

| msgid (EN) | msgstr FR |
|---|---|
| `"Real-time report — Current shift"` | `"Rapport temps réel — Session en cours"` |
| `"Temporary report"` | `"Rapport temporaire"` |
| `"This report is computed in real time. It does not correspond to a closure and has no legal value."` | `"Ce rapport est calculé en temps réel. Il ne correspond pas à une clôture et n'a pas de valeur légale."` |
| `"No sales since the last closure."` | `"Aucune vente depuis la dernière clôture."` |
| `"The real-time report will appear once a sale is recorded."` | `"Le rapport temps réel apparaîtra dès qu'une vente sera enregistrée."` |
| `"Current shift report"` | `"Rapport en cours"` |

Les autres chaines (Payment method, Cash, Total, etc.) existent deja.

- [ ] **Step 3: Compiler les traductions**

```bash
docker exec lespass_django poetry run django-admin compilemessages
```

---

### Task 5 : Tests

**Files:**
- Modify: `tests/pytest/test_cloture_caisse.py` (ou creer si inexistant)

- [ ] **Step 1: Identifier le fichier de test existant**

```bash
ls tests/pytest/test_cloture*.py tests/pytest/test_pos*.py tests/pytest/test_caisse*.py 2>/dev/null
```

- [ ] **Step 2: Ajouter un test pour l'action `rapport_temps_reel`**

```python
def test_rapport_temps_reel_renvoie_page_html(client_api_laboutik):
    """
    GET /laboutik/caisse/rapport-temps-reel/ renvoie une page HTML complete.
    Soit avec le rapport (si des ventes existent), soit avec le message "aucune vente".
    / GET rapport-temps-reel returns a full HTML page.
    Either with the report (if sales exist) or the "no sales" message.
    """
    response = client_api_laboutik.get("/laboutik/caisse/rapport-temps-reel/")

    assert response.status_code == 200
    contenu = response.content.decode("utf-8")

    # La page est une page HTML complete (pas un partial)
    # / The page is a full HTML page (not a partial)
    assert "<!DOCTYPE html>" in contenu

    # Soit le rapport est present, soit le message "aucune vente"
    # / Either the report is present, or the "no sales" message
    rapport_present = "section-totaux-par-moyen" in contenu
    aucune_vente = "rapport-aucune-vente" in contenu
    assert rapport_present or aucune_vente
```

- [ ] **Step 3: Lancer le test**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_cloture_caisse.py::test_rapport_temps_reel_renvoie_page_html -v
```

Expected: PASS

---

### Task 6 : CHANGELOG + Documentation

**Files:**
- Modify: `CHANGELOG.md`
- Create: `A TESTER et DOCUMENTER/rapport-temps-reel.md`

- [ ] **Step 1: Ajouter l'entree CHANGELOG**

Ajouter en tete de `CHANGELOG.md` :

```markdown
## N. Rapport temps reel — Session en cours / Real-time report — Current shift

**Quoi / What:** Bouton "Rapport en cours" sur la liste des clotures de caisse (`/admin/laboutik/cloturecaisse/`). Ouvre dans un nouvel onglet un rapport comptable complet calcule en temps reel depuis la derniere cloture.
**Pourquoi / Why:** Permettre aux operateurs de consulter l'etat comptable du service en cours sans creer de cloture.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | Nouvelle action `rapport_temps_reel` sur CaisseViewSet |
| `Administration/templates/admin/cloture/rapport_temps_reel.html` | Template standalone du rapport temps reel |
| `Administration/templates/admin/cloture/changelist_before.html` | Bouton "Rapport en cours" avec target="_blank" |
| `Administration/admin/laboutik.py` | URL du rapport injectee dans changelist_view |

### Migration
- **Migration necessaire / Migration required:** Non
```

- [ ] **Step 2: Creer le fichier de test manuel**

Creer `A TESTER et DOCUMENTER/rapport-temps-reel.md` :

```markdown
# Rapport temps reel — Session en cours

## Ce qui a ete fait
Ajout d'un bouton "Rapport en cours" sur la page admin des clotures de caisse.
Le bouton ouvre un nouvel onglet avec un rapport comptable complet calcule
en temps reel depuis la derniere cloture, via RapportComptableService.

### Modifications
| Fichier | Changement |
|---|---|
| `laboutik/views.py` | Action `rapport_temps_reel` dans CaisseViewSet |
| `Administration/templates/admin/cloture/rapport_temps_reel.html` | Page HTML standalone |
| `Administration/templates/admin/cloture/changelist_before.html` | Bouton vert "Rapport en cours" |
| `Administration/admin/laboutik.py` | URL injectee dans contexte changelist |

## Tests a realiser

### Test 1 : Bouton visible sur la changelist
1. Aller sur /admin/laboutik/cloturecaisse/
2. Verifier qu'un bouton vert "Rapport en cours" apparait a cote des boutons d'export
3. Le bouton doit avoir une icone "monitoring"

### Test 2 : Rapport avec ventes en cours
1. S'assurer qu'il y a des ventes depuis la derniere cloture
2. Cliquer sur "Rapport en cours" (ouvre un nouvel onglet)
3. Verifier : bandeau jaune "Rapport temporaire" en haut
4. Verifier : les 13 sections sont presentes (totaux, detail ventes, TVA, solde caisse, recharges, adhesions, remboursements, habitus, billets, synthese, operateurs, ventilation par PV, infos legales)
5. Verifier : le header affiche la periode (debut session → maintenant)

### Test 3 : Rapport sans ventes
1. Cloturer la caisse pour que toutes les ventes soient couvertes
2. Cliquer sur "Rapport en cours"
3. Verifier : message "Aucune vente depuis la derniere cloture"

### Test 4 : Impression
1. Ouvrir le rapport en cours
2. Ctrl+P pour imprimer
3. Verifier que le rendu est lisible (pas de coupure de tableau)

## Compatibilite
- Pas de migration necessaire
- Pas d'impact sur les clotures existantes (lecture seule)
- Le rapport n'est pas persiste en base — c'est temporaire
```
