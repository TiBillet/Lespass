# Plan d'implémentation — S3 (Chantier 01 / App `comptabilite`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.
>
> **Hub :** [`INDEX.md`](INDEX.md) — **Spec :** [`SPEC.md`](SPEC.md) §5, §8, §9
>
> **Garde-fous projet :**
> - **JAMAIS d'opération `git`**. Output suggested commit at the end.
> - **Pas de `runserver_plus`** — serveur byobu sur port 8002.
> - **Pas de `ruff format` sur fichiers existants** — uniquement sur fichiers neufs.

**Goal :** Rendre les clôtures lisibles dans l'admin avec un rapport visuel complet sur la fiche détail (`change_form_before.html`) + ajouter une page « rapport temps réel » accessible depuis la liste, qui affiche les chiffres en cours pour la période ouverte. À la fin de S3 : un trésorier ouvre une clôture dans l'admin et lit son contenu sans avoir à lire le JSON brut.

**Architecture :**
- 1 partial `_sections_rapport.html` réutilisable (8 sections + en-tête + footer)
- 1 template `change_form_before.html` qui inclut le partial pour la fiche détail
- 1 vue Python `rapport_temps_reel(request)` + URL admin custom
- 1 template page complète `rapport_temps_reel.html` (HTMX every 30s, base Unfold)
- 1 template `changelist_before.html` (bandeau avec lien vers temps réel)
- 2-3 tests pytest smoke

**Tech Stack :** Django templates (DTL), Unfold admin CSS variables, HTMX `hx-get every 30s`, `aria-live="polite"`, `data-testid`, accessibility-first.

---

## File structure produite par S3

```
comptabilite/
├── templates/
│   └── comptabilite/
│       ├── admin/
│       │   ├── _sections_rapport.html           # partial (8 sections)
│       │   ├── change_form_before.html          # fiche détail clôture
│       │   └── changelist_before.html           # bandeau liste + lien temps réel
│       └── views/
│           └── rapport_temps_reel.html          # page standalone temps réel
└── admin.py                                      # MODIFIÉ : change_form_before_template +
                                                 # changelist_before_template + 2 vues custom +
                                                 # changeform_view override pour injecter rapport

tests/pytest/
└── test_comptabilite_admin.py                   # APPEND : 3 tests smoke S3
```

Pas de modification du modèle, pas de migration, pas de modification de `services.py` ou `tasks.py`.

---

## Découpage en 2 blocs subagent

| Bloc | Tasks | Sortie |
|---|---|---|
| **B1** | Partial `_sections_rapport.html` + `change_form_before.html` + intégration dans `ClotureCaisseAdmin` (override `changeform_view`) + 1 test smoke | Fiche détail clôture affiche les 8 sections |
| **B2** | Vue `rapport_temps_reel` + URL admin + `rapport_temps_reel.html` (page standalone) + `changelist_before.html` (lien) + 2 tests smoke | Page `/admin/comptabilite/cloturecaisse/rapport-temps-reel/` accessible, refresh HTMX 30s |

---

## Bloc B1 — Partial + fiche détail clôture

### Files
- Create: `comptabilite/templates/comptabilite/admin/_sections_rapport.html` (partial)
- Create: `comptabilite/templates/comptabilite/admin/change_form_before.html`
- Modify: `comptabilite/admin.py` (ajout `change_form_before_template` + override `changeform_view`)
- Modify: `tests/pytest/test_comptabilite_admin.py` (append 1 test)

### Test à écrire (TDD)

