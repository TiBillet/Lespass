# Session 02 — Admin Unfold : page bilan

> **Chantier :** Bilan billetterie interne (sous-projet 1/3)
> **Spec :** `../specs/2026-04-03-bilan-billetterie-design.md`
> **Plan global :** `../plans/2026-04-03-bilan-billetterie-plan.md`
> **Dépend de :** Session 01 (`BaseBillet/reports.py` doit exister et être testé)
> **Produit :** Page bilan dans l'admin Unfold + composants charts + liens dans la changelist et le changeform

---

## Objectif

Rendre le bilan visible dans l'admin. L'organisateur clique sur un lien depuis la liste des events (ou depuis la fiche d'un event) et arrive sur une page complète avec 6 sections : synthèse, ventes par tarif, moyens de paiement, canaux de vente, scans, codes promo.

---

## Contexte technique

### EventAdmin existant

Fichier : `Administration/admin/events.py`
- Ligne 238 : `class EventAdmin(ModelAdmin, ImportExportModelAdmin)`
- `list_display` : `['name', 'display_valid_tickets_count', 'datetime', 'show_time', 'published']`
- Pas de `get_urls()` existant
- Pas de `change_form_before_template` existant
- Le site admin est `staff_admin_site` (nom `staff_admin`), URL préfixe `/admin/`

### Pattern Unfold pour les pages custom

Le pattern recommandé (cf. skill unfold, sections 13 et 23) :

```python
# URLs custom via get_urls()
def get_urls(self):
    urls = super().get_urls()
    custom_urls = [
        re_path(
            r'^(?P<object_id>[^/]+)/bilan/$',
            self.admin_site.admin_view(self.vue_bilan),
            name='basebillet_event_bilan',
        ),
    ]
    return custom_urls + urls
```

**Pièges critiques :**
- Les helpers (fonctions utilitaires) doivent être **hors de la classe** ModelAdmin (Unfold wrappe toutes les méthodes)
- Pas de Tailwind custom — inline styles uniquement
- Variables CSS Unfold : `var(--color-primary-600)`, `var(--color-base-0)`, etc.

### Composants Unfold natifs

Chart.js est inclus nativement dans Unfold. Les composants :
- `unfold/components/card.html` — conteneur de section
- `unfold/components/chart/line.html` — courbe (pour les ventes cumulées)
- `unfold/components/chart/bar.html` — barres (pour l'affluence)
- `unfold/components/progress.html` — jauge (pour le taux de remplissage)

Usage des charts : via `@register_component` + `BaseComponent` qui passe les données en JSON au template. Ou directement dans le template avec un `<canvas>` et `data-value="{{ data_json }}"`.

### Service disponible (Session 01)

```python
from BaseBillet.reports import RapportBilletterieService

service = RapportBilletterieService(event)
synthese = service.calculer_synthese()           # dict
courbe = service.calculer_courbe_ventes()        # dict Chart.js ready
tarifs = service.calculer_ventes_par_tarif()     # list[dict]
moyens = service.calculer_par_moyen_paiement()   # list[dict]
canaux = service.calculer_par_canal()            # list[dict] | None
scans = service.calculer_scans()                 # dict
promos = service.calculer_codes_promo()          # list[dict] | None
remb = service.calculer_remboursements()         # dict
```

---

## Tâches

### 2.1 — URLs custom et vue bilan

**Fichiers :**
- Modifier : `Administration/admin/events.py`

Ajouter `get_urls()` avec 3 routes :
```
/admin/basebillet/event/{uuid}/bilan/        → vue_bilan (page HTML)
/admin/basebillet/event/{uuid}/bilan/pdf/    → vue_bilan_pdf (Session 03)
/admin/basebillet/event/{uuid}/bilan/csv/    → vue_bilan_csv (Session 03)
```

Pour cette session, seule la route `/bilan/` est implémentée. Les routes PDF/CSV sont ajoutées en Session 03.

**La vue `vue_bilan()` :**
- `get_object_or_404(Event, pk=object_id)`
- Instancie `RapportBilletterieService(event)`
- Appelle les 8 méthodes
- Passe tout dans le contexte + `self.admin_site.each_context(request)`
- Rend `admin/event/bilan.html` via `TemplateResponse`

**Imports nécessaires :**
```python
from django.urls import re_path
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from BaseBillet.reports import RapportBilletterieService
```

---

### 2.2 — Template principal `bilan.html`

**Fichier :** `Administration/templates/admin/event/bilan.html`

Ce template étend le layout Unfold. Structure :

```html
{% extends "admin/base_site.html" %}
{% load i18n unfold %}

{% block title %}{% translate "Bilan" %} — {{ event.name }}{% endblock %}

{% block content %}
    <!-- En-tête : nom event, date, lieu, boutons export -->
    <!-- Section synthèse : progress bar + chiffres + line chart -->
    <!-- Section ventes par tarif : tableau -->
    <!-- Section moyens de paiement : tableau -->
    <!-- Section canaux de vente : tableau (conditionnel) -->
    <!-- Section scans : chiffres + bar chart (conditionnel) -->
    <!-- Section codes promo : tableau (conditionnel) -->
    <!-- Section remboursements : chiffres -->
{% endblock %}
```

Chaque section est wrappée dans `{% component "unfold/components/card.html" %}` avec un titre.

**Breadcrumbs :** Events → {nom event} → Bilan

---

### 2.3 — 6 templates partials

**Fichiers à créer dans `Administration/templates/admin/event/partials/` :**

#### `synthese.html`
- Progress bar Unfold pour le taux de remplissage
- 3 lignes de chiffres : vendus/scannés/no-show, CA TTC/remboursements/CA net
- Line chart Unfold pour la courbe de ventes cumulées
- Données du chart passées via `{{ courbe_ventes_json }}` (json.dumps dans la vue)
- `data-testid="bilan-synthese"`

#### `ventes_tarif.html`
- Tableau HTML inline styles : Tarif | Vendus | Offerts | CA TTC | HT | TVA | Remb.
- Ligne de total en bas
- Montants convertis de centimes vers euros avec le filtre `|euros` (ou division dans le template)
- `data-testid="bilan-ventes-tarif"`

#### `moyens_paiement.html`
- Tableau : Moyen | Montant | % | Nb billets
- `data-testid="bilan-moyens-paiement"`

#### `canaux_vente.html`
- Conditionnel : `{% if par_canal %}` (None = section masquée)
- Tableau : Canal | Nb billets | Montant
- `data-testid="bilan-canaux-vente"`

#### `scans.html`
- Chiffres : scannés, non scannés (no-show), annulés
- Bar chart Unfold pour l'affluence par tranche 30min
- Conditionnel pour le chart : `{% if scans.tranches_horaires %}`
- `data-testid="bilan-scans"`

#### `codes_promo.html`
- Conditionnel : `{% if codes_promo %}`
- Tableau : Code | Utilisations | Réduction | Manque à gagner
- `data-testid="bilan-codes-promo"`

---

### 2.4 — Colonne "Bilan" dans la changelist

**Fichier :** `Administration/admin/events.py`

Ajouter `'display_bilan_link'` dans `list_display`.

```python
@display(description=_("Report"))
def display_bilan_link(self, obj):
    from django.utils.html import format_html
    has_reservations = Reservation.objects.filter(event=obj).exists()
    if not has_reservations:
        return "—"
    url = reverse('staff_admin:basebillet_event_bilan', args=[obj.pk])
    return format_html(
        '<a href="{}" title="{}">'
        '<span class="material-symbols-outlined">assessment</span>'
        '</a>',
        url, _("Voir le bilan"),
    )
```

Note : ajouter `Reservation` dans les imports si pas déjà présent.

---

### 2.5 — Lien dans le changeform (fiche Event)

**Fichiers :**
- Modifier : `Administration/admin/events.py` — ajouter `change_form_before_template`
- Créer : `Administration/templates/admin/event/bilan_link_changeform.html`

Le template affiche une carte discrète "Voir le bilan de billetterie" avec un lien. Visible uniquement si l'event a des réservations.

```python
# Dans EventAdmin
change_form_before_template = "admin/event/bilan_link_changeform.html"
```

Le template :
```html
{% load i18n %}
{% if object_id %}
<!-- Carte lien vers le bilan, visible si l'event a des reservations -->
<!-- affiché au dessus du formulaire Event dans l'admin -->
{% endif %}
```

Le contexte `object_id` est disponible nativement dans les templates `change_form_before`.

---

## Tests

**Fichier :** `tests/pytest/test_bilan_admin_views.py`

```python
def test_page_bilan_accessible(admin_client, event_with_mixed_sales):
    url = f"/admin/basebillet/event/{event_with_mixed_sales.pk}/bilan/"
    response = admin_client.get(url)
    assert response.status_code == 200

def test_page_bilan_event_sans_ventes(admin_client, event_without_sales):
    url = f"/admin/basebillet/event/{event_without_sales.pk}/bilan/"
    response = admin_client.get(url)
    assert response.status_code == 200

def test_page_bilan_event_inexistant(admin_client):
    import uuid
    url = f"/admin/basebillet/event/{uuid.uuid4()}/bilan/"
    response = admin_client.get(url)
    assert response.status_code == 404

def test_colonne_bilan_dans_changelist(admin_client):
    response = admin_client.get("/admin/basebillet/event/")
    assert response.status_code == 200
    assert b"assessment" in response.content  # icône Material Symbols
```

---

## Vérification finale

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bilan_admin_views.py tests/pytest/test_rapport_billetterie_service.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

---

## Résultat attendu

- 3 URLs custom dans EventAdmin (`/bilan/`, `/bilan/pdf/`, `/bilan/csv/` — les 2 dernières renvoient 404 pour l'instant)
- Page bilan complète avec 6 sections (cards Unfold, charts natifs, tableaux)
- Colonne "Bilan" dans la changelist events (icône `assessment`)
- Lien "Voir le bilan" dans la fiche Event
- ~4 tests pytest admin
- 0 régression sur les tests existants
