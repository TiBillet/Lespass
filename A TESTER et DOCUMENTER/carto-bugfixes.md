# Carto (explorer) — correctifs + rafraîchissement auto du cache

> ⚠️ **Codé mais NON validé** : le conteneur `lespass_django` était arrêté au moment du
> dev. Syntaxe Python + JS vérifiée uniquement. À valider visuellement + `manage.py check`.

## Ce qui a été fait

4 points sur le widget explorer partagé (`/explorer/` ROOT **et** `/federation/` tenant).

### Bug 1 — adresse décalée au clic (RÉSOLU)
**Cause :** `pa_id` = `PostalAddress.pk`, non unique entre tenants (PK par schema). Côté
JS, `pa_id` est la clé des markers (`state.markers[pa_id]`) → collision → cliquer sur le
lieu A centrait sur l'adresse du lieu B.
**Fix :** `build_aggregate_points` expose `pa_id = "{tenant_uuid}:{pk}"` (unique). Matching
interne (events, is_main_address) inchangé (pk brut).

### Bug 2 — clic sur un event ne bouge pas la carte (RÉSOLU)
**Cause :** les cartes event n'avaient pas `data-lieu-id` ; `bindListDelegation` ne gérait
que les cartes lieu.
**Fix :** `data-pa-id` sur la carte event + `focusOnPA(paId, tenantId)` (centre sur la PA
de l'event, ou sort proprement si pas de marker).

### Bug 3 — images events/lieux absentes (RÉSOLU)
**Cause :** events toujours en emoji ; cache sans `image_url` (events) ni image (lieux).
**Fix :** cache enrichi (`image_url` events, `image_url`/`tenant_image_url` lieux via social
card) ; JS affiche **logo → image → emoji** (lieux) et **image → emoji** (events), cartes +
accordéon.

### Bug 4 — rafraîchir le cache à chaque modif (AJOUTÉ)
Signal `post_save`/`post_delete` sur `Event` et `PostalAddress` → `refresh_seo_cache`
(Celery, débouncé : 1 refresh / 70 s, différé 60 s).

## Validation (quand le conteneur est relancé)

```bash
# 1. Vérifier le code
docker exec lespass_django poetry run python manage.py check

# 2. Régénérer le cache (indispensable : pa_id préfixés + images)
docker exec lespass_django poetry run python manage.py shell -c \
"from seo.tasks import refresh_seo_cache; print(refresh_seo_cache())"
```

### Tests visuels (Chrome) sur `/explorer/` et un tenant `/federation/`
1. **Bug 1** : cliquer plusieurs lieux de tenants différents → la carte centre sur **la
   bonne** adresse à chaque fois (plus de décalage).
2. **Bug 2** : pill « Événements », cliquer une carte event → la carte se centre sur
   l'adresse de l'event + popup ouverte.
3. **Bug 3** : les cartes lieu montrent logo/image (pas l'emoji 🏛️ si une image existe) ;
   les cartes event et l'accordéon montrent la vignette de l'event (pas l'emoji 🎶).
4. **Bug 4** : modifier une adresse ou un event dans l'admin → vérifier (logs Celery)
   qu'un `refresh_seo_cache` est programmé (countdown 60 s), et qu'une rafale de modifs ne
   déclenche **qu'un** refresh (débounce 70 s).

## Points d'attention

- **Régénération du cache obligatoire** après déploiement : sans `refresh_seo_cache`, le
  cache garde les anciens `pa_id` (collision) et pas d'images.
- **CSS images** : les images réutilisent `.explorer-card-icon` (80×80) ; l'accordéon a des
  dimensions inline (28×28). À vérifier visuellement (recadrage, border-radius).
## Bugs supplémentaires corrigés (audit)

- **Bug 5 — surbrillance des pins (RÉSOLU)** : `highlightPin`/`highlightPinClass` ciblaient
  `.explorer-pin[data-lieu-id]` alors que les pins portent `data-tenant-id` → la
  surbrillance (clic/survol d'une carte) ne marchait jamais. Corrigé + surligne désormais
  **tous** les pins d'un lieu (cas multi-adresses), via `querySelectorAll`.
- **Bug 6 — clic d'un pin en mode « Événements » (RÉSOLU)** : `scrollToCard` ne cherchait
  qu'une carte lieu (`data-type="lieu"`), absente en mode event → aucun scroll. Fallback
  ajouté vers la 1ʳᵉ carte event du tenant.
- **Cohérence popup (AMÉLIORÉ)** : la popup carte affiche maintenant logo → image (comme
  les cartes), via `tenant_image_url`.

**Test** : survoler/cliquer une carte → le(s) pin(s) du lieu se surligne(nt) ; en mode
« Événements », cliquer un pin scrolle vers sa carte event.
- **Débounce Celery** : nécessite un worker actif. Le beat 4 h reste le filet de sécurité.
