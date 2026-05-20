# Liste des évènements : filtre par date en SQL + filtres conservés à la pagination

## Contexte du bug

Sur un gros agenda (festival > 300 évènements sur 3 jours), la page liste des
évènements (`/event/`, skin `faire_festival`) avait deux problèmes liés :

1. **Filtre par date cassé** : le filtre par jour était appliqué en Python
   **après** la pagination (100 évènements/page). Filtrer un jour situé au-delà
   de la page 1 (ex : samedi quand la page 1 ne contient que jeu + début ven)
   renvoyait « aucun résultat ».
2. **Filtres perdus à la pagination** : le bouton « CHARGER PLUS » ne
   transmettait que `&page=N` et le premier tag → recherche/thématique/tags
   multiples disparaissaient après un chargement supplémentaire.

## Ce qui a été fait

| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` — `federated_events_filter` | Nouveau param `date_filter`. Filtre SQL `events.filter(datetime__date=date_filter)` appliqué **après** la collecte des dates/tags (menus déroulants restent complets) et **avant** la pagination. Si une date est filtrée : pagination désactivée, tous les évènements du jour affichés, `has_next=False`. Exclusion du cache si date filtrée. |
| `BaseBillet/views.py` — `_parse_date_filter` | Helper : valide une string ISO `"2025-03-15"` → objet `date` ou `None`. |
| `BaseBillet/views.py` — `_querystring_filtres` | Helper : construit `search=…&thematique=…&tag=a&tag=b` pour le bouton CHARGER PLUS. |
| `BaseBillet/views.py` — cache | Cache versionné : on cache la page principale ET les pages filtrées par **date seule** (1 h). Clé = `event_list_{tenant.uuid}_{jeton}[_date_{iso}]`. |
| `BaseBillet/models.py` — `Event.save()` | Réécrit `event_list_version_{tenant.uuid}` (jeton aléatoire) → invalide page principale + toutes les pages par date d'un coup. |
| `BaseBillet/views.py` — `list()` | Parse + passe `date_filter`, expose `querystring_filtres`. Suppression du filtrage Python post-pagination. |
| `BaseBillet/views.py` — `partial_list()` | Lit `?date=`, le propage, expose `querystring_filtres`. |
| `faire_festival/.../event/list.html` + `partial/list_append.html` | Bouton CHARGER PLUS : `{{ querystring_filtres }}` au lieu de `&tag={{ tags.0 }}`. |

## Tests à réaliser (manuel, sur un tenant skin `faire_festival` avec > 100 évènements)

### Test 1 : filtre par date sur un jour « lointain »
1. Aller sur `/event/`.
2. Vérifier que la page 1 affiche ~100 évènements + bouton « CHARGER PLUS ».
3. Ouvrir le dropdown « Trier par date », choisir un jour dont les évènements
   sont au-delà de la page 1 (ex : samedi d'un festival jeu/ven/sam).
4. **Attendu** : tous les évènements de ce jour s'affichent, **pas** de bouton
   « CHARGER PLUS » (pagination désactivée pour un jour précis).
5. Le libellé du dropdown affiche le jour choisi ; le dropdown reste complet
   (on peut changer de jour). Le bouton « Retirer les filtres » apparaît.

### Test 2 : recherche + CHARGER PLUS conserve le filtre
1. Sur `/event/`, taper un terme de recherche qui renvoie > 100 résultats.
2. Cliquer « Rechercher », puis « CHARGER PLUS ».
3. **Attendu** : la page suivante reste filtrée par la recherche (pas de
   réapparition d'évènements hors recherche).

### Test 3 : filtre par tag/thématique + CHARGER PLUS
1. Filtrer par un tag (ou thématique) ayant > 100 évènements.
2. Cliquer « CHARGER PLUS ».
3. **Attendu** : la page suivante reste filtrée par ce tag/thématique.

### Test 4 : paramètre date invalide
1. Aller sur `/event/?date=pas-une-date`.
2. **Attendu** : pas d'erreur 500, on affiche tout (filtre ignoré).

### Test 5 : fraîcheur du cache par date
1. Filtrer un jour (ex : samedi) → noter les évènements affichés.
2. Dans l'admin, modifier/publier/dépublier un évènement de ce jour.
3. Recharger `/event/?date=<samedi>`.
4. **Attendu** : la liste reflète immédiatement la modification (le cache par
   date est invalidé par `Event.save()` via le jeton de version).

## Vérification en base / debug (optionnel)

```bash
# Compter les évènements publiés à venir d'un tenant (adapter le schema)
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import schema_context
from BaseBillet.models import Event
from django.utils import timezone
with schema_context('lespass'):
    print(Event.objects.filter(published=True, datetime__gte=timezone.now()).count())
"
```

## Compatibilité

- Rétro-compatible : `date_filter=None` par défaut → comportement inchangé pour
  le skin `reunion` (qui n'a pas de filtre date) et pour l'action `embed`.
- Le filtre date est appliqué **après** la collecte des dates/tags : les menus
  déroulants restent complets même quand un jour est sélectionné.
