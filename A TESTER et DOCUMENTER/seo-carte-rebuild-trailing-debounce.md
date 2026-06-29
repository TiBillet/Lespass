# Carte réseau : rebuild d'agrégats en débounce « trailing »

## Ce qui a été fait

Correction du bug « un évènement / une adresse fraîchement sauvé(e) n'apparaît
pas sur la carte `/explorer/` du ROOT » (apparaissait seulement après le beat
Celery, jusqu'à 4 h plus tard).

La carte lit l'agrégat `AGGREGATE_POINTS`, recomposé par
`rebuild_seo_aggregates`. Ce rebuild était planifié en **débounce front
montant** (180 s après la *première* modif d'une rafale), ce qui pouvait
recombiner un fragment `TENANT_POINTS` pas encore à jour, sans rebuild de
rattrapage. On passe à un **débounce front descendant (trailing)** : le rebuild
s'exécute **après la dernière modif**.

### Modifications
| Fichier | Changement |
|---|---|
| `seo/tasks.py` | `planifier_rebuild_agregats()` (pousse `seo_rebuild_echeance`, planifie ≤ 1 rebuild/fenêtre via le verrou `seo_rebuild_planifie`) ; `rebuild_seo_aggregates(force=False)` : s'abstient et se replanifie si l'échéance est future, sinon recombine ; beat en `force=True` ; constantes `REBUILD_TRAILING_WINDOW=15`, `REBUILD_MARGE=2` |
| `BaseBillet/signals.py` | `declencher_refresh_seo_cache` : fragment `refresh_tenant_seo_cache` countdown 5 s + TTL verrou 5 s (fin de la « fenêtre morte ») ; rebuild via `planifier_rebuild_agregats()` |
| `tests/pytest/test_seo_cache_fragments.py` | +4 tests |

## Tests à réaliser

### Test 1 : pytest (déterministe)
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_cache_fragments.py -q
```
Attendu : 9 passed. Les 4 nouveaux tests couvrent :
- abstention + replanification si échéance future ;
- recombinaison réelle quand l'échéance est atteinte ;
- `force=True` ignore l'échéance (beat) ;
- `planifier_rebuild_agregats` pousse l'échéance et ne planifie qu'1 rebuild/fenêtre.

### Test 2 : manuel bout-en-bout (serveur + worker Celery + beat actifs)
Prérequis : worker Celery **et** beat lancés (sinon aucune tâche async ne
s'exécute).

1. Ouvrir la carte ROOT : `https://lespass.tibillet.localhost/explorer/`.
2. Dans l'admin d'un tenant « vivant », créer un nouvel évènement publié et futur
   (ou ajouter/déplacer une adresse géocodée).
3. Attendre ~20 s puis recharger `/explorer/`.
4. **Attendu :** le nouveau marqueur / la nouvelle adresse apparaît (avant : il
   fallait attendre le beat 4 h).

### Test 3 : rafale d'édition (le cas qui plantait)
1. Sauvegarder un évènement, puis ré-éditer et re-sauvegarder 2–3 fois sur ~30 s
   (simule un éditeur qui corrige).
2. Attendre ~20 s après la **dernière** sauvegarde, recharger `/explorer/`.
3. **Attendu :** toutes les modifs (y compris la dernière) sont visibles. Avant
   le fix, la dernière modif d'une rafale pouvait rester invisible jusqu'au beat.

### Vérifications en base / cache (optionnel)
```bash
# Forcer un rebuild complet immédiat (équivaut au beat) :
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c \
  "from seo.tasks import rebuild_seo_aggregates; print(rebuild_seo_aggregates(force=True))"

# Inspecter l'échéance trailing courante :
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c \
  "from django.core.cache import cache; print(cache.get('seo_rebuild_echeance'), cache.get('seo_rebuild_planifie'))"
```

## Bug L1 cross-schema (corrigé en même temps — cause racine du retard 4 h)

Découvert pendant la vérification E2E. Le L1 Memcached lu par les pages restait
périmé jusqu'au TTL (4 h) car `CACHES['default']` préfixe les clés par schema
(`django_tenants.cache.make_key`). Le worker écrivait l'agrégat global sous la clé
du tenant déclencheur, invisible des autres schemas. Fix : `set_memcached_l1` /
`get_memcached_l1` épinglent le schema `public` (clé L1 globale partagée).

### Test du fix L1 (Chrome + backend)
1. Noter le compteur de `https://tibillet.localhost/explorer/` (ex : « 4 lieux · N événements »).
2. Créer un event admin **publié, futur, sur une PA géocodée** (sous le cap de 5 events du popup pour voir le compteur bouger).
3. Attendre ~20 s **sans rien recalculer manuellement**.
4. Recharger `/explorer/` → le compteur doit avoir augmenté.
5. Vérifier la cohérence L1 sur tous les schemas :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from seo.services import get_memcached_l1
from seo.models import SEOCache
g=lambda d:[x['event_count'] for x in (d or {}).get('lieux',[]) if x['name']=='Lespass']
print('public:', g(get_memcached_l1(SEOCache.AGGREGATE_LIEUX,None)))
for sc in ['lespass','le-coeur-en-or','chantefrein']:
    with tenant_context(Client.objects.get(schema_name=sc)): print(sc, g(get_memcached_l1(SEOCache.AGGREGATE_LIEUX,None)))
"
```
**Attendu :** valeurs **identiques** sur tous les schemas (avant le fix, elles divergeaient).

## Compatibilité
- **Aucune migration.** Logique Celery + cache uniquement.
- Vues inchangées : mêmes `cache_type` consommés (`AGGREGATE_POINTS`, etc.).
- Le beat 4 h reste le filet anti-dérive (`force=True` → recombine toujours).
- Dépendance opérationnelle : un **worker Celery actif** est nécessaire pour que
  le rafraîchissement quasi temps réel fonctionne (sinon, seul le beat agit).
- Anciennes clés L1 préfixées par tenant : expirent seules (TTL 4 h), plus lues.
