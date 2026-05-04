# Explorer — Mode focus monnaie

## Ce qui a ete fait

Visualisation sur la carte `/explorer/` des relations entre lieux et monnaies federees du reseau TiBillet.

### Modifications

| Fichier | Changement |
|---|---|
| `seo/services.py` | `get_all_assets()` enrichi avec 5 nouveaux champs (tenant_origin_id/name, accepting_tenant_ids, accepting_count, is_federation_primary). `build_tenant_config_data()` ajoute `accepted_asset_ids`. `build_explorer_data()` propage les champs aux lieux. |
| `seo/models.py` | Inchange (AGGREGATE_ASSETS et TENANT_SUMMARY utilises sans changement de schema) |
| `seo/tasks.py` | Inchange (propagation automatique via `**config_data`) |
| `seo/static/seo/explorer.js` | +`ASSET_BADGE_CONFIG`, +`buildLieuAssetBadges`, +`handleAssetBadgeClick`, +section "Mode focus asset" (focusOnAsset, clearAssetFocus, applyDimming, drawHull, drawArcs, computeConvexHull, bezierArcPoints, drawAssetLinks, renderAssetLegend, refreshAssetBadgeActiveState, refreshMapMarkersForFocus, findAssetByUuid). `buildFlatCard` branchee sur focusOnAsset pour les cards asset. |
| `seo/static/seo/explorer.css` | Styles `.lieu-asset-badges`, `.lieu-asset-badge`, `.explorer-pin--dimmed`, `.explorer-asset-legend`, `.explorer-card--active` |
| `seo/templates/seo/explorer.html` | +DOM legende `#explorer-asset-legend` dans `.explorer-container` |
| `Administration/management/commands/demo_data_v2.py` | +`_create_federations_demo` : cree 2 Federations (globale + partielle) + asset "Monnaie Coeur" pour le-coeur-en-or |
| `tests/pytest/test_seo_explorer_assets.py` | 6 tests unitaires : enrichissement assets, TENANT_SUMMARY, build_explorer_data |
| `tests/e2e/test_explorer_assets_focus.py` | 3 tests E2E : hull polygon, toggle focus, clic sur badge lieu |

## Tests a realiser

### Test 1 : Focus sur TiBillet (federation globale)
1. Aller sur `/explorer/`
2. Cliquer sur le pill "Monnaies"
3. Cliquer sur la card "Fédéré TiBillet"
4. **Verifier** : polygone vert translucide englobe tous les lieux acceptants sur la carte
5. **Verifier** : la legende en bas-gauche affiche "TiBillet" + "Origine : Lespass" + "Partagée avec N autre(s) lieu(x)"
6. **Verifier** : la card a une bordure verte (etat actif)
7. **Verifier** : les lieux non acceptants sont dimmed (opacity 0.3 + grayscale)
8. Cliquer a nouveau sur la card → tout se reset

### Test 2 : Focus sur asset federe partiellement (Temps)
1. Filtrer par "Monnaies"
2. Cliquer sur la card "Temps"
3. **Verifier** : arcs courbes depuis Lespass vers Chantefrein
4. **Verifier** : les autres lieux sont dimmed
5. **Verifier** : la legende affiche "Partagée avec 1 autre(s) lieu(x)"

### Test 3 : Focus sur asset local (Cadeau ou Monnaie Coeur)
1. Cliquer sur la card "Cadeau" (origine Lespass, non federe)
2. **Verifier** : uniquement Lespass est highlight, les autres sont dimmed
3. **Verifier** : pas d'arc ni de polygone (asset local a 1 lieu)
4. **Verifier** : la legende affiche "Utilisée localement"

### Test 4 : Badge monnaie sur card lieu
1. Revenir sur le filtre "Tous"
2. Sur la card d'un lieu (ex: "La Maison des Communs"), repérer les badges monnaies en dessous de la description
3. Cliquer sur le badge "🔗 Fédéré"
4. **Verifier** : meme effet qu'un clic sur la card "TiBillet" dans la liste
5. **Verifier** : le badge devient vert (etat actif)

### Test 5 : Toggle et multi-focus
1. Cliquer sur "Fédéré TiBillet"
2. Puis cliquer sur "Temps"
3. **Verifier** : le polygone TiBillet disparait, les arcs Temps apparaissent
4. **Verifier** : un seul focus actif a la fois (pas de cumul)

### Verifications en base

```bash
docker exec lespass_django poetry run python manage.py shell -c "
from seo.services import build_explorer_data
data = build_explorer_data()
for a in data['assets']:
    print(f\"{a['name']} ({a['category']}) origine={a['tenant_origin_name']} accepte_par={a['accepting_count']} lieux\")
"
```

Expected :
- Fédéré TiBillet : FED, origine=Lespass, accepté par >= 5 lieux
- Temps : TIM, origine=Lespass, accepté par 2 lieux (Lespass + Chantefrein)
- Monnaie Coeur : TLF, origine=Le Coeur en or, accepté par 1 lieu

### Lancer les tests automatises

```bash
# Pytest unitaires (6 tests)
docker exec lespass_django poetry run pytest tests/pytest/test_seo_explorer_assets.py -v

# E2E Playwright Python (3 tests)
docker exec lespass_django poetry run pytest tests/e2e/test_explorer_assets_focus.py -v
```

## Compatibilite

- **Additif** : le mode focus ne modifie pas les autres interactions (filtres, search, accordion lieu).
- **Etat exclusif** : un seul `activeAssetUuid` a la fois. Si l'utilisateur clique sur un autre asset, le precedent est remplace.
- **Responsive mobile** : la legende s'affiche en bas au-dessus du FAB (via media query, `bottom: 80px` + `max-width: none`).
- **Desktop** : la legende est en bas-gauche dans `.explorer-container`, en `position: absolute`.

## Bugs connus / TODO

- Les ERROR teardown FK `fedow_connect_fedowconfig → AuthBillet_wallet` dans pytest sont un probleme preexistant (non introduit par cette task). A investiguer en dernière phase.