```python
def test_admin_changeform_affiche_rapport(admin_client, tenant_lespass):
    """
    GET /admin/comptabilite/cloturecaisse/<uuid>/change/ retourne 200 et
    contient les sections du rapport (totaux par moyen, TVA, etc.).
    """
    from django_tenants.utils import tenant_context
    from comptabilite.models import ClotureCaisse
    from comptabilite.tasks import generer_cloture_pour_tenant
    from django.utils import timezone
    from datetime import timedelta

    client, _ = admin_client
    fin = timezone.now() - timedelta(days=90)
    debut = fin - timedelta(days=1)

    with tenant_context(tenant_lespass):
        # Cleanup et création contrôlée
        ClotureCaisse.objects.filter(datetime_debut=debut, datetime_fin=fin).delete()
        cloture_uuid = generer_cloture_pour_tenant(
            schema_name=tenant_lespass.schema_name,
            niveau="J",
            datetime_debut_iso=debut.isoformat(),
            datetime_fin_iso=fin.isoformat(),
        )

        url = f"/admin/comptabilite/cloturecaisse/{cloture_uuid}/change/"
        response = client.get(url)
        contenu = response.content.decode("utf-8")

        assert response.status_code == 200
        # data-testid pour repérer les sections rendues
        assert 'data-testid="comptabilite-section-totaux-par-moyen"' in contenu
        assert 'data-testid="comptabilite-section-tva"' in contenu
        assert 'data-testid="comptabilite-section-infos-legales"' in contenu

        # Cleanup
        ClotureCaisse.objects.filter(uuid=cloture_uuid).delete()
```

### Template `_sections_rapport.html` (partial)

