# Carte explorer ROOT — pills exclusives, tags, URL partageable

**Date :** 2026-05-20
**Migration :** Non

## Ce qui a été fait

Cf. `TECH_DOC/SESSIONS/SEO/CHANTIER-06-explorer-ux-pills-tags.md`.

Résumé : la page `/explorer/` du ROOT a maintenant 2 pills exclusives (Lieux /
Événements) au lieu de 3, une barre de tag chips (top 10) cliquables pour
filtrer par tag, et les filtres sont reflétés dans l'URL pour permettre le
partage. L'accordéon "Prochains événements" sur les cards lieu est réparé.
Le JSON-LD federation des explorers tenant `/federation/` est corrigé
(régression silencieuse de CHANTIER-05).

## Tests à réaliser

### Test 1 : Refresh + chargement initial

1. Lancer un refresh manuel du cache :
   ```bash
   docker exec lespass_django poetry run python manage.py shell -c "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"
   ```
2. Ouvrir `/explorer/` du ROOT (`http://www.tibillet.localhost/explorer/`)
3. Vérifier visuellement :
   - 2 pills (pas 3) : "Lieux" et "Événements", **Lieux active par défaut**
   - Une barre de tag chips visible sous les pills (avec leurs couleurs)
   - Cards de tenant avec accordéon "N événements" qui se déplie au clic

### Test 2 : Mode Événements

1. Cliquer sur la pill "Événements"
2. La liste passe à 1 card par event futur (tri chronologique)
3. Chaque card event affiche :
   - Date + lieu (PA) + tenant en sous-titre
   - Tags inline (max 3 affichés) avec leurs couleurs
   - Titre cliquable qui ouvre `/event/<slug>/` dans un nouvel onglet
4. L'URL change : `?v=event` apparaît dans la barre d'adresse

### Test 3 : Tag chip + URL

1. Cliquer un chip (ex : `jazz`)
2. La liste se filtre, les markers sur la carte aussi
3. URL devient `?v=event&tag=jazz` (ou `?tag=jazz` en mode Lieux)
4. Le chip a une bordure noire + icône check
5. Cliquer le bouton `+ N tags` (si présent) : 2e ligne de chips apparaît
6. Re-cliquer le chip actif : désactive, URL nettoyée

### Test 4 : URL partageable

1. Composer manuellement `/explorer/?v=event&tag=<slug-valide>` (utiliser un
   slug de tag réellement présent dans la base, sinon test 5)
2. Au chargement : pill Événements active, chip présélectionné, liste/markers filtrés
3. Copier l'URL, l'ouvrir dans un nouvel onglet : même état restauré

### Test 5 : Empty state

1. Naviguer vers `/explorer/?tag=ce-tag-nexiste-pas-12345`
2. Liste vide avec :
   - Message `Aucun événement « ce-tag-nexiste-pas-12345 » dans la zone visible.`
   - Bouton `Effacer le filtre`
3. Clic sur le bouton : restaure la liste complète, URL nettoyée

### Test 6 : Explorer tenant — JSON-LD federation (régression CHANTIER-05)

1. Ouvrir `/federation/` sur un tenant (ex : `http://lespass.tibillet.localhost/federation/`)
2. Inspecter le `<script type="application/ld+json">` injecté dans le `<head>`
3. Vérifier que `subOrganization` **n'est pas vide** (avant le fix Task 3,
   le tableau était silencieusement vide à cause de la clé `lieux` renommée en
   `tenants` côté `build_explorer_data_for_tenants`)

### Test 7 : Cache Memcached (sanity)

1. Admin ROOT `/admin/seo/seocache/` en superuser
2. Vérifier qu'on a l'entrée `aggregate_points` globale (tenant=None)
3. Dans `data.points[i].events_futurs[j]`, le champ `tags` doit être présent
   (liste éventuellement vide). Pour au moins 1 event tagué, on doit voir
   `tags: [{slug, name, color}]`

### Test 8 : Tests automatisés

```bash
# Unit tests (rapide) — dans le container
docker exec -e API_KEY=test lespass_django poetry run pytest \
  tests/pytest/test_seo_event_tags.py \
  tests/pytest/test_seo_aggregate_points.py \
  tests/pytest/test_seo_indexing.py -v

# E2E Playwright — depuis le host (le serveur doit être actif dans byobu)
set -a && source .env && set +a
poetry run pytest tests/e2e/test_explorer_ux_pills_tags.py -v -s
```

## Compatibilité et rollback

- **Cache rétrocompatible** : le JS lit `.tags || []`, donc un cache sans tags
  ne plante pas (mais la barre chips sera vide tant que `refresh_seo_cache`
  n'a pas tourné).
- **Pas de changement de schéma DB.**
- **Explorer tenant** : continue de fonctionner avec la nouvelle structure
  `{points, tenants}` retournée par `build_explorer_data_for_tenants`.
- **Rollback partiel** : annuler les commits Tasks 4-10 (frontend) ramène
  à l'ancien JS. Les commits Tasks 1-3 (backend + bug fix) peuvent rester —
  ils sont compatibles avec l'ancien JS qui ignore simplement le champ `tags`.
