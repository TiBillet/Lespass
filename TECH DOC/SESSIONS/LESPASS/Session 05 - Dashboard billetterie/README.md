# Session 05 — Dashboard Billetterie

> **Chantier :** Bilan billetterie interne (extension)
> **Spec :** `../specs/2026-04-03-dashboard-billetterie-design.md`
> **Dépend de :** Sessions 01-04 (page bilan, filtre `cents_to_euros`, `RapportBilletterieService`)
> **Produit :** Page dashboard dans la sidebar Billetterie, cartes miniatures events, query annotée + cache

---

## Objectif

Ajouter un "Dashboard" en première position dans la section Billetterie de la sidebar admin. Cette page affiche des cartes miniatures pour chaque event (à venir en haut, 6 derniers passés en bas) avec les indicateurs clés : taux de remplissage, vendus, scannés, CA net.

---

## Contexte technique

### Sidebar Billetterie existante

Fichier : `Administration/admin/dashboard.py`, ligne 87-148. La section Billetterie est conditionnelle sur `configuration.module_billetterie`. Les items sont une liste de dicts `{title, icon, link, permission}`.

Le lien Dashboard doit être **en première position** de cette liste.

### EventAdmin.get_urls()

Fichier : `Administration/admin/events.py`. Le `get_urls()` existe déjà (ajouté en Session 02) avec les routes bilan. La route `dashboard/` doit être ajoutée **avant** les routes avec `object_id` (sinon Django interprète "dashboard" comme un UUID).

### Filtre dans EventAdmin.get_queryset()

Le queryset de la changelist exclut déjà :
- `categorie=Event.ACTION`
- `parent__isnull=False`

Le dashboard doit appliquer les mêmes filtres + `archived=False`.

### Cache multi-tenant

`django_tenants.cache.make_key` est configuré dans settings.py — les clés sont préfixées par tenant. On ajoute quand même `connection.tenant.pk` dans la clé pour être explicite (FALC).

### Filtre `cents_to_euros`

Disponible dans `BaseBillet/templatetags/billet_filters.py` (créé en Session 02). Usage : `{% load billet_filters %}` puis `{{ montant|cents_to_euros }}`.

---

## Tâches

### 5.1 — Ajouter la route dashboard dans get_urls()

Dans `Administration/admin/events.py`, dans `EventAdmin.get_urls()`, ajouter **en première position** de `custom_urls` (avant les routes bilan qui utilisent `object_id`) :

```python
path(
    'dashboard/',
    self.admin_site.admin_view(self.vue_dashboard_billetterie),
    name='BaseBillet_event_dashboard',
),
```

Note : `path()` et pas `re_path()` — pas besoin de regex ici.

### 5.2 — Implémenter la vue `vue_dashboard_billetterie()`

Méthode dans `EventAdmin` :

```python
def vue_dashboard_billetterie(self, request):
    """
    Dashboard billetterie : cartes miniatures des events avec indicateurs.
    / Ticketing dashboard: miniature event cards with key indicators.
    LOCALISATION : Administration/admin/events.py
    """
```

**Logique :**
1. Vérifier le cache : `cache.get(f"dashboard_billetterie:{connection.tenant.pk}")`
2. Si cache miss :
   - Query annotée (1 seule query, voir spec section 3.3)
   - Séparer : `events_a_venir` (datetime >= now, order by datetime asc) et `events_passes` (datetime < now, order by -datetime, [:6])
   - Pour chaque event, calculer `ca_net` et `taux_remplissage` en Python
   - Mettre en cache (TTL 120s)
3. Rendre le template avec le contexte

**Contexte template :**
```python
{
    **self.admin_site.each_context(request),
    "events_a_venir": events_a_venir,
    "events_passes": events_passes,
    "title": _("Ticketing dashboard"),
    "opts": self.model._meta,
}
```

### 5.3 — Ajouter le lien Dashboard dans la sidebar

Dans `Administration/admin/dashboard.py`, dans la section `module_billetterie` (ligne 92), ajouter **en première position** de `items` :

```python
{
    "title": _("Dashboard"),
    "icon": "monitoring",
    "link": reverse_lazy("staff_admin:BaseBillet_event_dashboard"),
    "permission": admin_permission,
},
```

### 5.4 — Créer le template `dashboard_billetterie.html`

Fichier : `Administration/templates/admin/event/dashboard_billetterie.html`

Extends `admin/base_site.html`. Deux sections avec grille de cartes.

### 5.5 — Créer le partial `event_card.html`

Fichier : `Administration/templates/admin/event/partials/event_card.html`

Carte miniature d'un event. Reçoit la variable `event` (annoté avec `nb_vendus`, `nb_scannes`, `ca_net`, `taux_remplissage`, `nb_reservations`).

Contenu :
- Nom + date
- Progress bar (vendus / jauge_max)
- 3 chiffres : vendus, scannés, CA net
- 2 liens : "Bilan" (si nb_reservations > 0) + "Modifier"
- Inline styles, `data-testid="event-card"`

### 5.6 — Tests

Fichier : `tests/pytest/test_dashboard_billetterie.py`

- `test_dashboard_accessible` : GET → 200
- `test_dashboard_event_inexistant_non_affiche` : les events archivés sont exclus
- `test_dashboard_contient_liens_bilan` : vérifier la présence des liens

---

## Vérification

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_dashboard_billetterie.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=short
```

---

## Résultat attendu

- URL `/admin/BaseBillet/event/dashboard/` fonctionnelle
- Lien "Dashboard" en 1ère position dans la sidebar Billetterie
- Cartes events avec progress bar, chiffres, liens
- Cache 2 min (pas d'invalidation)
- ~3 tests pytest
- 0 régression