Variables attendues dans le context :
- `rapport` (dict — résultat de `RapportComptableService.generer_rapport_complet()`)
- `cloture` (optionnel — instance ClotureCaisse pour l'en-tête)
- `datetime_debut`, `datetime_fin` (datetime) — toujours présents (fallback sur `rapport.meta`)

Le template doit afficher **8 sections** (mêmes clés que `rapport_json`), chacune dans un bloc `<section>` avec un `data-testid="comptabilite-section-<slug>"` :

```
totaux-par-moyen     → table : code, label, total, nb
tva                  → table : taux, ttc, ht, tva
detail-ventes        → groupé par catégorie, sous-table d'articles
adhesions            → table : produit, tarif, moyen, total, nb
billets              → table : event, date, produit, tarif, total, nb
remboursements       → 2 lignes : avoirs (CREDIT_NOTE) + refunds
synthese-operations  → matrice : opération × moyen
infos-legales        → paragraphe formaté
```

CSS **inline** uniquement (pas de Tailwind custom, cf. djc.md règle admin Unfold). Utiliser :
- `var(--color-base-0)` (texte clair sur fond clair / sombre sur fond sombre)
- `var(--color-base-100)` (fond muted)
- Bordures fines `border: 1px solid var(--color-base-200)`
- Pas de `display: grid` exotique — tables simples, alignement texte droite pour les montants

Tous les montants sont stockés en **centimes** dans `rapport_json` → diviser par 100 dans le template avec `{{ value|floatformat:2 }}` après filtre custom `cents_to_euros`. **OU plus simple** : faire le format en Python dans la vue avant de render.

Préférer le format Python : tu peux mapper le rapport en pré-format pour ne pas alourdir le template avec des filtres custom.

### Template `change_form_before.html`

Le template hérite implicitement du contexte Unfold (Django admin context_processors injectent `cl`, `original`, etc.). Le contexte custom est injecté par la vue (cf. plus bas).

Doit :
1. Cacher les fieldsets résiduels avec `<style>.aligned, fieldset.module, .submit-row { display: none !important; }</style>`
2. Afficher un en-tête : organisation, numéro séquentiel, niveau, période, hash (badge)
3. Include `{% include "comptabilite/admin/_sections_rapport.html" %}`
4. Aucun bouton d'action (S4 ajoutera les exports)

### Override `changeform_view` dans `ClotureCaisseAdmin`

```python
def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
    extra_context = extra_context or {}
    if object_id:
        from django.shortcuts import get_object_or_404
        from comptabilite.models import ClotureCaisse
        cloture = get_object_or_404(ClotureCaisse, pk=object_id)
        # Pre-format des montants centimes → euros formatés
        rapport_pretty = _enrichir_rapport_pour_template(cloture.rapport_json or {})
        extra_context["cloture"] = cloture
        extra_context["rapport"] = rapport_pretty
        extra_context["datetime_debut"] = cloture.datetime_debut
        extra_context["datetime_fin"] = cloture.datetime_fin
    return super().changeform_view(request, object_id, form_url, extra_context)
```

Et au niveau du module (pas méthode de classe — cf. djc.md règle Unfold) :

```python
def _enrichir_rapport_pour_template(rapport: dict) -> dict:
    """
    Ajoute des cles formatees (_euros suffixe) au rapport pour eviter
    les filtres custom dans le template. Modifie une copie, pas l'original.
    """
    import copy
    r = copy.deepcopy(rapport)
    # totaux_par_moyen : ajoute label_euros pour total
    if "totaux_par_moyen" in r and isinstance(r["totaux_par_moyen"], dict):
        for k, v in r["totaux_par_moyen"].items():
            if isinstance(v, dict) and "total" in v:
                v["total_euros"] = f"{v['total'] / 100:.2f}"
        if "total" in r["totaux_par_moyen"]:
            r["totaux_par_moyen"]["total_euros"] = f"{r['totaux_par_moyen']['total'] / 100:.2f}"
    # tva : ttc/ht/tva en euros
    if "tva" in r and isinstance(r["tva"], dict):
        for taux, v in r["tva"].items():
            if isinstance(v, dict):
                v["total_ttc_euros"] = f"{v.get('total_ttc', 0) / 100:.2f}"
                v["total_ht_euros"] = f"{v.get('total_ht', 0) / 100:.2f}"
                v["total_tva_euros"] = f"{v.get('total_tva', 0) / 100:.2f}"
    # adhesions/billets/remboursements : total en euros
    for section_key in ("adhesions", "billets"):
        if section_key in r and isinstance(r[section_key], dict):
            section = r[section_key]
            if "total" in section:
                section["total_euros"] = f"{section['total'] / 100:.2f}"
            for v in section.get("detail", {}).values():
                if "total" in v:
                    v["total_euros"] = f"{v['total'] / 100:.2f}"
    if "remboursements" in r and isinstance(r["remboursements"], dict):
        for k, v in r["remboursements"].items():
            if isinstance(v, dict) and "total" in v:
                v["total_euros"] = f"{v['total'] / 100:.2f}"
    # synthese : valeurs en euros
    if "synthese_operations" in r:
        for section, moyens in r["synthese_operations"].items():
            if isinstance(moyens, dict):
                r["synthese_operations"][section] = {
                    code: {"total": val, "total_euros": f"{val / 100:.2f}"}
                    for code, val in moyens.items()
                }
    return r
```

### Définir `change_form_before_template` sur le ModelAdmin

```python
change_form_before_template = "comptabilite/admin/change_form_before.html"
```

### Acceptance B1

- [ ] Partial `_sections_rapport.html` créé avec les 8 sections + en-tête + footer
- [ ] `change_form_before.html` créé, include le partial, cache les fieldsets
- [ ] Helper `_enrichir_rapport_pour_template` au niveau module
- [ ] `changeform_view` override dans `ClotureCaisseAdmin`
- [ ] `change_form_before_template` défini sur le ModelAdmin
- [ ] 1 test smoke vérifie que la page détail retourne 200 avec les `data-testid` attendus
- [ ] Tous les tests précédents passent toujours (S1 5 + S2 17 + S3 1 = 23 total)
- [ ] `manage.py check` 0 issue

---

## Bloc B2 — Vue temps réel + bandeau changelist

### Files
- Create: `comptabilite/templates/comptabilite/admin/changelist_before.html`
- Create: `comptabilite/templates/comptabilite/views/rapport_temps_reel.html`
- Modify: `comptabilite/admin.py` (ajout `get_urls`, vue `rapport_temps_reel`, `changelist_before_template`)
- Modify: `tests/pytest/test_comptabilite_admin.py` (append 2 tests)

### Tests à écrire

```python
def test_admin_changelist_contient_lien_temps_reel(admin_client):
    """
    La page liste contient un lien vers /admin/comptabilite/cloturecaisse/rapport-temps-reel/.
    """
    client, _ = admin_client
    response = client.get("/admin/comptabilite/cloturecaisse/")
    contenu = response.content.decode("utf-8")
    assert response.status_code == 200
    assert 'data-testid="comptabilite-bouton-temps-reel"' in contenu
    assert "/admin/comptabilite/cloturecaisse/rapport-temps-reel/" in contenu


def test_admin_rapport_temps_reel_se_charge(admin_client):
    """
    GET /admin/comptabilite/cloturecaisse/rapport-temps-reel/ retourne 200
    avec les sections du rapport.
    """
    client, _ = admin_client
    response = client.get("/admin/comptabilite/cloturecaisse/rapport-temps-reel/")
    contenu = response.content.decode("utf-8")
    assert response.status_code == 200
    # data-testid sur le conteneur HTMX
    assert 'data-testid="comptabilite-rapport-temps-reel-zone"' in contenu
    # aria-live obligatoire pour HTMX
    assert 'aria-live="polite"' in contenu
```

### Vue Python (à ajouter dans `ClotureCaisseAdmin`)

```python
def get_urls(self):
    urls = super().get_urls()
    from django.urls import path
    custom = [
        path(
            "rapport-temps-reel/",
            self.admin_site.admin_view(self.rapport_temps_reel),
            name="comptabilite_cloturecaisse_temps_reel",
        ),
    ]
    return custom + urls


def rapport_temps_reel(self, request):
    """
    Vue admin custom : agrege en temps reel les LigneArticle depuis la
    derniere cloture journaliere jusqu'a maintenant.
    Refresh HTMX toutes les 30 secondes.
    """
    from django.shortcuts import render
    from django.utils import timezone
    from comptabilite.models import ClotureCaisse
    from comptabilite.services import RapportComptableService

    derniere = (
        ClotureCaisse.objects
        .filter(niveau=ClotureCaisse.NIVEAU_JOURNALIER)
        .order_by("-datetime_fin")
        .first()
    )
    if derniere:
        datetime_debut = derniere.datetime_fin
    else:
        # Pas de cloture J : on prend depuis ce matin minuit local
        now_local = timezone.localtime()
        datetime_debut = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    datetime_fin = timezone.now()

    service = RapportComptableService(datetime_debut, datetime_fin)
    rapport_brut = service.generer_rapport_complet()
    rapport = _enrichir_rapport_pour_template(rapport_brut)

    context = {
        **self.admin_site.each_context(request),
        "title": "Rapport temps réel",
        "rapport": rapport,
        "datetime_debut": datetime_debut,
        "datetime_fin": datetime_fin,
        "nb_transactions": service.queryset.count(),
        "opts": self.model._meta,
    }
    return render(request, "comptabilite/views/rapport_temps_reel.html", context)
```

### Template `rapport_temps_reel.html`

Hérite de `admin/base_site.html` (template admin Unfold standard). Doit :
1. Title : « Rapport temps réel — clôture en cours »
2. Conteneur `<div id="rapport-temps-reel-zone" data-testid="comptabilite-rapport-temps-reel-zone" aria-live="polite" hx-get="..." hx-trigger="every 30s" hx-target="this" hx-swap="innerHTML">`
3. Include `_sections_rapport.html` dans le conteneur
4. Style sticky-header avec le timestamp de dernière mise à jour
5. Note importante : la zone HTMX **n'inclut PAS** la balise `<body hx-headers...>` (déjà gérée par le base template tenant) — mais sur l'admin, on est sur `admin/base_site.html` qui n'a pas les headers HTMX. **Solution** : injecter HTMX en `<script>` local + `hx-headers` sur l'élément lui-même.

```html
{% extends "admin/base_site.html" %}
{% load i18n %}

{% block extrahead %}
{{ block.super }}
<script src="{{ STATIC_URL }}admin/js/vendor/htmx/htmx.min.js"></script>
<style>
    /* CSS inline — voir djc.md règle Unfold (pas de Tailwind custom) */
    .comptabilite-tr-header {
        position: sticky;
        top: 0;
        background: var(--color-base-0);
        padding: 12px 16px;
        border-bottom: 1px solid var(--color-base-200);
        z-index: 10;
    }
    .comptabilite-tr-meta { color: var(--color-base-500); font-size: 0.875rem; }
</style>
{% endblock %}

{% block content %}
<div class="comptabilite-tr-header">
    <h1 style="margin: 0;">{% translate "Rapport temps réel" %}</h1>
    <p class="comptabilite-tr-meta">
        {% blocktrans with debut=datetime_debut|date:"d/m/Y H:i" fin=datetime_fin|date:"d/m/Y H:i" %}
        Période : du {{ debut }} au {{ fin }} — refresh automatique toutes les 30s.
        {% endblocktrans %}
    </p>
</div>

<div id="rapport-temps-reel-zone"
     data-testid="comptabilite-rapport-temps-reel-zone"
     aria-live="polite"
     hx-get="{% url 'staff_admin:comptabilite_cloturecaisse_temps_reel' %}"
     hx-trigger="every 30s"
     hx-target="this"
     hx-swap="outerHTML"
     hx-select="#rapport-temps-reel-zone">
    {% include "comptabilite/admin/_sections_rapport.html" %}
</div>
{% endblock %}
```

Note : le pattern HTMX `hx-swap="outerHTML" hx-select="#rapport-temps-reel-zone"` permet à HTMX de re-fetch toute la page et de remplacer la zone par la nouvelle version de cette même zone (auto-refresh sans changer d'URL).

Attention : `htmx.min.js` doit exister dans les statics admin. **Vérifier** s'il existe déjà dans le projet (probablement `BaseBillet/static/js/htmx.min.js` ou ailleurs). Si non, utiliser la CDN `https://unpkg.com/htmx.org@1.9.10` ou ajouter une copie locale.

→ **Vérifier d'abord** : `find /home/jonas/TiBillet/dev/Lespass -name "htmx*.js" -not -path "*/node_modules/*"` puis adapter le chemin.

### Template `changelist_before.html`

Bandeau Unfold avec lien vers la vue temps réel :

```html
{% load i18n %}
<div style="background: var(--color-base-100); border: 1px solid var(--color-base-200); border-radius: 8px; padding: 16px 20px; margin-bottom: 20px;">
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;">
        <div>
            <h3 style="margin: 0 0 4px 0; font-size: 1rem;">{% translate "Real-time monitoring" %}</h3>
            <p style="margin: 0; color: var(--color-base-500); font-size: 0.875rem;">
                {% translate "View the current shift's sales aggregated since the last daily closure." %}
            </p>
        </div>
        <a href="{% url 'staff_admin:comptabilite_cloturecaisse_temps_reel' %}"
           data-testid="comptabilite-bouton-temps-reel"
           style="background: var(--color-primary-600); color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-weight: 500;">
            {% translate "Open real-time report" %}
        </a>
    </div>
</div>
```

### Définir `changelist_before_template`

```python
changelist_before_template = "comptabilite/admin/changelist_before.html"
```

### Acceptance B2

- [ ] Vue `rapport_temps_reel` enregistrée dans `get_urls()`
- [ ] Page page `/admin/comptabilite/cloturecaisse/rapport-temps-reel/` retourne 200 avec le `data-testid` + `aria-live`
- [ ] Bandeau changelist contient le lien vers la vue
- [ ] HTMX refresh `every 30s` fonctionne
- [ ] 2 tests smoke passent
- [ ] 25 tests total (5 S1 + 17 S2 + 3 S3)
- [ ] `manage.py check` 0 issue

---

## Validation visuelle (maintaineur)

```
1. Liste : https://lespass.tibillet.localhost/admin/comptabilite/cloturecaisse/
   → bandeau « Real-time monitoring » avec bouton bleu en haut.
   → 1 clôture en liste (#1, niveau J, datée d'hier).

2. Détail : cliquer sur la clôture
   → rapport visuel avec 8 sections lisibles.
   → fieldsets cachés (pas de form édition).
   → en-tête avec numéro séquentiel, période, hash.

3. Temps réel : cliquer « Open real-time report »
   → page se charge, 8 sections affichées.
   → en haut : période [dernière clôture J → maintenant].
   → ouvrir DevTools Network, voir un hx-get toutes les 30s.
```

## Message de commit suggéré (à fournir par le dernier subagent)

```
feat(comptabilite): S3 — templates admin + vue rapport temps réel

- comptabilite/templates/comptabilite/admin/_sections_rapport.html :
  partial réutilisable affichant les 8 sections du rapport (totaux par
  moyen, TVA, ventes par catégorie, adhésions, billets, remboursements,
  synthèse, infos légales). CSS inline (var Unfold).
- change_form_before.html : fiche détail clôture immuable. En-tête avec
  numéro séquentiel, période, hash. Fieldsets cachés.
- changelist_before.html : bandeau au-dessus de la liste avec lien vers
  la page « rapport temps réel ».
- views/rapport_temps_reel.html : page autonome HTMX avec refresh every
  30s. aria-live="polite" pour les lecteurs d'écran.
- comptabilite/admin.py : changeform_view override (injecte cloture +
  rapport), get_urls (ajoute /rapport-temps-reel/), rapport_temps_reel
  view (agrège depuis dernière clôture J jusqu'à now), helper module
  _enrichir_rapport_pour_template (pré-format centimes → euros).
- tests/pytest/test_comptabilite_admin.py : 3 tests smoke (changeform
  200 + sections présentes, changelist contient lien, temps réel 200 +
  HTMX + a11y).

Référence : TECH_DOC/SESSIONS/COMPTABILITE/SPEC.md §5, §8, §9 (S3).
Plan : TECH_DOC/SESSIONS/COMPTABILITE/PLAN-S3-templates-admin-temps-reel.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Pièges anticipés pour S3

1. **`change_form_before_template` vs `change_form_template`** — Unfold accepte les 2 hooks. Le « before » s'insère **avant** les fieldsets standard. Préférer `change_form_before_template` (mieux pour notre cas : on cache les fieldsets résiduels par CSS).
2. **`changeform_view` signature** — le 4e param est `extra_context`, pas un autre nom. Passer `extra_context=extra_context` au `super().changeform_view(...)`.
3. **`get_urls` order matters** — les URLs custom doivent être AVANT `super().get_urls()` pour matcher `rapport-temps-reel/` avant `<uuid:object_id>/change/`. Sinon Django interprète "rapport-temps-reel" comme un UUID et lève une erreur.
4. **HTMX non chargé sur l'admin** — l'admin Django n'inclut pas HTMX par défaut. Soit on l'injecte via `{% block extrahead %}`, soit on utilise une CDN. Vérifier si htmx.min.js existe déjà en statics du projet.
5. **`each_context` indispensable** dans la vue custom — sans ça, le template admin n'a pas les variables Unfold (sidebar, theme, etc.) et casse l'affichage.
6. **`opts = model._meta`** doit être passé au context pour que les breadcrumbs admin fonctionnent.
7. **Permissions** : `self.admin_site.admin_view(self.rapport_temps_reel)` wrappe avec `@staff_member_required` automatiquement. Pas besoin de re-vérifier.
8. **Pré-format centimes → euros côté Python** — pas de filtre custom dans le template. Le helper `_enrichir_rapport_pour_template` ajoute des suffixes `_euros` aux dict. Plus simple et plus testable.
9. **CSS inline obligatoire** dans l'admin Unfold — cf. djc.md : les classes Tailwind custom (`bg-yellow-600`) ne sont PAS dans le bundle Unfold et rendent invisibles.
10. **`data-testid` partout** sur les sections (cf. djc.md). Convention : `comptabilite-section-<slug>` où slug est la clé du rapport en kebab-case.

## Estimation

- Bloc B1 : ~60 min (le partial est gros — 8 sections)
- Bloc B2 : ~40 min

**Total : ~1h40** (hors validation maintaineur).
