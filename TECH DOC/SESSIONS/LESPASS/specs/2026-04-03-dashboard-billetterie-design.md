# Design Spec — Dashboard Billetterie

> **Extension du sous-projet 1** (Bilan billetterie interne).
> Ajoute une page dashboard dans la section Billetterie de l'admin Unfold.
>
> Date : 2026-04-03
> Auteurs : Jonas (mainteneur) + Claude Code (brainstorming)
> Dépend de : Sessions 01-04 du bilan billetterie (`RapportBilletterieService`, page bilan, filtre `cents_to_euros`)

---

## 1. Objectif

Fournir une vue d'ensemble de tous les événements (passés et à venir) dans une page dédiée de la section Billetterie. Chaque événement est affiché comme une carte miniature avec ses indicateurs clés : taux de remplissage, billets vendus/scannés, CA net.

L'organisateur arrive sur cette page en premier quand il clique sur "Billetterie" dans la sidebar. Il voit immédiatement l'état de ses ventes sans avoir à ouvrir chaque event un par un.

---

## 2. Décisions prises

| # | Décision | Justification |
|---|----------|---------------|
| 1 | Page dédiée dans la sidebar Billetterie (pas dans le dashboard global) | Chaque module a son propre espace |
| 2 | 2 sections : "À venir" (tous) + "Passés" (6 derniers) | L'organisateur veut d'abord piloter le futur |
| 3 | Query annotée unique (pas N appels au service) | Performance : 1 query au lieu de 20 |
| 4 | Cache TTL 2 min, pas d'invalidation | Simple, pas de signaux fragiles |
| 5 | Events archivés exclus | Pas de bruit |
| 6 | Lien "Bilan" + "Modifier" par carte | 2 actions par event |
| 7 | Pas de pagination, lien changelist pour l'historique complet | YAGNI — 6 passés suffisent |

---

## 3. Architecture

### 3.1 — URL et sidebar

URL : `/admin/BaseBillet/event/dashboard/`

