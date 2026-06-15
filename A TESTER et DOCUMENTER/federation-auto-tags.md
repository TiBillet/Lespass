# Fédération automatique des évènements par tags

## Ce qui a été fait

Un tenant peut s'abonner à des **tags** via `FederationConfiguration.tags_federation` (M2M).
Les évènements de **tout le réseau TiBillet** portant un de ces tags apparaissent alors dans son
**agenda** (`/event/`) ET sur sa **carte** (`/federation/`), **en plus** de sa fédération habituelle
(voisins `FederatedPlace`). Liste vide = comportement inchangé.

- **Sens** : récepteur (j'affiche ce que je veux recevoir), sur tout le réseau (pas que mes voisins).
- **Additif** : ne remplace pas la fédération par voisins ni le champ `private`.
- **Veto `private`** : un event `private=True` d'un autre tenant n'est **jamais** affiché.
- **En cache** : l'identification des tenants concernés lit `AGGREGATE_EVENTS` (zéro requête
  cross-schema) ; l'agenda rend ensuite les events en objets `Event` via le moteur existant.

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | `FederationConfiguration.tags_federation` (M2M) + `save()` régénère le token cache agenda |
| `BaseBillet/migrations/0218_*` | AddField M2M |
| `seo/services.py` | `get_events_for_tenants` → `private` ; `build_aggregate_points` exclut `private` ; helper `get_tenant_uuids_with_event_tags` |
| `BaseBillet/views.py` | `federated_events_filter` (agenda) + `FederationViewset.list` (carto) |
| `Administration/admin_tenant.py` | fieldset « Fédération automatique par tags » + autocomplete |

## Prérequis
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
# Régénérer le cache AVEC le nouveau code (champ private) :
docker exec lespass_django poetry run python /DjangoFiles/manage.py refresh_seo_cache
```
> En prod : **redémarrer le worker Celery** avant le `refresh_seo_cache` (le beat 4h passe par le
> worker ; sans redémarrage il tourne avec l'ancien code et le cache n'aura pas `private`).

## Tests à réaliser

### Test 1 : réglage admin
1. Admin → `admin/BaseBillet/federationconfiguration/`.
2. **Vérifier** un fieldset **« Fédération automatique par tags »** avec un champ autocomplete
   `tags_federation`.
3. Y ajouter un tag présent ailleurs sur le réseau (ex : `entree-libre`, `jazz`, `prix-libre`). Enregistrer.

### Test 2 : agenda enrichi
1. Aller sur `/event/`.
2. **Vérifier** que des évènements d'autres lieux du réseau (portant ce tag) apparaissent, en plus
   des vôtres et de vos voisins. Les retirer du champ → ils disparaissent.

### Test 3 : carto enrichie
1. Aller sur `/federation/`.
2. **Vérifier** que les lieux des tenants ayant un event portant ce tag apparaissent sur la carte/liste,
   en plus de vos voisins.

### Test 4 : veto private (carto nettoyée)
1. Sur un autre tenant, créer un event futur publié **`private=True`** portant le tag suivi.
2. Relancer `refresh_seo_cache`.
3. **Vérifier** que cet event **n'apparaît PAS** : ni dans votre agenda, ni dans le popup carto du lieu.
   (Le veto private vaut désormais pour TOUS les lieux de la carto, pas seulement les nouveaux.)

### Test 5 : liste vide = inchangé
1. Vider `tags_federation`. `/event/` et `/federation/` reviennent au comportement d'avant
   (vous + voisins uniquement).

## Vérifications en base / cache
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell
```
```python
from seo.services import get_tenant_uuids_with_event_tags
from seo.views_common import get_seo_cache
from seo.models import SEOCache

# Le cache porte bien `private` ?
agg = get_seo_cache(SEOCache.AGGREGATE_EVENTS) or {}
ev = agg.get("events", [])
print("events sans private:", sum(1 for e in ev if "private" not in e), "/", len(ev))  # doit être 0

# Quels tenants portent un tag donné (private exclu) ?
print(get_tenant_uuids_with_event_tags(["jazz"]))
```

## Tests automatisés
- `tests/pytest/test_federation_auto_tags.py` (4 tests helper : match slug + veto private + liste vide + cache absent).
- `tests/pytest/test_federation_view_integration.py` (carto, mock complété) + `test_event_wizard_unifie.py` (agenda).
- Validé manuellement end-to-end : abonnement à `entree-libre` → +1 event dans l'agenda, `/event/` et
  `/federation/` à 200.

## Compatibilité
- Aucun changement de logique pour les tenants sans `tags_federation` (rétrocompatible).
- `private` et la fédération par voisins (`FederatedPlace`) restent prioritaires/inchangés.

## i18n
Nouveaux `_()` (verbose_name/help_text de `tags_federation`, fieldset admin) → `makemessages` + `compilemessages` (source FR).
