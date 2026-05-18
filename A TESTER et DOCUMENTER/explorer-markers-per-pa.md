# Carte explorer ROOT : 1 marker par PostalAddress

**Chantier :** CHANTIER-05 (cf. `TECH_DOC/SESSIONS/SEO/`)

## Ce qui a ete fait

Refacto de la carte `/explorer/` du tenant ROOT :
- **Avant** : 1 marker par tenant, positionne sur `Configuration.postal_address`.
- **Apres** : 1 marker par `PostalAddress` active (1 tenant peut donc avoir N markers).
- **Popup riche** : nom adresse + adresse formatee + lien tenant (avec logo) + 5 prochains events futurs + lien "voir tous (N)" si plus.

Architecture : nouveau cache `SEOCache.AGGREGATE_POINTS` (1 entree par PA active),
construit par `refresh_seo_cache` etape 6. La cache `AGGREGATE_LIEUX` reste
intacte (utilisee par les autres vues `/lieu/`, `/lieux/`, etc.).

## Tests automatises a lancer

```bash
# Tests unitaires (8 tests, ~1s)
docker exec -e API_KEY=dummy lespass_django poetry run pytest \
    tests/pytest/test_seo_aggregate_points.py -v

# Tests E2E Playwright (necessite serveur tournant + cache a jour)
# 1. Refresh cache d'abord
docker exec lespass_django poetry run python manage.py shell -c \
    "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"
# 2. Run tests
cd tests/playwright && npx playwright test 35-explorer-markers-per-pa.spec.ts
```

## Tests manuels a realiser

### Test 1 : Activation initiale + comptage markers

1. Forcer le refresh du cache :
   ```bash
   docker exec lespass_django poetry run python manage.py shell -c \
     "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"
   ```
   Verifier la sortie : `AGGREGATE_POINTS ecrit : N points`.

2. Ouvrir `http://localhost:8002/explorer/` (tenant ROOT).
3. Compter visuellement les markers (zoomer pour eclater les clusters).
4. **Attendu** : nombre de markers >= nombre de tenants vivants (avant le chantier, c'etait 1 par tenant).

### Test 2 : Universite Populaire Villeurbanne (cas multi-PA)

1. Ouvrir `/explorer/`, zoomer sur Villeurbanne / Lyon.
2. **Attendu** : voir plusieurs markers separes pour les lieux de UPOP (Le Rize, Villa Urbana, Theatre de l'Iris, MJC Jean Mace, etc.).
3. Cliquer sur l'un d'eux : popup contient le nom de l'adresse + "Universite Populaire Villeurbanne" + events futurs si presents.

### Test 3 : Tenant avec 1 seule PA principale

1. Identifier un tenant simple (1 lieu fixe, ex. La Raffinerie).
2. Verifier 1 seul marker pour ce tenant sur la carte.
3. Popup : nom du lieu en gras + adresse + lien tenant + events futurs.

### Test 4 : Tenant sans events futurs (mais avec produits)

1. Identifier un tenant qui a 1 PA + 0 event futur + 1 produit publie.
2. Verifier qu'il apparait quand meme (filtre "vivant" = event futur OU produit publie).
3. Popup : section "Evenements futurs" absente.

### Test 5 : Compteur > 5 events sur une PA

1. Si tu identifies une PA avec > 5 events futurs (rare mais possible).
2. Cliquer le marker, verifier popup : 5 events affiches + lien "+ N autre(s)".

### Test 6 : Pas de regression sur AGGREGATE_LIEUX

1. Ouvrir `/lieux/` (vue listing tenants) : doit toujours marcher.
2. Ouvrir `/lieu/<slug>/` d'un tenant : doit toujours marcher.
3. Faire une recherche : doit toujours marcher.

### Test 7 : Filtres explorer (pills)

1. Pill "Tous" : tous les tenants visibles.
2. Pill "Lieux" : meme resultat (tous les tenants restent visibles).
3. Pill "Evenements" : seulement les tenants ayant >=1 event futur.
4. Recherche texte : filtre les tenants par nom/locality.

### Verifier en base / DB checks

```bash
# Vue d'ensemble des caches
docker exec lespass_django poetry run python manage.py shell -c "
from seo.models import SEOCache
for c in SEOCache.objects.filter(tenant=None):
    if c.cache_type == 'aggregate_points':
        print(f'AGGREGATE_POINTS: {len(c.data[\"points\"])} points')
    elif c.cache_type == 'aggregate_lieux':
        print(f'AGGREGATE_LIEUX: {len(c.data[\"lieux\"])} lieux (intact)')
"
```

## Compatibilite

- **AGGREGATE_LIEUX intact** : les vues `/lieu/<slug>/`, `/lieux/`, recherche ROOT, JSON-LD federation utilisent cette cache et ne sont pas affectees.
- **Rollback facile** : supprimer la constante `AGGREGATE_POINTS` dans `seo/models.py` + la fonction `build_aggregate_points` dans `seo/services.py`. La vue `/explorer/` retombera sur `{"points": []}` (carte vide mais pas d'erreur).
- **Mobile** : la carte n'est initialisee qu'au 1er toggle vers "Carte" (perf).

## Limitations connues

- Si une PA est partagee par 2+ events, popup liste les 5 events les plus proches dans le temps (tries par `datetime` ASC).
- Les events passes sont skip (filtre Django `datetime__gte=now` dans `get_events_for_tenants`).
- `events_futurs_count_total` reflete uniquement les events futurs publies (pas les drafts).