Enregistrée via `get_urls()` dans `EventAdmin`. Placée AVANT les patterns par défaut (sinon Django interprète `dashboard/` comme un UUID d'event).

Entrée sidebar dans `get_sidebar_navigation()` (fichier `dashboard.py`) :
```python
# Dans la section Billetterie, en première position
{
    "title": _("Dashboard"),
    "icon": "monitoring",
    "link": reverse_lazy("staff_admin:BaseBillet_event_dashboard"),
}
```

### 3.2 — Vue

Méthode `vue_dashboard_billetterie()` dans `EventAdmin`. La vue :

1. Vérifie le cache (`dashboard_billetterie:{tenant_pk}`)
2. Si cache miss : exécute la query annotée
3. Sépare en 2 listes : à venir + passés (6 derniers)
4. Stocke en cache (TTL 120 secondes)
5. Rend le template

### 3.3 — Query annotée

Une seule query récupère tous les events non-archivés avec leurs indicateurs :

```python
from django.db.models import Count, Sum, Q
from django.db.models.functions import Coalesce

events_avec_stats = Event.objects.filter(
    archived=False,
    parent__isnull=True,      # Exclure les sous-events (actions)
).exclude(
    categorie=Event.ACTION,   # Exclure les actions (même filtre que le get_queryset)
).annotate(
    nb_vendus=Count(
        'reservation__tickets',
        filter=Q(reservation__tickets__status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED]),
        distinct=True,
    ),
    nb_scannes=Count(
        'reservation__tickets',
        filter=Q(reservation__tickets__status=Ticket.SCANNED),
        distinct=True,
    ),
    ca_ttc=Coalesce(
        Sum(
            'reservation__lignearticles__amount',
            filter=Q(reservation__lignearticles__status=LigneArticle.VALID),
        ),
        0,
    ),
    ca_rembourse=Coalesce(
        Sum(
            'reservation__lignearticles__amount',
            filter=Q(reservation__lignearticles__status=LigneArticle.REFUNDED),
        ),
        0,
    ),
    nb_reservations=Count('reservation', distinct=True),
).select_related('postal_address')
```

Le `ca_net` est calculé en Python : `event.ca_ttc - event.ca_rembourse`.
Le `taux_remplissage` aussi : `round((event.nb_vendus / event.jauge_max) * 100, 1) if event.jauge_max > 0 else 0.0`.

### 3.4 — Cache

```python
from django.core.cache import cache
from django.db import connection

cache_key = f"dashboard_billetterie:{connection.tenant.pk}"
cache_ttl = 120  # 2 minutes

donnees = cache.get(cache_key)
if donnees is None:
    # Exécuter la query + séparer futur/passé
    donnees = {...}
    cache.set(cache_key, donnees, cache_ttl)
```

Le cache stocke les 2 listes (à venir + passés) déjà séparées et annotées. Pas de sérialisation complexe — ce sont des querysets évalués en listes de dicts.

Note : `django_tenants.cache.make_key` est déjà configuré dans settings.py pour préfixer les clés par tenant. Mais on ajoute quand même le `tenant.pk` dans la clé pour être explicite (FALC).

### 3.5 — Carte miniature

Chaque carte affiche :

```
┌─────────────────────────────────────────────┐
│  Festival Rock du Bout du Monde             │
│  Samedi 15 mars 2026, 20h00                │
│                                             │
│  ████████████████░░░░  423/500  (84,6 %)   │
│                                             │
│  Vendus: 423    Scannés: 387    CA: 4 110 € │
│                           [Bilan] [Modifier] │
└─────────────────────────────────────────────┘
```

- **Nom** : `event.name`
- **Date** : `event.datetime|date:"l d F Y, H:i"`
- **Progress bar** : `nb_vendus / jauge_max`
- **Vendus** : `nb_vendus` (Ticket K+S)
- **Scannés** : `nb_scannes` (Ticket S)
- **CA net** : `(ca_ttc - ca_rembourse)|cents_to_euros` €
- **Lien "Bilan"** : vers `/admin/BaseBillet/event/{pk}/bilan/` — masqué si `nb_reservations == 0`
- **Lien "Modifier"** : vers `/admin/BaseBillet/event/{pk}/change/`

### 3.6 — Templates

```
Administration/templates/admin/event/
├── dashboard_billetterie.html    → page complète (extends admin/base_site.html)
└── partials/
    └── event_card.html           → carte miniature ({% include %} avec variable event)
```

**`dashboard_billetterie.html`** :
- Extends `admin/base_site.html` (layout Unfold avec sidebar)
- Section "Événements à venir" : grille 3 colonnes (`grid-template-columns: repeat(auto-fill, minmax(320px, 1fr))`)
- Section "Événements passés" : même grille, titre + lien "Voir tous" → changelist events
- Inline styles uniquement (pas de Tailwind custom)

**`event_card.html`** :
- Fond blanc, bordure, border-radius 8px
- Progress bar inline (même style que la page bilan)
- Chiffres en grille
- Boutons liens en bas
- `data-testid="event-card-{event.pk}"`

---

## 4. Tests

### pytest

Fichier : `tests/pytest/test_dashboard_billetterie.py`

- `test_dashboard_accessible` : GET `/admin/BaseBillet/event/dashboard/` → 200
- `test_dashboard_non_authentifie` : sans login → 302
- `test_dashboard_contient_events` : vérifier que les events avec réservations apparaissent
- `test_dashboard_exclut_archives` : un event archivé n'apparaît pas
- `test_dashboard_cache` : 2 appels rapides → la 2ème utilise le cache (pas de query)

---

## 5. Fichiers à créer / modifier

| Fichier | Action |
|---|---|
| `Administration/admin/events.py` | Modifier — ajouter URL `dashboard/` + vue `vue_dashboard_billetterie` |
| `Administration/admin/dashboard.py` | Modifier — ajouter lien "Dashboard" dans sidebar Billetterie |
| `Administration/templates/admin/event/dashboard_billetterie.html` | Créer |
| `Administration/templates/admin/event/partials/event_card.html` | Créer |
| `tests/pytest/test_dashboard_billetterie.py` | Créer |

---

## 6. Ce qui est hors périmètre

- Graphiques Chart.js sur le dashboard (les charts sont dans la page bilan)
- Pagination / infinite scroll
- Filtres par date ou catégorie
- Recherche d'events sur le dashboard
- Cache invalidation par signal
- Events hiérarchiques (sous-events / actions)
